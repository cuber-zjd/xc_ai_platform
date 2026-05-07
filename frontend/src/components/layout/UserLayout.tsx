import { useEffect, useMemo, useState } from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import {
    BarChart3,
    Briefcase,
    FileCheck,
    LogOut,
    Menu,
    MessageSquare,
    PanelLeftClose,
    PanelLeftOpen,
    Sparkles,
    Wrench,
} from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Toaster } from '@/components/ui/sonner';
import { cn } from '@/lib/utils';
import { useAuthStore } from '@/store/useAuthStore';

const navItems = [
    {
        label: '小助助手',
        icon: MessageSquare,
        path: '/chat-home',
        preview: '智能对话与创作助手',
    },
    {
        label: '工作台',
        icon: Briefcase,
        path: '/workspace',
        preview: '查看今日统计与最近任务',
    },
    {
        label: 'AI 工具箱',
        icon: Wrench,
        path: '/toolbox',
        preview: '探索和使用各类 AI 工具',
    },
    {
        label: '合同审查',
        icon: FileCheck,
        path: '/contracts',
        preview: '智能合同审查与风险提示',
    },
    {
        label: '报表生成',
        icon: BarChart3,
        path: '/fr-ai-reports',
        preview: '对话生成 FineReport 报表并预览',
    },
];

