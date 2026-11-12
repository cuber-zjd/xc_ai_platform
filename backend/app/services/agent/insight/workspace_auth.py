"""仅接受妙搭服务端签名；绑定表由部署管理员维护，前端不能自选旧平台账号。"""
import hashlib
import hmac
import json
import time
from dataclasses import dataclass

from fastapi import HTTPException, Request
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from app.models.system.sys_user import SysUser
from app.core.config import settings


@dataclass(frozen=True)
class WorkspacePrincipal:
    scope: str
    owner: str
    user_id: int


async def authenticate(request: Request, db: AsyncSession) -> WorkspacePrincipal:
    secret = settings.INSIGHT_WORKSPACE_KEY
    if len(secret) < 32:
        raise HTTPException(503, "工作空间接入尚未配置")
    principal = request.headers.get("x-workspace-principal", "")
    stamp = request.headers.get("x-workspace-time", "")
    signature = request.headers.get("x-workspace-signature", "")
    try:
        if abs(time.time() * 1000 - int(stamp)) > 120_000:
            raise ValueError()
        scope, owner = principal.rsplit(":", 1)
        if not owner or len(principal) > 340:
            raise ValueError()
    except ValueError:
        raise HTTPException(401, "工作空间身份签名无效") from None
    body = await request.body()
    if len(body) > 32_000:
        raise HTTPException(413, "请求内容过大")
    path = request.url.path.split("/insight-workspace", 1)[-1]
    expected = hmac.new(secret.encode(), f"{stamp}\n{principal}\n{request.method}\n{path}\n".encode() + body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(401, "工作空间身份签名无效")
    try:
        bindings = json.loads(settings.INSIGHT_WORKSPACE_BINDINGS_JSON)
        user_id = int(bindings[scope][owner])
    except (ValueError, TypeError, KeyError):
        raise HTTPException(403, "当前飞书账号尚未关联报告与采集权限，请联系管理员。") from None
    user = (await db.exec(select(SysUser).where(SysUser.id == user_id, SysUser.status == 1, SysUser.is_deleted == 0))).first()
    if not user:
        raise HTTPException(403, "关联账号已停用或不存在")
    return WorkspacePrincipal(scope, owner, user_id)
