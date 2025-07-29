"""TerminJetzt Heilbronn – Telegram Bot
================================================
An object‑oriented rewrite that consumes a hierarchical ``menu.yaml`` and
serves inline‑keyboard navigation in multiple languages.
Copy‑paste this single file alongside ``menu.yaml`` and ``.env``.

Dependencies
------------
* pyTelegramBotAPI 4.x  ➜  ``pip install pytelegrambotapi python‑dotenv pyyaml``
* Python ≥ 3.9 (for | pattern‑matching)

Environment (.env)
------------------
TELEGRAM_TJBOT_TOKEN="123456:ABC…"
CHANNEL="@TerminJetztHeilbronn"
DEFAULT_LANG="en"  # optional

Structure
---------
* ``MenuItem``     – immutable node of the navigation tree.
* ``MenuLoader``   – parses YAML, builds tree, language fallback.
* ``KeyboardFactory`` – converts nodes to ``InlineKeyboardMarkup``.
* ``TerminBot``    – orchestrates TeleBot handlers.

Author: ChatGPT 2025‑07‑29
"""

from __future__ import annotations

import os
import logging
from pathlib import Path
from functools import lru_cache
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple

import yaml
from telebot import TeleBot, types
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# 1. Menu Domain Model
# ---------------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class MenuItem:
    id: str
    text: str
    answer: Optional[str] = None
    children: Tuple["MenuItem", ...] = field(default_factory=tuple)

    def find(self, path: List[str]) -> "MenuItem | None":
        """Depth‑first search for the item located at *path* (list of ids)."""
        if not path:
            return self
        head, *tail = path
        for child in self.children:
            if child.id == head:
                return child.find(tail)
        return None

    def is_leaf(self) -> bool:
        return not self.children

    # Navigation helpers ----------------------------------------------------

    def breadcrumb(self, path: List[str]) -> str:
        parts = []
        node: MenuItem | None = self.find(path)
        while node:
            parts.append(node.text.strip())
            # get parent by trimming last element and searching again
            path = path[:-1]
            node = self.find(path) if path else None
        return " / ".join(reversed(parts))


# ---------------------------------------------------------------------------
# 2. Menu Loader – YAML → MenuItem tree
# ---------------------------------------------------------------------------


class MenuLoader:
    def __init__(self, yaml_path: Path, default_lang: str = "en"):
        self.yaml_path = yaml_path
        self.default_lang = default_lang
        self.root_items: Tuple[MenuItem, ...] = self._load()

    # public api ------------------------------------------------------------

    def get_root(self) -> Tuple[MenuItem, ...]:
        return self.root_items

    def find_by_path(self, path: List[str]) -> Optional[MenuItem]:
        for root in self.root_items:
            if root.id == path[0]:
                return root.find(path[1:])
        return None

    # internal --------------------------------------------------------------

    def _load(self) -> Tuple[MenuItem, ...]:
        with open(self.yaml_path, "r", encoding="utf‑8") as f:
            raw: Dict = yaml.safe_load(f)

        lang = self.default_lang
        if isinstance(raw.get("menu"), list):
            entries = raw["menu"]
        else:  # language blocks
            entries = raw.get(lang) or next(iter(raw.values()))["menu"]

        return tuple(self._parse_item(item) for item in entries)

    def _parse_item(self, node: Dict) -> MenuItem:
        children = tuple(self._parse_item(c) for c in node.get("children", []))
        return MenuItem(
            id=node["id"],
            text=node["text"],
            answer=node.get("answer"),
            children=children,
        )


# ---------------------------------------------------------------------------
# 3. Keyboard Factory – MenuItem → InlineKeyboardMarkup
# ---------------------------------------------------------------------------

BACK_CB = "BACK"


class KeyboardFactory:
    def __init__(self, channel: str | None = None):
        self.channel = channel

    def make_keyboard(
        self, parent_path: List[str], items: Tuple[MenuItem, ...]
    ) -> types.InlineKeyboardMarkup:
        kb = types.InlineKeyboardMarkup(row_width=1)
        for itm in items:
            cb_data = ":".join(parent_path + [itm.id])
            kb.add(types.InlineKeyboardButton(itm.text, callback_data=cb_data))

        # Special Channel / Notify button at root level
        if not parent_path and self.channel:
            kb.add(
                types.InlineKeyboardButton(
                    "🔔 Notify Me (Join)",
                    url=f"https://t.me/{self.channel.lstrip('@')}",
                )
            )

        # Back button for non‑root menus
        if parent_path:
            back_data = ":".join(parent_path[:-1]) or "ROOT"
            kb.add(types.InlineKeyboardButton("⬅️ Back", callback_data=back_data))
        return kb


