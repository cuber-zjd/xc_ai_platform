from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class InsightFeishuFieldOption(BaseModel):
    code: str
    label: str
    field_type: int
    required: bool = False
    default_selected: bool = True


class InsightFeishuSyncOptionsRead(BaseModel):
    configured: bool
    enabled: bool
    table_name: str = "情报中心"
    fields: list[InsightFeishuFieldOption]
    warnings: list[str] = Field(default_factory=list)


class InsightFeishuSyncRequest(BaseModel):
    scope: Literal["selected", "date_range"] = "date_range"
    intelligence_ids: list[int] = Field(default_factory=list, max_length=2000)
    date_from: datetime | None = None
    date_to: datetime | None = None
    field_codes: list[str] = Field(default_factory=list)
    update_existing: bool = True
    ensure_metadata: bool = True

    @model_validator(mode="after")
    def validate_scope(self) -> "InsightFeishuSyncRequest":
        if self.scope == "selected" and not self.intelligence_ids:
            raise ValueError("请选择需要同步的情报")
        if self.scope == "date_range" and (not self.date_from or not self.date_to):
            raise ValueError("请选择同步时间范围")
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("开始时间不能晚于结束时间")
        return self


class InsightFeishuSyncResponse(BaseModel):
    task_id: int
    requested_count: int
    eligible_count: int
    created_count: int
    updated_count: int
    skipped_count: int
    failed_count: int
    metadata_created_fields: list[str] = Field(default_factory=list)
    metadata_updated_fields: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[dict[str, Any]] = Field(default_factory=list)
