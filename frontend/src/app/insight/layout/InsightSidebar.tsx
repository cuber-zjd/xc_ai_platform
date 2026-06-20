import { BarChart3, Building2, Database, FileBarChart, FileText, Home, Settings } from "lucide-react";
import { NavLink } from "react-router-dom";

import { cn } from "@/lib/utils";
import { useAuthStore } from "@/store/useAuthStore";

import sidebarLandscape from "../assets/sidebar-landscape.png";

const insightNavItems = [
    { label: "首页看板", path: "/insight", icon: Home },
    { label: "情报中心", path: "/insight/intelligence", icon: FileText },
    { label: "企业档案", path: "/insight/companies", icon: Building2 },
    { label: "报告中心", path: "/insight/reports", icon: FileBarChart },
    { label: "数据源配置", path: "/insight/data-sources", icon: Database },
    { label: "质量运营", path: "/insight/quality", icon: BarChart3, adminOnly: true },
    { label: "系统设置", path: "/insight/settings", icon: Settings, adminOnly: true },
];

export function InsightSidebar() {
    const isAdmin = useAuthStore((state) => state.user?.role === "admin");
    const visibleItems = insightNavItems.filter((item) => !item.adminOnly || isAdmin);

    return (
        <aside className="relative hidden h-screen overflow-hidden border-r border-slate-200 bg-white text-slate-800 lg:flex lg:flex-col">
            <div className="pointer-events-none absolute inset-x-0 bottom-0 h-[46%]">
                <img src={sidebarLandscape} alt="" className="absolute inset-x-0 bottom-0 h-full w-full object-contain object-bottom" />
                <div className="absolute inset-0 bg-linear-to-b from-white via-white/70 to-white/10" />
            </div>

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

            <div className="relative z-10 mt-auto flex min-h-[240px] shrink-0 items-start justify-center px-8 pt-8 text-center">
                <div className="rounded-2xl bg-white/55 px-5 py-3 backdrop-blur-[2px]">
                    <div className="text-lg font-semibold leading-8 text-blue-600">
                        洞察行业趋势
                        <br />
                        驱动研发与增长
                    </div>
                </div>
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
