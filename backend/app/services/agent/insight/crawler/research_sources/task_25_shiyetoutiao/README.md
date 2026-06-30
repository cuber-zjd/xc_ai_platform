# 食业头条新闻资讯（官方基站检索）爬虫验证模块

本模块在免登录前提下，利用 Playwright 点击唤醒搜索抽屉，并直接在网页作用域中强行调用全局 `mobileSearch()` 函数触发 Ajax 级列表渲染，精准提取卡片并格式化落盘 JSON 格式数据。

## 操作指南
运行以下命令执行验证：
```bash
python test_shiyetoutiao.py
```
数据将自动降序去重后，保存在 `data/mixue_news.json` 和 `data/chabaidao_news.json` 中。
