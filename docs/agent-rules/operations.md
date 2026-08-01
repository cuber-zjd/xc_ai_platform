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
- 平台通用 MinIO：`MINIO_ENDPOINT`、`MINIO_ACCESS_KEY`、`MINIO_SECRET_KEY`、`MINIO_BUCKET_NAME`
- Milvus：`MILVUS_HOST`、`MILVUS_PORT`
- LangFuse：`LANGFUSE_PUBLIC_KEY`、`LANGFUSE_SECRET_KEY`、`LANGFUSE_HOST`
- OnlyOffice：`ONLYOFFICE_SERVER_URL`、`ONLYOFFICE_JWT_SECRET`
- Insight 通用采集：`INSIGHT_FIRECRAWL_BASE_URL`、`INSIGHT_FIRECRAWL_API_KEY`、`INSIGHT_FIRECRAWL_TIMEOUT_SECONDS`、`INSIGHT_REVIEW_FULLTEXT_REQUIRED`、`INSIGHT_REVIEW_FULLTEXT_TOP_N`、`INSIGHT_REVIEW_FULLTEXT_CONCURRENCY`、`INSIGHT_BOCHA_API_KEY`、`INSIGHT_BOCHA_BASE_URL`、`INSIGHT_SEARCH_TIMEOUT_SECONDS`、`INSIGHT_OWN_BUSINESS_PROFILE`
- Insight 周期调度：`INSIGHT_SCHEDULER_ENABLED`、`INSIGHT_SCHEDULER_AUTO_START`、`INSIGHT_SCHEDULER_TRIGGER_MODE`、`INSIGHT_SCHEDULER_DAILY_TIME`、`INSIGHT_SCHEDULER_TIMEZONE`、`INSIGHT_SCHEDULER_INTERVAL_SECONDS`、`INSIGHT_SCHEDULER_BATCH_LIMIT`、`INSIGHT_SCHEDULER_DAILY_DISCOVERY_ENABLED`、`INSIGHT_SCHEDULER_DAILY_DISCOVERY_FRESHNESS`、`INSIGHT_SCHEDULER_BAIDU_CONCURRENCY`、`INSIGHT_SCHEDULER_BAIDU_COOLDOWN_MIN_SECONDS`、`INSIGHT_SCHEDULER_BAIDU_COOLDOWN_MAX_SECONDS`、`INSIGHT_SCHEDULER_GROUPED_BATCH_SIZE`、`INSIGHT_SCHEDULER_GROUPED_AI_BATCH_SIZE`、`INSIGHT_SCHEDULER_GROUPED_BATCH_LIMIT`、`INSIGHT_SCHEDULER_GROUPED_INGEST_CONCURRENCY`、`INSIGHT_SCHEDULER_GROUPED_AI_TIMEOUT_SECONDS`、`INSIGHT_SCHEDULER_GROUPED_AI_RETRY_BATCH_SIZE`、`INSIGHT_SCHEDULER_GROUPED_AI_RETRY_CONCURRENCY`、`INSIGHT_DOUBAO_SEARCH_CONNECT_TIMEOUT_SECONDS`、`INSIGHT_DOUBAO_SEARCH_READ_TIMEOUT_SECONDS`、`INSIGHT_SCHEDULER_DAILY_ADAPTER_CHANNEL_CODES`、`INSIGHT_SCHEDULER_DAILY_ADAPTER_HIGH_COVERAGE_CODES`、`INSIGHT_SCHEDULER_DAILY_ADAPTER_CONCURRENCY`、`INSIGHT_SCHEDULER_DAILY_ADAPTER_TOPIC_LIMIT`、`INSIGHT_SCHEDULER_DAILY_ADAPTER_TIMEOUT_SECONDS`、`INSIGHT_SCHEDULER_STARTUP_DELAY_SECONDS`、`INSIGHT_SCHEDULER_ADVISORY_LOCK_ID`、`INSIGHT_SCHEDULER_USER_ID`、`INSIGHT_SCHEDULER_FAILURE_PAUSE_THRESHOLD`
- Insight 飞书集成：`FEISHU_APP_ID`、`FEISHU_APP_SECRET`、`FEISHU_BASE_URL`、`FEISHU_TIMEOUT_SECONDS`、`FEISHU_RETRY_MAX_ATTEMPTS`、`INSIGHT_FEISHU_SYNC_ENABLED`、`INSIGHT_FEISHU_DAILY_BRIEF_ENABLED`、`INSIGHT_FEISHU_BITABLE_APP_TOKEN`、`INSIGHT_FEISHU_BITABLE_TABLE_ID`、`INSIGHT_FEISHU_DOC_FOLDER_TOKEN`、`INSIGHT_FEISHU_DEFAULT_CHAT_ID`、`INSIGHT_FEISHU_DEFAULT_RECEIVE_ID_TYPE`。多维表格字段和记录查询可能超过 10 秒，`FEISHU_TIMEOUT_SECONDS` 默认使用 30 秒；同步失败日志必须保留异常类型和请求路径，前端应直接展示后端返回的具体原因。
- Insight 独立飞书简报机器人使用 `INSIGHT_FEISHU_BRIEF_ENABLED`、`INSIGHT_FEISHU_BRIEF_APP_ID`、`INSIGHT_FEISHU_BRIEF_APP_SECRET`、`INSIGHT_FEISHU_BRIEF_FOLDER_TOKEN`、`INSIGHT_FEISHU_BRIEF_BOT_NAME`、`INSIGHT_FEISHU_BRIEF_DEFAULT_RECIPIENTS_JSON`、`INSIGHT_FEISHU_BRIEF_TIMEOUT_SECONDS` 和 `INSIGHT_FEISHU_BRIEF_MAX_MATERIALS`。该应用凭证不得复用某个用户身份；只有独立应用凭证、文件夹授权和计划配置均有效时才允许发布。
- 独立飞书简报应用需额外开通云空间目录读取和管理权限（推荐 `drive:drive`）。`INSIGHT_FEISHU_BRIEF_FOLDER_TOKEN` 只配置总根目录，系统在根目录下幂等创建“公司 / 年份 / 周报或月报”目录；月报继续分为“正式稿”和“生成过程”。目录接口权限不足时简报仍可生成，但会回退根目录并在执行记录中保存警告。
- 飞书简报计划由独立到点调度任务执行，不依赖每日采集扫描。上午审阅组在报告生成后收到同一云文档并获得编辑权限，下午正式接收组在计划时间收到修改后的同一链接；待发送下午批次持久化在 `insight_feishu_brief_run`，服务重启后继续执行。
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
- 前端能通过 Vite 代理请求 `/ai-api/v1`。
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
- 帆软专用 MinIO 环境变量：`FR_AI_MINIO_ENDPOINT`、`FR_AI_MINIO_ACCESS_KEY`、`FR_AI_MINIO_SECRET_KEY`、`FR_AI_MINIO_BUCKET_NAME`、`FR_AI_MINIO_SECURE`。这些配置只用于读取现有 `.cpt` / `.frm`、写入用户指定的 `webroot/APP/reportlets/` 目标路径和目标目录下的结构化版本库，不影响平台通用文件存储。
- 报表文件读取环境变量：`FR_AI_REPORT_FILE_PREFIXES` 控制允许扫描的 MinIO 目录，默认 `webroot/APP/reportlets`；`FR_AI_REPORT_FILE_EXTENSIONS` 控制文件类型，默认 `.cpt,.frm`。
- SQL Server 校验环境变量：`FR_AI_SQLSERVER_ENABLED`、`FR_AI_SQLSERVER_HOST`、`FR_AI_SQLSERVER_PORT`、`FR_AI_SQLSERVER_DATABASE`、`FR_AI_SQLSERVER_USER`、`FR_AI_SQLSERVER_PASSWORD`、`FR_AI_SQLSERVER_QUERY_TIMEOUT_SECONDS`、`FR_AI_SQLSERVER_MAX_ROWS`。
- HR 同步数据库环境变量：`HR_SYNC_MSSQL_HOST`、`HR_SYNC_MSSQL_PORT`、`HR_SYNC_MSSQL_DATABASE`、`HR_SYNC_MSSQL_USER`、`HR_SYNC_MSSQL_PASSWORD`、`HR_SYNC_MSSQL_ODBC_DRIVER`、`HR_SYNC_MSSQL_TIMEOUT_SECONDS`。Linux 服务器缺少 ODBC 运行库时自动改用 `pymssql`，不得因此跳过人员状态同步。
- `FR_AI_SQLSERVER_ENABLED=false` 时跳过数据 SQL 校验；启用后用于 FineReport AI 报表生成链路中的只读 SQL Server 预执行校验。
- 用途：AI 报表生成后调用 FineReport 预览 URL 校验 HTTP 状态和页面报错信息。
- 未配置时：生成任务仍可完成，`PreviewValidator` 会返回 warning 并跳过 HTTP 校验。
- 新增后端依赖：`openpyxl`，用于 `ExcelAnalyzer` 读取 `.xlsx` 文件。
- Insight 报告 PDF 导出依赖 `reportlab`，导出服务会优先注册 Windows 中文字体 `NotoSansSC-VF.ttf` / `msyh.ttc` / `simhei.ttf` / `simsun.ttc`，确保中文 PDF 可读；DOCX 通用报告导出依赖 `python-docx`，当前生成可编辑 Word 文件；DOCX 官方模板套版和 XLSX 套版导出仍未接入。

