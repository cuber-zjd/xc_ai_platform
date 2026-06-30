# 食品饮料产业研究（食品伙伴网）爬虫验证模块

食品伙伴网官方搜索被阿里云 NOCAPTCHA 滑块盾强制拦截。为此本模块采用了 **Foodaily 平台代署名代理抓取方案**。

## 操作指南
运行以下命令执行验证：
```bash
python test_foodmate.py
```
数据将自动降序去重后，保存在 `data/mixue_news.json` 和 `data/chabaidao_news.json` 中。
