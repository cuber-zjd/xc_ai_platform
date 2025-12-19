import { useState, useEffect } from 'react';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import {
    LayoutDashboard,
    MessageSquare,
    Settings,
    LogOut,
    Menu,
    X,
    User
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { useAuthStore } from '@/store/useAuthStore';
import { Toaster } from "@/components/ui/sonner";

export default function MainLayout() {
    const [isSidebarOpen, setIsSidebarOpen] = useState(true);
    const navigate = useNavigate();
    const location = useLocation();
    const { logout, checkAuth } = useAuthStore();

    useEffect(() => {
        checkAuth();
    }, [checkAuth]);

    const navItems = [
        { label: '仪表盘', icon: LayoutDashboard, path: '/dashboard' },
        { label: '对话', icon: MessageSquare, path: '/chat' },
        { label: '用户管理', icon: User, path: '/users' },
        { label: '系统设置', icon: Settings, path: '/settings' },
    ];

    const handleLogout = () => {
        logout();
        navigate('/login');
    };

    return (
        <div className="flex h-screen bg-background text-foreground overflow-hidden">
            {/* Sidebar */}
            <aside
                className={cn(
                    "bg-zinc-50 dark:bg-zinc-900 border-r border-border transition-all duration-300 flex flex-col z-50",
                    isSidebarOpen ? "w-64" : "w-16"
                )}
            >
                <div className="h-16 flex items-center justify-between px-4 border-b border-border">
                    {isSidebarOpen && (
                        <span className="font-semibold text-lg truncate">AI 智能平台</span>
                    )}
                    <Button
                        variant="ghost"
                        size="icon"
                        className="ml-auto"
                        onClick={() => setIsSidebarOpen(!isSidebarOpen)}
                    >
                        {isSidebarOpen ? <X className="h-4 w-4" /> : <Menu className="h-4 w-4" />}
                    </Button>
                </div>

                <nav className="flex-1 p-2 space-y-1 overflow-y-auto">
                    {navItems.map((item) => (
                        <Button
                            key={item.path}
                            variant={location.pathname.startsWith(item.path) ? "secondary" : "ghost"}
                            className={cn(
                                "w-full justify-start",
                                !isSidebarOpen && "justify-center px-0"
                            )}
                            onClick={() => navigate(item.path)}
                        >
                            <item.icon className={cn("h-5 w-5", isSidebarOpen && "mr-2")} />
                            {isSidebarOpen && <span>{item.label}</span>}
                        </Button>
                    ))}
                </nav>

                <div className="p-2 border-t border-border mt-auto">
                    <Button
                        variant="ghost"
                        className={cn("w-full justify-start text-red-500 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-900/10", !isSidebarOpen && "justify-center px-0")}
                        onClick={handleLogout}
                    >
                        <LogOut className={cn("h-5 w-5", isSidebarOpen && "mr-2")} />
                        {isSidebarOpen && <span>退出登录</span>}
                    </Button>
                </div>
            </aside>

            {/* Main Content */}
            <main className="flex-1 flex flex-col min-w-0 overflow-hidden relative">
                {/* Header */}
                <header className="h-16 border-b border-border flex items-center px-6 bg-background/80 backdrop-blur-sm z-10 justify-between">
                    <div className="flex items-center gap-4">
                        <h1 className="text-xl font-semibold capitalize">
                            {location.pathname.split('/')[1] || 'Dashboard'}
                        </h1>
                    </div>
                    <div className="flex items-center gap-2">
                        <Button variant="ghost" size="icon" className="rounded-full">
                            <User className="h-5 w-5" />
                        </Button>
                    </div>
                </header>

                {/* Content Scroll Area */}
                <div className="flex-1 overflow-auto p-6 scroll-smooth">
                    <Outlet />
                </div>
            </main>
            <Toaster />
        </div>
    );
}