## 8. SAP 助手配置

- SAP 助手后端代码兼容未安装 `pyrfc` 的开发环境；真实连接 SAP ECC 时需要安装 SAP NetWeaver RFC SDK 和 Python `pyrfc`。
- 当前 Python 依赖固定使用 `pyrfc==3.3.1`；Windows 还必须把 SAP NetWeaver RFC SDK 的 `nwrfcsdk\lib` 加入系统 `PATH`，或配置 `SAPNWRFC_HOME=D:\sap\nwrfcsdk` / `SAP_NWRFC_LIB_DIR=D:\sap\nwrfcsdk\lib`；Linux 需要把 `/opt/sap/nwrfcsdk/lib` 加入 `LD_LIBRARY_PATH`。
- Windows 还需要安装 x64 版 Microsoft Visual C++ 2013 Redistributable。若 `sapnwrfc.dll` 存在但仍提示 `_cyrfc` DLL 找不到，优先检查 `C:\Windows\System32\MSVCR120.dll` 和 `C:\Windows\System32\MSVCP120.dll` 是否存在。
- 验证命令：`cd backend && uv run python -c "from pyrfc import Connection; print(Connection)"`。如果提示 `_cyrfc` DLL 找不到，说明 Python 包已安装但 SAP NWRFC SDK 未配置。
- SAP RFC 用户和密码必须通过环境变量提供，例如 `SAP_PRD_800_USER`、`SAP_PRD_800_PASSWORD`，管理页面只保存这些环境变量名。
- SAP 系统配置入口为 `/admin/sap-systems`，接口为 `/ai-api/v1/sap/systems`。
- ABAP RFC 示例文件位于 `docs/sap-rfc/`，生产部署前需要在 SAP 侧补充审计表、权限对象、返回量控制和 ZILOG 真实查询逻辑。
- 通用知识库接口为 `/ai-api/v1/knowledge-bases`，文件写入 MinIO，切片和索引元数据写 PostgreSQL；后续接入真实向量检索时使用现有 Milvus 服务。

