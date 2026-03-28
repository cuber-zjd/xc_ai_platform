import {
    Clock,
    MessageSquare,
    FileCheck,
    Star,
    ArrowRight,
    Activity,
    TrendingUp,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { useAuthStore } from '@/store/useAuthStore';
import { useNavigate } from 'react-router-dom';

// 最近对话 mock 数据
const RECENT_CHATS = [
    { id: '1', title: '季度销售数据分析报告', time: '10 分钟前', icon: '📊' },
    { id: '2', title: '合同条款风险审查', time: '1 小时前', icon: '📝' },
    { id: '3', title: 'Python 数据处理脚本', time: '昨天', icon: '💻' },
    { id: '4', title: '月度工作总结撰写', time: '2 天前', icon: '✍️' },
];

// 常用工具快捷入口
const QUICK_TOOLS = [
    { icon: MessageSquare, label: 'AI 对话', path: '/chat-home', color: 'text-blue-500', bg: 'bg-blue-500/10' },
    { icon: FileCheck, label: '合同智审', path: '/contracts', color: 'text-emerald-500', bg: 'bg-emerald-500/10' },
    { icon: Star, label: '收藏夹', path: '#', color: 'text-amber-500', bg: 'bg-amber-500/10' },
    { icon: Activity, label: '使用统计', path: '#', color: 'text-violet-500', bg: 'bg-violet-500/10' },
];

export default function WorkspacePage() {
    const { user } = useAuthStore();
    const navigate = useNavigate();

    return (
        <div className="space-y-8 max-w-6xl mx-auto">
            {/* 顶部统计概览 */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="rounded-xl border bg-card p-5 space-y-2">
                    <div className="flex items-center justify-between">
                        <span className="text-sm text-muted-foreground">今日对话</span>
                        <MessageSquare className="h-4 w-4 text-muted-foreground" />
                    </div>
                    <div className="text-3xl font-bold">12</div>
                    <div className="flex items-center gap-1 text-xs text-emerald-500">
                        <TrendingUp className="h-3 w-3" />
                        <span>较昨日 +25%</span>
                    </div>
                </div>
                <div className="rounded-xl border bg-card p-5 space-y-2">
                    <div className="flex items-center justify-between">
                        <span className="text-sm text-muted-foreground">已审文档</span>
                        <FileCheck className="h-4 w-4 text-muted-foreground" />
                    </div>
                    <div className="text-3xl font-bold">3</div>
                    <div className="text-xs text-muted-foreground">本周累计</div>
                </div>
                <div className="rounded-xl border bg-card p-5 space-y-2">
                    <div className="flex items-center justify-between">
                        <span className="text-sm text-muted-foreground">使用时长</span>
                        <Clock className="h-4 w-4 text-muted-foreground" />
                    </div>
                    <div className="text-3xl font-bold">2.5h</div>
                    <div className="text-xs text-muted-foreground">今日累计</div>
                </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* 左侧 - 快捷入口 + 最近对话 */}
                <div className="lg:col-span-2 space-y-6">
                    {/* 快捷入口 */}
                    <div className="space-y-3">
                        <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider">
                            快捷入口
                        </h3>
                        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                            {QUICK_TOOLS.map((tool) => (
                                <button
                                    key={tool.label}
                                    onClick={() => navigate(tool.path)}
                                    className={cn(
                                        'flex flex-col items-center gap-2 p-4 rounded-xl border',
                                        'hover:shadow-md hover:-translate-y-0.5 transition-all duration-300',
                                        'bg-card cursor-pointer'
                                    )}
                                >
                                    <div className={cn('flex h-10 w-10 items-center justify-center rounded-xl', tool.bg)}>
                                        <tool.icon className={cn('h-5 w-5', tool.color)} />
                                    </div>
                                    <span className="text-sm font-medium">{tool.label}</span>
                                </button>
                            ))}
                        </div>
                    </div>

                    {/* 最近对话 */}
                    <div className="space-y-3">
                        <div className="flex items-center justify-between">
                            <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider">
                                最近对话
                            </h3>
                            <button className="text-xs text-muted-foreground hover:text-foreground transition-colors flex items-center gap-1">
                                查看全部 <ArrowRight className="h-3 w-3" />
                            </button>
                        </div>
                        <div className="space-y-2">
                            {RECENT_CHATS.map((chat) => (
                                <button
                                    key={chat.id}
                                    className={cn(
                                        'w-full flex items-center gap-3 p-3 rounded-lg border',
                                        'hover:bg-accent/50 transition-colors cursor-pointer text-left'
                                    )}
                                >
                                    <span className="text-lg">{chat.icon}</span>
                                    <div className="flex-1 min-w-0">
                                        <div className="text-sm font-medium truncate">{chat.title}</div>
                                    </div>
                                    <span className="text-xs text-muted-foreground whitespace-nowrap">
                                        {chat.time}
                                    </span>
                                </button>
                            ))}
                        </div>
                    </div>
                </div>

                {/* 右侧 - 个人信息卡片 */}
                <div className="space-y-4">
                    <div className="rounded-xl border bg-card p-5 space-y-4">
                        <div className="flex items-center gap-3">
                            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-primary/10 text-primary font-bold text-lg">
                                {(user?.full_name || user?.username || 'U').charAt(0)}
                            </div>
                            <div>
                                <div className="font-semibold">{user?.full_name || user?.username}</div>
                                <div className="text-xs text-muted-foreground">{user?.username}</div>
                            </div>
                        </div>
                        <div className="h-px bg-border" />
                        <div className="space-y-2 text-sm">
                            <div className="flex justify-between">
                                <span className="text-muted-foreground">角色</span>
                                <span className="font-medium">{user?.role === 'admin' ? '管理员' : '普通用户'}</span>
                            </div>
                            <div className="flex justify-between">
                                <span className="text-muted-foreground">部门</span>
                                <span className="font-medium">{user?.dept_id || '未分配'}</span>
                            </div>
                        </div>
                    </div>

                    {/* 使用提示 */}
                    <div className="rounded-xl border border-dashed bg-muted/30 p-4 space-y-2">
                        <div className="text-sm font-medium">💡 小提示</div>
                        <p className="text-xs text-muted-foreground leading-relaxed">
                            你可以在 AI 对话中使用 Shift+Enter 换行，支持上传文件进行分析。遇到问题可以随时切换不同的 AI 模型。
                        </p>
                    </div>
                </div>
            </div>
        </div>
    );
}
