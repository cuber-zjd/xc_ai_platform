import { useMemo, useState } from "react";
import type { ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot, Bug, CalendarClock, ChevronDown, Clock3, ExternalLink, FileText, Loader2, Pencil, Play, Plus, RefreshCw, Send, Trash2, UserRound, X } from "lucide-react";
import ReactMarkdown from "react-markdown";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";

import { insightApi, type InsightFeishuBriefGenerationRules, type InsightFeishuBriefOccurrenceOverride, type InsightFeishuBriefPlanCreate, type InsightFeishuBriefPlanRead, type InsightFeishuBriefRecipient } from "../api";
import { DemoCard } from "../components/DemoPrimitives";
import { FeishuRecipientPickerDialog } from "../components/FeishuRecipientPickerDialog";
import { InsightSelect } from "../components/InsightSelect";
import { PageContainer } from "../layout/PageContainer";

const weekdayOptions = [
    { value: "0", label: "周一" },
    { value: "1", label: "周二" },
    { value: "2", label: "周三" },
    { value: "3", label: "周四" },
    { value: "4", label: "周五" },
    { value: "5", label: "周六" },
    { value: "6", label: "周日" },
];

const departmentOptions = ["销售", "市场", "研发", "采购", "供应链", "经营管理"];
const excludedOptions = [
    "广告软文", "榜单", "招聘", "通用专利", "旧闻", "重复事件",
    "植物油动态", "普通大豆行情", "泛食品资讯", "宽泛玉米行情",
];
const sectionNames = ["政策", "竞对", "客户", "技术", "原料"] as const;

const defaultGenerationRules: InsightFeishuBriefGenerationRules = {
    focus_topics: ["客户动态", "竞对变化", "政策监管", "技术与产品", "原料行情", "消费趋势"],
    value_departments: [...departmentOptions],
    excluded_content: excludedOptions.slice(0, 6),
    primary_score: 78,
    supporting_score: 68,
    section_priorities: { 政策: 3, 竞对: 3, 客户: 5, 技术: 3, 原料: 4 },
    minimum_citations: 7,
    maximum_citations: 25,
    writing_depth: "balanced",
    include_business_insight: true,
};

function generationRulesForCompany(companyName?: string | null): InsightFeishuBriefGenerationRules {
    const focus_topics = companyName?.includes("健源")
        ? ["果葡糖浆", "麦芽糖浆", "淀粉糖", "葡萄糖", "功能糖与糖醇", "玉米加工糖类应用", "糖类竞对", "糖类下游客户"]
        : companyName?.includes("御馨")
            ? ["大豆蛋白", "植物蛋白", "蛋白类竞对", "下游蛋白应用", "蛋白新品与技术", "非转基因大豆", "替代蛋白"]
            : [...defaultGenerationRules.focus_topics];
    return {
        ...defaultGenerationRules,
        focus_topics,
        value_departments: [...defaultGenerationRules.value_departments],
        excluded_content: companyName?.includes("御馨")
            ? [...defaultGenerationRules.excluded_content, "植物油动态", "普通大豆行情"]
            : companyName?.includes("健源")
                ? [...defaultGenerationRules.excluded_content, "泛食品资讯", "宽泛玉米行情"]
                : [...defaultGenerationRules.excluded_content],
        section_priorities: { ...defaultGenerationRules.section_priorities },
    };
}

const emptyForm: InsightFeishuBriefPlanCreate = {
    plan_name: "",
    sys_company_id: null,
    schedule_frequency: "weekly",
    weekday: 0,
    day_of_month: 1,
    time_of_day: "09:00",
    review_weekday: 0,
    review_time: "10:30",
    release_weekday: 1,
    release_time: "15:00",
    material_days: 7,
    max_materials: 200,
    generation_strategy: "multi_agent_ensemble",
    generation_rules: generationRulesForCompany(),
    workflow_config: { max_revision_rounds: 2, research_sections: [...sectionNames] },
    prompt_config: { planning: "", research: "", writing: "", reviewing: "", revision: "" },
    material_scope: { mode: "rolling_days", rolling_days: 7, start_weekday: 0, end_weekday: 6, filters: {} },
    template_markdown: `管理层情报简报｜{{素材周期}}｜生成时间：{{生成日期}}

适用公司：{{所属公司}}｜数据来源：情报管理多维表格·情报表｜原始候选 {{素材数量}} 条

---

# 一、总览
# 政策
# 竞对
# 客户
# 技术
# 原料
# 二、重点情报导读`,
    recipients: [],
    afternoon_recipients: [],
    afternoon_push_time: "15:00",
    status: "active",
};

