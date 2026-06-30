# 核心业务流程

本文件用于理解和维护主要业务链路。新增或重构核心流程时，需要同步更新本文件。

## 1. 登录鉴权流程

入口文件：

- 前端登录页：`frontend/src/pages/auth/LoginPage.tsx`
- 前端认证状态：`frontend/src/store/useAuthStore.ts`
- 前端 API 客户端：`frontend/src/api/client.ts`
- 后端登录接口：`backend/app/ai-api/v1/endpoints/system/login.py`
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
- 合同接口：`backend/app/ai-api/v1/endpoints/agent/contract/contracts.py`
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

- Agent 接口：`backend/app/ai-api/v1/endpoints/agent/agents.py`
- Agent 服务：`backend/app/services/agent/agent_service.py`
- 前端用户工作台页面：`frontend/src/pages/user-home/`
- 前端路由：`frontend/src/router/index.tsx`

流程：

1. 用户登录后进入普通用户或管理员路由。
2. 前端请求 `/ai-api/v1/agents/workbench`。
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
- 第一步入口优先使用 `POST /ai-api/v1/fr/ai-reports/steps/sql/generate`，用户可同时提交自然语言需求、人工补充修改意见、相关表名和 Excel 模板。
- 第一步完成后，把需求文本、来源表名、Excel 分析、需求摘要、SQL、SQL 校验结果和日志写回同一个任务记录，供人工回看和后续步骤接力。
- 第二步入口使用 `POST /ai-api/v1/fr/ai-reports/steps/dsl/generate`，基于同一任务的第一步产物继续生成 ReportDSL，并写回 `fr_ai_report_task.report_dsl`；前端预览直接基于 DSL 布局和 SQL 样例数据渲染，不借助 FineReport 预览。
- 第二步可携带 `dsl_feedback` 重生成 DSL，用于人工指出版式调整；例如“涨跌只保留最新一天，单独一行，放在市场下面、价格列表上面”会沉淀为 `layout.designHints.specialRows.latest_change_row`，由前端 DSL 预览按最新日期涨跌单行渲染。
- 第三步入口使用 `POST /ai-api/v1/fr/ai-reports/steps/cpt/generate` 或 AI 草稿 CPT 生成入口，基于同一任务的 ReportDSL/快照确定性生成 CPT；写入用户指定 `webroot/APP/reportlets/` 子路径前必须保存平台结构版本和 CPT 文件版本，并通过 hash/lastModified 检查 FineReport 设计器外部修改。
- 当目标是已有真实 CPT 时，AI 草稿 CPT 生成必须以当前 MinIO 中的原始 CPT/XML 为基底做增量补丁；结构快照只作为参数、SQL、样式等修改意图来源，不能重建整份 `<WorkBook>` 后覆盖原文件。
- 第三步不再固定只能进入 `AI生成报表/{task_id}` 预览目录；默认仍可使用专用目录作为兜底，但用户指定目标路径时，版本库应在目标目录下按 `版本库/<报表名>/v0001/` 结构归档，对接细节见 `docs/fr-ai-report-third-step.md`。
- 新建报表入口先通过 `POST /ai-api/v1/fr/ai-reports/empty/create` 创建空白 CPT、写入目标目录并生成结构版本和文件版本。随后用户选中该空报表，在右侧小驰侧边栏继续通过 `POST /ai-api/v1/fr/ai-reports/agent/chat` 发送消息、上下文和资料；后端先用大模型语义路由判断本轮是普通沟通、修改当前报表、开始生成还是保存 CPT，模型不可用时才走保守规则兜底，再按受控 ReAct 外壳把需求预检、读取真实表结构/预览数据、SQL ReAct、ReportDSL 生成和 CPT 版本保存作为白名单工具串联。用户明确“开始生成”时，未完全确认的问题可转为假设和风险提示继续执行，生成后通过后续聊天修订。
- 小驰主回答应像工程副驾驶一样基于当前上下文自然回应，避免固定模板腔；工具执行过程通过事件折叠展示，不能把执行轨迹、风险提示或流程说明当成每轮聊天主文案。
- 小驰 ReAct 外壳的第一版不暴露模型原始思考，而是把执行过程转成可读事件：上下文预算、工具开始、工具结果、方案草图、草稿就绪、SQL 就绪、DSL 就绪、CPT 就绪和风险提示。前端默认折叠执行轨迹，用户需要时再展开。
- 小驰能力中心通过 `agent/capabilities` 展示可用工具、风险等级、确认要求、系统技能和上下文/token 策略。用户可启用系统技能或填写个人开发习惯，这些内容仅作为上下文偏好参与下一轮对话，不改变后端工具白名单和安全确认门。
- 记忆系统按“三层”推进：当前轮上下文包用于工具执行，任务/版本/反馈用于可追溯历史，后续经验检索用于相似报表复用；不得把完整历史对话、完整 CPT/XML 或大批样例数据直接塞进模型。已确认应用的修改项只进入版本和审计历史，不再作为下一轮修改参考上下文。
- 已有 CPT 修改链路只采用直接 XML Patch：模型按需读取相关 CPT 片段和轻量 XML 索引后返回可回写 XML 片段或完整 CPT，版本控制负责写入、归档、冲突处理和预览验证；历史成功修改只做按需经验检索，不直接进入系统提示词；中高风险修改需要在前端提示用户确认。

