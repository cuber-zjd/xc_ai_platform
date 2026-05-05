import json
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.system.sys_user import SysUser
from app.schemas.fr_ai_report.ai_report import (
    CptPublishResponse,
    GenerateReportResponse,
    PreviewValidationResult,
    ReportTaskRead,
)
from app.schemas.result import Result
from app.services.fr_ai_report.report_generation_service import fr_ai_report_service

router = APIRouter()


@router.post("/generate", response_model=Result[GenerateReportResponse])
async def generate_report(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
    requirement: str | None = Form(default=None),
    report_name: str | None = Form(default=None),
    source_table_name: str | None = Form(default=None),
    table_schema_json: str | None = Form(default=None),
    file: UploadFile | None = File(default=None),
) -> Result[GenerateReportResponse]:
    _ = current_user
    table_schema = _parse_table_schema(table_schema_json)
    if not requirement and not file and not source_table_name:
        raise HTTPException(status_code=400, detail="请提供业务 Excel 文件、数据表名或自然语言需求")
    result = await fr_ai_report_service.generate(db, requirement, file, table_schema, report_name, source_table_name)
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


def _parse_table_schema(table_schema_json: str | None) -> dict[str, Any] | None:
    if not table_schema_json:
        return None
    try:
        value = json.loads(table_schema_json)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="table_schema_json 不是合法 JSON") from exc
    if not isinstance(value, dict):
        raise HTTPException(status_code=400, detail="table_schema_json 必须是 JSON 对象")
    return value
