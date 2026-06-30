"""Insight AI 自动评审、情报资产、RAG 和图谱烟测。"""

import asyncio
import json
from datetime import datetime
from uuid import uuid4

from langchain_core.messages import AIMessage
from sqlmodel import select

from app.core.llm_factory import LLMFactory
from app.core.logger import logger
from app.db.session import async_session
from app.models.agent.insight import (
    InsightCandidateReviewStatus,
    InsightCrawlerChannel,
    InsightCrawlResult,
    InsightCrawlStatus,
    InsightAssetVector,
    InsightGraphEdge,
    InsightGraphNode,
    InsightIntelligence,
    InsightIntelligenceAsset,
    InsightIntelligenceCandidate,
    InsightIntelligenceSource,
    InsightReviewRecord,
    InsightSubjectType,
    InsightTask,
    InsightTaskStatus,
)
from app.schemas.agent.insight.asset import InsightAssetSearchRequest
from app.services.agent.insight.ai_review_service import insight_ai_review_service
from app.services.agent.insight.asset_service import insight_asset_service


async def _fake_safe_invoke(*args, **kwargs):
    _ = args, kwargs
    return AIMessage(
        content=json.dumps(
            {
                "decision": "formal",
                "score": 0.88,
                "reason": "涉及客户新品扩张，可能带来配料需求",
                "intelligence_type": "新品情报",
                "business_value": "销售机会",
                "related_products": ["植物蛋白", "低糖配料"],
                "opportunities": ["销售可跟进低糖配料方案"],
                "risks": [],
                "entities": ["测试客户", "植物蛋白新品"],
                "evidence": "测试客户发布植物蛋白新品，并计划扩展低糖配料应用。",
            },
            ensure_ascii=False,
        )
    )


async def main() -> None:
    original_safe_invoke = LLMFactory.safe_invoke
    LLMFactory.safe_invoke = staticmethod(_fake_safe_invoke)
    created_rows: list[object] = []
    try:
        async with async_session() as db:
            suffix = uuid4().hex[:8]
            task = InsightTask(
                task_uid=f"smoke_asset_{suffix}",
                task_type="asset_ai_review_smoke",
                status=InsightTaskStatus.SUCCESS,
                progress=100,
                started_at=datetime.now(),
                finished_at=datetime.now(),
                input_payload={"smoke": True},
            )
            db.add(task)
            await db.flush()
            crawl = InsightCrawlResult(
                task_id=task.id or 0,
                channel=InsightCrawlerChannel.BAIDU_NEWS,
                query_text="测试客户 植物蛋白 新品",
                source_url=f"https://example.com/insight-smoke-{suffix}",
                source_title="测试客户发布植物蛋白新品",
                snippet="测试客户发布植物蛋白新品，并计划扩展低糖配料应用。",
                markdown_content="测试客户发布植物蛋白新品，并计划扩展低糖配料应用。该信息对研发营销有销售机会参考价值。",
                published_at=datetime.now(),
                dedupe_hash=f"smoke-{suffix}",
                crawl_metadata={"smoke": True},
                status=InsightCrawlStatus.PARSED,
            )
            db.add(crawl)
            await db.flush()
            candidate = InsightIntelligenceCandidate(
                crawl_result_id=crawl.id or 0,
                candidate_title="测试客户发布植物蛋白新品",
                candidate_summary="测试客户发布植物蛋白新品，并计划扩展低糖配料应用。",
                subject_type=InsightSubjectType.COMPANY,
                subject_name="测试客户",
                intelligence_type="新品情报",
                suggested_tags=[{"name": "烟测", "source": "smoke"}],
                confidence=0.72,
                review_status=InsightCandidateReviewStatus.PENDING,
                status="active",
            )
            db.add(candidate)
            await db.commit()
            await db.refresh(candidate)

            review = await insight_ai_review_service.review_candidate(
                db,
                candidate.id or 0,
                user_id=None,
                is_admin=True,
            )
            if review.decision.decision != "formal" or not review.intelligence_id:
                raise AssertionError(f"AI 自动评审未转正式情报: {review.model_dump()}")
            if not review.asset_id:
                raise AssertionError("AI 自动评审未生成资产")

            search = await insight_asset_service.search_assets(
                db,
                InsightAssetSearchRequest(query="植物蛋白 低糖配料 销售机会", top_k=3),
                user_id=None,
                is_admin=True,
            )
            if not search.hits:
                raise AssertionError("资产 RAG 未召回结果")

            graph = await insight_asset_service.graph(db, user_id=None, is_admin=True, asset_id=review.asset_id)
            if not graph.nodes or not graph.edges:
                raise AssertionError("资产图谱未生成节点或边")

            asset = await db.get(InsightIntelligenceAsset, review.asset_id)
            logger.info(
                "Insight 资产烟测通过: candidate_id={}, intelligence_id={}, asset_id={}, embedding_status={}, rag_hits={}, graph_nodes={}, graph_edges={}",
                candidate.id,
                review.intelligence_id,
                review.asset_id,
                asset.embedding_status if asset else None,
                len(search.hits),
                len(graph.nodes),
                len(graph.edges),
            )

            created_rows.extend([task, crawl, candidate])
            if review.intelligence_id:
                intelligence = await db.get(InsightIntelligence, review.intelligence_id)
                created_rows.append(intelligence)
                sources = list((await db.exec(select(InsightIntelligenceSource).where(InsightIntelligenceSource.intelligence_id == review.intelligence_id))).all())
                review_records = list((await db.exec(select(InsightReviewRecord).where(InsightReviewRecord.intelligence_id == review.intelligence_id))).all())
                created_rows.extend(sources)
                created_rows.extend(review_records)
            if review.asset_id:
                created_rows.append(asset)
                vectors = list((await db.exec(select(InsightAssetVector).where(InsightAssetVector.asset_id == review.asset_id))).all())
                nodes = list((await db.exec(select(InsightGraphNode).where(InsightGraphNode.source_asset_id == review.asset_id))).all())
                edges = list((await db.exec(select(InsightGraphEdge).where(InsightGraphEdge.source_asset_id == review.asset_id))).all())
                created_rows.extend([*vectors, *nodes, *edges])
            for row in created_rows:
                if row is not None:
                    row.is_deleted = 1
                    row.update_time = datetime.now()
            await db.commit()
    finally:
        LLMFactory.safe_invoke = original_safe_invoke


if __name__ == "__main__":
    asyncio.run(main())
