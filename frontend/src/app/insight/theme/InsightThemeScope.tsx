import type { PropsWithChildren } from "react";

import { cn } from "@/lib/utils";

interface InsightThemeScopeProps extends PropsWithChildren {
    className?: string;
}

export function InsightThemeScope({ children, className }: InsightThemeScopeProps) {
    return (
        <div data-app="insight" className={cn("insight-theme", className)}>
            {children}
        </div>
    );
}
