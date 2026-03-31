import { createBrowserRouter, Navigate, RouterProvider } from 'react-router-dom';
import LoginPage from '@/pages/auth/LoginPage';
import { lazy, Suspense, type JSX } from 'react';
import { useAuthStore } from '@/store/useAuthStore';

// 布局组件
import AdminLayout from '@/components/layout/AdminLayout';
import UserLayout from '@/components/layout/UserLayout';

// 管理员页面 - 懒加载
const DashboardPage = lazy(() => import('@/pages/dashboard'));
const UserPage = lazy(() => import('@/pages/system/UserPage'));
const ContractListPage = lazy(() => import('@/features/contract/pages/ContractListPage').then(module => ({ default: module.ContractListPage })));
const ContractDetailPage = lazy(() => import('@/features/contract/pages/ContractDetailPage').then(module => ({ default: module.ContractDetailPage })));
const ContractSidecarPage = lazy(() => import('@/features/contract/pages/ContractSidecarPage').then(module => ({ default: module.ContractSidecarPage })));
const RolePage = lazy(() => import('@/pages/system/RolePage'));
const AgentManagerPage = lazy(() => import('@/pages/system/agent/AgentManagerPage'));

// 普通用户页面 - 懒加载
const ChatHomePage = lazy(() => import('@/pages/user-home/ChatHomePage'));
const WorkbenchPage = lazy(() => import('@/pages/dashboard/WorkbenchPage'));
const ToolboxPage = lazy(() => import('@/pages/user-home/ToolboxPage'));
const WarehousePage = lazy(() => import('@/pages/agent_pages/warehouse/WarehousePage'));

// 加载占位符
const PageLoader = () => (
    <div className="flex items-center justify-center h-full">
        <div className="flex flex-col items-center gap-3">
            <div className="h-8 w-8 rounded-full border-2 border-primary border-t-transparent animate-spin" />
            <span className="text-sm text-muted-foreground">加载中...</span>
        </div>
    </div>
);

// 认证守卫
const ProtectedRoute = ({ children }: { children: JSX.Element }) => {
    const isAuthenticated = useAuthStore(state => state.isAuthenticated);
    if (!isAuthenticated) return <Navigate to="/login" replace />;
    return children;
};

// 管理员守卫 - 非管理员跳转到用户首页
const AdminRoute = ({ children }: { children: JSX.Element }) => {
    const user = useAuthStore(state => state.user);
    if (user?.role !== 'admin') return <Navigate to="/chat-home" replace />;
    return children;
};

// 根路由重定向 - 根据角色决定跳转
const RoleRedirect = () => {
    const user = useAuthStore(state => state.user);
    if (user?.role === 'admin') {
        return <Navigate to="/admin/dashboard" replace />;
    }
    return <Navigate to="/chat-home" replace />;
};

const router = createBrowserRouter([
    {
        path: '/login',
        element: <LoginPage />,
    },
    // 根路径 - 根据角色跳转
    {
        path: '/',
        element: (
            <ProtectedRoute>
                <RoleRedirect />
            </ProtectedRoute>
        ),
    },
    // ==================== 管理员路由 ====================
    {
        path: '/admin',
        element: (
            <ProtectedRoute>
                <AdminRoute>
                    <AdminLayout />
                </AdminRoute>
            </ProtectedRoute>
        ),
        children: [
            {
                index: true,
                element: <Navigate to="/admin/dashboard" replace />
            },
            {
                path: 'dashboard',
                element: (
                    <Suspense fallback={<PageLoader />}>
                        <DashboardPage />
                    </Suspense>
                )
            },
            {
                path: 'users',
                element: (
                    <Suspense fallback={<PageLoader />}>
                        <UserPage />
                    </Suspense>
                )
            },
            {
                path: 'contracts',
                element: (
                    <Suspense fallback={<PageLoader />}>
                        <ContractListPage />
                    </Suspense>
                )
            },
            {
                path: 'contract/:id',
                element: (
                    <Suspense fallback={<PageLoader />}>
                        <ContractDetailPage />
                    </Suspense>
                )
            },
            {
                path: 'agents',
                element: (
                    <Suspense fallback={<PageLoader />}>
                        <AgentManagerPage />
                    </Suspense>
                )
            },
            {
                path: 'permissions',
                element: (
                    <Suspense fallback={<PageLoader />}>
                        <RolePage />
                    </Suspense>
                )
            },
            {
                path: 'settings',
                element: <div className="flex items-center justify-center h-64 text-muted-foreground">系统设置页面（开发中...）</div>
            },
        ]
    },
    // ==================== 普通用户路由 ====================
    {
        path: '/',
        element: (
            <ProtectedRoute>
                <UserLayout />
            </ProtectedRoute>
        ),
        children: [
            {
                path: 'chat-home',
                element: (
                    <Suspense fallback={<PageLoader />}>
                        <ChatHomePage />
                    </Suspense>
                )
            },
            {
                path: 'workspace',
                element: (
                    <Suspense fallback={<PageLoader />}>
                        <WorkbenchPage />
                    </Suspense>
                )
            },
            {
                path: 'toolbox',
                element: (
                    <Suspense fallback={<PageLoader />}>
                        <ToolboxPage />
                    </Suspense>
                )
            },
            {
                path: 'contracts',
                element: (
                    <Suspense fallback={<PageLoader />}>
                        <ContractListPage />
                    </Suspense>
                )
            },
            {
                path: 'contract/:id',
                element: (
                    <Suspense fallback={<PageLoader />}>
                        <ContractDetailPage />
                    </Suspense>
                )
            },
        ]
    },
    // ==================== 公共路由 ====================
    {
        path: '/contract/sidecar/:id',
        element: (
            <Suspense fallback={<PageLoader />}>
                <ContractSidecarPage />
            </Suspense>
        )
    },
    {
        path: '*',
        element: (
            <div className="flex flex-col items-center justify-center h-screen gap-4">
                <span className="text-6xl font-bold text-muted-foreground/30">404</span>
                <span className="text-muted-foreground">页面未找到</span>
            </div>
        )
    }
]);

export default function AppRouter() {
    return <RouterProvider router={router} />;
}
