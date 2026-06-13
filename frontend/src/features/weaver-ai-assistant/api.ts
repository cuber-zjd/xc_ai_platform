import type { WeaverAssistantChatResponse, WeaverFormContext } from "./types";

const apiBaseUrl = import.meta.env.VITE_API_URL || "/api/v1";

interface ChatPayload {
  message: string;
  context: WeaverFormContext;
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
  const response = await fetch(`${apiBaseUrl}/weaver/ai-assistant/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "ai-sign": aiSign,
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw new Error(`接口请求失败：${response.status}`);
  }

  const result = (await response.json()) as Result<WeaverAssistantChatResponse>;
  if (result.code !== 200) {
    throw new Error(result.msg || "AI 助手处理失败");
  }
  return result.data;
}
