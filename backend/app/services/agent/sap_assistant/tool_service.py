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

        if tool_name in {"source_manifest", "source_search", "source_slice"}:
            if tool_name == "source_manifest":
                result = await self._execute_source_manifest(system, params, started)
            elif tool_name == "source_slice":
                result = await self._execute_source_slice(system, params, started)
            else:
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

        guard_message = self._preflight_guard(tool_name, params)
        if guard_message:
            duration_ms = int((time.perf_counter() - started) * 1000)
            rfc_params = self._rfc_params(tool_name, params)
            evidence = [
                SapToolEvidence(
                    evidence_type=self._evidence_type(tool_name),
                    title="工具调用参数需要收窄",
                    summary=guard_message,
                    source_object=params.get("table_name") or params.get("object_name"),
                    location=self._function_name(tool_name),
                    confidence=0.1,
                    content={
                        "request": rfc_params,
                        "strength": "none",
                        "sufficiency": "insufficient",
                        "businessConclusionAllowed": False,
                        "agentHint": guard_message,
                    },
                )
            ]
            result = SapToolResult(
                tool_name=tool_name,
                status="skipped",
                summary=guard_message,
                duration_ms=duration_ms,
                data={
                    "request": rfc_params,
                    "guard": guard_message,
                    "errorType": "safe_table_read_preflight",
                    "businessConclusionAllowed": False,
                },
                evidence=evidence,
                error_message=guard_message,
            )
            tool_call.status = result.status
            tool_call.duration_ms = result.duration_ms
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

        function_name = self._function_name(tool_name)
        rfc_result = await sap_rfc_client.call(system, function_name, self._rfc_params(tool_name, params))
        duration_ms = int((time.perf_counter() - started) * 1000)
        if tool_name in {"program_source", "function_source"} and self._is_successful_result(rfc_result):
            self._cache_source_result(system, tool_name, params, rfc_result)
        evidence = self._build_evidence(tool_name, params, rfc_result)

        status = "success" if self._is_successful_result(rfc_result) else "failed"
        summary = self._rfc_summary(tool_name, rfc_result)
        result = SapToolResult(
            tool_name=tool_name,
            status=status,
            summary=summary,
            duration_ms=duration_ms,
            data=rfc_result.get("data") if status == "success" else self._failed_tool_data(tool_name, params, rfc_result),
            evidence=evidence,
            error_message=None if status == "success" else summary,
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
            if data.get("JSON_PARSE_ERROR"):
                return False
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
            "source_manifest": "ZFM_AI_GET_PROGRAM_SOURCE",
            "source_search": "ZFM_AI_GET_PROGRAM_SOURCE",
            "source_slice": "ZFM_AI_GET_PROGRAM_SOURCE",
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
        if tool_name in {"source_manifest", "source_search", "source_slice"}:
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
                "IV_MAX_ROWS": clamp(params.get("max_rows"), 5, 10),
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

    def _preflight_guard(self, tool_name: str, params: dict[str, Any]) -> str:
        if tool_name != "safe_table_read":
            return ""
        rfc_params = self._rfc_params(tool_name, params)
        fields = rfc_params.get("IT_FIELDS")
        ranges = rfc_params.get("IT_RANGES")
        max_rows = rfc_params.get("IV_MAX_ROWS")
        if not isinstance(fields, list) or not fields:
            return (
                "safe_table_read 已拦截：必须显式指定少量字段，不能空 fields 读取整表宽行。"
                "请先根据源码或 DDIC 选择不超过 8 个必要字段，例如主键、过滤字段和待验证字段。"
            )
        if not isinstance(ranges, list) or not ranges:
            return (
                "safe_table_read 已拦截：必须至少提供一个高选择性的 ranges 条件，优先使用主键或凭证号 EQ。"
                "如只想探查表结构，请先调用 ddic_meta；不要无条件读取业务表样例。"
            )
        if int(max_rows or 0) > 10:
            return "safe_table_read 已拦截：max_rows 不能超过 10；请缩小字段和条件后重试。"
        return ""

    def _normalize_fields(self, fields: Any) -> list[dict[str, str]]:
        if not isinstance(fields, list):
            return []
        normalized: list[dict[str, str]] = []
        seen: set[str] = set()
        for field in fields:
            field_name = ""
            if isinstance(field, str) and field.strip():
                field_name = field.strip()
            elif isinstance(field, dict):
                field_name = str(
                    field.get("FIELDNAME")
                    or field.get("fieldname")
                    or field.get("field_name")
                    or field.get("field")
                    or field.get("name")
                    or ""
                ).strip()
            upper_name = field_name.upper()
            if upper_name and upper_name not in seen:
                normalized.append({"FIELDNAME": upper_name})
                seen.add(upper_name)
            if len(normalized) >= 8:
                break
        return normalized

    def _normalize_ranges(self, ranges: Any) -> list[dict[str, str]]:
        if not isinstance(ranges, list):
            return []
        normalized: list[dict[str, str]] = []
        seen: set[tuple[str, str, str, str, str]] = set()
        for item in ranges:
            if not isinstance(item, dict):
                continue
            field_name = str(
                item.get("FIELDNAME")
                or item.get("fieldname")
                or item.get("field_name")
                or item.get("field")
                or item.get("name")
                or ""
            ).strip()
            low = str(item.get("LOW") or item.get("low") or item.get("value") or "").strip()
            if not field_name or not low:
                continue
            normalized_item = {
                "FIELDNAME": field_name.upper(),
                "SIGN": str(item.get("SIGN") or item.get("sign") or "I").strip().upper()[:1],
                "OPTION": str(item.get("OPTION") or item.get("option") or "EQ").strip().upper()[:2],
                "LOW": low,
                "HIGH": str(item.get("HIGH") or item.get("high") or "").strip(),
            }
            key = (
                normalized_item["FIELDNAME"],
                normalized_item["SIGN"],
                normalized_item["OPTION"],
                normalized_item["LOW"],
                normalized_item["HIGH"],
            )
            if key not in seen:
                normalized.append(normalized_item)
                seen.add(key)
            if len(normalized) >= 8:
                break
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
                field_name = str(
                    item.get("FIELDNAME")
                    or item.get("fieldname")
                    or item.get("field_name")
                    or item.get("field")
                    or item.get("name")
                    or ""
                ).strip()
                direction = str(item.get("DIRECTION") or item.get("direction") or item.get("order") or "DESC").strip().upper()
            else:
                continue
            if not field_name:
                continue
            normalized.append({"FIELDNAME": field_name.upper(), "DIRECTION": "ASC" if direction == "ASC" else "DESC"})
        return normalized

    async def _execute_source_manifest(self, system: SapSystemConfig, params: dict[str, Any], started: float) -> SapToolResult:
        rfc_params = self._rfc_params("source_manifest", params)
        rfc_result = await self._get_or_fetch_source(system, rfc_params)
        duration_ms = int((time.perf_counter() - started) * 1000)
        if not self._is_successful_result(rfc_result):
            evidence = self._build_evidence("source_manifest", params, rfc_result)
            return SapToolResult(
                tool_name="source_manifest",
                status="failed",
                summary=rfc_result.get("message") or "源码清单读取失败",
                duration_ms=duration_ms,
                data={"request": rfc_params, "response": rfc_result.get("data")},
                evidence=evidence,
                error_message=rfc_result.get("message"),
            )
        parsed, lines = self._source_lines_from_rfc(rfc_result)
        object_name = parsed.get("object") or params.get("object_name")
        object_type = str(params.get("object_type") or rfc_params.get("IV_OBJECT_TYPE") or "PROG").upper()
        forms = self._extract_forms(lines)[:80]
        includes = self._extract_includes(lines)[:40]
        discovered_calls = self._extract_function_calls(lines)[:40]
        keyword_index = self._build_keyword_index(lines)[:80]
        result_data = {
            "object": object_name,
            "objectType": object_type,
            "resolvedProgram": parsed.get("resolvedProgram"),
            "totalLines": parsed.get("totalLines") or len(lines),
            "forms": forms,
            "includes": includes,
            "discoveredFunctionCalls": discovered_calls,
            "keywordIndex": keyword_index,
            "nextHint": "优先用 source_search 搜字段、表名、FORM 或函数名；只有需要确认上下文时再用 source_slice 读取最小窗口。",
            "compactNote": "源码全文已缓存在服务层并写入审计，LLM 只接收清单和索引。",
        }
        evidence = [
            SapToolEvidence(
                evidence_type="source_manifest",
                title="源码清单与索引",
                summary=f"已为 {object_name} 建立源码清单：{len(forms)} 个 FORM、{len(includes)} 个 INCLUDE、{len(discovered_calls)} 个函数调用线索",
                source_object=str(params.get("object_name") or ""),
                location="ZFM_AI_GET_PROGRAM_SOURCE",
                confidence=0.75,
                content={**result_data, "strength": "medium", "sufficiency": "needs_executable_slice", "uncertainty": "清单只能定位候选位置，不能单独作为业务结论。"},
            )
        ]
        return SapToolResult(
            tool_name="source_manifest",
            status="success",
            summary=evidence[0].summary or "源码清单读取完成",
            duration_ms=duration_ms,
            data=result_data,
            evidence=evidence,
        )

    async def _execute_source_slice(self, system: SapSystemConfig, params: dict[str, Any], started: float) -> SapToolResult:
        rfc_params = self._rfc_params("source_slice", params)
        rfc_result = await self._get_or_fetch_source(system, rfc_params)
        duration_ms = int((time.perf_counter() - started) * 1000)
        if not self._is_successful_result(rfc_result):
            evidence = self._build_evidence("source_slice", params, rfc_result)
            return SapToolResult(
                tool_name="source_slice",
                status="failed",
                summary=rfc_result.get("message") or "源码切片读取失败",
                duration_ms=duration_ms,
                data={"request": rfc_params, "response": rfc_result.get("data")},
                evidence=evidence,
                error_message=rfc_result.get("message"),
            )
        parsed, lines = self._source_lines_from_rfc(rfc_result)
        start_line = self._to_int(params.get("start_line"), 1, 999999)
        max_lines = self._to_int(params.get("max_lines"), 80, 120)
        begin = max(0, start_line - 1)
        end = min(len(lines), begin + max_lines)
        numbered_lines = [{"line": index + 1, "text": str(lines[index])[:500]} for index in range(begin, end)]
        executable_lines = [
            item
            for item in numbered_lines
            if self._classify_abap_line(item["text"]) == "code" and self._looks_like_executable_evidence(item["text"])
        ]
        object_name = parsed.get("object") or params.get("object_name")
        result_data = {
            "object": object_name,
            "objectType": str(params.get("object_type") or rfc_params.get("IV_OBJECT_TYPE") or "PROG").upper(),
            "resolvedProgram": parsed.get("resolvedProgram"),
            "totalLines": parsed.get("totalLines") or len(lines),
            "lineRange": [begin + 1, end],
            "purpose": str(params.get("purpose") or ""),
            "lines": numbered_lines,
            "executableEvidenceLines": executable_lines[:30],
            "evidenceStrength": "strong" if executable_lines else "weak",
            "compactNote": "这是缓存源码的最小必要切片，不包含对象全文。",
        }
        evidence = [
            SapToolEvidence(
                evidence_type="source_slice",
                title="源码可执行片段",
                summary=f"已读取 {object_name} 第 {begin + 1}-{end} 行源码切片，包含 {len(executable_lines)} 行可执行证据候选",
                source_object=str(params.get("object_name") or ""),
                location=f"{begin + 1}-{end}",
                confidence=0.95 if executable_lines else 0.45,
                content={
                    **result_data,
                    "strength": "strong" if executable_lines else "weak",
                    "sufficiency": "candidate_executable_evidence" if executable_lines else "insufficient",
                    "uncertainty": "" if executable_lines else "该切片未出现明确可执行取数、赋值或计算语句。",
                },
            )
        ]
        return SapToolResult(
            tool_name="source_slice",
            status="success",
            summary=evidence[0].summary or "源码切片读取完成",
            duration_ms=duration_ms,
            data=result_data,
            evidence=evidence,
        )

    async def _execute_source_search(self, system: SapSystemConfig, params: dict[str, Any], started: float) -> SapToolResult:
        rfc_params = self._rfc_params("source_search", params)
        rfc_result = await self._get_or_fetch_source(system, rfc_params)
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

        parsed, lines = self._source_lines_from_rfc(rfc_result)
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
                content={
                    **result_data,
                    "strength": "strong" if executable_matches else "weak" if comment_matches else "none",
                    "sufficiency": "candidate_executable_evidence" if executable_matches else "insufficient",
                    "uncertainty": "" if executable_matches else "未命中可执行代码，注释或空结果不能作为最终业务结论。",
                },
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
        object_type = str(params.get("object_type") or ("FUNC" if tool_name == "function_source" else "PROG")).upper()
        object_name = str(parsed.get("object") or parsed.get("resolvedProgram") or params.get("object_name") or "").upper()
        resolved = str(parsed.get("resolvedProgram") or object_name).upper()
        for name in {object_name, resolved}:
            if name:
                self._source_cache[self._source_cache_key(system, name, object_type)] = rfc_result

    async def _get_or_fetch_source(self, system: SapSystemConfig, rfc_params: dict[str, Any]) -> dict[str, Any]:
        cached = self._get_cached_source(system, rfc_params)
        if cached:
            return cached
        rfc_result = await sap_rfc_client.call(system, "ZFM_AI_GET_PROGRAM_SOURCE", rfc_params)
        if self._is_successful_result(rfc_result):
            self._cache_source_result(
                system,
                "function_source" if str(rfc_params.get("IV_OBJECT_TYPE") or "").upper() == "FUNC" else "program_source",
                {
                    "object_name": rfc_params.get("IV_OBJECT_NAME"),
                    "object_type": rfc_params.get("IV_OBJECT_TYPE"),
                },
                rfc_result,
            )
        return rfc_result

    def _source_lines_from_rfc(self, rfc_result: dict[str, Any]) -> tuple[dict[str, Any], list[Any]]:
        parsed: dict[str, Any] = {}
        data = rfc_result.get("data")
        if isinstance(data, dict) and isinstance(data.get("JSON_PARSED"), dict):
            parsed = data["JSON_PARSED"]
        lines = parsed.get("lines") if isinstance(parsed, dict) else []
        if not isinstance(lines, list):
            lines = []
        return parsed, lines

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

    def _extract_forms(self, lines: list[Any]) -> list[dict[str, Any]]:
        forms: list[dict[str, Any]] = []
        open_form: dict[str, Any] | None = None
        for index, raw_line in enumerate(lines):
            upper = str(raw_line).upper()
            form_match = re.search(r"^\s*FORM\s+([A-Z0-9_]+)", upper)
            if form_match:
                open_form = {"name": form_match.group(1), "startLine": index + 1}
                forms.append(open_form)
                continue
            if open_form is not None and re.search(r"^\s*ENDFORM\b", upper):
                open_form["endLine"] = index + 1
                open_form = None
        return forms

    def _extract_includes(self, lines: list[Any]) -> list[dict[str, Any]]:
        includes: list[dict[str, Any]] = []
        for index, raw_line in enumerate(lines):
            match = re.search(r"^\s*INCLUDE\s+([A-Z0-9_]+)", str(raw_line).upper())
            if match:
                includes.append({"include": match.group(1).rstrip("."), "line": index + 1})
        return includes

    def _build_keyword_index(self, lines: list[Any]) -> list[dict[str, Any]]:
        important_tokens = (
            "SELECT",
            "READ TABLE",
            "LOOP AT",
            "CALL FUNCTION",
            "PERFORM",
            "MOVE",
            "APPEND",
            "COLLECT",
            "MODIFY",
            "NETWR",
            "VBRK",
            "VBRP",
            "KONV",
            "PRCD",
            "DMBTR",
            "WRBTR",
            "MENGE",
            "FKIMG",
            "KBETR",
            "KPEIN",
        )
        index: list[dict[str, Any]] = []
        for line_no, raw_line in enumerate(lines, start=1):
            text = str(raw_line)
            upper = text.upper()
            matched = [token for token in important_tokens if token in upper]
            if not matched:
                continue
            line_kind = self._classify_abap_line(text)
            index.append(
                {
                    "line": line_no,
                    "lineKind": line_kind,
                    "evidenceStrength": "strong" if line_kind == "code" and self._looks_like_executable_evidence(text) else "weak",
                    "matchedTokens": matched[:6],
                    "text": text[:260],
                }
            )
            if len(index) >= 160:
                break
        return index

    def _classify_abap_line(self, line: str) -> str:
        stripped = line.strip()
        if not stripped:
            return "blank"
        if stripped.startswith("*") or stripped.startswith('"'):
            return "comment"
        code_part = stripped.split('"', 1)[0].strip()
        return "code" if code_part else "comment"

    def _looks_like_executable_evidence(self, line: str) -> bool:
        upper = line.upper()
        return any(
            token in upper
            for token in (
                "SELECT",
                "READ TABLE",
                "LOOP AT",
                "CALL FUNCTION",
                "PERFORM",
                "MOVE",
                "APPEND",
                "COLLECT",
                "MODIFY",
                " = ",
                "=",
            )
        )

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
        success = self._is_successful_result(rfc_result)
        parsed_failure = self._parsed_failure(rfc_result)
        error_type = rfc_result.get("errorType") or parsed_failure.get("errorType")
        content = {"data": data, "function": rfc_result.get("function"), "message": rfc_result.get("message")}
        if not success:
            content.update(
                {
                    "errorType": error_type or "business_failure",
                    "subrc": parsed_failure.get("subrc"),
                    "retryable": bool(rfc_result.get("retryable")),
                    "target": rfc_result.get("target"),
                    "rawMessage": rfc_result.get("rawMessage"),
                    "strength": "none",
                    "sufficiency": "insufficient",
                    "uncertainty": self._failure_uncertainty(tool_name, rfc_result),
                    "businessConclusionAllowed": False,
                }
            )
        title_map = {
            "tcode_info": "事务码对象信息",
            "program_source": "ABAP 源码片段",
            "function_source": "RFC/函数源码片段",
            "source_manifest": "源码清单与索引",
            "source_search": "源码搜索结果",
            "source_slice": "源码可执行片段",
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
                summary=self._rfc_summary(tool_name, rfc_result),
                source_object=params.get("tcode") or params.get("object_name") or params.get("table_name"),
                location=self._function_name(tool_name),
                confidence=0.9 if success else 0.05 if error_type in {"connection_failure", "timeout"} else 0.2,
                content=content,
            )
        ]

    def _evidence_type(self, tool_name: str) -> str:
        if tool_name in {"program_source", "function_source", "source_manifest", "source_search", "source_slice"}:
            return "source"
        if tool_name == "ddic_meta":
            return "ddic"
        if tool_name == "zilog_logs":
            return "log"
        if tool_name in {"safe_table_read", "latest_table_read"}:
            return "data"
        return "sap"

    def _rfc_summary(self, tool_name: str, rfc_result: dict[str, Any]) -> str:
        if rfc_result.get("errorType") in {"connection_failure", "timeout"}:
            target = rfc_result.get("target")
            target_text = f"（目标：{target}）" if target else ""
            return (
                f"{self._tool_label(tool_name)}未执行成功：SAP RFC 网络不可达或超时{target_text}。"
                "该结果只能说明本次无法联网取数，不能证明业务数据不存在。"
            )
        if rfc_result.get("errorType"):
            return str(rfc_result.get("message") or f"{self._tool_label(tool_name)}执行失败")
        data = rfc_result.get("data")
        if isinstance(data, dict):
            if data.get("JSON_PARSE_ERROR"):
                detail = data.get("JSON_PARSE_ERROR_DETAIL") or data.get("JSON_PARSE_ERROR")
                return (
                    f"{self._tool_label(tool_name)}返回的 JSON 无法解析：{detail}。"
                    "这通常是 SAP 侧 RFC 手工拼接 JSON 时未转义字段文本中的引号、反斜杠或控制字符导致；"
                    "本次结果不能作为可用 DDIC/业务证据。"
                )
            parsed = data.get("JSON_PARSED")
            if isinstance(parsed, dict) and parsed.get("success") is False:
                message = parsed.get("message") or "SAP 工具返回业务失败"
                subrc = parsed.get("subrc")
                if tool_name == "safe_table_read" and self._is_read_table_buffer_exceeded(parsed):
                    return (
                        "safe_table_read 读取失败：RFC_READ_TABLE 返回缓冲区超出（subrc=6）。"
                        "通常是字段过多、字段太宽、行数太多或条件不够精确导致；请改为 fields<=5、max_rows<=3，"
                        "并增加 VBELN/BUKRS/日期等 EQ 条件后重试。该结果不能证明业务数据不存在。"
                    )
                if subrc is not None:
                    return f"{message}（subrc={subrc}）"
                return str(message)
        return rfc_result.get("message") or f"{tool_name} 执行完成"

    def _summary(self, tool_name: str, rfc_result: dict[str, Any]) -> str:
        return rfc_result.get("message") or f"{tool_name} 执行完成"

    def _failed_tool_data(self, tool_name: str, params: dict[str, Any], rfc_result: dict[str, Any]) -> dict[str, Any]:
        parsed_failure = self._parsed_failure(rfc_result)
        error_type = rfc_result.get("errorType") or parsed_failure.get("errorType") or "business_failure"
        return {
            "request": self._rfc_params(tool_name, params),
            "response": rfc_result.get("data"),
            "errorType": error_type,
            "retryable": bool(rfc_result.get("retryable")),
            "target": rfc_result.get("target"),
            "message": rfc_result.get("message"),
            "rawMessage": rfc_result.get("rawMessage"),
            "businessConclusionAllowed": False,
            "agentHint": self._failure_uncertainty(tool_name, rfc_result),
        }

    def _failure_uncertainty(self, tool_name: str, rfc_result: dict[str, Any]) -> str:
        if rfc_result.get("errorType") in {"connection_failure", "timeout"}:
            return (
                f"{self._tool_label(tool_name)}因 RFC 网络连接失败未取得 SAP 数据；"
                "不要据此判断凭证、日志或表记录不存在，应先依赖源码证据并在最终回答中标注数据验证缺口。"
            )
        if rfc_result.get("errorType"):
            return f"{self._tool_label(tool_name)}执行失败，不能作为确定业务结论。"
        data = rfc_result.get("data")
        if isinstance(data, dict) and data.get("JSON_PARSE_ERROR"):
            return (
                f"{self._tool_label(tool_name)}返回内容不是合法 JSON，Agent 不能可靠读取字段结构或业务数据；"
                "需要修复 SAP 侧 RFC JSON 转义后重试，不能把本次结果当作已验证证据。"
            )
        parsed_failure = self._parsed_failure(rfc_result)
        if parsed_failure.get("errorType") == "read_table_buffer_exceeded":
            return (
                "safe_table_read 因 RFC_READ_TABLE 缓冲区超出未取得数据；"
                "请减少字段数、降低 max_rows、增加高选择性 EQ 条件后重试，不能据此判断数据不存在。"
            )
        return "SAP 工具返回业务失败，需结合源码、DDIC 或其他工具验证。"

    def _parsed_failure(self, rfc_result: dict[str, Any]) -> dict[str, Any]:
        data = rfc_result.get("data")
        if not isinstance(data, dict):
            return {}
        if data.get("JSON_PARSE_ERROR"):
            return {"errorType": "json_parse_error", "detail": data.get("JSON_PARSE_ERROR_DETAIL")}
        parsed = data.get("JSON_PARSED")
        if not isinstance(parsed, dict) or parsed.get("success") is not False:
            return {}
        if self._is_read_table_buffer_exceeded(parsed):
            return {"errorType": "read_table_buffer_exceeded", "subrc": 6}
        subrc = parsed.get("subrc")
        return {"errorType": "rfc_function_failure", "subrc": subrc} if subrc is not None else {"errorType": "business_failure"}

    def _is_read_table_buffer_exceeded(self, parsed: dict[str, Any]) -> bool:
        try:
            return int(parsed.get("subrc")) == 6
        except (TypeError, ValueError):
            return False

    def _tool_label(self, tool_name: str) -> str:
        labels = {
            "safe_table_read": "只读表查询",
            "latest_table_read": "最新记录查询",
            "zilog_logs": "ZILOG 日志查询",
            "tcode_info": "事务码查询",
            "program_source": "程序源码读取",
            "function_source": "函数源码读取",
            "ddic_meta": "DDIC 查询",
            "ping": "SAP 连接测试",
        }
        return labels.get(tool_name, tool_name)

    def _safe_payload(self, params: dict[str, Any]) -> dict[str, Any]:
        return {key: ("***" if "password" in key.lower() else value) for key, value in params.items()}


sap_tool_service = SapToolService()
