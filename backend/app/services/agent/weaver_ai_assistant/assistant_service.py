import asyncio
import json
import re
import time
from collections.abc import AsyncIterator
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from langchain_core.messages import HumanMessage, SystemMessage
import pymysql
from pymysql.cursors import DictCursor

from app.core.config import settings
from app.core.llm_factory import LLMFactory
from app.core.logger import logger
from app.schemas.agent.weaver_ai_assistant import (
    WeaverAssistantAction,
    WeaverAssistantChatRequest,
    WeaverAssistantChatResponse,
    WeaverFieldConfigItem,
    WeaverFieldOptionItem,
    WeaverFieldConfigResponse,
    WeaverNodeConfigItem,
)
from app.services.agent.weaver_ai_assistant.workflow_rule_service import weaver_workflow_rule_service


class WeaverAiAssistantService:
    """泛微流程填单助手。"""

    DATE_TOOL_TIMEZONE = "Asia/Shanghai"
    ACTION_START_TAG = "<WEAVER_ACTIONS>"
    ACTION_END_TAG = "</WEAVER_ACTIONS>"

    async def get_field_config(self, workflow_id: str, weaver_env: str | None = None) -> WeaverFieldConfigResponse:
        env_key = self._normalize_env(weaver_env)
        metadata_config = self._get_weaver_db_config(env_key)
        if metadata_config:
            try:
                return await asyncio.to_thread(self._load_field_config_from_weaver_db, workflow_id, env_key, metadata_config)
            except Exception as exc:
                logger.warning(
                    "泛微流程 AI 助手读取数据库字段配置失败，准备回退到手工配置: "
                    f"env={env_key}, workflow_id={workflow_id}, error={exc}"
                )

        configs = self._load_field_configs()
        env_configs = configs.get(env_key)
        if isinstance(env_configs, dict):
            raw_fields = env_configs.get(str(workflow_id), [])
        else:
            raw_fields = configs.get(str(workflow_id), [])
        fields = self._normalize_field_config(raw_fields)
        logger.info(f"泛微流程 AI 助手使用手工字段配置: env={env_key}, workflow_id={workflow_id}, fields={len(fields)}")
        return WeaverFieldConfigResponse(workflowId=workflow_id, env=env_key, fields=fields)

    def _normalize_env(self, weaver_env: str | None) -> str:
        value = (weaver_env or settings.WEAVER_DEFAULT_ENV or "default").strip()
        return value or "default"

    def _get_weaver_db_config(self, env_key: str) -> dict[str, Any] | None:
        raw_value = (settings.WEAVER_DB_CONFIGS or "").strip()
        if not raw_value:
            return None
        try:
            configs = json.loads(raw_value)
        except Exception as exc:
            logger.warning(f"泛微流程 AI 助手数据库配置解析失败: {exc}")
            return None
        if not isinstance(configs, dict):
            return None
        config = configs.get(env_key)
        if not isinstance(config, dict):
            logger.warning(f"泛微流程 AI 助手未找到数据库环境配置: env={env_key}")
            return None
        return config

    def _load_field_config_from_weaver_db(
        self,
        workflow_id: str,
        env_key: str,
        db_config: dict[str, Any],
    ) -> WeaverFieldConfigResponse:
        host = str(db_config.get("host") or "")
        port = int(db_config.get("port") or 3306)
        database = str(db_config.get("database") or db_config.get("db") or "ecology")
        logger.info(
            "泛微流程 AI 助手开始读取数据库字段配置: "
            f"env={env_key}, host={host}, port={port}, database={database}, workflow_id={workflow_id}"
        )

        with self._connect_weaver_mysql(db_config) as conn:
            with conn.cursor() as cursor:
                workflow = self._fetch_one(
                    cursor,
                    """
                    SELECT id, workflowname, formid, isbill
                    FROM workflow_base
                    WHERE id = %s
                    """,
                    (workflow_id,),
                )
                if not workflow:
                    raise ValueError(f"workflow_base 未找到流程: workflow_id={workflow_id}")

                form_id = str(workflow.get("formid") or "")
                bill = self._fetch_bill(cursor, form_id)
                if not bill:
                    raise ValueError(f"workflow_bill 未找到表单: workflow_id={workflow_id}, form_id={form_id}")

                bill_id = str(bill.get("id") or "")
                fields = self._fetch_fields(cursor, bill_id)
                self._attach_select_options(cursor, fields)
                try:
                    nodes = self._fetch_nodes(cursor, workflow_id)
                except Exception as exc:
                    logger.warning(f"泛微流程 AI 助手读取节点失败，已忽略节点信息: workflow_id={workflow_id}, error={exc}")
                    nodes = []

        logger.info(
            "泛微流程 AI 助手读取数据库字段配置成功: "
            f"env={env_key}, workflow_id={workflow_id}, form_id={form_id}, "
            f"bill_id={bill_id}, fields={len(fields)}, nodes={len(nodes)}"
        )
        return WeaverFieldConfigResponse(
            workflowId=str(workflow_id),
            env=env_key,
            workflowName=self._to_text(workflow.get("workflowname")),
            formId=form_id,
            billId=bill_id,
            mainTable=self._to_text(bill.get("tablename")),
            detailKeyField=self._to_text(bill.get("detailkeyfield")),
            fields=fields,
            nodes=nodes,
        )

    def _connect_weaver_mysql(self, db_config: dict[str, Any]):
        host = str(db_config.get("host") or "")
        port = int(db_config.get("port") or 3306)
        database = str(db_config.get("database") or db_config.get("db") or "ecology")
        user = str(db_config.get("user") or db_config.get("username") or "")
        password = str(db_config.get("password") or "")
        charset = str(db_config.get("charset") or "utf8mb4")
        retry_count = int(db_config.get("retry_count") or db_config.get("retries") or 8)
        connect_timeout = int(db_config.get("connect_timeout") or 20)
        last_error: Exception | None = None

        for attempt in range(1, max(retry_count, 1) + 1):
            try:
                return pymysql.connect(
                    host=host,
                    port=port,
                    user=user,
                    password=password,
                    database=database,
                    charset=charset,
                    cursorclass=DictCursor,
                    connect_timeout=connect_timeout,
                    read_timeout=int(db_config.get("read_timeout") or 20),
                    write_timeout=int(db_config.get("write_timeout") or 20),
                )
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "泛微流程 AI 助手连接数据库失败，准备重试: "
                    f"host={host}, port={port}, database={database}, attempt={attempt}/{retry_count}, error={exc}"
                )
                if attempt < retry_count:
                    time.sleep(min(attempt, 3))
        raise RuntimeError(f"连接泛微数据库失败: {last_error}") from last_error

    def _fetch_one(self, cursor: Any, sql: str, params: tuple[Any, ...]) -> dict[str, Any] | None:
        cursor.execute(sql, params)
        row = cursor.fetchone()
        return self._normalize_row_keys(row) if row else None

    def _fetch_all(self, cursor: Any, sql: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
        cursor.execute(sql, params)
        return [self._normalize_row_keys(row) for row in cursor.fetchall()]

    def _fetch_bill(self, cursor: Any, form_id: str) -> dict[str, Any] | None:
        candidates = [form_id]
        try:
            absolute_form_id = str(abs(int(form_id)))
            if absolute_form_id not in candidates:
                candidates.append(absolute_form_id)
        except Exception:
            pass

        for candidate in candidates:
            bill = self._fetch_one(
                cursor,
                """
                SELECT id, tablename, detailkeyfield
                FROM workflow_bill
                WHERE id = %s
                """,
                (candidate,),
            )
            if bill:
                return bill
        return None

    def _fetch_fields(self, cursor: Any, bill_id: str) -> list[WeaverFieldConfigItem]:
        rows = self._fetch_all(
            cursor,
            """
            SELECT
                f.id AS field_id_num,
                f.fieldname AS field_name,
                f.fieldlabel AS field_label_id,
                f.fielddbtype AS field_db_type,
                f.fieldhtmltype AS field_html_type,
                f.type AS field_type,
                f.viewtype AS view_type,
                f.detailtable AS detail_table,
                COALESCE(h.labelname, f.fieldname) AS label
            FROM workflow_billfield f
            LEFT JOIN HtmlLabelInfo h ON h.indexid = f.fieldlabel AND h.languageid = 7
            WHERE f.billid = %s
            ORDER BY f.viewtype, f.id
            """,
            (bill_id,),
        )
        fields: list[WeaverFieldConfigItem] = []
        for row in rows:
            field_id_num = row.get("field_id_num")
            if field_id_num is None:
                continue
            label = self._to_text(row.get("label") or row.get("field_name") or f"field{field_id_num}")
            field_name = self._to_text(row.get("field_name"))
            fields.append(
                WeaverFieldConfigItem(
                    bizKey=field_name or f"field{field_id_num}",
                    label=label,
                    fieldId=f"field{field_id_num}",
                    type=self._map_weaver_field_type(row),
                    writable=True,
                    fieldName=field_name,
                    fieldDbType=self._to_text(row.get("field_db_type")),
                    fieldHtmlType=self._to_text(row.get("field_html_type")),
                    fieldType=self._to_text(row.get("field_type")),
                    browserType=self._to_text(row.get("field_type")) if self._to_text(row.get("field_html_type")) == "3" else None,
                    viewType=self._to_int(row.get("view_type")),
                    detailTable=self._to_text(row.get("detail_table")),
                )
            )
        return fields

    def _attach_select_options(self, cursor: Any, fields: list[WeaverFieldConfigItem]) -> None:
        select_fields = [field for field in fields if field.type == "select"]
        if not select_fields:
            return
        for field in select_fields:
            field_id_num = field.field_id.replace("field", "", 1)
            try:
                rows = self._fetch_all(
                    cursor,
                    """
                    SELECT selectvalue, selectname, cancel
                    FROM workflow_selectitem
                    WHERE fieldid = %s
                    ORDER BY listorder, id
                    """,
                    (field_id_num,),
                )
            except Exception as exc:
                logger.warning(f"泛微流程 AI 助手读取下拉选项失败: field={field.field_id}, error={exc}")
                continue
            field.options = [
                WeaverFieldOptionItem(
                    value=self._to_text(row.get("selectvalue")),
                    label=self._to_text(row.get("selectname")),
                    disabled=self._to_text(row.get("cancel")) == "1",
                )
                for row in rows
                if self._to_text(row.get("selectvalue")) or self._to_text(row.get("selectname"))
            ]

    def _fetch_nodes(self, cursor: Any, workflow_id: str) -> list[WeaverNodeConfigItem]:
        rows = self._fetch_all(
            cursor,
            """
            SELECT
                fn.nodeid AS node_id,
                nb.nodename AS node_name
            FROM workflow_flownode fn
            LEFT JOIN workflow_nodebase nb ON nb.id = fn.nodeid
            WHERE fn.workflowid = %s
            ORDER BY fn.nodeid
            """,
            (workflow_id,),
        )
        nodes: list[WeaverNodeConfigItem] = []
        for row in rows:
            node_id = self._to_text(row.get("node_id"))
            if not node_id:
                continue
            nodes.append(
                WeaverNodeConfigItem(
                    nodeId=node_id,
                    nodeName=self._to_text(row.get("node_name") or node_id),
                    nodeType=self._to_text(row.get("node_type")) or None,
                )
            )
        return nodes

    def _normalize_row_keys(self, row: dict[str, Any]) -> dict[str, Any]:
        return {str(key).lower(): value for key, value in row.items()}

    def _map_weaver_field_type(self, row: dict[str, Any]) -> str:
        html_type = self._to_text(row.get("field_html_type"))
        field_type = self._to_text(row.get("field_type"))
        db_type = self._to_text(row.get("field_db_type")).lower()
        if "date" in db_type or field_type in {"2", "19", "290"}:
            return "date"
        if any(token in db_type for token in ("int", "decimal", "double", "float")) and html_type == "1":
            return "number"
        if html_type == "4":
            return "checkbox"
        if html_type == "5":
            return "select"
        if html_type == "6":
            return "attachment"
        if html_type == "3":
            return "browser"
        if html_type == "1" and field_type in {"2", "3"}:
            return "textarea"
        return "text"

    def _to_text(self, value: Any) -> str:
        return "" if value is None else str(value)

    def _to_int(self, value: Any) -> int | None:
        try:
            return int(value)
        except Exception:
            return None

    async def chat(self, request: WeaverAssistantChatRequest) -> WeaverAssistantChatResponse:
        if not request.message.strip():
            return WeaverAssistantChatResponse(message="请输入需要我协助填写的内容。", actions=[])

        all_fields, writable_fields = self._split_context_fields(request)
        workflow_rules = await self._load_workflow_rules(request)

        try:
            result = await self._invoke_llm(request, all_fields, writable_fields, workflow_rules)
            return self._normalize_response(result, request, all_fields, writable_fields)
        except Exception as exc:
            logger.warning(f"泛微流程 AI 助手模型调用失败: {LLMFactory.describe_invocation_error(exc)}")
            if not writable_fields:
                return WeaverAssistantChatResponse(
                    message="我可以先帮你梳理填写思路。当前还没有拿到可写字段，所以暂时不会直接写入表单；字段加载完成后，我会给出可确认的写入建议。",
                    actions=[],
                )
            return self._fallback_response(request, writable_fields)

    async def stream_chat(self, request: WeaverAssistantChatRequest) -> AsyncIterator[str]:
        if not request.message.strip():
            yield self._sse("message_delta", {"delta": "请输入需要我协助填写的内容。"})
            yield self._sse("actions", {"actions": []})
            yield self._sse("done", {})
            return

        all_fields, writable_fields = self._split_context_fields(request)
        workflow_rules = await self._load_workflow_rules(request)
        visible_chunks: list[str] = []

        try:
            action_payload_text = ""
            async for item in self._stream_assistant_message(request, all_fields, writable_fields, workflow_rules):
                if item["type"] == "message_delta":
                    delta = item["delta"]
                    visible_chunks.append(delta)
                    yield self._sse("message_delta", {"delta": delta})
                elif item["type"] == "action_payload":
                    action_payload_text = item["delta"]
            visible_message = "".join(visible_chunks).strip()
            result = self._parse_stream_action_payload(action_payload_text)
            result["message"] = visible_message or str(result.get("message") or "已生成填单建议，请确认后写入。")
            response = self._normalize_response(result, request, all_fields, writable_fields)
        except Exception as exc:
            logger.warning(f"泛微流程 AI 助手流式动作生成失败，准备回退: {LLMFactory.describe_invocation_error(exc)}")
            response = (
                WeaverAssistantChatResponse(
                    message="我可以先帮你梳理填写思路。当前还没有拿到可写字段，所以暂时不会直接写入表单；字段加载完成后，我会给出可确认的写入建议。",
                    actions=[],
                )
                if not writable_fields
                else self._fallback_response(request, writable_fields)
            )

        if not visible_chunks:
            for delta in self._split_stream_message(response.message):
                yield self._sse("message_delta", {"delta": delta})
                await asyncio.sleep(0)

        actions = [action.model_dump(exclude_none=True, by_alias=True) for action in response.actions]
        yield self._sse("actions", {"actions": actions})
        yield self._sse("done", {})

    def _split_stream_message(self, message: str) -> list[str]:
        text = message or "已处理完成。"
        chunks: list[str] = []
        buffer = ""
        for char in text:
            buffer += char
            if char in "。！？；\n" or len(buffer) >= 24:
                chunks.append(buffer)
                buffer = ""
        if buffer:
            chunks.append(buffer)
        return chunks

    def _split_context_fields(self, request: WeaverAssistantChatRequest) -> tuple[dict[str, Any], dict[str, Any]]:
        writable_fields = {
            key: field
            for key, field in request.context.fields.items()
            if field.writable and field.visible is not False and field.field_id
        }
        all_fields = {
            key: field
            for key, field in request.context.fields.items()
            if field.field_id
        }
        return all_fields, writable_fields

    async def _load_workflow_rules(self, request: WeaverAssistantChatRequest) -> list[dict[str, Any]]:
        workflow_id = request.context.base_info.get("workflowid") or request.context.base_info.get("workflowId")
        try:
            rules = await weaver_workflow_rule_service.load_enabled_rules_for_prompt(request.context.env, str(workflow_id or ""))
            logger.info(
                "泛微流程 AI 助手加载流程规则: "
                f"env={request.context.env}, workflow_id={workflow_id}, rules={len(rules)}"
            )
            return rules
        except Exception as exc:
            logger.warning(
                "泛微流程 AI 助手读取流程规则失败，已忽略: "
                f"env={request.context.env}, workflow_id={workflow_id}, error={exc}"
            )
            return []

    async def _stream_assistant_message(
        self,
        request: WeaverAssistantChatRequest,
        all_fields: dict[str, Any],
        writable_fields: dict[str, Any],
        workflow_rules: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[dict[str, str]]:
        prompt_payload = self._build_prompt_payload(request, all_fields, writable_fields, workflow_rules)
        field_policy = (
            "当前已提供表单字段状态。你必须参考 writable、required、currentValue 和历史对话。"
            "只能围绕当前 visible=true 且 writable=true 的字段给出可写入建议；隐藏字段、不可编辑字段可能属于后续审批节点或系统自动带出，不要要求用户填写。"
            "字段的 effectiveValue 是优先使用 displayValue 后再回退 currentValue 的可读值，应以 effectiveValue 判断字段是否已有内容。"
            "下拉字段会提供 options，用户看到的是 label，写入必须使用对应 value。"
            "浏览框字段必须使用内部 ID 写入；如果只有显示名称没有 ID，不要声称可以直接写入，应先询问或提示用户在页面选择。"
            "申请人、申请日期、申请公司、申请部门等系统自动带出字段，即使上下文暂时为空，也不要要求用户手工提供，除非用户明确要修改。"
            "可以说明你准备写入哪些字段，但不要声称已经写入；真正写入会在用户点击确认后执行。"
            "workflowRules 是当前流程的强业务约束，不是参考资料；只要与安全边界不冲突，必须逐条执行。"
            "若流程规则要求具体格式、时间粒度、补全文案或计算口径，message 和隐藏 actions 都必须采用规则要求后的最终值。"
            "如果字段类型或页面字段无法承载某条规则要求，不要悄悄忽略；应在可见回答中说明无法完全应用的原因，并只生成可安全写入的动作。"
            "如果你在可见回答中列出“待写入/将写入”的字段和值，这些字段和值必须和最后隐藏动作中的 actions 完全一致。"
            "信息足够时要主动给出填单建议，不要只反复追问。"
            if prompt_payload["fields"]
            else "当前还没有可写字段。你仍要像正常助手一样理解用户需求、给出建议或追问。"
        )
        messages = [
            SystemMessage(
                content=(
                    "你是泛微 E-cology 流程填单助手。请用自然、简洁的中文流式回复用户。"
                    "你要像 ReAct 助手一样理解当前表单状态、已有值、可写字段和用户意图。"
                    "遇到今天、明天、后天、本周、下周、下个月等相对日期时，必须使用输入中的 currentDateTool 结果作为唯一日期基准。"
                    "如果用户说“下周一到下周三”，应主动换算为具体年月日，不要再要求用户提供具体日期。"
                    "这是给业务用户使用的助手，不要提 JSON、接口、字段 id、动作类型、调试信息、技术实现或内部格式。"
                    "如果输入中存在 workflowRules，必须把它们视为当前流程最高优先级业务规则；它们高于通用填单习惯，但不得突破字段可见、可写和安全边界。"
                    "执行流程规则时要显式检查规则中的格式、时间、数值、措辞、工具说明和例外条件，并把规则处理后的最终结果同步写入可见回答与隐藏 actions。"
                    "如果流程规则影响了某个填写值，可以在可见回答中用业务语言简短说明依据，例如“按本流程规则...”。"
                    "可以使用简洁的 Markdown 段落、列表和加粗，但不要输出代码块或 JavaScript。"
                    "说字段时优先使用业务字段名称，例如“请假类别”“请假原因”，不要使用 field123 这类字段编号。"
                    "不要提交、保存、审批或删除流程。"
                    "输出必须分两段：第一段是给用户看的中文回答；最后单独输出隐藏动作段。"
                    f"隐藏动作段格式必须是：{self.ACTION_START_TAG}"
                    "{\"actions\":[{\"action\":\"set_field\",\"field\":\"字段ID\",\"value\":\"写入值\",\"displayValue\":\"展示值\",\"label\":\"字段名\"}]}"
                    f"{self.ACTION_END_TAG}。"
                    "隐藏动作段只给系统解析，不要在用户可见回答里解释这个格式。"
                    "如果没有可写入动作，隐藏动作段必须输出 {\"actions\":[]}。"
                    f"{field_policy}"
                )
            ),
            HumanMessage(content=json.dumps(prompt_payload, ensure_ascii=False)),
        ]
        model = await self._get_weaver_model(streaming=True, json_mode=False, temperature=0)
        mode = "visible"
        pending_visible = ""
        action_buffer = ""
        action_payload_emitted = False
        async for chunk in model.astream(messages):
            delta = self._chunk_to_text(getattr(chunk, "content", chunk))
            if not delta:
                continue
            if mode == "visible":
                pending_visible += delta
                start_index = pending_visible.find(self.ACTION_START_TAG)
                if start_index >= 0:
                    visible_delta = pending_visible[:start_index]
                    if visible_delta:
                        yield {"type": "message_delta", "delta": visible_delta}
                    action_buffer += pending_visible[start_index + len(self.ACTION_START_TAG) :]
                    pending_visible = ""
                    mode = "actions"
                    end_index = action_buffer.find(self.ACTION_END_TAG)
                    if end_index >= 0:
                        if not action_payload_emitted:
                            yield {"type": "action_payload", "delta": action_buffer[:end_index]}
                            action_payload_emitted = True
                        mode = "done"
                        continue
                    continue

                keep_length = len(self.ACTION_START_TAG) - 1
                if len(pending_visible) > keep_length:
                    visible_delta = pending_visible[:-keep_length]
                    pending_visible = pending_visible[-keep_length:]
                    if visible_delta:
                        yield {"type": "message_delta", "delta": visible_delta}
            elif mode == "actions":
                action_buffer += delta
                end_index = action_buffer.find(self.ACTION_END_TAG)
                if end_index >= 0:
                    if not action_payload_emitted:
                        yield {"type": "action_payload", "delta": action_buffer[:end_index]}
                        action_payload_emitted = True
                    mode = "done"
                    continue
            elif mode == "done":
                continue

        if mode == "visible":
            if pending_visible and not pending_visible.strip().startswith("<WEAVER"):
                yield {"type": "message_delta", "delta": pending_visible}
            if not action_payload_emitted:
                yield {"type": "action_payload", "delta": "{\"actions\":[]}"}
        elif mode == "actions" and not action_payload_emitted:
            yield {"type": "action_payload", "delta": action_buffer}

    def _parse_stream_action_payload(self, content: str) -> dict[str, Any]:
        text = (content or "").strip()
        if not text:
            return {"actions": []}
        try:
            payload = self._parse_json_content(text)
        except Exception as exc:
            logger.warning(f"泛微流程 AI 助手解析流式隐藏动作失败，已忽略动作: {exc}, content={text[:300]}")
            return {"actions": []}
        if isinstance(payload, list):
            return {"actions": payload}
        if isinstance(payload, dict):
            actions = payload.get("actions")
            return {"actions": actions if isinstance(actions, list) else []}
        return {"actions": []}

    def _chunk_to_text(self, content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    text = item.get("text") or item.get("content")
                    if text:
                        parts.append(str(text))
            return "".join(parts)
        return "" if content is None else str(content)

    def _sse(self, event: str, data: dict[str, Any]) -> str:
        return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    def _load_field_configs(self) -> dict[str, Any]:
        raw_value = (settings.WEAVER_AI_FIELD_CONFIGS or "").strip()
        if not raw_value:
            return {}
        try:
            parsed = json.loads(raw_value)
            if isinstance(parsed, dict):
                return parsed
        except Exception as exc:
            logger.warning(f"泛微流程 AI 助手字段配置解析失败: {exc}")
        return {}

    def _normalize_field_config(self, raw_fields: Any) -> list[WeaverFieldConfigItem]:
        if isinstance(raw_fields, dict):
            iterable = []
            for biz_key, item in raw_fields.items():
                if isinstance(item, str):
                    iterable.append({"bizKey": biz_key, "label": biz_key, "fieldId": item})
                elif isinstance(item, dict):
                    iterable.append({"bizKey": biz_key, **item})
        elif isinstance(raw_fields, list):
            iterable = raw_fields
        else:
            iterable = []

        fields: list[WeaverFieldConfigItem] = []
        for item in iterable:
            if not isinstance(item, dict):
                continue
            biz_key = item.get("bizKey") or item.get("biz_key") or item.get("key") or item.get("fieldId")
            field_id = item.get("fieldId") or item.get("field_id")
            if not biz_key or not field_id:
                continue
            fields.append(
                WeaverFieldConfigItem(
                    bizKey=str(biz_key),
                    label=str(item.get("label") or biz_key),
                    fieldId=str(field_id),
                    type=str(item.get("type") or "text"),
                    writable=item.get("writable", True) is not False,
                    options=self._normalize_options(item.get("options")),
                    browserType=self._to_text(item.get("browserType") or item.get("browser_type")) or None,
                    fieldType=self._to_text(item.get("fieldType") or item.get("field_type")) or None,
                )
            )
        return fields

    def _normalize_options(self, raw_options: Any) -> list[WeaverFieldOptionItem]:
        if not isinstance(raw_options, list):
            return []
        options: list[WeaverFieldOptionItem] = []
        for item in raw_options:
            if not isinstance(item, dict):
                continue
            value = self._to_text(item.get("value"))
            label = self._to_text(item.get("label") or item.get("name") or value)
            if not value and not label:
                continue
            options.append(
                WeaverFieldOptionItem(
                    value=value,
                    label=label,
                    disabled=item.get("disabled", False) is True,
                )
            )
        return options

    async def _invoke_llm(
        self,
        request: WeaverAssistantChatRequest,
        all_fields: dict[str, Any],
        writable_fields: dict[str, Any],
        workflow_rules: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        prompt_payload = self._build_prompt_payload(request, all_fields, writable_fields, workflow_rules)
        field_policy = (
            "当前已提供表单字段状态。你必须先参考字段 writable、required、currentValue 和历史对话。"
            "只能对当前 visible=true 且 writable=true 的字段生成动作；隐藏字段、不可编辑字段、后续审批字段、系统带出字段都不得生成写入动作。"
            "字段的 effectiveValue 是优先使用 displayValue 后再回退 currentValue 的可读值，应以 effectiveValue 判断字段是否已有内容。"
            "只能对 writable=true 且在 writableFieldIds 内的字段生成 set_field；"
            "对 select 下拉字段，set_field.value 必须使用 options 中的 value，message 可以展示 options 中的 label。"
            "对 browser 浏览框字段，set_field.value 必须是内部 ID；如需展示名称，可额外返回 displayValue 和 specialObj=[{\"id\":\"...\",\"name\":\"...\"}]。"
            "如果浏览框只有名称没有 ID，不要生成 set_field。"
            "只读字段和已有值字段可以作为上下文参考，但不得覆盖，除非用户明确要求且字段可写。"
            "申请人、申请日期、申请公司、申请部门等系统自动带出字段不是填单阻塞项，不要因为这些字段为空就追问用户，也不要生成写入动作。"
            "workflowRules 是当前流程的强业务约束，不是参考资料；只要与字段可见、可写和安全边界不冲突，必须逐条执行。"
            "若流程规则要求具体格式、时间粒度、补全文案或计算口径，message 和 actions 都必须采用规则要求后的最终值。"
            "如果字段类型或页面字段无法承载某条规则要求，不要悄悄忽略；应在 message 中说明无法完全应用的原因，并只生成可安全写入的动作。"
            "如果用户说“确认”“就这样”等，要结合 history 中最近的用户意图继续生成可确认写入动作。"
            "遇到相对日期时，必须用 currentDateTool 中的 today/weekday/relativeDateExamples 换算成具体 YYYY-MM-DD 日期。"
            "如果用户已经给出“今天、明天、下周一”这类可换算时间，不要再追问具体年月日。"
            "信息足够时应主动生成 set_field 动作，不要只反复追问。"
            if prompt_payload["fields"]
            else "当前还没有可写字段。你仍要像正常助手一样理解用户需求、给出建议或追问；actions 必须返回空数组。"
        )
        messages = [
            SystemMessage(
                content=(
                    "你是泛微 E-cology 流程填单助手，采用 ReAct 风格工作：先理解用户意图和当前流程上下文，"
                    "再判断是否需要追问、给建议，或生成可确认的表单写入动作。"
                    "你只能输出 JSON，不要输出 Markdown。"
                    "返回格式必须是 {\"message\":\"...\",\"actions\":[...]}。"
                    "actions 只允许 set_field、add_detail_row、show_message。"
                    "set_field 必须使用输入字段列表中的 fieldId，不得编造字段。"
                    "message 中展示的拟写入字段和值必须与 actions 完全一致；不要在 message 中展示未进入 actions 的写入值。"
                    "不要生成 JavaScript，不要提交、保存、审批或删除流程。"
                    "如果输入中存在 workflowRules，必须把它们视为当前流程最高优先级业务规则；它们高于通用填单习惯，但不得突破字段可见、可写和安全边界。"
                    "执行流程规则时要显式检查规则中的格式、时间、数值、措辞、工具说明和例外条件，并把规则处理后的最终结果同步写入 message 与 actions。"
                    "如果信息不足，只返回自然语言建议或 show_message，不要硬填。"
                    f"{field_policy}"
                )
            ),
            HumanMessage(content=json.dumps(prompt_payload, ensure_ascii=False)),
        ]
        response = await self._invoke_weaver_model(messages, json_mode=True, temperature=0)
        content = getattr(response, "content", response)
        return self._parse_json_content(str(content))

    async def _get_weaver_model(
        self,
        *,
        streaming: bool,
        json_mode: bool,
        temperature: float = 0,
    ) -> Any:
        model_name = (settings.WEAVER_AI_MODEL_NAME or "").strip()
        if model_name:
            logger.info(f"泛微流程 AI 助手使用指定模型: {model_name}")
            return await LLMFactory.get_model_by_name(
                model_name,
                temperature=temperature,
                streaming=streaming,
                json_mode=json_mode,
                enable_reasoning=settings.WEAVER_AI_ENABLE_REASONING,
            )
        capability = self._model_capability()
        logger.info(f"泛微流程 AI 助手使用能力模型: capability={capability}")
        return await LLMFactory.get_model(
            capability=capability,
            temperature=temperature,
            streaming=streaming,
            json_mode=json_mode,
            enable_reasoning=settings.WEAVER_AI_ENABLE_REASONING,
        )

    async def _invoke_weaver_model(
        self,
        messages: list[Any],
        *,
        json_mode: bool,
        temperature: float = 0,
    ) -> Any:
        model_name = (settings.WEAVER_AI_MODEL_NAME or "").strip()
        if model_name:
            logger.info(f"泛微流程 AI 助手使用指定模型: {model_name}")
            model = await LLMFactory.get_model_by_name(
                model_name,
                temperature=temperature,
                streaming=False,
                json_mode=json_mode,
                enable_reasoning=settings.WEAVER_AI_ENABLE_REASONING,
            )
            return await model.ainvoke(messages)
        capability = self._model_capability()
        logger.info(f"泛微流程 AI 助手使用能力模型: capability={capability}")
        return await LLMFactory.safe_invoke(
            messages,
            capability=capability,
            temperature=temperature,
            json_mode=json_mode,
            enable_reasoning=settings.WEAVER_AI_ENABLE_REASONING,
        )

    def _model_capability(self) -> str:
        return (settings.WEAVER_AI_MODEL_CAPABILITY or "complex-reasoning").strip() or "complex-reasoning"

    def _build_prompt_payload(
        self,
        request: WeaverAssistantChatRequest,
        all_fields: dict[str, Any],
        writable_fields: dict[str, Any],
        workflow_rules: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        field_summary = []
        for key, field in all_fields.items():
            effective_value = self._effective_field_value(field)
            field_summary.append(
                {
                    "bizKey": key,
                    "label": field.label,
                    "fieldId": field.field_id,
                    "type": field.type,
                    "writable": field.writable,
                    "required": field.required,
                    "visible": field.visible,
                    "options": [
                        {"value": option.value, "label": option.label}
                        for option in getattr(field, "options", [])
                        if not option.disabled
                    ],
                    "browserType": field.browser_type,
                    "currentValue": field.value,
                    "displayValue": field.display_value,
                    "effectiveValue": effective_value,
                    "hasValue": effective_value not in (None, ""),
                    "readonlyReason": field.readonly_reason,
                    "systemAutoField": self._is_system_auto_field(field),
                }
            )
        history_summary = [
            {"role": item.role, "content": item.content}
            for item in request.history[-10:]
            if item.content.strip()
        ]
        return {
            "userMessage": request.message,
            "history": history_summary,
            "baseInfo": request.context.base_info,
            "url": request.context.url,
            "currentDateTool": self._get_current_date_tool_result(),
            "workflowRules": workflow_rules or [],
            "fields": field_summary,
            "writableFieldIds": [field.field_id for field in writable_fields.values()],
        }

    def _effective_field_value(self, field: Any) -> Any:
        display_value = getattr(field, "display_value", None)
        if display_value not in (None, "") and not self._is_placeholder_value(display_value, field):
            return display_value
        if self._is_placeholder_value(field.value, field):
            return ""
        return field.value

    def _is_placeholder_value(self, value: Any, field: Any | None = None) -> bool:
        text = self._to_text(value).strip()
        if not text:
            return False
        placeholders = {"简要说明请假事由", "请输入", "请选择", "undefined"}
        if text in placeholders:
            return True
        field_text = ""
        if field is not None:
            field_text = f"{getattr(field, 'label', '')} {getattr(field, 'field_id', '')}"
        return bool(re.search(r"原因|事由|说明", field_text) and text.startswith("简要说明"))

    def _is_system_auto_field(self, field: Any) -> bool:
        text = f"{field.label} {field.field_id}".lower()
        keywords = ("申请人", "申请日期", "申请公司", "申请部门", "创建人", "创建日期", "所属公司", "所属部门")
        return any(keyword.lower() in text for keyword in keywords)

    def _get_current_date_tool_result(self) -> dict[str, Any]:
        now = datetime.now(ZoneInfo(self.DATE_TOOL_TIMEZONE))
        today = now.date()
        weekday_names = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
        monday = today - timedelta(days=today.weekday())
        next_monday = monday + timedelta(days=7)
        return {
            "toolName": "current_date",
            "timezone": self.DATE_TOOL_TIMEZONE,
            "now": now.strftime("%Y-%m-%d %H:%M:%S"),
            "today": today.isoformat(),
            "weekday": weekday_names[today.weekday()],
            "relativeDateExamples": {
                "今天": today.isoformat(),
                "明天": (today + timedelta(days=1)).isoformat(),
                "后天": (today + timedelta(days=2)).isoformat(),
                "本周一": monday.isoformat(),
                "本周日": (monday + timedelta(days=6)).isoformat(),
                "下周一": next_monday.isoformat(),
                "下周三": (next_monday + timedelta(days=2)).isoformat(),
                "下周日": (next_monday + timedelta(days=6)).isoformat(),
            },
        }

    def _parse_json_content(self, content: str) -> dict[str, Any]:
        text = content.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?", "", text, flags=re.IGNORECASE).strip()
            text = re.sub(r"```$", "", text).strip()
        return json.loads(text)

    def _normalize_response(
        self,
        payload: dict[str, Any],
        request: WeaverAssistantChatRequest,
        all_fields: dict[str, Any],
        writable_fields: dict[str, Any],
    ) -> WeaverAssistantChatResponse:
        allowed_field_ids = {field.field_id for field in writable_fields.values()}
        field_lookup = self._build_field_lookup(all_fields)
        actions: list[WeaverAssistantAction] = []
        for raw_action in payload.get("actions") or []:
            action_type = raw_action.get("type") or raw_action.get("action")
            if action_type == "set_field":
                field_ref = raw_action.get("field") or raw_action.get("fieldId") or raw_action.get("field_id")
                field_id = self._resolve_field_ref(field_ref, field_lookup)
                if field_id not in allowed_field_ids:
                    continue
                field = self._find_field_by_id(all_fields, field_id)
                normalized_action = self._normalize_set_field_action(raw_action, field, request.context.env)
                if not normalized_action:
                    continue
                label = raw_action.get("label") or getattr(field, "label", None)
                actions.append(
                    WeaverAssistantAction(
                        type="set_field",
                        field=field_id,
                        value=normalized_action["value"],
                        displayValue=normalized_action.get("displayValue"),
                        specialObj=normalized_action.get("specialObj"),
                        label=label,
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

    def _build_field_lookup(self, fields: dict[str, Any]) -> dict[str, str]:
        lookup: dict[str, str] = {}
        for key, field in fields.items():
            for value in (key, field.field_id, field.label):
                normalized = self._normalize_field_ref(value)
                if normalized:
                    lookup[normalized] = field.field_id
        return lookup

    def _resolve_field_ref(self, value: Any, lookup: dict[str, str]) -> str:
        text = "" if value is None else str(value)
        if text in lookup.values():
            return text
        return lookup.get(self._normalize_field_ref(text), text)

    def _normalize_field_ref(self, value: Any) -> str:
        return re.sub(r"\s+", "", "" if value is None else str(value)).lower()

    def _find_field_by_id(self, fields: dict[str, Any], field_id: str) -> Any | None:
        for field in fields.values():
            if field.field_id == field_id:
                return field
        return None

    def _normalize_set_field_action(
        self,
        raw_action: dict[str, Any],
        field: Any | None,
        weaver_env: str | None = None,
    ) -> dict[str, Any] | None:
        raw_value = raw_action.get("value", "")
        display_value = raw_action.get("displayValue") or raw_action.get("display_value")
        if not field:
            return {"value": raw_value, "displayValue": display_value}

        if field.type == "select":
            option = self._resolve_option(field, raw_value)
            if option:
                return {"value": option.value, "displayValue": option.label}
            logger.warning(
                "泛微流程 AI 助手跳过无法匹配选项的下拉写入: "
                f"field={field.field_id}, label={field.label}, value={raw_value}"
            )
            return None

        if field.type == "browser":
            special_obj = raw_action.get("specialObj") or raw_action.get("special_obj")
            normalized_special_obj = self._normalize_special_obj(raw_value, display_value, special_obj)
            if not normalized_special_obj:
                normalized_special_obj = self._resolve_browser_special_obj(field, raw_value, display_value, weaver_env)
            if not normalized_special_obj:
                logger.warning(
                    "泛微流程 AI 助手跳过缺少内部 ID 的浏览框写入: "
                    f"field={field.field_id}, label={field.label}, value={raw_value}, displayValue={display_value}"
                )
                return None
            return {
                "value": ",".join(item["id"] for item in normalized_special_obj),
                "displayValue": ",".join(item["name"] for item in normalized_special_obj if item.get("name")),
                "specialObj": normalized_special_obj,
            }

        return {"value": raw_value, "displayValue": display_value}

    def _resolve_option(self, field: Any, value: Any) -> WeaverFieldOptionItem | None:
        text = self._normalize_field_ref(value)
        if not text:
            return None
        for option in getattr(field, "options", []):
            if option.disabled:
                continue
            option_value = self._normalize_field_ref(option.value)
            option_label = self._normalize_field_ref(option.label)
            if text in {option_value, option_label}:
                return option
            if option_label and (text in option_label or option_label in text):
                return option
        return None

    def _normalize_special_obj(
        self,
        raw_value: Any,
        display_value: Any,
        special_obj: Any,
    ) -> list[dict[str, str]] | None:
        if isinstance(special_obj, list):
            items = []
            for item in special_obj:
                if not isinstance(item, dict):
                    continue
                item_id = self._to_text(item.get("id") or item.get("value"))
                item_name = self._to_text(item.get("name") or item.get("label") or display_value)
                if item_id:
                    items.append({"id": item_id, "name": item_name or item_id})
            if items:
                return items

        raw_text = self._to_text(raw_value).strip()
        if not raw_text:
            return None
        if not re.fullmatch(r"\d+(?:\s*,\s*\d+)*", raw_text):
            return None
        ids = [item.strip() for item in raw_text.split(",") if item.strip()]
        if not ids:
            return None
        names = [item.strip() for item in self._to_text(display_value).split(",") if item.strip()]
        return [
            {
                "id": item_id,
                "name": names[index] if index < len(names) else item_id,
            }
            for index, item_id in enumerate(ids)
        ]

    def _resolve_browser_special_obj(
        self,
        field: Any,
        raw_value: Any,
        display_value: Any,
        weaver_env: str | None,
    ) -> list[dict[str, str]] | None:
        keyword = self._to_text(display_value or raw_value).strip()
        if not keyword:
            return None
        browser_type = self._to_text(getattr(field, "browser_type", None))
        resolver = self._browser_resolver_sql(browser_type)
        if not resolver:
            return None
        env_key = self._normalize_env(weaver_env)
        db_config = self._get_weaver_db_config(env_key)
        if not db_config:
            return None
        sql, params = resolver(keyword)
        try:
            with self._connect_weaver_mysql(db_config) as conn:
                with conn.cursor() as cursor:
                    rows = self._fetch_all(cursor, sql, params)
        except Exception as exc:
            logger.warning(
                "泛微流程 AI 助手解析浏览框内部 ID 失败: "
                f"env={env_key}, field={field.field_id}, browserType={browser_type}, keyword={keyword}, error={exc}"
            )
            return None
        if len(rows) != 1:
            logger.warning(
                "泛微流程 AI 助手浏览框内部 ID 非唯一或不存在，已跳过写入: "
                f"env={env_key}, field={field.field_id}, browserType={browser_type}, keyword={keyword}, matches={len(rows)}"
            )
            return None
        row = rows[0]
        item_id = self._to_text(row.get("id"))
        item_name = self._to_text(row.get("name") or keyword)
        return [{"id": item_id, "name": item_name}] if item_id else None

    def _browser_resolver_sql(self, browser_type: str):
        if browser_type in {"1", "17"}:
            return lambda keyword: (
                """
                SELECT id, lastname AS name
                FROM hrmresource
                WHERE lastname = %s OR workcode = %s OR loginid = %s
                LIMIT 2
                """,
                (keyword, keyword, keyword),
            )
        if browser_type in {"4", "57"}:
            return lambda keyword: (
                """
                SELECT id, departmentname AS name
                FROM hrmdepartment
                WHERE departmentname = %s
                LIMIT 2
                """,
                (keyword,),
            )
        if browser_type in {"164", "194"}:
            return lambda keyword: (
                """
                SELECT id, subcompanyname AS name
                FROM hrmsubcompany
                WHERE subcompanyname = %s
                LIMIT 2
                """,
                (keyword,),
            )
        return None

    def _build_rule_based_actions(
        self,
        request: WeaverAssistantChatRequest,
        all_fields: dict[str, Any],
        writable_fields: dict[str, Any],
    ) -> list[WeaverAssistantAction]:
        if not writable_fields:
            return []

        text = self._conversation_text_for_action(request)
        if not self._looks_like_fill_request(text):
            return []

        slots = self._extract_leave_slots(text)
        if not any(value not in (None, "") for value in slots.values()):
            return []

        actions: list[WeaverAssistantAction] = []
        self._append_slot_action(actions, writable_fields, ("请假类别", "假别", "类型"), slots.get("leave_type"))
        self._append_slot_action(actions, writable_fields, ("开始日期", "请假开始"), slots.get("start_date"))
        self._append_slot_action(actions, writable_fields, ("结束日期", "请假结束"), slots.get("end_date"))
        self._append_slot_action(actions, writable_fields, ("请假天数", "天数", "时长"), slots.get("days"))
        self._append_slot_action(actions, writable_fields, ("请假原因", "原因", "事由", "说明"), slots.get("reason"))
        self._append_slot_action(actions, writable_fields, ("申请日期",), slots.get("apply_date"))

        logger.info(
            "泛微流程 AI 助手使用规则兜底生成写入动作: "
            f"workflow_id={request.context.base_info.get('workflowid') or request.context.base_info.get('workflowId')}, "
            f"actions={len(actions)}, slots={slots}"
        )
        return actions

    def _conversation_text_for_action(self, request: WeaverAssistantChatRequest) -> str:
        pieces = [
            item.content
            for item in request.history[-8:]
            if item.content.strip() and not self._is_pure_apply_command(item.content)
        ]
        pieces.append(request.message)
        return "\n".join(pieces)

    def _is_pure_apply_command(self, text: str) -> bool:
        return bool(re.fullmatch(r"\s*(确认|执行|写入|写入表单|确认写入|可以|就这样|开始写入|帮我写入)\s*", text, re.I))

    def _looks_like_fill_request(self, text: str) -> bool:
        return any(keyword in text for keyword in ("请假", "事假", "病假", "年假", "调休", "下周", "明天", "后天", "原因"))

    def _extract_leave_slots(self, text: str) -> dict[str, Any]:
        date_tool = self._get_current_date_tool_result()
        start_date, end_date = self._extract_date_range(text, date_tool)
        days = self._extract_days(text)
        if days is None and start_date and end_date:
            days = self._inclusive_days(start_date, end_date)
        return {
            "leave_type": self._extract_leave_type(text),
            "start_date": start_date,
            "end_date": end_date,
            "days": days,
            "reason": self._extract_reason(text),
            "apply_date": date_tool["today"],
        }

    def _extract_leave_type(self, text: str) -> str | None:
        labeled_value = self._extract_labeled_value(text, ("请假类别", "假别", "请假类型"))
        if labeled_value:
            for leave_type in ("事假", "病假", "年假", "调休", "婚假", "产假", "陪产假", "丧假"):
                if leave_type in labeled_value:
                    return leave_type
        for leave_type in ("事假", "病假", "年假", "调休", "婚假", "产假", "陪产假", "丧假"):
            if leave_type in text:
                return leave_type
        return None

    def _extract_date_range(self, text: str, date_tool: dict[str, Any]) -> tuple[str | None, str | None]:
        examples = date_tool.get("relativeDateExamples") or {}
        start_value = self._extract_labeled_value(text, ("请假开始日期", "开始日期", "请假开始"))
        end_value = self._extract_labeled_value(text, ("请假结束日期", "结束日期", "请假结束"))
        start_date = self._parse_date_or_relative(start_value, examples)
        end_date = self._parse_date_or_relative(end_value, examples)
        if start_date or end_date:
            return start_date or end_date, end_date or start_date

        if "下周一" in text and ("下周三" in text or "周三" in text):
            return examples.get("下周一"), examples.get("下周三")
        if "下周一" in text and ("下周二" in text or "周二" in text):
            return examples.get("下周一"), self._relative_weekday("下周二")
        if "下周一" in text:
            return examples.get("下周一"), examples.get("下周一")
        if "今天" in text:
            return examples.get("今天"), examples.get("今天")
        if "明天" in text:
            return examples.get("明天"), examples.get("明天")
        if "后天" in text:
            return examples.get("后天"), examples.get("后天")

        dates = re.findall(r"(20\d{2}[-/年.]\d{1,2}[-/月.]\d{1,2})", text)
        normalized_dates = [self._normalize_date_text(value) for value in dates]
        normalized_dates = [value for value in normalized_dates if value]
        if len(normalized_dates) >= 2:
            return normalized_dates[0], normalized_dates[1]
        if len(normalized_dates) == 1:
            return normalized_dates[0], normalized_dates[0]
        return None, None

    def _extract_labeled_value(self, text: str, labels: tuple[str, ...]) -> str | None:
        for label in labels:
            pattern = rf"\*{{0,2}}{re.escape(label)}\*{{0,2}}\s*[：:]\s*([^\n，。,；;]+)"
            match = re.search(pattern, text)
            if match:
                value = match.group(1).strip()
                value = re.sub(r"^\*\*|\*\*$", "", value).strip()
                return value or None
        return None

    def _parse_date_or_relative(self, value: str | None, examples: dict[str, str]) -> str | None:
        if not value:
            return None
        normalized = self._normalize_date_text(value)
        if normalized:
            return normalized
        for key, date_value in examples.items():
            if key in value:
                return date_value
        if "周二" in value:
            return self._relative_weekday("下周二" if "下周" in value else "本周二")
        if "周三" in value:
            return self._relative_weekday("下周三" if "下周" in value else "本周三")
        return None

    def _relative_weekday(self, text: str) -> str | None:
        weekday_map = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}
        match = re.search(r"(本周|下周)?([一二三四五六日天])", text)
        if not match:
            return None
        week_prefix = match.group(1) or "本周"
        weekday = weekday_map.get(match.group(2))
        if weekday is None:
            return None
        today = datetime.now(ZoneInfo(self.DATE_TOOL_TIMEZONE)).date()
        monday = today - timedelta(days=today.weekday())
        if week_prefix == "下周":
            monday += timedelta(days=7)
        return (monday + timedelta(days=weekday)).isoformat()

    def _normalize_date_text(self, value: str) -> str | None:
        parts = re.findall(r"\d+", value)
        if len(parts) < 3:
            return None
        year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
        return f"{year:04d}-{month:02d}-{day:02d}"

    def _extract_days(self, text: str) -> str | None:
        labeled_value = self._extract_labeled_value(text, ("请假天数", "天数", "请假时长", "时长"))
        if labeled_value:
            labeled_match = re.search(r"([0-9]+)", labeled_value)
            if labeled_match:
                return labeled_match.group(1)
        match = re.search(r"([0-9]+)\s*天", text)
        if match:
            return match.group(1)
        chinese_numbers = {
            "一": "1",
            "二": "2",
            "两": "2",
            "三": "3",
            "四": "4",
            "五": "5",
            "六": "6",
            "七": "7",
            "八": "8",
            "九": "9",
            "十": "10",
        }
        match = re.search(r"([一二两三四五六七八九十])\s*天", text)
        return chinese_numbers.get(match.group(1)) if match else None

    def _inclusive_days(self, start_date: str, end_date: str) -> str | None:
        try:
            start = datetime.strptime(start_date, "%Y-%m-%d").date()
            end = datetime.strptime(end_date, "%Y-%m-%d").date()
            return str((end - start).days + 1)
        except Exception:
            return None

    def _extract_reason(self, text: str) -> str | None:
        labeled_value = self._extract_labeled_value(text, ("请假原因", "原因", "事由", "说明"))
        if labeled_value:
            return labeled_value
        match = re.search(r"原因(?:是|为|：|:)?\s*([^，。,.\n]+)", text)
        if match:
            return match.group(1).strip()
        match = re.search(r"(家中[^，。,.\n]+|家里[^，。,.\n]+|个人[^，。,.\n]+|参加[^，。,.\n]+)", text)
        if match:
            return match.group(1).strip()
        for reason in ("家里有事", "身体不适", "生病", "个人事务", "家庭事务"):
            if reason in text:
                return reason
        return None

    def _append_slot_action(
        self,
        actions: list[WeaverAssistantAction],
        writable_fields: dict[str, Any],
        keywords: tuple[str, ...],
        value: Any,
    ) -> None:
        if value in (None, ""):
            return
        field = self._find_field(writable_fields, keywords)
        if not field:
            return
        if self._effective_field_value(field) not in (None, ""):
            return
        normalized_action = self._normalize_set_field_action({"value": value}, field)
        if not normalized_action:
            return
        if any(action.field == field.field_id for action in actions):
            return
        actions.append(
            WeaverAssistantAction(
                type="set_field",
                field=field.field_id,
                value=normalized_action["value"],
                displayValue=normalized_action.get("displayValue"),
                specialObj=normalized_action.get("specialObj"),
                label=field.label,
            )
        )

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
        return f"{normalized[:max_length - 1]}..."


weaver_ai_assistant_service = WeaverAiAssistantService()
