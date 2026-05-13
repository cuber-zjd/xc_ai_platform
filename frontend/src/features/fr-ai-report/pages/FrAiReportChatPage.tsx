import { useMemo, useRef, useState } from 'react';
import type { RefObject } from 'react';
import { createPortal } from 'react-dom';
import type { LucideIcon } from 'lucide-react';
import {
    AlertCircle,
    ArrowRight,
    CheckCircle2,
    Code2,
    Copy,
    Database,
    Eye,
    FileSpreadsheet,
    History,
    Loader2,
    PencilLine,
    Plus,
    ScrollText,
    SendHorizonal,
    ShieldCheck,
    Sparkles,
    Table2,
    ThumbsDown,
    ThumbsUp,
    UploadCloud,
} from 'lucide-react';
import { toast } from 'sonner';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils';
import {
    useCreateFrAiReportFeedback,
    useFrAiReportTask,
    useFrAiReportTasks,
    useGenerateFrAiReportCptStep,
    useGenerateFrAiReportDslStep,
    useGenerateFrAiReportSqlStep,
} from '@/features/fr-ai-report/hooks/useFrAiReport';
import type {
    ExcelFieldAnalysis,
    GenerateCptStepResponse,
    GenerateDslStepResponse,
    GenerateSqlStepResponse,
    ReportDsl,
    ReportTaskListItem,
    ReportTaskRead,
    SqlValidationResult,
} from '@/features/fr-ai-report/types';

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

type StepTask = Partial<ReportTaskRead> & Partial<GenerateSqlStepResponse> & Partial<GenerateDslStepResponse> & Partial<GenerateCptStepResponse>;
type ResultTabKey = 'result' | 'dslPreview' | 'dsl' | 'finePreview' | 'preview' | 'summary' | 'template' | 'excel';

const DEFAULT_REQUIREMENT = '按年份、日期、区域生成交叉日报，列展示各区域价格，并支持开始日期和结束日期筛选。';
const DEFAULT_REPORT_NAME = '区域统计表';

interface ConversationGroup {
    id: string;
    title: string;
    latestTask: ReportTaskListItem;
    tasks: ReportTaskListItem[];
    updateTime: string;
}

export function FrAiReportChatPage() {
    const fileInputRef = useRef<HTMLInputElement>(null);
    const [requirement, setRequirement] = useState(DEFAULT_REQUIREMENT);
    const [revisionNote, setRevisionNote] = useState('');
    const [reportName, setReportName] = useState(DEFAULT_REPORT_NAME);
    const [sourceTableName, setSourceTableName] = useState('');
    const [selectedFile, setSelectedFile] = useState<File | null>(null);
    const [taskId, setTaskId] = useState<string | null>(null);
    const [activeTab, setActiveTab] = useState<ResultTabKey>('result');
    const [showConversationList, setShowConversationList] = useState(false);
    const [expandedConversationId, setExpandedConversationId] = useState<string | null>(null);

    const generateMutation = useGenerateFrAiReportSqlStep();
    const dslMutation = useGenerateFrAiReportDslStep();
    const cptMutation = useGenerateFrAiReportCptStep();
    const taskQuery = useFrAiReportTask(taskId);
    const taskListQuery = useFrAiReportTasks(1, 20);
    const feedbackMutation = useCreateFrAiReportFeedback();

    const currentTask = taskId
        ? ({
            ...(generateMutation.data?.taskId === taskId ? generateMutation.data : {}),
            ...(taskQuery.data ?? {}),
            ...(dslMutation.data?.taskId === taskId ? dslMutation.data : {}),
            ...(cptMutation.data?.taskId === taskId ? cptMutation.data : {}),
        } as StepTask)
        : undefined;
    const taskItems = useMemo(() => taskListQuery.data?.items ?? [], [taskListQuery.data?.items]);
    const conversationGroups = useMemo(() => groupTasksByConversation(taskItems), [taskItems]);
    const primarySheet =
        currentTask?.excelAnalysis?.sheets?.find(
            (sheet) => sheet.sheetName === currentTask.excelAnalysis?.primarySheet,
        ) || currentTask?.excelAnalysis?.sheets?.[0];
    const issueList = [...(currentTask?.errors ?? []), ...(currentTask?.warnings ?? [])];
    const activeStep = getStepFromTab(activeTab);

    const mergedRequirement = useMemo(() => {
        const blocks = [requirement.trim()];
        if (revisionNote.trim()) {
            blocks.push(`补充修改意见：${revisionNote.trim()}`);
        }
        return blocks.filter(Boolean).join('\n');
    }, [requirement, revisionNote]);

    const handleGenerate = () => {
        if (!requirement.trim() && !selectedFile && !sourceTableName.trim()) {
            toast.error('请先输入报表要求、相关表名，或者上传一个 Excel。');
            return;
        }

        generateMutation.mutate(
            {
                requirement: mergedRequirement,
                reportName,
                sourceTableName,
                file: selectedFile,
                conversationId: currentTask?.conversationId ?? null,
            },
            {
                onSuccess: (data) => {
                    setTaskId(data.taskId);
                    toast.success('第一步已完成，已生成 SQL 和样例数据预览。');
                },
                onError: () => {
                    toast.error('SQL 生成失败，请检查输入内容或后端日志。');
                },
            },
        );
    };

    const handleNewConversation = () => {
        setTaskId(null);
        setReportName(DEFAULT_REPORT_NAME);
        setSourceTableName('');
        setRequirement(DEFAULT_REQUIREMENT);
        setRevisionNote('');
        setSelectedFile(null);
        setActiveTab('result');
        setShowConversationList(false);
        setExpandedConversationId(null);
        generateMutation.reset();
        dslMutation.reset();
        cptMutation.reset();
        if (fileInputRef.current) {
            fileInputRef.current.value = '';
        }
        toast.success('已新建会话，可以从第一步开始生成。');
    };

    const handleGenerateDsl = () => {
        if (!currentTask?.taskId || !currentTask.querySql) {
            toast.error('请先完成第一步 SQL 生成。');
            return;
        }
        dslMutation.mutate({ taskId: currentTask.taskId, dslFeedback: revisionNote }, {
            onSuccess: (data) => {
                setTaskId(data.taskId);
                setActiveTab('dslPreview');
                toast.success('第二步已完成，已生成 ReportDSL 和 DSL 预览。');
            },
            onError: () => {
                toast.error('ReportDSL 生成失败，请检查第一步结果或后端日志。');
            },
        });
    };

    const handleGenerateCpt = () => {
        if (!currentTask?.taskId || !currentTask.reportDsl) {
            toast.error('请先完成第二步 ReportDSL 生成。');
            return;
        }
        cptMutation.mutate(currentTask.taskId, {
            onSuccess: (data) => {
                setTaskId(data.taskId);
                setActiveTab('finePreview');
                toast.success(data.previewUrl ? '第三步已完成，已生成 FineReport 预览地址。' : '第三步已完成，预览地址待配置后可用。');
            },
            onError: () => {
                toast.error('CPT 生成或 MinIO 上传失败，请检查后端配置。');
            },
        });
    };

    const handleRestoreTask = (task: ReportTaskListItem) => {
        setTaskId(task.taskId);
        setReportName(task.reportName);
        setSourceTableName(task.sourceTableName ?? '');
        setRequirement(task.requirementText ?? '');
        setRevisionNote('');
        setActiveTab('result');
        toast.success('已恢复历史任务，可继续补充修改意见后重新生成。');
    };

    const handleRestoreConversation = (conversation: ConversationGroup) => {
        handleRestoreTask(conversation.latestTask);
        setExpandedConversationId(conversation.id);
        setShowConversationList(false);
    };

    const handleFeedback = (isPositive: boolean) => {
        if (!currentTask?.taskId) {
            return;
        }
        feedbackMutation.mutate(
            {
                taskId: currentTask.taskId,
                payload: {
                    feedbackType: isPositive ? 'accepted' : 'needs_adjustment',
                    content: isPositive ? '人工确认本次结果可作为正向样本' : revisionNote.trim() || '人工标记本次结果仍需调整',
                    isPositive,
                },
            },
            {
                onSuccess: () => {
                    toast.success(isPositive ? '已沉淀为正向反馈。' : '已记录为待优化反馈。');
                },
                onError: () => {
                    toast.error('反馈记录失败，请稍后重试。');
                },
            },
        );
    };

    return (
        <div className="fr-ai-report-page flex h-[calc(100vh-5.5rem)] min-h-0 w-full max-w-full flex-col gap-3 overflow-hidden px-1 pb-3 pt-1 lg:px-2">
            <section className="app-page-header relative shrink-0 px-5 py-4">
                <div className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
                    <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                            <Badge>FineReport 报表生成</Badge>
                        </div>
                    </div>
                    <div className="flex shrink-0 flex-wrap items-center gap-2">
                        <Button
                            type="button"
                            variant="default"
                            className="w-fit"
                            onClick={handleNewConversation}
                        >
                            <Plus className="h-4 w-4" />
                            新建会话
                        </Button>
                        <Button
                            type="button"
                            variant="outline"
                            className="w-fit bg-white/82"
                            onClick={() => setShowConversationList((value) => !value)}
                        >
                            <History className="h-4 w-4" />
                            历史会话
                            <Badge variant="outline" className="ml-1 bg-white/90">
                                {conversationGroups.length}
                            </Badge>
                        </Button>
                    </div>
                </div>
                {showConversationList ? (
                    <ConversationPopover
                        conversations={conversationGroups}
                        activeTaskId={currentTask?.taskId}
                        expandedConversationId={expandedConversationId}
                        isLoading={taskListQuery.isFetching}
                        onToggle={(conversationId) =>
                            setExpandedConversationId((current) => (current === conversationId ? null : conversationId))
                        }
                        onRestoreConversation={handleRestoreConversation}
                        onRestoreTask={(task) => {
                            handleRestoreTask(task);
                            setShowConversationList(false);
                        }}
                        onNewConversation={handleNewConversation}
                    />
                ) : null}
                <div className="mt-4">
                    <StepBar
                        activeStep={activeStep}
                        hasSql={Boolean(currentTask?.querySql)}
                        hasDsl={Boolean(currentTask?.reportDsl)}
                        hasCpt={Boolean(currentTask?.cptObjectPath || currentTask?.previewUrl)}
                        onStepChange={(step) => setActiveTab(getDefaultTabForStep(step, currentTask))}
                    />
                </div>
            </section>

            <div className="grid min-h-0 min-w-0 flex-1 gap-3 overflow-hidden xl:grid-cols-[minmax(0,0.82fr)_minmax(0,1.55fr)_minmax(0,1fr)] 2xl:grid-cols-[minmax(0,0.9fr)_minmax(0,1.65fr)_minmax(0,1fr)]">
                <section className="app-panel flex min-h-0 min-w-0 flex-col overflow-hidden rounded-[30px] p-4 2xl:p-5">
                    <SectionTitle
                        icon={activeStep === 1 ? PencilLine : activeStep === 2 ? Code2 : Eye}
                        title={activeStep === 1 ? '第一步输入材料' : activeStep === 2 ? '第二步 DSL 设计' : '第三步 FineReport 预览'}
                        description={
                            activeStep === 1
                                ? '用于生成 SQL 和样例数据预览。'
                                : activeStep === 2
                                    ? '只调整 ReportDSL 版式和 DSL 预览，不重复生成 SQL。'
                                    : '生成 CPT、上传 staging 并获取 FineReport 预览。'
                        }
                    />

                    <StepInputPanel
                        activeStep={activeStep}
                        reportName={reportName}
                        sourceTableName={sourceTableName}
                        selectedFile={selectedFile}
                        requirement={requirement}
                        revisionNote={revisionNote}
                        mergedRequirement={mergedRequirement}
                        currentTask={currentTask}
                        isGeneratingSql={generateMutation.isPending}
                        isGeneratingDsl={dslMutation.isPending}
                        isGeneratingCpt={cptMutation.isPending}
                        fileInputRef={fileInputRef}
                        onReportNameChange={setReportName}
                        onSourceTableNameChange={setSourceTableName}
                        onSelectedFileChange={setSelectedFile}
                        onRequirementChange={setRequirement}
                        onRevisionNoteChange={setRevisionNote}
                        onGenerateSql={handleGenerate}
                        onGenerateDsl={handleGenerateDsl}
                        onGenerateCpt={handleGenerateCpt}
                    />
                </section>

                <section className="min-h-0 min-w-0 overflow-hidden">
                    <GenerationTabs
                        activeTab={activeTab}
                        onTabChange={setActiveTab}
                        task={currentTask}
                        validation={currentTask?.sqlValidation}
                        fields={primarySheet?.fields ?? []}
                        sheetName={primarySheet?.sheetName}
                        activeStep={activeStep}
                    />
                </section>

                <aside className="grid min-h-0 min-w-0 gap-3 overflow-hidden xl:grid-rows-[auto_minmax(0,1fr)]">
                    <IssueCard issues={issueList} />
                    <StatusCard
                        task={currentTask}
                        isLoading={taskQuery.isFetching || generateMutation.isPending || dslMutation.isPending || cptMutation.isPending}
                        isSavingFeedback={feedbackMutation.isPending}
                        onFeedback={handleFeedback}
                        className="h-full min-h-0 overflow-y-auto"
                    />
                </aside>
            </div>
        </div>
    );
}

