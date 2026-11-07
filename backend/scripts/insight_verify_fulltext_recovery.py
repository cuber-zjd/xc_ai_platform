"""近七天正文完整批次验收；不运行报告生成、订阅或消息发送。"""

import argparse
import asyncio
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import String, text  # noqa: E402
from sqlmodel import select  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.db.session import async_session  # noqa: E402
from app.models.agent.insight import InsightCrawlResult, InsightIntelligence, InsightTask, InsightTaskStatus  # noqa: E402
from app.services.agent.insight.crawler.crawl_service import insight_crawl_service  # noqa: E402
from app.services.agent.insight.crawler.fulltext_retry_service import fulltext_retry_service  # noqa: E402
from app.services.agent.insight.feishu_bitable_service import insight_feishu_bitable_service as bitable  # noqa: E402


def emit(value):
    sys.stdout.write(json.dumps(value, ensure_ascii=False, default=str) + "\n")
    sys.stdout.flush()


async def snapshot(days):
    async with async_session() as db:
        rows = (await db.exec(text("""
            SELECT channel, substring(source_url from 'https?://([^/]+)') AS host,
                   count(*) AS total,
                   count(*) FILTER (WHERE length(coalesce(markdown_content,'')) >= 200) AS body_available,
                   count(*) FILTER (WHERE crawl_metadata->'fulltext_fetch'->>'status'='failed') AS failed
            FROM insight_crawl_result
            WHERE is_deleted=0 AND create_time>=:since
            GROUP BY channel,host ORDER BY total DESC
        """).bindparams(since=datetime.now()-timedelta(days=days)))).mappings().all()
        return [dict(row) for row in rows]


async def verify_feishu():
    records = await bitable._list_records()
    remote = {}
    for record in records:
        fields = record.get("fields") or {}
        key = bitable._normalize_text_value(fields.get("情报ID"))
        remote.setdefault(key, []).append(bitable._normalize_text_value(fields.get("正文")))
    async with async_session() as db:
        rows = list((await db.exec(select(InsightIntelligence).where(
            InsightIntelligence.is_deleted == 0, InsightIntelligence.status == "active",
        ))).all())
    missing, different, matched, local_empty = [], [], 0, 0
    for row in rows:
        content = (row.content or "").strip()
        if not content:
            local_empty += 1
            continue
        actual = remote.get(str(row.id))
        if not actual:
            missing.append(row.id)
        elif any(value != content for value in actual):
            different.append(row.id)
        else:
            matched += 1
    return {"active_intelligences": len(rows), "remote_records": len(records), "matched_body": matched,
            "local_empty_body": local_empty, "missing_ids": missing, "different_body_ids": different,
            "duplicate_ids": [key for key, values in remote.items() if len(values) > 1]}


async def run(args):
    result = {"before": await snapshot(args.days)}
    emit(result)
    if args.repair:
        async with async_session() as db:
            result["retry"] = await fulltext_retry_service.run(
                db, user_id=settings.INSIGHT_SCHEDULER_USER_ID, limit=0,
                days=args.days, repair=True, budget_seconds=0,
            )
        emit({"retry": result["retry"]})
    result["after"] = await snapshot(args.days)
    if args.backfill_formal:
        async with async_session() as db:
            ids = list((await db.exec(select(InsightCrawlResult.id).join(
                InsightIntelligence,
                InsightIntelligence.raw_payload["crawl_result_id"].astext == InsightCrawlResult.id.cast(String),
            ).where(InsightIntelligence.is_deleted == 0, InsightIntelligence.status == "active",
                    (InsightIntelligence.content.is_(None)) | (InsightIntelligence.content == ""),
                    InsightCrawlResult.markdown_content.is_not(None),
                    InsightCrawlResult.is_deleted == 0))).all())
        restored, errors = [], []
        for number in dict.fromkeys(ids):
            async with async_session() as db:
                try:
                    crawl = await db.get(InsightCrawlResult, number)
                    restored.extend(await asyncio.wait_for(insight_crawl_service.backfill_promoted_fulltext(db, crawl), 120))
                except Exception as exc:
                    await db.rollback()
                    errors.append({"crawl_result_id": number, "error": f"{type(exc).__name__}: {exc}"[:300]})
        result["formal_backfill"] = {"restored_ids": restored, "errors": errors}
        emit({"formal_backfill": result["formal_backfill"]})
    if args.sync:
        async with async_session() as db:
            response = await bitable.sync_incremental(db, user_id=settings.INSIGHT_SCHEDULER_USER_ID)
            result["sync"] = response.model_dump(mode="json")
        emit({"sync": result["sync"]})
    if args.verify_feishu or args.sync:
        result["feishu_readback"] = await verify_feishu()
        emit({"feishu_readback": result["feishu_readback"]})
    if args.repair or args.sync or args.backfill_formal:
        async with async_session() as db:
            audit = InsightTask(task_uid=f"fulltext_verify_{uuid4().hex}", task_type="fulltext_validation",
                                status=InsightTaskStatus.SUCCESS, started_at=datetime.now(),
                                finished_at=datetime.now(), progress=100,
                                input_payload=vars(args), output_payload=result)
            check = result.get("feishu_readback", {})
            retry = result.get("retry", {})
            if (check.get("missing_ids") or check.get("different_body_ids") or retry.get("failed")
                    or retry.get("remaining") or retry.get("review_pending") or retry.get("locked") or retry.get("deferred")
                    or result.get("sync", {}).get("failed_count") or result.get("formal_backfill", {}).get("errors")):
                audit.status = InsightTaskStatus.FAILED
            db.add(audit)
            await db.commit()
            await db.refresh(audit)
            emit({"validation_task_id": audit.id, "status": audit.status, "result": result})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, choices=range(1, 32), default=7)
    parser.add_argument("--repair", action="store_true", help="对固定清单逐条执行，显式放开旧重试次数限制一次")
    parser.add_argument("--sync", action="store_true")
    parser.add_argument("--backfill-formal", action="store_true", help="仅将同一原始证据的有效正文回填空正文，并更新资产索引")
    parser.add_argument("--verify-feishu", action="store_true")
    asyncio.run(run(parser.parse_args()))
