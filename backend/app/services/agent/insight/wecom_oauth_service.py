import base64
import hashlib
import hmac
import json
from datetime import datetime, timedelta
from urllib.parse import quote, urlencode

import httpx
from sqlalchemy import or_
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core import security
from app.core.config import settings
from app.models.system.sys_user import SysUser
from app.services.agent.insight.notification_service import insight_notification_service


class InsightWecomOAuthService:
    authorize_base_url = "https://open.weixin.qq.com/connect/oauth2/authorize"

    def build_authorize_url(self, target_path: str | None) -> str:
        self._validate_settings()
        front_target = self._normalize_front_target(target_path)
        state = self._encode_state({"target_path": front_target, "ts": int(datetime.now().timestamp())})
        redirect_uri = self._api_callback_url()
        params = {
            "appid": settings.INSIGHT_WECOM_CORP_ID,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "snsapi_base",
            "state": state,
            "agentid": settings.INSIGHT_WECOM_AGENT_ID,
        }
        return f"{self.authorize_base_url}?{urlencode(params, quote_via=quote)}#wechat_redirect"

    async def handle_callback(self, db: AsyncSession, *, code: str, state: str) -> str:
        self._validate_settings()
        state_payload = self._decode_state(state)
        target_path = self._normalize_front_target(str(state_payload.get("target_path") or ""))
        userid = await self._fetch_wecom_userid(code)
        if not userid:
            return self._front_auth_url(error="not_bound", redirect=target_path)
        user = await self._find_platform_user(db, userid)
        if not user:
            return self._front_auth_url(error="not_bound", redirect=target_path)
        access_token = security.create_access_token(
            user.id,
            expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        )
        return self._front_auth_url(token=access_token, redirect=target_path)

    async def _fetch_wecom_userid(self, code: str) -> str | None:
        token = await insight_notification_service._get_wecom_access_token()
        url = f"{settings.INSIGHT_WECOM_BASE_URL.rstrip('/')}/cgi-bin/user/getuserinfo"
        async with httpx.AsyncClient(timeout=settings.INSIGHT_WECOM_TIMEOUT_SECONDS) as client:
            response = await client.get(url, params={"access_token": token, "code": code})
            response.raise_for_status()
            data = response.json()
        if data.get("errcode") != 0:
            raise ValueError(f"企业微信用户身份获取失败: {data.get('errmsg') or data}")
        userid = data.get("UserId") or data.get("userid") or data.get("user_id")
        return str(userid).strip() if userid else None

    async def _find_platform_user(self, db: AsyncSession, wecom_userid: str) -> SysUser | None:
        return (
            await db.exec(
                select(SysUser).where(
                    SysUser.is_deleted == 0,
                    SysUser.status == 1,
                    or_(SysUser.employee_id == wecom_userid, SysUser.username == wecom_userid),
                )
            )
        ).first()

    def _api_callback_url(self) -> str:
        base_url = settings.INSIGHT_PUBLIC_BASE_URL.strip()
        if not base_url:
            raise ValueError("未配置 INSIGHT_PUBLIC_BASE_URL，无法生成企业微信 OAuth 回调地址")
        return f"{base_url.rstrip('/')}/ai-api/v1/insight/wecom/oauth/callback"

    def _front_auth_url(self, *, token: str | None = None, error: str | None = None, redirect: str = "/ai/insight") -> str:
        base_url = settings.INSIGHT_PUBLIC_BASE_URL.strip()
        if not base_url:
            raise ValueError("未配置 INSIGHT_PUBLIC_BASE_URL，无法生成企业微信登录跳转地址")
        params = {"redirect": redirect}
        if token:
            params["token"] = token
        if error:
            params["error"] = error
        return f"{base_url.rstrip('/')}/ai/insight/wecom-auth?{urlencode(params, quote_via=quote)}"

    def _normalize_front_target(self, target_path: str | None) -> str:
        value = str(target_path or "").strip()
        if not value:
            return "/ai/insight"
        if value.startswith("http://") or value.startswith("https://"):
            return "/ai/insight"
        if value.startswith("/ai/insight"):
            return value
        if value.startswith("/insight"):
            return f"/ai{value}"
        return "/ai/insight"

    def _encode_state(self, payload: dict[str, object]) -> str:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        body_token = base64.urlsafe_b64encode(body).decode("ascii").rstrip("=")
        signature = hmac.new(settings.SECRET_KEY.encode("utf-8"), body_token.encode("ascii"), hashlib.sha256).hexdigest()
        return f"{body_token}.{signature}"

    def _decode_state(self, state: str) -> dict[str, object]:
        try:
            body_token, signature = state.split(".", 1)
        except ValueError as exc:
            raise ValueError("企业微信登录状态无效") from exc
        expected = hmac.new(settings.SECRET_KEY.encode("utf-8"), body_token.encode("ascii"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError("企业微信登录状态校验失败")
        padded = body_token + "=" * (-len(body_token) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
        ts = int(payload.get("ts") or 0)
        if ts < int((datetime.now() - timedelta(minutes=10)).timestamp()):
            raise ValueError("企业微信登录状态已过期")
        return payload

    def _validate_settings(self) -> None:
        missing = []
        if not settings.INSIGHT_WECOM_CORP_ID:
            missing.append("INSIGHT_WECOM_CORP_ID")
        if not settings.INSIGHT_WECOM_AGENT_ID:
            missing.append("INSIGHT_WECOM_AGENT_ID")
        if not settings.INSIGHT_WECOM_SECRET:
            missing.append("INSIGHT_WECOM_SECRET")
        if missing:
            raise ValueError(f"企业微信 OAuth 配置缺失: {', '.join(missing)}")


insight_wecom_oauth_service = InsightWecomOAuthService()
