import os
import json
import re
import time
from datetime import datetime
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

def crawl_biotech(keyword):
    print(f"--- [生物通] 通过必应站内检索 关键字: '{keyword}' ---")
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
            # 采用 cn.bing.com site 检索
            url = f"https://cn.bing.com/search?q=site:ebiotrade.com%20{keyword}"
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_timeout(4000)
            
            html = page.content()
            soup = BeautifulSoup(html, "html.parser")
            
            # 必应的搜索卡片
            cards = soup.find_all("li", class_="b_algo")
            print(f"  [生物通] 必应检索到候选记录数: {len(cards)}")
            
            for card in cards:
                try:
                    a_tag = card.find("a")
                    if not a_tag:
                        continue
                    title = a_tag.get_text().strip()
                    link = a_tag.get("href", "")
                    
                    # 核心校验：超链接必须包含 ebiotrade.com 域名以排除降级全网杂音
                    if "ebiotrade.com" not in link:
                        continue
                        
                    # 摘要
                    desc_p = card.find(class_=re.compile(r"b_caption|desc|caption"))
                    content = desc_p.get_text().strip() if desc_p else ""
                    
                    # 时间清洗：若无明确时间则使用当前时间
                    created_at = datetime.now().strftime("%Y-%m-%d 00:00:00")
                    
                    articles.append({
                        "title": title,
                        "author": "生物通",
                        "created_at": created_at,
                        "content": content,
                        "url": link,
                        "likes": 0,
                        "comments": 0,
                        "retweets": 0
                    })
                except Exception as ex:
                    print(f"  [生物通] 解析单条卡片出错: {ex}")
                    
        except Exception as e:
            print(f"  [生物通] 检索流程异常: {e}")
        finally:
            browser.close()
            
    return articles

if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    for kw, filename in [("蜜雪冰城", "data/mixue_news.json"), ("茶百道", "data/chabaidao_news.json")]:
        results = crawl_biotech(kw)
        
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
