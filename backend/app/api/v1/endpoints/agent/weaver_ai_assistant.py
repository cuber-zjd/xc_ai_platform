from fastapi import APIRouter, Depends, Query

from app.api import deps
from app.schemas.agent.weaver_ai_assistant import (
    WeaverAssistantChatRequest,
    WeaverAssistantChatResponse,
    WeaverFieldConfigResponse,
)
from app.schemas.result import Result
from app.services.agent.weaver_ai_assistant.assistant_service import weaver_ai_assistant_service

router = APIRouter(dependencies=[Depends(deps.verify_external_ai_sign)])


@router.get("/field-config", response_model=Result[WeaverFieldConfigResponse])
async def get_weaver_field_config(
    workflow_id: str = Query(..., description="泛微流程 ID"),
) -> Result[WeaverFieldConfigResponse]:
    data = await weaver_ai_assistant_service.get_field_config(workflow_id)
    return Result.success(data=data)


@router.post("/chat", response_model=Result[WeaverAssistantChatResponse])
async def weaver_assistant_chat(
    request: WeaverAssistantChatRequest,
) -> Result[WeaverAssistantChatResponse]:
    data = await weaver_ai_assistant_service.chat(request)
    return Result.success(data=data)
