import os
import json
import re
import time
from datetime import datetime
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

def clean_wipo_time(time_str):
    time_str = time_str.strip()
    try:
        match = re.search(r'(\d{2})\.(\d{2})\.(\d{4})', time_str)
        if match:
            day, month, year = match.group(1), match.group(2), match.group(3)
            return f"{year}-{month}-{day} 00:00:00"
    except Exception:
        pass
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def crawl_wipo(keyword):
    print(f"--- [WIPO] 启动检索 关键字: '{keyword}' ---")
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
            url = "https://patentscope.wipo.int/search/zh/search.jsf"
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            
            search_ipt = page.locator("input[id='simpleSearchForm:fpSearch:input']").first
            search_ipt.click()
            search_ipt.fill(keyword)
            page.wait_for_timeout(1000)
            search_ipt.press("Enter")
            
            # 使用 wait_for_selector 等待数据渲染
            try:
                page.wait_for_selector("div.ps-patent-result", timeout=12000)
            except Exception:
                print("  [WIPO] 等待结果卡片元素超时")
                
            html = page.content()
            soup = BeautifulSoup(html, "html.parser")
            
            cards = soup.find_all("div", class_="ps-patent-result")
            print(f"  [WIPO] 找到专利记录卡片数: {len(cards)}")
            
            for card in cards:
                try:
                    title_span = card.find("span", class_="ps-patent-result--title--title")
                    if not title_span:
                        title_span = card.find("span", class_="needTranslation-title")
                    title = title_span.get_text().strip() if title_span else "无标题"
                    title = re.sub(r'^\d+\.?\s*', '', title)
                    
                    a_tag = card.find("div", class_="ps-patent-result--title").find("a") if card.find("div", class_="ps-patent-result--title") else None
                    if not a_tag:
                        a_tag = card.find("a")
                    href = a_tag.get("href", "") if a_tag else ""
                    
                    # 提取专利号用来做唯一 URL 标识
                    pub_no = a_tag.get_text().strip() if a_tag else ""
                    link = f"https://patentscope.wipo.int/search/zh/detail.jsf?docId={pub_no}" if pub_no else href
                    
                    fields_div = card.find("div", class_="ps-patent-result--fields")
                    author = "专利局"
                    if fields_div:
                        for field in fields_div.find_all("span", class_="ps-field"):
                            label_span = field.find("span", class_="ps-field--label")
                            if label_span and "申请人" in label_span.get_text():
                                val_span = field.find("span", class_="ps-field--value")
                                if val_span:
                                    author = val_span.get_text().strip()
                                    break
                                    
                    date_span = card.find(class_="ps-patent-result--title--ctr-pubdate")
                    date_raw = date_span.get_text().strip() if date_span else ""
                    created_at = clean_wipo_time(date_raw)
                    
                    abs_div = card.find(class_="ps-patent-result--abstract")
                    content = abs_div.get_text().strip() if abs_div else ""
                    
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
                except Exception as ex:
                    print(f"  [WIPO] 解析卡片出错: {ex}")
                    
        except Exception as e:
            print(f"  [WIPO] 检索流程异常: {e}")
        finally:
            browser.close()
            
    return articles

def clean_cnipa_time(time_str):
    time_str = time_str.strip()
    try:
        clean = time_str.replace(".", "-")
        if re.match(r'\d{4}-\d{2}-\d{2}', clean):
            return f"{clean} 00:00:00"
    except Exception:
        pass
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def crawl_cnipa_fallback(keyword):
    print(f"--- [CNIPA] 启动降级检索 关键字: '{keyword}' ---")
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
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        
        try:
            url = "http://epub.cnipa.gov.cn/"
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            
            search_ipt = page.locator("input[id='searchStr']").first
            search_ipt.click()
            search_ipt.fill(keyword)
            page.wait_for_timeout(1000)
            search_ipt.press("Enter")
            
            try:
                page.wait_for_selector(".item", timeout=12000)
            except Exception:
                print("  [CNIPA] 等待结果卡片元素超时")
                
            html = page.content()
            soup = BeautifulSoup(html, "html.parser")
            
            cards = soup.find_all(class_=re.compile(r"item"))
            print(f"  [CNIPA] 找到专利记录卡片数: {len(cards)}")
            
            for card in cards:
                try:
                    text = card.get_text().strip()
                    if "申请公布号" not in text:
                        continue
                        
                    # 1. 标题
                    title_div = card.find(class_="tit")
                    title = title_div.get_text().strip() if title_div else "未命名专利"
                    title = re.sub(r'^\[[^\]]+\]\s*', '', title)
                    
                    # 2. 申请公布号 (用于做唯一的 url 排重标识)
                    pub_no = ""
                    pub_match = re.search(r'申请公布号：\s*([A-Za-z0-9]+)', text)
                    if pub_match:
                        pub_no = pub_match.group(1).strip()
                    
                    link = f"http://epub.cnipa.gov.cn/patent/{pub_no}" if pub_no else "javascript:;"
                    
                    # 3. 申请人
                    author = "专利申请人"
                    author_match = re.search(r'申请人：\s*([\u4e00-\u9fa5A-Za-z0-9（）\(\)股份有限公司]+)', text)
                    if author_match:
                        author = author_match.group(1).strip()
                    else:
                        author_match_fallback = re.search(r'申请人：\s*\n*\s*([^\s\n\r]+)', text)
                        if author_match_fallback:
                            author = author_match_fallback.group(1).strip()
                            
                    # 4. 公布时间
                    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    date_match = re.search(r'(申请公布日|授权公告日)：\s*([\d\.]+)', text)
                    if date_match:
                        date_raw = date_match.group(2).strip()
                        created_at = clean_cnipa_time(date_raw)
                        
                    articles.append({
                        "title": title,
                        "author": author,
                        "created_at": created_at,
                        "content": text.replace("\n", " | ")[:300],
                        "url": link,
                        "likes": 0,
                        "comments": 0,
                        "retweets": 0
                    })
                except Exception as ex:
                    print(f"  [CNIPA] 解析卡片出错: {ex}")
        except Exception as e:
            print(f"  [CNIPA] 检索流程异常: {e}")
        finally:
            browser.close()
            
    return articles

def crawl_patent(keyword):
    results = crawl_wipo(keyword)
    if not results:
        print(f"  [警告] WIPO 未获取到结果，触发降级到 CNIPA...")
        results = crawl_cnipa_fallback(keyword)
    return results

if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    for kw, filename in [("蜜雪冰城", "data/mixue_news.json"), ("茶百道", "data/chabaidao_news.json")]:
        results = crawl_patent(kw)
        
        unique_arts = {}
        for art in results:
            unique_arts[art["url"]] = art
            
        sorted_arts = sorted(unique_arts.values(), key=lambda x: x["created_at"], reverse=True)
        
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(sorted_arts, f, ensure_ascii=False, indent=2)
        print(f"成功保存 {len(sorted_arts)} 条数据到 {filename}")
        time.sleep(10)
