import os
import json
import time
import urllib.request
import re
from urllib.parse import quote
from datetime import datetime
from bs4 import BeautifulSoup

def clean_html(text):
    # 洗掉标题或描述中可能存在的 HTML 高亮标签（如 <span style='color:red'>蜜</span>）
    if not text:
        return ""
    try:
        soup = BeautifulSoup(text, "html.parser")
        return soup.get_text().strip()
    except Exception:
        # 退化正则过滤
        return re.sub(r'<[^>]+>', '', text).strip()

def format_timestamp(ts):
    # 将 13 位毫秒级时间戳转换为 YYYY-MM-DD HH:MM:SS
    try:
        dt = datetime.fromtimestamp(int(ts) / 1000.0)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def crawl_cnfood(keyword):
    # 本爬虫通过直连官方逆向所得的 API，实现极速拉取数据并绕过前台人机盾
    print(f"--- [中国食品报] 启动基站直连检索 关键字: '{keyword}' ---")
    articles = []
    
    url = f"http://www.cnfood.cn/api/blade-desk/pass/article/search?current=1&size=20&keyword={quote(keyword)}&time="
    
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
        with urllib.request.urlopen(req, timeout=15) as r:
            res_data = json.loads(r.read().decode("utf-8"))
            data_node = res_data.get("data") or {}
            records = data_node.get("records", [])
            print(f"  [中国食品报] 成功拉取数据条数: {len(records)}")
            
            for item in records:
                try:
                    raw_title = item.get("title", "")
                    doc_id = item.get("id")
                    if not raw_title or not doc_id:
                        continue
                    
                    # 1. 纯净标题
                    title = clean_html(raw_title)
                    
                    # 2. 拼接详情链接
                    link = f"http://www.cnfood.cn/article?id={doc_id}"
                    
                    # 3. 转换发布时间
                    create_time = item.get("createTime")
                    created_at = format_timestamp(create_time)
                    
                    # 4. 纯净摘要
                    raw_desc = item.get("description", "")
                    content = clean_html(raw_desc)
                    if not content:
                        content = title
                        
                    articles.append({
                        "title": title,
                        "author": "中国食品报",
                        "created_at": created_at,
                        "content": content,
                        "url": link,
                        "likes": 0,
                        "comments": 0,
                        "retweets": 0
                    })
                except Exception as card_ex:
                    print(f"  解析新闻条目出错: {card_ex}")
                    
    except Exception as e:
        print(f"  [中国食品报] 检索流程异常: {e}")
        
    return articles

if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    for kw, filename in [("蜜雪冰城", "data/mixue_news.json"), ("茶百道", "data/chabaidao_news.json")]:
        results = crawl_cnfood(kw)
        
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
