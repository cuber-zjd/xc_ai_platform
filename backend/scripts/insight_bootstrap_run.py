"""Insight 期初真实数据运行脚本。

用法示例：
uv run python scripts/insight_bootstrap_run.py --seed-files "F:/.../信息采集需求收集.xlsx" "F:/.../网址整理.docx" --target 2000 --batch-size 10 --crawl-top-n 4
"""

import argparse
import asyncio
import contextlib
import re
import sys
import warnings
from datetime import datetime
from hashlib import sha1
from pathlib import Path

from loguru import logger
from sqlalchemy import func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.session import async_session
from app.db.session import engine
from app.models.agent.insight import InsightCompany, InsightDataSource, InsightIntelligence
from app.schemas.agent.insight.data_source import InsightDataSourceExecuteRequest
from app.services.agent.insight.data_source_service import insight_data_source_service
from app.services.agent.insight.requirement_import_service import insight_requirement_import_service


COMPANY_SOURCE_PLANS = [
    {
        "suffix": "dynamic",
        "source_type": "multi_news",
        "label": "综合动态",
        "keywords": ["{name}", "{short} 新品", "{short} 研发", "{short} 扩产", "{short} 合作"],
    },
    {
        "suffix": "finance",
        "source_type": "finance_news",
        "label": "经营财经",
        "keywords": ["{short} 业绩", "{short} 投资", "{short} 融资", "{short} 年报"],
    },
    {
        "suffix": "patent",
        "source_type": "patent_search",
        "label": "专利技术",
        "keywords": ["{name} 专利", "{short} 发明专利", "{short} 技术"],
    },
    {
        "suffix": "ecommerce",
        "source_type": "ecommerce_search",
        "label": "电商新品",
        "keywords": ["{short} 新品", "{short} 旗舰店", "{short} 低糖", "{short} 配料"],
    },
    {
        "suffix": "media",
        "source_type": "industry_media",
        "label": "行业媒体",
        "keywords": ["{short} 食品饮料", "{short} 市场", "{short} 渠道", "{short} 趋势"],
    },
]


async def run(args: argparse.Namespace) -> None:
    if args.quiet_logs:
        warnings.filterwarnings("ignore")
        logger.remove()
        logger.add(sys.stderr, level="WARNING")
    engine.echo = False
    if args.single_source_id:
        await execute_single_source(
            data_source_id=args.single_source_id,
            crawl_top_n=args.crawl_top_n,
            user_id=args.user_id,
        )
        return
    async with async_session() as db:
        if args.seed_files:
            files = [(path, Path(path).read_bytes()) for path in args.seed_files if Path(path).exists()]
            result = await insight_requirement_import_service.import_files(
                db,
                files=files,
                user_id=args.user_id,
                is_admin=True,
            )
            print(
                f"导入完成：解析 {result.parsed_count}，新增 {result.created_count}，"
                f"更新 {result.updated_count}，失败 {result.failed_count}，暂未自动化 {len(result.unsupported_channels)}",
                flush=True,
            )

        if args.expand_company_sources:
            created, updated = await expand_company_sources(db, user_id=args.user_id, limit=args.expanded_source_limit)
            print(f"企业扩展数据源完成：新增 {created}，更新 {updated}", flush=True)

        if args.patch_fetch_config:
            patched = await patch_fetch_config(
                db,
                max_results=args.max_results,
                crawl_top_n=args.crawl_top_n,
                keyword_limit=args.keyword_limit,
                create_candidate_from_hits=args.create_candidate_from_hits,
            )
            print(f"数据源抓取配置补强完成：更新 {patched} 个", flush=True)

        round_no = 0
        while round_no < args.max_rounds:
            current_count = (
                await db.exec(
                    select(func.count()).select_from(InsightIntelligence).where(
                        InsightIntelligence.is_deleted == 0,
                        InsightIntelligence.status == "active",
                    )
                )
            ).one()
            print(f"当前正式情报：{current_count}/{args.target}", flush=True)
            if current_count >= args.target:
                break
            source_filters = [
                InsightDataSource.is_deleted == 0,
                InsightDataSource.status == "enabled",
                InsightDataSource.consecutive_failure_count < args.max_source_failures,
            ]
            if args.include_source_types:
                source_filters.append(InsightDataSource.source_type.in_(args.include_source_types))
            if args.exclude_source_types:
                source_filters.append(InsightDataSource.source_type.notin_(args.exclude_source_types))
            if args.skip_source_ids:
                source_filters.append(InsightDataSource.id.notin_(args.skip_source_ids))
            rows = list(
                (
                    await db.exec(
                        select(InsightDataSource)
                        .where(*source_filters)
                        .order_by(InsightDataSource.last_success_time.asc().nullsfirst(), InsightDataSource.id.asc())
                        .limit(args.batch_size)
                    )
                ).all()
            )
            if not rows:
                print("没有可执行的数据源，停止。")
                break
            round_no += 1
            ids = [row.id for row in rows if row.id]
            names = "、".join(row.source_name for row in rows[:5])
            print(f"第 {round_no} 轮执行 {len(ids)} 个数据源：{names}", flush=True)
            result = await execute_sources(
                db,
                ids,
                crawl_top_n=args.crawl_top_n,
                user_id=args.user_id,
                per_source_timeout=args.per_source_timeout,
                subprocess_per_source=args.subprocess_per_source,
            )
            print(f"执行结果：成功 {result['success_count']}，失败 {result['failed_count']}", flush=True)
            for item in result["items"]:
                if item.get("status") == "failed":
                    print(f"失败：{item.get('data_source_id')} {item.get('message')}", flush=True)


