import { useCallback, useEffect, useMemo, useState } from "react";
import { CheckCircle2, Loader2, Plus, Save, Trash2, Wand2 } from "lucide-react";

import {
  createWeaverWorkflowRule,
  deleteWeaverWorkflowRule,
  fetchWeaverWorkflowRules,
  updateWeaverWorkflowRule,
} from "../api";
import type { WeaverWorkflowRule, WeaverWorkflowRulePayload } from "../types";

interface RuleFormState {
  id?: number;
  ruleTitle: string;
  ruleContent: string;
  toolInstructions: string;
  enabled: boolean;
  priority: number;
}

const emptyForm: RuleFormState = {
  ruleTitle: "",
  ruleContent: "",
  toolInstructions: "",
  enabled: true,
  priority: 100,
};

export default function WeaverWorkflowConfigEmbedPage() {
  const query = useMemo(() => new URLSearchParams(window.location.search), []);
  const aiSign = query.get("ai_sign") || query.get("aiSign") || "";
  const env = query.get("env") || "default";
  const workflowId = query.get("workflow_id") || query.get("workflowId") || "";
  const workflowName = query.get("workflow_name") || query.get("workflowName") || "";

  const [rules, setRules] = useState<WeaverWorkflowRule[]>([]);
  const [form, setForm] = useState<RuleFormState>(emptyForm);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const activeRules = rules.filter((rule) => rule.enabled);

  const loadRules = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await fetchWeaverWorkflowRules(aiSign, workflowId, env);
      setRules(data);
      setMessage(data.length ? "已加载当前流程的 AI 填报规则。" : "当前流程还没有配置特殊填报规则。");
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "规则加载失败");
    } finally {
      setLoading(false);
    }
  }, [aiSign, env, workflowId]);

  useEffect(() => {
    if (!aiSign || !workflowId) {
      setError("缺少 ai_sign 或 workflowId，无法加载流程规则。");
      return;
    }
    void loadRules();
  }, [aiSign, workflowId, env, loadRules]);

  async function handleSave() {
    if (!form.ruleTitle.trim() || !form.ruleContent.trim()) {
      setError("请填写规则标题和具体要求。");
      return;
    }
    setSaving(true);
    setError("");
    try {
      const payload = buildPayload(form, env, workflowId, workflowName);
      if (form.id) {
        await updateWeaverWorkflowRule(aiSign, form.id, payload);
      } else {
        await createWeaverWorkflowRule(aiSign, payload);
      }
      setForm(emptyForm);
      setMessage("规则已保存，后续该流程的 AI 填单会自动参考这些要求。");
      await loadRules();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "规则保存失败");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(rule: WeaverWorkflowRule) {
    const confirmed = window.confirm(`确认删除规则“${rule.ruleTitle}”？`);
    if (!confirmed) return;
    setSaving(true);
    setError("");
    try {
      await deleteWeaverWorkflowRule(aiSign, rule.id);
      if (form.id === rule.id) setForm(emptyForm);
      setMessage("规则已删除。");
      await loadRules();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "规则删除失败");
    } finally {
      setSaving(false);
    }
  }

  async function handleToggle(rule: WeaverWorkflowRule) {
    setSaving(true);
    setError("");
    try {
      await updateWeaverWorkflowRule(aiSign, rule.id, { enabled: !rule.enabled });
      await loadRules();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "规则状态更新失败");
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
              <Wand2 className="h-5 w-5 text-teal-600" />
              流程 AI 填报控制
            </div>
            <div className="mt-1 text-xs text-slate-500">
              环境：{env} · 流程 ID：{workflowId || "未识别"} {workflowName ? `· ${workflowName}` : ""}
            </div>
          </div>
          <button
            type="button"
            onClick={() => setForm(emptyForm)}
            className="inline-flex h-9 items-center gap-2 rounded-md border border-slate-200 bg-white px-3 text-sm font-medium text-slate-700 transition hover:bg-slate-50"
          >
            <Plus className="h-4 w-4" />
            新建
          </button>
        </div>
      </header>

      <main className="grid gap-4 p-4 lg:grid-cols-[minmax(280px,360px)_1fr]">
        <section className="rounded-lg border border-slate-200 bg-white">
          <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3">
            <div className="text-sm font-semibold">已配置规则</div>
            <span className="rounded-md bg-teal-50 px-2 py-1 text-xs text-teal-700">启用 {activeRules.length} 条</span>
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
                    <p className="mt-2 line-clamp-2 text-xs leading-5 text-slate-500">{rule.ruleContent}</p>
                  </button>
                ))}
              </div>
            ) : (
              <div className="rounded-md bg-slate-50 px-3 py-6 text-center text-sm text-slate-500">
                还没有规则，右侧新建一条即可。
              </div>
            )}
          </div>
        </section>

        <section className="rounded-lg border border-slate-200 bg-white">
          <div className="border-b border-slate-200 px-4 py-3">
            <div className="text-sm font-semibold">{form.id ? "编辑规则" : "新建规则"}</div>
            <p className="mt-1 text-xs text-slate-500">
              这里写的是当前流程专属填法，会在 AI 聊天和生成写入动作时自动生效。
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

            <label className="block">
              <span className="text-xs font-medium text-slate-600">规则标题</span>
              <input
                value={form.ruleTitle}
                onChange={(event) => setForm((current) => ({ ...current, ruleTitle: event.target.value }))}
                className="mt-1 h-10 w-full rounded-md border border-slate-200 px-3 text-sm outline-none transition focus:border-teal-500 focus:ring-2 focus:ring-teal-500/15"
                placeholder="例如：请假申请填写规范"
              />
            </label>

            <label className="block">
              <span className="text-xs font-medium text-slate-600">特殊填写要求 / 提示词</span>
              <textarea
                value={form.ruleContent}
                onChange={(event) => setForm((current) => ({ ...current, ruleContent: event.target.value }))}
                className="mt-1 h-40 w-full resize-none rounded-md border border-slate-200 px-3 py-2 text-sm leading-6 outline-none transition focus:border-teal-500 focus:ring-2 focus:ring-teal-500/15"
                placeholder="例如：请假原因必须说明具体事由；病假需提醒上传医院证明；请假天数由系统自动计算，不允许 AI 写入。"
              />
            </label>

            <label className="block">
              <span className="text-xs font-medium text-slate-600">工具 / 技能说明</span>
              <textarea
                value={form.toolInstructions}
                onChange={(event) => setForm((current) => ({ ...current, toolInstructions: event.target.value }))}
                className="mt-1 h-28 w-full resize-none rounded-md border border-slate-200 px-3 py-2 text-sm leading-6 outline-none transition focus:border-teal-500 focus:ring-2 focus:ring-teal-500/15"
                placeholder="例如：如需合同信息，后续应调用合同查询工具获取合同号、供应商和付款阶段；未取到数据时必须追问用户。"
              />
            </label>

            <div className="grid gap-3 sm:grid-cols-[160px_1fr]">
              <label className="block">
                <span className="text-xs font-medium text-slate-600">优先级</span>
                <input
                  type="number"
                  value={form.priority}
                  onChange={(event) => setForm((current) => ({ ...current, priority: Number(event.target.value) || 100 }))}
                  className="mt-1 h-10 w-full rounded-md border border-slate-200 px-3 text-sm outline-none transition focus:border-teal-500 focus:ring-2 focus:ring-teal-500/15"
                />
              </label>
              <label className="mt-6 flex h-10 items-center gap-2 text-sm text-slate-700">
                <input
                  type="checkbox"
                  checked={form.enabled}
                  onChange={(event) => setForm((current) => ({ ...current, enabled: event.target.checked }))}
                  className="h-4 w-4 accent-teal-700"
                />
                启用这条规则
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

function buildPayload(
  form: RuleFormState,
  env: string,
  workflowId: string,
  workflowName: string,
): WeaverWorkflowRulePayload {
  return {
    env,
    workflowId,
    workflowName: workflowName || null,
    ruleTitle: form.ruleTitle.trim(),
    ruleContent: form.ruleContent.trim(),
    skillConfig: {
      toolInstructions: form.toolInstructions.trim(),
    },
    enabled: form.enabled,
    priority: form.priority,
  };
}

function ruleToForm(rule: WeaverWorkflowRule): RuleFormState {
  const skillConfig = rule.skillConfig || {};
  return {
    id: rule.id,
    ruleTitle: rule.ruleTitle,
    ruleContent: rule.ruleContent,
    toolInstructions: String(skillConfig.toolInstructions || ""),
    enabled: rule.enabled,
    priority: rule.priority,
  };
}
