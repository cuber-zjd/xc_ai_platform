import asyncio
from pathlib import Path
from typing import Any

from sqlalchemy import text

from app.db.session import async_session, engine
from app.schemas.agent.insight.intelligence import InsightAssistantChatRequest, InsightDeepResearchRequest
from app.services.agent.insight.assistant_service import insight_assistant_service
from app.services.agent.insight.company_service import insight_company_service
from app.services.agent.insight.intelligence_service import insight_intelligence_service
from app.services.agent.insight.report_service import insight_report_service


engine.echo = False


PROJECT_ROOT = Path(__file__).resolve().parents[2]
INSIGHT_ROUTER = PROJECT_ROOT / "backend" / "app" / "api" / "v1" / "endpoints" / "agent" / "insight" / "router.py"
INSIGHT_ASSISTANT_PAGE = PROJECT_ROOT / "frontend" / "src" / "app" / "insight" / "pages" / "InsightAssistantPage.tsx"
INSIGHT_FRONTEND_CLIENT = PROJECT_ROOT / "frontend" / "src" / "app" / "insight" / "api" / "client.ts"
INSIGHT_FRONTEND_ROOT = PROJECT_ROOT / "frontend" / "src" / "app" / "insight"
UNSUPPORTED_CHANNELS_DOC = PROJECT_ROOT / "docs" / "solution-plans" / "市场洞察" / "暂未实现渠道清单.md"

STATIC_DEMO_PATTERNS = [
    "2025年5月21日",
    "关注植物基蛋白在乳制品",
    "跟踪头部茶饮品牌",
    "留意企业在精准营养",
    "示例客户有限公司",
    "示例竞对科技有限公司",
    "DataTableCard",
    "MiniLineChart",
    "DonutChart",
]

JIANYUAN_USER_ID = 40
YUXIN_USER_ID = 720
ADMIN_USER_ID = 5337
JIANYUAN_SYS_COMPANY_ID = 6
YUXIN_SYS_COMPANY_ID = 22
JIANYUAN_REPORT_ID = 25
YUXIN_REPORT_ID = 26


