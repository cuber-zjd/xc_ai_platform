from pydantic import BaseModel


class InsightSelectorOption(BaseModel):
    id: int
    label: str
    value: str
    type: str
    subtitle: str | None = None
    employee_id: str | None = None
    code: str | None = None
    parent_id: str | None = None
