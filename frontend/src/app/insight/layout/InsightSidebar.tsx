import { BarChart3, Building2, ChevronDown, FileBarChart, FileText, Home, LogOut, Settings, SlidersHorizontal, Tags } from "lucide-react";
import { NavLink, useNavigate } from "react-router-dom";

import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/store/useAuthStore";

const insightNavItems = [
    { label: "首页看板", path: "/insight", icon: Home },
    { label: "情报中心", path: "/insight/intelligence", icon: FileText },
    { label: "企业档案", path: "/insight/companies", icon: Building2 },
    { label: "监测配置", path: "/insight/monitoring", icon: SlidersHorizontal },
    { label: "分类标签", path: "/insight/tags", icon: Tags },
    { label: "报告中心", path: "/insight/reports", icon: FileBarChart },
    { label: "质量运营", path: "/insight/quality", icon: BarChart3, adminOnly: true },
    { label: "系统设置", path: "/insight/settings", icon: Settings, adminOnly: true },
];

export function InsightSidebar() {
    const user = useAuthStore((state) => state.user);
    const logout = useAuthStore((state) => state.logout);
    const navigate = useNavigate();
    const isAdmin = user?.role === "admin";
    const visibleItems = insightNavItems.filter((item) => !item.adminOnly || isAdmin);
    const displayName = user?.full_name?.trim() || user?.username?.trim() || "当前用户";
    const avatarText = getAvatarText(displayName);

    const handleLogout = () => {
        logout();
        navigate("/insight/login", { replace: true });
    };

    return (
        <aside className="relative hidden h-screen overflow-hidden border-r border-slate-200 bg-white text-slate-800 lg:flex lg:flex-col">
            <div className="relative z-10 flex h-[88px] shrink-0 items-center gap-3 px-5">
                <div className="relative size-11 overflow-hidden rounded-2xl bg-linear-to-br from-blue-600 to-cyan-400 shadow-[0_12px_24px_rgba(37,99,235,0.18)]">
                    <div className="absolute -left-1 top-3 h-8 w-12 rotate-[-32deg] rounded-[100%] bg-white/80" />
                    <div className="absolute bottom-1 right-1 h-8 w-10 rotate-[-28deg] rounded-[100%] bg-emerald-300/90" />
                </div>
                <div className="min-w-0">
                    <div className="truncate text-sm font-black tracking-tight text-slate-950">研发营销市场洞察平台</div>
                    <div className="mt-1 text-sm font-semibold text-slate-600">Insight v1.0</div>
                </div>
            </div>

            <nav className="relative z-10 mt-4 flex flex-1 flex-col gap-2 px-3">
                {visibleItems.map((item) => {
                    const Icon = item.icon;
                    return (
                        <NavLink
                            key={item.path}
                            to={item.path}
                            end={item.path === "/insight"}
                            className={({ isActive }) =>
                                cn(
                                    "flex h-12 items-center gap-3 rounded-xl px-4 text-sm font-bold text-slate-700 transition-colors",
                                    "hover:bg-blue-50 hover:text-blue-700",
                                    isActive && "bg-blue-600 text-white shadow-[0_12px_26px_rgba(29,116,255,0.22)] hover:bg-blue-600 hover:text-white",
                                )
                            }
                        >
                            <Icon className="size-5 shrink-0" />
                            <span className="truncate">{item.label}</span>
                        </NavLink>
                    );
                })}
            </nav>

            <div className="relative z-10 mt-auto border-t border-slate-100 p-3">
                <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                        <button
                            type="button"
                            className="flex w-full min-w-0 items-center gap-3 rounded-xl px-3 py-3 text-left transition hover:bg-slate-50"
                            title={displayName}
                        >
                            <span className="grid size-10 shrink-0 place-items-center rounded-full border border-blue-100 bg-linear-to-br from-blue-100 to-cyan-100 text-sm font-black text-blue-700">
                                {avatarText}
                            </span>
                            <span className="min-w-0 flex-1">
                                <span className="block truncate text-sm font-black text-slate-900">{displayName}</span>
                                <span className="mt-0.5 block truncate text-xs font-semibold text-slate-500">@{user?.username || "user"}</span>
                            </span>
                            <ChevronDown className="size-4 shrink-0 text-slate-400" />
                        </button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent side="right" align="end" className="w-56 rounded-xl border-slate-200 p-2 shadow-xl">
                        <DropdownMenuLabel className="px-3 py-2">
                            <div className="truncate text-sm font-bold text-slate-900">{displayName}</div>
                            <div className="truncate text-xs font-medium text-slate-500">@{user?.username || "user"}</div>
                        </DropdownMenuLabel>
                        <DropdownMenuSeparator />
                        <DropdownMenuItem className="cursor-pointer rounded-lg px-3 py-2 text-red-600 focus:text-red-600" onClick={handleLogout}>
                            <LogOut className="mr-2 size-4" />
                            退出登录
                        </DropdownMenuItem>
                    </DropdownMenuContent>
                </DropdownMenu>
            </div>
        </aside>
    );
}

export function InsightMobileNav() {
    const isAdmin = useAuthStore((state) => state.user?.role === "admin");
    const visibleItems = insightNavItems.filter((item) => !item.adminOnly || isAdmin);

    return (
        <nav className="fixed inset-x-0 bottom-0 z-30 border-t border-slate-200 bg-white/95 px-2 py-2 shadow-[0_-12px_32px_rgba(30,74,120,0.08)] backdrop-blur-xl lg:hidden">
            <div className="mx-auto flex max-w-3xl gap-1 overflow-x-auto">
                {visibleItems.map((item) => {
                    const Icon = item.icon;
                    return (
                        <NavLink
                            key={item.path}
                            to={item.path}
                            end={item.path === "/insight"}
                            className={({ isActive }) =>
                                cn(
                                    "flex h-12 min-w-16 shrink-0 flex-col items-center justify-center gap-1 rounded-xl px-1 text-[10px] font-black leading-none text-slate-500 transition-colors",
                                    "hover:bg-blue-50 hover:text-blue-700",
                                    isActive && "bg-blue-600 text-white shadow-[0_10px_24px_rgba(29,116,255,0.22)] hover:bg-blue-600 hover:text-white",
                                )
                            }
                        >
                            <Icon className="size-4 shrink-0" />
                            <span className="w-full truncate text-center">{item.label}</span>
                        </NavLink>
                    );
                })}
            </div>
        </nav>
    );
}

function getAvatarText(name: string) {
    const first = Array.from(name.trim())[0];
    return first ? first.toUpperCase() : "用";
}
