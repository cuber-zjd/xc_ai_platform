# FineReport AI 报表第三步对接说明

本文档记录 FineReport AI 报表第三步的当前对接口径：从第二步确认后的 `ReportDSL` 确定性生成 `.cpt`，上传到 MinIO 的 `reportlets/AI生成报表/` 专用预览目录，并返回 FineReport 预览地址。当前阶段只做预览，不做正式报表覆盖、审批复制或发布。

第三步接口：

```text
POST /api/v1/fr/ai-reports/steps/cpt/generate
Content-Type: multipart/form-data

task_id=<第一步和第二步共用的任务 ID>
```

## 1. 当前已确认环境

- FineReport 访问根地址：`http://192.168.14.41:1080`。
- FineReport 预览入口：`/webroot/decision/view/report?viewlet=...`。
- MinIO S3 API endpoint：`192.168.14.41:9000`，由容器端口 `-p 192.168.14.41:9000:9000` 确认。
- MinIO 控制台/浏览器入口：`http://192.168.14.41:1080/minio`，由 `MINIO_BROWSER_REDIRECT_URL` 确认。
- MinIO bucket：`fanruan`。
- FineReport 数据连接名：第一版默认 `XcTest`。
- CPT 样例版本：`xmlVersion="20211223"`、`releaseVersion="11.5.0"`。

## 2. 后端环境变量

```env
FR_AI_MINIO_ENDPOINT=192.168.14.41:9000
FR_AI_MINIO_ACCESS_KEY=minioadmin
FR_AI_MINIO_SECRET_KEY=<从服务器 minio.setting、部署密钥或新建 Access Key 获取>
FR_AI_MINIO_BUCKET_NAME=fanruan
FR_AI_MINIO_SECURE=false

FINEREPORT_PREVIEW_BASE_URL=http://192.168.14.41:1080
FR_AI_FINEREPORT_DB_NAME=XcTest
```

`FINEREPORT_PREVIEW_BASE_URL` 可以填写 FineReport 根地址，也可以填写完整预览入口 `http://192.168.14.41:1080/webroot/decision/view/report`。后端会拼接 `viewlet` 参数。

真实 `FR_AI_MINIO_SECRET_KEY` 不写入仓库；如果生产环境允许，优先在 MinIO 控制台中新建专用 Access Key，并只授予 `fanruan` bucket 里 `webroot/APP/reportlets/AI生成报表/` 路径的读写权限。

## 3. MinIO 路径规则

第三步生成物只能写入 reportlets 下的 AI 专用预览目录：

```text
webroot/APP/reportlets/AI生成报表/{task_id}/report.cpt
webroot/APP/reportlets/AI生成报表/{task_id}/report.dsl.json
webroot/APP/reportlets/AI生成报表/{task_id}/query.sql
webroot/APP/reportlets/AI生成报表/{task_id}/create_table.sql
webroot/APP/reportlets/AI生成报表/{task_id}/generation.log
```

不得直接写入正式目录，例如：

```text
webroot/APP/reportlets/数据分析/天下五谷/...
```

正式目录复制、审批、覆盖和回滚后续单独设计。

## 4. FineReport 预览规则

正式报表示例的预览地址形态为：

```text
http://192.168.14.41:1080/webroot/decision/view/report?viewlet=数据分析/御馨/展示/10.3、大客户订单原料锁定.cpt
```

AI 预览使用任务路径：

```text
http://192.168.14.41:1080/webroot/decision/view/report?viewlet=AI生成报表/{task_id}/report.cpt
```

FineReport 预览端按 `reportlets` 根目录解析，因此 MinIO 对象必须位于 `webroot/APP/reportlets/AI生成报表/`，但 `viewlet` 参数只传 `AI生成报表/...`。

## 5. 第三步执行边界

1. 读取同一任务的 `report_dsl`、`query_sql`、`create_table_sql` 和生成日志。
2. `CptGenerator` 以确定性程序生成 FineReport `.cpt` XML，不能由 AI 直接输出 CPT/XML。
3. CPT 内数据库连接名来自 `FR_AI_FINEREPORT_DB_NAME`，当前默认 `XcTest`。
4. `MinIOStagingService` 上传 CPT、DSL、SQL、建表 SQL 和日志到 `reportlets/AI生成报表/` 专用预览目录。
5. `PreviewValidator` 调用 FineReport 预览 URL，记录 `previewUrl`、HTTP 状态、`warnings` 和 `errors`。
6. 当前 `publish` 只允许标记任务状态，不得复制到正式 `reportlets`。

## 6. 验证方式

- 生成任务后，在 MinIO 控制台确认 `fanruan/webroot/APP/reportlets/AI生成报表/{task_id}/report.cpt` 存在。
- 打开返回的 `previewUrl`，确认 FineReport 能读取 CPT。
- 检查任务详情中的 `cptObjectPath`、`dslObjectPath`、`sqlObjectPath`、`previewUrl`、`warnings` 和 `errors`。
- 如果预览失败，优先确认 `viewlet` 相对路径是否与 FineReport reportlets 根目录一致，其次确认 MinIO bucket、Access Key 权限和 `FR_AI_FINEREPORT_DB_NAME` 是否正确。
