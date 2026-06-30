import type { ReactNode } from "react";

interface PageTitleProps {
    eyebrow?: string;
    title: string;
    description?: string;
    action?: ReactNode;
}

export function PageTitle({ action }: PageTitleProps) {
    if (!action) return null;

    return (
        <div className="insight-page-heading">
            {action ? <div className="insight-actions">{action}</div> : null}
        </div>
    );
}
