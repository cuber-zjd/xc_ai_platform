import { useState } from "react";
import { useContracts, useUploadContract } from "../hooks/useContract";
import { ContractStatus, TrafficLight } from "../types";
import { Button } from "@/components/ui/button";
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Loader2, Plus, FileText, ExternalLink } from "lucide-react";
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { toast } from "sonner";
import { useNavigate } from "react-router-dom";

export function ContractListPage() {
    const { data: contracts, isLoading } = useContracts();
    const uploadMutation = useUploadContract();
    const navigate = useNavigate();

    const [isOpen, setIsOpen] = useState(false);
    const [formData, setFormData] = useState({
        title: "",
        contract_type: "General",
        file: null as File | null,
    });

    const handleUpload = async () => {
        if (!formData.file || !formData.title) {
            toast.error("Please fill all fields");
            return;
        }

        try {
            await uploadMutation.mutateAsync({
                title: formData.title,
                contract_type: formData.contract_type,
                initiator_id: 1, // Mock
                file: formData.file,
            });
            toast.success("Upload successful! Analysis started.");
            setIsOpen(false);
        } catch (e) {
            toast.error("Upload failed");
        }
    };

    const statusColor = (status: ContractStatus) => {
        switch (status) {
            case ContractStatus.ANALYSIS_COMPLETED:
                return "default"; // black
            case ContractStatus.ANALYSIS_FAILED:
                return "destructive";
            default:
                return "secondary";
        }
    };

    const trafficLightBadge = (light: TrafficLight) => {
        const colors = {
            [TrafficLight.RED]: "bg-red-500 hover:bg-red-600",
            [TrafficLight.YELLOW]: "bg-yellow-500 hover:bg-yellow-600",
            [TrafficLight.GREEN]: "bg-green-500 hover:bg-green-600",
            [TrafficLight.NONE]: "bg-gray-300",
        };

        return (
            <Badge className={`${colors[light]} text-white border-0`}>
                {light.toUpperCase()}
            </Badge>
        );
    };

    return (
        <div className="p-8 space-y-6">
            <div className="flex justify-between items-center">
                <div>
                    <h1 className="text-3xl font-bold tracking-tight">合同管理</h1>
                    <p className="text-muted-foreground mt-2">
                        AI 智能审查系统 - 支持静默预审与风险预警
                    </p>
                </div>

                <Dialog open={isOpen} onOpenChange={setIsOpen}>
                    <DialogTrigger asChild>
                        <Button>
                            <Plus className="mr-2 h-4 w-4" /> 上传合同
                        </Button>
                    </DialogTrigger>
                    <DialogContent>
                        <DialogHeader>
                            <DialogTitle>上传合同文件</DialogTitle>
                        </DialogHeader>
                        <div className="space-y-4 py-4">
                            <div className="space-y-2">
                                <Label>合同标题</Label>
                                <Input
                                    value={formData.title}
                                    onChange={(e) => setFormData({ ...formData, title: e.target.value })}
                                    placeholder="e.g. 2024年度采购协议"
                                />
                            </div>
                            <div className="space-y-2">
                                <Label>合同类型</Label>
                                <Select
                                    value={formData.contract_type}
                                    onValueChange={(v) => setFormData({ ...formData, contract_type: v })}
                                >
                                    <SelectTrigger>
                                        <SelectValue />
                                    </SelectTrigger>
                                    <SelectContent>
                                        <SelectItem value="General">通用合同</SelectItem>
                                        <SelectItem value="Purchase">采购合同</SelectItem>
                                        <SelectItem value="Sales">销售合同</SelectItem>
                                        <SelectItem value="NDA">保密协议</SelectItem>
                                    </SelectContent>
                                </Select>
                            </div>
                            <div className="space-y-2">
                                <Label>文件附件</Label>
                                <Input
                                    type="file"
                                    onChange={(e) => setFormData({ ...formData, file: e.target.files?.[0] || null })}
                                />
                            </div>
                            <Button
                                onClick={handleUpload}
                                className="w-full"
                                disabled={uploadMutation.isPending}
                            >
                                {uploadMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                                开始智审
                            </Button>
                        </div>
                    </DialogContent>
                </Dialog>
            </div>

            <div className="rounded-md border bg-card">
                <Table>
                    <TableHeader>
                        <TableRow>
                            <TableHead>标题</TableHead>
                            <TableHead>类型</TableHead>
                            <TableHead>状态</TableHead>
                            <TableHead>AI 风险评估</TableHead>
                            <TableHead>创建时间</TableHead>
                            <TableHead className="text-right">操作</TableHead>
                        </TableRow>
                    </TableHeader>
                    <TableBody>
                        {isLoading ? (
                            <TableRow>
                                <TableCell colSpan={6} className="h-24 text-center">
                                    <Loader2 className="h-6 w-6 animate-spin mx-auto text-muted-foreground" />
                                </TableCell>
                            </TableRow>
                        ) : contracts?.map((contract) => (
                            <TableRow key={contract.id} className="group">
                                <TableCell className="font-medium flex items-center gap-2">
                                    <FileText className="h-4 w-4 text-blue-500" />
                                    {contract.title}
                                </TableCell>
                                <TableCell>{contract.contract_type}</TableCell>
                                <TableCell>
                                    <Badge variant={statusColor(contract.status)}>
                                        {contract.status === ContractStatus.ANALYZING && (
                                            <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                                        )}
                                        {contract.status}
                                    </Badge>
                                </TableCell>
                                <TableCell>{trafficLightBadge(contract.traffic_light)}</TableCell>
                                <TableCell className="text-muted-foreground text-sm">
                                    {new Date(contract.create_time).toLocaleDateString()}
                                </TableCell>
                                <TableCell className="text-right">
                                    <Button
                                        variant="ghost"
                                        size="sm"
                                        onClick={() => navigate(`/contract/${contract.id}`)}
                                    >
                                        查看详情 <ExternalLink className="ml-1 h-3 w-3" />
                                    </Button>
                                </TableCell>
                            </TableRow>
                        ))}
                    </TableBody>
                </Table>
            </div>
        </div>
    );
}
