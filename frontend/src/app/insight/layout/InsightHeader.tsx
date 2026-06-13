import { Bell, CalendarDays, ChevronDown, Search } from "lucide-react";

import { useAuthStore } from "@/store/useAuthStore";

export function InsightHeader() {
    const user = useAuthStore((state) => state.user);
    const displayName = user?.full_name?.trim() || user?.username?.trim() || "当前用户";
    const avatarText = getAvatarText(displayName);
    const todayLabel = formatTodayLabel();

    return (
        <header className="z-20 flex min-h-[var(--insight-header-height)] shrink-0 items-center justify-between border-b border-slate-200 bg-white/95 px-[var(--insight-space-page-x)] py-3 backdrop-blur-xl md:py-0">
            <div className="flex w-full min-w-0 flex-col gap-3 md:flex-row md:items-center md:justify-between md:gap-4">
                <label className="flex h-11 w-full min-w-0 items-center gap-3 rounded-xl border border-slate-200 bg-white px-4 text-sm shadow-sm transition focus-within:border-primary md:max-w-[420px]">
                    <Search className="size-4 text-slate-400" />
                    <input
                        className="min-w-0 flex-1 bg-transparent font-semibold text-slate-700 outline-none placeholder:text-slate-400"
                        placeholder="搜索企业、情报、报告、数据源..."
                    />
                    <span className="hidden rounded-md border border-slate-200 px-2 py-0.5 text-xs font-bold text-slate-400 sm:inline">/</span>
                </label>

                <div className="flex shrink-0 items-center justify-between gap-3 md:justify-end md:gap-6">
                    <div className="hidden items-center gap-2 text-sm font-bold text-slate-600 2xl:flex">
                        <CalendarDays className="size-4 text-slate-500" />
                        {todayLabel}
                    </div>
                    <button type="button" className="relative grid size-10 place-items-center rounded-full border border-slate-200 bg-white text-slate-600 shadow-sm">
                        <Bell className="size-4" />
                        <span className="absolute right-2 top-2 size-2 rounded-full bg-red-500" />
                    </button>
                    <div className="flex min-w-0 items-center gap-2 sm:gap-3" title={displayName}>
                        <div className="grid size-10 place-items-center rounded-full border border-blue-100 bg-linear-to-br from-blue-100 to-orange-100 text-sm font-black text-blue-700">{avatarText}</div>
                        <span className="hidden max-w-32 truncate text-sm font-bold text-slate-800 sm:inline">{displayName}</span>
                        <ChevronDown className="size-4 text-slate-500" />
                    </div>
                </div>
            </div>
        </header>
    );
}

function getAvatarText(name: string) {
    const first = Array.from(name.trim())[0];
    return first ? first.toUpperCase() : "用";
}

function formatTodayLabel() {
    return new Intl.DateTimeFormat("zh-CN", {
        year: "numeric",
        month: "long",
        day: "numeric",
        weekday: "long",
    }).format(new Date());
}
