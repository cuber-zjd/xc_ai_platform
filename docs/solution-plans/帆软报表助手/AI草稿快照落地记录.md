# AI 草稿快照落地记录

更新时间：2026-06-13

## 本次落地范围

- 新增 `fr_report_snapshot`，保存报表结构快照、父快照、源文件 ETag、快照号、状态、应用补丁和内容 hash。
- 新增 `fr_report_operation_draft`，保存 AI 操作草稿审计记录，包含用户提示词、选中单元格、数据集、操作列表、预览补丁、安全信息和 warnings。
- 新增 `POST /api/v1/fr/ai-reports/ai/apply-draft`，把 AI 操作草稿应用为新的后端快照版本。
- 新增 `POST /api/v1/fr/ai-reports/ai/snapshots/cpt/generate`，基于目标快照确定性生成 CPT 预览产物。
- AI 生成报表预览产物固定写入 `webroot/APP/reportlets/AI生成报表/快照/{snapshot_id}/`，放在 FineReport 可读取的 `reportlets` 根下，同时与正式报表目录隔离。
- 当前应用逻辑支持 `set_cell_style` 的确定性结构快照合并，并保留原始 `previewPatch`。

## 当前边界

- 当前阶段可从快照生成静态网格 CPT、快照 JSON、操作 JSON 和生成日志。
- CPT 生成仍由确定性程序完成，AI 只产出受控操作草稿。
- 不写正式 reportlets。
- FineReport 可打开后的精细样式映射仍需继续补齐，当前前端实时预览优先呈现 AI 样式细节。

## 验证结果

- 使用测试账号 `104484` 登录。
- 读取当前用户可见 CPT 文件。
- 调用 `/ai/operation-draft` 生成 `set_cell_style` 操作草稿。
- 调用 `/ai/apply-draft` 成功创建源快照 `source_imported` 和目标快照 `snapshot_created`。
- 返回示例目标版本：`V2 AI 草稿`。
- 调用 `/ai/snapshots/cpt/generate` 成功上传到 `webroot/APP/reportlets/AI生成报表/快照/{snapshot_id}/report.cpt`。
- 返回预览地址：`/webroot/decision/view/report?viewlet=AI生成报表/快照/{snapshot_id}/report.cpt`。
- 当前环境 FineReport HTTP 校验出现 `Server disconnected without sending a response`，接口保留 `preview_failed` 状态、对象路径和错误信息，便于后续区分上传成功与预览服务异常。
