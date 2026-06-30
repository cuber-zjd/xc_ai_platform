import { type FormEvent, type ReactNode, useEffect, useMemo, useState } from "react";
import { AlertTriangle, CalendarClock, CheckCircle2, ClipboardList, Database, FileInput, Globe2, Layers3, Loader2, MoreHorizontal, Pencil, Play, Power, RotateCcw, Search, Settings2, ShieldCheck, Trash2, Users, X } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";
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
    useInsightBulkActionDataSources,
    useInsightBatchCreateDataSources,
    useInsightDataSourceGroups,
    useInsightDataSourceExecutionLogs,
    useInsightDataSources,
    useInsightDeleteDataSource,
    useInsightExecuteDataSource,
    useInsightImportDataSources,
    useInsightPreviewImportDataSources,
    useInsightCompanies,
    useInsightRetryDataSourceSchedule,
    useInsightRunSchedulerOnce,
    useInsightSchedulerStatus,
    useInsightStartScheduler,
    useInsightStopScheduler,
    useInsightUpdateDataSource,
} from "../hooks";
import { PageContainer } from "../layout/PageContainer";
import {
    insightApi,
    type InsightDataSourceCreate,
    type InsightDataSourceFetchConfig,
    type InsightDataSourceGroupRead,
    type InsightDataSourceImportResponse,
    type InsightDataSourceRead,
    type InsightDataSourceBatchCreateRequest,
    type InsightDataSourceBatchCreateResponse,
    type InsightCompanyListItem,
    type InsightSchedulerStatusRead,
    type InsightSearchDiscoveryResponse,
    type InsightTaskRead,
} from "../api";

