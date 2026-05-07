import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
    ArrowRight,
    Bot,
    BrainCircuit,
    Cpu,
    LayoutGrid,
    MessagesSquare,
    Search,
    Sparkles,
} from 'lucide-react';

import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils';
import { apiClient } from '@/api/client';

interface Agent {
    id: number;
    name: string;
    description?: string;
    icon?: string;
    logo_url?: string;
    route_path: string;
}

interface Group {
    id: number;
    name: string;
    agents: Agent[];
}

const ICON_MAP: Record<string, typeof Bot> = {
    Bot,
    Sparkles,
    BrainCircuit,
    Cpu,
    MessagesSquare,
};

export default function WorkbenchPage() {
    const [groups, setGroups] = useState<Group[]>([]);
    const [loading, setLoading] = useState(true);
    const [searchQuery, setSearchQuery] = useState('');
    const navigate = useNavigate();

    useEffect(() => {
        void fetchWorkbench();
    }, []);

    const fetchWorkbench = async () => {
        try {
            setLoading(true);
            const data: Group[] = await apiClient.get('/agents/workbench');
            setGroups(data || []);
        } finally {
            setLoading(false);
        }
    };

    const filteredGroups = groups
        .map((group) => ({
            ...group,
            agents: group.agents.filter((agent) => {
                const keyword = searchQuery.toLowerCase();
                return (
                    agent.name.toLowerCase().includes(keyword) ||
                    (agent.description ?? '').toLowerCase().includes(keyword)
                );
            }),
        }))
        .filter((group) => group.agents.length > 0);

    return (
        <div className="app-page">
            <section className="app-page-header">
                <div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
                    <div>
                        <div className="app-kicker">智能体工作台</div>
                        <h2 className="mt-4 text-[34px] font-black tracking-[-0.04em] text-[#24233b]">
                            我的智能体入口
                        </h2>
                        <p className="mt-2 max-w-2xl app-subtle-text">
                            所有已授权的智能体与业务应用会在这里集中呈现。你可以按分组快速进入，也可以通过搜索直接定位目标能力。
                        </p>
                    </div>
                    <div className="w-full max-w-sm">
                        <div className="relative">
                            <Search className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-[#9699af]" />
                            <Input
                                value={searchQuery}
                                onChange={(event) => setSearchQuery(event.target.value)}
                                placeholder="搜索智能体、场景或描述"
                                className="pl-11"
                            />
                        </div>
                    </div>
                </div>
            </section>

            {loading ? (
                <div className="app-panel flex h-[320px] items-center justify-center">
                    <div className="flex flex-col items-center gap-4 text-[#7c7f96]">
                        <div className="h-12 w-12 animate-spin rounded-full border-4 border-[#d7d9ef] border-t-[#6d5df6]" />
                        <p className="text-sm font-semibold">正在加载你的智能体工作台...</p>
                    </div>
                </div>
            ) : filteredGroups.length === 0 ? (
                <div className="app-panel flex h-[320px] flex-col items-center justify-center text-center">
                    <Sparkles className="h-12 w-12 text-[#c2c5dc]" />
                    <h3 className="mt-4 text-xl font-black text-[#2a2942]">没有找到匹配结果</h3>
                    <p className="mt-2 max-w-md text-sm text-[#8a8da4]">
                        可以试试更短的关键词，或者检查当前账号是否已经被授予对应智能体访问权限。
                    </p>
                </div>
            ) : (
                <div className="space-y-6">
                    {filteredGroups.map((group) => (
                        <section key={group.id} className="app-panel px-6 py-6">
                            <div className="flex items-center gap-3">
                                <div className="flex h-10 w-10 items-center justify-center rounded-[18px] bg-linear-to-br from-[#eef0ff] to-[#f8f4ff] text-[#6d5df6]">
                                    <LayoutGrid className="h-5 w-5" />
                                </div>
                                <div className="min-w-0">
                                    <h3 className="truncate text-[20px] font-black tracking-tight text-[#282741]">{group.name}</h3>
                                    <p className="text-sm text-[#8a8da4]">共 {group.agents.length} 个可用入口</p>
                                </div>
                            </div>

                            <div className="mt-5 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                                {group.agents.map((agent) => {
                                    const IconComponent = ICON_MAP[agent.icon || 'Bot'] || Bot;
                                    const isLogoUrl = agent.icon?.startsWith('http');
                                    return (
                                        <button
                                            key={agent.id}
                                            type="button"
                                            onClick={() => navigate(agent.route_path)}
                                            className={cn(
                                                'group rounded-[26px] border border-white/80 bg-white/72 p-5 text-left shadow-[0_12px_30px_rgba(102,99,166,0.05)] transition-all duration-300 hover:-translate-y-1 hover:shadow-[0_22px_40px_rgba(102,99,166,0.10)]',
                                            )}
                                        >
                                            <div className="flex items-start justify-between gap-3">
                                                <div className="flex h-12 w-12 items-center justify-center rounded-[18px] bg-linear-to-br from-[#f3f4ff] to-[#f7fbff] text-[#6d5df6] shadow-[inset_0_1px_0_rgba(255,255,255,0.95)]">
                                                    {isLogoUrl ? (
                                                        <img src={agent.icon} alt={agent.name} className="h-7 w-7 object-contain" />
                                                    ) : (
                                                        <IconComponent className="h-6 w-6" />
                                                    )}
                                                </div>
                                                <div className="flex items-center gap-1 text-xs font-bold text-[#a2a5b9] transition-colors group-hover:text-[#6d5df6]">
                                                    立即进入
                                                    <ArrowRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5" />
                                                </div>
                                            </div>
                                            <h4 className="mt-5 text-[18px] font-black tracking-tight text-[#24233b]">{agent.name}</h4>
                                            <p className="mt-2 line-clamp-2 text-sm leading-6 text-[#7e8196]">
                                                {agent.description || '已接入工作台，可直接进入开始使用。'}
                                            </p>
                                        </button>
                                    );
                                })}
                            </div>
                        </section>
                    ))}
                </div>
            )}
        </div>
    );
}
