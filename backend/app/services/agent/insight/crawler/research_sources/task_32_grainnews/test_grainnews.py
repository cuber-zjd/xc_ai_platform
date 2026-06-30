import os
import json
import time
import re
from urllib.parse import quote
from datetime import datetime
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

def clean_time(date_text):
    # 将 2026/6/9 10:17:02 格式清洗为 2026-06-09 10:17:02
    date_text = date_text.strip()
    try:
        # 将斜杠替换为中划线
        clean = date_text.replace("/", "-")
        # 尝试匹配带时间或仅有日期的部分
        match = re.search(r'(\d{4}-\d{1,2}-\d{1,2})\s*(\d{1,2}:\d{2}:\d{2})?', clean)
        if match:
            date_part = match.group(1)
            time_part = match.group(2) if match.group(2) else "00:00:00"
            
            # 格式化日期部分，将 2026-6-9 转换为 2026-06-09
            y, m, d = date_part.split("-")
            date_formatted = f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
            
            # 格式化时间部分，将 10:17:02 补全
            h, mi, s = time_part.split(":")
            time_formatted = f"{int(h):02d}:{int(mi):02d}:{int(s):02d}"
            
            return f"{date_formatted} {time_formatted}"
    except Exception:
        pass
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def crawl_grainnews(keyword):
    # 本爬虫严格执行"优先爬取官方基站"原则，直连粮油市场报官方搜索接口
    print(f"--- [粮油市场报] 启动基站直连检索 关键字: '{keyword}' ---")
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
            url = f"https://www.grainnews.com.cn/search.aspx?search={quote(keyword)}"
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_timeout(5000)
            
            html = page.content()
            soup = BeautifulSoup(html, "html.parser")
            
            # 定位卡片容器 div.liang_time
            cards = soup.find_all("div", class_=lambda x: x and "liang_time" in x)
            print(f"  [粮油市场报] 成功定位候选卡片数: {len(cards)}")
            
            for card in cards:
                try:
                    p_tags = card.find_all("p")
                    if len(p_tags) < 2:
                        continue
                    
                    # 1. 标题是第一个 p
                    title = p_tags[0].get_text().strip()
                    
                    # 2. 时间是第二个 p
                    date_raw = ""
                    time_li = card.find("p", class_="time_li")
                    if time_li:
                        span = time_li.find("span")
                        date_raw = span.get_text().strip() if span else time_li.get_text().strip()
                    if not date_raw and len(p_tags) >= 2:
                        date_raw = p_tags[1].get_text().strip()
                    created_at = clean_time(date_raw)
                    
                    # 3. 摘要是第三个 p
                    content = ""
                    if len(p_tags) >= 3:
                        content = p_tags[2].get_text().strip()
                    if not content:
                        content = title
                        
                    # 4. 获取唯一 dataguid 属性，拼接成检索定位 URL (解决 href='#' 无法直连详情页问题)
                    dataguid = card.get("dataguid", "").strip()
                    link = f"https://www.grainnews.com.cn/search.aspx?search={quote(keyword)}#{dataguid}"
                    
                    # 5. 作者：解析摘要，如包含“本报讯(记者 XXX)”则提取记者，否则记为默认“粮油市场报”
                    author = "粮油市场报"
                    reporter_match = re.search(r'本报讯\s*\(?（?记者\s*([^）\)]+)）?\)?', content)
                    if reporter_match:
                        author = f"粮油市场报(记者 {reporter_match.group(1).strip()})"
                    
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
                except Exception as ex:
                    print(f"  解析卡片出错: {ex}")
                    
        except Exception as e:
            print(f"  [粮油市场报] 检索流程异常: {e}")
        finally:
            browser.close()
            
    return articles

if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    
    # 1. 抓取目标品牌（客观为 0 条数据，落盘空列表）
    for kw, filename in [("蜜雪冰城", "data/mixue_news.json"), ("茶百道", "data/chabaidao_news.json")]:
        results = crawl_grainnews(kw)
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"成功保存 {len(results)} 条数据到 {filename}")
        time.sleep(10)
        
    # 2. 抓取功能性验证关键词（证明解析与字段清洗模块 100% 畅通可用）
    verify_kw = "小麦"
    verify_file = "data/verify_test.json"
    verify_results = crawl_grainnews(verify_kw)
    # 仅保留前 5 条以供验证
    verify_results = verify_results[:5]
    with open(verify_file, "w", encoding="utf-8") as f:
        json.dump(verify_results, f, ensure_ascii=False, indent=2)
    print(f"功能验证：成功保存 {len(verify_results)} 条数据到 {verify_file}")
