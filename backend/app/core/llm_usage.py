from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from typing import Any, Iterator


def _int_value(value: Any) -> int:
    try:
        return max(int(value or 0), 0)
    except (TypeError, ValueError):
        return 0


@dataclass
class LLMUsageCollector:
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    call_count: int = 0
    models: dict[str, dict[str, int]] = field(default_factory=dict)

    def record(self, model_name: str, usage: dict[str, Any] | None) -> None:
        payload = usage or {}
        input_tokens = _int_value(
            payload.get("input_tokens")
            or payload.get("prompt_tokens")
            or payload.get("input_token_count")
        )
        output_tokens = _int_value(
            payload.get("output_tokens")
            or payload.get("completion_tokens")
            or payload.get("output_token_count")
        )
        total_tokens = _int_value(payload.get("total_tokens") or payload.get("total_token_count"))
        if total_tokens <= 0:
            total_tokens = input_tokens + output_tokens

        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.total_tokens += total_tokens
        self.call_count += 1

        model_key = model_name.strip() or "unknown"
        model_usage = self.models.setdefault(
            model_key,
            {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "call_count": 0},
        )
        model_usage["input_tokens"] += input_tokens
        model_usage["output_tokens"] += output_tokens
        model_usage["total_tokens"] += total_tokens
        model_usage["call_count"] += 1

    def snapshot(self) -> dict[str, Any]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "call_count": self.call_count,
            "models": [
                {"model": model, **usage}
                for model, usage in sorted(
                    self.models.items(),
                    key=lambda item: item[1]["total_tokens"],
                    reverse=True,
                )
            ],
        }


_current_collector: ContextVar[LLMUsageCollector | None] = ContextVar(
    "llm_usage_collector",
    default=None,
)


@contextmanager
def collect_llm_usage() -> Iterator[LLMUsageCollector]:
    collector = LLMUsageCollector()
    token: Token[LLMUsageCollector | None] = _current_collector.set(collector)
    try:
        yield collector
    finally:
        _current_collector.reset(token)


def record_llm_usage(model_name: str, response: Any) -> None:
    collector = _current_collector.get()
    if collector is None:
        return
    usage = getattr(response, "usage_metadata", None)
    if not isinstance(usage, dict):
        metadata = getattr(response, "response_metadata", None)
        if isinstance(metadata, dict):
            usage = metadata.get("token_usage") or metadata.get("usage")
    collector.record(model_name, usage if isinstance(usage, dict) else None)


def record_llm_usage_payload(model_name: str, usage: dict[str, Any] | None) -> None:
    collector = _current_collector.get()
    if collector is not None:
        collector.record(model_name, usage)