## 9. 模型服务代理配置

- 后端模型调用统一经过 `backend/app/core/llm_factory.py`，不得在业务代码里绕过工厂直接实例化 `ChatOpenAI`。
- Insight 情报资产 RAG 使用 `sys_model.model_type=embedding` 的模型配置；当前默认补齐火山方舟 `doubao-embedding-vision-251215`，调用 `/api/v3/embeddings/multimodal`，Key 和 base_url 继承已有火山引擎模型配置。
- 代理策略由 `LLM_PROXY_MODE` 控制：`auto` 为默认值；`off` 表示模型调用忽略系统代理；`env` 表示使用 `HTTP_PROXY`、`HTTPS_PROXY`、`ALL_PROXY` 及其小写形式；`url` 表示只使用 `LLM_PROXY_URL`。
- `auto` 模式下，如果配置了 `LLM_PROXY_URL`，模型调用使用该显式代理并忽略系统代理；如果未配置，则兼容系统代理环境变量。这样本地无代理可以直连，服务器有代理也可以按需接入。
- 如果服务器使用 SOCKS 代理，必须使用 `socks5://host:port`，不要使用 `socks://host:port`；LLM 工厂会将遗留的 `socks://` 自动规范为 `socks5://`，避免 `ChatOpenAI` 初始化时报 `Unknown scheme for proxy URL`。
- 后端依赖已启用 `httpx[socks]`，用于支持 HTTPX/OpenAI 客户端通过 SOCKS 代理访问外部模型服务。
- 推荐部署策略：本地 `.env` 保持 `LLM_PROXY_MODE=auto` 且不配置 `LLM_PROXY_URL`；服务器如果必须走代理，配置 `LLM_PROXY_MODE=url` 和 `LLM_PROXY_URL=socks5://127.0.0.1:7897`；服务器如果全局代理会干扰模型服务，配置 `LLM_PROXY_MODE=off`。

