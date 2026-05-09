import type { PropsWithChildren } from "react";

import { cn } from "@/lib/utils";

interface PageContainerProps extends PropsWithChildren {
    className?: string;
}

export function PageContainer({ children, className }: PageContainerProps) {
    return <main className={cn("insight-page space-y-5", className)}>{children}</main>;
}
