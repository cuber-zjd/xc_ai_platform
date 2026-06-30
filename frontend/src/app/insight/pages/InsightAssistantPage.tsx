import { useMemo, useState } from "react";
import type { ReactNode } from "react";
import { Bot, ExternalLink, FileText, Loader2, Search, Sparkles } from "lucide-react";
import { Link } from "react-router-dom";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

import type { InsightAssistantChatResponse, InsightAssistantCitation, InsightDeepResearchResponse, InsightEvidenceMatrixItem } from "../api";
import { DemoCard, DemoTag } from "../components/DemoPrimitives";
import { InsightSelect } from "../components/InsightSelect";
import { useInsightAssistantChat, useInsightCompanies, useInsightDataSources, useInsightDeepResearch, useInsightSystemCompanies } from "../hooks";
import { PageContainer } from "../layout/PageContainer";
import { formatInsightDate } from "../utils/display";

const sentimentOptions = [
    { value: "", label: "全部情感" },
    { value: "positive", label: "正面" },
    { value: "neutral", label: "中性" },
    { value: "negative", label: "负面" },
    { value: "mixed", label: "混合" },
];

const typeOptions = [
    { value: "", label: "全部情报" },
    { value: "新品情报", label: "新品情报" },
    { value: "经营动态", label: "经营动态" },
    { value: "行业资讯", label: "行业资讯" },
    { value: "政策法规", label: "政策法规" },
    { value: "专利技术", label: "专利技术" },
    { value: "财报公告", label: "财报公告" },
];

