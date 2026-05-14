# AGENTS.md - AI 平台协作入口

本文件是 AI 编程代理进入本仓库后的第一阅读入口。先读本文件，再按任务类型阅读 `docs/agent-rules/` 下的分册。

## 0. 必读规则

- 所有回复、思考摘要、任务清单、代码注释和文档均使用中文。
- 前端页面可见文本必须使用中文。
- 后端包管理器固定使用 `uv`，前端包管理器固定使用 `pnpm`。
- 先读代码再行动，优先沿用项目已有目录、命名、接口和组件模式。
- 非用户明确要求，不做无关重构，不回滚他人改动，不提交真实密钥。
- 涉及架构、目录职责、启动方式、核心流程变化时，必须同步更新本文件和相关分册。
- 设计或业务流程发生明显变化时，需要补充文档说明变更点、影响范围和验证方式。

## 1. 按需阅读索引

| 任务类型 | 必读文件 |
| --- | --- |
| 理解项目结构、核心链路、关键入口 | `docs/agent-rules/project-overview.md` |
| 修改后端 API、服务、模型、Agent、MCP | `docs/agent-rules/backend.md` |
| 修改前端页面、组件、路由、状态、样式 | `docs/agent-rules/frontend.md` |
| 修改数据库表、模型字段、数据初始化 | `docs/agent-rules/database.md` |
| 修改启动、环境变量、Docker、部署、测试 | `docs/agent-rules/operations.md` |
| 修改认证、权限、密钥、外部接口、文件上传 | `docs/agent-rules/security.md` |
| 梳理或新增业务流程、Agent 流程 | `docs/agent-rules/business-flows.md` |

## 2. 项目速览

- 项目类型：企业级 AI Agent 编排与管理平台。
- 后端：FastAPI + SQLModel + LangGraph + MCP + LangFuse。
- 前端：React 19 + Vite + TypeScript + Tailwind CSS v4 + Shadcn/ui。
- 基础设施：PostgreSQL、Redis、MinIO、Milvus、ClickHouse、LangFuse、OnlyOffice。
- 后端入口：`backend/app/main.py`。
- 后端总路由：`backend/app/api/v1/router.py`。
- 前端入口：`frontend/src/main.tsx`。
- 前端路由：`frontend/src/router/index.tsx`。
- 基础设施编排：`docker-compose.yml`。

## 3. 常用命令

### 基础设施

```bash
docker compose up -d
docker compose ps
```

### 后端

```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
uv run pytest
uv run ruff check .
```

### 前端

```bash
cd frontend
pnpm install
pnpm dev
pnpm lint
pnpm build
```

## 4. 工作流程

1. 判断任务类型，并阅读本文件索引中对应分册。
2. 使用 `rg` / `rg --files` 或等价方式定位相关文件。
3. 先确认入口、调用链、数据结构，再实施修改。
4. 修改后运行与影响范围匹配的检查命令。
5. 最终回复说明改了什么、如何验证、是否存在风险或后续建议。

## 5. 关键约束

- 后端所有 I/O 操作优先使用 async/await。
- API 返回优先使用统一 `Result` 包装，列表接口优先使用分页结构。
- 生产代码禁止 `print()` 和 `console.log()`。
- Agent 或复杂 Chain 必须考虑 LangFuse 可观测性。
- LLM 模型名称、API Key、外部服务地址不得硬编码在业务代码中。
- MCP 服务必须接入鉴权，并保持工具输入输出 Schema 清晰。
- 前端 API 统一通过 `frontend/src/api/client.ts` 的 Axios 封装。
- 服务端状态使用 TanStack Query，全局认证状态使用 Zustand。
- UI 风格遵循项目现有的浅色玻璃卡片、柔和紫蓝点缀、超圆角容器、App-in-App 分层和暗色模式兼容约定。

## 6. 文档维护规则

- 如果新增或移动顶层目录，更新 `docs/agent-rules/project-overview.md`。
- 如果新增后端分层、Agent、MCP 或接口规范，更新 `docs/agent-rules/backend.md` 和 `docs/agent-rules/business-flows.md`。
- 如果新增前端功能模块、路由或设计规范，更新 `docs/agent-rules/frontend.md`。
- 如果新增基础设施、端口、环境变量或部署步骤，更新 `docs/agent-rules/operations.md`。
- 如果新增敏感配置、鉴权方式、外部调用或上传下载行为，更新 `docs/agent-rules/security.md`。

## 7. FineReport AI 报表生成约束

