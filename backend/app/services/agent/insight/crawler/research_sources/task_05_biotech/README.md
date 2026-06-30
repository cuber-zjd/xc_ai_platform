# 生物通新闻资讯（必应站内检索代理）爬虫验证模块

由于生物通官方站内检索接口 `/search/` 发生 404 故障，本模块基于必应（Bing）搜索引擎，以 `site:ebiotrade.com 关键词` 指令进行精准站内代理检索，并对结果进行严格域名过滤以提取其站内文章。

## 操作指南
运行以下命令执行验证：
```bash
python test_biotech.py
```
数据将自动降序去重后，保存在 `data/mixue_news.json` 和 `data/chabaidao_news.json` 中。由于客观事实，若生物通上无相关报道，数据过滤后将以 `[]` 空数组落盘。
