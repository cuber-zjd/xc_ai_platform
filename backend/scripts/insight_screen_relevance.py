"""复筛 Insight 正式情报的业务相关性。

用于期初真实运行后的质量纠偏：
- 只处理已入库的真实来源情报；
- 调用平台 AI 判断是否适合研发营销市场洞察；
- 不相关内容标记为 inactive + needs_review，避免进入正式情报列表和报告素材；
- 所有判断写回 raw_payload.relevance_screen，便于后续复核。
"""

import argparse
import asyncio
import json
import sys
import warnings
from datetime import datetime
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger
from sqlalchemy import text
from sqlmodel import select

from app.core.llm_factory import LLMFactory
from app.db.session import async_session, engine
from app.models.agent.insight import InsightIntelligence, InsightIntelligenceSource
from app.models.agent.insight.data_source import InsightDataSource
from app.models.system.sys_company import SysCompany  # noqa: F401


async def run(args: argparse.Namespace) -> None:
    if args.quiet_logs:
        warnings.filterwarnings("ignore")
        logger.remove()
        logger.add(sys.stderr, level="WARNING")
    engine.echo = False
    processed = 0
    kept = 0
    flagged = 0
    failed = 0
    async with async_session() as db:
        filters = [
            InsightIntelligence.is_deleted == 0,
            InsightIntelligence.status == "active",
            text("COALESCE(raw_payload->>'relevance_screen_status', '') = ''"),
        ]
        statement = select(InsightIntelligence)
        if args.search_excerpt_only:
            filters.append(text("raw_payload->>'deepening_mode' = 'search_excerpt'"))
        if args.include_source_types:
            statement = statement.join(InsightDataSource, InsightDataSource.id == InsightIntelligence.data_source_id)
            filters.append(InsightDataSource.source_type.in_(args.include_source_types))
        rows = list(
            (
                await db.exec(
                    statement
                    .where(*filters)
                    .order_by(InsightIntelligence.update_time.desc().nullslast(), InsightIntelligence.id.desc())
                    .limit(args.limit)
                )
            ).all()
        )
        print(f"待复筛情报：本批 {len(rows)} 条", flush=True)
        for intelligence in rows:
            processed += 1
            source = await _get_primary_source(db, intelligence.id or 0)
            try:
                result = _hard_quality_result(intelligence, source)
                if result is None:
                    result = await asyncio.wait_for(_screen_one(intelligence, source), timeout=args.per_item_timeout)
                _apply_screen_result(intelligence, result, args.threshold)
                await db.commit()
                if intelligence.status == "inactive":
                    flagged += 1
                    print(f"  降级 {intelligence.id}: {intelligence.title[:80]} | {result.get('reason')}", flush=True)
                else:
                    kept += 1
                    print(f"  保留 {intelligence.id}: {intelligence.title[:80]} | score={result.get('relevance_score')}", flush=True)
            except Exception as exc:
                await db.rollback()
                failed += 1
                print(f"  失败 {intelligence.id}: {exc}", flush=True)
        print({"processed": processed, "kept": kept, "flagged": flagged, "failed": failed}, flush=True)


async def _get_primary_source(db, intelligence_id: int) -> InsightIntelligenceSource | None:
    return (
        await db.exec(
            select(InsightIntelligenceSource)
            .where(
                InsightIntelligenceSource.intelligence_id == intelligence_id,
                InsightIntelligenceSource.is_deleted == 0,
            )
            .order_by(InsightIntelligenceSource.create_time.asc(), InsightIntelligenceSource.id.asc())
        )
    ).first()