入口文件：
- 后端接口：`backend/app/ai-api/v1/endpoints/agent/fr_report.py`
- 编排服务：`backend/app/services/agent/fr_report/report_generation_service.py`
- ReportDSL：`backend/app/schemas/agent/fr_report/report_dsl.py`
- 任务表：`backend/app/models/agent/fr_report/report_task.py`
- 真实报表结构读取：`backend/app/services/agent/fr_report/report_file_service.py`
- 前端设计器副驾驶：`frontend/src/features/fr-ai-report/pages/FrAiReportChatPage.tsx`

流程：
1. 用户通过 `POST /ai-api/v1/fr/ai-reports/generate` 上传 Excel 或填写自然语言需求。
2. `ExcelAnalyzer` 读取 Excel，识别 sheet、表头、样例行、字段类型和字段角色。
   - 解析前先裁剪真实有效区域，避免样式尾列或空尾列污染模型上下文。
   - 解析结果需要包含合并表头、`effectiveRange`、公式规则和公式/说明冲突；冲突交由 Agent 追问或提示风险。
3. `RequirementAgent` 通过 `LLMFactory` 基于需求和 Excel 分析输出结构化需求摘要，失败时使用规则兜底。
   - 对话阶段优先给用户方案草图和开始生成入口，除硬条件缺失外不应因追问阻断。
   - 用户明确要求开始执行时，未确认项转为假设、风险和后续可调整项。
4. 如果用户只提供 SQL Server 单表或多表表名，`SqlServerQueryService` 先查询 `INFORMATION_SCHEMA.COLUMNS` 获取真实字段结构并推断字段类型/角色；多表场景会生成表别名、字段来源和可推断的 `joinHints`，无法明确识别关联关系时返回 warning，提示用户在需求中补充 JOIN 条件。
   - 中文业务来源名称不等于真实库表名；不符合数据库标识符规则的名称不得进入表结构读取。
5. `DataModelAgent` 通过 `LLMFactory` 在未提供真实表结构时设计逻辑表结构和建表 SQL，并标记 `dataSourceStatus=designed_not_verified`；如果查询到真实表结构则标记为 `provided`。
6. `SqlReActAgent` 通过 `LLMFactory` 基于真实表结构、SQL Server TOP 样例数据和 Excel 模板摘要生成查询 SQL，SQL 参数必须使用 `${parameter}` 绑定；遇到城市、市场、区域等 Excel 横向表头时，优先保持长表 SQL，让 ReportDSL/FineReport 横向扩展负责列展开。
7. `SqlServerQueryService` 对生成 SQL 做只读预执行校验，仅允许 `SELECT/WITH`，禁止 DDL/DML/存储过程/多语句，并返回字段、样例行、错误和警告；执行失败时，`SqlReActAgent` 会带着错误和样例数据继续修复，最多迭代 3 轮。
7. `ReportDesignerAgent` 通过 `LLMFactory` 只生成 ReportDSL，不允许输出 CPT/XML；当前阶段仅生成表格类 DSL，不生成柱状图、折线图、饼图等图表型 DSL。ReportDSL 可通过 `layout.columnGroupFields`、`layout.valueFields` 和 `layout.horizontalExpansion` 表达 FineReport 设计器横向扩展；分步骤第二步不生成 CPT，也不调用 FineReport 预览。
8. `DslValidator` 校验 DSL 完整性、字段一致性、参数绑定、字段类型、格式和聚合规则。
9. `CptGenerator` 以确定性程序生成 FineReport `.cpt` 文件。
10. CPT 写入通过帆软专用 `FrMinIOService` 和版本控制服务完成，目标路径必须位于 `FR_AI_REPORT_FILE_PREFIXES` 允许范围内；每次写入同步归档 `report.cpt`、`report.dsl.json`、`manifest.json` 和 `diff.json`，不得复用平台通用文件 MinIO。
11. `PreviewValidator` 调用 FineReport 预览 URL，返回 `previewUrl`、`errors` 和 `warnings`。
12. `publish` 或确认写入动作不得绕过版本控制；若目标 CPT 已被 FineReport 设计器修改，默认阻止覆盖，并允许“仅同步外部修改为版本”或“覆盖前自动归档当前文件”。回收站使用目标目录下 `回收站/<报表名>/<时间>/`。

附件处理补充：
- 小驰侧边栏聊天入口可接收多附件；Excel 文件进入结构化解析，图片、Word、文本等非 Excel 附件暂作为需求资料保留并返回提示，不中断对话。
- 多附件场景下优先选择 Excel 做结构化分析，其余附件保留在事件上下文中，后续可扩展 OCR、文档摘要和多 Excel 合并事实包。

真实报表设计器副驾驶补充：
1. 前端进入 `/fr-ai-reports` 后通过 `GET /ai-api/v1/fr/ai-reports/files` 读取当前用户可见的 MinIO 报表文件树。
2. 选择报表后通过 `GET /ai-api/v1/fr/ai-reports/files/structure` 在线读取结构；后端只在内存中解析 CPT/FRM，返回数据集、SQL 片段、结构摘要和 `FrReportDocument`，不返回完整 XML 原文。
3. 前端根据 `FrReportDocument.document.sheets[0]` 渲染类帆软网格，支持真实单元格文本、合并区域、基础样式和选中态；右侧属性面板展示当前单元格坐标、合并跨度、字段绑定、样式摘要和原始节点路径。
4. 当前画布预览是平台结构预览，不等同于 FineReport 运行时预览；后续 AI 修改和写回前仍必须走快照、hash 检测和确定性写回。

## 8. Insight 市场洞察流程

入口文件：

