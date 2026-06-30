# 中国食品报网（官方 API 直连）资讯抓取验证模块

本模块在免登录前提下，通过中国食品报网核心检索 API（`/api/blade-desk/pass/article/search`），极速拉取并清洗行业新闻，避开前台页面强制加装的人机盾防御拦截。

## 操作指南
运行以下命令执行验证：
```bash
python test_cnfood.py
```
数据将自动降序去重、清洗掉 HTML 高亮后，保存在 `data/mixue_news.json` 和 `data/chabaidao_news.json` 中。
