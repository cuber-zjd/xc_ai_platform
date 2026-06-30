import os
import json
import time
import re
from datetime import datetime
from playwright.sync_api import sync_playwright

# 确保目标数据保存目录存在
os.makedirs("data", exist_ok=True)

def parse_and_save_data(raw_json_str, keyword, filename):
    try:
        data_obj = json.loads(raw_json_str)
        if data_obj.get("status_code") != 0:
            print(f"  [警告] 接口返回状态码异常: {data_obj.get('status_code')}")
            return False
        
        raw_list = data_obj.get("data", {}).get("data", [])
        if not raw_list:
            print(f"  [警告] 接口未返回任何新闻数据")
            return False

        parsed_items = []
        for item in raw_list:
            title = item.get("title") or ""
            # 清理标题中的 HTML 标签
            clean_title = re.sub(r'<[^>]+>', '', title).strip()
            if not clean_title:
                continue

            # 提取作者/来源
            author = item.get("source") or item.get("author") or "同花顺"
            
            # 转换时间戳 (time 字段为十位秒级时间戳字符串)
            time_val = item.get("time")
            created_at = ""
            if time_val:
                try:
                    ts = int(time_val)
                    created_at = datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
                except Exception:
                    created_at = item.get("date", "") + " 00:00:00"
            else:
                created_at = item.get("date", "") + " 00:00:00"

            # 优先使用 PC 链接，如果为空则使用移动端或客户端链接
            target_url = item.get("pc_url") or item.get("mobile_url") or item.get("client_url") or ""

            parsed_items.append({
                "title": clean_title,
                "author": author,
                "created_at": created_at,
                "content": "",  # 同花顺 API 未提供正文/摘要，默认为空
                "url": target_url,
                "likes": 0,
                "comments": 0,
                "retweets": 0
            })

        # 去重（按 url 去重）
        unique_items = []
        seen_urls = set()
        for pi in parsed_items:
            if pi["url"] not in seen_urls:
                seen_urls.add(pi["url"])
                unique_items.append(pi)

        # 按时间降序排序
        def get_sort_key(x):
            return x["created_at"] if x["created_at"] else "1970-01-01 00:00:00"
        
        unique_items.sort(key=get_sort_key, reverse=True)

        filepath = os.path.join("data", filename)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(unique_items, f, ensure_ascii=False, indent=2)

        print(f"【抓取成功】关键词: '{keyword}'，保存到: {filepath}，有效条数: {len(unique_items)}")
        return True

    except Exception as e:
        print(f"  [解析错误] 解析并保存数据时发生异常: {e}")
        return False

def run_crawler():
    targets = [
        {
            "keyword": "蜜雪冰城",
            "stock_code": "HK2097",
            "page_url": "https://stockpage.10jqka.com.cn/HK2097/news/",
            "out_file": "mixue_news.json"
        },
        {
            "keyword": "茶百道",
            "stock_code": "HK2555",
            "page_url": "https://stockpage.10jqka.com.cn/HK2555/news/",
            "out_file": "chabaidao_news.json"
        }
    ]

    captured_data = {}

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

        # 注册监听，截获新闻 API 的 JSON 数据
        def handle_response(res):
            url = res.url
            if "basicapi/notice/news" in url and res.status == 200:
                try:
                    # 识别该数据包属于哪个股票代码
                    for target in targets:
                        if target["stock_code"] in url:
                            raw_json = res.text()
                            captured_data[target["keyword"]] = raw_json
                            print(f"  [拦截成功] 捕获到 '{target['keyword']}' 的新闻数据包")
                except Exception as e:
                    print(f"  [拦截警告] 读取数据包失败: {e}")

        page.on("response", handle_response)

        for i, target in enumerate(targets):
            keyword = target["keyword"]
            page_url = target["page_url"]

            if i > 0:
                # 冷却间隔 10 秒，符合防封及频次控制规范
                cool_down = 10
                print(f"\n[频次控制] 冷却中，等待 {cool_down} 秒后再访问下一个目标...")
                time.sleep(cool_down)

            print(f"\n--- 步骤 {i+1}: 访问 {keyword} 新闻页 ({page_url}) ---")
            try:
                page.goto(page_url, wait_until="domcontentloaded")
                # 等待 6 秒以让页面充足执行 JavaScript 并发起 API 请求
                page.wait_for_timeout(6000)
            except Exception as e:
                print(f"  [访问错误] 页面访问失败: {e}")

        browser.close()

    print("\n--- 步骤 3: 提取清洗与降序去重落盘 ---")
    for target in targets:
        keyword = target["keyword"]
        out_file = target["out_file"]
        
        raw_json_str = captured_data.get(keyword)
        if raw_json_str:
            parse_and_save_data(raw_json_str, keyword, out_file)
        else:
            print(f"【抓取失败】未成功捕获到 '{keyword}' 的数据包，请检查页面加载或网络阻断情况。")

if __name__ == "__main__":
    run_crawler()
