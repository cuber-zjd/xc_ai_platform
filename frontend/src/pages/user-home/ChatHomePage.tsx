import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowUp, Bot, FileSpreadsheet, MessageSquareText, Plus, Search, Sparkles } from 'lucide-react';

import { cn } from '@/lib/utils';

const quickPrompts = [
    '帮我总结今天的任务重点',
    '起草一份项目周报',
    '分析上传表格里的异常数据',
    '帮我生成一份 FineReport 报表需求',
];

const quickEntrances = [
    {
        label: '探索智能体',
        description: '从工作台选择合同审查、SAP 助手、报表生成等应用',
        icon: Search,
        path: '/workspace',
    },
    {
        label: '报表生成',
        description: '按步骤生成 SQL、ReportDSL 和预览',
        icon: FileSpreadsheet,
        path: '/fr-ai-reports',
    },
    {
        label: 'SAP 助手',
        description: '围绕 SAP 源码、DDIC 和证据链展开调查',
        icon: Bot,
        path: '/sap-assistant',
    },
];

export default function ChatHomePage() {
    const [inputValue, setInputValue] = useState('');
    const navigate = useNavigate();

    return (
        <div className="flex min-h-full flex-col bg-white">
            <main className="flex flex-1 items-center justify-center px-5 py-12">
                <section className="w-full max-w-3xl text-center">
                    <div className="mx-auto mb-6 flex h-12 w-12 items-center justify-center rounded-2xl border border-[#e5e5e5] bg-white shadow-sm">
                        <Sparkles className="h-5 w-5 text-[#171717]" />
                    </div>
                    <h1 className="text-3xl font-semibold tracking-tight text-[#171717] md:text-4xl">你在忙什么？</h1>

                    <div className="mx-auto mt-9 w-full rounded-[28px] border border-[#dddddd] bg-white p-3 text-left shadow-[0_12px_40px_rgba(0,0,0,0.08)]">
                        <div className="flex items-center gap-3">
                            <button
                                type="button"
                                className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-[#6f6f6f] transition hover:bg-[#f4f4f4] hover:text-[#171717]"
                                aria-label="添加内容"
                            >
                                <Plus className="h-5 w-5" />
                            </button>
                            <input
                                value={inputValue}
                                onChange={(event) => setInputValue(event.target.value)}
                                placeholder="有问题，尽管问"
                                className="h-10 min-w-0 flex-1 bg-transparent text-[15px] text-[#171717] outline-none placeholder:text-[#8a8a8a]"
                            />
                            <button
                                type="button"
                                className={cn(
                                    'flex h-9 w-9 shrink-0 items-center justify-center rounded-full transition',
                                    inputValue.trim()
                                        ? 'bg-blue-600 text-white hover:bg-blue-700'
                                        : 'bg-[#f1f1f1] text-[#b5b5b5]',
                                )}
                                aria-label="发送"
                            >
                                <ArrowUp className="h-4 w-4" />
                            </button>
                        </div>
                    </div>

                    <div className="mt-5 flex flex-wrap justify-center gap-2">
                        {quickPrompts.map((prompt) => (
                            <button
                                key={prompt}
                                type="button"
                                onClick={() => setInputValue(prompt)}
                                className="rounded-full border border-[#e5e5e5] bg-white px-4 py-2 text-sm text-[#4a4a4a] transition hover:bg-[#f4f4f4] hover:text-[#171717]"
                            >
                                {prompt}
                            </button>
                        ))}
                    </div>
                </section>
            </main>

            <section className="mx-auto grid w-full max-w-5xl gap-3 px-5 pb-10 md:grid-cols-3">
                {quickEntrances.map((item) => (
                    <button
                        key={item.path}
                        type="button"
                        onClick={() => navigate(item.path)}
                        className="group rounded-2xl border border-[#e7e7e7] bg-white p-4 text-left transition hover:bg-[#fafafa]"
                    >
                        <div className="flex items-start gap-3">
                            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[#f4f4f4] text-[#333333]">
                                <item.icon className="h-5 w-5" />
                            </div>
                            <div className="min-w-0">
                                <div className="flex items-center gap-2 text-sm font-semibold text-[#171717]">
                                    {item.label}
                                    <MessageSquareText className="h-3.5 w-3.5 text-[#b5b5b5] transition group-hover:text-[#6f6f6f]" />
                                </div>
                                <p className="mt-1 line-clamp-2 text-sm leading-6 text-[#6f6f6f]">{item.description}</p>
                            </div>
                        </div>
                    </button>
                ))}
            </section>
        </div>
    );
}
