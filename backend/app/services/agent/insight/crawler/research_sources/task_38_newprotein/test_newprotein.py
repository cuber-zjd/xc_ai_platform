import os
import json
import time
import urllib.request
import re
from urllib.parse import quote
from datetime import datetime
from bs4 import BeautifulSoup

def clean_time(dt_str):
    # 解析 "2026-06-28T20:24:03+00:00" 为标准格式 YYYY-MM-DD HH:MM:SS
    if not dt_str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        # 去掉时区信息进行简化解析
        clean_str = re.sub(r'[\+\-]\d{2}:\d{2}$', '', dt_str)
        dt = datetime.fromisoformat(clean_str)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def crawl_newprotein(keyword, filter_title=True):
    # 坚持"优先爬取官方基站"原则，直连 WordPress 检索接口
    print(f"--- [新蛋白网] 启动基站直连检索 关键字: '{keyword}' ---")
    articles = []
    
    url = f"https://foodsustainability.cn/?s={quote(keyword)}"
    
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
        with urllib.request.urlopen(req, timeout=15) as r:
            html = r.read().decode("utf-8")
            soup = BeautifulSoup(html, "html.parser")
            
            posts = soup.find_all("article")
            print(f"  [新蛋白网] 检索页面卡片总数: {len(posts)}")
            
            for art in posts:
                try:
                    # 1. 提取标题
                    tit_tag = art.find("h6", class_="post-title")
                    if not tit_tag:
                        continue
                    tit_a = tit_tag.find("a")
                    if not tit_a:
                        continue
                    title = tit_a.get_text().strip()
                    if not title:
                        continue
                    
                    # 2. 判定防误配降噪
                    if filter_title and keyword.lower() not in title.lower():
                        # 不含关键词的退化推荐文章，直接过滤
                        continue
                    
                    # 3. 提取超链接
                    link = tit_a.get("href", "").strip()
                    if not link:
                        continue
                        
                    # 4. 提取隐藏的绝对日期时间
                    time_tag = art.find("time", class_="entry-date")
                    raw_dt = time_tag.get("datetime") if time_tag else ""
                    created_at = clean_time(raw_dt)
                    
                    # 5. 提取主笔作者
                    fn_tag = art.find("span", class_="fn")
                    author = fn_tag.get_text().strip() if fn_tag else "新蛋白网"
                    if not author:
                        author = "新蛋白网"
                        
                    articles.append({
                        "title": title,
                        "author": author,
                        "created_at": created_at,
                        "content": title,  # 列表不提供描述，缺省为标题
                        "url": link,
                        "likes": 0,
                        "comments": 0,
                        "retweets": 0
                    })
                except Exception as card_ex:
                    print(f"  解析卡片出错: {card_ex}")
                    
    except Exception as e:
        print(f"  [新蛋白网] 检索流程异常: {e}")
        
    return articles

if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    
    # 1. 目标品牌抓取
    for kw, filename in [("蜜雪冰城", "data/mixue_news.json"), ("茶百道", "data/chabaidao_news.json")]:
        results = crawl_newprotein(kw, filter_title=True)
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"成功保存 {len(results)} 条数据到 {filename}")
        time.sleep(5)
        
    # 2. 通用词结构验证
    verify_results = crawl_newprotein("植物奶", filter_title=True)
    verify_results = verify_results[:5]  # 保留前 5 条作为结构性测试验证
    verify_file = "data/verify_test.json"
    with open(verify_file, "w", encoding="utf-8") as f:
        json.dump(verify_results, f, ensure_ascii=False, indent=2)
    print(f"功能验证：成功保存 {len(verify_results)} 条数据到 {verify_file}")
