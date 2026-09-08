"""持久化分组搜索结果，正文处理失败后续跑时复用已付费搜索。"""

import hashlib
import json
from dataclasses import asdict
from datetime import datetime

from sqlmodel import select

from app.db.session import async_session
from app.models.agent.insight import InsightCrawlerChannel, InsightTask, InsightTaskStatus
from app.services.agent.insight.crawler.search_client import InsightSearchHit


async def checkpointed_search(key: str, search):
    uid = "discovery_" + hashlib.sha256(key.encode()).hexdigest()[:48]
    async with async_session() as db:
        task = (await db.exec(select(InsightTask).where(InsightTask.task_uid == uid))).first()
        if task and task.status == InsightTaskStatus.SUCCESS:
            payload = task.output_payload or {}
            hits = []
            for item in payload.get("hits", []):
                data = dict(item)
                data["channel"] = InsightCrawlerChannel(data["channel"])
                data["published_at"] = datetime.fromisoformat(data["published_at"]) if data.get("published_at") else None
                hits.append(InsightSearchHit(**data))
            return hits, {**payload.get("search_meta", {}), "checkpoint_reused": True}
        if task is None:
            task = InsightTask(task_uid=uid, task_type="discovery_checkpoint", input_payload={"key": key})
        task.status = InsightTaskStatus.RUNNING
        task.started_at = datetime.now()
        task.finished_at = None
        db.add(task)
        await db.commit()
        try:
            hits, meta = await search()
            task.output_payload = json.loads(json.dumps({"hits": [asdict(hit) for hit in hits], "search_meta": meta}, default=str))
            task.status = InsightTaskStatus.SUCCESS
            task.error_message = None
            task.finished_at = datetime.now()
            db.add(task)
            await db.commit()
            return hits, meta
        except Exception as exc:
            task.status = InsightTaskStatus.FAILED
            task.error_message = str(exc)[:1000]
            task.finished_at = datetime.now()
            db.add(task)
            await db.commit()
            raise
