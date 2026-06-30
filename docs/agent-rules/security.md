# 安全与权限规则

本文件适用于修改认证、授权、密钥、外部接口、文件上传、MCP 鉴权和敏感日志。

## 1. 基本原则

- 禁止硬编码真实密钥、密码、API Key、token。
- `.env` 存放本地真实配置，`.env.example` 只放示例值或占位值。
- 日志不能输出完整密码、token、API Key、授权码、身份证件、手机号等敏感信息。
- 外部接口必须有明确鉴权方式。
- 文件上传、下载、预览必须校验用户权限和文件归属。

## 2. JWT 认证

- 登录接口位于 `backend/app/api/v1/endpoints/system/login.py`。
- token 生成逻辑位于 `backend/app/core/security.py`。
- 当前用户依赖位于 `backend/app/api/deps.py`。
- 受保护接口使用 `deps.get_current_user`。
- 管理员接口使用 `deps.get_current_active_superuser`。

## 3. 前端认证

- token 和用户信息由 `frontend/src/store/useAuthStore.ts` 管理。
- Axios 请求拦截器自动注入 `Authorization: Bearer <token>`。
- 401 响应由 Axios 响应拦截器触发退出登录。
- 受保护路由使用 `ProtectedRoute`。
- 管理员路由使用 `AdminRoute`。

## 4. MCP 鉴权

- MCP 端点必须校验 `X-MCP-API-Key`。
- 配置项为 `MCP_API_KEY`。
- 开发环境可以允许空密钥放行，但生产环境必须设置。
- MCP 工具不得直接暴露任意文件读写、系统命令或未授权数据库操作。

## 5. 外部接口

- 外部调用统一使用 `ai-sign` 请求头。
- 可用密钥配置为 `EXTERNAL_API_KEYS`。
- 外部接口依赖 `verify_external_ai_sign` 校验。
- 外部接口返回错误时不暴露内部堆栈、数据库地址、服务密钥。

## 6. 文件与对象存储

- 文件服务通过 MinIO 存储。
- 上传文件应限制文件类型、大小和 content type。
- 下载或预览应使用预签名 URL，不直接暴露内部对象存储凭据。
- 合同、图标、文档类文件需要考虑归属和权限校验。

## 7. 模型与 LangFuse

- LLM API Key 应来自数据库配置或环境变量，不写死在代码中。
- LangFuse 公钥和私钥来自环境变量。
- 追踪内容应避免记录完整敏感业务文本，必要时做脱敏或截断。

## 8. 安全变更检查

涉及以下内容时，最终回复必须说明安全影响和验证方式：

- 登录、token、权限依赖。
- 文件上传、下载、预览。
- 外部 API。
- MCP 工具。
- 模型密钥、LangFuse 密钥、数据库连接。
- 用户、角色、部门、Agent 授权。

## 9. FineReport AI 报表安全规则

- 用户上传 Excel 可继续使用受控临时目录；AI 生成或修改后的 CPT/DSL/版本文件可写入用户指定的 `webroot/APP/reportlets/` 子路径，但必须走版本控制服务，禁止无版本覆盖。
- AI 不允许直接生成 CPT/XML，只允许生成 ReportDSL；CPT 必须由确定性程序生成。
- `publish` 或确认写入不得绕过审核和版本控制覆盖目标 reportlets；写入前必须比较 MinIO 当前对象 hash/lastModified，检测到 FineReport 设计器外部修改时默认阻止，并要求用户选择同步外部修改或归档后覆盖。
- 第三步可写入用户指定 reportlets 路径并覆盖目标 CPT；写入前必须检查 hash/lastModified，写入时必须归档当前/目标文件版本。帆软 MinIO `FR_AI_MINIO_SECRET_KEY` 必须来自本地 `.env`、服务器配置或专用 Access Key，不得写入仓库文档。
- 版本写入、同步外部修改、回档和回收必须受 `FR_AI_REPORT_FILE_PREFIXES` 允许范围约束，并使用同一路径锁串行处理；回收站只做移动归档，不做永久删除。
- 帆软报表文件读取和写回必须使用专用 `FR_AI_MINIO_*`，不得复用平台通用 `MINIO_*`，避免把平台文件权限扩大到帆软 bucket 或反向污染。
- 读取现有 FineReport 报表文件时只能访问 `FR_AI_REPORT_FILE_PREFIXES` 配置的允许目录，不得开放任意 bucket 路径浏览；结构读取接口只能返回后端解析出的元信息、结构摘要、数据集、参数、截断 SQL 和可渲染的结构化报表文档，不返回完整 CPT/XML 原文，不提供默认下载能力。
- 预览校验调用外部 FineReport URL 时不得携带真实密钥，不得在日志中输出敏感参数值。
- SQL Server 表结构查询和数据校验连接信息必须来自环境变量或本地 `.env`，不得硬编码真实账号密码；单表/多表结构查询仅访问 `INFORMATION_SCHEMA.COLUMNS` 元数据，数据校验只允许只读 `SELECT/WITH` 查询，禁止 DDL/DML/存储过程/多语句，并限制样例行数。

