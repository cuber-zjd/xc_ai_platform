# 36kr 爬虫验证模块

本模块用于在不登录前提下抓取“蜜雪冰城”和“茶百道”在 36kr 的最近行业资讯。

## 操作指南
运行以下命令执行验证：
```bash
python test_36kr.py
```
数据将自动降序去重后，保存在 `data/mixue_news.json` 和 `data/chabaidao_news.json` 中。
