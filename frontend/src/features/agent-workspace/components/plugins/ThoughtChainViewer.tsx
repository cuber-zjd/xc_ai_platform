import { Check, Loader2, PlayCircle, Wrench } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { ThoughtNodeData } from '@/features/agent-workspace/types/stream-protocol';

interface ThoughtChainViewerProps {
  data: ThoughtNodeData[];
}

export function ThoughtChainViewer({ data = [] }: ThoughtChainViewerProps) {
  return (
    <div className="h-full flex flex-col p-8 bg-zinc-50/50 dark:bg-zinc-950/50">
      <div className="flex items-center gap-3 mb-10">
        <div className="w-10 h-10 rounded-2xl bg-zinc-900 dark:bg-zinc-100 flex items-center justify-center text-zinc-100 dark:text-zinc-900 shadow-lg">
          <PlayCircle size={20} />
        </div>
        <div>
          <h3 className="text-lg font-semibold text-zinc-900 dark:text-zinc-100">思维链执行视图</h3>
          <p className="text-xs text-zinc-500">正在实时追踪智能体的决策链路</p>
        </div>
      </div>

      <div className="flex-1 relative">
        {/* 连接线 */}
        <div className="absolute left-[19px] top-4 bottom-4 w-px bg-zinc-200 dark:bg-zinc-800" />

        <div className="space-y-8 relative">
          {data.map((node) => (
            <div key={node.nodeId} className="flex gap-6 group animate-in fade-in slide-in-from-left-4 duration-500">
              {/* 状态图标 */}
              <div className={cn(
                "w-10 h-10 rounded-full flex items-center justify-center shrink-0 z-10 transition-all border-2",
                node.status === 'pending' 
                  ? "bg-white dark:bg-zinc-900 border-zinc-200 dark:border-zinc-800 text-zinc-400" 
                  : node.status === 'success'
                  ? "bg-zinc-900 dark:bg-zinc-100 border-zinc-900 dark:border-zinc-100 text-zinc-100 dark:text-zinc-900"
                  : "bg-red-50 dark:bg-red-950 border-red-200 dark:border-red-900 text-red-500"
              )}>
                {node.status === 'pending' ? (
                  <Loader2 size={18} className="animate-spin" />
                ) : node.act === 'calling_tool' ? (
                  <Wrench size={18} />
                ) : (
                  <Check size={18} />
                )}
              </div>

              {/* 节点详情 */}
              <div className="pt-1.5 flex-1">
                <div className="flex items-center justify-between mb-1">
                  <span className={cn(
                    "text-sm font-medium uppercase tracking-wider",
                    node.status === 'pending' ? "text-zinc-400" : "text-zinc-900 dark:text-zinc-100"
                  )}>
                    {node.act.replace('_', ' ')}
                  </span>
                  <span className="text-[10px] text-zinc-400 font-mono">
                    #{node.nodeId.slice(0, 8)}
                  </span>
                </div>
                <p className={cn(
                  "text-sm leading-relaxed",
                  node.status === 'pending' ? "text-zinc-400 italic" : "text-zinc-600 dark:text-zinc-400"
                )}>
                  {node.detailStr || "正在处理中..."}
                </p>
                
                {node.toolName && (
                  <div className="mt-3 inline-flex items-center gap-2 px-2.5 py-1 rounded-lg bg-zinc-100 dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700">
                    <Wrench size={12} className="text-zinc-500" />
                    <span className="text-[11px] font-medium text-zinc-600 dark:text-zinc-300">
                      工具: {node.toolName}
                    </span>
                  </div>
                )}
              </div>
            </div>
          ))}

          {data.length === 0 && (
            <div className="flex flex-col items-center justify-center h-64 text-zinc-400 space-y-3 opacity-50">
              <Loader2 size={32} className="animate-spin mb-2" />
              <p className="text-sm">暂无思考轨迹，等待指令中...</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
