from datetime import datetime

from pydantic import BaseModel, Field


class InsightSettingsStatusItem(BaseModel):
    key: str
    name: str
    status: str = Field(pattern="^(ok|warning|disabled)$")
    description: str
    details: list[str] = Field(default_factory=list)


class InsightSettingsStatusSection(BaseModel):
    key: str
    name: str
    description: str
    items: list[InsightSettingsStatusItem] = Field(default_factory=list)


class InsightSettingsStatusRead(BaseModel):
    generated_at: datetime
    readonly: bool = True
    sections: list[InsightSettingsStatusSection] = Field(default_factory=list)
