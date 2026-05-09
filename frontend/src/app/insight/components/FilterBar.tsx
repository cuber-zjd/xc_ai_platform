import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface FilterBarProps {
    children: ReactNode;
    className?: string;
}

export function FilterBar({ children, className }: FilterBarProps) {
    return (
        <div className={cn("insight-card flex flex-wrap items-center gap-3 p-3", className)}>
            <div className="flex flex-1 flex-wrap items-center gap-3">{children}</div>
            <Button
                type="button"
                className="h-10 rounded-2xl bg-primary px-4 text-primary-foreground shadow-[0_10px_22px_rgba(37,99,235,0.2)] hover:bg-primary/90"
            >
                应用筛选
            </Button>
        </div>
    );
}
