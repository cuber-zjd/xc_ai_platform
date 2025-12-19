import { createBrowserRouter, Navigate, RouterProvider } from 'react-router-dom';
import MainLayout from '@/components/layout/MainLayout';
import LoginPage from '@/pages/auth/LoginPage';
// Lazy load pages for performance
import { lazy, Suspense, type JSX } from 'react';
import { useAuthStore } from '@/store/useAuthStore';

// Lazy imports
const DashboardPage = lazy(() => import('@/pages/dashboard'));
const UserPage = lazy(() => import('@/pages/system/UserPage'));
// const ChatPage = lazy(() => import('@/pages/chat'));

// Guard Component
const ProtectedRoute = ({ children }: { children: JSX.Element }) => {
    // For Development: Simply return children to bypass auth if needed, 
    // OR implementing proper check:
    const isAuthenticated = useAuthStore(state => state.isAuthenticated);

    // NOTE: Uncomment next line to enable strict auth protection
    if (!isAuthenticated) return <Navigate to="/login" replace />;

    return children;
};

const router = createBrowserRouter([
    {
        path: '/login',
        element: <LoginPage />,
    },
    {
        path: '/',
        element: (
            <ProtectedRoute>
                <MainLayout />
            </ProtectedRoute>
        ),
        children: [
            {
                index: true,
                element: <Navigate to="/dashboard" replace />
            },
            {
                path: 'dashboard',
                element: (
                    <Suspense fallback={<div>Loading...</div>}>
                        <DashboardPage />
                    </Suspense>
                )
            },
            {
                path: 'chat',
                // element: <ChatPage />
                element: <div>Chat Page WIP</div>
            },
            {
                path: 'settings',
                element: <div>Settings Page WIP</div>
            },
            {
                path: 'users',
                element: (
                    <Suspense fallback={<div>Loading...</div>}>
                        <UserPage />
                    </Suspense>
                )
            }
        ]
    },
    {
        path: '*',
        element: <div className="p-10 text-center">404 Not Found</div>
    }
]);

export default function AppRouter() {
    return <RouterProvider router={router} />;
}
