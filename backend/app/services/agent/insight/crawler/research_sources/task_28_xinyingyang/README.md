# 新营养新闻资讯（官方基站检索）爬虫验证模块

本模块在免登录前提下，通过新营养官方检索接口（`xinyingyang.com/index.php?m=search...`），精准提取卡片并格式化落盘 JSON 格式数据。

## 操作指南
运行以下命令执行验证：
```bash
python test_xinyingyang.py
```
数据将自动降序去重后，保存在 `data/mixue_news.json` 和 `data/chabaidao_news.json` 中。
