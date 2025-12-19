import { useEffect, useState, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { useAuthStore } from "@/store/useAuthStore";
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
    Zap,
    MessageSquare,
    Sparkles
} from "lucide-react";

// Import Model Logos
import GPT5Logo from "@/assets/models_logo/GPT5.1.svg";
import GeminiLogo from "@/assets/models_logo/Gemini 3.0 Pro.svg";
import ClaudeLogo from "@/assets/models_logo/Claude 4.1 Thinking.svg";
import DeepSeekLogo from "@/assets/models_logo/DeepSeek-R1.ico";
import LlamaLogo from "@/assets/models_logo/Llama 4.ico";
import GrokLogo from "@/assets/models_logo/Grok-4.1.png";
import MistralLogo from "@/assets/models_logo/Mistral Large.svg";
import QwenLogo from "@/assets/models_logo/Qwen-3.0 MAX.png";

// 模型数据常量 - 移到组件外部避免每次渲染重新创建
const MODELS = [
    { name: "GPT5.1", icon: GPT5Logo, isImage: true },
    { name: "Gemini 3.0 Pro", icon: GeminiLogo, isImage: true },
    { name: "Claude 4.1 Thinking", icon: ClaudeLogo, isImage: true },
    { name: "DeepSeek-R1", icon: DeepSeekLogo, isImage: true },
    { name: "DeepSeek-V3.2", icon: DeepSeekLogo, isImage: true },
    { name: "Llama 4", icon: LlamaLogo, isImage: true },
    { name: "Stable Diffusion", icon: MessageSquare, isImage: false },
    { name: "Grok-4.1", icon: GrokLogo, isImage: true },
    { name: "Mistral Large", icon: MistralLogo, isImage: true },
    { name: "Qwen-3.0 MAX", icon: QwenLogo, isImage: true },
];

// 动画常量
const ITEM_HEIGHT = 80;
const TOTAL_HEIGHT = MODELS.length * ITEM_HEIGHT;
const ANIMATION_SPEED = 0.03; // 稍微降低速度使动画更平滑

