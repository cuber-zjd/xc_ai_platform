import { useMemo, useState } from "react";
import { CheckCircle2, EyeOff, ExternalLink, FileText, Loader2, Plus, RefreshCw, Search, ShieldCheck, SlidersHorizontal, Star, Tags, XCircle } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";

import type {
    InsightCandidateListParams,
    InsightIntelligenceCandidateListItem,
    InsightIntelligenceCreate,
    InsightIntelligenceListItem,
    InsightIntelligenceListParams,
} from "../api";
import { DemoCard, DemoTag, RankList, SectionHeader, type TagTone } from "../components/DemoPrimitives";
import { AccessRuleDialog } from "../components";
import { InsightSelect } from "../components/InsightSelect";
import {
    useInsightBulkActionIntelligence,
    useInsightCandidateReview,
    useInsightCandidates,
    useInsightCompanies,
    useInsightCreateIntelligence,
    useInsightDataSources,
    useInsightIntelligences,
    useInsightSystemCompanies,
    useInsightUpsertPool,
} from "../hooks";
import { PageContainer } from "../layout/PageContainer";
import { formatInsightDate, formatInsightType } from "../utils/display";

const subjectOptions = [
    { value: "", label: "全部类型" },
    { value: "company", label: "企业/客户/竞对" },
    { value: "industry", label: "行业趋势" },
    { value: "market", label: "市场动态" },
    { value: "product", label: "产品/新品" },
    { value: "policy", label: "政策法规" },
    { value: "technology", label: "技术应用" },
    { value: "custom", label: "自定义" },
];

const intelligenceTypeOptions = [
    { value: "", label: "全部情报类型" },
    { value: "新品情报", label: "新品情报" },
    { value: "财报公告", label: "财报公告" },
    { value: "行业资讯", label: "行业资讯" },
    { value: "政策法规", label: "政策法规" },
    { value: "应用方案", label: "应用方案" },
];

const sourceOptions = [
    { value: "", label: "全部来源" },
    { value: "firecrawl", label: "网页抓取" },
    { value: "baidu_news", label: "百度资讯" },
    { value: "bocha_news", label: "博查资讯" },
];

const sentimentOptions = [
    { value: "", label: "全部情感" },
    { value: "positive", label: "正向" },
    { value: "neutral", label: "中性" },
    { value: "negative", label: "负向" },
    { value: "mixed", label: "混合" },
];

const bulkSentimentOptions = [
    { value: "", label: "不调整" },
    { value: "positive", label: "正向" },
    { value: "neutral", label: "中性" },
    { value: "negative", label: "负向" },
    { value: "mixed", label: "混合" },
];

