import { AgentWorkspacePage } from '@/features/agent-workspace/pages/AgentWorkspacePage';
import { useWorkspaceStore } from '@/features/agent-workspace/hooks/useWorkspaceStore';
import { Button } from '@/components/ui/button';
import { Play, ShieldAlert, Wrench, Sparkles } from 'lucide-react';

export default function AgentTestPage() {
  const { setWorkspace } = useWorkspaceStore();

  const triggerThought = () => {
    setWorkspace('thought', [
      { nodeId: 't1', act: 'planning', status: 'success', detailStr: '正在检索用户文档库...' },
      { nodeId: 't2', act: 'calling_tool', status: 'pending', detailStr: '正在执行向量搜索', toolName: 'milvus_search' }
    ]);
  };

  const triggerHuman = () => {
    setWorkspace('human', {
      requestId: 'req_123',
      promptText: '智能体申请执行「全系统数据库备份并删除原始日志」，此操作不可逆，请确认。',
      actionType: 'approve',
      defaultPayload: {
        target: 'production_logs',
        action: 'archive_and_delete',
        retention_days: 0
      }
    });
  };

  const triggerTool = () => {
    setWorkspace('tool', {
      toolName: 'data_analyzer',
      displayType: 'table',
      content: [
        { id: 1, name: 'Item A', value: 100 },
        { id: 2, name: 'Item B', value: 200 }
      ]
    });
  };

  const triggerReset = () => {
    setWorkspace('idle', null);
  };

  return (
    <div className="relative h-screen w-full">
      {/* 核心工作台组件 */}
      <AgentWorkspacePage />

      {/* 浮动测试控制台 - 仅用于演示测试 */}
      <div className="absolute top-4 right-4 z-50 flex flex-col gap-2 p-2 bg-white/80 dark:bg-zinc-900/80 backdrop-blur-md border border-zinc-200 dark:border-zinc-800 rounded-2xl shadow-2xl">
        <div className="px-3 py-1 border-b border-zinc-100 dark:border-zinc-800 mb-1">
          <p className="text-[10px] font-bold text-zinc-400 uppercase tracking-tighter">Debug Console</p>
        </div>
        <Button size="sm" variant="ghost" className="justify-start gap-2 text-zinc-600 dark:text-zinc-400" onClick={triggerThought}>
          <Play size={14} /> 模拟思考
        </Button>
        <Button size="sm" variant="ghost" className="justify-start gap-2 text-amber-600" onClick={triggerHuman}>
          <ShieldAlert size={14} /> 模拟审批
        </Button>
        <Button size="sm" variant="ghost" className="justify-start gap-2 text-blue-600" onClick={triggerTool}>
          <Wrench size={14} /> 模拟工具
        </Button>
        <Button size="sm" variant="ghost" className="justify-start gap-2 text-zinc-400" onClick={triggerReset}>
          <Sparkles size={14} /> 重置空闲
        </Button>
      </div>
    </div>
  );
}
