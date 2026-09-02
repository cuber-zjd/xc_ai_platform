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
        await _ensure_sys_model_columns(conn)
        await _ensure_insight_monitor_config_schedule_columns(conn)
        await _ensure_insight_data_source_schedule_columns(conn)
        await _ensure_insight_data_source_hierarchy_columns(conn)
        await _ensure_insight_monitor_context_columns(conn)
        await _ensure_insight_intelligence_context_columns(conn)
        await _retire_legacy_insight_data_sources(conn)
        await _ensure_insight_company_columns(conn)
        await _ensure_insight_access_control_columns(conn)
        await _ensure_insight_report_template_columns(conn)
        await _ensure_insight_feishu_brief_columns(conn)
        await _ensure_insight_crawler_channel_values(conn)
        await _ensure_weaver_ai_workflow_rule_indexes(conn)
        await _ensure_weaver_ai_review_rule_columns(conn)
        await _ensure_weaver_ai_review_node_config_indexes(conn)
    
    # 初始化种子数据
    await _seed_contract_rules()
    await _seed_model_configs()
    await _seed_embedding_model_configs()
    await _seed_fr_report_database_drivers()
    await _seed_insight_default_tags()
    await _seed_insight_default_roles()

    logger.info("数据库表创建完成。")


def _register_models():
    """导入新分层模型，确保 SQLModel.metadata 能发现表。"""
    import_module("app.models.agent.weaver_ai_assistant")
    import_module("app.models.agent.fr_report")
    import_module("app.models.agent.insight")


async def _ensure_weaver_ai_workflow_rule_indexes(conn):
    """补齐泛微流程 AI 规则查询索引。"""
    await conn.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_weaver_ai_workflow_rule_lookup "
            "ON weaver_ai_workflow_rule (env, workflow_id, enabled, is_deleted, priority)"
        )
    )


async def _ensure_weaver_ai_review_rule_columns(conn):
    """补齐泛微流程 AI 智审规则范围控制字段。"""
    await conn.execute(
        text(
            "ALTER TABLE weaver_ai_review_rule "
            "ADD COLUMN IF NOT EXISTS general_check_enabled BOOLEAN DEFAULT FALSE NOT NULL"
        )
    )


async def _ensure_weaver_ai_review_node_config_indexes(conn):
    """补齐泛微流程 AI 智审节点开关查询索引。"""
    await conn.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_weaver_ai_review_node_config_lookup "
            "ON weaver_ai_review_node_config (env, workflow_id, node_id, enabled, automatic_review_enabled, is_deleted)"
        )
    )


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


