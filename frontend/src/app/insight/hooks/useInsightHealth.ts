import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
    insightApi,
    type InsightAccessRuleUpsert,
    type InsightCandidateListParams,
    type InsightCandidatePromoteRequest,
    type InsightCandidateReviewRequest,
    type InsightCompanyCreate,
    type InsightCompanyImportResponse,
    type InsightCompanyListParams,
    type InsightCompanyUpdate,
    type InsightDataSourceCreate,
    type InsightDataSourceExecutionLogParams,
    type InsightDataSourceExecuteRequest,
    type InsightDataSourceListParams,
    type InsightDataSourceUpdate,
    type InsightIntelligenceCreate,
    type InsightIntelligenceListParams,
    type InsightIntelligenceSourceCreate,
    type InsightIntelligenceUpdate,
    type InsightManualUrlCrawlRequest,
    type InsightNotificationCreate,
    type InsightNotificationListParams,
    type InsightPoolUpsertRequest,
    type InsightReportGenerateRequest,
    type InsightReportListParams,
    type InsightReportPreferenceUpdate,
    type InsightReportTemplateCloneRequest,
    type InsightReportTemplateCreate,
    type InsightReportTemplatePublishRequest,
    type InsightReportTemplateUpdate,
    type InsightReportUpdateRequest,
    type InsightSearchDiscoveryRequest,
    type InsightTagCreate,
    type InsightTagUpdate,
    type InsightVisibilityRuleCreate,
} from "../api";

export const insightQueryKeys = {
    all: ["insight"] as const,
    health: () => [...insightQueryKeys.all, "health"] as const,
    dashboard: () => [...insightQueryKeys.all, "dashboard"] as const,
    qualityOverview: () => [...insightQueryKeys.all, "quality-overview"] as const,
    settingsStatus: () => [...insightQueryKeys.all, "settings-status"] as const,
    dictionaryOverview: () => [...insightQueryKeys.all, "dictionary-overview"] as const,
    dictionaryTags: () => [...insightQueryKeys.all, "dictionary-tags"] as const,
    systemCompanies: () => [...insightQueryKeys.all, "system-companies"] as const,
    notifications: (params: InsightNotificationListParams) => [...insightQueryKeys.all, "notifications", params] as const,
    companies: (params: InsightCompanyListParams) => [...insightQueryKeys.all, "companies", params] as const,
    companyDetail: (companyId: number) => [...insightQueryKeys.all, "company", companyId] as const,
    dataSources: (params: InsightDataSourceListParams) => [...insightQueryKeys.all, "data-sources", params] as const,
    dataSourceExecutionLogs: (params: InsightDataSourceExecutionLogParams) => [...insightQueryKeys.all, "data-source-execution-logs", params] as const,
    schedulerStatus: () => [...insightQueryKeys.all, "scheduler-status"] as const,
    intelligences: (params: InsightIntelligenceListParams) => [...insightQueryKeys.all, "intelligences", params] as const,
    intelligenceDetail: (intelligenceId: number) => [...insightQueryKeys.all, "intelligence", intelligenceId] as const,
    visibilityRules: (intelligenceId: number) => [...insightQueryKeys.all, "visibility-rules", intelligenceId] as const,
    pool: (poolType?: string) => [...insightQueryKeys.all, "pool", poolType ?? "all"] as const,
    candidates: (params: InsightCandidateListParams) => [...insightQueryKeys.all, "candidates", params] as const,
    reports: (params: InsightReportListParams) => [...insightQueryKeys.all, "reports", params] as const,
    reportTemplates: () => [...insightQueryKeys.all, "report-templates"] as const,
    reportPreference: () => [...insightQueryKeys.all, "report-preference"] as const,
    reportDetail: (reportId: number) => [...insightQueryKeys.all, "report", reportId] as const,
    reportExports: (reportId: number) => [...insightQueryKeys.all, "report-exports", reportId] as const,
    accessRules: (targetType: string, targetId: number) => [...insightQueryKeys.all, "access-rules", targetType, targetId] as const,
};

