import { RefreshCw } from "lucide-react";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";

import {
    DemoCard,
    DemoTag,
    FilterInput,
    FilterSelect,
    OperationIconRow,
    RankList,
    SectionHeader,
} from "../components/DemoPrimitives";
import { PageContainer } from "../layout/PageContainer";

const intelligenceRows = [
    ["2025-05-21 09:35", "奈雪的茶", "新品", "奈雪的茶新品上新：推出「霸气杨梅」系列，清爽回归", "奈雪的茶上线霸气杨梅系列饮品，选用杨梅鲜果，搭配茉莉茶底。", ["新品", "茶饮"]],
    ["2025-05-21 08:50", "中粮科技", "财报", "中粮科技发布2025年第一季度报告：营收同比增长18.7%", "报告期内，公司实现营业收入23.45亿元，同比增长18.7%。", ["财报", "食品原料"]],
    ["2025-05-21 08:15", "FUJI", "行业资讯", "日本不二推出新应用方案：黄原胶在植物基酸奶中的应用", "不二公司介绍黄原胶在植物基酸奶中的稳定、增稠与口感优化效果。", ["应用方案", "植物基"]],
    ["2025-05-21 07:42", "瑞幸咖啡", "新品", "瑞幸春季限定饮品上市：轻椰系列回归", "瑞幸轻椰系列限时回归，新增轻椰拿铁与轻椰系列口味。", ["新品", "咖啡"]],
    ["2025-05-20 16:30", "山松生物", "产品动态", "山松蛋白新品动态：豌豆蛋白新配方发布", "山松生物发布高乳化稳定性豌豆蛋白新配方。", ["蛋白", "新品"]],
    ["2025-05-20 10:20", "汤臣倍健", "财报", "汤臣倍健发布2024年年报：营收增长", "公司披露年度经营情况，继续推进全球化。", ["财报", "营养保健"]],
    ["2025-05-19 19:05", "中粮科技", "行业资讯", "玉米纤维在健康零食中的应用趋势分析", "文章分析玉米纤维在高膳食纤维零食中的应用潜力。", ["行业资讯", "膳食纤维"]],
    ["2025-05-19 15:45", "奈雪的茶", "重点动态", "奈雪门店焕新升级：推出「轻快轻食」新概念空间", "奈雪在全国多地门店进行空间焕新。", ["门店动态", "茶饮"]],
];

export function IntelligenceCenterPage() {
    return (
        <PageContainer>
            <h1 className="text-3xl font-black tracking-tight text-slate-950">情报中心</h1>

            <DemoCard className="p-5">
                <div className="grid gap-4 xl:grid-cols-[1.1fr_0.8fr_1.4fr_0.9fr_1.2fr_auto_auto]">
                    <FilterInput label="企业名称" placeholder="搜索企业名称" />
                    <FilterSelect label="类型" value="客户 / 竞对" />
                    <FilterSelect label="来源" value="官网 / 财报公告 / 行业资讯 / 公众号" wide />
                    <FilterSelect label="课题标签" value="请选择课题标签" />
                    <FilterInput label="时间范围" placeholder="开始日期  ~  结束日期" />
                    <div className="flex items-end">
                        <Button className="h-11 rounded-xl bg-blue-600 px-7 text-white hover:bg-blue-700">搜索</Button>
                    </div>
                    <div className="flex items-end">
                        <Button variant="ghost" className="h-11 rounded-xl text-slate-600">
                            <RefreshCw className="size-4" />
                            重置
                        </Button>
                    </div>
                </div>
            </DemoCard>

            <DemoCard className="overflow-hidden">
                <div className="border-b border-slate-200 px-5 pt-4">
                    <div className="flex gap-10 text-base font-bold text-slate-600">
                        {["全部情报", "重点动态", "新品情报", "财报公告", "行业资讯"].map((tab, index) => (
                            <button key={tab} type="button" className={index === 0 ? "border-b-[3px] border-blue-600 pb-4 text-blue-600" : "pb-4"}>
                                {tab}
                            </button>
                        ))}
                    </div>
                </div>
                <div className="grid gap-4 p-4 xl:grid-cols-[minmax(0,1fr)_360px]">
                    <div className="overflow-hidden rounded-xl border border-slate-200">
                        <table className="w-full text-left text-sm">
                            <thead className="bg-slate-50 text-slate-500">
                                <tr>
                                    {["发布时间", "企业", "类型", "标题", "摘要", "标签", "操作"].map((head) => (
                                        <th key={head} className="px-4 py-3 font-bold">
                                            {head}
                                        </th>
                                    ))}
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-100">
                                {intelligenceRows.map((row, index) => (
                                    <tr key={`${row[0]}-${row[1]}`} className="align-top hover:bg-blue-50/40">
                                        <td className="w-28 px-4 py-4 text-slate-600">{row[0]}</td>
                                        <td className="w-24 px-4 py-4 font-bold text-slate-800">{row[1]}</td>
                                        <td className="px-4 py-4">
                                            <DemoTag tone={index % 3 === 0 ? "blue" : index % 3 === 1 ? "green" : "orange"}>{row[2]}</DemoTag>
                                        </td>
                                        <td className="w-56 px-4 py-4 font-bold text-slate-800">
                                            <Link to="/insight/intelligence/detail" className="hover:text-blue-600">
                                                {row[3]}
                                            </Link>
                                        </td>
                                        <td className="px-4 py-4 leading-6 text-slate-600">{row[4]}</td>
                                        <td className="px-4 py-4">
                                            <div className="flex flex-wrap gap-2">
                                                {(row[5] as string[]).map((tag) => (
                                                    <DemoTag key={tag} tone="cyan">
                                                        {tag}
                                                    </DemoTag>
                                                ))}
                                            </div>
                                        </td>
                                        <td className="px-4 py-4">
                                            <OperationIconRow />
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>

                    <div className="space-y-4">
                        <DemoCard className="p-4">
                            <SectionHeader title="今日热点" />
                            <RankList
                                showViews
                                items={[
                                    "奈雪的茶新品上新：推出「霸气杨梅」系列",
                                    "中粮科技发布2025年第一季度报告",
                                    "瑞幸春季限定饮品上市：轻椰系列回归",
                                    "日本不二推出新应用方案：黄原胶在植物基酸...",
                                    "山松蛋白新品动态：豌豆蛋白新配方发布",
                                ]}
                            />
                        </DemoCard>
                        <DemoCard className="p-4">
                            <SectionHeader title="标签云" />
                            <div className="flex flex-wrap gap-2">
                                {["新品 156", "财报 98", "行业资讯 142", "应用方案 87", "蛋白 73", "茶饮 64", "咖啡 58", "膳食纤维 45", "法规政策 28", "包装创新 27"].map((tag, index) => (
                                    <DemoTag key={tag} tone={index % 4 === 0 ? "blue" : index % 4 === 1 ? "green" : index % 4 === 2 ? "orange" : "purple"}>
                                        {tag}
                                    </DemoTag>
                                ))}
                            </div>
                        </DemoCard>
                        <DemoCard className="p-4">
                            <SectionHeader title="快速筛选" action="" />
                            <div className="grid grid-cols-2 gap-3">
                                {["新品 156", "财报 98", "法规 28", "应用方案 87"].map((tag) => (
                                    <div key={tag} className="rounded-xl border border-slate-200 bg-white p-4 text-center text-lg font-black text-blue-600">
                                        {tag}
                                    </div>
                                ))}
                            </div>
                        </DemoCard>
                    </div>
                </div>
            </DemoCard>
        </PageContainer>
    );
}
