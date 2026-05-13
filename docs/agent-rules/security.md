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

- 用户上传 Excel 和生成的 CPT/DSL/SQL/日志统一写入 MinIO staging 路径 `webroot/APP/reportlets_ai_staging/`。
- AI 不允许直接生成 CPT/XML，只允许生成 ReportDSL；CPT 必须由确定性程序生成。
- `publish` 不得绕过审核直接写正式 reportlets，第一版仅标记发布状态并保留 staging 路径。
- 第三步只做 staging 预览，不复制到 `webroot/APP/reportlets/` 正式目录；MinIO `MINIO_SECRET_KEY` 必须来自本地 `.env`、服务器配置或专用 Access Key，不得写入仓库文档。
- 预览校验调用外部 FineReport URL 时不得携带真实密钥，不得在日志中输出敏感参数值。
- SQL Server 表结构查询和数据校验连接信息必须来自环境变量或本地 `.env`，不得硬编码真实账号密码；单表/多表结构查询仅访问 `INFORMATION_SCHEMA.COLUMNS` 元数据，数据校验只允许只读 `SELECT/WITH` 查询，禁止 DDL/DML/存储过程/多语句，并限制样例行数。

## 10. SAP 助手安全规则

- 平台不得直连 SAP 数据库，不得保存 SAP 数据库账号。
- SAP RFC 密码不得写入数据库、文档或代码；系统配置只允许保存环境变量名。
- SAP 表数据读取必须通过 SAP 侧 `ZFM_AI_READ_TABLE_SAFE` 或等价只读 RFC，并在 SAP 内部执行最大行数、分页/分段读取、脱敏和审计。
- AI 不得把自然语言转换成任意 SQL 后直接执行；只能生成查询意图或结构化 ranges。
- 生产系统默认应限制更严：小行数、敏感字段脱敏、必要时人工确认。
- 工具调用日志不得输出完整密码、token、业务敏感字段原值或大批量业务数据。
- ABAP 示例中的 ZILOG 查询、只读取数和审计表必须按现场权限体系审核后才能传输到生产。
