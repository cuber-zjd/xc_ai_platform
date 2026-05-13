import asyncio
import json
import re
import time
import uuid
from typing import Any, AsyncGenerator

from langchain_core.messages import HumanMessage, SystemMessage
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.llm_factory import LLMFactory
from app.core.langfuse_observability import langfuse_observability
from app.core.logger import logger
from app.models.agent.sap_assistant import SapAssistantMessage, SapAssistantSession, SapEvidenceRecord, SapSystemConfig
from app.schemas.agent.sap_assistant import (
    SapAssistantChatRequest,
    SapAssistantChatResponse,
    SapStreamChunk,
    SapToolEvidence,
)
from app.services.agent.sap_assistant.deep_agent_service import sap_deep_agent_service
from app.services.knowledge_base_service import knowledge_base_service
from app.services.agent.sap_assistant.tool_service import sap_tool_service


class SapAssistantService:
    MAX_REACT_STEPS = 20

    async def chat(
        self,
        db: AsyncSession,
        request: SapAssistantChatRequest,
        user_id: int | None = None,
    ) -> SapAssistantChatResponse:
        session = await self._ensure_session(db, request, user_id)
        system = await self._resolve_system(db, request.sap_system_id or session.sap_system_id, request.message)
        response = await sap_deep_agent_service.run(db, request, session, system, user_id=user_id)

        db.add(SapAssistantMessage(session_id=session.id or 0, role="user", content=request.message))
        db.add(
            SapAssistantMessage(
                session_id=session.id or 0,
                role="assistant",
                content=response.answer,
                message_metadata={"timeline": response.timeline, "flowchart": response.flowchart},
            )
        )
        session.summary = self._build_session_memory(session.summary, request.message, response)
        await db.commit()
        return response

        plan = self._plan_tools(request.message)

        with langfuse_observability.current_observation(
            name="sap_assistant_react",
            as_type="agent",
            input={
                "message": request.message,
                "session_id": session.id,
                "sap_system_id": request.sap_system_id or session.sap_system_id,
                "knowledge_base_ids": request.knowledge_base_ids,
            },
            metadata={"user_id": user_id, "initial_plan": plan},
        ) as agent_obs:
            agent_obs.update_trace(
                name="SAP 助手",
                user_id=str(user_id) if user_id else None,
                session_id=str(session.id or ""),
                input=request.message,
                metadata={"sap_system": self._system_context(system), "initial_plan": plan},
                tags=["sap-assistant", "react", system.environment if system else "no-system"],
            )
            timeline, tool_results, evidence, executed_plan = await self._run_tool_loop(db, system, session.id, request.message, plan)

            with langfuse_observability.current_observation(
                name="knowledge_base_search",
                as_type="retriever",
                input={"knowledge_base_ids": request.knowledge_base_ids, "query": request.message},
            ) as kb_obs:
                kb_evidence = await self._search_knowledge(db, request.knowledge_base_ids, request.message)
                kb_obs.update(output=[item.model_dump() for item in kb_evidence], metadata={"hit_count": len(kb_evidence)})
            evidence.extend(kb_evidence)
            if kb_evidence:
                timeline.append(self._timeline("knowledge", "success", "检索知识库", f"命中 {len(kb_evidence)} 条知识片段"))

            answer = await self._compose_answer(request.message, system, tool_results, evidence)
            flowchart = self._build_flowchart(executed_plan, evidence)
            agent_obs.update(
                output={"answer": answer, "tool_count": len(tool_results), "evidence_count": len(evidence), "flowchart": flowchart},
                metadata={"executed_plan": executed_plan, "timeline": timeline},
            )
            agent_obs.update_trace(output=answer, metadata={"executed_plan": executed_plan, "tool_results": [item.model_dump() for item in tool_results]})
        langfuse_observability.flush()

        db.add(SapAssistantMessage(session_id=session.id or 0, role="user", content=request.message))
        db.add(
            SapAssistantMessage(
                session_id=session.id or 0,
                role="assistant",
                content=answer,
                message_metadata={"timeline": timeline, "flowchart": flowchart},
            )
        )
        await db.commit()

        return SapAssistantChatResponse(
            session_id=session.id or 0,
            answer=answer,
            system_context=self._system_context(system),
            timeline=timeline,
            tool_results=tool_results,
            evidence=evidence,
            flowchart=flowchart,
        )

    async def _run_tool_loop(
        self,
        db: AsyncSession,
        system: SapSystemConfig | None,
        session_id: int | None,
        message: str,
        initial_plan: list[tuple[str, dict[str, Any]]],
    ) -> tuple[list[dict[str, Any]], list[Any], list[SapToolEvidence], list[tuple[str, dict[str, Any]]]]:
        timeline: list[dict[str, Any]] = []
        tool_results: list[Any] = []
        evidence: list[SapToolEvidence] = []
        executed_plan: list[tuple[str, dict[str, Any]]] = []
        queue = list(initial_plan)
        seen: set[str] = set()
        object_names = self._extract_object_names(message)

        timeline.append(self._timeline("intent", "success", "识别问题意图", f"初始计划调用 {len(queue)} 个工具"))
        if system:
            timeline.append(
                self._timeline(
                    "system",
                    "success",
                    "确认 SAP 系统",
                    f"{system.name} / {system.client} / {system.environment}",
                )
            )
        else:
            timeline.append(self._timeline("system", "failed", "确认 SAP 系统", "未匹配到系统，已跳过 SAP RFC 调用"))

        conversation_context = await self._load_session_context(db, session_id)
        ai_initial = await self._ai_decide_next_calls(message, system, tool_results, evidence, seen, self.MAX_REACT_STEPS, conversation_context=conversation_context)
        if ai_initial["calls"]:
            queue = ai_initial["calls"]
            timeline.append(self._timeline("ai_plan", "success", "AI 制定工具计划", ai_initial["reason"] or f"计划调用 {len(queue)} 个工具"))
        elif ai_initial["done"]:
            queue = []
            timeline.append(self._timeline("ai_plan", "success", "AI 判断无需调用工具", ai_initial["reason"] or "直接进入回答阶段"))
        elif ai_initial["reason"]:
            timeline.append(self._timeline("ai_plan", "skipped", "AI 工具规划不可用", ai_initial["reason"]))

        for step in range(self.MAX_REACT_STEPS):
            if not queue:
                break
            tool_name, params = queue.pop(0)
            call_key = json.dumps([tool_name, params], ensure_ascii=False, sort_keys=True)
            if call_key in seen:
                continue
            seen.add(call_key)
            executed_plan.append((tool_name, params))
            node_id = f"{tool_name}_{step + 1}"
            compact_params = self._compact_value(params, max_text=240)
            timeline.append(self._timeline(node_id, "pending", f"调用工具 {tool_name}", f"参数：{compact_params}"))
            with langfuse_observability.current_observation(
                name=f"sap_tool:{tool_name}",
                as_type="tool",
                input={"tool_name": tool_name, "params": params, "step": step + 1},
                metadata={"system": self._system_context(system)},
            ) as tool_obs:
                result = await sap_tool_service.execute(db, system, tool_name, params, session_id=session_id)
                tool_obs.update(
                    output=result.model_dump(),
                    level="ERROR" if result.status == "failed" else "DEFAULT",
                    status_message=result.error_message,
                    metadata={"duration_ms": result.duration_ms, "status": result.status},
                )
            tool_results.append(result)
            evidence.extend(result.evidence)
            timeline.append(self._timeline(node_id, result.status, f"工具 {tool_name} 完成", result.summary))
            with langfuse_observability.current_observation(
                name=f"react_observe:{tool_name}",
                as_type="span",
                input={"tool_name": tool_name, "result": self._compact_value(result.model_dump(), max_text=1200)},
            ) as react_obs:
                ai_decision = await self._ai_decide_next_calls(
                    message,
                    system,
                    tool_results,
                    evidence,
                    seen,
                    self.MAX_REACT_STEPS - step - 1,
                    queue,
                )
                if self._has_sufficient_answer_evidence(message, tool_results):
                    ai_decision["done"] = True
                    ai_decision["reason"] = "已找到目标字段的可执行赋值或计算证据，停止继续搜索并整理答案"
                    next_calls = []
                else:
                    next_calls = self._filter_viable_calls(ai_decision["calls"], seen, tool_results)
                answer_ready = self._is_answer_ready(message, tool_results)
                if not next_calls and (not ai_decision["decided"] or (ai_decision["done"] and not answer_ready)):
                    next_calls = self._filter_viable_calls(self._react_next_calls(message, object_names, tool_name, params, result), seen, tool_results)
                if not next_calls and ai_decision["done"] and not answer_ready:
                    next_calls = self._gap_next_calls(message, tool_results, seen)
                if ai_decision["done"] and not answer_ready and next_calls:
                    ai_decision["done"] = False
                    ai_decision["reason"] = "当前只有注释、字段定义或弱证据，继续追查可执行源码逻辑"
                react_obs.update(
                    output={"next_calls": next_calls, "ai_decision": ai_decision},
                    metadata={"queued_count": len(queue), "seen_count": len(seen)},
                )
            if ai_decision["done"]:
                timeline.append(self._timeline(f"react_done_{step + 1}", "success", "AI 判断证据足够", ai_decision["reason"] or "准备生成最终回答"))
                break
            for next_call in reversed(next_calls):
                next_key = json.dumps(next_call, ensure_ascii=False, sort_keys=True)
                if next_key not in seen:
                    queue.insert(0, next_call)
            if next_calls:
                timeline.append(self._timeline(f"react_{step + 1}", "success", "观察工具结果", f"根据返回内容追加 {len(next_calls)} 个后续工具调用"))

        if queue:
            evidence.append(
                SapToolEvidence(
                    evidence_type="agent_limit",
                    title="达到自动追查上限",
                    summary=f"本轮最多自动调用 {self.MAX_REACT_STEPS} 次工具，仍有 {len(queue)} 个候选调用未执行；用户继续追问时可接着当前证据链运行。",
                    confidence=1.0,
                    content={"remaining_calls": queue[:5], "max_steps": self.MAX_REACT_STEPS},
                )
            )
            timeline.append(self._timeline("react_limit", "skipped", "停止自动追查", "已达到单轮最大工具调用次数，保留剩余计划待下一轮继续"))
        return timeline, tool_results, evidence, executed_plan


    async def stream_chat(
        self,
        db: AsyncSession,
        request: SapAssistantChatRequest,
        user_id: int | None = None,
    ) -> AsyncGenerator[str, None]:
        def encode(chunk_type: str, data: dict[str, Any]) -> str:
            chunk = SapStreamChunk(
                id=uuid.uuid4().hex,
                type=chunk_type,
                data=data,
                timestamp=int(time.time() * 1000),
            )
            return f"data: {chunk.model_dump_json()}\n\n"

        yield encode("thought_node", {"nodeId": "intent", "act": "planning", "status": "pending", "detailStr": "正在识别 SAP 问题类型"})
        response = await self.chat(db, request, user_id=user_id)
        yield encode("system_context", response.system_context or {})
        for item in response.timeline:
            yield encode(
                "thought_node",
                {
                    "nodeId": item["id"],
                    "act": "calling_tool" if item["status"] == "pending" else "tool_result",
                    "status": item["status"],
                    "detailStr": item["detail"],
                    "toolName": item.get("toolName"),
                },
            )
            await asyncio.sleep(0.02)
        for tool_result in response.tool_results:
            yield encode("tool_output", {"toolName": tool_result.tool_name, "displayType": "json", "content": tool_result.model_dump()})
        for item in response.evidence:
            yield encode("evidence", item.model_dump())
        if response.flowchart:
            yield encode("flowchart", {"code": response.flowchart})
        for piece in self._split_answer(response.answer):
            yield encode("text_delta", {"content": piece})
            await asyncio.sleep(0.01)
        yield encode("text_done", {"sessionId": response.session_id})

    async def stream_chat_realtime(
        self,
        db: AsyncSession,
        request: SapAssistantChatRequest,
        user_id: int | None = None,
    ) -> AsyncGenerator[str, None]:
        def encode(chunk_type: str, data: dict[str, Any]) -> str:
            chunk = SapStreamChunk(id=uuid.uuid4().hex, type=chunk_type, data=data, timestamp=int(time.time() * 1000))
            return f"data: {chunk.model_dump_json()}\n\n"

        def timeline_event(item: dict[str, Any]) -> str:
            return encode(
                "thought_node",
                {
                    "nodeId": item["id"],
                    "act": "calling_tool" if item["status"] == "pending" else "tool_result",
                    "status": item["status"],
                    "detailStr": item["detail"],
                    "toolName": item.get("toolName"),
                },
            )

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
            error_detail = sap_deep_agent_service._friendly_agent_error(exc) if is_recursion_error else str(exc)
            error_item = self._timeline(
                "deepagents_error",
                "skipped" if is_recursion_error else "failed",
                "停止自动追查" if is_recursion_error else "deepagents 执行失败",
                error_detail,
            )
            yield timeline_event(error_item)
            fallback_answer = (
                f"{error_detail}\n\n当前没有拿到完整的自动总结结果，请基于已有时间线和证据继续追问。"
                if is_recursion_error
                else f"deepagents 执行失败：{exc}"
            )
            db.add(SapAssistantMessage(session_id=session.id or 0, role="user", content=request.message))
            db.add(SapAssistantMessage(session_id=session.id or 0, role="assistant", content=fallback_answer, message_metadata={"timeline": [error_item]}))
            await db.commit()
            for piece in self._split_answer(fallback_answer):
                yield encode("text_delta", {"content": piece})
            yield encode("text_done", {"sessionId": session.id})
            return

        db.add(SapAssistantMessage(session_id=session.id or 0, role="user", content=request.message))
        db.add(SapAssistantMessage(session_id=session.id or 0, role="assistant", content=response.answer, message_metadata={"timeline": response.timeline, "flowchart": response.flowchart}))
        session.summary = self._build_session_memory(session.summary, request.message, response)
        await db.commit()

        if response.flowchart:
            yield encode("flowchart", {"code": response.flowchart})
        if not has_streamed_answer:
            for piece in self._split_answer(response.answer):
                yield encode("text_delta", {"content": piece})
                await asyncio.sleep(0.01)
        yield encode("text_done", {"sessionId": session.id})
        return

        timeline: list[dict[str, Any]] = []
        tool_results: list[Any] = []
        evidence: list[SapToolEvidence] = []
        executed_plan: list[tuple[str, dict[str, Any]]] = []
        session = await self._ensure_session(db, request, user_id)
        system = await self._resolve_system(db, request.sap_system_id or session.sap_system_id, request.message)
        conversation_context = await self._load_session_context(db, session.id)
        queue = self._plan_tools(request.message)
        seen: set[str] = set()
        object_names = self._extract_object_names(request.message)

        def add_timeline(node_id: str, status: str, title: str, detail: str) -> str:
            item = self._timeline(node_id, status, title, detail)
            timeline.append(item)
            return timeline_event(item)

        yield add_timeline("intent", "success", "识别问题意图", "准备由 AI 自主规划工具调用")
        yield encode("session_context", {"sessionId": session.id, "hasHistory": bool(conversation_context.get("messages"))})
        if system:
            yield encode("system_context", self._system_context(system) or {})
            yield add_timeline("system", "success", "确认 SAP 系统", f"{system.name} / {system.client} / {system.environment}")
        else:
            yield add_timeline("system", "failed", "确认 SAP 系统", "未匹配到系统，已跳过 SAP RFC 调用")

        with langfuse_observability.current_observation(
            name="sap_assistant_react_stream",
            as_type="agent",
            input={"message": request.message, "session_id": session.id},
            metadata={"user_id": user_id},
        ) as agent_obs:
            ai_initial = await self._ai_decide_next_calls(
                request.message,
                system,
                tool_results,
                evidence,
                seen,
                self.MAX_REACT_STEPS,
                conversation_context=conversation_context,
            )
            if ai_initial["calls"]:
                queue = ai_initial["calls"]
                yield add_timeline("ai_plan", "success", "AI 制定工具计划", ai_initial["reason"] or f"计划调用 {len(queue)} 个工具")
            elif ai_initial["done"]:
                queue = []
                yield add_timeline("ai_plan", "success", "AI 判断无需调用工具", ai_initial["reason"] or "直接进入回答阶段")
            elif ai_initial["reason"]:
                yield add_timeline("ai_plan", "skipped", "AI 工具规划不可用", ai_initial["reason"])

            for step in range(self.MAX_REACT_STEPS):
                if not queue:
                    break
                tool_name, params = queue.pop(0)
                call_key = json.dumps([tool_name, params], ensure_ascii=False, sort_keys=True)
                if call_key in seen:
                    continue
                seen.add(call_key)
                executed_plan.append((tool_name, params))
                node_id = f"{tool_name}_{step + 1}"
                yield add_timeline(node_id, "pending", f"调用工具 {tool_name}", f"参数：{self._compact_value(params, max_text=240)}")
                with langfuse_observability.current_observation(
                    name=f"sap_tool:{tool_name}",
                    as_type="tool",
                    input={"tool_name": tool_name, "params": params, "step": step + 1},
                    metadata={"system": self._system_context(system)},
                ) as tool_obs:
                    result = await sap_tool_service.execute(db, system, tool_name, params, session_id=session.id)
                    tool_obs.update(
                        output=result.model_dump(),
                        level="ERROR" if result.status == "failed" else "DEFAULT",
                        status_message=result.error_message,
                        metadata={"duration_ms": result.duration_ms, "status": result.status},
                    )
                tool_results.append(result)
                evidence.extend(result.evidence)
                yield add_timeline(node_id, result.status, f"工具 {tool_name} 完成", result.summary)
                yield encode("tool_output", {"toolName": result.tool_name, "displayType": "json", "content": result.model_dump()})
                for evidence_item in result.evidence:
                    yield encode("evidence", evidence_item.model_dump())

                ai_decision = await self._ai_decide_next_calls(
                    request.message,
                    system,
                    tool_results,
                    evidence,
                    seen,
                    self.MAX_REACT_STEPS - step - 1,
                    queue,
                    conversation_context,
                )
                if self._has_sufficient_answer_evidence(request.message, tool_results):
                    ai_decision["done"] = True
                    ai_decision["reason"] = "已找到目标字段的可执行赋值或计算证据，停止继续搜索并整理答案"
                    next_calls = []
                else:
                    next_calls = self._filter_viable_calls(ai_decision["calls"], seen, tool_results)
                answer_ready = self._is_answer_ready(request.message, tool_results)
                if not next_calls and (not ai_decision["decided"] or (ai_decision["done"] and not answer_ready)):
                    next_calls = self._filter_viable_calls(self._react_next_calls(request.message, object_names, tool_name, params, result), seen, tool_results)
                if not next_calls and ai_decision["done"] and not answer_ready:
                    next_calls = self._gap_next_calls(request.message, tool_results, seen)
                if ai_decision["done"] and not answer_ready and next_calls:
                    ai_decision["done"] = False
                    ai_decision["reason"] = "当前只有注释、字段定义或弱证据，继续追查可执行源码逻辑"
                if ai_decision["done"]:
                    yield add_timeline(f"react_done_{step + 1}", "success", "AI 判断证据足够", ai_decision["reason"] or "准备生成最终回答")
                    break
                for next_call in reversed(next_calls):
                    next_key = json.dumps(next_call, ensure_ascii=False, sort_keys=True)
                    if next_key not in seen:
                        queue.insert(0, next_call)
                if next_calls:
                    yield add_timeline(f"react_{step + 1}", "success", "AI 观察工具结果", ai_decision["reason"] or f"追加 {len(next_calls)} 个后续工具调用")

            if queue:
                limit_evidence = SapToolEvidence(
                    evidence_type="agent_limit",
                    title="达到自动追查上限",
                    summary=f"本轮最多自动调用 {self.MAX_REACT_STEPS} 次工具，仍有 {len(queue)} 个候选调用未执行；用户继续追问时可接着当前证据链运行。",
                    confidence=1.0,
                    content={"remaining_calls": queue[:5], "max_steps": self.MAX_REACT_STEPS},
                )
                evidence.append(limit_evidence)
                yield encode("evidence", limit_evidence.model_dump())
                yield add_timeline("react_limit", "skipped", "达到自动追查上限", limit_evidence.summary or "达到自动追查上限")

            kb_evidence = await self._search_knowledge(db, request.knowledge_base_ids, request.message)
            evidence.extend(kb_evidence)
            if kb_evidence:
                yield add_timeline("knowledge", "success", "检索知识库", f"命中 {len(kb_evidence)} 条知识片段")
                for item in kb_evidence:
                    yield encode("evidence", item.model_dump())

            yield add_timeline("answer", "pending", "生成最终回答", "正在整理证据链并生成回答")
            answer = await self._compose_answer(request.message, system, tool_results, evidence, conversation_context)
            flowchart = self._build_flowchart(executed_plan, evidence)
            if flowchart:
                yield encode("flowchart", {"code": flowchart})
            yield add_timeline("answer", "success", "最终回答完成", "证据链回答已生成")
            agent_obs.update(output={"answer": answer, "tool_count": len(tool_results), "evidence_count": len(evidence)}, metadata={"executed_plan": executed_plan, "timeline": timeline})

        db.add(SapAssistantMessage(session_id=session.id or 0, role="user", content=request.message))
        db.add(SapAssistantMessage(session_id=session.id or 0, role="assistant", content=answer, message_metadata={"timeline": timeline, "flowchart": flowchart}))
        await db.commit()
        langfuse_observability.flush()

        for piece in self._split_answer(answer):
            yield encode("text_delta", {"content": piece})
            await asyncio.sleep(0.01)
        yield encode("text_done", {"sessionId": session.id})

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

    def _build_session_memory(
        self,
        previous_summary: str | None,
        user_message: str,
        response: SapAssistantChatResponse,
    ) -> str:
        lines: list[str] = []
        if previous_summary:
            lines.append(previous_summary.strip()[-2500:])
            lines.append("")
        lines.append("【最近一轮】")
        lines.append(f"用户问题：{user_message[:500]}")
        system_context = response.system_context or {}
        if system_context:
            lines.append(
                "SAP 系统："
                f"{system_context.get('name') or '-'} / {system_context.get('client') or '-'} / {system_context.get('environment') or '-'}"
            )
        tool_summaries: list[str] = []
        for item in response.tool_results[:8]:
            source = self._tool_source_label(item)
            summary = item.summary or ""
            tool_summaries.append(f"- {item.tool_name}{f'({source})' if source else ''}：{summary[:220]}")
        if tool_summaries:
            lines.append("已调查工具与对象：")
            lines.extend(tool_summaries)
        evidence_summaries: list[str] = []
        for item in response.evidence[:8]:
            source = item.source_object or item.location or ""
            evidence_summaries.append(f"- {item.title}{f'[{source}]' if source else ''}：{(item.summary or '')[:220]}")
        if evidence_summaries:
            lines.append("关键证据：")
            lines.extend(evidence_summaries)
        lines.append(f"上轮结论摘要：{self._compact_answer_for_memory(response.answer)}")
        return "\n".join(line for line in lines if line is not None)[-4000:]

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
        if isinstance(items, list):
            programs: list[str] = []
            for row in items:
                if not isinstance(row, dict):
                    continue
                program = row.get("program") or row.get("pgmna")
                if program and str(program) not in programs:
                    programs.append(str(program))
            if programs:
                return ",".join(programs[:3])
        return ""

    def _compact_answer_for_memory(self, answer: str) -> str:
        cleaned = " ".join(answer.split())
        return cleaned[:1200]

    async def _load_session_context(self, db: AsyncSession, session_id: int | None) -> dict[str, Any]:
        if not session_id:
            return {}
        messages_result = await db.exec(
            select(SapAssistantMessage)
            .where(SapAssistantMessage.session_id == session_id)
            .order_by(SapAssistantMessage.create_time.desc())
            .limit(8)
        )
        messages = list(reversed(list(messages_result.all())))
        evidence_result = await db.exec(
            select(SapEvidenceRecord)
            .where(SapEvidenceRecord.session_id == session_id)
            .order_by(SapEvidenceRecord.create_time.desc())
            .limit(12)
        )
        evidence_items = list(evidence_result.all())
        return {
            "messages": [
                {
                    "role": item.role,
                    "content": item.content[:1200],
                    "metadata": item.message_metadata,
                }
                for item in messages
            ],
            "recent_evidence": [
                {
                    "type": item.evidence_type,
                    "title": item.title,
                    "summary": item.summary,
                    "source_object": item.source_object,
                    "location": item.location,
                }
                for item in evidence_items
            ],
        }

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

    def _plan_tools(self, message: str) -> list[tuple[str, dict[str, Any]]]:
        upper = message.upper()
        plan: list[tuple[str, dict[str, Any]]] = []
        object_names = self._extract_object_names(message)
        function_names = [name for name in object_names if name.startswith(("ZFM_", "YFM_"))]
        source_intent = any(keyword in message for keyword in ("源码", "代码", "逻辑", "实现", "函数")) or "RFC" in upper or "FUNCTION" in upper
        tcode_intent = "事务" in message or "TCODE" in upper
        data_intent = any(keyword in message for keyword in ("数据", "样例", "取数", "读表"))

        if function_names or source_intent:
            func = function_names[0] if function_names else (object_names[0] if object_names else "")
            plan.append(("function_source", {"object_name": func, "start_line": 1, "max_lines": 0}))

        if tcode_intent or (object_names and not function_names and not source_intent):
            tcode = object_names[0] if object_names else ""
            plan.append(("tcode_info", {"tcode": tcode, "query": message[:80], "max_rows": 20}))
        if "字段" in message or "结构" in message or "表" in message or "SE11" in upper or "血缘" in message:
            obj = object_names[0] if object_names else ""
            plan.append(("ddic_meta", {"object_name": obj, "object_type": "TABL"}))
        if "日志" in message or "ZILOG" in upper or "报错" in message or "错误" in message:
            plan.append(("zilog_logs", {"object_name": object_names[0] if object_names else "", "keyword": message[:80], "max_rows": 60}))
        if data_intent and not source_intent:
            plan.append(("safe_table_read", {"table_name": object_names[0] if object_names else "", "fields": [], "ranges": [], "max_rows": 80}))
        if not plan:
            plan.append(("ping", {}))
        return plan

    def _extract_object_names(self, message: str) -> list[str]:
        upper = message.upper()
        names = re.findall(r"(?<![A-Z0-9_/])([A-Z/][A-Z0-9_/]{1,40})(?![A-Z0-9_/])", upper)
        stop_words = {"RFC", "FUNCTION", "TCODE", "SE11", "ZILOG", "SAP", "ECC"}
        return [name for name in names if name not in stop_words]

    async def _ai_decide_next_calls(
        self,
        message: str,
        system: SapSystemConfig | None,
        tool_results: list[Any],
        evidence: list[SapToolEvidence],
        seen: set[str],
        remaining_steps: int,
        queued_calls: list[tuple[str, dict[str, Any]]] | None = None,
        conversation_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if remaining_steps <= 0:
            return {"decided": True, "done": True, "calls": [], "reason": "已达到本轮最大工具调用次数"}

        prompt = (
            "你是 SAP 助手的 ReAct 决策器。你只能根据用户问题、已执行工具结果和证据，决定下一步是否继续调用工具。"
            "不要把还能通过工具继续查询的问题交给用户。只有在证据足够、没有可用工具、需要人工授权或达到上限时才停止。"
            "源码分析时必须区分注释和可执行代码：注释只能作为弱线索，不能优先追；实际 CALL FUNCTION、SELECT、PERFORM、赋值语句是强证据。"
            "如果 source_search 返回 discoveredFunctionCalls，优先追这些真实调用的函数源码，不要优先追注释中提到但没有代码调用证据的函数名。"
            "如果 tcode_info 已证明事务码 A 对应程序 B，后续应围绕程序 B 继续查源码和调用链，不要把 A 与 B 的名称不同当作错误。"
            "如果 investigation_state.sufficient 为 true，说明已经有目标字段的可执行赋值或计算证据，应输出 action=answer，不要继续重复搜索。"
            "不要在同一对象上用相近关键词反复 source_search；如果已有 directEvidenceMatches，优先总结证据链。"
            "输出必须是 JSON 对象，格式为："
            '{"action":"continue|answer|need_user","reason":"简短原因","tool_calls":[{"tool_name":"...","params":{}}]}。'
            "可用工具："
            "tcode_info(tcode,query,max_rows) 查询事务码及描述候选；"
            "program_source(object_name,start_line,max_lines) 读取报表/Include 源码，max_lines=0 表示完整拉取但后端会压缩投喂；"
            "function_source(object_name,start_line,max_lines) 读取函数/RFC 源码；"
            "source_search(object_name,object_type,keywords,context_lines,max_matches) 在完整源码中按你自己选择的关键词搜索命中行和上下文；"
            "ddic_meta(object_name,object_type) 查询表或结构元数据；"
            "zilog_logs(object_name,keyword,max_rows) 查询日志；"
            "safe_table_read(table_name,fields,ranges,max_rows) 只读样例数据；"
            "ping() 测试连接。"
            "一次最多给 3 个 tool_calls。不要重复调用已经执行过的完全相同参数。"
        )
        state = {
            "question": message,
            "system": self._system_context(system),
            "remaining_steps": remaining_steps,
            "conversation_context": conversation_context or {},
            "object_relationships": self._extract_object_relationships(tool_results),
            "investigation_state": self._build_investigation_state(message, tool_results),
            "seen_calls": list(seen)[-20:],
            "queued_calls": queued_calls or [],
            "tool_results": [self._compact_value(item.model_dump(), max_text=2200, query=message) for item in tool_results[-8:]],
            "evidence": [self._compact_value(item.model_dump(), max_text=1200, query=message) for item in evidence[-8:]],
        }
        try:
            response = await LLMFactory.safe_invoke(
                [
                    SystemMessage(content=prompt),
                    HumanMessage(content=json.dumps(state, ensure_ascii=False, separators=(",", ":"))[:18000]),
                ],
                capability="complex-reasoning",
                json_mode=True,
                max_retries=2,
            )
            decision = self._parse_json_object(str(response.content))
        except Exception as exc:
            logger.warning(f"SAP 助手 AI 工具决策失败，使用兜底规则: {exc}")
            return {"decided": False, "done": False, "calls": [], "reason": f"AI 工具决策失败：{exc}"}

        action = str(decision.get("action") or "").strip().lower()
        calls = self._normalize_ai_tool_calls(decision.get("tool_calls"), seen)
        return {
            "decided": True,
            "done": action in {"answer", "need_user"} or (action != "continue" and not calls),
            "calls": calls[: min(3, remaining_steps)],
            "reason": str(decision.get("reason") or "").strip()[:300],
        }

    def _parse_json_object(self, text: str) -> dict[str, Any]:
        text = text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, re.S)
            if not match:
                return {}
            data = json.loads(match.group(0))
        return data if isinstance(data, dict) else {}

    def _normalize_ai_tool_calls(self, raw_calls: Any, seen: set[str]) -> list[tuple[str, dict[str, Any]]]:
        allowed_tools = {
            "tcode_info",
            "program_source",
            "function_source",
            "source_search",
            "ddic_meta",
            "zilog_logs",
            "safe_table_read",
            "ping",
        }
        if not isinstance(raw_calls, list):
            return []
        calls: list[tuple[str, dict[str, Any]]] = []
        for item in raw_calls:
            if not isinstance(item, dict):
                continue
            tool_name = str(item.get("tool_name") or item.get("tool") or item.get("name") or "").strip()
            params = item.get("params") or item.get("parameters") or {}
            if tool_name not in allowed_tools or not isinstance(params, dict):
                continue
            normalized = self._normalize_ai_tool_params(tool_name, params)
            call = (tool_name, normalized)
            call_key = json.dumps(call, ensure_ascii=False, sort_keys=True)
            if call_key not in seen and call not in calls:
                calls.append(call)
        return calls

    def _normalize_ai_tool_params(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        def pick(*names: str, default: Any = "") -> Any:
            for name in names:
                if name not in params:
                    continue
                value = params[name]
                if value is not None and value != "":
                    return value
            return default

        if tool_name == "tcode_info":
            return {"tcode": pick("tcode", "TCode", "IV_TCODE"), "query": pick("query", "keyword", "IV_QUERY"), "max_rows": pick("max_rows", "maxRows", "IV_MAX_ROWS", default=20)}
        if tool_name in {"program_source", "function_source"}:
            return {
                "object_name": pick("object_name", "object", "program", "include", "function", "IV_OBJECT_NAME"),
                "start_line": pick("start_line", "startLine", "IV_START_LINE", default=1),
                "max_lines": pick("max_lines", "maxLines", "IV_MAX_LINES", "line_count", default=0),
            }
        if tool_name == "source_search":
            return {
                "object_name": pick("object_name", "object", "program", "include", "IV_OBJECT_NAME"),
                "object_type": pick("object_type", "type", "IV_OBJECT_TYPE", default="PROG"),
                "keywords": pick("keywords", "keyword", "query", default=[]),
                "context_lines": pick("context_lines", "contextLines", default=12),
                "max_matches": pick("max_matches", "maxMatches", default=20),
            }
        if tool_name == "ddic_meta":
            return {"object_name": pick("object_name", "table", "structure", "IV_OBJECT_NAME"), "object_type": pick("object_type", "type", "IV_OBJECT_TYPE", default="TABL")}
        if tool_name == "zilog_logs":
            return {"object_name": pick("object_name", "object", "IV_OBJECT_NAME"), "keyword": pick("keyword", "query", "IV_KEYWORD"), "max_rows": pick("max_rows", "maxRows", "IV_MAX_ROWS", default=60)}
        if tool_name == "safe_table_read":
            return {
                "table_name": pick("table_name", "table", "IV_TABLE_NAME"),
                "fields": pick("fields", "IT_FIELDS", default=[]),
                "ranges": pick("ranges", "conditions", "IT_RANGES", default=[]),
                "max_rows": pick("max_rows", "maxRows", "IV_MAX_ROWS", default=80),
            }
        return params

    def _react_next_calls(
        self,
        message: str,
        object_names: list[str],
        tool_name: str,
        params: dict[str, Any],
        result: Any,
    ) -> list[tuple[str, dict[str, Any]]]:
        data = result.data if hasattr(result, "data") else None
        parsed = self._parsed_payload(data)
        next_calls: list[tuple[str, dict[str, Any]]] = []

        if tool_name in {"function_source", "program_source"} and parsed:
            if parsed.get("success") is False and "对象名不能为空" in str(parsed.get("message")):
                fallback = next((name for name in object_names if name.startswith(("ZFM_", "YFM_"))), object_names[0] if object_names else "")
                if fallback:
                    next_calls.append(("function_source", {"object_name": fallback, "start_line": 1, "max_lines": 0}))
                return next_calls

            lines = parsed.get("lines")
            if isinstance(lines, list) and not self._contains_function_body(lines):
                for include in self._extract_source_includes(lines):
                    next_calls.append(("program_source", {"object_name": include, "start_line": 1, "max_lines": 0}))
                    if len(next_calls) >= 2:
                        break
            if isinstance(lines, list) and self._needs_source_focus(message, params):
                for start_line in self._find_relevant_source_windows(message, parsed):
                    next_calls.append(
                        (
                            "program_source",
                            {
                                "object_name": str(parsed.get("resolvedProgram") or parsed.get("object") or params.get("object_name") or ""),
                                "start_line": start_line,
                                "max_lines": 120,
                            },
                        )
                    )
                    if len(next_calls) >= 3:
                        break
                for start_line in self._source_pagination_windows(parsed):
                    next_calls.append(
                        (
                            "program_source",
                            {
                                "object_name": str(parsed.get("resolvedProgram") or parsed.get("object") or params.get("object_name") or ""),
                                "start_line": start_line,
                                "max_lines": 180,
                            },
                        )
                    )
                    if len(next_calls) >= 5:
                        break
        if tool_name == "tcode_info" and parsed:
            for program in self._extract_programs_from_tcode_result(parsed):
                next_calls.append(("program_source", {"object_name": program, "start_line": 1, "max_lines": 0}))
                if len(next_calls) >= 3:
                    break
        return next_calls

    def _is_answer_ready(self, message: str, tool_results: list[Any]) -> bool:
        if not self._requires_executable_logic(message):
            return True
        return self._has_executable_logic_evidence(tool_results)

    def _requires_executable_logic(self, message: str) -> bool:
        upper = message.upper()
        triggers = (
            "怎么取",
            "怎么来",
            "怎么算",
            "取值",
            "来源",
            "逻辑",
            "字段血缘",
            "开票",
            "金额",
            "NETWR",
            "KWERT",
            "FKIMG",
        )
        return any(trigger in message or trigger in upper for trigger in triggers)

    def _has_executable_logic_evidence(self, tool_results: list[Any]) -> bool:
        for result in tool_results:
            if getattr(result, "status", "") != "success":
                continue
            tool_name = getattr(result, "tool_name", "")
            data = getattr(result, "data", None)
            if tool_name == "source_search" and self._source_search_has_logic(data):
                return True
        return False

    def _source_search_has_logic(self, data: Any) -> bool:
        if not isinstance(data, dict):
            return False
        matches = data.get("matches")
        if not isinstance(matches, list):
            return False
        for match in matches:
            if not isinstance(match, dict) or match.get("lineKind") != "code":
                continue
            text = str(match.get("text") or "")
            context = "\n".join(str(line) for line in match.get("context") or [])
            if self._looks_like_business_logic(f"{text}\n{context}"):
                return True
        return False

    def _has_sufficient_answer_evidence(self, message: str, tool_results: list[Any]) -> bool:
        state = self._build_investigation_state(message, tool_results)
        return bool(state.get("sufficient"))

    def _build_investigation_state(self, message: str, tool_results: list[Any]) -> dict[str, Any]:
        focus_terms = self._answer_focus_terms(message)
        direct_matches: list[dict[str, Any]] = []
        calculation_matches: list[dict[str, Any]] = []
        source_search_counts: dict[str, int] = {}
        discovered_calls: list[str] = []

        for result in tool_results:
            if getattr(result, "status", "") != "success":
                continue
            tool_name = getattr(result, "tool_name", "")
            data = getattr(result, "data", None)
            if tool_name != "source_search" or not isinstance(data, dict):
                continue
            object_name = str(data.get("object") or data.get("resolvedProgram") or "").upper()
            if object_name:
                source_search_counts[object_name] = source_search_counts.get(object_name, 0) + 1
            for call in data.get("discoveredFunctionCalls") or []:
                if isinstance(call, dict):
                    function_name = str(call.get("function") or "").upper()
                    if function_name and function_name not in discovered_calls:
                        discovered_calls.append(function_name)
            matches = data.get("matches")
            if not isinstance(matches, list):
                continue
            for match in matches:
                if not isinstance(match, dict) or match.get("lineKind") != "code":
                    continue
                text = str(match.get("text") or "")
                context = "\n".join(str(line) for line in match.get("context") or [])
                full_text = f"{text}\n{context}"
                if not self._contains_focus_term(full_text, focus_terms):
                    continue
                if self._looks_like_direct_assignment(full_text):
                    direct_matches.append(self._compact_match(match))
                if self._looks_like_calculation(full_text):
                    calculation_matches.append(self._compact_match(match))

        sufficient = bool(calculation_matches or len(direct_matches) >= 2 or (direct_matches and discovered_calls))
        return {
            "sufficient": sufficient,
            "focusTerms": focus_terms,
            "sourceSearchCounts": source_search_counts,
            "directEvidenceCount": len(direct_matches),
            "calculationEvidenceCount": len(calculation_matches),
            "directEvidenceMatches": direct_matches[:6],
            "calculationMatches": calculation_matches[:6],
            "discoveredFunctionCalls": discovered_calls[:12],
        }

    def _answer_focus_terms(self, message: str) -> list[str]:
        upper = message.upper()
        terms = self._extract_object_names(message)
        if any(word in message or word in upper for word in ("开票", "发票", "INVOICE", "BILLING")):
            terms.extend(["PZKPJE", "RMBKPJE", "FKIMG", "VBRP", "VBRK"])
        if any(word in message or word in upper for word in ("金额", "价", "PRICE", "AMOUNT", "NETWR", "KWERT")):
            terms.extend(["NETWR", "KWERT", "KBETR", "ZPR0", "ZPR0P", "ZPR0P_P1", "KONV"])
        if not terms:
            terms.extend(["NETWR", "KWERT", "KBETR", "FKIMG", "CALL FUNCTION", "SELECT"])
        seen: set[str] = set()
        normalized: list[str] = []
        for term in terms:
            item = str(term).strip().upper()
            if item and item not in seen:
                normalized.append(item)
                seen.add(item)
        return normalized[:20]

    def _contains_focus_term(self, text: str, terms: list[str]) -> bool:
        upper = text.upper()
        return any(term in upper for term in terms)

    def _looks_like_direct_assignment(self, text: str) -> bool:
        upper = text.upper()
        if not self._looks_like_business_logic(upper):
            return False
        return any(token in upper for token in ("=", "MOVE", "MOVE-CORRESPONDING", "COLLECT", "APPEND", "READ TABLE", "SELECT"))

    def _looks_like_calculation(self, text: str) -> bool:
        upper = text.upper()
        if not self._looks_like_direct_assignment(upper):
            return False
        return any(token in upper for token in (" * ", "*", " / ", "/", "+", "-", "MULTIPLY", "DIVIDE", "ADD", "SUBTRACT", "ZFM_"))

    def _compact_match(self, match: dict[str, Any]) -> dict[str, Any]:
        context = match.get("context") or []
        return {
            "line": match.get("line"),
            "matchedKeywords": match.get("matchedKeywords"),
            "text": str(match.get("text") or "")[:220],
            "contextRange": match.get("contextRange"),
            "contextPreview": [str(line)[:220] for line in context[:8]],
        }

    def _looks_like_business_logic(self, text: str) -> bool:
        upper = text.upper()
        if not any(token in upper for token in ("SELECT", "LOOP", "READ TABLE", "CALL FUNCTION", "PERFORM", "MOVE", "=", "COLLECT", "SUM", "ADD", "SUBTRACT", "MULTIPLY", "DIVIDE")):
            return False
        definition_only = (" TYPE " in upper or " LIKE " in upper) and not any(token in upper for token in ("SELECT", "LOOP", "READ TABLE", "CALL FUNCTION", "PERFORM", "=", "MOVE"))
        return not definition_only

    def _filter_viable_calls(
        self,
        calls: list[tuple[str, dict[str, Any]]],
        seen: set[str],
        tool_results: list[Any],
    ) -> list[tuple[str, dict[str, Any]]]:
        counts = self._source_search_counts(tool_results)
        viable: list[tuple[str, dict[str, Any]]] = []
        for call in calls:
            if self._is_seen_call(call, seen):
                continue
            tool_name, params = call
            if tool_name == "source_search":
                object_name = str(params.get("object_name") or params.get("object") or "").upper()
                if counts.get(object_name, 0) >= 6:
                    continue
            viable.append(call)
        return viable

    def _filter_unseen_calls(
        self,
        calls: list[tuple[str, dict[str, Any]]],
        seen: set[str],
    ) -> list[tuple[str, dict[str, Any]]]:
        return [call for call in calls if not self._is_seen_call(call, seen)]

    def _is_seen_call(self, call: tuple[str, dict[str, Any]], seen: set[str]) -> bool:
        return json.dumps(call, ensure_ascii=False, sort_keys=True) in seen

    def _source_search_counts(self, tool_results: list[Any]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for result in tool_results:
            if getattr(result, "tool_name", "") != "source_search" or getattr(result, "status", "") != "success":
                continue
            data = getattr(result, "data", None)
            if not isinstance(data, dict):
                continue
            object_name = str(data.get("object") or data.get("resolvedProgram") or "").upper()
            if object_name:
                counts[object_name] = counts.get(object_name, 0) + 1
        return counts

    def _gap_next_calls(
        self,
        message: str,
        tool_results: list[Any],
        seen: set[str],
    ) -> list[tuple[str, dict[str, Any]]]:
        keywords = self._source_focus_keywords(message) or ["SELECT", "LOOP AT", "READ TABLE", "CALL FUNCTION", "NETWR", "KWERT", "FKIMG"]
        calls: list[tuple[str, dict[str, Any]]] = []
        for relationship in self._extract_object_relationships(tool_results):
            program = str(relationship.get("program") or "").strip()
            if program:
                calls.extend(self._source_gap_calls_for_object(program, "PROG", keywords, seen))
                if calls:
                    return calls[:3]
        for result in tool_results:
            if getattr(result, "tool_name", "") not in {"program_source", "function_source"} or getattr(result, "status", "") != "success":
                continue
            parsed = self._parsed_payload(getattr(result, "data", None))
            if not parsed:
                continue
            object_name = str(parsed.get("resolvedProgram") or parsed.get("object") or "").strip()
            if object_name:
                object_type = "FUNC" if getattr(result, "tool_name", "") == "function_source" else "PROG"
                calls.extend(self._source_gap_calls_for_object(object_name, object_type, keywords, seen))
                calls.extend(self._source_page_gap_calls(parsed, object_name, seen))
                if calls:
                    return calls[:3]
        return self._filter_unseen_calls(calls, seen)[:3]

    def _source_gap_calls_for_object(
        self,
        object_name: str,
        object_type: str,
        keywords: list[str],
        seen: set[str],
    ) -> list[tuple[str, dict[str, Any]]]:
        candidates = [
            ("source_search", {"object_name": object_name, "object_type": object_type, "keywords": keywords, "context_lines": 18, "max_matches": 40}),
            (
                "source_search",
                {
                    "object_name": object_name,
                    "object_type": object_type,
                    "keywords": ["SELECT", "LOOP AT", "READ TABLE", "CALL FUNCTION", "PERFORM", "MOVE", "COLLECT", "NETWR", "KWERT", "FKIMG"],
                    "context_lines": 24,
                    "max_matches": 60,
                },
            ),
        ]
        return self._filter_unseen_calls(candidates, seen)

    def _source_page_gap_calls(
        self,
        parsed: dict[str, Any],
        object_name: str,
        seen: set[str],
    ) -> list[tuple[str, dict[str, Any]]]:
        total_lines = int(parsed.get("totalLines") or 0)
        if total_lines <= 180:
            return []
        candidates: list[tuple[str, dict[str, Any]]] = []
        for start_line in range(181, min(total_lines, 1800) + 1, 240):
            candidates.append(("program_source", {"object_name": object_name, "start_line": start_line, "max_lines": 240}))
        return self._filter_unseen_calls(candidates, seen)

    def _extract_programs_from_tcode_result(self, parsed: dict[str, Any]) -> list[str]:
        programs: list[str] = []
        items = parsed.get("items")
        if not isinstance(items, list):
            return programs
        for item in items:
            if not isinstance(item, dict):
                continue
            program = str(item.get("program") or item.get("pgmna") or "").strip().upper()
            if program and program not in programs:
                programs.append(program)
        return programs

    def _needs_source_focus(self, message: str, params: dict[str, Any]) -> bool:
        if int(params.get("max_lines") or 0) > 0:
            return False
        keywords = self._source_focus_keywords(message)
        return bool(keywords)

    def _source_focus_keywords(self, message: str) -> list[str]:
        upper = message.upper()
        keywords: list[str] = []
        keyword_groups = [
            (("开票", "发票", "票据", "INVOICE", "BILLING"), ["VBRK", "VBRP", "VBFA", "KONV", "PRCD", "NETWR", "VNETWR", "KWERT", "FKIMG", "FKDAT"]),
            (("金额", "价税", "含税", "未税", "PRICE", "AMOUNT"), ["NETWR", "VNETWR", "MWSBP", "KWERT", "KNUMV", "KBETR", "KPEIN", "KMEIN"]),
            (("字段", "怎么算", "怎么取", "来源", "血缘"), ["SELECT", "JOIN", "FORM", "PERFORM", "CALL FUNCTION", "LOOP AT", "READ TABLE", "MOVE-CORRESPONDING"]),
        ]
        for triggers, values in keyword_groups:
            if any(trigger in message or trigger in upper for trigger in triggers):
                keywords.extend(values)
        for name in self._extract_object_names(message):
            if name not in keywords:
                keywords.append(name)
        return keywords

    def _find_relevant_source_windows(self, message: str, parsed: dict[str, Any]) -> list[int]:
        lines = parsed.get("lines")
        if not isinstance(lines, list):
            return []
        keywords = self._source_focus_keywords(message)
        if not keywords:
            return []
        base_line = int(parsed.get("startLine") or 1)
        starts: list[int] = []
        for offset, line in enumerate(lines):
            text = str(line).upper()
            if any(keyword in text for keyword in keywords):
                start_line = max(1, base_line + offset - 35)
                if all(abs(start_line - existing) > 80 for existing in starts):
                    starts.append(start_line)
            if len(starts) >= 3:
                break
        return starts

    def _source_pagination_windows(self, parsed: dict[str, Any]) -> list[int]:
        start_line = int(parsed.get("startLine") or 1)
        max_lines = int(parsed.get("maxLines") or 0)
        total_lines = int(parsed.get("totalLines") or 0)
        if start_line != 1 or max_lines != 0 or total_lines <= 220:
            return []
        windows = [181, 361, 541, 721]
        return [line for line in windows if line <= total_lines]

    def _parsed_payload(self, data: Any) -> dict[str, Any] | None:
        if not isinstance(data, dict):
            return None
        parsed = data.get("JSON_PARSED")
        if isinstance(parsed, dict):
            return parsed
        return data

    def _contains_function_body(self, lines: list[Any]) -> bool:
        joined = "\n".join(str(line).upper() for line in lines)
        return "FUNCTION " in joined and "ENDFUNCTION" in joined

    def _extract_source_includes(self, lines: list[Any]) -> list[str]:
        includes: list[str] = []
        for line in lines:
            match = re.search(r"^\s*INCLUDE\s+([A-Z0-9_]+)", str(line).upper())
            if not match:
                continue
            include = match.group(1).rstrip(".")
            if include.endswith("TOP"):
                continue
            includes.append(include)
        includes.sort(key=lambda item: (0 if re.search(r"U\d+$", item) else 1 if item.endswith("UXX") else 2, item))
        return includes

    async def _search_knowledge(
        self,
        db: AsyncSession,
        knowledge_base_ids: list[int],
        query: str,
    ) -> list[SapToolEvidence]:
        evidence: list[SapToolEvidence] = []
        for kb_id in knowledge_base_ids[:5]:
            try:
                result = await knowledge_base_service.search(db, kb_id, query, top_k=3)
            except Exception as exc:
                logger.warning(f"知识库检索失败 kb_id={kb_id}: {exc}")
                continue
            for hit in result.hits:
                evidence.append(
                    SapToolEvidence(
                        evidence_type="kb",
                        title=f"知识库片段：{hit.title}",
                        summary=hit.content[:160],
                        source_object=hit.title,
                        location=hit.source_label,
                        confidence=hit.score,
                        content=hit.model_dump(),
                    )
                )
        return evidence

    async def _compose_answer(
        self,
        message: str,
        system: SapSystemConfig | None,
        tool_results: list[Any],
        evidence: list[SapToolEvidence],
        conversation_context: dict[str, Any] | None = None,
    ) -> str:
        context = {
            "system": self._system_context(system),
            "conversation_context": conversation_context or {},
            "object_relationships": self._extract_object_relationships(tool_results),
            "answer_readiness": {
                "requires_executable_logic": self._requires_executable_logic(message),
                "has_executable_logic_evidence": self._has_executable_logic_evidence(tool_results),
                "has_sufficient_answer_evidence": self._has_sufficient_answer_evidence(message, tool_results),
                "rule": "涉及字段取值、金额计算或血缘追踪时，只有注释和字段定义不能作为结论，必须有可执行取数、赋值、计算或函数调用证据。",
            },
            "investigation_state": self._build_investigation_state(message, tool_results),
            "tool_results": [self._compact_value(item.model_dump(), max_text=2200, query=message) for item in self._select_answer_tool_results(tool_results)],
            "evidence": [self._compact_value(item.model_dump(), max_text=1600, query=message) for item in self._select_answer_evidence(evidence)],
        }
        prompt = (
            "你是 SAP 助手。请基于工具证据回答用户问题，中文输出。"
            "必须包含：结论、证据链、下一步建议；如果 SAP RFC 连接不可用或未配置，要明确说明。"
            "严禁在没有源码、DDIC、日志或知识库证据时，仅凭函数名、事务码命名或通用经验推断具体业务逻辑。"
            "如果证据不足，只说明缺少哪些证据以及下一步应该调用哪个工具。"
            "如果 tcode_info 已证明事务码 A 对应程序 B，那么后续对程序 B 的源码、搜索和函数调用分析都属于事务码 A 的证据链；"
            "严禁因为 A 与 B 名称不同就说搜索对象错误。用户问事务码时，应表述为“事务码 A 对应程序 B”。"
            "涉及字段取值、金额计算或血缘追踪时，注释、标题和 DATA/TYPES 字段定义只能作为线索，不能直接下结论；"
            "必须基于可执行代码中的 SELECT、LOOP、READ TABLE、CALL FUNCTION、PERFORM、赋值或计算语句给出结论。"
            "如果 answer_readiness.has_executable_logic_evidence 为 false，结论必须写“当前证据不足以确定具体取值逻辑”，"
            "并列出已知线索和缺失的可执行代码证据，不得把注释中的描述改写成事实结论。"
        )
        try:
            response = await LLMFactory.safe_invoke(
                [
                    SystemMessage(content=prompt),
                    HumanMessage(content=f"用户问题：{message}\n压缩证据JSON：{json.dumps(context, ensure_ascii=False, separators=(',', ':'))[:18000]}"),
                ],
                capability="complex-reasoning",
                json_mode=False,
                max_retries=2,
            )
            return str(response.content)
        except Exception as exc:
            logger.warning(f"SAP 助手 LLM 总结失败，使用规则兜底: {exc}")
            lines = [
                "我已经按证据链方式完成第一轮排查。",
                "",
                f"结论：当前问题已调用 {len(tool_results)} 个 SAP 工具，获得 {len(evidence)} 条证据。"
                + (" 其中部分工具调用失败，请检查 pyrfc、SAP NetWeaver RFC SDK 或系统连接配置。" if any(result.status == "failed" for result in tool_results) else ""),
                "",
                "证据链：",
            ]
            for item in evidence[:8]:
                lines.append(f"- {item.title}：{item.summary or '已返回结构化结果'}")
            lines.extend(["", "下一步建议：补充 SAP RFC 连接参数、ZILOG 表结构和只读取数审计配置后，再对同一问题重新执行。"])
            return "\n".join(lines)

    def _extract_object_relationships(self, tool_results: list[Any]) -> list[dict[str, Any]]:
        relationships: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for result in tool_results:
            if getattr(result, "tool_name", "") != "tcode_info" or getattr(result, "status", "") != "success":
                continue
            parsed = self._parsed_payload(getattr(result, "data", None))
            if not parsed:
                continue
            items = parsed.get("items")
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                tcode = str(item.get("tcode") or "").strip().upper()
                program = str(item.get("program") or item.get("pgmna") or "").strip().upper()
                if not tcode or not program:
                    continue
                key = (tcode, program)
                if key in seen:
                    continue
                seen.add(key)
                relationships.append(
                    {
                        "type": "tcode_program",
                        "tcode": tcode,
                        "program": program,
                        "screen": item.get("screen") or item.get("dypno"),
                        "text": item.get("text"),
                        "rule": f"事务码 {tcode} 对应程序 {program}，程序源码证据可用于回答该事务码问题。",
                    }
                )
        return relationships

    def _select_answer_tool_results(self, tool_results: list[Any]) -> list[Any]:
        scored: list[tuple[int, int, Any]] = []
        for index, item in enumerate(tool_results):
            score = 0
            tool_name = getattr(item, "tool_name", "")
            status = getattr(item, "status", "")
            data = getattr(item, "data", None)
            if status == "success":
                score += 2
            if tool_name == "tcode_info":
                score += 6
            if tool_name in {"source_search", "function_source", "program_source"}:
                score += 3
            if isinstance(data, dict):
                if data.get("matchCount"):
                    score += 5
                if data.get("matches"):
                    score += 4
            scored.append((score, index, item))
        selected = sorted(scored, key=lambda row: (row[0], row[1]), reverse=True)[:16]
        return [item for _, _, item in sorted(selected, key=lambda row: row[1])]

    def _select_answer_evidence(self, evidence: list[SapToolEvidence]) -> list[SapToolEvidence]:
        scored: list[tuple[int, int, SapToolEvidence]] = []
        for index, item in enumerate(evidence):
            score = 0
            if item.evidence_type in {"source", "source_search"}:
                score += 3
            if item.location == "ZFM_AI_GET_TCODE_INFO":
                score += 6
            content = item.content or {}
            data = content.get("data") if isinstance(content, dict) else None
            if isinstance(data, dict):
                if data.get("matchCount"):
                    score += 5
                if data.get("matches"):
                    score += 4
            if item.confidence >= 0.8:
                score += 1
            scored.append((score, index, item))
        selected = sorted(scored, key=lambda row: (row[0], row[1]), reverse=True)[:18]
        return [item for _, _, item in sorted(selected, key=lambda row: row[1])]

    def _build_flowchart(self, plan: list[tuple[str, dict[str, Any]]], evidence: list[SapToolEvidence]) -> str:
        nodes = ["flowchart TD", '  A["用户问题"]']
        previous = "A"
        for index, (tool_name, _) in enumerate(plan, start=1):
            node_id = f"N{index}"
            nodes.append(f'  {node_id}["{tool_name}"]')
            nodes.append(f"  {previous} --> {node_id}")
            previous = node_id
        nodes.append('  Z["证据链回答"]')
        nodes.append(f"  {previous} --> Z")
        if any(item.evidence_type == "kb" for item in evidence):
            nodes.append('  K["知识库检索"] --> Z')
        return "\n".join(nodes)

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

    def _compact_value(self, value: Any, max_text: int = 1200, query: str | None = None) -> Any:
        if isinstance(value, str):
            return value if len(value) <= max_text else f"{value[:max_text]}...<已截断，可继续调用工具获取后续内容>"
        if isinstance(value, list):
            return [self._compact_value(item, max_text=max_text, query=query) for item in value[:40]]
        if isinstance(value, dict):
            if isinstance(value.get("lines"), list):
                return self._compact_source_payload(value, query=query)
            compacted: dict[str, Any] = {}
            for key, item in value.items():
                if key in {"ET_JSON_LINES", "JSON_TEXT"}:
                    continue
                compacted[key] = self._compact_value(item, max_text=max_text, query=query)
            return compacted
        return value

    def _compact_source_payload(self, value: dict[str, Any], query: str | None = None) -> dict[str, Any]:
        lines = value.get("lines")
        if not isinstance(lines, list):
            return value
        start_line = int(value.get("startLine") or 1)
        total_lines = int(value.get("totalLines") or len(lines))
        visible_lines = lines[:180]
        focused_excerpts = self._focused_source_excerpts(lines, start_line, query or "")
        return {
            **{key: item for key, item in value.items() if key != "lines"},
            "fedLineRange": [start_line, start_line + len(visible_lines) - 1],
            "lines": visible_lines,
            "focusedExcerpts": focused_excerpts,
            "note": f"源码已完整拉取 {total_lines} 行；本次仅投喂前 {len(visible_lines)} 行，后续可按行号继续取片段。",
        }

    def _focused_source_excerpts(self, lines: list[Any], start_line: int, query: str) -> list[dict[str, Any]]:
        keywords = self._source_focus_keywords(query)
        if not keywords:
            return []
        excerpts: list[dict[str, Any]] = []
        for offset, line in enumerate(lines):
            text = str(line).upper()
            if not any(keyword in text for keyword in keywords):
                continue
            begin = max(0, offset - 18)
            end = min(len(lines), offset + 42)
            line_range = [start_line + begin, start_line + end - 1]
            if any(abs(line_range[0] - item["lineRange"][0]) < 45 for item in excerpts):
                continue
            excerpts.append(
                {
                    "lineRange": line_range,
                    "matchedLine": start_line + offset,
                    "matchedText": str(line)[:240],
                    "lines": lines[begin:end],
                }
            )
            if len(excerpts) >= 4:
                break
        return excerpts


sap_assistant_service = SapAssistantService()
