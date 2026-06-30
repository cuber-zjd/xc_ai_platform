# 人民网新闻资讯（官方基站检索）爬虫验证模块

本模块在免登录前提下，通过人民网官方检索接口（`search.people.cn/s?keyword=...`），精准提取卡片并格式化落盘 JSON 格式数据。

## 操作指南
运行以下命令执行验证：
```bash
python test_people.py
```
数据将自动降序去重后，保存在 `data/mixue_news.json` 和 `data/chabaidao_news.json` 中。
