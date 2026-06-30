import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.llm_factory import LLMFactory
from app.core.logger import logger
from app.models.agent.insight import (
    InsightCandidateReviewStatus,
    InsightCompany,
    InsightCrawlResult,
    InsightDataSource,
    InsightIntelligenceCandidate,
    InsightMonitorConfig,
    InsightTag,
)
from app.schemas.agent.insight.asset import InsightAiReviewDecision, InsightAiReviewResponse
from app.schemas.agent.insight.intelligence import InsightCandidatePromoteRequest, InsightCandidateReviewRequest
from app.services.agent.insight.asset_service import insight_asset_service
from app.services.agent.insight.dictionary_service import INSIGHT_INTELLIGENCE_TYPES


class InsightAiReviewService:
    """AI 自动评审：决定候选进入正式情报、候选池或噪声归档。"""

    formal_threshold = 0.60
    candidate_threshold = 0.45

    async def review_candidate(
        self,
        db: AsyncSession,
        candidate_id: int,
        *,
        user_id: int | None,
        is_admin: bool = True,
    ) -> InsightAiReviewResponse:
        row = (
            await db.exec(
                select(InsightIntelligenceCandidate, InsightCrawlResult)
                .join(InsightCrawlResult, InsightCrawlResult.id == InsightIntelligenceCandidate.crawl_result_id)
                .where(
                    InsightIntelligenceCandidate.id == candidate_id,
                    InsightIntelligenceCandidate.is_deleted == 0,
                    InsightCrawlResult.is_deleted == 0,
                )
            )
        ).first()
        if not row:
            raise ValueError("候选情报不存在")
        candidate, crawl_result = row
        if candidate.review_status == InsightCandidateReviewStatus.PROMOTED and candidate.promoted_intelligence_id:
            asset_id = await self._upsert_formal_asset_for_promoted_candidate(
                db,
                candidate.promoted_intelligence_id,
                score_payload={"score": candidate.confidence},
            )
            return InsightAiReviewResponse(
                candidate_id=candidate.id or candidate_id,
                decision=InsightAiReviewDecision(decision="formal", score=candidate.confidence, reason="已转正式情报"),
                candidate_status=candidate.review_status.value,
                intelligence_id=candidate.promoted_intelligence_id,
                asset_id=asset_id,
            )
        if candidate.review_status != InsightCandidateReviewStatus.PENDING:
            return InsightAiReviewResponse(
                candidate_id=candidate.id or candidate_id,
                decision=InsightAiReviewDecision(decision="noise" if candidate.review_status == InsightCandidateReviewStatus.IGNORED else "candidate", score=candidate.confidence, reason="候选已处理"),
                candidate_status=candidate.review_status.value,
                intelligence_id=candidate.promoted_intelligence_id,
                asset_id=None,
            )

        context = await self._review_context(db, candidate, crawl_result)
        decision = await self._review_with_llm(candidate, crawl_result, context)
        decision = self._normalize_decision(decision, candidate, context)
        self._attach_review_tag(candidate, decision, context)

        intelligence_id: int | None = None
        asset_id: int | None = None
        if decision.decision == "formal":
            from app.services.agent.insight.intelligence_service import insight_intelligence_service

            response = await insight_intelligence_service.promote_candidate(
                db,
                candidate.id or candidate_id,
                InsightCandidatePromoteRequest(
                    review_comment=f"AI 自动评审通过：{decision.reason or '符合业务规则'}",
                    visibility_scope="assigned",
                    importance_level=self._importance_from_score(decision.score),
                    business_domain=decision.business_value,
                ),
                user_id,
                is_admin=is_admin,
            )
            intelligence_id = response.intelligence.id if response.intelligence else None
            if intelligence_id:
                from app.models.agent.insight import InsightIntelligence, InsightIntelligenceSource

                intelligence = await db.get(InsightIntelligence, intelligence_id)
                sources = list((await db.exec(select(InsightIntelligenceSource).where(InsightIntelligenceSource.intelligence_id == intelligence_id, InsightIntelligenceSource.is_deleted == 0))).all())
                if intelligence:
                    raw_payload = intelligence.raw_payload or {}
                    raw_payload["ai_review"] = decision.model_dump()
                    intelligence.raw_payload = raw_payload
                    asset = await insight_asset_service.upsert_intelligence_asset(db, intelligence, sources, review_payload=decision.model_dump())
                    asset_id = asset.id
                    await db.commit()
        elif decision.decision == "noise":
            from app.services.agent.insight.intelligence_service import insight_intelligence_service

            response = await insight_intelligence_service.ignore_candidate(
                db,
                candidate.id or candidate_id,
                InsightCandidateReviewRequest(review_comment=f"AI 自动归档噪声：{decision.reason or '相关性不足'}"),
                user_id,
                is_admin=is_admin,
            )
            candidate.review_status = InsightCandidateReviewStatus(response.candidate.review_status)
            await db.commit()
        else:
            await db.commit()

        await db.refresh(candidate)
        return InsightAiReviewResponse(
            candidate_id=candidate.id or candidate_id,
            decision=decision,
            candidate_status=candidate.review_status.value,
            intelligence_id=intelligence_id or candidate.promoted_intelligence_id,
            asset_id=asset_id,
        )

    async def review_candidates(
        self,
        db: AsyncSession,
        candidate_ids: list[int],
        *,
        user_id: int | None,
        is_admin: bool = True,
    ) -> list[InsightAiReviewResponse]:
        results: list[InsightAiReviewResponse] = []
        for candidate_id in candidate_ids:
            try:
                results.append(await self.review_candidate(db, candidate_id, user_id=user_id, is_admin=is_admin))
            except Exception as exc:
                await db.rollback()
                logger.warning(f"Insight AI 自动评审失败: candidate_id={candidate_id}, error={exc}")
        return results

    async def _upsert_formal_asset_for_promoted_candidate(
        self,
        db: AsyncSession,
        intelligence_id: int,
        *,
        score_payload: dict[str, Any] | None = None,
    ) -> int | None:
        from app.models.agent.insight import InsightIntelligence, InsightIntelligenceSource

        intelligence = await db.get(InsightIntelligence, intelligence_id)
        if not intelligence:
            return None
        sources = list(
            (
                await db.exec(
                    select(InsightIntelligenceSource).where(
                        InsightIntelligenceSource.intelligence_id == intelligence_id,
                        InsightIntelligenceSource.is_deleted == 0,
                    )
                )
            ).all()
        )
        asset = await insight_asset_service.upsert_intelligence_asset(db, intelligence, sources, review_payload=score_payload)
        await db.commit()
        return asset.id

    async def _review_context(
        self,
        db: AsyncSession,
        candidate: InsightIntelligenceCandidate,
        crawl_result: InsightCrawlResult,
    ) -> dict[str, Any]:
        data_source = await db.get(InsightDataSource, crawl_result.data_source_id) if crawl_result.data_source_id else None
        company = await db.get(InsightCompany, candidate.company_id) if candidate.company_id else None
        monitor_config = None
        monitor_config_id = crawl_result.monitor_config_id or (getattr(data_source, "monitor_config_id", None) if data_source else None)
        if monitor_config_id:
            monitor_config = await db.get(InsightMonitorConfig, monitor_config_id)
        if not monitor_config and company:
            monitor_config = (
                await db.exec(
                    select(InsightMonitorConfig).where(
                        InsightMonitorConfig.object_type == "company",
                        InsightMonitorConfig.object_id == company.id,
                        InsightMonitorConfig.is_deleted == 0,
                        InsightMonitorConfig.status == "active",
                    )
                )
            ).first()
        return {
            "company": {
                "name": company.name if company else None,
                "short_name": company.short_name if company else None,
                "company_type": company.company_type if company else None,
                "profile": company.profile_json if company and isinstance(company.profile_json, dict) else {},
            },
            "monitor_config": {
                "name": monitor_config.config_name if monitor_config else None,
                "relation_type": monitor_config.relation_type if monitor_config else None,
                "enabled_modules": monitor_config.enabled_modules if monitor_config else [],
                "keywords": monitor_config.keywords if monitor_config else [],
                "ai_review_prompt": monitor_config.ai_review_prompt if monitor_config else None,
            },
            "data_source": {
                "id": data_source.id if data_source else None,
                "source_name": data_source.source_name if data_source else None,
                "execution_role": getattr(data_source, "execution_role", None) if data_source else None,
            },
            "own_business": self._own_business_profile(),
            "taxonomy": await self._taxonomy_context(db),
        }

    async def _review_with_llm(
        self,
        candidate: InsightIntelligenceCandidate,
        crawl_result: InsightCrawlResult,
        context: dict[str, Any],
    ) -> InsightAiReviewDecision:
        payload = {
            "candidate": {
                "title": candidate.candidate_title,
                "summary": candidate.candidate_summary,
                "intelligence_type": candidate.intelligence_type,
                "confidence": candidate.confidence,
                "suggested_tags": candidate.suggested_tags,
            },
            "source": {
                "url": crawl_result.source_url,
                "title": crawl_result.source_title,
                "snippet": crawl_result.snippet,
                "content": (crawl_result.markdown_content or "")[:5000],
                "published_at": crawl_result.published_at.isoformat() if crawl_result.published_at else None,
            },
            "context": context,
            "decision_values": ["formal", "candidate", "noise"],
        }
        prompt = context.get("monitor_config", {}).get("ai_review_prompt") or self._default_prompt(context)
        try:
            response = await LLMFactory.safe_invoke(
                [
                    SystemMessage(
                        content=(
                            "你是研发营销市场洞察平台的 AI 情报评审员。"
                            "请取消人工审核思路，直接判断资料进入正式情报、候选情报或噪声归档。"
                            "只能输出严格 JSON，格式为："
                            "{\"decision\":\"formal|candidate|noise\",\"score\":0.86,\"reason\":\"...\","
                            "\"intelligence_type_code\":\"product_update\",\"intelligence_type\":\"产品动态\","
                            "\"business_value\":\"销售机会\",\"tag_codes\":[\"sales_opportunity\"],"
                            "\"suggested_new_tags\":[\"...\"],"
                            "\"related_products\":[\"...\"],\"opportunities\":[\"...\"],\"risks\":[\"...\"],"
                            "\"entities\":[\"...\"],\"evidence\":\"原文关键摘录\"}。"
                            "intelligence_type_code 只能从 allowed_intelligence_types 中选择。"
                            "tag_codes 只能从 controlled_tags 的 tag_code 中选择，不允许编造正式标签；"
                            "确实缺少标签时，只能放入 suggested_new_tags，等待管理员维护字典。"
                            "必须先参考 context.own_business 中的我方业务定位，再结合监测对象关系类型、监测模块和原文证据判断业务价值。"
                            "business_value 要写清楚这条信息对香驰控股在客户经营洞察、销售跟进、研发应用、竞对策略、供应链、质量风险或战略研判上的具体用途。"
                            "formal 表示监测对象相关、公开证据清楚，且有明确业务价值；"
                            "正式情报不限于直接采购需求，新设公司、战略规划、风险投诉、专利技术、产品研发、渠道动作、合作融资、经营变化等只要与监测口径相关也应进入 formal。"
                            "candidate 仅用于来源较弱、事实不完整、业务价值不明确或需要持续观察的线索；"
                            "noise 表示无关、重复、验证码、广告、百科泛信息、纯例行公告或低价值转载。"
                        )
                    ),
                    HumanMessage(content=json.dumps({"business_prompt": prompt, **payload}, ensure_ascii=False)),
                ],
                capability="complex-reasoning",
                temperature=0,
                json_mode=True,
                max_retries=2,
            )
        except Exception as exc:
            logger.warning(f"Insight AI 自动评审模型调用失败，使用规则兜底：{exc}")
            return self._fallback_decision(candidate)

        content = getattr(response, "content", response)
        if isinstance(content, list):
            content = "".join(str(item) for item in content)
        if not isinstance(content, str):
            return self._fallback_decision(candidate)
        try:
            parsed = json.loads(self._strip_json_fence(content))
        except json.JSONDecodeError:
            return self._fallback_decision(candidate)
        if not isinstance(parsed, dict):
            return self._fallback_decision(candidate)
        return InsightAiReviewDecision(
            decision=str(parsed.get("decision") or "candidate"),
            score=self._float_value(parsed.get("score"), candidate.confidence),
            reason=str(parsed.get("reason") or "")[:1000] or None,
            intelligence_type_code=str(parsed.get("intelligence_type_code") or "")[:80] or None,
            intelligence_type=str(parsed.get("intelligence_type") or candidate.intelligence_type or "")[:50] or None,
            business_value=str(parsed.get("business_value") or "")[:100] or None,
            tag_codes=self._string_items(parsed.get("tag_codes") or parsed.get("tags"))[:10],
            suggested_new_tags=self._string_items(parsed.get("suggested_new_tags"))[:10],
            related_products=self._string_items(parsed.get("related_products"))[:8],
            opportunities=self._string_items(parsed.get("opportunities"))[:8],
            risks=self._string_items(parsed.get("risks"))[:8],
            entities=self._string_items(parsed.get("entities"))[:12],
            evidence=str(parsed.get("evidence") or "")[:1000] or None,
        )

    def _normalize_decision(
        self,
        decision: InsightAiReviewDecision,
        candidate: InsightIntelligenceCandidate,
        context: dict[str, Any],
    ) -> InsightAiReviewDecision:
        value = decision.decision.strip().lower()
        if value not in {"formal", "candidate", "noise"}:
            value = "candidate"
        decision.score = min(max(decision.score, 0), 1)
        if decision.score < self.candidate_threshold:
            value = "noise"
        if candidate.confidence < 0.35:
            value = "noise"
        type_code, type_name = self._normalize_intelligence_type(
            decision.intelligence_type_code,
            decision.intelligence_type,
            candidate.intelligence_type,
            context,
        )
        decision.intelligence_type_code = type_code
        decision.intelligence_type = type_name
        candidate.intelligence_type = type_name
        tag_codes, tag_names = self._normalize_tag_codes(decision.tag_codes, context)
        decision.tag_codes = tag_codes
        decision.tag_names = tag_names
        decision.suggested_new_tags = self._suggested_new_tags(decision.suggested_new_tags, tag_names, context)
        if value == "formal" and decision.score < self.formal_threshold:
            value = "candidate"
        if value == "candidate" and self._should_promote_high_value_candidate(decision):
            value = "formal"
            rule_note = "系统规则：评分、受控标签和业务价值达到正式情报阈值，自动转正式。"
            decision.reason = f"{decision.reason or ''} {rule_note}".strip()[:1000]
        decision.decision = value
        return decision

    def _should_promote_high_value_candidate(self, decision: InsightAiReviewDecision) -> bool:
        if decision.score < self.formal_threshold:
            return False
        business_value = str(decision.business_value or "").strip().lower()
        if business_value in {"", "无", "none", "null", "n/a"}:
            return False
        if not decision.tag_codes and not decision.intelligence_type_code:
            return False
        return True

    def _fallback_decision(self, candidate: InsightIntelligenceCandidate) -> InsightAiReviewDecision:
        score = min(max(candidate.confidence, 0), 1)
        if score >= self.formal_threshold:
            decision = "formal"
            reason = "规则兜底：候选置信度达到正式情报阈值"
        elif score < self.candidate_threshold:
            decision = "noise"
            reason = "规则兜底：候选置信度较低，归档为噪声"
        else:
            decision = "candidate"
            reason = "规则兜底：保留为候选线索"
        return InsightAiReviewDecision(
            decision=decision,
            score=score,
            reason=reason,
            intelligence_type=candidate.intelligence_type,
        )

    def _attach_review_tag(
        self,
        candidate: InsightIntelligenceCandidate,
        decision: InsightAiReviewDecision,
        context: dict[str, Any],
    ) -> None:
        tags = candidate.suggested_tags if isinstance(candidate.suggested_tags, list) else []
        tags = [tag for tag in tags if not self._is_uncontrolled_semantic_tag(tag)]
        tags.extend(self._controlled_tag_payloads(decision, context))
        tags.append({"name": "AI自动评审", "source": "ai_review", **decision.model_dump()})
        candidate.suggested_tags = tags
        candidate.confidence = max(candidate.confidence, decision.score)

    async def _taxonomy_context(self, db: AsyncSession) -> dict[str, Any]:
        tag_rows = list(
            (
                await db.exec(
                    select(InsightTag)
                    .where(
                        InsightTag.is_deleted == 0,
                        InsightTag.status == "active",
                    )
                    .order_by(InsightTag.sort_no, InsightTag.id)
                )
            ).all()
        )
        return {
            "allowed_intelligence_types": [
                {
                    "type_code": str(item["type_code"]),
                    "type_name": str(item["type_name"]),
                    "description": str(item["description"]),
                }
                for item in INSIGHT_INTELLIGENCE_TYPES
            ],
            "controlled_tags": [
                {
                    "tag_code": tag.tag_code,
                    "tag_name": tag.tag_name,
                    "tag_type": tag.tag_type,
                    "color": tag.color,
                }
                for tag in tag_rows
            ],
        }

    def _normalize_intelligence_type(
        self,
        code: str | None,
        name: str | None,
        fallback: str | None,
        context: dict[str, Any],
    ) -> tuple[str, str]:
        values = context.get("taxonomy", {}).get("allowed_intelligence_types")
        allowed = values if isinstance(values, list) else []
        by_code = {str(item.get("type_code")): item for item in allowed if isinstance(item, dict)}
        by_name = {str(item.get("type_name")): item for item in allowed if isinstance(item, dict)}
        selected = by_code.get(str(code or "").strip()) or by_name.get(str(name or "").strip()) or by_name.get(str(fallback or "").strip())
        if not selected:
            selected = by_code.get("industry_news") or (allowed[0] if allowed else {"type_code": "industry_news", "type_name": "行业资讯"})
        return str(selected.get("type_code") or "industry_news"), str(selected.get("type_name") or "行业资讯")

    def _normalize_tag_codes(self, values: list[str], context: dict[str, Any]) -> tuple[list[str], list[str]]:
        tags = context.get("taxonomy", {}).get("controlled_tags")
        controlled = tags if isinstance(tags, list) else []
        by_code = {str(item.get("tag_code")): item for item in controlled if isinstance(item, dict)}
        by_name = {str(item.get("tag_name")): item for item in controlled if isinstance(item, dict)}
        codes: list[str] = []
        names: list[str] = []
        seen: set[str] = set()
        for value in values:
            key = str(value or "").strip()
            item = by_code.get(key) or by_name.get(key)
            if not item:
                continue
            code = str(item.get("tag_code") or "").strip()
            name = str(item.get("tag_name") or "").strip()
            if code and code not in seen:
                seen.add(code)
                codes.append(code)
                names.append(name)
        return codes[:10], names[:10]

    def _suggested_new_tags(
        self,
        values: list[str],
        selected_names: list[str],
        context: dict[str, Any],
    ) -> list[str]:
        tags = context.get("taxonomy", {}).get("controlled_tags")
        controlled = tags if isinstance(tags, list) else []
        existing = {str(item.get("tag_name") or "").strip() for item in controlled if isinstance(item, dict)}
        existing.update(str(item.get("tag_code") or "").strip() for item in controlled if isinstance(item, dict))
        existing.update(selected_names)
        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            name = str(value or "").strip()[:30]
            if not name or name in existing or name in seen:
                continue
            seen.add(name)
            result.append(name)
        return result[:10]

    def _controlled_tag_payloads(
        self,
        decision: InsightAiReviewDecision,
        context: dict[str, Any],
    ) -> list[dict[str, Any]]:
        tags = context.get("taxonomy", {}).get("controlled_tags")
        controlled = tags if isinstance(tags, list) else []
        by_code = {str(item.get("tag_code")): item for item in controlled if isinstance(item, dict)}
        result: list[dict[str, Any]] = []
        for code in decision.tag_codes:
            item = by_code.get(code)
            if not item:
                continue
            result.append(
                {
                    "name": item.get("tag_name"),
                    "code": item.get("tag_code"),
                    "tag_type": item.get("tag_type"),
                    "color": item.get("color"),
                    "source": "controlled_dictionary",
                    "confidence": decision.score,
                }
            )
        return result

    def _is_uncontrolled_semantic_tag(self, tag: object) -> bool:
        if not isinstance(tag, dict):
            return False
        source = str(tag.get("source") or "")
        return source in {"ai_review", "controlled_dictionary", "llm", "llm_analysis", "rule"}

    def _own_business_profile(self) -> dict[str, Any]:
        custom_profile = settings.INSIGHT_OWN_BUSINESS_PROFILE.strip()
        profile: dict[str, Any] = {
            "company_name": "香驰控股有限公司",
            "positioning": (
                "香驰控股有限公司是以大豆、玉米初加工和精深加工为主的农业产业化企业，"
                "面向全球营养健康和食品饮料产业提供原料、配料、粮油产品及应用解决方案。"
            ),
            "core_industries": [
                "大豆精深加工",
                "玉米精深加工",
                "功能糖和糖醇配料",
                "植物蛋白和大豆蛋白产品",
                "食用油和粮油终端品牌",
                "新能源动力、资源综合利用、仓储物流等产业配套",
            ],
            "core_products": [
                "果葡糖浆",
                "麦芽糖浆",
                "赤藓糖醇",
                "葡萄糖酸钠",
                "风味糖浆",
                "大豆分离蛋白",
                "大豆组织蛋白",
                "大豆浓缩蛋白",
                "大豆膳食纤维",
                "磷脂",
                "豆粕",
                "大豆油和粮油产品",
            ],
            "application_scenarios": [
                "饮料、茶饮、乳制品、冷饮、糖果、咖啡、烘焙等功能糖应用",
                "肉制品、植物基食品、保健食品、运动营养、特医食品、婴幼儿食品等蛋白应用",
                "包装食用油、餐饮连锁、食品加工等粮油应用",
                "饲料、豆粕、磷脂、膳食纤维等副产品和循环经济应用",
            ],
            "strategic_focus": [
                "客户新品、配方变化、原料替代、供应商导入和采购需求",
                "食品饮料、健康营养、植物基、运动营养、特医食品等下游行业变化",
                "竞对在功能糖、糖醇、植物蛋白、粮油、豆粕等领域的价格、产能、技术、渠道和客户合作",
                "玉米、大豆、豆粕、糖浆、油脂等原料和产品价格、进出口、政策、供需和库存变化",
                "食品安全、质量投诉、监管政策、标准、专利、环保、安全生产和贸易风险",
                "能支持销售拜访、客户维护、研发立项、产品方案、风险预警和公司战略研判的信息",
            ],
            "formal_guidance": (
                "评审时不要只找直接采购线索。凡是能帮助香驰判断客户动向、竞对动作、行业供需、"
                "产品趋势、研发方向、质量风险、政策变化或战略机会的公开信息，都应视为有业务价值。"
            ),
        }
        if custom_profile:
            profile["custom_profile"] = custom_profile
        return profile

    def _default_prompt(self, context: dict[str, Any]) -> str:
        relation = str(context.get("monitor_config", {}).get("relation_type") or context.get("company", {}).get("company_type") or "").strip()
        base = (
            "我方为香驰控股有限公司，核心关注大豆、玉米精深加工，果葡糖浆、麦芽糖浆、赤藓糖醇、"
            "大豆分离蛋白、组织蛋白、浓缩蛋白、豆粕、粮油等产品，以及食品饮料、营养健康、植物基、"
            "饲料、餐饮和食品加工客户的需求变化。"
        )
        if relation in {"客户", "customer"}:
            return f"{base}当前企业是我司客户。重点保留新品、配方变化、采购需求、产能扩张、渠道布局、经营变化、质量风险、政策影响、合作动态和供应链变化。"
        if relation in {"竞对", "competitor"}:
            return f"{base}当前企业是我司竞对。重点保留新品发布、技术专利、价格策略、渠道动作、营销活动、产能扩张、客户合作、融资并购、战略方向和风险事件。"
        if relation in {"潜在客户", "potential_customer"}:
            return f"{base}当前企业是我司潜在客户。重点识别销售线索、合作机会、研发配套机会、扩张、新产品、新工厂、新渠道、融资、采购需求和招标。"
        if relation in {"供应商", "supplier"}:
            return f"{base}当前企业是我司供应商或潜在供应商。重点识别价格波动、产能变化、交付风险、质量风险、环保安全、政策影响和替代供应可能性。"
        return f"{base}保留与我司研发、营销、销售、产品机会、客户变化、竞对动作、政策、专利、经营风险相关的资料；过滤无关转载、泛泛介绍、广告页和验证码页。"

    def _importance_from_score(self, score: float) -> str:
        if score >= 0.82:
            return "high"
        if score <= 0.45:
            return "low"
        return "medium"

    def _strip_json_fence(self, text: str) -> str:
        value = text.strip()
        if value.startswith("```"):
            value = re.sub(r"^```(?:json)?", "", value, flags=re.IGNORECASE).strip()
            value = re.sub(r"```$", "", value).strip()
        return value

    def _float_value(self, value: Any, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _string_items(self, value: object) -> list[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str) and value.strip():
            return [item.strip() for item in re.split(r"[\n,，;；]+", value) if item.strip()]
        return []


insight_ai_review_service = InsightAiReviewService()
