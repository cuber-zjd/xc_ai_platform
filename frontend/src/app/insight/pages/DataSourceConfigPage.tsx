import { type FormEvent, type ReactNode, useMemo, useState } from "react";
import { AlertTriangle, CalendarClock, CheckCircle2, ClipboardList, Database, FileInput, Globe2, Loader2, MoreHorizontal, Pencil, Play, Power, RotateCcw, Search, Settings2, ShieldCheck, Trash2, X } from "lucide-react";
import { Link } from "react-router-dom";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

import { AccessRuleDialog } from "../components";
import { DemoCard, DemoTag, StatCard } from "../components/DemoPrimitives";
import { InsightSelect } from "../components/InsightSelect";
import {
    useInsightCreateDataSource,
    useInsightDataSourceExecutionLogs,
    useInsightDataSources,
    useInsightDeleteDataSource,
    useInsightExecuteDataSource,
    useInsightCompanies,
    useInsightRetryDataSourceSchedule,
    useInsightRunSchedulerOnce,
    useInsightSchedulerStatus,
    useInsightStartScheduler,
    useInsightStopScheduler,
    useInsightUpdateDataSource,
} from "../hooks";
import { PageContainer } from "../layout/PageContainer";
import type {
    InsightDataSourceCreate,
    InsightDataSourceFetchConfig,
    InsightDataSourceRead,
    InsightSchedulerStatusRead,
    InsightSearchDiscoveryResponse,
    InsightTaskRead,
} from "../api";

const sourceTypeOptions = [
    { value: "baidu_news", label: "百度资讯" },
    { value: "bocha_news", label: "博查资讯" },
    { value: "bocha_web", label: "博查网页" },
    { value: "official_site", label: "官网" },
    { value: "web_page", label: "通用网页" },
    { value: "multi_news", label: "多源资讯" },
];

const frequencyOptions = [
    { value: "manual", label: "手动" },
    { value: "15m", label: "每 15 分钟" },
    { value: "hourly", label: "每小时" },
    { value: "daily", label: "每天" },
    { value: "cron", label: "自定义 Cron" },
];

const dataSourceFilterOptions = [
    { value: "", label: "全部类型" },
    ...sourceTypeOptions,
];

const statusOptions = [
    { value: "", label: "全部状态" },
    { value: "enabled", label: "已启用" },
    { value: "disabled", label: "已停用" },
];

const autoReviewOptions = [
    { value: "off", label: "关闭自动审核" },
    { value: "high_confidence", label: "高置信度自动通过" },
    { value: "all", label: "全部自动通过" },
];

const candidateStatusText: Record<string, string> = {
    pending: "待审核",
    promoted: "已入池",
    rejected: "已拒绝",
    ignored: "已忽略",
    merged: "已合并",
};

const pageSize = 10;
type UtilityPanel = "scheduler" | "test" | "logs" | null;
type ExecuteResult = NonNullable<ReturnType<typeof useInsightExecuteDataSource>["data"]>;

const emptyForm: DataSourceFormState = {
    source_name: "",
    source_type: "baidu_news",
    company_id: "",
    base_url: "",
    fetch_frequency: "manual",
    keywords: "",
    include_keywords: "",
    exclude_keywords: "",
    max_results: 8,
    crawl_top_n: 8,
    freshness: "noLimit",
    enable_llm_filter: false,
    filter_prompt: "",
    auto_review_mode: "off",
    auto_review_min_confidence: 0.75,
    auto_review_required_tags: "",
    auto_review_intelligence_types: "",
    auto_add_to_report_pool: false,
    auto_report_folder: "",
    cron_expression: "",
    status: "enabled",
};

