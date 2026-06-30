from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import settings  # noqa: E402


TEST_PATTERNS = [
    "%测试客户%",
    "%烟测%",
    "%样例%",
    "%示例数据%",
    "%仅用于测试%",
]
DEMO_NAME_PATTERNS = ["%demo%", "%DEMO%", "%Demo%"]
SMOKE_PATTERNS = ['%"smoke": true%', '%"source": "smoke"%', "%source': 'smoke'%"]
GENERIC_TEST_REPORT_TITLES = ["专题报告", "测试报告", "烟测报告"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="清理 Insight 测试、烟测、样例数据")
    parser.add_argument("--execute", action="store_true", help="实际执行清理；不加时只预览命中数量和样例")
    parser.add_argument("--include-generic-report", action="store_true", default=True, help="清理标题为“专题报告”等通用测试报告")
    parser.add_argument("--connect-timeout", type=int, default=10, help="数据库连接超时秒数")
    return parser.parse_args()


def like_clause(fields: list[str], prefix: str, pattern_count: int) -> str:
    parts = []
    for field in fields:
        parts.extend(f"{field} ILIKE :{prefix}_{index}" for index in range(pattern_count))
    return "(" + " OR ".join(parts) + ")"


def strict_clause(fields: list[str]) -> str:
    return like_clause(fields, "strict_pattern", len(TEST_PATTERNS))


def demo_name_clause(fields: list[str]) -> str:
    return like_clause(fields, "demo_pattern", len(DEMO_NAME_PATTERNS))


def smoke_clause(fields: list[str]) -> str:
    return like_clause(fields, "smoke_pattern", len(SMOKE_PATTERNS))


def params() -> dict[str, str]:
    bind: dict[str, str] = {}
    bind.update({f"strict_pattern_{index}": value for index, value in enumerate(TEST_PATTERNS)})
    bind.update({f"demo_pattern_{index}": value for index, value in enumerate(DEMO_NAME_PATTERNS)})
    bind.update({f"smoke_pattern_{index}": value for index, value in enumerate(SMOKE_PATTERNS)})
    return bind


async def execute_scalar(conn, sql: str, bind: dict[str, Any] | None = None) -> int:
    result = await conn.execute(text(sql), bind or {})
    value = result.scalar_one()
    return int(value or 0)


async def execute_count(conn, sql: str, bind: dict[str, Any] | None = None) -> int:
    result = await conn.execute(text(sql), bind or {})
    return int(result.rowcount or 0)


