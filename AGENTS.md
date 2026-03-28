# AGENTS.md - AI 平台开发者指南

本文件为在此代码库工作的 AI 编程代理提供开发规范。

---

## 0. 通用规则

- **语言要求**: 所有回复、思考过程及任务清单，均须使用中文
- **前端文本**: 前端页面上显示的文字，必须全部使用中文
- **包管理器**: 前端使用 `pnpm`，后端使用 `uv`
- **架构更新**: 每次如果涉及项目架构的修改，要修改 agents.md 文件，使项目架构文件始终保持最新
- **文档更新**: 设计重大改动，最好进行文档总结，修改了哪些内容
- **代码注释**: 生成注释的时候，使用中文

---

## 1. 项目概览

- **类型**: 全栈 AI 平台，FastAPI 后端 + React/TypeScript 前端
- **后端**: FastAPI + LangGraph + SQLModel (Python 3.11+)
- **前端**: React 19 + Vite + Tailwind CSS v4 + TypeScript
- **数据库**: PostgreSQL + Redis + MinIO + Milvus
- **可观测性**: LangFuse 链路追踪

---

## 2. 构建命令

### 后端

```bash
# 安装依赖（必须使用 uv，不要用 pip）
cd backend
uv sync

# 运行开发服务器
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 使用自定义导入运行（用于 IDE 调试）
uv run python -c "import uvicorn; uvicorn.run('app.main:app', reload=True)"

# 运行测试（如果配置了 pytest）
uv run pytest

# 运行单个测试
uv run pytest path/to/test_file.py::test_function_name -v

# 运行代码检查（如果安装了 ruff）
uv run ruff check .
uv run ruff check path/to/file.py --fix
```

### 前端

```bash
# 安装依赖（必须使用 pnpm，不要用 npm）
cd frontend
pnpm install

# 运行开发服务器
pnpm dev

# 构建生产版本
pnpm build

# 运行代码检查
pnpm lint

# 运行代码检查并自动修复
pnpm lint --fix
```

---

## 3. 代码风格指南

### 后端 (Python)

#### 命名规范
- **文件**: `snake_case` (如 `user_service.py`, `role_service.py`)
- **类**: `PascalCase` (如 `LLMFactory`, `UserService`)
- **变量/函数**: `snake_case` (如 `get_current_user`, `async def process_file`)
- **常量**: `UPPER_CASE` (如 `DEFAULT_TIMEOUT`, `MAX_RETRIES`)

#### 类型注解 (必须)
所有函数必须包含类型注解：
```python
async def get_user_by_id(user_id: int) -> User | None:
    ...

def process_data(items: list[str], config: dict[str, Any]) -> dict[str, Any]:
    ...
```

#### 导入顺序
1. 标准库
2. 第三方包
3. 本地应用导入
```python
import asyncio
from datetime import datetime
from typing import Optional

import loguru
from fastapi import Depends
from sqlmodel import Session, select

from app.core.config import settings
from app.models.system.sys_user import SysUser
```

#### 异步要求
- 所有 I/O 操作必须使用 async/await
- 禁止使用阻塞 I/O (`time.sleep`, `requests.get`) - 使用 `asyncio.sleep`, `httpx`
- 通过 SQLModel 的数据库查询必须 await

#### 错误处理
- 使用 `BizException` 处理业务逻辑错误（而非原始 500 错误）
- 全局异常处理器将所有错误格式化为统一响应：
  ```python
  {
    "code": 200,      # 200=success, non-200=failure
    "msg": "Success",
    "data": {...}
  }
  ```
- 使用 `Result.success()` 和 `Result.fail()` 辅助方法
- 禁止向客户端暴露原始异常

#### 日志
- 使用 `loguru` - 禁止使用 `print()`
- 所有关键路径必须记录日志
- 日志中包含上下文信息 (user_id, request_id)

#### API 响应模式
```python
from app.schemas.result import Result
from app.schemas.page import Page

# 单条数据
return Result.success(data=user)

# 分页列表
return Result.success(data=Page(total=100, items=[...], page=1, size=10))
```