export function useInsightHealth() {
    return useQuery({
        queryKey: insightQueryKeys.health(),
        queryFn: insightApi.getHealth,
    });
}

export function useInsightDashboard() {
    return useQuery({
        queryKey: insightQueryKeys.dashboard(),
        queryFn: insightApi.getDashboard,
    });
}

export function useInsightQualityOverview() {
    return useQuery({
        queryKey: insightQueryKeys.qualityOverview(),
        queryFn: insightApi.getQualityOverview,
    });
}

export function useInsightSettingsStatus() {
    return useQuery({
        queryKey: insightQueryKeys.settingsStatus(),
        queryFn: insightApi.getSettingsStatus,
    });
}

export function useInsightDictionaryOverview() {
    return useQuery({
        queryKey: insightQueryKeys.dictionaryOverview(),
        queryFn: insightApi.getDictionaryOverview,
    });
}

export function useInsightCreateTag() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (payload: InsightTagCreate) => insightApi.createDictionaryTag(payload),
        onSuccess: () => {
            void queryClient.invalidateQueries({ queryKey: insightQueryKeys.dictionaryOverview() });
            void queryClient.invalidateQueries({ queryKey: insightQueryKeys.dictionaryTags() });
        },
    });
}

export function useInsightUpdateTag() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (payload: InsightTagUpdateMutationPayload) => insightApi.updateDictionaryTag(payload.tagId, payload.data),
        onSuccess: () => {
            void queryClient.invalidateQueries({ queryKey: insightQueryKeys.dictionaryOverview() });
            void queryClient.invalidateQueries({ queryKey: insightQueryKeys.dictionaryTags() });
        },
    });
}

export function useInsightDisableTag() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (tagId: number) => insightApi.disableDictionaryTag(tagId),
        onSuccess: () => {
            void queryClient.invalidateQueries({ queryKey: insightQueryKeys.dictionaryOverview() });
            void queryClient.invalidateQueries({ queryKey: insightQueryKeys.dictionaryTags() });
        },
    });
}

export function useInsightNotifications(params: InsightNotificationListParams) {
    return useQuery({
        queryKey: insightQueryKeys.notifications(params),
        queryFn: () => insightApi.listNotifications(params),
    });
}

export function useInsightCreateNotification() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (payload: InsightNotificationCreate) => insightApi.createNotification(payload),
        onSuccess: (response) => {
            void queryClient.invalidateQueries({ queryKey: insightQueryKeys.notifications({ target_type: response.target_type, target_id: response.target_id }) });
        },
    });
}

export function useInsightRetryNotification() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (notificationId: number) => insightApi.retryNotification(notificationId),
        onSuccess: (response) => {
            void queryClient.invalidateQueries({ queryKey: insightQueryKeys.notifications({ target_type: response.target_type, target_id: response.target_id }) });
        },
    });
}

export function useInsightCompanies(params: InsightCompanyListParams) {
    return useQuery({
        queryKey: insightQueryKeys.companies(params),
        queryFn: () => insightApi.listCompanies(params),
    });
}

export function useInsightSystemCompanies() {
    return useQuery({
        queryKey: insightQueryKeys.systemCompanies(),
        queryFn: insightApi.listSystemCompanies,
    });
}

export function useInsightCompanyDetail(companyId: number | null) {
    return useQuery({
        queryKey: insightQueryKeys.companyDetail(companyId ?? 0),
        queryFn: () => insightApi.getCompanyDetail(companyId ?? 0),
        enabled: Boolean(companyId),
    });
}

export function useInsightCreateCompany() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (payload: InsightCompanyCreate) => insightApi.createCompany(payload),
        onSuccess: () => {
            void queryClient.invalidateQueries({ queryKey: insightQueryKeys.all });
        },
    });
}

