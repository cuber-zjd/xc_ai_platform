export interface SapSystem {
  id: number;
  name: string;
  system_code: string;
  company_code?: string | null;
  environment: string;
  client: string;
  language: string;
  ashost?: string | null;
  mshost?: string | null;
  sysnr?: string | null;
  group?: string | null;
  user_env_key?: string | null;
  password_env_key?: string | null;
  max_rows: number;
  is_production: boolean;
  is_enabled: boolean;
  allow_web_search: boolean;
  allowed_tables?: string[] | null;
  allowed_objects?: string[] | null;
}

export interface KnowledgeBase {
  id: number;
  name: string;
  description?: string | null;
  collection_name: string;
}

export interface TimelineItem {
  id: string;
  title: string;
  status: 'pending' | 'success' | 'failed' | 'skipped';
  detail: string;
  toolName?: string;
}

export interface EvidenceItem {
  evidence_type: string;
  title: string;
  summary?: string | null;
  source_object?: string | null;
  location?: string | null;
  confidence?: number;
  content?: unknown;
}

export interface ToolResult {
  tool_name: string;
  status: string;
  summary: string;
  duration_ms: number;
  data?: unknown;
  evidence?: EvidenceItem[];
  error_message?: string | null;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  isStreaming?: boolean;
  timeline?: TimelineItem[];
}

export interface SapAssistantSession {
  id: number;
  title: string;
  sap_system_id?: number | null;
  knowledge_base_ids?: number[] | null;
  status: string;
  summary?: string | null;
  create_time: string;
  update_time: string;
}

export interface SapAssistantStoredMessage {
  id: number;
  session_id: number;
  role: 'user' | 'assistant' | 'tool';
  content: string;
  message_metadata?: {
    timeline?: TimelineItem[];
    flowchart?: string;
  } | null;
  create_time: string;
}
