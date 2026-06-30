import requests
try:
    resp = requests.post(
        "http://127.0.0.1:8000/ai-api/v1/login/access-token",
        data={"username": "admin", "password": "admin123", "grant_type": "password"}
    )
    print(f"Status: {resp.status_code}")
    print(f"Body: {resp.text}")
except Exception as e:
    print(f"Error: {e}")
