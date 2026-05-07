import {
    ArrowRight,
    BarChart3,
    Calculator,
    Code2,
    FileText,
    ImageIcon,
    Languages,
    PenTool,
    SearchCheck,
    Wrench,
} from 'lucide-react';

import { cn } from '@/lib/utils';

const AI_TOOLS = [
    {
        icon: FileText,
        title: '文档摘要',
        desc: '上传文档后自动提取关键信息，快速形成摘要与阅读提示。',
        category: '效率',
        tone: 'from-[#edf2ff] to-[#f7fbff]',
        iconColor: 'text-[#5d72ff]',
    },
    {
        icon: Languages,
        title: '智能翻译',
        desc: '支持多语言互译，并尽量保留行业术语与上下文语义。',
        category: '效率',
        tone: 'from-[#f1efff] to-[#faf7ff]',
        iconColor: 'text-[#7c67ff]',
    },
    {
        icon: BarChart3,
        title: '数据分析',
        desc: '上传数据后生成表格分析、趋势洞察和可复用结论。',
        category: '分析',
        tone: 'from-[#ecfbf5] to-[#f7fffb]',
        iconColor: 'text-[#22a06b]',
    },
    {
        icon: Code2,
        title: '代码生成',
        desc: '按需求生成代码片段、接口示例和实现骨架。',
        category: '开发',
        tone: 'from-[#f3efff] to-[#fbf8ff]',
        iconColor: 'text-[#8d5cf6]',
    },
    {
        icon: ImageIcon,
        title: 'AI 绘图',
        desc: '根据文本描述生成视觉草图、插画和概念图像。',
        category: '创意',
        tone: 'from-[#fff0f6] to-[#fff8fb]',
        iconColor: 'text-[#e34a7a]',
    },
    {
        icon: PenTool,
        title: '公文写作',
        desc: '辅助撰写请示、总结、通知等各类正式文稿。',
        category: '效率',
        tone: 'from-[#fff6eb] to-[#fffaf4]',
        iconColor: 'text-[#d38a2c]',
    },
    {
        icon: Calculator,
        title: '智能计算',
        desc: '帮助处理复杂公式、指标试算与口径换算。',
        category: '工具',
        tone: 'from-[#edf9ff] to-[#f8fcff]',
        iconColor: 'text-[#2994d1]',
    },
    {
        icon: SearchCheck,
        title: '智能审核',
        desc: '对合同、文档或流程进行规则核验与风险识别。',
        category: '分析',
        tone: 'from-[#fff1ee] to-[#fff9f8]',
        iconColor: 'text-[#ea5a47]',
    },
];

export default function ToolboxPage() {
    return (
        <div className="app-page">
            <section className="app-page-header">
                <div className="flex items-start gap-4">
                    <div className="flex h-14 w-14 items-center justify-center rounded-[22px] bg-linear-to-br from-[#6e5df7] to-[#b48fff] text-white shadow-[0_18px_36px_rgba(110,93,247,0.28)]">
                        <Wrench className="h-6 w-6" />
                    </div>
                    <div>
                        <div className="app-kicker">AI 工具箱</div>
                        <h2 className="mt-4 text-[34px] font-black tracking-[-0.04em] text-[#24233b]">探索可直接使用的 AI 工具</h2>
                        <p className="mt-2 max-w-2xl app-subtle-text">
                            这里汇集了适合日常办公、分析、创作和开发的高频工具入口。后续也可以继续按同一风格扩展更多工具卡片。
                        </p>
                    </div>
                </div>
            </section>

            <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
                {AI_TOOLS.map((tool) => (
                    <button
                        key={tool.title}
                        type="button"
                        className={cn(
                            'app-panel group flex flex-col items-start rounded-[28px] border-white/80 p-5 text-left transition-all duration-300 hover:-translate-y-1 hover:shadow-[0_22px_42px_rgba(102,99,166,0.1)]',
                        )}
                    >
                        <div className="flex w-full items-start justify-between gap-3">
                            <div
                                className={cn(
                                    'flex h-12 w-12 items-center justify-center rounded-[18px] bg-linear-to-br shadow-[inset_0_1px_0_rgba(255,255,255,0.95)]',
                                    tool.tone,
                                )}
                            >
                                <tool.icon className={cn('h-6 w-6', tool.iconColor)} />
                            </div>
                            <span className="rounded-full border border-white/80 bg-white/80 px-2.5 py-1 text-[11px] font-bold text-[#8d90a6]">
                                {tool.category}
                            </span>
                        </div>
                        <h3 className="mt-5 text-[18px] font-black tracking-tight text-[#24233b]">{tool.title}</h3>
                        <p className="mt-2 text-sm leading-6 text-[#7b7e95]">{tool.desc}</p>
                        <div className="mt-5 flex items-center gap-1 text-sm font-bold text-[#9ea1b5] transition-colors group-hover:text-[#6d5df6]">
                            开始使用
                            <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
                        </div>
                    </button>
                ))}
            </section>
        </div>
    );
}
