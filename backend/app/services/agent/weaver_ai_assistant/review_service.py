import json
from datetime import datetime
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import or_
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.llm_factory import LLMFactory
from app.core.logger import logger
from app.models.agent.weaver_ai_assistant import WeaverAiReviewRecord, WeaverAiReviewRule
from app.schemas.agent.weaver_ai_assistant import (
    WeaverReviewRecordRead,
    WeaverReviewRequest,
    WeaverReviewResponse,
    WeaverReviewResult,
    WeaverReviewRuleCreate,
    WeaverReviewRuleRead,
    WeaverReviewRuleUpdate,
)


class WeaverAiReviewService:
    """泛微流程 AI 智审服务。"""

    async def list_rules(
        self,
        db: AsyncSession,
        env: str,
        workflow_id: str,
        node_id: str | None = None,
        reviewer_user_id: str | None = None,
    ) -> list[WeaverReviewRuleRead]:
        statement = (
            select(WeaverAiReviewRule)
            .where(
                WeaverAiReviewRule.env == self.normalize_env(env),
                WeaverAiReviewRule.workflow_id == str(workflow_id),
                WeaverAiReviewRule.is_deleted == 0,
            )
            .order_by(WeaverAiReviewRule.priority.asc(), WeaverAiReviewRule.id.asc())
        )
        rows = list((await db.exec(statement)).all())
        if node_id:
            rows = [row for row in rows if not row.node_id or row.node_id == str(node_id)]
        if reviewer_user_id:
            rows = [row for row in rows if not row.reviewer_user_id or row.reviewer_user_id == str(reviewer_user_id)]
        return [self.to_rule_read(row) for row in rows]

    async def create_rule(self, db: AsyncSession, payload: WeaverReviewRuleCreate) -> WeaverReviewRuleRead:
        row = WeaverAiReviewRule(
            env=self.normalize_env(payload.env),
            workflow_id=str(payload.workflow_id),
            workflow_name=payload.workflow_name,
            node_id=self.empty_to_none(payload.node_id),
            node_name=self.empty_to_none(payload.node_name),
            reviewer_user_id=self.empty_to_none(payload.reviewer_user_id),
            reviewer_name=self.empty_to_none(payload.reviewer_name),
            rule_title=payload.rule_title.strip(),
            rule_content=payload.rule_content.strip(),
            tool_config=self.clean_json(payload.tool_config),
            auto_review_mode=payload.auto_review_mode,
            enabled=payload.enabled,
            priority=payload.priority,
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return self.to_rule_read(row)

    async def update_rule(
        self,
        db: AsyncSession,
        rule_id: int,
        payload: WeaverReviewRuleUpdate,
    ) -> WeaverReviewRuleRead | None:
        row = await db.get(WeaverAiReviewRule, rule_id)
        if not row or row.is_deleted:
            return None

        update_data = payload.model_dump(exclude_unset=True, by_alias=False)
        if "workflow_name" in update_data:
            row.workflow_name = payload.workflow_name
        if "node_id" in update_data:
            row.node_id = self.empty_to_none(payload.node_id)
        if "node_name" in update_data:
            row.node_name = self.empty_to_none(payload.node_name)
        if "reviewer_user_id" in update_data:
            row.reviewer_user_id = self.empty_to_none(payload.reviewer_user_id)
        if "reviewer_name" in update_data:
            row.reviewer_name = self.empty_to_none(payload.reviewer_name)
        if payload.rule_title is not None:
            row.rule_title = payload.rule_title.strip()
        if payload.rule_content is not None:
            row.rule_content = payload.rule_content.strip()
        if "tool_config" in update_data:
            row.tool_config = self.clean_json(payload.tool_config)
        if payload.auto_review_mode is not None:
            row.auto_review_mode = payload.auto_review_mode
        if payload.enabled is not None:
            row.enabled = payload.enabled
        if payload.priority is not None:
            row.priority = payload.priority
        row.update_time = datetime.now()
        await db.commit()
        await db.refresh(row)
        return self.to_rule_read(row)

    async def delete_rule(self, db: AsyncSession, rule_id: int) -> bool:
        row = await db.get(WeaverAiReviewRule, rule_id)
        if not row or row.is_deleted:
            return False
        row.is_deleted = 1
        row.update_time = datetime.now()
        await db.commit()
        return True

    async def pre_review(self, db: AsyncSession, payload: WeaverReviewRequest) -> WeaverReviewResponse:
        env = self.normalize_env(payload.context.env)
        workflow_id = self.workflow_id(payload)
        request_id = self.text(payload.context.base_info.get("requestid") or payload.context.base_info.get("requestId"))
        node_id = self.text(payload.current_node_id or payload.context.base_info.get("nodeid") or payload.context.base_info.get("nodeId"))
        node_name = self.text(payload.current_node_name)
        reviewer_user_id = self.text(payload.reviewer.user_id if payload.reviewer else None)
        rules = await self.load_enabled_rules(db, env, workflow_id, node_id, reviewer_user_id)

        result = await self.invoke_review_model(payload, rules)
        record = WeaverAiReviewRecord(
            env=env,
            workflow_id=workflow_id,
            workflow_name=self.text(payload.context.base_info.get("workflowname") or payload.context.base_info.get("workflowName")),
            request_id=request_id or None,
            node_id=node_id or None,
            node_name=node_name or None,
            trigger_type=payload.trigger_type,
            submitter_user_id=self.text(payload.submitter.user_id if payload.submitter else None) or None,
            submitter_name=self.text(payload.submitter.user_name if payload.submitter else None) or None,
            reviewer_user_id=reviewer_user_id or None,
            reviewer_name=self.text(payload.reviewer.user_name if payload.reviewer else None) or None,
            risk_level=result.risk_level,
            decision_suggestion=result.decision_suggestion,
            summary=result.summary,
            suggested_opinion=result.suggested_opinion,
            confidence=result.confidence,
            can_auto_approve=result.can_auto_approve,
            rule_snapshot=[rule.model_dump(by_alias=True) for rule in rules],
            form_snapshot=payload.model_dump(by_alias=True),
            review_result=result.model_dump(by_alias=True),
            status="completed",
        )
        db.add(record)
        await db.commit()
        await db.refresh(record)

        logger.info(
            "泛微流程 AI 智审完成: "
            f"env={env}, workflow_id={workflow_id}, request_id={request_id}, "
            f"node_id={node_id}, risk={result.risk_level}, suggestion={result.decision_suggestion}"
        )
        return WeaverReviewResponse(
            record=self.to_record_read(record),
            result=result,
            matchedRules=rules,
        )

    async def latest_record(
        self,
        db: AsyncSession,
        env: str,
        workflow_id: str,
        request_id: str | None = None,
        node_id: str | None = None,
    ) -> WeaverReviewRecordRead | None:
        statement = (
            select(WeaverAiReviewRecord)
            .where(
                WeaverAiReviewRecord.env == self.normalize_env(env),
                WeaverAiReviewRecord.workflow_id == str(workflow_id),
                WeaverAiReviewRecord.is_deleted == 0,
            )
            .order_by(WeaverAiReviewRecord.create_time.desc(), WeaverAiReviewRecord.id.desc())
            .limit(1)
        )
        if request_id:
            statement = statement.where(WeaverAiReviewRecord.request_id == str(request_id))
        if node_id:
            statement = statement.where(WeaverAiReviewRecord.node_id == str(node_id))
        row = (await db.exec(statement)).first()
        return self.to_record_read(row) if row else None

    async def load_enabled_rules(
        self,
        db: AsyncSession,
        env: str,
        workflow_id: str,
        node_id: str | None,
        reviewer_user_id: str | None,
    ) -> list[WeaverReviewRuleRead]:
        statement = (
            select(WeaverAiReviewRule)
            .where(
                WeaverAiReviewRule.env == self.normalize_env(env),
                WeaverAiReviewRule.workflow_id == str(workflow_id),
                WeaverAiReviewRule.enabled == True,  # noqa: E712
                WeaverAiReviewRule.status == "active",
                WeaverAiReviewRule.is_deleted == 0,
                or_(WeaverAiReviewRule.node_id.is_(None), WeaverAiReviewRule.node_id == "", WeaverAiReviewRule.node_id == str(node_id or "")),
                or_(
                    WeaverAiReviewRule.reviewer_user_id.is_(None),
                    WeaverAiReviewRule.reviewer_user_id == "",
                    WeaverAiReviewRule.reviewer_user_id == str(reviewer_user_id or ""),
                ),
            )
            .order_by(WeaverAiReviewRule.priority.asc(), WeaverAiReviewRule.id.asc())
            .limit(30)
        )
        rows = list((await db.exec(statement)).all())
        return [self.to_rule_read(row) for row in rows]

    async def invoke_review_model(
        self,
        payload: WeaverReviewRequest,
        rules: list[WeaverReviewRuleRead],
    ) -> WeaverReviewResult:
        prompt_payload = {
            "triggerType": payload.trigger_type,
            "operation": payload.operation,
            "currentNodeId": payload.current_node_id,
            "currentNodeName": payload.current_node_name,
            "submitter": payload.submitter.model_dump(by_alias=True) if payload.submitter else None,
            "reviewer": payload.reviewer.model_dump(by_alias=True) if payload.reviewer else None,
            "comment": payload.comment,
            "extra": payload.extra,
            "context": payload.context.model_dump(by_alias=True),
            "reviewRules": [rule.model_dump(by_alias=True) for rule in rules],
        }
        messages = [
            SystemMessage(
                content=(
                    "你是泛微 E-cology 流程 AI 智审助手，只做预审建议和风险识别。"
                    "你必须根据当前表单字段、审批节点、审批人规则和历史上下文判断是否存在缺失材料、逻辑矛盾、金额/日期/权限/附件风险。"
                    "你不能声称已经审批、提交、退回或通过流程，也不能输出 JavaScript。"
                    "如果没有配置智审规则，也要基于表单内容做通用合规检查，但必须说明依据有限。"
                    "如果规则启用了 autoReviewMode=auto，也只能在风险等级 low、检查项无 fail、材料无缺失且置信度较高时把 canAutoApprove 设为 true。"
                    "输出必须是 JSON，不要 Markdown。字段："
                    "summary, riskLevel(low/medium/high/blocked), decisionSuggestion(approve/return/reject/supplement/manual_review), "
                    "suggestedOpinion, checks[{name,status(pass/warning/fail/unknown),detail}], missingMaterials[], concerns[], confidence, canAutoApprove。"
                )
            ),
            HumanMessage(content=json.dumps(prompt_payload, ensure_ascii=False)),
        ]
        try:
            response = await self.invoke_model(messages)
            payload_json = self.parse_json_content(self.text(getattr(response, "content", response)))
            return self.normalize_review_result(payload_json, rules)
        except Exception as exc:
            logger.warning(f"泛微流程 AI 智审模型调用失败，使用保守结果: {LLMFactory.describe_invocation_error(exc)}")
            return WeaverReviewResult(
                summary="AI 智审暂时不可用，建议转人工检查当前流程材料、字段完整性和审批权限。",
                riskLevel="medium",
                decisionSuggestion="manual_review",
                suggestedOpinion="建议人工复核后再处理。",
                checks=[
                    {
                        "name": "AI 智审服务",
                        "status": "warning",
                        "detail": "模型调用失败，未能完成自动预审。",
                    }
                ],
                missingMaterials=[],
                concerns=["AI 智审服务暂时不可用"],
                confidence=0,
                canAutoApprove=False,
            )

    async def invoke_model(self, messages: list[Any]) -> Any:
        model_name = settings.WEAVER_AI_MODEL_NAME.strip()
        if model_name:
            model = await LLMFactory.get_model_by_name(
                model_name,
                streaming=False,
                json_mode=True,
                temperature=0,
                enable_reasoning=settings.WEAVER_AI_ENABLE_REASONING,
            )
        else:
            model = await LLMFactory.get_model(
                capability=settings.WEAVER_AI_MODEL_CAPABILITY or "complex-reasoning",
                streaming=False,
                json_mode=True,
                temperature=0,
                enable_reasoning=settings.WEAVER_AI_ENABLE_REASONING,
            )
        return await model.ainvoke(messages)

    def normalize_review_result(self, value: dict[str, Any], rules: list[WeaverReviewRuleRead]) -> WeaverReviewResult:
        auto_allowed = any(rule.auto_review_mode == "auto" for rule in rules)
        checks = value.get("checks") if isinstance(value.get("checks"), list) else []
        missing = value.get("missingMaterials") or value.get("missing_materials") or []
        concerns = value.get("concerns") if isinstance(value.get("concerns"), list) else []
        risk_level = self.choice(value.get("riskLevel") or value.get("risk_level"), {"low", "medium", "high", "blocked"}, "medium")
        decision = self.choice(
            value.get("decisionSuggestion") or value.get("decision_suggestion"),
            {"approve", "return", "reject", "supplement", "manual_review"},
            "manual_review",
        )
        confidence = self.to_float(value.get("confidence"))
        has_failed_check = any(isinstance(item, dict) and item.get("status") == "fail" for item in checks)
        can_auto_approve = bool(
            auto_allowed
            and risk_level == "low"
            and decision == "approve"
            and not missing
            and not has_failed_check
            and (confidence is None or confidence >= 0.8)
            and value.get("canAutoApprove") is True
        )
        return WeaverReviewResult(
            summary=self.text(value.get("summary")) or "已完成 AI 预审，请结合实际业务复核。",
            riskLevel=risk_level,
            decisionSuggestion=decision,
            suggestedOpinion=self.text(value.get("suggestedOpinion") or value.get("suggested_opinion")) or None,
            checks=[
                {
                    "name": self.text(item.get("name")) or "检查项",
                    "status": self.choice(item.get("status"), {"pass", "warning", "fail", "unknown"}, "unknown"),
                    "detail": self.text(item.get("detail")),
                }
                for item in checks
                if isinstance(item, dict)
            ][:20],
            missingMaterials=[self.text(item) for item in missing if self.text(item)][:20] if isinstance(missing, list) else [],
            concerns=[self.text(item) for item in concerns if self.text(item)][:20] if isinstance(concerns, list) else [],
            confidence=confidence,
            canAutoApprove=can_auto_approve,
        )

    def parse_json_content(self, content: str) -> dict[str, Any]:
        text = (content or "").strip()
        if text.startswith("```"):
            text = text.strip("`")
            text = text[4:].strip() if text.lower().startswith("json") else text.strip()
        try:
            value = json.loads(text)
        except Exception:
            match = re_search_json(text)
            if not match:
                raise
            value = json.loads(match)
        if not isinstance(value, dict):
            raise ValueError("智审模型未返回 JSON 对象")
        return value

    def to_rule_read(self, row: WeaverAiReviewRule) -> WeaverReviewRuleRead:
        return WeaverReviewRuleRead(
            id=row.id or 0,
            env=row.env,
            workflowId=row.workflow_id,
            workflowName=row.workflow_name,
            nodeId=row.node_id,
            nodeName=row.node_name,
            reviewerUserId=row.reviewer_user_id,
            reviewerName=row.reviewer_name,
            ruleTitle=row.rule_title,
            ruleContent=row.rule_content,
            toolConfig=row.tool_config or {},
            autoReviewMode=row.auto_review_mode,
            enabled=row.enabled,
            priority=row.priority,
            status=row.status,
        )

    def to_record_read(self, row: WeaverAiReviewRecord) -> WeaverReviewRecordRead:
        return WeaverReviewRecordRead(
            id=row.id or 0,
            env=row.env,
            workflowId=row.workflow_id,
            workflowName=row.workflow_name,
            requestId=row.request_id,
            nodeId=row.node_id,
            nodeName=row.node_name,
            triggerType=row.trigger_type,
            submitterUserId=row.submitter_user_id,
            submitterName=row.submitter_name,
            reviewerUserId=row.reviewer_user_id,
            reviewerName=row.reviewer_name,
            riskLevel=row.risk_level,
            decisionSuggestion=row.decision_suggestion,
            summary=row.summary,
            suggestedOpinion=row.suggested_opinion,
            confidence=row.confidence,
            canAutoApprove=row.can_auto_approve,
            reviewResult=row.review_result or {},
            status=row.status,
        )

    def workflow_id(self, payload: WeaverReviewRequest) -> str:
        value = payload.context.base_info.get("workflowid") or payload.context.base_info.get("workflowId")
        return self.text(value)

    def normalize_env(self, env: str | None) -> str:
        value = (env or settings.WEAVER_DEFAULT_ENV or "default").strip()
        return value or "default"

    def clean_json(self, value: dict[str, Any] | None) -> dict[str, Any]:
        if not isinstance(value, dict):
            return {}
        return {str(key): item for key, item in value.items() if item not in (None, "")}

    def empty_to_none(self, value: Any) -> str | None:
        text = self.text(value).strip()
        return text or None

    def text(self, value: Any) -> str:
        return "" if value is None else str(value)

    def to_float(self, value: Any) -> float | None:
        try:
            return float(value)
        except Exception:
            return None

    def choice(self, value: Any, allowed: set[str], default: str) -> str:
        text = self.text(value).strip()
        return text if text in allowed else default


def re_search_json(text: str) -> str | None:
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    return text[start : end + 1]


weaver_ai_review_service = WeaverAiReviewService()
