# 今日头条（头条搜索）爬虫验证模块

本模块在免登录前提下，通过其标准的 GET 检索页及 `pd=information` 参数，抓取今日头条资讯栏目“蜜雪冰城”和“茶百道”的最新行业资讯。包含跳转保护链接 unquote 二次解码逻辑，可直接解出并落盘真正的落地文章 URL。

## 操作指南
运行以下命令执行验证：
```bash
python test_toutiao.py
```
数据将自动降序去重后，保存在 `data/mixue_news.json` 和 `data/chabaidao_news.json` 中。
