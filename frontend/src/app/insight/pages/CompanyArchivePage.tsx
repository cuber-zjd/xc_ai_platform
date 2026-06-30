import { type FormEvent, useMemo, useRef, useState } from "react";
import { Building2, Database, Download, ExternalLink, FileSpreadsheet, FileText, Loader2, Plus, Search, ShieldCheck, Tags, Upload } from "lucide-react";
import { Link } from "react-router-dom";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { useAuthStore } from "@/store/useAuthStore";

import { insightApi, type InsightCompanyCreate, type InsightCompanyImportResponse, type InsightCompanyListItem } from "../api";
import { AccessRuleDialog } from "../components";
import { DemoCard, DemoTag, StatCard } from "../components/DemoPrimitives";
import { InsightSelect } from "../components/InsightSelect";
import { useInsightCompanies, useInsightCompanyDetail, useInsightCreateCompany, useInsightImportCompanies, useInsightSystemCompanies } from "../hooks";
import { PageContainer } from "../layout/PageContainer";
import { formatInsightDate, formatInsightType } from "../utils/display";

const monitorLevelText: Record<string, string> = {
    normal: "普通监控",
    key: "重点客户",
    competitor: "重点竞对",
    watch: "观察名单",
};

const companyTypeOptions = [
    { value: "客户", label: "客户" },
    { value: "竞对", label: "竞对" },
    { value: "供应商", label: "供应商" },
    { value: "合作伙伴", label: "合作伙伴" },
    { value: "其他", label: "其他" },
];

const monitorLevelOptions = [
    { value: "normal", label: "普通监控" },
    { value: "key", label: "重点客户" },
    { value: "competitor", label: "重点竞对" },
    { value: "watch", label: "观察名单" },
];

