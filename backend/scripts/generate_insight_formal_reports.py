"""生成 Insight 下午汇报用正式报告。

该脚本只调用 Insight 现有报告生成服务，不手写报告正文。
生成前会按业务主题挑选正式情报，避免报告素材跑偏或混入测试数据。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import or_
from sqlmodel import select

from app.db.session import async_session, engine
from app.models.agent.insight import InsightIntelligence, InsightReport
from app.schemas.agent.insight.report import InsightReportGenerateRequest
from app.services.agent.insight.report_service import insight_report_service


TEST_TERMS = ("测试", "烟测", "smoke", "test", "demo", "样例", "样本", "测试客户")
LOW_QUALITY_SOURCE_TERMS = ("淘宝百科", "淘宝", "1688.com", "阿里巴巴", "批发/厂家")
VISIBLE_BANNED_TERMS = ("演示报告", "测试报告", "样例报告", "烟测", "素材ID", "证据ID", "RAG", "向量", "知识图谱")


@dataclass(frozen=True)
class FormalReportCase:
    key: str
    title: str
    report_type: str
    template_code: str
    days: int
    max_materials: int
    keywords: tuple[str, ...]
    prompt: str


REPORT_CASES: tuple[FormalReportCase, ...] = (
    FormalReportCase(
        key="milk_tea_daily",
        title="奶茶客户近期经营变化日报",
        report_type="日报",
        template_code="customer_new_product_opportunity",
        days=7,
        max_materials=60,
        keywords=("奶茶", "茶饮", "咖啡", "蜜雪", "茶百道", "古茗", "沪上阿姨", "奈雪", "喜茶", "幸运咖", "库迪", "瑞幸", "低糖", "功能配料"),
        prompt=(
            "请重点分析近期奶茶、茶饮与咖啡客户值得销售、市场和研发关注的变化。"
            "围绕新品、门店扩张、价格带、联名营销、现制咖啡、低糖和功能配料需求、食品安全或经营风险，"
            "说明对香驰控股果葡糖浆、麦芽糖、功能糖、植物蛋白等产品方案的机会、风险和后续建议。"
            "正文要面向正式业务汇报，不写演示、测试、样例或技术实现词。"
        ),
    ),
    FormalReportCase(
        key="milk_tea_weekly",
        title="奶茶与咖啡客户市场洞察周报",
        report_type="周报",
        template_code="weekly_report",
        days=15,
        max_materials=90,
        keywords=("奶茶", "茶饮", "咖啡", "蜜雪", "茶百道", "古茗", "沪上阿姨", "奈雪", "喜茶", "幸运咖", "库迪", "瑞幸", "低糖", "糖浆", "植脂末"),
        prompt=(
            "生成一份正式周报，聚焦奶茶、茶饮和咖啡客户近期经营动态。"
            "需要提炼本周高价值变化、销售可跟进客户、市场需要观察的竞争和消费趋势、研发可以验证的配料方向。"
            "请区分已确认事实、弱信号和需要继续跟踪的事项，结论要具体，避免空话。"
        ),
    ),
    FormalReportCase(
        key="protein_weekly",
        title="蛋白客户与植物基原料机会周报",
        report_type="周报",
        template_code="rd_topic_trend_report",
        days=15,
        max_materials=90,
        keywords=("蛋白", "大豆", "豆粕", "植物蛋白", "蛋白粉", "新蛋白", "乳清", "蒙牛", "佳禾", "索宝", "罗盖特", "Roquette", "Jungbunzlauer"),
        prompt=(
            "请分析近期蛋白客户、植物基原料、豆粕和蛋白粉相关变化。"
            "重点说明哪些信息值得销售跟进，哪些变化提示市场需求或竞对动作，哪些方向可转化为研发验证课题。"
            "结合香驰控股大豆加工、豆粕、植物蛋白和粮油业务背景，输出机会、风险和后续建议。"
        ),
    ),
    FormalReportCase(
        key="sweetener_quarter",
        title="功能糖与蛋白原料客户机会季度研判",
        report_type="季报",
        template_code="deep_research_report",
        days=90,
        max_materials=80,
        keywords=("果葡糖浆", "麦芽糖", "功能糖", "低糖", "代糖", "甜味剂", "糖醇", "赤藓糖醇", "木糖醇", "植物蛋白", "蛋白粉", "大豆加工", "玉米加工", "豆粕", "粮油"),
        prompt=(
            "生成一份正式季度研判，时间口径限定为2026年二季度至2026年6月底，不要写成2025年或跨年度回顾。"
            "围绕功能糖、低糖配料、植物蛋白、大豆和玉米加工相关客户机会。"
            "请从销售、市场和研发三个视角分析机会、风险、客户切入点、需要验证的假设和下一步行动。"
            "报告对象是香驰控股内部经营决策和业务跟进，不要写成媒体综述或演示稿。"
        ),
    ),
)


async def run(args: argparse.Namespace) -> None:
    engine.echo = False
    generated: list[dict[str, Any]] = []
    async with async_session() as db:
        selected_cases = [case for case in REPORT_CASES if not args.case or case.key == args.case]
        for case in selected_cases[: args.max_reports]:
            since = datetime.now() - timedelta(days=case.days)
            intelligence_ids = await select_relevant_intelligence_ids(db, case, since=since)
            if len(intelligence_ids) < args.min_materials:
                generated.append(
                    {
                        "key": case.key,
                        "status": "skipped",
                        "reason": f"正式素材不足：{len(intelligence_ids)}",
                    }
                )
                continue
            response = await insight_report_service.generate_report(
                db,
                InsightReportGenerateRequest(
                    title=case.title,
                    report_type=case.report_type,
                    template_code=case.template_code,
                    intelligence_ids=intelligence_ids,
                    max_materials=min(case.max_materials, len(intelligence_ids)),
                    period_start=since,
                    period_end=datetime.now(),
                    generation_prompt=case.prompt,
                ),
                user_id=args.user_id,
                is_admin=True,
            )
            report = (await db.exec(select(InsightReport).where(InsightReport.id == response.report.id))).first()
            if report:
                report.status = "final"
                report.visibility_scope = "public"
                report.owner_user_id = None
                report.update_by = str(args.user_id)
                await db.commit()
                await db.refresh(report)
            qa = visible_text_qa(report.content_json if report else response.report.content_json)
            generated.append(
                {
                    "key": case.key,
                    "status": "generated",
                    "report_id": response.report.id,
                    "title": response.report.title,
                    "report_type": case.report_type,
                    "materials": response.used_material_count,
                    "generation_mode": response.generation_mode,
                    "visible_banned_terms": qa["banned_terms"],
                    "summary_preview": normalize_space((report.summary if report else response.report.summary) or "")[:180],
                }
            )
    print(json.dumps({"generated": generated}, ensure_ascii=False, indent=2), flush=True)


async def select_relevant_intelligence_ids(db, case: FormalReportCase, *, since: datetime) -> list[int]:
    keyword_filter = or_(
        *[
            or_(
                InsightIntelligence.title.ilike(f"%{keyword}%"),
                InsightIntelligence.summary.ilike(f"%{keyword}%"),
                InsightIntelligence.content.ilike(f"%{keyword}%"),
                InsightIntelligence.subject_name.ilike(f"%{keyword}%"),
                InsightIntelligence.business_domain.ilike(f"%{keyword}%"),
            )
            for keyword in case.keywords
        ]
    )
    test_filter = ~or_(
        *[
            or_(
                InsightIntelligence.title.ilike(f"%{term}%"),
                InsightIntelligence.summary.ilike(f"%{term}%"),
                InsightIntelligence.subject_name.ilike(f"%{term}%"),
            )
            for term in TEST_TERMS
        ]
    )
    quality_filter = ~or_(
        *[
            or_(
                InsightIntelligence.title.ilike(f"%{term}%"),
                InsightIntelligence.summary.ilike(f"%{term}%"),
                InsightIntelligence.content.ilike(f"%{term}%"),
            )
            for term in LOW_QUALITY_SOURCE_TERMS
        ]
    )
    rows = list(
        (
            await db.exec(
                select(InsightIntelligence)
                .where(
                    InsightIntelligence.is_deleted == 0,
                    InsightIntelligence.status == "active",
                    test_filter,
                    quality_filter,
                    keyword_filter,
                    or_(InsightIntelligence.publish_time >= since, InsightIntelligence.create_time >= since),
                )
                .order_by(
                    InsightIntelligence.importance_level.desc(),
                    InsightIntelligence.publish_time.desc().nullslast(),
                    InsightIntelligence.create_time.desc(),
                )
                .limit(max(case.max_materials * 4, 160))
            )
        ).all()
    )
    scored = sorted(rows, key=lambda row: intelligence_score(row, case.keywords), reverse=True)
    return [int(row.id) for row in scored[: case.max_materials] if row.id]


def intelligence_score(row: InsightIntelligence, keywords: tuple[str, ...]) -> tuple[int, int, float, datetime]:
    text = normalize_space(" ".join([row.title or "", row.summary or "", row.content or "", row.subject_name or "", row.business_domain or ""]))
    keyword_hits = sum(1 for keyword in keywords if keyword.lower() in text.lower())
    title_hits = sum(1 for keyword in keywords if keyword.lower() in (row.title or "").lower())
    importance = {"high": 3, "medium": 2, "low": 1}.get((row.importance_level or "").lower(), 0)
    publish_time = row.publish_time or row.create_time or datetime.min
    return keyword_hits, title_hits, float(importance), publish_time


def visible_text_qa(content_json: dict[str, Any]) -> dict[str, Any]:
    text_parts: list[str] = []
    text_parts.append(str(content_json.get("title") or ""))
    text_parts.append(str(content_json.get("executive_summary") or content_json.get("summary") or ""))
    for chapter in content_json.get("chapters") or []:
        if isinstance(chapter, dict):
            text_parts.append(str(chapter.get("heading") or ""))
            for paragraph in chapter.get("paragraphs") or []:
                text_parts.append(str(paragraph))
    text_parts.append(str(content_json.get("conclusion") or ""))
    visible_text = "\n".join(text_parts)
    return {"banned_terms": [term for term in VISIBLE_BANNED_TERMS if term in visible_text]}


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--user-id", type=int, default=720)
    parser.add_argument("--max-reports", type=int, default=len(REPORT_CASES))
    parser.add_argument("--min-materials", type=int, default=12)
    parser.add_argument("--case", choices=[case.key for case in REPORT_CASES])
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(run(parse_args()))
