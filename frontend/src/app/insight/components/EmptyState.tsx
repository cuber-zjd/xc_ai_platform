import type { ReactNode } from "react";

interface EmptyStateProps {
    icon?: ReactNode;
    title: string;
    description?: string;
    action?: ReactNode;
}

export function EmptyState({ icon, title, description, action }: EmptyStateProps) {
    return (
        <div className="flex min-h-64 flex-col items-center justify-center rounded-[var(--insight-radius-xl)] border border-dashed border-border bg-muted/35 p-8 text-center">
            {icon && <div className="mb-4 flex size-12 items-center justify-center rounded-2xl bg-card text-primary shadow-[var(--insight-shadow-subtle)]">{icon}</div>}
            <h3 className="text-base font-bold text-foreground">{title}</h3>
            {description && <p className="mt-2 max-w-md text-sm leading-6 text-muted-foreground">{description}</p>}
            {action && <div className="mt-5">{action}</div>}
        </div>
    );
}
