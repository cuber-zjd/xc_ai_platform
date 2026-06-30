from datetime import datetime
from typing import Any

from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field

from app.models.agent.insight.enums import InsightCrawlerChannel, InsightCrawlStatus
from app.models.base import BaseDBModel


class InsightCrawlResult(BaseDBModel, table=True):
    """百度、Bocha/博查、Firecrawl、通用网页等通用采集结果。"""

    __tablename__ = "insight_crawl_result"

    task_id: int = Field(foreign_key="insight_task.id", index=True)
    data_source_id: int | None = Field(default=None, foreign_key="insight_data_source.id", index=True)
    monitor_config_id: int | None = Field(default=None, foreign_key="insight_monitor_config.id", index=True)
    source_channel_id: int | None = Field(default=None, foreign_key="insight_channel.id", index=True)
    channel: InsightCrawlerChannel = Field(index=True)
    query_text: str | None = Field(default=None, index=True, max_length=500)
    source_url: str = Field(index=True, max_length=1000)
    source_title: str | None = Field(default=None, max_length=500)
    snippet: str | None = Field(default=None)
    raw_html_object_path: str | None = Field(default=None, max_length=800)
    markdown_content: str | None = Field(default=None)
    published_at: datetime | None = Field(default=None, index=True)
    dedupe_hash: str | None = Field(default=None, index=True, max_length=128)
    crawl_metadata: dict[str, Any] | None = Field(default=None, sa_type=JSONB)
    status: InsightCrawlStatus = Field(default=InsightCrawlStatus.DISCOVERED, index=True)
    error_message: str | None = Field(default=None)
