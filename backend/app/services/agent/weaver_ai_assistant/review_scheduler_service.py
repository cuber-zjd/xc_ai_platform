import asyncio
from collections import defaultdict
from datetime import datetime, timedelta
from time import monotonic
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from app.core.config import settings
from app.core.logger import logger
from app.db.session import async_session
from app.models.agent.weaver_ai_assistant import (
    WeaverAiReviewNodeConfig,
    WeaverAiReviewScanTask,
)
from app.services.agent.weaver_ai_assistant.assistant_service import weaver_ai_assistant_service
from app.services.agent.weaver_ai_assistant.review_service import weaver_ai_review_service


class WeaverAiReviewSchedulerService:
    """按节点配置扫描泛微当前待办并生成自动预审结果。"""

    def __init__(self) -> None:
        self._task: asyncio.Task[None] | None = None
        self._run_lock = asyncio.Lock()
        self._last_result: dict[str, Any] | None = None

    def status(self) -> dict[str, Any]:
        return {
            "enabled": settings.WEAVER_AI_REVIEW_SCHEDULER_ENABLED,
            "running": bool(self._task and not self._task.done()),
            "intervalSeconds": self._interval_seconds(),
            "batchLimit": self._batch_limit(),
            "concurrency": self._concurrency(),
            "lastResult": self._last_result,
        }

    async def start_from_settings(self) -> None:
        if not (
            settings.WEAVER_AI_REVIEW_SCHEDULER_ENABLED
            and settings.WEAVER_AI_REVIEW_SCHEDULER_AUTO_START
        ):
            logger.info("泛微 AI 自动预审扫描器未启用")
            return
        if self._task and not self._task.done():
            return
        self._task = asyncio.create_task(self._loop(), name="weaver-ai-review-scheduler")
        logger.info(
            f"泛微 AI 自动预审扫描器已启动，扫描间隔 {self._interval_seconds()} 秒"
        )

    async def stop(self) -> None:
        if not self._task:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    async def run_once(self) -> dict[str, Any]:
        if self._run_lock.locked():
            return self._last_result or {"status": "busy", "message": "上一轮自动预审仍在执行"}
        async with self._run_lock:
            started_at = datetime.now()
            result: dict[str, Any] = {
                "status": "completed",
                "startedAt": started_at.isoformat(),
                "configuredNodes": 0,
                "discovered": 0,
                "claimed": 0,
                "completed": 0,
                "failed": 0,
                "skipped": 0,
                "errors": [],
            }
            try:
                configs = await self._load_enabled_node_configs()
                result["configuredNodes"] = len(configs)
                if not configs:
                    return self._finish_result(result, started_at)
                candidates = await asyncio.to_thread(self._scan_candidates, configs)
                result["discovered"] = len(candidates)
                semaphore = asyncio.Semaphore(self._concurrency())

                async def process(candidate: dict[str, Any]) -> dict[str, Any]:
                    async with semaphore:
                        return await self._process_candidate(candidate)

                outcomes = await asyncio.gather(
                    *(process(candidate) for candidate in candidates[: self._batch_limit()])
                )
                for outcome in outcomes:
                    outcome_status = outcome.pop("status")
                    result[outcome_status] += 1
                    if outcome_status == "failed":
                        result["errors"].append(outcome)
                result["claimed"] = result["completed"] + result["failed"]
                return self._finish_result(result, started_at)
            except Exception as exc:
                result["status"] = "failed"
                result["errors"].append({"message": str(exc)[:500]})
                logger.exception(f"泛微 AI 自动预审扫描轮次失败: {exc}")
                return self._finish_result(result, started_at)

    async def _loop(self) -> None:
        await asyncio.sleep(max(0, settings.WEAVER_AI_REVIEW_SCHEDULER_STARTUP_DELAY_SECONDS))
        while True:
            started = monotonic()
            await self.run_once()
            await asyncio.sleep(max(1.0, self._interval_seconds() - (monotonic() - started)))

    async def _load_enabled_node_configs(self) -> list[WeaverAiReviewNodeConfig]:
        async with async_session() as db:
            statement = select(WeaverAiReviewNodeConfig).where(
                WeaverAiReviewNodeConfig.enabled == True,  # noqa: E712
                WeaverAiReviewNodeConfig.automatic_review_enabled == True,  # noqa: E712
                WeaverAiReviewNodeConfig.status == "active",
                WeaverAiReviewNodeConfig.is_deleted == 0,
            )
            return list((await db.exec(statement)).all())

    def _scan_candidates(
        self,
        configs: list[WeaverAiReviewNodeConfig],
    ) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        grouped: dict[str, list[WeaverAiReviewNodeConfig]] = defaultdict(list)
        for config in configs:
            grouped[config.env].append(config)
        for env, env_configs in grouped.items():
            db_config = weaver_ai_assistant_service._get_weaver_db_config(env)
            with weaver_ai_assistant_service._connect_weaver_mysql(db_config) as conn:
                with conn.cursor() as cursor:
                    for config in env_configs:
                        remaining = self._batch_limit() - len(candidates)
                        if remaining <= 0:
                            return candidates
                        rows = weaver_ai_assistant_service._fetch_all(
                            cursor,
                            """
                            SELECT co.id AS operator_id, rb.requestid, rb.requestname,
                                   rb.workflowid, rb.currentnodeid, nb.nodename,
                                   co.userid AS reviewer_user_id, hr.lastname AS reviewer_name,
                                   CONCAT_WS(' ', co.receivedate, co.receivetime) AS received_at
                            FROM workflow_requestbase rb
                            JOIN workflow_currentoperator co
                              ON co.requestid = rb.requestid
                             AND co.workflowid = rb.workflowid
                             AND co.nodeid = rb.currentnodeid
                            LEFT JOIN workflow_nodebase nb ON nb.id = rb.currentnodeid
                            LEFT JOIN hrmresource hr ON hr.id = co.userid
                            WHERE rb.workflowid = %s
                              AND rb.currentnodeid = %s
                              AND rb.currentnodetype <> '3'
                              AND co.isremark = 0
                              AND co.iscomplete = 0
                              AND co.userid > 0
                            ORDER BY co.id ASC
                            LIMIT %s
                            """,
                            (config.workflow_id, config.node_id, remaining),
                        )
                        for row in rows:
                            candidates.append(
                                {
                                    "env": config.env,
                                    "workflow_id": str(config.workflow_id),
                                    "workflow_name": config.workflow_name or "",
                                    "request_id": str(row.get("requestid") or ""),
                                    "request_name": str(row.get("requestname") or ""),
                                    "node_id": str(row.get("currentnodeid") or config.node_id),
                                    "node_name": str(row.get("nodename") or config.node_name or ""),
                                    "reviewer_user_id": str(row.get("reviewer_user_id") or ""),
                                    "reviewer_name": str(row.get("reviewer_name") or ""),
                                    "operator_id": str(row.get("operator_id") or ""),
                                    "received_at": str(row.get("received_at") or ""),
                                }
                            )
        return candidates

    async def _claim(self, candidate: dict[str, Any]) -> int | None:
        async with async_session() as db:
            statement = select(WeaverAiReviewScanTask).where(
                WeaverAiReviewScanTask.env == candidate["env"],
                WeaverAiReviewScanTask.workflow_id == candidate["workflow_id"],
                WeaverAiReviewScanTask.request_id == candidate["request_id"],
                WeaverAiReviewScanTask.node_id == candidate["node_id"],
                WeaverAiReviewScanTask.reviewer_user_id == candidate["reviewer_user_id"],
                WeaverAiReviewScanTask.operator_id == candidate["operator_id"],
                WeaverAiReviewScanTask.is_deleted == 0,
            )
            row = (await db.exec(statement)).first()
            if row:
                stale = bool(
                    row.status == "running"
                    and row.update_time
                    and row.update_time < datetime.now() - timedelta(minutes=15)
                )
                retryable = row.status == "failed" and row.attempts < self._max_attempts()
                if not stale and not retryable:
                    return None
                row.status = "running"
                row.attempts += 1
                row.last_error = None
                row.update_time = datetime.now()
            else:
                row = WeaverAiReviewScanTask(
                    **candidate,
                    status="running",
                    attempts=1,
                )
                db.add(row)
            try:
                await db.commit()
                await db.refresh(row)
            except IntegrityError:
                await db.rollback()
                return None
            return row.id

    async def _review_candidate(self, candidate: dict[str, Any]) -> int:
        payload = await weaver_ai_review_service.build_scheduled_review_request(
            env=candidate["env"],
            workflow_id=candidate["workflow_id"],
            request_id=candidate["request_id"],
            node_id=candidate["node_id"],
            node_name=candidate["node_name"],
            reviewer_user_id=candidate["reviewer_user_id"],
            reviewer_name=candidate["reviewer_name"],
        )
        async with async_session() as db:
            response = await weaver_ai_review_service.pre_review(db, payload)
            return response.record.id

    async def _process_candidate(self, candidate: dict[str, Any]) -> dict[str, Any]:
        task_id = await self._claim(candidate)
        if task_id is None:
            return {"status": "skipped"}
        try:
            review_record_id = await self._review_candidate(candidate)
        except Exception as exc:
            await self._finish_task(task_id, "failed", error=str(exc))
            logger.exception(
                "泛微自动预审失败: "
                f"env={candidate['env']}, request_id={candidate['request_id']}, "
                f"node_id={candidate['node_id']}, reviewer={candidate['reviewer_user_id']}"
            )
            return {
                "status": "failed",
                "requestId": candidate["request_id"],
                "nodeId": candidate["node_id"],
                "message": str(exc)[:300],
            }
        await self._finish_task(task_id, "completed", review_record_id=review_record_id)
        return {"status": "completed"}

    async def _finish_task(
        self,
        task_id: int,
        status: str,
        *,
        review_record_id: int | None = None,
        error: str | None = None,
    ) -> None:
        async with async_session() as db:
            row = await db.get(WeaverAiReviewScanTask, task_id)
            if not row:
                return
            row.status = status
            row.review_record_id = review_record_id
            row.last_error = error[:2000] if error else None
            row.update_time = datetime.now()
            await db.commit()

    def _finish_result(self, result: dict[str, Any], started_at: datetime) -> dict[str, Any]:
        result["finishedAt"] = datetime.now().isoformat()
        result["durationSeconds"] = round((datetime.now() - started_at).total_seconds(), 3)
        self._last_result = result
        logger.info(
            "泛微 AI 自动预审扫描完成: "
            f"configured={result['configuredNodes']}, discovered={result['discovered']}, "
            f"completed={result['completed']}, failed={result['failed']}, skipped={result['skipped']}"
        )
        return result

    def _interval_seconds(self) -> int:
        return max(30, int(settings.WEAVER_AI_REVIEW_SCHEDULER_INTERVAL_SECONDS))

    def _batch_limit(self) -> int:
        return max(1, min(100, int(settings.WEAVER_AI_REVIEW_SCHEDULER_BATCH_LIMIT)))

    def _max_attempts(self) -> int:
        return max(1, min(10, int(settings.WEAVER_AI_REVIEW_SCHEDULER_MAX_ATTEMPTS)))

    def _concurrency(self) -> int:
        return max(1, min(5, int(settings.WEAVER_AI_REVIEW_SCHEDULER_CONCURRENCY)))


weaver_ai_review_scheduler_service = WeaverAiReviewSchedulerService()
