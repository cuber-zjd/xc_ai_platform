import asyncio
import importlib
import json
import os
import re
import sys
from typing import Any

from app.core.logger import logger
from app.models.agent.sap_assistant import SapSystemConfig


class SapRfcClient:
    """SAP RFC 客户端。pyrfc 未安装或系统未配置时返回可诊断错误。"""

    async def ping(self, system: SapSystemConfig) -> dict[str, Any]:
        return await self.call(system, "ZFM_AI_PING", {})

    async def call(
        self,
        system: SapSystemConfig,
        function_name: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        params = params or {}
        self._configure_nwrfc_dll_path()
        try:
            pyrfc = importlib.import_module("pyrfc")
            Connection = getattr(pyrfc, "Connection")
        except AttributeError:
            logger.warning("pyrfc 已安装，但 SAP NetWeaver RFC SDK 动态库未加载")
            return {
                "success": False,
                "function": function_name,
                "errorType": "sdk_not_available",
                "retryable": False,
                "message": "pyrfc 已安装，但未找到 SAP NetWeaver RFC SDK 动态库。请安装 NWRFC SDK 并把 lib 目录加入 PATH。",
                "data": None,
            }
        except Exception:
            logger.warning("pyrfc 未安装，SAP RFC 正式调用不可用")
            return {
                "success": False,
                "function": function_name,
                "errorType": "sdk_not_available",
                "retryable": False,
                "message": "后端未安装 pyrfc 或 SAP NetWeaver RFC SDK，无法发起正式 SAP RFC 调用。",
                "data": None,
            }

        conn_params = self._build_connection_params(system)
        if not conn_params.get("user") or not conn_params.get("passwd"):
            return {
                "success": False,
                "function": function_name,
                "errorType": "missing_credentials",
                "retryable": False,
                "message": "SAP RFC 用户或密码环境变量未配置。",
                "data": None,
            }

        try:
            result = await asyncio.to_thread(self._call_sync, Connection, conn_params, function_name, params)
            result = self._normalize_result(result)
            return {"success": True, "function": function_name, "message": "调用成功", "data": result}
        except Exception as exc:
            logger.error(f"SAP RFC 调用失败 {function_name}: {exc}")
            masked_message = self._mask_error(str(exc))
            diagnosis = self._diagnose_error(masked_message)
            return {
                "success": False,
                "function": function_name,
                "errorType": diagnosis["errorType"],
                "retryable": diagnosis["retryable"],
                "target": diagnosis.get("target"),
                "message": diagnosis["message"],
                "rawMessage": masked_message,
                "data": None,
            }

    def _call_sync(self, connection_cls: Any, conn_params: dict[str, Any], function_name: str, params: dict[str, Any]) -> Any:
        conn = connection_cls(**conn_params)
        try:
            return conn.call(function_name, **params)
        finally:
            conn.close()

    def _build_connection_params(self, system: SapSystemConfig) -> dict[str, Any]:
        params: dict[str, Any] = {
            "client": system.client,
            "lang": system.language,
        }
        if system.ashost:
            params["ashost"] = system.ashost
            if system.sysnr:
                params["sysnr"] = system.sysnr
        elif system.mshost:
            params["mshost"] = system.mshost
            if system.sysnr:
                params["sysnr"] = system.sysnr
            if system.group:
                params["group"] = system.group
        if system.user_env_key:
            params["user"] = self._resolve_secret(system.user_env_key)
        if system.password_env_key:
            params["passwd"] = self._resolve_secret(system.password_env_key)
        return params

    def _resolve_secret(self, value: str) -> str | None:
        env_value = os.getenv(value)
        if env_value:
            return env_value
        return value

    def _mask_error(self, message: str) -> str:
        for token in ("passwd", "password", "PWD"):
            message = message.replace(token, "***")
        return message[:800]

    def _diagnose_error(self, message: str) -> dict[str, Any]:
        upper_message = message.upper()
        target = self._extract_error_target(message)
        if any(
            token in upper_message
            for token in (
                "RFC_COMMUNICATION_FAILURE",
                "WSAETIMEDOUT",
                "CONNECTION TIMED OUT",
                "CONNECT CALL FAILED",
                "PARTNER",
                "NOT REACHED",
                "NIPCONNECT",
            )
        ):
            target_text = f"（目标：{target}）" if target else ""
            return {
                "errorType": "connection_failure",
                "retryable": True,
                "target": target,
                "message": f"SAP RFC 网络连接失败{target_text}，未能执行远程函数；这不能作为业务数据不存在的证据。",
            }
        if "LOGON" in upper_message or "PASSWORD" in upper_message or "NAME OR PASSWORD" in upper_message:
            return {
                "errorType": "authentication_failure",
                "retryable": False,
                "target": target,
                "message": "SAP RFC 登录失败，请检查 RFC 用户、密码环境变量和账号状态。",
            }
        if "TIMEOUT" in upper_message:
            target_text = f"（目标：{target}）" if target else ""
            return {
                "errorType": "timeout",
                "retryable": True,
                "target": target,
                "message": f"SAP RFC 调用超时{target_text}，未能取得结果；这不能作为业务数据不存在的证据。",
            }
        return {
            "errorType": "rfc_error",
            "retryable": False,
            "target": target,
            "message": message,
        }

    def _extract_error_target(self, message: str) -> str | None:
        partner_match = re.search(r"partner\s+'([^']+)'", message, flags=re.IGNORECASE)
        if partner_match:
            return partner_match.group(1)
        connect_match = re.search(r"Connect call failed\s+\('([^']+)'\s*,\s*(\d+)\)", message, flags=re.IGNORECASE)
        if connect_match:
            return f"{connect_match.group(1)}:{connect_match.group(2)}"
        detail_match = re.search(r"NiPConnect2:\s*([^\s\r\n]+)", message, flags=re.IGNORECASE)
        if detail_match:
            return detail_match.group(1)
        return None

    def _normalize_result(self, result: Any) -> Any:
        if not isinstance(result, dict):
            return result
        lines = result.get("ET_JSON_LINES")
        if isinstance(lines, list):
            json_text = "".join(str(item.get("LINE", item.get("line", ""))).rstrip() for item in lines if isinstance(item, dict))
            if json_text:
                normalized = {**result, "JSON_TEXT": json_text}
                try:
                    normalized["JSON_PARSED"] = json.loads(json_text)
                except json.JSONDecodeError:
                    parse_error = sys.exception()
                    repaired_text = self._repair_json_text(json_text)
                    if repaired_text != json_text:
                        try:
                            normalized["JSON_PARSED"] = json.loads(repaired_text)
                            normalized["JSON_TEXT_REPAIRED"] = repaired_text
                            normalized["JSON_REPAIR_NOTE"] = (
                                "RFC JSON_TEXT 包含常见格式问题，平台侧已做容错修复。"
                            )
                            return normalized
                        except json.JSONDecodeError:
                            parse_error = sys.exception()
                    normalized["JSON_PARSE_ERROR"] = "RFC JSON_TEXT 解析失败，保留原始文本。"
                    if isinstance(parse_error, json.JSONDecodeError):
                        context = self._json_error_context(json_text, parse_error.pos)
                        normalized["JSON_PARSE_ERROR_DETAIL"] = (
                            f"{parse_error.msg} at line {parse_error.lineno} column {parse_error.colno} char {parse_error.pos}"
                        )
                        normalized["JSON_PARSE_ERROR_CONTEXT"] = context
                        normalized["JSON_PARSE_ERROR_HINT"] = self._json_error_hint(parse_error)
                        normalized["JSON_TEXT_PREVIEW"] = context["snippet"]
                return normalized
        return result

    def _repair_json_text(self, text: str) -> str:
        """修复常见 RFC 手工拼 JSON 问题。"""
        repaired: list[str] = []
        in_string = False
        escaped = False
        index = 0
        while index < len(text):
            char = text[index]
            if escaped:
                repaired.append(char)
                escaped = False
                index += 1
                continue
            if char == "\\":
                repaired.append(char)
                escaped = True
                index += 1
                continue
            if char == '"':
                repaired.append(char)
                in_string = not in_string
                index += 1
                continue
            if in_string:
                if char == "\n":
                    repaired.append("\\n")
                    index += 1
                    continue
                if char == "\r":
                    repaired.append("\\r")
                    index += 1
                    continue
                if char == "\t":
                    repaired.append("\\t")
                    index += 1
                    continue
                if ord(char) < 32:
                    repaired.append(f"\\u{ord(char):04x}")
                    index += 1
                    continue
            elif char == "0" and self._is_leading_zero_number(text, index, repaired):
                end = index + 1
                while end < len(text) and text[end].isdigit():
                    end += 1
                repaired.append(str(int(text[index:end])))
                index = end
                continue
            repaired.append(char)
            index += 1
        return "".join(repaired)

    def _is_leading_zero_number(self, text: str, index: int, repaired: list[str]) -> bool:
        if index + 1 >= len(text) or not text[index + 1].isdigit():
            return False
        previous = next((char for char in reversed(repaired) if not char.isspace()), "")
        if previous not in {":", ",", "["}:
            return False
        end = index + 1
        while end < len(text) and text[end].isdigit():
            end += 1
        next_char = text[end] if end < len(text) else ""
        return not next_char or next_char.isspace() or next_char in {",", "}", "]"}

    def _json_error_context(self, text: str, pos: int) -> dict[str, Any]:
        begin = max(0, pos - 160)
        end = min(len(text), pos + 160)
        snippet = text[begin:end]
        return {
            "position": pos,
            "snippet": snippet,
            "markerOffset": pos - begin,
            "marker": " " * max(0, pos - begin) + "^",
        }

    def _json_error_hint(self, error: json.JSONDecodeError) -> str:
        if error.msg in {"Expecting ',' delimiter", "Expecting property name enclosed in double quotes"}:
            return "多半是 SAP 侧手工拼 JSON 时，字段文本或业务值里的双引号没有转义。请修复对应 ZFM_AI_* RFC 的 JSON 字符串转义后重试。"
        if "Invalid control character" in error.msg:
            return "多半是 SAP 侧返回文本中包含未转义的换行、回车、制表符或其他控制字符。请修复对应 ZFM_AI_* RFC 的 JSON 字符串转义后重试。"
        if "Invalid \\escape" in error.msg:
            return "多半是 SAP 侧返回文本中包含未转义的反斜杠。请先把反斜杠转为两个反斜杠，再拼入 JSON 字符串。"
        return "请检查 SAP 侧 ET_JSON_LINES 拼接出的 JSON_TEXT，优先修复字符串字段的引号、反斜杠和控制字符转义。"

    def _configure_nwrfc_dll_path(self) -> None:
        if os.name != "nt":
            return
        candidates = []
        if os.getenv("SAP_NWRFC_LIB_DIR"):
            candidates.append(os.getenv("SAP_NWRFC_LIB_DIR") or "")
        if os.getenv("SAPNWRFC_HOME"):
            candidates.append(os.path.join(os.getenv("SAPNWRFC_HOME") or "", "lib"))
        for path in candidates:
            if path and os.path.isdir(path):
                try:
                    os.add_dll_directory(path)
                except (FileNotFoundError, OSError):
                    logger.warning(f"SAP NWRFC DLL 目录不可用: {path}")

sap_rfc_client = SapRfcClient()
