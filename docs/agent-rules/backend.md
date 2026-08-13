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
- 泛微发票与对账单单位核验优先使用确定性的单位别名和量纲换算；仅对确定性规则无法识别的单位冲突调用模型复核，模型必须返回换算系数且通过数量等式校验，高置信结果才允许改判为一致。

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
- 空白报表创建入口为 `POST /ai-api/v1/fr/ai-reports/empty/create`，只接收报表名称、目标目录/路径和冲突策略，确定性生成空白 CPT，写入用户指定 `webroot/APP/reportlets/` 子路径并同步结构版本和文件版本。右侧小驰侧边栏主入口为 `POST /ai-api/v1/fr/ai-reports/agent/run/stream`，普通输入默认传 `autonomyMode=high`，用于在已选中报表上下文内接收用户消息、附件和上下文 JSON，流式执行读取 CPT、解析结构、查询数据库、检索案例库、生成修改、写入版本和预览验证；`agent/chat` 仅保留兼容旧流程。
- 小驰侧边栏后端采用“直接文件编辑 + 高权限观察-行动-验证外壳”：默认把 CPT 当作源代码文件读取和改写，优先返回 `file_edit` 精确 `oldText/newText` 文件编辑，必要时才接受完整 WorkBook XML 兜底；工具循环用于补上下文、查数据库、检索案例、验证和修复。旧 `xml_patch`、selector 操作和旧写入器不再作为主写入方式，也不得把关键词匹配作为主判断逻辑。
- 小驰面向用户的主回答优先使用模型路由或后续 Agent 生成的自然短回复；前端和后端只可在错误、缺少硬条件、工具产物摘要等场景提供简短兜底，不得把所有聊天回答套成固定流程模板。
- 小驰能力清单入口为 `GET /ai-api/v1/fr/ai-reports/agent/capabilities`，返回工具名称、风险等级、是否自动执行、系统技能和运行策略；能力边界不按参数栏、数据集、样式、填报、脚本等类型裁剪，前端技能只作为上下文偏好，不得绕过路径白名单、版本归档、预览校验和回档。
- 小驰上下文工程必须控制 token 使用：默认先读取结构索引和相关片段，信息不足时允许读取完整 CPT XML；样例数据限行、字段列表限量、技能只注入启用项。长会话后续应沉淀为会话摘要、任务版本、反馈和经验检索，不直接拼接全量历史。已写入版本的旧修改项不得继续作为下一轮修改参考上下文；当前报表修改应以本轮用户指令、选区、当前 CPT 文件和真实数据库事实为主。
- FineReport 案例库接口位于同一 `fr_report.py` 路由下：`POST /cases/sample-build` 启动样本报表自发现任务，`GET /cases/sample-jobs/{job_id}` 查询进度，`GET /cases/search` 检索案例，`GET /cases/{case_id}` 查看详情。初始化对象是 50-100 个典型报表样本，不是固定数量或固定类型的案例；案例由逐报表分析过程自然产生。高权限 Agent 每次准备写入 CPT 前必须先调用 `search_reference_cpt` 做轻量检索，需要更细证据时再读取案例详情或参考报表全文；案例不预加载进系统提示词，不覆盖当前 CPT、用户需求、数据库事实和预览结果。
- FineReport 属性设置知识库由 `fr_setting_knowledge_service.py` 提供，只维护属性面板能力到 CPT 节点、适用场景、避用场景和验证点的只读索引。高权限 Agent 可通过 `search_fr_setting_knowledge` 按需检索格式、扩展、样式、形态、其他、悬浮元素、控件、条件属性、超链接和填报等设置线索；该知识库不得演变为自动改写规则、全局 Prompt 注入或覆盖当前 CPT/案例/预览结果的依据。
- 任务模型：`backend/app/models/agent/fr_report/report_task.py`，保存 Excel 分析、需求摘要、ReportDSL、SQL、建表 SQL、生成日志、MinIO 专用预览目录路径和预览校验结果。
- Schema：`backend/app/schemas/agent/fr_report/report_dsl.py` 定义第一版 ReportDSL 和 JSON Schema，当前阶段只落地 `detail_table`、`group_table`、`pivot_table` 三类表格报表。
- ReportDSL 需要通过 `reportMeta` 承载模板级语义，包括标题、单位、更新时间、均价、备注和筛选条件；这些信息不能只停留在 Excel `templateAnalysis` 或 `layout.designHints`。
- 服务分层：`backend/app/services/agent/fr_report/` 内按 `ExcelAnalyzer -> RequirementAgent -> DataModelAgent -> SqlAgent -> ReportDesignerAgent -> DslValidator -> CptGenerator -> MinIOStagingService -> PreviewValidator` 串联。
- 分步骤改造时，优先把阶段产物持久化到同一个任务表中，至少保留 `requirement_text`、`source_table_name`、Excel 分析、需求摘要、SQL、SQL 校验结果与日志，方便人工回看和后续步骤接力。
- 第二步生成的 ReportDSL 继续写回同一条 `fr_ai_report_task.report_dsl`，前端预览直接基于 DSL 布局和 SQL 样例数据渲染，用于人工确认版式，不代表 FineReport 运行时预览结果。
- 第二步接口可接收 `dsl_feedback` 做 DSL 版式重生成，只更新需求摘要中的 DSL 修订提示、ReportDSL 和日志，不重复生成 SQL；非标准表格结构优先落入 `layout.designHints.specialRows`，例如最新一天涨跌单行使用 `latest_change_row`。
- 第三步确定性 CPT 生成继续走 `FrReportVersionControlService`；已有 CPT 的高权限 Agent 写入同样必须走该服务，保存结构版本、文件版本、diff、manifest 和日志，并检测/归档 FineReport 设计器外部修改，不能无版本直接覆盖。
- 对已有真实 CPT 的小驰修改，保存 CPT 时必须基于当前 MinIO 原始 CPT/XML 应用模型返回的精确文件编辑；当改动无法稳定用精确编辑表达时允许整份 WorkBook XML 重写，但必须先归档当前文件，避免不可回滚。
- 对已有真实 CPT 的小驰修改，写入前必须先生成候选 CPT 并做工程审计：确认候选文件确实发生变化、没有旧 `t="ds"` 伪绑定、DSColumn 指向存在的数据集、数据集 SQL 返回列覆盖绑定字段、隐藏行列和尺寸配置基本一致、填报属性引用的单元格仍存在。审计失败必须把审计报告带入自动修复循环，不能直接写入。
- 候选 CPT 后处理必须规范化模型常见的非标准数据绑定：`<O t="ds"><DS ds="..." name="..."/></O>` 和 `<O><DSColumn>...</DSColumn></O>` 都要在写入前转成当前案例库验证过的 `<O t="DSColumn"><Attributes dsName="..." columnName="..."/>...</O>`；审计器必须把未规范化的绑定视为失败，不能因为 XML 合法就放行。
- 对已有真实 CPT 的小驰修改，模型可直接修改 `ReportParameterAttr`、`ParameterUI`、`TableData/Query`、`StyleList`、`ReportWriteAttr`、`ReportWebAttr`、脚本事件、`<C>`、`ReportPageAttr`、`HR/HC`、`ColumnWidth`、`RowHeight` 和完整 `<WorkBook>`。隐藏行列优先沿用当前 CPT 的原生隐藏配置，`ColumnWidth/RowHeight` 是尺寸信息和兼容兜底，不应被当作唯一隐藏方式。字段名必须优先取真实数据库结构和数据集字段，单元格坐标只可用于定位，禁止把中文口语或表头猜成数据库字段。
- 已有 CPT 修改必须有通用布局影响检查：字段格式变长、表头文案变长、隐藏/显示行列、合并区域变化、控件变化、填报公式变化、数据集字段类型变化，都要联动检查 `ColumnWidth`、`RowHeight`、`StyleList`、`ReportWriteAttr` 和相关单元格，不能只改“目标节点”就断言完成。日期显示只是其中一类：如果 FineReport 预览不吃单元格 `DateAttr`，应同步修改数据集显示字段，例如把 `CAST(zdata AS DATE) AS month_day` 改成 `FORMAT(CAST(zdata AS DATE), 'yyyy年MM月dd日') AS month_day`；隐藏前置列后还要同步检查可见日期列的 `ColumnWidth`；若填报写回曾通过 `CONCATENATE(A5,B5)` 拼日期，日期列改成完整日期后必须同步改写回公式。
- CPT 修改提示词应维护极短 mini-shot，示范“按需读取片段/完整 CPT -> 用数据库和单元格语义定位 -> 返回精确文件编辑或完整 WorkBook 兜底 -> 写入版本 -> 预览验证”的行为；mini-shot 只用于塑造行为，不得演变成固定问答模板或限制用户可修改的 CPT 范围。
- 高权限 Agent 的用户可见结果只展示自然语言修改范围、写入路径、版本号、预览结果、风险和回档入口，不展示原始 JSON 或 XML；旧待应用草稿只作兼容/显式 review 模式，不得阻断默认的流式高权限直接写入主链路。
- 版本控制服务需要覆盖生成、外部同步、文件回档、结构回档和回收站；同一 `current_object_path` 的写操作必须串行化，避免并发请求同时通过 hash 检测后互相覆盖。
- 第三步对接细节见 `docs/fr-ai-report-third-step.md`。CPT XML 按 FineReport 11.5.0 样例生成，数据库连接名来自 `FR_AI_FINEREPORT_DB_NAME`，当前默认 `XcTest`。
- Agent 实现：`RequirementAgent`、`DataModelAgent`、`SqlAgent`、`ReportDesignerAgent` 必须优先通过 `app.core.llm_factory.LLMFactory` 调用已配置大模型生成结构化 JSON；模型不可用或 JSON 校验失败时才使用规则兜底。
- 表结构与 SQL 校验：用户只提供单表或多表表名时，`SqlServerQueryService` 可查询 SQL Server `INFORMATION_SCHEMA.COLUMNS` 获取字段结构并推断字段类型/角色；多表会生成 `tables`、字段来源和 `joinHints` 供 `SqlAgent` 生成 JOIN SQL。`SqlAgent` 生成 SQL 后由同一服务做只读预执行校验，只允许 `SELECT/WITH` 查询，禁止 DDL/DML/存储过程/多语句，参数使用安全默认值绑定，失败时允许 `SqlAgent` 基于错误修复一次。
- SQL 生成校验链路会读取 Excel 模板摘要、真实表结构和 SQL Server TOP 样例数据，生成 SQL 后立即执行只读校验；如果 SQL 不可执行会把错误和样例数据反馈给大模型继续修复，最多迭代 3 轮。对于 Excel 中城市、市场、区域等横向表头，优先通过 ReportDSL/FineReport 横向扩展表达，SQL 保持 `record_date/market/price/change_amt` 等长表结果，不因模板横向表头强制生成大量 `CASE WHEN`、`PIVOT` 或聚合宽表列。
- Excel 模板分析：`ExcelAnalyzer` 需要保留标题、单位、筛选区、更新时间、备注说明、年份/月日格式、涨跌规则和横向扩展候选信息，供 SQL Agent 与 ReportDesignerAgent 共同判断“数据集长表 + 设计器横向扩展”的方案。
- Excel 模板分析必须先基于非空值、公式和有效合并区域裁剪真实有效区域，避免把 `XFD` 等样式尾列喂给模型；`templateAnalysis` 需要输出 `effectiveRange`、`formulaRules` 和 `formulaConflicts`，公式与文字说明冲突时由小驰追问或提示风险，不能自行择一。
- Excel 标题识别不能简单默认第一行，应结合表格区域上方文本、合并单元格、标题关键词和全报表语义打分判断；筛选条件、单位、更新时间、备注等辅助文本不能误判为标题。
- 多层表头解析必须结合合并单元格生成完整语义字段；例如期权填报模板中的 `开仓` + `权利金单价` 应解析为 `开仓权利金单价`，空白尾列不得进入字段列表。
- 小驰聊天入口允许多附件上传；Excel 进入结构解析，Word 进入文本摘要，图片必须优先按当前模型档位选择 `sys_model.is_multimodal=true` 的 chat/vision 模型解析为文字上下文，再交给主 Agent。不得把图片 base64 直接塞进主 Agent 提示词；没有可用多模态模型时返回清晰 warning，不中断其他附件和文本需求。
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
- 经营智能基础接口为 `GET /ai-api/v1/insight/operation/overview` 和 `GET /ai-api/v1/insight/operation/customer-lifecycle`，服务层位于 `backend/app/services/agent/insight/operation_intelligence_service.py`，当前以 FineReport SQL Server 只读连接聚合健源公司销量利润、客户流失、采购库存、经营净头寸、套保风险，以及新客户质量、90 天挽回窗口、沉默客户分层、应收叠加和高价值行动清单；接口仅管理员可访问，不新增持久化表，不得返回伪造样例指标。
- Firecrawl、Bocha/博查、豆包联网搜索等外部服务地址、模型配置和密钥不得硬编码在业务代码中，应进入配置、环境变量或 `sys_model`。
- Insight 飞书月报编排位于 `backend/app/services/agent/insight/feishu_monthly_report_service.py`。月报必须先审批资料，再保留单模型、分章节并行和多智能体候选，通过事实、相关度和管理表达审校后择优合成；发布前还要执行章节、链接白名单、裸网址、引用覆盖和内部技术词确定性检查。模型从 `sys_model` 动态选择，实际模型、评分、审校意见和阶段耗时写入简报运行记录。
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
- 智审规则声明的只读证据工具由 `backend/app/services/agent/weaver_ai_assistant/review_evidence_service.py` 执行；工具必须先通过泛微元数据解析和数据库标识符校验，只允许参数化 `SELECT`，确定性失败结论不得被模型覆盖或用于自动替审。
- 智审主入口为 `POST /ai-api/v1/weaver/ai-assistant/review/precheck`，只返回风险等级、检查项、建议结论和建议审批意见；任何自动替审能力必须先通过规则授权并保留审计记录。
- 智审配置页测试入口使用 `POST /ai-api/v1/weaver/ai-assistant/review/test`：按当前环境、当前配置流程和输入的 `requestId` 从泛微数据库读取主表、明细表及只读证据，忽略请求当前节点和节点启用开关；测试记录只能写入 `weaver_ai_review_test_record`，不得进入正式记录查询或触发流程动作。
- 泛微助手模型选择优先读取 `WEAVER_AI_MODEL_NAME`；未配置时按 `WEAVER_AI_MODEL_CAPABILITY` 选择模型，默认使用 `complex-reasoning`，避免复杂流程规则被轻量模型弱化。
- ecode 或泛微页面调用该接口时使用 `ai-sign` 请求头，校验逻辑复用 `deps.verify_external_ai_sign`。
- 聊天主入口为 `POST /ai-api/v1/weaver/ai-assistant/chat/stream`，以 SSE 推送 `message_delta`、`actions`、`done`；`/chat` 仅作为非流式兼容入口保留。
- 服务层需要在每轮聊天上下文中注入 `current_date` 日期工具结果，供 AI 将“今天、明天、下周一、本月”等相对日期换算为具体日期。
- AI 只能返回 `set_field`、`add_detail_row`、`show_message` 等结构化动作，不得返回任意 JavaScript，不得触发保存、提交、审批或删除流程。
