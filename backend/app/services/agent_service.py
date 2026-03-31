from typing import Optional, List, Set
from sqlmodel import select, func, delete, or_
from sqlmodel.ext.asyncio.session import AsyncSession
from app.models.agent.agent_group import AgentGroup
from app.models.agent.agent_app import AgentApp
from app.models.agent.role_agent import SysRoleAgent
from app.models.agent.dept_agent import SysDeptAgent
from app.models.system.sys_user import SysUser
from app.models.system.sys_role import SysUserRole
from app.schemas.agent import (
    AgentGroupCreate, AgentGroupUpdate, 
    AgentAppCreate, AgentAppUpdate,
    WorkbenchGroup, WorkbenchAgent
)
from app.schemas.page import Page
from app.services.file_service import file_service

class AgentService:
    # --- Agent Group ---
    @staticmethod
    async def get_group_list(db: AsyncSession) -> List[AgentGroup]:
        query = select(AgentGroup).where(AgentGroup.is_deleted == 0).order_by(AgentGroup.sort_order.asc())
        result = await db.exec(query)
        return result.all()

    @staticmethod
    async def get_group_by_id(db: AsyncSession, id: int) -> Optional[AgentGroup]:
        return await db.get(AgentGroup, id)

    @staticmethod
    async def create_group(db: AsyncSession, obj_in: AgentGroupCreate) -> AgentGroup:
        db_obj = AgentGroup.model_validate(obj_in)
        db.add(db_obj)
        await db.commit()
        await db.refresh(db_obj)
        return db_obj

    @staticmethod
    async def update_group(db: AsyncSession, db_obj: AgentGroup, obj_in: AgentGroupUpdate) -> AgentGroup:
        update_data = obj_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_obj, field, value)
        db.add(db_obj)
        await db.commit()
        await db.refresh(db_obj)
        return db_obj

    # --- Agent App ---
    @staticmethod
    async def get_app_list(db: AsyncSession, group_id: Optional[int] = None) -> List[AgentApp]:
        query = select(AgentApp).where(AgentApp.is_deleted == 0)
        if group_id:
            query = query.where(AgentApp.group_id == group_id)
        query = query.order_by(AgentApp.sort_order.asc())
        result = await db.exec(query)
        return result.all()

    @staticmethod
    async def get_app_by_id(db: AsyncSession, id: int) -> Optional[AgentApp]:
        return await db.get(AgentApp, id)

    @staticmethod
    async def create_app(db: AsyncSession, obj_in: AgentAppCreate) -> AgentApp:
        db_obj = AgentApp.model_validate(obj_in)
        db.add(db_obj)
        await db.commit()
        await db.refresh(db_obj)
        return db_obj

    @staticmethod
    async def update_app(db: AsyncSession, db_obj: AgentApp, obj_in: AgentAppUpdate) -> AgentApp:
        update_data = obj_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_obj, field, value)
        db.add(db_obj)
        await db.commit()
        await db.refresh(db_obj)
        return db_obj

    # --- Permission Assignment ---
    @staticmethod
    async def assign_to_role(db: AsyncSession, role_id: int, agent_app_ids: List[int]) -> None:
        await db.exec(delete(SysRoleAgent).where(SysRoleAgent.role_id == role_id))
        for aid in agent_app_ids:
            db.add(SysRoleAgent(role_id=role_id, agent_app_id=aid))
        await db.commit()

    @staticmethod
    async def assign_to_dept(db: AsyncSession, dept_id: int, agent_app_ids: List[int]) -> None:
        await db.exec(delete(SysDeptAgent).where(SysDeptAgent.dept_id == dept_id))
        for aid in agent_app_ids:
            db.add(SysDeptAgent(dept_id=dept_id, agent_app_id=aid))
        await db.commit()

    @staticmethod
    async def get_role_agent_ids(db: AsyncSession, role_id: int) -> List[int]:
        query = select(SysRoleAgent.agent_app_id).where(SysRoleAgent.role_id == role_id)
        result = await db.exec(query)
        return result.all()

    @staticmethod
    async def get_dept_agent_ids(db: AsyncSession, dept_id: int) -> List[int]:
        query = select(SysDeptAgent.agent_app_id).where(SysDeptAgent.dept_id == dept_id)
        result = await db.exec(query)
        return result.all()

    # --- Workbench Logic ---
    @staticmethod
    async def get_user_workbench(db: AsyncSession, user: SysUser) -> List[WorkbenchGroup]:
        """
        核心逻辑：获取用户所有的智能体权限，并按分组聚合。
        """
        # 1. 获取用户所属的所有角色
        role_query = select(SysUserRole.role_id).where(SysUserRole.user_id == user.id)
        role_ids = (await db.exec(role_query)).all()

        # 2. 从角色和部门两个维度查找有权限的 Agent ID
        # 获取角色关联的 Agent IDs
        agent_ids: Set[int] = set()
        if role_ids:
            ra_query = select(SysRoleAgent.agent_app_id).where(SysRoleAgent.role_id.in_(role_ids))
            ra_result = (await db.exec(ra_query)).all()
            agent_ids.update(ra_result)
        
        # 获取部门关联的 Agent IDs
        if user.dept_id:
            # 兼容性处理：user.dept_id 如果是字符串需要转换或匹配
            # 假设 sys_dept 的 id 是 int，这里要做转换
            try:
                dept_id_int = int(user.dept_id)
                da_query = select(SysDeptAgent.agent_app_id).where(SysDeptAgent.dept_id == dept_id_int)
                da_result = (await db.exec(da_query)).all()
                agent_ids.update(da_result)
            except ValueError:
                pass

        # 3. 如果是超级管理员，显示所有启用的 Agent
        if getattr(user, "is_superuser", False):
            all_agents_query = select(AgentApp.id).where(AgentApp.is_deleted == 0, AgentApp.status == 1)
            agent_ids = set((await db.exec(all_agents_query)).all())

        if not agent_ids:
            return []

        # 4. 获取对应的分组和智能体详细信息
        groups = await AgentService.get_group_list(db)
        # 过滤掉禁用的分组
        groups = [g for g in groups if g.status == 1]
        
        apps_query = select(AgentApp).where(
            AgentApp.id.in_(list(agent_ids)), 
            AgentApp.is_deleted == 0,
            AgentApp.status == 1
        ).order_by(AgentApp.sort_order.asc())
        apps = (await db.exec(apps_query)).all()

        # 5. 组装返回数据
        result = []
        for group in groups:
            group_agents = []
            for app in apps:
                if app.group_id == group.id:
                    icon_url = app.icon
                    if icon_url and not icon_url.startswith('http'):
                        try:
                            icon_url = await file_service.get_presigned_url(icon_url)
                        except Exception:
                            icon_url = None
                    group_agents.append(WorkbenchAgent(
                        id=app.id,
                        name=app.name,
                        description=app.description,
                        icon=icon_url,
                        route_path=app.route_path
                    ))
            if group_agents:
                result.append(WorkbenchGroup(
                    id=group.id,
                    name=group.name,
                    agents=group_agents
                ))
        
        return result
