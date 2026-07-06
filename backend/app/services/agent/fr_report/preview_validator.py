import html
import re
from urllib.parse import quote

import httpx

from app.core.config import settings
from app.schemas.agent.fr_report.ai_report import PreviewValidationResult


class PreviewValidator:
    async def validate(self, reportlet_path: str, write_mode: bool = False) -> PreviewValidationResult:
        preview_url = self._preview_url(reportlet_path, write_mode)
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

        errors.extend(self._detect_error_text(response.text, source="HTTP", is_html=True))

        if not errors:
            rendered_errors, rendered_warnings = await self._validate_rendered_preview(preview_url)
            errors.extend(rendered_errors)
            warnings.extend(rendered_warnings)

        return PreviewValidationResult(
            previewUrl=preview_url,
            httpStatus=response.status_code,
            errors=errors,
            warnings=warnings,
        )

    async def _validate_rendered_preview(self, preview_url: str) -> tuple[list[str], list[str]]:
        try:
            from playwright.async_api import async_playwright
        except Exception:
            return [], ["当前后端未安装 Playwright，已完成 HTTP 预览校验，未执行浏览器渲染校验。"]

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page(viewport={"width": 1440, "height": 900})
                await page.goto(preview_url, wait_until="networkidle", timeout=30000)
                rendered_text = await page.locator("body").inner_text(timeout=5000)
                await browser.close()
        except Exception as exc:
            return [], [f"FineReport 浏览器渲染校验未完成：{exc}"]

        return self._detect_error_text(rendered_text, source="浏览器渲染"), []

    def _detect_error_text(self, text: str, *, source: str, is_html: bool = False) -> list[str]:
        if is_html:
            text = re.sub(r"<script\b[^>]*>.*?</script>", " ", text or "", flags=re.S | re.I)
            text = re.sub(r"<style\b[^>]*>.*?</style>", " ", text, flags=re.S | re.I)
            text = re.sub(r"<[^>]+>", " ", text)
            text = html.unescape(text)
        normalized = re.sub(r"\s+", " ", text or "").strip()
        lowered = normalized.lower()
        error_keywords = [
            "oops",
            "stacktrace",
            "exception:",
            "java.lang.",
            "模板不存在",
            "模板文件解析出错",
            "报表不存在",
            "无法找到",
            "错误代码",
            "error code",
            "server error",
        ]
        if not any(keyword in lowered for keyword in error_keywords):
            return []
        detail = normalized[:240] if normalized else "页面包含疑似报错信息"
        return [f"FineReport 预览{source}发现异常：{detail}"]

    def _preview_url(self, reportlet_path: str, write_mode: bool = False) -> str:
        base_url = settings.FINEREPORT_PREVIEW_BASE_URL.rstrip("/")
        encoded = quote(reportlet_path, safe="/")
        mode_query = "op=write&" if write_mode else ""
        if not base_url:
            return f"/webroot/decision/view/report?{mode_query}viewlet={encoded}"
        if base_url.endswith("/webroot/decision/view/report"):
            return f"{base_url}?{mode_query}viewlet={encoded}"
        return f"{base_url}/webroot/decision/view/report?{mode_query}viewlet={encoded}"


preview_validator = PreviewValidator()
