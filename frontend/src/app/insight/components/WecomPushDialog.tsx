import { useMemo, useState } from "react";
import { Loader2, RefreshCw, Send } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";

import { useInsightCreateNotification, useInsightNotifications, useInsightRetryNotification } from "../hooks";
import { InsightSelect } from "./InsightSelect";

const recipientTypeOptions = [
    { value: "user", label: "用户" },
    { value: "dept", label: "部门" },
    { value: "role", label: "角色" },
    { value: "job", label: "岗位" },
    { value: "all", label: "全员" },
];

const retryableStatuses = new Set(["failed", "pending", "sent_mock"]);

export function WecomPushDialog({
    open,
    onOpenChange,
    targetType,
    targetId,
    targetTitle,
    defaultTitle,
    defaultContent,
}: {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    targetType: "report" | "intelligence";
    targetId: number | null;
    targetTitle: string;
    defaultTitle: string;
    defaultContent: string;
}) {
    const [title, setTitle] = useState(defaultTitle);
    const [content, setContent] = useState(defaultContent);
    const [recipientType, setRecipientType] = useState("user");
    const [recipientIds, setRecipientIds] = useState("");
    const [sendNow, setSendNow] = useState(true);
    const createMutation = useInsightCreateNotification();
    const retryMutation = useInsightRetryNotification();
    const notificationsQuery = useInsightNotifications({
        page: 1,
        size: 5,
        target_type: targetType,
        target_id: targetId ?? undefined,
        channel: "wecom",
    });
    const recipients = useMemo(
        () =>
            recipientType === "all"
                ? [{ recipient_type: "all", recipient_id: null }]
                : recipientIds
                      .split(/[\n,\s，]+/)
                      .map((item) => item.trim())
                      .filter(Boolean)
                      .map((item) => ({
                          recipient_type: recipientType,
                          recipient_id: recipientType === "user" ? null : /^\d+$/.test(item) ? Number(item) : null,
                          recipient_name: item,
                          wecom_userid: recipientType === "user" ? item : undefined,
                      })),
        [recipientIds, recipientType],
    );

    const handleSubmit = () => {
        if (!targetId) return;
        if (recipientType !== "all" && recipients.length === 0) {
            toast.error("请填写至少一个接收对象");
            return;
        }
        createMutation.mutate(
            {
                channel: "wecom",
                target_type: targetType,
                target_id: targetId,
                title: title.trim() || defaultTitle,
                content: content.trim() || defaultContent,
                recipient_scope: recipientType === "all" ? "all" : "selected",
                recipients,
                send_now: sendNow,
            },
            {
                onSuccess: (result) => {
                    const message =
                        result.status === "sent"
                            ? "企业微信已发送"
                            : result.status === "sent_mock"
                              ? "已生成企业微信模拟推送记录"
                              : "已创建企业微信推送任务";
                    toast.success(message);
                    onOpenChange(false);
                },
                onError: () => toast.error("推送任务创建失败，请确认当前账号有权访问目标内容"),
            },
        );
    };

    const handleRetry = (notificationId: number) => {
        retryMutation.mutate(notificationId, {
            onSuccess: (result) => {
                toast.success(result.status === "sent" ? "重试发送成功" : "已重新提交推送任务");
            },
            onError: () => toast.error("重试失败，请检查企业微信配置或接收人映射"),
        });
    };

    const recentNotifications = notificationsQuery.data?.items ?? [];

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="max-h-[86vh] overflow-y-auto rounded-2xl border-slate-200 bg-white sm:max-w-2xl">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2 text-xl font-black text-slate-950">
                        <Send className="size-5 text-primary" />
                        企业微信推送
                    </DialogTitle>
                    <DialogDescription>{targetTitle || "当前内容"} 的推送会先写入记录，并在后端完成目标权限校验。</DialogDescription>
                </DialogHeader>
                <div className="space-y-4">
                    <label className="block space-y-2 text-sm font-bold text-slate-700">
                        推送标题
                        <input
                            value={title}
                            onChange={(event) => setTitle(event.target.value)}
                            className="h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm outline-none transition focus:border-primary"
                        />
                    </label>
                    <label className="block space-y-2 text-sm font-bold text-slate-700">
                        推送内容
                        <textarea
                            value={content}
                            onChange={(event) => setContent(event.target.value)}
                            rows={5}
                            className="w-full resize-y rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm leading-7 text-slate-800 outline-none transition focus:border-primary"
                        />
                    </label>
                    <div className="grid gap-3 md:grid-cols-[140px_minmax(0,1fr)]">
                        <InsightSelect label="接收对象" value={recipientType} options={recipientTypeOptions} onChange={setRecipientType} />
                        <label className="block space-y-2 text-sm font-bold text-slate-700">
                            接收对象 ID / 工号 / 名称
                            <textarea
                                value={recipientIds}
                                onChange={(event) => setRecipientIds(event.target.value)}
                                disabled={recipientType === "all"}
                                rows={3}
                                placeholder={recipientType === "all" ? "全员无需填写" : "可用换行、逗号或空格分隔；用户可填写企业微信 UserID、工号或姓名"}
                                className="w-full resize-y rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm leading-6 text-slate-800 outline-none transition focus:border-primary disabled:bg-slate-100"
                            />
                        </label>
                    </div>
                    <label className="flex h-11 items-center justify-between rounded-xl border border-slate-200 bg-slate-50 px-4 text-sm font-bold text-slate-700">
                        立即推送
                        <input type="checkbox" checked={sendNow} onChange={(event) => setSendNow(event.target.checked)} className="size-4 accent-primary" />
                    </label>
                    <div className="rounded-xl border border-blue-100 bg-blue-50/70 px-4 py-3 text-xs font-semibold leading-5 text-blue-700">
                        接收对象可填写企业微信 UserID、工号或姓名；系统会先按平台用户匹配，匹配不到时按企业微信 UserID 发送。
                    </div>
                    <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
                        <div className="mb-3 flex items-center justify-between gap-3">
                            <span className="text-sm font-black text-slate-900">最近推送记录</span>
                            {notificationsQuery.isFetching ? <Loader2 className="size-4 animate-spin text-slate-400" /> : null}
                        </div>
                        <div className="space-y-2">
                            {recentNotifications.length === 0 ? (
                                <div className="text-xs font-semibold text-slate-500">暂无推送记录</div>
                            ) : (
                                recentNotifications.map((item) => (
                                    <div key={item.id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-white px-3 py-2 text-xs shadow-sm">
                                        <div className="min-w-0">
                                            <div className="truncate font-bold text-slate-800">{item.title}</div>
                                            <div className="mt-1 text-slate-500">{notificationStatusLabel(item.status)}</div>
                                            {item.error_message ? <div className="mt-1 line-clamp-2 text-red-600">{item.error_message}</div> : null}
                                        </div>
                                        {retryableStatuses.has(item.status) ? (
                                            <Button
                                                type="button"
                                                variant="outline"
                                                size="sm"
                                                className="h-8 rounded-lg border-slate-200 bg-white"
                                                disabled={retryMutation.isPending}
                                                onClick={() => handleRetry(item.id)}
                                            >
                                                {retryMutation.isPending ? <Loader2 className="size-3 animate-spin" /> : <RefreshCw className="size-3" />}
                                                重试
                                            </Button>
                                        ) : null}
                                    </div>
                                ))
                            )}
                        </div>
                    </div>
                </div>
                <div className="mt-5 insight-actions">
                    <Button type="button" variant="outline" className="rounded-xl border-slate-200 bg-white" onClick={() => onOpenChange(false)}>
                        取消
                    </Button>
                    <Button type="button" className="rounded-xl" onClick={handleSubmit} disabled={createMutation.isPending || !targetId}>
                        {createMutation.isPending ? <Loader2 className="size-4 animate-spin" /> : <Send className="size-4" />}
                        创建推送
                    </Button>
                </div>
            </DialogContent>
        </Dialog>
    );
}

function notificationStatusLabel(status: string) {
    const labels: Record<string, string> = {
        pending: "待发送",
        sent: "已发送",
        sent_mock: "模拟发送",
        failed: "发送失败",
        blocked: "已阻断",
    };
    return labels[status] ?? status;
}
