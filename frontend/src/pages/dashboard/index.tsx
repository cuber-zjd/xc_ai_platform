import { BarChart3, Bot, ChartNoAxesColumn, ShieldCheck, Sparkles } from "lucide-react";

const metricCards = [
    { title: "活跃用户", value: "1,284", detail: "较昨日提升 8.4%", icon: Sparkles },
    { title: "运行中的智能体", value: "32", detail: "8 个分组在线", icon: Bot },
    { title: "本周报表任务", value: "96", detail: "SQL 阶段通过率 91%", icon: BarChart3 },
    { title: "风险告警", value: "3", detail: "均已分配责任人", icon: ShieldCheck },
];

const activityList = [
    "FineReport 报表生成已切换为步骤式工作流",
    "用户侧与管理后台正在统一视觉系统和信息密度",
    "本周重点继续完善 Excel 模板识别与报表设计阶段",
];

export default function DashboardPage() {
    return (
        <div className="app-page">
            <section className="app-page-header">
                <div className="flex flex-col gap-3 xl:flex-row xl:items-end xl:justify-between">
                    <div>
                        <div className="app-kicker">平台概览</div>
                        <h2 className="mt-3 text-[34px] font-black tracking-[-0.05em] text-[#24233b]">管理后台总览</h2>
                        <p className="mt-2 max-w-3xl app-subtle-text">
                            这里先提供一版与新视觉对齐的后台概览，用于承接后续更多运营指标、任务状态和系统治理信息。
                        </p>
                    </div>
                    <div className="rounded-full border border-white/80 bg-white/80 px-4 py-2 text-sm text-[#8d90a6] shadow-[0_10px_24px_rgba(102,99,166,0.05)]">
                        视觉风格已与用户侧工作台同步
                    </div>
                </div>
            </section>

            <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
                {metricCards.map((card) => (
                    <div key={card.title} className="app-panel rounded-[28px] p-5">
                        <div className="flex items-start justify-between gap-3">
                            <div>
                                <div className="text-sm font-bold text-[#8f92a8]">{card.title}</div>
                                <div className="mt-4 text-[34px] font-black tracking-[-0.05em] text-[#25233b]">{card.value}</div>
                                <div className="mt-2 text-sm text-[#7c8096]">{card.detail}</div>
                            </div>
                            <div className="flex h-12 w-12 items-center justify-center rounded-[18px] bg-linear-to-br from-[#edf1ff] to-[#faf7ff] text-[#6b5cf0]">
                                <card.icon className="h-5 w-5" />
                            </div>
                        </div>
                    </div>
                ))}
            </section>

            <section className="mt-4 grid gap-4 xl:grid-cols-[1.2fr_0.8fr]">
                <div className="app-panel rounded-[30px] p-6">
                    <div className="flex items-center gap-2 text-sm font-black text-[#2c2a43]">
                        <ChartNoAxesColumn className="h-4 w-4 text-[#6d5df6]" />
                        重点推进事项
                    </div>
                    <div className="mt-5 space-y-3">
                        {activityList.map((item, index) => (
                            <div
                                key={item}
                                className="flex items-center gap-4 rounded-[22px] border border-white/80 bg-white/76 px-4 py-4 shadow-[0_10px_24px_rgba(102,99,166,0.05)]"
                            >
                                <div className="flex h-10 w-10 items-center justify-center rounded-full bg-linear-to-br from-[#6e5df7] to-[#b48fff] text-sm font-black text-white">
                                    0{index + 1}
                                </div>
                                <div className="text-sm font-semibold text-[#47485d]">{item}</div>
                            </div>
                        ))}
                    </div>
                </div>

                <div className="app-panel rounded-[30px] p-6">
                    <div className="text-sm font-black text-[#2c2a43]">状态说明</div>
                    <div className="mt-4 rounded-[24px] bg-[#11131d] p-5 text-white shadow-[0_18px_36px_rgba(17,19,29,0.18)]">
                        <div className="text-[18px] font-black tracking-tight">新的管理工作区已上线</div>
                        <p className="mt-3 text-sm leading-6 text-white/72">
                            这一版先完成全局基调、主布局和核心页面对齐。后续可以继续把系统管理、用户管理、模型管理等明细页逐步切到同一套表达方式。
                        </p>
                    </div>
                </div>
            </section>
        </div>
    );
}