async def prepare_temp_tables(conn, *, include_generic_report: bool) -> dict[str, int]:
    bind = params()
    for table in [
        "tmp_insight_test_candidate_ids",
        "tmp_insight_test_crawl_ids",
        "tmp_insight_test_intelligence_ids",
        "tmp_insight_test_asset_ids",
        "tmp_insight_test_report_ids",
        "tmp_insight_test_company_ids",
        "tmp_insight_test_monitor_config_ids",
        "tmp_insight_test_task_ids",
    ]:
        await conn.execute(text(f"CREATE TEMP TABLE {table} (id BIGINT PRIMARY KEY) ON COMMIT DROP"))

    candidate_match = "(" + " OR ".join(
        [
            strict_clause(
                [
                    "c.candidate_title",
                    "COALESCE(c.candidate_summary, '')",
                    "COALESCE(c.subject_name, '')",
                    "COALESCE(CAST(c.suggested_tags AS TEXT), '')",
                    "COALESCE(cr.query_text, '')",
                    "COALESCE(cr.source_title, '')",
                    "COALESCE(cr.snippet, '')",
                ]
            ),
            demo_name_clause(["c.candidate_title", "COALESCE(c.subject_name, '')", "COALESCE(cr.query_text, '')"]),
            smoke_clause(["COALESCE(CAST(c.suggested_tags AS TEXT), '')", "COALESCE(CAST(cr.crawl_metadata AS TEXT), '')"]),
        ]
    ) + ")"
    await conn.execute(
        text(
            f"""
            INSERT INTO tmp_insight_test_candidate_ids(id)
            SELECT DISTINCT c.id
            FROM insight_intelligence_candidate c
            LEFT JOIN insight_crawl_result cr ON cr.id = c.crawl_result_id
            WHERE c.is_deleted = 0 AND {candidate_match}
            ON CONFLICT DO NOTHING
            """
        ),
        bind,
    )

    crawl_match = "(" + " OR ".join(
        [
            strict_clause(
                [
                    "COALESCE(cr.query_text, '')",
                    "COALESCE(cr.source_title, '')",
                    "COALESCE(cr.snippet, '')",
                    "COALESCE(cr.markdown_content, '')",
                ]
            ),
            demo_name_clause(["COALESCE(cr.query_text, '')", "COALESCE(cr.source_title, '')"]),
            smoke_clause(["COALESCE(CAST(cr.crawl_metadata AS TEXT), '')"]),
        ]
    ) + ")"
    await conn.execute(
        text(
            f"""
            INSERT INTO tmp_insight_test_crawl_ids(id)
            SELECT DISTINCT cr.id
            FROM insight_crawl_result cr
            WHERE cr.is_deleted = 0 AND {crawl_match}
            ON CONFLICT DO NOTHING
            """
        ),
        bind,
    )
    await conn.execute(
        text(
            """
            INSERT INTO tmp_insight_test_crawl_ids(id)
            SELECT DISTINCT c.crawl_result_id
            FROM insight_intelligence_candidate c
            JOIN tmp_insight_test_candidate_ids t ON t.id = c.id
            WHERE c.crawl_result_id IS NOT NULL
            ON CONFLICT DO NOTHING
            """
        )
    )

    intelligence_match = "(" + " OR ".join(
        [
            strict_clause(
                [
                    "i.title",
                    "COALESCE(i.summary, '')",
                    "COALESCE(i.content, '')",
                    "COALESCE(i.subject_name, '')",
                    "COALESCE(CAST(i.raw_payload AS TEXT), '')",
                ]
            ),
            demo_name_clause(["i.title", "COALESCE(i.subject_name, '')"]),
            smoke_clause(["COALESCE(CAST(i.raw_payload AS TEXT), '')"]),
        ]
    ) + ")"
    await conn.execute(
        text(
            f"""
            INSERT INTO tmp_insight_test_intelligence_ids(id)
            SELECT DISTINCT i.id
            FROM insight_intelligence i
            WHERE i.is_deleted = 0 AND {intelligence_match}
            ON CONFLICT DO NOTHING
            """
        ),
        bind,
    )
    await conn.execute(
        text(
            """
            INSERT INTO tmp_insight_test_intelligence_ids(id)
            SELECT DISTINCT c.promoted_intelligence_id
            FROM insight_intelligence_candidate c
            JOIN tmp_insight_test_candidate_ids t ON t.id = c.id
            WHERE c.promoted_intelligence_id IS NOT NULL
            ON CONFLICT DO NOTHING
            """
        )
    )
    source_match = "(" + " OR ".join(
        [
            strict_clause(["COALESCE(s.source_title, '')", "COALESCE(s.content_excerpt, '')"]),
            demo_name_clause(["COALESCE(s.source_title, '')"]),
            smoke_clause(["COALESCE(CAST(s.source_metadata AS TEXT), '')"]),
        ]
    ) + ")"
    await conn.execute(
        text(
            f"""
            INSERT INTO tmp_insight_test_intelligence_ids(id)
            SELECT DISTINCT s.intelligence_id
            FROM insight_intelligence_source s
            WHERE s.is_deleted = 0 AND {source_match}
            ON CONFLICT DO NOTHING
            """
        ),
        bind,
    )

    asset_match = "(" + " OR ".join(
        [
            strict_clause(
                [
                    "a.title",
                    "COALESCE(a.summary, '')",
                    "COALESCE(a.evidence_text, '')",
                    "COALESCE(a.subject_name, '')",
                    "COALESCE(CAST(a.tags AS TEXT), '')",
                    "COALESCE(CAST(a.structured_payload AS TEXT), '')",
                    "COALESCE(CAST(a.review_payload AS TEXT), '')",
                ]
            ),
            demo_name_clause(["a.title", "COALESCE(a.subject_name, '')"]),
            smoke_clause(
                [
                    "COALESCE(CAST(a.tags AS TEXT), '')",
                    "COALESCE(CAST(a.structured_payload AS TEXT), '')",
                    "COALESCE(CAST(a.review_payload AS TEXT), '')",
                ]
            ),
        ]
    ) + ")"
    await conn.execute(
        text(
            f"""
            INSERT INTO tmp_insight_test_asset_ids(id)
            SELECT DISTINCT a.id
            FROM insight_intelligence_asset a
            WHERE a.is_deleted = 0
              AND (
                {asset_match}
                OR a.intelligence_id IN (SELECT id FROM tmp_insight_test_intelligence_ids)
                OR a.candidate_id IN (SELECT id FROM tmp_insight_test_candidate_ids)
                OR a.crawl_result_id IN (SELECT id FROM tmp_insight_test_crawl_ids)
              )
            ON CONFLICT DO NOTHING
            """
        ),
        bind,
    )

    report_match = "(" + " OR ".join(
        [
            strict_clause(["r.title", "COALESCE(r.summary, '')", "COALESCE(r.company_name, '')", "COALESCE(CAST(r.content_json AS TEXT), '')"]),
            demo_name_clause(["r.title", "COALESCE(r.company_name, '')"]),
            smoke_clause(["COALESCE(CAST(r.content_json AS TEXT), '')"]),
        ]
    ) + ")"
    title_filter = ""
    title_bind: dict[str, Any] = {}
    if include_generic_report:
        title_names = ", ".join(f":report_title_{index}" for index in range(len(GENERIC_TEST_REPORT_TITLES)))
        title_filter = f" OR r.title IN ({title_names})"
        title_bind = {f"report_title_{index}": value for index, value in enumerate(GENERIC_TEST_REPORT_TITLES)}
    await conn.execute(
        text(
            f"""
            INSERT INTO tmp_insight_test_report_ids(id)
            SELECT DISTINCT r.id
            FROM insight_report r
            WHERE r.is_deleted = 0 AND ({report_match}{title_filter})
            ON CONFLICT DO NOTHING
            """
        ),
        bind | title_bind,
    )
    await conn.execute(
        text(
            """
            INSERT INTO tmp_insight_test_report_ids(id)
            SELECT DISTINCT m.report_id
            FROM insight_report_material m
            WHERE m.is_deleted = 0
              AND m.intelligence_id IN (SELECT id FROM tmp_insight_test_intelligence_ids)
            ON CONFLICT DO NOTHING
            """
        )
    )

    company_match = "(" + " OR ".join(
        [
            strict_clause(["co.name", "COALESCE(co.short_name, '')", "COALESCE(co.description, '')", "COALESCE(CAST(co.profile_json AS TEXT), '')"]),
            demo_name_clause(["co.name", "COALESCE(co.short_name, '')"]),
            smoke_clause(["COALESCE(CAST(co.profile_json AS TEXT), '')"]),
        ]
    ) + ")"
    await conn.execute(
        text(
            f"""
            INSERT INTO tmp_insight_test_company_ids(id)
            SELECT DISTINCT co.id
            FROM insight_company co
            WHERE co.is_deleted = 0 AND {company_match}
            ON CONFLICT DO NOTHING
            """
        ),
        bind,
    )

    monitor_match = "(" + " OR ".join(
        [
            strict_clause(
                [
                    "mc.config_name",
                    "COALESCE(mc.object_name, '')",
                    "COALESCE(mc.ai_review_prompt, '')",
                    "COALESCE(CAST(mc.keywords AS TEXT), '')",
                    "COALESCE(CAST(mc.config_json AS TEXT), '')",
                ]
            ),
            demo_name_clause(["mc.config_name", "COALESCE(mc.object_name, '')"]),
            smoke_clause(["COALESCE(CAST(mc.config_json AS TEXT), '')"]),
        ]
    ) + ")"
    await conn.execute(
        text(
            f"""
            INSERT INTO tmp_insight_test_monitor_config_ids(id)
            SELECT DISTINCT mc.id
            FROM insight_monitor_config mc
            WHERE mc.is_deleted = 0
              AND (
                {monitor_match}
                OR mc.object_id IN (SELECT id FROM tmp_insight_test_company_ids)
              )
            ON CONFLICT DO NOTHING
            """
        ),
        bind,
    )

    task_match = "(" + " OR ".join(
        [
            strict_clause(["COALESCE(CAST(t.input_payload AS TEXT), '')", "COALESCE(CAST(t.output_payload AS TEXT), '')", "COALESCE(t.error_message, '')"]),
            smoke_clause(["COALESCE(CAST(t.input_payload AS TEXT), '')", "COALESCE(CAST(t.output_payload AS TEXT), '')"]),
        ]
    ) + ")"
    await conn.execute(
        text(
            f"""
            INSERT INTO tmp_insight_test_task_ids(id)
            SELECT DISTINCT t.id
            FROM insight_task t
            WHERE t.is_deleted = 0
              AND (
                {task_match}
                OR t.monitor_config_id IN (SELECT id FROM tmp_insight_test_monitor_config_ids)
                OR t.intelligence_id IN (SELECT id FROM tmp_insight_test_intelligence_ids)
                OR t.report_id IN (SELECT id FROM tmp_insight_test_report_ids)
              )
            ON CONFLICT DO NOTHING
            """
        ),
        bind,
    )
    await conn.execute(
        text(
            """
            INSERT INTO tmp_insight_test_task_ids(id)
            SELECT DISTINCT cr.task_id
            FROM insight_crawl_result cr
            JOIN tmp_insight_test_crawl_ids c ON c.id = cr.id
            WHERE cr.task_id IS NOT NULL
            ON CONFLICT DO NOTHING
            """
        )
    )

    return {
        "candidates": await execute_scalar(conn, "SELECT count(*) FROM tmp_insight_test_candidate_ids"),
        "crawls": await execute_scalar(conn, "SELECT count(*) FROM tmp_insight_test_crawl_ids"),
        "intelligences": await execute_scalar(conn, "SELECT count(*) FROM tmp_insight_test_intelligence_ids"),
        "assets": await execute_scalar(conn, "SELECT count(*) FROM tmp_insight_test_asset_ids"),
        "reports": await execute_scalar(conn, "SELECT count(*) FROM tmp_insight_test_report_ids"),
        "companies": await execute_scalar(conn, "SELECT count(*) FROM tmp_insight_test_company_ids"),
        "monitor_configs": await execute_scalar(conn, "SELECT count(*) FROM tmp_insight_test_monitor_config_ids"),
        "tasks": await execute_scalar(conn, "SELECT count(*) FROM tmp_insight_test_task_ids"),
    }


