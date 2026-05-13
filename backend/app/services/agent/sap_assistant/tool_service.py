import re
import time
from typing import Any

from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.agent.sap_assistant import SapEvidenceRecord, SapSystemConfig, SapToolCall
from app.schemas.agent.sap_assistant import SapToolEvidence, SapToolResult
from app.services.agent.sap_assistant.rfc_client import sap_rfc_client


class SapToolService:
    _source_cache: dict[str, dict[str, Any]] = {}

    async def execute(
        self,
        db: AsyncSession,
        system: SapSystemConfig | None,
        tool_name: str,
        params: dict[str, Any],
        session_id: int | None = None,
    ) -> SapToolResult:
        started = time.perf_counter()
        tool_call = SapToolCall(
            session_id=session_id,
            sap_system_id=system.id if system else None,
            tool_name=tool_name,
            status="pending",
            request_payload=self._safe_payload(params),
        )
        db.add(tool_call)
        await db.commit()
        await db.refresh(tool_call)

        if not system:
            result = SapToolResult(
                tool_name=tool_name,
                status="skipped",
                summary="未选择 SAP 系统，已跳过 RFC 调用。",
                duration_ms=0,
                evidence=[],
            )
            tool_call.status = "skipped"
            tool_call.response_payload = result.model_dump()
            await db.commit()
            return result

        if tool_name == "source_search":
            result = await self._execute_source_search(system, params, started)
            tool_call.status = result.status
            tool_call.duration_ms = result.duration_ms
            tool_call.response_payload = result.model_dump()
            tool_call.error_message = result.error_message
            await db.commit()
            await db.refresh(tool_call)
            for item in result.evidence:
                db.add(
                    SapEvidenceRecord(
                        session_id=session_id,
                        tool_call_id=tool_call.id,
                        sap_system_id=system.id,
                        evidence_type=item.evidence_type,
                        title=item.title,
                        summary=item.summary,
                        source_object=item.source_object,
                        location=item.location,
                        confidence=item.confidence,
                        content=item.content,
                    )
                )
            await db.commit()
            return result

        function_name = self._function_name(tool_name)
        rfc_result = await sap_rfc_client.call(system, function_name, self._rfc_params(tool_name, params))
        duration_ms = int((time.perf_counter() - started) * 1000)
        if tool_name in {"program_source", "function_source"} and self._is_successful_result(rfc_result):
            self._cache_source_result(system, tool_name, params, rfc_result)
        evidence = self._build_evidence(tool_name, params, rfc_result)

        status = "success" if self._is_successful_result(rfc_result) else "failed"
        result = SapToolResult(
            tool_name=tool_name,
            status=status,
            summary=self._summary(tool_name, rfc_result),
            duration_ms=duration_ms,
            data=rfc_result.get("data") if status == "success" else {"request": self._rfc_params(tool_name, params), "response": rfc_result.get("data")},
            evidence=evidence,
            error_message=None if status == "success" else rfc_result.get("message"),
        )

        tool_call.status = status
        tool_call.duration_ms = duration_ms
        tool_call.response_payload = result.model_dump()
        tool_call.error_message = result.error_message
        await db.commit()
        await db.refresh(tool_call)

        for item in evidence:
            db.add(
                SapEvidenceRecord(
                    session_id=session_id,
                    tool_call_id=tool_call.id,
                    sap_system_id=system.id,
                    evidence_type=item.evidence_type,
                    title=item.title,
                    summary=item.summary,
                    source_object=item.source_object,
                    location=item.location,
                    confidence=item.confidence,
                    content=item.content,
                )
            )
        await db.commit()
        return result

    def _is_successful_result(self, rfc_result: dict[str, Any]) -> bool:
        if not rfc_result.get("success"):
            return False
        data = rfc_result.get("data")
        if isinstance(data, dict):
            parsed = data.get("JSON_PARSED")
            if isinstance(parsed, dict) and parsed.get("success") is False:
                return False
        return True

    def _function_name(self, tool_name: str) -> str:
        mapping = {
            "tcode_info": "ZFM_AI_GET_TCODE_INFO",
            "program_source": "ZFM_AI_GET_PROGRAM_SOURCE",
            "function_source": "ZFM_AI_GET_PROGRAM_SOURCE",
            "ddic_meta": "ZFM_AI_GET_DDIC_META",
            "zilog_logs": "ZFM_AI_QUERY_ZILOG",
            "safe_table_read": "ZFM_AI_READ_TABLE_SAFE",
            "latest_table_read": "ZFM_AI_READ_TABLE_LATEST",
            "ping": "ZFM_AI_PING",
            "source_search": "ZFM_AI_GET_PROGRAM_SOURCE",
        }
        return mapping.get(tool_name, tool_name)

    def _rfc_params(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        def clamp(value: Any, default: int, upper: int) -> int:
            try:
                number = int(value or default)
            except (TypeError, ValueError):
                number = default
            return max(1, min(number, upper))

        if tool_name == "tcode_info":
            return {
                "IV_TCODE": params.get("tcode", ""),
                "IV_QUERY": params.get("query", ""),
                "IV_MAX_ROWS": clamp(params.get("max_rows"), 20, 50),
            }
        if tool_name in {"program_source", "function_source"}:
            return {
                "IV_OBJECT_NAME": str(params.get("object_name", "")),
                "IV_OBJECT_TYPE": "FUNC" if tool_name == "function_source" else "PROG",
                "IV_START_LINE": clamp(params.get("start_line"), 1, 999999),
                "IV_MAX_LINES": 0 if params.get("max_lines") in {None, 0, "0", ""} else clamp(params.get("max_lines"), 220, 5000),
            }
        if tool_name == "source_search":
            return {
                "IV_OBJECT_NAME": str(params.get("object_name", "")),
                "IV_OBJECT_TYPE": str(params.get("object_type") or "PROG"),
                "IV_START_LINE": 1,
                "IV_MAX_LINES": 0,
            }
        if tool_name == "ddic_meta":
            return {"IV_OBJECT_NAME": params.get("object_name", ""), "IV_OBJECT_TYPE": params.get("object_type", "TABL")}
        if tool_name == "zilog_logs":
            return {
                "IV_OBJECT_NAME": params.get("object_name", ""),
                "IV_KEYWORD": params.get("keyword", ""),
                "IV_MAX_ROWS": clamp(params.get("max_rows"), 60, 120),
            }
        if tool_name == "safe_table_read":
            return {
                "IV_TABLE_NAME": params.get("table_name", ""),
                "IT_FIELDS": self._normalize_fields(params.get("fields", [])),
                "IT_RANGES": self._normalize_ranges(params.get("ranges", [])),
                "IV_MAX_ROWS": clamp(params.get("max_rows"), 80, 200),
            }
        if tool_name == "latest_table_read":
            return {
                "IV_TABLE_NAME": params.get("table_name", ""),
                "IT_FIELDS": self._normalize_fields(params.get("fields", [])),
                "IT_RANGES": self._normalize_ranges(params.get("ranges", [])),
                "IT_SORT_FIELDS": self._normalize_sort_fields(params.get("sort_fields", [])),
                "IV_MAX_ROWS": clamp(params.get("max_rows"), 1, 20),
            }
        return params

    def _normalize_fields(self, fields: Any) -> list[dict[str, str]]:
        if not isinstance(fields, list):
            return []
        normalized: list[dict[str, str]] = []
        for field in fields:
            if isinstance(field, str) and field.strip():
                normalized.append({"FIELDNAME": field.strip().upper()})
            elif isinstance(field, dict):
                field_name = str(field.get("FIELDNAME") or field.get("fieldname") or field.get("field_name") or "").strip()
                if field_name:
                    normalized.append({"FIELDNAME": field_name.upper()})
        return normalized

    def _normalize_ranges(self, ranges: Any) -> list[dict[str, str]]:
        if not isinstance(ranges, list):
            return []
        normalized: list[dict[str, str]] = []
        for item in ranges:
            if not isinstance(item, dict):
                continue
            field_name = str(item.get("FIELDNAME") or item.get("fieldname") or item.get("field_name") or "").strip()
            low = str(item.get("LOW") or item.get("low") or "").strip()
            if not field_name or not low:
                continue
            normalized.append(
                {
                    "FIELDNAME": field_name.upper(),
                    "SIGN": str(item.get("SIGN") or item.get("sign") or "I").strip().upper()[:1],
                    "OPTION": str(item.get("OPTION") or item.get("option") or "EQ").strip().upper()[:2],
                    "LOW": low,
                    "HIGH": str(item.get("HIGH") or item.get("high") or "").strip(),
                }
            )
        return normalized

    def _normalize_sort_fields(self, sort_fields: Any) -> list[dict[str, str]]:
        if not isinstance(sort_fields, list):
            return []
        normalized: list[dict[str, str]] = []
        for item in sort_fields:
            if isinstance(item, str):
                field_name = item.strip()
                direction = "DESC"
            elif isinstance(item, dict):
                field_name = str(item.get("FIELDNAME") or item.get("fieldname") or item.get("field_name") or "").strip()
                direction = str(item.get("DIRECTION") or item.get("direction") or item.get("order") or "DESC").strip().upper()
            else:
                continue
            if not field_name:
                continue
            normalized.append({"FIELDNAME": field_name.upper(), "DIRECTION": "ASC" if direction == "ASC" else "DESC"})
        return normalized

    async def _execute_source_search(self, system: SapSystemConfig, params: dict[str, Any], started: float) -> SapToolResult:
        rfc_params = self._rfc_params("source_search", params)
        cached = self._get_cached_source(system, rfc_params)
        rfc_result = cached or await sap_rfc_client.call(system, "ZFM_AI_GET_PROGRAM_SOURCE", rfc_params)
        duration_ms = int((time.perf_counter() - started) * 1000)
        if not self._is_successful_result(rfc_result):
            evidence = self._build_evidence("source_search", params, rfc_result)
            return SapToolResult(
                tool_name="source_search",
                status="failed",
                summary=rfc_result.get("message") or "源码搜索失败",
                duration_ms=duration_ms,
                data={"request": rfc_params, "response": rfc_result.get("data")},
                evidence=evidence,
                error_message=rfc_result.get("message"),
            )

        parsed: dict[str, Any] = {}
        data = rfc_result.get("data")
        if isinstance(data, dict) and isinstance(data.get("JSON_PARSED"), dict):
            parsed = data["JSON_PARSED"]
        lines = parsed.get("lines") if isinstance(parsed, dict) else []
        if not isinstance(lines, list):
            lines = []
        keywords = self._normalize_keywords(params.get("keywords") or params.get("query") or [])
        context_lines = self._to_int(params.get("context_lines"), 6, 12)
        max_matches = self._to_int(params.get("max_matches"), 12, 20)
        matches = self._search_source_lines(lines, keywords, context_lines, max_matches)
        executable_matches = [item for item in matches if item.get("lineKind") == "code"]
        comment_matches = [item for item in matches if item.get("lineKind") == "comment"]
        discovered_calls = self._extract_function_calls(lines)[:20]
        result_data = {
            "object": parsed.get("object") or params.get("object_name"),
            "resolvedProgram": parsed.get("resolvedProgram"),
            "totalLines": parsed.get("totalLines") or len(lines),
            "keywords": keywords,
            "matchCount": len(matches),
            "executableMatchCount": len(executable_matches),
            "commentMatchCount": len(comment_matches),
            "discoveredFunctionCalls": discovered_calls,
            "matches": matches,
        }
        evidence = [
            SapToolEvidence(
                evidence_type="source_search",
                title="源码搜索结果",
                summary=f"在 {result_data['object']} 中按 {len(keywords)} 个关键词命中 {len(matches)} 处，其中可执行代码 {len(executable_matches)} 处、注释 {len(comment_matches)} 处",
                source_object=str(params.get("object_name") or ""),
                location="ZFM_AI_GET_PROGRAM_SOURCE",
                confidence=0.95 if executable_matches else 0.45 if comment_matches else 0.3,
                content=result_data,
            )
        ]
        return SapToolResult(
            tool_name="source_search",
            status="success",
            summary=evidence[0].summary or "源码搜索完成",
            duration_ms=duration_ms,
            data=result_data,
            evidence=evidence,
        )

    def _normalize_keywords(self, raw_keywords: Any) -> list[str]:
        if isinstance(raw_keywords, str):
            text = raw_keywords.replace("，", ",")
            if "," in text:
                items = [item.strip() for item in text.split(",")]
            else:
                items = [item.strip() for item in text.split()]
        elif isinstance(raw_keywords, list):
            items = [str(item).strip() for item in raw_keywords]
        else:
            items = []
        keywords: list[str] = []
        seen_upper: set[str] = set()
        for item in items:
            if not any(ch.isalnum() or "\u4e00" <= ch <= "\u9fff" or ch in {"_", "-"} for ch in item):
                continue
            upper_item = item.upper()
            if item and upper_item not in seen_upper:
                keywords.append(item)
                seen_upper.add(upper_item)
        return keywords[:20]

    def _cache_source_result(self, system: SapSystemConfig, tool_name: str, params: dict[str, Any], rfc_result: dict[str, Any]) -> None:
        data = rfc_result.get("data")
        if not isinstance(data, dict) or not isinstance(data.get("JSON_PARSED"), dict):
            return
        parsed = data["JSON_PARSED"]
        if not isinstance(parsed.get("lines"), list):
            return
        object_type = "FUNC" if tool_name == "function_source" else "PROG"
        object_name = str(parsed.get("object") or parsed.get("resolvedProgram") or params.get("object_name") or "").upper()
        resolved = str(parsed.get("resolvedProgram") or object_name).upper()
        for name in {object_name, resolved}:
            if name:
                self._source_cache[self._source_cache_key(system, name, object_type)] = rfc_result

    def _get_cached_source(self, system: SapSystemConfig, rfc_params: dict[str, Any]) -> dict[str, Any] | None:
        object_name = str(rfc_params.get("IV_OBJECT_NAME") or "").upper()
        object_type = str(rfc_params.get("IV_OBJECT_TYPE") or "PROG").upper()
        return self._source_cache.get(self._source_cache_key(system, object_name, object_type))

    def _source_cache_key(self, system: SapSystemConfig, object_name: str, object_type: str) -> str:
        return f"{system.id}:{system.system_code}:{system.client}:{object_type}:{object_name.upper()}"

    def _search_source_lines(self, lines: list[Any], keywords: list[str], context_lines: int, max_matches: int) -> list[dict[str, Any]]:
        if not keywords:
            return []
        matches: list[dict[str, Any]] = []
        upper_keywords = [keyword.upper() for keyword in keywords]
        for index, line in enumerate(lines):
            text = str(line)
            upper_text = text.upper()
            matched = [keywords[pos] for pos, keyword in enumerate(upper_keywords) if keyword in upper_text]
            if not matched:
                continue
            line_kind = self._classify_abap_line(text)
            begin = max(0, index - context_lines)
            end = min(len(lines), index + context_lines + 1)
            matches.append(
                {
                    "line": index + 1,
                    "lineKind": line_kind,
                    "evidenceStrength": "strong" if line_kind == "code" else "weak",
                    "matchedKeywords": matched,
                    "text": text[:500],
                    "contextRange": [begin + 1, end],
                    "context": [str(item) for item in lines[begin:end]],
                }
            )
            if len(matches) >= max_matches:
                break
        return matches

    def _classify_abap_line(self, line: str) -> str:
        stripped = line.strip()
        if not stripped:
            return "blank"
        if stripped.startswith("*") or stripped.startswith('"'):
            return "comment"
        code_part = stripped.split('"', 1)[0].strip()
        return "code" if code_part else "comment"

    def _extract_function_calls(self, lines: list[Any]) -> list[dict[str, Any]]:
        calls: list[dict[str, Any]] = []
        pending_line: int | None = None
        for index, raw_line in enumerate(lines):
            line = str(raw_line)
            if self._classify_abap_line(line) != "code":
                continue
            code = line.split('"', 1)[0].strip()
            upper = code.upper()
            if "CALL FUNCTION" in upper:
                match = re.search(r"CALL\s+FUNCTION\s+'?([A-Z0-9_/]+)'?", upper)
                if match:
                    calls.append({"function": match.group(1), "line": index + 1, "statement": code[:300]})
                    pending_line = None
                else:
                    pending_line = index + 1
                continue
            if pending_line is not None:
                match = re.search(r"'([A-Z0-9_/]+)'", upper)
                if match:
                    calls.append({"function": match.group(1), "line": pending_line, "statement": code[:300]})
                    pending_line = None
            if len(calls) >= 80:
                break
        return calls

    def _to_int(self, value: Any, default: int, upper: int) -> int:
        try:
            number = int(value or default)
        except (TypeError, ValueError):
            number = default
        return max(1, min(number, upper))

    def _build_evidence(self, tool_name: str, params: dict[str, Any], rfc_result: dict[str, Any]) -> list[SapToolEvidence]:
        data = rfc_result.get("data")
        title_map = {
            "tcode_info": "事务码对象信息",
            "program_source": "ABAP 源码片段",
            "function_source": "RFC/函数源码片段",
            "ddic_meta": "DDIC 结构信息",
            "zilog_logs": "ZILOG 日志记录",
            "safe_table_read": "只读数据样例",
            "latest_table_read": "只读排序数据",
            "ping": "SAP 连接测试",
        }
        return [
            SapToolEvidence(
                evidence_type=self._evidence_type(tool_name),
                title=title_map.get(tool_name, tool_name),
                summary=rfc_result.get("message"),
                source_object=params.get("tcode") or params.get("object_name") or params.get("table_name"),
                location=self._function_name(tool_name),
                confidence=0.9 if rfc_result.get("success") else 0.2,
                content={"data": data, "function": rfc_result.get("function"), "message": rfc_result.get("message")},
            )
        ]

    def _evidence_type(self, tool_name: str) -> str:
        if tool_name in {"program_source", "function_source", "source_search"}:
            return "source"
        if tool_name == "ddic_meta":
            return "ddic"
        if tool_name == "zilog_logs":
            return "log"
        if tool_name in {"safe_table_read", "latest_table_read"}:
            return "data"
        return "sap"

    def _summary(self, tool_name: str, rfc_result: dict[str, Any]) -> str:
        return rfc_result.get("message") or f"{tool_name} 执行完成"

    def _safe_payload(self, params: dict[str, Any]) -> dict[str, Any]:
        return {key: ("***" if "password" in key.lower() else value) for key, value in params.items()}


sap_tool_service = SapToolService()
