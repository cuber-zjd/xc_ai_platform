import { useMemo, useState, type ReactNode } from "react";
import { FolderTree, Loader2, Pencil, Plus, Save, Search, Tag, Tags, XCircle, type LucideIcon } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { cn } from "@/lib/utils";

import {
    useInsightCreateTag,
    useInsightCreateTagCategory,
    useInsightDictionaryOverview,
    useInsightDisableTag,
    useInsightDisableTagCategory,
    useInsightUpdateTag,
    useInsightUpdateTagCategory,
} from "../hooks";
import { PageContainer } from "../layout/PageContainer";
import type { InsightTagCategoryRead, InsightTagRead } from "../api";

const colors = ["#2563eb", "#0891b2", "#16a34a", "#0d9488", "#9333ea", "#ea580c", "#dc2626", "#64748b"];

const emptyCategoryForm: CategoryFormState = {
    category_name: "",
    description: "",
    color: "#2563eb",
    sort_no: "0",
};

const emptyTagForm: TagFormState = {
    tag_name: "",
    tag_code: "",
    tag_type: "",
    color: "#2563eb",
    sort_no: "0",
};

type CategoryFilter = "all" | string;

interface CategoryFormState {
    category_name: string;
    description: string;
    color: string;
    sort_no: string;
}

interface TagFormState {
    tag_name: string;
    tag_code: string;
    tag_type: string;
    color: string;
    sort_no: string;
}

