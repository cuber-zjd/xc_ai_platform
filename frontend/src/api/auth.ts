import { apiClient } from './client';

export interface User {
    id: string;
    username: string;
    email?: string;
    full_name?: string;
    role?: string;
    avatar?: string;
    dept_id?: string;
    status?: number;
}

export interface LoginResponse {
    access_token: string;
    token_type: string;
    user: User;
}

export const authApi = {
    login: async (credentials: FormData) => {
        // Using FormData for OAuth2PasswordRequestForm compatibility in FastAPI
        return apiClient.post<any, LoginResponse>('/login/access-token', credentials, {
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' }
        });
    },

    me: async () => {
        return apiClient.get<any, User>('/users/me');
    }
};
