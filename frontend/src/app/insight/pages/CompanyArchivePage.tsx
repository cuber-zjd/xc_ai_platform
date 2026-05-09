import { BellDot, FilePieChart, Flame, Newspaper } from "lucide-react";

import { DemoCard, DemoTag, DonutChart, LinkButton, MiniLineChart, RankList, SectionHeader, StatCard } from "../components/DemoPrimitives";
import { PageContainer } from "../layout/PageContainer";

export function CompanyArchivePage() {
    return (
        <PageContainer>
            <h1 className="text-3xl font-black tracking-tight text-slate-950">企业档案</h1>
            <div className="text-sm font-semibold text-slate-500">首页看板 / 企业档案 / 奈雪的茶</div>

            <DemoCard className="p-6">
                <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_repeat(4,190px)]">
                    <div className="flex items-center gap-7">
                        <div className="flex size-28 items-center justify-center rounded-xl bg-lime-500 text-center text-3xl font-black leading-tight text-white">奈雪<br />的茶</div>
                        <div>
                            <div className="flex flex-wrap items-center gap-3">
                                <h2 className="text-3xl font-black text-slate-950">奈雪的茶</h2>
                                <DemoTag tone="orange">重点客户</DemoTag>
                                <DemoTag tone="green">健康</DemoTag>
                            </div>
                            <p className="mt-4 max-w-2xl text-base leading-7 text-slate-600">
                                奈雪的茶是一家新式茶饮品牌，聚焦健康茶饮与生活方式体验，以“好茶 好果 好品牌”为核心，持续推出创新产品与场景服务。
                            </p>
                        </div>
                    </div>
                    <StatCard title="最近30天情报" value="26" compare="较上周" delta="+8" icon={<Newspaper className="size-6" />} />
                    <StatCard title="新品动态" value="8" compare="较上周" delta="+3" tone="cyan" icon={<BellDot className="size-6" />} />
                    <StatCard title="财报公告" value="2" compare="较上月" delta="+1" icon={<FilePieChart className="size-6" />} />
                    <StatCard title="高关注标签" value="12" compare="较上月" delta="+5" tone="cyan" icon={<Flame className="size-6" />} />
                </div>
            </DemoCard>

            <div className="grid gap-4 xl:grid-cols-[1.1fr_0.9fr_1fr]">
                <DemoCard className="p-5">
                    <SectionHeader title="近30天动态趋势" action="近30天" />
                    <div className="h-72">
                        <MiniLineChart points={[24, 31, 21, 38, 55, 41, 26]} />
                    </div>
                </DemoCard>
                <DemoCard className="p-5">
                    <SectionHeader title="情报类型分布" action="查看详情" />
                    <DonutChart total="26" compact />
                </DemoCard>
                <DemoCard className="p-5">
                    <SectionHeader title="最新动态" />
                    <RankList items={["奈雪的茶新品上新：推出「霸气杨梅」系列", "奈雪的茶与FENDI联合合作，推出限定周边", "奈雪的茶发布2025年第一季度报告：营收同比增长18.7%", "奈雪的茶门店新开12家，覆盖苏州、成都等城市", "奈雪的茶×喜茶联名快闪活动引发社交媒体热议"]} />
                </DemoCard>
            </div>

            <div className="grid gap-4 xl:grid-cols-[0.82fr_1.3fr_1.1fr]">
                <DemoCard className="p-5">
                    <SectionHeader title="产品 / 应用关键词" action="" />
                    <div className="grid grid-cols-3 gap-4 py-8 text-center">
                        {["茶饮", "低糖", "联名", "季节限定", "果味", "健康轻负担"].map((tag, index) => (
                            <DemoTag key={tag} tone={index % 3 === 0 ? "green" : index % 3 === 1 ? "blue" : "orange"} className="justify-center py-3 text-base">
                                {tag}
                            </DemoTag>
                        ))}
                    </div>
                    <div className="text-right">
                        <LinkButton>更多关键词</LinkButton>
                    </div>
                </DemoCard>

                <DemoCard className="p-5">
                    <SectionHeader title="重点情报时间线" action="" />
                    <div className="space-y-5">
                        {[
                            ["2025-05-21 09:35", "平果杨梅系列新品上市，主打低糖清爽风味", "新品动态"],
                            ["2025-05-20 20:15", "发布2025年第一季度报告：营收同比增长18.7%", "财报公告"],
                            ["2025-05-19 14:30", "与FENDI联合合作正式上线，推出限定周边", "品牌合作"],
                            ["2025-05-17 10:08", "全国新开12家门店，重点布局华东与西南", "门店拓展"],
                            ["2025-05-15 18:22", "联名快闪活动上线，相关话题登上微博热搜", "市场活动"],
                        ].map(([time, title, tag], index) => (
                            <div key={title} className="grid grid-cols-[16px_150px_minmax(0,1fr)_90px] items-center gap-3">
                                <span className="size-3 rounded-full bg-blue-500" style={{ opacity: 1 - index * 0.1 }} />
                                <span className="text-sm text-slate-500">{time}</span>
                                <span className="text-sm font-semibold text-slate-700">{title}</span>
                                <DemoTag tone={index % 2 === 0 ? "blue" : "green"}>{tag}</DemoTag>
                            </div>
                        ))}
                    </div>
                    <div className="mt-5 text-center">
                        <LinkButton>查看全部时间线</LinkButton>
                    </div>
                </DemoCard>

                <DemoCard className="p-5">
                    <SectionHeader title="企业关键信息" action="" />
                    <div className="divide-y divide-slate-100">
                        {[
                            ["所属类别", "新式茶饮"],
                            ["重点应用方向", "即饮茶饮、健康轻负担、季节限定、联合合作"],
                            ["监控级别", "重点客户"],
                            ["关联课题", "低糖茶饮创新、果味茶基研发、联名产品趋势研究"],
                        ].map(([label, value]) => (
                            <div key={label} className="grid grid-cols-[120px_minmax(0,1fr)] gap-4 py-4">
                                <span className="font-bold text-slate-500">{label}</span>
                                <span className="font-semibold leading-6 text-slate-800">{value}</span>
                            </div>
                        ))}
                    </div>
                    <div className="mt-5 text-center">
                        <LinkButton>进入企业情报中心</LinkButton>
                    </div>
                </DemoCard>
            </div>
        </PageContainer>
    );
}
