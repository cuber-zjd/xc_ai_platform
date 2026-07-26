import argparse
import asyncio
import json
import logging
from datetime import datetime
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
    parser = argparse.ArgumentParser(description="按生产调度策略执行一批到期 Insight 监测配置。")
    parser.add_argument("--limit", type=int, default=settings.INSIGHT_SCHEDULER_BATCH_LIMIT)
    parser.add_argument("--days", type=int, default=0, help="覆盖本次采集时间窗，0 表示按监测频率自动计算。")
    parser.add_argument("--user-id", type=int, default=settings.INSIGHT_SCHEDULER_USER_ID)
    parser.add_argument("--summary-file", default="tmp/insight_run_due_monitor_configs_summary.json")
    args = parser.parse_args()

    engine.echo = False
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    freshness_override = f"{max(args.days, 1)}d" if args.days > 0 else None
    started_at = datetime.now()

    async with async_session() as db:
        lock_result = await db.execute(
            text("SELECT pg_try_advisory_lock(:lock_id)"),
            {"lock_id": settings.INSIGHT_SCHEDULER_ADVISORY_LOCK_ID},
        )
        if not bool(lock_result.scalar_one()):
            print("另一个 Insight 调度实例正在执行，本次到期采集已跳过。", flush=True)
            return 2
        try:
            result = await insight_monitor_execution_service.run_due_monitor_configs(
                db,
                limit=args.limit,
                user_id=args.user_id,
                freshness_override=freshness_override,
            )
            payload = {
                "started_at": started_at,
                "finished_at": datetime.now(),
                "seconds": round((datetime.now() - started_at).total_seconds(), 2),
                "limit": args.limit,
                "days": args.days,
                "freshness_override": freshness_override,
                "result": result.model_dump(mode="json"),
            }
            summary_path = Path(args.summary_file)
            summary_path.parent.mkdir(parents=True, exist_ok=True)
            summary_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8")
            print(json.dumps(payload, ensure_ascii=False, default=_json_default), flush=True)
            return 0 if result.failed_count == 0 else 1
        finally:
            await db.execute(
                text("SELECT pg_advisory_unlock(:lock_id)"),
                {"lock_id": settings.INSIGHT_SCHEDULER_ADVISORY_LOCK_ID},
            )
            await db.commit()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