export function useInsightImportCompanies() {
    const queryClient = useQueryClient();
    return useMutation<InsightCompanyImportResponse, Error, FormData>({
        mutationFn: (payload: FormData) => insightApi.importCompanies(payload),
        onSuccess: () => {
            void queryClient.invalidateQueries({ queryKey: insightQueryKeys.all });
        },
    });
}

export function useInsightUpdateCompany() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (payload: InsightCompanyUpdateMutationPayload) => insightApi.updateCompany(payload.companyId, payload.data),
        onSuccess: (_data, variables) => {
            void queryClient.invalidateQueries({ queryKey: insightQueryKeys.all });
            void queryClient.invalidateQueries({ queryKey: insightQueryKeys.companyDetail(variables.companyId) });
        },
    });
}

export function useInsightDataSources(params: InsightDataSourceListParams) {
    return useQuery({
        queryKey: insightQueryKeys.dataSources(params),
        queryFn: () => insightApi.listDataSources(params),
    });
}

export function useInsightDataSourceExecutionLogs(params: InsightDataSourceExecutionLogParams) {
    return useQuery({
        queryKey: insightQueryKeys.dataSourceExecutionLogs(params),
        queryFn: () => insightApi.listDataSourceExecutionLogs(params),
    });
}

export function useInsightSchedulerStatus() {
    return useQuery({
        queryKey: insightQueryKeys.schedulerStatus(),
        queryFn: insightApi.getSchedulerStatus,
        refetchInterval: 30000,
    });
}

export function useInsightRunSchedulerOnce() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: insightApi.runSchedulerOnce,
        onSuccess: () => {
            void queryClient.invalidateQueries({ queryKey: insightQueryKeys.all });
        },
    });
}

export function useInsightStartScheduler() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: insightApi.startScheduler,
        onSuccess: () => {
            void queryClient.invalidateQueries({ queryKey: insightQueryKeys.schedulerStatus() });
        },
    });
}

export function useInsightStopScheduler() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: insightApi.stopScheduler,
        onSuccess: () => {
            void queryClient.invalidateQueries({ queryKey: insightQueryKeys.schedulerStatus() });
        },
    });
}

export function useInsightRunDueDataSources() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (payload?: { limit?: number }) => insightApi.runDueDataSources(payload),
        onSuccess: () => {
            void queryClient.invalidateQueries({ queryKey: insightQueryKeys.all });
        },
    });
}

export function useInsightReports(params: InsightReportListParams) {
    return useQuery({
        queryKey: insightQueryKeys.reports(params),
        queryFn: () => insightApi.listReports(params),
    });
}

export function useInsightReportTemplates() {
    return useQuery({
        queryKey: insightQueryKeys.reportTemplates(),
        queryFn: insightApi.listReportTemplates,
    });
}

export function useInsightReportPreference() {
    return useQuery({
        queryKey: insightQueryKeys.reportPreference(),
        queryFn: insightApi.getReportPreference,
    });
}

export function useInsightUpdateReportPreference() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (payload: InsightReportPreferenceUpdate) => insightApi.updateReportPreference(payload),
        onSuccess: () => {
            void queryClient.invalidateQueries({ queryKey: insightQueryKeys.reportPreference() });
        },
    });
}

export function useInsightCreateReportTemplate() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (payload: InsightReportTemplateCreate) => insightApi.createReportTemplate(payload),
        onSuccess: () => {
            void queryClient.invalidateQueries({ queryKey: insightQueryKeys.reportTemplates() });
        },
    });
}

export function useInsightUploadReportTemplate() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (payload: FormData) => insightApi.uploadReportTemplate(payload),
        onSuccess: () => {
            void queryClient.invalidateQueries({ queryKey: insightQueryKeys.reportTemplates() });
        },
    });
}

export function useInsightPublishReportTemplate() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (payload: InsightReportTemplatePublishMutationPayload) => insightApi.publishReportTemplate(payload.templateId, payload.data),
        onSuccess: () => {
            void queryClient.invalidateQueries({ queryKey: insightQueryKeys.reportTemplates() });
        },
    });
}