export function DataSourceConfigPage() {
    const [keyword, setKeyword] = useState("");
    const [sourceType, setSourceType] = useState("");
    const [status, setStatus] = useState("");
    const [editingSource, setEditingSource] = useState<InsightDataSourceRead | null>(null);
    const [formOpen, setFormOpen] = useState(false);
    const [importOpen, setImportOpen] = useState(false);
    const [executeKeyword, setExecuteKeyword] = useState("");
    const [selectedSourceId, setSelectedSourceId] = useState<number | null>(null);
    const [executingSourceId, setExecutingSourceId] = useState<number | null>(null);
    const [accessSource, setAccessSource] = useState<InsightDataSourceRead | null>(null);
    const [page, setPage] = useState(1);
    const [utilityPanel, setUtilityPanel] = useState<UtilityPanel>(null);
    const dataSourcesQuery = useInsightDataSources({
        page: 1,
        size: 50,
        keyword: keyword || undefined,
        source_type: sourceType || undefined,
        status: status || undefined,
    });
    const createMutation = useInsightCreateDataSource();
    const updateMutation = useInsightUpdateDataSource();
    const deleteMutation = useInsightDeleteDataSource();
    const executeMutation = useInsightExecuteDataSource();
    const retryScheduleMutation = useInsightRetryDataSourceSchedule();
    const schedulerStatusQuery = useInsightSchedulerStatus();
    const runSchedulerOnceMutation = useInsightRunSchedulerOnce();
    const startSchedulerMutation = useInsightStartScheduler();
    const stopSchedulerMutation = useInsightStopScheduler();
    const companiesQuery = useInsightCompanies({ page: 1, size: 100 });
    const dataSources = dataSourcesQuery.data?.items ?? [];
    const isDataSourcesLoading = dataSourcesQuery.isLoading && !dataSourcesQuery.data;
    const companyOptions = useMemo(
        () => [
            { value: "", label: "不关联企业" },
            ...((companiesQuery.data?.items ?? []).map((company) => ({
                value: String(company.id),
                label: company.short_name || company.name,
            }))),
        ],
        [companiesQuery.data?.items],
    );
    const selectedSource = dataSources.find((item) => item.id === selectedSourceId) ?? null;
    const executionLogsQuery = useInsightDataSourceExecutionLogs({ page: 1, size: 8, data_source_id: selectedSource?.id });
    const schedulerLogsQuery = useInsightDataSourceExecutionLogs({ page: 1, size: 5, task_type: "scheduler_tick" });
    const enabledCount = dataSources.filter((item) => item.status === "enabled").length;
    const scheduledCount = dataSources.filter((item) => item.fetch_frequency !== "manual").length;
    const dueScheduledCount = dataSources.filter((item) => item.schedule_enabled && isDue(item.next_run_time)).length;
    const llmFilterCount = dataSources.filter((item) => item.fetch_config?.enable_llm_filter).length;
    const lastResult = executeMutation.data;
    const lastSearchResults = lastResult?.search_results?.length ? lastResult.search_results : lastResult?.search_result ? [lastResult.search_result] : [];
    const lastExecutionErrors = lastResult?.execution_errors ?? [];
    const lastHitCount = lastSearchResults.reduce((sum, item) => sum + item.hits.length, 0);
    const lastCrawledCount = lastSearchResults.reduce((sum, item) => sum + item.crawled_results.length, 0);
    const lastCandidateCount = lastSearchResults.reduce((sum, item) => sum + item.candidates.length, 0);
    const totalPages = Math.max(1, Math.ceil(dataSources.length / pageSize));
    const currentPage = Math.min(page, totalPages);
    const pagedDataSources = dataSources.slice((currentPage - 1) * pageSize, currentPage * pageSize);

    const handleCreate = () => {
        setEditingSource(null);
        setFormOpen(true);
    };

    const handleEdit = (source: InsightDataSourceRead) => {
        setSelectedSourceId(source.id);
        setEditingSource(source);
        setFormOpen(true);
    };

    const handleToggle = (source: InsightDataSourceRead) => {
        updateMutation.mutate({
            dataSourceId: source.id,
            data: { status: source.status === "enabled" ? "disabled" : "enabled" },
        });
    };

    const handleExecute = (source: InsightDataSourceRead) => {
        const keywordOverride = executeKeyword.trim();
        setSelectedSourceId(source.id);
        setExecutingSourceId(source.id);
        toast.info(keywordOverride ? `开始测试：${source.source_name} / ${keywordOverride}` : `开始测试：${source.source_name}`);
        executeMutation.mutate(
            {
                dataSourceId: source.id,
                data: { keyword: keywordOverride || undefined },
            },
            {
                onSuccess: (result) => {
                    const results = result.search_results?.length ? result.search_results : result.search_result ? [result.search_result] : [];
                    const found = results.reduce((sum, item) => sum + item.hits.length, 0) || (result.manual_result ? 1 : 0);
                    const candidates = results.reduce((sum, item) => sum + item.candidates.length, 0) || (result.manual_result ? 1 : 0);
                    const errorCount = result.execution_errors?.length ?? 0;
                    toast.success(`测试完成：发现 ${found} 条，候选 ${candidates} 条${errorCount ? `，${errorCount} 个关键词失败` : ""}`);
                },
                onError: (error) => toast.error(getErrorMessage(error)),
                onSettled: () => setExecutingSourceId(null),
            },
        );
    };

    const handleRunDue = () => {
        runSchedulerOnceMutation.mutate(
            undefined,
            {
                onSuccess: (result) => {
                    const remaining = Math.max(result.due_count - result.executions.length, 0);
                    toast.success(`周期采集完成：成功 ${result.executed_count} 个，失败 ${result.failed_count} 个，剩余到期 ${remaining} 个`);
                },
                onError: (error) => toast.error(getErrorMessage(error)),
            },
        );
    };

    return (
        <PageContainer className="insight-page-locked flex min-h-0 flex-col gap-4">
            <div className="insight-page-heading">
                <div>
                    <h1 className="text-2xl font-black leading-tight tracking-tight text-slate-950 md:text-3xl">数据源配置</h1>
                    <p className="mt-2 text-sm font-semibold text-slate-500">维护官网、百度资讯、博查资讯和通用网页采集源，配置关键词、周期和筛选规则。</p>
                </div>
                <div className="insight-actions">
                    <Button variant="outline" className="h-10 rounded-xl bg-white" onClick={() => setImportOpen(true)}>
                        <FileInput className="size-4" />
                        批量导入
                    </Button>
                    <Button variant="outline" className="h-10 rounded-xl bg-white" onClick={handleRunDue} disabled={runSchedulerOnceMutation.isPending}>
                        {runSchedulerOnceMutation.isPending ? <Loader2 className="size-4 animate-spin" /> : <CalendarClock className="size-4" />}
                        立即扫描到期任务
                    </Button>
                    <Button className="h-10 rounded-xl px-5" onClick={handleCreate}>
                        + 新增数据源
                    </Button>
                </div>
            </div>

            <div className="grid grid-cols-2 gap-2 md:hidden">
                <MobileSourceStat title="数据源" value={String(dataSourcesQuery.data?.total ?? dataSources.length)} loading={isDataSourcesLoading} />
                <MobileSourceStat title="已启用" value={String(enabledCount)} loading={isDataSourcesLoading} />
                <MobileSourceStat title="周期采集" value={`${scheduledCount} / 到期 ${dueScheduledCount}`} loading={isDataSourcesLoading} />
                <MobileSourceStat title="LLM 筛选" value={String(llmFilterCount)} loading={isDataSourcesLoading} />
            </div>

            <div className="hidden md:block">
                <div className="insight-metric-strip">
                    <StatCard title="数据源总数" value={String(dataSourcesQuery.data?.total ?? dataSources.length)} compare="当前筛选" loading={isDataSourcesLoading} icon={<Database className="size-7" />} />
                    <StatCard title="已启用" value={String(enabledCount)} compare="可执行" loading={isDataSourcesLoading} tone="cyan" icon={<CheckCircle2 className="size-7" />} />
                    <StatCard title="周期采集" value={String(scheduledCount)} compare={`到期 ${dueScheduledCount}`} loading={isDataSourcesLoading} icon={<ClipboardList className="size-7" />} />
                    <StatCard title="LLM 筛选" value={String(llmFilterCount)} compare="已开启" loading={isDataSourcesLoading} tone="cyan" icon={<Settings2 className="size-7" />} />
                </div>
            </div>

            <DemoCard className="flex min-h-0 flex-1 flex-col p-3 sm:p-4">
                <div className="mb-3 grid gap-3 md:hidden">
                    <Input
                        className="h-10 rounded-xl border-slate-200 bg-white"
                        placeholder="搜索名称、编码或 URL"
                        value={keyword}
                        onChange={(event) => {
                            setKeyword(event.target.value);
                            setPage(1);
                        }}
                    />
                    <details className="rounded-xl border border-slate-100 bg-slate-50/80 px-3 py-2">
                        <summary className="cursor-pointer list-none text-sm font-black text-slate-700">筛选与工具</summary>
                        <div className="mt-3 grid gap-3">
                            <InsightSelect
                                value={sourceType}
                                options={dataSourceFilterOptions}
                                onChange={(value) => {
                                    setSourceType(value);
                                    setPage(1);
                                }}
                            />
                            <InsightSelect
                                value={status}
                                options={statusOptions}
                                onChange={(value) => {
                                    setStatus(value);
                                    setPage(1);
                                }}
                            />
                            <div className="insight-action-cluster justify-start">
                                <Button variant="outline" className="h-10 rounded-xl bg-white" onClick={() => setUtilityPanel("scheduler")}>
                                    <CalendarClock className="size-4" />
                                    调度器
                                </Button>
                                <Button variant="outline" className="h-10 rounded-xl bg-white" onClick={() => setUtilityPanel("test")}>
                                    <Play className="size-4" />
                                    测试
                                </Button>
                                <Button variant="outline" className="h-10 rounded-xl bg-white" onClick={() => setUtilityPanel("logs")}>
                                    <ClipboardList className="size-4" />
                                    日志
                                </Button>
                            </div>
                        </div>
                    </details>
                </div>

                <div className="mb-3 hidden gap-3 md:grid md:grid-cols-[minmax(0,1fr)_11rem_10rem_auto] md:items-center">
                    <Input
                        className="h-10 rounded-xl border-slate-200 bg-white"
                        placeholder="搜索名称、编码或 URL"
                        value={keyword}
                        onChange={(event) => {
                            setKeyword(event.target.value);
                            setPage(1);
                        }}
                    />
                    <InsightSelect
                        value={sourceType}
                        options={dataSourceFilterOptions}
                        onChange={(value) => {
                            setSourceType(value);
                            setPage(1);
                        }}
                    />
                    <InsightSelect
                        value={status}
                        options={statusOptions}
                        onChange={(value) => {
                            setStatus(value);
                            setPage(1);
                        }}
                    />
                    <div className="insight-action-cluster justify-start md:justify-end">
                        <Button variant="outline" className="h-10 rounded-xl bg-white" onClick={() => setUtilityPanel("scheduler")}>
                            <CalendarClock className="size-4" />
                            调度器
                        </Button>
                        <Button variant="outline" className="h-10 rounded-xl bg-white" onClick={() => setUtilityPanel("test")}>
                            <Play className="size-4" />
                            测试
                        </Button>
                        <Button variant="outline" className="h-10 rounded-xl bg-white" onClick={() => setUtilityPanel("logs")}>
                            <ClipboardList className="size-4" />
                            日志
                        </Button>
                    </div>
                </div>

                <div className="grid gap-3 md:hidden">
                    {isDataSourcesLoading ? (
                        <div className="rounded-xl border border-slate-200 bg-white px-4 py-8 text-center text-sm font-semibold text-slate-500">
                            正在读取数据源配置...
                        </div>
                    ) : null}
                    {pagedDataSources.map((source) => (
                        <DataSourceCard
                            key={source.id}
                            source={source}
                            selected={selectedSource?.id === source.id}
                            onEdit={handleEdit}
                            onToggle={handleToggle}
                            onSelect={(target) => setSelectedSourceId(target.id)}
                            onExecute={(target) => {
                                setUtilityPanel("test");
                                handleExecute(target);
                            }}
                            onRetry={(target) => {
                                retryScheduleMutation.mutate(target.id, {
                                    onSuccess: () => toast.success("已加入下一轮调度"),
                                    onError: (error) => toast.error(getErrorMessage(error)),
                                });
                            }}
                            onAccess={(target) => {
                                setSelectedSourceId(target.id);
                                setAccessSource(target);
                            }}
                            onDelete={(target) => deleteMutation.mutate(target.id)}
                            executing={executeMutation.isPending && executingSourceId === source.id}
                            retrying={retryScheduleMutation.isPending}
                            disabled={executeMutation.isPending}
                        />
                    ))}
                    {!isDataSourcesLoading && dataSources.length === 0 ? (
                        <div className="rounded-xl border border-dashed border-slate-200 bg-white px-4 py-8 text-center text-sm font-semibold text-slate-500">
                            暂无数据源。建议先在企业档案中新增观察企业，再为企业配置数据源。
                        </div>
                    ) : null}
                </div>

                <div className="insight-work-table hidden rounded-xl border border-slate-200 md:block">
                    <table className="insight-sticky-table min-w-[1180px] w-full table-fixed text-left text-sm">
                        <colgroup>
                            <col className="w-[300px]" />
                            <col className="w-[132px]" />
                            <col className="w-[116px]" />
                            <col className="w-[260px]" />
                            <col className="w-[96px]" />
                            <col className="w-[160px]" />
                            <col className="w-[92px]" />
                            <col className="w-[116px]" />
                        </colgroup>
                        <thead className="bg-slate-50 text-slate-500">
                            <tr>
                                <th className="insight-sticky-left px-4 py-3 font-bold">名称</th>
                                {["所属企业", "类型", "关键词", "周期", "下次执行", "状态"].map((head) => (
                                    <th key={head} className="px-4 py-3 font-bold">{head}</th>
                                ))}
                                <th className="insight-sticky-right px-4 py-3 text-right font-bold">操作</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100">
                            {isDataSourcesLoading ? (
                                <tr>
                                    <td colSpan={8} className="px-4 py-10 text-center text-sm font-semibold text-slate-500">
                                        正在读取数据源配置...
                                    </td>
                                </tr>
                            ) : null}
                            {pagedDataSources.map((source) => (
                                <DataSourceRow
                                    key={source.id}
                                    source={source}
                                    selected={selectedSource?.id === source.id}
                                    onEdit={handleEdit}
                                    onToggle={handleToggle}
                                    onSelect={(target) => setSelectedSourceId(target.id)}
                                    onExecute={(target) => {
                                        setUtilityPanel("test");
                                        handleExecute(target);
                                    }}
                                    onRetry={(target) => {
                                        retryScheduleMutation.mutate(target.id, {
                                            onSuccess: () => toast.success("已加入下一轮调度"),
                                            onError: (error) => toast.error(getErrorMessage(error)),
                                        });
                                    }}
                                    onAccess={(target) => {
                                        setSelectedSourceId(target.id);
                                        setAccessSource(target);
                                    }}
                                    onDelete={(target) => deleteMutation.mutate(target.id)}
                                    executing={executeMutation.isPending && executingSourceId === source.id}
                                    retrying={retryScheduleMutation.isPending}
                                    disabled={executeMutation.isPending}
                                />
                            ))}
                            {!dataSourcesQuery.isLoading && dataSources.length === 0 ? (
                                <tr>
                                    <td colSpan={8} className="px-4 py-10 text-center text-sm font-semibold text-slate-500">
                                        暂无数据源。建议先在企业档案中新增观察企业，再为企业配置百度资讯、博查资讯或官网数据源。
                                    </td>
                                </tr>
                            ) : null}
                        </tbody>
                    </table>
                </div>

                <div className="mt-3 flex flex-wrap items-center justify-between gap-3 text-sm font-semibold text-slate-500">
                    <span>第 {currentPage} / {totalPages} 页，每页 {pageSize} 条，共 {dataSources.length} 条</span>
                    <div className="insight-action-cluster">
                        <Button variant="outline" className="h-9 rounded-lg bg-white" disabled={currentPage <= 1} onClick={() => setPage((value) => Math.max(1, value - 1))}>
                            上一页
                        </Button>
                        <Button variant="outline" className="h-9 rounded-lg bg-white" disabled={currentPage >= totalPages} onClick={() => setPage((value) => Math.min(totalPages, value + 1))}>
                            下一页
                        </Button>
                    </div>
                </div>
            </DemoCard>

            <UtilityDrawer title={utilityPanelTitle(utilityPanel)} open={Boolean(utilityPanel)} onClose={() => setUtilityPanel(null)}>
                {utilityPanel === "scheduler" ? (
                    <SchedulerStatusCard
                        status={schedulerStatusQuery.data ?? null}
                        loading={schedulerStatusQuery.isLoading}
                        refreshing={schedulerStatusQuery.isFetching}
                        starting={startSchedulerMutation.isPending}
                        stopping={stopSchedulerMutation.isPending}
                        logs={schedulerLogsQuery.data?.items ?? []}
                        logsLoading={schedulerLogsQuery.isLoading}
                        onStart={() => {
                            startSchedulerMutation.mutate(undefined, {
                                onSuccess: () => toast.success("调度器已启动"),
                                onError: (error) => toast.error(getErrorMessage(error)),
                            });
                        }}
                        onStop={() => {
                            stopSchedulerMutation.mutate(undefined, {
                                onSuccess: () => toast.success("调度器已停止"),
                                onError: (error) => toast.error(getErrorMessage(error)),
                            });
                        }}
                    />
                ) : null}
                {utilityPanel === "test" ? (
                    <TestPanel
                        selectedSource={selectedSource}
                        executeKeyword={executeKeyword}
                        setExecuteKeyword={setExecuteKeyword}
                        executeMutationPending={executeMutation.isPending}
                        executeError={executeMutation.error}
                        lastResult={lastResult}
                        lastSearchResults={lastSearchResults}
                        lastExecutionErrors={lastExecutionErrors}
                        lastHitCount={lastHitCount}
                        lastCrawledCount={lastCrawledCount}
                        lastCandidateCount={lastCandidateCount}
                        onExecuteSelected={() => {
                            if (selectedSource) {
                                handleExecute(selectedSource);
                            }
                        }}
                    />
                ) : null}
                {utilityPanel === "logs" ? (
                    <ExecutionLogsPanel
                        selectedSource={selectedSource}
                        logs={executionLogsQuery.data?.items ?? []}
                        loading={executionLogsQuery.isLoading}
                        fetching={executionLogsQuery.isFetching}
                    />
                ) : null}
            </UtilityDrawer>

            {formOpen ? (
                <DataSourceForm
                    source={editingSource}
                    companyOptions={companyOptions}
                    onClose={() => setFormOpen(false)}
                    onSubmit={(payload) => {
                        if (editingSource) {
                            updateMutation.mutate({ dataSourceId: editingSource.id, data: payload }, { onSuccess: () => setFormOpen(false) });
                        } else {
                            createMutation.mutate(payload, { onSuccess: () => setFormOpen(false) });
                        }
                    }}
                    pending={createMutation.isPending || updateMutation.isPending}
                />
            ) : null}

            {importOpen ? (
                <ImportDialog
                    onClose={() => setImportOpen(false)}
                    onImport={(payloads) => {
                        Promise.all(payloads.map((payload) => createMutation.mutateAsync(payload))).then(() => setImportOpen(false));
                    }}
                    pending={createMutation.isPending}
                />
            ) : null}

            <AccessRuleDialog
                open={Boolean(accessSource)}
                onOpenChange={(open) => {
                    if (!open) setAccessSource(null);
                }}
                targetType="data_source"
                targetId={accessSource?.id ?? null}
                targetName={accessSource?.source_name ?? ""}
            />
        </PageContainer>
    );
}

