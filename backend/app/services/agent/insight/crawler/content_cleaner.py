from datetime import datetime, timedelta
from hashlib import sha256
from re import search, sub
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


TRACKING_QUERY_KEYS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "utm_id",
    "utm_source_platform",
    "spm",
    "ivk_sa",
    "from",
    "source",
    "ref",
    "fr",
    "bd_vid",
    "eqid",
    "fbclid",
    "gclid",
}


class InsightContentCleaner:
    """采集入库前的轻量清洗、摘要整理和去重指纹生成。"""

    def normalize_url(self, url: str) -> str:
        parsed = urlsplit(url.strip())
        query_items = sorted(
            [
                (key, value)
                for key, value in parse_qsl(parsed.query, keep_blank_values=True)
                if key.lower() not in TRACKING_QUERY_KEYS
            ],
            key=lambda item: (item[0].lower(), item[1]),
        )
        netloc = parsed.netloc.lower()
        path = parsed.path or "/"
        query = urlencode(query_items, doseq=True)
        return urlunsplit((parsed.scheme.lower() or "https", netloc, path, query, ""))

    def clean_title(self, *values: Any) -> str:
        for value in values:
            text = self.clean_text(value)
            if text and not self._is_noise_title(text):
                return text[:500]
        return "未命名情报"

    def clean_summary(self, value: str | None, max_length: int = 800) -> str | None:
        text = self.clean_readable_excerpt(value)
        if not text:
            return None
        return text if len(text) <= max_length else f"{text[:max_length]}..."

    def clean_text(self, value: Any) -> str | None:
        if not isinstance(value, str):
            return None
        text = value.replace("\u200b", "").replace("\ufeff", "")
        text = sub(r"\n{3,}", "\n\n", text)
        text = sub(r"[ \t]{2,}", " ", text)
        text = text.strip()
        return text or None

    def clean_readable_excerpt(self, value: Any) -> str | None:
        text = self.clean_text(value)
        if not text:
            return None
        lower_text = text.lower()
        if "just a moment" in lower_text or "performing security verification" in lower_text:
            return "页面需要安全验证，暂未提取到有效正文。"

        text = sub(r"!\[[^\]]*\]\([^)]+\)", " ", text)
        text = sub(r"\[([^\]]{1,80})\]\([^)]+\)", r"\1", text)
        text = sub(r"https?://\S+", " ", text)
        text = sub(r"data:image/[^)\s]+", " ", text)
        text = sub(r"\([^)]{80,}\)", " ", text)
        text = sub(r"={4,}|-{4,}|_{4,}", " ", text)

        ignored_keywords = (
            "登录",
            "注册",
            "首页",
            "导航",
            "app下载",
            "京公网安备",
            "营业执照",
            "copyright",
            "privacy",
            "cookie",
            "javascript",
        )
        lines: list[str] = []
        for raw_line in text.splitlines():
            line = self.clean_text(raw_line)
            if not line:
                continue
            lower_line = line.lower()
            if any(keyword.lower() in lower_line for keyword in ignored_keywords) and len(line) < 80:
                continue
            if len(line) <= 2 or line.count("|") >= 3:
                continue
            lines.append(line)

        compact = " ".join(lines)
        compact = sub(r"\s{2,}", " ", compact).strip(" -*|_")
        return compact or None

    def parse_publish_time(self, metadata: dict[str, Any], *texts: Any) -> datetime | None:
        keys = (
            "publishedTime",
            "published_time",
            "publishTime",
            "datePublished",
            "article:published_time",
            "og:published_time",
            "date",
            "pubdate",
            "publish_date",
            "time",
            "sourceTime",
            "source_time",
        )
        for key in keys:
            parsed = self._parse_datetime(metadata.get(key))
            if parsed:
                return parsed
        for key in keys:
            parsed = self._parse_datetime_from_text(metadata.get(key))
            if parsed:
                return parsed
        for text in texts:
            parsed = self._parse_datetime_from_text(text)
            if parsed:
                return parsed
        return None

    def build_dedupe_hash(self, url: str, title: str | None, content: str | None) -> str:
        normalized_content = self.clean_text(content) or ""
        if len(normalized_content) > 2000:
            normalized_content = normalized_content[:2000]
        raw = f"{self.normalize_url(url)}\n{self.clean_text(title) or ''}\n{normalized_content}"
        return sha256(raw.encode("utf-8")).hexdigest()

    def _parse_datetime(self, value: Any) -> datetime | None:
        if not isinstance(value, str) or not value.strip():
            return None
        normalized = value.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
        if parsed.tzinfo:
            return parsed.astimezone().replace(tzinfo=None)
        return parsed

    def _parse_datetime_from_text(self, value: Any) -> datetime | None:
        if not isinstance(value, str) or not value.strip():
            return None
        text = value.strip()

        relative = self._parse_relative_datetime(text)
        if relative:
            return relative

        absolute_patterns = (
            r"(?P<year>20\d{2})[-/.年](?P<month>1[0-2]|0?[1-9])[-/.月](?P<day>3[01]|[12]\d|0?[1-9])(?:日)?(?:\s+(?P<hour>[01]?\d|2[0-3]):(?P<minute>[0-5]\d))?",
            r"(?P<month>1[0-2]|0?[1-9])[-/.月](?P<day>3[01]|[12]\d|0?[1-9])(?:日)?(?:\s+(?P<hour>[01]?\d|2[0-3]):(?P<minute>[0-5]\d))?",
        )
        for pattern in absolute_patterns:
            match = search(pattern, text)
            if not match:
                continue
            now = datetime.now()
            year = int(match.groupdict().get("year") or now.year)
            month = int(match.group("month"))
            day = int(match.group("day"))
            hour = int(match.groupdict().get("hour") or 0)
            minute = int(match.groupdict().get("minute") or 0)
            try:
                parsed = datetime(year, month, day, hour, minute)
            except ValueError:
                continue
            if parsed > now + timedelta(days=2) and "year" not in match.groupdict():
                parsed = parsed.replace(year=year - 1)
            return parsed
        return None

    def _parse_relative_datetime(self, text: str) -> datetime | None:
        relative_match = search(r"(?P<num>\d+)\s*(?P<unit>分钟|小时|天|日|周|个月|月)前", text)
        if relative_match:
            number = int(relative_match.group("num"))
            unit = relative_match.group("unit")
            if unit == "分钟":
                return datetime.now() - timedelta(minutes=number)
            if unit == "小时":
                return datetime.now() - timedelta(hours=number)
            if unit in {"天", "日"}:
                return datetime.now() - timedelta(days=number)
            if unit == "周":
                return datetime.now() - timedelta(days=number * 7)
            if unit in {"个月", "月"}:
                return datetime.now() - timedelta(days=number * 30)
        if "刚刚" in text:
            return datetime.now()
        if "今天" in text:
            base = datetime.now()
            time_match = search(r"(?P<hour>[01]?\d|2[0-3]):(?P<minute>[0-5]\d)", text)
            if time_match:
                return base.replace(hour=int(time_match.group("hour")), minute=int(time_match.group("minute")), second=0, microsecond=0)
            return base.replace(hour=0, minute=0, second=0, microsecond=0)
        if "昨天" in text:
            base = datetime.now() - timedelta(days=1)
            time_match = search(r"(?P<hour>[01]?\d|2[0-3]):(?P<minute>[0-5]\d)", text)
            if time_match:
                return base.replace(hour=int(time_match.group("hour")), minute=int(time_match.group("minute")), second=0, microsecond=0)
            return base.replace(hour=0, minute=0, second=0, microsecond=0)
        return None

    def _is_noise_title(self, value: str) -> bool:
        text = value.strip().lower()
        return text in {"just a moment...", "just a moment", "百度一下"} or "security verification" in text


insight_content_cleaner = InsightContentCleaner()
