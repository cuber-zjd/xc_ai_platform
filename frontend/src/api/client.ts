import axios from 'axios';
import { useAuthStore } from '@/store/useAuthStore';

const DEFAULT_API_BASE_URL = '/ai-api/v1';

function normalizeApiBaseURL(value?: string): string {
    const rawValue = value?.trim();
    if (!rawValue || rawValue === '/v1' || rawValue === 'v1') {
        return DEFAULT_API_BASE_URL;
    }

    try {
        const url = new URL(rawValue);
        if (url.pathname.replace(/\/+$/, '') === '/v1') {
            url.pathname = DEFAULT_API_BASE_URL;
            return url.toString().replace(/\/+$/, '');
        }
    } catch {
        // 相对路径不是完整 URL，继续按路径规则处理。
    }

    return rawValue.replace(/\/+$/, '');
}

const baseURL = normalizeApiBaseURL(import.meta.env.VITE_API_URL);

export const apiClient = axios.create({
    baseURL,
    timeout: 10000,
    headers: {
        'Content-Type': 'application/json',
    },
});

apiClient.interceptors.request.use(
    (config) => {
        const token = useAuthStore.getState().token;
        if (token) {
            config.headers.Authorization = `Bearer ${token}`;
        }
        return config;
    },
    (error) => Promise.reject(error)
);

apiClient.interceptors.response.use(
    (response) => {
        const res = response.data;

        if (res && typeof res.code === 'number') {
            if (res.code === 200) {
                return res.data;
            } else {
                return Promise.reject({
                    response: {
                        data: { detail: res.msg || 'Error' }
                    }
                });
            }
        }

        return res;
    },
    (error) => {
        if (error.response?.status === 401) {
            useAuthStore.getState().logout();
        }
        return Promise.reject(error);
    }
);
