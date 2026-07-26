from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime

from app.db.session import async_session
from app.schemas.agent.insight.feishu_brief import InsightFeishuBriefRunRequest
from app.services.agent.insight.feishu_brief_service import insight_feishu_brief_service


def _parse_datetime(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("时间必须使用 ISO 格式，例如 2026-07-01T00:00:00") from exc


async def _run(args: argparse.Namespace) -> None:
    request = InsightFeishuBriefRunRequest(
        period_start=args.period_start,
        period_end=args.period_end,
        publish_candidate_documents=not args.skip_candidates,
        push_final=not args.skip_push,
    )
    async with async_session() as db:
        result = await insight_feishu_brief_service.run_plan(
            db,
            args.plan_id,
            trigger_type="manual_experiment",
            run_request=request,
        )
        print(
            json.dumps(
                result.model_dump(mode="json"),
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="执行飞书简报计划，可显式指定素材周期并保留月报候选方案")
    parser.add_argument("--plan-id", type=int, required=True)
    parser.add_argument("--period-start", type=_parse_datetime, required=True)
    parser.add_argument("--period-end", type=_parse_datetime, required=True)
    parser.add_argument("--skip-candidates", action="store_true", help="不创建候选稿和审校记录云文档")
    parser.add_argument("--skip-push", action="store_true", help="只生成文档，不推送最终稿")
    args = parser.parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
