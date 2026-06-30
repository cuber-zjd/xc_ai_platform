from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlmodel import select

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db.session import async_session  # noqa: E402
from app.models.agent.insight import InsightChannel, InsightMonitorConfig  # noqa: E402
from app.schemas.agent.insight.crawl import InsightSearchDiscoveryRequest  # noqa: E402
from app.services.agent.insight.channel_service import insight_channel_service  # noqa: E402
from app.services.agent.insight.crawler import insight_search_discovery_service  # noqa: E402
from app.services.agent.insight.crawler.channel_adapter_service import insight_channel_adapter_service  # noqa: E402


XIANGCHI_TERMS = [
    "果葡糖浆",
    "麦芽糖",
    "植物蛋白",
    "豆粕",
    "粮油",
    "大豆加工",
    "玉米加工",
    "功能糖",
    "低糖配料",
]

EXCLUDED_SAMPLE_WORDS = ("测试客户", "烟测", "demo", "Demo", "DEMO", "样例")
MODE_RUN_TYPE = {
    "simulate-daily": "daily",
    "simulate-weekly": "weekly",
    "simulate-monthly": "monthly",
    "backfill": "backfill",
}
BUILTIN_HANDLERS = {
    "baidu_news": "baidu_news",
    "bocha_search": "bocha",
}
BUSINESS_DAILY_SITE_ORDER = [
    "shipin_huoban",
    "food_daily",
    "grainnews",
    "chinagrain",
    "new_protein",
]
BUSINESS_WEEKLY_SITE_ORDER = [
    *BUSINESS_DAILY_SITE_ORDER,
    "drinknewspaper",
    "foodinc",
    "shiye_toutiao",
    "xinyingyang",
    "yntw",
    "food_industry_observe",
    "kamen",
    "sina_finance",
    "huaon",
    "cnstock",
    "stockstar",
]


@dataclass(slots=True)
class RunItemReport:
    channel_code: str
    channel_name: str
    query: str
    monitor_config_id: int | None
    status: str
    hit_count: int = 0
    candidate_count: int = 0
    formal_count: int = 0
    sample_urls: list[str] = field(default_factory=list)
    error: str | None = None
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())
    finished_at: str | None = None


@dataclass(frozen=True, slots=True)
class ChannelSnapshot:
    id: int | None
    channel_code: str
    channel_name: str


@dataclass(frozen=True, slots=True)
class MonitorConfigSnapshot:
    id: int | None
    config_name: str
    object_name: str | None
    relation_type: str | None
    monitor_type: str
    keywords: list[str]
    excluded_keywords: list[str]


@dataclass(frozen=True, slots=True)
class RunJob:
    channel: ChannelSnapshot
    handler: str
    query: str
    monitor_config: MonitorConfigSnapshot | None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Insight 全渠道适配器模拟调度与近半月补数入口")
    parser.add_argument("--mode", choices=["backfill", "simulate-daily", "simulate-weekly", "simulate-monthly"], required=True)
    parser.add_argument("--days", type=int, default=15)
    parser.add_argument("--limit-configs", type=int, default=0, help="冒烟时限制监测配置数量，0 表示不限制")
    parser.add_argument("--limit-adapters", type=int, default=0, help="冒烟时限制网站适配器数量，0 表示不限制")
    parser.add_argument("--dry-run", action="store_true", help="只输出执行计划，不请求外部网站、不入库")
    parser.add_argument("--user-id", type=int, default=None)
    parser.add_argument("--output-dir", type=str, default=str(BACKEND_ROOT / "storage" / "insight_adapter_run_reports"))
    parser.add_argument("--api-concurrency", type=int, default=8, help="百度、博查和 HTTP 适配器并发数")
    parser.add_argument("--playwright-concurrency", type=int, default=4, help="Playwright 站点适配器并发数")
    parser.add_argument("--adapter-timeout", type=int, default=180, help="单个渠道任务超时时间，单位秒")
    parser.add_argument("--shard-index", type=int, default=0, help="分片索引，从 0 开始")
    parser.add_argument("--shard-total", type=int, default=1, help="分片总数，用于夜间分批补数")
    return parser.parse_args()