export function IntelligenceCenterPage() {
    const [searchParams, setSearchParams] = useSearchParams();
    const dataSourceIdParam = Number(searchParams.get("data_source_id") || 0) || undefined;
    const [keywordInput, setKeywordInput] = useState("");
    const [keyword, setKeyword] = useState("");
    const [subjectType, setSubjectType] = useState("");
    const [intelligenceType, setIntelligenceType] = useState("");
    const [sourceType, setSourceType] = useState("");
    const [sysCompanyId, setSysCompanyId] = useState("");
    const [companyId, setCompanyId] = useState("");
    const [projectName, setProjectName] = useState("");
    const [sentiment, setSentiment] = useState("");
    const [tag, setTag] = useState("");
    const [dataSourceId, setDataSourceId] = useState(dataSourceIdParam ? String(dataSourceIdParam) : "");
    const [dateFrom, setDateFrom] = useState("");
    const [dateTo, setDateTo] = useState("");
    const [viewMode, setViewMode] = useState<"official" | "candidate">(searchParams.get("mode") === "candidate" ? "candidate" : "official");
    const [createOpen, setCreateOpen] = useState(false);
    const [selectedOfficialIds, setSelectedOfficialIds] = useState<number[]>([]);
    const [selectedCandidateIds, setSelectedCandidateIds] = useState<number[]>([]);
    const [bulkAccessOpen, setBulkAccessOpen] = useState(false);
    const [bulkEditOpen, setBulkEditOpen] = useState(false);

    const officialParams = useMemo<InsightIntelligenceListParams>(
        () => ({
            page: 1,
            size: 20,
            keyword: keyword || undefined,
            subject_type: subjectType || undefined,
            intelligence_type: intelligenceType || undefined,
            sys_company_id: parseOptionalNumber(sysCompanyId) ?? undefined,
            company_id: parseOptionalNumber(companyId) ?? undefined,
            project_name: projectName.trim() || undefined,
            sentiment: sentiment || undefined,
            tag: tag.trim() || undefined,
            data_source_id: parseOptionalNumber(dataSourceId) ?? dataSourceIdParam,
            date_from: dateFrom || undefined,
            date_to: dateTo || undefined,
        }),
        [companyId, dataSourceId, dataSourceIdParam, dateFrom, dateTo, intelligenceType, keyword, projectName, sentiment, subjectType, sysCompanyId, tag],
    );
    const candidateParams = useMemo<InsightCandidateListParams>(
        () => ({
            page: 1,
            size: 20,
            keyword: keyword || undefined,
            review_status: "pending",
            subject_type: subjectType || undefined,
            intelligence_type: intelligenceType || undefined,
            data_source_id: parseOptionalNumber(dataSourceId) ?? dataSourceIdParam,
        }),
        [dataSourceId, dataSourceIdParam, intelligenceType, keyword, subjectType],
    );

    const intelligencesQuery = useInsightIntelligences(officialParams);
    const candidatesQuery = useInsightCandidates(candidateParams);
    const companiesQuery = useInsightCompanies({ page: 1, size: 500, sys_company_id: parseOptionalNumber(sysCompanyId) ?? undefined });
    const dataSourcesQuery = useInsightDataSources({ page: 1, size: 500, status: "enabled" });
    const systemCompaniesQuery = useInsightSystemCompanies();
    const reviewMutation = useInsightCandidateReview();
    const createMutation = useInsightCreateIntelligence();
    const poolMutation = useInsightUpsertPool();
    const bulkMutation = useInsightBulkActionIntelligence();
    const intelligences = useMemo(() => intelligencesQuery.data?.items ?? [], [intelligencesQuery.data?.items]);
    const candidates = useMemo(
        () => (candidatesQuery.data?.items ?? []).filter((item) => !sourceType || item.source_channel === sourceType),
        [candidatesQuery.data?.items, sourceType],
    );
    const companyOptions = useMemo(
        () => [
            { value: "", label: "全部企业" },
            ...(companiesQuery.data?.items ?? []).map((company) => ({ value: String(company.id), label: company.short_name || company.name })),
        ],
        [companiesQuery.data?.items],
    );
    const dataSourceOptions = useMemo(
        () => [
            { value: "", label: "全部数据源" },
            ...(dataSourcesQuery.data?.items ?? []).map((source) => ({ value: String(source.id), label: source.source_name })),
        ],
        [dataSourcesQuery.data?.items],
    );
    const systemCompanyOptions = useMemo(
        () => [
            { value: "", label: "全部所属公司" },
            ...(systemCompaniesQuery.data ?? []).map((company) => ({ value: String(company.id), label: company.code ? `${company.name}（${company.code}）` : company.name })),
        ],
        [systemCompaniesQuery.data],
    );
    const hotItems = useMemo(
        () => (viewMode === "official" ? intelligences.slice(0, 5).map((item) => item.title) : candidates.slice(0, 5).map((item) => item.candidate_title)),
        [candidates, intelligences, viewMode],
    );
    const tagItems = useMemo(() => {
        const counts = new Map<string, number>();
        const addTag = (name?: string) => {
            const key = name?.trim();
            if (!key) return;
            counts.set(key, (counts.get(key) ?? 0) + 1);
        };
        intelligences.forEach((item) => item.suggested_tags?.forEach((tag) => addTag(typeof tag.name === "string" ? tag.name : undefined)));
        candidates.forEach((item) => item.suggested_tags?.forEach((tag) => addTag(typeof tag.name === "string" ? tag.name : undefined)));
        return Array.from(counts.entries())
            .sort((left, right) => right[1] - left[1])
            .slice(0, 12)
            .map(([name, count]) => `${name} ${count}`);
    }, [candidates, intelligences]);
    const advancedFilterCount = [
        subjectType,
        intelligenceType,
        sourceType,
        sysCompanyId,
        companyId,
        projectName.trim(),
        sentiment,
        tag.trim(),
        dataSourceId,
        dateFrom,
        dateTo,
    ].filter(Boolean).length;

    const search = () => setKeyword(keywordInput.trim());
    const reset = () => {
        setKeyword("");
        setKeywordInput("");
        setSubjectType("");
        setIntelligenceType("");
        setSourceType("");
        setSysCompanyId("");
        setCompanyId("");
        setProjectName("");
        setSentiment("");
        setTag("");
        setDataSourceId("");
        setDateFrom("");
        setDateTo("");
        setSearchParams({});
        setSelectedOfficialIds([]);
        setSelectedCandidateIds([]);
    };

    const handleReview = (candidateId: number, action: "promote" | "reject" | "ignore") => {
        reviewMutation.mutate(
            {
                candidateId,
                action,
                data: action === "promote" ? { visibility_scope: "assigned", importance_level: "medium" } : {},
            },
            {
                onSuccess: () => toast.success(actionSuccessText[action]),
                onError: () => toast.error("审核操作失败，请稍后重试"),
            },
        );
    };

    const handleAddReportMaterial = (intelligenceId: number) => {
        poolMutation.mutate(
            {
                intelligenceId,
                data: {
                    pool_type: "report_material",
                    folder_name: "默认报告素材",
                },
            },
            {
                onSuccess: () => toast.success("已加入报告素材"),
                onError: () => toast.error("加入报告素材失败，请稍后重试"),
            },
        );
    };

    const selectedCount = viewMode === "official" ? selectedOfficialIds.length : selectedCandidateIds.length;
    const toggleOfficial = (id: number) => setSelectedOfficialIds((current) => toggleId(current, id));
    const toggleCandidate = (id: number) => setSelectedCandidateIds((current) => toggleId(current, id));
    const selectCurrentOfficial = () => setSelectedOfficialIds(intelligences.map((item) => item.id));
    const selectCurrentCandidates = () => setSelectedCandidateIds(candidates.map((item) => item.id));
    const clearSelection = () => {
        setSelectedOfficialIds([]);
        setSelectedCandidateIds([]);
    };

    const handleBulkCandidate = (action: "promote" | "reject" | "ignore") => {
        if (selectedCandidateIds.length === 0) return;
        bulkMutation.mutate(
            {
                target_type: "candidate",
                candidate_ids: selectedCandidateIds,
                action,
                visibility_scope: "assigned",
                importance_level: "medium",
                review_comment: "前端批量审核",
            },
            {
                onSuccess: (result) => {
                    toast.success(`批量操作完成：成功 ${result.success_count} 条，失败 ${result.failed_count} 条`);
                    setSelectedCandidateIds([]);
                },
                onError: () => toast.error("批量审核失败，请稍后重试"),
            },
        );
    };

    const handleBulkOfficial = (action: "add_to_pool" | "hide" | "set_high_importance") => {
        if (selectedOfficialIds.length === 0) return;
        const payload =
            action === "add_to_pool"
                ? { action: "add_to_pool", pool_type: "report_material", folder_name: "默认报告素材", review_comment: "前端批量加入报告素材" }
                : action === "hide"
                    ? { action: "set_status", status: "inactive", review_comment: "前端批量隐藏" }
                    : { action: "set_importance", importance_level: "high", review_comment: "前端批量标记重点" };
        bulkMutation.mutate(
            {
                target_type: "intelligence",
                intelligence_ids: selectedOfficialIds,
                ...payload,
            },
            {
                onSuccess: (result) => {
                    toast.success(`批量操作完成：成功 ${result.success_count} 条，失败 ${result.failed_count} 条`);
                    setSelectedOfficialIds([]);
                },
                onError: () => toast.error("批量操作失败，请稍后重试"),
            },
        );
    };

    const handleBulkMetadata = (payload: { tags?: string; sentiment?: string; importanceLevel?: string }) => {
        if (selectedOfficialIds.length === 0) return;
        const tags = payload.tags
            ?.split(/[,，\n]/)
            .map((item) => item.trim())
            .filter(Boolean)
            .map((name) => ({ name, source: "manual_bulk" }));
        bulkMutation.mutate(
            {
                target_type: "intelligence",
                intelligence_ids: selectedOfficialIds,
                action: "patch_metadata",
                tags,
                sentiment: payload.sentiment || undefined,
                importance_level: payload.importanceLevel || undefined,
                review_comment: "前端批量修正标签、情感和重要性",
            },
            {
                onSuccess: (result) => {
                    toast.success(`批量修正完成：成功 ${result.success_count} 条，失败 ${result.failed_count} 条`);
                    setSelectedOfficialIds([]);
                    setBulkEditOpen(false);
                },
                onError: () => toast.error("批量修正失败，请检查填写内容"),
            },
        );
    };

    return (
        <PageContainer>
            <div className="insight-page-heading">
                <h1 className="text-2xl font-black leading-tight tracking-tight text-slate-950 md:text-3xl">情报中心</h1>
                <div className="insight-actions">
                    <Button className="h-10 rounded-xl px-5" onClick={() => setCreateOpen(true)}>
                        <Plus className="size-4" />
                        新增情报
                    </Button>
                </div>
            </div>

            <DemoCard className="p-3 md:hidden">
                {dataSourceIdParam ? (
                    <div className="mb-3 rounded-xl border border-blue-100 bg-blue-50 px-3 py-2 text-xs font-bold leading-5 text-blue-700">
                        当前仅查看数据源 #{dataSourceIdParam} 产生的候选情报
                    </div>
                ) : null}
                <div className="grid gap-3">
                    <label className="grid gap-2">
                        <span className="text-sm font-bold text-slate-700">关键词</span>
                        <div className="relative">
                            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-400" />
                            <Input
                                className="h-11 rounded-xl border-slate-200 bg-white pl-10 shadow-none"
                                placeholder="搜索标题、摘要、主题"
                                value={keywordInput}
                                onChange={(event) => setKeywordInput(event.target.value)}
                                onKeyDown={(event) => {
                                    if (event.key === "Enter") {
                                        search();
                                    }
                                }}
                            />
                        </div>
                    </label>
                    <div className="grid grid-cols-2 gap-2 rounded-xl bg-slate-100 p-1">
                        <MobileModeButton active={viewMode === "candidate"} onClick={() => setViewMode("candidate")}>候选审核</MobileModeButton>
                        <MobileModeButton active={viewMode === "official"} onClick={() => setViewMode("official")}>正式情报</MobileModeButton>
                    </div>
                    <div className="insight-action-cluster">
                        <Button className="h-10 rounded-xl px-5" onClick={search}>搜索</Button>
                        <Button variant="ghost" className="h-10 rounded-xl px-4 text-slate-600" onClick={reset}>
                            <RefreshCw className="size-4" />
                            重置
                        </Button>
                    </div>
                    <details className="rounded-xl border border-slate-100 bg-slate-50/80 px-3 py-2">
                        <summary className="flex cursor-pointer list-none items-center justify-between gap-3 text-sm font-black text-slate-700">
                            <span className="inline-flex items-center gap-2">
                                <SlidersHorizontal className="size-4 text-slate-500" />
                                高级筛选
                            </span>
                            <span className="text-xs font-bold text-slate-400">
                                {advancedFilterCount} 项
                            </span>
                        </summary>
                        <div className="mt-3 grid gap-3">
                            <InsightSelect label="主题类型" value={subjectType} options={subjectOptions} onChange={setSubjectType} />
                            <InsightSelect label="情报类型" value={intelligenceType} options={intelligenceTypeOptions} onChange={setIntelligenceType} />
                            <InsightSelect label="所属公司" value={sysCompanyId} options={systemCompanyOptions} onChange={setSysCompanyId} />
                            <InsightSelect label="企业" value={companyId} options={companyOptions} onChange={setCompanyId} />
                            <InsightSelect label="情感" value={sentiment} options={sentimentOptions} onChange={setSentiment} />
                            <InsightSelect label="数据源" value={dataSourceId} options={dataSourceOptions} onChange={setDataSourceId} />
                            <InsightSelect label="候选来源" value={sourceType} options={sourceOptions} onChange={setSourceType} />
                            <FilterInput label="课题" value={projectName} onChange={setProjectName} placeholder="课题/项目名称" />
                            <FilterInput label="标签" value={tag} onChange={setTag} placeholder="例如：功能糖" />
                            <FilterInput label="开始日期" value={dateFrom} onChange={setDateFrom} type="date" />
                            <FilterInput label="结束日期" value={dateTo} onChange={setDateTo} type="date" />
                            {dataSourceIdParam ? (
                                <Button variant="outline" className="h-10 rounded-xl bg-white" onClick={() => setSearchParams({ mode: viewMode })}>
                                    清除数据源筛选
                                </Button>
                            ) : null}
                        </div>
                    </details>
                </div>
            </DemoCard>

            <DemoCard className="hidden p-5 md:block">
                {dataSourceIdParam ? (
                    <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-blue-100 bg-blue-50 px-4 py-3 text-sm font-bold text-blue-700">
                        <span>当前仅查看数据源 #{dataSourceIdParam} 产生的候选情报</span>
                        <Button variant="ghost" className="h-8 rounded-lg px-3 text-blue-700 hover:bg-white" onClick={() => setSearchParams({ mode: viewMode })}>
                            清除数据源筛选
                        </Button>
                    </div>
                ) : null}
                <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-[minmax(220px,1.2fr)_180px_180px_180px_auto] xl:items-end">
                    <label className="grid gap-2">
                        <span className="text-sm font-bold text-slate-700">关键词</span>
                        <div className="relative">
                            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-400" />
                            <Input
                                className="h-11 rounded-xl border-slate-200 bg-white pl-10 shadow-none"
                                placeholder="搜索标题、摘要、主题"
                                value={keywordInput}
                                onChange={(event) => setKeywordInput(event.target.value)}
                                onKeyDown={(event) => {
                                    if (event.key === "Enter") {
                                        search();
                                    }
                                }}
                            />
                        </div>
                    </label>
                    <InsightSelect label="主题类型" value={subjectType} options={subjectOptions} onChange={setSubjectType} />
                    <InsightSelect label="情报类型" value={intelligenceType} options={intelligenceTypeOptions} onChange={setIntelligenceType} />
                    <InsightSelect label="所属公司" value={sysCompanyId} options={systemCompanyOptions} onChange={setSysCompanyId} />
                    <div className="flex items-end md:col-span-2 xl:col-span-1">
                        <div className="insight-action-cluster w-full justify-start xl:justify-end">
                            <Button className="h-11 rounded-xl px-7" onClick={search}>搜索</Button>
                            <Button variant="ghost" className="h-11 rounded-xl px-4 text-slate-600" onClick={reset}>
                                <RefreshCw className="size-4" />
                                重置
                            </Button>
                        </div>
                    </div>
                </div>
                <div className="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-6 xl:items-end">
                    <InsightSelect label="企业" value={companyId} options={companyOptions} onChange={setCompanyId} />
                    <InsightSelect label="情感" value={sentiment} options={sentimentOptions} onChange={setSentiment} />
                    <InsightSelect label="数据源" value={dataSourceId} options={dataSourceOptions} onChange={setDataSourceId} />
                    <InsightSelect label="候选来源" value={sourceType} options={sourceOptions} onChange={setSourceType} />
                    <FilterInput label="课题" value={projectName} onChange={setProjectName} placeholder="项目/课题" />
                    <FilterInput label="标签" value={tag} onChange={setTag} placeholder="标签关键词" />
                </div>
                <div className="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-[180px_180px_minmax(0,1fr)] xl:items-end">
                    <FilterInput label="开始日期" value={dateFrom} onChange={setDateFrom} type="date" />
                    <FilterInput label="结束日期" value={dateTo} onChange={setDateTo} type="date" />
                    <div className="rounded-xl border border-slate-100 bg-slate-50 px-3 py-2 text-xs font-semibold leading-5 text-slate-500">
                        正式情报筛选会传到后端权限过滤后再分页；候选审核当前支持关键词、主题、类型、数据源和候选来源筛选。
                    </div>
                </div>
            </DemoCard>

            <DemoCard className="overflow-hidden">
                <div className="hidden border-b border-slate-200 px-5 pt-4 md:block">
                    <div className="flex flex-wrap gap-x-10 gap-y-2 text-base font-bold text-slate-600">
                        <TabButton active={viewMode === "official"} onClick={() => setViewMode("official")}>正式情报</TabButton>
                        <TabButton active={viewMode === "candidate"} onClick={() => setViewMode("candidate")}>候选审核</TabButton>
                    </div>
                </div>
                <div className="space-y-4 p-3 sm:p-4">
                    <BulkActionBar
                        mode={viewMode}
                        selectedCount={selectedCount}
                        pending={bulkMutation.isPending}
                        onSelectPage={viewMode === "official" ? selectCurrentOfficial : selectCurrentCandidates}
                        onClear={clearSelection}
                        onCandidateAction={handleBulkCandidate}
                        onOfficialAction={handleBulkOfficial}
                        onOpenBulkAccess={() => setBulkAccessOpen(true)}
                        onOpenBulkEdit={() => setBulkEditOpen(true)}
                    />
                    <div className="min-h-0 min-w-0 overflow-y-auto rounded-xl border border-slate-200 bg-white xl:max-h-[calc(100dvh-23rem)]">
                        {viewMode === "official" ? (
                            <OfficialFeed
                                rows={intelligences}
                                loading={intelligencesQuery.isLoading}
                                pending={poolMutation.isPending}
                                selectedIds={selectedOfficialIds}
                                onToggleSelected={toggleOfficial}
                                onAddReportMaterial={handleAddReportMaterial}
                            />
                        ) : (
                            <CandidateFeed
                                rows={candidates}
                                loading={candidatesQuery.isLoading}
                                pending={reviewMutation.isPending}
                                selectedIds={selectedCandidateIds}
                                onToggleSelected={toggleCandidate}
                                onReview={handleReview}
                            />
                        )}
                    </div>

                    <div className="grid min-w-0 gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
                        <DemoCard className="p-4">
                            <SectionHeader title="今日热点" />
                            <RankList showViews items={hotItems.length > 0 ? hotItems : ["暂无候选情报"]} />
                        </DemoCard>
                        <DemoCard className="p-4">
                            <SectionHeader title="标签云" />
                            <div className="flex flex-wrap gap-2">
                                {tagItems.map((tag, index) => (
                                    <DemoTag key={tag} tone={index % 4 === 0 ? "blue" : index % 4 === 1 ? "green" : index % 4 === 2 ? "orange" : "purple"} className="whitespace-nowrap">
                                        {tag}
                                    </DemoTag>
                                ))}
                                {tagItems.length === 0 ? <span className="text-sm font-semibold text-slate-500">暂无标签</span> : null}
                            </div>
                        </DemoCard>
                    </div>
                </div>
            </DemoCard>

            <CreateIntelligenceDialog
                open={createOpen}
                pending={createMutation.isPending}
                onOpenChange={setCreateOpen}
                onSubmit={(payload) => {
                    createMutation.mutate(payload, {
                        onSuccess: () => {
                            toast.success("正式情报已新增");
                            setCreateOpen(false);
                            setViewMode("official");
                        },
                        onError: () => toast.error("新增情报失败，请检查必填项"),
                    });
                }}
            />
            <AccessRuleDialog
                open={bulkAccessOpen}
                onOpenChange={setBulkAccessOpen}
                targetType="intelligence"
                targetId={selectedOfficialIds[0] ?? null}
                targetIds={selectedOfficialIds}
                targetName={`已选择 ${selectedOfficialIds.length} 条正式情报`}
            />
            <BulkMetadataDialog
                open={bulkEditOpen}
                count={selectedOfficialIds.length}
                pending={bulkMutation.isPending}
                onOpenChange={setBulkEditOpen}
                onSubmit={handleBulkMetadata}
            />
        </PageContainer>
    );
}

