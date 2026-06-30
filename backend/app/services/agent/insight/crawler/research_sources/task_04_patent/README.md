# 专利数据库（WIPO & CNIPA）爬虫验证模块

本模块用于在免登录前提下，抓取“蜜雪冰城”和“茶百道”在世界知识产权组织（WIPO）及国家知识产权局（CNIPA）的最权威专利数据。

## 操作指南
运行以下命令执行验证：
```bash
python test_patent.py
```
数据将自动降序去重后，保存在 `data/mixue_news.json` 和 `data/chabaidao_news.json` 中。
