import {
    Wrench,
    FileText,
    BarChart3,
    Code2,
    Languages,
    ImageIcon,
    PenTool,
    Calculator,
    SearchCheck,
    ArrowRight,
} from 'lucide-react';
import { cn } from '@/lib/utils';

// AI 工具列表
const AI_TOOLS = [
    {
        icon: FileText,
        title: '文档摘要',
        desc: '上传文档，自动提取关键信息并生成摘要',
        category: '效率',
        gradient: 'from-blue-500/10 to-cyan-500/10',
        iconColor: 'text-blue-500',
    },
    {
        icon: Languages,
        title: '智能翻译',
        desc: '支持多语言互译，保留专业术语',
        category: '效率',
        gradient: 'from-indigo-500/10 to-blue-500/10',
        iconColor: 'text-indigo-500',
    },
    {
        icon: BarChart3,
        title: '数据分析',
        desc: '上传数据表格，自动生成可视化分析报告',
        category: '分析',
        gradient: 'from-emerald-500/10 to-teal-500/10',
        iconColor: 'text-emerald-500',
    },
    {
        icon: Code2,
        title: '代码生成',
        desc: '描述需求，自动生成高质量代码片段',
        category: '开发',
        gradient: 'from-violet-500/10 to-purple-500/10',
        iconColor: 'text-violet-500',
    },
    {
        icon: ImageIcon,
        title: 'AI 绘图',
        desc: '输入文字描述，生成精美图片',
        category: '创意',
        gradient: 'from-pink-500/10 to-rose-500/10',
        iconColor: 'text-pink-500',
    },
    {
        icon: PenTool,
        title: '公文写作',
        desc: '智能辅助撰写各类公文和报告',
        category: '效率',
        gradient: 'from-amber-500/10 to-orange-500/10',
        iconColor: 'text-amber-500',
    },
    {
        icon: Calculator,
        title: '智能计算',
        desc: '复杂公式计算与数学问题求解',
        category: '工具',
        gradient: 'from-cyan-500/10 to-sky-500/10',
        iconColor: 'text-cyan-500',
    },
    {
        icon: SearchCheck,
        title: '智能审核',
        desc: '合同、文档智能审核与风险识别',
        category: '分析',
        gradient: 'from-red-500/10 to-orange-500/10',
        iconColor: 'text-red-500',
    },
];

export default function ToolboxPage() {
    return (
        <div className="space-y-8 max-w-6xl mx-auto">
            {/* 页面标题 */}
            <div className="space-y-2">
                <div className="flex items-center gap-3">
                    <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10">
                        <Wrench className="h-5 w-5 text-primary" />
                    </div>
                    <div>
                        <h2 className="text-2xl font-bold tracking-tight">AI 工具箱</h2>
                        <p className="text-sm text-muted-foreground">
                            选择你需要的 AI 工具，提升工作效率
                        </p>
                    </div>
                </div>
            </div>

            {/* 工具网格 */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                {AI_TOOLS.map((tool) => (
                    <button
                        key={tool.title}
                        className={cn(
                            'group flex flex-col items-start gap-3 p-5 rounded-xl border transition-all duration-300',
                            'bg-gradient-to-br hover:shadow-lg hover:-translate-y-0.5 cursor-pointer text-left',
                            tool.gradient,
                            'border-border/50 hover:border-primary/30'
                        )}
                    >
                        <div className="flex items-center justify-between w-full">
                            <div className={cn(
                                'flex h-10 w-10 items-center justify-center rounded-xl',
                                'bg-background/80 backdrop-blur-sm shadow-sm'
                            )}>
                                <tool.icon className={cn('h-5 w-5', tool.iconColor)} />
                            </div>
                            <span className="text-[10px] font-medium px-2 py-0.5 rounded-full bg-muted text-muted-foreground">
                                {tool.category}
                            </span>
                        </div>
                        <div className="space-y-1">
                            <h3 className="font-semibold text-sm">{tool.title}</h3>
                            <p className="text-xs text-muted-foreground leading-relaxed">
                                {tool.desc}
                            </p>
                        </div>
                        <div className="flex items-center gap-1 text-xs text-muted-foreground/50 group-hover:text-primary transition-colors mt-auto pt-2">
                            <span>开始使用</span>
                            <ArrowRight className="h-3 w-3 group-hover:translate-x-0.5 transition-transform" />
                        </div>
                    </button>
                ))}
            </div>

            {/* 底部提示 */}
            <div className="text-center text-xs text-muted-foreground/50 py-4">
                更多工具持续上线中...
            </div>
        </div>
    );
}
