import { apiClient } from "@/api/client";
import { useAuthStore } from "@/store/useAuthStore";

export const insightApiPrefix = "/insight";

export const insightApi = {
    getHealth: () => apiClient.get<InsightHealth, InsightHealth>(`${insightApiPrefix}/health`),
    getDashboard: () => apiClient.get<InsightDashboardSummary, InsightDashboardSummary>(`${insightApiPrefix}/dashboard`),
    getSettingsStatus: () => apiClient.get<InsightSettingsStatusRead, InsightSettingsStatusRead>(`${insightApiPrefix}/settings/status`),
    listChannels: (params: InsightChannelListParams) =>
        apiClient.get<InsightPage<InsightChannelRead>, InsightPage<InsightChannelRead>>(`${insightApiPrefix}/settings/channels`, { params }),
    createChannel: (payload: InsightChannelCreate) =>
        apiClient.post<InsightChannelRead, InsightChannelRead>(`${insightApiPrefix}/settings/channels`, payload),
    updateChannel: (channelId: number, payload: InsightChannelUpdate) =>
        apiClient.put<InsightChannelRead, InsightChannelRead>(`${insightApiPrefix}/settings/channels/${channelId}`, payload),
    deleteChannel: (channelId: number) =>
        apiClient.delete<void, void>(`${insightApiPrefix}/settings/channels/${channelId}`),
    seedDefaultChannels: () =>
        apiClient.post<Record<string, number>, Record<string, number>>(`${insightApiPrefix}/settings/channels/seed-defaults`),
    listMonitorConfigs: (params: InsightMonitorConfigListParams) =>
        apiClient.get<InsightPage<InsightMonitorConfigRead>, InsightPage<InsightMonitorConfigRead>>(`${insightApiPrefix}/settings/monitor-configs`, { params }),
    createMonitorConfig: (payload: InsightMonitorConfigCreate) =>
        apiClient.post<InsightMonitorConfigRead, InsightMonitorConfigRead>(`${insightApiPrefix}/settings/monitor-configs`, payload),
    updateMonitorConfig: (configId: number, payload: InsightMonitorConfigUpdate) =>
        apiClient.put<InsightMonitorConfigRead, InsightMonitorConfigRead>(`${insightApiPrefix}/settings/monitor-configs/${configId}`, payload),
    deleteMonitorConfig: (configId: number) =>
        apiClient.delete<void, void>(`${insightApiPrefix}/settings/monitor-configs/${configId}`),
    syncLegacyDataSources: () =>
        apiClient.post<InsightLegacySourceSyncResponse, InsightLegacySourceSyncResponse>(`${insightApiPrefix}/settings/legacy-sources/sync`),
    getQualityOverview: () => apiClient.get<InsightQualityOverview, InsightQualityOverview>(`${insightApiPrefix}/quality/overview`),
    getDictionaryOverview: () => apiClient.get<InsightDictionaryOverview, InsightDictionaryOverview>(`${insightApiPrefix}/dictionaries/overview`),
    listTagCategories: (params?: { include_disabled?: boolean }) =>
        apiClient.get<InsightTagCategoryRead[], InsightTagCategoryRead[]>(`${insightApiPrefix}/dictionaries/tag-categories`, { params }),
    createTagCategory: (payload: InsightTagCategoryCreate) =>
        apiClient.post<InsightTagCategoryRead, InsightTagCategoryRead>(`${insightApiPrefix}/dictionaries/tag-categories`, payload),
    updateTagCategory: (categoryId: number, payload: InsightTagCategoryUpdate) =>
        apiClient.put<InsightTagCategoryRead, InsightTagCategoryRead>(`${insightApiPrefix}/dictionaries/tag-categories/${categoryId}`, payload),
    disableTagCategory: (categoryId: number) =>
        apiClient.post<InsightTagCategoryRead, InsightTagCategoryRead>(`${insightApiPrefix}/dictionaries/tag-categories/${categoryId}/disable`),
    listDictionaryTags: (params?: { tag_type?: string; include_disabled?: boolean }) =>
        apiClient.get<InsightTagRead[], InsightTagRead[]>(`${insightApiPrefix}/dictionaries/tags`, { params }),
    createDictionaryTag: (payload: InsightTagCreate) =>
        apiClient.post<InsightTagRead, InsightTagRead>(`${insightApiPrefix}/dictionaries/tags`, payload),
    updateDictionaryTag: (tagId: number, payload: InsightTagUpdate) =>
        apiClient.put<InsightTagRead, InsightTagRead>(`${insightApiPrefix}/dictionaries/tags/${tagId}`, payload),
    disableDictionaryTag: (tagId: number) =>
        apiClient.post<InsightTagRead, InsightTagRead>(`${insightApiPrefix}/dictionaries/tags/${tagId}/disable`),
    listIntelligenceTypes: () =>
        apiClient.get<InsightIntelligenceTypeRead[], InsightIntelligenceTypeRead[]>(`${insightApiPrefix}/dictionaries/intelligence-types`),
    listNotifications: (params: InsightNotificationListParams) =>
        apiClient.get<InsightPage<InsightNotificationRead>, InsightPage<InsightNotificationRead>>(`${insightApiPrefix}/notifications`, { params }),
    createNotification: (payload: InsightNotificationCreate) =>
        apiClient.post<InsightNotificationRead, InsightNotificationRead>(`${insightApiPrefix}/notifications`, payload),
    retryNotification: (notificationId: number) =>
        apiClient.post<InsightNotificationRead, InsightNotificationRead>(`${insightApiPrefix}/notifications/${notificationId}/retry`),
    listCompanies: (params: InsightCompanyListParams) =>
        apiClient.get<InsightPage<InsightCompanyListItem>, InsightPage<InsightCompanyListItem>>(`${insightApiPrefix}/companies`, { params }),
    listSystemCompanies: () => apiClient.get<SystemCompanyOption[], SystemCompanyOption[]>("/companies"),
    getCompanyDetail: (companyId: number) =>
        apiClient.get<InsightCompanyDetail, InsightCompanyDetail>(`${insightApiPrefix}/companies/${companyId}`),
    createCompany: (payload: InsightCompanyCreate) =>
        apiClient.post<InsightCompanyRead, InsightCompanyRead>(`${insightApiPrefix}/companies`, payload),
    importCompanies: (payload: FormData) =>
        apiClient.post<InsightCompanyImportResponse, InsightCompanyImportResponse>(`${insightApiPrefix}/companies/import`, payload, {
            headers: { "Content-Type": "multipart/form-data" },
            timeout: 120000,
        }),
    downloadCompanyImportTemplate: () =>
        apiClient.get<Blob, Blob>(`${insightApiPrefix}/companies/import-template`, {
            responseType: "blob",
            timeout: 120000,
        }),
    updateCompany: (companyId: number, payload: InsightCompanyUpdate) =>
        apiClient.put<InsightCompanyRead, InsightCompanyRead>(`${insightApiPrefix}/companies/${companyId}`, payload),
    listReports: (params: InsightReportListParams) =>
        apiClient.get<InsightPage<InsightReportListItem>, InsightPage<InsightReportListItem>>(`${insightApiPrefix}/reports`, { params }),
    listReportTemplates: () =>
        apiClient.get<InsightReportTemplateRead[], InsightReportTemplateRead[]>(`${insightApiPrefix}/reports/templates`),
    createReportTemplate: (payload: InsightReportTemplateCreate) =>
        apiClient.post<InsightReportTemplateRead, InsightReportTemplateRead>(`${insightApiPrefix}/reports/templates`, payload),
    uploadReportTemplate: (payload: FormData) =>
        apiClient.post<InsightReportTemplateUploadResponse, InsightReportTemplateUploadResponse>(
            `${insightApiPrefix}/reports/templates/upload`,
            payload,
            { timeout: 120000 },
        ),
    publishReportTemplate: (templateId: number, payload: InsightReportTemplatePublishRequest) =>
        apiClient.post<InsightReportTemplateRead, InsightReportTemplateRead>(`${insightApiPrefix}/reports/templates/${templateId}/publish`, payload),
    cloneReportTemplate: (templateCode: string, payload: InsightReportTemplateCloneRequest) =>
        apiClient.post<InsightReportTemplateRead, InsightReportTemplateRead>(`${insightApiPrefix}/reports/templates/${templateCode}/clone`, payload),
    updateReportTemplate: (templateId: number, payload: InsightReportTemplateUpdate) =>
        apiClient.put<InsightReportTemplateRead, InsightReportTemplateRead>(`${insightApiPrefix}/reports/templates/${templateId}`, payload),
    deleteReportTemplate: (templateId: number) =>
        apiClient.delete<void, void>(`${insightApiPrefix}/reports/templates/${templateId}`),
    getReportDetail: (reportId: number) =>
        apiClient.get<InsightReportDetail, InsightReportDetail>(`${insightApiPrefix}/reports/${reportId}`),
    generateReport: (payload: InsightReportGenerateRequest) =>
        apiClient.post<InsightReportGenerateResponse, InsightReportGenerateResponse>(`${insightApiPrefix}/reports/generate`, payload, {
            timeout: 180000,
        }),
    generateReportStream: (payload: InsightReportGenerateRequest, onEvent: (event: InsightReportGenerateStreamEvent) => void, signal?: AbortSignal) =>
        streamInsightEvents<InsightReportGenerateStreamEvent>(`${insightApiPrefix}/reports/generate/stream`, payload, onEvent, signal),
    listReportSubscriptions: (params: InsightReportSubscriptionListParams) =>
        apiClient.get<InsightPage<InsightReportSubscriptionRead>, InsightPage<InsightReportSubscriptionRead>>(`${insightApiPrefix}/reports/subscriptions`, { params }),
    createReportSubscription: (payload: InsightReportSubscriptionCreate) =>
        apiClient.post<InsightReportSubscriptionRead, InsightReportSubscriptionRead>(`${insightApiPrefix}/reports/subscriptions`, payload),
    updateReportSubscription: (subscriptionId: number, payload: InsightReportSubscriptionUpdate) =>
        apiClient.put<InsightReportSubscriptionRead, InsightReportSubscriptionRead>(`${insightApiPrefix}/reports/subscriptions/${subscriptionId}`, payload),
    deleteReportSubscription: (subscriptionId: number) =>
        apiClient.delete<void, void>(`${insightApiPrefix}/reports/subscriptions/${subscriptionId}`),
    runReportSubscription: (subscriptionId: number) =>
        apiClient.post<InsightReportSubscriptionRunResponse, InsightReportSubscriptionRunResponse>(`${insightApiPrefix}/reports/subscriptions/${subscriptionId}/run`, undefined, {
            timeout: 180000,
        }),
    runDueReportSubscriptions: (params?: { limit?: number }) =>
        apiClient.post<InsightReportSubscriptionDueRunResponse, InsightReportSubscriptionDueRunResponse>(`${insightApiPrefix}/reports/subscriptions/run-due`, undefined, { params, timeout: 180000 }),
    updateReport: (reportId: number, payload: InsightReportUpdateRequest) =>
        apiClient.put<InsightReportDetail, InsightReportDetail>(`${insightApiPrefix}/reports/${reportId}`, payload),
    listReportExports: (reportId: number) =>
        apiClient.get<InsightReportExportRead[], InsightReportExportRead[]>(`${insightApiPrefix}/reports/${reportId}/exports`),
    exportReport: (reportId: number, payload: InsightReportExportRequest) =>
        apiClient.post<InsightReportExportRead, InsightReportExportRead>(`${insightApiPrefix}/reports/${reportId}/exports`, payload, {
            timeout: 120000,
        }),
    downloadReportExport: (reportId: number, exportId: number) =>
        apiClient.get<Blob, Blob>(`${insightApiPrefix}/reports/${reportId}/exports/${exportId}/download`, {
            responseType: "blob",
            timeout: 120000,
        }),
    getReportPreference: () =>
        apiClient.get<InsightReportPreferenceRead, InsightReportPreferenceRead>(`${insightApiPrefix}/reports/preference`),
    updateReportPreference: (payload: InsightReportPreferenceUpdate) =>
        apiClient.put<InsightReportPreferenceRead, InsightReportPreferenceRead>(`${insightApiPrefix}/reports/preference`, payload),
    listAccessRules: (targetType: string, targetId: number) =>
        apiClient.get<InsightAccessRuleRead[], InsightAccessRuleRead[]>(`${insightApiPrefix}/permissions/${targetType}/${targetId}`),
    grantAccessRule: (targetType: string, targetId: number, payload: InsightAccessRuleUpsert) =>
        apiClient.post<InsightAccessRuleRead, InsightAccessRuleRead>(`${insightApiPrefix}/permissions/${targetType}/${targetId}`, payload),
    grantAccessRulesBulk: (targetType: string, payload: InsightAccessRuleBulkUpsert) =>
        apiClient.post<InsightAccessRuleBulkResponse, InsightAccessRuleBulkResponse>(`${insightApiPrefix}/permissions/${targetType}/bulk`, payload),
    revokeAccessRule: (ruleId: number) =>
        apiClient.delete<void, void>(`${insightApiPrefix}/permissions/rules/${ruleId}`),
    getSchedulerStatus: () =>
        apiClient.get<InsightSchedulerStatusRead, InsightSchedulerStatusRead>(`${insightApiPrefix}/scheduler/status`),
    runSchedulerOnce: () =>
        apiClient.post<InsightDataSourceScheduleRunResponse, InsightDataSourceScheduleRunResponse>(`${insightApiPrefix}/scheduler/run-once`),
    startScheduler: () =>
        apiClient.post<InsightSchedulerStatusRead, InsightSchedulerStatusRead>(`${insightApiPrefix}/scheduler/start`),
    stopScheduler: () =>
        apiClient.post<InsightSchedulerStatusRead, InsightSchedulerStatusRead>(`${insightApiPrefix}/scheduler/stop`),
    listDataSources: (params: InsightDataSourceListParams) =>
        apiClient.get<InsightPage<InsightDataSourceRead>, InsightPage<InsightDataSourceRead>>(`${insightApiPrefix}/data-sources`, { params }),
    listDataSourceGroups: (params: InsightDataSourceListParams) =>
        apiClient.get<InsightDataSourceGroupRead[], InsightDataSourceGroupRead[]>(`${insightApiPrefix}/data-sources/groups`, { params }),
    listDataSourceExecutionLogs: (params: InsightDataSourceExecutionLogParams) =>
        apiClient.get<InsightPage<InsightTaskRead>, InsightPage<InsightTaskRead>>(`${insightApiPrefix}/data-sources/execution-logs`, { params }),
    runDueDataSources: (params?: { limit?: number }) =>
        apiClient.post<InsightDataSourceScheduleRunResponse, InsightDataSourceScheduleRunResponse>(
            `${insightApiPrefix}/data-sources/schedule/run-due`,
            null,
            { params },
        ),
    createDataSource: (payload: InsightDataSourceCreate) =>
        apiClient.post<InsightDataSourceRead, InsightDataSourceRead>(`${insightApiPrefix}/data-sources`, payload),
    batchCreateDataSources: (payload: InsightDataSourceBatchCreateRequest) =>
        apiClient.post<InsightDataSourceBatchCreateResponse, InsightDataSourceBatchCreateResponse>(`${insightApiPrefix}/data-sources/batch-create`, payload),
    importDataSources: (payload: FormData) =>
        apiClient.post<InsightDataSourceImportResponse, InsightDataSourceImportResponse>(`${insightApiPrefix}/data-sources/import`, payload, {
            headers: { "Content-Type": "multipart/form-data" },
            timeout: 180000,
        }),
    previewImportDataSources: (payload: FormData) =>
        apiClient.post<InsightDataSourceImportResponse, InsightDataSourceImportResponse>(`${insightApiPrefix}/data-sources/import-preview`, payload, {
            headers: { "Content-Type": "multipart/form-data" },
            timeout: 180000,
        }),
    downloadDataSourceImportTemplate: () =>
        apiClient.get<Blob, Blob>(`${insightApiPrefix}/data-sources/import-template`, {
            responseType: "blob",
            timeout: 120000,
        }),
    bulkActionDataSources: (payload: InsightDataSourceBulkActionRequest) =>
        apiClient.post<InsightDataSourceBulkActionResponse, InsightDataSourceBulkActionResponse>(`${insightApiPrefix}/data-sources/bulk-action`, payload, {
            timeout: 180000,
        }),
    updateDataSource: (dataSourceId: number, payload: InsightDataSourceUpdate) =>
        apiClient.put<InsightDataSourceRead, InsightDataSourceRead>(`${insightApiPrefix}/data-sources/${dataSourceId}`, payload),
    deleteDataSource: (dataSourceId: number) =>
        apiClient.delete<void, void>(`${insightApiPrefix}/data-sources/${dataSourceId}`),
    retryDataSourceSchedule: (dataSourceId: number) =>
        apiClient.post<InsightDataSourceRead, InsightDataSourceRead>(`${insightApiPrefix}/data-sources/${dataSourceId}/schedule/retry`),
    executeDataSource: (dataSourceId: number, payload: InsightDataSourceExecuteRequest) =>
        apiClient.post<InsightDataSourceExecuteResponse, InsightDataSourceExecuteResponse>(`${insightApiPrefix}/data-sources/${dataSourceId}/execute`, payload, {
            timeout: 180000,
        }),
    listIntelligences: (params: InsightIntelligenceListParams) =>
        apiClient.get<InsightPage<InsightIntelligenceListItem>, InsightPage<InsightIntelligenceListItem>>(`${insightApiPrefix}/intelligence`, {
            params,
        }),
    bulkActionIntelligence: (payload: InsightIntelligenceBulkActionRequest) =>
        apiClient.post<InsightIntelligenceBulkActionResponse, InsightIntelligenceBulkActionResponse>(`${insightApiPrefix}/intelligence/bulk-action`, payload, {
            timeout: 180000,
        }),
    chatWithAssistant: (payload: InsightAssistantChatRequest) =>
        apiClient.post<InsightAssistantChatResponse, InsightAssistantChatResponse>(`${insightApiPrefix}/assistant/chat`, payload, {
            timeout: 180000,
        }),
    deepResearch: (payload: InsightDeepResearchRequest) =>
        apiClient.post<InsightDeepResearchResponse, InsightDeepResearchResponse>(`${insightApiPrefix}/research/deep`, payload, {
            timeout: 240000,
        }),
    getIntelligenceDetail: (intelligenceId: number) =>
        apiClient.get<InsightIntelligenceDetail, InsightIntelligenceDetail>(`${insightApiPrefix}/intelligence/${intelligenceId}`),
    createIntelligence: (payload: InsightIntelligenceCreate) =>
        apiClient.post<InsightIntelligenceDetail, InsightIntelligenceDetail>(`${insightApiPrefix}/intelligence`, payload),
    updateIntelligence: (intelligenceId: number, payload: InsightIntelligenceUpdate) =>
        apiClient.put<InsightIntelligenceDetail, InsightIntelligenceDetail>(`${insightApiPrefix}/intelligence/${intelligenceId}`, payload),
    addIntelligenceSource: (intelligenceId: number, payload: InsightIntelligenceSourceCreate) =>
        apiClient.post<InsightIntelligenceSourceRead, InsightIntelligenceSourceRead>(
            `${insightApiPrefix}/intelligence/${intelligenceId}/sources`,
            payload,
        ),
    listVisibilityRules: (intelligenceId: number) =>
        apiClient.get<InsightVisibilityRuleRead[], InsightVisibilityRuleRead[]>(`${insightApiPrefix}/intelligence/${intelligenceId}/visibility-rules`),
    grantVisibility: (intelligenceId: number, payload: InsightVisibilityRuleCreate) =>
        apiClient.post<InsightVisibilityRuleRead, InsightVisibilityRuleRead>(
            `${insightApiPrefix}/intelligence/${intelligenceId}/visibility-rules`,
            payload,
        ),
    listMyPool: (params?: { pool_type?: string }) =>
        apiClient.get<InsightUserIntelligencePoolRead[], InsightUserIntelligencePoolRead[]>(`${insightApiPrefix}/intelligence-pool`, { params }),
    upsertPool: (intelligenceId: number, payload: InsightPoolUpsertRequest) =>
        apiClient.post<InsightUserIntelligencePoolRead, InsightUserIntelligencePoolRead>(`${insightApiPrefix}/intelligence/${intelligenceId}/pool`, payload),
    removePool: (intelligenceId: number, poolType: string) =>
        apiClient.delete<void, void>(`${insightApiPrefix}/intelligence/${intelligenceId}/pool/${poolType}`),
    listCandidates: (params: InsightCandidateListParams) =>
        apiClient.get<InsightPage<InsightIntelligenceCandidateListItem>, InsightPage<InsightIntelligenceCandidateListItem>>(
            `${insightApiPrefix}/intelligence/candidates`,
            { params },
        ),
    searchAssets: (payload: InsightAssetSearchRequest) =>
        apiClient.post<InsightAssetSearchResponse, InsightAssetSearchResponse>(`${insightApiPrefix}/assets/search`, payload, {
            timeout: 120000,
        }),
    backfillFormalAssets: (payload: InsightFormalAssetBackfillRequest) =>
        apiClient.post<InsightFormalAssetBackfillResponse, InsightFormalAssetBackfillResponse>(`${insightApiPrefix}/assets/backfill-formal`, payload, {
            timeout: 180000,
        }),
    getAssetGraph: (params?: InsightGraphParams) =>
        apiClient.get<InsightGraphResponse, InsightGraphResponse>(`${insightApiPrefix}/assets/graph`, { params }),
    crawlManualUrl: (payload: InsightManualUrlCrawlRequest) =>
        apiClient.post<InsightManualUrlCrawlResponse, InsightManualUrlCrawlResponse>(`${insightApiPrefix}/crawler/manual-url`, payload, {
            timeout: 120000,
        }),
    searchDiscovery: (payload: InsightSearchDiscoveryRequest) =>
        apiClient.post<InsightSearchDiscoveryResponse, InsightSearchDiscoveryResponse>(`${insightApiPrefix}/crawler/search-discovery`, payload, {
            timeout: 180000,
        }),
    promoteCandidate: (candidateId: number, payload: InsightCandidatePromoteRequest) =>
        apiClient.post<InsightCandidateReviewResponse, InsightCandidateReviewResponse>(
            `${insightApiPrefix}/intelligence/candidates/${candidateId}/promote`,
            payload,
        ),
    rejectCandidate: (candidateId: number, payload: InsightCandidateReviewRequest) =>
        apiClient.post<InsightCandidateReviewResponse, InsightCandidateReviewResponse>(
            `${insightApiPrefix}/intelligence/candidates/${candidateId}/reject`,
            payload,
        ),
    ignoreCandidate: (candidateId: number, payload: InsightCandidateReviewRequest) =>
        apiClient.post<InsightCandidateReviewResponse, InsightCandidateReviewResponse>(
            `${insightApiPrefix}/intelligence/candidates/${candidateId}/ignore`,
            payload,
        ),
};

