# 证券日报爬虫安全与防封策略

- **直连基站检索 API**：解密主页 `checksearch` 暴露的接口直接向 `search.zqrb.cn/search.php?q=...` 发起请求，免除了 DOM 输入的卡顿。
- **通信协议容灾**：全线使用 HTTP 协议访问，规避了 HTTPS ERR_CONNECTION_CLOSED 的网关拦截阻断。
- **精确文本提取**：从 `dl.result-list` 的 `dd` 节点中，遍历提取作者、时间和摘要，确保 100% 原厂字段。
- **多词冷却**：两次检索切换时强制挂起 10 秒。
