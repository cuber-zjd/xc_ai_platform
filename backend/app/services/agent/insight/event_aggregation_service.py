import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from hashlib import sha1
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import or_
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.logger import logger
from app.models.agent.insight import (
    InsightAssetVector,
    InsightCandidateReviewStatus,
    InsightCrawlResult,
    InsightIntelligence,
    InsightIntelligenceAsset,
    InsightIntelligenceCandidate,
    InsightIntelligenceSource,
    InsightReviewRecord,
)
from app.services.agent.insight.embedding_service import insight_embedding_service


@dataclass(slots=True)
class EventAggregationResult:
    intelligence: InsightIntelligence
    source: InsightIntelligenceSource | None
    method: str
    score: float


class InsightEventAggregationService:
    """把多平台对同一事件的报道归并到一条正式情报。"""

    lookback_days = 10
    deterministic_title_threshold = 0.90
    combined_title_threshold = 0.78
    combined_summary_threshold = 0.70
    vector_threshold = 0.94
    action_groups = {
        "product": {"新品", "发布", "推出", "上市", "首发", "上新"},
        "capacity": {"扩产", "投产", "产能", "项目开工", "项目投建", "生产基地"},
        "price": {"涨价", "降价", "提价", "价格", "报价", "调价"},
        "finance": {"融资", "并购", "收购", "投资", "上市", "募资", "增资"},
        "cooperation": {"合作", "签约", "战略协议", "供应商", "客户合作"},
        "policy": {"政策", "法规", "监管", "标准", "征求意见", "公告"},
        "risk": {"处罚", "召回", "投诉", "风险", "亏损", "停产", "事故"},
        "technology": {"专利", "技术", "研发", "成果", "工艺"},
        "personnel": {"任命", "辞任", "董事长", "总经理", "高管", "法定代表人"},
    }

    async def try_merge_candidate(
        self,
        db: AsyncSession,
        candidate: InsightIntelligenceCandidate,
        crawl_result: InsightCrawlResult,
        *,
        user_id: int | None,
    ) -> EventAggregationResult | None:
        if candidate.review_status != InsightCandidateReviewStatus.PENDING:
            return None
        candidates = await self._recent_intelligences(db, candidate, crawl_result)
        if not candidates:
            return None

        best: tuple[InsightIntelligence, str, float] | None = None
        borderline: list[tuple[InsightIntelligence, float, float]] = []
        for intelligence in candidates:
            if not self._within_event_window(crawl_result, intelligence):
                continue
            if not self._compatible_subject(candidate, intelligence):
                continue
            if not self._compatible_actions(
                self._join(candidate.candidate_title, candidate.candidate_summary),
                self._join(intelligence.title, intelligence.summary),
            ):
                continue
            title_score = self._text_similarity(candidate.candidate_title, intelligence.title)
            summary_score = self._text_similarity(candidate.candidate_summary, intelligence.summary)
            normalized_title = self._normalize(candidate.candidate_title)
            normalized_existing = self._normalize(intelligence.title)
            if len(normalized_title) >= 10 and normalized_title == normalized_existing:
                score = 0.995
                method = "normalized_title"
            elif title_score >= self.deterministic_title_threshold:
                score = title_score
                method = "title_similarity"
            elif title_score >= self.combined_title_threshold and summary_score >= self.combined_summary_threshold:
                score = title_score * 0.6 + summary_score * 0.4
                method = "title_summary_similarity"
            else:
                if title_score >= 0.62 and summary_score >= 0.58:
                    borderline.append((intelligence, title_score, summary_score))
                continue
            if best is None or score > best[2]:
                best = (intelligence, method, score)

        if best is None and borderline:
            vector_match = await self._vector_match(db, candidate, borderline)
            if vector_match:
                best = vector_match
        if best is None:
            return None
        intelligence, method, score = best
        return await self._merge(db, candidate, crawl_result, intelligence, method=method, score=score, user_id=user_id)

    async def _recent_intelligences(
        self,
        db: AsyncSession,
        candidate: InsightIntelligenceCandidate,
        crawl_result: InsightCrawlResult,
    ) -> list[InsightIntelligence]:
        reference_time = crawl_result.published_at or crawl_result.create_time or datetime.now()
        cutoff = reference_time - timedelta(days=self.lookback_days)
        filters: list[Any] = [
            InsightIntelligence.is_deleted == 0,
            InsightIntelligence.status == "active",
            or_(InsightIntelligence.publish_time >= cutoff, InsightIntelligence.create_time >= cutoff),
        ]
        if candidate.company_id:
            filters.append(InsightIntelligence.company_id == candidate.company_id)
        else:
            filters.append(InsightIntelligence.company_id == None)  # noqa: E711
        return list(
            (
                await db.exec(
                    select(InsightIntelligence)
                    .where(*filters)
                    .order_by(InsightIntelligence.publish_time.desc().nullslast(), InsightIntelligence.id.desc())
                    .limit(150)
                )
            ).all()
        )

    async def _vector_match(
        self,
        db: AsyncSession,
        candidate: InsightIntelligenceCandidate,
        borderline: list[tuple[InsightIntelligence, float, float]],
    ) -> tuple[InsightIntelligence, str, float] | None:
        intelligence_by_id = {item.id: item for item, _, _ in borderline if item.id}
        if not intelligence_by_id:
            return None
        rows = list(
            (
                await db.exec(
                    select(InsightIntelligenceAsset, InsightAssetVector)
                    .join(InsightAssetVector, InsightAssetVector.asset_id == InsightIntelligenceAsset.id)
                    .where(
                        InsightIntelligenceAsset.intelligence_id.in_(intelligence_by_id),
                        InsightIntelligenceAsset.is_deleted == 0,
                        InsightAssetVector.is_deleted == 0,
                        InsightAssetVector.status == "indexed",
                    )
                )
            ).all()
        )
        if not rows:
            return None
        vector, _ = await insight_embedding_service.embed_text(
            db,
            self._join(candidate.candidate_title, candidate.candidate_summary),
        )
        if not vector:
            return None
        best: tuple[InsightIntelligence, str, float] | None = None
        for asset, stored_vector in rows:
            intelligence = intelligence_by_id.get(asset.intelligence_id)
            if not intelligence:
                continue
            score = insight_embedding_service.cosine_similarity(vector, stored_vector.vector)
            if score >= self.vector_threshold and (best is None or score > best[2]):
                best = (intelligence, "semantic_vector", score)
        return best

    async def _merge(
        self,
        db: AsyncSession,
        candidate: InsightIntelligenceCandidate,
        crawl_result: InsightCrawlResult,
        intelligence: InsightIntelligence,
        *,
        method: str,
        score: float,
        user_id: int | None,
    ) -> EventAggregationResult:
        existing_source = (
            await db.exec(
                select(InsightIntelligenceSource).where(
                    InsightIntelligenceSource.intelligence_id == intelligence.id,
                    InsightIntelligenceSource.source_url == crawl_result.source_url,
                    InsightIntelligenceSource.is_deleted == 0,
                )
            )
        ).first()
        source = existing_source
        if source is None:
            source = InsightIntelligenceSource(
                intelligence_id=intelligence.id or 0,
                data_source_id=crawl_result.data_source_id,
                source_type=self._enum_value(crawl_result.channel),
                source_url=crawl_result.source_url,
                source_title=crawl_result.source_title,
                source_publish_time=crawl_result.published_at,
                content_excerpt=crawl_result.snippet,
                credibility_score=self._credibility_score(crawl_result.source_url),
                source_metadata=(crawl_result.crawl_metadata or {})
                | {
                    "event_aggregation": {
                        "candidate_id": candidate.id,
                        "method": method,
                        "score": round(score, 4),
                    }
                },
            )
            db.add(source)

        from_status = candidate.review_status.value
        candidate.review_status = InsightCandidateReviewStatus.PROMOTED
        candidate.promoted_intelligence_id = intelligence.id
        candidate.update_time = datetime.now()
        raw_payload = dict(intelligence.raw_payload or {})
        aggregation = dict(raw_payload.get("event_aggregation") or {})
        merged_ids = [int(item) for item in aggregation.get("merged_candidate_ids") or [] if str(item).isdigit()]
        if candidate.id and candidate.id not in merged_ids:
            merged_ids.append(candidate.id)
        aggregation.update(
            {
                "event_key": aggregation.get("event_key") or self._event_key(intelligence),
                "merged_candidate_ids": merged_ids[-200:],
                "last_merge_method": method,
                "last_merge_score": round(score, 4),
                "last_merged_at": datetime.now().isoformat(),
            }
        )
        raw_payload["event_aggregation"] = aggregation
        intelligence.raw_payload = raw_payload
        if crawl_result.published_at and (
            intelligence.publish_time is None or crawl_result.published_at < intelligence.publish_time
        ):
            intelligence.publish_time = crawl_result.published_at
        intelligence.update_time = datetime.now()
        db.add(
            InsightReviewRecord(
                intelligence_id=intelligence.id,
                candidate_id=candidate.id,
                review_user_id=user_id,
                from_status=from_status,
                to_status=InsightCandidateReviewStatus.PROMOTED.value,
                review_comment=f"自动归并到同一事件：{method}，相似度 {score:.2%}",
                diff_json={
                    "action": "merge_event_source",
                    "method": method,
                    "score": round(score, 4),
                    "source_url": crawl_result.source_url,
                },
            )
        )
        await db.commit()
        await db.refresh(candidate)
        await db.refresh(intelligence)
        if source and source.id is None:
            await db.refresh(source)
        logger.info(
            "Insight 多源事件归并完成：candidate_id={} intelligence_id={} method={} score={:.4f}",
            candidate.id,
            intelligence.id,
            method,
            score,
        )
        return EventAggregationResult(intelligence=intelligence, source=source, method=method, score=score)

    def _compatible_subject(
        self,
        candidate: InsightIntelligenceCandidate,
        intelligence: InsightIntelligence,
    ) -> bool:
        if candidate.company_id or intelligence.company_id:
            return candidate.company_id == intelligence.company_id
        left = self._normalize(candidate.subject_name)
        right = self._normalize(intelligence.subject_name)
        return not left or not right or left == right or left in right or right in left

    def _within_event_window(
        self,
        crawl_result: InsightCrawlResult,
        intelligence: InsightIntelligence,
    ) -> bool:
        left = crawl_result.published_at or crawl_result.create_time
        right = intelligence.publish_time or intelligence.create_time
        if not left or not right:
            return True
        return abs((left - right).total_seconds()) <= self.lookback_days * 86400

    def _compatible_actions(self, left: str, right: str) -> bool:
        left_actions = self._actions(left)
        right_actions = self._actions(right)
        return not left_actions or not right_actions or bool(left_actions.intersection(right_actions))

    def _actions(self, text: str) -> set[str]:
        return {
            group
            for group, keywords in self.action_groups.items()
            if any(keyword in text for keyword in keywords)
        }

    def _text_similarity(self, left: str | None, right: str | None) -> float:
        normalized_left = self._normalize(left)
        normalized_right = self._normalize(right)
        if not normalized_left or not normalized_right:
            return 0.0
        sequence = SequenceMatcher(None, normalized_left, normalized_right).ratio()
        left_grams = self._ngrams(normalized_left)
        right_grams = self._ngrams(normalized_right)
        jaccard = len(left_grams.intersection(right_grams)) / max(len(left_grams.union(right_grams)), 1)
        return sequence * 0.65 + jaccard * 0.35

    def _normalize(self, value: str | None) -> str:
        text = str(value or "").lower().strip()
        text = re.sub(r"^(?:重磅|最新|突发|快讯|独家|关注)[：:丨|\s]+", "", text)
        text = re.sub(r"(?:[-_|丨]\s*)?(?:人民网|新华网|中新网|证券时报|证券日报|新浪财经|腾讯新闻|搜狐网|网易新闻|今日头条)$", "", text)
        text = re.sub(r"\b(?:http|https|www)\S+", "", text)
        return re.sub(r"[^\w\u4e00-\u9fff]", "", text)

    def _ngrams(self, value: str, size: int = 3) -> set[str]:
        if len(value) <= size:
            return {value}
        return {value[index : index + size] for index in range(len(value) - size + 1)}

    def _credibility_score(self, url: str | None) -> float:
        host = urlparse(url or "").hostname or ""
        if host.endswith(".gov.cn") or host.endswith("gov.cn"):
            return 0.98
        if any(domain in host for domain in ("sse.com.cn", "szse.cn", "bse.cn", "cnipa.gov.cn")):
            return 0.96
        if any(domain in host for domain in ("xinhuanet.com", "people.com.cn", "cctv.com", "ce.cn")):
            return 0.90
        return 0.72

    def _event_key(self, intelligence: InsightIntelligence) -> str:
        raw = f"{intelligence.company_id or 0}:{self._normalize(intelligence.title)}"
        return sha1(raw.encode("utf-8")).hexdigest()

    def _join(self, *values: str | None) -> str:
        return "\n".join(str(value).strip() for value in values if value and str(value).strip())

    def _enum_value(self, value: Any) -> str:
        return str(getattr(value, "value", value) or "unknown")


insight_event_aggregation_service = InsightEventAggregationService()
