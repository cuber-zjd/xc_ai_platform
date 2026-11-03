"""报告证据的确定性摘录、引用对账；不将模型分析当作原文事实。"""

import json
import re
from typing import Any

from app.core.config import settings
from app.services.agent.insight.crawler.content_cleaner import insight_content_cleaner


class MaterialApprovalIncomplete(ValueError):
    def __init__(self, audit: dict[str, Any]) -> None:
        self.audit = audit
        super().__init__(f"素材审批未完成：{audit['pending_count']} 条尚无有效结论；已保存逐条状态，不按无关素材排除")


def report_model_names(role: str) -> list[str]:
    values = {
        "writer": settings.INSIGHT_REPORT_WRITER_MODELS,
        "reviewer": settings.INSIGHT_REPORT_REVIEWER_MODELS,
        "approval": settings.INSIGHT_REPORT_APPROVAL_MODELS,
    }
    return list(dict.fromkeys(name.strip() for name in values[role].split(",") if name.strip()))


def report_policy_snapshot() -> dict[str, Any]:
    return {
        "version": "evidence_v2",
        "preferred_models": {role: report_model_names(role) for role in ("writer", "reviewer", "approval")},
        "approval_concurrency": settings.INSIGHT_REPORT_APPROVAL_CONCURRENCY,
        "context_char_budget": settings.INSIGHT_REPORT_CONTEXT_CHAR_BUDGET,
        "approval_batch_size": 25,
        "material_quota": None,
    }


def evidence_excerpt(content: str, *, budget: int = 2400, query: str = "") -> dict[str, Any]:
    """保留原文位置，优先取关键事实段；长文保留首尾，避免只读开头。"""
    if len(content) <= budget:
        return {"text": content, "complete": True, "source_chars": len(content), "spans": [[0, len(content)]]}
    paragraphs = list(re.finditer(r"[^\n。！？]+[。！？]?", content))
    if not paragraphs:
        return {"text": content[:budget], "complete": False, "source_chars": len(content), "spans": [[0, budget]]}
    terms = set(re.findall(r"[\w\u4e00-\u9fff]{2,12}", query.lower()))
    scored = sorted(
        paragraphs,
        key=lambda p: (
            p is paragraphs[0] or p is paragraphs[-1],
            sum(term in p.group().lower() for term in terms) + bool(re.search(r"\d|投产|公告|获批|专利", p.group())),
        ), reverse=True,
    )
    spans: list[tuple[int, int]] = []
    remaining = budget
    for paragraph in scored:
        if remaining <= 0:
            break
        length = min(len(paragraph.group()), remaining, max(200, budget // 3))
        spans.append((paragraph.start(), paragraph.start() + length))
        remaining -= length
    spans.sort()
    merged: list[tuple[int, int]] = []
    for start, end in spans:
        if merged and start == merged[-1][1]:
            merged[-1] = (merged[-1][0], end)
        else:
            merged.append((start, end))
    return {
        "text": "\n[…]\n".join(content[start:end] for start, end in merged),
        "complete": False, "source_chars": len(content), "spans": merged,
    }


def citation_coverage(markdown: str, materials: list[dict[str, Any]]) -> dict[str, Any]:
    """链接出现仅表示引用覆盖，不代表该链接已证明句中事实。"""
    normalize = insight_content_cleaner.normalize_url
    references = [(match.start(), normalize(match.group(1))) for match in re.finditer(r"\[[^\]]+\]\((https?://[^\s)]+)\)", markdown)]
    headings = [(match.start(), match.group(1)) for match in re.finditer(r"^#{1,4}\s+(.+)$", markdown, re.MULTILINE)]
    rows = []
    for item in materials:
        url = str(item.get("source_url") or "").strip()
        locations = [position for position, reference in references if url and reference == normalize(url)]
        sections = list(dict.fromkeys(next((heading for offset, heading in reversed(headings) if offset <= position), "正文") for position in locations))
        rows.append({
            "id": item.get("id"), "source_url": url,
            "status": "cited" if locations else "not_cited",
            "sections": sections,
            "reason": None if locations else "正文未引用，需审阅其遗漏或合并原因",
        })
    return {"candidate_count": len(rows), "cited_count": sum(row["status"] == "cited" for row in rows), "items": rows}


def report_material_context(materials: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """所有事件保留索引，按整期预算分配原文摘录；不靠删除末尾事件压缩上下文。"""
    budget = max(settings.INSIGHT_REPORT_CONTEXT_CHAR_BUDGET, 10000)
    indexes = []
    for item in materials:
        approval = item.get("approval") or {}
        indexes.append({
            "id": item.get("id"), "title": item.get("title"),
            "publish_time": item.get("publish_time"), "source_url": item.get("source_url"),
            "subject_name": item.get("subject_name"), "category": item.get("category"),
            "summary_navigation_only": str(approval.get("fact_digest") or item.get("summary") or "")[:600],
            "role": item.get("brief_role") or approval.get("role"),
            "key_numbers_to_verify": approval.get("key_numbers") or [],
        })

    def build(share: int) -> list[dict[str, Any]]:
        return [
            index | {"original_evidence": evidence_excerpt(str(item.get("content") or ""), budget=share, query=str(item.get("title") or ""))}
            for index, item in zip(indexes, materials, strict=True)
        ]

    def size(value: list[dict[str, Any]]) -> int:
        return len(json.dumps(value, ensure_ascii=False, default=str))

    result = build(6000)
    if size(result) <= budget:
        return result
    result = build(200)
    if size(result) > budget:
        for index in indexes:
            index["summary_navigation_only"] = index["summary_navigation_only"][:160]
        result = build(200)
    if size(result) > budget:
        raise ValueError("整期素材索引及最小证据超过上下文字符预算，请提高预算或拆分章节研究；未截断候选材料")
    # 按实际序列化长度分配，而非只数正文，确保转义、链接和证据位置也计入预算。
    lower, upper = 200, 6000
    while lower + 1 < upper:
        share = (lower + upper) // 2
        candidate = build(share)
        if size(candidate) <= budget:
            result, lower = candidate, share
        else:
            upper = share
    return result
