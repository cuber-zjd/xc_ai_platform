import { useMemo, useState } from "react";
import { Check, Loader2, Plus, Search, Trash2, UserRoundCheck, Users } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";

import type { InsightAccessRuleRead, InsightSelectorOption } from "../api";
import {
    useInsightAccessRules,
    useInsightGrantAccessRule,
    useInsightGrantAccessRulesBulk,
    useInsightRevokeAccessRule,
    useInsightSelectorCompanies,
    useInsightSelectorDepts,
    useInsightSelectorRoles,
    useInsightSelectorUsers,
} from "../hooks";
import { InsightSelect } from "./InsightSelect";

const principalOptions = [
    { value: "all", label: "全员" },
    { value: "user", label: "指定用户" },
    { value: "dept", label: "指定部门" },
    { value: "role", label: "指定角色" },
    { value: "sys_company", label: "所属公司" },
];

const permissionOptions = [
    { value: "view", label: "可查看" },
    { value: "edit", label: "可编辑" },
    { value: "owner", label: "所有者" },
];

export function AccessRuleDialog({
    open,
    onOpenChange,
    targetType,
    targetId,
    targetIds,
    targetName,
}: {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    targetType: string;
    targetId: number | null;
    targetIds?: number[];
    targetName: string;
}) {
    const [principalType, setPrincipalType] = useState("all");
    const [keyword, setKeyword] = useState("");
    const [pickerOpen, setPickerOpen] = useState(false);
    const [selectedPrincipal, setSelectedPrincipal] = useState<InsightSelectorOption | null>(null);
    const [permission, setPermission] = useState("view");
    const rulesQuery = useInsightAccessRules(targetType, open ? targetId : null);
    const usersQuery = useInsightSelectorUsers(pickerOpen && principalType === "user" ? keyword : "");
    const deptsQuery = useInsightSelectorDepts(pickerOpen && principalType === "dept" ? keyword : "");
    const rolesQuery = useInsightSelectorRoles(pickerOpen && principalType === "role" ? keyword : "");
    const companiesQuery = useInsightSelectorCompanies(pickerOpen && principalType === "sys_company" ? keyword : "");
    const grantMutation = useInsightGrantAccessRule();
    const bulkGrantMutation = useInsightGrantAccessRulesBulk();
    const revokeMutation = useInsightRevokeAccessRule();
    const rules = rulesQuery.data ?? [];
    const selectorRows = useMemo(() => {
        if (principalType === "user") return usersQuery.data ?? [];
        if (principalType === "dept") return deptsQuery.data ?? [];
        if (principalType === "role") return rolesQuery.data ?? [];
        if (principalType === "sys_company") return companiesQuery.data ?? [];
        return [];
    }, [companiesQuery.data, deptsQuery.data, principalType, rolesQuery.data, usersQuery.data]);
    const bulkTargetIds = targetIds?.length ? Array.from(new Set(targetIds)) : [];
    const isBulk = bulkTargetIds.length > 1;
    const pending = grantMutation.isPending || bulkGrantMutation.isPending || revokeMutation.isPending;

    const handleGrant = () => {
        if (!targetId && !isBulk) return;
        if (principalType !== "all" && !selectedPrincipal) {
            toast.error("请先选择授权对象");
            return;
        }
        const data = {
            principal_type: principalType,
            principal_id: principalType === "all" ? null : Number(selectedPrincipal?.id),
            permission,
            grant_type: "manual",
        };
        if (isBulk) {
            bulkGrantMutation.mutate(
                {
                    targetType,
                    data: {
                        ...data,
                        target_ids: bulkTargetIds,
                    },
                },
                {
                    onSuccess: (result) => {
                        toast.success(`已批量更新 ${result.target_count} 个对象权限`);
                        setSelectedPrincipal(null);
                    },
                    onError: () => toast.error("批量授权失败，请检查授权对象"),
                },
            );
            return;
        }
        grantMutation.mutate(
            {
                targetType,
                targetId: targetId ?? 0,
                data,
            },
            {
                onSuccess: () => {
                    toast.success("授权已保存");
                    setSelectedPrincipal(null);
                },
                onError: () => toast.error("授权失败，请检查授权对象"),
            },
        );
    };

    const handleRevoke = (rule: InsightAccessRuleRead) => {
        if (!targetId) return;
        revokeMutation.mutate(
            { targetType, targetId, ruleId: rule.id },
            {
                onSuccess: () => toast.success("授权已移除"),
                onError: () => toast.error("移除授权失败"),
            },
        );
    };

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="max-h-[86vh] overflow-hidden rounded-2xl border-slate-200 bg-white p-0 sm:max-w-2xl">
                <DialogHeader className="border-b border-slate-100 px-6 py-5">
                    <DialogTitle className="flex items-center gap-2 text-xl font-black text-slate-950">
                        <Users className="size-5 text-primary" />
                        权限配置
                    </DialogTitle>
                    <DialogDescription>
                        {isBulk ? `将批量调整 ${bulkTargetIds.length} 个对象的可见与协作权限。` : `${targetName || "当前对象"} 的可见与协作权限会在后端过滤生效。`}
                    </DialogDescription>
                </DialogHeader>
                <div className="max-h-[68vh] overflow-y-auto p-5">
                    <div className="rounded-2xl border border-slate-200 bg-slate-50/80 p-4">
                        <div className="grid gap-3 md:grid-cols-[150px_minmax(0,1fr)_120px_auto] md:items-end">
                            <InsightSelect
                                label="授权类型"
                                value={principalType}
                                options={principalOptions}
                                onChange={(value) => {
                                    setPrincipalType(value);
                                    setKeyword("");
                                    setSelectedPrincipal(null);
                                }}
                            />
                            <PrincipalSelector
                                principalType={principalType}
                                selected={selectedPrincipal}
                                onOpenPicker={() => {
                                    setKeyword("");
                                    setPickerOpen(true);
                                }}
                            />
                            <InsightSelect label="权限" value={permission} options={permissionOptions} onChange={setPermission} />
                            <Button type="button" className="h-10 rounded-xl" onClick={handleGrant} disabled={pending || (!targetId && !isBulk)}>
                                {grantMutation.isPending || bulkGrantMutation.isPending ? <Loader2 className="size-4 animate-spin" /> : <Plus className="size-4" />}
                                {isBulk ? "批量添加" : "添加"}
                            </Button>
                        </div>
                    </div>

                    <div className="mt-4 space-y-2">
                        {isBulk ? (
                            <div className="rounded-xl border border-blue-100 bg-blue-50 p-4 text-sm font-semibold leading-6 text-blue-800">
                                批量模式只会为选中的 {bulkTargetIds.length} 个对象添加或更新同一条授权规则，不会删除它们已有的其他授权。
                            </div>
                        ) : null}
                        {!isBulk && rulesQuery.isLoading ? (
                            <div className="rounded-xl border border-dashed border-slate-200 p-6 text-center text-sm font-semibold text-slate-500">正在读取授权规则...</div>
                        ) : null}
                        {!isBulk && !rulesQuery.isLoading && rules.length === 0 ? (
                            <div className="rounded-xl border border-dashed border-slate-200 p-6 text-center text-sm font-semibold text-slate-500">暂无额外授权，仅所有者和管理员可访问。</div>
                        ) : null}
                        {!isBulk && rules.map((rule) => (
                            <div key={rule.id} className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white px-4 py-3">
                                <div className="min-w-0">
                                    <div className="text-sm font-black text-slate-800">
                                        {rule.principal_name || principalLabel(rule.principal_type)}
                                    </div>
                                    <div className="mt-1 text-xs font-semibold text-slate-500">
                                        {principalMeta(rule)} · {permissionLabel(rule.permission)} · {rule.status === "active" ? "生效中" : rule.status}
                                    </div>
                                </div>
                                <Button type="button" variant="ghost" size="icon" className="size-9 rounded-xl text-red-500 hover:bg-red-50 hover:text-red-600" onClick={() => handleRevoke(rule)} disabled={pending}>
                                    {revokeMutation.isPending ? <Loader2 className="size-4 animate-spin" /> : <Trash2 className="size-4" />}
                                </Button>
                            </div>
                        ))}
                    </div>
                </div>
                <PrincipalPickerDialog
                    open={pickerOpen}
                    onOpenChange={setPickerOpen}
                    principalType={principalType}
                    keyword={keyword}
                    selected={selectedPrincipal}
                    rows={selectorRows}
                    onKeywordChange={setKeyword}
                    onClear={() => setSelectedPrincipal(null)}
                    onSelect={(item) => {
                        setSelectedPrincipal(item);
                        setPickerOpen(false);
                    }}
                />
            </DialogContent>
        </Dialog>
    );
}

