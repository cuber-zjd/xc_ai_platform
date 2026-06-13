import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface FilterBarProps {
    children: ReactNode;
    className?: string;
}

export function FilterBar({ children, className }: FilterBarProps) {
    return (
        <div className={cn("insight-card flex flex-col gap-3 p-3 lg:flex-row lg:items-center", className)}>
            <div className="grid min-w-0 flex-1 gap-3 sm:grid-cols-2 xl:flex xl:flex-wrap xl:items-center">{children}</div>
            <Button
                type="button"
                className="h-10 w-full rounded-2xl bg-primary px-4 text-primary-foreground shadow-[0_10px_22px_rgba(37,99,235,0.2)] hover:bg-primary/90 sm:w-auto"
            >
                应用筛选
            </Button>
        </div>
    );
}
