import os
import json
import time
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

def crawl_sina(keyword):
    print(f"开始爬取 search.sina.com.cn - 关键字: '{keyword}'")
    articles = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        
        api_data = []
        def handle_response(res):
            if "search.sina.com.cn/api/news" in res.url:
                try:
                    content_type = res.headers.get("content-type", "")
                    if "json" in content_type:
                        json_data = res.json()
                        if json_data.get("code") == 0:
                            items = json_data.get("data", {}).get("list", [])
                            api_data.extend(items)
                except Exception:
                    pass
                    
        page.on("response", handle_response)
        
        url = f"https://search.sina.com.cn/search?q={keyword}&tp=news"
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_timeout(5000)
        
        if api_data:
            print(f"  --> 成功拦截 API 并获取到 {len(api_data)} 条新闻")
            for item in api_data:
                title = BeautifulSoup(item.get("title", ""), "html.parser").get_text().strip()
                link = item.get("url", "")
                content = item.get("summary", "") or item.get("intro", "")
                author = item.get("author", "") or item.get("source", {}).get("media", "") or "新浪网"
                created_at = item.get("dataTime", "")
                
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
        else:
            print("  --> 未能捕获到 API 响应，退回到 DOM 解析模式")
            html = page.content()
            soup = BeautifulSoup(html, "html.parser")
            cards = soup.find_all(class_="result-item")
            for card in cards:
                try:
                    title_div = card.find(class_="result-title")
                    if not title_div:
                        continue
                    a_tag = title_div.find("a")
                    if not a_tag:
                        continue
                        
                    title = a_tag.get_text().strip()
                    link = a_tag.get("href", "")
                    
                    desc_div = card.find(class_="result-intro")
                    content = desc_div.get_text().strip() if desc_div else ""
                    
                    src_span = card.find("span", class_="source")
                    author = src_span.get_text().strip() if src_span else "新浪网"
                    
                    time_span = card.find("span", class_="time")
                    created_at = time_span.get_text().strip() if time_span else ""
                    
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
                    print(f"解析 DOM 卡片出错: {e}")
                    
        browser.close()
        
    unique_arts = {}
    for art in articles:
        unique_arts[art["url"]] = art
        
    sorted_arts = sorted(unique_arts.values(), key=lambda x: x["created_at"], reverse=True)
    return sorted_arts

if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    for kw, filename in [("蜜雪冰城", "data/mixue_news.json"), ("茶百道", "data/chabaidao_news.json")]:
        results = crawl_sina(kw)
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"成功保存 {len(results)} 条数据到 {filename}")
        time.sleep(10)
