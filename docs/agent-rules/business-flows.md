# 核心业务流程

本文件用于理解和维护主要业务链路。新增或重构核心流程时，需要同步更新本文件。

## 1. 登录鉴权流程

入口文件：

- 前端登录页：`frontend/src/pages/auth/LoginPage.tsx`
- 前端认证状态：`frontend/src/store/useAuthStore.ts`
- 前端 API 客户端：`frontend/src/api/client.ts`
- 后端登录接口：`backend/app/api/v1/endpoints/system/login.py`
- 后端认证依赖：`backend/app/api/deps.py`
- 后端 token 工具：`backend/app/core/security.py`

流程：

1. 用户在登录页输入工号和密码。
2. 前端通过 `authApi.login` 提交 `FormData`。
3. 后端查询 `SysUser` 并校验密码。
4. 后端生成 JWT，返回 token 和用户信息。
5. 前端保存 token 和 user。
6. 后续请求由 Axios 拦截器自动注入 Authorization。
7. 受保护接口通过 `get_current_user` 解析 token 并查询当前用户。

## 2. 合同审查流程

入口文件：

- 前端合同模块：`frontend/src/features/contract/`
- 合同接口：`backend/app/api/v1/endpoints/agent/contract/contracts.py`
- 合同服务：`backend/app/services/agent/contract/contract_service.py`
- 文件服务：`backend/app/services/system/file_service.py`
- 合同 Agent 图：`backend/app/agents/definitions/contract_review/graph.py`
- 合同 Agent 节点：`backend/app/agents/definitions/contract_review/nodes.py`
- 合同 Agent 状态：`backend/app/agents/definitions/contract_review/state.py`

流程：

1. 前端上传合同文件、标题、合同类型和发起人。
2. 后端将文件保存到 MinIO。
3. 后端创建合同数据库记录，状态为 `UPLOADING`。
4. 后端通过 `BackgroundTasks` 启动异步分析任务。
5. 后台任务创建新的数据库 session。
6. 后台任务将合同状态更新为 `ANALYZING`。
7. LangGraph 执行 `loader -> rule_check -> llm_audit -> synthesizer`。
8. 后台任务写入风险灯、分析摘要和审计日志。
9. 前端通过 TanStack Query 轮询合同详情，直到分析完成或失败。
10. 前端可请求 OnlyOffice 编辑器配置进行文档预览。

## 3. 智能体工作台流程

入口文件：

- Agent 接口：`backend/app/api/v1/endpoints/agent/agents.py`
- Agent 服务：`backend/app/services/agent/agent_service.py`
- 前端用户工作台页面：`frontend/src/pages/user-home/`
- 前端路由：`frontend/src/router/index.tsx`

流程：

1. 用户登录后进入普通用户或管理员路由。
2. 前端请求 `/api/v1/agents/workbench`。
3. 后端获取用户角色 ID。
4. 后端通过角色和部门查找用户可访问 Agent。
5. 超级管理员可访问所有启用 Agent。
6. 后端按 Agent 分组组装工作台数据。
7. 前端按分组渲染工具入口。

## 4. Agent 管理流程

管理员可维护：

- Agent 分组。
- Agent 应用。
- Agent 图标。
- 角色到 Agent 的授权。
- 部门到 Agent 的授权。

相关接口都应使用管理员权限依赖。

## 5. MCP 服务加载流程

入口文件：

- MCP 管理器：`backend/app/mcp/manager.py`
- MCP 基类：`backend/app/mcp/base.py`
- MCP 安全：`backend/app/mcp/security.py`
- MCP 服务目录：`backend/app/mcp/servers/`

流程：

1. FastAPI 生命周期启动。
2. `mcp_manager.load_servers()` 扫描 `servers/` 下的服务目录。
3. 每个服务目录需要提供 `server.py` 和 `server` 实例。
4. 管理器检查实例是否继承 `BaseMCPServer`。
5. 管理器挂载 SSE 端点和 messages 端点。
6. 请求进入 MCP 端点时先通过 `verify_mcp_auth`。

## 6. 模型配置流程

- 模型配置由系统模型模块管理。
- 业务代码不应直接写死模型名称、端点和密钥。
- Agent 节点需要模型时，应通过模型工厂或服务层读取配置。
- 模型调用失败时应有日志、状态更新和降级策略。

## 7. FineReport AI 报表生成流程

历史任务与自驱进化第一版补充：
- `fr_ai_report_task` 记录单次生成快照，并通过 `conversation_id`、`parent_task_id`、`revision_no` 串联同一报表会话内的多轮修订。
- `fr_ai_report_conversation` 记录会话标题、所属用户、最新任务、状态和摘要，前端可通过历史任务列表恢复旧任务继续调整。
- `fr_ai_report_feedback` 记录人工确认、需调整、补充说明等结构化反馈，作为后续经验检索和离线评估的数据来源。
- 第一版自驱进化仅沉淀历史任务和反馈，不自动改写全局 Prompt、业务规则、DSL 生成器或 CPT 生成器。

