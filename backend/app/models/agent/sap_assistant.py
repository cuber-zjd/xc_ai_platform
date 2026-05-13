from enum import Enum
from typing import Any

from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field

from app.models.base import BaseDBModel


class SapEnvironment(str, Enum):
    DEV = "dev"
    QAS = "qas"
    PRD = "prd"
    SANDBOX = "sandbox"
    UNKNOWN = "unknown"


class SapSystemConfig(BaseDBModel, table=True):
    """SAP 系统连接配置。敏感密码只保存环境变量名，不保存明文。"""

    __tablename__ = "sap_system_config"

    name: str = Field(index=True, description="系统显示名")
    system_code: str = Field(index=True, description="系统编码，例如 PRD_800")
    company_code: str | None = Field(default=None, index=True, description="公司或隔离域")
    environment: SapEnvironment = Field(default=SapEnvironment.UNKNOWN, index=True)
    client: str = Field(default="800", index=True)
    language: str = Field(default="ZH")
    ashost: str | None = Field(default=None, description="应用服务器")
    mshost: str | None = Field(default=None, description="消息服务器")
    sysnr: str | None = Field(default=None, description="系统编号")
    group: str | None = Field(default=None, description="登录组")
    user_env_key: str | None = Field(default=None, description="RFC 用户环境变量名")
    password_env_key: str | None = Field(default=None, description="RFC 密码环境变量名")
    max_rows: int = Field(default=100)
    is_production: bool = Field(default=False, index=True)
    is_enabled: bool = Field(default=True, index=True)
    allow_web_search: bool = Field(default=False)
    allowed_tables: list[str] | None = Field(default=None, sa_type=JSONB)
    allowed_objects: list[str] | None = Field(default=None, sa_type=JSONB)
    config_metadata: dict[str, Any] | None = Field(default=None, sa_type=JSONB)


class SapAssistantSession(BaseDBModel, table=True):
    __tablename__ = "sap_assistant_session"

    user_id: int | None = Field(default=None, index=True)
    title: str = Field(default="SAP 助手会话")
    sap_system_id: int | None = Field(default=None, foreign_key="sap_system_config.id", index=True)
    knowledge_base_ids: list[int] | None = Field(default=None, sa_type=JSONB)
    status: str = Field(default="active", index=True)
    summary: str | None = Field(default=None)


class SapAssistantMessage(BaseDBModel, table=True):
    __tablename__ = "sap_assistant_message"

    session_id: int = Field(foreign_key="sap_assistant_session.id", index=True)
    role: str = Field(index=True, description="user / assistant / tool")
    content: str
    message_metadata: dict[str, Any] | None = Field(default=None, sa_type=JSONB)


class SapToolCall(BaseDBModel, table=True):
    __tablename__ = "sap_tool_call"

    session_id: int | None = Field(default=None, foreign_key="sap_assistant_session.id", index=True)
    sap_system_id: int | None = Field(default=None, foreign_key="sap_system_config.id", index=True)
    tool_name: str = Field(index=True)
    status: str = Field(default="pending", index=True)
    request_payload: dict[str, Any] | None = Field(default=None, sa_type=JSONB)
    response_payload: dict[str, Any] | None = Field(default=None, sa_type=JSONB)
    duration_ms: int | None = Field(default=None)
    error_message: str | None = Field(default=None)


class SapEvidenceRecord(BaseDBModel, table=True):
    __tablename__ = "sap_evidence_record"

    session_id: int | None = Field(default=None, foreign_key="sap_assistant_session.id", index=True)
    tool_call_id: int | None = Field(default=None, foreign_key="sap_tool_call.id", index=True)
    sap_system_id: int | None = Field(default=None, foreign_key="sap_system_config.id", index=True)
    evidence_type: str = Field(index=True, description="source / ddic / log / data / kb / lineage")
    title: str
    summary: str | None = Field(default=None)
    source_object: str | None = Field(default=None, index=True)
    location: str | None = Field(default=None)
    confidence: float = Field(default=0.7)
    content: dict[str, Any] | None = Field(default=None, sa_type=JSONB)