def selected_channel_codes(mode: str) -> list[str]:
    supported = [item for item in insight_channel_adapter_service.adapters if item.status == "supported"]
    key = [item.channel_code for item in supported if item.priority == "key"]
    other = [item.channel_code for item in supported if item.priority != "key"]
    if mode == "simulate-daily":
        site_codes = ordered_supported_codes(BUSINESS_DAILY_SITE_ORDER, key, limit=5)
        return ["baidu_news", "bocha_search", *site_codes]
    if mode == "simulate-weekly":
        site_codes = ordered_supported_codes(BUSINESS_WEEKLY_SITE_ORDER, [*key, *other], limit=12)
        return ["baidu_news", "bocha_search", *site_codes]
    return ["baidu_news", "bocha_search", *key, *other]


def ordered_supported_codes(preferred: list[str], candidates: list[str], *, limit: int | None = None) -> list[str]:
    candidate_set = set(candidates)
    ordered: list[str] = []
    for code in preferred:
        if code in candidate_set and code not in ordered:
            ordered.append(code)
    for code in candidates:
        if code not in ordered:
            ordered.append(code)
    if limit is not None:
        return ordered[:limit]
    return ordered


def is_sample_config(row: InsightMonitorConfig | MonitorConfigSnapshot) -> bool:
    text = " ".join(
        [
            row.config_name or "",
            row.object_name or "",
            " ".join(row.keywords or []),
        ]
    )
    return any(word in text for word in EXCLUDED_SAMPLE_WORDS)


def build_query(row: InsightMonitorConfig | MonitorConfigSnapshot | None) -> str:
    if not row:
        return "香驰控股 " + " ".join(XIANGCHI_TERMS)
    parts = [row.object_name or row.config_name]
    parts.extend(row.keywords or [])
    if row.monitor_type in {"industry_topic", "product_topic", "topic"}:
        parts.extend(XIANGCHI_TERMS[:5])
    deduped: list[str] = []
    for item in parts:
        value = str(item or "").strip()
        if value and value not in deduped:
            deduped.append(value)
    return " ".join(deduped[:10])


def filter_prompt(row: InsightMonitorConfig | MonitorConfigSnapshot | None) -> str:
    base = (
        "请围绕香驰控股有限公司的业务判断公开信息是否有价值。香驰主要涉及玉米、大豆加工，"
        "果葡糖浆、麦芽糖、豆粕、植物蛋白粉、粮油、功能糖和低糖配料等产品。"
        "正式情报优先保留客户、竞对、价格、产能、食品配料、粮油供需、政策监管、专利技术、"
        "投融资、风险事件和渠道变化相关内容；明显广告、泛泛转载、无关娱乐和低质量聚合应剔除。"
    )
    if not row:
        return base
    return f"{base}\n当前监测对象：{row.object_name or row.config_name}。关系类型：{row.relation_type or row.monitor_type}。"


async def load_channels(db, codes: list[str], *, ensure_seed: bool) -> dict[str, ChannelSnapshot]:
    if ensure_seed:
        await insight_channel_service.seed_default_channels(db, None)
    rows = list(
        (
            await db.exec(
                select(InsightChannel).where(
                    InsightChannel.channel_code.in_(codes),
                    InsightChannel.is_deleted == 0,
                    InsightChannel.status == "active",
                )
            )
        ).all()
    )
    return {row.channel_code: ChannelSnapshot(id=row.id, channel_code=row.channel_code, channel_name=row.channel_name) for row in rows}


async def load_monitor_configs(db, limit: int) -> list[MonitorConfigSnapshot]:
    rows = list(
        (
            await db.exec(
                select(InsightMonitorConfig)
                .where(
                    InsightMonitorConfig.is_deleted == 0,
                    InsightMonitorConfig.status == "active",
                    InsightMonitorConfig.schedule_enabled == True,  # noqa: E712
                )
                .order_by(InsightMonitorConfig.last_success_time.desc().nullslast(), InsightMonitorConfig.id.asc())
            )
        ).all()
    )
    rows = [row for row in rows if not is_sample_config(row)]
    if limit > 0:
        rows = rows[:limit]
    return [
        MonitorConfigSnapshot(
            id=row.id,
            config_name=row.config_name,
            object_name=row.object_name,
            relation_type=row.relation_type,
            monitor_type=row.monitor_type,
            keywords=list(row.keywords or []),
            excluded_keywords=list(row.excluded_keywords or []),
        )
        for row in rows
    ]


def channel_handler(code: str) -> str | None:
    if code in BUILTIN_HANDLERS:
        return BUILTIN_HANDLERS[code]
    if code in insight_channel_adapter_service.supported_channel_codes():
        return code
    return None


def max_results_for(mode: str, channel_code: str) -> int:
    if channel_code == "bocha_search":
        if mode == "simulate-daily":
            return 10
        if mode == "simulate-weekly":
            return 30
        return 50
    if mode == "simulate-daily":
        return 12
    if mode == "simulate-weekly":
        return 20
    return 30


