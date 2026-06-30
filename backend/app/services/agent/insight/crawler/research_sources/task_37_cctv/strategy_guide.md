# 央视网爬虫安全与防封策略

- **基站直连 SSR**：使用 `urllib` 直连 `https://search.cctv.com/search.php?qtext=关键词&type=web`，由于该页面为服务器端渲染，可避开复杂的 Playwright 前端模拟。
- **原始落地页提取**：直接提取 `span[lanmu1]` 节点中的 `lanmu1` 属性值作为落地链接，避免了对 `link_p.php` 转发接口的参数解析与再次请求，安全度极高。
- **高纯度 HTML 洗涤**：采用 BeautifulSoup 对标题与摘要进行红字高亮 `font` 标签洗涤，并过滤了摘要里的图片（`img`）等子节点。
- **多词冷却**：两次检索切换时强制挂起 5 秒。