export function FeishuBriefPage() {
    const queryClient = useQueryClient();
    const [page, setPage] = useState(1);
    const [dialogOpen, setDialogOpen] = useState(false);
    const [editing, setEditing] = useState<InsightFeishuBriefPlanRead | null>(null);
    const [form, setForm] = useState<InsightFeishuBriefPlanCreate>(emptyForm);
    const [promptExpanded, setPromptExpanded] = useState(false);
    const [editorSection, setEditorSection] = useState<"plan" | "content" | "advanced" | "debug">("plan");
    const [recipientPickerStage, setRecipientPickerStage] = useState<"morning" | "afternoon" | null>(null);
    const [selectedRunId, setSelectedRunId] = useState<number | null>(null);
    const [occurrencePlan, setOccurrencePlan] = useState<InsightFeishuBriefPlanRead | null>(null);
    const [occurrenceForm, setOccurrenceForm] = useState<InsightFeishuBriefOccurrenceOverride>(() => defaultOccurrenceForm());
    const optionsQuery = useQuery({ queryKey: ["insight-feishu-brief-options"], queryFn: insightApi.getFeishuBriefOptions });
    const plansQuery = useQuery({
        queryKey: ["insight-feishu-brief-plans", page],
        queryFn: () => insightApi.listFeishuBriefPlans({ page, size: 20 }),
    });
    const runsQuery = useQuery({
        queryKey: ["insight-feishu-brief-runs"],
        queryFn: () => insightApi.listFeishuBriefRuns({ page: 1, size: 20 }),
    });
    const stagesQuery = useQuery({
        queryKey: ["insight-feishu-brief-stages", selectedRunId],
        queryFn: () => insightApi.listFeishuBriefAgentStages(selectedRunId as number),
        enabled: selectedRunId !== null,
    });
    const companiesQuery = useQuery({ queryKey: ["system-companies"], queryFn: insightApi.listSystemCompanies });
    const options = optionsQuery.data;
    const plans = plansQuery.data?.items ?? [];
    const runs = runsQuery.data?.items ?? [];
    const companyOptions = useMemo(
        () => [
            { value: "", label: "全部业务公司" },
            ...(companiesQuery.data ?? []).map((item) => ({ value: String(item.id), label: item.name })),
        ],
        [companiesQuery.data],
    );

    const refresh = () => {
        void queryClient.invalidateQueries({ queryKey: ["insight-feishu-brief-options"] });
        void queryClient.invalidateQueries({ queryKey: ["insight-feishu-brief-plans"] });
        void queryClient.invalidateQueries({ queryKey: ["insight-feishu-brief-runs"] });
    };
    const resetPlanEditor = () => {
        setEditing(null);
        setForm({ ...emptyForm, generation_rules: generationRulesForCompany() });
        setPromptExpanded(false);
        setEditorSection("plan");
        setRecipientPickerStage(null);
    };
    const saveMutation = useMutation({
        mutationFn: () => editing
            ? insightApi.updateFeishuBriefPlan(editing.id, form)
            : insightApi.createFeishuBriefPlan(form),
        onSuccess: () => {
            toast.success(editing ? "简报计划已更新" : "简报计划已创建");
            setDialogOpen(false);
            resetPlanEditor();
            refresh();
        },
        onError: () => toast.error("保存失败，请检查填写内容"),
    });
    const runMutation = useMutation({
        mutationFn: (planId: number) => insightApi.runFeishuBriefPlan(planId),
        onSuccess: (result) => {
            toast.success(result.message);
            refresh();
        },
        onError: () => toast.error("生成失败，请查看执行记录"),
    });
    const deleteMutation = useMutation({
        mutationFn: insightApi.deleteFeishuBriefPlan,
        onSuccess: () => {
            toast.success("简报计划已删除");
            refresh();
        },
        onError: () => toast.error("删除失败"),
    });
    const debugMutation = useMutation({
        mutationFn: () => {
            if (!editing) throw new Error("请先保存计划后再生成调试稿");
            return insightApi.debugFeishuBriefPlan(editing.id, form);
        },
        onSuccess: (result) => {
            toast.success("调试稿已生成，未向任何接收人推送");
            refresh();
            if (result.run.document_url) window.open(result.run.document_url, "_blank", "noopener,noreferrer");
        },
        onError: () => toast.error("调试稿生成失败，请查看执行记录"),
    });
    const regenerateMutation = useMutation({
        mutationFn: (runId: number) => insightApi.regenerateFeishuBriefRun(runId),
        onSuccess: (result) => {
            toast.success(result.message);
            refresh();
        },
        onError: () => toast.error("原文档重新生成失败"),
    });
    const occurrenceMutation = useMutation({
        mutationFn: () => {
            if (!occurrencePlan) throw new Error("未选择计划");
            const periodKey = occurrenceForm.generation_scheduled_at.slice(0, 10);
            return insightApi.upsertFeishuBriefOccurrence(occurrencePlan.id, periodKey, { ...occurrenceForm, period_key: periodKey });
        },
        onSuccess: () => {
            toast.success("本期临时时间和素材范围已保存，下期自动恢复常规计划");
            setOccurrencePlan(null);
            refresh();
        },
        onError: () => toast.error("本期临时调整保存失败"),
    });

    const openEdit = (item: InsightFeishuBriefPlanRead) => {
        setEditing(item);
        setEditorSection("plan");
        setForm({
            plan_name: item.plan_name,
            sys_company_id: item.sys_company_id,
            schedule_frequency: item.schedule_frequency,
            weekday: item.weekday,
            day_of_month: item.day_of_month,
            time_of_day: item.time_of_day,
            review_weekday: item.review_weekday,
            review_time: item.review_time,
            release_weekday: item.release_weekday,
            release_time: item.release_time,
            material_days: item.material_days,
            max_materials: item.max_materials,
            generation_strategy: item.schedule_frequency === "weekly" ? "multi_agent_ensemble" : item.generation_strategy,
            generation_rules: item.generation_rules,
            workflow_config: item.workflow_config,
            prompt_config: item.prompt_config,
            material_scope: item.material_scope,
            template_markdown: item.template_markdown,
            recipients: item.recipients,
            afternoon_recipients: item.afternoon_recipients,
            afternoon_push_time: item.afternoon_push_time,
            status: item.status,
        });
        setDialogOpen(true);
    };

    return (
        <PageContainer className="flex h-full min-h-0 flex-col gap-3 overflow-hidden">
            <DemoCard className="shrink-0 p-3">
                <div className="flex flex-wrap items-center justify-between gap-3">
                    <div className="flex min-w-0 items-center gap-3">
                        <div className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-cyan-50 text-cyan-700">
                            <Bot className="size-5" />
                        </div>
                        <div className="min-w-0">
                            <div className="flex flex-wrap items-center gap-2">
                                <span className="text-sm font-black text-slate-900">飞书简报机器人</span>
                                <Badge variant="outline" className={options?.configured ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-amber-200 bg-amber-50 text-amber-700"}>
                                    {options?.configured ? "配置完成" : "等待配置"}
                                </Badge>
                            </div>
                            <div className="mt-0.5 truncate text-xs font-semibold text-slate-500">
                                {options?.bot_name || "市场洞察报告机器人"} · 独立生成日报、周报和月报，不进入报告中心
                            </div>
                        </div>
                    </div>
                    <div className="flex items-center gap-2">
                        <Button variant="outline" size="icon" className="size-9 rounded-lg" onClick={refresh} title="刷新">
                            <RefreshCw className="size-4" />
                        </Button>
                        <Button className="h-9 rounded-lg bg-blue-600 hover:bg-blue-700" onClick={() => { resetPlanEditor(); setDialogOpen(true); }}>
                            <Plus className="size-4" />
                            新建计划
                        </Button>
                    </div>
                </div>
                {!options?.configured ? (
                    <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs font-semibold leading-5 text-amber-800">
                        {(options?.warnings ?? ["请在后端 .env 中补充独立机器人应用、云文档文件夹和接收人配置。"]).join("；")}
                    </div>
                ) : null}
            </DemoCard>

            <div className="grid min-h-0 flex-1 grid-cols-1 gap-3 xl:grid-cols-[minmax(0,1.15fr)_minmax(360px,0.85fr)]">
                <DemoCard className="flex min-h-0 flex-col overflow-hidden p-0">
                    <div className="flex shrink-0 items-center justify-between border-b border-slate-100 px-4 py-3">
                        <div className="text-sm font-black text-slate-900">简报计划</div>
                        <span className="text-xs font-semibold text-slate-500">{plansQuery.data?.total ?? 0} 个</span>
                    </div>
                    <div className="min-h-0 flex-1 overflow-auto">
                        <Table>
                            <TableHeader className="sticky top-0 z-10 bg-white">
                                <TableRow>
                                    <TableHead>计划</TableHead>
                                    <TableHead>周期</TableHead>
                                    <TableHead>下次执行</TableHead>
                                    <TableHead>上次结果</TableHead>
                                    <TableHead className="w-[150px] text-right">操作</TableHead>
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {plans.map((item) => (
                                    <TableRow key={item.id}>
                                        <TableCell>
                                            <div className="font-bold text-slate-900">{item.plan_name}</div>
                                            <div className="mt-1 text-xs text-slate-500">{item.sys_company_name || "全部业务公司"}</div>
                                        </TableCell>
                                        <TableCell className="text-sm font-semibold text-slate-700">
                                            <div>{scheduleLabel(item)} {item.time_of_day}</div>
                                            <div className="mt-1 text-xs font-medium text-slate-500">
                                                素材近 {item.material_days} 天
                                                {item.schedule_frequency === "monthly" ? ` · ${strategyLabel(item.generation_strategy)}` : ""}
                                                {" "}· 上午 {item.recipients.length} 人 · 下午 {item.afternoon_recipients.length} 人
                                            </div>
                                        </TableCell>
                                        <TableCell className="text-xs font-semibold text-slate-600">{formatDateTime(item.next_run_time)}</TableCell>
                                        <TableCell>
                                            <Badge variant="outline" className={statusClass(item.last_status)}>{statusLabel(item.last_status)}</Badge>
                                        </TableCell>
                                        <TableCell>
                                            <div className="flex justify-end gap-1">
                                                <Button variant="ghost" size="icon" className="size-8" title="立即正式生成" disabled={!item.can_edit || !options?.configured || runMutation.isPending} onClick={() => runMutation.mutate(item.id)}>
                                                    {runMutation.isPending && runMutation.variables === item.id ? <Loader2 className="size-4 animate-spin" /> : <Play className="size-4" />}
                                                </Button>
                                                <Button variant="ghost" size="icon" className="size-8" title="本期临时调整" disabled={!item.can_edit || item.schedule_frequency !== "weekly"} onClick={() => { setOccurrencePlan(item); setOccurrenceForm(defaultOccurrenceForm(item)); }}><CalendarClock className="size-4" /></Button>
                                                <Button variant="ghost" size="icon" className="size-8" title={item.can_edit ? "编辑" : "只读查看"} onClick={() => openEdit(item)}><Pencil className="size-4" /></Button>
                                                <Button variant="ghost" size="icon" className="size-8 text-rose-600" title="删除" disabled={!item.can_edit} onClick={() => deleteMutation.mutate(item.id)}><Trash2 className="size-4" /></Button>
                                            </div>
                                        </TableCell>
                                    </TableRow>
                                ))}
                                {!plans.length ? (
                                    <TableRow><TableCell colSpan={5} className="h-40 text-center text-sm font-semibold text-slate-400">暂无简报计划</TableCell></TableRow>
                                ) : null}
                            </TableBody>
                        </Table>
                    </div>
                    <div className="flex shrink-0 items-center justify-end gap-2 border-t border-slate-100 px-3 py-2">
                        <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage((value) => value - 1)}>上一页</Button>
                        <span className="text-xs font-semibold text-slate-500">第 {page} 页</span>
                        <Button variant="outline" size="sm" disabled={plans.length < 20} onClick={() => setPage((value) => value + 1)}>下一页</Button>
                    </div>
                </DemoCard>

                <div className="grid min-h-0 grid-rows-[auto_minmax(0,1fr)] gap-3">
                    <DemoCard className="p-4">
                        <div className="flex items-center gap-2 text-sm font-black text-slate-900"><FileText className="size-4 text-blue-600" />固定报告格式</div>
                        <div className="mt-3 grid grid-cols-2 gap-2">
                            {(options?.fixed_format ?? []).map((item) => (
                                <div key={item} className="rounded-lg border border-slate-100 bg-slate-50 px-3 py-2 text-xs font-bold text-slate-700">{item}</div>
                            ))}
                        </div>
                    </DemoCard>
                    <DemoCard className="flex min-h-0 flex-col overflow-hidden p-0">
                        <div className="shrink-0 border-b border-slate-100 px-4 py-3 text-sm font-black text-slate-900">最近执行</div>
                        <div className="min-h-0 flex-1 overflow-auto p-3">
                            <div className="space-y-2">
                                {runs.map((item) => (
                                    <div key={item.id} className="rounded-lg border border-slate-100 p-3">
                                        <div className="flex items-start justify-between gap-3">
                                            <div className="min-w-0">
                                                <div className="truncate text-sm font-bold text-slate-900">{item.report_title || `执行记录 #${item.id}`}</div>
                                                <div className="mt-1 text-xs font-semibold text-slate-500">
                                                    {formatDateTime(item.finished_at || item.started_at)} · {item.material_count} 条素材 · 已推送 {item.pushed_count} 人
                                                    {item.afternoon_push_status === "pending" ? " · 等待下午发送" : ""}
                                                </div>
                                            </div>
                                            <Badge variant="outline" className={statusClass(item.status)}>{statusLabel(item.status)}</Badge>
                                        </div>
                                        {item.error_message ? <div className="mt-2 text-xs font-semibold text-rose-600">{item.error_message}</div> : null}
                                        {item.document_url ? (
                                            <div className="mt-2 flex flex-wrap items-center gap-2">
                                                <a className="inline-flex items-center gap-1 text-xs font-bold text-blue-600 hover:underline" href={item.document_url} target="_blank" rel="noreferrer">
                                                    打开云文档 <ExternalLink className="size-3" />
                                                </a>
                                                <Button variant="ghost" size="sm" className="h-7 px-2 text-xs" onClick={() => setSelectedRunId((value) => value === item.id ? null : item.id)}>查看智能体过程</Button>
                                                {item.run_mode === "formal" && item.output_payload.multi_agent ? (
                                                    <Button variant="ghost" size="sm" className="h-7 px-2 text-xs" disabled={regenerateMutation.isPending} onClick={() => regenerateMutation.mutate(item.id)}>原文档重新生成</Button>
                                                ) : null}
                                                {item.run_mode === "debug" ? <Badge variant="outline" className="border-violet-200 bg-violet-50 text-violet-700">调试·未推送</Badge> : null}
                                            </div>
                                        ) : null}
                                        {selectedRunId === item.id ? (
                                            <div className="mt-3 space-y-2 rounded-lg border border-slate-200 bg-slate-50 p-2">
                                                {stagesQuery.isLoading ? <div className="p-2 text-xs text-slate-500">正在加载执行过程…</div> : null}
                                                {(stagesQuery.data ?? []).map((stage) => (
                                                    <details key={stage.id} className="rounded-md border border-slate-200 bg-white px-3 py-2">
                                                        <summary className="cursor-pointer text-xs font-bold text-slate-800">{stage.stage_name} · {(stage.duration_ms / 1000).toFixed(1)} 秒 · {statusLabel(stage.status)}</summary>
                                                        <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap text-[11px] leading-5 text-slate-600">{stage.output_content || stage.error_message || "无输出"}</pre>
                                                    </details>
                                                ))}
                                            </div>
                                        ) : null}
                                        {(item.output_payload.artifacts?.length ?? 0) > 0 ? (
                                            <div className="mt-3 grid gap-2 sm:grid-cols-2">
                                                {item.output_payload.artifacts?.map((artifact, index) => (
                                                    <a
                                                        key={`${artifact.artifact_type}-${artifact.strategy_code || index}`}
                                                        className="rounded-lg border border-slate-200 bg-slate-50 p-2.5 transition hover:border-blue-200 hover:bg-blue-50"
                                                        href={artifact.document_url || undefined}
                                                        target="_blank"
                                                        rel="noreferrer"
                                                        aria-disabled={!artifact.document_url}
                                                    >
                                                        <div className="flex items-center justify-between gap-2">
                                                            <span className="truncate text-xs font-bold text-slate-800">{artifact.strategy_name || artifact.title}</span>
                                                            {typeof artifact.score === "number" ? <Badge variant="outline">{artifact.score.toFixed(1)} 分</Badge> : null}
                                                        </div>
                                                        {artifact.models?.length ? <div className="mt-1 truncate text-[11px] text-slate-500">{artifact.models.join(" / ")}</div> : null}
                                                    </a>
                                                ))}
                                            </div>
                                        ) : null}
                                        {typeof item.output_payload.final_score === "number" ? (
                                            <div className="mt-2 text-xs font-bold text-emerald-700">最终审校评分 {item.output_payload.final_score.toFixed(1)} 分</div>
                                        ) : null}
                                    </div>
                                ))}
                                {!runs.length ? <div className="py-20 text-center text-sm font-semibold text-slate-400">暂无执行记录</div> : null}
                            </div>
                        </div>
                    </DemoCard>
                </div>
            </div>

            <Dialog open={dialogOpen} onOpenChange={(open) => { setDialogOpen(open); if (!open) resetPlanEditor(); }}>
                <DialogContent className="flex max-h-[min(900px,calc(100vh-32px))] !w-[min(1040px,calc(100vw-32px))] !max-w-[1040px] flex-col gap-0 overflow-hidden p-0 sm:!max-w-[1040px]">
                    <DialogHeader className="shrink-0 border-b border-slate-100 px-6 py-5">
                        <DialogTitle>{editing ? "编辑飞书简报计划" : "新建飞书简报计划"}</DialogTitle>
                        <DialogDescription>常用计划设置与高级生成编排分开维护，修改后可先生成调试稿验证。</DialogDescription>
                    </DialogHeader>
                    <div className="flex shrink-0 gap-1 overflow-x-auto border-b border-slate-100 bg-slate-50/70 px-6 py-2">
                        {([
                            ["plan", "计划设置"],
                            ["content", "素材与生成"],
                            ["advanced", "高级编排"],
                            ["debug", "调试与记录"],
                        ] as const).map(([value, label]) => (
                            <Button
                                key={value}
                                type="button"
                                size="sm"
                                variant={editorSection === value ? "default" : "ghost"}
                                className={editorSection === value ? "shrink-0" : "shrink-0 text-slate-600"}
                                onClick={() => setEditorSection(value)}
                            >
                                {label}
                            </Button>
                        ))}
                    </div>
                    <div className="min-h-0 flex-1 space-y-5 overflow-auto px-6 py-5">
                        {editorSection === "plan" || editorSection === "content" ? (
                        <section>
                            <div className="mb-3 text-sm font-black text-slate-900">{editorSection === "plan" ? "计划与时间" : "素材范围与生成方式"}</div>
                            <div className="grid gap-4 md:grid-cols-2">
                                {editorSection === "plan" ? (
                                <>
                                <div className="space-y-2 md:col-span-2">
                                    <Label>计划名称</Label>
                                    <Input value={form.plan_name} placeholder="如：御馨市场信息周报" onChange={(event) => setForm((old) => ({ ...old, plan_name: event.target.value }))} />
                                </div>
                                <InsightSelect label="所属公司" value={form.sys_company_id ? String(form.sys_company_id) : ""} options={companyOptions} onChange={(value) => setForm((old) => ({ ...old, sys_company_id: value ? Number(value) : null }))} />
                                <InsightSelect
                                    label="生成周期"
                                    value={form.schedule_frequency}
                                    options={[{ value: "daily", label: "日报" }, { value: "weekly", label: "周报" }, { value: "monthly", label: "月报" }]}
                                    onChange={(value) => setForm((old) => ({
                                        ...old,
                                        schedule_frequency: value as "daily" | "weekly" | "monthly",
                                        generation_strategy: value === "weekly" ? "multi_agent_ensemble" : old.generation_strategy,
                                        material_days: value === "daily" ? 1 : value === "weekly" ? 7 : 31,
                                        material_scope: { ...old.material_scope, rolling_days: value === "daily" ? 1 : value === "weekly" ? 7 : 31 },
                                    }))}
                                />
                                {form.schedule_frequency === "weekly" ? (
                                    <InsightSelect label="每周执行日" value={String(form.weekday ?? 0)} options={weekdayOptions} onChange={(value) => setForm((old) => ({ ...old, weekday: Number(value) }))} />
                                ) : form.schedule_frequency === "monthly" ? (
                                    <InsightSelect
                                        label="每月执行日"
                                        value={String(form.day_of_month ?? 1)}
                                        options={[
                                            ...Array.from({ length: 28 }, (_, index) => ({ value: String(index + 1), label: `${index + 1} 日` })),
                                            { value: "31", label: "每月最后一天" },
                                        ]}
                                        onChange={(value) => setForm((old) => ({ ...old, day_of_month: Number(value) }))}
                                    />
                                ) : <div />}
                                <div className="space-y-2">
                                    <Label>生成时间</Label>
                                    <Input type="time" value={form.time_of_day} onChange={(event) => setForm((old) => ({ ...old, time_of_day: event.target.value }))} />
                                </div>
                                {form.schedule_frequency === "weekly" ? (
                                    <>
                                        <InsightSelect label="审阅组推送日" value={String(form.review_weekday ?? 0)} options={weekdayOptions} onChange={(value) => setForm((old) => ({ ...old, review_weekday: Number(value) }))} />
                                        <div className="space-y-2">
                                            <Label>审阅组推送时间</Label>
                                            <Input type="time" value={form.review_time} onChange={(event) => setForm((old) => ({ ...old, review_time: event.target.value }))} />
                                        </div>
                                        <InsightSelect label="正式组推送日" value={String(form.release_weekday ?? 1)} options={weekdayOptions} onChange={(value) => setForm((old) => ({ ...old, release_weekday: Number(value) }))} />
                                        <div className="space-y-2">
                                            <Label>正式组推送时间</Label>
                                            <Input type="time" value={form.release_time} onChange={(event) => setForm((old) => ({ ...old, release_time: event.target.value, afternoon_push_time: event.target.value }))} />
                                        </div>
                                    </>
                                ) : null}
                                <InsightSelect label="状态" value={form.status} options={[{ value: "active", label: "启用" }, { value: "paused", label: "暂停" }]} onChange={(value) => setForm((old) => ({ ...old, status: value as "active" | "paused" }))} />
                                </>
                                ) : (
                                <>
                                <InsightSelect
                                    label="素材范围模式"
                                    value={form.material_scope.mode}
                                    options={[
                                        { value: "rolling_days", label: "向前滚动天数" },
                                        { value: "fixed_weekdays", label: "固定星期区间" },
                                        { value: "custom_range", label: "指定日期区间" },
                                    ]}
                                    onChange={(value) => setForm((old) => ({ ...old, material_scope: { ...old.material_scope, mode: value as InsightFeishuBriefPlanCreate["material_scope"]["mode"] } }))}
                                />
                                <InsightSelect
                                    label="素材周期"
                                    value={String(form.material_scope.rolling_days)}
                                    options={[
                                        { value: "1", label: "近 1 天" },
                                        { value: "3", label: "近 3 天" },
                                        { value: "7", label: "近 7 天" },
                                        { value: "15", label: "近 15 天" },
                                        { value: "30", label: "近 30 天" },
                                        { value: "31", label: "近 31 天" },
                                    ]}
                                    onChange={(value) => setForm((old) => ({ ...old, material_days: Number(value), material_scope: { ...old.material_scope, rolling_days: Number(value) } }))}
                                />
                                {form.material_scope.mode === "fixed_weekdays" ? (
                                    <>
                                        <InsightSelect label="素材开始星期" value={String(form.material_scope.start_weekday)} options={weekdayOptions} onChange={(value) => setForm((old) => ({ ...old, material_scope: { ...old.material_scope, start_weekday: Number(value) } }))} />
                                        <InsightSelect label="素材结束星期" value={String(form.material_scope.end_weekday)} options={weekdayOptions} onChange={(value) => setForm((old) => ({ ...old, material_scope: { ...old.material_scope, end_weekday: Number(value) } }))} />
                                    </>
                                ) : null}
                                {form.material_scope.mode === "custom_range" ? (
                                    <>
                                        <div className="space-y-2"><Label>素材开始时间</Label><Input type="datetime-local" value={form.material_scope.custom_start?.slice(0, 16) || ""} onChange={(event) => setForm((old) => ({ ...old, material_scope: { ...old.material_scope, custom_start: event.target.value || null } }))} /></div>
                                        <div className="space-y-2"><Label>素材结束时间</Label><Input type="datetime-local" value={form.material_scope.custom_end?.slice(0, 16) || ""} onChange={(event) => setForm((old) => ({ ...old, material_scope: { ...old.material_scope, custom_end: event.target.value || null } }))} /></div>
                                    </>
                                ) : null}
                                <div className="space-y-2">
                                    <Label>单次读取上限</Label>
                                    <Input type="number" min={20} max={500} value={form.max_materials} onChange={(event) => setForm((old) => ({ ...old, max_materials: Number(event.target.value) }))} />
                                    <div className="text-xs leading-5 text-slate-500">只控制单次扫描性能，不限制符合规则的素材入选数量。</div>
                                </div>
                                {form.schedule_frequency !== "daily" ? (
                                    <div className="md:col-span-2">
                                        <InsightSelect
                                            label={form.schedule_frequency === "weekly" ? "周报生成策略" : "月报生成策略"}
                                            value={form.generation_strategy}
                                            options={form.schedule_frequency === "weekly"
                                                ? [{ value: "multi_agent_ensemble", label: "多智能体编排（固定）" }]
                                                : [
                                                    { value: "auto", label: "多策略择优（推荐）" },
                                                    { value: "single_model", label: "单模型整篇生成" },
                                                    { value: "section_parallel", label: "分章节并行生成" },
                                                    { value: "multi_agent_ensemble", label: "多智能体集成" },
                                                ]}
                                            onChange={(value) => setForm((old) => ({ ...old, generation_strategy: value as InsightFeishuBriefPlanCreate["generation_strategy"] }))}
                                        />
                                        <div className="mt-2 rounded-lg border border-blue-100 bg-blue-50 px-3 py-2 text-xs leading-5 text-blue-800">
                                            {form.schedule_frequency === "weekly"
                                                ? "周报固定使用策划、五专题研究、主笔、独立审阅和修订流程，模型由系统自动路由。"
                                                : "模型由系统自动路由，生成策略仅控制月报的组织方式。"}
                                        </div>
                                    </div>
                                ) : null}
                                </>
                                )}
                            </div>
                        </section>
                        ) : null}

                        {editorSection === "advanced" && form.schedule_frequency === "weekly" ? (
                            <section>
                                <div className="mb-3 text-sm font-black text-slate-900">多智能体流程与提示词</div>
                                <div className="grid gap-4 md:grid-cols-2">
                                    <div className="space-y-2">
                                        <Label>最多修订轮数</Label>
                                        <Input type="number" min={1} max={4} value={form.workflow_config.max_revision_rounds} onChange={(event) => setForm((old) => ({ ...old, workflow_config: { ...old.workflow_config, max_revision_rounds: Number(event.target.value) } }))} />
                                    </div>
                                    <div className="rounded-lg border border-cyan-100 bg-cyan-50 px-3 py-2 text-xs leading-5 text-cyan-800">固定流程：策划 → 政策/竞对/客户/技术/原料研究 → 主笔 → 独立审阅 → 主笔修订 → 确定性校验。</div>
                                    {([
                                        ["planning", "策划智能体"],
                                        ["research", "专题研究智能体"],
                                        ["writing", "主笔智能体"],
                                        ["reviewing", "审阅智能体"],
                                        ["revision", "修订智能体"],
                                    ] as const).map(([key, label]) => (
                                        <div key={key} className="space-y-2">
                                            <Label>{label}业务提示词</Label>
                                            <Textarea className="min-h-28 resize-y" value={form.prompt_config[key]} placeholder="留空则使用系统迁移的现有周报策略" onChange={(event) => setForm((old) => ({ ...old, prompt_config: { ...old.prompt_config, [key]: event.target.value } }))} />
                                        </div>
                                    ))}
                                </div>
                                <div className="mt-4 grid gap-4 lg:grid-cols-2">
                                    <div className="space-y-2">
                                        <Label>Markdown 模板</Label>
                                        <Textarea className="min-h-80 resize-y font-mono text-xs leading-5" value={form.template_markdown || ""} onChange={(event) => setForm((old) => ({ ...old, template_markdown: event.target.value }))} />
                                    </div>
                                    <div className="space-y-2">
                                        <Label>模板预览</Label>
                                        <div className="prose prose-sm min-h-80 max-w-none overflow-auto rounded-lg border border-slate-200 bg-white p-4">
                                            <ReactMarkdown>{form.template_markdown || "暂无模板"}</ReactMarkdown>
                                        </div>
                                    </div>
                                </div>
                            </section>
                        ) : null}

                        {editorSection === "content" ? (
                        <section className="border-t border-slate-100 pt-5">
                            <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
                                <div>
                                    <div className="text-sm font-black text-slate-900">内容规则</div>
                                    <div className="mt-1 text-xs leading-5 text-slate-500">调整业务关注范围和写作侧重；领导固定版式、七条导读和事实核验规则不会被改变。</div>
                                </div>
                                <Button
                                    type="button"
                                    variant="outline"
                                    size="sm"
                                    onClick={() => {
                                        const companyName = companyOptions.find((item) => item.value === String(form.sys_company_id ?? ""))?.label;
                                        setForm((old) => ({ ...old, generation_rules: generationRulesForCompany(companyName) }));
                                    }}
                                >
                                    恢复公司默认
                                </Button>
                            </div>
                            <div className="space-y-4 rounded-lg border border-slate-200 bg-slate-50/60 p-4">
                                <div className="space-y-2">
                                    <Label>关注主题</Label>
                                    <Input
                                        value={form.generation_rules.focus_topics.join("、")}
                                        placeholder="使用顿号或逗号分隔，如：茶饮客户、糖浆、减糖趋势"
                                        onChange={(event) => setForm((old) => ({
                                            ...old,
                                            generation_rules: {
                                                ...old.generation_rules,
                                                focus_topics: event.target.value.split(/[、,，]/).map((item) => item.trim()).filter(Boolean),
                                            },
                                        }))}
                                    />
                                    <div className="text-xs leading-5 text-slate-500">用于判断哪些变化值得纳入，不要求文章必须直接出现产品名称。</div>
                                </div>

                                <div className="grid gap-4 lg:grid-cols-2">
                                    <RuleChipGroup
                                        label="服务部门"
                                        options={departmentOptions}
                                        selected={form.generation_rules.value_departments}
                                        onChange={(value) => setForm((old) => ({ ...old, generation_rules: { ...old.generation_rules, value_departments: value } }))}
                                    />
                                    <RuleChipGroup
                                        label="默认排除"
                                        options={excludedOptions}
                                        selected={form.generation_rules.excluded_content}
                                        onChange={(value) => setForm((old) => ({ ...old, generation_rules: { ...old.generation_rules, excluded_content: value } }))}
                                    />
                                </div>

                                <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                                    <div className="space-y-2">
                                        <Label>主线素材分数</Label>
                                        <Input type="number" min={60} max={100} value={form.generation_rules.primary_score} onChange={(event) => setForm((old) => ({ ...old, generation_rules: { ...old.generation_rules, primary_score: Number(event.target.value) } }))} />
                                    </div>
                                    <div className="space-y-2">
                                        <Label>补充素材分数</Label>
                                        <Input type="number" min={50} max={99} value={form.generation_rules.supporting_score} onChange={(event) => setForm((old) => ({ ...old, generation_rules: { ...old.generation_rules, supporting_score: Number(event.target.value) } }))} />
                                    </div>
                                    <div className="space-y-2">
                                        <Label>最少引用来源</Label>
                                        <Input type="number" min={5} max={30} value={form.generation_rules.minimum_citations} onChange={(event) => setForm((old) => ({ ...old, generation_rules: { ...old.generation_rules, minimum_citations: Number(event.target.value) } }))} />
                                    </div>
                                    <div className="space-y-2">
                                        <Label>最多引用来源</Label>
                                        <Input type="number" min={7} max={40} value={form.generation_rules.maximum_citations} onChange={(event) => setForm((old) => ({ ...old, generation_rules: { ...old.generation_rules, maximum_citations: Number(event.target.value) } }))} />
                                    </div>
                                </div>

                                <div>
                                    <Label>栏目侧重</Label>
                                    <div className="mt-2 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
                                        {sectionNames.map((section) => (
                                            <InsightSelect
                                                key={section}
                                                label={section}
                                                value={String(form.generation_rules.section_priorities[section] ?? 3)}
                                                options={[0, 1, 2, 3, 4, 5].map((value) => ({ value: String(value), label: value === 0 ? "不关注" : `${value} 级` }))}
                                                onChange={(value) => setForm((old) => ({
                                                    ...old,
                                                    generation_rules: {
                                                        ...old.generation_rules,
                                                        section_priorities: { ...old.generation_rules.section_priorities, [section]: Number(value) },
                                                    },
                                                }))}
                                            />
                                        ))}
                                    </div>
                                </div>

                                <div className="grid items-end gap-4 md:grid-cols-2">
                                    <InsightSelect
                                        label="写作深度"
                                        value={form.generation_rules.writing_depth}
                                        options={[{ value: "concise", label: "精简" }, { value: "balanced", label: "均衡" }, { value: "detailed", label: "深入" }]}
                                        onChange={(value) => setForm((old) => ({ ...old, generation_rules: { ...old.generation_rules, writing_depth: value as InsightFeishuBriefGenerationRules["writing_depth"] } }))}
                                    />
                                    <div className="flex min-h-10 items-center justify-between gap-4 rounded-lg border border-slate-200 bg-white px-3 py-2">
                                        <div>
                                            <div className="text-sm font-bold text-slate-800">说明业务影响</div>
                                            <div className="mt-0.5 text-xs text-slate-500">基于材料解释影响，不生成无依据的行动建议。</div>
                                        </div>
                                        <Switch checked={form.generation_rules.include_business_insight} onCheckedChange={(checked) => setForm((old) => ({ ...old, generation_rules: { ...old.generation_rules, include_business_insight: checked } }))} />
                                    </div>
                                </div>
                            </div>
                        </section>
                        ) : null}

                        {editorSection === "advanced" ? (
                        <section className="border-t border-slate-100 pt-5">
                            <div className="mb-2 text-sm font-black text-slate-900">系统护栏</div>
                            <div className="mb-3 rounded-lg border border-emerald-100 bg-emerald-50 px-3 py-2 text-xs leading-5 text-emerald-800">
                                固定栏目、七条导读、权限过滤、事实核验和引用合法性由系统强制执行，不占用业务 Prompt，也不能被自定义配置关闭。
                            </div>
                            <Button
                                type="button"
                                variant="outline"
                                className="h-10 w-full justify-between bg-white"
                                onClick={() => setPromptExpanded((value) => !value)}
                            >
                                <span>查看系统固定规则</span>
                                <ChevronDown className={promptExpanded ? "size-4 rotate-180 transition-transform" : "size-4 transition-transform"} />
                            </Button>
                            {promptExpanded ? (
                                <pre className="mt-2 max-h-72 overflow-auto whitespace-pre-wrap rounded-lg border border-slate-200 bg-slate-50 p-4 text-xs leading-6 text-slate-700">
                                    {options?.prompt_template || "提示词加载中"}
                                </pre>
                            ) : null}
                        </section>
                        ) : null}

                        {editorSection === "plan" ? (
                        <section className="border-t border-slate-100 pt-5">
                            <div className="mb-3 flex items-center gap-2 text-sm font-black text-slate-900">
                                <Send className="size-4 text-blue-600" />
                                分批推送
                            </div>
                            <div className="rounded-lg border border-blue-100 bg-blue-50 px-3 py-2 text-xs leading-5 text-blue-800">
                                周报只生成一篇云文档。上午审阅人可直接修改，下午发送的是修改后的同一篇文档。
                            </div>
                            <div className="mt-4 grid gap-4 [grid-template-columns:repeat(auto-fit,minmax(min(100%,360px),1fr))]">
                                <RecipientGroupCard
                                    title="审阅组"
                                    description={`按计划于周${Number(form.review_weekday ?? 0) + 1} ${form.review_time} 推送；若生成延迟则完成后立即发送。`}
                                    recipients={form.recipients}
                                    onChoose={() => setRecipientPickerStage("morning")}
                                    onRemove={(receiveId) => setForm((old) => ({
                                        ...old,
                                        recipients: old.recipients.filter((item) => item.receive_id !== receiveId),
                                    }))}
                                />
                                <RecipientGroupCard
                                    title="正式接收组"
                                    description={`将在 ${form.release_time} 自动发送审阅后的同一文档。`}
                                    recipients={form.afternoon_recipients}
                                    onChoose={() => setRecipientPickerStage("afternoon")}
                                    onRemove={(receiveId) => setForm((old) => ({
                                        ...old,
                                        afternoon_recipients: old.afternoon_recipients.filter((item) => item.receive_id !== receiveId),
                                    }))}
                                    action={(
                                        <div className="flex items-center gap-2">
                                            <Clock3 className="size-4 text-slate-400" />
                                            <Input
                                                type="time"
                                                className="h-8 w-28 bg-white"
                                                value={form.release_time}
                                                onChange={(event) => setForm((old) => ({ ...old, release_time: event.target.value, afternoon_push_time: event.target.value }))}
                                            />
                                        </div>
                                    )}
                                />
                            </div>
                        </section>
                        ) : null}

                        {editorSection === "debug" ? (
                            <section className="space-y-4">
                                <div>
                                    <div className="text-sm font-black text-slate-900">调试当前配置</div>
                                    <div className="mt-1 text-xs leading-5 text-slate-500">使用页面中尚未保存的配置运行完整流程，生成带“[调试]”前缀的云文档，不向任何人推送。</div>
                                </div>
                                <div className="rounded-xl border border-violet-100 bg-violet-50/70 p-4">
                                    <div className="flex flex-wrap items-center justify-between gap-3">
                                        <div>
                                            <div className="text-sm font-bold text-violet-950">策划、研究、主笔、审阅和修订都会真实执行</div>
                                            <div className="mt-1 text-xs leading-5 text-violet-700">调试稿所有权会转给当前登录用户，执行过程保留模型、耗时和阶段输出。</div>
                                        </div>
                                        <Button
                                            type="button"
                                            disabled={!editing?.can_edit || debugMutation.isPending || !options?.configured}
                                            onClick={() => debugMutation.mutate()}
                                        >
                                            {debugMutation.isPending ? <Loader2 className="size-4 animate-spin" /> : <Bug className="size-4" />}
                                            生成调试稿
                                        </Button>
                                    </div>
                                    {!editing ? <div className="mt-3 text-xs font-semibold text-amber-700">请先保存计划，再使用当前页面草稿生成调试稿。</div> : null}
                                </div>
                                <div>
                                    <div className="mb-2 text-sm font-black text-slate-900">本计划最近执行</div>
                                    <div className="space-y-2">
                                        {runs.filter((item) => item.plan_id === editing?.id).slice(0, 5).map((item) => (
                                            <div key={item.id} className="flex items-center justify-between gap-3 rounded-lg border border-slate-200 bg-white p-3">
                                                <div className="min-w-0">
                                                    <div className="truncate text-sm font-bold text-slate-900">{item.report_title || `执行记录 #${item.id}`}</div>
                                                    <div className="mt-1 text-xs text-slate-500">{item.run_mode === "debug" ? "调试" : "正式"} · {formatDateTime(item.finished_at || item.started_at)} · {item.material_count} 条素材</div>
                                                </div>
                                                <div className="flex shrink-0 items-center gap-2">
                                                    <Badge variant="outline" className={statusClass(item.status)}>{statusLabel(item.status)}</Badge>
                                                    {item.document_url ? <Button type="button" variant="ghost" size="sm" onClick={() => window.open(item.document_url || "", "_blank", "noopener,noreferrer")}>打开文档</Button> : null}
                                                </div>
                                            </div>
                                        ))}
                                        {editing && !runs.some((item) => item.plan_id === editing.id) ? <div className="rounded-lg border border-dashed border-slate-200 py-10 text-center text-sm text-slate-400">暂无执行记录</div> : null}
                                    </div>
                                </div>
                            </section>
                        ) : null}
                    </div>
                    <DialogFooter className="shrink-0 border-t border-slate-100 px-6 py-4">
                        <Button variant="outline" onClick={() => { setDialogOpen(false); resetPlanEditor(); }}>取消</Button>
                        <Button disabled={!form.plan_name.trim() || saveMutation.isPending || Boolean(editing && !editing.can_edit)} onClick={() => saveMutation.mutate()}>
                            {saveMutation.isPending ? <Loader2 className="size-4 animate-spin" /> : null}
                            保存计划
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
            <Dialog open={occurrencePlan !== null} onOpenChange={(open) => { if (!open) setOccurrencePlan(null); }}>
                <DialogContent className="sm:max-w-xl">
                    <DialogHeader>
                        <DialogTitle>本期临时调整</DialogTitle>
                        <DialogDescription>{occurrencePlan?.plan_name} 本期按以下时间执行，完成后自动恢复常规计划。</DialogDescription>
                    </DialogHeader>
                    <div className="grid gap-4 py-2 md:grid-cols-2">
                        <div className="space-y-2 md:col-span-2"><Label>本期生成时间</Label><Input type="datetime-local" value={occurrenceForm.generation_scheduled_at.slice(0, 16)} onChange={(event) => setOccurrenceForm((old) => ({ ...old, generation_scheduled_at: event.target.value }))} /></div>
                        <div className="space-y-2"><Label>审阅组推送时间</Label><Input type="datetime-local" value={occurrenceForm.review_scheduled_at.slice(0, 16)} onChange={(event) => setOccurrenceForm((old) => ({ ...old, review_scheduled_at: event.target.value }))} /></div>
                        <div className="space-y-2"><Label>正式组推送时间</Label><Input type="datetime-local" value={occurrenceForm.release_scheduled_at.slice(0, 16)} onChange={(event) => setOccurrenceForm((old) => ({ ...old, release_scheduled_at: event.target.value }))} /></div>
                        <InsightSelect label="本期素材范围" value={occurrenceForm.material_scope?.mode || "rolling_days"} options={[{ value: "rolling_days", label: "向前滚动天数" }, { value: "fixed_weekdays", label: "固定星期区间" }, { value: "custom_range", label: "指定日期区间" }]} onChange={(value) => setOccurrenceForm((old) => ({ ...old, material_scope: { ...(old.material_scope || emptyForm.material_scope), mode: value as InsightFeishuBriefPlanCreate["material_scope"]["mode"] } }))} />
                        {occurrenceForm.material_scope?.mode === "rolling_days" ? <div className="space-y-2"><Label>向前取材天数</Label><Input type="number" min={1} max={90} value={occurrenceForm.material_scope?.rolling_days || 7} onChange={(event) => setOccurrenceForm((old) => ({ ...old, material_scope: { ...(old.material_scope || emptyForm.material_scope), rolling_days: Number(event.target.value) } }))} /></div> : null}
                        {occurrenceForm.material_scope?.mode === "fixed_weekdays" ? <>
                            <InsightSelect label="素材开始星期" value={String(occurrenceForm.material_scope.start_weekday)} options={weekdayOptions} onChange={(value) => setOccurrenceForm((old) => ({ ...old, material_scope: { ...(old.material_scope || emptyForm.material_scope), start_weekday: Number(value) } }))} />
                            <InsightSelect label="素材结束星期" value={String(occurrenceForm.material_scope.end_weekday)} options={weekdayOptions} onChange={(value) => setOccurrenceForm((old) => ({ ...old, material_scope: { ...(old.material_scope || emptyForm.material_scope), end_weekday: Number(value) } }))} />
                        </> : null}
                        {occurrenceForm.material_scope?.mode === "custom_range" ? <>
                            <div className="space-y-2"><Label>素材开始时间</Label><Input type="datetime-local" value={occurrenceForm.material_scope.custom_start?.slice(0, 16) || ""} onChange={(event) => setOccurrenceForm((old) => ({ ...old, material_scope: { ...(old.material_scope || emptyForm.material_scope), custom_start: event.target.value || null } }))} /></div>
                            <div className="space-y-2"><Label>素材结束时间</Label><Input type="datetime-local" value={occurrenceForm.material_scope.custom_end?.slice(0, 16) || ""} onChange={(event) => setOccurrenceForm((old) => ({ ...old, material_scope: { ...(old.material_scope || emptyForm.material_scope), custom_end: event.target.value || null } }))} /></div>
                        </> : null}
                    </div>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setOccurrencePlan(null)}>取消</Button>
                        <Button disabled={occurrenceMutation.isPending} onClick={() => occurrenceMutation.mutate()}>{occurrenceMutation.isPending ? <Loader2 className="size-4 animate-spin" /> : null}保存本期调整</Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
            <FeishuRecipientPickerDialog
                open={recipientPickerStage !== null}
                selected={recipientPickerStage === "afternoon" ? form.afternoon_recipients : form.recipients}
                onOpenChange={(open) => {
                    if (!open) setRecipientPickerStage(null);
                }}
                onConfirm={(recipients) => {
                    setForm((old) => recipientPickerStage === "afternoon"
                        ? ({ ...old, afternoon_recipients: recipients })
                        : ({ ...old, recipients }));
                    setRecipientPickerStage(null);
                }}
            />
        </PageContainer>
    );
}

