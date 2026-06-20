import type React from "react";
import { Link } from "react-router-dom";
import { Building2, Database, FileText, Flame } from "lucide-react";

import { DemoCard, DemoTag, SectionHeader, StatCard } from "../components/DemoPrimitives";
import { useInsightDashboard } from "../hooks";
import { PageContainer } from "../layout/PageContainer";
import type { InsightDashboardSourceSlice, InsightDashboardTrendPoint, InsightIntelligenceListItem } from "../api";
import { formatInsightDate, formatInsightType } from "../utils/display";

const sourceColors = ["#1d74ff", "#6657f5", "#ffc44d", "#55cfc2", "#f97316", "#94a3b8"];

export function DashboardPage() {
    const dashboardQuery = useInsightDashboard();
    const dashboard = dashboardQuery.data;
    const metrics = dashboard?.metrics ?? [];
    const metricMap = new Map(metrics.map((item) => [item.key, item]));
    const latestItems = dashboard?.latest_items ?? [];
    const focusItems = dashboard?.focus_items ?? [];
    const trend = dashboard?.trend ?? [];
    const sourceDistribution = dashboard?.source_distribution ?? [];
    const isDashboardLoading = dashboardQuery.isLoading && !dashboard;

    return (
        <PageContainer className="flex min-h-0 flex-col gap-4">
            <div className="insight-page-heading">
                <h1 className="text-2xl font-black leading-tight tracking-tight text-slate-950 md:text-3xl">首页看板</h1>
                {dashboardQuery.isFetching ? <span className="text-sm font-semibold text-slate-500">数据刷新中...</span> : null}
            </div>

            <div className="insight-metric-strip">
                <MetricCard
                    metric={metricMap.get("companies")}
                    fallbackLabel="监控企业"
                    loading={isDashboardLoading}
                    icon={<Building2 className="size-7" />}
                />
                <MetricCard
                    metric={metricMap.get("data_sources")}
                    fallbackLabel="数据源"
                    tone="cyan"
                    loading={isDashboardLoading}
                    icon={<Database className="size-7" />}
                />
                <MetricCard
                    metric={metricMap.get("today_intelligence")}
                    fallbackLabel="今日新增情报"
                    loading={isDashboardLoading}
                    icon={<FileText className="size-7" />}
                />
                <MetricCard
                    metric={metricMap.get("week_focus")}
                    fallbackLabel="本周重点动态"
                    tone="cyan"
                    loading={isDashboardLoading}
                    icon={<Flame className="size-7" />}
                />
            </div>

            <div className="grid gap-4 auto-rows-[minmax(18rem,auto)] xl:grid-cols-2 2xl:grid-cols-[1.12fr_0.86fr_1fr]">
                <DemoCard className="flex min-h-[18rem] min-w-0 flex-col p-4">
                    <SectionHeader title="近 7 日情报趋势" action="近 7 日" />
                    <div className="min-h-0 flex-1 px-2 pb-5">
                        <TrendChart points={trend} />
                    </div>
                </DemoCard>

                <DemoCard className="flex min-h-[18rem] min-w-0 flex-col p-4">
                    <SectionHeader title="情报来源分布" action="可见范围" />
                    <div className="flex min-h-0 flex-1 items-center justify-center">
                        <SourceDonut slices={sourceDistribution} />
                    </div>
                </DemoCard>

                <DemoCard className="flex min-h-[18rem] min-w-0 flex-col p-4 xl:col-span-2 2xl:col-span-1">
                    <SectionHeader title="重点动态" action="按重要性" />
                    <div className="min-h-0 flex-1 overflow-auto">
                        {focusItems.length > 0 ? (
                            <div className="space-y-4">
                                {focusItems.map((item, index) => (
                                    <Link key={item.id} to={`/insight/intelligence/${item.id}`} className="flex items-start gap-3 rounded-xl p-2 transition hover:bg-blue-50/60">
                                        <span className={rankClass(index)}>{index + 1}</span>
                                        <span className="min-w-0 flex-1">
                                            <span className="block truncate text-sm font-bold text-slate-800">{item.title}</span>
                                            <span className="mt-1 block text-xs text-slate-500">
                                                {item.subject_name || formatInsightType(item.intelligence_type)} · {formatInsightDate(item.publish_time)}
                                            </span>
                                        </span>
                                    </Link>
                                ))}
                            </div>
                        ) : (
                            <EmptyHint text="暂无重点动态" />
                        )}
                    </div>
                </DemoCard>
            </div>

            <DemoCard className="flex min-h-[20rem] min-w-0 flex-col p-4">
                <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                    <h2 className="text-xl font-black text-slate-900">最新情报</h2>
                    <Link to="/insight/intelligence" className="text-sm font-bold text-blue-600">
                        查看更多情报
                    </Link>
                </div>
                <div className="min-h-0 flex-1 overflow-auto rounded-xl border border-slate-200">
                    <table className="min-w-[760px] w-full text-left text-sm">
                        <thead className="bg-slate-50 text-slate-500">
                            <tr>
                                {["发布时间", "主题", "类型", "标题", "标签"].map((head) => (
                                    <th key={head} className="px-4 py-3 font-bold">
                                        {head}
                                    </th>
                                ))}
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100">
                            {dashboardQuery.isLoading ? (
                                <tr>
                                    <td colSpan={5} className="px-4 py-10 text-center text-sm font-semibold text-slate-500">
                                        正在读取最新情报...
                                    </td>
                                </tr>
                            ) : null}
                            {latestItems.map((row) => (
                                <LatestRow key={row.id} row={row} />
                            ))}
                            {!dashboardQuery.isLoading && latestItems.length === 0 ? (
                                <tr>
                                    <td colSpan={5} className="px-4 py-10 text-center text-sm font-semibold text-slate-500">
                                        暂无可见情报，先到数据源配置发起一次采集。
                                    </td>
                                </tr>
                            ) : null}
                        </tbody>
                    </table>
                </div>
            </DemoCard>
        </PageContainer>
    );
}

