from typing import Any

from sqlalchemy import UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field

from app.models.base import BaseDBModel


class WeaverAiWorkflowRule(BaseDBModel, table=True):
    """泛微流程 AI 填报规则/技能配置。"""

    __tablename__ = "weaver_ai_workflow_rule"

    env: str = Field(default="default", index=True, max_length=80, description="泛微环境 key")
    workflow_id: str = Field(index=True, max_length=80, description="泛微 workflowid")
    workflow_name: str | None = Field(default=None, max_length=300, description="流程名称快照")
    rule_title: str = Field(max_length=200, description="规则标题")
    rule_content: str = Field(description="流程特殊填写要求或提示词")
    skill_config: dict[str, Any] | None = Field(default=None, sa_type=JSONB, description="技能/工具说明配置")
    enabled: bool = Field(default=True, index=True, description="是否启用")
    priority: int = Field(default=100, index=True, description="优先级，数字越小越靠前")
    status: str = Field(default="active", index=True, max_length=30)


class WeaverAiReviewRule(BaseDBModel, table=True):
    """泛微流程 AI 智审规则。"""

    __tablename__ = "weaver_ai_review_rule"

    env: str = Field(default="default", index=True, max_length=80, description="泛微环境 key")
    workflow_id: str = Field(index=True, max_length=80, description="泛微 workflowid")
    workflow_name: str | None = Field(default=None, max_length=300, description="流程名称快照")
    node_id: str | None = Field(default=None, index=True, max_length=80, description="泛微节点 ID，空表示流程通用")
    node_name: str | None = Field(default=None, max_length=200, description="节点名称快照")
    reviewer_user_id: str | None = Field(default=None, index=True, max_length=80, description="审批人用户 ID，空表示节点通用")
    reviewer_name: str | None = Field(default=None, max_length=120, description="审批人名称快照")
    rule_title: str = Field(max_length=200, description="智审规则标题")
    rule_content: str = Field(description="智审规则、审批口径或风险检查要求")
    tool_config: dict[str, Any] | None = Field(default=None, sa_type=JSONB, description="工具/知识库/外部查询说明")
    general_check_enabled: bool = Field(default=False, description="是否允许超出已配置规则执行通用检查")
    auto_review_mode: str = Field(default="suggestion", index=True, max_length=30, description="suggestion/assist/auto")
    enabled: bool = Field(default=True, index=True, description="是否启用")
    priority: int = Field(default=100, index=True, description="优先级，数字越小越靠前")
    status: str = Field(default="active", index=True, max_length=30)


class WeaverAiReviewNodeConfig(BaseDBModel, table=True):
    """泛微流程节点的 AI 智审启用范围。"""

    __tablename__ = "weaver_ai_review_node_config"
    __table_args__ = (
        UniqueConstraint("env", "workflow_id", "node_id", name="uq_weaver_ai_review_node_config_scope"),
    )

    env: str = Field(default="default", index=True, max_length=80, description="泛微环境 key")
    workflow_id: str = Field(index=True, max_length=80, description="泛微 workflowid")
    workflow_name: str | None = Field(default=None, max_length=300, description="流程名称快照")
    node_id: str = Field(index=True, max_length=80, description="泛微节点 ID")
    node_name: str | None = Field(default=None, max_length=200, description="节点名称快照")
    enabled: bool = Field(default=False, index=True, description="是否启用当前节点智审")
    show_entry: bool = Field(default=True, description="是否在审批页显示智审入口")
    automatic_review_enabled: bool = Field(default=False, index=True, description="是否允许提交或 Action 自动预审")
    status: str = Field(default="active", index=True, max_length=30)


