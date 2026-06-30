# 咖门（微信公众号）爬虫验证模块

微信公众号属于封闭生态。本模块通过加载咖门在 36kr 绑定的唯一认证官方同步专栏 `https://www.36kr.com/user/1080897699`，在免登录前提下，成功抓取其同步更新的原创文章，并通过精准正则表达式排除其他人的杂音文章。

## 操作指南
运行以下命令执行验证：
```bash
python test_kamen.py
```
数据将自动降序去重后，保存在 `data/mixue_news.json` 和 `data/chabaidao_news.json` 中。
