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
