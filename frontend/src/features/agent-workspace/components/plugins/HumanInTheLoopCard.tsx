import { AlertCircle, Check, RefreshCw, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import type { HumanInteractData } from '@/features/agent-workspace/types/stream-protocol';

interface HumanInTheLoopCardProps {
  data: HumanInteractData;
  onAction?: (action: string, payload?: any) => void;
}

export function HumanInTheLoopCard({ data, onAction }: HumanInTheLoopCardProps) {
  return (
    <div className="h-full flex flex-col p-8 bg-zinc-50/50 dark:bg-zinc-950/50">
      <div className="flex items-center gap-3 mb-8">
        <div className="w-10 h-10 rounded-2xl bg-amber-500 flex items-center justify-center text-white shadow-lg animate-pulse">
          <AlertCircle size={20} />
        </div>
        <div>
          <h3 className="text-lg font-semibold text-zinc-900 dark:text-zinc-100">需要人类干预</h3>
          <p className="text-xs text-zinc-500">智能体在执行关键操作前请求你的确认</p>
        </div>
      </div>

      <div className="flex-1 bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-3xl p-6 shadow-sm overflow-auto">
        <div className="mb-6">
          <label className="text-[10px] font-bold text-zinc-400 uppercase tracking-widest block mb-2">背景请求</label>
          <p className="text-zinc-700 dark:text-zinc-300 leading-relaxed font-medium">
            {data.promptText || "智能体请求权限执行敏感操作，请检查下方载荷。"}
          </p>
        </div>

        {data.defaultPayload && (
          <div className="mb-8">
            <label className="text-[10px] font-bold text-zinc-400 uppercase tracking-widest block mb-2">提议的数据/配置</label>
            <pre className="p-4 rounded-xl bg-zinc-900 text-zinc-100 text-xs font-mono overflow-x-auto border border-zinc-800">
              {JSON.stringify(data.defaultPayload, null, 2)}
            </pre>
          </div>
        )}

        <div className="flex flex-col gap-3">
          <div className="flex gap-3">
            <Button 
              className="flex-1 h-12 rounded-2xl bg-blue-600 text-white hover:bg-blue-700 gap-2 font-semibold"
              onClick={() => onAction?.('approve')}
            >
              <Check size={18} />
              确认执行
            </Button>
            <Button 
              variant="outline"
              className="flex-1 h-12 rounded-2xl border-zinc-200 dark:border-zinc-800 hover:bg-zinc-50 dark:hover:bg-zinc-800 gap-2 font-semibold"
              onClick={() => onAction?.('modify')}
            >
              <RefreshCw size={18} />
              修改并重试
            </Button>
          </div>
          <Button 
            variant="ghost"
            className="h-12 rounded-2xl text-red-500 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-950/30 gap-2 font-semibold"
            onClick={() => onAction?.('reject')}
          >
            <X size={18} />
            拒绝操作
          </Button>
        </div>
      </div>
    </div>
  );
}