function RecipientGroupCard({
    title,
    description,
    recipients,
    onChoose,
    onRemove,
    action,
}: {
    title: string;
    description: string;
    recipients: InsightFeishuBriefRecipient[];
    onChoose: () => void;
    onRemove: (receiveId: string) => void;
    action?: ReactNode;
}) {
    return (
        <div className="min-w-0 rounded-lg border border-slate-200 bg-slate-50 p-3">
            <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                    <div className="text-sm font-black text-slate-900">{title}</div>
                    <div className="mt-1 text-xs leading-5 text-slate-500">{description}</div>
                </div>
                {action ? <div className="shrink-0">{action}</div> : null}
            </div>
            <div className="mt-3 min-h-24 rounded-lg border border-slate-200 bg-white p-2">
                {recipients.length ? (
                    <div className="space-y-2">
                        {recipients.map((recipient) => (
                            <div key={`${recipient.receive_id_type}-${recipient.receive_id}`} className="flex items-center gap-2 rounded-md bg-slate-50 px-2 py-1.5">
                                <div className="flex size-7 shrink-0 items-center justify-center rounded-full bg-blue-50 text-blue-700">
                                    <UserRound className="size-3.5" />
                                </div>
                                <div className="min-w-0 flex-1">
                                    <div className="truncate text-xs font-bold text-slate-800">{recipient.name || recipient.receive_id}</div>
                                    <div className="truncate text-[11px] text-slate-500">{recipient.receive_id}</div>
                                </div>
                                <Button type="button" variant="ghost" size="icon" className="size-7 text-slate-400 hover:text-rose-600" title="移除" onClick={() => onRemove(recipient.receive_id)}>
                                    <X className="size-3.5" />
                                </Button>
                            </div>
                        ))}
                    </div>
                ) : (
                    <div className="flex h-20 items-center justify-center text-xs font-semibold text-slate-400">尚未选择人员</div>
                )}
            </div>
            <Button type="button" variant="outline" size="sm" className="mt-3 w-full bg-white" onClick={onChoose}>
                <UserRound className="size-4" />
                {recipients.length ? "调整人员" : "选择人员"}
            </Button>
        </div>
    );
}

