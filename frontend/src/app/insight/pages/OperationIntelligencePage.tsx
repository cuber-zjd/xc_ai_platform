import { useMemo, useState, type ReactNode } from "react";
import {
    Activity,
    AlertTriangle,
    ArrowUpRight,
    BadgeCheck,
    BarChart3,
    Boxes,
    BrainCircuit,
    CalendarDays,
    CircleDot,
    Database,
    FileSearch,
    Gauge,
    RefreshCw,
    ShieldAlert,
    Sparkles,
    Target,
    TrendingUp,
    Users,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

import { SectionCard } from "../components/SectionCard";
import { useInsightOperationCustomerLifecycle, useInsightOperationOverview } from "../hooks";
import { PageContainer } from "../layout/PageContainer";
import type { InsightOperationCustomerLifecycle, InsightOperationDomain, InsightOperationLifecycleSection, InsightOperationMetric, InsightOperationSignal } from "../api";

const domainIcons: Record<string, typeof TrendingUp> = {
    sales: TrendingUp,
    customer: Users,
    position: Boxes,
    hedging: ShieldAlert,
};

const domainAccent: Record<string, string> = {
    sales: "from-sky-500 to-cyan-500",
    customer: "from-rose-500 to-amber-500",
    position: "from-emerald-500 to-teal-500",
    hedging: "from-indigo-500 to-slate-700",
};

export function OperationIntelligencePage() {
    const overviewQuery = useInsightOperationOverview();
    const lifecycleQuery = useInsightOperationCustomerLifecycle();
    const overview = overviewQuery.data;
    const lifecycle = lifecycleQuery.data;
    const domains = overview?.domains ?? [];
    const [selectedDomainKey, setSelectedDomainKey] = useState<string>("sales");
    const selectedDomain = domains.find((domain) => domain.key === selectedDomainKey) ?? domains[0];
    const signalCounts = useMemo(() => countSignals(overview?.signals ?? []), [overview?.signals]);
    const isRefreshing = overviewQuery.isFetching || lifecycleQuery.isFetching;

    const handleRefresh = () => {
        void overviewQuery.refetch();
        void lifecycleQuery.refetch();
    };

    return (
        <PageContainer className="flex min-h-0 flex-col gap-4 overflow-y-auto pr-1">
            <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="flex min-w-0 flex-wrap items-center gap-2">
                    <Badge variant="outline" className="border-cyan-100 bg-cyan-50 text-cyan-800">
                        <BrainCircuit className="size-3.5" />
                        经营智能
                    </Badge>
                    <FreshnessPill label="分析日" value={overview?.analysisDate ?? "读取中"} icon={<CalendarDays className="size-3.5" />} />
                    <FreshnessPill label="客户期间" value={overview?.analysisPeriod ?? "读取中"} icon={<Target className="size-3.5" />} />
                    <FreshnessPill label="生成时间" value={overview?.generatedAt ?? "读取中"} icon={<Activity className="size-3.5" />} />
                </div>
                <Button variant="outline" size="sm" onClick={handleRefresh} disabled={isRefreshing}>
                    <RefreshCw className={cn("size-4", isRefreshing && "animate-spin")} />
                    刷新分析
                </Button>
            </div>

            <section className="relative overflow-hidden rounded-[24px] border border-slate-200 bg-white p-5 shadow-[0_18px_45px_rgba(15,23,42,0.06)]">
                <div className="absolute inset-x-0 top-0 h-1 bg-linear-to-r from-cyan-500 via-emerald-500 to-amber-400" />
                <div className="grid gap-5 xl:grid-cols-[1.25fr_0.75fr]">
                    <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                            <span className="inline-flex size-10 items-center justify-center rounded-2xl bg-slate-950 text-white shadow-[0_14px_28px_rgba(15,23,42,0.18)]">
                                <Sparkles className="size-5" />
                            </span>
                            <div className="min-w-0">
                                <div className="text-sm font-black text-slate-500">{overview?.companyName ?? "健源公司"}</div>
                                <h1 className="mt-1 text-balance text-2xl font-black leading-tight text-slate-950 sm:text-3xl">
                                    {overview?.headline ?? "正在读取经营数据链路..."}
                                </h1>
                            </div>
                        </div>
                        <div className="mt-5 grid gap-3 md:grid-cols-3">
                            <SignalCounter label="高优先级风险" value={signalCounts.danger} tone="danger" />
                            <SignalCounter label="需跟进信号" value={signalCounts.warning} tone="warning" />
                            <SignalCounter label="已接入证据" value={overview?.evidence.length ?? 0} tone="normal" />
                        </div>
                    </div>

                    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-1">
                        {(overview?.executiveSummary ?? []).slice(0, 3).map((item, index) => (
                            <div key={`${item}-${index}`} className="flex min-w-0 items-start gap-3 rounded-2xl border border-slate-100 bg-slate-50 px-4 py-3">
                                <CircleDot className="mt-0.5 size-4 shrink-0 text-cyan-600" />
                                <p className="line-clamp-2 text-sm font-semibold leading-6 text-slate-700">{item}</p>
                            </div>
                        ))}
                        {!overview && (
                            <div className="rounded-2xl border border-slate-100 bg-slate-50 px-4 py-8 text-sm font-semibold text-slate-500">
                                {overviewQuery.isError ? "经营分析读取失败，请稍后重试。" : "正在聚合销量、客户、库存与套保数据..."}
                            </div>
                        )}
                    </div>
                </div>
            </section>

            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                {(overview?.kpis ?? []).slice(0, 8).map((metric) => (
                    <MetricTile key={metric.key} metric={metric} />
                ))}
                {!overview && Array.from({ length: 4 }).map((_, index) => <MetricSkeleton key={index} />)}
            </div>

            <CustomerLifecyclePanel lifecycle={lifecycle} loading={lifecycleQuery.isLoading && !lifecycle} />

            <div className="grid gap-4 xl:grid-cols-[1.35fr_0.65fr]">
                <div className="grid gap-4 md:grid-cols-2">
                    {domains.map((domain) => (
                        <DomainCard key={domain.key} domain={domain} active={selectedDomain?.key === domain.key} onSelect={() => setSelectedDomainKey(domain.key)} />
                    ))}
                </div>

                <SectionCard title="经营信号流" description="按风险等级、经营域和证据强度排序">
                    <div className="space-y-3">
                        {(overview?.signals ?? []).map((signal) => (
                            <SignalItem key={`${signal.domain}-${signal.title}`} signal={signal} />
                        ))}
                        {!overview?.signals?.length && <EmptyPanel text="暂无经营信号" />}
                    </div>
                </SectionCard>
            </div>

            <div className="grid gap-4 xl:grid-cols-[0.95fr_1.05fr]">
                <SectionCard
                    title="指标拆解"
                    description={selectedDomain?.subtitle ?? "选择经营域查看指标与明细"}
                    action={
                        <div className="flex flex-wrap gap-2">
                            {domains.map((domain) => (
                                <Button
                                    key={domain.key}
                                    type="button"
                                    size="sm"
                                    variant={selectedDomain?.key === domain.key ? "default" : "outline"}
                                    onClick={() => setSelectedDomainKey(domain.key)}
                                >
                                    {domain.title}
                                </Button>
                            ))}
                        </div>
                    }
                >
                    {selectedDomain ? <DomainDetail domain={selectedDomain} /> : <EmptyPanel text="暂无经营域数据" />}
                </SectionCard>

                <SectionCard title="证据链" description="从 CPT 报表、来源表和指标口径回看分析依据">
                    <div className="space-y-3">
                        {(overview?.evidence ?? []).map((evidence) => (
                            <div key={evidence.title} className="rounded-2xl border border-slate-100 bg-white px-4 py-3">
                                <div className="flex items-start justify-between gap-3">
                                    <div className="min-w-0">
                                        <div className="flex items-center gap-2 text-sm font-black text-slate-900">
                                            <FileSearch className="size-4 text-cyan-600" />
                                            {evidence.title}
                                        </div>
                                        <div className="mt-2 truncate text-xs font-semibold text-slate-500">{evidence.reportPath}</div>
                                    </div>
                                    <ArrowUpRight className="size-4 shrink-0 text-slate-400" />
                                </div>
                                <div className="mt-3 flex flex-wrap gap-2">
                                    {evidence.metrics.map((metric) => (
                                        <span key={metric} className="rounded-full bg-cyan-50 px-2.5 py-1 text-xs font-bold text-cyan-800">
                                            {metric}
                                        </span>
                                    ))}
                                </div>
                                <div className="mt-3 flex flex-wrap items-center gap-2 text-xs font-semibold text-slate-500">
                                    <Database className="size-3.5" />
                                    {evidence.tables.join(" / ")}
                                </div>
                                {evidence.note ? <p className="mt-2 text-xs font-semibold leading-5 text-amber-700">{evidence.note}</p> : null}
                            </div>
                        ))}
                    </div>
                </SectionCard>
            </div>

            {overview?.warnings?.length ? (
                <SectionCard title="数据提示">
                    <div className="grid gap-2 md:grid-cols-2">
                        {overview.warnings.map((warning) => (
                            <div key={warning} className="flex items-start gap-2 rounded-2xl border border-amber-100 bg-amber-50 px-4 py-3 text-sm font-semibold leading-6 text-amber-800">
                                <AlertTriangle className="mt-0.5 size-4 shrink-0" />
                                {warning}
                            </div>
                        ))}
                    </div>
                </SectionCard>
            ) : null}
        </PageContainer>
    );
}

function FreshnessPill({ label, value, icon }: { label: string; value: string; icon: ReactNode }) {
    return (
        <span className="inline-flex h-8 max-w-full items-center gap-1.5 rounded-full border border-slate-200 bg-white px-3 text-xs font-bold text-slate-600">
            {icon}
            <span className="text-slate-400">{label}</span>
            <span className="truncate">{value}</span>
        </span>
    );
}

function SignalCounter({ label, value, tone }: { label: string; value: number; tone: "danger" | "warning" | "normal" }) {
    const toneClass = {
        danger: "border-rose-100 bg-rose-50 text-rose-700",
        warning: "border-amber-100 bg-amber-50 text-amber-700",
        normal: "border-emerald-100 bg-emerald-50 text-emerald-700",
    };
    return (
        <div className={cn("rounded-2xl border px-4 py-3", toneClass[tone])}>
            <div className="text-xs font-black opacity-80">{label}</div>
            <div className="mt-1 text-3xl font-black leading-none">{value}</div>
        </div>
    );
}

function MetricTile({ metric }: { metric: InsightOperationMetric }) {
    const severityClass = {
        normal: "border-slate-200 bg-white text-slate-950",
        warning: "border-amber-200 bg-amber-50 text-amber-900",
        danger: "border-rose-200 bg-rose-50 text-rose-900",
    }[metric.severity] ?? "border-slate-200 bg-white text-slate-950";
    return (
        <div className={cn("min-h-32 rounded-[22px] border p-4 shadow-[0_12px_28px_rgba(15,23,42,0.04)]", severityClass)}>
            <div className="flex items-start justify-between gap-3">
                <div className="min-w-0 text-sm font-black text-slate-500">{metric.label}</div>
                {metric.severity === "danger" ? <AlertTriangle className="size-4 shrink-0 text-rose-600" /> : <Gauge className="size-4 shrink-0 text-cyan-600" />}
            </div>
            <div className="mt-4 flex items-end gap-1">
                <span className="truncate text-3xl font-black leading-none">{formatMetricValue(metric.value)}</span>
                {metric.unit ? <span className="pb-0.5 text-sm font-black text-slate-500">{metric.unit}</span> : null}
            </div>
            {metric.description ? <div className="mt-2 line-clamp-2 text-xs font-semibold leading-5 text-slate-500">{metric.description}</div> : null}
        </div>
    );
}

function MetricSkeleton() {
    return (
        <div className="min-h-32 animate-pulse rounded-[22px] border border-slate-200 bg-white p-4">
            <div className="h-4 w-24 rounded-full bg-slate-100" />
            <div className="mt-5 h-8 w-28 rounded-full bg-slate-100" />
            <div className="mt-3 h-3 w-36 rounded-full bg-slate-100" />
        </div>
    );
}

function DomainCard({ domain, active, onSelect }: { domain: InsightOperationDomain; active: boolean; onSelect: () => void }) {
    const Icon = domainIcons[domain.key] ?? BarChart3;
    const maxValue = Math.max(...domain.series.map((point) => Number(point.value) || 0), 1);
    return (
        <button
            type="button"
            onClick={onSelect}
            className={cn(
                "min-h-[22rem] rounded-[24px] border bg-white p-4 text-left shadow-[0_12px_32px_rgba(15,23,42,0.05)] transition",
                "hover:-translate-y-0.5 hover:border-cyan-200 hover:shadow-[0_18px_38px_rgba(14,116,144,0.12)]",
                active ? "border-cyan-300 ring-4 ring-cyan-100" : "border-slate-200",
            )}
        >
            <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                    <div className="flex items-center gap-2">
                        <span className={cn("inline-flex size-10 items-center justify-center rounded-2xl bg-linear-to-br text-white", domainAccent[domain.key] ?? "from-slate-700 to-slate-950")}>
                            <Icon className="size-5" />
                        </span>
                        <div className="min-w-0">
                            <h2 className="truncate text-base font-black text-slate-950">{domain.title}</h2>
                            <p className="mt-0.5 line-clamp-1 text-xs font-semibold text-slate-500">{domain.subtitle}</p>
                        </div>
                    </div>
                </div>
                <div className="text-right">
                    <div className="text-3xl font-black leading-none text-slate-950">{domain.score ?? "--"}</div>
                    <div className="mt-1 text-xs font-black text-slate-500">{domain.scoreLabel ?? "待校验"}</div>
                </div>
            </div>
            <div className="mt-4 grid grid-cols-2 gap-2">
                {domain.metrics.slice(0, 4).map((metric) => (
                    <div key={metric.key} className="rounded-2xl bg-slate-50 px-3 py-2">
                        <div className="truncate text-xs font-black text-slate-500">{metric.label}</div>
                        <div className="mt-1 truncate text-lg font-black text-slate-950">
                            {formatMetricValue(metric.value)}
                            {metric.unit ? <span className="ml-1 text-xs text-slate-500">{metric.unit}</span> : null}
                        </div>
                    </div>
                ))}
            </div>
            <div className="mt-4 space-y-2">
                {domain.series.slice(0, 5).map((point) => (
                    <div key={point.label} className="grid grid-cols-[6.5rem_1fr_4rem] items-center gap-2 text-xs font-bold text-slate-600">
                        <span className="truncate">{point.label}</span>
                        <span className="h-2 overflow-hidden rounded-full bg-slate-100">
                            <span className="block h-full rounded-full bg-cyan-500" style={{ width: `${Math.max(5, Math.min(100, (Number(point.value) / maxValue) * 100))}%` }} />
                        </span>
                        <span className="truncate text-right text-slate-900">{formatMetricValue(point.value)}</span>
                    </div>
                ))}
            </div>
            <div className="mt-4 space-y-2">
                {domain.findings.slice(0, 2).map((finding) => (
                    <p key={finding} className="line-clamp-2 text-xs font-semibold leading-5 text-slate-600">
                        {finding}
                    </p>
                ))}
            </div>
        </button>
    );
}

function SignalItem({ signal }: { signal: InsightOperationSignal }) {
    const tone = signalTone(signal.level);
    return (
        <div className={cn("rounded-2xl border px-4 py-3", tone.panel)}>
            <div className="flex items-start gap-3">
                <span className={cn("mt-0.5 inline-flex size-8 shrink-0 items-center justify-center rounded-xl", tone.icon)}>
                    {signal.level === "danger" ? <AlertTriangle className="size-4" /> : signal.level === "warning" ? <Activity className="size-4" /> : <BadgeCheck className="size-4" />}
                </span>
                <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                        <h3 className="text-sm font-black text-slate-950">{signal.title}</h3>
                        <span className={cn("rounded-full px-2 py-0.5 text-[11px] font-black", tone.badge)}>{signal.domain}</span>
                    </div>
                    <p className="mt-2 text-sm font-semibold leading-6 text-slate-700">{signal.summary}</p>
                    <p className="mt-2 text-xs font-bold leading-5 text-slate-500">{signal.suggestion}</p>
                    <div className="mt-3 flex flex-wrap gap-1.5">
                        {signal.evidence.map((item) => (
                            <span key={item} className="rounded-full bg-white/80 px-2 py-0.5 text-[11px] font-bold text-slate-500">
                                {item}
                            </span>
                        ))}
                    </div>
                </div>
            </div>
        </div>
    );
}

function CustomerLifecyclePanel({ lifecycle, loading }: { lifecycle?: InsightOperationCustomerLifecycle; loading: boolean }) {
    const [selectedKey, setSelectedKey] = useState("new-quality");
    const sections = lifecycle?.sections ?? [];
    const selectedSection = sections.find((section) => section.key === selectedKey) ?? sections[0];

    return (
        <section className="rounded-[26px] border border-slate-200 bg-white p-4 shadow-[0_18px_42px_rgba(15,23,42,0.05)] sm:p-5">
            <div className="flex flex-col justify-between gap-3 lg:flex-row lg:items-start">
                <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                        <span className="inline-flex size-9 items-center justify-center rounded-2xl bg-cyan-600 text-white">
                            <Users className="size-5" />
                        </span>
                        <div className="min-w-0">
                            <div className="text-xs font-black text-cyan-700">客户生命周期运营</div>
                            <h2 className="mt-1 text-xl font-black leading-tight text-slate-950 sm:text-2xl">
                                {lifecycle?.headline ?? "正在生成新客户与流失客户常态分析..."}
                            </h2>
                        </div>
                    </div>
                </div>
                <div className="flex flex-wrap gap-2">
                    <FreshnessPill label="分析日" value={lifecycle?.analysisDate ?? "读取中"} icon={<CalendarDays className="size-3.5" />} />
                    <FreshnessPill label="流失期间" value={lifecycle?.analysisPeriod ?? "读取中"} icon={<Target className="size-3.5" />} />
                </div>
            </div>

            {loading ? (
                <div className="mt-4 grid gap-3 md:grid-cols-4">
                    {Array.from({ length: 4 }).map((_, index) => (
                        <MetricSkeleton key={index} />
                    ))}
                </div>
            ) : null}

            {lifecycle ? (
                <>
                    <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                        {lifecycle.metrics.map((metric) => (
                            <MetricTile key={metric.key} metric={metric} />
                        ))}
                    </div>

                    <div className="mt-4 grid gap-3 lg:grid-cols-[0.9fr_1.1fr]">
                        <div className="grid gap-2">
                            {lifecycle.summary.map((item) => (
                                <div key={item} className="flex items-start gap-2 rounded-2xl border border-slate-100 bg-slate-50 px-4 py-3 text-sm font-semibold leading-6 text-slate-700">
                                    <CircleDot className="mt-1 size-3 shrink-0 text-cyan-600" />
                                    {item}
                                </div>
                            ))}
                        </div>
                        <div className="grid gap-2">
                            {lifecycle.signals.map((signal) => (
                                <SignalItem key={`${signal.domain}-${signal.title}`} signal={signal} />
                            ))}
                        </div>
                    </div>

                    <div className="mt-4 grid gap-4 xl:grid-cols-[18rem_1fr]">
                        <div className="space-y-2">
                            {sections.map((section) => (
                                <Button
                                    key={section.key}
                                    type="button"
                                    variant={selectedSection?.key === section.key ? "default" : "outline"}
                                    className="h-auto w-full justify-start whitespace-normal px-3 py-3 text-left"
                                    onClick={() => setSelectedKey(section.key)}
                                >
                                    <span className="flex min-w-0 flex-col items-start">
                                        <span className="font-black">{section.title}</span>
                                        {section.subtitle ? <span className="mt-1 line-clamp-2 text-xs font-semibold opacity-80">{section.subtitle}</span> : null}
                                    </span>
                                </Button>
                            ))}
                        </div>
                        {selectedSection ? <LifecycleSectionDetail section={selectedSection} /> : <EmptyPanel text="暂无客户生命周期数据" />}
                    </div>

                    <div className="mt-4 flex flex-wrap gap-2">
                        {lifecycle.evidence.map((item) => (
                            <span key={item.title} className="inline-flex items-center gap-1 rounded-full border border-cyan-100 bg-cyan-50 px-3 py-1 text-xs font-bold text-cyan-800">
                                <FileSearch className="size-3.5" />
                                {item.title}
                            </span>
                        ))}
                    </div>
                </>
            ) : null}
        </section>
    );
}

function LifecycleSectionDetail({ section }: { section: InsightOperationLifecycleSection }) {
    const columns = useMemo(() => Array.from(new Set(section.rows.flatMap((row) => Object.keys(row.values)))), [section.rows]);
    return (
        <div className="min-w-0 rounded-[22px] border border-slate-200 bg-white p-4">
            <div className="flex flex-col justify-between gap-3 lg:flex-row lg:items-start">
                <div className="min-w-0">
                    <h3 className="text-lg font-black text-slate-950">{section.title}</h3>
                    {section.subtitle ? <p className="mt-1 text-sm font-semibold leading-6 text-slate-500">{section.subtitle}</p> : null}
                </div>
                {section.metrics.length ? (
                    <div className="flex flex-wrap gap-2">
                        {section.metrics.map((metric) => (
                            <span key={metric.key} className="rounded-full bg-slate-100 px-3 py-1 text-xs font-black text-slate-600">
                                {metric.label} {formatMetricValue(metric.value)}
                                {metric.unit ?? ""}
                            </span>
                        ))}
                    </div>
                ) : null}
            </div>

            <div className="mt-4 grid gap-2 md:grid-cols-2">
                {section.findings.map((finding) => (
                    <div key={finding} className="rounded-2xl bg-slate-50 px-4 py-3 text-sm font-semibold leading-6 text-slate-700">
                        {finding}
                    </div>
                ))}
            </div>

            <div className="mt-4 overflow-auto rounded-2xl border border-slate-200">
                <table className="w-full min-w-[760px] text-left text-sm">
                    <thead className="bg-slate-50 text-xs font-black text-slate-500">
                        <tr>
                            <th className="px-4 py-3">对象</th>
                            {columns.map((column) => (
                                <th key={column} className="px-4 py-3">
                                    {column}
                                </th>
                            ))}
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100 bg-white">
                        {section.rows.map((row) => (
                            <tr key={row.name} className="text-slate-700">
                                <td className="max-w-[16rem] truncate px-4 py-3 font-black text-slate-950" title={row.name}>
                                    {row.name}
                                </td>
                                {columns.map((column) => (
                                    <td key={`${row.name}-${column}`} className="max-w-[18rem] truncate px-4 py-3 font-semibold" title={String(row.values[column] ?? "")}>
                                        {formatMetricValue(row.values[column])}
                                    </td>
                                ))}
                            </tr>
                        ))}
                        {section.rows.length === 0 ? (
                            <tr>
                                <td colSpan={Math.max(columns.length + 1, 1)} className="px-4 py-10 text-center text-sm font-semibold text-slate-500">
                                    暂无明细数据
                                </td>
                            </tr>
                        ) : null}
                    </tbody>
                </table>
            </div>
        </div>
    );
}

function DomainDetail({ domain }: { domain: InsightOperationDomain }) {
    const rows = domain.rows;
    const columns = useMemo(() => Array.from(new Set(rows.flatMap((row) => Object.keys(row.values)))), [rows]);
    return (
        <div className="space-y-4">
            <div className="grid gap-3 sm:grid-cols-2">
                {domain.findings.map((finding) => (
                    <div key={finding} className="flex items-start gap-2 rounded-2xl border border-slate-100 bg-slate-50 px-4 py-3 text-sm font-semibold leading-6 text-slate-700">
                        <CircleDot className="mt-1 size-3 shrink-0 text-cyan-600" />
                        {finding}
                    </div>
                ))}
            </div>
            <div className="overflow-auto rounded-2xl border border-slate-200">
                <table className="w-full min-w-[640px] text-left text-sm">
                    <thead className="bg-slate-50 text-xs font-black text-slate-500">
                        <tr>
                            <th className="px-4 py-3">项目</th>
                            {columns.map((column) => (
                                <th key={column} className="px-4 py-3">
                                    {column}
                                </th>
                            ))}
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100 bg-white">
                        {rows.map((row) => (
                            <tr key={row.name} className="text-slate-700">
                                <td className="px-4 py-3 font-black text-slate-950">{row.name}</td>
                                {columns.map((column) => (
                                    <td key={`${row.name}-${column}`} className="px-4 py-3 font-semibold">
                                        {formatMetricValue(row.values[column])}
                                    </td>
                                ))}
                            </tr>
                        ))}
                        {rows.length === 0 ? (
                            <tr>
                                <td colSpan={Math.max(columns.length + 1, 1)} className="px-4 py-10 text-center text-sm font-semibold text-slate-500">
                                    暂无明细数据
                                </td>
                            </tr>
                        ) : null}
                    </tbody>
                </table>
            </div>
            <div className="flex flex-wrap gap-2">
                {domain.evidenceReports.map((report) => (
                    <span key={report} className="rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-bold text-slate-500">
                        {report}
                    </span>
                ))}
            </div>
        </div>
    );
}

function EmptyPanel({ text }: { text: string }) {
    return <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50 px-4 py-10 text-center text-sm font-semibold text-slate-500">{text}</div>;
}

function countSignals(signals: InsightOperationSignal[]) {
    return signals.reduce(
        (acc, signal) => {
            if (signal.level === "danger") acc.danger += 1;
            if (signal.level === "warning") acc.warning += 1;
            return acc;
        },
        { danger: 0, warning: 0 },
    );
}

function signalTone(level: string) {
    if (level === "danger") {
        return {
            panel: "border-rose-100 bg-rose-50",
            icon: "bg-rose-600 text-white",
            badge: "bg-rose-100 text-rose-700",
        };
    }
    if (level === "warning") {
        return {
            panel: "border-amber-100 bg-amber-50",
            icon: "bg-amber-500 text-white",
            badge: "bg-amber-100 text-amber-700",
        };
    }
    return {
        panel: "border-emerald-100 bg-emerald-50",
        icon: "bg-emerald-600 text-white",
        badge: "bg-emerald-100 text-emerald-700",
    };
}

function formatMetricValue(value: InsightOperationMetric["value"] | Record<string, unknown> | undefined) {
    if (value === null || value === undefined || value === "") return "--";
    if (typeof value === "number") {
        if (Math.abs(value) >= 10000) return value.toLocaleString("zh-CN", { maximumFractionDigits: 0 });
        if (Number.isInteger(value)) return value.toLocaleString("zh-CN");
        return value.toLocaleString("zh-CN", { maximumFractionDigits: 1 });
    }
    return String(value);
}
