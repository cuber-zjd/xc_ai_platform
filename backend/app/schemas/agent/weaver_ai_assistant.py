from typing import Any, Literal

from pydantic import BaseModel, Field


class WeaverFieldContext(BaseModel):
    label: str = ""
    field_id: str = Field(alias="fieldId")
    type: str = "text"
    writable: bool = True
    value: Any = None
    display_value: Any = Field(default=None, alias="displayValue")
    options: list["WeaverFieldOptionItem"] = Field(default_factory=list)
    browser_type: str | None = Field(default=None, alias="browserType")
    required: bool | None = None
    visible: bool | None = None
    readonly_reason: str | None = Field(default=None, alias="readonlyReason")


class WeaverFormContext(BaseModel):
    env: str | None = None
    base_info: dict[str, Any] = Field(default_factory=dict, alias="baseInfo")
    url: str = ""
    fields: dict[str, WeaverFieldContext] = Field(default_factory=dict)


class WeaverAssistantChatRequest(BaseModel):
    message: str
    context: WeaverFormContext = Field(default_factory=WeaverFormContext)
    history: list["WeaverChatHistoryItem"] = Field(default_factory=list)


class WeaverChatHistoryItem(BaseModel):
    role: Literal["assistant", "user"]
    content: str


class WeaverAssistantAction(BaseModel):
    type: Literal["set_field", "add_detail_row", "show_message"]
    field: str | None = None
    value: Any = None
    display_value: Any = Field(default=None, alias="displayValue")
    special_obj: list[dict[str, Any]] | None = Field(default=None, alias="specialObj")
    detail: str | None = None
    values: dict[str, Any] | None = None
    message: str | None = None
    label: str | None = None


class WeaverAssistantChatResponse(BaseModel):
    message: str
    actions: list[WeaverAssistantAction] = Field(default_factory=list)


class WeaverFieldOptionItem(BaseModel):
    value: str
    label: str
    disabled: bool = False


class WeaverFieldConfigItem(BaseModel):
    biz_key: str = Field(alias="bizKey")
    label: str
    field_id: str = Field(alias="fieldId")
    type: str = "text"
    writable: bool = True
    options: list[WeaverFieldOptionItem] = Field(default_factory=list)
    browser_type: str | None = Field(default=None, alias="browserType")
    field_name: str | None = Field(default=None, alias="fieldName")
    field_db_type: str | None = Field(default=None, alias="fieldDbType")
    field_html_type: str | None = Field(default=None, alias="fieldHtmlType")
    field_type: str | None = Field(default=None, alias="fieldType")
    view_type: int | None = Field(default=None, alias="viewType")
    detail_table: str | None = Field(default=None, alias="detailTable")


class WeaverNodeConfigItem(BaseModel):
    node_id: str = Field(alias="nodeId")
    node_name: str = Field(alias="nodeName")
    node_type: str | None = Field(default=None, alias="nodeType")


class WeaverFieldConfigResponse(BaseModel):
    workflow_id: str = Field(alias="workflowId")
    env: str | None = None
    workflow_name: str | None = Field(default=None, alias="workflowName")
    form_id: str | None = Field(default=None, alias="formId")
    bill_id: str | None = Field(default=None, alias="billId")
    main_table: str | None = Field(default=None, alias="mainTable")
    detail_key_field: str | None = Field(default=None, alias="detailKeyField")
    fields: list[WeaverFieldConfigItem] = Field(default_factory=list)
    nodes: list[WeaverNodeConfigItem] = Field(default_factory=list)


class WeaverWorkflowRuleBase(BaseModel):
    env: str = "default"
    workflow_id: str = Field(alias="workflowId")
    workflow_name: str | None = Field(default=None, alias="workflowName")
    rule_title: str = Field(alias="ruleTitle")
    rule_content: str = Field(alias="ruleContent")
    skill_config: dict[str, Any] | None = Field(default=None, alias="skillConfig")
    enabled: bool = True
    priority: int = 100


class WeaverWorkflowRuleCreate(WeaverWorkflowRuleBase):
    pass


class WeaverWorkflowRuleUpdate(BaseModel):
    workflow_name: str | None = Field(default=None, alias="workflowName")
    rule_title: str | None = Field(default=None, alias="ruleTitle")
    rule_content: str | None = Field(default=None, alias="ruleContent")
    skill_config: dict[str, Any] | None = Field(default=None, alias="skillConfig")
    enabled: bool | None = None
    priority: int | None = None


class WeaverWorkflowRuleRead(WeaverWorkflowRuleBase):
    id: int
    status: str = "active"


