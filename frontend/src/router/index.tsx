import { lazy, Suspense, type JSX } from "react";
import {
    createBrowserRouter,
    isRouteErrorResponse,
    Navigate,
    RouterProvider,
    useRouteError,
} from "react-router-dom";

import AdminLayout from "@/components/layout/AdminLayout";
import UserLayout from "@/components/layout/UserLayout";
import LoginPage from "@/pages/auth/LoginPage";
import { useAuthStore } from "@/store/useAuthStore";

const DashboardPage = lazy(() => import("@/pages/dashboard"));
const UserPage = lazy(() => import("@/pages/system/UserPage"));
const ContractListPage = lazy(() =>
    import("@/features/contract/pages/ContractListPage").then((module) => ({ default: module.ContractListPage })),
);
const ContractDetailPage = lazy(() =>
    import("@/features/contract/pages/ContractDetailPage").then((module) => ({ default: module.ContractDetailPage })),
);
const ContractSidecarPage = lazy(() =>
    import("@/features/contract/pages/ContractSidecarPage").then((module) => ({ default: module.ContractSidecarPage })),
);
const RolePage = lazy(() => import("@/pages/system/RolePage"));
const AgentManagerPage = lazy(() => import("@/pages/system/agent/AgentManagerPage"));
const ModelPage = lazy(() => import("@/pages/system/ModelPage"));

const ChatHomePage = lazy(() => import("@/pages/user-home/ChatHomePage"));
const WorkbenchPage = lazy(() => import("@/pages/dashboard/WorkbenchPage"));
const ToolboxPage = lazy(() => import("@/pages/user-home/ToolboxPage"));
const AgentTestPage = lazy(() => import("@/pages/agent-test/AgentTestPage"));
const FrAiReportChatPage = lazy(() =>
    import("@/features/fr-ai-report/pages/FrAiReportChatPage").then((module) => ({ default: module.FrAiReportChatPage })),
);

const PageLoader = () => (
    <div className="app-page flex min-h-[60vh] items-center justify-center">
        <div className="app-panel flex min-w-[260px] flex-col items-center gap-4 rounded-[28px] px-8 py-10 text-center">
            <div className="h-10 w-10 animate-spin rounded-full border-2 border-[#7261f8] border-t-transparent" />
            <span className="text-sm font-semibold text-[#81849b]">页面加载中...</span>
        </div>
    </div>
);

