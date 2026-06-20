# AGENTS.md - AI 平台协作入口

本文件是 AI 编程代理进入本仓库后的第一阅读入口。先读本文件，再按任务类型阅读 `docs/agent-rules/` 下的分册。

## 0. 必读规则

- 所有回复、思考摘要、任务清单、代码注释和文档均使用中文。
- 前端页面可见文本必须使用中文。
- Windows PowerShell 中执行命令前默认先设置 UTF-8 编码：`[Console]::InputEncoding=[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false); $OutputEncoding=[System.Text.UTF8Encoding]::new($false); chcp 65001 > $null`；读取中文文件必须显式使用 `Get-Content -Encoding UTF8`，避免中文输出乱码。
- 后端包管理器固定使用 `uv`，前端包管理器固定使用 `pnpm`。
- 先读代码再行动，优先沿用项目已有目录、命名、接口和组件模式。
- 查询项目进度、业务方案、实施计划或阶段拆解时，先检查 `docs/solution-plans/` 是否已有对应 Markdown 方案；方案按业务域目录归档，计划文件使用中文命名；如同时存在 HTML 和 Markdown，优先阅读 Markdown 版以节省上下文。
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
| 查询项目方案、开发计划、阶段进度 | 优先查看 `docs/solution-plans/index.md`，再按业务域阅读 `docs/solution-plans/<业务域>/*.md` |

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
- UI 风格除明确独立设计的业务域外，默认遵循当前 ChatGPT 式极简产品壳与青绿色主题点缀：浅灰侧栏、冷白主内容区、轻描边、克制阴影、适度圆角和现代留白。

## 6. 文档维护规则

- 如果新增或移动顶层目录，更新 `docs/agent-rules/project-overview.md`。
- 如果新增方案、开发计划、验收记录或阶段进度文档，放入 `docs/solution-plans/<业务域>/`，文件名使用中文，并同步更新 `docs/solution-plans/index.md`。
- 如果新增后端分层、Agent、MCP 或接口规范，更新 `docs/agent-rules/backend.md` 和 `docs/agent-rules/business-flows.md`。
- 如果新增前端功能模块、路由或设计规范，更新 `docs/agent-rules/frontend.md`。
- 如果新增基础设施、端口、环境变量或部署步骤，更新 `docs/agent-rules/operations.md`。
- 如果新增敏感配置、鉴权方式、外部调用或上传下载行为，更新 `docs/agent-rules/security.md`。

## 7. FineReport AI 报表生成约束

