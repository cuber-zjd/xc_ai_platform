import asyncio
from datetime import datetime
from uuid import uuid4

from app.db.session import async_session
from app.schemas.agent.insight.dictionary import InsightTagCreate, InsightTagUpdate
from app.services.agent.insight.dictionary_service import insight_dictionary_service


async def main() -> None:
    tag_code = f"accept_{uuid4().hex[:10]}"
    tag_id: int | None = None
    async with async_session() as db:
        created = await insight_dictionary_service.create_tag(
            db,
            InsightTagCreate(tag_code=tag_code, tag_name="验收临时标签", tag_type="business", sort_no=999),
            user_id=0,
        )
        tag_id = created.id
        updated = await insight_dictionary_service.update_tag(
            db,
            created.id,
            InsightTagUpdate(tag_name="验收临时标签已更新", sort_no=1000),
            user_id=0,
        )
        disabled = await insight_dictionary_service.disable_tag(db, created.id, user_id=0)
        tags = await insight_dictionary_service.list_tags(db, include_disabled=True)
        active_tags = await insight_dictionary_service.list_tags(db, include_disabled=False)
        intelligence_types = await insight_dictionary_service.list_intelligence_types(db)
        overview = await insight_dictionary_service.get_overview(db)

        temp_tag = await insight_dictionary_service._get_tag(db, created.id)
        temp_tag.is_deleted = 1
        temp_tag.update_time = datetime.now()
        await db.commit()

    checks = {
        "标签可创建": created.tag_code == tag_code and created.status == "active",
        "标签可更新": updated.tag_name == "验收临时标签已更新" and updated.sort_no == 1000,
        "标签可禁用": disabled.status == "disabled",
        "禁用标签在全量列表可见": any(item.id == tag_id and item.status == "disabled" for item in tags),
        "禁用标签不在启用列表": all(item.id != tag_id for item in active_tags),
        "情报类型字典可读": len(intelligence_types) >= 6 and all(item.readonly for item in intelligence_types),
        "字典总览包含标签和类型": isinstance(overview.tags, list) and len(overview.intelligence_types) >= 6,
    }
    for name, passed in checks.items():
        print(f"[{'PASS' if passed else 'FAIL'}] {name}")
    if not all(checks.values()):
        failed = [name for name, passed in checks.items() if not passed]
        raise SystemExit(f"Insight 字典验收未通过: {'; '.join(failed)}")


if __name__ == "__main__":
    asyncio.run(main())
