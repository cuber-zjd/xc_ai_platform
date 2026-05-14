# 启动、部署与测试规则

本文件适用于修改启动方式、Docker、环境变量、部署文档和测试流程。

## 1. 本地启动顺序

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
```

### 前端

```bash
cd frontend
pnpm install
pnpm dev
```

## 2. 端口约定

- 后端 API：`8000`。
- 前端 Vite：默认 `5173`。
- PostgreSQL：`9500 -> 5432`。
- Redis：`9501 -> 6379`。
- MinIO API：`9502 -> 9000`。
- MinIO Console：`9503 -> 9001`。
- Milvus：`9504 -> 19530`。
- LangFuse：`9506 -> 3000`。
- ClickHouse HTTP：`9507 -> 8123`。
- OnlyOffice：`9509 -> 80`。

如端口变化，必须同步更新 `docker-compose.yml`、`.env.example`、`README.md` 和本文件。

## 3. 环境变量

后端配置入口：

- `backend/.env`
- `backend/.env.example`
- `backend/app/core/config.py`

重点配置：

- PostgreSQL：`POSTGRES_SERVER`、`POSTGRES_PORT`、`POSTGRES_DB`、`POSTGRES_USER`、`POSTGRES_PASSWORD`
- Redis：`REDIS_HOST`、`REDIS_PORT`
- MinIO：`MINIO_ENDPOINT`、`MINIO_ACCESS_KEY`、`MINIO_SECRET_KEY`、`MINIO_BUCKET_NAME`
- Milvus：`MILVUS_HOST`、`MILVUS_PORT`
- LangFuse：`LANGFUSE_PUBLIC_KEY`、`LANGFUSE_SECRET_KEY`、`LANGFUSE_HOST`
- OnlyOffice：`ONLYOFFICE_SERVER_URL`、`ONLYOFFICE_JWT_SECRET`
- 安全：`SECRET_KEY`、`MCP_API_KEY`、`EXTERNAL_API_KEYS`

## 4. 测试与检查

### 后端

```bash
cd backend
uv run pytest
uv run pytest path/to/test_file.py::test_function_name -v
uv run ruff check .
```

### 前端

```bash
cd frontend
pnpm lint
pnpm build
```

### 联调验证

- 后端 `/` 能返回欢迎信息。
- Swagger/OpenAPI 能访问。
- 登录接口能返回 token。
- 前端能通过 Vite 代理请求 `/api/v1`。
- Docker 服务健康，特别是 PostgreSQL、MinIO、LangFuse。
- 合同上传后后台任务能推进状态。

## 5. Windows 多机开发

如果代码位于网络共享盘，Python 虚拟环境建议放在本机磁盘，例如 `C:\venvs\ai_platform_backend`。同步依赖时可设置：

```powershell
$env:UV_PROJECT_ENVIRONMENT = "C:\venvs\ai_platform_backend"
uv sync
```

## 6. 文档更新

修改以下内容时必须更新文档：

- 新增或变更端口。
- 新增基础设施服务。
- 新增必需环境变量。
- 改变启动命令。
- 改变部署方式。
- 改变测试命令或 CI 流程。

## 7. FineReport 配置

- 新增环境变量：`FINEREPORT_PREVIEW_BASE_URL`。
- FineReport AI 第三步配置详见 `docs/fr-ai-report-third-step.md`；当前已确认 MinIO S3 API endpoint 为 `192.168.14.41:9000`，bucket 为 `fanruan`，FineReport 访问根地址为 `http://192.168.14.41:1080`。
- CPT 数据连接名环境变量：`FR_AI_FINEREPORT_DB_NAME`，当前默认 `XcTest`。
- SQL Server 校验环境变量：`FR_AI_SQLSERVER_ENABLED`、`FR_AI_SQLSERVER_HOST`、`FR_AI_SQLSERVER_PORT`、`FR_AI_SQLSERVER_DATABASE`、`FR_AI_SQLSERVER_USER`、`FR_AI_SQLSERVER_PASSWORD`、`FR_AI_SQLSERVER_QUERY_TIMEOUT_SECONDS`、`FR_AI_SQLSERVER_MAX_ROWS`。
- `FR_AI_SQLSERVER_ENABLED=false` 时跳过数据 SQL 校验；启用后用于 FineReport AI 报表生成链路中的只读 SQL Server 预执行校验。
- 用途：AI 报表生成后调用 FineReport 预览 URL 校验 HTTP 状态和页面报错信息。
- 未配置时：生成任务仍可完成，`PreviewValidator` 会返回 warning 并跳过 HTTP 校验。
- 新增后端依赖：`openpyxl`，用于 `ExcelAnalyzer` 读取 `.xlsx` 文件。

