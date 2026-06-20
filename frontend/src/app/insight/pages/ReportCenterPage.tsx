import { useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { CalendarClock, Copy, Download, ExternalLink, FileText, Info, Loader2, Pencil, PlayCircle, Plus, RefreshCw, Save, Search, Send, Settings2, ShieldCheck, SlidersHorizontal, Sparkles, Trash2, UploadCloud, X } from "lucide-react";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

import type {
    InsightReportChapter,
    InsightReportChartRead,
    InsightReportCompanySection,
    InsightReportContent,
    InsightReportExportRead,
    InsightReportFinding,
    InsightCompanyListItem,
    InsightDataSourceRead,
    InsightReportListItem,
    InsightReportPreferenceRead,
    InsightReportPreferenceUpdate,
    InsightReportSubscriptionCreate,
    InsightReportSubscriptionRead,
    InsightReportTemplateCreate,
    InsightReportTemplateRead,
    InsightReportTemplateSection,
    SystemCompanyOption,
} from "../api";
import { insightApi } from "../api";
import { AccessRuleDialog, ChartCard, InsightSelect, SectionCard, WecomPushDialog } from "../components";
import { PageContainer } from "../layout/PageContainer";
import {
    useInsightCompanies,
    useInsightCloneReportTemplate,
    useInsightCreateReportSubscription,
    useInsightCreateReportTemplate,
    useInsightDeleteReportSubscription,
    useInsightDeleteReportTemplate,
    useInsightGenerateReport,
    useInsightPublishReportTemplate,
    useInsightReportDetail,
    useInsightReportExports,
    useInsightReportPreference,
    useInsightReports,
    useInsightReportSubscriptions,
    useInsightReportTemplates,
    useInsightRunReportSubscription,
    useInsightSystemCompanies,
    useInsightUpdateReportSubscription,
    useInsightUpdateReportPreference,
    useInsightUpdateReportTemplate,
    useInsightUpdateReport,
    useInsightExportReport,
    useInsightUploadReportTemplate,
    useInsightDataSources,
} from "../hooks";

type ReportDetail = NonNullable<ReturnType<typeof useInsightReportDetail>["data"]>;
type ReportMaterial = ReportDetail["materials"][number];
type ReportExportFormat = "html" | "pdf" | "docx";

export function ReportCenterPage() {
    const [searchParams, setSearchParams] = useSearchParams();
    const reportIdParam = parseOptionalNumber(searchParams.get("report_id") || "");
    const [keyword, setKeyword] = useState("");
    const [selectedReportId, setSelectedReportId] = useState<number | null>(reportIdParam ?? null);
    const [templateCode, setTemplateCode] = useState("customer_business_review");
    const [reportType, setReportType] = useState("专题报告");
    const [companyId, setCompanyId] = useState("");
    const [selectedDataSourceIds, setSelectedDataSourceIds] = useState<number[]>([]);
    const [dataSourcePickerOpen, setDataSourcePickerOpen] = useState(false);
    const [folderName, setFolderName] = useState("P1企业档案测试素材");
    const [maxMaterials, setMaxMaterials] = useState("100");
    const [prompt, setPrompt] = useState("生成一份可直接交付的 Word 式客户经营洞察报告，正文完整、结论克制、引用可追溯。");
    const [templateDialogOpen, setTemplateDialogOpen] = useState(false);
    const [preferenceDialogOpen, setPreferenceDialogOpen] = useState(false);
    const [subscriptionDialogOpen, setSubscriptionDialogOpen] = useState(false);
    const [reportAccessTarget, setReportAccessTarget] = useState<InsightReportListItem | ReportDetail | null>(null);
    const [reportPushTarget, setReportPushTarget] = useState<InsightReportListItem | ReportDetail | null>(null);

    const reportsQuery = useInsightReports({ page: 1, size: 30, keyword: keyword || undefined });
    const templatesQuery = useInsightReportTemplates();
    const preferenceQuery = useInsightReportPreference();
    const templates = useMemo(() => templatesQuery.data ?? [], [templatesQuery.data]);
    const reports = useMemo(() => reportsQuery.data?.items ?? [], [reportsQuery.data?.items]);
    const selectedReport = reports.find((report) => report.id === selectedReportId) ?? reports[0] ?? null;
    const activeReportId = selectedReportId ?? selectedReport?.id ?? null;
    const reportDetailQuery = useInsightReportDetail(activeReportId);
    const reportDetail = reportDetailQuery.data ?? selectedReport;
    const reportExportsQuery = useInsightReportExports(reportDetail?.id ?? null);
    const companiesQuery = useInsightCompanies({ page: 1, size: 500 });
    const systemCompaniesQuery = useInsightSystemCompanies();
    const dataSourcesQuery = useInsightDataSources({ page: 1, size: 500, status: "enabled" });
    const subscriptionsQuery = useInsightReportSubscriptions({ page: 1, size: 20 });
    const generateMutation = useInsightGenerateReport();
    const updateMutation = useInsightUpdateReport();
    const exportMutation = useInsightExportReport();
    const createSubscriptionMutation = useInsightCreateReportSubscription();
    const updateSubscriptionMutation = useInsightUpdateReportSubscription();
    const deleteSubscriptionMutation = useInsightDeleteReportSubscription();
    const runSubscriptionMutation = useInsightRunReportSubscription();
    const createTemplateMutation = useInsightCreateReportTemplate();
    const cloneTemplateMutation = useInsightCloneReportTemplate();
    const publishTemplateMutation = useInsightPublishReportTemplate();
    const updateTemplateMutation = useInsightUpdateReportTemplate();
    const deleteTemplateMutation = useInsightDeleteReportTemplate();
    const uploadTemplateMutation = useInsightUploadReportTemplate();
    const updatePreferenceMutation = useInsightUpdateReportPreference();

    const templateOptions = useMemo(
        () => templates.map((template) => ({ value: template.template_code, label: template.template_name })),
        [templates],
    );

    useEffect(() => {
        if (reportIdParam && reportIdParam !== selectedReportId) {
            setSelectedReportId(reportIdParam);
        }
    }, [reportIdParam, selectedReportId]);

    useEffect(() => {
        if (!selectedReportId && reports[0]?.id) {
            setSelectedReportId(reports[0].id);
        }
    }, [reports, selectedReportId]);

    const handleSelectReport = (reportId: number) => {
        setSelectedReportId(reportId);
        const nextParams = new URLSearchParams(searchParams);
        nextParams.set("report_id", String(reportId));
        setSearchParams(nextParams, { replace: true });
    };

    const companyOptions = useMemo(
        () => [
            { value: "", label: "全部企业" },
            ...((companiesQuery.data?.items ?? []).map((company) => ({
                value: String(company.id),
                label: company.short_name || company.name,
            }))),
        ],
        [companiesQuery.data?.items],
    );
    const dataSources = useMemo(() => dataSourcesQuery.data?.items ?? [], [dataSourcesQuery.data?.items]);

    const handleTemplateChange = (value: string) => {
        setTemplateCode(value);
        const template = templates.find((item) => item.template_code === value);
        if (template) {
            setReportType(template.report_type);
            setPrompt(template.default_prompt);
        }
    };

    const applyPreference = (preference?: InsightReportPreferenceRead | null) => {
        if (!preference) return;
        if (preference.default_template_code) {
            handleTemplateChange(preference.default_template_code);
        }
        setReportType(preference.default_report_type);
        setFolderName(preference.default_folder_name || "");
        setMaxMaterials(String(preference.default_max_materials));
        if (preference.custom_prompt_suffix) {
            setPrompt(preference.custom_prompt_suffix);
        }
    };

    const handleGenerate = () => {
        generateMutation.mutate(
            {
                report_type: reportType,
                template_code: templateCode,
                company_ids: companyId ? [Number(companyId)] : [],
                data_source_ids: selectedDataSourceIds,
                folder_name: folderName || null,
                max_materials: Number(maxMaterials) || 100,
                generation_prompt: prompt,
            },
            {
                onSuccess: (response) => {
                    setSelectedReportId(response.report.id);
                    toast.success(`报告已生成，引用 ${response.used_material_count} 条素材，${reportGenerationModeLabel(response.generation_mode)}`);
                },
                onError: () => toast.error("报告生成失败，请确认报告素材池有可用情报"),
            },
        );
    };

    return (
        <PageContainer className="flex flex-col gap-4">
            <div className="insight-page-heading">
                <div>
                    <p className="text-sm font-bold text-primary">REPORT CENTER</p>
                    <h1 className="mt-1 text-2xl font-black leading-tight tracking-tight text-slate-950 md:text-3xl">报告中心</h1>
                    <p className="mt-2 text-sm leading-6 text-slate-500">按模板生成、阅读和编辑市场洞察研究报告。</p>
                </div>
                <div className="insight-actions">
                    <Button type="button" variant="outline" className="h-10 rounded-xl border-slate-200 bg-white" onClick={() => setSubscriptionDialogOpen(true)}>
                        <CalendarClock className="size-4" />
                        定时报告
                    </Button>
                    <Button type="button" variant="outline" className="h-10 rounded-xl border-slate-200 bg-white" onClick={() => void reportsQuery.refetch()}>
                        <RefreshCw className="size-4" />
                        刷新
                    </Button>
                </div>
            </div>

            <SectionCard className="p-3 md:hidden">
                <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                        <div className="text-sm font-black text-slate-900">快速生成</div>
                        <p className="mt-1 line-clamp-2 text-xs font-semibold leading-5 text-slate-500">
                            {templates.find((item) => item.template_code === templateCode)?.template_name || "客户经营洞察报告"} · {companyOptions.find((item) => item.value === companyId)?.label || "全部企业"}
                        </p>
                    </div>
                    <Button type="button" className="h-10 shrink-0 rounded-xl px-4" onClick={handleGenerate} disabled={generateMutation.isPending}>
                        {generateMutation.isPending ? <Loader2 className="size-4 animate-spin" /> : <Sparkles className="size-4" />}
                        生成报告
                    </Button>
                </div>
                <details className="mt-3 rounded-xl border border-slate-100 bg-slate-50/80 px-3 py-2">
                    <summary className="flex cursor-pointer list-none items-center justify-between gap-3 text-sm font-black text-slate-700">
                        <span className="inline-flex items-center gap-2">
                            <SlidersHorizontal className="size-4 text-slate-500" />
                            调整生成设置
                        </span>
                        <span className="text-xs font-bold text-slate-400">已选 {selectedDataSourceIds.length} 个数据源</span>
                    </summary>
                    <div className="mt-3 grid gap-3">
                        <InsightSelect label="报告模板" value={templateCode} options={templateOptions} onChange={handleTemplateChange} />
                        <InsightSelect label="报告对象" value={companyId} options={companyOptions} onChange={setCompanyId} />
                        <label className="space-y-2 text-sm font-bold text-slate-700">
                            素材池
                            <input
                                value={folderName}
                                onChange={(event) => setFolderName(event.target.value)}
                                className="h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm outline-none transition focus:border-primary"
                            />
                        </label>
                        <label className="space-y-2 text-sm font-bold text-slate-700">
                            生成要求
                            <textarea
                                value={prompt}
                                onChange={(event) => setPrompt(event.target.value)}
                                rows={3}
                                className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm outline-none transition focus:border-primary"
                            />
                        </label>
                        <div className="rounded-xl border border-slate-100 bg-white p-3">
                            <div className="flex items-center justify-between gap-2">
                                <div className="text-sm font-black text-slate-800">按数据源选材</div>
                                {selectedDataSourceIds.length ? (
                                    <Button type="button" variant="ghost" className="h-8 rounded-xl text-xs" onClick={() => setSelectedDataSourceIds([])}>
                                        清空
                                    </Button>
                                ) : null}
                            </div>
                            <div className="mt-3 flex max-h-36 flex-wrap gap-2 overflow-y-auto">
                                {dataSources.map((source) => {
                                    const checked = selectedDataSourceIds.includes(source.id);
                                    return (
                                        <button
                                            key={source.id}
                                            type="button"
                                            onClick={() => setSelectedDataSourceIds(toggleNumber(selectedDataSourceIds, source.id))}
                                            className={cn(
                                                "rounded-full border px-3 py-1.5 text-xs font-bold transition",
                                                checked ? "border-primary/40 bg-primary text-primary-foreground" : "border-slate-200 bg-white text-slate-600 hover:border-primary/30 hover:text-primary",
                                            )}
                                        >
                                            {source.source_name}
                                        </button>
                                    );
                                })}
                                {!dataSourcesQuery.isLoading && dataSources.length === 0 ? <span className="text-xs text-slate-500">暂无可选数据源。</span> : null}
                                {dataSourcesQuery.isLoading ? <span className="text-xs text-slate-500">正在读取数据源...</span> : null}
                            </div>
                        </div>
                    </div>
                </details>
            </SectionCard>

            <SectionCard className="hidden p-4 md:block">
                <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-[minmax(180px,1fr)_140px_160px_170px_110px] 2xl:grid-cols-[180px_140px_160px_170px_110px_minmax(320px,1fr)] 2xl:items-end">
                    <InsightSelect label="报告模板" value={templateCode} options={templateOptions} onChange={handleTemplateChange} />
                    <label className="space-y-2 text-sm font-bold text-slate-700">
                        报告类型
                        <input
                            value={reportType}
                            onChange={(event) => setReportType(event.target.value)}
                            className="h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm outline-none transition focus:border-primary"
                        />
                    </label>
                    <InsightSelect label="报告对象" value={companyId} options={companyOptions} onChange={setCompanyId} />
                    <label className="space-y-2 text-sm font-bold text-slate-700">
                        素材池
                        <input
                            value={folderName}
                            onChange={(event) => setFolderName(event.target.value)}
                            className="h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm outline-none transition focus:border-primary"
                        />
                    </label>
                    <label className="space-y-2 text-sm font-bold text-slate-700">
                        素材上限
                        <input
                            value={maxMaterials}
                            onChange={(event) => setMaxMaterials(event.target.value)}
                            className="h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm outline-none transition focus:border-primary"
                        />
                    </label>
                    <label className="space-y-2 text-sm font-bold text-slate-700 md:col-span-2 xl:col-span-5 2xl:col-span-1">
                        生成要求
                        <input
                            value={prompt}
                            onChange={(event) => setPrompt(event.target.value)}
                            className="h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm outline-none transition focus:border-primary"
                        />
                    </label>
                </div>
                <div className="mt-4 flex flex-col gap-3 border-t border-slate-100 pt-4 lg:flex-row lg:items-center lg:justify-between">
                    <p className="text-xs leading-5 text-slate-500">
                        生成前可先限定企业、素材池与数据源，避免报告引用范围过宽。
                    </p>
                    <div className="insight-actions">
                        <Button type="button" variant="outline" className="h-10 rounded-xl border-slate-200 bg-white" onClick={() => setTemplateDialogOpen(true)}>
                            <Settings2 className="size-4" />
                            自定义模板
                        </Button>
                        <Button type="button" variant="outline" className="h-10 rounded-xl border-slate-200 bg-white" onClick={() => setPreferenceDialogOpen(true)}>
                            <SlidersHorizontal className="size-4" />
                            生成偏好
                        </Button>
                        <Button type="button" variant="outline" className="h-10 rounded-xl border-slate-200 bg-white" onClick={() => setSubscriptionDialogOpen(true)}>
                            <CalendarClock className="size-4" />
                            定时生成
                        </Button>
                        <Button type="button" className="h-10 rounded-xl bg-primary px-5 text-primary-foreground" onClick={handleGenerate} disabled={generateMutation.isPending}>
                            {generateMutation.isPending ? <Loader2 className="size-4 animate-spin" /> : <Sparkles className="size-4" />}
                            生成报告
                        </Button>
                    </div>
                </div>
                <p className="mt-3 text-xs leading-5 text-slate-500">
                    当前模板：{templates.find((item) => item.template_code === templateCode)?.description || "用于正式市场洞察报告。"}
                </p>
                <div className="mt-4 rounded-2xl border border-slate-100 bg-slate-50/80 p-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                        <div>
                            <div className="text-sm font-black text-slate-800">按数据源选材</div>
                            <p className="mt-1 text-xs leading-5 text-slate-500">
                                可指定一个或多个已启用数据源，报告只引用这些数据源采集并入库的正式情报。当前已选 {selectedDataSourceIds.length} 个。
                            </p>
                        </div>
                        <div className="flex flex-wrap items-center gap-2">
                            {selectedDataSourceIds.length ? (
                                <Button type="button" variant="ghost" className="h-8 rounded-xl text-xs" onClick={() => setSelectedDataSourceIds([])}>
                                    清空数据源
                                </Button>
                            ) : null}
                            <Button type="button" variant="outline" className="h-8 rounded-xl border-slate-200 bg-white text-xs" onClick={() => setDataSourcePickerOpen((open) => !open)}>
                                <SlidersHorizontal className="size-3.5" />
                                {dataSourcePickerOpen ? "收起选择" : "展开选择"}
                            </Button>
                        </div>
                    </div>
                    {dataSourcePickerOpen ? (
                        <div className="mt-3 flex max-h-28 flex-wrap gap-2 overflow-y-auto">
                            {dataSources.map((source) => {
                                const checked = selectedDataSourceIds.includes(source.id);
                                return (
                                    <button
                                        key={source.id}
                                        type="button"
                                        onClick={() => setSelectedDataSourceIds(toggleNumber(selectedDataSourceIds, source.id))}
                                        className={cn(
                                            "rounded-full border px-3 py-1.5 text-xs font-bold transition",
                                            checked ? "border-primary/40 bg-primary text-primary-foreground" : "border-slate-200 bg-white text-slate-600 hover:border-primary/30 hover:text-primary",
                                        )}
                                    >
                                        {source.source_name}
                                    </button>
                                );
                            })}
                            {!dataSourcesQuery.isLoading && dataSources.length === 0 ? <span className="text-xs text-slate-500">暂无可选数据源。</span> : null}
                            {dataSourcesQuery.isLoading ? <span className="text-xs text-slate-500">正在读取数据源...</span> : null}
                        </div>
                    ) : null}
                </div>
            </SectionCard>

            <TemplateDialog
                open={templateDialogOpen}
                onOpenChange={setTemplateDialogOpen}
                templates={templates}
                currentTemplateCode={templateCode}
                currentReportType={reportType}
                currentPrompt={prompt}
                onUseTemplate={handleTemplateChange}
                onCreate={(payload) =>
                    createTemplateMutation.mutate(payload, {
                        onSuccess: (template) => {
                            toast.success("自定义模板已保存");
                            handleTemplateChange(template.template_code);
                        },
                        onError: () => toast.error("模板保存失败"),
                    })
                }
                onUpdate={(templateId, payload) =>
                    updateTemplateMutation.mutate(
                        { templateId, data: payload },
                        {
                            onSuccess: (template) => {
                                toast.success("模板已更新");
                                handleTemplateChange(template.template_code);
                            },
                            onError: () => toast.error("模板更新失败"),
                        },
                    )
                }
                onDelete={(templateId) =>
                    deleteTemplateMutation.mutate(templateId, {
                        onSuccess: () => toast.success("模板已删除"),
                        onError: () => toast.error("模板删除失败"),
                    })
                }
                onUpload={(payload) =>
                    uploadTemplateMutation.mutate(payload, {
                        onSuccess: (response) => {
                            toast.success("模板已解析并保存");
                            handleTemplateChange(response.template.template_code);
                        },
                        onError: () => toast.error("模板上传解析失败，请确认文件为 docx 或 xlsx"),
                    })
                }
                onClone={(templateCode, templateName) =>
                    cloneTemplateMutation.mutate(
                        { templateCode, data: { template_name: templateName } },
                        {
                            onSuccess: (template) => {
                                toast.success("已复制为我的模板");
                                handleTemplateChange(template.template_code);
                            },
                            onError: () => toast.error("复制模板失败"),
                        },
                    )
                }
                onPublish={(templateId, payload) =>
                    publishTemplateMutation.mutate(
                        { templateId, data: payload },
                        {
                            onSuccess: () => toast.success("模板已发布到市场"),
                            onError: () => toast.error("发布模板失败"),
                        },
                    )
                }
                saving={
                    createTemplateMutation.isPending ||
                    updateTemplateMutation.isPending ||
                    deleteTemplateMutation.isPending ||
                    uploadTemplateMutation.isPending ||
                    cloneTemplateMutation.isPending ||
                    publishTemplateMutation.isPending
                }
            />

            <PreferenceDialog
                key={`${preferenceQuery.data?.id ?? 0}-${preferenceQuery.data?.update_time ?? "default"}-${preferenceDialogOpen ? "open" : "closed"}`}
                open={preferenceDialogOpen}
                onOpenChange={setPreferenceDialogOpen}
                preference={preferenceQuery.data ?? null}
                templates={templates}
                currentTemplateCode={templateCode}
                currentReportType={reportType}
                currentFolderName={folderName}
                currentMaxMaterials={Number(maxMaterials) || 100}
                currentPrompt={prompt}
                saving={updatePreferenceMutation.isPending}
                onApply={applyPreference}
                onSave={(payload) =>
                    updatePreferenceMutation.mutate(payload, {
                        onSuccess: (preference) => {
                            toast.success("报告生成偏好已保存");
                            applyPreference(preference);
                        },
                        onError: () => toast.error("报告偏好保存失败"),
                    })
                }
            />

            <ReportSubscriptionPanel
                subscriptions={subscriptionsQuery.data?.items ?? []}
                loading={subscriptionsQuery.isLoading}
                total={subscriptionsQuery.data?.total ?? 0}
                runningId={runSubscriptionMutation.variables ?? null}
                saving={createSubscriptionMutation.isPending || updateSubscriptionMutation.isPending || deleteSubscriptionMutation.isPending}
                onCreate={() => setSubscriptionDialogOpen(true)}
                onRun={(subscription) =>
                    runSubscriptionMutation.mutate(subscription.id, {
                        onSuccess: (response) => {
                            if (response.report?.id) {
                                setSelectedReportId(response.report.id);
                            }
                            toast.success(response.message || "定时报告已执行");
                        },
                        onError: () => toast.error("定时报告执行失败，请检查素材范围和接收人"),
                    })
                }
                onToggle={(subscription) =>
                    updateSubscriptionMutation.mutate(
                        { subscriptionId: subscription.id, data: { status: subscription.status === "active" ? "paused" : "active" } },
                        {
                            onSuccess: () => toast.success(subscription.status === "active" ? "计划已暂停" : "计划已启用"),
                            onError: () => toast.error("计划状态更新失败"),
                        },
                    )
                }
                onDelete={(subscription) =>
                    deleteSubscriptionMutation.mutate(subscription.id, {
                        onSuccess: () => toast.success("定时报告计划已删除"),
                        onError: () => toast.error("计划删除失败"),
                    })
                }
            />

            <ReportSubscriptionDialog
                open={subscriptionDialogOpen}
                onOpenChange={setSubscriptionDialogOpen}
                templates={templates}
                systemCompanies={systemCompaniesQuery.data ?? []}
                companies={companiesQuery.data?.items ?? []}
                dataSources={dataSources}
                defaultTemplateCode={templateCode}
                defaultReportType={reportType}
                defaultFolderName={folderName}
                defaultMaxMaterials={Number(maxMaterials) || 100}
                defaultPrompt={prompt}
                saving={createSubscriptionMutation.isPending}
                onSubmit={(payload) =>
                    createSubscriptionMutation.mutate(payload, {
                        onSuccess: () => {
                            toast.success("定时报告计划已保存");
                            setSubscriptionDialogOpen(false);
                        },
                        onError: () => toast.error("定时报告计划保存失败，请检查范围和接收人"),
                    })
                }
            />

            <div className="grid min-h-0 min-w-0 gap-4 xl:grid-cols-[310px_minmax(0,1fr)]">
                <ReportHistoryPanel
                    keyword={keyword}
                    onKeywordChange={setKeyword}
                    reports={reports}
                    loading={reportsQuery.isLoading}
                    activeReportId={activeReportId}
                    total={reportsQuery.data?.total ?? 0}
                    onSelect={handleSelectReport}
                />
                <ReportDocument
                    key={`${reportDetail?.id ?? selectedReport?.id ?? "empty"}-${reportDetail?.version_no ?? selectedReport?.version_no ?? 0}-${reportDetailQuery.data ? "detail" : "list"}`}
                    report={reportDetail ?? null}
                    loading={reportDetailQuery.isLoading}
                    saving={updateMutation.isPending}
                    onSave={(reportId, payload) =>
                        updateMutation.mutate(
                            { reportId, data: payload },
                            {
                                onSuccess: () => toast.success("报告已保存为新版本"),
                                onError: () => toast.error("报告保存失败，请稍后重试"),
                            },
                        )
                    }
                    onOpenAccess={(target) => setReportAccessTarget(target)}
                    onOpenPush={(target) => setReportPushTarget(target)}
                    exporting={exportMutation.isPending}
                    exports={reportExportsQuery.data ?? []}
                    exportsLoading={reportExportsQuery.isLoading}
                    onExport={(reportId, exportFormat) =>
                        exportMutation.mutate(
                            { reportId, exportFormat },
                            {
                                onSuccess: ({ exportRecord, file }) => {
                                    if (exportRecord.status !== "success" || !file) {
                                        toast.error(exportRecord.error_message || "报告导出失败，请稍后重试");
                                        return;
                                    }
                                    downloadBlob(file, exportRecord.file_name || `insight-report-${reportId}.${exportFormat}`);
                                    toast.success(`报告 ${exportFormat.toUpperCase()} 已导出`);
                                },
                                onError: () => toast.error("报告导出失败，请稍后重试"),
                            },
                        )
                    }
                    onDownloadExport={(reportId, exportRecord) =>
                        insightDownloadReportExport(reportId, exportRecord).catch(() => {
                            toast.error("导出文件下载失败，请重新导出");
                        })
                    }
                />
            </div>
            <AccessRuleDialog
                open={Boolean(reportAccessTarget)}
                onOpenChange={(open) => {
                    if (!open) setReportAccessTarget(null);
                }}
                targetType="report"
                targetId={reportAccessTarget?.id ?? null}
                targetName={reportAccessTarget?.title ?? ""}
            />
            <WecomPushDialog
                open={Boolean(reportPushTarget)}
                onOpenChange={(open) => {
                    if (!open) setReportPushTarget(null);
                }}
                targetType="report"
                targetId={reportPushTarget?.id ?? null}
                targetTitle={reportPushTarget?.title ?? ""}
                defaultTitle={reportPushTarget ? `市场洞察报告：${reportPushTarget.title}` : ""}
                defaultContent={reportPushTarget?.summary || "报告已生成，请进入研发营销市场洞察平台查看正文与引用来源。"}
            />
        </PageContainer>
    );
}

function ReportSubscriptionPanel({
    subscriptions,
    loading,
    total,
    runningId,
    saving,
    onCreate,
    onRun,
    onToggle,
    onDelete,
}: {
    subscriptions: InsightReportSubscriptionRead[];
    loading: boolean;
    total: number;
    runningId: number | null;
    saving: boolean;
    onCreate: () => void;
    onRun: (subscription: InsightReportSubscriptionRead) => void;
    onToggle: (subscription: InsightReportSubscriptionRead) => void;
    onDelete: (subscription: InsightReportSubscriptionRead) => void;
}) {
    return (
        <SectionCard className="p-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                    <div className="flex items-center gap-2">
                        <CalendarClock className="size-5 text-primary" />
                        <h2 className="text-base font-black text-slate-950">定时报告计划</h2>
                    </div>
                    <p className="mt-1 text-xs font-semibold leading-5 text-slate-500">共 {total} 个计划，到点后按创建者权限自动生成报告并写入企业微信推送记录。</p>
                </div>
                <Button type="button" className="h-10 rounded-xl bg-primary text-primary-foreground" onClick={onCreate}>
                    <Plus className="size-4" />
                    新建计划
                </Button>
            </div>
            {loading ? <div className="mt-4 rounded-xl border border-slate-100 bg-slate-50 p-4 text-sm font-semibold text-slate-500">正在读取定时报告计划...</div> : null}
            {!loading && subscriptions.length === 0 ? (
                <div className="mt-4 rounded-xl border border-dashed border-slate-200 bg-slate-50/70 p-5 text-sm font-semibold text-slate-500">
                    暂无定时报告计划。可以先建一个每周周报，选择模板、范围和接收人后自动生成并推送。
                </div>
            ) : null}
            {subscriptions.length ? (
                <div className="mt-4 grid gap-3 lg:grid-cols-2">
                    {subscriptions.map((subscription) => (
                        <div key={subscription.id} className="rounded-2xl border border-slate-100 bg-white p-4 shadow-sm">
                            <div className="flex flex-wrap items-start justify-between gap-3">
                                <div className="min-w-0">
                                    <div className="flex flex-wrap items-center gap-2">
                                        <h3 className="truncate text-sm font-black text-slate-950">{subscription.subscription_name}</h3>
                                        <span className={cn("rounded-full px-2 py-0.5 text-[10px] font-black", subscription.status === "active" ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-500")}>
                                            {subscription.status === "active" ? "已启用" : "已暂停"}
                                        </span>
                                        {subscription.last_status ? (
                                            <span className={cn("rounded-full px-2 py-0.5 text-[10px] font-black", subscription.last_status === "success" ? "bg-blue-50 text-blue-700" : "bg-rose-50 text-rose-700")}>
                                                上次{subscription.last_status === "success" ? "成功" : "失败"}
                                            </span>
                                        ) : null}
                                    </div>
                                    <p className="mt-1 text-xs font-semibold leading-5 text-slate-500">
                                        {reportScheduleLabel(subscription)} · {reportScopeLabel(subscription)}
                                    </p>
                                </div>
                                <div className="flex shrink-0 items-center gap-2">
                                    <Button type="button" variant="outline" className="h-8 rounded-xl border-slate-200 bg-white text-xs" onClick={() => onRun(subscription)} disabled={runningId === subscription.id || saving}>
                                        {runningId === subscription.id ? <Loader2 className="size-3.5 animate-spin" /> : <PlayCircle className="size-3.5" />}
                                        立即执行
                                    </Button>
                                </div>
                            </div>
                            <div className="mt-3 grid gap-2 text-xs font-semibold text-slate-500 md:grid-cols-2">
                                <div>模板：{subscription.template_code || "默认模板"}</div>
                                <div>下次：{formatFullDate(subscription.next_run_time)}</div>
                                <div>接收：{subscription.wecom_recipient_scope === "all" ? "全员" : `${subscription.wecom_recipients.length} 人/对象`}</div>
                                <div>素材上限：{subscription.max_materials}</div>
                            </div>
                            {subscription.last_error ? <p className="mt-3 rounded-xl bg-rose-50 px-3 py-2 text-xs font-semibold leading-5 text-rose-700">{subscription.last_error}</p> : null}
                            <div className="mt-3 flex flex-wrap justify-end gap-2">
                                <Button type="button" variant="ghost" className="h-8 rounded-xl text-xs" onClick={() => onToggle(subscription)} disabled={saving}>
                                    {subscription.status === "active" ? "暂停" : "启用"}
                                </Button>
                                <Button type="button" variant="ghost" className="h-8 rounded-xl text-xs text-red-600 hover:bg-red-50 hover:text-red-700" onClick={() => onDelete(subscription)} disabled={saving}>
                                    删除
                                </Button>
                            </div>
                        </div>
                    ))}
                </div>
            ) : null}
        </SectionCard>
    );
}

function ReportSubscriptionDialog({
    open,
    onOpenChange,
    templates,
    systemCompanies,
    companies,
    dataSources,
    defaultTemplateCode,
    defaultReportType,
    defaultFolderName,
    defaultMaxMaterials,
    defaultPrompt,
    saving,
    onSubmit,
}: {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    templates: InsightReportTemplateRead[];
    systemCompanies: SystemCompanyOption[];
    companies: InsightCompanyListItem[];
    dataSources: InsightDataSourceRead[];
    defaultTemplateCode: string;
    defaultReportType: string;
    defaultFolderName: string;
    defaultMaxMaterials: number;
    defaultPrompt: string;
    saving: boolean;
    onSubmit: (payload: InsightReportSubscriptionCreate) => void;
}) {
    const [name, setName] = useState("市场洞察周报");
    const [templateCode, setTemplateCode] = useState(defaultTemplateCode);
    const [reportType, setReportType] = useState(defaultReportType);
    const [scopeType, setScopeType] = useState("sys_company");
    const [sysCompanyId, setSysCompanyId] = useState("");
    const [companyIds, setCompanyIds] = useState<number[]>([]);
    const [dataSourceIds, setDataSourceIds] = useState<number[]>([]);
    const [folder, setFolder] = useState(defaultFolderName);
    const [maxMaterials, setMaxMaterials] = useState(String(defaultMaxMaterials));
    const [prompt, setPrompt] = useState(defaultPrompt);
    const [frequency, setFrequency] = useState("weekly");
    const [weekday, setWeekday] = useState("0");
    const [dayOfMonth, setDayOfMonth] = useState("1");
    const [timeOfDay, setTimeOfDay] = useState("09:00");
    const [recipientScope, setRecipientScope] = useState("selected");
    const [recipientText, setRecipientText] = useState("");

    useEffect(() => {
        if (open) {
            setTemplateCode(defaultTemplateCode);
            setReportType(defaultReportType);
            setFolder(defaultFolderName);
            setMaxMaterials(String(defaultMaxMaterials));
            setPrompt(defaultPrompt);
            if (!sysCompanyId && systemCompanies[0]?.id) {
                setSysCompanyId(String(systemCompanies[0].id));
            }
        }
    }, [defaultFolderName, defaultMaxMaterials, defaultPrompt, defaultReportType, defaultTemplateCode, open, sysCompanyId, systemCompanies]);

    const templateOptions = useMemo(() => templates.map((template) => ({ value: template.template_code, label: template.template_name })), [templates]);
    const sysCompanyOptions = useMemo(
        () => systemCompanies.map((company) => ({ value: String(company.id), label: company.name })),
        [systemCompanies],
    );

    const submit = () => {
        const recipients = recipientText
            .split(/\r?\n/)
            .map((item) => item.trim())
            .filter(Boolean)
            .map((value) => ({ recipient_type: "user", recipient_name: value, wecom_userid: value }));
        if (recipientScope === "selected" && recipients.length === 0) {
            toast.error("请填写至少一个企业微信接收人");
            return;
        }
        onSubmit({
            subscription_name: name.trim() || "未命名定时报告",
            report_type: reportType,
            template_code: templateCode,
            scope_type: scopeType,
            sys_company_id: scopeType === "sys_company" && sysCompanyId ? Number(sysCompanyId) : null,
            company_ids: scopeType === "company" ? companyIds : [],
            data_source_ids: scopeType === "data_source" ? dataSourceIds : [],
            folder_name: scopeType === "material_pool" ? folder : null,
            max_materials: Number(maxMaterials) || 100,
            generation_prompt: prompt,
            schedule_frequency: frequency,
            weekday: frequency === "weekly" ? Number(weekday) : null,
            day_of_month: frequency === "monthly" ? Number(dayOfMonth) : null,
            time_of_day: timeOfDay,
            timezone: "Asia/Shanghai",
            wecom_recipient_scope: recipientScope,
            wecom_recipients: recipientScope === "all" ? [] : recipients,
            visibility_scope: "private",
            status: "active",
        });
    };

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="max-h-[88vh] overflow-y-auto rounded-2xl border-slate-200 bg-white sm:max-w-4xl">
                <DialogHeader>
                    <DialogTitle className="text-xl font-black text-slate-950">新建定时报告计划</DialogTitle>
                    <DialogDescription>选择报告模板、素材范围、企业微信接收人和生成时间，系统会按权限自动生成并推送。</DialogDescription>
                </DialogHeader>
                <div className="grid gap-4 md:grid-cols-2">
                    <TemplateField label="计划名称" value={name} onChange={setName} />
                    <InsightSelect label="报告模板" value={templateCode} options={templateOptions} onChange={setTemplateCode} />
                    <TemplateField label="报告类型" value={reportType} onChange={setReportType} />
                    <TemplateField label="素材上限" value={maxMaterials} onChange={setMaxMaterials} />
                </div>
                <div className="mt-4 rounded-2xl border border-slate-100 bg-slate-50/80 p-4">
                    <div className="text-sm font-black text-slate-800">生成范围</div>
                    <div className="mt-3 grid gap-2 md:grid-cols-4">
                        {[
                            ["material_pool", "素材池"],
                            ["sys_company", "所属公司"],
                            ["company", "指定企业"],
                            ["data_source", "指定数据源"],
                        ].map(([value, label]) => (
                            <button
                                key={value}
                                type="button"
                                onClick={() => setScopeType(value)}
                                className={cn("h-10 rounded-xl border text-sm font-black transition", scopeType === value ? "border-primary bg-primary text-primary-foreground" : "border-slate-200 bg-white text-slate-600")}
                            >
                                {label}
                            </button>
                        ))}
                    </div>
                    {scopeType === "material_pool" ? <TemplateField label="素材池名称" value={folder} onChange={setFolder} /> : null}
                    {scopeType === "sys_company" ? <InsightSelect label="所属公司" value={sysCompanyId} options={sysCompanyOptions} onChange={setSysCompanyId} /> : null}
                    {scopeType === "company" ? (
                        <div className="mt-4 flex max-h-40 flex-wrap gap-2 overflow-y-auto">
                            {companies.map((company) => {
                                const checked = companyIds.includes(company.id);
                                return (
                                    <button
                                        key={company.id}
                                        type="button"
                                        onClick={() => setCompanyIds(toggleNumber(companyIds, company.id))}
                                        className={cn("rounded-full border px-3 py-1.5 text-xs font-bold", checked ? "border-primary bg-primary text-primary-foreground" : "border-slate-200 bg-white text-slate-600")}
                                    >
                                        {company.short_name || company.name}
                                    </button>
                                );
                            })}
                        </div>
                    ) : null}
                    {scopeType === "data_source" ? (
                        <div className="mt-4 flex max-h-40 flex-wrap gap-2 overflow-y-auto">
                            {dataSources.map((source) => {
                                const checked = dataSourceIds.includes(source.id);
                                return (
                                    <button
                                        key={source.id}
                                        type="button"
                                        onClick={() => setDataSourceIds(toggleNumber(dataSourceIds, source.id))}
                                        className={cn("rounded-full border px-3 py-1.5 text-xs font-bold", checked ? "border-primary bg-primary text-primary-foreground" : "border-slate-200 bg-white text-slate-600")}
                                    >
                                        {source.source_name}
                                    </button>
                                );
                            })}
                        </div>
                    ) : null}
                </div>
                <div className="mt-4 grid gap-4 md:grid-cols-[160px_160px_160px_minmax(0,1fr)]">
                    <InsightSelect label="频率" value={frequency} options={[{ value: "daily", label: "每天" }, { value: "weekly", label: "每周" }, { value: "monthly", label: "每月" }]} onChange={setFrequency} />
                    {frequency === "weekly" ? <InsightSelect label="星期" value={weekday} options={weekdayOptions()} onChange={setWeekday} /> : null}
                    {frequency === "monthly" ? <TemplateField label="每月几号" value={dayOfMonth} onChange={setDayOfMonth} /> : null}
                    <TemplateField label="发送时间" value={timeOfDay} onChange={setTimeOfDay} />
                    <InsightSelect label="接收范围" value={recipientScope} options={[{ value: "selected", label: "指定人员" }, { value: "all", label: "全员" }]} onChange={setRecipientScope} />
                </div>
                {recipientScope === "selected" ? (
                    <TemplateTextarea label="接收人员（工号 / 企业微信 UserID / 姓名，每行一个）" value={recipientText} onChange={setRecipientText} rows={4} />
                ) : null}
                <TemplateTextarea label="生成要求" value={prompt} onChange={setPrompt} rows={4} />
                <div className="mt-6 flex justify-end gap-3">
                    <Button type="button" variant="outline" className="h-10 rounded-xl border-slate-200 bg-white" onClick={() => onOpenChange(false)}>
                        取消
                    </Button>
                    <Button type="button" className="h-10 rounded-xl bg-primary text-primary-foreground" onClick={submit} disabled={saving}>
                        {saving ? <Loader2 className="size-4 animate-spin" /> : <CalendarClock className="size-4" />}
                        保存计划
                    </Button>
                </div>
            </DialogContent>
        </Dialog>
    );
}

function ReportHistoryPanel({
    keyword,
    onKeywordChange,
    reports,
    loading,
    activeReportId,
    total,
    onSelect,
}: {
    keyword: string;
    onKeywordChange: (value: string) => void;
    reports: InsightReportListItem[];
    loading: boolean;
    activeReportId: number | null;
    total: number;
    onSelect: (id: number) => void;
}) {
    return (
        <aside className="insight-card flex min-h-[18rem] min-w-0 flex-col overflow-hidden p-0 xl:max-h-[calc(100dvh-25rem)]">
            <div className="border-b border-slate-100 p-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                    <div className="min-w-0">
                        <h2 className="text-base font-black text-slate-950">报告历史</h2>
                        <p className="mt-1 text-xs font-semibold text-slate-500">共 {total} 份，可点击切换正文</p>
                    </div>
                    <FileText className="size-5 text-primary" />
                </div>
                <label className="mt-3 flex h-10 items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 text-sm">
                    <Search className="size-4 text-slate-400" />
                    <input
                        value={keyword}
                        onChange={(event) => onKeywordChange(event.target.value)}
                        placeholder="搜索报告名称"
                        className="min-w-0 flex-1 bg-transparent outline-none placeholder:text-slate-400"
                    />
                </label>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto p-3">
                {loading ? <HistorySkeleton /> : null}
                {!loading && reports.length === 0 ? (
                    <div className="rounded-xl border border-dashed border-slate-200 p-6 text-center text-sm text-slate-500">暂无报告，先生成一份研究报告。</div>
                ) : null}
                <div className="space-y-2">
                    {reports.map((report) => (
                        <ReportHistoryItem key={report.id} report={report} active={report.id === activeReportId} onClick={() => onSelect(report.id)} />
                    ))}
                </div>
            </div>
        </aside>
    );
}

function TemplateDialog({
    open,
    onOpenChange,
    templates,
    currentTemplateCode,
    currentReportType,
    currentPrompt,
    saving,
    onUseTemplate,
    onCreate,
    onUpdate,
    onDelete,
    onUpload,
    onClone,
    onPublish,
}: {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    templates: InsightReportTemplateRead[];
    currentTemplateCode: string;
    currentReportType: string;
    currentPrompt: string;
    saving: boolean;
    onUseTemplate: (templateCode: string) => void;
    onCreate: (payload: InsightReportTemplateCreate) => void;
    onUpdate: (templateId: number, payload: Partial<InsightReportTemplateCreate>) => void;
    onDelete: (templateId: number) => void;
    onUpload: (payload: FormData) => void;
    onClone: (templateCode: string, templateName?: string | null) => void;
    onPublish: (templateId: number, payload: { market_category?: string | null; market_description?: string | null }) => void;
}) {
    const uploadInputRef = useRef<HTMLInputElement | null>(null);
    const activeTemplate = templates.find((template) => template.template_code === currentTemplateCode) ?? templates[0];
    const [selectedCode, setSelectedCode] = useState(activeTemplate?.template_code ?? "");
    const [templateTab, setTemplateTab] = useState<"market" | "mine">("market");
    const selectedTemplate = templates.find((template) => template.template_code === selectedCode) ?? activeTemplate;
    const [draftName, setDraftName] = useState(selectedTemplate?.template_name ?? "");
    const [draftDescription, setDraftDescription] = useState(selectedTemplate?.description ?? "");
    const [draftReportType, setDraftReportType] = useState(selectedTemplate?.report_type ?? currentReportType);
    const [draftPrompt, setDraftPrompt] = useState(selectedTemplate?.default_prompt || currentPrompt);
    const [draftSections, setDraftSections] = useState<InsightReportTemplateSection[]>(selectedTemplate?.sections?.length ? selectedTemplate.sections : defaultSections());
    const [accessTemplate, setAccessTemplate] = useState<InsightReportTemplateRead | null>(null);
    const marketTemplates = useMemo(() => templates.filter((template) => isMarketTemplate(template)), [templates]);
    const myTemplates = useMemo(() => templates.filter((template) => !isMarketTemplate(template)), [templates]);
    const visibleTemplates = templateTab === "market" ? marketTemplates : myTemplates;
    const currentIsMarket = selectedTemplate ? isMarketTemplate(selectedTemplate) : false;

    const resetDraft = (template: InsightReportTemplateRead | undefined) => {
        setDraftName(template?.template_name ?? "");
        setDraftDescription(template?.description ?? "");
        setDraftReportType(template?.report_type ?? currentReportType);
        setDraftPrompt(template?.default_prompt || currentPrompt);
        setDraftSections(template?.sections?.length ? template.sections : defaultSections());
    };

    const handleSelect = (templateCode: string) => {
        setSelectedCode(templateCode);
        resetDraft(templates.find((template) => template.template_code === templateCode));
    };

    const payload = (): InsightReportTemplateCreate => ({
        template_name: draftName.trim() || "未命名模板",
        description: draftDescription.trim(),
        report_type: draftReportType.trim() || "专题报告",
        default_prompt: draftPrompt.trim() || currentPrompt,
        sections: draftSections.map((section, index) => ({
            section_key: section.section_key?.trim() || `section_${index + 1}`,
            heading: section.heading?.trim() || `第 ${index + 1} 章`,
            description: section.description?.trim() || "按本章节要求组织正文。",
        })),
    });
    const handleUpload = (file: File | null) => {
        if (!file) return;
        const formData = new FormData();
        formData.append("file", file);
        formData.append("template_name", draftName.trim() || file.name.replace(/\.(docx|xlsx)$/i, ""));
        formData.append("report_type", draftReportType.trim() || "专题报告");
        formData.append("description", draftDescription.trim() || "由上传文件解析生成的报告模板");
        onUpload(formData);
        if (uploadInputRef.current) {
            uploadInputRef.current.value = "";
        }
    };

    return (
        <>
            <Dialog open={open} onOpenChange={onOpenChange}>
                <DialogContent className="max-h-[86vh] overflow-hidden rounded-2xl border-slate-200 bg-white p-0 sm:max-w-5xl">
                <DialogHeader className="border-b border-slate-100 px-6 py-5">
                        <DialogTitle className="text-xl font-black text-slate-950">报告模板市场</DialogTitle>
                        <DialogDescription>从市场模板复制为自己的模板，或把个人模板发布给团队复用。</DialogDescription>
                    <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-dashed border-slate-200 bg-slate-50/80 p-4">
                        <div>
                            <div className="text-sm font-black text-slate-800">上传 Word / Excel 模板</div>
                            <p className="mt-1 text-xs leading-5 text-slate-500">系统会解析标题、段落、表格、Sheet 和字段结构，保存成可复用报告生成模板。</p>
                            <p className="mt-1 flex items-center gap-1.5 text-xs leading-5 text-amber-700">
                                <Info className="size-3.5 shrink-0" />
                                当前真实可导出格式为 HTML / PDF / DOCX；XLSX 套版导出尚未接入。
                            </p>
                        </div>
                        <input ref={uploadInputRef} type="file" accept=".docx,.xlsx" className="hidden" onChange={(event) => handleUpload(event.target.files?.[0] ?? null)} />
                        <Button type="button" variant="outline" className="h-10 rounded-xl border-slate-200 bg-white" onClick={() => uploadInputRef.current?.click()} disabled={saving}>
                            {saving ? <Loader2 className="size-4 animate-spin" /> : <UploadCloud className="size-4" />}
                            上传并解析
                        </Button>
                    </div>
                    </DialogHeader>
                <div className="grid min-h-0 gap-0 md:grid-cols-[280px_minmax(0,1fr)]">
                    <div className="max-h-[68vh] overflow-y-auto border-r border-slate-100 p-4">
                        <div className="mb-3 grid grid-cols-2 gap-2 rounded-2xl bg-slate-100 p-1">
                            <button
                                type="button"
                                onClick={() => setTemplateTab("market")}
                                className={cn("h-9 rounded-xl text-sm font-black transition", templateTab === "market" ? "bg-white text-primary shadow-sm" : "text-slate-500")}
                            >
                                模板市场
                            </button>
                            <button
                                type="button"
                                onClick={() => setTemplateTab("mine")}
                                className={cn("h-9 rounded-xl text-sm font-black transition", templateTab === "mine" ? "bg-white text-primary shadow-sm" : "text-slate-500")}
                            >
                                我的模板
                            </button>
                        </div>
                        <div className="space-y-2">
                            {visibleTemplates.map((template) => (
                                <button
                                    key={template.template_code}
                                    type="button"
                                    onClick={() => handleSelect(template.template_code)}
                                    className={cn(
                                        "w-full rounded-xl border p-3 text-left transition",
                                        template.template_code === selectedCode ? "border-primary/30 bg-blue-50" : "border-transparent hover:bg-slate-50",
                                    )}
                                >
                                    <div className="flex flex-wrap items-center justify-between gap-2">
                                        <div className="min-w-0 text-sm font-black text-slate-950">{template.template_name}</div>
                                        <span className="shrink-0 rounded-full bg-slate-100 px-2 py-1 text-[11px] font-bold text-slate-500">
                                            {templateBadge(template)}
                                        </span>
                                    </div>
                                    <div className="mt-2 flex flex-wrap gap-1.5">
                                        <span className="rounded-full bg-blue-50 px-2 py-0.5 text-[10px] font-black text-blue-700">{templateKindLabel(template.template_kind)}</span>
                                        <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-black text-emerald-700">
                                            {templateExportCapabilityLabel(template)}
                                        </span>
                                        {templatePlannedCapabilityLabel(template) ? (
                                            <span className="rounded-full bg-amber-50 px-2 py-0.5 text-[10px] font-black text-amber-700">{templatePlannedCapabilityLabel(template)}</span>
                                        ) : null}
                                    </div>
                                    <p className="mt-1 line-clamp-2 text-xs leading-5 text-slate-500">{template.description || template.default_prompt}</p>
                                </button>
                            ))}
                            {visibleTemplates.length === 0 ? (
                                <div className="rounded-xl border border-dashed border-slate-200 p-6 text-center text-sm font-semibold text-slate-500">
                                    {templateTab === "market" ? "暂无市场模板。" : "暂无个人模板，可先从市场复制或另存为自定义模板。"}
                                </div>
                            ) : null}
                        </div>
                    </div>
                    <div className="max-h-[68vh] overflow-y-auto p-5">
                        <div className="mb-4 grid gap-3 rounded-2xl border border-slate-200 bg-slate-50/80 p-4 md:grid-cols-3">
                            <TemplateMeta label="模板归属" value={currentIsMarket ? "模板市场" : selectedTemplate?.editable ? "我的模板" : "系统模板"} />
                            <TemplateMeta label="模板类型" value={templateKindLabel(selectedTemplate?.template_kind)} />
                            <TemplateMeta label="真实导出" value={templateExportCapabilityLabel(selectedTemplate)} />
                        </div>
                        {templatePlannedCapabilityLabel(selectedTemplate) ? (
                            <div className="mb-4 rounded-2xl border border-amber-100 bg-amber-50/70 px-4 py-3 text-xs font-semibold leading-5 text-amber-800">
                                {templatePlannedCapabilityLabel(selectedTemplate)}。当前上传模板会参与章节结构和 Prompt 生成，不会直接按原文件套版导出。
                            </div>
                        ) : null}
                        <div className="grid gap-4 md:grid-cols-2">
                            <TemplateField label="模板名称" value={draftName} onChange={setDraftName} />
                            <TemplateField label="报告类型" value={draftReportType} onChange={setDraftReportType} />
                        </div>
                        <TemplateTextarea label="模板说明" value={draftDescription} onChange={setDraftDescription} rows={3} />
                        <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
                            <h3 className="text-sm font-black text-slate-700">默认 Prompt</h3>
                            <Button
                                type="button"
                                variant="outline"
                                className="h-8 rounded-xl border-slate-200 bg-white text-xs"
                                onClick={() => {
                                    setDraftReportType(currentReportType);
                                    setDraftPrompt(currentPrompt);
                                }}
                            >
                                使用当前生成栏内容
                            </Button>
                        </div>
                        <TemplateTextarea label="" value={draftPrompt} onChange={setDraftPrompt} rows={5} />
                        <div className="mt-5 space-y-3">
                            <div className="flex flex-wrap items-center justify-between gap-3">
                                <h3 className="text-sm font-black text-slate-700">章节结构</h3>
                                <Button
                                    type="button"
                                    variant="outline"
                                    className="h-9 rounded-xl border-slate-200 bg-white"
                                    onClick={() => setDraftSections([...draftSections, { section_key: `section_${draftSections.length + 1}`, heading: "新增章节", description: "" }])}
                                >
                                    <Plus className="size-4" />
                                    新增章节
                                </Button>
                            </div>
                            {draftSections.map((section, index) => (
                                <div key={`${section.section_key}-${index}`} className="grid gap-3 rounded-xl border border-slate-200 p-3 md:grid-cols-[150px_minmax(0,1fr)_minmax(0,1.2fr)_auto]">
                                    <input
                                        value={section.section_key}
                                        onChange={(event) => setDraftSections(updateTemplateSection(draftSections, index, { section_key: event.target.value }))}
                                        className="h-10 rounded-xl border border-slate-200 px-3 text-sm outline-none focus:border-primary"
                                        placeholder="section_key"
                                    />
                                    <input
                                        value={section.heading}
                                        onChange={(event) => setDraftSections(updateTemplateSection(draftSections, index, { heading: event.target.value }))}
                                        className="h-10 rounded-xl border border-slate-200 px-3 text-sm outline-none focus:border-primary"
                                        placeholder="章节标题"
                                    />
                                    <input
                                        value={section.description}
                                        onChange={(event) => setDraftSections(updateTemplateSection(draftSections, index, { description: event.target.value }))}
                                        className="h-10 rounded-xl border border-slate-200 px-3 text-sm outline-none focus:border-primary"
                                        placeholder="章节要求"
                                    />
                                    <Button
                                        type="button"
                                        variant="ghost"
                                        size="icon"
                                        className="size-10 rounded-xl text-red-500 hover:bg-red-50 hover:text-red-600"
                                        onClick={() => setDraftSections(draftSections.filter((_section, currentIndex) => currentIndex !== index))}
                                    >
                                        <Trash2 className="size-4" />
                                    </Button>
                                </div>
                            ))}
                        </div>
                        <div className="mt-6 flex flex-col gap-3 border-t border-slate-100 pt-4 2xl:flex-row 2xl:items-center 2xl:justify-between">
                            <div className="insight-action-cluster justify-start">
                                <Button type="button" variant="outline" className="h-10 rounded-xl border-slate-200 bg-white" onClick={() => selectedTemplate && onUseTemplate(selectedTemplate.template_code)}>
                                    使用此模板
                                </Button>
                                {currentIsMarket && selectedTemplate ? (
                                    <Button
                                        type="button"
                                        variant="outline"
                                        className="h-10 rounded-xl border-slate-200 bg-white text-blue-700"
                                        onClick={() => onClone(selectedTemplate.template_code, `${selectedTemplate.template_name} 副本`)}
                                        disabled={saving}
                                    >
                                        <Copy className="size-4" />
                                        复制为我的模板
                                    </Button>
                                ) : null}
                                {selectedTemplate?.editable && selectedTemplate.id && selectedTemplate.market_status !== "listed" ? (
                                    <Button
                                        type="button"
                                        variant="outline"
                                        className="h-10 rounded-xl border-emerald-100 bg-white text-emerald-700 hover:bg-emerald-50 hover:text-emerald-800"
                                        onClick={() =>
                                            onPublish(selectedTemplate.id ?? 0, {
                                                market_category: selectedTemplate.market_category || "用户模板",
                                                market_description: draftDescription || selectedTemplate.description || draftPrompt,
                                            })
                                        }
                                        disabled={saving}
                                    >
                                        <Send className="size-4" />
                                        发布到市场
                                    </Button>
                                ) : null}
                                {selectedTemplate?.editable && selectedTemplate.id ? (
                                    <Button
                                        type="button"
                                        variant="outline"
                                        className="h-10 rounded-xl border-slate-200 bg-white text-blue-700"
                                        onClick={() => setAccessTemplate(selectedTemplate)}
                                        disabled={saving}
                                    >
                                        <ShieldCheck className="size-4" />
                                        模板权限
                                    </Button>
                                ) : null}
                                {selectedTemplate?.editable && selectedTemplate.id ? (
                                    <Button
                                        type="button"
                                        variant="outline"
                                        className="h-10 rounded-xl border-red-100 bg-white text-red-600 hover:bg-red-50 hover:text-red-700"
                                        onClick={() => onDelete(selectedTemplate.id ?? 0)}
                                        disabled={saving}
                                    >
                                        <Trash2 className="size-4" />
                                        删除
                                    </Button>
                                ) : null}
                            </div>
                            <div className="insight-action-cluster">
                                {selectedTemplate?.editable && selectedTemplate.id ? (
                                    <Button type="button" className="h-10 rounded-xl bg-primary text-primary-foreground" onClick={() => onUpdate(selectedTemplate.id ?? 0, payload())} disabled={saving}>
                                        {saving ? <Loader2 className="size-4 animate-spin" /> : <Save className="size-4" />}
                                        更新模板
                                    </Button>
                                ) : null}
                                <Button type="button" className="h-10 rounded-xl bg-primary text-primary-foreground" onClick={() => onCreate(payload())} disabled={saving}>
                                    {saving ? <Loader2 className="size-4 animate-spin" /> : <Plus className="size-4" />}
                                    另存为自定义模板
                                </Button>
                            </div>
                        </div>
                    </div>
                </div>
                </DialogContent>
            </Dialog>
            <AccessRuleDialog
                open={Boolean(accessTemplate)}
                onOpenChange={(nextOpen) => {
                    if (!nextOpen) setAccessTemplate(null);
                }}
                targetType="report_template"
                targetId={accessTemplate?.id ?? null}
                targetName={accessTemplate?.template_name ?? ""}
            />
        </>
    );
}

function TemplateField({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
    return (
        <label className="block space-y-2 text-sm font-bold text-slate-700">
            {label}
            <input
                value={value}
                onChange={(event) => onChange(event.target.value)}
                className="h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm outline-none transition focus:border-primary"
            />
        </label>
    );
}

function TemplateMeta({ label, value }: { label: string; value: string }) {
    return (
        <div>
            <div className="text-xs font-bold text-slate-500">{label}</div>
            <div className="mt-1 text-sm font-black text-slate-900">{value || "-"}</div>
        </div>
    );
}

function TemplateTextarea({ label, value, onChange, rows }: { label: string; value: string; onChange: (value: string) => void; rows: number }) {
    return (
        <label className="mt-4 block space-y-2 text-sm font-bold text-slate-700">
            {label ? <span>{label}</span> : null}
            <textarea
                value={value}
                onChange={(event) => onChange(event.target.value)}
                rows={rows}
                className="w-full resize-y rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm leading-7 text-slate-800 outline-none transition focus:border-primary"
            />
        </label>
    );
}

function isMarketTemplate(template: InsightReportTemplateRead) {
    return template.scope === "market" || template.market_status === "listed";
}

function templateBadge(template: InsightReportTemplateRead) {
    if (isMarketTemplate(template)) return "市场";
    if (template.editable) return "我的";
    return "系统";
}

function templateKindLabel(value?: string) {
    if (value === "html") return "HTML 风格";
    if (value === "spreadsheet") return "表格模板";
    if (value === "document") return "文档模板";
    return "文档模板";
}

function templateExportCapabilityLabel(template?: InsightReportTemplateRead | null) {
    const formats = template?.export_formats?.filter((format) => ["html", "pdf", "docx"].includes(format.toLowerCase())) ?? [];
    return formats.length ? formats.join(" / ").toUpperCase() : "HTML / PDF / DOCX";
}

function templatePlannedCapabilityLabel(template?: InsightReportTemplateRead | null) {
    if (!template) return "";
    const plannedFormats = (template.export_formats ?? []).filter((format) => !["html", "pdf", "docx"].includes(format.toLowerCase()));
    if (template.source_file_type) {
        return `${template.source_file_type.toUpperCase()} 套版导出待接入`;
    }
    if (plannedFormats.length) {
        return `${plannedFormats.join(" / ").toUpperCase()} 待接入`;
    }
    return "";
}

function reportGenerationModeLabel(mode?: string | null) {
    if (mode === "llm") return "AI 生成";
    if (mode === "rules") return "证据草稿";
    return "库内证据";
}

function reportScheduleLabel(subscription: InsightReportSubscriptionRead) {
    if (subscription.schedule_frequency === "daily") return `每天 ${subscription.time_of_day}`;
    if (subscription.schedule_frequency === "monthly") return `每月 ${subscription.day_of_month ?? 1} 号 ${subscription.time_of_day}`;
    return `${weekdayName(subscription.weekday ?? 0)} ${subscription.time_of_day}`;
}

function reportScopeLabel(subscription: InsightReportSubscriptionRead) {
    if (subscription.scope_type === "sys_company") return "所属公司全部企业";
    if (subscription.scope_type === "company") return `指定 ${subscription.company_ids.length} 家企业`;
    if (subscription.scope_type === "data_source") return `指定 ${subscription.data_source_ids.length} 个数据源`;
    return `素材池：${subscription.folder_name || "默认素材池"}`;
}

function weekdayOptions() {
    return [
        { value: "0", label: "周一" },
        { value: "1", label: "周二" },
        { value: "2", label: "周三" },
        { value: "3", label: "周四" },
        { value: "4", label: "周五" },
        { value: "5", label: "周六" },
        { value: "6", label: "周日" },
    ];
}

function weekdayName(value: number) {
    return weekdayOptions().find((item) => item.value === String(value))?.label ?? "周一";
}

function exportStatusLabel(status: string) {
    const labels: Record<string, string> = {
        pending: "等待中",
        running: "导出中",
        success: "成功",
        failed: "失败",
    };
    return labels[status] ?? status;
}

function exportStatusClass(status: string) {
    if (status === "success") return "bg-emerald-50 text-emerald-700";
    if (status === "failed") return "bg-rose-50 text-rose-700";
    if (status === "running") return "bg-blue-50 text-blue-700";
    return "bg-slate-100 text-slate-500";
}

function PreferenceDialog({
    open,
    onOpenChange,
    preference,
    templates,
    currentTemplateCode,
    currentReportType,
    currentFolderName,
    currentMaxMaterials,
    currentPrompt,
    saving,
    onApply,
    onSave,
}: {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    preference: InsightReportPreferenceRead | null;
    templates: InsightReportTemplateRead[];
    currentTemplateCode: string;
    currentReportType: string;
    currentFolderName: string;
    currentMaxMaterials: number;
    currentPrompt: string;
    saving: boolean;
    onApply: (preference: InsightReportPreferenceRead | null) => void;
    onSave: (payload: InsightReportPreferenceUpdate) => void;
}) {
    const [defaultTemplateCode, setDefaultTemplateCode] = useState(preference?.default_template_code || currentTemplateCode);
    const [defaultReportType, setDefaultReportType] = useState(preference?.default_report_type || currentReportType);
    const [defaultFolderName, setDefaultFolderName] = useState(preference?.default_folder_name || currentFolderName);
    const [defaultMaxMaterials, setDefaultMaxMaterials] = useState(String(preference?.default_max_materials || currentMaxMaterials));
    const [writingStance, setWritingStance] = useState(preference?.writing_stance || "客户经营视角");
    const [reportDepth, setReportDepth] = useState(preference?.report_depth || "深度研究");
    const [citationStyle, setCitationStyle] = useState(preference?.citation_style || "正文上标引用");
    const [includeRisks, setIncludeRisks] = useState(preference?.include_risks ?? true);
    const [includeOpportunities, setIncludeOpportunities] = useState(preference?.include_opportunities ?? true);
    const [includeFollowUpQuestions, setIncludeFollowUpQuestions] = useState(preference?.include_follow_up_questions ?? true);
    const [customPromptSuffix, setCustomPromptSuffix] = useState(preference?.custom_prompt_suffix || currentPrompt);

    const templateOptions = useMemo(
        () => templates.map((template) => ({ value: template.template_code, label: template.template_name })),
        [templates],
    );

    const payload = (): InsightReportPreferenceUpdate => ({
        default_template_code: defaultTemplateCode,
        default_report_type: defaultReportType,
        default_folder_name: defaultFolderName,
        default_max_materials: Number(defaultMaxMaterials) || 100,
        writing_stance: writingStance,
        report_depth: reportDepth,
        citation_style: citationStyle,
        include_risks: includeRisks,
        include_opportunities: includeOpportunities,
        include_follow_up_questions: includeFollowUpQuestions,
        custom_prompt_suffix: customPromptSuffix,
    });

    const applyDraft = () => {
        onApply({
            id: preference?.id ?? 0,
            user_id: preference?.user_id ?? 0,
            default_template_code: defaultTemplateCode,
            default_report_type: defaultReportType,
            default_folder_name: defaultFolderName,
            default_max_materials: Number(defaultMaxMaterials) || 100,
            writing_stance: writingStance,
            report_depth: reportDepth,
            citation_style: citationStyle,
            include_risks: includeRisks,
            include_opportunities: includeOpportunities,
            include_follow_up_questions: includeFollowUpQuestions,
            custom_prompt_suffix: customPromptSuffix,
            status: "active",
            create_time: preference?.create_time ?? "",
            update_time: preference?.update_time ?? "",
        });
    };

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="max-h-[86vh] overflow-y-auto rounded-2xl border-slate-200 bg-white sm:max-w-3xl">
                <DialogHeader>
                    <DialogTitle className="text-xl font-black text-slate-950">报告生成偏好</DialogTitle>
                    <DialogDescription>保存常用生成默认值，下次做报告时不用反复调整。</DialogDescription>
                </DialogHeader>
                <div className="grid gap-4 md:grid-cols-2">
                    <InsightSelect label="默认模板" value={defaultTemplateCode} options={templateOptions} onChange={setDefaultTemplateCode} />
                    <TemplateField label="默认报告类型" value={defaultReportType} onChange={setDefaultReportType} />
                    <TemplateField label="默认素材池" value={defaultFolderName} onChange={setDefaultFolderName} />
                    <TemplateField label="默认素材上限" value={defaultMaxMaterials} onChange={setDefaultMaxMaterials} />
                    <PreferenceSelect label="写作立场" value={writingStance} options={["客户经营视角", "销售跟进视角", "行业研究视角", "风险预警视角"]} onChange={setWritingStance} />
                    <PreferenceSelect label="报告深度" value={reportDepth} options={["简版", "标准", "深度研究"]} onChange={setReportDepth} />
                    <PreferenceSelect label="引用方式" value={citationStyle} options={["正文上标引用", "章节末引用", "参考文献列表"]} onChange={setCitationStyle} />
                </div>
                <div className="mt-5 grid gap-3 md:grid-cols-3">
                    <PreferenceToggle label="包含风险提醒" checked={includeRisks} onChange={setIncludeRisks} />
                    <PreferenceToggle label="包含机会建议" checked={includeOpportunities} onChange={setIncludeOpportunities} />
                    <PreferenceToggle label="包含后续问题" checked={includeFollowUpQuestions} onChange={setIncludeFollowUpQuestions} />
                </div>
                <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
                    <h3 className="text-sm font-black text-slate-700">附加 Prompt</h3>
                    <Button
                        type="button"
                        variant="outline"
                        className="h-8 rounded-xl border-slate-200 bg-white text-xs"
                        onClick={() => {
                            setDefaultTemplateCode(currentTemplateCode);
                            setDefaultReportType(currentReportType);
                            setDefaultFolderName(currentFolderName);
                            setDefaultMaxMaterials(String(currentMaxMaterials));
                            setCustomPromptSuffix(currentPrompt);
                        }}
                    >
                        使用当前生成栏内容
                    </Button>
                </div>
                <TemplateTextarea label="" value={customPromptSuffix} onChange={setCustomPromptSuffix} rows={5} />
                <div className="mt-6 flex flex-wrap justify-between gap-3">
                    <Button type="button" variant="outline" className="h-10 rounded-xl border-slate-200 bg-white" onClick={applyDraft}>
                        应用到生成栏
                    </Button>
                    <Button type="button" className="h-10 rounded-xl bg-primary text-primary-foreground" onClick={() => onSave(payload())} disabled={saving}>
                        {saving ? <Loader2 className="size-4 animate-spin" /> : <Save className="size-4" />}
                        保存偏好
                    </Button>
                </div>
            </DialogContent>
        </Dialog>
    );
}

function PreferenceSelect({ label, value, options, onChange }: { label: string; value: string; options: string[]; onChange: (value: string) => void }) {
    return <InsightSelect label={label} value={value} options={options.map((option) => ({ value: option, label: option }))} onChange={onChange} />;
}

function PreferenceToggle({ label, checked, onChange }: { label: string; checked: boolean; onChange: (value: boolean) => void }) {
    return (
        <label className="flex h-11 items-center justify-between rounded-xl border border-slate-200 bg-white px-3 text-sm font-bold text-slate-700">
            {label}
            <input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} className="size-4 accent-primary" />
        </label>
    );
}

function ExportHistoryPanel({
    reportId,
    exports,
    loading,
    exporting,
    onRetry,
    onDownload,
}: {
    reportId: number;
    exports: InsightReportExportRead[];
    loading: boolean;
    exporting: boolean;
    onRetry: (reportId: number, exportRecord: InsightReportExportRead) => void;
    onDownload: (reportId: number, exportRecord: InsightReportExportRead) => void;
}) {
    const recentExports = exports.slice(0, 3);
    const latestExport = recentExports[0];
    return (
        <div className="mx-auto mb-4 max-w-[920px] rounded-2xl border border-slate-200 bg-white/90 p-3 shadow-sm">
            <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                    <div className="text-xs font-black text-slate-700">导出历史</div>
                    <p className="mt-1 text-xs text-slate-500">{loading ? "正在读取导出记录" : recentExports.length ? "最近导出记录可下载或重试" : "暂无导出记录"}</p>
                </div>
                <Button
                    type="button"
                    variant="outline"
                    className="h-8 rounded-xl border-slate-200 bg-white text-xs"
                    onClick={() => latestExport && onRetry(reportId, latestExport)}
                    disabled={exporting || !latestExport}
                >
                    {exporting ? <Loader2 className="size-3.5 animate-spin" /> : <Download className="size-3.5" />}
                    重新导出
                </Button>
            </div>
            {recentExports.length ? (
                <div className="mt-3 space-y-2">
                    {recentExports.map((item) => (
                        <div key={item.id} className="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-slate-50 px-3 py-2">
                            <div className="min-w-0">
                                <div className="flex flex-wrap items-center gap-2 text-xs font-bold text-slate-700">
                                    <span>{item.export_format.toUpperCase()}</span>
                                    <span className={cn("rounded-full px-2 py-0.5 text-[10px] font-black", exportStatusClass(item.status))}>{exportStatusLabel(item.status)}</span>
                                    <span className="text-slate-400">v{item.report_version_no}</span>
                                    <span className="text-slate-400">{formatFullDate(item.finished_at || item.create_time)}</span>
                                </div>
                                {item.status === "failed" && item.error_message ? <p className="mt-1 line-clamp-1 text-xs text-rose-600">{item.error_message}</p> : null}
                            </div>
                            <div className="flex items-center gap-2">
                                {item.status === "success" ? (
                                    <Button type="button" variant="ghost" className="h-8 rounded-xl px-2 text-xs text-violet-700" onClick={() => onDownload(reportId, item)}>
                                        <Download className="size-3.5" />
                                        下载
                                    </Button>
                                ) : null}
                                {item.status === "failed" ? (
                                    <Button type="button" variant="ghost" className="h-8 rounded-xl px-2 text-xs text-rose-700" onClick={() => onRetry(reportId, item)} disabled={exporting}>
                                        {exporting ? <Loader2 className="size-3.5 animate-spin" /> : <RefreshCw className="size-3.5" />}
                                        重试
                                    </Button>
                                ) : null}
                            </div>
                        </div>
                    ))}
                </div>
            ) : null}
        </div>
    );
}

function ReportDocument({
    report,
    loading,
    saving,
    exporting,
    exports,
    exportsLoading,
    onSave,
    onOpenAccess,
    onOpenPush,
    onExport,
    onDownloadExport,
}: {
    report: ReturnType<typeof useInsightReportDetail>["data"] | InsightReportListItem | null;
    loading: boolean;
    saving: boolean;
    exporting: boolean;
    exports: InsightReportExportRead[];
    exportsLoading: boolean;
    onSave: (reportId: number, payload: { title: string; summary: string; content_json: InsightReportContent; change_summary: string }) => void;
    onOpenAccess: (report: ReportDetail | InsightReportListItem) => void;
    onOpenPush: (report: ReportDetail | InsightReportListItem) => void;
    onExport: (reportId: number, exportFormat: ReportExportFormat) => void;
    onDownloadExport: (reportId: number, exportRecord: InsightReportExportRead) => void;
}) {
    const initialContent = report?.content_json ?? {};
    const [editing, setEditing] = useState(false);
    const [draftTitle, setDraftTitle] = useState(report?.title ?? "");
    const [draftSummary, setDraftSummary] = useState(stringValue(initialContent.executive_summary) || report?.summary || "");
    const [draftConclusion, setDraftConclusion] = useState(stringValue(initialContent.conclusion));
    const [draftChapters, setDraftChapters] = useState<InsightReportChapter[]>(asChapters(initialContent.chapters));

    if (loading) {
        return (
            <div className="insight-card flex min-h-[20rem] items-center justify-center text-sm text-slate-500 lg:min-h-[32rem]">
                <Loader2 className="mr-2 size-4 animate-spin" />
                正在读取报告
            </div>
        );
    }
    if (!report) {
        return <div className="insight-card flex min-h-[20rem] items-center justify-center text-sm text-slate-500 lg:min-h-[32rem]">还没有可预览的报告。</div>;
    }

    const content = report.content_json ?? {};
    const detail = "materials" in report ? report : null;
    const materials = detail?.materials ?? [];
    const charts = detail?.charts ?? [];
    const materialMap = new Map(materials.map((material) => [material.intelligence_id, material]));
    const chapters = asChapters(content.chapters);
    const companySections = asCompanySections(content.company_sections);
    const findings = asFindings(content.key_findings);
    const risks = asFindings(content.risks);
    const opportunities = asFindings(content.opportunities);
    const generatedAt = formatFullDate(report.update_time || report.create_time);

    const handleSave = () => {
        const nextContent: InsightReportContent = {
            ...content,
            title: draftTitle,
            executive_summary: draftSummary,
            chapters: draftChapters.map((chapter) => ({
                ...chapter,
                heading: chapter.heading?.trim(),
                paragraphs: (chapter.paragraphs ?? []).map((paragraph) => paragraph.trim()).filter(Boolean),
            })),
            conclusion: draftConclusion,
        };
        onSave(report.id, {
            title: draftTitle,
            summary: draftSummary,
            content_json: nextContent,
            change_summary: "人工编辑报告正文",
        });
        setEditing(false);
    };

    return (
        <article className="min-h-0 min-w-0 overflow-y-auto rounded-2xl border border-slate-200 bg-slate-100/60 px-3 py-4 shadow-sm xl:max-h-[calc(100dvh-25rem)] sm:px-4 sm:py-6">
            <div className="mx-auto mb-4 flex max-w-[920px] flex-wrap items-center justify-between gap-3">
                <div className="text-xs font-semibold text-slate-500">
                    {content.template_name ? `模板：${content.template_name}` : "Word 式报告"}
                    <span className="mx-2 text-slate-300">/</span>
                    第 {report.version_no} 版
                    {typeof content.generation_mode === "string" ? (
                        <>
                            <span className="mx-2 text-slate-300">/</span>
                            {reportGenerationModeLabel(content.generation_mode)}
                        </>
                    ) : null}
                </div>
                <div className="insight-actions">
                    {editing ? (
                        <>
                            <Button type="button" variant="outline" className="h-9 rounded-xl border-slate-200 bg-white" onClick={() => setEditing(false)} disabled={saving}>
                                <X className="size-4" />
                                取消
                            </Button>
                            <Button type="button" className="h-9 rounded-xl bg-primary text-primary-foreground" onClick={handleSave} disabled={saving}>
                                {saving ? <Loader2 className="size-4 animate-spin" /> : <Save className="size-4" />}
                                保存版本
                            </Button>
                        </>
                    ) : (
                        <>
                            <Button type="button" variant="outline" className="h-9 rounded-xl border-slate-200 bg-white text-blue-700" onClick={() => onOpenAccess(report)}>
                                <ShieldCheck className="size-4" />
                                权限
                            </Button>
                            <Button type="button" variant="outline" className="h-9 rounded-xl border-slate-200 bg-white text-emerald-700" onClick={() => onOpenPush(report)}>
                                <Send className="size-4" />
                                企微推送
                            </Button>
                            <Button type="button" variant="outline" className="h-9 rounded-xl border-slate-200 bg-white text-violet-700" onClick={() => onExport(report.id, "html")} disabled={exporting}>
                                {exporting ? <Loader2 className="size-4 animate-spin" /> : <Download className="size-4" />}
                                导出 HTML
                            </Button>
                            <Button type="button" variant="outline" className="h-9 rounded-xl border-slate-200 bg-white text-emerald-700" onClick={() => onExport(report.id, "pdf")} disabled={exporting}>
                                {exporting ? <Loader2 className="size-4 animate-spin" /> : <Download className="size-4" />}
                                导出 PDF
                            </Button>
                            <Button type="button" variant="outline" className="h-9 rounded-xl border-slate-200 bg-white text-sky-700" onClick={() => onExport(report.id, "docx")} disabled={exporting}>
                                {exporting ? <Loader2 className="size-4 animate-spin" /> : <Download className="size-4" />}
                                导出 DOCX
                            </Button>
                            <Button type="button" variant="outline" className="h-9 rounded-xl border-slate-200 bg-white" onClick={() => setEditing(true)}>
                                <Pencil className="size-4" />
                                编辑报告
                            </Button>
                        </>
                    )}
                </div>
            </div>

            <ExportHistoryPanel
                reportId={report.id}
                exports={exports}
                loading={exportsLoading}
                exporting={exporting}
                onRetry={(reportId, exportRecord) => onExport(reportId, normalizeExportFormat(exportRecord.export_format))}
                onDownload={onDownloadExport}
            />

            <div className="mx-auto min-h-[36rem] max-w-[920px] bg-white px-4 py-8 shadow-[0_18px_60px_rgba(15,23,42,0.10)] sm:px-10 sm:py-12 xl:min-h-[56rem] xl:px-14 xl:py-16">
                {editing ? (
                    <ReportEditor
                        title={draftTitle}
                        summary={draftSummary}
                        conclusion={draftConclusion}
                        chapters={draftChapters}
                        onTitleChange={setDraftTitle}
                        onSummaryChange={setDraftSummary}
                        onConclusionChange={setDraftConclusion}
                        onChaptersChange={setDraftChapters}
                    />
                ) : (
                    <>
                        <header className="border-b border-slate-200 pb-10 text-center">
                            <div className="text-sm font-semibold text-slate-500">{report.report_type}</div>
                            <h2 className="mt-6 text-3xl font-black leading-tight tracking-tight text-slate-950">{report.title}</h2>
                            <div className="mt-6 flex flex-wrap justify-center gap-x-6 gap-y-2 text-xs font-semibold text-slate-500">
                                <span>版本：第 {report.version_no} 版</span>
                                <span>素材：{report.material_count} 条</span>
                                <span>更新：{generatedAt}</span>
                            </div>
                        </header>

                        <WordSection title="摘要">
                            <ReportParagraph text={content.executive_summary || report.summary || "暂无摘要。"} evidenceIds={firstEvidenceIds(materials, 3)} materialMap={materialMap} />
                        </WordSection>

                        {chapters.length > 0 ? (
                            chapters.map((chapter, index) => (
                                <WordSection key={`${chapter.heading}-${index}`} title={chapter.heading || sectionTitle(index)}>
                                    {(chapter.paragraphs?.length ? chapter.paragraphs : ["暂无正文。"]).map((paragraph, paragraphIndex) => (
                                        <ReportParagraph
                                            key={`${chapter.heading}-${paragraphIndex}`}
                                            text={paragraph}
                                            evidenceIds={chapter.evidence_ids?.length ? chapter.evidence_ids : firstEvidenceIds(materials, 2, index * 3)}
                                            materialMap={materialMap}
                                        />
                                    ))}
                                </WordSection>
                            ))
                        ) : (
                            <FallbackReportBody
                                companySections={companySections}
                                findings={findings}
                                risks={risks}
                                opportunities={opportunities}
                                materials={materials}
                                materialMap={materialMap}
                            />
                        )}

                        <WordSection title="结论与建议">
                            <ReportParagraph text={stringValue(content.conclusion) || buildConclusion(findings, opportunities, risks)} evidenceIds={firstEvidenceIds(materials, 4, 8)} materialMap={materialMap} />
                        </WordSection>

                        {charts.length > 0 ? <ReportChartsAppendix charts={charts} /> : null}

                        <WordSection title="参考资料">
                            <ReferenceList materials={materials} />
                        </WordSection>
                    </>
                )}
            </div>
        </article>
    );
}

function ReportEditor({
    title,
    summary,
    conclusion,
    chapters,
    onTitleChange,
    onSummaryChange,
    onConclusionChange,
    onChaptersChange,
}: {
    title: string;
    summary: string;
    conclusion: string;
    chapters: InsightReportChapter[];
    onTitleChange: (value: string) => void;
    onSummaryChange: (value: string) => void;
    onConclusionChange: (value: string) => void;
    onChaptersChange: (value: InsightReportChapter[]) => void;
}) {
    const updateChapter = (index: number, patch: Partial<InsightReportChapter>) => {
        onChaptersChange(chapters.map((chapter, currentIndex) => (currentIndex === index ? { ...chapter, ...patch } : chapter)));
    };

    return (
        <div className="space-y-8">
            <label className="block space-y-2">
                <span className="text-sm font-black text-slate-700">报告标题</span>
                <input
                    value={title}
                    onChange={(event) => onTitleChange(event.target.value)}
                    className="w-full border-0 border-b border-slate-200 px-0 py-3 text-3xl font-black leading-tight text-slate-950 outline-none focus:border-primary"
                />
            </label>
            <EditorTextarea label="摘要" value={summary} onChange={onSummaryChange} minRows={5} />
            <div className="space-y-5">
                <div className="flex flex-wrap items-center justify-between gap-3">
                    <h3 className="text-lg font-black text-slate-950">正文章节</h3>
                    <Button
                        type="button"
                        variant="outline"
                        className="h-9 rounded-xl border-slate-200 bg-white"
                        onClick={() => onChaptersChange([...chapters, { heading: "新增章节", paragraphs: [""], evidence_ids: [] }])}
                    >
                        <Plus className="size-4" />
                        新增章节
                    </Button>
                </div>
                {chapters.map((chapter, index) => (
                    <div key={`${chapter.heading}-${index}`} className="rounded-xl border border-slate-200 p-4">
                        <div className="flex items-center gap-2">
                            <input
                                value={chapter.heading ?? ""}
                                onChange={(event) => updateChapter(index, { heading: event.target.value })}
                                className="min-w-0 flex-1 border-0 border-b border-slate-200 px-0 py-2 text-lg font-black text-slate-950 outline-none focus:border-primary"
                            />
                            <Button
                                type="button"
                                variant="ghost"
                                size="icon"
                                className="size-9 rounded-xl text-red-500 hover:bg-red-50 hover:text-red-600"
                                onClick={() => onChaptersChange(chapters.filter((_chapter, currentIndex) => currentIndex !== index))}
                            >
                                <Trash2 className="size-4" />
                            </Button>
                        </div>
                        <textarea
                            value={(chapter.paragraphs ?? []).join("\n\n")}
                            onChange={(event) => updateChapter(index, { paragraphs: splitParagraphs(event.target.value) })}
                            rows={7}
                            className="mt-4 w-full resize-y rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm leading-7 text-slate-800 outline-none transition focus:border-primary"
                            placeholder="每段之间用空行分隔"
                        />
                    </div>
                ))}
            </div>
            <EditorTextarea label="结论与建议" value={conclusion} onChange={onConclusionChange} minRows={5} />
        </div>
    );
}

function EditorTextarea({ label, value, onChange, minRows }: { label: string; value: string; onChange: (value: string) => void; minRows: number }) {
    return (
        <label className="block space-y-2">
            <span className="text-sm font-black text-slate-700">{label}</span>
            <textarea
                value={value}
                onChange={(event) => onChange(event.target.value)}
                rows={minRows}
                className="w-full resize-y rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm leading-7 text-slate-800 outline-none transition focus:border-primary"
            />
        </label>
    );
}

function FallbackReportBody({
    companySections,
    findings,
    risks,
    opportunities,
    materials,
    materialMap,
}: {
    companySections: InsightReportCompanySection[];
    findings: InsightReportFinding[];
    risks: InsightReportFinding[];
    opportunities: InsightReportFinding[];
    materials: ReportMaterial[];
    materialMap: Map<number, ReportMaterial>;
}) {
    return (
        <>
            <WordSection title="一、企业与市场动态概览">
                {companySections.length > 0 ? (
                    companySections.map((section, index) => (
                        <ReportParagraph
                            key={`${section.company_name}-${index}`}
                            text={`${section.company_name || "相关企业"}方面：${section.summary || "当前素材尚未形成完整判断。"}`}
                            evidenceIds={firstEvidenceIds(materials, 2, index * 2)}
                            materialMap={materialMap}
                        />
                    ))
                ) : (
                    <ReportParagraph text="当前素材主要覆盖目标企业公开资讯、市场动作、产品变化和潜在风险，仍需要结合企业数据继续验证。" evidenceIds={firstEvidenceIds(materials, 3)} materialMap={materialMap} />
                )}
            </WordSection>
            <WordSection title="二、关键发现">
                {findings.slice(0, 6).map((finding, index) => (
                    <ReportParagraph
                        key={`${finding.title}-${index}`}
                        text={`${finding.title || "发现"}。${finding.insight || finding.summary || ""}`}
                        evidenceIds={asNumberArray(finding.evidence_ids).length ? asNumberArray(finding.evidence_ids) : firstEvidenceIds(materials, 2, index * 2)}
                        materialMap={materialMap}
                    />
                ))}
            </WordSection>
            <WordSection title="三、机会与风险判断">
                <ReportParagraph text={joinFindingText("机会方面", opportunities)} evidenceIds={firstEvidenceIds(materials, 3, 4)} materialMap={materialMap} />
                <ReportParagraph text={joinFindingText("风险方面", risks)} evidenceIds={firstEvidenceIds(materials, 3, 7)} materialMap={materialMap} />
            </WordSection>
        </>
    );
}

function WordSection({ title, children }: { title: string; children: ReactNode }) {
    return (
        <section className="mt-10">
            <h3 className="mb-4 text-xl font-black leading-8 text-slate-950">{title}</h3>
            <div className="space-y-4">{children}</div>
        </section>
    );
}

function ReportChartsAppendix({ charts }: { charts: InsightReportChartRead[] }) {
    return (
        <WordSection title="附录：数据图表">
            <div className="grid gap-4 md:grid-cols-2">
                {charts.map((chart) => (
                    <ChartCard key={chart.chart_key} chart={chart} compact />
                ))}
            </div>
        </WordSection>
    );
}

function ReportParagraph({ text, evidenceIds, materialMap }: { text: string; evidenceIds?: number[]; materialMap: Map<number, ReportMaterial> }) {
    const references = (evidenceIds ?? []).map((id) => materialMap.get(id)).filter((item): item is ReportMaterial => Boolean(item)).slice(0, 3);
    return (
        <p className="text-justify text-[15px] leading-8 text-slate-800">
            {text}
            {references.map((material, index) => (
                <CitationMarker key={`${material.id}-${index}`} index={index + 1} material={material} />
            ))}
        </p>
    );
}

function CitationMarker({ index, material }: { index: number; material: ReportMaterial }) {
    return (
        <span className="group relative ml-1 inline-flex align-super">
            <button type="button" className="rounded px-1 text-[10px] font-black leading-none text-primary underline decoration-primary/40 underline-offset-2">
                [{index}]
            </button>
            <span className="absolute left-1/2 top-full z-30 hidden w-80 -translate-x-1/2 pt-2 normal-case group-hover:block">
                <span className="block rounded-xl border border-slate-200 bg-white p-4 text-left text-xs leading-5 text-slate-600 shadow-xl">
                    <span className="block font-black text-slate-950">{material.intelligence_title || material.source_title || `素材 ${material.intelligence_id}`}</span>
                    {material.quote_text || material.intelligence_summary ? <span className="mt-2 line-clamp-4 block">{material.quote_text || material.intelligence_summary}</span> : null}
                    {material.source_url ? (
                        <a href={material.source_url} target="_blank" rel="noreferrer" className="mt-3 inline-flex items-center gap-1 font-bold text-primary">
                            打开原文
                            <ExternalLink className="size-3" />
                        </a>
                    ) : null}
                </span>
            </span>
        </span>
    );
}

function ReferenceList({ materials }: { materials: ReportMaterial[] }) {
    if (materials.length === 0) {
        return <p className="text-sm leading-7 text-slate-500">暂无引用来源。</p>;
    }
    return (
        <ol className="space-y-2 text-sm leading-7 text-slate-700">
            {materials.slice(0, 30).map((material, index) => (
                <li key={material.id} className="flex gap-2">
                    <span className="shrink-0 text-slate-400">[{index + 1}]</span>
                    {material.source_url ? (
                        <a href={material.source_url} target="_blank" rel="noreferrer" className="min-w-0 text-primary hover:underline">
                            {material.intelligence_title || material.source_title || `素材 ${material.intelligence_id}`}
                        </a>
                    ) : (
                        <span>{material.intelligence_title || material.source_title || `素材 ${material.intelligence_id}`}</span>
                    )}
                </li>
            ))}
        </ol>
    );
}

function ReportHistoryItem({ report, active, onClick }: { report: InsightReportListItem; active: boolean; onClick: () => void }) {
    return (
        <button
            type="button"
            onClick={onClick}
            className={cn(
                "w-full rounded-xl border p-3 text-left transition",
                active ? "border-primary/30 bg-blue-50 text-slate-950 shadow-sm" : "border-transparent hover:bg-slate-50",
            )}
        >
            <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                    <div className="line-clamp-2 text-sm font-black leading-5">{report.title}</div>
                    <div className="mt-1 text-xs text-slate-500">{formatDate(report.update_time)} 更新</div>
                </div>
                <span className="shrink-0 rounded-full bg-emerald-50 px-2 py-1 text-xs font-bold text-emerald-600">{report.status === "draft" ? "草稿" : report.status}</span>
            </div>
            <div className="mt-3 flex items-center gap-2 text-xs font-bold text-slate-500">
                <FileText className="size-3.5" />
                {report.material_count} 条素材
            </div>
        </button>
    );
}

function HistorySkeleton() {
    return (
        <div className="space-y-2">
            {[1, 2, 3].map((item) => (
                <div key={item} className="h-20 animate-pulse rounded-xl bg-slate-100" />
            ))}
        </div>
    );
}

function asFindings(value: unknown): InsightReportFinding[] {
    return Array.isArray(value) ? value.filter((item): item is InsightReportFinding => typeof item === "object" && item !== null) : [];
}

function asCompanySections(value: unknown): InsightReportCompanySection[] {
    return Array.isArray(value) ? value.filter((item): item is InsightReportCompanySection => typeof item === "object" && item !== null) : [];
}

function asChapters(value: unknown): InsightReportChapter[] {
    return Array.isArray(value) ? value.filter((item): item is InsightReportChapter => typeof item === "object" && item !== null) : [];
}

function asNumberArray(value: unknown): number[] {
    return Array.isArray(value) ? value.filter((item): item is number => typeof item === "number") : [];
}

function stringValue(value: unknown): string {
    return typeof value === "string" ? value : "";
}

function splitParagraphs(value: string): string[] {
    return value.split(/\n{2,}/).map((item) => item.trim());
}

function defaultSections(): InsightReportTemplateSection[] {
    return [
        { section_key: "summary", heading: "一、核心摘要", description: "概括报告主要发现和判断边界。" },
        { section_key: "analysis", heading: "二、重点分析", description: "围绕素材做正式正文分析。" },
        { section_key: "recommendations", heading: "三、结论与建议", description: "形成客户经营和业务跟进建议。" },
    ];
}

function updateTemplateSection(
    sections: InsightReportTemplateSection[],
    index: number,
    patch: Partial<InsightReportTemplateSection>,
): InsightReportTemplateSection[] {
    return sections.map((section, currentIndex) => (currentIndex === index ? { ...section, ...patch } : section));
}

function firstEvidenceIds(materials: ReportMaterial[], count: number, offset = 0): number[] {
    return materials.slice(offset, offset + count).map((material) => material.intelligence_id);
}

function toggleNumber(values: number[], value: number) {
    return values.includes(value) ? values.filter((item) => item !== value) : [...values, value];
}

function sectionTitle(index: number) {
    return ["一、市场概览", "二、企业动态分析", "三、机会与风险", "四、结论建议"][index] ?? `第 ${index + 1} 章`;
}

function joinFindingText(prefix: string, findings: InsightReportFinding[]) {
    if (findings.length === 0) return `${prefix}，现有素材尚未形成足够清晰的连续信号，需要后续补充来源验证。`;
    return `${prefix}，${findings
        .slice(0, 4)
        .map((item) => `${item.title || "相关信号"}${item.summary || item.insight ? `，${item.summary || item.insight}` : ""}`)
        .join("；")}。`;
}

function buildConclusion(findings: InsightReportFinding[], opportunities: InsightReportFinding[], risks: InsightReportFinding[]) {
    return `综合现有素材，报告已经识别出 ${findings.length} 项关键发现、${opportunities.length} 项合作机会信号和 ${risks.length} 项需要关注的客户经营风险信号。后续建议将这些公开资讯与企业工商、招投标、招聘、渠道和内部客户合作数据联动验证，再形成更稳定的客户经营判断。`;
}

function formatDate(value?: string | null) {
    if (!value) return "-";
    return new Date(value).toLocaleDateString("zh-CN", { month: "2-digit", day: "2-digit" });
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

function normalizeExportFormat(format?: string | null): ReportExportFormat {
    const normalized = format?.toLowerCase();
    if (normalized === "pdf" || normalized === "docx") return normalized;
    return "html";
}

async function insightDownloadReportExport(reportId: number, exportRecord: InsightReportExportRead) {
    const file = await insightApi.downloadReportExport(reportId, exportRecord.id);
    downloadBlob(file, exportRecord.file_name || `insight-report-${reportId}.${exportRecord.export_format || "html"}`);
}

function formatFullDate(value?: string | null) {
    if (!value) return "生成时间未知";
    return new Date(value).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

function parseOptionalNumber(value: string) {
    if (!value) return undefined;
    const numberValue = Number(value);
    return Number.isFinite(numberValue) ? numberValue : undefined;
}
