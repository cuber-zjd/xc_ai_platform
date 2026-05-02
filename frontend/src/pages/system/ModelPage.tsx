/**
 * AI 模型配置管理页面
 *
 * 功能：模型配置 CRUD、熔断器状态查看、缓存管理
 */
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
    modelApi,
    type ModelConfig,
    type ModelCreatePayload,
    type ModelUpdatePayload,
    type CircuitBreakerStatus,
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
import {
    Loader2,
    MoreHorizontal,
    Pencil,
    Plus,
    Trash2,
    ShieldAlert,
    RefreshCw,
    Zap,
    Brain,
    Cpu,
    Sparkles,
    CircleOff,
    CheckCircle2,
    AlertTriangle,
} from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";

// ========== 常量映射 ==========

/** 模型级别映射 */
const LEVEL_MAP: Record<number, { label: string; color: string; icon: typeof Brain }> = {
    1: { label: "顶级", color: "bg-amber-500/10 text-amber-600 border-amber-500/20", icon: Sparkles },
    2: { label: "高级", color: "bg-violet-500/10 text-violet-600 border-violet-500/20", icon: Brain },
    3: { label: "标准", color: "bg-sky-500/10 text-sky-600 border-sky-500/20", icon: Cpu },
    4: { label: "轻量", color: "bg-zinc-500/10 text-zinc-600 border-zinc-500/20", icon: Zap },
};

/** 供应商映射 */
const PROVIDER_MAP: Record<string, string> = {
    volcengine: "火山引擎",
    openai: "OpenAI",
    zhipu: "智谱AI",
    deepseek: "DeepSeek",
    qwen: "通义千问",
    moonshot: "Moonshot",
};

/** 能力标签映射 */
const CAPABILITY_MAP: Record<string, string> = {
    "complex-reasoning": "复杂推理",
    general: "通用",
    fast: "快速",
    code: "代码",
};

/** 熔断器状态映射 */
const CIRCUIT_STATE_MAP: Record<string, { label: string; color: string; icon: typeof CheckCircle2 }> = {
    closed: { label: "正常", color: "text-emerald-600", icon: CheckCircle2 },
    open: { label: "熔断", color: "text-red-600", icon: CircleOff },
    half_open: { label: "半开", color: "text-amber-600", icon: AlertTriangle },
};

// ========== 主页面 ==========