function PrincipalSelector({
    principalType,
    selected,
    onOpenPicker,
}: {
    principalType: string;
    selected: InsightSelectorOption | null;
    onOpenPicker: () => void;
}) {
    if (principalType === "all") {
        return (
            <div className="space-y-2 text-sm font-bold text-slate-700">
                授权范围
                <div className="flex h-10 items-center rounded-xl border border-slate-200 bg-white px-3 text-sm font-semibold text-slate-500">全员可按所选权限访问</div>
            </div>
        );
    }
    return (
        <div className="space-y-2 text-sm font-bold text-slate-700">
            选择对象
            {selected ? (
                <div className="flex min-h-10 items-center justify-between gap-3 rounded-xl border border-blue-100 bg-white px-3 py-2 shadow-sm">
                    <span className="min-w-0">
                        <span className="block truncate text-sm font-black text-slate-900">{selected.label}</span>
                        {selected.subtitle ? <span className="mt-0.5 block truncate text-xs font-semibold text-slate-500">{selected.subtitle}</span> : null}
                    </span>
                    <button type="button" className="shrink-0 text-xs font-black text-primary hover:underline" onClick={onOpenPicker}>
                        更换
                    </button>
                </div>
            ) : (
                <button
                    type="button"
                    className="flex h-10 w-full items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white px-3 text-left text-sm font-semibold text-slate-700 transition hover:border-blue-200 hover:bg-blue-50/50"
                    onClick={onOpenPicker}
                >
                    <span className="min-w-0 truncate">
                        {`点击选择${principalLabel(principalType).replace("指定", "")}`}
                    </span>
                    <Search className="size-4 shrink-0 text-slate-400" />
                </button>
            )}
        </div>
    );
}

