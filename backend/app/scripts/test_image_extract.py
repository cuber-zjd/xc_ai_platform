import requests
import os

# 配置项
# 建议根据实际运行环境修改端口，默认 8000
API_URL = "http://localhost:8000/ai-api/v1/external/extract_with_image"
# 预设的测试 Key
AI_SIGN = "xc-rpa-1ba531fa-264d-4fa2-b57c-006442b46f5d"

def test_image_extract(image_path: str):
    """
    调用图片数据提取接口的测试函数
    """
    if not os.path.exists(image_path):
        print(f"❌ 错误：找不到文件 '{image_path}'")
        return

    try:
        # 1. 准备请求头
        headers = {
            "ai-sign": AI_SIGN
        }

        # 2. 准备文件数据
        # FastAPI 接口中的参数名是 file
        with open(image_path, "rb") as f:
            files = {
                "file": (os.path.basename(image_path), f, "image/png" if image_path.endswith(".png") else "image/jpeg")
            }

            print(f"🚀 正在发送请求到: {API_URL}")
            print(f"📸 上传图片: {image_path}")
            
            # 3. 发送请求
            response = requests.post(API_URL, headers=headers, files=files, timeout=60)

        # 4. 解析结果
        response.raise_for_status()
        result = response.json()

        if result.get("code") == 200:
            extracted_data = result.get("data", {}).get("extracted_data", [])
            print("\n✅ 提取成功！得到 {} 行数据:".format(len(extracted_data)))
            print("-" * 50)
            for i, row in enumerate(extracted_data):
                print(f"行 {i+1}: {row}")
            print("-" * 50)
        else:
            print(f"❌ 业务逻辑失败: {result.get('msg')}")

    except requests.exceptions.RequestException as e:
        print(f"❌ 网络请求异常: {e}")
    except Exception as e:
        print(f"❌ 系统异常: {e}")

if __name__ == "__main__":
    # 你可以修改这里的路径进行测试
    test_image = "test_table.jpg" 
    print("提示：请确保后端服务已启动，并修改脚本中的 test_image 路径为真实图片路径。")
    test_image_extract(test_image)
