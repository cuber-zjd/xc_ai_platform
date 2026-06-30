import os
import json
import re
import time
from urllib.parse import quote
from datetime import datetime
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

def clean_zqrb_time(date_str):
    date_str = date_str.strip()
    try:
        match = re.search(r'(\d{4})年(\d{2})月(\d{2})日', date_str)
        if match:
            return f"{match.group(1)}-{match.group(2)}-{match.group(3)} 00:00:00"
    except Exception:
        pass
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def crawl_zqrb(keyword):
    print(f"--- [证券日报] 启动基站直连检索 关键字: '{keyword}' ---")
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
            # 证券日报官方站内搜索基站 URL
            url = f"http://search.zqrb.cn/search.php?src=all&q={quote(keyword)}&f=_all&s=newsdate_DESC"
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_timeout(5000)
            
            html = page.content()
            soup = BeautifulSoup(html, "html.parser")
            
            # 定位卡片容器
            cards = soup.find_all("dl", class_="result-list")
            print(f"  [证券日报] 成功定位候选卡片数: {len(cards)}")
            
            for card in cards:
                try:
                    dt = card.find("dt")
                    if not dt:
                        continue
                    a_tag = dt.find("a")
                    if not a_tag:
                        continue
                        
                    title_raw = a_tag.get_text().strip()
                    # 清洗标题首部可能带有的数字序号（如 "1 十亿元补贴..." 中的 "1 "）
                    title = re.sub(r'^\d+\s+', '', title_raw)
                    
                    href = a_tag.get("href", "")
                    link = href if href.startswith("http") else "http://www.zqrb.cn" + href
                    
                    dd = card.find("dd")
                    if not dd:
                        continue
                        
                    desc_el = dd.find("p", class_=None)
                    content = desc_el.get_text().strip() if desc_el else title
                    
                    info_el = dd.find("p", class_=lambda x: x and "field-info" in x)
                    
                    author = "证券日报"
                    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    
                    if info_el:
                        for span in info_el.find_all("span"):
                            text = span.get_text()
                            if "作者:" in text:
                                author = text.split("作者:")[1].strip()
                            elif "时间:" in text:
                                created_at = clean_zqrb_time(text.split("时间:")[1])
                                
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
            print(f"  检索流程异常: {e}")
        finally:
            browser.close()
            
    return articles

if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    for kw, filename in [("蜜雪冰城", "data/mixue_news.json"), ("茶百道", "data/chabaidao_news.json")]:
        results = crawl_zqrb(kw)
        
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