阶段化改造补充：
- 第一步入口优先使用 `POST /api/v1/fr/ai-reports/steps/sql/generate`，用户可同时提交自然语言需求、人工补充修改意见、相关表名和 Excel 模板。
- 第一步完成后，把需求文本、来源表名、Excel 分析、需求摘要、SQL、SQL 校验结果和日志写回同一个任务记录，供人工回看和后续步骤接力。
- 第二步入口使用 `POST /api/v1/fr/ai-reports/steps/dsl/generate`，基于同一任务的第一步产物继续生成 ReportDSL，并写回 `fr_ai_report_task.report_dsl`；前端预览直接基于 DSL 布局和 SQL 样例数据渲染，不借助 FineReport 预览。
- 第二步可携带 `dsl_feedback` 重生成 DSL，用于人工指出版式调整；例如“涨跌只保留最新一天，单独一行，放在市场下面、价格列表上面”会沉淀为 `layout.designHints.specialRows.latest_change_row`，由前端 DSL 预览按最新日期涨跌单行渲染。
- 第三步入口使用 `POST /api/v1/fr/ai-reports/steps/cpt/generate`，基于同一任务的 ReportDSL 确定性生成 CPT、写入 `reportlets/AI生成报表/` 专用预览目录并返回 FineReport 预览地址。
- 第三步当前只做专用目录预览，不做正式 reportlets 复制或覆盖；对接细节见 `docs/fr-ai-report-third-step.md`。MinIO 对象路径固定为 `webroot/APP/reportlets/AI生成报表/{task_id}/report.cpt`，FineReport 预览 `viewlet` 使用 `AI生成报表/{task_id}/report.cpt`。

入口文件：
- 后端接口：`backend/app/api/v1/endpoints/agent/fr_report.py`
- 编排服务：`backend/app/services/agent/fr_report/report_generation_service.py`
- ReportDSL：`backend/app/schemas/agent/fr_report/report_dsl.py`
- 任务表：`backend/app/models/agent/fr_report/report_task.py`
- 真实报表结构读取：`backend/app/services/agent/fr_report/report_file_service.py`
- 前端设计器副驾驶：`frontend/src/features/fr-ai-report/pages/FrAiReportChatPage.tsx`

流程：
1. 用户通过 `POST /api/v1/fr/ai-reports/generate` 上传 Excel 或填写自然语言需求。
2. `ExcelAnalyzer` 读取 Excel，识别 sheet、表头、样例行、字段类型和字段角色。
3. `RequirementAgent` 通过 `LLMFactory` 基于需求和 Excel 分析输出结构化需求摘要，失败时使用规则兜底。
4. 如果用户只提供 SQL Server 单表或多表表名，`SqlServerQueryService` 先查询 `INFORMATION_SCHEMA.COLUMNS` 获取真实字段结构并推断字段类型/角色；多表场景会生成表别名、字段来源和可推断的 `joinHints`，无法明确识别关联关系时返回 warning，提示用户在需求中补充 JOIN 条件。
5. `DataModelAgent` 通过 `LLMFactory` 在未提供真实表结构时设计逻辑表结构和建表 SQL，并标记 `dataSourceStatus=designed_not_verified`；如果查询到真实表结构则标记为 `provided`。
6. `SqlReActAgent` 通过 `LLMFactory` 基于真实表结构、SQL Server TOP 样例数据和 Excel 模板摘要生成查询 SQL，SQL 参数必须使用 `${parameter}` 绑定；遇到城市、市场、区域等 Excel 横向表头时，优先保持长表 SQL，让 ReportDSL/FineReport 横向扩展负责列展开。
7. `SqlServerQueryService` 对生成 SQL 做只读预执行校验，仅允许 `SELECT/WITH`，禁止 DDL/DML/存储过程/多语句，并返回字段、样例行、错误和警告；执行失败时，`SqlReActAgent` 会带着错误和样例数据继续修复，最多迭代 3 轮。
7. `ReportDesignerAgent` 通过 `LLMFactory` 只生成 ReportDSL，不允许输出 CPT/XML；当前阶段仅生成表格类 DSL，不生成柱状图、折线图、饼图等图表型 DSL。ReportDSL 可通过 `layout.columnGroupFields`、`layout.valueFields` 和 `layout.horizontalExpansion` 表达 FineReport 设计器横向扩展；分步骤第二步不生成 CPT，也不调用 FineReport 预览。
8. `DslValidator` 校验 DSL 完整性、字段一致性、参数绑定、字段类型、格式和聚合规则。
9. `CptGenerator` 以确定性程序生成 FineReport `.cpt` 文件。
10. `MinIOStagingService` 通过帆软专用 `FrMinIOService` 将 CPT、DSL、SQL、建表 SQL 和生成日志写入 `webroot/APP/reportlets/AI生成报表/{task_id}/`，不得复用平台通用文件 MinIO。
11. `PreviewValidator` 调用 FineReport 预览 URL，返回 `previewUrl`、`errors` 和 `warnings`。
12. `publish` 接口当前只标记任务已发布，仍保留在 staging，不直接写正式 reportlets。

