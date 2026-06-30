# Insight 服务目录约定

本目录承载“研发营销市场洞察平台”的后端业务服务。

- `crawler/`：通用联网采集、Firecrawl、百度搜索、Bocha/博查 API 等采集适配。
- `intelligence/`：情报清洗、候选情报、正式情报、审核与标签。
- `visibility/`：情报、主题、报告的用户/角色/部门可见性规则。
- `report/`：报告素材、模板、偏好、自定义图表与生成流程。

第一阶段先建立目录和接口边界，再按开发计划逐步补充 P0 表、接口和页面。

当前 P0 已提供通用联网采集基础链路：

- 配置项：`INSIGHT_FIRECRAWL_BASE_URL`、`INSIGHT_FIRECRAWL_API_KEY`、`INSIGHT_FIRECRAWL_TIMEOUT_SECONDS`。
- 接口：`POST /ai-api/v1/insight/crawler/manual-url`。
- 行为：创建采集任务，调用 Firecrawl 抽取正文，写入 `insight_crawl_result` 和 `insight_intelligence_candidate`。
- 搜索发现：`POST /ai-api/v1/insight/crawler/search-discovery` 支持百度和 Bocha/博查 API；启用 `enable_llm_filter` 时会先调用平台 LLM 对搜索结果判分筛选。`crawl_top_n=0` 的轻量模式不抓正文，但会对搜索命中执行 AI 初筛，候选入库即带摘要、标签、情感、机会点、风险点、相关性分和置信度。
- 清洗入库：抓取结果会做 URL 归一、追踪参数清理、标题/摘要清洗、发布时间解析、去重判断和候选主题/类型/标签识别；正文抓取模式继续复用 Firecrawl 和正文级 LLM 摘要。
- 候选查询：`GET /ai-api/v1/insight/intelligence/candidates` 返回候选情报分页列表，供情报中心和后续审核流程使用。
- 候选审核：`POST /ai-api/v1/insight/intelligence/candidates/{candidate_id}/promote`、`/reject`、`/ignore` 支持通过、驳回和忽略；通过后写入正式情报、来源证据和审核记录。
- 正式情报：`GET /ai-api/v1/insight/intelligence` 和 `GET /ai-api/v1/insight/intelligence/{intelligence_id}` 提供正式情报分页列表、详情正文和来源证据读取。
- 情报维护：`POST /ai-api/v1/insight/intelligence`、`PUT /ai-api/v1/insight/intelligence/{intelligence_id}` 和 `POST /ai-api/v1/insight/intelligence/{intelligence_id}/sources` 支持人工新增、编辑和补充来源证据。
- 权限与情报池：`GET/POST /ai-api/v1/insight/intelligence/{intelligence_id}/visibility-rules` 管理可见性授权；`/intelligence-pool` 和 `/intelligence/{id}/pool` 管理用户个人收藏、稍后看、隐藏和 `report_material` 报告素材。
- 首页看板：`GET /ai-api/v1/insight/dashboard` 聚合当前用户可见情报，返回 KPI、近 7 日趋势、来源分布、重点动态和最新情报。
- 数据源执行：`POST /ai-api/v1/insight/data-sources/{id}/execute` 按数据源关键词逐个搜索并记录命中、抓取、候选和失败明细；候选生成优先使用数据源 `company_id` 归因，后续企业档案可按 `company_id` 聚合情报。
- 自动处理策略：数据源 `fetch_config` 可配置 `auto_review_mode`、`auto_review_min_confidence`、`auto_review_required_tags`、`auto_review_intelligence_types`、`auto_add_to_report_pool` 和 `auto_report_folder`。采集完成后按策略自动通过候选情报，并可自动加入 `report_material` 报告素材池；默认关闭，自动操作会写入审核记录。
- 任务清理与验收：`POST /ai-api/v1/insight/data-sources/tasks/cleanup-stale` 可清理超时 running/pending 任务；P0 封板验收脚本为 `backend/scripts/insight_p0_acceptance.py`。

当前 P1 已提供企业档案和报告最小闭环：

- 企业档案：`GET/POST /ai-api/v1/insight/companies` 和 `GET/PUT /ai-api/v1/insight/companies/{company_id}` 管理企业主数据，并聚合企业指标、关联数据源、情报类型分布、标签和时间线。
- 报告生成：`GET /ai-api/v1/insight/reports`、`POST /ai-api/v1/insight/reports/generate`、`GET /ai-api/v1/insight/reports/{report_id}` 和 `PUT /ai-api/v1/insight/reports/{report_id}` 提供报告列表、生成、详情和编辑。
- 报告服务：`report_service.py` 从 `report_material` 素材池或指定情报 ID 选择素材，调用 LLM 生成结构化报告草稿，写入 `insight_report`、`insight_report_material`、`insight_report_version` 和 `insight_task`。
- 素材追溯：报告素材引用保留 `intelligence_id`、来源标题、原文链接和引用摘要，前端报告中心可以从报告跳回一条条原文资讯。
- P1 报告测试：`backend/scripts/insight_p1_report_smoke.py` 使用真实素材池生成多份报告，用于验证 LLM 草稿生成、版本保存和素材引用数量。
