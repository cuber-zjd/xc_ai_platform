import { useParams } from "react-router-dom";
import { useContract } from "../hooks/useContract";
import { AuditSidecar } from "../components/AuditSidecar";
import { Loader2 } from "lucide-react";

export function ContractSidecarPage() {
    const { id } = useParams();
    const contractId = Number(id);
    const { data: contract, isLoading } = useContract(contractId);

    // Communication with parent window (CMS)
    const handleRiskClick = (log: any) => {
        // Post message to parent CMS or local OnlyOffice iframe sibling
        window.parent.postMessage({ type: 'CONTRACT_RISK_CLICK', log }, '*');
    };

    if (isLoading || !contract) {
        return (
            <div className="h-screen flex items-center justify-center bg-background">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
        );
    }

    return (
        <div className="h-screen w-full bg-background">
            <AuditSidecar
                logs={contract.audit_logs || []}
                onRiskClick={handleRiskClick}
                className="h-full border-none"
            />
        </div>
    );
}
