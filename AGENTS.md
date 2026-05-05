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
- UI 风格遵循项目现有的 Zinc 单色、玻璃拟态、App-in-App 容器和暗色模式兼容约定。

## 6. 文档维护规则

- 如果新增或移动顶层目录，更新 `docs/agent-rules/project-overview.md`。
- 如果新增后端分层、Agent、MCP 或接口规范，更新 `docs/agent-rules/backend.md` 和 `docs/agent-rules/business-flows.md`。
- 如果新增前端功能模块、路由或设计规范，更新 `docs/agent-rules/frontend.md`。
- 如果新增基础设施、端口、环境变量或部署步骤，更新 `docs/agent-rules/operations.md`。
- 如果新增敏感配置、鉴权方式、外部调用或上传下载行为，更新 `docs/agent-rules/security.md`。

## 7. FineReport AI 报表生成约束

- FineReport AI 报表生成必须遵循“AI 只生成 ReportDSL，CPT/XML 只能由确定性程序生成”的边界。
- 生成文件只能写入 MinIO `webroot/APP/reportlets_ai_staging/`，不得直接写正式 reportlets。
