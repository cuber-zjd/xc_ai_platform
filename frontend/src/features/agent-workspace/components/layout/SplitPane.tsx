import React, { useState, useCallback, useEffect } from 'react';
import { cn } from '@/lib/utils';

interface SplitPaneProps {
  left: React.ReactNode;
  right: React.ReactNode;
  initialLeftWidth?: number; // 默认百分比，例如 40
  minLeftWidth?: number;
  maxLeftWidth?: number;
  className?: string;
}

export const SplitPane = React.memo(({
  left,
  right,
  initialLeftWidth = 40,
  minLeftWidth = 20,
  maxLeftWidth = 80,
  className,
}: SplitPaneProps) => {
  const [leftWidth, setLeftWidth] = useState(initialLeftWidth);
  const [isResizing, setIsResizing] = useState(false);

  const startResizing = useCallback(() => {
    setIsResizing(true);
  }, []);

  const stopResizing = useCallback(() => {
    setIsResizing(false);
  }, []);

  const resize = useCallback(
    (e: MouseEvent) => {
      if (isResizing) {
        const newWidth = (e.clientX / window.innerWidth) * 100;
        if (newWidth >= minLeftWidth && newWidth <= maxLeftWidth) {
          setLeftWidth(newWidth);
        }
      }
    },
    [isResizing, minLeftWidth, maxLeftWidth]
  );

  useEffect(() => {
    if (isResizing) {
      window.addEventListener('mousemove', resize);
      window.addEventListener('mouseup', stopResizing);
    }
    return () => {
      window.removeEventListener('mousemove', resize);
      window.removeEventListener('mouseup', stopResizing);
    };
  }, [isResizing, resize, stopResizing]);

  return (
    <div className={cn('flex h-full w-full overflow-hidden bg-background', className)}>
      {/* 左侧面板 */}
      <div
        className="h-full overflow-hidden flex flex-col"
        style={{ width: `${leftWidth}%` }}
      >
        {left}
      </div>

      {/* 拖拽手柄 */}
      <div
        className={cn(
          'w-1.5 h-full cursor-col-resize transition-colors hover:bg-zinc-200 dark:hover:bg-zinc-800 shrink-0 group flex items-center justify-center',
          isResizing && 'bg-zinc-300 dark:bg-zinc-700'
        )}
        onMouseDown={startResizing}
      >
        <div className="w-0.5 h-8 rounded-full bg-zinc-300 dark:bg-zinc-700 group-hover:bg-zinc-400 dark:group-hover:bg-zinc-600 transition-colors" />
      </div>

      {/* 右侧面板 */}
      <div
        className="h-full overflow-hidden flex-1 bg-zinc-50/50 dark:bg-zinc-950/50 backdrop-blur-sm border-l border-zinc-100 dark:border-zinc-900"
      >
        {right}
      </div>
    </div>
  );
});
