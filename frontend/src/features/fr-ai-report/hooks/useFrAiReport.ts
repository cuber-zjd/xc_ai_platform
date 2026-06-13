import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { apiClient } from '@/api/client';
import type {
    CptPublishResponse,
    FrAiReportFeedbackPayload,
    FrAiReportFeedbackRead,
    FrAiReportRequirementReviewPayload,
    FrAiReportRequirementReviewResponse,
    FrReportAiApplyDraftPayload,
    FrReportAiApplyDraftResponse,
    FrReportAiNewReportPlanPayload,
    FrReportAiNewReportPlanResponse,
    FrReportAiOperationDraftResponse,
    FrReportAiOperationPayload,
    FrReportAiSnapshotCptPayload,
    FrReportAiSnapshotCptResponse,
    FrReportDatabaseConnectionPayload,
    FrReportDatabaseConnectionRead,
    FrReportDatabaseDriverRead,
    FrReportDatasetPreviewPayload,
    FrReportDatasetPreviewResponse,
    FrReportFileStructureRead,
    FrReportFileListResponse,
    FrReportVisibilityPreferencePayload,
    FrReportVisibilityPreferenceRead,
    GenerateCptStepResponse,
    GenerateDslStepResponse,
    GenerateReportPayload,
    GenerateReportResponse,
    GenerateSqlStepResponse,
    PageResult,
    PreviewValidationResult,
    ReportTaskListItem,
    ReportTaskRead,
} from '@/features/fr-ai-report/types';

const BASE_URL = '/fr/ai-reports';

export function useGenerateFrAiReport() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async (payload: GenerateReportPayload) => {
            const formData = new FormData();
            formData.append('requirement', payload.requirement);
            if (payload.reportName) {
                formData.append('report_name', payload.reportName);
            }
            if (payload.sourceTableName) {
                formData.append('source_table_name', payload.sourceTableName);
            }
            if (payload.tableSchemaJson) {
                formData.append('table_schema_json', payload.tableSchemaJson);
            }
            if (payload.conversationId) {
                formData.append('conversation_id', payload.conversationId);
            }
            if (payload.file) {
                formData.append('file', payload.file);
            }

            const response = await apiClient.post<GenerateReportResponse>(`${BASE_URL}/generate`, formData, {
                headers: {
                    'Content-Type': 'multipart/form-data',
                },
                timeout: 60000,
            });
            return response as unknown as GenerateReportResponse;
        },
        onSuccess: (data) => {
            queryClient.invalidateQueries({ queryKey: ['fr-ai-report-task', data.taskId] });
            queryClient.invalidateQueries({ queryKey: ['fr-ai-report-tasks'] });
        },
    });
}

export function useGenerateFrAiReportSqlStep() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async (payload: GenerateReportPayload) => {
            const formData = new FormData();
            formData.append('requirement', payload.requirement);
            if (payload.reportName) {
                formData.append('report_name', payload.reportName);
            }
            if (payload.sourceTableName) {
                formData.append('source_table_name', payload.sourceTableName);
            }
            if (payload.tableSchemaJson) {
                formData.append('table_schema_json', payload.tableSchemaJson);
            }
            if (payload.conversationId) {
                formData.append('conversation_id', payload.conversationId);
            }
            if (payload.file) {
                formData.append('file', payload.file);
            }

            const response = await apiClient.post<GenerateSqlStepResponse>(`${BASE_URL}/steps/sql/generate`, formData, {
                headers: {
                    'Content-Type': 'multipart/form-data',
                },
                timeout: 60000,
            });
            return response as unknown as GenerateSqlStepResponse;
        },
        onSuccess: (data) => {
            queryClient.invalidateQueries({ queryKey: ['fr-ai-report-task', data.taskId] });
            queryClient.invalidateQueries({ queryKey: ['fr-ai-report-tasks'] });
        },
    });
}

export function useGenerateFrAiReportDslStep() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async ({ taskId, dslFeedback }: { taskId: string; dslFeedback?: string }) => {
            const formData = new FormData();
            formData.append('task_id', taskId);
            if (dslFeedback?.trim()) {
                formData.append('dsl_feedback', dslFeedback.trim());
            }
            const response = await apiClient.post<GenerateDslStepResponse>(`${BASE_URL}/steps/dsl/generate`, formData, {
                headers: {
                    'Content-Type': 'multipart/form-data',
                },
                timeout: 60000,
            });
            return response as unknown as GenerateDslStepResponse;
        },
        onSuccess: (data) => {
            queryClient.invalidateQueries({ queryKey: ['fr-ai-report-task', data.taskId] });
            queryClient.invalidateQueries({ queryKey: ['fr-ai-report-tasks'] });
        },
    });
}

