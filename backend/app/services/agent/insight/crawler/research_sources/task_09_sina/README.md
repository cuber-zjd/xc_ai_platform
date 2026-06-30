# 新浪财经爬虫验证模块

本模块在免登录前提下，抓取“蜜雪冰城”和“茶百道”在新浪财经的最新行业资讯。包含 API 拦截优先与 DOM 解析兜底的双保险机制。

## 操作指南
运行以下命令执行验证：
```bash
python test_sina.py
```
数据将自动降序去重后，保存在 `data/mixue_news.json` 和 `data/chabaidao_news.json` 中。
