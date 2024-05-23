from dotenv import load_dotenv
import os 
import openai

import telegram
import asyncio

import sqlite3
from contextlib import closing

from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import requests

# load .env
load_dotenv()
openai.api_key = os.environ.get('OPENAI_API_KEY')
telegram_bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
DB_NAME=os.environ.get('DB_NAME')

CATEGORIES = ["LLM", "Multimodal", "Computer vision", "Reinforcement learning", "Robotics"]

with closing(sqlite3.connect(DB_NAME)) as connection:
    with closing(connection.cursor()) as cursor:
        cursor.execute("""CREATE TABLE IF NOT EXISTS dailypaper (
            title TEXT NOT NULL,
            date DATE,
            summaryEN TEXT,
            summaryKO TEXT,
            categories TEXT
            )""")
        connection.commit()

def fetch_data():
    
    fetch_day = datetime.now()
    
    result = None
    for _ in range(7): 
        day_str = fetch_day.strftime("%Y-%m-%d")
        url = f"https://huggingface.co/papers?date={day_str}"
        response = requests.get(url)
        if response.status_code == 200:
            result = response.text
            break
        
        fetch_day -= timedelta(days=1)
        
    return fetch_day, result

# Fetch the paper abstract
def fetch_paper_abstract(paper_url):
    response = requests.get(paper_url)
    if response.status_code == 200:
        soup = BeautifulSoup(response.text, 'html.parser')
        abstract_tag = soup.find('p', class_='text-gray-700 dark:text-gray-400')
        if abstract_tag:
            abstract_tag = abstract_tag.get_text(strip=True)
            abstract_tag = abstract_tag.replace('\n', " ")
            return abstract_tag
    return "Abstract not found."

# Parse papers from the main page
def parse_papers(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    papers = []
    articles = soup.find_all('article', class_='flex flex-col overflow-hidden rounded-xl border')
    
    for article in articles:
        paper_name_tag = article.find('h3')
        if paper_name_tag:
            paper_name = paper_name_tag.get_text(strip=True)
            paper_url_tag = paper_name_tag.find('a')
            if paper_url_tag and paper_url_tag.has_attr('href'):
                paper_url = "https://huggingface.co" + paper_url_tag['href']
                paper_abstract = fetch_paper_abstract(paper_url)
                papers.append((paper_name, paper_url, paper_abstract))
    return papers

def summarize_text(text):
    response = openai.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", 
             "content": "You are a highly knowledgeable assistant who is very specialized in deep learning field. "
                        "Provide the summarization of the given content into 2~3 sentences. "
                        "ONLY provide the summmarized sentences."},
            {"role": "user", "content": f"Summarize this content into maximum 2 sentences: {text}"},
        ]
    )
    # summary = response.choices[0].message.content.strip()
    summary = text.split('.')[0]
    
    return summary

def translate_text(text):
    response = openai.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", 
             "content": "You are a highly knowledgeable assistant who is very specialized in English-Korean translating. "
                        "Provide translated text of the given content. "
                        "Don't translate English terminologies and focus on translating common words. "
                        "ONLY provide translated sentences"},
            {"role": "user", "content": f"Translate it into Korean: {text}"},
        ]
    )
    
    translated_text = response.choices[0].message.content.strip()
    
    return translated_text

def categorize_paper(title, summary):
    messages=[
        {"role": "system", 
         "content": "You are a highly knowledgeable assistant who is very specialized in deep learning field. "
                    "Suggest one or multiple categories of the given paper. "
                    f"Categories must be selected among {str(CATEGORIES)}. "
                    "ONLY provide categories seperated by comma and nothing else."},
        {"role": "user", 
         "content": "What categories would you suggest me to add to this paper?\n"
                    f"paper title: {title}\n"
                    f"paper summary: {summary}"}
    ]
    response = openai.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=messages
    )
    categories = response.choices[0].message.content.strip()
    categories = categories.split(",")
    categories = [c.strip() for c in categories]
    
    return categories

def update_paper():
    
    fetch_day, url_content = fetch_data()
    
    new_papers = []
    if url_content:
        papers = parse_papers(url_content)
        
        for paper_name, paper_url, paper_abstract in papers:
            
            # TODO: paper DB에 있는지 확인 -> 있으면 pass
            with closing(sqlite3.connect(DB_NAME)) as connection:
                with closing(connection.cursor()) as cursor:
                    is_exist = cursor.execute("SELECT EXISTS (SELECT 1 FROM dailypaper WHERE title = ?)", (paper_name,))
                    is_exist = is_exist.fetchone()[0]
            if is_exist:
                continue
            
            summary = summarize_text(paper_abstract)
            translate_summary = translate_text(summary)
            categories = categorize_paper(title=paper_name, summary=summary)
            categories_str = ','.join(categories)
            
            with closing(sqlite3.connect(DB_NAME)) as connection:
                with closing(connection.cursor()) as cursor:
                    cursor.execute(f"INSERT INTO dailypaper VALUES (?,?,?,?,?)", (paper_name, fetch_day.strftime("%Y-%m-%d"), summary, translate_summary, categories_str))
                    connection.commit()
                    
            new_papers.append({
                "title": paper_name,
                "summary_EN": summary,
                "summary_KO": translate_summary,
                "categories": categories,
                "url": paper_url
            })
    
    return new_papers

async def send_daily_message(user_info, new_papers):
    chat_id, lang, categories_str = user_info
    categories = categories_str.strip().split(',')
    
    token = telegram_bot_token
    bot = telegram.Bot(token = token)
    
    for new_paper in new_papers:
        # category 에 포함되는지 (None 인 경우 모든 category 로 간주)
        paper_categories = new_paper.get('categories')
        if len(set(paper_categories) & set(categories)) == 0:
            continue
        
        paper_name = new_paper.get('title')
        summary = new_paper.get(f'summary_{lang}')
        paper_url = new_paper.get('url')

        message = f"**{paper_name}**\n{summary}\n\n{paper_url}"
        await bot.send_message(chat_id, message, parse_mode='Markdown')

async def main():
    while True:
        print("Checking daily paper update...", flush=True)
        new_paper = update_paper()
        
        with closing(sqlite3.connect(DB_NAME)) as connection:
            with closing(connection.cursor()) as cursor:
                res = cursor.execute("SELECT chatId, lang, category FROM telegramchat")
                all_user_info = res.fetchall()
        
        if new_paper:
            print("Get new papers!!", flush=True)
                    
            for user_info in all_user_info:
                await send_daily_message(user_info, new_paper)
        
        else:
            print("There is nothing new...", flush=True)

        await asyncio.sleep(10 * 60) # 10분 대기
        
if __name__ == "__main__":
    asyncio.run(main())