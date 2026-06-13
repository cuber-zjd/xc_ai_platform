import json
import re
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from typing import Any
from uuid import uuid4

from langchain_core.messages import HumanMessage, SystemMessage
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.llm_factory import LLMFactory
from app.core.logger import logger
from app.models.agent.insight import (
    InsightCrawlerChannel,
    InsightCrawlResult,
    InsightCrawlStatus,
    InsightDataSource,
    InsightTask,
    InsightTaskStatus,
)
from app.schemas.agent.insight.crawl import (
    InsightManualUrlCrawlRequest,
    InsightSearchDiscoveryRequest,
    InsightSearchDiscoveryResponse,
    InsightSearchHitRead,
)
from app.services.agent.insight.crawler.crawl_service import insight_crawl_service
from app.services.agent.insight.crawler.search_client import InsightSearchHit, baidu_search_client, bocha_search_client
from app.services.agent.insight.permission_service import insight_permission_service


@dataclass(slots=True)
class SearchFilterTrace:
    hits: list[InsightSearchHit]
    collected_count: int
    rule_kept_count: int
    dedupe_kept_count: int
    llm_kept_count: int
    rejected_items: list[dict[str, Any]]
    kept_items: list[dict[str, Any]]
    channel_errors: list[str]
    llm_filter_applied: bool = False
    llm_filter_message: str | None = None


