import { useEffect, useMemo, useRef, useState } from "react";
import { ClipboardCheck, Loader2, Send, Sparkles, X } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { fetchWeaverFieldConfig, streamWeaverAssistantMessage } from "../api";
import { WeaverAssistantAvatar } from "../components/WeaverAssistantAvatar";
import type { WeaverAssistantAction, WeaverFieldConfigItem, WeaverFormContext, WeaverMessage } from "../types";

const makeMessageId = () => `${Date.now()}-${Math.random().toString(16).slice(2)}`;

const initialMessage: WeaverMessage = {
  id: "welcome",
  role: "assistant",
  content: "正在读取当前表单字段，请稍等...",
};

export default function WeaverAssistantEmbedPage() {
  const query = useMemo(() => new URLSearchParams(window.location.search), []);
  const aiSign = query.get("ai_sign") || query.get("aiSign") || "";
  const targetOrigin = query.get("target_origin") || "*";

  const [context, setContext] = useState<WeaverFormContext>({});
  const [messages, setMessages] = useState<WeaverMessage[]>([initialMessage]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [fieldConfigLoading, setFieldConfigLoading] = useState(false);
  const [fieldConfigError, setFieldConfigError] = useState("");
  const [pendingActions, setPendingActions] = useState<WeaverAssistantAction[]>([]);
  const pendingContextRequestsRef = useRef<
    Map<string, { resolve: (context: WeaverFormContext | null) => void; timer: number }>
  >(new Map());

  const fieldList = useMemo(() => Object.values(context.fields || {}).filter((field) => field.fieldId), [context]);
  const writableFieldList = useMemo(
    () => fieldList.filter((field) => field.visible === true && field.writable === true),
    [fieldList],
  );
  const workflowId = String(context.baseInfo?.workflowid || context.baseInfo?.workflowId || "未识别");
  const welcomeContent = useMemo(
    () => buildWelcomeMessage(context, fieldList, fieldConfigLoading, fieldConfigError),
    [context, fieldConfigError, fieldConfigLoading, fieldList],
  );

  useEffect(() => {
    setMessages((current) =>
      current.map((message) => (message.id === "welcome" ? { ...message, content: welcomeContent } : message)),
    );
  }, [welcomeContent]);

  useEffect(() => {
    const pendingContextRequests = pendingContextRequestsRef.current;
    const handleMessage = (event: MessageEvent) => {
      const data = event.data;
      if (!data || typeof data !== "object") return;
      if (data.type === "WEAVER_AI_CONTEXT") {
        setContext(data.context || {});
      }
      if (data.type === "WEAVER_AI_APPLY_RESULT") {
        const successCount = Number(data.successCount || 0);
        const failedCount = Number(data.failedCount || 0);
        if (failedCount > 0) {
          const failureLines = formatApplyFailures(data.failures);
          appendMessage({
            role: "assistant",
            content: [
              `表单写入完成 ${successCount} 项，失败 ${failedCount} 项。`,
              failureLines ? `\n失败明细：\n${failureLines}` : "",
              "\n请检查当前节点权限、字段是否可编辑，以及浏览框/下拉框内部值是否匹配。",
            ].join(""),
          });
        } else {
          appendMessage({ role: "assistant", content: `已写入表单 ${successCount} 项，请在页面上核对。` });
        }
      }
      if (data.type === "WEAVER_AI_CONTEXT_RESPONSE" && data.requestId) {
        const pending = pendingContextRequests.get(data.requestId);
        if (!pending) return;
        window.clearTimeout(pending.timer);
        pendingContextRequests.delete(data.requestId);
        pending.resolve(data.context || null);
      }
    };

    window.addEventListener("message", handleMessage);
    window.parent.postMessage({ type: "WEAVER_AI_READY" }, targetOrigin);
    return () => {
      window.removeEventListener("message", handleMessage);
      pendingContextRequests.forEach((pending) => {
        window.clearTimeout(pending.timer);
        pending.resolve(null);
      });
      pendingContextRequests.clear();
    };
  }, [targetOrigin]);

  useEffect(() => {
    if (!aiSign) return;
    if (!workflowId || workflowId === "未识别") return;
    if (fieldList.length > 0 || fieldConfigLoading) return;

    let cancelled = false;
    setFieldConfigLoading(true);
    setFieldConfigError("");

    fetchWeaverFieldConfig(aiSign, workflowId, context.env)
      .then((config) => {
        if (cancelled) return;
        const fields = buildFieldsFromConfig(config.fields || {}, context.fields || {});
        setContext((current) => ({
          ...current,
          env: current.env || config.env,
          fields,
        }));
      })
      .catch((error) => {
        if (cancelled) return;
        setFieldConfigError(error instanceof Error ? error.message : "字段配置加载失败");
      })
      .finally(() => {
        if (!cancelled) setFieldConfigLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [aiSign, context.env, context.fields, fieldConfigLoading, fieldList.length, workflowId]);

  const appendMessage = (message: Omit<WeaverMessage, "id">) => {
    setMessages((current) => current.concat({ ...message, id: makeMessageId() }));
  };

  const appendAssistantDelta = (messageId: string, delta: string) => {
    setMessages((current) =>
      current.map((message) =>
        message.id === messageId ? { ...message, content: `${message.content}${delta}` } : message,
      ),
    );
  };

  const updateAssistantMessage = (messageId: string, updater: (message: WeaverMessage) => WeaverMessage) => {
    setMessages((current) => current.map((message) => (message.id === messageId ? updater(message) : message)));
  };

  const handleSend = async () => {
    const content = input.trim();
    if (!content || loading) return;
    if (!aiSign) {
      appendMessage({ role: "assistant", content: "缺少 ai_sign 参数，无法调用平台后端接口。" });
      return;
    }
    if (pendingActions.length && isApplyCommand(content)) {
      setInput("");
      handleApply();
      return;
    }

    setInput("");
    setLoading(true);
    setPendingActions([]);
    const userMessage: WeaverMessage = { id: makeMessageId(), role: "user", content };
    const assistantMessageId = makeMessageId();
    setMessages((current) =>
      current.concat(userMessage, {
        id: assistantMessageId,
        role: "assistant",
        content: "",
      }),
    );

    try {
      const contextWithFields = await ensureContextWithFields();
      const history = messages
        .filter((message) => message.role === "assistant" || message.role === "user")
        .slice(-10)
        .map((message) => ({ role: message.role, content: message.content }));
      let receivedText = false;
      await streamWeaverAssistantMessage(aiSign, {
        message: content,
        context: contextWithFields,
        history,
      }, {
        onDelta: (delta) => {
          receivedText = true;
          appendAssistantDelta(assistantMessageId, delta);
        },
        onActions: (actions) => {
          const writableActions = (actions || []).filter(isWritableAction);
          setPendingActions(writableActions);
          updateAssistantMessage(assistantMessageId, (message) => ({
            ...message,
            content: message.content || "已生成填单建议，请确认后写入。",
            actions: actions || [],
          }));
        },
        onDone: () => {
          if (!receivedText) {
            appendAssistantDelta(assistantMessageId, "已处理完成。");
          }
        },
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : "请求失败";
      updateAssistantMessage(assistantMessageId, () => ({
        id: assistantMessageId,
        role: "assistant",
        content: `处理失败：${message}`,
      }));
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
    appendMessage({ role: "assistant", content: `已发送 ${pendingActions.length} 项写入指令，正在等待表单回执。` });
    setPendingActions([]);
  };

  const handleClose = () => {
    window.parent.postMessage({ type: "WEAVER_AI_CLOSE" }, targetOrigin);
  };

  return (
    <div className="flex h-screen min-h-0 flex-col bg-white text-slate-950">
      <header className="relative flex h-[108px] shrink-0 items-center justify-between overflow-hidden border-b border-blue-950 bg-[#071b50] px-5">
        <div className="flex min-w-0 items-center gap-4">
          <WeaverAssistantAvatar
            className="h-[76px] w-[86px] overflow-visible"
            mode={loading ? "thinking" : pendingActions.length ? "success" : "idle"}
            title="AI 填单助手"
            glow
          />
          <div className="min-w-0">
            <div className="truncate text-lg font-semibold text-white">泛微流程 AI 助手</div>
            <div className="mt-1 flex items-center gap-2 text-xs text-blue-100">
              <span className="h-2 w-2 rounded-full bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.9)]" />
              {loading ? "正在思考" : "在线 · 随时为你服务"}
            </div>
            <div className="mt-1 truncate text-[11px] text-blue-200/80">流程 ID：{workflowId}</div>
          </div>
        </div>
        <button
          type="button"
          className="inline-flex h-9 w-9 items-center justify-center rounded-full text-blue-100 transition hover:bg-white/10 hover:text-white"
          onClick={handleClose}
          title="关闭"
        >
          <X className="h-5 w-5" />
        </button>
      </header>

      <section className="border-b border-slate-200 bg-white px-4 py-3">
        <div className="flex items-center gap-2 text-xs font-medium text-slate-700">
          <Sparkles className="h-3.5 w-3.5 text-blue-600" />
          当前可写字段
        </div>
        <div className="mt-2 flex gap-2 overflow-x-auto pb-1">
          {writableFieldList.length ? (
            writableFieldList.slice(0, 8).map((field) => (
              <span
                key={field.fieldId}
                className="shrink-0 rounded-full border border-blue-100 bg-blue-50 px-2.5 py-1 text-xs text-blue-800"
              >
                {field.label || field.fieldId}
              </span>
            ))
          ) : (
            <span className="text-xs text-slate-400">
              {fieldConfigLoading ? "正在读取当前页面字段状态" : fieldConfigError || "等待 ecode 传入字段状态"}
            </span>
          )}
        </div>
      </section>

      <main className="min-h-0 flex-1 overflow-y-auto bg-[#f8faff] px-4 py-5">
        <div className="flex flex-col gap-4">
          {messages.map((message) => (
            <div
              key={message.id}
              className={
                message.role === "user"
                  ? "ml-12 self-end rounded-[18px_18px_5px_18px] bg-blue-600 px-4 py-3 text-sm leading-6 text-white shadow-[0_8px_20px_rgba(37,99,235,0.16)]"
                  : "flex max-w-[94%] items-start gap-2.5"
              }
            >
              {message.role === "assistant" ? (
                <>
                  <WeaverAssistantAvatar
                    className="mt-1 h-8 w-9"
                    mode={loading && message.id === messages[messages.length - 1]?.id ? "thinking" : "idle"}
                    title="AI 助手"
                  />
                  <div className="min-w-0 rounded-[5px_18px_18px_18px] border border-slate-100 bg-white px-4 py-3 text-sm leading-6 text-slate-700 shadow-[0_8px_24px_rgba(15,23,42,0.06)]">
                    <MessageContent content={message.content} />
                  </div>
                </>
              ) : (
                <MessageContent content={message.content} />
              )}
            </div>
          ))}
        </div>
      </main>

      <footer className="shrink-0 border-t border-slate-200 bg-white p-4">
        {pendingActions.length ? (
          <div className="mb-3 rounded-lg border border-blue-100 bg-blue-50/70 px-3 py-2">
            <div className="text-xs font-medium text-blue-950">待写入表单</div>
            <div className="mt-1 space-y-1 text-xs leading-5 text-blue-900">
              {pendingActions.map((action, index) => (
                <div key={`${action.type}-${action.field || action.detail || index}`}>
                  {formatActionLabel(action, index)}
                </div>
              ))}
            </div>
          </div>
        ) : null}
        <div className="rounded-xl border border-blue-100 bg-white p-2 shadow-[0_8px_24px_rgba(30,64,175,0.08)] transition focus-within:border-blue-300 focus-within:ring-2 focus-within:ring-blue-100">
          <textarea
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                void handleSend();
              }
            }}
            className="h-16 w-full resize-none border-0 bg-transparent px-2 py-1 text-sm outline-none placeholder:text-slate-400"
            placeholder="输入你的问题或填单要求..."
          />
          <div className="flex items-center justify-end gap-2">
          <button
            type="button"
            disabled={!pendingActions.length}
            onClick={handleApply}
              className="inline-flex h-9 items-center gap-2 rounded-full border border-slate-200 bg-white px-3 text-sm font-medium text-slate-700 transition hover:border-blue-200 hover:bg-blue-50 disabled:cursor-not-allowed disabled:opacity-45"
          >
            <ClipboardCheck className="h-4 w-4" />
            确认写入
          </button>
          <button
            type="button"
            disabled={loading || !input.trim()}
            onClick={handleSend}
              className="inline-flex h-10 w-10 items-center justify-center rounded-full bg-blue-600 text-white shadow-[0_6px_16px_rgba(37,99,235,0.3)] transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-45"
              title={loading ? "处理中" : "发送"}
          >
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
          </button>
          </div>
        </div>
        <div className="mt-2 text-center text-[11px] text-slate-400">Enter 发送，Shift + Enter 换行</div>
      </footer>
    </div>
  );

  async function ensureContextWithFields() {
    const latestContext = await requestLatestContext();
    const baseContext = latestContext ? mergeContext(context, latestContext) : context;

    if (Object.values(baseContext.fields || {}).some((field) => field.fieldId)) {
      setContext(baseContext);
      return baseContext;
    }
    const latestWorkflowId = String(baseContext.baseInfo?.workflowid || baseContext.baseInfo?.workflowId || "");
    if (!latestWorkflowId) {
      return baseContext;
    }

    setFieldConfigLoading(true);
    setFieldConfigError("");
    try {
      const config = await fetchWeaverFieldConfig(aiSign, latestWorkflowId, baseContext.env);
      const fields = buildFieldsFromConfig(config.fields || [], baseContext.fields || {});
      const nextContext = {
        ...baseContext,
        env: baseContext.env || config.env,
        fields,
      };
      setContext(nextContext);
      return nextContext;
    } catch (error) {
      const message = error instanceof Error ? error.message : "字段配置加载失败";
      setFieldConfigError(message);
      return baseContext;
    } finally {
      setFieldConfigLoading(false);
    }
  }

  function requestLatestContext() {
    const requestId = `${Date.now()}-${Math.random().toString(16).slice(2)}`;
    return new Promise<WeaverFormContext | null>((resolve) => {
      const timer = window.setTimeout(() => {
        pendingContextRequestsRef.current.delete(requestId);
        resolve(null);
      }, 800);
      pendingContextRequestsRef.current.set(requestId, { resolve, timer });
      window.parent.postMessage({ type: "WEAVER_AI_REQUEST_CONTEXT", requestId }, targetOrigin);
    });
  }
}

function mergeContext(current: WeaverFormContext, latest: WeaverFormContext) {
  return {
    ...current,
    ...latest,
    baseInfo: {
      ...(current.baseInfo || {}),
      ...(latest.baseInfo || {}),
    },
    fields: {
      ...(current.fields || {}),
      ...(latest.fields || {}),
    },
  };
}

function isWritableAction(action: WeaverAssistantAction) {
  return action.type === "set_field" || action.type === "add_detail_row";
}

function isApplyCommand(content: string) {
  return /^(确认|执行|写入|写入表单|确认写入|可以|就这样|开始写入|帮我写入)$/i.test(content.trim());
}

function buildWelcomeMessage(
  context: WeaverFormContext,
  fields: NonNullable<WeaverFormContext["fields"]>[string][],
  loading: boolean,
  error: string,
) {
  if (error) {
    return `当前表单字段读取失败：${error}`;
  }
  if (loading || !fields.length) {
    return "正在读取当前表单字段，请稍等...";
  }

  const formName = String(
    context.baseInfo?.workflowname ||
      context.baseInfo?.workflowName ||
      context.baseInfo?.requestname ||
      context.baseInfo?.requestName ||
      "当前流程表单",
  );
  const writableFields = fields.filter((field) => field.visible === true && field.writable === true);
  const writableLabels = writableFields
    .map((field) => field.label)
    .filter(Boolean)
    .slice(0, 8)
    .join("、");

  if (!writableLabels) {
    return `已读取到${formName}，但当前页面暂未识别到可填写字段。隐藏、只读和系统带出字段不会自动写入。`;
  }

  return [
    `已读取到${formName}。`,
    `当前可协助填写：${writableLabels}。`,
    "申请人、申请日期、申请公司等系统带出或只读字段，我只会作为上下文参考，不会写入。",
    "你可以直接告诉我请假类型、时间和原因，我会先整理成填单建议，确认后再写入。",
  ].join("\n\n");
}

function buildFieldsFromConfig(
  items: WeaverFieldConfigItem[] | Record<string, never>,
  currentFields: WeaverFormContext["fields"],
) {
  const fields: WeaverFormContext["fields"] = {};
  if (!Array.isArray(items)) return currentFields || fields;
  const currentByFieldId = Object.values(currentFields || {}).reduce<Record<string, NonNullable<WeaverFormContext["fields"]>[string]>>(
    (record, field) => {
      if (field.fieldId) record[field.fieldId] = field;
      return record;
    },
    {},
  );

  items.forEach((item) => {
    if (!item.fieldId) return;
    const key = item.bizKey || item.fieldId;
    const currentField = currentFields?.[key] || currentFields?.[item.fieldId] || currentByFieldId[item.fieldId];
    fields[key] = {
      label: item.label || item.fieldId,
      fieldId: item.fieldId,
      type: item.type || "text",
      options: item.options || currentField?.options || [],
      browserType: item.browserType || item.fieldType || currentField?.browserType,
      writable: currentField?.writable ?? false,
      required: currentField?.required,
      visible: currentField?.visible ?? false,
      readonlyReason: currentField?.readonlyReason ?? "等待 ecode 传入当前页面状态",
      value: currentField?.value ?? "",
      displayValue: currentField?.displayValue ?? "",
    };
  });
  return fields;
}

function formatActionLabel(action: WeaverAssistantAction, index: number) {
  if (action.type === "set_field") {
    return `${index + 1}. ${action.label || action.field || "字段"}：${action.displayValue ?? action.value ?? ""}`;
  }
  if (action.type === "add_detail_row") {
    return `${index + 1}. 新增明细：${action.detail || "明细行"}`;
  }
  return `${index + 1}. 待处理动作`;
}

function formatApplyFailures(failures: unknown) {
  if (!Array.isArray(failures)) return "";
  return failures
    .slice(0, 6)
    .map((failure, index) => {
      if (!failure || typeof failure !== "object") {
        return `${index + 1}. 未知失败`;
      }
      const item = failure as Record<string, unknown>;
      const label = String(item.label || item.field || item.detail || "未知字段");
      const displayValue = item.displayValue ?? item.value ?? "";
      const message = String(item.message || "写入失败");
      return `${index + 1}. ${label}${displayValue ? `：${String(displayValue)}` : ""}，${message}`;
    })
    .join("\n");
}

function MessageContent({ content }: { content: string }) {
  return (
    <div className="weaver-assistant-markdown">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
          ul: ({ children }) => <ul className="mb-2 list-disc space-y-1 pl-5 last:mb-0">{children}</ul>,
          ol: ({ children }) => <ol className="mb-2 list-decimal space-y-1 pl-5 last:mb-0">{children}</ol>,
          li: ({ children }) => <li className="pl-1">{children}</li>,
          strong: ({ children }) => <strong className="font-semibold text-slate-950">{children}</strong>,
          h1: ({ children }) => <p className="mb-2 text-sm font-semibold text-slate-950">{children}</p>,
          h2: ({ children }) => <p className="mb-2 text-sm font-semibold text-slate-950">{children}</p>,
          h3: ({ children }) => <p className="mb-2 text-sm font-semibold text-slate-950">{children}</p>,
          code: ({ children }) => (
            <code className="rounded bg-slate-200 px-1 py-0.5 text-[12px] text-slate-800">{children}</code>
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
