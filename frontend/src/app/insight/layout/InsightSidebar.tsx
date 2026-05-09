import { Building2, Database, FileBarChart, FileText, Home, Settings } from "lucide-react";
import { NavLink } from "react-router-dom";

import { cn } from "@/lib/utils";

const navItems = [
    { label: "首页看板", path: "/insight", icon: Home },
    { label: "情报中心", path: "/insight/intelligence", icon: FileText },
    { label: "企业档案", path: "/insight/companies", icon: Building2 },
    { label: "报告中心", path: "/insight/reports", icon: FileBarChart },
    { label: "数据源配置", path: "/insight/data-sources", icon: Database },
    { label: "系统设置", path: "/insight/settings", icon: Settings },
];

export function InsightSidebar() {
    return (
        <aside className="sticky top-0 hidden h-screen border-r border-slate-200 bg-white text-slate-800 lg:flex lg:flex-col">
            <div className="flex h-[88px] items-center gap-3 px-7">
                <div className="relative size-11 overflow-hidden rounded-2xl bg-linear-to-br from-blue-600 to-cyan-400">
                    <div className="absolute -left-1 top-3 h-8 w-12 rotate-[-32deg] rounded-[100%] bg-white/80" />
                    <div className="absolute bottom-1 right-1 h-8 w-10 rotate-[-28deg] rounded-[100%] bg-emerald-300/90" />
                </div>
                <div>
                    <div className="text-lg font-black tracking-tight text-slate-950">研发营销市场洞察平台</div>
                    <div className="mt-1 text-sm font-semibold text-slate-700">Demo v1.0</div>
                </div>
            </div>

            <nav className="mt-5 flex flex-1 flex-col gap-3 px-5">
                {navItems.map((item) => {
                    const Icon = item.icon;
                    return (
                        <NavLink
                            key={item.path}
                            to={item.path}
                            end={item.path === "/insight"}
                            className={({ isActive }) =>
                                cn(
                                    "flex h-[52px] items-center gap-4 rounded-xl px-5 text-lg font-bold text-slate-700 transition-colors",
                                    "hover:bg-blue-50 hover:text-blue-700",
                                    isActive && "bg-blue-600 text-white shadow-[0_12px_26px_rgba(29,116,255,0.24)] hover:bg-blue-600 hover:text-white",
                                )
                            }
                        >
                            <Icon className="size-5" />
                            <span>{item.label}</span>
                        </NavLink>
                    );
                })}
            </nav>

            <div className="relative mx-0 h-80 overflow-hidden bg-linear-to-b from-transparent to-blue-50 px-8 pb-8 text-center">
                <div className="absolute inset-x-0 bottom-0 h-44 bg-[radial-gradient(ellipse_at_center,rgba(29,116,255,0.12),transparent_62%)]" />
                <div className="relative mt-12 text-lg font-semibold leading-8 text-blue-500">
                    洞察行业趋势
                    <br />
                    驱动研发与增长
                </div>
                <div className="absolute bottom-0 left-0 right-0 h-36">
                    <div className="absolute bottom-0 left-0 right-0 h-28 bg-blue-100/70 [clip-path:polygon(0_48%,18%_28%,36%_52%,54%_22%,78%_48%,100%_18%,100%_100%,0_100%)]" />
                    <div className="absolute bottom-0 left-0 right-0 h-20 bg-blue-200/55 [clip-path:polygon(0_42%,24%_18%,48%_48%,68%_25%,100%_55%,100%_100%,0_100%)]" />
                    <div className="absolute bottom-7 left-[68px] h-14 w-24 rounded-t bg-white/80 shadow-sm" />
                    <div className="absolute bottom-7 left-44 h-20 w-5 rounded-t bg-blue-300/75" />
                    <div className="absolute bottom-7 left-52 h-11 w-16 rounded-t bg-white/75 shadow-sm" />
                </div>
            </div>
        </aside>
    );
}
