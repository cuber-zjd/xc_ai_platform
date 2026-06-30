# 腾讯网新闻资讯（搜狗站内检索代理）爬虫验证模块

本模块在免登录前提下，基于搜狗搜索引擎（腾讯官方控股），以 `site:new.qq.com 关键词` 指令进行精准站内代理检索，并对结果进行严格域名过滤和后台跳转解码，提取腾讯新闻原创文章。

## 操作指南
运行以下命令执行验证：
```bash
python test_tencent.py
```
数据将自动降序去重后，保存在 `data/mixue_news.json` 和 `data/chabaidao_news.json` 中。
