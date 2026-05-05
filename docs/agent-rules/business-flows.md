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

入口文件：
- 后端接口：`backend/app/api/v1/endpoints/fr/ai_reports.py`
- 编排服务：`backend/app/services/fr_ai_report/report_generation_service.py`
- ReportDSL：`backend/app/schemas/fr_ai_report/report_dsl.py`
- 任务表：`backend/app/models/fr_ai_report/report_task.py`

流程：
1. 用户通过 `POST /api/v1/fr/ai-reports/generate` 上传 Excel 或填写自然语言需求。
2. `ExcelAnalyzer` 读取 Excel，识别 sheet、表头、样例行、字段类型和字段角色。
3. `RequirementAgent` 通过 `LLMFactory` 基于需求和 Excel 分析输出结构化需求摘要，失败时使用规则兜底。
4. 如果用户只提供 SQL Server 单表或多表表名，`SqlServerQueryService` 先查询 `INFORMATION_SCHEMA.COLUMNS` 获取真实字段结构并推断字段类型/角色；多表场景会生成表别名、字段来源和可推断的 `joinHints`，无法明确识别关联关系时返回 warning，提示用户在需求中补充 JOIN 条件。
5. `DataModelAgent` 通过 `LLMFactory` 在未提供真实表结构时设计逻辑表结构和建表 SQL，并标记 `dataSourceStatus=designed_not_verified`；如果查询到真实表结构则标记为 `provided`。
6. `SqlAgent` 通过 `LLMFactory` 基于真实表结构或逻辑表结构生成查询 SQL，SQL 参数必须使用 `${parameter}` 绑定，校验失败时使用规则 SQL。
7. `SqlServerQueryService` 在启用并配置 SQL Server 后，对生成 SQL 做只读预执行校验，仅允许 `SELECT/WITH`，禁止 DDL/DML/存储过程/多语句，并返回字段、样例行、错误和警告；执行失败时 `SqlAgent` 可基于数据库错误修复一次。
7. `ReportDesignerAgent` 通过 `LLMFactory` 只生成 ReportDSL，不允许输出 CPT/XML；当前阶段仅生成表格类 DSL，不生成柱状图、折线图、饼图等图表型 DSL。
8. `DslValidator` 校验 DSL 完整性、字段一致性、参数绑定、字段类型、格式和聚合规则。
9. `CptGenerator` 以确定性程序生成 FineReport `.cpt` 文件。
10. `MinIOStagingService` 将 CPT、DSL、SQL、建表 SQL 和生成日志写入 `webroot/APP/reportlets_ai_staging/{task_id}/`。
11. `PreviewValidator` 调用 FineReport 预览 URL，返回 `previewUrl`、`errors` 和 `warnings`。
12. `publish` 接口当前只标记任务已发布，仍保留在 staging，不直接写正式 reportlets。
