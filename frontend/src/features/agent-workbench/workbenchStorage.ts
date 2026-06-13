export interface WorkbenchAgent {
    id: number;
    name: string;
    description?: string;
    icon?: string | null;
    route_path: string;
}

export interface WorkbenchGroup {
    id: number;
    name: string;
    agents: WorkbenchAgent[];
}

export const PINNED_AGENTS_STORAGE_KEY = 'ai-platform:pinned-agents';
export const RECENT_AGENTS_STORAGE_KEY = 'ai-platform:recent-agents';

const MAX_RECENT_AGENTS = 8;

function canUseStorage() {
    return typeof window !== 'undefined' && typeof window.localStorage !== 'undefined';
}

function readAgentIds(key: string) {
    if (!canUseStorage()) return [];

    try {
        const value = window.localStorage.getItem(key);
        if (!value) return [];
        const parsed = JSON.parse(value);
        if (!Array.isArray(parsed)) return [];
        return parsed
            .map((item) => Number(item))
            .filter((item) => Number.isInteger(item) && item > 0);
    } catch {
        return [];
    }
}

function writeAgentIds(key: string, ids: number[]) {
    if (!canUseStorage()) return;
    window.localStorage.setItem(key, JSON.stringify(Array.from(new Set(ids))));
}

export function flattenWorkbenchGroups(groups: WorkbenchGroup[]) {
    return groups.flatMap((group) => group.agents.map((agent) => ({ ...agent, groupName: group.name })));
}

export function getPinnedAgentIds() {
    return readAgentIds(PINNED_AGENTS_STORAGE_KEY);
}

export function setPinnedAgentIds(ids: number[]) {
    writeAgentIds(PINNED_AGENTS_STORAGE_KEY, ids);
}

export function getRecentAgentIds() {
    return readAgentIds(RECENT_AGENTS_STORAGE_KEY);
}

export function setRecentAgentIds(ids: number[]) {
    writeAgentIds(RECENT_AGENTS_STORAGE_KEY, ids.slice(0, MAX_RECENT_AGENTS));
}

export function recordRecentAgent(agentId: number) {
    const nextIds = [agentId, ...getRecentAgentIds().filter((id) => id !== agentId)];
    setRecentAgentIds(nextIds);
    return nextIds.slice(0, MAX_RECENT_AGENTS);
}

export function togglePinnedAgent(agentId: number) {
    const pinnedIds = getPinnedAgentIds();
    const nextIds = pinnedIds.includes(agentId)
        ? pinnedIds.filter((id) => id !== agentId)
        : [agentId, ...pinnedIds];
    setPinnedAgentIds(nextIds);
    return nextIds;
}

export function selectVisibleAgents(agentIds: number[], agents: WorkbenchAgent[]) {
    const agentById = new Map(agents.map((agent) => [agent.id, agent]));
    return agentIds.map((id) => agentById.get(id)).filter((agent): agent is WorkbenchAgent => Boolean(agent));
}
