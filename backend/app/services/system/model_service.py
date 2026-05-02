"""
模型配置服务层

提供模型配置的 CRUD 操作以及按名称/级别查询等业务逻辑。
"""

from typing import Optional

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.logger import logger
from app.models.system.sys_model import SysModel
from app.schemas.system.model_schema import SysModelCreate, SysModelUpdate


class ModelService:
    """模型配置服务"""

    async def create_model(
        self, session: AsyncSession, data: SysModelCreate
    ) -> SysModel:
        """创建模型配置"""
        db_model = SysModel(**data.model_dump())
        session.add(db_model)
        await session.commit()
        await session.refresh(db_model)
        logger.info(f"创建模型配置: {db_model.model_name} (级别={db_model.model_level})")
        return db_model

    async def update_model(
        self, session: AsyncSession, model_id: int, data: SysModelUpdate
    ) -> SysModel | None:
        """更新模型配置"""
        db_model = await session.get(SysModel, model_id)
        if not db_model:
            return None
        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(db_model, key, value)
        session.add(db_model)
        await session.commit()
        await session.refresh(db_model)
        logger.info(f"更新模型配置: {db_model.model_name}")
        return db_model

    async def delete_model(self, session: AsyncSession, model_id: int) -> bool:
        """软删除模型配置"""
        db_model = await session.get(SysModel, model_id)
        if not db_model:
            return False
        db_model.is_deleted = 1
        session.add(db_model)
        await session.commit()
        logger.info(f"删除模型配置: {db_model.model_name}")
        return True

    async def get_model_by_id(
        self, session: AsyncSession, model_id: int
    ) -> SysModel | None:
        """根据 ID 查询模型"""
        return await session.get(SysModel, model_id)

    async def get_model_by_name(
        self, session: AsyncSession, model_name: str
    ) -> SysModel | None:
        """根据模型名称查询"""
        statement = select(SysModel).where(
            SysModel.model_name == model_name,
            SysModel.is_deleted == 0,
            SysModel.is_enabled == True,
        )
        result = await session.exec(statement)
        return result.first()

    async def get_all_enabled_models(
        self,
        session: AsyncSession,
        model_type: str = "chat",
    ) -> list[SysModel]:
        """获取所有启用的模型配置，按级别和优先级排序"""
        statement = (
            select(SysModel)
            .where(
                SysModel.is_deleted == 0,
                SysModel.is_enabled == True,
                SysModel.model_type == model_type,
            )
            .order_by(SysModel.model_level, SysModel.priority)
        )
        result = await session.exec(statement)
        return list(result.all())

    async def get_models_by_level(
        self,
        session: AsyncSession,
        level: int,
        model_type: str = "chat",
    ) -> list[SysModel]:
        """获取指定级别的所有启用模型，按优先级排序"""
        statement = (
            select(SysModel)
            .where(
                SysModel.model_level == level,
                SysModel.model_type == model_type,
                SysModel.is_deleted == 0,
                SysModel.is_enabled == True,
            )
            .order_by(SysModel.priority)
        )
        result = await session.exec(statement)
        return list(result.all())

    async def get_models_by_capability(
        self,
        session: AsyncSession,
        capability: str,
        model_type: str = "chat",
    ) -> list[SysModel]:
        """获取指定能力标签的所有启用模型，按级别和优先级排序"""
        statement = (
            select(SysModel)
            .where(
                SysModel.capability == capability,
                SysModel.model_type == model_type,
                SysModel.is_deleted == 0,
                SysModel.is_enabled == True,
            )
            .order_by(SysModel.model_level, SysModel.priority)
        )
        result = await session.exec(statement)
        return list(result.all())

    async def get_fallback_models(
        self,
        session: AsyncSession,
        current_level: int,
        model_type: str = "chat",
        exclude_names: list[str] | None = None,
    ) -> list[SysModel]:
        """
        获取降级候选模型列表

        策略：先找同级别其他模型，再找下级模型（level+1, level+2...）
        排除已经尝试失败的模型
        """
        statement = (
            select(SysModel)
            .where(
                SysModel.model_level >= current_level,
                SysModel.model_type == model_type,
                SysModel.is_deleted == 0,
                SysModel.is_enabled == True,
            )
            .order_by(SysModel.model_level, SysModel.priority)
        )
        result = await session.exec(statement)
        models = list(result.all())

        # 排除已尝试过的模型
        if exclude_names:
            models = [m for m in models if m.model_name not in exclude_names]

        return models

    async def list_models(
        self, session: AsyncSession
    ) -> list[SysModel]:
        """获取所有模型配置（含禁用的），用于管理页面"""
        statement = (
            select(SysModel)
            .where(SysModel.is_deleted == 0)
            .order_by(SysModel.model_level, SysModel.priority)
        )
        result = await session.exec(statement)
        return list(result.all())


# 单例
model_service = ModelService()
