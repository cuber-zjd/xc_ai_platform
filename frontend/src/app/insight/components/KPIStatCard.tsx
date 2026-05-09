import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

interface KPIStatCardProps {
    label: string;
    value: string;
    trend?: string;
    tone?: "blue" | "cyan" | "green" | "amber";
    icon?: ReactNode;
    className?: string;
}

const toneClass = {
    blue: "bg-blue-50 text-blue-700 dark:bg-blue-950/40 dark:text-blue-300",
    cyan: "bg-cyan-50 text-cyan-700 dark:bg-cyan-950/40 dark:text-cyan-300",
    green: "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300",
    amber: "bg-amber-50 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300",
};

export function KPIStatCard({ label, value, trend, tone = "blue", icon, className }: KPIStatCardProps) {
    return (
        <div className={cn("insight-card p-5", className)}>
            <div className="flex items-start justify-between gap-3">
                <div className="text-sm font-medium text-muted-foreground">{label}</div>
                {icon && <div className={cn("flex size-9 items-center justify-center rounded-2xl", toneClass[tone])}>{icon}</div>}
            </div>
            <div className="mt-4 text-3xl font-black tracking-tight text-foreground">{value}</div>
            {trend && <div className="mt-2 text-xs font-semibold text-muted-foreground">{trend}</div>}
        </div>
    );
}
