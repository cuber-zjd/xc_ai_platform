import type {
  WeaverAssistantChatResponse,
  WeaverChatHistoryItem,
  WeaverFieldConfigResponse,
  WeaverFormContext,
  WeaverReviewRecord,
  WeaverReviewRequest,
  WeaverReviewResponse,
  WeaverReviewRule,
  WeaverReviewRulePayload,
  WeaverWorkflowRule,
  WeaverWorkflowRulePayload,
} from "./types";

const apiBaseUrl = import.meta.env.VITE_API_URL || "/ai-api/v1";

interface ChatPayload {
  message: string;
  context: WeaverFormContext;
  history?: WeaverChatHistoryItem[];
}

interface StreamHandlers {
  onDelta?: (delta: string) => void;
  onActions?: (actions: WeaverAssistantChatResponse["actions"]) => void;
  onDone?: () => void;
}

interface Result<T> {
  code: number;
  msg: string;
  data: T;
}

export async function sendWeaverAssistantMessage(
  aiSign: string,
  payload: ChatPayload,
): Promise<WeaverAssistantChatResponse> {
  const safeAiSign = normalizeHeaderValue(aiSign, "ai_sign");
  const response = await fetch(`${apiBaseUrl}/weaver/ai-assistant/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "ai-sign": safeAiSign,
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    if (response.status === 401) {
      throw new Error("认证失败：请检查 ecode 里的 AI_SIGN 是否与后端 EXTERNAL_API_KEYS 一致，并确认后端已重启");
    }
    throw new Error(`接口请求失败：${response.status}`);
  }

  const result = (await response.json()) as Result<WeaverAssistantChatResponse>;
  if (result.code !== 200) {
    throw new Error(result.msg || "AI 助手处理失败");
  }
  return result.data;
}

export async function streamWeaverAssistantMessage(
  aiSign: string,
  payload: ChatPayload,
  handlers: StreamHandlers,
): Promise<void> {
  const safeAiSign = normalizeHeaderValue(aiSign, "ai_sign");
  const response = await fetch(`${apiBaseUrl}/weaver/ai-assistant/chat/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "ai-sign": safeAiSign,
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    if (response.status === 401) {
      throw new Error("认证失败：请检查 ecode 里的 AI_SIGN 是否与后端 EXTERNAL_API_KEYS 一致，并确认后端已重启");
    }
    throw new Error(`流式接口请求失败：${response.status}`);
  }
  if (!response.body) {
    throw new Error("当前浏览器不支持读取流式响应");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split(/\n\n/);
    buffer = parts.pop() || "";
    parts.forEach((part) => handleSseBlock(part, handlers));
  }

  buffer += decoder.decode();
  if (buffer.trim()) {
    handleSseBlock(buffer, handlers);
  }
}

export async function fetchWeaverFieldConfig(
  aiSign: string,
  workflowId: string,
  env?: string,
): Promise<WeaverFieldConfigResponse> {
  const safeAiSign = normalizeHeaderValue(aiSign, "ai_sign");
  const params = new URLSearchParams({ workflow_id: workflowId });
  if (env) params.set("env", env);

  const response = await fetch(`${apiBaseUrl}/weaver/ai-assistant/field-config?${params.toString()}`, {
    method: "GET",
    headers: {
      "ai-sign": safeAiSign,
    },
  });

  if (!response.ok) {
    if (response.status === 401) {
      throw new Error("认证失败：请检查 ecode 里的 AI_SIGN 是否与后端 EXTERNAL_API_KEYS 一致，并确认后端已重启");
    }
    throw new Error(`字段配置接口请求失败：${response.status}`);
  }

  const result = (await response.json()) as Result<WeaverFieldConfigResponse>;
  if (result.code !== 200) {
    throw new Error(result.msg || "字段配置加载失败");
  }
  return result.data;
}