function UtilityDrawer({ title, open, onClose, children }: { title: string; open: boolean; onClose: () => void; children: ReactNode }) {
    if (!open) {
        return null;
    }
    return (
        <>
            <button type="button" aria-label="关闭侧边栏" className="insight-drawer-backdrop" onClick={onClose} />
            <aside className="insight-drawer-panel">
                <div className="flex items-center justify-between gap-4 border-b border-slate-200 px-5 py-4">
                    <div className="min-w-0">
                        <h2 className="truncate text-xl font-black text-slate-950">{title}</h2>
                        <p className="mt-1 text-xs font-semibold text-slate-500">辅助任务独立处理，不挤占主列表工作区。</p>
                    </div>
                    <Button type="button" variant="outline" size="icon" className="insight-icon-button bg-white" onClick={onClose}>
                        <X className="size-4" />
                    </Button>
                </div>
                <div className="min-h-0 flex-1 overflow-y-auto p-4">
                    {children}
                </div>
            </aside>
        </>
    );
}

function utilityPanelTitle(panel: UtilityPanel) {
    if (panel === "scheduler") return "调度器";
    if (panel === "test") return "立即测试";
    if (panel === "logs") return "执行日志";
    return "";
}

function TestPanel({
    selectedSource,
    executeKeyword,
    setExecuteKeyword,
    executeMutationPending,
    executeError,
    lastResult,
    lastSearchResults,
    lastExecutionErrors,
    lastHitCount,
    lastCrawledCount,
    lastCandidateCount,
    onExecuteSelected,
}: {
    selectedSource: InsightDataSourceRead | null;
    executeKeyword: string;
    setExecuteKeyword: (value: string) => void;
    executeMutationPending: boolean;
    executeError: unknown;
    lastResult?: ExecuteResult;
    lastSearchResults: InsightSearchDiscoveryResponse[];
    lastExecutionErrors: ExecuteResult["execution_errors"];
    lastHitCount: number;
    lastCrawledCount: number;
    lastCandidateCount: number;
    onExecuteSelected: () => void;
}) {
    const executionErrors = lastExecutionErrors ?? [];
    return (
        <div className="space-y-4">
            <DemoCard className="min-w-0 p-4">
                <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                    <h3 className="text-lg font-black text-slate-900">测试目标</h3>
                    {executeMutationPending ? <Loader2 className="size-5 animate-spin text-blue-600" /> : <Play className="size-5 text-blue-600" />}
                </div>
                <div className="mb-3 rounded-xl border border-blue-100 bg-blue-50/70 px-3 py-2 text-sm font-bold text-blue-700">
                    当前选中：{selectedSource?.source_name ?? "点击主表格中的数据源"}
                </div>
                {selectedSource ? (
                    <Link
                        to={`/insight/intelligence?mode=candidate&data_source_id=${selectedSource.id}`}
                        className="mb-3 inline-flex h-9 items-center rounded-lg border border-blue-100 bg-white px-3 text-xs font-black text-blue-700 hover:bg-blue-50"
                    >
                        查看该数据源候选情报
                    </Link>
                ) : null}
                <label className="grid gap-2">
                    <span className="text-sm font-bold text-slate-700">临时覆盖关键词</span>
                    <Input className="h-11 rounded-xl border-slate-200 bg-white" value={executeKeyword} onChange={(event) => setExecuteKeyword(event.target.value)} placeholder="可留空，逐个执行数据源内全部关键词" />
                </label>
                <div className="mt-4 flex flex-wrap items-center gap-3">
                    <Button className="h-10 rounded-xl px-5" disabled={!selectedSource || executeMutationPending} onClick={onExecuteSelected}>
                        {executeMutationPending ? <Loader2 className="size-4 animate-spin" /> : <Play className="size-4" />}
                        测试当前数据源
                    </Button>
                    <p className="text-xs font-semibold leading-5 text-slate-500">测试会写入候选情报链路，方便后续审核。</p>
                </div>
            </DemoCard>

            {lastResult ? (
                <DemoCard className="min-w-0 p-4">
                    <h3 className="text-lg font-black text-slate-900">最近测试结果</h3>
                    <div className="mt-4 grid gap-3 sm:grid-cols-3">
                        <ResultMetric label="发现" value={`${lastHitCount || (lastResult.manual_result ? 1 : 0)} 条`} />
                        <ResultMetric label="已抓取" value={`${lastCrawledCount || (lastResult.manual_result ? 1 : 0)} 条`} />
                        <ResultMetric label="候选" value={`${lastCandidateCount || (lastResult.manual_result ? 1 : 0)} 条`} />
                    </div>
                    <div className="mt-4 max-h-[28rem] overflow-y-auto rounded-xl border border-blue-100 bg-blue-50/70 p-4 text-sm font-semibold leading-6 text-slate-700">
                        {lastSearchResults.length > 0 ? (
                            <div className="space-y-2">
                                {lastSearchResults.map((result, index) => (
                                    <div key={`${getSearchQuery(result)}-${index}`} className="rounded-lg bg-white/70 px-3 py-2">
                                        <div className="font-black text-slate-800">关键词：{getSearchQuery(result)}</div>
                                        <div className="mt-1 text-xs text-slate-600">
                                            发现 {result.hits.length} 条，已抓取 {result.crawled_results.length} 条，候选 {result.candidates.length} 条
                                        </div>
                                        <details className="mt-2 rounded-lg border border-slate-100 bg-slate-50/80 px-3 py-2">
                                            <summary className="cursor-pointer text-xs font-black text-slate-700">查看本关键词爬取详情</summary>
                                            <div className="mt-3 space-y-3">
                                                <SearchResultList title="百度返回结果" items={result.hits.map(toHitRecord)} emptyText="百度没有返回可解析的外部结果" />
                                                <SearchResultList title="已抓取正文" items={result.crawled_results.map(toResultRecord)} emptyText="没有成功抓取正文" tone="green" />
                                                <SearchResultList title="候选情报" items={result.candidates.map(toCandidateRecord)} emptyText="没有生成候选情报" tone="blue" />
                                            </div>
                                        </details>
                                    </div>
                                ))}
                            </div>
                        ) : lastResult.manual_result?.candidate.candidate_title ?? "测试完成"}
                    </div>
                    {lastResult.auto_review_summary?.enabled ? (
                        <div className="mt-3 grid gap-3 sm:grid-cols-4">
                            <ResultMetric label="自动检查" value={`${lastResult.auto_review_summary.checked_count} 条`} />
                            <ResultMetric label="自动通过" value={`${lastResult.auto_review_summary.promoted_count} 条`} />
                            <ResultMetric label="自动入池" value={`${lastResult.auto_review_summary.pooled_count} 条`} />
                            <ResultMetric label="保留候选" value={`${lastResult.auto_review_summary.skipped_count} 条`} />
                        </div>
                    ) : null}
                    {executionErrors.length > 0 ? (
                        <div className="mt-3 rounded-xl border border-orange-100 bg-orange-50 p-3 text-xs font-semibold leading-5 text-orange-700">
                            {executionErrors.map((item, index) => (
                                <div key={`${item.keyword ?? index}-${index}`}>
                                    {item.keyword ?? "未知关键词"}：{item.error ?? "执行失败"}
                                </div>
                            ))}
                        </div>
                    ) : null}
                </DemoCard>
            ) : null}

            {executeError ? (
                <DemoCard className="border-red-100 bg-red-50 p-5">
                    <div className="flex gap-3 text-sm font-semibold leading-6 text-red-700">
                        <AlertTriangle className="mt-0.5 size-5 shrink-0" />
                        {getErrorMessage(executeError)}
                    </div>
                </DemoCard>
            ) : null}
        </div>
    );
}

