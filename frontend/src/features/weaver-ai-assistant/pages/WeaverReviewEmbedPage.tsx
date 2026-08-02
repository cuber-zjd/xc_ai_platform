import { useCallback, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import {
  AlertTriangle,
  BarChart3,
  CheckCircle2,
  ChevronDown,
  ClipboardCheck,
  Info,
  ListChecks,
  Loader2,
  RefreshCw,
  ShieldCheck,
  TableProperties,
  Volume2,
  X,
} from "lucide-react";

import { fetchLatestWeaverReview, fetchWeaverFieldConfig, runWeaverPreReview, runWeaverTestReview } from "../api";
import { WeaverAssistantAvatar } from "../components/WeaverAssistantAvatar";
import type {
  WeaverFieldConfigResponse,
  WeaverFormContext,
  WeaverReviewRecord,
  WeaverReviewComparisonRow,
  WeaverReviewComparisonTable,
  WeaverReviewResult,
} from "../types";

export default function WeaverReviewEmbedPage() {
  const query = useMemo(() => new URLSearchParams(window.location.search), []);
  const aiSign = query.get("ai_sign") || query.get("aiSign") || "";
  const targetOrigin = query.get("target_origin") || "*";
  const env = query.get("env") || "default";
  const queryWorkflowId = query.get("workflow_id") || query.get("workflowId") || "";
  const queryWorkflowName = query.get("workflow_name") || query.get("workflowName") || "";
  const queryRequestId = query.get("request_id") || query.get("requestId") || "";
  const queryNodeId = query.get("node_id") || query.get("nodeId") || "";
  const queryNodeName = query.get("node_name") || query.get("nodeName") || "";
  const reviewerUserId = query.get("reviewer_user_id") || query.get("reviewerUserId") || "";
  const reviewerName = query.get("reviewer_name") || query.get("reviewerName") || "";
  const autoRun = query.get("auto_run") === "1" || query.get("autoRun") === "1";
  const testMode = query.get("test_mode") === "1" || query.get("testMode") === "1";

  const [context, setContext] = useState<WeaverFormContext>({
    env,
    baseInfo: testMode ? { workflowid: queryWorkflowId, workflowname: queryWorkflowName, requestid: queryRequestId } : {},
  });
  const [record, setRecord] = useState<WeaverReviewRecord | null>(null);
  const [result, setResult] = useState<WeaverReviewResult | null>(null);
  const [metadata, setMetadata] = useState<WeaverFieldConfigResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState(
    testMode ? "测试智审将读取该请求的数据库快照，并忽略其当前节点。" : "正在等待泛微页面上下文...",
  );
  const [error, setError] = useState("");

  const workflowId = String(context.baseInfo?.workflowid || context.baseInfo?.workflowId || queryWorkflowId || "");
  const requestId = String(context.baseInfo?.requestid || context.baseInfo?.requestId || queryRequestId || "");
  const nodeId = String(context.baseInfo?.nodeid || context.baseInfo?.nodeId || queryNodeId || "");
  const displayResult = result || normalizeRecordResult(record);
  const workflowName =
    record?.workflowName ||
    readBaseInfoText(context.baseInfo, ["workflowname", "workflowName", "workflow_name"]) ||
    queryWorkflowName ||
    metadata?.workflowName ||
    "当前流程";
  const resolvedNodeName =
    record?.nodeName ||
    queryNodeName ||
    readBaseInfoText(context.baseInfo, ["nodename", "nodeName", "node_name"]) ||
    metadata?.nodes?.find((item) => String(item.nodeId) === nodeId)?.nodeName ||
    "当前节点";
  const nodeName = testMode
    ? `测试审批 · ${record?.nodeName || "忽略当前节点"}`
    : resolvedNodeName;

  const loadLatest = useCallback(async () => {
    if (testMode || !aiSign || !workflowId) return;
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
  }, [aiSign, context.env, env, nodeId, requestId, testMode, workflowId]);

  useEffect(() => {
    if (!aiSign || !workflowId) {
      setMetadata(null);
      return;
    }
    let cancelled = false;
    void fetchWeaverFieldConfig(aiSign, workflowId, context.env || env)
      .then((data) => {
        if (!cancelled) setMetadata(data);
      })
      .catch(() => {
        if (!cancelled) setMetadata(null);
      });
    return () => {
      cancelled = true;
    };
  }, [aiSign, context.env, env, workflowId]);

  const handleReview = useCallback(async () => {
    if (!aiSign) {
      setError("缺少 ai_sign，无法调用平台智审接口。");
      return;
    }
    if (!workflowId) {
      setError("未识别到 workflowId，无法进行 AI 智审。");
      return;
    }
    if (testMode && !requestId) {
      setError("请输入需要测试的 requestId。");
      return;
    }
    setLoading(true);
    setError("");
    setMessage("AI 正在预审当前流程，请稍等...");
    try {
      const response = testMode
        ? await runWeaverTestReview(aiSign, {
            env: context.env || env,
            workflowId,
            workflowName,
            requestId,
          })
        : await runWeaverPreReview(aiSign, {
            context: {
              ...context,
              env: context.env || env,
              baseInfo: {
                ...(context.baseInfo || {}),
                workflowid: workflowId,
                workflowname: workflowName,
                requestid: requestId,
                nodeid: nodeId,
                nodename: nodeName,
              },
            },
            triggerType: "manual",
            operation: "review",
            currentNodeId: nodeId || null,
            currentNodeName: nodeName === "当前节点" ? null : nodeName,
            reviewer: reviewerUserId || reviewerName ? { userId: reviewerUserId, userName: reviewerName } : null,
          });
      setResult(response.result);
      setRecord(response.record);
      setMessage(testMode ? "测试智审已完成，结果已独立保存。" : "AI 智审已完成。");
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "AI 智审失败");
      setMessage("");
    } finally {
      setLoading(false);
    }
  }, [aiSign, context, env, nodeId, nodeName, requestId, reviewerName, reviewerUserId, testMode, workflowId, workflowName]);

  useEffect(() => {
    if (testMode) return;
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
  }, [targetOrigin, testMode]);

  useEffect(() => {
    void loadLatest();
  }, [loadLatest]);

  useEffect(() => {
    if (!autoRun || record || result || loading || !workflowId) return;
    void handleReview();
  }, [autoRun, handleReview, loading, record, result, workflowId]);

  return (
    <div className="flex h-screen min-h-0 flex-col overflow-hidden bg-[#fbfdff] text-[#12203a]">
      <header className="relative h-[148px] shrink-0 overflow-hidden border-b border-[#edf1f8] bg-white px-6 py-5">
        <img
          src="/ai/weaver-assistant/review-header-bg.png"
          alt=""
          className="absolute -right-[22%] -top-[22%] h-[160%] w-[94%] object-cover object-center opacity-[0.11]"
        />
        <div className="absolute inset-0 bg-[linear-gradient(90deg,rgba(255,255,255,1)_0%,rgba(255,255,255,0.96)_42%,rgba(246,250,255,0.55)_100%)]" />
        <div className="relative flex h-full items-center justify-between gap-4">
          <div className="flex min-w-0 items-center gap-4">
            <span className="inline-flex h-16 w-16 shrink-0 items-center justify-center rounded-full border border-[#edf3fb] bg-[rgba(247,250,255,0.86)] shadow-[0_8px_22px_rgba(54,93,160,0.12)]">
              <WeaverAssistantAvatar
                className="h-[52px] w-14 overflow-visible"
                mode={loading ? "thinking" : displayResult?.riskLevel === "low" ? "success" : "review"}
                title="AI 智审助手"
                glow
              />
            </span>
            <div className="min-w-0">
              <h1 className="truncate text-[23px] font-bold leading-tight text-[#101b32]">
                {testMode ? "流程 AI 测试智审" : "流程 AI 智审"}
              </h1>
              <div className="mt-1.5 flex items-center gap-2 text-[13px] font-medium text-[#63718b]">
                <span className="h-2 w-2 rounded-full bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.72)]" />
                {loading ? "在线 · 正在生成审批建议" : displayResult ? "在线 · 审批建议已就绪" : "在线 · 随时可以发起预审"}
              </div>
              <div className="mt-1.5 max-w-[300px] truncate text-[12px] text-[#98a3b7]">
                {workflowName} · {nodeName}
              </div>
            </div>
          </div>
          <button
            type="button"
            className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-[#63718b] transition hover:bg-[#f2f5fa] hover:text-[#263753]"
            onClick={() => window.parent.postMessage({ type: "WEAVER_AI_REVIEW_CLOSE" }, targetOrigin)}
            title="关闭"
            aria-label="关闭智审面板"
          >
            <X className="h-5 w-5" />
          </button>
        </div>
      </header>

      <main className="flex min-h-0 flex-1 flex-col overflow-y-auto bg-white px-6 pb-5 pt-5">
        {message ? (
          <div className="mb-5 flex min-h-12 items-center gap-3 rounded-2xl border border-[#dff2e8] bg-[#f5fcf8] px-4 py-3 text-sm font-medium text-[#4a9b75]">
            <span className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-[#9ce1be] bg-white text-emerald-500">
              <Volume2 className="h-4 w-4" />
            </span>
            <span className="leading-6">{message}</span>
          </div>
        ) : null}
        {error ? (
          <div className="mb-5 flex items-start gap-3 rounded-xl border border-red-100 bg-red-50 px-4 py-3 text-sm text-red-700">
            <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0" />
            <span>{error}</span>
          </div>
        ) : null}

        {displayResult ? (
          <section className="space-y-4">
            <div className={`rounded-2xl border p-5 shadow-[0_10px_28px_rgba(56,83,130,0.06)] ${riskClass(displayResult.riskLevel)}`}>
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-2 text-base font-semibold">
                  {displayResult.riskLevel === "low" ? <CheckCircle2 className="h-5 w-5" /> : <AlertTriangle className="h-5 w-5" />}
                  {riskText(displayResult.riskLevel)}
                </div>
                <span className="rounded-full bg-white/80 px-3 py-1.5 text-xs font-semibold shadow-sm">
                  {decisionText(displayResult.decisionSuggestion)}
                </span>
              </div>
              <p className="mt-4 text-sm leading-7">{displayResult.summary}</p>
              {displayResult.suggestedOpinion ? (
                <div className="mt-4 rounded-xl bg-white/75 px-4 py-3 text-sm leading-6">
                  <span className="font-semibold">建议审批意见：</span>{displayResult.suggestedOpinion}
                </div>
              ) : null}
            </div>

            {displayResult.comparisonTables?.map((table, index) => (
              <ComparisonTableCard key={`${table.title}-${index}`} table={table} />
            ))}

            <section className="rounded-2xl border border-[#e7ecf4] bg-white shadow-[0_10px_28px_rgba(56,83,130,0.05)]">
              <div className="flex items-center gap-2 border-b border-[#eef2f7] px-4 py-3 text-sm font-semibold">
                <ListChecks className="h-5 w-5 text-[#6779ed]" />
                智审检查项
              </div>
              <div className="divide-y divide-slate-100">
                {displayResult.checks?.length ? (
                  displayResult.checks.map((item, index) => (
                    <div key={`${item.name}-${index}`} className="px-4 py-3.5">
                      <div className="flex items-center justify-between gap-3">
                        <span className="text-sm font-medium">{item.name}</span>
                        <span className={`rounded-full bg-slate-50 px-2.5 py-1 text-xs font-medium ${checkTextClass(item.status)}`}>
                          {checkText(item.status)}
                        </span>
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
              <section className="rounded-2xl border border-amber-100 bg-amber-50 px-4 py-4 text-sm text-amber-900">
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
          <EmptyReviewState loading={loading} />
        )}
      </main>

      <footer className="flex shrink-0 items-center justify-between gap-3 border-t border-[#eef2f7] bg-white px-6 py-4">
        <div className="flex min-w-0 items-center gap-2 text-sm text-slate-500">
          <Info className="h-5 w-5 shrink-0 text-slate-400" />
          <span>{testMode ? "测试结果独立保存，不影响正式智审" : record ? "结果仅作为审批参考" : "预审不会自动审批流程"}</span>
        </div>
        <button
          type="button"
          disabled={loading}
          onClick={() => void handleReview()}
          className="inline-flex h-12 shrink-0 items-center gap-2 rounded-full border border-[#8a87ff] bg-[linear-gradient(135deg,#8a75ff,#527df8)] px-6 text-base font-semibold text-white shadow-[0_10px_24px_rgba(99,102,241,0.24)] transition hover:-translate-y-0.5 hover:shadow-[0_14px_28px_rgba(99,102,241,0.3)] disabled:translate-y-0 disabled:opacity-60"
        >
          {loading ? <Loader2 className="h-5 w-5 animate-spin" /> : record ? <RefreshCw className="h-5 w-5" /> : <ClipboardCheck className="h-5 w-5" />}
          {testMode ? (record ? "重新测试" : "开始测试") : record ? "重新智审" : "立即智审"}
        </button>
      </footer>
    </div>
  );
}

function EmptyReviewState({ loading }: { loading: boolean }) {
  return (
    <section className="flex min-h-[500px] flex-1 flex-col items-center justify-center rounded-[20px] border border-[#e7ecf4] bg-white px-5 py-8 text-center shadow-[0_12px_32px_rgba(56,83,130,0.045)]">
      <div className="relative h-[200px] w-full max-w-[350px] overflow-hidden">
        <img
          src="/ai/weaver-assistant/review-empty-state.png"
          alt=""
          className={`h-full w-full object-cover object-center transition ${loading ? "animate-pulse opacity-70" : "opacity-90"}`}
        />
      </div>
      <h2 className="mt-1 text-[24px] font-bold text-[#10203b]">
        {loading ? "AI 正在生成智审结果" : "当前还没有 AI 智审结果"}
      </h2>
      <p className="mt-3 max-w-[390px] text-sm leading-6 text-[#7b8aa5]">
        {loading ? "正在结合当前表单、审批节点和智审规则进行检查，请稍等。" : "点击下方按钮，快速生成本节点的预审建议与风险提示。"}
      </p>
      <div className="mt-7 grid w-full max-w-[420px] grid-cols-3 divide-x divide-[#e8edf5]">
        <EmptyFeature icon={<ShieldCheck className="h-6 w-6" />} title="风险识别" description="发现潜在风险" />
        <EmptyFeature icon={<ListChecks className="h-6 w-6" />} title="审批建议" description="提供专业意见" />
        <EmptyFeature icon={<BarChart3 className="h-6 w-6" />} title="高效合规" description="辅助审慎决策" />
      </div>
    </section>
  );
}

function EmptyFeature({
  icon,
  title,
  description,
}: {
  icon: React.ReactNode;
  title: string;
  description: string;
}) {
  return (
    <div className="flex min-w-0 flex-col items-center px-2">
      <span className="inline-flex h-11 w-11 items-center justify-center rounded-xl bg-[linear-gradient(145deg,#6ebdff,#6470ee)] text-white shadow-[0_8px_18px_rgba(91,117,235,0.2)]">
        {icon}
      </span>
      <span className="mt-2 text-sm font-semibold text-[#18315b]">{title}</span>
      <span className="mt-1 text-[11px] text-[#7587a7]">{description}</span>
    </div>
  );
}

function readBaseInfoText(baseInfo: Record<string, unknown> | undefined, keys: string[]) {
  if (!baseInfo) return "";
  for (const key of keys) {
    const value = baseInfo[key];
    if (value !== null && value !== undefined && String(value).trim()) {
      return String(value).trim();
    }
  }
  return "";
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
    comparisonTables: Array.isArray(record.reviewResult?.comparisonTables) ? record.reviewResult.comparisonTables : [],
    confidence: record.confidence,
    canAutoApprove: record.canAutoApprove,
  };
}

function ComparisonTableCard({ table }: { table: WeaverReviewComparisonTable }) {
  const [open, setOpen] = useState(true);
  const [viewMode, setViewMode] = useState<"exception_first" | "reconciliation_order" | "exceptions_only">("exception_first");
  const failedCount = table.rows.filter((row) => row.status === "fail").length;
  const pendingCount = table.rows.filter((row) => row.status === "warning").length;
  const visibleRows = useMemo(() => {
    const indexed = table.rows.map((row, index) => ({ row, index }));
    if (viewMode === "exceptions_only") {
      return indexed.filter(({ row }) => row.status !== "pass").map(({ row }) => row);
    }
    if (viewMode === "exception_first") {
      const rank = { fail: 0, warning: 1, pass: 2 };
      indexed.sort((left, right) => rank[left.row.status] - rank[right.row.status] || left.index - right.index);
    }
    return indexed.map(({ row }) => row);
  }, [table.rows, viewMode]);

  return (
    <section className="overflow-hidden rounded-2xl border border-[#dfe8f5] bg-white shadow-[0_10px_28px_rgba(56,83,130,0.05)]">
      <button
        type="button"
        className="flex w-full items-center justify-between gap-3 px-4 py-3.5 text-left transition hover:bg-[#f8faff]"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
      >
        <span className="flex min-w-0 items-center gap-2">
          <TableProperties className="h-5 w-5 shrink-0 text-[#527df8]" />
          <span className="truncate text-sm font-semibold text-[#17243d]">{table.title}</span>
          <span className="shrink-0 rounded-full bg-[#eef4ff] px-2 py-0.5 text-[11px] font-medium text-[#5270c8]">
            {table.rows.length} 项
          </span>
        </span>
        <span className="flex shrink-0 items-center gap-2">
          <span className={`text-xs font-medium ${failedCount ? "text-red-600" : pendingCount ? "text-amber-600" : "text-teal-600"}`}>
            {failedCount || pendingCount
              ? [failedCount ? `${failedCount} 项异常` : "", pendingCount ? `${pendingCount} 项待核对` : ""].filter(Boolean).join(" · ")
              : "全部一致"}
          </span>
          <ChevronDown className={`h-4 w-4 text-slate-400 transition-transform ${open ? "rotate-180" : ""}`} />
        </span>
      </button>

      {open ? (
        <div className="border-t border-[#edf1f7]">
          <div className="grid grid-cols-2 gap-px bg-[#e8eef7] text-xs">
            <ComparisonMetric label="对账单号" value={table.reconciliationNumber || "-"} />
            <ComparisonMetric label="发票号码" value={table.invoiceNumbers.join("、") || "-"} />
            <ComparisonMetric label="发票价税合计" value={formatMoney(table.invoiceTotal)} />
            <ComparisonMetric label="对账单价税合计" value={formatMoney(table.reconciliationTotal)} />
          </div>

          <div className="flex flex-wrap items-center justify-between gap-2 border-t border-[#edf1f7] bg-white px-3 py-2.5">
            <div className="inline-flex rounded-lg border border-[#dfe7f3] bg-[#f7f9fc] p-0.5 text-[11px]">
              <ComparisonViewButton active={viewMode === "exception_first"} onClick={() => setViewMode("exception_first")}>
                异常优先
              </ComparisonViewButton>
              <ComparisonViewButton active={viewMode === "reconciliation_order"} onClick={() => setViewMode("reconciliation_order")}>
                对账顺序
              </ComparisonViewButton>
              <ComparisonViewButton active={viewMode === "exceptions_only"} onClick={() => setViewMode("exceptions_only")}>
                仅看问题
              </ComparisonViewButton>
            </div>
            <span className="text-[11px] text-[#7b899f]">
              显示 {visibleRows.length} / {table.rows.length} 项
            </span>
          </div>

          <div className="max-h-[360px] overflow-auto">
            <table className="min-w-[1390px] w-full border-collapse text-left text-xs">
              <thead className="sticky top-0 z-10 bg-[#f6f8fc] text-[#66758f] shadow-[0_1px_0_#e7ecf4]">
                <tr>
                  <th className="w-16 px-3 py-2.5 font-medium">序号</th>
                  <th className="min-w-[210px] px-3 py-2.5 font-medium">对账物料</th>
                  <th className="min-w-[250px] px-3 py-2.5 font-medium">发票商品（名称+规格）</th>
                  <th className="min-w-[110px] px-3 py-2.5 font-medium">单位</th>
                  <th className="min-w-[120px] px-3 py-2.5 font-medium">数量</th>
                  <th className="w-28 px-3 py-2.5 text-right font-medium">对账未税金额</th>
                  <th className="w-28 px-3 py-2.5 text-right font-medium">发票未税金额</th>
                  <th className="min-w-[120px] px-3 py-2.5 font-medium">税率</th>
                  <th className="w-24 px-3 py-2.5 font-medium">名称置信度</th>
                  <th className="w-20 px-3 py-2.5 font-medium">结果</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#edf1f6]">
                {visibleRows.map((row, index) => (
                  <tr
                    key={`${row.reconciliationSequence}-${row.invoiceName}-${row.reconciliationName}-${index}`}
                    className={row.status === "fail" ? "bg-red-50/70" : row.status === "warning" ? "bg-amber-50/60" : "bg-white"}
                    title={row.detail}
                  >
                    <td className="px-3 py-3 align-top font-medium tabular-nums text-[#52627c]">{row.reconciliationSequence || "-"}</td>
                    <td className={comparisonValueClass(row.nameStatus)} title={row.reconciliationName || ""}>
                      <div>{row.reconciliationName || "-"}</div>
                      {row.nameStatus === "warning" ? <NameReviewBadge /> : null}
                    </td>
                    <td className={comparisonValueClass(row.nameStatus)} title={formatInvoiceProduct(row)}>
                      <div>{row.invoiceName || "-"}</div>
                      {row.invoiceSpecification ? <div className="mt-1 text-[11px] font-normal text-[#71809a]">规格：{row.invoiceSpecification}</div> : null}
                      {row.matchMethod === "ai_semantic" ? (
                        <div className="mt-1 inline-flex rounded-full bg-blue-50 px-2 py-0.5 text-[10px] font-medium text-blue-700">
                          AI语义匹配
                        </div>
                      ) : null}
                      {row.nameStatus === "warning" ? <NameReviewBadge /> : null}
                    </td>
                    <td className="px-3 py-3 align-top"><PairComparisonCell left={row.reconciliationUnit} right={row.invoiceUnit} status={row.unitStatus} /></td>
                    <td className="px-3 py-3 align-top"><PairComparisonCell left={row.reconciliationQuantity} right={row.invoiceQuantity} status={row.quantityStatus} numeric /></td>
                    <td className={comparisonMoneyClass(row.amountStatus)}>{formatMoney(row.reconciliationAmount)}</td>
                    <td className={comparisonMoneyClass(row.amountStatus)}>{formatMoney(row.invoiceAmount)}</td>
                    <td className="px-3 py-3 align-top"><PairComparisonCell left={formatRates(row.reconciliationTaxRates)} right={formatRates(row.invoiceTaxRates)} status={row.taxRateStatus} /></td>
                    <td className="px-3 py-3 align-top tabular-nums text-[#52627c]">{formatSimilarity(row.similarity)}</td>
                    <td className="px-3 py-3 align-top">
                      <span className={`inline-flex rounded-full px-2 py-1 text-[11px] font-medium ${comparisonResultClass(row.status)}`}>
                        {row.status === "fail" ? "异常" : row.status === "warning" ? "待核对" : "一致"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="border-t border-[#edf1f6] bg-[#fbfcff] px-4 py-2.5 text-[11px] leading-5 text-[#7b899f]">
            名称完全归一化且其余数据一致时标记为“一致”；名称匹配度不足100%时标记为“待核对”。单位、数量、金额或税率不一致，以及完全无法匹配时标记为“异常”。悬停明细行可查看匹配依据。
          </div>
        </div>
      ) : null}
    </section>
  );
}

function ComparisonViewButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      className={`rounded-md px-2.5 py-1.5 transition ${active ? "bg-white font-medium text-[#315fc7] shadow-sm" : "text-[#687790] hover:text-[#315fc7]"}`}
      onClick={onClick}
    >
      {children}
    </button>
  );
}

function PairComparisonCell({
  left,
  right,
  status,
  numeric = false,
}: {
  left?: string | null;
  right?: string | null;
  status?: WeaverReviewComparisonRow["specificationStatus"];
  numeric?: boolean;
}) {
  const valueClass = status === "fail" ? "font-semibold text-red-700" : status === "unknown" ? "text-amber-700" : "text-[#263753]";
  return (
    <div className={`space-y-1 leading-4 ${valueClass} ${numeric ? "tabular-nums" : ""}`}>
      <div title={left || ""}><span className="mr-1 text-[10px] font-normal text-[#96a1b4]">对账</span>{left || "-"}</div>
      <div title={right || ""}><span className="mr-1 text-[10px] font-normal text-[#96a1b4]">发票</span>{right || "-"}</div>
    </div>
  );
}

function comparisonValueClass(status?: WeaverReviewComparisonRow["nameStatus"]) {
  return `px-3 py-3 align-top leading-5 ${status === "fail" ? "font-semibold text-red-700" : status === "warning" ? "font-medium text-amber-800" : "text-[#263753]"}`;
}

function NameReviewBadge() {
  return (
    <span className="mt-1 inline-flex rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-medium text-amber-800">
      名称待核对
    </span>
  );
}

function formatInvoiceProduct(row: WeaverReviewComparisonRow) {
  return [row.invoiceName, row.invoiceSpecification].filter(Boolean).join(" ") || "";
}

function comparisonMoneyClass(status?: WeaverReviewComparisonRow["amountStatus"]) {
  return `px-3 py-3 text-right align-top tabular-nums ${status === "fail" ? "font-semibold text-red-700" : "text-[#263753]"}`;
}

function comparisonResultClass(status: WeaverReviewComparisonRow["status"]) {
  if (status === "fail") return "bg-red-100 text-red-700";
  if (status === "warning") return "bg-amber-100 text-amber-700";
  return "bg-teal-50 text-teal-700";
}

function ComparisonMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 bg-[#fbfcff] px-4 py-3">
      <div className="text-[11px] text-[#8a97ad]">{label}</div>
      <div className="mt-1 truncate font-medium text-[#263753]" title={value}>{value}</div>
    </div>
  );
}

function formatMoney(value?: string | null) {
  if (!value) return "-";
  const number = Number(value);
  return Number.isFinite(number) ? number.toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : value;
}

function formatRates(rates?: string[]) {
  return rates?.length ? rates.map((value) => `${value}%`).join("/") : "-";
}

function formatSimilarity(value?: number | null) {
  return typeof value === "number" ? `${Math.round(value * 100)}%` : "-";
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
