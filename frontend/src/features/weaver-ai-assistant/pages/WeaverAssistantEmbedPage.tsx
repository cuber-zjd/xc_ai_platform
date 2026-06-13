import { useEffect, useMemo, useState } from "react";
import { ClipboardCheck, Loader2, Send, Sparkles, X } from "lucide-react";

import { sendWeaverAssistantMessage } from "../api";
import type { WeaverAssistantAction, WeaverFormContext, WeaverMessage } from "../types";

const makeMessageId = () => `${Date.now()}-${Math.random().toString(16).slice(2)}`;

const initialMessage: WeaverMessage = {
  id: "welcome",
  role: "assistant",
  content: "你好，我可以读取当前流程上下文，并生成填单建议。写入前会先让你确认。",
};

export default function WeaverAssistantEmbedPage() {
  const query = useMemo(() => new URLSearchParams(window.location.search), []);
  const aiSign = query.get("ai_sign") || query.get("aiSign") || "";
  const targetOrigin = query.get("target_origin") || "*";

  const [context, setContext] = useState<WeaverFormContext>({});
  const [messages, setMessages] = useState<WeaverMessage[]>([initialMessage]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [pendingActions, setPendingActions] = useState<WeaverAssistantAction[]>([]);

  const fieldList = useMemo(() => Object.values(context.fields || {}).filter((field) => field.fieldId), [context]);
  const workflowId = String(context.baseInfo?.workflowid || context.baseInfo?.workflowId || "未识别");

  useEffect(() => {
    const handleMessage = (event: MessageEvent) => {
      const data = event.data;
      if (!data || typeof data !== "object") return;
      if (data.type === "WEAVER_AI_CONTEXT") {
        setContext(data.context || {});
      }
    };

    window.addEventListener("message", handleMessage);
    window.parent.postMessage({ type: "WEAVER_AI_READY" }, targetOrigin);
    return () => window.removeEventListener("message", handleMessage);
  }, [targetOrigin]);

  const appendMessage = (message: Omit<WeaverMessage, "id">) => {
    setMessages((current) => current.concat({ ...message, id: makeMessageId() }));
  };

  const handleSend = async () => {
    const content = input.trim();
    if (!content || loading) return;
    if (!aiSign) {
      appendMessage({ role: "assistant", content: "缺少 ai_sign 参数，无法调用平台后端接口。" });
      return;
    }

    setInput("");
    setLoading(true);
    setPendingActions([]);
    appendMessage({ role: "user", content });

    try {
      const result = await sendWeaverAssistantMessage(aiSign, {
        message: content,
        context,
      });
      setPendingActions(result.actions || []);
      appendMessage({
        role: "assistant",
        content: buildReply(result.message, result.actions || []),
        actions: result.actions || [],
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : "请求失败";
      appendMessage({ role: "assistant", content: `处理失败：${message}` });
    } finally {
      setLoading(false);
    }
  };

  const handleApply = () => {
    if (!pendingActions.length) return;
    window.parent.postMessage(
      {
        type: "WEAVER_AI_APPLY_ACTIONS",
        actions: pendingActions,
      },
      targetOrigin,
    );
    appendMessage({ role: "assistant", content: `已发送 ${pendingActions.length} 个写入动作，请回到表单检查结果。` });
    setPendingActions([]);
  };

  const handleClose = () => {
    window.parent.postMessage({ type: "WEAVER_AI_CLOSE" }, targetOrigin);
  };

  return (
    <div className="flex h-screen min-h-0 flex-col bg-white text-slate-950">
      <header className="flex h-14 shrink-0 items-center justify-between border-b border-slate-200 bg-slate-50 px-4">
        <div className="flex min-w-0 items-center gap-3">
          <img src="/ai_logo.svg" alt="AI填单助手" className="h-8 w-8 shrink-0 object-contain" />
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold">泛微流程 AI 助手</div>
            <div className="truncate text-xs text-slate-500">流程 ID：{workflowId}</div>
          </div>
        </div>
        <button
          type="button"
          className="inline-flex h-8 w-8 items-center justify-center rounded-md text-slate-500 transition hover:bg-slate-200 hover:text-slate-900"
          onClick={handleClose}
          title="关闭"
        >
          <X className="h-4 w-4" />
        </button>
      </header>

      <section className="border-b border-slate-200 bg-white px-4 py-3">
        <div className="flex items-center gap-2 text-xs font-medium text-slate-600">
          <Sparkles className="h-3.5 w-3.5 text-teal-600" />
          当前可写字段
        </div>
        <div className="mt-2 flex gap-2 overflow-x-auto pb-1">
          {fieldList.length ? (
            fieldList.slice(0, 8).map((field) => (
              <span
                key={field.fieldId}
                className="shrink-0 rounded-md border border-slate-200 bg-slate-50 px-2 py-1 text-xs text-slate-600"
              >
                {field.label || field.fieldId}
              </span>
            ))
          ) : (
            <span className="text-xs text-slate-400">等待 ecode 传入字段配置</span>
          )}
        </div>
      </section>

      <main className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
        <div className="flex flex-col gap-3">
          {messages.map((message) => (
            <div
              key={message.id}
              className={
                message.role === "user"
                  ? "ml-10 rounded-lg bg-teal-50 px-3 py-2 text-sm leading-6 text-teal-950"
                  : "mr-8 rounded-lg bg-slate-100 px-3 py-2 text-sm leading-6 text-slate-800"
              }
            >
              <div className="whitespace-pre-wrap">{message.content}</div>
            </div>
          ))}
        </div>
      </main>

      <footer className="shrink-0 border-t border-slate-200 bg-white p-3">
        <textarea
          value={input}
          onChange={(event) => setInput(event.target.value)}
          className="h-20 w-full resize-none rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm outline-none transition placeholder:text-slate-400 focus:border-teal-500 focus:ring-2 focus:ring-teal-500/15"
          placeholder="例如：帮我把请假原因写得正式一点，并补全标题"
        />
        <div className="mt-2 flex items-center justify-end gap-2">
          <button
            type="button"
            disabled={!pendingActions.length}
            onClick={handleApply}
            className="inline-flex h-9 items-center gap-2 rounded-md border border-slate-200 bg-white px-3 text-sm font-medium text-slate-700 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <ClipboardCheck className="h-4 w-4" />
            写入表单
          </button>
          <button
            type="button"
            disabled={loading || !input.trim()}
            onClick={handleSend}
            className="inline-flex h-9 items-center gap-2 rounded-md bg-teal-700 px-3 text-sm font-medium text-white transition hover:bg-teal-800 disabled:cursor-not-allowed disabled:opacity-55"
          >
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
            {loading ? "处理中" : "发送"}
          </button>
        </div>
      </footer>
    </div>
  );
}

function buildReply(message: string, actions: WeaverAssistantAction[]) {
  if (!actions.length) return message;
  const lines = [message, "", "待写入内容："];
  actions.forEach((action, index) => {
    if (action.type === "set_field") {
      lines.push(`${index + 1}. ${action.label || action.field || "字段"} = ${action.value ?? ""}`);
    } else if (action.type === "add_detail_row") {
      lines.push(`${index + 1}. 新增明细行：${action.detail || "未命名明细"}`);
    } else if (action.type === "show_message") {
      lines.push(`${index + 1}. ${action.message || "展示提示"}`);
    }
  });
  return lines.join("\n");
}