async def execute_item(
    *,
    channel: ChannelSnapshot,
    handler: str,
    query: str,
    monitor_config: MonitorConfigSnapshot | None,
    mode: str,
    days: int,
    user_id: int | None,
    dry_run: bool,
    timeout_seconds: int,
) -> RunItemReport:
    report = RunItemReport(
        channel_code=channel.channel_code,
        channel_name=channel.channel_name,
        query=query,
        monitor_config_id=monitor_config.id if monitor_config else None,
        status="planned" if dry_run else "running",
    )
    if dry_run:
        report.finished_at = datetime.now().isoformat()
        return report
    try:
        async with async_session() as db:
            request = InsightSearchDiscoveryRequest(
                query=query,
                channels=[handler],
                freshness="halfMonth" if days <= 15 else "noLimit",
                max_results=max_results_for(mode, channel.channel_code),
                crawl_top_n=0,
                monitor_config_id=monitor_config.id if monitor_config else None,
                source_channel_id=channel.id,
                exclude_keywords=(monitor_config.excluded_keywords if monitor_config else []) or [],
                filter_prompt=filter_prompt(monitor_config),
                enable_llm_filter=True,
                llm_min_score=0.6,
                create_candidate_from_hits=True,
                run_type=MODE_RUN_TYPE[mode],
            )
            response = await asyncio.wait_for(
                insight_search_discovery_service.search_and_crawl(
                    db,
                    request,
                    user_id=user_id,
                    is_admin=True,
                ),
                timeout=timeout_seconds,
            )
        report.status = "success"
        report.hit_count = len(response.hits)
        report.candidate_count = len(response.candidates)
        report.formal_count = len([item for item in response.candidates if str(getattr(item, "review_status", "")) == "promoted"])
        report.sample_urls = [item.url for item in response.hits[:5]]
    except Exception as exc:
        report.status = "failed"
        report.error = f"{exc.__class__.__name__}: {str(exc)[:500]}"
    finally:
        report.finished_at = datetime.now().isoformat()
    return report


def execution_bucket(channel_code: str) -> str:
    if channel_code in BUILTIN_HANDLERS:
        return "api"
    definition = insight_channel_adapter_service.definition_for(channel_code)
    if definition and definition.adapter_kind == "http":
        return "api"
    return "playwright"


def shard_jobs(jobs: list[RunJob], shard_index: int, shard_total: int) -> list[RunJob]:
    if shard_total <= 1:
        return jobs
    if shard_index < 0 or shard_index >= shard_total:
        raise ValueError("--shard-index 必须在 0 和 --shard-total - 1 之间")
    return [job for index, job in enumerate(jobs) if index % shard_total == shard_index]


async def run_jobs(jobs: list[RunJob], args: argparse.Namespace) -> list[RunItemReport]:
    api_semaphore = asyncio.Semaphore(max(args.api_concurrency, 1))
    playwright_semaphore = asyncio.Semaphore(max(args.playwright_concurrency, 1))
    channel_locks = {code: asyncio.Lock() for code in {job.channel.channel_code for job in jobs}}

    async def run_one(job: RunJob) -> RunItemReport:
        bucket = execution_bucket(job.channel.channel_code)
        semaphore = api_semaphore if bucket == "api" else playwright_semaphore
        async with semaphore:
            async with channel_locks[job.channel.channel_code]:
                return await execute_item(
                    channel=job.channel,
                    handler=job.handler,
                    query=job.query,
                    monitor_config=job.monitor_config,
                    mode=args.mode,
                    days=args.days,
                    user_id=args.user_id,
                    dry_run=args.dry_run,
                    timeout_seconds=args.adapter_timeout,
                )

    results: list[RunItemReport] = []
    for task in asyncio.as_completed([asyncio.create_task(run_one(job)) for job in jobs]):
        results.append(await task)
    return results