async def _screen_one(intelligence: InsightIntelligence, source: InsightIntelligenceSource | None) -> dict[str, Any]:
    raw_payload = intelligence.raw_payload or {}
    ai_analysis = raw_payload.get("ai_analysis") if isinstance(raw_payload, dict) else {}
    payload = {
        "title": intelligence.title,
        "summary": intelligence.summary,
        "content_excerpt": (intelligence.content or "")[:1200],
        "source_title": source.source_title if source else None,
        "source_url": source.source_url if source else None,
        "source_excerpt": source.content_excerpt if source else None,
        "tags": ai_analysis.get("tags") if isinstance(ai_analysis, dict) else None,
        "opportunities": ai_analysis.get("opportunities") if isinstance(ai_analysis, dict) else None,
        "risks": ai_analysis.get("risks") if isinstance(ai_analysis, dict) else None,
    }
    response = await LLMFactory.safe_invoke(
        [
            SystemMessage(
                content=(
                    "你是研发营销市场洞察平台的数据质量审核助手。"
                    "请判断这条情报是否适合进入食品饮料、功能糖/淀粉糖、植物蛋白、配料原料、"
                    "客户/竞对动态、政策法规、专利技术、研发课题、营销渠道洞察范围。"
                    "如果只是同名误匹配、图书/地产/美妆/汽车/半导体/家居等无关行业，或只有无效占位内容，应判为 needs_review。"
                    "输出严格 JSON：decision 只能是 keep 或 needs_review；relevance_score 为 0 到 1；"
                    "reason 用中文一句话说明；business_tags 为中文数组，最多 5 个。"
                )
            ),
            HumanMessage(content=json.dumps(payload, ensure_ascii=False)),
        ],
        capability="general",
        temperature=0,
        json_mode=True,
        max_retries=2,
    )
    content = getattr(response, "content", response)
    if isinstance(content, list):
        content = "".join(str(item) for item in content)
    if not isinstance(content, str):
        raise ValueError("AI 未返回文本")
    result = json.loads(_strip_json_fence(content))
    if not isinstance(result, dict):
        raise ValueError("AI 未返回 JSON 对象")
    return result


def _hard_quality_result(intelligence: InsightIntelligence, source: InsightIntelligenceSource | None) -> dict[str, Any] | None:
    title = (intelligence.title or "").lower()
    summary = (intelligence.summary or "").lower()
    source_url = ((source.source_url if source else "") or "").lower()
    source_title = ((source.source_title if source else "") or "").lower()
    text = " ".join([title, summary, source_title, source_url])

    weak_domains = (
        "book118.com",
        "docin.com",
        "wenku.baidu.com",
        "wjx.cn",
        "wenjuan.com",
        "sojump.com",
    )
    weak_markers = (
        "原创力文档",
        "调研问卷",
        "加盟合作伙伴调研",
        "页面主要部分被登录墙遮挡",
        "登录墙",
        "需要登录",
    )
    file_title_markers = (
        ".docx",
        ".ppt",
        ".pptx",
        ".pdf",
        "年度总结",
    )
    if any(domain in source_url for domain in weak_domains):
        return _needs_review_result("来源为文档分享、问卷或公开访问质量较弱站点，不适合作为正式培训展示情报。")
    if any(marker.lower() in text for marker in weak_markers):
        return _needs_review_result("页面存在问卷、登录墙或低信息量摘要特征，需人工复核后再进入正式情报。")
    if any(marker in title for marker in file_title_markers) and any(marker in text for marker in ("文档", "报告", "总结")):
        return _needs_review_result("标题呈现为二次上传文件或资料站内容，缺少稳定公开新闻/公告属性。")
    return None


def _needs_review_result(reason: str) -> dict[str, Any]:
    return {
        "decision": "needs_review",
        "relevance_score": 0.1,
        "reason": reason,
        "business_tags": ["低质量来源", "待人工复核"],
    }


def _apply_screen_result(intelligence: InsightIntelligence, result: dict[str, Any], threshold: float) -> None:
    score = _float_value(result.get("relevance_score"), 0)
    decision = str(result.get("decision") or "").strip()
    reason = str(result.get("reason") or "").strip()[:500]
    business_tags = _string_items(result.get("business_tags"))[:5]
    raw = dict(intelligence.raw_payload or {})
    raw["relevance_screen"] = {
        "decision": decision,
        "relevance_score": score,
        "reason": reason,
        "business_tags": business_tags,
        "screened_at": datetime.now().isoformat(),
        "screened_by": "insight_screen_relevance",
    }
    raw["relevance_screen_status"] = "screened"
    if decision == "needs_review" or score < threshold:
        intelligence.status = "inactive"
        intelligence.review_status = "needs_review"
        raw["relevance_screen_status"] = "needs_review"
    else:
        intelligence.review_status = intelligence.review_status or "approved"
    intelligence.raw_payload = raw
    intelligence.update_time = datetime.now()


def _strip_json_fence(value: str) -> str:
    text_value = value.strip()
    if text_value.startswith("```"):
        text_value = text_value.strip("`")
        if text_value.startswith("json"):
            text_value = text_value[4:]
    return text_value.strip()


def _float_value(value: object, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _string_items(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip()[:80] for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [item.strip()[:80] for item in value.replace("；", ";").split(";") if item.strip()]
    return []


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--per-item-timeout", type=int, default=45)
    parser.add_argument("--threshold", type=float, default=0.45)
    parser.add_argument("--quiet-logs", action="store_true")
    parser.add_argument("--search-excerpt-only", action="store_true")
    parser.add_argument("--include-source-types", nargs="*", default=[])
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(run(parse_args()))
