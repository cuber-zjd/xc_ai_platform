import argparse
import asyncio
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from sqlmodel import select

from app.db.session import async_session
from app.models.agent.insight import (
    InsightAssetVector,
    InsightGraphEdge,
    InsightGraphNode,
    InsightIntelligence,
    InsightIntelligenceAsset,
    InsightIntelligenceCandidate,
    InsightIntelligenceSource,
    InsightIntelligenceTag,
    InsightReviewRecord,
    InsightUserIntelligencePool,
    InsightVisibilityRule,
)
from app.services.agent.insight.event_aggregation_service import insight_event_aggregation_service


@dataclass(slots=True)
class DuplicateGroup:
    canonical: InsightIntelligence
    duplicates: list[InsightIntelligence]
    normalized_title: str


class HistoricalEventMerger:
    """以严格规则清理历史正式情报中的同事件重复项。"""

    event_window = timedelta(days=4)

    async def run(self, *, apply: bool, days: int, output: Path) -> dict[str, Any]:
        async with async_session() as db:
            rows = list(
                (
                    await db.exec(
                        select(InsightIntelligence)
                        .where(
                            InsightIntelligence.is_deleted == 0,
                            InsightIntelligence.status == "active",
                            InsightIntelligence.create_time >= datetime.now() - timedelta(days=days),
                        )
                        .order_by(InsightIntelligence.create_time.asc(), InsightIntelligence.id.asc())
                    )
                ).all()
            )
            groups = self._find_groups(rows)
            summary: dict[str, Any] = {
                "mode": "apply" if apply else "dry-run",
                "lookback_days": days,
                "scanned_intelligence_count": len(rows),
                "duplicate_group_count": len(groups),
                "duplicate_intelligence_count": sum(len(group.duplicates) for group in groups),
                "moved_source_count": 0,
                "merged_candidate_count": 0,
                "merged_tag_count": 0,
                "merged_pool_count": 0,
                "merged_permission_count": 0,
                "groups": [self._group_payload(group) for group in groups[:100]],
            }
            if apply:
                for group in groups:
                    await self._merge_group(db, group, summary)
                await db.commit()
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
            return summary

    def _find_groups(self, rows: list[InsightIntelligence]) -> list[DuplicateGroup]:
        buckets: dict[tuple[int, str, str], list[InsightIntelligence]] = defaultdict(list)
        for row in rows:
            normalized = insight_event_aggregation_service._normalize(row.title)
            if len(normalized) < 10:
                continue
            subject_key = str(row.company_id or row.subject_id or 0)
            subject_type = str(getattr(row.subject_type, "value", row.subject_type) or "custom")
            buckets[(row.company_id or 0, f"{subject_type}:{subject_key}", normalized)].append(row)

        groups: list[DuplicateGroup] = []
        for (_, _, normalized_title), items in buckets.items():
            if len(items) < 2:
                continue
            items.sort(key=self._event_time)
            windows: list[list[InsightIntelligence]] = []
            for item in items:
                if not windows or self._event_time(item) - self._event_time(windows[-1][0]) > self.event_window:
                    windows.append([item])
                else:
                    windows[-1].append(item)
            for window in windows:
                compatible = self._compatible_window(window)
                if len(compatible) < 2:
                    continue
                canonical = min(compatible, key=lambda row: (self._event_time(row), row.id or 0))
                groups.append(
                    DuplicateGroup(
                        canonical=canonical,
                        duplicates=[item for item in compatible if item.id != canonical.id],
                        normalized_title=normalized_title,
                    )
                )
        return groups

    def _compatible_window(self, rows: list[InsightIntelligence]) -> list[InsightIntelligence]:
        if len(rows) < 2:
            return rows
        canonical = rows[0]
        canonical_text = insight_event_aggregation_service._join(canonical.title, canonical.summary)
        return [
            row
            for row in rows
            if insight_event_aggregation_service._compatible_actions(
                canonical_text,
                insight_event_aggregation_service._join(row.title, row.summary),
            )
        ]

    async def _merge_group(self, db: Any, group: DuplicateGroup, summary: dict[str, Any]) -> None:
        canonical_id = group.canonical.id or 0
        duplicate_ids = [row.id or 0 for row in group.duplicates]
        existing_urls = {
            source.source_url
            for source in (
                await db.exec(
                    select(InsightIntelligenceSource).where(
                        InsightIntelligenceSource.intelligence_id == canonical_id,
                        InsightIntelligenceSource.is_deleted == 0,
                    )
                )
            ).all()
            if source.source_url
        }
        for duplicate in group.duplicates:
            duplicate_id = duplicate.id or 0
            sources = list(
                (
                    await db.exec(
                        select(InsightIntelligenceSource).where(
                            InsightIntelligenceSource.intelligence_id == duplicate_id,
                            InsightIntelligenceSource.is_deleted == 0,
                        )
                    )
                ).all()
            )
            for source in sources:
                if source.source_url and source.source_url in existing_urls:
                    source.is_deleted = 1
                else:
                    source.intelligence_id = canonical_id
                    if source.source_url:
                        existing_urls.add(source.source_url)
                    summary["moved_source_count"] += 1
                source.update_time = datetime.now()

            summary["merged_candidate_count"] += await self._move_candidates(db, duplicate_id, canonical_id)
            summary["merged_tag_count"] += await self._move_tags(db, duplicate_id, canonical_id)
            summary["merged_pool_count"] += await self._move_pool(db, duplicate_id, canonical_id)
            summary["merged_permission_count"] += await self._move_permissions(db, duplicate_id, canonical_id)
            await self._move_review_records(db, duplicate_id, canonical_id)
            await self._retire_asset(db, duplicate_id)
            duplicate.raw_payload = dict(duplicate.raw_payload or {}) | {
                "event_aggregation": {
                    **dict((duplicate.raw_payload or {}).get("event_aggregation") or {}),
                    "merged_into_intelligence_id": canonical_id,
                    "merged_at": datetime.now().isoformat(),
                    "method": "historical_exact_title",
                }
            }
            duplicate.status = "merged"
            duplicate.is_deleted = 1
            duplicate.update_time = datetime.now()

        canonical_payload = dict(group.canonical.raw_payload or {})
        aggregation = dict(canonical_payload.get("event_aggregation") or {})
        aggregation.update(
            {
                "event_key": aggregation.get("event_key")
                or insight_event_aggregation_service._event_key(group.canonical),
                "merged_intelligence_ids": sorted(
                    set(aggregation.get("merged_intelligence_ids") or []).union(duplicate_ids)
                ),
                "last_merged_at": datetime.now().isoformat(),
                "last_merge_method": "historical_exact_title",
            }
        )
        canonical_payload["event_aggregation"] = aggregation
        group.canonical.raw_payload = canonical_payload
        group.canonical.publish_time = min(
            [item.publish_time for item in [group.canonical, *group.duplicates] if item.publish_time],
            default=group.canonical.publish_time,
        )
        group.canonical.update_time = datetime.now()

    async def _move_candidates(self, db: Any, old_id: int, new_id: int) -> int:
        rows = list(
            (
                await db.exec(
                    select(InsightIntelligenceCandidate).where(
                        InsightIntelligenceCandidate.promoted_intelligence_id == old_id,
                        InsightIntelligenceCandidate.is_deleted == 0,
                    )
                )
            ).all()
        )
        for row in rows:
            row.promoted_intelligence_id = new_id
            row.update_time = datetime.now()
        return len(rows)

    async def _move_tags(self, db: Any, old_id: int, new_id: int) -> int:
        existing = {
            row.tag_id
            for row in (
                await db.exec(
                    select(InsightIntelligenceTag).where(
                        InsightIntelligenceTag.intelligence_id == new_id,
                        InsightIntelligenceTag.is_deleted == 0,
                    )
                )
            ).all()
        }
        moved = 0
        rows = list(
            (
                await db.exec(
                    select(InsightIntelligenceTag).where(
                        InsightIntelligenceTag.intelligence_id == old_id,
                        InsightIntelligenceTag.is_deleted == 0,
                    )
                )
            ).all()
        )
        for row in rows:
            if row.tag_id in existing:
                row.is_deleted = 1
            else:
                row.intelligence_id = new_id
                existing.add(row.tag_id)
                moved += 1
            row.update_time = datetime.now()
        return moved

    async def _move_pool(self, db: Any, old_id: int, new_id: int) -> int:
        existing = {
            (row.user_id, row.pool_type, row.folder_name or "")
            for row in (
                await db.exec(
                    select(InsightUserIntelligencePool).where(
                        InsightUserIntelligencePool.intelligence_id == new_id,
                        InsightUserIntelligencePool.is_deleted == 0,
                    )
                )
            ).all()
        }
        moved = 0
        rows = list(
            (
                await db.exec(
                    select(InsightUserIntelligencePool).where(
                        InsightUserIntelligencePool.intelligence_id == old_id,
                        InsightUserIntelligencePool.is_deleted == 0,
                    )
                )
            ).all()
        )
        for row in rows:
            key = (row.user_id, row.pool_type, row.folder_name or "")
            if key in existing:
                row.is_deleted = 1
            else:
                row.intelligence_id = new_id
                existing.add(key)
                moved += 1
            row.update_time = datetime.now()
        return moved

    async def _move_permissions(self, db: Any, old_id: int, new_id: int) -> int:
        rows = list(
            (
                await db.exec(
                    select(InsightVisibilityRule).where(
                        InsightVisibilityRule.target_type == "intelligence",
                        InsightVisibilityRule.target_id == old_id,
                        InsightVisibilityRule.is_deleted == 0,
                    )
                )
            ).all()
        )
        existing = {
            (item.principal_type, item.principal_id, item.permission)
            for item in (
                await db.exec(
                    select(InsightVisibilityRule).where(
                        InsightVisibilityRule.target_type == "intelligence",
                        InsightVisibilityRule.target_id == new_id,
                        InsightVisibilityRule.is_deleted == 0,
                    )
                )
            ).all()
        }
        moved = 0
        for row in rows:
            key = (row.principal_type, row.principal_id, row.permission)
            if key in existing:
                row.is_deleted = 1
            else:
                row.target_id = new_id
                existing.add(key)
                moved += 1
            row.update_time = datetime.now()
        return moved

    async def _move_review_records(self, db: Any, old_id: int, new_id: int) -> None:
        rows = list(
            (
                await db.exec(
                    select(InsightReviewRecord).where(
                        InsightReviewRecord.intelligence_id == old_id,
                        InsightReviewRecord.is_deleted == 0,
                    )
                )
            ).all()
        )
        for row in rows:
            row.intelligence_id = new_id
            row.update_time = datetime.now()

    async def _retire_asset(self, db: Any, intelligence_id: int) -> None:
        assets = list(
            (
                await db.exec(
                    select(InsightIntelligenceAsset).where(
                        InsightIntelligenceAsset.intelligence_id == intelligence_id,
                        InsightIntelligenceAsset.is_deleted == 0,
                    )
                )
            ).all()
        )
        for asset in assets:
            asset.is_deleted = 1
            asset.status = "merged"
            asset.update_time = datetime.now()
            for vector in (
                await db.exec(
                    select(InsightAssetVector).where(
                        InsightAssetVector.asset_id == asset.id,
                        InsightAssetVector.is_deleted == 0,
                    )
                )
            ).all():
                vector.is_deleted = 1
                vector.status = "merged"
                vector.update_time = datetime.now()
            for node in (
                await db.exec(
                    select(InsightGraphNode).where(
                        InsightGraphNode.source_asset_id == asset.id,
                        InsightGraphNode.is_deleted == 0,
                    )
                )
            ).all():
                node.is_deleted = 1
                node.status = "merged"
                node.update_time = datetime.now()
            for edge in (
                await db.exec(
                    select(InsightGraphEdge).where(
                        InsightGraphEdge.source_asset_id == asset.id,
                        InsightGraphEdge.is_deleted == 0,
                    )
                )
            ).all():
                edge.is_deleted = 1
                edge.status = "merged"
                edge.update_time = datetime.now()

    def _event_time(self, row: InsightIntelligence) -> datetime:
        return row.publish_time or row.create_time

    def _group_payload(self, group: DuplicateGroup) -> dict[str, Any]:
        return {
            "canonical_id": group.canonical.id,
            "title": group.canonical.title,
            "normalized_title": group.normalized_title,
            "duplicate_ids": [row.id for row in group.duplicates],
            "publish_times": [self._event_time(row).isoformat() for row in [group.canonical, *group.duplicates]],
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="归并 Insight 历史同事件重复情报")
    parser.add_argument("--apply", action="store_true", help="实际执行；不传时只输出预演报告")
    parser.add_argument("--days", type=int, default=365, help="扫描最近多少天，默认 365 天")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("logs/insight/event-merge-report.json"),
        help="JSON 报告输出路径",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    summary = await HistoricalEventMerger().run(apply=args.apply, days=max(args.days, 1), output=args.output)
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
