from typing import Optional, List, Dict
from datetime import datetime
from enum import Enum
from sqlmodel import Field, Relationship, SQLModel
from sqlalchemy.dialects.postgresql import JSONB

from app.models.base import BaseDBModel

# --- Enums ---


class ContractStatusEnum(str, Enum):
    UPLOADING = "uploading"
    ANALYZING = "analyzing"
    ANALYSIS_COMPLETED = "analysis_completed"  # Ready for review
    ANALYSIS_FAILED = "analysis_failed"


class TrafficLightEnum(str, Enum):
    GREEN = "green"  # Safe
    YELLOW = "yellow"  # Warnings
    RED = "red"  # Critical Risks
    NONE = "none"  # Not analyzed yet


class RiskLevelEnum(str, Enum):
    CRITICAL = "critical"  # Red flag
    WARNING = "warning"  # Yellow flag
    INFO = "info"  # Suggestion


# --- Models ---


class Contract(BaseDBModel, table=True):
    """
    Core Contract Metadata
    """

    __tablename__ = "contract_info"

    title: str = Field(index=True)
    serial_number: Optional[str] = Field(default=None, index=True)  # Contract No.

    file_path: str = Field(description="MinIO object path")
    file_version: str = Field(default="v1")

    contract_type: str = Field(description="To match with Rules groups")
    initiator_id: Optional[int] = Field(
        default=None, description="User ID who uploaded"
    )

    # Analysis Status
    status: ContractStatusEnum = Field(default=ContractStatusEnum.UPLOADING)
    traffic_light: TrafficLightEnum = Field(default=TrafficLightEnum.NONE)

    # AI Summary (JSON)
    analysis_summary: Optional[Dict] = Field(default=None, sa_type=JSONB)

    # Relationships
    audit_logs: List["ContractAuditLog"] = Relationship(back_populates="contract")


class ContractRule(BaseDBModel, table=True):
    """
    Configurable Rules for 'Rule-based Audit'
    """

    __tablename__ = "contract_rule"

    rule_name: str
    description: Optional[str] = None

    category: str = Field(
        index=True, description="Contract Type this rule applies to, or 'GLOBAL'"
    )

    severity: RiskLevelEnum = Field(default=RiskLevelEnum.WARNING)

    # The actual instruction for the AI or Code
    # Can be a prompt snippet or a conditional logic description
    rule_definition: str = Field(description="Prompt instruction or logical condition")

    is_active: bool = Field(default=True)


class ContractAuditLog(BaseDBModel, table=True):
    """
    Detailed findings from the AI Analysis
    """

    __tablename__ = "contract_audit_log"

    contract_id: int = Field(foreign_key="contract_info.id")
    rule_id: Optional[int] = Field(
        default=None, foreign_key="contract_rule.id", nullable=True
    )

    risk_level: RiskLevelEnum = Field(default=RiskLevelEnum.INFO)

    finding_summary: str = Field(description="Short title of the finding")
    finding_detail: str = Field(description="Full explanation")
    
    # Location for Sidecar/OnlyOffice
    quote_text: Optional[str] = Field(default=None, description="Original text quoted")
    page_num: Optional[int] = Field(default=None)
    location_index: Optional[Dict] = Field(
        default=None, sa_type=JSONB, description="{'start': 100, 'end': 200} or xpath"
    )

    # Handling
    is_accepted: bool = Field(
        default=False, description="Whether legal team accepted this risk"
    )
    acceptance_reason: Optional[str] = Field(default=None)

    # Relationships
    contract: Contract = Relationship(back_populates="audit_logs")


class PolicyDocument(BaseDBModel, table=True):
    """
    Internal Policy Documents for RAG (Retrieval)
    """

    __tablename__ = "policy_document"

    title: str
    file_path: str = Field(description="MinIO object path")

    doc_type: str = Field(default="general")

    # Milvus Collection Info
    collection_name: str = Field(default="policy_docs")
    is_indexed: bool = Field(default=False)
