import json
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.system.sys_user import SysUser
from app.schemas.agent.fr_report.ai_report import (
    CptPublishResponse,
    FrAiReportAgentCapabilitiesResponse,
    FrAiReportAgentChatResponse,
    FrAiReportAgentContext,
    GenerateCptStepResponse,
    FrAiReportFeedbackCreate,
    FrAiReportFeedbackRead,
    GenerateDslStepResponse,
    GenerateReportResponse,
    GenerateSqlStepResponse,
    FrAiReportRequirementReviewResponse,
    PreviewValidationResult,
    ReportTaskListItem,
    ReportTaskRead,
)
from app.schemas.agent.fr_report.report_ai_operation import (
    FrReportAiApplyDraftRequest,
    FrReportAiApplyDraftResponse,
    FrReportAiNewReportPlanResponse,
    FrReportAiOperationDraftResponse,
    FrReportAiOperationRequest,
    FrReportAiSnapshotCptRequest,
    FrReportAiSnapshotCptResponse,
    FrReportExternalSyncRequest,
    FrReportExternalSyncResponse,
    FrReportRecycleRequest,
    FrReportRecycleResponse,
    FrReportVersionListResponse,
    FrReportVersionRollbackRequest,
    FrReportVersionRollbackResponse,
    FrReportStructureRollbackRequest,
    FrReportStructureRollbackResponse,
)
from app.schemas.agent.fr_report.report_file import (
    FrReportDatabaseConnectionCreate,
    FrReportDatabaseConnectionRead,
    FrReportDatabaseDriverRead,
    FrReportDatasetPreviewRequest,
    FrReportDatasetPreviewResponse,
    FrReportFileListResponse,
    FrReportFileStructureRead,
    FrReportVisibilityPreferenceRead,
    FrReportVisibilityPreferenceUpdate,
)
from app.schemas.page import Page
from app.schemas.result import Result
from app.services.agent.fr_report.report_file_service import fr_report_file_service
from app.services.agent.fr_report.ai_operation_service import fr_report_ai_operation_service
from app.services.agent.fr_report.report_generation_service import fr_ai_report_service
from app.services.agent.fr_report.version_control_service import fr_report_version_control_service

router = APIRouter()


@router.get("/files", response_model=Result[FrReportFileListResponse])
async def list_report_files(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
    prefix: str | None = None,
    keyword: str | None = None,
    limit: int = 200,
    include_all: bool = False,
) -> Result[FrReportFileListResponse]:
    try:
        result = await fr_report_file_service.list_report_files(
            db=db,
            user_id=current_user.id,
            prefix=prefix,
            keyword=keyword,
            limit=limit,
            include_all=include_all,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="读取 MinIO 报表文件失败，请检查 endpoint、bucket 和 Access Key 配置") from exc
    return Result.success(result)


@router.get("/files/structure", response_model=Result[FrReportFileStructureRead])
async def get_report_file_structure(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
    object_path: str,
) -> Result[FrReportFileStructureRead]:
    try:
        result = await fr_report_file_service.read_report_structure(
            db=db,
            user_id=current_user.id,
            object_path=object_path,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="读取帆软报表结构失败，请检查 MinIO 对象和 CPT 格式") from exc
    return Result.success(result)


@router.get("/database-connections", response_model=Result[list[FrReportDatabaseConnectionRead]])
async def list_report_database_connections(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
) -> Result[list[FrReportDatabaseConnectionRead]]:
    result = await fr_report_file_service.list_database_connections(db, current_user.id)
    return Result.success(result)


@router.get("/database-drivers", response_model=Result[list[FrReportDatabaseDriverRead]])
async def list_report_database_drivers(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
) -> Result[list[FrReportDatabaseDriverRead]]:
    _ = current_user
    result = await fr_report_file_service.list_database_drivers(db)
    return Result.success(result)


