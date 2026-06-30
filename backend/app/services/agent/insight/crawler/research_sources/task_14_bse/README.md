# 北京证券交易所官网信息披露公告爬虫验证模块

本模块在免登录前提下，通过北交所上市公司信息披露专区（`bse.cn/disclosure/announcement.html`），以关键字输入模拟触发其后台 Ajax `/disclosureInfoController/companyAnnouncement.do` 数据交互，抓取并落盘新茶饮企业相关的权威公告与审核进度数据。

## 操作指南
运行以下命令执行验证：
```bash
python test_bse.py
```
数据将自动降序去重后，保存在 `data/mixue_news.json` 和 `data/chabaidao_news.json` 中。
