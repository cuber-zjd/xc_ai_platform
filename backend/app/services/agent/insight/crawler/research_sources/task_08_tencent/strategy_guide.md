# 腾讯网爬虫安全与防封策略

- **搜狗 site 定向检索**：直接访问 `www.sogou.com/web?query=site:new.qq.com...` 避开腾讯主站反爬和无搜索接口的硬性限制。
- **跳转落地页后台拦截**：在 Playwright 后台开启独立标签页加载搜狗的 `/link?url=...` 跳转链接，通过 `wait_until="commit"` 拦截其 Headers 级别的 302 重定向重定向直接获取真实的腾讯新闻 `new.qq.com` 落地链接。
- **多词冷却**：两次检索切换时强制挂起 10 秒。