#### Schema 模式 (SQLModel)
使用继承以保持 DRY：
```python
class UserBase(SQLModel):
    email: str
    is_active: bool = True

class User(UserBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    hashed_password: str

class UserRead(UserBase):
    id: int
```

#### 可观测性
- **无追踪，不合并**: 任何 Agent 流程或复杂 Chain 必须集成 LangFuse
- 使用装饰器或中间件进行结构化日志记录
- 请求 ID: 每个请求必须将 `X-Request-ID` 头注入日志
- 使用 `contextvars` 传递用户信息和追踪 ID

#### LLM 工厂模式
禁止硬编码模型名称：
```python
# ✅ 正确
llm = LLMFactory.get_model(type="chat", capability="complex-reasoning")

# ❌ 错误
llm = ChatOpenAI(model="gpt-4")
```

---

### 前端 (TypeScript/React)

#### 命名规范
- **组件**: `PascalCase` (如 `UserProfile.tsx`, `RolePage.tsx`)
- **Hooks**: `camelCase` (如 `useAuth.ts`, `useUserData.ts`)
- **文件**: 工具类用 `kebab-case`，组件用 PascalCase

#### 导入顺序 (必须)
```typescript
// 1. React / 标准库
import { useState, useEffect } from "react";

// 2. 第三方
import { useQuery } from "@tanstack/react-query";
import { cn } from "@/lib/utils";

// 3. 组件
import { Button } from "@/components/ui/button";
import { UserAvatar } from "@/components/common/UserAvatar";

// 4. 类型 / 工具函数
import type { User } from "@/features/user/types";
import { formatDate } from "@/lib/date";
```

#### 组件结构
```tsx
// 1. 导入
import { useState } from "react";
import { cn } from "@/lib/utils";

// 2. 类型
interface Props {
  className?: string;
  userId: number;
}

// 3. 组件
export function UserProfile({ className, userId }: Props) {
  // 4. Hooks
  const { data, isLoading } = useQuery(...);
  
  // 5. 派生状态
  const displayName = data?.name ?? "Unknown";
  
  // 6. Effects
  useEffect(() => { ... }, [userId]);
  
  // 7. 渲染
  if (isLoading) return <Skeleton />;
  
  return (
    <div className={cn("base-style", className)}>
      {displayName}
    </div>
  );
}
```

#### 样式规范
- 使用 Tailwind CSS v4 - 除全局动画外不要自定义 CSS 文件
- 使用 `cn()` 工具函数处理条件类
- 使用语义化 token: `bg-background`, `text-foreground`，不要用硬编码的十六进制颜色
- 优先考虑暗色模式 - 所有组件必须在暗色模式下正常工作

#### 视觉美学
- **极致单色**: 使用 `Zinc` (50-950) 调色板。避免高饱和度颜色（红/蓝/绿），状态指示器除外
- **玻璃拟态**: 侧边栏和主布局应使用圆角 (`rounded-3xl`)、多层阴影、半透明背景 (`bg-white/60 backdrop-blur-2xl`)
- **App-in-App**: 内容区域应为带有阴影边界的嵌套容器，而非全视口白色块

#### 动效与交互
- **微交互**: 按钮、卡片、列表项必须有悬停反馈 (`hover:bg-accent transition-colors duration-200`)
- **平滑过渡**: 路由切换、对话框打开、折叠动画必须平滑 - 禁止生硬切换

#### UI 组件
- 使用 Shadcn/ui 作为所有基础组件: `pnpm dlx shadcn@latest add avatar`
- 在 `components/ui/` 中自定义 - 不要全局覆盖样式
- 图标: 只使用 `lucide-react`（不要使用 material icons 或 font awesome）

#### 状态管理
- 全局状态（用户、主题）: 通过 `useAuthStore` 使用 `Zustand`
- 服务端状态（API 数据）: `TanStack Query`
- API 调用: 使用 `src/api/client.ts` (Axios 封装)

