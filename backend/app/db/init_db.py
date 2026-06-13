from importlib import import_module

from sqlmodel import SQLModel
from sqlalchemy import text
from app.db.session import engine
from app.core.logger import logger

# 导入所有模型确保注册到 SQLModel.metadata

async def init_db():
    """
    创建数据库表 + 初始化种子数据。
    应用启动时调用。
    """
    _register_models()
    logger.info("正在创建数据库表...")
    async with engine.begin() as conn:
        # await conn.run_sync(SQLModel.metadata.drop_all) # 危险：仅开发环境使用
        await conn.run_sync(SQLModel.metadata.create_all)
        await _ensure_fr_ai_report_task_columns(conn)
        await _ensure_fr_report_snapshot_columns(conn)
        await _ensure_fr_report_database_connection_columns(conn)
        await _ensure_insight_data_source_schedule_columns(conn)
        await _ensure_insight_company_columns(conn)
        await _ensure_insight_access_control_columns(conn)
        await _ensure_insight_report_template_columns(conn)
        await _ensure_insight_crawler_channel_values(conn)
    
    # 初始化种子数据
    await _seed_contract_rules()
    await _seed_model_configs()
    await _seed_fr_report_database_drivers()

    logger.info("数据库表创建完成。")


def _register_models():
    """导入新分层模型，确保 SQLModel.metadata 能发现表。"""
    import_module("app.models.agent.fr_report")
    import_module("app.models.agent.insight")


async def _ensure_fr_ai_report_task_columns(conn):
    """补齐 create_all 不会自动追加的历史表字段。"""
    await conn.execute(
        text(
            "ALTER TABLE fr_ai_report_task "
            "ADD COLUMN IF NOT EXISTS sql_validation JSONB"
        )
    )


async def _ensure_fr_report_snapshot_columns(conn):
    """补齐 AI 报表快照生成预览产物字段。"""
    await conn.execute(text("ALTER TABLE fr_report_snapshot ADD COLUMN IF NOT EXISTS cpt_object_path VARCHAR"))
    await conn.execute(text("ALTER TABLE fr_report_snapshot ADD COLUMN IF NOT EXISTS meta_object_path VARCHAR"))
    await conn.execute(text("ALTER TABLE fr_report_snapshot ADD COLUMN IF NOT EXISTS preview_url VARCHAR"))
    await conn.execute(
        text(
            "ALTER TABLE fr_report_snapshot "
            "ADD COLUMN IF NOT EXISTS generation_errors JSONB DEFAULT '[]'::jsonb"
        )
    )
    await conn.execute(
        text(
            "ALTER TABLE fr_report_snapshot "
            "ADD COLUMN IF NOT EXISTS generation_warnings JSONB DEFAULT '[]'::jsonb"
        )
    )


async def _ensure_fr_report_database_connection_columns(conn):
    """补齐帆软报表数据库连接的历史字段。"""
    await conn.execute(
        text(
            "ALTER TABLE fr_report_database_connection "
            "ADD COLUMN IF NOT EXISTS driver_key VARCHAR DEFAULT 'sqlserver'"
        )
    )
    await conn.execute(
        text(
            "UPDATE fr_report_database_connection "
            "SET driver_key = 'sqlserver' "
            "WHERE driver_key IS NULL OR driver_key = ''"
        )
    )


async def _ensure_insight_data_source_schedule_columns(conn):
    """补齐 Insight 数据源周期采集字段。"""
    await conn.execute(
        text(
            "ALTER TABLE insight_data_source "
            "ADD COLUMN IF NOT EXISTS next_run_time TIMESTAMP"
        )
    )
    await conn.execute(
        text(
            "ALTER TABLE insight_data_source "
            "ADD COLUMN IF NOT EXISTS schedule_enabled BOOLEAN DEFAULT FALSE"
        )
    )
    await conn.execute(
        text(
            "ALTER TABLE insight_data_source "
            "ADD COLUMN IF NOT EXISTS last_schedule_status VARCHAR(30)"
        )
    )
    await conn.execute(
        text(
            "ALTER TABLE insight_data_source "
            "ADD COLUMN IF NOT EXISTS last_schedule_message VARCHAR(1000)"
        )
    )
    await conn.execute(
        text(
            "ALTER TABLE insight_data_source "
            "ADD COLUMN IF NOT EXISTS consecutive_failure_count INTEGER DEFAULT 0"
        )
    )
    await conn.execute(
        text(
            "ALTER TABLE insight_data_source "
            "ADD COLUMN IF NOT EXISTS last_failure_time TIMESTAMP"
        )
    )
    await conn.execute(
        text(
            "ALTER TABLE insight_data_source "
            "ADD COLUMN IF NOT EXISTS auto_paused_reason VARCHAR(1000)"
        )
    )
    await conn.execute(
        text(
            "UPDATE insight_data_source "
            "SET schedule_enabled = TRUE, next_run_time = COALESCE(next_run_time, NOW()), last_schedule_status = 'waiting' "
            "WHERE is_deleted = 0 "
            "AND fetch_frequency <> 'manual' "
            "AND schedule_enabled = FALSE "
            "AND last_schedule_status IS NULL"
        )
    )


