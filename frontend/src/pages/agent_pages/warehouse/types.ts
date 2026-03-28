export interface MaterialItem {
  id: number;
  material_code: string;
  material_desc?: string;
  storage_loc?: string;
  storage_bin?: string;
  unrestricted_qty: number;
  base_uom?: string;
  material_group?: string;
  net_amount: number;
}

export interface WarehouseData {
  materials: MaterialItem[];
  total: number;
}

// 仓库架构常量
export const ROWS = 6;
export const GROUPS_PER_ROW = 4;
export const LEVELS = 4;
export const MAX_CELLS = 9;

export interface StorageBinPosition {
  floor: number;
  row: number;
  group: number;
  level: number;
  cell: number;
}

export function parseStorageBin(storageBin: string): StorageBinPosition | null {
  const match = storageBin.match(/(\d+)楼(\d+)排(\d+)组(\d+)层(\d+)格/);
  if (match) {
    return {
      floor: parseInt(match[1]),
      row: parseInt(match[2]),
      group: parseInt(match[3]),
      level: parseInt(match[4]),
      cell: parseInt(match[5]),
    };
  }
  return null;
}

export function getBinKey(pos: StorageBinPosition): string {
  // 仅计算在同一楼层内的相对 ID，因为 3D 每次渲染一个楼层
  const gIdx = (pos.row - 1) * GROUPS_PER_ROW + pos.group;
  return `${gIdx}-${pos.level}-${pos.cell}`;
}