function ExecutionLogsPanel({
    selectedSource,
    logs,
    loading,
    fetching,
}: {
    selectedSource: InsightDataSourceRead | null;
    logs: InsightTaskRead[];
    loading: boolean;
    fetching: boolean;
}) {
    return (
        <DemoCard className="min-w-0 p-4">
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                <h3 className="text-lg font-black text-slate-900">最近执行日志</h3>
                {fetching ? <Loader2 className="size-5 animate-spin text-blue-600" /> : null}
            </div>
            <p className="mb-3 text-xs font-semibold text-slate-500">
                {selectedSource ? `仅显示：${selectedSource.source_name}` : "点击主表格中的数据源后，这里会只显示该数据源的执行记录。"}
            </p>
            <div className="max-h-[calc(100dvh-12rem)] space-y-3 overflow-y-auto pr-1">
                {logs.map((task) => (
                    <TaskLogItem key={task.id} task={task} />
                ))}
                {!loading && logs.length === 0 ? (
                    <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50 px-4 py-8 text-center text-sm font-semibold text-slate-500">
                        暂无执行日志，点击主表格中的“测试”后会在这里显示。
                    </div>
                ) : null}
            </div>
        </DemoCard>
    );
}

function SchedulerStatusCard({
    status,
    loading,
    refreshing,
    starting,
    stopping,
    logs,
    logsLoading,
    onStart,
    onStop,
}: {
    status: InsightSchedulerStatusRead | null;
    loading: boolean;
    refreshing: boolean;
    starting: boolean;
    stopping: boolean;
    logs: InsightTaskRead[];
    logsLoading: boolean;
    onStart: () => void;
    onStop: () => void;
}) {
    const lastResult = status?.last_result ?? {};
    const checkedCount = getRecordNumber(lastResult, "checked_count");
    const dueCount = getRecordNumber(lastResult, "due_count");
    const executedCount = getRecordNumber(lastResult, "executed_count");
    const failedCount = getRecordNumber(lastResult, "failed_count");
    const skippedReason = getRecordText(lastResult, "reason");
    const configWarnings = status?.config_warnings ?? [];
    const configRecommendations = status?.config_recommendations ?? [];
    return (
        <DemoCard className="min-w-0 p-4 sm:p-5">
            <div className="flex flex-wrap items-start justify-between gap-4">
                <div className="min-w-0">
                    <h2 className="text-xl font-black text-slate-900">调度器</h2>
                    <p className="mt-1 text-xs font-semibold leading-5 text-slate-500">后台按数据源周期扫描到期任务，统一写入执行日志。</p>
                </div>
                {loading || refreshing ? <Loader2 className="size-5 animate-spin text-blue-600" /> : <CalendarClock className="size-5 text-blue-600" />}
            </div>
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
                <ResultMetric label="运行状态" value={status?.running ? "运行中" : "已停止"} />
                <ResultMetric label="启用状态" value={status?.enabled ? "已启用" : "未启用"} />
                <ResultMetric label="扫描间隔" value={status ? `${status.interval_seconds} 秒` : "-"} />
                <ResultMetric label="单批上限" value={status ? `${status.batch_limit} 个` : "-"} />
                <ResultMetric label="失败暂停阈值" value={status ? `${status.failure_pause_threshold} 次` : "-"} />
                <ResultMetric label="互斥锁 ID" value={status ? String(status.advisory_lock_id) : "-"} />
            </div>
            {status ? (
                <div className={`mt-4 rounded-xl border px-3 py-3 text-xs font-semibold leading-5 ${status.config_health === "ready" ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-orange-200 bg-orange-50 text-orange-700"}`}>
                    <div className="font-black">{status.config_health === "ready" ? "调度配置已就绪" : "调度配置需要关注"}</div>
                    {configWarnings.map((item) => (
                        <div key={item} className="mt-1">
                            {item}
                        </div>
                    ))}
                    {configRecommendations.map((item) => (
                        <div key={item} className="mt-1 text-slate-600">
                            {item}
                        </div>
                    ))}
                </div>
            ) : null}
            <div className="mt-4 rounded-xl border border-slate-200 bg-slate-50 px-3 py-3 text-xs font-semibold leading-5 text-slate-600">
                <div>上次扫描：{formatDateTime(status?.last_tick_at)}</div>
                <div>上次成功：{formatDateTime(status?.last_success_at)}</div>
                <div>下次扫描：{formatDateTime(status?.next_tick_at)}</div>
                {status?.last_error ? <div className="text-red-600">上次错误：{status.last_error}</div> : null}
                {skippedReason ? <div className="text-orange-600">跳过原因：{skippedReason}</div> : null}
                {checkedCount !== null || dueCount !== null || executedCount !== null || failedCount !== null ? (
                    <div>
                        最近结果：检查 {checkedCount ?? 0} 个，到期 {dueCount ?? 0} 个，成功 {executedCount ?? 0} 个，失败 {failedCount ?? 0} 个
                    </div>
                ) : null}
            </div>
            <div className="mt-4 insight-actions justify-start">
                <Button size="sm" className="rounded-lg" onClick={onStart} disabled={starting || Boolean(status?.running)}>
                    {starting ? <Loader2 className="size-3.5 animate-spin" /> : null}
                    启动调度器
                </Button>
                <Button size="sm" variant="outline" className="rounded-lg bg-white" onClick={onStop} disabled={stopping || !status?.running}>
                    {stopping ? <Loader2 className="size-3.5 animate-spin" /> : null}
                    停止调度器
                </Button>
            </div>
            <div className="mt-4 rounded-xl border border-slate-200 bg-white px-3 py-3">
                <div className="mb-2 flex flex-wrap items-center justify-between gap-3">
                    <div className="text-xs font-black text-slate-700">最近调度批次</div>
                    {logsLoading ? <Loader2 className="size-4 animate-spin text-blue-600" /> : null}
                </div>
                <div className="space-y-2">
                    {logs.map((task) => (
                        <SchedulerBatchItem key={task.id} task={task} />
                    ))}
                    {!logsLoading && logs.length === 0 ? (
                        <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50 px-3 py-4 text-center text-xs font-semibold text-slate-500">
                            暂无调度批次
                        </div>
                    ) : null}
                </div>
            </div>
        </DemoCard>
    );
}

function SchedulerBatchItem({ task }: { task: InsightTaskRead }) {
    const payload = task.output_payload ?? {};
    const checkedCount = getRecordNumber(payload, "checked_count") ?? 0;
    const dueCount = getRecordNumber(payload, "due_count") ?? 0;
    const executedCount = getRecordNumber(payload, "executed_count") ?? 0;
    const failedCount = getRecordNumber(payload, "failed_count") ?? 0;
    return (
        <div className="rounded-lg border border-slate-100 bg-slate-50/80 px-3 py-2 text-xs font-semibold leading-5 text-slate-600">
            <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="font-black text-slate-800">{formatDateTime(task.started_at ?? task.create_time)}</div>
                <DemoTag tone={task.status === "success" ? "green" : task.status === "failed" ? "red" : "orange"}>{taskStatusLabel(task.status)}</DemoTag>
            </div>
            <div>检查 {checkedCount} 个，到期 {dueCount} 个，成功 {executedCount} 个，失败 {failedCount} 个</div>
            {task.error_message ? <div className="line-clamp-2 text-red-600">{task.error_message}</div> : null}
        </div>
    );
}