## 10. Insight 通用采集配置

- Insight 第一阶段通用网页抓取通过本地 Firecrawl 服务完成，接口由 `INSIGHT_FIRECRAWL_BASE_URL` 指定，例如 `http://127.0.0.1:3002`。
- 如 Firecrawl 启用 API Key，使用 `INSIGHT_FIRECRAWL_API_KEY` 配置；未启用时留空。
- 抓取超时由 `INSIGHT_FIRECRAWL_TIMEOUT_SECONDS` 控制，默认 30 秒。
- 搜索命中在最终 AI 评审前默认补抓正文，由 `INSIGHT_REVIEW_FULLTEXT_REQUIRED=true` 开启；每次监测优先补抓数量由 `INSIGHT_REVIEW_FULLTEXT_TOP_N` 控制，默认 3；跨监测任务并发由 `INSIGHT_REVIEW_FULLTEXT_CONCURRENCY` 控制，默认 6。
- 政府、交易所等静态页面优先尝试受控直接 HTTP 抽取；其他页面在 Firecrawl 超时或正文过短时降级直接抽取。直接抽取最多跟随 5 次重定向、响应体上限 5MB，并阻断本机、链路本地和 RFC1918 内网目标。
- 手动 URL 抓取接口为 `POST /ai-api/v1/insight/crawler/manual-url`，会创建采集任务、调用 Firecrawl、写入爬取结果和候选情报。
- 关键词搜索发现接口为 `POST /ai-api/v1/insight/crawler/search-discovery`，第一版支持百度发现和 Bocha/博查 API，发现候选 URL 后复用 Firecrawl 正文抽取链路。
- 抓取结果入库前会做 URL 归一、追踪参数清理、标题/摘要清洗、发布时间解析、内容去重和候选主题/类型/标签规则识别；候选列表接口为 `GET /ai-api/v1/insight/intelligence/candidates`。
- 候选审核接口包括 `POST /ai-api/v1/insight/intelligence/candidates/{candidate_id}/promote`、`/reject`、`/ignore`；通过后会写入正式情报、来源证据和审核记录。
- 正式情报查询接口包括 `GET /ai-api/v1/insight/intelligence` 和 `GET /ai-api/v1/insight/intelligence/{intelligence_id}`；第一版权限策略为管理员看全部，普通用户看公开或自己审核/拥有的情报。
- 正式情报维护接口包括 `POST /ai-api/v1/insight/intelligence`、`PUT /ai-api/v1/insight/intelligence/{intelligence_id}` 和 `POST /ai-api/v1/insight/intelligence/{intelligence_id}/sources`；人工新增、编辑和补来源都会写审核记录。
- 可见性授权接口包括 `GET/POST /ai-api/v1/insight/intelligence/{intelligence_id}/visibility-rules`，支持 `user`、`role`、`dept`、`all` 四类主体；用户情报池接口包括 `GET /ai-api/v1/insight/intelligence-pool`、`POST /ai-api/v1/insight/intelligence/{intelligence_id}/pool` 和 `DELETE /ai-api/v1/insight/intelligence/{intelligence_id}/pool/{pool_type}`。
- Bocha/博查 API Key 通过 `INSIGHT_BOCHA_API_KEY` 配置，默认接口根地址为 `INSIGHT_BOCHA_BASE_URL=https://api.bocha.cn`，完整 Web Search 地址为 `/v1/web-search`；未配置 Key 时不要启用 `bocha` 通道。
- 搜索发现超时由 `INSIGHT_SEARCH_TIMEOUT_SECONDS` 控制，默认 30 秒。
  - Insight 全渠道适配器依赖 `beautifulsoup4`、`requests` 和 `playwright`；服务器部署后需要执行 `uv sync` 并安装 Playwright 浏览器运行环境。近半月补数与调度模拟入口为 `uv run python scripts/insight_run_all_channel_adapters.py --mode backfill|simulate-daily|simulate-weekly|simulate-monthly --days 15`，默认把运行报告写入 `backend/storage/insight_adapter_run_reports`，适配器原始输出和运行副作用写入 `backend/storage/insight_adapter_runs`。脚本支持受控并行：`--api-concurrency` 控制百度、博查和 HTTP 适配器，`--playwright-concurrency` 控制 Playwright 站点适配器，同一渠道仍串行，`--adapter-timeout` 控制单渠道超时，`--shard-index/--shard-total` 用于夜间分片补数。正式夜间采集建议在 01:00-06:00 分批执行，失败记录可通过 `/ai-api/v1/insight/quality/adapter-runs` 查询。
  - Insight 测试/烟测/样例数据清理入口为 `uv run python scripts/cleanup_insight_test_data.py`。默认只预览命中数量和样例；确认范围后加 `--execute` 才会软删除候选线索、正式情报、来源证据、报告、资产、向量、图谱、采集任务等关联数据。清理规则只匹配“测试客户、烟测、样例、仅用于测试、smoke=true”等明确测试痕迹，避免因真实网页正文中的普通 `Demo` 或“测试数据”字样误删业务数据。
  - AI 自动评审会默认注入香驰控股有限公司的大豆、玉米精深加工，功能糖、糖醇、植物蛋白、豆粕、粮油和营养健康应用画像；如需补充内部战略、重点客户群或阶段性经营口径，可用 `INSIGHT_OWN_BUSINESS_PROFILE` 配置额外文本，系统会合并进评审上下文。
