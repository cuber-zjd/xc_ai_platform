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
- 第三步入口使用 `POST /api/v1/fr/ai-reports/steps/cpt/generate`，基于同一任务的 ReportDSL 确定性生成 CPT、写入 staging 并返回 FineReport 预览地址。
- 第三步当前只做 staging 预览，不做正式 reportlets 复制；对接细节见 `docs/fr-ai-report-third-step.md`。MinIO 对象路径固定为 `webroot/APP/reportlets_ai_staging/{task_id}/report.cpt`，FineReport 预览 `viewlet` 第一版使用 `reportlets_ai_staging/{task_id}/report.cpt`。

入口文件：
- 后端接口：`backend/app/api/v1/endpoints/agent/fr_report.py`
- 编排服务：`backend/app/services/agent/fr_report/report_generation_service.py`
- ReportDSL：`backend/app/schemas/agent/fr_report/report_dsl.py`
- 任务表：`backend/app/models/agent/fr_report/report_task.py`

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
10. `MinIOStagingService` 将 CPT、DSL、SQL、建表 SQL 和生成日志写入 `webroot/APP/reportlets_ai_staging/{task_id}/`。
11. `PreviewValidator` 调用 FineReport 预览 URL，返回 `previewUrl`、`errors` 和 `warnings`。
12. `publish` 接口当前只标记任务已发布，仍保留在 staging，不直接写正式 reportlets。

## 8. SAP 助手流程

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
4. `SapAssistantService` 识别意图、解析系统，并交由 `SapGraphAgentService` 使用 LangGraph 状态机自主选择下一步工具调用或停止总结。
5. `SapToolService` 调用 `SapRfcClient`，再由 SAP 侧 `ZFM_AI_*` RFC 获取事务码、源码、DDIC、ZILOG 或只读分页数据。
6. 每次工具调用写入 `sap_tool_call`，证据写入 `sap_evidence_record`。
7. 如选择知识库，后端通过通用知识库服务检索片段并合并到证据链。
8. 每轮工具结果返回后，LangGraph 决策节点只读取压缩观察、源码关键片段和会话记忆，判断继续调用工具、停止回答或请求人工介入；只有在模型决策失败时才允许使用轻量规则兜底。
9. 对源码定位类问题，可以读取完整源码作为工具产物，但进入 LLM 上下文前必须由服务层抽取可执行证据片段、调用关系和必要摘要，避免反复把全文交给模型。
10. SAP 助手会话需要读取最近消息和证据作为下一轮上下文，不允许只保存不使用；前端通过 `/api/v1/sap/assistant/sessions` 和 `/api/v1/sap/assistant/sessions/{id}/messages` 展示历史会话。
11. 如果达到单轮最大工具步数仍未完成，回答中需要明确说明已达到自动追查上限，并提示用户可以继续追问以接着当前证据链运行。
12. 后端通过 LLM 总结回答；模型不可用时使用规则兜底回答。
13. 前端在主对话气泡内折叠展示执行时间线，让用户在聊天主线中看到 AI 正在做什么；右侧动态工作区不再作为 SAP 助手第一版必需界面。

安全边界：
- 平台不直连 SAP 数据库。
- SAP 系统配置不保存密码明文，只保存环境变量名。
- 生产系统数据查询必须通过 RFC 内部只读逻辑、行数限制、分页/分段读取、脱敏和审计。
## SAP 助手状态化调查补充

- SAP 助手聊天入口当前优先走 `backend/app/services/agent/sap_assistant/deep_agent_service.py`。`graph_agent_service.py` 作为 LangGraph 实验实现保留，用于后续验证状态机降 token 方案；未达到 deepagents 的自主追查效果前不得切为默认入口。
- SAP 助手的源码分析不再依赖单纯 ReAct 循环反复让模型决定下一步；LangGraph 状态需要维护调查进度，包括工具调用去重、最近观察摘要、源码关键证据片段、直接赋值证据、计算证据和发现的函数调用。
- 为减少 token，工具完整结果只推送给前端、审计和数据库持久化；LLM 决策节点只读取压缩后的观察摘要，源码全文读取后由服务层抽取可执行片段和调用关系，再决定是否继续追查或直接总结。
- 涉及字段取值、金额计算或字段血缘的问题，只有找到可执行代码证据后才能给出确定结论。有效证据包括 `SELECT`、`LOOP`、`READ TABLE`、`CALL FUNCTION`、`PERFORM`、赋值和计算语句；注释和 `DATA/TYPES` 定义只能作为线索。
- 如果调查状态已经包含目标字段的可执行赋值或计算证据，应停止继续重复读取和检索并进入总结阶段。
- 同一源码对象的读取需要去重控制，避免在同一程序中来回读取造成 token 和时间浪费；必要时改为追踪真实 `CALL FUNCTION` 或查询 DDIC、日志、只读样例数据补证。
