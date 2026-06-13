from enum import Enum


class InsightSubjectType(str, Enum):
    COMPANY = "company"
    INDUSTRY = "industry"
    MARKET = "market"
    PRODUCT = "product"
    POLICY = "policy"
    TECHNOLOGY = "technology"
    CUSTOM = "custom"


class InsightVisibilityScope(str, Enum):
    PRIVATE = "private"
    ASSIGNED = "assigned"
    DEPT = "dept"
    ROLE = "role"
    PUBLIC = "public"


class InsightTaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


class InsightCrawlerChannel(str, Enum):
    BAIDU = "baidu"
    BAIDU_NEWS = "baidu_news"
    BOCHA = "bocha"
    BOCHA_NEWS = "bocha_news"
    FIRECRAWL = "firecrawl"
    GENERIC_WEB = "generic_web"
    MANUAL_URL = "manual_url"


class InsightCrawlStatus(str, Enum):
    DISCOVERED = "discovered"
    FETCHED = "fetched"
    PARSED = "parsed"
    FAILED = "failed"
    IGNORED = "ignored"


class InsightCandidateReviewStatus(str, Enum):
    PENDING = "pending"
    PROMOTED = "promoted"
    REJECTED = "rejected"
    MERGED = "merged"
    IGNORED = "ignored"