真实报表设计器副驾驶补充：
1. 前端进入 `/fr-ai-reports` 后通过 `GET /api/v1/fr/ai-reports/files` 读取当前用户可见的 MinIO 报表文件树。
2. 选择报表后通过 `GET /api/v1/fr/ai-reports/files/structure` 在线读取结构；后端只在内存中解析 CPT/FRM，返回数据集、SQL 片段、结构摘要和 `FrReportDocument`，不返回完整 XML 原文。
3. 前端根据 `FrReportDocument.document.sheets[0]` 渲染类帆软网格，支持真实单元格文本、合并区域、基础样式和选中态；右侧属性面板展示当前单元格坐标、合并跨度、字段绑定、样式摘要和原始节点路径。
4. 当前画布预览是平台结构预览，不等同于 FineReport 运行时预览；后续 AI 修改和写回前仍必须走快照、hash 检测和确定性写回。

## 8. Insight 市场洞察流程

入口文件：

- 前端入口：`frontend/src/app/insight/`
- 前端 API：`frontend/src/app/insight/api/client.ts`
- 后端接口：`backend/app/api/v1/endpoints/agent/insight/router.py`
- 数据源服务：`backend/app/services/agent/insight/data_source_service.py`
- 采集服务：`backend/app/services/agent/insight/crawler/`
- 情报服务：`backend/app/services/agent/insight/intelligence_service.py`
- 报告服务：`backend/app/services/agent/insight/report_service.py`
- P0 验收脚本：`backend/scripts/insight_p0_acceptance.py`
- P1 报告测试脚本：`backend/scripts/insight_p1_report_smoke.py`
- 方案计划：`docs/solution-plans/市场洞察/市场洞察平台开发计划.md`

流程：

