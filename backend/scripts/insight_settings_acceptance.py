from app.core.config import settings
from app.services.agent.insight.settings_service import insight_settings_service


SECRET_VALUES = [
    settings.INSIGHT_WECOM_SECRET,
    settings.INSIGHT_BOCHA_API_KEY,
    settings.INSIGHT_FIRECRAWL_API_KEY,
]


def main() -> None:
    status = insight_settings_service.get_status()
    dumped = status.model_dump(mode="json")
    text = str(dumped)
    section_keys = {section.key for section in status.sections}
    item_keys = {item.key for section in status.sections for item in section.items}

    checks = {
        "设置状态只读": status.readonly is True,
        "包含采集配置": "crawler" in section_keys,
        "包含调度配置": "scheduler" in section_keys,
        "包含企微推送配置": "notification" in section_keys,
        "包含报告交付配置": "report" in section_keys,
        "包含登录权限配置": "auth" in section_keys,
        "企微发送状态可读": "wecom_sender" in item_keys,
        "企微卡片状态可读": "wecom_card" in item_keys,
        "不暴露敏感值": all(not secret or secret not in text for secret in SECRET_VALUES),
    }
    for name, passed in checks.items():
        print(f"[{'PASS' if passed else 'FAIL'}] {name}")
    if not all(checks.values()):
        failed = [name for name, passed in checks.items() if not passed]
        raise SystemExit(f"Insight 设置状态验收未通过: {'; '.join(failed)}")
    print(dumped)


if __name__ == "__main__":
    main()