const sourceTypeOptions = [
    { value: "baidu_news", label: "百度资讯" },
    { value: "bocha_search", label: "博查搜索" },
    { value: "official_site", label: "官网" },
    { value: "web_page", label: "通用网页" },
    { value: "wechat_public_account", label: "公众号公开文章" },
    { value: "ecommerce_search", label: "电商公开搜索" },
    { value: "government_policy", label: "政府政策" },
    { value: "finance_news", label: "财经资讯" },
    { value: "patent_search", label: "专利公开检索" },
    { value: "industry_media", label: "行业媒体" },
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

const batchSourceTypeOptions = sourceTypeOptions.filter((item) => item.value !== "official_site" && item.value !== "web_page");

const defaultLlmFilterPrompt = "保留与食品饮料、功能糖、淀粉糖、植物蛋白、配料原料、竞对、客户新品、政策法规、专利技术、研发营销机会相关的公开信息；过滤验证码、图片搜索、百科泛信息、无业务价值页面和明显跨行业噪声。";

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
type DataSourceViewMode = "plan" | "company" | "detail";
interface DataSourcePlanGroup {
    group_key: string;
    source_type: string;
    source_type_label: string;
    company_count: number;
    unlinked_count: number;
    total_count: number;
    enabled_count: number;
    disabled_count: number;
    scheduled_count: number;
    llm_filter_count: number;
    auto_review_count: number;
    failed_count: number;
    paused_count: number;
    latest_success_time?: string | null;
    latest_failure_time?: string | null;
    next_run_time?: string | null;
    visibility_scopes: string[];
    data_source_ids: number[];
    children: DataSourcePlanChild[];
}
interface DataSourcePlanChild {
    key: string;
    label: string;
    company_id: number | null;
    company_name: string;
    total_count: number;
    enabled_count: number;
    scheduled_count: number;
    failed_count: number;
    paused_count: number;
    latest_success_time?: string | null;
    next_run_time?: string | null;
    visibility_scopes: string[];
    data_source_ids: number[];
}
interface DataSourceCompanyGroup {
    group_key: string;
    company_id: number | null;
    company_name: string;
    company_short_name?: string | null;
    sys_company_id?: number | null;
    type_labels: string[];
    total_count: number;
    enabled_count: number;
    disabled_count: number;
    scheduled_count: number;
    llm_filter_count: number;
    auto_review_count: number;
    failed_count: number;
    paused_count: number;
    latest_success_time?: string | null;
    latest_failure_time?: string | null;
    next_run_time?: string | null;
    visibility_scopes: string[];
    data_source_ids: number[];
}
type DataSourceBulkActionHandler = (
    action: "enable" | "disable" | "set_schedule" | "set_visibility" | "patch_config" | "execute",
    options?: Partial<InsightDataSourceFetchConfig> & {
        fetch_frequency?: string;
        schedule_enabled?: boolean;
        visibility_scope?: string;
        execute_crawl_top_n?: number;
    },
    targetIds?: number[],
) => void;

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
    const [searchParams] = useSearchParams();
    const [keyword, setKeyword] = useState("");
    const [sourceType, setSourceType] = useState("");
    const [status, setStatus] = useState("");
    const [editingSource, setEditingSource] = useState<InsightDataSourceRead | null>(null);
    const [formOpen, setFormOpen] = useState(false);
    const [batchOpen, setBatchOpen] = useState(false);
    const [batchResult, setBatchResult] = useState<InsightDataSourceBatchCreateResponse | null>(null);
    const [importOpen, setImportOpen] = useState(false);
    const [importResult, setImportResult] = useState<InsightDataSourceImportResponse | null>(null);
    const [executeKeyword, setExecuteKeyword] = useState("");
    const [selectedSourceId, setSelectedSourceId] = useState<number | null>(null);
    const [selectedBulkSourceIds, setSelectedBulkSourceIds] = useState<number[]>([]);
    const [executingSourceId, setExecutingSourceId] = useState<number | null>(null);
    const [accessSource, setAccessSource] = useState<InsightDataSourceRead | null>(null);
    const [bulkAccessOpen, setBulkAccessOpen] = useState(false);
    const [groupConfigTarget, setGroupConfigTarget] = useState<{ name: string; ids: number[] } | null>(null);
    const [expandedPlanKey, setExpandedPlanKey] = useState<string | null>(null);
    const [viewMode, setViewMode] = useState<DataSourceViewMode>("plan");
    const [page, setPage] = useState(1);
    const [utilityPanel, setUtilityPanel] = useState<UtilityPanel>(null);
    const dataSourcesQuery = useInsightDataSources({
        page: 1,
        size: 100,
        keyword: keyword || undefined,
        source_type: sourceType || undefined,
        status: status || undefined,
    });
    const dataSourceGroupsQuery = useInsightDataSourceGroups({
        keyword: keyword || undefined,
        source_type: sourceType || undefined,
        status: status || undefined,
    });
    const createMutation = useInsightCreateDataSource();
    const batchCreateMutation = useInsightBatchCreateDataSources();
    const updateMutation = useInsightUpdateDataSource();
    const deleteMutation = useInsightDeleteDataSource();
    const executeMutation = useInsightExecuteDataSource();
    const importMutation = useInsightImportDataSources();
    const importPreviewMutation = useInsightPreviewImportDataSources();
    const bulkMutation = useInsightBulkActionDataSources();
    const retryScheduleMutation = useInsightRetryDataSourceSchedule();
    const schedulerStatusQuery = useInsightSchedulerStatus();
    const runSchedulerOnceMutation = useInsightRunSchedulerOnce();
    const startSchedulerMutation = useInsightStartScheduler();
    const stopSchedulerMutation = useInsightStopScheduler();
    const companiesQuery = useInsightCompanies({ page: 1, size: 500 });
    const dataSources = dataSourcesQuery.data?.items ?? [];
    const dataSourceGroups = dataSourceGroupsQuery.data ?? [];
    const sourceIdParam = Number(searchParams.get("data_source_id"));
    const isDataSourcesLoading = dataSourcesQuery.isLoading && !dataSourcesQuery.data;
    const isGroupsLoading = dataSourceGroupsQuery.isLoading && !dataSourceGroupsQuery.data;
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
    const dueScheduledCount = dataSources.filter((item) => item.schedule_enabled && isDue(item.next_run_time)).length;
    const lastResult = executeMutation.data;
    const lastSearchResults = lastResult?.search_results?.length ? lastResult.search_results : lastResult?.search_result ? [lastResult.search_result] : [];
    const lastExecutionErrors = lastResult?.execution_errors ?? [];
    const lastHitCount = lastSearchResults.reduce((sum, item) => sum + item.hits.length, 0);
    const lastCrawledCount = lastSearchResults.reduce((sum, item) => sum + item.crawled_results.length, 0);
    const lastCandidateCount = lastSearchResults.reduce((sum, item) => sum + item.candidates.length, 0);
    const planGroups = useMemo(() => aggregatePlanGroups(dataSourceGroups), [dataSourceGroups]);
    const companyGroups = useMemo(() => aggregateCompanyGroups(dataSourceGroups), [dataSourceGroups]);
    const totalPages = Math.max(1, Math.ceil(dataSources.length / pageSize));
    const planPageSize = 10;
    const groupPageSize = 12;
    const planTotalPages = Math.max(1, Math.ceil(planGroups.length / planPageSize));
    const groupTotalPages = Math.max(1, Math.ceil(companyGroups.length / groupPageSize));
    const activeTotalPages = viewMode === "plan" ? planTotalPages : viewMode === "company" ? groupTotalPages : totalPages;
    const currentPage = Math.min(page, activeTotalPages);
    const pagedDataSources = dataSources.slice((currentPage - 1) * pageSize, currentPage * pageSize);
    const pagedPlanGroups = planGroups.slice((currentPage - 1) * planPageSize, currentPage * planPageSize);
    const pagedCompanyGroups = companyGroups.slice((currentPage - 1) * groupPageSize, currentPage * groupPageSize);
    const selectedBulkCount = selectedBulkSourceIds.length;
    const groupedSourceCount = dataSourceGroups.reduce((sum, item) => sum + item.total_count, 0);
    const groupedEnabledCount = dataSourceGroups.reduce((sum, item) => sum + item.enabled_count, 0);
    const groupedScheduledCount = dataSourceGroups.reduce((sum, item) => sum + item.scheduled_count, 0);
    const groupedLlmCount = dataSourceGroups.reduce((sum, item) => sum + item.llm_filter_count, 0);

    useEffect(() => {
        if (!Number.isFinite(sourceIdParam) || sourceIdParam <= 0 || dataSources.length === 0) return;
        const source = dataSources.find((item) => item.id === sourceIdParam);
        if (!source || selectedSourceId === source.id) return;
        setSelectedSourceId(source.id);
        setUtilityPanel("logs");
    }, [dataSources, selectedSourceId, sourceIdParam]);

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

    const toggleBulkSource = (sourceId: number) => {
        setSelectedBulkSourceIds((current) => toggleId(current, sourceId));
    };

    const selectCurrentPageSources = () => {
        if (viewMode === "plan") {
            setSelectedBulkSourceIds(uniqueIds(pagedPlanGroups.flatMap((item) => item.data_source_ids)));
            return;
        }
        if (viewMode === "company") {
            setSelectedBulkSourceIds(uniqueIds(pagedCompanyGroups.flatMap((item) => item.data_source_ids)));
            return;
        }
        setSelectedBulkSourceIds(pagedDataSources.map((item) => item.id));
    };

    const selectGroupSources = (group: DataSourceCompanyGroup | DataSourcePlanGroup) => {
        setSelectedBulkSourceIds(group.data_source_ids);
    };

    const clearBulkSources = () => setSelectedBulkSourceIds([]);

    const handleBulkAction = (
        action: "enable" | "disable" | "set_schedule" | "set_visibility" | "patch_config" | "execute",
        options: Partial<InsightDataSourceFetchConfig> & {
            fetch_frequency?: string;
            schedule_enabled?: boolean;
            visibility_scope?: string;
            execute_crawl_top_n?: number;
        } = {},
        targetIds: number[] = [],
    ) => {
        const dataSourceIds = uniqueIds(targetIds.length > 0 ? targetIds : selectedBulkSourceIds);
        if (dataSourceIds.length === 0) return;
        const cleanOptions = options;
        const fetchConfigPatch: Record<string, unknown> = {};
        if (Object.prototype.hasOwnProperty.call(cleanOptions, "enable_llm_filter")) {
            fetchConfigPatch.enable_llm_filter = cleanOptions.enable_llm_filter;
            if (cleanOptions.enable_llm_filter) {
                fetchConfigPatch.filter_prompt = cleanOptions.filter_prompt || defaultLlmFilterPrompt;
            }
        }
        if (Object.prototype.hasOwnProperty.call(cleanOptions, "crawl_top_n")) {
            fetchConfigPatch.crawl_top_n = cleanOptions.crawl_top_n;
            fetchConfigPatch.create_candidate_from_hits = Number(cleanOptions.crawl_top_n ?? 0) === 0;
        }
        for (const key of ["auto_review_mode", "auto_review_min_confidence", "auto_add_to_report_pool", "auto_report_folder"] as const) {
            if (Object.prototype.hasOwnProperty.call(cleanOptions, key)) {
                fetchConfigPatch[key] = cleanOptions[key];
            }
        }
        bulkMutation.mutate(
            {
                data_source_ids: dataSourceIds,
                action,
                fetch_frequency: cleanOptions.fetch_frequency,
                schedule_enabled: cleanOptions.schedule_enabled,
                visibility_scope: cleanOptions.visibility_scope,
                execute_crawl_top_n: cleanOptions.execute_crawl_top_n,
                fetch_config_patch: Object.keys(fetchConfigPatch).length > 0 ? fetchConfigPatch : undefined,
            },
            {
                onSuccess: (result) => {
                    toast.success(`批量操作完成：成功 ${result.success_count} 个，失败 ${result.failed_count} 个`);
                    setSelectedBulkSourceIds([]);
                },
                onError: (error) => toast.error(getErrorMessage(error)),
            },
        );
    };

    return (
        <PageContainer className="insight-page-locked flex min-h-0 flex-col gap-4">
            <div className="insight-page-heading">
                <div className="insight-actions">
                    <Button variant="outline" className="h-10 rounded-xl bg-white" onClick={() => setImportOpen(true)}>
                        <FileInput className="size-4" />
                        Excel/Word 导入
                    </Button>
                    <Button className="h-10 rounded-xl px-5" onClick={() => {
                        setBatchResult(null);
                        setBatchOpen(true);
                    }}>
                        <Layers3 className="size-4" />
                        批量配置采集计划
                    </Button>
                    <Button variant="outline" className="h-10 rounded-xl bg-white" onClick={handleRunDue} disabled={runSchedulerOnceMutation.isPending}>
                        {runSchedulerOnceMutation.isPending ? <Loader2 className="size-4 animate-spin" /> : <CalendarClock className="size-4" />}
                        立即扫描到期任务
                    </Button>
                    <Button variant="outline" className="h-10 rounded-xl bg-white px-5" onClick={handleCreate}>
                        + 新增数据源
                    </Button>
                </div>
            </div>

            <div className="grid grid-cols-2 gap-2 md:hidden">
                <MobileSourceStat title="采集计划" value={String(planGroups.length)} loading={isGroupsLoading} />
                <MobileSourceStat title="数据源" value={String(groupedSourceCount || dataSourcesQuery.data?.total || 0)} loading={isGroupsLoading} />
                <MobileSourceStat title="已启用" value={String(groupedEnabledCount)} loading={isGroupsLoading} />
                <MobileSourceStat title="周期/LLM" value={`${groupedScheduledCount} / ${groupedLlmCount}`} loading={isGroupsLoading} />
            </div>

            <div className="hidden md:block">
                <div className="insight-metric-strip">
                    <StatCard title="采集计划组" value={String(planGroups.length)} compare={`企业组 ${companyGroups.length}`} loading={isGroupsLoading} icon={<Database className="size-7" />} />
                    <StatCard title="数据源总数" value={String(groupedSourceCount || dataSourcesQuery.data?.total || 0)} compare="当前筛选" loading={isGroupsLoading} tone="cyan" icon={<CheckCircle2 className="size-7" />} />
                    <StatCard title="已启用 / 周期" value={`${groupedEnabledCount} / ${groupedScheduledCount}`} compare={`明细到期 ${dueScheduledCount}`} loading={isGroupsLoading} icon={<ClipboardList className="size-7" />} />
                    <StatCard title="LLM 筛选" value={String(groupedLlmCount)} compare="按真实数据源统计" loading={isGroupsLoading} tone="cyan" icon={<Settings2 className="size-7" />} />
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

                <div className="mb-3 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-100 bg-slate-50/80 p-2">
                    <div className="flex rounded-lg bg-white p-1 shadow-sm ring-1 ring-slate-200">
                        <button
                            type="button"
                            className={cn("h-8 rounded-md px-3 text-sm font-black transition", viewMode === "plan" ? "bg-blue-600 text-white" : "text-slate-600 hover:bg-slate-100")}
                            onClick={() => {
                                setViewMode("plan");
                                setPage(1);
                                setSelectedBulkSourceIds([]);
                            }}
                        >
                            采集计划
                        </button>
                        <button
                            type="button"
                            className={cn("h-8 rounded-md px-3 text-sm font-black transition", viewMode === "company" ? "bg-blue-600 text-white" : "text-slate-600 hover:bg-slate-100")}
                            onClick={() => {
                                setViewMode("company");
                                setPage(1);
                                setSelectedBulkSourceIds([]);
                            }}
                        >
                            聚合管理
                        </button>
                        <button
                            type="button"
                            className={cn("h-8 rounded-md px-3 text-sm font-black transition", viewMode === "detail" ? "bg-blue-600 text-white" : "text-slate-600 hover:bg-slate-100")}
                            onClick={() => {
                                setViewMode("detail");
                                setPage(1);
                                setSelectedBulkSourceIds([]);
                            }}
                        >
                            明细列表
                        </button>
                    </div>
                    <div className="text-xs font-bold text-slate-500">
                        默认按采集计划折叠；企业分组和明细列表用于下钻排障，组级按钮会直接作用到组内真实数据源。
                    </div>
                </div>

                <DataSourceBulkActionBar
                    selectedCount={selectedBulkCount}
                    pending={bulkMutation.isPending}
                    onSelectPage={selectCurrentPageSources}
                    onClear={clearBulkSources}
                    onOpenBulkAccess={() => setBulkAccessOpen(true)}
                    onBulkAction={handleBulkAction}
                />

                {viewMode === "plan" ? (
                    <div className="min-h-0 flex-1 overflow-y-auto pr-1">
                        <DataSourcePlanGroupList
                            groups={pagedPlanGroups}
                            loading={isGroupsLoading}
                            selectedIds={selectedBulkSourceIds}
                            pending={bulkMutation.isPending}
                            onSelectGroup={selectGroupSources}
                            onOpenBulkAccess={(ids) => {
                                setSelectedBulkSourceIds(ids);
                                setBulkAccessOpen(true);
                            }}
                            onOpenGroupConfig={(group) => setGroupConfigTarget({ name: group.source_type_label, ids: group.data_source_ids })}
                            expandedKey={expandedPlanKey}
                            onToggleExpand={(group) => setExpandedPlanKey((current) => current === group.group_key ? null : group.group_key)}
                            onOpenDetail={(group) => {
                                setSourceType(group.source_type);
                                setViewMode("detail");
                                setPage(1);
                                setSelectedBulkSourceIds([]);
                            }}
                            onBulkAction={handleBulkAction}
                        />
                    </div>
                ) : null}

                {viewMode === "company" ? (
                    <div className="min-h-0 flex-1 overflow-y-auto pr-1">
                        <DataSourceGroupList
                            groups={pagedCompanyGroups}
                            loading={isGroupsLoading}
                            selectedIds={selectedBulkSourceIds}
                            pending={bulkMutation.isPending}
                            onSelectGroup={selectGroupSources}
                            onOpenBulkAccess={(ids) => {
                                setSelectedBulkSourceIds(ids);
                                setBulkAccessOpen(true);
                            }}
                            onOpenGroupConfig={(group) => setGroupConfigTarget({ name: group.company_short_name || group.company_name || "未关联企业", ids: group.data_source_ids })}
                            onBulkAction={handleBulkAction}
                        />
                    </div>
                ) : null}

                {viewMode === "detail" ? (
                    <>
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
                            bulkSelected={selectedBulkSourceIds.includes(source.id)}
                            onToggleBulk={toggleBulkSource}
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
                            <col className="w-[48px]" />
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
                                <th className="px-4 py-3 font-bold">选</th>
                                <th className="px-4 py-3 font-bold">名称</th>
                                {["所属企业", "类型", "关键词", "周期", "下次执行", "状态"].map((head) => (
                                    <th key={head} className="px-4 py-3 font-bold">{head}</th>
                                ))}
                                <th className="insight-sticky-right px-4 py-3 text-right font-bold">操作</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100">
                            {isDataSourcesLoading ? (
                                <tr>
                                    <td colSpan={9} className="px-4 py-10 text-center text-sm font-semibold text-slate-500">
                                        正在读取数据源配置...
                                    </td>
                                </tr>
                            ) : null}
                            {pagedDataSources.map((source) => (
                                <DataSourceRow
                                    key={source.id}
                                    source={source}
                                    selected={selectedSource?.id === source.id}
                                    bulkSelected={selectedBulkSourceIds.includes(source.id)}
                                    onToggleBulk={toggleBulkSource}
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
                                    <td colSpan={9} className="px-4 py-10 text-center text-sm font-semibold text-slate-500">
                                        暂无数据源。建议先在企业档案中新增观察企业，再为企业配置百度资讯、博查搜索或官网数据源。
                                    </td>
                                </tr>
                            ) : null}
                        </tbody>
                    </table>
                </div>
                    </>
                ) : null}

                <div className="mt-3 flex flex-wrap items-center justify-between gap-3 text-sm font-semibold text-slate-500">
                    <span>
                        {viewMode === "plan"
                            ? `第 ${currentPage} / ${planTotalPages} 页，每页 ${planPageSize} 个采集计划，计划组 ${planGroups.length} 个，覆盖 ${groupedSourceCount} 个数据源`
                            : viewMode === "company"
                            ? `第 ${currentPage} / ${groupTotalPages} 页，每页 ${groupPageSize} 家企业，企业配置组 ${companyGroups.length} 个，覆盖 ${groupedSourceCount} 个数据源`
                            : `第 ${currentPage} / ${totalPages} 页，每页 ${pageSize} 条，本次读取 ${dataSources.length} 条，筛选总数 ${dataSourcesQuery.data?.total ?? dataSources.length} 条`}
                    </span>
                    <div className="insight-action-cluster">
                        <Button variant="outline" className="h-9 rounded-lg bg-white" disabled={currentPage <= 1} onClick={() => setPage((value) => Math.max(1, value - 1))}>
                            上一页
                        </Button>
                        <Button variant="outline" className="h-9 rounded-lg bg-white" disabled={currentPage >= activeTotalPages} onClick={() => setPage((value) => Math.min(activeTotalPages, value + 1))}>
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
                    result={importResult}
                    onClose={() => {
                        setImportOpen(false);
                        setImportResult(null);
                    }}
                    onPreview={(formData) => {
                        setImportResult(null);
                        importPreviewMutation.mutate(formData, {
                            onSuccess: (result) => {
                                setImportResult(result);
                                toast.success(`预览完成：将新增 ${result.created_count} 个，更新 ${result.updated_count} 个，失败 ${result.failed_count} 个`);
                            },
                            onError: (error) => toast.error(getErrorMessage(error)),
                        });
                    }}
                    onImport={(formData) => {
                        setImportResult(null);
                        importMutation.mutate(formData, {
                            onSuccess: (result) => {
                                setImportResult(result);
                                void dataSourcesQuery.refetch();
                                toast.success(`导入完成：新增 ${result.created_count} 个，更新 ${result.updated_count} 个，失败 ${result.failed_count} 个`);
                            },
                            onError: (error) => toast.error(getErrorMessage(error)),
                        });
                    }}
                    pending={importMutation.isPending || importPreviewMutation.isPending}
                    importing={importMutation.isPending}
                    previewing={importPreviewMutation.isPending}
                />
            ) : null}

            {batchOpen ? (
                <BatchCreateDialog
                    companies={companiesQuery.data?.items ?? []}
                    result={batchResult}
                    pending={batchCreateMutation.isPending}
                    onClose={() => {
                        setBatchOpen(false);
                        setBatchResult(null);
                    }}
                    onSubmit={(payload) => {
                        setBatchResult(null);
                        batchCreateMutation.mutate(payload, {
                            onSuccess: (result) => {
                                setBatchResult(result);
                                toast.success(`批量配置完成：新增 ${result.created_count} 个，更新 ${result.updated_count} 个，跳过 ${result.skipped_count} 个，失败 ${result.failed_count} 个`);
                            },
                            onError: (error) => toast.error(getErrorMessage(error)),
                        });
                    }}
                />
            ) : null}

            {groupConfigTarget ? (
                <GroupConfigDialog
                    targetName={groupConfigTarget.name}
                    targetCount={groupConfigTarget.ids.length}
                    pending={bulkMutation.isPending}
                    onClose={() => setGroupConfigTarget(null)}
                    onSubmit={(options) => {
                        handleBulkAction("patch_config", options, groupConfigTarget.ids);
                        setGroupConfigTarget(null);
                    }}
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
            <AccessRuleDialog
                open={bulkAccessOpen}
                onOpenChange={setBulkAccessOpen}
                targetType="data_source"
                targetId={selectedBulkSourceIds[0] ?? null}
                targetIds={selectedBulkSourceIds}
                targetName={`已选择 ${selectedBulkSourceIds.length} 个数据源`}
            />
        </PageContainer>
    );
}

function DataSourceGroupList({
    groups,
    loading,
    selectedIds,
    pending,
    onSelectGroup,
    onOpenBulkAccess,
    onOpenGroupConfig,
    onBulkAction,
}: {
    groups: DataSourceCompanyGroup[];
    loading: boolean;
    selectedIds: number[];
    pending: boolean;
    onSelectGroup: (group: DataSourceCompanyGroup) => void;
    onOpenBulkAccess: (ids: number[]) => void;
    onOpenGroupConfig: (group: DataSourceCompanyGroup) => void;
    onBulkAction: DataSourceBulkActionHandler;
}) {
    if (loading) {
        return (
            <div className="rounded-xl border border-slate-200 bg-white px-4 py-10 text-center text-sm font-semibold text-slate-500">
                正在按企业和类型聚合数据源...
            </div>
        );
    }
    if (groups.length === 0) {
        return (
            <div className="rounded-xl border border-dashed border-slate-200 bg-white px-4 py-10 text-center text-sm font-semibold text-slate-500">
                当前筛选下没有可管理的数据源组。
            </div>
        );
    }
    return (
        <div className="grid gap-3">
            {groups.map((group) => {
                const isSelected = group.data_source_ids.length > 0 && group.data_source_ids.every((id: number) => selectedIds.includes(id));
                return (
                    <div key={group.group_key} className={cn("rounded-xl border bg-white p-4 shadow-sm transition", isSelected ? "border-blue-300 ring-2 ring-blue-100" : "border-slate-200")}>
                        <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
                            <div className="min-w-0">
                                <div className="flex flex-wrap items-center gap-2">
                                    <button
                                        type="button"
                                        className="text-left text-lg font-black text-slate-950 hover:text-blue-700"
                                        onClick={() => onSelectGroup(group)}
                                        title="选择本组全部数据源"
                                    >
                                        {group.company_short_name || group.company_name || "未关联企业"}
                                    </button>
                                    {group.type_labels.slice(0, 5).map((label) => (
                                        <DemoTag key={label} tone="blue">{label}</DemoTag>
                                    ))}
                                    {group.type_labels.length > 5 ? <DemoTag tone="slate">+{group.type_labels.length - 5} 类</DemoTag> : null}
                                    {group.failed_count > 0 || group.paused_count > 0 ? <DemoTag tone="red">需处理 {group.failed_count + group.paused_count}</DemoTag> : <DemoTag tone="cyan">运行正常</DemoTag>}
                                </div>
                                <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs font-bold text-slate-500">
                                    <span>数据源 {group.total_count}</span>
                                    <span>启用 {group.enabled_count}</span>
                                    <span>周期 {group.scheduled_count}</span>
                                    <span>LLM {group.llm_filter_count}</span>
                                    <span>自动审核 {group.auto_review_count}</span>
                                    <span>权限：{formatVisibilityScopes(group.visibility_scopes)}</span>
                                </div>
                                <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs font-semibold text-slate-400">
                                    <span>最近成功：{formatDateTime(group.latest_success_time)}</span>
                                    <span>下次执行：{formatDateTime(group.next_run_time)}</span>
                                    {group.latest_failure_time ? <span>最近失败：{formatDateTime(group.latest_failure_time)}</span> : null}
                                </div>
                            </div>
                            <div className="flex flex-wrap items-center gap-2 xl:justify-end">
                                <Button type="button" variant="outline" className="h-9 rounded-lg bg-white" onClick={() => onSelectGroup(group)}>
                                    选择本组
                                </Button>
                                <Button type="button" variant="outline" className="h-9 rounded-lg bg-white" disabled={pending || group.data_source_ids.length === 0} onClick={() => onOpenGroupConfig(group)}>
                                    配置
                                </Button>
                                <Button
                                    type="button"
                                    variant="outline"
                                    className="h-9 rounded-lg bg-white"
                                    disabled={pending || group.data_source_ids.length === 0}
                                    onClick={() => onBulkAction("enable", {}, group.data_source_ids)}
                                >
                                    启用
                                </Button>
                                <Button
                                    type="button"
                                    variant="outline"
                                    className="h-9 rounded-lg bg-white"
                                    disabled={pending || group.data_source_ids.length === 0}
                                    onClick={() => onBulkAction("set_schedule", { fetch_frequency: "daily", schedule_enabled: true }, group.data_source_ids)}
                                >
                                    每日周期
                                </Button>
                                <Button
                                    type="button"
                                    variant="outline"
                                    className="h-9 rounded-lg bg-white"
                                    disabled={pending || group.data_source_ids.length === 0}
                                    onClick={() => onOpenBulkAccess(group.data_source_ids)}
                                >
                                    权限
                                </Button>
                                <Button
                                    type="button"
                                    variant="outline"
                                    className="h-9 rounded-lg bg-white text-blue-700"
                                    disabled={pending || group.data_source_ids.length === 0}
                                    onClick={() => onBulkAction("execute", { execute_crawl_top_n: 0 }, group.data_source_ids)}
                                >
                                    轻量执行
                                </Button>
                            </div>
                        </div>
                    </div>
                );
            })}
        </div>
    );
}

function DataSourcePlanGroupList({
    groups,
    loading,
    selectedIds,
    pending,
    onSelectGroup,
    onOpenBulkAccess,
    onOpenGroupConfig,
    expandedKey,
    onToggleExpand,
    onOpenDetail,
    onBulkAction,
}: {
    groups: DataSourcePlanGroup[];
    loading: boolean;
    selectedIds: number[];
    pending: boolean;
    onSelectGroup: (group: DataSourcePlanGroup) => void;
    onOpenBulkAccess: (ids: number[]) => void;
    onOpenGroupConfig: (group: DataSourcePlanGroup) => void;
    expandedKey: string | null;
    onToggleExpand: (group: DataSourcePlanGroup) => void;
    onOpenDetail: (group: DataSourcePlanGroup) => void;
    onBulkAction: DataSourceBulkActionHandler;
}) {
    if (loading) {
        return (
            <div className="rounded-xl border border-slate-200 bg-white px-4 py-10 text-center text-sm font-semibold text-slate-500">
                正在按采集计划聚合数据源...
            </div>
        );
    }
    if (groups.length === 0) {
        return (
            <div className="rounded-xl border border-dashed border-slate-200 bg-white px-4 py-10 text-center text-sm font-semibold text-slate-500">
                当前筛选下没有可管理的采集计划。
            </div>
        );
    }
    return (
        <div className="grid gap-3">
            {groups.map((group) => {
                const isSelected = group.data_source_ids.length > 0 && group.data_source_ids.every((id) => selectedIds.includes(id));
                const isExpanded = expandedKey === group.group_key;
                const issueCount = group.failed_count + group.paused_count;
                return (
                    <div key={group.group_key} className={cn("rounded-xl border bg-white p-4 shadow-sm transition", isSelected ? "border-blue-300 ring-2 ring-blue-100" : "border-slate-200")}>
                        <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
                            <div className="min-w-0">
                                <div className="flex flex-wrap items-center gap-2">
                                    <button type="button" className="text-left text-lg font-black text-slate-950 hover:text-blue-700" onClick={() => onToggleExpand(group)}>
                                        {group.source_type_label}
                                    </button>
                                    <DemoTag tone={issueCount > 0 ? "red" : "cyan"}>{issueCount > 0 ? `需处理 ${issueCount}` : "运行正常"}</DemoTag>
                                </div>
                                <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-sm font-bold text-slate-600">
                                    <span>覆盖 {group.company_count} 家企业</span>
                                    {group.unlinked_count > 0 ? <span>{group.unlinked_count} 个未关联主题源</span> : null}
                                    <span>{group.total_count} 个数据源</span>
                                    <span>{group.scheduled_count} 个周期运行</span>
                                </div>
                                <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs font-semibold text-slate-400">
                                    <span>下次执行：{formatDateTime(group.next_run_time)}</span>
                                    <span>权限：{formatVisibilityScopes(group.visibility_scopes)}</span>
                                </div>
                            </div>
                            <div className="flex flex-wrap items-center gap-2 xl:justify-end">
                                <Button type="button" variant="outline" className="h-9 rounded-lg bg-white" onClick={() => onToggleExpand(group)}>
                                    {isExpanded ? "收起" : "展开"}
                                </Button>
                                <Button type="button" variant="outline" className="h-9 rounded-lg bg-white" disabled={pending || group.data_source_ids.length === 0} onClick={() => onOpenGroupConfig(group)}>
                                    配置
                                </Button>
                                <Button type="button" variant="outline" className="h-9 rounded-lg bg-white" disabled={pending || group.data_source_ids.length === 0} onClick={() => onOpenBulkAccess(group.data_source_ids)}>
                                    权限
                                </Button>
                                <Button type="button" variant="outline" className="h-9 rounded-lg bg-white text-blue-700" disabled={pending || group.data_source_ids.length === 0} onClick={() => onBulkAction("execute", { execute_crawl_top_n: 0 }, group.data_source_ids)}>
                                    轻量执行
                                </Button>
                                <Button type="button" variant="outline" className="h-9 rounded-lg bg-white" onClick={() => onOpenDetail(group)}>
                                    明细
                                </Button>
                            </div>
                        </div>
                        {isExpanded ? (
                            <div className="mt-4 rounded-xl border border-slate-100 bg-slate-50/80 p-2">
                                <div className="mb-2 flex flex-wrap items-center justify-between gap-2 px-2 text-xs font-black text-slate-500">
                                    <span>下钻到企业/主题</span>
                                    <span>{group.children.length} 组</span>
                                </div>
                                <div className="grid gap-2">
                                    {group.children.slice(0, 80).map((child) => {
                                        const childIssueCount = child.failed_count + child.paused_count;
                                        return (
                                            <div key={child.key} className="flex flex-col gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 md:flex-row md:items-center md:justify-between">
                                                <div className="min-w-0">
                                                    <div className="flex flex-wrap items-center gap-2">
                                                        <div className="truncate text-sm font-black text-slate-800">{child.label}</div>
                                                        <DemoTag tone={childIssueCount > 0 ? "red" : "cyan"}>{childIssueCount > 0 ? `需处理 ${childIssueCount}` : "正常"}</DemoTag>
                                                    </div>
                                                    <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs font-semibold text-slate-500">
                                                        <span>{child.total_count} 个数据源</span>
                                                        <span>启用 {child.enabled_count}</span>
                                                        <span>周期 {child.scheduled_count}</span>
                                                        <span>下次 {formatDateTime(child.next_run_time)}</span>
                                                        <span>权限 {formatVisibilityScopes(child.visibility_scopes)}</span>
                                                    </div>
                                                </div>
                                                <div className="flex flex-wrap items-center gap-2 md:justify-end">
                                                    <Button type="button" variant="outline" className="h-8 rounded-lg bg-white px-3 text-xs" disabled={pending} onClick={() => onSelectGroup({ ...group, data_source_ids: child.data_source_ids })}>
                                                        选择
                                                    </Button>
                                                    <Button type="button" variant="outline" className="h-8 rounded-lg bg-white px-3 text-xs" disabled={pending} onClick={() => onOpenBulkAccess(child.data_source_ids)}>
                                                        权限
                                                    </Button>
                                                    <Button type="button" variant="outline" className="h-8 rounded-lg bg-white px-3 text-xs text-blue-700" disabled={pending} onClick={() => onBulkAction("execute", { execute_crawl_top_n: 0 }, child.data_source_ids)}>
                                                        执行
                                                    </Button>
                                                </div>
                                            </div>
                                        );
                                    })}
                                    {group.children.length > 80 ? (
                                        <div className="rounded-lg border border-slate-200 bg-white px-3 py-3 text-center text-xs font-semibold text-slate-500">
                                            还有 {group.children.length - 80} 组未显示，可点“明细”按该采集计划查看完整底层数据源。
                                        </div>
                                    ) : null}
                                </div>
                            </div>
                        ) : null}
                    </div>
                );
            })}
        </div>
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

function DataSourceBulkActionBar({
    selectedCount,
    pending,
    onSelectPage,
    onClear,
    onOpenBulkAccess,
    onBulkAction,
}: {
    selectedCount: number;
    pending: boolean;
    onSelectPage: () => void;
    onClear: () => void;
    onOpenBulkAccess: () => void;
    onBulkAction: (
        action: "enable" | "disable" | "set_schedule" | "set_visibility" | "patch_config" | "execute",
        options?: Partial<InsightDataSourceFetchConfig> & {
            fetch_frequency?: string;
            schedule_enabled?: boolean;
            visibility_scope?: string;
            execute_crawl_top_n?: number;
        },
    ) => void;
}) {
    return (
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-200 bg-slate-50/80 px-3 py-3">
            <div className="flex flex-wrap items-center gap-2 text-sm font-bold text-slate-600">
                <Button type="button" variant="outline" className="h-9 rounded-lg bg-white" onClick={onSelectPage}>
                    选择本页
                </Button>
                <Button type="button" variant="ghost" className="h-9 rounded-lg text-slate-600" disabled={selectedCount === 0} onClick={onClear}>
                    清空选择
                </Button>
                <span>已选择 {selectedCount} 个数据源</span>
            </div>
            <div className="insight-action-cluster">
                <Button type="button" className="h-9 rounded-lg" disabled={pending || selectedCount === 0} onClick={() => onBulkAction("enable")}>
                    {pending ? <Loader2 className="size-4 animate-spin" /> : <Power className="size-4" />}
                    批量启用
                </Button>
                <Button type="button" variant="outline" className="h-9 rounded-lg bg-white" disabled={pending || selectedCount === 0} onClick={() => onBulkAction("disable")}>
                    <Power className="size-4" />
                    批量停用
                </Button>
                <Button type="button" variant="outline" className="h-9 rounded-lg bg-white" disabled={pending || selectedCount === 0} onClick={() => onBulkAction("set_schedule", { fetch_frequency: "daily", schedule_enabled: true })}>
                    <CalendarClock className="size-4" />
                    设为每日
                </Button>
                <Button type="button" variant="outline" className="h-9 rounded-lg bg-white" disabled={pending || selectedCount === 0} onClick={() => onBulkAction("patch_config", { enable_llm_filter: true, crawl_top_n: 0 })}>
                    <Settings2 className="size-4" />
                    轻量AI模式
                </Button>
                <Button type="button" variant="outline" className="h-9 rounded-lg bg-white" disabled={pending || selectedCount === 0} onClick={() => onBulkAction("set_visibility", { visibility_scope: "assigned" })}>
                    <ShieldCheck className="size-4" />
                    指定可见
                </Button>
                <Button type="button" variant="outline" className="h-9 rounded-lg bg-white" disabled={pending || selectedCount === 0} onClick={onOpenBulkAccess}>
                    <Users className="size-4" />
                    批量授权
                </Button>
                <Button type="button" variant="outline" className="h-9 rounded-lg bg-white text-blue-700" disabled={pending || selectedCount === 0} onClick={() => onBulkAction("execute", { execute_crawl_top_n: 0 })}>
                    <Play className="size-4" />
                    批量执行
                </Button>
            </div>
        </div>
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
                                        <SearchAiStatus payload={result.task.output_payload ?? {}} />
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
                        <div className="mt-3 space-y-2">
                            {executionErrors.map((item, index) => (
                                <FriendlyErrorBox key={`${item.keyword ?? index}-${index}`} error={item.error} context={item.keyword ? `关键词：${item.keyword}` : "关键词执行"} tone="orange" />
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
                {status?.last_error ? <FriendlyErrorBox error={status.last_error} context="上次调度错误" className="mt-2" /> : null}
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
    const status = normalizeStatus(task.status);
    const checkedCount = getRecordNumber(payload, "checked_count") ?? 0;
    const dueCount = getRecordNumber(payload, "due_count") ?? 0;
    const executedCount = getRecordNumber(payload, "executed_count") ?? 0;
    const failedCount = getRecordNumber(payload, "failed_count") ?? 0;
    return (
        <div className="rounded-lg border border-slate-100 bg-slate-50/80 px-3 py-2 text-xs font-semibold leading-5 text-slate-600">
            <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="font-black text-slate-800">{formatDateTime(task.started_at ?? task.create_time)}</div>
                <DemoTag tone={status === "success" ? "green" : status === "failed" ? "red" : "orange"}>{taskStatusLabel(status)}</DemoTag>
            </div>
            <div>检查 {checkedCount} 个，到期 {dueCount} 个，成功 {executedCount} 个，失败 {failedCount} 个</div>
            {task.error_message ? <FriendlyErrorBox error={task.error_message} context="调度批次错误" className="mt-2" compact /> : null}
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
    bulkSelected,
    onToggleBulk,
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
    bulkSelected: boolean;
    onToggleBulk: (sourceId: number) => void;
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
            <div className="flex w-full items-start gap-3">
                <label className="mt-2 inline-flex size-6 shrink-0 items-center justify-center rounded-lg border border-slate-200 bg-white">
                    <input className="size-4 accent-blue-600" type="checkbox" checked={bulkSelected} onChange={() => onToggleBulk(source.id)} />
                </label>
                <button type="button" className="flex min-w-0 flex-1 items-start gap-3 text-left" onClick={() => onSelect(source)}>
                <div className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-blue-50 text-blue-600">
                    {source.source_type.includes("news") ? <Search className="size-5" /> : <Globe2 className="size-5" />}
                </div>
                <div className="min-w-0 flex-1">
                    <div className="line-clamp-2 text-sm font-black leading-5 text-slate-900">{source.source_name}</div>
                    <div className="mt-1 truncate text-xs font-semibold text-slate-500">{source.base_url || source.source_code}</div>
                </div>
                </button>
            </div>
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
    bulkSelected,
    onToggleBulk,
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
    bulkSelected: boolean;
    onToggleBulk: (sourceId: number) => void;
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
            <td className="px-4 py-4 align-middle">
                <label className="inline-flex size-6 items-center justify-center rounded-lg border border-slate-200 bg-white">
                    <input className="size-4 accent-blue-600" type="checkbox" checked={bulkSelected} onChange={() => onToggleBulk(source.id)} />
                </label>
            </td>
            <td className="px-4 py-4 align-middle">
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

interface GroupConfigState {
    fetchFrequency: string;
    visibilityScope: string;
    enableLlmFilter: boolean;
    crawlTopN: number;
    autoReviewMode: string;
    autoReviewMinConfidence: number;
    autoAddToReportPool: boolean;
    autoReportFolder: string;
}

const defaultGroupConfigState: GroupConfigState = {
    fetchFrequency: "daily",
    visibilityScope: "assigned",
    enableLlmFilter: true,
    crawlTopN: 0,
    autoReviewMode: "high_confidence",
    autoReviewMinConfidence: 0.72,
    autoAddToReportPool: true,
    autoReportFolder: "期初真实运行素材池",
};

function GroupConfigDialog({
    targetName,
    targetCount,
    pending,
    onClose,
    onSubmit,
}: {
    targetName: string;
    targetCount: number;
    pending: boolean;
    onClose: () => void;
    onSubmit: (options: Partial<InsightDataSourceFetchConfig> & { fetch_frequency?: string; schedule_enabled?: boolean; visibility_scope?: string }) => void;
}) {
    const [form, setForm] = useState<GroupConfigState>(defaultGroupConfigState);
    const submit = (event: FormEvent<HTMLFormElement>) => {
        event.preventDefault();
        onSubmit({
            fetch_frequency: form.fetchFrequency,
            schedule_enabled: form.fetchFrequency !== "manual",
            visibility_scope: form.visibilityScope,
            enable_llm_filter: form.enableLlmFilter,
            filter_prompt: form.enableLlmFilter ? defaultLlmFilterPrompt : null,
            crawl_top_n: form.crawlTopN,
            auto_review_mode: form.autoReviewMode,
            auto_review_min_confidence: form.autoReviewMinConfidence,
            auto_add_to_report_pool: form.autoAddToReportPool,
            auto_report_folder: form.autoReportFolder.trim() || null,
        });
    };
    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/30 p-3 backdrop-blur-sm sm:p-4">
            <form onSubmit={submit} className="max-h-[92vh] w-full max-w-2xl overflow-auto rounded-2xl border border-slate-200 bg-white p-4 shadow-2xl sm:p-6">
                <div className="mb-5 flex flex-wrap items-start justify-between gap-4">
                    <div>
                        <h2 className="text-xl font-black text-slate-950 sm:text-2xl">配置采集组</h2>
                        <p className="mt-1 text-sm font-semibold text-slate-500">{targetName}，共 {targetCount} 个底层数据源。</p>
                    </div>
                    <Button type="button" variant="outline" className="rounded-xl bg-white" onClick={onClose}>关闭</Button>
                </div>
                <div className="grid gap-4 sm:grid-cols-2">
                    <InsightSelect label="抓取周期" value={form.fetchFrequency} options={frequencyOptions} onChange={(value) => setForm((old) => ({ ...old, fetchFrequency: value }))} />
                    <InsightSelect
                        label="权限范围"
                        value={form.visibilityScope}
                        options={[
                            { value: "assigned", label: "指定可见" },
                            { value: "dept", label: "部门可见" },
                            { value: "private", label: "仅创建人" },
                            { value: "public", label: "公开" },
                        ]}
                        onChange={(value) => setForm((old) => ({ ...old, visibilityScope: value }))}
                    />
                    <NumberField label="每词抓取上限" value={form.crawlTopN} min={0} max={20} onChange={(value) => setForm((old) => ({ ...old, crawlTopN: value }))} />
                    <InsightSelect label="自动审核" value={form.autoReviewMode} options={autoReviewOptions} onChange={(value) => setForm((old) => ({ ...old, autoReviewMode: value }))} />
                    <NumberField label="审核置信度" value={form.autoReviewMinConfidence} min={0} max={1} step={0.05} onChange={(value) => setForm((old) => ({ ...old, autoReviewMinConfidence: value }))} />
                    <Field label="素材池文件夹" value={form.autoReportFolder} onChange={(value) => setForm((old) => ({ ...old, autoReportFolder: value }))} />
                    <label className="flex items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-bold text-slate-700">
                        <input type="checkbox" checked={form.enableLlmFilter} onChange={(event) => setForm((old) => ({ ...old, enableLlmFilter: event.target.checked }))} />
                        启用 AI 筛选、摘要和标签
                    </label>
                    <label className="flex items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-bold text-slate-700">
                        <input type="checkbox" checked={form.autoAddToReportPool} onChange={(event) => setForm((old) => ({ ...old, autoAddToReportPool: event.target.checked }))} />
                        高置信情报自动加入素材池
                    </label>
                </div>
                <div className="mt-6 insight-actions border-t border-slate-100 pt-5">
                    <Button type="button" variant="outline" className="rounded-xl bg-white" onClick={onClose}>取消</Button>
                    <Button type="submit" className="rounded-xl" disabled={pending || targetCount === 0}>
                        {pending ? <Loader2 className="size-4 animate-spin" /> : <Settings2 className="size-4" />}
                        保存组配置
                    </Button>
                </div>
            </form>
        </div>
    );
}

interface BatchCreateState {
    companyIds: number[];
    sourceTypes: string[];
    companyKeyword: string;
    keywordTemplate: string;
    includeKeywords: string;
    excludeKeywords: string;
    fetchFrequency: string;
    maxResults: number;
    crawlTopN: number;
    enableLlmFilter: boolean;
    filterPrompt: string;
    autoReviewMode: string;
    autoReviewMinConfidence: number;
    autoAddToReportPool: boolean;
    autoReportFolder: string;
    visibilityScope: string;
    updateExisting: boolean;
}

const defaultBatchState: BatchCreateState = {
    companyIds: [],
    sourceTypes: ["baidu_news", "bocha_search"],
    companyKeyword: "",
    keywordTemplate: "",
    includeKeywords: "",
    excludeKeywords: "",
    fetchFrequency: "daily",
    maxResults: 6,
    crawlTopN: 0,
    enableLlmFilter: true,
    filterPrompt: defaultLlmFilterPrompt,
    autoReviewMode: "high_confidence",
    autoReviewMinConfidence: 0.72,
    autoAddToReportPool: true,
    autoReportFolder: "期初真实运行素材池",
    visibilityScope: "assigned",
    updateExisting: true,
};

function BatchCreateDialog({
    companies,
    result,
    pending,
    onClose,
    onSubmit,
}: {
    companies: InsightCompanyListItem[];
    result: InsightDataSourceBatchCreateResponse | null;
    pending: boolean;
    onClose: () => void;
    onSubmit: (payload: InsightDataSourceBatchCreateRequest) => void;
}) {
    const [form, setForm] = useState<BatchCreateState>(defaultBatchState);
    const filteredCompanies = useMemo(() => {
        const keyword = form.companyKeyword.trim().toLowerCase();
        if (!keyword) return companies;
        return companies.filter((company) => {
            const haystack = `${company.name} ${company.short_name ?? ""} ${company.industry ?? ""} ${company.region ?? ""}`.toLowerCase();
            return haystack.includes(keyword);
        });
    }, [companies, form.companyKeyword]);
    const visibleCompanies = filteredCompanies.slice(0, 120);
    const selectedCompanySet = new Set(form.companyIds);
    const selectedTypeSet = new Set(form.sourceTypes);
    const payload = useMemo<InsightDataSourceBatchCreateRequest>(() => ({
        company_ids: form.companyIds,
        source_types: form.sourceTypes,
        keyword_template: form.keywordTemplate.trim() || undefined,
        include_keywords: splitLines(form.includeKeywords),
        exclude_keywords: splitLines(form.excludeKeywords),
        fetch_frequency: form.fetchFrequency,
        max_results: form.maxResults,
        crawl_top_n: form.crawlTopN,
        freshness: "noLimit",
        enable_llm_filter: form.enableLlmFilter,
        filter_prompt: form.filterPrompt.trim() || defaultLlmFilterPrompt,
        auto_review_mode: form.autoReviewMode,
        auto_review_min_confidence: form.autoReviewMinConfidence,
        auto_add_to_report_pool: form.autoAddToReportPool,
        auto_report_folder: form.autoReportFolder.trim() || undefined,
        visibility_scope: form.visibilityScope,
        status: "enabled",
        update_existing: form.updateExisting,
    }), [form]);
    const plannedCount = form.companyIds.length * form.sourceTypes.length;

    const toggleCompany = (companyId: number) => {
        setForm((old) => ({ ...old, companyIds: toggleId(old.companyIds, companyId) }));
    };
    const selectVisibleCompanies = () => {
        setForm((old) => ({ ...old, companyIds: uniqueIds([...old.companyIds, ...visibleCompanies.map((company) => company.id)]) }));
    };
    const clearCompanies = () => {
        setForm((old) => ({ ...old, companyIds: [] }));
    };
    const toggleSourceType = (sourceType: string) => {
        setForm((old) => ({ ...old, sourceTypes: toggleString(old.sourceTypes, sourceType) }));
    };
    const submit = (event: FormEvent<HTMLFormElement>) => {
        event.preventDefault();
        onSubmit(payload);
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/30 p-3 backdrop-blur-sm sm:p-4">
            <form onSubmit={submit} className="max-h-[92vh] w-full max-w-6xl overflow-auto rounded-2xl border border-slate-200 bg-white p-4 shadow-2xl sm:p-6">
                <div className="mb-5 flex flex-wrap items-start justify-between gap-4">
                    <div>
                        <h2 className="text-xl font-black text-slate-950 sm:text-2xl">批量配置采集计划</h2>
                        <p className="mt-1 text-sm font-semibold text-slate-500">一次选择多个企业和多个采集类型，系统自动生成或更新底层数据源，后续按企业组管理。</p>
                    </div>
                    <Button type="button" variant="outline" className="rounded-xl bg-white" onClick={onClose}>关闭</Button>
                </div>

                <div className="grid gap-4 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,0.85fr)]">
                    <div className="rounded-2xl border border-slate-200 bg-slate-50/70 p-4">
                        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
                            <div>
                                <div className="text-sm font-black text-slate-900">选择企业</div>
                                <div className="mt-1 text-xs font-semibold text-slate-500">当前已选 {form.companyIds.length} 家；搜索结果显示前 {visibleCompanies.length} 家。</div>
                            </div>
                            <div className="insight-action-cluster">
                                <Button type="button" variant="outline" className="h-9 rounded-lg bg-white" onClick={selectVisibleCompanies}>选择当前结果</Button>
                                <Button type="button" variant="ghost" className="h-9 rounded-lg text-slate-600" onClick={clearCompanies}>清空</Button>
                            </div>
                        </div>
                        <Input
                            className="h-10 rounded-xl border-slate-200 bg-white"
                            value={form.companyKeyword}
                            placeholder="搜索企业、简称、行业或地区"
                            onChange={(event) => setForm((old) => ({ ...old, companyKeyword: event.target.value }))}
                        />
                        <div className="mt-3 grid max-h-[28rem] gap-2 overflow-y-auto pr-1 sm:grid-cols-2">
                            {visibleCompanies.map((company) => (
                                <button
                                    key={company.id}
                                    type="button"
                                    className={cn(
                                        "rounded-xl border px-3 py-2 text-left transition",
                                        selectedCompanySet.has(company.id) ? "border-blue-300 bg-blue-50 ring-2 ring-blue-100" : "border-slate-200 bg-white hover:border-blue-200",
                                    )}
                                    onClick={() => toggleCompany(company.id)}
                                >
                                    <div className="line-clamp-1 text-sm font-black text-slate-900">{company.short_name || company.name}</div>
                                    <div className="mt-1 line-clamp-1 text-xs font-semibold text-slate-500">{company.name}</div>
                                    <div className="mt-2 flex flex-wrap gap-1">
                                        {company.sys_company_id ? <DemoTag tone="cyan">所属公司 {company.sys_company_id}</DemoTag> : <DemoTag tone="slate">未绑定所属公司</DemoTag>}
                                        {company.company_type ? <DemoTag tone="blue">{company.company_type}</DemoTag> : null}
                                    </div>
                                </button>
                            ))}
                            {visibleCompanies.length === 0 ? (
                                <div className="rounded-xl border border-dashed border-slate-200 bg-white px-4 py-8 text-center text-sm font-semibold text-slate-500 sm:col-span-2">
                                    没有匹配企业，可先到企业档案导入或调整筛选。
                                </div>
                            ) : null}
                        </div>
                    </div>

                    <div className="space-y-4">
                        <div className="rounded-2xl border border-slate-200 bg-white p-4">
                            <div className="text-sm font-black text-slate-900">采集类型</div>
                            <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-1 xl:grid-cols-2">
                                {batchSourceTypeOptions.map((option) => (
                                    <button
                                        key={option.value}
                                        type="button"
                                        className={cn(
                                            "rounded-xl border px-3 py-2 text-left text-sm font-black transition",
                                            selectedTypeSet.has(option.value) ? "border-blue-300 bg-blue-50 text-blue-700 ring-2 ring-blue-100" : "border-slate-200 bg-slate-50 text-slate-700 hover:border-blue-200",
                                        )}
                                        onClick={() => toggleSourceType(option.value)}
                                    >
                                        {option.label}
                                    </button>
                                ))}
                            </div>
                        </div>

                        <div className="rounded-2xl border border-blue-100 bg-blue-50/60 p-4">
                            <div className="mb-3 text-sm font-black text-slate-900">统一策略</div>
                            <div className="grid gap-3 sm:grid-cols-2">
                                <InsightSelect label="抓取周期" value={form.fetchFrequency} options={frequencyOptions} onChange={(value) => setForm((old) => ({ ...old, fetchFrequency: value }))} />
                                <InsightSelect
                                    label="权限范围"
                                    value={form.visibilityScope}
                                    options={[
                                        { value: "assigned", label: "指定可见" },
                                        { value: "dept", label: "部门可见" },
                                        { value: "private", label: "仅创建人" },
                                        { value: "public", label: "公开" },
                                    ]}
                                    onChange={(value) => setForm((old) => ({ ...old, visibilityScope: value }))}
                                />
                                <NumberField label="每词发现数量" value={form.maxResults} min={1} max={20} onChange={(value) => setForm((old) => ({ ...old, maxResults: value }))} />
                                <NumberField label="每词抓取上限" value={form.crawlTopN} min={0} max={20} onChange={(value) => setForm((old) => ({ ...old, crawlTopN: value }))} />
                                <InsightSelect label="自动审核" value={form.autoReviewMode} options={autoReviewOptions} onChange={(value) => setForm((old) => ({ ...old, autoReviewMode: value }))} />
                                <NumberField label="审核置信度" value={form.autoReviewMinConfidence} min={0} max={1} step={0.05} onChange={(value) => setForm((old) => ({ ...old, autoReviewMinConfidence: value }))} />
                            </div>
                            <div className="mt-3 grid gap-3">
                                <Field label="关键词模板" value={form.keywordTemplate} onChange={(value) => setForm((old) => ({ ...old, keywordTemplate: value }))} placeholder="可留空。支持 {企业}、{简称}、{类型}" />
                                <TextArea label="必须包含词" value={form.includeKeywords} onChange={(value) => setForm((old) => ({ ...old, includeKeywords: value }))} placeholder="每行一个，所有类型统一追加" />
                                <TextArea label="排除词" value={form.excludeKeywords} onChange={(value) => setForm((old) => ({ ...old, excludeKeywords: value }))} placeholder="每行一个，例如：招聘、股票、百科" />
                                <label className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm font-bold text-slate-700">
                                    <input type="checkbox" checked={form.enableLlmFilter} onChange={(event) => setForm((old) => ({ ...old, enableLlmFilter: event.target.checked }))} />
                                    启用 AI 筛选、摘要和标签
                                </label>
                                <TextArea label="AI 筛选提示词" value={form.filterPrompt} onChange={(value) => setForm((old) => ({ ...old, filterPrompt: value }))} />
                                <label className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm font-bold text-slate-700">
                                    <input type="checkbox" checked={form.autoAddToReportPool} onChange={(event) => setForm((old) => ({ ...old, autoAddToReportPool: event.target.checked }))} />
                                    高置信情报自动加入报告素材池
                                </label>
                                <Field label="素材池文件夹" value={form.autoReportFolder} onChange={(value) => setForm((old) => ({ ...old, autoReportFolder: value }))} />
                                <label className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm font-bold text-slate-700">
                                    <input type="checkbox" checked={form.updateExisting} onChange={(event) => setForm((old) => ({ ...old, updateExisting: event.target.checked }))} />
                                    已存在同类企业数据源时直接更新配置
                                </label>
                            </div>
                        </div>
                    </div>
                </div>

                <div className="mt-4 rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-semibold text-slate-600">
                    将为 {form.companyIds.length} 家企业 × {form.sourceTypes.length} 种采集类型生成 {plannedCount} 个底层数据源。主页面仍按企业聚合显示，日常不需要逐条管理。
                </div>
                {result ? <BatchCreateResultSummary result={result} /> : null}
                <div className="mt-5 insight-actions border-t border-slate-100 pt-5">
                    <Button type="button" variant="outline" className="rounded-xl bg-white" onClick={onClose}>取消</Button>
                    <Button type="submit" disabled={pending || form.companyIds.length === 0 || form.sourceTypes.length === 0} className="rounded-xl">
                        {pending ? <Loader2 className="size-4 animate-spin" /> : <Layers3 className="size-4" />}
                        保存采集计划
                    </Button>
                </div>
            </form>
        </div>
    );
}

function BatchCreateResultSummary({ result }: { result: InsightDataSourceBatchCreateResponse }) {
    const visibleItems = result.items.slice(0, 80);
    return (
        <div className="mt-4 space-y-3 rounded-xl border border-slate-200 bg-white p-3 text-xs font-semibold leading-5 text-slate-600">
            <div className="grid gap-2 sm:grid-cols-5">
                <ImportMetric label="计划" value={result.requested_count} />
                <ImportMetric label="新增" value={result.created_count} tone="green" />
                <ImportMetric label="更新" value={result.updated_count} tone="blue" />
                <ImportMetric label="跳过" value={result.skipped_count} tone="orange" />
                <ImportMetric label="失败" value={result.failed_count} tone="red" />
            </div>
            <div className="max-h-72 overflow-auto rounded-xl border border-slate-200">
                <table className="w-full min-w-[720px] text-left">
                    <thead className="bg-slate-50 text-[11px] font-black text-slate-500">
                        <tr>
                            <th className="px-3 py-2">企业</th>
                            <th className="px-3 py-2">采集类型</th>
                            <th className="px-3 py-2">数据源</th>
                            <th className="px-3 py-2">状态</th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100 bg-white">
                        {visibleItems.map((item) => (
                            <tr key={`${item.company_id}-${item.source_type}-${item.source_code}`}>
                                <td className="px-3 py-2 font-black text-slate-800">{item.company_name}</td>
                                <td className="px-3 py-2">{sourceTypeLabel(item.source_type)}</td>
                                <td className="px-3 py-2">
                                    <div className="max-w-[260px] truncate font-black text-slate-800">{item.source_name}</div>
                                    <div className="max-w-[260px] truncate text-[11px] text-slate-400">{item.source_code}</div>
                                </td>
                                <td className="px-3 py-2">
                                    <span className={cn("rounded-full px-2 py-0.5 text-[11px] font-black", batchStatusClass(item.status))}>{batchStatusLabel(item.status)}</span>
                                    {item.message ? <div className="mt-1 max-w-[220px] truncate text-[11px] text-slate-400">{item.message}</div> : null}
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
            {result.items.length > visibleItems.length ? <div className="text-slate-400">还有 {result.items.length - visibleItems.length} 条未显示。</div> : null}
        </div>
    );
}

function batchStatusLabel(status: string) {
    const labels: Record<string, string> = {
        created: "新增",
        updated: "更新",
        skipped: "跳过",
        failed: "失败",
    };
    return labels[status] ?? status;
}

function batchStatusClass(status: string) {
    if (status === "created") return "bg-emerald-50 text-emerald-700";
    if (status === "updated") return "bg-blue-50 text-blue-700";
    if (status === "failed") return "bg-red-50 text-red-700";
    return "bg-orange-50 text-orange-700";
}

function ImportDialog({
    onClose,
    onPreview,
    onImport,
    pending,
    previewing,
    importing,
    result,
}: {
    onClose: () => void;
    onPreview: (payload: FormData) => void;
    onImport: (payload: FormData) => void;
    pending: boolean;
    previewing: boolean;
    importing: boolean;
    result: InsightDataSourceImportResponse | null;
}) {
    const [files, setFiles] = useState<File[]>([]);
    const handleDownloadTemplate = async () => {
        try {
            const blob = await insightApi.downloadDataSourceImportTemplate();
            downloadBlob(blob, "insight-data-source-import-template.xlsx");
        } catch (error) {
            toast.error(getErrorMessage(error));
        }
    };
    const buildFormData = () => {
        const formData = new FormData();
        files.forEach((file) => formData.append("files", file));
        return formData;
    };
    const handlePreview = () => {
        onPreview(buildFormData());
    };
    const handleImport = () => {
        const formData = buildFormData();
        onImport(formData);
    };
    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/30 p-3 backdrop-blur-sm sm:p-4">
            <div className="max-h-[92vh] w-full max-w-3xl overflow-auto rounded-2xl border border-slate-200 bg-white p-4 shadow-2xl sm:p-6">
                <div className="mb-4 flex flex-wrap items-center justify-between gap-4">
                    <div>
                        <h2 className="text-xl font-black text-slate-950 sm:text-2xl">Excel/Word 导入数据源</h2>
                        <p className="mt-1 text-sm font-semibold text-slate-500">支持 .xlsx、.xlsm、.docx，会按渠道、课题、关键词生成可执行数据源。</p>
                    </div>
                    <Button variant="outline" className="rounded-xl bg-white" onClick={onClose}>关闭</Button>
                </div>
                <div className="grid gap-3 rounded-xl border border-blue-100 bg-blue-50 p-4 text-sm font-semibold text-slate-700">
                    <div className="font-black text-slate-900">导入后会自动启用 LLM 筛选和高置信自动审核策略。</div>
                    <div>公众号、电商、政府、财经、专利、行业媒体会生成搜索型数据源；公开 URL 会生成网页/官网数据源。</div>
                    <div>登录态、验证码、付费内容不会绕过，会在导入结果中列为暂未自动化渠道。</div>
                </div>
                <div className="mt-4 grid gap-3">
                    <input
                        type="file"
                        multiple
                        accept=".xlsx,.xlsm,.docx"
                        className="rounded-xl border border-slate-200 bg-white p-3 text-sm font-bold text-slate-700"
                        onChange={(event) => setFiles(Array.from(event.target.files ?? []))}
                    />
                    {files.length > 0 ? (
                        <div className="rounded-xl border border-slate-100 bg-slate-50 px-3 py-2 text-xs font-semibold text-slate-600">
                            {files.map((file) => file.name).join("、")}
                        </div>
                    ) : null}
                </div>
                {result ? <ImportResultSummary result={result} /> : null}
                <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
                    <Button variant="outline" className="rounded-xl bg-white" onClick={handleDownloadTemplate}>
                        下载模板
                    </Button>
                    <div className="insight-action-cluster">
                        <Button variant="outline" className="rounded-xl bg-white" disabled={pending || files.length === 0} onClick={handlePreview}>
                            {previewing ? <Loader2 className="size-4 animate-spin" /> : <ClipboardList className="size-4" />}
                            先预览
                        </Button>
                        <Button className="rounded-xl" disabled={pending || files.length === 0} onClick={handleImport}>
                            {importing ? <Loader2 className="size-4 animate-spin" /> : null}
                            确认导入
                        </Button>
                    </div>
                </div>
            </div>
        </div>
    );
}

function ImportResultSummary({ result }: { result: InsightDataSourceImportResponse }) {
    const visibleItems = result.items.slice(0, 80);
    const failedItems = result.items.filter((item) => item.status === "failed");
    const isPreview = result.items.some((item) => item.status.startsWith("will_"));
    return (
        <div className="mt-4 space-y-3 rounded-xl border border-slate-200 bg-white p-3 text-xs font-semibold leading-5 text-slate-600">
            <div className="grid gap-2 sm:grid-cols-5">
                <ImportMetric label="解析" value={result.parsed_count} />
                <ImportMetric label="新增" value={result.created_count} tone="green" />
                <ImportMetric label="更新" value={result.updated_count} tone="blue" />
                <ImportMetric label="失败" value={result.failed_count} tone="red" />
                <ImportMetric label="暂不支持" value={result.unsupported_channels.length} tone="orange" />
            </div>
            <div className="rounded-xl border border-blue-100 bg-blue-50/70 px-3 py-2 text-blue-700">
                {isPreview
                    ? "这是导入前预览，尚未写入数据库。确认明细无误后点击“确认导入”，失败和暂未自动化渠道可先调整文件后重新预览。"
                    : "这是本次导入结果，已成功写入的数据源会出现在主列表；失败和暂未自动化渠道需要按原因调整后重新导入或走人工/授权接入。"}
            </div>
            <div>
                <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                    <span className="font-black text-slate-900">导入明细</span>
                    <span className="text-slate-400">显示 {visibleItems.length} / {result.items.length} 条</span>
                </div>
                {visibleItems.length > 0 ? (
                    <div className="max-h-72 overflow-auto rounded-xl border border-slate-200">
                        <table className="w-full min-w-[720px] text-left">
                            <thead className="bg-slate-50 text-[11px] font-black text-slate-500">
                                <tr>
                                    <th className="px-3 py-2">行号</th>
                                    <th className="px-3 py-2">数据源</th>
                                    <th className="px-3 py-2">类型</th>
                                    <th className="px-3 py-2">企业/课题</th>
                                    <th className="px-3 py-2">关键词</th>
                                    <th className="px-3 py-2">状态</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-100 bg-white">
                                {visibleItems.map((item) => (
                                    <tr key={`${item.row_no}-${item.source_name}-${item.status}`}>
                                        <td className="px-3 py-2 text-slate-400">{item.row_no}</td>
                                        <td className="px-3 py-2 font-black text-slate-800">
                                            <div className="max-w-[220px] truncate">{item.source_name}</div>
                                            {item.source_document ? <div className="mt-0.5 text-[11px] font-semibold text-slate-400">{item.source_document}</div> : null}
                                        </td>
                                        <td className="px-3 py-2">{sourceTypeLabel(item.source_type)}</td>
                                        <td className="px-3 py-2">
                                            <div className="max-w-[180px] truncate">{item.company_name || item.project_name || item.channel_name || "-"}</div>
                                        </td>
                                        <td className="px-3 py-2">
                                            <div className="max-w-[220px] truncate">{item.keywords?.join("、") || "-"}</div>
                                        </td>
                                        <td className="px-3 py-2">
                                            <span className={cn("rounded-full px-2 py-0.5 text-[11px] font-black", importStatusClass(item.status))}>{importStatusLabel(item.status)}</span>
                                            {item.message ? <div className="mt-1 max-w-[220px] truncate text-[11px] text-slate-400">{item.message}</div> : null}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                ) : (
                    <div className="rounded-xl border border-dashed border-slate-200 px-3 py-8 text-center text-slate-500">未解析到可导入数据源。</div>
                )}
            </div>
            {result.unsupported_channels.length > 0 ? <UnsupportedChannelList rows={result.unsupported_channels} /> : null}
            {failedItems.length > 0 ? (
                <div className="rounded-xl border border-red-100 bg-red-50 px-3 py-2 text-red-700">
                    <div className="font-black">失败条目</div>
                    <div className="mt-1 space-y-1">
                        {failedItems.slice(0, 8).map((item) => (
                            <div key={`${item.row_no}-${item.source_name}-failed`}>
                                第 {item.row_no} 行：{item.source_name}，{item.message || "导入失败"}
                            </div>
                        ))}
                    </div>
                </div>
            ) : null}
        </div>
    );
}

function ImportMetric({ label, value, tone = "slate" }: { label: string; value: number; tone?: "slate" | "green" | "blue" | "red" | "orange" }) {
    const toneClass = {
        slate: "text-slate-900",
        green: "text-emerald-700",
        blue: "text-blue-700",
        red: "text-red-700",
        orange: "text-orange-700",
    }[tone];
    return (
        <div className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2">
            <div className="text-[11px] font-black text-slate-500">{label}</div>
            <div className={cn("mt-1 text-lg font-black", toneClass)}>{value}</div>
        </div>
    );
}

function UnsupportedChannelList({ rows }: { rows: Array<Record<string, unknown>> }) {
    return (
        <div className="rounded-xl border border-orange-100 bg-orange-50 px-3 py-2 text-orange-800">
            <div className="font-black">暂未自动化渠道</div>
            <div className="mt-1 space-y-1">
                {rows.slice(0, 12).map((item, index) => (
                    <div key={`${String(item.channel ?? "channel")}-${index}`}>
                        {String(item.channel ?? item.name ?? "未命名渠道")}
                        {item.row_no ? `（第 ${String(item.row_no)} 行）` : ""}：{String(item.reason ?? "需要人工确认接入方式")}
                    </div>
                ))}
                {rows.length > 12 ? <div className="text-orange-600">还有 {rows.length - 12} 条未显示，可查看后端导入结果或分批整理。</div> : null}
            </div>
        </div>
    );
}

function importStatusLabel(status: string) {
    const labels: Record<string, string> = {
        will_create: "将新增",
        will_update: "将更新",
        will_restore: "将恢复",
        created: "新增",
        updated: "更新",
        failed: "失败",
        skipped: "跳过",
    };
    return labels[status] ?? status;
}

function importStatusClass(status: string) {
    if (status === "created" || status === "will_create") return "bg-emerald-50 text-emerald-700";
    if (status === "updated" || status === "will_update" || status === "will_restore") return "bg-blue-50 text-blue-700";
    if (status === "failed") return "bg-red-50 text-red-700";
    return "bg-slate-100 text-slate-500";
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

function downloadBlob(file: Blob, fileName: string) {
    const url = URL.createObjectURL(file);
    const link = document.createElement("a");
    link.href = url;
    link.download = fileName;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
}

function FriendlyErrorBox({
    error,
    context,
    tone = "red",
    compact = false,
    className = "",
}: {
    error?: string | null;
    context?: string;
    tone?: "red" | "orange";
    compact?: boolean;
    className?: string;
}) {
    if (!error) return null;
    const explanation = explainInsightError(error);
    const toneClass =
        tone === "orange"
            ? "border-orange-100 bg-orange-50 text-orange-700"
            : "border-red-100 bg-red-50 text-red-700";
    return (
        <div className={`rounded-lg border px-3 py-2 text-xs font-semibold leading-5 ${toneClass} ${className}`}>
            {context ? <div className="font-black">{context}</div> : null}
            <div className={context ? "mt-1" : ""}>{explanation.summary}</div>
            {!compact ? <div className="mt-1 text-slate-600">{explanation.suggestion}</div> : null}
            {!compact ? (
                <details className="mt-2 rounded-md bg-white/70 px-2 py-1">
                    <summary className="cursor-pointer font-black">技术详情</summary>
                    <div className="mt-1 whitespace-pre-wrap break-words text-slate-500">{error}</div>
                </details>
            ) : null}
        </div>
    );
}

function explainInsightError(error: string): { summary: string; suggestion: string } {
    const text = String(error || "").trim();
    const lowered = text.toLowerCase();
    if (lowered.includes("408") || lowered.includes("request timed out") || lowered.includes("timeout") || text.includes("超时")) {
        return {
            summary: "正文抓取超时，搜索命中已尽量保留为候选。",
            suggestion: "通常是目标站点响应慢或反爬导致。可先使用搜索摘要候选继续审核，必要时降低每词抓取上限或稍后重试。",
        };
    }
    if (text.includes("未启用可用的搜索通道") || text.includes("未配置搜索通道")) {
        return {
            summary: "当前数据源没有可用搜索通道。",
            suggestion: "请检查数据源类型、Bocha/百度通道配置和关键词；公开 URL 可改用官网/网页类数据源。",
        };
    }
    if (text.includes("筛选规则全部过滤") || text.includes("没有命中可进入候选池")) {
        return {
            summary: "搜索结果被包含词、排除词或 AI 筛选过滤，没有生成候选。",
            suggestion: "这不是系统故障。可放宽包含词、降低 AI 最低分，或增加企业简称、品牌名、英文名等关键词。",
        };
    }
    if (lowered.includes("connection") || lowered.includes("connect") || lowered.includes("network") || lowered.includes("dns") || text.includes("网络")) {
        return {
            summary: "外部服务或目标网站连接失败。",
            suggestion: "请检查 Firecrawl/搜索服务是否可用，或稍后重试；连续失败的数据源建议先暂停周期采集。",
        };
    }
    if (lowered.includes("llm") || text.includes("模型") || text.includes("AI")) {
        return {
            summary: "AI 处理阶段失败。",
            suggestion: "请检查模型配置、额度、网络和提示词长度；失败候选可先保留，后续批量重新深化。",
        };
    }
    if (text.includes("任务超过") || text.includes("running") || text.includes("pending")) {
        return {
            summary: "任务执行时间过长，已被清理或需要重试。",
            suggestion: "建议降低抓取上限或启用轻量 AI 模式；如果同一数据源反复超时，先检查关键词是否过宽。",
        };
    }
    return {
        summary: "采集任务执行失败。",
        suggestion: "请展开技术详情查看原始错误；可先重试，若重复失败再调整关键词、通道或数据源配置。",
    };
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
                        const rawError = getRecordText(item, "error");
                        const summary = getRecordText(item, "summary") ?? getRecordText(item, "snippet") ?? rawError;
                        const friendlyError = rawError ? explainInsightError(rawError) : null;
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
                                {friendlyError ? (
                                    <div className="mt-1 rounded-md bg-white/70 px-2 py-1">
                                        <div className="font-black">{friendlyError.summary}</div>
                                        <div className="opacity-80">{friendlyError.suggestion}</div>
                                    </div>
                                ) : summary ? (
                                    <div className="mt-1 line-clamp-2 opacity-80">{summary}</div>
                                ) : null}
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
    const status = normalizeStatus(task.status);
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
                        <DemoTag tone={status === "success" ? "green" : status === "failed" ? "red" : "orange"}>
                            {taskStatusLabel(status)}
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
                <ResultMetric label="已抓取" value={`${crawledIds.length || (task.task_type === "manual_url_crawl" && status === "success" ? 1 : 0)} 条`} />
                <ResultMetric label="候选" value={`${candidateIds.length || (task.output_payload?.candidate_title ? 1 : 0)} 条`} />
            </div>
            <SearchAiStatus payload={payload} />
            {task.error_message ? (
                <FriendlyErrorBox error={task.error_message} context="任务失败" className="mt-3" />
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

function SearchAiStatus({ payload }: { payload: Record<string, unknown> }) {
    const filterSummary = getPayloadObject(payload, "filter_summary");
    const configured = getRecordBoolean(payload, "llm_filter_configured") || getRecordBoolean(filterSummary, "llm_filter_configured");
    const applied = getRecordBoolean(payload, "llm_filter_applied") || getRecordBoolean(filterSummary, "llm_filter_applied");
    const hitAiApplied = getRecordBoolean(payload, "hit_ai_analysis_applied");
    const message = getRecordText(payload, "llm_filter_message") ?? getRecordText(filterSummary, "llm_filter_message");
    if (!configured && !applied && !hitAiApplied && !message) {
        return null;
    }
    return (
        <div className="mt-2 flex flex-wrap items-center gap-2 rounded-lg border border-blue-100 bg-blue-50/70 px-3 py-2 text-xs font-semibold text-blue-700">
            <DemoTag tone={configured ? "cyan" : "orange"}>{configured ? "已配置LLM筛选" : "未配置LLM筛选"}</DemoTag>
            <DemoTag tone={applied ? "green" : configured ? "orange" : "slate"}>{applied ? "LLM已判分" : configured ? "等待判分记录" : "未判分"}</DemoTag>
            <DemoTag tone={hitAiApplied ? "green" : "slate"}>{hitAiApplied ? "AI初筛已入库" : "未记录AI初筛"}</DemoTag>
            {message ? <span className="min-w-0 flex-1 truncate">{message}</span> : null}
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

function getRecordBoolean(record: Record<string, unknown>, key: string) {
    const value = record[key];
    if (typeof value === "boolean") return value;
    if (typeof value === "string") return value.toLowerCase() === "true";
    return false;
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

function normalizeStatus(value: string) {
    return value.toLowerCase();
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

function aggregatePlanGroups(groups: InsightDataSourceGroupRead[]): DataSourcePlanGroup[] {
    const map = new Map<string, DataSourcePlanGroup>();
    const companySets = new Map<string, Set<number>>();
    for (const group of groups) {
        const key = group.source_type;
        const existing = map.get(key) ?? {
            group_key: key,
            source_type: group.source_type,
            source_type_label: group.source_type_label,
            company_count: 0,
            unlinked_count: 0,
            total_count: 0,
            enabled_count: 0,
            disabled_count: 0,
            scheduled_count: 0,
            llm_filter_count: 0,
            auto_review_count: 0,
            failed_count: 0,
            paused_count: 0,
            latest_success_time: null,
            latest_failure_time: null,
            next_run_time: null,
            visibility_scopes: [],
            data_source_ids: [],
            children: [],
        };
        const companySet = companySets.get(key) ?? new Set<number>();
        const childLabel = group.company_id
            ? group.company_short_name || group.company_name || "未命名企业"
            : "未关联主题";
        if (group.company_id) {
            companySet.add(group.company_id);
        } else {
            existing.unlinked_count += group.total_count;
        }
        existing.company_count = companySet.size;
        existing.total_count += group.total_count;
        existing.enabled_count += group.enabled_count;
        existing.disabled_count += group.disabled_count;
        existing.scheduled_count += group.scheduled_count;
        existing.llm_filter_count += group.llm_filter_count;
        existing.auto_review_count += group.auto_review_count;
        existing.failed_count += group.failed_count;
        existing.paused_count += group.paused_count;
        existing.latest_success_time = maxDateString(existing.latest_success_time, group.latest_success_time);
        existing.latest_failure_time = maxDateString(existing.latest_failure_time, group.latest_failure_time);
        existing.next_run_time = minDateString(existing.next_run_time, group.next_run_time);
        existing.visibility_scopes = uniqueStrings([...existing.visibility_scopes, ...group.visibility_scopes]);
        existing.data_source_ids = uniqueIds([...existing.data_source_ids, ...group.data_source_ids]);
        existing.children.push({
            key: `${group.source_type}:${group.company_id ?? "none"}`,
            label: childLabel,
            company_id: group.company_id ?? null,
            company_name: group.company_name || childLabel,
            total_count: group.total_count,
            enabled_count: group.enabled_count,
            scheduled_count: group.scheduled_count,
            failed_count: group.failed_count,
            paused_count: group.paused_count,
            latest_success_time: group.latest_success_time,
            next_run_time: group.next_run_time,
            visibility_scopes: group.visibility_scopes,
            data_source_ids: group.data_source_ids,
        });
        map.set(key, existing);
        companySets.set(key, companySet);
    }
    return Array.from(map.values()).map((group) => ({
        ...group,
        children: group.children.sort((a, b) => {
            const issueDelta = (b.failed_count + b.paused_count) - (a.failed_count + a.paused_count);
            if (issueDelta !== 0) return issueDelta;
            return b.total_count - a.total_count;
        }),
    })).sort((a, b) => {
        const statusDelta = (b.failed_count + b.paused_count) - (a.failed_count + a.paused_count);
        if (statusDelta !== 0) return statusDelta;
        return b.total_count - a.total_count;
    });
}

function aggregateCompanyGroups(groups: InsightDataSourceGroupRead[]): DataSourceCompanyGroup[] {
    const map = new Map<string, DataSourceCompanyGroup>();
    for (const group of groups) {
        const key = String(group.company_id ?? "none");
        const existing = map.get(key) ?? {
            group_key: key,
            company_id: group.company_id ?? null,
            company_name: group.company_name || "未关联企业",
            company_short_name: group.company_short_name,
            sys_company_id: group.sys_company_id,
            type_labels: [],
            total_count: 0,
            enabled_count: 0,
            disabled_count: 0,
            scheduled_count: 0,
            llm_filter_count: 0,
            auto_review_count: 0,
            failed_count: 0,
            paused_count: 0,
            latest_success_time: null,
            latest_failure_time: null,
            next_run_time: null,
            visibility_scopes: [],
            data_source_ids: [],
        };
        existing.type_labels = uniqueStrings([...existing.type_labels, group.source_type_label]);
        existing.total_count += group.total_count;
        existing.enabled_count += group.enabled_count;
        existing.disabled_count += group.disabled_count;
        existing.scheduled_count += group.scheduled_count;
        existing.llm_filter_count += group.llm_filter_count;
        existing.auto_review_count += group.auto_review_count;
        existing.failed_count += group.failed_count;
        existing.paused_count += group.paused_count;
        existing.latest_success_time = maxDateString(existing.latest_success_time, group.latest_success_time);
        existing.latest_failure_time = maxDateString(existing.latest_failure_time, group.latest_failure_time);
        existing.next_run_time = minDateString(existing.next_run_time, group.next_run_time);
        existing.visibility_scopes = uniqueStrings([...existing.visibility_scopes, ...group.visibility_scopes]);
        existing.data_source_ids = uniqueIds([...existing.data_source_ids, ...group.data_source_ids]);
        map.set(key, existing);
    }
    return Array.from(map.values()).sort((a, b) => a.company_name.localeCompare(b.company_name, "zh-CN"));
}

function uniqueStrings(values: string[]) {
    return Array.from(new Set(values.filter(Boolean)));
}

function maxDateString(current?: string | null, next?: string | null) {
    if (!current) return next ?? null;
    if (!next) return current;
    return new Date(next).getTime() > new Date(current).getTime() ? next : current;
}

function minDateString(current?: string | null, next?: string | null) {
    if (!current) return next ?? null;
    if (!next) return current;
    return new Date(next).getTime() < new Date(current).getTime() ? next : current;
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

function toggleId(ids: number[], id: number) {
    return ids.includes(id) ? ids.filter((item) => item !== id) : [...ids, id];
}

function toggleString(values: string[], value: string) {
    return values.includes(value) ? values.filter((item) => item !== value) : [...values, value];
}

function uniqueIds(ids: number[]) {
    return Array.from(new Set(ids));
}

function sourceTypeLabel(value: string) {
    const legacyLabels: Record<string, string> = {
        baidu_search: "百度搜索",
        bocha_news: "博查资讯",
        bocha_web: "博查网页",
        multi_news: "多源资讯",
    };
    return sourceTypeOptions.find((item) => item.value === value)?.label ?? legacyLabels[value] ?? value;
}

function formatVisibilityScopes(values: string[]) {
    if (!values.length) {
        return "未设置";
    }
    const labels: Record<string, string> = {
        private: "仅本人",
        assigned: "指定可见",
        dept: "部门",
        role: "角色",
        public: "公开",
    };
    return values.map((value) => labels[value] ?? value).join("、");
}

function frequencyLabel(value: string) {
    return frequencyOptions.find((item) => item.value === value)?.label ?? value;
}

function getErrorMessage(error: unknown): string {
    let message: string;
    if (typeof error === "object" && error !== null && "response" in error) {
        const response = (error as { response?: { data?: { detail?: string } } }).response;
        message = response?.data?.detail ?? "执行失败，请检查数据源配置。";
    } else {
        message = error instanceof Error ? error.message : "执行失败，请稍后重试。";
    }
    return explainInsightError(message).summary;
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