1. 用户在 `/insight/data-sources` 维护数据源，配置来源类型、独立搜索关键词、抓取上限、排除词、LLM 后处理提示词和可选 `company_id`。
2. 点击测试或后续调度触发数据源执行，后端按关键词逐个搜索；百度资讯、博查资讯和通用网页搜索各自返回候选 URL。
3. 搜索阶段只做 URL 归一、同 URL 去重、排除词和数量保护，不默认用 LLM 拦截搜索结果。
4. URL 进入 Firecrawl 正文抓取，正文清洗后写入 `insight_crawl_result`，并记录命中 URL、抓取成功、抓取失败和候选生成明细到 `insight_task.output_payload`。
5. 候选生成阶段先做正文质量评分、正文指纹/相似候选去重和质量标签，再调用 LLM 生成摘要、主题类型、情报类型、标签和置信度；模型失败时使用规则摘要兜底。情报类型必须使用中文业务词，历史英文枚举需要在服务层和展示层兜底映射。
6. 文章发布时间优先来自搜索结果发布时间，其次来自 Firecrawl 元数据、正文/标题中的中文日期；无法可靠解析时保持为空，前端显示“发布时间未知 · 抓取时间”，不得把抓取时间伪装成文章发布时间。
7. 企业归因优先使用数据源绑定的 `company_id`，其次按 `InsightCompany.name`、`short_name` 和 `profile_json.aliases` 在标题/正文中匹配；候选和正式情报都保留 `company_id`，供 P1 企业档案聚合。
8. P1 企业档案通过 `GET/POST /api/v1/insight/companies` 和 `GET/PUT /api/v1/insight/companies/{company_id}` 管理企业主数据；企业详情聚合关联数据源、正式情报时间线、情报类型分布和候选/正式情报标签。
9. 情报中心以一条 URL 一条资讯的卡片流展示候选和正式情报，标题和原文按钮都可跳转来源链接；候选可通过、驳回或忽略，通过后生成正式情报和来源证据。
10. 正式情报列表和详情页可加入收藏、稍后看、隐藏或 `report_material` 报告素材池；P1 报告草稿优先读取 `report_material` 素材，并保留原文链接和来源证据。
10.1. 数据源可配置采集后的自动处理策略：`auto_review_mode` 默认为关闭，可设置高置信度自动通过或全部自动通过；可通过 `auto_review_min_confidence`、`auto_review_required_tags` 和 `auto_review_intelligence_types` 约束自动通过范围；`auto_add_to_report_pool` 开启后会把自动通过的正式情报加入 `report_material` 素材池，并可写入 `auto_report_folder`。自动操作必须复用候选审核和情报池服务，写入审核记录，不能绕过正式情报和来源证据链路。
11. 报告中心通过 `GET /api/v1/insight/reports/templates` 获取“模板市场 + 当前用户个人模板”，通过 `POST /api/v1/insight/reports/templates`、`PUT /api/v1/insight/reports/templates/{template_id}` 和 `DELETE /api/v1/insight/reports/templates/{template_id}` 管理个人模板；自定义模板会保存模板名、说明、报告类型、默认 Prompt 和章节结构。`POST /api/v1/insight/reports/templates/upload` 支持上传 `.docx` / `.xlsx` 模板，后端解析 Word 标题、段落、表格或 Excel Sheet、字段、样例行，转为 `sections_json`、`structure_json` 和默认 Prompt 后保存为个人模板。模板新增 `template_kind`、`style_code`、`export_formats`、`market_status`、`market_category`、`market_description`、`cloned_from_template_id`、`visibility_scope` 等字段：内置 HTML 风格模板默认进入市场，个人模板默认仅本人可见；用户可通过 `POST /api/v1/insight/reports/templates/{template_id}/publish` 发布到市场，也可通过 `POST /api/v1/insight/reports/templates/{template_code}/clone` 复制市场模板为自己的模板后再调整章节、Prompt、数据范围和导出格式。报告生成通过 `POST /api/v1/insight/reports/generate` 生成草稿，生成请求可携带 `template_code`，并可按 `company_ids`、`data_source_ids`、`intelligence_ids`、`folder_name` 和 `max_materials` 控制素材范围。后端写入 `insight_report`、`insight_report_material`、`insight_report_version` 和 `insight_task`，并在 `content_json` 中保留模板编码和模板名称。
12. 报告中心通过 `GET /api/v1/insight/reports/preference` 和 `PUT /api/v1/insight/reports/preference` 管理当前用户的报告生成偏好；偏好保存默认模板、默认报告类型、默认素材池、素材上限、写作立场、报告深度、引用方式、是否包含风险提醒、机会建议、后续问题和附加 Prompt。生成报告时后端会读取用户偏好并补充到生成请求中，前端也可显式将偏好应用到生成栏。
13. 报告生成阶段通过 `LLMFactory.safe_invoke(..., capability="complex-reasoning", json_mode=True)` 优先调用复杂推理模型，内部按深度研究方式做分组、交叉验证、风险机会判断和证据缺口反思；输出需要包含可直接交付的章节正文 `chapters`、执行摘要、结论建议和引用元数据。报告默认面向客户经营洞察，测试企业按我们的客户或潜在客户处理，风险表达应服务于客户维护、销售跟进、方案匹配和合作机会识别，避免第三方投研式唱空或竞品攻击口吻。模型不可用或 JSON 解析失败时使用规则兜底，但仍保留素材引用。
14. 报告素材引用必须保留 `intelligence_id`、来源标题、原文 URL 和引用摘要，前端 `/insight/reports` 采用“左侧报告历史 + 顶部紧凑生成栏 + 中间 Word 式报告纸张”的阅读器结构。正文只展示标题、摘要、章节段落、结论和参考资料；证据链、引用摘要和原文链接通过正文上标悬浮小窗展示，悬浮窗需要允许鼠标移入并点击原文，鼠标离开后自然消失，避免把研究过程或证据表直接铺在报告正文里。报告正文支持进入编辑模式，人工修改标题、摘要、章节段落和结论后调用 `PUT /api/v1/insight/reports/{report_id}` 保存，并写入新的 `insight_report_version` 版本快照。
15. 报告详情 `GET /api/v1/insight/reports/{report_id}` 会基于当前报告引用素材实时聚合 `charts`，第一版包含企业与主题分布、情报类型分布、来源渠道占比、素材发布时间趋势、机会风险信号和高频标签。图表只能使用已经进入报告的素材，不额外扩大查询范围；前端在 Word 式报告正文的“附录：数据图表”展示，不把图表当作正文观点替代证据引用。
16. 权限过滤必须在后端完成，正式情报列表、首页看板、详情接口、数据源列表、报告列表、报告详情、报告素材选择、模板列表和企业档案列表/详情都不能先返回全量再由前端隐藏。数据源、报告和模板保留 `owner_user_id`、`owner_dept_id`、`visibility_scope`，企业档案至少保留 `owner_user_id`，并统一复用 `InsightPermissionService.visibility_filter_for_user` 解析 owner、public、用户、角色、部门和全员授权规则；授权接口统一使用 `GET/POST /api/v1/insight/permissions/{target_type}/{target_id}` 和 `DELETE /api/v1/insight/permissions/rules/{rule_id}`。企业微信报告推送、团队数据源协作和企业档案共享都必须先复用该权限结果，再决定是否推送或展示。
17. P2-1 周期采集使用 Insight 内置生产级调度器，不再按 demo 型显式扫描方案推进。数据源通过 `fetch_frequency`、`schedule_enabled`、`next_run_time`、`last_schedule_status`、`last_schedule_message`、`consecutive_failure_count`、`last_failure_time` 和 `auto_paused_reason` 表达周期状态；FastAPI 生命周期可按 `INSIGHT_SCHEDULER_ENABLED` 自动启动常驻调度器，调度器按 `INSIGHT_SCHEDULER_INTERVAL_SECONDS` 扫描到期数据源，并按 `INSIGHT_SCHEDULER_BATCH_LIMIT` 分批执行。后端调度接口包括 `GET /api/v1/insight/scheduler/status`、`POST /api/v1/insight/scheduler/run-once`、`/start` 和 `/stop`；每轮扫描写入 `scheduler_tick` 任务日志，并通过 PostgreSQL advisory lock 防止多实例重复执行。数据源连续失败达到 `INSIGHT_SCHEDULER_FAILURE_PAUSE_THRESHOLD` 后自动暂停周期采集并保留暂停原因，人工可通过 `POST /api/v1/insight/data-sources/{data_source_id}/schedule/retry` 将单个数据源加入下一轮调度。`POST /api/v1/insight/data-sources/schedule/run-due` 仅作为兼容入口保留，前端主入口应使用调度器接口。
18. P0 封板验收前先调用 `POST /api/v1/insight/data-sources/tasks/cleanup-stale` 或服务方法清理超时 running/pending 任务，再运行 `uv run python scripts/insight_p0_acceptance.py` 检查数据源、任务、抓取结果、候选情报、正式情报和遗留任务状态；P1 封板验收运行 `uv run python scripts/insight_p1_acceptance.py`，只读检查企业档案、数据源、情报、报告素材池、报告、报告引用和遗留任务状态；P1 报告生成冒烟可运行 `uv run python scripts/insight_p1_report_smoke.py` 基于真实素材生成测试报告。
19. Insight 视觉统一由 `InsightLayout`、`InsightHeader`、`InsightSidebar` 和 `InsightThemeScope` 承载。侧边栏、头部固定在视口内，页面主内容独立滚动；左侧导航下半部分使用品牌插画背景，避免临时色块。后续新增页面应优先复用全局布局节奏和 Shadcn/ui 基础组件，再做页面局部信息结构。
20. 企业微信推送通过 `insight_notification` 记录报告或正式情报的推送任务，接口为 `GET/POST /api/v1/insight/notifications` 和 `POST /api/v1/insight/notifications/{notification_id}/retry`。创建或重试推送前必须先按当前用户读取目标报告或情报详情，复用后端权限校验，避免用户推送自己无权访问的内容；推送记录保留 `target_type`、`target_id`、目标标题、接收人结构、推送内容、权限校验状态、发送状态、重试次数和错误信息。真实发送由 `INSIGHT_WECOM_SEND_ENABLED` 控制，默认关闭并写入 `sent_mock`；开启后通过企业微信 `gettoken` 和 `message/send` 发送文本消息，失败写入 `failed` 并允许人工重试。接收人映射优先使用平台用户 `employee_id` 工号，部门、角色、岗位会展开到有效用户工号，全员使用 `@all`。

