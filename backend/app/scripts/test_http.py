import http.client
import json

extracted_data = []

try:
    # 1. 确认服务是 HTTP 还是 HTTPS！本地开发通常用 HTTP
    conn = http.client.HTTPConnection("localhost", 8000, timeout=100)

    # 2. payload 必须编码为 bytes
    payload = json.dumps(
        {
            "text": "豆油主力合约收盘价为8605元/吨，涨32元/吨，豆粕主力合约收盘价3021元/吨，涨1元/吨。今日连盘油粕比为2.8484，现货方面，张家港现货市场油粕比为3.0205，隔夜CBOT油粕比为4.581。",
            "requirements": [
                "豆油价格(数字)",
                "豆油涨幅(数字)",
                "豆粕价格(数字)",
                "豆粕涨幅(数字)",
                "油粕比",
                "张家港现货市场油粕比",
                "隔夜油粕比",
            ],
            "enable_reasoning": False,
        }
    ).encode(
        "utf-8"
    )  # 🔑 关键：转 bytes

    headers = {
        "ai-sign": "xc-rpa-1ba531fa-264d-4fa2-b57c-006442b46f5d",
        "User-Agent": "Apifox/1.0.0 (https://apifox.com)",
        "Content-Type": "application/json",
        "Accept": "*/*",
        "Host": "localhost:8000",
        "Connection": "keep-alive",
    }

    # 3. 发送请求
    conn.request(
        "POST", "/api/v1/external/extract_with_text", body=payload, headers=headers
    )

    # 4. 获取响应 + 状态码检查
    res = conn.getresponse()
    status = res.status
    data = res.read().decode("utf-8")

    if status != 200:
        print(f"❌ 请求失败: {status} {res.reason}")
        print(data)
    else:
        try:
            # 解析统一响应格式 Result
            result_obj = json.loads(data)
            if result_obj.get("code") == 200:
                # 提取内部的数组
                extracted_data = result_obj.get("data", {}).get("extracted_data", [])
                print("✅ 提取结果 (纯数组):", extracted_data)
            else:
                print(f"❌ 业务失败: {result_obj.get('msg')}")
        except Exception as parse_err:
            print(f"❌ JSON 解析失败: {parse_err}")
            print("原始数据:", data)

except Exception as e:
    print(f"❌ 请求异常: {type(e).__name__}: {e}")

finally:
    # 5. 务必关闭连接
    conn.close()
