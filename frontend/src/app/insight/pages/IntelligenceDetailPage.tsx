import { useState } from "react";
import { Bookmark, Clock, ExternalLink, EyeOff, FileText, Send, ShieldCheck } from "lucide-react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";

import type { InsightIntelligenceDetail, InsightIntelligenceSourceCreate, InsightIntelligenceUpdate } from "../api";
import { AccessRuleDialog, WecomPushDialog } from "../components";
import { DemoCard, DemoTag, RankList, SectionHeader } from "../components/DemoPrimitives";
import {
    useInsightAddIntelligenceSource,
    useInsightIntelligenceDetail,
    useInsightUpdateIntelligence,
    useInsightUpsertPool,
    useInsightVisibilityRules,
} from "../hooks";
import { PageContainer } from "../layout/PageContainer";
import { formatInsightDate, formatInsightType } from "../utils/display";

export function IntelligenceDetailPage() {
    const params = useParams();
    const navigate = useNavigate();
    const intelligenceId = Number(params.id);
    const detailQuery = useInsightIntelligenceDetail(Number.isFinite(intelligenceId) ? intelligenceId : null);
    const visibilityQuery = useInsightVisibilityRules(Number.isFinite(intelligenceId) ? intelligenceId : null);
    const updateMutation = useInsightUpdateIntelligence();
    const addSourceMutation = useInsightAddIntelligenceSource();
    const poolMutation = useInsightUpsertPool();
    const [editOpen, setEditOpen] = useState(false);
    const [sourceOpen, setSourceOpen] = useState(false);
    const [accessOpen, setAccessOpen] = useState(false);
    const [pushOpen, setPushOpen] = useState(false);
    const detail = detailQuery.data;
    const primarySource = detail?.sources[0];
    const suggestedTags = Array.isArray(detail?.raw_payload?.suggested_tags) ? detail.raw_payload.suggested_tags : [];

    if (detailQuery.isLoading) {
        return (
            <PageContainer>
                <DemoCard className="p-10 text-center text-sm font-semibold text-slate-500">正在加载情报详情...</DemoCard>
            </PageContainer>
        );
    }

    if (!detail) {
        return (
            <PageContainer>
                <DemoCard className="p-10 text-center">
                    <div className="text-lg font-black text-slate-900">未找到情报</div>
                    <Link to="/insight/intelligence" className="mt-4 inline-flex text-sm font-bold text-blue-600">
                        返回情报中心
                    </Link>
                </DemoCard>
            </PageContainer>
        );
    }

    return (
        <PageContainer>
            <div className="insight-page-heading">
                <div>
                    <h1 className="text-2xl font-black leading-tight tracking-tight text-slate-950 md:text-3xl">情报详情</h1>
                    <div className="mt-2 text-sm font-semibold text-slate-500">首页看板 / 情报中心 / 情报详情</div>
                </div>
                <div className="insight-actions lg:max-w-[760px]">
                    <Button variant="outline" className="h-10 rounded-xl" onClick={() => {
                        poolMutation.mutate({ intelligenceId: detail.id, data: { pool_type: "favorite" } }, { onSuccess: () => toast.success("已加入收藏") });
                    }}>
                        <Bookmark className="size-4" />
                        收藏
                    </Button>
                    <Button variant="outline" className="h-10 rounded-xl" onClick={() => {
                        poolMutation.mutate({ intelligenceId: detail.id, data: { pool_type: "later" } }, { onSuccess: () => toast.success("已加入稍后看") });
                    }}>
                        稍后看
                    </Button>
                    <Button variant="outline" className="h-10 rounded-xl" onClick={() => {
                        poolMutation.mutate(
                            { intelligenceId: detail.id, data: { pool_type: "report_material", folder_name: "默认报告素材" } },
                            { onSuccess: () => toast.success("已加入报告素材") },
                        );
                    }}>
                        <FileText className="size-4" />
                        报告素材
                    </Button>
                    <Button variant="outline" className="h-10 rounded-xl border-slate-200 bg-white text-slate-600 shadow-none hover:bg-slate-50" onClick={() => {
                        poolMutation.mutate({ intelligenceId: detail.id, data: { pool_type: "hidden" } }, {
                            onSuccess: () => {
                                toast.success("已隐藏该情报");
                                navigate("/insight/intelligence");
                            },
                        });
                    }}>
                        <EyeOff className="size-4" />
                        隐藏
                    </Button>
                    <Button variant="outline" className="h-10 rounded-xl text-blue-700" onClick={() => setAccessOpen(true)}>
                        <ShieldCheck className="size-4" />
                        权限
                    </Button>
                    <Button variant="outline" className="h-10 rounded-xl text-emerald-700" onClick={() => setPushOpen(true)}>
                        <Send className="size-4" />
                        企微推送
                    </Button>
                    <Button variant="outline" className="h-10 rounded-xl" onClick={() => setSourceOpen(true)}>
                        补充来源
                    </Button>
                    <Button className="h-10 rounded-xl" onClick={() => setEditOpen(true)}>
                        编辑情报
                    </Button>
                </div>
            </div>

            <DemoCard className="p-4 sm:p-6">
                <div className="flex flex-col justify-between gap-5 lg:flex-row lg:items-end">
                    <div className="min-w-0">
                        <h2 className="text-2xl font-black leading-tight tracking-tight text-slate-950 md:text-3xl">{detail.title}</h2>
                        <div className="mt-5 flex flex-wrap items-center gap-x-6 gap-y-3 text-sm font-semibold text-slate-600 md:mt-7">
                            <span>来源：{primarySource?.source_type ?? "未记录"}</span>
                            <span className="inline-flex items-center gap-2">
                                <Clock className="size-4" />
                                发布时间：{formatInsightDate(detail.publish_time ?? primarySource?.source_publish_time, detail.capture_time ?? detail.create_time)}
                            </span>
                            <span>
                                主题：<span className="text-blue-600">{detail.subject_name || subjectTypeText[detail.subject_type] || "未识别"}</span>
                            </span>
                            <span>
                                信息类型：<DemoTag tone="blue">{formatInsightType(detail.intelligence_type)}</DemoTag>
                            </span>
                        </div>
                    </div>
                    {primarySource?.source_url ? (
                        <a href={primarySource.source_url} target="_blank" rel="noreferrer">
                            <Button variant="outline" className="h-10 rounded-xl">
                                原文链接
                                <ExternalLink className="size-4" />
                            </Button>
                        </a>
                    ) : null}
                </div>
            </DemoCard>

            <div className="grid min-h-0 gap-4 2xl:grid-cols-[minmax(0,1fr)_430px]">
                <div className="space-y-4">
                    <DemoCard className="p-6">
                        <SectionHeader title="摘要" action="" />
                        <div className="text-base leading-8 text-slate-700">{detail.summary || primarySource?.content_excerpt || "暂无摘要"}</div>
                    </DemoCard>

                    <DemoCard className="p-6">
                        <SectionHeader title="原文内容" action="" />
                        <div className="max-h-[min(680px,60dvh)] overflow-auto whitespace-pre-wrap text-base leading-9 text-slate-700">
                            {detail.content || primarySource?.content_excerpt || "暂无正文内容"}
                        </div>
                    </DemoCard>

                    <DemoCard className="p-6">
                        <SectionHeader title="来源证据" action="" />
                        <div className="space-y-3">
                            {detail.sources.length > 0 ? (
                                detail.sources.map((source) => (
                                    <div key={source.id} className="rounded-xl border border-slate-200 bg-white p-4">
                                        <div className="flex flex-wrap items-start justify-between gap-4">
                                            <div className="min-w-0">
                                                <div className="flex items-center gap-2 text-sm font-black text-slate-800">
                                                    <FileText className="size-4 text-blue-600" />
                                                    {source.source_title || "未命名来源"}
                                                </div>
                                                <div className="mt-2 text-xs font-semibold text-slate-500">
                                                    {source.source_type} · {formatInsightDate(source.source_publish_time, source.create_time)}
                                                </div>
                                            </div>
                                            {source.source_url ? (
                                                <a href={source.source_url} target="_blank" rel="noreferrer" className="shrink-0 text-sm font-bold text-blue-600">
                                                    打开
                                                </a>
                                            ) : null}
                                        </div>
                                    </div>
                                ))
                            ) : (
                                <div className="text-sm font-semibold text-slate-500">暂无来源证据</div>
                            )}
                        </div>
                    </DemoCard>
                </div>

                <div className="space-y-4">
                    <DemoCard className="p-5">
                        <SectionHeader title="标签" action="" />
                        <div className="flex flex-wrap gap-3">
                            {suggestedTags.length > 0 ? (
                                suggestedTags.slice(0, 12).map((tag, index) => (
                                    <DemoTag key={`${tag.name ?? "tag"}-${index}`} tone={index % 3 === 0 ? "blue" : index % 3 === 1 ? "green" : "orange"} className="px-6">
                                        {tag.name ?? "标签"}
                                    </DemoTag>
                                ))
                            ) : (
                                <DemoTag tone="slate">暂无标签</DemoTag>
                            )}
                        </div>
                    </DemoCard>

                    <DemoCard className="p-5">
                        <SectionHeader title="情报属性" action="" />
                        <div className="space-y-3 text-sm font-semibold text-slate-600">
                            <InfoLine label="重要性" value={importanceText[detail.importance_level] ?? detail.importance_level} />
                            <InfoLine label="可见性" value={visibilityText[detail.visibility_scope] ?? detail.visibility_scope} />
                            <InfoLine label="审核状态" value={detail.review_status} />
                            <InfoLine label="来源数量" value={`${detail.sources.length} 条`} />
                        </div>
                    </DemoCard>

                    <DemoCard className="p-5">
                        <SectionHeader title="授权规则" action="" />
                        <div className="space-y-3 text-sm font-semibold text-slate-600">
                            {(visibilityQuery.data ?? []).length > 0 ? (
                                (visibilityQuery.data ?? []).slice(0, 6).map((rule) => (
                                    <div key={rule.id} className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 pb-3">
                                        <span>{principalText[rule.principal_type] ?? rule.principal_type}</span>
                                        <span className="font-black text-slate-900">{rule.principal_id ?? "全员"}</span>
                                    </div>
                                ))
                            ) : (
                                <div className="text-sm font-semibold text-slate-500">暂无显式授权规则</div>
                            )}
                        </div>
                    </DemoCard>

                    <DemoCard className="p-5">
                        <SectionHeader title="相似情报推荐" />
                        <RankList items={["同主题最新正式情报待接入", "同来源历史情报待接入", "同标签趋势情报待接入", "同业务域机会点待接入"]} />
                    </DemoCard>
                </div>
            </div>
            <EditIntelligenceDialog
                key={`${detail.id}-${detail.update_time}-${editOpen ? "open" : "closed"}`}
                detail={detail}
                open={editOpen}
                pending={updateMutation.isPending}
                onOpenChange={setEditOpen}
                onSubmit={(payload) => {
                    updateMutation.mutate(
                        { intelligenceId: detail.id, data: payload },
                        {
                            onSuccess: () => {
                                toast.success("情报已更新");
                                setEditOpen(false);
                            },
                            onError: () => toast.error("情报更新失败"),
                        },
                    );
                }}
            />
            <AddSourceDialog
                open={sourceOpen}
                pending={addSourceMutation.isPending}
                onOpenChange={setSourceOpen}
                onSubmit={(payload) => {
                    addSourceMutation.mutate(
                        { intelligenceId: detail.id, data: payload },
                        {
                            onSuccess: () => {
                                toast.success("来源证据已补充");
                                setSourceOpen(false);
                            },
                            onError: () => toast.error("来源补充失败"),
                        },
                    );
                }}
            />
            <AccessRuleDialog
                open={accessOpen}
                onOpenChange={setAccessOpen}
                targetType="intelligence"
                targetId={detail.id}
                targetName={detail.title}
            />
            <WecomPushDialog
                open={pushOpen}
                onOpenChange={setPushOpen}
                targetType="intelligence"
                targetId={detail.id}
                targetTitle={detail.title}
                defaultTitle={`市场情报：${detail.title}`}
                defaultContent={detail.summary || primarySource?.content_excerpt || "发现一条新的市场情报，请进入研发营销市场洞察平台查看原文与证据。"}
            />
        </PageContainer>
    );
}

