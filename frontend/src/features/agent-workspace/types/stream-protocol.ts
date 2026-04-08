/**
 * 智能体工作台 SSE 流式数据协议定义
 */

export enum ChunkType {
  // 左侧打字机专属
  TEXT_DELTA = 'text_delta',         // AI 对话流式文本增量
  TEXT_DONE = 'text_done',           // 文本生成结束 

  // 右侧动态展示专属
  THOUGHT_NODE = 'thought_node',     // 链式思考节点更新 (如：开始思考、工具调用)
  HUMAN_INTERACT = 'human_interact', // 触发人类介入表单结构
  TOOL_OUTPUT = 'tool_output',       // 复杂工具/外部动作可视化
  ERROR = 'error'                    // 异常终止
}

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

export interface StreamChunk<T = any> {
  id: string;
  type: ChunkType;
  data: T;
  timestamp: number;
}

export type WorkspaceType = 'thought' | 'human' | 'tool' | 'idle';
