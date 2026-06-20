from datetime import datetime
from typing import Any

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.session import async_session
from app.models.agent.weaver_ai_assistant import WeaverAiWorkflowRule
from app.schemas.agent.weaver_ai_assistant import (
    WeaverWorkflowRuleCreate,
    WeaverWorkflowRuleRead,
    WeaverWorkflowRuleUpdate,
)


class WeaverWorkflowRuleService:
    """泛微流程 AI 特殊填报规则维护。"""

    async def list_rules(self, db: AsyncSession, env: str, workflow_id: str) -> list[WeaverWorkflowRuleRead]:
        statement = (
            select(WeaverAiWorkflowRule)
            .where(
                WeaverAiWorkflowRule.env == self.normalize_env(env),
                WeaverAiWorkflowRule.workflow_id == str(workflow_id),
                WeaverAiWorkflowRule.is_deleted == 0,
            )
            .order_by(WeaverAiWorkflowRule.priority.asc(), WeaverAiWorkflowRule.id.asc())
        )
        rows = list((await db.exec(statement)).all())
        return [self.to_read(row) for row in rows]

    async def create_rule(self, db: AsyncSession, payload: WeaverWorkflowRuleCreate) -> WeaverWorkflowRuleRead:
        row = WeaverAiWorkflowRule(
            env=self.normalize_env(payload.env),
            workflow_id=str(payload.workflow_id),
            workflow_name=payload.workflow_name,
            rule_title=payload.rule_title.strip(),
            rule_content=payload.rule_content.strip(),
            skill_config=self.clean_skill_config(payload.skill_config),
            enabled=payload.enabled,
            priority=payload.priority,
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return self.to_read(row)

    async def update_rule(self, db: AsyncSession, rule_id: int, payload: WeaverWorkflowRuleUpdate) -> WeaverWorkflowRuleRead | None:
        row = await db.get(WeaverAiWorkflowRule, rule_id)
        if not row or row.is_deleted:
            return None
        update_data = payload.model_dump(exclude_unset=True, by_alias=False)
        if "workflow_name" in update_data:
            row.workflow_name = payload.workflow_name
        if payload.rule_title is not None:
            row.rule_title = payload.rule_title.strip()
        if payload.rule_content is not None:
            row.rule_content = payload.rule_content.strip()
        if "skill_config" in update_data:
            row.skill_config = self.clean_skill_config(payload.skill_config)
        if payload.enabled is not None:
            row.enabled = payload.enabled
        if payload.priority is not None:
            row.priority = payload.priority
        row.update_time = datetime.now()
        await db.commit()
        await db.refresh(row)
        return self.to_read(row)

    async def delete_rule(self, db: AsyncSession, rule_id: int) -> bool:
        row = await db.get(WeaverAiWorkflowRule, rule_id)
        if not row or row.is_deleted:
            return False
        row.is_deleted = 1
        row.update_time = datetime.now()
        await db.commit()
        return True

    async def load_enabled_rules_for_prompt(self, env: str | None, workflow_id: str | None) -> list[dict[str, Any]]:
        if not workflow_id:
            return []
        async with async_session() as db:
            statement = (
                select(WeaverAiWorkflowRule)
                .where(
                    WeaverAiWorkflowRule.env == self.normalize_env(env),
                    WeaverAiWorkflowRule.workflow_id == str(workflow_id),
                    WeaverAiWorkflowRule.enabled == True,  # noqa: E712
                    WeaverAiWorkflowRule.status == "active",
                    WeaverAiWorkflowRule.is_deleted == 0,
                )
                .order_by(WeaverAiWorkflowRule.priority.asc(), WeaverAiWorkflowRule.id.asc())
                .limit(20)
            )
            rows = list((await db.exec(statement)).all())
        return [
            {
                "title": row.rule_title,
                "content": row.rule_content,
                "priority": row.priority,
                "skillConfig": row.skill_config or {},
            }
            for row in rows
        ]

    def to_read(self, row: WeaverAiWorkflowRule) -> WeaverWorkflowRuleRead:
        return WeaverWorkflowRuleRead(
            id=row.id or 0,
            env=row.env,
            workflowId=row.workflow_id,
            workflowName=row.workflow_name,
            ruleTitle=row.rule_title,
            ruleContent=row.rule_content,
            skillConfig=row.skill_config or {},
            enabled=row.enabled,
            priority=row.priority,
            status=row.status,
        )

    def normalize_env(self, env: str | None) -> str:
        value = (env or "default").strip()
        return value or "default"

    def clean_skill_config(self, value: dict[str, Any] | None) -> dict[str, Any]:
        if not isinstance(value, dict):
            return {}
        return {str(key): item for key, item in value.items() if item not in (None, "")}


weaver_workflow_rule_service = WeaverWorkflowRuleService()
