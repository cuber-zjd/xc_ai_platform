# 证券之星爬虫安全与防封策略

- **基站首页要闻直连解析**：直接通过 `page.goto` 访问 `www.stockstar.com` 和 `news.stockstar.com`，避开了检索接口 404 与 Headless 搜索表单不可见交互死等的问题。
- **超链接精确提取过滤**：在内存中只提取 href 包含 `"stockstar.com"` 的链接，排除外部广告干扰。
- **多词冷却**：两次检索切换时强制挂起 10 秒。
