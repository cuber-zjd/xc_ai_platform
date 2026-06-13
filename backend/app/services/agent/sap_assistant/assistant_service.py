import asyncio
import time
import uuid
from typing import Any, AsyncGenerator

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.agent.sap_assistant import SapAssistantMessage, SapAssistantSession, SapSystemConfig
from app.schemas.agent.sap_assistant import SapAssistantChatRequest, SapAssistantChatResponse, SapStreamChunk
from app.services.agent.sap_assistant.deep_agent_service import sap_deep_agent_service


class SapAssistantService:
    """SAP 助手会话编排层。

    Agent 调查逻辑只保留 deep_agent_service；本层只负责会话、系统解析、流式事件转发和记忆沉淀。
    """

    async def chat(
        self,
        db: AsyncSession,
        request: SapAssistantChatRequest,
        user_id: int | None = None,
    ) -> SapAssistantChatResponse:
        session = await self._ensure_session(db, request, user_id)
        system = await self._resolve_system(db, request.sap_system_id or session.sap_system_id, request.message)
        response = await sap_deep_agent_service.run(db, request, session, system, user_id=user_id)
        await self._persist_exchange(db, session, request.message, response)
        return response

    async def stream_chat_realtime(
        self,
        db: AsyncSession,
        request: SapAssistantChatRequest,
        user_id: int | None = None,
    ) -> AsyncGenerator[str, None]:
        def encode(chunk_type: str, data: dict[str, Any]) -> str:
            chunk = SapStreamChunk(id=uuid.uuid4().hex, type=chunk_type, data=data, timestamp=int(time.time() * 1000))
            return f"data: {chunk.model_dump_json()}\n\n"

        session = await self._ensure_session(db, request, user_id)
        system = await self._resolve_system(db, request.sap_system_id or session.sap_system_id, request.message)
        event_queue: asyncio.Queue[tuple[str, dict[str, Any]]] = asyncio.Queue()
        has_streamed_answer = False

        async def event_sink(event_type: str, data: dict[str, Any]) -> None:
            nonlocal has_streamed_answer
            if event_type == "text_delta":
                has_streamed_answer = True
            await event_queue.put((event_type, data))

        yield encode("session_context", {"sessionId": session.id, "hasHistory": True})
        yield encode("system_context", self._system_context(system) or {})

        task = asyncio.create_task(sap_deep_agent_service.run(db, request, session, system, user_id=user_id, event_sink=event_sink))
        while not task.done() or not event_queue.empty():
            try:
                event_type, data = await asyncio.wait_for(event_queue.get(), timeout=0.15)
            except TimeoutError:
                continue
            yield encode(event_type, data)

        try:
            response = await task
        except Exception as exc:
            is_recursion_error = sap_deep_agent_service._is_recursion_limit_error(exc)
            error_detail = sap_deep_agent_service._friendly_agent_error(exc)
            status = "skipped" if is_recursion_error else "failed"
            title = "停止自动追查" if is_recursion_error else "SAP 工具 Agent 执行失败"
            error_item = self._timeline("sap_agent_error", status, title, error_detail)
            yield encode(
                "thought_node",
                {
                    "nodeId": error_item["id"],
                    "act": "tool_result",
                    "status": error_item["status"],
                    "detailStr": error_item["detail"],
                    "toolName": error_item["toolName"],
                },
            )
            fallback_answer = (
                f"{error_detail}\n\n当前没有拿到完整的自动总结结果，请基于已有时间线和证据继续追问。"
                if is_recursion_error
                else f"SAP 工具 Agent 执行失败：{exc}"
            )
            db.add(SapAssistantMessage(session_id=session.id or 0, role="user", content=request.message))
            db.add(
                SapAssistantMessage(
                    session_id=session.id or 0,
                    role="assistant",
                    content=fallback_answer,
                    message_metadata={"timeline": [error_item], "tool_results": [], "evidence": []},
                )
            )
            await db.commit()
            for piece in self._split_answer(fallback_answer):
                yield encode("text_delta", {"content": piece})
            yield encode("text_done", {"sessionId": session.id})
            return

        await self._persist_exchange(db, session, request.message, response)
        if response.flowchart:
            yield encode("flowchart", {"code": response.flowchart})
        if not has_streamed_answer:
            for piece in self._split_answer(response.answer):
                yield encode("text_delta", {"content": piece})
                await asyncio.sleep(0.01)
        yield encode("text_done", {"sessionId": session.id})

    async def _persist_exchange(
        self,
        db: AsyncSession,
        session: SapAssistantSession,
        user_message: str,
        response: SapAssistantChatResponse,
    ) -> None:
        db.add(SapAssistantMessage(session_id=session.id or 0, role="user", content=user_message))
        db.add(
            SapAssistantMessage(
                session_id=session.id or 0,
                role="assistant",
                content=response.answer,
                message_metadata={
                    "timeline": response.timeline,
                    "tool_results": [item.model_dump() for item in response.tool_results],
                    "evidence": [item.model_dump() for item in response.evidence],
                    "flowchart": response.flowchart,
                },
            )
        )
        session.summary = self._build_session_memory(session.summary, user_message, response)
        await db.commit()

    async def _ensure_session(
        self,
        db: AsyncSession,
        request: SapAssistantChatRequest,
        user_id: int | None,
    ) -> SapAssistantSession:
        if request.session_id:
            session = await db.get(SapAssistantSession, request.session_id)
            if session:
                return session
        session = SapAssistantSession(
            user_id=user_id,
            title=request.message[:40],
            sap_system_id=request.sap_system_id,
            knowledge_base_ids=request.knowledge_base_ids,
        )
        db.add(session)
        await db.commit()
        await db.refresh(session)
        return session

    async def _resolve_system(
        self,
        db: AsyncSession,
        sap_system_id: int | None,
        message: str,
    ) -> SapSystemConfig | None:
        if sap_system_id:
            system = await db.get(SapSystemConfig, sap_system_id)
            if system and system.is_enabled and not system.is_deleted:
                return system

        statement = select(SapSystemConfig).where(SapSystemConfig.is_enabled, SapSystemConfig.is_deleted == 0)
        result = await db.exec(statement)
        systems = list(result.all())
        if not systems:
            return None

        lowered = message.lower()
        for system in systems:
            if system.system_code.lower() in lowered or system.name.lower() in lowered:
                return system
            if "生产" in message and system.is_production:
                return system
            if "测试" in message and system.environment == "qas":
                return system
            if "开发" in message and system.environment == "dev":
                return system
        return systems[0]

    def _build_session_memory(
        self,
        previous_summary: str | None,
        user_message: str,
        response: SapAssistantChatResponse,
    ) -> str:
        lines: list[str] = []
        if previous_summary:
            lines.extend([previous_summary.strip()[-2500:], ""])
        lines.append("【最近一轮】")
        lines.append(f"用户问题：{user_message[:500]}")

        system_context = response.system_context or {}
        if system_context:
            lines.append(
                "SAP 系统："
                f"{system_context.get('name') or '-'} / {system_context.get('client') or '-'} / {system_context.get('environment') or '-'}"
            )

        tool_summaries = []
        for item in response.tool_results[:8]:
            source = self._tool_source_label(item)
            suffix = f"({source})" if source else ""
            tool_summaries.append(f"- {item.tool_name}{suffix}：{(item.summary or '')[:220]}")
        if tool_summaries:
            lines.append("已调查工具与对象：")
            lines.extend(tool_summaries)

        evidence_summaries = []
        for item in response.evidence[:8]:
            source = item.source_object or item.location or ""
            suffix = f"[{source}]" if source else ""
            evidence_summaries.append(f"- {item.title}{suffix}：{(item.summary or '')[:220]}")
        if evidence_summaries:
            lines.append("关键证据：")
            lines.extend(evidence_summaries)

        lines.append(f"上轮回答摘要：{self._compact_answer_for_memory(response.answer)}")
        return "\n".join(lines)[-4000:]

    def _tool_source_label(self, item: Any) -> str:
        data = getattr(item, "data", None)
        if not isinstance(data, dict):
            return ""
        parsed = data.get("JSON_PARSED")
        payload = parsed if isinstance(parsed, dict) else data
        for key in ("object", "resolvedProgram", "table", "tableName"):
            value = payload.get(key)
            if value:
                return str(value)
        items = payload.get("items")
        if not isinstance(items, list):
            return ""
        programs: list[str] = []
        for row in items:
            if not isinstance(row, dict):
                continue
            program = row.get("program") or row.get("pgmna")
            if program and str(program) not in programs:
                programs.append(str(program))
        return ",".join(programs[:3])

    def _compact_answer_for_memory(self, answer: str) -> str:
        return " ".join(answer.split())[:1200]

    def _system_context(self, system: SapSystemConfig | None) -> dict[str, Any] | None:
        if not system:
            return None
        return {
            "id": system.id,
            "name": system.name,
            "systemCode": system.system_code,
            "client": system.client,
            "environment": system.environment,
            "companyCode": system.company_code,
            "isProduction": system.is_production,
        }

    def _timeline(self, node_id: str, status: str, title: str, detail: str) -> dict[str, Any]:
        return {"id": node_id, "status": status, "title": title, "detail": detail, "toolName": node_id}

    def _split_answer(self, answer: str, size: int = 24) -> list[str]:
        return [answer[index : index + size] for index in range(0, len(answer), size)] or [answer]


sap_assistant_service = SapAssistantService()
