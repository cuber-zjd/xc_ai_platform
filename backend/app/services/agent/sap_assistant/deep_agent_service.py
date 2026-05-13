import json
import re
from collections.abc import Awaitable, Callable
from typing import Any

from deepagents import create_deep_agent
from deepagents.middleware._tool_exclusion import _ToolExclusionMiddleware
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.tools import StructuredTool
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.llm_factory import LLMFactory
from app.core.langfuse_observability import langfuse_observability
from app.models.agent.sap_assistant import SapAssistantMessage, SapAssistantSession, SapSystemConfig
from app.schemas.agent.sap_assistant import SapAssistantChatRequest, SapAssistantChatResponse, SapToolEvidence
from app.services.agent.sap_assistant.tool_service import sap_tool_service
from app.services.knowledge_base_service import knowledge_base_service


class SapAgentStop(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class SapDeepAgentService:
    MAX_TOOL_RESULT_TEXT = 2200
    MAX_SOURCE_PACK_TEXT = 22000
    MAX_TOOL_CALLS = 12
    GRAPH_RECURSION_LIMIT = 60
    EXCLUDED_DEEPAGENT_TOOLS = frozenset(
        {
            "write_todo",
            "write_todos",
            "ls",
            "read_file",
            "write_file",
            "edit_file",
            "glob",
            "grep",
            "execute",
            "task",
        }
    )

    async def _get_streaming_model(self, model_name: str | None = None) -> Any:
        if model_name:
            return await LLMFactory.get_model_by_name(model_name, streaming=True)
        return await LLMFactory.get_model(capability="complex-reasoning", streaming=True)

    async def run(
        self,
        db: AsyncSession,
        request: SapAssistantChatRequest,
        session: SapAssistantSession,
        system: SapSystemConfig | None,
        user_id: int | None = None,
        event_sink: Callable[[str, dict[str, Any]], Awaitable[None]] | None = None,
    ) -> SapAssistantChatResponse:
        timeline: list[dict[str, Any]] = []
        tool_results: list[Any] = []
        evidence: list[SapToolEvidence] = []
        executed_plan: list[tuple[str, dict[str, Any]]] = []

        intent_item = self._timeline("intent", "success", "识别问题意图", "由 deepagents 规划和执行 SAP 证据链调查")
        timeline.append(intent_item)
        await self._emit_timeline(event_sink, intent_item)
        if system:
            system_item = self._timeline("system", "success", "确认 SAP 系统", f"{system.name} / {system.client} / {system.environment}")
        else:
            system_item = self._timeline("system", "failed", "确认 SAP 系统", "未匹配到 SAP 系统，RFC 工具将跳过")
        timeline.append(system_item)
        await self._emit_timeline(event_sink, system_item)

        model = await self._get_streaming_model(request.model_name)
        history_messages = await self._load_context(db, session)
        tools = self._build_tools(db, system, session.id, request, timeline, tool_results, evidence, executed_plan, event_sink)
        agent = create_deep_agent(
            model=model,
            tools=tools,
            system_prompt=self._system_prompt(system),
            middleware=[_ToolExclusionMiddleware(excluded=self.EXCLUDED_DEEPAGENT_TOOLS)],
        )

        with langfuse_observability.current_observation(
            name="sap_assistant_deepagents",
            as_type="agent",
            input={"message": request.message, "session_id": session.id},
            metadata={"user_id": user_id, "sap_system": self._system_context(system), "model_name": request.model_name},
        ) as agent_obs:
            try:
                result = await agent.ainvoke(
                    {
                        "messages": [
                            *history_messages,
                            HumanMessage(
                                content=(
                                    f"用户问题：{request.message}\n"
                                    "请直接自主完成调查并输出结论，不要把中间步骤抛给用户确认。"
                                )
                            )
                        ]
                    },
                    config={"recursion_limit": self.GRAPH_RECURSION_LIMIT},
                )
            except SapAgentStop as exc:
                stop_item = self._timeline("agent_stop", "success", "停止自动追查", exc.reason)
                timeline.append(stop_item)
                await self._emit_timeline(event_sink, stop_item)
                answer = await self._compose_budget_answer(
                    request.message,
                    system,
                    tool_results,
                    evidence,
                    exc.reason,
                    event_sink,
                    model_name=request.model_name,
                )
            except Exception as exc:
                reason = str(exc)
                is_recursion_error = self._is_recursion_limit_error(exc)
                status = "skipped" if is_recursion_error else "failed"
                title = "停止自动追查" if status == "skipped" else "deepagents 执行失败"
                stop_reason = self._friendly_agent_error(exc) if is_recursion_error else reason
                error_item = self._timeline("deepagents_error", status, title, stop_reason)
                timeline.append(error_item)
                await self._emit_timeline(event_sink, error_item)
                answer = await self._compose_budget_answer(
                    request.message,
                    system,
                    tool_results,
                    evidence,
                    stop_reason,
                    event_sink,
                    model_name=request.model_name,
                )
            else:
                agent_answer = self._extract_answer(result)
                answer = await self._compose_budget_answer(
                    request.message,
                    system,
                    tool_results,
                    evidence,
                    "调查阶段已完成，进入流式总结",
                    event_sink,
                    agent_answer=agent_answer,
                    model_name=request.model_name,
                )
            agent_obs.update(
                output={"answer": answer, "tool_count": len(tool_results), "evidence_count": len(evidence)},
                metadata={"executed_plan": executed_plan, "timeline": timeline},
            )
            agent_obs.update_trace(output=answer, metadata={"tool_results": [self._compact_result_for_trace(item.model_dump()) for item in tool_results[:8]]})
        langfuse_observability.flush()

        return SapAssistantChatResponse(
            session_id=session.id or 0,
            answer=answer,
            system_context=self._system_context(system),
            timeline=timeline,
            tool_results=tool_results,
            evidence=evidence,
            flowchart=None,
        )

    def _build_tools(
        self,
        db: AsyncSession,
        system: SapSystemConfig | None,
        session_id: int | None,
        request: SapAssistantChatRequest,
        timeline: list[dict[str, Any]],
        tool_results: list[Any],
        evidence: list[SapToolEvidence],
        executed_plan: list[tuple[str, dict[str, Any]]],
        event_sink: Callable[[str, dict[str, Any]], Awaitable[None]] | None = None,
    ) -> list[StructuredTool]:
        budget_state: dict[str, Any] = {
            "tool_calls": 0,
            "seen_call_keys": set(),
        }

        async def call_sap_tool(tool_name: str, params: dict[str, Any]) -> str:
            guard_message = self._budget_guard(tool_name, params, budget_state)
            if guard_message:
                node_id = f"{tool_name}_{len(executed_plan) + 1}"
                executed_plan.append((tool_name, params))
                item = self._timeline(node_id, "skipped", f"跳过{self._tool_action_label(tool_name)}", guard_message, tool_name=tool_name)
                timeline.append(item)
                await self._emit_timeline(event_sink, item)
                raise SapAgentStop(guard_message)

            budget_state["tool_calls"] = int(budget_state.get("tool_calls") or 0) + 1
            node_id = f"{tool_name}_{len(executed_plan) + 1}"
            executed_plan.append((tool_name, params))
            pending_item = self._timeline(
                node_id,
                "pending",
                f"正在{self._tool_action_label(tool_name)}",
                self._tool_pending_detail(tool_name, params),
                tool_name=tool_name,
            )
            timeline.append(pending_item)
            await self._emit_timeline(event_sink, pending_item)
            with langfuse_observability.current_observation(
                name=f"sap_tool:{tool_name}",
                as_type="tool",
                input={"tool_name": tool_name, "params": params},
                metadata={"system": self._system_context(system)},
            ) as tool_obs:
                result = await sap_tool_service.execute(db, system, tool_name, params, session_id=session_id)
                tool_obs.update(
                    output=self._compact_result_for_trace(result.model_dump()),
                    level="ERROR" if result.status == "failed" else "DEFAULT",
                    status_message=result.error_message,
                    metadata={"duration_ms": result.duration_ms, "status": result.status},
                )
            tool_results.append(result)
            evidence.extend(result.evidence)
            done_item = self._timeline(
                node_id,
                result.status,
                f"{self._tool_action_label(tool_name)}完成",
                self._tool_done_detail(tool_name, params, result.summary, result.data),
                tool_name=tool_name,
            )
            timeline.append(done_item)
            await self._emit_timeline(event_sink, done_item)
            await self._emit(
                event_sink,
                "tool_output",
                {"toolName": self._tool_action_label(result.tool_name), "displayType": "json", "content": result.model_dump()},
            )
            for evidence_item in result.evidence:
                await self._emit(event_sink, "evidence", evidence_item.model_dump())
            return self._llm_tool_return(tool_name, result.data, result.status, result.summary, params)

        async def tcode_info(tcode: str = "", query: str = "", max_rows: int = 20) -> str:
            """查询事务码及描述，返回事务码对应程序、屏幕号和文本。"""
            return await call_sap_tool("tcode_info", {"tcode": tcode, "query": query, "max_rows": max_rows})

        async def program_source(object_name: str) -> str:
            """读取 ABAP 程序、Report 或 Include 的完整源码。"""
            return await call_sap_tool("program_source", {"object_name": object_name, "start_line": 1, "max_lines": 0})

        async def program_source_window(object_name: str, start_line: int, max_lines: int = 180) -> str:
            """按行号读取 ABAP 程序源码窗口。先用 program_source 定位 FORM/关键行，再读取目标位置的完整上下文。"""
            return await call_sap_tool("program_source", {"object_name": object_name, "start_line": start_line, "max_lines": max(20, min(max_lines, 260))})

        async def function_source(object_name: str) -> str:
            """读取 ABAP Function Module/RFC 的完整源码。"""
            return await call_sap_tool("function_source", {"object_name": object_name, "start_line": 1, "max_lines": 0})

        async def function_source_window(object_name: str, start_line: int, max_lines: int = 180) -> str:
            """按行号读取函数源码窗口。用于查看函数内部某段完整实现，不要重复读取整个函数。"""
            return await call_sap_tool("function_source", {"object_name": object_name, "start_line": start_line, "max_lines": max(20, min(max_lines, 260))})

        async def ddic_meta(object_name: str, object_type: str = "TABL") -> str:
            """查询 DDIC 表、结构、字段、数据元素和域信息。"""
            return await call_sap_tool("ddic_meta", {"object_name": object_name, "object_type": object_type})

        async def zilog_logs(object_name: str = "", keyword: str = "", max_rows: int = 60) -> str:
            """查询 ZILOG 日志。"""
            return await call_sap_tool("zilog_logs", {"object_name": object_name, "keyword": keyword, "max_rows": max_rows})

        async def safe_table_read(
            table_name: str,
            fields: list[dict[str, Any]] | None = None,
            ranges: list[dict[str, Any]] | None = None,
            max_rows: int = 80,
        ) -> str:
            """通过 SAP 侧只读 RFC 小批量读取样例数据。"""
            return await call_sap_tool("safe_table_read", {"table_name": table_name, "fields": fields or [], "ranges": ranges or [], "max_rows": max_rows})

        async def latest_table_read(
            table_name: str,
            fields: list[dict[str, Any]] | None = None,
            ranges: list[dict[str, Any]] | None = None,
            sort_fields: list[dict[str, str]] | None = None,
            max_rows: int = 1,
        ) -> str:
            """通过 SAP 侧只读 RFC 按排序字段读取最新 Top N 记录。遇到“最新、最后一笔、最近、最大凭证号”必须优先使用它。"""
            return await call_sap_tool(
                "latest_table_read",
                {
                    "table_name": table_name,
                    "fields": fields or [],
                    "ranges": ranges or [],
                    "sort_fields": sort_fields or [],
                    "max_rows": max_rows,
                },
            )

        async def knowledge_search(query: str, top_k: int = 3) -> str:
            """检索用户选择的通用知识库。"""
            if not request.knowledge_base_ids:
                return json.dumps({"hits": [], "message": "未选择知识库"}, ensure_ascii=False)
            hits: list[dict[str, Any]] = []
            for kb_id in request.knowledge_base_ids[:5]:
                result = await knowledge_base_service.search(db, kb_id, query, top_k=top_k)
                for hit in result.hits:
                    item = SapToolEvidence(
                        evidence_type="kb",
                        title=f"知识库片段：{hit.title}",
                        summary=hit.content[:160],
                        source_object=hit.title,
                        location=hit.source_label,
                        confidence=hit.score,
                        content=hit.model_dump(),
                    )
                    evidence.append(item)
                    hits.append(item.model_dump())
            knowledge_item = self._timeline("knowledge", "success", "检索知识库", f"命中 {len(hits)} 条知识片段")
            timeline.append(knowledge_item)
            await self._emit_timeline(event_sink, knowledge_item)
            for item in hits:
                await self._emit(event_sink, "evidence", item)
            return self._to_llm_tool_text({"hits": hits[:top_k]})

        async def finish_investigation(reason: str = "已找到足够证据") -> str:
            """当你认为证据已经足够回答用户问题时调用。调用后后端会进入流式总结，不要直接输出长答案。"""
            item = self._timeline("finish_investigation", "success", "进入流式总结", reason, tool_name="finish_investigation")
            timeline.append(item)
            await self._emit_timeline(event_sink, item)
            raise SapAgentStop(reason)

        return [
            StructuredTool.from_function(coroutine=tcode_info, name="tcode_info", description=tcode_info.__doc__ or ""),
            StructuredTool.from_function(coroutine=program_source, name="program_source", description=program_source.__doc__ or ""),
            StructuredTool.from_function(coroutine=program_source_window, name="program_source_window", description=program_source_window.__doc__ or ""),
            StructuredTool.from_function(coroutine=function_source, name="function_source", description=function_source.__doc__ or ""),
            StructuredTool.from_function(coroutine=function_source_window, name="function_source_window", description=function_source_window.__doc__ or ""),
            StructuredTool.from_function(coroutine=ddic_meta, name="ddic_meta", description=ddic_meta.__doc__ or ""),
            StructuredTool.from_function(coroutine=zilog_logs, name="zilog_logs", description=zilog_logs.__doc__ or ""),
            StructuredTool.from_function(coroutine=safe_table_read, name="safe_table_read", description=safe_table_read.__doc__ or ""),
            StructuredTool.from_function(coroutine=latest_table_read, name="latest_table_read", description=latest_table_read.__doc__ or ""),
            StructuredTool.from_function(coroutine=knowledge_search, name="knowledge_search", description=knowledge_search.__doc__ or ""),
            StructuredTool.from_function(coroutine=finish_investigation, name="finish_investigation", description=finish_investigation.__doc__ or ""),
        ]

    async def _load_context(self, db: AsyncSession, session: SapAssistantSession) -> list[BaseMessage]:
        history: list[BaseMessage] = []
        if session.summary:
            history.append(
                SystemMessage(
                    content=(
                        "以下是本 SAP 助手会话的持续记忆。用户追问省略主语、事务码、程序名、字段名时，"
                        "优先结合这段记忆理解上下文；如果新问题明确切换对象，再以新问题为准。\n"
                        f"{session.summary[:3000]}"
                    )
                )
            )
        if not session.id:
            return history
        result = await db.exec(
            select(SapAssistantMessage)
            .where(SapAssistantMessage.session_id == session.id)
            .order_by(SapAssistantMessage.create_time.desc())
            .limit(4)
        )
        messages = list(reversed(result.all()))
        for item in messages:
            content = item.content[:900]
            if item.role == "user":
                history.append(HumanMessage(content=content))
            elif item.role == "assistant":
                history.append(AIMessage(content=content))
        return history

    def _system_prompt(self, system: SapSystemConfig | None) -> str:
        system_ctx = self._system_context(system)
        system_label = f"{system_ctx['name']}({system_ctx['client']})" if system_ctx else "未连接"
        return (
            f"你是一个高级 SAP ECC 调查专家 Agent，正在对系统 {system_label} 进行自主诊断。\n"
            "【核心原则：自主且克制】\n"
            "1. 你的目标是构建可验证的证据链，不要仅凭记忆猜测 SAP 逻辑。\n"
            "2. 不要依赖用户指引，你必须自主调用工具完成下钻。\n"
            "3. 用户问事务码时，先用 tcode_info 定位对应程序，再围绕该程序调查；事务码名和程序名不同不是错误。\n"
            "4. 调查源码时直接读取完整程序或完整函数源码，不使用源码搜索工具；请自行在完整源码中定位字段赋值、计算、SELECT、READ TABLE、PERFORM 或关键 CALL FUNCTION。\n"
            "5. 字段取值、金额计算、字段血缘问题必须有可执行代码证据；注释、标题、DDIC 字段定义只能作为线索。\n"
            "6. 当你认为证据足够时，必须调用 finish_investigation 进入后端流式总结；不要自己直接输出长篇最终答案。\n"
            "7. 用户问“最新、最后一笔、最近、最大凭证号”时，不能用 safe_table_read 的无序样例下结论；必须使用 latest_table_read 并给出排序字段。物料凭证常用 MKPF 按 CPUDT DESC、CPUTM DESC 排序，必要时再用 MJAHR DESC、MBLNR DESC 兜底。\n"
            "【节省 Token 与效率指南】\n"
            "1. 当前试验模式要求每次读取完整源码，因此你要减少无关工具调用，优先围绕事务码对应程序和真实 CALL FUNCTION 下钻。\n"
            "2. 不要为了同一目的反复盲目试探，不要重复调用相同参数的工具。\n"
            "3. 如果某个方向没有命中，果断换表、程序、函数或关键词。\n"
            f"4. 本轮最多调用 {self.MAX_TOOL_CALLS} 次业务工具；可以围绕同一对象读取完整程序和真实函数源码，但不要重复调用完全相同参数。\n"
            "【输出格式】\n"
            "直接给出结论、证据链、完整流转链路和仍不确定的地方；如果权限、RFC 或代码缺失导致证据不足，明确指出。"
        )

    def _source_subagent_prompt(self) -> str:
        return (
            "你是 ABAP 源码调查子 Agent。你的任务是减少重复搜索，快速定位可执行证据。"
            "优先顺序：事务码对应程序 -> 读取完整程序源码 -> 查赋值/计算语句 -> 追 CALL FUNCTION -> 总结链路。"
            "如果已经找到目标字段的赋值或计算，不要继续泛搜。"
        )

    def _budget_guard(self, tool_name: str, params: dict[str, Any], budget_state: dict[str, Any]) -> str:
        call_key = json.dumps([tool_name, params], ensure_ascii=False, sort_keys=True, default=str)
        seen_call_keys = budget_state.get("seen_call_keys")
        if isinstance(seen_call_keys, set):
            if call_key in seen_call_keys:
                return "该工具调用和参数已经执行过，请基于已有结果继续总结，不要重复调用"
            seen_call_keys.add(call_key)
        if int(budget_state.get("tool_calls") or 0) >= self.MAX_TOOL_CALLS:
            return f"已达到本轮 deepagents 工具调用上限 {self.MAX_TOOL_CALLS} 次"

        return ""

    def _is_recursion_limit_error(self, exc: Exception) -> bool:
        reason = f"{type(exc).__name__}: {exc}"
        return any(token in reason for token in ("Recursion limit", "GRAPH_RECURSION_LIMIT", "GraphRecursionError"))

    def _friendly_agent_error(self, exc: Exception) -> str:
        if self._is_recursion_limit_error(exc):
            return (
                f"已达到本轮自动追查步数上限（{self.GRAPH_RECURSION_LIMIT} 步），"
                "系统已停止继续调用工具，并基于已有 SAP 证据生成阶段性结论。"
            )
        return str(exc)

    def _llm_tool_return(self, tool_name: str, data: Any, status: str, summary: str, params: dict[str, Any] | None = None) -> str:
        if status != "success":
            return self._to_llm_tool_text({"ok": False, "error": summary})
        if tool_name in {"program_source", "function_source"}:
            if params and int(params.get("max_lines") or 0) > 0:
                return self._source_payload_to_text(data)
            return self._source_payload_to_investigation_pack(data)
        compact_data = self._compact_result_data(tool_name, data)
        return self._to_llm_tool_text(compact_data)

    def _source_payload_to_investigation_pack(self, data: Any) -> str:
        parsed = self._source_parsed(data)
        lines = parsed.get("lines")
        if not isinstance(lines, list):
            return self._source_payload_to_text(data)
        object_name = parsed.get("object") or parsed.get("resolvedProgram") or ""
        start_line = int(parsed.get("startLine") or 1)
        total_lines = parsed.get("totalLines") or len(lines)
        snippets, calls, forms = self._source_evidence_snippets(lines, start_line)
        payload = {
            "object": object_name,
            "totalLines": total_lines,
            "forms": forms[:80],
            "note": "源码已完整读取并保留给前端/审计；为避免后续每轮重复消耗 token，这里只返回关键调查片段。",
            "discoveredCalls": calls[:40],
            "evidenceSnippets": snippets[:90],
        }
        text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)
        return text if len(text) <= self.MAX_SOURCE_PACK_TEXT else f"{text[:self.MAX_SOURCE_PACK_TEXT]}\n...[源码调查包过长，已截断]"

    def _source_parsed(self, data: Any) -> dict[str, Any]:
        if not isinstance(data, dict):
            return {}
        parsed = data.get("JSON_PARSED")
        return parsed if isinstance(parsed, dict) else {}

    def _is_source_window(self, data: Any) -> bool:
        parsed = self._source_parsed(data)
        if not parsed:
            return False
        try:
            returned = int(parsed.get("returnedLines") or 0)
            total = int(parsed.get("totalLines") or 0)
            start_line = int(parsed.get("startLine") or 1)
        except (TypeError, ValueError):
            return False
        return start_line > 1 or (returned > 0 and total > returned)

    def _source_evidence_snippets(self, lines: list[Any], start_line: int) -> tuple[list[dict[str, Any]], list[str], list[dict[str, Any]]]:
        calls: list[str] = []
        selected: dict[int, str] = {}
        forms: list[dict[str, Any]] = []
        open_form: dict[str, Any] | None = None
        important_tokens = (
            "PZKPJE",
            "RMBKPJE",
            "ZPR0",
            "FKIMG",
            "NETWR",
            "KONV",
            "VBRP",
            "VBRK",
            "KBETR",
            "KPEIN",
            "KURRF",
            "PEINH",
            "DMBTR",
            "WRBTR",
        )

        def add_window(index: int, radius: int = 2) -> None:
            begin = max(0, index - radius)
            end = min(len(lines), index + radius + 1)
            for offset in range(begin, end):
                selected[start_line + offset] = self._short_text(str(lines[offset]), 260)

        for index, raw_line in enumerate(lines):
            line = str(raw_line)
            upper = line.upper()
            form_match = re.search(r"^\s*FORM\s+([A-Z0-9_]+)", upper)
            if form_match:
                open_form = {"name": form_match.group(1), "startLine": start_line + index}
                forms.append(open_form)
                add_window(index, 1)
            if open_form is not None and re.search(r"^\s*ENDFORM\b", upper):
                open_form["endLine"] = start_line + index
                open_form = None
            call_match = re.search(r"CALL\s+FUNCTION\s+'?([A-Z0-9_]+)'?", upper)
            if call_match and call_match.group(1) not in calls:
                calls.append(call_match.group(1))
                add_window(index, 1)
            perform_match = re.search(r"\bPERFORM\s+([A-Z0-9_]+)", upper)
            if perform_match:
                perform_name = f"PERFORM {perform_match.group(1)}"
                if perform_name not in calls:
                    calls.append(perform_name)
                if any(token in upper for token in important_tokens):
                    add_window(index, 2)
            if any(token in upper for token in important_tokens) and self._looks_like_abap_evidence(upper):
                add_window(index, 3)
            elif self._looks_like_abap_evidence(upper) and any(word in upper for word in ("SELECT", "READ TABLE", "LOOP AT", "FORM ", "ENDFORM")):
                if len(selected) < 120:
                    add_window(index, 1)
        snippets = [{"line": line_no, "text": selected[line_no]} for line_no in sorted(selected)]
        return snippets, calls, forms

    def _looks_like_abap_evidence(self, upper_line: str) -> bool:
        tokens = (
            "SELECT",
            "READ TABLE",
            "CALL FUNCTION",
            "PERFORM",
            "LOOP AT",
            "FORM ",
            " = ",
            "=",
            "MOVE",
            "APPEND",
            "COLLECT",
            "MODIFY",
            "KONV",
            "VBRP",
        )
        return any(token in upper_line for token in tokens)

    def _source_payload_to_text(self, data: Any) -> str:
        if not isinstance(data, dict):
            return str(data)
        parsed = data.get("JSON_PARSED")
        if not isinstance(parsed, dict):
            return json.dumps(data, ensure_ascii=False, default=str)
        lines = parsed.get("lines")
        if not isinstance(lines, list):
            return json.dumps(parsed, ensure_ascii=False, default=str)
        object_name = parsed.get("object") or parsed.get("resolvedProgram") or ""
        start_line = int(parsed.get("startLine") or 1)
        total_lines = parsed.get("totalLines") or len(lines)
        numbered_lines = [f"{start_line + index}: {line}" for index, line in enumerate(lines)]
        return "\n".join(
            [
                f"对象：{object_name}",
                f"总行数：{total_lines}",
                "完整源码：",
                *numbered_lines,
            ]
        )

    def _to_llm_tool_text(self, value: Any) -> str:
        if isinstance(value, str):
            return self._short_text(value, self.MAX_TOOL_RESULT_TEXT)
        text = json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)
        if len(text) <= self.MAX_TOOL_RESULT_TEXT:
            return text
        fallback = {
            "truncated": True,
            "message": "工具结果过长，已在数据层级压缩；请缩小搜索范围或读取更小源码片段。",
            "preview": self._short_text(text, min(900, self.MAX_TOOL_RESULT_TEXT // 2)),
        }
        return json.dumps(fallback, ensure_ascii=False, separators=(",", ":"))

    def _short_text(self, text: str, max_len: int) -> str:
        if len(text) <= max_len:
            return text
        return f"{text[:max_len]}\n...[内容过长，已在安全边界处截断]"

    def _compact_result_for_trace(self, value: Any) -> Any:
        return self._compact_result_data("trace", value)

    def _compact_result_data(self, tool_name: str, data: Any) -> Any:
        if isinstance(data, list):
            compacted = [self._compact_result_data(tool_name, item) for item in data[:20]]
            if len(data) > 20:
                compacted.append({"truncated": True, "omittedCount": len(data) - 20})
            return compacted
        if not isinstance(data, dict):
            return self._short_text(data, 600) if isinstance(data, str) else data
        if tool_name in {"source_search", "source"}:
            matches = data.get("matches")
            compact_matches = []
            if isinstance(matches, list):
                for item in matches[:8]:
                    if not isinstance(item, dict):
                        continue
                    context = item.get("context")
                    compact_matches.append(
                        {
                            **{key: value for key, value in item.items() if key != "context"},
                    "context": [self._short_text(str(line), 220) for line in context[:6]] if isinstance(context, list) else [],
                        }
                    )
            calls = data.get("discoveredFunctionCalls")
            return {
                **{key: value for key, value in data.items() if key not in {"matches", "discoveredFunctionCalls"}},
                "discoveredFunctionCalls": calls[:20] if isinstance(calls, list) else calls,
                "matches": compact_matches,
                "compactNote": "已裁剪源码搜索上下文，避免单轮对话 token 过大。",
            }
        parsed = data.get("JSON_PARSED")
        if isinstance(parsed, dict) and isinstance(parsed.get("lines"), list):
            lines = parsed.get("lines") or []
            return {
                **{key: value for key, value in data.items() if key != "JSON_PARSED"},
                "JSON_PARSED": {
                    **{key: value for key, value in parsed.items() if key != "lines"},
                    "linePreview": [self._short_text(str(line), 220) for line in lines[:60]],
                    "linePreviewCount": min(len(lines), 60),
                    "compactNote": "完整源码已用于工具侧检索；返回模型时只保留前 60 行预览。",
                },
            }
        compacted: dict[str, Any] = {}
        for key, value in data.items():
            if key in {"ET_JSON_LINES", "JSON_TEXT"}:
                continue
            compacted[key] = self._compact_result_data(tool_name, value)
        return compacted

    async def _compose_budget_answer(
        self,
        message: str,
        system: SapSystemConfig | None,
        tool_results: list[Any],
        evidence: list[SapToolEvidence],
        stop_reason: str,
        event_sink: Callable[[str, dict[str, Any]], Awaitable[None]] | None = None,
        agent_answer: str | None = None,
        model_name: str | None = None,
    ) -> str:
        if not tool_results and not evidence:
            return (
                f"本轮 SAP 助手未能完成自动调查：{stop_reason}\n\n"
                "当前还没有可用工具证据，因此不能下确定结论。请检查 SAP 系统配置、RFC 可用性和问题中的事务码/对象名后重试。"
            )
        answer_item = self._timeline("answer", "pending", "生成最终回答", "正在基于已获取的 SAP 证据流式生成总结。")
        await self._emit_timeline(event_sink, answer_item)
        prompt = (
            "你是 SAP 助手。调查阶段已经结束，请不要再规划或调用工具，"
            "只基于已给出的工具结果和证据生成中文回答。回答包含：结论、证据链、完整流转链路、仍不确定的地方。"
            "如果证据不足，必须明确说证据不足，不能把注释或字段定义当作确定业务逻辑。"
        )
        context_text = self._summary_context_text(message, system, tool_results, evidence, stop_reason, agent_answer)
        try:
            model = await self._get_streaming_model(model_name)
            chunks: list[str] = []
            async for chunk in model.astream(
                [SystemMessage(content=prompt), HumanMessage(content=context_text)]
            ):
                text = self._message_content_to_text(getattr(chunk, "content", ""))
                if not text:
                    continue
                chunks.append(text)
                await self._emit(event_sink, "text_delta", {"content": text})
            answer = "".join(chunks).strip()
            done_item = self._timeline("answer", "success", "最终回答完成", "SAP 助手已完成流式总结。")
            await self._emit_timeline(event_sink, done_item)
            return answer or "已完成调查，但模型未返回有效总结。"
        except Exception:
            lines = [
                "本轮 SAP 助手已停止自动追查，并基于已有证据给出阶段性结果。",
                "",
                f"停止原因：{stop_reason}",
                "",
                "证据链：",
            ]
            for item in evidence[:8]:
                lines.append(f"- {item.title}：{item.summary or '已返回结构化结果'}")
            if not evidence:
                lines.append("- 暂无可用证据。")
            lines.extend(["", "仍不确定的地方：如需确定字段取值、金额计算或血缘关系，需要继续取得可执行源码、DDIC、日志或只读样例数据。"])
            answer = "\n".join(lines)
            await self._emit(event_sink, "text_delta", {"content": answer})
            return answer

    def _summary_context_text(
        self,
        message: str,
        system: SapSystemConfig | None,
        tool_results: list[Any],
        evidence: list[SapToolEvidence],
        stop_reason: str,
        agent_answer: str | None = None,
    ) -> str:
        sections = [
            f"用户问题：{message}",
            f"SAP 系统：{json.dumps(self._system_context(system), ensure_ascii=False, default=str)}",
            f"调查停止原因：{stop_reason}",
        ]
        if agent_answer:
            sections.append(f"调查 Agent 阶段性判断：\n{agent_answer[:3000]}")
        sections.append("工具结果：")
        for index, item in enumerate(tool_results[:8], start=1):
            sections.append(f"\n[{index}] {self._tool_action_label(item.tool_name)} / 状态：{item.status}\n摘要：{item.summary}")
            if item.tool_name in {"program_source", "function_source"}:
                if self._is_source_window(item.data):
                    sections.append(self._source_payload_to_text(item.data))
                else:
                    sections.append(self._source_payload_to_investigation_pack(item.data))
            else:
                sections.append(self._to_llm_tool_text(self._compact_result_data(item.tool_name, item.data)))
        if evidence:
            sections.append("\n证据摘要：")
            for item in evidence[:10]:
                sections.append(
                    f"- {item.title}：{item.summary or '已返回结构化结果'}；来源：{item.source_object or '-'}；位置：{item.location or '-'}"
                )
        return "\n\n".join(sections)

    def _extract_answer(self, result: Any) -> str:
        if isinstance(result, dict):
            messages = result.get("messages")
            if isinstance(messages, list):
                for message in reversed(messages):
                    if isinstance(message, AIMessage):
                        return self._message_content_to_text(message.content)
                    if isinstance(message, BaseMessage) and getattr(message, "type", "") == "ai":
                        return self._message_content_to_text(message.content)
                    if isinstance(message, dict) and message.get("role") == "assistant":
                        return self._message_content_to_text(message.get("content"))
            if "output" in result:
                return self._message_content_to_text(result["output"])
        return self._message_content_to_text(result)

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
        return str(content)

    async def _emit_timeline(
        self,
        event_sink: Callable[[str, dict[str, Any]], Awaitable[None]] | None,
        item: dict[str, Any],
    ) -> None:
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

    async def _emit(
        self,
        event_sink: Callable[[str, dict[str, Any]], Awaitable[None]] | None,
        event_type: str,
        data: dict[str, Any],
    ) -> None:
        if event_sink:
            await event_sink(event_type, data)

    def _compact_text(self, value: Any, max_len: int) -> str:
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
        return text if len(text) <= max_len else f"{text[:max_len]}...<已截断>"

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
            tcode = params.get("tcode") or params.get("query") or "用户问题中的事务码"
            return f"正在定位事务码 {tcode} 对应的程序、屏幕号和描述。"
        if tool_name == "program_source":
            object_name = params.get("object_name") or "未知程序"
            return f"正在读取 ABAP 程序 {object_name} 的完整源码，准备分析字段赋值、取数和函数调用。"
        if tool_name == "function_source":
            object_name = params.get("object_name") or "未知函数"
            return f"正在读取函数 {object_name} 的完整源码，准备追踪内部取数、计算和返回值。"
        if tool_name == "ddic_meta":
            object_name = params.get("object_name") or "未知对象"
            return f"正在查询 {object_name} 的 DDIC 字段、数据元素和域定义。"
        if tool_name == "zilog_logs":
            keyword = params.get("keyword") or params.get("object_name") or "相关对象"
            return f"正在按 {keyword} 查询 ZILOG 日志，辅助确认运行时证据。"
        if tool_name == "safe_table_read":
            table_name = params.get("table_name") or "未知表"
            return f"正在通过受控只读 RFC 读取 {table_name} 的少量样例数据。"
        if tool_name == "latest_table_read":
            table_name = params.get("table_name") or "未知表"
            sort_fields = params.get("sort_fields") or []
            return f"正在按排序字段读取 {table_name} 的最新记录：{self._compact_text(sort_fields, 220)}。"
        return f"参数：{self._compact_text(params, 360)}"

    def _tool_done_detail(self, tool_name: str, params: dict[str, Any], summary: str, data: Any) -> str:
        if tool_name in {"program_source", "function_source"}:
            object_name = params.get("object_name") or "源码对象"
            total_lines = self._source_total_lines(data)
            if total_lines:
                return f"已读取 {object_name} 的完整源码，共 {total_lines} 行；AI 将继续在源码中定位可执行证据。"
            return f"已读取 {object_name} 的源码；AI 将继续分析其中的取数、赋值和函数调用。"
        if tool_name == "tcode_info":
            programs = self._programs_from_tcode_data(data)
            if programs:
                return f"已定位事务码对应程序：{', '.join(programs[:5])}。"
        if tool_name == "latest_table_read":
            table_name = params.get("table_name") or "目标表"
            return f"已按指定排序读取 {table_name} 的最新记录，可用于回答“最新/最后一笔”类问题。"
        return summary or f"{self._tool_action_label(tool_name)}完成。"

    def _source_total_lines(self, data: Any) -> int | None:
        if not isinstance(data, dict):
            return None
        parsed = data.get("JSON_PARSED")
        if not isinstance(parsed, dict):
            return None
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

    def _timeline(self, node_id: str, status: str, title: str, detail: str, tool_name: str | None = None) -> dict[str, Any]:
        return {"id": node_id, "status": status, "title": title, "detail": detail, "toolName": tool_name or node_id}


sap_deep_agent_service = SapDeepAgentService()
