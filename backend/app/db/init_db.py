from sqlmodel import SQLModel
from app.db.session import engine
from app.core.logger import logger

# Import all models here to ensure they are registered with SQLModel.metadata
from app.models.system import sys_user, sys_dept, sys_company, sys_post
from app.models.contract import contract_model

async def init_db():
    """
    Creates the database tables based on the SQLModel metadata.
    This should be run on startup.
    """
    logger.info("Creating database tables...")
    async with engine.begin() as conn:
        # await conn.run_sync(SQLModel.metadata.drop_all) # DANGEROUS: For dev only if needed
        await conn.run_sync(SQLModel.metadata.create_all)
    
    # Init Seed Data (Rules)
    from sqlmodel import select
    from app.models.contract.contract_model import ContractRule, RiskLevelEnum
    from app.db.session import async_session
    
    async with async_session() as session:
        statement = select(ContractRule)
        result = await session.exec(statement)
        if not result.first():
            logger.info("Seeding Contract Rules...")
            rules = [
                ContractRule(
                    rule_name="违约金条款检查", 
                    description="检查合同是否包含违约金相关说明",
                    category="GLOBAL",
                    severity=RiskLevelEnum.WARNING,
                    rule_definition="Check for default penalty"
                ),
                ContractRule(
                    rule_name="付款账期限制", 
                    description="付款账期不得超过60天",
                    category="Purchase",
                    severity=RiskLevelEnum.CRITICAL,
                    rule_definition="Payment terms <= 60 days"
                )
            ]
            session.add_all(rules)
            await session.commit()

    logger.info("Database tables created successfully.")
