"""正文补偿队列：固定清单、逐条限时、独立事务和持续审计。"""

import asyncio
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta
from uuid import uuid4
from urllib.parse import urlparse

from sqlalchemy import and_, or_, text
from sqlmodel import func, select

from app.core.config import settings
from app.db.session import async_session, engine
from app.models.agent.insight import InsightCrawlResult, InsightTask, InsightTaskStatus
from app.services.agent.insight.crawler.firecrawl_client import firecrawl_client


class FulltextRetryService:
    async def run(self, db, *, user_id, limit=20, days=7, repair=False, budget_seconds=None):
        # 手工验收与每日调度共用锁，防止相同记录同时评审或重复调用供应商。
        async with engine.connect() as connection:
            acquired = (await connection.execute(text("SELECT pg_try_advisory_lock(746321909)"))).scalar()
            await connection.commit()
            if not acquired:
                return {"attempted": 0, "success": 0, "failed": 0, "locked": True}
            try:
                return await self._run(db, user_id=user_id, limit=limit, days=days,
                                       repair=repair, budget_seconds=budget_seconds)
            finally:
                await connection.execute(text("SELECT pg_advisory_unlock(746321909)"))
                await connection.commit()

    async def _run(self, db, *, user_id, limit, days, repair, budget_seconds):
        from app.services.agent.insight.crawler.search_service import insight_search_discovery_service as search

        now = datetime.now()
        rows = list((await db.exec(select(InsightCrawlResult).where(
            InsightCrawlResult.is_deleted == 0,
            InsightCrawlResult.create_time >= now - timedelta(days=days),
            InsightCrawlResult.create_time <= now,
            or_(func.length(func.coalesce(InsightCrawlResult.markdown_content, "")) < 200,
                InsightCrawlResult.crawl_metadata["fulltext_retry"]["status"].astext.in_(["review_pending", "running"]),
                and_(repair, InsightCrawlResult.source_url.like("%toutiao.com/%"),
                     InsightCrawlResult.crawl_metadata["fulltext_fetch"]["metadata"]["body_selector"].astext.is_(None))),
        ).order_by(InsightCrawlResult.create_time.asc(), InsightCrawlResult.id.asc()))).all())
        ids, excluded = [], []
        blocked_hosts = set()
        # 从已落盘的限制原因恢复本轮冷却，维护重启不能立即重试刚被拒绝的站点。
        for row in rows:
            fetch = (row.crawl_metadata or {}).get("fulltext_fetch") or {}
            try:
                recently_blocked = ("FulltextAccessBlocked" in str(fetch.get("error") or "")
                                    and datetime.fromisoformat(fetch.get("attempted_at") or "") > now - timedelta(hours=1))
            except (TypeError, ValueError):
                recently_blocked = False
            if recently_blocked:
                try:
                    blocked_url = firecrawl_client.canonical_article_url(row.source_url)
                except ValueError:
                    blocked_url = row.source_url
                blocked_hosts.add(urlparse(blocked_url).hostname or "")
        for row in rows:
            metadata = row.crawl_metadata or {}
            retry = metadata.get("fulltext_retry") or {}
            fetch = metadata.get("fulltext_fetch") or {}
            reason = search._unsupported_fulltext_reason(row.source_url)
            if not repair and not reason:
                previous = retry.get("attempted_at") or fetch.get("attempted_at")
                try:
                    recent = previous and datetime.fromisoformat(previous) > now - timedelta(hours=6)
                except (TypeError, ValueError):
                    recent = False
                if int(retry.get("attempts") or 0) >= 2 and retry.get("status") != "running":
                    reason = "已达自动重试上限"
                elif recent:
                    reason = "重试冷却中"
            if reason:
                excluded.append({"id": row.id, "reason": reason})
            else:
                ids.append(row.id)
        selected = ids[:limit] if limit else ids
        manifest = {
            "date_from": (now - timedelta(days=days)).isoformat(), "date_to": now.isoformat(),
            "selected_ids": selected, "excluded": excluded, "beyond_limit_ids": ids[len(selected):],
            "repair": repair, "user_id": user_id,
        }
        task = InsightTask(task_uid=f"fulltext_retry_{uuid4().hex}", task_type="fulltext_retry",
                           status=InsightTaskStatus.RUNNING, started_at=now, input_payload=manifest)
        db.add(task)
        await db.commit()
        await db.refresh(task)
        task_id = task.id
        # refresh 会重新开启只读事务，必须在长批次之前释放，避免挡住发布时的 DDL。
        await db.commit()
        outcomes = []
        started = time.monotonic()
        budget = settings.INSIGHT_FULLTEXT_RETRY_BUDGET_SECONDS if budget_seconds is None else budget_seconds
        queue = asyncio.Queue()
        domains = defaultdict(deque)
        urls = {row.id: row.source_url for row in rows}
        for number in selected:
            try:
                url = firecrawl_client.canonical_article_url(urls[number])
            except ValueError:
                url = urls[number]
            domains[urlparse(url).hostname or ""].append(number)
        for host in domains:
            queue.put_nowait(host)
        journal_lock = asyncio.Lock()

        def totals():
            return {
                "task_id": task_id, "selected": len(selected), "excluded": len(excluded),
                "attempted": sum(item["attempted"] for item in outcomes),
                "success": sum(item["status"] == "success" for item in outcomes),
                "failed": sum(item["status"] == "failed" for item in outcomes),
                "review_pending": sum(item["status"] == "review_pending" for item in outcomes),
                "deferred": sum(item["status"] == "deferred" for item in outcomes),
                "body_available": sum(item.get("body_available", False) for item in outcomes),
                "remaining": len(selected) - len(outcomes),
                "candidates": sum(item.get("candidates", 0) for item in outcomes),
                "elapsed_seconds": round(time.monotonic() - started, 2),
            }

        async def worker():
            while not queue.empty():
                host = queue.get_nowait()
                number = domains[host].popleft()
                outcome = {"id": number, "attempted": 0, "status": "deferred"}
                if budget and time.monotonic() - started >= budget:
                    outcome["error"] = "批次预算已用完，未发起请求，留待下一轮"
                elif host in blocked_hosts or firecrawl_client.host_is_blocked(host):
                    outcome["error"] = "同站已触发访问限制，本轮不再请求"
                else:
                    async with async_session() as item_db:
                        try:
                            counts = await search._retry_fulltext_records(
                                item_db, user_id=user_id, limit=1, result_ids=[number], repair=repair,
                                force_fetch=repair and host == "www.toutiao.com",
                            )
                            row = await item_db.get(InsightCrawlResult, number, populate_existing=True)
                            metadata = row.crawl_metadata or {}
                            retry = metadata.get("fulltext_retry") or {}
                            outcome.update(attempted=counts["attempted"], candidates=counts["candidates"],
                                           body_available=search._has_fulltext(row),
                                           status=retry.get("status", "deferred"),
                                           error=retry.get("review_error") or row.error_message,
                                           provider=(metadata.get("fulltext_fetch") or {}).get("provider"))
                        except Exception as exc:
                            await item_db.rollback()
                            outcome.update(status="failed", error=f"{type(exc).__name__}: {exc}"[:500])
                # 进度落库不与正文事务共享；崩溃后仍可查到已完成项及固定清单。
                async with journal_lock:
                    outcomes.append(outcome)
                    async with async_session() as audit_db:
                        audit = await audit_db.get(InsightTask, task_id)
                        audit.output_payload = {**totals(), "items": list(outcomes)}
                        audit.progress = int(100 * len(outcomes) / max(len(selected), 1))
                        audit_db.add(audit)
                        await audit_db.commit()
                if domains[host]:
                    queue.put_nowait(host)

        workers = [asyncio.create_task(worker()) for _ in range(max(1, min(6, settings.INSIGHT_FULLTEXT_RETRY_CONCURRENCY)))]
        try:
            await asyncio.gather(*workers)
        finally:
            for item in workers:
                if not item.done():
                    item.cancel()
            await asyncio.gather(*workers, return_exceptions=True)
            async with async_session() as audit_db:
                audit = await audit_db.get(InsightTask, task_id)
                result = totals()
                audit.output_payload = {**result, "items": outcomes}
                audit.finished_at = datetime.now()
                audit.status = (InsightTaskStatus.FAILED if result["failed"] or result["review_pending"]
                                or result["remaining"] else InsightTaskStatus.SUCCESS)
                audit.progress = int(100 * len(outcomes) / max(len(selected), 1))
                audit_db.add(audit)
                await audit_db.commit()
        return totals()


fulltext_retry_service = FulltextRetryService()
