# Insight 情报、报告、企微、权限与采集策略改造记录

更新时间：2026-07-01

## 一、改造目标

本轮改造围绕“用户能顺手用、数据能进入资产链路、权限边界清楚”展开，重点解决以下问题：

- 情报可以从 Word、Excel 批量导入，不再只能逐条录入。
- 分类和标签由系统字典控制，AI 只能在启用字典中选择，避免标签越用越乱。
- 正式情报也展示“为什么选中”和“对业务有什么启示”，让用户能快速判断价值。
- 企业微信推送链接改为企微 OAuth 换登，不做永久公开链接。
- 推送对象改为人员、部门、角色选择器，不再主要依赖手填工号。
- 报告可以直接从情报中心勾选素材生成，并支持按发布时间限制素材范围。
- 普通用户仅能看到本人创建或明确授权的数据，后端先过滤再分页和聚合。
- 采集策略调整为百度资讯优先、博查每个监测对象合并查询一次，并补充行业、政策、舆情主题。

## 二、用户操作变化

### 1. 情报导入

入口：情报中心右上角“上传导入”。

支持文件：

- `.docx`
- `.xlsx`
- `.xlsm`

操作流程：

1. 上传 Word 或 Excel。
2. 系统解析文本和表格。
3. AI 自动拆成多条情报，并给出标题、摘要、正文、发布时间、分类、标签、选中理由和业务启示。
4. 用户在预览弹窗中勾选需要保存的情报。
5. 确认后进入正式情报，并同步生成来源记录、资产、向量索引和图谱关系。

注意：旧版 `.doc`、`.xls` 暂不直接支持，需要先转成新版格式。

### 2. 情报筛选

主筛选项精简为：

- 关键词
- 所属公司/企业
- 分类
- 标签
- 发布时间
- 重要性

旧的数据源、项目名、情感、主体类型等不再作为主筛选项，避免筛选区过重。

### 3. 报告生成

现在有两种入口：

- 在情报中心勾选多篇正式情报，点击“生成报告”。
- 在报告中心点击新建报告，再通过“选择素材”选择文章。

素材选择支持发布时间范围：

- 近 7 天
- 近 15 天
- 近 30 天
- 自定义日期

报告生成过程会显示阶段：

1. 读取素材
2. 素材分组
3. 问题拆解
4. 交叉验证
5. 正文生成
6. 引用整理
7. 完成

### 4. 企业微信推送

推送前仍会先生成 `insight_notification` 记录，并校验当前用户是否有目标报告或情报的访问权限。

链接打开方式：

1. 企微内点击推送链接。
2. 进入平台企微 OAuth 地址。
3. 通过企业微信 `code` 换取 UserID。
4. 根据 `SysUser.employee_id` 优先匹配平台用户，匹配不到再看用户名。
5. 发放平台登录态后跳转报告或情报详情。

未绑定或无权限时，只展示错误提示，不展示内容。

接收人选择支持：

- 搜索人员姓名/工号
- 选择部门
- 选择角色
- 已选对象列表
- 手工输入备用

## 三、权限口径

普通用户默认只能看到：

- 本人创建的数据
- 明确授权给本人的数据
- 授权给本人所在部门的数据
- 授权给本人角色的数据

管理员保留全量查看和授权能力。

本轮已复核并改造的范围：

- 情报列表和详情
- 报告列表、详情和素材选择
- 监测配置列表
- 情报资产检索
- AI 助手检索上下文
- 首页统计
- 企业微信推送权限校验

重要变化：`public` 不再代表普通用户默认可见全平台数据，避免普通账号看到未授权情报和报告。

## 四、采集策略变化

本轮策略调整为：

1. 百度资讯先跑，作为低成本发现源。
2. 博查不再只在“百度结果不足”时补充，而是每个监测对象至少按合并关键词跑一次。
3. 博查不按企业、模块、标签、网站做笛卡尔积调用。
4. 每个监测对象把企业名、别名和核心关键词合并成 1 到 2 个查询。
5. 单次返回量受频率控制：每日 10 条、每周 30 条、半月及以上 50 条。
6. 链接去重优先，历史已抓取链接直接跳过，不再重复进入过滤和评审。
7. 后续重点网站和其他网站仍按渠道适配器独立运行，不和百度、博查混成一个源。

新增主题监测对象：

- 果葡糖浆与麦芽糖浆市场动态
- 植物蛋白与蛋白粉机会动态
- 豆粕粮油与大豆加工动态
- 玉米深加工与功能糖政策市场
- 饮料茶饮客户需求变化
- 食品安全与质量舆情

## 五、测试结果

### 1. 文件导入预览测试

测试方式：临时生成一个 Word 和一个 Excel，只走导入预览，不确认入库，避免污染正式数据。

结果：

- Word：解析 60 字，拆出 2 条情报，标签命中“客户动向、低糖趋势”。
- Excel：解析 121 字，拆出 2 条情报，标签命中“客户动向、低糖趋势、销售机会”。
- 预览无错误。

### 2. 近 15 天完整采集测试

测试时间：2026-07-01 凌晨。

执行范围：

