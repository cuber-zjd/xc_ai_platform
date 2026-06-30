import os
import json
import re
import time
from datetime import datetime
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

def clean_stockstar_time(date_str):
    date_str = date_str.strip()
    try:
        if re.match(r'\d{4}-\d{2}-\d{2}', date_str):
            return f"{date_str} 00:00:00"
    except Exception:
        pass
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def crawl_stockstar_base(keyword):
    # 本爬虫严格奉行“优先爬取基站”原则，直接请求证券之星主域名及新闻频道首页，在内存中进行深度关联过滤
    print(f"--- [证券之星] 启动基站直连检索 关键字: '{keyword}' ---")
    articles = []
    
    urls = [
        "https://www.stockstar.com/",
        "https://news.stockstar.com/"
    ]
    
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
        
        for url in urls:
            try:
                print(f"  正在请求基站页面: {url}")
                page.goto(url, wait_until="domcontentloaded")
                page.wait_for_timeout(4000)
                
                html = page.content()
                soup = BeautifulSoup(html, "html.parser")
                
                # 遍历解析页面上所有的超链接 a 标签
                links = soup.find_all("a")
                print(f"    成功提取 a 标签数: {len(links)}")
                
                for a in links:
                    try:
                        title = a.get_text().strip()
                        href = a.get("href", "")
                        
                        if not title or len(title) < 5 or not href:
                            continue
                            
                        # 确保属于证券之星基站链接，排除外部广告
                        if "stockstar.com" not in href and not href.startswith("/"):
                            continue
                            
                        link = href if href.startswith("http") else "https://www.stockstar.com" + href
                        
                        # 在内存中实施关键字校验
                        if keyword in title or keyword in link:
                            # 尝试获取大致日期或使用当前运行时间
                            created_at = datetime.now().strftime("%Y-%m-%d 00:00:00")
                            
                            articles.append({
                                "title": title,
                                "author": "证券之星",
                                "created_at": created_at,
                                "content": f"证券之星官方报道: {title}",
                                "url": link,
                                "likes": 0,
                                "comments": 0,
                                "retweets": 0
                            })
                    except Exception:
                        pass
            except Exception as e:
                print(f"  请求基站页面出错: {e}")
                
        browser.close()
        
    return articles

if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    for kw, filename in [("蜜雪冰城", "data/mixue_news.json"), ("茶百道", "data/chabaidao_news.json")]:
        results = crawl_stockstar_base(kw)
        
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
