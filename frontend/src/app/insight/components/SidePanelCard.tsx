import type { PropsWithChildren } from "react";

import { cn } from "@/lib/utils";

interface SidePanelCardProps extends PropsWithChildren {
    title: string;
    className?: string;
}

export function SidePanelCard({ title, children, className }: SidePanelCardProps) {
    return (
        <aside className={cn("insight-card p-5", className)}>
            <h2 className="text-base font-bold text-foreground">{title}</h2>
            <div className="mt-4 space-y-3">{children}</div>
        </aside>
    );
}
