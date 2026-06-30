import { useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, CircleSlash, Database, Loader2, Pencil, Plus, RefreshCw, Save, Settings, Sparkles, Tag, Trash2, XCircle } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";

import { SectionCard } from "../components";
import {
    useInsightChannels,
    useInsightCreateChannel,
    useInsightCreateDataSource,
    useInsightCreateMonitorConfig,
    useInsightCreateTag,
    useInsightDeleteChannel,
    useInsightDeleteDataSource,
    useInsightDeleteMonitorConfig,
    useInsightDictionaryOverview,
    useInsightDisableTag,
    useInsightDataSources,
    useInsightMonitorConfigs,
    useInsightSeedDefaultChannels,
    useInsightSettingsStatus,
    useInsightSyncLegacyDataSources,
    useInsightUpdateDataSource,
    useInsightUpdateMonitorConfig,
    useInsightUpdateChannel,
    useInsightUpdateTag,
} from "../hooks";
import { PageContainer } from "../layout/PageContainer";
import type {
    InsightChannelCreate,
    InsightChannelRead,
    InsightDataSourceCreate,
    InsightDataSourceRead,
    InsightIntelligenceTypeRead,
    InsightMonitorConfigCreate,
    InsightMonitorConfigRead,
    InsightSettingsStatusItem,
    InsightTagRead,
} from "../api";

const statusMeta = {
    ok: {
        label: "正常",
        className: "border-emerald-200 bg-emerald-50 text-emerald-700",
        icon: CheckCircle2,
    },
    warning: {
        label: "需关注",
        className: "border-amber-200 bg-amber-50 text-amber-700",
        icon: AlertTriangle,
    },
    disabled: {
        label: "未启用",
        className: "border-slate-200 bg-slate-100 text-slate-600",
        icon: CircleSlash,
    },
};

const tagTypeLabels: Record<string, string> = {
    business: "业务标签",
    topic: "主题标签",
    risk: "风险标签",
    product: "产品标签",
};

const channelTypeOptions = [
    { value: "", label: "全部渠道类型" },
    { value: "enterprise_official", label: "企业官网" },
    { value: "industry_media", label: "行业媒体" },
    { value: "finance_news", label: "财经资讯" },
    { value: "policy_regulation", label: "政策监管" },
    { value: "patent_technology", label: "专利技术" },
    { value: "general_news", label: "综合资讯" },
    { value: "ecommerce", label: "电商新品" },
    { value: "wechat_public_account", label: "公众号" },
    { value: "database", label: "资料库" },
    { value: "search_engine", label: "搜索发现" },
    { value: "custom", label: "自定义" },
];

const monitorScenarioOptions = [
    { value: "", label: "全部监测分类" },
    { value: "企业新闻", label: "企业监测 / 企业新闻" },
    { value: "官网动态", label: "企业监测 / 官网动态" },
    { value: "经营财经", label: "企业监测 / 经营财经" },
    { value: "专利技术", label: "企业监测 / 专利技术" },
    { value: "电商新品", label: "企业监测 / 电商新品" },
    { value: "行业资讯", label: "主题监测 / 行业资讯" },
    { value: "政策监管", label: "主题监测 / 政策监管" },
    { value: "技术专利", label: "主题监测 / 技术专利" },
    { value: "综合舆情", label: "主题监测 / 综合舆情" },
];

const collectionMethodOptions = [
    { value: "search", label: "搜索发现" },
    { value: "list_page", label: "列表页抓取" },
    { value: "detail_page", label: "详情页抓取" },
    { value: "api", label: "API" },
    { value: "rss", label: "RSS" },
    { value: "file_import", label: "文件导入" },
    { value: "manual_import", label: "人工导入" },
    { value: "adapter", label: "独立适配器" },
    { value: "pending", label: "待接入" },
];

const accessStatusOptions = [
    { value: "", label: "全部接入状态" },
    { value: "supported", label: "已支持" },
    { value: "partial", label: "部分支持" },
    { value: "pending", label: "待接入" },
    { value: "unsupported", label: "暂不支持" },
];

const executionStatusOptions = [
    { value: "", label: "全部状态" },
    { value: "enabled", label: "已启用" },
    { value: "disabled", label: "已停用" },
];

const accessStatusLabels = Object.fromEntries(accessStatusOptions.filter((item) => item.value).map((item) => [item.value, item.label]));
const channelTypeLabels = Object.fromEntries(channelTypeOptions.filter((item) => item.value).map((item) => [item.value, item.label]));
const collectionMethodLabels = Object.fromEntries(collectionMethodOptions.map((item) => [item.value, item.label]));
const legacyCollectionSourceTypeLabels: Record<string, string> = {
    baidu_search: "百度搜索",
    bocha_news: "博查资讯",
    bocha_web: "博查网页",
    multi_news: "多源资讯",
};

const emptyChannelForm: ChannelFormState = {
    channel_name: "",
    channel_type: "industry_media",
    channel_url: "",
    applicable_scenarios: "",
    collection_method: "search",
    login_requirement: "none",
    access_status: "pending",
    default_trust_level: "medium",
    default_frequency: "daily",
    default_processing_policy: "ai_review",
    comment: "",
};

type SettingsTab = "status" | "channels" | "execution" | "monitoring" | "tags" | "types";

const settingsTabs: { key: SettingsTab; label: string }[] = [
    { key: "status", label: "配置状态" },
    { key: "channels", label: "渠道库" },
    { key: "execution", label: "执行源" },
    { key: "tags", label: "标签字典" },
    { key: "types", label: "情报类型" },
];

const channelPageSize = 12;
const executionPageSize = 12;
const monitorPageSize = 12;

const executionRoleOptions = [
    { value: "", label: "全部执行角色" },
    { value: "企业新闻", label: "企业新闻" },
    { value: "官网动态", label: "官网动态" },
    { value: "经营财经", label: "经营财经" },
    { value: "专利技术", label: "专利技术" },
    { value: "电商新品", label: "电商新品" },
    { value: "行业资讯", label: "行业资讯" },
    { value: "政策监管", label: "政策监管" },
    { value: "综合舆情", label: "综合舆情" },
];

