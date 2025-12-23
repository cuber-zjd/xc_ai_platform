from datetime import datetime
import uuid
from typing import List, Optional
from fastapi import UploadFile
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select, desc

from app.models.contract.contract_model import Contract, ContractStatusEnum, ContractAuditLog
from app.schemas.contract import ContractCreate, ContractUpdate
from app.services.file_service import file_service
from app.core.logger import logger

from fastapi import BackgroundTasks
from app.agents.definitions.contract_review.graph import review_graph
from app.core.logger import logger
from app.models.contract.contract_model import ContractStatusEnum, TrafficLightEnum, ContractAuditLog, RiskLevelEnum
import asyncio

async def run_analysis_task(contract_id: int, file_path: str, contract_type: str, session: AsyncSession): # Note: Session management in background task is tricky
    # Better to create a new session here or pass a session factory
    # For MVP: We need to handle session creation inside the background task
    from app.db.session import async_session
    async with async_session() as db:
        logger.info(f"Starting Analysis for Contract {contract_id}")
        
        # 1. Update Status to ANALYZING
        contract = await contract_service.get_contract(db, contract_id)
        if not contract: return
        contract.status = ContractStatusEnum.ANALYZING
        db.add(contract)
        await db.commit()
        
        # 2. Run Graph
        inputs = {
            "contract_id": contract_id,
            "file_path": file_path,
            "contract_type": contract_type,
            "text_content": "",
            "rule_findings": [],
            "llm_findings": []
        }
        
        try:
            result = await review_graph.ainvoke(inputs)
            
            # 3. Save Results
            contract.status = ContractStatusEnum.ANALYSIS_COMPLETED
            contract.traffic_light = TrafficLightEnum(result["traffic_light"]) if result.get("traffic_light") else TrafficLightEnum.NONE
            contract.analysis_summary = result.get("analysis_summary", {})
            
            # Audit Logs
            all_findings = result.get("rule_findings", []) + result.get("llm_findings", [])
            for f in all_findings:
                log = ContractAuditLog(
                    contract_id=contract.id,
                    risk_level=RiskLevelEnum(f.risk_level),
                    finding_summary=f.summary,
                    finding_detail=f.detail,
                    quote_text=f.quote,
                    page_num=f.page
                )
                db.add(log)
            
            logger.info(f"Analysis Finished for {contract_id}. Status: {contract.traffic_light}")
            
        except Exception as e:
            logger.error(f"Analysis Failed: {e}")
            contract.status = ContractStatusEnum.ANALYSIS_FAILED
            contract.analysis_summary = {"error": str(e)}
            
        db.add(contract)
        await db.commit()

class ContractService:
    
    async def create_contract(self, session: AsyncSession, file: UploadFile, meta: ContractCreate, background_tasks: BackgroundTasks) -> Contract:
        """
        1. Upload file to MinIO
        2. Create DB record
        3. Trigger AI Agent
        """

        # 1. Upload
        file_ext = file.filename.split('.')[-1] if '.' in file.filename else "doc"
        unique_filename = f"{uuid.uuid4()}.{file_ext}"
        object_name = f"contracts/{datetime.now().strftime('%Y/%m')}/{unique_filename}"
        
        file_content = await file.read()
        await file_service.upload_file(file_content, object_name, content_type=file.content_type)
        
        # 2. DB Record
        db_contract = Contract(
            title=meta.title,
            contract_type=meta.contract_type,
            initiator_id=meta.initiator_id,
            file_path=object_name,
            file_version="v1",
            status=ContractStatusEnum.UPLOADING
        )
        session.add(db_contract)
        await session.commit()
        await session.refresh(db_contract)
        
        logger.info(f"Contract created: {db_contract.id}, Path: {object_name}")
        
        # 3. Trigger AI Agent
        background_tasks.add_task(
            run_analysis_task, 
            contract_id=db_contract.id, 
            file_path=object_name, 
            contract_type=meta.contract_type, 
            session=None # Pass None, task creates its own session
        )
        
        return db_contract

    async def get_contract(self, session: AsyncSession, contract_id: int) -> Optional[Contract]:
        statement = select(Contract).where(Contract.id == contract_id)
        result = await session.exec(statement)
        return result.first()

    async def get_contract_with_logs(self, session: AsyncSession, contract_id: int) -> Optional[Contract]:
        # Eager load logs if relationships set up correctly, 
        # but AsyncSession lazy loading is tricky. Often better to join or separate query.
        # For simplicity, let's rely on SQLModel relationship lazy loading if working, 
        # or explicit query. Here we use select(Contract) options(selectinload...) for async.
        from sqlalchemy.orm import selectinload
        statement = select(Contract).options(selectinload(Contract.audit_logs)).where(Contract.id == contract_id)
        result = await session.exec(statement)
        return result.first()

    async def get_user_contracts(self, session: AsyncSession, user_id: int, skip: int = 0, limit: int = 10) -> List[Contract]:
        statement = select(Contract).where(Contract.initiator_id == user_id).order_by(desc(Contract.create_time)).offset(skip).limit(limit)
        result = await session.exec(statement)
        return result.all()

    async def update_status(self, session: AsyncSession, contract_id: int, status: ContractStatusEnum) -> Contract:
        contract = await self.get_contract(session, contract_id)
        if not contract:
            raise ValueError("Contract not found")
        contract.status = status
        session.add(contract)
        await session.commit()
        await session.refresh(contract)
        return contract

contract_service = ContractService()
