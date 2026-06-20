import json
import re
from datetime import datetime
from difflib import SequenceMatcher
from typing import Any
from uuid import uuid4

import httpx
from langchain_core.messages import HumanMessage, SystemMessage
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.llm_factory import LLMFactory
from app.core.logger import logger
from app.models.agent.insight import (
    InsightCandidateReviewStatus,
    InsightCompany,
    InsightCrawlerChannel,
    InsightCrawlResult,
    InsightCrawlStatus,
    InsightDataSource,
    InsightIntelligenceCandidate,
    InsightSubjectType,
    InsightTask,
    InsightTaskStatus,
)
from app.schemas.agent.insight.crawl import InsightManualUrlCrawlRequest, InsightManualUrlCrawlResponse
from app.services.agent.insight.crawler.content_cleaner import insight_content_cleaner
from app.services.agent.insight.crawler.firecrawl_client import firecrawl_client
from app.services.agent.insight.permission_service import insight_permission_service


class InsightCrawlService:
    async def crawl_manual_url(
        self,
        db: AsyncSession,
        request: InsightManualUrlCrawlRequest,
        user_id: int | None,
        *,
        is_admin: bool = False,
    ) -> InsightManualUrlCrawlResponse:
        await self._ensure_data_source_editable(db, request.data_source_id, user_id=user_id, is_admin=is_admin)
        task = InsightTask(
            task_uid=f"crawl_{uuid4().hex}",
            task_type="manual_url_crawl",
            data_source_id=request.data_source_id,
            status=InsightTaskStatus.RUNNING,
            progress=10,
            started_at=datetime.now(),
            input_payload={"url": request.url, "query_text": request.query_text, "user_id": user_id},
            create_by=str(user_id) if user_id else None,
            update_by=str(user_id) if user_id else None,
        )
        db.add(task)
        await db.commit()
        await db.refresh(task)

        try:
            firecrawl_data = await firecrawl_client.scrape_url(request.url)
            crawl_result = self._to_crawl_result(task.id or 0, request, firecrawl_data)
            crawl_result.create_by = str(user_id) if user_id else None
            crawl_result.update_by = str(user_id) if user_id else None
            existing_result = await self._get_existing_crawl_result(db, crawl_result)
            if existing_result:
                crawl_result = existing_result
            else:
                db.add(crawl_result)
                await db.commit()
                await db.refresh(crawl_result)

            quality_report = await self._assess_crawl_quality(db, crawl_result)
            crawl_metadata = crawl_result.crawl_metadata or {}
            crawl_metadata["quality_report"] = quality_report
            crawl_result.crawl_metadata = crawl_metadata

            candidate = await self._get_existing_candidate(db, crawl_result.id or 0)
            if not candidate:
                candidate = await self._to_candidate(db, crawl_result, firecrawl_data, quality_report)
                candidate.create_by = str(user_id) if user_id else None
                candidate.update_by = str(user_id) if user_id else None
                db.add(candidate)

            task.status = InsightTaskStatus.SUCCESS
            task.progress = 100
            task.finished_at = datetime.now()
            task.output_payload = {
                "crawl_result_id": crawl_result.id,
                "candidate_title": candidate.candidate_title,
                "deduped": existing_result is not None,
                "quality_report": quality_report,
            }
            await db.commit()
            await db.refresh(candidate)
            await db.refresh(task)
            return InsightManualUrlCrawlResponse(task=task, crawl_result=crawl_result, candidate=candidate)
        except Exception as exc:
            task.status = InsightTaskStatus.FAILED
            task.progress = 100
            task.finished_at = datetime.now()
            task.error_message = self._format_error(exc)
            await db.commit()
            raise

    async def _ensure_data_source_editable(
        self,
        db: AsyncSession,
        data_source_id: int | None,
        *,
        user_id: int | None,
        is_admin: bool,
    ) -> None:
        if not data_source_id:
            return
        filters = [
            InsightDataSource.id == data_source_id,
            InsightDataSource.is_deleted == 0,
            await insight_permission_service.visibility_filter_for_user(
                db,
                InsightDataSource,
                target_type="data_source",
                user_id=user_id,
                is_admin=is_admin,
                permission="edit",
            ),
        ]
        row = (await db.exec(select(InsightDataSource).where(*filters))).first()
        if not row:
            raise ValueError("数据源不存在或无权采集")

    def _to_crawl_result(
        self,
        task_id: int,
        request: InsightManualUrlCrawlRequest,
        firecrawl_data: dict[str, Any],
    ) -> InsightCrawlResult:
        metadata = firecrawl_data.get("metadata") or {}
        normalized_url = insight_content_cleaner.normalize_url(request.url)
        title = insight_content_cleaner.clean_title(
            metadata.get("title"),
            firecrawl_data.get("title"),
            request.query_text,
            normalized_url,
        )
        markdown = insight_content_cleaner.clean_text(firecrawl_data.get("markdown") or firecrawl_data.get("content"))
        html = firecrawl_data.get("html")
        published_at = insight_content_cleaner.parse_publish_time(metadata, markdown, title)
        return InsightCrawlResult(
            task_id=task_id,
            data_source_id=request.data_source_id,
            channel=InsightCrawlerChannel.FIRECRAWL,
            query_text=request.query_text,
            source_url=normalized_url,
            source_title=title,
            snippet=insight_content_cleaner.clean_summary(markdown, 500),
            markdown_content=markdown,
            published_at=published_at,
            dedupe_hash=insight_content_cleaner.build_dedupe_hash(normalized_url, title, markdown),
            crawl_metadata={
                "metadata": metadata,
                "html_length": len(html or ""),
                "markdown_length": len(markdown or ""),
                "original_url": request.url,
            },
            status=InsightCrawlStatus.PARSED,
        )

    async def _to_candidate(
        self,
        db: AsyncSession,
        crawl_result: InsightCrawlResult,
        firecrawl_data: dict[str, Any],
        quality_report: dict[str, Any] | None = None,
    ) -> InsightIntelligenceCandidate:
        metadata = firecrawl_data.get("metadata") or {}
        title = insight_content_cleaner.clean_title(crawl_result.source_title, metadata.get("title"), crawl_result.source_url)
        summary_source = crawl_result.markdown_content or crawl_result.snippet or ""
        quality_report = quality_report or {}
        review_status = (
            InsightCandidateReviewStatus.IGNORED
            if quality_report.get("auto_ignore")
            else InsightCandidateReviewStatus.PENDING
        )
        quality_tags = self._quality_tags(quality_report)
        subject_context = await self._resolve_subject_context(db, crawl_result, title, summary_source)
        llm_result = await self._summarize_candidate_with_llm(title, crawl_result.source_url, summary_source)
        if llm_result:
            subject_type = subject_context.get("subject_type") or self._subject_type_from_value(llm_result.get("subject_type")) or self._infer_subject_type(title, summary_source)
            intelligence_type = self._normalize_intelligence_type(llm_result.get("intelligence_type") or self._infer_intelligence_type(title, summary_source))
            return InsightIntelligenceCandidate(
                crawl_result_id=crawl_result.id or 0,
                candidate_title=str(llm_result.get("title") or title)[:500],
                candidate_summary=str(llm_result.get("summary") or insight_content_cleaner.clean_summary(summary_source, 800)),
                subject_type=subject_type,
                subject_name=str(subject_context.get("subject_name") or llm_result.get("subject_name") or self._infer_subject_name(title) or "")[:200] or None,
                company_id=subject_context.get("company_id"),
                intelligence_type=intelligence_type,
                suggested_tags=self._normalize_llm_tags(llm_result.get("tags")) + self._llm_analysis_tags(llm_result) + quality_tags,
                confidence=self._quality_adjusted_confidence(self._float_value(llm_result.get("confidence"), 0.68), quality_report),
                review_status=review_status,
                status="active",
            )

        return InsightIntelligenceCandidate(
            crawl_result_id=crawl_result.id or 0,
            candidate_title=title,
            candidate_summary=insight_content_cleaner.clean_summary(summary_source, 800),
            subject_type=subject_context.get("subject_type") or self._infer_subject_type(title, summary_source),
            subject_name=subject_context.get("subject_name") or self._infer_subject_name(title),
            company_id=subject_context.get("company_id"),
            intelligence_type=self._infer_intelligence_type(title, summary_source),
            suggested_tags=self._suggest_tags(title, summary_source) + quality_tags,
            confidence=self._quality_adjusted_confidence(0.35, quality_report),
            review_status=review_status,
            status="active",
        )

    async def _summarize_candidate_with_llm(
        self,
        title: str,
        url: str,
        content: str,
    ) -> dict[str, Any] | None:
        compact_content = insight_content_cleaner.clean_text(content)[:5000]
        if not compact_content:
            return None
        payload = {
            "title": title,
            "url": url,
            "content": compact_content,
            "allowed_subject_types": [item.value for item in InsightSubjectType],
        }
        try:
            response = await LLMFactory.safe_invoke(
                [
                    SystemMessage(
                        content=(
                            "你是研发营销市场洞察平台的情报摘要助手。"
                            "请从网页正文中抽取适合业务人员阅读的候选情报，输出严格 JSON。"
                            "字段包括 title、summary、subject_type、subject_name、intelligence_type、tags、sentiment、sentiment_reason、opportunities、risks、confidence。"
                            "summary 用中文，2-4 句，突出事件、主体、影响或商业价值；"
                            "subject_type 只能从 allowed_subject_types 中选择；"
                            "intelligence_type 必须使用中文，优先从 新品情报、财报公告、行业资讯、政策法规、应用方案、营销策略、竞品动态、经营动态、风险预警 中选择；"
                            "sentiment 只能为 positive、neutral、negative、mixed；"
                            "opportunities 和 risks 为中文字符串数组，分别给出可用于研发营销判断的机会点和风险点；"
                            "tags 为字符串数组，最多 6 个；confidence 为 0 到 1。"
                        )
                    ),
                    HumanMessage(content=json.dumps(payload, ensure_ascii=False)),
                ],
                capability="general",
                temperature=0,
                json_mode=True,
                max_retries=2,
            )
        except Exception as exc:
            logger.warning(f"Insight 候选情报 LLM 摘要失败，使用规则摘要兜底：{exc}")
            return None

        content_value = getattr(response, "content", response)
        if isinstance(content_value, list):
            content_value = "".join(str(item) for item in content_value)
        if not isinstance(content_value, str):
            return None
        try:
            result = json.loads(self._strip_json_fence(content_value))
        except json.JSONDecodeError as exc:
            logger.warning(f"Insight 候选情报 LLM 摘要 JSON 解析失败，使用规则摘要兜底：{exc}")
            return None
        return result if isinstance(result, dict) else None

    async def _resolve_subject_context(
        self,
        db: AsyncSession,
        crawl_result: InsightCrawlResult,
        title: str,
        content: str,
    ) -> dict[str, Any]:
        linked_company = await self._get_data_source_company(db, crawl_result.data_source_id)
        if linked_company:
            return self._company_subject_context(linked_company, "data_source_binding")

        matched_company = await self._match_company_by_text(db, f"{title}\n{content[:2000]}")
        if matched_company:
            return self._company_subject_context(matched_company, "text_match")
        return {}

    async def _get_data_source_company(
        self,
        db: AsyncSession,
        data_source_id: int | None,
    ) -> InsightCompany | None:
        if not data_source_id:
            return None
        data_source = await db.get(InsightDataSource, data_source_id)
        if not data_source or not data_source.company_id:
            return None
        company = await db.get(InsightCompany, data_source.company_id)
        if company and company.is_deleted == 0 and company.status == "active":
            return company
        return None

    async def _match_company_by_text(
        self,
        db: AsyncSession,
        text: str,
    ) -> InsightCompany | None:
        normalized_text = self._normalize_similarity_text(text)
        if not normalized_text:
            return None
        statement = (
            select(InsightCompany)
            .where(
                InsightCompany.is_deleted == 0,
                InsightCompany.status == "active",
            )
            .limit(500)
        )
        companies = list((await db.exec(statement)).all())
        best: tuple[InsightCompany, int] | None = None
        for company in companies:
            aliases = self._company_aliases(company)
            matched_lengths = [len(alias) for alias in aliases if alias and self._normalize_similarity_text(alias) in normalized_text]
            if not matched_lengths:
                continue
            score = max(matched_lengths)
            if best is None or score > best[1]:
                best = (company, score)
        return best[0] if best else None

    def _company_aliases(self, company: InsightCompany) -> list[str]:
        aliases = [company.name, company.short_name]
        profile = company.profile_json or {}
        extra_aliases = profile.get("aliases")
        if isinstance(extra_aliases, list):
            aliases.extend(str(item) for item in extra_aliases if str(item).strip())
        return [item.strip() for item in aliases if item and item.strip()]

    def _company_subject_context(self, company: InsightCompany, source: str) -> dict[str, Any]:
        return {
            "company_id": company.id,
            "subject_type": InsightSubjectType.COMPANY,
            "subject_name": company.short_name or company.name,
            "subject_match_source": source,
        }

    def _strip_json_fence(self, text: str) -> str:
        value = text.strip()
        if value.startswith("```"):
            value = re.sub(r"^```(?:json)?", "", value, flags=re.IGNORECASE).strip()
            value = re.sub(r"```$", "", value).strip()
        return value

    def _subject_type_from_value(self, value: object) -> InsightSubjectType | None:
        try:
            return InsightSubjectType(str(value))
        except (TypeError, ValueError):
            return None

    def _normalize_llm_tags(self, value: object) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        tags: list[dict[str, Any]] = []
        for item in value:
            name = item.get("name") if isinstance(item, dict) else item
            if isinstance(name, str) and name.strip():
                tags.append({"name": name.strip()[:30], "source": "llm"})
            if len(tags) >= 6:
                break
        return tags

    def _llm_analysis_tags(self, value: dict[str, Any]) -> list[dict[str, Any]]:
        sentiment = str(value.get("sentiment") or "neutral").strip()
        if sentiment not in {"positive", "neutral", "negative", "mixed"}:
            sentiment = "neutral"
        return [
            {
                "name": "AI分析",
                "source": "llm_analysis",
                "sentiment": sentiment,
                "sentiment_reason": str(value.get("sentiment_reason") or "").strip()[:500],
                "opportunities": self._string_items(value.get("opportunities"))[:6],
                "risks": self._string_items(value.get("risks"))[:6],
            }
        ]

    def _string_items(self, value: object) -> list[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str) and value.strip():
            return [item.strip() for item in re.split(r"[\n;；]+", value) if item.strip()]
        return []

    async def _assess_crawl_quality(
        self,
        db: AsyncSession,
        crawl_result: InsightCrawlResult,
    ) -> dict[str, Any]:
        title = insight_content_cleaner.clean_text(crawl_result.source_title) or ""
        readable = insight_content_cleaner.clean_readable_excerpt(crawl_result.markdown_content or crawl_result.snippet) or ""
        issues: list[str] = []
        score = 1.0

        if not title or title == "未命名情报":
            issues.append("标题缺失")
            score -= 0.2
        if len(readable) < 80:
            issues.append("正文过短")
            score -= 0.35
        if "页面需要安全验证" in readable:
            issues.append("安全验证页")
            score -= 0.55
        if self._looks_like_market_quote(title, readable):
            issues.append("疑似股价快讯")
            score -= 0.25

        duplicate = await self._find_similar_candidate(db, title)
        if duplicate:
            issues.append("标题高度相似")
            score -= 0.2

        score = min(max(score, 0), 1)
        return {
            "score": round(score, 2),
            "issues": issues,
            "auto_ignore": score < 0.35 or "安全验证页" in issues,
            "similar_candidate": duplicate,
            "readable_length": len(readable),
        }

    async def _find_similar_candidate(
        self,
        db: AsyncSession,
        title: str,
    ) -> dict[str, Any] | None:
        normalized_title = self._normalize_similarity_text(title)
        if len(normalized_title) < 8:
            return None
        statement = (
            select(InsightIntelligenceCandidate)
            .where(
                InsightIntelligenceCandidate.is_deleted == 0,
                InsightIntelligenceCandidate.status == "active",
            )
            .order_by(InsightIntelligenceCandidate.create_time.desc())
            .limit(200)
        )
        candidates = list((await db.exec(statement)).all())
        best: tuple[InsightIntelligenceCandidate, float] | None = None
        for candidate in candidates:
            other_title = self._normalize_similarity_text(candidate.candidate_title)
            if not other_title or other_title == normalized_title:
                continue
            ratio = SequenceMatcher(None, normalized_title, other_title).ratio()
            if ratio >= 0.9 and (best is None or ratio > best[1]):
                best = (candidate, ratio)
        if not best:
            return None
        candidate, ratio = best
        return {
            "candidate_id": candidate.id,
            "title": candidate.candidate_title,
            "similarity": round(ratio, 3),
        }

    def _normalize_similarity_text(self, value: str | None) -> str:
        text = insight_content_cleaner.clean_text(value) or ""
        text = re.sub(r"[\s·,，。！？!?:：;；'\"“”‘’（）()【】\[\]_-]+", "", text.lower())
        return text[:120]

    def _looks_like_market_quote(self, title: str, content: str) -> bool:
        text = f"{title}\n{content}"
        quote_keywords = ("成交额", "美股", "股票交易", "股价", "涨幅", "跌幅", "排第", "内部人股票")
        return sum(1 for keyword in quote_keywords if keyword in text) >= 2

    def _quality_tags(self, quality_report: dict[str, Any]) -> list[dict[str, Any]]:
        tags: list[dict[str, Any]] = []
        for issue in quality_report.get("issues") or []:
            if isinstance(issue, str):
                tags.append({"name": issue, "source": "quality_rule"})
        if quality_report.get("similar_candidate"):
            tags.append({"name": "可能重复", "source": "quality_rule"})
        if quality_report.get("auto_ignore"):
            tags.append({"name": "自动忽略", "source": "quality_rule"})
        return tags[:5]

    def _quality_adjusted_confidence(self, confidence: float, quality_report: dict[str, Any]) -> float:
        score = self._float_value(quality_report.get("score"), 1)
        adjusted = confidence * (0.55 + 0.45 * score)
        return min(max(adjusted, 0), 1)

    def _float_value(self, value: object, default: float) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return default
        return min(max(number, 0), 1)

    async def _get_existing_crawl_result(
        self,
        db: AsyncSession,
        crawl_result: InsightCrawlResult,
    ) -> InsightCrawlResult | None:
        if crawl_result.dedupe_hash:
            statement = select(InsightCrawlResult).where(
                InsightCrawlResult.dedupe_hash == crawl_result.dedupe_hash,
                InsightCrawlResult.status == InsightCrawlStatus.PARSED,
                InsightCrawlResult.is_deleted == 0,
            )
            existing = (await db.exec(statement)).first()
            if existing:
                return existing
        statement = select(InsightCrawlResult).where(
            InsightCrawlResult.source_url == crawl_result.source_url,
            InsightCrawlResult.status == InsightCrawlStatus.PARSED,
            InsightCrawlResult.is_deleted == 0,
        )
        return (await db.exec(statement)).first()

    async def _get_existing_candidate(
        self,
        db: AsyncSession,
        crawl_result_id: int,
    ) -> InsightIntelligenceCandidate | None:
        statement = select(InsightIntelligenceCandidate).where(
            InsightIntelligenceCandidate.crawl_result_id == crawl_result_id,
            InsightIntelligenceCandidate.is_deleted == 0,
        )
        return (await db.exec(statement)).first()

    def _format_error(self, exc: Exception) -> str:
        if isinstance(exc, httpx.HTTPStatusError):
            return f"Firecrawl HTTP {exc.response.status_code}: {exc.response.text[:500]}"
        if isinstance(exc, httpx.HTTPError):
            return f"Firecrawl 网络错误: {exc}"
        return str(exc)

    def _infer_subject_type(self, title: str, content: str) -> InsightSubjectType:
        text = f"{title}\n{content[:500]}".lower()
        if any(keyword in text for keyword in ("政策", "法规", "标准", "监管")):
            return InsightSubjectType.POLICY
        if any(keyword in text for keyword in ("行业", "趋势", "市场", "报告")):
            return InsightSubjectType.INDUSTRY
        if any(keyword in text for keyword in ("技术", "专利", "方案", "应用")):
            return InsightSubjectType.TECHNOLOGY
        if any(keyword in text for keyword in ("新品", "产品", "上市", "配方")):
            return InsightSubjectType.PRODUCT
        return InsightSubjectType.CUSTOM

    def _infer_subject_name(self, title: str) -> str | None:
        separators = ("：", ":", "｜", "|", "-", "_")
        for separator in separators:
            if separator in title:
                value = title.split(separator, 1)[0].strip()
                return value[:80] if value else None
        return None

    def _infer_intelligence_type(self, title: str, content: str) -> str:
        text = f"{title}\n{content[:500]}"
        if any(keyword in text for keyword in ("财报", "年报", "季报", "业绩")):
            return "财报公告"
        if any(keyword in text for keyword in ("新品", "上市", "发布", "上新")):
            return "新品情报"
        if any(keyword in text for keyword in ("政策", "法规", "标准", "监管")):
            return "政策法规"
        if any(keyword in text for keyword in ("方案", "应用", "技术", "专利")):
            return "应用方案"
        return "行业资讯"

    def _normalize_intelligence_type(self, value: object) -> str:
        text = str(value or "").strip()
        mapping = {
            "strategic_planning": "战略规划",
            "strategy": "战略规划",
            "marketing_strategy": "营销策略",
            "competitor_strategy": "竞品动态",
            "competitor": "竞品动态",
            "product_launch": "新品情报",
            "product_launch_failure": "新品情报",
            "new_product": "新品情报",
            "financial_report": "财报公告",
            "financial": "财报公告",
            "industry_news": "行业资讯",
            "industry": "行业资讯",
            "policy": "政策法规",
            "regulation": "政策法规",
            "application_solution": "应用方案",
            "technology": "应用方案",
            "business_operation": "经营动态",
            "operation": "经营动态",
            "risk_warning": "风险预警",
            "risk": "风险预警",
        }
        normalized = text.lower().replace("-", "_").replace(" ", "_")
        if normalized in mapping:
            return mapping[normalized]
        if re.fullmatch(r"[A-Za-z0-9_]+", text):
            return "行业资讯"
        return text[:50] if text else "行业资讯"

    def _suggest_tags(self, title: str, content: str) -> list[dict[str, Any]]:
        text = f"{title}\n{content[:1000]}"
        candidates = {
            "新品": ("新品", "上市", "上新", "发布"),
            "财报": ("财报", "年报", "季报", "业绩"),
            "政策": ("政策", "法规", "标准", "监管"),
            "行业趋势": ("趋势", "市场", "行业", "报告"),
            "应用方案": ("方案", "应用", "技术", "配方"),
            "食品": ("食品", "饮料", "茶饮", "营养"),
        }
        tags = []
        for tag, keywords in candidates.items():
            if any(keyword in text for keyword in keywords):
                tags.append({"name": tag, "source": "rule"})
        return tags[:6]


insight_crawl_service = InsightCrawlService()
