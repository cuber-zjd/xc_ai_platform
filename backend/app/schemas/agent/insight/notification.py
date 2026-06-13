from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.agent.insight.common import InsightBaseRead


class InsightNotificationRecipient(BaseModel):
    recipient_type: str = Field(default="user", max_length=30)
    recipient_id: int | None = None
    recipient_name: str | None = Field(default=None, max_length=120)
    wecom_userid: str | None = Field(default=None, max_length=120)


class InsightNotificationCreate(BaseModel):
    channel: str = Field(default="wecom", max_length=30)
    target_type: str = Field(max_length=30)
    target_id: int
    title: str | None = Field(default=None, max_length=300)
    content: str | None = Field(default=None, max_length=2000)
    recipient_scope: str = Field(default="selected", max_length=30)
    recipients: list[InsightNotificationRecipient] = Field(default_factory=list)
    scheduled_at: datetime | None = None
    send_now: bool = False


class InsightNotificationRead(InsightBaseRead):
    notification_uid: str
    channel: str
    title: str
    content: str | None = None
    target_type: str
    target_id: int
    target_title: str | None = None
    recipient_scope: str
    recipients: list[InsightNotificationRecipient] = Field(default_factory=list)
    payload_json: dict[str, Any] = Field(default_factory=dict)
    status: str
    permission_status: str
    scheduled_at: datetime | None = None
    sent_at: datetime | None = None
    error_message: str | None = None
    created_by_user_id: int | None = None


class InsightNotificationListParams(BaseModel):
    target_type: str | None = None
    target_id: int | None = None
    channel: str | None = None
    status: str | None = None
