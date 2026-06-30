# 新浪财经爬虫安全与防封策略

- **双保险拦截**：在浏览器渲染搜索页面时，捕获 `search.sina.com.cn/api/news` 数据包以直接解码 JSON，作为降级方案再采用 DOM 解析。
- **高亮剥离**：在 DOM 提取时，对 `result-title` 内的 font 高亮标签调用 BeautifulSoup 的 `get_text()` 自动净化。
- **多词冷却**：两次搜索切换时挂起 10 秒。
