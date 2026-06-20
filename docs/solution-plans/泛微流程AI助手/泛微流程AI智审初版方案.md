# 泛微流程 AI 智审初版方案

## 目标

在泛微 E9 流程审批节点引入 AI 预审能力，让审批人打开待办前或审批时看到风险提示、缺失材料、建议结论和建议审批意见，减少无谓退回和沟通成本。

## 初版边界

- AI 只做预审建议，不直接保存、提交、审批、退回或删除流程。
- 审批页 ecode 只负责展示智审入口和传递当前表单上下文。
- Java Action 只负责在节点流转时调用平台接口生成智审记录，默认不阻断流程。
- 平台保存每次预审的表单快照、规则快照和模型结果，便于复盘与后续替审评估。

## 平台入口

- 智审展示页：`/weaver/assistant/review`
- 智审规则配置页：`/weaver/assistant/review-config`
- 智审接口：`POST /api/v1/weaver/ai-assistant/review/precheck`
- 最近智审记录：`GET /api/v1/weaver/ai-assistant/review/latest`
- 智审规则维护：`/api/v1/weaver/ai-assistant/review-rules`

## 数据表

- `weaver_ai_review_rule`：按 `env + workflow_id + node_id + reviewer_user_id` 维护智审规则。
- `weaver_ai_review_record`：保存每次智审结果，包括风险等级、建议结论、检查项、缺失材料、关注点和建议审批意见。

## 泛微侧代码

- 审批页 ecode：`docs/solution-plans/泛微流程AI助手/ecode/泛微流程AI智审-审批页ecode脚本.js`
- 规则配置页 ecode：`docs/solution-plans/泛微流程AI助手/ecode/泛微流程AI智审-规则配置页ecode脚本.js`
- Java Action：`docs/solution-plans/泛微流程AI助手/java/WeaverAiReviewAction.java`

## 推荐落地方式

1. 先在测试流程审批页加入“AI智审”悬浮入口。
2. 在流程路径设置页加入“AI智审规则”页签，配置流程通用规则。
3. 将 `WeaverAiReviewAction` 挂到测试流程节点后附加操作，提交后自动生成预审记录。
4. 审批人打开待办时查看 AI 智审建议，人工决定审批动作。
5. 积累一段时间后，统计低风险且审批人采纳率高的场景，再评估 `autoReviewMode=auto` 的替审能力。

## 后续替审要求

后续如果启用 AI 替审，必须满足：

- 审批人显式授权。
- 只允许白名单流程、白名单节点和低风险条件。
- 每次替审保存规则版本、模型结果、表单快照和操作结果。
- 高风险、材料缺失、置信度不足或模型异常时必须转人工。
- 不允许 AI 自行越过泛微权限、跳过必审节点或执行任意脚本。
