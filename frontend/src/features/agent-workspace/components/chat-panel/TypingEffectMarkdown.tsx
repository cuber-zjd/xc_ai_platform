import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { cn } from '@/lib/utils';

interface TypingEffectMarkdownProps {
  content: string;
  className?: string;
  isStreaming?: boolean;
}

/**
 * 支持 Markdown 渲染与流式光标效果的文本组件
 */
export const TypingEffectMarkdown = React.memo(({ content, className, isStreaming }: TypingEffectMarkdownProps) => {
  return (
    <div className={cn('prose prose-sm dark:prose-invert max-w-none', className)}>
      <ReactMarkdown remarkPlugins={[remarkGfm]}>
        {content}
      </ReactMarkdown>
      {isStreaming && (
        <span className="inline-block w-1.5 h-4 ml-0.5 bg-zinc-400 dark:bg-zinc-500 animate-pulse align-middle" />
      )}
    </div>
  );
});
