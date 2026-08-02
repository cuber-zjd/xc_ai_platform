from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.llm_factory import LLMFactory
from app.models.system.sys_model import SysModel
from app.services.agent.insight.company_context import (
    insight_company_business_context,
    insight_company_material_rejection_reason,
)


MONTHLY_SECTIONS = [
    "一、月度核心总览",
    "二、五大维度月度趋势",
    "三、月度关键市场信息解读",
    "四、下月跟踪重点与风险提示",
]

MONTHLY_TEMPLATE_PROMPT = """
这是领导确认的月度报告模板，必须严格沿用以下结构和分析逻辑。正文不得展示生成过程，
不得增加竞对明细、客户明细、方法说明、资料清单等模板之外的主章节。

固定结构：
1. 月度核心总览：只写一段，开门见山概括当月行业核心主线，提炼 1-2 条最关键的变化结论，
   不铺垫细节，不罗列新闻。
2. 五大维度月度趋势：固定包含“1.政策、2.竞对、3.客户、4.技术、5.原料”五个二级标题。
   每个维度严格遵循“趋势判断（变化）→核心佐证→业务影响”：
   - 趋势判断：一句话概括本月方向和相对变化；
   - 核心佐证：选 2-3 个最有代表性的事实并嵌入原文链接；
   - 业务影响：直接落到目标公司的合规、经营、产品、销售、研发、采购、成本或毛利。
   政策确无合格资料时可以明确写“本月未发现足以改变经营判断的新政策信号”，不得用旧闻凑数。
3. 月度关键市场信息解读：只选 1-3 条最具标志性、具有中长期影响的事件，不重复复述新闻。
   每条以“事件名称｜类别标签”为二级标题，并固定写清：
   - 事件本质：一句话定性其行业意义；
   - 传导逻辑：说明如何影响产业链、需求、竞争格局或成本；
   - 业务启示：给出对目标公司的直接参考和应对方向。
   每条解读至少引用 1 条审批资料，链接必须嵌入“主体+动作”组成的自然事件短语中，
   不把链接挂在章节标题上，也不得使用“原文、来源、详情、点击查看”等无语义文字。
4. 下月跟踪重点与风险提示：
   - 重点跟踪方向：列出下月需持续关注的 3-4 个核心变量，写清观察信号；
   - 风险预警：列出 2-3 个有资料基础的潜在风险，标明影响范围和触发条件。

写作要求：
- 只使用给定的已审批资料，不使用模型记忆补数字、日期、企业动作或链接。
- 相同事件合并，多来源只用于交叉印证，不重复计算。
- 链接挂在自然的“主体+动作”事件短语上，不显示裸网址，不复制冗长新闻标题，
  禁止使用“原文、来源、详情、点击查看”等无语义链接文字。
- 强调“本月发生了什么变化、为何重要、如何传导、公司应关注什么”，不能写成信息汇编。
- 重要数字必须保留主体、口径和时间，不得把计划、预测、传闻写成已实现结果。
- 弱相关、广告、榜单、通用专利、旧闻重发和无法确认日期的材料不得用于核心结论。
- 报告允许写审慎研判，但必须区分“已确认事实、较强信号、待验证线索”。
- 禁止空泛口号、新闻目录式罗列、夸张媒体词和无证据的因果判断。
"""


@dataclass
class MonthlyCandidate:
    strategy_code: str
    strategy_name: str
    markdown: str
    models: list[str] = field(default_factory=list)
    stage_notes: list[str] = field(default_factory=list)
    reviews: list[dict[str, Any]] = field(default_factory=list)
    score: float = 0
    document_id: str | None = None
    document_url: str | None = None


@dataclass
class MonthlyReportResult:
    title: str
    markdown: str
    candidates: list[MonthlyCandidate]
    audit_markdown: str
    output_payload: dict[str, Any]