async def _ensure_sys_model_columns(conn):
    """补齐模型配置的多模态能力标记。"""
    column_exists = await conn.scalar(
        text(
            "SELECT EXISTS ("
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema = current_schema() "
            "AND table_name = 'sys_model' "
            "AND column_name = 'is_multimodal'"
            ")"
        )
    )
    if not column_exists:
        await conn.execute(
            text(
                "ALTER TABLE sys_model "
                "ADD COLUMN is_multimodal BOOLEAN DEFAULT FALSE"
            )
        )
    await conn.execute(
        text(
            "UPDATE sys_model "
            "SET is_multimodal = TRUE "
            "WHERE is_multimodal IS DISTINCT FROM TRUE "
            "AND (model_type = 'vision' "
            "OR model_code ILIKE '%vision%' "
            "OR model_code ILIKE '%gpt-4o%' "
            "OR model_code ILIKE '%omni%' "
            "OR model_name ILIKE '%vision%' "
            "OR model_name ILIKE '%多模态%')"
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


async def _ensure_insight_monitor_config_schedule_columns(conn):
    """补齐 Insight 监测配置调度字段，调度器以监测配置为主表。"""
    await conn.execute(text("ALTER TABLE insight_monitor_config ADD COLUMN IF NOT EXISTS last_fetch_time TIMESTAMP"))
    await conn.execute(text("ALTER TABLE insight_monitor_config ADD COLUMN IF NOT EXISTS last_success_time TIMESTAMP"))
    await conn.execute(text("ALTER TABLE insight_monitor_config ADD COLUMN IF NOT EXISTS next_run_time TIMESTAMP"))
    await conn.execute(text("ALTER TABLE insight_monitor_config ADD COLUMN IF NOT EXISTS schedule_enabled BOOLEAN DEFAULT TRUE"))
    await conn.execute(text("ALTER TABLE insight_monitor_config ADD COLUMN IF NOT EXISTS last_schedule_status VARCHAR(30)"))
    await conn.execute(text("ALTER TABLE insight_monitor_config ADD COLUMN IF NOT EXISTS last_schedule_message VARCHAR(1000)"))
    await conn.execute(text("ALTER TABLE insight_monitor_config ADD COLUMN IF NOT EXISTS consecutive_failure_count INTEGER DEFAULT 0"))
    await conn.execute(text("ALTER TABLE insight_monitor_config ADD COLUMN IF NOT EXISTS last_failure_time TIMESTAMP"))
    await conn.execute(text("ALTER TABLE insight_monitor_config ADD COLUMN IF NOT EXISTS auto_paused_reason VARCHAR(1000)"))
    await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_insight_monitor_config_next_run_time ON insight_monitor_config (next_run_time)"))
    await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_insight_monitor_config_schedule_enabled ON insight_monitor_config (schedule_enabled)"))
    await conn.execute(
        text(
            "UPDATE insight_monitor_config "
            "SET schedule_enabled = CASE WHEN status = 'active' AND fetch_frequency <> 'manual' THEN TRUE ELSE FALSE END, "
            "next_run_time = CASE WHEN status = 'active' AND fetch_frequency <> 'manual' THEN COALESCE(next_run_time, NOW()) ELSE NULL END, "
            "last_schedule_status = CASE WHEN status = 'active' AND fetch_frequency <> 'manual' THEN COALESCE(last_schedule_status, 'waiting') ELSE last_schedule_status END, "
            "consecutive_failure_count = COALESCE(consecutive_failure_count, 0) "
            "WHERE is_deleted = 0"
        )
    )


async def _ensure_insight_monitor_context_columns(conn):
    """让采集任务和抓取结果能直接关联监测配置。"""
    await conn.execute(text("ALTER TABLE insight_task ADD COLUMN IF NOT EXISTS monitor_config_id INTEGER"))
    await conn.execute(text("ALTER TABLE insight_crawl_result ADD COLUMN IF NOT EXISTS monitor_config_id INTEGER"))
    await conn.execute(text("ALTER TABLE insight_task ADD COLUMN IF NOT EXISTS source_channel_id INTEGER"))
    await conn.execute(text("ALTER TABLE insight_crawl_result ADD COLUMN IF NOT EXISTS source_channel_id INTEGER"))
    await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_insight_task_monitor_config_id ON insight_task (monitor_config_id)"))
    await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_insight_crawl_result_monitor_config_id ON insight_crawl_result (monitor_config_id)"))
    await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_insight_task_source_channel_id ON insight_task (source_channel_id)"))
    await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_insight_crawl_result_source_channel_id ON insight_crawl_result (source_channel_id)"))
    await conn.execute(
        text(
            "UPDATE insight_task task "
            "SET monitor_config_id = ds.monitor_config_id "
            "FROM insight_data_source ds "
            "WHERE task.monitor_config_id IS NULL "
            "AND task.data_source_id = ds.id "
            "AND ds.monitor_config_id IS NOT NULL"
        )
    )
    await conn.execute(
        text(
            "UPDATE insight_crawl_result result "
            "SET monitor_config_id = ds.monitor_config_id "
            "FROM insight_data_source ds "
            "WHERE result.monitor_config_id IS NULL "
            "AND result.data_source_id = ds.id "
            "AND ds.monitor_config_id IS NOT NULL"
        )
    )
    await conn.execute(
        text(
            "UPDATE insight_task task "
            "SET source_channel_id = ds.channel_id "
            "FROM insight_data_source ds "
            "WHERE task.source_channel_id IS NULL "
            "AND task.data_source_id = ds.id "
            "AND ds.channel_id IS NOT NULL"
        )
    )
    await conn.execute(
        text(
            "UPDATE insight_crawl_result result "
            "SET source_channel_id = ds.channel_id "
            "FROM insight_data_source ds "
            "WHERE result.source_channel_id IS NULL "
            "AND result.data_source_id = ds.id "
            "AND ds.channel_id IS NOT NULL"
        )
    )


async def _ensure_insight_intelligence_context_columns(conn):
    """让正式情报直接继承监测配置权限，避免每条情报重复授权。"""
    await conn.execute(text("ALTER TABLE insight_intelligence ADD COLUMN IF NOT EXISTS monitor_config_id INTEGER"))
    await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_insight_intelligence_monitor_config_id ON insight_intelligence (monitor_config_id)"))
    await conn.execute(
        text(
            "UPDATE insight_intelligence intel "
            "SET monitor_config_id = result.monitor_config_id "
            "FROM insight_crawl_result result "
            "WHERE intel.monitor_config_id IS NULL "
            "AND (intel.raw_payload ->> 'crawl_result_id') ~ '^[0-9]+$' "
            "AND CAST(intel.raw_payload ->> 'crawl_result_id' AS INTEGER) = result.id "
            "AND result.monitor_config_id IS NOT NULL"
        )
    )


async def _ensure_insight_data_source_hierarchy_columns(conn):
    """补齐 Insight 执行源分层归属字段，兼容旧数据源。"""
    await conn.execute(text("ALTER TABLE insight_data_source ADD COLUMN IF NOT EXISTS channel_id INTEGER"))
    await conn.execute(text("ALTER TABLE insight_data_source ADD COLUMN IF NOT EXISTS monitor_config_id INTEGER"))
    await conn.execute(text("ALTER TABLE insight_data_source ADD COLUMN IF NOT EXISTS monitor_object_type VARCHAR(30)"))
    await conn.execute(text("ALTER TABLE insight_data_source ADD COLUMN IF NOT EXISTS monitor_object_id INTEGER"))
    await conn.execute(text("ALTER TABLE insight_data_source ADD COLUMN IF NOT EXISTS execution_role VARCHAR(50)"))
    await conn.execute(text("ALTER TABLE insight_data_source ADD COLUMN IF NOT EXISTS generation_mode VARCHAR(30) DEFAULT 'manual'"))
    await conn.execute(text("ALTER TABLE insight_data_source ADD COLUMN IF NOT EXISTS collection_strategy VARCHAR(30) DEFAULT 'standard'"))
    await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_insight_data_source_channel_id ON insight_data_source (channel_id)"))
    await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_insight_data_source_monitor_config_id ON insight_data_source (monitor_config_id)"))
    await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_insight_data_source_execution_role ON insight_data_source (execution_role)"))
    await conn.execute(
        text(
            "UPDATE insight_data_source "
            "SET execution_role = CASE "
            "WHEN source_type IN ('official_site', 'web_page') THEN '官网动态' "
            "WHEN source_type = 'finance_news' THEN '经营财经' "
            "WHEN source_type = 'patent_search' THEN '专利技术' "
            "WHEN source_type = 'government_policy' THEN '政策监管' "
            "WHEN source_type = 'ecommerce_search' THEN '电商新品' "
            "WHEN source_type = 'industry_media' THEN '行业资讯' "
            "WHEN source_type IN ('multi_news', 'baidu_news', 'bocha_news', 'wechat_public_account') THEN '企业新闻' "
            "ELSE '综合舆情' END "
            "WHERE is_deleted = 0 AND execution_role IS NULL"
        )
    )


async def _retire_legacy_insight_data_sources(conn):
    """废除旧数据源主概念：旧执行源软删除，调度状态汇总到监测配置。"""
    await conn.execute(
        text(
            "WITH source_state AS ("
            "SELECT monitor_config_id, "
            "array_remove(array_agg(DISTINCT channel_id), NULL) AS channel_ids, "
            "MAX(last_fetch_time) AS last_fetch_time, "
            "MAX(last_success_time) AS last_success_time, "
            "MIN(next_run_time) FILTER (WHERE schedule_enabled = TRUE AND status = 'enabled' AND fetch_frequency <> 'manual') AS next_run_time, "
            "MAX(consecutive_failure_count) AS consecutive_failure_count, "
            "MAX(last_failure_time) AS last_failure_time "
            "FROM insight_data_source "
            "WHERE is_deleted = 0 AND monitor_config_id IS NOT NULL "
            "GROUP BY monitor_config_id"
            ") "
            "UPDATE insight_monitor_config cfg "
            "SET last_fetch_time = COALESCE(cfg.last_fetch_time, source_state.last_fetch_time), "
            "last_success_time = COALESCE(cfg.last_success_time, source_state.last_success_time), "
            "next_run_time = CASE WHEN cfg.schedule_enabled = TRUE THEN COALESCE(cfg.next_run_time, source_state.next_run_time, NOW()) ELSE NULL END, "
            "consecutive_failure_count = GREATEST(COALESCE(cfg.consecutive_failure_count, 0), COALESCE(source_state.consecutive_failure_count, 0)), "
            "last_failure_time = COALESCE(cfg.last_failure_time, source_state.last_failure_time) "
            "FROM source_state "
            "WHERE cfg.id = source_state.monitor_config_id"
        )
    )
    await conn.execute(
        text(
            "UPDATE insight_monitor_config "
            "SET source_channel_ids = '[]'::jsonb "
            "WHERE is_deleted = 0 AND generation_mode = 'legacy_migrated'"
        )
    )
    await conn.execute(
        text(
            "UPDATE insight_data_source "
            "SET is_deleted = 1, "
            "status = 'disabled', "
            "schedule_enabled = FALSE, "
            "next_run_time = NULL, "
            "last_schedule_status = 'retired', "
            "last_schedule_message = '旧数据源概念已废除，调度改为按监测配置执行。', "
            "update_time = NOW() "
            "WHERE is_deleted = 0"
        )
    )
    await conn.execute(
        text(
            "UPDATE insight_data_source "
            "SET monitor_object_type = CASE WHEN company_id IS NULL THEN 'topic' ELSE 'company' END, "
            "monitor_object_id = COALESCE(monitor_object_id, company_id), "
            "generation_mode = COALESCE(generation_mode, 'manual'), "
            "collection_strategy = COALESCE(collection_strategy, 'standard') "
            "WHERE is_deleted = 0"
        )
    )


async def _ensure_insight_crawler_channel_values(conn):
    """补齐 Insight 采集通道枚举的新增值。"""
    await conn.execute(text("ALTER TYPE insightcrawlerchannel ADD VALUE IF NOT EXISTS 'BAIDU_NEWS'"))
    await conn.execute(text("ALTER TYPE insightcrawlerchannel ADD VALUE IF NOT EXISTS 'BOCHA_NEWS'"))
    await conn.execute(text("ALTER TYPE insightcrawlerchannel ADD VALUE IF NOT EXISTS 'DOUBAO_WEB_SEARCH'"))


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


async def _ensure_insight_feishu_brief_columns(conn):
    """补齐飞书简报计划的可配置工作流、多阶段调度和审计字段。"""
    await conn.execute(
        text(
            "ALTER TABLE insight_feishu_brief_plan "
            "ADD COLUMN IF NOT EXISTS material_days INTEGER DEFAULT 7 NOT NULL"
        )
    )
    await conn.execute(
        text(
            "ALTER TABLE insight_feishu_brief_plan "
            "ADD COLUMN IF NOT EXISTS day_of_month INTEGER DEFAULT 1"
        )
    )
    await conn.execute(
        text(
            "ALTER TABLE insight_feishu_brief_plan "
            "ADD COLUMN IF NOT EXISTS generation_strategy VARCHAR(40) DEFAULT 'auto' NOT NULL"
        )
    )
    await conn.execute(
        text(
            "ALTER TABLE insight_feishu_brief_plan "
            "ADD COLUMN IF NOT EXISTS generation_rules_json JSONB DEFAULT '{}'::jsonb NOT NULL"
        )
    )
    await conn.execute(
        text(
            "ALTER TABLE insight_feishu_brief_plan "
            "ADD COLUMN IF NOT EXISTS afternoon_recipients_json JSONB DEFAULT '[]'::jsonb NOT NULL"
        )
    )
    await conn.execute(
        text(
            "ALTER TABLE insight_feishu_brief_plan "
            "ADD COLUMN IF NOT EXISTS afternoon_push_time VARCHAR(5) DEFAULT '15:00' NOT NULL"
        )
    )
    await conn.execute(
        text(
            "ALTER TABLE insight_feishu_brief_run "
            "ADD COLUMN IF NOT EXISTS afternoon_push_scheduled_at TIMESTAMP"
        )
    )
    await conn.execute(
        text(
            "ALTER TABLE insight_feishu_brief_run "
            "ADD COLUMN IF NOT EXISTS afternoon_push_status VARCHAR(30)"
        )
    )
    await conn.execute(
        text(
            "ALTER TABLE insight_feishu_brief_run "
            "ADD COLUMN IF NOT EXISTS afternoon_pushed_count INTEGER DEFAULT 0 NOT NULL"
        )
    )
    await conn.execute(
        text(
            "ALTER TABLE insight_feishu_brief_run "
            "ADD COLUMN IF NOT EXISTS afternoon_failed_push_count INTEGER DEFAULT 0 NOT NULL"
        )
    )
    await conn.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_insight_feishu_brief_run_afternoon_due "
            "ON insight_feishu_brief_run (afternoon_push_status, afternoon_push_scheduled_at)"
        )
    )
    plan_columns = {
        "owner_user_id": "INTEGER",
        "review_weekday": "INTEGER DEFAULT 0",
        "review_time": "VARCHAR(5) DEFAULT '10:30' NOT NULL",
        "release_weekday": "INTEGER DEFAULT 1",
        "release_time": "VARCHAR(5) DEFAULT '15:00' NOT NULL",
        "workflow_config_json": "JSONB DEFAULT '{}'::jsonb NOT NULL",
        "prompt_config_json": "JSONB DEFAULT '{}'::jsonb NOT NULL",
        "material_scope_json": "JSONB DEFAULT '{}'::jsonb NOT NULL",
        "template_markdown": "TEXT",
        "config_version": "INTEGER DEFAULT 1 NOT NULL",
    }
    for column_name, column_type in plan_columns.items():
        await conn.execute(
            text(
                f"ALTER TABLE insight_feishu_brief_plan ADD COLUMN IF NOT EXISTS {column_name} {column_type}"
            )
        )
    run_columns = {
        "run_mode": "VARCHAR(20) DEFAULT 'formal' NOT NULL",
        "review_push_scheduled_at": "TIMESTAMP",
        "review_push_status": "VARCHAR(30)",
        "review_pushed_count": "INTEGER DEFAULT 0 NOT NULL",
        "review_failed_push_count": "INTEGER DEFAULT 0 NOT NULL",
        "occurrence_id": "INTEGER",
        "config_snapshot_json": "JSONB DEFAULT '{}'::jsonb NOT NULL",
        "owner_transfer_status": "VARCHAR(30)",
    }
    for column_name, column_type in run_columns.items():
        await conn.execute(
            text(
                f"ALTER TABLE insight_feishu_brief_run ADD COLUMN IF NOT EXISTS {column_name} {column_type}"
            )
        )
    await conn.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_insight_feishu_brief_run_review_due "
            "ON insight_feishu_brief_run (review_push_status, review_push_scheduled_at)"
        )
    )
    await conn.execute(
        text(
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_insight_feishu_brief_occurrence_period "
            "ON insight_feishu_brief_occurrence (plan_id, period_key) WHERE is_deleted = 0"
        )
    )
    await conn.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_insight_feishu_brief_agent_stage_run_sequence "
            "ON insight_feishu_brief_agent_stage (run_id, sequence_no)"
        )
    )
    # 旧计划直接迁入新工作流：原生成时间继续作为生成时间，原下午时间成为正式推送时间。
    await conn.execute(
        text(
            "UPDATE insight_feishu_brief_plan SET owner_user_id = NULLIF(create_by, '')::INTEGER "
            "WHERE owner_user_id IS NULL AND create_by ~ '^[0-9]+$'"
        )
    )
    await conn.execute(
        text(
            "UPDATE insight_feishu_brief_plan SET release_time = afternoon_push_time "
            "WHERE afternoon_push_time IS NOT NULL AND (release_time IS NULL OR release_time = '15:00')"
        )
    )
    await conn.execute(
        text(
            "UPDATE insight_feishu_brief_plan SET "
            "review_weekday = weekday, release_weekday = weekday, review_time = time_of_day, "
            "workflow_config_json = CAST(:workflow_config_json AS jsonb), "
            "material_scope_json = jsonb_build_object('mode','rolling_days','rolling_days',material_days,'start_weekday',0,'end_weekday',6,'filters','{}'::jsonb) "
            "WHERE workflow_config_json = '{}'::jsonb"
        ),
        {
            "workflow_config_json": (
                '{"max_revision_rounds":2,'
                '"research_sections":["政策","竞对","客户","技术","原料"]}'
            )
        },
    )
    await conn.execute(
        text(
            "INSERT INTO insight_feishu_brief_plan_version "
            "(plan_id, version_no, config_json, diff_json, create_time, update_time, is_deleted) "
            "SELECT p.id, COALESCE(p.config_version, 1), "
            "jsonb_build_object('migrated', true, 'generation_strategy', p.generation_strategy, "
            "'generation_rules', p.generation_rules_json, 'prompt_override', p.prompt_override, "
            "'template_markdown', p.template_markdown, 'workflow_config', p.workflow_config_json, "
            "'material_scope', p.material_scope_json), CAST(:diff_json AS jsonb), "
            "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 0 FROM insight_feishu_brief_plan p "
            "WHERE NOT EXISTS (SELECT 1 FROM insight_feishu_brief_plan_version v WHERE v.plan_id = p.id)"
        ),
        {"diff_json": '{"legacy_migrated":true}'},
    )


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

        turbo_model = (
            await session.exec(
                select(SysModel).where(
                    SysModel.model_code == "doubao-seed-2-1-turbo-260628",
                    SysModel.is_deleted == 0,
                )
            )
        ).first()
        if turbo_model:
            return
        volc_chat = (
            await session.exec(
                select(SysModel)
                .where(
                    SysModel.provider == "volcengine",
                    SysModel.model_type == "chat",
                    SysModel.is_deleted == 0,
                    SysModel.is_enabled,
                )
                .order_by(SysModel.model_level, SysModel.priority)
            )
        ).first()
        if not volc_chat:
            return
        session.add(
            SysModel(
                model_name="doubao-seed-2-1-turbo",
                model_code="doubao-seed-2-1-turbo-260628",
                provider="volcengine",
                api_key=volc_chat.api_key,
                base_url=volc_chat.base_url,
                model_level=2,
                model_type="chat",
                capability="general",
                max_tokens=4096,
                default_temperature=0.0,
                priority=6,
                is_enabled=True,
                comment="Insight 豆包联网搜索默认模型，复用已配置火山方舟连接。",
            )
        )
        await session.commit()
        logger.info("已补齐 Insight 豆包联网搜索模型配置：doubao-seed-2-1-turbo-260628")