async def execute_sources(
    db: AsyncSession,
    data_source_ids: list[int],
    *,
    crawl_top_n: int,
    user_id: int,
    per_source_timeout: int,
    subprocess_per_source: bool,
) -> dict:
    result = {"success_count": 0, "failed_count": 0, "items": []}
    for data_source_id in data_source_ids:
        if subprocess_per_source:
            item = await execute_source_in_subprocess(
                db,
                data_source_id,
                crawl_top_n=crawl_top_n,
                user_id=user_id,
                per_source_timeout=per_source_timeout,
            )
            result["items"].append(item)
            if item.get("status") == "success":
                result["success_count"] += 1
            else:
                result["failed_count"] += 1
            continue
        try:
            response = await asyncio.wait_for(
                insight_data_source_service.execute_data_source(
                    db,
                    data_source_id,
                    InsightDataSourceExecuteRequest(crawl_top_n=crawl_top_n),
                    user_id,
                    is_admin=True,
                ),
                timeout=per_source_timeout,
            )
            candidate_count = sum(len(item.candidates) for item in response.search_results)
            if response.manual_result:
                candidate_count += 1
            result["items"].append(
                {
                    "data_source_id": data_source_id,
                    "status": "success",
                    "candidate_count": candidate_count,
                    "execution_errors": response.execution_errors,
                }
            )
            result["success_count"] += 1
            print(f"  数据源 {data_source_id} 完成，候选 {candidate_count}", flush=True)
        except asyncio.TimeoutError:
            await db.rollback()
            result["items"].append({"data_source_id": data_source_id, "status": "failed", "message": f"单源超过 {per_source_timeout} 秒"})
            result["failed_count"] += 1
        except Exception as exc:
            await db.rollback()
            result["items"].append({"data_source_id": data_source_id, "status": "failed", "message": str(exc)})
            result["failed_count"] += 1
    return result


async def execute_source_in_subprocess(
    db: AsyncSession,
    data_source_id: int,
    *,
    crawl_top_n: int,
    user_id: int,
    per_source_timeout: int,
) -> dict:
    script_path = str(Path(__file__).resolve())
    command = [
        sys.executable,
        "-u",
        script_path,
        "--single-source-id",
        str(data_source_id),
        "--crawl-top-n",
        str(crawl_top_n),
        "--user-id",
        str(user_id),
        "--quiet-logs",
    ]
    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=str(Path(__file__).resolve().parent.parent),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=per_source_timeout)
    except asyncio.TimeoutError:
        with contextlib.suppress(ProcessLookupError):
            process.kill()
        await mark_source_failure(db, data_source_id, f"单源子进程超过 {per_source_timeout} 秒，已中止")
        print(f"  数据源 {data_source_id} 超时，已跳过", flush=True)
        return {"data_source_id": data_source_id, "status": "failed", "message": f"单源超过 {per_source_timeout} 秒"}

    stdout_text = stdout.decode("utf-8", errors="ignore")
    stderr_text = stderr.decode("utf-8", errors="ignore")
    if stdout_text.strip():
        for line in stdout_text.strip().splitlines():
            print(f"  子进程 {data_source_id}: {line}", flush=True)
    if process.returncode == 0:
        match = re.search(r"SINGLE_SOURCE_RESULT status=success candidate_count=(\d+)", stdout_text)
        candidate_count = int(match.group(1)) if match else 0
        return {"data_source_id": data_source_id, "status": "success", "candidate_count": candidate_count, "execution_errors": []}

    message = stderr_text.strip() or stdout_text.strip() or f"子进程退出码 {process.returncode}"
    await mark_source_failure(db, data_source_id, message[:1000])
    print(f"  数据源 {data_source_id} 失败：{message[:300]}", flush=True)
    return {"data_source_id": data_source_id, "status": "failed", "message": message[:1000]}