export function CompanyArchivePage() {
    const isAdmin = useAuthStore((state) => state.user?.role === "admin");
    const [keywordInput, setKeywordInput] = useState("");
    const [keyword, setKeyword] = useState("");
    const [sysCompanyFilter, setSysCompanyFilter] = useState("");
    const [selectedCompanyId, setSelectedCompanyId] = useState<number | null>(null);
    const [createOpen, setCreateOpen] = useState(false);
    const [importOpen, setImportOpen] = useState(false);
    const [importResult, setImportResult] = useState<InsightCompanyImportResponse | null>(null);
    const [selectorOpen, setSelectorOpen] = useState(false);
    const [accessOpen, setAccessOpen] = useState(false);
    const [bulkAccessOpen, setBulkAccessOpen] = useState(false);
    const [selectedCompanyIds, setSelectedCompanyIds] = useState<number[]>([]);
    const [companyPage, setCompanyPage] = useState(1);
    const importInputRef = useRef<HTMLInputElement | null>(null);
    const companiesQuery = useInsightCompanies({
        page: companyPage,
        size: 20,
        keyword: keyword || undefined,
        sys_company_id: parseOptionalNumber(sysCompanyFilter) ?? undefined,
    });
    const companies = useMemo(() => companiesQuery.data?.items ?? [], [companiesQuery.data?.items]);
    const totalCompanies = companiesQuery.data?.total ?? 0;
    const totalCompanyPages = Math.max(1, Math.ceil(totalCompanies / 20));
    const effectiveSelectedCompanyId = selectedCompanyId ?? companies[0]?.id ?? null;
    const selectedCompany = companies.find((company) => company.id === effectiveSelectedCompanyId) ?? null;
    const detailQuery = useInsightCompanyDetail(effectiveSelectedCompanyId);
    const createMutation = useInsightCreateCompany();
    const importMutation = useInsightImportCompanies();
    const systemCompaniesQuery = useInsightSystemCompanies();
    const systemCompanyOptions = useMemo(
        () =>
            (systemCompaniesQuery.data ?? []).map((company) => ({
                value: String(company.id),
                label: company.code ? `${company.name}（${company.code}）` : company.name,
            })),
        [systemCompaniesQuery.data],
    );
    const systemCompanyNameById = useMemo(
        () => new Map((systemCompaniesQuery.data ?? []).map((company) => [company.id, company.name])),
        [systemCompaniesQuery.data],
    );
    const detail = detailQuery.data;

    const trendPoints = useMemo(() => buildTrendPoints(detail?.timeline ?? []), [detail?.timeline]);

    const handleImportFile = (file: File | null) => {
        if (!file) {
            return;
        }
        if (!/\.(xlsx|xlsm)$/i.test(file.name)) {
            toast.error("请上传 xlsx 或 xlsm 格式的 Excel 文件");
            return;
        }
        const payload = new FormData();
        payload.append("file", file);
        importMutation.mutate(payload, {
            onSuccess: (result) => {
                setImportResult(result);
                setImportOpen(true);
                const firstCompany = result.companies[0];
                if (firstCompany?.id) {
                    setSelectedCompanyId(firstCompany.id);
                }
                toast.success(`导入完成：新增 ${result.created_count} 家，更新 ${result.updated_count} 家`);
            },
            onError: () => toast.error("企业档案导入失败，请检查 Excel 表头和内容"),
            onSettled: () => {
                if (importInputRef.current) {
                    importInputRef.current.value = "";
                }
            },
        });
    };

    const handleDownloadTemplate = async () => {
        try {
            const file = await insightApi.downloadCompanyImportTemplate();
            downloadBlob(file, "企业档案导入模板.xlsx");
        } catch {
            toast.error("模板下载失败，请稍后重试");
        }
    };

    return (
        <PageContainer className="flex h-full min-h-0 flex-col gap-3 overflow-hidden">
            <div className="flex shrink-0 flex-wrap items-center justify-between gap-3">
                <div className="min-w-0">
                    <div className="text-sm font-black text-slate-900">企业档案</div>
                    <p className="mt-1 text-xs font-semibold text-slate-500">左侧选择企业，右侧查看档案、情报和监测状态。</p>
                </div>
                <div className="insight-actions">
                    <input
                        ref={importInputRef}
                        type="file"
                        accept=".xlsx,.xlsm"
                        className="hidden"
                        onChange={(event) => handleImportFile(event.target.files?.[0] ?? null)}
                    />
                    <Button
                        type="button"
                        variant="outline"
                        className="h-10 rounded-xl border-slate-200 bg-white px-5 text-blue-700"
                        onClick={() => setSelectorOpen(true)}
                    >
                        <Building2 className="size-4" />
                        选择企业
                    </Button>
                    <Button
                        type="button"
                        variant="outline"
                        className="h-10 rounded-xl border-slate-200 bg-white px-5 text-blue-700"
                        onClick={() => {
                            setImportResult(null);
                            setImportOpen(true);
                        }}
                    >
                        <Upload className="size-4" />
                        Excel 导入
                    </Button>
                    <Button className="h-10 rounded-xl bg-primary px-5 text-primary-foreground" onClick={() => setCreateOpen(true)}>
                        <Plus className="size-4" />
                        新增企业
                    </Button>
                </div>
            </div>

            <div className="grid min-h-0 min-w-0 flex-1 gap-3 overflow-hidden lg:grid-cols-[260px_minmax(0,1fr)] xl:grid-cols-[320px_minmax(0,1fr)]">
                <aside className="insight-card flex min-h-0 min-w-0 flex-col overflow-hidden p-0">
                    <div className="shrink-0 border-b border-slate-100 p-4">
                        <div className="flex flex-wrap items-center justify-between gap-3">
                            <div>
                                <div className="text-base font-black text-slate-950">企业列表</div>
                                <p className="mt-1 text-xs font-semibold text-slate-500">共 {totalCompanies} 家，点击切换档案</p>
                            </div>
                            {selectedCompanyIds.length ? (
                                <Button type="button" variant="outline" className="h-8 rounded-xl bg-white text-xs" onClick={() => setBulkAccessOpen(true)}>
                                    批量授权
                                </Button>
                            ) : null}
                        </div>
                        <label className="mt-3 flex h-10 items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 text-sm">
                            <Search className="size-4 text-slate-400" />
                            <input
                                value={keywordInput}
                                onChange={(event) => setKeywordInput(event.target.value)}
                                onKeyDown={(event) => {
                                    if (event.key === "Enter") {
                                        setKeyword(keywordInput.trim());
                                        setCompanyPage(1);
                                    }
                                }}
                                placeholder="搜索企业名称、简称"
                                className="min-w-0 flex-1 bg-transparent outline-none placeholder:text-slate-400"
                            />
                        </label>
                        <div className="mt-3 grid gap-2">
                            <InsightSelect
                                label="所属公司"
                                value={sysCompanyFilter}
                                options={[{ value: "", label: "全部所属公司" }, ...systemCompanyOptions]}
                                onChange={(value) => {
                                    setSysCompanyFilter(value);
                                    setCompanyPage(1);
                                    setSelectedCompanyIds([]);
                                }}
                            />
                            <div className="insight-action-cluster justify-start">
                                <Button
                                    type="button"
                                    className="h-9 rounded-xl bg-primary px-4 text-primary-foreground"
                                    onClick={() => {
                                        setKeyword(keywordInput.trim());
                                        setCompanyPage(1);
                                    }}
                                >
                                    搜索
                                </Button>
                                <Button
                                    type="button"
                                    variant="ghost"
                                    className="h-9 rounded-xl px-3 text-slate-600"
                                    onClick={() => {
                                        setKeyword("");
                                        setKeywordInput("");
                                        setSysCompanyFilter("");
                                        setSelectedCompanyIds([]);
                                        setCompanyPage(1);
                                    }}
                                >
                                    重置
                                </Button>
                            </div>
                        </div>
                    </div>
                    <div className="min-h-0 flex-1 space-y-2 overflow-y-auto p-3">
                        {companies.map((company) => (
                            <CompanyListButton
                                key={company.id}
                                company={company}
                                active={company.id === effectiveSelectedCompanyId}
                                selected={selectedCompanyIds.includes(company.id)}
                                onClick={() => setSelectedCompanyId(company.id)}
                                onToggleSelect={() =>
                                    setSelectedCompanyIds((current) =>
                                        current.includes(company.id) ? current.filter((id) => id !== company.id) : [...current, company.id],
                                    )
                                }
                            />
                        ))}
                        {companiesQuery.isLoading ? <EmptyPanel text="正在加载企业列表..." /> : null}
                        {!companiesQuery.isLoading && companies.length === 0 ? <EmptyPanel text="暂无企业档案，可新增或通过 Excel 导入。" /> : null}
                    </div>
                    <div className="shrink-0 border-t border-slate-100 px-4 py-3">
                        <div className="flex items-center justify-between gap-3 text-xs font-semibold text-slate-500">
                            <span>{companyPage} / {totalCompanyPages}</span>
                            <div className="flex items-center gap-2">
                                <Button type="button" variant="outline" className="h-8 rounded-xl bg-white text-xs" disabled={companyPage <= 1} onClick={() => setCompanyPage((page) => Math.max(1, page - 1))}>
                                    上一页
                                </Button>
                                <Button type="button" variant="outline" className="h-8 rounded-xl bg-white text-xs" disabled={companyPage >= totalCompanyPages} onClick={() => setCompanyPage((page) => Math.min(totalCompanyPages, page + 1))}>
                                    下一页
                                </Button>
                            </div>
                        </div>
                    </div>
                </aside>

                <section className="min-h-0 min-w-0 overflow-y-auto rounded-2xl border border-slate-200 bg-slate-100/60 p-3 sm:p-4">
                {detail ? (
                    <div className="space-y-4">
                        <DemoCard className="p-4 sm:p-6">
                            <div className="flex flex-col justify-between gap-5 2xl:flex-row 2xl:items-start">
                                <div className="flex min-w-0 flex-col gap-4 sm:flex-row sm:gap-5">
                                    <div className="flex size-14 shrink-0 items-center justify-center rounded-xl bg-linear-to-br from-blue-500 to-cyan-500 text-lg font-black text-white sm:size-16 sm:text-xl">
                                        {(detail.short_name || detail.name).slice(0, 2)}
                                    </div>
                                    <div className="min-w-0">
                                        <div className="flex flex-wrap items-center gap-3">
                                            <h2 className="text-xl font-black leading-tight text-slate-950 md:text-2xl">{detail.name}</h2>
                                            <DemoTag tone={detail.monitor_level === "key" ? "orange" : "blue"}>{monitorLevelText[detail.monitor_level] ?? detail.monitor_level}</DemoTag>
                                            {detail.industry ? <DemoTag tone="green">{detail.industry}</DemoTag> : null}
                                        </div>
                                        <p className="mt-3 max-w-3xl text-sm font-semibold leading-6 text-slate-600">
                                            {detail.description || "暂无企业描述，可在后续企业档案编辑中补充业务画像、产品线和监控重点。"}
                                        </p>
                                        <div className="mt-3 flex flex-wrap gap-x-5 gap-y-2 text-xs font-semibold text-slate-500">
                                            <span>简称：{detail.short_name || "-"}</span>
                                            <span>所属公司：{detail.sys_company_id ? systemCompanyNameById.get(detail.sys_company_id) ?? "-" : "-"}</span>
                                            <span>区域：{detail.region || "-"}</span>
                                            <span>类型：{detail.company_type || "-"}</span>
                                            {detail.website ? (
                                                <a className="inline-flex items-center gap-1 text-blue-600 hover:underline" href={detail.website} target="_blank" rel="noreferrer">
                                                    官网
                                                    <ExternalLink className="size-3" />
                                                </a>
                                            ) : null}
                                        </div>
                                    </div>
                                </div>
                                <div className="insight-actions 2xl:max-w-[420px]">
                                    <Button
                                        type="button"
                                        variant="outline"
                                        className="h-10 rounded-xl border-slate-200 bg-white text-blue-700"
                                        onClick={() => setAccessOpen(true)}
                                    >
                                        <ShieldCheck className="size-4" />
                                        权限
                                    </Button>
                                    {isAdmin ? (
                                        <Link
                                            to="/insight/data-sources"
                                            className="inline-flex h-10 items-center justify-center rounded-xl border border-blue-100 bg-blue-50 px-4 text-sm font-black text-blue-700 hover:bg-blue-100"
                                        >
                                            配置执行源
                                        </Link>
                                    ) : null}
                                    <Link
                                        to={`/insight/intelligence?subject_type=company&keyword=${encodeURIComponent(detail.short_name || detail.name)}`}
                                        className="inline-flex h-10 items-center justify-center rounded-xl border border-slate-200 bg-white px-4 text-sm font-black text-slate-700 hover:bg-slate-50"
                                    >
                                        查看关联情报
                                    </Link>
                                </div>
                            </div>
                        </DemoCard>

                        <div className="grid grid-cols-2 gap-3 2xl:grid-cols-4">
                            {(detail.metrics.length ? detail.metrics : emptyMetrics).map((metric, index) => (
                                <StatCard
                                    key={metric.key}
                                    title={metric.label}
                                    value={String(metric.value)}
                                    compare={metric.compare_label || "当前企业"}
                                    delta={formatDelta(metric.delta)}
                                    tone={index % 2 === 0 ? "blue" : "cyan"}
                                    icon={metricIcon(metric.key)}
                                />
                            ))}
                        </div>

                        <div className="grid gap-4 2xl:grid-cols-[1fr_0.9fr]">
                            <DemoCard className="p-5">
                                <SectionTitle title="重点情报时间线" />
                                <div className="space-y-4">
                                    {detail.timeline.map((item) => (
                                        <div key={item.id} className="grid gap-2 rounded-xl border border-slate-100 bg-white px-4 py-3 lg:grid-cols-[140px_minmax(0,1fr)_auto] lg:items-start">
                                            <div className="text-xs font-bold text-slate-500">{formatInsightDate(item.publish_time, item.create_time)}</div>
                                            <div className="min-w-0">
                                                <Link to={`/insight/intelligence/${item.id}`} className="line-clamp-1 text-sm font-black text-slate-900 hover:text-blue-600">
                                                    {item.title}
                                                </Link>
                                                <div className="mt-1 line-clamp-2 text-xs font-semibold leading-5 text-slate-500">{item.summary || item.primary_source_title || "暂无摘要"}</div>
                                            </div>
                                            <DemoTag tone={item.importance_level === "high" ? "orange" : "blue"}>{formatInsightType(item.intelligence_type)}</DemoTag>
                                        </div>
                                    ))}
                                    {detail.timeline.length === 0 ? <EmptyPanel text="暂无已关联正式情报。新采集情报带上 company_id 后会自动进入这里。" /> : null}
                                </div>
                            </DemoCard>

                            <div className="space-y-4">
                                <DemoCard className="p-5">
                                    <SectionTitle title="情报类型分布" />
                                    {detail.type_distribution.length > 0 ? (
                                        <div className="space-y-3">
                                            {detail.type_distribution.map((slice) => (
                                                <div key={slice.label}>
                                                    <div className="mb-1 flex flex-wrap items-center justify-between gap-2 text-sm font-bold text-slate-700">
                                                        <span>{slice.label}</span>
                                                        <span>{slice.count} 条</span>
                                                    </div>
                                                    <div className="h-2 overflow-hidden rounded-full bg-slate-100">
                                                        <div className="h-full rounded-full bg-blue-500" style={{ width: `${Math.max(slice.percent, slice.count > 0 ? 8 : 0)}%` }} />
                                                    </div>
                                                </div>
                                            ))}
                                        </div>
                                    ) : (
                                        <EmptyPanel text="暂无类型分布数据" />
                                    )}
                                </DemoCard>

                                <DemoCard className="p-5">
                                    <SectionTitle title="高频标签" />
                                    <div className="flex flex-wrap gap-2">
                                        {detail.tag_stats.length > 0 ? (
                                            detail.tag_stats.map((tag, index) => (
                                                <DemoTag key={tag.name} tone={index % 3 === 0 ? "cyan" : index % 3 === 1 ? "green" : "orange"}>
                                                    {tag.name} {tag.count}
                                                </DemoTag>
                                            ))
                                        ) : (
                                            <DemoTag tone="slate">暂无标签</DemoTag>
                                        )}
                                    </div>
                                </DemoCard>
                            </div>
                        </div>

                        <div className="grid gap-4 2xl:grid-cols-[0.9fr_1.1fr]">
                            <DemoCard className="p-5">
                                <SectionTitle title="关联数据源" />
                                <div className="space-y-3">
                                    {detail.data_sources.map((source) => (
                                        <div key={source.id} className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-100 bg-white px-4 py-3">
                                            <div className="min-w-0">
                                                <div className="line-clamp-1 text-sm font-black text-slate-800">{source.source_name}</div>
                                                <div className="mt-1 text-xs font-semibold text-slate-500">{source.source_type} · {source.status}</div>
                                            </div>
                                            {isAdmin ? <Link className="text-xs font-black text-blue-600" to="/insight/data-sources">配置</Link> : null}
                                        </div>
                                    ))}
                                    {detail.data_sources.length === 0 ? <EmptyPanel text={isAdmin ? "暂无关联执行源，可到系统设置中的执行源配置维护。" : "暂无关联执行源，后续由管理员统一维护。"} /> : null}
                                </div>
                            </DemoCard>

                            <DemoCard className="p-5">
                                <SectionTitle title="近7天动态" />
                                <div className="overflow-x-auto">
                                    <div className="grid min-w-[520px] grid-cols-7 items-end gap-3 pt-6">
                                        {trendPoints.map((point) => (
                                            <div key={point.label} className="grid gap-2 text-center">
                                                <div className="flex h-32 items-end justify-center rounded-lg bg-blue-50 px-2">
                                                    <div className="w-full rounded-t-md bg-blue-500" style={{ height: `${Math.max(8, point.count * 18)}px` }} />
                                                </div>
                                                <div className="text-xs font-bold text-slate-500">{point.label}</div>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            </DemoCard>
                        </div>
                    </div>
                ) : (
                    <DemoCard className="flex min-h-[24rem] items-center justify-center gap-2 p-10 text-center text-sm font-semibold text-slate-500">
                        {companiesQuery.isLoading || detailQuery.isLoading ? <Loader2 className="size-4 animate-spin" /> : null}
                        {companiesQuery.isLoading || detailQuery.isLoading ? "正在加载企业档案" : "请选择左侧企业查看档案。"}
                    </DemoCard>
                )}
                </section>
            </div>

            <CompanySelectorDialog
                open={selectorOpen}
                companies={companies}
                loading={companiesQuery.isLoading}
                fetching={companiesQuery.isFetching}
                keywordInput={keywordInput}
                sysCompanyFilter={sysCompanyFilter}
                systemCompanyOptions={systemCompanyOptions}
                selectedCompanyId={effectiveSelectedCompanyId}
                selectedCompanyIds={selectedCompanyIds}
                page={companyPage}
                total={totalCompanies}
                totalPages={totalCompanyPages}
                onOpenChange={setSelectorOpen}
                onKeywordInputChange={setKeywordInput}
                onSearch={() => {
                    setKeyword(keywordInput.trim());
                    setCompanyPage(1);
                }}
                onReset={() => {
                    setKeyword("");
                    setKeywordInput("");
                    setSysCompanyFilter("");
                    setSelectedCompanyIds([]);
                    setCompanyPage(1);
                }}
                onSysCompanyFilterChange={(value) => {
                    setSysCompanyFilter(value);
                    setSelectedCompanyIds([]);
                    setCompanyPage(1);
                }}
                onSelectCompany={(companyId) => {
                    setSelectedCompanyId(companyId);
                    setSelectorOpen(false);
                }}
                onToggleSelect={(companyId) =>
                    setSelectedCompanyIds((current) =>
                        current.includes(companyId) ? current.filter((id) => id !== companyId) : [...current, companyId],
                    )
                }
                onToggleCurrentPage={() =>
                    setSelectedCompanyIds((current) => {
                        const currentPageIds = companies.map((company) => company.id);
                        const currentPageSelected = currentPageIds.length > 0 && currentPageIds.every((id) => current.includes(id));
                        if (currentPageSelected) {
                            return current.filter((id) => !currentPageIds.includes(id));
                        }
                        return Array.from(new Set([...current, ...currentPageIds]));
                    })
                }
                onBulkAccess={() => {
                    setSelectorOpen(false);
                    setBulkAccessOpen(true);
                }}
                onPageChange={setCompanyPage}
            />

            <CreateCompanyDialog
                open={createOpen}
                pending={createMutation.isPending}
                systemCompanyOptions={systemCompanyOptions}
                onOpenChange={setCreateOpen}
                onSubmit={(payload) => {
                    createMutation.mutate(payload, {
                        onSuccess: (company) => {
                            toast.success("企业档案已创建");
                            setSelectedCompanyId(company.id);
                            setCreateOpen(false);
                        },
                        onError: () => toast.error("企业档案创建失败，请检查名称或编码"),
                    });
                }}
            />
            <AccessRuleDialog
                open={accessOpen}
                onOpenChange={setAccessOpen}
                targetType="company"
                targetId={detail?.id ?? selectedCompany?.id ?? null}
                targetName={detail?.name ?? selectedCompany?.name ?? ""}
            />
            <AccessRuleDialog
                open={bulkAccessOpen}
                onOpenChange={setBulkAccessOpen}
                targetType="company"
                targetId={selectedCompanyIds[0] ?? null}
                targetIds={selectedCompanyIds}
                targetName={`已选择 ${selectedCompanyIds.length} 家企业`}
            />
            <CompanyImportDialog
                open={importOpen}
                pending={importMutation.isPending}
                result={importResult}
                onOpenChange={setImportOpen}
                onDownloadTemplate={handleDownloadTemplate}
                onSelectFile={() => importInputRef.current?.click()}
            />
        </PageContainer>
    );
}

function CompanyListButton({
    company,
    active,
    selected,
    onClick,
    onToggleSelect,
}: {
    company: InsightCompanyListItem;
    active: boolean;
    selected: boolean;
    onClick: () => void;
    onToggleSelect: () => void;
}) {
    return (
        <div className={`flex items-start gap-3 rounded-xl border px-4 py-3 transition ${active ? "border-blue-200 bg-blue-50" : "border-slate-100 bg-white hover:border-blue-100 hover:bg-blue-50/40"}`}>
            <input
                type="checkbox"
                checked={selected}
                onChange={onToggleSelect}
                className="mt-3 size-4 rounded border-slate-300 text-blue-600 focus:ring-blue-500"
                aria-label={`选择${company.name}`}
            />
            <button type="button" onClick={onClick} className="min-w-0 flex-1 text-left">
                <div className="flex items-start gap-3">
                <div className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-blue-500 text-xs font-black text-white">
                    {(company.short_name || company.name).slice(0, 2)}
                </div>
                <div className="min-w-0 flex-1">
                    <div className="line-clamp-1 text-sm font-black text-slate-900">{company.name}</div>
                    <div className="mt-1 flex flex-wrap gap-2 text-xs font-semibold text-slate-500">
                        <span>{company.industry || "未分类"}</span>
                        <span>情报 {company.intelligence_count}</span>
                        <span>候选 {company.candidate_count}</span>
                    </div>
                </div>
            </div>
            </button>
        </div>
    );
}

function CompanySelectorDialog({
    open,
    companies,
    loading,
    fetching,
    keywordInput,
    sysCompanyFilter,
    systemCompanyOptions,
    selectedCompanyId,
    selectedCompanyIds,
    page,
    total,
    totalPages,
    onOpenChange,
    onKeywordInputChange,
    onSearch,
    onReset,
    onSysCompanyFilterChange,
    onSelectCompany,
    onToggleSelect,
    onToggleCurrentPage,
    onBulkAccess,
    onPageChange,
}: {
    open: boolean;
    companies: InsightCompanyListItem[];
    loading: boolean;
    fetching: boolean;
    keywordInput: string;
    sysCompanyFilter: string;
    systemCompanyOptions: Array<{ value: string; label: string }>;
    selectedCompanyId: number | null;
    selectedCompanyIds: number[];
    page: number;
    total: number;
    totalPages: number;
    onOpenChange: (open: boolean) => void;
    onKeywordInputChange: (value: string) => void;
    onSearch: () => void;
    onReset: () => void;
    onSysCompanyFilterChange: (value: string) => void;
    onSelectCompany: (companyId: number) => void;
    onToggleSelect: (companyId: number) => void;
    onToggleCurrentPage: () => void;
    onBulkAccess: () => void;
    onPageChange: (page: number) => void;
}) {
    const currentPageAllSelected = companies.length > 0 && companies.every((company) => selectedCompanyIds.includes(company.id));
    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="max-h-[88vh] overflow-hidden rounded-2xl border-slate-200 bg-white p-0 sm:max-w-5xl">
                <DialogHeader className="border-b border-slate-100 px-6 py-5">
                    <DialogTitle className="flex items-center gap-2 text-xl font-black text-slate-950">
                        <Building2 className="size-5 text-primary" />
                        选择企业档案
                    </DialogTitle>
                    <DialogDescription>搜索或按所属公司筛选企业，选择后主页面只展示该企业档案。</DialogDescription>
                </DialogHeader>
                <div className="space-y-4 p-5">
                    <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_260px_auto_auto] lg:items-end">
                        <label className="grid gap-2">
                            <span className="text-sm font-bold text-slate-700">关键词</span>
                            <div className="relative">
                                <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-400" />
                                <Input
                                    className="h-11 rounded-xl border-slate-200 bg-white pl-10 shadow-none"
                                    placeholder="搜索企业、简称、行业"
                                    value={keywordInput}
                                    onChange={(event) => onKeywordInputChange(event.target.value)}
                                    onKeyDown={(event) => {
                                        if (event.key === "Enter") {
                                            onSearch();
                                        }
                                    }}
                                />
                            </div>
                        </label>
                        <label className="grid gap-2">
                            <span className="text-sm font-bold text-slate-700">所属公司</span>
                            <select
                                value={sysCompanyFilter}
                                onChange={(event) => onSysCompanyFilterChange(event.target.value)}
                                className="h-11 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm font-semibold text-slate-700 shadow-none outline-none transition hover:border-blue-200 hover:bg-blue-50/30 focus:border-blue-300 focus:ring-4 focus:ring-blue-100"
                            >
                                <option value="">全部所属公司</option>
                                {systemCompanyOptions.map((option) => (
                                    <option key={option.value} value={option.value}>
                                        {option.label}
                                    </option>
                                ))}
                            </select>
                        </label>
                        <Button type="button" className="h-11 rounded-xl bg-primary px-5 text-primary-foreground" onClick={onSearch}>
                            搜索
                        </Button>
                        <Button type="button" variant="ghost" className="h-11 rounded-xl text-slate-600" onClick={onReset}>
                            重置
                        </Button>
                    </div>

                    <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-slate-100 bg-slate-50 px-4 py-3">
                        <div className="text-sm font-bold text-slate-600">
                            {fetching ? "正在筛选企业..." : `共 ${total} 家企业 · 第 ${page} / ${totalPages} 页`}
                        </div>
                        <div className="flex flex-wrap items-center gap-2">
                            <Button type="button" variant="ghost" className="h-9 rounded-lg text-blue-700" disabled={companies.length === 0} onClick={onToggleCurrentPage}>
                                {currentPageAllSelected ? "取消全选本页" : "全选本页"}
                            </Button>
                            <Button
                                type="button"
                                variant="outline"
                                className="h-9 rounded-lg border-blue-100 bg-white px-3 text-blue-700"
                                disabled={selectedCompanyIds.length === 0}
                                onClick={onBulkAccess}
                            >
                                <ShieldCheck className="size-4" />
                                批量权限 {selectedCompanyIds.length > 0 ? selectedCompanyIds.length : ""}
                            </Button>
                        </div>
                    </div>

                    <div className="max-h-[44vh] min-h-[280px] overflow-y-auto pr-1">
                        <div className="grid gap-2 md:grid-cols-2">
                            {!fetching && companies.map((company) => (
                                <CompanyListButton
                                    key={company.id}
                                    company={company}
                                    active={company.id === selectedCompanyId}
                                    selected={selectedCompanyIds.includes(company.id)}
                                    onClick={() => onSelectCompany(company.id)}
                                    onToggleSelect={() => onToggleSelect(company.id)}
                                />
                            ))}
                        </div>
                        {loading || fetching ? (
                            <div className="mt-3 flex items-center justify-center gap-2 rounded-xl border border-slate-100 bg-slate-50 px-4 py-10 text-sm font-semibold text-slate-500">
                                <Loader2 className="size-4 animate-spin" />
                                正在加载企业档案
                            </div>
                        ) : null}
                        {!loading && !fetching && companies.length === 0 ? (
                            <div className="mt-3 rounded-xl border border-dashed border-slate-200 bg-slate-50 px-4 py-10 text-center text-sm font-semibold text-slate-500">
                                暂无符合条件的企业档案。
                            </div>
                        ) : null}
                    </div>

                    <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 pt-4">
                        <div className="text-xs font-semibold text-slate-500">选择企业后将关闭弹窗并切换主页面档案。</div>
                        <div className="flex items-center gap-2">
                            <Button type="button" variant="outline" className="h-9 rounded-lg" disabled={page <= 1 || loading || fetching} onClick={() => onPageChange(Math.max(1, page - 1))}>
                                上一页
                            </Button>
                            <span className="min-w-20 text-center text-sm font-black text-slate-700">
                                {page} / {totalPages}
                            </span>
                            <Button type="button" variant="outline" className="h-9 rounded-lg" disabled={page >= totalPages || loading || fetching} onClick={() => onPageChange(Math.min(totalPages, page + 1))}>
                                下一页
                            </Button>
                        </div>
                    </div>
                </div>
            </DialogContent>
        </Dialog>
    );
}

function CreateCompanyDialog({
    open,
    pending,
    systemCompanyOptions,
    onOpenChange,
    onSubmit,
}: {
    open: boolean;
    pending: boolean;
    systemCompanyOptions: Array<{ value: string; label: string }>;
    onOpenChange: (open: boolean) => void;
    onSubmit: (payload: InsightCompanyCreate) => void;
}) {
    const [form, setForm] = useState({
        company_code: "",
        sys_company_id: "",
        name: "",
        short_name: "",
        industry: "",
        company_type: "",
        region: "",
        website: "",
        monitor_level: "normal",
        description: "",
    });
    const update = (field: keyof typeof form, value: string) => setForm((current) => ({ ...current, [field]: value }));
    const submit = (event: FormEvent<HTMLFormElement>) => {
        event.preventDefault();
        onSubmit({
            company_code: form.company_code.trim() || undefined,
            sys_company_id: parseOptionalNumber(form.sys_company_id),
            name: form.name.trim(),
            short_name: form.short_name.trim() || undefined,
            industry: form.industry.trim() || undefined,
            company_type: form.company_type.trim() || undefined,
            region: form.region.trim() || undefined,
            website: form.website.trim() || undefined,
            monitor_level: form.monitor_level.trim() || "normal",
            description: form.description.trim() || undefined,
        });
    };
    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="max-h-[90vh] overflow-auto sm:max-w-3xl">
                <DialogHeader>
                    <DialogTitle>新增企业档案</DialogTitle>
                </DialogHeader>
                <form onSubmit={submit} className="space-y-4">
                    <div className="grid gap-4 md:grid-cols-2">
                        <Field label="企业名称" value={form.name} onChange={(value) => update("name", value)} required />
                        <Field label="简称" value={form.short_name} onChange={(value) => update("short_name", value)} />
                        <InsightSelect
                            label="所属公司"
                            value={form.sys_company_id}
                            onChange={(value) => update("sys_company_id", value)}
                            options={systemCompanyOptions}
                            placeholder={systemCompanyOptions.length > 0 ? "选择所属公司" : "暂无可选公司"}
                        />
                        <Field label="行业" value={form.industry} onChange={(value) => update("industry", value)} />
                        <InsightSelect
                            label="企业类型"
                            value={form.company_type}
                            onChange={(value) => update("company_type", value)}
                            options={companyTypeOptions}
                            placeholder="选择企业类型"
                        />
                        <Field label="区域" value={form.region} onChange={(value) => update("region", value)} />
                        <InsightSelect
                            label="监控级别"
                            value={form.monitor_level}
                            onChange={(value) => update("monitor_level", value)}
                            options={monitorLevelOptions}
                            placeholder="选择监控级别"
                        />
                        <details className="rounded-2xl border border-slate-100 bg-slate-50/70 p-4 md:col-span-2">
                            <summary className="cursor-pointer text-sm font-black text-slate-700">更多信息</summary>
                            <div className="mt-4 grid gap-4 md:grid-cols-2">
                                <Field label="企业编码" value={form.company_code} onChange={(value) => update("company_code", value)} placeholder="可用于主数据或 Excel 更新匹配" />
                                <Field label="官网" value={form.website} onChange={(value) => update("website", value)} placeholder="https://example.com" />
                                <label className="grid gap-2 md:col-span-2">
                                    <span className="text-sm font-bold text-slate-700">描述</span>
                                    <textarea
                                        className="min-h-28 rounded-xl border border-slate-200 bg-white p-3 text-sm font-semibold text-slate-700 outline-none focus:border-blue-300"
                                        value={form.description}
                                        onChange={(event) => update("description", event.target.value)}
                                        placeholder="可补充产品线、经营重点、关注原因等画像信息"
                                    />
                                </label>
                            </div>
                        </details>
                    </div>
                    <DialogFooter>
                        <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>取消</Button>
                        <Button type="submit" className="bg-primary text-primary-foreground" disabled={pending || !form.name.trim()}>
                            {pending ? <Loader2 className="size-4 animate-spin" /> : null}
                            保存企业
                        </Button>
                    </DialogFooter>
                </form>
            </DialogContent>
        </Dialog>
    );
}