- 前端入口：`frontend/src/app/insight/`
- 前端 API：`frontend/src/app/insight/api/client.ts`
- 后端接口：`backend/app/ai-api/v1/endpoints/agent/insight/router.py`
- 监测配置服务：`backend/app/services/agent/insight/monitor_config_service.py`
- 监测配置执行服务：`backend/app/services/agent/insight/monitor_execution_service.py`
- 监测配置服务：`backend/app/services/agent/insight/monitor_config_service.py`
- 采集服务：`backend/app/services/agent/insight/crawler/`
- 情报服务：`backend/app/services/agent/insight/intelligence_service.py`
- 报告服务：`backend/app/services/agent/insight/report_service.py`
- P0 验收脚本：`backend/scripts/insight_p0_acceptance.py`
- P1 报告测试脚本：`backend/scripts/insight_p1_report_smoke.py`
- 方案计划：`docs/solution-plans/市场洞察/市场洞察平台开发计划.md`

流程：

1. 管理员在 `/insight/settings` 维护渠道库；普通业务用户在 `/insight/monitoring` 维护监测配置。旧 `insight_data_source` 概念已废除，不再作为用户配置、执行源维护或调度主表；历史表仅为旧任务、抓取结果和正式情报外键兼容保留。
2. 监测配置表达“监测谁、关系是什么、看哪些模块、用什么 AI 口径和频率”。调度器直接扫描 `insight_monitor_config`，运行时按监测配置动态展开执行，不把这些执行单元持久化为成百上千条用户可维护数据源。
3. 旧版零散数据源由启动迁移汇总到监测配置：旧执行源上的渠道覆盖、最近成功时间、下次执行时间和失败状态被收回到 `insight_monitor_config`，随后旧 `insight_data_source` 统一软删除、停用调度。
4. 点击测试或后续调度触发监测配置执行时，必须先生成“本轮采集计划”，再按计划执行渠道；渠道库只是候选能力池，不允许把监测配置与全部渠道源做笛卡尔积。当前默认发现源为百度资讯和博查搜索，二者是独立渠道源，各自走自己的搜索适配器；FoodDaily、食品伙伴网、粮油市场报、新蛋白、WIPO、CNIPA、东方财富等渠道源后续逐个补充对应爬取方式和脚本，未接入脚本前只标记为待接入，不允许用百度或博查代跑其他渠道。WIPO/CNIPA 属于技术专利低频专项源，不作为日常冒烟和业务演示的优先渠道。
4.1. 已迁移的预研渠道脚本统一由 `channel_adapter_service.py` 包装为正式适配器，接口形态为按关键词、时间窗和数量上限返回标准命中；脚本运行副作用、原始输出和失败快照必须落在 `backend/storage/insight_adapter_runs`，不得继续把 `data/*.json` 写回源码目录。每次适配器执行都要写 `insight_channel_adapter_run`，单个适配器失败只能影响该渠道，不能中断整轮监测配置。
5. 搜索阶段默认取近半月数据：博查适配器用接口可接受的新鲜度参数取回候选，再由搜索服务按发布时间过滤 15 天窗口；百度资讯无法强约束接口时间时，同样在搜索服务层按已解析发布时间过滤，无法可靠解析发布时间的结果保守保留。
6. 博查搜索必须按监测频率控量：每日或 Cron 每个监测对象最多 10 条，每周最多 30 条，半月及以上最多 50 条；百度资讯同一轮执行使用相同上限口径。禁止按模块、按关键词、按网站重复触发博查调用。调度执行必须遵循“百度资讯优先；百度结果不足、候选不足或低成本源失败时才调用博查”的策略，并在执行结果中返回 planned/executed/skipped/paid 调用统计。
7. 搜索阶段必须先做 URL 归一、单次结果去重、历史 URL 去重、排除词、数量保护和成本保护；历史已采集过的相同链接要在 LLM 筛选、候选生成和正文抓取前剔除，并把过滤结果写入 `insight_task.output_payload.filter_summary`。
8. 周期调度推荐 `crawl_top_n=0` 的轻量模式：不抓正文时也必须对搜索命中执行 AI 初筛，候选入库即写入摘要、标签、情感、机会点、风险点、相关性分、置信度和 `AI搜索初筛` 标签，不得只保存裸搜索摘要。
9. URL 进入 Firecrawl 正文抓取时，正文清洗后写入 `insight_crawl_result`，并记录命中 URL、抓取成功、抓取失败和候选生成明细到 `insight_task.output_payload`。
10. 正文候选生成阶段先做正文质量评分、正文指纹/相似候选去重和质量标签，再调用 LLM 生成摘要、主题类型、情报类型、标签和置信度；模型失败时使用规则摘要兜底。情报类型必须使用中文业务词，历史英文枚举需要在服务层和展示层兜底映射。
11. 文章发布时间优先来自搜索结果发布时间，其次来自 Firecrawl 元数据、正文/标题中的中文日期；无法可靠解析时保持为空，前端显示“发布时间未知 · 抓取时间”，不得把抓取时间伪装成文章发布时间。
12. 企业归因优先使用监测配置绑定的企业对象，其次兼容旧数据源绑定的 `company_id`，最后按 `InsightCompany.name`、`short_name` 和 `profile_json.aliases` 在标题/正文中匹配；候选和正式情报都保留 `company_id`，供 P1 企业档案聚合。
13. P1 企业档案通过 `GET/POST /ai-api/v1/insight/companies` 和 `GET/PUT /ai-api/v1/insight/companies/{company_id}` 管理企业主数据；企业详情聚合关联数据源、正式情报时间线、情报类型分布和候选/正式情报标签。
14. 情报中心以一条 URL 一条资讯的卡片流展示候选和正式情报，标题和原文按钮都可跳转来源链接；采集后默认进入 AI 自动评审，AI 输出 `formal`、`candidate`、`noise` 三类决策，分别对应转正式情报、保留候选线索和噪声归档。AI 自动评审正式情报阈值为 60 分，且必须有明确业务价值、受控情报类型或受控标签；低于 60 分、来源较弱或价值不清楚的内容保留候选线索。AI 自动评审必须注入我方业务画像，默认按香驰控股有限公司的大豆、玉米精深加工，功能糖、糖醇、植物蛋白、豆粕、粮油和营养健康应用场景判断业务价值；可通过 `INSIGHT_OWN_BUSINESS_PROFILE` 补充企业内部定位。AI 自动评审的情报类型必须从内置受控类型中选择，标签必须从启用的 `insight_tag` 字典中选择；模型认为缺少的标签只能进入 `suggested_new_tags`，不得直接污染正式标签体系。
15. AI 自动评审必须复用候选转正式、忽略和来源证据服务，写入 `insight_review_record`；人工按钮仅作为复核/纠偏入口，不再是主流程。
16. 只有正式情报沉淀到情报资产层；候选线索和噪声归档不得生成资产、向量和图谱。`insight_intelligence_asset` 记录正式情报结构化字段，`insight_asset_vector` 记录正式情报向量索引，`insight_graph_node` 和 `insight_graph_edge` 基于正式情报沉淀轻量知识图谱；报告、AI 助手和深度研究优先走 `/ai-api/v1/insight/assets/search` 做权限过滤后的 RAG 检索，图谱读取走 `/ai-api/v1/insight/assets/graph`。
17. 正式情报列表和详情页可加入收藏、稍后看或隐藏；正式情报一旦沉淀为资产即可被报告、AI 助手和深度研究调用，不再要求用户手工加入报告素材池。历史 `insight_report_material` 表仅作为“本次报告引用了哪些正式情报证据”的审计和导出引用清单保留。
18. 报告中心通过 `GET /ai-api/v1/insight/reports/templates` 获取“模板市场 + 当前用户个人模板”，通过 `POST /ai-api/v1/insight/reports/templates`、`PUT /ai-api/v1/insight/reports/templates/{template_id}` 和 `DELETE /ai-api/v1/insight/reports/templates/{template_id}` 管理个人模板；自定义模板会保存模板名、说明、报告类型、默认 Prompt 和章节结构。`POST /ai-api/v1/insight/reports/templates/upload` 支持上传 `.docx` / `.xlsx` 模板，后端解析 Word 标题、段落、表格或 Excel Sheet、字段、样例行，转为 `sections_json`、`structure_json` 和默认 Prompt 后保存为个人模板。模板新增 `template_kind`、`style_code`、`export_formats`、`market_status`、`market_category`、`market_description`、`cloned_from_template_id`、`visibility_scope` 等字段：内置 HTML 风格模板默认进入市场，个人模板默认仅本人可见；用户可通过 `POST /ai-api/v1/insight/reports/templates/{template_id}/publish` 发布到市场，也可通过 `POST /ai-api/v1/insight/reports/templates/{template_code}/clone` 复制市场模板为自己的模板后再调整章节、Prompt、数据范围和导出格式。报告生成通过 `POST /ai-api/v1/insight/reports/generate` 生成草稿，生成请求可携带 `template_code`，并可按主题、企业、数据源、时间范围或显式 `intelligence_ids` 限定素材范围；未显式指定情报时，后端从正式情报资产库进行 RAG 检索，结合资产结构化字段和知识图谱关系，以深度研究方式生成报告。前端当面生成报告必须优先调用 `POST /ai-api/v1/insight/reports/generate/stream` 获取 SSE 进度事件，向用户展示理解问题、查找素材、整理线索、补充关联、形成大纲、撰写正文、检查质量和保存草稿等阶段；定时计划、后台补跑和兼容脚本仍可使用普通 `generate` 接口。后端写入 `insight_report`、`insight_report_material`、`insight_report_version` 和 `insight_task`，并在 `content_json` 中保留模板编码、模板名称、素材检索摘要、研究过程和生成模式。
19. 报告中心通过 `GET /ai-api/v1/insight/reports/preference` 和 `PUT /ai-api/v1/insight/reports/preference` 管理当前用户的报告生成偏好；偏好保存默认模板、默认报告类型、默认素材池、素材上限、写作立场、报告深度、引用方式、是否包含风险提醒、机会建议、后续问题和附加 Prompt。生成报告时后端会读取用户偏好并补充到生成请求中，前端也可显式将偏好应用到生成栏。
20. 报告中心支持定时报告计划，接口为 `GET/POST/PUT/DELETE /ai-api/v1/insight/reports/subscriptions`、`POST /ai-api/v1/insight/reports/subscriptions/{subscription_id}/run` 和 `POST /ai-api/v1/insight/reports/subscriptions/run-due`。计划保存模板、报告类型、素材范围、素材上限、生成 Prompt、频率、执行时间和企业微信接收人；素材范围支持当前用户报告素材池、某个 `sys_company` 下全部企业、指定企业和指定数据源。计划到期执行时必须按计划创建者身份重新校验模板、企业、数据源和报告生成权限，生成报告后再复用企业微信通知服务创建 `insight_notification`，不能使用管理员身份绕过隔离。
21. 报告生成阶段通过 `LLMFactory.safe_invoke(..., capability="complex-reasoning", json_mode=True)` 优先调用复杂推理模型，内部按深度研究方式做分组、交叉验证、风险机会判断和证据缺口反思；输出需要包含可直接交付的章节正文 `chapters`、执行摘要、结论建议和引用元数据。报告默认面向客户经营洞察，测试企业按我们的客户或潜在客户处理，风险表达应服务于客户维护、销售跟进、方案匹配和合作机会识别，避免第三方投研式唱空或竞品攻击口吻。模型不可用或 JSON 解析失败时使用规则兜底，但仍保留素材引用。
22. 报告素材引用必须保留 `intelligence_id`、来源标题、原文 URL 和引用摘要，前端 `/insight/reports` 采用“左侧报告历史 + 顶部紧凑生成栏 + 中间 Word 式报告纸张”的阅读器结构。正文只展示标题、摘要、章节段落、结论和参考资料；证据链、引用摘要和原文链接通过正文上标悬浮小窗展示，悬浮窗需要允许鼠标移入并点击原文，鼠标离开后自然消失，避免把研究过程或证据表直接铺在报告正文里。报告正文支持进入编辑模式，人工修改标题、摘要、章节段落和结论后调用 `PUT /ai-api/v1/insight/reports/{report_id}` 保存，并写入新的 `insight_report_version` 版本快照。
23. 报告详情 `GET /ai-api/v1/insight/reports/{report_id}` 会基于当前报告引用素材实时聚合 `charts`，第一版包含企业与主题分布、情报类型分布、来源渠道占比、素材发布时间趋势、机会风险信号和高频标签。图表只能使用已经进入报告的素材，不额外扩大查询范围；前端在 Word 式报告正文的“附录：数据图表”展示，不把图表当作正文观点替代证据引用。
24. 权限过滤必须在后端完成，正式情报列表、首页看板、详情接口、数据源列表、报告列表、报告详情、报告素材选择、模板列表和企业档案列表/详情都不能先返回全量再由前端隐藏。数据源、报告和模板保留 `owner_user_id`、`owner_dept_id`、`visibility_scope`，企业档案至少保留 `owner_user_id`，并统一复用 `InsightPermissionService.visibility_filter_for_user` 解析 owner、public、用户、角色、部门和全员授权规则；授权接口统一使用 `GET/POST /ai-api/v1/insight/permissions/{target_type}/{target_id}` 和 `DELETE /ai-api/v1/insight/permissions/rules/{rule_id}`。企业微信报告推送、团队数据源协作和企业档案共享都必须先复用该权限结果，再决定是否推送或展示。
25. P2-1 周期采集使用 Insight 内置生产级调度器，不再按 demo 型显式扫描方案推进。监测配置通过 `fetch_frequency`、`schedule_enabled`、`next_run_time`、`last_schedule_status`、`last_schedule_message`、`consecutive_failure_count`、`last_failure_time` 和 `auto_paused_reason` 表达周期状态；FastAPI 生命周期可按 `INSIGHT_SCHEDULER_ENABLED` 自动启动常驻调度器，调度器按 `INSIGHT_SCHEDULER_INTERVAL_SECONDS` 扫描到期监测配置，并按 `INSIGHT_SCHEDULER_BATCH_LIMIT` 分批执行。后端调度接口包括 `GET /ai-api/v1/insight/scheduler/status`、`POST /ai-api/v1/insight/scheduler/run-once`、`/start` 和 `/stop`；每轮扫描写入 `scheduler_tick` 任务日志，并通过 PostgreSQL advisory lock 防止多实例重复执行。监测配置连续失败达到 `INSIGHT_SCHEDULER_FAILURE_PAUSE_THRESHOLD` 后自动暂停周期采集并保留暂停原因。`POST /ai-api/v1/insight/data-sources/schedule/run-due` 仅作为兼容入口保留，内部同样执行到期监测配置。
26. P0 封板验收前先调用 `POST /ai-api/v1/insight/data-sources/tasks/cleanup-stale` 或服务方法清理超时 running/pending 任务，再运行 `uv run python scripts/insight_p0_acceptance.py` 检查数据源、任务、抓取结果、候选情报、正式情报和遗留任务状态；P1 封板验收运行 `uv run python scripts/insight_p1_acceptance.py`，只读检查企业档案、数据源、情报、报告素材池、报告、报告引用和遗留任务状态；P1 报告生成冒烟可运行 `uv run python scripts/insight_p1_report_smoke.py` 基于真实素材生成测试报告。
27. Insight 视觉统一由 `InsightLayout`、`InsightSidebar` 和 `InsightThemeScope` 承载。登录后业务页不使用常驻顶层 Header，用户信息与退出入口放在侧边栏底部；页面根容器不做纵向整页滚动，滚动只放在列表、表格、详情、预览、日志等组件内部，并优先展示业务数据、筛选、列表、图表和主要操作。后续新增页面不得用占位型大标题、解释型小标题或常驻大表单挤压主信息区。
28. Insight 渠道库面向用户按监测用途分类，而不是按技术来源堆砌：企业监测包括“企业新闻、官网动态、经营财经、专利技术、电商新品”，主题监测包括“行业资讯、政策监管、技术专利、综合舆情”。`channel_type` 仍作为底层来源属性保留，页面筛选、默认渠道标签、报告和后续 RAG 召回优先使用 `applicable_scenarios` 中的监测分类。搜索发现类默认只展示“百度资讯”和“博查搜索”；其他搜索组合、网页搜索或专项源后续按测试结果逐步补充，不作为默认来源。
29. Insight 渠道源必须保留执行分级策略：`config_json.execution_policy.tier` 可为 `discovery`、`vertical`、`specialized` 或 `custom`，`cost_level` 表达低成本、普通成本或付费渠道，`trigger_mode` 表达每轮执行、质量不足补充、按频道频率执行或低频专项触发。新增渠道适配器后也必须经过 `monitor_execution_service` 的采集计划、频率判断和预算控制；不得因为适配器可用就让每个监测对象每日执行全部渠道。
29.1. 全渠道补数和模拟调度入口为 `uv run python scripts/insight_run_all_channel_adapters.py --mode backfill|simulate-daily|simulate-weekly|simulate-monthly --days 15`。脚本必须读取真实监测配置并追加香驰业务关键词，过滤“测试客户、烟测、demo”等样例对象；执行结果输出 JSON 和 Markdown 报告，统计每个渠道的成功、失败、样例 URL、候选、正式和向量化链路情况。日模拟优先食品伙伴网、FoodDaily、粮油市场报、粮信网、新蛋白等香驰业务相关渠道；周模拟再扩展饮品、食品行业、营养健康和财经类渠道；WIPO/CNIPA 等专利源放在月度或全渠道补数中验证。正式运行采用“跨网站并行、同网站串行”的受控队列：百度/博查/HTTP 适配器和 Playwright 适配器分池限流，同一渠道加锁串行，单渠道超时失败不影响整轮；大批量补数通过 `--shard-index/--shard-total` 分片跨夜完成，不要求一次性跑完所有站点。
30. 企业微信推送通过 `insight_notification` 记录报告或正式情报的推送任务，接口为 `GET/POST /ai-api/v1/insight/notifications` 和 `POST /ai-api/v1/insight/notifications/{notification_id}/retry`。创建或重试推送前必须先按当前用户读取目标报告或情报详情，复用后端权限校验，避免用户推送自己无权访问的内容；推送记录保留 `target_type`、`target_id`、目标标题、接收人结构、推送内容、权限校验状态、发送状态、重试次数和错误信息。真实发送由 `INSIGHT_WECOM_SEND_ENABLED` 控制，默认关闭并写入 `sent_mock`；开启后通过企业微信 `gettoken` 和 `message/send` 发送文本消息，失败写入 `failed` 并允许人工重试。接收人映射优先使用平台用户 `employee_id` 工号，部门、角色、岗位会展开到有效用户工号，全员使用 `@all`。

