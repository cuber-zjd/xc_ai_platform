"""Firecrawl 独立端到端探测；只写任务与本机告警，不发送消息、不重启容器。"""

import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text  # noqa: E402
from sqlmodel import select  # noqa: E402
from app.db.session import async_session, engine  # noqa: E402
from app.models.agent.insight import InsightTask, InsightTaskStatus  # noqa: E402
from app.services.agent.insight.crawler.firecrawl_client import FirecrawlClient  # noqa: E402


async def run() -> dict:
    async with engine.connect() as lock:
        acquired = (await lock.execute(text("SELECT pg_try_advisory_lock(746321910)"))).scalar()
        await lock.commit()
        if not acquired:
            return {"skipped": "探测正在运行"}
        try:
            return await probe()
        finally:
            await lock.execute(text("SELECT pg_advisory_unlock(746321910)"))
            await lock.commit()


async def probe() -> dict:
    started = datetime.now()
    # 环境文件由systemd加载；未配置目标不能伪报健康。
    targets = json.loads(os.environ.get("INSIGHT_FIRECRAWL_PROBE_TARGETS", "[]"))
    results = []
    client = FirecrawlClient()
    for target in targets[:2]:
        try:
            url = target["url"]
            separator = "&" if "?" in url else "?"
            data = await asyncio.wait_for(client.scrape_url(url + separator + "insight_probe=" + uuid4().hex), 75)
            body = str(data.get("markdown") or "")
            client._check_verification_page(body)
            ok = len(body) >= 200 and target["expected"] in body
            results.append({"url": url, "ok": ok, "chars": len(body), "error": None if ok else "正文或预期标记缺失"})
        except Exception as exc:
            results.append({"url": target.get("url"), "ok": False, "error": f"{type(exc).__name__}: {exc}"[:400]})
    healthy = bool(results) and all(item["ok"] for item in results)
    async with async_session() as db:
        recent = list((await db.exec(select(InsightTask).where(InsightTask.task_type == "firecrawl_health")
                                    .order_by(InsightTask.id.desc()).limit(2))).all())
        streak = 0 if healthy else 1
        if not healthy:
            for previous in recent:
                if previous.status != InsightTaskStatus.FAILED:
                    break
                streak += 1
        output = {"healthy": healthy, "targets": results, "consecutive_failures": streak,
                  "alert": "critical" if streak >= 3 else ("warning" if not healthy else "none"),
                  "recovered": healthy and bool(recent) and recent[0].status == InsightTaskStatus.FAILED,
                  "note": "未使用HTTP降级；异常可能来自站点或网络，不自动认定worker崩溃"}
        task = InsightTask(task_uid=f"firecrawl_health_{uuid4().hex}", task_type="firecrawl_health",
                           started_at=started, finished_at=datetime.now(), progress=100,
                           status=InsightTaskStatus.SUCCESS if healthy else InsightTaskStatus.FAILED,
                           output_payload=output, error_message=None if healthy else "Firecrawl端到端探测异常")
        db.add(task)
        await db.commit()
    sys.stderr.write(f"Firecrawl告警级别={output['alert']} 连续失败={streak} 恢复={output['recovered']}\n")
    return output


if __name__ == "__main__":
    sys.stdout.write(json.dumps(asyncio.run(run()), ensure_ascii=False) + "\n")
