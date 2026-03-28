import { apiClient } from "@/api/client";
import type { MaterialItem, WarehouseData } from "./types";

export async function getWarehouseData(): Promise<WarehouseData> {
  return apiClient.get("/inventory/warehouse");
}

export async function queryMaterials(query: string, limit: number = 20): Promise<MaterialItem[]> {
  return apiClient.post("/inventory/query", { query, limit });
}
