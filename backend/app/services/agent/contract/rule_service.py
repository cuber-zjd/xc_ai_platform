from typing import List
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from app.models.contract.contract_model import ContractRule

class RuleService:
    async def get_active_rules(self, session: AsyncSession, category: str = "GLOBAL") -> List[ContractRule]:
        # TODO: Filter by category
        statement = select(ContractRule).where(ContractRule.is_active)
        result = await session.exec(statement)
        return result.all()

rule_service = RuleService()