### 8.1 本轮补充约束

- 候选情报继承关联采集结果的数据源权限：候选列表必须按关联 `InsightCrawlResult.data_source_id` 对应的 `data_source` view 权限过滤；没有数据源的手动候选仅允许对应采集任务创建人访问。
- 候选审核动作必须强于只读权限：转正、驳回、忽略必须按关联数据源 edit/owner 权限校验，view 用户只能查看候选，不能执行审核动作。
- 直接采集入口同样必须校验数据源权限：`/api/v1/insight/crawler/manual-url` 和 `/api/v1/insight/crawler/search-discovery` 如果携带 `data_source_id`，后端必须先校验当前用户对该数据源有 edit/owner 权限，再创建任务、采集结果或候选情报。
- 手动抓取、搜索发现、采集结果和候选情报创建时需要写入 `create_by` / `update_by`，便于审计和无数据源候选的访问归属判断。
- 数据源配置字段必须在保存和执行时保持一致：`include_keywords`、`exclude_keywords`、`enable_llm_filter`、`filter_prompt`、`max_results` 和 `crawl_top_n` 等字段不得只存在于表单；启用网页类数据源必须有 URL，启用周期搜索类数据源必须有独立关键词，启用 LLM 筛选必须有筛选提示词。
- 候选审核列表必须返回并展示候选质量解释：后端至少返回 `quality_score`、`quality_issues` 和 `quality_auto_ignore`，前端需要让审核人看到正文过短、疑似重复、建议忽略等原因，避免低质量候选只以普通置信度卡片展示。
- 正式情报维护必须复用统一权限口径：owner、review_user 或显式 intelligence edit/owner 授权可编辑正式情报和补充来源，view 授权只能查看；补充来源至少需要 URL、标题、摘录或文件路径之一，引用 `data_source_id` 时还必须对该数据源有 edit/owner 权限。
- 用户情报池 `pool_type` 必须限定为 `favorite`、`later`、`hidden`、`report_material`；报告生成按素材池取数时只能读取当前用户 `report_material` 且匹配目标 `folder_name` 的素材，`favorite`、`later`、`hidden` 和其他素材文件夹不得污染报告素材范围。
- 阶段二主链路烟测使用 `uv run python scripts/insight_main_flow_smoke.py`，覆盖数据源 view/edit 差异、数据源字段保存与错误校验、候选质量解释、候选转正、正式情报编辑、来源证据追踪、素材池隔离、报告草稿和无权报告访问阻断。
- 调度器状态接口必须暴露生产配置健康信息：`/api/v1/insight/scheduler/status` 至少返回 `config_health`、`config_warnings`、`config_recommendations`、`batch_limit`、`failure_pause_threshold`、`advisory_lock_id` 和 `scheduler_user_id`；当 `INSIGHT_SCHEDULER_ENABLED=false` 时必须明确提示生产环境不会自动执行周期采集。阶段三调度配置验收使用 `uv run python scripts/insight_scheduler_acceptance.py`。
- 到期任务自动执行验收使用 `uv run python scripts/insight_scheduler_due_acceptance.py`；脚本必须创建临时到期源并 mock 外部采集执行，避免真实搜索、Firecrawl 或业务数据源被验收脚本误触发；验收后需要软删除临时用户、数据源和 `scheduler_tick` 任务。
- 多实例互斥验收使用 `uv run python scripts/insight_scheduler_lock_acceptance.py`；脚本必须预先持有同一个 PostgreSQL advisory lock，再触发 `run_once`，确认调度器返回 skipped、不执行数据源、不创建 `scheduler_tick` 任务，并释放锁。
- 连续失败自动暂停验收使用 `uv run python scripts/insight_scheduler_failure_pause_acceptance.py`；脚本必须创建临时到期源并 mock 执行器抛错，将失败次数推到 `INSIGHT_SCHEDULER_FAILURE_PAUSE_THRESHOLD`，确认数据源 `schedule_enabled=false`、`last_schedule_status=paused`、写入 `last_failure_time` 和 `auto_paused_reason`，并软删除临时用户、数据源和 `scheduler_tick` 任务。
- 单源重试和遗留任务清理验收使用 `uv run python scripts/insight_scheduler_retry_cleanup_acceptance.py`；脚本必须创建已暂停临时数据源、超时 running/pending 任务和未超时任务，确认 `retry_data_source` 将暂停源恢复为 waiting 并加入下一轮调度，`cleanup_stale_tasks` 只把超时任务标记为 failed、写入 cleanup 元数据，不影响未超时任务，并软删除临时数据。
- 报告导出第一版使用 `insight_report_export` 记录导出审计，HTML 文件暂存 `backend/storage/insight_exports/` 并通过 `GET /api/v1/insight/reports/{report_id}/exports/{export_id}/download` 下载；下载前必须复用报告 view 权限校验。当前只承诺 HTML 导出，PDF、DOCX、XLSX 套版导出未完成前必须明确拒绝，不能返回伪 PDF 或伪套版文件。阶段四导出验收使用 `uv run python scripts/insight_report_export_acceptance.py`。
- 上传 DOCX/XLSX 报告模板当前只用于解析章节、段落、表格、Sheet 和字段结构，不能在 `export_formats` 中声明 docx/xlsx 已可导出；模板结构需要写入 `export_boundary.templated_export_supported=false`，前端需要显示“结构解析，套版导出待接入”等明确边界。阶段四套版边界验收使用 `uv run python scripts/insight_report_template_boundary_acceptance.py`。
- 报告导出失败必须保留 `insight_report_export.status=failed` 和可读 `error_message`，不能只在接口层抛错后丢失审计记录；失败记录不允许下载，但需要在导出列表中可见，用户重试时应创建新的导出记录并保留历史失败记录。阶段四失败重试验收使用 `uv run python scripts/insight_report_export_retry_acceptance.py`。
- 企业微信推送当前只允许 `channel=wecom`，目标类型只允许报告或正式情报；接收范围只允许 `selected` 或 `all`，`selected` 必须提供 user/dept/role/job 类型接收人及平台 ID、名称或工号之一。企业微信配置项为 `INSIGHT_WECOM_SEND_ENABLED`、`INSIGHT_WECOM_CORP_ID`、`INSIGHT_WECOM_AGENT_ID`、`INSIGHT_WECOM_SECRET`、`INSIGHT_WECOM_BASE_URL`、`INSIGHT_WECOM_TIMEOUT_SECONDS`、`INSIGHT_WECOM_RETRY_MAX_ATTEMPTS` 和 `INSIGHT_PUBLIC_BASE_URL`，密钥不得硬编码。配置 `INSIGHT_PUBLIC_BASE_URL` 后，报告/情报相对路径会拼成绝对地址并优先发送企业微信 `textcard` 卡片消息；未配置可跳转地址时回退为文本消息。阶段五推送验收使用 `uv run python scripts/insight_notification_acceptance.py`，脚本会用假发送器覆盖真实发送成功、失败和人工重试路径。
- 设置页状态接口为 `GET /api/v1/insight/settings/status`，仅用于只读展示采集、调度、企业微信推送、报告导出和登录态配置健康；敏感配置只能返回是否已配置，不得返回密钥、Secret 或完整敏感值。阶段六设置页验收使用 `uv run python scripts/insight_settings_acceptance.py`，需确认配置分组完整、企微卡片跳转状态可见、且响应中不暴露敏感值。
- Insight 字典接口统一位于 `/api/v1/insight/dictionaries/*`：`GET /overview` 返回标签和情报类型总览，`GET/POST /tags`、`PUT /tags/{tag_id}` 和 `POST /tags/{tag_id}/disable` 维护标签，`GET /intelligence-types` 返回内置受控情报类型。标签写操作仅管理员可用；禁用标签不得删除历史情报；情报类型当前为只读统一口径，如需在线增删类型需另建持久化类型表和审核规则。阶段六字典验收使用 `uv run python scripts/insight_dictionary_acceptance.py`。
- 质量运营基础版接口为 `GET /api/v1/insight/quality/overview`，聚合采集任务成功率、失败任务数、平均执行耗时、候选生成率、失败原因排行、候选审核通过/驳回率、AI 质量规则和数据源质量排行；前端入口为 `/insight/quality`。质量运营页只能展示真实聚合数据，图表缺数据时必须展示空状态，不得生成样例点冒充真实指标。阶段七验收使用 `uv run python scripts/insight_quality_acceptance.py`。

