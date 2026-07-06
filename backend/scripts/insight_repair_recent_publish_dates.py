"""修复近期 Insight 正式情报的发布时间。

用于处理采集脚本把抓取时间误写成文章发布时间的历史数据。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlparse

import httpx
from sqlalchemy import select

from app.db.session import async_session
from app.models.agent.insight.asset import InsightIntelligenceAsset
from app.models.agent.insight.crawl import InsightCrawlResult
from app.models.agent.insight.intelligence import (
    InsightIntelligence,
    InsightIntelligenceCandidate,
    InsightIntelligenceSource,
)
from app.services.agent.insight.crawler.content_cleaner import insight_content_cleaner


EVENT_DATE_KEYWORDS = (
    "股权登记日",
    "除权除息日",
    "现金红利发放日",
    "申请公布日期",
    "授权公告日",
    "授权公告日期",
    "申请日期",
    "公告日",
    "上市日期",
    "成立日期",
    "申购日期",
    "截至",
    "截止",
)


@dataclass(slots=True)
class DateCandidate:
    value: datetime
    reason: str
    confidence: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="修复 Insight 正式情报发布时间")
    parser.add_argument("--since", default="2026-07-01", help="按正式情报 create_time 起始日期过滤")
    parser.add_argument("--until", default=None, help="按正式情报 create_time 结束日期过滤，默认当前时间")
    parser.add_argument("--apply", action="store_true", help="实际写库；默认 dry-run")
    parser.add_argument("--limit", type=int, default=0, help="最多处理多少条，0 表示不限")
    return parser.parse_args()


def parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    parsed = insight_content_cleaner.parse_publish_time({"datePublished": text})
    if parsed:
        return parsed.replace(tzinfo=None)
    parsed = insight_content_cleaner.parse_publish_time({}, text)
    if parsed:
        return parsed.replace(tzinfo=None)
    normalized = text.replace("/", "-").replace(".", "-").replace("T", " ")
    normalized = re.sub(r"([+-]\d{2}:?\d{2}|Z)$", "", normalized).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(normalized[:19], fmt)
        except ValueError:
            continue
    return None


def is_plausible(value: datetime, *, now: datetime) -> bool:
    return datetime(2000, 1, 1) <= value <= now + timedelta(days=1)


def nested_values(payload: Any, keys: set[str]) -> list[Any]:
    values: list[Any] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in keys:
                values.append(value)
            values.extend(nested_values(value, keys))
    elif isinstance(payload, list):
        for item in payload:
            values.extend(nested_values(item, keys))
    return values


def nested_texts(payload: Any, keys: set[str]) -> list[str]:
    values: list[str] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in keys and isinstance(value, str) and value.strip():
                values.append(value.strip())
            values.extend(nested_texts(value, keys))
    elif isinstance(payload, list):
        for item in payload:
            values.extend(nested_texts(item, keys))
    return values


def has_event_date_text(payloads: list[dict[str, Any] | None]) -> bool:
    text_keys = {"search_context", "snippet", "summary", "content", "description", "title", "source_title"}
    for payload in payloads:
        for text in nested_texts(payload, text_keys):
            if any(keyword in text for keyword in EVENT_DATE_KEYWORDS):
                return True
    return False


def date_from_url(url: str | None) -> DateCandidate | None:
    if not url:
        return None
    patterns = (
        r"/(?P<year>20\d{2})[-/](?P<month>\d{1,2})[-/](?P<day>\d{1,2})/",
        r"/(?P<year>20\d{2})(?P<month>\d{2})(?P<day>\d{2})/",
        r"(?P<year>20\d{2})(?P<month>\d{2})(?P<day>\d{2})",
    )
    for pattern in patterns:
        match = re.search(pattern, url)
        if not match:
            continue
        try:
            value = datetime(int(match.group("year")), int(match.group("month")), int(match.group("day")))
        except ValueError:
            continue
        return DateCandidate(value=value, reason="url_date", confidence=88)
    return None


def extract_from_foodaily(html: str) -> DateCandidate | None:
    article_block = re.search(
        r'<h2[^>]*class="article-title"[^>]*>.*?</h2>.*?<div[^>]*class="news-user-time"[^>]*>(?P<body>.*?)</div>\s*</div>',
        html,
        re.S | re.I,
    )
    body = article_block.group("body") if article_block else html[:10000]
    date_match = re.search(r"(20\d{2})[./年-](\d{1,2})[./月-](\d{1,2})", body)
    if not date_match:
        return None
    value = datetime(int(date_match.group(1)), int(date_match.group(2)), int(date_match.group(3)))
    return DateCandidate(value=value, reason="foodaily_article_page", confidence=95)


def extract_from_html(html: str, url: str | None) -> DateCandidate | None:
    host = urlparse(url or "").netloc.lower()
    if "foodaily.com" in host:
        foodaily = extract_from_foodaily(html)
        if foodaily:
            return foodaily
    patterns = (
        r'"datePublished"\s*:\s*"(?P<date>[^"]+)"',
        r'property=["\']article:published_time["\']\s+content=["\'](?P<date>[^"\']+)["\']',
        r'name=["\']pubdate["\']\s+content=["\'](?P<date>[^"\']+)["\']',
        r'<time[^>]+datetime=["\'](?P<date>[^"\']+)["\']',
        r"(?:发布时间|发表时间|发布日期|时间)[:：\s]*(?P<date>20\d{2}[年./-]\d{1,2}[月./-]\d{1,2}(?:日)?(?:\s+\d{1,2}:\d{2})?)",
    )
    for pattern in patterns:
        match = re.search(pattern, html, re.S | re.I)
        if not match:
            continue
        value = parse_datetime(match.group("date"))
        if value:
            return DateCandidate(value=value, reason="article_page_meta", confidence=90)
    return None


async def fetch_page_date(client: httpx.AsyncClient, url: str | None) -> DateCandidate | None:
    if not url:
        return None
    try:
        response = await client.get(url, follow_redirects=True)
        response.raise_for_status()
    except Exception:
        return None
    candidate = extract_from_html(response.text, url)
    if candidate and abs((candidate.value - datetime.now()).total_seconds()) <= 600:
        return None
    return candidate


def is_suspicious_existing(value: datetime | None, *, create_time: datetime | None, source_channel: str | None, url: str | None) -> bool:
    if not value or not create_time:
        return True
    if value > create_time + timedelta(hours=12):
        return True
    host = urlparse(url or "").netloc.lower()
    if value.date() == create_time.date() and value.hour == 0 and value.minute == 0 and value.second == 0:
        if host in {"www.jiemian.com", "jiemian.com"} or "baijiahao.baidu.com" in host:
            return True
    if abs((value - create_time).total_seconds()) <= 600:
        if source_channel in {"food_daily", "drinknewspaper", "shipin_huoban", "huaon"}:
            return True
        if "foodaily.com" in host or "baijiahao.baidu.com" in host:
            return True
    if value.date() != create_time.date():
        value_seconds = value.hour * 3600 + value.minute * 60 + value.second
        create_seconds = create_time.hour * 3600 + create_time.minute * 60 + create_time.second
        if abs(value_seconds - create_seconds) <= 600:
            host = urlparse(url or "").netloc.lower()
            if "baijiahao.baidu.com" in host or source_channel in {"food_daily", "drinknewspaper", "shipin_huoban", "huaon"}:
                return True
    return False


def candidates_from_metadata(payloads: list[dict[str, Any] | None], *, now: datetime) -> list[DateCandidate]:
    result: list[DateCandidate] = []
    date_keys = {
        "datePublished",
        "dateLastCrawled",
        "created_at",
        "published_at",
        "publish_time",
        "publishedTime",
        "pubdate",
        "date",
        "time",
    }
    text_keys = {"search_context", "snippet", "summary", "content", "description"}
    for payload in payloads:
        if not payload:
            continue
        for text in nested_texts(payload, text_keys):
            value = insight_content_cleaner.parse_publish_time({}, text)
            if value and is_plausible(value, now=now):
                result.append(DateCandidate(value=value, reason="metadata_text", confidence=85))
        for raw_value in nested_values(payload, date_keys):
            value = parse_datetime(raw_value)
            if value and is_plausible(value, now=now):
                result.append(DateCandidate(value=value, reason="metadata_date", confidence=65))
    return result


def choose_candidate(
    candidates: list[DateCandidate],
    *,
    current_value: datetime | None,
    create_time: datetime | None,
    source_channel: str | None,
    url: str | None,
) -> DateCandidate | None:
    filtered: list[DateCandidate] = []
    for candidate in candidates:
        if candidate.reason == "metadata_date" and is_suspicious_existing(
            candidate.value,
            create_time=create_time,
            source_channel=source_channel,
            url=url,
        ):
            continue
        filtered.append(candidate)
    if not filtered:
        return None
    filtered.sort(key=lambda item: item.confidence, reverse=True)
    best = filtered[0]
    if current_value and best.value < current_value - timedelta(days=30):
        return None
    if current_value and abs((best.value - current_value).total_seconds()) < 60:
        return None
    return best


async def main() -> None:
    args = parse_args()
    since = datetime.fromisoformat(args.since)
    until = datetime.fromisoformat(args.until) if args.until else datetime.now()
    now = datetime.now()
    changes: list[dict[str, Any]] = []

    async with async_session() as db:
        rows = (
            await db.execute(
                select(InsightIntelligence, InsightIntelligenceSource, InsightIntelligenceCandidate, InsightCrawlResult)
                .outerjoin(InsightIntelligenceSource, InsightIntelligenceSource.intelligence_id == InsightIntelligence.id)
                .outerjoin(InsightIntelligenceCandidate, InsightIntelligenceCandidate.promoted_intelligence_id == InsightIntelligence.id)
                .outerjoin(InsightCrawlResult, InsightCrawlResult.id == InsightIntelligenceCandidate.crawl_result_id)
                .where(
                    InsightIntelligence.is_deleted == 0,
                    InsightIntelligence.create_time >= since,
                    InsightIntelligence.create_time <= until,
                )
                .order_by(InsightIntelligence.id.asc())
            )
        ).all()
        if args.limit:
            rows = rows[: args.limit]

        async with httpx.AsyncClient(
            timeout=20,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36"},
        ) as client:
            for intelligence, source, _candidate, crawl in rows:
                url = (source.source_url if source else None) or (crawl.source_url if crawl else None)
                source_channel = None
                for payload in (source.source_metadata if source else None, crawl.crawl_metadata if crawl else None):
                    raw = (payload or {}).get("raw") if isinstance(payload, dict) else None
                    if isinstance(raw, dict):
                        source_channel = raw.get("source_channel") or source_channel
                needs_repair = is_suspicious_existing(
                    intelligence.publish_time,
                    create_time=intelligence.create_time,
                    source_channel=source_channel,
                    url=url,
                ) or has_event_date_text([source.source_metadata if source else None, crawl.crawl_metadata if crawl else None])
                if not needs_repair:
                    continue
                candidates = candidates_from_metadata(
                    [
                        source.source_metadata if source else None,
                        crawl.crawl_metadata if crawl else None,
                    ],
                    now=now,
                )
                page_candidate = await fetch_page_date(client, url)
                if page_candidate and is_plausible(page_candidate.value, now=now):
                    candidates.insert(0, page_candidate)
                url_candidate = date_from_url(url)
                if url_candidate and is_plausible(url_candidate.value, now=now):
                    candidates.append(url_candidate)

                chosen = choose_candidate(
                    candidates,
                    current_value=intelligence.publish_time,
                    create_time=intelligence.create_time,
                    source_channel=source_channel,
                    url=url,
                )
                if not chosen:
                    continue

                change = {
                    "id": intelligence.id,
                    "title": intelligence.title,
                    "url": url,
                    "old_publish_time": intelligence.publish_time.isoformat() if intelligence.publish_time else None,
                    "new_publish_time": chosen.value.isoformat(),
                    "reason": chosen.reason,
                }
                changes.append(change)

                if args.apply:
                    intelligence.publish_time = chosen.value
                    intelligence.update_time = datetime.now()
                    raw_payload = dict(intelligence.raw_payload or {})
                    raw_payload["publish_time_repair"] = {
                        "old_publish_time": change["old_publish_time"],
                        "new_publish_time": change["new_publish_time"],
                        "reason": chosen.reason,
                        "repaired_at": datetime.now().isoformat(),
                    }
                    intelligence.raw_payload = raw_payload
                    if source:
                        source.source_publish_time = chosen.value
                        source.update_time = datetime.now()
                    if crawl:
                        crawl.published_at = chosen.value
                        crawl.update_time = datetime.now()
                    assets = (
                        await db.execute(
                            select(InsightIntelligenceAsset).where(
                                InsightIntelligenceAsset.intelligence_id == intelligence.id,
                                InsightIntelligenceAsset.is_deleted == 0,
                            )
                        )
                    ).scalars().all()
                    for asset in assets:
                        asset.publish_time = chosen.value
                        asset.update_time = datetime.now()

        if args.apply:
            await db.commit()

    print(json.dumps({"apply": args.apply, "count": len(changes), "changes": changes}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
