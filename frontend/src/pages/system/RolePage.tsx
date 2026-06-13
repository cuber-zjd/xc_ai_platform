import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
    Plus,
    Pencil,
    Trash2,
    Shield,
    UserPlus,
    Key,
    Loader2,
    MoreHorizontal,
    Check,
    Users,
    Building2,
    ChevronRight,
    ChevronDown,
    Search,
    X
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
import { ScrollArea } from "@/components/ui/scroll-area";
import { apiClient } from "@/api/client";
import { cn } from "@/lib/utils";

interface Role {
    id: number;
    name: string;
    code: string;
    status: number;
    order: number;
}

interface User {
    id: number;
    username: string;
    full_name: string;
}

interface AgentApp {
    id: number;
    name: string;
    icon?: string;
    group_id: number;
}

interface AgentGroup {
    id: number;
    name: string;
    apps?: AgentApp[];
}

interface DeptNode {
    id: string;
    name: string;
    parent_id?: string;
    node_type?: string; // "company" | "dept"
    children?: DeptNode[];
}

function DeptTree({ nodes, selectedId, onSelect, level = 0 }: { nodes: DeptNode[], selectedId: string | null, onSelect: (id: string) => void, level?: number }) {
    return (
        <div className="space-y-1">
            {nodes.map(node => (
                <DeptTreeItem key={node.id} node={node} selectedId={selectedId} onSelect={onSelect} level={level} />
            ))}
        </div>
    );
}

function DeptTreeItem({ node, selectedId, onSelect, level }: { node: DeptNode, selectedId: string | null, onSelect: (id: string) => void, level: number }) {
    const [expanded, setExpanded] = useState(level < 2);
    const hasChildren = node.children && node.children.length > 0;
    const isCompany = node.node_type === "company";

    return (
        <div>
            <div
                className={cn(
                    "flex items-center gap-1.5 py-1.5 px-2 rounded-lg cursor-pointer text-sm transition-colors",
                    selectedId === node.id ? "bg-zinc-100 font-medium text-zinc-900" : "hover:bg-zinc-50 text-zinc-600",
                    isCompany && "font-medium"
                )}
                style={{ paddingLeft: `${level * 16 + 8}px` }}
                onClick={() => onSelect(node.id)}
            >
                <div
                    className="w-4 h-4 flex items-center justify-center shrink-0"
                    onClick={(e) => {
                        if (hasChildren) {
                            e.stopPropagation();
                            setExpanded(!expanded);
                        }
                    }}
                >
                    {hasChildren && (expanded ? <ChevronDown size={14} className="text-zinc-400" /> : <ChevronRight size={14} className="text-zinc-400" />)}
                </div>
                {isCompany
                    ? <Building2 size={14} className="text-blue-500 shrink-0" />
                    : <Users size={14} className="text-zinc-400 shrink-0" />
                }
                <span className="truncate">{node.name}</span>
            </div>
            {hasChildren && expanded && (
                <div className="mt-0.5">
                    <DeptTree nodes={node.children!} selectedId={selectedId} onSelect={onSelect} level={level + 1} />
                </div>
            )}
        </div>
    );
}

