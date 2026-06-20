import { useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { useLocation } from 'react-router-dom';
import {
    Bot,
    Braces,
    Check,
    ChevronDown,
    ChevronRight,
    Columns3,
    Database,
    ExternalLink,
    FileSpreadsheet,
    Paperclip,
    Folder,
    History,
    LayoutGrid,
    ListTree,
    MessageSquareText,
    PaintBucket,
    PanelRightClose,
    PanelRightOpen,
    Play,
    Plus,
    Redo2,
    RefreshCw,
    Rows3,
    Save,
    Search,
    SendHorizonal,
    Settings2,
    Sigma,
    SlidersHorizontal,
    Sparkles,
    Table2,
    Trash2,
    Undo2,
    WandSparkles,
} from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { cn } from '@/lib/utils';
import {
    useApplyFrReportAiOperationDraft,
    useFrAiReportAgentChat,
    useFrAiReportFileStructure,
    useFrAiReportFiles,
    useGenerateFrReportAiOperationDraft,
    useGenerateFrReportAiSnapshotCpt,
    useFrReportVisibilityPreference,
    useFrReportDatabaseConnections,
    useFrReportDatabaseDrivers,
    useFrReportVersions,
    usePreviewFrReportDataset,
    useRollbackFrReportFileVersion,
    useRollbackFrReportStructureVersion,
    useRecycleFrReportFile,
    useSyncFrReportExternalVersion,
    useUpsertFrReportDatabaseConnection,
    useUpdateFrReportVisibilityPreference,
} from '@/features/fr-ai-report/hooks/useFrAiReport';
import type {
    FrReportAiApplyDraftResponse,
    FrReportAiOperationDraftResponse,
    FrReportAiSnapshotCptResponse,
    FrAiReportAgentChatResponse,
    FrAiReportAgentContext,
    FrAiReportRequirementReviewResponse,
    GenerateCptStepResponse,
    GenerateDslStepResponse,
    GenerateSqlStepResponse,
    FrReportCellRead,
    FrReportDatasetRead,
    FrReportFileRead,
    FrReportFileStructureRead,
    FrReportSheetRead,
} from '@/features/fr-ai-report/types';

const toolbarItems = [
    { label: '保存', icon: Save, active: true },
    { label: '撤销', icon: Undo2 },
    { label: '重做', icon: Redo2 },
    { label: 'SQL', icon: Database },
    { label: '公式', icon: Sigma },
    { label: '边框', icon: LayoutGrid },
    { label: '填充', icon: PaintBucket },
    { label: '预览', icon: Play, active: true },
];

const DEFAULT_CANVAS_ROWS = 18;
const DEFAULT_CANVAS_COLUMNS = 12;

const aiMessages = [
    {
        role: 'assistant',
        content: '已识别当前报表适合使用长表数据集，并通过横向扩展表达城市和市场列。',
    },
    {
        role: 'user',
        content: '把年销量放到产品分组后面，客户名称列加宽，筛选区保留开始年月和结束年月。',
    },
    {
        role: 'assistant',
        content: '已生成 3 个操作：调整列顺序、更新 C 列宽度、保留筛选区参数。确认后会生成版本 V2.3。',
    },
];

const operationItems = [
    '更新 SQL：保留 record_date / market / price / change_amt 长表结构',
    '调整 DSL：C 列宽度 180，客户名称不换行',
    '设置横向扩展：市场字段按列展开，合计行固定',
];

const DEFAULT_NEW_REPORT_TEMPLATE_OBJECT_PATH = 'webroot/APP/reportlets/数据分析/农产品价格平台/大豆/谷物大豆国际海运费报价-周报.cpt';

type AiPreviewCellPatch = {
    style?: Partial<FrReportCellRead['style']>;
    text?: string;
    badge?: string;
};

type AiPreviewPatch = {
    cells?: Record<string, AiPreviewCellPatch>;
};

type AssistantMessage = {
    id: string;
    role: 'user' | 'assistant' | 'system';
    content: string;
    status?: 'pending' | 'success' | 'error';
};

void aiMessages;
void operationItems;

interface ReportTreeFolder {
    name: string;
    path: string;
    fileCount: number;
    folders: ReportTreeFolder[];
    files: FrReportFileRead[];
}

export function FrAiReportChatPage() {
    const location = useLocation();
    const [selectedCell, setSelectedCell] = useState('C3');
    const [selectedPanel, setSelectedPanel] = useState<'属性' | '小驰'>('小驰');
    const [rightPanelVisible, setRightPanelVisible] = useState(true);
    const [rightPanelWidth, setRightPanelWidth] = useState(430);
    const [isResizingRightPanel, setIsResizingRightPanel] = useState(false);
    const [reportKeyword, setReportKeyword] = useState('');
    const [selectedReportPath, setSelectedReportPath] = useState<string | null>(null);
    const [selectedDatasetName, setSelectedDatasetName] = useState<string | null>(null);
    const [previewColumnsByDataset, setPreviewColumnsByDataset] = useState<Record<string, string[]>>({});
    const [aiDraft, setAiDraft] = useState<FrReportAiOperationDraftResponse | null>(null);
    const [aiPreviewPatch, setAiPreviewPatch] = useState<AiPreviewPatch | null>(null);
    const [aiAppliedSnapshotId, setAiAppliedSnapshotId] = useState<string | null>(null);
    const [aiSnapshotCpt, setAiSnapshotCpt] = useState<FrReportAiSnapshotCptResponse | null>(null);
    const [newReportDialogOpen, setNewReportDialogOpen] = useState(false);
    const reportFilesQuery = useFrAiReportFiles(reportKeyword, 3000);
    const allReportFilesQuery = useFrAiReportFiles('', 5000, true);
    const visibilityPreferenceQuery = useFrReportVisibilityPreference();
    const updateVisibilityPreference = useUpdateFrReportVisibilityPreference();
    const [expandedFolders, setExpandedFolders] = useState<Set<string>>(() => new Set());
    const [collapsedFolders, setCollapsedFolders] = useState<Set<string>>(() => new Set());
    const [visibilityDialogOpen, setVisibilityDialogOpen] = useState(false);
    const [draftVisiblePaths, setDraftVisiblePaths] = useState<Set<string>>(() => new Set());
    const isAdminRoute = location.pathname.startsWith('/admin/');
    const reportFiles = useMemo(() => reportFilesQuery.data?.items ?? [], [reportFilesQuery.data?.items]);
    const selectedReport = useMemo(() => {
        return reportFiles.find((item) => item.objectPath === selectedReportPath) ?? reportFiles[0] ?? null;
    }, [reportFiles, selectedReportPath]);
    const reportStructureQuery = useFrAiReportFileStructure(selectedReport?.objectPath);
    const selectedCellDetail = useMemo(() => {
        const column = selectedCell.replace(/\d+/g, '');
        const row = selectedCell.replace(/\D+/g, '');
        return { column, row };
    }, [selectedCell]);
    const activeSheet = reportStructureQuery.data?.document?.sheets[0] ?? null;
    const selectedReportCell = useMemo(() => {
        return activeSheet?.cells.find((cell) => cell.address === selectedCell) ?? null;
    }, [activeSheet, selectedCell]);
    const inferredColumnsByDataset = useMemo(() => {
        const result: Record<string, string[]> = {};
        for (const cell of activeSheet?.cells ?? []) {
            const binding = cell.fieldBinding ?? cell.dataColumn;
            const datasetName = binding?.dataset;
            const fieldName = binding?.field;
            if (!datasetName || !fieldName) {
                continue;
            }
            result[datasetName] = result[datasetName] ?? [];
            if (!result[datasetName].includes(fieldName)) {
                result[datasetName].push(fieldName);
            }
        }
        return result;
    }, [activeSheet]);
    const selectedDatasetPreviewColumns = selectedDatasetName
        ? previewColumnsByDataset[selectedDatasetName]?.length
            ? previewColumnsByDataset[selectedDatasetName]
            : inferredColumnsByDataset[selectedDatasetName] ?? []
        : [];
    const parsedFieldBindings = selectedDatasetPreviewColumns.map((field) => ({
        dataset: selectedDatasetName,
        field,
        expression: field,
    }));
    useEffect(() => {
        if (!isResizingRightPanel) {
            return undefined;
        }
        const handleMouseMove = (event: MouseEvent) => {
            setRightPanelWidth(Math.min(Math.max(window.innerWidth - event.clientX, 360), 680));
        };
        const handleMouseUp = () => setIsResizingRightPanel(false);
        document.body.style.cursor = 'col-resize';
        document.body.style.userSelect = 'none';
        window.addEventListener('mousemove', handleMouseMove);
        window.addEventListener('mouseup', handleMouseUp);
        return () => {
            document.body.style.cursor = '';
            document.body.style.userSelect = '';
            window.removeEventListener('mousemove', handleMouseMove);
            window.removeEventListener('mouseup', handleMouseUp);
        };
    }, [isResizingRightPanel]);

    return (
        <div
            className={cn(
                'fr-ai-report-page flex min-h-0 w-full max-w-none flex-col overflow-hidden bg-white',
                isAdminRoute ? 'h-[calc(100vh-3.5rem)]' : 'h-screen',
            )}
        >
            <header className="flex shrink-0 items-center justify-between border-b border-[#e8eeee] bg-white px-5 py-3">
                <div className="min-w-0">
                    <div className="flex items-center gap-2">
                        <Badge className="border-[#dedede] bg-white text-[#0f8f7b] shadow-none">真实报表</Badge>
                        <h1 className="truncate text-lg font-semibold text-[#1f2933]">帆软报表助手</h1>
                        <span className="hidden rounded-full border border-[#dbe7e4] bg-[#f6fbfa] px-2.5 py-1 text-xs text-[#5c716d] md:inline-flex">
                            小驰报表助手 V2
                        </span>
                    </div>
                    <p className="mt-1 text-xs text-[#71817e]">已对接帆软 MinIO，当前先展示真实报表文件列表。</p>
                </div>
                <div className="flex items-center gap-2">
                    <Button
                        variant="outline"
                        className="h-9 border-[#bfe3dc] bg-[#f6fbfa] text-[#0b7c6b] hover:bg-[#eaf7f4]"
                        onClick={() => setNewReportDialogOpen(true)}
                    >
                        <Sparkles className="size-4" />
                        AI 新建报表
                    </Button>
                    <Button variant="outline" className="h-9 border-[#dedede] text-[#333333] hover:bg-[#f5f5f5]">
                        <History className="size-4" />
                        历史版本
                    </Button>
                    <Button
                        variant="outline"
                        className="h-9 border-[#dedede] text-[#333333] hover:bg-[#f5f5f5]"
                        onClick={() => {
                            setDraftVisiblePaths(new Set(visibilityPreferenceQuery.data?.visiblePaths ?? []));
                            setVisibilityDialogOpen(true);
                        }}
                    >
                        <Settings2 className="size-4" />
                        显示范围
                    </Button>
                    <Button className="h-9 bg-[#0f8f7b] text-white hover:bg-[#0b7c6b]">
                        <Sparkles className="size-4" />
                        生成 CPT
                    </Button>
                </div>
            </header>

            <div className="flex shrink-0 items-center gap-1 border-b border-[#eeeeee] bg-white px-4 py-2">
                {toolbarItems.map((item) => {
                    const Icon = item.icon;
                    return (
                        <button
                            key={item.label}
                            type="button"
                            className={cn(
                                'inline-flex h-8 items-center gap-1 rounded-md px-2.5 text-xs font-medium text-[#555555] transition hover:bg-[#f5f5f5] hover:text-[#0f8f7b]',
                                item.active && 'bg-[#f2f7f6] text-[#0f8f7b]',
                            )}
                            title={item.label}
                        >
                            <Icon className="size-4" />
                            <span className="hidden xl:inline">{item.label}</span>
                        </button>
                    );
                })}
                <div className="mx-2 h-5 w-px bg-[#e5e5e5]" />
                <button type="button" className="inline-flex h-8 items-center gap-1 rounded-md px-2 text-xs text-[#555555] hover:bg-[#f5f5f5]">
                    宋体
                    <ChevronDown className="size-3" />
                </button>
                <button type="button" className="inline-flex h-8 items-center gap-1 rounded-md px-2 text-xs text-[#555555] hover:bg-[#f5f5f5]">
                    13
                    <ChevronDown className="size-3" />
                </button>
            </div>

            <main className="flex min-h-0 flex-1 bg-white">
                <aside className="hidden min-h-0 w-[260px] shrink-0 border-r border-[#e5e5e5] bg-[#fafafa] 2xl:block">
                    <div className="border-b border-[#eeeeee] p-3">
                        <div className="relative">
                            <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-[#8aa19c]" />
                            <Input
                                value={reportKeyword}
                                onChange={(event) => setReportKeyword(event.target.value)}
                                className="h-9 border-[#dedede] bg-white pl-9 text-sm"
                                placeholder="搜索报表文件"
                            />
                        </div>
                    </div>
                    <div className="h-full overflow-auto p-3">
                        <section className="mb-4">
                            <div className="mb-2 flex items-center justify-between gap-2 text-xs font-semibold text-[#444444]">
                                <span className="flex min-w-0 items-center gap-2">
                                    <Folder className="size-4 shrink-0 text-[#0f8f7b]" />
                                    <span className="truncate">报表文件</span>
                                </span>
                                <span className="shrink-0 rounded-full bg-white px-2 py-0.5 text-[11px] text-[#6d817d] ring-1 ring-[#e5e5e5]">
                                    {reportFilesQuery.data?.total ?? 0}
                                </span>
                            </div>
                            <ReportFileList
                                files={reportFiles}
                                selectedPath={selectedReport?.objectPath ?? null}
                                expandedFolders={expandedFolders}
                                collapsedFolders={collapsedFolders}
                                loading={reportFilesQuery.isLoading}
                                error={reportFilesQuery.error}
                                onToggleFolder={(folderPath, isExpanded) => {
                                    setExpandedFolders((current) => {
                                        const next = new Set(current);
                                        if (isExpanded) {
                                            next.delete(folderPath);
                                            setCollapsedFolders((collapsed) => new Set(collapsed).add(folderPath));
                                        } else {
                                            next.add(folderPath);
                                            setCollapsedFolders((collapsed) => {
                                                const nextCollapsed = new Set(collapsed);
                                                nextCollapsed.delete(folderPath);
                                                return nextCollapsed;
                                            });
                                        }
                                        return next;
                                    });
                                }}
                                onSelect={(file) => setSelectedReportPath(file.objectPath)}
                            />
                        </section>

                        <section className="mb-4">
                            <div className="mb-2 flex items-center gap-2 text-xs font-semibold text-[#444444]">
                                <Database className="size-4 text-[#0f8f7b]" />
                                数据集
                            </div>
                            <ReportDatasetList
                                structure={reportStructureQuery.data ?? null}
                                loading={reportStructureQuery.isLoading || reportStructureQuery.isFetching}
                                error={reportStructureQuery.error}
                                selectedDatasetName={selectedDatasetName}
                                onDatasetSelect={setSelectedDatasetName}
                                onDatasetPreview={(datasetName, columns) =>
                                    setPreviewColumnsByDataset((current) => ({
                                        ...current,
                                        [datasetName]: columns,
                                    }))
                                }
                            />
                        </section>

                        <section className="mb-4">
                            <div className="mb-2 flex items-center gap-2 text-xs font-semibold text-[#444444]">
                                <ListTree className="size-4 text-[#0f8f7b]" />
                                字段
                            </div>
                            <div className="space-y-1">
                                {parsedFieldBindings.length > 0 ? (
                                    parsedFieldBindings.map((binding) => (
                                        <ResourcePill
                                            key={`${binding.dataset ?? 'dataset'}-${binding.field}`}
                                            label={binding.dataset ? `${binding.dataset}.${binding.field}` : binding.field ?? binding.expression}
                                        />
                                    ))
                                ) : (
                                    <div className="rounded-lg border border-[#eeeeee] bg-white px-3 py-3 text-xs text-[#6d817d]">当前报表暂无已解析字段绑定</div>
                                )}
                            </div>
                        </section>
                    </div>
                </aside>

                <section className="flex min-h-0 min-w-0 flex-1 flex-col">
                    <div className="flex shrink-0 items-center justify-between border-b border-[#eeeeee] bg-white px-4 py-3">
                        <div className="min-w-0">
                            <div className="flex items-center gap-2">
                                <FileSpreadsheet className="size-4 text-[#0f8f7b]" />
                                <span className="truncate text-sm font-semibold text-[#213531]">
                                    {selectedReport?.fileName ?? '请选择报表文件'}
                                </span>
                                <Badge className="border-[#d8ebe6] bg-[#f6fbfa] text-[#0c7a68] shadow-none">
                                    {selectedReport ? selectedReport.fileType.toUpperCase() : '未选择'}
                                </Badge>
                            </div>
                            <p className="mt-1 truncate text-xs text-[#6d817d]">
                                {selectedReport ? selectedReport.reportPath : '从左侧真实报表列表选择一个 CPT / FRM 文件'}
                            </p>
                        </div>
                        <div className="flex items-center gap-2 text-xs text-[#60736f]">
                            <span>缩放 100%</span>
                            <span className="rounded-md bg-[#f7f7f7] px-2 py-1 ring-1 ring-[#e5e5e5]">选区 {selectedCell}</span>
                            {!rightPanelVisible ? (
                                <Button
                                    type="button"
                                    variant="outline"
                                    size="sm"
                                    className="h-8 border-[#d8ebe6] bg-[#f6fbfa] px-2 text-xs text-[#0c7a68] hover:bg-[#eef8f5]"
                                    onClick={() => {
                                        setRightPanelVisible(true);
                                        setSelectedPanel('小驰');
                                    }}
                                >
                                    <PanelRightOpen className="size-3.5" />
                                    打开小驰
                                </Button>
                            ) : null}
                        </div>
                    </div>

                    <ReportDesignCanvas
                        sheet={activeSheet}
                        loading={reportStructureQuery.isLoading || reportStructureQuery.isFetching}
                        error={reportStructureQuery.error}
                        selectedCell={selectedCell}
                        previewPatch={aiPreviewPatch}
                        onSelectCell={setSelectedCell}
                    />

                    <footer className="flex shrink-0 items-center justify-between border-t border-[#dfecea] bg-white px-4 py-2 text-xs text-[#657773]">
                        <div className="flex items-center gap-4">
                            <span>版本 V2.3</span>
                            <span className="text-[#0b7c6b]">MinIO 已连接</span>
                            <span className="text-[#0b7c6b]">已发现 {reportFilesQuery.data?.total ?? 0} 个报表</span>
                        </div>
                        <span>FineReport 预览待生成</span>
                    </footer>
                </section>

                {rightPanelVisible ? (
                <aside className="relative grid min-h-0 shrink-0 grid-rows-[auto_minmax(0,1fr)] border-l border-[#e5e5e5] bg-white" style={{ width: rightPanelWidth }}>
                    <button
                        type="button"
                        aria-label="拖动调整小驰宽度"
                        className="absolute left-0 top-0 z-20 h-full w-1 cursor-col-resize bg-transparent transition hover:bg-[#bfe3dc]"
                        onMouseDown={(event) => {
                            event.preventDefault();
                            setIsResizingRightPanel(true);
                        }}
                    />
                    <div className="flex border-b border-[#eeeeee] p-2">
                        {(['属性', '小驰'] as const).map((item) => (
                            <button
                                key={item}
                                type="button"
                                onClick={() => setSelectedPanel(item)}
                                className={cn(
                                    'flex-1 rounded-lg px-3 py-2 text-sm font-medium text-[#666666] transition hover:bg-[#f5f5f5]',
                                    selectedPanel === item && 'bg-[#f2f7f6] text-[#0f8f7b]',
                                )}
                            >
                                {item}
                            </button>
                        ))}
                        <Button
                            type="button"
                            variant="ghost"
                            size="icon"
                            className="ml-2 size-9 shrink-0 text-[#60736f] hover:bg-[#f5f5f5] hover:text-[#0f8f7b]"
                            onClick={() => setRightPanelVisible(false)}
                            title="隐藏小驰侧栏"
                        >
                            <PanelRightClose className="size-4" />
                        </Button>
                    </div>
                    <div className="min-h-0 overflow-hidden p-4">
                        {selectedPanel === '属性' ? (
                            <div className="h-full overflow-auto">
                                <PropertyPanel
                                    selectedCell={selectedCell}
                                    column={selectedCellDetail.column}
                                    row={selectedCellDetail.row}
                                    cell={selectedReportCell}
                                    sheet={activeSheet}
                                />
                            </div>
                        ) : (
                            <CopilotPanel
                                selectedReport={selectedReport}
                                reportStructure={reportStructureQuery.data ?? null}
                                structureLoading={reportStructureQuery.isLoading || reportStructureQuery.isFetching}
                                structureError={reportStructureQuery.error}
                                structureFetching={reportStructureQuery.isFetching}
                                onRefetchStructure={() => reportStructureQuery.refetch()}
                                selectedCell={selectedCell}
                                selectedDatasetName={selectedDatasetName}
                                previewColumns={selectedDatasetPreviewColumns}
                                aiDraft={aiDraft}
                                appliedSnapshotId={aiAppliedSnapshotId}
                                snapshotCpt={aiSnapshotCpt}
                                onDraftReady={(draft) => {
                                    setAiDraft(draft);
                                    setAiPreviewPatch(toAiPreviewPatch(draft.previewPatch));
                                    setAiAppliedSnapshotId(null);
                                    setAiSnapshotCpt(null);
                                }}
                                onApplyDraft={(draft) => {
                                    setAiDraft(draft);
                                }}
                                onDraftApplied={(result) => {
                                    setAiPreviewPatch(toAiPreviewPatch(result.previewPatch));
                                    setAiAppliedSnapshotId(result.targetSnapshot.snapshotId);
                                    setAiSnapshotCpt(null);
                                }}
                                onSnapshotCptGenerated={(result) => {
                                    setAiSnapshotCpt(result);
                                }}
                                onClearDraft={() => {
                                    setAiDraft(null);
                                    setAiPreviewPatch(null);
                                    setAiAppliedSnapshotId(null);
                                    setAiSnapshotCpt(null);
                                }}
                            />
                        )}
                    </div>
                </aside>
                ) : null}
            </main>

            <NewReportAiDialog
                open={newReportDialogOpen}
                onOpenChange={setNewReportDialogOpen}
                templateObjectPath={selectedReport?.objectPath ?? null}
                reportFiles={allReportFilesQuery.data?.items ?? reportFiles}
            />

            <VisibilityPreferenceDialog
                open={visibilityDialogOpen}
                onOpenChange={setVisibilityDialogOpen}
                files={allReportFilesQuery.data?.items ?? []}
                selectedPaths={draftVisiblePaths}
                loading={allReportFilesQuery.isLoading || visibilityPreferenceQuery.isLoading}
                saving={updateVisibilityPreference.isPending}
                onTogglePath={(path) => setDraftVisiblePaths((current) => toggleVisiblePath(current, path))}
                onShowAll={() => {
                    updateVisibilityPreference.mutate(
                        { visiblePaths: [] },
                        {
                            onSuccess: () => {
                                setDraftVisiblePaths(new Set());
                                setVisibilityDialogOpen(false);
                            },
                        },
                    );
                }}
                onSave={() => {
                    updateVisibilityPreference.mutate(
                        { visiblePaths: Array.from(draftVisiblePaths) },
                        {
                            onSuccess: () => setVisibilityDialogOpen(false),
                        },
                    );
                }}
            />
        </div>
    );
}

function ReportFileList({
    files,
    selectedPath,
    expandedFolders,
    collapsedFolders,
    loading,
    error,
    onToggleFolder,
    onSelect,
}: {
    files: FrReportFileRead[];
    selectedPath: string | null;
    expandedFolders: Set<string>;
    collapsedFolders: Set<string>;
    loading: boolean;
    error: unknown;
    onToggleFolder: (folderPath: string, isExpanded: boolean) => void;
    onSelect: (file: FrReportFileRead) => void;
}) {
    if (loading) {
        return <div className="rounded-lg border border-[#eeeeee] bg-white px-3 py-4 text-xs text-[#6d817d]">正在读取帆软报表列表...</div>;
    }

    if (error) {
        return <div className="rounded-lg border border-[#f0d0d0] bg-[#fff8f8] px-3 py-4 text-xs text-[#9b3a3a]">报表列表读取失败，请检查帆软 MinIO 配置。</div>;
    }

    if (files.length === 0) {
        return <div className="rounded-lg border border-[#eeeeee] bg-white px-3 py-4 text-xs text-[#6d817d]">没有找到匹配的报表文件。</div>;
    }

    const tree = buildReportFileTree(files);

    return (
        <div className="rounded-lg border border-[#eeeeee] bg-white p-1">
            {tree.folders.map((folder) => (
                <ReportTreeFolderNode
                    key={folder.path}
                    folder={folder}
                    level={0}
                    selectedPath={selectedPath}
                    expandedFolders={expandedFolders}
                    collapsedFolders={collapsedFolders}
                    onToggleFolder={onToggleFolder}
                    onSelect={onSelect}
                />
            ))}
            {tree.files.map((file) => (
                <ReportTreeFileNode key={file.objectPath} file={file} level={0} selectedPath={selectedPath} onSelect={onSelect} />
            ))}
        </div>
    );
}

function ReportTreeFolderNode({
    folder,
    level,
    selectedPath,
    expandedFolders,
    collapsedFolders,
    onToggleFolder,
    onSelect,
}: {
    folder: ReportTreeFolder;
    level: number;
    selectedPath: string | null;
    expandedFolders: Set<string>;
    collapsedFolders: Set<string>;
    onToggleFolder: (folderPath: string, isExpanded: boolean) => void;
    onSelect: (file: FrReportFileRead) => void;
}) {
    const hasSelected = reportFolderHasSelectedFile(folder, selectedPath);
    const expanded = expandedFolders.has(folder.path) || (hasSelected && !collapsedFolders.has(folder.path));

    return (
        <div>
            <button
                type="button"
                onClick={() => onToggleFolder(folder.path, expanded)}
                className={cn(
                    'flex w-full items-center gap-1.5 rounded-md py-1.5 pr-2 text-left text-xs text-[#444444] transition hover:bg-[#f7f7f7]',
                    hasSelected && 'text-[#0f8f7b]',
                )}
                style={{ paddingLeft: level * 14 + 6 }}
            >
                {expanded ? <ChevronDown className="size-3.5 shrink-0" /> : <ChevronRight className="size-3.5 shrink-0 text-[#8aa19c]" />}
                <Folder className={cn('size-3.5 shrink-0', hasSelected ? 'text-[#0f8f7b]' : 'text-[#8aa19c]')} />
                <span className="min-w-0 flex-1 truncate font-semibold">{folder.name}</span>
                <span className="shrink-0 rounded-full bg-[#f2f7f6] px-1.5 py-0.5 text-[10px] text-[#0c7a68]">{folder.fileCount}</span>
            </button>
            {expanded ? (
                <div>
                    {folder.folders.map((childFolder) => (
                        <ReportTreeFolderNode
                            key={childFolder.path}
                            folder={childFolder}
                            level={level + 1}
                            selectedPath={selectedPath}
                            expandedFolders={expandedFolders}
                            collapsedFolders={collapsedFolders}
                            onToggleFolder={onToggleFolder}
                            onSelect={onSelect}
                        />
                    ))}
                    {folder.files.map((file) => (
                        <ReportTreeFileNode key={file.objectPath} file={file} level={level + 1} selectedPath={selectedPath} onSelect={onSelect} />
                    ))}
                </div>
            ) : null}
        </div>
    );
}

function ReportTreeFileNode({
    file,
    level,
    selectedPath,
    onSelect,
}: {
    file: FrReportFileRead;
    level: number;
    selectedPath: string | null;
    onSelect: (file: FrReportFileRead) => void;
}) {
    const active = file.objectPath === selectedPath;

    return (
        <button
            type="button"
            onClick={() => onSelect(file)}
            className={cn(
                'flex w-full items-center gap-2 rounded-md py-1.5 pr-2 text-left text-xs text-[#666666] transition hover:bg-[#f7f7f7] hover:text-[#0f8f7b]',
                active && 'bg-[#f2fbf8] text-[#0f8f7b] ring-1 ring-inset ring-[#d7eee8]',
            )}
            style={{ paddingLeft: level * 14 + 24 }}
        >
            <FileSpreadsheet className="size-3.5 shrink-0 text-[#0f8f7b]" />
            <span className="min-w-0 flex-1 truncate font-medium">{file.fileName}</span>
            <span className="shrink-0 rounded bg-[#f2f7f6] px-1.5 py-0.5 text-[10px] uppercase text-[#0c7a68]">{file.fileType}</span>
        </button>
    );
}

function ResourcePill({ label }: { label: string }) {
    return (
        <button
            type="button"
            className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left text-xs text-[#666666] transition hover:bg-[#f2f2f2] hover:text-[#0f8f7b]"
        >
            <span className="size-1.5 rounded-full bg-[#b7c9c5]" />
            <span className="truncate">{label}</span>
        </button>
    );
}

function ReportDesignCanvas({
    sheet,
    loading,
    error,
    selectedCell,
    previewPatch,
    onSelectCell,
}: {
    sheet: FrReportSheetRead | null;
    loading: boolean;
    error: unknown;
    selectedCell: string;
    previewPatch: AiPreviewPatch | null;
    onSelectCell: (cell: string) => void;
}) {
    if (loading) {
        return <div className="grid min-h-0 flex-1 place-items-center bg-[#fafafa] p-4 text-sm text-[#60736f]">正在解析报表画布...</div>;
    }

    if (error) {
        return <div className="grid min-h-0 flex-1 place-items-center bg-[#fffafa] p-4 text-sm text-[#9b3a3a]">报表结构读取失败，暂时无法渲染画布。</div>;
    }

    const rowCount = Math.min(sheet?.rowCount ?? DEFAULT_CANVAS_ROWS, 200);
    const columnCount = Math.min(sheet?.columnCount ?? DEFAULT_CANVAS_COLUMNS, 60);
    const rows = Array.from({ length: rowCount }, (_, index) => index + 1);
    const columns = Array.from({ length: columnCount }, (_, index) => index + 1);
    const cellMap = new Map((sheet?.cells ?? []).map((cell) => [`${cell.row}:${cell.column}`, cell]));
    const coveredCells = mergedCoveredCells(sheet?.cells ?? []);
    const columnWidths = new Map((sheet?.columns ?? []).map((item) => [item.index, clampSize(item.size, 72, 220)]));
    const rowHeights = new Map((sheet?.rows ?? []).map((item) => [item.index, clampSize(item.size, 28, 96)]));
    const gridTemplateColumns = `44px ${columns.map((column) => `${columnWidths.get(column) ?? 88}px`).join(' ')}`;
    const gridTemplateRows = `32px ${rows.map((row) => `${rowHeights.get(row) ?? 36}px`).join(' ')}`;
    const truncated = (sheet?.rowCount ?? 0) > rowCount || (sheet?.columnCount ?? 0) > columnCount;

    return (
        <div className="min-h-0 flex-1 overflow-auto bg-[#fafafa] p-4">
            <div className="inline-block min-w-full rounded-xl border border-[#dedede] bg-white shadow-sm">
                <div
                    className="grid text-xs text-[#333333]"
                    style={{
                        gridTemplateColumns,
                        gridTemplateRows,
                    }}
                >
                    <div className="sticky left-0 top-0 z-30 border-b border-r border-[#dedede] bg-[#f7f7f7]" />
                    {columns.map((column) => (
                        <div
                            key={`header-${column}`}
                            className="sticky top-0 z-20 flex items-center justify-center border-b border-r border-[#dedede] bg-[#f7f7f7] font-semibold text-[#555555]"
                            style={{ gridColumn: column + 1, gridRow: 1 }}
                        >
                            {columnLabel(column)}
                        </div>
                    ))}
                    {rows.map((row) => (
                        <div
                            key={`row-${row}`}
                            className="sticky left-0 z-10 flex items-center justify-center border-b border-r border-[#dedede] bg-[#f7f7f7] text-[#8a8a8a]"
                            style={{ gridColumn: 1, gridRow: row + 1 }}
                        >
                            {row}
                        </div>
                    ))}
                    {rows.flatMap((row) =>
                        columns.map((column) => {
                            const address = `${columnLabel(column)}${row}`;
                            const cell = cellMap.get(`${row}:${column}`);
                            if (!cell && coveredCells.has(`${row}:${column}`)) {
                                return null;
                            }
                            const rowSpan = Math.min(cell?.rowSpan ?? 1, rowCount - row + 1);
                            const colSpan = Math.min(cell?.colSpan ?? 1, columnCount - column + 1);
                            const content = cell?.text ?? cell?.formula ?? '';
                            const isSelected = address === selectedCell;
                            const patch = previewPatch?.cells?.[address];
                            const style = { ...cellStyle(cell), ...cellStyleFromPatch(patch?.style) };
                            const wrapContent = shouldWrapCell(cell, content);
                            return (
                                <button
                                    key={address}
                                    type="button"
                                    onClick={() => onSelectCell(address)}
                                    className={cn(
                                        'flex min-w-0 overflow-hidden border-b border-r border-[#eeeeee] px-2 text-left text-[11px] leading-4 transition hover:bg-[#f7f7f7]',
                                        cell?.fieldBinding && 'bg-[#f7fbfa] text-[#1f4f45]',
                                        cell?.formula && 'font-medium text-[#273b49]',
                                        patch && 'relative z-10 animate-pulse ring-2 ring-inset ring-[#f0b429]',
                                        isSelected && 'relative z-20 bg-[#f2fbf8] ring-2 ring-inset ring-[#19a88d]',
                                    )}
                                    style={{
                                        gridColumn: `${column + 1} / span ${colSpan}`,
                                        gridRow: `${row + 1} / span ${rowSpan}`,
                                        ...style,
                                    }}
                                    title={patch?.text || content || address}
                                >
                                    <span className={cn('block min-w-0', wrapContent ? 'whitespace-pre-line break-words' : 'truncate')}>
                                        {patch?.text ?? content}
                                    </span>
                                    {patch?.badge ? (
                                        <span className="absolute right-1 top-1 rounded bg-[#0f8f7b] px-1 text-[9px] font-semibold leading-3 text-white">
                                            {patch.badge}
                                        </span>
                                    ) : null}
                                </button>
                            );
                        }),
                    )}
                </div>
            </div>
            <div className="mt-2 flex items-center justify-between text-xs text-[#657773]">
                <span>
                    {sheet ? `${sheet.name} · ${sheet.cells.length} 个单元格 · ${sheet.merges.length} 个合并区域` : '当前报表暂无可渲染结构'}
                </span>
                {truncated ? <span className="text-[#9a6a12]">画布较大，当前仅展示前 {rowCount} 行、{columnCount} 列</span> : null}
            </div>
        </div>
    );
}

function ReportDatasetList({
    structure,
    loading,
    error,
    selectedDatasetName,
    onDatasetSelect,
    onDatasetPreview,
}: {
    structure: FrReportFileStructureRead | null;
    loading: boolean;
    error: unknown;
    selectedDatasetName: string | null;
    onDatasetSelect: (datasetName: string) => void;
    onDatasetPreview: (datasetName: string, columns: string[]) => void;
}) {
    const [selectedDataset, setSelectedDataset] = useState<FrReportDatasetRead | null>(null);

    if (loading) {
        return <div className="rounded-lg border border-[#eeeeee] bg-white px-3 py-3 text-xs text-[#6d817d]">正在读取当前报表数据集...</div>;
    }

    if (error) {
        return <div className="rounded-lg border border-[#f0d0d0] bg-[#fff8f8] px-3 py-3 text-xs text-[#9b3a3a]">数据集读取失败</div>;
    }

    const datasets = structure?.datasets ?? [];
    if (datasets.length === 0) {
        return <div className="rounded-lg border border-[#eeeeee] bg-white px-3 py-3 text-xs text-[#6d817d]">当前报表暂无已解析数据集</div>;
    }

    return (
        <>
            <div className="space-y-1">
                {datasets.map((dataset, index) => {
                    const name = dataset.name || `未命名数据集 ${index + 1}`;
                    const detail = [dataset.databaseName, dataset.parameters.length > 0 ? `${dataset.parameters.length} 个参数` : null]
                        .filter(Boolean)
                        .join(' · ');
                    return (
                        <button
                            key={`${name}-${index}`}
                            type="button"
                            className={cn(
                                'flex w-full min-w-0 items-start gap-2 rounded-lg px-2.5 py-2 text-left text-xs transition hover:bg-[#f2f2f2] hover:text-[#0f8f7b]',
                                selectedDatasetName === name ? 'bg-[#eef8f5] text-[#0c7a68]' : 'text-[#666666]',
                            )}
                            onClick={() => {
                                onDatasetSelect(name);
                                setSelectedDataset(dataset);
                            }}
                        >
                            <Database className="mt-0.5 size-3.5 shrink-0 text-[#0f8f7b]" />
                            <span className="min-w-0 flex-1">
                                <span className="block truncate font-medium text-[#3f4f4b]">{name}</span>
                                {detail ? <span className="mt-0.5 block truncate text-[11px] text-[#7a8a87]">{detail}</span> : null}
                            </span>
                            <ChevronRight className="mt-0.5 size-3.5 shrink-0 text-[#8aa19c]" />
                        </button>
                    );
                })}
            </div>
            <DatasetDetailDialog
                key={selectedDataset ? `${selectedDataset.name}-${selectedDataset.databaseName}-${selectedDataset.querySql}` : 'empty-dataset'}
                dataset={selectedDataset}
                onOpenChange={(open) => !open && setSelectedDataset(null)}
                onPreviewSuccess={onDatasetPreview}
            />
        </>
    );
}

function DatasetDetailDialog({
    dataset,
    onOpenChange,
    onPreviewSuccess,
}: {
    dataset: FrReportDatasetRead | null;
    onOpenChange: (open: boolean) => void;
    onPreviewSuccess: (datasetName: string, columns: string[]) => void;
}) {
    const datasetName = dataset?.name || '未命名数据集';
    const connectionName = dataset?.databaseName || '';
    const [querySql, setQuerySql] = useState(dataset?.querySql ?? '');
    const [parameterValues, setParameterValues] = useState<Record<string, string>>(() =>
        Object.fromEntries(
            (dataset?.parameters ?? []).map((parameter) => [
                parameter.name,
                parameter.defaultValue == null ? '' : String(parameter.defaultValue),
            ]),
        ),
    );
    const [connectionForm, setConnectionForm] = useState({
        driverKey: 'sqlserver',
        host: '',
        port: '1433',
        database: '',
        username: '',
        password: '',
    });
    const connectionsQuery = useFrReportDatabaseConnections();
    const driversQuery = useFrReportDatabaseDrivers();
    const previewDataset = usePreviewFrReportDataset();
    const upsertConnection = useUpsertFrReportDatabaseConnection();
    const matchedConnection = connectionsQuery.data?.find((item) => item.connectionName === connectionName);
    const selectedDriver = driversQuery.data?.find((driver) => driver.driverKey === connectionForm.driverKey);
    const previewResult = previewDataset.data;
    const shouldShowConnectionForm = Boolean(dataset && connectionName && (!matchedConnection || previewResult?.needsConnection));

    const handlePreview = () => {
        if (!dataset || !connectionName || !querySql.trim()) {
            return;
        }
        previewDataset.mutate(
            {
                connectionName,
                querySql,
                parameters: dataset.parameters.map((parameter) => ({
                    name: parameter.name,
                    value: parameterValues[parameter.name] ?? parameter.defaultValue ?? null,
                })),
                maxRows: 20,
            },
            {
                onSuccess: (result) => {
                    if (result.executed && result.columns.length > 0) {
                        onPreviewSuccess(datasetName, result.columns);
                    }
                },
            },
        );
    };

    const handleSaveConnection = () => {
        if (!connectionName) {
            return;
        }
        upsertConnection.mutate(
            {
                connectionName,
                driverKey: connectionForm.driverKey,
                dbType: selectedDriver?.dbType,
                host: connectionForm.host,
                port: Number(connectionForm.port) || selectedDriver?.defaultPort || 1433,
                database: connectionForm.database,
                username: connectionForm.username,
                password: connectionForm.password,
            },
            {
                onSuccess: () => handlePreview(),
            },
        );
    };

    return (
        <Dialog open={Boolean(dataset)} onOpenChange={onOpenChange}>
            <DialogContent className="max-h-[90vh] overflow-hidden rounded-xl border-[#dfe7e5] bg-white p-0 sm:max-w-5xl">
                <DialogHeader className="border-b border-[#eeeeee] px-5 py-4">
                    <DialogTitle className="truncate text-base font-semibold text-[#243a35]">数据集查询：{datasetName}</DialogTitle>
                    <DialogDescription className="text-xs text-[#6d817d]">
                        编辑 SQL、补充参数并预览数据；缺少数据库连接时可在当前弹窗中保存连接配置。
                    </DialogDescription>
                </DialogHeader>

                {dataset ? (
                    <div className="grid max-h-[calc(90vh-96px)] min-h-[620px] grid-rows-[minmax(0,1fr)_auto] overflow-hidden">
                        <div className="grid min-h-0 grid-cols-[240px_minmax(0,1fr)]">
                            <aside className="min-h-0 overflow-auto border-r border-[#eeeeee] bg-[#fafafa] p-4">
                                <div className="space-y-3">
                                    <InfoItem label="名称" value={datasetName} />
                                    <InfoItem label="连接" value={connectionName || '未识别'} />
                                    <InfoItem label="类型" value={dataset.className || '未识别'} />
                                </div>

                                <section className="mt-4 rounded-lg border border-[#eeeeee] bg-white p-3">
                                    <div className="mb-2 text-xs font-semibold text-[#243a35]">参数</div>
                                    {dataset.parameters.length > 0 ? (
                                        <div className="space-y-2">
                                            {dataset.parameters.map((parameter) => (
                                                <label key={parameter.name} className="block">
                                                    <span className="mb-1 block truncate text-[11px] text-[#60736f]">{parameter.name}</span>
                                                    <Input
                                                        value={parameterValues[parameter.name] ?? ''}
                                                        onChange={(event) =>
                                                            setParameterValues((current) => ({
                                                                ...current,
                                                                [parameter.name]: event.target.value,
                                                            }))
                                                        }
                                                        className="h-8 border-[#dedede] bg-white text-xs"
                                                        placeholder="预览参数值"
                                                    />
                                                </label>
                                            ))}
                                        </div>
                                    ) : (
                                        <div className="rounded-md bg-[#fafafa] px-3 py-2 text-xs text-[#8a8a8a] ring-1 ring-[#eeeeee]">无参数</div>
                                    )}
                                </section>

                                {shouldShowConnectionForm ? (
                                    <section className="mt-4 rounded-lg border border-[#f0dfb8] bg-[#fffaf0] p-3">
                                        <div className="text-xs font-semibold text-[#6f5210]">补充数据库连接</div>
                                        <p className="mt-1 text-[11px] leading-4 text-[#8a6518]">
                                            未找到连接名 {connectionName}，保存后可用于预览和后续 AI 修改。
                                        </p>
                                        <div className="mt-3 space-y-2">
                                            <Select
                                                value={connectionForm.driverKey}
                                                onValueChange={(driverKey) => {
                                                    const driver = driversQuery.data?.find((item) => item.driverKey === driverKey);
                                                    setConnectionForm((current) => ({
                                                        ...current,
                                                        driverKey,
                                                        port: driver ? String(driver.defaultPort) : current.port,
                                                    }));
                                                }}
                                            >
                                                <SelectTrigger className="h-8 bg-white text-xs">
                                                    <SelectValue placeholder="选择数据库驱动" />
                                                </SelectTrigger>
                                                <SelectContent>
                                                    {(driversQuery.data ?? []).map((driver) => (
                                                        <SelectItem key={driver.driverKey} value={driver.driverKey}>
                                                            {driver.displayName}
                                                        </SelectItem>
                                                    ))}
                                                </SelectContent>
                                            </Select>
                                            <Input value={connectionForm.host} onChange={(event) => setConnectionForm((current) => ({ ...current, host: event.target.value }))} className="h-8 bg-white text-xs" placeholder="主机 / IP" />
                                            <Input value={connectionForm.port} onChange={(event) => setConnectionForm((current) => ({ ...current, port: event.target.value }))} className="h-8 bg-white text-xs" placeholder="端口" />
                                            <Input value={connectionForm.database} onChange={(event) => setConnectionForm((current) => ({ ...current, database: event.target.value }))} className="h-8 bg-white text-xs" placeholder="数据库名" />
                                            <Input value={connectionForm.username} onChange={(event) => setConnectionForm((current) => ({ ...current, username: event.target.value }))} className="h-8 bg-white text-xs" placeholder="用户名" />
                                            <Input type="password" value={connectionForm.password} onChange={(event) => setConnectionForm((current) => ({ ...current, password: event.target.value }))} className="h-8 bg-white text-xs" placeholder="密码" />
                                            <Button className="h-8 w-full bg-[#0f8f7b] text-xs text-white hover:bg-[#0b7c6b]" onClick={handleSaveConnection} disabled={upsertConnection.isPending}>
                                                {upsertConnection.isPending ? '保存中...' : '保存连接并预览'}
                                            </Button>
                                        </div>
                                    </section>
                                ) : null}
                            </aside>

                            <main className="grid min-h-0 grid-rows-[minmax(0,1fr)_220px]">
                                <section className="min-h-0 border-b border-[#eeeeee] bg-white">
                                    <div className="flex items-center justify-between border-b border-[#eeeeee] px-4 py-2">
                                        <div className="text-xs font-semibold text-[#243a35]">SQL 查询</div>
                                        <div className="flex items-center gap-2">
                                            {dataset.querySqlTruncated ? <span className="rounded-full bg-[#fff8e8] px-2 py-0.5 text-[11px] text-[#9a6a12]">已截断</span> : null}
                                            <Button className="h-8 bg-[#0f8f7b] text-xs text-white hover:bg-[#0b7c6b]" onClick={handlePreview} disabled={previewDataset.isPending || !querySql.trim()}>
                                                {previewDataset.isPending ? '预览中...' : '预览'}
                                            </Button>
                                        </div>
                                    </div>
                                    <textarea
                                        value={querySql}
                                        onChange={(event) => setQuerySql(event.target.value)}
                                        className="h-full min-h-0 w-full resize-none overflow-auto border-0 bg-white p-4 font-mono text-[12px] leading-5 text-[#23332f] outline-none"
                                        spellCheck={false}
                                        placeholder="SELECT ..."
                                    />
                                </section>

                                <section className="min-h-0 bg-[#fafafa] p-3">
                                    <div className="mb-2 flex items-center justify-between gap-2">
                                        <div className="text-xs font-semibold text-[#243a35]">预览结果</div>
                                        {previewResult?.executed ? <span className="text-[11px] text-[#60736f]">返回 {previewResult.rowCount} 行</span> : null}
                                    </div>
                                    <DatasetPreviewResult result={previewResult ?? null} loading={previewDataset.isPending} />
                                </section>
                            </main>
                        </div>

                        <DialogFooter className="border-t border-[#eeeeee] px-5 py-3">
                            <Button variant="outline" className="h-9 border-[#dedede]" onClick={() => onOpenChange(false)}>
                                关闭
                            </Button>
                        </DialogFooter>
                    </div>
                ) : null}
            </DialogContent>
        </Dialog>
    );
}

function DatasetPreviewResult({
    result,
    loading,
}: {
    result: ReturnType<typeof usePreviewFrReportDataset>['data'] | null;
    loading: boolean;
}) {
    if (loading) {
        return <div className="grid h-[168px] place-items-center rounded-lg border border-[#eeeeee] bg-white text-xs text-[#60736f]">正在执行只读预览...</div>;
    }
    if (!result) {
        return <div className="grid h-[168px] place-items-center rounded-lg border border-[#eeeeee] bg-white text-xs text-[#60736f]">点击“预览”后展示样例数据。</div>;
    }
    if (result.needsConnection || result.errors.length > 0) {
        return (
            <div className="h-[168px] overflow-auto rounded-lg border border-[#f0d0d0] bg-[#fffafa] p-3 text-xs leading-5 text-[#9b3a3a]">
                {result.errors.map((error) => (
                    <div key={error}>{error}</div>
                ))}
            </div>
        );
    }
    if (result.columns.length === 0) {
        return <div className="grid h-[168px] place-items-center rounded-lg border border-[#eeeeee] bg-white text-xs text-[#60736f]">预览成功，但没有返回列。</div>;
    }
    return (
        <div className="h-[168px] overflow-auto rounded-lg border border-[#eeeeee] bg-white">
            <table className="min-w-full border-collapse text-left text-[11px]">
                <thead className="sticky top-0 bg-[#f6fbfa] text-[#243a35]">
                    <tr>
                        {result.columns.map((column) => (
                            <th key={column} className="whitespace-nowrap border-b border-r border-[#eeeeee] px-2 py-1.5 font-semibold last:border-r-0">
                                {column}
                            </th>
                        ))}
                    </tr>
                </thead>
                <tbody>
                    {result.sampleRows.map((row, rowIndex) => (
                        <tr key={rowIndex} className="odd:bg-white even:bg-[#fafafa]">
                            {result.columns.map((column) => (
                                <td key={column} className="max-w-48 truncate border-b border-r border-[#eeeeee] px-2 py-1.5 last:border-r-0" title={String(row[column] ?? '')}>
                                    {String(row[column] ?? '')}
                                </td>
                            ))}
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}

function VisibilityPreferenceDialog({
    open,
    onOpenChange,
    files,
    selectedPaths,
    loading,
    saving,
    onTogglePath,
    onShowAll,
    onSave,
}: {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    files: FrReportFileRead[];
    selectedPaths: Set<string>;
    loading: boolean;
    saving: boolean;
    onTogglePath: (path: string) => void;
    onShowAll: () => void;
    onSave: () => void;
}) {
    const [keyword, setKeyword] = useState('');
    const tree = useMemo(() => buildReportFileTree(files), [files]);
    const filteredTree = useMemo(() => filterReportFileTree(tree, keyword), [keyword, tree]);
    const selectedCount = selectedPaths.size;
    const visibleCount = filteredTree.fileCount;

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="max-h-[86vh] overflow-hidden rounded-xl border-[#dfe7e5] bg-white p-0 sm:max-w-4xl">
                <DialogHeader className="border-b border-[#eeeeee] px-5 py-4">
                    <DialogTitle className="text-base font-semibold text-[#243a35]">选择显示的报表范围</DialogTitle>
                    <DialogDescription className="text-xs text-[#6d817d]">
                        可选择文件夹或单个报表。未选择任何路径时显示全部；保存后只展示已选择范围。
                    </DialogDescription>
                </DialogHeader>

                <div className="grid min-h-0 grid-cols-[260px_minmax(0,1fr)]">
                    <aside className="border-r border-[#eeeeee] bg-[#fafafa] p-4 text-xs text-[#60736f]">
                        <div className="rounded-lg border border-[#e5e5e5] bg-white p-3">
                            <div className="font-semibold text-[#243a35]">当前策略</div>
                            <div className="mt-2 leading-5">
                                {selectedCount === 0 ? '显示全部报表，不做用户级过滤。' : `仅显示 ${selectedCount} 个已选择的文件夹或报表路径。`}
                            </div>
                        </div>
                        <div className="mt-3 rounded-lg border border-[#e5e5e5] bg-white p-3 leading-5">
                            选择上级文件夹会包含它下面全部报表；如果只想显示少量报表，请不要勾选上级目录，直接勾选具体报表。
                        </div>
                    </aside>

                    <div className="min-h-0 p-4">
                        <div className="mb-3 flex items-center justify-between gap-3 text-xs text-[#60736f]">
                            <div className="relative min-w-0 flex-1">
                                <Search className="absolute left-3 top-1/2 size-3.5 -translate-y-1/2 text-[#8aa19c]" />
                                <Input
                                    value={keyword}
                                    onChange={(event) => setKeyword(event.target.value)}
                                    className="h-9 border-[#dedede] bg-white pl-8 text-xs"
                                    placeholder="搜索文件夹或报表，列表会直接定位到匹配项"
                                />
                            </div>
                            <span className="shrink-0">
                                {keyword.trim() ? `匹配：${visibleCount}` : `全量：${files.length}`} · 已选：{selectedCount}
                            </span>
                        </div>
                        <div className="max-h-[56vh] overflow-auto rounded-lg border border-[#eeeeee] bg-white p-2">
                            {loading ? (
                                <div className="px-3 py-6 text-sm text-[#6d817d]">正在读取全量报表目录...</div>
                            ) : keyword.trim() && visibleCount === 0 ? (
                                <div className="px-3 py-6 text-sm text-[#6d817d]">没有找到匹配的文件夹或报表。</div>
                            ) : (
                                <>
                                    {filteredTree.folders.map((folder) => (
                                        <VisibilityTreeFolderNode
                                            key={folder.path}
                                            folder={folder}
                                            level={0}
                                            selectedPaths={selectedPaths}
                                            onTogglePath={onTogglePath}
                                        />
                                    ))}
                                    {filteredTree.files.map((file) => (
                                        <VisibilityTreeFileNode
                                            key={file.objectPath}
                                            file={file}
                                            level={0}
                                            selectedPaths={selectedPaths}
                                            onTogglePath={onTogglePath}
                                        />
                                    ))}
                                </>
                            )}
                        </div>
                    </div>
                </div>

                <DialogFooter className="border-t border-[#eeeeee] px-5 py-4">
                    <Button type="button" variant="outline" className="border-[#dedede]" disabled={saving} onClick={onShowAll}>
                        全部显示
                    </Button>
                    <Button type="button" className="bg-[#0f8f7b] text-white hover:bg-[#0b7c6b]" disabled={saving || loading} onClick={onSave}>
                        {saving ? '保存中...' : '保存显示范围'}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

function VisibilityTreeFolderNode({
    folder,
    level,
    selectedPaths,
    onTogglePath,
}: {
    folder: ReportTreeFolder;
    level: number;
    selectedPaths: Set<string>;
    onTogglePath: (path: string) => void;
}) {
    const checked = isVisiblePathCovered(folder.path, selectedPaths);

    return (
        <div>
            <label
                className={cn(
                    'flex cursor-pointer items-center gap-2 rounded-md py-1.5 pr-2 text-xs text-[#444444] hover:bg-[#f7f7f7]',
                    checked && 'text-[#0f8f7b]',
                )}
                style={{ paddingLeft: level * 14 + 6 }}
            >
                <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => onTogglePath(folder.path)}
                    className="size-3.5 accent-[#0f8f7b]"
                />
                <Folder className="size-3.5 shrink-0 text-[#8aa19c]" />
                <span className="min-w-0 flex-1 truncate font-semibold">{folder.name}</span>
                <span className="shrink-0 rounded-full bg-[#f2f7f6] px-1.5 py-0.5 text-[10px] text-[#0c7a68]">{folder.fileCount}</span>
            </label>
            {folder.folders.map((childFolder) => (
                <VisibilityTreeFolderNode
                    key={childFolder.path}
                    folder={childFolder}
                    level={level + 1}
                    selectedPaths={selectedPaths}
                    onTogglePath={onTogglePath}
                />
            ))}
            {folder.files.map((file) => (
                <VisibilityTreeFileNode
                    key={file.objectPath}
                    file={file}
                    level={level + 1}
                    selectedPaths={selectedPaths}
                    onTogglePath={onTogglePath}
                />
            ))}
        </div>
    );
}

function VisibilityTreeFileNode({
    file,
    level,
    selectedPaths,
    onTogglePath,
}: {
    file: FrReportFileRead;
    level: number;
    selectedPaths: Set<string>;
    onTogglePath: (path: string) => void;
}) {
    const path = formatReportPath(file.reportPath);
    const checked = isVisiblePathCovered(path, selectedPaths);

    return (
        <label
            className={cn(
                'flex cursor-pointer items-center gap-2 rounded-md py-1.5 pr-2 text-xs text-[#666666] hover:bg-[#f7f7f7]',
                checked && 'text-[#0f8f7b]',
            )}
            style={{ paddingLeft: level * 14 + 24 }}
        >
            <input
                type="checkbox"
                checked={checked}
                onChange={() => onTogglePath(path)}
                className="size-3.5 accent-[#0f8f7b]"
            />
            <FileSpreadsheet className="size-3.5 shrink-0 text-[#0f8f7b]" />
            <span className="min-w-0 flex-1 truncate font-medium">{file.fileName}</span>
        </label>
    );
}

function toggleVisiblePath(current: Set<string>, path: string) {
    const next = new Set(current);
    if (next.has(path)) {
        next.delete(path);
        return next;
    }
    for (const selectedPath of Array.from(next)) {
        if (selectedPath.startsWith(`${path}/`)) {
            next.delete(selectedPath);
        }
    }
    next.add(path);
    return next;
}

function isVisiblePathCovered(path: string, selectedPaths: Set<string>) {
    return Array.from(selectedPaths).some((selectedPath) => path === selectedPath || path.startsWith(`${selectedPath}/`));
}

function mergedCoveredCells(cells: FrReportCellRead[]) {
    const covered = new Set<string>();
    for (const cell of cells) {
        for (let row = cell.row; row < cell.row + cell.rowSpan; row += 1) {
            for (let column = cell.column; column < cell.column + cell.colSpan; column += 1) {
                if (row === cell.row && column === cell.column) {
                    continue;
                }
                covered.add(`${row}:${column}`);
            }
        }
    }
    return covered;
}

function cellStyle(cell?: FrReportCellRead) {
    if (!cell) {
        return {};
    }
    const style = cell.style ?? {};
    return {
        color: safeCssColor(style.color),
        backgroundColor: safeCssColor(style.backgroundColor),
        fontSize: style.fontSize ? `${Math.min(Math.max(style.fontSize, 10), 18)}px` : undefined,
        fontFamily: style.fontFamily ?? undefined,
        fontWeight: style.bold ? 600 : undefined,
        fontStyle: style.italic ? 'italic' : undefined,
        textDecoration: style.underline ? 'underline' : undefined,
        justifyContent: alignToFlex(style.horizontalAlign),
        alignItems: alignToFlex(style.verticalAlign) ?? 'center',
        borderTop: style.borderTop && cell.row === 1 ? `1px solid ${safeCssColor(style.borderColor) ?? '#bdccd6'}` : undefined,
        borderRight: style.borderRight ? `1px solid ${safeCssColor(style.borderColor) ?? '#bdccd6'}` : undefined,
        borderBottom: style.borderBottom ? `1px solid ${safeCssColor(style.borderColor) ?? '#bdccd6'}` : undefined,
        borderLeft: style.borderLeft && cell.column === 1 ? `1px solid ${safeCssColor(style.borderColor) ?? '#bdccd6'}` : undefined,
    };
}

function cellStyleFromPatch(style?: Partial<FrReportCellRead['style']>) {
    if (!style) {
        return {};
    }
    const borderColor = safeCssColor(style.borderColor) ?? '#0f8f7b';
    return {
        color: safeCssColor(style.color),
        backgroundColor: safeCssColor(style.backgroundColor),
        fontSize: style.fontSize ? `${Math.min(Math.max(style.fontSize, 10), 22)}px` : undefined,
        fontFamily: style.fontFamily ?? undefined,
        fontWeight: style.bold ? 700 : undefined,
        fontStyle: style.italic ? 'italic' : undefined,
        textDecoration: style.underline ? 'underline' : undefined,
        justifyContent: alignToFlex(style.horizontalAlign),
        alignItems: alignToFlex(style.verticalAlign),
        borderTop: style.borderTop ? `1px solid ${borderColor}` : undefined,
        borderRight: style.borderRight ? `1px solid ${borderColor}` : undefined,
        borderBottom: style.borderBottom ? `1px solid ${borderColor}` : undefined,
        borderLeft: style.borderLeft ? `1px solid ${borderColor}` : undefined,
    };
}

function toAiPreviewPatch(value: Record<string, unknown>): AiPreviewPatch {
    const cells = value.cells;
    if (!cells || typeof cells !== 'object' || Array.isArray(cells)) {
        return {};
    }
    return { cells: cells as Record<string, AiPreviewCellPatch> };
}

function shouldWrapCell(cell: FrReportCellRead | undefined, content: string) {
    if (!cell) {
        return false;
    }
    return cell.row <= 4 || cell.rowSpan > 1 || cell.colSpan > 1 || content.length > 18;
}

function safeCssColor(value?: string | null) {
    if (!value) {
        return undefined;
    }
    const text = value.trim();
    if (/^#([0-9a-f]{3}|[0-9a-f]{6}|[0-9a-f]{8})$/i.test(text) || /^rgba?\([0-9.,%\s]+\)$/i.test(text)) {
        return text;
    }
    if (/^[a-z]+$/i.test(text)) {
        return text;
    }
    return undefined;
}

function alignToFlex(value?: string | null) {
    const text = value?.toLowerCase();
    if (text === 'center' || text === 'middle') {
        return 'center';
    }
    if (text === 'right' || text === 'bottom') {
        return 'flex-end';
    }
    return undefined;
}

function formatExpandDirection(value?: string | null) {
    const text = value?.toLowerCase();
    if (text === 'vertical') {
        return '纵向';
    }
    if (text === 'horizontal') {
        return '横向';
    }
    if (text === 'none') {
        return '不扩展';
    }
    return value || '未配置';
}

function clampSize(value: number | null | undefined, min: number, max: number) {
    if (!value) {
        return undefined;
    }
    return Math.min(Math.max(value, min), max);
}

function columnLabel(index: number) {
    let current = index;
    let label = '';
    while (current > 0) {
        const remainder = (current - 1) % 26;
        label = String.fromCharCode(65 + remainder) + label;
        current = Math.floor((current - 1) / 26);
    }
    return label || 'A';
}

function formatReportPath(reportPath: string) {
    return reportPath.replace(/^reportlets\//, '');
}

function listReportFolders(files: FrReportFileRead[]) {
    const folders = new Set<string>();
    for (const file of files) {
        const objectPath = file.objectPath || '';
        const reportPath = file.reportPath || '';
        const normalized = objectPath.startsWith('webroot/APP/reportlets/')
            ? objectPath
            : `webroot/APP/${reportPath.replace(/^reportlets\//, 'reportlets/')}`;
        const folder = normalized.split('/').slice(0, -1).join('/');
        if (folder.startsWith('webroot/APP/reportlets')) {
            folders.add(folder);
        }
    }
    folders.add('webroot/APP/reportlets/AI生成报表');
    return Array.from(folders).sort((left, right) => left.localeCompare(right, 'zh-Hans-CN'));
}

function extractNewReportContext(text: string) {
    const normalized = text.trim();
    const reportName =
        matchFirst(normalized, [
            /报表(?:名称|名)?[：:]\s*([^\n，,；;]+)/,
            /(?:叫|命名为|名称为)\s*([^\n，,；;]+?报表)/,
        ]) ?? undefined;
    const targetFolder =
        matchFirst(normalized, [
            /(?:保存到|放到|生成到|目录)[：:\s]*((?:webroot\/APP\/reportlets|reportlets)\/[^\s，,；;]+)/i,
            /((?:webroot\/APP\/reportlets|reportlets)\/[^\s，,；;]+)/i,
        ]) ?? undefined;
    const tableMatches = Array.from(
        normalized.matchAll(/\b(?:[A-Za-z_][\w]*\.)?[A-Za-z_][\w]*(?:\s*,\s*(?:[A-Za-z_][\w]*\.)?[A-Za-z_][\w]*)*\b/g),
    )
        .map((match) => match[0])
        .filter((value) => /[_\.]/.test(value) && !value.toLowerCase().includes('webroot') && !value.toLowerCase().includes('reportlets'))
        .slice(0, 8);
    const sourceTablesText = tableMatches.length > 0 ? tableMatches.join('\n') : undefined;
    return { reportName, targetFolder: normalizeReportFolder(targetFolder), sourceTablesText };
}

function matchFirst(text: string, patterns: RegExp[]) {
    for (const pattern of patterns) {
        const matched = text.match(pattern);
        const value = matched?.[1]?.trim();
        if (value) {
            return value;
        }
    }
    return null;
}

function normalizeReportFolder(value?: string) {
    if (!value) {
        return undefined;
    }
    const trimmed = value.replace(/[。.!！?？]+$/, '').replace(/\/+$/, '');
    if (trimmed.startsWith('webroot/APP/reportlets')) {
        return trimmed;
    }
    if (trimmed.startsWith('reportlets/')) {
        return `webroot/APP/${trimmed}`;
    }
    return trimmed;
}

function isGenerateReportCommand(text: string) {
    const normalized = text.replace(/\s/g, '');
    return /开始生成|生成报表|可以生成|直接生成|开始做|开始吧/.test(normalized);
}

function isSaveCptCommand(text: string) {
    const normalized = text.replace(/\s/g, '').toLowerCase();
    return normalized.includes('保存成cpt') || normalized.includes('生成cpt') || normalized.includes('保存cpt');
}

function isFreshReportRequest(text: string) {
    const normalized = text.replace(/\s/g, '');
    return /^(帮我|我要|请|直接)?(做|新建|生成|创建|设计)(一个|一张)?/.test(normalized) || /报表名[：:]/.test(text);
}

function agentToolLabel(toolName: string) {
    const labels: Record<string, string> = {
        ai_requirement_review: 'AI 需求理解',
        review_requirement: '需求预检',
        generate_sql_with_preview: 'SQL 与数据预览',
        generate_report_dsl: '报表设计',
        generate_cpt: 'CPT 与版本控制',
    };
    return labels[toolName] ?? toolName;
}

function buildReportFileTree(files: FrReportFileRead[]) {
    const root: ReportTreeFolder = {
        name: '报表',
        path: '',
        fileCount: 0,
        folders: [],
        files: [],
    };
    const folderIndex = new Map<string, ReportTreeFolder>();

    for (const file of files) {
        const pathParts = formatReportPath(file.reportPath).split('/').filter(Boolean);
        const folderParts = pathParts.slice(0, -1);
        let currentFolder = root;
        let currentPath = '';

        for (const folderName of folderParts) {
            currentPath = currentPath ? `${currentPath}/${folderName}` : folderName;
            let nextFolder = folderIndex.get(currentPath);
            if (!nextFolder) {
                nextFolder = {
                    name: folderName,
                    path: currentPath,
                    fileCount: 0,
                    folders: [],
                    files: [],
                };
                folderIndex.set(currentPath, nextFolder);
                currentFolder.folders.push(nextFolder);
            }
            currentFolder = nextFolder;
        }

        currentFolder.files.push(file);
    }

    sortAndCountReportFolder(root);
    return root;
}

function sortAndCountReportFolder(folder: ReportTreeFolder) {
    folder.folders.sort((left, right) => left.name.localeCompare(right.name, 'zh-Hans-CN'));
    folder.files.sort((left, right) => left.fileName.localeCompare(right.fileName, 'zh-Hans-CN'));
    folder.fileCount = folder.files.length + folder.folders.reduce((total, child) => total + sortAndCountReportFolder(child), 0);
    return folder.fileCount;
}

function filterReportFileTree(folder: ReportTreeFolder, keyword: string): ReportTreeFolder {
    const text = keyword.trim().toLowerCase();
    if (!text) {
        return folder;
    }
    const nextFolders = folder.folders
        .map((child) => filterReportFileTree(child, text))
        .filter((child) => child.fileCount > 0 || child.name.toLowerCase().includes(text) || child.path.toLowerCase().includes(text));
    const nextFiles = folder.files.filter((file) => {
        const path = formatReportPath(file.reportPath).toLowerCase();
        return file.fileName.toLowerCase().includes(text) || path.includes(text) || file.objectPath.toLowerCase().includes(text);
    });
    const folderMatches = folder.name.toLowerCase().includes(text) || folder.path.toLowerCase().includes(text);
    const visibleFiles = folderMatches ? folder.files : nextFiles;
    const visibleFolders = folderMatches ? folder.folders : nextFolders;
    return {
        ...folder,
        folders: visibleFolders,
        files: visibleFiles,
        fileCount: visibleFiles.length + visibleFolders.reduce((total, child) => total + child.fileCount, 0),
    };
}

function reportFolderHasSelectedFile(folder: ReportTreeFolder, selectedPath: string | null): boolean {
    if (!selectedPath) {
        return false;
    }
    return folder.files.some((file) => file.objectPath === selectedPath) || folder.folders.some((child) => reportFolderHasSelectedFile(child, selectedPath));
}

function PropertyPanel({
    selectedCell,
    column,
    row,
    cell,
    sheet,
}: {
    selectedCell: string;
    column: string;
    row: string;
    cell: FrReportCellRead | null;
    sheet: FrReportSheetRead | null;
}) {
    const binding = cell?.fieldBinding;
    const dataColumn = cell?.dataColumn;
    const widget = cell?.widget;
    const submitBindings = cell?.submitBindings ?? [];
    const style = cell?.style;
    const [advancedDialogOpen, setAdvancedDialogOpen] = useState(false);
    const canOpenAdvanced = Boolean(dataColumn || widget || submitBindings.length > 0 || binding);

    return (
        <div className="space-y-4">
            <section className="rounded-xl border border-[#e5e5e5] bg-white p-4">
                <div className="mb-3 flex items-center gap-2">
                    <Settings2 className="size-4 text-[#0f8f7b]" />
                    <h2 className="text-sm font-semibold text-[#243a35]">单元格属性</h2>
                </div>
                <div className="grid grid-cols-2 gap-3 text-xs">
                    <InfoItem label="当前单元格" value={selectedCell} />
                    <InfoItem label="列" value={column} />
                    <InfoItem label="行" value={row} />
                    <InfoItem label="类型" value={binding ? '数据绑定' : cell?.formula ? '公式' : cell?.text ? '文本' : '空白'} />
                    <InfoItem label="合并" value={cell ? `${cell.rowSpan} 行 x ${cell.colSpan} 列` : '无'} />
                    <InfoItem label="扩展" value={cell?.expandDirection || '未配置'} />
                    <InfoItem label="来源" value={cell?.rawPath || '未识别'} />
                </div>
                <Button
                    type="button"
                    variant="outline"
                    className="mt-3 h-8 w-full border-[#d8ebe6] bg-[#f6fbfa] text-xs text-[#0c7a68] hover:bg-[#eef8f5]"
                    disabled={!canOpenAdvanced}
                    onClick={() => setAdvancedDialogOpen(true)}
                >
                    打开完整属性
                </Button>
            </section>

            <section className="rounded-xl border border-[#e5e5e5] bg-white p-4">
                <div className="mb-3 flex items-center gap-2">
                    <Database className="size-4 text-[#0f8f7b]" />
                    <h2 className="text-sm font-semibold text-[#243a35]">数据绑定</h2>
                </div>
                {binding ? (
                    <div className="space-y-2">
                        <div className="rounded-lg border border-[#eeeeee] bg-[#fafafa] px-3 py-2 text-xs text-[#555555]">
                            {binding.dataset ? `${binding.dataset}.${binding.field}` : binding.field}
                        </div>
                        <div className="rounded-lg border border-[#eeeeee] bg-white px-3 py-2 font-mono text-[11px] text-[#60736f]">
                            {binding.expression}
                        </div>
                    </div>
                ) : (
                    <div className="rounded-lg border border-[#eeeeee] bg-[#fafafa] px-3 py-3 text-xs text-[#6d817d]">当前单元格暂无字段绑定。</div>
                )}
            </section>

            <section className="rounded-xl border border-[#e5e5e5] bg-white p-4">
                <div className="mb-3 flex items-center gap-2">
                    <ListTree className="size-4 text-[#0f8f7b]" />
                    <h2 className="text-sm font-semibold text-[#243a35]">数据列属性</h2>
                </div>
                {dataColumn ? (
                    <div className="space-y-3 text-xs">
                        <div className="grid grid-cols-2 gap-2">
                            <InfoItem label="数据集" value={dataColumn.dataset || '未识别'} />
                            <InfoItem label="数据列" value={dataColumn.field || '未识别'} />
                            <InfoItem label="聚合" value={dataColumn.aggregation || '普通'} />
                            <InfoItem label="扩展方向" value={formatExpandDirection(dataColumn.expandDirection)} />
                            <InfoItem label="横向可伸展" value={dataColumn.horizontalExtendable ? '是' : '否'} />
                            <InfoItem label="纵向可伸展" value={dataColumn.verticalExtendable ? '是' : '否'} />
                        </div>
                        {dataColumn.customDisplay ? (
                            <div className="rounded-lg border border-[#eeeeee] bg-white px-3 py-2 font-mono text-[11px] text-[#60736f]">
                                {dataColumn.customDisplay}
                            </div>
                        ) : null}
                        {dataColumn.conditions.length > 0 ? (
                            <div className="space-y-1">
                                {dataColumn.conditions.map((condition, index) => (
                                    <div key={`${condition.column}-${index}`} className="rounded-lg bg-[#fafafa] px-3 py-2 text-[#4b5f5b] ring-1 ring-[#eeeeee]">
                                        {condition.join ? `${condition.join} ` : ''}
                                        {condition.column || '字段'} {condition.operator || '条件'} {condition.value || '空值'}
                                    </div>
                                ))}
                            </div>
                        ) : null}
                    </div>
                ) : (
                    <div className="rounded-lg border border-[#eeeeee] bg-[#fafafa] px-3 py-3 text-xs text-[#6d817d]">当前单元格不是数据列。</div>
                )}
            </section>

            <section className="rounded-xl border border-[#e5e5e5] bg-white p-4">
                <div className="mb-3 flex items-center gap-2">
                    <SlidersHorizontal className="size-4 text-[#0f8f7b]" />
                    <h2 className="text-sm font-semibold text-[#243a35]">单元格控件</h2>
                </div>
                {widget ? (
                    <div className="grid grid-cols-2 gap-2 text-xs">
                        <InfoItem label="控件类型" value={widget.widgetType || '未识别'} />
                        <InfoItem label="控件名称" value={widget.widgetName || '未命名'} />
                        <InfoItem label="控件类" value={widget.widgetClass || '未识别'} />
                        <InfoItem label="说明" value={widget.description || '无'} />
                    </div>
                ) : (
                    <div className="rounded-lg border border-[#eeeeee] bg-[#fafafa] px-3 py-3 text-xs text-[#6d817d]">当前单元格没有配置控件。</div>
                )}
            </section>

            <section className="rounded-xl border border-[#e5e5e5] bg-white p-4">
                <div className="mb-3 flex items-center gap-2">
                    <Save className="size-4 text-[#0f8f7b]" />
                    <h2 className="text-sm font-semibold text-[#243a35]">填报绑定</h2>
                </div>
                {submitBindings.length > 0 ? (
                    <div className="space-y-2">
                        {submitBindings.map((submit, index) => (
                            <div key={`${submit.name}-${index}`} className="rounded-lg border border-[#eeeeee] bg-[#fafafa] p-3 text-xs text-[#4b5f5b]">
                                <div className="mb-2 font-semibold text-[#243a35]">
                                    {submit.name || '未命名提交'} · {submit.database || '未知库'}
                                    {submit.tableName ? `.${submit.schemaName || 'dbo'}.${submit.tableName}` : ''}
                                </div>
                                <div className="space-y-1">
                                    {submit.columns.map((column) => (
                                        <div key={`${column.column}-${column.cell || column.value}`} className="flex items-center justify-between gap-2 rounded-md bg-white px-2 py-1 ring-1 ring-[#eeeeee]">
                                            <span>{column.isKey ? '主键' : '值'} · {column.column}</span>
                                            <span className="max-w-36 truncate text-[#60736f]">{column.cell || column.value || '当前格'}</span>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        ))}
                    </div>
                ) : (
                    <div className="rounded-lg border border-[#eeeeee] bg-[#fafafa] px-3 py-3 text-xs text-[#6d817d]">当前单元格没有填报写回绑定。</div>
                )}
            </section>

            <section className="rounded-xl border border-[#e5e5e5] bg-white p-4">
                <div className="mb-3 flex items-center gap-2">
                    <SlidersHorizontal className="size-4 text-[#0f8f7b]" />
                    <h2 className="text-sm font-semibold text-[#243a35]">版式规则</h2>
                </div>
                <div className="grid gap-2">
                    <RuleItem icon={Columns3} title="工作表列数" desc={`${sheet?.columnCount ?? DEFAULT_CANVAS_COLUMNS} 列`} />
                    <RuleItem icon={Rows3} title="工作表行数" desc={`${sheet?.rowCount ?? DEFAULT_CANVAS_ROWS} 行`} />
                    <RuleItem icon={Table2} title="合并区域" desc={`${sheet?.merges.length ?? 0} 个`} />
                </div>
            </section>

            <section className="rounded-xl border border-[#e5e5e5] bg-white p-4">
                <div className="mb-3 flex items-center gap-2">
                    <Braces className="size-4 text-[#0f8f7b]" />
                    <h2 className="text-sm font-semibold text-[#243a35]">样式摘要</h2>
                </div>
                <pre className="overflow-auto rounded-lg bg-[#12352f] p-3 text-[11px] leading-5 text-[#d7fff4]">
{JSON.stringify(
    {
        styleName: style?.styleName ?? null,
        fontSize: style?.fontSize ?? null,
        bold: style?.bold ?? null,
        backgroundColor: style?.backgroundColor ?? null,
        borderColor: style?.borderColor ?? null,
        borderTop: style?.borderTop ?? null,
        borderRight: style?.borderRight ?? null,
        borderBottom: style?.borderBottom ?? null,
        borderLeft: style?.borderLeft ?? null,
        horizontalAlign: style?.horizontalAlign ?? null,
    },
    null,
    2,
)}
                </pre>
            </section>

            <CellAdvancedPropertyDialog
                open={advancedDialogOpen}
                onOpenChange={setAdvancedDialogOpen}
                selectedCell={selectedCell}
                cell={cell}
            />
        </div>
    );
}

type CellAdvancedTab = 'data-basic' | 'data-filter' | 'data-advanced' | 'submit' | 'validation' | 'shortcut';

function CellAdvancedPropertyDialog({
    open,
    onOpenChange,
    selectedCell,
    cell,
}: {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    selectedCell: string;
    cell: FrReportCellRead | null;
}) {
    const [activeTab, setActiveTab] = useState<CellAdvancedTab>('data-basic');
    const dataColumn = cell?.dataColumn ?? null;
    const widget = cell?.widget ?? null;
    const submitBindings = cell?.submitBindings ?? [];
    const tabs: { key: CellAdvancedTab; label: string }[] = [
        { key: 'data-basic', label: '数据列-基本' },
        { key: 'data-filter', label: '数据列-过滤' },
        { key: 'data-advanced', label: '数据列-高级' },
        { key: 'submit', label: '填报-提交' },
        { key: 'validation', label: '填报-数据校验' },
        { key: 'shortcut', label: '填报-快捷设置' },
    ];

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="max-h-[86vh] max-w-4xl overflow-hidden p-0">
                <DialogHeader className="border-b border-[#e5e5e5] px-5 py-4">
                    <DialogTitle className="text-base font-semibold text-[#243a35]">单元格完整属性：{selectedCell}</DialogTitle>
                    <DialogDescription className="text-xs text-[#60736f]">
                        按 FineReport 弹窗结构展示当前已解析的数据列、控件和填报写回配置。
                    </DialogDescription>
                </DialogHeader>

                <div className="grid min-h-0 grid-cols-[180px_minmax(0,1fr)]">
                    <div className="border-r border-[#e5e5e5] bg-[#fafafa] p-3">
                        <div className="space-y-1">
                            {tabs.map((tab) => (
                                <button
                                    key={tab.key}
                                    type="button"
                                    className={cn(
                                        'w-full rounded-md px-3 py-2 text-left text-xs transition',
                                        activeTab === tab.key
                                            ? 'bg-white font-semibold text-[#0c7a68] shadow-sm ring-1 ring-[#d8ebe6]'
                                            : 'text-[#52635f] hover:bg-white hover:text-[#0c7a68]',
                                    )}
                                    onClick={() => setActiveTab(tab.key)}
                                >
                                    {tab.label}
                                </button>
                            ))}
                        </div>
                    </div>

                    <div className="max-h-[62vh] overflow-auto p-5">
                        {activeTab === 'data-basic' ? <DataColumnBasicPanel dataColumn={dataColumn} cell={cell} /> : null}
                        {activeTab === 'data-filter' ? <DataColumnFilterPanel dataColumn={dataColumn} /> : null}
                        {activeTab === 'data-advanced' ? <DataColumnAdvancedPanel dataColumn={dataColumn} widget={widget} /> : null}
                        {activeTab === 'submit' ? <SubmitPropertyPanel submitBindings={submitBindings} /> : null}
                        {activeTab === 'validation' ? <ValidationPropertyPanel submitBindings={submitBindings} /> : null}
                        {activeTab === 'shortcut' ? <ShortcutPropertyPanel widget={widget} submitBindings={submitBindings} /> : null}
                    </div>
                </div>

                <DialogFooter className="border-t border-[#e5e5e5] px-5 py-3">
                    <Button type="button" variant="outline" className="h-8" onClick={() => onOpenChange(false)}>
                        关闭
                    </Button>
                    <Button type="button" className="h-8 bg-[#0f8f7b] text-white hover:bg-[#0b7c6b]" disabled>
                        应用修改
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

function DataColumnBasicPanel({ dataColumn, cell }: { dataColumn: FrReportCellRead['dataColumn'] | null; cell: FrReportCellRead | null }) {
    if (!dataColumn) {
        return <EmptyPropertyState text="当前单元格没有数据列配置。" />;
    }
    return (
        <div className="space-y-4">
            <PropertyGroup title="选择数据列">
                <div className="grid grid-cols-2 gap-3 text-xs">
                    <InfoItem label="数据集" value={dataColumn.dataset || '未识别'} />
                    <InfoItem label="数据列" value={dataColumn.field || '未识别'} />
                    <InfoItem label="表达式" value={cell?.fieldBinding?.expression || cell?.text || '无'} />
                    <InfoItem label="左父格" value={dataColumn.parentCell || '默认'} />
                </div>
            </PropertyGroup>
            <PropertyGroup title="数据设置">
                <div className="grid grid-cols-3 gap-3 text-xs">
                    <InfoItem label="类型" value={dataColumn.aggregation ? '分组' : '列表'} />
                    <InfoItem label="聚合" value={dataColumn.aggregation || '普通'} />
                    <InfoItem label="扩展方向" value={formatExpandDirection(dataColumn.expandDirection)} />
                </div>
            </PropertyGroup>
        </div>
    );
}

function DataColumnFilterPanel({ dataColumn }: { dataColumn: FrReportCellRead['dataColumn'] | null }) {
    if (!dataColumn) {
        return <EmptyPropertyState text="当前单元格没有可展示的数据列过滤条件。" />;
    }
    return (
        <div className="space-y-4">
            <PropertyGroup title="父格条件">
                <label className="flex items-center gap-2 text-xs text-[#4b5f5b]">
                    <input type="checkbox" checked readOnly className="size-3.5 accent-[#0f8f7b]" />
                    将父格作为过滤条件
                </label>
            </PropertyGroup>
            <PropertyGroup title="普通条件">
                {dataColumn.conditions.length > 0 ? (
                    <div className="overflow-hidden rounded-lg border border-[#e5e5e5]">
                        <table className="w-full text-left text-xs">
                            <thead className="bg-[#f5f8f7] text-[#52635f]">
                                <tr>
                                    <th className="px-3 py-2 font-medium">连接</th>
                                    <th className="px-3 py-2 font-medium">字段</th>
                                    <th className="px-3 py-2 font-medium">操作符</th>
                                    <th className="px-3 py-2 font-medium">值</th>
                                </tr>
                            </thead>
                            <tbody>
                                {dataColumn.conditions.map((condition, index) => (
                                    <tr key={`${condition.column}-${index}`} className="border-t border-[#eeeeee]">
                                        <td className="px-3 py-2">{condition.join || 'AND'}</td>
                                        <td className="px-3 py-2 font-mono">{condition.column || '字段'}</td>
                                        <td className="px-3 py-2">{condition.operator || '等于'}</td>
                                        <td className="px-3 py-2">{condition.value || '空值'}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                ) : (
                    <EmptyPropertyState text="没有解析到过滤条件。" />
                )}
            </PropertyGroup>
        </div>
    );
}

function DataColumnAdvancedPanel({
    dataColumn,
    widget,
}: {
    dataColumn: FrReportCellRead['dataColumn'] | null;
    widget: FrReportCellRead['widget'] | null;
}) {
    return (
        <div className="space-y-4">
            <PropertyGroup title="自定义显示">
                <div className="rounded-lg border border-[#eeeeee] bg-white px-3 py-2 font-mono text-xs text-[#52635f]">
                    {dataColumn?.customDisplay || '未配置'}
                </div>
            </PropertyGroup>
            <PropertyGroup title="可伸展性">
                <div className="grid grid-cols-2 gap-3 text-xs">
                    <InfoItem label="横向可伸展" value={dataColumn?.horizontalExtendable ? '是' : '否'} />
                    <InfoItem label="纵向可伸展" value={dataColumn?.verticalExtendable ? '是' : '否'} />
                </div>
            </PropertyGroup>
            <PropertyGroup title="单元格控件">
                {widget ? (
                    <div className="grid grid-cols-2 gap-3 text-xs">
                        <InfoItem label="控件类型" value={widget.widgetType || '未识别'} />
                        <InfoItem label="控件名称" value={widget.widgetName || '未命名'} />
                        <InfoItem label="控件类" value={widget.widgetClass || '未识别'} />
                        <InfoItem label="说明" value={widget.description || '无'} />
                    </div>
                ) : (
                    <EmptyPropertyState text="当前单元格没有配置控件。" />
                )}
            </PropertyGroup>
        </div>
    );
}

function SubmitPropertyPanel({ submitBindings }: { submitBindings: FrReportCellRead['submitBindings'] }) {
    if (submitBindings.length === 0) {
        return <EmptyPropertyState text="当前单元格没有填报提交配置。" />;
    }
    return (
        <div className="space-y-4">
            {submitBindings.map((submit, index) => (
                <PropertyGroup key={`${submit.name}-${index}`} title={submit.name || `提交配置 ${index + 1}`}>
                    <div className="mb-3 grid grid-cols-3 gap-3 text-xs">
                        <InfoItem label="数据库" value={submit.database || '未识别'} />
                        <InfoItem label="模式" value={submit.schemaName || 'dbo'} />
                        <InfoItem label="表" value={submit.tableName || '未识别'} />
                    </div>
                    <div className="overflow-hidden rounded-lg border border-[#e5e5e5]">
                        <table className="w-full text-left text-xs">
                            <thead className="bg-[#f5f8f7] text-[#52635f]">
                                <tr>
                                    <th className="px-3 py-2 font-medium">主键</th>
                                    <th className="px-3 py-2 font-medium">列</th>
                                    <th className="px-3 py-2 font-medium">值</th>
                                    <th className="px-3 py-2 font-medium">未修改不更新</th>
                                </tr>
                            </thead>
                            <tbody>
                                {submit.columns.map((column) => (
                                    <tr key={`${column.column}-${column.cell || column.value}`} className="border-t border-[#eeeeee]">
                                        <td className="px-3 py-2">{column.isKey ? '是' : '否'}</td>
                                        <td className="px-3 py-2 font-mono">{column.column}</td>
                                        <td className="px-3 py-2">{column.cell || column.value || '当前单元格'}</td>
                                        <td className="px-3 py-2">{column.skipUnmodified ? '是' : '否'}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </PropertyGroup>
            ))}
        </div>
    );
}

function ValidationPropertyPanel({ submitBindings }: { submitBindings: FrReportCellRead['submitBindings'] }) {
    const valueColumns = submitBindings.flatMap((submit) => submit.columns.filter((column) => !column.isKey));
    return (
        <div className="space-y-4">
            <PropertyGroup title="数据校验">
                <div className="grid grid-cols-2 gap-3 text-xs">
                    <InfoItem label="校验规则" value={valueColumns.length > 0 ? '已识别填报值字段' : '未配置'} />
                    <InfoItem label="值字段数量" value={`${valueColumns.length}`} />
                </div>
            </PropertyGroup>
            <PropertyGroup title="提交条件">
                <EmptyPropertyState text="当前版本先解析提交字段，复杂校验表达式后续继续补齐。" />
            </PropertyGroup>
        </div>
    );
}

function ShortcutPropertyPanel({
    widget,
    submitBindings,
}: {
    widget: FrReportCellRead['widget'] | null;
    submitBindings: FrReportCellRead['submitBindings'];
}) {
    return (
        <div className="space-y-4">
            <PropertyGroup title="智能添加字段">
                <div className="grid grid-cols-2 gap-3 text-xs">
                    <InfoItem label="可从控件生成字段" value={widget ? '是' : '否'} />
                    <InfoItem label="可从提交配置生成单元格" value={submitBindings.length > 0 ? '是' : '否'} />
                </div>
            </PropertyGroup>
            <PropertyGroup title="快捷操作">
                <div className="grid grid-cols-2 gap-2">
                    {['添加字段', '添加单元格', '添加单元格组', '移除字段'].map((item) => (
                        <Button key={item} type="button" variant="outline" className="h-8 justify-start text-xs" disabled>
                            {item}
                        </Button>
                    ))}
                </div>
            </PropertyGroup>
        </div>
    );
}

function PropertyGroup({ title, children }: { title: string; children: ReactNode }) {
    return (
        <section className="rounded-xl border border-[#e5e5e5] bg-[#fcfcfc] p-4">
            <h3 className="mb-3 text-sm font-semibold text-[#243a35]">{title}</h3>
            {children}
        </section>
    );
}

function EmptyPropertyState({ text }: { text: string }) {
    return <div className="rounded-lg border border-[#eeeeee] bg-white px-3 py-3 text-xs text-[#6d817d]">{text}</div>;
}

function ReportStructurePanel({
    selectedReport,
    reportStructure,
    loading,
    error,
    fetching,
    hasDraft,
    onRefetchStructure,
}: {
    selectedReport: FrReportFileRead | null;
    reportStructure: FrReportFileStructureRead | null;
    loading: boolean;
    error: unknown;
    fetching: boolean;
    hasDraft: boolean;
    onRefetchStructure: () => void;
}) {
    const [detailOpen, setDetailOpen] = useState(false);
    const [syncDialogOpen, setSyncDialogOpen] = useState(false);

    if (!selectedReport) {
        return (
            <section className="rounded-xl border border-[#e5e5e5] bg-white p-4">
                <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-[#243a35]">
                    <Database className="size-4 text-[#0f8f7b]" />
                    报表结构
                </div>
                <p className="text-xs leading-5 text-[#60736f]">请先从左侧选择一个 CPT 或 FRM 报表文件。</p>
            </section>
        );
    }

    if (loading) {
        return (
            <section className="rounded-xl border border-[#e5e5e5] bg-white p-4">
                <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-[#243a35]">
                    <Database className="size-4 text-[#0f8f7b]" />
                    正在读取报表结构
                </div>
                <p className="text-xs leading-5 text-[#60736f]">正在从帆软 MinIO 在线读取 CPT，不会下载到本地。</p>
            </section>
        );
    }

    if (error || !reportStructure) {
        return (
            <section className="rounded-xl border border-[#f0d0d0] bg-[#fffafa] p-4">
                <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-[#8a2f2f]">
                    <Database className="size-4" />
                    结构读取失败
                </div>
                <p className="text-xs leading-5 text-[#9b3a3a]">当前报表暂时无法解析，请检查文件格式或显示范围权限。</p>
            </section>
        );
    }

    return (
        <section className="rounded-xl border border-[#dbe9e6] bg-white p-3">
            <div className="mb-3 flex items-start justify-between gap-3">
                <div className="min-w-0">
                    <div className="flex items-center gap-2 text-sm font-semibold text-[#243a35]">
                        <Database className="size-4 text-[#0f8f7b]" />
                        当前结构
                    </div>
                    <p className="mt-1 truncate text-xs text-[#60736f]">{reportStructure.fileName}</p>
                </div>
                <Badge className="border-[#d8ebe6] bg-[#f6fbfa] text-[#0c7a68] shadow-none">{reportStructure.format.toUpperCase()}</Badge>
            </div>

            <div className="grid grid-cols-3 gap-2 text-center text-xs">
                <div className="rounded-lg bg-[#f7fbfa] px-2 py-2 ring-1 ring-[#e1efec]">
                    <div className="font-semibold text-[#203b35]">{reportStructure.summary.cellCount}</div>
                    <div className="mt-0.5 text-[11px] text-[#60736f]">单元格</div>
                </div>
                <div className="rounded-lg bg-[#f7fbfa] px-2 py-2 ring-1 ring-[#e1efec]">
                    <div className="font-semibold text-[#203b35]">{reportStructure.summary.datasetCount}</div>
                    <div className="mt-0.5 text-[11px] text-[#60736f]">数据集</div>
                </div>
                <div className="rounded-lg bg-[#f7fbfa] px-2 py-2 ring-1 ring-[#e1efec]">
                    <div className="font-semibold text-[#203b35]">{reportStructure.summary.parameterCount}</div>
                    <div className="mt-0.5 text-[11px] text-[#60736f]">参数</div>
                </div>
            </div>

            {reportStructure.warnings.length > 0 ? (
                <div className="mt-3 rounded-lg border border-[#f0dfb8] bg-[#fffaf0] px-3 py-2 text-xs leading-5 text-[#8a6518] line-clamp-2">
                    {reportStructure.warnings.length} 条结构提示：{reportStructure.warnings.join('；')}
                </div>
            ) : null}

            <div className="mt-3 grid grid-cols-2 gap-2">
                <Button type="button" variant="outline" className="h-8 border-[#dedede] text-xs" onClick={() => setDetailOpen(true)}>
                    查看结构
                </Button>
                <Button
                    type="button"
                    variant="outline"
                    className="h-8 border-[#bfe3dc] bg-[#f6fbfa] text-xs text-[#0b7c6b] hover:bg-[#eaf7f4]"
                    onClick={() => setSyncDialogOpen(true)}
                    disabled={fetching}
                >
                    <RefreshCw className={cn('size-3.5', fetching && 'animate-spin')} />
                    重新获取
                </Button>
            </div>
            <ReportStructureDetailDialog open={detailOpen} onOpenChange={setDetailOpen} reportStructure={reportStructure} />
            <Dialog open={syncDialogOpen} onOpenChange={setSyncDialogOpen}>
                <DialogContent className="max-w-xl">
                    <DialogHeader>
                        <DialogTitle className="text-base text-[#243a35]">重新获取设计器中的报表结构</DialogTitle>
                        <DialogDescription className="text-xs leading-5 text-[#60736f]">
                            将重新从 MinIO 读取当前 CPT/FRM 的最新结构，用来同步 FineReport 设计器里直接做的修改。
                        </DialogDescription>
                    </DialogHeader>
                    <div className="rounded-lg bg-[#fffaf0] p-3 text-xs leading-5 text-[#795300] ring-1 ring-[#f1d48a]">
                        {hasDraft
                            ? '当前有待应用的小驰修改草稿。同步后画布会以设计器最新文件为准，尚未写入文件的预览修改可能需要重新生成。'
                            : '同步只刷新平台读取到的结构，不会直接覆盖 FineReport 文件。'}
                    </div>
                    <DialogFooter>
                        <Button type="button" variant="outline" onClick={() => setSyncDialogOpen(false)}>
                            取消
                        </Button>
                        <Button
                            type="button"
                            className="bg-[#0f8f7b] text-white hover:bg-[#0b7c6b]"
                            onClick={() => {
                                onRefetchStructure();
                                setSyncDialogOpen(false);
                            }}
                        >
                            确认同步
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </section>
    );
}

function ReportStructureDetailDialog({
    open,
    onOpenChange,
    reportStructure,
}: {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    reportStructure: FrReportFileStructureRead;
}) {
    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="max-h-[86vh] overflow-hidden rounded-xl border-[#dfe7e5] bg-white p-0 sm:max-w-5xl">
                <DialogHeader className="border-b border-[#eeeeee] px-5 py-4">
                    <DialogTitle className="text-base font-semibold text-[#243a35]">报表结构详情</DialogTitle>
                    <DialogDescription className="text-xs text-[#6d817d]">
                        这里展示当前在线解析到的工作表、数据集、SQL 和参数，常规聊天区只保留摘要。
                    </DialogDescription>
                </DialogHeader>
                <div className="grid max-h-[68vh] min-h-[520px] grid-cols-[220px_minmax(0,1fr)] overflow-hidden">
                    <aside className="border-r border-[#eeeeee] bg-[#fafafa] p-4">
                        <div className="grid gap-2 text-xs">
                            <InfoItem label="文件名" value={reportStructure.fileName} />
                            <InfoItem label="工作表" value={`${reportStructure.summary.sheetCount}`} />
                            <InfoItem label="单元格" value={`${reportStructure.summary.cellCount}`} />
                            <InfoItem label="合并" value={`${reportStructure.summary.mergeCount}`} />
                            <InfoItem label="数据集" value={`${reportStructure.summary.datasetCount}`} />
                            <InfoItem label="SQL" value={`${reportStructure.summary.queryCount}`} />
                            <InfoItem label="参数" value={`${reportStructure.summary.parameterCount}`} />
                            <InfoItem
                                label="FineReport"
                                value={`${reportStructure.releaseVersion || '未识别'}${reportStructure.xmlVersion ? ` / XML ${reportStructure.xmlVersion}` : ''}`}
                            />
                        </div>
                        {reportStructure.warnings.length > 0 ? (
                            <div className="mt-3 rounded-lg border border-[#f0dfb8] bg-[#fffaf0] px-3 py-2 text-xs leading-5 text-[#8a6518]">
                                {reportStructure.warnings.join('；')}
                            </div>
                        ) : null}
                    </aside>
                    <main className="min-h-0 overflow-auto p-4">
                        <div className="space-y-3">
                            {reportStructure.datasets.length > 0 ? (
                                reportStructure.datasets.map((dataset, index) => (
                                    <div key={`${dataset.name}-${index}`} className="rounded-lg border border-[#eeeeee] bg-[#fafafa] p-3">
                                        <div className="mb-2 flex items-center justify-between gap-2">
                                            <div className="min-w-0">
                                                <div className="truncate text-xs font-semibold text-[#243a35]">{dataset.name || `未命名数据集 ${index + 1}`}</div>
                                                <div className="mt-0.5 truncate text-[11px] text-[#7a8a87]">{dataset.databaseName || dataset.className || '无连接信息'}</div>
                                            </div>
                                            <span className="shrink-0 rounded-full bg-white px-2 py-0.5 text-[10px] text-[#0c7a68] ring-1 ring-[#dbe9e6]">
                                                {dataset.parameters.length} 参数
                                            </span>
                                        </div>
                                        {dataset.querySql ? (
                                            <pre className="max-h-56 overflow-auto whitespace-pre-wrap rounded-md bg-white p-2 font-mono text-[11px] leading-4 text-[#3f4f4b] ring-1 ring-[#eeeeee]">
                                                {dataset.querySql}
                                                {dataset.querySqlTruncated ? '\n...' : ''}
                                            </pre>
                                        ) : (
                                            <div className="rounded-md bg-white p-2 text-[11px] text-[#8a8a8a] ring-1 ring-[#eeeeee]">该数据集暂无 SQL。</div>
                                        )}
                                    </div>
                                ))
                            ) : (
                                <div className="rounded-lg border border-[#eeeeee] bg-white px-3 py-8 text-center text-xs text-[#60736f]">没有解析到数据集。</div>
                            )}
                        </div>
                    </main>
                </div>
                <DialogFooter className="border-t border-[#eeeeee] px-5 py-3">
                    <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                        关闭
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

function CopilotPanel({
    selectedReport,
    reportStructure,
    structureLoading,
    structureError,
    structureFetching,
    onRefetchStructure,
    selectedCell,
    selectedDatasetName,
    previewColumns,
    aiDraft,
    appliedSnapshotId,
    snapshotCpt,
    onDraftReady,
    onApplyDraft,
    onDraftApplied,
    onSnapshotCptGenerated,
    onClearDraft,
}: {
    selectedReport: FrReportFileRead | null;
    reportStructure: FrReportFileStructureRead | null;
    structureLoading: boolean;
    structureError: unknown;
    structureFetching: boolean;
    onRefetchStructure: () => void;
    selectedCell: string;
    selectedDatasetName: string | null;
    previewColumns: string[];
    aiDraft: FrReportAiOperationDraftResponse | null;
    appliedSnapshotId: string | null;
    snapshotCpt: FrReportAiSnapshotCptResponse | null;
    onDraftReady: (draft: FrReportAiOperationDraftResponse) => void;
    onApplyDraft: (draft: FrReportAiOperationDraftResponse) => void;
    onDraftApplied: (result: FrReportAiApplyDraftResponse) => void;
    onSnapshotCptGenerated: (result: FrReportAiSnapshotCptResponse) => void;
    onClearDraft: () => void;
}) {
    const [prompt, setPrompt] = useState('');
    const [draftPrompt, setDraftPrompt] = useState('');
    const [targetObjectPath, setTargetObjectPath] = useState('');
    const [conflictDialogOpen, setConflictDialogOpen] = useState(false);
    const [recycleDialogOpen, setRecycleDialogOpen] = useState(false);
    const [activeTool, setActiveTool] = useState<'structure' | 'draft' | 'commands' | 'versions' | null>(null);
    const [messages, setMessages] = useState<AssistantMessage[]>([
        {
            id: 'welcome',
            role: 'assistant',
            content: '我可以帮你改 SQL、样式、填报配置和版本发布。你直接说要改哪里，我会先生成可预览的修改草稿。',
        },
    ]);
    const generateDraft = useGenerateFrReportAiOperationDraft();
    const applyDraft = useApplyFrReportAiOperationDraft();
    const generateSnapshotCpt = useGenerateFrReportAiSnapshotCpt();
    const effectiveTargetObjectPath = targetObjectPath.trim() || snapshotCpt?.cptObjectPath || selectedReport?.objectPath || '';
    const versionsQuery = useFrReportVersions(effectiveTargetObjectPath || selectedReport?.objectPath);
    const rollbackFileVersion = useRollbackFrReportFileVersion();
    const rollbackStructureVersion = useRollbackFrReportStructureVersion();
    const syncExternalVersion = useSyncFrReportExternalVersion();
    const recycleReportFile = useRecycleFrReportFile();
    const conflictDetail = snapshotCpt?.status === 'conflict' ? snapshotCpt.conflict : versionsQuery.data?.externalConflict;
    useEffect(() => {
        if (snapshotCpt?.status === 'conflict') {
            setConflictDialogOpen(true);
        }
    }, [snapshotCpt]);
    const handleSubmit = () => {
        if (!selectedReport || !prompt.trim()) {
            return;
        }
        const requestText = prompt.trim();
        const pendingMessageId = `assistant-${Date.now()}`;
        setMessages((current) => [
            ...current,
            { id: `user-${Date.now()}`, role: 'user', content: requestText },
            {
                id: pendingMessageId,
                role: 'assistant',
                status: 'pending',
                content: '小驰正在读取当前结构、检查选中单元格和数据集字段，并生成可预览的修改草稿...',
            },
        ]);
        setPrompt('');
        generateDraft.mutate(
            {
                objectPath: selectedReport.objectPath,
                prompt: requestText,
                selectedCell,
                selectedDataset: selectedDatasetName,
                previewColumns,
                previewRows: [],
                mode: 'modify',
            },
            {
                onSuccess: (draft) => {
                    setDraftPrompt(requestText);
                    onDraftReady(draft);
                    setMessages((current) =>
                        current.map((message) =>
                            message.id === pendingMessageId
                                ? {
                                      ...message,
                                      status: 'success',
                                      content: draft.assistantMessage || `已生成 ${draft.operations.length} 个修改操作，画布会先展示预览效果。确认后再应用为平台草稿。`,
                                  }
                                : message,
                        ),
                    );
                },
                onError: (error) => {
                    setMessages((current) =>
                        current.map((message) =>
                            message.id === pendingMessageId
                                ? {
                                      ...message,
                                      status: 'error',
                                      content: error instanceof Error ? `生成失败：${error.message}` : '生成失败：模型或接口暂时没有返回有效结果。',
                                  }
                                : message,
                        ),
                    );
                },
            },
        );
    };
    const handleApplyDraft = () => {
        if (!selectedReport || !aiDraft) {
            return;
        }
        applyDraft.mutate(
            {
                objectPath: selectedReport.objectPath,
                draftId: aiDraft.draftId,
                prompt: draftPrompt,
                selectedCell,
                selectedDataset: selectedDatasetName,
                assistantMessage: aiDraft.assistantMessage,
                operations: aiDraft.operations,
                previewPatch: aiDraft.previewPatch,
                safety: aiDraft.safety,
                warnings: aiDraft.warnings,
            },
            {
                onSuccess: (result) => {
                    onApplyDraft({ ...aiDraft, targetVersion: result.targetVersion });
                    onDraftApplied(result);
                },
            },
        );
    };
    const handleGenerateSnapshotCpt = () => {
        if (!appliedSnapshotId) {
            return;
        }
        generateSnapshotCpt.mutate(
            {
                snapshotId: appliedSnapshotId,
                targetObjectPath: effectiveTargetObjectPath,
                conflictStrategy: 'abort',
            },
            {
                onSuccess: onSnapshotCptGenerated,
            },
        );
    };
    const handleArchiveAndOverwrite = () => {
        if (!appliedSnapshotId || !effectiveTargetObjectPath) {
            return;
        }
        generateSnapshotCpt.mutate(
            {
                snapshotId: appliedSnapshotId,
                targetObjectPath: effectiveTargetObjectPath,
                conflictStrategy: 'archive_and_overwrite',
            },
            {
                onSuccess: onSnapshotCptGenerated,
            },
        );
    };
    const handleImportExternal = () => {
        if (!effectiveTargetObjectPath) {
            return;
        }
        syncExternalVersion.mutate(
            effectiveTargetObjectPath,
            {
                onSuccess: () => {
                    setConflictDialogOpen(false);
                },
            },
        );
    };
    const errorMessage = generateDraft.error instanceof Error ? generateDraft.error.message : null;
    const applyErrorMessage = applyDraft.error instanceof Error ? applyDraft.error.message : null;
    const cptErrorMessage = generateSnapshotCpt.error instanceof Error ? generateSnapshotCpt.error.message : null;

    return (
        <div className="grid h-full min-h-0 grid-rows-[auto_minmax(0,1fr)_auto]">
            <div className="flex items-center justify-between gap-2 border-b border-[#eeeeee] px-1 pb-3">
                <div className="flex min-w-0 items-center gap-2">
                    <div className="grid size-8 shrink-0 place-items-center rounded-lg bg-[#0f8f7b] text-white">
                        <Bot className="size-4" />
                    </div>
                    <div className="min-w-0">
                        <div className="truncate text-sm font-semibold text-[#203b35]">小驰</div>
                        <div className="truncate text-[11px] text-[#60736f]">
                            {selectedReport ? '随时描述你想怎么改这张报表' : '先选择一个报表文件'}
                        </div>
                    </div>
                </div>
                {generateDraft.isPending ? (
                    <span className="inline-flex shrink-0 items-center gap-1 rounded-full bg-[#eef8f5] px-2 py-0.5 text-[11px] text-[#0c7a68]">
                        <RefreshCw className="size-3 animate-spin" />
                        处理中
                    </span>
                ) : null}
            </div>

            <div className="min-h-0 overflow-auto px-1 py-4">
                <div className="space-y-3">
                    {messages.map((message) => (
                        <div
                            key={message.id}
                            className={cn(
                                'max-w-[92%] rounded-2xl px-3 py-2 text-sm leading-6',
                                message.role === 'user'
                                    ? 'ml-auto bg-[#0f8f7b] text-white'
                                    : 'mr-auto border border-[#e8eeee] bg-[#f8faf9] text-[#344541]',
                                message.status === 'pending' && 'border-[#bfe3dc] bg-[#f6fbfa] text-[#0b7c6b]',
                                message.status === 'error' && 'border-[#ffd6d6] bg-[#fff1f1] text-[#9b3a3a]',
                            )}
                        >
                            {message.content}
                        </div>
                    ))}
                    {selectedDatasetName ? (
                        <div className="mr-auto max-w-[92%] rounded-2xl border border-[#e8eeee] bg-white px-3 py-2 text-xs leading-5 text-[#60736f]">
                            当前数据集：{selectedDatasetName}，已预览字段 {previewColumns.length} 个。
                        </div>
                    ) : null}
                </div>
            </div>

            <div className="space-y-2 border-t border-[#eeeeee] bg-white pt-3">
                <div className="flex items-center gap-1 px-1">
                    {[
                        { key: 'structure' as const, label: '上下文', icon: Database },
                        { key: 'draft' as const, label: aiDraft ? `草稿 ${aiDraft.operations.length}` : '草稿', icon: WandSparkles },
                        { key: 'versions' as const, label: '版本', icon: History },
                        { key: 'commands' as const, label: '指令', icon: MessageSquareText },
                    ].map((item) => {
                        const Icon = item.icon;
                        return (
                            <Button
                                key={item.key}
                                type="button"
                                variant="ghost"
                                className="h-8 rounded-lg px-2 text-xs text-[#60736f] hover:bg-[#f6fbfa] hover:text-[#0b7c6b]"
                                onClick={() => setActiveTool(item.key)}
                            >
                                <Icon className="size-3.5" />
                                {item.label}
                            </Button>
                        );
                    })}
                </div>
                <div className="flex items-center gap-2 rounded-xl border border-[#dedede] bg-white p-2 shadow-[0_-8px_20px_rgba(255,255,255,0.92)]">
                <Plus className="size-4 text-[#0f8f7b]" />
                <input
                    className="min-w-0 flex-1 bg-transparent text-sm text-[#333333] outline-none placeholder:text-[#8a8a8a]"
                    value={prompt}
                    onChange={(event) => setPrompt(event.target.value)}
                    onKeyDown={(event) => {
                        if (event.key === 'Enter' && !event.shiftKey) {
                            event.preventDefault();
                            handleSubmit();
                        }
                    }}
                    disabled={!selectedReport || generateDraft.isPending}
                    placeholder="告诉小驰要如何调整这张报表"
                />
                <Button size="icon" className="size-8 bg-[#0f8f7b] text-white hover:bg-[#0b7c6b]" onClick={handleSubmit} disabled={!selectedReport || !prompt.trim() || generateDraft.isPending}>
                    <SendHorizonal className="size-4" />
                </Button>
                </div>
            </div>
            <Dialog open={activeTool === 'structure'} onOpenChange={(open) => setActiveTool(open ? 'structure' : null)}>
                <DialogContent className="max-h-[86vh] overflow-auto rounded-xl border-[#dfe7e5] bg-white sm:max-w-xl">
                    <DialogHeader>
                        <DialogTitle className="text-base text-[#243a35]">小驰上下文</DialogTitle>
                        <DialogDescription className="text-xs text-[#60736f]">
                            结构、SQL、参数和设计器同步入口默认隐藏，需要时再查看。
                        </DialogDescription>
                    </DialogHeader>
                    <ReportStructurePanel
                        selectedReport={selectedReport}
                        reportStructure={reportStructure}
                        loading={structureLoading}
                        error={structureError}
                        fetching={structureFetching}
                        hasDraft={Boolean(aiDraft)}
                        onRefetchStructure={onRefetchStructure}
                    />
                </DialogContent>
            </Dialog>
            <Dialog open={activeTool === 'draft'} onOpenChange={(open) => setActiveTool(open ? 'draft' : null)}>
                <DialogContent className="max-h-[86vh] overflow-auto rounded-xl border-[#dfe7e5] bg-white sm:max-w-2xl">
                    <DialogHeader>
                        <DialogTitle className="text-base text-[#243a35]">待应用修改</DialogTitle>
                        <DialogDescription className="text-xs text-[#60736f]">
                            小驰生成的修改会先停在这里，确认后才进入平台草稿和 CPT 版本流程。
                        </DialogDescription>
                    </DialogHeader>
                    <div className="space-y-2">
                        {(aiDraft?.operations ?? []).map((item) => (
                            <div key={`${item.operationType}-${item.target}-${item.summary}`} className="flex gap-2 rounded-lg bg-[#fafafa] px-3 py-2 text-xs text-[#555555] ring-1 ring-[#eeeeee]">
                                <Check className="mt-0.5 size-3.5 shrink-0 text-[#0f8f7b]" />
                                <span>{item.operationType}：{item.summary}</span>
                            </div>
                        ))}
                        {!aiDraft ? (
                            <div className="rounded-lg bg-[#fafafa] px-3 py-3 text-xs leading-5 text-[#60736f] ring-1 ring-[#eeeeee]">
                                暂无 AI 草稿。输入指令后，模型会返回 SQL、报表、样式或填报相关操作。
                            </div>
                        ) : null}
                        {aiDraft?.warnings.map((warning) => (
                            <div key={warning} className="rounded-lg bg-[#fff8eb] px-3 py-2 text-xs text-[#8a5a00] ring-1 ring-[#f5d79b]">
                                {warning}
                            </div>
                        ))}
                        {[errorMessage, applyErrorMessage, cptErrorMessage].filter(Boolean).map((message) => (
                            <div key={message} className="rounded-lg bg-[#fff1f1] px-3 py-2 text-xs text-[#9b3a3a] ring-1 ring-[#ffd6d6]">{message}</div>
                        ))}
                    </div>
                    <div className="grid grid-cols-2 gap-2">
                        <Button variant="outline" className="h-9 border-[#dedede] text-[#333333] hover:bg-[#f5f5f5]" onClick={onClearDraft} disabled={!aiDraft}>
                            清空草稿
                        </Button>
                        <Button className="h-9 bg-[#0f8f7b] text-white hover:bg-[#0b7c6b]" onClick={handleApplyDraft} disabled={!aiDraft || applyDraft.isPending}>
                            {applyDraft.isPending ? '保存中...' : '应用为草稿'}
                        </Button>
                    </div>
                    <Input
                        value={targetObjectPath}
                        onChange={(event) => setTargetObjectPath(event.target.value)}
                        className="h-9 border-[#dfe7e4] bg-white text-xs"
                        placeholder={selectedReport?.objectPath ?? '目标 CPT 路径，例如 webroot/APP/reportlets/期货/台账/报表.cpt'}
                    />
                    <Button
                        variant="outline"
                        className="h-9 w-full border-[#bfe3dc] bg-[#f6fbfa] text-[#0b7c6b] hover:bg-[#eaf7f4]"
                        onClick={handleGenerateSnapshotCpt}
                        disabled={!appliedSnapshotId || generateSnapshotCpt.isPending}
                    >
                        <Play className="size-4" />
                        {generateSnapshotCpt.isPending ? '生成预览中...' : '生成预览 CPT'}
                    </Button>
                    {snapshotCpt ? (
                        <div className="space-y-2 rounded-lg bg-[#f6fbfa] p-3 text-xs text-[#49615c] ring-1 ring-[#dbe9e6]">
                            <div className="font-medium text-[#0b7c6b]">
                                {snapshotCpt.status === 'conflict'
                                    ? '检测到外部修改，已阻止覆盖'
                                    : snapshotCpt.status === 'generated'
                                      ? 'CPT 文件版本已生成'
                                      : 'CPT 已写入版本库，但 FineReport 校验未通过'}
                            </div>
                            <div className="break-all">对象路径：{snapshotCpt.cptObjectPath}</div>
                            {snapshotCpt.status === 'conflict' ? (
                                <Button size="sm" className="h-8 bg-[#0f8f7b] text-xs text-white hover:bg-[#0b7c6b]" onClick={() => setConflictDialogOpen(true)}>
                                    处理冲突
                                </Button>
                            ) : (
                                <a className="inline-flex items-center gap-1 font-medium text-[#0b7c6b] hover:underline" href={snapshotCpt.previewUrl} target="_blank" rel="noreferrer">
                                    打开 FineReport 预览
                                    <ExternalLink className="size-3.5" />
                                </a>
                            )}
                        </div>
                    ) : null}
                </DialogContent>
            </Dialog>
            <Dialog open={activeTool === 'commands'} onOpenChange={(open) => setActiveTool(open ? 'commands' : null)}>
                <DialogContent className="rounded-xl border-[#dfe7e5] bg-white sm:max-w-md">
                    <DialogHeader>
                        <DialogTitle className="text-base text-[#243a35]">快捷指令</DialogTitle>
                        <DialogDescription className="text-xs text-[#60736f]">点击后会填入输入框，你可以继续补充细节。</DialogDescription>
                    </DialogHeader>
                    <div className="flex flex-wrap gap-2">
                        {['改 SQL', '调整样式', '新增填报项', '生成预览'].map((item) => (
                            <button
                                key={item}
                                type="button"
                                className="rounded-full border border-[#dedede] bg-white px-3 py-1.5 text-xs text-[#444444] hover:bg-[#f5f5f5] hover:text-[#0f8f7b]"
                                onClick={() => {
                                    setPrompt(item);
                                    setActiveTool(null);
                                }}
                            >
                                {item}
                            </button>
                        ))}
                    </div>
                </DialogContent>
            </Dialog>
            <Dialog open={activeTool === 'versions'} onOpenChange={(open) => setActiveTool(open ? 'versions' : null)}>
                <DialogContent className="max-h-[86vh] overflow-auto rounded-xl border-[#dfe7e5] bg-white sm:max-w-2xl">
                    <DialogHeader>
                        <DialogTitle className="text-base text-[#243a35]">版本中心</DialogTitle>
                        <DialogDescription className="text-xs text-[#60736f]">这里只展示真实版本、冲突和回档入口。</DialogDescription>
                    </DialogHeader>
                    {versionsQuery.data?.externalConflict ? (
                        <div className="rounded-lg bg-[#fffaf0] px-3 py-2 text-xs leading-5 text-[#795300] ring-1 ring-[#f1d48a]">
                            {String(versionsQuery.data.externalConflict.message ?? '检测到 FineReport 设计器外部修改')}
                        </div>
                    ) : null}
                    {versionsQuery.data?.project ? (
                        <div className="rounded-lg bg-[#f6fbfa] px-3 py-2 text-xs leading-5 text-[#49615c] ring-1 ring-[#dbe9e6]">
                            <div className="flex items-start justify-between gap-3">
                                <div className="min-w-0">
                                    <div>当前报表：{versionsQuery.data.project.reportName}</div>
                                    <div className="break-all">当前文件：{versionsQuery.data.project.currentObjectPath}</div>
                                </div>
                                <Button
                                    type="button"
                                    variant="outline"
                                    size="sm"
                                    className="h-7 shrink-0 border-[#f0c6c6] px-2 text-[11px] text-[#9b3a3a] hover:bg-[#fff1f1]"
                                    onClick={() => setRecycleDialogOpen(true)}
                                >
                                    <Trash2 className="size-3.5" />
                                    回收
                                </Button>
                            </div>
                        </div>
                    ) : null}
                    <div className="space-y-2">
                        {(versionsQuery.data?.structureVersions ?? []).slice(0, 5).map((item, index) => (
                            <div key={item.structureVersionId} className="rounded-md bg-white px-2.5 py-2 text-xs text-[#60736f] ring-1 ring-[#e5eeee]">
                                <div className="flex items-center justify-between gap-2">
                                    <span className="font-medium text-[#243a35]">结构 V{item.versionNo} · {item.versionName ?? item.sourceType}</span>
                                    <Button
                                        size="sm"
                                        variant="outline"
                                        className="h-7 border-[#dedede] px-2 text-[11px]"
                                        disabled={index === 0 || rollbackStructureVersion.isPending}
                                        onClick={() => rollbackStructureVersion.mutate(item.structureVersionId)}
                                    >
                                        回档结构
                                    </Button>
                                </div>
                                <div className="mt-1 text-[11px]">{item.createTime}</div>
                            </div>
                        ))}
                        {(versionsQuery.data?.fileVersions ?? []).slice(0, 8).map((item, index) => (
                            <div key={item.fileVersionId} className="rounded-lg border border-[#eeeeee] bg-[#fafafa] px-3 py-2 text-xs text-[#60736f]">
                                <div className="flex items-center justify-between gap-2">
                                    <span className="font-medium text-[#243a35]">文件 v{String(item.versionNo).padStart(4, '0')} · {item.versionName ?? item.writeStatus}</span>
                                    <Button
                                        size="sm"
                                        variant="outline"
                                        className="h-7 border-[#dedede] px-2 text-[11px]"
                                        disabled={index === 0 || rollbackFileVersion.isPending}
                                        onClick={() => rollbackFileVersion.mutate(item.fileVersionId)}
                                    >
                                        回档
                                    </Button>
                                </div>
                                <div className="mt-1 break-all text-[11px]">{item.archiveObjectPath}</div>
                                <div className="mt-1 grid gap-1 text-[11px]">
                                    <span>{item.createTime}</span>
                                    <span>状态：{item.writeStatus}</span>
                                </div>
                            </div>
                        ))}
                        {(versionsQuery.data?.fileVersions ?? []).length === 0 && (versionsQuery.data?.structureVersions ?? []).length === 0 ? (
                            <div className="rounded-lg border border-[#eeeeee] bg-[#fafafa] px-3 py-3 text-xs leading-5 text-[#60736f]">
                                暂无平台版本记录。第一次应用草稿或生成 CPT 后，会在这里展示可回档的结构版本和文件版本。
                            </div>
                        ) : null}
                    </div>
                </DialogContent>
            </Dialog>
            <Dialog open={conflictDialogOpen} onOpenChange={setConflictDialogOpen}>
                <DialogContent className="max-w-2xl">
                    <DialogHeader>
                        <DialogTitle className="text-base text-[#243a35]">检测到 FineReport 设计器外部修改</DialogTitle>
                        <DialogDescription className="text-xs leading-5 text-[#60736f]">
                            平台记录的最新文件版本与 MinIO 当前文件不一致。为了避免覆盖设计器中的人工修改，请选择一种处理方式。
                        </DialogDescription>
                    </DialogHeader>
                    <div className="space-y-3 rounded-lg bg-[#fffaf0] p-3 text-xs leading-5 text-[#795300] ring-1 ring-[#f1d48a]">
                        <div>{String(conflictDetail?.message ?? '目标文件和平台最新版本不一致。')}</div>
                        <div className="break-all">目标文件：{effectiveTargetObjectPath || selectedReport?.objectPath || '未选择'}</div>
                        {conflictDetail?.detectedHash ? <div className="break-all">检测 hash：{String(conflictDetail.detectedHash)}</div> : null}
                        {conflictDetail?.detectedLastModified ? <div>检测时间：{String(conflictDetail.detectedLastModified)}</div> : null}
                    </div>
                    <DialogFooter className="gap-2 sm:justify-between">
                        <Button type="button" variant="outline" onClick={() => setConflictDialogOpen(false)}>
                            先不处理
                        </Button>
                        <div className="flex gap-2">
                            <Button type="button" variant="outline" onClick={handleImportExternal} disabled={!effectiveTargetObjectPath || syncExternalVersion.isPending}>
                                仅同步外部修改为版本
                            </Button>
                            <Button type="button" className="bg-[#0f8f7b] text-white hover:bg-[#0b7c6b]" onClick={handleArchiveAndOverwrite} disabled={!appliedSnapshotId || generateSnapshotCpt.isPending}>
                                归档当前文件并覆盖
                            </Button>
                        </div>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
            <Dialog open={recycleDialogOpen} onOpenChange={setRecycleDialogOpen}>
                <DialogContent className="max-w-xl">
                    <DialogHeader>
                        <DialogTitle className="text-base text-[#243a35]">移入回收站</DialogTitle>
                        <DialogDescription className="text-xs leading-5 text-[#60736f]">
                            当前 CPT 会被移动到同目录的回收站，并保留现有版本库。操作前会检查是否存在设计器外部修改。
                        </DialogDescription>
                    </DialogHeader>
                    <div className="break-all rounded-lg bg-[#fffaf0] p-3 text-xs leading-5 text-[#795300] ring-1 ring-[#f1d48a]">
                        {versionsQuery.data?.project?.currentObjectPath ?? effectiveTargetObjectPath}
                    </div>
                    <DialogFooter>
                        <Button type="button" variant="outline" onClick={() => setRecycleDialogOpen(false)}>
                            取消
                        </Button>
                        <Button
                            type="button"
                            className="bg-[#9b3a3a] text-white hover:bg-[#7f2f2f]"
                            disabled={!versionsQuery.data?.project?.currentObjectPath || recycleReportFile.isPending}
                            onClick={() => {
                                const objectPath = versionsQuery.data?.project?.currentObjectPath;
                                if (!objectPath) {
                                    return;
                                }
                                recycleReportFile.mutate(objectPath, {
                                    onSuccess: () => setRecycleDialogOpen(false),
                                });
                            }}
                        >
                            确认移入回收站
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    );
}

function NewReportAiDialog({
    open,
    onOpenChange,
    templateObjectPath,
    reportFiles,
}: {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    templateObjectPath: string | null;
    reportFiles: FrReportFileRead[];
}) {
    const [requirement, setRequirement] = useState('');
    const [reportName, setReportName] = useState('业务报表');
    const [targetFolder, setTargetFolder] = useState('webroot/APP/reportlets/AI生成报表');
    const [sourceTablesText, setSourceTablesText] = useState('');
    const [folderPickerOpen, setFolderPickerOpen] = useState(false);
    const [folderKeyword, setFolderKeyword] = useState('');
    const [files, setFiles] = useState<File[]>([]);
    const [review, setReview] = useState<FrAiReportRequirementReviewResponse | null>(null);
    const [sqlStep, setSqlStep] = useState<GenerateSqlStepResponse | null>(null);
    const [dslStep, setDslStep] = useState<GenerateDslStepResponse | null>(null);
    const [cptStep, setCptStep] = useState<GenerateCptStepResponse | null>(null);
    const [editableCreateTableSql, setEditableCreateTableSql] = useState('');
    const [editableQuerySql, setEditableQuerySql] = useState('');
    const [replyText, setReplyText] = useState('');
    const [builderMessages, setBuilderMessages] = useState<AssistantMessage[]>([
        {
            id: 'new-report-welcome',
            role: 'assistant',
            content: '直接告诉我你要做什么报表、保存到哪里、有没有现成数据库表，也可以上传资料。你提供表名后，我会受控读取表结构并做只读数据预览；信息不够会继续问，够了就开始生成。',
        },
    ]);
    const agentChat = useFrAiReportAgentChat();
    const effectiveTemplateObjectPath = templateObjectPath ?? DEFAULT_NEW_REPORT_TEMPLATE_OBJECT_PATH;
    const errorMessage = agentChat.error instanceof Error ? agentChat.error.message : null;
    const folderOptions = useMemo(() => listReportFolders(reportFiles), [reportFiles]);
    const filteredFolderOptions = useMemo(() => {
        const keyword = folderKeyword.trim().toLowerCase();
        if (!keyword) {
            return folderOptions;
        }
        return folderOptions.filter((folder) => folder.toLowerCase().includes(keyword));
    }, [folderKeyword, folderOptions]);
    const appendBuilderMessage = (message: Omit<AssistantMessage, 'id'>) => {
        setBuilderMessages((current) => [
            ...current,
            { ...message, id: `builder-${Date.now()}-${Math.random().toString(16).slice(2)}` },
        ]);
    };
    const buildAgentContext = (overrides?: Partial<FrAiReportAgentContext>): FrAiReportAgentContext => ({
        reportName,
        targetFolder,
        sourceTableName: sourceTablesText.trim() || null,
        templateObjectPath: effectiveTemplateObjectPath,
        taskId: dslStep?.taskId ?? sqlStep?.taskId ?? cptStep?.taskId ?? null,
        conversationId: dslStep?.conversationId ?? sqlStep?.conversationId ?? cptStep?.conversationId ?? null,
        requirement: requirement.trim() || null,
        ...overrides,
    });
    const applyAgentResponse = (result: FrAiReportAgentChatResponse) => {
        if (result.context.reportName) {
            setReportName(result.context.reportName);
        }
        if (result.context.targetFolder) {
            setTargetFolder(result.context.targetFolder);
        }
        if (result.context.sourceTableName) {
            setSourceTablesText(result.context.sourceTableName);
        }
        if (result.context.requirement) {
            setRequirement(result.context.requirement);
        }
        if (result.review) {
            setReview(result.review);
        }
        if (result.sqlStep) {
            setSqlStep(result.sqlStep);
            setEditableCreateTableSql(result.sqlStep.createTableSql ?? '');
            setEditableQuerySql(result.sqlStep.querySql ?? '');
        }
        if (result.dslStep) {
            setDslStep(result.dslStep);
        }
        if (result.cptStep) {
            setCptStep(result.cptStep);
        }
        const assistantLines = [
            ...result.events
                .filter((event) => event.content)
                .map((event) => {
                    const prefix = event.toolName ? `【${agentToolLabel(event.toolName)}】` : '';
                    return `${prefix}${event.content}`;
                }),
            ...result.questions.map((question) => `需要确认：${question}`),
            ...result.errors.map((item) => `问题：${item}`),
        ].filter(Boolean);
        if (assistantLines.length > 0) {
            appendBuilderMessage({ role: 'assistant', content: assistantLines.join('\n') });
        }
    };
    const sendAgentMessage = (message: string, action: 'chat' | 'start_generate' | 'save_cpt' = 'chat', contextOverrides?: Partial<FrAiReportAgentContext>) => {
        const context = buildAgentContext(contextOverrides);
        const pendingText =
            action === 'start_generate'
                ? '小驰开始执行：需求预检、读取表结构、预览数据、生成 SQL 和 ReportDSL。这个过程可能需要一会儿。'
                : action === 'save_cpt'
                  ? '小驰开始保存 CPT：会先检查版本和外部修改，避免覆盖设计器里的改动。'
                  : '小驰正在分析你的补充内容。';
        appendBuilderMessage({ role: 'assistant', status: 'pending', content: pendingText });
        agentChat.mutate(
            {
                message,
                action,
                context,
                file: files[0] ?? null,
            },
            {
                onSuccess: applyAgentResponse,
                onError: (error) => {
                    appendBuilderMessage({
                        role: 'assistant',
                        status: 'error',
                        content: error instanceof Error ? `小驰执行失败：${error.message}` : '小驰执行失败：接口没有返回有效结果。',
                    });
                },
            },
        );
    };
    const applyChatContext = (text: string) => {
        const extracted = extractNewReportContext(text);
        if (extracted.reportName) {
            setReportName(extracted.reportName);
        }
        if (extracted.targetFolder) {
            setTargetFolder(extracted.targetFolder);
        }
        if (extracted.sourceTablesText) {
            setSourceTablesText((current) => [current.trim(), extracted.sourceTablesText].filter(Boolean).join('\n'));
        }
        return extracted;
    };
    const mergedRequirement = (extraText?: string) => [requirement.trim(), extraText?.trim()].filter(Boolean).join('\n');
    const handleReply = (overrideText?: string) => {
        const text = (overrideText ?? replyText).trim() || (files.length > 0 ? '请根据我上传的资料分析并生成报表方案。' : '');
        if (!text && files.length === 0) {
            return;
        }
        const extracted = applyChatContext(text);
        const freshRequest = isFreshReportRequest(text);
        const nextRequirement = freshRequest ? text : mergedRequirement(text);
        const nextSourceTablesText = freshRequest
            ? (extracted.sourceTablesText ?? '')
            : [sourceTablesText.trim(), extracted.sourceTablesText].filter(Boolean).join('\n');
        setRequirement(nextRequirement);
        setSourceTablesText(nextSourceTablesText);
        if (freshRequest) {
            setReview(null);
            setSqlStep(null);
            setDslStep(null);
            setCptStep(null);
            setEditableCreateTableSql('');
            setEditableQuerySql('');
        }
        appendBuilderMessage({ role: 'user', content: text });
        setReplyText('');
        if (isSaveCptCommand(text)) {
            sendAgentMessage(text, 'save_cpt', {
                requirement: nextRequirement,
                sourceTableName: nextSourceTablesText || null,
            });
            return;
        }
        if (isGenerateReportCommand(text)) {
            sendAgentMessage(text, 'start_generate', {
                requirement: nextRequirement,
                sourceTableName: nextSourceTablesText || null,
            });
            return;
        }
        sendAgentMessage(text, 'chat', {
            requirement: nextRequirement,
            sourceTableName: nextSourceTablesText || null,
        });
    };
    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="max-h-[86vh] w-[70vw] max-w-[1200px] min-w-[860px] overflow-hidden border-[#dfe7e4] bg-white p-0 max-lg:w-[94vw] max-lg:min-w-0">
                <DialogHeader className="border-b border-[#edf2f0] px-5 py-4">
                    <DialogTitle className="text-base font-semibold text-[#243a35]">AI 新建报表</DialogTitle>
                    <DialogDescription className="text-xs text-[#60736f]">
                        上传资料并描述目标，AI 会先生成问题清单和报表方案；确认生成 CPT 时会按指定目录写入并保留版本。
                    </DialogDescription>
                </DialogHeader>
                <div className="grid max-h-[62vh] gap-4 overflow-auto px-5 py-4">
                    <section className="rounded-xl border border-[#edf2f0] bg-[#fafafa] px-3 py-2">
                        <div className="flex flex-wrap items-center gap-2 text-xs text-[#60736f]">
                            <span className="rounded-full bg-white px-2.5 py-1 ring-1 ring-[#edf2f0]">报表：{reportName || '待识别'}</span>
                            <span className="max-w-full truncate rounded-full bg-white px-2.5 py-1 ring-1 ring-[#edf2f0]">
                                目录：{targetFolder || '待识别'}
                            </span>
                            <span className="rounded-full bg-white px-2.5 py-1 ring-1 ring-[#edf2f0]">
                                资料：{files.length} 个
                            </span>
                            <Button
                                type="button"
                                variant="ghost"
                                className="h-7 rounded-full px-2 text-xs text-[#0b7c6b] hover:bg-[#eef8f5]"
                                onClick={() => setFolderPickerOpen(true)}
                            >
                                <Folder className="size-3.5" />
                                选择目录
                            </Button>
                        </div>
                    </section>
                    {errorMessage ? (
                        <div className="rounded-lg bg-[#fff1f1] px-3 py-2 text-xs text-[#9b3a3a] ring-1 ring-[#ffd6d6]">
                            {errorMessage}
                        </div>
                    ) : null}
                    <section className="grid gap-3 rounded-xl border border-[#edf2f0] bg-white p-3">
                        <div className="space-y-3">
                            {builderMessages.map((message) => (
                                <div
                                    key={message.id}
                                    className={cn(
                                        'max-w-[92%] whitespace-pre-wrap rounded-2xl px-3 py-2 text-sm leading-6',
                                        message.role === 'user'
                                            ? 'ml-auto bg-[#0f8f7b] text-white'
                                            : 'mr-auto border border-[#e8eeee] bg-[#f8faf9] text-[#344541]',
                                    )}
                                >
                                    {message.content}
                                </div>
                            ))}
                        </div>
                        {review ? (
                            <details className="rounded-lg border border-[#edf2f0] bg-[#f8fbfa] p-3 text-xs text-[#344541]">
                                <summary className="cursor-pointer font-semibold text-[#243a35]">查看需求预检</summary>
                                <div className="mt-3">
                                    <RequirementReviewPanel review={review} />
                                </div>
                            </details>
                        ) : null}
                        {sqlStep ? (
                            <details className="rounded-lg border border-[#edf2f0] bg-[#f8fbfa] p-3 text-xs text-[#344541]">
                                <summary className="cursor-pointer font-semibold text-[#243a35]">查看并修改 SQL 和表结构</summary>
                                <div className="mt-3 grid gap-3">
                                    <div className="text-xs text-[#60736f]">任务：{sqlStep.taskId} · 状态：{sqlStep.status}</div>
                                    {sqlStep.createTableSql ? (
                                        <label className="grid gap-1 text-xs font-semibold text-[#243a35]">
                                            候选建表 SQL / 字段注释
                                            <textarea
                                                value={editableCreateTableSql}
                                                onChange={(event) => setEditableCreateTableSql(event.target.value)}
                                                className="min-h-48 resize-y rounded-lg border border-[#edf2f0] bg-white p-3 font-mono text-xs font-normal leading-5 text-[#344541] outline-none focus:border-[#0f8f7b]"
                                                spellCheck={false}
                                            />
                                        </label>
                                    ) : null}
                                    {sqlStep.querySql ? (
                                        <label className="grid gap-1 text-xs font-semibold text-[#243a35]">
                                            报表查询 SQL
                                            <textarea
                                                value={editableQuerySql}
                                                onChange={(event) => setEditableQuerySql(event.target.value)}
                                                className="min-h-36 resize-y rounded-lg border border-[#edf2f0] bg-white p-3 font-mono text-xs font-normal leading-5 text-[#344541] outline-none focus:border-[#0f8f7b]"
                                                spellCheck={false}
                                            />
                                        </label>
                                    ) : null}
                                </div>
                            </details>
                        ) : null}
                        {dslStep ? (
                            <div className="rounded-lg bg-[#f6fbfa] px-3 py-2 text-xs leading-5 text-[#0b7c6b] ring-1 ring-[#dbe9e6]">
                                报表设计已生成：{dslStep.reportName}。现在可以保存成 CPT。
                            </div>
                        ) : null}
                        {cptStep ? (
                            <div className="rounded-lg bg-[#f6fbfa] px-3 py-2 text-xs leading-5 text-[#0b7c6b] ring-1 ring-[#dbe9e6]">
                                CPT 状态：{cptStep.status}
                                {cptStep.cptObjectPath ? <div className="break-all">路径：{cptStep.cptObjectPath}</div> : null}
                                {cptStep.previewUrl ? (
                                    <a className="inline-flex items-center gap-1 font-medium hover:underline" href={cptStep.previewUrl} target="_blank" rel="noreferrer">
                                        打开预览
                                        <ExternalLink className="size-3.5" />
                                    </a>
                                ) : null}
                            </div>
                        ) : null}
                        {files.length > 0 ? (
                            <div className="flex flex-wrap gap-2">
                                {files.map((file) => (
                                    <span key={`${file.name}-${file.size}`} className="inline-flex items-center gap-1 rounded-full bg-[#f6fbfa] px-2.5 py-1 text-xs text-[#31544d] ring-1 ring-[#dbe9e6]">
                                        <FileSpreadsheet className="size-3.5" />
                                        {file.name}
                                    </span>
                                ))}
                            </div>
                        ) : null}
                        <div className="flex items-end gap-2 rounded-2xl border border-[#dedede] bg-white p-2">
                            <input
                                id="new-report-file-upload"
                                type="file"
                                multiple
                                accept=".xlsx,.xls,.csv,.doc,.docx,.png,.jpg,.jpeg,.txt,.md"
                                className="hidden"
                                onChange={(event) => setFiles(Array.from(event.target.files ?? []))}
                            />
                            <Button type="button" variant="ghost" size="icon" className="size-9 shrink-0 rounded-full text-[#60736f] hover:bg-[#eef8f5] hover:text-[#0b7c6b]" asChild>
                                <label htmlFor="new-report-file-upload" aria-label="上传资料">
                                    <Paperclip className="size-4" />
                                </label>
                            </Button>
                            <textarea
                                value={replyText}
                                onChange={(event) => setReplyText(event.target.value)}
                                onKeyDown={(event) => {
                                    if (event.key === 'Enter' && !event.shiftKey) {
                                        event.preventDefault();
                                        handleReply();
                                    }
                                }}
                                className="max-h-36 min-h-10 min-w-0 flex-1 resize-none bg-transparent px-1 py-2 text-sm leading-5 text-[#333333] outline-none placeholder:text-[#8a8a8a]"
                                placeholder="直接告诉小驰要做什么报表、保存到哪里、用哪些表；Shift+Enter 换行"
                            />
                            <Button type="button" size="icon" className="size-9 shrink-0 rounded-full bg-[#0f8f7b] text-white hover:bg-[#0b7c6b]" onClick={() => handleReply()} disabled={!replyText.trim() && files.length === 0}>
                                <SendHorizonal className="size-4" />
                            </Button>
                        </div>
                    </section>
                </div>
                <DialogFooter className="border-t border-[#edf2f0] px-5 py-4">
                    <Button variant="outline" className="border-[#dedede]" onClick={() => onOpenChange(false)}>
                        关闭
                    </Button>
                </DialogFooter>
            </DialogContent>
            <Dialog open={folderPickerOpen} onOpenChange={setFolderPickerOpen}>
                <DialogContent className="max-h-[78vh] overflow-hidden rounded-xl border-[#dfe7e4] bg-white p-0 sm:max-w-xl">
                    <DialogHeader className="border-b border-[#edf2f0] px-5 py-4">
                        <DialogTitle className="text-base font-semibold text-[#243a35]">选择生成目录</DialogTitle>
                        <DialogDescription className="text-xs text-[#60736f]">
                            从当前可见 reportlets 目录中选择，也可以关闭后手动输入新目录。
                        </DialogDescription>
                    </DialogHeader>
                    <div className="grid max-h-[54vh] gap-3 overflow-hidden p-4">
                        <div className="relative">
                            <Search className="absolute left-3 top-1/2 size-3.5 -translate-y-1/2 text-[#8aa19c]" />
                            <Input
                                value={folderKeyword}
                                onChange={(event) => setFolderKeyword(event.target.value)}
                                className="h-9 border-[#dedede] bg-white pl-8 text-xs"
                                placeholder="搜索目录"
                            />
                        </div>
                        <div className="min-h-0 overflow-auto rounded-lg border border-[#edf2f0] bg-white p-2">
                            {filteredFolderOptions.length > 0 ? (
                                filteredFolderOptions.map((folder) => (
                                    <button
                                        key={folder}
                                        type="button"
                                        className={cn(
                                            'block w-full rounded-md px-3 py-2 text-left text-xs transition hover:bg-[#f6fbfa] hover:text-[#0b7c6b]',
                                            targetFolder === folder ? 'bg-[#eef8f5] font-semibold text-[#0b7c6b]' : 'text-[#344541]',
                                        )}
                                        onClick={() => {
                                            setTargetFolder(folder);
                                            setFolderPickerOpen(false);
                                        }}
                                    >
                                        {folder}
                                    </button>
                                ))
                            ) : (
                                <div className="px-3 py-8 text-center text-xs text-[#60736f]">没有找到匹配目录。</div>
                            )}
                        </div>
                    </div>
                    <DialogFooter className="border-t border-[#edf2f0] px-5 py-3">
                        <Button type="button" variant="outline" className="border-[#dedede]" onClick={() => setFolderPickerOpen(false)}>
                            关闭
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </Dialog>
    );
}

function RequirementReviewPanel({ review }: { review: FrAiReportRequirementReviewResponse }) {
    return (
        <section className="space-y-3 rounded-xl border border-[#dbe9e6] bg-[#f6fbfa] p-4">
            <div>
                <div className="text-sm font-semibold text-[#243a35]">需求预检</div>
                <div className="mt-1 text-xs leading-5 text-[#60736f]">{review.summary}</div>
            </div>
            {review.maintenanceTables.length > 0 ? (
                <div>
                    <div className="mb-2 text-xs font-semibold text-[#0b7c6b]">建议维护表</div>
                    <div className="grid gap-2">
                        {review.maintenanceTables.map((table) => (
                            <div key={table.tableName} className="rounded-lg bg-white p-3 text-xs ring-1 ring-[#dbe9e6]">
                                <div className="font-semibold text-[#243a35]">{table.displayName}</div>
                                <div className="mt-1 text-[#60736f]">{table.purpose}</div>
                                <div className="mt-2 flex flex-wrap gap-1.5">
                                    {table.fields.slice(0, 8).map((field) => (
                                        <span key={`${table.tableName}-${field.name}`} className="rounded-full bg-[#eef7f5] px-2 py-1 text-[11px] text-[#0b7c6b]">
                                            {field.label}
                                        </span>
                                    ))}
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            ) : null}
            {review.writeBackPlan?.enabled ? (
                <div className="rounded-lg bg-white p-3 text-xs ring-1 ring-[#dbe9e6]">
                    <div className="mb-2 flex items-center justify-between gap-3">
                        <div className="font-semibold text-[#243a35]">填报生成方案</div>
                        <span className="rounded-full bg-[#eef7f5] px-2 py-1 text-[11px] text-[#0b7c6b]">
                            {review.writeBackPlan.allowInsert || review.writeBackPlan.allowDelete ? '支持增删行' : '仅写回'}
                        </span>
                    </div>
                    <div className="grid gap-2 sm:grid-cols-2">
                        <InfoItem label="写回表" value={review.writeBackPlan.targetTable || '待确认'} />
                        <InfoItem label="主键" value={review.writeBackPlan.primaryKeys.join('、') || '待确认'} />
                        <InfoItem label="隐藏主键" value={review.writeBackPlan.hiddenKeys.join('、') || '无'} />
                        <InfoItem label="控件策略" value={review.writeBackPlan.widgetPolicy} />
                    </div>
                    {review.writeBackPlan.editableFields.length > 0 ? (
                        <div className="mt-3">
                            <div className="mb-1 text-[11px] font-semibold text-[#60736f]">可编辑字段</div>
                            <div className="flex flex-wrap gap-1.5">
                                {review.writeBackPlan.editableFields.slice(0, 18).map((field) => (
                                    <span key={field} className="rounded-full bg-[#f6fbfa] px-2 py-1 text-[11px] text-[#31544d] ring-1 ring-[#dbe9e6]">
                                        {field}
                                    </span>
                                ))}
                            </div>
                        </div>
                    ) : null}
                    {review.writeBackPlan.calculatedFields.length > 0 ? (
                        <div className="mt-3">
                            <div className="mb-1 text-[11px] font-semibold text-[#60736f]">计算/只读字段</div>
                            <div className="flex flex-wrap gap-1.5">
                                {review.writeBackPlan.calculatedFields.slice(0, 12).map((field) => (
                                    <span key={field} className="rounded-full bg-[#fafafa] px-2 py-1 text-[11px] text-[#6d817d] ring-1 ring-[#eeeeee]">
                                        {field}
                                    </span>
                                ))}
                            </div>
                        </div>
                    ) : null}
                    {review.writeBackPlan.safetyNotes.length > 0 ? (
                        <div className="mt-3 space-y-1">
                            {review.writeBackPlan.safetyNotes.map((note) => (
                                <div key={note} className="rounded-lg bg-[#fffaf0] px-3 py-2 text-[#6f5200] ring-1 ring-[#f2d99b]">
                                    {note}
                                </div>
                            ))}
                        </div>
                    ) : null}
                </div>
            ) : null}
            {review.questions.length > 0 ? (
                <div>
                    <div className="mb-2 text-xs font-semibold text-[#8a5a00]">需要确认</div>
                    <div className="space-y-1">
                        {review.questions.map((question) => (
                            <div key={question} className="rounded-lg bg-[#fffaf0] px-3 py-2 text-xs text-[#6f5200] ring-1 ring-[#f2d99b]">
                                {question}
                            </div>
                        ))}
                    </div>
                </div>
            ) : null}
            {review.qualityGates.length > 0 ? (
                <div>
                    <div className="mb-2 text-xs font-semibold text-[#60736f]">生成监工规则</div>
                    <div className="grid gap-1.5">
                        {review.qualityGates.map((gate) => (
                            <div key={gate.code} className="rounded-lg bg-white px-3 py-2 text-xs text-[#445a55] ring-1 ring-[#edf2f0]">
                                <span className="font-semibold text-[#243a35]">{gate.label}</span>
                                <span className="ml-2 text-[#60736f]">{gate.description}</span>
                            </div>
                        ))}
                    </div>
                </div>
            ) : null}
        </section>
    );
}

function InfoItem({ label, value }: { label: string; value: string }) {
    return (
        <div className="rounded-lg bg-[#fafafa] px-3 py-2 ring-1 ring-[#eeeeee]">
            <div className="text-[11px] text-[#8a8a8a]">{label}</div>
            <div className="mt-1 truncate font-semibold text-[#333333]">{value}</div>
        </div>
    );
}

function RuleItem({ icon: Icon, title, desc }: { icon: typeof Columns3; title: string; desc: string }) {
    return (
        <div className="flex items-center gap-3 rounded-lg bg-[#fafafa] px-3 py-2 ring-1 ring-[#eeeeee]">
            <Icon className="size-4 text-[#0f8f7b]" />
            <div className="min-w-0">
                <div className="text-xs font-semibold text-[#333333]">{title}</div>
                <div className="truncate text-[11px] text-[#777777]">{desc}</div>
            </div>
        </div>
    );
}
