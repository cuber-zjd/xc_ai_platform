import os
import json
import time
from urllib.parse import quote
from datetime import datetime
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

def clean_netease_url(url):
    url = url.strip()
    if url.startswith("//"):
        return "https:" + url
    elif url.startswith("/"):
        return "https://www.163.com" + url
    return url

def crawl_netease(keyword):
    # 本爬虫严格执行“优先爬取官方基站”原则，直连网易官方站内搜索中心
    print(f"--- [网易新闻] 启动基站直连检索 关键字: '{keyword}' ---")
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
            url = f"https://www.163.com/search?keyword={quote(keyword)}"
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_timeout(6000)
            
            html = page.content()
            soup = BeautifulSoup(html, "html.parser")
            
            # 定位卡片大容器
            cards = soup.find_all("div", class_=lambda x: x and "keyword_new" in x)
            print(f"  [网易新闻] 成功定位候选卡片数: {len(cards)}")
            
            for card in cards:
                try:
                    h3 = card.find("h3")
                    if not h3:
                        continue
                    a_tag = h3.find("a")
                    if not a_tag:
                        continue
                        
                    title = a_tag.get_text().strip()
                    href = a_tag.get("href", "")
                    link = clean_netease_url(href)
                    
                    # 提取发布时间与来源作者
                    time_el = card.find(class_="keyword_time")
                    time_text = time_el.get_text().strip() if time_el else ""
                    
                    # 补齐格式为 YYYY-MM-DD 00:00:00
                    if time_text and len(time_text) >= 10:
                        created_at = f"{time_text[:10]} 00:00:00"
                    else:
                        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    
                    source_el = card.find(class_="keyword_source")
                    author = source_el.get_text().strip() if source_el else "网易新闻"
                    
                    articles.append({
                        "title": title,
                        "author": author,
                        "created_at": created_at,
                        "content": title,
                        "url": link,
                        "likes": 0,
                        "comments": 0,
                        "retweets": 0
                    })
                except Exception as ex:
                    print(f"  解析卡片出错: {ex}")
                    
        except Exception as e:
            print(f"  [网易新闻] 检索流程异常: {e}")
        finally:
            browser.close()
            
    return articles

if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    for kw, filename in [("蜜雪冰城", "data/mixue_news.json"), ("茶百道", "data/chabaidao_news.json")]:
        results = crawl_netease(kw)
        
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