export function TagCategoryPage() {
    const dictionaryQuery = useInsightDictionaryOverview();
    const createCategoryMutation = useInsightCreateTagCategory();
    const updateCategoryMutation = useInsightUpdateTagCategory();
    const disableCategoryMutation = useInsightDisableTagCategory();
    const createTagMutation = useInsightCreateTag();
    const updateTagMutation = useInsightUpdateTag();
    const disableTagMutation = useInsightDisableTag();

    const dictionary = dictionaryQuery.data;
    const tags = useMemo(() => dictionary?.tags ?? [], [dictionary?.tags]);
    const categories = useMemo(() => normalizeCategories(dictionary?.categories ?? [], tags), [dictionary?.categories, tags]);
    const activeCategories = categories.filter((item) => item.status === "active");
    const [selectedCategory, setSelectedCategory] = useState<CategoryFilter>("all");
    const [keyword, setKeyword] = useState("");
    const [categoryDialogOpen, setCategoryDialogOpen] = useState(false);
    const [tagDialogOpen, setTagDialogOpen] = useState(false);
    const [editingCategory, setEditingCategory] = useState<InsightTagCategoryRead | null>(null);
    const [editingTag, setEditingTag] = useState<InsightTagRead | null>(null);
    const [categoryForm, setCategoryForm] = useState<CategoryFormState>(emptyCategoryForm);
    const [tagForm, setTagForm] = useState<TagFormState>(emptyTagForm);

    const filteredTags = useMemo(() => {
        const normalizedKeyword = keyword.trim().toLowerCase();
        return tags.filter((item) => {
            const categoryMatched = selectedCategory === "all" || item.tag_type === selectedCategory;
            if (!categoryMatched) return false;
            if (!normalizedKeyword) return true;
            return `${item.tag_name} ${item.tag_code} ${item.tag_type}`.toLowerCase().includes(normalizedKeyword);
        });
    }, [keyword, selectedCategory, tags]);
    const selectedCategoryItem = categories.find((item) => item.category_code === selectedCategory);
    const isMutating =
        createCategoryMutation.isPending ||
        updateCategoryMutation.isPending ||
        disableCategoryMutation.isPending ||
        createTagMutation.isPending ||
        updateTagMutation.isPending ||
        disableTagMutation.isPending;

    const openCreateCategory = () => {
        setEditingCategory(null);
        setCategoryForm(emptyCategoryForm);
        setCategoryDialogOpen(true);
    };

    const openEditCategory = (category: InsightTagCategoryRead) => {
        setEditingCategory(category);
        setCategoryForm({
            category_name: category.category_name,
            description: category.description ?? "",
            color: category.color ?? "#2563eb",
            sort_no: String(category.sort_no ?? 0),
        });
        setCategoryDialogOpen(true);
    };

    const openCreateTag = () => {
        setEditingTag(null);
        setTagForm({
            ...emptyTagForm,
            tag_type: selectedCategory === "all" ? activeCategories[0]?.category_code ?? "业务价值" : selectedCategory,
        });
        setTagDialogOpen(true);
    };

    const openEditTag = (tagItem: InsightTagRead) => {
        setEditingTag(tagItem);
        setTagForm({
            tag_name: tagItem.tag_name,
            tag_code: tagItem.tag_code,
            tag_type: tagItem.tag_type,
            color: tagItem.color ?? "#2563eb",
            sort_no: String(tagItem.sort_no ?? 0),
        });
        setTagDialogOpen(true);
    };

    const saveCategory = async () => {
        const payload = {
            category_name: categoryForm.category_name.trim(),
            description: categoryForm.description.trim() || null,
            color: categoryForm.color,
            sort_no: numberValue(categoryForm.sort_no),
        };
        if (!payload.category_name) return;
        try {
            const result = editingCategory
                ? await updateCategoryMutation.mutateAsync({ categoryId: editingCategory.id, data: payload })
                : await createCategoryMutation.mutateAsync(payload);
            toast.success(editingCategory ? "分类已更新" : "分类已创建");
            setSelectedCategory(result.category_code);
            setCategoryDialogOpen(false);
            setEditingCategory(null);
            setCategoryForm(emptyCategoryForm);
        } catch (error) {
            toast.error(errorMessage(error, "分类保存失败"));
        }
    };

    const saveTag = async () => {
        const payload = {
            tag_name: tagForm.tag_name.trim(),
            tag_code: editingTag ? undefined : tagForm.tag_code.trim() || undefined,
            tag_type: tagForm.tag_type || activeCategories[0]?.category_code || "业务价值",
            color: tagForm.color,
            sort_no: numberValue(tagForm.sort_no),
        };
        if (!payload.tag_name) return;
        try {
            await (editingTag ? updateTagMutation.mutateAsync({ tagId: editingTag.id, data: payload }) : createTagMutation.mutateAsync(payload));
            toast.success(editingTag ? "标签已更新" : "标签已创建");
            setSelectedCategory(payload.tag_type);
            setTagDialogOpen(false);
            setEditingTag(null);
            setTagForm(emptyTagForm);
        } catch (error) {
            toast.error(errorMessage(error, "标签保存失败"));
        }
    };

    const disableCategory = async (category: InsightTagCategoryRead) => {
        try {
            await disableCategoryMutation.mutateAsync(category.id);
            toast.success("分类已禁用");
            if (selectedCategory === category.category_code) setSelectedCategory("all");
        } catch (error) {
            toast.error(errorMessage(error, "分类禁用失败"));
        }
    };

    const disableTag = async (tagItem: InsightTagRead) => {
        try {
            await disableTagMutation.mutateAsync(tagItem.id);
            toast.success("标签已禁用");
        } catch (error) {
            toast.error(errorMessage(error, "标签禁用失败"));
        }
    };

    return (
        <PageContainer className="flex h-full min-h-0 flex-col gap-3 overflow-hidden">
            <div className="flex shrink-0 flex-col gap-2 rounded-2xl border border-slate-200 bg-white p-3 shadow-sm lg:flex-row lg:items-center lg:justify-between">
                <div className="flex min-w-0 items-center gap-2">
                    <div className="grid size-9 shrink-0 place-items-center rounded-xl bg-blue-50 text-blue-700">
                        <Tags className="size-4" />
                    </div>
                    <div className="min-w-0">
                        <div className="text-sm font-black text-slate-950">分类及标签管理</div>
                        <div className="truncate text-xs font-semibold text-slate-500">AI 评审只会从启用标签中选择，新增口径先进入建议标签</div>
                    </div>
                </div>
                <div className="flex flex-wrap gap-2">
                    <Button type="button" variant="outline" className="h-9 rounded-xl bg-white" onClick={openCreateCategory}>
                        <FolderTree className="size-4" />
                        新增分类
                    </Button>
                    <Button type="button" className="h-9 rounded-xl bg-blue-600 text-white hover:bg-blue-700" onClick={openCreateTag}>
                        <Plus className="size-4" />
                        新增标签
                    </Button>
                </div>
            </div>

            <div className="grid min-h-0 flex-1 gap-3 lg:grid-cols-[300px_minmax(0,1fr)]">
                <section className="flex min-h-0 flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
                    <div className="flex shrink-0 items-center justify-between border-b border-slate-100 px-4 py-3">
                        <div className="text-sm font-black text-slate-900">分类</div>
                        <Badge variant="outline">{categories.length}</Badge>
                    </div>
                    <div className="min-h-0 flex-1 overflow-y-auto p-2">
                        <CategoryButton
                            active={selectedCategory === "all"}
                            name="全部标签"
                            count={tags.length}
                            color="#2563eb"
                            onClick={() => setSelectedCategory("all")}
                        />
                        {dictionaryQuery.isLoading ? (
                            <div className="flex h-28 items-center justify-center gap-2 text-sm font-semibold text-slate-500">
                                <Loader2 className="size-4 animate-spin" />
                                正在读取分类
                            </div>
                        ) : (
                            categories.map((category) => (
                                <CategoryButton
                                    key={category.category_code}
                                    active={selectedCategory === category.category_code}
                                    name={category.category_name}
                                    count={category.tag_count}
                                    color={category.color ?? "#64748b"}
                                    disabled={category.status !== "active"}
                                    onClick={() => setSelectedCategory(category.category_code)}
                                    onEdit={() => openEditCategory(category)}
                                    onDisable={() => disableCategory(category)}
                                />
                            ))
                        )}
                    </div>
                </section>

                <section className="flex min-h-0 flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
                    <div className="grid shrink-0 gap-2 border-b border-slate-100 bg-slate-50/70 p-3 md:grid-cols-[minmax(0,1fr)_180px]">
                        <div className="relative min-w-0">
                            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-400" />
                            <Input
                                value={keyword}
                                onChange={(event) => setKeyword(event.target.value)}
                                className="h-10 rounded-xl bg-white pl-9"
                                placeholder="搜索标签名称、编码或分类"
                            />
                        </div>
                        <div className="flex items-center justify-end gap-2 text-xs font-bold text-slate-500">
                            <span>{selectedCategoryItem?.category_name ?? "全部分类"}</span>
                            <Badge variant="outline">{filteredTags.length} 个标签</Badge>
                        </div>
                    </div>

                    <div className="min-h-0 flex-1 overflow-y-auto">
                        {dictionaryQuery.isError ? (
                            <EmptyState icon={XCircle} text="字典读取失败，请稍后重试" />
                        ) : filteredTags.length ? (
                            <div className="divide-y divide-slate-100">
                                {filteredTags.map((tagItem) => (
                                    <TagRow key={tagItem.id} tagItem={tagItem} category={categories.find((item) => item.category_code === tagItem.tag_type)} onEdit={openEditTag} onDisable={disableTag} />
                                ))}
                            </div>
                        ) : (
                            <EmptyState icon={Tag} text="当前筛选下暂无标签" />
                        )}
                    </div>

                    <div className="grid shrink-0 gap-2 border-t border-slate-100 bg-slate-50 px-4 py-3 text-xs font-semibold text-slate-500 md:grid-cols-3">
                        <div>启用标签：{tags.filter((item) => item.status === "active").length}</div>
                        <div>禁用标签：{tags.filter((item) => item.status !== "active").length}</div>
                        <div>情报类型：{dictionary?.intelligence_types.length ?? 0} 个受控口径</div>
                    </div>
                </section>
            </div>

            <Dialog open={categoryDialogOpen} onOpenChange={setCategoryDialogOpen}>
                <DialogContent className="max-w-xl rounded-2xl p-5">
                    <DialogHeader>
                        <DialogTitle>{editingCategory ? "编辑分类" : "新增分类"}</DialogTitle>
                    </DialogHeader>
                    <div className="grid gap-4">
                        <Field label="分类名称">
                            <Input value={categoryForm.category_name} onChange={(event) => setCategoryForm((current) => ({ ...current, category_name: event.target.value }))} placeholder="如 产品方向" />
                        </Field>
                        <Field label="说明">
                            <Input value={categoryForm.description} onChange={(event) => setCategoryForm((current) => ({ ...current, description: event.target.value }))} placeholder="用于说明这个分类的业务边界" />
                        </Field>
                        <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_120px]">
                            <Field label="颜色">
                                <ColorPicker value={categoryForm.color} onChange={(color) => setCategoryForm((current) => ({ ...current, color }))} />
                            </Field>
                            <Field label="排序">
                                <Input value={categoryForm.sort_no} onChange={(event) => setCategoryForm((current) => ({ ...current, sort_no: event.target.value }))} />
                            </Field>
                        </div>
                        <div className="flex justify-end gap-2">
                            <Button type="button" variant="outline" className="rounded-xl bg-white" onClick={() => setCategoryDialogOpen(false)}>取消</Button>
                            <Button type="button" className="rounded-xl bg-blue-600 text-white hover:bg-blue-700" disabled={!categoryForm.category_name.trim() || isMutating} onClick={saveCategory}>
                                {isMutating ? <Loader2 className="size-4 animate-spin" /> : <Save className="size-4" />}
                                保存分类
                            </Button>
                        </div>
                    </div>
                </DialogContent>
            </Dialog>

            <Dialog open={tagDialogOpen} onOpenChange={setTagDialogOpen}>
                <DialogContent className="max-w-xl rounded-2xl p-5">
                    <DialogHeader>
                        <DialogTitle>{editingTag ? "编辑标签" : "新增标签"}</DialogTitle>
                    </DialogHeader>
                    <div className="grid gap-4">
                        <Field label="标签名称">
                            <Input value={tagForm.tag_name} onChange={(event) => setTagForm((current) => ({ ...current, tag_name: event.target.value }))} placeholder="如 销售机会" />
                        </Field>
                        <div className="grid gap-3 sm:grid-cols-2">
                            <Field label="所属分类">
                                <Select value={tagForm.tag_type || activeCategories[0]?.category_code} onValueChange={(value) => setTagForm((current) => ({ ...current, tag_type: value }))}>
                                    <SelectTrigger className="h-10 w-full rounded-xl bg-white">
                                        <SelectValue placeholder="选择分类" />
                                    </SelectTrigger>
                                    <SelectContent>
                                        {activeCategories.map((category) => (
                                            <SelectItem key={category.category_code} value={category.category_code}>{category.category_name}</SelectItem>
                                        ))}
                                    </SelectContent>
                                </Select>
                            </Field>
                            <Field label="标签编码">
                                <Input disabled={Boolean(editingTag)} value={tagForm.tag_code} onChange={(event) => setTagForm((current) => ({ ...current, tag_code: event.target.value }))} placeholder="可空，系统自动生成" />
                            </Field>
                        </div>
                        <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_120px]">
                            <Field label="颜色">
                                <ColorPicker value={tagForm.color} onChange={(color) => setTagForm((current) => ({ ...current, color }))} />
                            </Field>
                            <Field label="排序">
                                <Input value={tagForm.sort_no} onChange={(event) => setTagForm((current) => ({ ...current, sort_no: event.target.value }))} />
                            </Field>
                        </div>
                        <div className="flex justify-end gap-2">
                            <Button type="button" variant="outline" className="rounded-xl bg-white" onClick={() => setTagDialogOpen(false)}>取消</Button>
                            <Button type="button" className="rounded-xl bg-blue-600 text-white hover:bg-blue-700" disabled={!tagForm.tag_name.trim() || !tagForm.tag_type || isMutating} onClick={saveTag}>
                                {isMutating ? <Loader2 className="size-4 animate-spin" /> : <Save className="size-4" />}
                                保存标签
                            </Button>
                        </div>
                    </div>
                </DialogContent>
            </Dialog>
        </PageContainer>
    );
}

