from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class SapSystemCreate(BaseModel):
    name: str
    system_code: str
    company_code: str | None = None
    environment: str = "unknown"
    client: str = "800"
    language: str = "ZH"
    ashost: str | None = None
    mshost: str | None = None
    sysnr: str | None = None
    group: str | None = None
    user_env_key: str | None = None
    password_env_key: str | None = None
    max_rows: int = Field(default=100, ge=1, le=1000)
    is_production: bool = False
    is_enabled: bool = True
    allow_web_search: bool = False
    allowed_tables: list[str] | None = None
    allowed_objects: list[str] | None = None


class SapSystemRead(SapSystemCreate):
    id: int
    create_time: datetime
    update_time: datetime

    class Config:
        from_attributes = True


class SapToolEvidence(BaseModel):
    evidence_type: str
    title: str
    summary: str | None = None
    source_object: str | None = None
    location: str | None = None
    confidence: float = 0.7
    content: dict[str, Any] | None = None


class SapToolResult(BaseModel):
    tool_name: str
    status: Literal["success", "failed", "skipped"]
    summary: str
    duration_ms: int = 0
    data: dict[str, Any] | list[dict[str, Any]] | list[str] | None = None
    evidence: list[SapToolEvidence] = []
    error_message: str | None = None


class SapAssistantChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    session_id: int | None = None
    sap_system_id: int | None = None
    knowledge_base_ids: list[int] = []
    model_name: str | None = Field(default=None, description="指定模型名称；为空时使用默认复杂推理模型")
    require_confirmation_token: str | None = None


class SapAssistantChatResponse(BaseModel):
    session_id: int
    answer: str
    system_context: dict[str, Any] | None = None
    timeline: list[dict[str, Any]]
    tool_results: list[SapToolResult]
    evidence: list[SapToolEvidence]
    flowchart: str | None = None
    requires_confirmation: bool = False
    confirmation_payload: dict[str, Any] | None = None


class SapAssistantSessionRead(BaseModel):
    id: int
    title: str
    sap_system_id: int | None = None
    knowledge_base_ids: list[int] | None = None
    status: str
    summary: str | None = None
    create_time: datetime
    update_time: datetime

    class Config:
        from_attributes = True


class SapAssistantMessageRead(BaseModel):
    id: int
    session_id: int
    role: str
    content: str
    message_metadata: dict[str, Any] | None = None
    create_time: datetime

    class Config:
        from_attributes = True


class SapStreamChunk(BaseModel):
    id: str
    type: str
    data: dict[str, Any]
    timestamp: int
