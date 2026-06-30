# 上海证券交易所官网信息披露公告爬虫验证模块

本模块在免登录前提下，通过上交所上市公司信息披露公告专区（`sse.com.cn/disclosure/listed/announcement/`），以关键字输入模拟触发数据更新，并对返回的公告行实施严格的“6位证券代码正则强校验”，精确提取和落盘相关的信披数据。

## 操作指南
运行以下命令执行验证：
```bash
python test_sse.py
```
数据将自动降序去重后，保存在 `data/mixue_news.json` 和 `data/chabaidao_news.json` 中。
