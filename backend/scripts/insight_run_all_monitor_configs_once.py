import argparse
import asyncio
import json
import logging
import traceback
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlmodel import select

from app.core.config import settings
from app.db.session import async_session, engine
from app.models.agent.insight import InsightMonitorConfig
from app.services.agent.insight.monitor_execution_service import insight_monitor_execution_service


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _write_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(payload, ensure_ascii=False, default=_json_default) + "\n")


def _response_counts(response: Any) -> dict[str, int]:
    task_payload = getattr(getattr(response, "task", None), "output_payload", None) or {}
    rejected_items = task_payload.get("rejected_items") if isinstance(task_payload, dict) else []
    filter_summary = task_payload.get("filter_summary") if isinstance(task_payload, dict) else {}
    return {
        "hits": len(getattr(response, "hits", []) or []),
        "discovered": len(getattr(response, "discovered_results", []) or []),
        "candidates": len(getattr(response, "candidates", []) or []),
        "history_duplicates": sum(
            1
            for item in rejected_items or []
            if isinstance(item, dict) and item.get("stage") == "history_dedupe"
        ),
        "time_window_kept": int((filter_summary or {}).get("time_window_kept_count") or 0),
        "history_dedupe_kept": int((filter_summary or {}).get("history_dedupe_kept_count") or 0),
    }


