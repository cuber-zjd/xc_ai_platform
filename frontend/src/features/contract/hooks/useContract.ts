import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/api/client";
import type { Contract, ContractCreatePayload } from "../types";
import { ContractStatus } from "../types";

const BASE_URL = "/contracts";

export function useContracts(skip = 0, limit = 10) {
    return useQuery({
        queryKey: ["contracts", skip, limit],
        queryFn: async () => {
            const response = await apiClient.get<Contract[]>(BASE_URL, {
                params: { skip, limit },
            });
            return response as any as Contract[];
        },
    });
}

export function useContract(id: number, enabled = true) {
    return useQuery({
        queryKey: ["contract", id],
        queryFn: async () => {
            const response = await apiClient.get<Contract>(`${BASE_URL}/${id}`);
            return response as any as Contract;
        },
        enabled,
        refetchInterval: (query) => {
            const data = query.state.data;
            if (data && (data.status === ContractStatus.UPLOADING || data.status === ContractStatus.ANALYZING)) {
                return 2000; // Poll every 2s if processing
            }
            return false;
        },
    });
}

export function useUploadContract() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async (payload: ContractCreatePayload) => {
            const formData = new FormData();
            formData.append("file", payload.file);
            formData.append("title", payload.title);
            formData.append("contract_type", payload.contract_type);
            formData.append("initiator_id", String(payload.initiator_id));

            const response = await apiClient.post<Contract>(`${BASE_URL}/upload`, formData, {
                headers: {
                    "Content-Type": "multipart/form-data",
                },
            });
            return response;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ["contracts"] });
        },
    });
}

// OnlyOffice 编辑器配置类型
export interface EditorConfig {
    config: {
        document: {
            fileType: string;
            key: string;
            title: string;
            url: string;
            permissions: Record<string, boolean>;
        };
        documentType: string;
        editorConfig: Record<string, any>;
        token: string;
        type: string;
        height: string;
        width: string;
    };
    server_url: string;
    api_url: string;
}

export function useEditorConfig(contractId: number, enabled = true) {
    return useQuery({
        queryKey: ["editor-config", contractId],
        queryFn: async () => {
            const response = await apiClient.get<EditorConfig>(`${BASE_URL}/${contractId}/editor-config`);
            return response as any as EditorConfig;
        },
        enabled,
        staleTime: 1000 * 60 * 5, // 缓存 5 分钟
    });
}
