import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { apiClient } from '@/api/client';
import type {
    CptPublishResponse,
    GenerateReportPayload,
    GenerateReportResponse,
    PreviewValidationResult,
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