@router.post("/database-connections", response_model=Result[FrReportDatabaseConnectionRead])
async def upsert_report_database_connection(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
    payload: FrReportDatabaseConnectionCreate,
) -> Result[FrReportDatabaseConnectionRead]:
    try:
        result = await fr_report_file_service.upsert_database_connection(db, current_user.id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Result.success(result)


@router.post("/datasets/preview", response_model=Result[FrReportDatasetPreviewResponse])
async def preview_report_dataset(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
    payload: FrReportDatasetPreviewRequest,
) -> Result[FrReportDatasetPreviewResponse]:
    result = await fr_report_file_service.preview_dataset(db, current_user.id, payload)
    return Result.success(result)


@router.get("/files/visibility-preference", response_model=Result[FrReportVisibilityPreferenceRead])
async def get_report_file_visibility_preference(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
) -> Result[FrReportVisibilityPreferenceRead]:
    visible_paths = await fr_report_file_service.get_visible_paths(db, current_user.id)
    return Result.success(FrReportVisibilityPreferenceRead(visiblePaths=visible_paths))


@router.put("/files/visibility-preference", response_model=Result[FrReportVisibilityPreferenceRead])
async def update_report_file_visibility_preference(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
    payload: FrReportVisibilityPreferenceUpdate,
) -> Result[FrReportVisibilityPreferenceRead]:
    visible_paths = await fr_report_file_service.update_visible_paths(
        db,
        user_id=current_user.id,
        visible_paths=payload.visiblePaths,
    )
    return Result.success(FrReportVisibilityPreferenceRead(visiblePaths=visible_paths))


@router.post("/ai/operation-draft", response_model=Result[FrReportAiOperationDraftResponse])
async def generate_report_ai_operation_draft(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
    payload: FrReportAiOperationRequest,
) -> Result[FrReportAiOperationDraftResponse]:
    if not payload.prompt.strip():
        raise HTTPException(status_code=400, detail="请输入 AI 修改指令")
    try:
        result = await fr_report_ai_operation_service.generate_operation_draft(
            db=db,
            user_id=current_user.id,
            payload=payload,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return Result.success(result)


@router.post("/ai/new-report-plan", response_model=Result[FrReportAiNewReportPlanResponse])
async def create_report_ai_new_report_plan(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
    requirement: str = Form(...),
    template_object_path: str | None = Form(default=None),
    report_name: str | None = Form(default=None),
    target_folder: str | None = Form(default=None),
    files: list[UploadFile] | None = File(default=None),
) -> Result[FrReportAiNewReportPlanResponse]:
    if not requirement.strip():
        raise HTTPException(status_code=400, detail="请输入新建报表需求")
    try:
        result = await fr_report_ai_operation_service.create_new_report_plan(
            db=db,
            user_id=current_user.id,
            requirement=requirement,
            template_object_path=template_object_path,
            report_name=report_name,
            target_folder=target_folder,
            files=files or [],
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return Result.success(result)


@router.post("/ai/apply-draft", response_model=Result[FrReportAiApplyDraftResponse])
async def apply_report_ai_operation_draft(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
    payload: FrReportAiApplyDraftRequest,
) -> Result[FrReportAiApplyDraftResponse]:
    try:
        result = await fr_report_ai_operation_service.apply_operation_draft(
            db=db,
            user_id=current_user.id,
            payload=payload,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return Result.success(result)


@router.get("/versions", response_model=Result[FrReportVersionListResponse])
async def list_report_versions(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
    object_path: str,
) -> Result[FrReportVersionListResponse]:
    try:
        result = await fr_report_version_control_service.list_versions(db, current_user.id, object_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Result.success(result)


@router.post("/versions/rollback", response_model=Result[FrReportVersionRollbackResponse])
async def rollback_report_file_version(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
    payload: FrReportVersionRollbackRequest,
) -> Result[FrReportVersionRollbackResponse]:
    try:
        result = await fr_report_version_control_service.rollback_file_version(
            db=db,
            user_id=current_user.id,
            file_version_id=payload.fileVersionId,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return Result.success(result)


@router.post("/versions/structure/rollback", response_model=Result[FrReportStructureRollbackResponse])
async def rollback_report_structure_version(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
    payload: FrReportStructureRollbackRequest,
) -> Result[FrReportStructureRollbackResponse]:
    try:
        result = await fr_report_version_control_service.rollback_structure_version(
            db=db,
            user_id=current_user.id,
            structure_version_id=payload.structureVersionId,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Result.success(result)


@router.post("/versions/external/sync", response_model=Result[FrReportExternalSyncResponse])
async def sync_report_external_file_version(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
    payload: FrReportExternalSyncRequest,
) -> Result[FrReportExternalSyncResponse]:
    try:
        result = await fr_report_version_control_service.sync_external_file_version(
            db=db,
            user_id=current_user.id,
            object_path=payload.objectPath,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Result.success(result)


@router.post("/versions/recycle", response_model=Result[FrReportRecycleResponse])
async def recycle_report_file(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
    payload: FrReportRecycleRequest,
) -> Result[FrReportRecycleResponse]:
    try:
        result = await fr_report_version_control_service.recycle_report_file(
            db=db,
            user_id=current_user.id,
            object_path=payload.objectPath,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return Result.success(result)


@router.post("/requirements/review", response_model=Result[FrAiReportRequirementReviewResponse])
async def review_report_requirement(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
    requirement: str | None = Form(default=None),
    source_table_name: str | None = Form(default=None),
    table_schema_json: str | None = Form(default=None),
    file: UploadFile | None = File(default=None),
) -> Result[FrAiReportRequirementReviewResponse]:
    _ = db
    _ = current_user
    table_schema = _parse_table_schema(table_schema_json)
    if not requirement and not file and not source_table_name:
        raise HTTPException(status_code=400, detail="请提供业务 Excel、自然语言需求或相关数据表名")
    result = await fr_ai_report_service.review_requirement(
        requirement=requirement,
        file=file,
        table_schema=table_schema,
        source_table_name=source_table_name,
    )
    return Result.success(result)


@router.post("/agent/chat", response_model=Result[FrAiReportAgentChatResponse])
async def chat_with_report_agent(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
    message: str = Form(...),
    action: str = Form(default="chat"),
    context_json: str | None = Form(default=None),
    file: UploadFile | None = File(default=None),
    files: list[UploadFile] | None = File(default=None),
) -> Result[FrAiReportAgentChatResponse]:
    context_payload = _parse_json_object(context_json, "context_json") if context_json else {}
    try:
        context = FrAiReportAgentContext.model_validate(context_payload)
        result = await fr_ai_report_service.agent_chat(
            db,
            user_id=current_user.id,
            message=message,
            action=action,
            context=context,
            file=file,
            files=files or [],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Result.success(result)


@router.get("/agent/capabilities", response_model=Result[FrAiReportAgentCapabilitiesResponse])
async def get_report_agent_capabilities(
    *,
    current_user: SysUser = Depends(get_current_user),
) -> Result[FrAiReportAgentCapabilitiesResponse]:
    _ = current_user
    return Result.success(fr_ai_report_service.get_agent_capabilities())


@router.post("/empty/create", response_model=Result[GenerateCptStepResponse])
async def create_empty_report(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
    report_name: str = Form(...),
    target_folder: str = Form(...),
    target_object_path: str | None = Form(default=None),
    conflict_strategy: str = Form(default="abort"),
) -> Result[GenerateCptStepResponse]:
    if not report_name.strip():
        raise HTTPException(status_code=400, detail="请输入报表名称")
    if not target_folder.strip() and not (target_object_path or "").strip():
        raise HTTPException(status_code=400, detail="请选择保存目录")
    try:
        result = await fr_ai_report_service.create_empty_report(
            db,
            user_id=current_user.id,
            report_name=report_name,
            target_folder=target_folder,
            target_object_path=target_object_path,
            conflict_strategy=conflict_strategy,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Result.success(result)


@router.post("/ai/snapshots/cpt/generate", response_model=Result[FrReportAiSnapshotCptResponse])
async def generate_report_ai_snapshot_cpt(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
    payload: FrReportAiSnapshotCptRequest,
) -> Result[FrReportAiSnapshotCptResponse]:
    try:
        result = await fr_report_ai_operation_service.generate_snapshot_cpt(
            db=db,
            user_id=current_user.id,
            payload=payload,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return Result.success(result)


@router.post("/steps/sql/generate", response_model=Result[GenerateSqlStepResponse])
async def generate_sql_step(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
    requirement: str | None = Form(default=None),
    report_name: str | None = Form(default=None),
    source_table_name: str | None = Form(default=None),
    conversation_id: str | None = Form(default=None),
    table_schema_json: str | None = Form(default=None),
    ddl_dialect: str | None = Form(default=None),
    id_auto_increment: bool = Form(default=True),
    table_name_overrides_json: str | None = Form(default=None),
    file: UploadFile | None = File(default=None),
) -> Result[GenerateSqlStepResponse]:
    _ = current_user
    table_schema = _parse_table_schema(table_schema_json)
    table_name_overrides = _parse_json_object(table_name_overrides_json, "table_name_overrides_json")
    if not requirement and not file and not source_table_name:
        raise HTTPException(status_code=400, detail="请提供业务 Excel 文件、数据表名或自然语言需求")
    result = await fr_ai_report_service.generate_sql_step(
        db,
        requirement,
        file,
        table_schema,
        report_name,
        source_table_name,
        conversation_id,
        str(current_user.id) if current_user.id is not None else None,
        ddl_dialect=ddl_dialect,
        id_auto_increment=id_auto_increment,
        table_name_overrides=table_name_overrides,
    )
    return Result.success(result)


@router.post("/steps/dsl/generate", response_model=Result[GenerateDslStepResponse])
async def generate_dsl_step(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
    task_id: str = Form(...),
    dsl_feedback: str | None = Form(default=None),
) -> Result[GenerateDslStepResponse]:
    _ = current_user
    try:
        result = await fr_ai_report_service.generate_dsl_step(db, task_id, dsl_feedback)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Result.success(result)


@router.post("/steps/cpt/generate", response_model=Result[GenerateCptStepResponse])
async def generate_cpt_step(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
    task_id: str = Form(...),
    report_name: str | None = Form(default=None),
    target_folder: str | None = Form(default=None),
    target_object_path: str | None = Form(default=None),
    conflict_strategy: str = Form(default="abort"),
) -> Result[GenerateCptStepResponse]:
    try:
        result = await fr_ai_report_service.generate_cpt_step(
            db,
            task_id,
            user_id=current_user.id,
            report_name=report_name,
            target_folder=target_folder,
            target_object_path=target_object_path,
            conflict_strategy=conflict_strategy,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Result.success(result)


@router.post("/generate", response_model=Result[GenerateReportResponse])
async def generate_report(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
    requirement: str | None = Form(default=None),
    report_name: str | None = Form(default=None),
    target_folder: str | None = Form(default=None),
    target_object_path: str | None = Form(default=None),
    conflict_strategy: str = Form(default="abort"),
    source_table_name: str | None = Form(default=None),
    conversation_id: str | None = Form(default=None),
    table_schema_json: str | None = Form(default=None),
    file: UploadFile | None = File(default=None),
) -> Result[GenerateReportResponse]:
    _ = current_user
    table_schema = _parse_table_schema(table_schema_json)
    if not requirement and not file and not source_table_name:
        raise HTTPException(status_code=400, detail="请提供业务 Excel 文件、数据表名或自然语言需求")
    result = await fr_ai_report_service.generate(
        db,
        requirement,
        file,
        table_schema,
        report_name,
        target_folder,
        target_object_path,
        conflict_strategy,
        source_table_name,
        conversation_id,
        str(current_user.id) if current_user.id is not None else None,
        current_user.id,
    )
    return Result.success(result)


@router.get("/tasks", response_model=Result[Page[ReportTaskListItem]])
async def list_report_tasks(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
    page: int = 1,
    size: int = 20,
    keyword: str | None = None,
    status: str | None = None,
) -> Result[Page[ReportTaskListItem]]:
    result = await fr_ai_report_service.list_tasks(
        db,
        page=page,
        size=size,
        keyword=keyword,
        status=status,
        user_id=str(current_user.id) if current_user.id is not None else None,
    )
    return Result.success(result)


@router.get("/tasks/{task_id}", response_model=Result[ReportTaskRead])
async def get_report_task(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
    task_id: str,
) -> Result[ReportTaskRead]:
    _ = current_user
    task = await fr_ai_report_service.get_task(db, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return Result.success(fr_ai_report_service.to_read_schema(task))


@router.post("/tasks/{task_id}/feedback", response_model=Result[FrAiReportFeedbackRead])
async def create_report_task_feedback(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
    task_id: str,
    feedback: FrAiReportFeedbackCreate,
) -> Result[FrAiReportFeedbackRead]:
    _ = current_user
    try:
        result = await fr_ai_report_service.add_feedback(db, task_id, feedback)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Result.success(result)


@router.post("/tasks/{task_id}/validate", response_model=Result[PreviewValidationResult])
async def validate_report_task(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
    task_id: str,
) -> Result[PreviewValidationResult]:
    _ = current_user
    try:
        result = await fr_ai_report_service.validate_preview(db, task_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Result.success(result)


@router.post("/tasks/{task_id}/publish", response_model=Result[CptPublishResponse])
async def publish_report_task(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
    task_id: str,
) -> Result[CptPublishResponse]:
    _ = current_user
    try:
        task = await fr_ai_report_service.publish(db, task_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Result.success(
        CptPublishResponse(
            taskId=task.task_id,
            status=task.status.value,
            cptObjectPath=task.cpt_object_path,
            warnings=task.warnings or [],
        )
    )


def _parse_json_object(value_json: str | None, field_name: str) -> dict[str, Any] | None:
    if not value_json:
        return None
    try:
        value = json.loads(value_json)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"{field_name} 不是合法 JSON") from exc
    if not isinstance(value, dict):
        raise HTTPException(status_code=400, detail=f"{field_name} 必须是 JSON 对象")
    return value


def _parse_table_schema(table_schema_json: str | None) -> dict[str, Any] | None:
    return _parse_json_object(table_schema_json, "table_schema_json")
