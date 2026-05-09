import { Building2, Database, FileText, Flame } from "lucide-react";

import {
    DemoCard,
    DemoTag,
    DonutChart,
    LinkButton,
    MiniLineChart,
    RankList,
    SectionHeader,
    StatCard,
} from "../components/DemoPrimitives";
import { PageContainer } from "../layout/PageContainer";

const latestRows = [
    ["2025-05-21 09:35", "奈雪的茶", "新品上市", "奈雪的茶新品上新：推出「霸气杨梅」系列，清爽回归", ["新品", "茶饮", "季节限定"]],
    ["2025-05-21 08:50", "中粮科技", "财报公告", "中粮科技发布2025年第一季度报告：营收同比增长18.7%", ["财报", "食品原料"]],
    ["2025-05-21 08:15", "不二制油", "产品方案", "日本不二推出新应用方案：黄原胶在植物基酸奶中的应用", ["应用方案", "植物基"]],
    ["2025-05-21 07:42", "瑞幸咖啡", "新品上市", "瑞幸春季限定饮品上市：轻椰系列回归，清爽椰香来袭", ["新品", "咖啡", "季节限定"]],
    ["2025-05-21 07:10", "山松生物", "产品动态", "山松蛋白新品动态：豌豆蛋白新配方发布，提升乳化稳定性", ["蛋白", "新品", "植物蛋白"]],
];

export function DashboardPage() {
    return (
        <PageContainer>
            <h1 className="text-3xl font-black tracking-tight text-slate-950">首页看板</h1>

            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
                <StatCard title="监控企业" value="20" compare="较昨日" delta="+1" icon={<Building2 className="size-7" />} />
                <StatCard title="数据源" value="12" compare="较昨日" delta="+0" tone="cyan" icon={<Database className="size-7" />} />
                <StatCard title="今日新增情报" value="38" compare="较昨日" delta="+8" icon={<FileText className="size-7" />} />
                <StatCard title="本周重点动态" value="16" compare="较上周" delta="+3" tone="cyan" icon={<Flame className="size-7" />} />
            </div>

            <div className="grid gap-4 xl:grid-cols-[1.12fr_0.86fr_1fr]">
                <DemoCard className="p-5">
                    <SectionHeader title="近7日情报趋势" action="近7日" />
                    <div className="h-72 px-2 pb-5">
                        <MiniLineChart />
                    </div>
                </DemoCard>

                <DemoCard className="p-5">
                    <SectionHeader title="情报来源分布" action="查看详情" />
                    <DonutChart />
                </DemoCard>

                <DemoCard className="p-5">
                    <SectionHeader title="重点动态" action="查看更多" />
                    <RankList
                        items={[
                            "奈雪的茶新品上新：推出「霸气杨梅」系列",
                            "中粮科技发布2025年第一季度报告",
                            "日本不二推出新应用方案：黄原胶解决方案",
                            "瑞幸春季限定饮品上市：轻椰系列回归",
                            "山松蛋白新品动态：豌豆蛋白新配方发布",
                        ]}
                    />
                </DemoCard>
            </div>

            <DemoCard className="p-5">
                <SectionHeader title="最新情报" action="查看更多情报" />
                <div className="overflow-hidden rounded-xl border border-slate-200">
                    <table className="w-full text-left text-sm">
                        <thead className="bg-slate-50 text-slate-500">
                            <tr>
                                {["发布时间", "企业", "类型", "标题", "标签"].map((head) => (
                                    <th key={head} className="px-4 py-3 font-bold">
                                        {head}
                                    </th>
                                ))}
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100">
                            {latestRows.map((row) => (
                                <tr key={row[0] as string} className="hover:bg-blue-50/40">
                                    <td className="px-4 py-3 text-slate-600">{row[0]}</td>
                                    <td className="px-4 py-3 font-bold text-slate-800">{row[1]}</td>
                                    <td className="px-4 py-3">
                                        <DemoTag tone="blue">{row[2]}</DemoTag>
                                    </td>
                                    <td className="px-4 py-3 font-semibold text-slate-800">{row[3]}</td>
                                    <td className="px-4 py-3">
                                        <div className="flex flex-wrap gap-2">
                                            {(row[4] as string[]).map((tag, index) => (
                                                <DemoTag key={tag} tone={index === 0 ? "blue" : index === 1 ? "green" : "orange"}>
                                                    {tag}
                                                </DemoTag>
                                            ))}
                                        </div>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
                <div className="mt-4 flex justify-center">
                    <LinkButton>查看更多情报</LinkButton>
                </div>
            </DemoCard>
        </PageContainer>
    );
}
