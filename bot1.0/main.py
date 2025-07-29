# bot.py
import os
import logging
from telebot import TeleBot, types
from pathlib import Path
import yaml
from dotenv import load_dotenv


load_dotenv()
TOKEN = os.getenv("TELEGRAM_TJBOT_TOKEN")
CHANNEL = os.getenv("CHANNEL")
FAQ_YAML = Path("bot/data/menu.yaml")

# load yaml once
faq = (
    yaml.safe_load(FAQ_YAML.read_text(encoding="utf-8")) if FAQ_YAML.exists() else {}
)

if not TOKEN:
    raise ValueError("TELEGRAM_TJBOT_TOKEN is not set in .env file")
bot = TeleBot(TOKEN)


@bot.message_handler(commands=["start", "help"])
def cmd_start(message):
    """
    Handle /start and /help commands.
    Sends a welcome message with inline buttons for FAQ and channel.
    """
    if not CHANNEL:
        bot.send_message(message.chat.id, "Channel not configured.")
        return
    channel_url = f"https://t.me/{CHANNEL.lstrip('@')}"
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton("📅 Release Times", callback_data="times"),
        types.InlineKeyboardButton("📋 Required Docs", callback_data="docs"),
        types.InlineKeyboardButton("➕ Join channel", url=channel_url),
    )
    bot.send_message(
        message.chat.id,
        "👋 Welcome to TerminJetzt Heilbronn!\n"
        "I’m here to help you catch Ausländeramt slots in seconds.",
        reply_markup=kb,
    )


@bot.callback_query_handler(func=lambda c: c.data in ("times", "docs"))
def handle_faq(call):
    answer = faq.get(call.data, "Info coming soon.")
    bot.answer_callback_query(call.id, answer, show_alert=True)


@bot.message_handler(commands=["faq"])
def cmd_faq(message):
    bot.send_message(
        message.chat.id,
        "📅 Release times: " + faq.get("times", "Tue–Thu 08-11 h") + "\n"
        "📋 Required docs: " + faq.get("docs", "Passport, photo, 35 € fee"),
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    bot.infinity_polling()
