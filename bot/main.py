"""TerminJetzt Heilbronn – Telegram Bot (adapted for provided menu.yaml)
=====================================================================
Place this file next to **menu.yaml** and a **.env** containing at least
`TELEGRAM_TJBOT_TOKEN`.  Run with:

    pip install pytelegrambotapi python-dotenv pyyaml
    python bot_main.py

This version automatically detects language blocks in `menu.yaml` (e.g.
`en:` → `menu:`) and renders nested inline-keyboard navigation with Back
buttons.  It also exposes a *Notify Me* link to your Telegram channel at
root level.
"""
from __future__ import annotations

import os
import logging
from pathlib import Path
from functools import lru_cache
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional, Any

import yaml
from telebot import TeleBot, types
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# 1. Domain Model
# ---------------------------------------------------------------------------

@dataclass(slots=True, frozen=True)
class MenuItem:
    id: str
    text: str
    answer: Optional[str] = None
    children: Tuple["MenuItem", ...] = field(default_factory=tuple)

    # Recursive helpers ----------------------------------------------------

    def find(self, path: List[str]) -> Optional["MenuItem"]:
        if not path:
            return self
        head, *tail = path
        for child in self.children:
            if child.id == head:
                return child.find(tail)
        return None

    def is_leaf(self) -> bool:
        return not self.children

    def breadcrumb(self, path: List[str]) -> str:
        """Return `Section / Subsection / Item` for display heading."""
        parts: List[str] = []
        node = self.find(path)
        # Walk back towards root
        while node and path:
            parts.append(node.text.strip())
            path = path[:-1]
            node = self.find(path) if path else None
        if node:
            parts.append(node.text.strip())
        return " / ".join(reversed(parts))

# ---------------------------------------------------------------------------
# 2. Menu Loader – YAML → MenuItem tree
# ---------------------------------------------------------------------------

class MenuLoader:
    def __init__(self, yaml_path: Path, default_lang: str = "en") -> None:
        self.yaml_path = yaml_path
        self.default_lang = default_lang
        self.root_items: Tuple[MenuItem, ...] = self._load()

    # Public ----------------------------------------------------------------

    def get_root(self) -> Tuple[MenuItem, ...]:
        return self.root_items

    def find_by_path(self, path: List[str]) -> Optional[MenuItem]:
        if not path:
            return None
        for root in self.root_items:
            if root.id == path[0]:
                return root.find(path[1:])
        return None

    # Internal --------------------------------------------------------------

    def _load(self) -> Tuple[MenuItem, ...]:
        with open(self.yaml_path, "r", encoding="utf-8") as fh:
            raw: Any = yaml.safe_load(fh)

        # Accept 2 formats:
        # 1) Top-level `menu: [...]`
        # 2) Language block `en: { menu: [...] }`
        if isinstance(raw, dict) and isinstance(raw.get("menu"), list):
            entries = raw["menu"]
        elif isinstance(raw, dict) and self.default_lang in raw:
            entries = raw[self.default_lang].get("menu", [])
        else:
            # Fallback: first dict value containing a list under `menu`.
            entries = []
            for val in raw.values() if isinstance(raw, dict) else []:
                if isinstance(val, dict) and isinstance(val.get("menu"), list):
                    entries = val["menu"]
                    break

        return tuple(self._parse_item(node) for node in entries)

    def _parse_item(self, node: Dict[str, Any]) -> MenuItem:
        child_nodes = [c for c in node.get("children", []) if isinstance(c, dict)]
        children = tuple(self._parse_item(c) for c in child_nodes)
        return MenuItem(
            id=node.get("id", ""),
            text=node.get("text", ""),
            answer=node.get("answer"),
            children=children,
        )

# ---------------------------------------------------------------------------
# 3. Keyboard Factory – MenuItem → InlineKeyboardMarkup
# ---------------------------------------------------------------------------

BACK_ROOT = "ROOT"  # callback data that returns to top-level menu

