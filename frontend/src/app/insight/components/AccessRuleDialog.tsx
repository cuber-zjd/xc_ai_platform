import { useState } from "react";
import { Loader2, Plus, Trash2, Users } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";

import type { InsightAccessRuleRead } from "../api";
import { useInsightAccessRules, useInsightGrantAccessRule, useInsightGrantAccessRulesBulk, useInsightRevokeAccessRule } from "../hooks";
import { InsightSelect } from "./InsightSelect";

const principalOptions = [
    { value: "all", label: "全员" },
    { value: "user", label: "指定用户" },
    { value: "role", label: "指定角色" },
    { value: "dept", label: "指定部门" },
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
    const [principalId, setPrincipalId] = useState("");
    const [permission, setPermission] = useState("view");
    const rulesQuery = useInsightAccessRules(targetType, open ? targetId : null);
    const grantMutation = useInsightGrantAccessRule();
    const bulkGrantMutation = useInsightGrantAccessRulesBulk();
    const revokeMutation = useInsightRevokeAccessRule();
    const rules = rulesQuery.data ?? [];
    const bulkTargetIds = targetIds?.length ? Array.from(new Set(targetIds)) : [];
    const isBulk = bulkTargetIds.length > 1;
    const pending = grantMutation.isPending || bulkGrantMutation.isPending || revokeMutation.isPending;

    const handleGrant = () => {
        if (!targetId && !isBulk) return;
        if (principalType !== "all" && !principalId.trim()) {
            toast.error("请填写授权对象 ID");
            return;
        }
        const data = {
            principal_type: principalType,
            principal_id: principalType === "all" ? null : Number(principalId),
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
                        setPrincipalId("");
                    },
                    onError: () => toast.error("批量授权失败，请检查对象 ID"),
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
                    setPrincipalId("");
                },
                onError: () => toast.error("授权失败，请检查对象 ID"),
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
                        <div className="grid gap-3 md:grid-cols-[130px_minmax(0,1fr)_120px_auto] md:items-end">
                            <InsightSelect label="授权对象" value={principalType} options={principalOptions} onChange={setPrincipalType} />
                            <label className="space-y-2 text-sm font-bold text-slate-700">
                                对象 ID
                                <input
                                    value={principalId}
                                    onChange={(event) => setPrincipalId(event.target.value)}
                                    disabled={principalType === "all"}
                                    placeholder={principalType === "all" ? "全员无需填写" : "填写用户 / 角色 / 部门 ID"}
                                    className="h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm outline-none transition focus:border-primary disabled:bg-slate-100"
                                />
                            </label>
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
                                        {principalLabel(rule.principal_type)}
                                        {rule.principal_id ? ` #${rule.principal_id}` : ""}
                                    </div>
                                    <div className="mt-1 text-xs font-semibold text-slate-500">
                                        {permissionLabel(rule.permission)} · {rule.status === "active" ? "生效中" : rule.status}
                                    </div>
                                </div>
                                <Button type="button" variant="ghost" size="icon" className="size-9 rounded-xl text-red-500 hover:bg-red-50 hover:text-red-600" onClick={() => handleRevoke(rule)} disabled={pending}>
                                    {revokeMutation.isPending ? <Loader2 className="size-4 animate-spin" /> : <Trash2 className="size-4" />}
                                </Button>
                            </div>
                        ))}
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
