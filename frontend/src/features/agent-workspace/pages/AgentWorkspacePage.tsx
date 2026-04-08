import { SplitPane } from '@/features/agent-workspace/components/layout/SplitPane';
import { MessageList } from '@/features/agent-workspace/components/chat-panel/MessageList';
import { ChatInputArea } from '@/features/agent-workspace/components/chat-panel/ChatInputArea';
import { ComponentDispatcher } from '@/features/agent-workspace/components/dynamic-workspace/ComponentDispatcher';
import { useWorkspaceStore } from '@/features/agent-workspace/hooks/useWorkspaceStore';

export function AgentWorkspacePage() {
  // 精准选择器，避免无关状态变化导致重绘
  const messages = useWorkspaceStore(state => state.messages);
  const activeWorkspaceType = useWorkspaceStore(state => state.activeWorkspaceType);
  const workspaceData = useWorkspaceStore(state => state.workspaceData);
  const isStreaming = useWorkspaceStore(state => state.isStreaming);
  
  const addMessage = useWorkspaceStore(state => state.addMessage);
  const updateLastMessage = useWorkspaceStore(state => state.updateLastMessage);
  const setWorkspace = useWorkspaceStore(state => state.setWorkspace);
  const setStreaming = useWorkspaceStore(state => state.setStreaming);

  const handleSendMessage = (text: string) => {
    // 1. 添加用户消息
    addMessage({ id: Date.now().toString(), role: 'user', content: text });
    
    // 2. 模拟 AI 响应开始
    setStreaming(true);
    const aiMsgId = (Date.now() + 1).toString();
    addMessage({ id: aiMsgId, role: 'assistant', content: '', isStreaming: true });

    // 3. 模拟右侧切换到思考状态
    setWorkspace('thought', [
      { nodeId: 'n1', act: 'planning', status: 'success', detailStr: '正在分析您的请求...' },
      { nodeId: 'n2', act: 'calling_tool', status: 'pending', detailStr: '准备调用搜索工具', toolName: 'web_search' }
    ]);

    // 4. 使用 rAF 模拟更平滑的打字效果
    const fullText = "收到您的请求，我正在为您处理中。基于目前的分析，我们需要调用搜索工具来获取最新信息。";
    let i = 0;
    let lastTime = 0;
    const charPerFrame = 2; // 每两帧渲染一个字左右

    const animate = (time: number) => {
      if (time - lastTime > 30) { // 控制在大约 30ms 更新一次
        if (i < fullText.length) {
          const nextI = Math.min(i + charPerFrame, fullText.length);
          const currentContent = fullText.slice(0, nextI);
          updateLastMessage(currentContent, true);
          i = nextI;
          lastTime = time;
          requestAnimationFrame(animate);
        } else {
          updateLastMessage(fullText, false);
          setStreaming(false);
          
          // 5. 模拟工具调用成功
          setTimeout(() => {
            setWorkspace('tool', {
              toolName: 'web_search',
              displayType: 'json',
              content: { status: "found", results: ["AI Platform 架构指南", "FastAPI + React 实战"] }
            });
          }, 1000);
        }
      } else {
        requestAnimationFrame(animate);
      }
    };
    
    requestAnimationFrame(animate);
  };

  return (
    <div className="h-screen w-full bg-zinc-50 dark:bg-zinc-950">
      <SplitPane
        left={
          <div className="flex-1 flex flex-col pt-6 overflow-hidden">
            <header className="px-6 mb-4 shrink-0">
              <div className="flex items-center gap-2 mb-1">
                <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                <h1 className="text-sm font-bold uppercase tracking-widest text-zinc-400">
                  Agent Workspace
                </h1>
              </div>
              <h2 className="text-xl font-semibold text-zinc-900 dark:text-zinc-100">
                智控中心 v1.0
              </h2>
            </header>
            
            <div className="flex-1 overflow-hidden flex flex-col">
              <MessageList messages={messages} isTyping={isStreaming} />
            </div>

            <div className="shrink-0 pt-4">
              <ChatInputArea onSend={handleSendMessage} disabled={isStreaming} />
            </div>
          </div>
        }
        right={
          <ComponentDispatcher activeType={activeWorkspaceType} data={workspaceData} />
        }
      />
    </div>
  );
}

export default AgentWorkspacePage;
