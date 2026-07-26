# 泛微流程 AI 助手 ecode 代码

## 复制入口

以后 ecode 侧代码统一维护在：

- [泛微流程AI助手-ecode完整脚本.js](./泛微流程AI助手-ecode完整脚本.js)：默认仅用于流程发起页面。
- [泛微流程AI助手-流程规则配置页ecode脚本.js](./泛微流程AI助手-流程规则配置页ecode脚本.js)：用于流程路径设置的基础信息页，例如 `#/workflowengine/path/pathSet/pathDetail/baseSet/baseInfo?workflowId=346`。
- [泛微流程AI智审-审批页ecode脚本.js](./泛微流程AI智审-审批页ecode脚本.js)：用于流程审批/处理页面，添加“AI智审”悬浮入口。
- [泛微流程AI智审-规则配置页ecode脚本.js](./泛微流程AI智审-规则配置页ecode脚本.js)：用于流程路径设置页，添加“AI智审规则”页签。
- [WeaverAiReviewAction.java](../java/WeaverAiReviewAction.java)：用于泛微后端 Action 节点附加操作，提交或流转后自动调用平台生成智审记录。

每次需要更新 ecode，按页面类型复制对应文件整段内容到 ecode 前置加载脚本。

## 必改配置

复制后只改脚本顶部“现场配置区”：

```javascript
var AI_PLATFORM_BASE_URL = "http://localhost:5173";
var AI_SIGN = "替换为后端 EXTERNAL_API_KEYS 中配置的值";
var WEAVER_ENV = "test";
var AI_ICON_URL = AI_PLATFORM_BASE_URL + "/ai/weaver-assistant/mascot-selected.png";
```

- 本地开发：`AI_PLATFORM_BASE_URL` 通常填 `http://localhost:5173`。
- 服务器部署：填平台前端部署地址，例如 `http://192.168.x.x:5173` 或正式域名。
- `AI_SIGN` 必须与后端 `EXTERNAL_API_KEYS` 中的某一个值一致。
- `WEAVER_ENV` 对应后端 `WEAVER_DB_CONFIGS` 的环境 key，例如 `test`、`prod`。
- 当前前端应用基础路径为 `/ai`，ecode 已自动拼接该路径，`AI_PLATFORM_BASE_URL` 只填写协议、主机和端口。

## 当前脚本包含能力

- 流程发起页面悬浮 AI 填单图标；默认通过 `iscreate=1`、`requestid/resourceid` 和 `WfForm.getBaseInfo()` 区分发起页与处理页。
- 填单脚本顶部 `ENABLE_ON_PROCESS_PAGE` 默认为 `false`，审批/处理页不会读取字段配置、不会挂载填单助手。
- 点击后通过 Web Animations API 将悬浮形象连续展开为平台 `/weaver/assistant/embed` iframe 面板；关闭时反向收回，旧浏览器自动降级为直接显隐。
- 按 `workflowid + env` 从平台读取泛微字段配置。
- 每次聊天前响应平台 `WEAVER_AI_REQUEST_CONTEXT`，回传当前表单实时值、可写状态和只读原因。
- 接收平台 `WEAVER_AI_APPLY_ACTIONS` 后，只执行 `set_field` 和 `add_detail_row`。
- 不执行 AI 返回的任意 JavaScript，不自动保存、提交或审批。

## 流程规则配置页脚本包含能力

- 仅在流程路径设置的基础信息页生效。
- 自动从当前 URL 读取 `workflowId`。
- 在“基础设置 / 表单管理 / 流转设置 / 高级设置”这一排一级页签中，自动追加“AI填报规则”页签。
- 点击“AI填报规则”页签后，在当前设置区域打开平台 `/weaver/assistant/workflow-config` iframe。
- 配置内容按 `env + workflowId` 保存到平台。
- 后续该流程的填单聊天会自动注入这些特殊填写要求、提示词和工具/技能说明。

## AI 智审脚本包含能力

- 审批页脚本仅在已有 `requestid/resourceid` 的流程处理页面添加“AI智审”悬浮入口，发起页不会挂载。
- 两份 ecode 即使被同一泛微全局加载器同时加载，也会按页面类型互斥并主动清理错误入口，避免右下角两个图标重叠。
- 审批页会只读采集当前表单字段和值作为智审依据，但不会执行填单动作，也不会自动审批、退回或提交。
- 点击后使用同一套助手形象和展开转场打开平台 `/weaver/assistant/review` iframe，读取最近一次预审结果，或手动发起“立即智审”。
- 智审面板通过 `postMessage` 读取当前页面上下文，平台接口统一使用 `/ai-api/v1/weaver/ai-assistant/*`。
- 规则配置脚本会在流程路径设置页追加“AI智审规则”页签，打开平台 `/weaver/assistant/review-config`。
- 智审规则按 `env + workflowId + nodeId + reviewerUserId` 维护，支持流程通用、节点级和审批人个人口径。
- 初版 AI 智审只生成风险等级、检查项、建议结论和建议审批意见，不自动保存、提交、审批或退回。

## 助手形象资源

- 当前正式图标：`frontend/public/weaver-assistant/mascot-selected.png`，使用已确认的透明机器人素材。
- 悬浮入口只展示透明机器人图片，不增加圆框或实体背景；ecode 仅添加贴合轮廓的轻微投影、持续浮动、悬停反馈和透明 SVG 风格的眨眼覆盖层。
- Lottie：`frontend/public/weaver-assistant/avatar-lottie.json`，包含呼吸、漂浮和眨眼关键帧。
- React 动画组件：`frontend/src/features/weaver-ai-assistant/components/WeaverAssistantAvatar.tsx`，支持 `idle/thinking/review/success` 状态。

## Java Action 说明

Java Action 文件放在：

```text
docs/solution-plans/泛微流程AI助手/java/WeaverAiReviewAction.java
```

建议先挂在测试流程的“节点后附加操作”，参数至少配置：

```text
platformBaseUrl = http://你的平台后端地址:8000
aiSign = 后端 EXTERNAL_API_KEYS 中配置的值
env = test
```

默认情况下，Action 调用失败不会阻断泛微流程；只有显式配置 `blockOnRiskLevel=blocked` 或 `blockOnRiskLevel=high,blocked` 时，才会按风险等级阻断。