export function InsightAssistantPage() {
    const [mode, setMode] = useState<"chat" | "research">("chat");
    const [question, setQuestion] = useState("");
    const [keyword, setKeyword] = useState("");
    const [sysCompanyId, setSysCompanyId] = useState("");
    const [companyId, setCompanyId] = useState("");
    const [dataSourceId, setDataSourceId] = useState("");
    const [projectName, setProjectName] = useState("");
    const [tag, setTag] = useState("");
    const [sentiment, setSentiment] = useState("");
    const [intelligenceType, setIntelligenceType] = useState("");
    const [dateFrom, setDateFrom] = useState("");
    const [dateTo, setDateTo] = useState("");
    const [saveReport, setSaveReport] = useState(true);
    const [chatResult, setChatResult] = useState<InsightAssistantChatResponse | null>(null);
    const [researchResult, setResearchResult] = useState<InsightDeepResearchResponse | null>(null);

    const systemCompaniesQuery = useInsightSystemCompanies();
    const companiesQuery = useInsightCompanies({ page: 1, size: 500, sys_company_id: parseOptionalNumber(sysCompanyId) ?? undefined });
    const dataSourcesQuery = useInsightDataSources({ page: 1, size: 500, status: "enabled" });
    const chatMutation = useInsightAssistantChat();
    const researchMutation = useInsightDeepResearch();
    const pending = chatMutation.isPending || researchMutation.isPending;

    const systemCompanyOptions = useMemo(
        () => [{ value: "", label: "全部所属公司" }, ...(systemCompaniesQuery.data ?? []).map((item) => ({ value: String(item.id), label: item.name }))],
        [systemCompaniesQuery.data],
    );
    const companyOptions = useMemo(
        () => [{ value: "", label: "全部企业" }, ...(companiesQuery.data?.items ?? []).map((item) => ({ value: String(item.id), label: item.short_name || item.name }))],
        [companiesQuery.data?.items],
    );
    const dataSourceOptions = useMemo(
        () => [{ value: "", label: "全部数据源" }, ...(dataSourcesQuery.data?.items ?? []).map((item) => ({ value: String(item.id), label: item.source_name }))],
        [dataSourcesQuery.data?.items],
    );

    const handleSubmit = () => {
        const trimmed = question.trim();
        if (!trimmed) {
            toast.warning("请输入研究问题");
            return;
        }
        const payload = {
            question: trimmed,
            keyword: keyword.trim() || undefined,
            sys_company_id: parseOptionalNumber(sysCompanyId) ?? undefined,
            company_id: parseOptionalNumber(companyId) ?? undefined,
            data_source_id: parseOptionalNumber(dataSourceId) ?? undefined,
            project_name: projectName.trim() || undefined,
            tag: tag.trim() || undefined,
            sentiment: sentiment || undefined,
            intelligence_type: intelligenceType || undefined,
            date_from: dateFrom || undefined,
            date_to: dateTo || undefined,
            limit: mode === "research" ? 12 : 8,
        };
        if (mode === "chat") {
            chatMutation.mutate(payload, {
                onSuccess: (result) => {
                    setChatResult(result);
                    setResearchResult(null);
                },
                onError: () => toast.error("AI 问情报失败，请稍后重试"),
            });
            return;
        }
        researchMutation.mutate({ ...payload, save_report: saveReport, report_title: `${trimmed.slice(0, 36)}${trimmed.length > 36 ? "..." : ""}` }, {
            onSuccess: (result) => {
                setResearchResult(result);
                setChatResult(null);
                toast.success(result.report_id ? "深度研究已保存为报告" : "深度研究已生成");
            },
            onError: () => toast.error("深度研究失败，请稍后重试"),
        });
    };

    return (
        <PageContainer className="flex min-h-0 flex-col gap-4">
            <div className="flex justify-end">
                <Link className="rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-black text-slate-700 hover:bg-slate-50" to="/insight/intelligence">
                    情报中心
                </Link>
            </div>

            <div className="grid min-h-0 gap-4 xl:grid-cols-[minmax(360px,0.9fr)_minmax(0,1.4fr)]">
                <DemoCard className="min-w-0 p-4 sm:p-5">
                    <div className="grid gap-4">
                        <div className="grid gap-2">
                            <span className="text-sm font-bold text-slate-700">模式</span>
                            <div className="grid gap-2 sm:grid-cols-2">
                                <ModeButton
                                    active={mode === "chat"}
                                    icon={<Bot className="size-4" />}
                                    title="AI 问情报"
                                    description="直接基于库内情报回答，并给出引用来源。"
                                    onClick={() => setMode("chat")}
                                />
                                <ModeButton
                                    active={mode === "research"}
                                    icon={<Sparkles className="size-4" />}
                                    title="深度研究"
                                    description="检索证据、提炼机会风险，并可保存为报告。"
                                    onClick={() => setMode("research")}
                                />
                            </div>
                        </div>
                        <label className="grid gap-2">
                            <span className="text-sm font-bold text-slate-700">问题</span>
                            <textarea
                                className="min-h-36 rounded-xl border border-slate-200 bg-white p-3 text-sm font-semibold leading-6 text-slate-700 outline-none focus:border-blue-300"
                                value={question}
                                onChange={(event) => setQuestion(event.target.value)}
                                placeholder={mode === "chat" ? "最近竞对在植物蛋白饮料上有什么动作？" : "大豆蛋白在茶饮新品中的机会和风险是什么？"}
                            />
                        </label>
                        <div className="grid gap-3 md:grid-cols-2">
                            <Field label="关键词" value={keyword} onChange={setKeyword} placeholder="低糖 / 功能糖" />
                            <Field label="课题" value={projectName} onChange={setProjectName} placeholder="项目名称" />
                            <InsightSelect label="所属公司" value={sysCompanyId} options={systemCompanyOptions} onChange={(value) => { setSysCompanyId(value); setCompanyId(""); }} />
                            <InsightSelect label="企业" value={companyId} options={companyOptions} onChange={setCompanyId} />
                            <InsightSelect label="情报类型" value={intelligenceType} options={typeOptions} onChange={setIntelligenceType} />
                            <InsightSelect label="情感" value={sentiment} options={sentimentOptions} onChange={setSentiment} />
                            <InsightSelect label="数据源" value={dataSourceId} options={dataSourceOptions} onChange={setDataSourceId} />
                            <Field label="标签" value={tag} onChange={setTag} placeholder="功能糖" />
                            <Field label="开始日期" value={dateFrom} onChange={setDateFrom} type="date" />
                            <Field label="结束日期" value={dateTo} onChange={setDateTo} type="date" />
                        </div>
                        {mode === "research" ? (
                            <label className="flex items-center gap-2 text-sm font-bold text-slate-700">
                                <input type="checkbox" checked={saveReport} onChange={(event) => setSaveReport(event.target.checked)} />
                                保存为报告草稿
                            </label>
                        ) : null}
                        <Button className="h-11 rounded-xl" disabled={pending || !question.trim()} onClick={handleSubmit}>
                            {pending ? <Loader2 className="size-4 animate-spin" /> : mode === "chat" ? <Bot className="size-4" /> : <Sparkles className="size-4" />}
                            {mode === "chat" ? "开始回答" : "开始研究"}
                        </Button>
                    </div>
                </DemoCard>

                <DemoCard className="min-h-[32rem] min-w-0 p-4 sm:p-5">
                    {!chatResult && !researchResult ? (
                        <div className="flex h-full min-h-80 items-center justify-center rounded-xl border border-dashed border-slate-200 bg-slate-50 text-center text-sm font-semibold text-slate-500">
                            <div>
                                <Search className="mx-auto mb-3 size-8 text-blue-500" />
                                <div>等待库内证据检索</div>
                            </div>
                        </div>
                    ) : null}
                    {chatResult ? <ChatResult result={chatResult} /> : null}
                    {researchResult ? <ResearchResult result={researchResult} /> : null}
                </DemoCard>
            </div>
        </PageContainer>
    );
}