function CategoryButton({
    active,
    name,
    count,
    color,
    disabled,
    onClick,
    onEdit,
    onDisable,
}: {
    active: boolean;
    name: string;
    count: number;
    color: string;
    disabled?: boolean;
    onClick: () => void;
    onEdit?: () => void;
    onDisable?: () => void;
}) {
    return (
        <div className={cn("group mb-1 flex items-center gap-2 rounded-xl px-2 py-2 transition", active ? "bg-blue-50" : "hover:bg-slate-50", disabled && "opacity-60")}>
            <button type="button" className="flex min-w-0 flex-1 items-center gap-2 text-left" onClick={onClick}>
                <span className="size-2.5 shrink-0 rounded-full" style={{ backgroundColor: color }} />
                <span className={cn("truncate text-sm font-black", active ? "text-blue-700" : "text-slate-800")}>{name}</span>
                <span className="ml-auto rounded-full bg-slate-100 px-2 py-0.5 text-xs font-bold text-slate-500">{count}</span>
            </button>
            {onEdit ? (
                <button type="button" className="hidden rounded-lg p-1 text-slate-400 hover:bg-white hover:text-blue-600 group-hover:block" onClick={onEdit} title="编辑分类">
                    <Pencil className="size-3.5" />
                </button>
            ) : null}
            {onDisable ? (
                <button type="button" className="hidden rounded-lg p-1 text-slate-400 hover:bg-white hover:text-rose-600 group-hover:block" onClick={onDisable} title="禁用分类">
                    <XCircle className="size-3.5" />
                </button>
            ) : null}
        </div>
    );
}

