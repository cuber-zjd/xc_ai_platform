from typing import Optional, List, Dict
from datetime import datetime
from sqlmodel import SQLModel 
from app.models.contract.contract_model import ContractStatusEnum, TrafficLightEnum, RiskLevelEnum

class ContractAuditLogRead(SQLModel):
    id: int
    risk_level: RiskLevelEnum
    finding_summary: str
    finding_detail: str
    quote_text: Optional[str] = None
    page_num: Optional[int] = None
    is_accepted: bool = False
    
class ContractRead(SQLModel):
    id: int
    title: str
    serial_number: Optional[str] = None
    file_version: str
    contract_type: str
    status: ContractStatusEnum
    traffic_light: TrafficLightEnum
    create_time: datetime
    initiator_id: Optional[int] = None
    
    # Optional URL field (presigned)
    file_url: Optional[str] = None

class ContractDetailRead(ContractRead):
    analysis_summary: Optional[Dict] = None
    audit_logs: List[ContractAuditLogRead] = []

class ContractCreate(SQLModel):
    title: str
    contract_type: str = "General"
    initiator_id: int

class ContractUpdate(SQLModel):
    title: Optional[str] = None
    status: Optional[ContractStatusEnum] = None
    traffic_light: Optional[TrafficLightEnum] = None
    analysis_summary: Optional[Dict] = None
