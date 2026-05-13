from contextlib import nullcontext
from typing import Any

from langfuse import get_client

from app.core.logger import logger


class _NoopObservation:
    id = None
    trace_id = None

    def update(self, **_: Any) -> "_NoopObservation":
        return self

    def update_trace(self, **_: Any) -> "_NoopObservation":
        return self

    def end(self, **_: Any) -> "_NoopObservation":
        return self

    def start_as_current_observation(self, **_: Any):
        return nullcontext(_NoopObservation())


class LangfuseObservability:
    def __init__(self) -> None:
        try:
            self.client = get_client()
        except Exception as exc:
            logger.warning(f"LangFuse 客户端初始化失败: {exc}")
            self.client = None

    def current_observation(self, *, name: str, as_type: str = "span", **kwargs: Any):
        if not self.client:
            return nullcontext(_NoopObservation())
        try:
            return self.client.start_as_current_observation(name=name, as_type=as_type, **kwargs)
        except Exception as exc:
            logger.warning(f"LangFuse observation 创建失败 name={name}: {exc}")
            return nullcontext(_NoopObservation())

    def flush(self) -> None:
        if not self.client:
            return
        try:
            self.client.flush()
        except Exception as exc:
            logger.warning(f"LangFuse flush 失败: {exc}")


langfuse_observability = LangfuseObservability()
