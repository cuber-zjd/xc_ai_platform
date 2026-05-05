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

如需开发新的 MCP 服务，请参考 `docs/agent-rules/backend.md` 中的 MCP 规则章节。

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

## 🚀 生产环境部署指南 (Ubuntu 源码方式)

本指南适用于在 Ubuntu 22.04+ 服务器上通过源码直接部署项目。

### 1. 基础环境准备

在服务器上安装必要的系统组件：

```bash
# 更新系统
sudo apt update && sudo apt upgrade -y

# 安装基础工具
sudo apt install -y git curl wget build-essential libssl-dev zlib1g-dev \
    libbz2-dev libreadline-dev libsqlite3-dev curl \
    libncursesw5-dev xz-utils tk-dev libxml2-dev libxmlsec1-dev libffi-dev liblzma-dev

# 1.1 安装 Docker & Docker Compose
# 参考官方文档：https://docs.docker.com/engine/install/ubuntu/
sudo apt install -y docker.io docker-compose-v2
sudo usermod -aG docker $USER
# 注销并重新登录以使 docker 权限生效

# 1.2 安装 uv (Python 包管理器)
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.cargo/env

# 1.3 安装 Node.js (20+) & pnpm
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
sudo npm install -g pnpm
```

### 2. 获取源码与基础架构启动

```bash
git clone <your-repo-url> ai_platform
cd ai_platform

# 2.1 启动数据库与中间件 (Docker)
# 这将启动 Postgres, Redis, MinIO, Milvus, LangFuse, OnlyOffice
docker compose up -d

# 检查容器状态
docker compose ps
```

### 3. 后端部署 (FastAPI)

```bash
cd backend

# 3.1 安装依赖
uv sync

# 3.2 配置环境变量
cp .env.example .env
# 编辑 .env 文件，修改数据库地址 (由于是源码部署，localhost 即可，端口参见 docker-compose.yml 映射)
# 例如：POSTGRES_SERVER=localhost:9500
nano .env

# 3.3 使用 Systemd 进行进程管理
sudo nano /etc/systemd/system/ai-backend.service
```

在 `ai-backend.service` 中写入：
```ini
[Unit]
Description=AI Platform Backend
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/ai_platform/backend
ExecStart=/home/ubuntu/.cargo/bin/uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable ai-backend
sudo systemctl start ai-backend
```

### 4. 前端部署 (React/Vite)

生产环境建议将前端编译为静态文件，并由 Nginx 托管。

```bash
cd ../frontend

# 4.1 安装依赖
pnpm install

# 4.2 编译静态资源
# 确保文件中的 .env.production 或配置指向了正确的后端 API 地址
pnpm build
```

### 5. Nginx 配置 (反向代理)

```bash
sudo apt install -y nginx
sudo nano /etc/nginx/sites-available/ai-platform
```

写入配置：
```nginx
server {
    listen 80;
    server_name your_domain_or_ip;

    # 前端静态文件
    location / {
        root /home/ubuntu/ai_platform/frontend/dist;
        index index.html;
        try_files $uri $uri/ /index.html;
    }

    # 后端 API 转发
    location /api {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/ai-platform /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

### 6. 完成部署

访问 `http://your_server_ip` 即可使用平台。
- **Swagger 文档**: `http://your_server_ip/api/v1/docs` (根据具体路由配置)
- **LangFuse**: `http://your_server_ip:9506`
- **OnlyOffice**: `http://your_server_ip:9509`

---

## ❓ 常见问题

- **数据库初始密码**: 默认位于 `docker-compose.yml` 中的 `password`。
- **端口映射**: 生产环境如果不需要暴露 95xx 系列端口，可以在 `docker-compose.yml` 中删除 ports 映射，仅让容器在内部网络通信，并通过 Nginx 进行外部暴露。