async def rows(sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    async with async_session() as db:
        result = await db.exec(text(sql), params=params or {})
        return [dict(row._mapping) for row in result.fetchall()]


def pass_fail(name: str, ok: bool, value: Any) -> tuple[str, bool, Any]:
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {name}: {value}")
    return name, ok, value


def scan_static_demo_frontend() -> list[dict[str, Any]]:
    if not INSIGHT_FRONTEND_ROOT.exists():
        return [{"file": str(INSIGHT_FRONTEND_ROOT), "pattern": "目录不存在", "line": 0}]

    findings: list[dict[str, Any]] = []
    for file_path in INSIGHT_FRONTEND_ROOT.rglob("*"):
        if file_path.suffix not in {".ts", ".tsx"}:
            continue
        try:
            text_content = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            findings.append({"file": str(file_path), "pattern": "无法按 UTF-8 读取", "line": 0})
            continue
        for line_no, line in enumerate(text_content.splitlines(), start=1):
            for pattern in STATIC_DEMO_PATTERNS:
                if pattern in line:
                    findings.append({
                        "file": str(file_path.relative_to(PROJECT_ROOT)),
                        "line": line_no,
                        "pattern": pattern,
                    })
    return findings


async def check_real_company_isolation() -> dict[str, Any]:
    async with async_session() as db:
        jianyuan_companies = await insight_company_service.list_companies(
            db,
            page=1,
            size=200,
            keyword=None,
            sys_company_id=None,
            industry=None,
            monitor_level=None,
            status=None,
            user_id=JIANYUAN_USER_ID,
            is_admin=False,
        )
        yuxin_companies = await insight_company_service.list_companies(
            db,
            page=1,
            size=200,
            keyword=None,
            sys_company_id=None,
            industry=None,
            monitor_level=None,
            status=None,
            user_id=YUXIN_USER_ID,
            is_admin=False,
        )
        admin_companies = await insight_company_service.list_companies(
            db,
            page=1,
            size=300,
            keyword=None,
            sys_company_id=None,
            industry=None,
            monitor_level=None,
            status=None,
            user_id=ADMIN_USER_ID,
            is_admin=True,
        )

        jianyuan_reports = await insight_report_service.list_reports(
            db,
            page=1,
            size=100,
            keyword=None,
            report_type=None,
            status=None,
            user_id=JIANYUAN_USER_ID,
            is_admin=False,
        )
        yuxin_reports = await insight_report_service.list_reports(
            db,
            page=1,
            size=100,
            keyword=None,
            report_type=None,
            status=None,
            user_id=YUXIN_USER_ID,
            is_admin=False,
        )
        admin_reports = await insight_report_service.list_reports(
            db,
            page=1,
            size=100,
            keyword=None,
            report_type=None,
            status=None,
            user_id=ADMIN_USER_ID,
            is_admin=True,
        )

        jianyuan_other_intelligence = await insight_intelligence_service.list_intelligences(
            db,
            page=1,
            size=20,
            keyword=None,
            subject_type=None,
            intelligence_type=None,
            visibility_scope=None,
            sys_company_id=YUXIN_SYS_COMPANY_ID,
            user_id=JIANYUAN_USER_ID,
            is_admin=False,
        )
        yuxin_other_intelligence = await insight_intelligence_service.list_intelligences(
            db,
            page=1,
            size=20,
            keyword=None,
            subject_type=None,
            intelligence_type=None,
            visibility_scope=None,
            sys_company_id=JIANYUAN_SYS_COMPANY_ID,
            user_id=YUXIN_USER_ID,
            is_admin=False,
        )
        admin_jianyuan_intelligence = await insight_intelligence_service.list_intelligences(
            db,
            page=1,
            size=20,
            keyword=None,
            subject_type=None,
            intelligence_type=None,
            visibility_scope=None,
            sys_company_id=JIANYUAN_SYS_COMPANY_ID,
            user_id=ADMIN_USER_ID,
            is_admin=True,
        )
        admin_yuxin_intelligence = await insight_intelligence_service.list_intelligences(
            db,
            page=1,
            size=20,
            keyword=None,
            subject_type=None,
            intelligence_type=None,
            visibility_scope=None,
            sys_company_id=YUXIN_SYS_COMPANY_ID,
            user_id=ADMIN_USER_ID,
            is_admin=True,
        )
        try:
            jianyuan_own_report = await insight_report_service.get_report_detail(
                db,
                JIANYUAN_REPORT_ID,
                user_id=JIANYUAN_USER_ID,
                is_admin=False,
            )
        except Exception:
            jianyuan_own_report = None
        try:
            yuxin_own_report = await insight_report_service.get_report_detail(
                db,
                YUXIN_REPORT_ID,
                user_id=YUXIN_USER_ID,
                is_admin=False,
            )
        except Exception:
            yuxin_own_report = None
        try:
            await insight_report_service.get_report_detail(
                db,
                YUXIN_REPORT_ID,
                user_id=JIANYUAN_USER_ID,
                is_admin=False,
            )
            jianyuan_other_report_detail_blocked = False
        except Exception:
            jianyuan_other_report_detail_blocked = True
        try:
            await insight_report_service.get_report_detail(
                db,
                JIANYUAN_REPORT_ID,
                user_id=YUXIN_USER_ID,
                is_admin=False,
            )
            yuxin_other_report_detail_blocked = False
        except Exception:
            yuxin_other_report_detail_blocked = True

    jianyuan_report_ids = {item.id for item in jianyuan_reports.items}
    yuxin_report_ids = {item.id for item in yuxin_reports.items}
    admin_report_ids = {item.id for item in admin_reports.items}
    return {
        "jianyuan_company_total": jianyuan_companies.total,
        "jianyuan_company_ids": sorted({item.sys_company_id for item in jianyuan_companies.items}),
        "yuxin_company_total": yuxin_companies.total,
        "yuxin_company_ids": sorted({item.sys_company_id for item in yuxin_companies.items}),
        "admin_company_total": admin_companies.total,
        "jianyuan_can_see_yuxin_intelligence": jianyuan_other_intelligence.total,
        "yuxin_can_see_jianyuan_intelligence": yuxin_other_intelligence.total,
        "admin_jianyuan_intelligence": admin_jianyuan_intelligence.total,
        "admin_yuxin_intelligence": admin_yuxin_intelligence.total,
        "jianyuan_report_has_own": JIANYUAN_REPORT_ID in jianyuan_report_ids,
        "jianyuan_report_has_other": YUXIN_REPORT_ID in jianyuan_report_ids,
        "yuxin_report_has_own": YUXIN_REPORT_ID in yuxin_report_ids,
        "yuxin_report_has_other": JIANYUAN_REPORT_ID in yuxin_report_ids,
        "admin_report_has_both": {JIANYUAN_REPORT_ID, YUXIN_REPORT_ID}.issubset(admin_report_ids),
        "jianyuan_own_report_materials": len(jianyuan_own_report.materials) if jianyuan_own_report else 0,
        "yuxin_own_report_materials": len(yuxin_own_report.materials) if yuxin_own_report else 0,
        "jianyuan_other_report_detail_blocked": jianyuan_other_report_detail_blocked,
        "yuxin_other_report_detail_blocked": yuxin_other_report_detail_blocked,
    }


async def check_ai_assistant_runtime() -> dict[str, Any]:
    async with async_session() as db:
        chat = await insight_assistant_service.chat(
            db,
            InsightAssistantChatRequest(
                question="低糖和功能糖相关机会有哪些？请引用库内情报。",
                keyword="低糖 功能糖",
                sys_company_id=JIANYUAN_SYS_COMPANY_ID,
                limit=6,
            ),
            user_id=ADMIN_USER_ID,
            is_admin=True,
        )
        research = await insight_assistant_service.deep_research(
            db,
            InsightDeepResearchRequest(
                question="低糖饮料和功能糖方向是否值得继续跟踪？",
                keyword="低糖 功能糖 饮料",
                sys_company_id=JIANYUAN_SYS_COMPANY_ID,
                limit=8,
            ),
            user_id=ADMIN_USER_ID,
            is_admin=True,
        )
        cross_company_chat = await insight_assistant_service.chat(
            db,
            InsightAssistantChatRequest(
                question="健源相关低糖和功能糖情报有哪些？",
                keyword="低糖 功能糖",
                sys_company_id=JIANYUAN_SYS_COMPANY_ID,
                limit=6,
            ),
            user_id=YUXIN_USER_ID,
            is_admin=False,
        )
    chat_citations = [item.model_dump(mode="json") for item in chat.citations]
    research_citations = [item.model_dump(mode="json") for item in research.citations]
    return {
        "chat_evidence_count": chat.evidence_count,
        "chat_generation_mode": chat.generation_mode,
        "chat_has_citation_url": any(item.get("source_url") for item in chat_citations),
        "chat_has_citation_title": any(item.get("title") for item in chat_citations),
        "research_evidence_matrix": len(research.evidence_matrix),
        "research_citation_count": len(research.citations),
        "research_generation_mode": research.generation_mode,
        "research_has_source_url": any(item.get("source_url") for item in research_citations),
        "cross_company_no_evidence": cross_company_chat.no_evidence and cross_company_chat.evidence_count == 0,
    }


async def main() -> None:
    checks: list[tuple[str, bool, Any]] = []

    source_summary = await rows(
        """
        select count(*) filter (where status <> 'deleted') total,
               count(*) filter (where status = 'enabled') enabled,
               count(*) filter (where status <> 'deleted' and schedule_enabled = true) scheduled
        from insight_data_source
        """
    )
    source_types = await rows(
        """
        select source_type, count(*) total
        from insight_data_source
        where status <> 'deleted'
        group by source_type
        """
    )
    source_type_map = {item["source_type"]: item["total"] for item in source_types}
    required_source_types = {
        "wechat_public_account",
        "ecommerce_search",
        "government_policy",
        "finance_news",
        "patent_search",
        "industry_media",
    }
    source_row = source_summary[0]
    checks.append(pass_fail("数据源总量达到期初运行规模", source_row["total"] >= 800, source_row))
    checks.append(pass_fail("周期数据源已启用", source_row["scheduled"] >= 700, source_row["scheduled"]))
    checks.append(pass_fail("新增渠道类型已覆盖", required_source_types.issubset(source_type_map), source_type_map))

    active_intelligence = await rows(
        """
        select count(*) total,
               count(*) filter (where summary is not null and length(trim(summary)) > 0) with_summary,
               count(*) filter (where sentiment in ('positive', 'neutral', 'negative', 'mixed')) with_sentiment,
               count(*) filter (where raw_payload ? 'suggested_tags' or raw_payload->'ai_analysis' ? 'tags') with_tags,
               count(*) filter (
                   where exists (
                       select 1
                       from insight_intelligence_source src
                       where src.intelligence_id = insight_intelligence.id
                         and src.source_url is not null
                         and length(src.source_url) > 0
                   )
               ) with_source_url,
               count(*) filter (where jsonb_array_length(coalesce(raw_payload->'ai_analysis'->'opportunities', '[]'::jsonb)) > 0) with_opportunities,
               count(*) filter (where jsonb_array_length(coalesce(raw_payload->'ai_analysis'->'risks', '[]'::jsonb)) > 0) with_risks
        from insight_intelligence
        where status = 'active' and review_status = 'approved'
        """
    )
    intelligence_row = active_intelligence[0]
    total_intelligence = intelligence_row["total"]
    checks.append(pass_fail("正式情报不少于 2000 条", total_intelligence >= 2000, total_intelligence))
    checks.append(pass_fail("正式情报摘要全覆盖", intelligence_row["with_summary"] == total_intelligence, intelligence_row))
    checks.append(pass_fail("正式情报情感全覆盖", intelligence_row["with_sentiment"] == total_intelligence, intelligence_row))
    checks.append(pass_fail("正式情报标签全覆盖", intelligence_row["with_tags"] == total_intelligence, intelligence_row))
    checks.append(pass_fail("正式情报来源 URL 全覆盖", intelligence_row["with_source_url"] == total_intelligence, intelligence_row))
    checks.append(pass_fail("机会点有足够覆盖", intelligence_row["with_opportunities"] >= int(total_intelligence * 0.5), intelligence_row["with_opportunities"]))
    checks.append(pass_fail("风险点有足够覆盖", intelligence_row["with_risks"] >= int(total_intelligence * 0.5), intelligence_row["with_risks"]))

    task_health = await rows(
        """
        with activity as (
            select greatest(
                coalesce(max(coalesce(started_at, create_time)), now() at time zone 'Asia/Shanghai'),
                now() at time zone 'Asia/Shanghai'
            ) as latest_at
            from insight_task
        )
        select count(*) filter (where status::text in ('RUNNING', 'PENDING')) running_or_pending,
               count(*) filter (
                   where status::text in ('RUNNING', 'PENDING')
                     and activity.latest_at is not null
                     and coalesce(started_at, create_time) < activity.latest_at - interval '30 minutes'
               ) stale_tasks
        from insight_task, activity
        """
    )
    checks.append(pass_fail("无运行中或等待任务堆积", task_health[0]["running_or_pending"] <= 5, task_health[0]))
    checks.append(pass_fail("无 30 分钟以上遗留任务", task_health[0]["stale_tasks"] == 0, task_health[0]))

    empty_result_failures = await rows(
        """
        select count(*) as failed_empty_result_tasks
        from insight_task
        where status::text = 'FAILED'
          and (
              error_message ilike '%结果已被筛选规则全部过滤%'
              or error_message ilike '%没有命中可进入候选池%'
          )
        """
    )
    checks.append(pass_fail("搜索空结果不计为失败任务", empty_result_failures[0]["failed_empty_result_tasks"] == 0, empty_result_failures[0]))

    templates = await rows(
        """
        select template_code, template_name, report_type, export_formats
        from insight_report_template
        where status = 'active' and scope = 'market'
        """
    )
    required_templates = {
        "market_weekly_brief_v1",
        "competitor_watch_v1",
        "customer_new_product_v1",
        "rd_topic_trend_v1",
        "policy_regulation_brief_v1",
        "ecommerce_new_product_monitor_v1",
        "deep_research_v1",
    }
    template_codes = {item["template_code"] for item in templates}
    export_ready = all({"html", "pdf", "docx"}.issubset(set(item["export_formats"] or [])) for item in templates if item["template_code"] in required_templates)
    checks.append(pass_fail("七类市场报告模板已上架", required_templates.issubset(template_codes), sorted(template_codes)))
    checks.append(pass_fail("市场模板真实导出格式已声明", export_ready, templates))

    report_distribution = await rows(
        """
        select report_type, count(*) total
        from insight_report
        group by report_type
        """
    )
    report_type_count = sum(1 for item in report_distribution if item["total"] >= 2)
    report_total = sum(item["total"] for item in report_distribution)
    checks.append(pass_fail("多类型报告已生成", report_type_count >= 7 and report_total >= 14, report_distribution))

    report_material_health = await rows(
        """
        with active_counts as (
            select report_id, count(*) active_materials
            from insight_report_material
            where is_deleted = 0
            group by report_id
        )
        select
            (select count(*)
             from insight_report_material m
             left join insight_intelligence i on i.id = m.intelligence_id
             where m.is_deleted = 0
               and (i.id is null or i.status <> 'active' or i.review_status <> 'approved')) as bad_active_materials,
            (select count(*)
             from insight_report r
             left join active_counts a on a.report_id = r.id
             where r.material_count <> coalesce(a.active_materials, 0)) as material_count_mismatch_reports,
            (select count(*)
             from insight_report_material
             where is_deleted = 0) as active_report_materials
        """
    )
    material_row = report_material_health[0]
    checks.append(pass_fail("报告素材池不少于 1500 条", material_row["active_report_materials"] >= 1500, material_row))
    checks.append(pass_fail("报告有效素材不引用降级情报", material_row["bad_active_materials"] == 0, material_row))
    checks.append(pass_fail("报告素材计数一致", material_row["material_count_mismatch_reports"] == 0, material_row))

    report_content_health = await rows(
        """
        with blocked_texts as (
            select id, title, summary
            from insight_intelligence
            where status <> 'active'
               or review_status <> 'approved'
               or is_deleted <> 0
        )
        select count(distinct r.id) as reports_with_blocked_text
        from insight_report r
        join blocked_texts b on (
            (b.title is not null and length(trim(b.title)) >= 24 and r.content_json::text ilike '%' || b.title || '%')
            or (b.summary is not null and length(trim(b.summary)) >= 32 and r.content_json::text ilike '%' || left(b.summary, 180) || '%')
        )
        """
    )
    checks.append(pass_fail("报告正文不残留已降级情报文本", report_content_health[0]["reports_with_blocked_text"] == 0, report_content_health[0]))

    isolation = await check_real_company_isolation()
    isolation_ok = (
        isolation["jianyuan_company_total"] == 97
        and isolation["jianyuan_company_ids"] == [JIANYUAN_SYS_COMPANY_ID]
        and isolation["yuxin_company_total"] == 43
        and isolation["yuxin_company_ids"] == [YUXIN_SYS_COMPANY_ID]
        and isolation["admin_company_total"] >= 140
        and isolation["jianyuan_can_see_yuxin_intelligence"] == 0
        and isolation["yuxin_can_see_jianyuan_intelligence"] == 0
        and isolation["admin_jianyuan_intelligence"] > 0
        and isolation["admin_yuxin_intelligence"] > 0
        and isolation["jianyuan_report_has_own"]
        and not isolation["jianyuan_report_has_other"]
        and isolation["yuxin_report_has_own"]
        and not isolation["yuxin_report_has_other"]
        and isolation["admin_report_has_both"]
        and isolation["jianyuan_own_report_materials"] > 0
        and isolation["yuxin_own_report_materials"] > 0
        and isolation["jianyuan_other_report_detail_blocked"]
        and isolation["yuxin_other_report_detail_blocked"]
    )
    checks.append(pass_fail("健源/御馨真实账号权限隔离", isolation_ok, isolation))

    router_text = INSIGHT_ROUTER.read_text(encoding="utf-8") if INSIGHT_ROUTER.exists() else ""
    frontend_client_text = INSIGHT_FRONTEND_CLIENT.read_text(encoding="utf-8") if INSIGHT_FRONTEND_CLIENT.exists() else ""
    assistant_page_text = INSIGHT_ASSISTANT_PAGE.read_text(encoding="utf-8") if INSIGHT_ASSISTANT_PAGE.exists() else ""
    required_public_endpoints = [
        "/data-sources/import",
        "/data-sources/import-template",
        "/data-sources/bulk-action",
        "/intelligence/bulk-action",
        "/assistant/chat",
        "/research/deep",
        "/bootstrap/seed-from-requirements",
    ]
    endpoint_contract = {
        "missing_backend_routes": [endpoint for endpoint in required_public_endpoints if f'"{endpoint}"' not in router_text],
        "missing_frontend_client_routes": [
            endpoint
            for endpoint in required_public_endpoints
            if endpoint != "/bootstrap/seed-from-requirements" and endpoint not in frontend_client_text
        ],
    }
    checks.append(pass_fail(
        "计划公开接口已接通",
        not endpoint_contract["missing_backend_routes"] and not endpoint_contract["missing_frontend_client_routes"],
        endpoint_contract,
    ))

    assistant_contract = (
        '"/assistant/chat"' in router_text
        and '"/research/deep"' in router_text
        and "useInsightAssistantChat" in assistant_page_text
        and "useInsightDeepResearch" in assistant_page_text
        and "CitationList" in assistant_page_text
    )
    checks.append(pass_fail("AI 助手与深度研究入口已接通", assistant_contract, {"router": str(INSIGHT_ROUTER), "page": str(INSIGHT_ASSISTANT_PAGE)}))

    assistant_runtime = await check_ai_assistant_runtime()
    assistant_runtime_ok = (
        assistant_runtime["chat_evidence_count"] > 0
        and assistant_runtime["chat_has_citation_url"]
        and assistant_runtime["chat_has_citation_title"]
        and assistant_runtime["research_evidence_matrix"] > 0
        and assistant_runtime["research_citation_count"] > 0
        and assistant_runtime["research_has_source_url"]
        and assistant_runtime["cross_company_no_evidence"]
    )
    checks.append(pass_fail("AI 助手与深度研究真实检索可用", assistant_runtime_ok, assistant_runtime))

    unsupported_doc_ok = UNSUPPORTED_CHANNELS_DOC.exists() and all(
        text in UNSUPPORTED_CHANNELS_DOC.read_text(encoding="utf-8")
        for text in ["电商登录/强风控页面", "微信公众号历史文章全量抓取", "专利库高级检索", "付费财经/研报"]
    )
    checks.append(pass_fail("暂未实现渠道清单已沉淀", unsupported_doc_ok, str(UNSUPPORTED_CHANNELS_DOC)))

    static_demo_findings = scan_static_demo_frontend()
    checks.append(pass_fail("Insight 前端无静态演示数据残留", not static_demo_findings, static_demo_findings))

    failed = [name for name, ok, _ in checks if not ok]
    print("=" * 36)
    print(f"Insight 完整可用化验收：{len(checks) - len(failed)}/{len(checks)} 通过")
    if failed:
        raise SystemExit(f"Insight 完整可用化验收未通过: {'; '.join(failed)}")


if __name__ == "__main__":
    asyncio.run(main())
