from datetime import datetime, timedelta

import httpx
import pytest

from app.services.agent.insight.crawler.search_client import (
    BaiduAntiBotError,
    BaiduCircuitOpenError,
    BaiduSearchClient,
)


def _response(*, url: str, status_code: int = 200, text: str = "") -> httpx.Response:
    request = httpx.Request("GET", url)
    return httpx.Response(status_code, text=text, request=request)


def test_baidu_antibot_response_detects_redirect_and_page_marker() -> None:
    client = BaiduSearchClient()

    assert client._is_antibot_response(
        _response(url="https://wappass.baidu.com/static/captcha/tuxing_v2.html")
    )
    assert client._is_antibot_response(
        _response(url="https://www.baidu.com/s", text="<title>百度安全验证</title>")
    )
    assert not client._is_antibot_response(
        _response(url="https://www.baidu.com/s", text="<title>百度资讯搜索结果</title>")
    )


def test_baidu_antibot_opens_circuit(monkeypatch: pytest.MonkeyPatch) -> None:
    client = BaiduSearchClient()
    monkeypatch.setattr(
        "app.services.agent.insight.crawler.search_client.settings.INSIGHT_BAIDU_ANTIBOT_COOLDOWN_SECONDS",
        600,
    )

    with pytest.raises(BaiduAntiBotError):
        client._open_antibot_circuit(
            _response(url="https://wappass.baidu.com/static/captcha/tuxing_v2.html")
        )

    assert client._blocked_until is not None
    assert client._blocked_until > datetime.now() + timedelta(seconds=590)
    with pytest.raises(BaiduCircuitOpenError):
        client._raise_if_circuit_open()


def test_baidu_expired_circuit_is_released() -> None:
    client = BaiduSearchClient()
    client._blocked_until = datetime.now() - timedelta(seconds=1)

    client._raise_if_circuit_open()

    assert client._blocked_until is None
