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
        return response.data;
    },
    (error) => {
        // 401: Unauthorized -> Logout
        if (error.response?.status === 401) {
            useAuthStore.getState().logout();
        }
        return Promise.reject(error);
    }
);
