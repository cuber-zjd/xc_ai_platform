"""
AI 模型配置管理 API

提供模型配置的 CRUD、熔断器状态查看和缓存管理等接口。
"""

from typing import Any

from fastapi import APIRouter, Depends
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api import deps
from app.core.llm_factory import LLMFactory
from app.db.session import get_db
from app.models.system.sys_user import SysUser
from app.schemas.result import Result
from app.schemas.system.model_schema import SysModelCreate, SysModelRead, SysModelUpdate
from app.services.system.model_service import model_service

router = APIRouter()


@router.get("", response_model=Result)
async def list_models(
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(deps.get_current_user),
) -> Any:
    """获取所有模型配置"""
    models = await model_service.list_models(db)

    # 转换为 Read Schema（隐藏 API Key）
    result = []
    for m in models:
        read = SysModelRead(
            id=m.id,
            model_name=m.model_name,
            model_code=m.model_code,
            provider=m.provider,
            base_url=m.base_url,
            model_level=m.model_level,
            model_type=m.model_type,
            capability=m.capability,
            max_tokens=m.max_tokens,
            default_temperature=m.default_temperature,
            priority=m.priority,
            is_enabled=m.is_enabled,
            status=m.status,
            comment=m.comment,
            api_key_masked=f"****{m.api_key[-4:]}" if len(m.api_key) > 4 else "****",
        )
        result.append(read)

    return Result.success(data=result)


@router.post("", response_model=Result)
async def create_model(
    data: SysModelCreate,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(deps.get_current_user),
) -> Any:
    """创建模型配置"""
    model = await model_service.create_model(db, data)
    # 新增模型后使缓存失效
    LLMFactory.invalidate_cache()
    return Result.success(data={"id": model.id, "model_name": model.model_name})


@router.put("/{model_id}", response_model=Result)
async def update_model(
    model_id: int,
    data: SysModelUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(deps.get_current_user),
) -> Any:
    """更新模型配置"""
    model = await model_service.update_model(db, model_id, data)
    if not model:
        return Result.fail(code=404, msg="模型配置不存在")
    # 更新后使缓存失效
    LLMFactory.invalidate_cache()
    return Result.success(data={"id": model.id, "model_name": model.model_name})


@router.delete("/{model_id}", response_model=Result)
async def delete_model(
    model_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(deps.get_current_user),
) -> Any:
    """删除模型配置"""
    success = await model_service.delete_model(db, model_id)
    if not success:
        return Result.fail(code=404, msg="模型配置不存在")
    # 删除后使缓存失效
    LLMFactory.invalidate_cache()
    return Result.success(msg="删除成功")


@router.get("/circuit-breakers", response_model=Result)
async def get_circuit_breakers(
    current_user: SysUser = Depends(deps.get_current_user),
) -> Any:
    """获取所有模型的熔断器状态"""
    status = LLMFactory.get_circuit_breaker_status()
    return Result.success(data=status)


@router.post("/circuit-breakers/reset", response_model=Result)
async def reset_circuit_breaker(
    model_name: str | None = None,
    current_user: SysUser = Depends(deps.get_current_user),
) -> Any:
    """重置熔断器（指定模型或全部）"""
    LLMFactory.reset_circuit_breaker(model_name)
    msg = f"已重置模型 {model_name} 的熔断器" if model_name else "已重置所有熔断器"
    return Result.success(msg=msg)


@router.post("/cache/invalidate", response_model=Result)
async def invalidate_cache(
    current_user: SysUser = Depends(deps.get_current_user),
) -> Any:
    """手动清除模型配置缓存"""
    LLMFactory.invalidate_cache()
    return Result.success(msg="缓存已清除")