export default function RolePage() {
    const queryClient = useQueryClient();
    const [isCreateOpen, setIsCreateOpen] = useState(false);
    const [editingRole, setEditingRole] = useState<Role | null>(null);
    const [assigningUserRole, setAssigningUserRole] = useState<Role | null>(null);
    const [assigningAgentRole, setAssigningAgentRole] = useState<Role | null>(null);

    const { data: rolesResult, isLoading } = useQuery({
        queryKey: ['roles'],
        queryFn: async () => apiClient.get("/roles") as Promise<any>,
    });

    const createMutation = useMutation({
        mutationFn: (data: any) => apiClient.post("/roles", data),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['roles'] });
            setIsCreateOpen(false);
            toast.success("角色创建成功");
        }
    });

    const updateMutation = useMutation({
        mutationFn: ({ id, data }: { id: number; data: any }) => apiClient.put(`/roles/${id}`, data),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['roles'] });
            setEditingRole(null);
            toast.success("角色更新成功");
        }
    });

    const deleteMutation = useMutation({
        mutationFn: (id: number) => apiClient.delete(`/roles/${id}`),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['roles'] });
            toast.success("角色删除成功");
        }
    });

    const handleDelete = (id: number) => {
        if (confirm("确定要删除该角色吗？")) {
            deleteMutation.mutate(id);
        }
    };

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <div>
                    <h2 className="text-2xl font-bold tracking-tight">角色管理</h2>
                    <p className="text-muted-foreground">
                        配置系统角色及其关联的智能体使用权限。
                    </p>
                </div>
                <Button onClick={() => setIsCreateOpen(true)}>
                    <Plus className="mr-2 h-4 w-4" /> 添加角色
                </Button>
            </div>

            <div className="rounded-md border bg-card">
                <Table>
                    <TableHeader>
                        <TableRow>
                            <TableHead>角色名称</TableHead>
                            <TableHead>角色编码</TableHead>
                            <TableHead>状态</TableHead>
                            <TableHead>排序</TableHead>
                            <TableHead className="text-right">操作</TableHead>
                        </TableRow>
                    </TableHeader>
                    <TableBody>
                        {isLoading ? (
                            <TableRow>
                                <TableCell colSpan={5} className="h-24 text-center">
                                    <Loader2 className="h-6 w-6 animate-spin mx-auto" />
                                </TableCell>
                            </TableRow>
                        ) : rolesResult?.items?.map((role: Role) => (
                            <TableRow key={role.id}>
                                <TableCell className="font-medium">
                                    <div className="flex items-center gap-2">
                                        <Shield size={16} className="text-zinc-400" />
                                        {role.name}
                                    </div>
                                </TableCell>
                                <TableCell>
                                    <code className="text-xs bg-zinc-100 dark:bg-zinc-800 px-1.5 py-0.5 rounded">
                                        {role.code}
                                    </code>
                                </TableCell>
                                <TableCell>
                                    <Badge variant={role.status === 1 ? 'default' : 'secondary'}>
                                        {role.status === 1 ? '启用' : '禁用'}
                                    </Badge>
                                </TableCell>
                                <TableCell>{role.order}</TableCell>
                                <TableCell className="text-right">
                                    <DropdownMenu>
                                        <DropdownMenuTrigger asChild>
                                            <Button variant="ghost" size="icon">
                                                <MoreHorizontal className="h-4 w-4" />
                                            </Button>
                                        </DropdownMenuTrigger>
                                        <DropdownMenuContent align="end">
                                            <DropdownMenuLabel>管理操作</DropdownMenuLabel>
                                            <DropdownMenuItem onClick={() => setEditingRole(role)}>
                                                <Pencil className="mr-2 h-4 w-4" /> 编辑基本信息
                                            </DropdownMenuItem>
                                            <DropdownMenuItem onClick={() => setAssigningUserRole(role)}>
                                                <UserPlus className="mr-2 h-4 w-4" /> 分配用户成员
                                            </DropdownMenuItem>
                                            <DropdownMenuItem onClick={() => setAssigningAgentRole(role)}>
                                                <Key className="mr-2 h-4 w-4" /> 智能体授权
                                            </DropdownMenuItem>
                                            <DropdownMenuItem className="text-red-600" onClick={() => handleDelete(role.id)}>
                                                <Trash2 className="mr-2 h-4 w-4" /> 删除角色
                                            </DropdownMenuItem>
                                        </DropdownMenuContent>
                                    </DropdownMenu>
                                </TableCell>
                            </TableRow>
                        ))}
                    </TableBody>
                </Table>
            </div>

            {/* Role Dialog */}
            <RoleDialog
                open={isCreateOpen || !!editingRole}
                onOpenChange={(open: boolean) => {
                    if (!open) {
                        setIsCreateOpen(false);
                        setEditingRole(null);
                    }
                }}
                onSubmit={(data: any) => {
                    if (editingRole) {
                        updateMutation.mutate({ id: editingRole.id, data });
                    } else {
                        createMutation.mutate(data);
                    }
                }}
                initialData={editingRole}
                isLoading={createMutation.isPending || updateMutation.isPending}
            />

            {/* User Assignment Dialog */}
            {assigningUserRole && (
                <UserAssignmentDialog
                    role={assigningUserRole}
                    open={!!assigningUserRole}
                    onOpenChange={(open: boolean) => !open && setAssigningUserRole(null)}
                />
            )}

            {/* Agent Assignment Dialog */}
            {assigningAgentRole && (
                <AgentAssignmentDialog
                    role={assigningAgentRole}
                    open={!!assigningAgentRole}
                    onOpenChange={(open: boolean) => !open && setAssigningAgentRole(null)}
                />
            )}
        </div>
    );
}

