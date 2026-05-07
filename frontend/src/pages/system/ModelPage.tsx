import { useState, type FormEvent, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
    AlertTriangle,
    Brain,
    CheckCircle2,
    CircleOff,
    Cpu,
    Loader2,
    MoreHorizontal,
    Pencil,
    Plus,
    RefreshCw,
    ShieldAlert,
    Sparkles,
    Trash2,
    Zap,
} from "lucide-react";
import { toast } from "sonner";

import {
    modelApi,
    type CircuitBreakerStatus,
    type ModelConfig,
    type ModelCreatePayload,
    type ModelUpdatePayload,
} from "@/api/models";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog";
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuLabel,
    DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";

const LEVEL_MAP: Record<number, { label: string; color: string; icon: typeof Brain }> = {
    1: { label: "顶级", color: "bg-amber-500/10 text-amber-600 border-amber-500/20", icon: Sparkles },
    2: { label: "高级", color: "bg-sky-500/10 text-sky-600 border-sky-500/20", icon: Brain },
    3: { label: "标准", color: "bg-emerald-500/10 text-emerald-600 border-emerald-500/20", icon: Cpu },
    4: { label: "轻量", color: "bg-zinc-500/10 text-zinc-600 border-zinc-500/20", icon: Zap },
};

const PROVIDER_MAP: Record<string, string> = {
    volcengine: "火山引擎",
    openai: "OpenAI",
    zhipu: "智谱 AI",
    deepseek: "DeepSeek",
    qwen: "通义千问",
    moonshot: "Moonshot",
};

const CAPABILITY_MAP: Record<string, string> = {
    "complex-reasoning": "复杂推理",
    general: "通用",
    fast: "快速响应",
    code: "代码生成",
};

const MODEL_TYPE_OPTIONS = [
    { value: "chat", label: "对话模型" },
    { value: "embedding", label: "向量模型" },
    { value: "rerank", label: "重排模型" },
];

const PROVIDER_OPTIONS = [
    { value: "volcengine", label: "火山引擎" },
    { value: "openai", label: "OpenAI" },
    { value: "zhipu", label: "智谱 AI" },
    { value: "deepseek", label: "DeepSeek" },
    { value: "qwen", label: "通义千问" },
    { value: "moonshot", label: "Moonshot" },
];

const CAPABILITY_OPTIONS = [
    { value: "general", label: "通用" },
    { value: "complex-reasoning", label: "复杂推理" },
    { value: "fast", label: "快速响应" },
    { value: "code", label: "代码生成" },
];

const CIRCUIT_STATE_MAP: Record<string, { label: string; color: string; icon: typeof CheckCircle2 }> = {
    closed: { label: "正常", color: "text-emerald-600", icon: CheckCircle2 },
    open: { label: "熔断", color: "text-red-600", icon: CircleOff },
    half_open: { label: "半开", color: "text-amber-600", icon: AlertTriangle },
};

interface ModelFormState {
    model_name: string;
    model_code: string;
    provider: string;
    api_key: string;
    base_url: string;
    model_level: string;
    model_type: string;
    capability: string;
    max_tokens: string;
    default_temperature: string;
    priority: string;
    is_enabled: string;
    status: string;
    comment: string;
}

const DEFAULT_FORM_STATE: ModelFormState = {
    model_name: "",
    model_code: "",
    provider: "openai",
    api_key: "",
    base_url: "",
    model_level: "3",
    model_type: "chat",
    capability: "general",
    max_tokens: "4096",
    default_temperature: "0",
    priority: "100",
    is_enabled: "true",
    status: "1",
    comment: "",
};