class KeyboardFactory:
    def __init__(self, channel: Optional[str] = None) -> None:
        self.channel = channel

    def build(self, parent_path: List[str], items: Tuple[MenuItem, ...]) -> types.InlineKeyboardMarkup:
        kb = types.InlineKeyboardMarkup(row_width=1)
        for itm in items:
            cb_data = ":".join(parent_path + [itm.id])
            kb.add(types.InlineKeyboardButton(itm.text, callback_data=cb_data))

        # Channel link on root menu
        if not parent_path and self.channel:
            kb.add(
                types.InlineKeyboardButton(
                    "🔔 Notify Me",
                    url=f"https://t.me/{self.channel.lstrip('@')}",
                )
            )

        # Back button on sub-menus
        if parent_path:
            prev_cb = ":".join(parent_path[:-1]) if parent_path[:-1] else BACK_ROOT
            kb.add(types.InlineKeyboardButton("⬅️ Back", callback_data=prev_cb))
        return kb

# ---------------------------------------------------------------------------
# 4. Bot Orchestrator
# ---------------------------------------------------------------------------

class TerminBot:
    def __init__(self, token: str, loader: MenuLoader, channel: Optional[str] = None):
        self.bot = TeleBot(token, parse_mode="HTML")
        self.loader = loader
        self.kbf = KeyboardFactory(channel)
        self._register_handlers()

    # Register telegram handlers ------------------------------------------

    def _register_handlers(self) -> None:
        @self.bot.message_handler(commands=["start", "help"])
        def on_start(msg: types.Message):
            welcome = (
                "<b>Welcome to TerminJetzt Heilbronn!</b>\n"
                "Use the buttons below to explore appointment info, docs, and FAQs."
            )
            kb = self.kbf.build([], self.loader.get_root())
            self.bot.send_message(msg.chat.id, welcome, reply_markup=kb)

        @self.bot.callback_query_handler(func=lambda c: True)
        def on_callback(call: types.CallbackQuery):
            data = call.data or BACK_ROOT
            if data == BACK_ROOT:
                self._show_menu(call, [])
                return
            path = data.split(":")
            item = self.loader.find_by_path(path)

            # Unknown → reset
            if item is None:
                self._show_menu(call, [])
                return

            # Leaf node → show answer (stay on same path)
            if item.is_leaf() and item.answer:
                title = item.breadcrumb(path)
                text = f"<b>{title}</b>\n\n{item.answer}"
                kb = self.kbf.build(path, ())
                self.bot.edit_message_text(
                    text,
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    reply_markup=kb,
                )
            else:
                # Non-leaf → open submenu
                self._show_menu(call, path)

        @self.bot.message_handler(func=lambda m: True)
        def on_fallback(msg: types.Message):
            answer = self._search(msg.text or "")
            if answer:
                self.bot.reply_to(msg, answer)
            else:
                self.bot.reply_to(msg, "Sorry, I didn't get that. Please use the menu.")

    # Helpers --------------------------------------------------------------

    def _show_menu(self, call: types.CallbackQuery, path: List[str]):
        node = self.loader.find_by_path(path) if path else None
        items = node.children if node else self.loader.get_root()
        kb = self.kbf.build(path, items)
        # Edit only the keyboard; keep the same text
        self.bot.edit_message_reply_markup(
            call.message.chat.id, call.message.message_id, reply_markup=kb
        )

    @lru_cache(maxsize=128)
    def _search(self, query: str) -> Optional[str]:
        q_words = query.lower().split()
        for root in self.loader.get_root():
            for leaf in self._iterate_leaves(root):
                if leaf.answer and any(w in leaf.answer.lower() for w in q_words):
                    return leaf.answer
        return None

    def _iterate_leaves(self, item: MenuItem):
        if item.is_leaf():
            yield item
        else:
            for c in item.children:
                yield from self._iterate_leaves(c)

    # API ------------------------------------------------------------------

    def run(self):
        logging.info("🤖 Bot is polling …")
        self.bot.infinity_polling(skip_pending=True)

# ---------------------------------------------------------------------------
# 5. Entrypoint
# ---------------------------------------------------------------------------

def main():
    load_dotenv()
    token = os.getenv("TELEGRAM_TJBOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_TJBOT_TOKEN missing in .env")

    channel = os.getenv("CHANNEL")
    default_lang = os.getenv("DEFAULT_LANG", "en")

    # Use script directory as reference so it runs from anywhere
    base_dir = Path(__file__).resolve().parent
    menu_path = base_dir / "data/menu.yaml"

    loader = MenuLoader(menu_path, default_lang)
    TerminBot(token, loader, channel).run()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    main()
