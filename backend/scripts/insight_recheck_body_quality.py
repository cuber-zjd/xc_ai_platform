"""固定补抓清单的全量重洗与质量复核；不删除、不生成报告、不对外同步。"""

import argparse
import asyncio
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlmodel import select  # noqa: E402
from app.db.session import async_session  # noqa: E402
from app.models.agent.insight import InsightTask, InsightTaskStatus, InsightCrawlResult, InsightIntelligence  # noqa: E402
from app.services.agent.insight.crawler.body_quality import assess_body  # noqa: E402
from app.services.agent.insight.crawler.firecrawl_client import firecrawl_client  # noqa: E402


async def run(task_id: int, apply: bool, refresh_flagged: bool = False) -> dict:
    async with async_session() as db:
        source = await db.get(InsightTask, task_id)
        if not source or source.task_type != "fulltext_retry":
            raise ValueError("必须指定真实正文补抓任务")
        ids = list(dict.fromkeys((source.input_payload or {}).get("selected_ids", [])))
    items = []
    for number in ids:
        async with async_session() as db:
            row = (await db.exec(select(InsightCrawlResult).where(InsightCrawlResult.id == number).with_for_update())).first()
            if not row or row.is_deleted or not row.markdown_content:
                items.append({"id": number, "status": "no_body"})
                continue
            original = row.markdown_content
            cleaned, quality = assess_body(original, row.source_title or "")
            refresh_error = None
            if refresh_flagged and quality["status"] == "needs_review" and quality["kind"] == "article":
                # 不在网络等待期间持有行锁；写入前再次锁定并比较原文，避免覆盖并发修改。
                url, title = row.source_url, row.source_title
                await db.commit()
                try:
                    fetched = await asyncio.wait_for(firecrawl_client.scrape_url_with_fallback(url), 90)
                    candidate, candidate_quality = assess_body(str(fetched.get("markdown") or ""), title or "")
                    if candidate_quality["status"] == "passed_rules":
                        cleaned, quality = candidate, candidate_quality
                        quality["reextracted_from_url"] = url
                except Exception as exc:
                    refresh_error = f"{type(exc).__name__}: {exc}"[:300]
                row = (await db.exec(select(InsightCrawlResult).where(InsightCrawlResult.id == number)
                                     .with_for_update().execution_options(populate_existing=True))).first()
                if row.markdown_content != original:
                    items.append({"id": number, "status": "conflict_preserved"})
                    continue
            item = {"id": number, "status": quality["status"], "kind": quality["kind"],
                    "issues": quality["issues"], "changed": cleaned != original,
                    "before": len(original), "after": len(cleaned), "formal_updated": []}
            item["refresh_error"] = refresh_error
            if apply:
                metadata = dict(row.crawl_metadata or {})
                metadata.setdefault("body_quality_original", original)
                metadata["body_quality"] = quality
                row.crawl_metadata = metadata
                # 无法判定质量时保留原文，候选清洗文本供复核，不用清空冒充修复。
                metadata["body_quality_candidate"] = cleaned
                if quality["status"] == "passed_rules" and cleaned:
                    row.markdown_content = cleaned
                row.update_time = datetime.now()
                db.add(row)
                formal = list((await db.exec(select(InsightIntelligence).where(
                    InsightIntelligence.is_deleted == 0,
                    InsightIntelligence.raw_payload["crawl_result_id"].astext == str(number),
                ).with_for_update())).all())
                for intelligence in formal:
                    payload = dict(intelligence.raw_payload or {})
                    payload["body_quality"] = {key: value for key, value in quality.items() if key != "removed"}
                    intelligence.raw_payload = payload
                    # 不覆盖人工修改，也不在本次触发资产模型或发布流程。
                    db.add(intelligence)
                await db.commit()
            items.append(item)
    result = {"source_task": task_id, "apply": apply, "total": len(ids),
              "statuses": dict(Counter(x["status"] for x in items)),
              "changed_candidates": sum(bool(x.get("changed")) for x in items), "items": items,
              "deleted": 0, "reports": 0, "notifications": 0}
    if apply:
        async with async_session() as db:
            audit = InsightTask(task_uid=f"body_quality_{uuid4().hex}", task_type="body_quality_recheck",
                                status=InsightTaskStatus.SUCCESS, progress=100,
                                started_at=datetime.now(), finished_at=datetime.now(), output_payload=result)
            db.add(audit)
            await db.commit()
            await db.refresh(audit)
            result["audit_id"] = audit.id
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-task", required=True, type=int)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--refresh-flagged", action="store_true")
    args = parser.parse_args()
    sys.stdout.write(json.dumps(asyncio.run(run(args.source_task, args.apply, args.refresh_flagged)), ensure_ascii=False) + "\n")