async def main() -> int:
    parser = argparse.ArgumentParser(description="立即执行所有 active Insight 监测配置，用于全量补数和链路测试。")
    parser.add_argument("--limit", type=int, default=0, help="最多执行多少个监测配置，0 表示不限制。")
    parser.add_argument("--start-id", type=int, default=0, help="从指定监测配置 ID 开始。")
    parser.add_argument(
        "--group-all-active",
        action="store_true",
        help="分组搜索阶段覆盖全部 active 监测配置，适用于中断续跑后的完整补数。",
    )
    parser.add_argument(
        "--grouped-channels",
        default="bocha_search,doubao_web_search",
        help="分组补充渠道，逗号分隔；可只指定 doubao_web_search 做故障续跑。",
    )
    parser.add_argument("--days", type=int, default=0, help="覆盖本次采集时间窗，0 表示按监测频率自动计算。")
    parser.add_argument("--start-date", help="精确补采开始日期，格式 YYYY-MM-DD，需与 --end-date 同时使用。")
    parser.add_argument("--end-date", help="精确补采结束日期，格式 YYYY-MM-DD，包含当天。")
    parser.add_argument("--timeout", type=int, default=180, help="单个监测配置超时时间，秒。")
    parser.add_argument("--user-id", type=int, default=settings.INSIGHT_SCHEDULER_USER_ID, help="记录执行人的用户 ID。")
    parser.add_argument("--log-file", default="tmp/insight_run_all_monitor_configs.jsonl", help="进度 JSONL 日志。")
    parser.add_argument("--summary-file", default="tmp/insight_run_all_monitor_configs_summary.json", help="最终汇总 JSON。")
    args = parser.parse_args()

    if bool(args.start_date) != bool(args.end_date):
        parser.error("--start-date 与 --end-date 必须同时提供")
    published_start = datetime.combine(datetime.strptime(args.start_date, "%Y-%m-%d").date(), time.min) if args.start_date else None
    published_end = datetime.combine(datetime.strptime(args.end_date, "%Y-%m-%d").date() + timedelta(days=1), time.min) - timedelta(microseconds=1) if args.end_date else None
    if published_start and published_end and published_start > published_end:
        parser.error("--start-date 不能晚于 --end-date")

    engine.echo = False
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

    log_file = Path(args.log_file)
    summary_file = Path(args.summary_file)
    if log_file.exists() and args.start_id <= 0:
        log_file.unlink()

    async with async_session() as db:
        lock_result = await db.execute(
            text("SELECT pg_try_advisory_lock(:lock_id)"),
            {"lock_id": settings.INSIGHT_SCHEDULER_ADVISORY_LOCK_ID},
        )
        if not bool(lock_result.scalar_one()):
            print("另一个 Insight 调度实例正在执行，本次全量测试已跳过。", flush=True)
            return 2

        started_at = datetime.now()
        exact_days = (published_end.date() - published_start.date()).days + 1 if published_start and published_end else 0
        freshness_override = f"{max(args.days, exact_days + 1, 1)}d" if args.days > 0 or exact_days > 0 else None
        totals = {
            "requested": 0,
            "days": args.days,
            "success": 0,
            "failed": 0,
            "hits": 0,
            "discovered": 0,
            "candidates": 0,
            "history_duplicates": 0,
            "grouped_search_batches": 0,
            "grouped_search_hits": 0,
            "grouped_search_candidates": 0,
        }
        failures: list[dict[str, Any]] = []
        successful_row_ids: list[int] = []

        try:
            filters = [
                InsightMonitorConfig.is_deleted == 0,
                InsightMonitorConfig.status == "active",
            ]
            if args.start_id > 0:
                filters.append(InsightMonitorConfig.id >= args.start_id)
            rows = list(
                (
                    await db.exec(
                        select(InsightMonitorConfig)
                        .where(*filters)
                        .order_by(InsightMonitorConfig.id.asc())
                        .limit(args.limit if args.limit > 0 else None)
                    )
                ).all()
            )
            row_snapshots = [
                {
                    "id": row.id or 0,
                    "config_name": row.config_name,
                    "object_name": row.object_name,
                    "fetch_frequency": row.fetch_frequency,
                }
                for row in rows
            ]
            totals["requested"] = len(row_snapshots)
            print(f"准备执行 {len(row_snapshots)} 个 active 监测配置。", flush=True)

            for index, snapshot in enumerate(row_snapshots, start=1):
                item_started_at = datetime.now()
                row_id = int(snapshot["id"])
                config_name = str(snapshot["config_name"])
                object_name = str(snapshot["object_name"] or "")
                fetch_frequency = str(snapshot["fetch_frequency"] or "")
                row = await db.get(InsightMonitorConfig, row_id)
                if not row or row.is_deleted != 0 or row.status != "active":
                    continue
                row.last_schedule_status = "running"
                row.last_schedule_message = f"全量近 {args.days} 天测试采集中" if args.days > 0 else "全量测试采集中"
                row.last_fetch_time = item_started_at
                row.update_time = item_started_at
                db.add(row)
                await db.commit()

                progress: dict[str, Any] = {
                    "index": index,
                    "total": len(row_snapshots),
                    "monitor_config_id": row_id,
                    "config_name": config_name,
                    "object_name": object_name,
                    "fetch_frequency": fetch_frequency,
                    "freshness_override": freshness_override,
                    "started_at": item_started_at,
                }
                try:
                    result = await asyncio.wait_for(
                        insight_monitor_execution_service.execute_monitor_config(
                            db,
                            row,
                            user_id=args.user_id,
                            include_conditional_discovery=False,
                            freshness_override=freshness_override,
                            published_start=published_start,
                            published_end=published_end,
                        ),
                        timeout=args.timeout,
                    )
                    search_results = result.get("search_results", [])
                    counts = {"hits": 0, "discovered": 0, "candidates": 0, "history_duplicates": 0}
                    channels = []
                    for response in search_results:
                        response_counts = _response_counts(response)
                        counts["hits"] += response_counts["hits"]
                        counts["discovered"] += response_counts["discovered"]
                        counts["candidates"] += response_counts["candidates"]
                        counts["history_duplicates"] += response_counts["history_duplicates"]
                        channels.append(
                            {
                                "task_id": getattr(getattr(response, "task", None), "id", None),
                                "hits": response_counts["hits"],
                                "candidates": response_counts["candidates"],
                                "history_duplicates": response_counts["history_duplicates"],
                                "time_window_kept": response_counts["time_window_kept"],
                                "history_dedupe_kept": response_counts["history_dedupe_kept"],
                            }
                        )

                    row.last_schedule_status = "success"
                    row.last_schedule_message = (
                        f"全量测试完成：发现 {counts['hits']} 条，候选 {counts['candidates']} 条，"
                        f"历史重复跳过 {counts['history_duplicates']} 条"
                    )[:1000]
                    row.last_success_time = datetime.now()
                    row.next_run_time = insight_monitor_execution_service._calculate_next_run_time(  # noqa: SLF001
                        row.fetch_frequency,
                        row.config_json,
                        datetime.now(),
                    )
                    row.consecutive_failure_count = 0
                    row.last_failure_time = None
                    row.auto_paused_reason = None
                    row.update_by = str(args.user_id) if args.user_id else None
                    row.update_time = datetime.now()
                    db.add(row)
                    await db.commit()

                    totals["success"] += 1
                    successful_row_ids.append(row_id)
                    for key in ("hits", "discovered", "candidates", "history_duplicates"):
                        totals[key] += counts[key]
                    progress.update(
                        {
                            "status": "success",
                            "finished_at": datetime.now(),
                            "seconds": round((datetime.now() - item_started_at).total_seconds(), 2),
                            "counts": counts,
                            "channels": channels,
                        }
                    )
                except Exception as exc:
                    await db.rollback()
                    failed_row = await db.get(InsightMonitorConfig, row_id)
                    if failed_row:
                        failed_row.last_schedule_status = "failed"
                        failed_row.last_schedule_message = str(exc)[:1000]
                        failed_row.last_failure_time = datetime.now()
                        failed_row.consecutive_failure_count = (failed_row.consecutive_failure_count or 0) + 1
                        failed_row.update_by = str(args.user_id) if args.user_id else None
                        failed_row.update_time = datetime.now()
                        db.add(failed_row)
                        await db.commit()
                    totals["failed"] += 1
                    failure = {
                        "monitor_config_id": progress["monitor_config_id"],
                        "config_name": progress["config_name"],
                        "error": f"{exc.__class__.__name__}: {str(exc) or '无错误详情'}"[:1000],
                    }
                    failures.append(failure)
                    progress.update(
                        {
                            "status": "failed",
                            "finished_at": datetime.now(),
                            "seconds": round((datetime.now() - item_started_at).total_seconds(), 2),
                            "error": f"{exc.__class__.__name__}: {str(exc) or '无错误详情'}",
                            "traceback": traceback.format_exc(limit=5),
                        }
                    )

                _write_jsonl(log_file, progress)
                print(
                    f"[{index}/{len(row_snapshots)}] {progress['status']} "
                    f"#{progress['monitor_config_id']} {progress['config_name']} "
                    f"{progress.get('counts', {})}",
                    flush=True,
                )

            grouped_row_ids = successful_row_ids
            if args.group_all_active:
                grouped_row_ids = [
                    int(item)
                    for item in (
                        await db.exec(
                            select(InsightMonitorConfig.id).where(
                                InsightMonitorConfig.is_deleted == 0,
                                InsightMonitorConfig.status == "active",
                            )
                        )
                    ).all()
                    if item
                ]
            print(
                f"开始对 {len(grouped_row_ids)} 个监测对象执行博查、豆包分组补充。",
                flush=True,
            )
            grouped_summary = await insight_monitor_execution_service._execute_grouped_daily_discovery(  # noqa: SLF001
                db,
                grouped_row_ids,
                user_id=args.user_id,
                freshness_override=freshness_override,
                channel_codes={item.strip() for item in args.grouped_channels.split(",") if item.strip()},
                published_start=published_start,
                published_end=published_end,
            )
            grouped_batches = grouped_summary.get("batches", [])
            totals["grouped_search_batches"] = len(grouped_batches)
            totals["grouped_search_hits"] = sum(int(item.get("hits") or 0) for item in grouped_batches)
            totals["grouped_search_candidates"] = sum(
                int(item.get("candidates") or 0) for item in grouped_batches
            )
            totals["hits"] += totals["grouped_search_hits"]
            totals["candidates"] += totals["grouped_search_candidates"]
            _write_jsonl(
                log_file,
                {
                    "stage": "grouped_discovery",
                    "finished_at": datetime.now(),
                    "successful_monitor_count": len(successful_row_ids),
                    "grouped_monitor_count": len(grouped_row_ids),
                    "summary": grouped_summary,
                },
            )
            print(
                "分组补充完成："
                f"批次 {totals['grouped_search_batches']}，"
                f"命中 {totals['grouped_search_hits']}，"
                f"候选 {totals['grouped_search_candidates']}。",
                flush=True,
            )

            summary = {
                "started_at": started_at,
                "finished_at": datetime.now(),
                "seconds": round((datetime.now() - started_at).total_seconds(), 2),
                "freshness_override": freshness_override,
                "published_start": published_start,
                "published_end": published_end,
                "totals": totals,
                "failures": failures[:100],
                "log_file": str(log_file),
            }
            summary_file.parent.mkdir(parents=True, exist_ok=True)
            summary_file.write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8")
            print(json.dumps(summary, ensure_ascii=False, default=_json_default), flush=True)
            return 0 if totals["failed"] == 0 else 1
        finally:
            try:
                await db.execute(
                    text("SELECT pg_advisory_unlock(:lock_id)"),
                    {"lock_id": settings.INSIGHT_SCHEDULER_ADVISORY_LOCK_ID},
                )
                await db.commit()
            except Exception:
                await db.rollback()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
