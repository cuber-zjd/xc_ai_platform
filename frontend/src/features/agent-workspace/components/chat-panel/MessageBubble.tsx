import React from 'react';
import { cn } from '@/lib/utils';
import { User, Bot } from 'lucide-react';
import { TypingEffectMarkdown } from './TypingEffectMarkdown';

interface MessageBubbleProps {
  role: 'user' | 'assistant';
  content: string;
  isStreaming?: boolean;
}

export const MessageBubble = React.memo(({ role, content, isStreaming }: MessageBubbleProps) => {
  const isUser = role === 'user';

  return (
    <div
      className={cn(
        'flex w-full mb-8 group animate-in fade-in slide-in-from-bottom-2 duration-300',
        isUser ? 'justify-end' : 'justify-start'
      )}
    >
      <div
        className={cn(
          'flex max-w-[85%] gap-3',
          isUser ? 'flex-row-reverse' : 'flex-row'
        )}
      >
        {/* 头像 */}
        <div
          className={cn(
            'w-8 h-8 rounded-full flex items-center justify-center shrink-0 border mt-1',
            isUser 
              ? 'bg-zinc-100 dark:bg-zinc-800 border-zinc-200 dark:border-zinc-700 text-zinc-600 dark:text-zinc-400' 
              : 'bg-zinc-900 dark:bg-zinc-100 border-zinc-800 dark:border-zinc-200 text-zinc-100 dark:text-zinc-900'
          )}
        >
          {isUser ? <User size={16} /> : <Bot size={16} />}
        </div>

        {/* 内容气泡 */}
        <div
          className={cn(
            'flex flex-col gap-2 px-4 py-3 rounded-2xl text-sm leading-relaxed',
            isUser
              ? 'bg-zinc-900 border-zinc-800 text-zinc-50 dark:bg-zinc-100 dark:border-zinc-200 dark:text-zinc-900 shadow-sm'
              : 'bg-white dark:bg-zinc-900 border border-zinc-100 dark:border-zinc-800 text-zinc-800 dark:text-zinc-200'
          )}
        >
          <TypingEffectMarkdown 
            content={content} 
            isStreaming={isStreaming} 
          />
        </div>
      </div>
    </div>
  );
});
