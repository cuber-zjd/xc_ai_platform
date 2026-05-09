import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

import { insightBusinessColors, insightStatusColors, type InsightBusinessTag, type InsightStatus } from "../theme/semantic-colors";

interface InsightTagProps {
    children?: string;
    status?: InsightStatus;
    business?: InsightBusinessTag;
    className?: string;
}

export function InsightTag({ children, status, business, className }: InsightTagProps) {
    const statusColor = status ? insightStatusColors[status] : undefined;
    const businessColor = business ? insightBusinessColors[business] : undefined;

    return (
        <Badge
            variant="outline"
            className={cn(
                "h-[var(--insight-badge-height,1.625rem)] rounded-full border px-2.5 text-xs font-bold shadow-none",
                statusColor && [statusColor.bg, statusColor.border, statusColor.text],
                businessColor?.className,
                !statusColor && !businessColor && "border-border bg-secondary text-secondary-foreground",
                className,
            )}
        >
            {children ?? statusColor?.label ?? businessColor?.label}
        </Badge>
    );
}
