# 粮油市场报资讯（官方基站检索）爬虫验证模块

本模块在免登录前提下，通过粮油市场报官方检索接口（`grainnews.com.cn/search.aspx?search=...`），提取列表页上的详尽摘要并格式化落盘 JSON 格式数据。

## 操作指南
运行以下命令执行验证：
```bash
python test_grainnews.py
```
- 目标数据保存在 `data/mixue_news.json` 和 `data/chabaidao_news.json` 中（客观由于该垂直报纸无奶茶报道，均为空列表）。
- 爬虫解析逻辑与格式化清洗功能的验证数据保存在 `data/verify_test.json`（抓取小麦相关最新资讯）中，供用户实机验证。
