import { useMemo, useState } from "react";
import { CalendarClock, CircleStop, Clock3, Eye, Loader2, Play, RefreshCw, TimerReset, Zap } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

import type { InsightSchedulerRunLogRead } from "../api";
import { DemoCard } from "../components/DemoPrimitives";
import { InsightSelect } from "../components/InsightSelect";
import {
    useInsightRunSchedulerOnce,
    useInsightSchedulerLogs,
    useInsightSchedulerStatus,
    useInsightStartScheduler,
    useInsightStopScheduler,
} from "../hooks";
import { PageContainer } from "../layout/PageContainer";

const statusOptions = [
    { value: "", label: "全部状态" },
    { value: "success", label: "成功" },
    { value: "failed", label: "失败" },
    { value: "running", label: "执行中" },
];

export function ScheduledTasksPage() {
    const [page, setPage] = useState(1);
    const [size, setSize] = useState(20);
    const [status, setStatus] = useState("");
    const [dateFrom, setDateFrom] = useState("");
    const [dateTo, setDateTo] = useState("");
    const [detail, setDetail] = useState<InsightSchedulerRunLogRead | null>(null);
    const schedulerQuery = useInsightSchedulerStatus();
    const logsQuery = useInsightSchedulerLogs({
        page,
        size,
        status: status || undefined,
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
    });
    const runMutation = useInsightRunSchedulerOnce();
    const startMutation = useInsightStartScheduler();
    const stopMutation = useInsightStopScheduler();
    const scheduler = schedulerQuery.data;
    const logs = logsQuery.data?.items ?? [];
    const total = logsQuery.data?.total ?? 0;
    const totalPages = Math.max(1, Math.ceil(total / size));
    const busy = runMutation.isPending || startMutation.isPending || stopMutation.isPending;
    const recentTotals = useMemo(
        () => ({
            successful: logs.filter((item) => item.status === "success").length,
            failed: logs.filter((item) => item.status === "failed").length,
            tokens: logs.reduce((sum, item) => sum + item.total_tokens, 0),
        }),
        [logs],
    );

    const refresh = () => {
        void schedulerQuery.refetch();
        void logsQuery.refetch();
    };

    return (
        <PageContainer className="flex h-full min-h-0 flex-col gap-3 overflow-hidden">
            <DemoCard className="shrink-0 p-3">
                <div className="flex flex-wrap items-center justify-between gap-3">
                    <div className="flex min-w-0 flex-wrap items-center gap-3">
                        <span className={`size-2.5 rounded-full ${scheduler?.running ? "bg-emerald-500" : "bg-slate-300"}`} />
                        <div className="min-w-0">
                            <div className="text-sm font-black text-slate-900">情报采集与报告定时任务</div>
                            <div className="mt-0.5 text-xs font-semibold text-slate-500">
                                {scheduler?.running ? "正在等待下一次执行" : "当前未运行"} · 每日 {scheduler?.daily_time || "--"} · {scheduler?.timezone || "--"}
                            </div>
                        </div>
                        <Badge variant="outline" className="rounded-lg border-slate-200 bg-white text-slate-600">
                            下次 {formatDateTime(scheduler?.next_tick_at)}
                        </Badge>
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                        <Button
                            type="button"
                            variant="outline"
                            className="h-9 rounded-lg bg-white"
                            disabled={busy}
                            onClick={() => runMutation.mutate(undefined, {
                                onSuccess: () => {
                                    toast.success("本轮定时任务执行完成");
                                    refresh();
                                },
                                onError: () => toast.error("定时任务执行失败，请查看日志"),
                            })}
                        >
                            {runMutation.isPending ? <Loader2 className="size-4 animate-spin" /> : <Play className="size-4" />}
                            立即执行
                        </Button>
                        {scheduler?.running ? (
                            <Button
                                type="button"
                                variant="outline"
                                className="h-9 rounded-lg bg-white"
                                disabled={busy}
                                onClick={() => stopMutation.mutate(undefined, { onSuccess: () => toast.success("定时任务已停止") })}
                            >
                                <CircleStop className="size-4" />
                                停止
                            </Button>
                        ) : (
                            <Button
                                type="button"
                                className="h-9 rounded-lg bg-primary text-primary-foreground"
                                disabled={busy}
                                onClick={() => startMutation.mutate(undefined, { onSuccess: () => toast.success("定时任务已启动") })}
                            >
                                <Clock3 className="size-4" />
                                启动
                            </Button>
                        )}
                        <Button type="button" variant="ghost" size="icon" className="size-9 rounded-lg" onClick={refresh} title="刷新">
                            <RefreshCw className={`size-4 ${schedulerQuery.isFetching || logsQuery.isFetching ? "animate-spin" : ""}`} />
                        </Button>
                    </div>
                </div>
                <div className="mt-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
                    <StatusMetric icon={<CalendarClock className="size-4" />} label="每日发现" value={scheduler?.daily_discovery_enabled ? "全部监测对象" : "未启用"} />
                    <StatusMetric icon={<TimerReset className="size-4" />} label="最近成功" value={formatDateTime(scheduler?.last_success_at)} />
                    <StatusMetric icon={<Zap className="size-4" />} label="本页 Token" value={formatNumber(recentTotals.tokens)} />
                    <StatusMetric icon={<Clock3 className="size-4" />} label="本页结果" value={`${recentTotals.successful} 成功 / ${recentTotals.failed} 失败`} />
                </div>
            </DemoCard>

            <DemoCard className="flex min-h-0 flex-1 flex-col overflow-hidden">
                <div className="flex shrink-0 flex-wrap items-end gap-2 border-b border-slate-100 p-3">
                    <InsightSelect value={status} options={statusOptions} onChange={(value) => { setStatus(value); setPage(1); }} triggerClassName="h-9 w-32 rounded-lg" />
                    <DateFilter label="开始日期" value={dateFrom} onChange={(value) => { setDateFrom(value); setPage(1); }} />
                    <DateFilter label="结束日期" value={dateTo} onChange={(value) => { setDateTo(value); setPage(1); }} />
                    <InsightSelect
                        value={String(size)}
                        options={[20, 50, 100].map((value) => ({ value: String(value), label: `每页 ${value}` }))}
                        onChange={(value) => { setSize(Number(value)); setPage(1); }}
                        triggerClassName="h-9 w-28 rounded-lg"
                    />
                </div>
                <div className="min-h-0 flex-1 overflow-auto">
                    <Table>
                        <TableHeader className="sticky top-0 z-10 bg-slate-50">
                            <TableRow>
                                <TableHead>执行时间</TableHead>
                                <TableHead>触发方式</TableHead>
                                <TableHead>状态</TableHead>
                                <TableHead className="text-right">耗时</TableHead>
                                <TableHead className="text-right">每日发现</TableHead>
                                <TableHead className="text-right">深挖执行</TableHead>
                                <TableHead className="text-right">失败</TableHead>
                                <TableHead className="text-right">飞书同步</TableHead>
                                <TableHead className="text-right">模型调用</TableHead>
                                <TableHead className="text-right">Token</TableHead>
                                <TableHead className="w-20 text-right">详情</TableHead>
                            </TableRow>
                        </TableHeader>
                        <TableBody>
                            {logs.map((item) => (
                                <TableRow key={item.id}>
                                    <TableCell className="font-semibold text-slate-700">{formatDateTime(item.started_at)}</TableCell>
                                    <TableCell>{triggerLabel(item.triggered_by)}</TableCell>
                                    <TableCell><RunStatus status={item.status} /></TableCell>
                                    <TableCell className="text-right">{formatDuration(item.duration_seconds)}</TableCell>
                                    <TableCell className="text-right font-bold text-slate-800">{item.discovery_checked_count} 个 / {item.discovery_candidate_count} 条</TableCell>
                                    <TableCell className="text-right font-bold text-slate-800">{item.executed_count} / {item.due_count}</TableCell>
                                    <TableCell className="text-right">{item.failed_count + item.report_failed_count}</TableCell>
                                    <TableCell className="text-right">{item.feishu_created_count + item.feishu_updated_count}</TableCell>
                                    <TableCell className="text-right">{item.model_call_count}</TableCell>
                                    <TableCell className="text-right font-bold text-blue-700">{formatNumber(item.total_tokens)}</TableCell>
                                    <TableCell className="text-right">
                                        <Button type="button" variant="ghost" size="icon" className="size-8 rounded-lg" title="查看详情" onClick={() => setDetail(item)}>
                                            <Eye className="size-4" />
                                        </Button>
                                    </TableCell>
                                </TableRow>
                            ))}
                            {!logsQuery.isLoading && logs.length === 0 ? (
                                <TableRow><TableCell colSpan={11} className="h-40 text-center text-sm font-semibold text-slate-500">暂无定时任务日志</TableCell></TableRow>
                            ) : null}
                        </TableBody>
                    </Table>
                </div>
                <div className="flex shrink-0 items-center justify-between border-t border-slate-100 bg-slate-50 px-4 py-2">
                    <span className="text-xs font-semibold text-slate-500">共 {total} 次 · 第 {page} / {totalPages} 页</span>
                    <div className="flex gap-2">
                        <Button type="button" variant="outline" className="h-8 rounded-lg bg-white text-xs" disabled={page <= 1} onClick={() => setPage((value) => Math.max(1, value - 1))}>上一页</Button>
                        <Button type="button" variant="outline" className="h-8 rounded-lg bg-white text-xs" disabled={page >= totalPages} onClick={() => setPage((value) => Math.min(totalPages, value + 1))}>下一页</Button>
                    </div>
                </div>
            </DemoCard>

            <RunDetailDialog item={detail} onOpenChange={(open) => { if (!open) setDetail(null); }} />
        </PageContainer>
    );
}

