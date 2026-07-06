from pydantic import BaseModel, Field

from app.schemas.agent.insight.common import InsightBaseRead


class InsightRoleCreate(BaseModel):
    role_code: str = Field(..., min_length=1, max_length=80)
    role_name: str = Field(..., min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    sort_no: int = 0
    status: str = Field(default="active", max_length=20)


class InsightRoleUpdate(BaseModel):
    role_code: str | None = Field(default=None, min_length=1, max_length=80)
    role_name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    sort_no: int | None = None
    status: str | None = Field(default=None, max_length=20)


class InsightRoleRead(InsightBaseRead):
    role_code: str
    role_name: str
    description: str | None = None
    sort_no: int
    status: str
    member_count: int = 0


class InsightRoleMemberRead(InsightBaseRead):
    role_id: int
    user_id: int
    user_name: str | None = None
    username: str | None = None
    employee_id: str | None = None
    dept_id: str | None = None
    job_title: str | None = None
    status: str


class InsightRoleMemberUpsert(BaseModel):
    user_ids: list[int] = Field(..., min_length=1, max_length=500)