## 9. SAP 助手流程

入口文件：
- 前端页面：`frontend/src/features/sap-assistant/pages/SapAssistantPage.tsx`
- SAP 系统管理页：`frontend/src/pages/system/sap/SapSystemManagerPage.tsx`
- 后端接口：`backend/app/api/v1/endpoints/agent/sap_assistant.py`
- 编排服务：`backend/app/services/agent/sap_assistant/assistant_service.py`
- RFC 客户端：`backend/app/services/agent/sap_assistant/rfc_client.py`
- ABAP 示例：`docs/sap-rfc/`

流程：
1. 用户进入 `/sap-assistant`，可从历史会话列表恢复旧会话，也可新建会话并选择 SAP 系统和可选知识库。
2. 前端通过 `/api/v1/sap/assistant/chat/stream` 发起流式聊天请求。
3. 后端创建或恢复 `sap_assistant_session`，写入用户消息。
4. `SapAssistantService` 创建或恢复会话、解析 SAP 系统，并交由 `SapDeepAgentService` 使用 SAP 专用 Agent 自主规划工具调用、更新证据链和决定是否调用 `finish_investigation`；该 Agent 复用 deepagents 的摘要压缩、工具调用修复和提示缓存中间件，但不注入默认 todo、文件、shell 或 subagent 工具；历史 LangGraph 和自定义 ReAct 实现已移除。
5. `SapToolService` 调用 `SapRfcClient`，再由 SAP 侧 `ZFM_AI_*` RFC 获取事务码、源码、DDIC 或受控只读样例数据；源码类工具会完整拉取并写入缓存、前端事件、审计和数据库记录，但默认只把与用户问题相关的源码包作为工具观察交给 SAP 工具 Agent。`safe_table_read` 可暴露给 Agent，但必须经过少字段、少行、强条件的预检；`zilog_logs` 和 `latest_table_read` 完成前不得暴露。
6. 每次工具调用写入 `sap_tool_call`，证据写入 `sap_evidence_record`。

