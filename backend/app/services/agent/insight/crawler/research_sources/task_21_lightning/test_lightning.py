import os
import json
import re
import time
from urllib.parse import quote
from datetime import datetime
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

def clean_lightning_time(date_str):
    date_str = date_str.strip()
    try:
        match = re.search(r'\d{4}-\d{2}-\d{2}', date_str)
        if match:
            return f"{match.group()} 00:00:00"
    except Exception:
        pass
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def crawl_lightning(keyword):
    print(f"--- [闪电新闻] 启动基站直连检索 关键字: '{keyword}' ---")
    articles = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox"
            ]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800}
        )
        page = context.new_page()
        
        try:
            # 齐鲁网（闪电新闻）官方百度CSE站内检索接口
            url = f"https://s.iqilu.com/cse/search?q={quote(keyword)}&entry=1&s=2576961992730276856"
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_timeout(6000)
            
            html = page.content()
            soup = BeautifulSoup(html, "html.parser")
            
            # 定位卡片大容器
            cards = soup.find_all(class_="result-item")
            print(f"  [闪电新闻] 成功定位候选卡片数: {len(cards)}")
            
            for card in cards:
                try:
                    title_el = card.find(class_="result-title")
                    if not title_el:
                        continue
                        
                    a_tag = title_el.find("a")
                    if not a_tag:
                        continue
                        
                    title = a_tag.get_text().strip()
                    href = a_tag.get("href", "")
                    
                    # 只抓取与齐鲁网/闪电新闻相关的超链接
                    if "iqilu.com" not in href:
                        continue
                        
                    desc_el = card.find(class_="result-content")
                    content = desc_el.get_text().strip() if desc_el else title
                    
                    meta_el = card.find(class_="result-meta")
                    meta_text = meta_el.get_text().strip() if meta_el else ""
                    
                    created_at = clean_lightning_time(meta_text)
                    
                    # 区分作者属性：若是 sdxw 域名则定为闪电新闻，其余为齐鲁网
                    author = "闪电新闻" if "sdxw.iqilu.com" in href else "齐鲁网"
                    
                    articles.append({
                        "title": title,
                        "author": author,
                        "created_at": created_at,
                        "content": content,
                        "url": href,
                        "likes": 0,
                        "comments": 0,
                        "retweets": 0
                    })
                except Exception as ex:
                    print(f"  解析卡片出错: {ex}")
                    
        except Exception as e:
            print(f"  检索流程异常: {e}")
        finally:
            browser.close()
            
    return articles

if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    for kw, filename in [("蜜雪冰城", "data/mixue_news.json"), ("茶百道", "data/chabaidao_news.json")]:
        results = crawl_lightning(kw)
        
        # 去重
        unique_arts = {}
        for art in results:
            unique_arts[art["url"]] = art
            
        # 排序
        sorted_arts = sorted(unique_arts.values(), key=lambda x: x["created_at"], reverse=True)
        
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(sorted_arts, f, ensure_ascii=False, indent=2)
        print(f"成功保存 {len(sorted_arts)} 条数据到 {filename}")
        time.sleep(10)
