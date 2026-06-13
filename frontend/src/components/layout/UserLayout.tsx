import { useEffect, useMemo, useState } from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import {
    Bot,
    BriefcaseBusiness,
    ChevronLeft,
    ChevronRight,
    FileCheck,
    LayoutGrid,
    LogOut,
    MessageSquarePlus,
    Pin,
    Search,
    Sparkles,
} from 'lucide-react';

import { apiClient } from '@/api/client';
import { Button } from '@/components/ui/button';
import { Toaster } from '@/components/ui/sonner';
import {
    flattenWorkbenchGroups,
    getPinnedAgentIds,
    getRecentAgentIds,
    recordRecentAgent,
    selectVisibleAgents,
    togglePinnedAgent,
    type WorkbenchAgent,
    type WorkbenchGroup,
} from '@/features/agent-workbench/workbenchStorage';
import { cn } from '@/lib/utils';
import { useAuthStore } from '@/store/useAuthStore';

const primaryNavItems = [
    {
        label: '新对话',
        icon: MessageSquarePlus,
        path: '/chat-home',
    },
    {
        label: '搜索智能体',
        icon: Search,
        path: '/workspace',
    },
    {
        label: '应用中心',
        icon: LayoutGrid,
        path: '/toolbox',
    },
];

const businessNavItems = [
    {
        label: '合同审查',
        icon: FileCheck,
        path: '/contracts',
    },
    {
        label: '报表生成',
        icon: BriefcaseBusiness,
        path: '/fr-ai-reports',
    },
    {
        label: 'SAP 助手',
        icon: Bot,
        path: '/sap-assistant',
    },
];

const isActivePath = (pathname: string, path: string) => pathname === path || pathname.startsWith(`${path}/`);

function AgentAvatar({ agent }: { agent: WorkbenchAgent }) {
    if (agent.icon?.startsWith('http')) {
        return <img src={agent.icon} alt={agent.name} className="h-6 w-6 rounded-md object-contain" />;
    }

    return <span className="text-xs font-semibold text-[#424242]">{agent.name.slice(0, 1)}</span>;
}