async function streamInsightEvents<TEvent>(path: string, payload: unknown, onEvent: (event: TEvent) => void, signal?: AbortSignal) {
    const baseURL = String(apiClient.defaults.baseURL || "/ai-api/v1").replace(/\/$/, "");
    const url = /^https?:\/\//i.test(baseURL) ? `${baseURL}${path}` : `${baseURL}${path}`;
    const token = useAuthStore.getState().token;
    const response = await fetch(url, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            Accept: "text/event-stream",
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify(payload),
        signal,
    });
    if (!response.ok || !response.body) {
        throw new Error("报告生成请求失败");
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let buffer = "";
    while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const chunks = buffer.split("\n\n");
        buffer = chunks.pop() ?? "";
        for (const chunk of chunks) {
            const data = chunk
                .split("\n")
                .filter((line) => line.startsWith("data:"))
                .map((line) => line.slice(5).trim())
                .join("\n");
            if (!data) continue;
            onEvent(JSON.parse(data) as TEvent);
        }
    }
}

export interface InsightHealth {
    module: string;
    status: string;
    version: string;
    enabled_capabilities: string[];
}

export interface InsightDashboardMetric {
    key: string;
    label: string;
    value: number;
    compare_label: string;
    delta: number;
}

export interface InsightDashboardTrendPoint {
    date: string;
    label: string;
    count: number;
}