function ModeButton({ active, icon, title, description, onClick }: { active: boolean; icon: ReactNode; title: string; description: string; onClick: () => void }) {
    return (
        <button
            type="button"
            onClick={onClick}
            className={cn(
                "rounded-xl border p-3 text-left transition",
                active ? "border-blue-200 bg-blue-50 text-blue-900 shadow-sm" : "border-slate-200 bg-white text-slate-700 hover:border-blue-200 hover:bg-blue-50/50",
            )}
        >
            <span className="flex items-center gap-2 text-sm font-black">
                {icon}
                {title}
            </span>
            <span className="mt-1 block text-xs font-semibold leading-5 text-slate-500">{description}</span>
        </button>
    );
}

function Field({ label, value, onChange, placeholder, type = "text" }: { label: string; value: string; onChange: (value: string) => void; placeholder?: string; type?: string }) {
    return (
        <label className="grid min-w-0 gap-2">
            <span className="text-sm font-bold text-slate-700">{label}</span>
            <Input className="h-11 rounded-xl border-slate-200 bg-white shadow-none" type={type} value={value} placeholder={placeholder} onChange={(event) => onChange(event.target.value)} />
        </label>
    );
}

function ChatResult({ result }: { result: InsightAssistantChatResponse }) {
    return (
        <div className="grid gap-4">
            <ResultHeader title="库内回答" generationMode={result.generation_mode} count={result.evidence_count} />
            <div className="whitespace-pre-wrap rounded-xl bg-slate-50 p-4 text-sm font-semibold leading-7 text-slate-700">{result.answer}</div>
            <CitationList citations={result.citations} />
        </div>
    );
}

function ResearchResult({ result }: { result: InsightDeepResearchResponse }) {
    return (
        <div className="grid gap-4">
            <ResultHeader title={result.title} generationMode={result.generation_mode} count={result.citations.length} />
            <div className="whitespace-pre-wrap rounded-xl bg-slate-50 p-4 text-sm font-semibold leading-7 text-slate-700">{result.conclusion}</div>
            {result.report_id ? (
                <Link className="inline-flex w-fit items-center gap-2 rounded-xl bg-blue-600 px-4 py-2 text-sm font-black text-white hover:bg-blue-700" to={`/insight/reports?report_id=${result.report_id}`}>
                    <FileText className="size-4" />
                    查看报告 #{result.report_id}
                </Link>
            ) : null}
            <ResultList title="关键发现" items={result.findings} />
            <ResultList title="机会点" items={result.opportunities} />
            <ResultList title="风险点" items={result.risks} />
            <EvidenceMatrix rows={result.evidence_matrix} />
            <ResultList title="待验证问题" items={result.follow_up_questions} />
            <CitationList citations={result.citations} />
        </div>
    );
}