async def _seed_embedding_model_configs():
    """基于现有火山引擎 Key 补齐 Insight 可用的向量模型配置。"""
    from sqlmodel import select

    from app.db.session import async_session
    from app.models.system.sys_model import SysModel

    async with async_session() as session:
        existing = (
            await session.exec(
                select(SysModel).where(
                    SysModel.model_type == "embedding",
                    SysModel.provider == "volcengine",
                    SysModel.is_deleted == 0,
                )
            )
        ).first()
        if existing:
            return
        volc_chat = (
            await session.exec(
                select(SysModel)
                .where(
                    SysModel.provider == "volcengine",
                    SysModel.is_enabled,
                    SysModel.is_deleted == 0,
                )
                .order_by(SysModel.model_level, SysModel.priority)
            )
        ).first()
        if not volc_chat:
            logger.warning("未找到火山引擎模型配置，跳过向量模型种子")
            return
        session.add(
            SysModel(
                model_name="doubao-embedding-vision",
                model_code="doubao-embedding-vision-251215",
                provider="volcengine",
                api_key=volc_chat.api_key,
                base_url=volc_chat.base_url,
                model_level=volc_chat.model_level,
                model_type="embedding",
                capability="embedding",
                max_tokens=8192,
                default_temperature=0,
                priority=1,
                is_enabled=True,
                comment="火山方舟多模态向量模型，用于 Insight RAG 与情报资产索引",
            )
        )
        await session.commit()
        logger.info("已补齐 Insight 火山向量模型配置：doubao-embedding-vision-251215")


