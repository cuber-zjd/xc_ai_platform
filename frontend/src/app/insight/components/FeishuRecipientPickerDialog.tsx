import { useEffect, useMemo, useState } from "react";
import { Check, Search, UserRoundCheck } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";

import type { InsightFeishuBriefRecipient, InsightSelectorOption } from "../api";
import { useInsightSelectorDepts, useInsightSelectorUsers } from "../hooks";
import { InsightSelect } from "./InsightSelect";

export function FeishuRecipientPickerDialog({
    open,
    selected,
    onOpenChange,
    onConfirm,
}: {
    open: boolean;
    selected: InsightFeishuBriefRecipient[];
    onOpenChange: (open: boolean) => void;
    onConfirm: (recipients: InsightFeishuBriefRecipient[]) => void;
}) {
    const [keyword, setKeyword] = useState("");
    const [deptId, setDeptId] = useState("");
    const [draft, setDraft] = useState<InsightFeishuBriefRecipient[]>(selected);
    const usersQuery = useInsightSelectorUsers(keyword, deptId);
    const deptsQuery = useInsightSelectorDepts("");
    const users = usersQuery.data ?? [];
    const deptOptions = useMemo(
        () => [{ value: "", label: "全部部门" }, ...(deptsQuery.data ?? [])],
        [deptsQuery.data],
    );

    useEffect(() => {
        if (open) {
            setDraft(selected);
            setKeyword("");
            setDeptId("");
        }
    }, [open, selected]);

    const toggle = (user: InsightSelectorOption) => {
        const userId = user.employee_id || user.code;
        if (!userId) return;
        setDraft((current) => {
            const exists = current.some((item) => item.receive_id_type === "user_id" && item.receive_id === userId);
            if (exists) {
                return current.filter((item) => !(item.receive_id_type === "user_id" && item.receive_id === userId));
            }
            return [...current, { receive_id_type: "user_id", receive_id: userId, name: user.label }];
        });
    };

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="flex max-h-[86dvh] w-[min(820px,calc(100vw-32px))] max-w-none flex-col overflow-hidden p-0">
                <DialogHeader className="shrink-0 border-b border-slate-100 px-6 py-5">
                    <DialogTitle className="flex items-center gap-2">
                        <UserRoundCheck className="size-5 text-blue-600" />
                        选择飞书接收人
                    </DialogTitle>
                </DialogHeader>
                <div className="grid min-h-0 flex-1 gap-4 overflow-hidden p-5 md:grid-cols-[minmax(0,1fr)_280px]">
                    <div className="flex min-h-0 flex-col gap-3">
                        <div className="grid gap-2 sm:grid-cols-[180px_minmax(0,1fr)]">
                            <InsightSelect value={deptId} options={deptOptions} onChange={setDeptId} />
                            <div className="relative">
                                <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-400" />
                                <Input
                                    className="h-10 pl-9"
                                    value={keyword}
                                    placeholder="搜索姓名或工号"
                                    onChange={(event) => setKeyword(event.target.value)}
                                />
                            </div>
                        </div>
                        <div className="min-h-0 flex-1 overflow-y-auto rounded-lg border border-slate-200">
                            {users.map((user) => {
                                const userId = user.employee_id || user.code;
                                const checked = Boolean(
                                    userId
                                    && draft.some((item) => item.receive_id_type === "user_id" && item.receive_id === userId),
                                );
                                return (
                                    <Button
                                        key={user.value}
                                        type="button"
                                        variant="ghost"
                                        className="h-auto w-full justify-between rounded-none border-b border-slate-100 px-4 py-3 text-left hover:bg-blue-50"
                                        disabled={!userId}
                                        onClick={() => toggle(user)}
                                    >
                                        <span className="min-w-0">
                                            <span className="block truncate text-sm font-bold text-slate-900">{user.label}</span>
                                            <span className="mt-1 block truncate text-xs text-slate-500">{user.subtitle || userId || "未配置工号"}</span>
                                        </span>
                                        <span className={checked ? "flex size-6 shrink-0 items-center justify-center rounded-full bg-blue-600 text-white" : "size-6 shrink-0 rounded-full border border-slate-300 bg-white"}>
                                            {checked ? <Check className="size-4" /> : null}
                                        </span>
                                    </Button>
                                );
                            })}
                            {!users.length ? <div className="py-16 text-center text-sm text-slate-500">暂无匹配人员</div> : null}
                        </div>
                    </div>
                    <div className="min-h-0 overflow-y-auto rounded-lg border border-slate-200 bg-slate-50 p-3">
                        <div className="mb-3 text-xs font-bold text-slate-500">已选择 {draft.length} 人</div>
                        <div className="space-y-2">
                            {draft.map((item) => (
                                <div key={`${item.receive_id_type}-${item.receive_id}`} className="rounded-lg border border-slate-200 bg-white p-3">
                                    <div className="truncate text-sm font-bold text-slate-900">{item.name || item.receive_id}</div>
                                    <div className="mt-1 truncate text-xs text-slate-500">{item.receive_id}</div>
                                    <Button
                                        type="button"
                                        variant="ghost"
                                        size="sm"
                                        className="mt-2 h-7 px-2 text-xs text-rose-600 hover:text-rose-700"
                                        onClick={() => setDraft((current) => current.filter((row) => row !== item))}
                                    >
                                        移除
                                    </Button>
                                </div>
                            ))}
                            {!draft.length ? <div className="py-12 text-center text-xs text-slate-500">尚未选择接收人</div> : null}
                        </div>
                    </div>
                </div>
                <DialogFooter className="shrink-0 border-t border-slate-100 px-6 py-4">
                    <Button variant="outline" onClick={() => onOpenChange(false)}>取消</Button>
                    <Button
                        onClick={() => {
                            onConfirm(draft);
                            onOpenChange(false);
                        }}
                    >
                        确认选择
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
