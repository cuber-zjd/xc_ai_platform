import os
import json
import re
import time
from datetime import datetime
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

def resolve_real_url(context, jump_url):
    # 在后台快速重定向获取真实 news 落地超链接
    if not jump_url.startswith("http"):
        jump_url = "https://www.sogou.com" + jump_url
        
    page = context.new_page()
    real_url = jump_url
    try:
        # 使用 domcontentloaded 并等待 3 秒以执行搜狗页面内的 JS/meta 重定向跳转
        page.goto(jump_url, wait_until="domcontentloaded", timeout=12000)
        page.wait_for_timeout(3000)
        real_url = page.url
    except Exception:
        pass
    finally:
        page.close()
    return real_url

def crawl_tencent(keyword):
    print(f"--- [腾讯网] 启动检索 关键字: '{keyword}' ---")
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
            # 搜狗检索 site:new.qq.com
            url = f"https://www.sogou.com/web?query=site:new.qq.com%20{keyword}"
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_timeout(4000)
            
            html = page.content()
            soup = BeautifulSoup(html, "html.parser")
            
            cards = soup.find_all(class_=["vrwrap", "rb"])
            print(f"  [腾讯网] 搜狗检索到候选卡片数: {len(cards)}")
            
            for card in cards:
                try:
                    a_tag = card.find("a")
                    if not a_tag:
                        continue
                    title = a_tag.get_text().strip()
                    jump_url = a_tag.get("href", "")
                    
                    # 过滤多余的非腾讯新闻的站长平台等
                    if "zhanzhang" in title or "站长" in title or not jump_url:
                        continue
                        
                    # 在后台请求跳转链接，还原真实的 new.qq.com 超链接
                    real_url = resolve_real_url(context, jump_url)
                    if "qq.com" not in real_url:
                        continue
                        
                    # 摘要
                    desc_div = card.find(class_=re.compile(r"desc|summary|abstract|vr-wrap"))
                    content = desc_div.get_text().strip() if desc_div else ""
                    
                    # 时间 (默认为当前时间)
                    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    # 从页面文字中匹配类似 2026-06-25 或 2小时前 等，通常由搜狗展示在底部或摘要前段
                    date_match = re.search(r'(\d{4})[-.年](\d{1,2})[-.月](\d{1,2})', content)
                    if date_match:
                        created_at = f"{date_match.group(1)}-{int(date_match.group(2)):02d}-{int(date_match.group(3)):02d} 00:00:00"
                    
                    articles.append({
                        "title": title,
                        "author": "腾讯新闻",
                        "created_at": created_at,
                        "content": content,
                        "url": real_url,
                        "likes": 0,
                        "comments": 0,
                        "retweets": 0
                    })
                except Exception as ex:
                    print(f"  [腾讯网] 解析单条卡片出错: {ex}")
                    
        except Exception as e:
            print(f"  [腾讯网] 检索流程异常: {e}")
        finally:
            browser.close()
            
    return articles

if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    for kw, filename in [("蜜雪冰城", "data/mixue_news.json"), ("茶百道", "data/chabaidao_news.json")]:
        results = crawl_tencent(kw)
        
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
