import json
import re
from datetime import datetime
from typing import Any
from uuid import uuid4

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import String, cast, exists, or_
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.llm_factory import LLMFactory
from app.core.logger import logger
from app.models.agent.insight import InsightCompany, InsightIntelligence, InsightIntelligenceSource
from app.models.agent.insight.report import InsightReport, InsightReportMaterial, InsightReportVersion
from app.schemas.agent.insight.intelligence import (
    InsightAssistantChatRequest,
    InsightAssistantChatResponse,
    InsightAssistantCitation,
    InsightDeepResearchRequest,
    InsightDeepResearchResponse,
    InsightEvidenceMatrixItem,
)
from app.services.agent.insight.permission_service import insight_permission_service


class InsightAssistantService:
    async def chat(
        self,
        db: AsyncSession,
        payload: InsightAssistantChatRequest,
        *,
        user_id: int | None,
        is_admin: bool,
    ) -> InsightAssistantChatResponse:
        evidences = await self._retrieve_evidence(db, payload, user_id=user_id, is_admin=is_admin)
        if not evidences:
            return InsightAssistantChatResponse(
                answer="库内未找到足够证据回答这个问题。建议先扩大关键词、公司或日期范围，再执行相关数据源采集。",
                no_evidence=True,
                generation_mode="none",
            )
        answer, generation_mode = await self._ask_llm_for_answer(payload.question, evidences)
        return InsightAssistantChatResponse(
            answer=answer,
            citations=self._citations(evidences),
            evidence_count=len(evidences),
            no_evidence=False,
            generation_mode=generation_mode,
        )

    async def deep_research(
        self,
        db: AsyncSession,
        payload: InsightDeepResearchRequest,
        *,
        user_id: int | None,
        is_admin: bool,
    ) -> InsightDeepResearchResponse:
        evidences = await self._retrieve_evidence(db, payload, user_id=user_id, is_admin=is_admin)
        if not evidences:
            return InsightDeepResearchResponse(
                title=payload.report_title or payload.question[:80],
                conclusion="库内未找到足够证据形成深度研究结论。",
                follow_up_questions=["补充相关数据源并重新执行采集", "扩大关键词和时间范围后再次研究"],
                generation_mode="none",
            )
        draft, generation_mode = await self._ask_llm_for_research(payload.question, evidences)
        response = InsightDeepResearchResponse(
            title=str(draft.get("title") or payload.report_title or payload.question[:80]),
            conclusion=str(draft.get("conclusion") or ""),
            findings=self._string_items(draft.get("findings")),
            opportunities=self._string_items(draft.get("opportunities")),
            risks=self._string_items(draft.get("risks")),
            evidence_matrix=[
                InsightEvidenceMatrixItem(
                    intelligence_id=int(item.get("intelligence_id") or 0),
                    title=str(item.get("title") or ""),
                    evidence=str(item.get("evidence") or ""),
                    source_url=item.get("source_url"),
                    publish_time=self._parse_datetime(item.get("publish_time")),
                )
                for item in draft.get("evidence_matrix", [])
                if isinstance(item, dict) and item.get("intelligence_id")
            ],
            follow_up_questions=self._string_items(draft.get("follow_up_questions")),
            citations=self._citations(evidences),
            generation_mode=generation_mode,
        )
        if payload.save_report:
            response.report_id = await self._save_research_report(db, response, evidences, user_id=user_id)
        return response

    async def _retrieve_evidence(
        self,
        db: AsyncSession,
        payload: InsightAssistantChatRequest,
        *,
        user_id: int | None,
        is_admin: bool,
    ) -> list[dict[str, Any]]:
        filters = [InsightIntelligence.is_deleted == 0, InsightIntelligence.status == "active", InsightIntelligence.review_status == "approved"]
        keyword = payload.keyword or payload.question
        tokens = [item for item in re.split(r"[\s,，;；、]+", keyword) if len(item.strip()) >= 2][:8]
        if tokens:
            token_filters = []
            for token in tokens:
                like = f"%{token.strip()}%"
                token_filters.append(
                    or_(
                        InsightIntelligence.title.ilike(like),
                        InsightIntelligence.summary.ilike(like),
                        InsightIntelligence.content.ilike(like),
                        InsightIntelligence.subject_name.ilike(like),
                        cast(InsightIntelligence.raw_payload, String).ilike(like),
                    )
                )
            filters.append(or_(*token_filters))
        if payload.company_id:
            filters.append(InsightIntelligence.company_id == payload.company_id)
        if payload.data_source_id:
            filters.append(InsightIntelligence.data_source_id == payload.data_source_id)
        if payload.intelligence_type:
            filters.append(InsightIntelligence.intelligence_type == payload.intelligence_type)
        if payload.sentiment:
            filters.append(InsightIntelligence.sentiment == payload.sentiment)
        if payload.project_name:
            filters.append(cast(InsightIntelligence.raw_payload, String).ilike(f"%{payload.project_name.strip()}%"))
        if payload.tag:
            filters.append(cast(InsightIntelligence.raw_payload, String).ilike(f"%{payload.tag.strip()}%"))
        if payload.date_from:
            filters.append(InsightIntelligence.publish_time >= payload.date_from)
        if payload.date_to:
            filters.append(InsightIntelligence.publish_time <= payload.date_to)
        if payload.sys_company_id:
            filters.append(
                exists()
                .where(InsightCompany.id == InsightIntelligence.company_id)
                .where(InsightCompany.sys_company_id == payload.sys_company_id)
                .where(InsightCompany.is_deleted == 0)
            )
        if not is_admin:
            filters.append(await self._company_isolation_filter(db, user_id=user_id, is_admin=is_admin))
            filters.append(
                await insight_permission_service.visibility_filter_for_user(
                    db,
                    InsightIntelligence,
                    target_type="intelligence",
                    user_id=user_id,
                    is_admin=is_admin,
                )
            )
        rows = list(
            (
                await db.exec(
                    select(InsightIntelligence)
                    .where(*filters)
                    .order_by(InsightIntelligence.publish_time.desc().nullslast(), InsightIntelligence.create_time.desc())
                    .limit(payload.limit)
                )
            ).all()
        )
        source_map = await self._source_map(db, [row.id for row in rows if row.id])
        return [self._evidence_item(row, source_map.get(row.id or 0)) for row in rows]

    async def _company_isolation_filter(
        self,
        db: AsyncSession,
        *,
        user_id: int | None,
        is_admin: bool,
    ):
        if is_admin:
            return True
        sys_company_id = await insight_permission_service.resolve_user_sys_company_id(db, user_id)
        if sys_company_id is None:
            return InsightIntelligence.company_id.is_(None)
        return or_(
            InsightIntelligence.company_id.is_(None),
            exists()
            .where(InsightCompany.id == InsightIntelligence.company_id)
            .where(InsightCompany.sys_company_id == sys_company_id)
            .where(InsightCompany.is_deleted == 0),
        )

    async def _source_map(self, db: AsyncSession, ids: list[int]) -> dict[int, InsightIntelligenceSource]:
        if not ids:
            return {}
        sources = list(
            (
                await db.exec(
                    select(InsightIntelligenceSource)
                    .where(InsightIntelligenceSource.intelligence_id.in_(ids), InsightIntelligenceSource.is_deleted == 0)
                    .order_by(InsightIntelligenceSource.create_time.asc())
                )
            ).all()
        )
        result: dict[int, InsightIntelligenceSource] = {}
        for source in sources:
            result.setdefault(source.intelligence_id, source)
        return result

    def _evidence_item(self, row: InsightIntelligence, source: InsightIntelligenceSource | None) -> dict[str, Any]:
        return {
            "intelligence_id": row.id,
            "title": row.title,
            "summary": row.summary,
            "content_excerpt": (row.content or "")[:1200],
            "intelligence_type": row.intelligence_type,
            "sentiment": row.sentiment,
            "publish_time": row.publish_time.isoformat() if row.publish_time else None,
            "source_url": source.source_url if source else None,
            "source_title": source.source_title if source else None,
        }

    async def _ask_llm_for_answer(self, question: str, evidences: list[dict[str, Any]]) -> tuple[str, str]:
        try:
            response = await LLMFactory.safe_invoke(
                [
                    SystemMessage(
                        content=(
                            "你是研发营销市场洞察平台的库内证据问答助手。只能依据给定情报证据回答，"
                            "每个关键判断必须引用情报ID和来源URL；证据不足时明确说明不足，不得编造。"
                        )
                    ),
                    HumanMessage(content=json.dumps({"question": question, "evidences": evidences}, ensure_ascii=False)),
                ],
                capability="general",
                temperature=0,
            )
            return str(getattr(response, "content", response)).strip(), "llm"
        except Exception as exc:
            logger.warning(f"Insight AI 助手调用失败，使用证据摘要兜底：{exc}")
            return self._fallback_answer(question, evidences), "rules"

    async def _ask_llm_for_research(self, question: str, evidences: list[dict[str, Any]]) -> tuple[dict[str, Any], str]:
        try:
            response = await LLMFactory.safe_invoke(
                [
                    SystemMessage(
                        content=(
                            "你是研发营销市场洞察平台的深度研究助手。只能使用给定情报证据，输出严格 JSON，"
                            "字段：title、conclusion、findings、opportunities、risks、evidence_matrix、follow_up_questions。"
                            "evidence_matrix 每项包含 intelligence_id、title、evidence、source_url、publish_time。"
                        )
                    ),
                    HumanMessage(content=json.dumps({"question": question, "evidences": evidences}, ensure_ascii=False)),
                ],
                capability="general",
                temperature=0,
                json_mode=True,
            )
            content = str(getattr(response, "content", response))
            return json.loads(self._strip_json_fence(content)), "llm"
        except Exception as exc:
            logger.warning(f"Insight 深度研究调用失败，使用规则草稿兜底：{exc}")
            return self._fallback_research(question, evidences), "rules"

    async def _save_research_report(
        self,
        db: AsyncSession,
        response: InsightDeepResearchResponse,
        evidences: list[dict[str, Any]],
        *,
        user_id: int | None,
    ) -> int:
        report = InsightReport(
            report_uid=f"report_{uuid4().hex}",
            title=response.title,
            report_type="深度研究报告",
            content_json=response.model_dump(mode="json"),
            summary=response.conclusion,
            status="draft",
            material_count=len(evidences),
            owner_user_id=user_id,
            visibility_scope="assigned",
            create_by=str(user_id) if user_id else None,
            update_by=str(user_id) if user_id else None,
        )
        db.add(report)
        await db.flush()
        for index, evidence in enumerate(evidences, start=1):
            db.add(
                InsightReportMaterial(
                    report_id=report.id or 0,
                    intelligence_id=int(evidence["intelligence_id"]),
                    section_key="evidence_matrix",
                    sort_no=index,
                    quote_text=evidence.get("summary") or evidence.get("content_excerpt"),
                    source_url=evidence.get("source_url"),
                    source_title=evidence.get("source_title"),
                    selection_source="deep_research",
                )
            )
        db.add(
            InsightReportVersion(
                report_id=report.id or 0,
                version_no=1,
                content_json=response.model_dump(mode="json"),
                change_summary="深度研究生成初稿",
                created_by_user_id=user_id,
            )
        )
        await db.commit()
        await db.refresh(report)
        return report.id or 0

    def _citations(self, evidences: list[dict[str, Any]]) -> list[InsightAssistantCitation]:
        return [
            InsightAssistantCitation(
                intelligence_id=int(item["intelligence_id"]),
                title=str(item.get("title") or ""),
                source_url=item.get("source_url"),
                source_title=item.get("source_title"),
                publish_time=self._parse_datetime(item.get("publish_time")),
                summary=item.get("summary"),
            )
            for item in evidences
        ]

    def _fallback_answer(self, question: str, evidences: list[dict[str, Any]]) -> str:
        lines = [f"问题：{question}", "基于库内证据，先给出可核查摘要："]
        for item in evidences[:8]:
            lines.append(f"- 情报ID {item['intelligence_id']}：{item.get('title')}。来源：{item.get('source_url') or '未记录URL'}")
        return "\n".join(lines)

    def _fallback_research(self, question: str, evidences: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "title": question[:80],
            "conclusion": f"已检索到 {len(evidences)} 条库内情报，可作为初步研究证据，建议结合新增采集继续验证。",
            "findings": [str(item.get("summary") or item.get("title")) for item in evidences[:5]],
            "opportunities": [],
            "risks": [],
            "evidence_matrix": [
                {
                    "intelligence_id": item["intelligence_id"],
                    "title": item.get("title"),
                    "evidence": item.get("summary") or item.get("content_excerpt"),
                    "source_url": item.get("source_url"),
                    "publish_time": item.get("publish_time"),
                }
                for item in evidences[:10]
            ],
            "follow_up_questions": ["哪些渠道仍缺少直接证据？", "是否需要补充竞对官网、专利和电商平台采集？"],
        }

    def _strip_json_fence(self, value: str) -> str:
        value = value.strip()
        if value.startswith("```"):
            value = re.sub(r"^```(?:json)?", "", value, flags=re.IGNORECASE).strip()
            value = re.sub(r"```$", "", value).strip()
        return value

    def _string_items(self, value: object) -> list[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str) and value.strip():
            return [item.strip() for item in re.split(r"[\n;；]+", value) if item.strip()]
        return []

    def _parse_datetime(self, value: object) -> datetime | None:
        if isinstance(value, datetime):
            return value
        if isinstance(value, str) and value:
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                return None
        return None


insight_assistant_service = InsightAssistantService()
