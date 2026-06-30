# 央视新闻网（官方 SSR 检索）资讯抓取验证模块

本模块在免登录前提下，通过央视搜索的 SSR（服务器端渲染）网页分类接口（`search.php?qtext=关键词&type=web`），拉取并清洗行业新闻，无需使用任何 Headless 浏览器。

## 操作指南
运行以下命令执行验证：
```bash
python test_cctv.py
```
数据将自动清洗掉红字高亮标签，提取原始详情 URL 并在本地降序排序，最终保存在 `data/mixue_news.json` 和 `data/chabaidao_news.json` 中。