export default function LoginPage() {
    const [showPassword, setShowPassword] = useState(false);

    // 使用 ref 存储动画偏移量，避免频繁触发 React 重渲染
    const scrollOffsetRef = useRef(0);
    const containerRef = useRef<HTMLDivElement>(null);
    const animationRef = useRef<number>(0);

    // 丝滑动画循环 - 直接操作 DOM 避免 React 重渲染开销
    useEffect(() => {
        let lastTime = performance.now();

        const animate = (currentTime: number) => {
            const delta = currentTime - lastTime;
            lastTime = currentTime;

            scrollOffsetRef.current = (scrollOffsetRef.current + ANIMATION_SPEED * delta) % TOTAL_HEIGHT;

            // 直接更新每个子元素的 transform
            if (containerRef.current) {
                const children = containerRef.current.children;
                for (let i = 0; i < children.length; i++) {
                    const child = children[i] as HTMLElement;
                    const modelIndex = parseInt(child.dataset.index || '0', 10);

                    let relativeY = ((modelIndex * ITEM_HEIGHT - scrollOffsetRef.current + TOTAL_HEIGHT / 2) % TOTAL_HEIGHT);
                    if (relativeY < 0) relativeY += TOTAL_HEIGHT;
                    relativeY -= TOTAL_HEIGHT / 2;

                    const distanceFromCenter = Math.abs(relativeY);
                    const opacity = Math.max(0.1, 1 - (distanceFromCenter / 180));
                    const scale = Math.max(0.85, 1.05 - (distanceFromCenter / 600));

                    if (distanceFromCenter > 280) {
                        child.style.visibility = 'hidden';
                    } else {
                        child.style.visibility = 'visible';
                        child.style.transform = `translate3d(0, ${relativeY - 20}px, 0) scale(${scale})`;
                        child.style.opacity = String(opacity);
                        child.style.zIndex = String(10 - Math.floor(distanceFromCenter / 10));
                    }
                }
            }

            animationRef.current = requestAnimationFrame(animate);
        };

        animationRef.current = requestAnimationFrame(animate);

        return () => {
            if (animationRef.current) {
                cancelAnimationFrame(animationRef.current);
            }
        };
    }, []);

    const { login } = useAuthStore();
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState("");
    const navigate = useNavigate();

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setIsLoading(true);
        setError("");

        // Basic validation
        const username = (document.getElementById("username") as HTMLInputElement).value;
        const password = (document.getElementById("password") as HTMLInputElement).value;

        if (!username || !password) {
            setError("请输入工号和密码");
            setIsLoading(false);
            return;
        }

        try {
            await login(username, password);
            navigate("/"); // Redirect to dashboard
        } catch (err: any) {
            console.error("Login failed:", err);
            setError(err.response?.data?.detail || "登录失败，请检查账号密码");
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <div className="flex h-screen w-full overflow-hidden bg-background font-sans text-foreground">
            {/* Left Panel - Feature Showcase - SAME AS BEFORE, OMITTED FOR BREVITY IF UNCHANGED */}
            <div className="relative hidden w-[90%] border-r border-border bg-zinc-50/50 p-10 lg:flex dark:bg-zinc-900 overflow-hidden">
                {/* ... (Kept existing left panel content) ... */}
                {/* Background Pattern */}
                <div className="absolute inset-0 z-0 bg-[radial-gradient(#e5e7eb_1px,transparent_1px)] [background-size:16px_16px] opacity-50 dark:bg-[radial-gradient(#3f3f46_1px,transparent_1px)]" />

                <div className="relative z-10 grid w-full h-full grid-cols-2 gap-4">

                    {/* Left Side of Panel: Model Carousel */}
                    <div className="flex flex-col items-end justify-center pr-8 border-r border-zinc-200/50 dark:border-zinc-800/50 relative overflow-hidden h-full">
                        {/* Fade masks */}
                        <div className="absolute top-0 left-0 right-0 h-32 bg-gradient-to-b from-zinc-50 to-transparent z-20 dark:from-zinc-900 pointer-events-none" />
                        <div className="absolute bottom-0 left-0 right-0 h-32 bg-gradient-to-t from-zinc-50 to-transparent z-20 dark:from-zinc-900 pointer-events-none" />

                        <div className="absolute inset-0 flex items-center justify-end pr-8">
                            {/* 模型滚动容器 - 使用 ref 直接操作 DOM 实现丝滑动画 */}
                            <div ref={containerRef} className="relative w-full h-[400px]">
                                {MODELS.map((model, i) => (
                                    <div
                                        key={model.name}
                                        data-index={i}
                                        className="absolute right-0 flex items-center gap-4"
                                        style={{
                                            top: '50%',
                                            willChange: 'transform, opacity',
                                        }}
                                    >
                                        <span className="model-name text-right font-medium whitespace-nowrap text-lg text-muted-foreground/70">
                                            {model.name}
                                        </span>
                                        <div className="flex h-10 w-10 items-center justify-center rounded-xl shadow-sm overflow-hidden flex-shrink-0 bg-zinc-200/80 text-zinc-500 dark:bg-zinc-800/80">
                                            {model.isImage ? (
                                                <img
                                                    src={model.icon as string}
                                                    alt={model.name}
                                                    className="h-6 w-6 object-contain"
                                                    loading="eager"
                                                />
                                            ) : (
                                                // @ts-ignore
                                                <model.icon className="h-5 w-5" />
                                            )}
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    </div>

                    {/* Right Side of Panel: Enterprise Branding */}
                    <div className="flex flex-col justify-center pl-12 gap-8">
                        <div className="flex flex-col gap-2">
                            <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-black text-white dark:bg-white dark:text-black mb-4">
                                <InfinityIcon className="h-8 w-8 stroke-[1.5]" />
                            </div>
                            <h2 className="text-4xl font-light tracking-tight text-black dark:text-white">
                                企业
                            </h2>
                            <p className="mt-2 text-lg text-muted-foreground/80 font-light">
                                企业级智能平台
                            </p>
                        </div>
                        <div className="flex flex-col gap-4 text-sm text-muted-foreground/80">
                            {/* ... kept icons ... */}
                            <div className="flex items-center gap-3">
                                <span className="flex h-6 w-6 items-center justify-center rounded-full bg-green-100 text-green-600 dark:bg-green-900/30 dark:text-green-400">
                                    <Sparkles className="h-3 w-3" />
                                </span>
                                业务协同 (Business)
                            </div>
                            <div className="flex items-center gap-3">
                                <span className="flex h-6 w-6 items-center justify-center rounded-full bg-blue-100 text-blue-600 dark:bg-blue-900/30 dark:text-blue-400">
                                    <Zap className="h-3 w-3" />
                                </span>
                                数据驱动 (Data)
                            </div>
                            <div className="flex items-center gap-3">
                                <span className="flex h-6 w-6 items-center justify-center rounded-full bg-purple-100 text-purple-600 dark:bg-purple-900/30 dark:text-purple-400">
                                    <Bot className="h-3 w-3" />
                                </span>
                                知识沉淀 (Knowledge)
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            {/* Right Panel - Login Form */}
            <div className="flex w-full flex-col items-center justify-center p-8 lg:w-1/2 bg-white dark:bg-black">
                <div className="w-full max-w-md space-y-8">
                    {/* Header */}
                    <div className="flex items-center gap-3 text-2xl font-semibold tracking-tight">
                        <div className="flex h-8 w-8 items-center justify-center rounded-lg text-white dark:bg-white dark:text-black">
                            <img src="/src/assets/logo/ai_logo.png" alt="" />
                        </div>
                        小驰助手
                    </div>

                    <div className="space-y-2">
                        <h1 className="text-3xl font-bold tracking-tight text-black dark:text-white">登录</h1>
                        <p className="text-sm text-muted-foreground">
                            请输入您的企业工号和密码以继续
                        </p>
                    </div>

                    {/* Form */}
                    <form className="space-y-6" onSubmit={handleSubmit}>
                        <div className="space-y-4">
                            {error && (
                                <div className="text-red-500 text-sm bg-red-50 p-3 rounded-md border border-red-100 dark:bg-red-900/20 dark:border-red-800">
                                    {error}
                                </div>
                            )}

                            <div className="space-y-2">
                                <Label htmlFor="username">账号 / 工号</Label>
                                <div className="relative">
                                    <User className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
                                    <Input
                                        id="username"
                                        placeholder="请输入工号"
                                        disabled={isLoading}
                                        className="pl-10 h-11 bg-zinc-50 border-input focus-visible:ring-black dark:bg-zinc-900"
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
                                        disabled={isLoading}
                                        className="pl-10 pr-10 h-11 bg-zinc-50 border-input focus-visible:ring-black dark:bg-zinc-900"
                                    />
                                    <Button
                                        type="button"
                                        variant="ghost"
                                        size="icon"
                                        disabled={isLoading}
                                        className="absolute right-0 top-0 h-11 w-11 text-muted-foreground hover:text-black"
                                        onClick={() => setShowPassword(!showPassword)}
                                    >
                                        {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                                    </Button>
                                </div>
                            </div>
                        </div>

                        <Button
                            disabled={isLoading}
                            type="submit"
                            className="w-full h-11 bg-black text-white hover:bg-zinc-800 dark:bg-white dark:text-black dark:hover:bg-zinc-200 text-base font-medium"
                        >
                            {isLoading ? "登录中..." : "登 录"}
                        </Button>
                    </form>

                    <div className="text-center text-xs text-muted-foreground/50 mt-auto">
                        &copy; 2025 AI 智能平台 · 版权所有
                    </div>
                </div>
            </div>
        </div>
    );
}