function TagRow({
    tagItem,
    category,
    onEdit,
    onDisable,
}: {
    tagItem: InsightTagRead;
    category?: InsightTagCategoryRead;
    onEdit: (tagItem: InsightTagRead) => void;
    onDisable: (tagItem: InsightTagRead) => void;
}) {
    return (
        <div className="grid gap-3 px-4 py-3 lg:grid-cols-[minmax(0,1fr)_180px_130px] lg:items-center">
            <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                    <span className="size-2.5 rounded-full" style={{ backgroundColor: tagItem.color ?? category?.color ?? "#64748b" }} />
                    <span className="text-sm font-black text-slate-950">{tagItem.tag_name}</span>
                    <Badge variant={tagItem.status === "active" ? "default" : "outline"} className={tagItem.status === "active" ? "bg-blue-600" : ""}>
                        {tagItem.status === "active" ? "启用" : "禁用"}
                    </Badge>
                </div>
                <div className="mt-1 flex flex-wrap gap-2 text-xs font-semibold text-slate-500">
                    <span>{tagItem.tag_code}</span>
                    <span>{category?.category_name ?? tagItem.tag_type}</span>
                    <span>排序 {tagItem.sort_no}</span>
                </div>
            </div>
            <div className="text-xs font-bold text-slate-500">更新 {formatDateTime(tagItem.update_time)}</div>
            <div className="flex justify-start gap-2 lg:justify-end">
                <Button type="button" variant="outline" size="sm" className="h-8 rounded-lg bg-white" onClick={() => onEdit(tagItem)}>
                    <Pencil className="size-3.5" />
                    编辑
                </Button>
                <Button type="button" variant="outline" size="sm" className="h-8 rounded-lg bg-white text-rose-600" disabled={tagItem.status !== "active"} onClick={() => onDisable(tagItem)}>
                    <XCircle className="size-3.5" />
                    禁用
                </Button>
            </div>
        </div>
    );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
    return (
        <div className="grid gap-2">
            <Label className="text-xs font-black text-slate-600">{label}</Label>
            {children}
        </div>
    );
}

