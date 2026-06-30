import re
from datetime import datetime
from hashlib import sha1
from typing import Any
from uuid import uuid4

from sqlalchemy import String, cast, exists, func, or_
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.agent.insight import (
    InsightAssetVector,
    InsightCandidateReviewStatus,
    InsightCrawlResult,
    InsightGraphEdge,
    InsightGraphNode,
    InsightIntelligence,
    InsightIntelligenceAsset,
    InsightIntelligenceCandidate,
    InsightIntelligenceSource,
    InsightVisibilityScope,
)
from app.schemas.agent.insight.asset import (
    InsightAssetRead,
    InsightAssetSearchHit,
    InsightAssetSearchRequest,
    InsightAssetSearchResponse,
    InsightFormalAssetBackfillRequest,
    InsightFormalAssetBackfillResponse,
    InsightGraphEdgeRead,
    InsightGraphNodeRead,
    InsightGraphResponse,
)
from app.services.agent.insight.embedding_service import insight_embedding_service
from app.services.agent.insight.permission_service import insight_permission_service


class InsightAssetService:
    """情报资产层：资产化、向量化、RAG 检索和轻量图谱。"""

    async def upsert_candidate_asset(
        self,
        db: AsyncSession,
        candidate: InsightIntelligenceCandidate,
        crawl_result: InsightCrawlResult | None = None,
        *,
        review_payload: dict[str, Any] | None = None,
    ) -> InsightIntelligenceAsset:
        if crawl_result is None:
            crawl_result = await db.get(InsightCrawlResult, candidate.crawl_result_id)
        existing = (
            await db.exec(
                select(InsightIntelligenceAsset).where(
                    InsightIntelligenceAsset.candidate_id == candidate.id,
                    InsightIntelligenceAsset.is_deleted == 0,
                )
            )
        ).first()
        tags = candidate.suggested_tags if isinstance(candidate.suggested_tags, list) else []
        ai_payload = self._extract_ai_payload(tags, review_payload)
        asset = existing or InsightIntelligenceAsset(asset_uid=f"asset_{uuid4().hex}", source_kind="candidate")
        asset.asset_type = self._asset_type_from_candidate(candidate)
        asset.source_kind = "candidate"
        asset.candidate_id = candidate.id
        asset.crawl_result_id = candidate.crawl_result_id
        asset.data_source_id = crawl_result.data_source_id if crawl_result else None
        asset.company_id = candidate.company_id
        asset.subject_type = candidate.subject_type
        asset.subject_name = candidate.subject_name
        asset.title = candidate.candidate_title
        asset.summary = candidate.candidate_summary
        asset.evidence_text = self._asset_text(candidate.candidate_title, candidate.candidate_summary, crawl_result)
        asset.source_url = crawl_result.source_url if crawl_result else None
        asset.source_title = crawl_result.source_title if crawl_result else None
        asset.source_channel = crawl_result.channel.value if crawl_result else None
        asset.publish_time = crawl_result.published_at if crawl_result else None
        asset.intelligence_type = candidate.intelligence_type
        asset.business_value = ai_payload.get("business_value")
        asset.importance_level = self._importance_from_score(candidate.confidence)
        asset.sentiment = str(ai_payload.get("sentiment") or "neutral")
        asset.confidence = candidate.confidence
        asset.tags = tags
        asset.entities = self._entity_payload(ai_payload.get("entities"))
        asset.opportunities = self._string_items(ai_payload.get("opportunities"))
        asset.risks = self._string_items(ai_payload.get("risks"))
        asset.keywords = self._keywords(candidate.candidate_title, candidate.candidate_summary, tags)
        asset.structured_payload = ai_payload
        asset.review_payload = review_payload
        asset.visibility_scope = InsightVisibilityScope.ASSIGNED
        asset.owner_user_id = self._int_or_none(candidate.create_by)
        asset.status = "active"
        asset.update_time = datetime.now()
        if existing is None:
            db.add(asset)
        await db.flush()
        await self.index_asset(db, asset)
        await self.upsert_graph(db, asset)
        return asset

    async def upsert_intelligence_asset(
        self,
        db: AsyncSession,
        intelligence: InsightIntelligence,
        sources: list[InsightIntelligenceSource] | None = None,
        *,
        review_payload: dict[str, Any] | None = None,
    ) -> InsightIntelligenceAsset:
        sources = sources if sources is not None else list((await db.exec(
            select(InsightIntelligenceSource).where(
                InsightIntelligenceSource.intelligence_id == intelligence.id,
                InsightIntelligenceSource.is_deleted == 0,
            ).order_by(InsightIntelligenceSource.create_time.asc())
        )).all())
        primary_source = sources[0] if sources else None
        existing = (
            await db.exec(
                select(InsightIntelligenceAsset).where(
                    InsightIntelligenceAsset.intelligence_id == intelligence.id,
                    InsightIntelligenceAsset.is_deleted == 0,
                )
            )
        ).first()
        raw_payload = intelligence.raw_payload if isinstance(intelligence.raw_payload, dict) else {}
        tags = raw_payload.get("suggested_tags") if isinstance(raw_payload.get("suggested_tags"), list) else []
        ai_payload = self._extract_ai_payload(tags, raw_payload.get("ai_review") or review_payload)
        asset = existing or InsightIntelligenceAsset(asset_uid=f"asset_{uuid4().hex}", source_kind="intelligence")
        asset.asset_type = "formal"
        asset.source_kind = "intelligence"
        asset.intelligence_id = intelligence.id
        asset.data_source_id = intelligence.data_source_id or (primary_source.data_source_id if primary_source else None)
        asset.company_id = intelligence.company_id
        asset.subject_type = intelligence.subject_type
        asset.subject_id = intelligence.subject_id
        asset.subject_name = intelligence.subject_name
        asset.title = intelligence.title
        asset.summary = intelligence.summary
        asset.evidence_text = self._join_text(intelligence.title, intelligence.summary, intelligence.content, primary_source.content_excerpt if primary_source else None)
        asset.source_url = primary_source.source_url if primary_source else None
        asset.source_title = primary_source.source_title if primary_source else None
        asset.source_channel = primary_source.source_type if primary_source else None
        asset.publish_time = intelligence.publish_time
        asset.intelligence_type = intelligence.intelligence_type
        asset.business_value = ai_payload.get("business_value")
        asset.importance_level = intelligence.importance_level
        asset.sentiment = intelligence.sentiment
        asset.confidence = self._float_value(ai_payload.get("score"), 0.85)
        asset.tags = tags
        asset.entities = self._entity_payload(ai_payload.get("entities"))
        asset.opportunities = self._string_items(ai_payload.get("opportunities"))
        asset.risks = self._string_items(ai_payload.get("risks"))
        asset.keywords = self._keywords(intelligence.title, intelligence.summary, tags)
        asset.structured_payload = ai_payload
        asset.review_payload = raw_payload.get("ai_review") or review_payload
        asset.visibility_scope = intelligence.visibility_scope
        asset.owner_user_id = intelligence.owner_user_id
        asset.status = intelligence.status
        asset.update_time = datetime.now()
        if existing is None:
            db.add(asset)
        await db.flush()
        await self.index_asset(db, asset)
        await self.upsert_graph(db, asset)
        return asset

    async def index_asset(self, db: AsyncSession, asset: InsightIntelligenceAsset) -> None:
        text = self._join_text(asset.title, asset.summary, asset.evidence_text)
        content_hash = insight_embedding_service.content_hash(text)
        existing = (
            await db.exec(
                select(InsightAssetVector).where(
                    InsightAssetVector.asset_id == asset.id,
                    InsightAssetVector.vector_scope == "summary",
                    InsightAssetVector.content_hash == content_hash,
                    InsightAssetVector.is_deleted == 0,
                )
            )
        ).first()
        if existing:
            asset.embedding_status = "indexed"
            return
        vector, metadata = await insight_embedding_service.embed_text(db, text)
        if not vector:
            asset.embedding_status = "failed"
            asset.structured_payload = (asset.structured_payload or {}) | {"embedding_error": metadata}
            return
        old_vectors = await db.exec(
            select(InsightAssetVector).where(
                InsightAssetVector.asset_id == asset.id,
                InsightAssetVector.vector_scope == "summary",
                InsightAssetVector.is_deleted == 0,
            )
        )
        for row in old_vectors.all():
            row.is_deleted = 1
            row.update_time = datetime.now()
        db.add(
            InsightAssetVector(
                asset_id=asset.id or 0,
                vector_uid=f"vec_{uuid4().hex}",
                vector_scope="summary",
                embedding_model=str(metadata.get("model") or insight_embedding_service.default_model_code),
                dimension=len(vector),
                content_hash=content_hash,
                vector=vector,
                vector_metadata=metadata,
                status="indexed",
            )
        )
        asset.embedding_status = "indexed"

    async def backfill_formal_assets(
        self,
        db: AsyncSession,
        payload: InsightFormalAssetBackfillRequest,
        *,
        user_id: int | None,
    ) -> InsightFormalAssetBackfillResponse:
        filters = self._formal_backfill_filters(include_inactive=payload.include_inactive)
        rows = list(
            (
                await db.exec(
                    select(InsightIntelligence)
                    .where(*filters)
                    .order_by(InsightIntelligence.publish_time.desc().nullslast(), InsightIntelligence.id.desc())
                    .limit(payload.limit)
                )
            ).all()
        )
        source_map = await self._source_map_for_intelligences(db, [row.id for row in rows if row.id])
        response = InsightFormalAssetBackfillResponse(requested_limit=payload.limit, scanned_count=len(rows))
        for row in rows:
            row_id = row.id
            row_title = row.title
            before_asset = (
                await db.exec(
                    select(InsightIntelligenceAsset).where(
                        InsightIntelligenceAsset.intelligence_id == row_id,
                        InsightIntelligenceAsset.is_deleted == 0,
                    )
                )
            ).first()
            try:
                row.update_by = str(user_id) if user_id else row.update_by
                asset = await self.upsert_intelligence_asset(db, row, source_map.get(row.id or 0, []))
                await db.commit()
                await db.refresh(asset)
                if before_asset is None:
                    response.created_count += 1
                else:
                    response.updated_count += 1
                if asset.embedding_status == "indexed":
                    response.indexed_count += 1
                elif asset.embedding_status == "failed":
                    response.failed_count += 1
                response.items.append(
                    {
                        "intelligence_id": row_id,
                        "asset_id": asset.id,
                        "title": row_title,
                        "asset_created": before_asset is None,
                        "embedding_status": asset.embedding_status,
                        "graph_status": asset.graph_status,
                    }
                )
            except Exception as exc:
                await db.rollback()
                response.failed_count += 1
                response.items.append(
                    {
                        "intelligence_id": row_id,
                        "title": row_title,
                        "error": str(exc)[:500],
                    }
                )
        response.remaining_count = await self.count_formal_assets_remaining(db, include_inactive=payload.include_inactive)
        return response

    async def count_formal_assets_remaining(self, db: AsyncSession, *, include_inactive: bool = False) -> int:
        return (
            await db.exec(
                select(func.count())
                .select_from(InsightIntelligence)
                .where(*self._formal_backfill_filters(include_inactive=include_inactive))
            )
        ).one()

    async def search_assets(
        self,
        db: AsyncSession,
        payload: InsightAssetSearchRequest,
        *,
        user_id: int | None,
        is_admin: bool,
    ) -> InsightAssetSearchResponse:
        query_vector, vector_meta = await insight_embedding_service.embed_text(db, payload.query)
        filters = [InsightIntelligenceAsset.is_deleted == 0, InsightIntelligenceAsset.status == "active"]
        if not payload.include_candidates:
            filters.append(InsightIntelligenceAsset.asset_type == "formal")
        if payload.company_id:
            filters.append(InsightIntelligenceAsset.company_id == payload.company_id)
        if payload.subject_type:
            filters.append(InsightIntelligenceAsset.subject_type == payload.subject_type)
        if payload.intelligence_type:
            filters.append(InsightIntelligenceAsset.intelligence_type == payload.intelligence_type)
        if payload.date_from:
            filters.append(InsightIntelligenceAsset.publish_time >= payload.date_from)
        if payload.date_to:
            filters.append(InsightIntelligenceAsset.publish_time <= payload.date_to)
        keyword = payload.query.strip()
        if not query_vector and keyword:
            like = f"%{keyword}%"
            filters.append(
                or_(
                    InsightIntelligenceAsset.title.ilike(like),
                    InsightIntelligenceAsset.summary.ilike(like),
                    cast(InsightIntelligenceAsset.keywords, String).ilike(like),
                )
            )
        if not is_admin:
            filters.append(
                await insight_permission_service.visibility_filter_for_user(
                    db,
                    InsightIntelligenceAsset,
                    target_type="asset",
                    user_id=user_id,
                    is_admin=is_admin,
                )
            )
        assets = list((await db.exec(select(InsightIntelligenceAsset).where(*filters).limit(300))).all())
        vector_map = await self._vector_map(db, [asset.id for asset in assets if asset.id])
        hits: list[InsightAssetSearchHit] = []
        for asset in assets:
            vector_score = None
            if query_vector and asset.id in vector_map:
                vector_score = insight_embedding_service.cosine_similarity(query_vector, vector_map[asset.id].vector)
            keyword_score = self._keyword_score(payload.query, asset)
            score = max(vector_score or 0, keyword_score)
            if score <= 0:
                continue
            hits.append(
                InsightAssetSearchHit(
                    asset=self._to_asset_read(asset),
                    score=round(score, 6),
                    vector_score=round(vector_score, 6) if vector_score is not None else None,
                    keyword_score=round(keyword_score, 6),
                    match_reason="向量召回" if vector_score and vector_score >= keyword_score else "关键词召回",
                )
            )
        hits.sort(key=lambda item: item.score, reverse=True)
        mode = "asset_vector_rag" if query_vector else f"asset_keyword_rag:{vector_meta.get('reason')}"
        return InsightAssetSearchResponse(query=payload.query, hits=hits[: payload.top_k], generation_mode=mode)

    async def graph(
        self,
        db: AsyncSession,
        *,
        user_id: int | None,
        is_admin: bool,
        company_id: int | None = None,
        asset_id: int | None = None,
        limit: int = 80,
    ) -> InsightGraphResponse:
        node_filters = [InsightGraphNode.is_deleted == 0, InsightGraphNode.status == "active"]
        edge_filters = [InsightGraphEdge.is_deleted == 0, InsightGraphEdge.status == "active"]
        asset_filters = [InsightIntelligenceAsset.is_deleted == 0, InsightIntelligenceAsset.status == "active"]
        if company_id:
            asset_filters.append(InsightIntelligenceAsset.company_id == company_id)
        if asset_id:
            asset_filters.append(InsightIntelligenceAsset.id == asset_id)
        if not is_admin:
            asset_filters.append(
                await insight_permission_service.visibility_filter_for_user(
                    db,
                    InsightIntelligenceAsset,
                    target_type="asset",
                    user_id=user_id,
                    is_admin=is_admin,
                )
            )
        visible_asset_ids = list((await db.exec(select(InsightIntelligenceAsset.id).where(*asset_filters).limit(500))).all())
        if not visible_asset_ids:
            return InsightGraphResponse()
        edge_filters.append(InsightGraphEdge.source_asset_id.in_(visible_asset_ids))
        edges = list((await db.exec(select(InsightGraphEdge).where(*edge_filters).order_by(InsightGraphEdge.update_time.desc()).limit(limit))).all())
        node_ids = sorted({edge.source_node_id for edge in edges} | {edge.target_node_id for edge in edges})
        if node_ids:
            node_filters.append(InsightGraphNode.id.in_(node_ids))
        else:
            node_filters.append(InsightGraphNode.source_asset_id.in_(visible_asset_ids))
        nodes = list((await db.exec(select(InsightGraphNode).where(*node_filters).order_by(InsightGraphNode.update_time.desc()).limit(limit))).all())
        return InsightGraphResponse(
            nodes=[self._to_node_read(node) for node in nodes],
            edges=[self._to_edge_read(edge) for edge in edges],
        )

    async def upsert_graph(self, db: AsyncSession, asset: InsightIntelligenceAsset) -> None:
        subject_name = asset.subject_name or asset.title
        subject_node = await self._upsert_node(db, "企业" if asset.company_id else "主题", subject_name, asset)
        event_node = await self._upsert_node(db, "事件", asset.title, asset)
        await self._upsert_edge(db, subject_node, event_node, "涉及", asset, asset.summary)
        for entity in asset.entities[:8]:
            name = str(entity.get("name") or "").strip()
            if not name:
                continue
            node = await self._upsert_node(db, str(entity.get("type") or "关键词"), name, asset)
            await self._upsert_edge(db, subject_node, node, self._relation_for_entity(entity), asset, asset.summary)
        for keyword in asset.keywords[:8]:
            node = await self._upsert_node(db, "关键词", keyword, asset)
            await self._upsert_edge(db, event_node, node, "包含关键词", asset, asset.summary)
        asset.graph_status = "indexed"

    async def _upsert_node(self, db: AsyncSession, node_type: str, name: str, asset: InsightIntelligenceAsset) -> InsightGraphNode:
        canonical = self._canonical(name)
        uid = sha1(f"{node_type}:{canonical}".encode("utf-8")).hexdigest()
        node = (await db.exec(select(InsightGraphNode).where(InsightGraphNode.node_uid == uid))).first()
        if node is None:
            node = InsightGraphNode(
                node_uid=uid,
                node_type=node_type[:50],
                node_name=name[:300],
                canonical_name=canonical[:300],
                source_asset_id=asset.id,
                company_id=asset.company_id,
                node_metadata={"first_asset_id": asset.id},
            )
            db.add(node)
            await db.flush()
        else:
            was_deleted = node.is_deleted != 0
            node.is_deleted = 0
            node.status = "active"
            node.source_asset_id = asset.id if was_deleted else node.source_asset_id or asset.id
            node.company_id = node.company_id or asset.company_id
            node.node_name = node.node_name or name[:300]
            node.canonical_name = node.canonical_name or canonical[:300]
            node.update_time = datetime.now()
        return node

    async def _upsert_edge(
        self,
        db: AsyncSession,
        source: InsightGraphNode,
        target: InsightGraphNode,
        relation_type: str,
        asset: InsightIntelligenceAsset,
        evidence: str | None,
    ) -> InsightGraphEdge:
        uid = sha1(f"{source.id}:{relation_type}:{target.id}:{asset.id}".encode("utf-8")).hexdigest()
        edge = (await db.exec(select(InsightGraphEdge).where(InsightGraphEdge.edge_uid == uid))).first()
        if edge is None:
            edge = InsightGraphEdge(
                edge_uid=uid,
                source_node_id=source.id or 0,
                target_node_id=target.id or 0,
                relation_type=relation_type[:80],
                source_asset_id=asset.id,
                confidence=asset.confidence,
                evidence_text=(evidence or "")[:1000] or None,
            )
            db.add(edge)
            await db.flush()
        else:
            edge.is_deleted = 0
            edge.status = "active"
            edge.confidence = max(edge.confidence, asset.confidence)
            edge.evidence_text = edge.evidence_text or (evidence or "")[:1000] or None
            edge.update_time = datetime.now()
        return edge

    async def _vector_map(self, db: AsyncSession, asset_ids: list[int]) -> dict[int, InsightAssetVector]:
        if not asset_ids:
            return {}
        rows = list((await db.exec(
            select(InsightAssetVector).where(
                InsightAssetVector.asset_id.in_(asset_ids),
                InsightAssetVector.vector_scope == "summary",
                InsightAssetVector.status == "indexed",
                InsightAssetVector.is_deleted == 0,
            )
        )).all())
        return {row.asset_id: row for row in rows}

    def _formal_backfill_filters(self, *, include_inactive: bool) -> list[Any]:
        filters: list[Any] = [
            InsightIntelligence.is_deleted == 0,
            InsightIntelligence.review_status == "approved",
            ~exists()
            .where(InsightIntelligenceAsset.intelligence_id == InsightIntelligence.id)
            .where(InsightIntelligenceAsset.is_deleted == 0),
        ]
        if not include_inactive:
            filters.append(InsightIntelligence.status == "active")
        return filters

    async def _source_map_for_intelligences(
        self,
        db: AsyncSession,
        intelligence_ids: list[int],
    ) -> dict[int, list[InsightIntelligenceSource]]:
        if not intelligence_ids:
            return {}
        rows = list(
            (
                await db.exec(
                    select(InsightIntelligenceSource)
                    .where(
                        InsightIntelligenceSource.intelligence_id.in_(intelligence_ids),
                        InsightIntelligenceSource.is_deleted == 0,
                    )
                    .order_by(InsightIntelligenceSource.intelligence_id.asc(), InsightIntelligenceSource.create_time.asc())
                )
            ).all()
        )
        result: dict[int, list[InsightIntelligenceSource]] = {}
        for row in rows:
            result.setdefault(row.intelligence_id, []).append(row)
        return result

    def _asset_type_from_candidate(self, candidate: InsightIntelligenceCandidate) -> str:
        if candidate.review_status == InsightCandidateReviewStatus.IGNORED:
            return "noise"
        if candidate.review_status == InsightCandidateReviewStatus.PROMOTED:
            return "formal"
        return "candidate"

    def _extract_ai_payload(self, tags: list[dict[str, Any]], review_payload: dict[str, Any] | None) -> dict[str, Any]:
        result = dict(review_payload or {})
        for tag in tags:
            if not isinstance(tag, dict):
                continue
            if tag.get("source") in {"llm_analysis", "ai_review"}:
                result.update({key: value for key, value in tag.items() if key not in {"name", "source"}})
        return result

    def _asset_text(self, title: str, summary: str | None, crawl_result: InsightCrawlResult | None) -> str:
        return self._join_text(title, summary, crawl_result.snippet if crawl_result else None, crawl_result.markdown_content if crawl_result else None)

    def _join_text(self, *values: str | None) -> str:
        return "\n".join(str(value).strip() for value in values if str(value or "").strip())

    def _importance_from_score(self, score: float) -> str:
        if score >= 0.82:
            return "high"
        if score <= 0.45:
            return "low"
        return "medium"

    def _entity_payload(self, value: object) -> list[dict[str, Any]]:
        if isinstance(value, list):
            result = []
            for item in value:
                if isinstance(item, dict):
                    name = str(item.get("name") or item.get("text") or "").strip()
                    if name:
                        result.append({"name": name[:100], "type": str(item.get("type") or "实体")[:50]})
                elif str(item).strip():
                    result.append({"name": str(item).strip()[:100], "type": "实体"})
            return result
        return []

    def _string_items(self, value: object) -> list[str]:
        if isinstance(value, list):
            return [str(item).strip()[:200] for item in value if str(item).strip()]
        if isinstance(value, str) and value.strip():
            return [item.strip()[:200] for item in re.split(r"[\n,，;；]+", value) if item.strip()]
        return []

    def _keywords(self, title: str, summary: str | None, tags: list[dict[str, Any]]) -> list[str]:
        values = [str(tag.get("name") or "").strip() for tag in tags if isinstance(tag, dict)]
        text = f"{title} {summary or ''}"
        values.extend(re.findall(r"[\u4e00-\u9fa5A-Za-z0-9]{2,20}", text)[:20])
        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            if value and value not in seen:
                seen.add(value)
                result.append(value[:50])
        return result[:30]

    def _keyword_score(self, query: str, asset: InsightIntelligenceAsset) -> float:
        terms = [term for term in re.split(r"\s+", query.lower()) if term]
        if not terms:
            terms = [query.lower()]
        text = self._join_text(asset.title, asset.summary, " ".join(asset.keywords)).lower()
        hits = sum(1 for term in terms if term and term in text)
        return hits / max(len(terms), 1)

    def _relation_for_entity(self, entity: dict[str, Any]) -> str:
        node_type = str(entity.get("type") or "")
        if "产品" in node_type:
            return "发布或涉及产品"
        if "技术" in node_type or "专利" in node_type:
            return "涉及技术"
        if "政策" in node_type:
            return "涉及政策"
        return "关联"

    def _canonical(self, name: str) -> str:
        return re.sub(r"\s+", "", name.strip().lower())

    def _float_value(self, value: object, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _int_or_none(self, value: object) -> int | None:
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    def _to_asset_read(self, asset: InsightIntelligenceAsset) -> InsightAssetRead:
        payload = asset.structured_payload if isinstance(asset.structured_payload, dict) else {}
        return InsightAssetRead(
            id=asset.id,
            create_time=asset.create_time,
            update_time=asset.update_time,
            create_by=asset.create_by,
            update_by=asset.update_by,
            comment=asset.comment,
            is_deleted=asset.is_deleted,
            asset_uid=asset.asset_uid,
            asset_type=asset.asset_type,
            source_kind=asset.source_kind,
            intelligence_id=asset.intelligence_id,
            candidate_id=asset.candidate_id,
            crawl_result_id=asset.crawl_result_id,
            data_source_id=asset.data_source_id,
            company_id=asset.company_id,
            subject_type=asset.subject_type.value,
            subject_id=asset.subject_id,
            subject_name=asset.subject_name,
            title=asset.title,
            summary=asset.summary,
            source_url=asset.source_url,
            source_title=asset.source_title,
            source_channel=asset.source_channel,
            publish_time=asset.publish_time,
            intelligence_type=asset.intelligence_type,
            business_value=asset.business_value,
            importance_level=asset.importance_level,
            sentiment=asset.sentiment,
            confidence=asset.confidence,
            tags=asset.tags,
            entities=asset.entities,
            related_products=self._string_items(payload.get("related_products")),
            opportunities=asset.opportunities,
            risks=asset.risks,
            keywords=asset.keywords,
            evidence=str(payload.get("evidence") or "")[:1000] or None,
            review_reason=str(payload.get("reason") or "")[:1000] or None,
            embedding_status=asset.embedding_status,
            graph_status=asset.graph_status,
            visibility_scope=asset.visibility_scope.value,
            status=asset.status,
        )

    def _to_node_read(self, node: InsightGraphNode) -> InsightGraphNodeRead:
        return InsightGraphNodeRead(
            id=node.id,
            create_time=node.create_time,
            update_time=node.update_time,
            create_by=node.create_by,
            update_by=node.update_by,
            comment=node.comment,
            is_deleted=node.is_deleted,
            node_uid=node.node_uid,
            node_type=node.node_type,
            node_name=node.node_name,
            canonical_name=node.canonical_name,
            source_asset_id=node.source_asset_id,
            company_id=node.company_id,
            node_metadata=node.node_metadata,
            status=node.status,
        )

    def _to_edge_read(self, edge: InsightGraphEdge) -> InsightGraphEdgeRead:
        return InsightGraphEdgeRead(
            id=edge.id,
            create_time=edge.create_time,
            update_time=edge.update_time,
            create_by=edge.create_by,
            update_by=edge.update_by,
            comment=edge.comment,
            is_deleted=edge.is_deleted,
            edge_uid=edge.edge_uid,
            source_node_id=edge.source_node_id,
            target_node_id=edge.target_node_id,
            relation_type=edge.relation_type,
            source_asset_id=edge.source_asset_id,
            confidence=edge.confidence,
            evidence_text=edge.evidence_text,
            edge_metadata=edge.edge_metadata,
            status=edge.status,
        )


insight_asset_service = InsightAssetService()