export interface InsightDashboardSourceSlice {
    source_type: string;
    label: string;
    count: number;
    percent: number;
}

export interface InsightDashboardFocusItem {
    id: number;
    title: string;
    subject_name?: string | null;
    intelligence_type: string;
    importance_level: string;
    publish_time?: string | null;
    score: number;
}

export interface InsightDashboardSummary {
    metrics: InsightDashboardMetric[];
    trend: InsightDashboardTrendPoint[];
    source_distribution: InsightDashboardSourceSlice[];
    focus_items: InsightDashboardFocusItem[];
    latest_items: InsightIntelligenceListItem[];
}

export interface InsightQualityMetric {
    key: string;
    label: string;
    value: number;
    unit: string;
    description?: string | null;
}

export interface InsightQualityReason {
    reason: string;
    count: number;
    category?: string;
    raw_reason?: string | null;
    suggestion?: string | null;
}

export interface InsightQualitySourceMetric {
    data_source_id?: number | null;
    data_source_name: string;
    total_tasks: number;
    success_tasks: number;
    failed_tasks: number;
    success_rate: number;
}

export interface InsightQualityOverview {
    collection_metrics: InsightQualityMetric[];
    review_metrics: InsightQualityMetric[];
    ai_metrics: InsightQualityMetric[];
    failure_reasons: InsightQualityReason[];
    source_metrics: InsightQualitySourceMetric[];
    generated_at: string;
}