function RoleDialog({ open, onOpenChange, onSubmit, initialData, isLoading }: any) {
    const isEdit = !!initialData;

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        const formData = new FormData(e.target as HTMLFormElement);
        const data: any = Object.fromEntries(formData);
        data.status = formData.get('status') === 'on' ? 1 : 0;
        data.order = parseInt(data.order as string) || 0;
        onSubmit(data);
    };

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent>
                <DialogHeader>
                    <DialogTitle>{isEdit ? '编辑角色' : '创建角色'}</DialogTitle>
                    <DialogDescription>
                        {isEdit ? '修改系统角色信息。' : '为系统添加一个新的功能角色。'}
                    </DialogDescription>
                </DialogHeader>
                <form onSubmit={handleSubmit} className="space-y-4">
                    <div className="grid gap-4 py-4">
                        <div className="grid grid-cols-4 items-center gap-4">
                            <Label htmlFor="name" className="text-right">角色名称</Label>
                            <Input id="name" name="name" defaultValue={initialData?.name} className="col-span-3" required />
                        </div>
                        <div className="grid grid-cols-4 items-center gap-4">
                            <Label htmlFor="code" className="text-right">角色编码</Label>
                            <Input id="code" name="code" defaultValue={initialData?.code} disabled={isEdit} className="col-span-3" required />
                        </div>
                        <div className="grid grid-cols-4 items-center gap-4">
                            <Label htmlFor="order" className="text-right">排序</Label>
                            <Input id="order" name="order" type="number" defaultValue={initialData?.order || 0} className="col-span-3" />
                        </div>
                        <div className="grid grid-cols-4 items-center gap-4">
                            <Label htmlFor="status" className="text-right">启用状态</Label>
                            <div className="flex items-center space-x-2 col-span-3">
                                <input
                                    type="checkbox"
                                    id="status"
                                    name="status"
                                    className="h-4 w-4 rounded border-gray-300"
                                    defaultChecked={initialData ? initialData.status === 1 : true}
                                />
                                <Label htmlFor="status" className="font-normal">是否立即启用</Label>
                            </div>
                        </div>
                    </div>
                    <DialogFooter>
                        <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>取消</Button>
                        <Button type="submit" disabled={isLoading}>{isLoading ? '保存中...' : '保存'}</Button>
                    </DialogFooter>
                </form>
            </DialogContent>
        </Dialog>
    );
}

