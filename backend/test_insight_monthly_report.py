from __future__ import annotations

import asyncio
import unittest
from datetime import datetime
from unittest.mock import AsyncMock, patch

from app.services.agent.insight.feishu_monthly_report_service import (
    MONTHLY_SECTIONS,
    InsightFeishuMonthlyReportService,
)
from app.services.agent.insight.company_context import insight_company_business_context


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
        self.assertIn("大豆精深加工和植物蛋白", jianyuan)
        self.assertIn("果葡糖浆、麦芽糖浆", yuxin)
        self.assertIn("不是健源月报的核心业务", jianyuan)
        self.assertIn("不是御馨月报的核心业务", yuxin)

    def test_cross_company_material_filter_keeps_only_direct_overlap(self) -> None:
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
                "山东御馨生物科技股份有限公司",
                soybean_only,
            )
        )
        self.assertIsNone(
            self.service._cross_company_material_reason(
                "山东御馨生物科技股份有限公司",
                soybean_with_syrup,
            )
        )
        generic_customer = {
            "title": "茶饮品牌推出夏季新品",
            "summary": "新品覆盖果茶和咖啡场景。",
            "business_insight": "可能带动香驰大豆蛋白需求",
        }
        self.assertIsNotNone(
            self.service._cross_company_material_reason(
                "山东香驰健源生物科技有限公司",
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
                "山东香驰健源生物科技有限公司",
                incidental_soybean,
            )
        )
        direct_soybean = {
            "title": "大豆蛋白客户扩大植物蛋白饮料产线",
            "summary": "新增产线直接带动分离蛋白采购需求。",
        }
        self.assertIsNone(
            self.service._cross_company_material_reason(
                "山东香驰健源生物科技有限公司",
                direct_soybean,
            )
        )

    def test_material_approval_uses_global_editor_above_sixty_items(self) -> None:
        materials = [
            {
                "id": index,
                "title": f"情报 {index}",
                "summary": f"与目标公司核心业务直接相关的事实 {index}",
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