- FineReport AI 报表生成必须遵循“AI 只生成 ReportDSL，CPT/XML 只能由确定性程序生成”的边界。
- 当前前端交互应优先按分步骤推进，第一步先收集需求、人工修改意见、Excel 和相关表名，完成 SQL 生成与数据预览，再进入后续报表设计和预览发布步骤。
- 第二步通过 `POST /api/v1/fr/ai-reports/steps/dsl/generate` 基于第一步任务产物生成 ReportDSL，并写回同一条任务记录；该步骤不得生成 CPT/XML，也不得调用 FineReport 预览。
- 第三步通过 `POST /api/v1/fr/ai-reports/steps/cpt/generate` 基于同一任务的 ReportDSL 确定性生成 CPT，上传 MinIO staging，并返回 FineReport 预览地址。
- 第二步允许携带 `dsl_feedback` 重新生成 ReportDSL，用于只调整版式和 DSL 预览，不重复跑 SQL。
- 第二步预览为前端基于 ReportDSL 布局和 SQL 样例数据渲染的轻量预览，尤其需要支持 `horizontalExpansion` 横向扩展，不代表 FineReport 运行时预览结果。
- ReportDSL 必须通过 `reportMeta` 承载标题、单位、更新时间、均价、备注和筛选条件等模板级语义；Excel 标题识别应结合全报表语义、合并单元格和表格区域上方文本，不能简单把第一行当标题。
- 对非标准表格需要优先沉淀到 `layout.designHints`：例如“涨跌只保留最新一天、单独一行、放在市场下面价格列表上面”应表达为 `specialRows.latest_change_row`，前端 DSL 预览按该提示渲染。
- FineReport AI 报表任务需要沉淀历史任务和会话上下文；新任务应优先写入 `conversation_id`、`revision_no` 和 `parent_task_id`，便于恢复旧任务、追踪多轮人工修订和后续经验检索。
- 人工反馈应通过结构化反馈记录沉淀为正向样本或待优化样本；第一版只做历史经验积累和后续检索基础，不允许自动改写全局提示词、业务规则或代码。
- SQL 生成应优先服务 FineReport 设计器布局：Excel 中城市、市场、区域等横向表头可通过 ReportDSL/FineReport 横向扩展表达时，SQL 保持 `record_date/market/price/change_amt` 等长表结果，不强行用大量 `CASE WHEN`、`PIVOT` 或聚合转宽表。
- 生成文件只能写入 MinIO `webroot/APP/reportlets_ai_staging/`，不得直接写正式 reportlets。
- 第三步对接文档见 `docs/fr-ai-report-third-step.md`；当前只做 CPT 生成、MinIO staging 上传和 FineReport 预览，不做审批复制或正式 reportlets 发布。
- 第三步默认 MinIO S3 endpoint 为 `192.168.14.41:9000`、bucket 为 `fanruan`，FineReport 预览根地址为 `http://192.168.14.41:1080`，CPT 数据连接名通过 `FR_AI_FINEREPORT_DB_NAME` 配置，当前默认 `XcTest`。

## 8. 当前前端视觉基调

- 全局基调以浅色背景、雾化玻璃卡片、柔和紫蓝渐变和大圆角容器为主，不再使用偏重的纯 Zinc 单色后台感。
- 用户侧与管理后台应共用一致的品牌节奏：悬浮侧边栏、柔和阴影、信息卡片分组、低饱和状态色。
- 新页面优先复用 `app-shell`、`app-stage`、`app-panel`、`app-page`、`app-page-header` 等全局样式类，避免重复手写大段散装容器样式。

## 9. SAP 助手约束

- SAP 助手第一版入口为用户侧 `/sap-assistant`，管理侧 SAP 系统配置入口为 `/admin/sap-systems`。
- SAP 助手后端按智能体归属放在 `backend/app/api/v1/endpoints/agent/sap_assistant.py`、`backend/app/services/agent/sap_assistant/`、`backend/app/models/agent/sap_assistant.py` 和 `backend/app/schemas/agent/sap_assistant.py`。
- SAP 助手核心边界是“AI 组织证据链，SAP 侧 RFC 受控取数”，不得让 AI 直接持有或使用数据库账号。
- SAP 助手聊天入口固定走 `backend/app/services/agent/sap_assistant/deep_agent_service.py`；该文件按 deepagents 源码思路组装 SAP 专用 Agent，复用摘要压缩、工具调用修复和提示缓存中间件，但禁用 deepagents 默认 todo、文件、shell 和 subagent 工具；历史 LangGraph 和自定义 ReAct 实现已移除。
- 所有 SAP 代码、DDIC、样例数据访问优先通过 `ZFM_AI_*` 受控 RFC；示例 ABAP 文件位于 `docs/sap-rfc/`。`zilog_logs` 和 `latest_table_read` 工具完成前不得暴露给 SAP 助手 AI。
- SAP 助手源码调查当前试验“完整源码上下文优先”：Agent 可直接通过 `program_source` / `function_source` 获取完整程序或函数源码交给 AI 自主分析，服务层仍负责工具去重、审计、缓存和证据记录。
- SAP 助手源码调查采用“全量拉取、聚焦观察、按需全文”策略：源码完整进入服务层缓存、审计和前端事件，LLM 默认只接收与问题相关的源码包；聚焦源码包不足时才调用 `source_full_text` 获取全文。
- SAP 助手达到工具或递归预算前应先压缩调查状态，基于强证据、弱证据、缺口和不确定性决定继续读取关键源码包、请求全文、跳过可选补强或调用 `finish_investigation` 总结。
- SAP 系统配置只保存连接定位和环境变量名，不保存 RFC 用户密码明文。
- 表数据查询必须通过只读 RFC，并控制最大行数、分页/分段读取、脱敏和审计；优先多轮小批量获取，避免一次返回过多 token。
- SAP 助手的 `safe_table_read` 必须按“少字段、少行、强条件”使用：显式提供 1-8 个字段、至少一个高选择性 ranges 条件，默认 `max_rows=5`；不得空字段或无条件读取宽表，遇到 subrc=6 需要缩小到 fields<=5、max_rows<=3 后重试。
- 通用知识库能力位于 `/api/v1/knowledge-bases`，设计目标是被 SAP 助手和后续其他智能体复用，不允许写成 SAP 专属 RAG。
- SAP 助手流式协议会推送文本、执行时间线、工具结果、证据片段、系统上下文和流程图，前端必须让用户能看到 AI 当前正在做什么。
