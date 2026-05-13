import React, { useState } from 'react';
import { Check, Copy } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import rehypeHighlight from 'rehype-highlight';
import remarkGfm from 'remark-gfm';
import { cn } from '@/lib/utils';

interface TypingEffectMarkdownProps {
  content: string;
  className?: string;
  isStreaming?: boolean;
}

export const TypingEffectMarkdown = React.memo(({ content, className, isStreaming }: TypingEffectMarkdownProps) => {
  return (
    <div className={cn('max-w-none break-words text-sm leading-7', className)}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeHighlight]}
        components={{
          p: ({ children }) => <p className="my-2 leading-7">{children}</p>,
          h1: ({ children }) => <h1 className="mb-3 mt-4 text-2xl font-black tracking-[-0.02em]">{children}</h1>,
          h2: ({ children }) => <h2 className="mb-3 mt-4 text-xl font-black tracking-[-0.02em]">{children}</h2>,
          h3: ({ children }) => <h3 className="mb-2 mt-4 text-base font-black">{children}</h3>,
          ul: ({ children }) => <ul className="my-3 list-disc space-y-1.5 pl-5">{children}</ul>,
          ol: ({ children }) => <ol className="my-3 list-decimal space-y-1.5 pl-5">{children}</ol>,
          li: ({ children }) => <li className="pl-1 leading-7">{children}</li>,
          strong: ({ children }) => <strong className="font-black text-inherit">{children}</strong>,
          blockquote: ({ children }) => (
            <blockquote className="my-3 border-l-4 border-[#9b8cff] bg-[#f6f4ff] px-4 py-2 text-[#5f6278]">
              {children}
            </blockquote>
          ),
          a: ({ href, children }) => (
            <a className="font-bold text-[#6254e8] underline decoration-[#bdb6ff] underline-offset-4" href={href} target="_blank" rel="noreferrer">
              {children}
            </a>
          ),
          table: ({ children }) => (
            <div className="my-4 overflow-x-auto rounded-2xl border border-[#e4e6f3] bg-white/80">
              <table className="min-w-full border-collapse text-left text-sm">{children}</table>
            </div>
          ),
          thead: ({ children }) => <thead className="bg-[#f3f1ff] text-[#34324a]">{children}</thead>,
          th: ({ children }) => <th className="border-b border-[#e4e6f3] px-3 py-2 font-black">{children}</th>,
          td: ({ children }) => <td className="border-b border-[#eef0f7] px-3 py-2 align-top">{children}</td>,
          code: CodeRenderer,
          pre: ({ children }) => <>{children}</>,
          hr: () => <hr className="my-5 border-[#e3e5f2]" />,
        }}
      >
        {content}
      </ReactMarkdown>
      {isStreaming && <span className="ml-1 inline-block h-4 w-1.5 animate-pulse align-middle bg-[#8a82ff]" />}
    </div>
  );
});

TypingEffectMarkdown.displayName = 'TypingEffectMarkdown';

function CodeRenderer({ inline, className, children, ...props }: React.ComponentProps<'code'> & { inline?: boolean }) {
  const [copied, setCopied] = useState(false);
  const code = String(children ?? '').replace(/\n$/, '');
  const language = /language-(\w+)/.exec(className || '')?.[1]?.toUpperCase();
  const isBlock = Boolean(className?.includes('language-') || code.includes('\n'));

  if (inline || !isBlock) {
    return (
      <code className="rounded-md border border-[#e4e6f3] bg-[#f7f8ff] px-1.5 py-0.5 font-mono text-[0.88em] font-semibold text-[#383a52]" {...props}>
        {children}
      </code>
    );
  }

  const copyCode = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1200);
    } catch {
      setCopied(false);
    }
  };

  return (
    <div className="my-4 overflow-hidden rounded-2xl border border-[#e2e5f1] bg-white shadow-[0_12px_28px_rgba(91,95,130,0.08)]">
      <div className="flex h-9 items-center justify-between border-b border-[#e8eaf4] bg-[#f7f8fc] px-3">
        <span className="font-mono text-[11px] font-bold uppercase tracking-wide text-[#737891]">{language || 'CODE'}</span>
        <button
          type="button"
          onClick={copyCode}
          className="inline-flex h-7 items-center gap-1.5 rounded-lg border border-[#dde1ef] bg-white px-2 text-[11px] font-bold text-[#62677f] transition hover:bg-[#f0f2fb]"
        >
          {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
          {copied ? '已复制' : '复制'}
        </button>
      </div>
      <pre className="max-h-[520px] overflow-auto bg-white p-4 text-[13px] leading-6 text-[#26293d]">
        <code className={cn('font-mono [&_.hljs-keyword]:text-[#7c4dff] [&_.hljs-string]:text-[#17803d] [&_.hljs-number]:text-[#a15c00] [&_.hljs-comment]:text-[#7b8198]', className)} {...props}>
          {children}
        </code>
      </pre>
    </div>
  );
}
