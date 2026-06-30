import os
import json
import re
import time
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

def clean_title(title_html):
    return re.sub(r'<[^>]+>', '', title_html).strip()

def parse_time(time_str):
    now = datetime.now()
    time_str = time_str.strip()
    try:
        if "分钟前" in time_str:
            mins = int(re.search(r'\d+', time_str).group())
            dt = now - timedelta(minutes=mins)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        elif "小时前" in time_str:
            hours = int(re.search(r'\d+', time_str).group())
            dt = now - timedelta(hours=hours)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        elif "昨天" in time_str:
            dt = now - timedelta(days=1)
            return dt.strftime("%Y-%m-%d 00:00:00")
        elif "天前" in time_str:
            days = int(re.search(r'\d+', time_str).group())
            dt = now - timedelta(days=days)
            return dt.strftime("%Y-%m-%d 00:00:00")
        else:
            match = re.search(r'(\d{4})[-.](\d{1,2})[-.](\d{1,2})', time_str)
            if match:
                return f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d} 00:00:00"
            match_no_year = re.search(r'(\d{1,2})[-.](\d{1,2})', time_str)
            if match_no_year:
                return f"{now.year}-{int(match_no_year.group(1)):02d}-{int(match_no_year.group(2)):02d} 00:00:00"
    except Exception:
        pass
    return now.strftime("%Y-%m-%d %H:%M:%S")

def crawl_kamen(keywords_pattern):
    url = "https://www.36kr.com/user/1080897699"
    print(f"开始爬取咖门 36kr 专栏主页 - 过滤模式: '{keywords_pattern}'")
    articles = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_timeout(5000)
        
        html = page.content()
        soup = BeautifulSoup(html, "html.parser")
        
        cards = soup.find_all("div", class_="kr-shadow-content")
        for card in cards:
            try:
                title_a = card.find("a", class_="article-item-title")
                if not title_a:
                    continue
                title = clean_title(str(title_a))
                href = title_a.get("href", "")
                link = "https://36kr.com" + href if href.startswith("/") else href
                
                desc_a = card.find("a", class_="article-item-description")
                content = desc_a.get_text().strip() if desc_a else ""
                
                if not (re.search(keywords_pattern, title) or re.search(keywords_pattern, content)):
                    continue
                    
                time_span = card.find("span", class_="kr-flow-bar-time")
                time_str = time_span.get_text().strip() if time_span else ""
                created_at = parse_time(time_str)
                
                articles.append({
                    "title": title,
                    "author": "咖门",
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
    mixue_pattern = r"蜜雪|冰城"
    chabaidao_pattern = r"茶百道|百道"
    
    for pat, filename in [(mixue_pattern, "data/mixue_news.json"), (chabaidao_pattern, "data/chabaidao_news.json")]:
        results = crawl_kamen(pat)
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"成功保存 {len(results)} 条数据到 {filename}")
        time.sleep(10)
