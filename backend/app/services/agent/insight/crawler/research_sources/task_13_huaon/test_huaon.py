import os
import json
import re
import time
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

def clean_time(date_str):
    date_str = date_str.strip()
    try:
        if re.match(r'\d{4}-\d{2}-\d{2}', date_str):
            return f"{date_str} 00:00:00"
    except Exception:
        pass
    return time.strftime("%Y-%m-%d %H:%M:%S")

def crawl_huaon(keyword, keywords_pattern):
    print(f"开始爬取 huaon.com - 关键字: '{keyword}'")
    articles = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            ignore_https_errors=True
        )
        page = context.new_page()
        
        url = f"https://www.huaon.com/search?word={keyword}"
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_timeout(4000)
        
        html = page.content()
        soup = BeautifulSoup(html, "html.parser")
        
        headers = soup.find_all("h3")
        for h3 in headers:
            try:
                a_tag = h3.find("a")
                if not a_tag:
                    continue
                title = a_tag.get_text().strip()
                href = a_tag.get("href", "")
                link = "https://www.huaon.com" + href if href.startswith("/") else href
                
                desc_p = h3.find_next_sibling("p")
                content = desc_p.get_text().strip() if desc_p else ""
                
                if not (re.search(keywords_pattern, title) or re.search(keywords_pattern, content)):
                    continue
                    
                parent_div = h3.parent
                date_span = parent_div.find("span", class_="t-placeholder") if parent_div else None
                date_raw = date_span.get_text().strip() if date_span else ""
                created_at = clean_time(date_raw)
                
                articles.append({
                    "title": title,
                    "author": "华经产业研究院",
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
    mixue_pattern = r"蜜雪|冰城|鲜活"
    chabaidao_pattern = r"茶百道|百道"
    
    for kw, pat, filename in [("蜜雪冰城", mixue_pattern, "data/mixue_news.json"), ("茶百道", pat, "data/chabaidao_news.json")]:
        results = crawl_huaon(kw, pat)
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"成功保存 {len(results)} 条数据到 {filename}")
        time.sleep(10)
