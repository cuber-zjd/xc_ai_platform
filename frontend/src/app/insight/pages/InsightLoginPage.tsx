import { useState } from "react";
import { Eye, EyeOff, LockKeyhole, Radar, UserRound } from "lucide-react";
import { Navigate, useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuthStore } from "@/store/useAuthStore";

import loginHero from "../assets/login-hero.png";
import { InsightThemeScope } from "../theme/InsightThemeScope";

export function InsightLoginPage() {
    const login = useAuthStore((state) => state.login);
    const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
    const navigate = useNavigate();
    const [username, setUsername] = useState("");
    const [password, setPassword] = useState("");
    const [showPassword, setShowPassword] = useState(false);
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState("");

    if (isAuthenticated) {
        return <Navigate to="/insight" replace />;
    }

    const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
        event.preventDefault();
        setError("");

        const trimmedUsername = username.trim();
        if (!trimmedUsername || !password) {
            setError("请输入账号和密码");
            return;
        }

        try {
            setIsLoading(true);
            await login(trimmedUsername, password);
            navigate("/insight", { replace: true });
        } catch (loginError: unknown) {
            setError(getLoginErrorMessage(loginError));
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <InsightThemeScope>
            <main className="relative min-h-screen overflow-hidden bg-[#edf6fd] text-slate-950">
                <img src={loginHero} alt="" className="absolute inset-0 h-full w-full object-cover object-center" />
                <div className="absolute inset-0 bg-linear-to-r from-white/20 via-[#edf6fd]/18 to-[#edf6fd]/86" />
                <div className="absolute inset-0 bg-linear-to-b from-white/35 via-transparent to-[#edf6fd]/42" />

                <section className="relative z-10 grid min-h-screen grid-cols-1 gap-8 px-5 py-7 sm:px-8 lg:grid-cols-[minmax(0,1fr)_minmax(420px,0.56fr)] lg:px-14 xl:px-16">
                    <div className="flex min-h-[34vh] flex-col lg:min-h-0">
                        <div className="flex items-center gap-3">
                            <div className="grid size-11 place-items-center rounded-2xl bg-blue-600 text-white shadow-[0_16px_36px_rgba(37,99,235,0.22)]">
                                <Radar className="size-5" />
                            </div>
                            <div className="text-lg font-black tracking-tight text-[#102040]">研发营销市场洞察平台</div>
                        </div>

                        <div className="mt-12 max-w-3xl lg:mt-16 xl:mt-20">
                            <h1 className="text-4xl font-black leading-tight tracking-tight text-[#0b2756] xl:text-5xl">
                                洞察市场信号 · 驱动研发增长
                            </h1>
                            <p className="mt-5 max-w-2xl text-base font-semibold leading-8 text-[#5f718d] xl:text-lg">
                                汇聚行业趋势、竞品动态与营销线索，辅助研发和市场团队更快发现机会。
                            </p>
                        </div>
                    </div>

                    <div className="flex items-center justify-center lg:justify-end">
                        <div className="w-full max-w-[470px]">
                            <div className="rounded-[30px] border border-white/80 bg-white/94 p-6 shadow-[0_26px_76px_rgba(30,74,120,0.13)] backdrop-blur sm:p-9">
                                <div className="mb-9 text-center">
                                    <h2 className="text-3xl font-black tracking-tight text-slate-950">欢迎登录</h2>
                                    <p className="mt-3 text-sm font-semibold text-slate-400">市场洞察平台</p>
                                </div>

                                <form className="space-y-5" onSubmit={handleSubmit}>
                                    {error ? (
                                        <div className="rounded-2xl border border-red-100 bg-red-50 px-4 py-3 text-sm font-bold text-red-600">
                                            {error}
                                        </div>
                                    ) : null}

                                    <div className="space-y-2">
                                        <Label htmlFor="insight-username" className="text-sm font-black text-slate-700">
                                            账号
                                        </Label>
                                        <div className="relative">
                                            <UserRound className="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-slate-400" />
                                            <Input
                                                id="insight-username"
                                                value={username}
                                                onChange={(event) => setUsername(event.target.value)}
                                                disabled={isLoading}
                                                autoComplete="username"
                                                placeholder="请输入账号"
                                                className="h-12 rounded-2xl border-slate-200 bg-white/80 pl-10 font-semibold focus-visible:border-blue-300 focus-visible:ring-blue-100"
                                            />
                                        </div>
                                    </div>

                                    <div className="space-y-2">
                                        <Label htmlFor="insight-password" className="text-sm font-black text-slate-700">
                                            密码
                                        </Label>
                                        <div className="relative">
                                            <LockKeyhole className="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-slate-400" />
                                            <Input
                                                id="insight-password"
                                                value={password}
                                                onChange={(event) => setPassword(event.target.value)}
                                                disabled={isLoading}
                                                type={showPassword ? "text" : "password"}
                                                autoComplete="current-password"
                                                placeholder="请输入密码"
                                                className="h-12 rounded-2xl border-slate-200 bg-white/80 pl-10 pr-12 font-semibold focus-visible:border-blue-300 focus-visible:ring-blue-100"
                                            />
                                            <Button
                                                type="button"
                                                variant="ghost"
                                                size="icon-sm"
                                                disabled={isLoading}
                                                className="absolute right-2 top-1/2 -translate-y-1/2 rounded-xl text-slate-500 hover:bg-slate-100"
                                                onClick={() => setShowPassword((current) => !current)}
                                                aria-label={showPassword ? "隐藏密码" : "显示密码"}
                                            >
                                                {showPassword ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                                            </Button>
                                        </div>
                                    </div>

                                    <Button
                                        type="submit"
                                        disabled={isLoading}
                                        size="lg"
                                        className="h-12 w-full rounded-2xl bg-blue-600 text-base font-black text-white shadow-[0_16px_34px_rgba(37,99,235,0.22)] hover:bg-blue-700"
                                    >
                                        {isLoading ? "正在登录..." : "登录"}
                                    </Button>
                                </form>
                            </div>

                            <p className="mt-6 text-center text-xs font-semibold text-slate-400">
                                版权所有 © {new Date().getFullYear()} 研发营销市场洞察平台
                            </p>
                        </div>
                    </div>
                </section>
            </main>
        </InsightThemeScope>
    );
}

function getLoginErrorMessage(error: unknown) {
    if (typeof error === "object" && error !== null && "response" in error) {
        const response = (error as { response?: { data?: { detail?: string } } }).response;
        return response?.data?.detail || "登录失败，请检查账号或密码";
    }
    return "登录失败，请检查账号或密码";
}