export default function UserLayout() {
    const [isSidebarOpen, setIsSidebarOpen] = useState(true);
    const navigate = useNavigate();
    const location = useLocation();
    const { logout, checkAuth, user } = useAuthStore();

    useEffect(() => {
        checkAuth();
    }, [checkAuth]);

    const currentNav = useMemo(
        () => navItems.find((item) => location.pathname.startsWith(item.path)),
        [location.pathname],
    );
    const hideStageHeader = location.pathname.startsWith('/fr-ai-reports');

    const handleLogout = () => {
        logout();
        navigate('/login');
    };

    return (
        <div className="app-shell">
            <div className="relative z-10 flex min-h-screen gap-4 p-4">
                <aside
                    className={cn(
                        'app-sidebar flex shrink-0 flex-col rounded-[34px] transition-all duration-300',
                        isSidebarOpen ? 'w-[276px]' : 'w-[92px]',
                    )}
                >
                    <div className={cn('flex items-center px-5 pt-5', isSidebarOpen ? 'gap-3' : 'justify-center')}>
                        <div className="flex h-13 w-13 items-center justify-center rounded-[22px] bg-linear-to-br from-[#6d5df6] to-[#8d7dff] text-white shadow-[0_18px_36px_rgba(110,93,247,0.32)]">
                            <Sparkles className="h-6 w-6" />
                        </div>
                        {isSidebarOpen && (
                            <div className="min-w-0">
                                <div className="truncate text-[30px] font-black tracking-[-0.04em] text-[#26243b]">
                                    AI PLATFORM
                                </div>
                                <div className="mt-1 text-[11px] font-bold uppercase tracking-[0.22em] text-[#8b8da5]">
                                    Next Gen Core
                                </div>
                            </div>
                        )}
                        <Button
                            variant="ghost"
                            size="icon"
                            className={cn('ml-auto shrink-0', !isSidebarOpen && 'ml-0')}
                            onClick={() => setIsSidebarOpen((value) => !value)}
                        >
                            {isSidebarOpen ? <PanelLeftClose className="h-4 w-4" /> : <PanelLeftOpen className="h-4 w-4" />}
                        </Button>
                    </div>

                    <div className="px-5 pt-6">
                        {isSidebarOpen ? (
                            <div className="text-[11px] font-bold uppercase tracking-[0.16em] text-[#a0a2b8]">
                                智能应用
                            </div>
                        ) : (
                            <div className="flex justify-center">
                                <Button variant="ghost" size="icon" onClick={() => setIsSidebarOpen(true)}>
                                    <Menu className="h-4 w-4" />
                                </Button>
                            </div>
                        )}
                    </div>

                    <nav className="flex-1 space-y-2 px-4 py-4">
                        {navItems.map((item, index) => {
                            const isActive = location.pathname.startsWith(item.path);
                            return (
                                <button
                                    key={item.path}
                                    type="button"
                                    onClick={() => navigate(item.path)}
                                    className={cn(
                                        'group relative flex w-full items-center overflow-hidden rounded-[24px] border text-left transition-all duration-300',
                                        isSidebarOpen ? 'gap-3 px-3 py-3.5' : 'justify-center px-0 py-3.5',
                                        isActive
                                            ? 'border-transparent bg-linear-to-r from-[#6e5df7] to-[#b48fff] text-white shadow-[0_18px_34px_rgba(110,93,247,0.28)]'
                                            : 'border-white/70 bg-white/38 text-[#62647a] hover:bg-white/68 hover:text-[#25233b]',
                                    )}
                                >
                                    <div
                                        className={cn(
                                            'flex h-11 w-11 shrink-0 items-center justify-center rounded-[18px] transition-all duration-300',
                                            isActive
                                                ? 'bg-white/18 text-white'
                                                : 'bg-white/72 text-[#7d7f96] shadow-[0_8px_18px_rgba(102,99,166,0.06)]',
                                        )}
                                    >
                                        <item.icon className="h-5 w-5" />
                                    </div>
                                    {isSidebarOpen && (
                                        <div className="min-w-0">
                                            <div className="truncate text-[15px] font-bold tracking-tight">{item.label}</div>
                                            <div className={cn('mt-1 truncate text-[12px]', isActive ? 'text-white/72' : 'text-[#9a9cb1]')}>
                                                {item.preview}
                                            </div>
                                        </div>
                                    )}
                                    {isSidebarOpen && !isActive && (
                                        <div className="ml-auto text-[12px] font-bold text-[#b5b7c8]">{`0${index + 1}`}</div>
                                    )}
                                </button>
                            );
                        })}
                    </nav>

                    <div className="p-4">
                        <div className="rounded-[28px] border border-white/80 bg-white/55 p-4 shadow-[0_12px_34px_rgba(102,99,166,0.05)]">
                            <div className={cn('flex items-center gap-3', !isSidebarOpen && 'justify-center')}>
                                <div className="relative">
                                    <div className="flex h-12 w-12 items-center justify-center rounded-[18px] bg-[#f0f2ff] text-sm font-black text-[#4f5aa8]">
                                        {(user?.full_name || user?.username || 'U').charAt(0).toUpperCase()}
                                    </div>
                                    <div className="absolute -bottom-0.5 -right-0.5 h-4 w-4 rounded-full border-2 border-white bg-emerald-400" />
                                </div>
                                {isSidebarOpen && (
                                    <div className="min-w-0">
                                        <div className="truncate text-sm font-black text-[#24233b]">{user?.full_name || user?.username}</div>
                                        <div className="mt-1 text-[11px] font-bold uppercase tracking-[0.14em] text-[#9ea0b5]">
                                            Access Granted
                                        </div>
                                    </div>
                                )}
                            </div>

                            <Button
                                variant="outline"
                                className={cn('mt-4 w-full text-[#ef4444] hover:text-[#dc2626]', !isSidebarOpen && 'mt-3 px-0')}
                                onClick={handleLogout}
                            >
                                <LogOut className="h-4 w-4" />
                                {isSidebarOpen && '退出登录'}
                            </Button>
                        </div>
                    </div>
                </aside>

                <main className="flex min-w-0 flex-1 flex-col">
                    <div className="app-stage flex min-h-[calc(100vh-2rem)] flex-1 flex-col rounded-[38px] p-3">
                        {!hideStageHeader ? (
                            <header className="app-panel-soft flex items-center justify-between gap-4 px-5 py-4">
                                <div>
                                    <div className="app-kicker">智能工作区</div>
                                    <h1 className="mt-3 text-[30px] font-black tracking-[-0.04em] text-[#24233b]">
                                        {currentNav?.label ?? 'AI Platform'}
                                    </h1>
                                    <p className="mt-1 text-sm text-[#7a7d92]">{currentNav?.preview ?? '统一的智能应用工作台体验'}</p>
                                </div>
                            </header>
                        ) : null}

                        <div className="min-h-0 flex-1 overflow-auto">
                            <Outlet />
                        </div>
                    </div>
                </main>
            </div>
            <Toaster />
        </div>
    );
}
