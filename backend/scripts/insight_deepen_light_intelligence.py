"""批量深化 Insight 搜索轻发现情报。

该脚本只处理已经入库的真实来源情报，不生成前端假数据：
- 选择 raw_payload 中带“待AI深化”的正式情报；
- 按正式情报来源 URL 调用 Firecrawl 抓取正文；
- 复用 Insight 候选摘要 LLM 生成摘要、标签、情感、机会点和风险点；
- 回写正式情报 content、summary、sentiment、raw_payload.ai_analysis。
"""

import argparse
import asyncio
import sys
import warnings
from datetime import datetime
from typing import Any

from loguru import logger
from sqlalchemy import text
from sqlmodel import select

from app.db.session import async_session, engine
from app.models.agent.insight import InsightIntelligence, InsightIntelligenceSource
from app.models.agent.insight.data_source import InsightDataSource
from app.models.system.sys_company import SysCompany  # noqa: F401
from app.services.agent.insight.crawler.content_cleaner import insight_content_cleaner
from app.services.agent.insight.crawler.crawl_service import insight_crawl_service
from app.services.agent.insight.crawler.firecrawl_client import firecrawl_client


async def run(args: argparse.Namespace) -> None:
    if args.quiet_logs:
        warnings.filterwarnings("ignore")
        logger.remove()
        logger.add(sys.stderr, level="WARNING")
    engine.echo = False
    processed = 0
    success = 0
    failed = 0
    skipped = 0
    async with async_session() as db:
        filters = [
            InsightIntelligence.is_deleted == 0,
            InsightIntelligence.status == "active",
            text("raw_payload::text LIKE '%待AI深化%'"),
            text("COALESCE(raw_payload->>'deepening_status', '') NOT IN ('completed', 'failed')"),
        ]
        statement = select(InsightIntelligence)
        if args.include_source_types or args.exclude_source_types:
            statement = statement.join(InsightDataSource, InsightDataSource.id == InsightIntelligence.data_source_id)
            if args.include_source_types:
                filters.append(InsightDataSource.source_type.in_(args.include_source_types))
            if args.exclude_source_types:
                filters.append(InsightDataSource.source_type.notin_(args.exclude_source_types))
        rows = list(
            (
                await db.exec(
                    statement
                    .where(*filters)
                    .order_by(InsightIntelligence.capture_time.desc().nullslast(), InsightIntelligence.id.desc())
                    .limit(args.limit)
                )
            ).all()
        )
        print(f"待深化情报：本批 {len(rows)} 条", flush=True)
        for intelligence in rows:
            intelligence_id = intelligence.id or 0
            intelligence_title = intelligence.title or ""
            processed += 1
            source = await _get_primary_source(db, intelligence_id)
            if not source or not source.source_url:
                _mark_deepen_failure(intelligence, "无来源 URL，无法正文深化")
                await db.commit()
                skipped += 1
                print(f"  跳过 {intelligence_id}: 无来源 URL", flush=True)
                continue
            if args.search_excerpt_only:
                changed = await asyncio.wait_for(
                    _enrich_from_search_excerpt(db, intelligence, source, "按参数跳过正文抓取，使用真实搜索摘要做 AI 富化"),
                    timeout=args.per_item_timeout,
                )
                if changed:
                    success += 1
                    print(f"  摘要富化 {intelligence_id}: {(intelligence.title or intelligence_title)[:80]}", flush=True)
                else:
                    skipped += 1
                    print(f"  跳过 {intelligence_id}: 搜索摘要质量不足", flush=True)
                continue
            if _is_excluded_url(source.source_url):
                _mark_deepen_failure(intelligence, "来源 URL 属于验证码、图片搜索、联盟跳转或强反爬页面，暂不做正文深化")
                await db.commit()
                skipped += 1
                print(f"  跳过 {intelligence_id}: URL 不适合正文深化", flush=True)
                continue
            try:
                changed = await asyncio.wait_for(
                    _deepen_one(db, intelligence, source),
                    timeout=args.per_item_timeout,
                )
                if changed:
                    success += 1
                    print(f"  完成 {intelligence_id}: {(intelligence.title or intelligence_title)[:80]}", flush=True)
                else:
                    skipped += 1
                    print(f"  跳过 {intelligence_id}: 正文质量不足", flush=True)
            except asyncio.TimeoutError:
                await db.rollback()
                failed += 1
                print(f"  失败 {intelligence_id}: 单条超过 {args.per_item_timeout} 秒", flush=True)
            except Exception as exc:
                await db.rollback()
                failed += 1
                print(f"  失败 {intelligence_id}: {exc}", flush=True)
        print({"processed": processed, "success": success, "skipped": skipped, "failed": failed}, flush=True)


