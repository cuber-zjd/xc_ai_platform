import asyncio
import json
import re
from datetime import datetime
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import or_
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.llm_factory import LLMFactory
from app.core.logger import logger
from app.models.agent.weaver_ai_assistant import (
    WeaverAiReviewNodeConfig,
    WeaverAiReviewRecord,
    WeaverAiReviewRule,
    WeaverAiReviewTestRecord,
)
from app.schemas.agent.weaver_ai_assistant import (
    WeaverFieldConfigResponse,
    WeaverFieldContext,
    WeaverFormContext,
    WeaverReviewNodeConfigRead,
    WeaverReviewNodeConfigUpdate,
    WeaverReviewNodeStatus,
    WeaverReviewActor,
    WeaverReviewRecordRead,
    WeaverReviewRequest,
    WeaverReviewResponse,
    WeaverReviewResult,
    WeaverReviewRuleCreate,
    WeaverReviewRuleRead,
    WeaverReviewRuleUpdate,
    WeaverReviewTestRequest,
    WeaverReviewTestResponse,
)
from app.services.agent.weaver_ai_assistant.assistant_service import weaver_ai_assistant_service
from app.services.agent.weaver_ai_assistant.review_evidence_service import weaver_review_evidence_service


class WeaverReviewNodeDisabledError(PermissionError):
    """当前流程节点未开启对应的智审方式。"""


