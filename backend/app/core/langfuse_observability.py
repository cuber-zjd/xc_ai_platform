import os
from contextlib import nullcontext
from typing import Any
from urllib.parse import urlparse

from langfuse import get_client

from app.core.config import settings
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
            self._normalize_proxy_environment()
            self.client = get_client()
        except Exception as exc:
            logger.warning(f"LangFuse 客户端初始化失败: {exc}")
            self.client = None

    @staticmethod
    def _normalize_proxy_environment() -> None:
        proxy_keys = (
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "ALL_PROXY",
            "http_proxy",
            "https_proxy",
            "all_proxy",
        )
        for key in proxy_keys:
            value = os.getenv(key)
            if value and value.lower().startswith("socks://"):
                os.environ[key] = f"socks5://{value[len('socks://'):]}"
                logger.warning(f"已将环境变量 {key} 的代理协议从 socks:// 规范为 socks5://")

        no_proxy_hosts = ["localhost", "127.0.0.1"]
        if settings.LANGFUSE_HOST:
            hostname = urlparse(settings.LANGFUSE_HOST).hostname
            if hostname:
                no_proxy_hosts.append(hostname)

        for key in ("NO_PROXY", "no_proxy"):
            existing = [item.strip() for item in os.getenv(key, "").split(",") if item.strip()]
            merged = existing + [host for host in no_proxy_hosts if host not in existing]
            os.environ[key] = ",".join(merged)

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
