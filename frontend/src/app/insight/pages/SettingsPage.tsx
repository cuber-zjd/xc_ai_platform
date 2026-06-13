import { useState } from "react";
import { AlertTriangle, CheckCircle2, CircleSlash, Loader2, Plus, RefreshCw, Save, Settings, Tag, XCircle } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

import { PageTitle, SectionCard } from "../components";
import { useInsightCreateTag, useInsightDictionaryOverview, useInsightDisableTag, useInsightSettingsStatus, useInsightUpdateTag } from "../hooks";
import { PageContainer } from "../layout/PageContainer";
import type { InsightIntelligenceTypeRead, InsightSettingsStatusItem, InsightTagRead } from "../api";

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

export function SettingsPage() {
    const statusQuery = useInsightSettingsStatus();
    const dictionaryQuery = useInsightDictionaryOverview();
    const createTagMutation = useInsightCreateTag();
    const updateTagMutation = useInsightUpdateTag();
    const disableTagMutation = useInsightDisableTag();
    const sections = statusQuery.data?.sections ?? [];
    const dictionary = dictionaryQuery.data;
    const [newTagName, setNewTagName] = useState("");
    const [newTagType, setNewTagType] = useState("business");
    const [editingTagId, setEditingTagId] = useState<number | null>(null);
    const [editingTagName, setEditingTagName] = useState("");

    const isMutating = createTagMutation.isPending || updateTagMutation.isPending || disableTagMutation.isPending;

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

    return (
        <PageContainer>
            <PageTitle
                title="系统设置"
                description="展示 Insight 当前配置健康状态，并维护上线首版需要统一口径的业务字典。敏感配置只显示是否已配置。"
                action={
                    <Button
                        type="button"
                        variant="outline"
                        className="rounded-xl border-slate-200 bg-white"
                        onClick={() => {
                            void statusQuery.refetch();
                            void dictionaryQuery.refetch();
                        }}
                    >
                        {statusQuery.isFetching || dictionaryQuery.isFetching ? <Loader2 className="size-4 animate-spin" /> : <RefreshCw className="size-4" />}
                        刷新
                    </Button>
                }
            />

            <div className="space-y-5">
                {statusQuery.isLoading ? (
                    <SectionCard>
                        <div className="flex min-h-[220px] items-center justify-center gap-3 text-sm font-bold text-slate-500">
                            <Loader2 className="size-5 animate-spin" />
                            正在读取配置状态
                        </div>
                    </SectionCard>
                ) : statusQuery.isError ? (
                    <SectionCard>
                        <div className="flex min-h-[220px] flex-col items-center justify-center gap-3 text-center">
                            <Settings className="size-8 text-amber-500" />
                            <div className="text-base font-black text-slate-900">配置状态读取失败</div>
                            <div className="text-sm font-semibold text-slate-500">请确认当前账号已登录，且后端 Insight 设置状态接口可访问。</div>
                        </div>
                    </SectionCard>
                ) : (
                    <>
                        <SectionCard title="配置总览" description={`只读状态面板，最后刷新时间：${formatDateTime(statusQuery.data?.generated_at)}`}>
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
                    </>
                )}

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

                <SectionCard title="情报类型字典" description="当前情报类型采用内置受控口径，供筛选、展示和生成约束统一使用。">
                    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                        {(dictionary?.intelligence_types ?? []).map((typeItem) => (
                            <IntelligenceTypeCard key={typeItem.type_code} typeItem={typeItem} />
                        ))}
                    </div>
                </SectionCard>
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

function formatDateTime(value?: string) {
    if (!value) return "未知";
    return new Date(value).toLocaleString("zh-CN", { hour12: false });
}
