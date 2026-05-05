# 项目结构与关键入口

本文件用于快速理解项目整体结构、启动入口和模块边界。

## 1. 项目定位

AI Platform 是一个企业级 AI Agent 编排与管理平台，采用前后端分离架构。后端负责 API、认证、数据库、文件服务、Agent 编排、MCP 工具扩展；前端负责管理员后台、用户工作台、合同审查界面和 Agent 入口。

## 2. 顶层结构

```text
ai_platform/
├── backend/                  # FastAPI 后端
├── frontend/                 # React 前端
├── agents/                   # 业务自动化资料或外部规则沉淀
├── docker/                   # Docker 初始化脚本与服务配置
├── docker-compose.yml        # 本地基础设施编排
├── Dockerfile-postgres       # 自定义 PostgreSQL 镜像
├── README.md                 # 项目说明与部署指南
└── docs/agent-rules/         # AI 代理按需阅读规则分册
```

## 3. 后端结构

```text
backend/app/
├── main.py                   # FastAPI 应用入口、生命周期、路由挂载
├── api/                      # API 路由、认证依赖
├── agents/                   # LangGraph Agent 定义
├── core/                     # 配置、安全、日志、中间件、异常
├── db/                       # 数据库引擎、会话、初始化
├── mcp/                      # MCP 管理器、基础类、安全、服务目录
├── models/                   # SQLModel 数据模型
├── schemas/                  # 请求和响应 Schema
├── services/                 # 业务服务层
└── scripts/                  # 辅助脚本
```

关键入口：

- `backend/app/main.py`：应用启动、初始化数据库、加载 MCP、注册中间件和异常处理。
- `backend/app/api/v1/router.py`：API 总路由。
- `backend/app/core/config.py`：环境变量和配置中心。
- `backend/app/db/session.py`：异步数据库引擎和会话。
- `backend/app/db/init_db.py`：建表和种子数据。

## 4. 前端结构

```text
frontend/src/
├── main.tsx                  # 前端入口
├── App.tsx                   # 应用根组件
├── router/                   # React Router 路由
├── api/                      # Axios 客户端和 API 模块
├── store/                    # Zustand 全局状态
├── pages/                    # 页面级入口
├── features/                 # 复杂业务功能模块
├── components/               # 布局、通用组件、UI 组件
├── lib/                      # 工具函数
└── assets/                   # 静态资源
```

关键入口：

- `frontend/src/router/index.tsx`：登录、管理员、普通用户、公共页面路由。
- `frontend/src/api/client.ts`：Axios 封装、token 注入、统一响应解包。
- `frontend/src/store/useAuthStore.ts`：登录态、用户信息、token 持久化。
- `frontend/vite.config.ts`：别名 `@` 和 `/api` 开发代理。

## 5. 基础设施

`docker-compose.yml` 当前编排：

- PostgreSQL：业务库与 LangFuse 库。
- Redis：缓存与 LangFuse 队列。
- MinIO：文件和 LangFuse 事件对象存储。
- Milvus + etcd：向量数据库。
- ClickHouse：LangFuse 分析存储。
- LangFuse + worker：AI 调用链路追踪。
- OnlyOffice：文档在线预览和编辑。

## 6. 当前核心模块

- 系统管理：登录、用户、角色、部门、模型配置。
- 智能体管理：Agent 分组、应用、角色和部门授权、用户工作台。
- 合同审查：合同上传、MinIO 存储、后台 Agent 分析、审计日志、OnlyOffice 预览。
- MCP：启动时自动扫描 `backend/app/mcp/servers/` 并挂载 SSE 端点。
