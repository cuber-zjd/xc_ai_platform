import { useState } from 'react';
import { MessageSquarePlus, SendHorizonal, Sparkles } from 'lucide-react';

import { cn } from '@/lib/utils';

const quickPrompts = [
    '帮我总结今天的任务重点',
    '起草一份项目周报',
    '分析上传表格里的异常数据',
    '帮我生成一份 FineReport 报表需求',
];

export default function ChatHomePage() {
    const [inputValue, setInputValue] = useState('');

    return (
        <div className="app-page flex min-h-full items-center">
            <section className="mx-auto w-full max-w-5xl">
                <div className="app-page-header overflow-hidden">
                    <div className="grid gap-6 lg:grid-cols-[1.2fr_0.8fr]">
                        <div className="flex flex-col justify-between">
                            <div>
                                <div className="app-kicker">智能对话中心</div>
                                <h2 className="mt-4 text-[40px] font-black tracking-[-0.05em] text-[#24233b]">
                                    在一个统一的输入框里开始今天的工作
                                </h2>
                                <p className="mt-3 max-w-2xl app-subtle-text">
                                    这套首页也已经切换到新的工作台风格。你可以从这里发起问答、写作、数据分析或报表任务，后续再进入具体应用继续处理。
                                </p>
                            </div>

                            <div className="mt-8 rounded-[30px] border border-white/80 bg-white/78 p-3 shadow-[0_18px_36px_rgba(102,99,166,0.06)]">
                                <div className="flex items-center gap-3 rounded-[24px] bg-[#11131d] px-4 py-4 text-white shadow-[inset_0_1px_0_rgba(255,255,255,0.08)]">
                                    <Sparkles className="h-5 w-5 text-[#b7a5ff]" />
                                    <input
                                        value={inputValue}
                                        onChange={(event) => setInputValue(event.target.value)}
                                        placeholder="输入你的问题、任务或创作请求"
                                        className="h-8 flex-1 bg-transparent text-[15px] outline-none placeholder:text-white/45"
                                    />
                                    <button
                                        type="button"
                                        className={cn(
                                            'flex h-11 w-11 items-center justify-center rounded-full transition-all duration-300',
                                            inputValue.trim()
                                                ? 'bg-linear-to-r from-[#6e5df7] to-[#b48fff] text-white shadow-[0_14px_32px_rgba(110,93,247,0.34)]'
                                                : 'bg-white/8 text-white/45',
                                        )}
                                    >
                                        <SendHorizonal className="h-4.5 w-4.5" />
                                    </button>
                                </div>
                            </div>
                        </div>

                        <div className="app-panel flex flex-col justify-between rounded-[32px] p-5">
                            <div>
                                <div className="flex items-center gap-2 text-sm font-black text-[#2c2a43]">
                                    <MessageSquarePlus className="h-4 w-4 text-[#6d5df6]" />
                                    快捷开始
                                </div>
                                <p className="mt-2 text-sm leading-6 text-[#7e8196]">
                                    选择一个常见场景，快速进入新的对话上下文。
                                </p>
                            </div>

                            <div className="mt-5 space-y-3">
                                {quickPrompts.map((prompt) => (
                                    <button
                                        key={prompt}
                                        type="button"
                                        className="w-full rounded-[22px] border border-white/80 bg-white/82 px-4 py-4 text-left text-sm font-semibold text-[#43445a] shadow-[0_10px_24px_rgba(102,99,166,0.05)] transition-all duration-300 hover:-translate-y-0.5 hover:text-[#24233b]"
                                        onClick={() => setInputValue(prompt)}
                                    >
                                        {prompt}
                                    </button>
                                ))}
                            </div>
                        </div>
                    </div>
                </div>
            </section>
        </div>
    );
}
