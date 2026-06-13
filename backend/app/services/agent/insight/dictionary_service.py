import re
from datetime import datetime
from uuid import uuid4

from sqlalchemy import func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.agent.insight import InsightIntelligence, InsightTag
from app.schemas.agent.insight.dictionary import (
    InsightDictionaryOverview,
    InsightIntelligenceTypeRead,
    InsightTagCreate,
    InsightTagRead,
    InsightTagUpdate,
)


INSIGHT_INTELLIGENCE_TYPES: tuple[dict[str, str | int], ...] = (
    {"type_code": "industry_news", "type_name": "行业资讯", "description": "行业趋势、市场变化和业务环境信息。", "sort_no": 10},
    {"type_code": "competitor_update", "type_name": "竞品动态", "description": "竞品产品、渠道、客户和市场动作。", "sort_no": 20},
    {"type_code": "policy_regulation", "type_name": "政策监管", "description": "政策、法规、标准和监管变化。", "sort_no": 30},
    {"type_code": "technology_trend", "type_name": "技术趋势", "description": "技术路线、方案能力和创新方向。", "sort_no": 40},
    {"type_code": "product_update", "type_name": "产品动态", "description": "产品发布、升级、价格和服务变化。", "sort_no": 50},
    {"type_code": "customer_signal", "type_name": "客户动向", "description": "客户经营、采购、扩张和合作信号。", "sort_no": 60},
    {"type_code": "tender_bid", "type_name": "招投标", "description": "招标、采购公告、中标和项目机会。", "sort_no": 70},
    {"type_code": "price_market", "type_name": "价格行情", "description": "价格、供需、库存和行情波动。", "sort_no": 80},
    {"type_code": "risk_warning", "type_name": "风险预警", "description": "经营、合规、舆情和交付风险。", "sort_no": 90},
    {"type_code": "cooperation_opportunity", "type_name": "合作机会", "description": "潜在合作、销售跟进和方案匹配机会。", "sort_no": 100},
)


class InsightDictionaryService:
    async def list_tags(
        self,
        db: AsyncSession,
        *,
        tag_type: str | None = None,
        include_disabled: bool = False,
    ) -> list[InsightTagRead]:
        statement = select(InsightTag).where(InsightTag.is_deleted == 0)
        if tag_type:
            statement = statement.where(InsightTag.tag_type == tag_type)
        if not include_disabled:
            statement = statement.where(InsightTag.status == "active")
        statement = statement.order_by(InsightTag.sort_no, InsightTag.id)
        result = await db.exec(statement)
        return [self._to_tag_read(tag) for tag in result.all()]

    async def create_tag(self, db: AsyncSession, payload: InsightTagCreate, user_id: int | None) -> InsightTagRead:
        tag_code = self._normalize_tag_code(payload.tag_code, payload.tag_name)
        await self._ensure_tag_code_available(db, tag_code)
        tag = InsightTag(
            tag_code=tag_code,
            tag_name=payload.tag_name.strip(),
            tag_type=payload.tag_type.strip() or "business",
            color=payload.color,
            sort_no=payload.sort_no,
            status="active",
            create_by=str(user_id) if user_id else None,
            update_by=str(user_id) if user_id else None,
        )
        db.add(tag)
        await db.commit()
        await db.refresh(tag)
        return self._to_tag_read(tag)

    async def update_tag(self, db: AsyncSession, tag_id: int, payload: InsightTagUpdate, user_id: int | None) -> InsightTagRead:
        tag = await self._get_tag(db, tag_id)
        data = payload.model_dump(exclude_unset=True)
        allowed_status = {"active", "disabled"}
        if "status" in data and data["status"] not in allowed_status:
            raise ValueError("标签状态只能为 active 或 disabled")
        for field, value in data.items():
            if isinstance(value, str):
                value = value.strip()
            setattr(tag, field, value)
        tag.update_time = datetime.now()
        tag.update_by = str(user_id) if user_id else None
        await db.commit()
        await db.refresh(tag)
        return self._to_tag_read(tag)

    async def disable_tag(self, db: AsyncSession, tag_id: int, user_id: int | None) -> InsightTagRead:
        tag = await self._get_tag(db, tag_id)
        tag.status = "disabled"
        tag.update_time = datetime.now()
        tag.update_by = str(user_id) if user_id else None
        await db.commit()
        await db.refresh(tag)
        return self._to_tag_read(tag)

    async def list_intelligence_types(self, db: AsyncSession) -> list[InsightIntelligenceTypeRead]:
        usage_counts = await self._intelligence_type_usage_counts(db)
        return [
            InsightIntelligenceTypeRead(
                type_code=str(item["type_code"]),
                type_name=str(item["type_name"]),
                description=str(item["description"]),
                sort_no=int(item["sort_no"]),
                usage_count=usage_counts.get(str(item["type_name"]), 0),
            )
            for item in INSIGHT_INTELLIGENCE_TYPES
        ]

    async def get_overview(self, db: AsyncSession) -> InsightDictionaryOverview:
        tags = await self.list_tags(db, include_disabled=True)
        intelligence_types = await self.list_intelligence_types(db)
        return InsightDictionaryOverview(tags=tags, intelligence_types=intelligence_types)

    async def _get_tag(self, db: AsyncSession, tag_id: int) -> InsightTag:
        result = await db.exec(select(InsightTag).where(InsightTag.id == tag_id, InsightTag.is_deleted == 0))
        tag = result.first()
        if not tag:
            raise ValueError("标签不存在")
        return tag

    async def _ensure_tag_code_available(self, db: AsyncSession, tag_code: str) -> None:
        result = await db.exec(select(InsightTag).where(InsightTag.tag_code == tag_code, InsightTag.is_deleted == 0))
        if result.first():
            raise ValueError("标签编码已存在")

    async def _intelligence_type_usage_counts(self, db: AsyncSession) -> dict[str, int]:
        result = await db.exec(
            select(InsightIntelligence.intelligence_type, func.count(InsightIntelligence.id))
            .where(InsightIntelligence.is_deleted == 0)
            .group_by(InsightIntelligence.intelligence_type)
        )
        return {str(type_name): int(count) for type_name, count in result.all() if type_name}

    def _normalize_tag_code(self, tag_code: str | None, tag_name: str) -> str:
        value = (tag_code or "").strip().lower()
        if not value:
            value = re.sub(r"[^a-zA-Z0-9_]+", "_", tag_name.strip().lower()).strip("_")
        if not value:
            value = f"tag_{uuid4().hex[:8]}"
        if not re.fullmatch(r"[a-zA-Z0-9_]{2,64}", value):
            raise ValueError("标签编码只能包含字母、数字和下划线，长度 2-64")
        return value

    def _to_tag_read(self, tag: InsightTag) -> InsightTagRead:
        return InsightTagRead.model_validate(tag, from_attributes=True)


insight_dictionary_service = InsightDictionaryService()
