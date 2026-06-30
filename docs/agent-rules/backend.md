# 后端开发规则

本文件适用于修改 `backend/` 下的 API、服务、模型、Agent、MCP、配置和数据库访问逻辑。

## 1. 技术栈

- Web 框架：FastAPI。
- ORM：SQLModel + SQLAlchemy AsyncSession。
- Agent 编排：LangGraph。
- 包管理：`uv`。
- 日志：`loguru`。
- 认证：JWT。
- 可观测性：LangFuse。

## 2. 分层约定

- API 路由放在 `backend/app/ai-api/v1/endpoints/`。
- 业务逻辑放在 `backend/app/services/`。
- 数据模型放在 `backend/app/models/`。
- 请求响应 Schema 放在 `backend/app/schemas/`。
- 通用配置、安全、日志、中间件放在 `backend/app/core/`。
- LangGraph 定义放在 `backend/app/agents/definitions/`。
- MCP 服务放在 `backend/app/mcp/servers/`。

新增接口优先按以下顺序落地：

1. 定义或复用 SQLModel 模型。
2. 定义请求和响应 Schema。
3. 在 service 层实现业务逻辑。
4. 在 endpoint 层做参数接收、权限依赖和统一响应。
5. 在 `api/v1/router.py` 注册路由。
6. 增加必要测试或脚本验证。

## 3. Python 代码规范

- 文件名、变量名、函数名使用 `snake_case`。
- 类名使用 `PascalCase`。
- 常量使用 `UPPER_CASE`。
- 所有函数必须有类型注解。
- 导入顺序：标准库、第三方库、本地应用。
- 所有 I/O 操作优先使用 async/await。
- 避免阻塞调用，例如 `time.sleep`、同步 `requests`、同步数据库查询。
- 禁止在生产代码中使用 `print()`，使用 `app.core.logger.logger`。

## 4. API 响应与异常

- 业务接口优先返回 `Result.success()` 或 `Result.fail()`。
- 列表接口优先返回分页结构 `Page[T]`。
- 业务错误使用 `BizException` 或明确的 HTTP 异常，不能向客户端暴露原始异常堆栈。
- 全局异常由 `backend/app/core/exceptions.py` 统一处理。
- 受保护接口使用 `deps.get_current_user` 或 `deps.get_current_active_superuser`。

## 5. 数据库访问

- 使用 `backend/app/db/session.py` 中的异步会话。
- 查询使用 `select()` 并 `await db.exec(...)`。
- 写入后按需要 `commit()` 和 `refresh()`。
- 后台任务不得复用请求生命周期中的 session，应创建新的 `async_session()`。
- 表结构和字段规范详见 `docs/agent-rules/database.md`。

## 6. LLM 与 Agent

- 禁止在业务代码中硬编码模型名称、模型端点和 API Key。
- 模型配置应来自 `sys_model` 表或配置层。
- 复杂 Agent 或 Chain 必须考虑 LangFuse 追踪。
- LangGraph 节点要保持输入输出状态清晰，状态定义放在 `state.py`。
- 节点函数命名建议使用 `<step>_node`。
- Agent 运行失败时要记录日志，并把业务状态更新为可恢复或可排查的失败状态。

## 7. MCP 服务

MCP 服务目录结构：

```text
backend/app/mcp/servers/my_tool/
├── server.py
└── schema.py
```

规则：

- 继承 `BaseMCPServer`。
- 使用 `@register_tool` 注册工具。
- 工具函数必须是异步函数。
- 输入输出使用 Pydantic Schema。
- 捕获异常并返回友好错误。
- 端点必须通过 `X-MCP-API-Key` 鉴权。

## 8. 后端验证命令

