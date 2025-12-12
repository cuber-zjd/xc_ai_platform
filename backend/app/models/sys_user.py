from datetime import datetime, date
from typing import Optional
from sqlmodel import SQLModel, Field

class SysUserBase(SQLModel):
    sync_id: Optional[str] = Field(default=None, index=True, description="Original ID from HR system (a0188)")
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
    job_point: Optional[str] = Field(default=None, description="Job Point (gangweixindian)")
    
    status: int = Field(default=1, description="Status: 1=Normal, 0=Deleted")
    comment: Optional[str] = Field(default=None, description="Remarks")

class SysUser(SysUserBase, table=True):
    __tablename__ = "sys_user"
    
    id: int | None = Field(default=None, primary_key=True)
    create_time: datetime = Field(default_factory=datetime.now)
    update_time: datetime = Field(default_factory=datetime.now)
    create_by: Optional[str] = Field(default=None)
    update_by: Optional[str] = Field(default=None)
