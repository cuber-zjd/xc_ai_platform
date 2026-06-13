from urllib.parse import quote

import httpx

from app.core.config import settings
from app.schemas.agent.fr_report.ai_report import PreviewValidationResult


class PreviewValidator:
    async def validate(self, reportlet_path: str) -> PreviewValidationResult:
        preview_url = self._preview_url(reportlet_path)
        warnings: list[str] = []
        errors: list[str] = []

        if not settings.FINEREPORT_PREVIEW_BASE_URL:
            warnings.append("未配置 FINEREPORT_PREVIEW_BASE_URL，已跳过 FineReport HTTP 预览校验")
            return PreviewValidationResult(previewUrl=preview_url, warnings=warnings)

        try:
            async with httpx.AsyncClient(timeout=15, trust_env=False) as client:
                response = await client.get(preview_url)
        except httpx.HTTPError as exc:
            errors.append(f"FineReport 预览请求失败：{exc}")
            return PreviewValidationResult(previewUrl=preview_url, errors=errors)

        if response.status_code >= 400:
            errors.append(f"FineReport 预览 HTTP 状态异常：{response.status_code}")

        lowered = response.text.lower()
        error_keywords = [
            "stacktrace",
            "exception:",
            "java.lang.",
            "模板不存在",
            "报表不存在",
            "无法找到",
            "错误代码",
            "error code",
            "server error",
        ]
        if any(keyword in lowered for keyword in error_keywords):
            errors.append("FineReport 预览页面包含疑似报错信息")

        return PreviewValidationResult(
            previewUrl=preview_url,
            httpStatus=response.status_code,
            errors=errors,
            warnings=warnings,
        )

    def _preview_url(self, reportlet_path: str) -> str:
        base_url = settings.FINEREPORT_PREVIEW_BASE_URL.rstrip("/")
        encoded = quote(reportlet_path, safe="/")
        if not base_url:
            return f"/webroot/decision/view/report?viewlet={encoded}"
        if base_url.endswith("/webroot/decision/view/report"):
            return f"{base_url}?viewlet={encoded}"
        return f"{base_url}/webroot/decision/view/report?viewlet={encoded}"


preview_validator = PreviewValidator()