export function useInsightCloneReportTemplate() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (payload: InsightReportTemplateCloneMutationPayload) => insightApi.cloneReportTemplate(payload.templateCode, payload.data),
        onSuccess: () => {
            void queryClient.invalidateQueries({ queryKey: insightQueryKeys.reportTemplates() });
        },
    });
}

export function useInsightUpdateReportTemplate() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (payload: InsightReportTemplateUpdateMutationPayload) => insightApi.updateReportTemplate(payload.templateId, payload.data),
        onSuccess: () => {
            void queryClient.invalidateQueries({ queryKey: insightQueryKeys.reportTemplates() });
        },
    });
}

export function useInsightDeleteReportTemplate() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (templateId: number) => insightApi.deleteReportTemplate(templateId),
        onSuccess: () => {
            void queryClient.invalidateQueries({ queryKey: insightQueryKeys.reportTemplates() });
        },
    });
}

export function useInsightReportDetail(reportId: number | null) {
    return useQuery({
        queryKey: insightQueryKeys.reportDetail(reportId ?? 0),
        queryFn: () => insightApi.getReportDetail(reportId ?? 0),
        enabled: Boolean(reportId),
    });
}

export function useInsightAccessRules(targetType: string, targetId: number | null) {
    return useQuery({
        queryKey: insightQueryKeys.accessRules(targetType, targetId ?? 0),
        queryFn: () => insightApi.listAccessRules(targetType, targetId ?? 0),
        enabled: Boolean(targetType && targetId),
    });
}

export function useInsightGrantAccessRule() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (payload: InsightAccessRuleMutationPayload) => insightApi.grantAccessRule(payload.targetType, payload.targetId, payload.data),
        onSuccess: (_response, variables) => {
            void queryClient.invalidateQueries({ queryKey: insightQueryKeys.accessRules(variables.targetType, variables.targetId) });
        },
    });
}

export function useInsightRevokeAccessRule() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (payload: InsightAccessRuleRevokePayload) => insightApi.revokeAccessRule(payload.ruleId),
        onSuccess: (_response, variables) => {
            void queryClient.invalidateQueries({ queryKey: insightQueryKeys.accessRules(variables.targetType, variables.targetId) });
        },
    });
}

export function useInsightGenerateReport() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (payload: InsightReportGenerateRequest) => insightApi.generateReport(payload),
        onSuccess: (response) => {
            void queryClient.invalidateQueries({ queryKey: insightQueryKeys.all });
            void queryClient.invalidateQueries({ queryKey: insightQueryKeys.reportDetail(response.report.id) });
        },
    });
}

export function useInsightUpdateReport() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (payload: InsightReportUpdateMutationPayload) => insightApi.updateReport(payload.reportId, payload.data),
        onSuccess: (_data, variables) => {
            void queryClient.invalidateQueries({ queryKey: insightQueryKeys.all });
            void queryClient.invalidateQueries({ queryKey: insightQueryKeys.reportDetail(variables.reportId) });
        },
    });
}

export function useInsightReportExports(reportId: number | null) {
    return useQuery({
        queryKey: insightQueryKeys.reportExports(reportId ?? 0),
        queryFn: () => insightApi.listReportExports(reportId ?? 0),
        enabled: Boolean(reportId),
    });
}

export function useInsightExportReport() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (payload: InsightReportExportMutationPayload) => {
            const exportRecord = await insightApi.exportReport(payload.reportId, { export_format: payload.exportFormat ?? "html" });
            if (exportRecord.status !== "success") {
                return { exportRecord, file: null };
            }
            const file = await insightApi.downloadReportExport(payload.reportId, exportRecord.id);
            return { exportRecord, file };
        },
        onSuccess: (_data, variables) => {
            void queryClient.invalidateQueries({ queryKey: insightQueryKeys.reportDetail(variables.reportId) });
            void queryClient.invalidateQueries({ queryKey: insightQueryKeys.reportExports(variables.reportId) });
        },
    });
}

