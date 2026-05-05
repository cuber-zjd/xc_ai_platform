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
- SQL Server 校验环境变量：`FR_AI_SQLSERVER_ENABLED`、`FR_AI_SQLSERVER_HOST`、`FR_AI_SQLSERVER_PORT`、`FR_AI_SQLSERVER_DATABASE`、`FR_AI_SQLSERVER_USER`、`FR_AI_SQLSERVER_PASSWORD`、`FR_AI_SQLSERVER_QUERY_TIMEOUT_SECONDS`、`FR_AI_SQLSERVER_MAX_ROWS`。
- `FR_AI_SQLSERVER_ENABLED=false` 时跳过数据 SQL 校验；启用后用于 FineReport AI 报表生成链路中的只读 SQL Server 预执行校验。
- 用途：AI 报表生成后调用 FineReport 预览 URL 校验 HTTP 状态和页面报错信息。
- 未配置时：生成任务仍可完成，`PreviewValidator` 会返回 warning 并跳过 HTTP 校验。
- 新增后端依赖：`openpyxl`，用于 `ExcelAnalyzer` 读取 `.xlsx` 文件。
