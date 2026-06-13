from pydantic import BaseModel, Field


class InsightHealthRead(BaseModel):
    module: str = Field(default="insight")
    status: str = Field(default="ready")
    version: str = Field(default="0.1.0")
    enabled_capabilities: list[str] = Field(default_factory=list)
