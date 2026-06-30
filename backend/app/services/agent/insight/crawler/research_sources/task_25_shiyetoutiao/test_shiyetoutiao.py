import os
import json
import re
import time
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

def clean_shiye_url(url):
    url = url.strip()
    if url.startswith("//"):
        return "https:" + url
    elif url.startswith("/"):
        return "https://www.shiyetoutiao.cn" + url
    return url

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
        elif "周前" in time_str:
            weeks = int(re.search(r'\d+', time_str).group())
            dt = now - timedelta(weeks=weeks)
            return dt.strftime("%Y-%m-%d 00:00:00")
        else:
            # 格式一: 03月21日
            match = re.search(r'(\d{1,2})\s*月\s*(\d{1,2})\s*日', time_str)
            if match:
                return f"{now.year}-{int(match.group(1)):02d}-{int(match.group(2)):02d} 00:00:00"
            # 格式二: 2025年12月29日
            match_full = re.search(r'(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日', time_str)
            if match_full:
                return f"{match_full.group(1)}-{int(match_full.group(2)):02d}-{int(match_full.group(3)):02d} 00:00:00"
    except Exception:
        pass
    return now.strftime("%Y-%m-%d %H:%M:%S")

def crawl_shiyetoutiao(keyword):
    # 本爬虫严格执行“优先爬取官方基站”原则，直接连接食业头条官方网站并进行客户端级签名检索
    print(f"--- [食业头条] 启动基站直连检索 关键字: '{keyword}' ---")
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
            url = "http://www.shiyetoutiao.cn/"
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            
            # 1. 唤醒搜索抽屉
            search_trigger = page.locator("span", has_text="搜索").filter(visible=True).first
            search_trigger.click()
            page.wait_for_timeout(2000)
            
            # 2. 全局 searchText 强行赋检索词，并派发事件刷新 Vue 状态绑定
            page.evaluate(f'''() => {{
                document.querySelectorAll("input.searchText").forEach(ipt => {{
                    ipt.value = "{keyword}";
                    ipt.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    ipt.dispatchEvent(new Event('change', {{ bubbles: true }}));
                }});
            }}''')
            page.wait_for_timeout(1000)
            
            # 3. 呼叫官方全局检索函数，使前端发送带有效防爬签名的 POST 请求并渲染
            page.evaluate('''() => {
                if (typeof mobileSearch === 'function') {
                    mobileSearch();
                } else if (typeof window.mobileSearch === 'function') {
                    window.mobileSearch();
                }
            }''')
            page.wait_for_timeout(6000)
            
            html = page.content()
            soup = BeautifulSoup(html, "html.parser")
            
            # 4. 精准解析卡片列表
            search_list = soup.find(class_="searchlist")
            if search_list:
                cards = search_list.find_all("li", class_="list_mobile")
                print(f"  [食业头条] 成功定位候选卡片数: {len(cards)}")
                
                for card in cards:
                    try:
                        a_tag = card.find("a")
                        if not a_tag:
                            continue
                            
                        title_el = a_tag.find("h1", class_="tit")
                        if not title_el:
                            continue
                        title = title_el.get_text().strip()
                        
                        href = a_tag.get("href", "")
                        link = clean_shiye_url(href)
                        
                        # 提取 meta
                        info_el = a_tag.find("p", class_="xinxi")
                        author = "食业头条"
                        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        
                        if info_el:
                            spans = info_el.find_all("span")
                            if len(spans) >= 1:
                                author = spans[0].get_text().strip()
                            if len(spans) >= 3:
                                time_raw = spans[2].get_text().strip()
                                created_at = parse_relative_time(time_raw)
                                
                        articles.append({
                            "title": title,
                            "author": author,
                            "created_at": created_at,
                            "content": title,
                            "url": link,
                            "likes": 0,
                            "comments": 0,
                            "retweets": 0
                        })
                    except Exception as ex:
                        print(f"  解析卡片出错: {ex}")
            else:
                print("  [食业头条] 未在页面中查找到 searchlist 渲染容器！")
                
        except Exception as e:
            print(f"  [食业头条] 检索流程异常: {e}")
        finally:
            browser.close()
            
    return articles

if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    for kw, filename in [("蜜雪冰城", "data/mixue_news.json"), ("茶百道", "data/chabaidao_news.json")]:
        results = crawl_shiyetoutiao(kw)
        
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
