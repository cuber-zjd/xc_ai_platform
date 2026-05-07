/**
 * AI 模型配置管理 API
 */
import { apiClient } from './client';

// ========== 类型定义 ==========

/** 模型配置（后端返回，API Key 已脱敏） */
export interface ModelConfig {
    id: number;
    model_name: string;
    model_code: string;
    provider: string;
    base_url: string;
    model_level: number;
    model_type: string;
    capability: string | null;
    max_tokens: number | null;
    default_temperature: number;
    priority: number;
    is_enabled: boolean;
    status: number;
    comment: string | null;
    api_key_masked: string;
}

/** 创建模型配置 */
export interface ModelCreatePayload {
    model_name: string;
    model_code: string;
    provider: string;
    api_key: string;
    base_url: string;
    model_level?: number;
    model_type?: string;
    capability?: string;
    max_tokens?: number;
    default_temperature?: number;
    priority?: number;
    is_enabled?: boolean;
    status?: number;
    comment?: string;
}

/** 更新模型配置 */
export interface ModelUpdatePayload {
    model_name?: string;
    model_code?: string;
    provider?: string;
    api_key?: string;
    base_url?: string;
    model_level?: number;
    model_type?: string;
    capability?: string;
    max_tokens?: number;
    default_temperature?: number;
    priority?: number;
    is_enabled?: boolean;
    status?: number;
    comment?: string;
}

/** 熔断器状态 */
export interface CircuitBreakerStatus {
    [modelName: string]: {
        state: 'closed' | 'open' | 'half_open';
        failure_count: number;
        last_failure_time: number;
        is_available: boolean;
    };
}

// ========== API 方法 ==========

export const modelApi = {
    /** 获取所有模型配置 */
    getList: async () => {
        return apiClient.get<any, ModelConfig[]>('/models');
    },

    /** 创建模型配置 */
    create: async (data: ModelCreatePayload) => {
        return apiClient.post<any, { id: number; model_name: string }>('/models', data);
    },

    /** 更新模型配置 */
    update: async (id: number, data: ModelUpdatePayload) => {
        return apiClient.put<any, { id: number; model_name: string }>(`/models/${id}`, data);
    },

    /** 删除模型配置 */
    delete: async (id: number) => {
        return apiClient.delete<any, any>(`/models/${id}`);
    },

    /** 获取熔断器状态 */
    getCircuitBreakers: async () => {
        return apiClient.get<any, CircuitBreakerStatus>('/models/circuit-breakers');
    },

    /** 重置熔断器 */
    resetCircuitBreaker: async (modelName?: string) => {
        return apiClient.post<any, any>('/models/circuit-breakers/reset', null, {
            params: modelName ? { model_name: modelName } : {},
        });
    },

    /** 清除模型配置缓存 */
    invalidateCache: async () => {
        return apiClient.post<any, any>('/models/cache/invalidate');
    },
};
