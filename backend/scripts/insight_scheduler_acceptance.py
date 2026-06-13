from app.core.config import settings
from app.schemas.agent.insight.data_source import InsightSchedulerStatusRead
from app.services.agent.insight.scheduler_service import insight_scheduler_service


def main() -> None:
    status = insight_scheduler_service.status()
    status_read = InsightSchedulerStatusRead(**status)
    warning_text = "\n".join(status_read.config_warnings)
    recommendation_text = "\n".join(status_read.config_recommendations)
    checks = {
        "status_schema_valid": isinstance(status_read.enabled, bool),
        "enabled_reflects_settings": status_read.enabled == settings.INSIGHT_SCHEDULER_ENABLED,
        "interval_positive": status_read.interval_seconds > 0,
        "batch_limit_positive": status_read.batch_limit > 0,
        "failure_threshold_positive": status_read.failure_pause_threshold > 0,
        "advisory_lock_configured": status_read.advisory_lock_id > 0,
        "scheduler_user_configured": status_read.scheduler_user_id > 0,
        "config_health_present": status_read.config_health in {"ready", "warning"},
        "disabled_warning_visible": settings.INSIGHT_SCHEDULER_ENABLED
        or "INSIGHT_SCHEDULER_ENABLED" in warning_text
        or "INSIGHT_SCHEDULER_ENABLED" in recommendation_text,
    }
    for name, passed in checks.items():
        print(f"[{'PASS' if passed else 'FAIL'}] {name}")
    if not all(checks.values()):
        failed = [name for name, passed in checks.items() if not passed]
        raise SystemExit(f"Insight 调度配置验收未通过: {'; '.join(failed)}")
    print(
        {
            "enabled": status_read.enabled,
            "running": status_read.running,
            "interval_seconds": status_read.interval_seconds,
            "batch_limit": status_read.batch_limit,
            "failure_pause_threshold": status_read.failure_pause_threshold,
            "advisory_lock_id": status_read.advisory_lock_id,
            "config_health": status_read.config_health,
            "warnings": status_read.config_warnings,
            "recommendations": status_read.config_recommendations,
        }
    )


if __name__ == "__main__":
    main()
