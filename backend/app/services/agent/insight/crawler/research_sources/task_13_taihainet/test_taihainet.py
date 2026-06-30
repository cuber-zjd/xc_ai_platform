import os
import json
import re
import time
from urllib.parse import urlparse, parse_qs, unquote
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

def decode_jump_url(jump_url):
    try:
        if "/search/jump" in jump_url:
            parsed = urlparse(jump_url)
            qs = parse_qs(parsed.query)
            real = qs.get("url", [jump_url])[0]
            return unquote(real)
    except Exception:
        pass
    return jump_url

def parse_relative_time(time_str):
    now = datetime.now()
    time_str = time_str.strip()
    try:
        if "分钟前" in time_str:
            mins = int(re.search(r'\d+', time_str).group())
            dt = now - timedelta(minutes=mins)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        elif "小时前" in time_str:
            hours = int(re.search(r'\d+', time_str).group())
            dt = now - timedelta(hours=hours)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        elif "昨天" in time_str:
            dt = now - timedelta(days=1)
            return dt.strftime("%Y-%m-%d 00:00:00")
        elif "天前" in time_str:
            days = int(re.search(r'\d+', time_str).group())
            dt = now - timedelta(days=days)
            return dt.strftime("%Y-%m-%d 00:00:00")
        else:
            match = re.search(r'(\d{1,2})\s*月\s*(\d{1,2})\s*日', time_str)
            if match:
                return f"{now.year}-{int(match.group(1)):02d}-{int(match.group(2)):02d} 00:00:00"
            match_full = re.search(r'(\d{4})[-.年](\d{1,2})[-.月](\d{1,2})', time_str)
            if match_full:
                return f"{match_full.group(1)}-{int(match_full.group(2)):02d}-{int(match_full.group(3)):02d} 00:00:00"
    except Exception:
        pass
    return now.strftime("%Y-%m-%d %H:%M:%S")

def crawl_taihainet(keyword):
    # 采用今日头条资讯代理方案，精确检索“台海网”关于新茶饮的原创报道
    search_kw = f"台海网 {keyword}"
    print(f"开始利用头条平台间接爬取台海网 - 检索词: '{search_kw}'")
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
        
        url = f"https://so.toutiao.com/search/?dvpf=pc&pd=information&keyword={search_kw}"
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_timeout(6000)
        
        html = page.content()
        soup = BeautifulSoup(html, "html.parser")
        
        cards = soup.find_all(class_=re.compile(r"cs-card-content"))
        print(f"  [台海网] 找到候选卡片数: {len(cards)}")
        
        for card in cards:
            try:
                a_tag = card.find("a")
                if not a_tag:
                    continue
                    
                title = a_tag.get_text().strip()
                jump_url = a_tag.get("href", "")
                
                if "/search?keyword=" in jump_url or len(jump_url) < 15 or "温馨提示" in title:
                    continue
                    
                real_url = decode_jump_url(jump_url)
                
                source_el = card.find(class_=re.compile(r"cs-source"))
                source_text = source_el.get_text().strip() if source_el else ""
                
                parts = source_text.split("\n")
                author = parts[0].strip() if len(parts) > 0 and parts[0].strip() else "台海网"
                
                # 核心校验：来源必须包含台海网，以排除杂音
                if "台海网" not in author:
                    continue
                    
                time_raw = ""
                for p_val in reversed(parts):
                    p_val = p_val.strip()
                    if "评论" not in p_val and p_val != author:
                        time_raw = p_val
                        break
                        
                created_at = parse_relative_time(time_raw)
                
                desc_el = card.find(class_=re.compile(r"cs-text"))
                content = desc_el.get_text().strip() if desc_el else ""
                
                articles.append({
                    "title": title,
                    "author": "台海网",
                    "created_at": created_at,
                    "content": content,
                    "url": real_url,
                    "likes": 0,
                    "comments": 0,
                    "retweets": 0
                })
            except Exception as e:
                print(f"解析卡片出错: {e}")
                
        browser.close()
        
    return articles

if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    for kw, filename in [("蜜雪冰城", "data/mixue_news.json"), ("茶百道", "data/chabaidao_news.json")]:
        results = crawl_taihainet(kw)
        
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
