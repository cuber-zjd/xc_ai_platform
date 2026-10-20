# 经营助手只读试点

从个人工作台已验收的 `capabilities/tools/business_insights/` 提取经营计算、客户权限、过程快照及七个 MCP 工具。服务端只接收有截止日的聚合快照，不复制个人工作台、SAP 依赖、飞书凭据或业务库连接。与主平台独立锁定 MCP 2.3.0，避免升级主后端依赖。

服务器模块不注册演示登录和反馈写入，不调用模型、不发送消息、不创建飞书自动化。操作身份由服务端 SHA256 摘要映射到固定试点范围；共享试点凭据不是飞书用户身份，不用于生产全员接入。后续业务员身份须先确认映射与授权。

HTTPS 前缀 `/business-insights`；MCP 为 `/business-insights/mcp/`，业务 HTTP 位于 `/business-insights/api/`。Bearer 是这个独立试点的专用鉴权，与主平台 `X-MCP-API-Key` 和 `ai-sign` 分别隔离。所有业务接口要求凭据；健康检查仅展示运行与截止日。MCP 响应保留原工具 Schema，不使用主平台 Result 包装。

发布使用根目录 `scripts/deploy_server.ps1 -ExpectedCommit <commit> -BusinessInsightsOnly -BusinessInsightsDataDirectory <私有快照目录> -BusinessInsightsCredentialFile <本机私有凭据路径>`。先将代码精确提交到 main 并推送内网仓库。附属 Python 步骤仅通过 SSH stdin 传结构化 JSON 数据，代码只从 Git 更新。首次生成凭据并限制本机文件权限；服务器只保存其摘要。禁止把快照、私钥、服务环境文件或凭据加入 Git。

运行数据在组件 `storage/`（Git 忽略，目录 0700、文件 0600）；每次发布保存原快照、身份和 Nginx 配置备份。服务 `ai-platform-business-insights.service` 监听服务器内网 8766，由现有 Dify Nginx 专用 location 转发。修改运行配置及重启模板，先 `nginx -t`，失败恢复原配置。发布不重启主平台前后端或其他容器。没有云端数据库轮询；数据更新需再次显式发布成功快照，回答始终显示各自截止日。飞书过程缓存超过 30 分钟标记过期。

验收须包含 HTTPS 证书正常、未认证拒绝、演示登录关闭、写接口不存在、官方 MCP 客户端实际发现并调用七工具，以及原平台页面仍可访问。此验收不等同真实飞书智能体调用成功。
