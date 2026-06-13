import asyncio
from dataclasses import dataclass
from datetime import datetime

from sqlmodel import select

from app.db.session import async_session
from app.models.agent.insight import (
    InsightCandidateReviewStatus,
    InsightCompany,
    InsightDataSource,
    InsightIntelligence,
    InsightIntelligenceCandidate,
)
from app.models.system.sys_user import SysUser
from app.schemas.agent.insight.company import InsightCompanyCreate, InsightCompanyUpdate
from app.schemas.agent.insight.data_source import (
    InsightDataSourceCreate,
    InsightDataSourceExecuteRequest,
    InsightDataSourceFetchConfig,
    InsightDataSourceUpdate,
)
from app.schemas.agent.insight.intelligence import InsightCandidatePromoteRequest, InsightPoolUpsertRequest
from app.services.agent.insight.company_service import insight_company_service
from app.services.agent.insight.data_source_service import insight_data_source_service
from app.services.agent.insight.intelligence_service import insight_intelligence_service


@dataclass(slots=True)
class CompanySeed:
    code: str
    name: str
    short_name: str
    industry: str
    company_type: str
    region: str
    website: str | None
    monitor_level: str
    aliases: list[str]


@dataclass(slots=True)
class DataSourceRun:
    id: int
    name: str


COMPANIES = [
    CompanySeed(
        code="p1_chabaidao",
        name="四川百茶百道实业股份有限公司",
        short_name="茶百道",
        industry="新式茶饮",
        company_type="品牌/客户",
        region="四川成都",
        website="https://www.chabaidao.com/",
        monitor_level="key",
        aliases=["茶百道", "ChaPanda", "百茶百道"],
    ),
    CompanySeed(
        code="p1_mixue",
        name="蜜雪冰城股份有限公司",
        short_name="蜜雪冰城",
        industry="新式茶饮",
        company_type="品牌/客户",
        region="河南郑州",
        website="https://www.mxbc.com/",
        monitor_level="key",
        aliases=["蜜雪冰城", "蜜雪", "Mixue"],
    ),
    CompanySeed(
        code="p1_cocacola",
        name="可口可乐公司",
        short_name="可口可乐",
        industry="饮料",
        company_type="品牌/客户",
        region="美国/中国",
        website="https://www.coca-cola.com/",
        monitor_level="key",
        aliases=["可口可乐", "Coca-Cola", "Coke", "中粮可口可乐", "太古可口可乐"],
    ),
    CompanySeed(
        code="p1_byhealth",
        name="汤臣倍健股份有限公司",
        short_name="汤臣倍健",
        industry="膳食营养补充剂",
        company_type="品牌/客户",
        region="广东珠海",
        website="https://www.by-health.com/",
        monitor_level="key",
        aliases=["汤臣倍健", "BYHEALTH", "健力多"],
    ),
]


def keyword_groups(seed: CompanySeed) -> list[tuple[str, list[str], int]]:
    name = seed.short_name
    aliases = [item for item in seed.aliases if item != name][:2]
    return [
        (
            "综合资讯",
            [name, *aliases],
            12,
        ),
        (
            "经营新品与市场动态",
            [f"{name} 新品", f"{name} 合作", f"{name} 市场", f"{name} 中国"],
            10,
        ),
        (
            "招标招聘与组织信号",
            [f"{name} 招聘", f"{name} 招标", f"{name} 投资", f"{name} 供应链"],
            8,
        ),
    ]


LOW_QUALITY_MARKERS = [
    "example domain",
    "just a moment",
    "页面需要安全验证",
    "安全验证",
    "未提取到有效正文",
    "this domain is for use",
    "access denied",
    "forbidden",
]


async def main() -> None:
    setup = await setup_companies_and_sources()

    execution_summary = []
    for source in setup["data_sources"]:
        execution_summary.append(await execute_source(source, setup["user_id"]))

    async with async_session() as db:
        cleanup_after_stats = await cleanup_low_quality(db)
        promoted = await promote_report_materials(db, setup["company_ids"], setup["user_id"])
        totals = await collect_totals(db, setup["company_ids"])
        print(
            {
                "cleanup_before": setup["cleanup_before"],
                "cleanup_after": cleanup_after_stats,
                "companies": setup["companies"],
                "data_sources": len(setup["data_sources"]),
                "execution_summary": execution_summary,
                "promoted_report_materials": promoted,
                "totals": totals,
            }
        )


