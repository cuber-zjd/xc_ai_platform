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
- 后端总路由：`backend/app/ai-api/v1/router.py`。
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

- FineReport AI 新建报表仍以 ReportDSL 和确定性 CPT 生成作为主链路；已有 CPT 修改走直接文件补丁模式，模型按需读取当前 CPT/XML 片段并生成可审计的 `xml_patch`，由后端版本控制服务校验、归档、确认后写回。
- 当前“AI 新建报表”入口只负责创建一个空白 CPT 并保存到用户指定的 `webroot/APP/reportlets/` 子路径；资料上传、需求解析、SQL、ReportDSL、样式和填报配置都应在打开该空报表后通过右侧小驰侧边栏逐步完成。
- 右侧小驰侧边栏采用受控 ReAct 外壳：先通过大模型语义路由判断普通沟通、修改当前报表、开始生成或保存 CPT，模型不可用或 JSON 无效时才使用保守规则兜底；再在工具注册表内选择只读、待应用修改项或写入工具；只读工具可自动执行，确认待应用修改项、生成 CPT、覆盖、回档和回收必须经过用户确认。
- 小驰能力边界通过后端 `GET /ai-api/v1/fr/ai-reports/agent/capabilities` 暴露，前端只展示工具、风险等级、运行策略和技能说明；已有 CPT 修改只允许 `xml_patch` 直接 CPT XML 补丁，前端技能配置不得扩大权限或绕过版本控制、安全确认和路径白名单。
- 小驰支持类 Skills 的个人开发习惯配置，技能只能影响上下文注入、默认样式、SQL 风格、填报偏好和追问策略；工具仍需后端开发、授权、审计和输入输出 Schema 约束。
- 小驰上下文工程默认按 token 预算裁剪：只注入当前报表摘要、选区、数据集预览字段、最近意图、启用技能和工具观察摘要；不得把完整 CPT/XML、大量样例行或完整历史对话直接塞入模型。已确认应用的修改项不得继续作为下一轮修改参考上下文，当前报表修改应以本轮用户指令和当前报表事实为主。历史经验只能按需检索为普通上下文 payload，不得直接拼进系统提示词或覆盖当前用户指令。
- 第二步通过 `POST /ai-api/v1/fr/ai-reports/steps/dsl/generate` 基于第一步任务产物生成 ReportDSL，并写回同一条任务记录；该步骤不得生成 CPT/XML，也不得调用 FineReport 预览。
- 第三步通过 `POST /ai-api/v1/fr/ai-reports/steps/cpt/generate` 或 AI 草稿 CPT 生成入口，基于已确认的 ReportDSL/快照确定性生成 CPT；写入用户指定的 `webroot/APP/reportlets/` 子路径前必须创建平台结构版本和 CPT 文件版本，并进行外部修改冲突检测。
- 第二步允许携带 `dsl_feedback` 重新生成 ReportDSL，用于只调整版式和 DSL 预览，不重复跑 SQL。
- 第二步预览为前端基于 ReportDSL 布局和 SQL 样例数据渲染的轻量预览，尤其需要支持 `horizontalExpansion` 横向扩展，不代表 FineReport 运行时预览结果。
- ReportDSL 必须通过 `reportMeta` 承载标题、单位、更新时间、均价、备注和筛选条件等模板级语义；Excel 标题识别应结合全报表语义、合并单元格和表格区域上方文本，不能简单把第一行当标题。
- Excel 多层表头解析必须结合合并单元格生成完整字段语义；例如期权填报模板中的 `开仓` + `权利金单价` 应解析为 `开仓权利金单价`，空白尾列不得进入字段列表。
- Excel 解析必须先裁剪真实有效区域，避免被 `XFD` 等样式尾列污染；解析结果需要沉淀 `effectiveRange`、合并表头、公式规则和公式/说明冲突，供 Agent 作为事实证据使用。
- 小驰侧边栏后续生成或修改报表时可接收多附件；Excel 附件进入结构解析，图片、Word、文本等暂作为需求资料上下文保留，不得因非 Excel 附件中断对话。
- 小驰侧边栏对话优先输出“方案草图 + 可开始生成”的推进方式，不应把所有未确认点作为硬阻断；用户明确“开始执行/直接开始做”时，未确认点应转为假设和风险，先在当前报表上下文生成可预览修改，再通过版本控制写入 CPT。
- 小驰面向用户的主回答应优先使用大模型或后续 Agent 生成的自然短回复，避免固定模板腔；执行轨迹、工具结果和风险提示默认折叠展示，不应把内部流程说明当作每轮主回答。
- AI 从需求中识别到的中文业务来源名称不等同于数据库真实表名；只有符合数据库标识符规则的英文/下划线表名才允许进入表结构读取和 SQL 预览。
- 期货和期权操作台账是不同沉淀场景：期权应识别为 `option_operation_ledger`，使用 `fr_option_contract_base`、`fr_option_trade_ledger`、权利金、执行价和合约乘数口径，不得落入期货吨数/手、每日收盘价和浮动盈亏模板。
- 对非标准表格需要优先沉淀到 `layout.designHints`：例如“涨跌只保留最新一天、单独一行、放在市场下面价格列表上面”应表达为 `specialRows.latest_change_row`，前端 DSL 预览按该提示渲染。
- FineReport AI 报表任务需要沉淀历史任务和会话上下文；新任务应优先写入 `conversation_id`、`revision_no` 和 `parent_task_id`，便于恢复旧任务、追踪多轮人工修订和后续经验检索。
- 人工反馈应通过结构化反馈记录沉淀为正向样本或待优化样本；第一版只做历史经验积累和后续检索基础，不允许自动改写全局提示词、业务规则或代码。
- SQL 生成应优先服务 FineReport 设计器布局：Excel 中城市、市场、区域等横向表头可通过 ReportDSL/FineReport 横向扩展表达时，SQL 保持 `record_date/market/price/change_amt` 等长表结果，不强行用大量 `CASE WHEN`、`PIVOT` 或聚合转宽表。
- AI 新建或修改后的 CPT 可写入用户指定的 `webroot/APP/reportlets/` 子路径，也可以覆盖目标 CPT；但写入前必须检查当前 MinIO 文件 hash/lastModified，发现 FineReport 设计器外部修改时默认阻止覆盖，并要求同步外部修改或归档当前文件后覆盖。对已有真实 CPT 的修改主路径是直接修改 CPT XML：后端按需把当前单元格、参数栏、数据集、样式、填报、脚本等相关片段和轻量 XML 索引提供给模型，模型通过 `xml_patch` 返回 XML 片段替换、插入、删除或完整 CPT 替换；后端只在原始 CPT XML 上应用这些 patch，并通过版本控制写回、归档和预览。XML 索引只是省 token 的导航图，不能限制模型读取和修改的内容；需求涉及多处时允许返回多个 patch 或 full_replace。
- 小驰新生成的已有 CPT 待应用修改项只允许确认 `xml_patch`；参数栏、SQL、样式、填报、脚本、单元格和尺寸都必须通过直接 CPT XML patch 表达。面向用户的详情只展示自然语言修改范围和风险提示，不展示原始 JSON 或 XML 片段。
- 小驰 CPT 修改提示词应包含极短 mini-shot，示范按需读取片段、返回 `xml_patch`、说明风险和给出轻量预览补丁；mini-shot 只做行为引导，不得变成固定模板或新的能力限制。中风险和高风险修改必须在前端明确提示用户确认；高风险包括整份 WorkBook 替换、样式表、填报配置、脚本事件和数据集查询等可能影响运行时行为的节点。
- 每次写入 CPT 都必须同步生成平台结构版本和 CPT 文件版本；CPT 文件版本归档在目标文件夹下的 `版本库/<报表名>/v0001/` 等结构化目录中，至少包含 `report.cpt`、`report.dsl.json`、`manifest.json` 和 `diff.json`。
- 同一 CPT 路径的生成、覆盖、外部同步、回档和回收必须通过版本控制服务串行化处理；只同步外部修改时不得覆盖当前 CPT，回收时移动到目标目录下 `回收站/<报表名>/<时间>/`。
- 第三步对接文档见 `docs/fr-ai-report-third-step.md`；当前支持 CPT 生成、版本归档、目标路径写入和 FineReport 预览，正式发布或覆盖必须经过用户确认和外部修改检测。
- 帆软报表文件读写使用专用 `FR_AI_MINIO_*` 配置，不复用平台通用 `MINIO_*`；第三步默认 `FR_AI_MINIO_ENDPOINT=192.168.14.41:9000`、`FR_AI_MINIO_BUCKET_NAME=fanruan`，FineReport 预览根地址为 `http://192.168.14.41:1080`，CPT 数据连接名通过 `FR_AI_FINEREPORT_DB_NAME` 配置，当前默认 `XcTest`。
- 现有报表结构读取入口为 `GET /ai-api/v1/fr/ai-reports/files/structure`，只能在线内存读取 `FR_AI_REPORT_FILE_PREFIXES` 允许范围内且当前用户可见的 CPT/FRM；第一版只返回 XML 版本、数据集、连接名、参数、截断 SQL 和 warnings，不返回完整 CPT/XML 原文，不落盘下载。

