from typing import Any, Literal

from pydantic import BaseModel, Field


class WeaverFieldContext(BaseModel):
    label: str = ""
    field_id: str = Field(alias="fieldId")
    type: str = "text"
    writable: bool = True
    value: Any = None


class WeaverFormContext(BaseModel):
    base_info: dict[str, Any] = Field(default_factory=dict, alias="baseInfo")
    url: str = ""
    fields: dict[str, WeaverFieldContext] = Field(default_factory=dict)


class WeaverAssistantChatRequest(BaseModel):
    message: str
    context: WeaverFormContext = Field(default_factory=WeaverFormContext)


class WeaverAssistantAction(BaseModel):
    type: Literal["set_field", "add_detail_row", "show_message"]
    field: str | None = None
    value: Any = None
    detail: str | None = None
    values: dict[str, Any] | None = None
    message: str | None = None
    label: str | None = None


class WeaverAssistantChatResponse(BaseModel):
    message: str
    actions: list[WeaverAssistantAction] = Field(default_factory=list)


class WeaverFieldConfigItem(BaseModel):
    biz_key: str = Field(alias="bizKey")
    label: str
    field_id: str = Field(alias="fieldId")
    type: str = "text"
    writable: bool = True


class WeaverFieldConfigResponse(BaseModel):
    workflow_id: str = Field(alias="workflowId")
    fields: list[WeaverFieldConfigItem] = Field(default_factory=list)
