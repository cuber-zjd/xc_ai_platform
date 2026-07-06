import { useEffect, useState } from "react";
import { Loader2, ShieldAlert } from "lucide-react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { authApi } from "@/api/auth";
import { useAuthStore } from "@/store/useAuthStore";

export function InsightWecomAuthPage() {
    const [searchParams] = useSearchParams();
    const navigate = useNavigate();
    const [message, setMessage] = useState("正在确认企业微信身份...");

    useEffect(() => {
        const token = searchParams.get("token");
        const error = searchParams.get("error");
        const redirect = normalizeRedirect(searchParams.get("redirect"));
        if (error || !token) {
            setMessage("当前企业微信账号未绑定平台用户，或没有权限访问该内容。");
            return;
        }
        localStorage.setItem("token", token);
        authApi
            .me()
            .then((user) => {
                useAuthStore.getState().setAuth(token, user);
                navigate(redirect, { replace: true });
            })
            .catch(() => {
                localStorage.removeItem("token");
                useAuthStore.getState().logout();
                setMessage("企业微信身份已识别，但平台登录态创建失败，请联系管理员检查账号映射。");
            });
    }, [navigate, searchParams]);

    return (
        <div className="flex min-h-screen items-center justify-center bg-slate-50 px-6">
            <div className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-8 text-center shadow-sm">
                {message.includes("正在") ? (
                    <Loader2 className="mx-auto size-8 animate-spin text-primary" />
                ) : (
                    <ShieldAlert className="mx-auto size-8 text-amber-500" />
                )}
                <div className="mt-5 text-lg font-black text-slate-950">研发营销市场洞察平台</div>
                <p className="mt-3 text-sm font-semibold leading-6 text-slate-600">{message}</p>
            </div>
        </div>
    );
}

function normalizeRedirect(value: string | null) {
    const redirect = value || "/ai/insight";
    if (redirect.startsWith("/ai/insight")) return redirect;
    if (redirect.startsWith("/insight")) return `/ai${redirect}`;
    return "/ai/insight";
}
