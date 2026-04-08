import { create } from 'zustand';
import type { WorkspaceType } from '@/features/agent-workspace/types/stream-protocol';

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  isStreaming?: boolean;
}

interface WorkspaceState {
  messages: Message[];
  activeWorkspaceType: WorkspaceType;
  workspaceData: any;
  isStreaming: boolean;

  // Actions
  addMessage: (message: Message) => void;
  updateLastMessage: (content: string, isStreaming?: boolean) => void;
  setWorkspace: (type: WorkspaceType, data: any) => void;
  setStreaming: (status: boolean) => void;
}

export const useWorkspaceStore = create<WorkspaceState>((set) => ({
  messages: [
    { id: '1', role: 'assistant', content: '您好！我是您的智能助手。请问有什么可以帮您的？' }
  ],
  activeWorkspaceType: 'idle',
  workspaceData: null,
  isStreaming: false,

  addMessage: (message) => set((state) => ({ 
    messages: [...state.messages, message] 
  })),

  updateLastMessage: (content, isStreaming = true) => set((state) => {
    const newMessages = [...state.messages];
    if (newMessages.length > 0) {
      newMessages[newMessages.length - 1] = {
        ...newMessages[newMessages.length - 1],
        content,
        isStreaming
      };
    }
    return { messages: newMessages };
  }),

  setWorkspace: (type, data) => set({ 
    activeWorkspaceType: type, 
    workspaceData: data 
  }),

  setStreaming: (status) => set({ isStreaming: status }),
}));