function EditIntelligenceDialog({
    detail,
    open,
    pending,
    onOpenChange,
    onSubmit,
}: {
    detail: InsightIntelligenceDetail;
    open: boolean;
    pending: boolean;
    onOpenChange: (open: boolean) => void;
    onSubmit: (payload: InsightIntelligenceUpdate) => void;
}) {
    const [form, setForm] = useState({
        title: detail.title,
        subject_name: detail.subject_name ?? "",
        intelligence_type: detail.intelligence_type,
        visibility_scope: detail.visibility_scope,
        summary: detail.summary ?? "",
        content: detail.content ?? "",
    });
    const update = (field: keyof typeof form, value: string) => setForm((current) => ({ ...current, [field]: value }));
    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="max-h-[90vh] overflow-auto sm:max-w-3xl">
                <DialogHeader>
                    <DialogTitle>编辑正式情报</DialogTitle>
                </DialogHeader>
                <div className="grid gap-4 md:grid-cols-2">
                    <Field label="标题" value={form.title} onChange={(value) => update("title", value)} className="md:col-span-2" />
                    <Field label="主题名称" value={form.subject_name} onChange={(value) => update("subject_name", value)} />
                    <Field label="情报类型" value={form.intelligence_type} onChange={(value) => update("intelligence_type", value)} />
                    <Field label="可见性" value={form.visibility_scope} onChange={(value) => update("visibility_scope", value)} />
                    <TextAreaField label="摘要" value={form.summary} onChange={(value) => update("summary", value)} className="md:col-span-2" />
                    <TextAreaField label="正文" value={form.content} onChange={(value) => update("content", value)} className="md:col-span-2" rows={8} />
                </div>
                <DialogFooter>
                    <Button variant="ghost" onClick={() => onOpenChange(false)}>取消</Button>
                    <Button disabled={pending || !form.title.trim()} onClick={() => onSubmit({
                        title: form.title.trim(),
                        subject_name: form.subject_name.trim() || null,
                        intelligence_type: form.intelligence_type.trim() || "行业资讯",
                        visibility_scope: form.visibility_scope.trim() || "assigned",
                        summary: form.summary.trim() || null,
                        content: form.content.trim() || null,
                    })}>
                        保存
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

function AddSourceDialog({
    open,
    pending,
    onOpenChange,
    onSubmit,
}: {
    open: boolean;
    pending: boolean;
    onOpenChange: (open: boolean) => void;
    onSubmit: (payload: InsightIntelligenceSourceCreate) => void;
}) {
    const [form, setForm] = useState({ source_type: "manual", source_title: "", source_url: "", content_excerpt: "" });
    const update = (field: keyof typeof form, value: string) => setForm((current) => ({ ...current, [field]: value }));
    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="sm:max-w-2xl">
                <DialogHeader>
                    <DialogTitle>补充来源证据</DialogTitle>
                </DialogHeader>
                <div className="grid gap-4 md:grid-cols-2">
                    <Field label="来源类型" value={form.source_type} onChange={(value) => update("source_type", value)} />
                    <Field label="来源标题" value={form.source_title} onChange={(value) => update("source_title", value)} />
                    <Field label="来源 URL" value={form.source_url} onChange={(value) => update("source_url", value)} className="md:col-span-2" />
                    <TextAreaField label="摘录" value={form.content_excerpt} onChange={(value) => update("content_excerpt", value)} className="md:col-span-2" />
                </div>
                <DialogFooter>
                    <Button variant="ghost" onClick={() => onOpenChange(false)}>取消</Button>
                    <Button disabled={pending} onClick={() => onSubmit({
                        source_type: form.source_type.trim() || "manual",
                        source_title: form.source_title.trim() || undefined,
                        source_url: form.source_url.trim() || undefined,
                        content_excerpt: form.content_excerpt.trim() || undefined,
                    })}>
                        保存
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

function Field({
    label,
    value,
    onChange,
    className,
}: {
    label: string;
    value: string;
    onChange: (value: string) => void;
    className?: string;
}) {
    return (
        <label className={`grid gap-2 ${className ?? ""}`}>
            <span className="text-sm font-bold text-slate-700">{label}</span>
            <Input className="h-11 rounded-xl border-slate-200 bg-white shadow-none" value={value} onChange={(event) => onChange(event.target.value)} />
        </label>
    );
}

function TextAreaField({
    label,
    value,
    onChange,
    className,
    rows = 4,
}: {
    label: string;
    value: string;
    onChange: (value: string) => void;
    className?: string;
    rows?: number;
}) {
    return (
        <label className={`grid gap-2 ${className ?? ""}`}>
            <span className="text-sm font-bold text-slate-700">{label}</span>
            <textarea
                className="min-h-24 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm shadow-none outline-none focus:border-blue-300"
                rows={rows}
                value={value}
                onChange={(event) => onChange(event.target.value)}
            />
        </label>
    );
}

function InfoLine({ label, value }: { label: string; value: string }) {
    return (
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 pb-3">
            <span>{label}</span>
            <span className="font-black text-slate-900">{value}</span>
        </div>
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

const visibilityText: Record<string, string> = {
    private: "私有",
    assigned: "指定可见",
    dept: "部门可见",
    role: "角色可见",
    public: "公开",
};

const principalText: Record<string, string> = {
    user: "用户",
    role: "角色",
    dept: "部门",
    all: "全员",
};

const importanceText: Record<string, string> = {
    low: "低",
    medium: "中",
    high: "高",
};
