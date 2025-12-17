from typing import Optional
from sqlmodel import SQLModel, Field
from app.models.base import BaseDBModel

class SysUserBase(SQLModel):
    sync_id: Optional[str] = Field(default=None, index=True, description="Original ID (a0188)")
    username: str = Field(index=True, unique=True, description="Login name (a0190)")
    full_name: str = Field(index=True, description="Real name (a0101)")
    gender: Optional[str] = Field(default=None, description="Gender (a0107)")
    ethnicity: Optional[str] = Field(default=None, description="Ethnicity (a0121)")
    id_card: Optional[str] = Field(default=None, index=True, description="ID Card (a0177)")
    mobile: Optional[str] = Field(default=None, index=True, description="Mobile (a01274)")
    education: Optional[str] = Field(default=None, description="Education (a01085)")
    
    # HR/Org Relations
    dept_id: Optional[str] = Field(default=None, index=True, description="Department ID (deptid)")
    job_title: Optional[str] = Field(default=None, description="Job Title/Post (j01_e0101)")
    supervisor_id: Optional[str] = Field(default=None, description="Direct Supervisor Sync ID (user_pre)")
    
    # Dates
    hire_date: Optional[str] = Field(default=None, description="Hire Date (a0144)")
    contract_start_date: Optional[str] = Field(default=None, description="Contract Start (a01107)")
    contract_end_date: Optional[str] = Field(default=None, description="Contract End (a01108)")
    birth_date: Optional[str] = Field(default=None, description="Birth Date (a0111)")
    
    # Employment Details
    level: Optional[str] = Field(default=None, description="Level (a01003)")
    employee_id: Optional[str] = Field(default=None, description="Employee ID/Jinghao (a0190)")
    travel_level: Optional[str] = Field(default=None, description="Travel Level (a01004)")
    job_order: Optional[str] = Field(default=None, description="Order (a01004order)")
    
    # Status
    status: int = Field(default=1, description="Employment Status Code (0-7)")
    status_desc: Optional[str] = Field(default=None, description="Employment Status Desc (Formal, Trial, etc.)")


class SysUser(BaseDBModel, SysUserBase, table=True):
    __tablename__ = "sys_user"
    # id, create_time, is_deleted etc inherited from BaseDBModel