export function useGenerateFrAiReportCptStep() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async (taskId: string) => {
            const formData = new FormData();
            formData.append('task_id', taskId);
            const response = await apiClient.post<GenerateCptStepResponse>(`${BASE_URL}/steps/cpt/generate`, formData, {
                headers: {
                    'Content-Type': 'multipart/form-data',
                },
                timeout: 60000,
            });
            return response as unknown as GenerateCptStepResponse;
        },
        onSuccess: (data) => {
            queryClient.invalidateQueries({ queryKey: ['fr-ai-report-task', data.taskId] });
            queryClient.invalidateQueries({ queryKey: ['fr-ai-report-tasks'] });
        },
    });
}

export function useFrAiReportTasks(page = 1, size = 20, keyword = '') {
    return useQuery({
        queryKey: ['fr-ai-report-tasks', page, size, keyword],
        queryFn: async () => {
            const response = await apiClient.get<PageResult<ReportTaskListItem>>(BASE_URL + '/tasks', {
                params: {
                    page,
                    size,
                    keyword: keyword || undefined,
                },
            });
            return response as unknown as PageResult<ReportTaskListItem>;
        },
    });
}

export function useFrAiReportTask(taskId?: string | null) {
    return useQuery({
        queryKey: ['fr-ai-report-task', taskId],
        queryFn: async () => {
            const response = await apiClient.get<ReportTaskRead>(`${BASE_URL}/tasks/${taskId}`);
            return response as unknown as ReportTaskRead;
        },
        enabled: Boolean(taskId),
    });
}

export function useFrAiReportFiles(keyword = '', limit = 200, includeAll = false) {
    return useQuery({
        queryKey: ['fr-ai-report-files', keyword, limit, includeAll],
        queryFn: async () => {
            const response = await apiClient.get<FrReportFileListResponse>(`${BASE_URL}/files`, {
                params: {
                    keyword: keyword || undefined,
                    limit,
                    include_all: includeAll,
                },
                timeout: 30000,
            });
            return response as unknown as FrReportFileListResponse;
        },
    });
}

export function useFrAiReportFileStructure(objectPath?: string | null) {
    return useQuery({
        queryKey: ['fr-ai-report-file-structure', objectPath],
        queryFn: async () => {
            const response = await apiClient.get<FrReportFileStructureRead>(`${BASE_URL}/files/structure`, {
                params: {
                    object_path: objectPath,
                },
                timeout: 30000,
            });
            return response as unknown as FrReportFileStructureRead;
        },
        enabled: Boolean(objectPath),
    });
}

export function useFrReportDatabaseConnections() {
    return useQuery({
        queryKey: ['fr-report-database-connections'],
        queryFn: async () => {
            const response = await apiClient.get<FrReportDatabaseConnectionRead[]>(`${BASE_URL}/database-connections`);
            return response as unknown as FrReportDatabaseConnectionRead[];
        },
    });
}

export function useFrReportDatabaseDrivers() {
    return useQuery({
        queryKey: ['fr-report-database-drivers'],
        queryFn: async () => {
            const response = await apiClient.get<FrReportDatabaseDriverRead[]>(`${BASE_URL}/database-drivers`);
            return response as unknown as FrReportDatabaseDriverRead[];
        },
    });
}

export function useUpsertFrReportDatabaseConnection() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async (payload: FrReportDatabaseConnectionPayload) => {
            const response = await apiClient.post<FrReportDatabaseConnectionRead>(`${BASE_URL}/database-connections`, payload);
            return response as unknown as FrReportDatabaseConnectionRead;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['fr-report-database-connections'] });
        },
    });
}

export function usePreviewFrReportDataset() {
    return useMutation({
        mutationFn: async (payload: FrReportDatasetPreviewPayload) => {
            const response = await apiClient.post<FrReportDatasetPreviewResponse>(`${BASE_URL}/datasets/preview`, payload, {
                timeout: 30000,
            });
            return response as unknown as FrReportDatasetPreviewResponse;
        },
    });
}

export function useGenerateFrReportAiOperationDraft() {
    return useMutation({
        mutationFn: async (payload: FrReportAiOperationPayload) => {
            const response = await apiClient.post<FrReportAiOperationDraftResponse>(`${BASE_URL}/ai/operation-draft`, payload, {
                timeout: 90000,
            });
            return response as unknown as FrReportAiOperationDraftResponse;
        },
    });
}

