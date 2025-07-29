# bot.py
import os
import logging
from telebot import TeleBot, types
from pathlib import Path
import yaml
from dotenv import load_dotenv


load_dotenv()
TOKEN = os.getenv("TELEGRAM_TJBOT_TOKEN")
CHANNEL = os.getenv("CHAT_ID_DEV")
FAQ_YAML = Path("data/menu.yaml")

# load yaml once
faq = yaml.safe_load(FAQ_YAML.read_text()) if FAQ_YAML.exists() else {}

bot = TeleBot(TOKEN)


@bot.message_handler(commands=["start", "help"])
def cmd_start(message):
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton("📅 Release Times", callback_data="times"),
        types.InlineKeyboardButton("📋 Required Docs", callback_data="docs"),
        types.InlineKeyboardButton(
            "➕ Join channel", url=f"https://t.me/{CHANNEL.lstrip('@')}"
        ),
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
