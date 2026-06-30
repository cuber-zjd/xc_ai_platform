import os
import json
import re
import time
from datetime import datetime
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

def clean_xinhua_url(url):
    url = url.strip()
    if url.startswith("//"):
        return "https:" + url
    return url

def crawl_xinhuanet(keyword):
    # 本爬虫严格执行“优先爬取官方基站”原则，直接连接新华网官方搜索中心
    print(f"--- [新华网] 启动基站直连检索 关键字: '{keyword}' ---")
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
            url = "https://so.news.cn/"
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            
            # 定位首个 class="input" 的输入框
            search_ipt = page.locator("input.input").first
            search_ipt.click()
            search_ipt.fill(keyword)
            page.wait_for_timeout(1000)
            
            # 模拟按 Enter 执行检索并等待 6 秒加载
            search_ipt.press("Enter")
            page.wait_for_timeout(6000)
            
            html = page.content()
            soup = BeautifulSoup(html, "html.parser")
            
            # 提取卡片容器
            cards = soup.find_all("div", class_="item")
            print(f"  [新华网] 成功定位候选卡片数: {len(cards)}")
            
            for card in cards:
                try:
                    title_el = card.find(class_="title")
                    if not title_el:
                        continue
                    a_tag = title_el.find("a")
                    if not a_tag:
                        continue
                        
                    title = a_tag.get_text().strip()
                    href = a_tag.get("href", "")
                    link = clean_xinhua_url(href)
                    
                    # 提取发布时间与来源作者
                    source_el = card.find(class_="source")
                    source_text = source_el.get_text().strip() if source_el else "新华网"
                    author = f"新华网（{source_text}）" if source_text != "新华网" else "新华网"
                    
                    time_el = card.find(class_="pub-tim")
                    created_at = time_el.get_text().strip() if time_el else datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    
                    articles.append({
                        "title": title,
                        "author": author,
                        "created_at": created_at,
                        "content": title, # 搜索结果卡片无正文段落，以标题填充以符合规范
                        "url": link,
                        "likes": 0,
                        "comments": 0,
                        "retweets": 0
                    })
                except Exception as ex:
                    print(f"  解析卡片出错: {ex}")
                    
        except Exception as e:
            print(f"  [新华网] 检索流程异常: {e}")
        finally:
            browser.close()
            
    return articles

if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    for kw, filename in [("蜜雪冰城", "data/mixue_news.json"), ("茶百道", "data/chabaidao_news.json")]:
        results = crawl_xinhuanet(kw)
        
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