export interface InsightCompanyRead {
    id: number;
    company_code: string;
    sys_company_id?: number | null;
    name: string;
    short_name?: string | null;
    industry?: string | null;
    company_type?: string | null;
    region?: string | null;
    website?: string | null;
    logo_url?: string | null;
    description?: string | null;
    monitor_level: string;
    owner_user_id?: number | null;
    profile_json?: Record<string, unknown> | null;
    status: string;
    create_time: string;
    update_time: string;
}

export interface InsightCompanyImportError {
    row_no: number;
    reason: string;
}

export interface InsightCompanyImportResponse {
    total_rows: number;
    created_count: number;
    updated_count: number;
    skipped_count: number;
    errors: InsightCompanyImportError[];
    companies: InsightCompanyRead[];
}

export interface InsightCompanyListItem extends InsightCompanyRead {
    intelligence_count: number;
    candidate_count: number;
    data_source_count: number;
    latest_intelligence_time?: string | null;
}

export interface InsightCompanyMetric {
    key: string;
    label: string;
    value: number;
    compare_label: string;
    delta: number;
}

export interface InsightCompanyTypeSlice {
    label: string;
    count: number;
    percent: number;
}

export interface InsightCompanyTagStat {
    name: string;
    count: number;
}

export interface InsightCompanyDataSourceSummary {
    id: number;
    source_name: string;
    source_type: string;
    status: string;
    last_success_time?: string | null;
}

export interface InsightCompanyTimelineItem {
    id: number;
    title: string;
    summary?: string | null;
    intelligence_type: string;
    importance_level: string;
    publish_time?: string | null;
    create_time: string;
    primary_source_url?: string | null;
    primary_source_title?: string | null;
}

export interface InsightCompanyDetail extends InsightCompanyRead {
    metrics: InsightCompanyMetric[];
    type_distribution: InsightCompanyTypeSlice[];
    tag_stats: InsightCompanyTagStat[];
    data_sources: InsightCompanyDataSourceSummary[];
    timeline: InsightCompanyTimelineItem[];
}

export interface InsightCompanyCreate {
    company_code?: string | null;
    sys_company_id?: number | null;
    name: string;
    short_name?: string | null;
    industry?: string | null;
    company_type?: string | null;
    region?: string | null;
    website?: string | null;
    logo_url?: string | null;
    description?: string | null;
    monitor_level?: string;
    owner_user_id?: number | null;
    profile_json?: Record<string, unknown> | null;
    status?: string;
}

export type InsightCompanyUpdate = Partial<InsightCompanyCreate>;

export interface SystemCompanyOption {
    id: number;
    name: string;
    code?: string | null;
    sync_id?: string | null;
    parent_id?: string | null;
}

export interface InsightCompanyListParams {
    page?: number;
    size?: number;
    keyword?: string;
    sys_company_id?: number;
    industry?: string;
    monitor_level?: string;
    status?: string;
}

export interface InsightReportGenerateRequest {
    title?: string | null;
    report_type?: string;
    template_code?: string | null;
    company_ids?: number[];
    data_source_ids?: number[];
    intelligence_ids?: number[];
    folder_name?: string | null;
    period_start?: string | null;
    period_end?: string | null;
    max_materials?: number;
    generation_prompt?: string | null;
}

export interface InsightReportSubscriptionCreate {
    subscription_name: string;
    report_type?: string;
    template_code?: string | null;
    scope_type?: string;
    sys_company_id?: number | null;
    company_ids?: number[];
    data_source_ids?: number[];
    folder_name?: string | null;
    max_materials?: number;
    generation_prompt?: string | null;
    schedule_frequency?: string;
    weekday?: number | null;
    day_of_month?: number | null;
    time_of_day?: string;
    timezone?: string;
    wecom_recipient_scope?: string;
    wecom_recipients?: InsightNotificationRecipient[];
    visibility_scope?: string;
    status?: string;
}

export type InsightReportSubscriptionUpdate = Partial<InsightReportSubscriptionCreate>;

export interface InsightReportSubscriptionRead {
    id: number;
    subscription_uid: string;
    subscription_name: string;
    report_type: string;
    template_code?: string | null;
    scope_type: string;
    sys_company_id?: number | null;
    company_ids: number[];
    data_source_ids: number[];
    folder_name?: string | null;
    max_materials: number;
    generation_prompt?: string | null;
    schedule_frequency: string;
    weekday?: number | null;
    day_of_month?: number | null;
    time_of_day: string;
    timezone: string;
    next_run_time?: string | null;
    last_run_time?: string | null;
    last_report_id?: number | null;
    last_notification_id?: number | null;
    last_status?: string | null;
    last_error?: string | null;
    wecom_recipient_scope: string;
    wecom_recipients: InsightNotificationRecipient[];
    owner_user_id?: number | null;
    owner_dept_id?: number | null;
    visibility_scope: string;
    status: string;
    create_time: string;
    update_time: string;
}

export interface InsightReportSubscriptionRunResponse {
    subscription: InsightReportSubscriptionRead;
    report?: InsightReportDetail | null;
    notification?: InsightNotificationRead | null;
    skipped?: boolean;
    message?: string | null;
}

export interface InsightReportSubscriptionDueRunResponse {
    checked_count: number;
    due_count: number;
    executed_count: number;
    failed_count: number;
    results: InsightReportSubscriptionRunResponse[];
}

export interface InsightReportSubscriptionListParams {
    page?: number;
    size?: number;
    status?: string;
}

export interface InsightReportUpdateRequest {
    title?: string | null;
    content_json?: InsightReportContent | null;
    summary?: string | null;
    status?: string | null;
    change_summary?: string | null;
}

export interface InsightReportExportRequest {
    export_format?: string;
}

export interface InsightReportExportRead {
    id: number;
    export_uid: string;
    report_id: number;
    report_version_no: number;
    export_format: string;
    status: string;
    file_name?: string | null;
    file_size?: number | null;
    content_type?: string | null;
    storage_backend: string;
    error_message?: string | null;
    requested_by_user_id?: number | null;
    finished_at?: string | null;
    create_time: string;
    update_time: string;
}

export interface InsightReportTemplateSection {
    section_key: string;
    heading: string;
    description: string;
}

export interface InsightReportTemplateRead {
    id?: number | null;
    template_code: string;
    template_name: string;
    description: string;
    report_type: string;
    default_prompt: string;
    sections: InsightReportTemplateSection[];
    structure_json?: Record<string, unknown>;
    template_kind?: string;
    style_code?: string | null;
    export_formats?: string[];
    source_file_name?: string | null;
    source_file_type?: string | null;
    source_file_size?: number | null;
    scope: string;
    market_status?: string;
    market_category?: string | null;
    market_description?: string | null;
    cloned_from_template_id?: number | null;
    published_at?: string | null;
    published_by_user_id?: number | null;
    owner_user_id?: number | null;
    owner_dept_id?: number | null;
    visibility_scope?: string;
    editable: boolean;
}

export interface InsightReportTemplateCreate {
    template_name: string;
    description?: string | null;
    report_type?: string;
    default_prompt: string;
    sections?: InsightReportTemplateSection[];
    structure_json?: Record<string, unknown> | null;
    template_kind?: string;
    style_code?: string | null;
    export_formats?: string[];
    visibility_scope?: string;
}

