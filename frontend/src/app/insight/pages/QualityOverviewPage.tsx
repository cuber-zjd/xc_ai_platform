import type React from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, BarChart3, Bot, CheckCircle2, Loader2, RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";

import { PageTitle, SectionCard } from "../components";
import { useInsightQualityOverview } from "../hooks";
import { PageContainer } from "../layout/PageContainer";
import type { InsightQualityMetric, InsightQualityReason, InsightQualitySourceMetric } from "../api";

export function QualityOverviewPage() {
    const qualityQuery = useInsightQualityOverview();
    const overview = qualityQuery.data;

    return (
        <PageContainer>
            <PageTitle
                title="质量运营"
                description="基于真实任务、采集、候选审核和质量规则沉淀的运营指标。"
                action={
                    <Button type="button" variant="outline" className="rounded-xl border-slate-200 bg-white" onClick={() => void qualityQuery.refetch()}>
                        {qualityQuery.isFetching ? <Loader2 className="size-4 animate-spin" /> : <RefreshCw className="size-4" />}
                        刷新
                    </Button>
                }
            />

            {qualityQuery.isLoading ? (
                <SectionCard>
                    <div className="flex min-h-28 items-center justify-center gap-3 text-sm font-bold text-slate-500 sm:min-h-[180px]">
                        <Loader2 className="size-5 animate-spin" />
                        正在读取质量指标
                    </div>
                </SectionCard>
            ) : qualityQuery.isError ? (
                <SectionCard>
                    <div className="flex min-h-[260px] flex-col items-center justify-center gap-3 text-center">
                        <AlertTriangle className="size-9 text-amber-500" />
                        <div className="text-base font-black text-slate-900">质量指标读取失败</div>
                        <div className="text-sm font-semibold text-slate-500">请确认后端质量运营接口可访问。</div>
                    </div>
                </SectionCard>
            ) : (
                <div className="space-y-5">
                    <div className="grid gap-2 md:hidden">
                        <a href="#quality-failures" className="rounded-xl border border-rose-100 bg-rose-50 px-4 py-3 text-sm font-black text-rose-700">
                            查看失败原因
                        </a>
                        <Link to="/insight/data-sources" className="rounded-xl border border-blue-100 bg-blue-50 px-4 py-3 text-sm font-black text-blue-700">
                            打开任务日志
                        </Link>
                    </div>

                    <SectionCard title="采集质量" description={`最后刷新：${formatDateTime(overview?.generated_at)}`}>
                        <MetricGrid metrics={overview?.collection_metrics ?? []} />
                    </SectionCard>

                    <div className="grid gap-5 xl:grid-cols-2">
                        <SectionCard title="审核质量" description="候选审核通过率、驳回率和人工修订情况。">
                            <MetricGrid metrics={overview?.review_metrics ?? []} />
                        </SectionCard>
                        <SectionCard title="AI 质量" description="采集质量规则、质量分和建议忽略情况。">
                            <MetricGrid metrics={overview?.ai_metrics ?? []} />
                        </SectionCard>
                    </div>

                    <div className="grid gap-5 xl:grid-cols-[0.9fr_1.1fr]">
                        <div id="quality-failures" className="scroll-mt-24">
                            <SectionCard
                                title="失败原因排行"
                                description="来自任务和采集结果的失败信息聚合。"
                                action={<LinkButton to="/insight/data-sources">任务日志</LinkButton>}
                            >
                                {(overview?.failure_reasons ?? []).length > 0 ? (
                                    <FailureReasonList rows={overview?.failure_reasons ?? []} />
                                ) : (
                                    <EmptyPanel text="暂无失败原因记录" />
                                )}
                            </SectionCard>
                        </div>

                        <SectionCard
                            title="数据源质量排行"
                            description="按失败任务数和任务总量排序，便于定位不稳定来源。"
                            action={<LinkButton to="/insight/data-sources">数据源配置</LinkButton>}
                        >
                            {(overview?.source_metrics ?? []).length > 0 ? <SourceQualityTable rows={overview?.source_metrics ?? []} /> : <EmptyPanel text="暂无数据源任务记录" />}
                        </SectionCard>
                    </div>

                    <div className="grid gap-3 md:grid-cols-3">
                        <QuickLink to="/insight/data-sources" icon={<BarChart3 className="size-5" />} title="查看任务日志" description="排查采集失败、调度暂停和重试记录。" />
                        <QuickLink to="/insight/intelligence" icon={<CheckCircle2 className="size-5" />} title="进入候选审核" description="处理低质量、重复或建议忽略的候选。" />
                        <QuickLink to="/insight/settings" icon={<Bot className="size-5" />} title="查看配置状态" description="确认采集、调度和模型相关配置边界。" />
                    </div>
                </div>
            )}
        </PageContainer>
    );
}

