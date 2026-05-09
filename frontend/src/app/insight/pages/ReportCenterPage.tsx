import { CalendarDays, Download, FileText } from "lucide-react";

import { Button } from "@/components/ui/button";

import {
    DemoCard,
    DemoTag,
    DonutChart,
    LinkButton,
    MiniLineChart,
    PrimaryAction,
    RankList,
    SearchField,
    SectionHeader,
    SuggestionList,
} from "../components/DemoPrimitives";
import { PageContainer } from "../layout/PageContainer";

const histories = ["《2025年第21周市场洞察周报》", "《2025年第20周市场洞察周报》", "《2025年第19周市场洞察周报》", "《5月20日日报》", "《5月19日日报》", "《茶饮客户新品专题报告》", "《植物基蛋白行业月报（5月）》", "《胶原蛋白市场分析报告》"];

export function ReportCenterPage() {
    return (
        <PageContainer>
            <h1 className="text-3xl font-black tracking-tight text-slate-950">报告中心</h1>

            <DemoCard className="p-5">
                <div className="flex flex-wrap items-center gap-8">
                    <div className="flex items-center gap-4">
                        <span className="font-bold text-slate-700">报告时间</span>
                        <button type="button" className="inline-flex h-11 items-center gap-4 rounded-xl border border-slate-200 px-4 font-semibold text-slate-600">
                            2025-05-12 ~ 2025-05-18
                            <CalendarDays className="size-4" />
                        </button>
                    </div>
                    <div className="flex items-center gap-4">
                        <span className="font-bold text-slate-700">报告对象</span>
                        <button type="button" className="h-11 rounded-xl border border-slate-200 px-8 font-semibold text-slate-600">全部行业</button>
                    </div>
                    <div className="ml-auto flex gap-3">
                        <PrimaryAction>生成报告</PrimaryAction>
                        <Button variant="outline" className="h-11 rounded-xl border-slate-200 bg-white shadow-none">
                            <Download className="size-4" />
                            导出Word
                        </Button>
                        <Button variant="outline" className="h-11 rounded-xl border-slate-200 bg-white shadow-none text-red-600">
                            <FileText className="size-4" />
                            导出PDF
                        </Button>
                    </div>
                </div>
            </DemoCard>

            <div className="grid gap-4 xl:grid-cols-[320px_minmax(0,1fr)]">
                <DemoCard className="p-5">
                    <SectionHeader title="报告历史" action="" />
                    <SearchField placeholder="搜索报告名称" />
                    <div className="mt-4 space-y-2">
                        {histories.map((item, index) => (
                            <div key={item} className={index === 0 ? "rounded-xl border border-blue-200 bg-blue-50 p-3" : "rounded-xl border border-transparent p-3 hover:bg-slate-50"}>
                                <div className="flex items-center justify-between gap-3">
                                    <div className="truncate text-sm font-bold text-slate-800">{item}</div>
                                    <DemoTag tone={index < 6 ? "green" : "orange"}>{index < 6 ? "已生成" : "草稿"}</DemoTag>
                                </div>
                                <div className="mt-2 text-xs text-slate-500">2025-05-{19 - index} 生成</div>
                            </div>
                        ))}
                    </div>
                    <div className="mt-10 text-center">
                        <LinkButton>查看全部报告（128）</LinkButton>
                    </div>
                </DemoCard>

                <div className="space-y-4">
                    <DemoCard className="overflow-hidden">
                        <div className="bg-linear-to-r from-blue-50 to-cyan-50 p-8">
                            <h2 className="text-4xl font-black tracking-tight text-slate-950">2025年第21周市场洞察周报</h2>
                            <p className="mt-4 font-semibold text-slate-600">2025.05.12 - 2025.05.18 ｜ 覆盖行业：食品饮料、营养健康、功能性原料等 6 大行业</p>
                        </div>
                        <div className="grid grid-cols-5 gap-0 p-4">
                            {[
                                ["本周监控企业", "20", "+1"],
                                ["本周新增情报", "38", "+8"],
                                ["本周涉及新品", "26", "+5"],
                                ["本周重点动态", "16", "+3"],
                                ["情报覆盖来源", "256", "+15"],
                            ].map(([label, value, delta]) => (
                                <div key={label} className="border-r border-slate-100 px-7 py-4 last:border-0">
                                    <div className="text-sm font-bold text-slate-600">{label}</div>
                                    <div className="mt-2 text-3xl font-black text-slate-950">{value}</div>
                                    <div className="mt-2 text-sm font-bold text-teal-600">较上周 {delta}</div>
                                </div>
                            ))}
                        </div>
                    </DemoCard>

                    <div className="grid gap-4 xl:grid-cols-[1fr_0.9fr_0.7fr]">
                        <DemoCard className="p-5">
                            <SectionHeader title="本周重点动态 TOP 3" />
                            <RankList items={["奈雪的茶新品上新：推出「霸气杨梅」系列，清爽回归", "中粮科技发布2025年第一季度报告：营收同比增长18.7%", "日本不二制油新应用方案：黄原胶解决方案"]} />
                        </DemoCard>
                        <DemoCard className="p-5">
                            <SectionHeader title="新品发布汇总" />
                            <DonutChart total="26" label="新品" compact />
                        </DemoCard>
                        <DemoCard className="p-5">
                            <SectionHeader title="财报与公告" />
                            <div className="space-y-4">
                                {["财报发布 8", "融资动态 3", "战略合作 4", "人事变动 2", "其他公告 1"].map((item) => (
                                    <div key={item} className="flex items-center justify-between text-sm font-semibold text-slate-700">
                                        <span>{item.split(" ")[0]}</span>
                                        <span>{item.split(" ")[1]}</span>
                                    </div>
                                ))}
                            </div>
                        </DemoCard>
                    </div>

                    <div className="grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
                        <DemoCard className="p-5">
                            <SectionHeader title="行业趋势观察" action="查看详情" />
                            <div className="grid gap-5 md:grid-cols-2">
                                <div className="h-60">
                                    <MiniLineChart />
                                </div>
                                <div className="flex flex-wrap content-center justify-center gap-3 text-center">
                                    {["新品上市", "功能食品", "益生菌", "无糖", "原料替代", "冻干技术", "可持续"].map((word, index) => (
                                        <span key={word} className={index === 0 ? "text-4xl font-black text-blue-500" : "text-xl font-bold text-cyan-600"}>
                                            {word}
                                        </span>
                                    ))}
                                </div>
                            </div>
                        </DemoCard>
                        <DemoCard className="p-5">
                            <SectionHeader title="AI生成结论与建议" action="查看详情" />
                            <div className="rounded-xl border border-slate-200 p-4">
                                <h3 className="font-black text-slate-900">核心结论</h3>
                                <p className="mt-2 text-sm leading-7 text-slate-600">本周新品发布活跃度提升，茶饮与功能食品赛道最为活跃；原料端持续向植物蛋白、清洁标签和功能复合方向发展。</p>
                            </div>
                            <div className="mt-4">
                                <SuggestionList />
                            </div>
                        </DemoCard>
                    </div>
                </div>
            </div>
        </PageContainer>
    );
}
