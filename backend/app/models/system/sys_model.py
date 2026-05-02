"""
sys_model - AI 模型配置表

用于存储各 LLM 供应商的模型配置信息，支持：
- 按模型名称调用
- 按模型级别调用（自动选择最优模型）
- 熔断降级（故障时自动切换到同级或下级模型）
"""

from typing import Optional

from sqlmodel import SQLModel, Field

from app.models.base import BaseDBModel


class SysModelBase(SQLModel):
    """模型配置基础字段"""

    # 基础信息
    model_name: str = Field(
        index=True, unique=True, description="模型显示名称，如 DeepSeek-V3"
    )
    model_code: str = Field(
        index=True, description="模型调用代码/端点ID，如 ep-xxx 或 gpt-4o"
    )
    provider: str = Field(
        index=True, description="供应商标识，如 volcengine / openai / zhipu / deepseek"
    )

    # 连接配置
    api_key: str = Field(description="API 密钥")
    base_url: str = Field(description="API 基础地址，如 https://ark.cn-beijing.volces.com/api/v3")

    # 模型分级与分类
    model_level: int = Field(
        default=3, index=True,
        description="模型级别：1=顶级(如 GPT-4o), 2=高级(如 DeepSeek-V3), 3=标准(如 GLM-4), 4=轻量(如 GLM-4-Flash)"
    )
    model_type: str = Field(
        default="chat", index=True,
        description="模型类型：chat / embedding / vision / reranker"
    )
    capability: Optional[str] = Field(
        default="general", index=True,
        description="能力标签：complex-reasoning / general / fast / code"
    )

    # 模型参数默认值
    max_tokens: Optional[int] = Field(
        default=4096, description="最大输出 token 数"
    )
    default_temperature: float = Field(
        default=0.0, description="默认温度参数"
    )

    # 调度控制
    priority: int = Field(
        default=100, index=True,
        description="同级别内的优先级，数字越小越优先"
    )
    is_enabled: bool = Field(
        default=True, index=True,
        description="是否启用"
    )

    # 状态
    status: int = Field(default=1, description="状态：1=正常, 0=禁用")


class SysModel(BaseDBModel, SysModelBase, table=True):
    """AI 模型配置数据库表"""

    __tablename__ = "sys_model"
