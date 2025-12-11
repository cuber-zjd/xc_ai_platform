import { useEffect, useState } from "react";
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
import { cn } from "@/lib/utils";

// Import Model Logos
import GPT5Logo from "@/assets/models_logo/GPT5.1.svg";
import GeminiLogo from "@/assets/models_logo/Gemini 3.0 Pro.svg";
import ClaudeLogo from "@/assets/models_logo/Claude 4.1 Thinking.svg";
import DeepSeekLogo from "@/assets/models_logo/DeepSeek-R1.ico";
import LlamaLogo from "@/assets/models_logo/Llama 4.ico";
import GrokLogo from "@/assets/models_logo/Grok-4.1.png";
import MistralLogo from "@/assets/models_logo/Mistral Large.svg";
import QwenLogo from "@/assets/models_logo/Qwen-3.0 MAX.png";

export default function LoginPage() {
    const [showPassword, setShowPassword] = useState(false);
    const [scrollOffset, setScrollOffset] = useState(0);

    const models = [
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

    useEffect(() => {
        let animationFrameId: number;
        let lastTime = performance.now();
        const speed = 0.05; // Pixels per ms

        const animate = (time: number) => {
            const delta = time - lastTime;
            lastTime = time;

            setScrollOffset((prev) => (prev + speed * delta));
            animationFrameId = requestAnimationFrame(animate);
        };

        animationFrameId = requestAnimationFrame(animate);
        return () => cancelAnimationFrame(animationFrameId);
    }, []);

    return (
        <div className="flex h-screen w-full overflow-hidden bg-background font-sans text-foreground">
            {/* Left Panel - Feature Showcase */}
            <div className="relative hidden w-[90%] border-r border-border bg-zinc-50/50 p-10 lg:flex dark:bg-zinc-900 overflow-hidden">
                {/* Background Pattern */}
                <div className="absolute inset-0 z-0 bg-[radial-gradient(#e5e7eb_1px,transparent_1px)] [background-size:16px_16px] opacity-50 dark:bg-[radial-gradient(#3f3f46_1px,transparent_1px)]" />

                <div className="relative z-10 grid w-full h-full grid-cols-2 gap-4">

                    {/* Left Side of Panel: Model Carousel */}
                    <div className="flex flex-col items-end justify-center pr-8 border-r border-zinc-200/50 dark:border-zinc-800/50 relative overflow-hidden h-full">
                        {/* Fade masks */}
                        <div className="absolute top-0 left-0 right-0 h-32 bg-gradient-to-b from-zinc-50 to-transparent z-20 dark:from-zinc-900 pointer-events-none" />
                        <div className="absolute bottom-0 left-0 right-0 h-32 bg-gradient-to-t from-zinc-50 to-transparent z-20 dark:from-zinc-900 pointer-events-none" />

                        <div className="absolute inset-0 flex items-center justify-end pr-8">
                            {/* Container for scrolling items */}
                            <div className="relative w-full h-[400px]"> {/* Fixed height container for calculation */}
                                {models.map((model, i) => {
                                    // Total height of the virtual scroll area
                                    const itemHeight = 80; // Distance between items
                                    const totalHeight = models.length * itemHeight;

                                    // Calculate vertical position based on scrollY
                                    // We want them to loop endlessly.
                                    // Standardize y to be within [0, totalHeight)
                                    // Render relative to Center.
                                    // position = ((i * itemHeight - scrollOffset + totalHeight/2) % totalHeight/2)
                                    // This gives a value between -totalHeight/2 and +totalHeight/2.

                                    let relativeY = ((i * itemHeight - scrollOffset + totalHeight / 2) % totalHeight);
                                    if (relativeY < 0) relativeY += totalHeight;
                                    relativeY -= totalHeight / 2;

                                    // Now relativeY is approx -400 to +400.
                                    // Visible area is approx -200 to +200.

                                    const distanceFromCenter = Math.abs(relativeY);

                                    // Opacity/Scale logic
                                    const opacity = Math.max(0.15, 1 - (distanceFromCenter / 200));
                                    const scale = Math.max(0.8, 1.1 - (distanceFromCenter / 500));
                                    const blur = Math.max(0, (distanceFromCenter / 40));

                                    // Don't render if too far to save DOM? CSS handles it well enough usually.
                                    if (distanceFromCenter > 250) return null;

                                    return (
                                        <div
                                            key={model.name}
                                            className="absolute right-0 flex items-center gap-4 transition-transform will-change-transform"
                                            style={{
                                                top: '50%', // Absolute center base
                                                transform: `translateY(${relativeY}px) translateY(-50%) translateZ(0) scale(${scale})`, // -50% to center the item itself
                                                opacity: opacity,
                                                filter: `blur(${blur}px)`,
                                                zIndex: 10 - Math.floor(distanceFromCenter / 10),
                                            }}
                                        >
                                            <span className={cn(
                                                "text-right font-medium transition-colors duration-300",
                                                distanceFromCenter < 40 ? "text-2xl text-black dark:text-white" : "text-lg text-muted-foreground"
                                            )}>
                                                {model.name}
                                            </span>
                                            <div className={cn(
                                                "flex h-10 w-10 items-center justify-center rounded-xl transition-colors duration-300 shadow-sm overflow-hidden",
                                                distanceFromCenter < 40 ? "bg-black text-white shadow-xl dark:bg-white dark:text-black" : "bg-zinc-200 text-zinc-500 dark:bg-zinc-800"
                                            )}>
                                                {model.isImage ? (
                                                    <img
                                                        src={model.icon as string}
                                                        alt={model.name}
                                                        className="h-6 w-6 object-contain"
                                                    />
                                                ) : (
                                                    // @ts-ignore
                                                    <model.icon className="h-5 w-5" />
                                                )}
                                            </div>
                                        </div>
                                    );
                                })}
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
                                Enterprise
                            </p>
                        </div>

                        <div className="flex flex-col gap-4 text-sm text-muted-foreground/80">
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
                    {/* Content below remains largely same but ensures spacing */}
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
                                        className="pl-10 pr-10 h-11 bg-zinc-50 border-input focus-visible:ring-black dark:bg-zinc-900"
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
                            </div>
                        </div>

                        <Button className="w-full h-11 bg-black text-white hover:bg-zinc-800 dark:bg-white dark:text-black dark:hover:bg-zinc-200 text-base font-medium">
                            登 录
                        </Button>
                    </form>

                    <div className="text-center text-xs text-muted-foreground/50 mt-auto">
                        &copy; 2025 AI Platform. All rights reserved.
                    </div>
                </div>
            </div>
        </div>
    );
}