function MobileSourceStat({ title, value, loading }: { title: string; value: string; loading: boolean }) {
    return (
        <div className="rounded-xl border border-slate-200 bg-white px-3 py-3 shadow-sm">
            <div className="text-xs font-black text-slate-500">{title}</div>
            {loading ? <div className="mt-2 h-6 w-16 animate-pulse rounded-md bg-slate-200" /> : <div className="mt-1 text-xl font-black text-slate-950">{value}</div>}
        </div>
    );
}

function DataSourceCard({
    source,
    selected,
    onEdit,
    onToggle,
    onSelect,
    onExecute,
    onRetry,
    onAccess,
    onDelete,
    executing,
    retrying,
    disabled,
}: {
    source: InsightDataSourceRead;
    selected: boolean;
    onEdit: (source: InsightDataSourceRead) => void;
    onToggle: (source: InsightDataSourceRead) => void;
    onSelect: (source: InsightDataSourceRead) => void;
    onExecute: (source: InsightDataSourceRead) => void;
    onRetry: (source: InsightDataSourceRead) => void;
    onAccess: (source: InsightDataSourceRead) => void;
    onDelete: (source: InsightDataSourceRead) => void;
    executing: boolean;
    retrying: boolean;
    disabled: boolean;
}) {
    const keywords = source.fetch_config?.keywords ?? [];
    const schedulePaused = source.last_schedule_status === "paused" || Boolean(source.auto_paused_reason);
    const scheduleFailed = source.last_schedule_status === "failed" || schedulePaused || source.consecutive_failure_count > 0;
    return (
        <article className={cn("rounded-xl border bg-white p-4 shadow-sm", selected ? "border-blue-300 ring-2 ring-blue-100" : "border-slate-200")}>
            <button type="button" className="flex w-full items-start gap-3 text-left" onClick={() => onSelect(source)}>
                <div className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-blue-50 text-blue-600">
                    {source.source_type.includes("news") ? <Search className="size-5" /> : <Globe2 className="size-5" />}
                </div>
                <div className="min-w-0 flex-1">
                    <div className="line-clamp-2 text-sm font-black leading-5 text-slate-900">{source.source_name}</div>
                    <div className="mt-1 truncate text-xs font-semibold text-slate-500">{source.base_url || source.source_code}</div>
                </div>
            </button>
            <div className="mt-3 flex flex-wrap gap-2">
                {source.company_name ? <DemoTag tone="green">{source.company_short_name || source.company_name}</DemoTag> : <DemoTag tone="slate">未关联</DemoTag>}
                <DemoTag tone="blue">{sourceTypeLabel(source.source_type)}</DemoTag>
                <DemoTag tone={source.status === "enabled" ? "green" : "slate"}>{source.status === "enabled" ? "已启用" : "已停用"}</DemoTag>
            </div>
            <div className="mt-3 rounded-lg bg-slate-50 px-3 py-2 text-xs font-semibold leading-5 text-slate-600">
                <div className="line-clamp-2">关键词：{keywords.length > 0 ? keywords.join("、") : "未配置"}</div>
                <div className="mt-1">周期：{frequencyLabel(source.fetch_frequency)}</div>
                <div className="mt-1">下次执行：{source.schedule_enabled ? formatDateTime(source.next_run_time) : "手动触发"}</div>
                {scheduleFailed ? (
                    <div className="mt-1 text-red-500">
                        {scheduleStatusLabel(source.last_schedule_status)}
                        {source.consecutive_failure_count > 0 ? ` · 连续失败 ${source.consecutive_failure_count} 次` : ""}
                    </div>
                ) : null}
                {source.auto_paused_reason ? <div className="mt-1 line-clamp-2 text-red-500">{source.auto_paused_reason}</div> : null}
            </div>
            <div className="mt-3 flex items-center gap-2">
                <Button size="sm" className="h-9 flex-1 rounded-lg px-3" disabled={disabled || source.status !== "enabled"} onClick={() => onExecute(source)}>
                    {executing ? <Loader2 className="size-3.5 animate-spin" /> : <Play className="size-4" />}
                    {executing ? "测试中" : "测试"}
                </Button>
                <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                        <Button size="icon" variant="outline" className="h-9 w-11 rounded-lg border-slate-200 bg-white">
                            <MoreHorizontal className="size-4" />
                        </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end" className="w-40 rounded-xl">
                        <DropdownMenuLabel>操作</DropdownMenuLabel>
                        {scheduleFailed ? (
                            <DropdownMenuItem disabled={retrying} onClick={() => onRetry(source)}>
                                {retrying ? <Loader2 className="size-3.5 animate-spin" /> : <RotateCcw className="size-4" />}
                                重试调度
                            </DropdownMenuItem>
                        ) : null}
                        <DropdownMenuItem onClick={() => onEdit(source)}>
                            <Pencil className="size-4" />
                            编辑
                        </DropdownMenuItem>
                        <DropdownMenuItem onClick={() => onAccess(source)}>
                            <ShieldCheck className="size-4" />
                            权限
                        </DropdownMenuItem>
                        <DropdownMenuItem onClick={() => onToggle(source)}>
                            <Power className="size-4" />
                            {source.status === "enabled" ? "停用" : "启用"}
                        </DropdownMenuItem>
                        <DropdownMenuSeparator />
                        <DropdownMenuItem className="text-red-600 focus:text-red-600" onClick={() => onDelete(source)}>
                            <Trash2 className="size-4" />
                            删除
                        </DropdownMenuItem>
                    </DropdownMenuContent>
                </DropdownMenu>
            </div>
        </article>
    );
}

function DataSourceRow({
    source,
    selected,
    onEdit,
    onToggle,
    onSelect,
    onExecute,
    onRetry,
    onAccess,
    onDelete,
    executing,
    retrying,
    disabled,
}: {
    source: InsightDataSourceRead;
    selected: boolean;
    onEdit: (source: InsightDataSourceRead) => void;
    onToggle: (source: InsightDataSourceRead) => void;
    onSelect: (source: InsightDataSourceRead) => void;
    onExecute: (source: InsightDataSourceRead) => void;
    onRetry: (source: InsightDataSourceRead) => void;
    onAccess: (source: InsightDataSourceRead) => void;
    onDelete: (source: InsightDataSourceRead) => void;
    executing: boolean;
    retrying: boolean;
    disabled: boolean;
}) {
    const keywords = source.fetch_config?.keywords ?? [];
    const schedulePaused = source.last_schedule_status === "paused" || Boolean(source.auto_paused_reason);
    const scheduleFailed = source.last_schedule_status === "failed" || schedulePaused || source.consecutive_failure_count > 0;
    return (
        <tr className={selected ? "bg-blue-50/70" : "hover:bg-blue-50/40"}>
            <td className="insight-sticky-left px-4 py-4 align-middle">
                <button type="button" className="flex w-full items-center gap-3 text-left" onClick={() => onSelect(source)}>
                    <div className="flex size-10 items-center justify-center rounded-lg bg-blue-50 text-blue-600">
                        {source.source_type.includes("news") ? <Search className="size-5" /> : <Globe2 className="size-5" />}
                    </div>
                    <div className="min-w-0">
                        <div className="truncate font-bold text-slate-800">{source.source_name}</div>
                        <div className="truncate text-xs font-semibold text-slate-500">{source.base_url || source.source_code}</div>
                    </div>
                </button>
            </td>
            <td className="px-4 py-4 align-middle">
                {source.company_name ? (
                    <DemoTag tone="green">{source.company_short_name || source.company_name}</DemoTag>
                ) : (
                    <DemoTag tone="slate">未关联</DemoTag>
                )}
            </td>
            <td className="px-4 py-4 align-middle"><DemoTag tone="blue">{sourceTypeLabel(source.source_type)}</DemoTag></td>
            <td className="px-4 py-4 align-middle text-slate-600">
                <span className="line-clamp-2">{keywords.length > 0 ? keywords.join("、") : "未配置"}</span>
            </td>
            <td className="px-4 py-4 align-middle text-slate-700">{frequencyLabel(source.fetch_frequency)}</td>
            <td className="px-4 py-4 align-middle text-xs font-semibold text-slate-600">
                {source.schedule_enabled ? (
                    <div className="space-y-1">
                        <div>{formatDateTime(source.next_run_time)}</div>
                        <div className={scheduleFailed ? "text-red-500" : "text-slate-400"}>
                            {scheduleStatusLabel(source.last_schedule_status)}
                        </div>
                        {source.consecutive_failure_count > 0 ? (
                            <div className="text-red-500">连续失败 {source.consecutive_failure_count} 次</div>
                        ) : null}
                        {source.auto_paused_reason ? (
                            <div className="line-clamp-2 text-red-500">{source.auto_paused_reason}</div>
                        ) : null}
                    </div>
                ) : (
                    <span className="text-slate-400">手动触发</span>
                )}
            </td>
            <td className="px-4 py-4 align-middle">
                <DemoTag tone={source.status === "enabled" ? "green" : "slate"}>{source.status === "enabled" ? "已启用" : "已停用"}</DemoTag>
            </td>
            <td className="insight-sticky-right px-4 py-4 text-right align-middle">
                <div className="insight-row-actions">
                    <Button size="sm" className="h-9 rounded-lg px-3" disabled={disabled || source.status !== "enabled"} onClick={() => onExecute(source)}>
                        {executing ? <Loader2 className="size-3.5 animate-spin" /> : null}
                        {executing ? "测试中" : "测试"}
                    </Button>
                    <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                            <Button size="icon" variant="outline" className="insight-icon-button border-slate-200 bg-white">
                                <MoreHorizontal className="size-4" />
                            </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end" className="w-40 rounded-xl">
                            <DropdownMenuLabel>操作</DropdownMenuLabel>
                            {scheduleFailed ? (
                                <DropdownMenuItem disabled={retrying} onClick={() => onRetry(source)}>
                                    {retrying ? <Loader2 className="size-3.5 animate-spin" /> : <RotateCcw className="size-4" />}
                                    重试调度
                                </DropdownMenuItem>
                            ) : null}
                            <DropdownMenuItem onClick={() => onEdit(source)}>
                                <Pencil className="size-4" />
                                编辑
                            </DropdownMenuItem>
                            <DropdownMenuItem onClick={() => onAccess(source)}>
                                <ShieldCheck className="size-4" />
                                权限
                            </DropdownMenuItem>
                            <DropdownMenuItem onClick={() => onToggle(source)}>
                                <Power className="size-4" />
                                {source.status === "enabled" ? "停用" : "启用"}
                            </DropdownMenuItem>
                            <DropdownMenuSeparator />
                            <DropdownMenuItem className="text-red-600 focus:text-red-600" onClick={() => onDelete(source)}>
                                <Trash2 className="size-4" />
                                删除
                            </DropdownMenuItem>
                        </DropdownMenuContent>
                    </DropdownMenu>
                </div>
            </td>
        </tr>
    );
}

