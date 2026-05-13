import json
import re
from collections.abc import Awaitable, Callable
from typing import Any, Literal, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.langfuse_observability import langfuse_observability
from app.core.llm_factory import LLMFactory
from app.models.agent.sap_assistant import SapAssistantMessage, SapAssistantSession, SapSystemConfig
from app.schemas.agent.sap_assistant import SapAssistantChatRequest, SapAssistantChatResponse, SapToolEvidence
from app.services.agent.sap_assistant.tool_service import sap_tool_service
from app.services.knowledge_base_service import knowledge_base_service


EventSink = Callable[[str, dict[str, Any]], Awaitable[None]]
SapGraphAction = Literal["tool", "finish"]


class SapGraphState(TypedDict, total=False):
    db: AsyncSession
    request: SapAssistantChatRequest
    session: SapAssistantSession
    system: SapSystemConfig | None
    user_id: int | None
    event_sink: EventSink | None
    timeline: list[dict[str, Any]]
    tool_results: list[Any]
    evidence: list[SapToolEvidence]
    executed_plan: list[tuple[str, dict[str, Any]]]
    seen_call_keys: set[str]
    history_text: str
    observations: list[str]
    source_notes: list[dict[str, Any]]
    next_action: SapGraphAction
    next_tool: str | None
    next_params: dict[str, Any]
    decision_reason: str
    stop_reason: str
    answer: str