function StepInputPanel({
    activeStep,
    reportName,
    sourceTableName,
    selectedFile,
    requirement,
    revisionNote,
    mergedRequirement,
    currentTask,
    isGeneratingSql,
    isGeneratingDsl,
    isGeneratingCpt,
    fileInputRef,
    onReportNameChange,
    onSourceTableNameChange,
    onSelectedFileChange,
    onRequirementChange,
    onRevisionNoteChange,
    onGenerateSql,
    onGenerateDsl,
    onGenerateCpt,
}: {
    activeStep: number;
    reportName: string;
    sourceTableName: string;
    selectedFile: File | null;
    requirement: string;
    revisionNote: string;
    mergedRequirement: string;
    currentTask?: StepTask;
    isGeneratingSql: boolean;
    isGeneratingDsl: boolean;
    isGeneratingCpt: boolean;
    fileInputRef: RefObject<HTMLInputElement | null>;
    onReportNameChange: (value: string) => void;
    onSourceTableNameChange: (value: string) => void;
    onSelectedFileChange: (value: File | null) => void;
    onRequirementChange: (value: string) => void;
    onRevisionNoteChange: (value: string) => void;
    onGenerateSql: () => void;
    onGenerateDsl: () => void;
    onGenerateCpt: () => void;
}) {
    if (activeStep === 3) {
        return (
            <div className="mt-5 flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto pr-1">
                <div className="rounded-[24px] border border-[#d8f0df] bg-emerald-50/72 p-4">
                    <div className="text-sm font-black text-[#243d30]">承接第二步结果</div>
                    <div className="mt-3 grid gap-2">
                        <Metric label="任务" value={currentTask?.taskId ? currentTask.taskId.slice(0, 8) : '待生成 DSL'} />
                        <Metric label="ReportDSL" value={currentTask?.reportDsl ? '已生成' : '未生成'} />
                        <Metric label="CPT" value={currentTask?.cptObjectPath ? '已上传 staging' : '待生成'} />
                        <Metric label="预览地址" value={currentTask?.previewUrl ? '已生成' : '待生成'} />
                    </div>
                </div>

                <div className="rounded-[28px] border border-[#d8f0df] bg-linear-to-br from-[#f2fff7] to-[#f7fbff] p-4 shadow-[0_18px_36px_rgba(80,150,110,0.08)]">
                    <div className="flex items-center gap-2 text-sm font-black text-[#33513d]">
                        <ShieldCheck className="h-4 w-4 text-emerald-600" />
                        本次只生成 staging 预览
                    </div>
                    <div className="mt-3 space-y-2 text-xs leading-6 text-[#657c6c]">
                        <div>MinIO 路径：{currentTask?.cptObjectPath || 'webroot/APP/reportlets_ai_staging/{task_id}/report.cpt'}</div>
                        <div>正式 reportlets：不复制、不覆盖。</div>
                    </div>
                </div>

                <Button
                    type="button"
                    size="lg"
                    className="w-full"
                    disabled={!currentTask?.reportDsl || isGeneratingCpt}
                    onClick={onGenerateCpt}
                >
                    {isGeneratingCpt ? <Loader2 className="h-4 w-4 animate-spin" /> : <Eye className="h-4 w-4" />}
                    {currentTask?.cptObjectPath ? '重新生成 FineReport 预览' : '生成 FineReport 预览'}
                </Button>

                {currentTask?.previewUrl ? (
                    <Button
                        type="button"
                        variant="outline"
                        className="w-full bg-white/82"
                        onClick={() => window.open(currentTask.previewUrl || '', '_blank', 'noopener,noreferrer')}
                    >
                        <Eye className="h-4 w-4" />
                        打开 FineReport 预览
                    </Button>
                ) : null}
            </div>
        );
    }

    if (activeStep === 2) {
        return (
            <div className="mt-5 flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto pr-1">
                <div className="rounded-[24px] border border-[#e7e9fb] bg-white/78 p-4">
                    <div className="text-sm font-black text-[#343852]">承接第一步结果</div>
                    <div className="mt-3 grid gap-2">
                        <Metric label="任务" value={currentTask?.taskId ? currentTask.taskId.slice(0, 8) : '待生成 SQL'} />
                        <Metric label="SQL" value={currentTask?.querySql ? '已生成' : '未生成'} />
                        <Metric label="样例数据" value={`${currentTask?.sqlValidation?.sampleRows?.length ?? 0} 行`} />
                    </div>
                </div>

                <TextAreaCard
                    title="DSL 修改意见"
                    value={revisionNote}
                    onChange={onRevisionNoteChange}
                    placeholder="例如：涨跌只保留最新一天，单独一行，只保留一行，放在市场下面、价格列表上面。"
                />

                <div className="rounded-[28px] border border-[#e7e9fb] bg-linear-to-br from-[#f7f5ff] to-[#eef6ff] p-4 shadow-[0_18px_36px_rgba(105,111,194,0.08)]">
                    <div className="flex items-center gap-2 text-sm font-black text-[#38405d]">
                        <ShieldCheck className="h-4 w-4 text-[#6d5df6]" />
                        本次只用于调整 ReportDSL
                    </div>
                    <pre className="mt-3 max-h-40 overflow-auto whitespace-pre-wrap break-words text-xs leading-6 text-[#646985] [overflow-wrap:anywhere]">
                        {revisionNote.trim() || '未填写修改意见时，将按第一步结果直接生成 DSL。'}
                    </pre>
                </div>

                <Button
                    type="button"
                    size="lg"
                    className="w-full"
                    disabled={!currentTask?.querySql || isGeneratingDsl}
                    onClick={onGenerateDsl}
                >
                    {isGeneratingDsl ? <Loader2 className="h-4 w-4 animate-spin" /> : <Code2 className="h-4 w-4" />}
                    {currentTask?.reportDsl ? '重新生成 DSL 并预览' : '生成 DSL 并预览'}
                </Button>
            </div>
        );
    }

    return (
        <div className="mt-5 flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto pr-1">
            <Input value={reportName} onChange={(event) => onReportNameChange(event.target.value)} placeholder="报表名称" />
            <Input
                value={sourceTableName}
                onChange={(event) => onSourceTableNameChange(event.target.value)}
                placeholder="相关表名，支持逗号或换行分隔"
            />

            <input
                ref={fileInputRef}
                type="file"
                accept=".xlsx,.xls"
                className="hidden"
                onChange={(event) => onSelectedFileChange(event.target.files?.[0] ?? null)}
            />
            <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                className="flex w-full items-center justify-between rounded-[24px] border border-white/80 bg-white/78 px-4 py-4 text-left shadow-[0_10px_24px_rgba(100,95,170,0.05)] transition-all duration-300 hover:bg-white"
            >
                <div className="flex items-center gap-3">
                    <div className="flex h-12 w-12 items-center justify-center rounded-[18px] bg-linear-to-br from-[#edf7ee] to-[#f8fff9] text-[#4caf72]">
                        <UploadCloud className="h-5 w-5" />
                    </div>
                    <div>
                        <div className="text-sm font-black text-[#2b2942]">上传 Excel 模板</div>
                        <div className="mt-1 text-xs text-[#8d90a6]">支持 .xlsx / .xls</div>
                    </div>
                </div>
                <ArrowRight className="h-4 w-4 text-[#a1a4b9]" />
            </button>

            {selectedFile ? (
                <div className="rounded-[22px] border border-emerald-200/80 bg-emerald-50/90 px-4 py-3 text-sm text-emerald-800">
                    <div className="flex items-center justify-between gap-3">
                        <div className="flex min-w-0 items-center gap-2 font-semibold">
                            <FileSpreadsheet className="h-4 w-4 shrink-0" />
                            <span className="truncate">{selectedFile.name}</span>
                        </div>
                        <button type="button" className="font-bold" onClick={() => onSelectedFileChange(null)}>
                            移除
                        </button>
                    </div>
                </div>
            ) : null}

            <TextAreaCard
                title="报表要求"
                value={requirement}
                onChange={onRequirementChange}
                placeholder="例如：按年份、日期、市场生成日报，列展示各区域价格与全国均价。"
            />
            <TextAreaCard
                title="SQL 补充说明"
                value={revisionNote}
                onChange={onRevisionNoteChange}
                placeholder="例如：多表请按 customer_id 关联；不要把市场转成宽表列。"
            />

            <div className="rounded-[28px] border border-[#e7e9fb] bg-linear-to-br from-[#f7f5ff] to-[#eef6ff] p-4 shadow-[0_18px_36px_rgba(105,111,194,0.08)]">
                <div className="flex items-center gap-2 text-sm font-black text-[#38405d]">
                    <ShieldCheck className="h-4 w-4 text-[#6d5df6]" />
                    本次将用于生成 SQL 的完整输入
                </div>
                <pre className="mt-3 max-h-40 overflow-auto whitespace-pre-wrap break-words text-xs leading-6 text-[#646985] [overflow-wrap:anywhere]">
                    {mergedRequirement || '暂未填写'}
                </pre>
            </div>

            <Button size="lg" className="w-full" disabled={isGeneratingSql} onClick={onGenerateSql}>
                {isGeneratingSql ? <Loader2 className="h-4 w-4 animate-spin" /> : <SendHorizonal className="h-4 w-4" />}
                生成 SQL 并预览数据
            </Button>
        </div>
    );
}

