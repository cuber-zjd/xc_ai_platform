import React, { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { 
    Plus, 
    Pencil, 
    FolderPlus, 
    Box, 
    LayoutGrid,
    Loader2
} from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from "@/components/ui/table";
import {
    Dialog,
    DialogContent,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { apiClient } from "@/api/client";

interface AgentGroup {
    id: number;
    name: string;
    description?: string;
    sort_order: number;
    status: number;
}

interface AgentApp {
    id: number;
    name: string;
    description?: string;
    icon?: string;
    route_path: string;
    group_id: number;
    status: number;
    sort_order: number;
}

export default function AgentManagerPage() {
    const queryClient = useQueryClient();
    const [activeTab, setActiveTab] = useState<'groups' | 'apps'>('groups');
    
    // Group State
    const [isGroupDialogOpen, setIsGroupDialogOpen] = useState(false);
    const [editingGroup, setEditingGroup] = useState<AgentGroup | null>(null);

    // App State
    const [isAppDialogOpen, setIsAppDialogOpen] = useState(false);
    const [editingApp, setEditingApp] = useState<AgentApp | null>(null);

    // --- Queries ---
    const { data: groups, isLoading: loadingGroups } = useQuery({
        queryKey: ['agent_groups'],
        queryFn: async () => apiClient.get("/agents/groups") as Promise<any>,
    });

    const { data: apps, isLoading: loadingApps } = useQuery({
        queryKey: ['agent_apps'],
        queryFn: async () => apiClient.get("/agents/apps") as Promise<any>,
    });

    // --- Transformations ---
    const getGroupName = (id: number) => groups?.find((g: any) => g.id === id)?.name || "未知分组";

    // --- Render ---
    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <div>
                    <h2 className="text-2xl font-bold tracking-tight">智能体管理</h2>
                    <p className="text-muted-foreground">定义系统中的智能体运行入口及分组组织结构。</p>
                </div>
                <div className="flex gap-2">
                    <Button variant={activeTab === 'groups' ? 'default' : 'outline'} onClick={() => setActiveTab('groups')}>
                        <LayoutGrid className="mr-2 h-4 w-4" /> 分组管理
                    </Button>
                    <Button variant={activeTab === 'apps' ? 'default' : 'outline'} onClick={() => setActiveTab('apps')}>
                        <Box className="mr-2 h-4 w-4" /> 应用管理
                    </Button>
                </div>
            </div>

            {activeTab === 'groups' ? (
                <div className="space-y-4">
                    <div className="flex justify-end">
                        <Button onClick={() => setIsGroupDialogOpen(true)}>
                            <FolderPlus className="mr-2 h-4 w-4" /> 新增分组
                        </Button>
                    </div>
                    <div className="rounded-md border bg-card">
                        <Table>
                            <TableHeader>
                                <TableRow>
                                    <TableHead>名称</TableHead>
                                    <TableHead>排序</TableHead>
                                    <TableHead>状态</TableHead>
                                    <TableHead className="text-right">操作</TableHead>
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {loadingGroups ? (
                                    <TableRow><TableCell colSpan={4} className="text-center py-10"><Loader2 className="animate-spin mx-auto" /></TableCell></TableRow>
                                ) : groups?.map((group: AgentGroup) => (
                                    <TableRow key={group.id}>
                                        <TableCell className="font-medium">{group.name}</TableCell>
                                        <TableCell>{group.sort_order}</TableCell>
                                        <TableCell>
                                            <Badge variant={group.status === 1 ? 'default' : 'secondary'}>{group.status === 1 ? '启用' : '禁用'}</Badge>
                                        </TableCell>
                                        <TableCell className="text-right">
                                            <Button variant="ghost" size="icon" onClick={() => { setEditingGroup(group); setIsGroupDialogOpen(true); }}>
                                                <Pencil className="h-4 w-4" />
                                            </Button>
                                        </TableCell>
                                    </TableRow>
                                ))}
                            </TableBody>
                        </Table>
                    </div>
                </div>
            ) : (
                <div className="space-y-4">
                    <div className="flex justify-end">
                        <Button onClick={() => setIsAppDialogOpen(true)}>
                            <Plus className="mr-2 h-4 w-4" /> 新增应用
                        </Button>
                    </div>
                    <div className="rounded-md border bg-card">
                        <Table>
                            <TableHeader>
                                <TableRow>
                                    <TableHead>应用名称</TableHead>
                                    <TableHead>所属分组</TableHead>
                                    <TableHead>路由路径</TableHead>
                                    <TableHead>状态</TableHead>
                                    <TableHead className="text-right">操作</TableHead>
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {loadingApps ? (
                                    <TableRow><TableCell colSpan={5} className="text-center py-10"><Loader2 className="animate-spin mx-auto" /></TableCell></TableRow>
                                ) : apps?.map((app: AgentApp) => (
                                    <TableRow key={app.id}>
                                        <TableCell className="font-medium">
                                            <div className="flex items-center gap-2">
                                                <div className="w-6 h-6 rounded bg-zinc-100 flex items-center justify-center text-[10px] text-zinc-500 overflow-hidden">
                                                    {app.icon?.startsWith('http') ? <img src={app.icon} alt={app.name} className="w-full h-full object-cover" /> : (app.icon || 'Bot')}
                                                </div>
                                                {app.name}
                                            </div>
                                        </TableCell>
                                        <TableCell>{getGroupName(app.group_id)}</TableCell>
                                        <TableCell><code className="text-xs">{app.route_path}</code></TableCell>
                                        <TableCell>
                                            <Badge variant={app.status === 1 ? 'default' : 'secondary'}>{app.status === 1 ? '启用' : '禁用'}</Badge>
                                        </TableCell>
                                        <TableCell className="text-right">
                                            <Button variant="ghost" size="icon" onClick={() => { setEditingApp(app); setIsAppDialogOpen(true); }}>
                                                <Pencil className="h-4 w-4" />
                                            </Button>
                                        </TableCell>
                                    </TableRow>
                                ))}
                            </TableBody>
                        </Table>
                    </div>
                </div>
            )}

            {/* Group Dialog */}
            <GroupDialog 
                open={isGroupDialogOpen}
                onOpenChange={(v: boolean) => { setIsGroupDialogOpen(v); if(!v) setEditingGroup(null); }}
                initialData={editingGroup}
                onSuccess={() => { queryClient.invalidateQueries({ queryKey: ['agent_groups'] }); setIsGroupDialogOpen(false); setEditingGroup(null); }}
            />

            {/* App Dialog */}
            <AppDialog
                open={isAppDialogOpen}
                onOpenChange={(v: boolean) => { setIsAppDialogOpen(v); if(!v) setEditingApp(null); }}
                initialData={editingApp}
                groups={groups || []}
                onSuccess={() => { queryClient.invalidateQueries({ queryKey: ['agent_apps'] }); setIsAppDialogOpen(false); setEditingApp(null); }}
            />
        </div>
    );
}

function GroupDialog({ open, onOpenChange, initialData, onSuccess }: any) {
    const isEdit = !!initialData;
    const mutation = useMutation({
        mutationFn: (data: any) => isEdit ? apiClient.put(`/agents/groups/${initialData.id}`, data) : apiClient.post("/agents/groups", data),
        onSuccess: () => { toast.success("保存成功"); onSuccess(); }
    });

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        const formData = new FormData(e.target as HTMLFormElement);
        const data: any = Object.fromEntries(formData);
        data.status = formData.get('status') === 'on' ? 1 : 0;
        data.sort_order = parseInt(data.sort_order as string) || 0;
        mutation.mutate(data);
    };

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent>
                <DialogHeader><DialogTitle>{isEdit ? '编辑分组' : '新增分组'}</DialogTitle></DialogHeader>
                <form onSubmit={handleSubmit} className="space-y-4">
                    <div className="space-y-2">
                        <Label>分组名称</Label>
                        <Input name="name" defaultValue={initialData?.name} required />
                    </div>
                    <div className="space-y-2">
                        <Label>排序</Label>
                        <Input name="sort_order" type="number" defaultValue={initialData?.sort_order || 0} />
                    </div>
                    <div className="flex items-center gap-2">
                        <input type="checkbox" id="group_status" name="status" defaultChecked={initialData ? initialData.status === 1 : true} />
                        <Label htmlFor="group_status">启用此分组</Label>
                    </div>
                    <DialogFooter>
                        <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>取消</Button>
                        <Button type="submit" disabled={mutation.isPending}>保存</Button>
                    </DialogFooter>
                </form>
            </DialogContent>
        </Dialog>
    );
}