function ColorPicker({ value, onChange }: { value: string; onChange: (value: string) => void }) {
    return (
        <div className="flex flex-wrap gap-2 rounded-xl border border-slate-200 bg-slate-50 p-2">
            {colors.map((color) => (
                <button
                    key={color}
                    type="button"
                    className={cn("size-7 rounded-full border-2 transition", value === color ? "border-slate-900" : "border-white")}
                    style={{ backgroundColor: color }}
                    onClick={() => onChange(color)}
                    title={color}
                />
            ))}
        </div>
    );
}

function EmptyState({ icon: Icon, text }: { icon: LucideIcon; text: string }) {
    return (
        <div className="flex h-full min-h-[260px] flex-col items-center justify-center gap-3 text-slate-500">
            <Icon className="size-7" />
            <div className="text-sm font-bold">{text}</div>
        </div>
    );
}

function normalizeCategories(categories: InsightTagCategoryRead[], tags: InsightTagRead[]) {
    const known = new Map(categories.map((item) => [item.category_code, item]));
    const generated: InsightTagCategoryRead[] = [...categories];
    const counts = new Map<string, number>();
    for (const tagItem of tags) {
        counts.set(tagItem.tag_type, (counts.get(tagItem.tag_type) ?? 0) + 1);
        if (!known.has(tagItem.tag_type)) {
            known.set(tagItem.tag_type, {
                id: -generated.length - 1,
                category_code: tagItem.tag_type,
                category_name: tagItem.tag_type,
                description: null,
                color: tagItem.color ?? "#64748b",
                sort_no: 999,
                status: "active",
                tag_count: 0,
                create_time: tagItem.create_time,
                update_time: tagItem.update_time,
            });
            generated.push(known.get(tagItem.tag_type)!);
        }
    }
    return generated
        .map((item) => ({ ...item, tag_count: counts.get(item.category_code) ?? item.tag_count ?? 0 }))
        .sort((a, b) => a.sort_no - b.sort_no || a.category_name.localeCompare(b.category_name, "zh-CN"));
}

function numberValue(value: string) {
    const parsed = Number.parseInt(value, 10);
    return Number.isFinite(parsed) ? parsed : 0;
}

function formatDateTime(value?: string | null) {
    if (!value) return "未知";
    return new Date(value).toLocaleString("zh-CN", { hour12: false });
}

function errorMessage(error: unknown, fallback: string) {
    if (error instanceof Error && error.message) return error.message;
    return fallback;
}
