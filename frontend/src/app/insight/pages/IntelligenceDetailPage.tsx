import { Clock, Edit3 } from "lucide-react";

import { DemoCard, DemoTag, ExternalButton, RankList, SectionHeader } from "../components/DemoPrimitives";
import { PageContainer } from "../layout/PageContainer";

export function IntelligenceDetailPage() {
    return (
        <PageContainer>
            <h1 className="text-3xl font-black tracking-tight text-slate-950">情报详情</h1>
            <div className="text-sm font-semibold text-slate-500">首页看板 / 情报中心 / 情报详情</div>

            <DemoCard className="p-6">
                <div className="flex flex-col justify-between gap-5 lg:flex-row lg:items-end">
                    <div>
                        <h2 className="text-3xl font-black tracking-tight text-slate-950">奈雪的茶新品上新：推出「霸气杨梅」系列，主打低糖清爽风味</h2>
                        <div className="mt-7 flex flex-wrap items-center gap-8 text-sm font-semibold text-slate-600">
                            <span>来源：品牌公众号</span>
                            <span className="inline-flex items-center gap-2">
                                <Clock className="size-4" />
                                发布时间：2025-05-21 09:35
                            </span>
                            <span>关联企业：<span className="text-blue-600">奈雪的茶</span></span>
                            <span>信息类型：<DemoTag tone="blue">新品上市</DemoTag></span>
                        </div>
                    </div>
                    <ExternalButton>原文链接</ExternalButton>
                </div>
            </DemoCard>

            <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_430px]">
                <div className="space-y-4">
                    <DemoCard className="p-6">
                        <SectionHeader title="AI 摘要" action="" />
                        <ul className="space-y-4 text-base leading-8 text-slate-700">
                            {[
                                "奈雪的茶推出全新「霸气杨梅」系列饮品，包含霸气杨梅、霸气杨梅气泡茶、霸气杨梅茉莉茶三款产品。",
                                "主打低糖、清爽风味，选用当季杨梅搭配茉莉茶基底，酸甜清爽，果香浓郁。",
                                "产品已于2025年5月21日全国门店及小程序同步上线。",
                                "该系列延续奈雪“低糖健康”的产品理念，适配夏季消费场景。",
                            ].map((item) => (
                                <li key={item} className="flex gap-3">
                                    <span className="mt-3 size-2 rounded-full bg-blue-600" />
                                    <span>{item}</span>
                                </li>
                            ))}
                        </ul>
                    </DemoCard>

                    <DemoCard className="p-6">
                        <SectionHeader title="原文内容" action="" />
                        <div className="space-y-5 text-base leading-9 text-slate-700">
                            <p>初夏已至，奈雪的茶带来清爽新选择！全新「霸气杨梅」系列正式上线，精选当季新鲜杨梅，搭配茉莉茶底，打造低糖清爽的夏日风味体验。</p>
                            <p>本次系列包含霸气杨梅、霸气杨梅气泡茶、霸气杨梅茉莉茶三款产品。杨梅果香浓郁，酸甜适中，茉莉花香清雅，两者相得益彰，入口清爽不腻。</p>
                            <p>产品已于2025年5月21日全国奈雪的茶门店及小程序同步上线。奈雪始终坚持“低糖健康”的产品理念，持续探索水果与茶的更多可能。</p>
                        </div>
                        <div className="mt-6 text-center text-blue-600">展开全文</div>
                    </DemoCard>

                    <DemoCard className="p-6">
                        <SectionHeader title="关键信息提取" action="" />
                        <div className="grid gap-4 md:grid-cols-2">
                            {[
                                ["风味特点", "低糖、清爽、酸甜、果香浓郁"],
                                ["产品系列", "霸气杨梅系列（霸气杨梅、霸气杨梅气泡茶、霸气杨梅茉莉茶）"],
                                ["糖度", "低糖（未明确具体糖度）"],
                                ["应用场景", "夏季解暑、日常饮用、聚会分享"],
                                ["上市时间", "2025年5月21日"],
                            ].map(([label, value]) => (
                                <div key={label} className="grid grid-cols-[120px_minmax(0,1fr)] items-center gap-3 border-b border-slate-100 pb-3">
                                    <span className="rounded-md bg-slate-100 px-3 py-2 text-sm font-bold text-slate-600">{label}</span>
                                    <span className="text-sm font-semibold text-slate-700">{value}</span>
                                </div>
                            ))}
                        </div>
                    </DemoCard>
                </div>

                <div className="space-y-4">
                    <DemoCard className="p-5">
                        <SectionHeader title="自动标签" action="" />
                        <div className="flex flex-wrap gap-3">
                            {["新品", "果茶", "低糖", "杨梅", "夏季饮品", "清爽", "茶饮"].map((tag, index) => (
                                <DemoTag key={tag} tone={index % 3 === 0 ? "blue" : index % 3 === 1 ? "green" : "orange"} className="px-6">
                                    {tag}
                                </DemoTag>
                            ))}
                        </div>
                        <button type="button" className="mt-5 inline-flex items-center gap-2 text-sm font-bold text-blue-600">
                            <Edit3 className="size-4" />
                            编辑标签
                        </button>
                    </DemoCard>

                    <DemoCard className="p-5">
                        <SectionHeader title="关联企业" action="查看详情" />
                        <div className="text-lg font-bold text-slate-800">奈雪的茶</div>
                    </DemoCard>

                    <DemoCard className="p-5">
                        <SectionHeader title="相似情报推荐" />
                        <RankList items={["茶百道杨梅系列上新：三款新品同步上市", "喜茶推出杨梅新品：多肉杨梅系列上线", "沪上阿姨杨梅系列新品上市，主打轻甜口感", "乐乐茶夏季限定：杨梅气泡系列清爽来袭"]} />
                    </DemoCard>

                    <DemoCard className="p-5">
                        <SectionHeader title="操作记录" action="" />
                        <div className="space-y-4">
                            {["已入库", "已摘要", "已打标", "已推送"].map((item, index) => (
                                <div key={item} className="grid grid-cols-[24px_1fr_auto] items-center gap-3 text-sm">
                                    <span className="flex size-6 items-center justify-center rounded-full bg-emerald-500 text-white">✓</span>
                                    <span className="font-bold text-slate-700">{item}</span>
                                    <span className="text-slate-500">2025-05-21 09:{36 + index}</span>
                                </div>
                            ))}
                        </div>
                    </DemoCard>
                </div>
            </div>
        </PageContainer>
    );
}
