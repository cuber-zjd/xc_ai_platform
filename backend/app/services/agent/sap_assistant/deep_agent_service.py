import json
import re
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError
from langchain.agents import create_agent
from langchain_anthropic.middleware import AnthropicPromptCachingMiddleware
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.tools import StructuredTool
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.llm_factory import LLMFactory
from app.core.langfuse_observability import langfuse_observability
from app.db.session import async_session
from app.models.agent.sap_assistant import SapAssistantMessage, SapAssistantSession, SapSystemConfig
from app.schemas.agent.sap_assistant import SapAssistantChatRequest, SapAssistantChatResponse, SapToolEvidence
from app.services.agent.sap_assistant.tool_service import sap_tool_service
from app.services.knowledge_base_service import knowledge_base_service
from deepagents.backends import StateBackend
from deepagents.middleware.patch_tool_calls import PatchToolCallsMiddleware
from deepagents.middleware.summarization import create_summarization_middleware


class SafeTableReadArgs(BaseModel):
    table_name: str = Field(description="SAP 表名，例如 VBRP、VBRK。")
    fields: list[str | dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "要返回的字段，支持字符串数组或对象数组。"
            "推荐形如 ['VBELN','POSNR']，也兼容 [{'fieldname':'VBELN'}]。"
        ),
    )
    ranges: list[dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "查询条件，支持 field/fieldname/FIELDNAME 与 value/low/LOW。"
            "例如 [{'field':'VBELN','sign':'I','option':'EQ','value':'2200590236'}]。"
        ),
    )
    max_rows: int = Field(default=5, ge=1, le=10, description="最大返回行数，建议 1-5，最多 10。")


