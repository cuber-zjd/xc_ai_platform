from __future__ import annotations

import asyncio
import calendar
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

import httpx
from langchain_core.messages import HumanMessage, SystemMessage
from sqlmodel import func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.llm_factory import LLMFactory
from app.models.agent.insight import InsightFeishuBriefPlan, InsightFeishuBriefRun, InsightIntelligence
from app.models.system.sys_company import SysCompany
from app.schemas.agent.insight.feishu_brief import (
    InsightFeishuBriefDueRunResponse,
    InsightFeishuBriefGenerationRules,
    InsightFeishuBriefOptionsRead,
    InsightFeishuBriefPlanCreate,
    InsightFeishuBriefPlanRead,
    InsightFeishuBriefPlanUpdate,
    InsightFeishuBriefRecipient,
    InsightFeishuBriefRunRead,
    InsightFeishuBriefRunRequest,
    InsightFeishuBriefRunResponse,
)
from app.schemas.page import Page
from app.services.agent.insight.feishu_bitable_service import insight_feishu_bitable_service
from app.services.agent.insight.feishu_monthly_report_service import (
    insight_feishu_monthly_report_service,
)
from app.services.agent.insight.company_context import (
    insight_company_business_context,
    insight_company_material_rejection_reason,
)


FIXED_FORMAT = [
    "一、总览",
    "政策",
    "竞对",
    "客户",
    "技术",
    "原料",
    "二、重点情报导读（固定 7 条）",
]

UNSUPPORTED_INFERENCE_PATTERNS = (
    r"(?:预计|将)(?:在)?(?:短期内)?(?:显著|直接)?(?:增加|拉动|带动)[^。\n]{0,35}(?:采购需求|原料需求)",
    r"(?:采购需求|原料需求)[^。\n]{0,18}(?:将|预计)[^。\n]{0,12}(?:增长|增加|收缩|下降|减少)",
    r"直接(?:带动|挤压|影响)[^。\n]{0,35}(?:需求|份额|销量|营收|格局)",
    r"直接指向[^。\n]{0,35}(?:新增采购|采购需求|销售机会)",
    r"(?:导致|拖累)[^。\n]{0,30}(?:销量|销售额|营收)(?:下滑|下降)",
    r"(?:最佳|明确的)(?:销售|市场|研发|供应链)?(?:契机|机会)",
    r"(?:直接拉动|意味着|代表)[^。\n]{0,45}(?:新增采购需求|采购需求|原料需求)",
    r"(?:提供了?|形成了?)[^。\n]{0,35}(?:明确的)?(?:销售跟进线索|原料应用场景)",
)

IMPLICIT_ADVICE_PATTERNS = (
    r"(?:香驰|我司|公司)(?:需|应当|应该|可考虑|必须)",
    r"(?<!无)需(?:关注|警惕|评估|调整|跟进|应对|建立|加强|优化)",
    r"(?:建议|应当|应该)(?:关注|评估|调整|跟进|建立|加强|优化)",
    r"(?:值得关注|需严格|需及时|需持续|需重点)",
)

APPROVED_STYLE_EXAMPLES = """
以下内容摘自领导已经确认的正式报告，只用于约束写法和版式。必须模仿其信息密度、句式和链接位置，
不得照抄其中事实，也不得把样例中的企业和数字带入新报告。

【分类正文样例】
# 竞对

玉米深加工竞对出现利润承压与产能扩张并行的分化。部分企业因原料上涨而产品售价传导不足，
但仍在[推进液体糖浆和晶体糖醇新增能力](https://example.com/a)，反映行业在短期盈利承压下继续
向高附加值产品延伸。与此同时，竞对的客户突破和技术品牌化也在加快，
[从原料销售延伸至应用方案](https://example.com/b)成为较为一致的经营动作。

这里的链接文字是从事件中提炼出的短语，不是文章原标题。段落先说明共同变化，再把多个来源作为证据
融入同一条叙述，不按“文章甲说……；文章乙说……”逐条罗列。

【重点情报导读样例】
## [1. 茶饮客户健康新品短期形成爆款](https://example.com/c)

客户　爆款新品

某茶饮品牌推出健康原料新品，中杯价格处于主流价格带，上线后短期销量快速增长。
产品采用订单农业和全程冷链，并延续品牌既有产品矩阵。该信息的写法只陈述公开事实、
产品构成、销量、产能或经营动作，不额外添加“建议”“启示”“机会”“风险”等段落。
"""

PROMPT_TEMPLATE_DISPLAY = f"""你是香驰控股管理层情报简报撰写人员。领导已经确定报告格式，必须严格套用。
只使用给定周期内的正式情报，不得虚构事实、数字、企业动作、来源或链接；相同事件先归并。

固定版式：
文档标题：{{公司简称}}｜{{年份}}年{{月份}}月第{{周次}}周信息简报
管理层情报简报｜{{素材开始日期}}至{{素材结束日期}}｜生成时间：{{生成日期}}
适用公司：{{所属公司}}｜数据来源：情报管理多维表格·情报表｜原始候选 {{素材数量}} 条
# 一、总览
# 政策
# 竞对
# 客户
# 技术
# 原料
# 二、重点情报导读

写作要求：
1. 每段先概括共同变化，再融合 2 至 4 条材料，不按文章顺序逐条拼接。
2. 超链接挂在事件、项目、产品或经营动作短语上，作为句子的组成部分。
3. 不显示裸网址，不照搬冗长原文标题，不单独列时间、内容、来源、启示或建议。
4. 明显属于历史旧闻且本周期没有新进展的材料不得采用。
5. 重点情报导读固定 7 条，标题重新概括事件，正文保留主体、动作、数字和业务背景。
6. 生成前按公司业务边界进行独立选材，低相关旧闻、广告、榜单、包装外观专利和通用设备专利不用于凑数。
7. 初稿需通过业务相关性终审；不得把“可能相关”夸大为“直接拉动需求”。
8. 原文没有明确采购、销量或经营结果时，只能写“可能影响”“值得关注”，不得写成“将显著增加采购需求”
   “直接指向新增采购”“必然带动销量”或擅自归因某家公司业绩下滑。
9. 导读标题使用正式、克制的管理语言，只概括材料明确披露的主体和动作；不用“死磕、引爆、撬动、倒逼”
   等媒体化词语，也不把潜在影响压缩成“收缩外采、致战略延缓”等确定结论。
10. 全文只写事实，不以“香驰需、我司应、需关注、需警惕、建议”等方式夹带行动建议；也不得断言未来
    采购需求一定增加、收缩或下降。

{APPROVED_STYLE_EXAMPLES.strip()}"""


@dataclass(frozen=True)
class BriefFolderResolution:
    token: str
    path: str
    organized: bool
    warning: str | None = None


