import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import { authApi } from '@/api/auth';
import type { User } from '@/api/auth';

interface AuthState {
    token: string | null;
    user: User | null;
    isAuthenticated: boolean;

    setAuth: (token: string, user: User) => void;
    login: (username: string, password: string) => Promise<void>;
    checkAuth: () => Promise<void>;
    logout: () => void;
}

export const useAuthStore = create<AuthState>()(
    persist(
        (set) => ({
            token: null,
            user: null,
            isAuthenticated: false,

            setAuth: (token, user) => set({ token, user, isAuthenticated: true }),

            login: async (username, password) => {
                const formData = new FormData();
                formData.append('username', username);
                formData.append('password', password);

                const res = await authApi.login(formData);
                localStorage.setItem('token', res.access_token);
                set({ token: res.access_token, user: res.user, isAuthenticated: true });
            },

            checkAuth: async () => {
                const token = localStorage.getItem('token');
                if (!token) {
                    set({ isAuthenticated: false, token: null, user: null });
                    return;
                }

                try {
                    // Update header if not set elsewhere, though interceptor does it.
                    const user = await authApi.me();
                    set({ user, isAuthenticated: true });
                } catch (error) {
                    // Token invalid or expired
                    set({ token: null, user: null, isAuthenticated: false });
                    localStorage.removeItem('token');
                }
            },

            logout: () => {
                localStorage.removeItem('token');
                set({ token: null, user: null, isAuthenticated: false });
            },
        }),
        {
            name: 'auth-storage', // key in localStorage
            storage: createJSONStorage(() => localStorage),
        }
    )
);
