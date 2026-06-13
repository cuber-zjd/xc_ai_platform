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

const AI_TOOLS = [
    {
        icon: FileText,
        title: '文档摘要',
        desc: '上传文档后自动提取关键信息，快速形成摘要与阅读提示。',
        category: '效率',
    },
    {
        icon: Languages,
        title: '智能翻译',
        desc: '支持多语言互译，并尽量保留行业术语与上下文语义。',
        category: '效率',
    },
    {
        icon: BarChart3,
        title: '数据分析',
        desc: '上传数据后生成表格分析、趋势洞察和可复用结论。',
        category: '分析',
    },
    {
        icon: Code2,
        title: '代码生成',
        desc: '按需求生成代码片段、接口示例和实现骨架。',
        category: '开发',
    },
    {
        icon: ImageIcon,
        title: 'AI 绘图',
        desc: '根据文本描述生成视觉草图、插画和概念图像。',
        category: '创意',
    },
    {
        icon: PenTool,
        title: '公文写作',
        desc: '辅助撰写请示、总结、通知等各类正式文稿。',
        category: '效率',
    },
    {
        icon: Calculator,
        title: '智能计算',
        desc: '帮助处理复杂公式、指标试算与口径换算。',
        category: '工具',
    },
    {
        icon: SearchCheck,
        title: '智能审核',
        desc: '对合同、文档或流程进行规则校验与风险识别。',
        category: '分析',
    },
];

export default function ToolboxPage() {
    return (
        <div className="app-page">
            <section className="mx-auto max-w-5xl px-4 pt-12">
                <div className="flex items-center gap-3">
                    <div className="flex h-11 w-11 items-center justify-center rounded-2xl border border-[#e5e5e5] bg-white shadow-sm">
                        <Wrench className="h-5 w-5 text-[#171717]" />
                    </div>
                    <div>
                        <h1 className="text-3xl font-semibold tracking-tight text-[#171717]">应用中心</h1>
                        <p className="mt-1 text-sm text-[#6f6f6f]">常用 AI 工具和轻量能力入口。</p>
                    </div>
                </div>
            </section>

            <section className="mx-auto mt-8 max-w-5xl px-4 pb-12">
                <div className="overflow-hidden rounded-2xl border border-[#e7e7e7] bg-white">
                    {AI_TOOLS.map((tool, index) => (
                        <button
                            key={tool.title}
                            type="button"
                            className="group flex w-full items-center gap-4 border-b border-[#eeeeee] px-4 py-4 text-left transition last:border-b-0 hover:bg-[#fafafa]"
                        >
                            <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-[#f4f4f4] text-[#333333]">
                                <tool.icon className="h-5 w-5" />
                            </div>
                            <div className="min-w-0 flex-1">
                                <div className="flex flex-wrap items-center gap-2">
                                    <h2 className="text-sm font-semibold text-[#171717]">{tool.title}</h2>
                                    <span className="rounded-full bg-[#f1f1f1] px-2 py-0.5 text-xs text-[#6f6f6f]">{tool.category}</span>
                                </div>
                                <p className="mt-1 line-clamp-1 text-sm text-[#6f6f6f]">{tool.desc}</p>
                            </div>
                            <div className="hidden items-center gap-2 text-sm font-medium text-[#6f6f6f] group-hover:text-[#171717] sm:flex">
                                开始使用
                                <ArrowRight className="h-4 w-4" />
                            </div>
                            <div className="text-xs text-[#b5b5b5]">{String(index + 1).padStart(2, '0')}</div>
                        </button>
                    ))}
                </div>
            </section>
        </div>
    );
}