async def load_samples(conn) -> dict[str, list[dict[str, Any]]]:
    queries = {
        "candidates": """
            SELECT c.id, c.candidate_title AS title
            FROM insight_intelligence_candidate c
            JOIN tmp_insight_test_candidate_ids t ON t.id = c.id
            ORDER BY c.create_time DESC
            LIMIT 10
        """,
        "intelligences": """
            SELECT i.id, i.title
            FROM insight_intelligence i
            JOIN tmp_insight_test_intelligence_ids t ON t.id = i.id
            ORDER BY i.create_time DESC
            LIMIT 10
        """,
        "reports": """
            SELECT r.id, r.title
            FROM insight_report r
            JOIN tmp_insight_test_report_ids t ON t.id = r.id
            ORDER BY r.create_time DESC
            LIMIT 10
        """,
        "monitor_configs": """
            SELECT mc.id, mc.config_name AS title
            FROM insight_monitor_config mc
            JOIN tmp_insight_test_monitor_config_ids t ON t.id = mc.id
            ORDER BY mc.create_time DESC
            LIMIT 10
        """,
        "companies": """
            SELECT co.id, co.name AS title
            FROM insight_company co
            JOIN tmp_insight_test_company_ids t ON t.id = co.id
            ORDER BY co.create_time DESC
            LIMIT 10
        """,
    }
    samples: dict[str, list[dict[str, Any]]] = {}
    for key, sql in queries.items():
        result = await conn.execute(text(sql))
        samples[key] = [dict(row._mapping) for row in result.fetchall()]
    return samples


