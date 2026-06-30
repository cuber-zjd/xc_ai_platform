import requests
from playwright.sync_api import sync_playwright

def get_xq_a_token():
    print("通过 Playwright 访问雪球首页提取 xq_a_token...")
    token = None
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        page.goto("https://xueqiu.com/")
        page.wait_for_timeout(3000)
        
        cookies = context.cookies()
        for cookie in cookies:
            if cookie['name'] == 'xq_a_token':
                token = cookie['value']
                print(f"成功拿到 xq_a_token: {token}")
                break
        browser.close()
    return token

def test_api(token):
    url = "https://xueqiu.com/query/v1/search/status.json"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://xueqiu.com/k?q=%E8%9C%9C%E9%9B%AA%E5%86%B0%E5%9F%8E",
        "Cookie": f"xq_a_token={token}"
    }
    params = {
        "sortId": "1",
        "q": "蜜雪冰城",
        "count": "10",
        "page": "1"
    }
    
    print(f"直接发起 API 请求到 {url}...")
    res = requests.get(url, headers=headers, params=params)
    print(f"状态码: {res.status_code}")
    print(f"响应前缀: {res.text[:300]}")

if __name__ == "__main__":
    token = get_xq_a_token()
    if token:
        test_api(token)
    else:
        print("未能提取到 xq_a_token！")