# ---------------------------------------------------------------------------
# 4. Bot Orchestrator
# ---------------------------------------------------------------------------


class TerminBot:
    def __init__(self, token: str, menu_loader: MenuLoader, channel: str | None = None):
        self.bot = TeleBot(token, parse_mode="HTML")
        self.menu_loader = menu_loader
        self.kbf = KeyboardFactory(channel)
        self._setup_handlers()

    # ---------------- TeleBot Handlers ------------------------------------

    def _setup_handlers(self):
        @self.bot.message_handler(commands=["start", "help"])
        def _start(msg):
            self.bot.send_chat_action(msg.chat.id, "typing")
            text = (
                "<b>Welcome to TerminJetzt Heilbronn!\n</b>"
                "Use the buttons below to explore appointment info, docs, and FAQs."
            )
            root_items = self.menu_loader.get_root()
            kb = self.kbf.make_keyboard([], root_items)
            self.bot.send_message(msg.chat.id, text, reply_markup=kb)

        @self.bot.callback_query_handler(func=lambda c: True)
        def _callbacks(call):
            path = (
                [] if call.data == "ROOT" else call.data.split(":") if call.data else []
            )
            item = self.menu_loader.find_by_path(path) if path else None
            if item is None:  # unknown path, go home
                root_items = self.menu_loader.get_root()
                kb = self.kbf.make_keyboard([], root_items)
                self.bot.edit_message_reply_markup(
                    call.message.chat.id, call.message.message_id, reply_markup=kb
                )
                return

            # if leaf, send answer, keep same kb
            if item.is_leaf() and item.answer:
                self.bot.answer_callback_query(call.id)
                breadcrumb = item.breadcrumb(path)
                self.bot.edit_message_text(
                    f"<b>{breadcrumb}</b>\n\n{item.answer}",
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    reply_markup=self.kbf.make_keyboard(path, ()),
                )
            else:  # has children – open submenu
                self.bot.answer_callback_query(call.id)
                kb = self.kbf.make_keyboard(path, item.children)
                self.bot.edit_message_reply_markup(
                    call.message.chat.id,
                    call.message.message_id,
                    reply_markup=kb,
                )

        @self.bot.message_handler(func=lambda m: True, content_types=["text"])
        def _fallback(msg):
            """Handle free text via simple keyword lookup."""
            answer = self._search_faq(msg.text)
            if answer:
                self.bot.reply_to(msg, answer)
            else:
                self.bot.reply_to(
                    msg, "Sorry, I didn't understand that. Please use the menu below."
                )

    # ---------------- Helpers --------------------------------------------

    @lru_cache(maxsize=128)
    def _search_faq(self, text: str) -> Optional[str]:
        text_lower = text.lower()
        # naive search – iterate all leaf answers
        for root in self.menu_loader.get_root():
            for leaf in self._iter_leaves(root):
                if leaf.answer and any(
                    word in leaf.answer.lower() for word in text_lower.split()
                ):
                    return leaf.answer
        return None

    def _iter_leaves(self, item: MenuItem):
        if item.is_leaf():
            yield item
        else:
            for child in item.children:
                yield from self._iter_leaves(child)

    # ---------------- API -------------------------------------------------

    def run(self):
        logging.info("🤖 TerminJetzt bot polling started …")
        self.bot.infinity_polling()


# ---------------------------------------------------------------------------
# 5. Entrypoint
# ---------------------------------------------------------------------------


def main():
    load_dotenv()
    token = os.getenv("TELEGRAM_TJBOT_TOKEN")
    channel = os.getenv("CHANNEL")
    default_lang = os.getenv("DEFAULT_LANG", "en")

    if not token:
        raise RuntimeError("TELEGRAM_TJBOT_TOKEN missing in environment")

    menu_path = Path("bot/data/menu.yaml")
    ml = MenuLoader(menu_path, default_lang)
    bot = TerminBot(token, ml, channel)
    bot.run()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s"
    )
    main()
