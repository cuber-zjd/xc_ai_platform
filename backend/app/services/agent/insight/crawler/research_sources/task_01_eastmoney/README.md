# 任务二：东方财富网未登录资讯爬取

本任务旨在利用 **Playwright** 抓取东方财富网（eastmoney.com）中关于“蜜雪冰城”和“茶百道”的最新帖子与新闻资讯。

## 目录结构说明

- `README.md`: 任务说明（当前文件）
- `strategy_guide.md`: 防封策略规范指南
- `test_eastmoney.py`: 主要爬取验证脚本
- `data/`: 抓取结果数据存放目录
  - `mixue_news.json`: 蜜雪冰城相关最新资讯
  - `chabaidao_news.json`: 茶百道相关最新资讯

## 技术方案

1. 使用 `playwright` 启动 Chromium。
2. 配合常规的去特征启动参数（不修改 webdriver 变量），确保指纹看起来合规。
3. 访问东方财富搜索页或股吧搜索页，拦截搜索相关的异步 API 数据。
4. 清洗帖子主要字段并降序去重存入 `data/` 目录中。
