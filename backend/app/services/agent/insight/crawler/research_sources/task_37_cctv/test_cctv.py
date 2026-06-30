import os
import json
import time
import urllib.request
import re
from urllib.parse import quote
from datetime import datetime
from bs4 import BeautifulSoup

def clean_html(text):
    if not text:
        return ""
    try:
        # 清除用于搜索红字高亮的 font 标签及残留
        soup = BeautifulSoup(text, "html.parser")
        return soup.get_text().strip()
    except Exception:
        return re.sub(r'<[^>]+>', '', text).strip()

def crawl_cctv(keyword):
    # 本爬虫严格贯彻"优先爬取官方基站"原则，通过直连 SSR 搜索获取完整的页面卡片
    print(f"--- [央视网] 启动基站直连检索 关键字: '{keyword}' ---")
    articles = []
    
    url = f"https://search.cctv.com/search.php?qtext={quote(keyword)}&type=web"
    
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
        with urllib.request.urlopen(req, timeout=15) as r:
            html = r.read().decode("utf-8")
            soup = BeautifulSoup(html, "html.parser")
            
            outer = soup.find("div", class_="outer")
            if not outer:
                print("  [央视网] 未能定位到 div.outer，可能无搜索结果")
                return articles
                
            lis = outer.find_all("li")
            print(f"  [央视网] 成功获取卡片条数: {len(lis)}")
            
            for li in lis:
                try:
                    # 1. 提取标题
                    tit_tag = li.find("h3", class_="tit")
                    if not tit_tag:
                        continue
                    title = clean_html(tit_tag.get_text())
                    
                    # 2. 提取最纯净的超链接
                    span_span = li.find("span", lanmu1=True)
                    if not span_span:
                        continue
                    link = span_span.get("lanmu1", "").strip()
                    if not link:
                        continue
                        
                    # 3. 提取时间
                    tim_tag = li.find("span", class_="tim")
                    created_at = ""
                    if tim_tag:
                        created_at = tim_tag.get_text().replace("发布时间：", "").strip()
                    if not created_at:
                        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        
                    # 4. 提取作者/分类
                    src_tag = li.find("span", class_="src")
                    author = "央视新闻"
                    if src_tag:
                        raw_src = src_tag.get_text().replace("来源：", "").strip()
                        if raw_src:
                            author = f"央视网-{raw_src}"
                            
                    # 5. 提取描述/摘要
                    bre_tag = li.find("p", class_="bre")
                    content = ""
                    if bre_tag:
                        # 除去图片等子标签
                        for img in bre_tag.find_all("img"):
                            img.decompose()
                        content = clean_html(bre_tag.get_text())
                    if not content:
                        content = title
                        
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
                except Exception as card_ex:
                    print(f"  解析央视网卡片出错: {card_ex}")
                    
    except Exception as e:
        print(f"  [央视网] 检索流程异常: {e}")
        
    return articles

if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    for kw, filename in [("蜜雪冰城", "data/mixue_news.json"), ("茶百道", "data/chabaidao_news.json")]:
        results = crawl_cctv(kw)
        
        # 去重
        unique_arts = {}
        for art in results:
            unique_arts[art["url"]] = art
            
        # 排序
        sorted_arts = sorted(unique_arts.values(), key=lambda x: x["created_at"], reverse=True)
        
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(sorted_arts, f, ensure_ascii=False, indent=2)
        print(f"成功保存 {len(sorted_arts)} 条数据到 {filename}")
        time.sleep(5)
