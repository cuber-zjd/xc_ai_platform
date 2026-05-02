from typing import List
from fastapi import APIRouter, Depends, File, UploadFile, Form, HTTPException, status, BackgroundTasks
from sqlmodel.ext.asyncio.session import AsyncSession
from app.api.deps import get_db
from app.schemas.agent.contract.contract import ContractRead, ContractCreate, ContractDetailRead
from app.services.agent.contract.contract_service import contract_service
from app.services.system.file_service import file_service
from app.models.contract.contract_model import Contract

router = APIRouter()
@router.post("/upload", response_model=ContractRead)
async def upload_contract(
    *,
    db: AsyncSession = Depends(get_db),
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    title: str = Form(...),
    contract_type: str = Form("General"),
    initiator_id: int = Form(1) # TODO: From current_user
):
    """
    Upload a contract file and create a record.
    """
    contract_create = ContractCreate(
        title=title, 
        contract_type=contract_type, 
        initiator_id=initiator_id
    )
    contract = await contract_service.create_contract(db, file, contract_create, background_tasks)
    return contract

@router.get("/{contract_id}", response_model=ContractDetailRead)
async def get_contract_detail(
    contract_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Get contract details with audit logs and presigned URL.
    """
    contract = await contract_service.get_contract_with_logs(db, contract_id)
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")
    
    # Generate presigned URL (with fallback if MinIO fails)
    url = None
    try:
        url = await file_service.get_presigned_url(contract.file_path)
    except Exception as e:
        # Log error but don't fail the whole request
        from app.core.logger import logger
        logger.warning(f"Failed to get presigned URL for contract {contract_id}: {e}")
    
    # Convert to schema manually or let Pydantic handle if fields match
    # We need to inject file_url
    return ContractDetailRead(
        **contract.model_dump(), 
        file_url=url,
        audit_logs=contract.audit_logs
    )

@router.get("", response_model=List[ContractRead])
async def list_contracts(
    db: AsyncSession = Depends(get_db),
    skip: int = 0,
    limit: int = 10,
    user_id: int = 1 # TODO: From current_user
):
    contracts = await contract_service.get_user_contracts(db, user_id, skip, limit)
    return contracts


@router.get("/{contract_id}/editor-config")
async def get_editor_config(
    contract_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    获取 OnlyOffice 编辑器配置（含 JWT 签名）
    前端使用此配置初始化 OnlyOffice 编辑器
    """
    from app.services.agent.contract.onlyoffice_service import onlyoffice_service
    from app.core.logger import logger
    
    contract = await contract_service.get_contract(db, contract_id)
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")
    
    # 生成 MinIO presigned URL
    try:
        document_url = await file_service.get_presigned_url(contract.file_path)
    except Exception as e:
        logger.error(f"Failed to get presigned URL: {e}")
        raise HTTPException(status_code=500, detail="无法生成文档访问链接")
    
    # 获取文件扩展名
    file_ext = contract.file_path.split('.')[-1] if '.' in contract.file_path else "docx"
    
    # 生成编辑器配置
    editor_config = onlyoffice_service.generate_editor_config(
        document_url=document_url,
        document_key=f"{contract.id}-{contract.file_version}",
        document_title=contract.title,
        file_ext=file_ext,
        user_id=1,  # TODO: 从 current_user 获取
        user_name="测试用户",  # TODO: 从 current_user 获取
        edit_mode=False,  # 默认只读模式
    )
    
    return editor_config