- 150 个启用监测对象
- 1050 个渠道任务
- 百度资讯、博查和已接入网站渠道按当前策略执行

汇总结果：

| 指标 | 数量 |
| --- | ---: |
| 监测对象 | 150 |
| 成功监测对象 | 150 |
| 失败监测对象 | 0 |
| 渠道任务 | 1050 |
| 新命中 | 161 |
| 新候选 | 161 |
| 历史重复跳过 | 1381 |
| 0 新命中监测对象 | 84 |

补充链路结果：

| 指标 | 数量 |
| --- | ---: |
| 今日新增候选 | 172 |
| 今日新增正式情报 | 88 |
| 今日新增资产 | 162 |
| 今日新增向量 | 162 |
| 今日新增图谱节点 | 872 |
| 今日新增图谱关系 | 1752 |

正式情报类型分布：

| 类型 | 数量 |
| --- | ---: |
| 客户动向 | 31 |
| 行业资讯 | 26 |
| 竞品动态 | 10 |
| 风险预警 | 9 |
| 产品动态 | 7 |
| 政策监管 | 2 |
| 价格行情 | 2 |
| 技术趋势 | 1 |

### 3. 数据量偏少原因

本轮观察到的主要原因：

- 历史重复多：本次 1381 条被历史链接去重跳过，这是最大因素。
- 监测对象长尾明显：150 个监测对象里 84 个没有新增命中。
- 部分主题关键词仍偏窄：例如政策、行业主题命中不稳定，需要继续扩展同义词和别名。
- 渠道质量差异大：百度和博查更稳定，部分网站渠道近半月没有有效结果或适配器可抓页面有限。
- AI 评审仍会过滤一部分弱相关内容：172 条候选中 88 条进入正式情报，74 条归为噪声或低价值内容。

后续建议：

- 对 0 命中的监测对象批量补充别名和行业词。
- 为高价值客户增加产品、原料、区域、品牌别名。
- 继续接入重点垂直网站适配器，提高非搜索渠道的有效命中。
- 把“低价值但可观察”的内容保留在候选，不强行进入正式情报。

## 六、验证情况

已通过：

```bash
uv run ruff check app/services/agent/insight app/api/v1/endpoints/agent/insight app/schemas/agent/insight scripts/insight_run_all_monitor_configs_once.py scripts/insight_seed_topic_monitor_configs.py
uv run python -m py_compile app/services/agent/insight/intelligence_import_service.py app/services/agent/insight/intelligence_service.py app/services/agent/insight/permission_service.py app/services/agent/insight/wecom_oauth_service.py app/services/agent/insight/notification_service.py app/services/agent/insight/report_service.py app/services/agent/insight/assistant_service.py app/services/agent/insight/monitor_execution_service.py app/services/agent/insight/monitor_config_service.py app/api/v1/endpoints/agent/insight/router.py app/schemas/agent/insight/intelligence.py app/schemas/agent/insight/selector.py scripts/insight_run_all_monitor_configs_once.py scripts/insight_seed_topic_monitor_configs.py
uv run python scripts/insight_run_all_monitor_configs_once.py --timeout 180 --log-file tmp/insight_full_collect_20260630.jsonl --summary-file tmp/insight_full_collect_20260630_summary.json
```

前端构建结果：

```bash
pnpm build
```

当前未通过，原因是帆软报表页面存在 4 个既有未使用变量：

- `buildResponseArtifacts`
- `buildAssistantContent`
- `onDraftReady`
- `streamAssistantMessage`

这些错误位于 `frontend/src/features/fr-ai-report/pages/FrAiReportChatPage.tsx`，与本轮 Insight 改造无关。

## 七、后续待办

- 企业微信真实 OAuth 需要在企业微信后台配置可信回调域：`https://ai.xiangchi.com`。
- 真实发送仍依赖 `INSIGHT_WECOM_SEND_ENABLED` 和企业微信应用配置。
- 部门、角色批量推送建议在上线前用真实组织数据再做一轮联调。
- 上传导入确认入库已实现，但演示前建议用真实资料走一次预览确认。
- 普通用户权限需要用真实普通账号再做一次端到端验证。
- 对 0 命中的监测对象做关键词扩展和健康度分层。

## 八、2026-07-06 调度策略与发布时间修复

### 1. 入库漏斗复盘

近 10 天 `keyword_search_discovery` 任务统计：

| 阶段 | 数量 |
| --- | ---: |
| 搜索任务 | 2353 |
| 原始命中 | 10199 |
| 时间窗口保留 | 5734 |
| 规则过滤保留 | 5715 |
| 单轮去重保留 | 5715 |
| 历史去重保留 | 4144 |
| LLM 预筛保留 | 515 |
| 最终入库命中 | 512 |
| 0 新命中任务 | 2044 |

结论：

- 数据偏少的主要瓶颈不是没有搜索结果，而是 LLM 搜索预筛过严。
- 历史 URL 去重也会显著减少重复线索，这是正常现象，但需要避免误把同一文章跨主题关联能力完全丢掉。
- 部分垂直渠道命中很低或长期 0 命中，需要后续按渠道健康度降频，不适合每天全量跑。