class InsightSearchDiscoveryService:
    async def search_and_crawl(
        self,
        db: AsyncSession,
        request: InsightSearchDiscoveryRequest,
        user_id: int | None,
        *,
        is_admin: bool = False,
    ) -> InsightSearchDiscoveryResponse:
        await self._ensure_data_source_editable(db, request.data_source_id, user_id=user_id, is_admin=is_admin)
        task = InsightTask(
            task_uid=f"search_{uuid4().hex}",
            task_type="keyword_search_discovery",
            data_source_id=request.data_source_id,
            status=InsightTaskStatus.RUNNING,
            progress=10,
            started_at=datetime.now(),
            input_payload=request.model_dump() | {"user_id": user_id},
            create_by=str(user_id) if user_id else None,
            update_by=str(user_id) if user_id else None,
        )
        db.add(task)
        await db.commit()
        await db.refresh(task)

        try:
            trace = await self._collect_hits(request)
            hits = trace.hits
            discovered_results = [self._to_discovered_result(task.id or 0, request, hit, user_id) for hit in hits]
            db.add_all(discovered_results)
            await db.commit()
            for result in discovered_results:
                await db.refresh(result)

            crawled_results = []
            candidates = []
            crawl_errors: list[dict[str, Any]] = []
            for hit in hits[: request.crawl_top_n]:
                try:
                    crawl_response = await insight_crawl_service.crawl_manual_url(
                        db,
                        InsightManualUrlCrawlRequest(
                            url=hit.url,
                            query_text=request.query,
                            data_source_id=request.data_source_id,
                        ),
                        user_id,
                        is_admin=is_admin,
                    )
                    if hit.published_at and not crawl_response.crawl_result.published_at:
                        crawl_response.crawl_result.published_at = hit.published_at
                        crawl_metadata = crawl_response.crawl_result.crawl_metadata or {}
                        crawl_metadata["search_published_at"] = hit.published_at.isoformat()
                        crawl_response.crawl_result.crawl_metadata = crawl_metadata
                        db.add(crawl_response.crawl_result)
                        await db.commit()
                    crawled_results.append(crawl_response.crawl_result)
                    candidates.append(crawl_response.candidate)
                except Exception as exc:
                    crawl_errors.append(
                        {
                            "title": hit.title,
                            "url": hit.url,
                            "channel": self._enum_value(hit.channel),
                            "error": str(exc),
                        }
                    )

            task.status = InsightTaskStatus.SUCCESS
            task.progress = 100
            task.finished_at = datetime.now()
            task.output_payload = {
                "hit_count": len(hits),
                "discovered_result_ids": [item.id for item in discovered_results],
                "crawled_result_ids": [item.id for item in crawled_results],
                "candidate_ids": [item.id for item in candidates],
                "rule_filter_enabled": bool(request.include_keywords or request.exclude_keywords),
                "llm_filter_configured": bool(request.enable_llm_filter and request.filter_prompt),
                "filter_summary": {
                    "source_hit_count": trace.collected_count,
                    "rule_kept_count": trace.rule_kept_count,
                    "dedupe_kept_count": trace.dedupe_kept_count,
                    "llm_kept_count": trace.llm_kept_count,
                    "final_hit_count": len(hits),
                    "rule_filter_enabled": bool(request.include_keywords or request.exclude_keywords),
                    "llm_filter_configured": bool(request.enable_llm_filter and request.filter_prompt),
                    "llm_filter_applied": trace.llm_filter_applied,
                    "llm_filter_message": trace.llm_filter_message,
                },
                "kept_items": trace.kept_items,
                "rejected_items": trace.rejected_items[:80],
                "channel_errors": trace.channel_errors,
                "hit_items": [self._kept_item(hit) for hit in hits],
                "crawled_items": [self._crawl_item(item) for item in crawled_results],
                "candidate_items": [self._candidate_item(item) for item in candidates],
                "crawl_errors": crawl_errors,
            }
            await db.commit()
            await db.refresh(task)

            return InsightSearchDiscoveryResponse(
                task=task,
                hits=[self._to_hit_read(hit) for hit in hits],
                discovered_results=discovered_results,
                crawled_results=crawled_results,
                candidates=candidates,
            )
        except Exception as exc:
            task.status = InsightTaskStatus.FAILED
            task.progress = 100
            task.finished_at = datetime.now()
            task.error_message = str(exc)
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

    async def _collect_hits(self, request: InsightSearchDiscoveryRequest) -> SearchFilterTrace:
        hits: list[InsightSearchHit] = []
        errors: list[str] = []
        channels = {channel.lower() for channel in request.channels}
        per_channel_count = max(request.max_results, 1)

        if "baidu" in channels:
            try:
                hits.extend(await baidu_search_client.search(request.query, per_channel_count))
            except Exception as exc:
                errors.append(f"百度搜索失败: {exc}")

        if "baidu_news" in channels:
            try:
                hits.extend(await baidu_search_client.search_news(request.query, per_channel_count))
            except Exception as exc:
                errors.append(f"百度资讯搜索失败: {exc}")

        if "bocha" in channels:
            try:
                hits.extend(await bocha_search_client.search(request.query, per_channel_count, request.freshness))
            except Exception as exc:
                errors.append(f"博查搜索失败: {exc}")

        if "bocha_news" in channels:
            try:
                hits.extend(await self._search_bocha_news(request, per_channel_count))
            except Exception as exc:
                errors.append(f"博查资讯搜索失败: {exc}")

        filtered_hits, rule_rejected = self._apply_rule_filter(hits, request)
        deduped, dedupe_rejected = self._dedupe_hits(filtered_hits)
        llm_hits, llm_rejected, llm_applied, llm_message = await self._apply_llm_filter(deduped, request)
        final_hits = llm_hits[: request.max_results]
        limit_rejected = [
            self._rejection_item(hit, "limit", f"超过本次发现数量上限 {request.max_results}，未进入后续抓取")
            for hit in llm_hits[request.max_results :]
        ]
        rejected_items = rule_rejected + dedupe_rejected + llm_rejected + limit_rejected

        if final_hits:
            return SearchFilterTrace(
                hits=final_hits,
                collected_count=len(hits),
                rule_kept_count=len(filtered_hits),
                dedupe_kept_count=len(deduped),
                llm_kept_count=len(llm_hits),
                rejected_items=rejected_items,
                kept_items=[self._kept_item(hit) for hit in final_hits],
                channel_errors=errors,
                llm_filter_applied=llm_applied,
                llm_filter_message=llm_message,
            )
        if errors:
            raise ValueError("；".join(errors))
        raise ValueError("未启用可用的搜索通道，或结果已被筛选规则全部过滤")

    async def _search_bocha_news(
        self,
        request: InsightSearchDiscoveryRequest,
        count: int,
    ) -> list[InsightSearchHit]:
        bocha_hits = await bocha_search_client.search(request.query, count, request.freshness)
        return [
            InsightSearchHit(
                channel=InsightCrawlerChannel.BOCHA_NEWS,
                title=hit.title,
                url=hit.url,
                snippet=hit.snippet,
                published_at=hit.published_at,
                raw=(hit.raw or {}) | {"source_channel": "bocha_news"},
            )
            for hit in bocha_hits
        ]

    def _apply_rule_filter(
        self,
        hits: list[InsightSearchHit],
        request: InsightSearchDiscoveryRequest,
    ) -> tuple[list[InsightSearchHit], list[dict[str, Any]]]:
        include_keywords = [item.strip().lower() for item in request.include_keywords if item.strip()]
        exclude_keywords = [item.strip().lower() for item in request.exclude_keywords if item.strip()]
        if not include_keywords and not exclude_keywords:
            return hits, []

        filtered: list[InsightSearchHit] = []
        rejected: list[dict[str, Any]] = []
        for hit in hits:
            text = f"{hit.title}\n{hit.snippet or ''}\n{hit.url}".lower()
            matched_include = [keyword for keyword in include_keywords if keyword in text]
            matched_exclude = [keyword for keyword in exclude_keywords if keyword in text]
            include_ok = not include_keywords or bool(matched_include)
            exclude_hit = bool(matched_exclude)
            if include_ok and not exclude_hit:
                filtered.append(hit)
                continue

            reason_parts: list[str] = []
            if not include_ok:
                reason_parts.append(f"未命中必须包含词：{'、'.join(include_keywords)}")
            if exclude_hit:
                reason_parts.append(f"命中排除词：{'、'.join(matched_exclude)}")
            rejected.append(self._rejection_item(hit, "rule", "；".join(reason_parts)))
        return filtered, rejected

    def _dedupe_hits(self, hits: list[InsightSearchHit]) -> tuple[list[InsightSearchHit], list[dict[str, Any]]]:
        deduped: list[InsightSearchHit] = []
        rejected: list[dict[str, Any]] = []
        seen: set[str] = set()
        for hit in hits:
            key = hit.url.strip()
            if not key:
                rejected.append(self._rejection_item(hit, "dedupe", "缺少 URL，无法入库去重"))
                continue
            if key in seen:
                rejected.append(self._rejection_item(hit, "dedupe", "URL 重复，已保留首条结果"))
                continue
            seen.add(key)
            deduped.append(hit)
        return deduped, rejected

    async def _apply_llm_filter(
        self,
        hits: list[InsightSearchHit],
        request: InsightSearchDiscoveryRequest,
    ) -> tuple[list[InsightSearchHit], list[dict[str, Any]], bool, str | None]:
        if not request.enable_llm_filter or not request.filter_prompt:
            return hits, [], False, "未启用 LLM 筛选"
        if not hits:
            return hits, [], False, "没有可供 LLM 筛选的搜索结果"

        min_score = request.llm_min_score if request.llm_min_score is not None else 0.6
        payload = {
            "query": request.query,
            "filterPrompt": request.filter_prompt,
            "minScore": min_score,
            "items": [
                {
                    "index": index,
                    "channel": self._enum_value(hit.channel),
                    "title": hit.title,
                    "url": hit.url,
                    "snippet": hit.snippet,
                }
                for index, hit in enumerate(hits[:20])
            ],
        }
        try:
            response = await LLMFactory.safe_invoke(
                [
                    SystemMessage(
                        content=(
                            "你是研发营销市场洞察平台的资讯筛选助手。"
                            "请根据用户筛选要求判断每条搜索结果是否值得进入抓取。"
                            "只输出严格 JSON，格式为 {\"decisions\":[{\"index\":0,\"keep\":true,\"score\":0.8,\"reason\":\"...\"}]}。"
                            "score 取 0 到 1，reason 使用中文且不超过 40 字。"
                        )
                    ),
                    HumanMessage(content=json.dumps(payload, ensure_ascii=False)),
                ],
                capability="complex-reasoning",
                temperature=0,
                json_mode=True,
                max_retries=2,
            )
        except Exception as exc:
            logger.warning(f"Insight LLM 筛选调用失败，按保留策略继续采集：{exc}")
            return hits, [], False, f"LLM 筛选失败，已按保留策略继续：{exc}"

        content = getattr(response, "content", response)
        if isinstance(content, list):
            content = "".join(str(item) for item in content)
        if not isinstance(content, str):
            return hits, [], False, "LLM 筛选返回非文本内容，已按保留策略继续"

        try:
            decisions = json.loads(self._strip_json_fence(content)).get("decisions", [])
        except (json.JSONDecodeError, AttributeError) as exc:
            logger.warning(f"Insight LLM 筛选 JSON 解析失败，按保留策略继续：{exc}")
            return hits, [], False, f"LLM 筛选结果解析失败，已按保留策略继续：{exc}"

        decision_map = {
            int(item["index"]): item
            for item in decisions
            if isinstance(item, dict) and isinstance(item.get("index"), int)
        }
        kept: list[InsightSearchHit] = []
        rejected: list[dict[str, Any]] = []
        for index, hit in enumerate(hits):
            decision = decision_map.get(index)
            if decision is None:
                kept.append(hit)
                continue
            score = self._float_value(decision.get("score"), 1)
            keep = bool(decision.get("keep")) and score >= min_score
            reason = str(decision.get("reason") or "LLM 判定相关性不足")
            if keep:
                kept.append(hit)
            else:
                rejected.append(self._rejection_item(hit, "llm", f"{reason}（得分 {score:.2f}）"))
        return kept, rejected, True, f"LLM 已完成判分，阈值 {min_score:.2f}"

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

    def _kept_item(self, hit: InsightSearchHit) -> dict[str, Any]:
        return {
            "channel": self._enum_value(hit.channel),
            "title": hit.title,
            "url": hit.url,
            "snippet": hit.snippet,
            "published_at": hit.published_at.isoformat() if hit.published_at else None,
        }

    def _crawl_item(self, result: InsightCrawlResult) -> dict[str, Any]:
        return {
            "id": result.id,
            "channel": self._enum_value(result.channel),
            "title": result.source_title,
            "url": result.source_url,
            "snippet": result.snippet,
            "published_at": result.published_at.isoformat() if result.published_at else None,
            "status": self._enum_value(result.status),
        }

    def _candidate_item(self, candidate: Any) -> dict[str, Any]:
        return {
            "id": getattr(candidate, "id", None),
            "title": getattr(candidate, "candidate_title", None),
            "summary": getattr(candidate, "candidate_summary", None),
            "subject_type": getattr(getattr(candidate, "subject_type", None), "value", getattr(candidate, "subject_type", None)),
            "subject_name": getattr(candidate, "subject_name", None),
            "intelligence_type": getattr(candidate, "intelligence_type", None),
            "confidence": getattr(candidate, "confidence", None),
            "review_status": self._enum_value(getattr(candidate, "review_status", None)),
            "suggested_tags": getattr(candidate, "suggested_tags", None),
        }

    def _enum_value(self, value: Any) -> str:
        enum_value = getattr(value, "value", value)
        return str(enum_value) if enum_value is not None else ""

    def _rejection_item(self, hit: InsightSearchHit, stage: str, reason: str) -> dict[str, Any]:
        return {
            "stage": stage,
            "reason": reason,
            "channel": self._enum_value(hit.channel),
            "title": hit.title,
            "url": hit.url,
            "snippet": hit.snippet,
        }

    def _to_discovered_result(
        self,
        task_id: int,
        request: InsightSearchDiscoveryRequest,
        hit: InsightSearchHit,
        user_id: int | None,
    ) -> InsightCrawlResult:
        dedupe_text = f"{self._enum_value(hit.channel)}\n{request.query}\n{hit.url}\n{hit.title}"
        return InsightCrawlResult(
            task_id=task_id,
            data_source_id=request.data_source_id,
            channel=hit.channel,
            query_text=request.query,
            source_url=hit.url,
            source_title=hit.title,
            snippet=hit.snippet,
            published_at=hit.published_at,
            dedupe_hash=sha256(dedupe_text.encode("utf-8")).hexdigest(),
            crawl_metadata={
                "raw": hit.raw or {},
                "filter": {
                    "include_keywords": request.include_keywords,
                    "exclude_keywords": request.exclude_keywords,
                    "llm_filter_configured": bool(request.enable_llm_filter and request.filter_prompt),
                },
            },
            status=InsightCrawlStatus.DISCOVERED,
            create_by=str(user_id) if user_id else None,
            update_by=str(user_id) if user_id else None,
        )

    def _to_hit_read(self, hit: InsightSearchHit) -> InsightSearchHitRead:
        return InsightSearchHitRead(
            channel=self._enum_value(hit.channel),
            title=hit.title,
            url=hit.url,
            snippet=hit.snippet,
            published_at=hit.published_at,
            raw=hit.raw,
        )


insight_search_discovery_service = InsightSearchDiscoveryService()