## 8. 当前前端视觉基调

- 除 `/insight/*` 市场洞察专 app 或用户明确要求的独立视觉外，登录后用户侧与管理后台统一采用接近 ChatGPT 的极简产品壳：浅灰固定侧边栏、冷白主内容区、黑白中性色、轻描边和克制阴影。
- 默认主题点缀色采用当前 SAP 助手确认过的青绿色体系，用于选中态、轻量标签、聚焦态、状态提示和少量品牌强调；不要回退到大面积紫蓝渐变、黑底模块或偏黄旧纸感背景。
- 智能体入口优先通过工作台集中展示，侧边栏可展示常用和最近使用智能体；智能体不强制做成聊天形态，点击后按 `route_path` 跳转到对应页面。
- 助手类智能区域默认采用“聊天优先、上下文隐藏”的交互：第一屏只保留对话流和输入框，结构、工具结果、版本、环境信息、调试信息和待应用操作默认隐藏到弹窗、抽屉或可展开面板中；除非用户明确要求常驻，否则不要把内部状态铺满主界面。
- 新页面优先复用 `app-shell`、`app-sidebar`、`app-stage`、`app-panel`、`app-page`、`app-page-header` 等全局样式类，但视觉应保持中性、简洁、低装饰。

## 9. SAP 助手约束