### 2. 调度策略调整

- 百度资讯继续作为低成本发现源优先执行。
- 百度资讯适合单对象探针，周期调度中保留“每个 active 监测对象每日可执行”的策略，但请求前增加轻微随机冷却，并继续受调度批次、失败暂停和渠道错误记录控制，降低反爬风险。
- 博查和豆包联网搜索也需要每日覆盖，但不再按单个监测对象逐个调用；周期调度先跑百度和站点适配器，再按客户组、竞对组、行业主题、政策主题等构建聚合 query。
- 聚合搜索每组最多 8 个监测对象，每轮默认最多 20 个聚合 query；博查默认并发 3，豆包默认并发 2。
- 聚合搜索命中后，系统按标题、摘要、URL、企业名、关键词和主题词反向归属到具体监测配置，再进入原有去重、LLM 预筛、AI 自动评审、正式情报/候选线索、资产和向量链路。
- 搜索阶段 LLM 预筛阈值从 `0.55` 下调到 `0.45`，让更多弱相关但可能有价值的线索进入候选，再交由 AI 自动评审决定正式情报、候选线索或噪声。

### 2.1 慢任务原因与改善点

上次全量采集偏慢，主要原因是：

- 调度按监测对象串行推进，搜索任务数量大。
- 豆包联网搜索单次链路较长，通常明显慢于普通搜索 API。
- 部分垂直网站适配器命中为 0，但仍占用执行时间。
- 博查和豆包如果按对象逐个执行，会形成大量相似 query，成本和耗时都偏高。

本次调整后：

- 百度仍逐对象每日探针，但单次较轻，并增加随机冷却。
- 博查、豆包改为每日聚合搜索，调用次数由“对象数”下降为“分组数”。
- 聚合结果反向归属到对象，不牺牲权限和企业档案联动。
- 同一 URL 的历史去重改为“同一监测配置下去重”，允许同一篇文章被不同对象建立归属，避免跨对象情报被过早丢掉。

### 2.2 后续网站适配器运行模式

后续新增的垂直网站不再默认按“所有监测对象逐个搜索”执行，而是按渠道模式进入调度：

| 模式 | 适用渠道 | 调度方式 |
| --- | --- | --- |
| `feed_latest` | Foodaily、食品伙伴网、小食代、36氪、食业头条等列表型媒体 | 每日或按渠道频率抓最新列表，再用规则/AI 反向匹配企业和主题 |
| `site_search` | 有站内搜索但不是主体库的网站 | 按行业主题、产品主题、政策主题聚合搜索 |
| `topic_scan` | 政策、行业、综合舆情类渠道 | 按主题监测运行，不跟每个企业做笛卡尔积 |
| `entity_lookup` | 专利库、交易所公告、工商/资质库等主体查询 | 只对重点企业或明确企业主体执行 |
| `official_watch` | 企业官网、公众号、招聘页、公告页 | 只对企业档案中明确绑定的重点企业执行 |

当前调度器已按渠道 `config_json.execution_policy.collection_mode` 或渠道类型推断模式：

- `industry_media`、`finance_news`、`general_news`、`policy_regulation` 默认按 `feed_latest`，不再跟普通企业监测逐个跑。
- `patent_technology`、`database` 默认按 `entity_lookup`。
- `enterprise_official` 默认按 `official_watch`。
- 未明确配置的普通渠道默认按 `site_search`。

### 3. 发布时间修复规则

本次发现的问题是：搜索摘要里常同时出现文章发布时间和事件日期，例如“昨天 16:00”和“股权登记日为 2026 年 7 月 9 日”。旧解析逻辑优先抓绝对日期，导致把股权登记日、专利公告日、申请公布日期等事件日期误当作文章发布时间。

已调整规则：

- 百度资讯解析优先使用摘要文本，再退回完整搜索上下文。
- 日期解析优先识别开头的 `刚刚/今天/昨天/前天/N 天前`。
- 优先识别靠前的 `7月4日消息/电/讯/报道` 这类新闻发布时间。
- 遇到 `股权登记日、除权除息日、申请公布日期、授权公告日、申请日期、申购日期、上市日期、报告期、全年` 等上下文时，不把该日期作为文章发布时间。
- 历史修复脚本只修明显错配，并记录旧值、新值、修复原因到 `raw_payload.publish_time_repair`。

### 4. 历史数据处理

已执行：

```bash
uv run python scripts/insight_repair_recent_publish_dates.py --since 2026-07-01 --apply
```

处理结果：

- 修复正式情报、来源、采集结果和资产表发布时间共 18 条。
- 修复后复扫 `2026-07-01` 以来数据，待修复项为 0。

### 5. 验证

已通过：

```bash
uv run python -m py_compile app/services/agent/insight/crawler/content_cleaner.py app/services/agent/insight/crawler/search_client.py app/services/agent/insight/monitor_execution_service.py scripts/insight_repair_recent_publish_dates.py
uv run ruff check app/services/agent/insight/crawler/content_cleaner.py app/services/agent/insight/crawler/search_client.py app/services/agent/insight/monitor_execution_service.py scripts/insight_repair_recent_publish_dates.py
```
