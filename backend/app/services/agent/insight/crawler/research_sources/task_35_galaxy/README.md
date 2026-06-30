# 银河证券观点（官方 API 直连）研报抓取验证模块

本模块在免登录前提下，通过中国银河证券官方数据接口（`queryDocList`），提取观点聚焦栏目中的最新报告并格式化落盘 JSON 格式数据。

## 操作指南
运行以下命令执行验证：
```bash
python test_galaxy.py
```
- 目标品牌数据保存在 `data/mixue_news.json` 和 `data/chabaidao_news.json` 中（由于该媒体无相关商业茶饮报道，客观均为空列表）。
- 爬虫解析逻辑与格式化清洗功能的验证数据保存在 `data/verify_test.json`（抓取“Token”相关最新研报）中，供用户实机验证。