async def cleanup(conn) -> dict[str, int]:
    statements = [
        (
            "visibility_rules",
            """
            UPDATE insight_visibility_rule
            SET is_deleted = 1, status = 'inactive', update_time = NOW()
            WHERE is_deleted = 0 AND (
              (target_type = 'intelligence' AND target_id IN (SELECT id FROM tmp_insight_test_intelligence_ids))
              OR (target_type = 'report' AND target_id IN (SELECT id FROM tmp_insight_test_report_ids))
            )
            """,
        ),
        (
            "notifications",
            """
            UPDATE insight_notification
            SET is_deleted = 1, status = 'deleted', update_time = NOW()
            WHERE is_deleted = 0 AND (
              (target_type = 'intelligence' AND target_id IN (SELECT id FROM tmp_insight_test_intelligence_ids))
              OR (target_type = 'report' AND target_id IN (SELECT id FROM tmp_insight_test_report_ids))
              OR title ILIKE ANY (ARRAY['%测试客户%', '%烟测%', '%样例%', '%示例数据%', '%仅用于测试%'])
              OR COALESCE(target_title, '') ILIKE ANY (ARRAY['%测试客户%', '%烟测%', '%样例%', '%示例数据%', '%仅用于测试%'])
            )
            """,
        ),
        (
            "report_exports",
            """
            UPDATE insight_report_export
            SET is_deleted = 1, status = 'deleted', update_time = NOW()
            WHERE is_deleted = 0 AND report_id IN (SELECT id FROM tmp_insight_test_report_ids)
            """,
        ),
        (
            "report_versions",
            """
            UPDATE insight_report_version
            SET is_deleted = 1, update_time = NOW()
            WHERE is_deleted = 0 AND report_id IN (SELECT id FROM tmp_insight_test_report_ids)
            """,
        ),
        (
            "report_materials",
            """
            UPDATE insight_report_material
            SET is_deleted = 1, update_time = NOW()
            WHERE is_deleted = 0 AND (
              report_id IN (SELECT id FROM tmp_insight_test_report_ids)
              OR intelligence_id IN (SELECT id FROM tmp_insight_test_intelligence_ids)
            )
            """,
        ),
        (
            "reports",
            """
            UPDATE insight_report
            SET is_deleted = 1, status = 'deleted', update_time = NOW()
            WHERE is_deleted = 0 AND id IN (SELECT id FROM tmp_insight_test_report_ids)
            """,
        ),
        (
            "asset_vectors",
            """
            UPDATE insight_asset_vector
            SET is_deleted = 1, status = 'deleted', update_time = NOW()
            WHERE is_deleted = 0 AND asset_id IN (SELECT id FROM tmp_insight_test_asset_ids)
            """,
        ),
        (
            "graph_edges",
            """
            UPDATE insight_graph_edge
            SET is_deleted = 1, status = 'inactive', update_time = NOW()
            WHERE is_deleted = 0 AND (
              source_asset_id IN (SELECT id FROM tmp_insight_test_asset_ids)
              OR source_node_id IN (SELECT id FROM insight_graph_node WHERE source_asset_id IN (SELECT id FROM tmp_insight_test_asset_ids))
              OR target_node_id IN (SELECT id FROM insight_graph_node WHERE source_asset_id IN (SELECT id FROM tmp_insight_test_asset_ids))
            )
            """,
        ),
        (
            "graph_nodes",
            """
            UPDATE insight_graph_node
            SET is_deleted = 1, status = 'inactive', update_time = NOW()
            WHERE is_deleted = 0 AND source_asset_id IN (SELECT id FROM tmp_insight_test_asset_ids)
            """,
        ),
        (
            "assets",
            """
            UPDATE insight_intelligence_asset
            SET is_deleted = 1, status = 'deleted', update_time = NOW()
            WHERE is_deleted = 0 AND id IN (SELECT id FROM tmp_insight_test_asset_ids)
            """,
        ),
        (
            "intelligence_tags",
            """
            UPDATE insight_intelligence_tag
            SET is_deleted = 1, update_time = NOW()
            WHERE is_deleted = 0 AND intelligence_id IN (SELECT id FROM tmp_insight_test_intelligence_ids)
            """,
        ),
        (
            "user_pools",
            """
            UPDATE insight_user_intelligence_pool
            SET is_deleted = 1, status = 'inactive', update_time = NOW()
            WHERE is_deleted = 0 AND intelligence_id IN (SELECT id FROM tmp_insight_test_intelligence_ids)
            """,
        ),
        (
            "ai_analysis",
            """
            UPDATE insight_ai_analysis
            SET is_deleted = 1, status = 'deleted', update_time = NOW()
            WHERE is_deleted = 0 AND intelligence_id IN (SELECT id FROM tmp_insight_test_intelligence_ids)
            """,
        ),
        (
            "review_records",
            """
            UPDATE insight_review_record
            SET is_deleted = 1, update_time = NOW()
            WHERE is_deleted = 0 AND (
              candidate_id IN (SELECT id FROM tmp_insight_test_candidate_ids)
              OR intelligence_id IN (SELECT id FROM tmp_insight_test_intelligence_ids)
            )
            """,
        ),
        (
            "intelligence_sources",
            """
            UPDATE insight_intelligence_source
            SET is_deleted = 1, update_time = NOW()
            WHERE is_deleted = 0 AND intelligence_id IN (SELECT id FROM tmp_insight_test_intelligence_ids)
            """,
        ),
        (
            "intelligences",
            """
            UPDATE insight_intelligence
            SET is_deleted = 1, status = 'deleted', update_time = NOW()
            WHERE is_deleted = 0 AND id IN (SELECT id FROM tmp_insight_test_intelligence_ids)
            """,
        ),
        (
            "candidates",
            """
            UPDATE insight_intelligence_candidate
            SET is_deleted = 1, status = 'deleted', update_time = NOW()
            WHERE is_deleted = 0 AND id IN (SELECT id FROM tmp_insight_test_candidate_ids)
            """,
        ),
        (
            "crawls",
            """
            UPDATE insight_crawl_result
            SET is_deleted = 1, update_time = NOW()
            WHERE is_deleted = 0 AND id IN (SELECT id FROM tmp_insight_test_crawl_ids)
            """,
        ),
        (
            "tasks",
            """
            UPDATE insight_task
            SET is_deleted = 1, update_time = NOW()
            WHERE is_deleted = 0 AND id IN (SELECT id FROM tmp_insight_test_task_ids)
            """,
        ),
        (
            "monitor_configs",
            """
            UPDATE insight_monitor_config
            SET is_deleted = 1, status = 'deleted', schedule_enabled = FALSE, update_time = NOW()
            WHERE is_deleted = 0 AND id IN (SELECT id FROM tmp_insight_test_monitor_config_ids)
            """,
        ),
        (
            "companies",
            """
            UPDATE insight_company
            SET is_deleted = 1, status = 'deleted', update_time = NOW()
            WHERE is_deleted = 0 AND id IN (SELECT id FROM tmp_insight_test_company_ids)
            """,
        ),
    ]
    result: dict[str, int] = {}
    for key, sql in statements:
        result[key] = await execute_count(conn, sql)
    return result


async def main_async(args: argparse.Namespace) -> dict[str, Any]:
    engine = create_async_engine(
        str(settings.sqlalchemy_database_uri),
        echo=False,
        future=True,
        pool_pre_ping=True,
        connect_args={"timeout": args.connect_timeout},
    )
    try:
        async with engine.begin() as conn:
            counts = await prepare_temp_tables(conn, include_generic_report=args.include_generic_report)
            samples = await load_samples(conn)
            cleanup_counts: dict[str, int] = {}
            if args.execute:
                cleanup_counts = await cleanup(conn)
            return {
                "executed": bool(args.execute),
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "match_counts": counts,
                "cleanup_counts": cleanup_counts,
                "samples": samples,
            }
    finally:
        await engine.dispose()


def main() -> None:
    args = parse_args()
    summary = asyncio.run(main_async(args))
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