function UserAssignmentDialog({ role, open, onOpenChange }: { role: Role, open: boolean, onOpenChange: (open: boolean) => void }) {
    const queryClient = useQueryClient();
    const [selectedIds, setSelectedIds] = useState<number[]>([]);
    const [selectedDeptId, setSelectedDeptId] = useState<string | null>(null);
    const [searchQuery, setSearchQuery] = useState("");

    // Fetch departments
    const { data: deptsTree, isLoading: loadingDepts } = useQuery({
        queryKey: ['depts_tree'],
        queryFn: async () => apiClient.get("/depts/tree") as Promise<any>,
    });

    // Fetch users for selected department
    const { data: deptUsers, isLoading: loadingUsers } = useQuery({
        queryKey: ['users_by_dept', selectedDeptId],
        queryFn: async () => {
            if (!selectedDeptId) return { items: [] };
            return apiClient.get(`/users?size=500&dept_id=${selectedDeptId}`) as Promise<any>;
        },
        enabled: !!selectedDeptId
    });

    // Fetch role members with details
    const { data: roleUsersDetails, isLoading: loadingInit } = useQuery({
        queryKey: ['role_users_details', role.id],
        queryFn: async () => {
             const res: any = await apiClient.get(`/roles/${role.id}/users/details`);
             return res || [];
        },
        enabled: open
    });

    // Cache user objects for name resolution
    const [userCache, setUserCache] = useState<Record<number, User>>({});

    // Sync initial selections and populate cache
    useEffect(() => {
        if (roleUsersDetails) {
            const cache = { ...userCache };
            roleUsersDetails.forEach((u: User) => { cache[u.id] = u; });
            setUserCache(cache);
            setSelectedIds(roleUsersDetails.map((u: User) => u.id));
        }
    }, [roleUsersDetails]);

    // Update cache from dept members
    useEffect(() => {
        if (deptUsers?.items) {
            setUserCache(prev => {
                const next = { ...prev };
                deptUsers.items.forEach((u: User) => { next[u.id] = u; });
                return next;
            });
        }
    }, [deptUsers]);


    const assignMutation = useMutation({
        mutationFn: (userIds: number[]) => {
            return apiClient.post(`/roles/${role.id}/users`, userIds);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['role_user_ids', role.id] });
            queryClient.invalidateQueries({ queryKey: ['role_users_details', role.id] });
            toast.success("成员分配更新成功");
            onOpenChange(false);
        }
    });

    const handleToggleUser = (user: User) => {
        if (selectedIds.includes(user.id)) {
            setSelectedIds(selectedIds.filter(id => id !== user.id));
        } else {
            setSelectedIds([...selectedIds, user.id]);
        }
    };

    const handleRemoveUser = (idToRemove: number) => {
        setSelectedIds(selectedIds.filter(id => id !== idToRemove));
    };

    // Derived filtered users
    const displayedUsers = deptUsers?.items?.filter((u: User) =>
        u.full_name?.includes(searchQuery) || u.username?.includes(searchQuery)
    ) || [];


    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="!w-[80vw] !max-w-none !h-[80vh] !p-0 !flex !flex-col !overflow-hidden">
                <DialogHeader className="p-6 pb-4 border-b shrink-0">
                    <DialogTitle>分配成员 - {role.name}</DialogTitle>
                    <DialogDescription>按部门多选用户，分配此角色。</DialogDescription>
                </DialogHeader>

                <div className="flex-1 grid grid-cols-3 divide-x min-h-0 overflow-hidden bg-zinc-50/50">
                    {/* 左侧：部门树 */}
                    <div className="flex flex-col min-h-0 bg-white">
                        <div className="p-4 border-b shrink-0 font-medium text-sm flex items-center gap-2">
                            <Building2 size={16} className="text-zinc-500" /> 组织架构
                        </div>
                        <div className="flex-1 overflow-y-auto min-h-0 p-3">
                            {loadingDepts ? (
                                <div className="flex justify-center py-8"><Loader2 className="animate-spin text-zinc-400" /></div>
                            ) : (
                                deptsTree ? <DeptTree nodes={deptsTree} selectedId={selectedDeptId} onSelect={setSelectedDeptId} /> : <div className="text-sm text-zinc-500 text-center py-8">暂无数据</div>
                            )}
                        </div>
                    </div>

                    {/* 中间：部门人员 */}
                    <div className="flex flex-col min-h-0 bg-white">
                        <div className="p-3 border-b shrink-0">
                            <div className="relative">
                                <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-zinc-400" />
                                <Input
                                    placeholder="搜索姓名或工号..."
                                    className="pl-9 bg-zinc-50/50"
                                    value={searchQuery}
                                    onChange={(e) => setSearchQuery(e.target.value)}
                                />
                            </div>
                        </div>
                        <div className="flex-1 overflow-y-auto min-h-0 p-3">
                            {!selectedDeptId ? (
                                <div className="flex flex-col items-center justify-center py-20 text-zinc-400 gap-2">
                                    <ChevronRight className="rotate-90 md:rotate-0" opacity={0.5} />
                                    <span className="text-sm">请先选择左侧部门</span>
                                </div>
                            ) : loadingUsers ? (
                                <div className="flex justify-center p-8"><Loader2 className="animate-spin text-zinc-400" /></div>
                            ) : displayedUsers.length === 0 ? (
                                <div className="text-sm text-zinc-500 text-center py-8">该部门下暂无相关人员</div>
                            ) : (
                                <div className="space-y-1">
                                    {displayedUsers.map((user: User) => {
                                        const isSelected = selectedIds.includes(user.id);
                                        return (
                                            <div
                                                key={user.id}
                                                onClick={() => handleToggleUser(user)}
                                                className={cn(
                                                    "flex items-center justify-between p-2.5 rounded-lg border cursor-pointer transition-colors",
                                                    isSelected ? "bg-zinc-100 border-zinc-300" : "hover:bg-zinc-50 border-transparent bg-white shadow-sm"
                                                )}
                                            >
                                                <div className="flex items-center gap-3">
                                                    <div className="w-8 h-8 rounded-full bg-zinc-200 flex items-center justify-center shrink-0">
                                                        <Users size={14} className="text-zinc-500" />
                                                    </div>
                                                    <div className="overflow-hidden">
                                                        <div className="text-sm font-medium truncate">{user.full_name || user.username}</div>
                                                        <div className="text-xs text-zinc-500 truncate">@{user.username}</div>
                                                    </div>
                                                </div>
                                                <div className={cn(
                                                    "w-4 h-4 rounded border flex items-center justify-center",
                                                    isSelected ? "border-blue-600 bg-blue-600" : "border-zinc-300"
                                                )}>
                                                    {isSelected && <Check size={12} className="text-white" />}
                                                </div>
                                            </div>
                                        );
                                    })}
                                </div>
                            )}
                        </div>
                    </div>

                    {/* 右侧：已选人员 */}
                    <div className="flex flex-col min-h-0 bg-zinc-50/50">
                        <div className="p-4 border-b shrink-0 bg-white font-medium text-sm flex items-center justify-between">
                            <div className="flex items-center gap-2">
                                已选人员
                                <Badge variant="secondary" className="font-mono">{selectedIds.length}</Badge>
                            </div>
                            {selectedIds.length > 0 && (
                                <Button variant="ghost" size="sm" onClick={() => setSelectedIds([])} className="h-6 px-2 text-xs text-zinc-500 hover:text-red-500">
                                    清空
                                </Button>
                            )}
                        </div>
                        <div className="flex-1 overflow-y-auto min-h-0 p-3">
                            {loadingInit ? (
                                <div className="flex justify-center p-8"><Loader2 className="animate-spin text-zinc-400" /></div>
                            ) : selectedIds.length === 0 ? (
                                <div className="text-sm text-zinc-400 text-center py-8">暂无已选人员</div>
                            ) : (
                                <div className="space-y-2">
                                    {selectedIds.map(id => {
                                        const user = userCache[id];
                                        return (
                                            <div key={id} className="flex items-center justify-between bg-white p-2.5 rounded-lg border shadow-sm group">
                                                <div className="flex items-center gap-3 overflow-hidden">
                                                    <div className="w-7 h-7 rounded-full bg-zinc-100 flex items-center justify-center shrink-0">
                                                        <Users size={12} className="text-zinc-500" />
                                                    </div>
                                                    <div className="overflow-hidden">
                                                        <div className="text-sm font-medium truncate">{user ? (user.full_name || user.username) : `ID: ${id}`}</div>
                                                    </div>
                                                </div>
                                                <Button
                                                    variant="ghost"
                                                    size="icon"
                                                    className="h-6 w-6 opacity-0 group-hover:opacity-100 text-zinc-400 hover:text-red-500 transition-opacity"
                                                    onClick={(e) => {
                                                        e.stopPropagation();
                                                        handleRemoveUser(id);
                                                    }}
                                                >
                                                    <X size={14} />
                                                </Button>
                                            </div>
                                        );
                                    })}
                                </div>
                            )}
                        </div>
                    </div>
                </div>

                <DialogFooter className="p-4 border-t shrink-0 bg-white">
                    <Button variant="outline" onClick={() => onOpenChange(false)}>取消</Button>
                    <Button onClick={() => assignMutation.mutate(selectedIds)} disabled={assignMutation.isPending}>
                        {assignMutation.isPending ? "提交中..." : "保存更改"}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