function PrincipalPickerDialog({
    open,
    onOpenChange,
    principalType,
    keyword,
    selected,
    rows,
    onKeywordChange,
    onClear,
    onSelect,
}: {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    principalType: string;
    keyword: string;
    selected: InsightSelectorOption | null;
    rows: InsightSelectorOption[];
    onKeywordChange: (value: string) => void;
    onClear: () => void;
    onSelect: (item: InsightSelectorOption) => void;
}) {
    if (principalType === "all") return null;
    const title = `选择${principalLabel(principalType).replace("指定", "")}`;
    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="flex max-h-[82dvh] flex-col overflow-hidden rounded-2xl border-slate-200 bg-white p-0 sm:max-w-2xl">
                <DialogHeader className="border-b border-slate-100 px-5 py-4">
                    <DialogTitle className="flex items-center gap-2 text-lg font-black text-slate-950">
                        <UserRoundCheck className="size-5 text-primary" />
                        {title}
                    </DialogTitle>
                    <DialogDescription>搜索后点击一项即可带回授权配置。</DialogDescription>
                </DialogHeader>
                <div className="flex min-h-0 flex-1 flex-col gap-3 p-4">
                    <div className="relative">
                        <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-400" />
                        <Input
                            autoFocus
                            className="h-11 rounded-xl border-slate-200 bg-white pl-10 shadow-none"
                            placeholder={`搜索${title.replace("选择", "")}名称、编码或工号`}
                            value={keyword}
                            onChange={(event) => onKeywordChange(event.target.value)}
                        />
                    </div>
                    <div className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2">
                        <div className="mb-2 text-xs font-black text-slate-500">已选择</div>
                        {selected ? (
                            <div className="flex items-center justify-between gap-3 rounded-xl border border-blue-100 bg-white px-3 py-2">
                                <span className="min-w-0">
                                    <span className="block truncate text-sm font-black text-slate-900">{selected.label}</span>
                                    {selected.subtitle ? <span className="mt-1 block truncate text-xs font-semibold text-slate-500">{selected.subtitle}</span> : null}
                                </span>
                                <Button type="button" variant="ghost" size="sm" className="h-8 rounded-lg text-slate-500 hover:text-red-500" onClick={onClear}>
                                    清除
                                </Button>
                            </div>
                        ) : (
                            <div className="rounded-xl border border-dashed border-slate-200 bg-white px-3 py-3 text-sm font-semibold text-slate-500">
                                还没有选择对象。
                            </div>
                        )}
                    </div>
                    <div className="min-h-[260px] overflow-y-auto rounded-xl border border-slate-200 bg-white">
                        {rows.map((item) => {
                            const active = selected?.value === item.value;
                            return (
                                <button
                                    key={`${principalType}-${item.value}`}
                                    type="button"
                                    className={`flex w-full items-center justify-between gap-3 border-b border-slate-100 px-4 py-3 text-left transition ${
                                        active ? "bg-blue-50 text-blue-900" : "hover:bg-blue-50/60"
                                    }`}
                                    onClick={() => onSelect(item)}
                                >
                                    <span className="min-w-0">
                                        <span className="block truncate text-sm font-black text-slate-900">{item.label}</span>
                                        {item.subtitle ? <span className="mt-1 block truncate text-xs font-semibold text-slate-500">{item.subtitle}</span> : null}
                                    </span>
                                    <span className={active ? "flex size-6 items-center justify-center rounded-full bg-primary text-white" : "size-6 rounded-full border border-slate-200 bg-white"}>
                                        {active ? <Check className="size-4" /> : null}
                                    </span>
                                </button>
                            );
                        })}
                        {rows.length === 0 ? (
                            <div className="flex min-h-[260px] items-center justify-center text-sm font-semibold text-slate-500">暂无匹配对象</div>
                        ) : null}
                    </div>
                </div>
            </DialogContent>
        </Dialog>
    );
}

function principalLabel(value: string) {
    return principalOptions.find((option) => option.value === value)?.label ?? value;
}

function permissionLabel(value: string) {
    return permissionOptions.find((option) => option.value === value)?.label ?? value;
}

function principalMeta(rule: InsightAccessRuleRead) {
    if (rule.principal_type === "all") return "全员";
    return [principalLabel(rule.principal_type), rule.principal_code || (rule.principal_id ? `#${rule.principal_id}` : "")].filter(Boolean).join(" · ");
}
