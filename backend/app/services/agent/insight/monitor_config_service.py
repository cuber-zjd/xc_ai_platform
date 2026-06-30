from datetime import datetime
from uuid import uuid4

from sqlalchemy import func, or_
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.agent.insight import InsightChannel, InsightMonitorConfig
from app.schemas.agent.insight.monitor_config import (
    InsightMonitorConfigCreate,
    InsightMonitorConfigRead,
    InsightMonitorConfigUpdate,
)
from app.schemas.page import Page


class InsightMonitorConfigService:
    allowed_monitor_types = {"enterprise", "industry", "policy", "technology", "product", "public_opinion", "custom"}
    allowed_object_types = {"company", "subject", "topic", "custom"}
    allowed_statuses = {"active", "disabled"}
    allowed_strengths = {"light", "standard", "deep", "structured"}
    allowed_frequencies = {"manual", "daily", "weekly", "monthly", "cron"}
    allowed_visibility_scopes = {"private", "assigned", "dept", "role", "public"}

    async def list_configs(
        self,
        db: AsyncSession,
        *,
        page: int,
        size: int,
        keyword: str | None,
        monitor_type: str | None,
        status: str | None,
        user_id: int | None = None,
        is_admin: bool = False,
    ) -> Page[InsightMonitorConfigRead]:
        page = max(page, 1)
        size = min(max(size, 1), 100)
        filters = [InsightMonitorConfig.is_deleted == 0]
        if not is_admin:
            filters.append(
                or_(
                    InsightMonitorConfig.owner_user_id == user_id,
                    InsightMonitorConfig.visibility_scope == "public",
                )
            )
        if keyword:
            like_keyword = f"%{keyword.strip()}%"
            filters.append(
                or_(
                    InsightMonitorConfig.config_name.ilike(like_keyword),
                    InsightMonitorConfig.config_code.ilike(like_keyword),
                    InsightMonitorConfig.object_name.ilike(like_keyword),
                )
            )
        if monitor_type:
            filters.append(InsightMonitorConfig.monitor_type == monitor_type)
        if status:
            filters.append(InsightMonitorConfig.status == status)
        total = (await db.exec(select(func.count()).select_from(InsightMonitorConfig).where(*filters))).one()
        rows = list(
            (
                await db.exec(
                    select(InsightMonitorConfig)
                    .where(*filters)
                    .order_by(InsightMonitorConfig.update_time.desc(), InsightMonitorConfig.id.desc())
                    .offset((page - 1) * size)
                    .limit(size)
                )
            ).all()
        )
        return Page.create(
            items=[await self._to_read_with_stats(db, row) for row in rows],
            total=total,
            page=page,
            size=size,
        )

    async def create_config(
        self,
        db: AsyncSession,
        payload: InsightMonitorConfigCreate,
        user_id: int | None,
    ) -> InsightMonitorConfigRead:
        self._validate(payload.model_dump())
        config_code = payload.config_code or f"mon_{uuid4().hex[:16]}"
        existing = (await db.exec(select(InsightMonitorConfig).where(InsightMonitorConfig.config_code == config_code))).first()
        if existing:
            raise ValueError("监测配置编码已存在")
        row = InsightMonitorConfig(
            config_code=config_code,
            config_name=payload.config_name,
            monitor_type=payload.monitor_type,
            object_type=payload.object_type,
            object_id=payload.object_id,
            object_name=payload.object_name,
            relation_type=payload.relation_type,
            enabled_modules=self._normalize_list(payload.enabled_modules),
            keywords=self._normalize_list(payload.keywords),
            excluded_keywords=self._normalize_list(payload.excluded_keywords),
            source_channel_ids=self._normalize_int_list(payload.source_channel_ids),
            monitor_strength=payload.monitor_strength,
            fetch_frequency=payload.fetch_frequency,
            ai_review_prompt=payload.ai_review_prompt,
            ai_review_policy=payload.ai_review_policy,
            owner_user_id=user_id,
            visibility_scope=payload.visibility_scope,
            generation_mode=payload.generation_mode,
            config_json=payload.config_json,
            schedule_enabled=payload.fetch_frequency != "manual" and payload.status == "active",
            next_run_time=datetime.now() if payload.fetch_frequency != "manual" and payload.status == "active" else None,
            last_schedule_status="waiting" if payload.fetch_frequency != "manual" and payload.status == "active" else None,
            status=payload.status,
            create_by=str(user_id) if user_id else None,
            update_by=str(user_id) if user_id else None,
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return await self._to_read_with_stats(db, row)

    async def update_config(
        self,
        db: AsyncSession,
        config_id: int,
        payload: InsightMonitorConfigUpdate,
        user_id: int | None,
        is_admin: bool = False,
    ) -> InsightMonitorConfigRead:
        row = await self._get_config(db, config_id)
        self._ensure_can_modify(row, user_id=user_id, is_admin=is_admin)
        data = payload.model_dump(exclude_unset=True)
        merged = {
            "monitor_type": data.get("monitor_type", row.monitor_type),
            "object_type": data.get("object_type", row.object_type),
            "monitor_strength": data.get("monitor_strength", row.monitor_strength),
            "fetch_frequency": data.get("fetch_frequency", row.fetch_frequency),
            "visibility_scope": data.get("visibility_scope", row.visibility_scope),
            "status": data.get("status", row.status),
        }
        self._validate(merged)
        for list_field in ("enabled_modules", "keywords", "excluded_keywords"):
            if list_field in data and data[list_field] is not None:
                data[list_field] = self._normalize_list(data[list_field])
        if "source_channel_ids" in data and data["source_channel_ids"] is not None:
            data["source_channel_ids"] = self._normalize_int_list(data["source_channel_ids"])
        for field, value in data.items():
            setattr(row, field, value)
        if "fetch_frequency" in data or "status" in data:
            row.schedule_enabled = row.fetch_frequency != "manual" and row.status == "active"
            row.next_run_time = datetime.now() if row.schedule_enabled and not row.next_run_time else (row.next_run_time if row.schedule_enabled else None)
            row.last_schedule_status = row.last_schedule_status or ("waiting" if row.schedule_enabled else None)
        row.update_by = str(user_id) if user_id else None
        row.update_time = datetime.now()
        await db.commit()
        await db.refresh(row)
        return await self._to_read_with_stats(db, row)

    async def delete_config(self, db: AsyncSession, config_id: int, user_id: int | None, is_admin: bool = False) -> None:
        row = await self._get_config(db, config_id)
        self._ensure_can_modify(row, user_id=user_id, is_admin=is_admin)
        row.is_deleted = 1
        row.status = "disabled"
        row.schedule_enabled = False
        row.next_run_time = None
        row.update_by = str(user_id) if user_id else None
        row.update_time = datetime.now()
        await db.commit()

    async def _get_config(self, db: AsyncSession, config_id: int) -> InsightMonitorConfig:
        row = (
            await db.exec(
                select(InsightMonitorConfig).where(
                    InsightMonitorConfig.id == config_id,
                    InsightMonitorConfig.is_deleted == 0,
                )
            )
        ).first()
        if not row:
            raise ValueError("监测配置不存在")
        return row

    def _ensure_can_modify(self, row: InsightMonitorConfig, *, user_id: int | None, is_admin: bool) -> None:
        if is_admin or (user_id is not None and row.owner_user_id == user_id):
            return
        raise ValueError("只能维护自己创建的监测配置")

    async def _to_read_with_stats(self, db: AsyncSession, row: InsightMonitorConfig) -> InsightMonitorConfigRead:
        merged_channel_ids = await self._coverage_channel_ids(db, row)
        return InsightMonitorConfigRead(
            id=row.id,
            create_time=row.create_time,
            update_time=row.update_time,
            create_by=row.create_by,
            update_by=row.update_by,
            comment=row.comment,
            is_deleted=row.is_deleted,
            config_code=row.config_code,
            config_name=row.config_name,
            monitor_type=row.monitor_type,
            object_type=row.object_type,
            object_id=row.object_id,
            object_name=row.object_name,
            relation_type=row.relation_type,
            enabled_modules=row.enabled_modules or [],
            keywords=row.keywords or [],
            excluded_keywords=row.excluded_keywords or [],
            source_channel_ids=merged_channel_ids,
            monitor_strength=row.monitor_strength,
            fetch_frequency=row.fetch_frequency,
            ai_review_prompt=row.ai_review_prompt,
            ai_review_policy=row.ai_review_policy,
            owner_user_id=row.owner_user_id,
            owner_dept_id=row.owner_dept_id,
            visibility_scope=row.visibility_scope,
            generation_mode=row.generation_mode,
            config_json=row.config_json,
            last_fetch_time=row.last_fetch_time,
            last_success_time=row.last_success_time,
            next_run_time=row.next_run_time,
            schedule_enabled=row.schedule_enabled,
            last_schedule_status=row.last_schedule_status,
            last_schedule_message=row.last_schedule_message,
            consecutive_failure_count=row.consecutive_failure_count,
            last_failure_time=row.last_failure_time,
            auto_paused_reason=row.auto_paused_reason,
            status=row.status,
            execution_source_count=len(merged_channel_ids),
        )

    async def _coverage_channel_ids(self, db: AsyncSession, row: InsightMonitorConfig) -> list[int]:
        explicit_ids = [item for item in row.source_channel_ids or [] if isinstance(item, int) and item > 0]
        if explicit_ids:
            return list(dict.fromkeys(explicit_ids))
        modules = set(row.enabled_modules or [])
        if not modules:
            return []
        channels = list(
            (
                await db.exec(
                    select(InsightChannel).where(
                        InsightChannel.is_deleted == 0,
                        InsightChannel.status == "active",
                    )
                )
            ).all()
        )
        return [
            channel.id
            for channel in channels
            if channel.id is not None and self._channel_matches_modules(channel, modules)
        ]

    def _channel_matches_modules(self, channel: InsightChannel, modules: set[str]) -> bool:
        scenarios = {str(item).strip() for item in channel.applicable_scenarios or [] if str(item).strip()}
        return bool(scenarios.intersection(modules))

    def _validate(self, data: dict) -> None:
        monitor_type = str(data.get("monitor_type") or "topic")
        object_type = str(data.get("object_type") or "topic")
        strength = str(data.get("monitor_strength") or "standard")
        frequency = str(data.get("fetch_frequency") or "daily")
        visibility = str(data.get("visibility_scope") or "assigned")
        status = str(data.get("status") or "active")
        if monitor_type not in self.allowed_monitor_types:
            raise ValueError(f"监测类型不支持：{monitor_type}")
        if object_type not in self.allowed_object_types:
            raise ValueError(f"监测对象类型不支持：{object_type}")
        if strength not in self.allowed_strengths:
            raise ValueError(f"监测强度不支持：{strength}")
        if frequency not in self.allowed_frequencies:
            raise ValueError(f"监测频率不支持：{frequency}")
        if visibility not in self.allowed_visibility_scopes:
            raise ValueError(f"可见范围不支持：{visibility}")
        if status not in self.allowed_statuses:
            raise ValueError(f"监测配置状态不支持：{status}")

    def _normalize_list(self, values: list[str] | None) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for value in values or []:
            text = str(value).strip()
            if text and text not in seen:
                result.append(text)
                seen.add(text)
        return result

    def _normalize_int_list(self, values: list[int] | None) -> list[int]:
        result: list[int] = []
        seen: set[int] = set()
        for value in values or []:
            try:
                parsed = int(value)
            except (TypeError, ValueError):
                continue
            if parsed > 0 and parsed not in seen:
                result.append(parsed)
                seen.add(parsed)
        return result


insight_monitor_config_service = InsightMonitorConfigService()
