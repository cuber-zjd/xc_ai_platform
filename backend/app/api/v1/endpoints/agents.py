from typing import Any, List
import uuid
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlmodel.ext.asyncio.session import AsyncSession
from app.api import deps
from app.db.session import get_db
from app.models.system.sys_user import SysUser
from app.schemas.result import Result
from app.schemas.agent import (
    AgentGroupRead, AgentGroupCreate, AgentGroupUpdate,
    AgentAppRead, AgentAppCreate, AgentAppUpdate,
    RoleAgentAssign, DeptAgentAssign, WorkbenchGroup
)
from app.services.agent_service import AgentService
from app.services.file_service import file_service

router = APIRouter()

# --- Workbench ---
@router.get("/workbench", response_model=Result[List[WorkbenchGroup]])
async def get_workbench(
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(deps.get_current_user),
) -> Any:
    """
    获取当前用户的工作台数据（按分组聚合）。
    """
    data = await AgentService.get_user_workbench(db, user=current_user)
    return Result.success(data=data)

# --- Groups ---
@router.get("/groups", response_model=Result[List[AgentGroupRead]])
async def read_groups(
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    获取所有智能体分组。
    """
    groups = await AgentService.get_group_list(db)
    return Result.success(data=groups)

@router.post("/groups", response_model=Result[AgentGroupRead])
async def create_group(
    *,
    db: AsyncSession = Depends(get_db),
    group_in: AgentGroupCreate,
    current_user: SysUser = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    创建新分组。
    """
    group = await AgentService.create_group(db, obj_in=group_in)
    return Result.success(data=group)

# --- Apps ---
@router.get("/apps", response_model=Result[List[AgentAppRead]])
async def read_apps(
    group_id: int = None,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    获取指定分组下的智能体应用列表。
    """
    apps = await AgentService.get_app_list(db, group_id=group_id)
    return Result.success(data=apps)

@router.put("/groups/{group_id}", response_model=Result[AgentGroupRead])
async def update_group(
    *,
    db: AsyncSession = Depends(get_db),
    group_id: int,
    group_in: AgentGroupUpdate,
    current_user: SysUser = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    更新智能体分组。
    """
    group = await AgentService.get_group_by_id(db, id=group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    group = await AgentService.update_group(db, db_obj=group, obj_in=group_in)
    return Result.success(data=group)

@router.post("/apps", response_model=Result[AgentAppRead])
async def create_app(
    *,
    db: AsyncSession = Depends(get_db),
    app_in: AgentAppCreate,
    current_user: SysUser = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    创建新智能体应用。
    """
    app = await AgentService.create_app(db, obj_in=app_in)
    return Result.success(data=app)

@router.put("/apps/{app_id}", response_model=Result[AgentAppRead])
async def update_app(
    *,
    db: AsyncSession = Depends(get_db),
    app_id: int,
    app_in: AgentAppUpdate,
    current_user: SysUser = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    更新智能体应用信息。
    """
    app = await AgentService.get_app_by_id(db, id=app_id)
    if not app:
        raise HTTPException(status_code=404, detail="Agent app not found")
    app = await AgentService.update_app(db, db_obj=app, obj_in=app_in)
    return Result.success(data=app)

@router.post("/upload_icon", response_model=Result[str])
async def upload_agent_icon(
    file: UploadFile = File(...),
    current_user: SysUser = Depends(deps.get_current_user),
) -> Any:
    """
    上传智能体图标到MinIO，返回文件URL（或对象名。目前通过MinIo presigned url临时，
    或者最好返回MinIO对象路径，使用 presigned 或公开 bucket 都可以）。
    我们这仅仅保存到 MinIO 然后返回临时/持久的可访问代理路径。
    """
    content = await file.read()
    ext = file.filename.split('.')[-1] if '.' in file.filename else 'png'
    object_name = f"agent_icons/{uuid.uuid4().hex}.{ext}"
    
    await file_service.upload_file(
        file_data=content,
        object_name=object_name,
        content_type=file.content_type
    )
    url = await file_service.get_presigned_url(object_name)
    return Result.success(data=url)

# --- Permissions ---
@router.post("/assign/role", response_model=Result[Any])
async def assign_role_agents(
    *,
    db: AsyncSession = Depends(get_db),
    assign_in: RoleAgentAssign,
    current_user: SysUser = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    为角色分配智能体权限。
    """
    await AgentService.assign_to_role(db, role_id=assign_in.role_id, agent_app_ids=assign_in.agent_app_ids)
    return Result.success(msg="Role agent permissions updated")

@router.post("/assign/dept", response_model=Result[Any])
async def assign_dept_agents(
    *,
    db: AsyncSession = Depends(get_db),
    assign_in: DeptAgentAssign,
    current_user: SysUser = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    为部门分配智能体权限。
    """
    await AgentService.assign_to_dept(db, dept_id=assign_in.dept_id, agent_app_ids=assign_in.agent_app_ids)
    return Result.success(msg="Dept agent permissions updated")

@router.get("/role/{role_id}/agents", response_model=Result[List[int]])
async def get_role_agent_ids(
    role_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    获取角色关联的智能体 ID 列表。
    """
    ids = await AgentService.get_role_agent_ids(db, role_id=role_id)
    return Result.success(data=ids)

@router.get("/dept/{dept_id}/agents", response_model=Result[List[int]])
async def get_dept_agent_ids(
    dept_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    获取部门关联的智能体 ID 列表。
    """
    ids = await AgentService.get_dept_agent_ids(db, dept_id=dept_id)
    return Result.success(data=ids)
