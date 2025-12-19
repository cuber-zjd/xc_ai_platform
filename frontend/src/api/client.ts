import axios from 'axios';
import { useAuthStore } from '@/store/useAuthStore';

// Default to localhost:8000 if not specified (Standard FastAPI port)
const baseURL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';

export const apiClient = axios.create({
    baseURL,
    timeout: 10000,
    headers: {
        'Content-Type': 'application/json',
    },
});

// Request Interceptor: Attach Token
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

// Response Interceptor: Error Handling
apiClient.interceptors.response.use(
    (response) => {
        // Backend returns standard Result { code: 200, msg: "...", data: ... }
        const res = response.data;

        // If the API returns the Result wrapper
        if (res && typeof res.code === 'number') {
            if (res.code === 200) {
                return res.data;
            } else {
                // Business Logic Error (handled as promise rejection)
                return Promise.reject({
                    response: {
                        data: { detail: res.msg || 'Error' }
                    }
                });
            }
        }

        // Fallback for non-standard responses
        return res;
    },
    (error) => {
        // 401: Unauthorized -> Logout
        if (error.response?.status === 401) {
            useAuthStore.getState().logout();
        }
        return Promise.reject(error);
    }
);
