import React, { useState, useRef, useEffect } from 'react';
import { Send, Paperclip } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

interface ChatInputAreaProps {
  onSend: (message: string) => void;
  disabled?: boolean;
  placeholder?: string;
}

export function ChatInputArea({ 
  onSend, 
  disabled, 
  placeholder = "输入消息，Shift + Enter 换行..." 
}: ChatInputAreaProps) {
  const [text, setText] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // 自动调整高度
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 200)}px`;
    }
  }, [text]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleSend = () => {
    if (text.trim() && !disabled) {
      onSend(text);
      setText('');
    }
  };

  return (
    <div className="relative w-full max-w-4xl mx-auto px-4 pb-6">
      <div className={cn(
        "relative rounded-2xl border bg-white/50 dark:bg-zinc-900/50 backdrop-blur-2xl transition-all duration-200 focus-within:ring-2 focus-within:ring-zinc-200 dark:focus-within:ring-zinc-800",
        disabled ? "opacity-50 grayscale border-zinc-100" : "border-zinc-200 dark:border-zinc-800 shadow-xl shadow-zinc-200/20 dark:shadow-none"
      )}>
        <textarea
          ref={textareaRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={disabled}
          rows={1}
          className="w-full bg-transparent border-none resize-none px-4 py-4 pr-24 focus:outline-none text-zinc-800 dark:text-zinc-200 placeholder:text-zinc-400 min-h-[56px] max-h-[200px]"
        />

        <div className="absolute right-2 bottom-2 flex items-center gap-1.5">
          <Button
            variant="ghost"
            size="icon"
            className="h-9 w-9 rounded-xl text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-300"
            disabled={disabled}
          >
            <Paperclip size={18} />
          </Button>
          <Button
            size="icon"
            onClick={handleSend}
            disabled={disabled || !text.trim()}
            className="h-9 w-9 rounded-xl bg-zinc-900 text-zinc-50 hover:bg-zinc-800 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-200 transition-all active:scale-95"
          >
            <Send size={18} />
          </Button>
        </div>
      </div>
      
      <p className="mt-3 text-[10px] text-center text-zinc-400 uppercase tracking-widest font-medium">
        Powered by AI Platform Agent Engine
      </p>
    </div>
  );
}
