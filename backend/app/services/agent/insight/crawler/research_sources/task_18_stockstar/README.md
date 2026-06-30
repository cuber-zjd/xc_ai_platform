# 证券之星新闻资讯（官方基站解析）爬虫验证模块

本模块严格执行“优先爬取官方基站”原则。由于证券之星官方新闻检索系统发生故障下线，本模块直接连接其官方首页（`stockstar.com`）及新闻中心首页（`news.stockstar.com`），提取和过滤其上展示的最新重大要闻超链接，并在内存中进行精确关键字和域名筛选，实现 100% 直连基站抓取。

## 操作指南
运行以下命令执行验证：
```bash
python test_stockstar.py
```
数据将自动降序去重后，保存在 `data/mixue_news.json` 和 `data/chabaidao_news.json` 中。
