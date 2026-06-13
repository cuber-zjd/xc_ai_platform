from io import BytesIO

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.system.sys_user import SysUser
from app.schemas.agent.insight.crawl import (
    InsightManualUrlCrawlRequest,
    InsightManualUrlCrawlResponse,
    InsightSearchDiscoveryRequest,
    InsightSearchDiscoveryResponse,
)
from app.schemas.agent.insight.company import (
    InsightCompanyCreate,
    InsightCompanyDetail,
    InsightCompanyImportResponse,
    InsightCompanyListItem,
    InsightCompanyRead,
    InsightCompanyUpdate,
)
from app.schemas.agent.insight.dashboard import InsightDashboardSummary
from app.schemas.agent.insight.data_source import (
    InsightDataSourceCreate,
    InsightDataSourceExecuteRequest,
    InsightDataSourceExecuteResponse,
    InsightDataSourceRead,
    InsightDataSourceScheduleRunResponse,
    InsightDataSourceUpdate,
    InsightSchedulerStatusRead,
    InsightStaleTaskCleanupResponse,
)
from app.schemas.agent.insight.health import InsightHealthRead
from app.schemas.agent.insight.dictionary import (
    InsightDictionaryOverview,
    InsightIntelligenceTypeRead,
    InsightTagCreate,
    InsightTagRead,
    InsightTagUpdate,
)
from app.schemas.agent.insight.intelligence import (
    InsightCandidatePromoteRequest,
    InsightCandidateReviewRequest,
    InsightCandidateReviewResponse,
    InsightIntelligenceDetail,
    InsightIntelligenceCandidateListItem,
    InsightIntelligenceCreate,
    InsightIntelligenceListItem,
    InsightIntelligenceSourceCreate,
    InsightIntelligenceSourceRead,
    InsightIntelligenceUpdate,
    InsightPoolUpsertRequest,
    InsightUserIntelligencePoolRead,
    InsightVisibilityRuleCreate,
    InsightVisibilityRuleRead,
)
from app.schemas.agent.insight.report import (
    InsightReportDetail,
    InsightReportExportRead,
    InsightReportExportRequest,
    InsightReportGenerateRequest,
    InsightReportGenerateResponse,
    InsightReportListItem,
    InsightReportPreferenceRead,
    InsightReportPreferenceUpdate,
    InsightReportTemplateCloneRequest,
    InsightReportTemplateCreate,
    InsightReportTemplatePublishRequest,
    InsightReportTemplateRead,
    InsightReportTemplateUploadResponse,
    InsightReportTemplateUpdate,
    InsightReportUpdateRequest,
)
from app.schemas.agent.insight.permission import InsightAccessRuleRead, InsightAccessRuleUpsert
from app.schemas.agent.insight.notification import InsightNotificationCreate, InsightNotificationRead
from app.schemas.agent.insight.quality import InsightQualityOverview
from app.schemas.agent.insight.settings import InsightSettingsStatusRead
from app.schemas.agent.insight.task import InsightTaskRead
from app.schemas.page import Page
from app.schemas.result import Result
from app.services.agent.insight.crawler import insight_crawl_service, insight_search_discovery_service
from app.services.agent.insight.company_service import insight_company_service
from app.services.agent.insight.data_source_service import insight_data_source_service
from app.services.agent.insight.health_service import insight_health_service
from app.services.agent.insight.dictionary_service import insight_dictionary_service
from app.services.agent.insight.intelligence_service import insight_intelligence_service
from app.services.agent.insight.report_service import insight_report_service
from app.services.agent.insight.scheduler_service import insight_scheduler_service
from app.services.agent.insight.permission_service import insight_permission_service
from app.services.agent.insight.notification_service import insight_notification_service
from app.services.agent.insight.quality_service import insight_quality_service
from app.services.agent.insight.settings_service import insight_settings_service

router = APIRouter()


@router.get("/health", response_model=Result[InsightHealthRead])
async def get_insight_health(
    current_user: SysUser = Depends(get_current_user),
) -> Result[InsightHealthRead]:
    """返回 Insight 子平台后端模块装配状态。"""
    _ = current_user
    return Result.success(data=insight_health_service.get_health())