export function useGenerateFrReportAiNewReportPlan() {
    return useMutation({
        mutationFn: async (payload: FrReportAiNewReportPlanPayload) => {
            const formData = new FormData();
            formData.append('requirement', payload.requirement);
            if (payload.templateObjectPath) {
                formData.append('template_object_path', payload.templateObjectPath);
            }
            for (const file of payload.files ?? []) {
                formData.append('files', file);
            }
            const response = await apiClient.post<FrReportAiNewReportPlanResponse>(`${BASE_URL}/ai/new-report-plan`, formData, {
                headers: {
                    'Content-Type': 'multipart/form-data',
                },
                timeout: 90000,
            });
            return response as unknown as FrReportAiNewReportPlanResponse;
        },
    });
}

export function useReviewFrAiReportRequirement() {
    return useMutation({
        mutationFn: async (payload: FrAiReportRequirementReviewPayload) => {
            const formData = new FormData();
            if (payload.requirement?.trim()) {
                formData.append('requirement', payload.requirement.trim());
            }
            if (payload.sourceTableName?.trim()) {
                formData.append('source_table_name', payload.sourceTableName.trim());
            }
            if (payload.tableSchemaJson?.trim()) {
                formData.append('table_schema_json', payload.tableSchemaJson.trim());
            }
            if (payload.file) {
                formData.append('file', payload.file);
            }
            const response = await apiClient.post<FrAiReportRequirementReviewResponse>(`${BASE_URL}/requirements/review`, formData, {
                headers: {
                    'Content-Type': 'multipart/form-data',
                },
                timeout: 60000,
            });
            return response as unknown as FrAiReportRequirementReviewResponse;
        },
    });
}

export function useApplyFrReportAiOperationDraft() {
    return useMutation({
        mutationFn: async (payload: FrReportAiApplyDraftPayload) => {
            const response = await apiClient.post<FrReportAiApplyDraftResponse>(`${BASE_URL}/ai/apply-draft`, payload, {
                timeout: 90000,
            });
            return response as unknown as FrReportAiApplyDraftResponse;
        },
    });
}

export function useGenerateFrReportAiSnapshotCpt() {
    return useMutation({
        mutationFn: async (payload: FrReportAiSnapshotCptPayload) => {
            const response = await apiClient.post<FrReportAiSnapshotCptResponse>(`${BASE_URL}/ai/snapshots/cpt/generate`, payload, {
                timeout: 90000,
            });
            return response as unknown as FrReportAiSnapshotCptResponse;
        },
    });
}

export function useFrReportVisibilityPreference() {
    return useQuery({
        queryKey: ['fr-report-visibility-preference'],
        queryFn: async () => {
            const response = await apiClient.get<FrReportVisibilityPreferenceRead>(`${BASE_URL}/files/visibility-preference`);
            return response as unknown as FrReportVisibilityPreferenceRead;
        },
    });
}

export function useUpdateFrReportVisibilityPreference() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async (payload: FrReportVisibilityPreferencePayload) => {
            const response = await apiClient.put<FrReportVisibilityPreferenceRead>(`${BASE_URL}/files/visibility-preference`, payload);
            return response as unknown as FrReportVisibilityPreferenceRead;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['fr-report-visibility-preference'] });
            queryClient.invalidateQueries({ queryKey: ['fr-ai-report-files'] });
        },
    });
}

export function useCreateFrAiReportFeedback() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async ({ taskId, payload }: { taskId: string; payload: FrAiReportFeedbackPayload }) => {
            const response = await apiClient.post<FrAiReportFeedbackRead>(`${BASE_URL}/tasks/${taskId}/feedback`, payload);
            return response as unknown as FrAiReportFeedbackRead;
        },
        onSuccess: (_data, variables) => {
            queryClient.invalidateQueries({ queryKey: ['fr-ai-report-task', variables.taskId] });
            queryClient.invalidateQueries({ queryKey: ['fr-ai-report-tasks'] });
        },
    });
}

export function useValidateFrAiReportTask() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async (taskId: string) => {
            const response = await apiClient.post<PreviewValidationResult>(`${BASE_URL}/tasks/${taskId}/validate`);
            return response as unknown as PreviewValidationResult;
        },
        onSuccess: (_data, taskId) => {
            queryClient.invalidateQueries({ queryKey: ['fr-ai-report-task', taskId] });
        },
    });
}

export function usePublishFrAiReportTask() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async (taskId: string) => {
            const response = await apiClient.post<CptPublishResponse>(`${BASE_URL}/tasks/${taskId}/publish`);
            return response as unknown as CptPublishResponse;
        },
        onSuccess: (_data, taskId) => {
            queryClient.invalidateQueries({ queryKey: ['fr-ai-report-task', taskId] });
        },
    });
}
