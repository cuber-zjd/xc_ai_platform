import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, CheckCircle2, ClipboardCheck, Loader2, RefreshCw, ShieldCheck, X } from "lucide-react";

import { fetchLatestWeaverReview, runWeaverPreReview } from "../api";
import type { WeaverFormContext, WeaverReviewRecord, WeaverReviewResult } from "../types";

export default function WeaverReviewEmbedPage() {
  const query = useMemo(() => new URLSearchParams(window.location.search), []);
  const aiSign = query.get("ai_sign") || query.get("aiSign") || "";
  const targetOrigin = query.get("target_origin") || "*";
  const env = query.get("env") || "default";
  const queryWorkflowId = query.get("workflow_id") || query.get("workflowId") || "";
  const queryRequestId = query.get("request_id") || query.get("requestId") || "";
  const queryNodeId = query.get("node_id") || query.get("nodeId") || "";
  const queryNodeName = query.get("node_name") || query.get("nodeName") || "";
  const reviewerUserId = query.get("reviewer_user_id") || query.get("reviewerUserId") || "";
  const reviewerName = query.get("reviewer_name") || query.get("reviewerName") || "";
  const autoRun = query.get("auto_run") === "1" || query.get("autoRun") === "1";

  const [context, setContext] = useState<WeaverFormContext>({ env });
  const [record, setRecord] = useState<WeaverReviewRecord | null>(null);
  const [result, setResult] = useState<WeaverReviewResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("正在等待泛微页面上下文...");
  const [error, setError] = useState("");

  const workflowId = String(context.baseInfo?.workflowid || context.baseInfo?.workflowId || queryWorkflowId || "");
  const requestId = String(context.baseInfo?.requestid || context.baseInfo?.requestId || queryRequestId || "");
  const nodeId = String(context.baseInfo?.nodeid || context.baseInfo?.nodeId || queryNodeId || "");
  const displayResult = result || normalizeRecordResult(record);

  const loadLatest = useCallback(async () => {
    if (!aiSign || !workflowId) return;
    setError("");
    try {
      const data = await fetchLatestWeaverReview(aiSign, workflowId, {
        env: context.env || env,
        requestId,
        nodeId,
      });
      setRecord(data);
      setMessage(data ? "已读取最近一次 AI 智审结果。" : "当前节点暂无 AI 智审结果，可手动发起预审。");
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "智审记录加载失败");
    }
  }, [aiSign, context.env, env, nodeId, requestId, workflowId]);

  const handleReview = useCallback(async () => {
    if (!aiSign) {
      setError("缺少 ai_sign，无法调用平台智审接口。");
      return;
    }
    if (!workflowId) {
      setError("未识别到 workflowId，无法进行 AI 智审。");
      return;
    }
    setLoading(true);
    setError("");
    setMessage("AI 正在预审当前流程，请稍等...");
    try {
      const response = await runWeaverPreReview(aiSign, {
        context: {
          ...context,
          env: context.env || env,
          baseInfo: {
            ...(context.baseInfo || {}),
            workflowid: workflowId,
            requestid: requestId,
            nodeid: nodeId,
          },
        },
        triggerType: "manual",
        operation: "review",
        currentNodeId: nodeId || null,
        currentNodeName: queryNodeName || null,
        reviewer: reviewerUserId || reviewerName ? { userId: reviewerUserId, userName: reviewerName } : null,
      });
      setResult(response.result);
      setRecord(response.record);
      setMessage("AI 智审已完成。");
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "AI 智审失败");
      setMessage("");
    } finally {
      setLoading(false);
    }
  }, [aiSign, context, env, nodeId, queryNodeName, requestId, reviewerName, reviewerUserId, workflowId]);

  useEffect(() => {
    const handleMessage = (event: MessageEvent) => {
      const data = event.data;
      if (!data || typeof data !== "object") return;
      if (data.type === "WEAVER_AI_CONTEXT" || data.type === "WEAVER_AI_REVIEW_CONTEXT") {
        setContext(data.context || {});
        setMessage("已读取当前流程上下文。");
      }
    };
    window.addEventListener("message", handleMessage);
    window.parent.postMessage({ type: "WEAVER_AI_REVIEW_READY" }, targetOrigin);
    window.parent.postMessage({ type: "WEAVER_AI_REQUEST_CONTEXT", requestId: `review-${Date.now()}` }, targetOrigin);
    return () => window.removeEventListener("message", handleMessage);
  }, [targetOrigin]);

  useEffect(() => {
    void loadLatest();
  }, [loadLatest]);

  useEffect(() => {
    if (!autoRun || record || result || loading || !workflowId) return;
    void handleReview();
  }, [autoRun, handleReview, loading, record, result, workflowId]);

  return (
    <div className="flex h-screen min-h-0 flex-col bg-white text-slate-950">
      <header className="flex h-14 shrink-0 items-center justify-between border-b border-slate-200 bg-slate-50 px-4">
        <div className="flex min-w-0 items-center gap-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-teal-50 text-teal-700">
            <ShieldCheck className="h-5 w-5" />
          </div>
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold">流程 AI 智审</div>
            <div className="truncate text-xs text-slate-500">流程：{workflowId || "未识别"} · 节点：{nodeId || "当前节点"}</div>
          </div>
        </div>
        <button
          type="button"
          className="inline-flex h-8 w-8 items-center justify-center rounded-md text-slate-500 transition hover:bg-slate-200 hover:text-slate-900"
          onClick={() => window.parent.postMessage({ type: "WEAVER_AI_REVIEW_CLOSE" }, targetOrigin)}
          title="关闭"
        >
          <X className="h-4 w-4" />
        </button>
      </header>

      <main className="min-h-0 flex-1 overflow-y-auto p-4">
        {message ? <div className="mb-3 rounded-md bg-teal-50 px-3 py-2 text-xs text-teal-800">{message}</div> : null}
        {error ? <div className="mb-3 rounded-md bg-red-50 px-3 py-2 text-xs text-red-700">{error}</div> : null}

        {displayResult ? (
          <section className="space-y-3">
            <div className={`rounded-lg border p-4 ${riskClass(displayResult.riskLevel)}`}>
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-2 text-sm font-semibold">
                  {displayResult.riskLevel === "low" ? <CheckCircle2 className="h-4 w-4" /> : <AlertTriangle className="h-4 w-4" />}
                  {riskText(displayResult.riskLevel)}
                </div>
                <span className="rounded-md bg-white/70 px-2 py-1 text-xs">{decisionText(displayResult.decisionSuggestion)}</span>
              </div>
              <p className="mt-3 text-sm leading-6">{displayResult.summary}</p>
              {displayResult.suggestedOpinion ? (
                <div className="mt-3 rounded-md bg-white/70 px-3 py-2 text-xs leading-5">
                  建议意见：{displayResult.suggestedOpinion}
                </div>
              ) : null}
            </div>

            <section className="rounded-lg border border-slate-200 bg-white">
              <div className="border-b border-slate-100 px-3 py-2 text-sm font-semibold">检查项</div>
              <div className="divide-y divide-slate-100">
                {displayResult.checks?.length ? (
                  displayResult.checks.map((item, index) => (
                    <div key={`${item.name}-${index}`} className="px-3 py-3">
                      <div className="flex items-center justify-between gap-3">
                        <span className="text-sm font-medium">{item.name}</span>
                        <span className={`text-xs ${checkTextClass(item.status)}`}>{checkText(item.status)}</span>
                      </div>
                      {item.detail ? <p className="mt-1 text-xs leading-5 text-slate-500">{item.detail}</p> : null}
                    </div>
                  ))
                ) : (
                  <div className="px-3 py-6 text-center text-sm text-slate-500">暂无明细检查项。</div>
                )}
              </div>
            </section>

            {displayResult.missingMaterials?.length || displayResult.concerns?.length ? (
              <section className="rounded-lg border border-amber-100 bg-amber-50 px-3 py-3 text-sm text-amber-900">
                {displayResult.missingMaterials?.length ? (
                  <div>
                    <div className="font-semibold">缺失材料</div>
                    <ul className="mt-2 list-inside list-disc space-y-1 text-xs leading-5">
                      {displayResult.missingMaterials.map((item) => <li key={item}>{item}</li>)}
                    </ul>
                  </div>
                ) : null}
                {displayResult.concerns?.length ? (
                  <div className="mt-3">
                    <div className="font-semibold">关注点</div>
                    <ul className="mt-2 list-inside list-disc space-y-1 text-xs leading-5">
                      {displayResult.concerns.map((item) => <li key={item}>{item}</li>)}
                    </ul>
                  </div>
                ) : null}
              </section>
            ) : null}
          </section>
        ) : (
          <div className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-8 text-center text-sm text-slate-500">
            当前还没有 AI 智审结果。
          </div>
        )}
      </main>

      <footer className="flex shrink-0 items-center justify-between gap-3 border-t border-slate-200 bg-white px-4 py-3">
        <div className="min-w-0 text-xs text-slate-500">
          {record ? `记录 #${record.id}` : "预审不会自动审批流程"}
        </div>
        <button
          type="button"
          disabled={loading}
          onClick={() => void handleReview()}
          className="inline-flex h-10 items-center gap-2 rounded-md bg-teal-700 px-4 text-sm font-medium text-white transition hover:bg-teal-800 disabled:opacity-60"
        >
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : record ? <RefreshCw className="h-4 w-4" /> : <ClipboardCheck className="h-4 w-4" />}
          {record ? "重新智审" : "立即智审"}
        </button>
      </footer>
    </div>
  );
}

