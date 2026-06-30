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
- Insight 通用采集：`INSIGHT_FIRECRAWL_BASE_URL`、`INSIGHT_FIRECRAWL_API_KEY`、`INSIGHT_FIRECRAWL_TIMEOUT_SECONDS`、`INSIGHT_BOCHA_API_KEY`、`INSIGHT_BOCHA_BASE_URL`、`INSIGHT_SEARCH_TIMEOUT_SECONDS`、`INSIGHT_OWN_BUSINESS_PROFILE`
- Insight 周期调度：`INSIGHT_SCHEDULER_ENABLED`、`INSIGHT_SCHEDULER_INTERVAL_SECONDS`、`INSIGHT_SCHEDULER_BATCH_LIMIT`、`INSIGHT_SCHEDULER_STARTUP_DELAY_SECONDS`、`INSIGHT_SCHEDULER_ADVISORY_LOCK_ID`、`INSIGHT_SCHEDULER_USER_ID`、`INSIGHT_SCHEDULER_FAILURE_PAUSE_THRESHOLD`
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
- Insight 首页看板接口为 `GET /ai-api/v1/insight/dashboard`，聚合当前用户可见的正式情报，返回 KPI、近 7 日趋势、来源分布、重点动态和最新情报；权限过滤和隐藏池过滤必须在后端完成。
- Insight 数据源配置需要支持手动和周期采集。第一版数据源类型包括官网、通用网页、百度资讯、博查资讯和博查网页搜索；百度资讯通道需要显式走资讯搜索参数，不应复用普通网页搜索结果。
- 数据源周期配置支持 `manual`、`15m`、`hourly`、`daily` 和自定义 cron。当前正式运行推荐 `INSIGHT_SCHEDULER_ENABLED=true`，`.env.example` 已按开启配置；仅在纯开发调试且不希望消耗外部搜索/抓取额度时手动改为 `false`。调度器只读取启用且到期的数据源创建采集任务，每轮写入 `scheduler_tick` 任务日志，并通过 PostgreSQL advisory lock 避免多实例重复执行。周期调度推荐搜索类数据源配置 `crawl_top_n=0`、`create_candidate_from_hits=true`、`enable_llm_filter=true` 和明确的 `filter_prompt`：平台会先做搜索发现、LLM 结果筛选和搜索摘要级 AI 初筛，再把候选入库；正文级深挖由批处理脚本分时执行，避免常驻调度器被慢 URL 阻塞。搜索通道可用但结果被规则或 LLM 全部过滤时，应记录为成功的 0 候选任务，并保留 `filter_summary`、`rejected_items` 和 LLM 判分信息；只有未配置搜索通道或外部通道调用失败时才标记失败。调度器对单个数据源有超时保护，超时后按失败写回该源状态并进入下一源，不允许长期占用 `scheduler_tick`。前端数据源配置页通过 `/ai-api/v1/insight/scheduler/status` 查看运行状态，通过 `/scheduler/run-once` 立即扫描到期任务，通过 `/scheduler/start` 和 `/scheduler/stop` 做运行态控制。连续失败达到 `INSIGHT_SCHEDULER_FAILURE_PAUSE_THRESHOLD` 后数据源会自动暂停周期采集，人工排查后可调用 `/ai-api/v1/insight/data-sources/{data_source_id}/schedule/retry` 加入下一轮调度。
- 数据源筛选配置包括确定性规则和 LLM 筛选提示词。LLM 筛选必须可关闭，筛选失败时按数据源配置决定降级保留或丢弃，并记录过滤原因。
- 御馨及健源第一批实际数据源初始化脚本为 `backend/scripts/seed_insight_data_sources.py`。执行 `uv run python scripts/seed_insight_data_sources.py` 可幂等写入 14 条 `yxjy_` 前缀数据源；追加 `--test` 会代表性测试嘉华官网、御馨大豆蛋白博查资讯和健源新茶饮百度资讯链路。
 
## 泛微流程AI助手环境配置

- `WEAVER_DEFAULT_ENV`：ecode 未传 `env` 时使用的默认泛微环境 key。
- `WEAVER_DB_CONFIGS`：泛微 MySQL8 多环境连接配置，JSON 对象，key 为环境名，例如 `test`、`prod`。
- `WEAVER_AI_FIELD_CONFIGS`：字段配置可按环境组织，推荐结构为 `{"test":{"494":[...]}, "prod":{"494":[...]}}`；旧结构 `{"494":[...]}` 仅作为兼容。
- `WEAVER_AI_MODEL_NAME`：泛微流程 AI 助手专用模型名；配置后优先按模型名调用，用于给流程规则理解更强的模型。
- `WEAVER_AI_MODEL_CAPABILITY`：未配置专用模型名时使用的模型能力标签，默认 `complex-reasoning`。
- `WEAVER_AI_ENABLE_REASONING`：模型支持 reasoning 时可开启；本地小模型或不兼容模型建议保持 `false`。
- ecode 调用字段配置接口时可携带 `env`：`/ai-api/v1/weaver/ai-assistant/field-config?workflow_id=494&env=test`。
