import { useEffect, useMemo, useRef, useState } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  Code2,
  Clock3,
  Database,
  Loader2,
  MessageSquarePlus,
  Plus,
  Send,
  Sparkles,
  Table2,
  UploadCloud,
  X,
} from 'lucide-react';

import { apiClient } from '@/api/client';
import { modelApi, type ModelConfig } from '@/api/models';
import AiLogo from '@/assets/logo/ai_logo.png';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { TypingEffectMarkdown } from '@/features/agent-workspace/components/chat-panel/TypingEffectMarkdown';
import { useAuthStore } from '@/store/useAuthStore';
import type {
  ChatMessage,
  EvidenceItem,
  KnowledgeBase,
  SapAssistantSession,
  SapAssistantStoredMessage,
  SapSystem,
  TimelineItem,
  ToolResult,
} from '@/features/sap-assistant/types';

const WELCOME_MESSAGE = '你好，我是 SAP 助手。可以问我事务码、RFC 函数、字段血缘、ZILOG 日志或知识库中的问题。';

const SUGGESTED_QUESTIONS = [
  '帮我分析事务码 VSD220 的开票金额取数逻辑',
  '查一下某个字段从哪里来，经过了哪些增强或函数',
  '根据 ZILOG 日志解释一次接口失败的原因',
  '先看 DDIC，再读取少量样例数据验证判断',
];

type VisibleStoredMessage = SapAssistantStoredMessage & { role: ChatMessage['role'] };
type ResourceType = 'source' | 'structure' | 'data' | 'object';
type ResourceFilter = ResourceType | 'all';

interface ResourceItem {
  id: string;
  title: string;
  type: ResourceType;
  status: TimelineItem['status'];
  summary: string;
  payload?: unknown;
  evidence?: EvidenceItem[];
  toolName?: string;
  messageId: string;
  durationMs?: number;
}

function createClientId(prefix: string) {
  if (globalThis.crypto?.randomUUID) {
    return globalThis.crypto.randomUUID();
  }

  if (globalThis.crypto?.getRandomValues) {
    const values = new Uint32Array(2);
    globalThis.crypto.getRandomValues(values);
    return `${prefix}-${Date.now().toString(36)}-${Array.from(values, (value) => value.toString(36)).join('')}`;
  }

  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}

