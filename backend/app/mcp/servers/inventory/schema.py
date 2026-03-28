from pydantic import BaseModel, Field
from typing import Optional

class MaterialQuerySchema(BaseModel):
    material_code: Optional[str] = Field(None, description="物料编码，支持模糊匹配")
    storage_bin: Optional[str] = Field(None, description="仓位/库位编码")

class MaterialSearchSchema(BaseModel):
    query_text: str = Field(..., description="搜索关键词，用于全文检索物料描述 (例如: '红色安全帽')")
    limit: int = Field(10, description="返回结果数量限制")