function StepBar({
    activeStep,
    hasSql,
    hasDsl,
    hasCpt,
    onStepChange,
}: {
    activeStep: number;
    hasSql: boolean;
    hasDsl: boolean;
    hasCpt: boolean;
    onStepChange: (step: number) => void;
}) {
    const steps = [
        { id: 1, title: '生成 SQL', desc: '需求、Excel、表名协作生成 SQL' },
        { id: 2, title: '设计报表', desc: '基于 SQL 产出 ReportDSL' },
        { id: 3, title: '预览发布', desc: '生成报表、预览并发布' },
    ];

    return (
        <div className="grid gap-3 xl:grid-cols-3">
            {steps.map((step, index) => {
                const active = step.id === activeStep;
                const completed = (step.id === 1 && hasSql) || (step.id === 2 && hasDsl) || (step.id === 3 && hasCpt);
                const disabled = (step.id === 2 && !hasSql) || (step.id === 3 && !hasDsl);
                return (
                    <button
                        key={step.id}
                        type="button"
                        disabled={disabled}
                        onClick={() => onStepChange(step.id)}
                        className={cn(
                            'relative rounded-[24px] border px-4 py-4 text-left transition-all duration-300',
                            active
                                ? 'border-transparent bg-linear-to-r from-[#ebe6ff] to-[#f5f7ff] shadow-[0_16px_36px_rgba(110,93,247,0.12)]'
                                : step.id === 3
                                    ? 'border-transparent bg-linear-to-r from-[#eefbf4] to-[#f8fffb]'
                                    : 'border-white/80 bg-white/72',
                            disabled ? 'cursor-not-allowed opacity-55' : 'cursor-pointer hover:-translate-y-0.5 hover:bg-white/86',
                        )}
                    >
                        <div className="flex items-center gap-3">
                            <div
                                className={cn(
                                    'flex h-10 w-10 items-center justify-center rounded-[16px] text-sm font-black',
                                    active
                                        ? 'bg-linear-to-br from-[#6e5df7] to-[#9f8aff] text-white'
                                        : completed
                                            ? 'bg-emerald-500 text-white'
                                            : step.id === 3
                                                ? 'bg-linear-to-br from-[#8bd9a0] to-[#62c97c] text-white'
                                                : 'bg-[#ebefff] text-[#6d5df6]',
                                )}
                            >
                                {completed ? <CheckCircle2 className="h-5 w-5" /> : `0${step.id}`}
                            </div>
                            <div className="min-w-0">
                                <div className="text-[16px] font-black tracking-tight text-[#24233b]">{step.title}</div>
                                <div className="mt-1 text-xs text-[#81849a]">{step.desc}</div>
                            </div>
                            {index < steps.length - 1 ? <ArrowRight className="ml-auto hidden h-4 w-4 text-[#a3a6bb] xl:block" /> : null}
                        </div>
                    </button>
                );
            })}
        </div>
    );
}

