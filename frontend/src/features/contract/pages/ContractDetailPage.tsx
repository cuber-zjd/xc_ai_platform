import { useParams } from "react-router-dom";
import { useContract, useEditorConfig } from "../hooks/useContract";
import { OnlyOfficeViewer } from "../components/OnlyOfficeViewer";
import { AuditSidecar } from "../components/AuditSidecar";
import { useState } from "react";
import type { ContractAuditLog } from "../types";
import { Loader2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";

export function ContractDetailPage() {
    const { id } = useParams();
    const contractId = Number(id);
    const { data: contract, isLoading: contractLoading } = useContract(contractId);
    const { data: editorConfig, isLoading: configLoading } = useEditorConfig(contractId, !!contract);
    const [activeLog, setActiveLog] = useState<ContractAuditLog | null>(null);

    const isLoading = contractLoading || configLoading;

    if (isLoading || !contract) {
        return (
            <div className="h-screen flex items-center justify-center">
                <div className="text-center">
                    <Loader2 className="h-8 w-8 animate-spin mx-auto mb-2" />
                    <p className="text-muted-foreground">
                        {contractLoading ? "加载合同信息..." : "获取文档配置..."}
                    </p>
                </div>
            </div>
        );
    }

    return (
        <div className="flex h-[calc(100vh-64px)] overflow-hidden">
            {/* Left: Document Editor */}
            <div className="flex-1 relative flex flex-col">
                <div className="h-12 border-b flex items-center px-4 justify-between bg-background">
                    <div className="flex items-center gap-2">
                        <span className="font-semibold">{contract.title}</span>
                        <Badge variant="outline">{contract.status}</Badge>
                    </div>
                </div>
                <OnlyOfficeViewer
                    className="flex-1"
                    editorConfig={editorConfig}
                    highlightLog={activeLog}
                />
            </div>

            {/* Right: AI Sidecar */}
            <div className="w-[400px] border-l bg-background z-10 shadow-xl">
                <AuditSidecar
                    logs={contract.audit_logs || []}
                    onRiskClick={setActiveLog}
                    className="h-full"
                />
            </div>
        </div>
    );
}
