# AI 草稿快照落地记录

更新时间：2026-06-13

## 本次落地范围

- 新增 `fr_report_snapshot`，保存报表结构快照、父快照、源文件 ETag、快照号、状态、应用补丁和内容 hash。
- 新增 `fr_report_operation_draft`，保存 AI 操作草稿审计记录，包含用户提示词、选中单元格、数据集、操作列表、预览补丁、安全信息和 warnings。
- 新增 `POST /api/v1/fr/ai-reports/ai/apply-draft`，把 AI 操作草稿应用为新的后端快照版本。
- 新增 `POST /api/v1/fr/ai-reports/ai/snapshots/cpt/generate`，基于目标快照确定性生成 CPT 文件版本；请求可指定 `targetObjectPath`，或通过 `targetFolder + reportName` 生成中文报表名路径。
- 新增 `fr_report_project`、`fr_report_structure_version`、`fr_report_file_version`、`fr_report_external_change_log`，把平台结构版本和真实 CPT 文件版本拆开管理。
- CPT 文件允许写入用户指定的 `webroot/APP/reportlets/` 子路径，也允许覆盖已有 CPT；覆盖前必须做 hash/修改时间检测，并把当前文件或新文件归档到目标目录下的 `版本库/<报表名>/v0001/` 等结构化版本目录。
- 当前应用逻辑支持 `set_cell_style` 的确定性结构快照合并，并保留原始 `previewPatch`。

## 当前边界

- 当前阶段可从快照生成静态网格 CPT、快照 JSON、操作 JSON 和生成日志。
- CPT 生成仍由确定性程序完成，AI 只产出受控操作草稿。
- 不再限制只能写 `AI生成报表` 目录；允许写用户指定 reportlets 路径，但必须保留文件版本、manifest、diff，并在检测到 FineReport 设计器外部修改时默认阻止覆盖。
- FineReport 可打开后的精细样式映射仍需继续补齐，当前前端实时预览优先呈现 AI 样式细节。

## 验证结果

- 使用测试账号 `104484` 登录。
- 读取当前用户可见 CPT 文件。
- 调用 `/ai/operation-draft` 生成 `set_cell_style` 操作草稿。
- 调用 `/ai/apply-draft` 成功创建源快照 `source_imported` 和目标快照 `snapshot_created`。
- 返回示例目标版本：`V2 AI 草稿`。
- 调用 `/ai/snapshots/cpt/generate` 可上传到用户指定 CPT 路径，例如 `webroot/APP/reportlets/期货/台账/期货操作台账填报报表.cpt`。
- 同时写入同目录版本库，例如 `webroot/APP/reportlets/期货/台账/版本库/期货操作台账填报报表/v0001/report.cpt`、`report.dsl.json`、`manifest.json` 和 `diff.json`。
- 返回文件版本 ID、结构版本 ID、当前 CPT 路径和 FineReport 预览地址；若目标文件 hash 与平台最新文件版本不一致，返回 `conflict` 并要求用户先同步或归档覆盖。
- 当前环境 FineReport HTTP 校验出现 `Server disconnected without sending a response`，接口保留 `preview_failed` 状态、对象路径和错误信息，便于后续区分上传成功与预览服务异常。