async def setup_companies_and_sources() -> dict:
    async with async_session() as db:
        user_id = await first_user_id(db)
        cleanup_stats = await cleanup_low_quality(db)
        companies = {}
        for seed in COMPANIES:
            companies[seed.code] = await upsert_company(db, seed, user_id)
        data_sources = []
        for seed in COMPANIES:
            company = companies[seed.code]
            for group_index, (group_name, keywords, crawl_top_n) in enumerate(keyword_groups(seed), start=1):
                source = await upsert_data_source(db, seed, company, group_index, group_name, keywords, crawl_top_n, user_id)
                if source.id:
                    data_sources.append(DataSourceRun(id=source.id, name=source.source_name))

        return {
            "user_id": user_id,
            "cleanup_before": cleanup_stats,
            "company_ids": [company.id for company in companies.values() if company.id],
            "companies": {seed.short_name: companies[seed.code].id for seed in COMPANIES},
            "data_sources": data_sources,
        }


async def execute_source(source: DataSourceRun, user_id: int) -> dict[str, int | str]:
    async with async_session() as db:
        try:
            result = await insight_data_source_service.execute_data_source(
                db,
                source.id,
                InsightDataSourceExecuteRequest(crawl_top_n=None),
                user_id,
            )
            hits = sum(len(item.hits) for item in result.search_results)
            crawled = sum(len(item.crawled_results) for item in result.search_results)
            candidates = sum(len(item.candidates) for item in result.search_results)
            return {
                "source": source.name,
                "hits": hits,
                "crawled": crawled,
                "candidates": candidates,
                "errors": len(result.execution_errors),
            }
        except Exception as exc:
            await db.rollback()
            return {"source": source.name, "error": str(exc)}


async def first_user_id(db) -> int:
    user = (await db.exec(select(SysUser).where(SysUser.is_deleted == 0).order_by(SysUser.id.asc()).limit(1))).first()
    return user.id if user and user.id else 1


async def upsert_company(db, seed: CompanySeed, user_id: int) -> InsightCompany:
    company = (await db.exec(select(InsightCompany).where(InsightCompany.company_code == seed.code))).first()
    payload = {
        "name": seed.name,
        "short_name": seed.short_name,
        "industry": seed.industry,
        "company_type": seed.company_type,
        "region": seed.region,
        "website": seed.website,
        "description": f"{seed.short_name} P1 企业档案测试样本，用于沉淀市场动态、经营信号、招聘招标和报告素材。",
        "monitor_level": seed.monitor_level,
        "profile_json": {
            "aliases": seed.aliases,
            "planned_external_channels": {
                "qixinbao": ["工商变更", "股权变化", "关联公司", "招投标"],
                "recruiting": ["招聘岗位", "组织扩张", "区域布局"],
                "internal_collaboration": ["合作项目", "客户拜访", "商机阶段"],
            },
        },
        "status": "active",
    }
    if company:
        await insight_company_service.update_company(db, company.id or 0, InsightCompanyUpdate(**payload), user_id)
        return await db.get(InsightCompany, company.id)
    created = await insight_company_service.create_company(db, InsightCompanyCreate(company_code=seed.code, **payload), user_id)
    return await db.get(InsightCompany, created.id)


async def upsert_data_source(
    db,
    seed: CompanySeed,
    company: InsightCompany,
    group_index: int,
    group_name: str,
    keywords: list[str],
    crawl_top_n: int,
    user_id: int,
) -> InsightDataSource:
    source_code = f"{seed.code}_p1_{group_index}"
    source = (await db.exec(select(InsightDataSource).where(InsightDataSource.source_code == source_code))).first()
    payload = {
        "source_name": f"{seed.short_name}-{group_name}",
        "source_type": "baidu_news",
        "base_url": None,
        "company_id": company.id,
        "fetch_frequency": "manual",
        "fetch_config": InsightDataSourceFetchConfig(
            keywords=keywords,
            exclude_keywords=["股票股吧", "同花顺", "东方财富", "无关招聘中介"],
            max_results=20,
            crawl_top_n=crawl_top_n,
            freshness="noLimit",
            schedule_type="manual",
            enable_llm_filter=False,
            filter_prompt="抓取正文后生成摘要、分类、标签和报告素材判断，搜索阶段不要提前丢弃结果。",
            extra={
                "p1_seed": True,
                "company_code": seed.code,
                "collection_scope": group_name,
                "future_channels": ["qixinbao", "recruiting", "internal_collaboration"],
            },
        ),
        "status": "enabled",
    }
    if source:
        await insight_data_source_service.update_data_source(db, source.id or 0, InsightDataSourceUpdate(**payload), user_id)
        return await db.get(InsightDataSource, source.id)
    created = await insight_data_source_service.create_data_source(
        db,
        InsightDataSourceCreate(source_code=source_code, **payload),
        user_id,
    )
    return await db.get(InsightDataSource, created.id)


