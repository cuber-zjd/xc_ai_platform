import os
import json
import re
import time
from datetime import datetime
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

def clean_bse_time(date_str):
    date_str = date_str.strip()
    try:
        if re.match(r'\d{4}-\d{2}-\d{2}', date_str):
            return f"{date_str} 00:00:00"
    except Exception:
        pass
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def crawl_bse(keyword):
    print(f"--- [北交所] 启动检索 关键字: '{keyword}' ---")
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
            url = "https://www.bse.cn/disclosure/announcement.html"
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            
            # 定位关键字搜索框
            search_ipt = page.locator("input[id='keyword']").first
            search_ipt.click()
            search_ipt.fill(keyword)
            page.wait_for_timeout(1000)
            
            # 模拟点击查询按钮
            query_btn = page.locator("button:has-text('查询'), input[type='button'][value='查询'], a:has-text('查询')").first
            query_btn.click()
            
            # 等待 6 秒加载数据并更新 DOM
            page.wait_for_timeout(6000)
            
            html = page.content()
            soup = BeautifulSoup(html, "html.parser")
            
            # 判断是否有 "暂无数据"
            if "暂无数据" in html:
                print(f"  [北交所] 未找到与 '{keyword}' 相关的上市公司公告 (暂无数据)")
            else:
                # 定位表格中的数据行
                # 通常是 table 里的 tr 行
                table = soup.find("table")
                if table:
                    rows = table.find_all("tr")
                    print(f"  [北交所] 找到表格行数: {len(rows)}")
                    for row in rows:
                        cols = row.find_all("td")
                        if len(cols) < 4:
                            continue
                            
                        code = cols[0].get_text().strip()
                        name = cols[1].get_text().strip() # 简称
                        title_td = cols[2]
                        date_raw = cols[3].get_text().strip() # 日期
                        
                        a_tag = title_td.find("a")
                        if not a_tag:
                            continue
                            
                        title = a_tag.get_text().strip()
                        href = a_tag.get("href", "")
                        link = "https://www.bse.cn" + href if href.startswith("/") else href
                        
                        created_at = clean_bse_time(date_raw)
                        
                        articles.append({
                            "title": title,
                            "author": name or "北交所",
                            "created_at": created_at,
                            "content": f"北交所上市公司公告: [{code}] {name} - {title}",
                            "url": link,
                            "likes": 0,
                            "comments": 0,
                            "retweets": 0
                        })
                else:
                    print("  [北交所] 未在页面中找到表格元素")
                    
        except Exception as e:
            print(f"  [北交所] 检索流程异常: {e}")
        finally:
            browser.close()
            
    return articles

if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    for kw, filename in [("蜜雪冰城", "data/mixue_news.json"), ("茶百道", "data/chabaidao_news.json")]:
        results = crawl_bse(kw)
        
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