## 8. SAP 助手配置

- SAP 助手后端代码兼容未安装 `pyrfc` 的开发环境；真实连接 SAP ECC 时需要安装 SAP NetWeaver RFC SDK 和 Python `pyrfc`。
- 当前 Python 依赖固定使用 `pyrfc==3.3.1`；Windows 还必须把 SAP NetWeaver RFC SDK 的 `nwrfcsdk\lib` 加入系统 `PATH`，或配置 `SAPNWRFC_HOME=D:\sap\nwrfcsdk` / `SAP_NWRFC_LIB_DIR=D:\sap\nwrfcsdk\lib`；Linux 需要把 `/opt/sap/nwrfcsdk/lib` 加入 `LD_LIBRARY_PATH`。
- Windows 还需要安装 x64 版 Microsoft Visual C++ 2013 Redistributable。若 `sapnwrfc.dll` 存在但仍提示 `_cyrfc` DLL 找不到，优先检查 `C:\Windows\System32\MSVCR120.dll` 和 `C:\Windows\System32\MSVCP120.dll` 是否存在。
- 验证命令：`cd backend && uv run python -c "from pyrfc import Connection; print(Connection)"`。如果提示 `_cyrfc` DLL 找不到，说明 Python 包已安装但 SAP NWRFC SDK 未配置。
- SAP RFC 用户和密码必须通过环境变量提供，例如 `SAP_PRD_800_USER`、`SAP_PRD_800_PASSWORD`，管理页面只保存这些环境变量名。
- SAP 系统配置入口为 `/admin/sap-systems`，接口为 `/api/v1/sap/systems`。
- ABAP RFC 示例文件位于 `docs/sap-rfc/`，生产部署前需要在 SAP 侧补充审计表、权限对象、返回量控制和 ZILOG 真实查询逻辑。
- 通用知识库接口为 `/api/v1/knowledge-bases`，文件写入 MinIO，切片和索引元数据写 PostgreSQL；后续接入真实向量检索时使用现有 Milvus 服务。

## 9. 模型服务代理配置

- 后端模型调用统一经过 `backend/app/core/llm_factory.py`，不得在业务代码里绕过工厂直接实例化 `ChatOpenAI`。
- 代理策略由 `LLM_PROXY_MODE` 控制：`auto` 为默认值；`off` 表示模型调用忽略系统代理；`env` 表示使用 `HTTP_PROXY`、`HTTPS_PROXY`、`ALL_PROXY` 及其小写形式；`url` 表示只使用 `LLM_PROXY_URL`。
- `auto` 模式下，如果配置了 `LLM_PROXY_URL`，模型调用使用该显式代理并忽略系统代理；如果未配置，则兼容系统代理环境变量。这样本地无代理可以直连，服务器有代理也可以按需接入。
- 如果服务器使用 SOCKS 代理，必须使用 `socks5://host:port`，不要使用 `socks://host:port`；LLM 工厂会将遗留的 `socks://` 自动规范为 `socks5://`，避免 `ChatOpenAI` 初始化时报 `Unknown scheme for proxy URL`。
- 后端依赖已启用 `httpx[socks]`，用于支持 HTTPX/OpenAI 客户端通过 SOCKS 代理访问外部模型服务。
- 推荐部署策略：本地 `.env` 保持 `LLM_PROXY_MODE=auto` 且不配置 `LLM_PROXY_URL`；服务器如果必须走代理，配置 `LLM_PROXY_MODE=url` 和 `LLM_PROXY_URL=socks5://127.0.0.1:7897`；服务器如果全局代理会干扰模型服务，配置 `LLM_PROXY_MODE=off`。
