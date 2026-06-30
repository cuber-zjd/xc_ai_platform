import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Check, Loader2, Pencil, Play, Plus, Search, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { cn } from "@/lib/utils";

import type { InsightChannelRead, InsightMonitorConfigCreate, InsightMonitorConfigRead } from "../api";
import { SectionCard } from "../components";
import {
    useInsightChannels,
    useInsightCreateMonitorConfig,
    useInsightDeleteMonitorConfig,
    useInsightMonitorConfigs,
    useInsightSearchDiscovery,
    useInsightUpdateMonitorConfig,
} from "../hooks";
import { PageContainer } from "../layout/PageContainer";

const pageSize = 12;

const monitorTypeOptions = [
    { value: "enterprise", label: "企业监测" },
    { value: "industry", label: "行业主题" },
    { value: "policy", label: "政策主题" },
    { value: "technology", label: "技术专利" },
    { value: "product", label: "产品新品" },
    { value: "public_opinion", label: "综合舆情" },
    { value: "custom", label: "自定义" },
];

const relationOptions = [
    { value: "customer", label: "客户" },
    { value: "potential_customer", label: "潜在客户" },
    { value: "competitor", label: "竞对" },
    { value: "partner", label: "合作伙伴" },
    { value: "supplier", label: "供应商" },
    { value: "watch", label: "关注对象" },
];

const frequencyOptions = [
    { value: "manual", label: "手动" },
    { value: "daily", label: "每日" },
    { value: "weekly", label: "每周" },
    { value: "monthly", label: "每月" },
];

const strengthOptions = [
    { value: "light", label: "轻量" },
    { value: "standard", label: "标准" },
    { value: "deep", label: "深度" },
    { value: "structured", label: "结构化" },
];

const statusOptions = [
    { value: "active", label: "启用" },
    { value: "disabled", label: "停用" },
];

const visibilityOptions = [
    { value: "private", label: "仅自己" },
    { value: "assigned", label: "指定可见" },
    { value: "dept", label: "部门可见" },
    { value: "public", label: "公开" },
];

const monitorModules = [
    { key: "企业新闻", type: "enterprise", label: "企业新闻", description: "媒体报道、公告、市场动态" },
    { key: "官网动态", type: "enterprise", label: "官网动态", description: "官网新闻、产品、活动和招聘等公开动态" },
    { key: "经营财经", type: "enterprise", label: "经营财经", description: "财报、融资、交易所和经营信息" },
    { key: "专利技术", type: "technology", label: "专利技术", description: "专利库、技术论文和研发趋势" },
    { key: "电商新品", type: "product", label: "电商新品", description: "电商平台新品、价格和规格变化" },
    { key: "行业资讯", type: "industry", label: "行业资讯", description: "行业媒体、协会和市场资讯" },
    { key: "政策监管", type: "policy", label: "政策监管", description: "政府、监管、标准和公告文件" },
    { key: "综合舆情", type: "public_opinion", label: "综合舆情", description: "搜索、新闻和社媒公开舆情" },
];

const typeLabelMap = Object.fromEntries(monitorTypeOptions.map((item) => [item.value, item.label]));
const relationLabelMap = Object.fromEntries(relationOptions.map((item) => [item.value, item.label]));
const frequencyLabelMap = Object.fromEntries(frequencyOptions.map((item) => [item.value, item.label]));
const strengthLabelMap = Object.fromEntries(strengthOptions.map((item) => [item.value, item.label]));
const statusLabelMap = Object.fromEntries(statusOptions.map((item) => [item.value, item.label]));

interface MonitorFormState {
    config_name: string;
    monitor_type: string;
    object_name: string;
    relation_type: string;
    keywords: string;
    excluded_keywords: string;
    enabled_modules: string[];
    source_channel_ids: number[];
    monitor_strength: string;
    fetch_frequency: string;
    visibility_scope: string;
    status: string;
    ai_review_prompt: string;
}

const emptyForm: MonitorFormState = {
    config_name: "",
    monitor_type: "enterprise",
    object_name: "",
    relation_type: "customer",
    keywords: "",
    excluded_keywords: "招聘、广告招商",
    enabled_modules: ["企业新闻", "官网动态", "经营财经"],
    source_channel_ids: [],
    monitor_strength: "standard",
    fetch_frequency: "daily",
    visibility_scope: "assigned",
    status: "active",
    ai_review_prompt: "",
};