class InsightFeishuMonthlyReportService:
    """按领导月报模板执行多模型、多阶段研究和审校。"""

    async def generate(
        self,
        db: AsyncSession,
        *,
        company_name: str,
        period_start: datetime,
        period_end: datetime,
        materials: list[dict[str, Any]],
        prompt_override: str | None,
        generation_strategy: str,
    ) -> MonthlyReportResult:
        model_pool = await self._model_pool(db)
        stage_trace: list[dict[str, Any]] = []
        approved, approval = await self._approve_materials(
            company_name=company_name,
            period_start=period_start,
            period_end=period_end,
            materials=materials,
            model_names=model_pool,
            stage_trace=stage_trace,
        )
        if len(approved) < 10:
            raise ValueError(f"月报资料审批后仅剩 {len(approved)} 条，无法支撑深度月报")

        candidates: list[MonthlyCandidate] = []
        strategies = (
            ["single_model", "section_parallel", "multi_agent"]
            if generation_strategy in {"auto", "multi_agent_ensemble"}
            else [generation_strategy]
        )
        if "single_model" in strategies:
            candidates.append(
                await self._generate_single_model(
                    company_name=company_name,
                    period_start=period_start,
                    period_end=period_end,
                    materials=approved,
                    prompt_override=prompt_override,
                    model_name=model_pool[0],
                    stage_trace=stage_trace,
                )
            )
            logger.info("月报候选策略完成: single_model")
        if "section_parallel" in strategies:
            candidates.append(
                await self._generate_section_parallel(
                    company_name=company_name,
                    period_start=period_start,
                    period_end=period_end,
                    materials=approved,
                    prompt_override=prompt_override,
                    model_names=model_pool,
                    stage_trace=stage_trace,
                )
            )
            logger.info("月报候选策略完成: section_parallel")
        if "multi_agent" in strategies or "multi_agent_ensemble" in strategies:
            candidates.append(
                await self._generate_multi_agent(
                    company_name=company_name,
                    period_start=period_start,
                    period_end=period_end,
                    materials=approved,
                    prompt_override=prompt_override,
                    model_names=model_pool,
                    stage_trace=stage_trace,
                )
            )
            logger.info("月报候选策略完成: multi_agent")

        logger.info("开始并行审校月报候选稿，候选数: {}", len(candidates))
        await asyncio.gather(
            *[
                self._review_candidate(
                    candidate,
                    company_name=company_name,
                    period_start=period_start,
                    period_end=period_end,
                    materials=approved,
                    model_names=model_pool,
                    stage_trace=stage_trace,
                )
                for candidate in candidates
            ]
        )
        candidates.sort(key=lambda item: item.score, reverse=True)
        if len(candidates) == 1:
            selected = candidates[0]
            logger.info("单候选实验直接进入终审，不执行无意义的二次选优改写")
            final_markdown = selected.markdown
            final_reviews = selected.reviews
            selection = {
                "judge_model": None,
                "editor_model": None,
                "selected_strategy": selected.strategy_code,
                "selected_strategy_name": selected.strategy_name,
                "judgment": {"reason": "独立策略实验仅有一个候选，直接进入发布门禁。"},
            }
        else:
            logger.info("月报候选稿审校完成，开始综合选优")
            final_markdown, selection = await self._synthesize_final(
                candidates=candidates,
                company_name=company_name,
                period_start=period_start,
                period_end=period_end,
                materials=approved,
                prompt_override=prompt_override,
                model_names=model_pool,
                stage_trace=stage_trace,
            )
            final_reviews = await self._run_review_panel(
                markdown=final_markdown,
                company_name=company_name,
                period_start=period_start,
                period_end=period_end,
                materials=approved,
                model_names=model_pool,
                stage_trace=stage_trace,
                stage_prefix="final_review",
            )
        final_score = self._review_score(final_reviews)
        blocking = self._blocking_issues(final_reviews)
        deterministic_errors = self._validate_monthly_markdown(
            final_markdown,
            approved,
            company_name=company_name,
        )
        if blocking or deterministic_errors or final_score < 82:
            repair_reviews = list(final_reviews)
            if deterministic_errors:
                repair_reviews.append(
                    {
                        "review_role": "确定性格式检查",
                        "blocking_issues": deterministic_errors,
                        "revision_advice": [
                            "只针对列出的模板或引用问题修订，保留原有事实和已审批链接。"
                        ],
                    }
                )
            final_markdown = await self._repair_final(
                markdown=final_markdown,
                reviews=repair_reviews,
                company_name=company_name,
                period_start=period_start,
                period_end=period_end,
                materials=approved,
                model_name=model_pool[0],
                stage_trace=stage_trace,
            )
            final_reviews = await self._run_review_panel(
                markdown=final_markdown,
                company_name=company_name,
                period_start=period_start,
                period_end=period_end,
                materials=approved,
                model_names=model_pool,
                stage_trace=stage_trace,
                stage_prefix="final_recheck",
            )
            final_score = self._review_score(final_reviews)
            blocking = self._blocking_issues(final_reviews)

        deterministic_errors = self._validate_monthly_markdown(
            final_markdown,
            approved,
            company_name=company_name,
        )
        if blocking or deterministic_errors or final_score < 78:
            reasons = blocking + deterministic_errors + [f"综合评分 {final_score:.1f}"]
            raise ValueError("月报终审未通过：" + "；".join(dict.fromkeys(reasons))[:1800])

        title = self._title(company_name, period_end)
        audit_markdown = self._audit_markdown(
            company_name=company_name,
            period_start=period_start,
            period_end=period_end,
            original_count=len(materials),
            approved_count=len(approved),
            approval=approval,
            candidates=candidates,
            final_reviews=final_reviews,
            final_score=final_score,
            selection=selection,
            stage_trace=stage_trace,
        )
        output_payload = {
            "pipeline_version": "monthly_multi_strategy_v1",
            "generation_strategy": generation_strategy,
            "model_pool": model_pool,
            "material_approval": approval,
            "candidate_results": [
                {
                    "strategy_code": item.strategy_code,
                    "strategy_name": item.strategy_name,
                    "models": item.models,
                    "score": item.score,
                    "reviews": item.reviews,
                    "stage_notes": item.stage_notes,
                }
                for item in candidates
            ],
            "final_selection": selection,
            "final_reviews": final_reviews,
            "final_score": final_score,
            "stage_trace": stage_trace,
        }
        return MonthlyReportResult(
            title=title,
            markdown=final_markdown,
            candidates=candidates,
            audit_markdown=audit_markdown,
            output_payload=output_payload,
        )

    async def _model_pool(self, db: AsyncSession) -> list[str]:
        rows = list(
            (
                await db.exec(
                    select(SysModel)
                    .where(
                        SysModel.model_type == "chat",
                        SysModel.is_enabled == True,  # noqa: E712
                        SysModel.status == 1,
                    )
                    .order_by(SysModel.model_level.asc(), SysModel.priority.asc())
                )
            ).all()
        )
        complex_models = [row.model_name for row in rows if row.capability == "complex-reasoning"]
        general_models = [row.model_name for row in rows if row.capability == "general"]
        pool: list[str] = []
        for name in complex_models[:4] + general_models[:2]:
            if name not in pool:
                pool.append(name)
        if not pool:
            raise ValueError("系统没有可用于月报生成的启用模型")
        while len(pool) < 4:
            pool.append(pool[len(pool) % len(pool)])
        return pool

    async def _approve_materials(
        self,
        *,
        company_name: str,
        period_start: datetime,
        period_end: datetime,
        materials: list[dict[str, Any]],
        model_names: list[str],
        stage_trace: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        deterministic_rejected = [
            {"id": item.get("id"), "reason": reason}
            for item in materials
            if (reason := self._cross_company_material_reason(company_name, item))
        ]
        deterministic_rejected_ids = {
            int(item["id"])
            for item in deterministic_rejected
            if str(item.get("id") or "").isdigit()
        }
        eligible_materials = [
            item
            for item in materials
            if int(item.get("id") or 0) not in deterministic_rejected_ids
        ]
        batches = [
            eligible_materials[index : index + 25]
            for index in range(0, min(len(eligible_materials), 200), 25)
        ]

        async def approve_batch(batch_index: int, batch: list[dict[str, Any]]) -> tuple[dict[str, Any], str]:
            compact = [self._compact_material(item) for item in batch]
            prompt = f"""
你是月报资料审批员，不写报告。审批 {company_name} 在
{self._period_text(period_start, period_end)} 的正式情报。
目标公司真实业务边界：{insight_company_business_context(company_name)}

逐条判断：
- 是否确实发生在本月，旧闻重发或日期矛盾必须排除；
- 是否属于目标公司的竞对、客户、原料、技术、行业或政策信息；
- 是否有具体主体、动作、数字或业务背景；
- 是否为广告、榜单、通用专利、重复转载或仅靠多层推测才能关联；
- 同一事件多来源时保留证据最强者，并记录 corroborating_ids。

只返回 JSON：
{{
  "approved": [
    {{
      "id": 1,
      "score": 90,
      "role": "竞对|客户|原料|技术|政策|行业",
      "subject": "企业或主题",
      "fact_digest": "只含原文明示事实的一句话",
      "key_numbers": ["数字及口径"],
      "corroborating_ids": [2],
      "reason": "入选原因"
    }}
  ],
  "rejected": [{{"id": 3, "reason": "旧闻|重复|弱相关|广告|证据不足|日期冲突"}}],
  "coverage_gaps": ["资料缺口"]
}}

公司业务边界由材料中的所属公司和主题共同确定。审批阈值 72 分，不得为凑数量降标。
这是第 {batch_index + 1}/{len(batches)} 批。材料：
{json.dumps(compact, ensure_ascii=False, default=str)}
"""
            return await self._invoke_json(
                stage=f"material_approval_batch_{batch_index + 1}",
                system="你是严格的资料审批员，只依据输入资料输出合法 JSON。",
                prompt=prompt,
                preferred_model=model_names[batch_index % len(model_names)],
                stage_trace=stage_trace,
                enable_reasoning=False,
                invocation_timeout_seconds=120,
            )

        batch_results = await asyncio.gather(
            *[
                approve_batch(batch_index, batch)
                for batch_index, batch in enumerate(batches)
            ]
        )
        by_id = {
            int(item["id"]): item
            for item in eligible_materials
            if item.get("id") is not None
        }
        approved_meta: list[dict[str, Any]] = []
        approved_ids: list[int] = []
        for payload, _used_model in batch_results:
            for row in payload.get("approved") or []:
                if not isinstance(row, dict):
                    continue
                try:
                    item_id = int(row.get("id"))
                    score = int(row.get("score") or 0)
                except (TypeError, ValueError):
                    continue
                if item_id in by_id and score >= 72 and item_id not in approved_ids:
                    approved_ids.append(item_id)
                    approved_meta.append(
                        {
                            "id": item_id,
                            "score": score,
                            "role": str(row.get("role") or "行业"),
                            "subject": str(row.get("subject") or by_id[item_id].get("subject_name") or ""),
                            "fact_digest": str(row.get("fact_digest") or by_id[item_id].get("summary") or "")[:800],
                            "key_numbers": [str(value)[:120] for value in (row.get("key_numbers") or [])[:8]],
                            "corroborating_ids": [
                                int(value)
                                for value in (row.get("corroborating_ids") or [])
                                if str(value).isdigit() and int(value) in by_id
                            ][:8],
                            "reason": str(row.get("reason") or "")[:300],
                        }
                    )
        global_selection: dict[str, Any] = {
            "mode": "not_required",
            "candidate_count": len(approved_ids),
            "selected_count": len(approved_ids),
        }
        if len(approved_ids) > 60:
            global_candidates = [
                {
                    "id": row["id"],
                    "score": row["score"],
                    "role": row["role"],
                    "subject": row["subject"],
                    "title": str(by_id[row["id"]].get("title") or "")[:180],
                    "fact_digest": row["fact_digest"][:360],
                    "reason": row["reason"][:180],
                }
                for row in approved_meta
            ]
            selection_payload, selection_model = await self._invoke_json(
                stage="material_global_selection",
                system="你是月报全局选材总编，只输出合法 JSON，不写报告。",
                prompt=f"""
对 {company_name} 的月报初筛材料做第二轮全局横向比较。
目标公司真实业务边界：{insight_company_business_context(company_name)}
周期：{self._period_text(period_start, period_end)}

要求：
1. 从全部初筛项中保留 30-50 条最有管理价值的材料，绝不因为某条在局部批次通过就继续保留；
2. 优先覆盖政策、竞对、客户、技术、原料五个维度，但不得用弱相关材料补齐分类；
3. 健源不得把大豆蛋白、蛋白粉、豆粕当作核心业务，御馨不得把淀粉糖、果葡糖浆、糖醇当作核心业务；
4. 相同事件只留事实最完整、来源最可靠的一条，其他来源作为交叉印证但不单独占名额；
5. 优先保留有明确主体、动作、时间、数字、经营影响或监管变化的材料；
6. 其他产业公司的材料只有能直接影响目标公司的核心产品、客户、竞对、原料或合规时才可保留。

只返回 JSON：
{{
  "selected_ids": [1, 2],
  "rejected": [{{"id": 3, "reason": "跨产业公司/重复/弱相关"}}],
  "coverage": {{"政策": 0, "竞对": 0, "客户": 0, "技术": 0, "原料": 0}},
  "coverage_gaps": ["仍然缺少的高价值信息"]
}}

初筛材料：
{json.dumps(global_candidates, ensure_ascii=False, default=str)}
""",
                preferred_model=model_names[0],
                stage_trace=stage_trace,
                enable_reasoning=False,
                invocation_timeout_seconds=180,
            )
            selected_ids: list[int] = []
            for value in selection_payload.get("selected_ids") or []:
                try:
                    item_id = int(value)
                except (TypeError, ValueError):
                    continue
                if item_id in approved_ids and item_id not in selected_ids:
                    selected_ids.append(item_id)
            if len(selected_ids) >= 10:
                selected_ids = selected_ids[:60]
                approved_by_id = {row["id"]: row for row in approved_meta}
                approved_ids = selected_ids
                approved_meta = [approved_by_id[item_id] for item_id in approved_ids]
                global_selection = {
                    "mode": "ai_global_editor",
                    "model": selection_model,
                    "candidate_count": len(global_candidates),
                    "selected_count": len(approved_ids),
                    "coverage": selection_payload.get("coverage") or {},
                    "coverage_gaps": selection_payload.get("coverage_gaps") or [],
                    "rejected": selection_payload.get("rejected") or [],
                }
            else:
                global_selection = {
                    "mode": "invalid_model_result_kept_batch_approval",
                    "model": selection_model,
                    "candidate_count": len(global_candidates),
                    "selected_count": len(approved_ids),
                    "warning": f"全局总编仅返回 {len(selected_ids)} 条，未采用该结果",
                }
        if len(approved_ids) < 6:
            raise ValueError(
                f"月报资料审批仅通过 {len(approved_ids)} 条，未达到 6 条最低证据要求；"
                "系统不会用未通过审批的材料凑数"
            )
        approved_by_id = {row["id"]: row for row in approved_meta}
        approved = []
        for item_id in approved_ids:
            item = dict(by_id[item_id])
            item["approval"] = approved_by_id[item_id]
            approved.append(item)
        rejected = deterministic_rejected + [
            {"id": row.get("id"), "reason": str(row.get("reason") or "")[:300]}
            for payload, _used_model in batch_results
            for row in (payload.get("rejected") or [])
            if isinstance(row, dict)
        ]
        coverage_gaps = [
            str(value)[:300]
            for payload, _used_model in batch_results
            for value in (payload.get("coverage_gaps") or [])[:6]
        ]
        return approved, {
            "models": list(dict.fromkeys(used_model for _payload, used_model in batch_results)),
            "batch_count": len(batch_results),
            "candidate_count": len(materials),
            "approved_count": len(approved),
            "rejected_count": max(len(materials) - len(approved), 0),
            "approved": approved_meta,
            "rejected": rejected,
            "coverage_gaps": list(dict.fromkeys(coverage_gaps))[:12],
            "global_selection": global_selection,
            "deterministic_cross_company_rejected_count": len(deterministic_rejected),
        }

    async def _generate_single_model(
        self,
        *,
        company_name: str,
        period_start: datetime,
        period_end: datetime,
        materials: list[dict[str, Any]],
        prompt_override: str | None,
        model_name: str,
        stage_trace: list[dict[str, Any]],
    ) -> MonthlyCandidate:
        markdown, used_model = await self._invoke_markdown(
            stage="candidate_single_model",
            system="你是管理层月报主笔。按固定模板一次形成完整月报，不展示生成过程。",
            prompt=self._draft_prompt(
                company_name=company_name,
                period_start=period_start,
                period_end=period_end,
                materials=materials,
                prompt_override=prompt_override,
                instruction="由你独立完成资料归并、月度分析、明细整理和整稿编辑。",
            ),
            preferred_model=model_name,
            stage_trace=stage_trace,
        )
        return MonthlyCandidate(
            strategy_code="single_model",
            strategy_name="单模型整稿基线",
            markdown=self._sanitize_markdown(markdown, materials),
            models=[used_model],
            stage_notes=["同一模型一次形成整稿，用于观察整体连贯性和遗漏风险。"],
        )

    async def _generate_section_parallel(
        self,
        *,
        company_name: str,
        period_start: datetime,
        period_end: datetime,
        materials: list[dict[str, Any]],
        prompt_override: str | None,
        model_names: list[str],
        stage_trace: list[dict[str, Any]],
    ) -> MonthlyCandidate:
        all_roles = ["竞对", "客户", "原料", "技术", "政策", "行业"]
        section_specs = [
            (
                "月度总览研究员",
                all_roles,
                ["一、月度核心总览"],
                "只写一段，提炼本月 1-2 条最关键变化结论。",
            ),
            (
                "五维趋势研究员",
                all_roles,
                ["二、五大维度月度趋势"],
                (
                    "固定包含 1.政策、2.竞对、3.客户、4.技术、5.原料；"
                    "每项都写趋势判断、核心佐证、业务影响。"
                ),
            ),
            (
                "关键事件研究员",
                all_roles,
                ["三、月度关键市场信息解读"],
                (
                    "只选 1-3 条中长期影响最大的事件；每条固定写事件本质、"
                    "传导逻辑、业务启示；每条至少把一个真实原文链接嵌入"
                    "“主体+动作”的事实语句，不使用“原文、来源、详情”等链接文字。"
                ),
            ),
            (
                "风险跟踪研究员",
                all_roles,
                ["四、下月跟踪重点与风险提示"],
                "写 3-4 个重点跟踪变量和 2-3 个风险，注明观察信号、影响范围和触发条件。",
            ),
        ]

        async def build_section(
            index: int,
            role_name: str,
            roles: list[str],
            headings: list[str],
            section_instruction: str,
        ) -> tuple[str, str]:
            scoped = [
                item
                for item in materials
                if str((item.get("approval") or {}).get("role") or "行业") in roles
            ]
            if len(scoped) < 4:
                scoped = materials
            markdown, used_model = await self._invoke_markdown(
                stage=f"candidate_section_{index + 1}",
                system=f"你是{role_name}，只撰写分配给你的月报章节。",
                prompt=f"""
{MONTHLY_TEMPLATE_PROMPT}
公司：{company_name}
周期：{self._period_text(period_start, period_end)}
目标公司真实业务边界：{insight_company_business_context(company_name)}
只输出以下章节，必须使用 `# 序号、标题` 和必要的 `## 子标题`：
{json.dumps(headings, ensure_ascii=False)}
本章要求：{section_instruction}
补充要求：{prompt_override or "无"}
资料：
{json.dumps([self._compact_material(item, include_approval=True) for item in scoped], ensure_ascii=False, default=str)}
""",
                preferred_model=model_names[index % len(model_names)],
                stage_trace=stage_trace,
                enable_langfuse_callbacks=False,
            )
            return markdown, used_model

        tasks = {
            asyncio.create_task(
                build_section(index, role_name, roles, headings, section_instruction),
                name=f"monthly-section-{index + 1}",
            ): (index, role_name, roles, headings, section_instruction)
            for index, (role_name, roles, headings, section_instruction) in enumerate(section_specs)
        }
        done, pending = await asyncio.wait(tasks, timeout=330)
        completed_parts: dict[int, tuple[str, str]] = {}
        for task in done:
            index, role_name, _roles, _headings, _section_instruction = tasks[task]
            try:
                completed_parts[index] = task.result()
                logger.info("月报分章节生成完成: {}", role_name)
            except Exception as exc:
                logger.warning("月报分章节生成失败，将单独补写: {} - {}", role_name, exc)

        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
            logger.warning("月报分章节并发收束超时，待补写章节数: {}", len(pending))

        for task, (index, role_name, roles, headings, section_instruction) in tasks.items():
            if index in completed_parts:
                continue
            logger.info("开始单独补写月报章节: {}", role_name)
            completed_parts[index] = await build_section(
                index,
                role_name,
                roles,
                headings,
                section_instruction,
            )

        parts = [completed_parts[index] for index in range(len(section_specs))]
        title_block = self._header(company_name, period_start, period_end, len(materials))
        markdown = title_block + "\n\n" + "\n\n".join(part[0] for part in parts)
        markdown = self._order_sections(markdown)
        return MonthlyCandidate(
            strategy_code="section_parallel",
            strategy_name="分章节并行研究",
            markdown=self._sanitize_markdown(markdown, materials),
            models=list(dict.fromkeys(part[1] for part in parts)),
            stage_notes=[
                "核心总览、五维趋势、关键事件、下月跟踪由独立研究角色并行撰写，再按领导模板合并。"
            ],
        )

    async def _generate_multi_agent(
        self,
        *,
        company_name: str,
        period_start: datetime,
        period_end: datetime,
        materials: list[dict[str, Any]],
        prompt_override: str | None,
        model_names: list[str],
        stage_trace: list[dict[str, Any]],
    ) -> MonthlyCandidate:
        plan, planner_model = await self._invoke_json(
            stage="candidate_multi_agent_plan",
            system="你是月报研究总监，只制定基于证据的研究计划并输出 JSON。",
            prompt=f"""
为 {company_name} 制定 {self._period_text(period_start, period_end)} 月报研究计划。
{MONTHLY_TEMPLATE_PROMPT}
目标公司真实业务边界：{insight_company_business_context(company_name)}
输出 JSON：research_questions、company_clusters、cross_month_signals、section_outline、
evidence_requirements、known_gaps。不得写正式报告。
资料：{json.dumps([self._compact_material(item, include_approval=True) for item in materials], ensure_ascii=False, default=str)}
""",
            preferred_model=model_names[1 % len(model_names)],
            stage_trace=stage_trace,
        )
        draft, writer_model = await self._invoke_markdown(
            stage="candidate_multi_agent_draft",
            system="你是资深产业研究员，根据研究总监计划和已审批证据形成完整月报。",
            prompt=self._draft_prompt(
                company_name=company_name,
                period_start=period_start,
                period_end=period_end,
                materials=materials,
                prompt_override=prompt_override,
                instruction=f"研究总监计划：{json.dumps(plan, ensure_ascii=False)}",
            ),
            preferred_model=model_names[2 % len(model_names)],
            stage_trace=stage_trace,
        )
        critique, critic_model = await self._invoke_json(
            stage="candidate_multi_agent_critique",
            system="你是独立月报审稿人，只输出 JSON，不重写报告。",
            prompt=f"""
审查以下月报草稿是否存在事实越界、弱相关、遗漏重点、新闻拼接、深度不足和结构不符合模板。
只返回 JSON：blocking_issues、important_omissions、depth_improvements、structure_fixes、
facts_to_recheck、strengths。
草稿：{draft}
资料：{json.dumps([self._compact_material(item, include_approval=True) for item in materials], ensure_ascii=False, default=str)}
""",
            preferred_model=model_names[3 % len(model_names)],
            stage_trace=stage_trace,
        )
        revised, editor_model = await self._invoke_markdown(
            stage="candidate_multi_agent_revision",
            system="你是管理层月报终稿编辑，只按审稿意见修订，不增加资料外事实。",
            prompt=f"""
{MONTHLY_TEMPLATE_PROMPT}
公司：{company_name}
周期：{self._period_text(period_start, period_end)}
目标公司真实业务边界：{insight_company_business_context(company_name)}
审稿意见：{json.dumps(critique, ensure_ascii=False)}
原稿：{draft}
资料：{json.dumps([self._compact_material(item, include_approval=True) for item in materials], ensure_ascii=False, default=str)}
返回完整 Markdown。
""",
            preferred_model=model_names[0],
            stage_trace=stage_trace,
        )
        revised = self._ensure_monthly_header(
            self._sanitize_markdown(revised, materials),
            company_name=company_name,
            period_start=period_start,
            period_end=period_end,
            material_count=len(materials),
        )
        return MonthlyCandidate(
            strategy_code="multi_agent",
            strategy_name="多智能体研究与编辑",
            markdown=revised,
            models=list(dict.fromkeys([planner_model, writer_model, critic_model, editor_model])),
            stage_notes=[
                "研究总监先制定问题与证据计划。",
                "产业研究员按计划形成初稿。",
                "独立审稿人检查事实、相关度、遗漏和深度。",
                "终稿编辑仅依据资料与审稿意见修订。",
            ],
        )

    async def _review_candidate(
        self,
        candidate: MonthlyCandidate,
        *,
        company_name: str,
        period_start: datetime,
        period_end: datetime,
        materials: list[dict[str, Any]],
        model_names: list[str],
        stage_trace: list[dict[str, Any]],
    ) -> None:
        candidate.reviews = await self._run_review_panel(
            markdown=candidate.markdown,
            company_name=company_name,
            period_start=period_start,
            period_end=period_end,
            materials=materials,
            model_names=model_names,
            stage_trace=stage_trace,
            stage_prefix=f"review_{candidate.strategy_code}",
        )
        candidate.score = self._review_score(candidate.reviews)

    async def _run_review_panel(
        self,
        *,
        markdown: str,
        company_name: str,
        period_start: datetime,
        period_end: datetime,
        materials: list[dict[str, Any]],
        model_names: list[str],
        stage_trace: list[dict[str, Any]],
        stage_prefix: str,
    ) -> list[dict[str, Any]]:
        compact = [self._compact_material(item, include_approval=True) for item in materials]
        roles = [
            (
                "事实与幻觉核验员",
                "逐项检查报告数字、日期、主体、动作和链接是否可在资料中找到；尤其检查计划被写成结果、传闻被写成事实。",
            ),
            (
                "业务相关度审核员",
                "检查内容与目标公司产品、客户、竞对、原料、技术和监管是否直接相关，弱关联信息不得占主要篇幅。",
            ),
            (
                "管理层报告编辑",
                (
                    "检查报告深度、五维趋势、关键事件三段式分析、下月跟踪、"
                    "可读性、模板一致性和新闻标题拼接问题。"
                ),
            ),
        ]

        async def review(index: int, role: str, instruction: str) -> dict[str, Any]:
            payload, used_model = await self._invoke_json(
                stage=f"{stage_prefix}_{index + 1}",
                system=f"你是{role}，独立审查，不为原稿辩护，只输出 JSON。",
                prompt=f"""
当前系统日期：{datetime.now():%Y年%m月%d日}。这是闭卷证据审核：
- 已审批资料是本次审核的事实基准，即使其日期晚于模型训练知识截止时间，也不得因此判为未来、虚构或不可核实。
- 不调用模型记忆或外部常识否定资料中的事件，只核对报告是否忠实表达给定资料。
- 只有报告出现资料中不存在、与资料冲突或把计划写成既成结果的内容，才属于事实/幻觉问题。

目标公司：{company_name}
报告周期：{self._period_text(period_start, period_end)}
目标公司真实业务边界：{insight_company_business_context(company_name)}
职责：{instruction}
按 0-100 评分并输出 JSON：
{{
  "review_role": "{role}",
  "fact_score": 0,
  "relevance_score": 0,
  "depth_score": 0,
  "structure_score": 0,
  "readability_score": 0,
  "citation_score": 0,
  "hallucination_risk": "低|中|高",
  "blocking_issues": ["只有必须阻止发布的问题"],
  "important_issues": ["需要改进的问题"],
  "strengths": ["优点"],
  "revision_advice": ["可执行修订要求"]
}}
报告：{markdown}
已审批资料：{json.dumps(compact, ensure_ascii=False, default=str)}
""",
                preferred_model=model_names[index % len(model_names)],
                stage_trace=stage_trace,
                enable_reasoning=False,
                invocation_timeout_seconds=120,
            )
            payload["model"] = used_model
            payload["review_role"] = role
            return payload

        return list(
            await asyncio.gather(
                *[
                    review(index, role, instruction)
                    for index, (role, instruction) in enumerate(roles)
                ]
            )
        )

    async def _synthesize_final(
        self,
        *,
        candidates: list[MonthlyCandidate],
        company_name: str,
        period_start: datetime,
        period_end: datetime,
        materials: list[dict[str, Any]],
        prompt_override: str | None,
        model_names: list[str],
        stage_trace: list[dict[str, Any]],
    ) -> tuple[str, dict[str, Any]]:
        candidate_summaries = [
            {
                "strategy_code": item.strategy_code,
                "strategy_name": item.strategy_name,
                "score": item.score,
                "reviews": item.reviews,
                "outline": re.findall(r"^#{1,2}\s+(.+)$", item.markdown, flags=re.MULTILINE),
                "excerpt": item.markdown[:6000],
            }
            for item in candidates
        ]
        judgment, judge_model = await self._invoke_json(
            stage="ensemble_judgment",
            system="你是月报总编辑，只比较候选稿并输出 JSON。",
            prompt=f"""
比较候选月报。不得只看平均分，还要优先事实可靠、相关度高、归并自然、月度纵深充分且符合领导模板的稿件。
输出 JSON：selected_strategy、ranking、selection_reason、must_keep、must_remove、synthesis_instructions。
候选：{json.dumps(candidate_summaries, ensure_ascii=False, default=str)}
""",
            preferred_model=model_names[-1],
            stage_trace=stage_trace,
        )
        selected_code = str(judgment.get("selected_strategy") or "")
        selected = next((item for item in candidates if item.strategy_code == selected_code), candidates[0])
        supporting = candidates[1] if len(candidates) > 1 and candidates[1] is not selected else None
        final_markdown, editor_model = await self._invoke_markdown(
            stage="ensemble_final_synthesis",
            system="你是月报总编辑。以最佳候选为主稿，只吸收其他候选中有资料支持的优点，形成发布终稿。",
            prompt=f"""
{MONTHLY_TEMPLATE_PROMPT}
公司：{company_name}
周期：{self._period_text(period_start, period_end)}
目标公司真实业务边界：{insight_company_business_context(company_name)}
补充要求：{prompt_override or "无"}
评选意见：{json.dumps(judgment, ensure_ascii=False)}
主稿：{selected.markdown}
参考稿：{supporting.markdown if supporting else "无"}
已审批资料：{json.dumps([self._compact_material(item, include_approval=True) for item in materials], ensure_ascii=False, default=str)}
返回完整 Markdown。不得输出评选过程、模型名称或评分。
""",
            preferred_model=model_names[0],
            stage_trace=stage_trace,
        )
        selection = {
            "judge_model": judge_model,
            "editor_model": editor_model,
            "selected_strategy": selected.strategy_code,
            "selected_strategy_name": selected.strategy_name,
            "judgment": judgment,
        }
        return self._sanitize_markdown(final_markdown, materials), selection

    async def _repair_final(
        self,
        *,
        markdown: str,
        reviews: list[dict[str, Any]],
        company_name: str,
        period_start: datetime,
        period_end: datetime,
        materials: list[dict[str, Any]],
        model_name: str,
        stage_trace: list[dict[str, Any]],
    ) -> str:
        repaired, _used_model = await self._invoke_markdown(
            stage="final_repair",
            system="你是月报发布前终审编辑，只修正审校问题，不增加资料外事实。",
            prompt=f"""
{MONTHLY_TEMPLATE_PROMPT}
公司：{company_name}
周期：{self._period_text(period_start, period_end)}
目标公司真实业务边界：{insight_company_business_context(company_name)}
终审意见：{json.dumps(reviews, ensure_ascii=False)}
原稿：{markdown}
已审批资料：{json.dumps([self._compact_material(item, include_approval=True) for item in materials], ensure_ascii=False, default=str)}
返回完整 Markdown。
""",
            preferred_model=model_name,
            stage_trace=stage_trace,
        )
        return self._ensure_monthly_header(
            self._sanitize_markdown(repaired, materials),
            company_name=company_name,
            period_start=period_start,
            period_end=period_end,
            material_count=len(materials),
        )

    async def _invoke_json(
        self,
        *,
        stage: str,
        system: str,
        prompt: str,
        preferred_model: str,
        stage_trace: list[dict[str, Any]],
        enable_reasoning: bool = True,
        invocation_timeout_seconds: float = 180,
    ) -> tuple[dict[str, Any], str]:
        started = datetime.now()
        response = await LLMFactory.safe_invoke(
            [SystemMessage(content=system), HumanMessage(content=prompt)],
            capability="complex-reasoning",
            preferred_model_names=[preferred_model],
            temperature=0,
            json_mode=True,
            enable_reasoning=enable_reasoning,
            max_retries=3,
            invocation_timeout_seconds=invocation_timeout_seconds,
            langfuse_run_name=f"insight_monthly_{stage}",
            langfuse_tags=["insight", "feishu_monthly", stage],
        )
        used_model = self._response_model(response, preferred_model)
        payload = self._parse_json(getattr(response, "content", str(response)))
        stage_trace.append(
            {
                "stage": stage,
                "model": used_model,
                "status": "success",
                "duration_ms": int((datetime.now() - started).total_seconds() * 1000),
            }
        )
        return payload, used_model

    async def _invoke_markdown(
        self,
        *,
        stage: str,
        system: str,
        prompt: str,
        preferred_model: str,
        stage_trace: list[dict[str, Any]],
        enable_langfuse_callbacks: bool = True,
    ) -> tuple[str, str]:
        started = datetime.now()
        response = await LLMFactory.safe_invoke(
            [SystemMessage(content=system), HumanMessage(content=prompt)],
            capability="complex-reasoning",
            preferred_model_names=[preferred_model],
            temperature=0.12,
            enable_reasoning=True,
            max_retries=3,
            invocation_timeout_seconds=300,
            enable_langfuse_callbacks=enable_langfuse_callbacks,
            langfuse_run_name=f"insight_monthly_{stage}",
            langfuse_tags=["insight", "feishu_monthly", stage],
        )
        used_model = self._response_model(response, preferred_model)
        markdown = self._clean_markdown(getattr(response, "content", str(response)))
        stage_trace.append(
            {
                "stage": stage,
                "model": used_model,
                "status": "success",
                "duration_ms": int((datetime.now() - started).total_seconds() * 1000),
            }
        )
        return markdown, used_model

    def _draft_prompt(
        self,
        *,
        company_name: str,
        period_start: datetime,
        period_end: datetime,
        materials: list[dict[str, Any]],
        prompt_override: str | None,
        instruction: str,
    ) -> str:
        return f"""
{MONTHLY_TEMPLATE_PROMPT}
公司：{company_name}
周期：{self._period_text(period_start, period_end)}
目标公司真实业务边界：{insight_company_business_context(company_name)}
任务：{instruction}
补充要求：{prompt_override or "无"}

输出 Markdown，正文必须以以下头部和章节开始，不得增加技术性说明或其他主章节：
{self._header(company_name, period_start, period_end, len(materials))}

{chr(10).join(f"# {section}" for section in MONTHLY_SECTIONS)}

第二章必须包含政策、竞对、客户、技术、原料五个二级标题，并在每个维度写趋势判断、核心佐证、
业务影响。第三章只选 1-3 条关键事件，每条写事件本质、传导逻辑、业务启示。引用必须使用语义链接。
已审批资料：
{json.dumps([self._compact_material(item, include_approval=True) for item in materials], ensure_ascii=False, default=str)}
"""

    def _header(
        self,
        company_name: str,
        period_start: datetime,
        period_end: datetime,
        material_count: int,
    ) -> str:
        generated_at = datetime.now()
        return (
            f"管理层月度市场信息报告｜{self._period_text(period_start, period_end)}｜"
            f"生成时间：{generated_at.year}年{generated_at.month}月{generated_at.day}日\n\n"
            f"适用公司：{company_name}｜资料范围：正式情报｜审批后素材 {material_count} 条\n\n---"
        )

    def _title(self, company_name: str, period_end: datetime) -> str:
        short_name = "健源" if "健源" in company_name else "御馨" if "御馨" in company_name else company_name
        return f"{short_name}｜{period_end.year}年{period_end.month}月市场洞察月度报告"

    def _sanitize_markdown(
        self,
        markdown: str,
        materials: list[dict[str, Any]],
    ) -> str:
        markdown = self._clean_markdown(markdown)
        allowed_urls = {
            str(item.get("source_url") or "").strip()
            for item in materials
            if item.get("source_url")
        }

        def replace(match: re.Match[str]) -> str:
            label = match.group(1).strip()
            url = match.group(2).strip()
            if url not in allowed_urls:
                return label
            return f"[{label}]({url})"

        markdown = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", replace, markdown)
        markdown = re.sub(r"(?<!\]\()https?://[^\s)]+", "", markdown)
        return self._normalize_monthly_subheadings(self._order_sections(markdown))

    def _normalize_monthly_subheadings(self, markdown: str) -> str:
        dimensions = {"1": "政策", "2": "竞对", "3": "客户", "4": "技术", "5": "原料"}
        normalized_lines: list[str] = []
        for line in markdown.splitlines():
            stripped = line.strip()
            plain = re.sub(r"[*_`#]", "", stripped).strip()
            match = re.match(r"^([1-5])[.、]\s*(政策|竞对|客户|技术|原料)(?:\s*[（(].{0,20}[）)])?$", plain)
            if match and dimensions.get(match.group(1)) == match.group(2):
                normalized_lines.append(f"## {match.group(1)}.{match.group(2)}")
                continue
            if plain in {"重点跟踪方向", "1.重点跟踪方向", "1、重点跟踪方向"}:
                normalized_lines.append("## 1.重点跟踪方向")
                continue
            if plain in {"风险预警", "2.风险预警", "2、风险预警"}:
                normalized_lines.append("## 2.风险预警")
                continue
            normalized_lines.append(line)
        return "\n".join(normalized_lines)

    def _cross_company_material_reason(
        self,
        company_name: str,
        item: dict[str, Any],
    ) -> str | None:
        return insight_company_material_rejection_reason(company_name, item)

    def _order_sections(self, markdown: str) -> str:
        def normalize_heading(value: str) -> str:
            value = re.sub(r"[*_`#\s]+", "", value)
            return value.strip("：:。.")

        canonical = {
            normalize_heading(section): section
            for section in MONTHLY_SECTIONS
        }
        section_matches: list[tuple[re.Match[str], str]] = []
        for match in re.finditer(r"^(?:#{1,3}\s+)?(.+)$", markdown, flags=re.MULTILINE):
            normalized = normalize_heading(match.group(1))
            section = canonical.get(normalized)
            if section:
                section_matches.append((match, section))

        # 无法识别任何主章节时保留模型原稿，让确定性校验明确报错，
        # 不得把已有正文破坏性替换为“暂无信息”。
        if not section_matches:
            return markdown.strip()

        header = markdown[: section_matches[0][0].start()].strip()
        section_map: dict[str, str] = {}
        for index, (match, section) in enumerate(section_matches):
            end = (
                section_matches[index + 1][0].start()
                if index + 1 < len(section_matches)
                else len(markdown)
            )
            body_start = match.end()
            body = markdown[body_start:end].strip()
            section_map[section] = f"# {section}\n\n{body}".strip()

        parts = [header]
        for section in MONTHLY_SECTIONS:
            parts.append(section_map.get(section) or f"# {section}\n\n本月暂无经审批后可用于该章节的新增信息。")
        return "\n\n".join(part for part in parts if part).strip()

    def _ensure_monthly_header(
        self,
        markdown: str,
        *,
        company_name: str,
        period_start: datetime,
        period_end: datetime,
        material_count: int,
    ) -> str:
        if markdown.startswith("管理层月度市场信息报告｜"):
            return markdown
        if "管理层月度市场信息报告" in markdown[:300]:
            first_section = re.search(
                r"^#\s+一、月度核心总览\s*$",
                markdown,
                flags=re.MULTILINE,
            )
            if first_section:
                markdown = markdown[first_section.start() :]
        return (
            self._header(company_name, period_start, period_end, material_count)
            + "\n\n"
            + markdown.lstrip()
        )

    def _validate_monthly_markdown(
        self,
        markdown: str,
        materials: list[dict[str, Any]],
        *,
        company_name: str | None = None,
    ) -> list[str]:
        errors: list[str] = []
        positions = [markdown.find(f"# {section}") for section in MONTHLY_SECTIONS]
        if any(position < 0 for position in positions) or positions != sorted(positions):
            errors.append("月报章节缺失或顺序不符合模板")
        if not markdown.startswith("管理层月度市场信息报告｜"):
            errors.append("缺少月报固定头部")
        allowed_urls = {
            str(item.get("source_url") or "").strip()
            for item in materials
            if item.get("source_url")
        }
        output_urls = set(re.findall(r"https?://[^)\s]+", markdown))
        if output_urls - allowed_urls:
            errors.append("存在审批资料之外的链接")
        if re.search(r"(?<!\]\()https?://", markdown):
            errors.append("存在未嵌入事件短语的裸网址")
        link_labels = re.findall(r"\[([^\]]+)\]\(https?://[^)]+\)", markdown)
        if any(
            re.fullmatch(
                r"\s*(?:原文|来源|来源\d+|查看原文|详情|点击查看|报道|链接)\s*",
                label,
                flags=re.IGNORECASE,
            )
            for label in link_labels
        ):
            errors.append("存在“原文、来源、详情”等无语义链接文字")
        minimum_citations = min(8, len(allowed_urls))
        if len(output_urls) < minimum_citations:
            errors.append(f"报告引用覆盖不足（当前 {len(output_urls)}，最低 {minimum_citations}）")
        dimension_section = self._section_body(markdown, MONTHLY_SECTIONS[1])
        for dimension in ("政策", "竞对", "客户", "技术", "原料"):
            if not re.search(
                rf"^#{{2,3}}\s+\**\s*(?:\d+[.、]\s*)?{dimension}\s*\**\s*$",
                dimension_section,
                flags=re.MULTILINE,
            ):
                errors.append(f"五大维度缺少“{dimension}”")
        if dimension_section.count("趋势判断") < 5:
            errors.append("五大维度未逐项给出趋势判断")
        if dimension_section.count("核心佐证") < 5:
            errors.append("五大维度未逐项给出核心佐证")
        if dimension_section.count("业务影响") < 5:
            errors.append("五大维度未逐项给出业务影响")
        interpretation_section = self._section_body(markdown, MONTHLY_SECTIONS[2])
        interpretation_count = len(
            re.findall(r"^#{2,3}\s+.+$", interpretation_section, flags=re.MULTILINE)
        )
        if interpretation_count < 1 or interpretation_count > 3:
            errors.append("关键市场信息解读必须为 1-3 条")
        for label in ("事件本质", "传导逻辑", "业务启示"):
            if interpretation_section.count(label) < interpretation_count:
                errors.append(f"关键市场信息解读缺少“{label}”")
        interpretation_headings = list(
            re.finditer(r"^#{2,3}\s+.+$", interpretation_section, flags=re.MULTILINE)
        )
        for index, heading in enumerate(interpretation_headings, 1):
            body_start = heading.end()
            body_end = (
                interpretation_headings[index].start()
                if index < len(interpretation_headings)
                else len(interpretation_section)
            )
            subsection = interpretation_section[body_start:body_end]
            if not re.search(r"\[[^\]]+\]\(https?://[^)]+\)", subsection):
                errors.append(f"第 {index} 条关键市场信息解读缺少自然嵌入的原文链接")
        tracking_section = self._section_body(markdown, MONTHLY_SECTIONS[3])
        if "重点跟踪方向" not in tracking_section or "风险预警" not in tracking_section:
            errors.append("下月跟踪章节缺少重点跟踪方向或风险预警")
        forbidden = ("作为AI", "多智能体", "模型生成", "RAG", "素材ID", "证据ID")
        if any(value in markdown for value in forbidden):
            errors.append("报告正文包含内部技术或编号表达")
        if company_name:
            errors.extend(self._validate_company_focus(markdown, company_name))
        return errors

    @staticmethod
    def _validate_company_focus(markdown: str, company_name: str) -> list[str]:
        normalized = markdown.lower()
        if "健源" in company_name:
            own_terms = ("果葡糖浆", "麦芽糖浆", "淀粉糖", "功能糖", "糖醇", "玉米")
            mixed_terms = ("大豆蛋白", "植物蛋白", "豆粕", "豆油", "大豆油")
            if sum(normalized.count(term) for term in own_terms) < 3:
                return ["健源月报未充分围绕玉米深加工和糖类业务"]
            if any(term in normalized for term in mixed_terms):
                return ["健源月报混入御馨大豆或植物蛋白业务主线"]
        if "御馨" in company_name:
            own_terms = ("大豆", "植物蛋白", "大豆蛋白", "豆粕", "豆油")
            mixed_terms = ("果葡糖浆", "麦芽糖浆", "淀粉糖", "糖醇", "赤藓糖醇")
            if sum(normalized.count(term) for term in own_terms) < 3:
                return ["御馨月报未充分围绕大豆和植物蛋白业务"]
            if any(term in normalized for term in mixed_terms):
                return ["御馨月报混入健源糖浆或糖醇业务主线"]
        return []

    def _section_body(self, markdown: str, section: str) -> str:
        match = re.search(
            rf"^#\s+{re.escape(section)}\s*$",
            markdown,
            flags=re.MULTILINE,
        )
        if not match:
            return ""
        next_heading = re.search(r"^#\s+", markdown[match.end() :], flags=re.MULTILINE)
        end = match.end() + next_heading.start() if next_heading else len(markdown)
        return markdown[match.end() : end]

    def _review_score(self, reviews: list[dict[str, Any]]) -> float:
        scores: list[float] = []
        fields = (
            "fact_score",
            "relevance_score",
            "depth_score",
            "structure_score",
            "readability_score",
            "citation_score",
        )
        for review in reviews:
            values = []
            for field_name in fields:
                try:
                    values.append(float(review.get(field_name) or 0))
                except (TypeError, ValueError):
                    values.append(0)
            if values:
                scores.append(sum(values) / len(values))
        score = sum(scores) / len(scores) if scores else 0
        if self._blocking_issues(reviews):
            score -= 20
        return round(max(score, 0), 2)

    def _blocking_issues(self, reviews: list[dict[str, Any]]) -> list[str]:
        issues: list[str] = []
        for review in reviews:
            if str(review.get("hallucination_risk") or "").strip() == "高":
                issues.append(f"{review.get('review_role') or '审校'}判定幻觉风险高")
            for value in review.get("blocking_issues") or []:
                text = str(value).strip()
                if text:
                    issues.append(text[:300])
        return list(dict.fromkeys(issues))

    def _audit_markdown(
        self,
        *,
        company_name: str,
        period_start: datetime,
        period_end: datetime,
        original_count: int,
        approved_count: int,
        approval: dict[str, Any],
        candidates: list[MonthlyCandidate],
        final_reviews: list[dict[str, Any]],
        final_score: float,
        selection: dict[str, Any],
        stage_trace: list[dict[str, Any]],
    ) -> str:
        lines = [
            f"月报生成与审校记录｜{self._period_text(period_start, period_end)}",
            "",
            f"适用公司：{company_name}｜原始正式情报 {original_count} 条｜资料审批通过 {approved_count} 条",
            "",
            "---",
            "",
            "# 一、资料审批",
            "",
            f"资料审批模型：{'、'.join(approval.get('models') or []) or '--'}。",
            f"审批通过 {approved_count} 条，排除 {approval.get('rejected_count', 0)} 条。",
        ]
        gaps = approval.get("coverage_gaps") or []
        if gaps:
            lines.extend(["", "## 资料缺口", "", "；".join(str(value) for value in gaps)])
        lines.extend(["", "# 二、候选策略对比", ""])
        for index, candidate in enumerate(candidates, 1):
            lines.extend(
                [
                    f"## {index}. {candidate.strategy_name}",
                    "",
                    f"综合评分：{candidate.score:.1f}｜参与模型：{'、'.join(candidate.models)}",
                    "",
                    "优势：" + "；".join(
                        str(value)
                        for review in candidate.reviews
                        for value in (review.get("strengths") or [])[:2]
                    )[:1000],
                    "",
                    "主要问题：" + "；".join(
                        str(value)
                        for review in candidate.reviews
                        for value in (review.get("important_issues") or review.get("blocking_issues") or [])[:2]
                    )[:1200],
                ]
            )
        lines.extend(
            [
                "",
                "# 三、终稿选择",
                "",
                f"主稿策略：{selection.get('selected_strategy_name') or selection.get('selected_strategy')}",
                f"评选模型：{selection.get('judge_model')}｜终稿编辑：{selection.get('editor_model')}",
                f"终稿综合评分：{final_score:.1f}",
                "",
                "# 四、终稿审核",
                "",
            ]
        )
        for review in final_reviews:
            lines.extend(
                [
                    f"## {review.get('review_role') or '审核'}",
                    "",
                    f"模型：{review.get('model') or '--'}｜幻觉风险：{review.get('hallucination_risk') or '--'}",
                    "；".join(str(value) for value in (review.get("important_issues") or review.get("strengths") or []))[:1000],
                ]
            )
        lines.extend(["", "# 五、生成过程", ""])
        for index, stage in enumerate(stage_trace, 1):
            lines.append(
                f"{index}. {stage.get('stage')}｜{stage.get('model')}｜"
                f"{stage.get('duration_ms', 0) / 1000:.1f} 秒｜{stage.get('status')}"
            )
        return "\n".join(lines)

    def _compact_material(
        self,
        item: dict[str, Any],
        *,
        include_approval: bool = False,
    ) -> dict[str, Any]:
        result = {
            "id": item.get("id"),
            "title": item.get("title"),
            "summary": str(item.get("summary") or "")[:1200],
            "content_excerpt": str(item.get("content") or "")[:1200],
            "publish_time": item.get("publish_time"),
            "subject_name": item.get("subject_name"),
            "category": item.get("category"),
            "tags": item.get("tags") or [],
            "selection_reason": str(item.get("selection_reason") or "")[:500],
            "business_insight": str(item.get("business_insight") or "")[:500],
            "source_channel": item.get("source_channel"),
            "source_url": item.get("source_url"),
        }
        if include_approval:
            result["approval"] = item.get("approval")
        return result

    @staticmethod
    def _parse_json(value: Any) -> dict[str, Any]:
        text = str(value or "").strip()
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text).strip()
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("月报模型未返回 JSON 对象")
        payload = json.loads(text[start : end + 1])
        if not isinstance(payload, dict):
            raise ValueError("月报模型返回的不是 JSON 对象")
        return payload

    @staticmethod
    def _clean_markdown(value: Any) -> str:
        text = str(value or "").strip()
        text = re.sub(r"^```(?:markdown)?\s*", "", text, flags=re.IGNORECASE)
        return re.sub(r"\s*```$", "", text).strip()

    @staticmethod
    def _response_model(response: Any, fallback: str) -> str:
        metadata = getattr(response, "response_metadata", None)
        if isinstance(metadata, dict) and metadata.get("selected_model_name"):
            return str(metadata["selected_model_name"])
        return fallback

    @staticmethod
    def _period_text(start: datetime, end: datetime) -> str:
        if start.year == end.year and start.month == end.month:
            return f"{start.year}年{start.month}月{start.day}日至{end.day}日"
        return f"{start:%Y年%m月%d日}至{end:%Y年%m月%d日}"


insight_feishu_monthly_report_service = InsightFeishuMonthlyReportService()
