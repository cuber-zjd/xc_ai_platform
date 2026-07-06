import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { Bot, ExternalLink, FileText, Loader2, Send, Sparkles, X } from "lucide-react";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

import type { InsightAssistantChatResponse, InsightAssistantCitation, InsightDeepResearchResponse } from "../api";
import { useInsightAssistantChat, useInsightDeepResearch } from "../hooks";
import { formatInsightDate } from "../utils/display";

type AssistantMode = "chat" | "research";

const quickQuestions = [
    "近期奶茶客户有哪些值得销售关注的变化？",
    "植物蛋白和蛋白粉有哪些机会和风险？",
    "最近有哪些政策或舆情需要关注？",
];

export function InsightFloatingAssistant() {
    const location = useLocation();
    const navigate = useNavigate();
    const [searchParams, setSearchParams] = useSearchParams();
    const [open, setOpen] = useState(false);
    const [mode, setMode] = useState<AssistantMode>("chat");
    const [question, setQuestion] = useState("");
    const [datePreset, setDatePreset] = useState<"7" | "15" | "30" | "all">("15");
    const [chatResult, setChatResult] = useState<InsightAssistantChatResponse | null>(null);
    const [researchResult, setResearchResult] = useState<InsightDeepResearchResponse | null>(null);
    const chatMutation = useInsightAssistantChat();
    const researchMutation = useInsightDeepResearch();
    const pending = chatMutation.isPending || researchMutation.isPending;

    useEffect(() => {
        if (searchParams.get("assistant") === "open" || location.pathname.endsWith("/assistant")) setOpen(true);
    }, [location.pathname, searchParams]);

    const dateRange = useMemo(() => buildDateRange(datePreset), [datePreset]);

    const handleOpen = () => {
        setOpen(true);
        const next = new URLSearchParams(searchParams);
        next.set("assistant", "open");
        setSearchParams(next, { replace: true });
    };

    const handleClose = () => {
        setOpen(false);
        if (location.pathname.endsWith("/assistant")) {
            navigate("/insight", { replace: true });
            return;
        }
        const next = new URLSearchParams(searchParams);
        next.delete("assistant");
        setSearchParams(next, { replace: true });
    };

    const handleSubmit = () => {
        const trimmed = question.trim();
        if (!trimmed) {
            toast.warning("先告诉我你想研究什么");
            return;
        }
        const payload = {
            question: trimmed,
            keyword: trimmed,
            date_from: dateRange.date_from,
            date_to: dateRange.date_to,
            limit: mode === "research" ? 12 : 8,
        };
        if (mode === "research") {
            researchMutation.mutate(
                {
                    ...payload,
                    save_report: false,
                    report_title: `${trimmed.slice(0, 36)}${trimmed.length > 36 ? "..." : ""}`,
                },
                {
                    onSuccess: (result) => {
                        setResearchResult(result);
                        setChatResult(null);
                    },
                    onError: () => toast.error("研究失败，请稍后再试"),
                },
            );
            return;
        }
        chatMutation.mutate(payload, {
            onSuccess: (result) => {
                setChatResult(result);
                setResearchResult(null);
            },
            onError: () => toast.error("回答失败，请稍后再试"),
        });
    };

    return (
        <>
            <Button
                type="button"
                className={cn(
                    "fixed bottom-20 right-4 z-40 size-14 rounded-2xl bg-blue-600 p-0 text-white shadow-[0_18px_36px_rgba(29,116,255,0.28)] transition hover:bg-blue-700 lg:bottom-6 lg:right-6",
                    open && "scale-95 opacity-0 pointer-events-none",
                )}
                aria-label="打开 AI 助手"
                onClick={handleOpen}
            >
                <Bot className="size-6" />
            </Button>

            {open ? (
                <aside className="fixed bottom-20 right-3 z-50 flex h-[min(680px,calc(100vh-6rem))] w-[min(420px,calc(100vw-1.5rem))] flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-[0_24px_70px_rgba(15,23,42,0.22)] lg:bottom-6 lg:right-6">
                    <div className="flex shrink-0 items-center justify-between border-b border-slate-100 px-4 py-3">
                        <div className="flex min-w-0 items-center gap-3">
                            <span className="grid size-10 shrink-0 place-items-center rounded-2xl bg-blue-600 text-white">
                                <Bot className="size-5" />
                            </span>
                            <div className="min-w-0">
                                <div className="truncate text-sm font-black text-slate-950">AI 助手</div>
                                <div className="truncate text-xs font-semibold text-slate-500">随时查情报、做研究</div>
                            </div>
                        </div>
                        <Button type="button" variant="ghost" size="icon" className="size-9 rounded-xl" onClick={handleClose}>
                            <X className="size-4" />
                        </Button>
                    </div>

                    <div className="min-h-0 flex-1 overflow-y-auto p-4">
                        <div className="grid grid-cols-2 gap-2">
                            <ModeButton active={mode === "chat"} icon={<Bot className="size-4" />} label="直接问" onClick={() => setMode("chat")} />
                            <ModeButton active={mode === "research"} icon={<Sparkles className="size-4" />} label="深度研究" onClick={() => setMode("research")} />
                        </div>

                        <div className="mt-3 grid grid-cols-4 gap-2">
                            {[
                                ["7", "近 7 天"],
                                ["15", "近 15 天"],
                                ["30", "近 30 天"],
                                ["all", "不限"],
                            ].map(([value, label]) => (
                                <button
                                    key={value}
                                    type="button"
                                    className={cn(
                                        "h-9 rounded-xl border text-xs font-black transition",
                                        datePreset === value ? "border-blue-200 bg-blue-50 text-blue-700" : "border-slate-200 bg-white text-slate-500 hover:bg-slate-50",
                                    )}
                                    onClick={() => setDatePreset(value as typeof datePreset)}
                                >
                                    {label}
                                </button>
                            ))}
                        </div>

                        <div className="mt-3 rounded-2xl border border-slate-200 bg-slate-50 p-3">
                            <textarea
                                value={question}
                                onChange={(event) => setQuestion(event.target.value)}
                                className="h-28 w-full resize-none rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-semibold leading-6 text-slate-700 outline-none focus:border-blue-300 focus:ring-4 focus:ring-blue-100"
                                placeholder={mode === "research" ? "例如：请分析近期蛋白客户值得关注的机会、风险和后续建议" : "例如：最近奶茶客户有什么新品和需求变化？"}
                            />
                            <div className="mt-2 flex flex-wrap gap-2">
                                {quickQuestions.map((item) => (
                                    <button
                                        key={item}
                                        type="button"
                                        className="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-bold text-slate-600 hover:border-blue-200 hover:bg-blue-50 hover:text-blue-700"
                                        onClick={() => setQuestion(item)}
                                    >
                                        {item}
                                    </button>
                                ))}
                            </div>
                            <Button type="button" className="mt-3 h-10 w-full rounded-xl" disabled={pending || !question.trim()} onClick={handleSubmit}>
                                {pending ? <Loader2 className="size-4 animate-spin" /> : <Send className="size-4" />}
                                {mode === "research" ? "开始研究" : "发送"}
                            </Button>
                        </div>

                        <div className="mt-4">
                            {pending ? (
                                <div className="rounded-2xl border border-blue-100 bg-blue-50 p-4 text-sm font-semibold text-blue-800">
                                    正在从你有权限查看的情报中查找资料...
                                </div>
                            ) : null}
                            {!pending && !chatResult && !researchResult ? (
                                <div className="rounded-2xl border border-dashed border-slate-200 bg-white p-5 text-center text-sm font-semibold text-slate-500">
                                    这里会显示回答、结论和引用来源。
                                </div>
                            ) : null}
                            {chatResult ? <ChatResult result={chatResult} /> : null}
                            {researchResult ? <ResearchResult result={researchResult} /> : null}
                        </div>
                    </div>
                </aside>
            ) : null}
        </>
    );
}

