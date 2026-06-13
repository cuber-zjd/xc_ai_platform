from pydantic import BaseModel


class CompanyOptionRead(BaseModel):
    id: int
    name: str
    code: str | None = None
    sync_id: str | None = None
    parent_id: str | None = None
