import hashlib
from typing import Any

import httpx
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.logger import logger
from app.models.system.sys_model import SysModel


class InsightEmbeddingService:
    """Insight 向量模型服务。当前优先使用火山方舟多模态向量接口。"""

    default_model_code = "doubao-embedding-vision-251215"
    default_dimension = 2048

    async def embed_text(self, db: AsyncSession, text: str) -> tuple[list[float], dict[str, Any]]:
        clean_text = (text or "").strip()
        if not clean_text:
            return [], {"reason": "empty_text"}
        model = await self._load_embedding_model(db)
        if model is None:
            return [], {"reason": "embedding_model_not_configured"}

        endpoint = f"{model.base_url.rstrip('/')}/embeddings/multimodal"
        payload = {
            "model": model.model_code,
            "input": [{"type": "text", "text": clean_text[:8000]}],
        }
        async with httpx.AsyncClient(timeout=60.0, trust_env=True) as client:
            response = await client.post(
                endpoint,
                headers={"Authorization": f"Bearer {model.api_key}", "Content-Type": "application/json"},
                json=payload,
            )
        try:
            body = response.json()
        except Exception:
            body = {"raw": response.text[:500]}
        if response.status_code >= 400:
            logger.warning(f"Insight 向量调用失败: status={response.status_code}, body={self._safe_body(body)}")
            return [], {"reason": "embedding_call_failed", "status_code": response.status_code, "error": self._safe_body(body)}

        data = body.get("data") if isinstance(body, dict) else None
        embedding = data.get("embedding") if isinstance(data, dict) else None
        if not isinstance(embedding, list) or not embedding:
            return [], {"reason": "embedding_empty", "usage": body.get("usage") if isinstance(body, dict) else None}
        vector = [float(value) for value in embedding]
        return vector, {
            "model": model.model_code,
            "provider": model.provider,
            "dimension": len(vector),
            "content_hash": self.content_hash(clean_text),
            "usage": body.get("usage") if isinstance(body, dict) else None,
        }

    async def _load_embedding_model(self, db: AsyncSession) -> SysModel | None:
        statement = (
            select(SysModel)
            .where(
                SysModel.model_type == "embedding",
                SysModel.provider == "volcengine",
                SysModel.is_enabled,
                SysModel.is_deleted == 0,
            )
            .order_by(SysModel.model_level, SysModel.priority)
        )
        model = (await db.exec(statement)).first()
        if model:
            return model
        fallback = (
            await db.exec(
                select(SysModel)
                .where(
                    SysModel.provider == "volcengine",
                    SysModel.is_enabled,
                    SysModel.is_deleted == 0,
                )
                .order_by(SysModel.model_level, SysModel.priority)
            )
        ).first()
        if fallback is None:
            return None
        return SysModel(
            model_name="doubao-embedding-vision",
            model_code=self.default_model_code,
            provider="volcengine",
            api_key=fallback.api_key,
            base_url=fallback.base_url,
            model_level=fallback.model_level,
            model_type="embedding",
            capability="embedding",
            max_tokens=8192,
            default_temperature=0,
            priority=1,
            is_enabled=True,
            comment="运行时继承火山聊天模型 Key 的多模态向量配置",
        )

    def content_hash(self, text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def cosine_similarity(self, left: list[float], right: list[float]) -> float:
        if not left or not right or len(left) != len(right):
            return 0.0
        dot = sum(a * b for a, b in zip(left, right))
        left_norm = sum(a * a for a in left) ** 0.5
        right_norm = sum(b * b for b in right) ** 0.5
        if not left_norm or not right_norm:
            return 0.0
        return dot / (left_norm * right_norm)

    def _safe_body(self, body: Any) -> Any:
        if isinstance(body, dict) and isinstance(body.get("error"), dict):
            error = body["error"]
            return {"code": error.get("code"), "message": error.get("message"), "type": error.get("type")}
        return body


insight_embedding_service = InsightEmbeddingService()