export function useInsightCreateDataSource() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (payload: InsightDataSourceCreate) => insightApi.createDataSource(payload),
        onSuccess: () => {
            void queryClient.invalidateQueries({ queryKey: insightQueryKeys.all });
        },
    });
}

export function useInsightUpdateDataSource() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (payload: InsightDataSourceUpdateMutationPayload) => insightApi.updateDataSource(payload.dataSourceId, payload.data),
        onSuccess: () => {
            void queryClient.invalidateQueries({ queryKey: insightQueryKeys.all });
        },
    });
}

export function useInsightDeleteDataSource() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (dataSourceId: number) => insightApi.deleteDataSource(dataSourceId),
        onSuccess: () => {
            void queryClient.invalidateQueries({ queryKey: insightQueryKeys.all });
        },
    });
}

export function useInsightRetryDataSourceSchedule() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (dataSourceId: number) => insightApi.retryDataSourceSchedule(dataSourceId),
        onSuccess: () => {
            void queryClient.invalidateQueries({ queryKey: insightQueryKeys.all });
        },
    });
}

export function useInsightExecuteDataSource() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (payload: InsightDataSourceExecuteMutationPayload) => insightApi.executeDataSource(payload.dataSourceId, payload.data),
        onSuccess: () => {
            void queryClient.invalidateQueries({ queryKey: insightQueryKeys.all });
        },
    });
}

export function useInsightCandidates(params: InsightCandidateListParams) {
    return useQuery({
        queryKey: insightQueryKeys.candidates(params),
        queryFn: () => insightApi.listCandidates(params),
    });
}

export function useInsightIntelligences(params: InsightIntelligenceListParams) {
    return useQuery({
        queryKey: insightQueryKeys.intelligences(params),
        queryFn: () => insightApi.listIntelligences(params),
    });
}

export function useInsightIntelligenceDetail(intelligenceId: number | null) {
    return useQuery({
        queryKey: insightQueryKeys.intelligenceDetail(intelligenceId ?? 0),
        queryFn: () => insightApi.getIntelligenceDetail(intelligenceId ?? 0),
        enabled: Boolean(intelligenceId),
    });
}

export function useInsightCreateIntelligence() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (payload: InsightIntelligenceCreate) => insightApi.createIntelligence(payload),
        onSuccess: () => {
            void queryClient.invalidateQueries({ queryKey: insightQueryKeys.all });
        },
    });
}

export function useInsightUpdateIntelligence() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (payload: InsightIntelligenceUpdateMutationPayload) => insightApi.updateIntelligence(payload.intelligenceId, payload.data),
        onSuccess: (_data, variables) => {
            void queryClient.invalidateQueries({ queryKey: insightQueryKeys.all });
            void queryClient.invalidateQueries({ queryKey: insightQueryKeys.intelligenceDetail(variables.intelligenceId) });
        },
    });
}

export function useInsightAddIntelligenceSource() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (payload: InsightAddSourceMutationPayload) => insightApi.addIntelligenceSource(payload.intelligenceId, payload.data),
        onSuccess: (_data, variables) => {
            void queryClient.invalidateQueries({ queryKey: insightQueryKeys.all });
            void queryClient.invalidateQueries({ queryKey: insightQueryKeys.intelligenceDetail(variables.intelligenceId) });
        },
    });
}

export function useInsightVisibilityRules(intelligenceId: number | null) {
    return useQuery({
        queryKey: insightQueryKeys.visibilityRules(intelligenceId ?? 0),
        queryFn: () => insightApi.listVisibilityRules(intelligenceId ?? 0),
        enabled: Boolean(intelligenceId),
    });
}

export function useInsightGrantVisibility() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (payload: InsightGrantVisibilityMutationPayload) => insightApi.grantVisibility(payload.intelligenceId, payload.data),
        onSuccess: (_data, variables) => {
            void queryClient.invalidateQueries({ queryKey: insightQueryKeys.visibilityRules(variables.intelligenceId) });
            void queryClient.invalidateQueries({ queryKey: insightQueryKeys.all });
        },
    });
}