function MetricCard({
    metric,
    fallbackLabel,
    loading = false,
    tone = "blue",
    icon,
}: {
    metric?: { label: string; value: number; compare_label: string; delta: number };
    fallbackLabel: string;
    loading?: boolean;
    tone?: "blue" | "cyan";
    icon: React.ReactNode;
}) {
    return (
        <StatCard
            title={metric?.label ?? fallbackLabel}
            value={String(metric?.value ?? 0)}
            compare={metric?.compare_label ?? "当前可见"}
            delta={formatMetricDelta(metric)}
            loading={loading}
            tone={tone}
            icon={icon}
        />
    );
}

function TrendChart({ points }: { points: InsightDashboardTrendPoint[] }) {
    if (points.length < 2) {
        return <EmptyHint text="暂无足够趋势数据" />;
    }
    const values = points.map((point) => point.count);
    const max = Math.max(...values, 5);
    const width = 560;
    const height = 220;
    const step = width / (points.length - 1);
    const coords = values.map((value, index) => [index * step, height - (value / max) * (height - 32) - 12]);
    const line = coords.map(([x, y]) => `${x},${y}`).join(" ");
    const area = `0,${height} ${line} ${width},${height}`;

    return (
        <div className="h-full w-full">
            <svg viewBox={`0 0 ${width} ${height}`} className="h-full w-full overflow-visible">
                {[40, 80, 120, 160, 200].map((y) => (
                    <line key={y} x1="0" x2={width} y1={y} y2={y} stroke="#dbeafe" strokeDasharray="4 4" />
                ))}
                <polygon points={area} fill="url(#dashboardLineArea)" />
                <polyline points={line} fill="none" stroke="#1677ff" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" />
                {coords.map(([x, y], index) => (
                    <g key={`${x}-${y}`}>
                        <circle cx={x} cy={y} r="6" fill="#1677ff" stroke="#fff" strokeWidth="3" />
                        <text x={x} y={y - 14} textAnchor="middle" className="fill-slate-700 text-xs font-bold">
                            {values[index]}
                        </text>
                    </g>
                ))}
                <defs>
                    <linearGradient id="dashboardLineArea" x1="0" x2="0" y1="0" y2="1">
                        <stop offset="0%" stopColor="#1677ff" stopOpacity="0.18" />
                        <stop offset="100%" stopColor="#1677ff" stopOpacity="0.02" />
                    </linearGradient>
                </defs>
            </svg>
            <div className="mt-2 grid grid-cols-7 text-center text-xs text-slate-500">
                {points.map((point) => (
                    <span key={point.label}>{point.label}</span>
                ))}
            </div>
        </div>
    );
}

