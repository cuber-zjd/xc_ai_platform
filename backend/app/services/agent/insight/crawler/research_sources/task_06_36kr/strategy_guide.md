# 36kr 爬虫安全与防封策略

- **频次控制**：每次词搜索切换时，程序强制挂起 10 秒（冷却期）。
- **静态 DOM 解析**：避开 initialState 的 AES 解密，采用浏览器端渲染后解析纯文本。
- **User-Agent 混淆**：使用标准的 Chrome 桌面版 User-Agent 伪装。