export function useInsightMyPool(poolType?: string) {
    return useQuery({
        queryKey: insightQueryKeys.pool(poolType),
        queryFn: () => insightApi.listMyPool({ pool_type: poolType }),
    });
}

export function useInsightUpsertPool() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (payload: InsightPoolMutationPayload) => insightApi.upsertPool(payload.intelligenceId, payload.data),
        onSuccess: () => {
            void queryClient.invalidateQueries({ queryKey: insightQueryKeys.all });
        },
    });
}

export function useInsightRemovePool() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (payload: { intelligenceId: number; poolType: string }) => insightApi.removePool(payload.intelligenceId, payload.poolType),
        onSuccess: () => {
            void queryClient.invalidateQueries({ queryKey: insightQueryKeys.all });
        },
    });
}

export function useInsightManualUrlCrawl() {
    return useMutation({
        mutationFn: (payload: InsightManualUrlCrawlRequest) => insightApi.crawlManualUrl(payload),
    });
}

export function useInsightSearchDiscovery() {
    return useMutation({
        mutationFn: (payload: InsightSearchDiscoveryRequest) => insightApi.searchDiscovery(payload),
    });
}

export function useInsightCandidateReview() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (payload: InsightCandidateReviewMutationPayload) => {
            if (payload.action === "promote") {
                return insightApi.promoteCandidate(payload.candidateId, payload.data ?? {});
            }
            if (payload.action === "reject") {
                return insightApi.rejectCandidate(payload.candidateId, payload.data ?? {});
            }
            return insightApi.ignoreCandidate(payload.candidateId, payload.data ?? {});
        },
        onSuccess: () => {
            void queryClient.invalidateQueries({ queryKey: insightQueryKeys.all });
        },
    });
}

export interface InsightCandidateReviewMutationPayload {
    candidateId: number;
    action: "promote" | "reject" | "ignore";
    data?: InsightCandidatePromoteRequest | InsightCandidateReviewRequest;
}

export interface InsightTagUpdateMutationPayload {
    tagId: number;
    data: InsightTagUpdate;
}

export interface InsightCompanyUpdateMutationPayload {
    companyId: number;
    data: InsightCompanyUpdate;
}

export interface InsightDataSourceUpdateMutationPayload {
    dataSourceId: number;
    data: InsightDataSourceUpdate;
}

export interface InsightDataSourceExecuteMutationPayload {
    dataSourceId: number;
    data: InsightDataSourceExecuteRequest;
}

export interface InsightIntelligenceUpdateMutationPayload {
    intelligenceId: number;
    data: InsightIntelligenceUpdate;
}

export interface InsightAddSourceMutationPayload {
    intelligenceId: number;
    data: InsightIntelligenceSourceCreate;
}

export interface InsightGrantVisibilityMutationPayload {
    intelligenceId: number;
    data: InsightVisibilityRuleCreate;
}

export interface InsightPoolMutationPayload {
    intelligenceId: number;
    data: InsightPoolUpsertRequest;
}

export interface InsightReportUpdateMutationPayload {
    reportId: number;
    data: InsightReportUpdateRequest;
}

export interface InsightReportExportMutationPayload {
    reportId: number;
    exportFormat?: string;
}

export interface InsightReportTemplateUpdateMutationPayload {
    templateId: number;
    data: InsightReportTemplateUpdate;
}

export interface InsightReportTemplatePublishMutationPayload {
    templateId: number;
    data: InsightReportTemplatePublishRequest;
}

export interface InsightReportTemplateCloneMutationPayload {
    templateCode: string;
    data: InsightReportTemplateCloneRequest;
}

export interface InsightAccessRuleMutationPayload {
    targetType: string;
    targetId: number;
    data: InsightAccessRuleUpsert;
}

export interface InsightAccessRuleRevokePayload {
    targetType: string;
    targetId: number;
    ruleId: number;
}
