"""妙搭服务端专用边界；不接受浏览器直接传入旧平台身份。"""
from fastapi import APIRouter, Depends, Request
from sqlmodel.ext.asyncio.session import AsyncSession
from app.db.session import get_db
from app.schemas.agent.insight.workspace import CollectionInput, CollectionNeed, CollectionStatus, ReportInput, ReportQuery, PushInput, PushAction
from app.services.agent.insight import workspace_catalog as catalog, workspace_collections as collections, workspace_pushes as pushes
from app.services.agent.insight.workspace_auth import authenticate, WorkspacePrincipal

router = APIRouter()

async def principal(request: Request, db: AsyncSession = Depends(get_db)) -> WorkspacePrincipal:
    return await authenticate(request, db)

@router.post("/options")
async def options(db: AsyncSession = Depends(get_db), who: WorkspacePrincipal = Depends(principal)) -> dict:
    return await catalog.options(db, who)

@router.post("/collections/list")
async def collection_list(db: AsyncSession = Depends(get_db), who: WorkspacePrincipal = Depends(principal)) -> list[dict]:
    return await collections.list_collections(db, who)

@router.post("/collections/interpret")
async def interpret(body: CollectionNeed, who: WorkspacePrincipal = Depends(principal)) -> dict:
    return await collections.interpret(body)

@router.post("/collections/save")
async def collection_save(body: CollectionInput, db: AsyncSession = Depends(get_db), who: WorkspacePrincipal = Depends(principal)) -> dict:
    return await collections.save_collection(db, who, body)

@router.post("/collections/status")
async def collection_status(body: CollectionStatus, db: AsyncSession = Depends(get_db), who: WorkspacePrincipal = Depends(principal)) -> dict:
    return await collections.set_status(db, who, body)

@router.post("/reports/list")
async def report_list(body: ReportQuery, db: AsyncSession = Depends(get_db), who: WorkspacePrincipal = Depends(principal)) -> dict:
    return await catalog.list_reports(db, who, body)

@router.post("/reports/save")
async def report_save(body: ReportInput, db: AsyncSession = Depends(get_db), who: WorkspacePrincipal = Depends(principal)) -> dict:
    return await catalog.save_report(db, who, body)

@router.post("/pushes/list")
async def push_list(db: AsyncSession = Depends(get_db), who: WorkspacePrincipal = Depends(principal)) -> list[dict]:
    return await pushes.list_pushes(db, who)

@router.post("/pushes/save")
async def push_save(body: PushInput, db: AsyncSession = Depends(get_db), who: WorkspacePrincipal = Depends(principal)) -> dict:
    return await pushes.save_push(db, who, body)

@router.post("/pushes/action")
async def push_action(body: PushAction, db: AsyncSession = Depends(get_db), who: WorkspacePrincipal = Depends(principal)) -> dict:
    return await pushes.perform_action(db, who, body)