export async function fetchWeaverWorkflowRules(
  aiSign: string,
  workflowId: string,
  env?: string,
): Promise<WeaverWorkflowRule[]> {
  const safeAiSign = normalizeHeaderValue(aiSign, "ai_sign");
  const params = new URLSearchParams({ workflow_id: workflowId });
  if (env) params.set("env", env);

  const response = await fetch(`${apiBaseUrl}/weaver/ai-assistant/workflow-rules?${params.toString()}`, {
    method: "GET",
    headers: {
      "ai-sign": safeAiSign,
    },
  });

  if (!response.ok) {
    throw new Error(`规则列表加载失败：${response.status}`);
  }

  const result = (await response.json()) as Result<WeaverWorkflowRule[]>;
  if (result.code !== 200) {
    throw new Error(result.msg || "规则列表加载失败");
  }
  return result.data || [];
}

export async function createWeaverWorkflowRule(
  aiSign: string,
  payload: WeaverWorkflowRulePayload,
): Promise<WeaverWorkflowRule> {
  return saveWeaverWorkflowRule(aiSign, "POST", `${apiBaseUrl}/weaver/ai-assistant/workflow-rules`, payload);
}

export async function updateWeaverWorkflowRule(
  aiSign: string,
  ruleId: number,
  payload: Partial<WeaverWorkflowRulePayload>,
): Promise<WeaverWorkflowRule> {
  return saveWeaverWorkflowRule(aiSign, "PUT", `${apiBaseUrl}/weaver/ai-assistant/workflow-rules/${ruleId}`, payload);
}

export async function deleteWeaverWorkflowRule(aiSign: string, ruleId: number): Promise<void> {
  const safeAiSign = normalizeHeaderValue(aiSign, "ai_sign");
  const response = await fetch(`${apiBaseUrl}/weaver/ai-assistant/workflow-rules/${ruleId}`, {
    method: "DELETE",
    headers: {
      "ai-sign": safeAiSign,
    },
  });
  if (!response.ok) {
    throw new Error(`规则删除失败：${response.status}`);
  }
}

export async function fetchWeaverReviewRules(
  aiSign: string,
  workflowId: string,
  options?: {
    env?: string;
    nodeId?: string;
    reviewerUserId?: string;
  },
): Promise<WeaverReviewRule[]> {
  const safeAiSign = normalizeHeaderValue(aiSign, "ai_sign");
  const params = new URLSearchParams({ workflow_id: workflowId });
  if (options?.env) params.set("env", options.env);
  if (options?.nodeId) params.set("node_id", options.nodeId);
  if (options?.reviewerUserId) params.set("reviewer_user_id", options.reviewerUserId);

  const response = await fetch(`${apiBaseUrl}/weaver/ai-assistant/review-rules?${params.toString()}`, {
    method: "GET",
    headers: {
      "ai-sign": safeAiSign,
    },
  });
  if (!response.ok) {
    throw new Error(`智审规则加载失败：${response.status}`);
  }
  const result = (await response.json()) as Result<WeaverReviewRule[]>;
  if (result.code !== 200) {
    throw new Error(result.msg || "智审规则加载失败");
  }
  return result.data || [];
}

export async function createWeaverReviewRule(
  aiSign: string,
  payload: WeaverReviewRulePayload,
): Promise<WeaverReviewRule> {
  return saveWeaverReviewRule(aiSign, "POST", `${apiBaseUrl}/weaver/ai-assistant/review-rules`, payload);
}

export async function updateWeaverReviewRule(
  aiSign: string,
  ruleId: number,
  payload: Partial<WeaverReviewRulePayload>,
): Promise<WeaverReviewRule> {
  return saveWeaverReviewRule(aiSign, "PUT", `${apiBaseUrl}/weaver/ai-assistant/review-rules/${ruleId}`, payload);
}

export async function deleteWeaverReviewRule(aiSign: string, ruleId: number): Promise<void> {
  const safeAiSign = normalizeHeaderValue(aiSign, "ai_sign");
  const response = await fetch(`${apiBaseUrl}/weaver/ai-assistant/review-rules/${ruleId}`, {
    method: "DELETE",
    headers: {
      "ai-sign": safeAiSign,
    },
  });
  if (!response.ok) {
    throw new Error(`智审规则删除失败：${response.status}`);
  }
}