- SAP 助手第一版入口为用户侧 `/sap-assistant`，管理侧 SAP 系统配置入口为 `/admin/sap-systems`。
- SAP 助手后端按智能体归属放在 `backend/app/ai-api/v1/endpoints/agent/sap_assistant.py`、`backend/app/services/agent/sap_assistant/`、`backend/app/models/agent/sap_assistant.py` 和 `backend/app/schemas/agent/sap_assistant.py`。
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
- 通用知识库能力位于 `/ai-api/v1/knowledge-bases`，设计目标是被 SAP 助手和后续其他智能体复用，不允许写成 SAP 专属 RAG。
- SAP 助手流式协议会推送文本、执行时间线、工具结果、证据片段、系统上下文和流程图，前端必须让用户能看到 AI 当前正在做什么。

## 10. Insight 研发营销市场洞察平台约束

- Insight 前端入口固定为 `/insight/*`，源码位于 `frontend/src/app/insight/`，保持独立 `InsightLayout` 和 `InsightThemeScope`。
- Insight 后端接口统一挂载到 `/ai-api/v1/insight`，入口位于 `backend/app/ai-api/v1/endpoints/agent/insight/`。
- Insight 后端服务位于 `backend/app/services/agent/insight/`，按 `crawler`、`intelligence`、`visibility`、`report` 等子域拆分。
- Insight 数据模型位于 `backend/app/models/agent/insight/`，Schema 位于 `backend/app/schemas/agent/insight/`。
- 第一阶段优先实现“通用联网采集”：本地 Firecrawl 通用网页抓取、百度搜索发现、Bocha/博查 API 多源查询、采集清洗、候选情报入库，再做情报权限、情报池和报告。
- Insight 周期采集必须按生产级调度系统建设：优先使用 `backend/app/services/agent/insight/scheduler_service.py`，通过 `INSIGHT_SCHEDULER_ENABLED`、扫描间隔、单批上限、连续失败暂停阈值和 advisory lock 控制常驻调度，前端主入口使用 `/ai-api/v1/insight/scheduler/*` 状态、单次扫描、启停接口，并保留最近调度批次、单源失败次数、自动暂停原因和单源重试能力。
- Insight 情报不固定绑定企业，必须支持企业、行业、市场、产品、政策、技术和自定义主题。
- Insight 权限必须在后端完成过滤，不能返回全量情报后仅由前端隐藏。
- Insight 监测配置、报告和报告模板都需要保留 `owner_user_id`、`owner_dept_id`、`visibility_scope` 和显式授权规则入口；列表接口必须先按当前用户权限过滤再分页或聚合。旧 `insight_data_source` 只作历史外键兼容，不再作为用户维护的数据源配置。
- Insight 报告模板分为个人模板和模板市场：个人模板默认仅本人可见，可发布到市场；市场模板可被复制为个人模板后调整章节、Prompt、数据范围和导出格式。HTML 风格模板优先支持 PDF 导出，Word/Excel 上传模板优先服务 docx/xlsx 套版导出。
- Insight 企业微信推送必须先写入 `insight_notification`，并在创建推送前复用目标报告或情报的后端权限校验；当前阶段只允许 `sent_mock` 模拟发送，接入真实企业微信 API 时不得绕过推送记录、账号映射、回执和失败重试。
- Insight 前端视觉统一通过 `InsightLayout`、`InsightSidebar` 和 `InsightThemeScope` 控制；登录后业务页不使用常驻顶层 Header，用户信息与退出入口放在侧边栏底部，主页面根容器不做纵向整页滚动，滚动只放在列表、表格、详情、预览等组件内部。
- Insight 登录后页面默认不展示占位型大标题和解释型小标题；页面主信息、筛选、列表、图表和主要操作优先，次要说明放入弹窗、抽屉、折叠区或详情页。
- Firecrawl、Bocha/博查等外部服务地址、密钥和鉴权信息不得硬编码在业务代码中。
- Insight 渠道库属于系统基础配置，入口放在 `/insight/settings`，仅管理员维护；监测配置是普通业务用户入口，放在 `/insight/monitoring`。调度器直接扫描监测配置，但每次执行必须先生成“本轮采集计划”，按渠道分级、频率、预算、成本和触发条件选择执行渠道，禁止把监测配置与全部渠道源做笛卡尔积全量执行，也不再持久化 800+ 条旧执行源。百度资讯和博查搜索只是两个独立渠道源，不得作为其他网站渠道的统一代理；FoodDaily、WIPO、CNIPA、东方财富等渠道源后续需要逐个接入自己的爬取方式和脚本，并继续经过采集计划与预算控制。旧 `/insight/data-sources` 只做兼容跳转或历史查看。
- Insight 全渠道适配器正式代码位于 `backend/app/services/agent/insight/crawler/channel_adapter_service.py`，预研脚本只作为迁移来源；适配器必须统一输出搜索命中并继续进入搜索去重、AI 自动评审、正式情报、资产、向量和图谱链路。适配器运行审计写入 `insight_channel_adapter_run`，查询入口为 `/ai-api/v1/insight/settings/channels/adapters` 和 `/ai-api/v1/insight/quality/adapter-runs`。近半月补数和日/周/月模拟入口为 `uv run python scripts/insight_run_all_channel_adapters.py --mode <backfill|simulate-daily|simulate-weekly|simulate-monthly> --days 15`；正式补数使用受控并行队列，跨网站并行、同网站串行，API/HTTP 与 Playwright 分池限流，并可用 `--shard-index/--shard-total` 跨夜分片。
- Insight 企业档案支持通过登录态接口导入 Excel，仅允许 `.xlsx/.xlsm`，后端解析表头并按企业编码或当前用户同名企业做新增/更新，不允许前端绕过权限直接写入。
- Insight 企业档案的“所属公司”必须从系统组织 `sys_company` 选择并保存 `sys_company_id`，不得做成前端自由文本。
- Insight 默认搜索发现源当前只保留“百度资讯”和“博查搜索”。每个监测对象默认展示这两类来源，但博查属于消耗点数渠道，执行策略必须按“合并关键词、缓存去重、限额保护、百度资讯优先、百度结果不足或质量不足时再补充博查”设计，禁止按模块、按关键词、按网站笛卡尔积重复调用博查。
- Insight 采集结果主流程采用 AI 自动评审，不再以人工审核为主；AI 评审输出正式情报、候选情报或噪声归档，并同步写入评审记录、情报资产层、向量索引和轻量知识图谱。
- Insight RAG 默认通过情报资产层检索，向量模型使用 `sys_model` 中 `model_type=embedding` 的配置，当前优先火山方舟 `doubao-embedding-vision-251215` 多模态向量接口，密钥继承现有火山配置。
 
