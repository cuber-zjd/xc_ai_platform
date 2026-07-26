import { useEffect, useMemo, useState } from "react";
import { Check, DatabaseZap, Loader2, Table2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";

import type { InsightFeishuSyncResponse } from "../api";
import { useInsightFeishuSyncOptions, useInsightSyncToFeishu } from "../hooks";

export function FeishuSyncDialog({
    open,
    selectedIds,
    initialDateFrom,
    initialDateTo,
    onOpenChange,
}: {
    open: boolean;
    selectedIds: number[];
    initialDateFrom?: string;
    initialDateTo?: string;
    onOpenChange: (open: boolean) => void;
}) {
    const optionsQuery = useInsightFeishuSyncOptions();
    const syncMutation = useInsightSyncToFeishu();
    const [scope, setScope] = useState<"selected" | "date_range">("date_range");
    const [dateFrom, setDateFrom] = useState("");
    const [dateTo, setDateTo] = useState("");
    const [fieldCodes, setFieldCodes] = useState<string[]>([]);
    const [updateExisting, setUpdateExisting] = useState(true);
    const [ensureMetadata, setEnsureMetadata] = useState(true);
    const [result, setResult] = useState<InsightFeishuSyncResponse | null>(null);
    const options = optionsQuery.data;
    const requiredCodes = useMemo(() => new Set((options?.fields ?? []).filter((item) => item.required).map((item) => item.code)), [options?.fields]);

    useEffect(() => {
        if (!open) return;
        const range = defaultRange(initialDateFrom, initialDateTo);
        setScope(selectedIds.length > 0 ? "selected" : "date_range");
        setDateFrom(range.from);
        setDateTo(range.to);
        setResult(null);
    }, [initialDateFrom, initialDateTo, open, selectedIds.length]);

    useEffect(() => {
        if (!open || !options?.fields.length) return;
        setFieldCodes(options.fields.filter((item) => item.default_selected || item.required).map((item) => item.code));
    }, [open, options?.fields]);

    const toggleField = (code: string) => {
        if (requiredCodes.has(code)) return;
        setFieldCodes((current) => current.includes(code) ? current.filter((item) => item !== code) : [...current, code]);
    };

    const submit = () => {
        if (!options?.enabled) {
            toast.error(options?.warnings[0] || "飞书多维表格同步尚未启用");
            return;
        }
        if (scope === "selected" && selectedIds.length === 0) {
            toast.error("请先选择需要同步的情报");
            return;
        }
        if (scope === "date_range" && (!dateFrom || !dateTo)) {
            toast.error("请选择同步时间范围");
            return;
        }
        syncMutation.mutate(
            {
                scope,
                intelligence_ids: scope === "selected" ? selectedIds : [],
                date_from: scope === "date_range" ? `${dateFrom}T00:00:00` : undefined,
                date_to: scope === "date_range" ? `${dateTo}T23:59:59` : undefined,
                field_codes: fieldCodes,
                update_existing: updateExisting,
                ensure_metadata: ensureMetadata,
            },
            {
                onSuccess: (data) => {
                    setResult(data);
                    toast.success(`同步完成：新增 ${data.created_count} 条，更新 ${data.updated_count} 条`);
                },
                onError: (error) => toast.error(error instanceof Error && error.message ? error.message : "同步失败，请检查飞书配置或查看任务记录"),
            },
        );
    };

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="max-h-[88dvh] overflow-hidden sm:max-w-3xl">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2"><Table2 className="size-5 text-blue-600" />同步至飞书多维表格</DialogTitle>
                    <DialogDescription>选择需要同步的情报和内容，重复情报会按情报ID更新，不会重复新增。</DialogDescription>
                </DialogHeader>
                <div className="min-h-0 space-y-4 overflow-y-auto pr-1">
                    {options?.warnings.length ? <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm font-semibold leading-6 text-amber-800">{options.warnings.join("；")}</div> : null}

                    <section className="rounded-xl border border-slate-200 p-4">
                        <div className="text-sm font-black text-slate-900">同步范围</div>
                        <div className="mt-3 grid grid-cols-2 gap-2 rounded-xl bg-slate-100 p-1">
                            <ModeButton active={scope === "date_range"} onClick={() => setScope("date_range")} label="按发布时间" detail="选择一段时间" />
                            <ModeButton active={scope === "selected"} onClick={() => setScope("selected")} label="已选情报" detail={`${selectedIds.length} 条`} />
                        </div>
                        {scope === "date_range" ? <div className="mt-3 grid gap-3 sm:grid-cols-2"><DateField label="开始日期" value={dateFrom} onChange={setDateFrom} /><DateField label="结束日期" value={dateTo} onChange={setDateTo} /></div> : <div className="mt-3 rounded-xl border border-blue-100 bg-blue-50 px-4 py-3 text-sm font-bold text-blue-700">已选择 {selectedIds.length} 条正式情报</div>}
                    </section>

                    <section className="rounded-xl border border-slate-200 p-4">
                        <div className="flex items-center justify-between gap-3"><div><div className="text-sm font-black text-slate-900">同步内容</div><div className="mt-1 text-xs font-semibold text-slate-500">情报ID固定同步，其余内容可按需选择。</div></div><span className="text-xs font-bold text-slate-500">已选 {fieldCodes.length} 项</span></div>
                        <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                            {(options?.fields ?? []).map((field) => {
                                const checked = fieldCodes.includes(field.code);
                                return <Button key={field.code} type="button" variant="outline" aria-pressed={checked} className={`flex h-10 justify-start gap-2 rounded-lg px-3 text-left text-sm font-bold shadow-none ${checked ? "border-blue-200 bg-blue-50 text-blue-700 hover:bg-blue-50" : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50"}`} onClick={() => toggleField(field.code)}><span className={`grid size-5 place-items-center rounded-md border ${checked ? "border-blue-600 bg-blue-600 text-white" : "border-slate-300 bg-white"}`}>{checked ? <Check className="size-3.5" /> : null}</span><span className="truncate">{field.label}</span>{field.required ? <span className="ml-auto text-[10px] text-slate-400">固定</span> : null}</Button>;
                            })}
                        </div>
                    </section>

                    <section className="grid gap-2 sm:grid-cols-2">
                        <SettingButton active={updateExisting} title="更新已有记录" detail="同一情报再次同步时更新已选内容" onClick={() => setUpdateExisting((value) => !value)} />
                        <SettingButton active={ensureMetadata} title="自动补齐表格字段和选项" detail="新增分类、标签时不需要手工维护表格" onClick={() => setEnsureMetadata((value) => !value)} />
                    </section>

                    {result ? <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4"><div className="font-black text-emerald-800">同步完成</div><div className="mt-2 text-sm font-semibold leading-6 text-emerald-700">符合范围 {result.eligible_count} 条，新增 {result.created_count} 条，更新 {result.updated_count} 条，跳过 {result.skipped_count} 条，失败 {result.failed_count} 条。</div>{result.metadata_created_fields.length || result.metadata_updated_fields.length ? <div className="mt-2 text-xs font-semibold text-emerald-700">已补齐字段：{result.metadata_created_fields.join("、") || "无"}；已更新选项：{result.metadata_updated_fields.join("、") || "无"}</div> : null}</div> : null}
                </div>
                <DialogFooter>
                    <Button type="button" variant="outline" className="rounded-xl bg-white" onClick={() => onOpenChange(false)}>关闭</Button>
                    <Button type="button" className="rounded-xl bg-primary text-primary-foreground" disabled={syncMutation.isPending || !options?.enabled} onClick={submit}>{syncMutation.isPending ? <Loader2 className="size-4 animate-spin" /> : <DatabaseZap className="size-4" />}开始同步</Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

function ModeButton({ active, label, detail, onClick }: { active: boolean; label: string; detail: string; onClick: () => void }) {
    return <Button type="button" variant="ghost" className={`h-auto items-start justify-start rounded-lg px-3 py-2.5 text-left ${active ? "bg-white text-blue-700 shadow-sm hover:bg-white" : "text-slate-500 hover:text-slate-800"}`} onClick={onClick}><span><span className="block text-sm font-black">{label}</span><span className="mt-0.5 block text-xs font-semibold">{detail}</span></span></Button>;
}

function SettingButton({ active, title, detail, onClick }: { active: boolean; title: string; detail: string; onClick: () => void }) {
    return <Button type="button" variant="outline" aria-pressed={active} className={`h-auto items-start justify-start gap-3 rounded-xl p-3 text-left shadow-none ${active ? "border-blue-200 bg-blue-50 hover:bg-blue-50" : "border-slate-200 bg-white"}`} onClick={onClick}><span className={`mt-0.5 grid size-5 shrink-0 place-items-center rounded-full border ${active ? "border-blue-600 bg-blue-600 text-white" : "border-slate-300"}`}>{active ? <Check className="size-3.5" /> : null}</span><span><span className="block text-sm font-black text-slate-900">{title}</span><span className="mt-1 block whitespace-normal text-xs font-semibold leading-5 text-slate-500">{detail}</span></span></Button>;
}

function DateField({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
    return <label className="grid gap-1.5 text-xs font-bold text-slate-600"><span>{label}</span><Input type="date" className="h-10 rounded-lg bg-white" value={value} onChange={(event) => onChange(event.target.value)} /></label>;
}

function defaultRange(from?: string, to?: string) {
    const end = to || toDateInput(new Date());
    if (from) return { from, to: end };
    const start = new Date();
    start.setDate(start.getDate() - 6);
    return { from: toDateInput(start), to: end };
}

function toDateInput(value: Date) {
    const year = value.getFullYear();
    const month = String(value.getMonth() + 1).padStart(2, "0");
    const day = String(value.getDate()).padStart(2, "0");
    return `${year}-${month}-${day}`;
}