- FineReport AI 报表生成必须遵循“AI 只生成 ReportDSL，CPT/XML 只能由确定性程序生成”的边界。
- 当前前端交互应优先按分步骤推进，第一步先收集需求、人工修改意见、Excel 和相关表名，完成 SQL 生成与数据预览，再进入后续报表设计和预览发布步骤。
- 第二步通过 `POST /api/v1/fr/ai-reports/steps/dsl/generate` 基于第一步任务产物生成 ReportDSL，并写回同一条任务记录；该步骤不得生成 CPT/XML，也不得调用 FineReport 预览。
- 第三步通过 `POST /api/v1/fr/ai-reports/steps/cpt/generate` 或 AI 草稿 CPT 生成入口，基于已确认的 ReportDSL/快照确定性生成 CPT；写入用户指定的 `webroot/APP/reportlets/` 子路径前必须创建平台结构版本和 CPT 文件版本，并进行外部修改冲突检测。
- 第二步允许携带 `dsl_feedback` 重新生成 ReportDSL，用于只调整版式和 DSL 预览，不重复跑 SQL。
- 第二步预览为前端基于 ReportDSL 布局和 SQL 样例数据渲染的轻量预览，尤其需要支持 `horizontalExpansion` 横向扩展，不代表 FineReport 运行时预览结果。
- ReportDSL 必须通过 `reportMeta` 承载标题、单位、更新时间、均价、备注和筛选条件等模板级语义；Excel 标题识别应结合全报表语义、合并单元格和表格区域上方文本，不能简单把第一行当标题。
- Excel 多层表头解析必须结合合并单元格生成完整字段语义；例如期权填报模板中的 `开仓` + `权利金单价` 应解析为 `开仓权利金单价`，空白尾列不得进入字段列表。
- 期货和期权操作台账是不同沉淀场景：期权应识别为 `option_operation_ledger`，使用 `fr_option_contract_base`、`fr_option_trade_ledger`、权利金、执行价和合约乘数口径，不得落入期货吨数/手、每日收盘价和浮动盈亏模板。
- 对非标准表格需要优先沉淀到 `layout.designHints`：例如“涨跌只保留最新一天、单独一行、放在市场下面价格列表上面”应表达为 `specialRows.latest_change_row`，前端 DSL 预览按该提示渲染。
- FineReport AI 报表任务需要沉淀历史任务和会话上下文；新任务应优先写入 `conversation_id`、`revision_no` 和 `parent_task_id`，便于恢复旧任务、追踪多轮人工修订和后续经验检索。
- 人工反馈应通过结构化反馈记录沉淀为正向样本或待优化样本；第一版只做历史经验积累和后续检索基础，不允许自动改写全局提示词、业务规则或代码。
- SQL 生成应优先服务 FineReport 设计器布局：Excel 中城市、市场、区域等横向表头可通过 ReportDSL/FineReport 横向扩展表达时，SQL 保持 `record_date/market/price/change_amt` 等长表结果，不强行用大量 `CASE WHEN`、`PIVOT` 或聚合转宽表。
- AI 新建或修改后的 CPT 可写入用户指定的 `webroot/APP/reportlets/` 子路径，也可以覆盖目标 CPT；但写入前必须检查当前 MinIO 文件 hash/lastModified，发现 FineReport 设计器外部修改时默认阻止覆盖，并要求同步外部修改或归档当前文件后覆盖。
- 每次写入 CPT 都必须同步生成平台结构版本和 CPT 文件版本；CPT 文件版本归档在目标文件夹下的 `版本库/<报表名>/v0001/` 等结构化目录中，至少包含 `report.cpt`、`report.dsl.json`、`manifest.json` 和 `diff.json`。
- 同一 CPT 路径的生成、覆盖、外部同步、回档和回收必须通过版本控制服务串行化处理；只同步外部修改时不得覆盖当前 CPT，回收时移动到目标目录下 `回收站/<报表名>/<时间>/`。
- 第三步对接文档见 `docs/fr-ai-report-third-step.md`；当前支持 CPT 生成、版本归档、目标路径写入和 FineReport 预览，正式发布或覆盖必须经过用户确认和外部修改检测。
- 帆软报表文件读写使用专用 `FR_AI_MINIO_*` 配置，不复用平台通用 `MINIO_*`；第三步默认 `FR_AI_MINIO_ENDPOINT=192.168.14.41:9000`、`FR_AI_MINIO_BUCKET_NAME=fanruan`，FineReport 预览根地址为 `http://192.168.14.41:1080`，CPT 数据连接名通过 `FR_AI_FINEREPORT_DB_NAME` 配置，当前默认 `XcTest`。
- 现有报表结构读取入口为 `GET /api/v1/fr/ai-reports/files/structure`，只能在线内存读取 `FR_AI_REPORT_FILE_PREFIXES` 允许范围内且当前用户可见的 CPT/FRM；第一版只返回 XML 版本、数据集、连接名、参数、截断 SQL 和 warnings，不返回完整 CPT/XML 原文，不落盘下载。

## 8. 当前前端视觉基调

- 除 `/insight/*` 市场洞察专 app 或用户明确要求的独立视觉外，登录后用户侧与管理后台统一采用接近 ChatGPT 的极简产品壳：浅灰固定侧边栏、冷白主内容区、黑白中性色、轻描边和克制阴影。
- 默认主题点缀色采用当前 SAP 助手确认过的青绿色体系，用于选中态、轻量标签、聚焦态、状态提示和少量品牌强调；不要回退到大面积紫蓝渐变、黑底模块或偏黄旧纸感背景。
- 智能体入口优先通过工作台集中展示，侧边栏可展示常用和最近使用智能体；智能体不强制做成聊天形态，点击后按 `route_path` 跳转到对应页面。
- 助手类智能区域默认采用“聊天优先、上下文隐藏”的交互：第一屏只保留对话流和输入框，结构、工具结果、版本、环境信息、调试信息和待应用操作默认隐藏到弹窗、抽屉或可展开面板中；除非用户明确要求常驻，否则不要把内部状态铺满主界面。
- 新页面优先复用 `app-shell`、`app-sidebar`、`app-stage`、`app-panel`、`app-page`、`app-page-header` 等全局样式类，但视觉应保持中性、简洁、低装饰。

## 9. SAP 助手约束