function AgentAssignmentDialog({ role, open, onOpenChange }: { role: Role, open: boolean, onOpenChange: (open: boolean) => void }) {
    const [selectedIds, setSelectedIds] = useState<number[]>([]);

    const { data: groupsResult, isLoading: loadingGroups } = useQuery({
        queryKey: ['agent_groups_all'],
        queryFn: async () => apiClient.get("/agents/groups") as Promise<any>,
    });

    const { data: appsResult, isLoading: loadingApps } = useQuery({
        queryKey: ['agent_apps_all'],
        queryFn: async () => apiClient.get("/agents/apps") as Promise<any>,
    });

    const { data: currentIds, isLoading: loadingCurrent } = useQuery({
        queryKey: ['role_agent_ids', role.id],
        queryFn: async () => {
            const res: any = await apiClient.get(`/agents/role/${role.id}/agents`);
            return res || [];
        },
        enabled: open
    });

    useEffect(() => {
        if (currentIds) {
            setSelectedIds(currentIds);
        }
    }, [currentIds]);

    const assignMutation = useMutation({
        mutationFn: (ids: number[]) => apiClient.post("/agents/assign/role", {
            role_id: role.id,
            agent_app_ids: ids
        }),
        onSuccess: () => {
            toast.success("权限分配成功");
            onOpenChange(false);
        }
    });

    const toggleAgent = (id: number) => {
        if (selectedIds.includes(id)) {
            setSelectedIds(selectedIds.filter(i => i !== id));
        } else {
            setSelectedIds([...selectedIds, id]);
        }
    };

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="max-w-2xl">
                <DialogHeader>
                    <DialogTitle>智能体授权 - {role.name}</DialogTitle>
                    <DialogDescription>配置该角色下可访问的智能体应用。</DialogDescription>
                </DialogHeader>
                <div className="py-4">
                    <ScrollArea className="h-[400px] pr-4">
                        {loadingGroups || loadingApps || loadingCurrent ? (
                            <div className="flex justify-center p-12"><Loader2 className="animate-spin" /></div>
                        ) : groupsResult?.map((group: AgentGroup) => (
                            <div key={group.id} className="mb-8 last:mb-0">
                                <h3 className="text-sm font-bold text-zinc-500 uppercase tracking-widest mb-4 flex items-center gap-2">
                                    <div className="w-1.5 h-1.5 rounded-full bg-zinc-800" />
                                    {group.name}
                                </h3>
                                <div className="grid grid-cols-2 gap-3">
                                    {appsResult?.filter((app: AgentApp) => app.group_id === group.id).map((app: AgentApp) => (
                                        <div
                                            key={app.id}
                                            onClick={() => toggleAgent(app.id)}
                                                className={cn(
                                                    "flex items-center justify-between p-4 rounded-xl border cursor-pointer transition-all duration-200",
                                                    selectedIds.includes(app.id)
                                                        ? "border-blue-200 bg-blue-50 text-blue-900 shadow-lg shadow-blue-100"
                                                        : "bg-white border-zinc-100 hover:border-blue-200 hover:bg-blue-50/50"
                                                )}
                                            >
                                            <div className="flex items-center gap-3">
                                                <div className={cn(
                                                    "w-10 h-10 rounded-lg flex items-center justify-center",
                                                    selectedIds.includes(app.id) ? "bg-blue-600 text-white" : "bg-zinc-100"
                                                )}>
                                                    <Shield size={20} />
                                                </div>
                                                <span className="font-semibold text-sm tracking-tight">{app.name}</span>
                                            </div>
                                            {selectedIds.includes(app.id) && <Check size={18} className="text-blue-600" />}
                                        </div>
                                    ))}
                                </div>
                            </div>
                        ))}
                    </ScrollArea>
                </div>
                <DialogFooter className="border-t pt-4">
                    <div className="flex-1 text-sm text-zinc-500 font-medium">
                        已选择 <span className="text-zinc-900">{selectedIds.length}</span> 个智能体
                    </div>
                    <Button variant="outline" onClick={() => onOpenChange(false)}>取消</Button>
                    <Button
                        className="rounded-xl bg-blue-600 px-8 hover:bg-blue-700"
                        onClick={() => assignMutation.mutate(selectedIds)}
                        disabled={assignMutation.isPending}
                    >
                        {assignMutation.isPending ? "同步中..." : "保存设置"}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