### 8.1 本轮补充约束

- 候选情报继承关联采集结果的数据源权限：候选列表必须按关联 `InsightCrawlResult.data_source_id` 对应的 `data_source` view 权限过滤；没有数据源的手动候选仅允许对应采集任务创建人访问。
- 候选审核动作必须强于只读权限：转正、驳回、忽略必须按关联数据源 edit/owner 权限校验，view 用户只能查看候选，不能执行审核动作。
- 直接采集入口同样必须校验数据源权限：`/ai-api/v1/insight/crawler/manual-url` 和 `/ai-api/v1/insight/crawler/search-discovery` 如果携带 `data_source_id`，后端必须先校验当前用户对该数据源有 edit/owner 权限，再创建任务、采集结果或候选情报。
- 手动抓取、搜索发现、采集结果和候选情报创建时需要写入 `create_by` / `update_by`，便于审计和无数据源候选的访问归属判断。
- 数据源配置字段必须在保存和执行时保持一致：`include_keywords`、`exclude_keywords`、`enable_llm_filter`、`filter_prompt`、`max_results` 和 `crawl_top_n` 等字段不得只存在于表单；启用网页类数据源必须有 URL，启用周期搜索类数据源必须有独立关键词，启用 LLM 筛选必须有筛选提示词。
- 候选审核列表必须返回并展示候选质量解释：后端至少返回 `quality_score`、`quality_issues` 和 `quality_auto_ignore`，前端需要让审核人看到正文过短、疑似重复、建议忽略等原因，避免低质量候选只以普通置信度卡片展示。
- 正式情报维护必须复用统一权限口径：owner、review_user 或显式 intelligence edit/owner 授权可编辑正式情报和补充来源，view 授权只能查看；补充来源至少需要 URL、标题、摘录或文件路径之一，引用 `data_source_id` 时还必须对该数据源有 edit/owner 权限。
- 用户情报池 `pool_type` 必须限定为 `favorite`、`later`、`hidden`、`report_material`；报告生成按素材池取数时只能读取当前用户 `report_material` 且匹配目标 `folder_name` 的素材，`favorite`、`later`、`hidden` 和其他素材文件夹不得污染报告素材范围。
- 阶段二主链路烟测使用 `uv run python scripts/insight_main_flow_smoke.py`，覆盖数据源 view/edit 差异、数据源字段保存与错误校验、候选质量解释、候选转正、正式情报编辑、来源证据追踪、素材池隔离、报告草稿和无权报告访问阻断。
- 调度器状态接口必须暴露生产配置健康信息：`/ai-api/v1/insight/scheduler/status` 至少返回 `config_health`、`config_warnings`、`config_recommendations`、`batch_limit`、`failure_pause_threshold`、`advisory_lock_id` 和 `scheduler_user_id`；当 `INSIGHT_SCHEDULER_ENABLED=false` 时必须明确提示生产环境不会自动执行周期采集。阶段三调度配置验收使用 `uv run python scripts/insight_scheduler_acceptance.py`。
- 到期任务自动执行验收使用 `uv run python scripts/insight_scheduler_due_acceptance.py`；脚本必须创建临时到期源并 mock 外部采集执行，避免真实搜索、Firecrawl 或业务数据源被验收脚本误触发；验收后需要软删除临时用户、数据源和 `scheduler_tick` 任务。
- 多实例互斥验收使用 `uv run python scripts/insight_scheduler_lock_acceptance.py`；脚本必须预先持有同一个 PostgreSQL advisory lock，再触发 `run_once`，确认调度器返回 skipped、不执行数据源、不创建 `scheduler_tick` 任务，并释放锁。
- 连续失败自动暂停验收使用 `uv run python scripts/insight_scheduler_failure_pause_acceptance.py`；脚本必须创建临时到期源并 mock 执行器抛错，将失败次数推到 `INSIGHT_SCHEDULER_FAILURE_PAUSE_THRESHOLD`，确认数据源 `schedule_enabled=false`、`last_schedule_status=paused`、写入 `last_failure_time` 和 `auto_paused_reason`，并软删除临时用户、数据源和 `scheduler_tick` 任务。
- 单源重试和遗留任务清理验收使用 `uv run python scripts/insight_scheduler_retry_cleanup_acceptance.py`；脚本必须创建已暂停临时数据源、超时 running/pending 任务和未超时任务，确认 `retry_data_source` 将暂停源恢复为 waiting 并加入下一轮调度，`cleanup_stale_tasks` 只把超时任务标记为 failed、写入 cleanup 元数据，不影响未超时任务，并软删除临时数据。
- 报告导出第一版使用 `insight_report_export` 记录导出审计，HTML 文件暂存 `backend/storage/insight_exports/` 并通过 `GET /ai-api/v1/insight/reports/{report_id}/exports/{export_id}/download` 下载；下载前必须复用报告 view 权限校验。当前只承诺 HTML 导出，PDF、DOCX、XLSX 套版导出未完成前必须明确拒绝，不能返回伪 PDF 或伪套版文件。阶段四导出验收使用 `uv run python scripts/insight_report_export_acceptance.py`。
- 上传 DOCX/XLSX 报告模板当前只用于解析章节、段落、表格、Sheet 和字段结构，不能在 `export_formats` 中声明 docx/xlsx 已可导出；模板结构需要写入 `export_boundary.templated_export_supported=false`，前端需要显示“结构解析，套版导出待接入”等明确边界。阶段四套版边界验收使用 `uv run python scripts/insight_report_template_boundary_acceptance.py`。
- 报告导出失败必须保留 `insight_report_export.status=failed` 和可读 `error_message`，不能只在接口层抛错后丢失审计记录；失败记录不允许下载，但需要在导出列表中可见，用户重试时应创建新的导出记录并保留历史失败记录。阶段四失败重试验收使用 `uv run python scripts/insight_report_export_retry_acceptance.py`。
- 企业微信推送当前只允许 `channel=wecom`，目标类型只允许报告或正式情报；接收范围只允许 `selected` 或 `all`，`selected` 必须提供 user/dept/role/job 类型接收人及平台 ID、名称或工号之一。企业微信配置项为 `INSIGHT_WECOM_SEND_ENABLED`、`INSIGHT_WECOM_CORP_ID`、`INSIGHT_WECOM_AGENT_ID`、`INSIGHT_WECOM_SECRET`、`INSIGHT_WECOM_BASE_URL`、`INSIGHT_WECOM_TIMEOUT_SECONDS`、`INSIGHT_WECOM_RETRY_MAX_ATTEMPTS` 和 `INSIGHT_PUBLIC_BASE_URL`，密钥不得硬编码。配置 `INSIGHT_PUBLIC_BASE_URL` 后，报告/情报相对路径会拼成绝对地址并优先发送企业微信 `textcard` 卡片消息；未配置可跳转地址时回退为文本消息。阶段五推送验收使用 `uv run python scripts/insight_notification_acceptance.py`，脚本会用假发送器覆盖真实发送成功、失败和人工重试路径。
- 设置页状态接口为 `GET /ai-api/v1/insight/settings/status`，仅用于只读展示采集、调度、企业微信推送、报告导出和登录态配置健康；敏感配置只能返回是否已配置，不得返回密钥、Secret 或完整敏感值。阶段六设置页验收使用 `uv run python scripts/insight_settings_acceptance.py`，需确认配置分组完整、企微卡片跳转状态可见、且响应中不暴露敏感值。
- Insight 字典接口统一位于 `/ai-api/v1/insight/dictionaries/*`：`GET /overview` 返回分类、标签和情报类型总览，`GET/POST /tag-categories`、`PUT /tag-categories/{category_id}`、`POST /tag-categories/{category_id}/disable` 维护标签分类，`GET/POST /tags`、`PUT /tags/{tag_id}` 和 `POST /tags/{tag_id}/disable` 维护标签，`GET /intelligence-types` 返回内置受控情报类型。分类和标签写操作对登录用户开放，用于业务用户维护 AI 评审口径；禁用标签不得删除历史情报；情报类型当前为只读统一口径，如需在线增删类型需另建持久化类型表和审核规则。AI 评审只允许写入 `source=controlled_dictionary` 的受控标签，新增口径先进入建议字段，管理员确认后再成为字典标签。阶段六字典验收使用 `uv run python scripts/insight_dictionary_acceptance.py`。
- 质量运营基础版接口为 `GET /ai-api/v1/insight/quality/overview`，聚合采集任务成功率、失败任务数、平均执行耗时、候选生成率、失败原因排行、候选审核通过/驳回率、AI 质量规则和数据源质量排行；前端入口为 `/insight/quality`。质量运营页只能展示真实聚合数据，图表缺数据时必须展示空状态，不得生成样例点冒充真实指标。阶段七验收使用 `uv run python scripts/insight_quality_acceptance.py`。