- SAP 助手第一版入口为用户侧 `/sap-assistant`，管理侧 SAP 系统配置入口为 `/admin/sap-systems`。
- SAP 助手后端按智能体归属放在 `backend/app/api/v1/endpoints/agent/sap_assistant.py`、`backend/app/services/agent/sap_assistant/`、`backend/app/models/agent/sap_assistant.py` 和 `backend/app/schemas/agent/sap_assistant.py`。
- SAP 助手核心边界是“AI 组织证据链，SAP 侧 RFC 受控取数”，不得让 AI 直接持有或使用数据库账号。
- SAP 助手聊天入口固定走 `backend/app/services/agent/sap_assistant/deep_agent_service.py`；该文件按 deepagents 源码思路组装 SAP 专用 Agent，复用摘要压缩、工具调用修复和提示缓存中间件，但禁用 deepagents 默认 todo、文件、shell 和 subagent 工具；历史 LangGraph 和自定义 ReAct 实现已移除。
- 所有 SAP 代码、DDIC 和样例数据访问优先通过 `ZFM_AI_*` 受控 RFC；示例 ABAP 文件位于 `docs/sap-rfc/`。`zilog_logs` 和 `latest_table_read` 工具完成前不得暴露给 SAP 助手 AI。
- SAP 助手源码调查当前试验“完整源码上下文优先”：Agent 可直接通过 `program_source` / `function_source` 获取完整程序或函数源码交给 AI 自主分析，服务层仍负责工具去重、审计、缓存和证据记录。
- SAP 助手源码调查采用“全量拉取、聚焦观察、按需全文”策略：源码完整进入服务层缓存、审计和前端事件，LLM 默认只接收与问题相关的源码包；聚焦源码包不足时才调用 `source_full_text` 获取全文。
- SAP 助手达到工具或递归预算前应先压缩调查状态，基于强证据、弱证据、缺口和不确定性决定继续读取关键源码包、请求全文、跳过可选补强或调用 `finish_investigation` 总结。
- SAP 系统配置只保存连接定位和环境变量名，不保存 RFC 用户密码明文。
- SAP 助手需要先判断问题意图：客户、物料、供应商、发货、开票、订单、库存、采购等业务数据查询优先查 DDIC 和只读数据；只有用户明确给出事务码、程序、函数、接口、字段血缘或计算逻辑时，才优先查事务码或源码。
- 调用 BAPI/RFC 或读取 SAP 表前必须注意内部格式和前导零，例如客户 `KUNNR`、供应商 `LIFNR` 通常 10 位，物料 `MATNR` 在 ECC 通常 18 位，销售/交货/开票凭证 `VBELN`、会计凭证 `BELNR`、采购订单 `EBELN` 通常 10 位，行项目 `POSNR` 通常 6 位；不确定时先查 DDIC 长度和转换出口。
- SAP 助手解释相对日期必须使用当前日期作为基准；用户只说“今年”“本月”或“5月份”且未给年份时，按当前年份/月推导，并转换为 SAP 内部日期范围 `YYYYMMDD`。
- SAP 助手的 `safe_table_read` 必须按“少字段、少行、强条件”使用：显式提供 1-8 个字段、至少一个高选择性 ranges 条件，默认 `max_rows=5`；不得空字段或无条件读取宽表，遇到 subrc=6 需要缩小到 fields<=5、max_rows<=3 后重试。
- SAP 助手支持本轮模型思考模式开关；本地 LM Studio 等模型不需要思考时可关闭，后端会以 `enable_reasoning=false` 调用模型。
- 通用知识库能力位于 `/api/v1/knowledge-bases`，设计目标是被 SAP 助手和后续其他智能体复用，不允许写成 SAP 专属 RAG。
- SAP 助手流式协议会推送文本、执行时间线、工具结果、证据片段、系统上下文和流程图，前端必须让用户能看到 AI 当前正在做什么。

## 10. Insight 研发营销市场洞察平台约束

