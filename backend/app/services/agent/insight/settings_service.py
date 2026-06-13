from datetime import datetime

from app.core.config import settings
from app.schemas.agent.insight.settings import (
    InsightSettingsStatusItem,
    InsightSettingsStatusRead,
    InsightSettingsStatusSection,
)


class InsightSettingsService:
    def get_status(self) -> InsightSettingsStatusRead:
        sections = [
            self._crawler_section(),
            self._scheduler_section(),
            self._notification_section(),
            self._report_section(),
            self._auth_section(),
        ]
        return InsightSettingsStatusRead(generated_at=datetime.now(), readonly=True, sections=sections)

    def _crawler_section(self) -> InsightSettingsStatusSection:
        return InsightSettingsStatusSection(
            key="crawler",
            name="采集与搜索",
            description="外部采集服务和搜索服务配置健康状态。",
            items=[
                InsightSettingsStatusItem(
                    key="firecrawl",
                    name="Firecrawl 网页抓取",
                    status="ok" if bool(settings.INSIGHT_FIRECRAWL_BASE_URL) else "warning",
                    description="用于抓取候选 URL 正文。",
                    details=[
                        "已配置服务地址" if settings.INSIGHT_FIRECRAWL_BASE_URL else "未配置服务地址",
                        "API Key 已配置" if settings.INSIGHT_FIRECRAWL_API_KEY else "API Key 未配置或当前服务不要求",
                        f"超时 {settings.INSIGHT_FIRECRAWL_TIMEOUT_SECONDS} 秒",
                    ],
                ),
                InsightSettingsStatusItem(
                    key="bocha",
                    name="Bocha 搜索",
                    status="ok" if bool(settings.INSIGHT_BOCHA_API_KEY) else "warning",
                    description="用于多源搜索发现候选网页。",
                    details=[
                        "API Key 已配置" if settings.INSIGHT_BOCHA_API_KEY else "API Key 未配置",
                        f"服务地址 {settings.INSIGHT_BOCHA_BASE_URL}",
                        f"搜索超时 {settings.INSIGHT_SEARCH_TIMEOUT_SECONDS} 秒",
                    ],
                ),
            ],
        )

    def _scheduler_section(self) -> InsightSettingsStatusSection:
        return InsightSettingsStatusSection(
            key="scheduler",
            name="周期调度",
            description="生产调度器开关、批量和失败暂停策略。",
            items=[
                InsightSettingsStatusItem(
                    key="scheduler_enabled",
                    name="自动周期采集",
                    status="ok" if settings.INSIGHT_SCHEDULER_ENABLED else "disabled",
                    description="控制 FastAPI 生命周期内置调度器是否自动运行。",
                    details=[
                        "已启用" if settings.INSIGHT_SCHEDULER_ENABLED else "未启用，需人工触发或通过接口启动",
                        f"扫描间隔 {settings.INSIGHT_SCHEDULER_INTERVAL_SECONDS} 秒",
                        f"单批上限 {settings.INSIGHT_SCHEDULER_BATCH_LIMIT}",
                    ],
                ),
                InsightSettingsStatusItem(
                    key="failure_pause",
                    name="失败暂停策略",
                    status="ok" if settings.INSIGHT_SCHEDULER_FAILURE_PAUSE_THRESHOLD > 0 else "warning",
                    description="连续失败达到阈值后自动暂停单个数据源。",
                    details=[
                        f"连续失败暂停阈值 {settings.INSIGHT_SCHEDULER_FAILURE_PAUSE_THRESHOLD}",
                        f"调度用户 ID {settings.INSIGHT_SCHEDULER_USER_ID}",
                        f"互斥锁 ID {settings.INSIGHT_SCHEDULER_ADVISORY_LOCK_ID}",
                    ],
                ),
            ],
        )

    def _notification_section(self) -> InsightSettingsStatusSection:
        secret_ready = bool(settings.INSIGHT_WECOM_CORP_ID and settings.INSIGHT_WECOM_AGENT_ID and settings.INSIGHT_WECOM_SECRET)
        public_url_ready = bool(settings.INSIGHT_PUBLIC_BASE_URL)
        return InsightSettingsStatusSection(
            key="notification",
            name="企业微信推送",
            description="报告和情报卡片推送配置状态。",
            items=[
                InsightSettingsStatusItem(
                    key="wecom_sender",
                    name="真实发送开关",
                    status="ok" if settings.INSIGHT_WECOM_SEND_ENABLED and secret_ready else "disabled",
                    description="开启后会真实调用企业微信应用发送。",
                    details=[
                        "真实发送已启用" if settings.INSIGHT_WECOM_SEND_ENABLED else "真实发送未启用",
                        "企业微信应用配置已齐全" if secret_ready else "企业微信应用配置不完整",
                        f"重试上限 {settings.INSIGHT_WECOM_RETRY_MAX_ATTEMPTS}",
                    ],
                ),
                InsightSettingsStatusItem(
                    key="wecom_card",
                    name="卡片跳转地址",
                    status="ok" if public_url_ready else "warning",
                    description="配置后推送优先使用企业微信 textcard 卡片。",
                    details=[
                        "已配置前端访问基址" if public_url_ready else "未配置前端访问基址，推送会回退文本消息",
                        "卡片点击仍需要平台登录态；免登录已记录为后续优化项",
                    ],
                ),
            ],
        )

    def _report_section(self) -> InsightSettingsStatusSection:
        return InsightSettingsStatusSection(
            key="report",
            name="报告交付",
            description="当前报告生成、编辑和导出能力边界。",
            items=[
                InsightSettingsStatusItem(
                    key="html_export",
                    name="HTML 导出",
                    status="ok",
                    description="已支持 HTML 导出记录、下载、失败落库和人工重试。",
                    details=["HTML 为当前承诺交付格式", "PDF/DOCX/XLSX 套版导出仍在后续优化清单中"],
                )
            ],
        )

    def _auth_section(self) -> InsightSettingsStatusSection:
        return InsightSettingsStatusSection(
            key="auth",
            name="登录与权限",
            description="平台访问控制和企微卡片登录边界。",
            items=[
                InsightSettingsStatusItem(
                    key="platform_auth",
                    name="平台登录态",
                    status="ok",
                    description="所有 Insight 页面继续复用平台 JWT 登录态和后端权限过滤。",
                    details=["未登录访问卡片链接会进入登录页", "不通过 URL 工号直接登录，避免身份伪造"],
                )
            ],
        )


insight_settings_service = InsightSettingsService()
