import { apiClient } from './client';
import type { User } from './auth';

export interface UserListResult {
    total: number;
    items: User[];
    page: number;
    size: number;
}

export interface UserCreatePayload {
    username: string;
    full_name: string;
    email?: string;
    password: string;
    is_superuser?: boolean;
    status?: number;
}

export interface UserUpdatePayload {
    full_name?: string;
    email?: string;
    password?: string;
    is_superuser?: boolean;
    status?: number;
}

export const userApi = {
    getList: async (page = 1, size = 20) => {
        return apiClient.get<any, UserListResult>('/users', {
            params: { page, size }
        });
    },

    create: async (data: UserCreatePayload) => {
        return apiClient.post<any, User>('/users', data);
    },

    update: async (id: string, data: UserUpdatePayload) => {
        return apiClient.put<any, User>(`/users/${id}`, data);
    },

    delete: async (id: string) => {
        return apiClient.delete<any, any>(`/users/${id}`);
    }
};