@router.get("/dashboard", response_model=Result[InsightDashboardSummary])
async def get_insight_dashboard(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
) -> Result[InsightDashboardSummary]:
    result = await insight_intelligence_service.get_dashboard(
        db,
        user_id=current_user.id,
        is_admin=_is_admin(current_user),
    )
    return Result.success(data=result)


@router.get("/settings/status", response_model=Result[InsightSettingsStatusRead])
async def get_insight_settings_status(
    current_user: SysUser = Depends(get_current_user),
) -> Result[InsightSettingsStatusRead]:
    _ = current_user
    return Result.success(data=insight_settings_service.get_status())


@router.get("/quality/overview", response_model=Result[InsightQualityOverview])
async def get_quality_overview(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
) -> Result[InsightQualityOverview]:
    _ = current_user
    result = await insight_quality_service.get_overview(db)
    return Result.success(data=result)


@router.get("/dictionaries/overview", response_model=Result[InsightDictionaryOverview])
async def get_dictionary_overview(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
) -> Result[InsightDictionaryOverview]:
    _ = current_user
    result = await insight_dictionary_service.get_overview(db)
    return Result.success(data=result)


@router.get("/dictionaries/tags", response_model=Result[list[InsightTagRead]])
async def list_dictionary_tags(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
    tag_type: str | None = None,
    include_disabled: bool = False,
) -> Result[list[InsightTagRead]]:
    _ = current_user
    result = await insight_dictionary_service.list_tags(db, tag_type=tag_type, include_disabled=include_disabled)
    return Result.success(data=result)