export interface InsightReportTemplatePublishRequest {
    market_category?: string | null;
    market_description?: string | null;
}

export interface InsightReportTemplateCloneRequest {
    template_name?: string | null;
}

export interface InsightReportTemplateUploadResponse {
    template: InsightReportTemplateRead;
    parsed_structure: Record<string, unknown>;
    extracted_text_preview?: string | null;
}

export type InsightReportTemplateUpdate = Partial<InsightReportTemplateCreate> & {
    status?: string;
    market_status?: string;
    market_category?: string | null;
    market_description?: string | null;
};

export interface InsightAccessRuleUpsert {
    principal_type: string;
    principal_id?: number | null;
    permission?: string;
    grant_type?: string;
    effective_from?: string | null;
    effective_to?: string | null;
}

export interface InsightAccessRuleBulkUpsert extends InsightAccessRuleUpsert {
    target_ids: number[];
}

export interface InsightAccessRuleBulkResponse {
    target_type: string;
    target_count: number;
    rule_count: number;
    rules: InsightAccessRuleRead[];
}

export interface InsightAccessRuleRead {
    id: number;
    target_type: string;
    target_id: number;
    principal_type: string;
    principal_id?: number | null;
    permission: string;
    grant_type: string;
    effective_from?: string | null;
    effective_to?: string | null;
    status: string;
    create_time: string;
    update_time: string;
}

export interface InsightNotificationRecipient {
    recipient_type: string;
    recipient_id?: number | null;
    recipient_name?: string | null;
    wecom_userid?: string | null;
}

export interface InsightNotificationCreate {
    channel?: string;
    target_type: string;
    target_id: number;
    title?: string | null;
    content?: string | null;
    recipient_scope?: string;
    recipients?: InsightNotificationRecipient[];
    scheduled_at?: string | null;
    send_now?: boolean;
}

export interface InsightNotificationRead {
    id: number;
    notification_uid: string;
    channel: string;
    title: string;
    content?: string | null;
    target_type: string;
    target_id: number;
    target_title?: string | null;
    recipient_scope: string;
    recipients: InsightNotificationRecipient[];
    payload_json: Record<string, unknown>;
    status: string;
    permission_status: string;
    scheduled_at?: string | null;
    sent_at?: string | null;
    error_message?: string | null;
    created_by_user_id?: number | null;
    create_time: string;
    update_time: string;
}

export interface InsightNotificationListParams {
    page?: number;
    size?: number;
    target_type?: string;
    target_id?: number;
    channel?: string;
    status?: string;
}

export interface InsightSettingsStatusItem {
    key: string;
    name: string;
    status: "ok" | "warning" | "disabled";
    description: string;
    details: string[];
}

export interface InsightSettingsStatusSection {
    key: string;
    name: string;
    description: string;
    items: InsightSettingsStatusItem[];
}

export interface InsightSettingsStatusRead {
    generated_at: string;
    readonly: boolean;
    sections: InsightSettingsStatusSection[];
}

export interface InsightChannelRead {
    id: number;
    channel_code: string;
    channel_name: string;
    channel_type: string;
    channel_url?: string | null;
    applicable_scenarios: string[];
    collection_method: string;
    login_requirement: string;
    access_status: string;
    default_trust_level: string;
    default_frequency: string;
    default_processing_policy: string;
    config_json?: Record<string, unknown> | null;
    sort_no: number;
    status: string;
    comment?: string | null;
    create_time: string;
    update_time: string;
}

export interface InsightChannelCreate {
    channel_code?: string | null;
    channel_name: string;
    channel_type: string;
    channel_url?: string | null;
    applicable_scenarios?: string[];
    collection_method?: string;
    login_requirement?: string;
    access_status?: string;
    default_trust_level?: string;
    default_frequency?: string;
    default_processing_policy?: string;
    config_json?: Record<string, unknown> | null;
    sort_no?: number;
    comment?: string | null;
    status?: string;
}

export type InsightChannelUpdate = Partial<InsightChannelCreate>;

export interface InsightChannelListParams {
    page?: number;
    size?: number;
    keyword?: string;
    channel_type?: string;
    access_status?: string;
    status?: string;
    scenario?: string;
}

export interface InsightTagRead {
    id: number;
    tag_code: string;
    tag_name: string;
    tag_type: string;
    color?: string | null;
    sort_no: number;
    status: "active" | "disabled" | string;
    create_time: string;
    update_time: string;
}

export interface InsightTagCategoryRead {
    id: number;
    category_code: string;
    category_name: string;
    description?: string | null;
    color?: string | null;
    sort_no: number;
    status: "active" | "disabled" | string;
    tag_count: number;
    create_time: string;
    update_time: string;
}

export interface InsightTagCategoryCreate {
    category_code?: string | null;
    category_name: string;
    description?: string | null;
    color?: string | null;
    sort_no?: number;
}

export type InsightTagCategoryUpdate = Partial<Pick<InsightTagCategoryCreate, "category_name" | "description" | "color" | "sort_no">> & {
    status?: "active" | "disabled";
};

export interface InsightTagCreate {
    tag_code?: string | null;
    tag_name: string;
    tag_type?: string;
    color?: string | null;
    sort_no?: number;
}

export type InsightTagUpdate = Partial<Pick<InsightTagCreate, "tag_name" | "tag_type" | "color" | "sort_no">> & {
    status?: "active" | "disabled";
};

export interface InsightIntelligenceTypeRead {
    type_code: string;
    type_name: string;
    description: string;
    sort_no: number;
    status: string;
    readonly: boolean;
    usage_count: number;
}

export interface InsightDictionaryOverview {
    categories: InsightTagCategoryRead[];
    tags: InsightTagRead[];
    intelligence_types: InsightIntelligenceTypeRead[];
}

export interface InsightReportPreferenceRead {
    id: number;
    user_id: number;
    default_template_code?: string | null;
    default_report_type: string;
    default_folder_name?: string | null;
    default_max_materials: number;
    writing_stance: string;
    report_depth: string;
    citation_style: string;
    include_risks: boolean;
    include_opportunities: boolean;
    include_follow_up_questions: boolean;
    custom_prompt_suffix?: string | null;
    status: string;
    create_time: string;
    update_time: string;
}

export type InsightReportPreferenceUpdate = Partial<
    Pick<
        InsightReportPreferenceRead,
        | "default_template_code"
        | "default_report_type"
        | "default_folder_name"
        | "default_max_materials"
        | "writing_stance"
        | "report_depth"
        | "citation_style"
        | "include_risks"
        | "include_opportunities"
        | "include_follow_up_questions"
        | "custom_prompt_suffix"
    >
>;

export interface InsightReportListParams {
    page?: number;
    size?: number;
    keyword?: string;
    report_type?: string;
    status?: string;
}

export interface InsightReportRead {
    id: number;
    report_uid: string;
    title: string;
    report_type: string;
    period_start?: string | null;
    period_end?: string | null;
    company_id?: number | null;
    company_name?: string | null;
    content_json: InsightReportContent;
    summary?: string | null;
    status: string;
    version_no: number;
    material_count: number;
    owner_user_id?: number | null;
    owner_dept_id?: number | null;
    visibility_scope?: string;
    create_time: string;
    update_time: string;
}

export type InsightReportListItem = InsightReportRead;

export interface InsightReportMaterialRead {
    id: number;
    report_id: number;
    intelligence_id: number;
    section_key: string;
    sort_no: number;
    quote_text?: string | null;
    source_url?: string | null;
    source_title?: string | null;
    selection_source: string;
    selection_reason?: string | null;
    intelligence_title?: string | null;
    intelligence_summary?: string | null;
    create_time: string;
    update_time: string;
}

export interface InsightReportVersionRead {
    id: number;
    report_id: number;
    version_no: number;
    content_json: InsightReportContent;
    change_summary?: string | null;
    created_by_user_id?: number | null;
    create_time: string;
    update_time: string;
}

export interface InsightReportChartPoint {
    label: string;
    value: number;
    key?: string | null;
    percent?: number | null;
}

export interface InsightReportChartRead {
    chart_key: string;
    title: string;
    description?: string | null;
    chart_type: "bar" | "donut" | "line" | "list" | string;
    unit: string;
    points: InsightReportChartPoint[];
}

