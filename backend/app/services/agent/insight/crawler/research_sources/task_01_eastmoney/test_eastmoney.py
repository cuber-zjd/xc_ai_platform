import os
import json
import time
import re
from urllib.parse import quote, urlparse, parse_qs, unquote
from playwright.sync_api import sync_playwright

# 确保数据保存目录存在
os.makedirs("data", exist_ok=True)

def parse_and_save_data(results_list, keyword, filename):
    parsed_items = []
    
    for clean_text in results_list:
        try:
            # 剥离 JSONP 外壳 jQueryxxxx(...)
            start_idx = clean_text.find("(")
            end_idx = clean_text.rfind(")")
            if start_idx != -1 and end_idx != -1:
                json_str = clean_text[start_idx + 1:end_idx]
                data = json.loads(json_str)
                
                # 万能提取 result 下的所有列表字段
                result_data = data.get("result", {})
                if not result_data:
                    continue
                    
                for key, val_list in result_data.items():
                    if isinstance(val_list, list):
                        for item in val_list:
                            # 提取常见字段（东财多源字段适配）
                            title = item.get("title") or item.get("Title") or ""
                            content = item.get("content") or item.get("Content") or item.get("description") or ""
                            created_at = item.get("date") or item.get("showTime") or item.get("ShowTime") or ""
                            author = item.get("sourceName") or item.get("NickName") or item.get("author") or "东方财富网"
                            target_url = item.get("url") or item.get("Url") or ""
                            
                            # 过滤空数据
                            if not title or not target_url:
                                continue
                                
                            # 清理 HTML 标签
                            clean_title = re.sub(r'<[^>]+>', '', title).strip()
                            clean_content = re.sub(r'<[^>]+>', '', content).strip()
                            
                            # 规范化日期格式
                            time_str = created_at.strip()
                            # 有时东财返回毫秒戳，转换之
                            if time_str.isdigit() or (isinstance(created_at, int)):
                                try:
                                    time_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(int(created_at) / 1000))
                                except Exception:
                                    pass
                            
                            parsed_items.append({
                                "title": clean_title,
                                "author": author,
                                "created_at": time_str,
                                "content": clean_content,
                                "url": target_url,
                                "likes": item.get("like_count") or item.get("LikeCount") or 0,
                                "comments": item.get("comment_count") or item.get("CommentCount") or 0,
                                "retweets": 0
                            })
        except Exception as e:
            print(f"  [解析错误] 处理数据包失败: {e}")
            
    # 去重
    unique_items = []
    seen_urls = set()
    for pi in parsed_items:
        if pi["url"] not in seen_urls:
            seen_urls.add(pi["url"])
            unique_items.append(pi)
            
    # 按时间降序排序
    # 先处理可能没有时间格式的
    def get_sort_key(x):
        return x["created_at"] if x["created_at"] else "1970-01-01 00:00:00"
    unique_items.sort(key=get_sort_key, reverse=True)
    
    filepath = os.path.join("data", filename)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(unique_items, f, ensure_ascii=False, indent=2)
        
    print(f"【保存成功】关键词: '{keyword}'，保存到: {filepath}，条数: {len(unique_items)}")

def run_crawler():
    mixue_raw_data = []
    chabaidao_raw_data = []
    
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
        
        # 绑定监听并分类注入
        def log_response(res):
            url = res.url
            if "search-api-web.eastmoney.com/search/jsonp" in url:
                if res.status == 200:
                    try:
                        text_content = res.text()
                        clean_text = text_content.strip()
                        # 查找属于哪个词
                        parsed_url = urlparse(url)
                        params = parse_qs(parsed_url.query)
                        # 东财的 query 在 param 这个 json 中，我们需要解析 param 参数
                        param_json_str = params.get("param", [])[0]
                        param_data = json.loads(param_json_str)
                        keyword = param_data.get("keyword", "")
                        
                        if "蜜雪冰城" in keyword:
                            print(f"  [拦截接口] 成功截获蜜雪冰城搜索包")
                            mixue_raw_data.append(clean_text)
                        elif "茶百道" in keyword:
                            print(f"  [拦截接口] 成功截获茶百道搜索包")
                            chabaidao_raw_data.append(clean_text)
                    except Exception as e:
                        pass

        page.on("response", log_response)
        
        try:
            # --- 抓取蜜雪冰城 ---
            print("\n--- 步骤 1: 访问搜索页: 蜜雪冰城 ---")
            mixue_url = f"https://so.eastmoney.com/Web/s?keyword={quote('蜜雪冰城')}"
            page.goto(mixue_url, wait_until="domcontentloaded")
            page.wait_for_timeout(8000)
            
            print("模拟页面滚动以触发布局加载...")
            for i in range(2):
                page.evaluate("window.scrollBy(0, 500)")
                page.wait_for_timeout(2000)
                
            # --- 冷静一下 ---
            print("\n冷静 5 秒后再开始下一个词...")
            page.wait_for_timeout(5000)
            
            # --- 抓取茶百道 ---
            print("\n--- 步骤 2: 访问搜索页: 茶百道 ---")
            chabaidao_url = f"https://so.eastmoney.com/Web/s?keyword={quote('茶百道')}"
            page.goto(chabaidao_url, wait_until="domcontentloaded")
            page.wait_for_timeout(8000)
            
            print("模拟页面滚动以触发布局加载...")
            for i in range(2):
                page.evaluate("window.scrollBy(0, 500)")
                page.wait_for_timeout(2000)
                
        except Exception as e:
            print(f"抓取流程异常: {e}")
        finally:
            browser.close()
            
    # 解析并保存
    print("\n--- 步骤 3: 保存数据 ---")
    parse_and_save_data(mixue_raw_data, "蜜雪冰城", "mixue_news.json")
    parse_and_save_data(chabaidao_raw_data, "茶百道", "chabaidao_news.json")

if __name__ == "__main__":
    run_crawler()