function DataSourceForm({
    source,
    companyOptions,
    onClose,
    onSubmit,
    pending,
}: {
    source: InsightDataSourceRead | null;
    companyOptions: Array<{ value: string; label: string }>;
    onClose: () => void;
    onSubmit: (payload: InsightDataSourceCreate) => void;
    pending: boolean;
}) {
    const [form, setForm] = useState<DataSourceFormState>(() => sourceToForm(source));
    const needsUrl = form.source_type === "official_site" || form.source_type === "web_page";

    const payload = useMemo<InsightDataSourceCreate>(() => ({
        source_name: form.source_name.trim(),
        source_type: form.source_type,
        company_id: parseOptionalNumber(form.company_id),
        base_url: form.base_url.trim() || undefined,
        fetch_frequency: form.fetch_frequency,
        schedule_enabled: form.fetch_frequency !== "manual",
        status: form.status,
        fetch_config: buildFetchConfig(form),
    }), [form]);

    const submit = (event: FormEvent<HTMLFormElement>) => {
        event.preventDefault();
        onSubmit(payload);
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/30 p-3 backdrop-blur-sm sm:p-4">
            <form onSubmit={submit} className="max-h-[92vh] w-full max-w-4xl overflow-auto rounded-2xl border border-slate-200 bg-white p-4 shadow-2xl sm:p-6">
                <div className="mb-5 flex flex-wrap items-center justify-between gap-4">
                    <h2 className="text-xl font-black text-slate-950 sm:text-2xl">{source ? "编辑数据源" : "新增数据源"}</h2>
                    <Button type="button" variant="outline" className="rounded-xl bg-white" onClick={onClose}>关闭</Button>
                </div>
                <div className="grid gap-4 md:grid-cols-2">
                    <Field label="名称" value={form.source_name} onChange={(value) => setForm((old) => ({ ...old, source_name: value }))} required />
                    <InsightSelect label="类型" value={form.source_type} options={sourceTypeOptions} onChange={(value) => setForm((old) => ({ ...old, source_type: value }))} />
                    <InsightSelect label="关联企业" value={form.company_id} options={companyOptions} onChange={(value) => setForm((old) => ({ ...old, company_id: value }))} />
                    {needsUrl ? <Field label="URL" value={form.base_url} onChange={(value) => setForm((old) => ({ ...old, base_url: value }))} required /> : null}
                    <InsightSelect label="抓取周期" value={form.fetch_frequency} options={frequencyOptions} onChange={(value) => setForm((old) => ({ ...old, fetch_frequency: value }))} />
                    {form.fetch_frequency === "cron" ? <Field label="Cron 表达式" value={form.cron_expression} onChange={(value) => setForm((old) => ({ ...old, cron_expression: value }))} /> : null}
                    <TextArea label="独立搜索关键词" value={form.keywords} onChange={(value) => setForm((old) => ({ ...old, keywords: value }))} placeholder="每行一个关键词，每个关键词会单独搜索一次。企业监控建议填写：\n蜜雪冰城\n蜜雪\nMixue" />
                    <TextArea label="必须包含词" value={form.include_keywords} onChange={(value) => setForm((old) => ({ ...old, include_keywords: value }))} placeholder="每行一个，留空则不限制" />
                    <TextArea label="排除词" value={form.exclude_keywords} onChange={(value) => setForm((old) => ({ ...old, exclude_keywords: value }))} placeholder="每行一个，例如：招聘\n股票" />
                    <div className="grid gap-4 sm:grid-cols-2">
                        <NumberField label="发现数量" value={form.max_results} onChange={(value) => setForm((old) => ({ ...old, max_results: value }))} />
                        <NumberField label="每词抓取上限" value={form.crawl_top_n} onChange={(value) => setForm((old) => ({ ...old, crawl_top_n: value }))} />
                    </div>
                    <label className="flex items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-bold text-slate-700">
                        <input type="checkbox" checked={form.enable_llm_filter} onChange={(event) => setForm((old) => ({ ...old, enable_llm_filter: event.target.checked }))} />
                        启用 LLM 筛选
                    </label>
                    <TextArea className="md:col-span-2" label="LLM 筛选提示词" value={form.filter_prompt} onChange={(value) => setForm((old) => ({ ...old, filter_prompt: value }))} placeholder="告诉模型什么资讯值得保留，例如：只保留与品牌开店、新品上市、供应链合作、食品饮料行业趋势相关的信息。" />
                    <div className="md:col-span-2 rounded-xl border border-blue-100 bg-blue-50/60 p-4">
                        <div className="mb-3 text-sm font-black text-slate-800">自动处理策略</div>
                        <div className="grid gap-4 md:grid-cols-2">
                            <InsightSelect label="自动审核" value={form.auto_review_mode} options={autoReviewOptions} onChange={(value) => setForm((old) => ({ ...old, auto_review_mode: value }))} />
                            <NumberField label="最低置信度" value={form.auto_review_min_confidence} min={0} max={1} step={0.05} onChange={(value) => setForm((old) => ({ ...old, auto_review_min_confidence: value }))} />
                            <TextArea label="限定标签" value={form.auto_review_required_tags} onChange={(value) => setForm((old) => ({ ...old, auto_review_required_tags: value }))} placeholder="每行一个，留空则不限制" />
                            <TextArea label="限定情报类型" value={form.auto_review_intelligence_types} onChange={(value) => setForm((old) => ({ ...old, auto_review_intelligence_types: value }))} placeholder="每行一个，例如：新品情报\n经营动态\n行业资讯" />
                            <label className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm font-bold text-slate-700">
                                <input type="checkbox" checked={form.auto_add_to_report_pool} onChange={(event) => setForm((old) => ({ ...old, auto_add_to_report_pool: event.target.checked }))} />
                                自动加入报告素材池
                            </label>
                            <Field label="素材池文件夹" value={form.auto_report_folder} onChange={(value) => setForm((old) => ({ ...old, auto_report_folder: value }))} placeholder="可留空" />
                        </div>
                    </div>
                </div>
                <div className="mt-6 insight-actions border-t border-slate-100 pt-5">
                    <Button type="button" variant="outline" className="rounded-xl bg-white" onClick={onClose}>取消</Button>
                    <Button type="submit" disabled={pending || !payload.source_name || (needsUrl && !payload.base_url)} className="rounded-xl">
                        {pending ? <Loader2 className="size-4 animate-spin" /> : null}
                        保存数据源
                    </Button>
                </div>
            </form>
        </div>
    );
}

function ImportDialog({ onClose, onImport, pending }: { onClose: () => void; onImport: (payloads: InsightDataSourceCreate[]) => void; pending: boolean }) {
    const [text, setText] = useState("蜜雪冰城资讯,baidu_news,,蜜雪冰城 新品|蜜雪冰城 开店,manual\n奈雪官网,official_site,https://www.naixue.com,,daily");
    const payloads = parseImportText(text);
    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/30 p-3 backdrop-blur-sm sm:p-4">
            <div className="max-h-[92vh] w-full max-w-3xl overflow-auto rounded-2xl border border-slate-200 bg-white p-4 shadow-2xl sm:p-6">
                <div className="mb-4 flex flex-wrap items-center justify-between gap-4">
                    <h2 className="text-xl font-black text-slate-950 sm:text-2xl">批量导入数据源</h2>
                    <Button variant="outline" className="rounded-xl bg-white" onClick={onClose}>关闭</Button>
                </div>
                <p className="mb-3 text-sm font-semibold text-slate-500">每行格式：名称,类型,URL,关键词1|关键词2,周期。类型可填 baidu_news、bocha_news、official_site、web_page。</p>
                <textarea className="min-h-56 w-full rounded-xl border border-slate-200 bg-white p-3 text-sm font-semibold text-slate-700" value={text} onChange={(event) => setText(event.target.value)} />
                <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
                    <span className="text-sm font-semibold text-slate-500">将导入 {payloads.length} 条</span>
                    <Button className="rounded-xl" disabled={pending || payloads.length === 0} onClick={() => onImport(payloads)}>
                        导入
                    </Button>
                </div>
            </div>
        </div>
    );
}

