"""Insight 生产环境自检脚本。

默认不触发付费搜索或模型调用，只检查调度器稳定运行所需的本地依赖、
数据库对象、关键配置和基础连通性。需要真实外部接口探测时显式增加
``--probe-paid``。
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import logging
import platform
import sys
import time
import warnings
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import text

from app.core.config import settings
from app.db.session import async_session


warnings.filterwarnings("ignore", category=DeprecationWarning, module=r"sqlmodel\..*")
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REQUIRED_TABLES = (
    "sys_user",
    "sys_model",
    "insight_channel",
    "insight_monitor_config",
    "insight_task",
    "insight_crawl_result",
    "insight_intelligence_candidate",
    "insight_intelligence",
    "insight_intelligence_asset",
    "insight_asset_vector",
    "insight_channel_adapter_run",
    "insight_role",
    "insight_role_member",
)
REQUIRED_CHANNELS = ("baidu_news", "bocha_search", "doubao_web_search")
REQUIRED_EMBEDDING_MODEL = "doubao-embedding-vision-251215"
RECOMMENDED_CHAT_MODEL = "doubao-seed-2-1-turbo-260628"


@dataclass
class CheckItem:
    name: str
    status: str
    message: str
    detail: dict[str, Any] = field(default_factory=dict)


class InsightEnvChecker:
    def __init__(
        self,
        *,
        timeout: float,
        skip_network: bool,
        skip_playwright: bool,
        probe_paid: bool,
    ) -> None:
        self.timeout = timeout
        self.skip_network = skip_network
        self.skip_playwright = skip_playwright
        self.probe_paid = probe_paid
        self.items: list[CheckItem] = []

    def ok(self, name: str, message: str, **detail: Any) -> None:
        self.items.append(CheckItem(name=name, status="ok", message=message, detail=detail))

    def warn(self, name: str, message: str, **detail: Any) -> None:
        self.items.append(CheckItem(name=name, status="warn", message=message, detail=detail))

    def fail(self, name: str, message: str, **detail: Any) -> None:
        self.items.append(CheckItem(name=name, status="fail", message=message, detail=detail))

    async def run(self) -> list[CheckItem]:
        self.check_runtime()
        self.check_writable_paths()
        self.check_scheduler_settings()
        await self.check_database()
        await self.check_redis()
        await self.check_milvus()
        await self.check_playwright()
        await self.check_external_network()
        return self.items

    def check_runtime(self) -> None:
        version = sys.version_info
        python_ok = version.major == 3 and version.minor >= 11
        message = "Python 版本满足后端运行要求。" if python_ok else "Python 版本偏低，建议使用 3.11 或以上。"
        target = self.ok if python_ok else self.fail
        target(
            "Python 运行时",
            message,
            version=platform.python_version(),
            executable=sys.executable,
            platform=platform.platform(),
        )

        tz_names = tuple(name for name in time.tzname if name)
        timezone_hint = " ".join(tz_names).lower()
        if "china" in timezone_hint or "中国" in timezone_hint or "cst" in timezone_hint or "shanghai" in timezone_hint:
            self.ok("系统时间", "系统时区看起来可用于夜间调度。", now=datetime.now().isoformat(), timezone=tz_names)
        else:
            self.warn(
                "系统时间",
                "无法确认服务器时区为中国时区，请确认夜间 01:00-06:00 调度窗口不会偏移。",
                now=datetime.now().isoformat(),
                timezone=tz_names,
            )

    def check_writable_paths(self) -> None:
        for relative in ("tmp", "storage/insight_adapter_runs", "storage/insight_adapter_run_reports"):
            path = BACKEND_ROOT / relative
            try:
                path.mkdir(parents=True, exist_ok=True)
                probe = path / ".insight_env_check.tmp"
                probe.write_text("ok", encoding="utf-8")
                probe.unlink(missing_ok=True)
                self.ok("目录可写", f"{relative} 可写。", path=str(path))
            except Exception as exc:  # noqa: BLE001
                self.fail("目录可写", f"{relative} 不可写，调度快照或运行报告可能落盘失败。", path=str(path), error=str(exc))

    def check_scheduler_settings(self) -> None:
        if settings.INSIGHT_SCHEDULER_ENABLED:
            self.ok("调度器开关", "INSIGHT_SCHEDULER_ENABLED 已开启。")
        else:
            self.warn("调度器开关", "INSIGHT_SCHEDULER_ENABLED 未开启，生产环境不会自动周期采集。")

        trigger_mode = settings.INSIGHT_SCHEDULER_TRIGGER_MODE.strip().lower()
        if trigger_mode == "daily":
            self.ok(
                "定时触发",
                "调度器按每日固定时间触发，不会因后端重启立即采集。",
                daily_time=settings.INSIGHT_SCHEDULER_DAILY_TIME,
                timezone=settings.INSIGHT_SCHEDULER_TIMEZONE,
                auto_start=settings.INSIGHT_SCHEDULER_AUTO_START,
            )
        elif trigger_mode == "fixed_interval":
            self.warn(
                "定时触发",
                "当前使用 fixed_interval 兼容模式，会按固定间隔循环扫描。",
                interval_seconds=settings.INSIGHT_SCHEDULER_INTERVAL_SECONDS,
            )
        else:
            self.fail("定时触发", "INSIGHT_SCHEDULER_TRIGGER_MODE 仅支持 daily 或 fixed_interval。", trigger_mode=trigger_mode)

        if trigger_mode == "fixed_interval" and settings.INSIGHT_SCHEDULER_INTERVAL_SECONDS < 60:
            self.warn(
                "调度间隔",
                "调度扫描间隔小于 60 秒，生产环境容易造成频繁扫描。",
                interval_seconds=settings.INSIGHT_SCHEDULER_INTERVAL_SECONDS,
            )
        elif trigger_mode == "fixed_interval":
            self.ok("调度间隔", "调度扫描间隔合理。", interval_seconds=settings.INSIGHT_SCHEDULER_INTERVAL_SECONDS)

        if settings.INSIGHT_SCHEDULER_BATCH_LIMIT <= 0:
            self.fail("单批上限", "INSIGHT_SCHEDULER_BATCH_LIMIT 必须大于 0。")
        elif settings.INSIGHT_SCHEDULER_BATCH_LIMIT > 50:
            self.warn(
                "单批上限",
                "单批上限较高，夜间调度建议用分批和限流保证稳定。",
                batch_limit=settings.INSIGHT_SCHEDULER_BATCH_LIMIT,
            )
        else:
            self.ok("单批上限", "单批上限合理。", batch_limit=settings.INSIGHT_SCHEDULER_BATCH_LIMIT)

        if settings.INSIGHT_SCHEDULER_ADVISORY_LOCK_ID <= 0:
            self.fail("调度互斥锁", "INSIGHT_SCHEDULER_ADVISORY_LOCK_ID 必须为正数。")
        else:
            self.ok("调度互斥锁", "已配置 PostgreSQL advisory lock。", lock_id=settings.INSIGHT_SCHEDULER_ADVISORY_LOCK_ID)

        if settings.INSIGHT_SCHEDULER_FAILURE_PAUSE_THRESHOLD <= 0:
            self.fail("失败暂停阈值", "连续失败暂停阈值必须大于 0。")
        else:
            self.ok(
                "失败暂停阈值",
                "连续失败暂停阈值已配置。",
                threshold=settings.INSIGHT_SCHEDULER_FAILURE_PAUSE_THRESHOLD,
            )

    async def check_database(self) -> None:
        try:
            async with async_session() as db:
                result = await db.exec(text("select current_database(), current_user, now()"))
                current_database, current_user, server_time = result.one()
                self.ok(
                    "PostgreSQL 连接",
                    "数据库连接正常。",
                    database=current_database,
                    user=current_user,
                    server_time=str(server_time),
                )
                await self.check_tables(db)
                await self.check_scheduler_user(db)
                await self.check_channels(db)
                await self.check_models(db)
                await self.check_monitor_configs(db)
        except Exception as exc:  # noqa: BLE001
            self.fail(
                "PostgreSQL 连接",
                "数据库连接失败，后端和调度器无法正常工作。",
                host=settings.POSTGRES_SERVER,
                port=settings.POSTGRES_PORT,
                database=settings.POSTGRES_DB,
                error=str(exc),
            )

    async def check_tables(self, db: Any) -> None:
        result = await db.exec(
            text(
                """
                select table_name
                from information_schema.tables
                where table_schema = 'public'
                  and table_name = any(:tables)
                """
            ).bindparams(tables=list(REQUIRED_TABLES)),
        )
        existing = {row[0] for row in result.all()}
        missing = [table for table in REQUIRED_TABLES if table not in existing]
        if missing:
            self.fail("数据库表", "Insight 必需表不完整，请先执行迁移或初始化。", missing=missing)
        else:
            self.ok("数据库表", "Insight 必需表已存在。", table_count=len(existing))

    async def check_scheduler_user(self, db: Any) -> None:
        try:
            result = await db.exec(
                text(
                    """
                    select id, username, status, is_superuser
                    from sys_user
                    where id = :user_id and coalesce(is_deleted, 0) = 0
                    limit 1
                    """
                ).bindparams(user_id=settings.INSIGHT_SCHEDULER_USER_ID),
            )
            row = result.first()
            if row and int(row[2] or 0) == 1 and bool(row[3]):
                self.ok(
                    "调度用户",
                    "调度用户已启用且具有管理员权限。",
                    user_id=row[0],
                    username=row[1],
                )
            elif row:
                self.fail(
                    "调度用户",
                    "调度用户必须处于启用状态且具有管理员权限。",
                    user_id=row[0],
                    username=row[1],
                    status=row[2],
                    is_superuser=bool(row[3]),
                )
            else:
                self.fail("调度用户", "INSIGHT_SCHEDULER_USER_ID 对应用户不存在或已删除。", user_id=settings.INSIGHT_SCHEDULER_USER_ID)
        except Exception as exc:  # noqa: BLE001
            self.warn("调度用户", "无法验证调度用户，请检查 sys_user 表结构。", error=str(exc))

    async def check_channels(self, db: Any) -> None:
        result = await db.exec(
            text(
                """
                select channel_code, channel_name, access_status, status
                from insight_channel
                where coalesce(is_deleted, 0) = 0
                  and channel_code = any(:codes)
                """
            ).bindparams(codes=list(REQUIRED_CHANNELS)),
        )
        rows = {row[0]: row for row in result.all()}
        missing = [code for code in REQUIRED_CHANNELS if code not in rows]
        inactive = [code for code, row in rows.items() if row[3] != "active"]
        if missing:
            self.fail("核心渠道", "核心搜索渠道缺失。", missing=missing)
        elif inactive:
            self.fail("核心渠道", "核心搜索渠道未启用。", inactive=inactive)
        else:
            self.ok("核心渠道", "百度资讯、博查、豆包联网搜索渠道已配置。", channels=list(rows))

    async def check_models(self, db: Any) -> None:
        result = await db.exec(
            text(
                """
                select model_name, model_code, provider, model_type, is_enabled, status
                from sys_model
                where coalesce(is_deleted, 0) = 0
                  and (
                    model_code = :embedding_model
                    or model_name = :embedding_model
                    or model_code = :chat_model
                    or model_name = :chat_model
                  )
                """
            ).bindparams(
                embedding_model=REQUIRED_EMBEDDING_MODEL,
                chat_model=RECOMMENDED_CHAT_MODEL,
            ),
        )
        rows = result.all()
        enabled_rows = [row for row in rows if bool(row[4]) and int(row[5] or 0) == 1]
        embedding_ready = any(REQUIRED_EMBEDDING_MODEL in {row[0], row[1]} and row[3] == "embedding" for row in enabled_rows)
        chat_ready = any(RECOMMENDED_CHAT_MODEL in {row[0], row[1]} and row[3] == "chat" for row in enabled_rows)
        if embedding_ready:
            self.ok("向量模型", "火山方舟向量模型已启用。", model=REQUIRED_EMBEDDING_MODEL)
        else:
            self.fail("向量模型", "未找到已启用的 Insight 向量模型，资产向量化会失败。", model=REQUIRED_EMBEDDING_MODEL)

        if chat_ready:
            self.ok("豆包联网模型", "推荐的豆包联网搜索模型已启用。", model=RECOMMENDED_CHAT_MODEL)
        else:
            self.warn("豆包联网模型", "未找到推荐豆包联网模型，豆包联网搜索可能不可用。", model=RECOMMENDED_CHAT_MODEL)

    async def check_monitor_configs(self, db: Any) -> None:
        result = await db.exec(
            text(
                """
                select
                  count(*) filter (where coalesce(is_deleted, 0) = 0) as total_count,
                  count(*) filter (
                    where coalesce(is_deleted, 0) = 0
                      and status = 'active'
                      and schedule_enabled is true
                  ) as active_count,
                  count(*) filter (
                    where coalesce(is_deleted, 0) = 0
                      and status = 'active'
                      and schedule_enabled is true
                      and (keywords is null or jsonb_array_length(keywords) = 0)
                  ) as empty_keyword_count
                from insight_monitor_config
                """
            )
        )
        total_count, active_count, empty_keyword_count = result.one()
        if active_count <= 0:
            self.warn("监测配置", "没有启用的监测配置，调度器即使启动也不会采集到业务情报。", total_count=total_count)
        else:
            self.ok(
                "监测配置",
                "存在启用的监测配置。",
                total_count=total_count,
                active_count=active_count,
                empty_keyword_count=empty_keyword_count,
            )
        if empty_keyword_count:
            self.warn("监测关键词", "部分启用监测配置没有关键词，可能只适合站点最新流采集。", count=empty_keyword_count)

    async def check_redis(self) -> None:
        try:
            redis_module = importlib.import_module("redis.asyncio")
        except Exception as exc:  # noqa: BLE001
            self.warn("Redis 依赖", "未安装 redis Python 依赖，缓存和部分队列能力可能不可用。", error=str(exc))
            return

        client = redis_module.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            decode_responses=True,
            socket_connect_timeout=self.timeout,
            socket_timeout=self.timeout,
        )
        try:
            pong = await client.ping()
            if pong:
                self.ok("Redis 连接", "Redis 连接正常。", host=settings.REDIS_HOST, port=settings.REDIS_PORT)
            else:
                self.fail("Redis 连接", "Redis ping 未返回成功。", host=settings.REDIS_HOST, port=settings.REDIS_PORT)
        except Exception as exc:  # noqa: BLE001
            self.fail("Redis 连接", "Redis 连接失败。", host=settings.REDIS_HOST, port=settings.REDIS_PORT, error=str(exc))
        finally:
            await client.aclose()

    async def check_milvus(self) -> None:
        try:
            pymilvus = importlib.import_module("pymilvus")
        except Exception as exc:  # noqa: BLE001
            self.warn("Milvus 依赖", "未安装 pymilvus，RAG 向量检索能力不可用。", error=str(exc))
            return

        alias = "insight_env_check"
        try:
            await asyncio.to_thread(
                pymilvus.connections.connect,
                alias=alias,
                host=settings.MILVUS_HOST,
                port=str(settings.MILVUS_PORT),
                timeout=self.timeout,
            )
            collections = await asyncio.to_thread(pymilvus.utility.list_collections, using=alias)
            self.ok("Milvus 连接", "Milvus 连接正常。", host=settings.MILVUS_HOST, port=settings.MILVUS_PORT, collections=len(collections))
        except Exception as exc:  # noqa: BLE001
            self.fail("Milvus 连接", "Milvus 连接失败，资产向量检索会不可用。", host=settings.MILVUS_HOST, port=settings.MILVUS_PORT, error=str(exc))
        finally:
            try:
                await asyncio.to_thread(pymilvus.connections.disconnect, alias)
            except Exception:
                pass

    async def check_playwright(self) -> None:
        if self.skip_playwright:
            self.warn("Playwright", "已跳过 Playwright 浏览器探测。")
            return
        try:
            async_playwright = importlib.import_module("playwright.async_api").async_playwright
        except Exception as exc:  # noqa: BLE001
            self.fail("Playwright", "未安装 Playwright，重点网站适配器无法运行。", error=str(exc))
            return

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.goto("about:blank", timeout=int(self.timeout * 1000))
                await browser.close()
            self.ok("Playwright", "Chromium 可正常启动。")
        except Exception as exc:  # noqa: BLE001
            self.fail(
                "Playwright",
                "Chromium 启动失败，请在服务器执行 uv run python -m playwright install --with-deps chromium。",
                error=str(exc),
            )

    async def check_external_network(self) -> None:
        if self.skip_network:
            self.warn("外部网络", "已跳过外部网络探测。")
            return

        await self.check_url_reachable("百度连通性", "https://www.baidu.com")
        if settings.INSIGHT_BOCHA_API_KEY:
            await self.check_bocha()
        else:
            self.fail("博查配置", "未配置 INSIGHT_BOCHA_API_KEY，每日博查补充搜索不可用。")

        if settings.INSIGHT_WECOM_SEND_ENABLED:
            missing = [
                key
                for key, value in (
                    ("INSIGHT_WECOM_CORP_ID", settings.INSIGHT_WECOM_CORP_ID),
                    ("INSIGHT_WECOM_AGENT_ID", settings.INSIGHT_WECOM_AGENT_ID),
                    ("INSIGHT_WECOM_SECRET", settings.INSIGHT_WECOM_SECRET),
                    ("INSIGHT_PUBLIC_BASE_URL", settings.INSIGHT_PUBLIC_BASE_URL),
                )
                if not value
            ]
            if missing:
                self.fail("企业微信配置", "真实推送已开启，但企业微信配置不完整。", missing=missing)
            else:
                self.ok("企业微信配置", "企业微信真实推送配置项已填写。", public_base_url=settings.INSIGHT_PUBLIC_BASE_URL)
        else:
            self.warn("企业微信配置", "INSIGHT_WECOM_SEND_ENABLED 未开启，生产环境只会写推送记录或模拟发送。")

    async def check_url_reachable(self, name: str, url: str) -> None:
        try:
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
                response = await client.get(url)
            if response.status_code < 500:
                self.ok(name, "外部地址可访问。", url=url, status_code=response.status_code)
            else:
                self.warn(name, "外部地址返回服务端错误。", url=url, status_code=response.status_code)
        except Exception as exc:  # noqa: BLE001
            self.warn(name, "外部地址访问失败，请确认服务器出口网络、DNS 或代理配置。", url=url, error=str(exc))

    async def check_bocha(self) -> None:
        base_url = settings.INSIGHT_BOCHA_BASE_URL.rstrip("/")
        if not self.probe_paid:
            await self.check_url_reachable("博查连通性", base_url)
            self.ok("博查配置", "博查 API Key 已配置；未加 --probe-paid，不执行付费搜索。")
            return

        endpoint = f"{base_url}/v1/web-search"
        payload = {"query": "香驰 控股", "summary": False, "count": 1}
        try:
            async with httpx.AsyncClient(timeout=max(self.timeout, 20)) as client:
                response = await client.post(
                    endpoint,
                    headers={"Authorization": f"Bearer {settings.INSIGHT_BOCHA_API_KEY}", "Content-Type": "application/json"},
                    json=payload,
                )
            if response.status_code == 200:
                self.ok("博查付费探测", "博查搜索接口可用。", status_code=response.status_code)
            else:
                self.fail(
                    "博查付费探测",
                    "博查搜索接口返回异常。",
                    status_code=response.status_code,
                    response_excerpt=response.text[:500],
                )
        except Exception as exc:  # noqa: BLE001
            self.fail("博查付费探测", "博查搜索接口调用失败。", endpoint=endpoint, error=str(exc))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Insight 生产环境自检")
    parser.add_argument("--json", action="store_true", help="仅输出 JSON，便于 CI 或部署脚本读取。")
    parser.add_argument("--strict", action="store_true", help="存在 warning 时也返回非 0。")
    parser.add_argument("--skip-network", action="store_true", help="跳过百度、博查等外部网络探测。")
    parser.add_argument("--skip-playwright", action="store_true", help="跳过 Playwright 浏览器启动探测。")
    parser.add_argument("--probe-paid", action="store_true", help="执行真实博查搜索探测，会消耗外部接口额度。")
    parser.add_argument("--timeout", type=float, default=8.0, help="单项网络或服务连接超时秒数。")
    return parser


def render_text(items: list[CheckItem]) -> str:
    icon_map = {"ok": "OK", "warn": "WARN", "fail": "FAIL"}
    lines = ["Insight 生产环境自检结果", "=" * 32]
    for item in items:
        lines.append(f"[{icon_map[item.status]}] {item.name}：{item.message}")
        if item.detail:
            compact = json.dumps(item.detail, ensure_ascii=False, default=str)
            lines.append(f"       {compact}")
    counts = {status: sum(1 for item in items if item.status == status) for status in ("ok", "warn", "fail")}
    lines.append("-" * 32)
    lines.append(f"汇总：OK {counts['ok']} / WARN {counts['warn']} / FAIL {counts['fail']}")
    return "\n".join(lines)


async def async_main() -> int:
    args = build_parser().parse_args()
    checker = InsightEnvChecker(
        timeout=args.timeout,
        skip_network=args.skip_network,
        skip_playwright=args.skip_playwright,
        probe_paid=args.probe_paid,
    )
    items = await checker.run()
    if args.json:
        payload = {"items": [asdict(item) for item in items]}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(render_text(items))

    has_fail = any(item.status == "fail" for item in items)
    has_warn = any(item.status == "warn" for item in items)
    if has_fail or (args.strict and has_warn):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(async_main()))