class WeaverReviewRuleBase(BaseModel):
    env: str = "default"
    workflow_id: str = Field(alias="workflowId")
    workflow_name: str | None = Field(default=None, alias="workflowName")
    node_id: str | None = Field(default=None, alias="nodeId")
    node_name: str | None = Field(default=None, alias="nodeName")
    reviewer_user_id: str | None = Field(default=None, alias="reviewerUserId")
    reviewer_name: str | None = Field(default=None, alias="reviewerName")
    rule_title: str = Field(alias="ruleTitle")
    rule_content: str = Field(alias="ruleContent")
    tool_config: dict[str, Any] | None = Field(default=None, alias="toolConfig")
    auto_review_mode: Literal["suggestion", "assist", "auto"] = Field(default="suggestion", alias="autoReviewMode")
    enabled: bool = True
    priority: int = 100


class WeaverReviewRuleCreate(WeaverReviewRuleBase):
    pass


class WeaverReviewRuleUpdate(BaseModel):
    workflow_name: str | None = Field(default=None, alias="workflowName")
    node_id: str | None = Field(default=None, alias="nodeId")
    node_name: str | None = Field(default=None, alias="nodeName")
    reviewer_user_id: str | None = Field(default=None, alias="reviewerUserId")
    reviewer_name: str | None = Field(default=None, alias="reviewerName")
    rule_title: str | None = Field(default=None, alias="ruleTitle")
    rule_content: str | None = Field(default=None, alias="ruleContent")
    tool_config: dict[str, Any] | None = Field(default=None, alias="toolConfig")
    auto_review_mode: Literal["suggestion", "assist", "auto"] | None = Field(default=None, alias="autoReviewMode")
    enabled: bool | None = None
    priority: int | None = None


class WeaverReviewRuleRead(WeaverReviewRuleBase):
    id: int
    status: str = "active"


class WeaverReviewActor(BaseModel):
    user_id: str | None = Field(default=None, alias="userId")
    user_name: str | None = Field(default=None, alias="userName")
    department_id: str | None = Field(default=None, alias="departmentId")
    department_name: str | None = Field(default=None, alias="departmentName")


class WeaverReviewRequest(BaseModel):
    context: WeaverFormContext = Field(default_factory=WeaverFormContext)
    trigger_type: Literal["submit", "action", "open", "manual"] = Field(default="manual", alias="triggerType")
    operation: str | None = None
    current_node_id: str | None = Field(default=None, alias="currentNodeId")
    current_node_name: str | None = Field(default=None, alias="currentNodeName")
    submitter: WeaverReviewActor | None = None
    reviewer: WeaverReviewActor | None = None
    comment: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class WeaverReviewCheckItem(BaseModel):
    name: str
    status: Literal["pass", "warning", "fail", "unknown"] = "unknown"
    detail: str = ""


class WeaverReviewResult(BaseModel):
    summary: str
    risk_level: Literal["low", "medium", "high", "blocked"] = Field(alias="riskLevel")
    decision_suggestion: Literal["approve", "return", "reject", "supplement", "manual_review"] = Field(alias="decisionSuggestion")
    suggested_opinion: str | None = Field(default=None, alias="suggestedOpinion")
    checks: list[WeaverReviewCheckItem] = Field(default_factory=list)
    missing_materials: list[str] = Field(default_factory=list, alias="missingMaterials")
    concerns: list[str] = Field(default_factory=list)
    confidence: float | None = None
    can_auto_approve: bool = Field(default=False, alias="canAutoApprove")


class WeaverReviewRecordRead(BaseModel):
    id: int
    env: str = "default"
    workflow_id: str = Field(alias="workflowId")
    workflow_name: str | None = Field(default=None, alias="workflowName")
    request_id: str | None = Field(default=None, alias="requestId")
    node_id: str | None = Field(default=None, alias="nodeId")
    node_name: str | None = Field(default=None, alias="nodeName")
    trigger_type: str = Field(alias="triggerType")
    submitter_user_id: str | None = Field(default=None, alias="submitterUserId")
    submitter_name: str | None = Field(default=None, alias="submitterName")
    reviewer_user_id: str | None = Field(default=None, alias="reviewerUserId")
    reviewer_name: str | None = Field(default=None, alias="reviewerName")
    risk_level: str = Field(alias="riskLevel")
    decision_suggestion: str = Field(alias="decisionSuggestion")
    summary: str
    suggested_opinion: str | None = Field(default=None, alias="suggestedOpinion")
    confidence: float | None = None
    can_auto_approve: bool = Field(alias="canAutoApprove")
    review_result: dict[str, Any] = Field(default_factory=dict, alias="reviewResult")
    status: str = "completed"


class WeaverReviewResponse(BaseModel):
    record: WeaverReviewRecordRead
    result: WeaverReviewResult
    matched_rules: list[WeaverReviewRuleRead] = Field(default_factory=list, alias="matchedRules")
