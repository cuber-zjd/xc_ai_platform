import { useMemo, useState } from "react";
import { Check, Search, UserRoundCheck } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";

import type { InsightNotificationRecipient, InsightSelectorOption } from "../api";
import { useInsightSelectorDepts, useInsightSelectorRoles, useInsightSelectorUsers } from "../hooks";
import { InsightSelect } from "./InsightSelect";

const tabs = [
    { key: "user", label: "人员" },
    { key: "dept", label: "部门" },
    { key: "role", label: "角色" },
] as const;

type PickerTab = (typeof tabs)[number]["key"];

export function RecipientPickerDialog({
    open,
    onOpenChange,
    onConfirm,
}: {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    onConfirm: (recipients: InsightNotificationRecipient[]) => void;
}) {
    const [activeTab, setActiveTab] = useState<PickerTab>("user");
    const [keyword, setKeyword] = useState("");
    const [deptId, setDeptId] = useState("");
    const [selected, setSelected] = useState<InsightNotificationRecipient[]>([]);
    const usersQuery = useInsightSelectorUsers(keyword, deptId);
    const deptsQuery = useInsightSelectorDepts(activeTab === "dept" ? keyword : "");
    const rolesQuery = useInsightSelectorRoles(activeTab === "role" ? keyword : "");
    const deptOptions = useInsightSelectorDepts("");
    const rows = useMemo(() => {
        if (activeTab === "dept") return deptsQuery.data ?? [];
        if (activeTab === "role") return rolesQuery.data ?? [];
        return usersQuery.data ?? [];
    }, [activeTab, deptsQuery.data, rolesQuery.data, usersQuery.data]);

    const toggle = (item: InsightSelectorOption) => {
        const key = pickerKey(activeTab, item);
        setSelected((current) => {
            if (current.some((row) => recipientKey(row) === key)) {
                return current.filter((row) => recipientKey(row) !== key);
            }
            return [
                ...current,
                {
                    recipient_type: activeTab,
                    recipient_id: activeTab === "user" || activeTab === "role" ? Number(item.id) : null,
                    recipient_name: item.label,
                    wecom_userid: activeTab === "user" ? item.employee_id ?? item.code ?? item.label : null,
                },
            ];
        });
    };

    const isSelected = (item: InsightSelectorOption) => {
        const key = pickerKey(activeTab, item);
        return selected.some((row) => recipientKey(row) === key);
    };

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="flex max-h-[86dvh] flex-col overflow-hidden rounded-2xl border-slate-200 bg-white sm:max-w-3xl">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2 text-xl font-black text-slate-950">
                        <UserRoundCheck className="size-5 text-primary" />
                        选择接收对象
                    </DialogTitle>
                </DialogHeader>
                <div className="flex min-h-0 flex-1 flex-col gap-3">
                    <div className="flex flex-wrap items-center gap-2">
                        <div className="rounded-xl bg-slate-100 p-1">
                            {tabs.map((tab) => (
                                <button
                                    key={tab.key}
                                    type="button"
                                    className={activeTab === tab.key ? "h-9 rounded-lg bg-white px-4 text-sm font-black text-blue-600 shadow-sm" : "h-9 px-4 text-sm font-bold text-slate-500"}
                                    onClick={() => setActiveTab(tab.key)}
                                >
                                    {tab.label}
                                </button>
                            ))}
                        </div>
                        {activeTab === "user" ? (
                            <InsightSelect
                                value={deptId}
                                options={[{ value: "", label: "全部部门" }, ...(deptOptions.data ?? [])]}
                                triggerClassName="h-10"
                                className="min-w-40"
                                onChange={setDeptId}
                            />
                        ) : null}
                    </div>
                    <div className="relative">
                        <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-400" />
                        <Input
                            className="h-11 rounded-xl border-slate-200 bg-white pl-10 shadow-none"
                            placeholder="搜索姓名、工号、部门或角色"
                            value={keyword}
                            onChange={(event) => setKeyword(event.target.value)}
                        />
                    </div>
                    <div className="grid min-h-0 flex-1 gap-3 md:grid-cols-[minmax(0,1fr)_260px]">
                        <div className="min-h-[280px] overflow-y-auto rounded-xl border border-slate-200">
                            {rows.map((item) => (
                                <button
                                    key={`${activeTab}-${item.value}`}
                                    type="button"
                                    className="flex w-full items-center justify-between gap-3 border-b border-slate-100 px-4 py-3 text-left transition hover:bg-blue-50/60"
                                    onClick={() => toggle(item)}
                                >
                                    <span className="min-w-0">
                                        <span className="block truncate text-sm font-black text-slate-900">{item.label}</span>
                                        {item.subtitle ? <span className="mt-1 block truncate text-xs font-semibold text-slate-500">{item.subtitle}</span> : null}
                                    </span>
                                    <span className={isSelected(item) ? "flex size-6 items-center justify-center rounded-full bg-primary text-white" : "size-6 rounded-full border border-slate-200 bg-white"}>
                                        {isSelected(item) ? <Check className="size-4" /> : null}
                                    </span>
                                </button>
                            ))}
                            {rows.length === 0 ? <div className="px-4 py-10 text-center text-sm font-semibold text-slate-500">暂无匹配对象</div> : null}
                        </div>
                        <div className="min-h-[180px] overflow-y-auto rounded-xl border border-slate-200 bg-slate-50 p-3">
                            <div className="mb-2 text-xs font-black text-slate-500">已选 {selected.length} 个</div>
                            <div className="space-y-2">
                                {selected.map((item, index) => (
                                    <button
                                        key={`${item.recipient_type}-${item.recipient_id ?? item.recipient_name}-${index}`}
                                        type="button"
                                        className="flex w-full items-center justify-between rounded-lg bg-white px-3 py-2 text-left text-xs font-bold text-slate-700 shadow-sm"
                                        onClick={() => setSelected((current) => current.filter((_, itemIndex) => itemIndex !== index))}
                                    >
                                        <span className="truncate">{item.recipient_name || item.wecom_userid}</span>
                                        <span className="text-slate-400">移除</span>
                                    </button>
                                ))}
                            </div>
                        </div>
                    </div>
                </div>
                <DialogFooter>
                    <Button variant="outline" className="rounded-xl bg-white" onClick={() => onOpenChange(false)}>
                        取消
                    </Button>
                    <Button
                        className="rounded-xl bg-primary text-primary-foreground"
                        onClick={() => {
                            onConfirm(selected);
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

function pickerKey(type: PickerTab, item: InsightSelectorOption) {
    return `${type}:${type === "dept" ? item.label : item.id}`;
}

function recipientKey(item: InsightNotificationRecipient) {
    return `${item.recipient_type}:${item.recipient_type === "dept" ? item.recipient_name : item.recipient_id ?? item.recipient_name}`;
}