function StatusMetric({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
    return <div className="flex min-w-0 items-center gap-3 rounded-lg border border-slate-100 bg-slate-50 px-3 py-2.5 text-sm"><span className="text-blue-600">{icon}</span><span className="text-xs font-semibold text-slate-500">{label}</span><span className="ml-auto truncate font-black text-slate-900">{value}</span></div>;
}

function DateFilter({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
    return <label className="grid gap-1 text-[11px] font-bold text-slate-500"><span>{label}</span><Input type="date" value={value} onChange={(event) => onChange(event.target.value)} className="h-9 w-40 rounded-lg bg-white" /></label>;
}

function RunStatus({ status }: { status: string }) {
    const config = status === "success" ? ["成功", "border-emerald-200 bg-emerald-50 text-emerald-700"] : status === "failed" ? ["失败", "border-red-200 bg-red-50 text-red-700"] : ["执行中", "border-blue-200 bg-blue-50 text-blue-700"];
    return <Badge variant="outline" className={`rounded-lg ${config[1]}`}>{config[0]}</Badge>;
}

function RunDetailDialog({ item, onOpenChange }: { item: InsightSchedulerRunLogRead | null; onOpenChange: (open: boolean) => void }) {
    return (
        <Dialog open={Boolean(item)} onOpenChange={onOpenChange}>
            <DialogContent className="max-h-[86dvh] overflow-hidden sm:max-w-3xl">
                <DialogHeader><DialogTitle>执行详情</DialogTitle><DialogDescription>{formatDateTime(item?.started_at)} · {triggerLabel(item?.triggered_by || "")}</DialogDescription></DialogHeader>
                {item ? <div className="min-h-0 space-y-4 overflow-y-auto pr-1">
                    <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
                        <StatusMetric icon={<Clock3 className="size-4" />} label="耗时" value={formatDuration(item.duration_seconds)} />
                        <StatusMetric icon={<Play className="size-4" />} label="每日覆盖" value={`${item.discovery_checked_count} 个`} />
                        <StatusMetric icon={<Zap className="size-4" />} label="Token" value={formatNumber(item.total_tokens)} />
                        <StatusMetric icon={<RefreshCw className="size-4" />} label="模型调用" value={`${item.model_call_count} 次`} />
                    </div>
                    <div className="rounded-xl border border-slate-200 bg-white p-4">
                        <div className="text-sm font-black text-slate-900">模型用量</div>
                        <div className="mt-3 space-y-2">
                            {item.token_models.map((model) => <div key={model.model} className="flex items-center justify-between gap-3 rounded-lg bg-slate-50 px-3 py-2 text-xs"><span className="truncate font-bold text-slate-700">{model.model}</span><span className="shrink-0 text-slate-500">{model.call_count} 次 · {formatNumber(model.total_tokens)} Token</span></div>)}
                            {item.token_models.length === 0 ? <div className="text-sm font-semibold text-slate-500">该历史任务未记录 Token，后续执行会自动统计。</div> : null}
                        </div>
                    </div>
                    {item.error_message ? <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm font-semibold leading-6 text-red-700">{item.error_message}</div> : null}
                    <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 text-xs leading-6 text-slate-600">
                        <div>每日发现：覆盖 {item.discovery_checked_count} 个监测对象，发现 {item.discovery_hit_count} 条，形成候选 {item.discovery_candidate_count} 条，渠道失败 {item.discovery_failed_count} 次</div><div>信号深挖：检查 {item.checked_count} 个，到期 {item.due_count} 个，执行 {item.executed_count} 个，失败 {item.failed_count} 个；单批上限只作用于深挖</div><div>定时报告：成功 {item.report_executed_count} 个，失败 {item.report_failed_count} 个</div><div>飞书同步：新增 {item.feishu_created_count} 条，更新 {item.feishu_updated_count} 条，失败 {item.feishu_failed_count} 条</div>
                    </div>
                </div> : null}
            </DialogContent>
        </Dialog>
    );
}

function triggerLabel(value: string) {
    if (value.startsWith("user:")) return "管理员手动执行";
    if (value.startsWith("scheduler:")) return "系统定时执行";
    return value || "系统执行";
}

function formatDateTime(value?: string | null) {
    if (!value) return "--";
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? value : date.toLocaleString("zh-CN", { hour12: false });
}

function formatDuration(seconds: number) {
    if (seconds < 60) return `${Math.round(seconds)} 秒`;
    return `${Math.floor(seconds / 60)} 分 ${Math.round(seconds % 60)} 秒`;
}

function formatNumber(value: number) {
    return new Intl.NumberFormat("zh-CN").format(value || 0);
}
