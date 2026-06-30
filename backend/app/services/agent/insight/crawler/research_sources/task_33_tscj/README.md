# 泰山财经资讯（官方基站检索）爬虫验证模块

本模块在免登录前提下，通过鲁网百度站内搜索引擎接口（`so.sdnews.com.cn/cse/search?q=...`），精确提取泰山财经的上市公司与行业报道并格式化落盘 JSON 格式数据。

## 操作指南
运行以下命令执行验证：
```bash
python test_tscj.py
```
数据将自动降序去重后，保存在 `data/mixue_news.json` 和 `data/chabaidao_news.json` 中。