export default function ModelPage() {
    const queryClient = useQueryClient();
    const [isCreateOpen, setIsCreateOpen] = useState(false);
    const [editingModel, setEditingModel] = useState<ModelConfig | null>(null);
    const [showCircuitBreakers, setShowCircuitBreakers] = useState(false);

    const { data: models, isLoading } = useQuery({
        queryKey: ["models"],
        queryFn: modelApi.getList,
    });

    const {
        data: circuitBreakers,
        isFetching: isCircuitLoading,
        refetch: refetchCircuitBreakers,
    } = useQuery({
        queryKey: ["circuit-breakers"],
        queryFn: modelApi.getCircuitBreakers,
        enabled: showCircuitBreakers,
    });

    const createMutation = useMutation({
        mutationFn: modelApi.create,
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ["models"] });
            setIsCreateOpen(false);
            toast.success("模型配置创建成功");
        },
        onError: () => toast.error("模型配置创建失败"),
    });

    const updateMutation = useMutation({
        mutationFn: ({ id, data }: { id: number; data: ModelUpdatePayload }) => modelApi.update(id, data),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ["models"] });
            setEditingModel(null);
            toast.success("模型配置更新成功");
        },
        onError: () => toast.error("模型配置更新失败"),
    });

    const deleteMutation = useMutation({
        mutationFn: modelApi.delete,
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ["models"] });
            toast.success("模型配置已删除");
        },
        onError: () => toast.error("模型配置删除失败"),
    });

    const resetCircuitMutation = useMutation({
        mutationFn: (modelName?: string) => modelApi.resetCircuitBreaker(modelName),
        onSuccess: () => {
            refetchCircuitBreakers();
            toast.success("熔断器已重置");
        },
        onError: () => toast.error("熔断器重置失败"),
    });

    const clearCacheMutation = useMutation({
        mutationFn: modelApi.invalidateCache,
        onSuccess: () => toast.success("模型缓存已清除"),
        onError: () => toast.error("模型缓存清除失败"),
    });

    const handleDelete = (id: number, name: string) => {
        if (confirm(`确定要删除模型“${name}”吗？`)) {
            deleteMutation.mutate(id);
        }
    };

    return (
        <div className="space-y-6">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                <div>
                    <h2 className="text-2xl font-bold tracking-tight">模型管理</h2>
                    <p className="text-muted-foreground">
                        统一维护 AI 模型配置，并查看熔断器和缓存状态。
                    </p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                    <Button
                        variant="outline"
                        size="sm"
                        onClick={() => clearCacheMutation.mutate()}
                        disabled={clearCacheMutation.isPending}
                    >
                        <RefreshCw className={cn("mr-2 h-4 w-4", clearCacheMutation.isPending && "animate-spin")} />
                        清理缓存
                    </Button>
                    <Button
                        variant="outline"
                        size="sm"
                        onClick={() => {
                            const next = !showCircuitBreakers;
                            setShowCircuitBreakers(next);
                            if (next) {
                                refetchCircuitBreakers();
                            }
                        }}
                    >
                        <ShieldAlert className="mr-2 h-4 w-4" />
                        {showCircuitBreakers ? "收起熔断器" : "查看熔断器"}
                    </Button>
                    <Button onClick={() => setIsCreateOpen(true)}>
                        <Plus className="mr-2 h-4 w-4" />
                        新增模型
                    </Button>
                </div>
            </div>

            {showCircuitBreakers && (
                <CircuitBreakerPanel
                    data={circuitBreakers}
                    isLoading={isCircuitLoading}
                    onRefresh={() => refetchCircuitBreakers()}
                    onReset={(name) => resetCircuitMutation.mutate(name)}
                    onResetAll={() => resetCircuitMutation.mutate(undefined)}
                    resetPending={resetCircuitMutation.isPending}
                />
            )}

            <div className="rounded-2xl border bg-card/80 backdrop-blur-sm">
                <Table>
                    <TableHeader>
                        <TableRow>
                            <TableHead>模型</TableHead>
                            <TableHead>供应商</TableHead>
                            <TableHead>级别</TableHead>
                            <TableHead>能力</TableHead>
                            <TableHead>类型</TableHead>
                            <TableHead>优先级</TableHead>
                            <TableHead>API Key</TableHead>
                            <TableHead>状态</TableHead>
                            <TableHead className="text-right">操作</TableHead>
                        </TableRow>
                    </TableHeader>
                    <TableBody>
                        {isLoading ? (
                            <TableRow>
                                <TableCell colSpan={9} className="h-28 text-center">
                                    <Loader2 className="mx-auto h-6 w-6 animate-spin" />
                                </TableCell>
                            </TableRow>
                        ) : !models?.length ? (
                            <TableRow>
                                <TableCell colSpan={9} className="h-28 text-center text-muted-foreground">
                                    还没有模型配置，点击右上角“新增模型”开始创建。
                                </TableCell>
                            </TableRow>
                        ) : (
                            models.map((model) => {
                                const levelInfo = LEVEL_MAP[model.model_level] ?? LEVEL_MAP[3];
                                const LevelIcon = levelInfo.icon;
                                return (
                                    <TableRow key={model.id}>
                                        <TableCell>
                                            <div className="flex flex-col gap-1">
                                                <span className="font-medium">{model.model_name}</span>
                                                <span className="max-w-[260px] truncate text-xs text-muted-foreground">
                                                    {model.model_code}
                                                </span>
                                            </div>
                                        </TableCell>
                                        <TableCell>{PROVIDER_MAP[model.provider] ?? model.provider}</TableCell>
                                        <TableCell>
                                            <Badge variant="outline" className={cn("gap-1 border", levelInfo.color)}>
                                                <LevelIcon className="h-3.5 w-3.5" />
                                                {levelInfo.label}
                                            </Badge>
                                        </TableCell>
                                        <TableCell>{CAPABILITY_MAP[model.capability ?? "general"] ?? (model.capability || "-")}</TableCell>
                                        <TableCell>{MODEL_TYPE_OPTIONS.find((item) => item.value === model.model_type)?.label ?? model.model_type}</TableCell>
                                        <TableCell>{model.priority}</TableCell>
                                        <TableCell>
                                            <code className="rounded bg-zinc-100 px-2 py-1 text-xs dark:bg-zinc-800">
                                                {model.api_key_masked}
                                            </code>
                                        </TableCell>
                                        <TableCell>
                                            <div className="flex items-center gap-2">
                                                <span
                                                    className={cn(
                                                        "h-2 w-2 rounded-full",
                                                        model.is_enabled && model.status === 1 ? "bg-emerald-500" : "bg-zinc-400"
                                                    )}
                                                />
                                                <span className="text-sm text-muted-foreground">
                                                    {model.is_enabled && model.status === 1 ? "启用中" : "已停用"}
                                                </span>
                                            </div>
                                        </TableCell>
                                        <TableCell className="text-right">
                                            <DropdownMenu>
                                                <DropdownMenuTrigger asChild>
                                                    <Button variant="ghost" size="icon">
                                                        <MoreHorizontal className="h-4 w-4" />
                                                    </Button>
                                                </DropdownMenuTrigger>
                                                <DropdownMenuContent align="end">
                                                    <DropdownMenuLabel>操作</DropdownMenuLabel>
                                                    <DropdownMenuItem onClick={() => setEditingModel(model)}>
                                                        <Pencil className="mr-2 h-4 w-4" />
                                                        编辑
                                                    </DropdownMenuItem>
                                                    <DropdownMenuItem
                                                        className="text-red-600"
                                                        onClick={() => handleDelete(model.id, model.model_name)}
                                                    >
                                                        <Trash2 className="mr-2 h-4 w-4" />
                                                        删除
                                                    </DropdownMenuItem>
                                                </DropdownMenuContent>
                                            </DropdownMenu>
                                        </TableCell>
                                    </TableRow>
                                );
                            })
                        )}
                    </TableBody>
                </Table>
            </div>

            <ModelDialog
                open={isCreateOpen}
                onOpenChange={setIsCreateOpen}
                onSubmit={(data) => createMutation.mutate(data as ModelCreatePayload)}
                isLoading={createMutation.isPending}
                mode="create"
            />

            {editingModel && (
                <ModelDialog
                    open={Boolean(editingModel)}
                    onOpenChange={(open) => {
                        if (!open) {
                            setEditingModel(null);
                        }
                    }}
                    onSubmit={(data) => updateMutation.mutate({ id: editingModel.id, data: data as ModelUpdatePayload })}
                    initialData={editingModel}
                    isLoading={updateMutation.isPending}
                    mode="edit"
                />
            )}
        </div>
    );
}

