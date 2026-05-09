import type { ReactNode } from "react";

interface PageTitleProps {
    eyebrow?: string;
    title: string;
    description?: string;
    action?: ReactNode;
}

export function PageTitle({ eyebrow, title, description, action }: PageTitleProps) {
    return (
        <div className="flex flex-col justify-between gap-4 rounded-[var(--insight-radius-xl)] border border-border bg-card px-6 py-5 shadow-[var(--insight-shadow-card)] md:flex-row md:items-end">
            <div>
                {eyebrow && <div className="text-xs font-bold uppercase tracking-[0.16em] text-primary">{eyebrow}</div>}
                <h1 className="mt-2 text-2xl font-black tracking-tight text-foreground md:text-3xl">{title}</h1>
                {description && <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">{description}</p>}
            </div>
            {action}
        </div>
    );
}
