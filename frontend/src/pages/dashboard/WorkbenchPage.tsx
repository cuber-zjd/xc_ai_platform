import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { 
    Search, 
    LayoutGrid, 
    ChevronRight, 
    Zap,
    Bot,
    Sparkles,
    BrainCircuit,
    Cpu,
    MessagesSquare,
    BookOpen
} from "lucide-react";
import { cn } from "@/lib/utils";
import { apiClient } from "@/api/client";

interface Agent {
    id: number;
    name: string;
    description?: string;
    icon?: string;
    route_path: string;
}

interface Group {
    id: number;
    name: string;
    agents: Agent[];
}

const ICON_MAP: Record<string, any> = {
    Bot,
    Sparkles,
    BrainCircuit,
    Cpu,
    MessagesSquare,
    BookOpen,
    Zap
};

export default function WorkbenchPage() {
    const [groups, setGroups] = useState<Group[]>([]);
    const [loading, setLoading] = useState(true);
    const [searchQuery, setSearchQuery] = useState("");
    const navigate = useNavigate();

    useEffect(() => {
        fetchWorkbench();
    }, []);

    const fetchWorkbench = async () => {
        try {
            setLoading(true);
            const data: any = await apiClient.get("/agents/workbench");
            setGroups(data || []);
        } catch (error) {
            console.error("Failed to fetch workbench", error);
        } finally {
            setLoading(false);
        }
    };

    const filteredGroups = groups.map((group: Group) => ({
        ...group,
        agents: group.agents.filter((agent: Agent) => 
            agent.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
            (agent.description && agent.description.toLowerCase().includes(searchQuery.toLowerCase()))
        )
    })).filter((group: Group) => group.agents.length > 0);

    if (loading) {
        return (
            <div className="flex h-[60vh] items-center justify-center">
                <div className="flex flex-col items-center gap-4">
                    <div className="h-12 w-12 animate-spin rounded-full border-4 border-zinc-200 border-t-zinc-800" />
                    <p className="text-zinc-500 animate-pulse font-medium">加载智能体工作台...</p>
                </div>
            </div>
        );
    }

    return (
        <div className="max-w-7xl mx-auto space-y-12 pb-20 p-4 lg:p-8">
            {/* Header & Search */}
            <div className="flex flex-col md:flex-row md:items-end justify-between gap-6 pb-2 border-b border-zinc-200/50">
                <div className="space-y-2">
                    <div className="flex items-center gap-2 text-zinc-500 text-sm font-medium tracking-wider uppercase">
                        <LayoutGrid size={16} />
                        <span>工作台</span>
                    </div>
                    <h1 className="text-4xl font-extrabold tracking-tight text-zinc-900 dark:text-zinc-100 italic">
                        我的<span className="text-zinc-500">智能体</span>
                    </h1>
                    <p className="text-zinc-500 dark:text-zinc-400 max-w-md">
                        在这里访问您所有的 AI 助手和自动化流程。
                    </p>
                </div>

                <div className="relative group w-full md:w-80">
                    <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-zinc-400 group-focus-within:text-zinc-800 transition-colors">
                        <Search size={18} />
                    </div>
                    <input
                        type="search"
                        placeholder="搜索智能体..."
                        className="w-full bg-white/50 backdrop-blur-xl border border-zinc-200 rounded-2xl py-3 pl-10 pr-4 focus:outline-none focus:ring-2 focus:ring-zinc-800/20 focus:border-zinc-300 transition-all shadow-sm"
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                    />
                </div>
            </div>

            {/* Groups Grid */}
            <div className="space-y-16">
                {filteredGroups.length === 0 ? (
                    <div className="flex flex-col items-center justify-center py-20 text-zinc-400 space-y-4">
                        <Sparkles size={48} className="opacity-20" />
                        <p className="text-lg">未找到匹配的智能体</p>
                    </div>
                ) : (
                    filteredGroups.map((group) => (
                        <section key={group.id} className="space-y-6">
                            <div className="flex items-center gap-3">
                                <h2 className="text-xl font-bold text-zinc-800 dark:text-zinc-200">
                                    {group.name}
                                </h2>
                                <div className="h-px flex-1 bg-zinc-200/50" />
                                <span className="text-xs font-mono bg-zinc-100 dark:bg-zinc-800 px-2 py-1 rounded-md text-zinc-500">
                                    {group.agents.length}
                                </span>
                            </div>

                            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                                {group.agents.map((agent) => {
                                    const IconComponent = ICON_MAP[agent.icon || "Bot"] || Bot;
                                    return (
                                        <div
                                            key={agent.id}
                                            onClick={() => navigate(agent.route_path)}
                                            className={cn(
                                                "group relative cursor-pointer",
                                                "bg-white/40 dark:bg-zinc-900/40 backdrop-blur-2xl px-6 py-8 rounded-[2rem]",
                                                "border border-white/60 dark:border-zinc-800/60 shadow-xl shadow-zinc-200/20 dark:shadow-none",
                                                "transition-all duration-300 transform hover:-translate-y-1 hover:shadow-2xl hover:bg-white/60 dark:hover:bg-zinc-900/60"
                                            )}
                                        >
                                            <div className="flex items-start justify-between">
                                                <div className={cn(
                                                    "p-4 rounded-2xl bg-zinc-50 dark:bg-zinc-800 transition-transform group-hover:scale-110 duration-500",
                                                    "border border-zinc-200/50 dark:border-zinc-700/50"
                                                )}>
                                                    <IconComponent className="text-zinc-700 dark:text-zinc-300" size={28} />
                                                </div>
                                                <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity duration-300 pr-2">
                                                    <span className="text-xs font-medium text-zinc-400">立即进入</span>
                                                    <ChevronRight size={14} className="text-zinc-400" />
                                                </div>
                                            </div>

                                            <div className="mt-8 space-y-2">
                                                <h3 className="text-xl font-bold text-zinc-900 dark:text-zinc-100 group-hover:text-zinc-800 transition-colors">
                                                    {agent.name}
                                                </h3>
                                                <p className="text-sm text-zinc-500 dark:text-zinc-400 line-clamp-2 leading-relaxed">
                                                    {agent.description || "暂无描述，点击开始探索。"}
                                                </p>
                                            </div>
                                            
                                            {/* Subtle Decorative Gradient */}
                                            <div className="absolute bottom-0 right-0 w-32 h-32 bg-gradient-to-br from-zinc-100/50 to-transparent dark:from-zinc-800/20 rounded-br-[2rem] -z-10 group-hover:from-zinc-200/50 dark:group-hover:from-zinc-700/20 transition-all" />
                                        </div>
                                    );
                                })}
                            </div>
                        </section>
                    ))
                )}
            </div>
        </div>
    );
}
