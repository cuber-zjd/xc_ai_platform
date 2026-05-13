import { useEffect, useMemo, useRef, useState } from 'react';
import type { RefObject } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  Clock3,
  Loader2,
  MessageSquarePlus,
  Plus,
  Send,
  UploadCloud,
} from 'lucide-react';

import { apiClient } from '@/api/client';
import { modelApi, type ModelConfig } from '@/api/models';
import { Button } from '@/components/ui/button';
import { TypingEffectMarkdown } from '@/features/agent-workspace/components/chat-panel/TypingEffectMarkdown';
import { useAuthStore } from '@/store/useAuthStore';
import type {
  ChatMessage,
  KnowledgeBase,
  SapAssistantSession,
  SapAssistantStoredMessage,
  SapSystem,
  TimelineItem,
} from '@/features/sap-assistant/types';

const WELCOME_MESSAGE = '你好，我是 SAP 助手。可以问我事务码、RFC 函数、字段血缘、ZILOG 日志或知识库中的问题。';

export default function SapAssistantPage() {
  const [systems, setSystems] = useState<SapSystem[]>([]);
  const [models, setModels] = useState<ModelConfig[]>([]);
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);
  const [sessions, setSessions] = useState<SapAssistantSession[]>([]);
  const [selectedSystemId, setSelectedSystemId] = useState<number | ''>('');
  const [selectedModelName, setSelectedModelName] = useState('');
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
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
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
        .filter((item) => item.role === 'user' || item.role === 'assistant')
        .map<ChatMessage>((item) => ({
          id: String(item.id),
          role: item.role,
          content: item.content,
          timeline: item.message_metadata?.timeline,
        }));
      setSessionId(id);
      setMessages(restored.length ? restored : [{ id: 'welcome', role: 'assistant', content: WELCOME_MESSAGE }]);
    } finally {
      setIsLoadingSession(false);
    }
  };

  const handleSend = async () => {
    const text = input.trim();
    if (!text || isStreaming) return;

    setInput('');
    setIsStreaming(true);

    const userMessage: ChatMessage = { id: crypto.randomUUID(), role: 'user', content: text };
    const assistantId = crypto.randomUUID();
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
    <div className="grid h-[calc(100vh-2rem)] min-h-[720px] grid-cols-[280px_minmax(0,1fr)] gap-4 p-2">
      <aside className="app-panel flex min-h-0 flex-col overflow-hidden rounded-[28px] border-white/80 bg-white/70">
        <div className="border-b border-white/80 p-4">
          <Button className="h-10 w-full rounded-2xl bg-[#6e5df7] text-white hover:bg-[#5d4ee0]" onClick={startNewSession} disabled={isStreaming}>
            <MessageSquarePlus className="h-4 w-4" />
            新会话
          </Button>
        </div>
        <div className="min-h-0 flex-1 overflow-auto p-3">
          <div className="px-2 pb-2 text-xs font-black text-[#85889f]">历史会话</div>
          <div className="space-y-2">
            {sessions.length === 0 ? (
              <div className="rounded-2xl bg-white/58 px-3 py-4 text-xs leading-5 text-[#85889f]">暂无历史会话，发送问题后会自动保存。</div>
            ) : (
              sessions.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  className={`w-full rounded-2xl px-3 py-3 text-left transition ${
                    item.id === sessionId ? 'bg-[#edeaff] text-[#4f45c8]' : 'bg-white/58 text-[#34324a] hover:bg-white'
                  }`}
                  onClick={() => void loadSession(item.id)}
                  disabled={isStreaming || isLoadingSession}
                >
                  <div className="line-clamp-2 text-sm font-bold">{item.title || 'SAP 助手会话'}</div>
                  <div className="mt-1 text-[11px] font-semibold text-[#9295aa]">{formatSessionTime(item.update_time)}</div>
                </button>
              ))
            )}
          </div>
        </div>
      </aside>

      <section className="app-panel flex min-w-0 flex-col overflow-hidden rounded-[28px] border-white/80 bg-white/72">
        <header className="border-b border-white/80 px-5 py-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="min-w-0">
              <div className="text-lg font-black text-[#25233b]">SAP 助手</div>
              <div className="mt-1 truncate text-xs font-semibold text-[#85889f]">
                {currentSession?.title || selectedSystem?.name || '选择系统后开始排查'}
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <select
                className="h-10 rounded-2xl border border-white/80 bg-white/78 px-3 text-xs font-semibold text-[#34324a] outline-none"
                value={selectedSystemId}
                onChange={(event) => setSelectedSystemId(event.target.value ? Number(event.target.value) : '')}
              >
                <option value="">让 AI 判断系统</option>
                {systems.map((system) => (
                  <option key={system.id} value={system.id}>
                    {system.name} / {system.client}
                  </option>
                ))}
              </select>
              <select
                className="h-10 max-w-[220px] rounded-2xl border border-white/80 bg-white/78 px-3 text-xs font-semibold text-[#34324a] outline-none"
                value={selectedModelName}
                onChange={(event) => setSelectedModelName(event.target.value)}
                title="选择本轮 SAP 助手使用的模型"
              >
                <option value="">自动选择模型</option>
                {models.map((model) => (
                  <option key={model.id} value={model.model_name}>
                    {model.model_name}
                    {model.capability ? ` / ${model.capability}` : ''}
                  </option>
                ))}
              </select>
              <button
                type="button"
                className="inline-flex h-10 items-center gap-1.5 rounded-2xl bg-[#f1f3ff] px-3 text-xs font-bold text-[#665cf0]"
                onClick={() => fileInputRef.current?.click()}
                disabled={isUploadingDoc}
              >
                {isUploadingDoc ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <UploadCloud className="h-3.5 w-3.5" />}
                上传
              </button>
            </div>
          </div>
          <KnowledgeBaseBar
            knowledgeBases={knowledgeBases}
            selectedKbIds={selectedKbIds}
            newKbName={newKbName}
            newKbDescription={newKbDescription}
            isCreatingKb={isCreatingKb}
            notice={kbNotice}
            fileInputRef={fileInputRef}
            onToggle={toggleKnowledgeBase}
            onNameChange={setNewKbName}
            onDescriptionChange={setNewKbDescription}
            onCreate={() => void handleCreateKnowledgeBase()}
            onFileChange={(file) => void handleUploadDocument(file)}
          />
        </header>

        <div className="flex-1 space-y-4 overflow-auto px-6 py-5">
          {messages.map((message) => (
            <div key={message.id} className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              <div
                className={`max-w-[82%] rounded-[24px] px-5 py-4 text-sm leading-7 shadow-[0_12px_30px_rgba(102,99,166,0.06)] ${
                  message.role === 'user'
                    ? 'bg-linear-to-r from-[#6e5df7] to-[#9b86ff] text-white'
                    : 'border border-white/85 bg-white/86 text-[#38364f]'
                }`}
              >
                {message.role === 'assistant' && message.timeline?.length ? (
                  <InlineThoughtTimeline items={message.timeline} isStreaming={Boolean(message.isStreaming)} />
                ) : null}
                <MarkdownText text={message.content || (message.isStreaming ? '正在组织证据链回答...' : '')} isStreaming={message.isStreaming} inverted={message.role === 'user'} />
              </div>
            </div>
          ))}
          <div ref={bottomRef} />
        </div>

        <footer className="border-t border-white/80 p-5">
          <div className="flex items-end gap-3 rounded-[24px] border border-white/90 bg-white/80 p-3 shadow-[0_16px_38px_rgba(102,99,166,0.08)]">
            <textarea
              className="min-h-11 flex-1 resize-none bg-transparent px-2 py-2 text-sm leading-6 text-[#28263c] outline-none placeholder:text-[#9ea1b8]"
              rows={2}
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && !event.shiftKey) {
                  event.preventDefault();
                  void handleSend();
                }
              }}
              placeholder="例如：ZSD220 中的开票金额是怎么取的"
            />
            <Button className="h-11 rounded-[18px] bg-[#6e5df7] px-5 text-white hover:bg-[#5d4ee0]" onClick={() => void handleSend()} disabled={isStreaming}>
              {isStreaming ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
              发送
            </Button>
          </div>
        </footer>
      </section>
    </div>
  );
}