function SectionTitle({
    icon: Icon,
    title,
    description,
}: {
    icon: LucideIcon;
    title: string;
    description: string;
}) {
    return (
        <div>
            <div className="flex items-center gap-2 text-sm font-black text-[#2b2942]">
                <Icon className="h-4 w-4 text-[#6d5df6]" />
                {title}
            </div>
            <p className="mt-2 text-sm leading-6 text-[#878aa0]">{description}</p>
        </div>
    );
}

function TextAreaCard({
    title,
    value,
    onChange,
    placeholder,
}: {
    title: string;
    value: string;
    onChange: (value: string) => void;
    placeholder: string;
}) {
    return (
        <div className="rounded-[26px] border border-white/80 bg-white/80 p-3 shadow-[0_10px_24px_rgba(100,95,170,0.05)]">
            <div className="px-2 pb-2 text-sm font-black text-[#4c4f66]">{title}</div>
            <textarea
                value={value}
                onChange={(event) => onChange(event.target.value)}
                placeholder={placeholder}
                className="min-h-28 w-full resize-none rounded-[20px] bg-transparent px-3 py-2 text-sm leading-6 text-[#303249] outline-none placeholder:text-[#a0a3b9]"
            />
        </div>
    );
}

function ConversationPopover({
    conversations,
    activeTaskId,
    expandedConversationId,
    isLoading,
    onToggle,
    onRestoreConversation,
    onRestoreTask,
    onNewConversation,
}: {
    conversations: ConversationGroup[];
    activeTaskId?: string;
    expandedConversationId: string | null;
    isLoading: boolean;
    onToggle: (conversationId: string) => void;
    onRestoreConversation: (conversation: ConversationGroup) => void;
    onRestoreTask: (task: ReportTaskListItem) => void;
    onNewConversation: () => void;
}) {
    return createPortal(
        <div className="fixed right-10 top-24 z-[2147483647] w-[min(430px,calc(100vw-3rem))] overflow-hidden rounded-[26px] border border-white/80 bg-white/95 p-3 shadow-[0_24px_70px_rgba(86,91,160,0.18)] backdrop-blur-xl">
            <div className="mb-3 flex items-center justify-between gap-3 px-1">
                <div className="flex items-center gap-2 text-sm font-black text-[#2b2942]">
                    <History className="h-4 w-4 text-[#6d5df6]" />
                    历史会话
                </div>
                <div className="flex items-center gap-2">
                    <span className="text-xs font-bold text-[#9aa0b8]">{isLoading ? '刷新中' : `${conversations.length} 个会话`}</span>
                    <Button
                        type="button"
                        size="sm"
                        className="h-8 rounded-full px-3 text-xs"
                        onClick={onNewConversation}
                    >
                        <Plus className="h-3.5 w-3.5" />
                        新建
                    </Button>
                </div>
            </div>
            <div className="max-h-[420px] space-y-2 overflow-y-auto pr-1">
                {conversations.length ? (
                    conversations.map((conversation) => {
                        const expanded = expandedConversationId === conversation.id;
                        const active = conversation.tasks.some((task) => task.taskId === activeTaskId);
                        return (
                            <div
                                key={conversation.id}
                                className={cn(
                                    'overflow-hidden rounded-[20px] border transition-colors',
                                    active ? 'border-[#c8c7ff] bg-[#f5f3ff]' : 'border-[#eef0fb] bg-[#fbfcff]',
                                )}
                            >
                                <div className="flex items-start gap-2 p-3">
                                    <button
                                        type="button"
                                        className="min-w-0 flex-1 text-left"
                                        onClick={() => onRestoreConversation(conversation)}
                                    >
                                        <div className="truncate text-sm font-black text-[#2e3047]">{conversation.title}</div>
                                        <div className="mt-1 flex min-w-0 items-center gap-2 text-xs text-[#8e92aa]">
                                            <span className="shrink-0">{conversation.tasks.length} 轮</span>
                                            <span className="min-w-0 truncate">
                                                {conversation.latestTask.sourceTableName || conversation.latestTask.sourceFileName || '未填写来源'}
                                            </span>
                                            <span className="shrink-0">{formatDateTime(conversation.updateTime)}</span>
                                        </div>
                                    </button>
                                    <button
                                        type="button"
                                        onClick={() => onToggle(conversation.id)}
                                        className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-white text-[#777d99] transition-colors hover:text-[#5b50d6]"
                                        aria-label={expanded ? '收起轮次' : '展开轮次'}
                                    >
                                        <ArrowRight className={cn('h-4 w-4 transition-transform', expanded ? 'rotate-90' : '')} />
                                    </button>
                                </div>
                                {expanded ? (
                                    <div className="border-t border-[#eceffc] bg-white/72 p-2">
                                        {conversation.tasks.map((task) => (
                                            <button
                                                key={task.taskId}
                                                type="button"
                                                onClick={() => onRestoreTask(task)}
                                                className={cn(
                                                    'flex w-full items-center justify-between gap-3 rounded-[16px] px-3 py-2 text-left text-xs transition-colors',
                                                    task.taskId === activeTaskId ? 'bg-[#f0eeff] text-[#4d45c9]' : 'hover:bg-[#f6f7ff]',
                                                )}
                                            >
                                                <span className="min-w-0 truncate font-bold">第 {task.revisionNo} 轮 · {task.reportName}</span>
                                                <span className="shrink-0 text-[#9aa0b8]">{STATUS_LABELS[task.status] ?? task.status}</span>
                                            </button>
                                        ))}
                                    </div>
                                ) : null}
                            </div>
                        );
                    })
                ) : (
                    <div className="rounded-[18px] bg-[#f7f8ff] px-4 py-8 text-center text-sm text-[#9ba0b8]">
                        暂无历史会话
                    </div>
                )}
            </div>
        </div>,
        document.body,
    );
}

function StatusCard({
    task,
    isLoading,
    isSavingFeedback,
    onFeedback,
    className,
}: {
    task?: StepTask;
    isLoading: boolean;
    isSavingFeedback: boolean;
    onFeedback: (isPositive: boolean) => void;
    className?: string;
}) {
    return (
        <div className={cn('app-panel min-w-0 overflow-hidden rounded-[28px] p-4', className)}>
            <div className="mb-4 flex flex-col gap-3">
                <div>
                    <div className="flex items-center gap-2 text-sm font-black text-[#2b2942]">
                        <Sparkles className="h-4 w-4 text-[#6d5df6]" />
                        任务执行状态
                    </div>
                    <p className="mt-2 text-sm text-[#868aa0]">
                        {task?.taskId ? `任务 ${task.taskId.slice(0, 8)}` : '生成后会保留一个可回看的任务快照'}
                    </p>
                </div>
                <Badge variant="outline" className="w-fit bg-white/82 text-[#4f5368]">
                    {isLoading ? '处理中' : STATUS_LABELS[task?.status ?? ''] ?? '未开始'}
                </Badge>
            </div>
            <div className="grid min-w-0 gap-2.5">
                <Metric label="会话轮次" value={`第 ${task?.revisionNo ?? 1} 轮`} />
                <Metric label="报表类型" value={REPORT_TYPE_LABELS[task?.reportType ?? ''] ?? '待识别'} />
                <Metric
                    label="数据来源"
                    value={task?.dataSourceStatus === 'designed_not_verified' ? 'AI 设计未验证' : task?.dataSourceStatus ?? '待生成'}
                />
                <Metric label="SQL 校验" value={getSqlValidationLabel(task?.sqlValidation)} />
                <Metric label="ReportDSL" value={task?.reportDsl ? '已生成' : '待生成'} />
                <Metric label="CPT 文件" value={task?.cptObjectPath ? '已上传' : '待生成'} />
                <Metric label="FineReport 预览" value={task?.previewUrl ? '已生成' : '待生成'} />
                <Metric label="来源表名" value={task?.sourceTableName || '未填写'} />
                <Metric label="Excel 模板" value={task?.sourceFileName || '未上传'} />
            </div>
            {task?.taskId ? (
                <div className="mt-4 grid grid-cols-2 gap-2">
                    <Button type="button" variant="outline" size="sm" disabled={isSavingFeedback} onClick={() => onFeedback(true)}>
                        <ThumbsUp className="h-4 w-4" />
                        可用
                    </Button>
                    <Button type="button" variant="outline" size="sm" disabled={isSavingFeedback} onClick={() => onFeedback(false)}>
                        <ThumbsDown className="h-4 w-4" />
                        需调整
                    </Button>
                </div>
            ) : null}
        </div>
    );
}

function IssueCard({ issues }: { issues: string[] }) {
    if (!issues.length) {
        return (
            <div className="app-panel rounded-[28px] border-emerald-200/80 bg-emerald-50/88 p-4 text-emerald-900">
                <div className="flex items-center gap-2 text-sm font-black">
                    <CheckCircle2 className="h-4 w-4" />
                    暂无错误或警告
                </div>
                <p className="mt-2 text-sm leading-6 text-emerald-800/75">
                    SQL 生成和数据预览阶段暂未发现问题，可以继续下一步。
                </p>
            </div>
        );
    }

    return (
        <div className="app-panel rounded-[28px] border-amber-200/80 bg-amber-50/86 p-4 text-amber-950">
            <div className="mb-3 flex items-center gap-2 text-sm font-black">
                <AlertCircle className="h-4 w-4" />
                状态提示
            </div>
            <div className="space-y-2">
                {issues.map((issue) => (
                    <div key={issue} className="rounded-[18px] bg-white/72 px-3 py-3 text-sm leading-6">
                        {issue}
                    </div>
                ))}
            </div>
        </div>
    );
}

function GenerationTabs({
    activeTab,
    onTabChange,
    task,
    validation,
    fields,
    sheetName,
    activeStep,
}: {
    activeTab: ResultTabKey;
    onTabChange: (tab: ResultTabKey) => void;
    task?: StepTask;
    validation?: SqlValidationResult | null;
    fields: ExcelFieldAnalysis[];
    sheetName?: string;
    activeStep: number;
}) {
    const tabs: Array<{
        key: ResultTabKey;
        label: string;
        hint: string;
        icon: LucideIcon;
    }> = activeStep === 3
        ? [
            { key: 'finePreview', label: 'FineReport 预览', hint: '查看 CPT 运行预览', icon: Eye },
        ]
        : activeStep === 2
            ? [
            { key: 'dslPreview', label: 'DSL 预览', hint: '按 DSL 布局渲染表格', icon: Eye },
            { key: 'dsl', label: 'ReportDSL', hint: '查看结构化设计 JSON', icon: Code2 },
            ]
            : [
            { key: 'result', label: 'SQL 结果', hint: '查看 SQL 文本', icon: Database },
            { key: 'preview', label: '数据预览', hint: '查看字段与样例数据', icon: Table2 },
            { key: 'summary', label: '需求摘要', hint: '查看结构化需求拆解', icon: ScrollText },
            { key: 'template', label: '模版资源', hint: '查看 Excel 模版语义', icon: ScrollText },
            { key: 'excel', label: 'Excel 字段参考', hint: '查看字段角色识别', icon: FileSpreadsheet },
            ];

    return (
        <div className="app-panel flex h-full min-h-0 flex-col overflow-hidden rounded-[32px] p-5">
            <div className="flex min-h-0 flex-1 flex-col gap-4">
                <div className="flex flex-col gap-2">
                    <div className="flex items-center gap-2 text-sm font-black text-[#2b2942]">
                        <Sparkles className="h-4 w-4 text-[#6d5df6]" />
                        {activeStep === 3 ? '第三步预览区' : activeStep === 2 ? '第二步生成区' : '第一步生成区'}
                    </div>
                </div>

                <div className="overflow-hidden rounded-[24px] border border-white/75 bg-linear-to-r from-[#f7f5ff] via-white/88 to-[#eef6ff] p-1.5 shadow-[0_10px_26px_rgba(105,111,194,0.06)]">
                    <div className={cn('grid grid-cols-2 gap-1.5', activeStep === 2 || activeStep === 3 ? 'lg:grid-cols-2' : 'lg:grid-cols-3 2xl:grid-cols-5')}>
                        {tabs.map((tab) => {
                            const active = activeTab === tab.key;
                            const Icon = tab.icon;
                            return (
                                <button
                                    key={tab.key}
                                    type="button"
                                    onClick={() => onTabChange(tab.key)}
                                    className={cn(
                                        'min-w-0 rounded-[18px] border px-3 py-2 text-left transition-all duration-200',
                                        active
                                            ? 'border-transparent bg-white shadow-[0_12px_28px_rgba(110,93,247,0.12)]'
                                            : 'border-transparent bg-transparent hover:bg-white/72',
                                    )}
                                >
                                    <div className="flex items-center gap-2 text-[13px] font-black leading-4 text-[#333754]">
                                        <Icon className={cn('h-4 w-4 shrink-0', active ? 'text-[#6d5df6]' : 'text-[#9aa0bf]')} />
                                        <span className="line-clamp-2 leading-4">{tab.label}</span>
                                    </div>
                                    <div className="mt-1 hidden text-xs leading-5 text-[#8a8fa8] 2xl:block">{tab.hint}</div>
                                </button>
                            );
                        })}
                    </div>
                </div>

                <div className="min-h-0 flex-1 overflow-y-auto pr-1">
                    {activeStep === 3 ? (
                        <>
                            {activeTab === 'finePreview' ? <FineReportPreviewCard task={task} /> : null}
                        </>
                    ) : activeStep === 2 ? (
                        <>
                            {activeTab === 'dslPreview' ? <DslPreviewCard task={task} /> : null}
                            {activeTab === 'dsl' ? <DslJsonCard dsl={task?.reportDsl} /> : null}
                        </>
                    ) : (
                        <>
                            {activeTab === 'result' ? <EnhancedQueryResultCard task={task} /> : null}
                            {activeTab === 'preview' ? <EnhancedDataPreviewCard validation={validation} /> : null}
                            {activeTab === 'summary' ? <EnhancedSummaryCard task={task} /> : null}
                            {activeTab === 'template' ? <TemplateCard task={task} /> : null}
                            {activeTab === 'excel' ? <ExcelCard fields={fields} sheetName={sheetName} /> : null}
                        </>
                    )}
                </div>
            </div>
        </div>
    );
}

function DslJsonCard({ dsl }: { dsl?: ReportDsl | null }) {
    const dslText = dsl ? JSON.stringify(dsl, null, 2) : '执行第二步后，这里会展示后端生成的 ReportDSL。';

    return (
        <div className="app-panel flex h-full min-h-0 flex-col overflow-hidden rounded-[28px] p-4">
            <div className="mb-3 flex items-center justify-between gap-3">
                <div className="flex items-center gap-2 text-sm font-black text-[#2b2942]">
                    <Code2 className="h-4 w-4 text-[#6d5df6]" />
                    ReportDSL
                </div>
                <CopyActionButton text={dslText} label="复制 DSL" />
            </div>
            <CodeBlock title="ReportDSL JSON" content={dslText} />
        </div>
    );
}

function FineReportPreviewCard({ task }: { task?: StepTask }) {
    if (!task?.previewUrl) {
        return (
            <div className="rounded-[28px] border border-dashed border-[#d9ddf1] bg-white/70 p-6 text-sm leading-7 text-[#858aa5]">
                执行第三步后，这里会展示 FineReport 运行时预览。
            </div>
        );
    }

    return (
        <div className="space-y-4">
            <div className="rounded-[26px] border border-emerald-200/80 bg-emerald-50/86 p-4">
                <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                    <div className="min-w-0">
                        <div className="text-sm font-black text-emerald-950">FineReport 预览已生成</div>
                        <div className="mt-2 break-all text-xs leading-5 text-emerald-800/80">{task.previewUrl}</div>
                    </div>
                    <Button
                        type="button"
                        size="sm"
                        className="shrink-0"
                        onClick={() => window.open(task.previewUrl || '', '_blank', 'noopener,noreferrer')}
                    >
                        <Eye className="h-4 w-4" />
                        打开预览
                    </Button>
                </div>
                <div className="mt-4 grid gap-2 md:grid-cols-2">
                    <Metric label="CPT 文件" value={task.cptObjectPath || '未返回'} />
                    <Metric label="DSL 文件" value={task.dslObjectPath || '未返回'} />
                    <Metric label="SQL 文件" value={task.sqlObjectPath || '未返回'} />
                    <Metric label="日志文件" value={task.logObjectPath || '未返回'} />
                </div>
            </div>
            <div className="h-[520px] overflow-hidden rounded-[26px] border border-[#e7e9fb] bg-white">
                <iframe
                    title="FineReport 预览"
                    src={task.previewUrl}
                    className="h-full w-full border-0"
                />
            </div>
        </div>
    );
}

function DslPreviewCard({ task }: { task?: StepTask }) {
    const dsl = task?.reportDsl ?? null;
    const sampleRows = task?.sqlValidation?.sampleRows ?? [];

    if (!dsl) {
        return (
            <div className="app-panel flex h-full min-h-0 flex-col overflow-hidden rounded-[32px] p-5">
                <SectionTitle icon={Eye} title="DSL 预览" description="执行第二步后，这里会直接根据 ReportDSL 渲染表格预览，不依赖 FineReport 预览地址。" />
                <div className="mt-4 flex min-h-0 flex-1 items-center justify-center rounded-[24px] border border-dashed border-[#dfe3f8] bg-white/62 px-4 text-center text-sm leading-6 text-[#9093a8]">
                    已有 SQL 和样例数据后，点击左侧“生成 DSL 并预览”。
                </div>
            </div>
        );
    }

    const preview = buildDslPreview(dsl, sampleRows);
    const meta = dsl.reportMeta;

    return (
        <div className="app-panel flex h-full min-h-0 flex-col overflow-hidden rounded-[32px] p-5">
            <div className="flex flex-col gap-3">
                <SectionTitle icon={Eye} title="DSL 预览" description="根据 ReportDSL 的布局、分组和横向扩展配置渲染，作为发布前的轻量预览。" />
                {meta?.title ? (
                    <div className="rounded-[22px] border border-[#e7e9fb] bg-white/78 px-4 py-3 text-center">
                        <div className="text-base font-black text-[#24233b]">{meta.title}</div>
                        <div className="mt-1 flex flex-wrap justify-center gap-3 text-xs font-semibold text-[#7a7f99]">
                            {meta.unit ? <span>{meta.unit}</span> : null}
                            {meta.averageLabel ? <span>均价：{meta.averageLabel}</span> : null}
                            {meta.updateText ? <span>{meta.updateText}</span> : null}
                        </div>
                    </div>
                ) : null}
                <div className="grid gap-2 md:grid-cols-3">
                    <Metric label="报表名称" value={dsl.reportName} />
                    <Metric label="布局类型" value={REPORT_TYPE_LABELS[dsl.reportType] ?? dsl.reportType} />
                    <Metric label="预览数据" value={`${preview.rows.length} 行 · ${preview.columns.length} 列`} />
                </div>
            </div>
            <div className="mt-4 min-h-0 flex-1 overflow-hidden rounded-[24px] border border-white/80 bg-white/86">
                <div className="h-full overflow-auto">
                    <table className="w-full min-w-max border-collapse text-left text-xs">
                        <thead className="sticky top-0 z-10 bg-[#f4f5ff] text-[#5e627d]">
                            <tr>
                                {preview.columns.map((column) => (
                                    <th key={column.key} className="border-b border-[#e4e6f5] px-3 py-3 font-black">
                                        <span className="block max-w-[180px] truncate">{column.title}</span>
                                    </th>
                                ))}
                            </tr>
                        </thead>
                        <tbody>
                            {preview.rows.length ? (
                                preview.rows.map((row, index) => (
                                    <tr key={row.__key ?? index} className="odd:bg-white/95 even:bg-[#fbfcff]">
                                        {preview.columns.map((column) => (
                                            <td key={`${row.__key ?? index}-${column.key}`} className="border-b border-[#eef0fb] px-3 py-3 text-[#55586e]">
                                                <span className="block max-w-[180px] truncate">{formatCellValue(row[column.key])}</span>
                                            </td>
                                        ))}
                                    </tr>
                                ))
                            ) : (
                                <tr>
                                    <td colSpan={preview.columns.length || 1} className="px-3 py-10 text-center text-sm text-[#9da1b8]">
                                        DSL 已生成，当前没有可用于渲染的样例数据。
                                    </td>
                                </tr>
                            )}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    );
}

function TemplateCard({ task }: { task?: StepTask }) {
    const template = task?.excelAnalysis?.sheets?.find(
        (sheet) => sheet.sheetName === task.excelAnalysis?.primarySheet,
    )?.templateAnalysis;

    if (!template) {
        return (
            <div className="app-panel flex h-full min-h-0 flex-col overflow-hidden rounded-[28px] p-4">
                <div className="mb-3 flex items-center gap-2 text-sm font-black text-[#2b2942]">
                    <ScrollText className="h-4 w-4 text-[#6d5df6]" />
                    模板与资源
                </div>
                <p className="min-h-0 flex-1 overflow-auto text-sm leading-6 text-[#9093a8]">
                    上传 Excel 并执行第一步后，这里会展示标题、筛选区、更新时间和横向指标列等模板语义。
                </p>
            </div>
        );
    }

    const title = typeof template.title === 'string' ? template.title : '';
    const unit = typeof template.unit === 'string' ? template.unit : '';
    const updateText = typeof template.updateText === 'string' ? template.updateText : '';
    const averageLabel = typeof template.averageLabel === 'string' ? template.averageLabel : '';
    const notes = Array.isArray(template.notes) ? template.notes : [];
    const filters = Array.isArray(template.filters) ? template.filters : [];
    const rowDimensions = Array.isArray(template.rowDimensionLabels) ? template.rowDimensionLabels : [];
    const columnGroups = Array.isArray(template.columnGroupLabels) ? template.columnGroupLabels : [];

    return (
        <div className="app-panel flex h-full min-h-0 flex-col overflow-hidden rounded-[28px] p-4">
            <div className="mb-3 flex items-center gap-2 text-sm font-black text-[#2b2942]">
                <ScrollText className="h-4 w-4 text-[#6d5df6]" />
                模板与资源
            </div>
            <div className="min-h-0 flex-1 space-y-3 overflow-auto pr-1">
                {title ? <TemplateMetric label="标题" value={title} /> : null}
                {unit ? <TemplateMetric label="单位" value={unit} /> : null}
                {averageLabel ? <TemplateMetric label="均价" value={averageLabel} /> : null}
                {updateText ? <TemplateMetric label="更新时间" value={updateText} /> : null}
                {rowDimensions.length ? <TemplateMetric label="行维度" value={rowDimensions.join('、')} /> : null}
                {columnGroups.length ? <TemplateMetric label="横向指标列" value={columnGroups.join('、')} /> : null}
                {notes.length ? (
                    <div>
                        <div className="mb-2 text-sm font-black text-[#5b5e74]">备注说明</div>
                        <div className="space-y-2">
                            {notes.map((note, index) => (
                                <div key={`${index}-${String(note)}`} className="rounded-[18px] bg-white/74 px-3 py-3 text-sm leading-6 text-[#5f6278]">
                                    {String(note)}
                                </div>
                            ))}
                        </div>
                    </div>
                ) : null}
                {filters.length ? (
                    <div>
                        <div className="mb-2 text-sm font-black text-[#5b5e74]">筛选区</div>
                        <div className="space-y-2">
                            {filters.map((filter, index) => (
                                <div key={index} className="rounded-[18px] bg-white/74 px-3 py-3 text-sm leading-6 text-[#5f6278]">
                                    {Array.isArray(filter.values) ? filter.values.join(' | ') : ''}
                                </div>
                            ))}
                        </div>
                    </div>
                ) : null}
            </div>
        </div>
    );
}

function ExcelCard({ fields, sheetName }: { fields: ExcelFieldAnalysis[]; sheetName?: string }) {
    return (
        <div className="app-panel flex h-full min-h-0 flex-col overflow-hidden rounded-[28px] p-4">
            <div className="mb-3 flex items-center justify-between gap-3">
                <div className="flex items-center gap-2 text-sm font-black text-[#2b2942]">
                    <FileSpreadsheet className="h-4 w-4 text-[#6d5df6]" />
                    Excel 字段参考
                </div>
                <span className="text-xs font-bold text-[#a1a4b9]">{sheetName ?? '未上传'}</span>
            </div>
            <div className="min-h-0 flex-1 space-y-2 overflow-auto pr-1">
                {fields.length ? (
                    fields.map((field) => (
                        <div key={field.name} className="flex items-center justify-between rounded-[18px] bg-white/74 px-3 py-3">
                            <div className="min-w-0">
                                <div className="truncate text-sm font-bold text-[#2e3047]">{field.label}</div>
                                <div className="mt-1 text-xs text-[#a1a4b9]">{field.name}</div>
                            </div>
                            <Badge variant="outline" className="ml-2 shrink-0 bg-white/88 text-[#63667b]">
                                {ROLE_LABELS[field.role] ?? field.role}
                            </Badge>
                        </div>
                    ))
                ) : (
                    <p className="text-sm leading-6 text-[#9093a8]">上传 Excel 并执行第一步后，这里会展示识别出的字段信息。</p>
                )}
            </div>
        </div>
    );
}

function EnhancedSummaryCard({ task }: { task?: StepTask }) {
    const summaryText = task?.requirementSummary ? JSON.stringify(task.requirementSummary, null, 2) : '生成后这里会展示结构化需求摘要。';

    return (
        <div className="app-panel flex h-full min-h-0 flex-col overflow-hidden rounded-[28px] p-4">
            <div className="mb-3 flex items-center justify-between gap-3">
                <div className="flex items-center gap-2 text-sm font-black text-[#2b2942]">
                    <ScrollText className="h-4 w-4 text-[#6d5df6]" />
                    需求摘要
                </div>
                <CopyActionButton text={summaryText} label="复制摘要" />
            </div>
            <pre className="min-h-0 flex-1 overflow-auto rounded-[20px] border border-[#e9ebfb] bg-[#f7f8ff] p-4 text-[11px] leading-6 text-[#5f637c]">
                {summaryText}
            </pre>
        </div>
    );
}

function EnhancedQueryResultCard({ task }: { task?: StepTask }) {
    const sqlText = task?.querySql || '执行第一步后，这里会展示查询 SQL。';

    return (
        <div className="app-panel flex h-full min-h-0 flex-col overflow-hidden rounded-[32px] p-5">
            <div className="flex items-start justify-between gap-3">
                <SectionTitle icon={Database} title="生成结果" description="这里保留 SQL 文本，方便你继续提出修改意见后重新生成。" />
                <CopyActionButton text={sqlText} label="复制 SQL" />
            </div>
            <div className="mt-4 min-h-0 flex-1">
                <CodeBlock title="SQL" content={sqlText} />
            </div>
        </div>
    );
}

function EnhancedDataPreviewCard({ validation }: { validation?: SqlValidationResult | null }) {
    const columns = validation?.columns ?? [];
    const rows = validation?.sampleRows ?? [];
    const validationText = validation
        ? JSON.stringify(
            {
                enabled: validation.enabled,
                configured: validation.configured,
                success: validation.success,
                executed: validation.executed,
                rowCount: validation.rowCount,
                columns: validation.columns,
            },
            null,
            2,
        )
        : '生成后这里会展示 SQL 校验状态。';

    return (
        <div className="app-panel flex h-full min-h-0 flex-col overflow-hidden rounded-[32px] p-5">
            <SectionTitle icon={Table2} title="数据预览" description="使用 SQL 校验返回的字段和样例行，帮助人工判断结果是否符合预期。" />
            <div className="mt-4 grid min-h-0 flex-1 gap-4 xl:grid-rows-[minmax(180px,38%)_minmax(0,1fr)]">
                <div className="min-h-[180px] overflow-hidden">
                    <CodeBlock title="SQL 校验摘要" content={validationText} />
                </div>
                <div className="min-h-0 overflow-hidden rounded-[24px] border border-white/80 bg-white/82">
                    {columns.length ? (
                        <div className="h-full overflow-auto">
                            <table className="w-full table-fixed border-collapse text-left text-xs">
                                <thead className="sticky top-0 bg-[#f4f5ff] text-[#70738b]">
                                    <tr>
                                        {columns.map((column) => (
                                            <th key={column} className="max-w-[160px] truncate border-b border-[#e4e6f5] px-3 py-3 font-black">
                                                <span className="block truncate">{column}</span>
                                            </th>
                                        ))}
                                    </tr>
                                </thead>
                                <tbody>
                                    {rows.length ? (
                                        rows.map((row, index) => (
                                            <tr key={`${index}-${columns.join('-')}`} className="bg-white/92">
                                                {columns.map((column) => (
                                                    <td key={`${index}-${column}`} className="max-w-[160px] border-b border-[#eef0fb] px-3 py-3 text-[#55586e]">
                                                        <span className="block truncate">{formatCellValue(row[column])}</span>
                                                    </td>
                                                ))}
                                            </tr>
                                        ))
                                    ) : (
                                        <tr>
                                            <td colSpan={columns.length} className="px-3 py-8 text-center text-sm text-[#9da1b8]">
                                                已生成字段结构，暂未返回样例数据。
                                            </td>
                                        </tr>
                                    )}
                                </tbody>
                            </table>
                        </div>
                    ) : (
                        <div className="flex h-full items-center justify-center px-4 text-center text-sm text-[#9da1b8]">
                            生成后这里会展示数据预览表格。
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}

function CopyActionButton({ text, label }: { text: string; label: string }) {
    const handleCopy = async () => {
        try {
            await navigator.clipboard.writeText(text);
            toast.success(`${label}已复制`);
        } catch {
            toast.error(`${label}复制失败`);
        }
    };

    return (
        <button
            type="button"
            onClick={() => void handleCopy()}
            className="inline-flex shrink-0 items-center gap-1.5 rounded-full border border-[#e6e8fb] bg-white/88 px-3 py-1.5 text-xs font-bold text-[#5c6180] transition-colors hover:bg-white"
        >
            <Copy className="h-3.5 w-3.5" />
            {label}
        </button>
    );
}

function Metric({ label, value }: { label: string; value: string }) {
    return (
        <div className="min-w-0 rounded-[20px] bg-[#f6f7ff] px-3.5 py-3">
            <div className="text-[11px] font-bold uppercase tracking-[0.14em] text-[#9ca0b7]">{label}</div>
            <div className="mt-2 break-words text-sm font-black leading-5 text-[#2d3046] [overflow-wrap:anywhere]">{value}</div>
        </div>
    );
}

function TemplateMetric({ label, value }: { label: string; value: string }) {
    return (
        <div className="rounded-[18px] bg-white/76 px-3 py-3">
            <div className="text-sm font-black text-[#5b5e74]">{label}</div>
            <div className="mt-1 text-sm leading-6 text-[#70738a]">{value}</div>
        </div>
    );
}

function CodeBlock({ title, content }: { title: string; content: string }) {
    return (
        <div className="flex h-full min-h-0 flex-col overflow-hidden rounded-[24px] border border-[#e7e9fb] bg-[#f8f9ff] shadow-[0_18px_36px_rgba(105,111,194,0.08)]">
            <div className="border-b border-[#e7e9fb] px-4 py-3 text-[11px] font-black uppercase tracking-[0.16em] text-[#9aa0bf]">
                {title}
            </div>
            <pre className="min-h-0 flex-1 overflow-auto whitespace-pre-wrap break-words p-4 text-[11px] leading-6 text-[#59607d] [overflow-wrap:anywhere]">
                {content}
            </pre>
        </div>
    );
}

interface DslPreviewColumn {
    key: string;
    title: string;
}

interface DslPreviewRow extends Record<string, unknown> {
    __key: string;
}

function buildDslPreview(dsl: ReportDsl, sampleRows: Record<string, unknown>[]): { columns: DslPreviewColumn[]; rows: DslPreviewRow[] } {
    const horizontal = dsl.layout.horizontalExpansion;
    if (horizontal?.enabled && horizontal.dimensionField && horizontal.valueFields.length) {
        return buildHorizontalDslPreview(dsl, sampleRows, horizontal.dimensionField, horizontal.valueFields);
    }

    const columns = dsl.layout.columns.length
        ? dsl.layout.columns.map((column) => ({ key: column.field, title: column.title }))
        : (dsl.datasets[0]?.fields ?? []).map((field) => ({ key: field.name, title: field.label }));
    return {
        columns,
        rows: sampleRows.map((row, index) => ({ ...row, __key: `row-${index}` }) as DslPreviewRow),
    };
}

function buildHorizontalDslPreview(
    dsl: ReportDsl,
    sampleRows: Record<string, unknown>[],
    dimensionField: string,
    valueFields: string[],
): { columns: DslPreviewColumn[]; rows: DslPreviewRow[] } {
    const columnMeta = new Map(dsl.layout.columns.map((column) => [column.field, column.title]));
    const latestChangeEnabled = hasLatestChangeRow(dsl);
    const changeField = valueFields.find((field) => /change|涨跌|增减|环比|同比/i.test(field));
    const displayValueFields = latestChangeEnabled && changeField
        ? valueFields.filter((field) => field !== changeField)
        : valueFields;
    const rowFields = dsl.layout.rowGroupFields.length
        ? dsl.layout.rowGroupFields
        : dsl.layout.columns
            .filter((column) => column.role !== 'measure' && column.field !== dimensionField)
            .map((column) => column.field)
            .slice(0, 3);
    const dimensionValues = uniqueValues([
        ...(dsl.layout.horizontalExpansion?.sourceLabels ?? []),
        ...sampleRows.map((row) => formatCellValue(row[dimensionField])).filter((value) => value !== '—'),
    ]);
    const columns: DslPreviewColumn[] = [
        ...rowFields.map((field) => ({ key: field, title: columnMeta.get(field) ?? field })),
        ...dimensionValues.flatMap((dimension) =>
            displayValueFields.map((field) => ({
                key: `${dimension}__${field}`,
                title: displayValueFields.length === 1 ? dimension : `${dimension} · ${columnMeta.get(field) ?? field}`,
            })),
        ),
    ];
    const grouped = new Map<string, DslPreviewRow>();

    for (const sourceRow of sampleRows) {
        const groupKey = rowFields.map((field) => formatCellValue(sourceRow[field])).join('||') || '全部';
        const targetRow = grouped.get(groupKey) ?? { __key: groupKey };
        for (const field of rowFields) {
            targetRow[field] = sourceRow[field];
        }
        const dimension = formatCellValue(sourceRow[dimensionField]);
        if (dimension !== '—') {
            for (const field of displayValueFields) {
                targetRow[`${dimension}__${field}`] = sourceRow[field];
            }
        }
        grouped.set(groupKey, targetRow);
    }

    const rows = Array.from(grouped.values());
    const latestChangeRow = changeField
        ? buildLatestChangeRow(dsl, sampleRows, rowFields, dimensionField, displayValueFields, changeField)
        : null;

    return {
        columns,
        rows: latestChangeRow ? [latestChangeRow, ...rows] : rows,
    };
}

function uniqueValues(values: string[]) {
    return Array.from(new Set(values.filter(Boolean))).slice(0, 24);
}

function buildLatestChangeRow(
    dsl: ReportDsl,
    sampleRows: Record<string, unknown>[],
    rowFields: string[],
    dimensionField: string,
    displayValueFields: string[],
    changeField: string,
): DslPreviewRow | null {
    if (!hasLatestChangeRow(dsl) || !sampleRows.length || !displayValueFields.length) {
        return null;
    }

    const dateField = findDateField(dsl, rowFields);
    const latestValue = dateField ? latestComparableValue(sampleRows.map((row) => row[dateField])) : null;
    const latestRows = latestValue && dateField
        ? sampleRows.filter((row) => compareDateLike(row[dateField], latestValue) === 0)
        : sampleRows.slice(0, 1);
    const previewRow: DslPreviewRow = { __key: 'latest-change-row' };

    rowFields.forEach((field, index) => {
        previewRow[field] = index === 0 ? '涨跌' : index === 1 && latestValue ? formatCellValue(latestValue) : '';
    });
    for (const sourceRow of latestRows) {
        const dimension = formatCellValue(sourceRow[dimensionField]);
        if (dimension !== '—') {
            for (const field of displayValueFields) {
                previewRow[`${dimension}__${field}`] = sourceRow[changeField];
            }
        }
    }
    return previewRow;
}

function hasLatestChangeRow(dsl: ReportDsl) {
    return getSpecialRows(dsl).some((row) => row.kind === 'latest_change_only' || row.id === 'latest_change_row');
}

function getSpecialRows(dsl: ReportDsl): Array<Record<string, string>> {
    const specialRows = dsl.layout.designHints?.specialRows;
    return Array.isArray(specialRows)
        ? specialRows.filter((item): item is Record<string, string> => Boolean(item) && typeof item === 'object')
        : [];
}

function findDateField(dsl: ReportDsl, rowFields: string[]) {
    const dateColumn = dsl.layout.columns.find((column) => column.role === 'date' || column.type === 'date' || column.type === 'datetime');
    if (dateColumn) {
        return dateColumn.field;
    }
    return rowFields.find((field) => /date|day|日期|时间/.test(field));
}

function latestComparableValue(values: unknown[]) {
    return values
        .filter((value) => value !== null && value !== undefined && value !== '')
        .sort((a, b) => compareDateLike(b, a))[0];
}

function compareDateLike(left: unknown, right: unknown) {
    const leftTime = Date.parse(String(left));
    const rightTime = Date.parse(String(right));
    if (!Number.isNaN(leftTime) && !Number.isNaN(rightTime)) {
        return leftTime - rightTime;
    }
    return String(left).localeCompare(String(right), 'zh-CN');
}

function getStepFromTab(tab: ResultTabKey) {
    if (tab === 'finePreview') {
        return 3;
    }
    if (tab === 'dslPreview' || tab === 'dsl') {
        return 2;
    }
    return 1;
}

function getDefaultTabForStep(step: number, task?: StepTask): ResultTabKey {
    if (step === 2) {
        return task?.reportDsl ? 'dslPreview' : 'dsl';
    }
    if (step === 3) {
        return task?.reportDsl ? 'finePreview' : 'preview';
    }
    return 'result';
}

function getSqlValidationLabel(validation?: SqlValidationResult | null) {
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

function formatCellValue(value: unknown) {
    if (value === null || value === undefined || value === '') {
        return '—';
    }
    if (typeof value === 'object') {
        return JSON.stringify(value);
    }
    return String(value);
}

function formatDateTime(value: string) {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
        return '';
    }
    return date.toLocaleDateString('zh-CN', {
        month: '2-digit',
        day: '2-digit',
    });
}

function groupTasksByConversation(tasks: ReportTaskListItem[]): ConversationGroup[] {
    const groups = new Map<string, ReportTaskListItem[]>();
    for (const task of tasks) {
        const conversationId = task.conversationId || `task-${task.taskId}`;
        groups.set(conversationId, [...(groups.get(conversationId) ?? []), task]);
    }

    return Array.from(groups.entries())
        .map(([id, groupTasks]) => {
            const sortedTasks = [...groupTasks].sort((a, b) => {
                if ((b.revisionNo ?? 1) !== (a.revisionNo ?? 1)) {
                    return (b.revisionNo ?? 1) - (a.revisionNo ?? 1);
                }
                return new Date(b.updateTime).getTime() - new Date(a.updateTime).getTime();
            });
            const latestTask = sortedTasks[0];
            return {
                id,
                title: latestTask.reportName || '未命名报表会话',
                latestTask,
                tasks: sortedTasks,
                updateTime: latestTask.updateTime,
            };
        })
        .sort((a, b) => new Date(b.updateTime).getTime() - new Date(a.updateTime).getTime());
}
