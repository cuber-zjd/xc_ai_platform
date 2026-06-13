from app.schemas.agent.insight.health import InsightHealthRead


class InsightHealthService:
    def get_health(self) -> InsightHealthRead:
        return InsightHealthRead(
            enabled_capabilities=[
                "crawler_scaffold",
                "intelligence_scaffold",
                "visibility_scaffold",
                "report_scaffold",
            ],
        )


insight_health_service = InsightHealthService()
