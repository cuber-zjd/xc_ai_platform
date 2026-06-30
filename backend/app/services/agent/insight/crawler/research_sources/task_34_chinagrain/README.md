# 粮信网资讯（官方基站检索）爬虫验证模块

本模块在免登录前提下，通过中国粮油信息网官方检索接口（`chinagrain.cn/news/?param=hyxx&key=...`），提取列表页上的详尽条目并格式化落盘 JSON 格式数据。

## 操作指南
运行以下命令执行验证：
```bash
python test_chinagrain.py
```
- 目标品牌数据保存在 `data/mixue_news.json` 和 `data/chabaidao_news.json` 中（由于该媒体无相关商业茶饮报道，客观均为空列表）。
- 为验证提取和清洗逻辑的可用性，特设有验证数据保存在 `data/verify_test.json`（抓取小麦相关最新资讯）中，供用户实机验证。
