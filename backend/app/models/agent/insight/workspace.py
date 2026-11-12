"""妙搭工作空间数据；不复制旧报告正文，不改写原有简报计划。"""
from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import Column, JSON
from sqlmodel import SQLModel, Field


class InsightWorkspaceItem(SQLModel, table=True):
    __tablename__ = "insight_workspace_item"
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True, max_length=36)
    scope: str = Field(index=True, max_length=180)
    owner: str = Field(index=True, max_length=160)
    legacy_user_id: int = Field(index=True)
    kind: str = Field(index=True, max_length=30)
    payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    enabled: bool = Field(default=False, index=True)
    next_run: datetime | None = Field(default=None, index=True)
    last_status: str | None = Field(default=None, max_length=30)
    last_message: str | None = Field(default=None, max_length=500)
    request_id: str | None = Field(default=None, max_length=64)
    updated_at: datetime = Field(default_factory=datetime.now)
    created_at: datetime = Field(default_factory=datetime.now)
