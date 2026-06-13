import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.core.llm_factory import LLMFactory
from app.core.logger import logger
from app.schemas.agent.weaver_ai_assistant import (
    WeaverAssistantAction,
    WeaverAssistantChatRequest,
    WeaverAssistantChatResponse,
    WeaverFieldConfigItem,
    WeaverFieldConfigResponse,
)


class WeaverAiAssistantService:
    """泛微流程填单助手。

    AI 只允许返回结构化填单动作，前端和 ecode 再按白名单解释执行。
    """

    async def get_field_config(self, workflow_id: str) -> WeaverFieldConfigResponse:
        return WeaverFieldConfigResponse(
            workflowId=workflow_id,
            fields=[
                WeaverFieldConfigItem(
                    bizKey="title",
                    label="标题",
                    fieldId="",
                    type="text",
                    writable=True,
                ),
                WeaverFieldConfigItem(
                    bizKey="reason",
                    label="申请原因",
                    fieldId="",
                    type="textarea",
                    writable=True,
                ),
            ],
        )

    async def chat(self, request: WeaverAssistantChatRequest) -> WeaverAssistantChatResponse:
        if not request.message.strip():
            return WeaverAssistantChatResponse(message="请输入需要我协助填写的内容。", actions=[])

        writable_fields = {
            key: field
            for key, field in request.context.fields.items()
            if field.writable and field.field_id
        }
        if not writable_fields:
            return WeaverAssistantChatResponse(
                message="当前没有可写字段配置。我可以先给出文字建议，但不能直接写入表单。",
                actions=[
                    WeaverAssistantAction(
                        type="show_message",
                        message="请先在 ecode 或平台配置当前流程的字段 ID，再启用自动写入。",
                    )
                ],
            )

        try:
            result = await self._invoke_llm(request, writable_fields)
            return self._normalize_response(result, writable_fields)
        except Exception as exc:
            logger.warning(f"泛微流程 AI 助手模型调用失败: {LLMFactory.describe_invocation_error(exc)}")
            return self._fallback_response(request, writable_fields)

    async def _invoke_llm(
        self,
        request: WeaverAssistantChatRequest,
        writable_fields: dict[str, Any],
    ) -> dict[str, Any]:
        field_summary = [
            {
                "bizKey": key,
                "label": field.label,
                "fieldId": field.field_id,
                "type": field.type,
                "currentValue": field.value,
            }
            for key, field in writable_fields.items()
        ]
        prompt_payload = {
            "userMessage": request.message,
            "baseInfo": request.context.base_info,
            "fields": field_summary,
        }
        messages = [
            SystemMessage(
                content=(
                    "你是泛微 E-cology 流程填单助手。你只能输出 JSON，不要输出 Markdown。"
                    "返回格式必须是 {\"message\":\"...\",\"actions\":[...]}。"
                    "actions 只允许 set_field、add_detail_row、show_message。"
                    "set_field 必须使用输入字段列表中的 fieldId，不得编造字段。"
                    "不要生成 JavaScript，不要提交、保存、审批或删除流程。"
                    "如果信息不足，只返回 show_message 或少量安全的 set_field 建议。"
                )
            ),
            HumanMessage(content=json.dumps(prompt_payload, ensure_ascii=False)),
        ]
        response = await LLMFactory.safe_invoke(
            messages,
            capability="general",
            temperature=0,
            json_mode=True,
            enable_reasoning=False,
        )
        content = getattr(response, "content", response)
        return self._parse_json_content(str(content))

    def _parse_json_content(self, content: str) -> dict[str, Any]:
        text = content.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?", "", text, flags=re.IGNORECASE).strip()
            text = re.sub(r"```$", "", text).strip()
        return json.loads(text)

    def _normalize_response(
        self,
        payload: dict[str, Any],
        writable_fields: dict[str, Any],
    ) -> WeaverAssistantChatResponse:
        allowed_field_ids = {field.field_id for field in writable_fields.values()}
        actions: list[WeaverAssistantAction] = []
        for raw_action in payload.get("actions") or []:
            action_type = raw_action.get("type")
            if action_type == "set_field":
                field_id = raw_action.get("field")
                if field_id not in allowed_field_ids:
                    continue
                actions.append(
                    WeaverAssistantAction(
                        type="set_field",
                        field=field_id,
                        value=raw_action.get("value", ""),
                        label=raw_action.get("label"),
                    )
                )
            elif action_type == "add_detail_row":
                actions.append(
                    WeaverAssistantAction(
                        type="add_detail_row",
                        detail=raw_action.get("detail"),
                        values=raw_action.get("values") or {},
                    )
                )
            elif action_type == "show_message":
                actions.append(
                    WeaverAssistantAction(
                        type="show_message",
                        message=raw_action.get("message") or "",
                    )
                )

        message = str(payload.get("message") or "已生成填单建议，请确认后写入。")
        return WeaverAssistantChatResponse(message=message, actions=actions)

    def _fallback_response(
        self,
        request: WeaverAssistantChatRequest,
        writable_fields: dict[str, Any],
    ) -> WeaverAssistantChatResponse:
        reason_field = self._find_field(writable_fields, ("原因", "事由", "说明", "备注"))
        title_field = self._find_field(writable_fields, ("标题", "主题", "名称"))
        actions: list[WeaverAssistantAction] = []
        if title_field:
            actions.append(
                WeaverAssistantAction(
                    type="set_field",
                    field=title_field.field_id,
                    value=self._compact_text(request.message, 60),
                    label=title_field.label,
                )
            )
        if reason_field and reason_field.field_id != getattr(title_field, "field_id", None):
            actions.append(
                WeaverAssistantAction(
                    type="set_field",
                    field=reason_field.field_id,
                    value=request.message.strip(),
                    label=reason_field.label,
                )
            )
        return WeaverAssistantChatResponse(
            message="模型暂时不可用，已根据字段名称生成一版基础填单建议。",
            actions=actions,
        )

    def _find_field(self, fields: dict[str, Any], keywords: tuple[str, ...]) -> Any | None:
        for field in fields.values():
            text = f"{field.label} {field.field_id}".lower()
            if any(keyword.lower() in text for keyword in keywords):
                return field
        return None

    def _compact_text(self, text: str, max_length: int) -> str:
        normalized = " ".join(text.strip().split())
        if len(normalized) <= max_length:
            return normalized
        return f"{normalized[:max_length - 1]}…"


weaver_ai_assistant_service = WeaverAiAssistantService()
