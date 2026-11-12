"""妙搭边界合同，显式限制输入尺寸及文档地址。"""
from datetime import datetime
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator


class WorkspaceInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CollectionNeed(WorkspaceInput):
    need: str = Field(min_length=5, max_length=3000)
    company: str = Field(default="", max_length=200)


class CollectionInput(CollectionNeed):
    id: str | None = Field(default=None, max_length=36)
    name: str = Field(min_length=1, max_length=100)
    keywords: list[str] = Field(min_length=1, max_length=12)
    excluded: list[str] = Field(default_factory=list, max_length=20)
    frequency: Literal["daily", "weekly", "manual"] = "daily"

    @field_validator("keywords", "excluded")
    @classmethod
    def normalize_words(cls, values: list[str]) -> list[str]:
        values = list(dict.fromkeys(value.strip() for value in values if value.strip()))
        if any(len(value) > 100 for value in values):
            raise ValueError("单个检索词不能超过100字")
        return values


class CollectionStatus(WorkspaceInput):
    id: str = Field(max_length=36)
    active: bool


def normalize_document_url(value: str) -> str:
    parsed = urlsplit(value)
    host = (parsed.hostname or "").lower()
    if (parsed.scheme != "https" or parsed.username or parsed.password or parsed.port
            or not (host == "feishu.cn" or host.endswith(".feishu.cn")
                    or host == "larksuite.com" or host.endswith(".larksuite.com"))):
        raise ValueError("请填写飞书云文档的 HTTPS 链接")
    parts = parsed.path.strip("/").split("/")
    if len(parts) != 2 or parts[0] not in {"docx", "docs", "wiki"} or not parts[1].isalnum():
        raise ValueError("仅支持飞书文档或知识库文档链接")
    # 登录令牌、分享追踪参数等不得进入目录或消息。
    return urlunsplit(("https", host, parsed.path, "", ""))


class ReportInput(WorkspaceInput):
    id: str | None = Field(default=None, max_length=36)
    title: str = Field(min_length=1, max_length=200)
    company: str = Field(default="", max_length=200)
    kind: str = Field(default="专题报告", min_length=1, max_length=30)
    url: str = Field(max_length=2000)
    summary: str = Field(default="", max_length=2000)

    @field_validator("url")
    @classmethod
    def document_url(cls, value: str) -> str:
        return normalize_document_url(value)


class ReportQuery(WorkspaceInput):
    page: int = Field(default=1, ge=1, le=100000)
    size: int = Field(default=20, ge=1, le=100)
    keyword: str = Field(default="", max_length=200)
    company: str = Field(default="", max_length=200)
    source: Literal["", "uploaded", "generated"] = ""
    kind: str = Field(default="", max_length=30)


class PushInput(WorkspaceInput):
    id: str | None = Field(default=None, max_length=36)
    reportId: str = Field(min_length=1, max_length=64)
    recipientIds: list[str] = Field(min_length=1, max_length=30)
    frequency: Literal["once", "weekly"] = "once"
    scheduledAt: str = Field(default="", max_length=40)
    weekday: int = Field(default=1, ge=0, le=6)
    time: str = Field(default="09:00", pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")

    @field_validator("scheduledAt")
    @classmethod
    def valid_time(cls, value: str) -> str:
        if value:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                raise ValueError("计划时间必须包含时区")
        return value


class PushAction(WorkspaceInput):
    id: str = Field(max_length=36)
    action: Literal["preview", "send", "status"]
    confirmed: bool = False
    active: bool = False
    requestId: str | None = Field(default=None, min_length=16, max_length=64)


class ArchiveInput(WorkspaceInput):
    id: str = Field(max_length=36)
    kind: Literal["report", "collection", "push"]
