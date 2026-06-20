from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel.ext.asyncio.session import AsyncSession
from starlette.responses import StreamingResponse

from app.api import deps
from app.db.session import get_db
from app.schemas.agent.weaver_ai_assistant import (
    WeaverAssistantChatRequest,
    WeaverAssistantChatResponse,
    WeaverFieldConfigResponse,
    WeaverReviewRecordRead,
    WeaverReviewRequest,
    WeaverReviewResponse,
    WeaverReviewRuleCreate,
    WeaverReviewRuleRead,
    WeaverReviewRuleUpdate,
    WeaverWorkflowRuleCreate,
    WeaverWorkflowRuleRead,
    WeaverWorkflowRuleUpdate,
)
from app.schemas.result import Result
from app.services.agent.weaver_ai_assistant.assistant_service import weaver_ai_assistant_service
from app.services.agent.weaver_ai_assistant.review_service import weaver_ai_review_service
from app.services.agent.weaver_ai_assistant.workflow_rule_service import weaver_workflow_rule_service

router = APIRouter(dependencies=[Depends(deps.verify_external_ai_sign)])


@router.get("/field-config", response_model=Result[WeaverFieldConfigResponse])
async def get_weaver_field_config(
    workflow_id: str = Query(..., description="泛微流程 ID"),
    env: str | None = Query(None, description="泛微环境 key，例如 test、prod；不传则使用 WEAVER_DEFAULT_ENV"),
) -> Result[WeaverFieldConfigResponse]:
    data = await weaver_ai_assistant_service.get_field_config(workflow_id, env)
    return Result.success(data=data)


@router.post("/chat", response_model=Result[WeaverAssistantChatResponse])
async def weaver_assistant_chat(
    request: WeaverAssistantChatRequest,
) -> Result[WeaverAssistantChatResponse]:
    data = await weaver_ai_assistant_service.chat(request)
    return Result.success(data=data)


@router.post("/chat/stream")
async def weaver_assistant_chat_stream(
    request: WeaverAssistantChatRequest,
) -> StreamingResponse:
    return StreamingResponse(
        weaver_ai_assistant_service.stream_chat(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/workflow-rules", response_model=Result[list[WeaverWorkflowRuleRead]])
async def list_weaver_workflow_rules(
    workflow_id: str = Query(..., description="泛微流程 ID"),
    env: str | None = Query(None, description="泛微环境 key"),
    db: AsyncSession = Depends(get_db),
) -> Result[list[WeaverWorkflowRuleRead]]:
    data = await weaver_workflow_rule_service.list_rules(db, env or "default", workflow_id)
    return Result.success(data=data)


@router.post("/workflow-rules", response_model=Result[WeaverWorkflowRuleRead])
async def create_weaver_workflow_rule(
    request: WeaverWorkflowRuleCreate,
    db: AsyncSession = Depends(get_db),
) -> Result[WeaverWorkflowRuleRead]:
    data = await weaver_workflow_rule_service.create_rule(db, request)
    return Result.success(data=data)


@router.put("/workflow-rules/{rule_id}", response_model=Result[WeaverWorkflowRuleRead])
async def update_weaver_workflow_rule(
    rule_id: int,
    request: WeaverWorkflowRuleUpdate,
    db: AsyncSession = Depends(get_db),
) -> Result[WeaverWorkflowRuleRead]:
    data = await weaver_workflow_rule_service.update_rule(db, rule_id, request)
    if not data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="规则不存在")
    return Result.success(data=data)


@router.delete("/workflow-rules/{rule_id}", response_model=Result[bool])
async def delete_weaver_workflow_rule(
    rule_id: int,
    db: AsyncSession = Depends(get_db),
) -> Result[bool]:
    deleted = await weaver_workflow_rule_service.delete_rule(db, rule_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="规则不存在")
    return Result.success(data=True)


@router.get("/review-rules", response_model=Result[list[WeaverReviewRuleRead]])
async def list_weaver_review_rules(
    workflow_id: str = Query(..., description="泛微流程 ID"),
    env: str | None = Query(None, description="泛微环境 key"),
    node_id: str | None = Query(None, description="泛微节点 ID，不传返回流程级规则"),
    reviewer_user_id: str | None = Query(None, description="审批人用户 ID，不传返回节点通用规则"),
    db: AsyncSession = Depends(get_db),
) -> Result[list[WeaverReviewRuleRead]]:
    data = await weaver_ai_review_service.list_rules(db, env or "default", workflow_id, node_id, reviewer_user_id)
    return Result.success(data=data)


@router.post("/review-rules", response_model=Result[WeaverReviewRuleRead])
async def create_weaver_review_rule(
    request: WeaverReviewRuleCreate,
    db: AsyncSession = Depends(get_db),
) -> Result[WeaverReviewRuleRead]:
    data = await weaver_ai_review_service.create_rule(db, request)
    return Result.success(data=data)


@router.put("/review-rules/{rule_id}", response_model=Result[WeaverReviewRuleRead])
async def update_weaver_review_rule(
    rule_id: int,
    request: WeaverReviewRuleUpdate,
    db: AsyncSession = Depends(get_db),
) -> Result[WeaverReviewRuleRead]:
    data = await weaver_ai_review_service.update_rule(db, rule_id, request)
    if not data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="智审规则不存在")
    return Result.success(data=data)


@router.delete("/review-rules/{rule_id}", response_model=Result[bool])
async def delete_weaver_review_rule(
    rule_id: int,
    db: AsyncSession = Depends(get_db),
) -> Result[bool]:
    deleted = await weaver_ai_review_service.delete_rule(db, rule_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="智审规则不存在")
    return Result.success(data=True)


@router.post("/review/precheck", response_model=Result[WeaverReviewResponse])
async def weaver_ai_pre_review(
    request: WeaverReviewRequest,
    db: AsyncSession = Depends(get_db),
) -> Result[WeaverReviewResponse]:
    data = await weaver_ai_review_service.pre_review(db, request)
    return Result.success(data=data)


@router.get("/review/latest", response_model=Result[WeaverReviewRecordRead | None])
async def get_weaver_latest_review(
    workflow_id: str = Query(..., description="泛微流程 ID"),
    env: str | None = Query(None, description="泛微环境 key"),
    request_id: str | None = Query(None, description="泛微 requestid"),
    node_id: str | None = Query(None, description="泛微节点 ID"),
    db: AsyncSession = Depends(get_db),
) -> Result[WeaverReviewRecordRead | None]:
    data = await weaver_ai_review_service.latest_record(db, env or "default", workflow_id, request_id, node_id)
    return Result.success(data=data)
