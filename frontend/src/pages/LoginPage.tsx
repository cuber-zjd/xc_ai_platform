import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
    Bot,
    Infinity as InfinityIcon,
    User,
    Lock,
    Eye,
    EyeOff,
    Cpu,
    Globe,
    Sparkles,
    Zap,
    MessageSquare,
    Code
} from "lucide-react";
import { cn } from "@/lib/utils";

export default function LoginPage() {
    const [showPassword, setShowPassword] = useState(false);

    const models = [
        { name: "ChatGPT Search", icon: Globe },
        { name: "Gemini 2.0 Pro", icon: Sparkles },
        { name: "Claude 3.7 Thinking", icon: Bot },
        { name: "DeepSeek-R1", icon: Zap },
        { name: "OpenAI o3-mini", icon: Cpu },
        { name: "Llama 3", icon: Code },
        { name: "Stable Diffusion", icon: MessageSquare },
    ];

    return (
        <div className="flex h-screen w-full overflow-hidden bg-background font-sans text-foreground">
            {/* Left Panel - Feature Showcase */}
            <div className="relative hidden w-[90%] flex-col items-center justify-center border-r border-border bg-zinc-50/50 p-10 lg:flex dark:bg-zinc-900">
                {/* Background Pattern */}
                <div className="absolute inset-0 z-0 bg-[radial-gradient(#e5e7eb_1px,transparent_1px)] [background-size:16px_16px] opacity-50 dark:bg-[radial-gradient(#3f3f46_1px,transparent_1px)]" />

                {/* Central Logo */}
                <div className="relative z-10 flex flex-col items-center gap-6">
                    <div className="flex items-center gap-4">
                        <InfinityIcon className="h-32 w-32 text-black dark:text-white stroke-[1.5]" />
                        <span className="text-6xl font-light tracking-tight text-black dark:text-white">
                            企业（Enterprise）
                        </span>
                    </div>

                    <div className="mt-12 grid grid-cols-2 gap-8 text-sm text-muted-foreground/80">
                        <div className="flex items-center gap-2">
                            <span className="h-2 w-2 rounded-full bg-black dark:bg-white" />
                            业务协同 (Business)
                        </div>
                        <div className="flex items-center gap-2">
                            <span className="h-2 w-2 rounded-full bg-black dark:bg-white" />
                            数据驱动 (Data)
                        </div>
                        <div className="flex items-center gap-2">
                            <span className="h-2 w-2 rounded-full bg-black dark:bg-white" />
                            知识沉淀 (Knowledge)
                        </div>
                    </div>
                </div>

                {/* Floating Model Names (Decorative) */}
                <div className="absolute left-10 top-20 flex flex-col gap-8 opacity-40 blur-[1px]">
                    {models.map((m, i) => (
                        <div key={i} className="flex items-center gap-3 text-sm font-medium text-zinc-500">
                            <m.icon className="h-4 w-4" />
                            {m.name}
                        </div>
                    ))}
                </div>
            </div>

            {/* Right Panel - Login Form */}
            <div className="flex w-full flex-col items-center justify-center p-8 lg:w-1/2">
                <div className="w-full max-w-md space-y-8">

                    {/* Header */}
                    <div className="flex items-center gap-3 text-2xl font-semibold tracking-tight">
                        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-black text-white dark:bg-white dark:text-black">
                            <Sparkles className="h-5 w-5" />
                        </div>
                        AI 平台
                    </div>

                    <div className="space-y-2">
                        <h1 className="text-3xl font-bold tracking-tight text-black dark:text-white">登录</h1>
                        <p className="text-sm text-muted-foreground">
                            请输入您的企业工号和密码以继续
                        </p>
                    </div>

                    {/* Form */}
                    <form className="space-y-6" onSubmit={(e) => e.preventDefault()}>
                        <div className="space-y-4">
                            <div className="space-y-2">
                                <Label htmlFor="username">账号 / 工号</Label>
                                <div className="relative">
                                    <User className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
                                    <Input
                                        id="username"
                                        placeholder="请输入工号"
                                        className="pl-10 h-11 bg-zinc-50/50 border-input focus-visible:ring-black"
                                    />
                                </div>
                            </div>

                            <div className="space-y-2">
                                <div className="flex items-center justify-between">
                                    <Label htmlFor="password">密码</Label>
                                    <a href="#" className="text-xs text-muted-foreground hover:text-black underline-offset-4 hover:underline">
                                        忘记密码?
                                    </a>
                                </div>
                                <div className="relative">
                                    <Lock className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
                                    <Input
                                        id="password"
                                        type={showPassword ? "text" : "password"}
                                        placeholder="请输入密码"
                                        className="pl-10 pr-10 h-11 bg-zinc-50/50 border-input focus-visible:ring-black"
                                    />
                                    <Button
                                        type="button"
                                        variant="ghost"
                                        size="icon"
                                        className="absolute right-0 top-0 h-11 w-11 text-muted-foreground hover:text-black"
                                        onClick={() => setShowPassword(!showPassword)}
                                    >
                                        {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                                    </Button>
                                </div>
                                <p className="text-[10px] text-muted-foreground">
                                    密码长度需为 8-24 位，包含字母和数字
                                </p>
                            </div>
                        </div>

                        <Button className="w-full h-11 bg-black text-white hover:bg-zinc-800 dark:bg-white dark:text-black dark:hover:bg-zinc-200 shadow-lg shadow-black/5 text-base font-medium">
                            登 录
                        </Button>
                    </form>

                    {/* Footer */}
                    <div className="text-center text-xs text-muted-foreground/50">
                        &copy; 2025 AI Platform. All rights reserved.
                    </div>
                </div>
            </div>
        </div>
    );
}