## 10. SAP 助手安全规则

- 平台不得直连 SAP 数据库，不得保存 SAP 数据库账号。
- SAP RFC 密码不得写入数据库、文档或代码；系统配置只允许保存环境变量名。
- SAP 表数据读取必须通过 SAP 侧 `ZFM_AI_READ_TABLE_SAFE` 或等价只读 RFC，并在 SAP 内部执行最大行数、分页/分段读取、脱敏和审计。Agent 侧调用必须显式给 1-8 个字段、至少一个高选择性 ranges 条件，默认 `max_rows=5`；遇到 `RFC_READ_TABLE` subrc=6 需要减少字段、降低行数并加强条件，不能把失败当作业务数据不存在。
- AI 不得把自然语言转换成任意 SQL 后直接执行；只能生成查询意图或结构化 ranges。
- 生产系统默认应限制更严：小行数、敏感字段脱敏、必要时人工确认。
- 工具调用日志不得输出完整密码、token、业务敏感字段原值或大批量业务数据。
- ABAP 示例中的 ZILOG 查询、只读取数和审计表必须按现场权限体系审核后才能传输到生产。

## 11. Insight 通用采集安全规则

- Firecrawl、Bocha/博查等外部或本地联网服务地址和 API Key 必须来自环境变量或配置，不得硬编码在业务代码中。
- 手动 URL 抓取接口必须经过登录鉴权，后续批量采集和特殊渠道配置应按管理员权限收口。
- 关键词搜索发现会访问外部搜索结果，必须限制最大结果数和自动抓取数量，避免被误用为无限制爬取入口。
- Insight 抓取结果进入 AI 自动评审，不再以人工审核作为主流程；AI 转正式情报、保留候选或归档噪声都必须写入评审记录、来源证据和情报资产索引，不得绕过后端权限与审计。
- 情报列表、候选情报、报告素材和抓取结果必须按后端权限过滤，不能只靠前端隐藏。
- 企业档案 Excel 导入接口必须经过登录鉴权，仅允许 `.xlsx/.xlsm`，限制文件大小和最大导入行数；后端按企业编码或当前用户同名企业做新增/更新，导入结果只返回结构化统计和行级错误，不回传原始文件内容。
- 日志不得输出完整 API Key、鉴权请求头、Cookie 或登录态信息；特殊渠道如登录态站点必须单独评审权限和审计策略。
- FineReport 数据集预览连接保存数据库账号密码时，接口不得回传密码明文，日志不得输出密码。
- FineReport 数据库驱动字典不保存密钥，可作为平台级共享资源；具体连接仍按用户保存和读取。
- FineReport 数据集预览必须保持只读 SQL 校验和行数限制，不允许执行 DDL、DML、存储过程或多语句。
 
## 泛微流程AI助手安全补充

- 泛微 ecode 接入 AI 平台时不得在前端保存模型 Key，只允许携带外部接口签名 `ai-sign`。
- `/api/v1/weaver/ai-assistant/*` 接口必须校验 `ai-sign`，签名值来自 `EXTERNAL_API_KEYS`，生产环境需要替换默认示例值。
- 泛微 MySQL8 连接信息通过 `WEAVER_DB_CONFIGS` 按环境 key 配置，生产环境必须使用只读账号，不得使用泛微业务库高权限账号。
- ecode 传入的 `env` 只能作为环境选择 key 使用，后端必须在 `WEAVER_DB_CONFIGS` 白名单中查找，不得把它拼接为任意数据库地址。
- ecode 只执行平台返回的结构化白名单动作，不允许执行 AI 生成的任意 JavaScript。
- 第一版不允许 AI 自动保存、提交、审批、删除流程，写入字段前需要用户在嵌入助手页点击确认。
- AI 智审第一版只允许生成预审建议和风险提示；即使规则中存在 `autoReviewMode=auto`，也只能输出 `canAutoApprove` 审计标记，不得绕过泛微权限直接审批。
- 泛微 Java Action 调用智审接口时必须使用 `ai-sign`，默认不得因平台不可用阻断生产流程；如启用高风险阻断，需要先在测试流程验证并保留审计记录。