function AppDialog({ open, onOpenChange, initialData, groups, onSuccess }: any) {
    const isEdit = !!initialData;
    const [selectedGroupId, setSelectedGroupId] = useState<string>(initialData?.group_id?.toString() || "");
    const [iconUrl, setIconUrl] = useState<string>(initialData?.icon || "");
    const [isUploading, setIsUploading] = useState(false);
    const fileInputRef = React.useRef<HTMLInputElement>(null);

    // 当 initialData 变化时同步状态（修复切换编辑对象时 state 不更新的问题）
    React.useEffect(() => {
        setSelectedGroupId(initialData?.group_id?.toString() || "");
        setIconUrl(initialData?.icon || "");
    }, [initialData]);

    const mutation = useMutation({
        mutationFn: (data: any) => isEdit ? apiClient.put(`/agents/apps/${initialData.id}`, data) : apiClient.post("/agents/apps", data),
        onSuccess: () => { toast.success("保存成功"); onSuccess(); }
    });

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        const formData = new FormData(e.target as HTMLFormElement);
        const data: any = Object.fromEntries(formData);
        data.group_id = parseInt(selectedGroupId);
        data.status = formData.get('status') === 'on' ? 1 : 0;
        data.sort_order = parseInt(data.sort_order as string) || 0;
        data.icon = iconUrl || "";
        mutation.mutate(data);
    };

    const handleIconUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (!file) return;
        setIsUploading(true);
        const uploadFormData = new FormData();
        uploadFormData.append("file", file);
        try {
            const res: any = await apiClient.post("/agents/upload_icon", uploadFormData, {
                headers: { "Content-Type": "multipart/form-data" }
            });
            setIconUrl(res);
            toast.success("图标上传成功");
        } catch (error) {
            toast.error("图标上传失败");
        } finally {
            setIsUploading(false);
            // 重置 file input，允许再次选择相同文件
            if (fileInputRef.current) fileInputRef.current.value = "";
        }
    };

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="max-w-md">
                <DialogHeader><DialogTitle>{isEdit ? '编辑智能体' : '新增智能体'}</DialogTitle></DialogHeader>
                {/* 文件选择器放在 form 外部，避免表单序列化干扰 */}
                <input type="file" ref={fileInputRef} className="hidden" accept="image/*" onChange={handleIconUpload} />
                <form onSubmit={handleSubmit} className="space-y-4">
                    <div className="space-y-2">
                        <Label>应用名称</Label>
                        <Input name="name" defaultValue={initialData?.name} required key={initialData?.id || 'new'} />
                    </div>
                    <div className="space-y-2">
                        <Label>图标</Label>
                        <div className="flex items-center gap-3">
                            {iconUrl && iconUrl.startsWith('http') ? (
                                <div className="w-12 h-12 rounded-lg overflow-hidden border shrink-0">
                                    <img src={iconUrl} alt="icon" className="w-full h-full object-cover" />
                                </div>
                            ) : (
                                <Input 
                                    value={iconUrl} 
                                    onChange={(e) => setIconUrl(e.target.value)} 
                                    placeholder="输入图标代码或上传图片" 
                                    className="flex-1"
                                />
                            )}
                            <Button type="button" variant="outline" size="sm" onClick={() => fileInputRef.current?.click()} disabled={isUploading}>
                                {isUploading ? <Loader2 className="h-4 w-4 animate-spin" /> : '上传图片'}
                            </Button>
                            {iconUrl && (
                                <Button type="button" variant="ghost" size="sm" onClick={() => setIconUrl('')}>清除</Button>
                            )}
                        </div>
                    </div>
                    <div className="space-y-2">
                        <Label>所属分组</Label>
                        <Select value={selectedGroupId} onValueChange={setSelectedGroupId}>
                            <SelectTrigger><SelectValue placeholder="选择所属分组" /></SelectTrigger>
                            <SelectContent>
                                {groups.map((g: any) => <SelectItem key={g.id} value={g.id.toString()}>{g.name}</SelectItem>)}
                            </SelectContent>
                        </Select>
                    </div>
                    <div className="space-y-2">
                        <Label>路由路径 (/chat, /contract, etc.)</Label>
                        <Input name="route_path" defaultValue={initialData?.route_path} required key={`route-${initialData?.id || 'new'}`} />
                    </div>
                    <div className="space-y-2">
                        <Label>简短描述</Label>
                        <Input name="description" defaultValue={initialData?.description} key={`desc-${initialData?.id || 'new'}`} />
                    </div>
                    <div className="grid grid-cols-2 gap-4">
                        <div className="space-y-2">
                            <Label>排序</Label>
                            <Input name="sort_order" type="number" defaultValue={initialData?.sort_order || 0} key={`sort-${initialData?.id || 'new'}`} />
                        </div>
                        <div className="flex items-center gap-2 pt-8">
                            <input type="checkbox" id="app_status" name="status" defaultChecked={initialData ? initialData.status === 1 : true} key={`status-${initialData?.id || 'new'}`} />
                            <Label htmlFor="app_status">启用此应用</Label>
                        </div>
                    </div>
                    <DialogFooter>
                        <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>取消</Button>
                        <Button type="submit" disabled={mutation.isPending || !selectedGroupId}>保存</Button>
                    </DialogFooter>
                </form>
            </DialogContent>
        </Dialog>
    );
}
