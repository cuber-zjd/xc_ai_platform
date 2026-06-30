# 证券日报新闻资讯（官方基站检索）爬虫验证模块

本模块在免登录前提下，通过证券日报官方检索接口（`search.zqrb.cn/search.php`），获取最新的权威报纸报道，并对卡片节点实施精确字段拆分（提取作者与时间），安全落盘 JSON 格式数据。

## 操作指南
运行以下命令执行验证：
```bash
python test_zqrb.py
```
数据将自动降序去重后，保存在 `data/mixue_news.json` 和 `data/chabaidao_news.json` 中。
