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
        <section className={cn("insight-card p-5", className)}>
            {(title || description || action) && (
                <div className="mb-4 flex items-start justify-between gap-4">
                    <div>
                        {title && <h2 className="text-base font-bold text-foreground">{title}</h2>}
                        {description && <p className="mt-1 text-sm leading-6 text-muted-foreground">{description}</p>}
                    </div>
                    {action}
                </div>
            )}
            {children}
        </section>
    );
}
