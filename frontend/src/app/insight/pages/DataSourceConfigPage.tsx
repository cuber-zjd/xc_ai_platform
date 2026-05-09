import { AlertTriangle, ClipboardList, Database, PieChart } from "lucide-react";

import { Button } from "@/components/ui/button";

import { DemoCard, FilterSelect, SearchField, SourceIcon, StatCard, StatusPill } from "../components/DemoPrimitives";
import { PageContainer } from "../layout/PageContainer";

const sources = [
    ["禹王集团官网", "官网", "爬虫", "每 6 小时"],
    ["中粮科技公告", "公告", "API", "每 2 小时"],
    ["巨潮资讯", "资讯", "API", "每 15 分钟"],
    ["Foodaily资讯", "资讯", "爬虫", "每 1 小时"],
    ["奈雪公众号", "公众号", "爬虫", "每 2 小时"],
    ["瑞幸公众号", "公众号", "爬虫", "每 2 小时"],
    ["京东新品监控", "电商", "RPA", "每 4 小时"],
    ["淘宝新品监控", "电商", "RPA", "每 4 小时"],
];

export function DataSourceConfigPage() {
    return (
        <PageContainer>
            <h1 className="text-3xl font-black tracking-tight text-slate-950">数据源配置</h1>

            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
                <StatCard title="已启用数据源" value="12" compare="较昨日" delta="+1" icon={<Database className="size-7" />} />
                <StatCard title="今日采集任务" value="24" compare="较昨日" delta="+6" tone="cyan" icon={<ClipboardList className="size-7" />} />
                <StatCard title="成功率" value="92%" compare="较昨日" delta="+3%" icon={<PieChart className="size-7" />} />
                <StatCard title="异常源" value="2" compare="较昨日" delta="+1" tone="red" icon={<AlertTriangle className="size-7" />} />
            </div>

            <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_0.9fr]">
                <DemoCard className="p-5">
                    <div className="mb-4 flex items-center justify-between gap-4">
                        <h2 className="text-xl font-black text-slate-900">数据源列表</h2>
                        <Button className="rounded-xl bg-blue-600 text-white hover:bg-blue-700">+ 新增数据源</Button>
                    </div>
                    <div className="mb-4 flex gap-3">
                        <div className="w-56">
                            <SearchField placeholder="搜索来源名称" />
                        </div>
                        <FilterSelect label="" value="全部类型" />
                        <FilterSelect label="" value="全部状态" />
                    </div>
                    <div className="overflow-hidden rounded-xl border border-slate-200">
                        <table className="w-full text-left text-sm">
                            <thead className="bg-slate-50 text-slate-500">
                                <tr>
                                    {["来源名称", "类型", "抓取方式", "更新频率", "状态"].map((head) => (
                                        <th key={head} className="px-4 py-3 font-bold">
                                            {head}
                                        </th>
                                    ))}
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-100">
                                {sources.map((row, index) => (
                                    <tr key={row[0]} className={index === 3 ? "bg-blue-50 outline outline-1 outline-blue-200" : "hover:bg-blue-50/40"}>
                                        <td className="px-4 py-4">
                                            <div className="flex items-center gap-3">
                                                <div className="flex size-10 items-center justify-center rounded-lg bg-blue-50 text-blue-600">
                                                    <SourceIcon type={index % 2 === 0 ? "database" : "file"} />
                                                </div>
                                                <span className={index === 3 ? "font-black text-blue-600" : "font-bold text-slate-800"}>{row[0]}</span>
                                            </div>
                                        </td>
                                        <td className="px-4 py-4 text-slate-700">{row[1]}</td>
                                        <td className="px-4 py-4 text-slate-700">{row[2]}</td>
                                        <td className="px-4 py-4 text-slate-700">{row[3]}</td>
                                        <td className="px-4 py-4">
                                            <StatusPill />
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                    <div className="mt-5 flex items-center justify-between text-sm text-slate-500">
                        <span>共 8 条</span>
                        <span className="rounded-full bg-blue-600 px-4 py-2 font-bold text-white">1</span>
                    </div>
                </DemoCard>

                <div className="space-y-4">
                    <DemoCard className="p-5">
                        <h2 className="mb-5 text-xl font-black text-slate-900">数据源配置 - Foodaily资讯</h2>
                        <div className="space-y-4">
                            {[
                                ["来源名称", "Foodaily资讯"],
                                ["来源URL", "https://www.foodaily.com/latest"],
                                ["来源类型", "资讯"],
                                ["抓取方式", "爬虫"],
                            ].map(([label, value]) => (
                                <div key={label} className="grid grid-cols-[120px_minmax(0,1fr)] items-center gap-4">
                                    <span className="font-bold text-slate-600">{label}</span>
                                    <div className="rounded-lg border border-slate-200 bg-white px-4 py-3 font-semibold text-slate-700">{value}</div>
                                </div>
                            ))}
                            <div className="grid grid-cols-[120px_minmax(0,1fr)] items-center gap-4">
                                <span className="font-bold text-slate-600">更新时间规则</span>
                                <div className="flex items-center gap-3 text-sm font-semibold text-slate-700">
                                    每 <span className="rounded-lg border border-slate-200 px-5 py-2">1</span> 小时 在 <span className="rounded-lg border border-slate-200 px-5 py-2">00:00</span>
                                </div>
                            </div>
                            <div className="grid grid-cols-[120px_minmax(0,1fr)] items-center gap-4">
                                <span className="font-bold text-slate-600">启用状态</span>
                                <StatusPill />
                            </div>
                        </div>
                        <div className="mt-6 flex gap-3 border-t border-slate-100 pt-5">
                            <Button className="rounded-xl bg-blue-600 text-white hover:bg-blue-700">保存配置</Button>
                            <Button variant="outline" className="rounded-xl border-blue-200 bg-white text-blue-600 shadow-none">立即测试</Button>
                            <Button variant="outline" className="rounded-xl border-blue-200 bg-white text-blue-600 shadow-none">查看日志</Button>
                        </div>
                    </DemoCard>

                    <DemoCard className="p-5">
                        <div className="mb-5 flex items-center justify-between">
                            <h2 className="text-xl font-black text-slate-900">最近任务日志</h2>
                            <button type="button" className="text-sm font-bold text-blue-600">查看更多</button>
                        </div>
                        <div className="space-y-4">
                            {[
                                ["数据采集成功，新增 56 条，更新 132 条", "2025-05-21 13:00:12", true],
                                ["数据采集成功，新增 48 条，更新 98 条", "2025-05-21 12:00:11", true],
                                ["数据采集成功，新增 62 条，更新 110 条", "2025-05-21 11:00:09", true],
                                ["部分内容抓取失败，已自动重试（失败 3 条）", "2025-05-21 10:00:08", false],
                                ["数据采集成功，新增 70 条，更新 125 条", "2025-05-21 09:00:07", true],
                            ].map(([text, time, ok]) => (
                                <div key={text as string} className="flex items-center justify-between gap-4 border-b border-slate-100 pb-3 last:border-0">
                                    <span className="inline-flex items-center gap-3 text-sm font-semibold text-slate-700">
                                        <span className={ok ? "flex size-6 items-center justify-center rounded-full bg-emerald-500 text-white" : "flex size-6 items-center justify-center rounded-full bg-amber-500 text-white"}>
                                            {ok ? "✓" : "!"}
                                        </span>
                                        {text}
                                    </span>
                                    <span className="text-sm text-slate-500">{time}</span>
                                </div>
                            ))}
                        </div>
                    </DemoCard>
                </div>
            </div>
        </PageContainer>
    );
}
