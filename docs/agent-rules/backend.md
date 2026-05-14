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

- API 路由放在 `backend/app/api/v1/endpoints/`。
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
- 列表入口：`GET /api/v1/fr/ai-reports/tasks` 返回分页历史任务；反馈入口：`POST /api/v1/fr/ai-reports/tasks/{task_id}/feedback` 记录正向样本或待优化样本。
- 自驱进化第一版只做经验数据沉淀，不允许自动改写全局 Prompt、业务规则或确定性 CPT 生成逻辑。
- 接口入口：`backend/app/api/v1/endpoints/agent/fr_report.py`，统一挂载到 `/api/v1/fr/ai-reports`。
- 当前需要同时维护“第一步 SQL 生成”“第二步 DSL 生成”“第三步 CPT 生成”与“全流程生成”四类接口，其中第一步接口为 `POST /api/v1/fr/ai-reports/steps/sql/generate`，用于只生成 SQL、执行只读校验并返回样例数据；第二步接口为 `POST /api/v1/fr/ai-reports/steps/dsl/generate`，基于同一任务的 SQL、需求摘要、Excel 分析和表结构生成 ReportDSL，不生成 CPT/XML，不调用 FineReport 预览；第三步接口为 `POST /api/v1/fr/ai-reports/steps/cpt/generate`，基于同一任务的 ReportDSL 确定性生成 CPT、上传 MinIO staging 并返回 FineReport 预览地址。
- 任务模型：`backend/app/models/agent/fr_report/report_task.py`，保存 Excel 分析、需求摘要、ReportDSL、SQL、建表 SQL、生成日志、MinIO staging 路径和预览校验结果。
- Schema：`backend/app/schemas/agent/fr_report/report_dsl.py` 定义第一版 ReportDSL 和 JSON Schema，当前阶段只落地 `detail_table`、`group_table`、`pivot_table` 三类表格报表。
- ReportDSL 需要通过 `reportMeta` 承载模板级语义，包括标题、单位、更新时间、均价、备注和筛选条件；这些信息不能只停留在 Excel `templateAnalysis` 或 `layout.designHints`。
- 服务分层：`backend/app/services/agent/fr_report/` 内按 `ExcelAnalyzer -> RequirementAgent -> DataModelAgent -> SqlAgent -> ReportDesignerAgent -> DslValidator -> CptGenerator -> MinIOStagingService -> PreviewValidator` 串联。
- 分步骤改造时，优先把阶段产物持久化到同一个任务表中，至少保留 `requirement_text`、`source_table_name`、Excel 分析、需求摘要、SQL、SQL 校验结果与日志，方便人工回看和后续步骤接力。
- 第二步生成的 ReportDSL 继续写回同一条 `fr_ai_report_task.report_dsl`，前端预览直接基于 DSL 布局和 SQL 样例数据渲染，用于人工确认版式，不代表 FineReport 运行时预览结果。
- 第二步接口可接收 `dsl_feedback` 做 DSL 版式重生成，只更新需求摘要中的 DSL 修订提示、ReportDSL 和日志，不重复生成 SQL；非标准表格结构优先落入 `layout.designHints.specialRows`，例如最新一天涨跌单行使用 `latest_change_row`。
- 第三步当前只允许从已确认的 `report_dsl` 确定性生成 CPT、写入 MinIO staging 并返回 FineReport 预览地址；不做正式 reportlets 复制、审批发布或覆盖。
- 第三步对接细节见 `docs/fr-ai-report-third-step.md`。CPT XML 按 FineReport 11.5.0 样例生成，数据库连接名来自 `FR_AI_FINEREPORT_DB_NAME`，当前默认 `XcTest`。
- Agent 实现：`RequirementAgent`、`DataModelAgent`、`SqlAgent`、`ReportDesignerAgent` 必须优先通过 `app.core.llm_factory.LLMFactory` 调用已配置大模型生成结构化 JSON；模型不可用或 JSON 校验失败时才使用规则兜底。
- 表结构与 SQL 校验：用户只提供单表或多表表名时，`SqlServerQueryService` 可查询 SQL Server `INFORMATION_SCHEMA.COLUMNS` 获取字段结构并推断字段类型/角色；多表会生成 `tables`、字段来源和 `joinHints` 供 `SqlAgent` 生成 JOIN SQL。`SqlAgent` 生成 SQL 后由同一服务做只读预执行校验，只允许 `SELECT/WITH` 查询，禁止 DDL/DML/存储过程/多语句，参数使用安全默认值绑定，失败时允许 `SqlAgent` 基于错误修复一次。
- SQL ReAct：`SqlReActAgent` 会读取 Excel 模板摘要、真实表结构和 SQL Server TOP 样例数据，生成 SQL 后立即执行只读校验；如果 SQL 不可执行会把错误和样例数据反馈给大模型继续修复，最多迭代 3 轮。对于 Excel 中城市、市场、区域等横向表头，优先通过 ReportDSL/FineReport 横向扩展表达，SQL 保持 `record_date/market/price/change_amt` 等长表结果，不因模板横向表头强制生成大量 `CASE WHEN`、`PIVOT` 或聚合宽表列。
- Excel 模板分析：`ExcelAnalyzer` 需要保留标题、单位、筛选区、更新时间、备注说明、年份/月日格式、涨跌规则和横向扩展候选信息，供 SQL Agent 与 ReportDesignerAgent 共同判断“数据集长表 + 设计器横向扩展”的方案。
- Excel 标题识别不能简单默认第一行，应结合表格区域上方文本、合并单元格、标题关键词和全报表语义打分判断；筛选条件、单位、更新时间、备注等辅助文本不能误判为标题。
- 关键边界：AI/Agent 只能输出结构化 ReportDSL、需求摘要、逻辑表结构和 SQL；FineReport `.cpt`/XML 必须由 `CptGenerator` 确定性生成。
- 存储边界：生成产物只能写入 MinIO `webroot/APP/reportlets_ai_staging/{task_id}/`，不得直接写正式 reportlets。

