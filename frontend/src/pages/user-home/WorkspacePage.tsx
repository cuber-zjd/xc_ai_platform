import {
    Clock,
    MessageSquare,
    FileCheck,
    ArrowRight,
    Loader2,
    Sparkles,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { useAuthStore } from '@/store/useAuthStore';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { apiClient } from '@/api/client';
import { Button } from '@/components/ui/button';

interface WorkbenchAgent {
    id: number;
    name: string;
    description?: string;
    icon?: string;
    route_path: string;
}

interface WorkbenchGroup {
    id: number;
    name: string;
    agents: WorkbenchAgent[];
}

export default function WorkspacePage() {
    const { user } = useAuthStore();
    const navigate = useNavigate();

    const { data: workbenchData, isLoading } = useQuery({
        queryKey: ['workbench'],
        queryFn: async () => {
            const res: any = await apiClient.get('/agents/workbench');
            return res || [];
        },
    });

    return (
        <div className="space-y-8 max-w-6xl mx-auto">
            {/* 顶部统计概览 */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <StatCard
                    title="今日对话"
                    value="12"
                    trend="+25%"
                    icon={MessageSquare}
                    trendUp
                />
                <StatCard
                    title="已审文档"
                    value="3"
                    subtitle="本周累计"
                    icon={FileCheck}
                />
                <StatCard
                    title="使用时长"
                    value="2.5h"
                    subtitle="今日累计"
                    icon={Clock}
                />
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* 左侧 - 智能体工作台 */}
                <div className="lg:col-span-2 space-y-6">
                    {/* 智能体快捷入口 */}
                    <div className="space-y-4">
                        <div className="flex items-center justify-between">
                            <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-2">
                                <Sparkles className="h-4 w-4" />
                                智能体工作台
                            </h3>
                            <Button variant="ghost" size="sm" className="text-xs h-7" onClick={() => navigate('/chat-home')}>
                                展开全部 <ArrowRight className="h-3 w-3 ml-1" />
                            </Button>
                        </div>

                        {isLoading ? (
                            <div className="flex items-center justify-center py-12">
                                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                            </div>
                        ) : workbenchData && workbenchData.length > 0 ? (
                            <div className="space-y-6">
                                {workbenchData.map((group: WorkbenchGroup) => (
                                    <div key={group.id} className="space-y-3">
                                        <div className="text-sm font-medium text-muted-foreground/70">
                                            {group.name}
                                        </div>
                                        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
                                            {group.agents.map((agent) => (
                                                <AgentCard key={agent.id} agent={agent} />
                                            ))}
                                        </div>
                                    </div>
                                ))}
                            </div>
                        ) : (
                            <EmptyState />
                        )}
                    </div>
                </div>

                {/* 右侧 - 个人信息卡片 */}
                <div className="space-y-4">
                    <div className="rounded-2xl border bg-card p-6 space-y-4 shadow-sm">
                        <div className="flex items-center gap-3">
                            <div className="relative">
                                <div className="flex h-14 w-14 items-center justify-center rounded-full bg-gradient-to-br from-primary/20 to-primary/5 text-primary font-bold text-xl ring-4 ring-primary/10">
                                    {(user?.full_name || user?.username || 'U').charAt(0).toUpperCase()}
                                </div>
                                <div className="absolute -bottom-0.5 -right-0.5 w-4 h-4 bg-emerald-500 rounded-full ring-2 ring-card" />
                            </div>
                            <div>
                                <div className="font-semibold text-lg">{user?.full_name || user?.username}</div>
                                <div className="text-xs text-muted-foreground">@{user?.username}</div>
                            </div>
                        </div>
                        <div className="h-px bg-border/60" />
                        <div className="space-y-3">
                            <InfoRow label="角色" value={user?.role === 'admin' ? '管理员' : '普通用户'} />
                            <InfoRow label="部门" value={user?.dept_id || '未分配'} />
                        </div>
                    </div>

                    {/* 使用提示 */}
                    <div className="rounded-2xl border border-dashed bg-gradient-to-br from-amber-500/5 to-orange-500/5 p-5 space-y-3">
                        <div className="flex items-center gap-2 text-sm font-medium">
                            <span className="text-lg">💡</span>
                            <span>使用技巧</span>
                        </div>
                        <p className="text-xs text-muted-foreground leading-relaxed">
                            在 AI 对话中使用 <kbd className="px-1.5 py-0.5 bg-muted rounded text-[10px] font-mono">Shift+Enter</kbd> 换行，支持上传文件进行分析。遇到问题可以随时切换不同的 AI 模型。
                        </p>
                    </div>
                </div>
            </div>
        </div>
    );
}

function StatCard({
    title,
    value,
    subtitle,
    trend,
    icon: Icon,
    trendUp
}: {
    title: string;
    value: string;
    subtitle?: string;
    trend?: string;
    icon: any;
    trendUp?: boolean;
}) {
    return (
        <div className="rounded-2xl border bg-card p-5 space-y-3 shadow-sm hover:shadow-md transition-shadow duration-300">
            <div className="flex items-center justify-between">
                <span className="text-sm text-muted-foreground">{title}</span>
                <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10">
                    <Icon className="h-4 w-4 text-primary" />
                </div>
            </div>
            <div className="text-3xl font-bold tracking-tight">{value}</div>
            {(subtitle || trend) && (
                <div className={cn("flex items-center gap-1 text-xs", trendUp ? "text-emerald-500" : "text-muted-foreground")}>
                    {trend && (
                        <>
                            <span>{trendUp ? '↑' : '↓'}</span>
                            <span>{trend}</span>
                        </>
                    )}
                    {subtitle && <span>{trend ? '' : subtitle}</span>}
                </div>
            )}
        </div>
    );
}

function AgentCard({ agent }: { agent: WorkbenchAgent }) {
    const navigate = useNavigate();

    return (
        <button
            onClick={() => navigate(agent.route_path || '/chat-home')}
            className={cn(
                "group relative flex flex-col items-center gap-3 p-4 rounded-2xl border bg-card",
                "hover:shadow-lg hover:-translate-y-1 transition-all duration-300",
                "cursor-pointer text-center"
            )}
        >
            {/* Logo 区域 */}
            <div className="relative flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-zinc-100 to-zinc-50 shadow-sm ring-1 ring-black/5">
                {agent.icon && agent.icon.startsWith('http') ? (
                    <img
                        src={agent.icon}
                        alt={agent.name}
                        className="h-8 w-8 object-contain"
                        onError={(e) => {
                            (e.target as HTMLImageElement).style.display = 'none';
                            (e.target as HTMLImageElement).nextElementSibling?.classList.remove('hidden');
                        }}
                    />
                ) : null}
                {!agent.icon || !agent.icon.startsWith('http') ? (
                    <Sparkles className="h-7 w-7 text-zinc-400" />
                ) : null}
            </div>

            {/* 名称 */}
            <div className="w-full">
                <div className="text-sm font-semibold truncate">{agent.name}</div>
                {agent.description && (
                    <div className="text-xs text-muted-foreground truncate mt-0.5">
                        {agent.description}
                    </div>
                )}
            </div>

            {/* Hover 效果 */}
            <div className="absolute inset-0 rounded-2xl bg-gradient-to-br from-primary/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none" />
        </button>
    );
}

function InfoRow({ label, value }: { label: string; value: string }) {
    return (
        <div className="flex items-center justify-between">
            <span className="text-sm text-muted-foreground">{label}</span>
            <span className="text-sm font-medium">{value}</span>
        </div>
    );
}

function EmptyState() {
    const navigate = useNavigate();
    return (
        <div className="flex flex-col items-center justify-center py-12 rounded-2xl border border-dashed bg-muted/20">
            <Sparkles className="h-10 w-10 text-muted-foreground/50 mb-3" />
            <div className="text-sm font-medium text-muted-foreground mb-1">暂无可用智能体</div>
            <div className="text-xs text-muted-foreground/70 mb-4">请联系管理员分配权限</div>
            <Button size="sm" variant="outline" onClick={() => navigate('/chat-home')}>
                前往对话
            </Button>
        </div>
    );
}
