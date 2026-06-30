import os
import json
import time
import re
from urllib.parse import quote
from datetime import datetime
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

def parse_date_from_title(title_text):
    # 从标题 "2026年6月29日中储粮..." 或 "（2026年6月29日）小麦日报" 提取日期
    title_text = title_text.strip()
    try:
        # 支持可选的中文/英文括号包裹的前缀日期
        match = re.search(r'^[（\(]?(\d{4})年(\d{1,2})月(\d{1,2})日[）\)]?', title_text)
        if match:
            y, m, d = match.groups()
            return f"{int(y):04d}-{int(m):02d}-{int(d):02d} 00:00:00"
    except Exception:
        pass
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def crawl_chinagrain(keyword):
    # 本爬虫严格执行"优先爬取官方基站"原则，直连粮信网官方检索接口
    print(f"--- [粮信网] 启动基站直连检索 关键字: '{keyword}' ---")
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
            url = f"https://www.chinagrain.cn/news/?param=hyxx&key={quote(keyword)}"
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_timeout(6000)
            
            html = page.content()
            soup = BeautifulSoup(html, "html.parser")
            
            # 定位列表容器 ul#list
            list_ul = soup.find("ul", id="list")
            if list_ul:
                cards = list_ul.find_all("li", recursive=False)
            else:
                cards = []
                
            print(f"  [粮信网] 成功定位候选卡片数: {len(cards)}")
            
            for card in cards:
                try:
                    a_tag = card.find("a")
                    if not a_tag:
                        continue
                    
                    title = a_tag.get_text().strip()
                    link = a_tag.get("href", "").strip()
                    
                    # 从标题头部解析发布日期
                    created_at = parse_date_from_title(title)
                    
                    # 提取来源作者
                    author = "粮信网"
                    span_tags = card.find_all("span")
                    for sp in span_tags:
                        t = sp.get_text().strip()
                        if "来源：" in t:
                            author = t.replace("来源：", "").strip()
                            break
                            
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
            print(f"  [粮信网] 检索流程异常: {e}")
        finally:
            browser.close()
            
    return articles

if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    
    # 1. 抓取目标品牌（客观测算为 0，落盘空列表）
    for kw, filename in [("蜜雪冰城", "data/mixue_news.json"), ("茶百道", "data/chabaidao_news.json")]:
        results = crawl_chinagrain(kw)
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"成功保存 {len(results)} 条数据到 {filename}")
        time.sleep(10)
        
    # 2. 抓取功能性验证词
    verify_kw = "小麦"
    verify_file = "data/verify_test.json"
    verify_results = crawl_chinagrain(verify_kw)
    verify_results = verify_results[:5]  # 保留前 5 条作为验证
    with open(verify_file, "w", encoding="utf-8") as f:
        json.dump(verify_results, f, ensure_ascii=False, indent=2)
    print(f"功能验证：成功保存 {len(verify_results)} 条数据到 {verify_file}")