function ModeButton({ active, icon, label, onClick }: { active: boolean; icon: ReactNode; label: string; onClick: () => void }) {
    return (
        <Button
            type="button"
            variant="outline"
            className={cn("h-10 rounded-xl bg-white text-sm font-black", active ? "border-blue-200 bg-blue-50 text-blue-700" : "border-slate-200 text-slate-600")}
            onClick={onClick}
        >
            {icon}
            {label}
        </Button>
    );
}

function ChatResult({ result }: { result: InsightAssistantChatResponse }) {
    return (
        <div className="space-y-3">
            <div className="rounded-2xl bg-slate-50 p-4 text-sm font-semibold leading-7 text-slate-700">
                {result.no_evidence ? "暂时没有找到足够匹配的资料。" : result.answer}
            </div>
            <CitationList citations={result.citations} />
        </div>
    );
}

function ResearchResult({ result }: { result: InsightDeepResearchResponse }) {
    return (
        <div className="space-y-3">
            <div className="rounded-2xl bg-slate-50 p-4">
                <div className="text-sm font-black text-slate-950">{result.title}</div>
                <div className="mt-2 whitespace-pre-wrap text-sm font-semibold leading-7 text-slate-700">{result.conclusion}</div>
            </div>
            <ResultSection title="关键发现" items={result.findings} />
            <ResultSection title="机会" items={result.opportunities} />
            <ResultSection title="风险" items={result.risks} />
            {result.report_id ? (
                <Link className="inline-flex items-center gap-2 rounded-xl bg-blue-600 px-3 py-2 text-sm font-black text-white hover:bg-blue-700" to={`/insight/reports?report_id=${result.report_id}`}>
                    <FileText className="size-4" />
                    查看报告
                </Link>
            ) : null}
            <CitationList citations={result.citations} />
        </div>
    );
}

