import type { InsightReportChartRead } from "../api";
import { insightChartPalette } from "../theme/chart-theme";
import { SectionCard } from "./SectionCard";

interface ChartCardProps {
    title?: string;
    description?: string;
    chart?: InsightReportChartRead;
    compact?: boolean;
}

export function ChartCard({ title, description, chart, compact = false }: ChartCardProps) {
    const resolvedTitle = chart?.title ?? title ?? "数据图表";
    const resolvedDescription = chart?.description ?? description;
    const points = chart?.points ?? [];
    const chartType = chart?.chart_type ?? "bar";
    const unit = chart?.unit ?? "条";
    const hasData = points.length > 0;

    const body = (
        <div className={compact ? "space-y-3" : "space-y-4"}>
            {compact ? (
                <div>
                    <h4 className="text-sm font-black text-slate-950">{resolvedTitle}</h4>
                    {resolvedDescription ? <p className="mt-1 text-xs leading-5 text-slate-500">{resolvedDescription}</p> : null}
                </div>
            ) : null}
            {!hasData ? <ChartEmptyState /> : null}
            {hasData && chartType === "donut" ? <DonutChart points={points} /> : null}
            {hasData && chartType === "line" ? <LineChart points={points} unit={unit} /> : null}
            {hasData && chartType === "list" ? <ListChart points={points} unit={unit} /> : null}
            {hasData && !["donut", "line", "list"].includes(chartType) ? <BarChart points={points} unit={unit} /> : null}
        </div>
    );

    if (compact) {
        return <div className="rounded-xl border border-slate-200 bg-white p-4">{body}</div>;
    }

    return (
        <SectionCard title={resolvedTitle} description={resolvedDescription}>
            <div className="rounded-[var(--insight-radius-lg)] border border-border bg-linear-to-b from-card to-muted/40 p-4">{body}</div>
        </SectionCard>
    );
}

function ChartEmptyState() {
    return (
        <div className="flex min-h-48 items-center justify-center rounded-xl border border-dashed border-slate-200 bg-white/70 px-4 text-center text-sm font-semibold text-slate-500">
            暂无可展示的图表数据
        </div>
    );
}

function BarChart({ points, unit }: { points: InsightReportChartRead["points"]; unit: string }) {
    const max = Math.max(...points.map((point) => point.value), 1);
    return (
        <div className="h-64">
            <div className="flex h-52 items-end gap-3 border-b border-l border-border/80 px-2 pb-2">
                {points.map((point, index) => (
                    <div key={point.key ?? point.label} className="flex min-w-0 flex-1 flex-col items-center gap-2">
                        <div className="relative flex w-full items-end justify-center">
                            <div
                                className="w-full max-w-10 rounded-t-xl"
                                style={{
                                    height: `${Math.max((point.value / max) * 100, 8)}%`,
                                    backgroundColor: insightChartPalette[index % insightChartPalette.length],
                                    opacity: 0.9,
                                }}
                                title={`${point.label}: ${point.value}${unit}`}
                            />
                        </div>
                        <span className="line-clamp-2 h-8 text-center text-[11px] font-medium leading-4 text-muted-foreground">{point.label}</span>
                    </div>
                ))}
            </div>
        </div>
    );
}

function DonutChart({ points }: { points: InsightReportChartRead["points"] }) {
    const total = points.reduce((sum, point) => sum + point.value, 0) || 1;
    const gradient = points
        .reduce<{ cursor: number; segments: string[] }>(
            (result, point, index) => {
                const start = result.cursor;
                const end = start + (point.value / total) * 100;
                return {
                    cursor: end,
                    segments: [...result.segments, `${insightChartPalette[index % insightChartPalette.length]} ${start}% ${end}%`],
                };
            },
            { cursor: 0, segments: [] },
        )
        .segments.join(", ");

    return (
        <div className="grid gap-4 sm:grid-cols-[150px_minmax(0,1fr)] sm:items-center">
            <div className="relative mx-auto size-36 rounded-full" style={{ background: `conic-gradient(${gradient})` }}>
                <div className="absolute inset-8 rounded-full bg-white" />
                <div className="absolute inset-0 flex items-center justify-center text-lg font-black text-slate-950">{total}</div>
            </div>
            <LegendList points={points} total={total} />
        </div>
    );
}

function LineChart({ points, unit }: { points: InsightReportChartRead["points"]; unit: string }) {
    const max = Math.max(...points.map((point) => point.value), 1);
    const width = 520;
    const height = 180;
    const padding = 18;
    const step = points.length > 1 ? (width - padding * 2) / (points.length - 1) : 0;
    const path = points
        .map((point, index) => {
            const x = padding + step * index;
            const y = height - padding - (point.value / max) * (height - padding * 2);
            return `${index === 0 ? "M" : "L"} ${x} ${y}`;
        })
        .join(" ");

    return (
        <div className="space-y-2">
            <svg viewBox={`0 0 ${width} ${height}`} className="h-48 w-full overflow-visible">
                <path d={path} fill="none" stroke={insightChartPalette[0]} strokeWidth="3" strokeLinecap="round" />
                {points.map((point, index) => {
                    const x = padding + step * index;
                    const y = height - padding - (point.value / max) * (height - padding * 2);
                    return (
                        <g key={point.key ?? point.label}>
                            <circle cx={x} cy={y} r="4" fill={insightChartPalette[index % insightChartPalette.length]} />
                            <title>{`${point.label}: ${point.value}${unit}`}</title>
                        </g>
                    );
                })}
            </svg>
            <div className="grid grid-cols-4 gap-2 text-[11px] font-medium text-slate-500">
                {points.slice(0, 8).map((point) => (
                    <span key={point.key ?? point.label} className="truncate">
                        {point.label}
                    </span>
                ))}
            </div>
        </div>
    );
}

function ListChart({ points, unit }: { points: InsightReportChartRead["points"]; unit: string }) {
    const max = Math.max(...points.map((point) => point.value), 1);
    return (
        <div className="space-y-2">
            {points.map((point, index) => (
                <div key={point.key ?? point.label} className="grid grid-cols-[minmax(0,1fr)_64px] items-center gap-3 text-sm">
                    <div className="min-w-0">
                        <div className="flex items-center gap-2">
                            <span className="flex size-5 shrink-0 items-center justify-center rounded-full bg-slate-100 text-[11px] font-black text-slate-500">{index + 1}</span>
                            <span className="truncate font-bold text-slate-700">{point.label}</span>
                        </div>
                        <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-slate-100">
                            <div
                                className="h-full rounded-full"
                                style={{
                                    width: `${Math.max((point.value / max) * 100, 4)}%`,
                                    backgroundColor: insightChartPalette[index % insightChartPalette.length],
                                }}
                            />
                        </div>
                    </div>
                    <span className="text-right text-xs font-black text-slate-700">
                        {point.value}
                        {unit}
                    </span>
                </div>
            ))}
        </div>
    );
}

function LegendList({ points, total }: { points: InsightReportChartRead["points"]; total: number }) {
    return (
        <div className="space-y-2">
            {points.map((point, index) => (
                <div key={point.key ?? point.label} className="flex items-center justify-between gap-3 text-xs">
                    <span className="flex min-w-0 items-center gap-2 font-bold text-slate-600">
                        <span className="size-2.5 shrink-0 rounded-full" style={{ backgroundColor: insightChartPalette[index % insightChartPalette.length] }} />
                        <span className="truncate">{point.label}</span>
                    </span>
                    <span className="shrink-0 font-black text-slate-900">{point.percent ?? Math.round((point.value / total) * 100)}%</span>
                </div>
            ))}
        </div>
    );
}
