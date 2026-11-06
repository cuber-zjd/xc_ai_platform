"""回放已付费搜索并核查漏项；默认只读，显式参数才补录、重试正文或同步飞书，不生成/推送报告。"""

import argparse
import asyncio
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlmodel import select  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.db.session import async_session  # noqa: E402
from app.models.agent.insight import (  # noqa: E402
    InsightChannel, InsightCompany, InsightCrawlerChannel, InsightCrawlResult,
    InsightMonitorConfig, InsightTask, InsightTaskStatus,
)
from app.schemas.agent.insight.crawl import InsightSearchDiscoveryRequest  # noqa: E402
from app.services.agent.insight.crawler.search_client import InsightSearchHit  # noqa: E402
from app.services.agent.insight.crawler.search_service import insight_search_discovery_service as search  # noqa: E402
from app.services.agent.insight.feishu_bitable_service import insight_feishu_bitable_service as bitable  # noqa: E402
from app.services.agent.insight.monitor_execution_service import InsightMonitorExecutionService  # noqa: E402


def emit(value):
    sys.stdout.write(json.dumps(value, ensure_ascii=False, default=str) + "\n")
    sys.stdout.flush()


def checkpoint_parts(key):
    parts = key.split("|", 6)
    if len(parts) == 6:
        parts.insert(2, "legacy")
    return parts if len(parts) == 7 else None


def replay_window(parts, created_at):
    end = datetime.fromisoformat(parts[5]) if parts[5] != "None" else created_at
    now = datetime.now()
    cutoff = search._freshness_cutoff(parts[3])
    start = datetime.fromisoformat(parts[4]) if parts[4] != "None" else (
        created_at - (now-cutoff) if cutoff else None
    )
    return start, end


def hit_in_window(hit, parts, created_at):
    start, end = replay_window(parts, created_at)
    return bool(hit.published_at and start and start <= hit.published_at <= end)