class InsightFeishuBriefService:
    """独立于报告中心的飞书机器人简报服务。"""

    def __init__(self) -> None:
        self._tenant_token: str | None = None
        self._tenant_token_expires_at = 0.0
        self._folder_cache: dict[tuple[str, str], str] = {}
        self._folder_lock = asyncio.Lock()

    def get_options(self) -> InsightFeishuBriefOptionsRead:
        app_configured = bool(settings.INSIGHT_FEISHU_BRIEF_APP_ID and settings.INSIGHT_FEISHU_BRIEF_APP_SECRET)
        folder_configured = bool(settings.INSIGHT_FEISHU_BRIEF_FOLDER_TOKEN)
        recipients = self._default_recipients()
        warnings: list[str] = []
        if not settings.INSIGHT_FEISHU_BRIEF_ENABLED:
            warnings.append("独立飞书简报尚未启用")
        if not app_configured:
            warnings.append("请配置独立简报机器人的 App ID 和 App Secret")
        if not folder_configured:
            warnings.append("请配置机器人可写入的飞书云文档文件夹 Token")
        if not recipients:
            warnings.append("尚未配置默认接收人，可在计划中单独设置")
        return InsightFeishuBriefOptionsRead(
            enabled=settings.INSIGHT_FEISHU_BRIEF_ENABLED,
            configured=bool(settings.INSIGHT_FEISHU_BRIEF_ENABLED and app_configured and folder_configured),
            bot_name=settings.INSIGHT_FEISHU_BRIEF_BOT_NAME,
            folder_configured=folder_configured,
            app_configured=app_configured,
            default_recipient_count=len(recipients),
            warnings=warnings,
            fixed_format=FIXED_FORMAT,
            prompt_template=PROMPT_TEMPLATE_DISPLAY,
        )

    async def list_plans(
        self,
        db: AsyncSession,
        *,
        page: int,
        size: int,
        status: str | None = None,
    ) -> Page[InsightFeishuBriefPlanRead]:
        page = max(page, 1)
        size = min(max(size, 1), 100)
        filters = [InsightFeishuBriefPlan.is_deleted == 0]
        if status:
            filters.append(InsightFeishuBriefPlan.status == status)
        total = (await db.exec(select(func.count()).select_from(InsightFeishuBriefPlan).where(*filters))).one()
        rows = list(
            (
                await db.exec(
                    select(InsightFeishuBriefPlan)
                    .where(*filters)
                    .order_by(InsightFeishuBriefPlan.next_run_time.asc().nullslast(), InsightFeishuBriefPlan.id.desc())
                    .offset((page - 1) * size)
                    .limit(size)
                )
            ).all()
        )
        companies = await self._company_names(db, [row.sys_company_id for row in rows if row.sys_company_id])
        return Page.create(
            items=[self._plan_read(row, companies.get(row.sys_company_id)) for row in rows],
            total=total,
            page=page,
            size=size,
        )

    async def list_runs(
        self,
        db: AsyncSession,
        *,
        page: int,
        size: int,
        plan_id: int | None = None,
    ) -> Page[InsightFeishuBriefRunRead]:
        page = max(page, 1)
        size = min(max(size, 1), 100)
        filters = [InsightFeishuBriefRun.is_deleted == 0]
        if plan_id:
            filters.append(InsightFeishuBriefRun.plan_id == plan_id)
        total = (await db.exec(select(func.count()).select_from(InsightFeishuBriefRun).where(*filters))).one()
        rows = list(
            (
                await db.exec(
                    select(InsightFeishuBriefRun)
                    .where(*filters)
                    .order_by(InsightFeishuBriefRun.id.desc())
                    .offset((page - 1) * size)
                    .limit(size)
                )
            ).all()
        )
        return Page.create(items=[self._run_read(row) for row in rows], total=total, page=page, size=size)

    async def create_plan(
        self,
        db: AsyncSession,
        payload: InsightFeishuBriefPlanCreate,
        *,
        user_id: int,
    ) -> InsightFeishuBriefPlanRead:
        company = await self._require_company(db, payload.sys_company_id)
        row = InsightFeishuBriefPlan(
            plan_uid=f"feishu_brief_{uuid4().hex}",
            plan_name=payload.plan_name.strip(),
            sys_company_id=payload.sys_company_id,
            schedule_frequency=payload.schedule_frequency,
            weekday=payload.weekday,
            day_of_month=payload.day_of_month,
            time_of_day=payload.time_of_day,
            material_days=payload.material_days,
            max_materials=payload.max_materials,
            generation_strategy=payload.generation_strategy,
            prompt_override=payload.prompt_override,
            generation_rules_json=payload.generation_rules.model_dump(mode="json"),
            recipients_json=[item.model_dump(mode="json") for item in payload.recipients],
            afternoon_recipients_json=[
                item.model_dump(mode="json") for item in payload.afternoon_recipients
            ],
            afternoon_push_time=payload.afternoon_push_time,
            next_run_time=self._next_run_time(
                payload.schedule_frequency,
                payload.time_of_day,
                payload.weekday,
                payload.day_of_month,
            ),
            status=payload.status,
            create_by=str(user_id),
            update_by=str(user_id),
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return self._plan_read(row, company.name if company else None)

    async def update_plan(
        self,
        db: AsyncSession,
        plan_id: int,
        payload: InsightFeishuBriefPlanUpdate,
        *,
        user_id: int,
    ) -> InsightFeishuBriefPlanRead:
        row = await self._require_plan(db, plan_id)
        data = payload.model_dump(exclude_unset=True, mode="json")
        if "sys_company_id" in data:
            await self._require_company(db, data["sys_company_id"])
        if "recipients" in data:
            data["recipients_json"] = data.pop("recipients")
        if "afternoon_recipients" in data:
            data["afternoon_recipients_json"] = data.pop("afternoon_recipients")
        if "generation_rules" in data:
            data["generation_rules_json"] = data.pop("generation_rules")
        for key, value in data.items():
            setattr(row, key, value)
        row.next_run_time = self._next_run_time(
            row.schedule_frequency,
            row.time_of_day,
            row.weekday,
            row.day_of_month,
        )
        row.update_by = str(user_id)
        row.update_time = datetime.now()
        db.add(row)
        await db.commit()
        await db.refresh(row)
        company = await db.get(SysCompany, row.sys_company_id) if row.sys_company_id else None
        return self._plan_read(row, company.name if company else None)

    async def delete_plan(self, db: AsyncSession, plan_id: int, *, user_id: int) -> None:
        row = await self._require_plan(db, plan_id)
        row.is_deleted = 1
        row.status = "deleted"
        row.update_by = str(user_id)
        row.update_time = datetime.now()
        db.add(row)
        await db.commit()

    async def run_plan(
        self,
        db: AsyncSession,
        plan_id: int,
        *,
        trigger_type: str = "manual",
        run_request: InsightFeishuBriefRunRequest | None = None,
    ) -> InsightFeishuBriefRunResponse:
        plan = await self._require_plan(db, plan_id)
        options = self.get_options()
        if not options.configured:
            raise ValueError("独立飞书简报机器人尚未配置完整")
        execution_started_at = datetime.now()
        period_reference = (
            run_request.period_end
            if run_request and run_request.period_end
            else execution_started_at
        )
        period_start, period_end = self._period_bounds(
            plan,
            now=period_reference,
            trigger_type=trigger_type,
            requested_start=run_request.period_start if run_request else None,
        )
        run = InsightFeishuBriefRun(
            run_uid=f"feishu_brief_run_{uuid4().hex}",
            plan_id=plan.id or 0,
            trigger_type=trigger_type,
            status="running",
            period_start=period_start,
            period_end=period_end,
            started_at=execution_started_at,
        )
        db.add(run)
        await db.flush()
        if self._is_scheduled_trigger(trigger_type):
            # 先持久化本周期占用，再执行建文档和消息发送。外部发送成功后即使数据库连接
            # 短暂中断，也不会因计划仍处于到期状态而自动重复发送。
            plan.last_run_time = execution_started_at
            plan.last_run_id = run.id
            plan.last_status = "running"
            plan.last_error = None
            plan.next_run_time = self._next_run_time(
                plan.schedule_frequency,
                plan.time_of_day,
                plan.weekday,
                plan.day_of_month,
                base=execution_started_at,
            )
            db.add(plan)
        await db.commit()
        await db.refresh(run)
        run_id = run.id or 0
        plan_id_value = plan.id or 0
        try:
            company = await self._require_company(db, plan.sys_company_id)
            company_name = company.name if company else "香驰控股"
            generation_rules = self._generation_rules(plan, company_name)
            effective_prompt_override = self._merge_rule_prompt(
                plan.prompt_override,
                generation_rules,
            )
            final_folder = await self._resolve_document_folder(
                company_name=company_name,
                frequency=plan.schedule_frequency,
                period_end=period_end,
                artifact_type="final",
            )
            process_folder = (
                await self._resolve_document_folder(
                    company_name=company_name,
                    frequency=plan.schedule_frequency,
                    period_end=period_end,
                    artifact_type="process",
                )
                if plan.schedule_frequency == "monthly"
                else final_folder
            )
            material_scan_limit = (
                1000
                if plan.schedule_frequency == "monthly"
                else min(plan.max_materials, settings.INSIGHT_FEISHU_BRIEF_MAX_MATERIALS)
            )
            materials = await self._load_materials(
                db,
                sys_company_id=plan.sys_company_id,
                period_start=period_start,
                period_end=period_end,
                limit=material_scan_limit,
            )
            minimum_materials = 10 if plan.schedule_frequency == "monthly" else 7
            if len(materials) < minimum_materials:
                raise ValueError(f"当前周期只有 {len(materials)} 条可用正式情报，不足以生成固定 7 条导读")
            pipeline_output: dict[str, Any]
            if plan.schedule_frequency == "monthly":
                monthly_result = await insight_feishu_monthly_report_service.generate(
                    db,
                    company_name=company_name,
                    period_start=period_start,
                    period_end=period_end,
                    materials=materials,
                    prompt_override=effective_prompt_override,
                    generation_strategy=plan.generation_strategy,
                )
                title = monthly_result.title
                markdown = monthly_result.markdown
                publish_candidates = not run_request or run_request.publish_candidate_documents
                artifacts: list[dict[str, Any]] = []
                if publish_candidates:
                    for index, candidate in enumerate(monthly_result.candidates, 1):
                        candidate_title = f"【候选方案{index}】{title}｜{candidate.strategy_name}"
                        candidate.document_id, candidate.document_url = await self._create_document(
                            candidate_title,
                            candidate.markdown,
                            folder_token=process_folder.token,
                        )
                        artifacts.append(
                            {
                                "artifact_type": "candidate",
                                "strategy_code": candidate.strategy_code,
                                "strategy_name": candidate.strategy_name,
                                "title": candidate_title,
                                "document_id": candidate.document_id,
                                "document_url": candidate.document_url,
                                "score": candidate.score,
                                "models": candidate.models,
                            }
                        )
                    audit_title = f"【生成与审校记录】{title}"
                    audit_document_id, audit_document_url = await self._create_document(
                        audit_title,
                        monthly_result.audit_markdown,
                        folder_token=process_folder.token,
                    )
                    artifacts.append(
                        {
                            "artifact_type": "audit",
                            "title": audit_title,
                            "document_id": audit_document_id,
                            "document_url": audit_document_url,
                        }
                    )
                pipeline_output = monthly_result.output_payload | {"artifacts": artifacts}
                used_material_count = int(
                    monthly_result.output_payload.get("material_approval", {}).get(
                        "approved_count",
                        len(materials),
                    )
                )
            else:
                selected_materials, selection_audit = await self._select_materials(
                    company_name=company_name,
                    period_start=period_start,
                    period_end=period_end,
                    materials=materials,
                    generation_rules=generation_rules,
                )
                if len(selected_materials) < 7:
                    raise ValueError(
                        f"当前周期有 {len(materials)} 条正式情报，但仅 {len(selected_materials)} 条"
                        "通过简报相关性审校，不足以生成固定 7 条导读"
                    )
                title, markdown = await self._generate_markdown(
                    company_name=company_name,
                    frequency=plan.schedule_frequency,
                    period_start=period_start,
                    period_end=period_end,
                    generated_at=execution_started_at,
                    materials=selected_materials,
                    original_material_count=len(materials),
                    prompt_override=effective_prompt_override,
                    generation_rules=generation_rules,
                )
                pipeline_output = {"material_selection": selection_audit}
                used_material_count = len(selected_materials)
            pipeline_output["document_folder"] = {
                "token": final_folder.token,
                "path": final_folder.path,
                "organized": final_folder.organized,
                "warning": final_folder.warning,
            }
            if process_folder.token != final_folder.token:
                pipeline_output["process_folder"] = {
                    "token": process_folder.token,
                    "path": process_folder.path,
                    "organized": process_folder.organized,
                    "warning": process_folder.warning,
                }
            document_id, document_url = await self._create_document(
                title,
                markdown,
                folder_token=final_folder.token,
            )
            recipients = self._recipients(plan)
            afternoon_recipients = self._afternoon_recipients(plan)
            should_push = not run_request or run_request.push_final
            morning_permission_result = (
                await self._grant_document_permission(document_id, recipients, permission="edit")
                if should_push and recipients
                else {"success_count": 0, "failed_count": 0, "results": []}
            )
            afternoon_permission_result = (
                await self._grant_document_permission(
                    document_id,
                    afternoon_recipients,
                    permission="view",
                )
                if should_push and afternoon_recipients
                else {"success_count": 0, "failed_count": 0, "results": []}
            )
            security_label_name = await self._document_security_label(document_id)
            push_result = (
                await self._push_document(
                    title,
                    document_url,
                    recipients,
                    stage="morning_review",
                )
                if should_push
                else {"success_count": 0, "failed_count": 0, "results": []}
            )
            finished = datetime.now()
            afternoon_scheduled_at = (
                self._same_day_time(finished, plan.afternoon_push_time)
                if should_push and afternoon_recipients
                else None
            )
            run.status = "success" if push_result["failed_count"] == 0 else "partial"
            run.material_count = used_material_count
            run.report_title = title
            run.document_id = document_id
            run.document_url = document_url
            run.pushed_count = push_result["success_count"]
            run.failed_push_count = push_result["failed_count"]
            run.afternoon_push_scheduled_at = afternoon_scheduled_at
            run.afternoon_push_status = "pending" if afternoon_scheduled_at else None
            run.content_markdown = markdown
            run.output_payload = {
                "morning_delivery": {
                    "recipients": [item.model_dump(mode="json") for item in recipients],
                    "permission_results": morning_permission_result,
                    "push_results": push_result,
                },
                "afternoon_delivery": {
                    "scheduled_at": afternoon_scheduled_at.isoformat() if afternoon_scheduled_at else None,
                    "recipients": [item.model_dump(mode="json") for item in afternoon_recipients],
                    "permission_results": afternoon_permission_result,
                    "status": "pending" if afternoon_scheduled_at else "disabled",
                },
                # 兼容已有执行记录读取方式。
                "push_results": push_result["results"],
                "bot_name": options.bot_name,
                "security_label_name": security_label_name,
                "security_label_status": "known" if security_label_name else "unknown",
                **pipeline_output,
            }
            run.finished_at = finished
            plan.last_run_time = finished
            plan.last_run_id = run.id
            plan.last_status = run.status
            plan.last_error = None
            plan.next_run_time = self._next_run_time(
                plan.schedule_frequency,
                plan.time_of_day,
                plan.weekday,
                plan.day_of_month,
                base=finished,
            )
            db.add(run)
            db.add(plan)
            await db.commit()
            await db.refresh(run)
            message = "飞书简报已生成"
            if should_push and recipients:
                message = "飞书简报已生成并发送给上午审阅组"
            if afternoon_scheduled_at:
                message += f"，下午 {plan.afternoon_push_time} 将发送同一云文档"
            return InsightFeishuBriefRunResponse(run=self._run_read(run), message=message)
        except Exception as exc:
            await db.rollback()
            failed_run = await db.get(InsightFeishuBriefRun, run_id)
            failed_plan = await db.get(InsightFeishuBriefPlan, plan_id_value)
            if failed_run:
                failed_run.status = "failed"
                failed_run.error_message = str(exc)[:2000]
                failed_run.finished_at = datetime.now()
                db.add(failed_run)
            if failed_plan:
                failed_plan.last_run_time = datetime.now()
                failed_plan.last_run_id = run_id
                failed_plan.last_status = "failed"
                failed_plan.last_error = str(exc)[:1000]
                failed_plan.next_run_time = self._next_run_time(
                    failed_plan.schedule_frequency,
                    failed_plan.time_of_day,
                    failed_plan.weekday,
                    failed_plan.day_of_month,
                )
                db.add(failed_plan)
            await db.commit()
            raise

    async def regenerate_run_in_place(
        self,
        db: AsyncSession,
        run_id: int,
    ) -> InsightFeishuBriefRunResponse:
        """重新生成既有周报并覆盖原云文档，不改变待推送文档链接。"""
        run = await db.get(InsightFeishuBriefRun, run_id)
        if not run or run.is_deleted:
            raise ValueError("飞书简报执行记录不存在")
        if not run.document_id or not run.document_url:
            raise ValueError("该执行记录尚未生成可覆盖的飞书云文档")
        plan = await self._require_plan(db, run.plan_id)
        if plan.schedule_frequency == "monthly":
            raise ValueError("月报暂不支持通过周报重生成接口覆盖")

        company = await self._require_company(db, plan.sys_company_id)
        company_name = company.name if company else "香驰控股"
        generation_rules = self._generation_rules(plan, company_name)
        materials = await self._load_materials(
            db,
            sys_company_id=plan.sys_company_id,
            period_start=run.period_start,
            period_end=run.period_end,
            limit=min(plan.max_materials, settings.INSIGHT_FEISHU_BRIEF_MAX_MATERIALS),
        )
        if len(materials) < 7:
            raise ValueError(f"当前周期只有 {len(materials)} 条可用正式情报，不足以重新生成")

        selected_materials, selection_audit = await self._select_materials(
            company_name=company_name,
            period_start=run.period_start,
            period_end=run.period_end,
            materials=materials,
            generation_rules=generation_rules,
        )
        if len(selected_materials) < 7:
            raise ValueError(
                f"当前周期有 {len(materials)} 条正式情报，但仅 {len(selected_materials)} 条通过相关性审校"
            )
        title, markdown = await self._generate_markdown(
            company_name=company_name,
            frequency=plan.schedule_frequency,
            period_start=run.period_start,
            period_end=run.period_end,
            generated_at=datetime.now(),
            materials=selected_materials,
            original_material_count=len(materials),
            prompt_override=self._merge_rule_prompt(plan.prompt_override, generation_rules),
            generation_rules=generation_rules,
        )
        await self._replace_document_content(run.document_id, markdown)

        output_payload = dict(run.output_payload or {})
        output_payload["material_selection"] = selection_audit
        output_payload["regeneration"] = {
            "regenerated_at": datetime.now().isoformat(),
            "original_document_preserved": True,
            "candidate_count": len(materials),
            "selected_count": len(selected_materials),
        }
        run.material_count = len(selected_materials)
        run.report_title = title
        run.content_markdown = markdown
        run.output_payload = output_payload
        run.error_message = None
        run.update_time = datetime.now()
        db.add(run)
        await db.commit()
        await db.refresh(run)
        return InsightFeishuBriefRunResponse(
            run=self._run_read(run),
            message="已重新生成并覆盖原飞书云文档，待推送链接保持不变",
        )

    async def run_due_plans(
        self,
        db: AsyncSession,
        *,
        limit: int = 10,
        trigger_type: str = "scheduler",
    ) -> InsightFeishuBriefDueRunResponse:
        if not self.get_options().configured:
            return InsightFeishuBriefDueRunResponse(checked_count=0, due_count=0, success_count=0, failed_count=0)
        now = datetime.now()
        rows = list(
            (
                await db.exec(
                    select(InsightFeishuBriefPlan)
                    .where(
                        InsightFeishuBriefPlan.is_deleted == 0,
                        InsightFeishuBriefPlan.status == "active",
                        InsightFeishuBriefPlan.next_run_time <= now,
                    )
                    .order_by(InsightFeishuBriefPlan.next_run_time.asc())
                    .limit(min(max(limit, 1), 50))
                )
            ).all()
        )
        results: list[dict[str, Any]] = []
        success_count = 0
        failed_count = 0
        for row in rows:
            try:
                result = await self.run_plan(db, row.id or 0, trigger_type=trigger_type)
                success_count += 1
                results.append({"plan_id": row.id, "status": result.run.status, "document_url": result.run.document_url})
            except Exception as exc:
                failed_count += 1
                results.append({"plan_id": row.id, "status": "failed", "error": str(exc)[:500]})
        return InsightFeishuBriefDueRunResponse(
            checked_count=len(rows),
            due_count=len(rows),
            success_count=success_count,
            failed_count=failed_count,
            results=results,
        )

    async def run_due_afternoon_pushes(
        self,
        db: AsyncSession,
        *,
        limit: int = 20,
    ) -> dict[str, Any]:
        """发送已经生成、允许上午修改后的同一篇云文档。"""
        now = datetime.now()
        rows = list(
            (
                await db.exec(
                    select(InsightFeishuBriefRun)
                    .where(
                        InsightFeishuBriefRun.is_deleted == 0,
                        InsightFeishuBriefRun.afternoon_push_status == "pending",
                        InsightFeishuBriefRun.afternoon_push_scheduled_at <= now,
                    )
                    .order_by(InsightFeishuBriefRun.afternoon_push_scheduled_at.asc())
                    .limit(min(max(limit, 1), 50))
                )
            ).all()
        )
        success_count = 0
        failed_count = 0
        results: list[dict[str, Any]] = []
        for row in rows:
            payload = dict(row.output_payload or {})
            delivery = dict(payload.get("afternoon_delivery") or {})
            recipients = [
                InsightFeishuBriefRecipient.model_validate(item)
                for item in delivery.get("recipients") or []
            ]
            row.afternoon_push_status = "sending"
            db.add(row)
            await db.commit()
            try:
                permission_result = (
                    self._stored_permission_result(delivery, recipients)
                    or await self._grant_document_permission(
                        row.document_id or "",
                        recipients,
                        permission="view",
                    )
                )
                failed_permission_ids = {
                    str(item.get("receive_id") or "")
                    for item in permission_result["results"]
                    if item.get("status") == "failed"
                }
                permitted_recipients = [
                    recipient
                    for recipient in recipients
                    if recipient.receive_id not in failed_permission_ids
                ]
                push_result = await self._push_document(
                    row.report_title or "市场信息简报",
                    row.document_url or "",
                    permitted_recipients,
                    stage="afternoon_release",
                )
                permission_failed_count = permission_result["failed_count"]
                row.afternoon_pushed_count = push_result["success_count"]
                row.afternoon_failed_push_count = (
                    push_result["failed_count"] + permission_failed_count
                )
                row.pushed_count += push_result["success_count"]
                row.failed_push_count += row.afternoon_failed_push_count
                row.afternoon_push_status = (
                    "success" if row.afternoon_failed_push_count == 0 else "partial"
                )
                row.status = "success" if row.failed_push_count == 0 else "partial"
                delivery.update(
                    {
                        "status": row.afternoon_push_status,
                        "sent_at": datetime.now().isoformat(),
                        "permission_results": permission_result,
                        "push_results": push_result,
                    }
                )
                success_count += 1
                results.append(
                    {
                        "run_id": row.id,
                        "status": row.afternoon_push_status,
                        "document_url": row.document_url,
                    }
                )
            except Exception as exc:
                row.afternoon_push_status = "failed"
                row.afternoon_failed_push_count = max(len(recipients), 1)
                row.failed_push_count += row.afternoon_failed_push_count
                row.status = "partial"
                delivery.update(
                    {
                        "status": "failed",
                        "sent_at": datetime.now().isoformat(),
                        "error": str(exc)[:1000],
                    }
                )
                failed_count += 1
                results.append({"run_id": row.id, "status": "failed", "error": str(exc)[:500]})
            payload["afternoon_delivery"] = delivery
            row.output_payload = payload
            db.add(row)
            await db.commit()
        return {
            "due_count": len(rows),
            "success_count": success_count,
            "failed_count": failed_count,
            "results": results,
        }

    async def _load_materials(
        self,
        db: AsyncSession,
        *,
        sys_company_id: int | None,
        period_start: datetime,
        period_end: datetime,
        limit: int,
    ) -> list[dict[str, Any]]:
        rows = list(
            (
                await db.exec(
                    select(InsightIntelligence)
                    .where(
                        InsightIntelligence.is_deleted == 0,
                        InsightIntelligence.status == "active",
                        InsightIntelligence.review_status == "approved",
                        InsightIntelligence.publish_time >= period_start,
                        InsightIntelligence.publish_time <= period_end,
                    )
                    .order_by(
                        InsightIntelligence.importance_level.asc(),
                        InsightIntelligence.publish_time.desc(),
                    )
                    .limit(1000)
                )
            ).all()
        )
        export_rows = await insight_feishu_bitable_service.build_export_rows(db, rows)
        intelligence_by_id = {int(item.id): item for item in rows if item.id is not None}
        company = await self._require_company(db, sys_company_id)
        company_name = company.name if company else None
        result: list[dict[str, Any]] = []
        for item in export_rows:
            values = item["values"]
            names = values.get("sys_company_name") or []
            if company_name and company_name not in names:
                continue
            if self._has_conflicting_url_year(
                str(values.get("source_url") or ""),
                values.get("publish_time"),
            ):
                continue
            result.append(
                {
                    "id": item["intelligence_id"],
                    "title": item["title"],
                    "summary": values.get("summary"),
                    "content": (
                        intelligence_by_id.get(int(item["intelligence_id"])).content
                        if intelligence_by_id.get(int(item["intelligence_id"]))
                        else None
                    ),
                    "publish_time": self._json_value(values.get("publish_time")),
                    "subject_name": values.get("subject_name"),
                    "category": values.get("category"),
                    "tags": values.get("tags") or [],
                    "importance": values.get("importance"),
                    "selection_reason": values.get("selection_reason"),
                    "business_insight": values.get("business_insight"),
                    "risk_opportunity": values.get("risk_opportunity"),
                    "source_channel": values.get("source_channel"),
                    "source_url": values.get("source_url"),
                }
            )
            if len(result) >= limit:
                break
        return result

    async def _select_materials(
        self,
        *,
        company_name: str,
        period_start: datetime,
        period_end: datetime,
        materials: list[dict[str, Any]],
        generation_rules: InsightFeishuBriefGenerationRules,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        deterministic_rejected = [
            {"id": item.get("id"), "reason": reason}
            for item in materials
            if (reason := insight_company_material_rejection_reason(company_name, item))
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
        compact_materials = [
            {
                "id": item["id"],
                "title": item.get("title"),
                "summary": item.get("summary"),
                "publish_time": item.get("publish_time"),
                "category": item.get("category"),
                "tags": item.get("tags"),
                "importance": item.get("importance"),
                "selection_reason": item.get("selection_reason"),
                "business_insight": item.get("business_insight"),
                "source_channel": item.get("source_channel"),
                "source_url": item.get("source_url"),
                "quality_warning": self._material_quality_warning(
                    item,
                    period_start=period_start,
                    period_end=period_end,
                ),
            }
            for item in eligible_materials
        ]
        prompt = f"""
你是管理层简报的选材编辑。请从候选正式情报中筛出真正值得写入
“{company_name}”简报的材料，不负责写报告。

公司业务边界：
{self._company_business_context(company_name)}

素材周期：{self._period_text(period_start, period_end)}

入选必须满足当前公司的核心业务边界，并至少具备以下一项业务价值关系：
1. 目标客户或竞对发生采购、配方、新品、销量、产能、门店、融资、供应链或经营风险变化；
2. 大豆、玉米及其加工产品，植物蛋白、蛋白粉、豆粕、淀粉糖、果葡糖浆、麦芽糖、
   功能糖或相关食品配料的供需、价格、技术和应用变化；
3. 会实质影响产品准入、原料合规、食品安全、进出口或客户采购标准的政策监管；
4. 可被销售、市场、研发或供应链部门直接用于判断和跟进的具体事件。
5. 下游茶饮、饮料、乳品、烘焙、肉制品及食品加工客户的新品、扩店、销量、渠道、经营和
   消费趋势变化，即使未直接提及上游配料，也能形成客户需求、应用方向或市场机会判断。
6. 泛食品行业资讯中，能够形成明确销售线索、研发方向、采购判断、竞争观察或风险预警的事实。

公司硬边界优先于上述通用价值：
- 御馨只保留蛋白类竞对、下游蛋白应用新布局和非转基因大豆原料信息；植物油相关动态全部排除。
- 健源材料必须涉及果糖、淀粉糖、麦芽糖、葡萄糖、功能糖、糖醇或其他玉米加工糖类产品及其应用；
  泛食品、泛客户和宽泛玉米行情若未落到实际产品，不得采用。

必须排除：
- 只有行业背景、没有具体主体、动作、数据或业务启示，需要三层以上推测才能联系到公司的新闻；
- 包装外观专利、通用设备专利、榜单、加盟软文、商业供货广告和缺乏事实依据的营销稿；
- 实际发生在素材周期前、周期内没有新增动作或数据的旧闻；
- 既没有具体事实，也无法说明对销售、市场、研发、采购或经营判断有何价值的材料。

按相关性40%、时效性20%、证据具体度20%、来源可信度10%、管理价值10%评分。
总分不低于{generation_rules.primary_score}分标记为 primary，用于七条重点导读候选；
{generation_rules.supporting_score}至{generation_rules.primary_score - 1}分标记为 supporting，
只作为五类正文的补充证据。低于{generation_rules.supporting_score}分排除。相同事件可保留一条主证据和一条来源独立、
能补充数字或经营动作的交叉证据，不要把所有补充证据误判为重复。
本轮有{len(eligible_materials)}条通过硬规则的材料，不设入选数量上限或配额：达到
{generation_rules.supporting_score}分的全部保留，
不得为了控制篇幅淘汰有业务价值的材料，也不得为了凑数量降低标准。政策、竞对、客户、技术、原料
中有真实材料的栏目都应获得覆盖。必须逐条作出决定，selected 与 rejected 合计覆盖全部候选 ID。
若 primary 不足7条，可从高分 supporting 中补足导读候选，但不得降低
{generation_rules.supporting_score}分底线。

只返回 JSON：
{{
  "selected": [{{"id": 1, "score": 90, "role": "primary", "category": "客户", "reason": "一句话"}}],
  "rejected": [{{"id": 2, "reason": "旧闻/弱相关/广告/重复/证据不足"}}]
}}

候选材料：
{json.dumps(compact_materials, ensure_ascii=False, default=str)}

本计划业务规则：
{self._rules_prompt(generation_rules)}
"""
        try:
            response = await LLMFactory.safe_invoke(
                [
                    SystemMessage(content="你只做严格选材并输出合法 JSON，不写简报正文。"),
                    HumanMessage(content=prompt),
                ],
                capability="complex-reasoning",
                temperature=0,
                enable_reasoning=False,
                max_retries=2,
            )
            payload = self._parse_json_object(getattr(response, "content", str(response)))
            selected_rows = payload.get("selected") if isinstance(payload.get("selected"), list) else []
            material_by_id = {int(item["id"]): item for item in eligible_materials}
            warnings_by_id = {
                int(item["id"]): self._material_quality_warning(
                    item,
                    period_start=period_start,
                    period_end=period_end,
                )
                for item in eligible_materials
            }
            hard_reject_warnings = {
                "明显旧闻",
                "商业供货广告",
                "榜单或营销稿，需核验来源和事实",
                "通用或包装专利，业务关联通常较弱",
            }
            selected_meta: list[dict[str, Any]] = []
            selected_ids: list[int] = []
            enforced_rejected: list[dict[str, Any]] = []
            for row in selected_rows:
                if not isinstance(row, dict):
                    continue
                try:
                    item_id = int(row.get("id"))
                    score = int(row.get("score") or 0)
                except (TypeError, ValueError):
                    continue
                warning = warnings_by_id.get(item_id)
                if warning in hard_reject_warnings:
                    enforced_rejected.append({"id": item_id, "reason": warning})
                    continue
                if (
                    item_id in material_by_id
                    and score >= generation_rules.supporting_score
                    and item_id not in selected_ids
                ):
                    role = (
                        "primary"
                        if score >= generation_rules.primary_score
                        else "supporting"
                    )
                    selected_ids.append(item_id)
                    selected_meta.append(
                        {
                            "id": item_id,
                            "score": score,
                            "role": role,
                            "category": str(row.get("category") or ""),
                            "reason": str(row.get("reason") or "")[:300],
                        }
                    )
            rejected_rows = payload.get("rejected") if isinstance(payload.get("rejected"), list) else []
            rejected_meta = [
                {
                    "id": row.get("id"),
                    "reason": str(row.get("reason") or "")[:300],
                }
                for row in rejected_rows
                if isinstance(row, dict)
            ]
            rejected_ids = {row.get("id") for row in rejected_meta}
            rejected_meta.extend(row for row in enforced_rejected if row["id"] not in rejected_ids)
            rejected_ids = {row.get("id") for row in rejected_meta}
            rejected_meta.extend(
                row for row in deterministic_rejected if row["id"] not in rejected_ids
            )
            selected_meta_by_id = {int(item["id"]): item for item in selected_meta}
            selected = [
                {
                    **material_by_id[item_id],
                    "editorial_score": selected_meta_by_id[item_id]["score"],
                    "brief_role": selected_meta_by_id[item_id]["role"],
                    "brief_category": selected_meta_by_id[item_id]["category"],
                }
                for item_id in selected_ids
            ]
            return selected, {
                "mode": "ai_editorial_selection",
                "candidate_count": len(materials),
                "eligible_count": len(eligible_materials),
                "deterministic_rejected_count": len(deterministic_rejected),
                "selected_count": len(selected),
                "rejected_count": len(materials) - len(selected),
                "selected": selected_meta,
                "rejected": rejected_meta,
            }
        except Exception as exc:
            selected = [
                item
                for item in eligible_materials
                if self._material_quality_warning(
                    item,
                    period_start=period_start,
                    period_end=period_end,
                )
                not in {"明显旧闻", "商业供货广告"}
            ]
            return selected, {
                "mode": "deterministic_fallback",
                "candidate_count": len(materials),
                "eligible_count": len(eligible_materials),
                "deterministic_rejected_count": len(deterministic_rejected),
                "selected_count": len(selected),
                "rejected_count": len(materials) - len(selected),
                "rejected": deterministic_rejected,
                "warning": str(exc)[:500],
            }

    async def _review_markdown_relevance(
        self,
        *,
        company_name: str,
        period_start: datetime,
        period_end: datetime,
        markdown: str,
        materials: list[dict[str, Any]],
    ) -> list[str]:
        prompt = f"""
你是管理层简报终审编辑。检查稿件是否真正服务于“{company_name}”。
公司业务边界：{self._company_business_context(company_name)}
素材周期：{self._period_text(period_start, period_end)}

逐项检查：
1. 材料能否为公司的销售、市场、研发、采购、供应链或经营判断提供清晰价值；不得仅因未直接出现
   核心产品名称而判为无关，下游客户动态、消费趋势和泛食品行业变化可以成立；
2. 是否把“可能相关”夸大成“直接拉动需求”，或给出材料没有支撑的机会、风险和行动；
3. 是否遗漏了已选素材中明显更有价值的客户扩张、采购、配方、产能和经营变化；
4. 客户、竞对、政策、技术、原料分类是否正确；
5. 是否将周期以前的旧闻写成本期新增动态；
6. 七条重点导读是否确实是全部已选材料中价值最高的七条。

只返回 JSON：
{{
  "pass": true,
  "issues": [
    {{"severity": "advisory", "action": "rewrite", "content": "可选优化"}}
  ]
}}。

严重级别规则：
- blocking：材料与稿件事实冲突、使用材料之外的事实或链接、把旧闻写成本期新增、明显错公司、
  将没有任何采购/配方/产能依据的内容断言为确定需求。只有 blocking 才能令 pass=false。
- advisory：不同素材之间的优先级偏好、可以进一步精炼的表述、尚可成立但证据不够强的业务推断。
  advisory 不得令 pass=false，也不得要求整篇重新生成。

如不通过，blocking issues 最多6条，必须指出具体事实错误及修正方式。不要因为个人选材偏好反复改变
已经通过75分选材门槛的七条导读；客户治理、采购流程和回款风险属于有效客户情报，不得仅因没有配方变化
就判定无关。

稿件：
{markdown}

已选材料：
{json.dumps(materials, ensure_ascii=False, default=str)}
"""
        try:
            response = await LLMFactory.safe_invoke(
                [
                    SystemMessage(content="你是严格、保守的业务编辑，只输出合法 JSON。"),
                    HumanMessage(content=prompt),
                ],
                capability="complex-reasoning",
                temperature=0,
                enable_reasoning=False,
                max_retries=2,
            )
            payload = self._parse_json_object(getattr(response, "content", str(response)))
            issues = payload.get("issues") if isinstance(payload.get("issues"), list) else []
            normalized: list[str] = []
            for item in issues[:6]:
                if isinstance(item, dict):
                    if str(item.get("severity") or "advisory").lower() != "blocking":
                        continue
                    action = str(item.get("action") or "修改")
                    content = str(item.get("content") or item.get("issue") or "")
                    value = f"{action}：{content}".strip("：")
                else:
                    value = str(item)
                if value.strip():
                    normalized.append(value[:500])
            if payload.get("pass") is True and not normalized:
                return []
            return normalized
        except Exception:
            return []

    async def _generate_markdown(
        self,
        *,
        company_name: str,
        frequency: str,
        period_start: datetime,
        period_end: datetime,
        generated_at: datetime,
        materials: list[dict[str, Any]],
        original_material_count: int,
        prompt_override: str | None,
        generation_rules: InsightFeishuBriefGenerationRules,
    ) -> tuple[str, str]:
        short_name = self._short_company_name(company_name)
        title = (
            f"{short_name}｜{period_end.year}年{period_end.month}月"
            f"第{self._week_of_month(period_end)}周信息简报"
        )
        period_text = self._period_text(period_start, period_end)
        # 有价值素材全部保留，但固定篇幅的周报不能按素材总量线性堆叠引用。
        minimum_citations = min(
            len(materials),
            max(
                generation_rules.minimum_citations,
                min(
                    generation_rules.maximum_citations,
                    math.ceil(len(materials) * 0.35),
                ),
            ),
        )
        system_prompt = (
            "你是香驰控股管理层情报简报撰写人员。领导已经确定了报告格式，"
            "你的职责是严格套用，不得重新设计报告。只使用所给正式情报，不得虚构数字、"
            "企业动作、来源或链接。先按事件和共同趋势归并材料，再组织段落；严禁按文章逐条拼接。"
            "正文以事实归纳为主，不写空泛结论，不增加行动建议、业务启示、机会、风险、方法说明、"
            "技术说明或结尾总结。链接必须挂在自然的事件、项目、产品或经营动作短语上，"
            "原则上作为句首主题或句中核心动宾短语，不得显示裸网址，不得直接复制冗长的文章原标题"
            "充当正文链接文字。材料即使被标为本周期发布，若内容明显只是历史旧闻重发且本周期没有"
            "新的进展、动作或数据，也不得写入简报。"
            "材料未明确披露采购量、采购计划、销量结果或经营影响时，只能客观描述客户动作及潜在关联，"
            "不得把推测写成确定需求，不得擅自建立竞争行为与另一家公司经营结果之间的因果关系。"
            "全文不得夹带面向香驰或我司的行动建议；只呈现事实、变化和材料明确支持的影响。"
            "宽口径文章被选中时，只提取与当前公司核心业务直接相关的事实。御馨不得写植物油、"
            "豆油、食用油或普通大豆行情，原料只写非转基因大豆；健源不得写未落到果糖及玉米加工"
            "糖类实际产品的泛食品、泛客户或宽泛玉米行情。"
        )
        format_prompt = f"""
输出 Markdown。文档标题由系统单独创建，正文不要再次输出标题。必须逐字遵循以下版式骨架：

管理层情报简报｜{period_text}｜生成时间：{generated_at.year}年{generated_at.month}月{generated_at.day}日

适用公司：{company_name}｜数据来源：情报管理多维表格·情报表｜原始候选 {original_material_count} 条

---

# 一、总览

本次报告分析涵盖{original_material_count}条数据，共分政策、原料、客户、竞对、技术五大方面去介绍。

# 政策

用 1 至 3 个连续自然段归纳政策事实，在相关事实文字上直接嵌入原文链接。

# 竞对

用 1 至 3 个连续自然段归纳竞对动作，在相关事实文字上直接嵌入原文链接。

# 客户

用 1 至 3 个连续自然段归纳客户变化，在相关事实文字上直接嵌入原文链接。

# 技术

用 1 至 3 个连续自然段归纳技术、专利和产品工艺变化，在相关事实文字上直接嵌入原文链接。

# 原料

用 1 至 3 个连续自然段归纳原料价格、供需、采购和加工变化，在相关事实文字上直接嵌入原文链接。

五类正文的共同写作要求：
1. 每段先给出一个清晰的趋势、变化或共同特征，再用 2 至 4 条相关材料交叉支撑。
2. 不按材料顺序写，不使用“一篇文章一分句”的新闻目录式拼接；相同事件只保留一次。
3. 链接锚文本应是 6 至 22 个汉字的事件短语，例如“推进液体糖浆新增产能”或“新品进入主流价格带”；
   不直接照搬文章原标题，不出现 https:// 开头的裸网址，也不单独列来源。
   锚文本必须替换句子中原本的事件短语，成为句子的主语、宾语或谓语；原则上放在句首，
   或放在句子开始 30 个汉字以内，不得先写完完整事件，
   再在句尾追加一个标题式链接。正确写法：`[长三角市场监管一体化进程加速](链接)，沪苏浙皖四地……`；
   错误写法：`四地启动标准互认并优化流通效率[长三角市场监管一体化提速](链接)。`
4. 每段控制在 120 至 420 字，信息不足时宁可少写一段，不用弱相关材料凑数。
5. 允许在段内说明事实之间的对比、延续、分化和因果关系，但不另设建议、启示、机会或风险。
6. 每条事实必须能回答“发生了什么、涉及谁、有什么数字或具体动作、与本分类有什么关系”中的至少三项。
7. 对明显发生在本报告周期以前、且本周期没有新动作或新数据的历史旧闻，即使材料时间被误标为本周期，
   也必须舍弃，不能作为现状写入。
8. 不得为了填满五个分类而使用弱相关材料。某类没有足够的高相关事实时，只写一句“本期暂无值得重点关注
   的新增动态”，不得用包装专利、通用设备专利、排行榜、加盟软文或地方性弱关联新闻凑数。
9. 只有材料明确出现配方、采购、产能、销量、门店扩张、客户经营、竞对行动、监管准入、原料供需或
   核心产品应用时，才能推导对公司的影响；不得把“可能相关”写成“直接拉动需求”。
10. 原文没有明确披露采购计划或采购量时，不得写“将显著增加采购需求”“直接指向新增采购”等确定性
    结论；可以写“可能带来原料增量”“值得关注后续采购变化”。不得把一家企业的扩张直接归因为另一家
    企业销量、营收或同店销售下滑，除非材料明确给出该因果证据。
11. 五类正文和重点导读都不得写“香驰需、我司应、需关注、需警惕、需评估、建议”等行动建议。报告
    只陈述公开事实及材料明确支持的业务影响，不替领导下结论或安排后续动作。
12. 材料中的 brief_role=primary 是主线事实，优先用于七条重点导读；brief_role=supporting 是补充证据，
    应融入五类正文以补充数字、趋势或交叉印证，不要因为它不进入七条导读就完全忽略。
13. 全文至少自然引用 {minimum_citations} 个不同来源；每条引用都必须承载具体事实，不得集中堆在段尾。
    7 条重点导读通常只能覆盖 7 个主线来源，因此政策、竞对、客户、技术、原料五类正文必须继续消化
    supporting 补充素材，并至少新增 {max(minimum_citations - 7, 0)} 个未在重点导读中使用的不同来源。
    不得只在五类正文重复引用七条导读来源，也不得用一串并列链接代替对事实的自然归纳。
14. 宽口径政策、行情或综述材料只采用与当前公司业务边界直接相关的子事实。御馨完全排除植物油、
    豆油、食用油动态，原料只采用非转基因大豆；健源只采用能落到果糖、淀粉糖、麦芽糖、葡萄糖、
    功能糖、糖醇或其他玉米加工糖类产品及应用的事实。

# 二、重点情报导读

必须正好 7 条，每条严格使用以下三段结构：
## [1. 情报标题](原文链接)

一级分类　事件标签

一段 120 至 260 字的完整事实描述。

编号必须从 1 到 7。导读标题本身就是链接，不得另写“时间、内容、来源、启示、建议”字段。
导读标题需要重新概括事件，不得机械复制原文标题；事实描述应保留主体、动作、数字和业务背景，
不得只是把原摘要换一种说法。
导读标题只写原文明示的主体和动作，例如“瑞幸加码自建烘焙产能”；不得使用“死磕、引爆、撬动、
倒逼”等媒体化表达，也不得把推测性影响写进标题，例如“收缩外采”“致战略延缓”。
一级分类从政策、竞对、客户、技术、原料、行业中选择；事件标签使用简短中文。
只能使用材料中真实存在的链接。若某一分类没有足够材料，保留该分类标题并用一句客观文字说明，
不得删除、改名或调整五类顺序。

{APPROVED_STYLE_EXAMPLES}
"""
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(
                content=f"{format_prompt}\n{prompt_override or ''}\n正式情报材料：\n"
                + json.dumps(materials, ensure_ascii=False, default=str)
            ),
        ]
        response = await LLMFactory.safe_invoke(
            messages,
            capability="complex-reasoning",
            temperature=0.1,
            enable_reasoning=False,
            max_retries=3,
        )
        markdown = self._normalize_editorial_tone(
            self._sanitize_markdown_link_labels(
                self._clean_markdown(getattr(response, "content", str(response))),
                materials,
            )
        )
        markdown = self._normalize_company_scope(markdown, company_name)
        errors = self._validate_markdown(markdown, materials, company_name=company_name, required_source_count=minimum_citations)
        for format_round in range(2):
            if not errors:
                break
            repair = await LLMFactory.safe_invoke(
                [
                    SystemMessage(content=system_prompt),
                    HumanMessage(
                        content=(
                            f"以下稿件第{format_round + 1}轮未通过固定格式检查：{'；'.join(errors)}。"
                            "请只修正这些问题，保持事实和链接不变，返回完整 Markdown。\n"
                            f"{format_prompt}\n原稿：\n{markdown}\n材料：\n"
                            + json.dumps(materials, ensure_ascii=False, default=str)
                        )
                    ),
                ],
                capability="complex-reasoning",
                temperature=0.05,
                enable_reasoning=False,
                max_retries=2,
            )
            markdown = self._normalize_editorial_tone(
                self._sanitize_markdown_link_labels(
                    self._clean_markdown(getattr(repair, "content", str(repair))),
                    materials,
                )
            )
            markdown = self._normalize_company_scope(markdown, company_name)
            errors = self._validate_markdown(markdown, materials, company_name=company_name, required_source_count=minimum_citations)
        if errors:
            raise ValueError(f"简报未通过固定格式检查：{'；'.join(errors)}")
        relevance_issues = await self._review_markdown_relevance(
            company_name=company_name,
            period_start=period_start,
            period_end=period_end,
            markdown=markdown,
            materials=materials,
        )
        for editorial_round in range(2):
            if not relevance_issues:
                break
            repair = await LLMFactory.safe_invoke(
                [
                    SystemMessage(content=system_prompt),
                    HumanMessage(
                        content=(
                            f"以下稿件格式已合格，但第{editorial_round + 1}轮业务编辑审校发现相关性问题。"
                            f"必须逐项修正：{'；'.join(relevance_issues)}。"
                            "优先删除或替换弱相关事实，不得虚构，不得改变固定版式，返回完整 Markdown。\n"
                            f"{format_prompt}\n原稿：\n{markdown}\n可用材料：\n"
                            + json.dumps(materials, ensure_ascii=False, default=str)
                        )
                    ),
                ],
                capability="complex-reasoning",
                temperature=0.05,
                enable_reasoning=False,
                max_retries=2,
            )
            markdown = self._normalize_editorial_tone(
                self._sanitize_markdown_link_labels(
                    self._clean_markdown(getattr(repair, "content", str(repair))),
                    materials,
                )
            )
            markdown = self._normalize_company_scope(markdown, company_name)
            errors = self._validate_markdown(markdown, materials, company_name=company_name, required_source_count=minimum_citations)
            if errors:
                relevance_issues = errors
                continue
            if editorial_round < 1:
                relevance_issues = await self._review_markdown_relevance(
                    company_name=company_name,
                    period_start=period_start,
                    period_end=period_end,
                    markdown=markdown,
                    materials=materials,
                )
            else:
                relevance_issues = []
        markdown = self._normalize_company_scope(markdown, company_name)
        errors = self._validate_markdown(markdown, materials, company_name=company_name, required_source_count=minimum_citations)
        if errors:
            raise ValueError(f"业务审校修订后仍未通过确定性检查：{'；'.join(errors)}")
        return title, markdown

    async def _create_document(
        self,
        title: str,
        markdown: str,
        *,
        folder_token: str | None = None,
    ) -> tuple[str, str]:
        data = await self._request(
            "POST",
            "/open-apis/docx/v1/documents",
            json={
                "folder_token": folder_token or settings.INSIGHT_FEISHU_BRIEF_FOLDER_TOKEN,
                "title": title,
            },
        )
        document = data.get("document") or {}
        document_id = str(document.get("document_id") or "")
        if not document_id:
            raise ValueError("飞书未返回云文档 ID")
        blocks = self._markdown_blocks(markdown)
        for index in range(0, len(blocks), 40):
            await self._request(
                "POST",
                f"/open-apis/docx/v1/documents/{document_id}/blocks/{document_id}/children",
                params={"document_revision_id": -1},
                json={"children": blocks[index : index + 40], "index": index},
            )
        return document_id, f"https://feishu.cn/docx/{document_id}"

    async def _replace_document_content(self, document_id: str, markdown: str) -> None:
        """清空根节点下的旧内容并写入新内容，保留文档链接和既有权限。"""
        data = await self._request(
            "GET",
            f"/open-apis/docx/v1/documents/{document_id}/blocks/{document_id}/children",
            params={"page_size": 500, "document_revision_id": -1},
        )
        children = data.get("items") or []
        if children:
            await self._request(
                "DELETE",
                f"/open-apis/docx/v1/documents/{document_id}/blocks/{document_id}/children/batch_delete",
                params={"document_revision_id": -1},
                json={"start_index": 0, "end_index": len(children)},
            )
        blocks = self._markdown_blocks(markdown)
        for index in range(0, len(blocks), 40):
            await self._request(
                "POST",
                f"/open-apis/docx/v1/documents/{document_id}/blocks/{document_id}/children",
                params={"document_revision_id": -1},
                json={"children": blocks[index : index + 40], "index": index},
            )

    async def _resolve_document_folder(
        self,
        *,
        company_name: str,
        frequency: str,
        period_end: datetime,
        artifact_type: str,
    ) -> BriefFolderResolution:
        root_token = settings.INSIGHT_FEISHU_BRIEF_FOLDER_TOKEN
        report_type = "月报" if frequency == "monthly" else "日报" if frequency == "daily" else "周报"
        segments = [
            self._safe_folder_name(self._short_company_name(company_name)),
            f"{period_end.year}年",
            report_type,
        ]
        if frequency == "monthly":
            segments.append("生成过程" if artifact_type == "process" else "正式稿")
        path = "/".join(segments)
        try:
            async with self._folder_lock:
                parent_token = root_token
                for segment in segments:
                    cache_key = (parent_token, segment)
                    child_token = self._folder_cache.get(cache_key)
                    if not child_token:
                        child_token = await self._find_child_folder(parent_token, segment)
                    if not child_token:
                        try:
                            child_token = await self._create_folder(parent_token, segment)
                        except Exception:
                            # 多进程同时到点时可能由另一个进程先创建同名目录。
                            child_token = await self._find_child_folder(parent_token, segment)
                            if not child_token:
                                raise
                    self._folder_cache[cache_key] = child_token
                    parent_token = child_token
            return BriefFolderResolution(
                token=parent_token,
                path=path,
                organized=True,
            )
        except Exception as exc:
            return BriefFolderResolution(
                token=root_token,
                path="根目录",
                organized=False,
                warning=f"自动归档失败，已回退根目录：{str(exc)[:500]}",
            )

    async def _find_child_folder(self, parent_token: str, name: str) -> str | None:
        page_token: str | None = None
        while True:
            params: dict[str, Any] = {
                "folder_token": parent_token,
                "page_size": 200,
            }
            if page_token:
                params["page_token"] = page_token
            data = await self._request(
                "GET",
                "/open-apis/drive/v1/files",
                params=params,
            )
            files = data.get("files") or data.get("items") or []
            for item in files:
                if item.get("type") == "folder" and str(item.get("name") or "") == name:
                    token = str(item.get("token") or item.get("file_token") or "")
                    if token:
                        return token
            if not data.get("has_more"):
                return None
            page_token = str(
                data.get("next_page_token") or data.get("page_token") or ""
            )
            if not page_token:
                return None

    async def _create_folder(self, parent_token: str, name: str) -> str:
        data = await self._request(
            "POST",
            "/open-apis/drive/v1/files/create_folder",
            json={"name": name, "folder_token": parent_token},
        )
        folder = data.get("folder") or {}
        token = str(data.get("token") or folder.get("token") or "")
        if not token:
            raise ValueError(f"飞书新建文件夹“{name}”后未返回 Token")
        return token

    async def move_document_to_folder(
        self,
        document_id: str,
        folder_token: str,
    ) -> None:
        await self._request(
            "POST",
            f"/open-apis/drive/v1/files/{document_id}/move",
            json={"type": "docx", "folder_token": folder_token},
        )

    @staticmethod
    def _safe_folder_name(value: str) -> str:
        cleaned = re.sub(r'[\\/:*?"<>|]+', "、", value).strip()
        return cleaned[:80] or "未分类公司"

    async def _push_document(
        self,
        title: str,
        document_url: str,
        recipients: list[InsightFeishuBriefRecipient],
        *,
        stage: str = "release",
    ) -> dict[str, Any]:
        results: list[dict[str, Any]] = []
        success_count = 0
        failed_count = 0
        for recipient in recipients:
            try:
                if stage == "morning_review":
                    message = (
                        f"**{settings.INSIGHT_FEISHU_BRIEF_BOT_NAME}已生成本期简报审阅稿**\n"
                        "请直接在云文档中审阅和修改；下午发送时会使用同一篇文档，不会覆盖您的修改。"
                    )
                    button_text = "打开并审阅"
                else:
                    message = (
                        "**本月市场洞察报告已发布**\n"
                        "点击下方按钮查看报告全文及相关信息来源。"
                    )
                    button_text = "查看月度报告" if "月度报告" in title else "查看完整报告"
                await self._request(
                    "POST",
                    "/open-apis/im/v1/messages",
                    params={"receive_id_type": recipient.receive_id_type},
                    json={
                        "receive_id": recipient.receive_id,
                        "msg_type": "interactive",
                        "content": json.dumps(
                            {
                                "config": {"wide_screen_mode": True},
                                "header": {
                                    "template": "blue",
                                    "title": {"tag": "plain_text", "content": title},
                                },
                                "elements": [
                                    {
                                        "tag": "div",
                                        "text": {
                                            "tag": "lark_md",
                                            "content": message,
                                        },
                                    },
                                    {
                                        "tag": "action",
                                        "actions": [
                                            {
                                                "tag": "button",
                                                "text": {"tag": "plain_text", "content": button_text},
                                                "type": "primary",
                                                "url": document_url,
                                            }
                                        ],
                                    },
                                ],
                            },
                            ensure_ascii=False,
                        ),
                    },
                )
                success_count += 1
                results.append({"receive_id": recipient.receive_id, "status": "success"})
            except Exception as exc:
                failed_count += 1
                results.append({"receive_id": recipient.receive_id, "status": "failed", "error": str(exc)[:500]})
        return {"success_count": success_count, "failed_count": failed_count, "results": results}

    async def _grant_document_edit_permission(
        self,
        document_id: str,
        recipients: list[InsightFeishuBriefRecipient],
    ) -> dict[str, Any]:
        """尽力给上午审阅人开放编辑权限；权限失败不阻断文档和消息发送。"""
        return await self._grant_document_permission(
            document_id,
            recipients,
            permission="edit",
        )

    async def _grant_document_permission(
        self,
        document_id: str,
        recipients: list[InsightFeishuBriefRecipient],
        *,
        permission: str,
    ) -> dict[str, Any]:
        """逐人授予文档权限，兼容 L3 等需要显式协作者的文档密级。"""
        if permission not in {"view", "edit"}:
            raise ValueError("飞书文档协作者权限仅支持 view 或 edit")
        member_type_map = {
            "open_id": "openid",
            "user_id": "userid",
            "email": "email",
            "chat_id": "openchat",
        }
        supported = [
            recipient
            for recipient in recipients
            if recipient.receive_id_type in member_type_map
        ]
        existing_permissions = await self._document_member_permissions(document_id)
        permission_rank = {"view": 1, "edit": 2, "full_access": 3}
        results: list[dict[str, Any]] = []
        success_count = 0
        failed_count = 0
        for index, recipient in enumerate(supported):
            member_type = member_type_map[recipient.receive_id_type]
            existing_permission = existing_permissions.get(
                (member_type, recipient.receive_id)
            )
            if permission_rank.get(existing_permission or "", 0) >= permission_rank[permission]:
                success_count += 1
                results.append(
                    {
                        "receive_id": recipient.receive_id,
                        "status": "already_granted",
                        "permission": existing_permission,
                    }
                )
                continue
            try:
                if existing_permission:
                    await self._request(
                        "PUT",
                        (
                            f"/open-apis/drive/v1/permissions/{document_id}/members/"
                            f"{recipient.receive_id}"
                        ),
                        params={"type": "docx", "need_notification": "false"},
                        json={"member_type": member_type, "perm": permission},
                    )
                else:
                    await self._request(
                        "POST",
                        f"/open-apis/drive/v1/permissions/{document_id}/members",
                        params={"type": "docx", "need_notification": "false"},
                        json={
                            "member_type": member_type,
                            "member_id": recipient.receive_id,
                            "perm": permission,
                        },
                    )
                success_count += 1
                results.append(
                    {
                        "receive_id": recipient.receive_id,
                        "status": "success",
                        "permission": permission,
                    }
                )
            except Exception as exc:
                failed_count += 1
                results.append(
                    {
                        "receive_id": recipient.receive_id,
                        "status": "failed",
                        "permission": permission,
                        "error": str(exc)[:500],
                    }
                )
            if index < len(supported) - 1:
                await asyncio.sleep(0.65)
        return {
            "success_count": success_count,
            "failed_count": failed_count,
            "results": results,
        }

    async def _document_member_permissions(
        self,
        document_id: str,
    ) -> dict[tuple[str, str], str]:
        permissions: dict[tuple[str, str], str] = {}
        page_token: str | None = None
        try:
            while True:
                params: dict[str, Any] = {"type": "docx", "page_size": 100}
                if page_token:
                    params["page_token"] = page_token
                data = await self._request(
                    "GET",
                    f"/open-apis/drive/v1/permissions/{document_id}/members",
                    params=params,
                )
                for item in data.get("items") or []:
                    member_type = str(item.get("member_type") or "")
                    member_id = str(item.get("member_id") or "")
                    if member_type and member_id:
                        permissions[(member_type, member_id)] = str(item.get("perm") or "")
                if not data.get("has_more"):
                    break
                page_token = str(data.get("page_token") or "")
                if not page_token:
                    break
        except Exception:
            return {}
        return permissions

    @staticmethod
    def _stored_permission_result(
        delivery: dict[str, Any],
        recipients: list[InsightFeishuBriefRecipient],
    ) -> dict[str, Any] | None:
        stored = delivery.get("permission_results")
        if not isinstance(stored, dict):
            return None
        results = stored.get("results")
        if not isinstance(results, list):
            return None
        successful_ids = {
            str(item.get("receive_id") or "")
            for item in results
            if item.get("status") in {"success", "already_granted"}
        }
        if any(recipient.receive_id not in successful_ids for recipient in recipients):
            return None
        return stored

    async def _document_security_label(self, document_id: str) -> str | None:
        """读取文档密级；应用未开通字段权限时返回 None，不阻断发布。"""
        try:
            data = await self._request(
                "POST",
                "/open-apis/drive/v1/metas/batch_query",
                params={"user_id_type": "open_id"},
                json={
                    "request_docs": [{"doc_token": document_id, "doc_type": "docx"}],
                    "with_url": False,
                },
            )
            metas = data.get("metas") or []
            if not metas:
                return None
            return str(metas[0].get("sec_label_name") or "").strip() or None
        except Exception:
            return None

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        token = await self._tenant_access_token()
        timeout = max(settings.INSIGHT_FEISHU_BRIEF_TIMEOUT_SECONDS, 5)
        async with httpx.AsyncClient(base_url=settings.FEISHU_BASE_URL.rstrip("/"), timeout=timeout) as client:
            response = await client.request(
                method,
                path,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"},
                **kwargs,
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise ValueError(f"飞书接口返回非 JSON：HTTP {response.status_code}") from exc
        if response.status_code >= 400 or int(payload.get("code") or 0) != 0:
            raise ValueError(
                f"飞书接口失败：HTTP {response.status_code}，code={payload.get('code')}，msg={payload.get('msg')}"
            )
        return payload.get("data") or {}

    async def _tenant_access_token(self) -> str:
        now = datetime.now().timestamp()
        if self._tenant_token and now < self._tenant_token_expires_at:
            return self._tenant_token
        async with httpx.AsyncClient(
            base_url=settings.FEISHU_BASE_URL.rstrip("/"),
            timeout=max(settings.INSIGHT_FEISHU_BRIEF_TIMEOUT_SECONDS, 5),
        ) as client:
            response = await client.post(
                "/open-apis/auth/v3/tenant_access_token/internal",
                json={
                    "app_id": settings.INSIGHT_FEISHU_BRIEF_APP_ID,
                    "app_secret": settings.INSIGHT_FEISHU_BRIEF_APP_SECRET,
                },
            )
        payload = response.json()
        if response.status_code >= 400 or int(payload.get("code") or 0) != 0:
            raise ValueError(f"飞书机器人鉴权失败：{payload.get('msg') or response.text[:300]}")
        self._tenant_token = str(payload.get("tenant_access_token") or "")
        self._tenant_token_expires_at = now + max(int(payload.get("expire") or 7200) - 300, 60)
        return self._tenant_token

    def _markdown_blocks(self, markdown: str) -> list[dict[str, Any]]:
        blocks: list[dict[str, Any]] = []
        paragraph: list[str] = []
        in_guide = False

        def flush() -> None:
            if paragraph:
                blocks.append(self._text_block(2, "text", "\n".join(paragraph)))
                paragraph.clear()

        for raw_line in markdown.splitlines():
            line = raw_line.strip()
            if not line:
                flush()
                continue
            if line.startswith("# "):
                flush()
                heading = line[2:].strip()
                blocks.append(self._text_block(3, "heading1", heading))
                if heading == "二、重点情报导读":
                    in_guide = True
            elif line.startswith("## "):
                flush()
                blocks.append(self._text_block(4, "heading2", line[3:].strip()))
            elif line == "---":
                flush()
                blocks.append({"block_type": 22, "divider": {}})
            elif line.startswith("> "):
                flush()
                blocks.append(self._text_block(2, "text", line[2:].strip()))
            elif not blocks and line.startswith(
                ("管理层情报简报｜", "管理层月度市场信息报告｜", "月报生成与审校记录｜")
            ):
                flush()
                blocks.append(self._text_block(2, "text", line, align=2))
            elif (
                len(blocks) == 1
                and line.startswith("适用公司：")
                and "数据来源：" in line
            ):
                flush()
                blocks.append(self._text_block(2, "text", line, align=2))
            elif in_guide and self._is_guide_tag_line(line):
                flush()
                blocks.append(self._guide_tag_block(line))
            else:
                paragraph.append(line)
        flush()
        return blocks

    def _text_block(
        self,
        block_type: int,
        key: str,
        text: str,
        *,
        align: int = 1,
    ) -> dict[str, Any]:
        text = text.replace("**", "")
        elements: list[dict[str, Any]] = []
        cursor = 0
        for match in re.finditer(r"\[([^\]]+)\]\((https?://[^)]+)\)", text):
            if match.start() > cursor:
                elements.append({"text_run": {"content": text[cursor : match.start()]}})
            elements.append(
                {
                    "text_run": {
                        "content": match.group(1),
                        "text_element_style": {"link": {"url": match.group(2)}},
                    }
                }
            )
            cursor = match.end()
        if cursor < len(text):
            elements.append({"text_run": {"content": text[cursor:]}})
        return {
            "block_type": block_type,
            key: {
                "elements": elements or [{"text_run": {"content": text}}],
                "style": {"align": align},
            },
        }

    @staticmethod
    def _week_of_month(value: datetime) -> int:
        """按素材截止日在当月的七天区间计算周次。"""
        return (value.day - 1) // 7 + 1

    @staticmethod
    def _is_guide_tag_line(text: str) -> bool:
        return bool(
            re.fullmatch(
                r"(政策|竞对|客户|技术|原料|行业)[\s　]+[^\s　].{0,30}",
                text,
            )
        )

    @staticmethod
    def _guide_tag_block(text: str) -> dict[str, Any]:
        parts = re.split(r"[\s　]+", text, maxsplit=1)
        category = parts[0]
        event_tag = parts[1] if len(parts) > 1 else ""
        return {
            "block_type": 2,
            "text": {
                "elements": [
                    {
                        "text_run": {
                            "content": category,
                            "text_element_style": {"background_color": 5},
                        }
                    },
                    {"text_run": {"content": "　"}},
                    {
                        "text_run": {
                            "content": event_tag,
                            "text_element_style": {"background_color": 3},
                        }
                    },
                ],
                "style": {"align": 1},
            },
        }

    def _validate_markdown(
        self,
        markdown: str,
        materials: list[dict[str, Any]],
        *,
        company_name: str | None = None,
        required_source_count: int | None = None,
    ) -> list[str]:
        errors: list[str] = []
        headings = ["# 一、总览", "# 政策", "# 竞对", "# 客户", "# 技术", "# 原料", "# 二、重点情报导读"]
        positions = [markdown.find(item) for item in headings]
        if any(position < 0 for position in positions) or positions != sorted(positions):
            errors.append("章节缺失或顺序错误")
        if not markdown.startswith("管理层情报简报｜"):
            errors.append("缺少领导定稿的头部信息")
        if "适用公司：" not in markdown or "数据来源：情报管理多维表格·情报表" not in markdown:
            errors.append("适用公司或数据来源信息不完整")
        guide = markdown.split("# 二、重点情报导读", 1)[-1]
        numbered = re.findall(r"^##\s+\[([1-7])\.\s+[^\]]+\]\(https?://[^)]+\)", guide, flags=re.MULTILINE)
        if numbered != [str(index) for index in range(1, 8)]:
            errors.append("重点情报导读必须使用可点击标题，并正好为 1 至 7 共七条")
        guide_titles = re.findall(
            r"^##\s+\[[1-7]\.\s+([^\]]+)\]\(https?://[^)]+\)",
            guide,
            flags=re.MULTILINE,
        )
        if any(
            re.search(r"(死磕|引爆|撬动|倒逼|收缩外采|致战略延缓|必然|强势碾压)", title)
            for title in guide_titles
        ):
            errors.append("导读标题包含媒体化或材料未充分支撑的因果措辞，需改为正式、客观的主体动作")
        forbidden = ("业务启示：", "机会：", "风险：", "行动建议", "建议：", "**时间：**", "**内容：**", "**来源：**")
        if any(item in markdown for item in forbidden):
            errors.append("包含领导定稿中不存在的字段或章节")
        if any(re.search(pattern, markdown) for pattern in UNSUPPORTED_INFERENCE_PATTERNS):
            errors.append("包含材料未充分支撑的确定性需求、业绩因果或机会判断，需改为客观事实或审慎表述")
        if any(re.search(pattern, markdown) for pattern in IMPLICIT_ADVICE_PATTERNS):
            errors.append("正文夹带行动建议，需删除“香驰需、我司应、需关注、需警惕”等建议性表达")
        if re.search(r"(?<!\]\()https?://", markdown):
            errors.append("正文包含未嵌入语义短语的裸网址")
        body = markdown.split("# 二、重点情报导读", 1)[0]
        competitor_match = re.search(r"^# 竞对\s*$([\s\S]*?)(?=^# )", body, flags=re.MULTILINE)
        competitor_body = competitor_match.group(1) if competitor_match else ""
        raw_material_match = re.search(r"^# 原料\s*$([\s\S]*?)(?=^# )", body, flags=re.MULTILINE)
        raw_material_body = raw_material_match.group(1) if raw_material_match else ""
        if company_name and "御馨" in company_name and re.search(
            r"(?:植物油|豆油|大豆油|食用油|油脂|玉米油|菜籽油)", body
        ):
            errors.append("御馨简报混入植物油或食用油动态，必须全部删除")
        if (
            company_name
            and "御馨" in company_name
            and "大豆" in raw_material_body
            and "非转基因" not in raw_material_body
        ):
            errors.append("御馨原料章节的大豆信息未明确限定为非转基因大豆")
        if company_name and "健源" in company_name and not re.search(
            r"(?:果葡糖浆|麦芽糖|淀粉糖|葡萄糖|功能糖|糖醇|赤藓糖醇|玉米糖|玉米深加工)",
            body,
        ):
            errors.append("健源简报未落到果糖或玉米加工糖类实际产品")
        if company_name and "御馨" in company_name and re.search(
            r"(?:长安花|西王|植物油|豆油|大豆油|食用油|油脂|菜籽油|玉米油)", competitor_body
        ):
            errors.append("御馨竞对章节混入植物油业务，必须删除并只保留蛋白主线")
        if company_name and "健源" in company_name and re.search(
            r"(?:大豆蛋白|豆粕|豆油|植物蛋白)", competitor_body
        ):
            errors.append("健源竞对章节混入大豆或植物蛋白旁支业务，必须删除并只保留玉米深加工及糖类主线")
        body_links = re.findall(r"\[([^\]]+)\]\((https?://[^)]+)\)", body)
        source_titles = {
            self._normalize_title(str(item.get("title") or ""))
            for item in materials
            if item.get("title")
        }
        for label, _url in body_links:
            normalized_label = self._normalize_title(label)
            if label.strip().lower().startswith(("http://", "https://", "www.")):
                errors.append("分类正文链接文字不能显示网址")
                break
            if len(label.strip()) > 22 and normalized_label in source_titles:
                errors.append("分类正文直接复制了冗长的文章原标题，需改为自然事件短语")
                break
        terminal_link_count = len(
            re.findall(r"\[[^\]]+\]\(https?://[^)]+\)[。！？；](?:\s|$)", body)
        )
        if body_links and terminal_link_count / len(body_links) > 0.6:
            errors.append("分类正文多数链接仍堆在句尾，需将事件链接自然嵌入句子")
        late_link_count = 0
        for match in re.finditer(r"\[[^\]]+\]\(https?://[^)]+\)", body):
            sentence_start = max(
                body.rfind(mark, 0, match.start())
                for mark in ("\n", "。", "！", "？", "；")
            )
            prefix = re.sub(r"\s+", "", body[sentence_start + 1 : match.start()])
            if len(prefix) > 80:
                late_link_count += 1
        if body_links and late_link_count / len(body_links) > 0.9:
            errors.append("分类正文链接几乎全部出现得过晚，需将事件短语自然融入核心事实")
        category_body = re.split(r"^# (?:政策|竞对|客户|技术|原料)$", body, flags=re.MULTILINE)[1:]
        if any(
            len(re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", paragraph).strip()) > 520
            for section in category_body
            for paragraph in re.split(r"\n\s*\n", section)
            if paragraph.strip() and not paragraph.lstrip().startswith("#")
        ):
            errors.append("分类正文存在过长段落，需按共同主题拆分并重新归纳")
        allowed_urls = {str(item.get("source_url")) for item in materials if item.get("source_url")}
        output_urls = set(re.findall(r"https?://[^)\s]+", markdown))
        if output_urls - allowed_urls:
            errors.append("包含材料之外的来源链接")
        required_source_count = min(
            len(allowed_urls),
            required_source_count
            if required_source_count is not None
            else max(7, min(25, math.ceil(len(allowed_urls) * 0.35))),
        )
        if len(output_urls & allowed_urls) < required_source_count:
            errors.append(
                f"正文只使用了 {len(output_urls & allowed_urls)} 个不同来源，至少需要自然消化 "
                f"{required_source_count} 个有效来源"
            )
        return errors

    def _recipients(self, plan: InsightFeishuBriefPlan) -> list[InsightFeishuBriefRecipient]:
        values = plan.recipients_json or self._default_recipients()
        return [InsightFeishuBriefRecipient.model_validate(item) for item in values]

    def _afternoon_recipients(
        self,
        plan: InsightFeishuBriefPlan,
    ) -> list[InsightFeishuBriefRecipient]:
        return [
            InsightFeishuBriefRecipient.model_validate(item)
            for item in plan.afternoon_recipients_json or []
        ]

    def _same_day_time(self, source: datetime, time_of_day: str) -> datetime:
        hour, minute = [int(item) for item in time_of_day.split(":", 1)]
        candidate = source.replace(hour=hour, minute=minute, second=0, microsecond=0)
        return max(candidate, source)

    def _default_recipients(self) -> list[dict[str, Any]]:
        try:
            value = json.loads(settings.INSIGHT_FEISHU_BRIEF_DEFAULT_RECIPIENTS_JSON or "[]")
            return value if isinstance(value, list) else []
        except json.JSONDecodeError:
            return []

    def _next_run_time(
        self,
        frequency: str,
        time_of_day: str,
        weekday: int | None,
        day_of_month: int | None,
        *,
        base: datetime | None = None,
    ) -> datetime:
        zone = ZoneInfo("Asia/Shanghai")
        source = base or datetime.now()
        now = source.replace(tzinfo=zone) if source.tzinfo is None else source.astimezone(zone)
        hour, minute = [int(item) for item in time_of_day.split(":", 1)]
        candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if frequency == "daily":
            if candidate <= now:
                candidate += timedelta(days=1)
        elif frequency == "weekly":
            target = weekday if weekday is not None else 0
            candidate += timedelta(days=(target - candidate.weekday()) % 7)
            if candidate <= now:
                candidate += timedelta(days=7)
        else:
            configured_day = min(max(day_of_month or 1, 1), 31)
            target_day = min(configured_day, calendar.monthrange(candidate.year, candidate.month)[1])
            candidate = candidate.replace(day=target_day)
            if candidate <= now:
                if candidate.month == 12:
                    candidate = candidate.replace(year=candidate.year + 1, month=1)
                else:
                    candidate = candidate.replace(month=candidate.month + 1)
                target_day = min(
                    configured_day,
                    calendar.monthrange(candidate.year, candidate.month)[1],
                )
                candidate = candidate.replace(day=target_day)
        return candidate.replace(tzinfo=None)

    def _period_bounds(
        self,
        plan: InsightFeishuBriefPlan,
        *,
        now: datetime,
        trigger_type: str,
        requested_start: datetime | None,
    ) -> tuple[datetime, datetime]:
        if requested_start:
            return requested_start, now
        if plan.schedule_frequency == "weekly" and self._is_scheduled_trigger(trigger_type):
            target_weekday = plan.weekday if plan.weekday is not None else 0
            days_since_schedule = (now.weekday() - target_weekday) % 7
            current_schedule_start = (now - timedelta(days=days_since_schedule)).replace(
                hour=0,
                minute=0,
                second=0,
                microsecond=0,
            )
            return current_schedule_start - timedelta(days=7), current_schedule_start - timedelta(microseconds=1)
        if plan.schedule_frequency != "monthly":
            return now - timedelta(days=plan.material_days), now
        if self._is_scheduled_trigger(trigger_type):
            if plan.day_of_month == 31:
                return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0), now
            current_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            previous_month_end = current_month_start - timedelta(microseconds=1)
            previous_month_start = previous_month_end.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            return previous_month_start, previous_month_end
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0), now

    def _is_scheduled_trigger(self, trigger_type: str) -> bool:
        return trigger_type in {"brief_scheduler", "scheduler", "manual_due_scan"} or trigger_type.startswith(
            "scheduler:"
        )

    async def _require_plan(self, db: AsyncSession, plan_id: int) -> InsightFeishuBriefPlan:
        row = await db.get(InsightFeishuBriefPlan, plan_id)
        if not row or row.is_deleted:
            raise ValueError("飞书简报计划不存在")
        return row

    def _generation_rules(
        self,
        plan: InsightFeishuBriefPlan,
        company_name: str,
    ) -> InsightFeishuBriefGenerationRules:
        payload = dict(plan.generation_rules_json or {})
        if not payload.get("focus_topics"):
            if "健源" in company_name:
                payload["focus_topics"] = [
                    "果葡糖浆", "麦芽糖浆", "淀粉糖", "葡萄糖", "功能糖与糖醇",
                    "玉米加工糖类应用", "糖类竞对", "糖类下游客户",
                ]
                payload["excluded_content"] = [
                    "广告软文", "榜单", "招聘", "通用专利", "旧闻", "重复事件",
                    "泛食品资讯", "宽泛玉米行情",
                ]
            elif "御馨" in company_name:
                payload["focus_topics"] = [
                    "大豆蛋白", "植物蛋白", "蛋白类竞对", "下游蛋白应用",
                    "蛋白新品与技术", "非转基因大豆", "替代蛋白",
                ]
                payload["excluded_content"] = [
                    "广告软文", "榜单", "招聘", "通用专利", "旧闻", "重复事件",
                    "植物油动态", "普通大豆行情",
                ]
            else:
                payload["focus_topics"] = ["客户", "竞对", "政策", "技术", "原料", "消费趋势"]
        try:
            return InsightFeishuBriefGenerationRules.model_validate(payload)
        except Exception:
            return InsightFeishuBriefGenerationRules(focus_topics=payload.get("focus_topics") or [])

    @staticmethod
    def _rules_prompt(rules: InsightFeishuBriefGenerationRules) -> str:
        depth_labels = {"concise": "精简", "balanced": "均衡", "detailed": "深入"}
        priorities = "、".join(
            f"{name}{level}/5"
            for name, level in sorted(
                rules.section_priorities.items(),
                key=lambda item: item[1],
                reverse=True,
            )
        )
        return (
            f"关注主题：{'、'.join(rules.focus_topics) or '按公司默认业务范围'}\n"
            f"服务部门：{'、'.join(rules.value_departments)}\n"
            f"排除内容：{'、'.join(rules.excluded_content)}\n"
            f"栏目侧重：{priorities}\n"
            f"写作深度：{depth_labels[rules.writing_depth]}\n"
            f"业务启示：{'需要说明' if rules.include_business_insight else '只陈述事实，不延伸启示'}\n"
            f"主线素材阈值：{rules.primary_score}；补充素材阈值：{rules.supporting_score}\n"
            f"正文来源覆盖：至少{rules.minimum_citations}个、最多按{rules.maximum_citations}个控制"
        )

    def _merge_rule_prompt(
        self,
        prompt_override: str | None,
        rules: InsightFeishuBriefGenerationRules,
    ) -> str:
        custom = (prompt_override or "").strip()
        rule_text = f"本计划结构化业务规则：\n{self._rules_prompt(rules)}"
        return f"{rule_text}\n\n本计划补充要求：\n{custom}" if custom else rule_text

    async def _require_company(self, db: AsyncSession, company_id: int | None) -> SysCompany | None:
        if company_id is None:
            return None
        row = await db.get(SysCompany, company_id)
        if not row or row.is_deleted:
            raise ValueError("所属公司不存在")
        return row

    async def _company_names(self, db: AsyncSession, ids: list[int]) -> dict[int, str]:
        if not ids:
            return {}
        rows = list((await db.exec(select(SysCompany).where(SysCompany.id.in_(ids), SysCompany.is_deleted == 0))).all())
        return {row.id: row.name for row in rows if row.id}

    def _plan_read(self, row: InsightFeishuBriefPlan, company_name: str | None) -> InsightFeishuBriefPlanRead:
        return InsightFeishuBriefPlanRead(
            id=row.id or 0,
            plan_uid=row.plan_uid,
            plan_name=row.plan_name,
            sys_company_id=row.sys_company_id,
            sys_company_name=company_name,
            schedule_frequency=row.schedule_frequency,
            weekday=row.weekday,
            day_of_month=row.day_of_month,
            time_of_day=row.time_of_day,
            timezone=row.timezone,
            material_days=row.material_days,
            max_materials=row.max_materials,
            generation_strategy=row.generation_strategy,
            prompt_override=row.prompt_override,
            generation_rules=self._generation_rules(row, company_name or "香驰控股"),
            recipients=[InsightFeishuBriefRecipient.model_validate(item) for item in row.recipients_json or []],
            afternoon_recipients=[
                InsightFeishuBriefRecipient.model_validate(item)
                for item in row.afternoon_recipients_json or []
            ],
            afternoon_push_time=row.afternoon_push_time,
            next_run_time=row.next_run_time,
            last_run_time=row.last_run_time,
            last_run_id=row.last_run_id,
            last_status=row.last_status,
            last_error=row.last_error,
            status=row.status,
            create_time=row.create_time,
            update_time=row.update_time,
        )

    def _run_read(self, row: InsightFeishuBriefRun) -> InsightFeishuBriefRunRead:
        return InsightFeishuBriefRunRead(
            id=row.id or 0,
            plan_id=row.plan_id,
            trigger_type=row.trigger_type,
            status=row.status,
            period_start=row.period_start,
            period_end=row.period_end,
            material_count=row.material_count,
            report_title=row.report_title,
            document_id=row.document_id,
            document_url=row.document_url,
            pushed_count=row.pushed_count,
            failed_push_count=row.failed_push_count,
            afternoon_push_scheduled_at=row.afternoon_push_scheduled_at,
            afternoon_push_status=row.afternoon_push_status,
            afternoon_pushed_count=row.afternoon_pushed_count,
            afternoon_failed_push_count=row.afternoon_failed_push_count,
            error_message=row.error_message,
            output_payload=row.output_payload or {},
            started_at=row.started_at,
            finished_at=row.finished_at,
            create_time=row.create_time,
        )

    def _clean_markdown(self, value: Any) -> str:
        if isinstance(value, list):
            value = "".join(str(item.get("text") or item) if isinstance(item, dict) else str(item) for item in value)
        text = str(value or "").strip()
        text = re.sub(r"^```(?:markdown)?\s*", "", text)
        return re.sub(r"\s*```$", "", text).strip()

    def _parse_json_object(self, value: Any) -> dict[str, Any]:
        text = self._clean_markdown(value)
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text).strip()
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("模型未返回 JSON 对象")
        payload = json.loads(text[start : end + 1])
        if not isinstance(payload, dict):
            raise ValueError("模型选材结果不是 JSON 对象")
        return payload

    def _company_business_context(self, company_name: str) -> str:
        return insight_company_business_context(company_name)

    def _material_quality_warning(
        self,
        item: dict[str, Any],
        *,
        period_start: datetime,
        period_end: datetime,
    ) -> str | None:
        title = str(item.get("title") or "")
        summary = str(item.get("summary") or "")
        text = f"{title} {summary}"
        if any(marker in title for marker in ("_供应_", "现货供应", "1千克起订", "食品商务中心")):
            return "商业供货广告"
        if any(marker in title.upper() for marker in ("TOP10", "排行榜", "实力榜", "人气榜")) or re.search(
            r"(?:评级|排名).{0,30}第\d+名",
            title,
        ):
            return "榜单或营销稿，需核验来源和事实"
        date_matches = re.findall(r"(20\d{2})年(\d{1,2})月(?:([0-3]?\d)日)?", text)
        parsed_dates: list[datetime] = []
        for year_text, month_text, day_text in date_matches:
            try:
                parsed_dates.append(
                    datetime(
                        int(year_text),
                        int(month_text),
                        int(day_text or 1),
                    )
                )
            except ValueError:
                continue
        if parsed_dates and all(
            value.year != period_end.year
            or value.month not in {period_start.month, period_end.month}
            for value in parsed_dates
        ):
            return "明显旧闻"
        first_year = re.match(r"\s*(20\d{2})年", summary)
        if first_year and int(first_year.group(1)) < period_start.year:
            return "明显旧闻"
        if any(marker in title for marker in ("包装盒相关专利", "包装外观专利", "清洗装置专利")):
            return "通用或包装专利，业务关联通常较弱"
        return None

    def _short_company_name(self, value: str) -> str:
        if "健源" in value:
            return "健源"
        if "御馨" in value:
            return "御馨"
        for suffix in ("产业有限公司", "有限公司", "股份有限公司", "产业公司"):
            value = value.replace(suffix, "")
        return value.strip() or "香驰"

    def _period_text(self, start: datetime, end: datetime) -> str:
        if start.year == end.year and start.month == end.month:
            return f"{start.year}年{start.month}月{start.day}日至{end.day}日"
        return f"{start:%Y年%m月%d日}至{end:%Y年%m月%d日}"

    def _normalize_title(self, value: str) -> str:
        return re.sub(r"[\W_]+", "", value, flags=re.UNICODE).lower()

    def _sanitize_markdown_link_labels(
        self,
        markdown: str,
        materials: list[dict[str, Any]],
    ) -> str:
        source_titles = {
            self._normalize_title(str(item.get("title") or ""))
            for item in materials
            if item.get("title")
        }

        material_links = [
            (
                self._normalize_title(str(item.get("title") or "")),
                str(item.get("source_url") or "").strip(),
            )
            for item in materials
            if item.get("title") and item.get("source_url")
        ]
        allowed_urls = {url for _title, url in material_links}

        def replace(match: re.Match[str]) -> str:
            label = match.group(1).strip()
            normalized_label = self._normalize_title(label)
            if len(label) > 22 and normalized_label in source_titles:
                cleaned = re.sub(r"^\[[^\]]{1,8}\]\s*", "", label)
                cleaned = re.split(
                    r"(?:--|__|_新浪|[-|｜]\s*(?:36氪|新浪|东方财富|中国咖啡网))",
                    cleaned,
                )[0]
                cleaned = re.sub(r"[，,:：；;。！？?!…]+$", "", cleaned).strip()
                if len(cleaned) > 22:
                    cleaned = cleaned[:22].rstrip("，,:：；;。！？?!… ")
                label = cleaned or label[:22]
                normalized_label = self._normalize_title(label)

            url = match.group(2).strip()
            if url not in allowed_urls:
                best_url = ""
                best_score = 0.0
                for normalized_title, source_url in material_links:
                    score = SequenceMatcher(None, normalized_label, normalized_title).ratio()
                    if score > best_score:
                        best_score = score
                        best_url = source_url
                if best_score < 0.42:
                    return label
                url = best_url
            return f"[{label}]({url})"

        return re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", replace, markdown)

    def _normalize_editorial_tone(self, markdown: str) -> str:
        replacements = (
            (r"娃哈哈治理真空致战略延缓", "娃哈哈家族诉讼影响集团治理"),
            (r"瑞幸自建烘焙厂收缩外采", "瑞幸加码自建烘焙产能"),
            (r"库迪激进拓店死磕瑞幸", "库迪加速便捷店渠道扩张"),
            (r"死磕", "竞争"),
            (r"引爆", "带动"),
            (r"撬动", "拓展"),
            (r"倒逼", "推动"),
            (r"强势碾压", "竞争领先"),
            (r"收缩外采", "推进供应链整合"),
            (r"致战略延缓", "牵动经营治理"),
            (r"采购需求将显著收缩", "采购结构可能发生变化"),
            (r"将显著增加对([^，。；\n]+)的采购需求", r"可能影响对\1的后续采购"),
            (r"直接带动对([^，。；\n]+)的需求", r"可能影响对\1的后续需求"),
            (r"直接挤压([^，。；\n]+)", r"可能影响\1"),
        )
        for pattern, replacement in replacements:
            markdown = re.sub(pattern, replacement, markdown)

        advice_pattern = re.compile("|".join(f"(?:{pattern})" for pattern in IMPLICIT_ADVICE_PATTERNS))
        inference_pattern = re.compile(
            "|".join(f"(?:{pattern})" for pattern in UNSUPPORTED_INFERENCE_PATTERNS)
        )
        normalized_lines: list[str] = []
        for line in markdown.splitlines():
            if (
                not line
                or line.startswith("#")
                or (advice_pattern.search(line) is None and inference_pattern.search(line) is None)
            ):
                normalized_lines.append(line)
                continue
            sentences = re.findall(r"[^。！？]+[。！？]?", line)
            kept = [
                sentence
                for sentence in sentences
                if advice_pattern.search(sentence) is None and inference_pattern.search(sentence) is None
            ]
            normalized_lines.append("".join(kept).strip())
        return self._split_long_paragraphs("\n".join(normalized_lines))

    @staticmethod
    def _split_long_paragraphs(markdown: str, *, max_chars: int = 480) -> str:
        """按完整句子拆分超长自然段，不改变事实、链接和章节结构。"""
        paragraphs = re.split(r"(\n\s*\n)", markdown)
        normalized: list[str] = []
        for paragraph in paragraphs:
            plain = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", paragraph).strip()
            if not plain or plain.startswith("#") or len(plain) <= max_chars:
                normalized.append(paragraph)
                continue
            sentences = re.findall(r"[^。！？]+[。！？]?", paragraph.strip())
            chunks: list[str] = []
            current = ""
            for sentence in sentences:
                candidate = f"{current}{sentence}"
                candidate_plain = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", candidate)
                if current and len(candidate_plain) > max_chars:
                    chunks.append(current.strip())
                    current = sentence
                else:
                    current = candidate
            if current.strip():
                chunks.append(current.strip())
            normalized.append("\n\n".join(chunks))
        return "".join(normalized)

    def _normalize_company_scope(self, markdown: str, company_name: str) -> str:
        """确定性移除竞对章节中的跨产业旁支句，避免模型返修不稳定。"""
        blocked_pattern: re.Pattern[str] | None = None
        if "御馨" in company_name:
            blocked_pattern = re.compile(r"(?:长安花|西王|菜籽油|玉米油)")
        elif "健源" in company_name:
            blocked_pattern = re.compile(r"(?:大豆蛋白|豆粕|豆油|植物蛋白)")
        if blocked_pattern is None:
            return markdown

        section_pattern = re.compile(r"(^# 竞对\s*$)([\s\S]*?)(?=^# )", flags=re.MULTILINE)

        def clean_section(match: re.Match[str]) -> str:
            sentences = re.findall(r"[^。！？\n]+[。！？]?|\n+", match.group(2))
            kept = [sentence for sentence in sentences if not blocked_pattern.search(sentence)]
            content = "".join(kept).strip()
            if not content:
                content = "本期暂无值得重点关注的新增动态"
            return f"{match.group(1)}\n\n{content}\n\n"

        return section_pattern.sub(clean_section, markdown, count=1)

    def _has_conflicting_url_year(self, source_url: str, publish_time: Any) -> bool:
        if not source_url or not isinstance(publish_time, datetime):
            return False
        years = {
            int(value)
            for value in re.findall(r"(?<!\d)(20\d{2})(?:[-/]|0[1-9]|1[0-2])", source_url)
        }
        return bool(years and publish_time.year not in years)

    def _json_value(self, value: Any) -> Any:
        return value.isoformat() if isinstance(value, datetime) else value


insight_feishu_brief_service = InsightFeishuBriefService()