function FailureReasonList({ rows }: { rows: InsightQualityReason[] }) {
    return (
        <div className="space-y-2">
            {rows.map((item) => (
                <details key={`${item.category ?? "unknown"}-${item.reason}`} className="rounded-xl border border-slate-200 bg-white px-4 py-3">
                    <summary className="flex cursor-pointer list-none items-center justify-between gap-3">
                        <span className="min-w-0">
                            <span className="block truncate text-sm font-black text-slate-800">{item.reason}</span>
                            {item.suggestion ? <span className="mt-1 line-clamp-1 text-xs font-semibold text-slate-500">{item.suggestion}</span> : null}
                        </span>
                        <span className="shrink-0 text-sm font-black text-rose-600">{item.count} 次</span>
                    </summary>
                    {item.raw_reason ? (
                        <div className="mt-3 rounded-lg bg-slate-50 px-3 py-2 text-xs font-semibold leading-5 text-slate-500">
                            技术详情：{item.raw_reason}
                        </div>
                    ) : null}
                </details>
            ))}
        </div>
    );
}

function MetricGrid({ metrics }: { metrics: InsightQualityMetric[] }) {
    if (metrics.length === 0) {
        return <EmptyPanel text="暂无可计算指标" />;
    }
    return (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
            {metrics.map((metric) => (
                <div key={metric.key} className="rounded-xl border border-slate-200 bg-white px-4 py-3">
                    <div className="text-xs font-black text-slate-500">{metric.label}</div>
                    <div className="mt-2 text-2xl font-black text-slate-950">
                        {formatNumber(metric.value)}
                        <span className="ml-1 text-sm font-bold text-slate-500">{metric.unit}</span>
                    </div>
                    {metric.description ? <div className="mt-2 text-xs font-semibold text-slate-500">{metric.description}</div> : null}
                </div>
            ))}
        </div>
    );
}

function SourceQualityTable({ rows }: { rows: InsightQualitySourceMetric[] }) {
    return (
        <div className="overflow-hidden rounded-xl border border-slate-200 bg-white">
            <table className="w-full min-w-[680px] text-left text-sm">
                <thead className="bg-slate-50 text-xs font-black text-slate-500">
                    <tr>
                        <th className="px-4 py-3">数据源</th>
                        <th className="px-4 py-3">任务数</th>
                        <th className="px-4 py-3">成功</th>
                        <th className="px-4 py-3">失败</th>
                        <th className="px-4 py-3">成功率</th>
                    </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                    {rows.map((row) => (
                        <tr key={`${row.data_source_id ?? "none"}-${row.data_source_name}`} className="hover:bg-blue-50/50">
                            <td className="px-4 py-3 font-bold text-slate-800">{row.data_source_name}</td>
                            <td className="px-4 py-3 text-slate-600">{row.total_tasks}</td>
                            <td className="px-4 py-3 text-emerald-600">{row.success_tasks}</td>
                            <td className="px-4 py-3 text-rose-600">{row.failed_tasks}</td>
                            <td className="px-4 py-3 font-black text-slate-800">{row.success_rate}%</td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}

function QuickLink({ to, icon, title, description }: { to: string; icon: React.ReactNode; title: string; description: string }) {
    return (
        <Link to={to} className="rounded-xl border border-slate-200 bg-white p-4 transition hover:border-blue-200 hover:bg-blue-50/60">
            <div className="flex items-center gap-2 text-sm font-black text-slate-900">
                {icon}
                {title}
            </div>
            <p className="mt-2 text-sm leading-6 text-slate-600">{description}</p>
        </Link>
    );
}

function LinkButton({ to, children }: { to: string; children: React.ReactNode }) {
    return (
        <Link to={to} className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-black text-blue-600 transition hover:bg-blue-50">
            {children}
        </Link>
    );
}

function EmptyPanel({ text }: { text: string }) {
    return <div className="flex min-h-[140px] items-center justify-center rounded-xl border border-dashed border-slate-200 text-sm font-semibold text-slate-500">{text}</div>;
}

function formatDateTime(value?: string) {
    if (!value) return "未知";
    return new Date(value).toLocaleString("zh-CN", { hour12: false });
}

function formatNumber(value: number) {
    return Number.isInteger(value) ? String(value) : value.toFixed(1);
}