export default function UserLayout() {
    const [isSidebarOpen, setIsSidebarOpen] = useState(true);
    const [workbenchGroups, setWorkbenchGroups] = useState<WorkbenchGroup[]>([]);
    const [pinnedIds, setPinnedIds] = useState<number[]>(() => getPinnedAgentIds());
    const [recentIds, setRecentIds] = useState<number[]>(() => getRecentAgentIds());
    const navigate = useNavigate();
    const location = useLocation();
    const { logout, checkAuth, user } = useAuthStore();

    useEffect(() => {
        void checkAuth();
    }, [checkAuth]);

    useEffect(() => {
        let ignore = false;

        async function fetchWorkbench() {
            try {
                const data = (await apiClient.get('/agents/workbench')) as unknown as WorkbenchGroup[];
                if (!ignore) setWorkbenchGroups(data ?? []);
            } catch {
                if (!ignore) setWorkbenchGroups([]);
            }
        }

        void fetchWorkbench();
        return () => {
            ignore = true;
        };
    }, []);

    const allAgents = useMemo(() => flattenWorkbenchGroups(workbenchGroups), [workbenchGroups]);
    const pinnedAgents = useMemo(() => selectVisibleAgents(pinnedIds, allAgents), [allAgents, pinnedIds]);
    const recentAgents = useMemo(
        () => selectVisibleAgents(recentIds.filter((id) => !pinnedIds.includes(id)), allAgents),
        [allAgents, pinnedIds, recentIds],
    );
    const fallbackAgents = useMemo(
        () => allAgents.filter((agent) => !pinnedIds.includes(agent.id)).slice(0, 4),
        [allAgents, pinnedIds],
    );
    const visibleAgents = pinnedAgents.length || recentAgents.length
        ? [...pinnedAgents, ...recentAgents].slice(0, 8)
        : fallbackAgents;
    const usesFixedCanvas = location.pathname.startsWith('/sap-assistant');

    const handleLogout = () => {
        logout();
        navigate('/login');
    };

    const handleAgentClick = (agent: WorkbenchAgent) => {
        setRecentIds(recordRecentAgent(agent.id));
        navigate(agent.route_path || '/chat-home');
    };

    const handleTogglePinned = (agentId: number) => {
        setPinnedIds(togglePinnedAgent(agentId));
    };

    return (
        <div className="app-shell bg-[#ffffff] text-[#171717]">
            <div className="flex h-screen overflow-hidden">
                <aside
                    className={cn(
                        'flex shrink-0 flex-col border-r border-[#e5e5e5] bg-[#f7f7f7] transition-all duration-200',
                        isSidebarOpen ? 'w-[272px]' : 'w-[72px]',
                    )}
                >
                    <div className="flex h-14 items-center gap-2 px-3">
                        <button
                            type="button"
                            onClick={() => navigate('/chat-home')}
                            className={cn(
                                'flex h-9 min-w-0 items-center rounded-lg px-2 text-left text-sm font-semibold text-[#171717] hover:bg-[#ececec]',
                                isSidebarOpen ? 'flex-1 gap-2' : 'justify-center',
                            )}
                        >
                            <Sparkles className="h-4 w-4 shrink-0" />
                            {isSidebarOpen && <span className="truncate">AI Platform</span>}
                        </button>
                        <Button
                            type="button"
                            variant="ghost"
                            size="icon-sm"
                            className="rounded-lg text-[#6f6f6f] hover:bg-[#ececec]"
                            onClick={() => setIsSidebarOpen((value) => !value)}
                            aria-label={isSidebarOpen ? '收起侧边栏' : '展开侧边栏'}
                        >
                            {isSidebarOpen ? <ChevronLeft className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                        </Button>
                    </div>

                    <nav className="space-y-1 px-2 pb-3">
                        {primaryNavItems.map((item) => {
                            const isActive = isActivePath(location.pathname, item.path);
                            return (
                                <button
                                    key={item.path}
                                    type="button"
                                    onClick={() => navigate(item.path)}
                                    className={cn(
                                        'flex h-10 w-full items-center rounded-lg text-sm transition-colors',
                                        isSidebarOpen ? 'gap-3 px-3 text-left' : 'justify-center px-0',
                                        isActive ? 'bg-[#ececec] text-[#171717]' : 'text-[#333333] hover:bg-[#ececec]',
                                    )}
                                >
                                    <item.icon className="h-4 w-4 shrink-0" />
                                    {isSidebarOpen && <span className="truncate">{item.label}</span>}
                                </button>
                            );
                        })}
                    </nav>

                    <div className="min-h-0 flex-1 overflow-y-auto px-2 py-2">
                        {isSidebarOpen && (
                            <div className="px-3 pb-2 text-xs font-medium text-[#8a8a8a]">
                                {pinnedAgents.length || recentAgents.length ? '常用智能体' : '推荐智能体'}
                            </div>
                        )}
                        <div className="space-y-1">
                            {visibleAgents.map((agent) => {
                                const isPinned = pinnedIds.includes(agent.id);
                                const isActive = isActivePath(location.pathname, agent.route_path);
                                return (
                                    <div key={agent.id} className="group relative">
                                        <button
                                            type="button"
                                            onClick={() => handleAgentClick(agent)}
                                            className={cn(
                                                'flex h-10 w-full min-w-0 items-center rounded-lg text-sm transition-colors',
                                                isSidebarOpen ? 'gap-3 px-3 pr-9 text-left' : 'justify-center px-0',
                                                isActive ? 'bg-[#ececec] text-[#171717]' : 'text-[#333333] hover:bg-[#ececec]',
                                            )}
                                            title={agent.name}
                                        >
                                            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-white ring-1 ring-[#dfdfdf]">
                                                <AgentAvatar agent={agent} />
                                            </span>
                                            {isSidebarOpen && <span className="truncate">{agent.name}</span>}
                                        </button>
                                        {isSidebarOpen && (
                                            <button
                                                type="button"
                                                onClick={() => handleTogglePinned(agent.id)}
                                                className={cn(
                                                    'absolute right-2 top-1/2 flex h-6 w-6 -translate-y-1/2 items-center justify-center rounded-md text-[#8a8a8a] opacity-0 transition hover:bg-[#dedede] hover:text-[#171717] group-hover:opacity-100',
                                                    isPinned && 'opacity-100 text-[#171717]',
                                                )}
                                                aria-label={isPinned ? '取消置顶' : '置顶智能体'}
                                            >
                                                <Pin className={cn('h-3.5 w-3.5', isPinned && 'fill-current')} />
                                            </button>
                                        )}
                                    </div>
                                );
                            })}
                        </div>

                        {isSidebarOpen && (
                            <div className="mt-5 px-3 pb-2 text-xs font-medium text-[#8a8a8a]">业务入口</div>
                        )}
                        <div className="space-y-1">
                            {businessNavItems.map((item) => {
                                const isActive = isActivePath(location.pathname, item.path);
                                return (
                                    <button
                                        key={item.path}
                                        type="button"
                                        onClick={() => navigate(item.path)}
                                        className={cn(
                                            'flex h-10 w-full items-center rounded-lg text-sm transition-colors',
                                            isSidebarOpen ? 'gap-3 px-3 text-left' : 'justify-center px-0',
                                            isActive ? 'bg-[#ececec] text-[#171717]' : 'text-[#333333] hover:bg-[#ececec]',
                                        )}
                                    >
                                        <item.icon className="h-4 w-4 shrink-0" />
                                        {isSidebarOpen && <span className="truncate">{item.label}</span>}
                                    </button>
                                );
                            })}
                        </div>
                    </div>

                    <div className="border-t border-[#e5e5e5] p-2">
                        <div className={cn('flex items-center gap-2 rounded-lg p-2', !isSidebarOpen && 'justify-center')}>
                            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[#111111] text-xs font-semibold text-white">
                                {(user?.full_name || user?.username || '用').slice(0, 1).toUpperCase()}
                            </div>
                            {isSidebarOpen && (
                                <div className="min-w-0 flex-1">
                                    <div className="truncate text-sm font-medium text-[#171717]">{user?.full_name || user?.username || '用户'}</div>
                                    <div className="truncate text-xs text-[#8a8a8a]">个人工作区</div>
                                </div>
                            )}
                            {isSidebarOpen && (
                                <button
                                    type="button"
                                    onClick={handleLogout}
                                    className="flex h-8 w-8 items-center justify-center rounded-lg text-[#6f6f6f] hover:bg-[#ececec] hover:text-[#171717]"
                                    aria-label="退出登录"
                                >
                                    <LogOut className="h-4 w-4" />
                                </button>
                            )}
                        </div>
                        {!isSidebarOpen && (
                            <button
                                type="button"
                                onClick={handleLogout}
                                className="mt-1 flex h-9 w-full items-center justify-center rounded-lg text-[#6f6f6f] hover:bg-[#ececec] hover:text-[#171717]"
                                aria-label="退出登录"
                            >
                                <LogOut className="h-4 w-4" />
                            </button>
                        )}
                    </div>
                </aside>

                <main className="flex min-w-0 flex-1 flex-col bg-white">
                    <div className={cn('flex min-h-0 flex-1 flex-col', usesFixedCanvas ? 'overflow-hidden' : 'overflow-auto')}>
                        <Outlet />
                    </div>
                </main>
            </div>
            <Toaster />
        </div>
    );
}