## 10. SAP 助手

- 接口入口：`backend/app/api/v1/endpoints/agent/sap_assistant.py`，统一挂载到 `/api/v1/sap`。
- 会话接口：`GET /api/v1/sap/assistant/sessions`、`GET /api/v1/sap/assistant/sessions/{id}/messages`，用于前端历史会话恢复。
- 通用知识库入口：`backend/app/api/v1/endpoints/knowledge_bases.py`，统一挂载到 `/api/v1/knowledge-bases`，不得绑定到 SAP 专属命名。
- SAP 模型：`backend/app/models/agent/sap_assistant.py`，保存系统配置、会话、消息、工具调用和证据记录。
- 知识库模型：`backend/app/models/knowledge_base.py`，保存知识库、文档、切片和索引任务。
- SAP 服务分层位于 `backend/app/services/agent/sap_assistant/`：`SapAssistantService -> SapDeepAgentService -> SapToolService -> SapRfcClient`，工具调用必须记录审计和证据。
- SAP RFC 客户端需要兼容未安装 `pyrfc` 的开发环境；未配置时可以返回明确的未配置或演示证据，但不得假装已经真实查询生产系统。
- AI 不允许直接执行任意 SQL 或保存数据库账号；业务数据必须通过 SAP 侧只读 RFC 查询，并采用小批量、多轮调用减少 token 消耗。`safe_table_read` 调用必须显式指定少量字段和高选择性 ranges 条件，默认最多 5 行；禁止空字段或无条件读取宽表。
- 回答必须尽量包含 SAP 系统上下文、使用的工具、证据来源和不确定性说明。
## SAP 助手 Agent 状态约束补充

- SAP 助手聊天入口固定走 `backend/app/services/agent/sap_assistant/deep_agent_service.py`，并复用 `SapToolService -> SapRfcClient` 调用 SAP 侧 `ZFM_AI_*` RFC；该入口按 deepagents 源码思路组装 SAP 专用 Agent，保留摘要压缩、工具调用修复和提示缓存中间件，但禁用 deepagents 默认 todo、文件、shell 和 subagent 工具；历史 LangGraph 和自定义 ReAct 实现已移除。
- SAP 助手服务层必须维护源码调查状态，不能只依赖模型逐轮自由规划。状态至少包含工具调用去重、最近观察摘要、直接赋值证据、计算证据和已发现函数调用。
- 当前源码调查采用“全量拉取、聚焦观察、按需全文”策略：`program_source` 和 `function_source` 在服务层完整读取源码并写入缓存、前端事件、审计和数据库记录，但默认只把与用户问题相关的源码包交给 LLM；只有聚焦源码包不足以判断关键逻辑时，Agent 才能显式调用 `source_full_text` 获取全文。
- SAP 助手调查状态需要维护 `evidence_ledger`、源码对象索引和工具预算；接近预算或递归限制时先压缩状态，再决定继续读取关键源码包、请求 `source_full_text`、跳过可选补强或调用 `finish_investigation`。
- 字段取值、金额计算、字段血缘类问题只有在存在可执行代码证据时才能下确定结论；注释、标题和字段定义不得被改写成事实结论。
- 当调查状态已经满足回答条件时，后端应强制进入总结阶段，避免模型继续重复搜索；当证据不足时，后端应自动选择未执行过的补查工具，而不是把“下一步建议调用工具”交给用户。
