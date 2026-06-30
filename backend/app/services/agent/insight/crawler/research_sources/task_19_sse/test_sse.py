import os
import json
import re
import time
from datetime import datetime
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

def clean_sse_time(date_str):
    date_str = date_str.strip()
    try:
        if re.match(r'\d{4}-\d{2}-\d{2}', date_str):
            return f"{date_str} 00:00:00"
    except Exception:
        pass
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def crawl_sse(keyword):
    # 本爬虫严格执行“优先爬取官方基站”原则，直接连接上交所信批专区进行检索
    print(f"--- [上交所] 启动基站直连检索 关键字: '{keyword}' ---")
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
            # 使用经过实机拨测修正的上市公司公告披露真实基站 URL
            url = "https://www.sse.com.cn/disclosure/listedinfo/announcement/"
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            
            # 定位“标题 / 关键字”检索输入框
            search_ipt = page.locator("input[placeholder*='标题'], input[placeholder*='关键字']").first
            search_ipt.click()
            search_ipt.fill(keyword)
            page.wait_for_timeout(1000)
            
            # 回车提交检索并等待 6 秒加载
            search_ipt.press("Enter")
            page.wait_for_timeout(6000)
            
            html = page.content()
            soup = BeautifulSoup(html, "html.parser")
            
            # 解析表格数据
            table = soup.find("table")
            if table:
                rows = table.find_all("tr")
                valid_count = 0
                for row in rows:
                    cols = row.find_all("td")
                    if len(cols) < 4:
                        continue
                        
                    code = cols[0].get_text().strip()
                    # 强校验：首列必须是严格的 6 位数字代码
                    if not re.match(r'^\d{6}$', code):
                        continue
                        
                    valid_count += 1
                    name = cols[1].get_text().strip() # 简称
                    title_td = cols[2]
                    date_raw = cols[3].get_text().strip() # 日期
                    
                    a_tag = title_td.find("a")
                    if not a_tag:
                        continue
                        
                    title = a_tag.get_text().strip()
                    href = a_tag.get("href", "")
                    link = "https://www.sse.com.cn" + href if href.startswith("/") else href
                    
                    created_at = clean_sse_time(date_raw)
                    
                    articles.append({
                        "title": title,
                        "author": name or "上交所",
                        "created_at": created_at,
                        "content": f"上交所上市公司公告: [{code}] {name} - {title}",
                        "url": link,
                        "likes": 0,
                        "comments": 0,
                        "retweets": 0
                    })
                print(f"  [上交所] 成功解析有效公告数据行: {valid_count}")
            else:
                # 兼容可能输出的“公告数：0条”空状态
                print("  [上交所] 未找到任何匹配数据，表格为空")
                
        except Exception as e:
            print(f"  [上交所] 检索流程异常: {e}")
        finally:
            browser.close()
            
    return articles

if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    for kw, filename in [("蜜雪冰城", "data/mixue_news.json"), ("茶百道", "data/chabaidao_news.json")]:
        results = crawl_sse(kw)
        
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
