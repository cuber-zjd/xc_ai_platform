# AI Engine Platform (AI 融合平台) - Vibe Coding Guidelines & Project Spec

> **Project Vibe**: Modern, Scalable, Agentic.
> 本文档旨在定义项目的整体架构、技术选型、目录规范及开发准则 (Vibe Coding)。

## 1. 项目愿景 (Overview)

构建一个集成了传统企业管理能力与前沿 AI Agent 能力的综合平台。平台不仅作为独立系统运行，还需具备嵌入第三方系统的能力。

**核心能力：**
*   **基础支撑**：基于 RBAC 的用户/组织/权限管理，支持从 HR 系统同步数据。
*   **AI 引擎**：集成 LangChain v1.1 & LangGraph，支持多 Agent 协同（聊天、工具调用、合同审查等）。
*   **融合架构**：React 前端 + FastAPI 后端，PostgreSQL + Milvus 双数据库。

---

## 2. 技术栈选型 (Tech Stack)

### 2.1 前端 (Frontend)
*   **构建工具**: **Vite + React**
    *   *理由*：Vite 构建速度快，产物纯净，便于 iframe/微前端嵌入。
*   **UI 体系**: **Shadcn/ui** + **Tailwind CSS**
    *   *理由*：高度可定制，符合 Premium Vibe，开发效率高。
    *   *使用*：pnpm dlx shadcn@latest add card 类似这种方式来添加组件
*   **状态管理**: **Zustand** (客户端流式状态) + **TanStack Query** (服务端数据同步)。
*   **包管理**: **pnpm**

### 2.2 后端 (Backend)
*   **Runtime**: **Python 3.13** (使用 **uv** 管理环境与依赖)
*   **Web 框架**: **FastAPI**
*   **AI 核心**: **LangChain v1.1** + **LangGraph**
*   **数据层 (Data Layer)**:
    *   **ORM**: **SQLModel** (结合 SQLAlchemy 与 Pydantic，统一数据模型与 API Schema)。
    *   **业务库**: **PostgreSQL** (AsyncPG 驱动)。
    *   **向量库**: **Milvus**。
*   **基础设施 (Infrastructure)**:
    *   **消息/缓存**: **Redis** (用于 Agent Memory, Celery/Arq 任务队列)。
    *   **对象存储**: **MinIO** (私有化部署，用于存储合同文件、知识库文档)。
    *   **可观测性**: **LangFuse** (用于 Trace、Debug、Prompt 管理)。

---

## 3. 后端架构与目录设计 (Backend Architecture)

采用 **模块化 (Modular)** 结构，并引入 **LLMFactory** 统一管理模型接入。

```plaintext
backend/
├── app/
│   ├── api/
│   │   ├── v1/
│   │   │   ├── endpoints/
│   │   │   │   ├── auth.py
│   │   │   │   ├── users.py
│   │   │   │   ├── depts.py
│   │   │   │   └── chat.py
│   │   │   └── router.py
│   │   └── deps.py             # 依赖注入 (SQLModel Session, Current User)
│   ├── core/
│   │   ├── config.py           # Settings
│   │   ├── security.py
│   │   ├── llm_factory.py      # [NEW] 统一的大模型工厂 (Model Gateway)
│   │   └── events.py
│   ├── db/
│   │   ├── session.py          # SQLModel AsyncEngine
│   │   └── init_db.py
│   ├── models/                 # [SQLModel] 统一模型定义
│   │   ├── user_model.py       # 含 Table=True 及 API Read/Write Schema
│   │   ├── rbac_model.py
│   │   └── agent_log_model.py
│   ├── services/
│   │   ├── auth_service.py
│   │   ├── hr_sync_service.py
│   │   ├── file_service.py     # [NEW] MinIO 交互逻辑
│   │   └── observability.py    # [NEW] LangFuse Trace 封装
│   │
│   │   # === AI Agent 核心区域 ===
│   ├── agents/
│   │   ├── definitions/        # LangGraph Workflows
│   │   │   ├── general_chat/
│   │   │   └── contract_review/
│   │   ├── tools/              # Custom Tools
│   │   └── callbacks/          # LangFuse Callbacks
│   ├── main.py
│   └── uv.lock
├── .env
├── docker-compose.yml          # Postgres, MinIO, Redis, Milvus, LangFuse
├── pyproject.toml
└── README.md
```

### 关键架构说明：
1.  **SQLModel 统一模式**：
    *   不再分离 `models/` (SQLAlchemy) 和 `schemas/` (Pydantic)。
    *   在 `app/models/` 中定义 Base Model，然后通过继承创建 `UserRead`, `UserCreate`, `UserUpdate` 等变体，减少代码重复。
2.  **LLMFactory (核心组件)**：
    *   位于 `app/core/llm_factory.py`。
    *   **职责**：封装所有国产模型的调用细节（OneAPI, DeepSeek, ZhipuAI 等）。
    *   **功能**：统一加载 API Key，统一配置 Proxy，统一注入 LangFuse Callback Handler。
    *   *Usage*: `llm = LLMFactory.get_model(model_name="deepseek-v2", temperature=0.7)`
3.  **MinIO 集成**：
    *   文件上传/下载逻辑封装在 `services/file_service.py`。
    *   Agent 工具（如“读取合同”）不直接操作 S3 API，而是调用 File Service。

---

## 4. 开发规范 (Vibe Coding Rules)

### 4.1 环境启动
*   使用 `uv` 极速初始化：
    ```powershell
    uv venv .venv
    .venv\Scripts\activate
    uv pip install fastapi[all] sqlmodel langgraph langchain-community langchain-openai asyncpg minio redis langfuse
    ```

### 4.2 代码准则
1.  **Schema First (SQLModel)**：在写 API 之前，先思考数据模型。利用 SQLModel 的继承特性来管理 API 的输入输出字段。
2.  **Trace Everything**：所有的 Agent 执行、Chain 调用，**必须** 传入 LangFuse 的 Callback Handler。没有 Trace 的 Agent 是不可维护的。
    ```python
    # 示例
    chain.invoke(input, config={"callbacks": [langfuse_handler]})
    ```
3.  **Secure Factory**：严禁在代码中硬编码 Model Name 或 Key。所有模型获取必须通过 `LLMFactory`，以便在未来需要切换模型供应商时，只需修改 Factory 逻辑。
4.  **Async I/O**：MinIO 文件上传、向量库检索、LLM 生成，全部必须是异步 (`await`) 的。

---

## 5. 基础设施概览（Docker Compose）：

*   **App**: FastAPI Backend, React Frontend
*   **Data**: PostgreSQL (Port 9500), Milvus (Port 9504)
*   **Queue**: Redis (Port 9501)
*   **Storage**: MinIO (Port 9502 API / 9503 Console)
*   **Observability**: LangFuse Server (Port 9506)
