import { Sparkles } from 'lucide-react';

export function IdlePlaceholder() {
  return (
    <div className="h-full flex flex-col items-center justify-center p-12 text-center bg-zinc-50/50 dark:bg-zinc-950/50">
      <div className="max-w-md space-y-6">
        <div className="relative inline-block">
          <div className="w-20 h-20 bg-white dark:bg-zinc-900 rounded-[2.5rem] flex items-center justify-center shadow-2xl shadow-zinc-200 dark:shadow-none border border-zinc-100 dark:border-zinc-800 animate-in zoom-in duration-500">
            <Sparkles size={32} className="text-zinc-900 dark:text-zinc-100 animate-pulse" />
          </div>
          <div className="absolute -top-1 -right-1 w-6 h-6 bg-zinc-900 dark:bg-zinc-100 rounded-full border-2 border-white dark:border-zinc-950 flex items-center justify-center">
            <div className="w-1.5 h-1.5 bg-white dark:bg-zinc-900 rounded-full animate-ping" />
          </div>
        </div>

        <div className="space-y-2">
          <h2 className="text-xl font-semibold text-zinc-900 dark:text-zinc-100 tracking-tight">
            智能助手已就绪
          </h2>
          <p className="text-zinc-500 text-sm leading-relaxed">
            在左侧输入 Prompt 开启对话。当智能体进行深度思考、调用 API 工具或需要决策审批时，相关的可视化动作将同步呈现在此工作台。
          </p>
        </div>

        <div className="pt-8 grid grid-cols-2 gap-3">
          <div className="p-4 rounded-2xl bg-white dark:bg-zinc-900/50 border border-zinc-100 dark:border-zinc-800 text-left">
            <div className="text-[10px] font-bold text-zinc-400 uppercase mb-1 tracking-tighter">能力说明</div>
            <div className="text-xs font-medium text-zinc-600 dark:text-zinc-300">支持长文本分析与自动化工具调用</div>
          </div>
          <div className="p-4 rounded-2xl bg-white dark:bg-zinc-900/50 border border-zinc-100 dark:border-zinc-800 text-left">
            <div className="text-[10px] font-bold text-zinc-400 uppercase mb-1 tracking-tighter">响应机制</div>
            <div className="text-xs font-medium text-zinc-600 dark:text-zinc-300">SSE 实时推送，毫秒级状态同步</div>
          </div>
        </div>
      </div>
    </div>
  );
}