function CompanyImportDialog({
    open,
    pending,
    onOpenChange,
    onDownloadTemplate,
    onSelectFile,
    result,
}: {
    open: boolean;
    pending: boolean;
    onOpenChange: (open: boolean) => void;
    onDownloadTemplate: () => void;
    onSelectFile: () => void;
    result: InsightCompanyImportResponse | null;
}) {
    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="sm:max-w-2xl">
                <DialogHeader>
                    <DialogTitle>Excel 导入企业档案</DialogTitle>
                    <DialogDescription>
                        先下载模板整理企业信息，再上传 .xlsx 或 .xlsm 文件导入。企业名称必填，企业编码或同名企业已存在时会更新现有档案。
                    </DialogDescription>
                </DialogHeader>
                <div className="space-y-5">
                    <div className="grid gap-3 sm:grid-cols-2">
                        <button
                            type="button"
                            className="flex items-start gap-3 rounded-2xl border border-slate-200 bg-white p-4 text-left transition hover:border-blue-200 hover:bg-blue-50/40"
                            onClick={onDownloadTemplate}
                        >
                            <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-slate-100 text-slate-700">
                                <Download className="size-5" />
                            </span>
                            <span className="min-w-0">
                                <span className="block text-sm font-black text-slate-900">下载模板</span>
                                <span className="mt-1 block text-xs font-semibold leading-5 text-slate-500">按标准列填写企业名称、行业、区域、监控级别等信息。</span>
                            </span>
                        </button>
                        <button
                            type="button"
                            className="flex items-start gap-3 rounded-2xl border border-blue-200 bg-blue-50 p-4 text-left transition hover:border-blue-300 hover:bg-blue-100/70 disabled:cursor-not-allowed disabled:opacity-70"
                            disabled={pending}
                            onClick={onSelectFile}
                        >
                            <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-blue-600 text-white">
                                {pending ? <Loader2 className="size-5 animate-spin" /> : <Upload className="size-5" />}
                            </span>
                            <span className="min-w-0">
                                <span className="block text-sm font-black text-slate-900">选择 Excel 导入</span>
                                <span className="mt-1 block text-xs font-semibold leading-5 text-slate-600">{pending ? "正在导入，请稍候。" : "支持 .xlsx 和 .xlsm，导入后会刷新企业列表。"}</span>
                            </span>
                        </button>
                    </div>
                    <div className="rounded-2xl border border-blue-100 bg-blue-50 p-4">
                        <div className="flex items-start gap-3">
                            <div className="grid size-10 shrink-0 place-items-center rounded-xl bg-blue-600 text-white">
                                <FileSpreadsheet className="size-5" />
                            </div>
                            <div className="min-w-0">
                                <div className="text-sm font-black text-slate-900">支持的 Excel 列</div>
                                <div className="mt-1 text-sm font-semibold leading-6 text-slate-600">
                                    企业名称、简称、行业、企业类型、区域、官网、监控级别、描述。企业名称必填，企业编码可选；如果企业编码或同名企业已存在，会更新现有档案。
                                </div>
                            </div>
                        </div>
                    </div>
                    {result ? (
                        <>
                            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                                <ImportStat label="识别行数" value={result.total_rows} />
                                <ImportStat label="新增" value={result.created_count} />
                                <ImportStat label="更新" value={result.updated_count} />
                                <ImportStat label="跳过" value={result.skipped_count} />
                            </div>
                            {result.errors.length > 0 ? (
                                <div className="max-h-52 overflow-auto rounded-2xl border border-red-100 bg-red-50 p-3">
                                    <div className="mb-2 text-sm font-black text-red-700">需要处理的行</div>
                                    <div className="space-y-2">
                                        {result.errors.slice(0, 20).map((error) => (
                                            <div key={`${error.row_no}-${error.reason}`} className="text-sm font-semibold text-red-700">
                                                第 {error.row_no} 行：{error.reason}
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            ) : null}
                        </>
                    ) : null}
                </div>
                <DialogFooter>
                    <Button type="button" className="bg-primary text-primary-foreground" onClick={() => onOpenChange(false)}>
                        关闭
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

function ImportStat({ label, value }: { label: string; value: number }) {
    return (
        <div className="rounded-2xl border border-slate-100 bg-white p-4 text-center">
            <div className="text-2xl font-black text-slate-950">{value}</div>
            <div className="mt-1 text-xs font-bold text-slate-500">{label}</div>
        </div>
    );
}

function Field({ label, value, onChange, required, placeholder }: { label: string; value: string; onChange: (value: string) => void; required?: boolean; placeholder?: string }) {
    return (
        <label className="grid gap-2">
            <span className="text-sm font-bold text-slate-700">{label}</span>
            <Input required={required} placeholder={placeholder} className="h-11 rounded-xl border-slate-200 bg-white shadow-none" value={value} onChange={(event) => onChange(event.target.value)} />
        </label>
    );
}

function SectionTitle({ title }: { title: string }) {
    return <h2 className="mb-4 text-xl font-black text-slate-900">{title}</h2>;
}

function EmptyPanel({ text }: { text: string }) {
    return <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50 px-4 py-8 text-center text-sm font-semibold text-slate-500">{text}</div>;
}

const emptyMetrics = [
    { key: "recent_intelligence", label: "近30天情报", value: 0, compare_label: "当前企业", delta: 0 },
    { key: "candidate_count", label: "候选情报", value: 0, compare_label: "待审核/已沉淀", delta: 0 },
    { key: "data_sources", label: "关联数据源", value: 0, compare_label: "可采集来源", delta: 0 },
    { key: "high_importance", label: "高关注情报", value: 0, compare_label: "正式情报", delta: 0 },
];

function metricIcon(key: string) {
    if (key === "candidate_count") {
        return <Tags className="size-6" />;
    }
    if (key === "data_sources") {
        return <Database className="size-6" />;
    }
    if (key === "high_importance") {
        return <Building2 className="size-6" />;
    }
    return <FileText className="size-6" />;
}

function formatDelta(value: number) {
    if (value > 0) {
        return `+${value}`;
    }
    return String(value);
}

function parseOptionalNumber(value: string) {
    if (!value) {
        return undefined;
    }
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : undefined;
}

function buildTrendPoints(timeline: Array<{ publish_time?: string | null; create_time: string }>) {
    const today = new Date();
    const points = Array.from({ length: 7 }, (_, index) => {
        const date = new Date(today);
        date.setDate(today.getDate() - (6 - index));
        const key = date.toISOString().slice(0, 10);
        return { key, label: `${date.getMonth() + 1}-${date.getDate()}`, count: 0 };
    });
    for (const item of timeline) {
        const key = new Date(item.publish_time ?? item.create_time).toISOString().slice(0, 10);
        const target = points.find((point) => point.key === key);
        if (target) {
            target.count += 1;
        }
    }
    return points;
}

function downloadBlob(file: Blob, fileName: string) {
    const url = URL.createObjectURL(file);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = fileName;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
}