7. 如选择知识库，后端通过通用知识库服务检索片段并合并到证据链。
8. 每轮工具结果返回后，SAP 工具 Agent 决策阶段读取工具观察、证据账本、会话记忆和用户问题辅助提示，先判断问题是业务数据查询、源码/接口逻辑排查还是混合问题，再决定继续调用工具、停止回答或请求人工介入；服务层只做异常兜底和会话持久化，不再维护自定义 ReAct 工具循环。
9. 对客户、物料、供应商、发货、开票、订单、库存、采购等业务数据查询，Agent 应优先查 DDIC、字段含义、内部格式、日期范围和受控只读样例数据；除非用户明确给出事务码、程序、函数、接口、字段血缘、计算逻辑或“为什么查不到”，否则不应固定先查事务码或源码。
10. 对源码定位类问题，LLM 先使用 `program_source` / `function_source` 获取问题相关源码包，自主定位字段赋值、金额计算、取数语句和真实 `CALL FUNCTION` 链路；当源码包缺少关键上下文时，才调用 `source_full_text` 显式获取全文。
11. SAP 助手会话需要读取最近消息和证据作为下一轮上下文，不允许只保存不使用；前端通过 `/api/v1/sap/assistant/sessions` 和 `/api/v1/sap/assistant/sessions/{id}/messages` 展示历史会话。
12. 如果达到单轮最大工具步数仍未完成，回答中需要明确说明已达到自动追查上限，并提示用户可以继续追问以接着当前证据链运行。
13. 后端通过 `SapDeepAgentService` 的总结阶段生成回答；模型不可用时仅基于已有 deepagent 证据做轻量兜底。
14. 前端在主对话气泡内折叠展示执行时间线，让用户在聊天主线中看到 AI 正在做什么；右侧动态工作区不再作为 SAP 助手第一版必需界面。