function ResultSection({ title, items }: { title: string; items: string[] }) {
    if (!items.length) return null;
    return (
        <section className="rounded-2xl border border-slate-200 bg-white p-3">
            <div className="text-sm font-black text-slate-900">{title}</div>
            <ul className="mt-2 space-y-2 text-sm font-semibold leading-6 text-slate-700">
                {items.slice(0, 5).map((item, index) => (
                    <li key={`${title}-${index}`} className="rounded-xl bg-slate-50 px-3 py-2">
                        {item}
                    </li>
                ))}
            </ul>
        </section>
    );
}

function CitationList({ citations }: { citations: InsightAssistantCitation[] }) {
    if (!citations.length) return null;
    return (
        <section className="rounded-2xl border border-slate-200 bg-white p-3">
            <div className="text-sm font-black text-slate-900">引用来源</div>
            <div className="mt-2 space-y-2">
                {citations.slice(0, 6).map((item) => (
                    <div key={`${item.intelligence_id}-${item.title}`} className="rounded-xl bg-slate-50 p-3 text-xs font-semibold leading-5 text-slate-600">
                        <div className="font-black text-slate-800">{item.title}</div>
                        {item.summary ? <div className="mt-1 line-clamp-2">{item.summary}</div> : null}
                        <div className="mt-2 flex flex-wrap items-center gap-2">
                            {item.publish_time ? <span>{formatInsightDate(item.publish_time)}</span> : null}
                            <Link className="text-blue-600 hover:underline" to={`/insight/intelligence/${item.intelligence_id}`}>查看</Link>
                            {item.source_url ? (
                                <a className="inline-flex items-center gap-1 text-blue-600 hover:underline" href={item.source_url} target="_blank" rel="noreferrer">
                                    原文
                                    <ExternalLink className="size-3" />
                                </a>
                            ) : null}
                        </div>
                    </div>
                ))}
            </div>
        </section>
    );
}

function buildDateRange(preset: "7" | "15" | "30" | "all") {
    if (preset === "all") return {};
    const end = new Date();
    const start = new Date();
    start.setDate(end.getDate() - Number(preset));
    return {
        date_from: toDateInputValue(start),
        date_to: toDateInputValue(end),
    };
}

function toDateInputValue(date: Date) {
    const year = date.getFullYear();
    const month = `${date.getMonth() + 1}`.padStart(2, "0");
    const day = `${date.getDate()}`.padStart(2, "0");
    return `${year}-${month}-${day}`;
}
