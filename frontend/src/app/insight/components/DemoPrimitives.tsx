import type { ReactNode } from "react";
import {
    ArrowRight,
    Bookmark,
    Building2,
    CalendarDays,
    Check,
    ChevronRight,
    CircleAlert,
    Database,
    ExternalLink,
    FileText,
    Flame,
    MoreHorizontal,
    Search,
    Sparkles,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
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

export function SearchField({ placeholder = "搜索企业、情报、报告、数据源..." }: { placeholder?: string }) {
    return (
        <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-400" />
            <Input className="h-11 rounded-xl border-slate-200 bg-white pl-10 text-sm shadow-none" placeholder={placeholder} />
        </div>
    );
}

export function FilterInput({ label, placeholder, wide }: { label: string; placeholder: string; wide?: boolean }) {
    return (
        <label className={cn("grid min-w-0 gap-2", wide ? "sm:min-w-72 sm:flex-1" : "sm:min-w-44")}>
            <span className="text-sm font-bold text-slate-700">{label}</span>
            <Input className="h-11 rounded-xl border-slate-200 bg-white shadow-none" placeholder={placeholder} />
        </label>
    );
}

export function FilterSelect({ label, value, wide }: { label: string; value: string; wide?: boolean }) {
    return (
        <label className={cn("grid min-w-0 gap-2", wide ? "sm:min-w-72 sm:flex-1" : "sm:min-w-44")}>
            <span className="text-sm font-bold text-slate-700">{label}</span>
            <button type="button" className="flex h-11 items-center justify-between rounded-xl border border-slate-200 bg-white px-4 text-sm text-slate-600">
                {value}
                <ChevronRight className="size-4 rotate-90 text-slate-400" />
            </button>
        </label>
    );
}

export function MiniLineChart({ className, points = [32, 41, 28, 35, 52, 64, 38] }: { className?: string; points?: number[] }) {
    const width = 560;
    const height = 240;
    const max = 100;
    const step = width / (points.length - 1);
    const coords = points.map((value, index) => [index * step, height - (value / max) * (height - 30) - 10]);
    const line = coords.map(([x, y]) => `${x},${y}`).join(" ");
    const area = `0,${height} ${line} ${width},${height}`;

    return (
        <div className={cn("h-full w-full", className)}>
            <svg viewBox={`0 0 ${width} ${height}`} className="h-full w-full overflow-visible">
                {[40, 80, 120, 160, 200].map((y) => (
                    <line key={y} x1="0" x2={width} y1={y} y2={y} stroke="#dbeafe" strokeDasharray="4 4" />
                ))}
                <polygon points={area} fill="url(#insightLineArea)" />
                <polyline points={line} fill="none" stroke="#1677ff" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" />
                {coords.map(([x, y], index) => (
                    <g key={`${x}-${y}`}>
                        <circle cx={x} cy={y} r="6" fill="#1677ff" stroke="#fff" strokeWidth="3" />
                        <text x={x} y={y - 14} textAnchor="middle" className="fill-slate-700 text-xs font-bold">
                            {points[index]}
                        </text>
                    </g>
                ))}
                <defs>
                    <linearGradient id="insightLineArea" x1="0" x2="0" y1="0" y2="1">
                        <stop offset="0%" stopColor="#1677ff" stopOpacity="0.18" />
                        <stop offset="100%" stopColor="#1677ff" stopOpacity="0.02" />
                    </linearGradient>
                </defs>
            </svg>
            <div className="mt-2 grid grid-cols-7 text-center text-xs text-slate-500">
                {["05-15", "05-16", "05-17", "05-18", "05-19", "05-20", "05-21"].map((day) => (
                    <span key={day}>{day}</span>
                ))}
            </div>
        </div>
    );
}

export function DonutChart({ total = "1,256", label = "条", compact }: { total?: string; label?: string; compact?: boolean }) {
    const segments = [
        ["#1d74ff", "38.2%"],
        ["#6657f5", "24.0%"],
        ["#ffc44d", "22.7%"],
        ["#55cfc2", "15.1%"],
    ];

    return (
        <div className={cn("flex flex-col items-center justify-center gap-5 sm:flex-row sm:gap-8", compact && "sm:gap-5")}>
            <div className={cn("relative rounded-full", compact ? "size-36" : "size-48")}>
                <div
                    className="absolute inset-0 rounded-full"
                    style={{
                        background: "conic-gradient(#1d74ff 0 38%, #6657f5 38% 62%, #ffc44d 62% 84%, #55cfc2 84% 100%)",
                    }}
                />
                <div className="absolute inset-6 flex flex-col items-center justify-center rounded-full bg-white text-center shadow-inner">
                    <span className="text-sm text-slate-600">合计</span>
                    <strong className={cn("font-black text-slate-950", compact ? "text-2xl" : "text-3xl")}>{total}</strong>
                    <span className="text-sm text-slate-600">{label}</span>
                </div>
            </div>
            <div className="w-full space-y-3 text-sm sm:w-auto">
                {segments.map(([color, value], index) => (
                    <div key={color} className="flex items-center gap-3">
                        <span className="size-2.5 rounded-sm" style={{ backgroundColor: color }} />
                        <span className="min-w-16 text-slate-700">{["官网", "财报公告", "行业资讯", "公众号"][index]}</span>
                        <span className="font-semibold text-slate-600">{value}</span>
                    </div>
                ))}
            </div>
        </div>
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
                        <div className="mt-1 text-xs text-slate-500">{["奈雪的茶", "中粮科技", "不二制油", "瑞幸咖啡", "山松生物"][index] ?? "行业资讯"}</div>
                    </div>
                    {showViews && <span className="text-xs text-slate-400">{[2356, 1872, 1654, 1231, 987][index]}</span>}
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

export function CompanyLogo({ name, color = "green" }: { name: string; color?: "green" | "blue" | "red" | "orange" | "slate" }) {
    const classes = {
        green: "bg-lime-500",
        blue: "bg-blue-500",
        red: "bg-red-500",
        orange: "bg-orange-500",
        slate: "bg-slate-600",
    };

    return <div className={cn("flex size-10 shrink-0 items-center justify-center rounded-lg text-xs font-black text-white", classes[color])}>{name.slice(0, 2)}</div>;
}

export function HeaderMeta() {
    return (
        <div className="flex flex-wrap items-center gap-6 text-sm font-semibold text-slate-600">
            <span className="inline-flex items-center gap-2">
                <CalendarDays className="size-4 text-slate-500" />
                2025年5月21日 星期三
            </span>
            <span className="relative inline-flex">
                <span className="absolute -right-1 -top-1 flex size-4 items-center justify-center rounded-full bg-red-500 text-[10px] text-white">5</span>
                <Flame className="size-5 text-slate-500" />
            </span>
        </div>
    );
}

export function PrimaryAction({ children, icon = <Sparkles className="size-4" /> }: { children: ReactNode; icon?: ReactNode }) {
    return (
        <Button className="h-11 rounded-xl px-5">
            {icon}
            {children}
        </Button>
    );
}

export function StatusPill({ ok = true, children = "已启用" }: { ok?: boolean; children?: ReactNode }) {
    return (
        <span className={cn("inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-bold", ok ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-700")}>
            <span className={cn("size-2 rounded-full", ok ? "bg-emerald-500" : "bg-amber-500")} />
            {children}
        </span>
    );
}

export function OperationIconRow() {
    return (
        <div className="flex items-center gap-3 text-slate-500">
            <Bookmark className="size-4" />
            <MoreHorizontal className="size-5" />
        </div>
    );
}

export function SuggestionList() {
    return (
        <div className="space-y-3">
            {["关注植物基蛋白在乳制品与休闲食品中的替代机会", "跟踪头部茶饮品牌夏季新品对原料需求的拉动", "留意企业在精准营养与功能复合方向的布局"].map((item) => (
                <div key={item} className="flex items-start gap-2 text-sm text-slate-700">
                    <span className="flex size-5 items-center justify-center rounded-full bg-emerald-500 text-white">
                        <Check className="size-3" />
                    </span>
                    {item}
                </div>
            ))}
        </div>
    );
}

export function SourceIcon({ type }: { type: "database" | "file" | "alert" | "building" }) {
    const icons = {
        database: <Database className="size-6" />,
        file: <FileText className="size-6" />,
        alert: <CircleAlert className="size-6" />,
        building: <Building2 className="size-6" />,
    };
    return icons[type];
}

export function LinkButton({ children }: { children: ReactNode }) {
    return (
        <button type="button" className="inline-flex items-center gap-1 text-sm font-bold text-blue-600">
            {children}
            <ArrowRight className="size-4" />
        </button>
    );
}

export function ExternalButton({ children }: { children: ReactNode }) {
    return (
        <Button variant="outline" className="h-10 rounded-xl">
            {children}
            <ExternalLink className="size-4" />
        </Button>
    );
}