function Field({
    label,
    value,
    onChange,
    required,
    placeholder,
}: {
    label: string;
    value: string;
    onChange: (value: string) => void;
    required?: boolean;
    placeholder?: string;
}) {
    return (
        <label className="grid gap-2">
            <span className="text-sm font-bold text-slate-700">{label}</span>
            <Input required={required} placeholder={placeholder} className="h-11 rounded-xl border-slate-200 bg-white" value={value} onChange={(event) => onChange(event.target.value)} />
        </label>
    );
}

function NumberField({ label, value, onChange, min = 0, max = 20, step = 1 }: { label: string; value: number; onChange: (value: number) => void; min?: number; max?: number; step?: number }) {
    return (
        <label className="grid gap-2">
            <span className="text-sm font-bold text-slate-700">{label}</span>
            <Input type="number" min={min} max={max} step={step} className="h-11 rounded-xl border-slate-200 bg-white" value={value} onChange={(event) => onChange(Number(event.target.value))} />
        </label>
    );
}

function TextArea({ label, value, onChange, placeholder, className }: { label: string; value: string; onChange: (value: string) => void; placeholder?: string; className?: string }) {
    return (
        <label className={`grid gap-2 ${className ?? ""}`}>
            <span className="text-sm font-bold text-slate-700">{label}</span>
            <textarea className="min-h-28 rounded-xl border border-slate-200 bg-white p-3 text-sm font-semibold text-slate-700" value={value} onChange={(event) => onChange(event.target.value)} placeholder={placeholder} />
        </label>
    );
}

function ResultMetric({ label, value }: { label: string; value: string }) {
    return (
        <div className="rounded-xl border border-slate-200 bg-white px-3 py-3">
            <div className="text-xs font-bold text-slate-500">{label}</div>
            <div className="mt-1 text-sm font-black text-slate-800">{value}</div>
        </div>
    );
}

function getSearchQuery(result: InsightSearchDiscoveryResponse) {
    const query = result.task.input_payload?.query;
    return typeof query === "string" && query.trim() ? query : "未记录";
}

function SearchResultList({
    title,
    items,
    emptyText,
    tone = "slate",
}: {
    title: string;
    items: Record<string, unknown>[];
    emptyText: string;
    tone?: "slate" | "green" | "blue" | "red";
}) {
    const toneClass = {
        slate: "border-slate-200 bg-white text-slate-700",
        green: "border-emerald-100 bg-emerald-50 text-emerald-700",
        blue: "border-blue-100 bg-blue-50 text-blue-700",
        red: "border-red-100 bg-red-50 text-red-700",
    }[tone];
    return (
        <div className={`rounded-lg border px-3 py-2 ${toneClass}`}>
            <div className="mb-2 text-xs font-black">{title}</div>
            {items.length > 0 ? (
                <div className="space-y-2">
                    {items.map((item, index) => {
                        const titleText = getRecordText(item, "title") ?? getRecordText(item, "source_title") ?? getRecordText(item, "url") ?? `结果 ${index + 1}`;
                        const url = getRecordText(item, "url") ?? getRecordText(item, "source_url");
                        const summary = getRecordText(item, "summary") ?? getRecordText(item, "snippet") ?? getRecordText(item, "error");
                        const status = getRecordText(item, "review_status") ?? getRecordText(item, "status");
                        const tags = getRecordTagNames(item);
                        return (
                            <div key={`${url ?? titleText}-${index}`} className="rounded-md bg-white/70 px-2 py-2 text-xs font-semibold leading-5">
                                {url ? (
                                    <a className="line-clamp-1 font-black text-blue-700 hover:underline" href={url} target="_blank" rel="noreferrer">
                                        {titleText}
                                    </a>
                                ) : (
                                    <div className="line-clamp-1 font-black">{titleText}</div>
                                )}
                                {summary ? <div className="mt-1 line-clamp-2 opacity-80">{summary}</div> : null}
                                {status || tags.length > 0 ? (
                                    <div className="mt-1 flex flex-wrap gap-1">
                                        {status ? <DemoTag tone={status === "ignored" ? "orange" : "slate"}>{candidateStatusText[status] ?? status}</DemoTag> : null}
                                        {tags.map((tag) => <DemoTag key={tag} tone={tag.includes("重复") || tag.includes("低质量") || tag.includes("忽略") ? "orange" : "cyan"}>{tag}</DemoTag>)}
                                    </div>
                                ) : null}
                                {url ? <div className="mt-1 line-clamp-1 opacity-60">{url}</div> : null}
                            </div>
                        );
                    })}
                </div>
            ) : (
                <div className="text-xs font-semibold opacity-70">{emptyText}</div>
            )}
        </div>
    );
}

function toResultRecord(item: { source_title?: string | null; source_url: string; snippet?: string | null }) {
    return {
        title: item.source_title,
        url: item.source_url,
        snippet: item.snippet,
    };
}

function toHitRecord(item: { title?: string | null; url: string; snippet?: string | null }) {
    return {
        title: item.title,
        url: item.url,
        snippet: item.snippet,
    };
}

function toCandidateRecord(item: {
    candidate_title?: string | null;
    candidate_summary?: string | null;
    review_status?: string;
    suggested_tags?: Array<{ name?: string } & Record<string, unknown>> | null;
    confidence?: number;
}) {
    return {
        title: item.candidate_title,
        summary: item.candidate_summary,
        review_status: item.review_status,
        suggested_tags: item.suggested_tags,
        confidence: item.confidence,
    };
}

function TaskLogItem({ task }: { task: InsightTaskRead }) {
    const payload = task.output_payload ?? {};
    const hitCount = getPayloadNumber(payload, "hit_count");
    const candidateIds = getPayloadArray(payload, "candidate_ids");
    const crawledIds = getPayloadArray(payload, "crawled_result_ids");
    const filterSummary = getPayloadObject(payload, "filter_summary");
    const hitItems = getPayloadRecords(payload, "hit_items");
    const crawledItems = getPayloadRecords(payload, "crawled_items");
    const candidateItems = getPayloadRecords(payload, "candidate_items");
    const crawlErrors = getPayloadRecords(payload, "crawl_errors");
    const keptItems = getPayloadRecords(payload, "kept_items");
    const rejectedItems = getPayloadRecords(payload, "rejected_items");
    const channelErrors = getPayloadArray(payload, "channel_errors").filter((item): item is string => typeof item === "string");
    const hasCrawlDetails = hitItems.length > 0 || crawledItems.length > 0 || candidateItems.length > 0 || crawlErrors.length > 0;
    const hasFilterDetails = Object.keys(filterSummary).length > 0 || keptItems.length > 0 || rejectedItems.length > 0 || channelErrors.length > 0 || hasCrawlDetails;
    return (
        <div className="rounded-xl border border-slate-200 bg-white p-4">
            <div className="flex flex-wrap items-start justify-between gap-4">
                <div className="min-w-0">
                    <div className="flex items-center gap-2">
                        <DemoTag tone={task.status === "success" ? "green" : task.status === "failed" ? "red" : "orange"}>
                            {taskStatusLabel(task.status)}
                        </DemoTag>
                        <span className="truncate text-sm font-black text-slate-800">{taskTypeLabel(task.task_type)}</span>
                    </div>
                    <div className="mt-2 text-xs font-semibold text-slate-500">
                        {formatDateTime(task.started_at ?? task.create_time)}
                    </div>
                </div>
                <div className="shrink-0 text-right text-xs font-semibold text-slate-500">
                    进度 {task.progress}%
                </div>
            </div>
            <div className="mt-3 grid gap-2 sm:grid-cols-3">
                <ResultMetric label="发现" value={`${hitCount ?? 0} 条`} />
                <ResultMetric label="已抓取" value={`${crawledIds.length || (task.task_type === "manual_url_crawl" && task.status === "success" ? 1 : 0)} 条`} />
                <ResultMetric label="候选" value={`${candidateIds.length || (task.output_payload?.candidate_title ? 1 : 0)} 条`} />
            </div>
            {task.error_message ? (
                <div className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-xs font-semibold leading-5 text-red-700">
                    {task.error_message}
                </div>
            ) : null}
            {hasFilterDetails ? (
                <details className="mt-3 rounded-xl border border-slate-100 bg-slate-50/70 px-3 py-2">
                    <summary className="cursor-pointer text-xs font-black text-slate-700">查看爬取详情</summary>
                    <div className="mt-3 space-y-3">
                        <div className="grid gap-2 sm:grid-cols-4">
                            <ResultMetric label="过滤前" value={`${getRecordNumber(filterSummary, "source_hit_count") ?? hitCount ?? 0} 条`} />
                            <ResultMetric label="规则保留" value={`${getRecordNumber(filterSummary, "rule_kept_count") ?? 0} 条`} />
                            <ResultMetric label="去重保留" value={`${getRecordNumber(filterSummary, "dedupe_kept_count") ?? 0} 条`} />
                            <ResultMetric label="最终保留" value={`${getRecordNumber(filterSummary, "final_hit_count") ?? hitCount ?? 0} 条`} />
                        </div>
                        {typeof filterSummary.llm_filter_message === "string" ? (
                            <div className="rounded-lg border border-blue-100 bg-blue-50 px-3 py-2 text-xs font-semibold leading-5 text-blue-700">
                                {filterSummary.llm_filter_message}
                            </div>
                        ) : null}
                        {hasCrawlDetails ? (
                            <div className="space-y-3">
                                <SearchResultList title="搜索命中 URL" items={hitItems} emptyText="没有记录搜索命中明细" />
                                <SearchResultList title="正文抓取成功" items={crawledItems} emptyText="没有成功抓取正文" tone="green" />
                                <SearchResultList title="候选情报" items={candidateItems} emptyText="没有生成候选情报" tone="blue" />
                                <SearchResultList title="抓取失败" items={crawlErrors} emptyText="没有抓取失败记录" tone="red" />
                            </div>
                        ) : (
                            <div className="rounded-lg border border-orange-100 bg-orange-50 px-3 py-2 text-xs font-semibold leading-5 text-orange-700">
                                这条日志由旧版本生成，只记录了数量和 ID，没有保存 URL 明细。重新点击“测试”后会记录完整爬取详情。
                            </div>
                        )}
                        {keptItems.length > 0 ? (
                            <FilterList title="保留结果" items={keptItems.slice(0, 3)} tone="green" />
                        ) : null}
                        {rejectedItems.length > 0 ? (
                            <FilterList title="过滤原因" items={rejectedItems.slice(0, 5)} tone="red" />
                        ) : null}
                        {channelErrors.length > 0 ? (
                            <div className="rounded-lg border border-orange-100 bg-orange-50 px-3 py-2 text-xs font-semibold leading-5 text-orange-700">
                                {channelErrors.map((error) => (
                                    <div key={error}>{error}</div>
                                ))}
                            </div>
                        ) : null}
                    </div>
                </details>
            ) : null}
        </div>
    );
}

