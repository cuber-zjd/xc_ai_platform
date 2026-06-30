import os
import json
import time
import re
from urllib.parse import quote
from datetime import datetime
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

def clean_time(showurl_text):
    # 从 "f.sdnews.com.cn/qyjj/202603/t20260324_... 2026-3-24" 中提取日期 2026-03-24 00:00:00
    showurl_text = showurl_text.strip()
    try:
        # 正则匹配尾部的 YYYY-MM-DD 或 YYYY-M-D
        match = re.search(r'(\d{4}-\d{1,2}-\d{1,2})\s*$', showurl_text)
        if match:
            date_part = match.group(1)
            y, m, d = date_part.split("-")
            return f"{int(y):04d}-{int(m):02d}-{int(d):02d} 00:00:00"
    except Exception:
        pass
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def crawl_tscj(keyword):
    # 本爬虫严格执行"优先爬取官方基站"原则，直连鲁网百度站内搜索引擎
    print(f"--- [泰山财经] 启动基站直连检索 关键字: '{keyword}' ---")
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
            # 站内百度搜索引擎接口 URL
            url = f"http://so.sdnews.com.cn/cse/search?q={quote(keyword)}&s=14876359861596845233&nsid=0"
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_timeout(6000)
            
            html = page.content()
            soup = BeautifulSoup(html, "html.parser")
            
            # 定位所有的 div.result 卡片
            cards = soup.find_all("div", class_=lambda x: x and "result" in x)
            print(f"  [泰山财经] 成功定位候选卡片数: {len(cards)}")
            
            for card in cards:
                try:
                    # 1. 标题和超链接
                    title_el = card.find("h3", class_="c-title")
                    if not title_el:
                        continue
                    a_tag = title_el.find("a")
                    if not a_tag:
                        continue
                    
                    title = a_tag.get_text().strip()
                    link = a_tag.get("href", "").strip()
                    if link.startswith("//"):
                        link = "http:" + link
                    elif not link.startswith("http"):
                        link = "http://f.sdnews.com.cn" + link
                    
                    # 2. 摘要
                    abstract_el = card.find("div", class_="c-abstract")
                    content = abstract_el.get_text().strip() if abstract_el else title
                    
                    # 3. 发布时间 (提取 span.c-showurl 的尾部日期)
                    showurl_el = card.find("span", class_="c-showurl")
                    created_at = ""
                    if showurl_el:
                        created_at = clean_time(showurl_el.get_text())
                    if not created_at:
                        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    
                    articles.append({
                        "title": title,
                        "author": "泰山财经",
                        "created_at": created_at,
                        "content": content,
                        "url": link,
                        "likes": 0,
                        "comments": 0,
                        "retweets": 0
                    })
                except Exception as ex:
                    print(f"  解析卡片出错: {ex}")
                    
        except Exception as e:
            print(f"  [泰山财经] 检索流程异常: {e}")
        finally:
            browser.close()
            
    return articles

if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    for kw, filename in [("蜜雪冰城", "data/mixue_news.json"), ("茶百道", "data/chabaidao_news.json")]:
        results = crawl_tscj(kw)
        
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
