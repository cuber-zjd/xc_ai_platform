import asyncio
from uuid import uuid4

from sqlmodel import SQLModel, select

from app.core.config import settings
from app.db.session import async_session, engine
from app.models.agent.insight import InsightNotification, InsightReport
from app.models.system.sys_user import SysUser
from app.schemas.agent.insight.notification import InsightNotificationCreate, InsightNotificationRecipient
from app.services.agent.insight.notification_service import insight_notification_service


MARK = "insight-notification-acceptance"


async def main() -> None:
    token = uuid4().hex[:10]
    created: dict[str, list[int]] = {"users": [], "reports": [], "notifications": []}
    original_send_enabled = settings.INSIGHT_WECOM_SEND_ENABLED
    original_send = insight_notification_service._send_wecom_message

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    async with async_session() as db:
        try:
            owner = SysUser(
                username=f"insight_notify_owner_{token}",
                full_name=f"Insight 通知验收所有者 {token}",
                employee_id=f"IN{token}",
                job_title=f"Insight通知验收岗位{token}",
                hashed_password="acceptance-only",
                create_by=MARK,
                update_by=MARK,
            )
            other = SysUser(
                username=f"insight_notify_other_{token}",
                full_name=f"Insight 通知验收无权用户 {token}",
                employee_id=f"OUT{token}",
                hashed_password="acceptance-only",
                create_by=MARK,
                update_by=MARK,
            )
            db.add(owner)
            db.add(other)
            await db.flush()
            created["users"].extend([owner.id or 0, other.id or 0])

            report = InsightReport(
                report_uid=f"notification_acceptance_report_{token}",
                title=f"通知推送验收报告 {token}",
                report_type="专题报告",
                content_json={"executive_summary": "用于验证企业微信推送权限边界。", "chapters": []},
                summary="通知推送验收摘要",
                status="draft",
                version_no=1,
                material_count=0,
                owner_user_id=owner.id,
                visibility_scope="private",
                create_by=MARK,
                update_by=MARK,
            )
            db.add(report)
            await db.commit()
            await db.refresh(report)
            created["reports"].append(report.id or 0)

            settings.INSIGHT_WECOM_SEND_ENABLED = False
            sent = await insight_notification_service.create_notification(
                db,
                InsightNotificationCreate(
                    channel="wecom",
                    target_type="report",
                    target_id=report.id or 0,
                    title="通知推送验收",
                    content="这是一条模拟企业微信推送。",
                    recipient_scope="selected",
                    recipients=[
                        InsightNotificationRecipient(
                            recipient_type="user",
                            recipient_id=owner.id,
                            recipient_name=owner.full_name,
                        )
                    ],
                    send_now=True,
                ),
                user_id=owner.id or 0,
                is_admin=False,
            )
            created["notifications"].append(sent.id)

            scheduled = await insight_notification_service.create_notification(
                db,
                InsightNotificationCreate(
                    channel="wecom",
                    target_type="report",
                    target_id=report.id or 0,
                    recipient_scope="all",
                    recipients=[],
                    send_now=False,
                ),
                user_id=owner.id or 0,
                is_admin=False,
            )
            created["notifications"].append(scheduled.id)

            retried_mock = await insight_notification_service.retry_notification(
                db,
                sent.id,
                user_id=owner.id or 0,
                is_admin=False,
            )

            job_userids = await insight_notification_service._resolve_wecom_userids(
                db,
                [{"recipient_type": "job", "recipient_name": owner.job_title}],
            )

            fake_send_calls: list[dict] = []

            async def fake_send_success(*, touser: list[str], title: str, content: str, target_url: str) -> None:
                fake_send_calls.append({"touser": touser, "title": title, "content": content, "target_url": target_url})

            async def fake_send_failure(*, touser: list[str], title: str, content: str, target_url: str) -> None:
                fake_send_calls.append({"touser": touser, "title": title, "content": content, "target_url": target_url, "failed": True})
                raise RuntimeError("fake wecom failure")

            settings.INSIGHT_WECOM_SEND_ENABLED = True
            insight_notification_service._send_wecom_message = fake_send_success
            real_sent = await insight_notification_service.create_notification(
                db,
                InsightNotificationCreate(
                    channel="wecom",
                    target_type="report",
                    target_id=report.id or 0,
                    title="真实发送路径验收",
                    content="这条消息不会请求真实企业微信，只验证发送路径。",
                    recipient_scope="selected",
                    recipients=[
                        InsightNotificationRecipient(
                            recipient_type="user",
                            recipient_id=owner.id,
                            recipient_name=owner.full_name,
                        )
                    ],
                    send_now=True,
                ),
                user_id=owner.id or 0,
                is_admin=False,
            )
            created["notifications"].append(real_sent.id)

            insight_notification_service._send_wecom_message = fake_send_failure
            real_failed = await insight_notification_service.create_notification(
                db,
                InsightNotificationCreate(
                    channel="wecom",
                    target_type="report",
                    target_id=report.id or 0,
                    title="真实发送失败验收",
                    content="这条消息用于验证失败记录和人工重试。",
                    recipient_scope="selected",
                    recipients=[
                        InsightNotificationRecipient(
                            recipient_type="user",
                            recipient_name=owner.employee_id,
                        )
                    ],
                    send_now=True,
                ),
                user_id=owner.id or 0,
                is_admin=False,
            )
            created["notifications"].append(real_failed.id)

            insight_notification_service._send_wecom_message = fake_send_success
            retried_real = await insight_notification_service.retry_notification(
                db,
                real_failed.id,
                user_id=owner.id or 0,
                is_admin=False,
            )

            empty_recipient_rejected = False
            try:
                await insight_notification_service.create_notification(
                    db,
                    InsightNotificationCreate(
                        channel="wecom",
                        target_type="report",
                        target_id=report.id or 0,
                        recipient_scope="selected",
                        recipients=[],
                        send_now=True,
                    ),
                    user_id=owner.id or 0,
                    is_admin=False,
                )
            except ValueError:
                empty_recipient_rejected = True

            invalid_channel_rejected = False
            try:
                await insight_notification_service.create_notification(
                    db,
                    InsightNotificationCreate(
                        channel="email",
                        target_type="report",
                        target_id=report.id or 0,
                        recipient_scope="all",
                        send_now=True,
                    ),
                    user_id=owner.id or 0,
                    is_admin=False,
                )
            except ValueError:
                invalid_channel_rejected = True

            unauthorized_rejected = False
            try:
                await insight_notification_service.create_notification(
                    db,
                    InsightNotificationCreate(
                        channel="wecom",
                        target_type="report",
                        target_id=report.id or 0,
                        recipient_scope="all",
                        send_now=True,
                    ),
                    user_id=other.id or 0,
                    is_admin=False,
                )
            except ValueError:
                unauthorized_rejected = True

            owner_list = await insight_notification_service.list_notifications(
                db,
                page=1,
                size=20,
                target_type="report",
                target_id=report.id,
                channel=None,
                status=None,
                user_id=owner.id or 0,
                is_admin=False,
            )
            other_list = await insight_notification_service.list_notifications(
                db,
                page=1,
                size=20,
                target_type="report",
                target_id=report.id,
                channel=None,
                status=None,
                user_id=other.id or 0,
                is_admin=False,
            )

            checks = {
                "模拟推送记录创建成功": sent.status == "sent_mock" and sent.permission_status == "checked",
                "模拟推送明确未真实发送": sent.payload_json.get("real_send_enabled") is False and sent.sent_at is not None,
                "模拟记录支持人工重试": retried_mock.status == "sent_mock" and int(retried_mock.payload_json.get("retry_count") or 0) >= 1,
                "岗位接收对象可按工号展开": job_userids == [owner.employee_id],
                "真实发送路径可按工号发送": real_sent.status == "sent" and fake_send_calls[0]["touser"] == [owner.employee_id],
                "真实发送失败会落库": real_failed.status == "failed" and bool(real_failed.error_message),
                "失败记录支持人工重试": retried_real.status == "sent" and int(retried_real.payload_json.get("retry_count") or 0) >= 1,
                "全员计划推送规范化": scheduled.status == "pending" and scheduled.recipient_scope == "all" and scheduled.recipients[0].recipient_type == "all",
                "空接收人被拒绝": empty_recipient_rejected,
                "非法渠道被拒绝": invalid_channel_rejected,
                "无权用户不能推送私有报告": unauthorized_rejected,
                "创建人可查看自己的推送记录": owner_list.total >= 4 and {sent.id, scheduled.id, real_sent.id, real_failed.id}.issubset({item.id for item in owner_list.items}),
                "普通用户看不到他人推送记录": other_list.total == 0,
            }
            for name, passed in checks.items():
                print(f"[{'PASS' if passed else 'FAIL'}] {name}")
            if not all(checks.values()):
                failed = [name for name, passed in checks.items() if not passed]
                raise SystemExit(f"Insight 通知推送验收未通过: {'; '.join(failed)}")
            print(
                {
                    "report_id": report.id,
                    "sent_mock": sent.model_dump(mode="json"),
                    "scheduled": scheduled.model_dump(mode="json"),
                    "real_sent": real_sent.model_dump(mode="json"),
                    "retried_real": retried_real.model_dump(mode="json"),
                }
            )
        finally:
            settings.INSIGHT_WECOM_SEND_ENABLED = original_send_enabled
            insight_notification_service._send_wecom_message = original_send
            await cleanup(db, created)


async def cleanup(db, created: dict[str, list[int]]) -> None:
    model_map = {
        "notifications": InsightNotification,
        "reports": InsightReport,
        "users": SysUser,
    }
    for key, model in model_map.items():
        ids = [item_id for item_id in created[key] if item_id]
        if not ids:
            continue
        rows = list((await db.exec(select(model).where(model.id.in_(ids)))).all())
        for row in rows:
            row.is_deleted = 1
            row.update_by = f"{MARK}-cleanup"
        await db.commit()


if __name__ == "__main__":
    asyncio.run(main())
