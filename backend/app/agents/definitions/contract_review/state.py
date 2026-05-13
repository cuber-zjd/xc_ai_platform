from typing import TypedDict, List, Dict, Optional
from pydantic import BaseModel

class AuditFinding(BaseModel):
    summary: str
    detail: str
    risk_level: str # critical, warning, info
    quote: Optional[str] = None
    page: Optional[int] = None

class ReviewState(TypedDict):
    contract_id: int
    file_path: str
    text_content: str
    contract_type: str
    
    # Intermediate results
    rule_findings: List[AuditFinding]
    llm_findings: List[AuditFinding]
    
    # Final Output
    traffic_light: str
    analysis_summary: Dict
