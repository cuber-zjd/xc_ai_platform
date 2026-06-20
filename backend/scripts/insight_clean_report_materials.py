import argparse
import asyncio
from copy import deepcopy
from datetime import datetime
from typing import Any

from sqlalchemy import func
from sqlmodel import select

from app.db.session import async_session, engine
from app.models.agent.insight import InsightIntelligence, InsightReport, InsightReportMaterial


engine.echo = False


EVIDENCE_KEYS = {"evidence_ids", "citation_ids", "reference_ids", "intelligence_ids"}
PARAGRAPH_KEYS = {"paragraphs", "findings", "opportunities", "risks", "reflection", "follow_up_questions"}


def normalize_text(value: object) -> str:
    return " ".join(str(value or "").lower().split())


def build_blocked_texts(rows: list[InsightIntelligence]) -> list[str]:
    blocked: list[str] = []
    for row in rows:
        for value in [row.title, row.summary]:
            text = normalize_text(value)
            if len(text) >= 24:
                blocked.append(text[:180])
    return blocked


def has_blocked_text(value: object, blocked_texts: list[str]) -> bool:
    text = normalize_text(value)
    if not text:
        return False
    for blocked in blocked_texts:
        if not blocked:
            continue
        if blocked in text or text[:180] in blocked:
            return True
    return False


def prune_evidence_ids(value: Any, blocked_ids: set[int]) -> tuple[Any, int]:
    if isinstance(value, dict):
        changed = 0
        next_value: dict[str, Any] = {}
        for key, item in value.items():
            if key in EVIDENCE_KEYS and isinstance(item, list):
                filtered = [entry for entry in item if not isinstance(entry, int) or entry not in blocked_ids]
                changed += len(item) - len(filtered)
                next_value[key] = filtered
                continue
            next_item, item_changed = prune_evidence_ids(item, blocked_ids)
            changed += item_changed
            next_value[key] = next_item
        return next_value, changed
    if isinstance(value, list):
        changed = 0
        next_items: list[Any] = []
        for item in value:
            next_item, item_changed = prune_evidence_ids(item, blocked_ids)
            changed += item_changed
            next_items.append(next_item)
        return next_items, changed
    return value, 0


def item_contains_blocked_text(value: Any, blocked_texts: list[str]) -> bool:
    if isinstance(value, dict):
        return any(item_contains_blocked_text(item, blocked_texts) for item in value.values())
    if isinstance(value, list):
        return any(item_contains_blocked_text(item, blocked_texts) for item in value)
    return isinstance(value, str) and has_blocked_text(value, blocked_texts)


def prune_blocked_text(value: Any, blocked_texts: list[str]) -> tuple[Any, int]:
    if isinstance(value, dict):
        changed = 0
        next_value: dict[str, Any] = {}
        for key, item in value.items():
            if key in PARAGRAPH_KEYS and isinstance(item, list):
                filtered = [
                    entry
                    for entry in item
                    if not (
                        (isinstance(entry, str) and has_blocked_text(entry, blocked_texts))
                        or (isinstance(entry, dict) and item_contains_blocked_text(entry, blocked_texts))
                    )
                ]
                changed += len(item) - len(filtered)
                next_value[key] = filtered
                continue
            if key in {"title", "summary", "insight", "evidence", "quote_text"} and has_blocked_text(item, blocked_texts):
                changed += 1
                next_value[key] = ""
                continue
            next_item, item_changed = prune_blocked_text(item, blocked_texts)
            changed += item_changed
            next_value[key] = next_item
        return next_value, changed
    if isinstance(value, list):
        changed = 0
        next_items: list[Any] = []
        for item in value:
            if isinstance(item, dict) and item_contains_blocked_text(item, blocked_texts):
                changed += 1
                continue
            if isinstance(item, str) and has_blocked_text(item, blocked_texts):
                changed += 1
                continue
            next_item, item_changed = prune_blocked_text(item, blocked_texts)
            changed += item_changed
            next_items.append(next_item)
        return next_items, changed
    if isinstance(value, str) and has_blocked_text(value, blocked_texts):
        return "", 1
    return value, 0


async def clean_report_materials(*, dry_run: bool) -> dict[str, Any]:
    now = datetime.now()
    async with async_session() as db:
        invalid_materials = list(
            (
                await db.exec(
                    select(InsightReportMaterial)
                    .join(InsightIntelligence, InsightIntelligence.id == InsightReportMaterial.intelligence_id, isouter=True)
                    .where(
                        (InsightReportMaterial.is_deleted != 0)
                        | (InsightIntelligence.id.is_(None))
                        | (InsightIntelligence.status != "active")
                        | (InsightIntelligence.review_status != "approved"),
                    )
                )
            ).all()
        )
        invalid_intelligences = list(
            (
                await db.exec(
                    select(InsightIntelligence).where(
                        (InsightIntelligence.status != "active")
                        | (InsightIntelligence.review_status != "approved")
                        | (InsightIntelligence.is_deleted != 0),
                    )
                )
            ).all()
        )
        blocked_texts = build_blocked_texts(invalid_intelligences)
        report_to_invalid_ids: dict[int, set[int]] = {}
        for material in invalid_materials:
            report_to_invalid_ids.setdefault(material.report_id, set()).add(material.intelligence_id)

        reports = list((await db.exec(select(InsightReport))).all())
        report_updates: list[dict[str, Any]] = []
        for report in reports:
            report_id = report.id or 0
            blocked_ids = report_to_invalid_ids.get(report_id, set())
            original_content = deepcopy(report.content_json or {})
            next_content, pruned_count = prune_evidence_ids(original_content, blocked_ids)
            next_content, pruned_text_count = prune_blocked_text(next_content, blocked_texts)
            active_material_count = (
                await db.exec(
                    select(func.count())
                    .select_from(InsightReportMaterial)
                    .where(
                        InsightReportMaterial.report_id == report.id,
                        InsightReportMaterial.is_deleted == 0,
                    )
                )
            ).one()
            next_material_count = int(active_material_count or 0)
            needs_update = pruned_count > 0 or pruned_text_count > 0 or report.material_count != next_material_count
            if needs_update:
                report_updates.append(
                    {
                        "report_id": report.id,
                        "title": report.title,
                        "invalid_evidence_ids": len(blocked_ids),
                        "pruned_evidence_ids": pruned_count,
                        "pruned_text_items": pruned_text_count,
                        "old_material_count": report.material_count,
                        "material_count": next_material_count,
                    }
                )
            if not dry_run:
                if needs_update:
                    report.content_json = next_content
                    report.material_count = next_material_count
                    report.update_time = now

        if not dry_run:
            for material in invalid_materials:
                if material.is_deleted == 0:
                    material.is_deleted = 1
                    material.update_time = now
                    material.update_by = "insight_clean_report_materials"
            await db.commit()

        return {
            "dry_run": dry_run,
            "invalid_material_count": len(invalid_materials),
            "invalid_intelligence_text_count": len(blocked_texts),
            "affected_report_count": len(report_updates),
            "reports": report_updates,
        }


async def main() -> None:
    parser = argparse.ArgumentParser(description="清理报告中引用 inactive 或未审核通过情报的素材。")
    parser.add_argument("--apply", action="store_true", help="实际写入清理结果；默认只预览。")
    args = parser.parse_args()
    result = await clean_report_materials(dry_run=not args.apply)
    print(result)


if __name__ == "__main__":
    asyncio.run(main())