安全边界：
- 平台不直连 SAP 数据库。
- SAP 系统配置不保存密码明文，只保存环境变量名。
- 生产系统业务数据只能通过 SAP 侧只读 RFC 小批量查询；`safe_table_read` 必须显式指定少量字段和高选择性 ranges 条件，禁止空字段、无条件或大行数读取。
- 调用 BAPI/RFC 或读取 SAP 表前必须注意内部格式和前导零：客户 `KUNNR`、供应商 `LIFNR` 通常 10 位，物料 `MATNR` 在 ECC 通常 18 位，销售/交货/开票凭证 `VBELN`、会计凭证 `BELNR`、采购订单 `EBELN` 通常 10 位，行项目 `POSNR` 通常 6 位；不确定时先查 DDIC 的长度和转换出口。
- 相对日期必须按服务器当前日期解释；用户只说“今年”“本月”或“5月份”且未给年份时，按当前年份/月推导，并转换为 SAP 内部日期范围 `YYYYMMDD`。
## SAP 助手状态化调查补充

- SAP 助手聊天入口固定走 `backend/app/services/agent/sap_assistant/deep_agent_service.py`。该入口按 deepagents 源码思路组装 SAP 专用 Agent，复用摘要压缩、工具调用修复和提示缓存中间件，禁用 deepagents 默认 todo、文件、shell 和 subagent 工具。
- SAP 助手的源码分析不再保留旧 LangGraph 或自定义 ReAct 循环；调查状态由 deepagent 服务维护，包括工具调用去重、证据账本、源码对象索引和预算状态。
- 当前 SAP 工具 Agent 默认源码工具为 `program_source` 和 `function_source`，完整源码进入服务层缓存、审计和前端事件，LLM 默认接收问题相关源码包；服务层负责源码缓存、审计和证据强弱标注。
- 接近工具预算或递归限制时，后端先压缩调查状态，保留已执行计划、强弱证据、缺口和剩余预算，再由 Agent 决定继续读取关键源码包、请求全文、跳过可选分支或进入总结。
- 涉及字段取值、金额计算或字段血缘的问题，只有找到可执行代码证据后才能给出确定结论。有效证据包括 `SELECT`、`LOOP`、`READ TABLE`、`CALL FUNCTION`、`PERFORM`、赋值和计算语句；注释和 `DATA/TYPES` 定义只能作为线索。
- 如果调查状态已经包含目标字段的可执行赋值或计算证据，应停止继续重复读取和检索并进入总结阶段。
- 同一源码对象的读取需要去重控制，避免在同一程序中来回读取造成 token 和时间浪费；必要时改为追踪真实 `CALL FUNCTION`、查询 DDIC、只读样例数据或整理条件补证。
 
## 泛微流程AI助手流程

1. ecode 在泛微流程发起或处理页面通过 `WeaReqTop` 钩子挂载悬浮图标。
2. 用户点击图标后，ecode 打开平台 `/weaver/assistant/embed` iframe，并通过 `postMessage` 传入 `WfForm.getBaseInfo()` 和字段白名单上下文。
3. 平台嵌入页调用 `/api/v1/weaver/ai-assistant/chat`，后端 Agent 根据用户输入和字段上下文生成结构化填单动作。
4. 用户在嵌入页确认“写入表单”后，平台向父页面发送 `WEAVER_AI_APPLY_ACTIONS`。
5. ecode 只按白名单动作调用 `WfForm.changeFieldValue()` 或 `WfForm.addDetailRow()`，不执行任意脚本，不自动提交流程。