- Insight 企业微信推送卡片默认使用 `INSIGHT_PUBLIC_BASE_URL=https://ai.xiangchi.com` 拼接报告和情报链接；真实发送仍必须配置 `INSIGHT_WECOM_CORP_ID`、`INSIGHT_WECOM_AGENT_ID`、`INSIGHT_WECOM_SECRET` 并开启 `INSIGHT_WECOM_SEND_ENABLED`。
- Insight 飞书集成默认关闭：`INSIGHT_FEISHU_SYNC_ENABLED=false`、`INSIGHT_FEISHU_DAILY_BRIEF_ENABLED=false`。启用正式情报同步多维表格和飞书云文档日报前，必须填写 `FEISHU_APP_ID`、`FEISHU_APP_SECRET`、`INSIGHT_FEISHU_BITABLE_APP_TOKEN`、`INSIGHT_FEISHU_BITABLE_TABLE_ID`、`INSIGHT_FEISHU_DOC_FOLDER_TOKEN`，如需推送还需填写 `INSIGHT_FEISHU_DEFAULT_CHAT_ID` 或后续接收人配置。
- Insight 手动同步多维表格不依赖 `INSIGHT_FEISHU_SYNC_ENABLED`，只要飞书应用、多维表格 app token 和 table id 配置完整即可使用；该开关控制调度器是否在每日任务中自动同步。管理员可通过 `/insight/schedules` 查看每轮调度日志和 Token 用量，后端日志接口为 `GET /ai-api/v1/insight/scheduler/logs`。
- Insight 飞书简报只由独立简报调度器按 `next_run_time` 执行，通用采集调度器不得重复扫描简报计划。自动周报在计划执行日生成时，素材区间固定为“上一次计划执行日 00:00 至本次计划执行日前一日 23:59:59.999999”；执行前必须先持久化本周期占用和下次执行时间，避免飞书发送成功但数据库回写失败后自动重发。
- 飞书简报的素材截止时间和实际生成时间必须分别记录和渲染：显式指定历史素材周期时，只影响 `period_start/period_end`，不得把素材截止日期写成文档生成日期或执行记录的 `started_at`。
- Insight 服务器上线前可执行环境自检脚本：`cd backend && uv run python scripts/insight_env_check.py`，Windows 也可执行 `backend/scripts/insight_env_check.ps1`。脚本会检查 Python、PostgreSQL、Redis、Milvus、Playwright、Insight 必需表、核心渠道、调度器配置、模型配置、目录写入权限和外部连通性；默认不触发付费搜索，只有显式增加 `--probe-paid` / `-ProbePaid` 时才调用博查真实搜索。
- Insight 生产调度策略的本地批量验证入口为 `uv run python scripts/insight_run_due_monitor_configs_once.py --limit 20 --days 2`，它调用 `monitor_execution_service.run_due_monitor_configs`，保留“基础渠道先跑、博查/豆包分组补充、到期监测配置分批执行”的真实调度策略；`--days` 只覆盖本次时间窗，不修改正式调度配置。
- Insight 正式每日调度以“每日全覆盖发现 + 信号深挖 + 周期补漏”运行：每日发现不受 `INSIGHT_SCHEDULER_BATCH_LIMIT` 限制，百度资讯逐对象低并发执行，博查和豆包按同类对象合并查询；批量上限只限制较重的垂直站点深挖。上述旧批量脚本只验证深挖层，不代表完整每日调度。
- 博查与豆包使用独立分组：博查按 `INSIGHT_SCHEDULER_GROUPED_BATCH_SIZE` 聚合，豆包按较小的 `INSIGHT_SCHEDULER_GROUPED_AI_BATCH_SIZE` 聚合。豆包联网搜索总时限由 `INSIGHT_SCHEDULER_GROUPED_AI_TIMEOUT_SECONDS` 控制，连接与流式读取分别由 `INSIGHT_DOUBAO_SEARCH_CONNECT_TIMEOUT_SECONDS`、`INSIGHT_DOUBAO_SEARCH_READ_TIMEOUT_SECONDS` 控制；超时后按 `INSIGHT_SCHEDULER_GROUPED_AI_RETRY_BATCH_SIZE` 拆成更小组，并按 `INSIGHT_SCHEDULER_GROUPED_AI_RETRY_CONCURRENCY` 受控并行补偿，成功子组继续入库。入库并发由 `INSIGHT_SCHEDULER_GROUPED_INGEST_CONCURRENCY` 控制，避免正文补抓和 AI 评审长时间占满数据库连接池。相同 URL 已有有效正文时直接复用，PDF 等当前不支持的正文类型快速保留为候选并记录跳过原因。
- 重点垂直渠道不再依赖到期监测对象轮转。`INSIGHT_SCHEDULER_DAILY_ADAPTER_CHANNEL_CODES` 中的头条、搜狐、腾讯、新浪财经和食品行业渠道每天进入轻量采集池；高覆盖渠道按全部核心业务主题执行，其余渠道每天轮转 `INSIGHT_SCHEDULER_DAILY_ADAPTER_TOPIC_LIMIT` 个相关主题。不同渠道按 `INSIGHT_SCHEDULER_DAILY_ADAPTER_CONCURRENCY` 低并发执行，同一渠道严格串行并保留适配器冷却、失败审计和重试。周期深挖会跳过已由每日轻量池负责的渠道，避免同一夜重复调用。
- Insight 按自然日精确补采使用 `uv run python scripts/insight_run_daily_discovery_once.py --start-date YYYY-MM-DD --end-date YYYY-MM-DD`。该入口复用正式每日发现策略，结束日期包含当天；搜索命中先做时间过滤，正文补抓解析出真实发布时间后还会二次校验，越界或仍无日期的结果只保留采集审计，不进入候选、正式情报和资产链路。
- 搜索结果时间只作为未核验线索写入 `crawl_metadata.publication_time`。正文补抓后优先从页面元数据、JSON-LD、文章头部和 URL 识别真实发布时间，并记录 `source/verified/search_published_at`；正文叙述中的日期属于弱线索，不得推动普通媒体进入正式情报。每日滚动窗口同样在正文补抓后再次校验，避免旧文章因“刚刚”或采集时间进入当日情报。
- Insight 首页看板接口为 `GET /ai-api/v1/insight/dashboard`，聚合当前用户可见的正式情报，返回 KPI、近 7 日趋势、来源分布、重点动态和最新情报；权限过滤和隐藏池过滤必须在后端完成。
- Insight 数据源配置需要支持手动和周期采集。第一版数据源类型包括官网、通用网页、百度资讯、博查资讯和博查网页搜索；百度资讯通道需要显式走资讯搜索参数，不应复用普通网页搜索结果。
- 数据源周期配置支持 `manual`、`15m`、`hourly`、`daily` 和自定义 cron。生产环境默认不应依赖后端重启触发采集：`INSIGHT_SCHEDULER_ENABLED=true` 只表示允许调度器运行，`INSIGHT_SCHEDULER_AUTO_START=true` 时 FastAPI 启动后也只是进入定时等待；默认 `INSIGHT_SCHEDULER_TRIGGER_MODE=daily`、`INSIGHT_SCHEDULER_DAILY_TIME=01:00`、`INSIGHT_SCHEDULER_TIMEZONE=Asia/Shanghai`，到点才执行一轮。旧的 `fixed_interval` 只作兼容模式。如未显式开启 `AUTO_START`，应由人工、平台接口或服务器外部定时任务在夜间窗口调用 `/scheduler/run-once` 或 `/scheduler/start`。调度器只读取启用且到期的数据源创建采集任务，每轮写入 `scheduler_tick` 任务日志，并通过 PostgreSQL advisory lock 避免多实例重复执行。周期调度推荐搜索类数据源配置 `crawl_top_n=0`、`create_candidate_from_hits=true`、`enable_llm_filter=true` 和明确的 `filter_prompt`：平台会先做搜索发现、LLM 结果筛选和搜索摘要级 AI 初筛，再把候选入库；正文级深挖由批处理脚本分时执行，避免常驻调度器被慢 URL 阻塞。搜索通道可用但结果被规则或 LLM 全部过滤时，应记录为成功的 0 候选任务，并保留 `filter_summary`、`rejected_items` 和 LLM 判分信息；只有未配置搜索通道或外部通道调用失败时才标记失败。调度器对单个数据源有超时保护，超时后按失败写回该源状态并进入下一源，不允许长期占用 `scheduler_tick`。前端数据源配置页通过 `/ai-api/v1/insight/scheduler/status` 查看运行状态，通过 `/scheduler/run-once` 立即扫描到期任务，通过 `/scheduler/start` 和 `/scheduler/stop` 做运行态控制。连续失败达到 `INSIGHT_SCHEDULER_FAILURE_PAUSE_THRESHOLD` 后数据源会自动暂停周期采集，人工排查后可调用 `/ai-api/v1/insight/data-sources/{data_source_id}/schedule/retry` 加入下一轮调度。
- 数据源筛选配置包括确定性规则和 LLM 筛选提示词。LLM 筛选必须可关闭，筛选失败时按数据源配置决定降级保留或丢弃，并记录过滤原因。
- 御馨及健源第一批实际数据源初始化脚本为 `backend/scripts/seed_insight_data_sources.py`。执行 `uv run python scripts/seed_insight_data_sources.py` 可幂等写入 14 条 `yxjy_` 前缀数据源；追加 `--test` 会代表性测试嘉华官网、御馨大豆蛋白博查资讯和健源新茶饮百度资讯链路。

