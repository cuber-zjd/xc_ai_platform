import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot, ChevronDown, ExternalLink, FileText, Loader2, Pencil, Play, Plus, RefreshCw, Send, Trash2, UserRound, X } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";

import { insightApi, type InsightFeishuBriefPlanCreate, type InsightFeishuBriefPlanRead } from "../api";
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

const emptyForm: InsightFeishuBriefPlanCreate = {
    plan_name: "",
    sys_company_id: null,
    schedule_frequency: "weekly",
    weekday: 0,
    time_of_day: "09:00",
    material_days: 7,
    max_materials: 200,
    prompt_override: "",
    recipients: [],
    status: "active",
};

export function FeishuBriefPage() {
    const queryClient = useQueryClient();
    const [page, setPage] = useState(1);
    const [dialogOpen, setDialogOpen] = useState(false);
    const [editing, setEditing] = useState<InsightFeishuBriefPlanRead | null>(null);
    const [form, setForm] = useState<InsightFeishuBriefPlanCreate>(emptyForm);
    const [promptExpanded, setPromptExpanded] = useState(false);
    const [recipientPickerOpen, setRecipientPickerOpen] = useState(false);
    const optionsQuery = useQuery({ queryKey: ["insight-feishu-brief-options"], queryFn: insightApi.getFeishuBriefOptions });
    const plansQuery = useQuery({
        queryKey: ["insight-feishu-brief-plans", page],
        queryFn: () => insightApi.listFeishuBriefPlans({ page, size: 20 }),
    });
    const runsQuery = useQuery({
        queryKey: ["insight-feishu-brief-runs"],
        queryFn: () => insightApi.listFeishuBriefRuns({ page: 1, size: 20 }),
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
    const saveMutation = useMutation({
        mutationFn: () => editing
            ? insightApi.updateFeishuBriefPlan(editing.id, form)
            : insightApi.createFeishuBriefPlan(form),
        onSuccess: () => {
            toast.success(editing ? "简报计划已更新" : "简报计划已创建");
            setDialogOpen(false);
            refresh();
        },
        onError: () => toast.error("保存失败，请检查填写内容"),
    });
    const runMutation = useMutation({
        mutationFn: insightApi.runFeishuBriefPlan,
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

    useEffect(() => {
        if (!dialogOpen) {
            setEditing(null);
            setForm(emptyForm);
            setPromptExpanded(false);
            setRecipientPickerOpen(false);
        }
    }, [dialogOpen]);

    const openEdit = (item: InsightFeishuBriefPlanRead) => {
        setEditing(item);
        setForm({
            plan_name: item.plan_name,
            sys_company_id: item.sys_company_id,
            schedule_frequency: item.schedule_frequency,
            weekday: item.weekday,
            time_of_day: item.time_of_day,
            material_days: item.material_days,
            max_materials: item.max_materials,
            prompt_override: item.prompt_override,
            recipients: item.recipients,
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
                                {options?.bot_name || "市场洞察报告机器人"} · 独立生成日报和周报，不进入报告中心
                            </div>
                        </div>
                    </div>
                    <div className="flex items-center gap-2">
                        <Button variant="outline" size="icon" className="size-9 rounded-lg" onClick={refresh} title="刷新">
                            <RefreshCw className="size-4" />
                        </Button>
                        <Button className="h-9 rounded-lg bg-blue-600 hover:bg-blue-700" onClick={() => setDialogOpen(true)}>
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
                                            <div>{item.schedule_frequency === "daily" ? "每日" : `每${weekdayOptions[item.weekday ?? 0]?.label}`} {item.time_of_day}</div>
                                            <div className="mt-1 text-xs font-medium text-slate-500">素材近 {item.material_days} 天 · 推送 {item.recipients.length} 人</div>
                                        </TableCell>
                                        <TableCell className="text-xs font-semibold text-slate-600">{formatDateTime(item.next_run_time)}</TableCell>
                                        <TableCell>
                                            <Badge variant="outline" className={statusClass(item.last_status)}>{statusLabel(item.last_status)}</Badge>
                                        </TableCell>
                                        <TableCell>
                                            <div className="flex justify-end gap-1">
                                                <Button variant="ghost" size="icon" className="size-8" title="立即生成" disabled={!options?.configured || runMutation.isPending} onClick={() => runMutation.mutate(item.id)}>
                                                    {runMutation.isPending && runMutation.variables === item.id ? <Loader2 className="size-4 animate-spin" /> : <Play className="size-4" />}
                                                </Button>
                                                <Button variant="ghost" size="icon" className="size-8" title="编辑" onClick={() => openEdit(item)}><Pencil className="size-4" /></Button>
                                                <Button variant="ghost" size="icon" className="size-8 text-rose-600" title="删除" onClick={() => deleteMutation.mutate(item.id)}><Trash2 className="size-4" /></Button>
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
                                                <div className="mt-1 text-xs font-semibold text-slate-500">{formatDateTime(item.finished_at || item.started_at)} · {item.material_count} 条素材 · 推送 {item.pushed_count} 人</div>
                                            </div>
                                            <Badge variant="outline" className={statusClass(item.status)}>{statusLabel(item.status)}</Badge>
                                        </div>
                                        {item.error_message ? <div className="mt-2 text-xs font-semibold text-rose-600">{item.error_message}</div> : null}
                                        {item.document_url ? (
                                            <a className="mt-2 inline-flex items-center gap-1 text-xs font-bold text-blue-600 hover:underline" href={item.document_url} target="_blank" rel="noreferrer">
                                                打开云文档 <ExternalLink className="size-3" />
                                            </a>
                                        ) : null}
                                    </div>
                                ))}
                                {!runs.length ? <div className="py-20 text-center text-sm font-semibold text-slate-400">暂无执行记录</div> : null}
                            </div>
                        </div>
                    </DemoCard>
                </div>
            </div>

            <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
                <DialogContent className="flex max-h-[min(860px,calc(100vh-32px))] w-[min(860px,calc(100vw-32px))] max-w-none flex-col gap-0 overflow-hidden p-0">
                    <DialogHeader className="shrink-0 border-b border-slate-100 px-6 py-5">
                        <DialogTitle>{editing ? "编辑飞书简报计划" : "新建飞书简报计划"}</DialogTitle>
                        <DialogDescription>设置生成时间、素材范围和接收人；文档由独立飞书机器人创建并发送。</DialogDescription>
                    </DialogHeader>
                    <div className="min-h-0 flex-1 space-y-5 overflow-auto px-6 py-5">
                        <section>
                            <div className="mb-3 text-sm font-black text-slate-900">基础计划</div>
                            <div className="grid gap-4 md:grid-cols-2">
                                <div className="space-y-2 md:col-span-2">
                                    <Label>计划名称</Label>
                                    <Input value={form.plan_name} placeholder="如：御馨市场信息周报" onChange={(event) => setForm((old) => ({ ...old, plan_name: event.target.value }))} />
                                </div>
                                <InsightSelect label="所属公司" value={form.sys_company_id ? String(form.sys_company_id) : ""} options={companyOptions} onChange={(value) => setForm((old) => ({ ...old, sys_company_id: value ? Number(value) : null }))} />
                                <InsightSelect label="生成周期" value={form.schedule_frequency} options={[{ value: "daily", label: "日报" }, { value: "weekly", label: "周报" }]} onChange={(value) => setForm((old) => ({ ...old, schedule_frequency: value as "daily" | "weekly" }))} />
                                {form.schedule_frequency === "weekly" ? (
                                    <InsightSelect label="每周执行日" value={String(form.weekday ?? 0)} options={weekdayOptions} onChange={(value) => setForm((old) => ({ ...old, weekday: Number(value) }))} />
                                ) : <div />}
                                <div className="space-y-2">
                                    <Label>执行时间</Label>
                                    <Input type="time" value={form.time_of_day} onChange={(event) => setForm((old) => ({ ...old, time_of_day: event.target.value }))} />
                                </div>
                                <InsightSelect
                                    label="素材周期"
                                    value={String(form.material_days)}
                                    options={[
                                        { value: "1", label: "近 1 天" },
                                        { value: "3", label: "近 3 天" },
                                        { value: "7", label: "近 7 天" },
                                        { value: "15", label: "近 15 天" },
                                        { value: "30", label: "近 30 天" },
                                    ]}
                                    onChange={(value) => setForm((old) => ({ ...old, material_days: Number(value) }))}
                                />
                                <div className="space-y-2">
                                    <Label>最多使用素材</Label>
                                    <Input type="number" min={20} max={500} value={form.max_materials} onChange={(event) => setForm((old) => ({ ...old, max_materials: Number(event.target.value) }))} />
                                </div>
                                <InsightSelect label="状态" value={form.status} options={[{ value: "active", label: "启用" }, { value: "paused", label: "暂停" }]} onChange={(value) => setForm((old) => ({ ...old, status: value as "active" | "paused" }))} />
                            </div>
                        </section>

                        <section className="border-t border-slate-100 pt-5">
                            <div className="mb-3 text-sm font-black text-slate-900">提示词</div>
                            <Button
                                type="button"
                                variant="outline"
                                className="h-10 w-full justify-between bg-white"
                                onClick={() => setPromptExpanded((value) => !value)}
                            >
                                <span>查看领导固定模板与写作规则</span>
                                <ChevronDown className={promptExpanded ? "size-4 rotate-180 transition-transform" : "size-4 transition-transform"} />
                            </Button>
                            {promptExpanded ? (
                                <pre className="mt-2 max-h-72 overflow-auto whitespace-pre-wrap rounded-lg border border-slate-200 bg-slate-50 p-4 text-xs leading-6 text-slate-700">
                                    {options?.prompt_template || "提示词加载中"}
                                </pre>
                            ) : null}
                            <div className="mt-3 space-y-2">
                                <Label>本计划补充要求（可选）</Label>
                                <Textarea className="min-h-24 resize-none" value={form.prompt_override || ""} placeholder="只补充本计划特有的关注重点，不会覆盖领导固定格式。" onChange={(event) => setForm((old) => ({ ...old, prompt_override: event.target.value }))} />
                            </div>
                        </section>

                        <section className="border-t border-slate-100 pt-5">
                            <div className="flex items-center justify-between gap-4">
                                <div>
                                    <div className="flex items-center gap-2 text-sm font-black text-slate-900"><Send className="size-4 text-blue-600" />生成后推送</div>
                                    <div className="mt-1 text-xs text-slate-500">开启后，由独立机器人将云文档卡片发送给指定人员。</div>
                                </div>
                                <Switch
                                    checked={form.recipients.length > 0}
                                    onCheckedChange={(checked) => {
                                        if (checked) setRecipientPickerOpen(true);
                                        else setForm((old) => ({ ...old, recipients: [] }));
                                    }}
                                />
                            </div>
                            {form.recipients.length ? (
                                <div className="mt-4">
                                    <div className="mb-2 flex items-center justify-between">
                                        <span className="text-xs font-bold text-slate-500">已选 {form.recipients.length} 人</span>
                                        <Button type="button" variant="outline" size="sm" onClick={() => setRecipientPickerOpen(true)}>继续选择</Button>
                                    </div>
                                    <div className="grid gap-2 sm:grid-cols-2">
                                        {form.recipients.map((recipient) => (
                                            <div key={`${recipient.receive_id_type}-${recipient.receive_id}`} className="flex items-center gap-3 rounded-lg border border-slate-200 bg-white p-3">
                                                <div className="flex size-9 shrink-0 items-center justify-center rounded-full bg-blue-50 text-blue-700">
                                                    <UserRound className="size-4" />
                                                </div>
                                                <div className="min-w-0 flex-1">
                                                    <div className="truncate text-sm font-bold text-slate-900">{recipient.name || recipient.receive_id}</div>
                                                    <div className="mt-0.5 truncate text-xs text-slate-500">{recipient.receive_id}</div>
                                                </div>
                                                <Button
                                                    type="button"
                                                    variant="ghost"
                                                    size="icon"
                                                    className="size-8 shrink-0 text-slate-400 hover:text-rose-600"
                                                    title="移除"
                                                    onClick={() => setForm((old) => ({ ...old, recipients: old.recipients.filter((item) => item !== recipient) }))}
                                                >
                                                    <X className="size-4" />
                                                </Button>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            ) : (
                                <Button type="button" variant="outline" className="mt-4 bg-white" onClick={() => setRecipientPickerOpen(true)}>
                                    <UserRound className="size-4" />
                                    选择接收人
                                </Button>
                            )}
                        </section>
                    </div>
                    <DialogFooter className="shrink-0 border-t border-slate-100 px-6 py-4">
                        <Button variant="outline" onClick={() => setDialogOpen(false)}>取消</Button>
                        <Button disabled={!form.plan_name.trim() || saveMutation.isPending} onClick={() => saveMutation.mutate()}>
                            {saveMutation.isPending ? <Loader2 className="size-4 animate-spin" /> : null}
                            保存计划
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
            <FeishuRecipientPickerDialog
                open={recipientPickerOpen}
                selected={form.recipients}
                onOpenChange={setRecipientPickerOpen}
                onConfirm={(recipients) => setForm((old) => ({ ...old, recipients }))}
            />
        </PageContainer>
    );
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
