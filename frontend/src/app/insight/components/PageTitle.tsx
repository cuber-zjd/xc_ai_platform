import type { ReactNode } from "react";

interface PageTitleProps {
    eyebrow?: string;
    title: string;
    description?: string;
    action?: ReactNode;
}

export function PageTitle({ eyebrow, title, description, action }: PageTitleProps) {
    return (
        <div className="insight-page-heading rounded-[var(--insight-radius-xl)] border border-border bg-card px-4 py-4 shadow-[var(--insight-shadow-card)] sm:px-6 sm:py-5">
            <div className="min-w-0">
                {eyebrow && <div className="text-xs font-bold uppercase tracking-[0.16em] text-primary">{eyebrow}</div>}
                <h1 className="mt-2 text-2xl font-black leading-tight tracking-tight text-foreground md:text-3xl">{title}</h1>
                {description && <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">{description}</p>}
            </div>
            {action ? <div className="insight-actions">{action}</div> : null}
        </div>
    );
}
