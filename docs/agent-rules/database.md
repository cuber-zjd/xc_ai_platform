# 数据库规则

本文件适用于修改 SQLModel 模型、数据库字段、初始化数据、查询性能和迁移策略。

## 1. 技术栈

- 业务数据库：PostgreSQL。
- ORM：SQLModel。
- 异步驱动：asyncpg。
- 会话入口：`backend/app/db/session.py`。
- 初始化入口：`backend/app/db/init_db.py`。

## 2. 命名约定

- 表名使用 `snake_case` 单数形式，例如 `sys_user`。
- 主键统一使用 `id`。
- 外键使用 `<target>_id`，例如 `user_id`、`role_id`。
- 布尔字段使用 `is_` 前缀，例如 `is_active`、`is_deleted`。
- 时间字段使用 `create_time`、`update_time`。
- 软删除字段优先使用 `is_deleted`。
- 状态字段优先使用 `status`。

## 3. 标准字段

业务表优先包含：

- `id`
- `create_time`
- `update_time`
- `create_by`
- `update_by`
- `status`

如果现有表未完全遵守，新增字段和新表应向该规范靠拢，同时避免无关大改。

## 4. SQLModel 约定

- 使用继承保持 Base、Table、Read、Create、Update 结构清晰。
- 字段类型必须明确。
- 关系字段要注意异步加载方式，必要时使用 `selectinload`。
- 新模型必须确保在 `init_db.py` 或模型包入口中被导入，避免未注册到 `SQLModel.metadata`。

## 5. 查询与性能

- WHERE、JOIN、ORDER BY 高频字段应考虑索引。
- 列表接口必须控制分页，避免一次性返回大量数据。
- JSONB 可用于半结构化配置，但不要把 PostgreSQL 当文档数据库使用。
- 需要数据完整性的关系应显式定义外键。

## 6. 初始化与迁移

- FineReport AI 历史任务第一版新增 `fr_ai_report_conversation`、`fr_ai_report_feedback`，并为 `fr_ai_report_task` 补充 `conversation_id`、`parent_task_id`、`revision_no`；当前通过 `init_db.py` 和服务启动时的 `ADD COLUMN IF NOT EXISTS` 兼容旧库。
- FineReport 报表文件用户可见范围使用 `fr_report_visibility_preference` 保存当前用户选择显示的文件夹或报表路径列表；空列表表示显示全部，不保存全量报表清单。
- 当前项目启动时会通过 `SQLModel.metadata.create_all` 创建表。
- 泛微流程 AI 智审使用 `weaver_ai_review_rule` 保存规则，使用 `weaver_ai_review_record` 保存每次预审的表单快照、规则快照和模型结论；当前随 `SQLModel.metadata.create_all` 创建。
- Insight 定时报告计划使用 `insight_report_subscription`，保存报告模板、素材范围、周期、下次执行时间、上次生成报告、上次企业微信通知和接收人 JSON；该表已通过模型包入口注册，随 `SQLModel.metadata.create_all` 创建。
- Insight 底层配置以 `insight_monitor_config` 为调度主表，渠道库使用 `insight_channel` 表；旧 `insight_data_source` 不再作为用户配置或调度主概念，仅为历史任务、抓取结果和正式情报外键兼容保留，启动迁移会把旧执行源状态汇总回监测配置并软删除旧执行源。
- Insight 全渠道适配器运行审计使用 `insight_channel_adapter_run`，记录渠道、监测配置、关键词、运行类型、状态、耗时、命中/去重/候选/正式/向量化数量、错误类型、错误信息、请求载荷、响应摘要、HTML/截图/原始输出路径和重试次数；该表已通过模型包入口注册，随 `SQLModel.metadata.create_all` 创建。
- Insight 采集任务和抓取结果需要直接保存 `monitor_config_id`，AI 自动评审、资产化、报告和 RAG 优先按监测配置获取业务对象、模块、关键词和审批提示词；旧 `data_source_id` 只作为历史兼容字段。
- FineReport 报表数据集预览使用 `fr_report_database_driver` 保存平台级数据库驱动字典，驱动不按用户隔离；当前种子数据包含 `sqlserver` 和 `mysql8`。
- FineReport 报表数据库连接使用 `fr_report_database_connection` 保存用户级连接信息，连接引用平台级 `driver_key`，用于数据集预览和后续 AI SQL/报表调整。
- FineReport 报表版本控制使用 `fr_report_project`、`fr_report_structure_version`、`fr_report_file_version` 和 `fr_report_external_change_log`：平台结构版本和真实 CPT 文件版本分开保存，文件版本需记录当前对象路径、版本库归档路径、hash、ETag、lastModified、manifest 和回档状态。
- 生产环境禁止依赖手动改表。
- 如果后续引入 Alembic，表结构变化必须生成迁移脚本。
- 种子数据放在 `backend/app/db/init_db.py` 或明确的脚本中，并保持幂等。

## 7. 安全

- 禁止把真实 API Key、模型密钥写入种子数据。
- 如果必须初始化演示数据，应使用明显的占位值，并在 `.env.example` 中说明。
- 查询用户、权限、外部 API Key 等敏感数据时，日志不能输出完整密钥或密码。
