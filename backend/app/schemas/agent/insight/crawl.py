from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.agent.insight.common import InsightBaseRead
from app.schemas.agent.insight.intelligence import InsightIntelligenceCandidateRead
from app.schemas.agent.insight.task import InsightTaskRead


class InsightCrawlResultRead(InsightBaseRead):
    task_id: int
    data_source_id: int | None = None
    monitor_config_id: int | None = None
    source_channel_id: int | None = None
    channel: str
    query_text: str | None = None
    source_url: str
    source_title: str | None = None
    snippet: str | None = None
    raw_html_object_path: str | None = None
    markdown_content: str | None = None
    published_at: datetime | None = None
    dedupe_hash: str | None = None
    crawl_metadata: dict[str, Any] | None = None
    status: str
    error_message: str | None = None


class InsightManualUrlCrawlRequest(BaseModel):
    url: str = Field(..., min_length=1, max_length=1000)
    query_text: str | None = Field(default=None, max_length=500)
    data_source_id: int | None = None
    monitor_config_id: int | None = None
    source_channel_id: int | None = None


class InsightManualUrlCrawlResponse(BaseModel):
    task: InsightTaskRead
    crawl_result: InsightCrawlResultRead
    candidate: InsightIntelligenceCandidateRead


class InsightSearchDiscoveryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    channels: list[str] = Field(default_factory=lambda: ["baidu"])
    freshness: str | None = Field(default="noLimit", max_length=50)
    max_results: int = Field(default=8, ge=1, le=50)
    crawl_top_n: int = Field(default=3, ge=0, le=50)
    data_source_id: int | None = None
    monitor_config_id: int | None = None
    source_channel_id: int | None = None
    include_keywords: list[str] = Field(default_factory=list)
    exclude_keywords: list[str] = Field(default_factory=list)
    filter_prompt: str | None = Field(default=None, max_length=2000)
    enable_llm_filter: bool = False
    llm_min_score: float | None = Field(default=0.6, ge=0, le=1)
    create_candidate_from_hits: bool = False
    run_type: str = Field(default="manual_test", max_length=30)


class InsightSearchHitRead(BaseModel):
    channel: str
    title: str
    url: str
    snippet: str | None = None
    published_at: datetime | None = None
    raw: dict[str, Any] | None = None


class InsightSearchDiscoveryResponse(BaseModel):
    task: InsightTaskRead
    hits: list[InsightSearchHitRead]
    discovered_results: list[InsightCrawlResultRead]
    crawled_results: list[InsightCrawlResultRead]
    candidates: list[InsightIntelligenceCandidateRead]
