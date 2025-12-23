import type { ContractAuditLog } from "../types";
import { RiskLevel } from "../types";
import { ScrollArea } from "@/components/ui/scroll-area";
import { AlertCircle, AlertTriangle, Info, CheckCircle2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";

interface Props {
    logs: ContractAuditLog[];
    onRiskClick?: (log: ContractAuditLog) => void;
    className?: string;
}

export function AuditSidecar({ logs, onRiskClick, className }: Props) {
    const criticals = logs.filter(l => l.risk_level === RiskLevel.CRITICAL);
    const warnings = logs.filter(l => l.risk_level === RiskLevel.WARNING);
    const infos = logs.filter(l => l.risk_level === RiskLevel.INFO);

    const RiskItem = ({ log }: { log: ContractAuditLog }) => (
        <div
            onClick={() => onRiskClick?.(log)}
            className="p-3 mb-2 rounded-lg border bg-card hover:bg-accent cursor-pointer transition-colors text-sm group"
        >
            <div className="font-medium flex justify-between">
                <span>{log.finding_summary}</span>
                {log.page_num && <span className="text-xs text-muted-foreground">P{log.page_num}</span>}
            </div>
            <div className="text-muted-foreground mt-1 text-xs line-clamp-2 group-hover:line-clamp-none">
                {log.finding_detail}
            </div>
        </div>
    );

    return (
        <div className={cn("flex flex-col h-full bg-background border-l", className)}>
            <div className="p-4 border-b bg-muted/20">
                <h2 className="font-semibold flex items-center gap-2">
                    <CheckCircle2 className="h-5 w-5 text-primary" />
                    智审结果
                </h2>
                <div className="flex gap-2 mt-3">
                    <div className="flex-1 bg-red-100 dark:bg-red-900/20 text-red-600 rounded p-2 text-center text-xs font-bold">
                        {criticals.length} 高危
                    </div>
                    <div className="flex-1 bg-yellow-100 dark:bg-yellow-900/20 text-yellow-600 rounded p-2 text-center text-xs font-bold">
                        {warnings.length} 警告
                    </div>
                </div>
            </div>

            <ScrollArea className="flex-1 p-4">
                <Accordion type="multiple" defaultValue={["critical", "warning"]}>

                    {criticals.length > 0 && (
                        <AccordionItem value="critical">
                            <AccordionTrigger className="text-red-600 py-2">
                                <span className="flex items-center gap-2">
                                    <AlertCircle className="h-4 w-4" /> 高危风险
                                </span>
                            </AccordionTrigger>
                            <AccordionContent>
                                {criticals.map(log => <RiskItem key={log.id} log={log} />)}
                            </AccordionContent>
                        </AccordionItem>
                    )}

                    {warnings.length > 0 && (
                        <AccordionItem value="warning">
                            <AccordionTrigger className="text-yellow-600 py-2">
                                <span className="flex items-center gap-2">
                                    <AlertTriangle className="h-4 w-4" /> 风险预警
                                </span>
                            </AccordionTrigger>
                            <AccordionContent>
                                {warnings.map(log => <RiskItem key={log.id} log={log} />)}
                            </AccordionContent>
                        </AccordionItem>
                    )}

                    {infos.length > 0 && (
                        <AccordionItem value="info">
                            <AccordionTrigger className="text-blue-500 py-2">
                                <span className="flex items-center gap-2">
                                    <Info className="h-4 w-4" /> 优化建议
                                </span>
                            </AccordionTrigger>
                            <AccordionContent>
                                {infos.map(log => <RiskItem key={log.id} log={log} />)}
                            </AccordionContent>
                        </AccordionItem>
                    )}

                </Accordion>
            </ScrollArea>
        </div>
    );
}