class SapGraphAgentService:
    """基于 LangGraph 的 SAP 助手编排。

    设计重点是减少 token：LLM 决策只读取压缩状态，工具完整产物保留给前端和审计，
    源码只抽取关键片段进入下一轮决策与最终总结。
    """

    MAX_TOOL_CALLS = 7
    MAX_HISTORY_TEXT = 2600
    MAX_OBSERVATIONS = 8
    MAX_SOURCE_SNIPPETS = 14
    MAX_MODEL_TEXT = 2400
    AVAILABLE_TOOLS = {
        "tcode_info": "查询事务码对应程序、屏幕号和描述。",
        "program_source": "读取 ABAP 程序、Report 或 Include 的完整源码；模型只接收自动提取的关键片段。",
        "function_source": "读取 ABAP Function Module/RFC 的完整源码；模型只接收自动提取的关键片段。",
        "ddic_meta": "查询 DDIC 表、结构、字段、数据元素和域定义。",
        "zilog_logs": "查询 ZILOG 日志。",
        "safe_table_read": "通过 SAP 只读 RFC 小批量读取样例数据。",
        "latest_table_read": "按排序字段读取 Top N 最新记录；询问最新、最后一笔、最大凭证号时优先使用。",
        "knowledge_search": "检索用户选择的通用知识库。",
    }

    def __init__(self) -> None:
        self._graph = self._build_graph()

    async def run(
        self,
        db: AsyncSession,
        request: SapAssistantChatRequest,
        session: SapAssistantSession,
        system: SapSystemConfig | None,
        user_id: int | None = None,
        event_sink: EventSink | None = None,
    ) -> SapAssistantChatResponse:
        initial_state: SapGraphState = {
            "db": db,
            "request": request,
            "session": session,
            "system": system,
            "user_id": user_id,
            "event_sink": event_sink,
            "timeline": [],
            "tool_results": [],
            "evidence": [],
            "executed_plan": [],
            "seen_call_keys": set(),
            "observations": [],
            "source_notes": [],
            "next_action": "tool",
            "next_tool": None,
            "next_params": {},
            "decision_reason": "",
            "stop_reason": "",
            "answer": "",
        }
        with langfuse_observability.current_observation(
            name="sap_assistant_langgraph",
            as_type="agent",
            input={"message": request.message, "session_id": session.id},
            metadata={"user_id": user_id, "sap_system": self._system_context(system), "model_name": request.model_name},
        ) as agent_obs:
            final_state = await self._graph.ainvoke(initial_state, config={"recursion_limit": 24})
            agent_obs.update(
                output={
                    "answer": final_state.get("answer", ""),
                    "tool_count": len(final_state.get("tool_results", [])),
                    "evidence_count": len(final_state.get("evidence", [])),
                },
                metadata={
                    "executed_plan": final_state.get("executed_plan", []),
                    "timeline": final_state.get("timeline", []),
                    "source_note_count": len(final_state.get("source_notes", [])),
                },
            )
        langfuse_observability.flush()
        return SapAssistantChatResponse(
            session_id=session.id or 0,
            answer=final_state.get("answer", ""),
            system_context=self._system_context(system),
            timeline=final_state.get("timeline", []),
            tool_results=final_state.get("tool_results", []),
            evidence=final_state.get("evidence", []),
            flowchart=None,
        )

    def _build_graph(self) -> Any:
        workflow = StateGraph(SapGraphState)
        workflow.add_node("prepare", self._prepare_node)
        workflow.add_node("decide", self._decide_node)
        workflow.add_node("execute_tool", self._execute_tool_node)
        workflow.add_node("summarize", self._summarize_node)
        workflow.set_entry_point("prepare")
        workflow.add_edge("prepare", "decide")
        workflow.add_conditional_edges(
            "decide",
            self._route_after_decision,
            {"execute_tool": "execute_tool", "summarize": "summarize"},
        )
        workflow.add_edge("execute_tool", "decide")
        workflow.add_edge("summarize", END)
        return workflow.compile()

    async def _prepare_node(self, state: SapGraphState) -> SapGraphState:
        session = state["session"]
        system = state.get("system")
        intent_item = self._timeline("intent", "success", "识别问题意图", "由 LangGraph 规划和执行 SAP 助手调查")
        self._append_timeline(state, intent_item)
        await self._emit_timeline(state.get("event_sink"), intent_item)
        if system:
            system_item = self._timeline("system", "success", "确认 SAP 系统", f"{system.name} / {system.client} / {system.environment}")
        else:
            system_item = self._timeline("system", "failed", "确认 SAP 系统", "未匹配到 SAP 系统，SAP RFC 工具将跳过")
        self._append_timeline(state, system_item)
        await self._emit_timeline(state.get("event_sink"), system_item)
        state["history_text"] = await self._load_context_text(state["db"], session)
        return state

    async def _decide_node(self, state: SapGraphState) -> SapGraphState:
        state["next_tool"] = None
        state["next_params"] = {}
        if self._should_stop(state):
            state["next_action"] = "finish"
            if not state.get("stop_reason"):
                state["stop_reason"] = "已经获得足够证据或达到本轮工具预算，进入总结阶段"
            return state

        model = await self._get_streaming_model(state["request"].model_name)
        prompt = self._decision_prompt(state)
        try:
            result = await model.ainvoke([SystemMessage(content=self._decision_system_prompt()), HumanMessage(content=prompt)])
            payload = self._parse_json(self._message_content_to_text(getattr(result, "content", result)))
        except Exception as exc:
            payload = self._fallback_decision_payload(state, exc)

        action = str(payload.get("action") or "finish").lower()
        reason = str(payload.get("reason") or "").strip()
        tool_name = str(payload.get("tool") or "").strip()
        params = payload.get("params") if isinstance(payload.get("params"), dict) else {}
        if action == "tool" and tool_name in self.AVAILABLE_TOOLS:
            params = self._normalize_tool_params(tool_name, params)
            guard = self._tool_guard(state, tool_name, params)
            if guard:
                state["next_action"] = "finish"
                state["stop_reason"] = guard
                state["decision_reason"] = guard
                return state
            state["next_action"] = "tool"
            state["next_tool"] = tool_name
            state["next_params"] = params
            state["decision_reason"] = reason or f"AI 选择调用 {tool_name}"
            plan_item = self._timeline(
                f"plan_{len(state.get('executed_plan', [])) + 1}",
                "success",
                "AI 选择下一步",
                state["decision_reason"],
                tool_name=tool_name,
            )
            self._append_timeline(state, plan_item)
            await self._emit_timeline(state.get("event_sink"), plan_item)
            return state

        state["next_action"] = "finish"
        state["stop_reason"] = reason or "AI 判断可以基于已有证据进入总结阶段"
        state["decision_reason"] = state["stop_reason"]
        return state

    def _fallback_decision_payload(self, state: SapGraphState, error: Exception) -> dict[str, Any]:
        reason = f"模型决策 JSON 解析失败，启用轻量兜底计划：{error}"
        executed_plan = state.get("executed_plan", [])
        if not executed_plan:
            tcode = self._extract_tcode(state["request"].message)
            return {
                "action": "tool",
                "tool": "tcode_info",
                "params": {"tcode": tcode, "query": state["request"].message, "max_rows": 20},
                "reason": reason,
            }
        program = self._latest_program_from_results(state)
        if program and not self._has_called_tool_for_object(state, "program_source", program):
            return {
                "action": "tool",
                "tool": "program_source",
                "params": {"object_name": program},
                "reason": reason,
            }
        function_name = self._next_function_from_source_notes(state)
        if function_name and not self._has_called_tool_for_object(state, "function_source", function_name):
            return {
                "action": "tool",
                "tool": "function_source",
                "params": {"object_name": function_name},
                "reason": reason,
            }
        return {"action": "finish", "reason": f"模型决策失败且没有可安全兜底的下一步：{error}"}

    async def _execute_tool_node(self, state: SapGraphState) -> SapGraphState:
        tool_name = state.get("next_tool")
        if not tool_name:
            state["stop_reason"] = "没有可执行的下一步工具"
            return state
        params = state.get("next_params", {})
        call_key = self._call_key(tool_name, params)
        state.setdefault("seen_call_keys", set()).add(call_key)
        state.setdefault("executed_plan", []).append((tool_name, params))
        node_id = f"{tool_name}_{len(state.get('executed_plan', []))}"
        pending_item = self._timeline(
            node_id,
            "pending",
            f"正在{self._tool_action_label(tool_name)}",
            self._tool_pending_detail(tool_name, params),
            tool_name=tool_name,
        )
        self._append_timeline(state, pending_item)
        await self._emit_timeline(state.get("event_sink"), pending_item)

        if tool_name == "knowledge_search":
            result = await self._execute_knowledge_search(state, params)
        else:
            with langfuse_observability.current_observation(
                name=f"sap_tool:{tool_name}",
                as_type="tool",
                input={"tool_name": tool_name, "params": params},
                metadata={"system": self._system_context(state.get("system"))},
            ) as tool_obs:
                result = await sap_tool_service.execute(state["db"], state.get("system"), tool_name, params, session_id=state["session"].id)
                tool_obs.update(
                    output=self._compact_result_for_trace(result.model_dump()),
                    level="ERROR" if result.status == "failed" else "DEFAULT",
                    status_message=result.error_message,
                    metadata={"duration_ms": result.duration_ms, "status": result.status},
                )

        state.setdefault("tool_results", []).append(result)
        state.setdefault("evidence", []).extend(result.evidence)
        observation = self._observation_for_model(tool_name, result)
        state.setdefault("observations", []).append(observation)
        state["observations"] = state["observations"][-self.MAX_OBSERVATIONS :]
        if tool_name in {"program_source", "function_source"} and result.status == "success":
            state.setdefault("source_notes", []).append(self._source_note(tool_name, result.data, state["request"].message))
            state["source_notes"] = state["source_notes"][-self.MAX_SOURCE_SNIPPETS :]

        done_item = self._timeline(
            node_id,
            result.status,
            f"{self._tool_action_label(tool_name)}完成",
            self._tool_done_detail(tool_name, params, result.summary, result.data),
            tool_name=tool_name,
        )
        self._append_timeline(state, done_item)
        await self._emit_timeline(state.get("event_sink"), done_item)
        await self._emit(
            state.get("event_sink"),
            "tool_output",
            {"toolName": self._tool_action_label(result.tool_name), "displayType": "json", "content": result.model_dump()},
        )
        for evidence_item in result.evidence:
            await self._emit(state.get("event_sink"), "evidence", evidence_item.model_dump())
        return state

    async def _summarize_node(self, state: SapGraphState) -> SapGraphState:
        answer_item = self._timeline("answer", "pending", "生成最终回答", "正在基于压缩后的 SAP 证据流式生成总结")
        self._append_timeline(state, answer_item)
        await self._emit_timeline(state.get("event_sink"), answer_item)

        if not state.get("tool_results") and not state.get("evidence"):
            answer = (
                f"本轮 SAP 助手没有拿到可用证据：{state.get('stop_reason') or '未执行有效工具'}\n\n"
                "因此不能给出确定结论。请先确认 SAP 系统配置、RFC 连通性以及问题中的事务码或对象名。"
            )
            state["answer"] = answer
            await self._emit(state.get("event_sink"), "text_delta", {"content": answer})
            return state

        prompt = (
            "你是 SAP 助手。调查已经结束，禁止继续规划或调用工具。"
            "只能基于给定证据回答，不能把注释、字段定义或样例数据改写成确定业务逻辑。"
            "输出中文，包含：结论、证据链、完整流转链路、仍不确定的地方。"
        )
        context_text = self._summary_context_text(state)
        try:
            model = await self._get_streaming_model(state["request"].model_name)
            chunks: list[str] = []
            async for chunk in model.astream([SystemMessage(content=prompt), HumanMessage(content=context_text)]):
                text = self._message_content_to_text(getattr(chunk, "content", ""))
                if not text:
                    continue
                chunks.append(text)
                await self._emit(state.get("event_sink"), "text_delta", {"content": text})
            answer = "".join(chunks).strip()
        except Exception:
            answer = self._fallback_answer(state)
            await self._emit(state.get("event_sink"), "text_delta", {"content": answer})

        state["answer"] = answer or self._fallback_answer(state)
        done_item = self._timeline("answer", "success", "最终回答完成", "SAP 助手已完成 LangGraph 流式总结")
        self._append_timeline(state, done_item)
        await self._emit_timeline(state.get("event_sink"), done_item)
        return state

    def _route_after_decision(self, state: SapGraphState) -> str:
        return "execute_tool" if state.get("next_action") == "tool" and state.get("next_tool") else "summarize"

    async def _execute_knowledge_search(self, state: SapGraphState, params: dict[str, Any]) -> Any:
        from app.schemas.agent.sap_assistant import SapToolResult

        request = state["request"]
        query = str(params.get("query") or request.message)
        top_k = self._clamp_int(params.get("top_k"), 3, 1, 5)
        hits: list[dict[str, Any]] = []
        evidence: list[SapToolEvidence] = []
        for kb_id in request.knowledge_base_ids[:5]:
            result = await knowledge_base_service.search(state["db"], kb_id, query, top_k=top_k)
            for hit in result.hits:
                item = SapToolEvidence(
                    evidence_type="kb",
                    title=f"知识库片段：{hit.title}",
                    summary=hit.content[:180],
                    source_object=hit.title,
                    location=hit.source_label,
                    confidence=hit.score,
                    content=hit.model_dump(),
                )
                evidence.append(item)
                hits.append(item.model_dump())
        return SapToolResult(
            tool_name="knowledge_search",
            status="success",
            summary=f"命中 {len(hits)} 条知识库片段",
            duration_ms=0,
            data={"hits": hits[:top_k]},
            evidence=evidence,
        )

    async def _get_streaming_model(self, model_name: str | None = None) -> Any:
        if model_name:
            return await LLMFactory.get_model_by_name(model_name, streaming=True)
        return await LLMFactory.get_model(capability="complex-reasoning", streaming=True)

    async def _load_context_text(self, db: AsyncSession, session: SapAssistantSession) -> str:
        parts: list[str] = []
        if session.summary:
            parts.append(f"持续记忆：{session.summary[:1400]}")
        if session.id:
            result = await db.exec(
                select(SapAssistantMessage)
                .where(SapAssistantMessage.session_id == session.id)
                .order_by(SapAssistantMessage.create_time.desc())
                .limit(4)
            )
            messages = list(reversed(result.all()))
            for item in messages:
                role = "用户" if item.role == "user" else "助手"
                parts.append(f"{role}：{item.content[:420]}")
        return "\n".join(parts)[-self.MAX_HISTORY_TEXT :]

    def _decision_system_prompt(self) -> str:
        return (
            "你是一个高级 SAP ECC 调查 Agent 的决策器。你的唯一任务是选择下一步工具或停止。"
            "必须节省 token：不要重复调用同一工具同一参数；不要为了确认已知事实继续查。"
            "如果已经有可执行代码证据，立刻停止。"
            "只返回 JSON，不要输出 Markdown。格式："
            '{"action":"tool|finish","tool":"工具名或空","params":{},"reason":"一句话原因"}'
        )

    def _decision_prompt(self, state: SapGraphState) -> str:
        request = state["request"]
        payload = {
            "用户问题": request.message,
            "SAP系统": self._system_context(state.get("system")),
            "会话记忆": state.get("history_text", ""),
            "已调用工具": [
                {"tool": name, "params": params}
                for name, params in state.get("executed_plan", [])[-self.MAX_TOOL_CALLS :]
            ],
            "最近观察": state.get("observations", [])[-self.MAX_OBSERVATIONS :],
            "源码关键片段": self._source_notes_for_prompt(state),
            "剩余工具预算": max(0, self.MAX_TOOL_CALLS - len(state.get("executed_plan", []))),
            "可用工具": self.AVAILABLE_TOOLS,
            "约束": [
                "事务码问题通常先 tcode_info，再读对应 program_source。",
                "源码已读取后，不要要求再次读取同一对象；基于关键片段判断下一步。",
                "发现 CALL FUNCTION 且它可能承接目标字段时，可读取 function_source。",
                "最新、最后一笔、最近、最大凭证号类问题必须用 latest_table_read，并给 sort_fields。",
                "字段取值、金额计算、血缘类问题需要 SELECT/READ TABLE/PERFORM/CALL FUNCTION/赋值/计算等可执行证据。",
            ],
        }
        return json.dumps(payload, ensure_ascii=False, default=str)

    def _source_notes_for_prompt(self, state: SapGraphState) -> list[dict[str, Any]]:
        notes: list[dict[str, Any]] = []
        for item in state.get("source_notes", [])[-6:]:
            notes.append(
                {
                    "object": item.get("object"),
                    "totalLines": item.get("totalLines"),
                    "evidenceSnippets": item.get("evidenceSnippets", [])[:8],
                    "calls": item.get("calls", [])[:12],
                    "assignmentsFound": item.get("assignmentsFound", 0),
                }
            )
        return notes

    def _should_stop(self, state: SapGraphState) -> bool:
        if len(state.get("executed_plan", [])) >= self.MAX_TOOL_CALLS:
            state["stop_reason"] = f"已达到本轮 LangGraph 工具调用预算 {self.MAX_TOOL_CALLS} 次，避免超长链路"
            return True
        if not state.get("executed_plan"):
            return False
        if self._has_executable_source_evidence(state):
            state["stop_reason"] = "已找到可执行源码证据，停止继续检索以节省 token"
            return True
        if state.get("tool_results") and all(getattr(item, "status", "") != "success" for item in state.get("tool_results", [])[-3:]):
            state["stop_reason"] = "连续工具调用未取得成功结果，先基于已有信息说明限制"
            return True
        return False

    def _has_executable_source_evidence(self, state: SapGraphState) -> bool:
        for note in state.get("source_notes", []):
            if int(note.get("assignmentsFound") or 0) > 0:
                return True
        return False

    def _tool_guard(self, state: SapGraphState, tool_name: str, params: dict[str, Any]) -> str:
        if tool_name != "knowledge_search" and not state.get("system"):
            return "未匹配到 SAP 系统，无法继续调用 SAP RFC 工具"
        if self._call_key(tool_name, params) in state.get("seen_call_keys", set()):
            return "该工具和参数已经执行过，停止重复调用并进入总结"
        if len(state.get("executed_plan", [])) >= self.MAX_TOOL_CALLS:
            return f"已达到本轮 LangGraph 工具调用预算 {self.MAX_TOOL_CALLS} 次"
        return ""

    def _normalize_tool_params(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        if tool_name == "tcode_info":
            return {"tcode": str(params.get("tcode") or ""), "query": str(params.get("query") or ""), "max_rows": self._clamp_int(params.get("max_rows"), 20, 1, 50)}
        if tool_name in {"program_source", "function_source"}:
            return {"object_name": str(params.get("object_name") or params.get("program") or "").upper(), "start_line": 1, "max_lines": 0}
        if tool_name == "ddic_meta":
            return {"object_name": str(params.get("object_name") or "").upper(), "object_type": str(params.get("object_type") or "TABL").upper()}
        if tool_name == "zilog_logs":
            return {"object_name": str(params.get("object_name") or "").upper(), "keyword": str(params.get("keyword") or ""), "max_rows": self._clamp_int(params.get("max_rows"), 60, 1, 120)}
        if tool_name in {"safe_table_read", "latest_table_read"}:
            normalized = {
                "table_name": str(params.get("table_name") or "").upper(),
                "fields": params.get("fields") if isinstance(params.get("fields"), list) else [],
                "ranges": params.get("ranges") if isinstance(params.get("ranges"), list) else [],
                "max_rows": self._clamp_int(params.get("max_rows"), 1 if tool_name == "latest_table_read" else 80, 1, 200),
            }
            if tool_name == "latest_table_read":
                normalized["sort_fields"] = params.get("sort_fields") if isinstance(params.get("sort_fields"), list) else []
            return normalized
        if tool_name == "knowledge_search":
            return {"query": str(params.get("query") or ""), "top_k": self._clamp_int(params.get("top_k"), 3, 1, 5)}
        return params

    def _observation_for_model(self, tool_name: str, result: Any) -> str:
        if result.status != "success":
            return f"{self._tool_action_label(tool_name)}失败：{result.summary or result.error_message}"
        if tool_name in {"program_source", "function_source"}:
            note = self._source_note(tool_name, result.data, "")
            return self._short_text(
                json.dumps(
                    {
                        "tool": tool_name,
                        "summary": result.summary,
                        "object": note.get("object"),
                        "totalLines": note.get("totalLines"),
                        "calls": note.get("calls", [])[:12],
                        "evidenceSnippets": note.get("evidenceSnippets", [])[:8],
                    },
                    ensure_ascii=False,
                    default=str,
                ),
                self.MAX_MODEL_TEXT,
            )
        return self._short_text(json.dumps({"tool": tool_name, "summary": result.summary, "data": self._compact_result_data(tool_name, result.data)}, ensure_ascii=False, default=str), self.MAX_MODEL_TEXT)

    def _source_note(self, tool_name: str, data: Any, question: str) -> dict[str, Any]:
        parsed = self._source_parsed(data)
        lines = parsed.get("lines") if isinstance(parsed, dict) else None
        if not isinstance(lines, list):
            return {"tool": tool_name, "object": "", "totalLines": 0, "evidenceSnippets": [], "calls": [], "assignmentsFound": 0}
        object_name = str(parsed.get("object") or parsed.get("resolvedProgram") or "")
        start_line = self._safe_int(parsed.get("startLine"), 1)
        terms = self._question_terms(question)
        snippets: list[dict[str, Any]] = []
        calls: list[str] = []
        assignments = 0
        for index, raw_line in enumerate(lines):
            line = str(raw_line)
            upper = line.upper()
            line_no = start_line + index
            call_match = re.search(r"CALL\s+FUNCTION\s+'?([A-Z0-9_]+)'?", upper)
            if call_match and call_match.group(1) not in calls:
                calls.append(call_match.group(1))
            perform_match = re.search(r"\bPERFORM\s+([A-Z0-9_]+)", upper)
            if perform_match and perform_match.group(1) not in calls:
                calls.append(f"PERFORM {perform_match.group(1)}")
            has_term = not terms or any(term in upper for term in terms)
            executable = self._looks_executable(upper)
            if executable and has_term:
                assignments += 1
                snippets.extend(self._line_window(lines, line_no, index, start_line, radius=2))
        if not snippets:
            for index, raw_line in enumerate(lines):
                line = str(raw_line)
                if self._looks_executable(line.upper()):
                    snippets.extend(self._line_window(lines, start_line + index, index, start_line, radius=1))
                    if len(snippets) >= 8:
                        break
        return {
            "tool": tool_name,
            "object": object_name,
            "totalLines": parsed.get("totalLines") or len(lines),
            "evidenceSnippets": self._dedupe_snippets(snippets)[: self.MAX_SOURCE_SNIPPETS],
            "calls": calls[:24],
            "assignmentsFound": assignments,
        }

    def _question_terms(self, question: str) -> list[str]:
        upper = question.upper()
        terms = re.findall(r"\b[A-Z][A-Z0-9_]{2,}\b", upper)
        terms.extend(re.findall(r"[A-Z0-9_]*[A-Z]+[A-Z0-9_]*", upper))
        ignore = {"SAP", "RFC", "ABAP", "ECC"}
        return [item for item in dict.fromkeys(terms) if item not in ignore][:12]

    def _looks_executable(self, upper_line: str) -> bool:
        tokens = ("=", "SELECT", "READ TABLE", "CALL FUNCTION", "PERFORM", "MOVE", "LOOP AT", "MODIFY", "APPEND", "COLLECT", "FORM ")
        return any(token in upper_line for token in tokens)

    def _line_window(self, lines: list[Any], line_no: int, index: int, start_line: int, radius: int = 2) -> list[dict[str, Any]]:
        begin = max(0, index - radius)
        end = min(len(lines), index + radius + 1)
        return [{"line": start_line + offset, "text": self._short_text(str(lines[offset]), 260)} for offset in range(begin, end)]

    def _dedupe_snippets(self, snippets: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: set[int] = set()
        result: list[dict[str, Any]] = []
        for item in snippets:
            line = self._safe_int(item.get("line"), 0)
            if line in seen:
                continue
            seen.add(line)
            result.append(item)
        return result

    def _summary_context_text(self, state: SapGraphState) -> str:
        request = state["request"]
        sections = [
            f"用户问题：{request.message}",
            f"SAP 系统：{json.dumps(self._system_context(state.get('system')), ensure_ascii=False, default=str)}",
            f"停止原因：{state.get('stop_reason') or state.get('decision_reason') or '调查完成'}",
        ]
        if state.get("history_text"):
            sections.append(f"会话记忆：\n{state['history_text'][:1200]}")
        sections.append("工具结果摘要：")
        for index, item in enumerate(state.get("tool_results", [])[: self.MAX_TOOL_CALLS], start=1):
            sections.append(f"[{index}] {self._tool_action_label(item.tool_name)} / 状态：{item.status}\n摘要：{item.summary}")
            if item.tool_name not in {"program_source", "function_source"}:
                sections.append(self._short_text(json.dumps(self._compact_result_data(item.tool_name, item.data), ensure_ascii=False, default=str), 1200))
        if state.get("source_notes"):
            sections.append("源码关键证据片段：")
            for note in state["source_notes"][-6:]:
                sections.append(f"对象：{note.get('object')}，总行数：{note.get('totalLines')}")
                for snippet in note.get("evidenceSnippets", [])[:10]:
                    if isinstance(snippet, dict):
                        sections.append(f"{snippet.get('line')}: {snippet.get('text')}")
                calls = note.get("calls") or []
                if calls:
                    sections.append(f"发现的调用：{', '.join(calls[:12])}")
        if state.get("evidence"):
            sections.append("证据摘要：")
            for item in state["evidence"][:10]:
                sections.append(f"- {item.title}：{item.summary or '已返回结构化结果'}；来源：{item.source_object or '-'}；位置：{item.location or '-'}")
        return "\n\n".join(sections)

    def _fallback_answer(self, state: SapGraphState) -> str:
        lines = [
            "本轮 SAP 助手已停止自动追查，并基于已有证据给出阶段性结果。",
            "",
            f"停止原因：{state.get('stop_reason') or state.get('decision_reason') or '调查完成'}",
            "",
            "证据链：",
        ]
        for item in state.get("evidence", [])[:8]:
            lines.append(f"- {item.title}：{item.summary or '已返回结构化结果'}")
        if not state.get("evidence"):
            lines.append("- 暂无可用证据。")
        lines.extend(["", "仍不确定的地方：如需确定字段取值、金额计算或血缘关系，需要继续取得可执行源码、DDIC、日志或只读样例数据。"])
        return "\n".join(lines)

    def _source_parsed(self, data: Any) -> dict[str, Any]:
        if not isinstance(data, dict):
            return {}
        parsed = data.get("JSON_PARSED")
        return parsed if isinstance(parsed, dict) else {}

    def _compact_result_for_trace(self, value: Any) -> Any:
        return self._compact_result_data("trace", value)

    def _compact_result_data(self, tool_name: str, data: Any) -> Any:
        if isinstance(data, list):
            compacted = [self._compact_result_data(tool_name, item) for item in data[:12]]
            if len(data) > 12:
                compacted.append({"truncated": True, "omittedCount": len(data) - 12})
            return compacted
        if not isinstance(data, dict):
            return self._short_text(data, 500) if isinstance(data, str) else data
        parsed = data.get("JSON_PARSED")
        if isinstance(parsed, dict) and isinstance(parsed.get("lines"), list):
            return {
                **{key: value for key, value in data.items() if key != "JSON_PARSED"},
                "JSON_PARSED": {
                    **{key: value for key, value in parsed.items() if key != "lines"},
                    "lineCount": len(parsed.get("lines") or []),
                    "compactNote": "源码全文保留在工具结果和审计中，模型上下文仅使用关键片段。",
                },
            }
        compacted: dict[str, Any] = {}
        for key, value in data.items():
            if key in {"ET_JSON_LINES", "JSON_TEXT"}:
                continue
            compacted[key] = self._compact_result_data(tool_name, value)
        return compacted

    def _tool_action_label(self, tool_name: str) -> str:
        labels = {
            "tcode_info": "查询事务码",
            "program_source": "读取程序完整源码",
            "function_source": "读取函数完整源码",
            "ddic_meta": "查询 DDIC 结构",
            "zilog_logs": "查询 ZILOG 日志",
            "safe_table_read": "读取 SAP 只读样例数据",
            "latest_table_read": "读取 SAP 最新排序数据",
            "knowledge_search": "检索知识库",
        }
        return labels.get(tool_name, tool_name)

    def _tool_pending_detail(self, tool_name: str, params: dict[str, Any]) -> str:
        if tool_name == "tcode_info":
            target = params.get("tcode") or params.get("query") or "用户问题中的事务码"
            return f"正在定位事务码 {target} 对应的程序、屏幕号和描述。"
        if tool_name == "program_source":
            return f"正在读取 ABAP 程序 {params.get('object_name') or '未知程序'} 的完整源码，随后只提取关键证据片段给模型。"
        if tool_name == "function_source":
            return f"正在读取函数 {params.get('object_name') or '未知函数'} 的完整源码，随后只提取关键证据片段给模型。"
        if tool_name == "ddic_meta":
            return f"正在查询 {params.get('object_name') or '未知对象'} 的 DDIC 字段、数据元素和域定义。"
        if tool_name == "zilog_logs":
            keyword = params.get("keyword") or params.get("object_name") or "相关对象"
            return f"正在按 {keyword} 查询 ZILOG 日志，辅助确认运行时证据。"
        if tool_name == "safe_table_read":
            return f"正在通过受控只读 RFC 读取 {params.get('table_name') or '未知表'} 的少量样例数据。"
        if tool_name == "latest_table_read":
            return f"正在按排序字段读取 {params.get('table_name') or '未知表'} 的最新记录：{self._short_text(json.dumps(params.get('sort_fields') or [], ensure_ascii=False), 220)}。"
        if tool_name == "knowledge_search":
            return f"正在检索知识库：{params.get('query') or '用户问题'}。"
        return f"参数：{self._short_text(json.dumps(params, ensure_ascii=False, default=str), 360)}"

    def _tool_done_detail(self, tool_name: str, params: dict[str, Any], summary: str, data: Any) -> str:
        if tool_name in {"program_source", "function_source"}:
            total_lines = self._source_total_lines(data)
            object_name = params.get("object_name") or "源码对象"
            if total_lines:
                return f"已读取 {object_name} 的完整源码，共 {total_lines} 行；模型上下文仅保留关键证据片段，避免反复消耗 token。"
            return f"已读取 {object_name} 的源码；模型将基于提取后的取数、赋值和函数调用片段继续判断。"
        if tool_name == "tcode_info":
            programs = self._programs_from_tcode_data(data)
            if programs:
                return f"已定位事务码对应程序：{', '.join(programs[:5])}。"
        if tool_name == "latest_table_read":
            return f"已按指定排序读取 {params.get('table_name') or '目标表'} 的最新记录。"
        return summary or f"{self._tool_action_label(tool_name)}完成。"

    def _source_total_lines(self, data: Any) -> int | None:
        parsed = self._source_parsed(data)
        total_lines = parsed.get("totalLines")
        try:
            return int(total_lines) if total_lines is not None else None
        except (TypeError, ValueError):
            return None

    def _programs_from_tcode_data(self, data: Any) -> list[str]:
        if not isinstance(data, dict):
            return []
        parsed = data.get("JSON_PARSED")
        payload = parsed if isinstance(parsed, dict) else data
        items = payload.get("items") if isinstance(payload, dict) else None
        if not isinstance(items, list):
            return []
        programs: list[str] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            program = str(item.get("program") or item.get("pgmna") or "").strip()
            if program and program not in programs:
                programs.append(program)
        return programs

    def _extract_tcode(self, message: str) -> str:
        match = re.search(r"\b[ZSA][A-Z0-9]{2,19}\b", message.upper())
        return match.group(0) if match else ""

    def _latest_program_from_results(self, state: SapGraphState) -> str:
        for result in reversed(state.get("tool_results", [])):
            if getattr(result, "tool_name", "") != "tcode_info" or getattr(result, "status", "") != "success":
                continue
            programs = self._programs_from_tcode_data(getattr(result, "data", None))
            if programs:
                return programs[0].upper()
        return ""

    def _next_function_from_source_notes(self, state: SapGraphState) -> str:
        for note in reversed(state.get("source_notes", [])):
            calls = note.get("calls")
            if not isinstance(calls, list):
                continue
            for call in calls:
                name = str(call).strip().upper()
                if not name or name.startswith("PERFORM "):
                    continue
                if name not in {"BINARY", "SEARCH"}:
                    return name
        return ""

    def _has_called_tool_for_object(self, state: SapGraphState, tool_name: str, object_name: str) -> bool:
        target = object_name.upper()
        for name, params in state.get("executed_plan", []):
            if name == tool_name and str(params.get("object_name") or "").upper() == target:
                return True
        return False

    async def _emit_timeline(self, event_sink: EventSink | None, item: dict[str, Any]) -> None:
        await self._emit(
            event_sink,
            "thought_node",
            {
                "nodeId": item["id"],
                "act": "calling_tool" if item["status"] == "pending" else "tool_result",
                "status": item["status"],
                "detailStr": item["detail"],
                "toolName": item.get("title") or item.get("toolName"),
            },
        )

    async def _emit(self, event_sink: EventSink | None, event_type: str, data: dict[str, Any]) -> None:
        if event_sink:
            await event_sink(event_type, data)

    def _append_timeline(self, state: SapGraphState, item: dict[str, Any]) -> None:
        state.setdefault("timeline", []).append(item)

    def _timeline(self, node_id: str, status: str, title: str, detail: str, tool_name: str | None = None) -> dict[str, Any]:
        return {"id": node_id, "status": status, "title": title, "detail": detail, "toolName": tool_name or node_id}

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

    def _parse_json(self, text: str) -> dict[str, Any]:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
            cleaned = re.sub(r"```$", "", cleaned).strip()
        match = re.search(r"\{.*\}", cleaned, re.S)
        if match:
            cleaned = match.group(0)
        data = json.loads(cleaned)
        return data if isinstance(data, dict) else {}

    def _message_content_to_text(self, content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict):
                    parts.append(str(item.get("text") or item.get("content") or ""))
                else:
                    parts.append(str(item))
            return "\n".join(part for part in parts if part)
        if isinstance(content, BaseMessage):
            return self._message_content_to_text(content.content)
        if isinstance(content, AIMessage):
            return self._message_content_to_text(content.content)
        return str(content)

    def _call_key(self, tool_name: str, params: dict[str, Any]) -> str:
        return json.dumps([tool_name, params], ensure_ascii=False, sort_keys=True, default=str)

    def _short_text(self, value: Any, max_len: int) -> str:
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
        return text if len(text) <= max_len else f"{text[:max_len]}\n...[内容过长，已截断]"

    def _clamp_int(self, value: Any, default: int, lower: int, upper: int) -> int:
        try:
            number = int(value if value is not None else default)
        except (TypeError, ValueError):
            number = default
        return max(lower, min(number, upper))

    def _safe_int(self, value: Any, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default


sap_graph_agent_service = SapGraphAgentService()
