import argparse
import asyncio
import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text

from app.db.session import async_session, engine


engine.echo = False


async def fetch_all(sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    async with async_session() as db:
        result = await db.exec(text(sql), params=params or {})
        return [dict(row._mapping) for row in result.fetchall()]


def normalize_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "total_seconds"):
        return str(value)
    return value


def normalize_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{key: normalize_value(value) for key, value in row.items()} for row in rows]


async def build_snapshot(minutes: int) -> dict[str, Any]:
    source_summary = await fetch_all(
        """
        select count(*) total,
               count(*) filter (where status <> 'deleted') not_deleted,
               count(*) filter (where status <> 'deleted' and schedule_enabled = true) schedule_enabled,
               count(*) filter (where status = 'enabled') enabled_status
        from insight_data_source
        """
    )
    source_types = await fetch_all(
        """
        select source_type, count(*) total,
               count(*) filter (where schedule_enabled = true) scheduled
        from insight_data_source
        where status <> 'deleted'
        group by source_type
        order by total desc
        """
    )
    task_summary = await fetch_all(
        """
        select status::text status, count(*) total
        from insight_task
        group by status::text
        order by total desc
        """
    )
    latest_activity = await fetch_all(
        """
        select max(coalesce(started_at, create_time)) as latest_task_time
        from insight_task
        """
    )
    recent_window_tasks = await fetch_all(
        """
        with activity as (
            select greatest(
                coalesce(max(coalesce(started_at, create_time)), now() at time zone 'Asia/Shanghai'),
                now() at time zone 'Asia/Shanghai'
            ) as latest_at
            from insight_task
        )
        select status::text status, task_type, count(*) total
        from insight_task, activity
        where activity.latest_at is not null
          and coalesce(started_at, create_time) >= activity.latest_at - (:minutes * interval '1 minute')
        group by status::text, task_type
        order by status::text, task_type
        """,
        {"minutes": minutes},
    )
    running_or_pending = await fetch_all(
        """
        with activity as (
            select greatest(
                coalesce(max(coalesce(started_at, create_time)), now() at time zone 'Asia/Shanghai'),
                now() at time zone 'Asia/Shanghai'
            ) as latest_at
            from insight_task
        )
        select t.id, t.data_source_id, s.source_name, t.task_type, t.status::text status,
               t.progress, t.started_at, activity.latest_at - coalesce(t.started_at, t.create_time) as age
        from insight_task t
        cross join activity
        left join insight_data_source s on s.id = t.data_source_id
        where t.status::text in ('RUNNING', 'PENDING')
        order by coalesce(t.started_at, t.create_time) asc
        """
    )
    recent_failures = await fetch_all(
        """
        select t.id, t.data_source_id, s.source_name, t.task_type, t.started_at, t.finished_at,
               left(coalesce(t.error_message, ''), 260) error_message
        from insight_task t
        left join insight_data_source s on s.id = t.data_source_id
        where t.status::text = 'FAILED'
        order by coalesce(t.finished_at, t.started_at, t.create_time) desc nulls last
        limit 12
        """
    )
    failed_by_source = await fetch_all(
        """
        select t.data_source_id, max(s.source_name) source_name, count(*) failed,
               left(max(t.error_message), 220) sample_error,
               max(t.finished_at) last_failed_at
        from insight_task t
        left join insight_data_source s on s.id = t.data_source_id
        where t.status::text = 'FAILED'
        group by t.data_source_id
        order by failed desc
        limit 12
        """
    )
    intelligence_summary = await fetch_all(
        """
        select status, review_status, count(*) total,
               count(*) filter (where summary is not null and length(trim(summary)) > 0) with_summary,
               count(*) filter (where publish_time is not null) with_publish_time
        from insight_intelligence
        group by status, review_status
        order by total desc
        """
    )
    candidate_summary = await fetch_all(
        """
        select status, review_status::text review_status, count(*) total,
               count(*) filter (where candidate_summary is not null and length(trim(candidate_summary)) > 0) with_summary
        from insight_intelligence_candidate
        group by status, review_status::text
        order by total desc
        """
    )
    ai_field_coverage = await fetch_all(
        """
        select count(*) total,
               count(*) filter (where summary is not null and length(trim(summary)) > 0) with_summary,
               count(*) filter (where sentiment in ('positive', 'neutral', 'negative', 'mixed')) with_sentiment,
               count(*) filter (where raw_payload ? 'suggested_tags' or raw_payload->'ai_analysis' ? 'tags') with_tags,
               count(*) filter (where jsonb_array_length(coalesce(raw_payload->'ai_analysis'->'opportunities', '[]'::jsonb)) > 0) with_opportunities,
               count(*) filter (where jsonb_array_length(coalesce(raw_payload->'ai_analysis'->'risks', '[]'::jsonb)) > 0) with_risks,
               count(*) filter (
                   where exists (
                       select 1
                       from insight_intelligence_source src
                       where src.intelligence_id = insight_intelligence.id
                         and src.source_url is not null
                         and length(src.source_url) > 0
                   )
               ) with_source_url
        from insight_intelligence
        where status = 'active' and review_status = 'approved'
        """
    )
    report_material_health = await fetch_all(
        """
        with active_counts as (
            select report_id, count(*) active_materials
            from insight_report_material
            where is_deleted = 0
            group by report_id
        )
        select
            (select count(*)
             from insight_report_material m
             left join insight_intelligence i on i.id = m.intelligence_id
             where m.is_deleted = 0
               and (i.id is null or i.status <> 'active' or i.review_status <> 'approved')) as bad_active_materials,
            (select count(*)
             from insight_report r
             left join active_counts a on a.report_id = r.id
             where r.material_count <> coalesce(a.active_materials, 0)) as material_count_mismatch_reports,
            (select count(*)
             from insight_report_material
             where is_deleted = 0) as active_report_materials
        """
    )
    hourly_intelligence = await fetch_all(
        """
        select date_trunc('hour', create_time) as bucket, count(*) total
        from insight_intelligence
        where status = 'active' and review_status = 'approved' and create_time >= current_date
        group by 1
        order by 1 desc
        limit 12
        """
    )
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "window_minutes": minutes,
        "source_summary": normalize_rows(source_summary),
        "source_types": normalize_rows(source_types),
        "task_summary": normalize_rows(task_summary),
        "latest_activity": normalize_rows(latest_activity),
        "recent_window_tasks": normalize_rows(recent_window_tasks),
        "running_or_pending": normalize_rows(running_or_pending),
        "recent_failures": normalize_rows(recent_failures),
        "failed_by_source": normalize_rows(failed_by_source),
        "intelligence_summary": normalize_rows(intelligence_summary),
        "candidate_summary": normalize_rows(candidate_summary),
        "ai_field_coverage": normalize_rows(ai_field_coverage),
        "report_material_health": normalize_rows(report_material_health),
        "hourly_intelligence_today": normalize_rows(hourly_intelligence),
    }


async def main() -> None:
    parser = argparse.ArgumentParser(description="输出 Insight 平台真实运行监督快照。")
    parser.add_argument("--minutes", type=int, default=60, help="统计最近多少分钟内的任务。")
    args = parser.parse_args()
    snapshot = await build_snapshot(max(args.minutes, 1))
    print(json.dumps(snapshot, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
