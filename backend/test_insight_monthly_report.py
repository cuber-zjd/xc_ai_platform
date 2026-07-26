from __future__ import annotations

import unittest

from app.services.agent.insight.feishu_monthly_report_service import (
    MONTHLY_SECTIONS,
    InsightFeishuMonthlyReportService,
)


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
        body = ["管理层月度市场信息报告｜2026年7月1日至26日｜生成时间：2026年7月26日", "", "---"]
        for index, section in enumerate(MONTHLY_SECTIONS, 1):
            body.extend(
                [
                    "",
                    f"# {section}",
                    "",
                    f"## 主题 {index}",
                    "",
                    f"本月发生具体变化，详见[相关事项](https://example.com/{index})。",
                ]
            )
        for index in range(8, 11):
            body.append(f"补充[交叉来源](https://example.com/{index})。")
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


if __name__ == "__main__":
    unittest.main()