export interface InsightReportDetail extends InsightReportRead {
    materials: InsightReportMaterialRead[];
    versions: InsightReportVersionRead[];
    charts: InsightReportChartRead[];
}

export interface InsightReportGenerateResponse {
    report: InsightReportDetail;
    task_id?: number | null;
    used_material_count: number;
    generation_mode: string;
}

export interface InsightReportGenerateStreamEvent {
    event: "connected" | "progress" | "done" | "error" | string;
    step?: string;
    title?: string;
    detail?: string;
    progress?: number;
    material_count?: number;
    relation_count?: number;
    report_id?: number | null;
    generation_mode?: string | null;
    data?: InsightReportGenerateResponse;
}

export interface InsightReportContent {
    title?: string;
    executive_summary?: string;
    summary?: string;
    template_code?: string;
    template_name?: string;
    chapters?: InsightReportChapter[];
    conclusion?: string;
    research_method?: string[];
    evidence_matrix?: InsightReportEvidence[];
    key_findings?: InsightReportFinding[];
    company_sections?: InsightReportCompanySection[];
    risks?: InsightReportFinding[];
    opportunities?: InsightReportFinding[];
    reflection?: string[];
    follow_up_questions?: string[];
    source_notes?: string[];
    stats?: {
        material_count?: number;
        type_counts?: Record<string, number>;
        company_counts?: Record<string, number>;
    };
    [key: string]: unknown;
}

export interface InsightReportChapter {
    heading?: string;
    paragraphs?: string[];
    evidence_ids?: number[];
}

export interface InsightReportFinding {
    title?: string;
    insight?: string;
    summary?: string;
    evidence_ids?: number[];
}

export interface InsightReportEvidence {
    theme?: string;
    material_count?: number;
    evidence_strength?: string;
    note?: string;
}

export interface InsightReportCompanySection {
    company_name?: string;
    summary?: string;
    signals?: InsightReportFinding[];
}

export interface InsightManualUrlCrawlRequest {
    url: string;
    query_text?: string | null;
    data_source_id?: number | null;
    monitor_config_id?: number | null;
    source_channel_id?: number | null;
}

export interface InsightDataSourceFetchConfig {
    keywords?: string[];
    include_keywords?: string[];
    exclude_keywords?: string[];
    max_results?: number;
    crawl_top_n?: number;
    freshness?: string | null;
    schedule_type?: string;
    cron_expression?: string | null;
    enable_llm_filter?: boolean;
    filter_prompt?: string | null;
    llm_min_score?: number | null;
    llm_failure_policy?: string;
    auto_review_mode?: string;
    auto_review_min_confidence?: number;
    auto_review_required_tags?: string[];
    auto_review_intelligence_types?: string[];
    auto_add_to_report_pool?: boolean;
    auto_report_folder?: string | null;
    create_candidate_from_hits?: boolean;
    extra?: Record<string, unknown>;
}

export interface InsightDataSourceRead {
    id: number;
    source_code: string;
    source_name: string;
    source_type: string;
    base_url?: string | null;
    channel_id?: number | null;
    channel_name?: string | null;
    monitor_config_id?: number | null;
    monitor_config_name?: string | null;
    monitor_object_type?: string | null;
    monitor_object_id?: number | null;
    execution_role?: string | null;
    generation_mode: string;
    collection_strategy: string;
    company_id?: number | null;
    company_name?: string | null;
    company_short_name?: string | null;
    fetch_frequency: string;
    fetch_config?: InsightDataSourceFetchConfig | null;
    auth_config_ref?: string | null;
    last_fetch_time?: string | null;
    last_success_time?: string | null;
    next_run_time?: string | null;
    schedule_enabled: boolean;
    last_schedule_status?: string | null;
    last_schedule_message?: string | null;
    consecutive_failure_count: number;
    last_failure_time?: string | null;
    auto_paused_reason?: string | null;
    owner_user_id?: number | null;
    owner_dept_id?: number | null;
    visibility_scope?: string;
    status: string;
    create_time: string;
    update_time: string;
}

export interface InsightDataSourceGroupRead {
    group_key: string;
    monitor_config_id?: number | null;
    monitor_config_name?: string | null;
    monitor_type?: string | null;
    execution_role?: string | null;
    channel_id?: number | null;
    channel_name?: string | null;
    company_id?: number | null;
    company_name?: string | null;
    company_short_name?: string | null;
    sys_company_id?: number | null;
    source_type: string;
    source_type_label: string;
    total_count: number;
    enabled_count: number;
    disabled_count: number;
    scheduled_count: number;
    llm_filter_count: number;
    auto_review_count: number;
    failed_count: number;
    paused_count: number;
    latest_success_time?: string | null;
    latest_failure_time?: string | null;
    next_run_time?: string | null;
    visibility_scopes: string[];
    data_source_ids: number[];
}

export interface InsightDataSourceCreate {
    source_code?: string | null;
    source_name: string;
    source_type: string;
    base_url?: string | null;
    channel_id?: number | null;
    monitor_config_id?: number | null;
    monitor_object_type?: string | null;
    monitor_object_id?: number | null;
    execution_role?: string | null;
    generation_mode?: string;
    collection_strategy?: string;
    company_id?: number | null;
    fetch_frequency?: string;
    fetch_config?: InsightDataSourceFetchConfig | null;
    auth_config_ref?: string | null;
    schedule_enabled?: boolean | null;
    visibility_scope?: string;
    status?: string;
}

export interface InsightDataSourceBatchCreateRequest {
    company_ids: number[];
    source_types: string[];
    keyword_template?: string | null;
    include_keywords?: string[];
    exclude_keywords?: string[];
    fetch_frequency?: string;
    max_results?: number;
    crawl_top_n?: number;
    freshness?: string | null;
    enable_llm_filter?: boolean;
    filter_prompt?: string | null;
    auto_review_mode?: string;
    auto_review_min_confidence?: number;
    auto_add_to_report_pool?: boolean;
    auto_report_folder?: string | null;
    visibility_scope?: string;
    status?: string;
    update_existing?: boolean;
}

export interface InsightDataSourceBatchCreateItem {
    company_id: number;
    company_name: string;
    source_type: string;
    source_name: string;
    source_code: string;
    status: string;
    data_source_id?: number | null;
    message?: string | null;
}

export interface InsightDataSourceBatchCreateResponse {
    requested_company_count: number;
    requested_type_count: number;
    requested_count: number;
    created_count: number;
    updated_count: number;
    skipped_count: number;
    failed_count: number;
    items: InsightDataSourceBatchCreateItem[];
}

export type InsightDataSourceUpdate = Partial<InsightDataSourceCreate>;

export interface InsightDataSourceListParams {
    page?: number;
    size?: number;
    keyword?: string;
    source_type?: string;
    status?: string;
    monitor_config_id?: number;
    execution_role?: string;
    channel_id?: number;
}

export interface InsightMonitorConfigRead {
    id: number;
    config_code: string;
    config_name: string;
    monitor_type: string;
    object_type: string;
    object_id?: number | null;
    object_name?: string | null;
    relation_type?: string | null;
    enabled_modules: string[];
    keywords: string[];
    excluded_keywords: string[];
    source_channel_ids: number[];
    monitor_strength: string;
    fetch_frequency: string;
    ai_review_prompt?: string | null;
    ai_review_policy: string;
    owner_user_id?: number | null;
    owner_dept_id?: number | null;
    visibility_scope: string;
    generation_mode: string;
    config_json?: Record<string, unknown> | null;
    status: string;
    execution_source_count: number;
    last_fetch_time?: string | null;
    last_success_time?: string | null;
    next_run_time?: string | null;
    schedule_enabled: boolean;
    last_schedule_status?: string | null;
    last_schedule_message?: string | null;
    consecutive_failure_count: number;
    last_failure_time?: string | null;
    auto_paused_reason?: string | null;
    create_time: string;
    update_time: string;
}

export interface InsightMonitorConfigCreate {
    config_code?: string | null;
    config_name: string;
    monitor_type?: string;
    object_type?: string;
    object_id?: number | null;
    object_name?: string | null;
    relation_type?: string | null;
    enabled_modules?: string[];
    keywords?: string[];
    excluded_keywords?: string[];
    source_channel_ids?: number[];
    monitor_strength?: string;
    fetch_frequency?: string;
    ai_review_prompt?: string | null;
    ai_review_policy?: string;
    visibility_scope?: string;
    generation_mode?: string;
    config_json?: Record<string, unknown> | null;
    status?: string;
}

