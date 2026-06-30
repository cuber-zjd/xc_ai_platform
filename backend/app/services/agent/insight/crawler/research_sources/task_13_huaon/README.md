# 华经产业研究院爬虫验证模块

本模块在免登录前提下，抓取“蜜雪冰城”和“茶百道”在华经情报网（huaon.com）的最新行业研报。脚本中显式配置忽略了其过期的 HTTPS 证书链。

## 操作指南
运行以下命令执行验证：
```bash
python test_huaon.py
```
数据将自动降序去重后，保存在 `data/mixue_news.json` 和 `data/chabaidao_news.json` 中。