function SourceDonut({ slices }: { slices: InsightDashboardSourceSlice[] }) {
    if (slices.length === 0) {
        return <EmptyHint text="暂无来源分布数据" />;
    }
    const total = slices.reduce((sum, item) => sum + item.count, 0);
    const gradient = slices
        .reduce<{ cursor: number; stops: string[] }>(
            (state, item, index) => {
            const percent = item.percent || 0;
            const next = Math.min(state.cursor + percent, 100);
            return {
                cursor: next,
                stops: [...state.stops, `${sourceColors[index % sourceColors.length]} ${state.cursor}% ${next}%`],
            };
            },
            { cursor: 0, stops: [] },
        )
        .stops.join(", ");

    return (
        <div className="flex flex-col items-center justify-center gap-5 sm:flex-row sm:gap-8">
            <div className="relative size-48 rounded-full">
                <div className="absolute inset-0 rounded-full" style={{ background: `conic-gradient(${gradient})` }} />
                <div className="absolute inset-6 flex flex-col items-center justify-center rounded-full bg-white text-center shadow-inner">
                    <span className="text-sm text-slate-600">合计</span>
                    <strong className="text-3xl font-black text-slate-950">{total}</strong>
                    <span className="text-sm text-slate-600">条来源</span>
                </div>
            </div>
            <div className="w-full space-y-3 text-sm sm:w-auto">
                {slices.map((item, index) => (
                    <div key={item.source_type} className="flex items-center gap-3">
                        <span className="size-2.5 rounded-sm" style={{ backgroundColor: sourceColors[index % sourceColors.length] }} />
                        <span className="min-w-20 text-slate-700">{item.label}</span>
                        <span className="font-semibold text-slate-600">{item.percent.toFixed(1)}%</span>
                    </div>
                ))}
            </div>
        </div>
    );
}

function LatestRow({ row }: { row: InsightIntelligenceListItem }) {
    const tags = normalizeTags(row.suggested_tags).slice(0, 3);
    return (
        <tr className="hover:bg-blue-50/40">
            <td className="w-36 px-4 py-3 text-slate-600">{formatInsightDate(row.publish_time, row.create_time)}</td>
            <td className="w-32 px-4 py-3 font-bold text-slate-800">{row.subject_name || "通用主题"}</td>
            <td className="w-32 px-4 py-3">
                <DemoTag tone="blue">{formatInsightType(row.intelligence_type)}</DemoTag>
            </td>
            <td className="px-4 py-3 font-semibold text-slate-800">
                <Link to={`/insight/intelligence/${row.id}`} className="line-clamp-2 hover:text-blue-600">
                    {row.title}
                </Link>
            </td>
            <td className="w-56 px-4 py-3">
                <div className="flex flex-wrap gap-2">
                    {tags.length > 0 ? (
                        tags.map((tag, index) => (
                            <DemoTag key={tag} tone={index === 0 ? "blue" : index === 1 ? "green" : "orange"}>
                                {tag}
                            </DemoTag>
                        ))
                    ) : (
                        <DemoTag tone="slate">{row.primary_source_type || "未标注"}</DemoTag>
                    )}
                </div>
            </td>
        </tr>
    );
}

function EmptyHint({ text }: { text: string }) {
    return <div className="flex h-full min-h-36 items-center justify-center rounded-xl border border-dashed border-slate-200 text-sm font-semibold text-slate-500">{text}</div>;
}

function normalizeTags(value: InsightIntelligenceListItem["suggested_tags"]): string[] {
    if (!Array.isArray(value)) {
        return [];
    }
    return value.map((item) => item.name).filter((name): name is string => Boolean(name));
}

function formatDelta(value: number) {
    return value > 0 ? `+${value}` : String(value);
}

function formatMetricDelta(metric?: { compare_label: string; delta: number }) {
    if (!metric) {
        return undefined;
    }
    if (metric.delta === 0 && !metric.compare_label.includes("较")) {
        return undefined;
    }
    return formatDelta(metric.delta);
}

function rankClass(index: number) {
    const base = "mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-md text-xs font-black text-white";
    if (index === 0) {
        return `${base} bg-red-500`;
    }
    if (index === 1) {
        return `${base} bg-orange-500`;
    }
    if (index === 2) {
        return `${base} bg-amber-500`;
    }
    return `${base} bg-slate-300`;
}