export async function runWeaverPreReview(
  aiSign: string,
  payload: WeaverReviewRequest,
): Promise<WeaverReviewResponse> {
  const safeAiSign = normalizeHeaderValue(aiSign, "ai_sign");
  const response = await fetch(`${apiBaseUrl}/weaver/ai-assistant/review/precheck`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "ai-sign": safeAiSign,
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(`AI 智审请求失败：${response.status}`);
  }
  const result = (await response.json()) as Result<WeaverReviewResponse>;
  if (result.code !== 200) {
    throw new Error(result.msg || "AI 智审失败");
  }
  return result.data;
}

export async function fetchLatestWeaverReview(
  aiSign: string,
  workflowId: string,
  options?: {
    env?: string;
    requestId?: string;
    nodeId?: string;
  },
): Promise<WeaverReviewRecord | null> {
  const safeAiSign = normalizeHeaderValue(aiSign, "ai_sign");
  const params = new URLSearchParams({ workflow_id: workflowId });
  if (options?.env) params.set("env", options.env);
  if (options?.requestId) params.set("request_id", options.requestId);
  if (options?.nodeId) params.set("node_id", options.nodeId);
  const response = await fetch(`${apiBaseUrl}/weaver/ai-assistant/review/latest?${params.toString()}`, {
    method: "GET",
    headers: {
      "ai-sign": safeAiSign,
    },
  });
  if (!response.ok) {
    throw new Error(`智审记录加载失败：${response.status}`);
  }
  const result = (await response.json()) as Result<WeaverReviewRecord | null>;
  if (result.code !== 200) {
    throw new Error(result.msg || "智审记录加载失败");
  }
  return result.data || null;
}

async function saveWeaverWorkflowRule(
  aiSign: string,
  method: "POST" | "PUT",
  url: string,
  payload: Partial<WeaverWorkflowRulePayload>,
) {
  const safeAiSign = normalizeHeaderValue(aiSign, "ai_sign");
  const response = await fetch(url, {
    method,
    headers: {
      "Content-Type": "application/json",
      "ai-sign": safeAiSign,
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(`规则保存失败：${response.status}`);
  }
  const result = (await response.json()) as Result<WeaverWorkflowRule>;
  if (result.code !== 200 || !result.data) {
    throw new Error(result.msg || "规则保存失败");
  }
  return result.data;
}

async function saveWeaverReviewRule(
  aiSign: string,
  method: "POST" | "PUT",
  url: string,
  payload: Partial<WeaverReviewRulePayload>,
) {
  const safeAiSign = normalizeHeaderValue(aiSign, "ai_sign");
  const response = await fetch(url, {
    method,
    headers: {
      "Content-Type": "application/json",
      "ai-sign": safeAiSign,
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(`智审规则保存失败：${response.status}`);
  }
  const result = (await response.json()) as Result<WeaverReviewRule>;
  if (result.code !== 200 || !result.data) {
    throw new Error(result.msg || "智审规则保存失败");
  }
  return result.data;
}

function normalizeHeaderValue(value: string, name: string) {
  const normalized = value.trim();
  if (!normalized) {
    throw new Error(`缺少 ${name}，无法调用平台后端接口`);
  }
  if ([...normalized].some((char) => {
    const code = char.charCodeAt(0);
    return code !== 9 && (code < 32 || code > 126);
  })) {
    throw new Error(`${name} 只能使用英文、数字和常见符号，请检查 ecode 传入的密钥是否写成了中文`);
  }
  return normalized;
}

function handleSseBlock(block: string, handlers: StreamHandlers) {
  const lines = block.split(/\r?\n/);
  let event = "message";
  const dataLines: string[] = [];

  lines.forEach((line) => {
    if (line.startsWith("event:")) {
      event = line.slice("event:".length).trim();
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice("data:".length).trimStart());
    }
  });

  if (!dataLines.length) return;
  let data: unknown;
  try {
    data = JSON.parse(dataLines.join("\n"));
  } catch {
    return;
  }
  if (!data || typeof data !== "object") return;

  if (event === "message_delta") {
    const delta = "delta" in data ? data.delta : "";
    if (typeof delta === "string" && delta) handlers.onDelta?.(delta);
  }
  if (event === "actions") {
    const actions = "actions" in data && Array.isArray(data.actions) ? data.actions : [];
    handlers.onActions?.(actions as WeaverAssistantChatResponse["actions"]);
  }
  if (event === "done") {
    handlers.onDone?.();
  }
}
