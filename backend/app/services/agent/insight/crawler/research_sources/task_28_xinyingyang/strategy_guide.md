# 新营养爬虫安全与防封策略

- **站内搜索子域直连**：直连 `https://www.xinyingyang.com/index.php?m=search&c=index&a=init&typeid=1&siteid=1&q=...` 发送请求，绕过主页面加载开销。
- **高精度卡片解析**：从 `li.wrap` 节点中提取标题、链接、摘要与作者。
- **秒级时间抓取**：提取 `div.adds` 发布时间，补全为标准的 `YYYY-MM-DD 00:00:00` 格式，规避正则转换的出错率。
- **多词冷却**：两次检索切换时强制挂起 10 秒。
