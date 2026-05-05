import { useRef, useState } from 'react';
import {
    AlertCircle,
    BarChart3,
    Bot,
    CheckCircle2,
    Database,
    FileSpreadsheet,
    Globe2,
    Loader2,
    MessagesSquare,
    Play,
    Rocket,
    Send,
    ShieldCheck,
    Sparkles,
    UploadCloud,
} from 'lucide-react';
import { toast } from 'sonner';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { ScrollArea } from '@/components/ui/scroll-area';
import { cn } from '@/lib/utils';
import {
    useFrAiReportTask,
    useGenerateFrAiReport,
    usePublishFrAiReportTask,
    useValidateFrAiReportTask,
} from '@/features/fr-ai-report/hooks/useFrAiReport';
import type { ExcelFieldAnalysis, ReportTaskRead } from '@/features/fr-ai-report/types';

interface ChatMessage {
    id: string;
    role: 'user' | 'assistant';
    content: string;
}

const STARTER_MESSAGES: ChatMessage[] = [
    {
        id: 'welcome',
        role: 'assistant',
        content:
            '把业务 Excel 拖进来，或者直接描述你想看的表格报表。我会先生成结构化 ReportDSL，再由程序确定性生成 FineReport CPT。当前阶段只支持明细表、分组表、交叉透视表，不做柱状图、折线图、饼图。',
    },
];

const REPORT_TYPE_LABELS: Record<string, string> = {
    detail_table: '明细表',
    group_table: '分组汇总表',
    pivot_table: '交叉透视表',
};

const ROLE_LABELS: Record<string, string> = {
    dimension: '维度',
    measure: '指标',
    date: '日期',
    text: '文本',
};

const STATUS_LABELS: Record<string, string> = {
    generating: '生成中',
    generated: '已生成',
    validating: '校验中',
    validated: '已校验',
    validation_failed: '校验失败',
    published: '已发布',
    failed: '失败',
};

