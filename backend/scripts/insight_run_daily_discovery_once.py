import argparse
import asyncio
import json
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import text

from app.core.config import settings
from app.db.session import async_session, engine
from app.services.agent.insight.monitor_execution_service import insight_monitor_execution_service


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


async def main() -> int:
    parser = argparse.ArgumentParser(description="按生产每日发现策略立即执行一次 Insight 补采。")
    parser.add_argument("--start-date", required=True, help="开始日期，格式 YYYY-MM-DD。")
    parser.add_argument("--end-date", required=True, help="结束日期，格式 YYYY-MM-DD，包含当天。")
    parser.add_argument("--user-id", type=int, default=settings.INSIGHT_SCHEDULER_USER_ID)
    parser.add_argument("--summary-file", default="tmp/insight_daily_discovery_summary.json")
    args = parser.parse_args()

    start_date = datetime.strptime(args.start_date, "%Y-%m-%d").date()
    end_date = datetime.strptime(args.end_date, "%Y-%m-%d").date()
    if start_date > end_date:
        parser.error("--start-date 不能晚于 --end-date")
    published_start = datetime.combine(start_date, time.min)
    published_end = datetime.combine(end_date + timedelta(days=1), time.min) - timedelta(microseconds=1)
    freshness = f"{max((datetime.now().date() - start_date).days + 1, 1)}d"

    engine.echo = False
    async with async_session() as db:
        lock_result = await db.execute(
            text("SELECT pg_try_advisory_lock(:lock_id)"),
            {"lock_id": settings.INSIGHT_SCHEDULER_ADVISORY_LOCK_ID},
        )
        if not bool(lock_result.scalar_one()):
            print("另一个 Insight 调度实例正在执行，本次每日策略补采已跳过。", flush=True)
            return 2
        started_at = datetime.now()
        try:
            result = await insight_monitor_execution_service.run_daily_discovery_all(
                db,
                user_id=args.user_id,
                freshness_override=freshness,
                published_start=published_start,
                published_end=published_end,
            )
            summary = {
                "started_at": started_at,
                "finished_at": datetime.now(),
                "seconds": round((datetime.now() - started_at).total_seconds(), 2),
                "published_start": published_start,
                "published_end": published_end,
                "freshness": freshness,
                **result,
            }
            path = Path(args.summary_file)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(summary, ensure_ascii=False, indent=2, default=_json_default),
                encoding="utf-8",
            )
            print(json.dumps(summary, ensure_ascii=False, default=_json_default), flush=True)
            return 0 if not result.get("errors") else 1
        finally:
            await db.execute(
                text("SELECT pg_advisory_unlock(:lock_id)"),
                {"lock_id": settings.INSIGHT_SCHEDULER_ADVISORY_LOCK_ID},
            )
            await db.commit()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