async def _get_primary_source(db, intelligence_id: int) -> InsightIntelligenceSource | None:
    return (
        await db.exec(
            select(InsightIntelligenceSource)
            .where(
                InsightIntelligenceSource.intelligence_id == intelligence_id,
                InsightIntelligenceSource.is_deleted == 0,
            )
            .order_by(InsightIntelligenceSource.create_time.asc(), InsightIntelligenceSource.id.asc())
        )
    ).first()


async def _deepen_one(
    db,
    intelligence: InsightIntelligence,
    source: InsightIntelligenceSource,
) -> bool:
    try:
        firecrawl_data = await firecrawl_client.scrape_url(source.source_url or "")
    except Exception as exc:
        return await _enrich_from_search_excerpt(db, intelligence, source, f"正文抓取失败：{exc}")
    metadata = firecrawl_data.get("metadata") or {}
    markdown = insight_content_cleaner.clean_text(firecrawl_data.get("markdown") or firecrawl_data.get("content")) or ""
    readable = insight_content_cleaner.clean_readable_excerpt(markdown) or ""
    if len(readable) < 120 or "页面需要安全验证" in readable:
        return await _enrich_from_search_excerpt(db, intelligence, source, f"正文质量不足，长度 {len(readable)}")

    title = insight_content_cleaner.clean_title(
        metadata.get("title"),
        firecrawl_data.get("title"),
        source.source_title,
        intelligence.title,
    )
    publish_time = insight_content_cleaner.parse_publish_time(metadata, markdown, title) or source.source_publish_time
    llm_result = await insight_crawl_service._summarize_candidate_with_llm(title, source.source_url or "", readable)
    if not llm_result:
        _mark_deepen_failure(intelligence, "AI 摘要失败，保留搜索摘要")
        await db.commit()
        return False

    summary = str(llm_result.get("summary") or insight_content_cleaner.clean_summary(readable, 800) or intelligence.summary or "")
    intelligence.title = str(llm_result.get("title") or title or intelligence.title)[:500]
    intelligence.summary = summary
    intelligence.content = readable[:20000]
    intelligence.intelligence_type = str(llm_result.get("intelligence_type") or intelligence.intelligence_type or "行业资讯")[:50]
    intelligence.sentiment = _normalize_sentiment(llm_result.get("sentiment"))
    if publish_time and publish_time <= datetime.now():
        intelligence.publish_time = publish_time
    intelligence.raw_payload = _merge_raw_payload(intelligence.raw_payload, llm_result, readable, source, mode="full_text")

    source.source_title = title[:500]
    source.source_publish_time = intelligence.publish_time
    source.content_excerpt = insight_content_cleaner.clean_summary(readable, 1000)
    source.source_metadata = (source.source_metadata or {}) | {
        "deepened_at": datetime.now().isoformat(),
        "firecrawl_metadata": metadata,
    }
    await db.commit()
    return True


async def _enrich_from_search_excerpt(
    db,
    intelligence: InsightIntelligence,
    source: InsightIntelligenceSource,
    reason: str,
) -> bool:
    search_text = "\n".join(
        item
        for item in [
            intelligence.title or "",
            intelligence.summary or "",
            source.source_title or "",
            source.content_excerpt or "",
        ]
        if item
    )
    readable = insight_content_cleaner.clean_readable_excerpt(search_text) or ""
    if len(readable) < 40:
        _mark_deepen_failure(intelligence, reason)
        await db.commit()
        return False
    llm_result = await insight_crawl_service._summarize_candidate_with_llm(
        intelligence.title or source.source_title or "未命名情报",
        source.source_url or "",
        readable,
    )
    if not llm_result:
        _mark_deepen_failure(intelligence, f"{reason}；搜索摘要级 AI 富化失败")
        await db.commit()
        return False
    intelligence.title = str(llm_result.get("title") or intelligence.title or source.source_title or "")[:500]
    intelligence.summary = str(llm_result.get("summary") or intelligence.summary or readable)[:2000]
    intelligence.intelligence_type = str(llm_result.get("intelligence_type") or intelligence.intelligence_type or "行业资讯")[:50]
    intelligence.sentiment = _normalize_sentiment(llm_result.get("sentiment"))
    intelligence.raw_payload = _merge_raw_payload(
        intelligence.raw_payload,
        llm_result,
        readable,
        source,
        mode="search_excerpt",
        note=reason,
    )
    await db.commit()
    return True