async def execute_single_source(*, data_source_id: int, crawl_top_n: int, user_id: int) -> None:
    async with async_session() as db:
        response = await insight_data_source_service.execute_data_source(
            db,
            data_source_id,
            InsightDataSourceExecuteRequest(crawl_top_n=crawl_top_n),
            user_id,
            is_admin=True,
        )
        candidate_count = sum(len(item.candidates) for item in response.search_results)
        if response.manual_result:
            candidate_count += 1
        print(f"SINGLE_SOURCE_RESULT status=success candidate_count={candidate_count}", flush=True)


async def mark_source_failure(db: AsyncSession, data_source_id: int, message: str) -> None:
    row = (await db.exec(select(InsightDataSource).where(InsightDataSource.id == data_source_id))).first()
    if not row:
        return
    row.consecutive_failure_count = (row.consecutive_failure_count or 0) + 1
    row.last_schedule_status = "failed"
    row.last_schedule_message = message[:1000]
    row.last_failure_time = datetime.now()
    await db.commit()


async def expand_company_sources(db, *, user_id: int, limit: int) -> tuple[int, int]:
    statement = (
        select(InsightCompany)
        .where(InsightCompany.is_deleted == 0, InsightCompany.status == "active")
        .order_by(InsightCompany.id.asc())
    )
    if limit > 0:
        statement = statement.limit(limit)
    companies = list((await db.exec(statement)).all())
    created = 0
    updated = 0
    for company in companies:
        display_name = company.name.strip()
        short_name = (company.short_name or company.name).strip()
        for plan in COMPANY_SOURCE_PLANS:
            source_code = _source_code(company.id or 0, plan["source_type"], plan["suffix"])
            keywords = _render_keywords(plan["keywords"], name=display_name, short=short_name)
            config = {
                "keywords": keywords,
                "include_keywords": [],
                "exclude_keywords": ["招聘", "股吧", "二手", "下载", "百科"],
                "max_results": 20,
                "crawl_top_n": 20,
                "freshness": "noLimit",
                "enable_llm_filter": True,
                "filter_prompt": (
                    "请判断搜索结果是否与研发营销市场洞察相关，优先保留企业经营动态、新品、技术、专利、"
                    "渠道、价格、政策、招投标、合作、风险事件，过滤招聘、无关百科、纯广告和明显低质页面。"
                ),
                "llm_min_score": 0.45,
                "llm_failure_policy": "keep",
                "auto_review_mode": "high_confidence",
                "auto_review_min_confidence": 0.55,
                "auto_review_required_tags": [],
                "auto_review_intelligence_types": [],
                "auto_add_to_report_pool": True,
                "auto_report_folder": "期初真实运行素材池",
                "extra": {
                    "project_name": "期初真实运行",
                    "channel_name": plan["label"],
                    "platforms": [plan["source_type"]],
                    "search_need": f"{display_name}{plan['label']}监测",
                    "target_fields": ["标题", "来源", "发布时间", "摘要", "标签", "情感", "机会点", "风险点"],
                    "source_document": "期初运行脚本自动扩展",
                    "company_hint": display_name,
                    "sys_company_id": company.sys_company_id,
                },
            }
            existing = (await db.exec(select(InsightDataSource).where(InsightDataSource.source_code == source_code))).first()
            if existing:
                existing.is_deleted = 0
                existing.status = "enabled"
                existing.source_name = f"{short_name}-{plan['label']}"
                existing.source_type = plan["source_type"]
                existing.company_id = company.id
                existing.fetch_frequency = "manual"
                existing.fetch_config = config
                existing.visibility_scope = "assigned"
                existing.owner_user_id = user_id
                existing.update_by = str(user_id)
                updated += 1
            else:
                db.add(
                    InsightDataSource(
                        source_code=source_code,
                        source_name=f"{short_name}-{plan['label']}",
                        source_type=plan["source_type"],
                        company_id=company.id,
                        fetch_frequency="manual",
                        fetch_config=config,
                        owner_user_id=user_id,
                        visibility_scope="assigned",
                        status="enabled",
                        create_by=str(user_id),
                        update_by=str(user_id),
                    )
                )
                created += 1
    await db.commit()
    return created, updated


