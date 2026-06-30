# 中国饮品快报爬虫验证模块

中国饮品快报官方域名 `cndrinknews.com` 被 Cloudflare 防火墙强制拦截并返回 403。为此本模块采用了 **Foodaily 平台代署名代理抓取方案**。

## 操作指南
运行以下命令执行验证：
```bash
python test_cndrink.py
```
数据将自动降序去重后，保存在 `data/mixue_news.json` 和 `data/chabaidao_news.json` 中。