- Insight 前端入口固定为 `/insight/*`，源码位于 `frontend/src/app/insight/`，保持独立 `InsightLayout` 和 `InsightThemeScope`。
- Insight 后端接口统一挂载到 `/api/v1/insight`，入口位于 `backend/app/api/v1/endpoints/agent/insight/`。
- Insight 后端服务位于 `backend/app/services/agent/insight/`，按 `crawler`、`intelligence`、`visibility`、`report` 等子域拆分。
- Insight 数据模型位于 `backend/app/models/agent/insight/`，Schema 位于 `backend/app/schemas/agent/insight/`。
- 第一阶段优先实现“通用联网采集”：本地 Firecrawl 通用网页抓取、百度搜索发现、Bocha/博查 API 多源查询、采集清洗、候选情报入库，再做情报权限、情报池和报告。
- Insight 周期采集必须按生产级调度系统建设：优先使用 `backend/app/services/agent/insight/scheduler_service.py`，通过 `INSIGHT_SCHEDULER_ENABLED`、扫描间隔、单批上限、连续失败暂停阈值和 advisory lock 控制常驻调度，前端主入口使用 `/api/v1/insight/scheduler/*` 状态、单次扫描、启停接口，并保留最近调度批次、单源失败次数、自动暂停原因和单源重试能力。
- Insight 情报不固定绑定企业，必须支持企业、行业、市场、产品、政策、技术和自定义主题。
- Insight 权限必须在后端完成过滤，不能返回全量情报后仅由前端隐藏。
- Insight 数据源、报告和报告模板都需要保留 `owner_user_id`、`owner_dept_id`、`visibility_scope` 和显式授权规则入口；列表接口必须先按当前用户权限过滤再分页或聚合。
- Insight 报告模板分为个人模板和模板市场：个人模板默认仅本人可见，可发布到市场；市场模板可被复制为个人模板后调整章节、Prompt、数据范围和导出格式。HTML 风格模板优先支持 PDF 导出，Word/Excel 上传模板优先服务 docx/xlsx 套版导出。
- Insight 企业微信推送必须先写入 `insight_notification`，并在创建推送前复用目标报告或情报的后端权限校验；当前阶段只允许 `sent_mock` 模拟发送，接入真实企业微信 API 时不得绕过推送记录、账号映射、回执和失败重试。
- Insight 前端视觉统一通过 `InsightLayout`、`InsightHeader`、`InsightSidebar` 和 `InsightThemeScope` 控制；头部和侧边栏保持固定，页面内容区独立滚动，侧边栏下半部分使用品牌插画背景而不是临时色块。
- Firecrawl、Bocha/博查等外部服务地址、密钥和鉴权信息不得硬编码在业务代码中。
- Insight 企业档案支持通过登录态接口导入 Excel，仅允许 `.xlsx/.xlsm`，后端解析表头并按企业编码或当前用户同名企业做新增/更新，不允许前端绕过权限直接写入。
- Insight 企业档案的“所属公司”必须从系统组织 `sys_company` 选择并保存 `sys_company_id`，不得做成前端自由文本。
 
## 泛微流程AI助手约束

- 泛微流程 AI 助手用于 ecode 嵌入泛微流程发起/处理页面，平台前端入口为 `/weaver/assistant/embed`，源码位于 `frontend/src/features/weaver-ai-assistant/`。
- 泛微流程 AI 填报规则配置页用于 ecode 嵌入泛微流程路径设置/基础信息页，平台前端入口为 `/weaver/assistant/workflow-config`，按 `env + workflow_id` 维护流程特殊填报要求、提示词和工具/技能说明。
- 泛微流程 AI 智审用于审批节点预审和审批建议展示，平台前端入口为 `/weaver/assistant/review`，智审规则配置入口为 `/weaver/assistant/review-config`；泛微后端节点附加操作示例放在 `docs/solution-plans/泛微流程AI助手/java/WeaverAiReviewAction.java`。
- 后端接口统一挂载到 `/api/v1/weaver/ai-assistant`，入口位于 `backend/app/api/v1/endpoints/agent/weaver_ai_assistant.py`，服务层位于 `backend/app/services/agent/weaver_ai_assistant/`。
- 流程规则保存在 `weaver_ai_workflow_rule` 表，聊天接口需要自动加载启用规则进入 AI 上下文，但仍不得突破字段可见、可写和安全边界。
- 智审规则保存在 `weaver_ai_review_rule` 表，智审记录保存在 `weaver_ai_review_record` 表；初版只生成风险等级、检查项、建议结论和建议审批意见，不得直接保存、提交、审批、退回或越权替审。
- 泛微助手模型选择优先读取 `WEAVER_AI_MODEL_NAME`；未配置时按 `WEAVER_AI_MODEL_CAPABILITY` 选择模型，默认 `complex-reasoning`，用于提升流程特殊规则理解能力。
- ecode 侧只保留悬浮图标、iframe 打开、`WfForm` 上下文采集和结构化动作执行；聊天面板、样式、AI 调用和业务逻辑由平台承载。
- 该嵌入页不走平台登录态，接口必须通过 `ai-sign` 校验，生产环境必须配置非默认 `EXTERNAL_API_KEYS`。
- 泛微助手嵌入页聊天优先调用 `/api/v1/weaver/ai-assistant/chat/stream` 获取 SSE 流式文本，最终仍只接收后端白名单结构化动作；`/chat` 保留为非流式兼容入口。
- 泛微助手后端每轮聊天必须注入 `current_date` 日期工具结果，作为“今天、明天、下周一、本月”等相对日期的唯一换算基准。
- AI 只允许返回 `set_field`、`add_detail_row`、`show_message` 等结构化动作；不得返回任意 JavaScript，不得自动保存、提交、审批或删除流程。