export function FrAiReportChatPage() {
    const fileInputRef = useRef<HTMLInputElement>(null);
    const [requirement, setRequirement] = useState(
        '按年份、日期、周次生成交叉周报，列展示各区域库存或销量指标，支持开始日期和结束日期参数。',
    );
    const [reportName, setReportName] = useState('区域周报统计表');
    const [sourceTableName, setSourceTableName] = useState('');
    const [selectedFile, setSelectedFile] = useState<File | null>(null);
    const [taskId, setTaskId] = useState<string | null>(null);
    const [messages, setMessages] = useState<ChatMessage[]>(STARTER_MESSAGES);

    const generateMutation = useGenerateFrAiReport();
    const validateMutation = useValidateFrAiReportTask();
    const publishMutation = usePublishFrAiReportTask();
    const taskQuery = useFrAiReportTask(taskId);
    const task = taskQuery.data;

    const previewUrl = task?.previewUrl || generateMutation.data?.previewUrl;
    const reportDsl = task?.reportDsl;
    const primarySheet =
        task?.excelAnalysis?.sheets?.find(
            (sheet) => sheet.sheetName === task.excelAnalysis?.primarySheet,
        ) || task?.excelAnalysis?.sheets?.[0];
    const datasetSql = reportDsl?.datasets?.[0]?.sql;
    const issueList = [
        ...(task?.errors ?? generateMutation.data?.errors ?? []),
        ...(task?.warnings ?? generateMutation.data?.warnings ?? []),
    ];

    const handleGenerate = () => {
        if (!requirement.trim() && !selectedFile && !sourceTableName.trim()) {
            toast.error('请先输入报表需求、数据表名，或者上传一个业务 Excel。');
            return;
        }

        const userContent = [
            requirement.trim() || '根据上传的 Excel 自动生成表格报表。',
            selectedFile ? `已上传：${selectedFile.name}` : '',
            sourceTableName.trim() ? `数据表：${sourceTableName.trim()}` : '',
        ]
            .filter(Boolean)
            .join('\n');

        setMessages((current) => [
            ...current,
            { id: crypto.randomUUID(), role: 'user', content: userContent },
            {
                id: crypto.randomUUID(),
                role: 'assistant',
                content:
                    '收到。我会优先按表格报表来设计，只生成 ReportDSL，然后交给确定性程序生成 CPT 并写入 staging。',
            },
        ]);

        generateMutation.mutate(
            {
                requirement,
                reportName,
                sourceTableName,
                file: selectedFile,
            },
            {
                onSuccess: (data) => {
                    setTaskId(data.taskId);
                    setMessages((current) => [
                        ...current,
                        {
                            id: crypto.randomUUID(),
                            role: 'assistant',
                            content: `报表任务已生成：${data.reportName}。当前状态：${STATUS_LABELS[data.status] ?? data.status}。右侧可以查看 DSL 和预览。`,
                        },
                    ]);
                    toast.success('报表生成任务已完成');
                },
                onError: () => {
                    setMessages((current) => [
                        ...current,
                        {
                            id: crypto.randomUUID(),
                            role: 'assistant',
                            content: '生成失败了。请检查登录状态、文件格式或后端 FineReport 模块日志。',
                        },
                    ]);
                    toast.error('报表生成失败');
                },
            },
        );
    };

    const handleValidate = () => {
        if (!taskId) {
            return;
        }
        validateMutation.mutate(taskId, {
            onSuccess: (result) => {
                toast[result.errors.length ? 'warning' : 'success'](
                    result.errors.length ? '预览校验发现问题' : '预览校验通过',
                );
            },
        });
    };

    const handlePublish = () => {
        if (!taskId) {
            return;
        }
        publishMutation.mutate(taskId, {
            onSuccess: () => {
                toast.success('已标记发布，文件仍保留在 staging 区');
            },
        });
    };

    const isGenerating = generateMutation.isPending;
    const isValidating = validateMutation.isPending;
    const isPublishing = publishMutation.isPending;

    return (
        <div className="h-full min-h-[calc(100vh-3rem)] p-3 text-zinc-900">
            <div className="grid h-full gap-4 xl:grid-cols-[430px_minmax(0,1fr)]">
                <section className="flex min-h-0 flex-col overflow-hidden rounded-[34px] border border-white/70 bg-white/55 shadow-[0_20px_70px_rgba(15,23,42,0.08)] backdrop-blur-3xl">
                    <div className="border-b border-zinc-200/70 p-5">
                        <div className="flex items-center gap-3">
                            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-zinc-950 text-white shadow-lg">
                                <MessagesSquare className="h-5 w-5" />
                            </div>
                            <div>
                                <div className="flex items-center gap-2">
                                    <h1 className="text-xl font-black tracking-tight">报表生成对话</h1>
                                    <Badge className="rounded-full bg-zinc-950 text-white hover:bg-zinc-950">
                                        FineReport
                                    </Badge>
                                </div>
                                <p className="mt-1 text-xs font-medium text-zinc-500">
                                    当前阶段仅支持表格类报表：明细、分组、交叉透视
                                </p>
                            </div>
                        </div>
                    </div>

                    <ScrollArea className="min-h-0 flex-1 px-5 py-4">
                        <div className="space-y-4">
                            {messages.map((message) => (
                                <div
                                    key={message.id}
                                    className={cn(
                                        'flex gap-3',
                                        message.role === 'user' ? 'justify-end' : 'justify-start',
                                    )}
                                >
                                    {message.role === 'assistant' && (
                                        <div className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-2xl bg-zinc-950 text-white">
                                            <Bot className="h-4 w-4" />
                                        </div>
                                    )}
                                    <div
                                        className={cn(
                                            'max-w-[82%] whitespace-pre-wrap rounded-[22px] px-4 py-3 text-sm leading-6 shadow-sm',
                                            message.role === 'user'
                                                ? 'bg-zinc-950 text-white'
                                                : 'border border-white/70 bg-white/75 text-zinc-700',
                                        )}
                                    >
                                        {message.content}
                                    </div>
                                </div>
                            ))}
                        </div>
                    </ScrollArea>

                    <div className="space-y-3 border-t border-zinc-200/70 bg-white/50 p-5">
                        <div className="grid gap-3 sm:grid-cols-[1fr_150px]">
                            <Input
                                value={reportName}
                                onChange={(event) => setReportName(event.target.value)}
                                placeholder="报表名称"
                                className="h-11 rounded-2xl border-white/80 bg-white/80 text-sm font-semibold shadow-inner"
                            />
                            <input
                                ref={fileInputRef}
                                type="file"
                                accept=".xlsx,.xls"
                                className="hidden"
                                onChange={(event) => setSelectedFile(event.target.files?.[0] ?? null)}
                            />
                            <Button
                                type="button"
                                variant="outline"
                                className="h-11 rounded-2xl border-white/80 bg-white/70 text-zinc-700 hover:bg-white"
                                onClick={() => fileInputRef.current?.click()}
                            >
                                <UploadCloud className="mr-2 h-4 w-4" />
                                上传 Excel
                            </Button>
                        </div>
                        <Input
                            value={sourceTableName}
                            onChange={(event) => setSourceTableName(event.target.value)}
                            placeholder="数据表名，支持一行一个或逗号分隔；例如 dbo.orders, dbo.customers。多表请在需求中说明关联关系"
                            className="h-11 rounded-2xl border-white/80 bg-white/80 text-sm font-semibold shadow-inner"
                        />

                        {selectedFile && (
                            <div className="flex items-center justify-between rounded-2xl border border-emerald-200/70 bg-emerald-50/70 px-3 py-2 text-xs text-emerald-800">
                                <span className="flex items-center gap-2 font-semibold">
                                    <FileSpreadsheet className="h-4 w-4" />
                                    {selectedFile.name}
                                </span>
                                <button
                                    className="font-bold text-emerald-900/70 hover:text-emerald-950"
                                    onClick={() => setSelectedFile(null)}
                                >
                                    移除
                                </button>
                            </div>
                        )}

                        <div className="rounded-[26px] border border-white/80 bg-white/80 p-2 shadow-inner">
                            <textarea
                                value={requirement}
                                onChange={(event) => setRequirement(event.target.value)}
                                placeholder="描述你要生成的表格报表，例如：按区域、年份、周次生成交叉周报，列展示各区域指标，支持开始日期和结束日期参数。"
                                className="min-h-28 w-full resize-none rounded-[20px] bg-transparent px-4 py-3 text-sm leading-6 text-zinc-800 outline-none placeholder:text-zinc-400"
                            />
                            <div className="flex items-center justify-between border-t border-zinc-100 px-2 pt-2">
                                <div className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-[0.16em] text-zinc-400">
                                    <ShieldCheck className="h-4 w-4" />
                                    ReportDSL Only
                                </div>
                                <Button
                                    className="h-11 rounded-2xl bg-zinc-950 px-5 text-white shadow-lg hover:bg-black"
                                    disabled={isGenerating}
                                    onClick={handleGenerate}
                                >
                                    {isGenerating ? (
                                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                    ) : (
                                        <Send className="mr-2 h-4 w-4" />
                                    )}
                                    生成报表
                                </Button>
                            </div>
                        </div>
                    </div>
                </section>

                <section className="grid min-h-0 gap-4 2xl:grid-cols-[minmax(0,1fr)_380px]">
                    <div className="flex min-h-0 flex-col overflow-hidden rounded-[34px] border border-white/80 bg-white/70 shadow-[0_20px_80px_rgba(15,23,42,0.10)] backdrop-blur-3xl">
                        <PreviewHeader
                            task={task}
                            isValidating={isValidating}
                            isPublishing={isPublishing}
                            onValidate={handleValidate}
                            onPublish={handlePublish}
                        />
                        <div className="min-h-0 flex-1 bg-[radial-gradient(circle_at_top_left,rgba(255,255,255,0.96),rgba(255,255,255,0.72)_38%,rgba(244,244,245,0.92)_100%)] p-4">
                            {previewUrl ? (
                                <iframe
                                    title="FineReport 报表预览"
                                    src={previewUrl}
                                    className="h-full min-h-[540px] w-full rounded-[26px] border border-zinc-200/80 bg-white shadow-[0_16px_40px_rgba(15,23,42,0.10)]"
                                />
                            ) : (
                                <div className="flex h-full min-h-[540px] flex-col items-center justify-center rounded-[26px] border border-zinc-200/80 bg-white/88 text-center text-zinc-800 shadow-[inset_0_1px_0_rgba(255,255,255,0.85)]">
                                    <div className="mb-5 flex h-20 w-20 items-center justify-center rounded-[28px] bg-zinc-100 shadow-sm">
                                        <Globe2 className="h-9 w-9 text-zinc-500" />
                                    </div>
                                    <h2 className="text-2xl font-black tracking-tight text-zinc-900">
                                        等待 FineReport 预览
                                    </h2>
                                    <p className="mt-3 max-w-md text-sm leading-6 text-zinc-500">
                                        生成成功后，这里会加载后端返回的 `previewUrl`。当前阶段只考虑表格类周报、分组表、交叉表，不做图表型预览。
                                    </p>
                                </div>
                            )}
                        </div>
                    </div>

                    <aside className="min-h-0 overflow-hidden rounded-[34px] border border-white/70 bg-white/60 shadow-[0_20px_70px_rgba(15,23,42,0.08)] backdrop-blur-3xl">
                        <ScrollArea className="h-full">
                            <div className="space-y-4 p-5">
                                <StatusCard task={task} isLoading={taskQuery.isFetching || isGenerating} />
                                <IssueCard issues={issueList} />
                                <ExcelCard fields={primarySheet?.fields ?? []} sheetName={primarySheet?.sheetName} />
                                <DslCard task={task} sql={datasetSql} />
                            </div>
                        </ScrollArea>
                    </aside>
                </section>
            </div>
        </div>
    );
}

