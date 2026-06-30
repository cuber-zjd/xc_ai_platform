import os
import json
import time
from urllib.parse import quote
from datetime import datetime
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

def clean_xyy_url(url):
    url = url.strip()
    if url.startswith("//"):
        return "https:" + url
    elif url.startswith("/"):
        return "https://www.xinyingyang.com" + url
    return url

def crawl_xinyingyang(keyword):
    # 本爬虫严格执行“优先爬取官方基站”原则，直连新营养官方检索系统
    print(f"--- [新营养] 启动基站直连检索 关键字: '{keyword}' ---")
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
            url = f"https://www.xinyingyang.com/index.php?m=search&c=index&a=init&typeid=1&siteid=1&q={quote(keyword)}"
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_timeout(6000)
            
            html = page.content()
            soup = BeautifulSoup(html, "html.parser")
            
            # 定位卡片大容器
            cards = soup.find_all("li", class_=lambda x: x and "wrap" in x)
            print(f"  [新营养] 成功定位候选卡片数: {len(cards)}")
            
            for card in cards:
                try:
                    a_tag = card.find("a", class_="card-title")
                    if not a_tag:
                        continue
                        
                    title = a_tag.get_text().strip()
                    href = a_tag.get("href", "")
                    link = clean_xyy_url(href)
                    
                    desc_el = card.find("p", class_="card-text")
                    content = desc_el.get_text().strip() if desc_el else title
                    
                    # 提取发布时间
                    adds_el = card.find("div", class_="adds")
                    adds_text = adds_el.get_text().strip() if adds_el else ""
                    
                    if adds_text.startswith("发布时间："):
                        adds_text = adds_text.replace("发布时间：", "").strip()
                    
                    if adds_text and len(adds_text) >= 10:
                        created_at = f"{adds_text[:10]} 00:00:00"
                    else:
                        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    
                    articles.append({
                        "title": title,
                        "author": "新营养",
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
            print(f"  [新营养] 检索流程异常: {e}")
        finally:
            browser.close()
            
    return articles

if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    for kw, filename in [("蜜雪冰城", "data/mixue_news.json"), ("茶百道", "data/chabaidao_news.json")]:
        results = crawl_xinyingyang(kw)
        
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
