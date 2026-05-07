import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { apiClient } from '@/api/client';
import type {
    CptPublishResponse,
    FrAiReportFeedbackPayload,
    FrAiReportFeedbackRead,
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