class WeaverAiReviewRecord(BaseDBModel, table=True):
    """泛微流程 AI 智审记录。"""

    __tablename__ = "weaver_ai_review_record"

    env: str = Field(default="default", index=True, max_length=80, description="泛微环境 key")
    workflow_id: str = Field(index=True, max_length=80, description="泛微 workflowid")
    workflow_name: str | None = Field(default=None, max_length=300, description="流程名称快照")
    request_id: str | None = Field(default=None, index=True, max_length=80, description="泛微 requestid")
    node_id: str | None = Field(default=None, index=True, max_length=80, description="当前节点 ID")
    node_name: str | None = Field(default=None, max_length=200, description="当前节点名称")
    trigger_type: str = Field(default="manual", index=True, max_length=40, description="submit/action/open/manual")
    submitter_user_id: str | None = Field(default=None, index=True, max_length=80, description="提交人 ID")
    submitter_name: str | None = Field(default=None, max_length=120, description="提交人名称")
    reviewer_user_id: str | None = Field(default=None, index=True, max_length=80, description="审批人 ID")
    reviewer_name: str | None = Field(default=None, max_length=120, description="审批人名称")
    risk_level: str = Field(default="medium", index=True, max_length=30, description="low/medium/high/blocked")
    decision_suggestion: str = Field(default="manual_review", index=True, max_length=40, description="approve/return/reject/supplement/manual_review")
    summary: str = Field(default="", description="智审摘要")
    suggested_opinion: str | None = Field(default=None, description="建议审批意见")
    confidence: float | None = Field(default=None, description="模型置信度")
    can_auto_approve: bool = Field(default=False, index=True, description="是否满足替审条件")
    rule_snapshot: list[dict[str, Any]] | None = Field(default=None, sa_type=JSONB, description="命中的规则快照")
    form_snapshot: dict[str, Any] | None = Field(default=None, sa_type=JSONB, description="表单上下文快照")
    review_result: dict[str, Any] | None = Field(default=None, sa_type=JSONB, description="完整智审结果")
    status: str = Field(default="completed", index=True, max_length=30)


class WeaverAiReviewTestRecord(BaseDBModel, table=True):
    """泛微流程 AI 测试智审记录，与正式智审记录物理隔离。"""

    __tablename__ = "weaver_ai_review_test_record"

    env: str = Field(default="default", index=True, max_length=80, description="泛微环境 key")
    workflow_id: str = Field(index=True, max_length=80, description="配置页所属 workflowid")
    workflow_name: str | None = Field(default=None, max_length=300, description="流程名称快照")
    request_id: str = Field(index=True, max_length=80, description="用于测试的泛微 requestid")
    source_node_id: str | None = Field(default=None, index=True, max_length=80, description="请求当前真实节点 ID")
    source_node_name: str | None = Field(default=None, max_length=200, description="请求当前真实节点名称")
    risk_level: str = Field(default="medium", index=True, max_length=30)
    decision_suggestion: str = Field(default="manual_review", index=True, max_length=40)
    summary: str = Field(default="")
    suggested_opinion: str | None = Field(default=None)
    confidence: float | None = Field(default=None)
    can_auto_approve: bool = Field(default=False, description="仅记录模型判断，测试模式永不触发审批")
    rule_snapshot: list[dict[str, Any]] | None = Field(default=None, sa_type=JSONB)
    form_snapshot: dict[str, Any] | None = Field(default=None, sa_type=JSONB)
    review_result: dict[str, Any] | None = Field(default=None, sa_type=JSONB)
    status: str = Field(default="completed", index=True, max_length=30)


class WeaverAiReviewScanTask(BaseDBModel, table=True):
    """泛微待办节点自动预审扫描任务。"""

    __tablename__ = "weaver_ai_review_scan_task"
    __table_args__ = (
        UniqueConstraint(
            "env",
            "workflow_id",
            "request_id",
            "node_id",
            "reviewer_user_id",
            "operator_id",
            name="uq_weaver_ai_review_scan_task_target",
        ),
    )

    env: str = Field(default="default", index=True, max_length=80)
    workflow_id: str = Field(index=True, max_length=80)
    workflow_name: str | None = Field(default=None, max_length=300)
    request_id: str = Field(index=True, max_length=80)
    request_name: str | None = Field(default=None, max_length=500)
    node_id: str = Field(index=True, max_length=80)
    node_name: str | None = Field(default=None, max_length=200)
    reviewer_user_id: str = Field(default="", index=True, max_length=80)
    reviewer_name: str | None = Field(default=None, max_length=120)
    operator_id: str = Field(index=True, max_length=80, description="workflow_currentoperator.id")
    received_at: str | None = Field(default=None, max_length=40)
    review_record_id: int | None = Field(default=None, index=True)
    attempts: int = Field(default=0)
    last_error: str | None = Field(default=None)
    status: str = Field(default="pending", index=True, max_length=30)