async def run(args: argparse.Namespace) -> dict[str, Any]:
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    selected_codes = selected_channel_codes(args.mode)
    if args.limit_adapters > 0:
        builtins = [code for code in selected_codes if code in BUILTIN_HANDLERS]
        adapters = [code for code in selected_codes if code not in BUILTIN_HANDLERS][: args.limit_adapters]
        selected_codes = [*builtins, *adapters]
    async with async_session() as db:
        channels = await load_channels(db, selected_codes, ensure_seed=not args.dry_run)
        monitor_configs = await load_monitor_configs(db, args.limit_configs)
        query_configs: list[MonitorConfigSnapshot | None] = [*monitor_configs, None]
        jobs: list[RunJob] = []
        skipped_items: list[RunItemReport] = []
        for code in selected_codes:
            channel = channels.get(code)
            handler = channel_handler(code)
            if not channel or not handler:
                skipped_items.append(
                    RunItemReport(
                        channel_code=code,
                        channel_name=code,
                        query="",
                        monitor_config_id=None,
                        status="skipped",
                        error="渠道未在渠道库启用或适配器未支持",
                        finished_at=datetime.now().isoformat(),
                    )
                )
                continue
            for config in query_configs:
                query = build_query(config)
                jobs.append(RunJob(channel=channel, handler=handler, query=query, monitor_config=config))
    total_job_count = len(jobs) + len(skipped_items)
    jobs = shard_jobs(jobs, args.shard_index, max(args.shard_total, 1))
    items = [*skipped_items, *(await run_jobs(jobs, args))]
    pending = [
        asdict(item)
        for item in insight_channel_adapter_service.adapters
        if item.status != "supported" or item.channel_code not in insight_channel_adapter_service.supported_channel_codes()
    ]
    summary = {
        "mode": args.mode,
        "days": args.days,
        "dry_run": args.dry_run,
        "generated_at": datetime.now().isoformat(),
        "selected_channel_count": len(selected_codes),
        "planned_job_count": total_job_count,
        "shard_job_count": len(jobs),
        "executed_job_count": len(jobs),
        "shard_index": args.shard_index,
        "shard_total": args.shard_total,
        "api_concurrency": args.api_concurrency,
        "playwright_concurrency": args.playwright_concurrency,
        "adapter_timeout": args.adapter_timeout,
        "monitor_config_count": max(len({item.monitor_config_id for item in items if item.monitor_config_id}), 0),
        "success_count": len([item for item in items if item.status == "success"]),
        "failed_count": len([item for item in items if item.status == "failed"]),
        "skipped_count": len([item for item in items if item.status in {"skipped", "planned"}]),
        "hit_count": sum(item.hit_count for item in items),
        "candidate_count": sum(item.candidate_count for item in items),
        "formal_count": sum(item.formal_count for item in items),
        "items": [asdict(item) for item in items],
        "pending_or_unstable_adapters": pending,
    }
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = output_dir / f"{args.mode}_{args.days}d_{stamp}.json"
    md_path = output_dir / f"{args.mode}_{args.days}d_{stamp}.md"
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    md_path.write_text(render_markdown(summary), encoding="utf-8")
    summary["json_report_path"] = str(json_path)
    summary["markdown_report_path"] = str(md_path)
    return summary


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Insight 全渠道适配器运行报告",
        "",
        f"- 模式：{summary['mode']}",
        f"- 窗口：近 {summary['days']} 天",
        f"- 生成时间：{summary['generated_at']}",
        f"- 渠道数：{summary['selected_channel_count']}",
        f"- 成功/失败/跳过：{summary['success_count']} / {summary['failed_count']} / {summary['skipped_count']}",
        f"- 命中/候选/正式：{summary['hit_count']} / {summary['candidate_count']} / {summary['formal_count']}",
        "",
        "## 渠道运行明细",
        "",
        "| 渠道 | 状态 | 监测配置 | 命中 | 候选 | 正式 | 样例 URL | 失败原因 |",
        "| --- | --- | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for item in summary["items"]:
        urls = "<br>".join(item["sample_urls"][:3])
        lines.append(
            "| {channel} | {status} | {config} | {hit} | {candidate} | {formal} | {urls} | {error} |".format(
                channel=item["channel_code"],
                status=item["status"],
                config=item["monitor_config_id"] or "",
                hit=item["hit_count"],
                candidate=item["candidate_count"],
                formal=item["formal_count"],
                urls=sanitize_table_cell(urls),
                error=sanitize_table_cell(item["error"] or ""),
            )
        )
    lines.extend(["", "## 暂未稳定接入", ""])
    for item in summary["pending_or_unstable_adapters"]:
        lines.append(f"- {item['channel_code']}（{item['source_name']}）：{item['status']}，{item.get('note') or '待补充'}")
    return "\n".join(lines) + "\n"


def sanitize_table_cell(value: str) -> str:
    return str(value or "").replace("|", "/").replace("\r", " ").replace("\n", " ")[:500]


def main() -> None:
    args = parse_args()
    summary = asyncio.run(run(args))
    print(json.dumps({k: v for k, v in summary.items() if k not in {"items"}}, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