function BulkActionBar({
    mode,
    selectedCount,
    pending,
    onSelectPage,
    onClear,
    onCandidateAction,
    onOfficialAction,
    onOpenBulkAccess,
    onOpenBulkEdit,
}: {
    mode: "official" | "candidate";
    selectedCount: number;
    pending: boolean;
    onSelectPage: () => void;
    onClear: () => void;
    onCandidateAction: (action: "promote" | "reject" | "ignore") => void;
    onOfficialAction: (action: "add_to_pool" | "hide" | "set_high_importance") => void;
    onOpenBulkAccess: () => void;
    onOpenBulkEdit: () => void;
}) {
    return (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-200 bg-slate-50/80 px-3 py-3">
            <div className="flex flex-wrap items-center gap-2 text-sm font-bold text-slate-600">
                <Button type="button" variant="outline" className="h-9 rounded-lg bg-white" onClick={onSelectPage}>
                    选择本页
                </Button>
                <Button type="button" variant="ghost" className="h-9 rounded-lg text-slate-600" disabled={selectedCount === 0} onClick={onClear}>
                    清空选择
                </Button>
                <span>已选择 {selectedCount} 条</span>
            </div>
            {mode === "candidate" ? (
                <div className="insight-action-cluster">
                    <Button type="button" className="h-9 rounded-lg" disabled={pending || selectedCount === 0} onClick={() => onCandidateAction("promote")}>
                        {pending ? <Loader2 className="size-4 animate-spin" /> : <CheckCircle2 className="size-4" />}
                        批量通过
                    </Button>
                    <Button type="button" variant="outline" className="h-9 rounded-lg bg-white" disabled={pending || selectedCount === 0} onClick={() => onCandidateAction("ignore")}>
                        <EyeOff className="size-4" />
                        批量忽略
                    </Button>
                    <Button type="button" variant="outline" className="h-9 rounded-lg bg-white text-red-600 hover:text-red-700" disabled={pending || selectedCount === 0} onClick={() => onCandidateAction("reject")}>
                        <XCircle className="size-4" />
                        批量拒绝
                    </Button>
                </div>
            ) : (
                <div className="insight-action-cluster">
                    <Button type="button" className="h-9 rounded-lg" disabled={pending || selectedCount === 0} onClick={() => onOfficialAction("add_to_pool")}>
                        {pending ? <Loader2 className="size-4 animate-spin" /> : <FileText className="size-4" />}
                        加入素材池
                    </Button>
                    <Button type="button" variant="outline" className="h-9 rounded-lg bg-white" disabled={pending || selectedCount === 0} onClick={() => onOfficialAction("set_high_importance")}>
                        <Star className="size-4" />
                        标记重点
                    </Button>
                    <Button type="button" variant="outline" className="h-9 rounded-lg bg-white" disabled={pending || selectedCount === 0} onClick={onOpenBulkEdit}>
                        <Tags className="size-4" />
                        批量修正
                    </Button>
                    <Button type="button" variant="outline" className="h-9 rounded-lg bg-white" disabled={pending || selectedCount === 0} onClick={onOpenBulkAccess}>
                        <ShieldCheck className="size-4" />
                        批量授权
                    </Button>
                    <Button type="button" variant="outline" className="h-9 rounded-lg bg-white" disabled={pending || selectedCount === 0} onClick={() => onOfficialAction("hide")}>
                        <EyeOff className="size-4" />
                        批量隐藏
                    </Button>
                </div>
            )}
        </div>
    );
}

