from __future__ import annotations

import asyncio
import json
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.core.llm_factory import LLMFactory
from app.services.agent.insight.feishu_monthly_report_service import (
    MONTHLY_SECTIONS,
    InsightFeishuMonthlyReportService,
)
from app.services.agent.insight.company_context import insight_company_business_context
from app.models.agent.insight.feishu_brief import InsightFeishuBriefPlan
from app.schemas.agent.insight.feishu_brief import InsightFeishuBriefGenerationRules
from app.services.agent.insight.feishu_brief_service import InsightFeishuBriefService


class InsightFeishuBriefScheduleTest(unittest.TestCase):
    def setUp(self) -> None:
        self.service = InsightFeishuBriefService()

    def test_month_end_schedule_uses_actual_last_day(self) -> None:
        next_run = self.service._next_run_time(
            "monthly",
            "10:30",
            None,
            31,
            base=datetime(2027, 2, 1, 9, 0),
        )
        self.assertEqual(next_run, datetime(2027, 2, 28, 10, 30))

    def test_month_end_schedule_uses_current_month_materials(self) -> None:
        plan = InsightFeishuBriefPlan(
            plan_uid="test-month-end",
            plan_name="月末月报",
            schedule_frequency="monthly",
            day_of_month=31,
            time_of_day="10:30",
        )
        start, end = self.service._period_bounds(
            plan,
            now=datetime(2026, 8, 31, 10, 30),
            trigger_type="brief_scheduler",
            requested_start=None,
        )
        self.assertEqual(start, datetime(2026, 8, 1))
        self.assertEqual(end, datetime(2026, 8, 31, 10, 30))

    def test_week_title_uses_material_end_date_interval(self) -> None:
        self.assertEqual(self.service._week_of_month(datetime(2026, 8, 3, 23, 59)), 1)
        self.assertEqual(self.service._week_of_month(datetime(2026, 8, 8)), 2)

    def test_weekly_selection_keeps_supporting_evidence(self) -> None:
        materials = [
            {
                "id": index,
                "title": f"大豆蛋白客户产线动态 {index}",
                "summary": f"客户新增植物蛋白产线并披露产能数据 {index}",
                "source_url": f"https://example.com/{index}",
                "publish_time": datetime(2026, 8, 1),
                "category": "客户",
            }
            for index in range(1, 9)
        ]
        payload = {
            "selected": [
                {
                    "id": index,
                    "score": 82 if index <= 7 else 72,
                    "category": "客户",
                    "reason": "直接相关",
                }
                for index in range(1, 9)
            ],
            "rejected": [],
        }
        response = SimpleNamespace(content=json.dumps(payload, ensure_ascii=False))
        with patch.object(LLMFactory, "safe_invoke", AsyncMock(return_value=response)):
            selected, audit = asyncio.run(
                self.service._select_materials(
                    company_name="山东御馨生物科技股份有限公司",
                    period_start=datetime(2026, 7, 28),
                    period_end=datetime(2026, 8, 3, 23, 59, 59),
                    materials=materials,
                    generation_rules=InsightFeishuBriefGenerationRules(),
                )
            )
        self.assertEqual(len(selected), 8)
        self.assertEqual(selected[-1]["brief_role"], "supporting")
        self.assertEqual(audit["selected"][-1]["score"], 72)

    def test_company_default_rules_keep_business_boundaries_distinct(self) -> None:
        plan = InsightFeishuBriefPlan(plan_uid="rules", plan_name="规则测试")
        jianyuan = self.service._generation_rules(plan, "山东香驰健源生物科技有限公司")
        yuxin = self.service._generation_rules(plan, "山东御馨生物科技股份有限公司")
        self.assertIn("果葡糖浆", jianyuan.focus_topics)
        self.assertNotIn("大豆精深加工", jianyuan.focus_topics)
        self.assertIn("大豆蛋白", yuxin.focus_topics)
        self.assertNotIn("糖浆与功能糖", yuxin.focus_topics)

    def test_saved_generation_rules_override_company_defaults(self) -> None:
        plan = InsightFeishuBriefPlan(
            plan_uid="custom-rules",
            plan_name="自定义规则",
            generation_rules_json={
                "focus_topics": ["餐饮供应链"],
                "primary_score": 82,
                "supporting_score": 65,
                "minimum_citations": 10,
                "maximum_citations": 30,
            },
        )
        rules = self.service._generation_rules(plan, "山东香驰健源生物科技有限公司")
        self.assertEqual(rules.focus_topics, ["餐饮供应链"])
        self.assertEqual(rules.primary_score, 82)
        self.assertEqual(rules.supporting_score, 65)
        self.assertEqual(rules.minimum_citations, 10)

    def test_replace_document_preserves_document_and_rewrites_blocks(self) -> None:
        request = AsyncMock(
            side_effect=[
                {"items": [{"block_id": "old-1"}, {"block_id": "old-2"}]},
                {},
                {},
            ]
        )
        with patch.object(self.service, "_request", request):
            asyncio.run(self.service._replace_document_content("doc-1", "# 一、总览\n\n新内容"))
        self.assertEqual(request.await_count, 3)
        self.assertEqual(request.await_args_list[1].args[0], "DELETE")
        self.assertEqual(request.await_args_list[1].kwargs["json"], {"start_index": 0, "end_index": 2})
        self.assertIn("/doc-1/blocks/doc-1/children", request.await_args_list[2].args[1])

    def test_weekly_validation_blocks_unsupported_demand_and_advice(self) -> None:
        materials = [
            {"id": index, "source_url": f"https://example.com/{index}", "title": f"材料 {index}"}
            for index in range(1, 8)
        ]
        markdown = "\n".join(
            [
                "管理层情报简报｜2026年7月28日至8月3日｜生成时间：2026年8月4日",
                "适用公司：健源｜数据来源：情报管理多维表格·情报表｜原始候选 7 条",
                "# 一、总览",
                "# 政策",
                "该动作意味着未来新增采购需求，值得关注。",
                "# 竞对",
                "正文。",
                "# 客户",
                "正文。",
                "# 技术",
                "正文。",
                "# 原料",
                "正文。",
                "# 二、重点情报导读",
            ]
            + [
                f"## [{index}. 事件 {index}](https://example.com/{index})"
                for index in range(1, 8)
            ]
        )
        errors = self.service._validate_markdown(markdown, materials)
        self.assertIn("包含材料未充分支撑的确定性需求、业绩因果或机会判断，需改为客观事实或审慎表述", errors)
        self.assertIn("正文夹带行动建议，需删除“香驰需、我司应、需关注、需警惕”等建议性表达", errors)

    def test_weekly_validation_blocks_cross_business_competitor(self) -> None:
        materials = [
            {"id": index, "source_url": f"https://example.com/{index}", "title": f"材料 {index}"}
            for index in range(1, 8)
        ]
        markdown = "\n".join(
            [
                "管理层情报简报｜2026年7月28日至8月3日｜生成时间：2026年8月4日",
                "适用公司：御馨｜数据来源：情报管理多维表格·情报表｜原始候选 7 条",
                "# 一、总览",
                "# 政策",
                "正文。",
                "# 竞对",
                "西王专精玉米油细分领域。",
                "# 客户",
                "正文。",
                "# 技术",
                "正文。",
                "# 原料",
                "正文。",
                "# 二、重点情报导读",
            ]
            + [f"## [{index}. 事件 {index}](https://example.com/{index})" for index in range(1, 8)]
        )
        errors = self.service._validate_markdown(
            markdown,
            materials,
            company_name="山东御馨生物科技股份有限公司",
        )
        self.assertIn("御馨竞对章节混入植物油业务，必须删除并只保留蛋白主线", errors)

    def test_company_scope_normalizer_removes_only_cross_business_sentences(self) -> None:
        markdown = (
            "# 竞对\n\n"
            "[ADM扩建大豆压榨产能](https://example.com/adm)，新增约70万吨年产能。"
            "[西王专精玉米油](https://example.com/xw)，采用六重保鲜工艺。"
            "[长安花布局菜籽油](https://example.com/ca)，完善全产业链。\n\n"
            "# 客户\n\n客户正文。"
        )
        normalized = self.service._normalize_company_scope(
            markdown,
            "山东御馨生物科技股份有限公司",
        )
        self.assertIn("ADM扩建大豆压榨产能", normalized)
        self.assertNotIn("西王专精玉米油", normalized)
        self.assertNotIn("长安花布局菜籽油", normalized)
        self.assertIn("# 客户", normalized)


class InsightMonthlyReportServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.service = InsightFeishuMonthlyReportService()
        self.materials = [
            {
                "id": index,
                "source_url": f"https://example.com/{index}",
                "summary": f"正式情报 {index}",
            }
            for index in range(1, 13)
        ]

    def valid_markdown(self) -> str:
        body = [
            "管理层月度市场信息报告｜2026年7月1日至26日｜生成时间：2026年7月26日",
            "",
            "---",
            "",
            f"# {MONTHLY_SECTIONS[0]}",
            "",
            "本月核心主线发生变化，详见[总览依据](https://example.com/1)。",
            "",
            f"# {MONTHLY_SECTIONS[1]}",
        ]
        dimensions = ("政策", "竞对", "客户", "技术", "原料")
        for index, dimension in enumerate(dimensions, 2):
            body.extend(
                [
                    "",
                    f"## {index - 1}.{dimension}",
                    "",
                    f"**趋势判断（变化）**：本月{dimension}方向发生变化。",
                    "",
                    f"**核心佐证**：详见[{dimension}事项](https://example.com/{index})。",
                    "",
                    "**业务影响**：需要持续关注对经营的影响。",
                ]
            )
        body.extend(["", f"# {MONTHLY_SECTIONS[2]}"])
        for index in range(7, 9):
            body.extend(
                [
                    "",
                    f"## 事件 {index}｜行业",
                    "",
                    "**事件本质**：行业出现结构变化。",
                    "",
                    f"**传导逻辑**：详见[事件依据](https://example.com/{index})。",
                    "",
                    "**业务启示**：跟踪客户与成本变化。",
                ]
            )
        body.extend(
            [
                "",
                f"# {MONTHLY_SECTIONS[3]}",
                "",
                "## 1.重点跟踪方向",
                "",
                "关注[跟踪事项](https://example.com/9)。",
                "",
                "## 2.风险预警",
                "",
                "留意[风险事项](https://example.com/10)。",
            ]
        )
        return "\n".join(body)

    def test_valid_report_passes_deterministic_gate(self) -> None:
        errors = self.service._validate_monthly_markdown(self.valid_markdown(), self.materials)
        self.assertEqual(errors, [])

    def test_unknown_link_is_removed_by_sanitizer(self) -> None:
        value = self.valid_markdown() + "\n[外部虚构来源](https://unknown.example/report)"
        sanitized = self.service._sanitize_markdown(value, self.materials)
        self.assertNotIn("https://unknown.example/report", sanitized)

    def test_internal_technical_terms_are_blocked(self) -> None:
        value = self.valid_markdown() + "\n本报告采用多智能体和RAG生成。"
        errors = self.service._validate_monthly_markdown(value, self.materials)
        self.assertIn("报告正文包含内部技术或编号表达", errors)

    def test_generic_source_link_label_is_blocked(self) -> None:
        value = self.valid_markdown().replace(
            "[政策事项](https://example.com/2)",
            "[原文](https://example.com/2)",
        )
        errors = self.service._validate_monthly_markdown(value, self.materials)
        self.assertIn("存在“原文、来源、详情”等无语义链接文字", errors)

    def test_each_key_interpretation_requires_embedded_link(self) -> None:
        value = self.valid_markdown().replace(
            "[事件依据](https://example.com/8)",
            "事件依据",
        )
        errors = self.service._validate_monthly_markdown(value, self.materials)
        self.assertIn("第 2 条关键市场信息解读缺少自然嵌入的原文链接", errors)

    def test_company_focus_rejects_cross_company_business(self) -> None:
        jianyuan = self.valid_markdown() + "\n玉米果葡糖浆与麦芽糖浆是核心。大豆蛋白扩产。"
        errors = self.service._validate_monthly_markdown(
            jianyuan,
            self.materials,
            company_name="山东香驰健源生物科技有限公司",
        )
        self.assertIn("健源月报混入御馨大豆或植物蛋白业务主线", errors)

        yuxin = self.valid_markdown() + "\n大豆植物蛋白和豆粕是核心。果葡糖浆扩产。"
        errors = self.service._validate_monthly_markdown(
            yuxin,
            self.materials,
            company_name="山东御馨生物科技股份有限公司",
        )
        self.assertIn("御馨月报混入健源糖浆或糖醇业务主线", errors)

    def test_dimension_gate_accepts_bold_level_three_headings(self) -> None:
        value = self.valid_markdown()
        for index, dimension in enumerate(("政策", "竞对", "客户", "技术", "原料"), 1):
            value = value.replace(f"## {index}.{dimension}", f"### **{index}. {dimension}**")
        errors = self.service._validate_monthly_markdown(value, self.materials)
        self.assertFalse(any(error.startswith("五大维度缺少") for error in errors))

    def test_subheading_normalizer_restores_template_headings(self) -> None:
        value = "\n".join(
            [
                "### **1. 政策**",
                "**2、竞对**",
                "## 3.客户（变化）",
                "### 4、技术",
                "**5. 原料**",
                "**重点跟踪方向**",
                "### 2、风险预警",
            ]
        )
        normalized = self.service._normalize_monthly_subheadings(value)
        for index, dimension in enumerate(("政策", "竞对", "客户", "技术", "原料"), 1):
            self.assertIn(f"## {index}.{dimension}", normalized)
        self.assertIn("## 1.重点跟踪方向", normalized)
        self.assertIn("## 2.风险预警", normalized)

    def test_eight_distinct_citations_meet_template_gate(self) -> None:
        value = self.valid_markdown()
        value = value.replace("[跟踪事项](https://example.com/9)", "跟踪事项")
        value = value.replace("[风险事项](https://example.com/10)", "风险事项")
        errors = self.service._validate_monthly_markdown(value, self.materials)
        self.assertFalse(any(error.startswith("报告引用覆盖不足") for error in errors))

    def test_company_business_context_separates_jianyuan_and_yuxin(self) -> None:
        jianyuan = insight_company_business_context("山东香驰健源生物科技有限公司")
        yuxin = insight_company_business_context("山东御馨生物科技股份有限公司")
        self.assertIn("果葡糖浆、麦芽糖浆", jianyuan)
        self.assertIn("未涉及健源实际产品及其应用的，不予采用", jianyuan)
        self.assertIn("只聚焦蛋白板块", yuxin)
        self.assertIn("植物油", yuxin)
        self.assertIn("非转基因大豆", yuxin)

    def test_brief_editor_splits_long_paragraph_by_sentence(self) -> None:
        paragraph = "。".join(["客户新品与渠道变化带来新的市场观察" * 8 for _ in range(4)]) + "。"
        normalized = InsightFeishuBriefService._split_long_paragraphs(paragraph)
        self.assertIn("\n\n", normalized)
        self.assertEqual(normalized.replace("\n\n", ""), paragraph)

    def test_cross_company_material_filter_keeps_business_value_overlap(self) -> None:
        soybean_only = {
            "title": "禹王扩建大豆蛋白产线",
            "summary": "新增植物蛋白与豆粕产能。",
        }
        soybean_with_syrup = {
            "title": "植物蛋白饮料调整糖浆配方",
            "summary": "客户同步测试果葡糖浆和麦芽糖浆。",
        }
        self.assertIsNotNone(
            self.service._cross_company_material_reason(
                "山东香驰健源生物科技有限公司",
                soybean_only,
            )
        )
        self.assertIsNone(
            self.service._cross_company_material_reason(
                "山东香驰健源生物科技有限公司",
                soybean_with_syrup,
            )
        )
        syrup_only = {
            "title": "饮料客户调整果葡糖浆与麦芽糖浆配方",
            "summary": "客户测试低糖饮料方案。",
        }
        self.assertIsNone(
            self.service._cross_company_material_reason(
                "山东香驰健源生物科技有限公司",
                syrup_only,
            )
        )
        generic_corn_market = {
            "title": "国内玉米价格小幅波动",
            "summary": "产区玉米到货量发生变化。",
        }
        self.assertIsNotNone(
            self.service._cross_company_material_reason(
                "山东香驰健源生物科技有限公司",
                generic_corn_market,
            )
        )
        generic_tea_customer = {
            "title": "茶饮品牌新增一百家门店",
            "summary": "门店扩张但未披露糖类产品、配方或采购变化。",
        }
        self.assertIsNotNone(
            self.service._cross_company_material_reason(
                "山东香驰健源生物科技有限公司",
                generic_tea_customer,
            )
        )
        generic_patent = {
            "title": "食品企业取得新型杀菌装置专利",
            "summary": "该设备用于提升生产线清洗效率。",
            "tags": "技术 专利",
        }
        self.assertIsNotNone(
            self.service._cross_company_material_reason(
                "山东香驰健源生物科技有限公司",
                generic_patent,
            )
        )
        yuxin_policy = {
            "title": "食品添加剂新品种管理要求发布",
            "summary": "新规调整食品添加剂申报与标签管理要求。",
            "tags": "食品监管",
        }
        self.assertIsNotNone(
            self.service._cross_company_material_reason(
                "山东香驰健源生物科技有限公司",
                yuxin_policy,
            )
        )
        generic_customer = {
            "title": "茶饮品牌推出夏季新品",
            "summary": "新品覆盖果茶和咖啡场景。",
            "business_insight": "可能带动香驰大豆蛋白需求",
        }
        self.assertIsNotNone(
            self.service._cross_company_material_reason(
                "山东御馨生物科技股份有限公司",
                generic_customer,
            )
        )
        incidental_soybean = {
            "title": "益海嘉里周口投产果葡糖浆和麦芽糖浆产线",
            "summary": "项目核心为玉米深加工，正文附带提及集团其他大豆业务。",
            "content": "集团同时经营大豆加工业务。",
        }
        self.assertIsNotNone(
            self.service._cross_company_material_reason(
                "山东御馨生物科技股份有限公司",
                incidental_soybean,
            )
        )
        direct_soybean = {
            "title": "大豆蛋白客户扩大植物蛋白饮料产线",
            "summary": "新增产线直接带动分离蛋白采购需求。",
        }
        self.assertIsNone(
            self.service._cross_company_material_reason(
                "山东御馨生物科技股份有限公司",
                direct_soybean,
            )
        )
        sugar_policy = {
            "title": "功能糖与赤藓糖醇食品标签管理政策调整",
            "summary": "政策涉及糖醇和甜味剂产品的标识要求。",
            "tags": "食品监管",
        }
        self.assertIsNotNone(
            self.service._cross_company_material_reason(
                "山东御馨生物科技股份有限公司",
                sugar_policy,
            )
        )
        soybean_oil = {
            "title": "大豆油企业扩建植物油灌装线",
            "summary": "项目新增食用油产能。",
        }
        self.assertIn(
            "植物油",
            self.service._cross_company_material_reason(
                "山东御馨生物科技股份有限公司",
                soybean_oil,
            ) or "",
        )
        non_gmo_soybean = {
            "title": "非转基因大豆进口价格调整",
            "summary": "非转基因大豆供应收紧，采购成本发生变化。",
        }
        self.assertIsNone(
            self.service._cross_company_material_reason(
                "山东御馨生物科技股份有限公司",
                non_gmo_soybean,
            )
        )

    def test_material_approval_uses_global_editor_above_sixty_items(self) -> None:
        materials = [
            {
                "id": index,
                "title": f"大豆蛋白市场情报 {index}",
                "summary": f"植物蛋白与豆粕业务直接相关的事实 {index}",
                "source_url": f"https://example.com/{index}",
            }
            for index in range(1, 71)
        ]

        async def invoke_json(**kwargs):
            stage = kwargs["stage"]
            if stage == "material_global_selection":
                return (
                    {
                        "selected_ids": list(range(1, 36)),
                        "coverage": {"政策": 3, "竞对": 8, "客户": 8, "技术": 8, "原料": 8},
                    },
                    "global-editor",
                )
            batch_index = int(stage.rsplit("_", 1)[-1]) - 1
            batch = materials[batch_index * 25 : (batch_index + 1) * 25]
            return (
                {
                    "approved": [
                        {
                            "id": item["id"],
                            "score": 90,
                            "role": "行业",
                            "subject": "测试主题",
                            "fact_digest": item["summary"],
                            "reason": "直接相关",
                        }
                        for item in batch
                    ],
                    "rejected": [],
                    "coverage_gaps": [],
                },
                "batch-reviewer",
            )

        with patch.object(self.service, "_invoke_json", AsyncMock(side_effect=invoke_json)):
            approved, audit = asyncio.run(
                self.service._approve_materials(
                    company_name="山东御馨生物科技股份有限公司",
                    period_start=datetime(2026, 7, 1),
                    period_end=datetime(2026, 7, 27),
                    materials=materials,
                    model_names=["model-a", "model-b", "model-c"],
                    stage_trace=[],
                )
            )
        self.assertEqual(len(approved), 35)
        self.assertEqual(audit["global_selection"]["mode"], "ai_global_editor")
        self.assertEqual(audit["global_selection"]["model"], "global-editor")

    def test_section_order_accepts_bold_h2_headings(self) -> None:
        body = ["管理层月度市场信息报告｜2026年7月1日至26日｜生成时间：2026年7月26日"]
        for section in MONTHLY_SECTIONS:
            body.extend([f"## **{section}**", "该章节有真实正文。"])
        ordered = self.service._order_sections("\n\n".join(body))
        for section in MONTHLY_SECTIONS:
            self.assertIn(f"# {section}", ordered)
        self.assertNotIn("暂无经审批后可用于该章节", ordered)

    def test_section_order_preserves_unrecognized_draft(self) -> None:
        draft = "管理层月度市场信息报告\n\n正文存在，但主章节格式异常。"
        self.assertEqual(self.service._order_sections(draft), draft)

    def test_section_order_accepts_plain_leader_document_headings(self) -> None:
        body = ["管理层月度市场信息报告｜2026年7月1日至26日｜生成时间：2026年7月26日"]
        for section in MONTHLY_SECTIONS:
            body.extend([section, "该章节有真实正文。"])
        ordered = self.service._order_sections("\n\n".join(body))
        for section in MONTHLY_SECTIONS:
            self.assertIn(f"# {section}", ordered)
        self.assertNotIn("暂无经审批后可用于该章节", ordered)

    def test_missing_header_is_restored_deterministically(self) -> None:
        restored = self.service._ensure_monthly_header(
            "# 一、月度核心总览\n\n正文",
            company_name="山东御馨生物科技股份有限公司",
            period_start=datetime(2026, 7, 1),
            period_end=datetime(2026, 7, 27),
            material_count=42,
        )
        self.assertTrue(restored.startswith("管理层月度市场信息报告｜"))
        self.assertIn("审批后素材 42 条", restored)

    def test_markdown_title_header_is_replaced_without_duplication(self) -> None:
        value = (
            "# 管理层月度市场信息报告｜2026年7月1日至27日\n\n"
            "适用公司：山东御馨生物科技股份有限公司\n\n---\n\n"
            "# 一、月度核心总览\n\n正文"
        )
        restored = self.service._ensure_monthly_header(
            value,
            company_name="山东御馨生物科技股份有限公司",
            period_start=datetime(2026, 7, 1),
            period_end=datetime(2026, 7, 27),
            material_count=42,
        )
        self.assertEqual(restored.count("管理层月度市场信息报告"), 1)
        self.assertEqual(restored.count("适用公司：山东御馨生物科技股份有限公司"), 1)

    def test_blocking_issue_reduces_review_score(self) -> None:
        review = {
            "review_role": "事实与幻觉核验员",
            "fact_score": 90,
            "relevance_score": 90,
            "depth_score": 90,
            "structure_score": 90,
            "readability_score": 90,
            "citation_score": 90,
            "hallucination_risk": "高",
            "blocking_issues": ["存在资料外数字"],
        }
        self.assertEqual(self.service._review_score([review]), 70)

    def test_section_parallel_uses_markdown_interface(self) -> None:
        materials = [
            {
                **item,
                "title": f"情报 {item['id']}",
                "approval": {"role": "竞对" if item["id"] % 2 else "客户"},
            }
            for item in self.materials
        ]
        invoke = AsyncMock(return_value=("# 一、竞对市场信息导读\n\n正文", "mock-model"))
        with patch.object(self.service, "_invoke_markdown", invoke):
            candidate = asyncio.run(
                self.service._generate_section_parallel(
                    company_name="山东御馨生物科技股份有限公司",
                    period_start=datetime(2026, 7, 1),
                    period_end=datetime(2026, 7, 27),
                    materials=materials,
                    prompt_override=None,
                    model_names=["model-a", "model-b", "model-c"],
                    stage_trace=[],
                )
            )
        self.assertEqual(invoke.await_count, 4)
        self.assertEqual(candidate.strategy_code, "section_parallel")


if __name__ == "__main__":
    unittest.main()
