# 新蛋白网（官方 WordPress 直连）资讯抓取验证模块

本模块在免登录前提下，通过新蛋白网（`newprotein.cn`，重定向为 `foodsustainability.cn`）检索接口，抓取并清洗行业报道。

## 操作指南
运行以下命令执行验证：
```bash
python test_newprotein.py
```
- 本地防误配机制已装载。蜜雪冰城和茶百道无相关匹配文章，结果自动落盘为空列表 `[]`（无无关退化文章噪音）。
- 验证词“植物奶”的抓取与时间清洗数据保存在 `data/verify_test.json` 中，用作格式性校验。