function BulkMetadataDialog({
    open,
    count,
    pending,
    onOpenChange,
    onSubmit,
}: {
    open: boolean;
    count: number;
    pending: boolean;
    onOpenChange: (open: boolean) => void;
    onSubmit: (payload: { tags?: string; sentiment?: string; importanceLevel?: string }) => void;
}) {
    const [tags, setTags] = useState("");
    const [sentiment, setSentiment] = useState("");
    const [importanceLevel, setImportanceLevel] = useState("");
    const hasChange = Boolean(tags.trim() || sentiment || importanceLevel);
    const submit = () => {
        if (!hasChange) {
            toast.error("请至少填写标签、情感或重要性中的一项");
            return;
        }
        onSubmit({ tags, sentiment, importanceLevel });
    };
    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="sm:max-w-xl">
                <DialogHeader>
                    <DialogTitle>批量修正情报</DialogTitle>
                    <DialogDescription>
                        将对已选择的 {count} 条正式情报批量写入。留空的项目不会覆盖原值，标签支持逗号或换行分隔。
                    </DialogDescription>
                </DialogHeader>
                <div className="grid gap-4">
                    <TextAreaField label="标签" value={tags} onChange={setTags} rows={4} />
                    <div className="grid gap-3 md:grid-cols-2">
                        <InsightSelect label="情感" value={sentiment} options={bulkSentimentOptions} onChange={setSentiment} />
                        <InsightSelect
                            label="重要性"
                            value={importanceLevel}
                            options={[
                                { value: "", label: "不调整" },
                                { value: "high", label: "高" },
                                { value: "medium", label: "中" },
                                { value: "low", label: "低" },
                            ]}
                            onChange={setImportanceLevel}
                        />
                    </div>
                </div>
                <DialogFooter>
                    <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>取消</Button>
                    <Button type="button" disabled={pending || count === 0 || !hasChange} onClick={submit}>
                        {pending ? <Loader2 className="size-4 animate-spin" /> : <Tags className="size-4" />}
                        应用修正
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

function OfficialFeed({
    rows,
    loading,
    pending,
    selectedIds,
    onToggleSelected,
    onAddReportMaterial,
}: {
    rows: InsightIntelligenceListItem[];
    loading: boolean;
    pending: boolean;
    selectedIds: number[];
    onToggleSelected: (id: number) => void;
    onAddReportMaterial: (intelligenceId: number) => void;
}) {
    return (
        <div className="divide-y divide-slate-100">
            {rows.map((row) => (
                <article key={row.id} className="group px-5 py-4 transition hover:bg-blue-50/40">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                        <label className="mt-1 inline-flex size-6 shrink-0 items-center justify-center rounded-lg border border-slate-200 bg-white">
                            <input className="size-4 accent-blue-600" type="checkbox" checked={selectedIds.includes(row.id)} onChange={() => onToggleSelected(row.id)} />
                        </label>
                        <div className="min-w-0 flex-1">
                            <a
                                href={row.primary_source_url || `/insight/intelligence/${row.id}`}
                                target={row.primary_source_url ? "_blank" : undefined}
                                rel={row.primary_source_url ? "noreferrer" : undefined}
                                className="line-clamp-2 text-lg font-black leading-7 text-slate-900 group-hover:text-blue-600"
                            >
                                {row.title}
                            </a>
                            <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-2 text-xs font-semibold text-slate-500">
                                <span>{row.primary_source_title || sourceChannelText[row.primary_source_type ?? ""] || "来源未识别"}</span>
                                <span>{formatInsightDate(row.publish_time, row.capture_time ?? row.create_time)}</span>
                                <DemoTag tone="blue">{formatInsightType(row.intelligence_type)}</DemoTag>
                                <DemoTag tone={sentimentTone[row.sentiment] ?? "slate"}>{sentimentText[row.sentiment] ?? row.sentiment}</DemoTag>
                                <DemoTag tone={row.visibility_scope === "public" ? "green" : "slate"}>{visibilityText[row.visibility_scope] ?? row.visibility_scope}</DemoTag>
                            </div>
                        </div>
                        <div className="flex shrink-0 flex-wrap items-center justify-start gap-2">
                            {row.primary_source_url ? <SourceLink url={row.primary_source_url} /> : null}
                            <button
                                type="button"
                                disabled={pending}
                                className="inline-flex h-8 items-center gap-1 rounded-lg px-2 text-xs font-bold text-slate-600 hover:bg-white hover:text-blue-600 disabled:cursor-not-allowed disabled:opacity-60"
                                onClick={() => onAddReportMaterial(row.id)}
                            >
                                <FileText className="size-4" />
                                报告素材
                            </button>
                            <Link to={`/insight/intelligence/${row.id}`} className="inline-flex h-8 items-center rounded-lg px-2 text-xs font-bold text-slate-600 hover:bg-white hover:text-blue-600">
                                详情
                            </Link>
                        </div>
                    </div>
                    <p className="mt-3 line-clamp-3 text-sm font-semibold leading-6 text-slate-600">{compactText(row.summary || row.primary_source_title || "暂无摘要")}</p>
                    <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
                        <TagList tags={row.suggested_tags} fallback={row.subject_name || subjectTypeText[row.subject_type]} />
                        <div className="text-xs font-semibold text-slate-400">来源数 {row.source_count}</div>
                    </div>
                </article>
            ))}
            {!loading && rows.length === 0 ? <EmptyState text="暂无正式情报，可先在候选审核中通过一条情报。" /> : null}
        </div>
    );
}

function CandidateFeed({
    rows,
    loading,
    pending,
    selectedIds,
    onToggleSelected,
    onReview,
}: {
    rows: InsightIntelligenceCandidateListItem[];
    loading: boolean;
    pending: boolean;
    selectedIds: number[];
    onToggleSelected: (id: number) => void;
    onReview: (candidateId: number, action: "promote" | "reject" | "ignore") => void;
}) {
    return (
        <div className="divide-y divide-slate-100">
            {rows.map((row) => (
                <article key={row.id} className="group px-5 py-4 transition hover:bg-blue-50/40">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                        <label className="mt-1 inline-flex size-6 shrink-0 items-center justify-center rounded-lg border border-slate-200 bg-white">
                            <input className="size-4 accent-blue-600" type="checkbox" checked={selectedIds.includes(row.id)} onChange={() => onToggleSelected(row.id)} />
                        </label>
                        <div className="min-w-0 flex-1">
                            {row.source_url ? (
                                <a href={row.source_url} target="_blank" rel="noreferrer" className="line-clamp-2 text-lg font-black leading-7 text-slate-900 group-hover:text-blue-600">
                                    {row.candidate_title}
                                </a>
                            ) : (
                                <h3 className="line-clamp-2 text-lg font-black leading-7 text-slate-900">{row.candidate_title}</h3>
                            )}
                            <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-2 text-xs font-semibold text-slate-500">
                                <span>{row.source_title || sourceChannelText[row.source_channel ?? ""] || "来源未识别"}</span>
                                <span>{formatInsightDate(row.source_publish_time, row.create_time)}</span>
                                <DemoTag tone="green">{formatInsightType(row.intelligence_type) || subjectTypeText[row.subject_type] || "候选资讯"}</DemoTag>
                                <DemoTag tone={candidateStatusTone[row.review_status] ?? "slate"}>{candidateStatusText[row.review_status] ?? row.review_status}</DemoTag>
                            </div>
                        </div>
                        <div className="flex shrink-0 flex-wrap items-center justify-start gap-2">
                            {row.source_url ? <SourceLink url={row.source_url} /> : null}
                            <CandidateActionButtons rowStatus={row.review_status} pending={pending} onReview={(action) => onReview(row.id, action)} />
                        </div>
                    </div>
                    <p className="mt-3 line-clamp-3 text-sm font-semibold leading-6 text-slate-600">{compactText(row.candidate_summary || row.source_title || "暂无摘要")}</p>
                    <QualitySummary row={row} />
                    <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
                        <TagList tags={row.suggested_tags} fallback={row.subject_name || row.query_text || sourceChannelText[row.source_channel ?? ""]} />
                        <div className="text-xs font-semibold text-slate-400">置信度 {Math.round((row.confidence ?? 0) * 100)}%</div>
                    </div>
                </article>
            ))}
            {!loading && rows.length === 0 ? <EmptyState text="暂无候选情报，可先在数据源配置页执行采集测试。" /> : null}
        </div>
    );
}

function QualitySummary({ row }: { row: InsightIntelligenceCandidateListItem }) {
    const issues = (row.quality_issues ?? []).filter(Boolean).slice(0, 3);
    const hasQuality = typeof row.quality_score === "number" || issues.length > 0 || row.quality_auto_ignore;
    if (!hasQuality) {
        return null;
    }
    const qualityPercent = typeof row.quality_score === "number" ? Math.round(row.quality_score * 100) : null;
    return (
        <div className="mt-3 flex flex-wrap items-center gap-2 text-xs font-semibold">
            {qualityPercent !== null ? <DemoTag tone={qualityPercent >= 70 ? "green" : qualityPercent >= 45 ? "orange" : "red"}>质量 {qualityPercent}%</DemoTag> : null}
            {row.quality_auto_ignore ? <DemoTag tone="red">建议忽略</DemoTag> : null}
            {issues.map((issue, index) => (
                <DemoTag key={`${issue}-${index}`} tone="orange">{issue}</DemoTag>
            ))}
        </div>
    );
}

function TabButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: string }) {
    return (
        <button type="button" className={active ? "border-b-[3px] border-blue-600 pb-4 text-blue-600" : "pb-4 hover:text-blue-600"} onClick={onClick}>
            {children}
        </button>
    );
}

function MobileModeButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: string }) {
    return (
        <button
            type="button"
            className={active ? "h-9 rounded-lg bg-white text-sm font-black text-blue-600 shadow-sm" : "h-9 rounded-lg text-sm font-bold text-slate-500"}
            onClick={onClick}
        >
            {children}
        </button>
    );
}

function TagList({ tags, fallback }: { tags?: Array<{ name?: string } & Record<string, unknown>> | null; fallback?: string | null }) {
    const visibleTags = (tags ?? []).map((tag) => tag.name).filter(Boolean).slice(0, 3) as string[];
    return (
        <div className="flex flex-wrap items-start gap-2">
            {visibleTags.map((tag, index) => <DemoTag key={`${tag}-${index}`} tone="cyan" className="whitespace-nowrap">{tag}</DemoTag>)}
            {fallback ? <DemoTag tone="slate" className="whitespace-nowrap">{fallback}</DemoTag> : null}
        </div>
    );
}

function SourceLink({ url }: { url: string }) {
    return (
        <a href={url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 whitespace-nowrap text-blue-600 hover:text-blue-700">
            <ExternalLink className="size-4" />
            原文
        </a>
    );
}

function EmptyState({ text }: { text: string }) {
    return (
        <div className="px-4 py-12 text-center text-sm font-semibold text-slate-500">{text}</div>
    );
}

function FilterInput({
    label,
    value,
    onChange,
    placeholder,
    type = "text",
}: {
    label: string;
    value: string;
    onChange: (value: string) => void;
    placeholder?: string;
    type?: "text" | "date";
}) {
    return (
        <label className="grid gap-2">
            <span className="text-sm font-bold text-slate-700">{label}</span>
            <Input
                type={type}
                className="h-11 rounded-xl border-slate-200 bg-white shadow-none"
                value={value}
                onChange={(event) => onChange(event.target.value)}
                placeholder={placeholder}
            />
        </label>
    );
}

function CreateIntelligenceDialog({
    open,
    pending,
    onOpenChange,
    onSubmit,
}: {
    open: boolean;
    pending: boolean;
    onOpenChange: (open: boolean) => void;
    onSubmit: (payload: InsightIntelligenceCreate) => void;
}) {
    const [form, setForm] = useState({
        title: "",
        subject_name: "",
        subject_type: "custom",
        intelligence_type: "行业资讯",
        visibility_scope: "assigned",
        summary: "",
        content: "",
        source_url: "",
        source_title: "",
        tags: "",
    });
    const update = (field: keyof typeof form, value: string) => setForm((current) => ({ ...current, [field]: value }));
    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="max-h-[90vh] overflow-auto sm:max-w-3xl">
                <DialogHeader><DialogTitle>新增正式情报</DialogTitle></DialogHeader>
                <div className="grid gap-4 md:grid-cols-2">
                    <Field label="标题" value={form.title} onChange={(value) => update("title", value)} className="md:col-span-2" />
                    <Field label="主题名称" value={form.subject_name} onChange={(value) => update("subject_name", value)} />
                    <Field label="情报类型" value={form.intelligence_type} onChange={(value) => update("intelligence_type", value)} />
                    <Field label="主题类型" value={form.subject_type} onChange={(value) => update("subject_type", value)} placeholder="company / industry / product / custom" />
                    <Field label="可见性" value={form.visibility_scope} onChange={(value) => update("visibility_scope", value)} placeholder="assigned / public / private" />
                    <Field label="标签" value={form.tags} onChange={(value) => update("tags", value)} placeholder="用逗号分隔" className="md:col-span-2" />
                    <TextAreaField label="摘要" value={form.summary} onChange={(value) => update("summary", value)} className="md:col-span-2" />
                    <TextAreaField label="正文" value={form.content} onChange={(value) => update("content", value)} className="md:col-span-2" rows={7} />
                    <Field label="来源标题" value={form.source_title} onChange={(value) => update("source_title", value)} />
                    <Field label="来源 URL" value={form.source_url} onChange={(value) => update("source_url", value)} />
                </div>
                <DialogFooter>
                    <Button variant="ghost" onClick={() => onOpenChange(false)}>取消</Button>
                    <Button disabled={pending || !form.title.trim()} onClick={() => onSubmit(buildCreatePayload(form))}>保存</Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

function buildCreatePayload(form: {
    title: string;
    subject_name: string;
    subject_type: string;
    intelligence_type: string;
    visibility_scope: string;
    summary: string;
    content: string;
    source_url: string;
    source_title: string;
    tags: string;
}): InsightIntelligenceCreate {
    const tags = form.tags
        .split(/[,，]/)
        .map((item) => item.trim())
        .filter(Boolean)
        .map((name) => ({ name, source: "manual" }));
    return {
        title: form.title.trim(),
        subject_name: form.subject_name.trim() || undefined,
        subject_type: form.subject_type.trim() || "custom",
        intelligence_type: form.intelligence_type.trim() || "行业资讯",
        visibility_scope: form.visibility_scope.trim() || "assigned",
        summary: form.summary.trim() || undefined,
        content: form.content.trim() || undefined,
        suggested_tags: tags,
        source: form.source_url.trim() || form.source_title.trim()
            ? {
                source_type: "manual",
                source_url: form.source_url.trim() || undefined,
                source_title: form.source_title.trim() || form.title.trim(),
                content_excerpt: form.summary.trim() || undefined,
            }
            : undefined,
    };
}

function Field({ label, value, onChange, placeholder, className }: { label: string; value: string; onChange: (value: string) => void; placeholder?: string; className?: string }) {
    return (
        <label className={`grid gap-2 ${className ?? ""}`}>
            <span className="text-sm font-bold text-slate-700">{label}</span>
            <Input className="h-11 rounded-xl border-slate-200 bg-white shadow-none" value={value} placeholder={placeholder} onChange={(event) => onChange(event.target.value)} />
        </label>
    );
}

function TextAreaField({ label, value, onChange, className, rows = 4 }: { label: string; value: string; onChange: (value: string) => void; className?: string; rows?: number }) {
    return (
        <label className={`grid gap-2 ${className ?? ""}`}>
            <span className="text-sm font-bold text-slate-700">{label}</span>
            <textarea className="min-h-24 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm shadow-none outline-none focus:border-blue-300" rows={rows} value={value} onChange={(event) => onChange(event.target.value)} />
        </label>
    );
}

const subjectTypeText: Record<string, string> = {
    company: "企业",
    industry: "行业趋势",
    market: "市场",
    product: "产品",
    policy: "政策",
    technology: "技术",
    custom: "自定义",
};

const candidateStatusText: Record<string, string> = {
    pending: "待审核",
    promoted: "已转正式",
    rejected: "已驳回",
    merged: "已合并",
    ignored: "已忽略",
};

const candidateStatusTone: Record<string, TagTone> = {
    pending: "orange",
    promoted: "green",
    rejected: "red",
    merged: "purple",
    ignored: "slate",
};

const visibilityText: Record<string, string> = {
    private: "私有",
    assigned: "指定可见",
    dept: "部门可见",
    role: "角色可见",
    public: "公开",
};

const sentimentText: Record<string, string> = {
    positive: "正向",
    neutral: "中性",
    negative: "负向",
    mixed: "混合",
};

const sentimentTone: Record<string, TagTone> = {
    positive: "green",
    neutral: "slate",
    negative: "red",
    mixed: "purple",
};

const sourceChannelText: Record<string, string> = {
    firecrawl: "网页抓取",
    baidu_news: "百度资讯",
    bocha_news: "博查资讯",
    baidu: "百度",
    bocha: "博查",
    FIRECRAWL: "网页抓取",
    BAIDU_NEWS: "百度资讯",
    BOCHA_NEWS: "博查资讯",
    BAIDU: "百度",
    BOCHA: "博查",
};

const actionSuccessText: Record<"promote" | "reject" | "ignore", string> = {
    promote: "已转为正式情报",
    reject: "已驳回候选情报",
    ignore: "已忽略候选情报",
};

function CandidateActionButtons({ rowStatus, pending, onReview }: { rowStatus: string; pending: boolean; onReview: (action: "promote" | "reject" | "ignore") => void }) {
    const [confirmAction, setConfirmAction] = useState<"reject" | "ignore" | null>(null);
    if (rowStatus !== "pending") {
        return <span className="text-xs font-semibold text-slate-400">已处理</span>;
    }
    const confirmTitle = confirmAction === "reject" ? "确认驳回候选情报" : "确认忽略候选情报";
    const confirmDescription = confirmAction === "reject"
        ? "驳回后这条候选不会进入正式情报池，请确认它确实不适合作为市场洞察素材。"
        : "忽略后这条候选会从待审核列表中移出，适合用于重复、低价值或暂不处理的内容。";
    return (
        <>
            <div className="flex flex-wrap items-center gap-2">
                <Button variant="outline" className="h-9 rounded-lg border-emerald-100 bg-emerald-50 px-3 text-xs font-black text-emerald-700 hover:bg-emerald-100 hover:text-emerald-800" disabled={pending} title="通过并转正式情报" onClick={() => onReview("promote")}>
                    <CheckCircle2 className="size-4" />
                    通过
                </Button>
                <Button variant="outline" className="h-9 rounded-lg border-red-100 bg-red-50 px-3 text-xs font-black text-red-600 hover:bg-red-100 hover:text-red-700" disabled={pending} title="驳回候选情报" onClick={() => setConfirmAction("reject")}>
                    <XCircle className="size-4" />
                    驳回
                </Button>
                <Button variant="outline" className="h-9 rounded-lg border-slate-200 bg-white px-3 text-xs font-black text-slate-600 hover:bg-slate-100" disabled={pending} title="忽略候选情报" onClick={() => setConfirmAction("ignore")}>
                    <EyeOff className="size-4" />
                    忽略
                </Button>
            </div>
            <Dialog open={Boolean(confirmAction)} onOpenChange={(open) => {
                if (!open) setConfirmAction(null);
            }}>
                <DialogContent className="sm:max-w-md">
                    <DialogHeader>
                        <DialogTitle>{confirmTitle}</DialogTitle>
                        <DialogDescription>{confirmDescription}</DialogDescription>
                    </DialogHeader>
                    <DialogFooter>
                        <Button variant="ghost" onClick={() => setConfirmAction(null)}>取消</Button>
                        <Button
                            variant={confirmAction === "reject" ? "destructive" : "outline"}
                            disabled={pending}
                            onClick={() => {
                                if (!confirmAction) return;
                                onReview(confirmAction);
                                setConfirmAction(null);
                            }}
                        >
                            确认{confirmAction === "reject" ? "驳回" : "忽略"}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </>
    );
}

function compactText(value: string) {
    return value.replace(/!\[[^\]]*\]\([^)]+\)/g, " ").replace(/\[([^\]]{1,80})\]\([^)]+\)/g, "$1").replace(/https?:\/\/\S+/g, " ").replace(/\s+/g, " ").trim();
}

function toggleId(ids: number[], id: number) {
    return ids.includes(id) ? ids.filter((item) => item !== id) : [...ids, id];
}

function parseOptionalNumber(value: string) {
    const parsed = Number(value);
    return Number.isFinite(parsed) && parsed > 0 ? parsed : undefined;
}
