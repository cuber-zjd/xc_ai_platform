from datetime import datetime
from typing import Any

from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field

from app.models.base import BaseDBModel


class InsightNotification(BaseDBModel, table=True):
    """Insight 通知与企业微信推送记录。"""

    __tablename__ = "insight_notification"

    notification_uid: str = Field(index=True, unique=True, max_length=64)
    channel: str = Field(default="wecom", index=True, max_length=30)
    title: str = Field(index=True, max_length=300)
    content: str | None = Field(default=None)
    target_type: str = Field(index=True, max_length=30)
    target_id: int = Field(index=True)
    target_title: str | None = Field(default=None, max_length=300)
    recipient_scope: str = Field(default="selected", index=True, max_length=30)
    recipients_json: list[dict[str, Any]] = Field(default_factory=list, sa_type=JSONB)
    payload_json: dict[str, Any] = Field(default_factory=dict, sa_type=JSONB)
    status: str = Field(default="pending", index=True, max_length=30)
    permission_status: str = Field(default="unchecked", index=True, max_length=30)
    scheduled_at: datetime | None = Field(default=None, index=True)
    sent_at: datetime | None = Field(default=None, index=True)
    error_message: str | None = Field(default=None, max_length=1000)
    created_by_user_id: int | None = Field(default=None, index=True)