async def run(args):
    service = InsightMonitorExecutionService()
    cutoff = datetime.now() - timedelta(days=args.days)
    user_id = settings.INSIGHT_SCHEDULER_USER_ID
    async with async_session() as db:
        companies = list((await db.exec(select(InsightCompany).where(InsightCompany.is_deleted == 0))).all())
        rows = list((await db.exec(select(InsightMonitorConfig).where(
            InsightMonitorConfig.is_deleted == 0, InsightMonitorConfig.status == "active",
        ).order_by(InsightMonitorConfig.id))).all())
        company_by_id = {row.id: row for row in companies}
        # 不能深拷贝 ORM 内部状态；重建纯字段实例，避免历史基线赋值引用已释放对象。
        baseline_companies = {key: InsightCompany.model_validate(value.model_dump()) for key, value in company_by_id.items()}
        if args.baseline_alias_task:
            baseline_task = await db.get(InsightTask, args.baseline_alias_task)
            if not baseline_task or baseline_task.task_type != "collection_alias_repair":
                raise ValueError("别名基线必须指定真实的别名修复审计任务")
            for change in (baseline_task.output_payload or {}).get("changes", []):
                company = baseline_companies.get(change["company_id"])
                if company:
                    company.profile_json = dict(company.profile_json or {}) | {"aliases": change["before"]}
        before = {row.id: service._with_company_aliases(row, baseline_companies.get(row.object_id)
                  if row.object_type == "company" else None) for row in rows}
        if not args.apply_aliases:
            for company in companies:
                db.expunge(company)
        changes = []
        for declaration in args.company_alias:
            name, separator, alias = declaration.partition("=")
            if not separator or len(alias.strip()) < 2:
                raise ValueError("别名必须使用 企业全称=明确简称 格式")
            matches = [company for company in companies if company.name == name]
            if not matches:
                raise ValueError(f"未找到精确公司名：{name}")
            for company in matches:
                profile = dict(company.profile_json or {})
                old = profile.get("aliases") or []
                old = [old] if isinstance(old, str) else list(old)
                new = list(dict.fromkeys([*old, alias.strip()]))
                if new == old:
                    continue
                changes.append({"company_id": company.id, "name": name, "before": old, "after": new})
                company.profile_json = profile | {"aliases": new}
                if args.apply_aliases:
                    company.update_time = datetime.now()
                    db.add(company)
        if args.apply_aliases and changes:
            db.add(InsightTask(task_uid=f"alias_repair_{uuid4().hex}", task_type="collection_alias_repair",
                   status=InsightTaskStatus.SUCCESS, progress=100, started_at=datetime.now(), finished_at=datetime.now(),
                   input_payload={"user_id": user_id}, output_payload={"changes": changes}, create_by=str(user_id)))
            await db.commit()
        enriched = [service._with_company_aliases(row, company_by_id.get(row.object_id)
                    if row.object_type == "company" else None) for row in rows]
        batches = {}
        for size in {max(2, settings.INSIGHT_SCHEDULER_GROUPED_BATCH_SIZE),
                     max(1, settings.INSIGHT_SCHEDULER_GROUPED_AI_BATCH_SIZE)}:
            batches.update({batch.query: batch.rows for batch in service._build_grouped_discovery_batches(enriched, batch_size=size)})
        for row in enriched:
            previous = before[row.id]
            topic = str((row.enabled_modules or [""])[0])
            names = [(candidate.config_json or {}).get("aliases", [None])[0]
                     if (candidate.config_json or {}).get("aliases") else candidate.object_name or candidate.config_name
                     for candidate in (previous, row)]
            for name in names:
                query = f"{name} {topic}".strip()
                group = batches.setdefault(query, [])
                if all(item.id != row.id for item in group):
                    group.append(row)
        checkpoints = list((await db.exec(select(InsightTask).where(
            InsightTask.task_type == "discovery_checkpoint", InsightTask.status == InsightTaskStatus.SUCCESS,
            InsightTask.create_time >= cutoff,
        ).order_by(InsightTask.id.desc()))).all())
        channels = {row.channel_code: row for row in (await db.exec(select(InsightChannel))).all()}
        captured = set((await db.exec(select(InsightCrawlResult.source_url).where(InsightCrawlResult.is_deleted == 0))).all())
        recovered = {}
        scanned = unmatched_queries = 0
        for task in checkpoints:
            parts = checkpoint_parts(str((task.input_payload or {}).get("key") or ""))
            if not parts or parts[6] not in batches:
                unmatched_queries += 1
                continue
            group = batches[parts[6]]
            for raw in (task.output_payload or {}).get("hits", []):
                scanned += 1
                data = dict(raw)
                data["channel"] = InsightCrawlerChannel(data["channel"])
                data["published_at"] = datetime.fromisoformat(data["published_at"]) if data.get("published_at") else None
                hit = InsightSearchHit(**data)
                text = service._normalize_match_text(f"{hit.title}\n{hit.snippet or ''}\n{hit.url}")
                old_match = False
                for row in group:
                    previous = before[row.id]
                    terms = [previous.object_name, previous.config_name, *(previous.keywords or []),
                             *((previous.config_json or {}).get("aliases") or [])]
                    if previous.object_type != "company":
                        terms += previous.enabled_modules or []
                    old_match |= any(service._term_matches(term, text) for term in terms if term and len(term) >= 2)
                if old_match:
                    continue
                assigned = service._assign_grouped_hits(group, [hit])
                previous_hit = recovered.get(hit.url)
                if assigned and (previous_hit is None or (
                    hit_in_window(hit, parts, task.create_time)
                    and not hit_in_window(previous_hit[1], previous_hit[2], previous_hit[3])
                )):
                    row, _ = next(iter(assigned.values()))
                    recovered[hit.url] = (row, hit, parts, task.create_time, task.id)
        emit({"alias_changes": changes, "aliases_applied": args.apply_aliases,
              "checkpoint_count": len(checkpoints), "scanned_hits": scanned, "unmatched_checkpoint_queries": unmatched_queries,
              "newly_matched_unique_urls": len(recovered),
              "items": [{"title": hit.title, "url": hit.url, "monitor_id": row.id,
                         "published_at": hit.published_at, "already_captured": hit.url in captured,
                         "checkpoint_id": checkpoint_id}
                        for row, hit, _, _, checkpoint_id in recovered.values()]})
        # 未应用的别名仅作只读模拟，禁止用模拟配置补录。
        if changes and not args.apply_aliases and args.replay_limit:
            raise ValueError("补录前需显式应用已核实别名；当前仅展示模拟结果")
        pending = [value for url, value in recovered.items() if url not in captured][:args.replay_limit]
    for row, hit, parts, created_at, checkpoint_id in pending:
        channel = channels["bocha_search" if parts[1] == "bocha" else parts[1]]
        period_start, period_end = replay_window(parts, created_at)
        if period_start is None:
            emit({"skipped_checkpoint": checkpoint_id, "reason": "无法精确恢复原时间窗，未补录"})
            continue
        request = InsightSearchDiscoveryRequest(
            query=parts[6], channels=[parts[1]], freshness="noLimit", published_start=period_start,
            published_end=period_end, monitor_config_id=row.id, source_channel_id=channel.id,
            max_results=1, crawl_top_n=0, enrich_fulltext_before_review=True, fulltext_top_n=1,
            filter_prompt=service._filter_prompt(row, channel), enable_llm_filter=True, llm_min_score=0.45,
            exclude_keywords=row.excluded_keywords or [], create_candidate_from_hits=True, run_type="backfill",
        )
        async with async_session() as db:
            try:
                response = await asyncio.wait_for(search.ingest_search_hits(db, request, [hit], user_id, is_admin=True), timeout=240)
                emit({"replayed_checkpoint": checkpoint_id, "task_id": response.task.id, "title": hit.title,
                      "result": response.task.output_payload})
            except Exception as exc:
                emit({"replayed_checkpoint": checkpoint_id, "title": hit.title, "error": f"{type(exc).__name__}: {exc}"[:800]})
    if args.retry_fulltext_limit:
        async with async_session() as db:
            emit({"fulltext_retry": await asyncio.wait_for(search.retry_recent_fulltext(
                db, user_id=user_id, limit=args.retry_fulltext_limit), timeout=300)})
    if args.sync:
        async with async_session() as db:
            emit({"feishu_sync": (await bitable.sync_incremental(db, user_id=user_id)).model_dump(mode="json")})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, choices=range(1, 32), default=7)
    parser.add_argument("--company-alias", action="append", default=[])
    parser.add_argument("--apply-aliases", action="store_true")
    parser.add_argument("--baseline-alias-task", type=int)
    parser.add_argument("--replay-limit", type=int, choices=range(0, 51), default=0)
    parser.add_argument("--retry-fulltext-limit", type=int, choices=range(0, 21), default=0)
    parser.add_argument("--sync", action="store_true")
    asyncio.run(run(parser.parse_args()))
