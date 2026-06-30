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
            data = json.loads(clean_text)
            items_list = data.get("list", [])
            for item in items_list:
                title = item.get("title") or ""
                text = item.get("text") or ""
                description = item.get("description") or ""
                created_at = item.get("created_at")
                user = item.get("user", {})
                author = user.get("screen_name") or "匿名"
                target_id = item.get("id")
                source_url = f"https://xueqiu.com/{user.get('id', '')}/{target_id}" if target_id and user.get('id') else ""
                
                # 清理 HTML 标签
                clean_title = re.sub(r'<[^>]+>', '', title).strip()
                clean_content = re.sub(r'<[^>]+>', '', text or description).strip()
                
                time_str = ""
                if created_at:
                    try:
                        time_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(created_at / 1000))
                    except Exception:
                        pass
                
                parsed_items.append({
                    "title": clean_title,
                    "author": author,
                    "created_at": time_str,
                    "content": clean_content,
                    "url": source_url,
                    "likes": item.get("like_count", 0),
                    "comments": item.get("comment_count", 0),
                    "retweets": item.get("retweet_count", 0)
                })
        except Exception as e:
            print(f"解析单个数据包失败: {e}")
            
    # 去重
    unique_items = []
    seen_urls = set()
    for pi in parsed_items:
        if pi["url"] not in seen_urls:
            seen_urls.add(pi["url"])
            unique_items.append(pi)
            
    # 按时间降序排序
    unique_items.sort(key=lambda x: x["created_at"], reverse=True)
    
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
        
        # 绑定监听
        def log_response(res):
            url = res.url
            if "query/v1/search/status.json" in url or "query/v1/symbol/search/status.json" in url:
                if res.status == 200:
                    try:
                        text_content = res.text()
                        clean_text = text_content.strip()
                        if clean_text.startswith("{"):
                            data = json.loads(clean_text)
                            if "list" in data and len(data["list"]) > 0:
                                parsed_url = urlparse(url)
                                params = parse_qs(parsed_url.query)
                                q_list = params.get("q", [])
                                if q_list:
                                    keyword = unquote(q_list[0])
                                    if "蜜雪冰城" in keyword:
                                        print(f"  [发现蜜雪冰城数据包] 长度: {len(data['list'])}")
                                        mixue_raw_data.append(clean_text)
                                    elif "茶百道" in keyword:
                                        print(f"  [发现茶百道数据包] 长度: {len(data['list'])}")
                                        chabaidao_raw_data.append(clean_text)
                    except Exception:
                        pass

        page.on("response", log_response)
        
        try:
            print("--- 步骤 1: 访问首页以建立 Session ---")
            page.goto("https://xueqiu.com/", wait_until="domcontentloaded")
            page.wait_for_timeout(4000)
            
            # --- 抓取蜜雪冰城 ---
            print("\n--- 步骤 2: 访问搜索页: 蜜雪冰城 ---")
            mixue_url = "https://xueqiu.com/k?q=%E8%9C%9C%E9%9B%AA%E5%86%B0%E5%9F%8E"
            page.goto(mixue_url, wait_until="domcontentloaded")
            page.wait_for_timeout(6000)
            
            # 自动多次 reload 校验重试（最多3次），一旦抓到数据立即提前退出 reload 循环
            for attempt in range(1, 4):
                if len(mixue_raw_data) > 0:
                    break
                print(f"【重试 #{attempt}】刷新页面以套用 WAF Cookie 凭证...")
                page.reload(wait_until="domcontentloaded")
                page.wait_for_timeout(6000)
                
            print("模拟页面滚动以加载更多资讯...")
            for i in range(3):
                page.evaluate("window.scrollBy(0, 500)")
                page.wait_for_timeout(2500)
                
            # --- 冷却一下 ---
            print("\n冷静 5 秒后再开始下一个词...")
            page.wait_for_timeout(5000)
            
            # --- 抓取茶百道 ---
            print("\n--- 步骤 3: 访问搜索页: 茶百道 ---")
            chabaidao_url = "https://xueqiu.com/k?q=%E8%8C%B6%E7%99%BE%E9%81%93"
            page.goto(chabaidao_url, wait_until="domcontentloaded")
            page.wait_for_timeout(6000)
            
            # 同样使用自动 reload 重试机制
            for attempt in range(1, 4):
                if len(chabaidao_raw_data) > 0:
                    break
                print(f"【重试 #{attempt}】刷新页面以套用 WAF Cookie 凭证...")
                page.reload(wait_until="domcontentloaded")
                page.wait_for_timeout(6000)
            
            print("模拟页面滚动以加载更多资讯...")
            for i in range(3):
                page.evaluate("window.scrollBy(0, 500)")
                page.wait_for_timeout(2500)
                
        except Exception as e:
            print(f"抓取流程异常: {e}")
        finally:
            browser.close()
            
    # 解析并保存
    print("\n--- 步骤 4: 保存数据 ---")
    parse_and_save_data(mixue_raw_data, "蜜雪冰城", "mixue_news.json")
    parse_and_save_data(chabaidao_raw_data, "茶百道", "chabaidao_news.json")

if __name__ == "__main__":
    run_crawler()
