import type { PropsWithChildren } from "react";

import { cn } from "@/lib/utils";

interface PageContainerProps extends PropsWithChildren {
    className?: string;
}

export function PageContainer({ children, className }: PageContainerProps) {
    return <main className={cn("insight-page", className ?? "flex flex-col gap-4 overflow-y-auto pr-1")}>{children}</main>;
}
