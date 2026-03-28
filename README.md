# AI Platform 🚀

企业级 AI Agent 编排与管理平台。基于 FastAPI + LangGraph + SQLModel 构建，具备强大的扩展性与可观测性。

## 🏗️ 整体架构

本项目采用前后端分离架构，并引入了 **MCP (Model Context Protocol)** 作为工具扩展的核心体系。

### 后端 (Backend)
- **FastAPI**: 核心 Web 框架。
- **LangGraph**: Agent 流程编排与状态管理。
- **SQLModel**: 统一的 ORM 数据模型。
- **MCP Ecosystem**: 
  - `app/mcp/manager.py`: 动态服务加载器。
  - `app/mcp/security.py`: 工具调用安全校验层。
  - `app/mcp/servers/`: 业务工具集 (Echo, FileOps, DBExtensions 等)。
- **Observability**: 集成 LangFuse 进行全链路追踪。

### 前端 (Frontend)
- **Vite + React + Tailwind**: 现代化的前端技术栈。
- **Shadcn UI**: 高质量的组件库。
- **Vibe Design**: 极简、流畅的交互体验。

## 🛠️ MCP 服务开发

如需开发新的 MCP 服务，请参考 `backend_vibe_coding.md` 中的 **Section 7**。

### 快速开始
1. 在 `app/mcp/servers/` 下创建 new 目录。
2. 继承 `BaseMCPServer` 并注册工具。
3. 系统启动时将自动挂载路由并将工具暴露给 Agent。

## 🔐 安全与授权
- **JWT**: 用于业务接口的身份验证。
- **X-MCP-API-Key**: 用于 MCP 接口的安全通信。

---

## 💻 多机开发环境配置 (Windows / 网络共享盘)

本项目支持在不同电脑上通过网络共享盘（如 `X` 盘）共同开发。由于 Windows 无法从 UNC 路径加载原生 Python 模块，建议采取以下配置：

### 核心原则
- **代码同步**：直接在共享盘上操作。
- **虚拟环境隔离**：在每台电脑的**本地磁盘**（如 `C:\venvs\`）创建独立的 `.venv`。

### 配置步骤 (新电脑)
1. **安装 uv**：
   ```powershell
   powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
   ```
2. **创建本地虚拟环境**：
   ```powershell
   uv venv C:\venvs\ai_platform_backend --python 3.12
   ```
3. **同步依赖**：
   ```powershell
   $env:UV_PROJECT_ENVIRONMENT = "C:\venvs\ai_platform_backend"; uv sync
   ```
4. **VS Code 启动**：
   在 VS Code 调试面板中选择 `Backend: Uvicorn (New Computer)` 或 `Full Stack (New Computer)` 即可。

### ⚠️ 重要注意事项
- **依赖更新**：如果在 `pyproject.toml` 中新增了包，请在各自电脑上运行一遍同步命令：
  ```powershell
  $env:UV_PROJECT_ENVIRONMENT = "C:\venvs\ai_platform_backend"; uv sync
  ```
- **环境变量**：确保 `backend/.env` 中的 `POSTGRES_SERVER` 等地址在当前网络环境下可达。

---