## 泛微流程AI助手约束

- 泛微流程 AI 助手用于 ecode 嵌入泛微流程发起/处理页面，平台前端入口为 `/weaver/assistant/embed`，源码位于 `frontend/src/features/weaver-ai-assistant/`。
- 泛微流程 AI 填报规则配置页用于 ecode 嵌入泛微流程路径设置/基础信息页，平台前端入口为 `/weaver/assistant/workflow-config`，按 `env + workflow_id` 维护流程特殊填报要求、提示词和工具/技能说明。
- 泛微流程 AI 智审用于审批节点预审和审批建议展示，平台前端入口为 `/weaver/assistant/review`，智审规则配置入口为 `/weaver/assistant/review-config`；泛微后端节点附加操作示例放在 `docs/solution-plans/泛微流程AI助手/java/WeaverAiReviewAction.java`。
- 后端接口统一挂载到 `/ai-api/v1/weaver/ai-assistant`，入口位于 `backend/app/ai-api/v1/endpoints/agent/weaver_ai_assistant.py`，服务层位于 `backend/app/services/agent/weaver_ai_assistant/`。
- 流程规则保存在 `weaver_ai_workflow_rule` 表，聊天接口需要自动加载启用规则进入 AI 上下文，但仍不得突破字段可见、可写和安全边界。
- 智审规则保存在 `weaver_ai_review_rule` 表，智审记录保存在 `weaver_ai_review_record` 表；初版只生成风险等级、检查项、建议结论和建议审批意见，不得直接保存、提交、审批、退回或越权替审。
- 泛微助手模型选择优先读取 `WEAVER_AI_MODEL_NAME`；未配置时按 `WEAVER_AI_MODEL_CAPABILITY` 选择模型，默认 `complex-reasoning`，用于提升流程特殊规则理解能力。
- ecode 侧只保留悬浮图标、iframe 打开、`WfForm` 上下文采集和结构化动作执行；聊天面板、样式、AI 调用和业务逻辑由平台承载。
- 该嵌入页不走平台登录态，接口必须通过 `ai-sign` 校验，生产环境必须配置非默认 `EXTERNAL_API_KEYS`。
- 泛微助手嵌入页聊天优先调用 `/ai-api/v1/weaver/ai-assistant/chat/stream` 获取 SSE 流式文本，最终仍只接收后端白名单结构化动作；`/chat` 保留为非流式兼容入口。
- 泛微助手后端每轮聊天必须注入 `current_date` 日期工具结果，作为“今天、明天、下周一、本月”等相对日期的唯一换算基准。
- AI 只允许返回 `set_field`、`add_detail_row`、`show_message` 等结构化动作；不得返回任意 JavaScript，不得自动保存、提交、审批或删除流程。
