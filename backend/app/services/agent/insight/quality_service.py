from collections import Counter, defaultdict
from datetime import datetime
from typing import Any

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.agent.insight import (
    InsightCrawlResult,
    InsightDataSource,
    InsightIntelligenceCandidate,
    InsightReviewRecord,
    InsightTask,
    InsightTaskStatus,
)
from app.schemas.agent.insight.quality import (
    InsightQualityMetric,
    InsightQualityOverview,
    InsightQualityReason,
    InsightQualitySourceMetric,
)


class InsightQualityService:
    async def get_overview(self, db: AsyncSession) -> InsightQualityOverview:
        tasks = (await db.exec(select(InsightTask).where(InsightTask.is_deleted == 0))).all()
        candidates = (await db.exec(select(InsightIntelligenceCandidate).where(InsightIntelligenceCandidate.is_deleted == 0))).all()
        reviews = (await db.exec(select(InsightReviewRecord).where(InsightReviewRecord.is_deleted == 0))).all()
        crawl_results = (await db.exec(select(InsightCrawlResult).where(InsightCrawlResult.is_deleted == 0))).all()
        source_names = await self._source_names(db)
        return InsightQualityOverview(
            collection_metrics=self._collection_metrics(tasks, crawl_results, candidates),
            review_metrics=self._review_metrics(candidates, reviews),
            ai_metrics=self._ai_metrics(crawl_results, candidates),
            failure_reasons=self._failure_reasons(tasks, crawl_results),
            source_metrics=self._source_metrics(tasks, source_names),
            generated_at=datetime.now().isoformat(),
        )

    async def _source_names(self, db: AsyncSession) -> dict[int, str]:
        rows = (await db.exec(select(InsightDataSource.id, InsightDataSource.source_name).where(InsightDataSource.is_deleted == 0))).all()
        return {int(source_id): str(name) for source_id, name in rows if source_id is not None}

    def _collection_metrics(
        self,
        tasks: list[InsightTask],
        crawl_results: list[InsightCrawlResult],
        candidates: list[InsightIntelligenceCandidate],
    ) -> list[InsightQualityMetric]:
        total_tasks = len(tasks)
        success_tasks = sum(1 for task in tasks if task.status == InsightTaskStatus.SUCCESS)
        failed_tasks = sum(1 for task in tasks if task.status == InsightTaskStatus.FAILED)
        durations = [
            (task.finished_at - task.started_at).total_seconds()
            for task in tasks
            if task.started_at and task.finished_at and task.finished_at >= task.started_at
        ]
        candidate_rate = self._percent(len(candidates), len(crawl_results))
        return [
            InsightQualityMetric(key="task_total", label="采集任务数", value=total_tasks, unit="个"),
            InsightQualityMetric(key="task_success_rate", label="任务成功率", value=self._percent(success_tasks, total_tasks), unit="%"),
            InsightQualityMetric(key="task_failed", label="失败任务数", value=failed_tasks, unit="个"),
            InsightQualityMetric(key="avg_duration", label="平均执行耗时", value=round(sum(durations) / len(durations), 1) if durations else 0, unit="秒"),
            InsightQualityMetric(key="candidate_rate", label="候选生成率", value=candidate_rate, unit="%"),
        ]

    def _review_metrics(
        self,
        candidates: list[InsightIntelligenceCandidate],
        reviews: list[InsightReviewRecord],
    ) -> list[InsightQualityMetric]:
        promoted = sum(1 for candidate in candidates if str(candidate.review_status).lower().endswith("promoted"))
        rejected = sum(1 for candidate in candidates if str(candidate.review_status).lower().endswith("rejected"))
        ignored = sum(1 for candidate in candidates if str(candidate.review_status).lower().endswith("ignored"))
        reviewed = promoted + rejected + ignored
        manual_updates = sum(1 for review in reviews if review.to_status in {"manual_updated", "manual_created"})
        return [
            InsightQualityMetric(key="candidate_total", label="候选总数", value=len(candidates), unit="条"),
            InsightQualityMetric(key="reviewed_total", label="已审核候选", value=reviewed, unit="条"),
            InsightQualityMetric(key="promote_rate", label="审核通过率", value=self._percent(promoted, reviewed), unit="%"),
            InsightQualityMetric(key="reject_rate", label="驳回率", value=self._percent(rejected, reviewed), unit="%"),
            InsightQualityMetric(key="manual_updates", label="人工修订记录", value=manual_updates, unit="次"),
        ]

    def _ai_metrics(
        self,
        crawl_results: list[InsightCrawlResult],
        candidates: list[InsightIntelligenceCandidate],
    ) -> list[InsightQualityMetric]:
        quality_reports = [report for report in (self._quality_report(result.crawl_metadata) for result in crawl_results) if report]
        scores = [self._float_value(report.get("score")) for report in quality_reports if self._float_value(report.get("score")) is not None]
        auto_ignore_count = sum(1 for report in quality_reports if report.get("auto_ignore"))
        rule_quality_tags = sum(1 for candidate in candidates if self._has_quality_rule_tag(candidate.suggested_tags))
        return [
            InsightQualityMetric(key="quality_report_count", label="质量报告数", value=len(quality_reports), unit="份"),
            InsightQualityMetric(key="avg_quality_score", label="平均质量分", value=round(sum(scores) / len(scores) * 100, 1) if scores else 0, unit="%"),
            InsightQualityMetric(key="auto_ignore_count", label="建议忽略数", value=auto_ignore_count, unit="条"),
            InsightQualityMetric(key="quality_rule_tags", label="质量规则标签数", value=rule_quality_tags, unit="条"),
        ]

    def _failure_reasons(
        self,
        tasks: list[InsightTask],
        crawl_results: list[InsightCrawlResult],
    ) -> list[InsightQualityReason]:
        counter: Counter[tuple[str, str, str | None]] = Counter()
        raw_examples: dict[tuple[str, str, str | None], str] = {}
        for task in tasks:
            if task.error_message:
                classified = self._classify_reason(task.error_message)
                key = (classified["category"], classified["reason"], classified["suggestion"])
                counter[key] += 1
                raw_examples.setdefault(key, self._compact_reason(task.error_message, limit=180))
        for result in crawl_results:
            if result.error_message:
                classified = self._classify_reason(result.error_message)
                key = (classified["category"], classified["reason"], classified["suggestion"])
                counter[key] += 1
                raw_examples.setdefault(key, self._compact_reason(result.error_message, limit=180))
        return [
            InsightQualityReason(
                category=category,
                reason=reason,
                suggestion=suggestion,
                raw_reason=raw_examples.get((category, reason, suggestion)),
                count=count,
            )
            for (category, reason, suggestion), count in counter.most_common(8)
        ]

    def _source_metrics(self, tasks: list[InsightTask], source_names: dict[int, str]) -> list[InsightQualitySourceMetric]:
        grouped: dict[int | None, dict[str, int]] = defaultdict(lambda: {"total": 0, "success": 0, "failed": 0})
        for task in tasks:
            bucket = grouped[task.data_source_id]
            bucket["total"] += 1
            if task.status == InsightTaskStatus.SUCCESS:
                bucket["success"] += 1
            if task.status == InsightTaskStatus.FAILED:
                bucket["failed"] += 1
        rows = [
            InsightQualitySourceMetric(
                data_source_id=source_id,
                data_source_name=source_names.get(source_id or 0, "未关联数据源"),
                total_tasks=stats["total"],
                success_tasks=stats["success"],
                failed_tasks=stats["failed"],
                success_rate=self._percent(stats["success"], stats["total"]),
            )
            for source_id, stats in grouped.items()
        ]
        return sorted(rows, key=lambda item: (item.failed_tasks, item.total_tasks), reverse=True)[:10]

    def _quality_report(self, metadata: dict[str, Any] | None) -> dict[str, Any] | None:
        if not isinstance(metadata, dict):
            return None
        report = metadata.get("quality_report")
        return report if isinstance(report, dict) else None

    def _has_quality_rule_tag(self, tags: Any) -> bool:
        if not isinstance(tags, list):
            return False
        return any(isinstance(item, dict) and item.get("source") == "quality_rule" for item in tags)

    def _classify_reason(self, value: str) -> dict[str, str | None]:
        reason = self._compact_reason(value, limit=240)
        lowered = reason.lower()
        if any(token in lowered for token in ("timeout", "timed out", "read timed out", "connect timeout")):
            return {
                "category": "timeout",
                "reason": "外部服务响应超时",
                "suggestion": "稍后重试，或降低单次采集数量并检查目标站点响应速度。",
            }
        if any(token in lowered for token in ("connection", "connecterror", "dns", "name resolution", "network")):
            return {
                "category": "network",
                "reason": "网络连接失败",
                "suggestion": "检查采集服务网络、代理、DNS 或目标站点连通性。",
            }
        if any(token in lowered for token in ("403", "401", "429", "502", "503", "504", "http", "status code")):
            return {
                "category": "external_service",
                "reason": "目标网站或外部接口返回异常",
                "suggestion": "查看任务日志中的 URL 和状态码，必要时调整频率、鉴权或数据源配置。",
            }
        if any(token in lowered for token in ("nonetype", "keyerror", "indexerror", "attributeerror", "not subscriptable", "parse", "解析")):
            return {
                "category": "parse",
                "reason": "内容解析异常",
                "suggestion": "目标页面结构可能变化，建议查看任务日志并重新测试数据源。",
            }
        if any(token in lowered for token in ("no content", "empty", "素材不足", "insufficient", "未找到", "没有可用")):
            return {
                "category": "empty_content",
                "reason": "素材不足或内容为空",
                "suggestion": "放宽关键词、扩大时间范围，或补充更多可用数据源。",
            }
        if any(token in lowered for token in ("llm", "openai", "model", "模型", "大模型")):
            return {
                "category": "ai",
                "reason": "AI 处理失败",
                "suggestion": "检查模型配置、额度、网络和提示词长度，失败记录可人工重试。",
            }
        return {
            "category": "unknown",
            "reason": "采集任务执行失败",
            "suggestion": "打开任务日志查看原始错误，确认是否需要调整数据源或重试。",
        }

    def _compact_reason(self, value: str, limit: int = 80) -> str:
        return value.strip().splitlines()[0][:limit] or "未知失败原因"

    def _float_value(self, value: Any) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _percent(self, numerator: int | float, denominator: int | float) -> float:
        if not denominator:
            return 0
        return round(float(numerator) / float(denominator) * 100, 1)


insight_quality_service = InsightQualityService()