@router.post("/dictionaries/tags", response_model=Result[InsightTagRead])
async def create_dictionary_tag(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
    payload: InsightTagCreate,
) -> Result[InsightTagRead]:
    if not _is_admin(current_user):
        raise HTTPException(status_code=403, detail="仅管理员可维护标签字典")
    try:
        result = await insight_dictionary_service.create_tag(db, payload, current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Result.success(data=result, msg="标签已创建")


@router.put("/dictionaries/tags/{tag_id}", response_model=Result[InsightTagRead])
async def update_dictionary_tag(
    *,
    tag_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
    payload: InsightTagUpdate,
) -> Result[InsightTagRead]:
    if not _is_admin(current_user):
        raise HTTPException(status_code=403, detail="仅管理员可维护标签字典")
    try:
        result = await insight_dictionary_service.update_tag(db, tag_id, payload, current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Result.success(data=result, msg="标签已更新")


@router.post("/dictionaries/tags/{tag_id}/disable", response_model=Result[InsightTagRead])
async def disable_dictionary_tag(
    *,
    tag_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
) -> Result[InsightTagRead]:
    if not _is_admin(current_user):
        raise HTTPException(status_code=403, detail="仅管理员可维护标签字典")
    try:
        result = await insight_dictionary_service.disable_tag(db, tag_id, current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Result.success(data=result, msg="标签已禁用")


@router.get("/dictionaries/intelligence-types", response_model=Result[list[InsightIntelligenceTypeRead]])
async def list_dictionary_intelligence_types(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
) -> Result[list[InsightIntelligenceTypeRead]]:
    _ = current_user
    result = await insight_dictionary_service.list_intelligence_types(db)
    return Result.success(data=result)


@router.get("/notifications", response_model=Result[Page[InsightNotificationRead]])
async def list_notifications(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
    page: int = 1,
    size: int = 20,
    target_type: str | None = None,
    target_id: int | None = None,
    channel: str | None = None,
    status: str | None = None,
) -> Result[Page[InsightNotificationRead]]:
    result = await insight_notification_service.list_notifications(
        db,
        page=page,
        size=size,
        target_type=target_type,
        target_id=target_id,
        channel=channel,
        status=status,
        user_id=current_user.id,
        is_admin=_is_admin(current_user),
    )
    return Result.success(data=result)


@router.post("/notifications", response_model=Result[InsightNotificationRead])
async def create_notification(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
    payload: InsightNotificationCreate,
) -> Result[InsightNotificationRead]:
    try:
        result = await insight_notification_service.create_notification(
            db,
            payload,
            user_id=current_user.id,
            is_admin=_is_admin(current_user),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Result.success(data=result)


@router.post("/notifications/{notification_id}/retry", response_model=Result[InsightNotificationRead])
async def retry_notification(
    *,
    notification_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
) -> Result[InsightNotificationRead]:
    try:
        result = await insight_notification_service.retry_notification(
            db,
            notification_id,
            user_id=current_user.id,
            is_admin=_is_admin(current_user),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Result.success(data=result)


@router.get("/companies", response_model=Result[Page[InsightCompanyListItem]])
async def list_companies(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
    page: int = 1,
    size: int = 20,
    keyword: str | None = None,
    industry: str | None = None,
    monitor_level: str | None = None,
    status: str | None = None,
) -> Result[Page[InsightCompanyListItem]]:
    result = await insight_company_service.list_companies(
        db,
        page=page,
        size=size,
        keyword=keyword,
        industry=industry,
        monitor_level=monitor_level,
        status=status,
        user_id=current_user.id,
        is_admin=_is_admin(current_user),
    )
    return Result.success(data=result)


@router.post("/companies", response_model=Result[InsightCompanyRead])
async def create_company(
    *,
    payload: InsightCompanyCreate,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
) -> Result[InsightCompanyRead]:
    try:
        result = await insight_company_service.create_company(db, payload, current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Result.success(data=result, msg="企业档案已创建")


@router.post("/companies/import", response_model=Result[InsightCompanyImportResponse])
async def import_companies(
    *,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
) -> Result[InsightCompanyImportResponse]:
    try:
        file_bytes = await file.read()
        result = await insight_company_service.import_companies_from_excel(
            db,
            file_name=file.filename,
            file_bytes=file_bytes,
            user_id=current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Result.success(data=result, msg="企业档案导入完成")


@router.get("/companies/import-template")
async def download_company_import_template(
    current_user: SysUser = Depends(get_current_user),
) -> StreamingResponse:
    _ = current_user
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.utils import get_column_letter
    except ImportError as exc:
        raise HTTPException(status_code=500, detail="缺少 openpyxl 依赖，无法生成 Excel 模板") from exc

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "企业档案导入"
    headers = ["企业名称", "简称", "行业", "企业类型", "区域", "官网", "监控级别", "描述"]
    example = ["示例客户有限公司", "示例客户", "食品饮料", "客户", "华东", "https://example.com", "重点客户", "用于演示的客户档案"]
    sheet.append(headers)
    sheet.append(example)
    sheet.append(["示例竞对科技有限公司", "示例竞对", "智能制造", "竞对", "华南", "", "重点竞对", "第二行开始可直接替换或删除示例"])

    header_fill = PatternFill("solid", fgColor="DDEBFF")
    header_font = Font(bold=True, color="17365D")
    for cell in sheet[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")
    for index, width in enumerate([26, 16, 16, 14, 14, 28, 14, 36], start=1):
        sheet.column_dimensions[get_column_letter(index)].width = width
    sheet.freeze_panes = "A2"

    buffer = BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    headers_map = {"Content-Disposition": 'attachment; filename="insight-company-import-template.xlsx"'}
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers_map,
    )


@router.get("/companies/{company_id}", response_model=Result[InsightCompanyDetail])
async def get_company_detail(
    *,
    company_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
) -> Result[InsightCompanyDetail]:
    try:
        result = await insight_company_service.get_company_detail(
            db,
            company_id,
            user_id=current_user.id,
            is_admin=_is_admin(current_user),
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Result.success(data=result)


@router.put("/companies/{company_id}", response_model=Result[InsightCompanyRead])
async def update_company(
    *,
    company_id: int,
    payload: InsightCompanyUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
) -> Result[InsightCompanyRead]:
    try:
        result = await insight_company_service.update_company(
            db,
            company_id,
            payload,
            current_user.id,
            is_admin=_is_admin(current_user),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Result.success(data=result, msg="企业档案已更新")


@router.post("/crawler/manual-url", response_model=Result[InsightManualUrlCrawlResponse])
async def crawl_manual_url(
    *,
    payload: InsightManualUrlCrawlRequest,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
) -> Result[InsightManualUrlCrawlResponse]:
    try:
        result = await insight_crawl_service.crawl_manual_url(
            db,
            payload,
            current_user.id,
            is_admin=_is_admin(current_user),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Result.success(data=result, msg="网页抓取完成")


@router.post("/crawler/search-discovery", response_model=Result[InsightSearchDiscoveryResponse])
async def search_discovery(
    *,
    payload: InsightSearchDiscoveryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
) -> Result[InsightSearchDiscoveryResponse]:
    try:
        result = await insight_search_discovery_service.search_and_crawl(
            db,
            payload,
            current_user.id,
            is_admin=_is_admin(current_user),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Result.success(data=result, msg="搜索发现与抓取完成")


@router.get("/reports", response_model=Result[Page[InsightReportListItem]])
async def list_reports(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
    page: int = 1,
    size: int = 20,
    keyword: str | None = None,
    report_type: str | None = None,
    status: str | None = None,
) -> Result[Page[InsightReportListItem]]:
    result = await insight_report_service.list_reports(
        db,
        page=page,
        size=size,
        keyword=keyword,
        report_type=report_type,
        status=status,
        user_id=current_user.id,
        is_admin=_is_admin(current_user),
    )
    return Result.success(data=result)


@router.post("/reports/generate", response_model=Result[InsightReportGenerateResponse])
async def generate_report(
    *,
    payload: InsightReportGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
) -> Result[InsightReportGenerateResponse]:
    try:
        result = await insight_report_service.generate_report(
            db,
            payload,
            user_id=current_user.id,
            is_admin=_is_admin(current_user),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Result.success(data=result, msg="报告草稿已生成")


@router.get("/reports/templates", response_model=Result[list[InsightReportTemplateRead]])
async def list_report_templates(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
) -> Result[list[InsightReportTemplateRead]]:
    result = await insight_report_service.list_templates(
        db,
        user_id=current_user.id,
        is_admin=_is_admin(current_user),
    )
    return Result.success(data=result)


@router.post("/reports/templates", response_model=Result[InsightReportTemplateRead])
async def create_report_template(
    *,
    payload: InsightReportTemplateCreate,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
) -> Result[InsightReportTemplateRead]:
    result = await insight_report_service.create_template(db, payload, user_id=current_user.id)
    return Result.success(data=result, msg="报告模板已保存")


@router.post("/reports/templates/upload", response_model=Result[InsightReportTemplateUploadResponse])
async def upload_report_template(
    *,
    file: UploadFile = File(...),
    template_name: str | None = Form(default=None),
    report_type: str = Form(default="专题报告"),
    description: str | None = Form(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
) -> Result[InsightReportTemplateUploadResponse]:
    try:
        content = await file.read()
        result = await insight_report_service.create_template_from_upload(
            db,
            file_name=file.filename or "未命名模板",
            file_bytes=content,
            template_name=template_name,
            report_type=report_type,
            description=description,
            user_id=current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Result.success(data=result, msg="报告模板已解析并保存")


@router.post("/reports/templates/{template_id}/publish", response_model=Result[InsightReportTemplateRead])
async def publish_report_template(
    *,
    template_id: int,
    payload: InsightReportTemplatePublishRequest,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
) -> Result[InsightReportTemplateRead]:
    try:
        result = await insight_report_service.publish_template(
            db,
            template_id,
            payload,
            user_id=current_user.id,
            is_admin=_is_admin(current_user),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Result.success(data=result, msg="报告模板已发布到模板市场")


@router.post("/reports/templates/{template_code}/clone", response_model=Result[InsightReportTemplateRead])
async def clone_report_template(
    *,
    template_code: str,
    payload: InsightReportTemplateCloneRequest,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
) -> Result[InsightReportTemplateRead]:
    try:
        result = await insight_report_service.clone_template(
            db,
            template_code,
            payload,
            user_id=current_user.id,
            is_admin=_is_admin(current_user),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Result.success(data=result, msg="模板已复制为我的模板")


@router.put("/reports/templates/{template_id}", response_model=Result[InsightReportTemplateRead])
async def update_report_template(
    *,
    template_id: int,
    payload: InsightReportTemplateUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
) -> Result[InsightReportTemplateRead]:
    try:
        result = await insight_report_service.update_template(
            db,
            template_id,
            payload,
            user_id=current_user.id,
            is_admin=_is_admin(current_user),
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Result.success(data=result, msg="报告模板已更新")


@router.delete("/reports/templates/{template_id}", response_model=Result[None])
async def delete_report_template(
    *,
    template_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
) -> Result[None]:
    try:
        await insight_report_service.delete_template(
            db,
            template_id,
            user_id=current_user.id,
            is_admin=_is_admin(current_user),
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Result.success(msg="报告模板已删除")


@router.get("/reports/preference", response_model=Result[InsightReportPreferenceRead])
async def get_report_preference(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
) -> Result[InsightReportPreferenceRead]:
    result = await insight_report_service.get_preference(db, user_id=current_user.id)
    return Result.success(data=result)


@router.put("/reports/preference", response_model=Result[InsightReportPreferenceRead])
async def update_report_preference(
    *,
    payload: InsightReportPreferenceUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
) -> Result[InsightReportPreferenceRead]:
    result = await insight_report_service.update_preference(db, payload, user_id=current_user.id)
    return Result.success(data=result, msg="报告偏好已保存")


@router.get("/reports/{report_id}", response_model=Result[InsightReportDetail])
async def get_report_detail(
    *,
    report_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
) -> Result[InsightReportDetail]:
    try:
        result = await insight_report_service.get_report_detail(
            db,
            report_id,
            user_id=current_user.id,
            is_admin=_is_admin(current_user),
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Result.success(data=result)


@router.put("/reports/{report_id}", response_model=Result[InsightReportDetail])
async def update_report(
    *,
    report_id: int,
    payload: InsightReportUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
) -> Result[InsightReportDetail]:
    try:
        result = await insight_report_service.update_report(
            db,
            report_id,
            payload,
            user_id=current_user.id,
            is_admin=_is_admin(current_user),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Result.success(data=result, msg="报告草稿已更新")


@router.get("/reports/{report_id}/exports", response_model=Result[list[InsightReportExportRead]])
async def list_report_exports(
    *,
    report_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
) -> Result[list[InsightReportExportRead]]:
    try:
        result = await insight_report_service.list_report_exports(
            db,
            report_id,
            user_id=current_user.id,
            is_admin=_is_admin(current_user),
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Result.success(data=result)


@router.post("/reports/{report_id}/exports", response_model=Result[InsightReportExportRead])
async def export_report(
    *,
    report_id: int,
    payload: InsightReportExportRequest,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
) -> Result[InsightReportExportRead]:
    try:
        result = await insight_report_service.export_report(
            db,
            report_id,
            export_format=payload.export_format,
            user_id=current_user.id,
            is_admin=_is_admin(current_user),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Result.success(data=result, msg="报告导出已生成")


@router.get("/reports/{report_id}/exports/{export_id}/download")
async def download_report_export(
    *,
    report_id: int,
    export_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
) -> FileResponse:
    try:
        file_path, export = await insight_report_service.get_report_export_file(
            db,
            report_id,
            export_id,
            user_id=current_user.id,
            is_admin=_is_admin(current_user),
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(
        path=file_path,
        filename=export.file_name or file_path.name,
        media_type=export.content_type or "application/octet-stream",
    )


@router.get("/permissions/{target_type}/{target_id}", response_model=Result[list[InsightAccessRuleRead]])
async def list_access_rules(
    *,
    target_type: str,
    target_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
) -> Result[list[InsightAccessRuleRead]]:
    _ = current_user
    result = await insight_permission_service.list_rules(db, target_type=target_type, target_id=target_id)
    return Result.success(data=result)


@router.post("/permissions/{target_type}/{target_id}", response_model=Result[InsightAccessRuleRead])
async def grant_access_rule(
    *,
    target_type: str,
    target_id: int,
    payload: InsightAccessRuleUpsert,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
) -> Result[InsightAccessRuleRead]:
    result = await insight_permission_service.grant_rule(
        db,
        target_type=target_type,
        target_id=target_id,
        payload=payload,
        user_id=current_user.id,
    )
    return Result.success(data=result, msg="权限已更新")


@router.delete("/permissions/rules/{rule_id}", response_model=Result[None])
async def revoke_access_rule(
    *,
    rule_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
) -> Result[None]:
    try:
        await insight_permission_service.revoke_rule(db, rule_id=rule_id, user_id=current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Result.success(msg="权限已撤销")


@router.get("/data-sources", response_model=Result[Page[InsightDataSourceRead]])
async def list_data_sources(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
    page: int = 1,
    size: int = 20,
    keyword: str | None = None,
    source_type: str | None = None,
    status: str | None = None,
) -> Result[Page[InsightDataSourceRead]]:
    result = await insight_data_source_service.list_data_sources(
        db,
        page=page,
        size=size,
        keyword=keyword,
        source_type=source_type,
        status=status,
        user_id=current_user.id,
        is_admin=_is_admin(current_user),
    )
    return Result.success(data=result)


@router.post("/data-sources", response_model=Result[InsightDataSourceRead])
async def create_data_source(
    *,
    payload: InsightDataSourceCreate,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
) -> Result[InsightDataSourceRead]:
    try:
        result = await insight_data_source_service.create_data_source(db, payload, current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Result.success(data=result, msg="数据源已创建")


@router.get("/data-sources/execution-logs", response_model=Result[Page[InsightTaskRead]])
async def list_data_source_execution_logs(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
    page: int = 1,
    size: int = 20,
    data_source_id: int | None = None,
    status: str | None = None,
    task_type: str | None = None,
) -> Result[Page[InsightTaskRead]]:
    _ = current_user
    result = await insight_data_source_service.list_execution_logs(
        db,
        page=page,
        size=size,
        data_source_id=data_source_id,
        status=status,
        task_type=task_type,
    )
    return Result.success(data=result)


@router.post("/data-sources/tasks/cleanup-stale", response_model=Result[InsightStaleTaskCleanupResponse])
async def cleanup_stale_data_source_tasks(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
    timeout_minutes: int = 30,
) -> Result[InsightStaleTaskCleanupResponse]:
    result = await insight_data_source_service.cleanup_stale_tasks(
        db,
        timeout_minutes=timeout_minutes,
        user_id=current_user.id,
    )
    return Result.success(data=result, msg="遗留任务清理完成")


@router.post("/data-sources/{data_source_id}/schedule/retry", response_model=Result[InsightDataSourceRead])
async def retry_data_source_schedule(
    *,
    data_source_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
) -> Result[InsightDataSourceRead]:
    try:
        result = await insight_data_source_service.retry_data_source(
            db,
            data_source_id=data_source_id,
            user_id=current_user.id,
            is_admin=_is_admin(current_user),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Result.success(data=result, msg="数据源已加入下一轮调度")


@router.get("/scheduler/status", response_model=Result[InsightSchedulerStatusRead])
async def get_scheduler_status(
    current_user: SysUser = Depends(get_current_user),
) -> Result[InsightSchedulerStatusRead]:
    _ = current_user
    return Result.success(data=InsightSchedulerStatusRead(**insight_scheduler_service.status()))


@router.post("/scheduler/run-once", response_model=Result[InsightDataSourceScheduleRunResponse])
async def run_scheduler_once(
    current_user: SysUser = Depends(get_current_user),
) -> Result[InsightDataSourceScheduleRunResponse]:
    result = await insight_scheduler_service.run_once(triggered_by=f"user:{current_user.id}")
    return Result.success(data=result, msg="调度器已完成一次扫描")


@router.post("/scheduler/start", response_model=Result[InsightSchedulerStatusRead])
async def start_scheduler(
    current_user: SysUser = Depends(get_current_user),
) -> Result[InsightSchedulerStatusRead]:
    _ = current_user
    await insight_scheduler_service.start()
    return Result.success(data=InsightSchedulerStatusRead(**insight_scheduler_service.status()), msg="调度器已启动")


@router.post("/scheduler/stop", response_model=Result[InsightSchedulerStatusRead])
async def stop_scheduler(
    current_user: SysUser = Depends(get_current_user),
) -> Result[InsightSchedulerStatusRead]:
    _ = current_user
    await insight_scheduler_service.stop()
    return Result.success(data=InsightSchedulerStatusRead(**insight_scheduler_service.status()), msg="调度器已停止")


@router.post("/data-sources/schedule/run-due", response_model=Result[InsightDataSourceScheduleRunResponse])
async def run_due_data_sources(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
    limit: int = 5,
) -> Result[InsightDataSourceScheduleRunResponse]:
    result = await insight_data_source_service.run_due_data_sources(
        db,
        limit=limit,
        user_id=current_user.id,
    )
    return Result.success(data=result, msg="到期周期采集执行完成")


@router.get("/data-sources/{data_source_id}", response_model=Result[InsightDataSourceRead])
async def get_data_source(
    *,
    data_source_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
) -> Result[InsightDataSourceRead]:
    try:
        result = await insight_data_source_service.get_data_source(
            db,
            data_source_id,
            user_id=current_user.id,
            is_admin=_is_admin(current_user),
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Result.success(data=result)


@router.put("/data-sources/{data_source_id}", response_model=Result[InsightDataSourceRead])
async def update_data_source(
    *,
    data_source_id: int,
    payload: InsightDataSourceUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
) -> Result[InsightDataSourceRead]:
    try:
        result = await insight_data_source_service.update_data_source(
            db,
            data_source_id,
            payload,
            current_user.id,
            is_admin=_is_admin(current_user),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Result.success(data=result, msg="数据源已更新")


@router.delete("/data-sources/{data_source_id}", response_model=Result[None])
async def delete_data_source(
    *,
    data_source_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
) -> Result[None]:
    try:
        await insight_data_source_service.delete_data_source(
            db,
            data_source_id,
            current_user.id,
            is_admin=_is_admin(current_user),
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Result.success(msg="数据源已删除")


@router.post("/data-sources/{data_source_id}/execute", response_model=Result[InsightDataSourceExecuteResponse])
async def execute_data_source(
    *,
    data_source_id: int,
    payload: InsightDataSourceExecuteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
) -> Result[InsightDataSourceExecuteResponse]:
    try:
        result = await insight_data_source_service.execute_data_source(
            db,
            data_source_id,
            payload,
            current_user.id,
            is_admin=_is_admin(current_user),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Result.success(data=result, msg="数据源测试采集已完成")


@router.get("/intelligence/candidates", response_model=Result[Page[InsightIntelligenceCandidateListItem]])
async def list_intelligence_candidates(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
    page: int = 1,
    size: int = 20,
    keyword: str | None = None,
    review_status: str | None = None,
    subject_type: str | None = None,
    intelligence_type: str | None = None,
    data_source_id: int | None = None,
) -> Result[Page[InsightIntelligenceCandidateListItem]]:
    result = await insight_intelligence_service.list_candidates(
        db,
        page=page,
        size=size,
        keyword=keyword,
        review_status=review_status,
        subject_type=subject_type,
        intelligence_type=intelligence_type,
        data_source_id=data_source_id,
        user_id=current_user.id,
        is_admin=_is_admin(current_user),
    )
    return Result.success(data=result)


@router.get("/intelligence", response_model=Result[Page[InsightIntelligenceListItem]])
async def list_intelligences(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
    page: int = 1,
    size: int = 20,
    keyword: str | None = None,
    subject_type: str | None = None,
    intelligence_type: str | None = None,
    visibility_scope: str | None = None,
) -> Result[Page[InsightIntelligenceListItem]]:
    result = await insight_intelligence_service.list_intelligences(
        db,
        page=page,
        size=size,
        keyword=keyword,
        subject_type=subject_type,
        intelligence_type=intelligence_type,
        visibility_scope=visibility_scope,
        user_id=current_user.id,
        is_admin=_is_admin(current_user),
    )
    return Result.success(data=result)


@router.post("/intelligence", response_model=Result[InsightIntelligenceDetail])
async def create_intelligence(
    *,
    payload: InsightIntelligenceCreate,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
) -> Result[InsightIntelligenceDetail]:
    try:
        result = await insight_intelligence_service.create_intelligence(db, payload, current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Result.success(data=result, msg="正式情报已新增")


@router.get("/intelligence/{intelligence_id}", response_model=Result[InsightIntelligenceDetail])
async def get_intelligence_detail(
    *,
    intelligence_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
) -> Result[InsightIntelligenceDetail]:
    try:
        result = await insight_intelligence_service.get_intelligence_detail(
            db,
            intelligence_id,
            user_id=current_user.id,
            is_admin=_is_admin(current_user),
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Result.success(data=result)


@router.put("/intelligence/{intelligence_id}", response_model=Result[InsightIntelligenceDetail])
async def update_intelligence(
    *,
    intelligence_id: int,
    payload: InsightIntelligenceUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
) -> Result[InsightIntelligenceDetail]:
    try:
        result = await insight_intelligence_service.update_intelligence(
            db,
            intelligence_id,
            payload,
            user_id=current_user.id,
            is_admin=_is_admin(current_user),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Result.success(data=result, msg="正式情报已更新")


@router.post("/intelligence/{intelligence_id}/sources", response_model=Result[InsightIntelligenceSourceRead])
async def add_intelligence_source(
    *,
    intelligence_id: int,
    payload: InsightIntelligenceSourceCreate,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
) -> Result[InsightIntelligenceSourceRead]:
    try:
        result = await insight_intelligence_service.add_source(
            db,
            intelligence_id,
            payload,
            user_id=current_user.id,
            is_admin=_is_admin(current_user),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Result.success(data=result, msg="来源证据已补充")


@router.get("/intelligence/{intelligence_id}/visibility-rules", response_model=Result[list[InsightVisibilityRuleRead]])
async def list_intelligence_visibility_rules(
    *,
    intelligence_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
) -> Result[list[InsightVisibilityRuleRead]]:
    try:
        result = await insight_intelligence_service.list_visibility_rules(
            db,
            intelligence_id,
            user_id=current_user.id,
            is_admin=_is_admin(current_user),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Result.success(data=result)


@router.post("/intelligence/{intelligence_id}/visibility-rules", response_model=Result[InsightVisibilityRuleRead])
async def grant_intelligence_visibility(
    *,
    intelligence_id: int,
    payload: InsightVisibilityRuleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
) -> Result[InsightVisibilityRuleRead]:
    try:
        result = await insight_intelligence_service.grant_visibility(
            db,
            intelligence_id,
            payload,
            user_id=current_user.id,
            is_admin=_is_admin(current_user),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Result.success(data=result, msg="情报可见性已授权")


@router.get("/intelligence-pool", response_model=Result[list[InsightUserIntelligencePoolRead]])
async def list_my_intelligence_pool(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
    pool_type: str | None = None,
) -> Result[list[InsightUserIntelligencePoolRead]]:
    result = await insight_intelligence_service.list_user_pool(db, user_id=current_user.id, pool_type=pool_type)
    return Result.success(data=result)


@router.post("/intelligence/{intelligence_id}/pool", response_model=Result[InsightUserIntelligencePoolRead])
async def upsert_my_intelligence_pool(
    *,
    intelligence_id: int,
    payload: InsightPoolUpsertRequest,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
) -> Result[InsightUserIntelligencePoolRead]:
    try:
        result = await insight_intelligence_service.upsert_user_pool(
            db,
            intelligence_id,
            payload,
            user_id=current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Result.success(data=result, msg="情报池已更新")


@router.delete("/intelligence/{intelligence_id}/pool/{pool_type}", response_model=Result[None])
async def remove_my_intelligence_pool(
    *,
    intelligence_id: int,
    pool_type: str,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
) -> Result[None]:
    await insight_intelligence_service.remove_user_pool(
        db,
        intelligence_id,
        pool_type,
        user_id=current_user.id,
    )
    return Result.success(msg="情报池记录已移除")


@router.post(
    "/intelligence/candidates/{candidate_id}/promote",
    response_model=Result[InsightCandidateReviewResponse],
)
async def promote_intelligence_candidate(
    *,
    candidate_id: int,
    payload: InsightCandidatePromoteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
) -> Result[InsightCandidateReviewResponse]:
    try:
        result = await insight_intelligence_service.promote_candidate(
            db,
            candidate_id,
            payload,
            current_user.id,
            is_admin=_is_admin(current_user),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Result.success(data=result, msg="候选情报已转为正式情报")


@router.post(
    "/intelligence/candidates/{candidate_id}/reject",
    response_model=Result[InsightCandidateReviewResponse],
)
async def reject_intelligence_candidate(
    *,
    candidate_id: int,
    payload: InsightCandidateReviewRequest,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
) -> Result[InsightCandidateReviewResponse]:
    try:
        result = await insight_intelligence_service.reject_candidate(
            db,
            candidate_id,
            payload,
            current_user.id,
            is_admin=_is_admin(current_user),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Result.success(data=result, msg="候选情报已驳回")


@router.post(
    "/intelligence/candidates/{candidate_id}/ignore",
    response_model=Result[InsightCandidateReviewResponse],
)
async def ignore_intelligence_candidate(
    *,
    candidate_id: int,
    payload: InsightCandidateReviewRequest,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
) -> Result[InsightCandidateReviewResponse]:
    try:
        result = await insight_intelligence_service.ignore_candidate(
            db,
            candidate_id,
            payload,
            current_user.id,
            is_admin=_is_admin(current_user),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Result.success(data=result, msg="候选情报已忽略")


def _is_admin(user: SysUser) -> bool:
    return bool(getattr(user, "is_superuser", False) or getattr(user, "role", None) == "admin")
