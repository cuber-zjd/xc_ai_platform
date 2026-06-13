import type { PropsWithChildren, ReactNode } from "react";

import { cn } from "@/lib/utils";

interface SectionCardProps extends PropsWithChildren {
    title?: string;
    description?: string;
    action?: ReactNode;
    className?: string;
}

export function SectionCard({ title, description, action, children, className }: SectionCardProps) {
    return (
        <section className={cn("insight-card min-w-0 p-4 sm:p-5", className)}>
            {(title || description || action) && (
                <div className="mb-4 flex flex-col justify-between gap-3 md:flex-row md:items-start">
                    <div className="min-w-0">
                        {title && <h2 className="text-base font-bold text-foreground">{title}</h2>}
                        {description && <p className="mt-1 text-sm leading-6 text-muted-foreground">{description}</p>}
                    </div>
                    {action ? <div className="insight-actions">{action}</div> : null}
                </div>
            )}
            {children}
        </section>
    );
}