def _merge_raw_payload(
    raw_payload: dict[str, Any] | None,
    llm_result: dict[str, Any],
    readable: str,
    source: InsightIntelligenceSource,
    *,
    mode: str,
    note: str | None = None,
) -> dict[str, Any]:
    raw = dict(raw_payload or {})
    suggested_tags = [
        {"name": name, "source": "llm"}
        for name in _string_items(llm_result.get("tags"))[:6]
    ]
    ai_analysis = {
        "tags": [item["name"] for item in suggested_tags],
        "sentiment": _normalize_sentiment(llm_result.get("sentiment")),
        "sentiment_reason": str(llm_result.get("sentiment_reason") or "").strip()[:500],
        "opportunities": _string_items(llm_result.get("opportunities"))[:6],
        "risks": _string_items(llm_result.get("risks"))[:6],
        "source_excerpt": insight_content_cleaner.clean_summary(readable, 800),
        "source_summary": str(llm_result.get("summary") or "").strip()[:1200],
        "deepened_at": datetime.now().isoformat(),
        "deepened_by": "insight_deepen_light_intelligence",
        "source_url": source.source_url,
        "deepening_mode": mode,
        "deepening_note": note,
    }
    raw["suggested_tags"] = suggested_tags + [
        {
            "name": "AI分析",
            "source": "llm_analysis",
            "sentiment": ai_analysis["sentiment"],
            "sentiment_reason": ai_analysis["sentiment_reason"],
            "opportunities": ai_analysis["opportunities"],
            "risks": ai_analysis["risks"],
        }
    ]
    raw["ai_analysis"] = ai_analysis
    raw["deepening_status"] = "completed"
    raw["deepening_mode"] = mode
    raw.pop("publish_time_note", None)
    return raw


def _mark_deepen_failure(intelligence: InsightIntelligence, reason: str) -> None:
    raw = dict(intelligence.raw_payload or {})
    failures = list(raw.get("deepening_failures") or [])
    failures.append({"time": datetime.now().isoformat(), "reason": reason[:500]})
    raw["deepening_failures"] = failures[-5:]
    raw["deepening_status"] = "failed"
    intelligence.raw_payload = raw


def _normalize_sentiment(value: object) -> str:
    sentiment = str(value or "neutral").strip()
    return sentiment if sentiment in {"positive", "neutral", "negative", "mixed"} else "neutral"


def _string_items(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip()[:80] for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [item.strip()[:80] for item in value.replace("；", ";").split(";") if item.strip()]
    return []


def _is_excluded_url(url: str | None) -> bool:
    text = (url or "").lower()
    excluded_tokens = (
        "image.baidu.com",
        "wappass.baidu.com",
        "union-click.jd.com",
        "verify.meituan.com",
        "pages-fast.m.taobao.com",
        "taobao.com/list/item",
        "b2b.baidu.com",
        "baike.",
    )
    return any(token in text for token in excluded_tokens)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--per-item-timeout", type=int, default=90)
    parser.add_argument("--quiet-logs", action="store_true")
    parser.add_argument("--include-source-types", nargs="*", default=[])
    parser.add_argument("--exclude-source-types", nargs="*", default=[])
    parser.add_argument(
        "--search-excerpt-only",
        action="store_true",
        help="跳过正文抓取，仅基于真实搜索标题、摘要和来源片段调用 AI 富化；适合电商、跳转和强反爬渠道。",
    )
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(run(parse_args()))