function RuleChipGroup({
    label,
    options,
    selected,
    onChange,
}: {
    label: string;
    options: string[];
    selected: string[];
    onChange: (value: string[]) => void;
}) {
    return (
        <div className="space-y-2">
            <Label>{label}</Label>
            <div className="flex min-h-10 flex-wrap gap-2 rounded-lg border border-slate-200 bg-white p-2">
                {options.map((option) => {
                    const active = selected.includes(option);
                    return (
                        <Button
                            key={option}
                            type="button"
                            size="sm"
                            variant={active ? "default" : "outline"}
                            className={active ? "h-7 bg-blue-600 px-2.5 text-xs hover:bg-blue-700" : "h-7 bg-white px-2.5 text-xs"}
                            onClick={() => onChange(active ? selected.filter((item) => item !== option) : [...selected, option])}
                        >
                            {option}
                        </Button>
                    );
                })}
            </div>
        </div>
    );
}

function defaultOccurrenceForm(plan?: InsightFeishuBriefPlanRead): InsightFeishuBriefOccurrenceOverride {
    const now = new Date();
    const weekday = plan?.weekday ?? 0;
    const daysAhead = (weekday - ((now.getDay() + 6) % 7) + 7) % 7;
    const generation = new Date(now);
    generation.setDate(now.getDate() + daysAhead);
    const [generationHour, generationMinute] = (plan?.time_of_day || "09:00").split(":").map(Number);
    generation.setHours(generationHour, generationMinute, 0, 0);
    if (generation <= now) generation.setDate(generation.getDate() + 7);
    const monday = new Date(generation);
    monday.setDate(generation.getDate() - ((generation.getDay() + 6) % 7));
    monday.setHours(0, 0, 0, 0);
    const scheduled = (targetWeekday: number, time: string) => {
        const value = new Date(monday);
        const [hour, minute] = time.split(":").map(Number);
        value.setDate(monday.getDate() + targetWeekday);
        value.setHours(hour, minute, 0, 0);
        return value;
    };
    const review = scheduled(plan?.review_weekday ?? weekday, plan?.review_time || "10:30");
    const release = scheduled(plan?.release_weekday ?? weekday, plan?.release_time || "15:00");
    if (release <= generation) release.setDate(release.getDate() + 7);
    const localValue = (value: Date) => {
        const offset = value.getTimezoneOffset() * 60_000;
        return new Date(value.getTime() - offset).toISOString().slice(0, 16);
    };
    return {
        generation_scheduled_at: localValue(generation),
        review_scheduled_at: localValue(review),
        release_scheduled_at: localValue(release),
        material_scope: plan?.material_scope || { ...emptyForm.material_scope },
    };
}