async def _seed_insight_default_tags():
    """补齐 Insight AI 评审可选的默认受控标签。"""
    from sqlmodel import select

    from app.db.session import async_session
    from app.models.agent.insight import InsightTag, InsightTagCategory

    category_rows = [
        {"category_code": "业务价值", "category_name": "业务价值", "description": "销售机会、风险预警、合作机会等价值判断。", "color": "#2563eb", "sort_no": 10},
        {"category_code": "业务对象", "category_name": "业务对象", "description": "客户、竞对、供应商等对象关系。", "color": "#0891b2", "sort_no": 20},
        {"category_code": "情报主题", "category_name": "情报主题", "description": "政策、专利、新品、招投标等内容主题。", "color": "#16a34a", "sort_no": 30},
        {"category_code": "产品方向", "category_name": "产品方向", "description": "功能糖、植物蛋白、低糖趋势等产品方向。", "color": "#0d9488", "sort_no": 40},
        {"category_code": "经营动作", "category_name": "经营动作", "description": "产能扩张、融资并购等企业经营动作。", "color": "#9333ea", "sort_no": 50},
    ]
    seed_rows = [
        {"tag_code": "sales_opportunity", "tag_name": "销售机会", "tag_type": "业务价值", "color": "#2563eb", "sort_no": 10},
        {"tag_code": "customer_signal", "tag_name": "客户动向", "tag_type": "业务对象", "color": "#0891b2", "sort_no": 20},
        {"tag_code": "competitor_update", "tag_name": "竞对动态", "tag_type": "业务对象", "color": "#7c3aed", "sort_no": 30},
        {"tag_code": "new_product", "tag_name": "新品扩张", "tag_type": "情报主题", "color": "#16a34a", "sort_no": 40},
        {"tag_code": "policy_regulation", "tag_name": "政策监管", "tag_type": "情报主题", "color": "#0f766e", "sort_no": 50},
        {"tag_code": "patent_technology", "tag_name": "专利技术", "tag_type": "情报主题", "color": "#4f46e5", "sort_no": 60},
        {"tag_code": "price_market", "tag_name": "价格行情", "tag_type": "情报主题", "color": "#ea580c", "sort_no": 70},
        {"tag_code": "risk_warning", "tag_name": "风险预警", "tag_type": "业务价值", "color": "#dc2626", "sort_no": 80},
        {"tag_code": "tender_bid", "tag_name": "招投标", "tag_type": "情报主题", "color": "#9333ea", "sort_no": 90},
        {"tag_code": "cooperation_opportunity", "tag_name": "合作机会", "tag_type": "业务价值", "color": "#0284c7", "sort_no": 100},
        {"tag_code": "low_sugar_trend", "tag_name": "低糖趋势", "tag_type": "产品方向", "color": "#059669", "sort_no": 110},
        {"tag_code": "plant_protein", "tag_name": "植物蛋白", "tag_type": "产品方向", "color": "#65a30d", "sort_no": 120},
        {"tag_code": "functional_sugar", "tag_name": "功能糖", "tag_type": "产品方向", "color": "#0d9488", "sort_no": 130},
        {"tag_code": "capacity_expansion", "tag_name": "产能扩张", "tag_type": "经营动作", "color": "#2563eb", "sort_no": 140},
        {"tag_code": "financing_ma", "tag_name": "融资并购", "tag_type": "经营动作", "color": "#9333ea", "sort_no": 150},
    ]
    async with async_session() as session:
        existing_categories = {
            row
            for row in (
                await session.exec(
                    select(InsightTagCategory.category_code).where(
                        InsightTagCategory.category_code.in_([item["category_code"] for item in category_rows]),
                        InsightTagCategory.is_deleted == 0,
                    )
                )
            ).all()
        }
        created_categories = 0
        for item in category_rows:
            if item["category_code"] in existing_categories:
                continue
            session.add(InsightTagCategory(**item, status="active"))
            created_categories += 1
        existing_codes = {
            row
            for row in (
                await session.exec(
                    select(InsightTag.tag_code).where(
                        InsightTag.tag_code.in_([item["tag_code"] for item in seed_rows]),
                        InsightTag.is_deleted == 0,
                    )
                )
            ).all()
        }
        created = 0
        for item in seed_rows:
            if item["tag_code"] in existing_codes:
                continue
            session.add(InsightTag(**item, status="active"))
            created += 1
        if created:
            await session.commit()
            logger.info(f"已补齐 Insight 默认受控标签 {created} 个")
        elif created_categories:
            await session.commit()
        if created_categories:
            logger.info(f"已补齐 Insight 默认标签分类 {created_categories} 个")


async def _seed_insight_default_roles():
    """补齐 Insight 专用角色，避免复用平台通用角色造成权限混乱。"""
    from app.db.session import async_session
    from app.services.agent.insight.role_service import insight_role_service

    async with async_session() as session:
        await insight_role_service.seed_defaults(session)