const collectionSourceTypeOptions = [
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

const collectionSourceTypeLabels = {
    ...legacyCollectionSourceTypeLabels,
    ...Object.fromEntries(collectionSourceTypeOptions.map((item) => [item.value, item.label])),
};

const monitorTypeOptions = [
    { value: "", label: "全部监测类型" },
    { value: "enterprise", label: "企业监测" },
    { value: "industry", label: "行业主题" },
    { value: "policy", label: "政策主题" },
    { value: "technology", label: "技术专利" },
    { value: "product", label: "产品新品" },
    { value: "public_opinion", label: "综合舆情" },
    { value: "custom", label: "自定义" },
];

const monitorTypeLabels = Object.fromEntries(monitorTypeOptions.filter((item) => item.value).map((item) => [item.value, item.label]));
const executionRoleLabels = Object.fromEntries(executionRoleOptions.filter((item) => item.value).map((item) => [item.value, item.label]));

const emptyExecutionForm: ExecutionFormState = {
    source_name: "",
    source_type: "baidu_news",
    base_url: "",
    execution_role: "企业新闻",
    monitor_config_id: "",
    channel_id: "",
    fetch_frequency: "manual",
    status: "enabled",
    keywords: "",
};

const emptyMonitorForm: MonitorFormState = {
    config_name: "",
    monitor_type: "enterprise",
    object_type: "topic",
    object_name: "",
    relation_type: "",
    enabled_modules: "企业新闻、官网动态、经营财经",
    keywords: "",
    excluded_keywords: "招聘、广告招商",
    source_channel_ids: "",
    monitor_strength: "standard",
    fetch_frequency: "daily",
    ai_review_prompt: "",
    visibility_scope: "assigned",
    status: "active",
};

interface ChannelFormState {
    channel_name: string;
    channel_type: string;
    channel_url: string;
    applicable_scenarios: string;
    collection_method: string;
    login_requirement: string;
    access_status: string;
    default_trust_level: string;
    default_frequency: string;
    default_processing_policy: string;
    comment: string;
}

interface ExecutionFormState {
    source_name: string;
    source_type: string;
    base_url: string;
    execution_role: string;
    monitor_config_id: string;
    channel_id: string;
    fetch_frequency: string;
    status: string;
    keywords: string;
}

interface MonitorFormState {
    config_name: string;
    monitor_type: string;
    object_type: string;
    object_name: string;
    relation_type: string;
    enabled_modules: string;
    keywords: string;
    excluded_keywords: string;
    source_channel_ids: string;
    monitor_strength: string;
    fetch_frequency: string;
    ai_review_prompt: string;
    visibility_scope: string;
    status: string;
}

export function SettingsPage() {
    const statusQuery = useInsightSettingsStatus();
    const dictionaryQuery = useInsightDictionaryOverview();
    const [channelKeyword, setChannelKeyword] = useState("");
    const [channelScenario, setChannelScenario] = useState("");
    const [channelAccessStatus, setChannelAccessStatus] = useState("");
    const [channelPage, setChannelPage] = useState(1);
    const [executionKeyword, setExecutionKeyword] = useState("");
    const [executionRole, setExecutionRole] = useState("");
    const [executionStatus, setExecutionStatus] = useState("");
    const [executionPage, setExecutionPage] = useState(1);
    const [monitorKeyword, setMonitorKeyword] = useState("");
    const [monitorType, setMonitorType] = useState("");
    const [monitorStatus, setMonitorStatus] = useState("");
    const [monitorPage, setMonitorPage] = useState(1);
    const channelsQuery = useInsightChannels({
        page: channelPage,
        size: channelPageSize,
        keyword: channelKeyword || undefined,
        scenario: channelScenario || undefined,
        access_status: channelAccessStatus || undefined,
    });
    const channelOptionsQuery = useInsightChannels({
        page: 1,
        size: 200,
    });
    const executionSourcesQuery = useInsightDataSources({
        page: executionPage,
        size: executionPageSize,
        keyword: executionKeyword || undefined,
        execution_role: executionRole || undefined,
        status: executionStatus || undefined,
    });
    const monitorConfigsQuery = useInsightMonitorConfigs({
        page: monitorPage,
        size: monitorPageSize,
        keyword: monitorKeyword || undefined,
        monitor_type: monitorType || undefined,
        status: monitorStatus || undefined,
    });
    const monitorConfigOptionsQuery = useInsightMonitorConfigs({
        page: 1,
        size: 200,
        status: "enabled",
    });
    const createChannelMutation = useInsightCreateChannel();
    const updateChannelMutation = useInsightUpdateChannel();
    const deleteChannelMutation = useInsightDeleteChannel();
    const seedDefaultChannelsMutation = useInsightSeedDefaultChannels();
    const createExecutionMutation = useInsightCreateDataSource();
    const updateExecutionMutation = useInsightUpdateDataSource();
    const deleteExecutionMutation = useInsightDeleteDataSource();
    const syncLegacyMutation = useInsightSyncLegacyDataSources();
    const createMonitorMutation = useInsightCreateMonitorConfig();
    const updateMonitorMutation = useInsightUpdateMonitorConfig();
    const deleteMonitorMutation = useInsightDeleteMonitorConfig();
    const createTagMutation = useInsightCreateTag();
    const updateTagMutation = useInsightUpdateTag();
    const disableTagMutation = useInsightDisableTag();
    const sections = statusQuery.data?.sections ?? [];
    const dictionary = dictionaryQuery.data;
    const [newTagName, setNewTagName] = useState("");
    const [newTagType, setNewTagType] = useState("business");
    const [editingTagId, setEditingTagId] = useState<number | null>(null);
    const [editingTagName, setEditingTagName] = useState("");
    const [editingChannel, setEditingChannel] = useState<InsightChannelRead | null>(null);
    const [channelForm, setChannelForm] = useState<ChannelFormState>(emptyChannelForm);
    const [editingExecution, setEditingExecution] = useState<InsightDataSourceRead | null>(null);
    const [executionForm, setExecutionForm] = useState<ExecutionFormState>(emptyExecutionForm);
    const [editingMonitor, setEditingMonitor] = useState<InsightMonitorConfigRead | null>(null);
    const [monitorForm, setMonitorForm] = useState<MonitorFormState>(emptyMonitorForm);
    const [activeTab, setActiveTab] = useState<SettingsTab>("status");
    const [channelDialogOpen, setChannelDialogOpen] = useState(false);
    const [executionDialogOpen, setExecutionDialogOpen] = useState(false);
    const [monitorDialogOpen, setMonitorDialogOpen] = useState(false);

    const isMutating = createTagMutation.isPending || updateTagMutation.isPending || disableTagMutation.isPending;
    const isChannelMutating =
        createChannelMutation.isPending ||
        updateChannelMutation.isPending ||
        deleteChannelMutation.isPending ||
        seedDefaultChannelsMutation.isPending;
    const isExecutionMutating = createExecutionMutation.isPending || updateExecutionMutation.isPending || deleteExecutionMutation.isPending || syncLegacyMutation.isPending;
    const isMonitorMutating = createMonitorMutation.isPending || updateMonitorMutation.isPending || deleteMonitorMutation.isPending;
    const isRefreshing = statusQuery.isFetching || dictionaryQuery.isFetching || channelsQuery.isFetching || executionSourcesQuery.isFetching || monitorConfigsQuery.isFetching;
    const channelTotal = channelsQuery.data?.total ?? 0;
    const channelTotalPages = Math.max(1, Math.ceil(channelTotal / channelPageSize));
    const currentChannelPage = Math.min(channelPage, channelTotalPages);
    const executionTotal = executionSourcesQuery.data?.total ?? 0;
    const executionTotalPages = Math.max(1, Math.ceil(executionTotal / executionPageSize));
    const currentExecutionPage = Math.min(executionPage, executionTotalPages);
    const monitorTotal = monitorConfigsQuery.data?.total ?? 0;
    const monitorTotalPages = Math.max(1, Math.ceil(monitorTotal / monitorPageSize));
    const currentMonitorPage = Math.min(monitorPage, monitorTotalPages);

    useEffect(() => {
        if (channelPage > channelTotalPages) {
            setChannelPage(channelTotalPages);
        }
    }, [channelPage, channelTotalPages]);

    useEffect(() => {
        if (executionPage > executionTotalPages) {
            setExecutionPage(executionTotalPages);
        }
    }, [executionPage, executionTotalPages]);

    useEffect(() => {
        if (monitorPage > monitorTotalPages) {
            setMonitorPage(monitorTotalPages);
        }
    }, [monitorPage, monitorTotalPages]);

    const handleRefresh = () => {
        void statusQuery.refetch();
        void dictionaryQuery.refetch();
        void channelsQuery.refetch();
        void channelOptionsQuery.refetch();
        void executionSourcesQuery.refetch();
        void monitorConfigsQuery.refetch();
        void monitorConfigOptionsQuery.refetch();
    };

    const handleCreateTag = () => {
        const tagName = newTagName.trim();
        if (!tagName) return;
        createTagMutation.mutate(
            { tag_name: tagName, tag_type: newTagType },
            {
                onSuccess: () => {
                    setNewTagName("");
                    setNewTagType("business");
                },
            },
        );
    };

    const handleStartEdit = (tagItem: InsightTagRead) => {
        setEditingTagId(tagItem.id);
        setEditingTagName(tagItem.tag_name);
    };

    const handleSaveTag = (tagItem: InsightTagRead) => {
        const tagName = editingTagName.trim();
        if (!tagName) return;
        updateTagMutation.mutate(
            { tagId: tagItem.id, data: { tag_name: tagName } },
            {
                onSuccess: () => {
                    setEditingTagId(null);
                    setEditingTagName("");
                },
            },
        );
    };

    const handleStartEditChannel = (channel: InsightChannelRead) => {
        setEditingChannel(channel);
        setChannelForm({
            channel_name: channel.channel_name,
            channel_type: channel.channel_type,
            channel_url: channel.channel_url ?? "",
            applicable_scenarios: channel.applicable_scenarios.join("、"),
            collection_method: channel.collection_method,
            login_requirement: channel.login_requirement,
            access_status: channel.access_status,
            default_trust_level: channel.default_trust_level,
            default_frequency: channel.default_frequency,
            default_processing_policy: channel.default_processing_policy,
            comment: channel.comment ?? "",
        });
        setChannelDialogOpen(true);
    };

    const handleStartCreateChannel = () => {
        setEditingChannel(null);
        setChannelForm(emptyChannelForm);
        setChannelDialogOpen(true);
    };

    const handleSaveChannel = () => {
        const payload = buildChannelPayload(channelForm);
        if (!payload.channel_name.trim()) return;
        if (editingChannel) {
            updateChannelMutation.mutate(
                { channelId: editingChannel.id, data: payload },
                {
                    onSuccess: () => {
                        setEditingChannel(null);
                        setChannelForm(emptyChannelForm);
                        setChannelDialogOpen(false);
                    },
                },
            );
            return;
        }
        createChannelMutation.mutate(payload, {
            onSuccess: () => {
                setChannelForm(emptyChannelForm);
                setChannelDialogOpen(false);
            },
        });
    };

    const handleStartCreateExecution = () => {
        setEditingExecution(null);
        setExecutionForm(emptyExecutionForm);
        setExecutionDialogOpen(true);
    };

    const handleStartEditExecution = (source: InsightDataSourceRead) => {
        setEditingExecution(source);
        setExecutionForm({
            source_name: source.source_name,
            source_type: source.source_type,
            base_url: source.base_url ?? "",
            execution_role: source.execution_role ?? "企业新闻",
            monitor_config_id: source.monitor_config_id ? String(source.monitor_config_id) : "",
            channel_id: source.channel_id ? String(source.channel_id) : "",
            fetch_frequency: source.fetch_frequency,
            status: source.status,
            keywords: (source.fetch_config?.keywords ?? []).join("、"),
        });
        setExecutionDialogOpen(true);
    };

    const handleSaveExecution = () => {
        const payload = buildExecutionPayload(executionForm);
        if (!payload.source_name.trim()) return;
        if (editingExecution) {
            updateExecutionMutation.mutate(
                { dataSourceId: editingExecution.id, data: payload },
                {
                    onSuccess: () => {
                        setEditingExecution(null);
                        setExecutionForm(emptyExecutionForm);
                        setExecutionDialogOpen(false);
                    },
                },
            );
            return;
        }
        createExecutionMutation.mutate(payload, {
            onSuccess: () => {
                setExecutionForm(emptyExecutionForm);
                setExecutionDialogOpen(false);
            },
        });
    };

    const handleSyncLegacySources = () => {
        syncLegacyMutation.mutate(undefined, {
            onSuccess: (result) => {
                toast.success(`旧执行源同步完成：检查 ${result.checked_count} 个，关联监测配置 ${result.linked_source_count} 个，关联渠道 ${result.linked_channel_count} 个`);
            },
            onError: (error) => toast.error(error instanceof Error ? error.message : "旧执行源同步失败"),
        });
    };

    const handleStartCreateMonitor = () => {
        setEditingMonitor(null);
        setMonitorForm(emptyMonitorForm);
        setMonitorDialogOpen(true);
    };

    const handleStartEditMonitor = (config: InsightMonitorConfigRead) => {
        setEditingMonitor(config);
        setMonitorForm({
            config_name: config.config_name,
            monitor_type: config.monitor_type,
            object_type: config.object_type,
            object_name: config.object_name ?? "",
            relation_type: config.relation_type ?? "",
            enabled_modules: config.enabled_modules.join("、"),
            keywords: config.keywords.join("、"),
            excluded_keywords: config.excluded_keywords.join("、"),
            source_channel_ids: config.source_channel_ids.join("、"),
            monitor_strength: config.monitor_strength,
            fetch_frequency: config.fetch_frequency,
            ai_review_prompt: config.ai_review_prompt ?? "",
            visibility_scope: config.visibility_scope,
            status: config.status,
        });
        setMonitorDialogOpen(true);
    };

    const handleSaveMonitor = () => {
        const payload = buildMonitorPayload(monitorForm);
        if (!payload.config_name.trim()) return;
        if (editingMonitor) {
            updateMonitorMutation.mutate(
                { configId: editingMonitor.id, data: payload },
                {
                    onSuccess: () => {
                        setEditingMonitor(null);
                        setMonitorForm(emptyMonitorForm);
                        setMonitorDialogOpen(false);
                    },
                },
            );
            return;
        }
        createMonitorMutation.mutate(payload, {
            onSuccess: () => {
                setMonitorForm(emptyMonitorForm);
                setMonitorDialogOpen(false);
            },
        });
    };

    return (
        <PageContainer className="flex min-h-0 flex-col gap-3 overflow-hidden pr-1">
            <div className="flex min-h-0 flex-1 flex-col gap-3">
                <div className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white/90 p-1.5 shadow-[0_8px_24px_rgba(15,23,42,0.04)]">
                    <select
                        value={activeTab}
                        onChange={(event) => setActiveTab(event.target.value as SettingsTab)}
                        className="h-10 min-w-0 flex-1 rounded-lg border border-slate-200 bg-white px-3 text-sm font-black text-slate-800 sm:hidden"
                        aria-label="设置分类"
                    >
                        {settingsTabs.map((tab) => (
                            <option key={tab.key} value={tab.key}>
                                {tab.label}
                            </option>
                        ))}
                    </select>

                    <div className="hidden min-w-0 flex-1 overflow-x-auto sm:block">
                        <div className="flex min-w-max gap-1">
                        {settingsTabs.map((tab) => {
                            const active = activeTab === tab.key;
                            return (
                                <button
                                    key={tab.key}
                                    type="button"
                                    className={`min-w-[92px] rounded-lg px-3 py-2 text-center text-sm font-black transition-colors ${
                                        active
                                            ? "bg-blue-50 text-blue-900 ring-1 ring-blue-100"
                                            : "text-slate-500 hover:bg-slate-50 hover:text-slate-900"
                                    }`}
                                    onClick={() => setActiveTab(tab.key)}
                                >
                                    {tab.label}
                                </button>
                            );
                        })}
                        </div>
                    </div>
                    <Button type="button" variant="ghost" size="sm" className="h-10 shrink-0 rounded-lg px-3 text-slate-600 hover:bg-slate-50" onClick={handleRefresh}>
                        {isRefreshing ? <Loader2 className="size-4 animate-spin" /> : <RefreshCw className="size-4" />}
                        <span className="hidden sm:inline">刷新</span>
                    </Button>
                </div>

                <div className="min-h-0 flex-1 overflow-hidden">
                {activeTab === "status" ? (
                    statusQuery.isLoading ? (
                        <SectionCard className="h-full">
                            <div className="flex min-h-[220px] items-center justify-center gap-3 text-sm font-bold text-slate-500">
                                <Loader2 className="size-5 animate-spin" />
                                正在读取配置状态
                            </div>
                        </SectionCard>
                    ) : statusQuery.isError ? (
                        <SectionCard className="h-full">
                            <div className="flex min-h-[220px] flex-col items-center justify-center gap-3 text-center">
                                <Settings className="size-8 text-amber-500" />
                                <div className="text-base font-black text-slate-900">配置状态读取失败</div>
                                <div className="text-sm font-semibold text-slate-500">请确认当前账号已登录，且后端 Insight 设置状态接口可访问。</div>
                            </div>
                        </SectionCard>
                    ) : (
                        <div className="insight-page-scroll space-y-5">
                            <SectionCard title="配置总览" description={`最后刷新时间：${formatDateTime(statusQuery.data?.generated_at)}`} className="p-3 sm:p-4">
                                <div className="grid gap-3 md:grid-cols-3">
                                    <SummaryTile label="正常项" value={countItems(sections, "ok")} tone="ok" />
                                    <SummaryTile label="需关注项" value={countItems(sections, "warning")} tone="warning" />
                                    <SummaryTile label="未启用项" value={countItems(sections, "disabled")} tone="disabled" />
                                </div>
                            </SectionCard>

                            {sections.map((section) => (
                                <SectionCard key={section.key} title={section.name} description={section.description}>
                                    <div className="divide-y divide-slate-100 rounded-xl border border-slate-200 bg-white">
                                        {section.items.map((item) => (
                                            <StatusRow key={item.key} item={item} />
                                        ))}
                                    </div>
                                </SectionCard>
                            ))}
                        </div>
                    )
                ) : null}

                {activeTab === "channels" ? (
                <SectionCard className="flex h-full min-h-0 flex-col p-3">
                    <div className="hidden gap-2 rounded-xl border border-slate-200 bg-slate-50 p-2 sm:grid md:grid-cols-[minmax(0,1fr)_190px_160px] xl:grid-cols-[minmax(0,1fr)_220px_180px_auto]">
                        <Input
                            value={channelKeyword}
                            onChange={(event) => {
                                setChannelKeyword(event.target.value);
                                setChannelPage(1);
                            }}
                            placeholder="搜索渠道名称、编码或地址"
                        />
                        <select
                            value={channelScenario}
                            onChange={(event) => {
                                setChannelScenario(event.target.value);
                                setChannelPage(1);
                            }}
                            className="h-11 rounded-2xl border border-slate-200 bg-white px-3 text-sm font-semibold text-slate-700"
                        >
                            {monitorScenarioOptions.map((item) => (
                                <option key={item.value} value={item.value}>{item.label}</option>
                            ))}
                        </select>
                        <select
                            value={channelAccessStatus}
                            onChange={(event) => {
                                setChannelAccessStatus(event.target.value);
                                setChannelPage(1);
                            }}
                            className="h-11 rounded-2xl border border-slate-200 bg-white px-3 text-sm font-semibold text-slate-700"
                        >
                            {accessStatusOptions.map((item) => (
                                <option key={item.value} value={item.value}>{item.label}</option>
                            ))}
                        </select>
                        <div className="flex justify-end gap-2 md:col-span-3 xl:col-span-1">
                            <Button type="button" variant="outline" size="sm" className="h-11 rounded-2xl bg-white px-4" disabled={isChannelMutating} onClick={() => seedDefaultChannelsMutation.mutate()}>
                                {seedDefaultChannelsMutation.isPending ? <Loader2 className="size-4 animate-spin" /> : <Sparkles className="size-4" />}
                                补齐默认渠道
                            </Button>
                            <Button type="button" size="sm" className="h-11 rounded-2xl px-4" disabled={isChannelMutating} onClick={handleStartCreateChannel}>
                                <Plus className="size-4" />
                                新增渠道
                            </Button>
                        </div>
                    </div>

                    <div className="space-y-2 rounded-xl border border-slate-200 bg-slate-50 p-2 sm:hidden">
                        <div className="flex gap-2">
                            <Input
                                value={channelKeyword}
                                onChange={(event) => {
                                    setChannelKeyword(event.target.value);
                                    setChannelPage(1);
                                }}
                                placeholder="搜索渠道名称、编码或地址"
                            />
                            <Button type="button" size="sm" className="h-11 shrink-0 rounded-xl px-3" disabled={isChannelMutating} onClick={handleStartCreateChannel}>
                                <Plus className="size-4" />
                                新增
                            </Button>
                        </div>
                        <details className="rounded-xl border border-slate-200 bg-white px-3 py-2">
                            <summary className="cursor-pointer text-sm font-black text-slate-700">筛选条件</summary>
                            <div className="mt-2 grid gap-2">
                                <select
                                    value={channelScenario}
                                    onChange={(event) => {
                                        setChannelScenario(event.target.value);
                                        setChannelPage(1);
                                    }}
                                    className="h-10 rounded-xl border border-slate-200 bg-white px-3 text-sm font-semibold text-slate-700"
                                >
                                    {monitorScenarioOptions.map((item) => (
                                        <option key={item.value} value={item.value}>{item.label}</option>
                                    ))}
                                </select>
                                <select
                                    value={channelAccessStatus}
                                    onChange={(event) => {
                                        setChannelAccessStatus(event.target.value);
                                        setChannelPage(1);
                                    }}
                                    className="h-10 rounded-xl border border-slate-200 bg-white px-3 text-sm font-semibold text-slate-700"
                                >
                                    {accessStatusOptions.map((item) => (
                                        <option key={item.value} value={item.value}>{item.label}</option>
                                    ))}
                                </select>
                                <Button type="button" variant="outline" size="sm" className="h-10 rounded-xl bg-white" disabled={isChannelMutating} onClick={() => seedDefaultChannelsMutation.mutate()}>
                                    {seedDefaultChannelsMutation.isPending ? <Loader2 className="size-4 animate-spin" /> : <Sparkles className="size-4" />}
                                    补齐默认渠道
                                </Button>
                            </div>
                        </details>
                    </div>

                    <div className="mt-3 min-h-0 flex-1 divide-y divide-slate-100 overflow-y-auto rounded-xl border border-slate-200 bg-white">
                        {channelsQuery.isLoading ? (
                            <div className="flex min-h-[120px] items-center justify-center gap-2 text-sm font-semibold text-slate-500">
                                <Loader2 className="size-4 animate-spin" />
                                正在读取渠道库
                            </div>
                        ) : (channelsQuery.data?.items ?? []).length > 0 ? (
                            channelsQuery.data?.items.map((channel) => (
                                <ChannelRow
                                    key={channel.id}
                                    channel={channel}
                                    isMutating={isChannelMutating}
                                    onEdit={handleStartEditChannel}
                                    onDelete={(channelId) => deleteChannelMutation.mutate(channelId)}
                                />
                            ))
                        ) : (
                            <div className="flex min-h-[120px] items-center justify-center gap-2 text-sm font-semibold text-slate-500">
                                <Sparkles className="size-4" />
                                暂无渠道，建议先点击“补齐默认渠道”
                            </div>
                        )}
                    </div>

                    <div className="mt-3 flex shrink-0 flex-col gap-2 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm font-semibold text-slate-500 sm:flex-row sm:items-center sm:justify-between">
                        <div>
                            共 {channelTotal} 个渠道，每页 {channelPageSize} 个，第 {currentChannelPage} / {channelTotalPages} 页
                        </div>
                        <div className="flex gap-2">
                            <Button
                                type="button"
                                variant="outline"
                                size="sm"
                                className="h-9 flex-1 rounded-lg bg-white sm:flex-none"
                                disabled={channelPage <= 1 || channelsQuery.isFetching}
                                onClick={() => setChannelPage((value) => Math.max(1, value - 1))}
                            >
                                上一页
                            </Button>
                            <Button
                                type="button"
                                variant="outline"
                                size="sm"
                                className="h-9 flex-1 rounded-lg bg-white sm:flex-none"
                                disabled={channelPage >= channelTotalPages || channelsQuery.isFetching}
                                onClick={() => setChannelPage((value) => Math.min(channelTotalPages, value + 1))}
                            >
                                下一页
                            </Button>
                        </div>
                    </div>

                    <Dialog
                        open={channelDialogOpen}
                        onOpenChange={(open) => {
                            setChannelDialogOpen(open);
                            if (!open) {
                                setEditingChannel(null);
                                setChannelForm(emptyChannelForm);
                            }
                        }}
                    >
                        <DialogContent className="max-h-[calc(100vh-7rem)] gap-3 overflow-y-auto p-4 sm:max-h-[88vh] sm:max-w-4xl sm:p-5">
                            <DialogHeader>
                                <DialogTitle>{editingChannel ? "编辑渠道" : "新增渠道"}</DialogTitle>
                                <DialogDescription>维护渠道基础属性，保存后回到渠道列表继续查看。</DialogDescription>
                            </DialogHeader>
                            <ChannelForm
                                form={channelForm}
                                editing={Boolean(editingChannel)}
                                isMutating={isChannelMutating}
                                onChange={(patch) => setChannelForm((current) => ({ ...current, ...patch }))}
                                onSave={handleSaveChannel}
                                onCancel={() => {
                                    setEditingChannel(null);
                                    setChannelForm(emptyChannelForm);
                                    setChannelDialogOpen(false);
                                }}
                            />
                        </DialogContent>
                    </Dialog>
                </SectionCard>
                ) : null}

                {activeTab === "execution" ? (
                    <SectionCard className="flex h-full min-h-0 flex-col p-3">
                        <div className="grid gap-2 rounded-xl border border-slate-200 bg-slate-50 p-2 md:grid-cols-[minmax(0,1fr)_180px_150px_auto]">
                            <Input
                                value={executionKeyword}
                                onChange={(event) => {
                                    setExecutionKeyword(event.target.value);
                                    setExecutionPage(1);
                                }}
                                placeholder="搜索执行源名称、编码或 URL"
                            />
                            <select
                                value={executionRole}
                                onChange={(event) => {
                                    setExecutionRole(event.target.value);
                                    setExecutionPage(1);
                                }}
                                className="h-11 rounded-2xl border border-slate-200 bg-white px-3 text-sm font-semibold text-slate-700"
                            >
                                {executionRoleOptions.map((item) => (
                                    <option key={item.value} value={item.value}>{item.label}</option>
                                ))}
                            </select>
                            <select
                                value={executionStatus}
                                onChange={(event) => {
                                    setExecutionStatus(event.target.value);
                                    setExecutionPage(1);
                                }}
                                className="h-11 rounded-2xl border border-slate-200 bg-white px-3 text-sm font-semibold text-slate-700"
                            >
                                {executionStatusOptions.map((item) => (
                                    <option key={item.value} value={item.value}>{item.label}</option>
                                ))}
                            </select>
                            <div className="flex flex-wrap justify-end gap-2">
                                <Button type="button" variant="outline" size="sm" className="h-11 rounded-2xl bg-white px-4" disabled={isExecutionMutating} onClick={handleSyncLegacySources}>
                                    {syncLegacyMutation.isPending ? <Loader2 className="size-4 animate-spin" /> : <Sparkles className="size-4" />}
                                    同步旧数据
                                </Button>
                                <Button type="button" size="sm" className="h-11 rounded-2xl px-4" disabled={isExecutionMutating} onClick={handleStartCreateExecution}>
                                    <Plus className="size-4" />
                                    新增执行源
                                </Button>
                            </div>
                        </div>

                        <div className="mt-3 min-h-0 flex-1 divide-y divide-slate-100 overflow-y-auto rounded-xl border border-slate-200 bg-white">
                            {executionSourcesQuery.isLoading ? (
                                <div className="flex min-h-[120px] items-center justify-center gap-2 text-sm font-semibold text-slate-500">
                                    <Loader2 className="size-4 animate-spin" />
                                    正在读取执行源
                                </div>
                            ) : (executionSourcesQuery.data?.items ?? []).length > 0 ? (
                                executionSourcesQuery.data?.items.map((source) => (
                                    <ExecutionSourceRow
                                        key={source.id}
                                        source={source}
                                        isMutating={isExecutionMutating}
                                        onEdit={handleStartEditExecution}
                                        onDelete={(sourceId) => deleteExecutionMutation.mutate(sourceId)}
                                    />
                                ))
                            ) : (
                                <div className="flex min-h-[120px] items-center justify-center gap-2 text-sm font-semibold text-slate-500">
                                    <Database className="size-4" />
                                    暂无执行源，可先同步旧数据或新增执行源
                                </div>
                            )}
                        </div>

                        <div className="mt-3 flex shrink-0 flex-col gap-2 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm font-semibold text-slate-500 sm:flex-row sm:items-center sm:justify-between">
                            <div>共 {executionTotal} 个执行源，每页 {executionPageSize} 个，第 {currentExecutionPage} / {executionTotalPages} 页</div>
                            <div className="flex gap-2">
                                <Button type="button" variant="outline" size="sm" className="h-9 flex-1 rounded-lg bg-white sm:flex-none" disabled={executionPage <= 1 || executionSourcesQuery.isFetching} onClick={() => setExecutionPage((value) => Math.max(1, value - 1))}>
                                    上一页
                                </Button>
                                <Button type="button" variant="outline" size="sm" className="h-9 flex-1 rounded-lg bg-white sm:flex-none" disabled={executionPage >= executionTotalPages || executionSourcesQuery.isFetching} onClick={() => setExecutionPage((value) => Math.min(executionTotalPages, value + 1))}>
                                    下一页
                                </Button>
                            </div>
                        </div>

                        <Dialog
                            open={executionDialogOpen}
                            onOpenChange={(open) => {
                                setExecutionDialogOpen(open);
                                if (!open) {
                                    setEditingExecution(null);
                                    setExecutionForm(emptyExecutionForm);
                                }
                            }}
                        >
                            <DialogContent className="max-h-[calc(100vh-7rem)] gap-3 overflow-y-auto p-4 sm:max-h-[88vh] sm:max-w-4xl sm:p-5">
                                <DialogHeader>
                                    <DialogTitle>{editingExecution ? "编辑执行源" : "新增执行源"}</DialogTitle>
                                    <DialogDescription>执行源是系统内部采集任务明细，建议优先通过监测配置自动生成或归组。</DialogDescription>
                                </DialogHeader>
                                <ExecutionSourceForm
                                    form={executionForm}
                                    monitorConfigs={monitorConfigOptionsQuery.data?.items ?? []}
                                    channels={channelOptionsQuery.data?.items ?? []}
                                    editing={Boolean(editingExecution)}
                                    isMutating={isExecutionMutating}
                                    onChange={(patch) => setExecutionForm((current) => ({ ...current, ...patch }))}
                                    onSave={handleSaveExecution}
                                    onCancel={() => {
                                        setEditingExecution(null);
                                        setExecutionForm(emptyExecutionForm);
                                        setExecutionDialogOpen(false);
                                    }}
                                />
                            </DialogContent>
                        </Dialog>
                    </SectionCard>
                ) : null}

                {activeTab === "monitoring" ? (
                    <SectionCard className="flex h-full min-h-0 flex-col p-3">
                        <div className="grid gap-2 rounded-xl border border-slate-200 bg-slate-50 p-2 md:grid-cols-[minmax(0,1fr)_180px_150px_auto]">
                            <Input
                                value={monitorKeyword}
                                onChange={(event) => {
                                    setMonitorKeyword(event.target.value);
                                    setMonitorPage(1);
                                }}
                                placeholder="搜索监测名称、对象或编码"
                            />
                            <select
                                value={monitorType}
                                onChange={(event) => {
                                    setMonitorType(event.target.value);
                                    setMonitorPage(1);
                                }}
                                className="h-11 rounded-2xl border border-slate-200 bg-white px-3 text-sm font-semibold text-slate-700"
                            >
                                {monitorTypeOptions.map((item) => (
                                    <option key={item.value} value={item.value}>{item.label}</option>
                                ))}
                            </select>
                            <select
                                value={monitorStatus}
                                onChange={(event) => {
                                    setMonitorStatus(event.target.value);
                                    setMonitorPage(1);
                                }}
                                className="h-11 rounded-2xl border border-slate-200 bg-white px-3 text-sm font-semibold text-slate-700"
                            >
                                <option value="">全部状态</option>
                                <option value="active">启用</option>
                                <option value="disabled">停用</option>
                            </select>
                            <div className="flex justify-end">
                                <Button type="button" size="sm" className="h-11 rounded-2xl px-4" disabled={isMonitorMutating} onClick={handleStartCreateMonitor}>
                                    <Plus className="size-4" />
                                    新增监测配置
                                </Button>
                            </div>
                        </div>

                        <div className="mt-3 min-h-0 flex-1 divide-y divide-slate-100 overflow-y-auto rounded-xl border border-slate-200 bg-white">
                            {monitorConfigsQuery.isLoading ? (
                                <div className="flex min-h-[120px] items-center justify-center gap-2 text-sm font-semibold text-slate-500">
                                    <Loader2 className="size-4 animate-spin" />
                                    正在读取监测配置
                                </div>
                            ) : (monitorConfigsQuery.data?.items ?? []).length > 0 ? (
                                monitorConfigsQuery.data?.items.map((config) => (
                                    <MonitorConfigRow
                                        key={config.id}
                                        config={config}
                                        isMutating={isMonitorMutating}
                                        onEdit={handleStartEditMonitor}
                                        onDelete={(configId) => deleteMonitorMutation.mutate(configId)}
                                    />
                                ))
                            ) : (
                                <div className="flex min-h-[120px] items-center justify-center gap-2 text-sm font-semibold text-slate-500">
                                    <Sparkles className="size-4" />
                                    暂无监测配置，可先同步旧执行源生成历史迁移配置
                                </div>
                            )}
                        </div>

                        <div className="mt-3 flex shrink-0 flex-col gap-2 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm font-semibold text-slate-500 sm:flex-row sm:items-center sm:justify-between">
                            <div>共 {monitorTotal} 个监测配置，每页 {monitorPageSize} 个，第 {currentMonitorPage} / {monitorTotalPages} 页</div>
                            <div className="flex gap-2">
                                <Button type="button" variant="outline" size="sm" className="h-9 flex-1 rounded-lg bg-white sm:flex-none" disabled={monitorPage <= 1 || monitorConfigsQuery.isFetching} onClick={() => setMonitorPage((value) => Math.max(1, value - 1))}>
                                    上一页
                                </Button>
                                <Button type="button" variant="outline" size="sm" className="h-9 flex-1 rounded-lg bg-white sm:flex-none" disabled={monitorPage >= monitorTotalPages || monitorConfigsQuery.isFetching} onClick={() => setMonitorPage((value) => Math.min(monitorTotalPages, value + 1))}>
                                    下一页
                                </Button>
                            </div>
                        </div>

                        <Dialog
                            open={monitorDialogOpen}
                            onOpenChange={(open) => {
                                setMonitorDialogOpen(open);
                                if (!open) {
                                    setEditingMonitor(null);
                                    setMonitorForm(emptyMonitorForm);
                                }
                            }}
                        >
                            <DialogContent className="max-h-[calc(100vh-7rem)] gap-3 overflow-y-auto p-4 sm:max-h-[88vh] sm:max-w-4xl sm:p-5">
                                <DialogHeader>
                                    <DialogTitle>{editingMonitor ? "编辑监测配置" : "新增监测配置"}</DialogTitle>
                                    <DialogDescription>监测配置面向业务对象，执行源会归属到这里，便于报告、AI 助手和后续 RAG 使用。</DialogDescription>
                                </DialogHeader>
                                <MonitorConfigForm
                                    form={monitorForm}
                                    channels={channelOptionsQuery.data?.items ?? []}
                                    editing={Boolean(editingMonitor)}
                                    isMutating={isMonitorMutating}
                                    onChange={(patch) => setMonitorForm((current) => ({ ...current, ...patch }))}
                                    onSave={handleSaveMonitor}
                                    onCancel={() => {
                                        setEditingMonitor(null);
                                        setMonitorForm(emptyMonitorForm);
                                        setMonitorDialogOpen(false);
                                    }}
                                />
                            </DialogContent>
                        </Dialog>
                    </SectionCard>
                ) : null}

                {activeTab === "tags" ? (
                <div className="insight-page-scroll">
                <SectionCard
                    title="标签字典"
                    description="管理员可维护可复用标签。禁用标签不会删除历史情报，仅阻止后续作为启用标签使用。"
                    action={dictionaryQuery.isLoading ? <Loader2 className="size-4 animate-spin text-slate-400" /> : null}
                >
                    <div className="grid gap-3 rounded-xl border border-slate-200 bg-slate-50 p-3 lg:grid-cols-[minmax(0,1fr)_180px_auto]">
                        <Input value={newTagName} onChange={(event) => setNewTagName(event.target.value)} placeholder="输入标签名称" />
                        <select
                            value={newTagType}
                            onChange={(event) => setNewTagType(event.target.value)}
                            className="h-11 rounded-2xl border border-slate-200 bg-white px-3 text-sm font-semibold text-slate-700"
                        >
                            {Object.entries(tagTypeLabels).map(([value, label]) => (
                                <option key={value} value={value}>
                                    {label}
                                </option>
                            ))}
                        </select>
                        <Button type="button" className="rounded-xl" disabled={!newTagName.trim() || isMutating} onClick={handleCreateTag}>
                            {createTagMutation.isPending ? <Loader2 className="size-4 animate-spin" /> : <Plus className="size-4" />}
                            新增
                        </Button>
                    </div>

                    {dictionaryQuery.isError ? (
                        <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm font-semibold text-amber-700">
                            字典读取失败，请确认当前账号有访问权限。
                        </div>
                    ) : (
                        <div className="mt-4 divide-y divide-slate-100 rounded-xl border border-slate-200 bg-white">
                            {(dictionary?.tags ?? []).length > 0 ? (
                                dictionary?.tags.map((tagItem) => (
                                    <TagRow
                                        key={tagItem.id}
                                        tagItem={tagItem}
                                        editing={editingTagId === tagItem.id}
                                        editingName={editingTagName}
                                        isMutating={isMutating}
                                        onEditNameChange={setEditingTagName}
                                        onStartEdit={handleStartEdit}
                                        onSave={handleSaveTag}
                                        onCancel={() => setEditingTagId(null)}
                                        onDisable={(tagId) => disableTagMutation.mutate(tagId)}
                                    />
                                ))
                            ) : (
                                <div className="flex min-h-[120px] items-center justify-center gap-2 text-sm font-semibold text-slate-500">
                                    <Tag className="size-4" />
                                    暂无标签
                                </div>
                            )}
                        </div>
                    )}
                </SectionCard>
                </div>
                ) : null}

                {activeTab === "types" ? (
                <div className="insight-page-scroll">
                <SectionCard title="情报类型字典" description="当前情报类型采用内置受控口径，供筛选、展示和生成约束统一使用。">
                    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                        {(dictionary?.intelligence_types ?? []).map((typeItem) => (
                            <IntelligenceTypeCard key={typeItem.type_code} typeItem={typeItem} />
                        ))}
                    </div>
                </SectionCard>
                </div>
                ) : null}
                </div>
            </div>
        </PageContainer>
    );
}

function StatusRow({ item }: { item: InsightSettingsStatusItem }) {
    const meta = statusMeta[item.status] ?? statusMeta.warning;
    const Icon = meta.icon;
    return (
        <div className="grid gap-3 px-4 py-4 md:grid-cols-[minmax(0,1fr)_120px] md:items-start">
            <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                    <h3 className="text-sm font-black text-slate-900">{item.name}</h3>
                    <span className={`inline-flex h-7 items-center gap-1 rounded-full border px-2 text-xs font-black ${meta.className}`}>
                        <Icon className="size-3.5" />
                        {meta.label}
                    </span>
                </div>
                <p className="mt-2 text-sm leading-6 text-slate-600">{item.description}</p>
                {item.details.length > 0 ? (
                    <div className="mt-3 flex flex-wrap gap-2">
                        {item.details.map((detail) => (
                            <span key={detail} className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-semibold text-slate-600">
                                {detail}
                            </span>
                        ))}
                    </div>
                ) : null}
            </div>
        </div>
    );
}

function ChannelForm({
    form,
    editing,
    isMutating,
    onChange,
    onSave,
    onCancel,
}: {
    form: ChannelFormState;
    editing: boolean;
    isMutating: boolean;
    onChange: (patch: Partial<ChannelFormState>) => void;
    onSave: () => void;
    onCancel: () => void;
}) {
    return (
        <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
            <div className="grid gap-3 lg:grid-cols-3">
                <Input value={form.channel_name} onChange={(event) => onChange({ channel_name: event.target.value })} placeholder="渠道名称，如 FoodDaily" />
                <select value={form.channel_type} onChange={(event) => onChange({ channel_type: event.target.value })} className="h-11 rounded-2xl border border-slate-200 bg-white px-3 text-sm font-semibold text-slate-700">
                    {channelTypeOptions.filter((item) => item.value).map((item) => (
                        <option key={item.value} value={item.value}>{item.label}</option>
                    ))}
                </select>
                <Input value={form.channel_url} onChange={(event) => onChange({ channel_url: event.target.value })} placeholder="渠道地址，可为空" />
                <Input value={form.applicable_scenarios} onChange={(event) => onChange({ applicable_scenarios: event.target.value })} placeholder="适用场景，用顿号或逗号分隔" />
                <select value={form.collection_method} onChange={(event) => onChange({ collection_method: event.target.value })} className="h-11 rounded-2xl border border-slate-200 bg-white px-3 text-sm font-semibold text-slate-700">
                    {collectionMethodOptions.map((item) => (
                        <option key={item.value} value={item.value}>{item.label}</option>
                    ))}
                </select>
                <select value={form.access_status} onChange={(event) => onChange({ access_status: event.target.value })} className="h-11 rounded-2xl border border-slate-200 bg-white px-3 text-sm font-semibold text-slate-700">
                    {accessStatusOptions.filter((item) => item.value).map((item) => (
                        <option key={item.value} value={item.value}>{item.label}</option>
                    ))}
                </select>
                <select value={form.login_requirement} onChange={(event) => onChange({ login_requirement: event.target.value })} className="h-11 rounded-2xl border border-slate-200 bg-white px-3 text-sm font-semibold text-slate-700">
                    <option value="none">不需要登录</option>
                    <option value="account_required">需要账号</option>
                    <option value="licensed">需要授权</option>
                    <option value="unknown">未知</option>
                </select>
                <select value={form.default_trust_level} onChange={(event) => onChange({ default_trust_level: event.target.value })} className="h-11 rounded-2xl border border-slate-200 bg-white px-3 text-sm font-semibold text-slate-700">
                    <option value="high">可信度高</option>
                    <option value="medium">可信度中</option>
                    <option value="low">可信度低</option>
                </select>
                <select value={form.default_frequency} onChange={(event) => onChange({ default_frequency: event.target.value })} className="h-11 rounded-2xl border border-slate-200 bg-white px-3 text-sm font-semibold text-slate-700">
                    <option value="manual">手动</option>
                    <option value="daily">每日</option>
                    <option value="weekly">每周</option>
                    <option value="monthly">每月</option>
                </select>
                <select value={form.default_processing_policy} onChange={(event) => onChange({ default_processing_policy: event.target.value })} className="h-11 rounded-2xl border border-slate-200 bg-white px-3 text-sm font-semibold text-slate-700">
                    <option value="ai_review">AI 自动评审</option>
                    <option value="candidate_only">仅候选</option>
                    <option value="do_not_import">暂不入库</option>
                </select>
                <Input value={form.comment} onChange={(event) => onChange({ comment: event.target.value })} placeholder="备注，如反爬、授权或接入建议" />
                <div className="flex gap-2 lg:col-span-3 lg:justify-end">
                    <Button type="button" className="flex-1 rounded-xl lg:flex-none lg:min-w-28" disabled={!form.channel_name.trim() || isMutating} onClick={onSave}>
                        {isMutating ? <Loader2 className="size-4 animate-spin" /> : <Save className="size-4" />}
                        {editing ? "保存渠道" : "新增渠道"}
                    </Button>
                    <Button type="button" variant="outline" className="rounded-xl bg-white lg:min-w-24" onClick={onCancel}>
                        取消
                    </Button>
                </div>
            </div>
        </div>
    );
}

function ChannelRow({
    channel,
    isMutating,
    onEdit,
    onDelete,
}: {
    channel: InsightChannelRead;
    isMutating: boolean;
    onEdit: (channel: InsightChannelRead) => void;
    onDelete: (channelId: number) => void;
}) {
    return (
        <div className="grid gap-3 px-3 py-3 xl:grid-cols-[minmax(220px,1.15fr)_minmax(180px,0.9fr)_minmax(150px,0.6fr)_148px] xl:items-center">
            <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-black text-slate-900">{channel.channel_name}</span>
                    <Badge variant="outline">{channelTypeLabels[channel.channel_type] ?? channel.channel_type}</Badge>
                    <Badge variant={channel.access_status === "supported" ? "default" : "outline"}>{accessStatusLabels[channel.access_status] ?? channel.access_status}</Badge>
                </div>
                <div className="mt-1 flex flex-wrap gap-x-2 gap-y-1 text-xs font-semibold text-slate-500">
                    <span>编码：{channel.channel_code}</span>
                    <span>方式：{collectionMethodLabels[channel.collection_method] ?? channel.collection_method}</span>
                </div>
                {channel.applicable_scenarios.length > 0 ? (
                    <div className="mt-1 flex flex-wrap gap-1">
                        {channel.applicable_scenarios.map((item) => (
                            <span key={item} className="rounded-full bg-slate-100 px-2 py-1 text-xs font-semibold text-slate-600">{item}</span>
                        ))}
                    </div>
                ) : null}
            </div>
            <div className="min-w-0 text-xs font-bold leading-6 text-slate-500">
                {channel.channel_url ? <div className="truncate text-blue-600">{channel.channel_url}</div> : <div className="text-slate-400">未配置地址</div>}
                <div>频率：{frequencyLabel(channel.default_frequency)} / 处理：{processingPolicyLabel(channel.default_processing_policy)}</div>
            </div>
            <div className="text-xs font-bold leading-6 text-slate-500">
                <div>登录：{loginRequirementLabel(channel.login_requirement)}</div>
                <div>可信度：{trustLevelLabel(channel.default_trust_level)}</div>
                <div className="truncate">更新：{formatDateTime(channel.update_time)}</div>
            </div>
            <div className="flex flex-wrap justify-start gap-2 xl:justify-end">
                <Button type="button" size="sm" variant="outline" className="rounded-xl bg-white" disabled={isMutating} onClick={() => onEdit(channel)}>
                    <Pencil className="size-4" />
                    编辑
                </Button>
                <Button type="button" size="sm" variant="outline" className="rounded-xl bg-white text-rose-600" disabled={isMutating} onClick={() => onDelete(channel.id)}>
                    <Trash2 className="size-4" />
                    删除
                </Button>
            </div>
        </div>
    );
}

function ExecutionSourceRow({
    source,
    isMutating,
    onEdit,
    onDelete,
}: {
    source: InsightDataSourceRead;
    isMutating: boolean;
    onEdit: (source: InsightDataSourceRead) => void;
    onDelete: (sourceId: number) => void;
}) {
    return (
        <div className="grid gap-3 px-3 py-3 xl:grid-cols-[minmax(220px,1.1fr)_minmax(180px,0.9fr)_minmax(150px,0.7fr)_148px] xl:items-center">
            <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-black text-slate-900">{source.source_name}</span>
                    <Badge variant="outline">{executionRoleLabels[source.execution_role ?? ""] ?? source.execution_role ?? "未分配角色"}</Badge>
                    <Badge variant={source.status === "enabled" ? "default" : "outline"}>{source.status === "enabled" ? "已启用" : "已停用"}</Badge>
                </div>
                <div className="mt-1 flex flex-wrap gap-x-2 gap-y-1 text-xs font-semibold text-slate-500">
                    <span>编码：{source.source_code}</span>
                    <span>类型：{collectionSourceTypeLabels[source.source_type] ?? source.source_type}</span>
                    <span>策略：{strategyLabel(source.collection_strategy)}</span>
                </div>
            </div>
            <div className="min-w-0 text-xs font-bold leading-6 text-slate-500">
                <div className="truncate">监测配置：{source.monitor_config_name || "未归属"}</div>
                <div className="truncate">渠道：{source.channel_name || "未关联渠道"}</div>
                {source.base_url ? <div className="truncate text-blue-600">{source.base_url}</div> : null}
            </div>
            <div className="text-xs font-bold leading-6 text-slate-500">
                <div>周期：{frequencyLabel(source.fetch_frequency)}</div>
                <div>下次：{formatDateTime(source.next_run_time)}</div>
                <div>生成：{generationModeLabel(source.generation_mode)}</div>
            </div>
            <div className="flex flex-wrap justify-start gap-2 xl:justify-end">
                <Button type="button" size="sm" variant="outline" className="rounded-xl bg-white" disabled={isMutating} onClick={() => onEdit(source)}>
                    <Pencil className="size-4" />
                    编辑
                </Button>
                <Button type="button" size="sm" variant="outline" className="rounded-xl bg-white text-rose-600" disabled={isMutating} onClick={() => onDelete(source.id)}>
                    <Trash2 className="size-4" />
                    删除
                </Button>
            </div>
        </div>
    );
}

function MonitorConfigRow({
    config,
    isMutating,
    onEdit,
    onDelete,
}: {
    config: InsightMonitorConfigRead;
    isMutating: boolean;
    onEdit: (config: InsightMonitorConfigRead) => void;
    onDelete: (configId: number) => void;
}) {
    return (
        <div className="grid gap-3 px-3 py-3 xl:grid-cols-[minmax(240px,1.1fr)_minmax(220px,1fr)_minmax(140px,0.55fr)_148px] xl:items-center">
            <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-black text-slate-900">{config.config_name}</span>
                    <Badge variant="outline">{monitorTypeLabels[config.monitor_type] ?? config.monitor_type}</Badge>
                    <Badge variant={config.status === "active" ? "default" : "outline"}>{config.status === "active" ? "启用" : "停用"}</Badge>
                </div>
                <div className="mt-1 flex flex-wrap gap-x-2 gap-y-1 text-xs font-semibold text-slate-500">
                    <span>对象：{config.object_name || "未指定"}</span>
                    {config.relation_type ? <span>关系：{config.relation_type}</span> : null}
                    <span>强度：{strategyLabel(config.monitor_strength)}</span>
                </div>
            </div>
            <div className="min-w-0">
                <div className="flex flex-wrap gap-1">
                    {config.enabled_modules.slice(0, 5).map((item) => (
                        <span key={item} className="rounded-full bg-slate-100 px-2 py-1 text-xs font-semibold text-slate-600">{item}</span>
                    ))}
                </div>
                <div className="mt-1 truncate text-xs font-semibold text-slate-500">关键词：{config.keywords.join("、") || "未配置"}</div>
            </div>
            <div className="text-xs font-bold leading-6 text-slate-500">
                <div>执行源：{config.execution_source_count}</div>
                <div>周期：{frequencyLabel(config.fetch_frequency)}</div>
                <div>下次：{formatDateTime(config.next_run_time)}</div>
            </div>
            <div className="flex flex-wrap justify-start gap-2 xl:justify-end">
                <Button type="button" size="sm" variant="outline" className="rounded-xl bg-white" disabled={isMutating} onClick={() => onEdit(config)}>
                    <Pencil className="size-4" />
                    编辑
                </Button>
                <Button type="button" size="sm" variant="outline" className="rounded-xl bg-white text-rose-600" disabled={isMutating || config.execution_source_count > 0} onClick={() => onDelete(config.id)}>
                    <Trash2 className="size-4" />
                    删除
                </Button>
            </div>
        </div>
    );
}

function ExecutionSourceForm({
    form,
    monitorConfigs,
    channels,
    editing,
    isMutating,
    onChange,
    onSave,
    onCancel,
}: {
    form: ExecutionFormState;
    monitorConfigs: InsightMonitorConfigRead[];
    channels: InsightChannelRead[];
    editing: boolean;
    isMutating: boolean;
    onChange: (patch: Partial<ExecutionFormState>) => void;
    onSave: () => void;
    onCancel: () => void;
}) {
    return (
        <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
            <div className="grid gap-3 lg:grid-cols-3">
                <Input value={form.source_name} onChange={(event) => onChange({ source_name: event.target.value })} placeholder="执行源名称" />
                <select value={form.source_type} onChange={(event) => onChange({ source_type: event.target.value })} className="h-11 rounded-2xl border border-slate-200 bg-white px-3 text-sm font-semibold text-slate-700">
                    {collectionSourceTypeOptions.map((item) => (
                        <option key={item.value} value={item.value}>{item.label}</option>
                    ))}
                </select>
                <select value={form.execution_role} onChange={(event) => onChange({ execution_role: event.target.value })} className="h-11 rounded-2xl border border-slate-200 bg-white px-3 text-sm font-semibold text-slate-700">
                    {executionRoleOptions.filter((item) => item.value).map((item) => (
                        <option key={item.value} value={item.value}>{item.label}</option>
                    ))}
                </select>
                <select value={form.monitor_config_id} onChange={(event) => onChange({ monitor_config_id: event.target.value })} className="h-11 rounded-2xl border border-slate-200 bg-white px-3 text-sm font-semibold text-slate-700">
                    <option value="">不关联监测配置</option>
                    {monitorConfigs.map((item) => (
                        <option key={item.id} value={item.id}>{item.config_name}</option>
                    ))}
                </select>
                <select value={form.channel_id} onChange={(event) => onChange({ channel_id: event.target.value })} className="h-11 rounded-2xl border border-slate-200 bg-white px-3 text-sm font-semibold text-slate-700">
                    <option value="">不关联渠道</option>
                    {channels.map((item) => (
                        <option key={item.id} value={item.id}>{item.channel_name}</option>
                    ))}
                </select>
                <select value={form.fetch_frequency} onChange={(event) => onChange({ fetch_frequency: event.target.value })} className="h-11 rounded-2xl border border-slate-200 bg-white px-3 text-sm font-semibold text-slate-700">
                    <option value="manual">手动</option>
                    <option value="daily">每日</option>
                    <option value="weekly">每周</option>
                    <option value="hourly">每小时</option>
                </select>
                <Input value={form.base_url} onChange={(event) => onChange({ base_url: event.target.value })} placeholder="URL，可为空" />
                <Input value={form.keywords} onChange={(event) => onChange({ keywords: event.target.value })} placeholder="关键词，用顿号或逗号分隔" />
                <select value={form.status} onChange={(event) => onChange({ status: event.target.value })} className="h-11 rounded-2xl border border-slate-200 bg-white px-3 text-sm font-semibold text-slate-700">
                    <option value="enabled">已启用</option>
                    <option value="disabled">已停用</option>
                </select>
                <div className="flex gap-2 lg:col-span-3 lg:justify-end">
                    <Button type="button" className="flex-1 rounded-xl lg:flex-none lg:min-w-28" disabled={!form.source_name.trim() || isMutating} onClick={onSave}>
                        {isMutating ? <Loader2 className="size-4 animate-spin" /> : <Save className="size-4" />}
                        {editing ? "保存执行源" : "新增执行源"}
                    </Button>
                    <Button type="button" variant="outline" className="rounded-xl bg-white lg:min-w-24" onClick={onCancel}>取消</Button>
                </div>
            </div>
        </div>
    );
}

function MonitorConfigForm({
    form,
    channels,
    editing,
    isMutating,
    onChange,
    onSave,
    onCancel,
}: {
    form: MonitorFormState;
    channels: InsightChannelRead[];
    editing: boolean;
    isMutating: boolean;
    onChange: (patch: Partial<MonitorFormState>) => void;
    onSave: () => void;
    onCancel: () => void;
}) {
    return (
        <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
            <div className="grid gap-3 lg:grid-cols-3">
                <Input value={form.config_name} onChange={(event) => onChange({ config_name: event.target.value })} placeholder="监测配置名称" />
                <select value={form.monitor_type} onChange={(event) => onChange({ monitor_type: event.target.value })} className="h-11 rounded-2xl border border-slate-200 bg-white px-3 text-sm font-semibold text-slate-700">
                    {monitorTypeOptions.filter((item) => item.value).map((item) => (
                        <option key={item.value} value={item.value}>{item.label}</option>
                    ))}
                </select>
                <Input value={form.object_name} onChange={(event) => onChange({ object_name: event.target.value })} placeholder="监测对象，如企业/行业/主题" />
                <Input value={form.relation_type} onChange={(event) => onChange({ relation_type: event.target.value })} placeholder="关系类型，如客户、竞对、潜在客户" />
                <Input value={form.enabled_modules} onChange={(event) => onChange({ enabled_modules: event.target.value })} placeholder="监测模块，用顿号或逗号分隔" />
                <Input value={form.keywords} onChange={(event) => onChange({ keywords: event.target.value })} placeholder="关键词，用顿号或逗号分隔" />
                <Input value={form.excluded_keywords} onChange={(event) => onChange({ excluded_keywords: event.target.value })} placeholder="排除词，用顿号或逗号分隔" />
                <Input value={form.source_channel_ids} onChange={(event) => onChange({ source_channel_ids: event.target.value })} placeholder={`渠道ID，如 ${channels.slice(0, 3).map((item) => item.id).join("、")}`} />
                <select value={form.monitor_strength} onChange={(event) => onChange({ monitor_strength: event.target.value })} className="h-11 rounded-2xl border border-slate-200 bg-white px-3 text-sm font-semibold text-slate-700">
                    <option value="light">轻量</option>
                    <option value="standard">标准</option>
                    <option value="deep">深度</option>
                    <option value="structured">结构化</option>
                </select>
                <select value={form.fetch_frequency} onChange={(event) => onChange({ fetch_frequency: event.target.value })} className="h-11 rounded-2xl border border-slate-200 bg-white px-3 text-sm font-semibold text-slate-700">
                    <option value="manual">手动</option>
                    <option value="daily">每日</option>
                    <option value="weekly">每周</option>
                    <option value="monthly">每月</option>
                </select>
                <select value={form.visibility_scope} onChange={(event) => onChange({ visibility_scope: event.target.value })} className="h-11 rounded-2xl border border-slate-200 bg-white px-3 text-sm font-semibold text-slate-700">
                    <option value="assigned">指定可见</option>
                    <option value="private">仅自己</option>
                    <option value="dept">部门可见</option>
                    <option value="public">公开</option>
                </select>
                <select value={form.status} onChange={(event) => onChange({ status: event.target.value })} className="h-11 rounded-2xl border border-slate-200 bg-white px-3 text-sm font-semibold text-slate-700">
                    <option value="active">启用</option>
                    <option value="disabled">停用</option>
                </select>
                <textarea
                    value={form.ai_review_prompt}
                    onChange={(event) => onChange({ ai_review_prompt: event.target.value })}
                    placeholder="AI 自动评审提示词，可为空"
                    className="min-h-28 rounded-2xl border border-slate-200 bg-white px-3 py-3 text-sm font-semibold text-slate-700 lg:col-span-3"
                />
                <div className="flex gap-2 lg:col-span-3 lg:justify-end">
                    <Button type="button" className="flex-1 rounded-xl lg:flex-none lg:min-w-28" disabled={!form.config_name.trim() || isMutating} onClick={onSave}>
                        {isMutating ? <Loader2 className="size-4 animate-spin" /> : <Save className="size-4" />}
                        {editing ? "保存监测配置" : "新增监测配置"}
                    </Button>
                    <Button type="button" variant="outline" className="rounded-xl bg-white lg:min-w-24" onClick={onCancel}>取消</Button>
                </div>
            </div>
        </div>
    );
}

function TagRow({
    tagItem,
    editing,
    editingName,
    isMutating,
    onEditNameChange,
    onStartEdit,
    onSave,
    onCancel,
    onDisable,
}: {
    tagItem: InsightTagRead;
    editing: boolean;
    editingName: string;
    isMutating: boolean;
    onEditNameChange: (value: string) => void;
    onStartEdit: (tagItem: InsightTagRead) => void;
    onSave: (tagItem: InsightTagRead) => void;
    onCancel: () => void;
    onDisable: (tagId: number) => void;
}) {
    return (
        <div className="grid gap-3 px-4 py-3 lg:grid-cols-[minmax(0,1fr)_120px_160px] lg:items-center">
            <div className="min-w-0">
                {editing ? (
                    <Input value={editingName} onChange={(event) => onEditNameChange(event.target.value)} />
                ) : (
                    <div className="flex flex-wrap items-center gap-2">
                        <span className="text-sm font-black text-slate-900">{tagItem.tag_name}</span>
                        <Badge variant={tagItem.status === "active" ? "default" : "outline"}>{tagItem.status === "active" ? "启用" : "禁用"}</Badge>
                    </div>
                )}
                <div className="mt-2 flex flex-wrap gap-2 text-xs font-semibold text-slate-500">
                    <span>编码：{tagItem.tag_code}</span>
                    <span>类型：{tagTypeLabels[tagItem.tag_type] ?? tagItem.tag_type}</span>
                    <span>排序：{tagItem.sort_no}</span>
                </div>
            </div>
            <div className="text-xs font-bold text-slate-500">更新：{formatDateTime(tagItem.update_time)}</div>
            <div className="flex flex-wrap justify-start gap-2 lg:justify-end">
                {editing ? (
                    <>
                        <Button type="button" size="sm" className="rounded-xl" disabled={!editingName.trim() || isMutating} onClick={() => onSave(tagItem)}>
                            <Save className="size-4" />
                            保存
                        </Button>
                        <Button type="button" size="sm" variant="outline" className="rounded-xl bg-white" onClick={onCancel}>
                            取消
                        </Button>
                    </>
                ) : (
                    <>
                        <Button type="button" size="sm" variant="outline" className="rounded-xl bg-white" disabled={isMutating} onClick={() => onStartEdit(tagItem)}>
                            编辑
                        </Button>
                        <Button
                            type="button"
                            size="sm"
                            variant="outline"
                            className="rounded-xl bg-white text-rose-600"
                            disabled={tagItem.status !== "active" || isMutating}
                            onClick={() => onDisable(tagItem.id)}
                        >
                            <XCircle className="size-4" />
                            禁用
                        </Button>
                    </>
                )}
            </div>
        </div>
    );
}

function IntelligenceTypeCard({ typeItem }: { typeItem: InsightIntelligenceTypeRead }) {
    return (
        <div className="rounded-xl border border-slate-200 bg-white p-4">
            <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                    <div className="text-sm font-black text-slate-900">{typeItem.type_name}</div>
                    <div className="mt-1 text-xs font-semibold text-slate-500">{typeItem.type_code}</div>
                </div>
                <Badge variant="outline">只读</Badge>
            </div>
            <p className="mt-3 text-sm leading-6 text-slate-600">{typeItem.description}</p>
            <div className="mt-3 text-xs font-bold text-slate-500">已使用 {typeItem.usage_count} 条</div>
        </div>
    );
}

function SummaryTile({ label, value, tone }: { label: string; value: number; tone: keyof typeof statusMeta }) {
    const meta = statusMeta[tone];
    return (
        <div className={`rounded-xl border px-4 py-3 ${meta.className}`}>
            <div className="text-xs font-black">{label}</div>
            <div className="mt-2 text-2xl font-black">{value}</div>
        </div>
    );
}

function countItems(sections: { items: InsightSettingsStatusItem[] }[], status: InsightSettingsStatusItem["status"]) {
    return sections.reduce((total, section) => total + section.items.filter((item) => item.status === status).length, 0);
}

function formatDateTime(value?: string | null) {
    if (!value) return "未知";
    return new Date(value).toLocaleString("zh-CN", { hour12: false });
}

function buildChannelPayload(form: ChannelFormState): InsightChannelCreate {
    return {
        channel_name: form.channel_name.trim(),
        channel_type: form.channel_type,
        channel_url: form.channel_url.trim() || null,
        applicable_scenarios: splitList(form.applicable_scenarios),
        collection_method: form.collection_method,
        login_requirement: form.login_requirement,
        access_status: form.access_status,
        default_trust_level: form.default_trust_level,
        default_frequency: form.default_frequency,
        default_processing_policy: form.default_processing_policy,
        comment: form.comment.trim() || null,
    };
}

function buildExecutionPayload(form: ExecutionFormState): InsightDataSourceCreate {
    return {
        source_name: form.source_name.trim(),
        source_type: form.source_type,
        base_url: form.base_url.trim() || null,
        channel_id: parseOptionalId(form.channel_id),
        monitor_config_id: parseOptionalId(form.monitor_config_id),
        monitor_object_type: form.monitor_config_id ? "topic" : null,
        execution_role: form.execution_role,
        generation_mode: "manual",
        collection_strategy: "standard",
        fetch_frequency: form.fetch_frequency,
        fetch_config: {
            keywords: splitList(form.keywords),
            max_results: 8,
            crawl_top_n: 0,
            freshness: "noLimit",
            schedule_type: form.fetch_frequency,
            enable_llm_filter: true,
            filter_prompt: "保留与研发营销市场洞察相关的信息，过滤广告、招聘、百科泛信息和重复转载。",
            auto_review_mode: "high_confidence",
            auto_review_min_confidence: 0.72,
            create_candidate_from_hits: true,
        },
        schedule_enabled: form.fetch_frequency !== "manual",
        visibility_scope: "assigned",
        status: form.status,
    };
}

function buildMonitorPayload(form: MonitorFormState): InsightMonitorConfigCreate {
    return {
        config_name: form.config_name.trim(),
        monitor_type: form.monitor_type,
        object_type: form.object_type,
        object_name: form.object_name.trim() || null,
        relation_type: form.relation_type.trim() || null,
        enabled_modules: splitList(form.enabled_modules),
        keywords: splitList(form.keywords),
        excluded_keywords: splitList(form.excluded_keywords),
        source_channel_ids: splitIdList(form.source_channel_ids),
        monitor_strength: form.monitor_strength,
        fetch_frequency: form.fetch_frequency,
        ai_review_prompt: form.ai_review_prompt.trim() || null,
        ai_review_policy: "ai_auto",
        visibility_scope: form.visibility_scope,
        generation_mode: "user_created",
        status: form.status,
    };
}

function splitList(value: string) {
    return value
        .split(/[、,，;；\n]/)
        .map((item) => item.trim())
        .filter(Boolean);
}

function splitIdList(value: string) {
    return splitList(value)
        .map((item) => Number(item))
        .filter((item) => Number.isFinite(item) && item > 0);
}

function parseOptionalId(value: string) {
    const parsed = Number(value);
    return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}

function frequencyLabel(value: string) {
    const labels: Record<string, string> = { manual: "手动", daily: "每日", weekly: "每周", monthly: "每月" };
    return labels[value] ?? value;
}

function processingPolicyLabel(value: string) {
    const labels: Record<string, string> = { ai_review: "AI 自动评审", candidate_only: "仅候选", do_not_import: "暂不入库" };
    return labels[value] ?? value;
}

function loginRequirementLabel(value: string) {
    const labels: Record<string, string> = { none: "不需要", account_required: "需要账号", licensed: "需要授权", unknown: "未知" };
    return labels[value] ?? value;
}

function trustLevelLabel(value: string) {
    const labels: Record<string, string> = { high: "高", medium: "中", low: "低" };
    return labels[value] ?? value;
}

function strategyLabel(value: string) {
    const labels: Record<string, string> = { light: "轻量", standard: "标准", deep: "深度", structured: "结构化" };
    return labels[value] ?? value;
}

function generationModeLabel(value: string) {
    const labels: Record<string, string> = {
        manual: "手工",
        user_created: "用户创建",
        system_generated: "系统生成",
        legacy_migrated: "历史迁移",
        imported: "导入",
    };
    return labels[value] ?? value;
}
