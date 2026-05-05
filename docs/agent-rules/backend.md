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

- 接口入口：`backend/app/api/v1/endpoints/fr/ai_reports.py`，统一挂载到 `/api/v1/fr/ai-reports`。
- 任务模型：`backend/app/models/fr_ai_report/report_task.py`，保存 Excel 分析、需求摘要、ReportDSL、SQL、建表 SQL、生成日志、MinIO staging 路径和预览校验结果。
- Schema：`backend/app/schemas/fr_ai_report/report_dsl.py` 定义第一版 ReportDSL 和 JSON Schema，当前阶段只落地 `detail_table`、`group_table`、`pivot_table` 三类表格报表。
- 服务分层：`backend/app/services/fr_ai_report/` 内按 `ExcelAnalyzer -> RequirementAgent -> DataModelAgent -> SqlAgent -> ReportDesignerAgent -> DslValidator -> CptGenerator -> MinIOStagingService -> PreviewValidator` 串联。
- Agent 实现：`RequirementAgent`、`DataModelAgent`、`SqlAgent`、`ReportDesignerAgent` 必须优先通过 `app.core.llm_factory.LLMFactory` 调用已配置大模型生成结构化 JSON；模型不可用或 JSON 校验失败时才使用规则兜底。
- 表结构与 SQL 校验：用户只提供单表或多表表名时，`SqlServerQueryService` 可查询 SQL Server `INFORMATION_SCHEMA.COLUMNS` 获取字段结构并推断字段类型/角色；多表会生成 `tables`、字段来源和 `joinHints` 供 `SqlAgent` 生成 JOIN SQL。`SqlAgent` 生成 SQL 后由同一服务做只读预执行校验，只允许 `SELECT/WITH` 查询，禁止 DDL/DML/存储过程/多语句，参数使用安全默认值绑定，失败时允许 `SqlAgent` 基于错误修复一次。
- 关键边界：AI/Agent 只能输出结构化 ReportDSL、需求摘要、逻辑表结构和 SQL；FineReport `.cpt`/XML 必须由 `CptGenerator` 确定性生成。
- 存储边界：生成产物只能写入 MinIO `webroot/APP/reportlets_ai_staging/{task_id}/`，不得直接写正式 reportlets。
