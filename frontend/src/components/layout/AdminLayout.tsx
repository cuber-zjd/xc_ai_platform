import { useEffect, useMemo, useState } from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import {
    BarChart3,
    Bot,
    BrainCircuit,
    ChevronLeft,
    ChevronRight,
    LayoutDashboard,
    LogOut,
    Search,
    ServerCog,
    Settings,
    Shield,
    Sparkles,
    Users,
} from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Toaster } from '@/components/ui/sonner';
import { cn } from '@/lib/utils';
import { useAuthStore } from '@/store/useAuthStore';

const navItems = [
    { label: '仪表盘', icon: LayoutDashboard, path: '/admin/dashboard', preview: '查看平台运行概览' },
    { label: '用户管理', icon: Users, path: '/admin/users', preview: '维护账号、角色与组织' },
    { label: '智能体配置', icon: Bot, path: '/admin/agents', preview: '配置智能体入口与授权' },
    { label: '模型管理', icon: BrainCircuit, path: '/admin/models', preview: '维护模型供应商和参数' },
    { label: '权限管理', icon: Shield, path: '/admin/permissions', preview: '管理角色和访问边界' },
    { label: '报表生成', icon: BarChart3, path: '/admin/fr-ai-reports', preview: 'FineReport 生成工作流' },
    { label: 'SAP 系统', icon: ServerCog, path: '/admin/sap-systems', preview: '维护 RFC 连接配置' },
    { label: '系统设置', icon: Settings, path: '/admin/settings', preview: '平台开关与基础参数' },
];

const isActivePath = (pathname: string, path: string) => pathname === path || pathname.startsWith(`${path}/`);

export default function AdminLayout() {
    const [isSidebarOpen, setIsSidebarOpen] = useState(true);
    const navigate = useNavigate();
    const location = useLocation();
    const { logout, checkAuth, user } = useAuthStore();

    useEffect(() => {
        void checkAuth();
    }, [checkAuth]);

    const currentNav = useMemo(
        () => navItems.find((item) => isActivePath(location.pathname, item.path)),
        [location.pathname],
    );

    const handleLogout = () => {
        logout();
        navigate('/login');
    };

    return (
        <div className="app-shell bg-white text-[#171717]">
            <div className="flex min-h-screen">
                <aside
                    className={cn(
                        'flex shrink-0 flex-col border-r border-[#e5e5e5] bg-[#f7f7f7] transition-all duration-200',
                        isSidebarOpen ? 'w-[272px]' : 'w-[72px]',
                    )}
                >
                    <div className="flex h-14 items-center gap-2 px-3">
                        <button
                            type="button"
                            onClick={() => navigate('/admin/dashboard')}
                            className={cn(
                                'flex h-9 min-w-0 items-center rounded-lg px-2 text-left text-sm font-semibold text-[#171717] hover:bg-[#ececec]',
                                isSidebarOpen ? 'flex-1 gap-2' : 'justify-center',
                            )}
                        >
                            <Sparkles className="h-4 w-4 shrink-0" />
                            {isSidebarOpen && <span className="truncate">管理后台</span>}
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

                    <div className="px-2 pb-2">
                        <button
                            type="button"
                            onClick={() => navigate('/admin/agents')}
                            className={cn(
                                'flex h-10 w-full items-center rounded-lg text-sm text-[#333333] transition-colors hover:bg-[#ececec]',
                                isSidebarOpen ? 'gap-3 px-3 text-left' : 'justify-center px-0',
                            )}
                        >
                            <Search className="h-4 w-4 shrink-0" />
                            {isSidebarOpen && <span className="truncate">搜索配置</span>}
                        </button>
                    </div>

                    <nav className="min-h-0 flex-1 space-y-1 overflow-y-auto px-2 py-2">
                        {isSidebarOpen && <div className="px-3 pb-2 text-xs font-medium text-[#8a8a8a]">平台管理</div>}
                        {navItems.map((item) => {
                            const isActive = isActivePath(location.pathname, item.path);
                            return (
                                <button
                                    key={item.path}
                                    type="button"
                                    onClick={() => navigate(item.path)}
                                    className={cn(
                                        'flex h-10 w-full min-w-0 items-center rounded-lg text-sm transition-colors',
                                        isSidebarOpen ? 'gap-3 px-3 text-left' : 'justify-center px-0',
                                        isActive ? 'bg-[#ececec] text-[#171717]' : 'text-[#333333] hover:bg-[#ececec]',
                                    )}
                                    title={item.label}
                                >
                                    <item.icon className="h-4 w-4 shrink-0" />
                                    {isSidebarOpen && <span className="truncate">{item.label}</span>}
                                </button>
                            );
                        })}
                    </nav>

                    <div className="border-t border-[#e5e5e5] p-2">
                        <div className={cn('flex items-center gap-2 rounded-lg p-2', !isSidebarOpen && 'justify-center')}>
                            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[#111111] text-xs font-semibold text-white">
                                {(user?.full_name || user?.username || '管').slice(0, 1).toUpperCase()}
                            </div>
                            {isSidebarOpen && (
                                <div className="min-w-0 flex-1">
                                    <div className="truncate text-sm font-medium text-[#171717]">{user?.full_name || user?.username || '管理员'}</div>
                                    <div className="truncate text-xs text-[#8a8a8a]">管理员</div>
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
                    <header className="flex h-14 shrink-0 items-center justify-between border-b border-[#ececec] px-5">
                        <div className="min-w-0">
                            <h1 className="truncate text-sm font-semibold text-[#171717]">{currentNav?.label ?? '管理后台'}</h1>
                            <p className="truncate text-xs text-[#8a8a8a]">{currentNav?.preview ?? '平台配置与治理空间'}</p>
                        </div>
                    </header>
                    <div className="min-h-0 flex-1 overflow-auto">
                        <Outlet />
                    </div>
                </main>
            </div>
            <Toaster />
        </div>
    );
}
