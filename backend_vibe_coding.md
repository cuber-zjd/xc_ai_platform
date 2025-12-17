# Backend "Vibe Coding" Guide 🚀

> **核心哲学 (Core Philosophy)**:
> **Robust, Scalable, Agentic**. 后端不仅是数据的搬运工，更是智能的编排者。代码必须具备高可维护性、高可观测性，并为 AI Agent 提供强大的基础设施支持。
> **包管理**: **一定要使用 uv**

---

## 1. 架构设计标准 (Architectural Standards)

### 🏗️ 模块化与分层 (Modular & Layered)
*   **Controller (API)**: 仅负责请求接收、参数校验、响应格式化。严禁包含复杂业务逻辑。
*   **Service Layer**: 核心业务逻辑驻留地。Agent 编排、数据库事务、外调接口均在此层。
*   **Model Layer (SQLModel)**: 统一的数据源真理。
*   **Factory Pattern**: 对所有外部 LLM 服务使用工厂模式封装，确保供应商无关性 (Vendor Agnostic)。

### ⚡ Async First (异步优先)
*   所有 I/O 操作（DB 查询、S3 上传、LLM 生成、Redis 存取）**必须**使用 `async/await`。
*   严禁在 `async def` 中调用阻塞式 I/O 函数（如 `time.sleep`, `requests.get`），必须使用 `asyncio.sleep`, `httpx` 等替代方案。

### 🔍 Observability (可观测性)
*   **No Trace, No Merge**. 任何 Agent 流程、复杂 Chain 调用，必须集成 `LangFuse` 或同等 Trace 工具。
*   使用 Decorator 或 Middleware 自动捕获异常并记录结构化日志。

---

## 2. 技术栈与工具链 (Tech Stack & Tooling)

### 🐍 Core Runtime
*   **Language**: Python 3.13+
*   **Framework**: FastAPI
*   **Package Manager**: **uv** (比 poetry/pip 快 10-100 倍)

### 💾 Data & Storage
*   **ORM**: SQLModel (SQLAlchemy + Pydantic 合体)
*   **Vector DB**: Milvus
*   **Object Storage**: MinIO
*   **Cache/Queue**: Redis

### 🤖 AI Engineering
*   **Orchestration**: LangChain v1.1 + LangGraph
*   **Tracing**: LangFuse

---

## 3. 编码规范 (Coding Etiquette)

### 📁 目录结构 (Directory Structure)
保持结构清晰，避免循环依赖。
```plaintext
backend/app/
├── api/                # 路由层
│   └── v1/endpoints/   # 业务接口 (users, chat, auth)
├── core/               # 核心配置 (Config, Security, Factory)
├── services/           # 业务逻辑 (Agent流程, 文件处理)
├── models/             # SQLModel 数据模型
├── db/                 # 数据库连接会话
└── agents/             # LangGraph 定义与 Tools
```

### 📝 命名与写法 (Naming & Syntax)
*   **Files**: snake_case (`user_service.py`)
*   **Classes**: PascalCase (`LLMFactory`)
*   **Variables/Functions**: snake_case (`get_current_user`)
*   **Constants**: UPPER_CASE (`DEFAULT_TIMEOUT`)

### 🛡️ 代码准则 (The Vibe Rules)

#### Rule 1: Schema First
在写 API 之前，先定义 `Directory/Schemas`。
利用 SQLModel 的继承优势：
```python
class UserBase(SQLModel):
    email: str
    is_active: bool = True

class User(UserBase, table=True):  # DB Model
    id: int | None = Field(default=None, primary_key=True)
    hashed_password: str

class UserRead(UserBase):          # API Response
    id: int
```

#### Rule 2: LLM Factory Pattern
严禁硬编码模型名称。
```python
# ✅ GOOD
llm = LLMFactory.get_model(type="chat", capability="complex-reasoning")

# ❌ BAD
llm = ChatOpenAI(model="gpt-4")
```

#### Rule 3: Type Everything
Python 是动态强类型，但我们的代码库要求 **严格的类型提示 (Type Hints)**。
这也让 IDE 的补全飞起。
```python
async def review_contract(file_id: str, user: User) -> ReviewResult:
    ...
```

---

## 4. "Vibe" 检查清单 (Self-Check)

提交代码前，请灵魂拷问自己：
- [ ] **Is it Async?** 所有的 IO 操作都 await 了吗？
- [ ] **Is it Traced?** Agent 的运行过程能在 LangFuse 控制台看到吗？
- [ ] **Is it Typed?** 函数参数和返回值都有类型标注吗？
- [ ] **Is it Secure?** API Key 是不是都在 `.env` 里，而不是代码里？

---

> **记住**: 我们构建的是企业的大脑。它需要像磐石一样稳固 (Robust)，像水一样流畅 (Scalable)。

---

## 5. 统一标准 (Unified Standards)

### 📤 统一响应 (Unified Response)
所有 API **必须** 返回统一的 JSON 格式：
```python
{
  "code": 200,      # 业务状态码 (200=成功, 非200=失败)
  "msg": "Success", # 提示信息
  "data": { ... }   # 业务数据
}
```
使用 `app.schemas.result.Result` 进行封装：
```python
return Result.success(data=user)
```

### 🚨 异常处理 (Exception Handling)
*   **不要** 直接返回 500 错误，捕获已知异常并抛出 `BizException`。
*   全局异常处理器会统一拦截并格式化为标准响应。

### 🪵 日志规范 (Logging)
*   使用 `loguru`。
*   **禁止** 使用 `print()`。
*   关键路径必须有 Log。
### 📄 通用分页 (Standard Pagination)
所有列表查询接口 **必须** 返回 `Page[T]` 结构：
```python
{
  "total": 100,
  "items": [ ... ],
  "page": 1,
  "size": 10
}
```
使用 `app.schemas.page.Page` 进行封装。

### 🔗 中间件与追踪 (Middleware & Tracing)
*   **Request ID**: 每个请求 header 必须包含 `X-Request-ID`，并自动注入到 Logs 中。
*   **Context**: 使用 `contextvars` 传递用户信息和 Trace ID。