const RouteErrorPage = () => {
    const error = useRouteError();

    let title = "页面加载失败";
    let description = "当前页面暂时无法打开，请稍后重试。";

    if (isRouteErrorResponse(error)) {
        title = `${error.status} ${error.statusText}`;
        description = typeof error.data === "string" ? error.data : description;
    } else if (error instanceof Error && error.message) {
        description = error.message;
    }

    return (
        <div className="app-page flex min-h-[60vh] items-center justify-center px-6">
            <div className="app-panel w-full max-w-xl rounded-[32px] p-8 text-center">
                <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-[20px] bg-linear-to-br from-[#eef1ff] to-[#fbf8ff] text-lg font-semibold text-[#5f62f4]">
                    !
                </div>
                <h2 className="text-2xl font-black tracking-[-0.04em] text-[#24233b]">{title}</h2>
                <p className="mt-3 text-sm leading-6 text-[#7d8096]">{description}</p>
                <div className="mt-6 flex items-center justify-center gap-3">
                    <button
                        type="button"
                        className="inline-flex h-11 items-center justify-center rounded-full border border-white/85 bg-white/80 px-5 text-sm font-semibold text-[#4f5268] transition-colors hover:bg-white"
                        onClick={() => window.location.reload()}
                    >
                        刷新页面
                    </button>
                    <button
                        type="button"
                        className="inline-flex h-11 items-center justify-center rounded-full bg-linear-to-r from-[#6e5df7] to-[#b48fff] px-5 text-sm font-semibold text-white shadow-[0_14px_32px_rgba(110,93,247,0.28)] transition-opacity hover:opacity-95"
                        onClick={() => window.history.back()}
                    >
                        返回上一页
                    </button>
                </div>
            </div>
        </div>
    );
};

const ProtectedRoute = ({ children }: { children: JSX.Element }) => {
    const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
    if (!isAuthenticated) return <Navigate to="/login" replace />;
    return children;
};

const AdminRoute = ({ children }: { children: JSX.Element }) => {
    const user = useAuthStore((state) => state.user);
    if (user?.role !== "admin") return <Navigate to="/chat-home" replace />;
    return children;
};

const RoleRedirect = () => {
    const user = useAuthStore((state) => state.user);
    if (user?.role === "admin") {
        return <Navigate to="/admin/dashboard" replace />;
    }
    return <Navigate to="/chat-home" replace />;
};

const router = createBrowserRouter([
    {
        path: "/login",
        element: <LoginPage />,
        errorElement: <RouteErrorPage />,
    },
    {
        path: "/",
        element: (
            <ProtectedRoute>
                <RoleRedirect />
            </ProtectedRoute>
        ),
        errorElement: <RouteErrorPage />,
    },
    {
        path: "/admin",
        element: (
            <ProtectedRoute>
                <AdminRoute>
                    <AdminLayout />
                </AdminRoute>
            </ProtectedRoute>
        ),
        errorElement: <RouteErrorPage />,
        children: [
            {
                index: true,
                element: <Navigate to="/admin/dashboard" replace />,
            },
            {
                path: "dashboard",
                element: (
                    <Suspense fallback={<PageLoader />}>
                        <DashboardPage />
                    </Suspense>
                ),
            },
            {
                path: "users",
                element: (
                    <Suspense fallback={<PageLoader />}>
                        <UserPage />
                    </Suspense>
                ),
            },
            {
                path: "contracts",
                element: (
                    <Suspense fallback={<PageLoader />}>
                        <ContractListPage />
                    </Suspense>
                ),
            },
            {
                path: "fr-ai-reports",
                element: (
                    <Suspense fallback={<PageLoader />}>
                        <FrAiReportChatPage />
                    </Suspense>
                ),
            },
            {
                path: "contract/:id",
                element: (
                    <Suspense fallback={<PageLoader />}>
                        <ContractDetailPage />
                    </Suspense>
                ),
            },
            {
                path: "agents",
                element: (
                    <Suspense fallback={<PageLoader />}>
                        <AgentManagerPage />
                    </Suspense>
                ),
            },
            {
                path: "permissions",
                element: (
                    <Suspense fallback={<PageLoader />}>
                        <RolePage />
                    </Suspense>
                ),
            },
            {
                path: "models",
                element: (
                    <Suspense fallback={<PageLoader />}>
                        <ModelPage />
                    </Suspense>
                ),
            },
            {
                path: "settings",
                element: <div className="app-page flex h-64 items-center justify-center text-[#8b8fa5]">系统设置页面开发中...</div>,
            },
        ],
    },
    {
        path: "/",
        element: (
            <ProtectedRoute>
                <UserLayout />
            </ProtectedRoute>
        ),
        errorElement: <RouteErrorPage />,
        children: [
            {
                path: "chat-home",
                element: (
                    <Suspense fallback={<PageLoader />}>
                        <ChatHomePage />
                    </Suspense>
                ),
            },
            {
                path: "workspace",
                element: (
                    <Suspense fallback={<PageLoader />}>
                        <WorkbenchPage />
                    </Suspense>
                ),
            },
            {
                path: "toolbox",
                element: (
                    <Suspense fallback={<PageLoader />}>
                        <ToolboxPage />
                    </Suspense>
                ),
            },
            {
                path: "contracts",
                element: (
                    <Suspense fallback={<PageLoader />}>
                        <ContractListPage />
                    </Suspense>
                ),
            },
            {
                path: "fr-ai-reports",
                element: (
                    <Suspense fallback={<PageLoader />}>
                        <FrAiReportChatPage />
                    </Suspense>
                ),
            },
            {
                path: "contract/:id",
                element: (
                    <Suspense fallback={<PageLoader />}>
                        <ContractDetailPage />
                    </Suspense>
                ),
            },
        ],
    },
    {
        path: "/agent-test",
        element: (
            <Suspense fallback={<PageLoader />}>
                <AgentTestPage />
            </Suspense>
        ),
        errorElement: <RouteErrorPage />,
    },
    {
        path: "/contract/sidecar/:id",
        element: (
            <Suspense fallback={<PageLoader />}>
                <ContractSidecarPage />
            </Suspense>
        ),
        errorElement: <RouteErrorPage />,
    },
    {
        path: "*",
        element: (
            <div className="app-page flex h-screen flex-col items-center justify-center gap-4">
                <span className="text-6xl font-black text-[#c9ccdd]">404</span>
                <span className="text-[#8d90a6]">页面未找到</span>
            </div>
        ),
        errorElement: <RouteErrorPage />,
    },
]);

export default function AppRouter() {
    return <RouterProvider router={router} />;
}
