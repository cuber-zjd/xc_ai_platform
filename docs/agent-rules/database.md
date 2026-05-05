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

- 当前项目启动时会通过 `SQLModel.metadata.create_all` 创建表。
- 生产环境禁止依赖手动改表。
- 如果后续引入 Alembic，表结构变化必须生成迁移脚本。
- 种子数据放在 `backend/app/db/init_db.py` 或明确的脚本中，并保持幂等。

## 7. 安全

- 禁止把真实 API Key、模型密钥写入种子数据。
- 如果必须初始化演示数据，应使用明显的占位值，并在 `.env.example` 中说明。
- 查询用户、权限、外部 API Key 等敏感数据时，日志不能输出完整密钥或密码。