function KnowledgeBaseBar({
  knowledgeBases,
  selectedKbIds,
  newKbName,
  newKbDescription,
  isCreatingKb,
  notice,
  fileInputRef,
  onToggle,
  onNameChange,
  onDescriptionChange,
  onCreate,
  onFileChange,
}: {
  knowledgeBases: KnowledgeBase[];
  selectedKbIds: number[];
  newKbName: string;
  newKbDescription: string;
  isCreatingKb: boolean;
  notice: string;
  fileInputRef: RefObject<HTMLInputElement | null>;
  onToggle: (id: number) => void;
  onNameChange: (value: string) => void;
  onDescriptionChange: (value: string) => void;
  onCreate: () => void;
  onFileChange: (file: File | null | undefined) => void;
}) {
  return (
    <div className="mt-3 rounded-2xl border border-white/80 bg-white/50 p-2">
      <input
        ref={fileInputRef}
        type="file"
        className="hidden"
        accept=".txt,.md,.docx,.xlsx,.pdf"
        onChange={(event) => onFileChange(event.target.files?.[0])}
      />
      <div className="flex flex-wrap gap-2">
        {knowledgeBases.map((kb) => (
          <button
            key={kb.id}
            type="button"
            onClick={() => onToggle(kb.id)}
            className={`rounded-full px-3 py-1.5 text-xs font-bold transition ${
              selectedKbIds.includes(kb.id) ? 'bg-[#6e5df7] text-white' : 'bg-white text-[#62647a] hover:bg-[#f3f0ff]'
            }`}
          >
            {kb.name}
          </button>
        ))}
        {knowledgeBases.length === 0 ? <span className="px-2 py-1.5 text-xs text-[#8c8fa5]">暂无知识库</span> : null}
      </div>
      <div className="mt-2 grid gap-2 md:grid-cols-[0.9fr_1fr_auto]">
        <input
          className="h-9 rounded-2xl border border-white/80 bg-white/78 px-3 text-xs outline-none"
          value={newKbName}
          onChange={(event) => onNameChange(event.target.value)}
          placeholder="新知识库"
        />
        <input
          className="h-9 rounded-2xl border border-white/80 bg-white/78 px-3 text-xs outline-none"
          value={newKbDescription}
          onChange={(event) => onDescriptionChange(event.target.value)}
          placeholder="说明，可选"
        />
        <button
          type="button"
          className="inline-flex h-9 items-center justify-center gap-1.5 rounded-2xl bg-[#6e5df7] px-3 text-xs font-bold text-white disabled:opacity-60"
          onClick={onCreate}
          disabled={!newKbName.trim() || isCreatingKb}
        >
          {isCreatingKb ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />}
          新建
        </button>
      </div>
      {notice ? <div className="mt-2 rounded-2xl bg-[#f7f4ff] px-3 py-2 text-xs font-semibold text-[#6e5df7]">{notice}</div> : null}
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

function InlineThoughtTimeline({ items, isStreaming }: { items: TimelineItem[]; isStreaming: boolean }) {
  const latest = items[items.length - 1];
  const [open, setOpen] = useState(isStreaming);

  return (
    <details
      className="mb-4 rounded-[20px] border border-[#e5e7f5] bg-[#f8f9ff] text-[#3b3a52]"
      open={open}
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3">
        <div className="flex min-w-0 items-center gap-2">
          {isStreaming ? <Loader2 className="h-4 w-4 shrink-0 animate-spin text-[#6e5df7]" /> : <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-500" />}
          <span className="truncate text-xs font-black">{isStreaming ? 'AI 正在思考和执行' : 'AI 执行过程'}</span>
        </div>
        <span className="truncate text-[11px] font-semibold text-[#7a7d92]">{latest?.detail || `${items.length} 个步骤`}</span>
      </summary>
      <div className="max-h-72 space-y-2 overflow-auto border-t border-[#e8e9f6] px-4 py-3">
        {items.map((item, index) => (
          <div key={`${item.id}-${index}`} className="grid grid-cols-[18px_1fr] gap-2 text-xs leading-5">
            <StatusIcon status={item.status} />
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <span className="font-bold text-[#303047]">{item.title}</span>
                <span className="rounded-full bg-white px-2 py-0.5 text-[10px] font-bold text-[#85889f]">{item.status}</span>
              </div>
              <p className="mt-1 text-[#6f7288]">{item.detail}</p>
            </div>
          </div>
        ))}
      </div>
    </details>
  );
}

function StatusIcon({ status }: { status: string }) {
  if (status === 'success') return <CheckCircle2 className="h-5 w-5 text-emerald-500" />;
  if (status === 'failed') return <AlertTriangle className="h-5 w-5 text-rose-500" />;
  if (status === 'pending') return <Loader2 className="h-5 w-5 animate-spin text-[#6e5df7]" />;
  return <Clock3 className="h-5 w-5 text-[#a0a3b8]" />;
}

function MarkdownText({ text, isStreaming, inverted }: { text: string; isStreaming?: boolean; inverted?: boolean }) {
  return (
    <TypingEffectMarkdown
      content={text}
      isStreaming={isStreaming}
      className={`break-words leading-7 ${inverted ? 'prose-invert text-white' : 'text-[#38364f]'} prose-p:my-2 prose-strong:font-black prose-ol:my-2 prose-ul:my-2 prose-li:my-1 prose-code:rounded-md prose-code:bg-[#f3f1ff] prose-code:px-1.5 prose-code:py-0.5 prose-code:text-[#6e5df7] prose-pre:bg-white prose-pre:text-[#25233b]`}
    />
  );
}

function formatSessionTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  return date.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
}
