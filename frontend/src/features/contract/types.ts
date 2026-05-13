export const ContractStatus = {
    UPLOADING: "uploading",
    ANALYZING: "analyzing",
    ANALYSIS_COMPLETED: "analysis_completed",
    ANALYSIS_FAILED: "analysis_failed",
} as const;

export type ContractStatus = (typeof ContractStatus)[keyof typeof ContractStatus];

export const TrafficLight = {
    GREEN: "green",
    YELLOW: "yellow",
    RED: "red",
    NONE: "none",
} as const;

export type TrafficLight = (typeof TrafficLight)[keyof typeof TrafficLight];

export const RiskLevel = {
    CRITICAL: "critical",
    WARNING: "warning",
    INFO: "info",
} as const;

export type RiskLevel = (typeof RiskLevel)[keyof typeof RiskLevel];

export interface ContractAuditLog {
    id: number;
    risk_level: RiskLevel;
    finding_summary: string;
    finding_detail: string;
    quote_text?: string;
    page_num?: number;
    is_accepted: boolean;
}

export interface Contract {
    id: number;
    title: string;
    serial_number?: string;
    file_version: string;
    contract_type: string;
    status: ContractStatus;
    traffic_light: TrafficLight;
    create_time: string;
    initiator_id?: number;
    file_url?: string;
    analysis_summary?: Record<string, any>;
    audit_logs?: ContractAuditLog[];
}

export interface ContractCreatePayload {
    title: string;
    contract_type: string;
    initiator_id: number;
    file: File;
}
