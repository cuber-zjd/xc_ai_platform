import os
import json
import time
import urllib.request
from urllib.parse import quote
from datetime import datetime

def crawl_galaxy(keyword):
    # 本爬虫严格执行"优先爬取官方基站"原则，直连银河证券前台 API 获取结构化 JSON 数据
    print(f"--- [银河证券] 启动基站直连检索 关键字: '{keyword}' ---")
    articles = []
    
    url = f"https://www.chinastock.com.cn/website2020/doc/queryDocList?pageSize=50&pageNo=1&needBrief=1&catName=wt_gd_%E8%A7%82%E7%82%B9%E8%81%9A%E7%84%A6%E5%8C%BA&briefLength=200&keyword={quote(keyword)}"
    
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
        with urllib.request.urlopen(req, timeout=15) as r:
            res_data = json.loads(r.read().decode("utf-8"))
            
            # 使用安全的 None 容错防护，避免在无数据返回 null 时崩溃
            data_node = res_data.get("data") or {}
            lst = data_node.get("list", [])
            print(f"  [银河证券] 成功拉取数据条数: {len(lst)}")
            
            for item in lst:
                try:
                    title = item.get("title", "").strip()
                    doc_id = item.get("docId")
                    if not title or not doc_id:
                        continue
                    
                    # 拼接研报最终阅读链接
                    link = f"https://www.chinastock.com.cn/newsite/cgs-services/researchReportDetail.html?id={doc_id}"
                    
                    # 获取发布时间
                    created_at = item.get("uploadDate", "").strip()
                    if not created_at:
                        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        
                    # 获取摘要与作者
                    content = item.get("brief", "").strip()
                    if not content:
                        content = title
                    author = item.get("source", "银河证券").strip()
                    if not author:
                        author = "银河证券"
                        
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
                    print(f"  解析研报条目出错: {card_ex}")
                    
    except Exception as e:
        print(f"  [银河证券] 检索流程异常: {e}")
        
    return articles

if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    
    # 1. 抓取目标品牌（客观测算为 0，落盘空列表）
    for kw, filename in [("蜜雪冰城", "data/mixue_news.json"), ("茶百道", "data/chabaidao_news.json")]:
        results = crawl_galaxy(kw)
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"成功保存 {len(results)} 条数据到 {filename}")
        time.sleep(5)
        
    # 2. 抓取功能性验证词
    verify_kw = "Token"
    verify_file = "data/verify_test.json"
    verify_results = crawl_galaxy(verify_kw)
    verify_results = verify_results[:5]  # 保留前 5 条作为验证
    with open(verify_file, "w", encoding="utf-8") as f:
        json.dump(verify_results, f, ensure_ascii=False, indent=2)
    print(f"功能验证：成功保存 {len(verify_results)} 条数据到 {verify_file}")