---

## 4. 安全指南

### 后端
- 所有受保护端点使用 JWT 认证
- 使用 `deps.get_current_user` 依赖注入
- 密码必须使用 bcrypt 哈希
- 密钥（API keys, SECRET_KEY）放在 `.env` 中 - 禁止硬编码
- MCP 端点需要 `X-MCP-API-Key` 头

### 前端
- 使用 `useAuthStore` 管理 token
- 使用 API 拦截器自动注入 token
- 处理 401 错误（登出用户）
- 受保护路由使用 `<ProtectedRoute>`

---

## 5. 架构模式

### 后端分层
```
app/
├── api/           # 路由处理（只处理请求/响应）
├── services/      # 业务逻辑（数据库、外部 API、agents）
├── models/        # SQLModel 定义
├── schemas/       # Pydantic schemas（请求/响应）
├── core/          # 配置、安全、日志、中间件
├── db/            # 数据库会话
└── agents/        # LangGraph 定义
```

### 前端结构（基于功能模块）
```
src/
├── features/      # 复杂业务模块
│   └── contract/
│       ├── components/
│       ├── hooks/
│       └── types.ts
├── components/ui/    # Shadcn UI 组件
├── components/common/ # 全局业务组件
└── pages/            # 路由入口
```

---

## 6. MCP 服务开发 (后端)

MCP 服务位于 `app/mcp/servers/`：

```
app/mcp/servers/my_tool/
├── server.py    # 工具 + BaseMCPServer 继承
└── schema.py    # Pydantic 输入/输出 schema
```

规则：
1. 继承自 `BaseMCPServer`
2. 使用 `@register_tool` 装饰器
3. 所有工具必须是异步的
4. 捕获所有异常，返回友好错误
5. 添加安全验证（API Key 验证）

---

## 7. 数据库约定

- Table names: `snake_case`, singular (如 `sys_user`, 不要用 `sys_users`)
- 主键: `id`
- 外键: `target_entity_id` (如 `user_id`)
- 布尔值: `is_动词` (如 `is_active`, `is_deleted`)
- 时间戳: `create_time`, `update_time`
- 所有表必须有标准字段: `id`, `create_time`, `update_time`, `create_by`, `update_by`, `status`
- 使用 SQLModel 继承模式
- 通过 Alembic 进行迁移 - 禁止手动修改生产表

#### 性能提示
- **索引**: 在 WHERE 和 ORDER BY 使用的字段上添加索引
- **JSONB**: 使用 PostgreSQL JSONB 存储半结构化数据（如 Agent 配置、扩展属性）- 不要把数据库当 MongoDB 用
- **外键**: 显式定义外键约束以保证数据完整性

---

## 8. 重要提示

- **禁止使用 print()** - 使用 loguru
- **禁止硬编码密钥** - 使用 `.env`
- **I/O 操作必须使用 async/await**
- **必须使用类型注解**
- **生产代码禁止使用 console.log**
- **统一响应格式** - 必须返回 `Result` 包装
- **分页** - 所有列表端点返回 `Page[T]`
- **追踪 agents** - 使用 LangFuse 进行 AI agent 调试

---

## 9. 测试

- 后端: pytest (当配置后)
- 前端: ESLint 检查代码质量
- 运行单个测试: `uv run pytest path/to/test.py::test_name`
- 前端代码检查: `pnpm lint`

---

## 10. 关键文件参考

| 用途 | 文件 |
|------|------|
| 后端入口 | `backend/app/main.py` |
| 配置 | `backend/app/core/config.py` |
| 认证依赖 | `backend/app/api/deps.py` |
| API 路由 | `backend/app/api/v1/router.py` |
| 前端入口 | `frontend/src/main.tsx` |
| API 客户端 | `frontend/src/api/client.ts` |
| 认证状态 | `frontend/src/store/useAuthStore.ts` |
| 路由 | `frontend/src/router/index.tsx` | |
