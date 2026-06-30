import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256
from typing import Any
from uuid import uuid4

from langchain_core.messages import HumanMessage, SystemMessage
from sqlmodel import func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.llm_factory import LLMFactory
from app.core.logger import logger
from app.models.agent.insight import (
    InsightCandidateReviewStatus,
    InsightAssetVector,
    InsightChannelAdapterRun,
    InsightCompany,
    InsightCrawlerChannel,
    InsightCrawlResult,
    InsightCrawlStatus,
    InsightDataSource,
    InsightIntelligenceAsset,
    InsightIntelligenceCandidate,
    InsightMonitorConfig,
    InsightSubjectType,
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
from app.services.agent.insight.crawler.channel_adapter_service import AdapterRunContext, insight_channel_adapter_service
from app.services.agent.insight.crawler.content_cleaner import insight_content_cleaner
from app.services.agent.insight.crawler.search_client import InsightSearchHit, baidu_search_client, bocha_search_client
from app.services.agent.insight.permission_service import insight_permission_service


@dataclass(slots=True)
class SearchFilterTrace:
    hits: list[InsightSearchHit]
    collected_count: int
    time_window_kept_count: int
    rule_kept_count: int
    dedupe_kept_count: int
    history_dedupe_kept_count: int
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
        await self._ensure_monitor_config_editable(db, request.monitor_config_id, user_id=user_id, is_admin=is_admin)
        task = InsightTask(
            task_uid=f"search_{uuid4().hex}",
            task_type="keyword_search_discovery",
            data_source_id=request.data_source_id,
            monitor_config_id=request.monitor_config_id,
            source_channel_id=request.source_channel_id,
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
            trace = await self._collect_hits(db, request)
            hits = trace.hits
            discovered_results = [self._to_discovered_result(task.id or 0, request, hit, user_id) for hit in hits]
            db.add_all(discovered_results)
            await db.commit()
            for result in discovered_results:
                await db.refresh(result)

            crawled_results = []
            candidates = []
            crawl_errors: list[dict[str, Any]] = []
            fallback_candidate_results: list[InsightCrawlResult] = []
            if request.create_candidate_from_hits and request.crawl_top_n == 0:
                candidates = await self._create_candidates_from_hits(db, discovered_results, request, user_id)
            for index, hit in enumerate(hits[: request.crawl_top_n]):
                try:
                    crawl_response = await insight_crawl_service.crawl_manual_url(
                        db,
                        InsightManualUrlCrawlRequest(
                            url=hit.url,
                            query_text=request.query,
                            data_source_id=request.data_source_id,
                            monitor_config_id=request.monitor_config_id,
                            source_channel_id=request.source_channel_id,
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
                    discovered_result = discovered_results[index] if index < len(discovered_results) else None
                    if discovered_result:
                        crawl_metadata = discovered_result.crawl_metadata or {}
                        crawl_metadata["crawl_fallback"] = {
                            "reason": "正文抓取失败，已基于搜索命中生成候选",
                            "error": str(exc)[:500],
                            "fallback_time": datetime.now().isoformat(),
                        }
                        discovered_result.crawl_metadata = crawl_metadata
                        db.add(discovered_result)
                        fallback_candidate_results.append(discovered_result)
                    crawl_errors.append(
                        {
                            "title": hit.title,
                            "url": hit.url,
                            "channel": self._enum_value(hit.channel),
                            "error": str(exc),
                        }
                    )
            if fallback_candidate_results:
                fallback_candidates = await self._create_candidates_from_hits(db, fallback_candidate_results, request, user_id)
                candidates.extend(fallback_candidates)

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
                "llm_filter_applied": trace.llm_filter_applied,
                "llm_filter_message": trace.llm_filter_message,
                "hit_ai_analysis_applied": bool(request.create_candidate_from_hits and request.crawl_top_n == 0 and candidates),
                "filter_summary": {
                    "source_hit_count": trace.collected_count,
                    "time_window_kept_count": trace.time_window_kept_count,
                    "rule_kept_count": trace.rule_kept_count,
                    "dedupe_kept_count": trace.dedupe_kept_count,
                    "history_dedupe_kept_count": trace.history_dedupe_kept_count,
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
            await self._update_adapter_run_counts(db, hits, trace, candidates)
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

    async def _update_adapter_run_counts(
        self,
        db: AsyncSession,
        hits: list[InsightSearchHit],
        trace: SearchFilterTrace,
        candidates: list[InsightIntelligenceCandidate],
    ) -> None:
        adapter_run_ids = sorted(
            {
                int((hit.raw or {}).get("adapter_run_id"))
                for hit in hits
                if isinstance((hit.raw or {}).get("adapter_run_id"), int)
                or str((hit.raw or {}).get("adapter_run_id") or "").isdigit()
            }
        )
        if not adapter_run_ids:
            return
        rows = list(
            (
                await db.exec(
                    select(InsightChannelAdapterRun).where(
                        InsightChannelAdapterRun.id.in_(adapter_run_ids),
                        InsightChannelAdapterRun.is_deleted == 0,
                    )
                )
            ).all()
        )
        per_run_kept: dict[int, int] = {run_id: 0 for run_id in adapter_run_ids}
        for hit in hits:
            raw_run_id = (hit.raw or {}).get("adapter_run_id")
            if raw_run_id is not None and str(raw_run_id).isdigit():
                per_run_kept[int(raw_run_id)] = per_run_kept.get(int(raw_run_id), 0) + 1
        for row in rows:
            row.kept_count = per_run_kept.get(row.id or 0, row.kept_count)
            row.dedupe_count = max(trace.dedupe_kept_count - trace.history_dedupe_kept_count, 0)
            row.candidate_count = len(candidates)
            row.formal_count = len(
                [candidate for candidate in candidates if candidate.review_status == InsightCandidateReviewStatus.PROMOTED]
            )
            candidate_ids = [candidate.id for candidate in candidates if candidate.id]
            if candidate_ids:
                row.vectorized_count = (
                    await db.exec(
                        select(func.count())
                        .select_from(InsightAssetVector)
                        .join(InsightIntelligenceAsset, InsightIntelligenceAsset.id == InsightAssetVector.asset_id)
                        .where(
                            InsightIntelligenceAsset.candidate_id.in_(candidate_ids),
                            InsightIntelligenceAsset.is_deleted == 0,
                            InsightAssetVector.is_deleted == 0,
                        )
                    )
                ).one()
            row.update_time = datetime.now()

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

    async def _ensure_monitor_config_editable(
        self,
        db: AsyncSession,
        monitor_config_id: int | None,
        *,
        user_id: int | None,
        is_admin: bool,
    ) -> None:
        if not monitor_config_id or is_admin:
            return
        row = (
            await db.exec(
                select(InsightMonitorConfig).where(
                    InsightMonitorConfig.id == monitor_config_id,
                    InsightMonitorConfig.is_deleted == 0,
                )
            )
        ).first()
        if not row or (row.owner_user_id is not None and row.owner_user_id != user_id and row.visibility_scope != "public"):
            raise ValueError("监测配置不存在或无权采集")

    async def _collect_hits(self, db: AsyncSession, request: InsightSearchDiscoveryRequest) -> SearchFilterTrace:
        hits: list[InsightSearchHit] = []
        errors: list[str] = []
        channels = {channel.lower() for channel in request.channels}
        per_channel_count = max(request.max_results, 1)
        if not channels:
            raise ValueError("未配置搜索通道")

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

        built_in_channels = {"baidu", "baidu_news", "bocha", "bocha_news"}
        for channel_code in sorted(channels - built_in_channels):
            try:
                hits.extend(
                    await insight_channel_adapter_service.search(
                        db,
                        channel_code,
                        request.query,
                        context=AdapterRunContext(
                            channel_id=request.source_channel_id,
                            monitor_config_id=request.monitor_config_id,
                            run_type=getattr(request, "run_type", None) or "manual_test",
                            since=self._freshness_cutoff(request.freshness) or datetime.now() - timedelta(days=15),
                            limit=per_channel_count,
                        ),
                    )
                )
            except Exception as exc:
                errors.append(f"{channel_code} 适配器失败: {exc}")

        time_filtered_hits, time_rejected = self._apply_time_window_filter(hits, request)
        filtered_hits, rule_rejected = self._apply_rule_filter(time_filtered_hits, request)
        deduped, dedupe_rejected = self._dedupe_hits(filtered_hits)
        new_hits, history_dedupe_rejected = await self._dedupe_existing_hits(db, deduped)
        llm_hits, llm_rejected, llm_applied, llm_message = await self._apply_llm_filter(new_hits, request)
        final_hits = llm_hits[: request.max_results]
        limit_rejected = [
            self._rejection_item(hit, "limit", f"超过本次发现数量上限 {request.max_results}，未进入后续抓取")
            for hit in llm_hits[request.max_results :]
        ]
        rejected_items = time_rejected + rule_rejected + dedupe_rejected + history_dedupe_rejected + llm_rejected + limit_rejected

        if not final_hits and errors and not hits and not rejected_items and not self._is_empty_result_error(errors):
            raise ValueError("；".join(errors))
        return SearchFilterTrace(
            hits=final_hits,
            collected_count=len(hits),
            time_window_kept_count=len(time_filtered_hits),
            rule_kept_count=len(filtered_hits),
            dedupe_kept_count=len(deduped),
            history_dedupe_kept_count=len(new_hits),
            llm_kept_count=len(llm_hits),
            rejected_items=rejected_items,
            kept_items=[self._kept_item(hit) for hit in final_hits],
            channel_errors=errors,
            llm_filter_applied=llm_applied,
            llm_filter_message=llm_message if final_hits else llm_message or "搜索完成，但没有命中可进入候选池的结果",
        )

    def _is_empty_result_error(self, errors: list[str]) -> bool:
        if not errors:
            return False
        empty_result_markers = (
            "结果已被筛选规则全部过滤",
            "没有命中可进入候选池",
            "未找到可用结果",
            "no results",
            "empty result",
        )
        hard_failure_markers = (
            "未配置",
            "401",
            "403",
            "429",
            "500",
            "502",
            "503",
            "504",
            "timeout",
            "timed out",
            "连接",
            "鉴权",
            "api key",
        )
        joined = "；".join(errors).lower()
        if any(marker.lower() in joined for marker in hard_failure_markers):
            return False
        return any(marker.lower() in joined for marker in empty_result_markers)

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

    def _apply_time_window_filter(
        self,
        hits: list[InsightSearchHit],
        request: InsightSearchDiscoveryRequest,
    ) -> tuple[list[InsightSearchHit], list[dict[str, Any]]]:
        cutoff = self._freshness_cutoff(request.freshness)
        if cutoff is None:
            return hits, []

        filtered: list[InsightSearchHit] = []
        rejected: list[dict[str, Any]] = []
        for hit in hits:
            if hit.published_at is None or hit.published_at >= cutoff:
                filtered.append(hit)
                continue
            rejected.append(
                self._rejection_item(
                    hit,
                    "time_window",
                    f"发布时间早于本次时间窗（{cutoff:%Y-%m-%d} 之后）",
                )
            )
        return filtered, rejected

    def _freshness_cutoff(self, freshness: str | None) -> datetime | None:
        value = (freshness or "").strip().lower()
        if value in {"halfmonth", "half_month", "15d", "recent15d", "recent_15d"}:
            return datetime.now() - timedelta(days=15)
        if value in {"oneweek", "one_week", "week", "7d"}:
            return datetime.now() - timedelta(days=7)
        if value in {"oneday", "one_day", "day", "24h"}:
            return datetime.now() - timedelta(days=1)
        if value in {"onemonth", "one_month", "month", "30d"}:
            return datetime.now() - timedelta(days=30)
        return None

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
            key = self._normalize_url_key(hit.url)
            if not key:
                rejected.append(self._rejection_item(hit, "dedupe", "缺少 URL，无法入库去重"))
                continue
            if key in seen:
                rejected.append(self._rejection_item(hit, "dedupe", "URL 重复，已保留首条结果"))
                continue
            seen.add(key)
            deduped.append(hit)
        return deduped, rejected

    async def _dedupe_existing_hits(
        self,
        db: AsyncSession,
        hits: list[InsightSearchHit],
    ) -> tuple[list[InsightSearchHit], list[dict[str, Any]]]:
        if not hits:
            return hits, []
        current_keys = {self._normalize_url_key(hit.url) for hit in hits if self._normalize_url_key(hit.url)}
        if not current_keys:
            return [], [self._rejection_item(hit, "history_dedupe", "缺少 URL，无法执行历史去重") for hit in hits]

        existing_urls = list(
            (
                await db.exec(
                    select(InsightCrawlResult.source_url).where(
                        InsightCrawlResult.is_deleted == 0,
                        InsightCrawlResult.source_url != "",
                    )
                )
            ).all()
        )
        existing_keys = {
            normalized
            for url in existing_urls
            if (normalized := self._normalize_url_key(url))
        }

        kept: list[InsightSearchHit] = []
        rejected: list[dict[str, Any]] = []
        for hit in hits:
            key = self._normalize_url_key(hit.url)
            if not key:
                rejected.append(self._rejection_item(hit, "history_dedupe", "缺少 URL，无法执行历史去重"))
                continue
            if key in existing_keys:
                rejected.append(self._rejection_item(hit, "history_dedupe", "历史已采集过相同链接，跳过 AI 筛选和入库"))
                continue
            kept.append(hit)
        return kept, rejected

    def _normalize_url_key(self, url: str | None) -> str:
        if not url:
            return ""
        try:
            return insight_content_cleaner.normalize_url(url).rstrip("/")
        except Exception:
            return str(url).strip().rstrip("/")

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
        normalized_url = self._normalize_url_key(hit.url)
        dedupe_text = f"search_url\n{normalized_url or hit.url}"
        return InsightCrawlResult(
            task_id=task_id,
            data_source_id=request.data_source_id,
            monitor_config_id=request.monitor_config_id,
            source_channel_id=request.source_channel_id,
            channel=hit.channel,
            query_text=self._truncate(request.query, 500),
            source_url=self._truncate(hit.url, 1000) or hit.url[:1000],
            source_title=self._truncate(hit.title, 500),
            snippet=self._truncate(hit.snippet, 2000),
            published_at=hit.published_at,
            dedupe_hash=sha256(dedupe_text.encode("utf-8")).hexdigest(),
            crawl_metadata={
                "monitor_config_id": request.monitor_config_id,
                "source_channel_id": request.source_channel_id,
                "normalized_url": normalized_url,
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

    def _truncate(self, value: str | None, limit: int) -> str | None:
        if value is None:
            return None
        text = str(value)
        return text if len(text) <= limit else text[: limit - 1]

    async def _create_candidates_from_hits(
        self,
        db: AsyncSession,
        discovered_results: list[InsightCrawlResult],
        request: InsightSearchDiscoveryRequest,
        user_id: int | None,
    ) -> list[InsightIntelligenceCandidate]:
        if not discovered_results:
            return []
        data_source = None
        company = None
        monitor_config = None
        if request.monitor_config_id:
            monitor_config = (
                await db.exec(
                    select(InsightMonitorConfig).where(
                        InsightMonitorConfig.id == request.monitor_config_id,
                        InsightMonitorConfig.is_deleted == 0,
                    )
                )
            ).first()
            if monitor_config and monitor_config.object_type == "company" and monitor_config.object_id:
                company = (
                    await db.exec(
                        select(InsightCompany).where(
                            InsightCompany.id == monitor_config.object_id,
                            InsightCompany.is_deleted == 0,
                        )
                    )
                ).first()
        if request.data_source_id:
            data_source = (await db.exec(select(InsightDataSource).where(InsightDataSource.id == request.data_source_id))).first()
            if not company and data_source and data_source.company_id:
                company = (await db.exec(select(InsightCompany).where(InsightCompany.id == data_source.company_id))).first()

        analyses = await self._analyze_search_hit_candidates(discovered_results, request)
        candidates: list[InsightIntelligenceCandidate] = []
        for result in discovered_results:
            existing = (
                await db.exec(
                    select(InsightIntelligenceCandidate).where(
                        InsightIntelligenceCandidate.crawl_result_id == result.id,
                        InsightIntelligenceCandidate.is_deleted == 0,
                    )
                )
            ).first()
            if existing:
                candidates.append(existing)
                continue

            title = result.source_title or request.query
            analysis = analyses.get(result.id or 0, {})
            summary = (
                str(analysis.get("summary") or "").strip()
                or result.snippet
                or f"搜索发现与“{request.query}”相关的公开信息，等待后续正文抓取和 AI 深化。"
            )
            confidence = self._float_value(analysis.get("confidence"), 0.58)
            relevance_score = self._float_value(analysis.get("relevance_score"), confidence)
            keep = bool(analysis.get("keep", True))
            intelligence_type = str(analysis.get("intelligence_type") or "").strip() or self._infer_type_from_query(request.query)
            llm_tags = [{"name": item[:30], "source": "llm"} for item in self._string_items(analysis.get("tags"))[:6]]
            if not llm_tags:
                llm_tags = [{"name": "搜索发现", "source": "search_hit"}]
            crawl_fallback = (result.crawl_metadata or {}).get("crawl_fallback") if isinstance(result.crawl_metadata, dict) else None
            fallback_tags = (
                [
                    {
                        "name": "正文抓取待补",
                        "source": "crawl_fallback",
                        "reason": str(crawl_fallback.get("reason") or "")[:200],
                        "error": str(crawl_fallback.get("error") or "")[:300],
                    }
                ]
                if isinstance(crawl_fallback, dict)
                else []
            )
            candidate = InsightIntelligenceCandidate(
                crawl_result_id=result.id or 0,
                candidate_title=title[:500],
                candidate_summary=summary[:1000],
                subject_type=InsightSubjectType.COMPANY if company else InsightSubjectType.CUSTOM,
                subject_name=(company.short_name or company.name)[:200] if company else (monitor_config.object_name[:200] if monitor_config and monitor_config.object_name else request.query[:200]),
                company_id=company.id if company else (data_source.company_id if data_source else None),
                intelligence_type=intelligence_type[:50],
                suggested_tags=[
                    *llm_tags,
                    *fallback_tags,
                    {"name": self._enum_value(result.channel), "source": "search_channel"},
                    {
                        "name": "AI搜索初筛",
                        "source": "llm_analysis",
                        "sentiment": self._sentiment_value(analysis.get("sentiment")),
                        "sentiment_reason": str(analysis.get("sentiment_reason") or analysis.get("reason") or "").strip()[:500],
                        "opportunities": self._string_items(analysis.get("opportunities"))[:6],
                        "risks": self._string_items(analysis.get("risks"))[:6],
                        "keep": keep,
                        "relevance_score": round(relevance_score, 4),
                        "analysis_scope": "search_hit",
                    },
                ],
                confidence=min(max(confidence, 0), 1),
                review_status=InsightCandidateReviewStatus.PENDING,
                status="active",
                create_by=str(user_id) if user_id else None,
                update_by=str(user_id) if user_id else None,
            )
            db.add(candidate)
            candidates.append(candidate)
        await db.commit()
        for candidate in candidates:
            await db.refresh(candidate)
        from app.services.agent.insight.ai_review_service import insight_ai_review_service

        await insight_ai_review_service.review_candidates(
            db,
            [candidate.id for candidate in candidates if candidate.id],
            user_id=user_id,
            is_admin=True,
        )
        for candidate in candidates:
            await db.refresh(candidate)
        return candidates

    async def _analyze_search_hit_candidates(
        self,
        discovered_results: list[InsightCrawlResult],
        request: InsightSearchDiscoveryRequest,
    ) -> dict[int, dict[str, Any]]:
        if not discovered_results:
            return {}
        payload = {
            "query": request.query,
            "filterPrompt": request.filter_prompt or self._default_hit_analysis_prompt(),
            "items": [
                {
                    "id": result.id,
                    "title": result.source_title,
                    "url": result.source_url,
                    "snippet": result.snippet,
                    "published_at": result.published_at.isoformat() if result.published_at else None,
                    "channel": self._enum_value(result.channel),
                }
                for result in discovered_results[:20]
                if result.id is not None
            ],
        }
        if not payload["items"]:
            return {}
        try:
            response = await LLMFactory.safe_invoke(
                [
                    SystemMessage(
                        content=(
                            "你是研发营销市场洞察平台的搜索情报初筛助手。"
                            "你只能基于搜索标题、URL、摘要和发布时间做保守判断，不得编造正文细节。"
                            "请判断每条结果是否与食品饮料、功能糖/淀粉糖、植物蛋白、配料原料、客户/竞对、政策、专利、研发营销洞察相关。"
                            "输出严格 JSON：{\"items\":[{\"id\":1,\"keep\":true,\"relevance_score\":0.8,\"summary\":\"...\",\"intelligence_type\":\"行业资讯\",\"tags\":[\"...\"],\"sentiment\":\"neutral\",\"sentiment_reason\":\"...\",\"opportunities\":[\"...\"],\"risks\":[\"...\"],\"confidence\":0.75,\"reason\":\"...\"}]}。"
                            "summary 用中文 1-2 句，必须明确这是基于公开搜索摘要的初筛结论；"
                            "sentiment 只能为 positive、neutral、negative、mixed；confidence 和 relevance_score 为 0 到 1。"
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
            logger.warning(f"Insight 搜索命中 AI 初筛失败，使用规则候选继续：{exc}")
            return {}

        content = getattr(response, "content", response)
        if isinstance(content, list):
            content = "".join(str(item) for item in content)
        if not isinstance(content, str):
            return {}
        try:
            parsed = json.loads(self._strip_json_fence(content))
        except json.JSONDecodeError as exc:
            logger.warning(f"Insight 搜索命中 AI 初筛 JSON 解析失败，使用规则候选继续：{exc}")
            return {}
        items = parsed.get("items") if isinstance(parsed, dict) else None
        if not isinstance(items, list):
            return {}
        analyses: dict[int, dict[str, Any]] = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            try:
                result_id = int(item.get("id"))
            except (TypeError, ValueError):
                continue
            analyses[result_id] = item
        return analyses

    def _default_hit_analysis_prompt(self) -> str:
        return (
            "保留与食品饮料、功能糖、淀粉糖、植物蛋白、配料原料、竞对、客户新品、政策法规、专利技术、"
            "研发营销机会相关的公开信息；过滤验证码、图片搜索、百科泛信息、无业务价值页面和明显跨行业噪声。"
        )

    def _sentiment_value(self, value: object) -> str:
        sentiment = str(value or "neutral").strip()
        return sentiment if sentiment in {"positive", "neutral", "negative", "mixed"} else "neutral"

    def _string_items(self, value: object) -> list[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str) and value.strip():
            return [item.strip() for item in re.split(r"[\n,，;；]+", value) if item.strip()]
        return []

    def _infer_type_from_query(self, query: str) -> str:
        if "专利" in query or "技术" in query:
            return "研发技术"
        if "政策" in query or "法规" in query:
            return "政策法规"
        if "新品" in query or "配料" in query:
            return "新品情报"
        if "业绩" in query or "投资" in query or "融资" in query or "年报" in query:
            return "经营动态"
        if "电商" in query or "旗舰店" in query:
            return "电商监测"
        return "行业资讯"

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