export type InsightMonitorConfigUpdate = Partial<InsightMonitorConfigCreate>;

export interface InsightMonitorConfigListParams {
    page?: number;
    size?: number;
    keyword?: string;
    monitor_type?: string;
    status?: string;
}

export interface InsightLegacySourceSyncResponse {
    checked_count: number;
    created_config_count: number;
    linked_source_count: number;
    linked_channel_count: number;
    updated_role_count: number;
    skipped_count: number;
}

export interface InsightDataSourceExecutionLogParams {
    page?: number;
    size?: number;
    data_source_id?: number;
    status?: string;
    task_type?: string;
}

export interface InsightDataSourceExecuteRequest {
    keyword?: string | null;
    crawl_top_n?: number | null;
}

export interface InsightDataSourceExecuteResponse {
    data_source: InsightDataSourceRead;
    manual_result?: InsightManualUrlCrawlResponse | null;
    search_result?: InsightSearchDiscoveryResponse | null;
    search_results?: InsightSearchDiscoveryResponse[];
    execution_errors?: InsightDataSourceExecutionError[];
    auto_review_summary?: InsightAutoReviewSummary | null;
}

export interface InsightDataSourceImportItem {
    row_no: number;
    source_name: string;
    source_type: string;
    base_url?: string | null;
    company_id?: number | null;
    company_name?: string | null;
    keywords: string[];
    project_name?: string | null;
    channel_name?: string | null;
    source_document?: string | null;
    status: string;
    data_source_id?: number | null;
    message?: string | null;
}

export interface InsightDataSourceImportResponse {
    file_count: number;
    parsed_count: number;
    created_count: number;
    updated_count: number;
    skipped_count: number;
    failed_count: number;
    items: InsightDataSourceImportItem[];
    unsupported_channels: Array<Record<string, unknown>>;
}

export interface InsightDataSourceBulkActionRequest {
    data_source_ids: number[];
    action: string;
    status?: string | null;
    fetch_frequency?: string | null;
    schedule_enabled?: boolean | null;
    visibility_scope?: string | null;
    fetch_config_patch?: Record<string, unknown> | null;
    execute_crawl_top_n?: number | null;
}

export interface InsightDataSourceBulkActionResponse {
    action: string;
    requested_count: number;
    success_count: number;
    failed_count: number;
    items: Array<Record<string, unknown>>;
}

export interface InsightAutoReviewSummary {
    enabled: boolean;
    mode: string;
    checked_count: number;
    promoted_count: number;
    pooled_count: number;
    skipped_count: number;
    min_confidence?: number;
    auto_add_to_report_pool?: boolean;
    items?: Array<Record<string, unknown>>;
}

export interface InsightDataSourceExecutionError {
    keyword?: string;
    error?: string;
    [key: string]: unknown;
}

export interface InsightDataSourceScheduleExecution {
    data_source_id?: number | null;
    monitor_config_id?: number | null;
    source_name: string;
    status: string;
    message?: string | null;
    next_run_time?: string | null;
    found_count: number;
    candidate_count: number;
}

export interface InsightDataSourceScheduleRunResponse {
    checked_count: number;
    due_count: number;
    executed_count: number;
    failed_count: number;
    executions: InsightDataSourceScheduleExecution[];
}

export interface InsightSchedulerStatusRead {
    enabled: boolean;
    running: boolean;
    interval_seconds: number;
    batch_limit: number;
    startup_delay_seconds: number;
    advisory_lock_id: number;
    scheduler_user_id: number;
    failure_pause_threshold: number;
    config_health: string;
    config_warnings: string[];
    config_recommendations: string[];
    last_tick_at?: string | null;
    last_success_at?: string | null;
    next_tick_at?: string | null;
    last_error?: string | null;
    last_result?: Record<string, unknown> | null;
}

export interface InsightPage<T> {
    total: number;
    items: T[];
    page: number;
    size: number;
}

export interface InsightTaskRead {
    id: number;
    task_uid: string;
    task_type: string;
    status: string;
    progress: number;
    data_source_id?: number | null;
    monitor_config_id?: number | null;
    source_channel_id?: number | null;
    intelligence_id?: number | null;
    report_id?: number | null;
    started_at?: string | null;
    finished_at?: string | null;
    retry_count?: number;
    input_payload?: Record<string, unknown> | null;
    output_payload?: Record<string, unknown> | null;
    error_message?: string | null;
    create_time: string;
    update_time: string;
}

export interface InsightCrawlResultRead {
    id: number;
    task_id: number;
    data_source_id?: number | null;
    monitor_config_id?: number | null;
    source_channel_id?: number | null;
    channel: string;
    query_text?: string | null;
    source_url: string;
    source_title?: string | null;
    snippet?: string | null;
    raw_html_object_path?: string | null;
    markdown_content?: string | null;
    published_at?: string | null;
    dedupe_hash?: string | null;
    crawl_metadata?: Record<string, unknown> | null;
    status: string;
    error_message?: string | null;
    create_time: string;
    update_time: string;
}

export interface InsightIntelligenceCandidateRead {
    id: number;
    crawl_result_id: number;
    candidate_title: string;
    candidate_summary?: string | null;
    subject_type: string;
    subject_name?: string | null;
    company_id?: number | null;
    intelligence_type?: string | null;
    suggested_tags?: Array<{ name?: string; source?: string } & Record<string, unknown>> | null;
    quality_report?: Record<string, unknown> | null;
    quality_score?: number | null;
    quality_issues?: string[];
    quality_auto_ignore?: boolean;
    confidence?: number;
    promoted_intelligence_id?: number | null;
    review_status: string;
    status: string;
    create_time: string;
    update_time: string;
}

export interface InsightIntelligenceCandidateListItem extends InsightIntelligenceCandidateRead {
    source_url?: string | null;
    source_title?: string | null;
    source_channel?: string | null;
    source_publish_time?: string | null;
    query_text?: string | null;
}

export interface InsightCandidateListParams {
    page?: number;
    size?: number;
    keyword?: string;
    review_status?: string;
    subject_type?: string;
    intelligence_type?: string;
    data_source_id?: number;
}

export interface InsightIntelligenceRead {
    id: number;
    intelligence_uid: string;
    title: string;
    summary?: string | null;
    company_id?: number | null;
    subject_type: string;
    subject_id?: number | null;
    subject_name?: string | null;
    intelligence_type: string;
    business_domain?: string | null;
    importance_level: string;
    sentiment: string;
    publish_time?: string | null;
    capture_time?: string | null;
    review_status: string;
    visibility_scope: string;
    status: string;
    create_time: string;
    update_time: string;
}

export interface InsightIntelligenceSourceRead {
    id: number;
    intelligence_id: number;
    data_source_id?: number | null;
    source_type: string;
    source_url?: string | null;
    source_title?: string | null;
    source_author?: string | null;
    source_publish_time?: string | null;
    content_excerpt?: string | null;
    file_object_path?: string | null;
    credibility_score: number;
    source_metadata?: Record<string, unknown> | null;
    create_time: string;
    update_time: string;
}

export interface InsightIntelligenceSourceCreate {
    data_source_id?: number | null;
    source_type?: string;
    source_url?: string | null;
    source_title?: string | null;
    source_author?: string | null;
    source_publish_time?: string | null;
    content_excerpt?: string | null;
    file_object_path?: string | null;
    credibility_score?: number;
    source_metadata?: Record<string, unknown> | null;
}

export interface InsightIntelligenceListItem extends InsightIntelligenceRead {
    primary_source_url?: string | null;
    primary_source_title?: string | null;
    primary_source_type?: string | null;
    source_count: number;
    suggested_tags?: Array<{ name?: string; source?: string } & Record<string, unknown>> | null;
}

export interface InsightIntelligenceDetail extends InsightIntelligenceRead {
    content?: string | null;
    raw_payload?: Record<string, unknown> | null;
    sources: InsightIntelligenceSourceRead[];
}

export interface InsightIntelligenceListParams {
    page?: number;
    size?: number;
    keyword?: string;
    subject_type?: string;
    intelligence_type?: string;
    visibility_scope?: string;
    company_id?: number;
    sys_company_id?: number;
    project_name?: string;
    sentiment?: string;
    tag?: string;
    data_source_id?: number;
    date_from?: string;
    date_to?: string;
}

