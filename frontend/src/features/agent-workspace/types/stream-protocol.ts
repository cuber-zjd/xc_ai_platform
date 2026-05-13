/**
 * 智能体工作台 SSE 流式数据协议定义
 */

export const ChunkType = {
  // 左侧打字机专属
  TEXT_DELTA: 'text_delta',         // AI 对话流式文本增量
  TEXT_DONE: 'text_done',           // 文本生成结束 

  // 右侧动态展示专属
  THOUGHT_NODE: 'thought_node',     // 链式思考节点更新 (如：开始思考、工具调用)
  HUMAN_INTERACT: 'human_interact', // 触发人类介入表单结构
  TOOL_OUTPUT: 'tool_output',       // 复杂工具/外部动作可视化
  EVIDENCE: 'evidence',             // 证据链片段
  FLOWCHART: 'flowchart',           // 流程图/Mermaid
  SYSTEM_CONTEXT: 'system_context', // 当前系统上下文
  TOOL_STATUS: 'tool_status',       // 工具状态更新
  ERROR: 'error'                    // 异常终止
} as const;

export type ChunkType = (typeof ChunkType)[keyof typeof ChunkType];

export interface TextDeltaData {
  content: string;
}

export interface ThoughtNodeData {
  nodeId: string;
  act: 'planning' | 'calling_tool' | 'tool_result' | 'summarizing';
  status: 'pending' | 'success' | 'failed';
  toolName?: string;
  detailStr?: string;
}

export interface HumanInteractData {
  requestId: string;
  promptText: string;
  actionType: 'approve' | 'modify' | 'reject';
  defaultPayload?: any;
}

export interface ToolOutputData {
  toolName: string;
  displayType: 'table' | 'chart' | 'json' | 'html';
  content: any;
}

export interface EvidenceData {
  evidence_type: string;
  title: string;
  summary?: string | null;
  source_object?: string | null;
  location?: string | null;
  confidence?: number;
  content?: any;
}

export interface FlowchartData {
  code: string;
}

export interface SystemContextData {
  id?: number;
  name?: string;
  systemCode?: string;
  client?: string;
  environment?: string;
  companyCode?: string | null;
  isProduction?: boolean;
}

export interface StreamChunk<T = any> {
  id: string;
  type: ChunkType;
  data: T;
  timestamp: number;
}

export type WorkspaceType = 'thought' | 'human' | 'tool' | 'idle';