## 9. SAP 助手流程

入口文件：
- 前端页面：`frontend/src/features/sap-assistant/pages/SapAssistantPage.tsx`
- SAP 系统管理页：`frontend/src/pages/system/sap/SapSystemManagerPage.tsx`
- 后端接口：`backend/app/ai-api/v1/endpoints/agent/sap_assistant.py`
- 编排服务：`backend/app/services/agent/sap_assistant/assistant_service.py`
- RFC 客户端：`backend/app/services/agent/sap_assistant/rfc_client.py`
- ABAP 示例：`docs/sap-rfc/`

流程：
1. 用户进入 `/sap-assistant`，可从历史会话列表恢复旧会话，也可新建会话并选择 SAP 系统和可选知识库。
2. 前端通过 `/ai-api/v1/sap/assistant/chat/stream` 发起流式聊天请求。
3. 后端创建或恢复 `sap_assistant_session`，写入用户消息。
4. `SapAssistantService` 创建或恢复会话、解析 SAP 系统，并交由 `SapDeepAgentService` 使用 SAP 专用 Agent 自主规划工具调用、更新证据链和决定是否调用 `finish_investigation`；该 Agent 复用 deepagents 的摘要压缩、工具调用修复和提示缓存中间件，但不注入默认 todo、文件、shell 或 subagent 工具；历史 LangGraph 和自定义 ReAct 实现已移除。
5. `SapToolService` 调用 `SapRfcClient`，再由 SAP 侧 `ZFM_AI_*` RFC 获取事务码、源码、DDIC 或受控只读样例数据；源码类工具会完整拉取并写入缓存、前端事件、审计和数据库记录，但默认只把与用户问题相关的源码包作为工具观察交给 SAP 工具 Agent。`safe_table_read` 可暴露给 Agent，但必须经过少字段、少行、强条件的预检；`zilog_logs` 和 `latest_table_read` 完成前不得暴露。
6. 每次工具调用写入 `sap_tool_call`，证据写入 `sap_evidence_record`。