function FilterList({ title, items, tone }: { title: string; items: Record<string, unknown>[]; tone: "green" | "red" }) {
    const toneClass = tone === "green" ? "border-emerald-100 bg-emerald-50 text-emerald-700" : "border-red-100 bg-red-50 text-red-700";
    return (
        <div className={`rounded-lg border px-3 py-2 ${toneClass}`}>
            <div className="mb-2 text-xs font-black">{title}</div>
            <div className="space-y-2">
                {items.map((item, index) => (
                    <div key={`${String(item.url ?? item.title ?? index)}-${index}`} className="text-xs font-semibold leading-5">
                        <div className="line-clamp-1 font-black">{String(item.title ?? item.url ?? "未命名结果")}</div>
                        {typeof item.reason === "string" ? <div>{item.reason}</div> : null}
                        {typeof item.url === "string" ? <div className="line-clamp-1 opacity-80">{item.url}</div> : null}
                    </div>
                ))}
            </div>
        </div>
    );
}

function getPayloadNumber(payload: Record<string, unknown>, key: string) {
    const value = payload[key];
    return typeof value === "number" ? value : null;
}

function getPayloadArray(payload: Record<string, unknown>, key: string) {
    const value = payload[key];
    return Array.isArray(value) ? value : [];
}

function getPayloadObject(payload: Record<string, unknown>, key: string): Record<string, unknown> {
    const value = payload[key];
    return typeof value === "object" && value !== null && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function getPayloadRecords(payload: Record<string, unknown>, key: string): Record<string, unknown>[] {
    return getPayloadArray(payload, key).filter(
        (item): item is Record<string, unknown> => typeof item === "object" && item !== null && !Array.isArray(item),
    );
}

function getRecordNumber(record: Record<string, unknown>, key: string) {
    const value = record[key];
    return typeof value === "number" ? value : null;
}

function getRecordText(record: Record<string, unknown>, key: string) {
    const value = record[key];
    return typeof value === "string" && value.trim() ? value : null;
}

function getRecordTagNames(record: Record<string, unknown>) {
    const tags = record.suggested_tags;
    if (!Array.isArray(tags)) {
        return [];
    }
    return tags
        .map((tag) => (typeof tag === "object" && tag !== null && "name" in tag ? String((tag as { name?: unknown }).name ?? "") : ""))
        .filter(Boolean)
        .slice(0, 4);
}

function taskTypeLabel(value: string) {
    const labels: Record<string, string> = {
        manual_url_crawl: "网页抓取",
        keyword_search_discovery: "关键词发现",
        scheduler_tick: "调度扫描",
    };
    return labels[value] ?? value;
}

function taskStatusLabel(value: string) {
    const labels: Record<string, string> = {
        pending: "待执行",
        running: "执行中",
        success: "成功",
        failed: "失败",
        cancelled: "已取消",
    };
    return labels[value] ?? value;
}

function scheduleStatusLabel(value?: string | null) {
    const labels: Record<string, string> = {
        waiting: "等待执行",
        running: "执行中",
        success: "上次成功",
        failed: "上次失败",
        paused: "已自动暂停",
    };
    return value ? labels[value] ?? value : "等待执行";
}

function isDue(value?: string | null) {
    if (!value) {
        return true;
    }
    const date = new Date(value);
    return !Number.isNaN(date.getTime()) && date.getTime() <= Date.now();
}

function formatDateTime(value?: string | null) {
    if (!value) {
        return "-";
    }
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
        return value.slice(0, 16);
    }
    const pad = (input: number) => String(input).padStart(2, "0");
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function sourceToForm(source: InsightDataSourceRead | null): DataSourceFormState {
    if (!source) {
        return emptyForm;
    }
    const config = source.fetch_config ?? {};
    return {
        source_name: source.source_name,
        source_type: source.source_type,
        company_id: source.company_id ? String(source.company_id) : "",
        base_url: source.base_url ?? "",
        fetch_frequency: source.fetch_frequency,
        keywords: (config.keywords ?? []).join("\n"),
        include_keywords: (config.include_keywords ?? []).join("\n"),
        exclude_keywords: (config.exclude_keywords ?? []).join("\n"),
        max_results: config.max_results ?? 8,
        crawl_top_n: config.crawl_top_n ?? 8,
        freshness: config.freshness ?? "noLimit",
        enable_llm_filter: Boolean(config.enable_llm_filter),
        filter_prompt: config.filter_prompt ?? "",
        auto_review_mode: config.auto_review_mode ?? "off",
        auto_review_min_confidence: config.auto_review_min_confidence ?? 0.75,
        auto_review_required_tags: (config.auto_review_required_tags ?? []).join("\n"),
        auto_review_intelligence_types: (config.auto_review_intelligence_types ?? []).join("\n"),
        auto_add_to_report_pool: Boolean(config.auto_add_to_report_pool),
        auto_report_folder: config.auto_report_folder ?? "",
        cron_expression: config.cron_expression ?? "",
        status: source.status,
    };
}

function buildFetchConfig(form: DataSourceFormState): InsightDataSourceFetchConfig {
    return {
        keywords: splitLines(form.keywords),
        include_keywords: splitLines(form.include_keywords),
        exclude_keywords: splitLines(form.exclude_keywords),
        max_results: form.max_results,
        crawl_top_n: form.crawl_top_n,
        freshness: form.freshness,
        schedule_type: form.fetch_frequency,
        cron_expression: form.cron_expression || null,
        enable_llm_filter: form.enable_llm_filter,
        filter_prompt: form.filter_prompt || null,
        llm_failure_policy: "keep",
        auto_review_mode: form.auto_review_mode,
        auto_review_min_confidence: form.auto_review_min_confidence,
        auto_review_required_tags: splitLines(form.auto_review_required_tags),
        auto_review_intelligence_types: splitLines(form.auto_review_intelligence_types),
        auto_add_to_report_pool: form.auto_add_to_report_pool,
        auto_report_folder: form.auto_report_folder || null,
    };
}

function parseImportText(text: string): InsightDataSourceCreate[] {
    return text
        .split(/\r?\n/)
        .map((line) => line.trim())
        .filter(Boolean)
        .map((line) => {
            const [name, type, url, keywords, frequency] = line.split(",").map((item) => item?.trim() ?? "");
            return {
                source_name: name,
                source_type: type || "baidu_news",
                base_url: url || undefined,
                fetch_frequency: frequency || "manual",
                schedule_enabled: Boolean(frequency && frequency !== "manual"),
                status: "enabled",
                fetch_config: {
                    keywords: keywords ? keywords.split("|").map((item) => item.trim()).filter(Boolean) : [],
                    max_results: 8,
                    crawl_top_n: 8,
                    freshness: "noLimit",
                    schedule_type: frequency || "manual",
                },
            };
        })
        .filter((item) => item.source_name);
}

function splitLines(value: string) {
    return value.split(/\r?\n/).map((item) => item.trim()).filter(Boolean);
}

function parseOptionalNumber(value: string) {
    const trimmed = value.trim();
    if (!trimmed) {
        return undefined;
    }
    const parsed = Number(trimmed);
    return Number.isFinite(parsed) ? parsed : undefined;
}

function sourceTypeLabel(value: string) {
    return sourceTypeOptions.find((item) => item.value === value)?.label ?? value;
}

function frequencyLabel(value: string) {
    return frequencyOptions.find((item) => item.value === value)?.label ?? value;
}

function getErrorMessage(error: unknown): string {
    if (typeof error === "object" && error !== null && "response" in error) {
        const response = (error as { response?: { data?: { detail?: string } } }).response;
        return response?.data?.detail ?? "执行失败，请检查数据源配置。";
    }
    return error instanceof Error ? error.message : "执行失败，请稍后重试。";
}

interface DataSourceFormState {
    source_name: string;
    source_type: string;
    company_id: string;
    base_url: string;
    fetch_frequency: string;
    keywords: string;
    include_keywords: string;
    exclude_keywords: string;
    max_results: number;
    crawl_top_n: number;
    freshness: string;
    enable_llm_filter: boolean;
    filter_prompt: string;
    auto_review_mode: string;
    auto_review_min_confidence: number;
    auto_review_required_tags: string;
    auto_review_intelligence_types: string;
    auto_add_to_report_pool: boolean;
    auto_report_folder: string;
    cron_expression: string;
    status: string;
}