function PreviewHeader({
    task,
    isValidating,
    isPublishing,
    onValidate,
    onPublish,
}: {
    task?: ReportTaskRead;
    isValidating: boolean;
    isPublishing: boolean;
    onValidate: () => void;
    onPublish: () => void;
}) {
    return (
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-zinc-200/80 px-5 py-4 text-zinc-900">
            <div className="flex items-center gap-3">
                <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-zinc-100">
                    <BarChart3 className="h-5 w-5 text-zinc-700" />
                </div>
                <div>
                    <h2 className="text-lg font-black tracking-tight text-zinc-900">
                        {task?.reportName ?? '报表预览区'}
                    </h2>
                    <p className="text-xs font-medium text-zinc-500">
                        {task?.taskId
                            ? `任务 ${task.taskId.slice(0, 8)}`
                            : '生成后自动展示 FineReport 预览'}
                    </p>
                </div>
            </div>
            <div className="flex items-center gap-2">
                <Button
                    variant="outline"
                    className="rounded-2xl border-zinc-200 bg-white text-zinc-700 hover:bg-zinc-50 hover:text-zinc-950"
                    disabled={!task || isValidating}
                    onClick={onValidate}
                >
                    {isValidating ? (
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    ) : (
                        <Play className="mr-2 h-4 w-4" />
                    )}
                    校验预览
                </Button>
                <Button
                    className="rounded-2xl bg-zinc-950 text-white hover:bg-black"
                    disabled={!task || isPublishing}
                    onClick={onPublish}
                >
                    {isPublishing ? (
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    ) : (
                        <Rocket className="mr-2 h-4 w-4" />
                    )}
                    发布标记
                </Button>
            </div>
        </div>
    );
}

