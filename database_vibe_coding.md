# Database "Vibe Coding" Guide 🗄️

> **Data Gravity**: 数据是平台的重心。
> **Strict & Clean**: 数据库设计必须严谨，命名规范，索引合理。
> **Philosophy**: Schema First, Migration Always.

---

## 1. 命名规范 (Naming Conventions)

### 📐 General Rules
*   **Case**: 全小写 `snake_case`。严禁使用 `CamelCase` 或 `PascalCase`。
*   **Language**: 英语 (English)。严禁拼音。
*   **Plurality**: 单数 (Singular). e.g., `sys_user` NOT `sys_users`.

### 🏷️ Modifiers
*   **Tables**: `module_entity`. (e.g., `sys_user`, `sys_role`, `chat_message`)
*   **Primary Key**: `id`. (BigInteger / Serial)
*   **Foreign Key**: `target_entity_id`. (e.g., `user_id`, `dept_id`)
*   **Boolean**: `is_verb`. (e.g., `is_active`, `is_deleted`, `has_permission`)
*   **Date/Time**: `verb_time` or `noun_date`. (e.g., `create_time`, `start_date`)

---

## 2. 标准字段 (Standard Fields)

所有业务表（Relation Tables 除外）**必须**包含以下基础字段：

```sql
id          BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY
create_time TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
update_time TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
create_by   VARCHAR(64) -- 记录创建人 (User ID or Name)
update_by   VARCHAR(64) -- 记录更新人
comment     TEXT        -- 备注/说明
status      INTEGER     -- 状态 (1=Normal, 0=Disabled/Deleted)
```

> **Note**: 我们推荐 **Soft Delete** (逻辑删除)，通过 `status` 或 `is_deleted` 字段控制。

---

## 3. SQLModel 定义范式

利用 `SQLModel` 的继承特性，保持 Dry (Don't Repeat Yourself)。

### Base Model (Schema)
定义字段，用于 Pydantic 校验和 OpenAPI 生成。
```python
class SysUserBase(SQLModel):
    username: str = Field(index=True, unique=True)
    full_name: str
    status: int = Field(default=1)
```

### Table Model (Database)
定义表结构，添加 keys 和 relationships。
```python
class SysUser(SysUserBase, table=True):
    __tablename__ = "sys_user"
    
    id: int | None = Field(default=None, primary_key=True)
    create_time: datetime = Field(default_factory=datetime.now)
    # ... standard fields
```

---

## 4. 迁移管理 (Migrations)

*   **Tool**: `Alembic` (via `alembic` CLI or wrapper).
*   **Commitment**: 严禁直接在生产环境手动 `ALTER TABLE`。所有变更必须通过 Migration Script。
*   **Workflow**:
    1.  Modify `models/*.py`.
    2.  `alembic revision --autogenerate -m "add_table_xyz"`
    3.  Review the generated script.
    4.  `alembic upgrade head`

---

## 5. Performance Tips

*   **Indexing**: 对经常用于 Query Filter (`WHERE`) 和 Sorting (`ORDER BY`) 的字段加索引。
*   **JSONB**: 善用 Postgres 的 `JSONB` 存储非结构化数据 (e.g., Agent 配置, 扩展属性)，但要克制，不要把 DB 当 Mongo 用。
*   **Foreign Keys**: 显式定义外键约束，保证数据引用完整性。

