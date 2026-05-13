from typing import List

from fastapi import APIRouter, Depends, File, UploadFile
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api import deps
from app.db.session import get_db
from app.models.system.sys_user import SysUser
from app.schemas.knowledge_base import (
    KnowledgeBaseCreate,
    KnowledgeBaseRead,
    KnowledgeDocumentRead,
    KnowledgeSearchRequest,
    KnowledgeSearchResponse,
)
from app.schemas.result import Result
from app.services.knowledge_base_service import knowledge_base_service

router = APIRouter()


@router.get("", response_model=Result[List[KnowledgeBaseRead]])
async def list_knowledge_bases(
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(deps.get_current_user),
) -> Result[List[KnowledgeBaseRead]]:
    data = await knowledge_base_service.list_bases(db, user_id=current_user.id)
    return Result.success(data=data)


@router.post("", response_model=Result[KnowledgeBaseRead])
async def create_knowledge_base(
    obj_in: KnowledgeBaseCreate,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(deps.get_current_user),
) -> Result[KnowledgeBaseRead]:
    data = await knowledge_base_service.create(db, obj_in=obj_in, owner_id=current_user.id)
    return Result.success(data=data, msg="知识库已创建")


@router.post("/{knowledge_base_id}/documents", response_model=Result[KnowledgeDocumentRead])
async def upload_document(
    knowledge_base_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(deps.get_current_user),
) -> Result[KnowledgeDocumentRead]:
    data = await knowledge_base_service.upload_document(db, knowledge_base_id=knowledge_base_id, file=file)
    return Result.success(data=data, msg="文档已上传并完成第一版索引")


@router.post("/{knowledge_base_id}/search", response_model=Result[KnowledgeSearchResponse])
async def search_knowledge_base(
    knowledge_base_id: int,
    request: KnowledgeSearchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(deps.get_current_user),
) -> Result[KnowledgeSearchResponse]:
    data = await knowledge_base_service.search(db, knowledge_base_id, request.query, request.top_k)
    return Result.success(data=data)


@router.post("/{knowledge_base_id}/documents/{document_id}/reindex", response_model=Result[KnowledgeDocumentRead])
async def reindex_document(
    knowledge_base_id: int,
    document_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(deps.get_current_user),
) -> Result[KnowledgeDocumentRead]:
    data = await knowledge_base_service.reindex_document(db, document_id=document_id)
    return Result.success(data=data, msg="文档索引已重建")
