# 任务三：同花顺网未登录资讯爬取

本任务旨在利用 **Playwright** 抓取同花顺网（10jqka.com.cn）中关于“蜜雪冰城”和“茶百道”的最新帖子与新闻资讯。

## 目录结构说明

- `README.md`: 任务说明（当前文件）
- `strategy_guide.md`: 防封策略规范指南
- `test_ths.py`: 主要爬取验证脚本
- `data/`: 抓取结果数据存放目录
  - `mixue_news.json`: 蜜雪冰城相关最新资讯
  - `chabaidao_news.json`: 茶百道相关最新资讯

## 技术方案与反爬攻克

1. **规避强制登录与人机滑块风控**：同花顺财经搜索（`so.10jqka.com.cn`）与问财在未登录且自动化环境下极易触发强制扫码登录弹窗或人机风控。因此，我们改走免登录且风控相对宽松的**个股公开新闻资讯页**策略（蜜雪集团个股代码为 `HK2097`，茶百道为 `HK2555`）。
2. **利用 Playwright 进行会话初始化**：使用 Playwright 启动隐藏特征的 Chromium 访问个股新闻页（例如 `https://stockpage.10jqka.com.cn/HK2097/news/`）。在此过程中，页面自带的加密 JS 脚本会在后台自动生成 `hexin-v` 参数，避免了我们手动破解其复杂的动态混淆算法。
3. **拦截接口响应**：注册 Playwright 的 `response` 监听器，拦截其后台获取新闻列表的 API `https://basic.10jqka.com.cn/basicapi/notice/news` 并保存返回的原始 JSON 数据。
4. **数据清洗与规范化落盘**：对提取到的 JSON 进行清洗：过滤 HTML 标签、将秒级 Unix 时间戳转换为统一的 `YYYY-MM-DD HH:MM:SS` 格式时间、进行多数据源 URL 适配，去重并按发布时间进行降序排列后分别保存为 JSON 数据。

## 运行与操作指南

在当前目录下执行核心抓取脚本：
```bash
python test_ths.py
```
运行完成后，可在 `data/` 目录下查看 `mixue_news.json` 和 `chabaidao_news.json`。