export function MonitorConfigPage() {
    const [keyword, setKeyword] = useState("");
    const [typeFilter, setTypeFilter] = useState("all");
    const [page, setPage] = useState(1);
    const [selectedId, setSelectedId] = useState<number | null>(null);
    const [dialogOpen, setDialogOpen] = useState(false);
    const [editingConfig, setEditingConfig] = useState<InsightMonitorConfigRead | null>(null);
    const [form, setForm] = useState<MonitorFormState>(emptyForm);

    const monitorQuery = useInsightMonitorConfigs({
        page,
        size: pageSize,
        keyword: keyword || undefined,
        monitor_type: typeFilter === "all" ? undefined : typeFilter,
    });
    const channelQuery = useInsightChannels({ page: 1, size: 200 });
    const createMutation = useInsightCreateMonitorConfig();
    const updateMutation = useInsightUpdateMonitorConfig();
    const deleteMutation = useInsightDeleteMonitorConfig();
    const testMutation = useInsightSearchDiscovery();

    const configs = monitorQuery.data?.items ?? [];
    const total = monitorQuery.data?.total ?? 0;
    const totalPages = Math.max(1, Math.ceil(total / pageSize));
    const selectedConfig = configs.find((item) => item.id === selectedId) ?? configs[0] ?? null;
    const channels = channelQuery.data?.items ?? [];

    useEffect(() => {
        if (page > totalPages) setPage(totalPages);
    }, [page, totalPages]);

    useEffect(() => {
        if (!selectedId && configs[0]) setSelectedId(configs[0].id);
    }, [configs, selectedId]);

    const handleCreate = () => {
        setEditingConfig(null);
        setForm(emptyForm);
        setDialogOpen(true);
    };

    const handleEdit = (config: InsightMonitorConfigRead) => {
        setEditingConfig(config);
        setForm({
            config_name: config.config_name,
            monitor_type: config.monitor_type,
            object_name: config.object_name ?? "",
            relation_type: normalizeRelationType(config.relation_type),
            keywords: config.keywords.join("、"),
            excluded_keywords: config.excluded_keywords.join("、"),
            enabled_modules: config.enabled_modules.length ? config.enabled_modules : moduleDefaultsForType(config.monitor_type),
            source_channel_ids: config.source_channel_ids,
            monitor_strength: config.monitor_strength,
            fetch_frequency: config.fetch_frequency,
            visibility_scope: config.visibility_scope,
            status: config.status,
            ai_review_prompt: config.ai_review_prompt ?? "",
        });
        setDialogOpen(true);
    };

    const handleSave = () => {
        const payload = buildPayload(form, channels);
        if (!payload.config_name.trim()) {
            toast.error("请填写配置名称");
            return;
        }
        if (!payload.object_name?.trim()) {
            toast.error("请填写监测对象");
            return;
        }
        const mutationOptions = {
            onSuccess: (result: InsightMonitorConfigRead) => {
                setSelectedId(result.id);
                setDialogOpen(false);
                setEditingConfig(null);
                setForm(emptyForm);
            },
            onError: (error: Error) => toast.error(error.message || "保存失败"),
        };
        if (editingConfig) {
            updateMutation.mutate({ configId: editingConfig.id, data: payload }, mutationOptions);
            return;
        }
        createMutation.mutate(payload, mutationOptions);
    };

    const handleDelete = (config: InsightMonitorConfigRead) => {
        if (!window.confirm(`确认删除“${config.config_name}”？`)) return;
        deleteMutation.mutate(config.id, {
            onSuccess: () => {
                if (selectedId === config.id) setSelectedId(null);
            },
            onError: (error) => toast.error(error instanceof Error ? error.message : "删除失败"),
        });
    };

    const handleTest = (config: InsightMonitorConfigRead) => {
        const query = buildTestQuery(config);
        if (!query) {
            toast.error("缺少监测对象或关键词，无法测试");
            return;
        }
        toast.info("开始轻量测试：百度资讯 + 博查搜索，不抓正文");
        testMutation.mutate(
            {
                query,
                channels: ["baidu_news", "bocha"],
                freshness: "oneWeek",
                max_results: 6,
                crawl_top_n: 0,
                include_keywords: config.keywords.slice(0, 6),
                exclude_keywords: config.excluded_keywords,
                enable_llm_filter: false,
            },
            {
                onSuccess: (result) => {
                    const baiduCount = result.hits.filter((item) => item.channel === "baidu_news").length;
                    const bochaCount = result.hits.filter((item) => item.channel === "bocha").length;
                    toast.success(`测试完成：命中 ${result.hits.length} 条，百度 ${baiduCount} 条，博查 ${bochaCount} 条`);
                },
                onError: (error) => toast.error(error instanceof Error ? error.message : "测试失败"),
            },
        );
    };

    const isMutating = createMutation.isPending || updateMutation.isPending;

    return (
        <PageContainer className="insight-page-locked flex flex-col gap-3">
            <div className="flex shrink-0 flex-col gap-3 rounded-2xl border border-slate-200 bg-white p-3 shadow-[0_8px_24px_rgba(30,74,120,0.05)] xl:flex-row xl:items-center">
                <div className="flex min-w-0 flex-1 items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-3">
                    <Search className="size-4 shrink-0 text-slate-400" />
                    <Input
                        value={keyword}
                        onChange={(event) => {
                            setKeyword(event.target.value);
                            setPage(1);
                        }}
                        className="h-10 border-0 bg-transparent px-0 shadow-none focus-visible:ring-0"
                        placeholder="搜索监测对象、关键词或配置名称"
                    />
                </div>
                <InsightSelect value={typeFilter} onValueChange={(value) => { setTypeFilter(value); setPage(1); }} className="w-full xl:w-44">
                    <SelectItem value="all">全部监测类型</SelectItem>
                    {monitorTypeOptions.map((item) => (
                        <SelectItem key={item.value} value={item.value}>{item.label}</SelectItem>
                    ))}
                </InsightSelect>
                <Button type="button" className="h-10 rounded-xl" onClick={handleCreate}>
                    <Plus className="size-4" />
                    新增监测
                </Button>
            </div>

            <div className="grid min-h-0 flex-1 grid-rows-[minmax(220px,0.42fr)_minmax(0,1fr)] gap-3 xl:grid-cols-[390px_minmax(0,1fr)] xl:grid-rows-1 2xl:grid-cols-[420px_minmax(0,1fr)]">
                <SectionCard className="flex min-h-0 flex-col p-0">
                    <div className="flex shrink-0 items-center justify-between border-b border-slate-100 px-4 py-3">
                        <div className="text-sm font-black text-slate-900">监测对象</div>
                        <div className="text-xs font-bold text-slate-500">{total} 个</div>
                    </div>
                    <div className="min-h-0 flex-1 overflow-y-auto p-2">
                        {monitorQuery.isLoading ? (
                            <div className="flex h-40 items-center justify-center text-sm font-semibold text-slate-500">
                                <Loader2 className="mr-2 size-4 animate-spin" />
                                正在读取监测配置
                            </div>
                        ) : configs.length ? (
                            <div className="space-y-2">
                                {configs.map((config) => (
                                    <button
                                        key={config.id}
                                        type="button"
                                        className={cn(
                                            "w-full rounded-xl border p-3 text-left transition",
                                            selectedConfig?.id === config.id ? "border-blue-200 bg-blue-50/80" : "border-slate-100 bg-white hover:border-blue-100 hover:bg-slate-50",
                                        )}
                                        onClick={() => setSelectedId(config.id)}
                                    >
                                        <div className="flex items-start justify-between gap-2">
                                            <div className="min-w-0">
                                                <div className="truncate text-sm font-black text-slate-950">{config.config_name}</div>
                                                <div className="mt-1 truncate text-xs font-bold text-slate-500">{config.object_name || "未填写对象"}</div>
                                            </div>
                                            <Badge className={cn("shrink-0", config.status === "active" ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-slate-200 bg-slate-100 text-slate-500")} variant="outline">
                                                {statusLabelMap[config.status] ?? config.status}
                                            </Badge>
                                        </div>
                                        <div className="mt-3 flex flex-wrap gap-1.5">
                                            {config.enabled_modules.slice(0, 4).map((module) => (
                                                <span key={module} className="rounded-md bg-slate-100 px-2 py-1 text-[11px] font-bold text-slate-600">{module}</span>
                                            ))}
                                        </div>
                                    </button>
                                ))}
                            </div>
                        ) : (
                            <div className="flex h-40 items-center justify-center text-sm font-semibold text-slate-500">暂无监测配置</div>
                        )}
                    </div>
                    <div className="flex shrink-0 items-center justify-between border-t border-slate-100 px-3 py-2 text-xs font-bold text-slate-500">
                        <span>{page} / {totalPages}</span>
                        <div className="flex gap-2">
                            <Button type="button" variant="outline" size="sm" className="h-8 rounded-lg" disabled={page <= 1} onClick={() => setPage((value) => Math.max(1, value - 1))}>上一页</Button>
                            <Button type="button" variant="outline" size="sm" className="h-8 rounded-lg" disabled={page >= totalPages} onClick={() => setPage((value) => Math.min(totalPages, value + 1))}>下一页</Button>
                        </div>
                    </div>
                </SectionCard>

                <SectionCard className="flex min-h-0 flex-col p-0">
                    {selectedConfig ? (
                        <MonitorDetail config={selectedConfig} channels={channels} onEdit={handleEdit} onDelete={handleDelete} onTest={handleTest} deleting={deleteMutation.isPending} testing={testMutation.isPending} />
                    ) : (
                        <div className="flex min-h-0 flex-1 items-center justify-center text-sm font-semibold text-slate-500">选择一个监测对象查看详情</div>
                    )}
                </SectionCard>
            </div>

            <Dialog
                open={dialogOpen}
                onOpenChange={(open) => {
                    setDialogOpen(open);
                    if (!open) {
                        setEditingConfig(null);
                        setForm(emptyForm);
                    }
                }}
            >
                <DialogContent className="max-h-[92vh] overflow-hidden p-0 sm:max-w-5xl">
                    <DialogHeader className="border-b border-slate-100 px-5 py-4">
                        <DialogTitle>{editingConfig ? "编辑监测配置" : "新增监测配置"}</DialogTitle>
                    </DialogHeader>
                    <MonitorConfigForm form={form} channels={channels} isMutating={isMutating} onChange={(patch) => setForm((current) => ({ ...current, ...patch }))} onSave={handleSave} onCancel={() => setDialogOpen(false)} />
                </DialogContent>
            </Dialog>
        </PageContainer>
    );
}

function MonitorDetail({ config, channels, onEdit, onDelete, onTest, deleting, testing }: { config: InsightMonitorConfigRead; channels: InsightChannelRead[]; onEdit: (config: InsightMonitorConfigRead) => void; onDelete: (config: InsightMonitorConfigRead) => void; onTest: (config: InsightMonitorConfigRead) => void; deleting: boolean; testing: boolean }) {
    const selectedChannels = channels.filter(
        (channel) => config.source_channel_ids.includes(channel.id) || config.enabled_modules.some((module) => channel.applicable_scenarios.includes(module)),
    );
    return (
        <>
            <div className="flex shrink-0 flex-col gap-3 border-b border-slate-100 px-4 py-3 lg:flex-row lg:items-start lg:justify-between">
                <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                        <h2 className="truncate text-lg font-black text-slate-950">{config.config_name}</h2>
                        <Badge variant="outline" className="border-blue-100 bg-blue-50 text-blue-700">{typeLabelMap[config.monitor_type] ?? config.monitor_type}</Badge>
                        <Badge variant="outline" className="border-slate-200 bg-slate-50 text-slate-600">{relationLabelMap[config.relation_type ?? ""] ?? config.relation_type ?? "关注对象"}</Badge>
                    </div>
                    <div className="mt-1 truncate text-sm font-semibold text-slate-500">{config.object_name || "未填写监测对象"}</div>
                </div>
                <div className="flex shrink-0 gap-2">
                    <Button type="button" variant="outline" size="sm" className="h-9 rounded-lg bg-white text-blue-700" disabled={testing} onClick={() => onTest(config)}>
                        {testing ? <Loader2 className="size-4 animate-spin" /> : <Play className="size-4" />}
                        测试采集
                    </Button>
                    <Button type="button" variant="outline" size="sm" className="h-9 rounded-lg bg-white" onClick={() => onEdit(config)}>
                        <Pencil className="size-4" />
                        编辑
                    </Button>
                    <Button type="button" variant="outline" size="sm" className="h-9 rounded-lg bg-white text-red-600 hover:text-red-700" disabled={deleting} onClick={() => onDelete(config)}>
                        <Trash2 className="size-4" />
                        删除
                    </Button>
                </div>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto p-4">
                <div className="grid gap-3 sm:grid-cols-2 2xl:grid-cols-4">
                    <Metric label="监测强度" value={strengthLabelMap[config.monitor_strength] ?? config.monitor_strength} />
                    <Metric label="采集频率" value={frequencyLabelMap[config.fetch_frequency] ?? config.fetch_frequency} />
                    <Metric label="执行源" value={`${config.execution_source_count} 个`} />
                    <Metric label="下次执行" value={formatDateTime(config.next_run_time)} />
                </div>

                <div className="mt-4 grid gap-4 2xl:grid-cols-[minmax(0,1fr)_320px]">
                    <div className="space-y-3">
                        <div className="text-sm font-black text-slate-900">监测模块</div>
                        <div className="grid gap-3 2xl:grid-cols-2">
                            {config.enabled_modules.map((module) => {
                                const moduleChannels = selectedChannels.filter((channel) => channel.applicable_scenarios.includes(module));
                                return (
                                    <div key={module} className="rounded-xl border border-slate-200 bg-white p-3">
                                        <div className="flex items-center justify-between gap-2">
                                            <div className="font-black text-slate-900">{module}</div>
                        <Badge variant="outline" className="border-slate-200 bg-slate-50 text-slate-500">{moduleChannels.length} 个来源</Badge>
                                        </div>
                                        <div className="mt-3 flex items-center justify-between gap-3 rounded-lg bg-slate-50 px-3 py-2">
                                            <div className="min-w-0 truncate text-xs font-semibold text-slate-500">{channelSummary(moduleChannels)}</div>
                                            <WebsiteInfo channels={moduleChannels} />
                                        </div>
                                    </div>
                                );
                            })}
                        </div>
                    </div>
                    <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
                        <div className="text-sm font-black text-slate-900">AI 口径</div>
                        <div className="mt-3 rounded-lg bg-white p-3 text-sm font-semibold leading-6 text-slate-700">
                            {config.ai_review_prompt || defaultPrompt(config.relation_type || "watch")}
                        </div>
                        <div className="mt-4 text-sm font-black text-slate-900">关键词</div>
                        <div className="mt-2 flex flex-wrap gap-2">
                            {config.keywords.map((item) => <span key={item} className="rounded-lg bg-white px-2.5 py-1.5 text-xs font-bold text-slate-600">{item}</span>)}
                        </div>
                    </div>
                </div>
            </div>
        </>
    );
}

function MonitorConfigForm({ form, channels, isMutating, onChange, onSave, onCancel }: { form: MonitorFormState; channels: InsightChannelRead[]; isMutating: boolean; onChange: (patch: Partial<MonitorFormState>) => void; onSave: () => void; onCancel: () => void }) {
    const moduleOptions = useMemo(() => moduleOptionsForType(form.monitor_type), [form.monitor_type]);
    const moduleChannelMap = useMemo(() => {
        return Object.fromEntries(moduleOptions.map((module) => [module.key, channels.filter((channel) => channel.applicable_scenarios.includes(module.key))]));
    }, [channels, moduleOptions]);
    const coveredCount = coveredChannelIds(form.enabled_modules, channels).length;

    const toggleModule = (module: string) => {
        const enabled = form.enabled_modules.includes(module);
        const nextModules = enabled ? form.enabled_modules.filter((item) => item !== module) : [...form.enabled_modules, module];
        onChange({ enabled_modules: nextModules });
    };

    return (
        <div className="flex max-h-[calc(92vh-72px)] min-h-0 flex-col">
            <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
                <div className="grid gap-3 lg:grid-cols-3">
                    <Field label="配置名称">
                        <Input value={form.config_name} onChange={(event) => onChange({ config_name: event.target.value })} placeholder="如 嘉吉企业监测" />
                    </Field>
                    <Field label="监测类型">
                        <InsightSelect value={form.monitor_type} onValueChange={(value) => onChange({ monitor_type: value, enabled_modules: moduleDefaultsForType(value) })}>
                            {monitorTypeOptions.map((item) => <SelectItem key={item.value} value={item.value}>{item.label}</SelectItem>)}
                        </InsightSelect>
                    </Field>
                    <Field label="关系类型">
                        <InsightSelect value={form.relation_type} onValueChange={(value) => onChange({ relation_type: value, ai_review_prompt: form.ai_review_prompt || defaultPrompt(value) })}>
                            {relationOptions.map((item) => <SelectItem key={item.value} value={item.value}>{item.label}</SelectItem>)}
                        </InsightSelect>
                    </Field>
                    <Field label="监测对象">
                        <Input value={form.object_name} onChange={(event) => onChange({ object_name: event.target.value })} placeholder="企业、行业、产品或主题名称" />
                    </Field>
                    <Field label="采集频率">
                        <InsightSelect value={form.fetch_frequency} onValueChange={(value) => onChange({ fetch_frequency: value })}>
                            {frequencyOptions.map((item) => <SelectItem key={item.value} value={item.value}>{item.label}</SelectItem>)}
                        </InsightSelect>
                    </Field>
                    <Field label="监测强度">
                        <InsightSelect value={form.monitor_strength} onValueChange={(value) => onChange({ monitor_strength: value })}>
                            {strengthOptions.map((item) => <SelectItem key={item.value} value={item.value}>{item.label}</SelectItem>)}
                        </InsightSelect>
                    </Field>
                    <Field label="关键词">
                        <Input value={form.keywords} onChange={(event) => onChange({ keywords: event.target.value })} placeholder="多个关键词用顿号或逗号分隔" />
                    </Field>
                    <Field label="排除词">
                        <Input value={form.excluded_keywords} onChange={(event) => onChange({ excluded_keywords: event.target.value })} placeholder="如 招聘、广告招商" />
                    </Field>
                    <Field label="可见范围">
                        <InsightSelect value={form.visibility_scope} onValueChange={(value) => onChange({ visibility_scope: value })}>
                            {visibilityOptions.map((item) => <SelectItem key={item.value} value={item.value}>{item.label}</SelectItem>)}
                        </InsightSelect>
                    </Field>
                </div>

                <div className="mt-4 rounded-2xl border border-slate-200 bg-slate-50 p-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                        <div>
                            <div className="text-sm font-black text-slate-900">监测模块和网站</div>
                            <div className="mt-1 text-xs font-semibold text-slate-500">只需要选择业务模块；模块下的搜索源和网站由系统自动覆盖并保存，不需要逐个配置。</div>
                        </div>
                        <Badge variant="outline" className="border-blue-100 bg-white text-blue-700">覆盖 {coveredCount} 个来源</Badge>
                    </div>
                    <div className="mt-3 grid gap-3 lg:grid-cols-2">
                        {moduleOptions.map((module) => {
                            const enabled = form.enabled_modules.includes(module.key);
                            const moduleChannels = moduleChannelMap[module.key] ?? [];
                            return (
                                <div key={module.key} className={cn("rounded-xl border bg-white p-3 transition", enabled ? "border-blue-200 shadow-[0_8px_20px_rgba(29,116,255,0.08)]" : "border-slate-200")}>
                                    <button type="button" className="flex w-full items-start justify-between gap-3 text-left" onClick={() => toggleModule(module.key)}>
                                        <span className="min-w-0">
                                            <span className="block text-sm font-black text-slate-900">{module.label}</span>
                                            <span className="mt-1 block text-xs font-semibold leading-5 text-slate-500">{module.description}</span>
                                            <span className="mt-2 block truncate text-xs font-semibold text-slate-400">{channelSummary(moduleChannels)}</span>
                                        </span>
                                        <span className="flex shrink-0 items-center gap-2">
                                            <WebsiteInfo channels={moduleChannels} />
                                            <span className={cn("grid size-6 place-items-center rounded-full border", enabled ? "border-blue-500 bg-blue-600 text-white" : "border-slate-200 bg-white text-transparent")}>
                                                <Check className="size-4" />
                                            </span>
                                        </span>
                                    </button>
                                </div>
                            );
                        })}
                    </div>
                </div>

                <div className="mt-4 grid gap-3 lg:grid-cols-[minmax(0,1fr)_180px]">
                    <Field label="AI 入库口径">
                        <textarea
                            value={form.ai_review_prompt}
                            onChange={(event) => onChange({ ai_review_prompt: event.target.value })}
                            className="min-h-28 w-full resize-y rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-semibold leading-6 text-slate-700 outline-none focus:border-blue-300 focus:ring-4 focus:ring-blue-100"
                            placeholder={defaultPrompt(form.relation_type)}
                        />
                    </Field>
                    <Field label="状态">
                        <InsightSelect value={form.status} onValueChange={(value) => onChange({ status: value })}>
                            {statusOptions.map((item) => <SelectItem key={item.value} value={item.value}>{item.label}</SelectItem>)}
                        </InsightSelect>
                    </Field>
                </div>
            </div>
            <div className="flex shrink-0 justify-end gap-2 border-t border-slate-100 px-5 py-4">
                <Button type="button" variant="outline" className="rounded-xl" onClick={onCancel}>取消</Button>
                <Button type="button" className="rounded-xl" disabled={isMutating} onClick={onSave}>
                    {isMutating ? <Loader2 className="size-4 animate-spin" /> : <Check className="size-4" />}
                    保存配置
                </Button>
            </div>
        </div>
    );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
    return (
        <label className="block min-w-0">
            <span className="mb-1.5 block text-xs font-black text-slate-500">{label}</span>
            {children}
        </label>
    );
}

function InsightSelect({ value, onValueChange, children, className }: { value: string; onValueChange: (value: string) => void; children: ReactNode; className?: string }) {
    return (
        <Select value={value} onValueChange={onValueChange}>
            <SelectTrigger className={cn("h-10 w-full rounded-xl border-slate-200 bg-white px-3 text-sm font-bold text-slate-700 shadow-none", className)}>
                <SelectValue />
            </SelectTrigger>
            <SelectContent className="rounded-xl border-slate-200 bg-white p-1 shadow-xl">
                {children}
            </SelectContent>
        </Select>
    );
}

function Metric({ label, value }: { label: string; value: string }) {
    return (
        <div className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2">
            <div className="text-xs font-bold text-slate-400">{label}</div>
            <div className="mt-1 truncate text-sm font-black text-slate-800">{value}</div>
        </div>
    );
}

function WebsiteInfo({ channels }: { channels: InsightChannelRead[] }) {
    return (
        <span className="group relative shrink-0" tabIndex={0} onClick={(event) => event.stopPropagation()}>
            <span className="grid size-5 cursor-help place-items-center rounded-full border border-blue-100 bg-white text-xs font-black text-blue-600">!</span>
            <span className="absolute right-0 top-full z-50 hidden w-80 pt-2 group-hover:block group-focus-within:block">
                <span className="block rounded-xl border border-slate-200 bg-white p-3 text-left shadow-xl">
                <span className="mb-2 block text-xs font-black text-slate-800">覆盖来源</span>
                    {channels.length ? (
                        <span className="block max-h-64 space-y-1 overflow-y-auto pr-1">
                            {channels.map((channel) => (
                                <span key={channel.id} className="block min-w-0 rounded-lg bg-slate-50 px-2 py-1.5">
                                    <span className="block truncate text-xs font-bold text-slate-700">{channel.channel_name}</span>
                                    <span className="mt-0.5 block truncate text-[11px] font-semibold text-slate-400">{channelSourceHint(channel)}</span>
                                </span>
                            ))}
                        </span>
                    ) : (
                    <span className="block rounded-lg bg-slate-50 px-2 py-1.5 text-xs font-semibold text-slate-500">暂无渠道库来源，将使用模块默认发现能力。</span>
                    )}
                </span>
            </span>
        </span>
    );
}

function channelSummary(channels: InsightChannelRead[]) {
    if (!channels.length) return "来源：暂无渠道库来源";
    const names = channels.slice(0, 4).map((channel) => channel.channel_name).join("、");
    return `来源：${names}${channels.length > 4 ? `等 ${channels.length} 个` : ""}`;
}

function channelSourceHint(channel: InsightChannelRead) {
    if (channel.channel_type === "search_engine") return channel.comment || "搜索发现源，按关键词发现候选链接";
    return channel.channel_url || "未配置网址";
}

function moduleOptionsForType(type: string) {
    if (type === "enterprise") return monitorModules.filter((item) => ["enterprise", "technology", "product"].includes(item.type));
    if (type === "industry") return monitorModules.filter((item) => ["industry", "public_opinion"].includes(item.type));
    if (type === "policy") return monitorModules.filter((item) => item.type === "policy");
    if (type === "technology") return monitorModules.filter((item) => item.type === "technology");
    if (type === "product") return monitorModules.filter((item) => item.type === "product");
    if (type === "public_opinion") return monitorModules.filter((item) => item.type === "public_opinion");
    return monitorModules;
}

function moduleDefaultsForType(type: string) {
    return moduleOptionsForType(type).slice(0, type === "enterprise" ? 5 : 2).map((item) => item.key);
}

function coveredChannelIds(modules: string[], channels: InsightChannelRead[]) {
    return Array.from(
        new Set(
            channels
                .filter((channel) => modules.some((module) => channel.applicable_scenarios.includes(module)))
                .map((channel) => channel.id),
        ),
    );
}

function normalizeRelationType(value?: string | null) {
    const relationMap: Record<string, string> = {
        客户: "customer",
        潜在客户: "potential_customer",
        竞对: "competitor",
        竞争对手: "competitor",
        合作伙伴: "partner",
        供应商: "supplier",
        关注对象: "watch",
    };
    if (!value) return "watch";
    if (relationOptions.some((item) => item.value === value)) return value;
    return relationMap[value] ?? "watch";
}

function buildPayload(form: MonitorFormState, channels: InsightChannelRead[]): InsightMonitorConfigCreate {
    const keywords = splitText(form.keywords || form.object_name);
    return {
        config_name: form.config_name,
        monitor_type: form.monitor_type,
        object_type: form.monitor_type === "enterprise" ? "company" : "topic",
        object_name: form.object_name,
        relation_type: form.relation_type,
        enabled_modules: form.enabled_modules,
        keywords,
        excluded_keywords: splitText(form.excluded_keywords),
        source_channel_ids: coveredChannelIds(form.enabled_modules, channels),
        monitor_strength: form.monitor_strength,
        fetch_frequency: form.fetch_frequency,
        ai_review_prompt: form.ai_review_prompt || defaultPrompt(form.relation_type),
        ai_review_policy: "ai_approve",
        visibility_scope: form.visibility_scope,
        generation_mode: "user_created",
        status: form.status,
    };
}

function buildTestQuery(config: InsightMonitorConfigRead) {
    const terms = uniqueStrings([
        config.object_name,
        ...config.keywords,
        ...config.enabled_modules.slice(0, 3),
    ]).filter(Boolean);
    return terms.slice(0, 6).join(" ");
}

function splitText(value: string) {
    return value.split(/[、,，\n]/).map((item) => item.trim()).filter(Boolean);
}

function uniqueStrings(values: Array<string | null | undefined>) {
    const result: string[] = [];
    const seen = new Set<string>();
    for (const item of values) {
        const value = (item || "").trim();
        if (!value || seen.has(value)) continue;
        seen.add(value);
        result.push(value);
    }
    return result;
}

function defaultPrompt(relationType: string) {
    const relationLabel = relationLabelMap[relationType] ?? "关注对象";
    return `当前对象按“${relationLabel}”关系监测。只收录与新品发布、技术专利、价格策略、渠道动作、营销活动、产能扩张、客户合作、风险事件和战略方向相关的信息；无关转载、低价值财经快讯、重复内容和泛泛介绍进入候选情报。`;
}

function formatDateTime(value?: string | null) {
    if (!value) return "暂无";
    return new Date(value).toLocaleString("zh-CN", { hour12: false });
}
