# 泛微流程 AI 助手接入方案

## 目标

将泛微 ecode 中的代码压缩到最小：只负责显示悬浮图标、打开平台 iframe、把当前流程上下文转发给平台、接收平台返回的写入动作并调用 `WfForm` 执行。AI 助手页面、样式、聊天交互和后端 Agent 均由当前 AI 平台承载。

## 平台侧入口

- 前端嵌入页：`/weaver/assistant/embed?ai_sign=<外部签名>`
- 后端字段配置：`GET /api/v1/weaver/ai-assistant/field-config?workflow_id=<流程ID>&env=<环境key>`
- 后端流式聊天接口：`POST /api/v1/weaver/ai-assistant/chat/stream`
- 后端非流式兼容接口：`POST /api/v1/weaver/ai-assistant/chat`
- 鉴权方式：请求头 `ai-sign`，值来自后端 `EXTERNAL_API_KEYS` 配置。

## ecode 完整脚本

ecode 侧代码统一放在 `docs/solution-plans/泛微流程AI助手/ecode/`，后续以该目录中的完整脚本为准：

- [泛微流程AI助手-ecode完整脚本.js](./ecode/泛微流程AI助手-ecode完整脚本.js)
- [ecode 代码说明](./ecode/README.md)

复制后只需要修改脚本顶部“现场配置区”的平台地址、`AI_SIGN` 和 `WEAVER_ENV`。当前版本不再要求 ecode 手工维护字段映射，脚本会按 `workflowid + env` 从平台查询字段配置，再用 `WfForm.getFieldValue()` 读取当前页面实时值。

## 安全边界

- ecode 不保存模型 Key，只保存外部接口签名 `ai-sign`。
- AI 后端只返回 `set_field`、`add_detail_row`、`show_message` 等结构化动作。
- ecode 只按白名单动作调用 `WfForm`，不执行 AI 生成的任意 JavaScript。
- 第一版不自动保存、不自动提交、不自动审批。
