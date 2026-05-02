"""
模型配置相关 Schema
"""

from typing import Optional

from pydantic import BaseModel


class SysModelCreate(BaseModel):
    """创建模型配置"""

    model_name: str
    model_code: str
    provider: str
    api_key: str
    base_url: str
    model_level: int = 3
    model_type: str = "chat"
    capability: Optional[str] = "general"
    max_tokens: Optional[int] = 4096
    default_temperature: float = 0.0
    priority: int = 100
    is_enabled: bool = True
    status: int = 1
    comment: Optional[str] = None


class SysModelUpdate(BaseModel):
    """更新模型配置"""

    model_name: Optional[str] = None
    model_code: Optional[str] = None
    provider: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model_level: Optional[int] = None
    model_type: Optional[str] = None
    capability: Optional[str] = None
    max_tokens: Optional[int] = None
    default_temperature: Optional[float] = None
    priority: Optional[int] = None
    is_enabled: Optional[bool] = None
    status: Optional[int] = None
    comment: Optional[str] = None


class SysModelRead(BaseModel):
    """模型配置读取（隐藏 API Key）"""

    id: int
    model_name: str
    model_code: str
    provider: str
    base_url: str
    model_level: int
    model_type: str
    capability: Optional[str]
    max_tokens: Optional[int]
    default_temperature: float
    priority: int
    is_enabled: bool
    status: int
    comment: Optional[str]

    # 隐藏完整 API Key，只展示后4位
    api_key_masked: str = ""

    class Config:
        from_attributes = True
