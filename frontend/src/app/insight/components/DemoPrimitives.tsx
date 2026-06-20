import type { ReactNode } from "react";
import { ChevronRight } from "lucide-react";

import { cn } from "@/lib/utils";

export type TagTone = "blue" | "cyan" | "green" | "orange" | "purple" | "red" | "slate";

const tagToneClass: Record<TagTone, string> = {
    blue: "bg-blue-50 text-blue-700 border-blue-100",
    cyan: "bg-cyan-50 text-cyan-700 border-cyan-100",
    green: "bg-emerald-50 text-emerald-700 border-emerald-100",
    orange: "bg-orange-50 text-orange-700 border-orange-100",
    purple: "bg-violet-50 text-violet-700 border-violet-100",
    red: "bg-red-50 text-red-700 border-red-100",
    slate: "bg-slate-50 text-slate-600 border-slate-200",
};

const iconToneClass = {
    blue: "from-blue-500 to-blue-600",
    cyan: "from-cyan-500 to-teal-500",
    green: "from-emerald-500 to-teal-500",
    orange: "from-orange-500 to-amber-500",
    red: "from-red-500 to-rose-500",
    purple: "from-violet-500 to-indigo-500",
};

export interface StatCardProps {
    title: string;
    value: string;
    compare?: string;
    delta?: string;
    loading?: boolean;
    tone?: keyof typeof iconToneClass;
    icon: ReactNode;
}

export function DemoCard({ children, className }: { children: ReactNode; className?: string }) {
    return <section className={cn("insight-demo-card min-w-0", className)}>{children}</section>;
}

export function DemoTag({ children, tone = "blue", className }: { children: ReactNode; tone?: TagTone; className?: string }) {
    return <span className={cn("inline-flex max-w-full items-center whitespace-nowrap rounded-md border px-2 py-1 text-xs font-semibold leading-none", tagToneClass[tone], className)}>{children}</span>;
}

export function StatCard({ title, value, compare, delta, loading = false, tone = "blue", icon }: StatCardProps) {
    return (
        <DemoCard className="relative flex min-h-24 items-center gap-3 overflow-hidden p-3 sm:min-h-28 sm:p-4">
            <div className={cn("flex size-10 shrink-0 items-center justify-center rounded-xl bg-linear-to-br text-white shadow-[0_10px_22px_rgba(37,99,235,0.18)] sm:size-11", iconToneClass[tone])}>
                <span className="[&_svg]:size-5">
                    {icon}
                </span>
            </div>
            <div className="min-w-0 flex-1">
                <div className="truncate text-sm font-semibold text-slate-600">{title}</div>
                <div className="mt-1 flex flex-wrap items-end gap-x-3 gap-y-1">
                    {loading ? (
                        <div className="h-8 w-20 animate-pulse rounded-lg bg-slate-200/80 sm:h-10" />
                    ) : (
                        <div className="text-3xl font-black leading-none text-slate-950 sm:text-4xl">{value}</div>
                    )}
                    {loading ? (
                        <div className="pb-1 text-xs font-bold text-slate-400 sm:text-sm">读取中</div>
                    ) : compare || delta ? (
                        <div className="flex items-center gap-2 pb-1 text-xs font-bold sm:text-sm">
                            {compare ? <span className="text-slate-500">{compare}</span> : null}
                            {delta ? <span className={cn(delta.startsWith("+") ? "text-teal-600" : "text-slate-500")}>{delta}</span> : null}
                        </div>
                    ) : null}
                </div>
            </div>
            <div className="pointer-events-none absolute -bottom-4 -right-2 text-blue-100/70 [&_svg]:size-20">{icon}</div>
        </DemoCard>
    );
}

export function RankList({ items, showViews }: { items: string[]; showViews?: boolean }) {
    return (
        <div className="space-y-4">
            {items.map((item, index) => (
                <div key={item} className="flex items-start gap-3">
                    <span
                        className={cn(
                            "mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-md text-xs font-black text-white",
                            index === 0 && "bg-red-500",
                            index === 1 && "bg-orange-500",
                            index === 2 && "bg-amber-500",
                            index > 2 && "bg-slate-300",
                        )}
                    >
                        {index + 1}
                    </span>
                    <div className="min-w-0 flex-1">
                        <div className="truncate text-sm font-bold text-slate-800">{item}</div>
                    </div>
                    {showViews ? <span className="text-xs text-slate-400">排序 {index + 1}</span> : null}
                </div>
            ))}
        </div>
    );
}

export function SectionHeader({ title, action = "查看更多" }: { title: string; action?: string }) {
    return (
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-lg font-black leading-tight text-slate-900 sm:text-xl">{title}</h2>
            <button type="button" className="inline-flex items-center gap-1 text-sm font-bold text-blue-600">
                {action}
                <ChevronRight className="size-4" />
            </button>
        </div>
    );
}

