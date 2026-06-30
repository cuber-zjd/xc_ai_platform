# 新蛋白网爬虫防封与数据过滤策略

- **基站直连**：直连重定向后的 WordPress 搜索端口：`https://foodsustainability.cn/?s=关键词`，高频轻量且免除浏览器组件依赖。
- **降噪防误配**：判定 `title` 中必须正向包含检索词，防范 WP 模板无匹配时默认加载“最新发布”无关新闻噪音。
- **隐藏绝对时间还原**：利用 BeautifulSoup 抽取 `aside.post-meta` 中隐藏的 `<time datetime="...">` 属性，并将 ISO-8601 时区时间转换为标准 `YYYY-MM-DD HH:MM:SS` 秒级时间。
- **多词冷却**：两次检索切换时强制挂起 5 秒。