async def _ensure_insight_crawler_channel_values(conn):
    """补齐 Insight 采集通道枚举的新增值。"""
    await conn.execute(text("ALTER TYPE insightcrawlerchannel ADD VALUE IF NOT EXISTS 'BAIDU_NEWS'"))
    await conn.execute(text("ALTER TYPE insightcrawlerchannel ADD VALUE IF NOT EXISTS 'BOCHA_NEWS'"))


async def _ensure_insight_company_columns(conn):
    """补齐 Insight 企业档案历史字段。"""
    await conn.execute(text("ALTER TABLE insight_company ADD COLUMN IF NOT EXISTS sys_company_id INTEGER"))
    await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_insight_company_sys_company_id ON insight_company (sys_company_id)"))


async def _ensure_insight_report_template_columns(conn):
    """补齐 Insight 报告模板上传解析字段。"""
    await conn.execute(
        text(
            "ALTER TABLE insight_report_template "
            "ADD COLUMN IF NOT EXISTS structure_json JSONB DEFAULT '{}'::jsonb"
        )
    )
    await conn.execute(
        text(
            "ALTER TABLE insight_report_template "
            "ADD COLUMN IF NOT EXISTS source_file_name VARCHAR(300)"
        )
    )
    await conn.execute(
        text(
            "ALTER TABLE insight_report_template "
            "ADD COLUMN IF NOT EXISTS source_file_type VARCHAR(30)"
        )
    )
    await conn.execute(
        text(
            "ALTER TABLE insight_report_template "
            "ADD COLUMN IF NOT EXISTS source_file_size INTEGER"
        )
    )
    await conn.execute(text("ALTER TABLE insight_report_template ADD COLUMN IF NOT EXISTS template_kind VARCHAR(30) DEFAULT 'document'"))
    await conn.execute(text("ALTER TABLE insight_report_template ADD COLUMN IF NOT EXISTS style_code VARCHAR(80)"))
    await conn.execute(text("ALTER TABLE insight_report_template ADD COLUMN IF NOT EXISTS export_formats JSONB DEFAULT '[]'::jsonb"))
    await conn.execute(text("ALTER TABLE insight_report_template ADD COLUMN IF NOT EXISTS market_status VARCHAR(30) DEFAULT 'not_listed'"))
    await conn.execute(text("ALTER TABLE insight_report_template ADD COLUMN IF NOT EXISTS market_category VARCHAR(80)"))
    await conn.execute(text("ALTER TABLE insight_report_template ADD COLUMN IF NOT EXISTS market_description VARCHAR(1000)"))
    await conn.execute(text("ALTER TABLE insight_report_template ADD COLUMN IF NOT EXISTS cloned_from_template_id INTEGER"))
    await conn.execute(text("ALTER TABLE insight_report_template ADD COLUMN IF NOT EXISTS published_at TIMESTAMP"))
    await conn.execute(text("ALTER TABLE insight_report_template ADD COLUMN IF NOT EXISTS published_by_user_id INTEGER"))
    await conn.execute(text("ALTER TABLE insight_report_template ADD COLUMN IF NOT EXISTS owner_dept_id INTEGER"))
    await conn.execute(text("ALTER TABLE insight_report_template ADD COLUMN IF NOT EXISTS visibility_scope VARCHAR(30) DEFAULT 'private'"))


