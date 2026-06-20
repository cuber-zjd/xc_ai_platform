from calendar import monthrange
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import and_, exists, or_
from sqlmodel import func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.agent.insight import InsightCompany, InsightDataSource, InsightReportSubscription
from app.models.system.sys_user import SysUser
from app.schemas.agent.insight.notification import InsightNotificationCreate, InsightNotificationRecipient
from app.schemas.agent.insight.report import (
    InsightReportGenerateRequest,
    InsightReportSubscriptionCreate,
    InsightReportSubscriptionDueRunResponse,
    InsightReportSubscriptionRead,
    InsightReportSubscriptionRunResponse,
    InsightReportSubscriptionUpdate,
)
from app.schemas.page import Page
from app.services.agent.insight.notification_service import insight_notification_service
from app.services.agent.insight.permission_service import insight_permission_service
from app.services.agent.insight.report_service import insight_report_service


class InsightReportSubscriptionService:
    allowed_scope_types = {"material_pool", "sys_company", "company", "data_source"}
    allowed_frequencies = {"daily", "weekly", "monthly"}
    allowed_statuses = {"active", "paused"}
    allowed_visibility_scopes = {"private", "assigned", "dept", "role", "public"}

    async def list_subscriptions(
        self,
        db: AsyncSession,
        *,
        page: int,
        size: int,
        status: str | None,
        user_id: int,
        is_admin: bool,
    ) -> Page[InsightReportSubscriptionRead]:
        page = max(page, 1)
        size = min(max(size, 1), 100)
        filters = [InsightReportSubscription.is_deleted == 0]
        if status:
            filters.append(InsightReportSubscription.status == status)
        if not is_admin:
            filters.append(await self._subscription_company_scope_filter(db, user_id=user_id, is_admin=is_admin))
            filters.append(
                await insight_permission_service.visibility_filter_for_user(
                    db,
                    InsightReportSubscription,
                    target_type="report_subscription",
                    user_id=user_id,
                    is_admin=is_admin,
                )
            )
        total = (await db.exec(select(func.count()).select_from(InsightReportSubscription).where(*filters))).one()
        rows = list(
            (
                await db.exec(
                    select(InsightReportSubscription)
                    .where(*filters)
                    .order_by(InsightReportSubscription.next_run_time.asc().nullslast(), InsightReportSubscription.id.desc())
                    .offset((page - 1) * size)
                    .limit(size)
                )
            ).all()
        )
        return Page.create(items=[self._to_read(row) for row in rows], total=total, page=page, size=size)

    async def create_subscription(
        self,
        db: AsyncSession,
        payload: InsightReportSubscriptionCreate,
        *,
        user_id: int,
        is_admin: bool,
    ) -> InsightReportSubscriptionRead:
        self._validate_payload(payload)
        await self._assert_template_visible(db, payload.template_code, user_id=user_id, is_admin=is_admin)
        company_ids, data_source_ids = await self._validate_scope(
            db,
            scope_type=payload.scope_type,
            sys_company_id=payload.sys_company_id,
            company_ids=payload.company_ids,
            data_source_ids=payload.data_source_ids,
            user_id=user_id,
            is_admin=is_admin,
        )
        owner_dept_id = await self._resolve_owner_dept_id(db, user_id)
        row = InsightReportSubscription(
            subscription_uid=f"report_sub_{uuid4().hex}",
            subscription_name=payload.subscription_name.strip(),
            report_type=payload.report_type,
            template_code=payload.template_code,
            scope_type=payload.scope_type,
            sys_company_id=payload.sys_company_id,
            company_ids_json=company_ids,
            data_source_ids_json=data_source_ids,
            folder_name=payload.folder_name,
            max_materials=payload.max_materials,
            generation_prompt=payload.generation_prompt,
            schedule_frequency=payload.schedule_frequency,
            weekday=payload.weekday,
            day_of_month=payload.day_of_month,
            time_of_day=payload.time_of_day,
            timezone=payload.timezone,
            next_run_time=self._next_run_time(payload.schedule_frequency, payload.time_of_day, payload.weekday, payload.day_of_month),
            wecom_recipient_scope=payload.wecom_recipient_scope,
            wecom_recipients_json=[item.model_dump(mode="json") for item in payload.wecom_recipients],
            owner_user_id=user_id,
            owner_dept_id=owner_dept_id,
            visibility_scope=payload.visibility_scope,
            status=payload.status,
            create_by=str(user_id),
            update_by=str(user_id),
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return self._to_read(row)

    async def update_subscription(
        self,
        db: AsyncSession,
        subscription_id: int,
        payload: InsightReportSubscriptionUpdate,
        *,
        user_id: int,
        is_admin: bool,
    ) -> InsightReportSubscriptionRead:
        row = await self._get_subscription(db, subscription_id, user_id=user_id, is_admin=is_admin, permission="edit")
        data = payload.model_dump(exclude_unset=True)
        next_scope_type = data.get("scope_type", row.scope_type)
        next_sys_company_id = data.get("sys_company_id", row.sys_company_id)
        next_company_ids = data.get("company_ids", row.company_ids_json)
        next_data_source_ids = data.get("data_source_ids", row.data_source_ids_json)
        if "template_code" in data:
            await self._assert_template_visible(db, data.get("template_code"), user_id=user_id, is_admin=is_admin)
        company_ids, data_source_ids = await self._validate_scope(
            db,
            scope_type=next_scope_type,
            sys_company_id=next_sys_company_id,
            company_ids=next_company_ids or [],
            data_source_ids=next_data_source_ids or [],
            user_id=user_id,
            is_admin=is_admin,
        )
        for key, value in data.items():
            if key == "company_ids":
                row.company_ids_json = company_ids
            elif key == "data_source_ids":
                row.data_source_ids_json = data_source_ids
            elif key == "wecom_recipients" and value is not None:
                row.wecom_recipients_json = [self._recipient_to_dict(item) for item in value]
            elif key in {"scope_type", "sys_company_id"}:
                setattr(row, key, value)
                row.company_ids_json = company_ids
                row.data_source_ids_json = data_source_ids
            elif key in {"subscription_name", "report_type", "template_code", "folder_name", "max_materials", "generation_prompt", "schedule_frequency", "weekday", "day_of_month", "time_of_day", "timezone", "wecom_recipient_scope", "visibility_scope", "status"}:
                setattr(row, key, value)
        self._validate_row(row)
        row.next_run_time = self._next_run_time(row.schedule_frequency, row.time_of_day, row.weekday, row.day_of_month)
        row.update_time = datetime.now()
        row.update_by = str(user_id)
        await db.commit()
        await db.refresh(row)
        return self._to_read(row)

    async def delete_subscription(
        self,
        db: AsyncSession,
        subscription_id: int,
        *,
        user_id: int,
        is_admin: bool,
    ) -> None:
        row = await self._get_subscription(db, subscription_id, user_id=user_id, is_admin=is_admin, permission="edit")
        row.is_deleted = 1
        row.status = "paused"
        row.update_time = datetime.now()
        row.update_by = str(user_id)
        await db.commit()

    async def run_subscription(
        self,
        db: AsyncSession,
        subscription_id: int,
        *,
        user_id: int,
        is_admin: bool,
        triggered_by: str = "manual",
    ) -> InsightReportSubscriptionRunResponse:
        row = await self._get_subscription(db, subscription_id, user_id=user_id, is_admin=is_admin, permission="edit")
        return await self._execute_subscription(db, row, triggered_by=triggered_by)

    async def run_due_subscriptions(
        self,
        db: AsyncSession,
        *,
        limit: int = 10,
        triggered_by: str = "scheduler",
    ) -> InsightReportSubscriptionDueRunResponse:
        now = datetime.now()
        limit = min(max(limit, 1), 50)
        checked_count = (
            await db.exec(
                select(func.count()).select_from(InsightReportSubscription).where(
                    InsightReportSubscription.is_deleted == 0,
                    InsightReportSubscription.status == "active",
                )
            )
        ).one()
        rows = list(
            (
                await db.exec(
                    select(InsightReportSubscription)
                    .where(
                        InsightReportSubscription.is_deleted == 0,
                        InsightReportSubscription.status == "active",
                        InsightReportSubscription.next_run_time.is_not(None),
                        InsightReportSubscription.next_run_time <= now,
                    )
                    .order_by(InsightReportSubscription.next_run_time.asc(), InsightReportSubscription.id.asc())
                    .limit(limit)
                )
            ).all()
        )
        results: list[InsightReportSubscriptionRunResponse] = []
        failed_count = 0
        for row in rows:
            try:
                results.append(await self._execute_subscription(db, row, triggered_by=triggered_by))
            except Exception as exc:
                failed_count += 1
                row.last_run_time = datetime.now()
                row.last_status = "failed"
                row.last_error = str(exc)[:1000]
                row.next_run_time = self._next_run_time(row.schedule_frequency, row.time_of_day, row.weekday, row.day_of_month)
                row.update_time = datetime.now()
                await db.commit()
                results.append(InsightReportSubscriptionRunResponse(subscription=self._to_read(row), skipped=False, message=str(exc)))
        return InsightReportSubscriptionDueRunResponse(
            checked_count=checked_count,
            due_count=len(rows),
            executed_count=max(len(rows) - failed_count, 0),
            failed_count=failed_count,
            results=results,
        )

    async def _execute_subscription(
        self,
        db: AsyncSession,
        row: InsightReportSubscription,
        *,
        triggered_by: str,
    ) -> InsightReportSubscriptionRunResponse:
        if row.status != "active":
            return InsightReportSubscriptionRunResponse(subscription=self._to_read(row), skipped=True, message="计划已暂停")
        user_id = row.owner_user_id
        if not user_id:
            raise ValueError("报告计划缺少创建人，无法按权限执行")
        company_ids, data_source_ids = await self._resolve_runtime_scope(db, row, user_id=user_id)
        report = await insight_report_service.generate_report(
            db,
            InsightReportGenerateRequest(
                title=f"{row.subscription_name} {datetime.now().strftime('%Y-%m-%d')}",
                report_type=row.report_type,
                template_code=row.template_code,
                company_ids=company_ids,
                data_source_ids=data_source_ids,
                folder_name=row.folder_name,
                max_materials=row.max_materials,
                generation_prompt=row.generation_prompt,
            ),
            user_id=user_id,
            is_admin=False,
        )
        notification = await insight_notification_service.create_notification(
            db,
            InsightNotificationCreate(
                target_type="report",
                target_id=report.report.id,
                title=f"定时报告：{report.report.title}",
                content=report.report.summary or "定时市场洞察报告已生成，请进入平台查看正文和引用来源。",
                recipient_scope=row.wecom_recipient_scope,
                recipients=[InsightNotificationRecipient.model_validate(item) for item in row.wecom_recipients_json],
                send_now=True,
            ),
            user_id=user_id,
            is_admin=False,
        )
        row.last_run_time = datetime.now()
        row.last_report_id = report.report.id
        row.last_notification_id = notification.id
        row.last_status = "success"
        row.last_error = None
        row.next_run_time = self._next_run_time(row.schedule_frequency, row.time_of_day, row.weekday, row.day_of_month)
        row.update_time = datetime.now()
        row.update_by = str(user_id)
        await db.commit()
        await db.refresh(row)
        return InsightReportSubscriptionRunResponse(
            subscription=self._to_read(row),
            report=report.report,
            notification=notification,
            message=f"{triggered_by} 已生成报告并创建企业微信推送记录",
        )

    async def _resolve_runtime_scope(self, db: AsyncSession, row: InsightReportSubscription, *, user_id: int) -> tuple[list[int], list[int]]:
        return await self._validate_scope(
            db,
            scope_type=row.scope_type,
            sys_company_id=row.sys_company_id,
            company_ids=row.company_ids_json,
            data_source_ids=row.data_source_ids_json,
            user_id=user_id,
            is_admin=False,
        )

    async def _validate_scope(
        self,
        db: AsyncSession,
        *,
        scope_type: str,
        sys_company_id: int | None,
        company_ids: list[int],
        data_source_ids: list[int],
        user_id: int,
        is_admin: bool,
    ) -> tuple[list[int], list[int]]:
        if scope_type not in self.allowed_scope_types:
            raise ValueError("报告范围类型不支持")
        if not is_admin:
            user_sys_company_id = await insight_permission_service.resolve_user_sys_company_id(db, user_id)
            if sys_company_id is not None and sys_company_id != user_sys_company_id:
                raise ValueError("无权选择其他所属公司的报告范围")
        if scope_type == "material_pool":
            return [], []
        if scope_type == "sys_company":
            if sys_company_id is None:
                raise ValueError("按所属公司生成报告时必须选择所属公司")
            company_ids = list(
                (
                    await db.exec(
                        select(InsightCompany.id).where(
                            InsightCompany.sys_company_id == sys_company_id,
                            InsightCompany.is_deleted == 0,
                            InsightCompany.status == "active",
                        )
                    )
                ).all()
            )
            return company_ids, []
        if scope_type == "company":
            ids = self._dedupe_ids(company_ids)
            if not ids:
                raise ValueError("按企业生成报告时必须选择至少一个企业")
            rows = list(
                (
                    await db.exec(
                        select(InsightCompany).where(
                            InsightCompany.id.in_(ids),
                            InsightCompany.is_deleted == 0,
                            InsightCompany.status == "active",
                        )
                    )
                ).all()
            )
            found = {row.id for row in rows}
            if len(found) != len(ids):
                raise ValueError("部分企业不存在或已停用")
            if not is_admin:
                user_sys_company_id = await insight_permission_service.resolve_user_sys_company_id(db, user_id)
                if any(row.sys_company_id != user_sys_company_id for row in rows):
                    raise ValueError("无权选择其他所属公司的企业")
            return ids, []
        ids = self._dedupe_ids(data_source_ids)
        if not ids:
            raise ValueError("按数据源生成报告时必须选择至少一个数据源")
        filters = [
            InsightDataSource.id.in_(ids),
            InsightDataSource.is_deleted == 0,
            InsightDataSource.status == "enabled",
        ]
        if not is_admin:
            filters.append(await self._data_source_company_scope_filter(db, user_id=user_id, is_admin=is_admin))
            filters.append(
                await insight_permission_service.visibility_filter_for_user(
                    db,
                    InsightDataSource,
                    target_type="data_source",
                    user_id=user_id,
                    is_admin=is_admin,
                )
            )
        found_ids = set((await db.exec(select(InsightDataSource.id).where(*filters))).all())
        if len(found_ids) != len(ids):
            raise ValueError("部分数据源不存在、已停用或无权访问")
        return [], ids

    async def _assert_template_visible(self, db: AsyncSession, template_code: str | None, *, user_id: int, is_admin: bool) -> None:
        if not template_code:
            return
        templates = await insight_report_service.list_templates(db, user_id=user_id, is_admin=is_admin)
        if not any(item.template_code == template_code for item in templates):
            raise ValueError("报告模板不存在或无权访问")

    async def _get_subscription(
        self,
        db: AsyncSession,
        subscription_id: int,
        *,
        user_id: int,
        is_admin: bool,
        permission: str = "view",
    ) -> InsightReportSubscription:
        filters = [InsightReportSubscription.id == subscription_id, InsightReportSubscription.is_deleted == 0]
        if not is_admin:
            filters.append(await self._subscription_company_scope_filter(db, user_id=user_id, is_admin=is_admin))
        filters.append(
            await insight_permission_service.visibility_filter_for_user(
                db,
                InsightReportSubscription,
                target_type="report_subscription",
                user_id=user_id,
                is_admin=is_admin,
                permission=permission,
            )
        )
        row = (await db.exec(select(InsightReportSubscription).where(*filters))).first()
        if not row:
            raise ValueError("报告计划不存在或无权访问")
        return row

    async def _subscription_company_scope_filter(self, db: AsyncSession, *, user_id: int | None, is_admin: bool):
        if is_admin:
            return True
        sys_company_id = await insight_permission_service.resolve_user_sys_company_id(db, user_id)
        return or_(InsightReportSubscription.sys_company_id.is_(None), InsightReportSubscription.sys_company_id == sys_company_id)

    async def _data_source_company_scope_filter(self, db: AsyncSession, *, user_id: int | None, is_admin: bool):
        if is_admin:
            return True
        sys_company_id = await insight_permission_service.resolve_user_sys_company_id(db, user_id)
        if sys_company_id is None:
            return InsightDataSource.company_id.is_(None)
        return or_(
            InsightDataSource.company_id.is_(None),
            exists()
            .where(
                and_(
                    InsightCompany.id == InsightDataSource.company_id,
                    InsightCompany.sys_company_id == sys_company_id,
                    InsightCompany.is_deleted == 0,
                )
            )
            .correlate(InsightDataSource),
        )

    async def _resolve_owner_dept_id(self, db: AsyncSession, user_id: int) -> int | None:
        user = await db.get(SysUser, user_id)
        return insight_permission_service.parse_int(user.dept_id if user else None)

    def _validate_payload(self, payload: InsightReportSubscriptionCreate) -> None:
        if payload.scope_type not in self.allowed_scope_types:
            raise ValueError("报告范围类型不支持")
        if payload.schedule_frequency not in self.allowed_frequencies:
            raise ValueError("定时频率仅支持 daily、weekly、monthly")
        if payload.status not in self.allowed_statuses:
            raise ValueError("计划状态仅支持 active 或 paused")
        if payload.visibility_scope not in self.allowed_visibility_scopes:
            raise ValueError("权限范围不支持")
        self._validate_time_of_day(payload.time_of_day)
        if payload.wecom_recipient_scope == "selected" and not payload.wecom_recipients:
            raise ValueError("请选择企业微信接收人")

    def _validate_row(self, row: InsightReportSubscription) -> None:
        if row.scope_type not in self.allowed_scope_types:
            raise ValueError("报告范围类型不支持")
        if row.schedule_frequency not in self.allowed_frequencies:
            raise ValueError("定时频率仅支持 daily、weekly、monthly")
        if row.status not in self.allowed_statuses:
            raise ValueError("计划状态仅支持 active 或 paused")
        if row.visibility_scope not in self.allowed_visibility_scopes:
            raise ValueError("权限范围不支持")
        self._validate_time_of_day(row.time_of_day)
        if row.wecom_recipient_scope == "selected" and not row.wecom_recipients_json:
            raise ValueError("请选择企业微信接收人")

    def _validate_time_of_day(self, value: str) -> None:
        try:
            hour, minute = [int(part) for part in value.split(":", 1)]
        except Exception as exc:
            raise ValueError("执行时间格式必须为 HH:mm") from exc
        if hour < 0 or hour > 23 or minute < 0 or minute > 59:
            raise ValueError("执行时间格式必须为 HH:mm")

    def _next_run_time(self, frequency: str, time_of_day: str, weekday: int | None, day_of_month: int | None) -> datetime:
        self._validate_time_of_day(time_of_day)
        hour, minute = [int(part) for part in time_of_day.split(":", 1)]
        now = datetime.now()
        candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if frequency == "daily":
            return candidate if candidate > now else candidate + timedelta(days=1)
        if frequency == "weekly":
            target_weekday = 0 if weekday is None else weekday
            days_ahead = (target_weekday - now.weekday()) % 7
            candidate = candidate + timedelta(days=days_ahead)
            return candidate if candidate > now else candidate + timedelta(days=7)
        if frequency == "monthly":
            target_day = max(min(day_of_month or 1, 31), 1)
            last_day = monthrange(now.year, now.month)[1]
            candidate = candidate.replace(day=min(target_day, last_day))
            if candidate > now:
                return candidate
            year = now.year + (1 if now.month == 12 else 0)
            month = 1 if now.month == 12 else now.month + 1
            last_day = monthrange(year, month)[1]
            return candidate.replace(year=year, month=month, day=min(target_day, last_day))
        raise ValueError("定时频率仅支持 daily、weekly、monthly")

    def _dedupe_ids(self, values: list[int]) -> list[int]:
        result: list[int] = []
        for value in values:
            try:
                parsed = int(value)
            except (TypeError, ValueError):
                continue
            if parsed > 0 and parsed not in result:
                result.append(parsed)
        return result

    def _recipient_to_dict(self, value: InsightNotificationRecipient | dict) -> dict:
        if isinstance(value, InsightNotificationRecipient):
            return value.model_dump(mode="json")
        return InsightNotificationRecipient.model_validate(value).model_dump(mode="json")

    def _to_read(self, row: InsightReportSubscription) -> InsightReportSubscriptionRead:
        return InsightReportSubscriptionRead(
            id=row.id or 0,
            create_time=row.create_time,
            update_time=row.update_time,
            subscription_uid=row.subscription_uid,
            subscription_name=row.subscription_name,
            report_type=row.report_type,
            template_code=row.template_code,
            scope_type=row.scope_type,
            sys_company_id=row.sys_company_id,
            company_ids=row.company_ids_json or [],
            data_source_ids=row.data_source_ids_json or [],
            folder_name=row.folder_name,
            max_materials=row.max_materials,
            generation_prompt=row.generation_prompt,
            schedule_frequency=row.schedule_frequency,
            weekday=row.weekday,
            day_of_month=row.day_of_month,
            time_of_day=row.time_of_day,
            timezone=row.timezone,
            next_run_time=row.next_run_time,
            last_run_time=row.last_run_time,
            last_report_id=row.last_report_id,
            last_notification_id=row.last_notification_id,
            last_status=row.last_status,
            last_error=row.last_error,
            wecom_recipient_scope=row.wecom_recipient_scope,
            wecom_recipients=[InsightNotificationRecipient.model_validate(item) for item in row.wecom_recipients_json],
            owner_user_id=row.owner_user_id,
            owner_dept_id=row.owner_dept_id,
            visibility_scope=row.visibility_scope,
            status=row.status,
        )


insight_report_subscription_service = InsightReportSubscriptionService()