class WeaverAiReviewService:
    """泛微流程 AI 智审服务。"""

    IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

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
            general_check_enabled=payload.general_check_enabled,
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
        if payload.general_check_enabled is not None:
            row.general_check_enabled = payload.general_check_enabled
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

    async def list_node_configs(
        self,
        db: AsyncSession,
        env: str,
        workflow_id: str,
    ) -> list[WeaverReviewNodeConfigRead]:
        statement = (
            select(WeaverAiReviewNodeConfig)
            .where(
                WeaverAiReviewNodeConfig.env == self.normalize_env(env),
                WeaverAiReviewNodeConfig.workflow_id == str(workflow_id),
                WeaverAiReviewNodeConfig.is_deleted == 0,
            )
            .order_by(WeaverAiReviewNodeConfig.id.asc())
        )
        rows = list((await db.exec(statement)).all())
        return [self.to_node_config_read(row) for row in rows]

    async def upsert_node_config(
        self,
        db: AsyncSession,
        payload: WeaverReviewNodeConfigUpdate,
    ) -> WeaverReviewNodeConfigRead:
        env = self.normalize_env(payload.env)
        workflow_id = str(payload.workflow_id).strip()
        node_id = str(payload.node_id).strip()
        if not workflow_id or not node_id:
            raise ValueError("流程 ID 和节点 ID 不能为空")

        statement = select(WeaverAiReviewNodeConfig).where(
            WeaverAiReviewNodeConfig.env == env,
            WeaverAiReviewNodeConfig.workflow_id == workflow_id,
            WeaverAiReviewNodeConfig.node_id == node_id,
        )
        row = (await db.exec(statement)).first()
        if row is None:
            row = WeaverAiReviewNodeConfig(env=env, workflow_id=workflow_id, node_id=node_id)
            db.add(row)

        row.workflow_name = self.empty_to_none(payload.workflow_name)
        row.node_name = self.empty_to_none(payload.node_name)
        row.enabled = payload.enabled
        row.show_entry = payload.show_entry if payload.enabled else False
        row.automatic_review_enabled = payload.automatic_review_enabled if payload.enabled else False
        row.status = "active"
        row.is_deleted = 0
        row.update_time = datetime.now()
        await db.commit()
        await db.refresh(row)
        return self.to_node_config_read(row)

    async def get_node_status(
        self,
        db: AsyncSession,
        env: str,
        workflow_id: str,
        node_id: str,
    ) -> WeaverReviewNodeStatus:
        normalized_env = self.normalize_env(env)
        normalized_workflow_id = str(workflow_id).strip()
        normalized_node_id = str(node_id).strip()
        statement = select(WeaverAiReviewNodeConfig).where(
            WeaverAiReviewNodeConfig.env == normalized_env,
            WeaverAiReviewNodeConfig.workflow_id == normalized_workflow_id,
            WeaverAiReviewNodeConfig.node_id == normalized_node_id,
            WeaverAiReviewNodeConfig.status == "active",
            WeaverAiReviewNodeConfig.is_deleted == 0,
        )
        row = (await db.exec(statement)).first()
        enabled = bool(row and row.enabled)
        return WeaverReviewNodeStatus(
            env=normalized_env,
            workflowId=normalized_workflow_id,
            nodeId=normalized_node_id,
            configured=row is not None,
            enabled=enabled,
            showEntry=bool(enabled and row and row.show_entry),
            automaticReviewEnabled=bool(enabled and row and row.automatic_review_enabled),
        )

    async def ensure_node_review_enabled(
        self,
        db: AsyncSession,
        env: str,
        workflow_id: str,
        node_id: str,
        trigger_type: str,
    ) -> WeaverReviewNodeStatus:
        if not str(node_id).strip():
            raise WeaverReviewNodeDisabledError("未识别当前审批节点，AI 智审未执行")
        node_status = await self.get_node_status(db, env, workflow_id, node_id)
        if not node_status.enabled:
            raise WeaverReviewNodeDisabledError("当前节点未在智审配置页启用，AI 智审未执行")
        if trigger_type in {"submit", "action"} and not node_status.automatic_review_enabled:
            raise WeaverReviewNodeDisabledError("当前节点未开启自动预审，AI 智审未执行")
        return node_status

    async def pre_review(self, db: AsyncSession, payload: WeaverReviewRequest) -> WeaverReviewResponse:
        env = self.normalize_env(payload.context.env)
        workflow_id = self.workflow_id(payload)
        request_id = self.text(payload.context.base_info.get("requestid") or payload.context.base_info.get("requestId"))
        node_id = self.text(payload.current_node_id or payload.context.base_info.get("nodeid") or payload.context.base_info.get("nodeId"))
        node_name = self.text(payload.current_node_name)
        reviewer_user_id = self.text(payload.reviewer.user_id if payload.reviewer else None)
        await self.ensure_node_review_enabled(db, env, workflow_id, node_id, payload.trigger_type)
        rules = await self.load_enabled_rules(db, env, workflow_id, node_id, reviewer_user_id)

        tool_evidence = await weaver_review_evidence_service.collect(payload, rules)
        result = await self.invoke_review_model(payload, rules, tool_evidence)
        result = self.merge_tool_evidence(result, tool_evidence)
        form_snapshot = self.to_json_compatible(payload.model_dump(by_alias=True))
        if tool_evidence:
            form_snapshot["reviewEvidence"] = self.to_json_compatible(tool_evidence)
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
            form_snapshot=form_snapshot,
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

    async def test_review(self, db: AsyncSession, payload: WeaverReviewTestRequest) -> WeaverReviewTestResponse:
        env = self.normalize_env(payload.env)
        workflow_id = str(payload.workflow_id).strip()
        request_id = str(payload.request_id).strip()
        metadata = await weaver_ai_assistant_service.get_field_config(workflow_id, env)
        context, extra, source_node_id, source_node_name = await asyncio.to_thread(
            self._load_test_request_context,
            env,
            workflow_id,
            request_id,
            metadata,
        )
        review_request = WeaverReviewRequest(
            context=context,
            triggerType="manual",
            operation="test_review",
            currentNodeId=None,
            currentNodeName="测试审批（忽略当前节点）",
            extra=extra,
        )
        rules = await self.load_all_enabled_rules_for_test(db, env, workflow_id)
        tool_evidence = await weaver_review_evidence_service.collect(review_request, rules)
        result = await self.invoke_review_model(review_request, rules, tool_evidence)
        result = self.merge_tool_evidence(result, tool_evidence)
        form_snapshot = self.to_json_compatible(review_request.model_dump(by_alias=True))
        if tool_evidence:
            form_snapshot["reviewEvidence"] = self.to_json_compatible(tool_evidence)

        record = WeaverAiReviewTestRecord(
            env=env,
            workflow_id=workflow_id,
            workflow_name=metadata.workflow_name or payload.workflow_name,
            request_id=request_id,
            source_node_id=source_node_id or None,
            source_node_name=source_node_name or None,
            risk_level=result.risk_level,
            decision_suggestion=result.decision_suggestion,
            summary=result.summary,
            suggested_opinion=result.suggested_opinion,
            confidence=result.confidence,
            can_auto_approve=result.can_auto_approve,
            rule_snapshot=[rule.model_dump(by_alias=True) for rule in rules],
            form_snapshot=form_snapshot,
            review_result=result.model_dump(by_alias=True),
            status="completed",
        )
        db.add(record)
        await db.commit()
        await db.refresh(record)
        logger.info(
            "泛微流程 AI 测试智审完成: "
            f"env={env}, workflow_id={workflow_id}, request_id={request_id}, "
            f"source_node_id={source_node_id}, risk={result.risk_level}"
        )
        return WeaverReviewTestResponse(
            record=self.to_test_record_read(record),
            result=result,
            matchedRules=rules,
            sourceNodeId=source_node_id or None,
            sourceNodeName=source_node_name or None,
        )

    async def build_scheduled_review_request(
        self,
        *,
        env: str,
        workflow_id: str,
        request_id: str,
        node_id: str,
        node_name: str,
        reviewer_user_id: str,
        reviewer_name: str,
    ) -> WeaverReviewRequest:
        metadata = await weaver_ai_assistant_service.get_field_config(workflow_id, env)
        context, extra, source_node_id, source_node_name = await asyncio.to_thread(
            self._load_test_request_context,
            env,
            workflow_id,
            request_id,
            metadata,
        )
        if source_node_id != node_id:
            raise ValueError(
                f"流程已离开待扫描节点：预期节点 {node_id}，当前节点 {source_node_id or '未知'}"
            )
        context.base_info["nodeid"] = node_id
        context.base_info["nodename"] = node_name or source_node_name
        extra.update(
            {
                "testMode": False,
                "ignoreCurrentNode": False,
                "scheduledReview": True,
            }
        )
        return WeaverReviewRequest(
            context=context,
            triggerType="action",
            operation="scheduled_pre_review",
            currentNodeId=node_id,
            currentNodeName=node_name or source_node_name or None,
            reviewer=WeaverReviewActor(
                userId=reviewer_user_id or None,
                userName=reviewer_name or None,
            ),
            extra=extra,
        )

    async def load_all_enabled_rules_for_test(
        self,
        db: AsyncSession,
        env: str,
        workflow_id: str,
    ) -> list[WeaverReviewRuleRead]:
        statement = (
            select(WeaverAiReviewRule)
            .where(
                WeaverAiReviewRule.env == self.normalize_env(env),
                WeaverAiReviewRule.workflow_id == str(workflow_id),
                WeaverAiReviewRule.enabled == True,  # noqa: E712
                WeaverAiReviewRule.status == "active",
                WeaverAiReviewRule.is_deleted == 0,
            )
            .order_by(WeaverAiReviewRule.priority.asc(), WeaverAiReviewRule.id.asc())
            .limit(100)
        )
        return [self.to_rule_read(row) for row in (await db.exec(statement)).all()]

    def _resolve_field_display_value(self, field: Any, value: Any) -> Any:
        """将泛微选择字段的数据库值还原为页面展示文本。"""
        if value in (None, "") or not getattr(field, "options", None):
            return value

        option_labels = {
            self.text(option.value).strip(): self.text(option.label).strip()
            for option in field.options
            if self.text(option.value).strip()
        }
        raw_value = self.text(value).strip()
        if raw_value in option_labels:
            return option_labels[raw_value]

        parts = [item.strip() for item in raw_value.split(",") if item.strip()]
        if parts and all(item in option_labels for item in parts):
            return ",".join(option_labels[item] for item in parts)
        return value

    def _load_test_request_context(
        self,
        env: str,
        workflow_id: str,
        request_id: str,
        metadata: WeaverFieldConfigResponse,
    ) -> tuple[WeaverFormContext, dict[str, Any], str, str]:
        db_config = weaver_ai_assistant_service._get_weaver_db_config(env)
        if not db_config:
            raise ValueError(f"未配置泛微数据库环境：{env}")
        with weaver_ai_assistant_service._connect_weaver_mysql(db_config) as conn:
            with conn.cursor() as cursor:
                request_row = weaver_ai_assistant_service._fetch_one(
                    cursor,
                    """
                    SELECT rb.requestid, rb.workflowid, rb.currentnodeid, rb.requestname,
                           rb.creater, rb.createdate, rb.createtime, nb.nodename
                    FROM workflow_requestbase rb
                    LEFT JOIN workflow_nodebase nb ON nb.id = rb.currentnodeid
                    WHERE rb.requestid = %s
                    """,
                    (request_id,),
                )
                if not request_row:
                    raise ValueError(f"未找到 requestId={request_id} 的流程请求")
                actual_workflow_id = self.text(request_row.get("workflowid"))
                if actual_workflow_id != workflow_id:
                    raise ValueError(
                        f"requestId={request_id} 属于流程 {actual_workflow_id}，与当前配置流程 {workflow_id} 不一致"
                    )

                main_table = self._safe_identifier(metadata.main_table, "流程主表")
                main_row = weaver_ai_assistant_service._fetch_one(
                    cursor,
                    f"SELECT * FROM `{main_table}` WHERE `requestid` = %s ORDER BY `id` DESC LIMIT 1",
                    (request_id,),
                )
                if not main_row:
                    raise ValueError(f"流程主表未找到 requestId={request_id} 的表单数据")

                field_contexts: dict[str, WeaverFieldContext] = {}
                detail_field_groups: dict[str, list[Any]] = {}
                for field in metadata.fields:
                    if field.detail_table:
                        detail_field_groups.setdefault(field.detail_table, []).append(field)
                        continue
                    value = main_row.get(self.text(field.field_name).lower())
                    display_value = self._resolve_field_display_value(field, value)
                    field_contexts[field.field_id] = WeaverFieldContext(
                        label=field.label,
                        fieldId=field.field_id,
                        type=field.type,
                        writable=False,
                        value=value,
                        displayValue=display_value,
                        options=field.options,
                        visible=True,
                        readonlyReason="测试智审从泛微数据库读取",
                    )

                detail_rows: dict[str, list[dict[str, Any]]] = {}
                main_id = main_row.get("id")
                detail_key = self._safe_identifier(metadata.detail_key_field or "mainid", "明细关联字段")
                for table_name, fields in detail_field_groups.items():
                    safe_table = self._safe_identifier(table_name, "流程明细表")
                    rows = weaver_ai_assistant_service._fetch_all(
                        cursor,
                        f"SELECT * FROM `{safe_table}` WHERE `{detail_key}` = %s ORDER BY `id` LIMIT 500",
                        (main_id,),
                    )
                    detail_rows[safe_table] = [
                        {
                            field.label: row.get(self.text(field.field_name).lower())
                            for field in fields
                        }
                        for row in rows
                    ]

        source_node_id = self.text(request_row.get("currentnodeid"))
        source_node_name = self.text(request_row.get("nodename"))
        base_info = {
            "requestid": request_id,
            "workflowid": workflow_id,
            "workflowname": metadata.workflow_name or "",
            "requestname": self.text(request_row.get("requestname")),
            "currentnodeid": source_node_id,
            "currentnodename": source_node_name,
            "creater": self.text(request_row.get("creater")),
            "createdate": self.text(request_row.get("createdate")),
            "createtime": self.text(request_row.get("createtime")),
        }
        context = WeaverFormContext(
            env=env,
            baseInfo=base_info,
            fields=field_contexts,
        )
        extra = {
            "testMode": True,
            "ignoreCurrentNode": True,
            "sourceCurrentNodeId": source_node_id,
            "sourceCurrentNodeName": source_node_name,
            "detailRows": detail_rows,
        }
        return context, extra, source_node_id, source_node_name

    def _safe_identifier(self, value: Any, label: str) -> str:
        identifier = self.text(value).strip()
        if not identifier or not self.IDENTIFIER_PATTERN.fullmatch(identifier):
            raise ValueError(f"{label}不合法")
        return identifier

    async def latest_record(
        self,
        db: AsyncSession,
        env: str,
        workflow_id: str,
        request_id: str | None = None,
        node_id: str | None = None,
        reviewer_user_id: str | None = None,
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
        if reviewer_user_id:
            statement = statement.where(
                or_(
                    WeaverAiReviewRecord.reviewer_user_id == str(reviewer_user_id),
                    WeaverAiReviewRecord.reviewer_user_id.is_(None),
                    WeaverAiReviewRecord.reviewer_user_id == "",
                )
            )
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
        tool_evidence: list[dict[str, Any]],
    ) -> WeaverReviewResult:
        general_check_enabled = any(rule.general_check_enabled for rule in rules)
        context_payload = payload.context.model_dump(by_alias=True)
        extra_payload = payload.extra
        if not general_check_enabled and tool_evidence:
            context_payload = {
                "env": context_payload.get("env"),
                "baseInfo": context_payload.get("baseInfo") or {},
                "url": context_payload.get("url") or "",
                "fields": {},
            }
            extra_payload = {
                key: value
                for key, value in payload.extra.items()
                if key in {"testMode", "requestId", "workflowId", "workflowName"}
            }
        prompt_payload = {
            "triggerType": payload.trigger_type,
            "operation": payload.operation,
            "currentNodeId": payload.current_node_id,
            "currentNodeName": payload.current_node_name,
            "submitter": payload.submitter.model_dump(by_alias=True) if payload.submitter else None,
            "reviewer": payload.reviewer.model_dump(by_alias=True) if payload.reviewer else None,
            "comment": payload.comment,
            "extra": extra_payload,
            "context": context_payload,
            "reviewRules": [rule.model_dump(by_alias=True) for rule in rules],
            "toolEvidence": tool_evidence,
            "reviewScope": {"generalCheckEnabled": general_check_enabled},
        }
        messages = [
            SystemMessage(
                content=(
                    "你是泛微 E-cology 流程 AI 智审助手，只做预审建议和风险识别。"
                    "reviewScope.generalCheckEnabled 决定检查边界。为 false 时，只能检查 reviewRules 明确要求的事项和 toolEvidence，"
                    "不得检查或评论规则未要求的其他字段、空值、材料、合同、科目、利润中心、固定资产或通用合规风险。"
                    "为 true 时，才可以在规则检查之外，根据当前表单字段补充通用合规检查。"
                    "你不能声称已经审批、提交、退回或通过流程，也不能输出 JavaScript。"
                    "如果没有配置智审规则且通用检查关闭，只能说明当前没有可执行的智审规则，不能自行扩展检查范围。"
                    "toolEvidence 是平台只读工具取得的确定性业务证据，必须优先采用；不得把工具明确判定的不一致改写为通过。"
                    "context.fields 为空或缺少字段只表示 ecode 未采集到页面组件，不能据此断言业务字段为空、材料缺失或数据不一致；"
                    "若 toolEvidence 已从泛微流程数据库取得关联数据，应以该证据为准。不得编造工具证据和当前上下文中都不存在的合同、供应商、金额或字段缺失问题。"
                    "如果规则启用了 autoReviewMode=auto，也只能在风险等级 low、检查项无 fail、材料无缺失且置信度较高时把 canAutoApprove 设为 true。"
                    "输出必须是 JSON，不要 Markdown。字段："
                    "summary, riskLevel(low/medium/high/blocked), decisionSuggestion(approve/return/reject/supplement/manual_review), "
                    "suggestedOpinion, checks[{name,status(pass/warning/fail/unknown),detail}], missingMaterials[], concerns[], confidence, canAutoApprove。"
                )
            ),
            HumanMessage(content=json.dumps(prompt_payload, ensure_ascii=False, default=str)),
        ]
        try:
            response = await self.invoke_model(messages)
            payload_json = self.parse_json_content(self.text(getattr(response, "content", response)))
            result = self.normalize_review_result(payload_json, rules)
            if not general_check_enabled and tool_evidence:
                result.checks = []
                result.missing_materials = []
                result.concerns = []
            return result
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

    def merge_tool_evidence(
        self,
        result: WeaverReviewResult,
        evidence: list[dict[str, Any]],
    ) -> WeaverReviewResult:
        if not evidence:
            return result

        evidence_checks: list[dict[str, str]] = []
        evidence_concerns: list[str] = []
        comparison_tables: list[dict[str, Any]] = []
        evidence_statuses: set[str] = set()
        for item in evidence:
            evidence_statuses.add(self.text(item.get("status")))
            for check in item.get("checks") or []:
                if isinstance(check, dict):
                    evidence_checks.append(
                        {
                            "name": self.text(check.get("name")) or "外部数据核验",
                            "status": self.choice(check.get("status"), {"pass", "warning", "fail", "unknown"}, "unknown"),
                            "detail": self.text(check.get("detail")),
                        }
                    )
            for concern in item.get("concerns") or []:
                text = self.text(concern)
                if text:
                    evidence_concerns.append(text)
            facts = item.get("facts") if isinstance(item.get("facts"), dict) else {}
            comparison_rows = facts.get("comparisonRows") if isinstance(facts.get("comparisonRows"), list) else []
            if comparison_rows:
                comparison_tables.append(
                    {
                        "title": "发票与对账单明细对比",
                        "reconciliationNumber": self.text(facts.get("reconciliationNumber")) or None,
                        "invoiceNumbers": [self.text(value) for value in facts.get("invoiceNumbers") or [] if self.text(value)],
                        "invoiceTotal": self.text(facts.get("invoiceTotal")) or None,
                        "reconciliationTotal": self.text(facts.get("reconciliationTotal")) or None,
                        "matchedCount": int(facts.get("matchedItemCount") or 0),
                        "rows": comparison_rows,
                    }
                )

        existing_checks = [item.model_dump() for item in result.checks]
        deduplicated_checks: list[dict[str, str]] = []
        seen_names: set[str] = set()
        for check in evidence_checks + existing_checks:
            name = self.text(check.get("name"))
            if not name or name in seen_names:
                continue
            seen_names.add(name)
            deduplicated_checks.append(check)

        risk_level = result.risk_level
        decision = result.decision_suggestion
        can_auto_approve = result.can_auto_approve
        if "fail" in evidence_statuses:
            risk_level = "high"
            decision = "manual_review"
            can_auto_approve = False
        elif "warning" in evidence_statuses:
            if risk_level == "low":
                risk_level = "medium"
            if decision == "approve":
                decision = "manual_review"
            can_auto_approve = False

        concerns = list(dict.fromkeys(evidence_concerns + result.concerns))[:20]
        return WeaverReviewResult(
            summary=result.summary,
            riskLevel=risk_level,
            decisionSuggestion=decision,
            suggestedOpinion=result.suggested_opinion,
            checks=deduplicated_checks[:20],
            missingMaterials=result.missing_materials,
            concerns=concerns,
            comparisonTables=comparison_tables,
            confidence=result.confidence,
            canAutoApprove=can_auto_approve,
        )

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
            comparisonTables=[],
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
            generalCheckEnabled=row.general_check_enabled,
            autoReviewMode=row.auto_review_mode,
            enabled=row.enabled,
            priority=row.priority,
            status=row.status,
        )

    def to_node_config_read(self, row: WeaverAiReviewNodeConfig) -> WeaverReviewNodeConfigRead:
        return WeaverReviewNodeConfigRead(
            id=row.id or 0,
            env=row.env,
            workflowId=row.workflow_id,
            workflowName=row.workflow_name,
            nodeId=row.node_id,
            nodeName=row.node_name,
            enabled=row.enabled,
            showEntry=row.show_entry,
            automaticReviewEnabled=row.automatic_review_enabled,
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

    def to_test_record_read(self, row: WeaverAiReviewTestRecord) -> WeaverReviewRecordRead:
        return WeaverReviewRecordRead(
            id=row.id or 0,
            env=row.env,
            workflowId=row.workflow_id,
            workflowName=row.workflow_name,
            requestId=row.request_id,
            nodeId=row.source_node_id,
            nodeName=row.source_node_name,
            triggerType="test",
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

    def to_json_compatible(self, value: Any) -> Any:
        """将 MySQL Decimal、日期等数据库值转换为可持久化的 JSON 值。"""
        return json.loads(json.dumps(value, ensure_ascii=False, default=str))

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