function ResultHeader({ title, generationMode, count }: { title: string; generationMode?: string | null; count: number }) {
    return (
        <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="min-w-0">
                <h2 className="truncate text-xl font-black text-slate-950">{title}</h2>
                <div className="mt-1 text-xs font-bold text-slate-500">证据 {count} 条</div>
            </div>
            <DemoTag tone={generationMode === "llm" ? "green" : generationMode === "none" ? "orange" : "blue"}>{generationModeLabel(generationMode)}</DemoTag>
        </div>
    );
}

function ResultList({ title, items }: { title: string; items: string[] }) {
    if (!items.length) return null;
    return (
        <section className="rounded-xl border border-slate-200 bg-white p-4">
            <div className="font-black text-slate-900">{title}</div>
            <ul className="mt-2 list-disc space-y-2 pl-5 text-sm font-semibold leading-6 text-slate-700">
                {items.map((item, index) => <li key={`${title}-${index}`}>{item}</li>)}
            </ul>
        </section>
    );
}

function EvidenceMatrix({ rows }: { rows: InsightEvidenceMatrixItem[] }) {
    if (!rows.length) return null;
    return (
        <section className="rounded-xl border border-slate-200 bg-white p-4">
            <div className="font-black text-slate-900">证据矩阵</div>
            <div className="mt-3 space-y-3">
                {rows.map((row) => (
                    <div key={`${row.intelligence_id}-${row.title}`} className="rounded-lg bg-slate-50 p-3 text-sm leading-6">
                        <div className="font-black text-slate-800">#{row.intelligence_id} {row.title}</div>
                        <div className="mt-1 font-semibold text-slate-600">{row.evidence}</div>
                        <div className="mt-2 flex flex-wrap items-center gap-2 text-xs font-bold text-slate-500">
                            {row.publish_time ? <span>{formatInsightDate(row.publish_time)}</span> : null}
                            {row.source_url ? <ExternalSource url={row.source_url} /> : null}
                        </div>
                    </div>
                ))}
            </div>
        </section>
    );
}

function CitationList({ citations }: { citations: InsightAssistantCitation[] }) {
    if (!citations.length) return null;
    return (
        <section className="rounded-xl border border-slate-200 bg-white p-4">
            <div className="font-black text-slate-900">引用来源</div>
            <div className="mt-3 space-y-3">
                {citations.map((item) => (
                    <div key={`${item.intelligence_id}-${item.title}`} className="rounded-lg bg-slate-50 p-3 text-xs font-semibold leading-5 text-slate-600">
                        <div className="font-black text-slate-800">情报 #{item.intelligence_id}：{item.title}</div>
                        {item.summary ? <div className="mt-1 line-clamp-2">{item.summary}</div> : null}
                        <div className="mt-2 flex flex-wrap items-center gap-2">
                            {item.publish_time ? <span>{formatInsightDate(item.publish_time)}</span> : null}
                            <Link className="text-blue-600 hover:underline" to={`/insight/intelligence/${item.intelligence_id}`}>查看情报</Link>
                            {item.source_url ? <ExternalSource url={item.source_url} /> : null}
                        </div>
                    </div>
                ))}
            </div>
        </section>
    );
}

function ExternalSource({ url }: { url: string }) {
    return (
        <a className="inline-flex items-center gap-1 text-blue-600 hover:underline" href={url} target="_blank" rel="noreferrer">
            来源
            <ExternalLink className="size-3" />
        </a>
    );
}

function generationModeLabel(mode?: string | null) {
    if (mode === "llm") return "AI 生成";
    if (mode === "rules") return "证据草稿";
    if (mode === "none") return "无证据";
    return "库内证据";
}

function parseOptionalNumber(value: string) {
    if (!value) return undefined;
    const numberValue = Number(value);
    return Number.isFinite(numberValue) ? numberValue : undefined;
}
