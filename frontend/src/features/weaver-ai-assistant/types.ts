export interface WeaverFieldContext {
  label: string;
  fieldId: string;
  type?: string;
  writable?: boolean;
  value?: unknown;
  displayValue?: unknown;
  options?: WeaverFieldOptionItem[];
  browserType?: string;
  required?: boolean;
  visible?: boolean;
  readonlyReason?: string;
}

export interface WeaverFormContext {
  env?: string;
  baseInfo?: Record<string, unknown>;
  url?: string;
  fields?: Record<string, WeaverFieldContext>;
}

export interface WeaverAssistantAction {
  type: "set_field" | "add_detail_row" | "show_message";
  field?: string;
  value?: unknown;
  displayValue?: unknown;
  specialObj?: Array<{ id: string; name: string }>;
  detail?: string;
  values?: Record<string, unknown>;
  message?: string;
  label?: string;
}

export interface WeaverAssistantChatResponse {
  message: string;
  actions: WeaverAssistantAction[];
}

export interface WeaverChatHistoryItem {
  role: "assistant" | "user";
  content: string;
}

export interface WeaverFieldConfigItem {
  bizKey: string;
  label: string;
  fieldId: string;
  type?: string;
  writable?: boolean;
  options?: WeaverFieldOptionItem[];
  browserType?: string;
  fieldType?: string;
}

export interface WeaverFieldOptionItem {
  value: string;
  label: string;
  disabled?: boolean;
}

export interface WeaverFieldConfigResponse {
  workflowId: string;
  env?: string;
  workflowName?: string;
  formId?: string;
  billId?: string;
  mainTable?: string;
  fields: WeaverFieldConfigItem[];
}

export interface WeaverMessage {
  id: string;
  role: "assistant" | "user";
  content: string;
  actions?: WeaverAssistantAction[];
}

export interface WeaverWorkflowRule {
  id: number;
  env: string;
  workflowId: string;
  workflowName?: string | null;
  ruleTitle: string;
  ruleContent: string;
  skillConfig?: Record<string, unknown> | null;
  enabled: boolean;
  priority: number;
  status: string;
}

export interface WeaverWorkflowRulePayload {
  env: string;
  workflowId: string;
  workflowName?: string | null;
  ruleTitle: string;
  ruleContent: string;
  skillConfig?: Record<string, unknown> | null;
  enabled: boolean;
  priority: number;
}

export interface WeaverReviewRule {
  id: number;
  env: string;
  workflowId: string;
  workflowName?: string | null;
  nodeId?: string | null;
  nodeName?: string | null;
  reviewerUserId?: string | null;
  reviewerName?: string | null;
  ruleTitle: string;
  ruleContent: string;
  toolConfig?: Record<string, unknown> | null;
  autoReviewMode: "suggestion" | "assist" | "auto";
  enabled: boolean;
  priority: number;
  status: string;
}

export interface WeaverReviewRulePayload {
  env: string;
  workflowId: string;
  workflowName?: string | null;
  nodeId?: string | null;
  nodeName?: string | null;
  reviewerUserId?: string | null;
  reviewerName?: string | null;
  ruleTitle: string;
  ruleContent: string;
  toolConfig?: Record<string, unknown> | null;
  autoReviewMode: "suggestion" | "assist" | "auto";
  enabled: boolean;
  priority: number;
}

export interface WeaverReviewActor {
  userId?: string | null;
  userName?: string | null;
  departmentId?: string | null;
  departmentName?: string | null;
}

export interface WeaverReviewRequest {
  context: WeaverFormContext;
  triggerType: "submit" | "action" | "open" | "manual";
  operation?: string | null;
  currentNodeId?: string | null;
  currentNodeName?: string | null;
  submitter?: WeaverReviewActor | null;
  reviewer?: WeaverReviewActor | null;
  comment?: string | null;
  extra?: Record<string, unknown>;
}

export interface WeaverReviewCheckItem {
  name: string;
  status: "pass" | "warning" | "fail" | "unknown";
  detail: string;
}

export interface WeaverReviewResult {
  summary: string;
  riskLevel: "low" | "medium" | "high" | "blocked";
  decisionSuggestion: "approve" | "return" | "reject" | "supplement" | "manual_review";
  suggestedOpinion?: string | null;
  checks: WeaverReviewCheckItem[];
  missingMaterials: string[];
  concerns: string[];
  confidence?: number | null;
  canAutoApprove: boolean;
}

export interface WeaverReviewRecord {
  id: number;
  env: string;
  workflowId: string;
  workflowName?: string | null;
  requestId?: string | null;
  nodeId?: string | null;
  nodeName?: string | null;
  triggerType: string;
  submitterUserId?: string | null;
  submitterName?: string | null;
  reviewerUserId?: string | null;
  reviewerName?: string | null;
  riskLevel: string;
  decisionSuggestion: string;
  summary: string;
  suggestedOpinion?: string | null;
  confidence?: number | null;
  canAutoApprove: boolean;
  reviewResult: Partial<WeaverReviewResult> & Record<string, unknown>;
  status: string;
}

export interface WeaverReviewResponse {
  record: WeaverReviewRecord;
  result: WeaverReviewResult;
  matchedRules: WeaverReviewRule[];
}
