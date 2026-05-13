from typing import List

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api import deps
from app.db.session import get_db
from app.models.agent.sap_assistant import SapAssistantMessage, SapAssistantSession, SapSystemConfig
from app.models.system.sys_user import SysUser
from app.schemas.result import Result
from app.schemas.agent.sap_assistant import (
    SapAssistantChatRequest,
    SapAssistantChatResponse,
    SapAssistantMessageRead,
    SapAssistantSessionRead,
    SapSystemCreate,
    SapSystemRead,
)
from app.services.agent.sap_assistant.assistant_service import sap_assistant_service
from app.services.agent.sap_assistant.rfc_client import sap_rfc_client

router = APIRouter()


@router.get("/systems", response_model=Result[List[SapSystemRead]])
async def list_sap_systems(
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(deps.get_current_user),
) -> Result[List[SapSystemRead]]:
    result = await db.exec(
        select(SapSystemConfig).where(SapSystemConfig.is_deleted == 0).order_by(SapSystemConfig.create_time.desc())
    )
    return Result.success(data=list(result.all()))


@router.get("/assistant/sessions", response_model=Result[List[SapAssistantSessionRead]])
async def list_sap_assistant_sessions(
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(deps.get_current_user),
) -> Result[List[SapAssistantSessionRead]]:
    result = await db.exec(
        select(SapAssistantSession)
        .where(SapAssistantSession.user_id == current_user.id, SapAssistantSession.status == "active")
        .order_by(SapAssistantSession.update_time.desc())
        .limit(50)
    )
    return Result.success(data=list(result.all()))


@router.get("/assistant/sessions/{session_id}/messages", response_model=Result[List[SapAssistantMessageRead]])
async def list_sap_assistant_messages(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(deps.get_current_user),
) -> Result[List[SapAssistantMessageRead]]:
    session = await db.get(SapAssistantSession, session_id)
    if not session or session.user_id != current_user.id or session.status != "active":
        return Result.fail(code=404, msg="SAP 助手会话不存在")
    result = await db.exec(
        select(SapAssistantMessage)
        .where(SapAssistantMessage.session_id == session_id)
        .order_by(SapAssistantMessage.create_time.asc())
    )
    return Result.success(data=list(result.all()))


@router.post("/systems", response_model=Result[SapSystemRead])
async def create_sap_system(
    obj_in: SapSystemCreate,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(deps.get_current_active_superuser),
) -> Result[SapSystemRead]:
    system = SapSystemConfig(**obj_in.model_dump())
    db.add(system)
    await db.commit()
    await db.refresh(system)
    return Result.success(data=system, msg="SAP 系统配置已创建")


@router.post("/systems/{system_id}/test-connection", response_model=Result[dict])
async def test_sap_connection(
    system_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(deps.get_current_user),
) -> Result[dict]:
    system = await db.get(SapSystemConfig, system_id)
    if not system or system.is_deleted:
        return Result.fail(code=404, msg="SAP 系统不存在")
    data = await sap_rfc_client.ping(system)
    return Result.success(data=data, msg=data.get("message", "连接测试完成"))


@router.post("/assistant/chat", response_model=Result[SapAssistantChatResponse])
async def sap_assistant_chat(
    request: SapAssistantChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(deps.get_current_user),
) -> Result[SapAssistantChatResponse]:
    data = await sap_assistant_service.chat(db, request, user_id=current_user.id)
    return Result.success(data=data)


@router.post("/assistant/chat/stream")
async def sap_assistant_chat_stream(
    request: SapAssistantChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(deps.get_current_user),
) -> StreamingResponse:
    return StreamingResponse(
        sap_assistant_service.stream_chat_realtime(db, request, user_id=current_user.id),
        media_type="text/event-stream",
    )
