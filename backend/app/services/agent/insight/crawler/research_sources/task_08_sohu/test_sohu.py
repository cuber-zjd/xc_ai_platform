import os
import json
import re
import time
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

def parse_sohu_time(time_str):
    now = datetime.now()
    time_str = time_str.replace("\xa0", " ").strip()
    try:
        if "小时前" in time_str:
            hours = int(re.search(r'\d+', time_str).group())
            dt = now - timedelta(hours=hours)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        elif "分钟前" in time_str:
            mins = int(re.search(r'\d+', time_str).group())
            dt = now - timedelta(minutes=mins)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        elif "昨天" in time_str:
            dt = now - timedelta(days=1)
            return dt.strftime("%Y-%m-%d 00:00:00")
        else:
            match = re.search(r'(\d{4})[-.](\d{1,2})[-.](\d{1,2})', time_str)
            if match:
                return f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d} 00:00:00"
    except Exception:
        pass
    return now.strftime("%Y-%m-%d %H:%M:%S")

def crawl_sohu(keyword):
    print(f"开始爬取 search.sohu.com - 关键字: '{keyword}'")
    articles = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        
        url = f"http://search.sohu.com/?keyword={keyword}"
        page.goto(url, wait_until="networkidle")
        page.wait_for_timeout(4000)
        
        html = page.content()
        soup = BeautifulSoup(html, "html.parser")
        
        cards = soup.find_all(class_=re.compile(r"cards-content|plain-content"))
        for card in cards:
            try:
                title_el = card.find(class_=re.compile(r"cards-content-title|plain-title"))
                if not title_el:
                    continue
                a_tag = title_el.find("a") if title_el.name != 'a' else title_el
                if not a_tag:
                    a_tag = card.find("a")
                
                title = a_tag.get_text().strip() if a_tag else "无标题"
                href = a_tag.get("href", "") if a_tag else ""
                
                if href.startswith("//"):
                    link = "http:" + href
                elif href.startswith("/"):
                    link = "http://search.sohu.com" + href
                else:
                    link = href
                    
                desc_el = card.find(class_=re.compile(r"cards-content-right-desc|plain-content-desc"))
                content = desc_el.get_text().strip() if desc_el else ""
                
                comm_el = card.find(class_=re.compile(r"cards-content-right-comm|plain-content-comm"))
                comm_text = comm_el.get_text().replace("\xa0", " ").strip() if comm_el else ""
                
                parts = re.split(r'\s{2,}', comm_text)
                if len(parts) >= 2:
                    author = parts[0].strip()
                    time_raw = parts[-1].strip()
                elif len(parts) == 1 and parts[0]:
                    author = "搜狐号"
                    time_raw = parts[0].strip()
                else:
                    author = "搜狐网"
                    time_raw = ""
                    
                created_at = parse_sohu_time(time_raw)
                
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
        results = crawl_sohu(kw)
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"成功保存 {len(results)} 条数据到 {filename}")
        time.sleep(10)