function StatusCard({ task, isLoading }: { task?: ReportTaskRead; isLoading: boolean }) {
    return (
        <div className="rounded-[26px] border border-white/80 bg-white/75 p-4 shadow-sm">
            <div className="mb-3 flex items-center justify-between">
                <div className="flex items-center gap-2 text-sm font-black">
                    <Sparkles className="h-4 w-4" />
                    生成状态
                </div>
                <Badge
                    className={cn(
                        'rounded-full',
                        task?.errors?.length
                            ? 'bg-red-100 text-red-700 hover:bg-red-100'
                            : 'bg-zinc-950 text-white hover:bg-zinc-950',
                    )}
                >
                    {isLoading ? '同步中' : STATUS_LABELS[task?.status ?? ''] ?? '未生成'}
                </Badge>
            </div>
            <div className="grid grid-cols-2 gap-2 text-xs">
                <Metric
                    label="报表类型"
                    value={REPORT_TYPE_LABELS[task?.reportType ?? ''] ?? '待识别'}
                />
                <Metric
                    label="数据源"
                    value={
                        task?.dataSourceStatus === 'designed_not_verified'
                            ? 'AI 设计未验证'
                            : task?.dataSourceStatus ?? '待生成'
                    }
                />
                <Metric
                    label="SQL 校验"
                    value={getSqlValidationLabel(task)}
                />
                <Metric
                    label="CPT 路径"
                    value={task?.cptObjectPath ? '已写入 staging' : '待写入'}
                />
                <Metric
                    label="DSL 路径"
                    value={task?.dslObjectPath ? '已保存' : '待保存'}
                />
            </div>
        </div>
    );
}

function IssueCard({ issues }: { issues: string[] }) {
    if (!issues.length) {
        return (
            <div className="rounded-[26px] border border-emerald-200/70 bg-emerald-50/80 p-4 text-emerald-900">
                <div className="flex items-center gap-2 text-sm font-black">
                    <CheckCircle2 className="h-4 w-4" />
                    暂无错误或警告
                </div>
                <p className="mt-2 text-xs leading-5 text-emerald-800/75">
                    生成、校验或发布后发现的问题会出现在这里。
                </p>
            </div>
        );
    }

    return (
        <div className="rounded-[26px] border border-amber-200/80 bg-amber-50/80 p-4 text-amber-950">
            <div className="mb-3 flex items-center gap-2 text-sm font-black">
                <AlertCircle className="h-4 w-4" />
                校验提示
            </div>
            <div className="space-y-2">
                {issues.map((issue) => (
                    <div key={issue} className="rounded-2xl bg-white/65 px-3 py-2 text-xs leading-5">
                        {issue}
                    </div>
                ))}
            </div>
        </div>
    );
}

