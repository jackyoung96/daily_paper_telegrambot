from dotenv import load_dotenv
import os 
from collections import defaultdict

import telegram
from telegram.ext import (
    Application, 
    MessageHandler, 
    filters,
)

import sqlite3
from contextlib import closing


# load .env
load_dotenv()
telegram_bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
DB_NAME=os.environ.get('DB_NAME')

# Global variables
CATEGORIES = ["LLM", "Multimodal", "Computer vision", "Reinforcement learning", "Robotics"]
LANGS = ['KO','EN']

with closing(sqlite3.connect(DB_NAME)) as connection:
    with closing(connection.cursor()) as cursor:
        cursor.execute("""CREATE TABLE IF NOT EXISTS telegramchat (
            chatId TEXT NOT NULL,
            lang TEXT DEFAULT EN,
            category TEXT DEFAULT '%s'
            )"""% (','.join(CATEGORIES)))
        connection.commit()

async def command_daily_paper(update, context):
    chat_id = update.effective_chat.id
    msg = update.message.text

    if msg == '/start':
        # con 에 데이터 저장
        with closing(sqlite3.connect(DB_NAME)) as connection:
            with closing(connection.cursor()) as cursor:
                is_exist = cursor.execute("SELECT EXISTS (SELECT 1 FROM telegramchat WHERE chatId = ?)", (chat_id,))

                if not is_exist.fetchone()[0]:
                    cursor.execute(f"INSERT INTO telegramchat (chatId) VALUES (?)", (chat_id,))
                    connection.commit()
        
        bot = telegram.Bot(token = telegram_bot_token)
        message = "Welcome to the daily paper bot!\n\n" + \
                    "Send the category of the papers you are interested in.\n" + \
                    "Possible categories: LLM, Multimodal, Computer vision, Reinforcement learning, Robotics.\n" + \
                    "Send them seperate by comma\n" + \
                    "ex) /setcategory:LLM,Computer vision\n\n" + \
                    "Send the language of the summary you want to get.\n" + \
                    "Possible languages: KO, EN\n" + \
                    "ex) /setlang:KO" 
        await bot.send_message(chat_id, message)
    elif msg.startswith("/setcategory:"):
        categories_str = msg.replace("/setcategory:", "")
        categories = list(set([x.strip() for x in categories_str.split(',')]) & set(CATEGORIES))
        
        if categories:
            # con 에 데이터 저장
            with closing(sqlite3.connect(DB_NAME)) as connection:
                with closing(connection.cursor()) as cursor:
                    cursor.execute("UPDATE telegramchat SET category = ? WHERE chatId = ?", (','.join(categories), chat_id))
                    connection.commit()
            message = f"Category change to {', '.join(categories)}"
        else:
            message = f"Wrong categories input!! Please select categories among LLM, Multimodal, Computer vision, Reinforcement learning, Robotics."  
        bot = telegram.Bot(token = telegram_bot_token)
        await bot.send_message(chat_id, message)
    elif msg.startswith("/setlang:"):
        lang_str = msg.replace("/setlang:", "").strip()
        
        if lang_str in LANGS:
            with closing(sqlite3.connect(DB_NAME)) as connection:
                with closing(connection.cursor()) as cursor:
                    cursor.execute("UPDATE telegramchat SET lang = ? WHERE chatId = ?", (lang_str, chat_id))
                    connection.commit()
            message = f"Language change to {lang_str}"
        else:
            message = f"Wrong language input!! Please select languages among EN, and KO"
        bot = telegram.Bot(token = telegram_bot_token)
        await bot.send_message(chat_id, message)

if __name__ == "__main__":
    application = Application.builder().token(telegram_bot_token).concurrent_updates(True).read_timeout(30).write_timeout(30).build()
    application.add_handler(MessageHandler(filters.Regex("/*") & filters.TEXT, callback=command_daily_paper))
    print("Daily paper telegram bot started!", flush=True)
    application.run_polling()
