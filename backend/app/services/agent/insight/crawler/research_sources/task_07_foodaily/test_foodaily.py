import os
import json
import re
import time
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

def clean_time(date_str):
    date_str = date_str.strip()
    try:
        clean = date_str.replace(".", "-")
        if re.match(r'\d{4}-\d{2}-\d{2}', clean):
            return f"{clean} 00:00:00"
    except Exception:
        pass
    return time.strftime("%Y-%m-%d %H:%M:%S")

def crawl_foodaily(keyword):
    print(f"开始爬取 Foodaily.com - 关键字: '{keyword}'")
    articles = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        
        url = f"https://www.foodaily.com/search/articles?search={keyword}"
        page.goto(url, wait_until="networkidle")
        page.wait_for_timeout(4000)
        
        html = page.content()
        soup = BeautifulSoup(html, "html.parser")
        
        cards = soup.find_all("div", class_="news-wrapper")
        for card in cards:
            try:
                title_el = card.find(class_="news-title")
                if not title_el:
                    continue
                title = title_el.get_text().strip()
                
                a_tag = card.find("a")
                href = a_tag.get("href", "") if a_tag else ""
                link = "https://www.foodaily.com" + href if href.startswith("/") else href
                
                desc_el = card.find(class_="news-text")
                content = desc_el.get_text().strip() if desc_el else ""
                
                ut_el = card.find(class_="news-user-time")
                author = "每日食品网"
                date_raw = ""
                if ut_el:
                    author_el = ut_el.find(class_="search-content")
                    if author_el:
                        author = author_el.get_text().strip()
                    date_el = ut_el.find(class_="float-right")
                    if date_el:
                        date_raw = date_el.get_text().strip()
                created_at = clean_time(date_raw)
                
                articles.append({
                    "title": title,
                    "author": author,
                    "created_at": created_at,
                    "content": content,
                    "url": link,
                    "likes": 0,
                    "comments": 0,
                    "retweets": 0
                })
            except Exception as e:
                print(f"解析卡片出错: {e}")
                
        browser.close()
        
    unique_arts = {}
    for art in articles:
        unique_arts[art["url"]] = art
        
    sorted_arts = sorted(unique_arts.values(), key=lambda x: x["created_at"], reverse=True)
    return sorted_arts

if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    for kw, filename in [("蜜雪冰城", "data/mixue_news.json"), ("茶百道", "data/chabaidao_news.json")]:
        results = crawl_foodaily(kw)
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"成功保存 {len(results)} 条数据到 {filename}")
        time.sleep(10)
