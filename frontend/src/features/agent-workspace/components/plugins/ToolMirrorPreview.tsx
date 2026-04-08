import { Monitor, Table, BarChart3, Code2, ExternalLink } from 'lucide-react';
import type { ToolOutputData } from '@/features/agent-workspace/types/stream-protocol';

interface ToolMirrorPreviewProps {
  data: ToolOutputData;
}

export function ToolMirrorPreview({ data }: ToolMirrorPreviewProps) {
  const Icon = {
    table: Table,
    chart: BarChart3,
    json: Code2,
    html: ExternalLink,
  }[data.displayType] || Monitor;

  return (
    <div className="h-full flex flex-col bg-zinc-50/50 dark:bg-zinc-950/50">
      <div className="p-8 border-b border-zinc-100 dark:border-zinc-900 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-2xl bg-zinc-900 dark:bg-zinc-100 flex items-center justify-center text-zinc-100 dark:text-zinc-900 shadow-lg">
            <Icon size={20} />
          </div>
          <div>
            <h3 className="text-lg font-semibold text-zinc-900 dark:text-zinc-100">{data.toolName} 输出预览</h3>
            <p className="text-xs text-zinc-500">工具执行成功，正在展示结构化数据</p>
          </div>
        </div>
        <div className="flex gap-2">
           <span className="px-2 py-1 rounded bg-zinc-200/50 dark:bg-zinc-800 text-[10px] font-mono text-zinc-500 uppercase tracking-tight">
             Type: {data.displayType}
           </span>
        </div>
      </div>

      <div className="flex-1 overflow-auto p-8">
        <div className="bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-3xl p-6 shadow-sm min-h-full">
          {data.displayType === 'json' && (
            <pre className="text-xs font-mono text-zinc-700 dark:text-zinc-300 leading-relaxed whitespace-pre-wrap">
              {JSON.stringify(data.content, null, 2)}
            </pre>
          )}

          {data.displayType === 'table' && (
             <div className="text-center py-20 text-zinc-400">
               <Table size={48} className="mx-auto mb-4 opacity-20" />
               <p>此处将渲染结构化表格组件</p>
               <pre className="mt-4 text-[10px] text-left overflow-hidden">
                 {JSON.stringify(data.content).slice(0, 100)}...
               </pre>
             </div>
          )}

          {/* 其他类型占位 */}
          {(data.displayType === 'chart' || data.displayType === 'html') && (
            <div className="flex flex-col items-center justify-center py-20 opacity-40">
              <Icon size={48} className="mb-4" />
              <p className="text-sm">正在加载可视化渲染器...</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