function CircuitBreakerPanel({
    data,
    isLoading,
    onRefresh,
    onReset,
    onResetAll,
    resetPending,
}: {
    data?: CircuitBreakerStatus;
    isLoading: boolean;
    onRefresh: () => void;
    onReset: (name: string) => void;
    onResetAll: () => void;
    resetPending: boolean;
}) {
    const items = Object.entries(data ?? {});

    return (
        <div className="rounded-2xl border bg-card/80 p-4 backdrop-blur-sm">
            <div className="mb-4 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                <div>
                    <h3 className="text-base font-semibold">熔断器状态</h3>
                    <p className="text-sm text-muted-foreground">
                        用于观察模型调用异常后的保护状态。
                    </p>
                </div>
                <div className="flex flex-wrap gap-2">
                    <Button variant="outline" size="sm" onClick={onRefresh} disabled={isLoading}>
                        <RefreshCw className={cn("mr-2 h-4 w-4", isLoading && "animate-spin")} />
                        刷新
                    </Button>
                    <Button size="sm" onClick={onResetAll} disabled={resetPending}>
                        全部重置
                    </Button>
                </div>
            </div>

            {isLoading ? (
                <div className="flex h-24 items-center justify-center">
                    <Loader2 className="h-6 w-6 animate-spin" />
                </div>
            ) : items.length === 0 ? (
                <div className="rounded-xl border border-dashed px-4 py-8 text-center text-sm text-muted-foreground">
                    当前没有可展示的熔断器状态。
                </div>
            ) : (
                <div className="grid gap-3 md:grid-cols-2">
                    {items.map(([name, status]) => {
                        const stateInfo = CIRCUIT_STATE_MAP[status.state] ?? CIRCUIT_STATE_MAP.closed;
                        const StateIcon = stateInfo.icon;
                        return (
                            <div key={name} className="rounded-xl border bg-background/60 p-4">
                                <div className="flex items-start justify-between gap-3">
                                    <div className="min-w-0">
                                        <div className="truncate font-medium">{name}</div>
                                        <div className="mt-1 flex items-center gap-2 text-sm text-muted-foreground">
                                            <StateIcon className={cn("h-4 w-4", stateInfo.color)} />
                                            <span className={stateInfo.color}>{stateInfo.label}</span>
                                        </div>
                                    </div>
                                    <Button variant="ghost" size="sm" onClick={() => onReset(name)} disabled={resetPending}>
                                        重置
                                    </Button>
                                </div>
                                <div className="mt-4 grid grid-cols-2 gap-3 text-sm">
                                    <div className="rounded-lg bg-muted/50 px-3 py-2">
                                        <div className="text-muted-foreground">失败次数</div>
                                        <div className="mt-1 font-medium">{status.failure_count}</div>
                                    </div>
                                    <div className="rounded-lg bg-muted/50 px-3 py-2">
                                        <div className="text-muted-foreground">是否可用</div>
                                        <div className="mt-1 font-medium">{status.is_available ? "可用" : "不可用"}</div>
                                    </div>
                                </div>
                            </div>
                        );
                    })}
                </div>
            )}
        </div>
    );
}