async def _ensure_insight_access_control_columns(conn):
    """补齐 Insight 权限底座字段。"""
    await conn.execute(text("ALTER TABLE insight_data_source ADD COLUMN IF NOT EXISTS owner_user_id INTEGER"))
    await conn.execute(text("ALTER TABLE insight_data_source ADD COLUMN IF NOT EXISTS owner_dept_id INTEGER"))
    await conn.execute(text("ALTER TABLE insight_data_source ADD COLUMN IF NOT EXISTS visibility_scope VARCHAR(30) DEFAULT 'private'"))
    await conn.execute(text("ALTER TABLE insight_report ADD COLUMN IF NOT EXISTS owner_dept_id INTEGER"))
    await conn.execute(text("ALTER TABLE insight_report ADD COLUMN IF NOT EXISTS visibility_scope VARCHAR(30) DEFAULT 'private'"))
    await conn.execute(
        text(
            "UPDATE insight_data_source "
            "SET visibility_scope = 'public' "
            "WHERE is_deleted = 0 "
            "AND owner_user_id IS NULL "
            "AND COALESCE(visibility_scope, 'private') <> 'public'"
        )
    )
    await conn.execute(
        text(
            "UPDATE insight_data_source "
            "SET visibility_scope = 'private' "
            "WHERE is_deleted = 0 "
            "AND owner_user_id IS NOT NULL "
            "AND visibility_scope IS NULL"
        )
    )
    await conn.execute(
        text(
            "UPDATE insight_report "
            "SET visibility_scope = 'public' "
            "WHERE is_deleted = 0 "
            "AND owner_user_id IS NULL "
            "AND COALESCE(visibility_scope, 'private') <> 'public'"
        )
    )
    await conn.execute(
        text(
            "UPDATE insight_report "
            "SET visibility_scope = 'private' "
            "WHERE is_deleted = 0 "
            "AND owner_user_id IS NOT NULL "
            "AND visibility_scope IS NULL"
        )
    )


async def _seed_contract_rules():
    """初始化合同审查规则种子数据"""
    from sqlmodel import select
    from app.models.contract.contract_model import ContractRule, RiskLevelEnum
    from app.db.session import async_session
    
    async with async_session() as session:
        statement = select(ContractRule)
        result = await session.exec(statement)
        if not result.first():
            logger.info("正在初始化合同审查规则...")
            rules = [
                ContractRule(
                    rule_name="违约金条款检查", 
                    description="检查合同是否包含违约金相关说明",
                    category="GLOBAL",
                    severity=RiskLevelEnum.WARNING,
                    rule_definition="Check for default penalty"
                ),
                ContractRule(
                    rule_name="付款账期限制", 
                    description="付款账期不得超过60天",
                    category="Purchase",
                    severity=RiskLevelEnum.CRITICAL,
                    rule_definition="Payment terms <= 60 days"
                )
            ]
            session.add_all(rules)
            await session.commit()


async def _seed_fr_report_database_drivers():
    """初始化帆软报表可选数据库驱动。"""
    from sqlmodel import select

    from app.db.session import async_session
    from app.models.agent.fr_report import FrReportDatabaseDriver

    seed_rows = [
        {
            "driver_key": "sqlserver",
            "display_name": "SQL Server",
            "db_type": "sqlserver",
            "python_driver": "pyodbc/pymssql",
            "odbc_driver": "SQL Server",
            "default_port": 1433,
            "description": "SQL Server 只读预览驱动，优先使用 pyodbc，失败后尝试 pymssql。",
        },
        {
            "driver_key": "mysql8",
            "display_name": "MySQL 8",
            "db_type": "mysql",
            "python_driver": "pymysql",
            "odbc_driver": None,
            "default_port": 3306,
            "description": "MySQL 8 只读预览驱动，使用 PyMySQL。",
        },
    ]
    async with async_session() as session:
        for item in seed_rows:
            statement = select(FrReportDatabaseDriver).where(
                FrReportDatabaseDriver.driver_key == item["driver_key"],
                FrReportDatabaseDriver.is_deleted == 0,
            )
            row = (await session.exec(statement)).first()
            if row is None:
                session.add(FrReportDatabaseDriver(**item))
                continue
            row.display_name = item["display_name"]
            row.db_type = item["db_type"]
            row.python_driver = item["python_driver"]
            row.odbc_driver = item["odbc_driver"]
            row.default_port = item["default_port"]
            row.description = item["description"]
            row.status = "active"
        await session.commit()


async def _seed_model_configs():
    """
    初始化 AI 模型配置种子数据

    如果 sys_model 表为空，则插入默认的模型配置。
    这里使用火山引擎（豆包）的端点作为示例，实际使用时需要修改为真实配置。
    """
    from sqlmodel import select
    from app.models.system.sys_model import SysModel
    from app.db.session import async_session

    async with async_session() as session:
        statement = select(SysModel)
        result = await session.exec(statement)
        if not result.first():
            logger.info("正在初始化 AI 模型配置...")
            models = [
                SysModel(
                    model_name="doubao-pro",
                    model_code="ep-20250716092812-ng6hc",
                    provider="volcengine",
                    api_key="8fd7cc00-8433-4843-8231-6d96853861bc",
                    base_url="https://ark.cn-beijing.volces.com/api/v3",
                    model_level=2,
                    model_type="chat",
                    capability="general",
                    max_tokens=4096,
                    default_temperature=0.0,
                    priority=10,
                    is_enabled=True,
                    comment="火山引擎豆包大模型 Pro 版",
                ),
            ]
            session.add_all(models)
            await session.commit()
            logger.info(f"已初始化 {len(models)} 个模型配置")