async def cleanup_low_quality(db) -> dict[str, int]:
    deleted_candidates = 0
    deleted_intelligences = 0
    candidates = list(
        (
            await db.exec(
                select(InsightIntelligenceCandidate).where(
                    InsightIntelligenceCandidate.is_deleted == 0,
                )
            )
        ).all()
    )
    for candidate in candidates:
        if is_low_quality_text(candidate.candidate_title, candidate.candidate_summary, candidate.suggested_tags):
            candidate.is_deleted = 1
            candidate.status = "deleted"
            candidate.update_time = datetime.now()
            deleted_candidates += 1

    intelligences = list(
        (
            await db.exec(
                select(InsightIntelligence).where(
                    InsightIntelligence.is_deleted == 0,
                )
            )
        ).all()
    )
    for intelligence in intelligences:
        if is_low_quality_text(intelligence.title, intelligence.summary, intelligence.raw_payload):
            intelligence.is_deleted = 1
            intelligence.status = "deleted"
            intelligence.update_time = datetime.now()
            deleted_intelligences += 1
    await db.commit()
    return {"candidates": deleted_candidates, "intelligences": deleted_intelligences}


def is_low_quality_text(title: str | None, summary: str | None, payload: object) -> bool:
    text = f"{title or ''}\n{summary or ''}\n{payload or ''}".lower()
    if any(marker in text for marker in LOW_QUALITY_MARKERS):
        return True
    if "低质量正文" in text and "ignored" in text:
        return True
    return False


async def promote_report_materials(db, company_ids: list[int], user_id: int) -> dict[str, int]:
    promoted = 0
    pooled = 0
    for company_id in company_ids:
        candidates = list(
            (
                await db.exec(
                    select(InsightIntelligenceCandidate)
                    .where(
                        InsightIntelligenceCandidate.company_id == company_id,
                        InsightIntelligenceCandidate.is_deleted == 0,
                        InsightIntelligenceCandidate.review_status == InsightCandidateReviewStatus.PENDING,
                        InsightIntelligenceCandidate.confidence >= 0.35,
                    )
                    .order_by(InsightIntelligenceCandidate.confidence.desc(), InsightIntelligenceCandidate.create_time.desc())
                    .limit(120)
                )
            ).all()
        )
        for candidate in candidates:
            if is_low_quality_text(candidate.candidate_title, candidate.candidate_summary, candidate.suggested_tags):
                continue
            response = await insight_intelligence_service.promote_candidate(
                db,
                candidate.id,
                InsightCandidatePromoteRequest(
                    review_comment="P1 批量测试：高置信候选自动转正式情报，便于报告素材验证。",
                    visibility_scope="public",
                    importance_level="medium",
                ),
                user_id,
                is_admin=True,
            )
            promoted += 1
            if response.intelligence and response.intelligence.id:
                await insight_intelligence_service.upsert_user_pool(
                    db,
                    response.intelligence.id,
                    InsightPoolUpsertRequest(
                        pool_type="report_material",
                        folder_name="P1企业档案测试素材",
                        note="P1 批量采集自动加入，供报告草稿验证。",
                    ),
                    user_id=user_id,
                )
                pooled += 1
    return {"promoted": promoted, "report_materials": pooled}


async def collect_totals(db, company_ids: list[int]) -> dict[str, int]:
    candidates = (
        await db.exec(
            select(InsightIntelligenceCandidate).where(
                InsightIntelligenceCandidate.company_id.in_(company_ids),
                InsightIntelligenceCandidate.is_deleted == 0,
            )
        )
    ).all()
    intelligences = (
        await db.exec(
            select(InsightIntelligence).where(
                InsightIntelligence.company_id.in_(company_ids),
                InsightIntelligence.is_deleted == 0,
            )
        )
    ).all()
    return {
        "company_candidates": len(candidates),
        "company_intelligences": len(intelligences),
        "pending_candidates": sum(1 for item in candidates if item.review_status == InsightCandidateReviewStatus.PENDING),
    }


if __name__ == "__main__":
    asyncio.run(main())
