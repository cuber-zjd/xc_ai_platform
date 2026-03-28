import { useState, useEffect } from 'react';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import {
    MessageSquare,
    Briefcase,
    Wrench,
    FileCheck,
    LogOut,
    Menu,
    Sparkles,
    Settings
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { useAuthStore } from '@/store/useAuthStore';
import { Toaster } from "@/components/ui/sonner";

/** 
 * 普通用户布局 - 彻底重构为高级毛玻璃 (Glassmorphism) 全局风格布局
 */
export default function UserLayout() {
    const [isSidebarOpen, setIsSidebarOpen] = useState(true);
    const navigate = useNavigate();
    const location = useLocation();
    const { logout, checkAuth, user } = useAuthStore();

    useEffect(() => {
        checkAuth();
    }, [checkAuth]);

    const navItems = [
        { label: '小驰助手', icon: MessageSquare, path: '/chat-home', preview: '智能助手随时待命...' },
        { label: '工作台', icon: Briefcase, path: '/workspace', preview: '查看今日统计与最近任务...' },
        { label: 'AI 工具箱', icon: Wrench, path: '/toolbox', preview: '各种效率工具集锦...' },
        { label: '合同智审', icon: FileCheck, path: '/contracts', preview: '智能合同审查与风险提示...' },
    ];

    const handleLogout = () => {
        logout();
        navigate('/login');
    };

    return (
        <div className="flex h-screen w-screen bg-[#fcfdfe] relative overflow-hidden font-sans text-neutral-800 selection:bg-black/10">
            {/* 极致高级动态波浪光晕背景 */}
            <div className="absolute inset-0 z-0 overflow-hidden pointer-events-none">
                {/* 动态光晕 1 */}
                <div className="absolute top-[-10%] left-[-10%] w-[50%] h-[50%] bg-blue-100/40 rounded-full mix-blend-multiply filter blur-[100px] animate-blob" />
                {/* 动态光晕 2 */}
                <div className="absolute top-[10%] right-[-5%] w-[45%] h-[45%] bg-purple-100/30 rounded-full mix-blend-multiply filter blur-[100px] animate-blob animation-delay-2000" />
                {/* 动态光晕 3 */}
                <div className="absolute bottom-[-10%] left-[20%] w-[50%] h-[50%] bg-pink-100/20 rounded-full mix-blend-multiply filter blur-[100px] animate-blob animation-delay-4000" />
                
                {/* 叠加微弱网格纹理以增加细节感 */}
                <div className="absolute inset-0 opacity-[0.03]" 
                    style={{ backgroundImage: `radial-gradient(#000 0.5px, transparent 0.5px)`, backgroundSize: '24px 24px' }} 
                />
            </div>

            <style dangerouslySetInnerHTML={{ __html: `
                @keyframes blob {
                    0% { transform: translate(0px, 0px) scale(1); }
                    33% { transform: translate(30px, -50px) scale(1.1); }
                    66% { transform: translate(-20px, 20px) scale(0.9); }
                    100% { transform: translate(0px, 0px) scale(1); }
                }
                .animate-blob {
                    animation: blob 7s infinite;
                }
                .animation-delay-2000 {
                    animation-delay: 2s;
                }
                .animation-delay-4000 {
                    animation-delay: 4s;
                }
            `}} />

            {/* 左侧悬浮侧边栏 - 极致玻璃拟合 */}
            <aside
                className={cn(
                    "my-4 ml-4 bg-white/40 backdrop-blur-[40px] border border-white/80 flex flex-col z-20 shrink-0",
                    "shadow-[0_8px_32px_rgba(0,0,0,0.04),inset_0_1px_1px_rgba(255,255,255,1)] rounded-[32px] transition-all duration-500 ease-in-out",
                    isSidebarOpen ? "w-72" : "w-20"
                )}
            >
                {/* 顶部标题栏 */}
                <div className={cn(
                    "h-24 flex items-center shrink-0 transition-all duration-300",
                    isSidebarOpen ? "px-7 gap-4" : "justify-center"
                )}>
                    {isSidebarOpen ? (
                        <div className="flex items-center gap-3 group cursor-default">
                            <div className="bg-zinc-900 p-2.5 rounded-2xl flex items-center justify-center shadow-lg group-hover:scale-110 transition-transform duration-500">
                                <Sparkles className="h-5 w-5 text-white" />
                            </div>
                            <div className="flex flex-col">
                                <span className="font-black text-[18px] tracking-tight text-zinc-900 leading-none">
                                    AI PLATFORM
                                </span>
                                <span className="text-[10px] font-bold text-zinc-400 tracking-[0.2em] mt-1.5 uppercase">
                                    Next Gen Core
                                </span>
                            </div>
                        </div>
                    ) : (
                        <Button
                            variant="ghost"
                            size="icon"
                            className="h-10 w-10 rounded-2xl bg-zinc-900/5 hover:bg-zinc-900/10 text-zinc-900 transition-all duration-300"
                            onClick={() => setIsSidebarOpen(true)}
                        >
                            <Menu className="h-5 w-5" />
                        </Button>
                    )}
                    
                    {isSidebarOpen && (
                        <Button
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8 text-zinc-300 hover:text-zinc-900 ml-auto transition-colors"
                            onClick={() => setIsSidebarOpen(false)}
                        >
                             <Menu className="h-4 w-4" />
                        </Button>
                    )}
                </div>

                {/* 导航列表区 */}
                <div className="flex-1 overflow-y-auto px-4 py-4 space-y-8 scrollbar-none">
                    <div className="space-y-2">
                        {isSidebarOpen && (
                            <div className="px-3 mb-4">
                                <span className="text-[10px] font-extrabold text-zinc-400 tracking-[0.15em] uppercase">智能应用</span>
                            </div>
                        )}
                        <div className="space-y-1.5">
                            {navItems.map((item) => {
                                const isActive = location.pathname.startsWith(item.path);
                                return (
                                    <button
                                        key={item.path}
                                        onClick={() => navigate(item.path)}
                                        className={cn(
                                            "w-full flex items-center gap-3 rounded-2xl transition-all duration-300 cursor-pointer group relative overflow-hidden",
                                            isSidebarOpen ? "p-3.5 text-left" : "p-3.5 justify-center",
                                            isActive
                                                ? "bg-zinc-900 text-white shadow-[0_10px_20px_rgba(0,0,0,0.1)] scale-[1.02]"
                                                : "hover:bg-white/60 text-zinc-600 hover:text-zinc-900"
                                        )}
                                    >
                                        <div className={cn(
                                            "flex items-center justify-center shrink-0 w-9 h-9 rounded-xl transition-all duration-500",
                                            isActive ? "bg-white/20" : "bg-white/50 group-hover:bg-white group-hover:shadow-sm"
                                        )}>
                                            <item.icon className={cn("h-4.5 w-4.5", isActive ? "text-white" : "text-zinc-500 group-hover:text-zinc-900")} />
                                        </div>

                                        {isSidebarOpen && (
                                            <div className="flex flex-col overflow-hidden">
                                                <span className={cn("text-[14px] font-bold tracking-tight", isActive ? "text-white" : "text-zinc-700")}>
                                                    {item.label}
                                                </span>
                                                <span className={cn("text-[11px] truncate leading-tight mt-0.5", isActive ? "text-white/60" : "text-zinc-400 group-hover:text-zinc-500 font-medium")}>
                                                    {item.preview}
                                                </span>
                                            </div>
                                        )}
                                        {isActive && !isSidebarOpen && (
                                            <div className="absolute right-1 top-1/2 -translate-y-1/2 w-1 h-4 rounded-full bg-white/40" />
                                        )}
                                    </button>
                                );
                            })}
                        </div>
                    </div>
                </div>

                {/* 底部用户信息栏 - 悬浮卡片风格 */}
                <div className="p-4 mt-auto">
                    <div className={cn(
                        "bg-white/30 backdrop-blur-xl border border-white/60 rounded-[24px] transition-all duration-300 overflow-hidden",
                        isSidebarOpen ? "p-4" : "p-2",
                        "shadow-[0_4px_12px_rgba(0,0,0,0.02)]"
                    )}>
                        {isSidebarOpen && (
                            <div className="flex items-center gap-4 mb-4">
                                <div className="relative shrink-0">
                                    <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-zinc-900 text-white text-sm font-black shadow-md">
                                        {(user?.full_name || user?.username || 'U').charAt(0).toUpperCase()}
                                    </div>
                                    <div className="absolute -bottom-1 -right-1 w-4 h-4 rounded-full bg-green-500 border-2 border-white" />
                                </div>
                                <div className="flex-1 min-w-0">
                                    <div className="text-[14px] font-black text-zinc-900 truncate tracking-tight">
                                        {user?.full_name || user?.username}
                                    </div>
                                    <div className="text-[10px] font-bold text-zinc-400 uppercase tracking-wider mt-0.5">
                                        {user?.role === 'admin' ? 'Administrator' : 'Access Granted'}
                                    </div>
                                </div>
                            </div>
                        )}

                        <div className="flex gap-2">
                            {isSidebarOpen && (
                                <button className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-xl bg-white/60 hover:bg-white text-zinc-600 hover:text-zinc-900 transition-all text-[11px] font-bold border border-white/50">
                                    <Settings className="h-3.5 w-3.5" />
                                    Account
                                </button>
                            )}
                            <button
                                onClick={handleLogout}
                                className={cn(
                                    "flex items-center justify-center gap-2 py-2.5 rounded-xl transition-all border",
                                    isSidebarOpen 
                                        ? "flex-1 bg-red-50/30 hover:bg-red-50 text-red-500 border-red-100/50 hover:border-red-100 text-[11px] font-bold" 
                                        : "w-full bg-red-50 text-red-500 border-red-100 p-2"
                                )}
                                title={!isSidebarOpen ? "退出登录" : undefined}
                            >
                                <LogOut className="h-3.5 w-3.5" />
                                {isSidebarOpen && <span>Logout</span>}
                            </button>
                        </div>
                    </div>
                </div>
            </aside>

            {/* 主内容区域 */}
            <main className="flex-1 flex flex-col min-w-0 relative z-10 h-full p-4 pl-6 overflow-hidden">
                <div className="flex-1 overflow-hidden rounded-[40px] bg-white/20 backdrop-blur-sm border border-white/40 shadow-[0_12px_40px_rgba(0,0,0,0.03)] flex flex-col">
                    <div className="flex-1 overflow-auto scrollbar-none p-2 relative">
                        {/* 用于页面内容的微弱内阴影，增加深度感 */}
                        <div className="absolute inset-0 pointer-events-none rounded-[40px] shadow-[inset_0_2px_10px_rgba(0,0,0,0.02)]" />
                        <Outlet />
                    </div>
                </div>
            </main>
            <Toaster />
        </div>
    );
}