function normalizeRecordResult(record: WeaverReviewRecord | null): WeaverReviewResult | null {
  if (!record) return null;
  return {
    summary: record.summary,
    riskLevel: normalizeRisk(record.riskLevel),
    decisionSuggestion: normalizeDecision(record.decisionSuggestion),
    suggestedOpinion: record.suggestedOpinion,
    checks: Array.isArray(record.reviewResult?.checks) ? record.reviewResult.checks : [],
    missingMaterials: Array.isArray(record.reviewResult?.missingMaterials) ? record.reviewResult.missingMaterials : [],
    concerns: Array.isArray(record.reviewResult?.concerns) ? record.reviewResult.concerns : [],
    confidence: record.confidence,
    canAutoApprove: record.canAutoApprove,
  };
}

function normalizeRisk(value: string): WeaverReviewResult["riskLevel"] {
  return ["low", "medium", "high", "blocked"].includes(value) ? value as WeaverReviewResult["riskLevel"] : "medium";
}

function normalizeDecision(value: string): WeaverReviewResult["decisionSuggestion"] {
  return ["approve", "return", "reject", "supplement", "manual_review"].includes(value)
    ? value as WeaverReviewResult["decisionSuggestion"]
    : "manual_review";
}

function riskText(value: string) {
  const map: Record<string, string> = { low: "低风险", medium: "中风险", high: "高风险", blocked: "阻断风险" };
  return map[value] || "中风险";
}

function decisionText(value: string) {
  const map: Record<string, string> = {
    approve: "建议同意",
    return: "建议退回",
    reject: "建议拒绝",
    supplement: "建议补充",
    manual_review: "建议人工复核",
  };
  return map[value] || "建议人工复核";
}

function riskClass(value: string) {
  if (value === "low") return "border-teal-100 bg-teal-50 text-teal-900";
  if (value === "high" || value === "blocked") return "border-red-100 bg-red-50 text-red-900";
  return "border-amber-100 bg-amber-50 text-amber-900";
}

function checkText(value: string) {
  const map: Record<string, string> = { pass: "通过", warning: "提醒", fail: "不通过", unknown: "待确认" };
  return map[value] || "待确认";
}

function checkTextClass(value: string) {
  if (value === "pass") return "text-teal-700";
  if (value === "fail") return "text-red-700";
  if (value === "warning") return "text-amber-700";
  return "text-slate-500";
}