```bash
cd backend
uv sync
uv run pytest
uv run pytest path/to/test_file.py::test_function_name -v
uv run ruff check .
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## 9. FineReport AI 报表生成

- 历史任务第一版：`fr_ai_report_task` 增加 `conversation_id`、`parent_task_id`、`revision_no`，新增 `fr_ai_report_conversation` 和 `fr_ai_report_feedback`，用于任务恢复、多轮修订追踪和人工反馈沉淀。
- 列表入口：`GET /ai-api/v1/fr/ai-reports/tasks` 返回分页历史任务；反馈入口：`POST /ai-api/v1/fr/ai-reports/tasks/{task_id}/feedback` 记录正向样本或待优化样本。
- 自驱进化第一版只做经验数据沉淀，不允许自动改写全局 Prompt、业务规则或确定性 CPT 生成逻辑。
- 接口入口：`backend/app/ai-api/v1/endpoints/agent/fr_report.py`，统一挂载到 `/ai-api/v1/fr/ai-reports`。
- 真实报表文件读取第一版入口：`GET /ai-api/v1/fr/ai-reports/files`，只读列出 MinIO 允许目录下的 `.cpt`、`.frm` 文件，返回对象路径、报表相对路径、文件大小、ETag 和修改时间；扫描范围由 `FR_AI_REPORT_FILE_PREFIXES` 控制。
- 真实报表结构读取入口：`GET /ai-api/v1/fr/ai-reports/files/structure`，按当前登录用户和显示范围校验 `object_path`，只在线内存读取 MinIO 对象，不落盘；当前解析 UTF-8/XML CPT 的根节点、版本、数据集、连接名、参数、截断 SQL，并返回 `document.sheets` 中的行列、单元格、合并区域、基础样式、字段绑定和原始节点路径引用；只返回结构化结果和 warnings，不返回完整 CPT 原文。
- 报表文件用户可见范围入口：`GET/PUT /ai-api/v1/fr/ai-reports/files/visibility-preference`，按当前登录用户保存显示的文件夹或报表路径；`GET /files` 默认按偏好过滤，配置弹窗需要传 `include_all=true` 拉取全量目录。
- 帆软报表文件存储必须走专用 `FR_AI_MINIO_*` 配置和 `FrMinIOService`，不得复用平台通用 `MINIO_*`，避免影响合同、知识库、图标等平台文件。
- 当前需要同时维护“第一步 SQL 生成”“第二步 DSL 生成”“第三步 CPT 生成”与“全流程生成”四类接口，其中第一步接口为 `POST /ai-api/v1/fr/ai-reports/steps/sql/generate`，用于只生成 SQL、执行只读校验并返回样例数据；第二步接口为 `POST /ai-api/v1/fr/ai-reports/steps/dsl/generate`，基于同一任务的 SQL、需求摘要、Excel 分析和表结构生成 ReportDSL，不生成 CPT/XML，不调用 FineReport 预览；第三步接口为 `POST /ai-api/v1/fr/ai-reports/steps/cpt/generate` 或 AI 草稿 CPT 入口，基于已确认 ReportDSL/快照确定性生成 CPT，按用户指定 `webroot/APP/reportlets/` 子路径写入并同步版本归档。
- 空白报表创建入口为 `POST /ai-api/v1/fr/ai-reports/empty/create`，只接收报表名称、目标目录/路径和冲突策略，确定性生成空白 CPT，写入用户指定 `webroot/APP/reportlets/` 子路径并同步结构版本和文件版本。`POST /ai-api/v1/fr/ai-reports/agent/chat` 保留给右侧小驰侧边栏，用于在已选中报表上下文内接收用户消息、附件和上下文 JSON，受控执行需求预检、读取真实表结构/预览数据、生成 SQL、生成 ReportDSL 或保存 CPT。
- 小驰侧边栏后端采用受控 ReAct 外壳：`agent/chat` 先通过 `LLMFactory.safe_invoke(..., json_mode=True)` 做语义意图路由，判断 `chat`、`modify_current_report`、`start_generate` 或 `save_cpt`，模型不可用或 JSON 无效时才使用保守规则兜底；不得把关键词匹配作为主判断逻辑。`modify_current_report` 只生成待应用修改项，`start_generate` 生成 SQL 和 ReportDSL，`save_cpt` 才进入版本控制写 CPT。
- 小驰面向用户的主回答优先使用模型路由或后续 Agent 生成的自然短回复；前端和后端只可在错误、缺少硬条件、工具产物摘要等场景提供简短兜底，不得把所有聊天回答套成固定流程模板。
- 小驰能力清单入口为 `GET /ai-api/v1/fr/ai-reports/agent/capabilities`，返回工具名称、风险等级、是否自动执行、是否需要确认、系统技能和运行策略；已有 CPT 修改工具只接受 `xml_patch`，前端技能只作为上下文偏好，不得改变后端工具权限。
- 小驰上下文工程必须控制 token 使用：报表结构需要压缩为摘要、样例数据限行、字段列表限量、技能只注入启用项；长会话后续应沉淀为会话摘要、任务版本、反馈和经验检索，不直接拼接全量历史。已确认应用的修改项不得继续作为下一轮修改参考上下文；当前报表修改应以本轮用户指令、选区、数据集字段和当前报表事实为主。历史经验只能按需检索为普通 payload，不直接注入系统提示词；XML 索引只辅助定位和省 token，不能限制后续读取或修改范围。
- 任务模型：`backend/app/models/agent/fr_report/report_task.py`，保存 Excel 分析、需求摘要、ReportDSL、SQL、建表 SQL、生成日志、MinIO 专用预览目录路径和预览校验结果。
- Schema：`backend/app/schemas/agent/fr_report/report_dsl.py` 定义第一版 ReportDSL 和 JSON Schema，当前阶段只落地 `detail_table`、`group_table`、`pivot_table` 三类表格报表。
- ReportDSL 需要通过 `reportMeta` 承载模板级语义，包括标题、单位、更新时间、均价、备注和筛选条件；这些信息不能只停留在 Excel `templateAnalysis` 或 `layout.designHints`。
- 服务分层：`backend/app/services/agent/fr_report/` 内按 `ExcelAnalyzer -> RequirementAgent -> DataModelAgent -> SqlAgent -> ReportDesignerAgent -> DslValidator -> CptGenerator -> MinIOStagingService -> PreviewValidator` 串联。
- 分步骤改造时，优先把阶段产物持久化到同一个任务表中，至少保留 `requirement_text`、`source_table_name`、Excel 分析、需求摘要、SQL、SQL 校验结果与日志，方便人工回看和后续步骤接力。
- 第二步生成的 ReportDSL 继续写回同一条 `fr_ai_report_task.report_dsl`，前端预览直接基于 DSL 布局和 SQL 样例数据渲染，用于人工确认版式，不代表 FineReport 运行时预览结果。
- 第二步接口可接收 `dsl_feedback` 做 DSL 版式重生成，只更新需求摘要中的 DSL 修订提示、ReportDSL 和日志，不重复生成 SQL；非标准表格结构优先落入 `layout.designHints.specialRows`，例如最新一天涨跌单行使用 `latest_change_row`。
- 第三步当前只允许从已确认的 `report_dsl` 或 AI 快照确定性生成 CPT；写入目标 CPT 前必须走 `FrReportVersionControlService`，保存结构版本、文件版本，并检测 FineReport 设计器外部修改，不能直接覆盖。
- 对已有真实 CPT 的小驰修改，保存 CPT 时必须优先基于当前 MinIO 原始 CPT/XML 做增量补丁；禁止仅凭结构快照重建整份 CPT 覆盖原文件，避免未解析到的单元格、参数、控件或设计器私有节点丢失。
- 对已有真实 CPT 的小驰修改，新生成的待应用修改项必须使用 `xml_patch` 直接修改 CPT XML。下拉筛选、参数栏控件、SQL 查询、样式、填报、脚本、单元格和尺寸修改都应直接替换或插入 `ReportParameterAttr`、`ParameterUI`、`TableData/Query`、`StyleList`、`ReportWriteAttr`、`<C>`、`ColumnWidth`、`RowHeight` 等真实 XML 片段。字段名必须优先取数据集真实字段，单元格坐标只可用于定位，禁止写成参数名。SQL Server 查询允许受控 `DECLARE @param ...; SELECT/WITH ...` 形式，但仍禁止 DDL/DML/存储过程和多语句写操作。
- 已有 CPT 修改主路径为直接 XML 修改：后端按需向模型提供当前单元格、参数栏、数据集、样式、填报、脚本等 CPT 片段以及轻量 XML 索引，模型通过 `xml_patch` 输出 replace/insert_before/insert_after/delete/full_replace。允许修改 `StyleList`、`ReportWriteAttr`、脚本事件和完整 `<WorkBook>`；索引只是导航图，不得成为读取或修改边界。后端负责 XML 合法性校验、patch 兜底定位、版本归档、外部修改冲突检测和 FineReport 预览验证；写入 CPT 时只在原始 XML 上应用 `xml_patch`。
- CPT 修改提示词应维护极短 mini-shot，示范“按需读取片段 -> 返回 `xml_patch` -> 说明风险和预览补丁”的输出形态；mini-shot 只用于塑造行为，不得演变成固定问答模板或限制用户可修改的 CPT 范围。
- CPT 待应用修改项需要自动推断风险等级：单元格文本等局部修改通常为低风险，参数栏、数据集、查询和控件通常为中风险，`StyleList`、`ReportWriteAttr`、`ReportWebAttr`、脚本事件和 `full_replace` 通常为高风险。中高风险必须在用户确认前显式提示；前端详情只展示自然语言修改范围和风险说明，不展示原始 JSON 或 XML。
- 版本控制服务需要覆盖生成、外部同步、文件回档、结构回档和回收站；同一 `current_object_path` 的写操作必须串行化，避免并发请求同时通过 hash 检测后互相覆盖。
- 第三步对接细节见 `docs/fr-ai-report-third-step.md`。CPT XML 按 FineReport 11.5.0 样例生成，数据库连接名来自 `FR_AI_FINEREPORT_DB_NAME`，当前默认 `XcTest`。
- Agent 实现：`RequirementAgent`、`DataModelAgent`、`SqlAgent`、`ReportDesignerAgent` 必须优先通过 `app.core.llm_factory.LLMFactory` 调用已配置大模型生成结构化 JSON；模型不可用或 JSON 校验失败时才使用规则兜底。
- 表结构与 SQL 校验：用户只提供单表或多表表名时，`SqlServerQueryService` 可查询 SQL Server `INFORMATION_SCHEMA.COLUMNS` 获取字段结构并推断字段类型/角色；多表会生成 `tables`、字段来源和 `joinHints` 供 `SqlAgent` 生成 JOIN SQL。`SqlAgent` 生成 SQL 后由同一服务做只读预执行校验，只允许 `SELECT/WITH` 查询，禁止 DDL/DML/存储过程/多语句，参数使用安全默认值绑定，失败时允许 `SqlAgent` 基于错误修复一次。
- SQL ReAct：`SqlReActAgent` 会读取 Excel 模板摘要、真实表结构和 SQL Server TOP 样例数据，生成 SQL 后立即执行只读校验；如果 SQL 不可执行会把错误和样例数据反馈给大模型继续修复，最多迭代 3 轮。对于 Excel 中城市、市场、区域等横向表头，优先通过 ReportDSL/FineReport 横向扩展表达，SQL 保持 `record_date/market/price/change_amt` 等长表结果，不因模板横向表头强制生成大量 `CASE WHEN`、`PIVOT` 或聚合宽表列。
- Excel 模板分析：`ExcelAnalyzer` 需要保留标题、单位、筛选区、更新时间、备注说明、年份/月日格式、涨跌规则和横向扩展候选信息，供 SQL Agent 与 ReportDesignerAgent 共同判断“数据集长表 + 设计器横向扩展”的方案。
- Excel 模板分析必须先基于非空值、公式和有效合并区域裁剪真实有效区域，避免把 `XFD` 等样式尾列喂给模型；`templateAnalysis` 需要输出 `effectiveRange`、`formulaRules` 和 `formulaConflicts`，公式与文字说明冲突时由小驰追问或提示风险，不能自行择一。
- Excel 标题识别不能简单默认第一行，应结合表格区域上方文本、合并单元格、标题关键词和全报表语义打分判断；筛选条件、单位、更新时间、备注等辅助文本不能误判为标题。
- 多层表头解析必须结合合并单元格生成完整语义字段；例如期权填报模板中的 `开仓` + `权利金单价` 应解析为 `开仓权利金单价`，空白尾列不得进入字段列表。
- 小驰聊天入口允许多附件上传；第一版优先解析 Excel，非 Excel 附件作为需求上下文保留并返回 warning，后续可接图片 OCR、Word 摘要和多 Excel 合并，不应把 Agent 限制成只能处理单一 Excel。
- 小驰需求理解阶段优先返回方案草图，而不是把所有追问作为阻断；只有报表名、目录、需求/资料完全缺失等硬条件才 `need_input`，其他未确认点进入风险和假设，用户明确开始生成时继续执行。
- AI 提取的 `sourceTables` 如果是中文业务来源名称，只能进入需求摘要和方案说明；只有 `fr_xxx`、`dbo.xxx` 等符合数据库标识符规则的真实表名才进入 `SqlServerQueryService` 表结构读取。
- 已沉淀的期货和期权操作台账场景应走独立 `businessPlan.scenario`、候选数据模型、SQL 兜底和 DSL 规范化；期权场景不得复用期货的吨数/手、每日收盘价和浮动盈亏口径。
- 候选表结构生成必须默认使用英文下划线表名和字段名，并包含 `id` 主键；第一步接口支持 `ddl_dialect`、`id_auto_increment`、`table_name_overrides_json`，DDL 需要按 SQL Server、MySQL、PostgreSQL 分别生成数据库级表注释和字段注释。
- 关键边界：AI/Agent 只能输出结构化 ReportDSL、需求摘要、逻辑表结构和 SQL；FineReport `.cpt`/XML 必须由 `CptGenerator` 确定性生成。
- 存储边界：AI 生成或修改后的 CPT 可写入用户指定的 `webroot/APP/reportlets/` 子路径，也可以覆盖目标 CPT；但必须先通过文件版本服务记录平台结构版本、CPT 文件版本、hash/lastModified，并把版本文件归档到目标目录下的 `版本库/<报表名>/v0001/` 等结构化目录。检测到 FineReport 设计器外部修改时默认阻止覆盖。
- 外部修改处理分为“仅同步外部修改为文件版本”和“覆盖前自动归档当前文件”；前者不得继续生成或覆盖 CPT。回收站目录固定为目标文件夹下 `回收站/<报表名>/<时间>/`。

## 10. SAP 助手

- 接口入口：`backend/app/ai-api/v1/endpoints/agent/sap_assistant.py`，统一挂载到 `/ai-api/v1/sap`。
- 会话接口：`GET /ai-api/v1/sap/assistant/sessions`、`GET /ai-api/v1/sap/assistant/sessions/{id}/messages`，用于前端历史会话恢复。
- 通用知识库入口：`backend/app/ai-api/v1/endpoints/knowledge_bases.py`，统一挂载到 `/ai-api/v1/knowledge-bases`，不得绑定到 SAP 专属命名。
- SAP 模型：`backend/app/models/agent/sap_assistant.py`，保存系统配置、会话、消息、工具调用和证据记录。
- 知识库模型：`backend/app/models/knowledge_base.py`，保存知识库、文档、切片和索引任务。
- SAP 服务分层位于 `backend/app/services/agent/sap_assistant/`：`SapAssistantService -> SapDeepAgentService -> SapToolService -> SapRfcClient`，工具调用必须记录审计和证据。
- SAP RFC 客户端需要兼容未安装 `pyrfc` 的开发环境；未配置时可以返回明确的未配置或演示证据，但不得假装已经真实查询生产系统。
- AI 不允许直接执行任意 SQL 或保存数据库账号；业务数据必须通过 SAP 侧只读 RFC 查询，并采用小批量、多轮调用减少 token 消耗。`safe_table_read` 调用必须显式指定少量字段和高选择性 ranges 条件，默认最多 5 行；禁止空字段或无条件读取宽表。
- SAP 助手系统提示词内维护极短 mini-shot，示例化 DDIC -> `safe_table_read`、前导零、日期范围和源码后补证路径；示例必须短小，不得演变成固定流程。
- SAP 助手聊天请求支持 `enable_reasoning`，用于本轮开启或关闭模型思考模式；本地 LM Studio 等模型不需要思考时可传 `false`。
- 回答必须尽量包含 SAP 系统上下文、使用的工具、证据来源和不确定性说明。

## 11. Insight 研发营销市场洞察平台

- 后端接口统一挂载到 `/ai-api/v1/insight`，入口目录为 `backend/app/ai-api/v1/endpoints/agent/insight/`。
- 后端业务服务放在 `backend/app/services/agent/insight/`，按 `crawler`、`intelligence`、`visibility`、`report` 等子域逐步拆分。
- 数据模型放在 `backend/app/models/agent/insight/`，Schema 放在 `backend/app/schemas/agent/insight/`。
- 定时报告计划服务位于 `backend/app/services/agent/insight/report_subscription_service.py`，通过 `insight_report_subscription` 保存模板、范围、周期和企业微信接收人；执行时必须按计划创建者权限生成报告并复用通知服务写 `insight_notification`。
- 第一阶段开发顺序以通用联网采集为先：本地 Firecrawl 通用网页抓取、百度搜索发现、Bocha/博查 API 多源查询、采集清洗、候选情报入库，再进入情报权限、情报池和报告模块。
- Insight 情报不固定绑定企业，必须支持 `company`、`industry`、`market`、`product`、`policy`、`technology`、`custom` 等主题类型。
- 情报列表接口必须在后端执行可见性过滤，不能返回全量情报后只靠前端隐藏。
- Insight 候选情报默认走 AI 自动评审：`formal` 转正式情报，`candidate` 保留为候选线索，`noise` 归档为噪声；评审结果必须写 `insight_review_record` 并同步进入情报资产层。
- Insight 情报资产层由 `insight_intelligence_asset`、`insight_asset_vector`、`insight_graph_node`、`insight_graph_edge` 承载，报告、AI 助手和深度研究后续优先通过资产检索接口取证据。
- Insight 向量模型使用 `sys_model.model_type=embedding` 配置，当前默认火山方舟 `doubao-embedding-vision-251215` 多模态向量接口；API Key 继承已配置火山模型，不得硬编码。
- 质量运营基础接口为 `GET /ai-api/v1/insight/quality/overview`，服务层位于 `backend/app/services/agent/insight/quality_service.py`，只能聚合真实任务、采集、候选审核和质量规则数据，不得返回样例指标。
- Firecrawl、Bocha/博查等外部服务地址和密钥不得硬编码在业务代码中，应进入配置或环境变量。
## SAP 助手 Agent 状态约束补充

- SAP 助手聊天入口固定走 `backend/app/services/agent/sap_assistant/deep_agent_service.py`，并复用 `SapToolService -> SapRfcClient` 调用 SAP 侧 `ZFM_AI_*` RFC；该入口按 deepagents 源码思路组装 SAP 专用 Agent，保留摘要压缩、工具调用修复和提示缓存中间件，但禁用 deepagents 默认 todo、文件、shell 和 subagent 工具；历史 LangGraph 和自定义 ReAct 实现已移除。
- SAP 助手服务层必须维护源码调查状态，不能只依赖模型逐轮自由规划。状态至少包含工具调用去重、最近观察摘要、直接赋值证据、计算证据和已发现函数调用。
- 当前源码调查采用“全量拉取、聚焦观察、按需全文”策略：`program_source` 和 `function_source` 在服务层完整读取源码并写入缓存、前端事件、审计和数据库记录，但默认只把与用户问题相关的源码包交给 LLM；只有聚焦源码包不足以判断关键逻辑时，Agent 才能显式调用 `source_full_text` 获取全文。
- SAP 助手调查状态需要维护 `evidence_ledger`、源码对象索引和工具预算；接近预算或递归限制时先压缩状态，再决定继续读取关键源码包、请求 `source_full_text`、跳过可选补强或调用 `finish_investigation`。
- 字段取值、金额计算、字段血缘类问题只有在存在可执行代码证据时才能下确定结论；注释、标题和字段定义不得被改写成事实结论。
- 当调查状态已经满足回答条件时，后端应强制进入总结阶段，避免模型继续重复搜索；当证据不足时，后端应自动选择未执行过的补查工具，而不是把“下一步建议调用工具”交给用户。

## 12. FineReport 数据集预览连接

- 数据库驱动是平台级资源，使用 `fr_report_database_driver` 保存，不按用户隔离；当前默认种子包含 `sqlserver` 和 `mysql8`。
- 报表数据库连接是用户级资源，使用 `fr_report_database_connection` 保存，并通过 `driver_key` 引用平台级驱动。
- 数据集预览入口为 `POST /ai-api/v1/fr/ai-reports/datasets/preview`，当前支持 SQL Server 与 MySQL 8，只允许 `SELECT/WITH` 查询并限制预览行数。
 
## 泛微流程AI助手补充

- 后端接口入口为 `backend/app/ai-api/v1/endpoints/agent/weaver_ai_assistant.py`，统一挂载到 `/ai-api/v1/weaver/ai-assistant`。
- Schema 位于 `backend/app/schemas/agent/weaver_ai_assistant.py`，服务层位于 `backend/app/services/agent/weaver_ai_assistant/`。
- 流程特殊填报规则使用 `weaver_ai_workflow_rule` 表保存，按 `env + workflow_id` 维护；规则管理接口为 `/workflow-rules`，聊天时会自动加载启用规则进入 AI 上下文。
- 流程 AI 智审规则使用 `weaver_ai_review_rule` 表保存，按 `env + workflow_id + node_id + reviewer_user_id` 逐级匹配；智审记录使用 `weaver_ai_review_record` 保存表单快照、规则快照和模型结论。
- 智审主入口为 `POST /ai-api/v1/weaver/ai-assistant/review/precheck`，只返回风险等级、检查项、建议结论和建议审批意见；任何自动替审能力必须先通过规则授权并保留审计记录。
- 泛微助手模型选择优先读取 `WEAVER_AI_MODEL_NAME`；未配置时按 `WEAVER_AI_MODEL_CAPABILITY` 选择模型，默认使用 `complex-reasoning`，避免复杂流程规则被轻量模型弱化。
- ecode 或泛微页面调用该接口时使用 `ai-sign` 请求头，校验逻辑复用 `deps.verify_external_ai_sign`。
- 聊天主入口为 `POST /ai-api/v1/weaver/ai-assistant/chat/stream`，以 SSE 推送 `message_delta`、`actions`、`done`；`/chat` 仅作为非流式兼容入口保留。
- 服务层需要在每轮聊天上下文中注入 `current_date` 日期工具结果，供 AI 将“今天、明天、下周一、本月”等相对日期换算为具体日期。
- AI 只能返回 `set_field`、`add_detail_row`、`show_message` 等结构化动作，不得返回任意 JavaScript，不得触发保存、提交、审批或删除流程。