export default function SapAssistantPage() {
  const [systems, setSystems] = useState<SapSystem[]>([]);
  const [models, setModels] = useState<ModelConfig[]>([]);
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);
  const [sessions, setSessions] = useState<SapAssistantSession[]>([]);
  const [selectedSystemId, setSelectedSystemId] = useState<number | ''>('');
  const [selectedModelName, setSelectedModelName] = useState('');
  const [enableReasoning, setEnableReasoning] = useState(false);
  const [selectedKbIds, setSelectedKbIds] = useState<number[]>([]);
  const [newKbName, setNewKbName] = useState('');
  const [newKbDescription, setNewKbDescription] = useState('');
  const [isCreatingKb, setIsCreatingKb] = useState(false);
  const [isUploadingDoc, setIsUploadingDoc] = useState(false);
  const [isLoadingSession, setIsLoadingSession] = useState(false);
  const [kbNotice, setKbNotice] = useState('');
  const [messages, setMessages] = useState<ChatMessage[]>([
    { id: 'welcome', role: 'assistant', content: WELCOME_MESSAGE },
  ]);
  const [input, setInput] = useState('');
  const [sessionId, setSessionId] = useState<number | null>(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const [activeResourceId, setActiveResourceId] = useState<string | null>(null);
  const [resourceRatio, setResourceRatio] = useState(0.5);
  const [isResizingResource, setIsResizingResource] = useState(false);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const splitPaneRef = useRef<HTMLElement | null>(null);
  const typewriterTimerRef = useRef<number | null>(null);
  const pendingTextRef = useRef('');
  const visibleAnswerRef = useRef('');
  const token = useAuthStore((state) => state.token);

  const selectedSystem = useMemo(
    () => systems.find((item) => item.id === selectedSystemId),
    [selectedSystemId, systems],
  );
  const currentSession = useMemo(
    () => sessions.find((item) => item.id === sessionId),
    [sessionId, sessions],
  );
  const isPristineSession = messages.length === 1 && messages[0]?.id === 'welcome';
  const resourceItems = useMemo(() => collectResourceItems(messages), [messages]);
  const activeResource = useMemo(
    () => resourceItems.find((item) => item.id === activeResourceId) ?? null,
    [activeResourceId, resourceItems],
  );

  const refreshKnowledgeBases = async () => {
    const data = await apiClient.get('/knowledge-bases');
    setKnowledgeBases((data ?? []) as unknown as KnowledgeBase[]);
  };

  const refreshSessions = async () => {
    const data = await apiClient.get('/sap/assistant/sessions');
    setSessions((data ?? []) as unknown as SapAssistantSession[]);
  };

  useEffect(() => {
    void Promise.all([
      apiClient.get('/sap/systems').then((data) => {
        const list = (data ?? []) as unknown as SapSystem[];
        setSystems(list);
        if (list.length > 0) setSelectedSystemId(list[0].id);
      }),
      modelApi.getList().then((data) => {
        setModels((data ?? []).filter((item) => item.is_enabled && item.model_type === 'chat'));
      }),
      refreshKnowledgeBases(),
      refreshSessions(),
    ]);
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  useEffect(() => {
    if (!activeResourceId || resourceItems.some((item) => item.id === activeResourceId)) return;
    setActiveResourceId(resourceItems[0]?.id ?? null);
  }, [activeResourceId, resourceItems]);

  useEffect(() => {
    if (!isResizingResource) return;

    const handlePointerMove = (event: PointerEvent) => {
      const rect = splitPaneRef.current?.getBoundingClientRect();
      if (!rect) return;
      const nextWidth = rect.right - event.clientX;
      setResourceRatio(Math.min(0.7, Math.max(0.3, nextWidth / rect.width)));
    };
    const stopResize = () => setIsResizingResource(false);

    window.addEventListener('pointermove', handlePointerMove);
    window.addEventListener('pointerup', stopResize, { once: true });
    return () => {
      window.removeEventListener('pointermove', handlePointerMove);
      window.removeEventListener('pointerup', stopResize);
    };
  }, [isResizingResource]);

  useEffect(() => () => {
    if (typewriterTimerRef.current) window.clearInterval(typewriterTimerRef.current);
  }, []);

  const waitForTypewriterDrain = async () => {
    for (let i = 0; i < 240; i += 1) {
      if (!pendingTextRef.current) return;
      await new Promise((resolve) => window.setTimeout(resolve, 30));
    }
  };

  const startNewSession = () => {
    if (isStreaming) return;
    setSessionId(null);
    setMessages([{ id: 'welcome', role: 'assistant', content: WELCOME_MESSAGE }]);
    setActiveResourceId(null);
    pendingTextRef.current = '';
    visibleAnswerRef.current = '';
  };

  const loadSession = async (id: number) => {
    if (isStreaming || isLoadingSession) return;
    setIsLoadingSession(true);
    try {
      const data = await apiClient.get(`/sap/assistant/sessions/${id}/messages`);
      const stored = (data ?? []) as unknown as SapAssistantStoredMessage[];
      const restored = stored
        .filter((item): item is VisibleStoredMessage => item.role === 'user' || item.role === 'assistant')
        .map<ChatMessage>((item) => ({
          id: String(item.id),
          role: item.role,
          content: item.content,
          timeline: item.message_metadata?.timeline,
          toolResults: item.message_metadata?.tool_results,
          evidence: item.message_metadata?.evidence,
        }));
      setSessionId(id);
      setMessages(restored.length ? restored : [{ id: 'welcome', role: 'assistant', content: WELCOME_MESSAGE }]);
      setActiveResourceId(null);
    } finally {
      setIsLoadingSession(false);
    }
  };

  const handleSend = async () => {
    const text = input.trim();
    if (!text || isStreaming) return;

    setInput('');
    setIsStreaming(true);

    const userMessage: ChatMessage = { id: createClientId('user'), role: 'user', content: text };
    const assistantId = createClientId('assistant');
    pendingTextRef.current = '';
    visibleAnswerRef.current = '';
    if (typewriterTimerRef.current) window.clearInterval(typewriterTimerRef.current);
    typewriterTimerRef.current = window.setInterval(() => {
      if (!pendingTextRef.current) return;
      const step = pendingTextRef.current.length > 240 ? 8 : pendingTextRef.current.length > 80 ? 5 : 2;
      const next = pendingTextRef.current.slice(0, step);
      pendingTextRef.current = pendingTextRef.current.slice(step);
      visibleAnswerRef.current += next;
      setMessages((items) =>
        items.map((item) => (item.id === assistantId ? { ...item, content: visibleAnswerRef.current, isStreaming: true } : item)),
      );
    }, 28);
    setMessages((items) => [...items, userMessage, { id: assistantId, role: 'assistant', content: '', isStreaming: true }]);

    try {
      const response = await fetch('/api/v1/sap/assistant/chat/stream', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          message: text,
          session_id: sessionId,
          sap_system_id: selectedSystemId || null,
          model_name: selectedModelName || null,
          enable_reasoning: enableReasoning,
          knowledge_base_ids: selectedKbIds,
        }),
      });

      if (!response.ok || !response.body) {
        throw new Error('SAP 助手流式接口不可用');
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const events = buffer.split('\n\n');
        buffer = events.pop() ?? '';

        for (const event of events) {
          const line = event.split('\n').find((item) => item.startsWith('data: '));
          if (!line) continue;
          const chunk = JSON.parse(line.slice(6));
          if (chunk.type === 'text_delta') {
            pendingTextRef.current += chunk.data.content ?? '';
          }
          if (chunk.type === 'text_done') {
            setSessionId(chunk.data.sessionId);
            void refreshSessions();
          }
          if (chunk.type === 'session_context') {
            setSessionId(chunk.data.sessionId);
          }
          if (chunk.type === 'thought_node') {
            const nextTimeline: TimelineItem = {
              id: chunk.data.nodeId,
              title: chunk.data.toolName || chunk.data.nodeId,
              status: chunk.data.status,
              detail: chunk.data.detailStr,
              toolName: chunk.data.toolName,
            };
            setMessages((items) =>
              items.map((item) =>
                item.id === assistantId
                  ? {
                      ...item,
                      timeline: upsertTimeline(item.timeline ?? [], nextTimeline),
                    }
                  : item,
              ),
            );
          }
          if (chunk.type === 'tool_output') {
            const nextResult = chunk.data.content as ToolResult;
            setMessages((items) =>
              items.map((item) =>
                item.id === assistantId
                  ? {
                      ...item,
                      toolResults: upsertToolResult(item.toolResults ?? [], nextResult),
                    }
                  : item,
              ),
            );
            setActiveResourceId((value) => value ?? resourceIdForTool(assistantId, nextResult, 0));
          }
          if (chunk.type === 'evidence') {
            const nextEvidence = chunk.data as EvidenceItem;
            setMessages((items) =>
              items.map((item) =>
                item.id === assistantId
                  ? {
                      ...item,
                      evidence: upsertEvidence(item.evidence ?? [], nextEvidence),
                    }
                  : item,
              ),
            );
          }
        }
      }

      await waitForTypewriterDrain();
      setMessages((items) => items.map((item) => (item.id === assistantId ? { ...item, content: visibleAnswerRef.current, isStreaming: false } : item)));
    } catch (error) {
      setMessages((items) =>
        items.map((item) =>
          item.id === assistantId
            ? { ...item, content: error instanceof Error ? error.message : '请求失败，请稍后重试。', isStreaming: false }
            : item,
        ),
      );
    } finally {
      if (typewriterTimerRef.current) {
        window.clearInterval(typewriterTimerRef.current);
        typewriterTimerRef.current = null;
      }
      setIsStreaming(false);
    }
  };

  const toggleKnowledgeBase = (id: number) => {
    setSelectedKbIds((items) => (items.includes(id) ? items.filter((item) => item !== id) : [...items, id]));
  };

  const handleCreateKnowledgeBase = async () => {
    const name = newKbName.trim();
    if (!name || isCreatingKb) return;
    setIsCreatingKb(true);
    setKbNotice('');
    try {
      const created = await apiClient.post('/knowledge-bases', {
        name,
        description: newKbDescription.trim() || null,
        is_public: false,
      }) as unknown as KnowledgeBase;
      await refreshKnowledgeBases();
      setSelectedKbIds((items) => Array.from(new Set([...items, created.id])));
      setNewKbName('');
      setNewKbDescription('');
      setKbNotice(`知识库“${created.name}”已创建，可以上传文档。`);
    } catch (error) {
      setKbNotice(error instanceof Error ? error.message : '知识库创建失败，请稍后重试。');
    } finally {
      setIsCreatingKb(false);
    }
  };

  const handleUploadDocument = async (file: File | null | undefined) => {
    if (!file || isUploadingDoc) return;
    const targetKbId = selectedKbIds[0] || knowledgeBases[0]?.id;
    if (!targetKbId) {
      setKbNotice('请先创建一个知识库，再上传文档。');
      return;
    }
    setIsUploadingDoc(true);
    setKbNotice('');
    try {
      const formData = new FormData();
      formData.append('file', file);
      await apiClient.post(`/knowledge-bases/${targetKbId}/documents`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: 60000,
      });
      await refreshKnowledgeBases();
      setSelectedKbIds((items) => Array.from(new Set([...items, targetKbId])));
      setKbNotice(`文档“${file.name}”已上传并完成第一版索引。`);
    } catch (error) {
      setKbNotice(error instanceof Error ? error.message : '文档上传失败，请检查文件类型或稍后重试。');
    } finally {
      setIsUploadingDoc(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  return (
    <div className="flex h-full min-h-0 overflow-hidden bg-[#f7f8fa] text-[#171717]">
      <input
        ref={fileInputRef}
        type="file"
        className="hidden"
        accept=".txt,.md,.docx,.xlsx,.pdf"
        onChange={(event) => void handleUploadDocument(event.target.files?.[0])}
      />

      <aside className="hidden w-[320px] shrink-0 flex-col overflow-hidden border-r border-[#f0ece4] bg-white shadow-[12px_0_36px_rgba(42,38,30,0.025)] lg:flex">
        <div className="p-4">
          <div className="mb-5 flex items-center gap-3 px-1">
            <img src={AiLogo} alt="AI Platform" className="h-11 w-11 object-contain" />
            <div className="min-w-0">
              <div className="truncate text-[15px] font-semibold">SAP 助手</div>
              <div className="mt-0.5 text-xs text-[#7a7f87]">证据链调查工作区</div>
            </div>
          </div>
          <Button className="h-10 w-full justify-start rounded-2xl bg-[#f0faf7] text-[#275b55] hover:bg-[#e4f3ef]" onClick={startNewSession} disabled={isStreaming}>
            <MessageSquarePlus className="h-4 w-4" />
            新会话
          </Button>
        </div>

        <div className="min-h-0 flex-1 overflow-auto px-3 pb-4">
          <div className="mb-2 flex items-center justify-between px-2">
            <span className="text-xs font-medium text-[#7a7f87]">历史会话</span>
            <span className="text-xs text-[#b0aaa0]">{sessions.length}</span>
          </div>
          <div className="space-y-2.5">
            {sessions.length === 0 ? (
              <div className="rounded-3xl border border-dashed border-[#e4e7eb] bg-[#f9fafb] px-4 py-5 text-sm leading-6 text-[#7a7f87]">
                暂无历史会话。发送问题后，这里会保留调查上下文。
              </div>
            ) : (
              sessions.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  className={`w-full rounded-3xl px-4 py-4 text-left transition ${
                    item.id === sessionId
                      ? 'bg-[#eefbf8] text-[#173d39] shadow-[inset_0_0_0_1px_rgba(47,111,104,0.12)]'
                      : 'bg-transparent text-[#34383f] hover:bg-[#f7f8fa]'
                  }`}
                  onClick={() => void loadSession(item.id)}
                  disabled={isStreaming || isLoadingSession}
                >
                  <div className="line-clamp-2 text-sm font-medium leading-5">{item.title || 'SAP 助手会话'}</div>
                  <div className="mt-3 flex items-center justify-between text-xs text-[#7a7f87]">
                    <span>{formatSessionTime(item.update_time)}</span>
                    {item.id === sessionId ? <span className="h-1.5 w-1.5 rounded-full bg-[#2f6f68]" /> : null}
                  </div>
                </button>
              ))
            )}
          </div>
        </div>
      </aside>

      <section className="ml-0 flex min-w-0 flex-1 flex-col overflow-hidden bg-white">
        <header className="flex h-16 shrink-0 items-center justify-between gap-4 border-b border-[#edf0f3] px-6">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="truncate text-base font-semibold text-[#171717]">SAP 助手</span>
              <span className="rounded-full bg-[#f0faf7] px-2.5 py-1 text-xs text-[#2f6f68]">受控 RFC</span>
            </div>
            <div className="mt-1 truncate text-xs text-[#7a7f87]">
              {currentSession?.title || selectedSystem?.name || '选择系统后开始排查'}
            </div>
          </div>
          {resourceItems.length > 0 ? (
            <button
              type="button"
              onClick={() => setActiveResourceId(activeResource?.id ? null : resourceItems[0].id)}
              className="rounded-full border border-[#e4e7eb] bg-white px-3 py-2 text-sm text-[#3f4650] transition hover:bg-[#f7f8fa]"
            >
              {activeResource ? '收起资源' : `资源 ${resourceItems.length}`}
            </button>
          ) : null}
        </header>

        <main ref={splitPaneRef} className="flex min-h-0 flex-1 overflow-hidden">
          <section className="flex min-w-0 flex-1 flex-col items-center overflow-hidden bg-[linear-gradient(180deg,#ffffff_0%,#f8fafc_100%)]">
            <div className="min-h-0 w-full flex-1 overflow-y-auto overflow-x-hidden px-4 py-8">
              <div className="mx-auto flex w-full max-w-[860px] flex-col gap-5">
                {isPristineSession ? (
                  <WelcomePanel onPick={setInput} />
                ) : (
                  messages.map((message) => (
                    <ChatBubble
                      key={message.id}
                      message={message}
                      onOpenResource={(timelineItem) => {
                        const matchedResource = resourceItems.find((item) => item.messageId === message.id && item.toolName === timelineItem.toolName);
                        setActiveResourceId(matchedResource?.id ?? resourceItems[0]?.id ?? null);
                      }}
                    />
                  ))
                )}
                <div ref={bottomRef} />
              </div>
            </div>

            <footer className="w-full shrink-0 px-4 pb-5 pt-3">
              <div className="mx-auto max-w-[780px]">
                <div className="relative rounded-[26px] border border-[#dfe3e8] bg-[#f3f4f6] p-1.5 shadow-[0_18px_48px_rgba(15,23,42,0.08)]">
                  <div className="flex items-end gap-2 rounded-[21px] border border-[#eef1f4] bg-white px-3 py-2 shadow-[0_1px_2px_rgba(15,23,42,0.04)]">
                    <button
                      type="button"
                      className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-[#7b838d] transition hover:bg-[#f2f4f7] hover:text-[#2f6f68]"
                      onClick={() => fileInputRef.current?.click()}
                      aria-label="上传知识库文档"
                    >
                      <Plus className="h-5 w-5" />
                    </button>
                    <textarea
                      className="max-h-40 min-h-11 flex-1 resize-none bg-transparent py-2 text-[15px] leading-6 text-[#171717] outline-none placeholder:text-[#9aa2ad]"
                      rows={2}
                      value={input}
                      onChange={(event) => setInput(event.target.value)}
                      onKeyDown={(event) => {
                        if (event.key === 'Enter' && !event.shiftKey) {
                          event.preventDefault();
                          void handleSend();
                        }
                      }}
                      placeholder="例如：VSD220 中的开票金额是怎么取的"
                    />
                    <button
                      type="button"
                      className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-[#8d949d] text-white transition hover:bg-[#727981] disabled:bg-[#eef1f3] disabled:text-[#b7bec7]"
                      onClick={() => void handleSend()}
                      disabled={isStreaming || !input.trim()}
                      aria-label="发送"
                    >
                      {isStreaming ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                    </button>
                  </div>
                  <ComposerControls
                    systems={systems}
                    models={models}
                    selectedSystemId={selectedSystemId}
                    selectedModelName={selectedModelName}
                    enableReasoning={enableReasoning}
                    knowledgeBases={knowledgeBases}
                    selectedKbIds={selectedKbIds}
                    newKbName={newKbName}
                    newKbDescription={newKbDescription}
                    isCreatingKb={isCreatingKb}
                    isUploadingDoc={isUploadingDoc}
                    notice={kbNotice}
                    onSystemChange={(value) => setSelectedSystemId(value ? Number(value) : '')}
                    onModelChange={setSelectedModelName}
                    onReasoningChange={setEnableReasoning}
                    onToggleKb={toggleKnowledgeBase}
                    onNameChange={setNewKbName}
                    onDescriptionChange={setNewKbDescription}
                    onCreate={() => void handleCreateKnowledgeBase()}
                    onUpload={() => fileInputRef.current?.click()}
                  />
                </div>
              </div>
            </footer>
          </section>
          {activeResource ? (
            <>
              <div
                role="separator"
                aria-label="调整资源区宽度"
                className="hidden w-3 shrink-0 cursor-col-resize items-center justify-center bg-[#f7f8fa] text-[#c8d0d8] transition hover:bg-[#eef2f5] lg:flex"
                onPointerDown={(event) => {
                  event.preventDefault();
                  setIsResizingResource(true);
                }}
              >
                <span className="h-10 w-1 rounded-full bg-current" />
              </div>
              <ResourcePanel
                items={resourceItems}
                activeId={activeResource.id}
                widthRatio={resourceRatio}
                onSelect={setActiveResourceId}
                onClose={() => setActiveResourceId(null)}
              />
            </>
          ) : null}
        </main>
      </section>
    </div>
  );
}

function CompactSelect({
  value,
  onChange,
  label,
  options,
  placeholder,
}: {
  value: string | number;
  onChange: (value: string) => void;
  label: string;
  options: Array<{ value: string; label: string }>;
  placeholder: string;
}) {
  return (
    <Select value={String(value)} onValueChange={onChange}>
      <SelectTrigger
        aria-label={label}
        size="sm"
        className="hidden h-8 max-w-[230px] rounded-lg border-0 bg-transparent px-2 text-[13px] text-[#555d67] shadow-none ring-0 transition hover:bg-white/80 focus:ring-2 focus:ring-[#c9ddd8] sm:flex [&>svg]:ml-1 [&>svg]:text-[#87909a]"
      >
        <SelectValue placeholder={placeholder} />
      </SelectTrigger>
      <SelectContent
        position="popper"
        align="start"
        className="z-80 max-h-72 min-w-[260px] rounded-2xl border-[#dde3e8] bg-white p-1.5 text-[#1f2933] shadow-[0_18px_48px_rgba(15,23,42,0.14)]"
      >
        {options.map((option) => (
          <SelectItem
            key={option.value}
            value={option.value}
            className="rounded-xl px-3 py-2 text-sm focus:bg-[#eef8f6] focus:text-[#173d39] data-[state=checked]:bg-[#eef8f6] data-[state=checked]:text-[#173d39]"
          >
            {option.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

function ComposerControls({
  systems,
  models,
  selectedSystemId,
  selectedModelName,
  enableReasoning,
  knowledgeBases,
  selectedKbIds,
  newKbName,
  newKbDescription,
  isCreatingKb,
  isUploadingDoc,
  notice,
  onSystemChange,
  onModelChange,
  onReasoningChange,
  onToggleKb,
  onNameChange,
  onDescriptionChange,
  onCreate,
  onUpload,
}: {
  systems: SapSystem[];
  models: ModelConfig[];
  selectedSystemId: number | '';
  selectedModelName: string;
  enableReasoning: boolean;
  knowledgeBases: KnowledgeBase[];
  selectedKbIds: number[];
  newKbName: string;
  newKbDescription: string;
  isCreatingKb: boolean;
  isUploadingDoc: boolean;
  notice: string;
  onSystemChange: (value: string) => void;
  onModelChange: (value: string) => void;
  onReasoningChange: (value: boolean) => void;
  onToggleKb: (id: number) => void;
  onNameChange: (value: string) => void;
  onDescriptionChange: (value: string) => void;
  onCreate: () => void;
  onUpload: () => void;
}) {
  const systemOptions = [
    { value: 'auto', label: '让 AI 判断系统' },
    ...systems.map((system) => ({
      value: String(system.id),
      label: `${system.name} / ${system.client}`,
    })),
  ];
  const modelOptions = [
    { value: 'auto', label: '自动选择模型' },
    ...models.map((model) => ({
      value: model.model_name,
      label: `${model.model_name}${model.capability ? ` / ${model.capability}` : ''}`,
    })),
  ];

  return (
    <div className="flex min-h-11 flex-wrap items-center gap-1.5 px-2 py-1.5">
        <CompactSelect
          value={selectedSystemId === '' ? 'auto' : selectedSystemId}
          onChange={(nextValue) => onSystemChange(nextValue === 'auto' ? '' : nextValue)}
          label="SAP 系统"
          placeholder="选择 SAP 系统"
          options={systemOptions}
        />
        <CompactSelect
          value={selectedModelName || 'auto'}
          onChange={(nextValue) => onModelChange(nextValue === 'auto' ? '' : nextValue)}
          label="模型"
          placeholder="选择模型"
          options={modelOptions}
        />
        <button
          type="button"
          className={`inline-flex h-8 items-center gap-1.5 rounded-lg px-2.5 text-[13px] transition ${
            enableReasoning
              ? 'bg-[#e8f6f2] text-[#2f6f68]'
              : 'bg-transparent text-[#69707a] hover:bg-white/80'
          }`}
          onClick={() => onReasoningChange(!enableReasoning)}
        >
          <Sparkles className="h-4 w-4" />
          {enableReasoning ? '思考开' : '思考关'}
        </button>
        <KnowledgeBaseMenu
          knowledgeBases={knowledgeBases}
          selectedKbIds={selectedKbIds}
          newKbName={newKbName}
          newKbDescription={newKbDescription}
          isCreatingKb={isCreatingKb}
          isUploadingDoc={isUploadingDoc}
          notice={notice}
          onToggleKb={onToggleKb}
          onNameChange={onNameChange}
          onDescriptionChange={onDescriptionChange}
          onCreate={onCreate}
          onUpload={onUpload}
        />
    </div>
  );
}

function KnowledgeBaseMenu({
  knowledgeBases,
  selectedKbIds,
  newKbName,
  newKbDescription,
  isCreatingKb,
  isUploadingDoc,
  notice,
  onToggleKb,
  onNameChange,
  onDescriptionChange,
  onCreate,
  onUpload,
}: {
  knowledgeBases: KnowledgeBase[];
  selectedKbIds: number[];
  newKbName: string;
  newKbDescription: string;
  isCreatingKb: boolean;
  isUploadingDoc: boolean;
  notice: string;
  onToggleKb: (id: number) => void;
  onNameChange: (value: string) => void;
  onDescriptionChange: (value: string) => void;
  onCreate: () => void;
  onUpload: () => void;
}) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
      <button
        type="button"
        className="inline-flex h-8 items-center gap-1.5 rounded-lg bg-transparent px-2.5 text-[13px] text-[#69707a] transition hover:bg-white/80 data-[state=open]:bg-white/90 data-[state=open]:text-[#2f3a43]"
      >
        知识库
        {selectedKbIds.length ? <span className="rounded-full bg-white px-2 py-0.5 text-[11px] text-[#2f6f68]">{selectedKbIds.length}</span> : null}
        <ChevronDown className="h-4 w-4 text-[#87909a]" />
      </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent
        side="top"
        align="start"
        sideOffset={10}
        className="z-100 max-h-[min(520px,var(--radix-dropdown-menu-content-available-height))] w-[380px] overflow-y-auto rounded-[24px] border-[#d9e0e7] bg-white p-4 text-[#171717] shadow-[0_24px_70px_rgba(15,23,42,0.16)]"
      >
        <div className="mb-3 text-sm font-semibold text-[#171717]">本轮知识库</div>
        <div className="flex max-h-40 flex-wrap gap-2 overflow-y-auto pr-1">
          {knowledgeBases.map((kb) => (
            <button
              key={kb.id}
              type="button"
              onClick={() => onToggleKb(kb.id)}
              className={`rounded-full border px-3 py-1.5 text-xs transition ${
                selectedKbIds.includes(kb.id)
                  ? 'border-[#bcd8d3] bg-[#eefbf8] text-[#2f6f68]'
                  : 'border-[#dde3e8] bg-white text-[#3f4650] hover:bg-[#f7f8fa]'
              }`}
            >
              {kb.name}
            </button>
          ))}
          {knowledgeBases.length === 0 ? <span className="text-sm text-[#7a7f87]">暂无知识库</span> : null}
        </div>
        <div className="mt-3 grid gap-2">
          <input
            className="h-10 rounded-2xl border border-[#dde3e8] bg-white px-3 text-sm outline-none focus:border-[#b9c9d4]"
            value={newKbName}
            onChange={(event) => onNameChange(event.target.value)}
            placeholder="新知识库名称"
          />
          <input
            className="h-10 rounded-2xl border border-[#dde3e8] bg-white px-3 text-sm outline-none focus:border-[#b9c9d4]"
            value={newKbDescription}
            onChange={(event) => onDescriptionChange(event.target.value)}
            placeholder="说明，可选"
          />
          <div className="grid grid-cols-2 gap-2">
            <button
              type="button"
              className="inline-flex h-10 items-center justify-center gap-2 rounded-2xl bg-[#2f6f68] px-3 text-sm font-medium text-white disabled:opacity-50"
              onClick={onCreate}
              disabled={!newKbName.trim() || isCreatingKb}
            >
              {isCreatingKb ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
              新建
            </button>
            <button
              type="button"
              className="inline-flex h-10 items-center justify-center gap-2 rounded-2xl border border-[#dde3e8] bg-white px-3 text-sm text-[#3f4650] hover:bg-[#f7f8fa]"
              onClick={onUpload}
              disabled={isUploadingDoc}
            >
              {isUploadingDoc ? <Loader2 className="h-4 w-4 animate-spin" /> : <UploadCloud className="h-4 w-4" />}
              上传
            </button>
          </div>
        </div>
        {notice ? <div className="mt-3 rounded-2xl bg-[#f7f8fa] px-3 py-2 text-xs leading-5 text-[#69707a]">{notice}</div> : null}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function ResourcePanel({
  items,
  activeId,
  widthRatio,
  onSelect,
  onClose,
}: {
  items: ResourceItem[];
  activeId: string;
  widthRatio: number;
  onSelect: (id: string) => void;
  onClose: () => void;
}) {
  const [activeFilter, setActiveFilter] = useState<ResourceFilter>('all');
  const sourceCount = items.filter((item) => item.type === 'source').length;
  const structureCount = items.filter((item) => item.type === 'structure').length;
  const dataCount = items.filter((item) => item.type === 'data').length;
  const objectCount = items.filter((item) => item.type === 'object').length;
  const visibleItems = activeFilter === 'all' ? items : items.filter((item) => item.type === activeFilter);
  const activeItem = visibleItems.find((item) => item.id === activeId) ?? visibleItems[0] ?? items[0];
  const activeMeta = resourceMeta(activeItem);
  const filters: Array<{ value: ResourceFilter; label: string; count: number }> = [
    { value: 'all', label: '全部', count: items.length },
    { value: 'source', label: '源码', count: sourceCount },
    { value: 'structure', label: '结构', count: structureCount },
    { value: 'data', label: '数据', count: dataCount },
    { value: 'object', label: '其他', count: objectCount },
  ];

  return (
    <aside
      className="hidden min-h-0 shrink-0 border-l border-[#edf0f3] bg-[#f8fafc] lg:flex lg:flex-col"
      style={{ width: `${Math.round(widthRatio * 1000) / 10}%` }}
    >
      <div className="flex h-14 shrink-0 items-center justify-between border-b border-[#edf0f3] px-4">
        <div>
          <div className="text-sm font-semibold text-[#171717]">资源</div>
          <div className="text-xs text-[#7a7f87]">源码、结构和样例数据</div>
        </div>
        <button type="button" className="rounded-full p-2 text-[#7a7f87] hover:bg-[#eef2f5]" onClick={onClose} aria-label="关闭资源区">
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="flex h-11 shrink-0 items-center gap-2 border-b border-[#edf0f3] px-4 text-xs text-[#69707a]">
        {filters.map((filter) => (
          <button
            key={filter.value}
            type="button"
            disabled={filter.count === 0}
            onClick={() => {
              setActiveFilter(filter.value);
              const nextItem = filter.value === 'all' ? items[0] : items.find((item) => item.type === filter.value);
              if (nextItem) onSelect(nextItem.id);
            }}
            className={`rounded-full px-2.5 py-1 transition ${
              activeFilter === filter.value
                ? 'bg-white text-[#173d39] ring-1 ring-[#c7ddd8]'
                : 'text-[#69707a] hover:bg-white/80 disabled:cursor-not-allowed disabled:opacity-40'
            }`}
          >
            {filter.label} {filter.count}
          </button>
        ))}
      </div>

      <div className="flex min-h-0 flex-1">
        <nav className="min-h-0 w-[176px] shrink-0 overflow-auto border-r border-[#edf0f3]">
          <div className="divide-y divide-[#edf0f3]">
            {visibleItems.map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => onSelect(item.id)}
                className={`flex w-full gap-2 px-3 py-3 text-left transition ${
                  item.id === activeItem.id ? 'bg-white text-[#173d39]' : 'text-[#3f4650] hover:bg-white/80'
                }`}
              >
                <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-xl bg-[#f0faf7] text-[#2f6f68]">
                  <ResourceIcon type={item.type} />
                </span>
                <span className="min-w-0">
                  <span className="line-clamp-2 text-xs font-medium leading-5">{item.title}</span>
                  <span className="mt-1 block text-[11px] text-[#7a7f87]">{resourceTypeLabel(item.type)}</span>
                </span>
              </button>
            ))}
          </div>
        </nav>

        <section className="flex min-w-0 flex-1 flex-col">
          <div className="shrink-0 border-b border-[#edf0f3] px-4 py-3">
            <div className="flex items-center gap-2">
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-[#f0faf7] text-[#2f6f68]">
                <ResourceIcon type={activeItem.type} />
              </span>
              <div className="min-w-0">
                <div className="truncate text-sm font-semibold text-[#171717]">{activeItem.title}</div>
                <div className="text-xs text-[#7a7f87]">
                  {[resourceTypeLabel(activeItem.type), activeMeta].filter(Boolean).join(' · ')}
                </div>
              </div>
            </div>
          </div>
          <div className="min-h-0 flex-1 overflow-hidden p-4">
            <ResourceBody item={activeItem} />
          </div>
        </section>
      </div>
    </aside>
  );
}

function ResourceBody({ item }: { item: ResourceItem }) {
  const payload = normalizePayload(item.payload);

  if (item.type === 'source') {
    const lines = extractSourceLines(payload);
    return (
      <div className="flex h-full min-h-0 flex-col gap-3">
        <ResourceSummary item={item} />
        {lines.length ? (
          <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-2xl border border-[#dde3e8] bg-white">
            <div className="flex shrink-0 items-center justify-between border-b border-[#edf0f3] bg-[#f8fafc] px-4 py-2 text-xs text-[#69707a]">
              <span>ABAP 源码</span>
              <span>{lines.length} 行</span>
            </div>
            <pre className="min-h-0 flex-1 overflow-auto bg-[#fbfcfd] p-4 font-mono text-xs leading-6 text-[#1f2933]">
              <code>{lines.join('\n')}</code>
            </pre>
          </div>
        ) : (
          <EmptyResourceState type={item.type} />
        )}
      </div>
    );
  }

  if (item.type === 'structure') {
    const fields = extractFieldRows(payload);
    return (
      <div className="flex h-full min-h-0 flex-col gap-3">
        <ResourceSummary item={item} />
        {fields.length ? (
          <div className="min-h-0 flex-1 overflow-auto rounded-2xl border border-[#dde3e8] bg-white">
            <table className="min-w-full text-left text-xs">
              <thead className="sticky top-0 bg-[#f1f5f9] text-[#69707a]">
                <tr>
                  <th className="px-3 py-2 font-medium">字段</th>
                  <th className="px-3 py-2 font-medium">类型</th>
                  <th className="px-3 py-2 font-medium">长度</th>
                  <th className="px-3 py-2 font-medium">说明</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#edf0f3]">
                {fields.map((field, index) => (
                  <tr key={`${field.name}-${index}`}>
                    <td className="whitespace-nowrap px-3 py-2 font-medium text-[#171717]">{field.name}</td>
                    <td className="whitespace-nowrap px-3 py-2 text-[#3f4650]">{field.type}</td>
                    <td className="whitespace-nowrap px-3 py-2 text-[#3f4650]">{field.length}</td>
                    <td className="min-w-[180px] px-3 py-2 text-[#69707a]">{field.text}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <EmptyResourceState type={item.type} />}
      </div>
    );
  }

  if (item.type === 'data') {
    const table = extractDataTable(payload);
    return (
      <div className="flex h-full min-h-0 flex-col gap-3">
        <ResourceSummary item={item} />
        {table.fields.length && table.rows.length ? (
          <div className="min-h-0 flex-1 overflow-auto rounded-2xl border border-[#dde3e8] bg-white">
            <table className="min-w-full text-left text-xs">
              <thead className="sticky top-0 bg-[#f1f5f9] text-[#69707a]">
                <tr>
                  {table.fields.map((field) => (
                    <th key={field} className="whitespace-nowrap px-3 py-2 font-medium">{field}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-[#edf0f3]">
                {table.rows.map((row, rowIndex) => (
                  <tr key={rowIndex}>
                    {table.fields.map((field) => (
                      <td key={field} className="whitespace-nowrap px-3 py-2 text-[#3f3a33]">{row[field] ?? '-'}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <EmptyResourceState type={item.type} />}
      </div>
    );
  }

  if (item.type === 'object') {
    const details = extractObjectDetails(payload);
    const table = extractObjectTable(payload);
    return (
      <div className="flex h-full min-h-0 flex-col gap-3">
        <ResourceSummary item={item} />
        {details.length ? (
          <div className="grid gap-2 rounded-2xl border border-[#dde3e8] bg-white p-3 text-xs">
            {details.map(([key, value]) => (
              <div key={key} className="grid grid-cols-[88px_1fr] gap-3 rounded-xl bg-[#f8fafc] px-3 py-2">
                <span className="text-[#7a7f87]">{key}</span>
                <span className="break-words font-medium text-[#24313d]">{value || '-'}</span>
              </div>
            ))}
          </div>
        ) : null}
        {table.fields.length && table.rows.length ? (
          <div className="min-h-0 flex-1 overflow-auto rounded-2xl border border-[#dde3e8] bg-white">
            <table className="min-w-full text-left text-xs">
              <thead className="sticky top-0 bg-[#f1f5f9] text-[#69707a]">
                <tr>
                  {table.fields.map((field) => (
                    <th key={field} className="whitespace-nowrap px-3 py-2 font-medium">{field}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-[#edf0f3]">
                {table.rows.map((row, rowIndex) => (
                  <tr key={rowIndex}>
                    {table.fields.map((field) => (
                      <td key={field} className="whitespace-nowrap px-3 py-2 text-[#3f4650]">{row[field] ?? '-'}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </div>
    );
  }

  return <EmptyResourceState type={item.type} />;
}

function ResourceSummary({ item }: { item: ResourceItem }) {
  return (
    <div className="rounded-2xl border border-[#dde3e8] bg-white px-4 py-3 text-sm leading-6 text-[#3f4650]">
      {item.summary || '暂无摘要。'}
    </div>
  );
}

function EmptyResourceState({ type }: { type: ResourceType }) {
  return (
    <div className="rounded-2xl border border-dashed border-[#d6dde5] bg-white px-4 py-8 text-center text-sm text-[#7a7f87]">
      暂无可渲染的{resourceTypeLabel(type)}内容
    </div>
  );
}

function WelcomePanel({ onPick }: { onPick: (value: string) => void }) {
  return (
    <div className="flex min-h-[54vh] flex-col items-center justify-center text-center">
      <div className="relative">
        <img src={AiLogo} alt="SAP 助手" className="h-20 w-20 object-contain drop-shadow-[0_18px_32px_rgba(42,38,30,0.16)]" />
        <span className="absolute -right-1 -top-1 flex h-5 w-5 items-center justify-center rounded-full border-2 border-white bg-emerald-500" />
      </div>
      <h1 className="mt-6 text-[34px] font-semibold tracking-tight text-[#171717]">今天要调查哪条 SAP 线索？</h1>
      <p className="mt-3 max-w-2xl text-sm leading-6 text-[#69707a]">
        我会先判断意图，再通过受控 RFC、DDIC、源码和少量样例数据组织证据链。复杂问题可以开启思考模式。
      </p>
      <div className="mt-8 grid w-full max-w-3xl gap-3 md:grid-cols-2">
        {SUGGESTED_QUESTIONS.map((question) => (
          <button
            key={question}
            type="button"
            onClick={() => onPick(question)}
            className="group rounded-2xl border border-[#dde3e8] bg-white/94 p-4 text-left shadow-[0_10px_30px_rgba(15,23,42,0.035)] transition hover:-translate-y-0.5 hover:border-[#cfd8e3] hover:bg-white hover:shadow-[0_18px_42px_rgba(15,23,42,0.07)]"
          >
            <div className="flex items-start gap-3">
              <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-[#f2f5f7] text-[#3f4650]">
                <Sparkles className="h-4 w-4" />
              </span>
              <span className="text-sm font-medium leading-6 text-[#2f2c27]">{question}</span>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}

function ChatBubble({
  message,
  onOpenResource,
}: {
  message: ChatMessage;
  onOpenResource: (item: TimelineItem) => void;
}) {
  const isUser = message.role === 'user';

  return (
    <div className={`flex w-full min-w-0 ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div className={`flex min-w-0 gap-3 ${isUser ? 'max-w-[72%] flex-row-reverse' : 'w-full max-w-full'}`}>
        <div
          className={`mt-1 flex h-9 w-9 shrink-0 items-center justify-center overflow-hidden rounded-full text-sm ${
            isUser ? 'bg-[#eef3f2] text-[#275b55]' : 'text-[#333333]'
          }`}
        >
          {isUser ? '你' : <img src={AiLogo} alt="SAP 助手" className="h-full w-full object-contain" />}
        </div>
        <div
          className={`min-w-0 rounded-[22px] px-4 py-3 text-sm leading-7 ${
            isUser
              ? 'bg-[#f3f6f8] text-[#171717] shadow-[0_10px_28px_rgba(15,23,42,0.035)]'
              : 'w-full border border-[#f1ede6] bg-white text-[#171717] shadow-[0_10px_32px_rgba(0,0,0,0.035)]'
          }`}
        >
          {!isUser && message.timeline?.length ? (
            <InlineThoughtTimeline items={message.timeline} isStreaming={Boolean(message.isStreaming)} onOpenResource={onOpenResource} />
          ) : null}
          <MarkdownText
            text={message.content || (message.isStreaming ? '正在组织证据链回答...' : '')}
            isStreaming={message.isStreaming}
          />
        </div>
      </div>
    </div>
  );
}

function upsertTimeline(items: TimelineItem[], next: TimelineItem): TimelineItem[] {
  const index = items.findIndex((item) => item.id === next.id);
  if (index === -1) return [...items, next];
  const copy = [...items];
  copy[index] = { ...copy[index], ...next };
  return copy;
}

function upsertToolResult(items: ToolResult[], next: ToolResult): ToolResult[] {
  const index = items.findIndex(
    (item) =>
      item.tool_name === next.tool_name &&
      item.summary === next.summary &&
      item.duration_ms === next.duration_ms,
  );
  if (index === -1) return [...items, next];
  const copy = [...items];
  copy[index] = next;
  return copy;
}

function upsertEvidence(items: EvidenceItem[], next: EvidenceItem): EvidenceItem[] {
  const index = items.findIndex(
    (item) =>
      item.evidence_type === next.evidence_type &&
      item.title === next.title &&
      item.source_object === next.source_object &&
      item.location === next.location,
  );
  if (index === -1) return [...items, next];
  const copy = [...items];
  copy[index] = next;
  return copy;
}

function resourceIdForTool(messageId: string, result: ToolResult, index: number) {
  return `${messageId}:tool:${result.tool_name}:${index}`;
}

function resourceDedupKey(item: ResourceItem) {
  const payload = normalizePayload(item.payload);
  if (item.type === 'source') {
    const objectName = isRecord(payload)
      ? stringValue(payload.object || payload.resolvedProgram || payload.objectName || payload.name)
      : item.title;
    return `${item.type}:${objectName.toUpperCase() || item.title.toUpperCase()}`;
  }
  if (item.type === 'structure' || item.type === 'data') {
    return `${item.type}:${item.title.toUpperCase()}`;
  }
  return `${item.type}:${item.toolName ?? ''}:${item.title.toUpperCase()}`;
}

function collectResourceItems(messages: ChatMessage[]): ResourceItem[] {
  const resources = messages.flatMap((message) =>
    (message.toolResults ?? []).flatMap((item, index) => {
      const status = normalizeResourceStatus(item.status);
      const type = inferResourceType(item);
      const payload = normalizePayload(item.data);

      if (status !== 'success' || !isRenderableResourceTool(item.tool_name, type)) {
        return [];
      }
      if (!hasRenderablePayload(type, payload)) {
        return [];
      }

      return [{
        id: resourceIdForTool(message.id, item, index),
        title: resourceTitle(item),
        type,
        status,
        summary: item.summary,
        payload,
        evidence: item.evidence,
        toolName: item.tool_name,
        messageId: message.id,
        durationMs: item.duration_ms,
      }];
    }),
  );
  const seen = new Set<string>();
  return resources.filter((item) => {
    const key = resourceDedupKey(item);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function normalizeResourceStatus(status: string): TimelineItem['status'] {
  if (status === 'success' || status === 'failed' || status === 'skipped' || status === 'pending') return status;
  return 'success';
}

function inferResourceType(item: ToolResult): ResourceType {
  if (item.tool_name === 'tcode_info') {
    return 'object';
  }
  if (['program_source', 'function_source', 'source_full_text', 'source_slice'].includes(item.tool_name)) {
    return 'source';
  }
  if (item.tool_name === 'ddic_meta') {
    return 'structure';
  }
  if (['safe_table_read', 'latest_table_read'].includes(item.tool_name)) {
    return 'data';
  }

  const text = `${item.tool_name} ${item.summary ?? ''} ${(item.evidence ?? []).map((evidence) => evidence.evidence_type).join(' ')}`.toLowerCase();
  if (text.includes('source') || text.includes('program') || text.includes('function') || text.includes('源码') || text.includes('函数')) {
    return 'source';
  }
  if (text.includes('ddic') || text.includes('structure') || text.includes('field') || text.includes('结构') || text.includes('字段')) {
    return 'structure';
  }
  if (text.includes('table') || text.includes('data') || text.includes('read') || text.includes('表') || text.includes('数据')) {
    return 'data';
  }
  return 'object';
}

function isRenderableResourceTool(toolName: string, type: ResourceType) {
  if (type === 'source') return ['program_source', 'function_source', 'source_full_text', 'source_slice'].includes(toolName);
  if (type === 'structure') return toolName === 'ddic_meta';
  if (type === 'data') return ['safe_table_read', 'latest_table_read'].includes(toolName);
  if (type === 'object') return toolName === 'tcode_info';
  return false;
}

function hasRenderablePayload(type: ResourceType, payload: unknown) {
  if (type === 'source') return extractSourceLines(payload).length > 0;
  if (type === 'structure') return extractFieldRows(payload).length > 0;
  if (type === 'data') {
    const table = extractDataTable(payload);
    return table.fields.length > 0 && table.rows.length > 0;
  }
  if (type === 'object') return isRecord(payload) || Array.isArray(payload);
  return false;
}

function resourceTitle(item: ToolResult) {
  const payload = normalizePayload(item.data);
  if (isRecord(payload)) {
    const objectName =
      stringValue(payload.tcode) ||
      stringValue(payload.transaction) ||
      stringValue(payload.object) ||
      stringValue(payload.resolvedProgram) ||
      stringValue(payload.program) ||
      stringValue(payload.table) ||
      stringValue(payload.tableName);
    if (objectName) return objectName;
  }
  const evidenceTitle = item.evidence?.[0]?.source_object || item.evidence?.[0]?.title;
  if (evidenceTitle) return evidenceTitle;
  return toolNameLabel(item.tool_name);
}

function toolNameLabel(toolName: string) {
  const labels: Record<string, string> = {
    tcode_info: '事务码对象',
    program_source: '程序源码',
    function_source: '函数源码',
    source_full_text: '完整源码',
    ddic_meta: 'DDIC 结构',
    safe_table_read: '样例数据',
    latest_table_read: '最新数据',
    knowledge_search: '知识片段',
  };
  return labels[toolName] ?? toolName;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function normalizePayload(value: unknown): unknown {
  if (typeof value === 'string') {
    try {
      return normalizePayload(JSON.parse(value));
    } catch {
      return value;
    }
  }
  if (isRecord(value) && isRecord(value.JSON_PARSED)) return normalizePayload(value.JSON_PARSED);
  if (isRecord(value) && typeof value.JSON_PARSED === 'string') return normalizePayload(value.JSON_PARSED);
  if (isRecord(value) && isRecord(value.response) && !value.lines && !value.fields && !value.rows) {
    return normalizePayload(value.response);
  }
  return value;
}

function stringValue(value: unknown): string {
  if (value === null || value === undefined) return '';
  return String(value);
}

function firstArrayValue(record: Record<string, unknown>, keys: string[]): unknown[] | null {
  for (const key of keys) {
    const value = record[key];
    if (Array.isArray(value)) return value;
  }
  return null;
}

function firstStringValue(record: Record<string, unknown>, keys: string[]): string {
  for (const key of keys) {
    const value = record[key];
    if (typeof value === 'string' && value.trim()) return value;
  }
  return '';
}

function resourceMeta(item: ResourceItem) {
  const payload = normalizePayload(item.payload);
  if (item.type === 'source') {
    const lines = extractSourceLines(payload);
    return lines.length ? `${lines.length} 行 ABAP` : '';
  }
  if (item.type === 'structure') {
    const fields = extractFieldRows(payload);
    return fields.length ? `${fields.length} 个字段` : '';
  }
  if (item.type === 'data') {
    const table = extractDataTable(payload);
    return table.rows.length ? `${table.rows.length} 行 · ${table.fields.length} 列` : '';
  }
  if (item.type === 'object') {
    const table = extractObjectTable(payload);
    return table.rows.length ? `${table.rows.length} 条对象` : '对象信息';
  }
  return '';
}

function extractSourceLines(payload: unknown): string[] {
  const normalized = normalizePayload(payload);
  if (typeof normalized === 'string') {
    return normalized.split(/\r?\n/).filter((line) => line.trim().length > 0);
  }
  if (!isRecord(normalized)) return [];
  const textSource = firstStringValue(normalized, ['code', 'source', 'sourceText', 'fullSource', 'content', 'text']);
  if (textSource) {
    return textSource.split(/\r?\n/);
  }
  const lines = firstArrayValue(normalized, ['lines', 'sourceLines', 'linePreview', 'context']);
  if (!Array.isArray(lines)) return [];
  return lines.map((line, index) => {
    if (isRecord(line)) {
      const lineNo = stringValue(line.line || line.lineNo || line.LINE || index + 1).padStart(4, ' ');
      return `${lineNo}  ${stringValue(line.text || line.content || line.source || line.LINE || '')}`;
    }
    return `${String(index + 1).padStart(4, ' ')}  ${stringValue(line)}`;
  });
}

function extractFieldRows(payload: unknown): Array<{ name: string; type: string; length: string; text: string }> {
  const normalized = normalizePayload(payload);
  if (!isRecord(normalized)) return [];
  const fields = firstArrayValue(normalized, ['fields', 'components', 'items', 'tableFields', 'ddicFields']);
  if (!Array.isArray(fields)) return [];
  return fields.map((field) => {
    if (!isRecord(field)) {
      return { name: stringValue(field), type: '-', length: '-', text: '-' };
    }
    return {
      name: stringValue(field.fieldname || field.fieldName || field.name || field.FIELDNAME || field.FIELD),
      type: stringValue(field.datatype || field.dataType || field.type || field.DATATYPE || field.INTTYPE || field.rollname || field.ROLLNAME || '-'),
      length: stringValue(field.leng || field.length || field.LENG || field.OUTPUTLEN || field.DDLENG || '-'),
      text: stringValue(field.scrtext_l || field.scrtextL || field.text || field.description || field.FIELDTEXT || field.SCRTEXT_L || '-'),
    };
  }).filter((field) => field.name);
}

function extractDataTable(payload: unknown): { fields: string[]; rows: Array<Record<string, string>> } {
  const normalized = normalizePayload(payload);
  if (!isRecord(normalized)) return { fields: [], rows: [] };
  const rawFieldsSource = firstArrayValue(normalized, ['fields', 'columns', 'fieldNames']);
  const rawFields = Array.isArray(rawFieldsSource)
    ? rawFieldsSource.map((field) => {
      if (isRecord(field)) {
        return stringValue(field.fieldname || field.fieldName || field.name || field.FIELDNAME || field.FIELD);
      }
      return stringValue(field);
    }).filter(Boolean)
    : [];
  const rawRows = firstArrayValue(normalized, ['rows', 'items', 'records', 'data', 'values']) ?? [];
  const objectRows = rawRows.map((row) => {
    if (Array.isArray(row)) {
      return rawFields.reduce<Record<string, string>>((acc, field, index) => {
        acc[field || `列${index + 1}`] = stringValue(row[index]);
        return acc;
      }, {});
    }
    if (isRecord(row)) {
      const rowData = isRecord(row.values) ? row.values : row;
      return Object.fromEntries(Object.entries(rowData).map(([key, value]) => [key, stringValue(value)]));
    }
    return { value: stringValue(row) };
  });
  const fields = rawFields.length ? rawFields : Array.from(new Set(objectRows.flatMap((row) => Object.keys(row))));
  return { fields, rows: objectRows };
}

function extractObjectDetails(payload: unknown): Array<[string, string]> {
  const normalized = normalizePayload(payload);
  if (!isRecord(normalized)) return [];
  const labelMap: Record<string, string> = {
    tcode: '事务码',
    transaction: '事务码',
    object: '对象',
    objectName: '对象',
    program: '程序',
    pgmna: '程序',
    screen: '屏幕',
    dynpro: '屏幕',
    description: '说明',
    text: '说明',
    message: '消息',
  };
  return Object.entries(labelMap)
    .map(([key, label]) => [label, stringValue(normalized[key])] as [string, string])
    .filter(([, value], index, rows) => value && rows.findIndex(([label]) => label === rows[index][0]) === index)
    .slice(0, 8);
}

function extractObjectTable(payload: unknown): { fields: string[]; rows: Array<Record<string, string>> } {
  const normalized = normalizePayload(payload);
  if (!isRecord(normalized)) return { fields: [], rows: [] };
  const items = firstArrayValue(normalized, ['items', 'rows', 'programs', 'objects']) ?? [];
  const rows = items
    .filter(isRecord)
    .map((item) => Object.fromEntries(Object.entries(item).map(([key, value]) => [key, stringValue(value)])));
  const fields = Array.from(new Set(rows.flatMap((row) => Object.keys(row)))).slice(0, 12);
  return { fields, rows };
}

function resourceTypeLabel(type: ResourceType) {
  const labels: Record<ResourceType, string> = {
    source: '源码',
    structure: '结构',
    data: '数据',
    object: '其他',
  };
  return labels[type];
}

function ResourceIcon({ type }: { type: ResourceType }) {
  if (type === 'source') return <Code2 className="h-4 w-4" />;
  if (type === 'structure') return <Table2 className="h-4 w-4" />;
  if (type === 'data') return <Database className="h-4 w-4" />;
  return <Sparkles className="h-4 w-4" />;
}

function InlineThoughtTimeline({
  items,
  isStreaming,
  onOpenResource,
}: {
  items: TimelineItem[];
  isStreaming: boolean;
  onOpenResource: (item: TimelineItem) => void;
}) {
  const latest = items[items.length - 1];
  const [open, setOpen] = useState(isStreaming);

  return (
    <details
      className="mb-3 max-w-full overflow-hidden rounded-[20px] border border-[#dde3e8] bg-[#f8fafc] text-[#171717]"
      open={open}
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3">
        <div className="flex min-w-0 items-center gap-2">
          <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-white shadow-sm">
            {isStreaming ? <Loader2 className="h-4 w-4 animate-spin text-[#4a4a4a]" /> : <CheckCircle2 className="h-4 w-4 text-emerald-600" />}
          </span>
          <span className="truncate text-sm font-semibold">{isStreaming ? '正在调查' : '执行过程'}</span>
        </div>
        <span className="max-w-[42%] truncate text-xs text-[#7a7f87]">{latest?.detail || `${items.length} 个步骤`}</span>
      </summary>
      <div className="max-h-72 space-y-2 overflow-y-auto overflow-x-hidden border-t border-[#edf0f3] px-4 py-3">
        {items.map((item, index) => (
          <button
            key={`${item.id}-${index}`}
            type="button"
            onClick={() => onOpenResource(item)}
            className="grid w-full grid-cols-[22px_1fr] gap-3 rounded-2xl bg-white/88 p-3 text-left text-xs leading-5 transition hover:bg-white hover:shadow-sm"
          >
            <StatusIcon status={item.status} />
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <span className="font-medium text-[#171717]">{item.title}</span>
                <span className="rounded-full bg-[#eef2f5] px-2 py-0.5 text-[10px] text-[#69707a]">{statusLabel(item.status)}</span>
              </div>
              <p className="mt-1 break-words text-[#69707a]">{item.detail}</p>
            </div>
          </button>
        ))}
      </div>
    </details>
  );
}

function StatusIcon({ status }: { status: TimelineItem['status'] }) {
  if (status === 'success') return <CheckCircle2 className="h-5 w-5 text-emerald-600" />;
  if (status === 'failed') return <AlertTriangle className="h-5 w-5 text-rose-600" />;
  if (status === 'pending') return <Loader2 className="h-5 w-5 animate-spin text-[#4a4a4a]" />;
  return <Clock3 className="h-5 w-5 text-[#8a8a8a]" />;
}

function statusLabel(status: TimelineItem['status']) {
  const labels: Record<TimelineItem['status'], string> = {
    pending: '执行中',
    success: '完成',
    failed: '失败',
    skipped: '跳过',
  };
  return labels[status];
}

function MarkdownText({ text, isStreaming }: { text: string; isStreaming?: boolean }) {
  return (
    <TypingEffectMarkdown
      content={text}
      isStreaming={isStreaming}
      className="max-w-full overflow-hidden break-words leading-7 text-[#171717] prose-p:my-2 prose-p:break-words prose-strong:font-semibold prose-ol:my-2 prose-ul:my-2 prose-li:my-1 prose-li:break-words prose-code:break-all prose-code:rounded-md prose-code:bg-[#f4f4f4] prose-code:px-1.5 prose-code:py-0.5 prose-code:text-[#333333] prose-pre:max-w-full prose-pre:overflow-x-auto prose-pre:whitespace-pre-wrap prose-pre:bg-[#f7f7f7] prose-pre:text-[#171717]"
    />
  );
}

function formatSessionTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  return date.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
}
