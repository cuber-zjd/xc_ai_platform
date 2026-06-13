import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowRight, Bot, Pin, Search, Sparkles } from 'lucide-react';

import { apiClient } from '@/api/client';
import { Input } from '@/components/ui/input';
import {
    flattenWorkbenchGroups,
    getPinnedAgentIds,
    getRecentAgentIds,
    recordRecentAgent,
    selectVisibleAgents,
    togglePinnedAgent,
    type WorkbenchAgent,
    type WorkbenchGroup,
} from '@/features/agent-workbench/workbenchStorage';
import { cn } from '@/lib/utils';

const ALL_GROUP = '全部';

function AgentIcon({ agent }: { agent: WorkbenchAgent }) {
    if (agent.icon?.startsWith('http')) {
        return <img src={agent.icon} alt={agent.name} className="h-9 w-9 rounded-xl object-contain" />;
    }

    return <Bot className="h-5 w-5 text-[#555555]" />;
}

export default function WorkbenchPage() {
    const [groups, setGroups] = useState<WorkbenchGroup[]>([]);
    const [loading, setLoading] = useState(true);
    const [searchQuery, setSearchQuery] = useState('');
    const [activeGroup, setActiveGroup] = useState(ALL_GROUP);
    const [pinnedIds, setPinnedIds] = useState<number[]>(() => getPinnedAgentIds());
    const [recentIds, setRecentIds] = useState<number[]>(() => getRecentAgentIds());
    const navigate = useNavigate();

    useEffect(() => {
        let ignore = false;

        async function fetchWorkbench() {
            try {
                setLoading(true);
                const data = (await apiClient.get('/agents/workbench')) as unknown as WorkbenchGroup[];
                if (!ignore) setGroups(data ?? []);
            } finally {
                if (!ignore) setLoading(false);
            }
        }

        void fetchWorkbench();
        return () => {
            ignore = true;
        };
    }, []);

    const allAgents = useMemo(() => flattenWorkbenchGroups(groups), [groups]);
    const groupNames = useMemo(() => [ALL_GROUP, ...groups.map((group) => group.name)], [groups]);
    const pinnedAgents = useMemo(() => selectVisibleAgents(pinnedIds, allAgents), [allAgents, pinnedIds]);
    const recentAgents = useMemo(
        () => selectVisibleAgents(recentIds.filter((id) => !pinnedIds.includes(id)), allAgents),
        [allAgents, pinnedIds, recentIds],
    );
    const featuredAgents = useMemo(() => {
        const selected = [...pinnedAgents, ...recentAgents];
        return (selected.length ? selected : allAgents).slice(0, 4);
    }, [allAgents, pinnedAgents, recentAgents]);

    const filteredAgents = useMemo(() => {
        const keyword = searchQuery.trim().toLowerCase();
        return allAgents.filter((agent) => {
            const matchesGroup = activeGroup === ALL_GROUP || agent.groupName === activeGroup;
            const matchesKeyword = !keyword
                || agent.name.toLowerCase().includes(keyword)
                || (agent.description ?? '').toLowerCase().includes(keyword)
                || agent.groupName.toLowerCase().includes(keyword);
            return matchesGroup && matchesKeyword;
        });
    }, [activeGroup, allAgents, searchQuery]);

    const handleOpenAgent = (agent: WorkbenchAgent) => {
        setRecentIds(recordRecentAgent(agent.id));
        navigate(agent.route_path || '/chat-home');
    };

    const handleTogglePinned = (agentId: number) => {
        setPinnedIds(togglePinnedAgent(agentId));
    };

    return (
        <div className="app-page">
            <section className="mx-auto flex max-w-4xl flex-col items-center px-4 pt-14 text-center">
                <div className="mb-5 flex h-12 w-12 items-center justify-center rounded-2xl border border-[#e5e5e5] bg-white shadow-sm">
                    <Sparkles className="h-5 w-5 text-[#171717]" />
                </div>
                <h1 className="text-4xl font-semibold tracking-tight text-[#171717] md:text-5xl">探索智能体</h1>
                <p className="mt-4 max-w-2xl text-sm leading-6 text-[#6f6f6f]">
                    从工作台选择已授权的智能体或业务应用。它们可以是对话助手，也可以是合同审查、报表生成、SAP 调查等独立工作流。
                </p>
                <div className="mt-8 w-full max-w-2xl">
                    <div className="relative">
                        <Search className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-[#8a8a8a]" />
                        <Input
                            value={searchQuery}
                            onChange={(event) => setSearchQuery(event.target.value)}
                            placeholder="搜索智能体、场景或描述"
                            className="h-13 rounded-2xl border-[#dddddd] bg-white pl-11 text-[15px] shadow-sm"
                        />
                    </div>
                </div>
            </section>

            <section className="mx-auto mt-10 max-w-5xl px-4">
                <div className="flex gap-2 overflow-x-auto pb-2">
                    {groupNames.map((groupName) => (
                        <button
                            key={groupName}
                            type="button"
                            onClick={() => setActiveGroup(groupName)}
                            className={cn(
                                'h-9 shrink-0 rounded-full border px-4 text-sm transition-colors',
                                activeGroup === groupName
                                    ? 'border-[#171717] bg-[#171717] text-white'
                                    : 'border-[#dddddd] bg-white text-[#4a4a4a] hover:bg-[#f4f4f4]',
                            )}
                        >
                            {groupName}
                        </button>
                    ))}
                </div>
            </section>

            {loading ? (
                <div className="mx-auto mt-10 flex h-64 max-w-5xl items-center justify-center rounded-2xl border border-[#eeeeee] bg-[#fafafa] text-sm text-[#6f6f6f]">
                    正在加载你的智能体工作台...
                </div>
            ) : allAgents.length === 0 ? (
                <div className="mx-auto mt-10 flex h-64 max-w-5xl flex-col items-center justify-center rounded-2xl border border-dashed border-[#dddddd] bg-[#fafafa] text-center">
                    <Sparkles className="h-8 w-8 text-[#b5b5b5]" />
                    <h2 className="mt-4 text-lg font-semibold text-[#171717]">暂无可用智能体</h2>
                    <p className="mt-2 text-sm text-[#6f6f6f]">请联系管理员为当前账号分配智能体访问权限。</p>
                </div>
            ) : (
                <div className="mx-auto mt-8 max-w-5xl space-y-10 px-4 pb-12">
                    {featuredAgents.length > 0 && !searchQuery.trim() && activeGroup === ALL_GROUP && (
                        <section>
                            <div className="mb-4">
                                <h2 className="text-xl font-semibold text-[#171717]">精选</h2>
                                <p className="mt-1 text-sm text-[#8a8a8a]">根据置顶和最近使用优先展示。</p>
                            </div>
                            <div className="grid gap-3 md:grid-cols-2">
                                {featuredAgents.map((agent) => (
                                    <AgentCard
                                        key={agent.id}
                                        agent={agent}
                                        pinned={pinnedIds.includes(agent.id)}
                                        onOpen={handleOpenAgent}
                                        onTogglePinned={handleTogglePinned}
                                        featured
                                    />
                                ))}
                            </div>
                        </section>
                    )}

                    <section>
                        <div className="mb-4 flex items-end justify-between gap-3">
                            <div>
                                <h2 className="text-xl font-semibold text-[#171717]">全部智能体</h2>
                                <p className="mt-1 text-sm text-[#8a8a8a]">共 {filteredAgents.length} 个匹配入口。</p>
                            </div>
                        </div>
                        {filteredAgents.length === 0 ? (
                            <div className="flex h-48 flex-col items-center justify-center rounded-2xl border border-dashed border-[#dddddd] bg-[#fafafa] text-center">
                                <Search className="h-7 w-7 text-[#b5b5b5]" />
                                <p className="mt-3 text-sm text-[#6f6f6f]">没有找到匹配的智能体。</p>
                            </div>
                        ) : (
                            <div className="grid gap-3 md:grid-cols-2">
                                {filteredAgents.map((agent) => (
                                    <AgentCard
                                        key={agent.id}
                                        agent={agent}
                                        pinned={pinnedIds.includes(agent.id)}
                                        onOpen={handleOpenAgent}
                                        onTogglePinned={handleTogglePinned}
                                    />
                                ))}
                            </div>
                        )}
                    </section>
                </div>
            )}
        </div>
    );
}

function AgentCard({
    agent,
    pinned,
    onOpen,
    onTogglePinned,
    featured,
}: {
    agent: WorkbenchAgent & { groupName?: string };
    pinned: boolean;
    onOpen: (agent: WorkbenchAgent) => void;
    onTogglePinned: (agentId: number) => void;
    featured?: boolean;
}) {
    return (
        <div
            className={cn(
                'group flex min-h-[132px] flex-col justify-between rounded-2xl border border-[#e7e7e7] bg-white p-4 transition hover:bg-[#fafafa]',
                featured && 'border-[#d7d7d7] shadow-sm',
            )}
        >
            <div className="flex items-start gap-4">
                <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl border border-[#e5e5e5] bg-[#f7f7f7]">
                    <AgentIcon agent={agent} />
                </div>
                <div className="min-w-0 flex-1 text-left">
                    <div className="flex items-center gap-2">
                        <h3 className="truncate text-base font-semibold text-[#171717]">{agent.name}</h3>
                        {agent.groupName && (
                            <span className="shrink-0 rounded-full bg-[#f1f1f1] px-2 py-0.5 text-xs text-[#6f6f6f]">{agent.groupName}</span>
                        )}
                    </div>
                    <p className="mt-2 line-clamp-2 text-sm leading-6 text-[#6f6f6f]">
                        {agent.description || '已接入工作台，可直接进入开始使用。'}
                    </p>
                </div>
                <button
                    type="button"
                    onClick={() => onTogglePinned(agent.id)}
                    className={cn(
                        'flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-[#8a8a8a] transition hover:bg-[#eeeeee] hover:text-[#171717]',
                        pinned && 'text-[#171717]',
                    )}
                    aria-label={pinned ? '取消置顶' : '置顶智能体'}
                >
                    <Pin className={cn('h-4 w-4', pinned && 'fill-current')} />
                </button>
            </div>
            <button
                type="button"
                onClick={() => onOpen(agent)}
                className="mt-4 flex w-fit items-center gap-1 rounded-lg px-2 py-1 text-sm font-medium text-[#424242] transition hover:bg-[#eeeeee] hover:text-[#171717]"
            >
                进入
                <ArrowRight className="h-4 w-4" />
            </button>
        </div>
    );
}
