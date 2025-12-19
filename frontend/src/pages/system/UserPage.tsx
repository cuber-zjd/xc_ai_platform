import type { User } from "@/api/auth";
import { userApi, type UserCreatePayload, type UserUpdatePayload } from "@/api/users";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
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
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from "@/components/ui/table";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, MoreHorizontal, Pencil, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

export default function UserPage() {
    const queryClient = useQueryClient();
    const [page, setPage] = useState(1);
    const [isCreateOpen, setIsCreateOpen] = useState(false);
    const [editingUser, setEditingUser] = useState<User | null>(null);

    // Fetch Users
    const { data: userResult, isLoading } = useQuery({
        queryKey: ['users', page],
        queryFn: () => userApi.getList(page),
    });

    // Mutations
    const createMutation = useMutation({
        mutationFn: userApi.create,
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['users'] });
            setIsCreateOpen(false);
            toast.success("用户创建成功");
        },
    });

    const updateMutation = useMutation({
        mutationFn: ({ id, data }: { id: string; data: UserUpdatePayload }) =>
            userApi.update(id, data),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['users'] });
            setEditingUser(null);
            toast.success("用户更新成功");
        },
    });

    const deleteMutation = useMutation({
        mutationFn: userApi.delete,
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['users'] });
            toast.success("用户删除成功");
        },
    });

    const handleDelete = (id: string) => {
        if (confirm("确定要删除该用户吗？")) {
            deleteMutation.mutate(id);
        }
    };

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <div>
                    <h2 className="text-2xl font-bold tracking-tight">用户管理</h2>
                    <p className="text-muted-foreground">
                        管理系统用户及其角色权限。
                    </p>
                </div>
                <div className="flex items-center gap-2">
                    <Button onClick={() => setIsCreateOpen(true)}>
                        <Plus className="mr-2 h-4 w-4" /> 添加用户
                    </Button>
                </div>
            </div>

            {/* Table */}
            <div className="rounded-md border bg-card">
                <Table>
                    <TableHeader>
                        <TableRow>
                            <TableHead className="w-[80px]">头像</TableHead>
                            <TableHead>用户信息</TableHead>
                            <TableHead>角色</TableHead>
                            <TableHead>状态</TableHead>
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
                        ) : userResult?.items.map((user) => (
                            <TableRow key={user.id}>
                                <TableCell>
                                    <Avatar>
                                        <AvatarImage src={user.avatar} />
                                        <AvatarFallback>{user.username.substring(0, 2).toUpperCase()}</AvatarFallback>
                                    </Avatar>
                                </TableCell>
                                <TableCell>
                                    <div className="flex flex-col">
                                        <span className="font-medium">{user.full_name || user.username}</span>
                                        <span className="text-xs text-muted-foreground">{user.email}</span>
                                    </div>
                                </TableCell>
                                <TableCell>
                                    <Badge variant={user.role === 'admin' ? 'default' : 'secondary'}>
                                        {user.role}
                                    </Badge>
                                </TableCell>
                                <TableCell>
                                    <div className="flex items-center gap-2">
                                        <span className={`h-2 w-2 rounded-full ${user.status === 1 ? 'bg-green-500' : 'bg-red-500'}`} />
                                        <span className="text-sm text-muted-foreground">
                                            {user.status === 1 ? '在职' : '离职'}
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
                                            <DropdownMenuItem onClick={() => setEditingUser(user)}>
                                                <Pencil className="mr-2 h-4 w-4" /> 编辑
                                            </DropdownMenuItem>
                                            <DropdownMenuItem className="text-red-600" onClick={() => handleDelete(user.id)}>
                                                <Trash2 className="mr-2 h-4 w-4" /> 删除
                                            </DropdownMenuItem>
                                        </DropdownMenuContent>
                                    </DropdownMenu>
                                </TableCell>
                            </TableRow>
                        ))}
                    </TableBody>
                </Table>
            </div>

            {/* Create Dialog */}
            <UserDialog
                open={isCreateOpen}
                onOpenChange={setIsCreateOpen}
                onSubmit={(data: UserCreatePayload) => createMutation.mutate(data)}
                isLoading={createMutation.isPending}
                mode="create"
            />

            {/* Edit Dialog */}
            {editingUser && (
                <UserDialog
                    open={!!editingUser}
                    onOpenChange={(open: boolean) => !open && setEditingUser(null)}
                    onSubmit={(data: UserUpdatePayload) => updateMutation.mutate({ id: editingUser.id, data })}
                    initialData={editingUser}
                    isLoading={updateMutation.isPending}
                    mode="edit"
                />
            )}
        </div>
    );
}

function UserDialog({ open, onOpenChange, onSubmit, initialData, isLoading, mode }: any) {
    const isEdit = mode === 'edit';

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        const formData = new FormData(e.target as HTMLFormElement);
        const data: any = Object.fromEntries(formData);

        // Transform checkbox
        data.is_superuser = formData.get('is_superuser') === 'on';
        // Status logic if needed, or defaults

        onSubmit(data);
    };

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent>
                <DialogHeader>
                    <DialogTitle>{isEdit ? '编辑用户' : '创建用户'}</DialogTitle>
                    <DialogDescription>
                        {isEdit ? '更新用户信息。' : '添加一个新用户到系统。'}
                    </DialogDescription>
                </DialogHeader>
                <form onSubmit={handleSubmit} className="space-y-4">
                    <div className="grid gap-4 py-4">
                        <div className="grid grid-cols-4 items-center gap-4">
                            <Label htmlFor="username" className="text-right">用户名</Label>
                            <Input id="username" name="username" defaultValue={initialData?.username} disabled={isEdit} className="col-span-3" required />
                        </div>
                        <div className="grid grid-cols-4 items-center gap-4">
                            <Label htmlFor="full_name" className="text-right">姓名</Label>
                            <Input id="full_name" name="full_name" defaultValue={initialData?.full_name} className="col-span-3" required />
                        </div>
                        <div className="grid grid-cols-4 items-center gap-4">
                            <Label htmlFor="email" className="text-right">邮箱</Label>
                            <Input id="email" name="email" type="email" defaultValue={initialData?.email} className="col-span-3" />
                        </div>
                        {(!isEdit || true) && ( // Allow password reset on edit? Usually separate. Let's allow for now.
                            <div className="grid grid-cols-4 items-center gap-4">
                                <Label htmlFor="password" className="text-right">密码</Label>
                                <Input
                                    id="password"
                                    name="password"
                                    type="password"
                                    placeholder={isEdit ? "留空则保持不变" : ""}
                                    className="col-span-3"
                                    required={!isEdit}
                                />
                            </div>
                        )}
                        <div className="grid grid-cols-4 items-center gap-4">
                            <Label htmlFor="is_superuser" className="text-right">管理员</Label>
                            <div className="flex items-center space-x-2 col-span-3">
                                <input
                                    type="checkbox"
                                    id="is_superuser"
                                    name="is_superuser"
                                    className="h-4 w-4 rounded border-gray-300"
                                    defaultChecked={initialData?.role === 'admin'}
                                />
                                <Label htmlFor="is_superuser" className="font-normal">授予管理员权限</Label>
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
