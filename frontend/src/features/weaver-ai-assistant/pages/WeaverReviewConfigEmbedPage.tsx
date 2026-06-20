import { useCallback, useEffect, useMemo, useState } from "react";
import { CheckCircle2, Loader2, Plus, Save, ShieldCheck, Trash2 } from "lucide-react";

import {
  createWeaverReviewRule,
  deleteWeaverReviewRule,
  fetchWeaverReviewRules,
  updateWeaverReviewRule,
} from "../api";
import type { WeaverReviewRule, WeaverReviewRulePayload } from "../types";

interface ReviewRuleForm {
  id?: number;
  ruleTitle: string;
  ruleContent: string;
  toolInstructions: string;
  nodeId: string;
  nodeName: string;
  reviewerUserId: string;
  reviewerName: string;
  autoReviewMode: "suggestion" | "assist" | "auto";
  enabled: boolean;
  priority: number;
}

const emptyForm: ReviewRuleForm = {
  ruleTitle: "",
  ruleContent: "",
  toolInstructions: "",
  nodeId: "",
  nodeName: "",
  reviewerUserId: "",
  reviewerName: "",
  autoReviewMode: "suggestion",
  enabled: true,
  priority: 100,
};

export default function WeaverReviewConfigEmbedPage() {
  const query = useMemo(() => new URLSearchParams(window.location.search), []);
  const aiSign = query.get("ai_sign") || query.get("aiSign") || "";
  const env = query.get("env") || "default";
  const workflowId = query.get("workflow_id") || query.get("workflowId") || "";
  const workflowName = query.get("workflow_name") || query.get("workflowName") || "";
  const defaultNodeId = query.get("node_id") || query.get("nodeId") || "";
  const defaultNodeName = query.get("node_name") || query.get("nodeName") || "";
  const defaultReviewerUserId = query.get("reviewer_user_id") || query.get("reviewerUserId") || "";
  const defaultReviewerName = query.get("reviewer_name") || query.get("reviewerName") || "";

  const [rules, setRules] = useState<WeaverReviewRule[]>([]);
  const [form, setForm] = useState<ReviewRuleForm>({ ...emptyForm, nodeId: defaultNodeId, nodeName: defaultNodeName, reviewerUserId: defaultReviewerUserId, reviewerName: defaultReviewerName });
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const activeCount = rules.filter((rule) => rule.enabled).length;

  const loadRules = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await fetchWeaverReviewRules(aiSign, workflowId, { env });
      setRules(data);
      setMessage(data.length ? "已加载当前流程的 AI 智审规则。" : "当前流程还没有配置 AI 智审规则。");
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "智审规则加载失败");
    } finally {
      setLoading(false);
    }
  }, [aiSign, env, workflowId]);

  useEffect(() => {
    if (!aiSign || !workflowId) {
      setError("缺少 ai_sign 或 workflowId，无法加载智审规则。");
      return;
    }
    void loadRules();
  }, [aiSign, workflowId, loadRules]);

  async function handleSave() {
    if (!form.ruleTitle.trim() || !form.ruleContent.trim()) {
      setError("请填写规则标题和智审要求。");
      return;
    }
    setSaving(true);
    setError("");
    try {
      const payload = buildPayload(form, env, workflowId, workflowName);
      if (form.id) {
        await updateWeaverReviewRule(aiSign, form.id, payload);
      } else {
        await createWeaverReviewRule(aiSign, payload);
      }
      setForm({ ...emptyForm, nodeId: defaultNodeId, nodeName: defaultNodeName, reviewerUserId: defaultReviewerUserId, reviewerName: defaultReviewerName });
      setMessage("智审规则已保存，后续该流程预审会自动参考这些要求。");
      await loadRules();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "智审规则保存失败");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(rule: WeaverReviewRule) {
    if (!window.confirm(`确认删除智审规则“${rule.ruleTitle}”？`)) return;
    setSaving(true);
    setError("");
    try {
      await deleteWeaverReviewRule(aiSign, rule.id);
      if (form.id === rule.id) setForm(emptyForm);
      setMessage("智审规则已删除。");
      await loadRules();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "智审规则删除失败");
    } finally {
      setSaving(false);
    }
  }

  async function handleToggle(rule: WeaverReviewRule) {
    setSaving(true);
    setError("");
    try {
      await updateWeaverReviewRule(aiSign, rule.id, { enabled: !rule.enabled });
      await loadRules();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "智审规则状态更新失败");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="min-h-screen bg-slate-50 text-slate-950">
      <header className="border-b border-slate-200 bg-white px-5 py-4">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 text-base font-semibold">
              <ShieldCheck className="h-5 w-5 text-teal-600" />
              流程 AI 智审控制
            </div>
            <div className="mt-1 text-xs text-slate-500">
              环境：{env} · 流程 ID：{workflowId || "未识别"} {workflowName ? `· ${workflowName}` : ""}
            </div>
          </div>
          <button
            type="button"
            onClick={() => setForm({ ...emptyForm, nodeId: defaultNodeId, nodeName: defaultNodeName, reviewerUserId: defaultReviewerUserId, reviewerName: defaultReviewerName })}
            className="inline-flex h-9 items-center gap-2 rounded-md border border-slate-200 bg-white px-3 text-sm font-medium text-slate-700 transition hover:bg-slate-50"
          >
            <Plus className="h-4 w-4" />
            新建
          </button>
        </div>
      </header>

      <main className="grid gap-4 p-4 lg:grid-cols-[minmax(300px,380px)_1fr]">
        <section className="rounded-lg border border-slate-200 bg-white">
          <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3">
            <div className="text-sm font-semibold">已配置智审规则</div>
            <span className="rounded-md bg-teal-50 px-2 py-1 text-xs text-teal-700">启用 {activeCount} 条</span>
          </div>
          <div className="max-h-[calc(100vh-180px)] overflow-y-auto p-3">
            {loading ? (
              <div className="flex h-28 items-center justify-center text-sm text-slate-500">
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                正在加载
              </div>
            ) : rules.length ? (
              <div className="space-y-2">
                {rules.map((rule) => (
                  <button
                    type="button"
                    key={rule.id}
                    onClick={() => setForm(ruleToForm(rule))}
                    className={`w-full rounded-md border px-3 py-3 text-left transition ${
                      form.id === rule.id ? "border-teal-400 bg-teal-50" : "border-slate-200 bg-white hover:bg-slate-50"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-3">
                      <span className="line-clamp-1 text-sm font-semibold">{rule.ruleTitle}</span>
                      <span className={`shrink-0 text-xs ${rule.enabled ? "text-teal-700" : "text-slate-400"}`}>
                        {rule.enabled ? "启用" : "停用"}
                      </span>
                    </div>
                    <div className="mt-1 text-xs text-slate-400">
                      {rule.nodeName || rule.nodeId || "流程通用"} · {modeText(rule.autoReviewMode)}
                    </div>
                    <p className="mt-2 line-clamp-2 text-xs leading-5 text-slate-500">{rule.ruleContent}</p>
                  </button>
                ))}
              </div>
            ) : (
              <div className="rounded-md bg-slate-50 px-3 py-6 text-center text-sm text-slate-500">
                还没有智审规则，右侧新建一条即可。
              </div>
            )}
          </div>
        </section>

        <section className="rounded-lg border border-slate-200 bg-white">
          <div className="border-b border-slate-200 px-4 py-3">
            <div className="text-sm font-semibold">{form.id ? "编辑智审规则" : "新建智审规则"}</div>
            <p className="mt-1 text-xs text-slate-500">
              可以配置流程通用规则、节点规则或审批人个人口径。AI 只会生成预审建议，不会直接审批。
            </p>
          </div>

          <div className="space-y-4 p-4">
            {message ? (
              <div className="flex items-center gap-2 rounded-md bg-teal-50 px-3 py-2 text-xs text-teal-800">
                <CheckCircle2 className="h-4 w-4" />
                {message}
              </div>
            ) : null}
            {error ? <div className="rounded-md bg-red-50 px-3 py-2 text-xs text-red-700">{error}</div> : null}

            <div className="grid gap-3 md:grid-cols-2">
              <Input label="节点 ID" value={form.nodeId} placeholder="留空表示流程通用" onChange={(value) => setForm((current) => ({ ...current, nodeId: value }))} />
              <Input label="节点名称" value={form.nodeName} placeholder="例如：部门经理审批" onChange={(value) => setForm((current) => ({ ...current, nodeName: value }))} />
              <Input label="审批人 ID" value={form.reviewerUserId} placeholder="留空表示节点通用" onChange={(value) => setForm((current) => ({ ...current, reviewerUserId: value }))} />
              <Input label="审批人姓名" value={form.reviewerName} placeholder="例如：张三" onChange={(value) => setForm((current) => ({ ...current, reviewerName: value }))} />
            </div>

            <Input label="规则标题" value={form.ruleTitle} placeholder="例如：部门经理请假审批口径" onChange={(value) => setForm((current) => ({ ...current, ruleTitle: value }))} />

            <label className="block">
              <span className="text-xs font-medium text-slate-600">智审要求 / 审批口径</span>
              <textarea
                value={form.ruleContent}
                onChange={(event) => setForm((current) => ({ ...current, ruleContent: event.target.value }))}
                className="mt-1 h-40 w-full resize-none rounded-md border border-slate-200 px-3 py-2 text-sm leading-6 outline-none transition focus:border-teal-500 focus:ring-2 focus:ring-teal-500/15"
                placeholder="例如：重点检查附件是否齐全、请假原因是否充分、日期是否与排班冲突；病假需医院证明；连续超过 3 天需上级审批意见。"
              />
            </label>

            <label className="block">
              <span className="text-xs font-medium text-slate-600">工具 / 资料说明</span>
              <textarea
                value={form.toolInstructions}
                onChange={(event) => setForm((current) => ({ ...current, toolInstructions: event.target.value }))}
                className="mt-1 h-24 w-full resize-none rounded-md border border-slate-200 px-3 py-2 text-sm leading-6 outline-none transition focus:border-teal-500 focus:ring-2 focus:ring-teal-500/15"
                placeholder="例如：后续可查询考勤、预算、合同、历史同类单据；查不到数据时必须提示人工确认。"
              />
            </label>

            <div className="grid gap-3 md:grid-cols-[180px_180px_1fr]">
              <label className="block">
                <span className="text-xs font-medium text-slate-600">模式</span>
                <select
                  value={form.autoReviewMode}
                  onChange={(event) => setForm((current) => ({ ...current, autoReviewMode: event.target.value as ReviewRuleForm["autoReviewMode"] }))}
                  className="mt-1 h-10 w-full rounded-md border border-slate-200 px-3 text-sm outline-none transition focus:border-teal-500 focus:ring-2 focus:ring-teal-500/15"
                >
                  <option value="suggestion">只给建议</option>
                  <option value="assist">辅助审批</option>
                  <option value="auto">允许低风险替审</option>
                </select>
              </label>
              <Input label="优先级" type="number" value={String(form.priority)} onChange={(value) => setForm((current) => ({ ...current, priority: Number(value) || 100 }))} />
              <label className="mt-6 flex h-10 items-center gap-2 text-sm text-slate-700">
                <input
                  type="checkbox"
                  checked={form.enabled}
                  onChange={(event) => setForm((current) => ({ ...current, enabled: event.target.checked }))}
                  className="h-4 w-4 accent-teal-700"
                />
                启用这条智审规则
              </label>
            </div>

            <div className="flex flex-wrap justify-end gap-2 border-t border-slate-100 pt-4">
              {form.id ? (
                <>
                  <button
                    type="button"
                    disabled={saving}
                    onClick={() => {
                      const rule = rules.find((item) => item.id === form.id);
                      if (rule) void handleToggle(rule);
                    }}
                    className="inline-flex h-10 items-center rounded-md border border-slate-200 bg-white px-3 text-sm font-medium text-slate-700 transition hover:bg-slate-50 disabled:opacity-60"
                  >
                    {rules.find((item) => item.id === form.id)?.enabled ? "停用" : "启用"}
                  </button>
                  <button
                    type="button"
                    disabled={saving}
                    onClick={() => {
                      const rule = rules.find((item) => item.id === form.id);
                      if (rule) void handleDelete(rule);
                    }}
                    className="inline-flex h-10 items-center gap-2 rounded-md border border-red-100 bg-red-50 px-3 text-sm font-medium text-red-700 transition hover:bg-red-100 disabled:opacity-60"
                  >
                    <Trash2 className="h-4 w-4" />
                    删除
                  </button>
                </>
              ) : null}
              <button
                type="button"
                disabled={saving}
                onClick={() => void handleSave()}
                className="inline-flex h-10 items-center gap-2 rounded-md bg-teal-700 px-4 text-sm font-medium text-white transition hover:bg-teal-800 disabled:opacity-60"
              >
                {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                保存规则
              </button>
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}

function Input({
  label,
  value,
  onChange,
  placeholder,
  type = "text",
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  type?: string;
}) {
  return (
    <label className="block">
      <span className="text-xs font-medium text-slate-600">{label}</span>
      <input
        type={type}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="mt-1 h-10 w-full rounded-md border border-slate-200 px-3 text-sm outline-none transition focus:border-teal-500 focus:ring-2 focus:ring-teal-500/15"
        placeholder={placeholder}
      />
    </label>
  );
}

function buildPayload(
  form: ReviewRuleForm,
  env: string,
  workflowId: string,
  workflowName: string,
): WeaverReviewRulePayload {
  return {
    env,
    workflowId,
    workflowName: workflowName || null,
    nodeId: form.nodeId.trim() || null,
    nodeName: form.nodeName.trim() || null,
    reviewerUserId: form.reviewerUserId.trim() || null,
    reviewerName: form.reviewerName.trim() || null,
    ruleTitle: form.ruleTitle.trim(),
    ruleContent: form.ruleContent.trim(),
    toolConfig: {
      toolInstructions: form.toolInstructions.trim(),
    },
    autoReviewMode: form.autoReviewMode,
    enabled: form.enabled,
    priority: form.priority,
  };
}

function ruleToForm(rule: WeaverReviewRule): ReviewRuleForm {
  const toolConfig = rule.toolConfig || {};
  return {
    id: rule.id,
    ruleTitle: rule.ruleTitle,
    ruleContent: rule.ruleContent,
    toolInstructions: String(toolConfig.toolInstructions || ""),
    nodeId: rule.nodeId || "",
    nodeName: rule.nodeName || "",
    reviewerUserId: rule.reviewerUserId || "",
    reviewerName: rule.reviewerName || "",
    autoReviewMode: rule.autoReviewMode,
    enabled: rule.enabled,
    priority: rule.priority,
  };
}

function modeText(value: WeaverReviewRule["autoReviewMode"]) {
  const map = {
    suggestion: "只给建议",
    assist: "辅助审批",
    auto: "允许低风险替审",
  };
  return map[value];
}
