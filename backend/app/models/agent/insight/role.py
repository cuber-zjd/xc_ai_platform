from sqlmodel import Field

from app.models.base import BaseDBModel


class InsightRole(BaseDBModel, table=True):
    """市场洞察专用业务角色。"""

    __tablename__ = "insight_role"

    role_code: str = Field(index=True, unique=True, max_length=80)
    role_name: str = Field(index=True, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    sort_no: int = Field(default=0, index=True)
    status: str = Field(default="active", index=True, max_length=20)


class InsightRoleMember(BaseDBModel, table=True):
    """市场洞察角色成员。"""

    __tablename__ = "insight_role_member"

    role_id: int = Field(foreign_key="insight_role.id", index=True)
    user_id: int = Field(foreign_key="sys_user.id", index=True)
    status: str = Field(default="active", index=True, max_length=20)