function ExcelCard({ fields, sheetName }: { fields: ExcelFieldAnalysis[]; sheetName?: string }) {
    return (
        <div className="rounded-[26px] border border-white/80 bg-white/75 p-4 shadow-sm">
            <div className="mb-3 flex items-center justify-between">
                <div className="flex items-center gap-2 text-sm font-black">
                    <FileSpreadsheet className="h-4 w-4" />
                    Excel 字段
                </div>
                <span className="text-xs font-bold text-zinc-400">{sheetName ?? '未上传'}</span>
            </div>
            <div className="space-y-2">
                {fields.slice(0, 8).map((field) => (
                    <div
                        key={field.name}
                        className="flex items-center justify-between rounded-2xl bg-zinc-50 px-3 py-2"
                    >
                        <div className="min-w-0">
                            <div className="truncate text-xs font-bold text-zinc-800">{field.label}</div>
                            <div className="text-[11px] text-zinc-400">{field.name}</div>
                        </div>
                        <Badge variant="outline" className="ml-2 shrink-0 rounded-full bg-white text-[10px]">
                            {ROLE_LABELS[field.role] ?? field.role}
                        </Badge>
                    </div>
                ))}
                {!fields.length && (
                    <p className="text-xs leading-5 text-zinc-400">
                        上传 Excel 并生成后，会展示识别出的字段角色。
                    </p>
                )}
            </div>
        </div>
    );
}

function DslCard({ task, sql }: { task?: ReportTaskRead; sql?: string }) {
    const sqlValidation = task?.sqlValidation;
    return (
        <div className="rounded-[26px] border border-white/80 bg-zinc-950 p-4 text-white shadow-sm">
            <div className="mb-3 flex items-center gap-2 text-sm font-black">
                <Database className="h-4 w-4" />
                结构化数据
            </div>
            <div className="space-y-3">
                <CodeBlock title="SQL" content={sql || '生成后展示绑定参数的查询 SQL'} />
                <CodeBlock
                    title="SQL 校验"
                    content={
                        sqlValidation
                            ? JSON.stringify(
                                  {
                                      enabled: sqlValidation.enabled,
                                      configured: sqlValidation.configured,
                                      success: sqlValidation.success,
                                      executed: sqlValidation.executed,
                                      rowCount: sqlValidation.rowCount,
                                      columns: sqlValidation.columns,
                                      sampleRows: sqlValidation.sampleRows,
                                  },
                                  null,
                                  2,
                              )
                            : '启用 SQL Server 校验后，这里会展示执行状态、字段和少量样例行。'
                    }
                />
                <CodeBlock
                    title="ReportDSL"
                    content={
                        task?.reportDsl
                            ? JSON.stringify(task.reportDsl, null, 2)
                            : '生成后展示结构化 ReportDSL，AI 不直接输出 CPT/XML。当前阶段只考虑表格类报表。'
                    }
                />
            </div>
        </div>
    );
}

function getSqlValidationLabel(task?: ReportTaskRead) {
    const validation = task?.sqlValidation;
    if (!validation) {
        return '待校验';
    }
    if (!validation.enabled) {
        return '未启用';
    }
    if (!validation.configured) {
        return '未配置';
    }
    if (validation.success) {
        return validation.executed ? `通过 ${validation.rowCount ?? 0} 行` : '通过';
    }
    return '未通过';
}

function Metric({ label, value }: { label: string; value: string }) {
    return (
        <div className="rounded-2xl bg-zinc-50 px-3 py-2">
            <div className="text-[10px] font-bold uppercase tracking-[0.12em] text-zinc-400">
                {label}
            </div>
            <div className="mt-1 truncate text-xs font-black text-zinc-800">{value}</div>
        </div>
    );
}

function CodeBlock({ title, content }: { title: string; content: string }) {
    return (
        <div className="overflow-hidden rounded-2xl border border-white/10 bg-black/30">
            <div className="border-b border-white/10 px-3 py-2 text-[11px] font-black uppercase tracking-[0.16em] text-white/45">
                {title}
            </div>
            <pre className="max-h-56 overflow-auto whitespace-pre-wrap p-3 text-[11px] leading-5 text-zinc-200">
                {content}
            </pre>
        </div>
    );
}
