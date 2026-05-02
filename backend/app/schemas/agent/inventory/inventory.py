from typing import Optional, List
from pydantic import BaseModel


class MaterialQueryRequest(BaseModel):
    """自然语言查询物料请求"""
    query: str
    limit: int = 20


class MaterialItem(BaseModel):
    """物料项"""
    id: int
    material_code: str
    material_desc: Optional[str] = None
    storage_loc: Optional[str] = None
    storage_bin: Optional[str] = None
    unrestricted_qty: float = 0
    base_uom: Optional[str] = None
    material_group: Optional[str] = None
    net_amount: float = 0


class WarehouseData(BaseModel):
    """仓库完整数据（用于3D建模）"""
    materials: List[MaterialItem]
    total: int