function statusLabel(value?: string | null) {
    return ({ success: "成功", partial: "部分成功", failed: "失败", running: "执行中", active: "启用", paused: "暂停" } as Record<string, string>)[value || ""] || "未执行";
}

function statusClass(value?: string | null) {
    if (value === "success") return "border-emerald-200 bg-emerald-50 text-emerald-700";
    if (value === "failed") return "border-rose-200 bg-rose-50 text-rose-700";
    if (value === "running") return "border-blue-200 bg-blue-50 text-blue-700";
    return "border-slate-200 bg-slate-50 text-slate-600";
}

function formatDateTime(value?: string | null) {
    if (!value) return "--";
    return new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date(value));
}

function scheduleLabel(item: InsightFeishuBriefPlanRead) {
    if (item.schedule_frequency === "daily") return "每日";
    if (item.schedule_frequency === "monthly") return item.day_of_month === 31 ? "每月最后一天" : `每月 ${item.day_of_month ?? 1} 日`;
    return `每${weekdayOptions[item.weekday ?? 0]?.label}`;
}

function strategyLabel(value: InsightFeishuBriefPlanRead["generation_strategy"]) {
    return ({
        auto: "多策略择优",
        single_model: "单模型",
        section_parallel: "分章节",
        multi_agent_ensemble: "多智能体",
    } as const)[value];
}
