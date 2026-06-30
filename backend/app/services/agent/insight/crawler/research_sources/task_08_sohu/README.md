# 搜狐网爬虫验证模块

本模块在免登录前提下，通过其搜狐站内搜索子域 `search.sohu.com` 抓取“蜜雪冰城”和“茶百道”的最新行业资讯。

## 操作指南
运行以下命令执行验证：
```bash
python test_sohu.py
```
数据将自动降序去重后，保存在 `data/mixue_news.json` 和 `data/chabaidao_news.json` 中。