export default function ModelPage() {
    const queryClient = useQueryClient();
    const [isCreateOpen, setIsCreateOpen] = useState(false);
    const [editingModel, setEditingModel] = useState<ModelConfig | null>(null);
    const [showCircuitBreakers, setShowCircuitBreakers] = useState(false);

    // 获取模型列表
    const { data: models, isLoading } = useQuery({
        queryKey: ["models"],
        queryFn: modelApi.getList,
    });

    // 获取熔断器状态
    const { data: circuitBreakers, refetch: refetchCB } = useQuery({
        queryKey: ["circuit-breakers"],
        queryFn: modelApi.getCircuitBreakers,
        enabled: showCircuitBreakers,
    });

    // 创建
    const createMutation = useMutation({
        mutationFn: modelApi.create,
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ["models"] });
            setIsCreateOpen(false);
            toast.success("模型配置创建成功");
        },
        onError: () => toast.error("创建失败"),
    });

    // 更新
    const updateMutation = useMutation({
        mutationFn: ({ id, data }: { id: number; data: ModelUpdatePayload }) =>
            modelApi.update(id, data),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ["models"] });
            setEditingModel(null);
            toast.success("模型配置更新成功");
        },
        onError: () => toast.error("更新失败"),
    });

    // 删除
    const deleteMutation = useMutation({
        mutationFn: modelApi.delete,
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ["models"] });
            toast.success("模型配置已删除");
        },
        onError: () => toast.error("删除失败"),
    });

    // 重置熔断器
    const resetCBMutation = useMutation({
        mutationFn: (name?: string) => modelApi.resetCircuitBreaker(name),
        onSuccess: () => {
            refetchCB();
            toast.success("熔断器已重置");
        },
    });

    // 清除缓存
    const cacheMutation = useMutation({
        mutationFn: modelApi.invalidateCache,
        onSuccess: () => toast.success("配置缓存已清除"),
    });

    const handleDelete = (id: number, name: string) => {
        if (confirm(`确定要删除模型「${name}」吗？`)) {
            deleteMutation.mutate(id);
        }
    };

    return (
        <div className="space-y-6">
            {/* 页头 */}
            <div className="flex items-center justify-between">
                <div>
                    <h2 className="text-2xl font-bold tracking-tight">模型管理</h2>
                    <p className="text-muted-foreground">
                        管理 AI 模型配置、查看熔断器状态。
                    </p>
                </div>
                <div className="flex items-center gap-2">
                    <Button
                        variant="outline"
                        size="sm"
                        onClick={() => cacheMutation.mutate()}
                        disabled={cacheMutation.isPending}
                    >
                        <RefreshCw className={cn("mr-2 h-4 w-4", cacheMutation.isPending && "animate-spin")} />
                        刷新缓存
                    </Button>
                    <Button
                        variant="outline"
                        size="sm"
                        onClick={() => {
                            setShowCircuitBreakers(!showCircuitBreakers);
                            if (!showCircuitBreakers) refetchCB();
                        }}
                    >
                        <ShieldAlert className="mr-2 h-4 w-4" />
                        熔断器状态
                    </Button>
                    <Button onClick={() => setIsCreateOpen(true)}>
                        <Plus className="mr-2 h-4 w-4" /> 添加模型
                    </Button>
                </div>
            </div>

            {/* 熔断器状态面板 */}
            {showCircuitBreakers && (
                <CircuitBreakerPanel
                    data={circuitBreakers}
                    onReset={(name) => resetCBMutation.mutate(name)}
                    onResetAll={() => resetCBMutation.mutate(undefined)}
                />
            )}

            {/* 模型列表表格 */}
            <div className="rounded-md border bg-card">
                <Table>
                    <TableHeader>
                        <TableRow>
                            <TableHead>模型名称</TableHead>
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
                                <TableCell colSpan={9} className="h-24 text-center">
                                    <Loader2 className="h-6 w-6 animate-spin mx-auto" />
                                </TableCell>
                            </TableRow>
                        ) : !models?.length ? (
                            <TableRow>
                                <TableCell colSpan={9} className="h-24 text-center text-muted-foreground">
                                    暂无模型配置，点击右上角「添加模型」创建
                                </TableCell>
                            </TableRow>
                        ) : (
                            models.map((model) => {
                                const levelInfo = LEVEL_MAP[model.model_level] || LEVEL_MAP[3];
                                const LevelIcon = levelInfo.icon;
                                return (
                                    <TableRow key={model.id}>
                                        <TableCell>
                                            <div className="flex flex-col">
                                                <span className="font-medium">{model.model_name}</span>
                                                <span className="text-xs text-muted-foreground truncate max-w-[200px]">
                                                    {model.model_code}
                                                </span>
                                            </div>
                                        </TableCell>
                                        <TableCell>
                                            <span className="text-sm">
                                                {PROVIDER_MAP[model.provider] || model.provider}
                                            </span>
                                        </TableCell>
                                        <TableCell>
                                            <Badge variant="outline" className={cn("gap-1", levelInfo.color)}>
                                                <LevelIcon className="h-3 w-3" />
                                                {levelInfo.label}
                                            </Badge>
                                        </TableCell>
                                        <TableCell>
                                            <span className="text-sm">
                                                {CAPABILITY_MAP[model.capability || ""] || model.capability || "-"}
                                            </span>
                                        </TableCell>
                                        <TableCell>
                                            <span className="text-xs text-muted-foreground uppercase">
                                                {model.model_type}
                                            </span>
                                        </TableCell>
                                        <TableCell>
                                            <span className="text-sm font-mono">{model.priority}</span>
                                        </TableCell>
                                        <TableCell>
                                            <span className="text-xs font-mono text-muted-foreground">
                                                {model.api_key_masked}
                                            </span>
                                        </TableCell>
                                        <TableCell>
                                            <div className="flex items-center gap-2">
                                                <span
                                                    className={cn(
                                                        "h-2 w-2 rounded-full",
                                                        model.is_enabled ? "bg-emerald-500" : "bg-zinc-400"
                                                    )}
                                                />
                                                <span className="text-sm text-muted-foreground">
                                                    {model.is_enabled ? "启用" : "禁用"}
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
                                                        <Pencil className="mr-2 h-4 w-4" /> 编辑
                                                    </DropdownMenuItem>
                                                    <DropdownMenuItem
                                                        className="text-red-600"
                                                        onClick={() => handleDelete(model.id, model.model_name)}
                                                    >
                                                        <Trash2 className="mr-2 h-4 w-4" /> 删除
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

            {/* 创建弹窗 */}
            <ModelDialog
                open={isCreateOpen}
                onOpenChange={setIsCreateOpen}
                onSubmit={(data) => createMutation.mutate(data as ModelCreatePayload)}
                isLoading={createMutation.isPending}
                mode="create"
            />

            {/* 编辑弹窗 */}
            {editingModel && (
                <ModelDialog
                    open={!!editingModel}
                    onOpenChange={(open) => !open && setEditingModel(null)}
                    onSubmit={(data) =>
                        updateMutation.mutate({ id: editingModel.id, data: data as ModelUpdatePayload })
                    }
                    initialData={editingModel}
                    isLoading={updateMutation.isPending}
                    mode="edit"
                />
            )}
        </div>
    );
}

// ========== 熔断器状态面板 ==========

function CircuitBreakerPanel({
    data,
    onReset,
    onResetAll,
}: {
    data?: CircuitBreakerStatus;
    onReset: (name: string) => void;
    onResetAll: () => void;
}) {
    const entries = data ? Object.entries(data) : [];

    return (
        <div className="rounded-lg border bg-card p-4 space-y-3">
            <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold flex items-center gap-2">
                    <ShieldAlert className="h-4 w-4" />
                    熔断器状态
                </h3>
                {entries.length > 0 && (
                    <Button variant="outline" size="sm" onClick={onResetAll}>
                        全部重置
                    </Button>
                )}
            </div>
            {entries.length === 0 ? (
                <p className="text-sm text-muted-foreground">暂无熔断器记录（模型未被调用过）</p>
            ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                    {entries.map(([name, info]) => {
                        const stateInfo = CIRCUIT_STATE_MAP[info.state] || CIRCUIT_STATE_MAP.closed;
                        const StateIcon = stateInfo.icon;
                        return (
                            <div
                                key={name}
                                className="flex items-center justify-between rounded-md border p-3 bg-background"
                            >
                                <div className="flex items-center gap-3">
                                    <StateIcon className={cn("h-5 w-5", stateInfo.color)} />
                                    <div>
                                        <p className="text-sm font-medium">{name}</p>
                                        <p className="text-xs text-muted-foreground">
                                            {stateInfo.label} · 失败 {info.failure_count} 次
                                        </p>
                                    </div>
                                </div>
                                {info.state !== "closed" && (
                                    <Button variant="ghost" size="sm" onClick={() => onReset(name)}>
                                        重置
                                    </Button>
                                )}
                            </div>
                        );
                    })}
                </div>
            )}
        </div>
    );
}

// ========== 模型编辑弹窗 ==========

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
    onSubmit: (data: ModelCreatePayload | ModelUpdatePayload) => void;
    initialData?: ModelConfig;
    isLoading: boolean;
    mode: "create" | "edit";
}) {
    const isEdit = mode === "edit";

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        const formData = new FormData(e.target as HTMLFormElement);
        const raw = Object.fromEntries(formData) as Record<string, string>;

        const data: Record<string, unknown> = {
            model_name: raw.model_name,
            model_code: raw.model_code,
            provider: raw.provider,
            base_url: raw.base_url,
            model_level: parseInt(raw.model_level) || 3,
            model_type: raw.model_type || "chat",
            capability: raw.capability || "general",
            max_tokens: parseInt(raw.max_tokens) || 4096,
            default_temperature: parseFloat(raw.default_temperature) || 0,
            priority: parseInt(raw.priority) || 100,
            is_enabled: raw.is_enabled === "true",
            comment: raw.comment || undefined,
        };

        // 创建时必须有 api_key；编辑时如果填了就更新
        if (!isEdit) {
            data.api_key = raw.api_key;
        } else if (raw.api_key) {
            data.api_key = raw.api_key;
        }

        onSubmit(data as ModelCreatePayload);
    };

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto">
                <DialogHeader>
                    <DialogTitle>{isEdit ? "编辑模型配置" : "添加模型配置"}</DialogTitle>
                    <DialogDescription>
                        {isEdit ? "修改模型的连接信息和调度参数。" : "添加一个新的 AI 模型到系统中。"}
                    </DialogDescription>
                </DialogHeader>
                <form onSubmit={handleSubmit} className="space-y-4">
                    <div className="grid gap-4 py-2">
                        {/* 基本信息 */}
                        <div className="grid grid-cols-2 gap-4">
                            <div className="space-y-2">
                                <Label htmlFor="model_name">模型名称 *</Label>
                                <Input
                                    id="model_name"
                                    name="model_name"
                                    placeholder="如 DeepSeek-V3"
                                    defaultValue={initialData?.model_name}
                                    required
                                />
                            </div>
                            <div className="space-y-2">
                                <Label htmlFor="model_code">模型代码 / 端点ID *</Label>
                                <Input
                                    id="model_code"
                                    name="model_code"
                                    placeholder="如 ep-xxx 或 gpt-4o"
                                    defaultValue={initialData?.model_code}
                                    required
                                />
                            </div>
                        </div>

                        {/* 供应商 + Base URL */}
                        <div className="grid grid-cols-2 gap-4">
                            <div className="space-y-2">
                                <Label htmlFor="provider">供应商 *</Label>
                                <Select name="provider" defaultValue={initialData?.provider || "volcengine"}>
                                    <SelectTrigger>
                                        <SelectValue placeholder="选择供应商" />
                                    </SelectTrigger>
                                    <SelectContent>
                                        <SelectItem value="volcengine">火山引擎</SelectItem>
                                        <SelectItem value="openai">OpenAI</SelectItem>
                                        <SelectItem value="zhipu">智谱AI</SelectItem>
                                        <SelectItem value="deepseek">DeepSeek</SelectItem>
                                        <SelectItem value="qwen">通义千问</SelectItem>
                                        <SelectItem value="moonshot">Moonshot</SelectItem>
                                    </SelectContent>
                                </Select>
                            </div>
                            <div className="space-y-2">
                                <Label htmlFor="base_url">API 地址 *</Label>
                                <Input
                                    id="base_url"
                                    name="base_url"
                                    placeholder="https://api.example.com/v1"
                                    defaultValue={initialData?.base_url}
                                    required
                                />
                            </div>
                        </div>

                        {/* API Key */}
                        <div className="space-y-2">
                            <Label htmlFor="api_key">
                                API Key {isEdit ? "（留空保持不变）" : "*"}
                            </Label>
                            <Input
                                id="api_key"
                                name="api_key"
                                type="password"
                                placeholder={isEdit ? "留空则保持原密钥" : "输入 API Key"}
                                required={!isEdit}
                            />
                        </div>

                        {/* 级别 + 能力 + 类型 */}
                        <div className="grid grid-cols-3 gap-4">
                            <div className="space-y-2">
                                <Label>模型级别</Label>
                                <Select
                                    name="model_level"
                                    defaultValue={String(initialData?.model_level || 3)}
                                >
                                    <SelectTrigger>
                                        <SelectValue />
                                    </SelectTrigger>
                                    <SelectContent>
                                        <SelectItem value="1">1 - 顶级</SelectItem>
                                        <SelectItem value="2">2 - 高级</SelectItem>
                                        <SelectItem value="3">3 - 标准</SelectItem>
                                        <SelectItem value="4">4 - 轻量</SelectItem>
                                    </SelectContent>
                                </Select>
                            </div>
                            <div className="space-y-2">
                                <Label>能力标签</Label>
                                <Select
                                    name="capability"
                                    defaultValue={initialData?.capability || "general"}
                                >
                                    <SelectTrigger>
                                        <SelectValue />
                                    </SelectTrigger>
                                    <SelectContent>
                                        <SelectItem value="general">通用</SelectItem>
                                        <SelectItem value="complex-reasoning">复杂推理</SelectItem>
                                        <SelectItem value="fast">快速</SelectItem>
                                        <SelectItem value="code">代码</SelectItem>
                                    </SelectContent>
                                </Select>
                            </div>
                            <div className="space-y-2">
                                <Label>模型类型</Label>
                                <Select
                                    name="model_type"
                                    defaultValue={initialData?.model_type || "chat"}
                                >
                                    <SelectTrigger>
                                        <SelectValue />
                                    </SelectTrigger>
                                    <SelectContent>
                                        <SelectItem value="chat">对话 (Chat)</SelectItem>
                                        <SelectItem value="embedding">向量 (Embedding)</SelectItem>
                                        <SelectItem value="vision">视觉 (Vision)</SelectItem>
                                        <SelectItem value="reranker">重排 (Reranker)</SelectItem>
                                    </SelectContent>
                                </Select>
                            </div>
                        </div>

                        {/* 参数行 */}
                        <div className="grid grid-cols-3 gap-4">
                            <div className="space-y-2">
                                <Label htmlFor="max_tokens">最大 Tokens</Label>
                                <Input
                                    id="max_tokens"
                                    name="max_tokens"
                                    type="number"
                                    defaultValue={initialData?.max_tokens || 4096}
                                />
                            </div>
                            <div className="space-y-2">
                                <Label htmlFor="default_temperature">默认温度</Label>
                                <Input
                                    id="default_temperature"
                                    name="default_temperature"
                                    type="number"
                                    step="0.1"
                                    min="0"
                                    max="2"
                                    defaultValue={initialData?.default_temperature ?? 0}
                                />
                            </div>
                            <div className="space-y-2">
                                <Label htmlFor="priority">优先级 (越小越优先)</Label>
                                <Input
                                    id="priority"
                                    name="priority"
                                    type="number"
                                    defaultValue={initialData?.priority || 100}
                                />
                            </div>
                        </div>

                        {/* 启用状态 + 备注 */}
                        <div className="grid grid-cols-2 gap-4">
                            <div className="space-y-2">
                                <Label>启用状态</Label>
                                <Select
                                    name="is_enabled"
                                    defaultValue={String(initialData?.is_enabled ?? true)}
                                >
                                    <SelectTrigger>
                                        <SelectValue />
                                    </SelectTrigger>
                                    <SelectContent>
                                        <SelectItem value="true">启用</SelectItem>
                                        <SelectItem value="false">禁用</SelectItem>
                                    </SelectContent>
                                </Select>
                            </div>
                            <div className="space-y-2">
                                <Label htmlFor="comment">备注</Label>
                                <Input
                                    id="comment"
                                    name="comment"
                                    placeholder="可选备注"
                                    defaultValue={initialData?.comment || ""}
                                />
                            </div>
                        </div>
                    </div>

                    <DialogFooter>
                        <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                            取消
                        </Button>
                        <Button type="submit" disabled={isLoading}>
                            {isLoading ? "保存中..." : "保存"}
                        </Button>
                    </DialogFooter>
                </form>
            </DialogContent>
        </Dialog>
    );
}