async def patch_fetch_config(
    db,
    *,
    max_results: int,
    crawl_top_n: int,
    keyword_limit: int,
    create_candidate_from_hits: bool,
) -> int:
    rows = list(
        (
            await db.exec(
                select(InsightDataSource).where(
                    InsightDataSource.is_deleted == 0,
                    InsightDataSource.status == "enabled",
                    InsightDataSource.source_type.notin_(["official_site", "web_page"]),
                )
            )
        ).all()
    )
    patched = 0
    for row in rows:
        config = dict(row.fetch_config or {})
        if keyword_limit > 0:
            keywords = config.get("keywords")
            if isinstance(keywords, list) and len(keywords) > keyword_limit:
                config["keywords"] = keywords[:keyword_limit]
        config["max_results"] = min(max(max_results, 1), 20)
        config["crawl_top_n"] = min(max(crawl_top_n, 0), 20)
        config.setdefault("freshness", "noLimit")
        config.setdefault("llm_failure_policy", "keep")
        config["enable_llm_filter"] = True
        config.setdefault(
            "filter_prompt",
            (
                "保留与食品饮料、功能糖、淀粉糖、植物蛋白、配料原料、竞对、客户新品、政策法规、"
                "专利技术、研发营销机会相关的公开信息；过滤验证码、图片搜索、百科泛信息、无业务价值页面和明显跨行业噪声。"
            ),
        )
        if create_candidate_from_hits:
            config["create_candidate_from_hits"] = True
        config.setdefault("auto_review_mode", "high_confidence")
        config["auto_review_min_confidence"] = min(float(config.get("auto_review_min_confidence") or 0.55), 0.75)
        config["auto_add_to_report_pool"] = True
        config.setdefault("auto_report_folder", "期初真实运行素材池")
        row.fetch_config = config
        patched += 1
    if patched:
        await db.commit()
    return patched


def _source_code(company_id: int, source_type: str, suffix: str) -> str:
    digest = sha1(f"{company_id}:{source_type}:{suffix}".encode("utf-8")).hexdigest()[:20]
    return f"boot_{digest}"


def _render_keywords(templates: list[str], *, name: str, short: str) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for template in templates:
        keyword = template.format(name=name, short=short).strip()
        if keyword and keyword not in seen:
            seen.add(keyword)
            result.append(keyword)
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed-files", nargs="*", default=[])
    parser.add_argument("--target", type=int, default=2000)
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--crawl-top-n", type=int, default=4)
    parser.add_argument("--max-results", type=int, default=20)
    parser.add_argument("--max-rounds", type=int, default=200)
    parser.add_argument("--user-id", type=int, default=1)
    parser.add_argument("--expand-company-sources", action="store_true")
    parser.add_argument("--expanded-source-limit", type=int, default=0)
    parser.add_argument("--patch-fetch-config", action="store_true")
    parser.add_argument("--quiet-logs", action="store_true")
    parser.add_argument("--per-source-timeout", type=int, default=240)
    parser.add_argument("--keyword-limit", type=int, default=0)
    parser.add_argument("--include-source-types", nargs="*", default=[])
    parser.add_argument("--exclude-source-types", nargs="*", default=[])
    parser.add_argument("--skip-source-ids", nargs="*", type=int, default=[])
    parser.add_argument("--subprocess-per-source", action="store_true")
    parser.add_argument("--max-source-failures", type=int, default=2)
    parser.add_argument("--single-source-id", type=int, default=0)
    parser.add_argument("--create-candidate-from-hits", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(run(parse_args()))