export interface InsightIntelligenceCreate {
    title: string;
    summary?: string | null;
    content?: string | null;
    company_id?: number | null;
    subject_type?: string;
    subject_id?: number | null;
    subject_name?: string | null;
    data_source_id?: number | null;
    intelligence_type?: string;
    business_domain?: string | null;
    importance_level?: string;
    sentiment?: string;
    publish_time?: string | null;
    visibility_scope?: string;
    suggested_tags?: Array<{ name?: string; source?: string } & Record<string, unknown>> | null;
    source?: InsightIntelligenceSourceCreate | null;
}

export interface InsightIntelligenceUpdate extends Partial<Omit<InsightIntelligenceCreate, "source">> {
    status?: string;
}

export interface InsightVisibilityRuleCreate {
    principal_type: string;
    principal_id?: number | null;
    permission?: string;
    grant_type?: string;
    effective_from?: string | null;
    effective_to?: string | null;
}

export interface InsightVisibilityRuleRead {
    id: number;
    target_type: string;
    target_id: number;
    principal_type: string;
    principal_id?: number | null;
    permission: string;
    grant_type: string;
    effective_from?: string | null;
    effective_to?: string | null;
    status: string;
    create_time: string;
    update_time: string;
}

export interface InsightPoolUpsertRequest {
    pool_type?: string;
    folder_name?: string | null;
    note?: string | null;
}

export interface InsightUserIntelligencePoolRead {
    id: number;
    user_id: number;
    intelligence_id: number;
    pool_type: string;
    folder_name?: string | null;
    note?: string | null;
    sort_no: number;
    status: string;
    create_time: string;
    update_time: string;
}

export interface InsightCandidateReviewRequest {
    review_comment?: string | null;
}

export interface InsightCandidatePromoteRequest extends InsightCandidateReviewRequest {
    visibility_scope?: string;
    importance_level?: string;
    business_domain?: string | null;
}

export interface InsightCandidateReviewResponse {
    candidate: InsightIntelligenceCandidateRead;
    intelligence?: InsightIntelligenceRead | null;
}

export interface InsightAssetRead {
    id: number;
    asset_uid: string;
    asset_type: string;
    source_kind: string;
    intelligence_id?: number | null;
    candidate_id?: number | null;
    crawl_result_id?: number | null;
    data_source_id?: number | null;
    company_id?: number | null;
    subject_type: string;
    subject_id?: number | null;
    subject_name?: string | null;
    title: string;
    summary?: string | null;
    source_url?: string | null;
    source_title?: string | null;
    source_channel?: string | null;
    publish_time?: string | null;
    intelligence_type?: string | null;
    business_value?: string | null;
    importance_level: string;
    sentiment: string;
    confidence: number;
    tags: Array<Record<string, unknown>>;
    entities: Array<Record<string, unknown>>;
    related_products: string[];
    opportunities: string[];
    risks: string[];
    keywords: string[];
    evidence?: string | null;
    review_reason?: string | null;
    embedding_status: string;
    graph_status: string;
    visibility_scope: string;
    status: string;
    create_time: string;
    update_time: string;
}

export interface InsightAssetSearchRequest {
    query: string;
    top_k?: number;
    include_candidates?: boolean;
    company_id?: number | null;
    subject_type?: string | null;
    intelligence_type?: string | null;
    date_from?: string | null;
    date_to?: string | null;
}

export interface InsightAssetSearchHit {
    asset: InsightAssetRead;
    score: number;
    vector_score?: number | null;
    keyword_score?: number | null;
    match_reason?: string | null;
}

export interface InsightAssetSearchResponse {
    query: string;
    hits: InsightAssetSearchHit[];
    generation_mode: string;
}

export interface InsightFormalAssetBackfillRequest {
    limit?: number;
    include_inactive?: boolean;
    reindex_existing_failed?: boolean;
}

export interface InsightFormalAssetBackfillResponse {
    requested_limit: number;
    scanned_count: number;
    created_count: number;
    updated_count: number;
    indexed_count: number;
    failed_count: number;
    remaining_count: number;
    items: Array<Record<string, unknown>>;
}

export interface InsightGraphParams {
    company_id?: number;
    asset_id?: number;
    limit?: number;
}

export interface InsightGraphNodeRead {
    id: number;
    node_uid: string;
    node_type: string;
    node_name: string;
    canonical_name?: string | null;
    source_asset_id?: number | null;
    company_id?: number | null;
    node_metadata: Record<string, unknown>;
    status: string;
    create_time: string;
    update_time: string;
}

export interface InsightGraphEdgeRead {
    id: number;
    edge_uid: string;
    source_node_id: number;
    target_node_id: number;
    relation_type: string;
    source_asset_id?: number | null;
    confidence: number;
    evidence_text?: string | null;
    edge_metadata: Record<string, unknown>;
    status: string;
    create_time: string;
    update_time: string;
}

export interface InsightGraphResponse {
    nodes: InsightGraphNodeRead[];
    edges: InsightGraphEdgeRead[];
}

export interface InsightIntelligenceBulkActionRequest {
    target_type?: "candidate" | "intelligence" | string;
    candidate_ids?: number[];
    intelligence_ids?: number[];
    action: string;
    review_comment?: string | null;
    visibility_scope?: string | null;
    importance_level?: string | null;
    business_domain?: string | null;
    pool_type?: string | null;
    folder_name?: string | null;
    tags?: Array<Record<string, unknown>> | null;
    sentiment?: string | null;
    status?: string | null;
}

export interface InsightIntelligenceBulkActionResponse {
    action: string;
    target_type: string;
    requested_count: number;
    success_count: number;
    failed_count: number;
    items: Array<Record<string, unknown>>;
}

export interface InsightAssistantChatRequest {
    question: string;
    keyword?: string | null;
    company_id?: number | null;
    sys_company_id?: number | null;
    project_name?: string | null;
    sentiment?: string | null;
    tag?: string | null;
    intelligence_type?: string | null;
    data_source_id?: number | null;
    date_from?: string | null;
    date_to?: string | null;
    limit?: number;
}

export interface InsightAssistantCitation {
    intelligence_id: number;
    title: string;
    source_url?: string | null;
    source_title?: string | null;
    publish_time?: string | null;
    summary?: string | null;
}

export interface InsightAssistantChatResponse {
    answer: string;
    citations: InsightAssistantCitation[];
    evidence_count: number;
    no_evidence: boolean;
    generation_mode?: string;
}

export interface InsightDeepResearchRequest extends InsightAssistantChatRequest {
    save_report?: boolean;
    report_title?: string | null;
}

export interface InsightEvidenceMatrixItem {
    intelligence_id: number;
    title: string;
    evidence: string;
    source_url?: string | null;
    publish_time?: string | null;
}

export interface InsightDeepResearchResponse {
    title: string;
    conclusion: string;
    findings: string[];
    opportunities: string[];
    risks: string[];
    evidence_matrix: InsightEvidenceMatrixItem[];
    follow_up_questions: string[];
    citations: InsightAssistantCitation[];
    report_id?: number | null;
    generation_mode?: string;
}

export interface InsightManualUrlCrawlResponse {
    task: InsightTaskRead;
    crawl_result: InsightCrawlResultRead;
    candidate: InsightIntelligenceCandidateRead;
}

export interface InsightSearchDiscoveryRequest {
    query: string;
    channels: string[];
    freshness?: string | null;
    max_results: number;
    crawl_top_n: number;
    data_source_id?: number | null;
    monitor_config_id?: number | null;
    source_channel_id?: number | null;
    include_keywords?: string[];
    exclude_keywords?: string[];
    filter_prompt?: string | null;
    enable_llm_filter?: boolean;
    llm_min_score?: number | null;
    create_candidate_from_hits?: boolean;
}

export interface InsightSearchHitRead {
    channel: string;
    title: string;
    url: string;
    snippet?: string | null;
    published_at?: string | null;
    raw?: Record<string, unknown> | null;
}

export interface InsightSearchDiscoveryResponse {
    task: InsightTaskRead;
    hits: InsightSearchHitRead[];
    discovered_results: InsightCrawlResultRead[];
    crawled_results: InsightCrawlResultRead[];
    candidates: InsightIntelligenceCandidateRead[];
}