class SapAgentStop(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


SAP_DEEP_AGENT_BASE_PROMPT = """你是一个 SAP 专用深度调查 Agent。你必须像 DeepAgent 一样通过“观察 -> 行动 -> 再观察”的循环推进，而不是一次性给出大段静态计划。

## 行为要求

- 先形成简短调查计划，但计划只是工作草稿；真正推进必须依赖工具观察。
- 每拿到一个工具结果，都要重新判断：证据是否足够、下一步是否应该查 DDIC、查源码、追函数、读取受控只读样例数据或总结。
- 对业务数据查询（例如客户、物料、订单、交货、发票、库存、采购在某月/某日的情况），优先识别相关表、字段、日期范围、内部格式和筛选条件，查 DDIC 后小批量读取数据；除非用户明确问事务码、程序、接口、字段来源、为什么查不到或计算逻辑，否则不要先查事务码或源码。
- 对需要看源码再查数据的问题，按“定位对象或接口 -> 读取源码包 -> 追真实 CALL FUNCTION/PERFORM -> 查 DDIC 或只读样例数据补证 -> 总结”的循环推进；只有用户给出事务码或问题显然围绕事务码时，才把 tcode_info 作为入口。
- 不要把后续步骤交给用户确认；除非系统/RFC/权限确实不可用，否则继续自主调用工具。
- 不要调用不存在的工具；你只能使用当前工具列表中的 SAP 业务工具。
- 如果某条路径没有证据，明确放弃该路径并切换到下一个最有价值的工具。
- program_source/function_source 默认返回“问题相关源码包”，完整源码已写入工具结果和审计；只有源码包不足以解释关键逻辑时，才调用 source_full_text 获取全文。
- 当证据足够时调用 finish_investigation；如果证据不足但预算接近上限，先调用 compact_investigation_state，再决定继续一个最关键工具或总结不确定性。
"""


class SapDeepAgentService:
    MAX_TOOL_RESULT_TEXT = 2200
    MAX_SOURCE_PACK_TEXT = 22000
    MAX_TOOL_CALLS = 12
    GRAPH_RECURSION_LIMIT = 60
    SAP_AGENT_TOOL_NAMES = frozenset(
        {
            "tcode_info",
            "program_source",
            "function_source",
            "source_full_text",
            "ddic_meta",
            "safe_table_read",
            "knowledge_search",
            "compact_investigation_state",
            "finish_investigation",
        }
    )

    async def _get_streaming_model(self, model_name: str | None = None, enable_reasoning: bool = False) -> Any:
        if model_name:
            return await LLMFactory.get_model_by_name(
                model_name,
                streaming=True,
                enable_reasoning=enable_reasoning,
                enable_langfuse_callbacks=False,
            )
        return await LLMFactory.get_model(
            capability="complex-reasoning",
            streaming=True,
            enable_reasoning=enable_reasoning,
            enable_langfuse_callbacks=False,
        )

    def _create_sap_deep_agent(
        self,
        model: Any,
        tools: list[StructuredTool],
        system: SapSystemConfig | None,
    ) -> Any:
        """按 deepagents 源码思路组装 SAP 专用 Agent，但不注入默认工具。"""
        backend = StateBackend()
        middleware = [
            create_summarization_middleware(model, backend),
            PatchToolCallsMiddleware(),
            AnthropicPromptCachingMiddleware(unsupported_model_behavior="ignore"),
        ]
        return create_agent(
            model=model,
            tools=tools,
            system_prompt=f"{self._system_prompt(system)}\n\n{SAP_DEEP_AGENT_BASE_PROMPT}",
            middleware=middleware,
            name="sap_assistant_deep_without_builtin_tools",
        )

    def _trace_context_from_observation(self, observation: Any) -> dict[str, str] | None:
        trace_id = getattr(observation, "trace_id", None)
        if not trace_id:
            return None
        trace_context = {"trace_id": str(trace_id)}
        observation_id = getattr(observation, "id", None)
        if observation_id:
            trace_context["parent_span_id"] = str(observation_id)
        return trace_context

    def _langchain_trace_config(
        self,
        callbacks: list[Any],
        *,
        session: SapAssistantSession,
        user_id: int | None,
        model_name: str | None,
    ) -> dict[str, Any]:
        metadata: dict[str, Any] = {
            "langfuse_session_id": f"sap-session-{session.id or 0}",
            "sap_session_id": session.id,
            "sap_model_name": model_name,
        }
        if user_id is not None:
            metadata["langfuse_user_id"] = str(user_id)
        return {
            "callbacks": callbacks,
            "tags": ["sap-assistant", "sap-deep-agent"],
            "metadata": metadata,
        }

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

        intent_item = self._timeline("intent", "success", "开始分析", "正在判断这是数据查询、源码逻辑排查还是混合问题，并选择最合适的 SAP 工具。")
        timeline.append(intent_item)
        await self._emit_timeline(event_sink, intent_item)
        if system:
            system_item = self._timeline("system", "success", "确认 SAP 系统", f"{system.name} / {system.client} / {system.environment}")
        else:
            system_item = self._timeline("system", "failed", "确认 SAP 系统", "未匹配到 SAP 系统，RFC 工具将跳过")
        timeline.append(system_item)
        await self._emit_timeline(event_sink, system_item)

        model = await self._get_streaming_model(request.model_name, enable_reasoning=request.enable_reasoning)
        history_messages = await self._load_context(db, session)

        with langfuse_observability.current_observation(
            name="sap_assistant_custom_tools_agent",
            as_type="agent",
            input={"message": request.message, "session_id": session.id},
            metadata={
                "user_id": user_id,
                "sap_system": self._system_context(system),
                "model_name": request.model_name,
                "enable_reasoning": request.enable_reasoning,
                "disabled_deepagents_default_tools": True,
                "sap_deep_middleware": ["SummarizationMiddleware", "PatchToolCallsMiddleware", "AnthropicPromptCachingMiddleware"],
            },
        ) as agent_obs:
            trace_context = self._trace_context_from_observation(agent_obs)
            callbacks = LLMFactory.create_langfuse_callbacks_for_trace(trace_context)
            langchain_config = self._langchain_trace_config(
                callbacks,
                session=session,
                user_id=user_id,
                model_name=request.model_name,
            )
            tools = self._build_tools(
                db,
                system,
                session.id,
                request,
                timeline,
                tool_results,
                evidence,
                executed_plan,
                event_sink,
                langfuse_trace_context=trace_context,
            )
            self._assert_only_sap_tools(tools)
            agent_obs.update(metadata={"tool_names": [tool.name for tool in tools]})
            agent = self._create_sap_deep_agent(model, tools, system)
            try:
                result = await agent.ainvoke(
                    {
                        "messages": [
                            *history_messages,
                            HumanMessage(
                                content=(
                                    f"用户问题：{request.message}\n"
                                    f"{self._user_question_hint(request.message)}\n"
                                    "请按观察-行动循环自主调查：先用最关键工具取得证据，"
                                    "每轮工具结果后再决定下一步；不要只输出静态计划，也不要把中间步骤抛给用户确认。"
                                )
                            )
                        ]
                    },
                    config={**langchain_config, "recursion_limit": self.GRAPH_RECURSION_LIMIT},
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
                    enable_reasoning=request.enable_reasoning,
                    langchain_config=langchain_config,
                )
            except Exception as exc:
                is_recursion_error = self._is_recursion_limit_error(exc)
                status = "skipped" if is_recursion_error else "failed"
                title = "停止自动追查" if status == "skipped" else "SAP 工具 Agent 执行失败"
                stop_reason = self._friendly_agent_error(exc) if is_recursion_error else self._friendly_agent_error(exc)
                error_item = self._timeline("sap_agent_error", status, title, stop_reason)
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
                    enable_reasoning=request.enable_reasoning,
                    langchain_config=langchain_config,
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
                    enable_reasoning=request.enable_reasoning,
                    langchain_config=langchain_config,
                )
            agent_obs.update(
                output={"answer": answer, "tool_count": len(tool_results), "evidence_count": len(evidence)},
                metadata={"executed_plan": executed_plan, "timeline": timeline},
            )
            agent_obs.update_trace(output=answer, metadata={"tool_results": [self._compact_result_for_trace(item.model_dump()) for item in tool_results[:8]]})
        langfuse_observability.flush()

        public_timeline = [self._public_timeline_item(item) for item in timeline]
        return SapAssistantChatResponse(
            session_id=session.id or 0,
            answer=answer,
            system_context=self._system_context(system),
            timeline=public_timeline,
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
        langfuse_trace_context: dict[str, str] | None = None,
    ) -> list[StructuredTool]:
        budget_state: dict[str, Any] = {
            "tool_calls": 0,
            "seen_call_keys": set(),
            "tool_result_cache": {},
            "evidence_ledger": [],
            "source_objects": {},
        }

        async def call_sap_tool(tool_name: str, params: dict[str, Any]) -> str:
            cached_result = self._cached_tool_result(tool_name, params, budget_state)
            if cached_result is not None:
                return self._llm_tool_return(
                    tool_name,
                    cached_result.data,
                    cached_result.status,
                    cached_result.summary,
                    params,
                    request.message,
                )

            guard_message = self._budget_guard(tool_name, params, budget_state)
            if guard_message:
                node_id = f"{tool_name}_{len(executed_plan) + 1}"
                executed_plan.append((tool_name, params))
                item = self._timeline(
                    node_id,
                    "skipped",
                    f"调整{self._tool_action_label(tool_name)}",
                    self._user_friendly_tool_detail(tool_name, params, "skipped", guard_message, None),
                    tool_name=tool_name,
                    debug_detail=guard_message,
                )
                timeline.append(item)
                await self._emit_timeline(event_sink, item)
                return self._compact_investigation_state(
                    request.message,
                    tool_results,
                    evidence,
                    executed_plan,
                    budget_state,
                    guard_message,
                )

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
                trace_context=langfuse_trace_context,
            ) as tool_obs:
                try:
                    async with async_session() as tool_db:
                        result = await sap_tool_service.execute(tool_db, system, tool_name, params, session_id=session_id)
                except Exception as exc:
                    friendly_error = self._friendly_tool_exception(tool_name, exc)
                    tool_obs.update(
                        output={"error": self._short_text(str(exc), 1200), "friendlyError": friendly_error},
                        level="ERROR",
                        status_message=friendly_error,
                        metadata={"status": "exception", "tool_name": tool_name},
                    )
                    failed_item = self._timeline(
                        node_id,
                        "failed",
                        f"{self._tool_action_label(tool_name)}未完成",
                        friendly_error,
                        tool_name=tool_name,
                        debug_detail=str(exc),
                    )
                    timeline.append(failed_item)
                    await self._emit_timeline(event_sink, failed_item)
                    raise
                else:
                    tool_obs.update(
                        output=self._compact_result_for_trace(result.model_dump()),
                        level="ERROR" if result.status == "failed" else "DEFAULT",
                        status_message=result.error_message,
                        metadata={"duration_ms": result.duration_ms, "status": result.status},
                    )
            tool_results.append(result)
            self._cache_tool_result(tool_name, params, result, budget_state)
            evidence.extend(result.evidence)
            self._record_investigation_evidence(result, budget_state)
            done_item = self._timeline(
                node_id,
                result.status,
                f"{self._tool_action_label(tool_name)}完成",
                self._user_friendly_tool_detail(tool_name, params, result.status, result.summary, result.data),
                tool_name=tool_name,
                debug_detail=self._tool_done_detail(tool_name, params, result.summary, result.data),
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
            return self._llm_tool_return(tool_name, result.data, result.status, result.summary, params, request.message)

        async def tcode_info(tcode: str = "", query: str = "", max_rows: int = 20) -> str:
            """查询事务码及描述，返回事务码对应程序、屏幕号和文本。仅当用户明确给出事务码或询问事务码入口时使用；普通客户/物料/发货/订单数据查询不要先调用。"""
            return await call_sap_tool("tcode_info", {"tcode": tcode, "query": query, "max_rows": max_rows})

        async def program_source(object_name: str) -> str:
            """读取 ABAP 程序、Report 或 Include 的完整源码；默认只向 AI 返回与用户问题相关的源码包，全文写入审计。"""
            return await call_sap_tool("program_source", {"object_name": object_name, "start_line": 1, "max_lines": 0})

        async def function_source(object_name: str) -> str:
            """读取 ABAP Function Module/RFC 的完整源码；默认只向 AI 返回与用户问题相关的源码包，全文写入审计。"""
            return await call_sap_tool("function_source", {"object_name": object_name, "start_line": 1, "max_lines": 0})

        async def source_full_text(object_name: str, object_type: str = "FUNC", reason: str = "") -> str:
            """仅当源码包没有给出关键 SELECT/WHERE/赋值/分支且 compact 后仍不足时读取全文；需说明缺失的具体证据。"""
            normalized_type = self._normalize_source_object_type(object_type)
            tool_name = "function_source" if normalized_type == "FUNC" else "program_source"
            return await call_sap_tool(
                tool_name,
                {
                    "object_name": object_name,
                    "start_line": 1,
                    "max_lines": 0,
                    "_return_full_source": True,
                    "_full_source_reason": reason,
                },
            )

        async def ddic_meta(object_name: str, object_type: str = "TABL") -> str:
            """查询 DDIC 表、结构、字段、数据元素和域信息。用于确认字段长度、日期字段、conversion exit 和后续 safe_table_read 的必要字段。"""
            return await call_sap_tool("ddic_meta", {"object_name": object_name, "object_type": object_type})

        async def safe_table_read(
            table_name: str,
            fields: list[str | dict[str, Any]] | None = None,
            ranges: list[dict[str, Any]] | None = None,
            max_rows: int = 5,
        ) -> str:
            """通过 SAP 侧只读 RFC 小批量读取数据。fields 可传字符串数组如 ["VBELN","POSNR"] 或对象数组；ranges 可用 field/value 或 fieldname/low。必须少字段、强条件。"""
            return await call_sap_tool("safe_table_read", {"table_name": table_name, "fields": fields or [], "ranges": ranges or [], "max_rows": max_rows})

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

        async def compact_investigation_state(reason: str = "需要压缩当前调查状态") -> str:
            """压缩当前调查状态、证据账本和剩余预算。预算紧张或需要拆分子任务时先调用它。"""
            item = self._timeline("compact_investigation_state", "success", "压缩调查状态", reason, tool_name="compact_investigation_state")
            timeline.append(item)
            await self._emit_timeline(event_sink, item)
            return self._compact_investigation_state(
                request.message,
                tool_results,
                evidence,
                executed_plan,
                budget_state,
                reason,
            )

        async def finish_investigation(reason: str = "已找到足够证据") -> str:
            """当你认为证据已经足够回答用户问题时调用。调用后后端会进入流式总结，不要直接输出长答案。"""
            item = self._timeline("finish_investigation", "success", "进入流式总结", reason, tool_name="finish_investigation")
            timeline.append(item)
            await self._emit_timeline(event_sink, item)
            raise SapAgentStop(reason)

        return [
            StructuredTool.from_function(coroutine=tcode_info, name="tcode_info", description=tcode_info.__doc__ or ""),
            StructuredTool.from_function(coroutine=program_source, name="program_source", description=program_source.__doc__ or ""),
            StructuredTool.from_function(coroutine=function_source, name="function_source", description=function_source.__doc__ or ""),
            StructuredTool.from_function(coroutine=source_full_text, name="source_full_text", description=source_full_text.__doc__ or ""),
            StructuredTool.from_function(coroutine=ddic_meta, name="ddic_meta", description=ddic_meta.__doc__ or ""),
            StructuredTool.from_function(
                coroutine=safe_table_read,
                name="safe_table_read",
                description=safe_table_read.__doc__ or "",
                args_schema=SafeTableReadArgs,
            ),
            StructuredTool.from_function(coroutine=knowledge_search, name="knowledge_search", description=knowledge_search.__doc__ or ""),
            StructuredTool.from_function(coroutine=compact_investigation_state, name="compact_investigation_state", description=compact_investigation_state.__doc__ or ""),
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
        now = datetime.now(ZoneInfo("Asia/Shanghai"))
        today = now.strftime("%Y-%m-%d")
        current_year = now.strftime("%Y")
        current_month = now.strftime("%Y-%m")
        return (
            f"你是一个高级 SAP ECC 调查专家 Agent，正在对系统 {system_label} 进行自主诊断。\n"
            f"【当前时间】当前日期是 {today}（Asia/Shanghai）。用户说“今年”就是 {current_year} 年；"
            f"用户说“本月”就是 {current_month}；用户只说“5月/5月份”且上下文没有年份时，默认按当前年份 {current_year} 年 5 月处理。"
            "SAP 日期字段通常使用 YYYYMMDD 内部格式，例如 2026 年 5 月为 20260501 到 20260531。\n"
            "【工作方式：计划驱动、证据优先、预算感知】\n"
            "1. 开始先在心中形成简短调查计划：核心问题、关键对象、必须证据、可选证据、停止条件；每轮工具后动态调整计划。\n"
            "2. 你的目标是构建可验证证据链，不要仅凭记忆、命名、注释或 DDIC 字段定义猜测 SAP 逻辑。\n"
            "3. 先判断意图，不要套固定流程：业务数据查询优先查表结构和只读数据；源码/接口/字段血缘/计算逻辑问题才优先查源码；只有用户给出事务码或明确问事务码对应程序时，才先用 tcode_info。\n"
            "4. 业务数据查询常见入口：客户销售/订单用 VBAK/VBAP，交货/发货用 LIKP/LIPS，开票用 VBRK/VBRP，客户主数据 KNA1/KNB1/KNVV，物料 MARA/MARC/MARD，库存/移动 MKPF/MSEG，采购 EKKO/EKPO，供应商 LFA1/LFB1。先用 DDIC 校验字段，再用 safe_table_read 小批量读取。\n"
            "5. SAP 内部格式很重要，调用工具前要把用户输入转换为内部格式，尤其是 BAPI/RFC/表查询的前导零：客户 KUNNR=10 位、供应商 LIFNR=10 位、物料 MATNR 在 ECC 通常 18 位、销售/交货/开票凭证 VBELN=10 位、会计凭证 BELNR=10 位、采购订单 EBELN=10 位、行项目 POSNR=6 位、生产/内部订单 AUFNR=12 位、成本中心 KOSTL=10 位、总账科目 SAKNR/HKONT=10 位、利润中心 PRCTR=10 位、固定资产主号 ANLN1=12 位/次号 ANLN2=4 位。公司代码 BUKRS、工厂 WERKS、年度 GJAHR 通常不补到 10 位；不确定长度时先查 DDIC 的 datatype/leng/conversionExit。\n"
            "6. 日期/月度条件要转成 SAP 内部日期范围：例如 2026 年 5 月发货，优先用 WADAT_IST/LFDAT/ERDAT 等经 DDIC 或业务语义确认的日期字段，范围为 20260501-20260531；不要把训练语料里的旧年份当当前年份。\n"
            "7. 源码调查先用 program_source/function_source 读取对象；系统会完整拉取源码并写入审计，但默认只返回与用户问题相关的源码包，包括关键 SELECT/WHERE、赋值、PERFORM、CALL FUNCTION 和相邻上下文。\n"
            "8. 如果源码包足以定位表、字段或过滤条件，下一步优先查 DDIC 或 safe_table_read 对照数据；safe_table_read 必须少字段、少行、强条件：fields 显式给 1-8 个必要字段，max_rows 默认 5，必须带主键/凭证号/公司/日期等高选择性 ranges，不要空 fields 或无条件读表。\n"
            "9. 可以沿真实 CALL FUNCTION 递归读取被调用函数的源码包，但不要重复读取完全相同对象；如果某个方向无关，果断换函数、查 DDIC、只读数据或总结不确定性。\n"
            "10. 字段取值、金额计算、字段血缘问题必须有可执行代码证据，例如 SELECT、LOOP、READ TABLE、CALL FUNCTION、PERFORM、赋值或计算语句；注释、标题、DDIC 只能作为弱证据。单纯业务数据查询不强制要求源码证据。\n"
            "11. 每轮观察后维护证据链：强证据、弱证据、缺口和不确定性。证据足够时必须调用 finish_investigation 进入后端流式总结，不要继续泛搜。\n"
            "【工具调用 mini-shot】\n"
            "例1：用户问“客户115863 5月份发货情况”。先 ddic_meta(LIKP) 和 ddic_meta(LIPS)；确认客户字段后再 safe_table_read(table_name='LIKP', fields=['VBELN','KUNNR','WADAT_IST'], ranges=[{'field':'KUNNR','option':'EQ','value':'0000115863'},{'field':'WADAT_IST','option':'BT','low':'20260501','high':'20260531'}], max_rows=5)。不要先查事务码。\n"
            "例2：用户给出 VBELN=2200590236 查开票行。先确认 VBRK/VBRP 字段；再 safe_table_read(table_name='VBRP', fields=['VBELN','POSNR','AUBEL'], ranges=[{'field':'VBELN','option':'EQ','value':'2200590236'}], max_rows=5)。如果 DDIC 显示 VBELN 长度为10，就不要补成12位。\n"
            "例3：用户问接口/函数为什么查不到。先 function_source(函数名) 找可执行 SELECT/WHERE；如果源码显示涉及 VBRK-RFBSK、VBAK-AUART、VBRK-ERDAT/AEDAT，再用 ddic_meta 和 safe_table_read 针对这些字段做最小验证。\n"
            "【预算与递归策略】\n"
            f"1. 本轮最多调用 {self.MAX_TOOL_CALLS} 次业务工具。预算紧张、方向发散或需要拆分子任务时，先调用 compact_investigation_state 查看证据账本和剩余预算。\n"
            "2. 如果核心证据仍不足，只选择一个最高价值的后续动作；如果剩余步骤只是知识库等可选补强，可以跳过并在最终总结中标注不确定性。\n"
            "3. 达到限制时不要中止式回答；基于压缩状态决定继续读取一个最关键源码包、必要时请求 source_full_text、追真实函数调用、或调用 finish_investigation 输出阶段性结论。\n"
            "【最终回答要求】\n"
            "通过 finish_investigation 结束调查后，最终总结由模型按用户问题自然组织，不要套固定小标题或固定段落；但必须忠于工具证据，证据不足时要明确说明不能确定。"
        )

    def _user_question_hint(self, message: str) -> str:
        now = datetime.now(ZoneInfo("Asia/Shanghai"))
        hints: list[str] = [f"当前日期提示：今天是 {now:%Y-%m-%d}，相对日期请按这个日期解释。"]
        text = message.strip()
        if self._looks_like_business_data_query(text) and not self._mentions_code_or_tcode(text):
            hints.append(
                "意图提示：这个问题更像业务数据查询，优先查 DDIC 和只读业务表；不要因为流程习惯先查事务码或源码。"
            )
        customer = self._extract_number_after_keywords(text, ("客户", "客户号", "客户编码", "KUNNR"))
        if customer:
            hints.append(f"格式提示：客户号 {customer} 查询 SAP 表/BAPI 前通常应转为 KUNNR 10 位内部格式 {customer.zfill(10)}。")
        vendor = self._extract_number_after_keywords(text, ("供应商", "供应商号", "供应商编码", "LIFNR"))
        if vendor:
            hints.append(f"格式提示：供应商号 {vendor} 查询 SAP 表/BAPI 前通常应转为 LIFNR 10 位内部格式 {vendor.zfill(10)}。")
        material = self._extract_number_after_keywords(text, ("物料", "物料号", "物料编码", "MATNR"))
        if material:
            hints.append(f"格式提示：物料号 {material} 在 ECC 查询前通常应转为 MATNR 18 位内部格式 {material.zfill(18)}。")
        if re.search(r"(今年|本年)", text):
            hints.append(f"时间提示：用户说今年/本年，默认是 {now:%Y} 年。")
        month_match = re.search(r"(?<!\d)(1[0-2]|0?[1-9])\s*月(?:份)?", text)
        if month_match and not re.search(r"\d{4}\s*年", text):
            month = int(month_match.group(1))
            hints.append(f"时间提示：用户只说 {month} 月且没有年份，默认按 {now:%Y} 年 {month} 月处理。")
        return "辅助提示：" + " ".join(hints)

    def _looks_like_business_data_query(self, message: str) -> bool:
        return bool(
            re.search(
                r"(客户|物料|供应商|发货|交货|开票|发票|订单|销售|采购|库存|凭证|公司|月份|本月|今年|情况|明细|数量|金额)",
                message,
                flags=re.IGNORECASE,
            )
        )

    def _mentions_code_or_tcode(self, message: str) -> bool:
        return bool(
            re.search(
                r"(事务码|tcode|程序|源码|代码|函数|接口|RFC|BAPI|字段血缘|取值逻辑|计算逻辑|为什么|查不到|报错)",
                message,
                flags=re.IGNORECASE,
            )
        )

    def _extract_number_after_keywords(self, message: str, keywords: tuple[str, ...]) -> str | None:
        keyword_pattern = "|".join(re.escape(keyword) for keyword in keywords)
        match = re.search(rf"(?:{keyword_pattern})\s*[:：#-]?\s*([A-Za-z0-9]{{3,20}})", message, flags=re.IGNORECASE)
        if not match:
            return None
        value = match.group(1).strip().upper()
        return value if value.isdigit() else None

    def _source_subagent_prompt(self) -> str:
        return (
            "你是 ABAP 源码调查子 Agent。你的任务是在问题相关源码包中快速定位可执行证据。"
            "仅当问题涉及源码、接口、字段血缘、计算或过滤逻辑时才进入源码调查；普通业务数据查询不要为了走流程而查源码。"
            "如果用户给出事务码，优先顺序：事务码对应程序 -> program_source/function_source 获取源码包 -> 定位赋值/计算/过滤条件 -> 查表数据对照 -> 必要时 source_full_text。"
            "如果用户给出函数/程序名，直接从该对象开始，不要额外查事务码。"
            "如果已经找到目标字段的赋值或计算，不要继续泛搜。"
        )

    def _assert_only_sap_tools(self, tools: list[StructuredTool]) -> None:
        tool_names = {tool.name for tool in tools}
        unexpected = sorted(tool_names - self.SAP_AGENT_TOOL_NAMES)
        missing = sorted(self.SAP_AGENT_TOOL_NAMES - tool_names)
        if unexpected or missing:
            raise RuntimeError(f"SAP 助手工具集合异常，unexpected={unexpected}, missing={missing}")

    def _normalize_source_object_type(self, object_type: str | None) -> str:
        normalized = str(object_type or "PROG").strip().upper()
        if normalized in {"FUNC", "FUNCTION", "FUNCTION_MODULE", "FM"}:
            return "FUNC"
        return "PROG"

    def _normalize_source_window(self, start_line: int, max_lines: int) -> tuple[int, int]:
        try:
            start = int(start_line or 1)
        except (TypeError, ValueError):
            start = 1
        try:
            size = int(max_lines or 80)
        except (TypeError, ValueError):
            size = 80
        start = max(1, start)
        size = max(20, min(size, 120))
        return start, start + size - 1

    def _source_window_overlap_message(
        self,
        object_name: str,
        object_type: str,
        window: tuple[int, int],
        budget_state: dict[str, Any],
    ) -> str:
        read_windows = budget_state.get("read_windows")
        if not isinstance(read_windows, dict):
            return ""
        key = f"{object_type}:{object_name.upper()}"
        existing = read_windows.get(key)
        if not isinstance(existing, list):
            return ""
        start, end = window
        for old_start, old_end in existing:
            overlap = max(0, min(end, old_end) - max(start, old_start) + 1)
            if overlap >= min(end - start + 1, old_end - old_start + 1) * 0.6:
                return f"{object_name} 第 {start}-{end} 行与已读窗口 {old_start}-{old_end} 高度重叠，请改用新关键词搜索、读取非重叠片段或总结已有证据。"
        return ""

    def _mark_source_window(
        self,
        object_name: str,
        object_type: str,
        window: tuple[int, int],
        budget_state: dict[str, Any],
    ) -> None:
        read_windows = budget_state.setdefault("read_windows", {})
        if not isinstance(read_windows, dict):
            return
        key = f"{object_type}:{object_name.upper()}"
        existing = read_windows.setdefault(key, [])
        if isinstance(existing, list):
            existing.append(window)

    def _record_investigation_evidence(self, result: Any, budget_state: dict[str, Any]) -> None:
        ledger = budget_state.setdefault("evidence_ledger", [])
        if not isinstance(ledger, list):
            return
        tool_name = getattr(result, "tool_name", "")
        data = getattr(result, "data", None)
        for item in getattr(result, "evidence", []) or []:
            content = item.content or {}
            strength = self._evidence_strength(tool_name, data, content)
            ledger.append(
                {
                    "tool": tool_name,
                    "title": item.title,
                    "source": item.source_object,
                    "location": item.location,
                    "strength": strength,
                    "sufficiency": content.get("sufficiency") if isinstance(content, dict) else None,
                    "uncertainty": content.get("uncertainty") if isinstance(content, dict) else None,
                    "summary": self._short_text(item.summary or "", 220),
                }
            )
        if isinstance(data, dict) and tool_name in {"program_source", "function_source", "source_manifest", "source_search", "source_slice"}:
            source_objects = budget_state.setdefault("source_objects", {})
            if isinstance(source_objects, dict):
                parsed = data.get("JSON_PARSED") if isinstance(data.get("JSON_PARSED"), dict) else data
                object_name = str(parsed.get("object") or parsed.get("resolvedProgram") or "").upper()
                object_type = str(parsed.get("objectType") or ("FUNC" if tool_name == "function_source" else "PROG")).upper()
                if object_name:
                    source_objects[f"{object_type}:{object_name}"] = {
                        "totalLines": parsed.get("totalLines"),
                        "lastTool": tool_name,
                        "lastRange": parsed.get("lineRange"),
                    }

    def _evidence_strength(self, tool_name: str, data: Any, content: dict[str, Any]) -> str:
        if isinstance(content, dict) and content.get("strength"):
            return str(content["strength"])
        if tool_name == "source_search" and isinstance(data, dict):
            return "strong" if int(data.get("executableMatchCount") or 0) > 0 else "weak"
        if tool_name == "source_slice" and isinstance(data, dict):
            return str(data.get("evidenceStrength") or "weak")
        if tool_name in {"program_source", "function_source"}:
            return "medium"
        if tool_name == "safe_table_read":
            return "strong"
        if tool_name in {"ddic_meta", "source_manifest", "knowledge_search"}:
            return "medium"
        return "weak"

    def _compact_investigation_state(
        self,
        message: str,
        tool_results: list[Any],
        evidence: list[SapToolEvidence],
        executed_plan: list[tuple[str, dict[str, Any]]],
        budget_state: dict[str, Any],
        reason: str,
    ) -> str:
        ledger = budget_state.get("evidence_ledger")
        source_objects = budget_state.get("source_objects")
        strong = [item for item in ledger if isinstance(item, dict) and item.get("strength") == "strong"] if isinstance(ledger, list) else []
        weak = [item for item in ledger if isinstance(item, dict) and item.get("strength") in {"weak", "medium"}] if isinstance(ledger, list) else []
        payload = {
            "reason": reason,
            "userQuestion": self._short_text(message, 300),
            "budget": {
                "toolCallsUsed": int(budget_state.get("tool_calls") or 0),
                "toolCallsLimit": self.MAX_TOOL_CALLS,
                "remainingToolCalls": max(0, self.MAX_TOOL_CALLS - int(budget_state.get("tool_calls") or 0)),
            },
            "executedPlanTail": [
                {"tool": tool, "params": self._compact_result_data(tool, params)}
                for tool, params in executed_plan[-6:]
            ],
            "sourceObjects": source_objects if isinstance(source_objects, dict) else {},
            "strongEvidence": strong[-6:],
            "weakEvidence": weak[-6:],
            "evidenceCount": len(evidence),
            "nextPolicy": (
                "如果已有强证据，调用 finish_investigation；如果缺少核心证据，只选择一个最高价值的 program_source/function_source 或真实 CALL FUNCTION 下钻；"
                "预算不足时跳过知识库等可选补强并说明不确定性。"
            ),
        }
        return self._to_llm_tool_text(payload)

    def _budget_guard(self, tool_name: str, params: dict[str, Any], budget_state: dict[str, Any]) -> str:
        call_key = json.dumps([tool_name, params], ensure_ascii=False, sort_keys=True, default=str)
        seen_call_keys = budget_state.get("seen_call_keys")
        if isinstance(seen_call_keys, set):
            if call_key in seen_call_keys:
                return "该工具调用和参数已经执行过，请基于已有结果继续总结，不要重复调用"
            seen_call_keys.add(call_key)
        if int(budget_state.get("tool_calls") or 0) >= self.MAX_TOOL_CALLS:
            return f"已达到本轮 SAP 工具 Agent 调用上限 {self.MAX_TOOL_CALLS} 次"

        return ""

    def _tool_result_cache_key(self, tool_name: str, params: dict[str, Any]) -> str:
        cacheable_params = {
            key: value
            for key, value in params.items()
            if not key.startswith("_") and key not in {"reason"}
        }
        return json.dumps([tool_name, cacheable_params], ensure_ascii=False, sort_keys=True, default=str)

    def _cached_tool_result(self, tool_name: str, params: dict[str, Any], budget_state: dict[str, Any]) -> Any | None:
        cache = budget_state.get("tool_result_cache")
        if not isinstance(cache, dict):
            return None
        return cache.get(self._tool_result_cache_key(tool_name, params))

    def _cache_tool_result(self, tool_name: str, params: dict[str, Any], result: Any, budget_state: dict[str, Any]) -> None:
        cache = budget_state.setdefault("tool_result_cache", {})
        if isinstance(cache, dict):
            cache[self._tool_result_cache_key(tool_name, params)] = result

    def _is_recursion_limit_error(self, exc: Exception) -> bool:
        reason = f"{type(exc).__name__}: {exc}"
        return any(token in reason for token in ("Recursion limit", "GRAPH_RECURSION_LIMIT", "GraphRecursionError"))

    def _friendly_agent_error(self, exc: Exception) -> str:
        if self._is_recursion_limit_error(exc):
            return (
                f"已达到本轮自动追查步数上限（{self.GRAPH_RECURSION_LIMIT} 步），"
                "系统已停止继续调用工具，并基于已有 SAP 证据生成阶段性结论。"
            )
        if isinstance(exc, SQLAlchemyError) or "sqlalchemy" in f"{type(exc).__module__}.{type(exc).__name__}".lower():
            return "后台记录工具调用时数据库连接中断，系统已停止本轮自动追查并基于已获得的证据生成阶段性回答。"
        reason = str(exc)
        if "LLM_PROXY_MODE" in reason:
            return reason
        if "Unknown scheme for proxy URL" in reason or "socks://" in reason:
            return (
                "模型服务代理配置不可用：当前代理地址使用了不被模型客户端接受的 socks:// 协议。"
                "请将服务器环境变量 HTTP_PROXY/HTTPS_PROXY/ALL_PROXY 中的 socks:// 改为 socks5://，"
                "或配置 LLM_PROXY_MODE=url、LLM_PROXY_URL=socks5://host:port 后重启服务。"
            )
        if "ConnectionDoesNotExistError" in reason or "connection was closed in the middle of operation" in reason:
            return "后台数据库连接在记录工具调用时中断，系统已停止本轮自动追查并基于已获得的证据生成阶段性回答。"
        return str(exc)

    def _friendly_tool_exception(self, tool_name: str, exc: Exception) -> str:
        reason = str(exc)
        if isinstance(exc, SQLAlchemyError) or "ConnectionDoesNotExistError" in reason or "connection was closed in the middle of operation" in reason:
            return f"{self._tool_action_label(tool_name)}过程中后台记录连接中断，系统会保留已获得的线索并停止本轮工具调用。"
        if "RFC_COMMUNICATION_FAILURE" in reason or "WSAETIMEDOUT" in reason:
            return f"{self._tool_action_label(tool_name)}时 SAP 连接不稳定，未能完成该步验证。"
        return f"{self._tool_action_label(tool_name)}执行异常，系统会基于已有证据继续整理阶段性回答。"

    def _llm_tool_return(
        self,
        tool_name: str,
        data: Any,
        status: str,
        summary: str,
        params: dict[str, Any] | None = None,
        user_question: str = "",
    ) -> str:
        if status != "success":
            error_type = data.get("errorType") if isinstance(data, dict) else None
            return self._to_llm_tool_text(
                {
                    "ok": False,
                    "tool": tool_name,
                    "error": summary,
                    "errorType": error_type or "tool_failed",
                    "diagnosticHint": data.get("agentHint") if isinstance(data, dict) else None,
                    "retryable": bool(data.get("retryable")) if isinstance(data, dict) else False,
                    "target": data.get("target") if isinstance(data, dict) else None,
                    "businessConclusionAllowed": False,
                    "nextPolicy": self._failed_tool_next_policy(data if isinstance(data, dict) else {}),
                }
            )
        if tool_name in {"program_source", "function_source"} and params and params.get("_return_full_source"):
            return self._source_payload_to_text(data)
        if tool_name in {"program_source", "function_source"}:
            return self._source_payload_to_investigation_pack(data, user_question, params)
        if tool_name == "safe_table_read":
            return self._table_payload_to_text(data, tool_name)
        compact_data = self._compact_result_data(tool_name, data)
        return self._to_llm_tool_text(compact_data)

    def _table_payload_to_text(self, data: Any, tool_name: str) -> str:
        if not isinstance(data, dict):
            return self._to_llm_tool_text(data)
        parsed = data.get("JSON_PARSED")
        if not isinstance(parsed, dict):
            return self._to_llm_tool_text(self._compact_result_data(tool_name, data))
        table_name = parsed.get("table") or "-"
        fields = parsed.get("fields") if isinstance(parsed.get("fields"), list) else []
        rows = parsed.get("rows") if isinstance(parsed.get("rows"), list) else []
        ranges = data.get("IT_RANGES") if isinstance(data.get("IT_RANGES"), list) else []
        lines = [
            f"TABLE_RESULT {tool_name}",
            f"table: {table_name}",
            f"rowCount: {parsed.get('rowCount', len(rows))}",
            f"fields: {', '.join(str(item) for item in fields) or '-'}",
        ]
        if ranges:
            range_text = []
            for item in ranges[:8]:
                if isinstance(item, dict):
                    range_text.append(
                        f"{item.get('FIELDNAME')} {item.get('SIGN', 'I')}{item.get('OPTION', 'EQ')} {item.get('LOW')}"
                        + (f"..{item.get('HIGH')}" if item.get("HIGH") else "")
                    )
            lines.append(f"ranges: {'; '.join(range_text) or '-'}")
        if fields and rows:
            lines.append("| " + " | ".join(str(item) for item in fields) + " |")
            lines.append("| " + " | ".join("---" for _ in fields) + " |")
            for row in rows[:12]:
                if isinstance(row, list):
                    lines.append("| " + " | ".join(self._short_text(str(cell), 80) for cell in row) + " |")
                else:
                    lines.append(f"| {self._short_text(str(row), 240)} |")
            if len(rows) > 12:
                lines.append(f"... 另有 {len(rows) - 12} 行已省略")
        return "\n".join(lines)

    def _source_payload_to_investigation_pack(
        self,
        data: Any,
        user_question: str = "",
        params: dict[str, Any] | None = None,
    ) -> str:
        parsed = self._source_parsed(data)
        lines = parsed.get("lines")
        if not isinstance(lines, list):
            return self._source_payload_to_text(data)
        object_name = parsed.get("object") or parsed.get("resolvedProgram") or ""
        start_line = int(parsed.get("startLine") or 1)
        total_lines = parsed.get("totalLines") or len(lines)
        keywords = self._source_relevance_keywords(user_question, params, lines)
        statements, snippets, calls, forms = self._source_evidence_snippets(lines, start_line, keywords)
        text = self._format_source_investigation_pack(
            object_name=str(object_name),
            resolved_program=str(parsed.get("resolvedProgram") or ""),
            total_lines=total_lines,
            keywords=keywords,
            forms=forms,
            calls=calls,
            statements=statements,
            snippets=snippets,
        )
        return text if len(text) <= self.MAX_SOURCE_PACK_TEXT else f"{text[:self.MAX_SOURCE_PACK_TEXT]}\n...[源码调查包过长，已截断]"

    def _format_source_investigation_pack(
        self,
        object_name: str,
        resolved_program: str,
        total_lines: Any,
        keywords: list[str],
        forms: list[dict[str, Any]],
        calls: list[str],
        statements: list[dict[str, Any]],
        snippets: list[dict[str, Any]],
    ) -> str:
        sections = [
            "SOURCE_PACK focused_source_pack",
            f"object: {object_name}",
            f"resolvedProgram: {resolved_program or '-'}",
            f"totalLines: {total_lines}",
            "note: 完整源码已写入服务层缓存/审计/前端事件；此处只给与问题相关的可执行代码。若关键分支仍缺失，再调用 source_full_text。",
            f"keywords: {', '.join(keywords[:36]) or '-'}",
        ]
        if forms:
            form_text = ", ".join(
                f"{item.get('name')}@{item.get('startLine')}-{item.get('endLine') or '?'}"
                for item in forms[:24]
                if item.get("name")
            )
            sections.append(f"forms: {form_text or '-'}")
        if calls:
            sections.append(f"calls: {', '.join(calls[:30])}")
        sections.append("keyStatements:")
        if statements:
            for index, statement in enumerate(statements[:14], start=1):
                line_range = statement.get("lineRange") or []
                reason = statement.get("reason") or "related executable statement"
                sections.append(f"[{index}] lines {line_range}: {reason}")
                sections.append(self._format_source_lines(statement.get("lines")))
        else:
            sections.append("- 未抽取到高置信可执行语句；如必须确认完整控制流，可调用 source_full_text。")
        if snippets:
            sections.append("supportingSnippets:")
            rendered = []
            statement_lines = {
                item.get("line")
                for statement in statements[:14]
                for item in (statement.get("lines") or [])
                if isinstance(item, dict)
            }
            for item in snippets:
                line_no = item.get("line")
                if line_no in statement_lines:
                    continue
                rendered.append(f"{line_no}: {item.get('text')}")
                if len(rendered) >= 24:
                    break
            sections.extend(rendered or ["- 无额外片段。"])
        sections.append("next: 先按 keyStatements 中的表/字段/过滤条件查 safe_table_read 对照数据；不要重复读取同一源码对象。")
        return "\n".join(sections)

    def _format_source_lines(self, raw_lines: Any) -> str:
        if not isinstance(raw_lines, list):
            return ""
        rendered = []
        for item in raw_lines:
            if isinstance(item, dict):
                rendered.append(f"{item.get('line')}: {item.get('text')}")
            else:
                rendered.append(str(item))
        return "\n".join(rendered)

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

    def _source_relevance_keywords(
        self,
        user_question: str,
        params: dict[str, Any] | None,
        lines: list[Any],
    ) -> list[str]:
        raw_text = user_question
        if params:
            raw_text = f"{raw_text} {json.dumps(params, ensure_ascii=False, default=str)}"
        tokens = re.findall(r"[A-Za-z_][A-Za-z0-9_]{1,}|[0-9]{4,}", raw_text.upper())
        stop_words = {
            "THIS",
            "THAT",
            "FUNC",
            "PROG",
            "TYPE",
            "TRUE",
            "FALSE",
            "NULL",
            "NONE",
            "MAX",
            "ROWS",
            "FIELD",
            "FIELDS",
            "RANGE",
            "RANGES",
        }
        keywords: list[str] = []
        seen: set[str] = set()
        for token in tokens:
            if token in stop_words or len(token) < 2:
                continue
            if token not in seen:
                keywords.append(token)
                seen.add(token)
        if any(token in seen for token in {"VBELN", "BUKRS"}):
            for token in ("VBRK", "VBRP", "VBAK", "VBFA", "VBKD", "AUART", "ERDAT", "AEDAT", "RFBSK", "FKSTO", "SFAKN"):
                if token not in seen:
                    keywords.append(token)
                    seen.add(token)
        for token in self._source_common_table_tokens(lines):
            if token not in seen:
                keywords.append(token)
                seen.add(token)
            if len(keywords) >= 48:
                break
        return keywords[:48]

    def _source_common_table_tokens(self, lines: list[Any]) -> list[str]:
        counts: dict[str, int] = {}
        for raw_line in lines:
            upper = str(raw_line).upper()
            if not any(marker in upper for marker in ("SELECT", "JOIN", "FROM", "INTO", "~")):
                continue
            for token in re.findall(r"\b[A-Z][A-Z0-9_]{2,}\b", upper):
                if token in {"SELECT", "SINGLE", "FROM", "WHERE", "INNER", "JOIN", "INTO", "TABLE", "FIELDS", "VALUE"}:
                    continue
                counts[token] = counts.get(token, 0) + 1
        return [token for token, _ in sorted(counts.items(), key=lambda item: item[1], reverse=True)[:24]]

    def _source_evidence_snippets(
        self,
        lines: list[Any],
        start_line: int,
        keywords: list[str],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str], list[dict[str, Any]]]:
        calls: list[str] = []
        selected: dict[int, str] = {}
        forms: list[dict[str, Any]] = []
        statement_windows: dict[tuple[int, int], dict[str, Any]] = {}
        open_form: dict[str, Any] | None = None
        important_tokens = tuple(dict.fromkeys([*keywords, "SELECT", "WHERE", "JOIN", "READ TABLE", "LOOP AT", "CALL FUNCTION", "PERFORM"]))

        def add_window(index: int, radius: int = 2) -> None:
            begin = max(0, index - radius)
            end = min(len(lines), index + radius + 1)
            for offset in range(begin, end):
                selected[start_line + offset] = self._short_text(str(lines[offset]), 260)

        def add_statement(index: int, reason: str) -> None:
            begin, end = self._abap_statement_bounds(lines, index)
            key = (start_line + begin, start_line + end)
            if key in statement_windows:
                return
            statement_text = "\n".join(str(lines[offset]) for offset in range(begin, end + 1))
            score = self._source_statement_score(statement_text, keywords)
            if score <= 0:
                return
            text_lines = [
                {"line": start_line + offset, "text": self._short_text(str(lines[offset]), 360)}
                for offset in range(begin, end + 1)
            ]
            statement_windows[key] = {
                "lineRange": [key[0], key[1]],
                "reason": reason,
                "score": score,
                "lines": text_lines,
            }
            for offset in range(begin, end + 1):
                selected[start_line + offset] = self._short_text(str(lines[offset]), 260)

        for index, raw_line in enumerate(lines):
            line = str(raw_line)
            upper = line.upper()
            if self._is_abap_comment_or_declaration(upper):
                continue
            matched_keywords = [token for token in keywords if token and token in upper]
            form_match = re.search(r"^\s*FORM\s+([A-Z0-9_]+)", upper)
            if form_match:
                open_form = {"name": form_match.group(1), "startLine": start_line + index}
                forms.append(open_form)
            if open_form is not None and re.search(r"^\s*ENDFORM\b", upper):
                open_form["endLine"] = start_line + index
                open_form = None
            call_match = re.search(r"CALL\s+FUNCTION\s+'?([A-Z0-9_]+)'?", upper)
            if call_match and call_match.group(1) not in calls:
                calls.append(call_match.group(1))
                if matched_keywords:
                    add_statement(index, f"函数调用命中关键词：{', '.join(matched_keywords[:5])}")
                else:
                    add_window(index, 1)
            perform_match = re.search(r"\bPERFORM\s+([A-Z0-9_]+)", upper)
            if perform_match:
                perform_name = f"PERFORM {perform_match.group(1)}"
                if perform_name not in calls:
                    calls.append(perform_name)
                if matched_keywords:
                    add_statement(index, f"PERFORM 命中关键词：{', '.join(matched_keywords[:5])}")
            if matched_keywords and self._looks_like_executable_abap(upper):
                add_statement(index, f"命中用户问题相关关键词：{', '.join(matched_keywords[:6])}")
            elif any(token in upper for token in important_tokens) and self._looks_like_executable_abap(upper):
                add_window(index, 2)
            elif self._looks_like_executable_abap(upper) and any(word in upper for word in ("SELECT", "READ TABLE", "LOOP AT", "FORM ", "ENDFORM")):
                if len(selected) < 120:
                    add_window(index, 1)
        snippets = [{"line": line_no, "text": selected[line_no]} for line_no in sorted(selected)]
        statements = sorted(statement_windows.values(), key=lambda item: (-int(item.get("score") or 0), item["lineRange"][0]))
        return statements, snippets, calls, forms

    def _is_abap_comment_or_declaration(self, upper_line: str) -> bool:
        stripped = upper_line.strip()
        if not stripped or stripped.startswith("*") or stripped.startswith('"'):
            return True
        declaration_prefixes = (
            "DATA:",
            "DATA ",
            "TYPES:",
            "TYPES ",
            "FIELD-SYMBOLS",
            "CONSTANTS",
            "RANGES:",
            "RANGES ",
            "TABLES:",
            "TYPE-POOLS",
        )
        return any(stripped.startswith(prefix) for prefix in declaration_prefixes)

    def _looks_like_executable_abap(self, upper_line: str) -> bool:
        if self._is_abap_comment_or_declaration(upper_line):
            return False
        executable_tokens = (
            "SELECT",
            "READ TABLE",
            "CALL FUNCTION",
            "PERFORM",
            "LOOP AT",
            "IF ",
            "ELSEIF ",
            "CASE ",
            "MOVE",
            "APPEND",
            "COLLECT",
            "MODIFY",
            "DELETE",
            "SORT",
            "CLEAR",
            " = ",
        )
        return any(token in upper_line for token in executable_tokens)

    def _source_statement_score(self, statement_text: str, keywords: list[str]) -> int:
        upper = statement_text.upper()
        if not self._looks_like_executable_abap(upper):
            return 0
        score = 0
        for keyword in keywords:
            if keyword and keyword in upper:
                score += 3
        weighted_tokens = {
            "SELECT": 18,
            " FROM ": 8,
            " JOIN ": 8,
            " WHERE ": 10,
            "VBAK~AUART": 14,
            "AUART": 8,
            "VBELN": 7,
            "BUKRS": 7,
            "ERDAT": 6,
            "RFBSK": 6,
            "READ TABLE": 8,
            "CALL FUNCTION": 6,
            "PERFORM": 4,
        }
        for token, weight in weighted_tokens.items():
            if token in upper:
                score += weight
        if any(prefix in upper.strip() for prefix in ("TYPES:", "DATA:", "RANGES:", "CONSTANTS")):
            score -= 30
        return max(0, score)

    def _abap_statement_bounds(self, lines: list[Any], index: int) -> tuple[int, int]:
        begin = index
        while begin > 0 and not str(lines[begin - 1]).rstrip().endswith("."):
            begin -= 1
            if index - begin >= 80:
                break
        end = index
        while end < len(lines) - 1 and not str(lines[end]).rstrip().endswith("."):
            end += 1
            if end - index >= 80:
                break
        return begin, end

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
        enable_reasoning: bool = False,
        langchain_config: dict[str, Any] | None = None,
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
            "只基于已给出的工具结果和证据生成中文回答。请按用户问题自然组织表达，不要套用固定格式或固定小标题。"
            "如果证据不足，必须明确说证据不足；不能把注释、字段定义或未验证信息当作确定业务逻辑。"
        )
        context_text = self._summary_context_text(message, system, tool_results, evidence, stop_reason, agent_answer)
        try:
            model = await self._get_streaming_model(model_name, enable_reasoning=enable_reasoning)
            chunks: list[str] = []
            async for chunk in model.astream(
                [SystemMessage(content=prompt), HumanMessage(content=context_text)],
                config=langchain_config,
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
            ]
            for item in evidence[:8]:
                lines.append(f"- {item.title}：{item.summary or '已返回结构化结果'}")
            if not evidence:
                lines.append("- 暂无可用证据。")
            lines.extend(["", "如需确定字段取值、金额计算或血缘关系，需要继续取得可执行源码、DDIC 或日志证据；如需核对业务记录，请按建议条件在 SAP 中自行查询。"])
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
                sections.append(self._source_payload_to_investigation_pack(item.data, message, {"object_name": item.evidence[0].source_object if item.evidence else ""}))
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
        public_item = self._public_timeline_item(item)
        await self._emit(
            event_sink,
            "thought_node",
            {
                "nodeId": public_item["id"],
                "act": "calling_tool" if public_item["status"] == "pending" else "tool_result",
                "status": public_item["status"],
                "detailStr": public_item["detail"],
                "toolName": public_item.get("title") or public_item.get("toolName"),
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

    def _public_timeline_item(self, item: dict[str, Any]) -> dict[str, Any]:
        public_item = {**item}
        public_item.pop("debugDetail", None)
        status = str(public_item.get("status") or "")
        detail = str(public_item.get("detail") or "")
        tool_name = str(public_item.get("toolName") or "")
        if tool_name == "compact_investigation_state":
            public_item["title"] = "梳理已知线索"
            public_item["detail"] = "正在整理已获得的源码、表结构和数据线索，决定下一步是否还需要补查。"
        elif status == "skipped":
            public_item["title"] = "调整查询范围"
            public_item["detail"] = self._friendly_skip_detail(detail)
        elif status == "failed":
            public_item["detail"] = self._friendly_failure_detail(tool_name, detail)
        return public_item

    def _friendly_skip_detail(self, detail: str) -> str:
        if "已经执行过" in detail:
            return "这个方向已经查过，系统会避免重复调用，改用已有结果继续判断。"
        if "调用上限" in detail:
            return "本轮自动排查已接近工具调用上限，正在基于已有证据整理回答。"
        return "系统已调整这一步，避免重复或低价值查询。"

    def _friendly_failure_detail(self, tool_name: str, detail: str) -> str:
        if "后台记录" in detail or "SAP 连接不稳定" in detail:
            return detail
        if "SQLAlchemy" in detail or "asyncpg" in detail or "ConnectionDoesNotExistError" in detail:
            return "后台记录工具调用时数据库连接中断，系统会基于已获得的证据给出阶段性回答。"
        if "RFC 网络不可达" in detail or "未能连接 SAP RFC" in detail or "connection_failure" in detail:
            return "本次 SAP 连接不稳定，未能完成该步数据验证；这不代表业务数据不存在。"
        if "JSON 无法解析" in detail or "JSON_PARSE_ERROR" in detail or "json_parse_error" in detail:
            return "SAP 工具返回内容格式异常，系统暂时无法可靠读取这一步结果；需要修复 RFC 返回 JSON 后重试。"
        if "subrc=6" in detail or "缓冲区超出" in detail:
            return "本次读表返回量过大，系统会提示改用更少字段和更精确条件重试。"
        if tool_name == "ddic_meta" and "未找到" in detail:
            return "没有在数据字典中找到这个对象，系统会尝试换一个更可能的表或结构继续核对。"
        return "这一步没有拿到可用结果，系统会基于已有线索调整排查方向。"

    def _failed_tool_next_policy(self, data: dict[str, Any]) -> str:
        error_type = str(data.get("errorType") or "")
        if error_type == "json_parse_error":
            return (
                "这是 SAP 侧 RFC 返回格式错误，不是业务无数据。不要把本次 DDIC/数据结果作为证据；"
                "请提示修复 ZFM_AI_* RFC 的 JSON 转义，或在已有源码证据足够时只给阶段性结论并标注 DDIC 验证缺口。"
            )
        if error_type in {"connection_failure", "timeout"}:
            return "本轮未能连接 SAP 取数，不能据此判断凭证或表记录不存在；可基于已有源码证据给阶段性结论并标注数据验证缺口。"
        if error_type == "read_table_buffer_exceeded":
            return "请将 safe_table_read 改成 fields<=5、max_rows<=3，并增加高选择性 EQ 条件后重试；该结果不能证明业务数据不存在。"
        return "不能把失败工具结果作为确定业务结论；请换更小范围工具调用，或基于已有证据说明不确定性。"

    def _tool_action_label(self, tool_name: str) -> str:
        labels = {
            "tcode_info": "查询事务码",
            "program_source": "读取程序完整源码",
            "function_source": "读取函数完整源码",
            "source_manifest": "建立源码清单",
            "source_search": "搜索源码证据",
            "source_slice": "读取源码切片",
            "ddic_meta": "查询 DDIC 结构",
            "safe_table_read": "读取 SAP 只读样例数据",
            "knowledge_search": "检索知识库",
            "compact_investigation_state": "压缩调查状态",
        }
        return labels.get(tool_name, tool_name)

    def _tool_pending_detail(self, tool_name: str, params: dict[str, Any]) -> str:
        if tool_name == "tcode_info":
            tcode = params.get("tcode") or params.get("query") or "用户问题中的事务码"
            return f"正在核对事务码 {tcode} 的入口信息。"
        if tool_name == "program_source":
            object_name = params.get("object_name") or "未知程序"
            return f"正在读取 ABAP 程序 {object_name} 的完整源码，准备分析字段赋值、取数和函数调用。"
        if tool_name == "function_source":
            object_name = params.get("object_name") or "未知函数"
            return f"正在读取函数 {object_name} 的完整源码，准备追踪内部取数、计算和返回值。"
        if tool_name == "source_manifest":
            object_name = params.get("object_name") or "未知源码对象"
            object_type = params.get("object_type") or "PROG"
            return f"正在为 {object_type} {object_name} 建立源码清单、调用关系和关键词索引。"
        if tool_name == "source_search":
            object_name = params.get("object_name") or "未知源码对象"
            keywords = params.get("keywords") or params.get("query") or []
            return f"正在 {object_name} 的缓存源码中搜索证据关键词：{self._compact_text(keywords, 220)}。"
        if tool_name == "source_slice":
            object_name = params.get("object_name") or "未知源码对象"
            start_line = params.get("start_line") or 1
            max_lines = params.get("max_lines") or 80
            return f"正在读取 {object_name} 第 {start_line} 行起的最小源码切片（约 {max_lines} 行）。"
        if tool_name == "ddic_meta":
            object_name = params.get("object_name") or "未知对象"
            return f"正在查看 {object_name} 的字段、长度、日期含义和转换规则。"
        if tool_name == "safe_table_read":
            table_name = params.get("table_name") or "未知表"
            fields = params.get("fields") or []
            ranges = params.get("ranges") or []
            max_rows = params.get("max_rows") or 5
            return (
                f"正在按已收窄的条件读取 {table_name} 的少量只读数据：字段 {len(fields)} 个、条件 {len(ranges)} 个、最多 {max_rows} 行。"
                "系统会避免无条件读取或读取过宽数据。"
            )
        return f"参数：{self._compact_text(params, 360)}"

    def _tool_done_detail(self, tool_name: str, params: dict[str, Any], summary: str, data: Any) -> str:
        if isinstance(data, dict) and data.get("errorType") in {"connection_failure", "timeout"}:
            target = data.get("target")
            target_text = f"（目标：{target}）" if target else ""
            return (
                f"{self._tool_action_label(tool_name)}未能连接 SAP RFC{target_text}；"
                "这只是技术连通性失败，不能作为业务数据不存在的证据。"
            )
        if isinstance(data, dict) and data.get("errorType") == "read_table_buffer_exceeded":
            return (
                "只读表查询触发 RFC_READ_TABLE 缓冲区超出（subrc=6）；"
                "请减少字段到 5 个以内、max_rows 降到 1-3，并增加主键/凭证号/公司/日期等 EQ 条件后重试。"
            )
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
        if tool_name == "source_manifest" and isinstance(data, dict):
            return (
                f"已建立源码清单：{data.get('object') or params.get('object_name')}，"
                f"FORM {len(data.get('forms') or [])} 个、函数调用线索 {len(data.get('discoveredFunctionCalls') or [])} 个；LLM 未接收源码全文。"
            )
        if tool_name == "source_search" and isinstance(data, dict):
            return (
                f"源码搜索命中 {data.get('matchCount') or 0} 处，其中可执行代码 {data.get('executableMatchCount') or 0} 处；"
                "下一步只需读取关键非重复切片或总结证据。"
            )
        if tool_name == "source_slice" and isinstance(data, dict):
            line_range = data.get("lineRange") or []
            return f"已读取源码切片 {line_range}，证据强度：{data.get('evidenceStrength') or 'unknown'}。"
        return summary or f"{self._tool_action_label(tool_name)}完成。"

    def _user_friendly_tool_detail(self, tool_name: str, params: dict[str, Any], status: str, summary: str, data: Any) -> str:
        if status == "skipped":
            return self._friendly_skip_detail(summary)
        if status == "failed":
            return self._friendly_failure_detail(tool_name, summary)
        if tool_name in {"program_source", "function_source"}:
            object_name = params.get("object_name") or "源码对象"
            total_lines = self._source_total_lines(data)
            suffix = f"共 {total_lines} 行，" if total_lines else ""
            return f"已读取 {object_name} 的源码，{suffix}正在提取与问题相关的关键逻辑。"
        if tool_name == "tcode_info":
            programs = self._programs_from_tcode_data(data)
            if programs:
                return f"已定位到相关程序：{', '.join(programs[:3])}。"
            return "已查询事务码相关对象，正在判断下一步入口。"
        if tool_name == "ddic_meta":
            object_name = params.get("object_name") or "目标对象"
            return f"已读取 {object_name} 的字段和结构信息，正在据此收窄查询条件。"
        if tool_name == "safe_table_read":
            table_name = params.get("table_name") or "目标表"
            return f"已按收窄条件读取 {table_name} 的少量数据，正在整理与问题直接相关的结果。"
        if tool_name == "knowledge_search":
            return summary or "已检索知识库补充背景信息。"
        return summary or f"{self._tool_action_label(tool_name)}已完成。"

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

    def _timeline(
        self,
        node_id: str,
        status: str,
        title: str,
        detail: str,
        tool_name: str | None = None,
        debug_detail: str | None = None,
    ) -> dict[str, Any]:
        item = {"id": node_id, "status": status, "title": title, "detail": detail, "toolName": tool_name or node_id}
        if debug_detail:
            item["debugDetail"] = self._short_text(debug_detail, 2000)
        return item


sap_deep_agent_service = SapDeepAgentService()
