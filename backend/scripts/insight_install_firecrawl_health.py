"""统一部署调用：安装独立探测计时器，不管理容器生命周期。"""

import asyncio
import json
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text  # noqa: E402
from app.db.session import async_session  # noqa: E402
from app.services.agent.insight.crawler.firecrawl_client import FirecrawlClient  # noqa: E402


async def install() -> None:
    backend = Path(__file__).resolve().parents[1]
    if str(backend) != "/home/xinxi/ai_platform/backend":
        raise RuntimeError("仅允许原服务器目录安装")
    config = backend / ".firecrawl-health.env"
    if not config.exists():
        async with async_session() as db:
            rows = (await db.exec(text("""SELECT source_url, source_title FROM insight_crawl_result
                WHERE is_deleted=0 AND length(markdown_content)>800
                AND crawl_metadata->'fulltext_fetch'->>'provider'='firecrawl'
                AND create_time>now()-interval '7 days' ORDER BY id DESC LIMIT 100"""))).mappings().all()
        targets, hosts = [], set()
        for row in rows:
            url = FirecrawlClient.canonical_article_url(row["source_url"])
            host = urlparse(url).hostname
            title = row["source_title"] or ""
            if host in hosts or len(title) < 8:
                continue
            hosts.add(host)
            targets.append({"url": url, "expected": title[:8]})
            if len(targets) == 2:
                break
        if len(targets) < 2:
            raise RuntimeError("缺少两个实际成功站点，不能安装虚假健康探针")
        config.write_text("INSIGHT_FIRECRAWL_PROBE_TARGETS='" + json.dumps(targets, ensure_ascii=False).replace("'", "\\'") + "'\n")
        config.chmod(0o600)
    units = Path.home() / ".config/systemd/user"
    units.mkdir(parents=True, exist_ok=True)
    (units / "ai-platform-firecrawl-health.service").write_text(f"""[Unit]
Description=Firecrawl实际抓取检测与本机告警
[Service]
Type=oneshot
WorkingDirectory={backend}
EnvironmentFile={config}
ExecStart={backend}/.venv/bin/python {backend}/scripts/insight_check_firecrawl.py
TimeoutStartSec=240
""")
    (units / "ai-platform-firecrawl-health.timer").write_text("""[Unit]
Description=Firecrawl每15分钟实际抓取检测
[Timer]
OnCalendar=*:0/15
RandomizedDelaySec=30
Persistent=true
Unit=ai-platform-firecrawl-health.service
[Install]
WantedBy=timers.target
""")
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "--user", "enable", "--now", "ai-platform-firecrawl-health.timer"], check=True)


if __name__ == "__main__":
    asyncio.run(install())
