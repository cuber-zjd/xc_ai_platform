import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Search, ShieldCheck } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";

import { insightApi, type InsightFeishuBriefPlanManagerRead, type InsightSelectorOption } from "../api";
import { useInsightSelectorDepts, useInsightSelectorUsers } from "../hooks";
import { InsightSelect } from "./InsightSelect";

export function FeishuBriefManagerDialog({
    open,
    planId,
    planName,
    ownerUserId,
    onOpenChange,
    onSaved,
}: {
    open: boolean;
    planId: number | null;
    planName: string;
    ownerUserId?: number | null;
    onOpenChange: (open: boolean) => void;
    onSaved: () => void;
}) {
    const queryClient = useQueryClient();
    const [keyword, setKeyword] = useState("");
    const [deptId, setDeptId] = useState("");
    const [addedManagers, setAddedManagers] = useState<InsightFeishuBriefPlanManagerRead[]>([]);
    const [removedUserIds, setRemovedUserIds] = useState<number[]>([]);
    const managersQuery = useQuery({
        queryKey: ["insight-feishu-brief-managers", planId],
        queryFn: () => insightApi.listFeishuBriefPlanManagers(planId as number),
        enabled: open && planId !== null,
    });
    const usersQuery = useInsightSelectorUsers(keyword, deptId);
    const deptsQuery = useInsightSelectorDepts("");
    const deptOptions = useMemo(
        () => [{ value: "", label: "全部部门" }, ...(deptsQuery.data ?? [])],
        [deptsQuery.data],
    );
    const draft = useMemo(
        () => [
            ...(managersQuery.data ?? []).filter((item) => !removedUserIds.includes(item.user_id)),
            ...addedManagers.filter(
                (item) => !(managersQuery.data ?? []).some((existing) => existing.user_id === item.user_id),
            ),
        ],
        [addedManagers, managersQuery.data, removedUserIds],
    );
    const saveMutation = useMutation({
        mutationFn: () => insightApi.replaceFeishuBriefPlanManagers(
            planId as number,
            draft.map((item) => item.user_id),
        ),
        onSuccess: () => {
            setAddedManagers([]);
            setRemovedUserIds([]);
            void queryClient.invalidateQueries({ queryKey: ["insight-feishu-brief-managers", planId] });
            toast.success("计划管理员已更新");
            onSaved();
            onOpenChange(false);
        },
        onError: () => toast.error("管理员保存失败，请确认当前账号是计划所有者或系统管理员"),
    });

    const toggle = (user: InsightSelectorOption) => {
        if (user.id === ownerUserId) return;
        const isSelected = draft.some((item) => item.user_id === user.id);
        const wasPersisted = (managersQuery.data ?? []).some((item) => item.user_id === user.id);
        if (isSelected) {
            setAddedManagers((current) => current.filter((item) => item.user_id !== user.id));
            if (wasPersisted) setRemovedUserIds((current) => [...current, user.id]);
            return;
        }
        setRemovedUserIds((current) => current.filter((userId) => userId !== user.id));
        if (!wasPersisted) {
            setAddedManagers((current) => [
                ...current,
                {
                    user_id: user.id,
                    full_name: user.label,
                    username: user.code || user.employee_id || user.value,
                    employee_id: user.employee_id,
                },
            ]);
        }
    };

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="flex max-h-[86dvh] w-[min(820px,calc(100vw-32px))] max-w-none flex-col overflow-hidden p-0">
                <DialogHeader className="shrink-0 border-b border-slate-100 px-6 py-5">
                    <DialogTitle className="flex items-center gap-2">
                        <ShieldCheck className="size-5 text-blue-600" />
                        配置计划管理员
                    </DialogTitle>
                    <DialogDescription>{planName}。管理员可编辑、调试、生成和临时调整计划，但不能删除计划或继续转授。</DialogDescription>
                </DialogHeader>
                <div className="grid min-h-0 flex-1 gap-4 overflow-hidden p-5 md:grid-cols-[minmax(0,1fr)_280px]">
                    <div className="flex min-h-0 flex-col gap-3">
                        <div className="grid gap-2 sm:grid-cols-[180px_minmax(0,1fr)]">
                            <InsightSelect value={deptId} options={deptOptions} onChange={setDeptId} />
                            <div className="relative">
                                <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-400" />
                                <Input className="h-10 pl-9" value={keyword} placeholder="搜索姓名或工号" onChange={(event) => setKeyword(event.target.value)} />
                            </div>
                        </div>
                        <div className="min-h-0 flex-1 overflow-y-auto rounded-lg border border-slate-200">
                            {(usersQuery.data ?? []).map((user) => {
                                const checked = draft.some((item) => item.user_id === user.id);
                                const isOwner = user.id === ownerUserId;
                                return (
                                    <Button
                                        key={user.value}
                                        type="button"
                                        variant="ghost"
                                        className="h-auto w-full justify-between rounded-none border-b border-slate-100 px-4 py-3 text-left hover:bg-blue-50"
                                        disabled={isOwner}
                                        onClick={() => toggle(user)}
                                    >
                                        <span className="min-w-0">
                                            <span className="block truncate text-sm font-bold text-slate-900">{user.label}{isOwner ? "（所有者）" : ""}</span>
                                            <span className="mt-1 block truncate text-xs text-slate-500">{user.subtitle || user.employee_id || user.code || "平台用户"}</span>
                                        </span>
                                        <span className={checked ? "flex size-6 shrink-0 items-center justify-center rounded-full bg-blue-600 text-white" : "size-6 shrink-0 rounded-full border border-slate-300 bg-white"}>
                                            {checked ? <Check className="size-4" /> : null}
                                        </span>
                                    </Button>
                                );
                            })}
                            {!usersQuery.isLoading && !(usersQuery.data ?? []).length ? <div className="py-16 text-center text-sm text-slate-500">暂无匹配人员</div> : null}
                        </div>
                    </div>
                    <div className="min-h-0 overflow-y-auto rounded-lg border border-slate-200 bg-slate-50 p-3">
                        <div className="mb-3 text-xs font-bold text-slate-500">已选择 {draft.length} 人</div>
                        <div className="space-y-2">
                            {draft.map((item) => (
                                <div key={item.user_id} className="rounded-lg border border-slate-200 bg-white p-3">
                                    <div className="truncate text-sm font-bold text-slate-900">{item.full_name}</div>
                                    <div className="mt-1 truncate text-xs text-slate-500">{item.employee_id || item.username}</div>
                                    <Button
                                        type="button"
                                        variant="ghost"
                                        size="sm"
                                        className="mt-2 h-7 px-2 text-xs text-rose-600 hover:text-rose-700"
                                        onClick={() => {
                                            setAddedManagers((current) => current.filter((row) => row.user_id !== item.user_id));
                                            if ((managersQuery.data ?? []).some((row) => row.user_id === item.user_id)) {
                                                setRemovedUserIds((current) => [...current, item.user_id]);
                                            }
                                        }}
                                    >
                                        移除
                                    </Button>
                                </div>
                            ))}
                            {!draft.length ? <div className="py-12 text-center text-xs text-slate-500">尚未选择计划管理员</div> : null}
                        </div>
                    </div>
                </div>
                <DialogFooter className="shrink-0 border-t border-slate-100 px-6 py-4">
                    <Button variant="outline" onClick={() => onOpenChange(false)}>取消</Button>
                    <Button disabled={!planId || managersQuery.isLoading || saveMutation.isPending} onClick={() => saveMutation.mutate()}>
                        保存管理员
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