## 11. Insight Linux 发布方式

- 192.168.14.44 服务器固定使用原 git 工作目录 `/home/xinxi/ai_platform` 部署和运行，不再创建 `ai_platform_releases` 或 `ai_platform_current` 发布目录。
- 部署前必须先确认当前运行进程、端口占用和其他服务，备份原目录或关键配置后再在 `/home/xinxi/ai_platform` 内同步代码、安装依赖、构建前端和重启服务。
- 前后端使用用户级 `ai-platform-backend.service`、`ai-platform-frontend.service` 守护，服务工作目录必须指向 `/home/xinxi/ai_platform/backend` 和 `/home/xinxi/ai_platform/frontend`。
- 要求未登录也能开机启动时，需要管理员执行 `loginctl enable-linger xinxi`；未启用 linger 时，用户级服务只在该用户的 systemd manager 存活期间运行。
- 回滚优先使用部署前备份或 git 历史在 `/home/xinxi/ai_platform` 内恢复。操作前必须精确核验端口和进程归属，不得批量终止服务器上的其他应用。
 
## 泛微流程AI助手环境配置

- `WEAVER_DEFAULT_ENV`：ecode 未传 `env` 时使用的默认泛微环境 key。
- `WEAVER_DB_CONFIGS`：泛微 MySQL8 多环境连接配置，JSON 对象，key 为环境名，例如 `test`、`prod`。
- `WEAVER_DB_CONFIGS.<env>.ssl_disabled`：是否禁用泛微 MySQL TLS，默认 `true`。当前内网 MySQL 不强制安全传输，禁用可避免 PyMySQL 自动 TLS 握手偶发断开；跨网络或生产环境需要 TLS 时设置为 `false`，并通过 `ssl_ca` 配置 CA 文件。
- `WEAVER_DB_CONFIGS.<env>.retry_backoff_base`、`retry_backoff_max`：连接失败后的指数退避秒数，默认分别为 `0.2` 和 `1.5`，用于缩短偶发握手断开后的恢复等待。
- 泛微 MySQL 连接返回前会执行一次 `ping`；握手成功但首个命令断开的连接会被关闭并进入既有重试流程。连接默认启用 `autocommit`，避免只读元数据查询长期占用事务。
- `WEAVER_AI_FIELD_CONFIGS`：字段配置可按环境组织，推荐结构为 `{"test":{"494":[...]}, "prod":{"494":[...]}}`；旧结构 `{"494":[...]}` 仅作为兼容。
- `WEAVER_AI_MODEL_NAME`：泛微流程 AI 助手专用模型名；配置后优先按模型名调用，用于给流程规则理解更强的模型。
- `WEAVER_AI_MODEL_CAPABILITY`：未配置专用模型名时使用的模型能力标签，默认 `complex-reasoning`。
- `WEAVER_AI_ENABLE_REASONING`：模型支持 reasoning 时可开启；本地小模型或不兼容模型建议保持 `false`。
- `WEAVER_AI_FIELD_CONFIG_CACHE_TTL_SECONDS`：泛微字段元数据按 `env + workflowId` 的进程内缓存秒数，默认 `600`；设置为 `0` 可关闭缓存。
- ecode 调用字段配置接口时可携带 `env`：`/ai-api/v1/weaver/ai-assistant/field-config?workflow_id=494&env=test`。
