export interface WeaverFieldContext {
  label: string;
  fieldId: string;
  type?: string;
  writable?: boolean;
  value?: unknown;
}

export interface WeaverFormContext {
  baseInfo?: Record<string, unknown>;
  url?: string;
  fields?: Record<string, WeaverFieldContext>;
}

export interface WeaverAssistantAction {
  type: "set_field" | "add_detail_row" | "show_message";
  field?: string;
  value?: unknown;
  detail?: string;
  values?: Record<string, unknown>;
  message?: string;
  label?: string;
}

export interface WeaverAssistantChatResponse {
  message: string;
  actions: WeaverAssistantAction[];
}

export interface WeaverMessage {
  id: string;
  role: "assistant" | "user";
  content: string;
  actions?: WeaverAssistantAction[];
}
