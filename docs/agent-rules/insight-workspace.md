# 妙搭情报工作空间接入

2026-11-12：为香驰·先机增加情报检索、需求式采集配置、报告目录及已有云文档推送。生成报告仍由原平台执行，妙搭不修改原简报计划。

## 分工与权限

- 妙搭承载页面与飞书登录。NestJS 从网关 userContext 读取租户、应用、用户，使用独立 HMAC 密钥签名；浏览器不能传入旧平台账号。
- 后端入口 `/ai-api/v1/insight-workspace`。签名覆盖时间、身份、方法、路径和完整请求体，允许两分钟时钟偏差。
- `INSIGHT_WORKSPACE_BINDINGS_JSON` 为 `{ "tenant:app": { "miaodaUserId": 旧平台用户数字ID } }`。未绑定、停用或删除账号拒绝访问，不默认使用管理员。
- `INSIGHT_WORKSPACE_BOT_READERS_JSON` 是获准汇总市场洞察助手报告与复用既有接收对象的完整身份字符串数组。它不授予修改旧简报计划、修改文档权限或增加任意接收对象的能力。
- 未来其他公司须绑定对应身份、独立数据源与机器人授权；当前实现不声称支持任意企业自助接入。

## 持久化与执行

- `insight_workspace_item` 按 scope/owner 隔离，保存采集包装记录、云文档目录、推送计划、发送审计。由既有 SQLModel 初始化流程创建新增表，不改变既有表。
- 需求整理使用原模型工厂，输出受 Pydantic 校验的可编辑检索草案；失败不会保存或启动。
- 采集配置映射到原 monitor_config，默认 disabled；修改后同样暂停，用户再确认启用。工作空间的业务过滤根据用户需求，不写死健源/御馨行业条件。
- 报告目录来自原报告表、简报运行记录和当前账号添加的云文档链接。原正文不复制、不覆盖。机器人无 drive 目录读取权限时，不宣称包含机器人所有云盘文件。
- 输入文档 URL 限 HTTPS 官方主机及 docx/docs/wiki 路径，移除查询参数和片段，防止保存一次性登录令牌。
- 推送保存为草稿；预览不发送。确认后写入队列，原飞书简报定时器处理队列及到期计划。每周发送同一篇文档，不生成新报告。
- 发送使用原机器人凭据，不自动修改文档权限。UUID 标记每次收件人消息，重复请求不重复入队。网络异常标 uncertain 并停用，不自动重试；进程中断十分钟后标记待核对。
- 调度使用独立会话与45秒边界，异常不阻断原简报定时器。审计只保存结果和消息ID，不记录凭据。

## 配置与部署

代码须经 `scripts/deploy_server.ps1 -BackendOnly -ExpectedCommit ...` 发布，不得复制代码覆盖服务器。

部署后 `backend/scripts/insight_workspace_configure.py` 从 stdin 读取专用密钥、scope、owner、userId、botReports。无 `--apply` 为预览，写入拒绝隐式轮换密钥和覆盖不同账号绑定。凭据只放私有文件或环境变量。

妙搭服务端配置 `INSIGHT_WORKSPACE_URL`（固定 HTTPS 根路径）和 `INSIGHT_WORKSPACE_KEY`；前端不能读取。配置完成后通过标准发布脚本重启后端。

## 验证

`uv run --with pytest --with pytest-asyncio --with aiosqlite python -m pytest tests/test_insight_workspace.py -q`：隔离 SQLite 与机器人替身验证链接、签名、跨账号隔离、草稿、队列、时间换算、重复请求及异常。真实联调只读报告和保存暂停配置；不向业务接收人试发。
