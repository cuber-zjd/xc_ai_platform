import React from 'react';
import type { WorkspaceType } from '@/features/agent-workspace/types/stream-protocol';
import { ThoughtChainViewer } from '@/features/agent-workspace/components/plugins/ThoughtChainViewer';
import { HumanInTheLoopCard } from '@/features/agent-workspace/components/plugins/HumanInTheLoopCard';
import { ToolMirrorPreview } from '@/features/agent-workspace/components/plugins/ToolMirrorPreview';
import { IdlePlaceholder } from '@/features/agent-workspace/components/plugins/IdlePlaceholder';
import { AnimatePresence, motion } from 'framer-motion';

interface ComponentDispatcherProps {
  activeType: WorkspaceType;
  data: any;
}

export const ComponentDispatcher = React.memo(({ activeType, data }: ComponentDispatcherProps) => {
  const renderComponent = () => {
    switch (activeType) {
      case 'thought':
        return <ThoughtChainViewer data={data} />;
      case 'human':
        return <HumanInTheLoopCard data={data} />;
      case 'tool':
        return <ToolMirrorPreview data={data} />;
      case 'idle':
      default:
        return <IdlePlaceholder />;
    }
  };

  return (
    <div className="h-full w-full relative overflow-hidden">
      <AnimatePresence mode="wait">
        <motion.div
          key={activeType}
          initial={{ opacity: 0, y: 10, scale: 0.98 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: -10, scale: 0.98 }}
          transition={{ duration: 0.3, ease: "circOut" }}
          className="h-full w-full"
        >
          {renderComponent()}
        </motion.div>
      </AnimatePresence>
    </div>
  );
});