function ModelDialog({
    open,
    onOpenChange,
    onSubmit,
    initialData,
    isLoading,
    mode,
}: {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    onSubmit: (data: ModelCreatePayload | ModelUpdatePayload) => void | Promise<void>;
    initialData?: ModelConfig;
    isLoading: boolean;
    mode: "create" | "edit";
}) {
    const isEdit = mode === "edit";
    const initialState = initialData ? mapModelToFormState(initialData) : DEFAULT_FORM_STATE;
    const [formState, setFormState] = useState<ModelFormState>(initialState);

    const handleOpenChange = (nextOpen: boolean) => {
        if (nextOpen) {
            setFormState(initialData ? mapModelToFormState(initialData) : DEFAULT_FORM_STATE);
        }
        onOpenChange(nextOpen);
    };

    const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
        event.preventDefault();
        const payload = buildPayload(formState, isEdit);
        onSubmit(payload);
    };

    return (
        <Dialog open={open} onOpenChange={handleOpenChange}>
            <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-3xl">
                <DialogHeader>
                    <DialogTitle>{isEdit ? "编辑模型" : "新增模型"}</DialogTitle>
                    <DialogDescription>
                        {isEdit ? "更新模型配置参数和启用状态。" : "添加一个新的模型配置到系统中。"}
                    </DialogDescription>
                </DialogHeader>

                <form onSubmit={handleSubmit} className="space-y-6">
                    <div className="grid gap-4 md:grid-cols-2">
                        <Field label="模型名称" htmlFor="model_name">
                            <Input
                                id="model_name"
                                value={formState.model_name}
                                onChange={(event) => setFormState((prev) => ({ ...prev, model_name: event.target.value }))}
                                required
                            />
                        </Field>

                        <Field label="模型编码" htmlFor="model_code">
                            <Input
                                id="model_code"
                                value={formState.model_code}
                                onChange={(event) => setFormState((prev) => ({ ...prev, model_code: event.target.value }))}
                                required
                            />
                        </Field>

                        <Field label="供应商" htmlFor="provider">
                            <Select
                                value={formState.provider}
                                onValueChange={(value) => setFormState((prev) => ({ ...prev, provider: value }))}
                            >
                                <SelectTrigger id="provider">
                                    <SelectValue placeholder="请选择供应商" />
                                </SelectTrigger>
                                <SelectContent>
                                    {PROVIDER_OPTIONS.map((item) => (
                                        <SelectItem key={item.value} value={item.value}>
                                            {item.label}
                                        </SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        </Field>

                        <Field label="接口地址" htmlFor="base_url">
                            <Input
                                id="base_url"
                                value={formState.base_url}
                                onChange={(event) => setFormState((prev) => ({ ...prev, base_url: event.target.value }))}
                                placeholder="https://api.example.com/v1"
                                required
                            />
                        </Field>

                        <Field label={isEdit ? "API Key（留空则不修改）" : "API Key"} htmlFor="api_key">
                            <Input
                                id="api_key"
                                type="password"
                                value={formState.api_key}
                                onChange={(event) => setFormState((prev) => ({ ...prev, api_key: event.target.value }))}
                                required={!isEdit}
                            />
                        </Field>

                        <Field label="模型类型" htmlFor="model_type">
                            <Select
                                value={formState.model_type}
                                onValueChange={(value) => setFormState((prev) => ({ ...prev, model_type: value }))}
                            >
                                <SelectTrigger id="model_type">
                                    <SelectValue placeholder="请选择模型类型" />
                                </SelectTrigger>
                                <SelectContent>
                                    {MODEL_TYPE_OPTIONS.map((item) => (
                                        <SelectItem key={item.value} value={item.value}>
                                            {item.label}
                                        </SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        </Field>

                        <Field label="模型级别" htmlFor="model_level">
                            <Select
                                value={formState.model_level}
                                onValueChange={(value) => setFormState((prev) => ({ ...prev, model_level: value }))}
                            >
                                <SelectTrigger id="model_level">
                                    <SelectValue placeholder="请选择模型级别" />
                                </SelectTrigger>
                                <SelectContent>
                                    {Object.entries(LEVEL_MAP).map(([value, info]) => (
                                        <SelectItem key={value} value={value}>
                                            {info.label}
                                        </SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        </Field>

                        <Field label="能力标签" htmlFor="capability">
                            <Select
                                value={formState.capability}
                                onValueChange={(value) => setFormState((prev) => ({ ...prev, capability: value }))}
                            >
                                <SelectTrigger id="capability">
                                    <SelectValue placeholder="请选择能力标签" />
                                </SelectTrigger>
                                <SelectContent>
                                    {CAPABILITY_OPTIONS.map((item) => (
                                        <SelectItem key={item.value} value={item.value}>
                                            {item.label}
                                        </SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        </Field>

                        <Field label="最大 Token" htmlFor="max_tokens">
                            <Input
                                id="max_tokens"
                                type="number"
                                min="1"
                                value={formState.max_tokens}
                                onChange={(event) => setFormState((prev) => ({ ...prev, max_tokens: event.target.value }))}
                            />
                        </Field>

                        <Field label="温度" htmlFor="default_temperature">
                            <Input
                                id="default_temperature"
                                type="number"
                                min="0"
                                max="2"
                                step="0.1"
                                value={formState.default_temperature}
                                onChange={(event) => setFormState((prev) => ({ ...prev, default_temperature: event.target.value }))}
                            />
                        </Field>

                        <Field label="优先级" htmlFor="priority">
                            <Input
                                id="priority"
                                type="number"
                                value={formState.priority}
                                onChange={(event) => setFormState((prev) => ({ ...prev, priority: event.target.value }))}
                            />
                        </Field>

                        <Field label="启用状态" htmlFor="is_enabled">
                            <Select
                                value={formState.is_enabled}
                                onValueChange={(value) => setFormState((prev) => ({ ...prev, is_enabled: value }))}
                            >
                                <SelectTrigger id="is_enabled">
                                    <SelectValue placeholder="请选择启用状态" />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="true">启用</SelectItem>
                                    <SelectItem value="false">停用</SelectItem>
                                </SelectContent>
                            </Select>
                        </Field>

                        <Field label="记录状态" htmlFor="status">
                            <Select
                                value={formState.status}
                                onValueChange={(value) => setFormState((prev) => ({ ...prev, status: value }))}
                            >
                                <SelectTrigger id="status">
                                    <SelectValue placeholder="请选择记录状态" />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="1">正常</SelectItem>
                                    <SelectItem value="0">停用</SelectItem>
                                </SelectContent>
                            </Select>
                        </Field>
                    </div>

                    <Field label="备注" htmlFor="comment">
                        <textarea
                            id="comment"
                            value={formState.comment}
                            onChange={(event) => setFormState((prev) => ({ ...prev, comment: event.target.value }))}
                            rows={4}
                            className="flex min-h-[96px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm outline-none ring-offset-background placeholder:text-muted-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                            placeholder="可填写用途、适用场景或接入说明"
                        />
                    </Field>

                    <DialogFooter>
                        <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                            取消
                        </Button>
                        <Button type="submit" disabled={isLoading}>
                            {isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                            {isEdit ? "保存修改" : "创建模型"}
                        </Button>
                    </DialogFooter>
                </form>
            </DialogContent>
        </Dialog>
    );
}

function Field({
    label,
    htmlFor,
    children,
}: {
    label: string;
    htmlFor: string;
    children: ReactNode;
}) {
    return (
        <div className="space-y-2">
            <Label htmlFor={htmlFor}>{label}</Label>
            {children}
        </div>
    );
}

function mapModelToFormState(model: ModelConfig): ModelFormState {
    return {
        model_name: model.model_name,
        model_code: model.model_code,
        provider: model.provider,
        api_key: "",
        base_url: model.base_url,
        model_level: String(model.model_level),
        model_type: model.model_type,
        capability: model.capability ?? "general",
        max_tokens: model.max_tokens ? String(model.max_tokens) : "",
        default_temperature: String(model.default_temperature ?? 0),
        priority: String(model.priority),
        is_enabled: String(model.is_enabled),
        status: String(model.status),
        comment: model.comment ?? "",
    };
}

function buildPayload(formState: ModelFormState, isEdit: boolean): ModelCreatePayload | ModelUpdatePayload {
    const payload: ModelCreatePayload | ModelUpdatePayload = {
        model_name: formState.model_name.trim(),
        model_code: formState.model_code.trim(),
        provider: formState.provider,
        base_url: formState.base_url.trim(),
        model_level: Number(formState.model_level),
        model_type: formState.model_type,
        capability: formState.capability,
        max_tokens: formState.max_tokens ? Number(formState.max_tokens) : undefined,
        default_temperature: formState.default_temperature ? Number(formState.default_temperature) : 0,
        priority: formState.priority ? Number(formState.priority) : 100,
        is_enabled: formState.is_enabled === "true",
        status: Number(formState.status),
        comment: formState.comment.trim() || undefined,
    };

    if (!isEdit || formState.api_key.trim()) {
        payload.api_key = formState.api_key.trim();
    }

    return payload;
}
