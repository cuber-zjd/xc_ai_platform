from datetime import datetime, timedelta
from urllib.parse import urljoin, urlparse
from uuid import uuid4

import httpx
from sqlalchemy import or_
from sqlmodel import func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.models.agent.insight import InsightNotification
from app.models.system.sys_role import SysUserRole
from app.models.system.sys_user import SysUser
from app.schemas.agent.insight.notification import InsightNotificationCreate, InsightNotificationRead, InsightNotificationRecipient
from app.schemas.page import Page
from app.services.agent.insight.intelligence_service import insight_intelligence_service
from app.services.agent.insight.report_service import insight_report_service


class InsightNotificationService:
    allowed_channels = {"wecom"}
    allowed_target_types = {"report", "intelligence"}
    allowed_recipient_scopes = {"selected", "all"}
    allowed_recipient_types = {"user", "dept", "role", "job", "all"}
    _access_token: str | None = None
    _access_token_expire_at: datetime | None = None

    async def list_notifications(
        self,
        db: AsyncSession,
        *,
        page: int,
        size: int,
        target_type: str | None,
        target_id: int | None,
        channel: str | None,
        status: str | None,
        user_id: int,
        is_admin: bool,
    ) -> Page[InsightNotificationRead]:
        page = max(page, 1)
        size = min(max(size, 1), 100)
        filters = [InsightNotification.is_deleted == 0]
        if target_type:
            filters.append(InsightNotification.target_type == target_type)
        if target_id:
            filters.append(InsightNotification.target_id == target_id)
        if channel:
            filters.append(InsightNotification.channel == channel)
        if status:
            filters.append(InsightNotification.status == status)
        if not is_admin:
            filters.append(InsightNotification.created_by_user_id == user_id)
        total = (await db.exec(select(func.count()).select_from(InsightNotification).where(*filters))).one()
        rows = list(
            (
                await db.exec(
                    select(InsightNotification)
                    .where(*filters)
                    .order_by(InsightNotification.create_time.desc(), InsightNotification.id.desc())
                    .offset((page - 1) * size)
                    .limit(size)
                )
            ).all()
        )
        return Page.create(items=[self._to_read(row) for row in rows], total=total, page=page, size=size)

    async def create_notification(
        self,
        db: AsyncSession,
        payload: InsightNotificationCreate,
        *,
        user_id: int,
        is_admin: bool,
    ) -> InsightNotificationRead:
        recipients = self._normalize_recipients(payload)
        target = await self._load_target(db, payload=payload, user_id=user_id, is_admin=is_admin)
        permission_status = "checked"
        status = "pending"
        error_message = None
        if not recipients and payload.recipient_scope == "selected":
            permission_status = "blocked"
            status = "blocked"
            error_message = "未选择接收人"
        elif payload.send_now and not settings.INSIGHT_WECOM_SEND_ENABLED:
            status = "sent_mock"

        row = InsightNotification(
            notification_uid=f"insight_notify_{uuid4().hex}",
            channel=payload.channel,
            title=payload.title or target["default_title"],
            content=payload.content or target["default_content"],
            target_type=payload.target_type,
            target_id=payload.target_id,
            target_title=target["target_title"],
            recipient_scope=payload.recipient_scope,
            recipients_json=recipients,
            payload_json={
                "target_url": target["target_url"],
                "target_summary": target["target_summary"],
                "send_mode": "real" if payload.send_now and settings.INSIGHT_WECOM_SEND_ENABLED else "mock" if payload.send_now else "scheduled",
                "real_send_enabled": settings.INSIGHT_WECOM_SEND_ENABLED,
                "mock_reason": "企业微信真实发送未启用，请配置 INSIGHT_WECOM_* 环境变量并打开 INSIGHT_WECOM_SEND_ENABLED",
                "permission_checked_by": "current_user_visibility",
            },
            status=status,
            permission_status=permission_status,
            scheduled_at=payload.scheduled_at,
            sent_at=datetime.now() if status == "sent_mock" else None,
            error_message=error_message,
            created_by_user_id=user_id,
            create_by=str(user_id),
            update_by=str(user_id),
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        if payload.send_now and settings.INSIGHT_WECOM_SEND_ENABLED:
            await self._deliver_notification(db, row, user_id=user_id)
            await db.refresh(row)
        return self._to_read(row)

    async def retry_notification(
        self,
        db: AsyncSession,
        notification_id: int,
        *,
        user_id: int,
        is_admin: bool,
    ) -> InsightNotificationRead:
        row = (
            await db.exec(
                select(InsightNotification).where(
                    InsightNotification.id == notification_id,
                    InsightNotification.is_deleted == 0,
                )
            )
        ).first()
        if not row:
            raise ValueError("推送记录不存在")
        if not is_admin and row.created_by_user_id != user_id:
            raise ValueError("无权重试该推送记录")
        if row.status not in {"failed", "pending", "sent_mock"}:
            raise ValueError("当前推送状态不支持重试")
        await self._assert_target_visible(db, row, user_id=user_id, is_admin=is_admin)
        await self._deliver_notification(db, row, user_id=user_id)
        await db.refresh(row)
        return self._to_read(row)

    async def _deliver_notification(self, db: AsyncSession, row: InsightNotification, *, user_id: int) -> None:
        payload = dict(row.payload_json or {})
        retry_count = int(payload.get("retry_count") or 0)
        max_retry_attempts = max(settings.INSIGHT_WECOM_RETRY_MAX_ATTEMPTS, 1)
        if row.status in {"failed", "sent_mock"} and retry_count >= max_retry_attempts:
            raise ValueError(f"已达到企业微信推送最大重试次数: {max_retry_attempts}")
        payload["retry_count"] = retry_count + (1 if row.status in {"failed", "sent_mock"} else 0)
        payload["max_retry_attempts"] = max_retry_attempts
        row.payload_json = payload
        row.update_time = datetime.now()
        row.update_by = str(user_id)

        if not settings.INSIGHT_WECOM_SEND_ENABLED:
            row.status = "sent_mock"
            row.sent_at = datetime.now()
            row.error_message = None
            row.payload_json = {
                **payload,
                "send_mode": "mock",
                "real_send_enabled": False,
                "mock_reason": "企业微信真实发送未启用，请配置 INSIGHT_WECOM_* 环境变量并打开 INSIGHT_WECOM_SEND_ENABLED",
            }
            await db.commit()
            return

        try:
            touser = await self._resolve_wecom_userids(db, row.recipients_json)
            await self._send_wecom_message(
                touser=touser,
                title=row.title,
                content=row.content or "",
                target_url=str((row.payload_json or {}).get("target_url") or ""),
            )
            row.status = "sent"
            row.sent_at = datetime.now()
            row.error_message = None
        except Exception as exc:
            row.status = "failed"
            row.error_message = str(exc)[:1000]
        await db.commit()

    async def _assert_target_visible(self, db: AsyncSession, row: InsightNotification, *, user_id: int, is_admin: bool) -> None:
        payload = InsightNotificationCreate(
            channel=row.channel,
            target_type=row.target_type,
            target_id=row.target_id,
            recipient_scope=row.recipient_scope,
            recipients=[InsightNotificationRecipient.model_validate(item) for item in row.recipients_json],
        )
        await self._load_target(db, payload=payload, user_id=user_id, is_admin=is_admin)

    async def _resolve_wecom_userids(self, db: AsyncSession, recipients: list[dict]) -> list[str]:
        if any(item.get("recipient_type") == "all" for item in recipients):
            return ["@all"]
        userids: set[str] = set()
        missing: list[str] = []
        for item in recipients:
            recipient_type = str(item.get("recipient_type") or "").lower()
            if recipient_type == "user":
                userid = await self._resolve_single_userid(db, item)
                if userid:
                    userids.add(userid)
                else:
                    missing.append(str(item.get("recipient_name") or item.get("recipient_id") or "user"))
            elif recipient_type == "dept":
                users = list(
                    (
                        await db.exec(
                            select(SysUser).where(
                                SysUser.is_deleted == 0,
                                SysUser.status == 1,
                                SysUser.dept_id == str(item.get("recipient_id") or item.get("recipient_name") or ""),
                            )
                        )
                    ).all()
                )
                self._collect_employee_ids(users, userids, missing, f"dept:{item.get('recipient_name') or item.get('recipient_id')}")
            elif recipient_type == "role":
                role_id = item.get("recipient_id")
                if role_id is None:
                    missing.append(str(item.get("recipient_name") or "role"))
                    continue
                users = list(
                    (
                        await db.exec(
                            select(SysUser)
                            .join(SysUserRole, SysUserRole.user_id == SysUser.id)
                            .where(
                                SysUser.is_deleted == 0,
                                SysUser.status == 1,
                                SysUserRole.is_deleted == 0,
                                SysUserRole.role_id == int(role_id),
                            )
                        )
                    ).all()
                )
                self._collect_employee_ids(users, userids, missing, f"role:{item.get('recipient_name') or role_id}")
            elif recipient_type == "job":
                job_title = str(item.get("recipient_name") or item.get("wecom_userid") or "").strip()
                users = list(
                    (
                        await db.exec(
                            select(SysUser).where(
                                SysUser.is_deleted == 0,
                                SysUser.status == 1,
                                SysUser.job_title == job_title,
                            )
                        )
                    ).all()
                )
                self._collect_employee_ids(users, userids, missing, f"job:{job_title}")
        if not userids:
            raise ValueError("未找到可用于企业微信发送的工号")
        if missing:
            raise ValueError(f"以下接收对象缺少工号或无法匹配用户: {', '.join(missing[:10])}")
        return sorted(userids)

    async def _resolve_single_userid(self, db: AsyncSession, item: dict) -> str | None:
        if item.get("wecom_userid"):
            return str(item["wecom_userid"]).strip()
        user = None
        if item.get("recipient_id") is not None:
            user = await db.get(SysUser, int(item["recipient_id"]))
        if not user and item.get("recipient_name"):
            value = str(item["recipient_name"]).strip()
            user = (
                await db.exec(
                    select(SysUser).where(
                        SysUser.is_deleted == 0,
                        or_(SysUser.employee_id == value, SysUser.username == value, SysUser.full_name == value),
                    )
                )
            ).first()
        if not user or user.is_deleted != 0 or user.status != 1:
            return None
        return user.employee_id or user.username

    def _collect_employee_ids(self, users: list[SysUser], userids: set[str], missing: list[str], label: str) -> None:
        if not users:
            missing.append(label)
            return
        for user in users:
            if user.employee_id:
                userids.add(user.employee_id)
            elif user.username:
                userids.add(user.username)
            else:
                missing.append(user.full_name or str(user.id))

    async def _send_wecom_text_message_legacy(self, *, touser: list[str], title: str, content: str, target_url: str) -> None:
        self._validate_wecom_settings()
        token = await self._get_wecom_access_token()
        text = f"{title}\n\n{content or '请进入研发营销市场洞察平台查看详情。'}"
        if target_url:
            text = f"{text}\n\n链接：{target_url}"
        body = {
            "touser": "|".join(touser),
            "msgtype": "text",
            "agentid": int(settings.INSIGHT_WECOM_AGENT_ID),
            "text": {"content": text[:2048]},
            "safe": 0,
        }
        url = f"{settings.INSIGHT_WECOM_BASE_URL.rstrip('/')}/cgi-bin/message/send"
        async with httpx.AsyncClient(timeout=settings.INSIGHT_WECOM_TIMEOUT_SECONDS) as client:
            response = await client.post(url, params={"access_token": token}, json=body)
            response.raise_for_status()
            data = response.json()
        if data.get("errcode") != 0:
            raise ValueError(f"企业微信发送失败: {data.get('errmsg') or data}")

    async def _send_wecom_message(self, *, touser: list[str], title: str, content: str, target_url: str) -> None:
        self._validate_wecom_settings()
        token = await self._get_wecom_access_token()
        absolute_url = self._absolute_target_url(target_url)
        body = {
            "touser": "|".join(touser),
            "agentid": int(settings.INSIGHT_WECOM_AGENT_ID),
            "safe": 0,
        }
        if absolute_url:
            body.update(
                {
                    "msgtype": "textcard",
                    "textcard": {
                        "title": title[:128],
                        "description": (content or "请进入研发营销市场洞察平台查看详情。")[:512],
                        "url": absolute_url,
                        "btntxt": "查看详情",
                    },
                }
            )
        else:
            text = f"{title}\n\n{content or '请进入研发营销市场洞察平台查看详情。'}"
            if target_url:
                text = f"{text}\n\n链接：{target_url}"
            body.update({"msgtype": "text", "text": {"content": text[:2048]}})

        url = f"{settings.INSIGHT_WECOM_BASE_URL.rstrip('/')}/cgi-bin/message/send"
        async with httpx.AsyncClient(timeout=settings.INSIGHT_WECOM_TIMEOUT_SECONDS) as client:
            response = await client.post(url, params={"access_token": token}, json=body)
            response.raise_for_status()
            data = response.json()
        if data.get("errcode") != 0:
            raise ValueError(f"企业微信发送失败: {data.get('errmsg') or data}")

    def _absolute_target_url(self, target_url: str) -> str:
        target_url = (target_url or "").strip()
        if not target_url:
            return ""
        parsed = urlparse(target_url)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            return target_url
        base_url = settings.INSIGHT_PUBLIC_BASE_URL.strip()
        if not base_url:
            return ""
        return urljoin(f"{base_url.rstrip('/')}/", target_url.lstrip("/"))

    async def _get_wecom_access_token(self) -> str:
        if self._access_token and self._access_token_expire_at and self._access_token_expire_at > datetime.now():
            return self._access_token
        self._validate_wecom_settings()
        url = f"{settings.INSIGHT_WECOM_BASE_URL.rstrip('/')}/cgi-bin/gettoken"
        async with httpx.AsyncClient(timeout=settings.INSIGHT_WECOM_TIMEOUT_SECONDS) as client:
            response = await client.get(
                url,
                params={"corpid": settings.INSIGHT_WECOM_CORP_ID, "corpsecret": settings.INSIGHT_WECOM_SECRET},
            )
            response.raise_for_status()
            data = response.json()
        if data.get("errcode") != 0 or not data.get("access_token"):
            raise ValueError(f"企业微信 access_token 获取失败: {data.get('errmsg') or data}")
        self._access_token = str(data["access_token"])
        self._access_token_expire_at = datetime.now() + timedelta(seconds=max(int(data.get("expires_in") or 7200) - 300, 60))
        return self._access_token

    def _validate_wecom_settings(self) -> None:
        missing = []
        if not settings.INSIGHT_WECOM_CORP_ID:
            missing.append("INSIGHT_WECOM_CORP_ID")
        if not settings.INSIGHT_WECOM_AGENT_ID:
            missing.append("INSIGHT_WECOM_AGENT_ID")
        if not settings.INSIGHT_WECOM_SECRET:
            missing.append("INSIGHT_WECOM_SECRET")
        if missing:
            raise ValueError(f"企业微信配置缺失: {', '.join(missing)}")

    def _normalize_recipients(self, payload: InsightNotificationCreate) -> list[dict]:
        channel = payload.channel.lower().strip()
        if channel not in self.allowed_channels:
            raise ValueError("当前仅支持企业微信 wecom 推送渠道")
        payload.channel = channel

        target_type = payload.target_type.lower().strip()
        if target_type not in self.allowed_target_types:
            raise ValueError("暂仅支持推送报告或正式情报")
        payload.target_type = target_type

        recipient_scope = payload.recipient_scope.lower().strip()
        if recipient_scope not in self.allowed_recipient_scopes:
            raise ValueError("接收范围仅支持 selected 或 all")
        payload.recipient_scope = recipient_scope

        if recipient_scope == "all":
            return [{"recipient_type": "all", "recipient_id": None, "recipient_name": "全员", "wecom_userid": None}]

        recipients: list[dict] = []
        for item in payload.recipients:
            recipient_type = item.recipient_type.lower().strip()
            if recipient_type not in self.allowed_recipient_types or recipient_type == "all":
                raise ValueError("接收人类型仅支持 user、dept 或 role")
            has_identity = item.recipient_id is not None or bool(item.recipient_name) or bool(item.wecom_userid)
            if not has_identity:
                raise ValueError("接收人必须提供平台 ID、名称或企业微信账号")
            data = item.model_dump(mode="json")
            data["recipient_type"] = recipient_type
            recipients.append(data)
        if not recipients:
            raise ValueError("请选择至少一个接收人")
        return recipients

    async def _load_target(
        self,
        db: AsyncSession,
        *,
        payload: InsightNotificationCreate,
        user_id: int,
        is_admin: bool,
    ) -> dict[str, str | None]:
        if payload.target_type == "report":
            report = await insight_report_service.get_report_detail(db, payload.target_id, user_id=user_id, is_admin=is_admin)
            return {
                "target_title": report.title,
                "target_summary": report.summary or "",
                "target_url": f"/insight/reports?report_id={report.id}",
                "default_title": f"市场洞察报告：{report.title}",
                "default_content": report.summary or "报告已生成，请进入研发营销市场洞察平台查看正文与引用来源。",
            }
        if payload.target_type == "intelligence":
            intelligence = await insight_intelligence_service.get_intelligence_detail(db, payload.target_id, user_id=user_id, is_admin=is_admin)
            return {
                "target_title": intelligence.title,
                "target_summary": intelligence.summary or "",
                "target_url": f"/insight/intelligence/{intelligence.id}",
                "default_title": f"市场情报：{intelligence.title}",
                "default_content": intelligence.summary or "发现一条新的市场情报，请进入研发营销市场洞察平台查看原文与证据。",
            }
        raise ValueError("暂仅支持推送报告或正式情报")

    def _to_read(self, row: InsightNotification) -> InsightNotificationRead:
        return InsightNotificationRead(
            id=row.id or 0,
            create_time=row.create_time,
            update_time=row.update_time,
            notification_uid=row.notification_uid,
            channel=row.channel,
            title=row.title,
            content=row.content,
            target_type=row.target_type,
            target_id=row.target_id,
            target_title=row.target_title,
            recipient_scope=row.recipient_scope,
            recipients=[InsightNotificationRecipient.model_validate(item) for item in row.recipients_json],
            payload_json=row.payload_json,
            status=row.status,
            permission_status=row.permission_status,
            scheduled_at=row.scheduled_at,
            sent_at=row.sent_at,
            error_message=row.error_message,
            created_by_user_id=row.created_by_user_id,
        )


insight_notification_service = InsightNotificationService()