7. 如选择知识库，后端通过通用知识库服务检索片段并合并到证据链。
8. 每轮工具结果返回后，SAP 工具 Agent 决策阶段读取工具观察、证据账本、会话记忆和用户问题辅助提示，先判断问题是业务数据查询、源码/接口逻辑排查还是混合问题，再决定继续调用工具、停止回答或请求人工介入；服务层只做异常兜底和会话持久化，不再维护自定义 ReAct 工具循环。
9. 对客户、物料、供应商、发货、开票、订单、库存、采购等业务数据查询，Agent 应优先查 DDIC、字段含义、内部格式、日期范围和受控只读样例数据；除非用户明确给出事务码、程序、函数、接口、字段血缘、计算逻辑或“为什么查不到”，否则不应固定先查事务码或源码。
10. 对源码定位类问题，LLM 先使用 `program_source` / `function_source` 获取问题相关源码包，自主定位字段赋值、金额计算、取数语句和真实 `CALL FUNCTION` 链路；当源码包缺少关键上下文时，才调用 `source_full_text` 显式获取全文。
11. SAP 助手会话需要读取最近消息和证据作为下一轮上下文，不允许只保存不使用；前端通过 `/ai-api/v1/sap/assistant/sessions` 和 `/ai-api/v1/sap/assistant/sessions/{id}/messages` 展示历史会话。
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
3. 每次聊天发送前，平台嵌入页通过 `WEAVER_AI_REQUEST_CONTEXT` 请求 ecode 回传当前表单实时状态，包括字段值、可写状态和只读原因。
4. 平台嵌入页调用 `/ai-api/v1/weaver/ai-assistant/chat/stream`，后端先以 SSE 流式返回自然语言回答，再返回白名单结构化填单动作。
5. 用户在嵌入页确认“写入表单”后，平台向父页面发送 `WEAVER_AI_APPLY_ACTIONS`。
6. ecode 只按白名单动作调用 `WfForm.changeFieldValue()` 或 `WfForm.addDetailRow()`，不执行任意脚本，不自动提交流程。

## 泛微流程AI智审流程

1. 流程审批页 ecode 打开 `/weaver/assistant/review` iframe，读取最近一次 AI 智审记录，必要时可手动发起预审。
2. 泛微后端可在节点前或节点后配置 `WeaverAiReviewAction`，在流程流转时调用 `/ai-api/v1/weaver/ai-assistant/review/precheck` 自动生成智审记录。
3. 智审服务按 `env + workflow_id + node_id + reviewer_user_id` 匹配启用规则，把表单快照、审批动作、规则快照交给模型生成结构化预审结果。
4. 预审结果保存到 `weaver_ai_review_record`，包含风险等级、建议结论、检查项、缺失材料、关注点和建议审批意见。
5. 初版只做建议展示和审计沉淀，不直接替审批人执行同意、退回、拒绝、保存或提交；后续替审必须显式授权、限制低风险场景并保留完整审计。
