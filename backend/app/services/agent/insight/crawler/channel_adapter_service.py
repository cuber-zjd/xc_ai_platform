import asyncio
import json
import os
import random
import re
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.agent.insight import InsightChannelAdapterRun, InsightCrawlerChannel
from app.services.agent.insight.crawler.search_client import InsightSearchHit


@dataclass(frozen=True, slots=True)
class AdapterDefinition:
    channel_code: str
    source_name: str
    task_dir: str
    script_name: str | None
    function_name: str | None
    status: str = "supported"
    adapter_kind: str = "playwright"
    cooldown_seconds: float = 10.0
    priority: str = "other"
    note: str | None = None


@dataclass(slots=True)
class AdapterRunContext:
    channel_id: int | None
    monitor_config_id: int | None
    run_type: str
    since: datetime
    limit: int
    user_id: int | None = None
    retry_count: int = 0
    timeout_seconds: int = 180


class InsightChannelAdapterService:
    """运行 crawler_research 迁移来的独立渠道适配器。"""

    base_dir = Path(__file__).resolve().parent / "research_sources"
    output_dir = Path(__file__).resolve().parents[5] / "storage" / "insight_adapter_runs"
    adapters: tuple[AdapterDefinition, ...] = (
        AdapterDefinition("eastmoney", "东方财富官网", "task_01_eastmoney", "test_eastmoney.py", None, status="adapter_pending", note="预研脚本为固定 run_crawler，需抽出按关键词检索函数"),
        AdapterDefinition("tonghuashun", "同花顺", "task_02_ths", "test_ths.py", None, status="adapter_pending", note="预研脚本绑定 HK2097/HK2555，需改造成通用关键词函数"),
        AdapterDefinition("xueqiu", "雪球网", "task_03_xueqiu", "test_token.py", None, status="unstable", note="当前脚本仅验证 token 和 API，需要补通用解析"),
        AdapterDefinition("wipo", "WIPO/CNIPA 专利数据库", "task_04_patent", "test_patent.py", "crawl_patent", priority="key", cooldown_seconds=10),
        AdapterDefinition("ebiotrade", "生物通", "task_05_biotech", "test_biotech.py", "crawl_biotech", priority="key"),
        AdapterDefinition("36kr", "36氪", "task_06_36kr", "test_36kr.py", "crawl_36kr"),
        AdapterDefinition("food_daily", "FoodDaily", "task_07_foodaily", "test_foodaily.py", "crawl_foodaily", priority="key"),
        AdapterDefinition("sohu", "搜狐", "task_08_sohu", "test_sohu.py", "crawl_sohu"),
        AdapterDefinition("qq", "腾讯网", "task_08_tencent", "test_tencent.py", "crawl_tencent"),
        AdapterDefinition("sina_finance", "新浪财经", "task_09_sina", "test_sina.py", "crawl_sina"),
        AdapterDefinition("drinknewspaper", "中国饮品快报", "task_10_cndrink", "test_cndrink.py", "crawl_cndrink", priority="key"),
        AdapterDefinition("shipin_huoban", "食品伙伴网", "task_11_foodmate", "test_foodmate.py", "crawl_foodmate", priority="key"),
        AdapterDefinition("kamen", "咖门", "task_12_kamen", "test_kamen.py", "crawl_kamen", priority="key"),
        AdapterDefinition("huaon", "华经产业研究院", "task_13_huaon", "test_huaon.py", "crawl_huaon"),
        AdapterDefinition("taiwan", "台海网", "task_13_taihainet", "test_taihainet.py", "crawl_taihainet"),
        AdapterDefinition("bjse", "北交所官网", "task_14_bse", "test_bse.py", "crawl_bse", priority="key"),
        AdapterDefinition("cnstock", "中国证券网", "task_15_cnstock", "test_cnstock.py", "crawl_cnstock"),
        AdapterDefinition("toutiao", "今日头条", "task_15_toutiao", "test_toutiao.py", "crawl_toutiao"),
        AdapterDefinition("china_com", "中华网", "task_16_china", "test_china.py", "crawl_china"),
        AdapterDefinition("szse", "深圳证券交易所", "task_17_szse", "test_szse.py", "crawl_szse", priority="key"),
        AdapterDefinition("stockstar", "证券之星", "task_18_stockstar", "test_stockstar.py", "crawl_stockstar_base"),
        AdapterDefinition("sse", "上海证券交易所", "task_19_sse", "test_sse.py", "crawl_sse", priority="key"),
        AdapterDefinition("bjnews", "新京报", "task_20_bjnews", "test_bjnews.py", "crawl_bjnews"),
        AdapterDefinition("sdxw", "闪电新闻", "task_21_lightning", "test_lightning.py", "crawl_lightning"),
        AdapterDefinition("zqrb", "证券日报", "task_22_zqrb", "test_zqrb.py", "crawl_zqrb"),
        AdapterDefinition("foodinc", "小食代", "task_23_xiaoshidai", "test_xiaoshidai.py", "crawl_xiaoshidai", priority="key"),
        AdapterDefinition("xinhua", "新华网", "task_24_xinhuanet", "test_xinhuanet.py", "crawl_xinhuanet"),
        AdapterDefinition("shiye_toutiao", "食业头条", "task_25_shiyetoutiao", "test_shiyetoutiao.py", "crawl_shiyetoutiao", priority="key"),
        AdapterDefinition("people", "人民网", "task_26_people", "test_people.py", "crawl_people"),
        AdapterDefinition("netease_news", "网易新闻", "task_27_163", "test_netease.py", "crawl_netease"),
        AdapterDefinition("xinyingyang", "新营养", "task_28_xinyingyang", "test_xinyingyang.py", "crawl_xinyingyang", priority="key"),
        AdapterDefinition("sanxin_food", "三新特食汇", "task_29_foodmate", None, None, status="adapter_pending", note="目录暂无 test_*.py"),
        AdapterDefinition("yntw", "云糖网", "task_30_yntw", "test_yntw.py", "crawl_yntw", priority="key"),
        AdapterDefinition("gmw", "光明网", "task_31_gmw", "test_gmw.py", "crawl_gmw"),
        AdapterDefinition("grainnews", "粮油市场报", "task_32_grainnews", "test_grainnews.py", "crawl_grainnews", priority="key"),
        AdapterDefinition("taishan_finance", "泰山财经", "task_33_tscj", "test_tscj.py", "crawl_tscj"),
        AdapterDefinition("chinagrain", "粮信网", "task_34_chinagrain", "test_chinagrain.py", "crawl_chinagrain", priority="key"),
        AdapterDefinition("chinastock", "银河证券", "task_35_galaxy", "test_galaxy.py", "crawl_galaxy", adapter_kind="http", cooldown_seconds=5),
        AdapterDefinition("food_industry_observe", "食品产业观察市场信息网", "task_36_cnfood", "test_cnfood.py", "crawl_cnfood", priority="key"),
        AdapterDefinition("cctv_news", "央视新闻网", "task_37_cctv", "test_cctv.py", "crawl_cctv"),
        AdapterDefinition("new_protein", "新蛋白", "task_38_newprotein", "test_newprotein.py", "crawl_newprotein", adapter_kind="http", priority="key"),
    )

    def supported_channel_codes(self) -> set[str]:
        return {item.channel_code for item in self.adapters if item.status == "supported"}

    def definitions(self) -> list[dict[str, Any]]:
        return [asdict(definition) for definition in self.adapters]

    def definition_for(self, channel_code: str) -> AdapterDefinition | None:
        return next((item for item in self.adapters if item.channel_code == channel_code), None)

    async def search(
        self,
        db: AsyncSession,
        channel_code: str,
        keyword: str,
        *,
        context: AdapterRunContext,
    ) -> list[InsightSearchHit]:
        definition = self.definition_for(channel_code)
        if not definition:
            raise ValueError(f"未注册渠道适配器：{channel_code}")
        run = InsightChannelAdapterRun(
            channel_id=context.channel_id,
            channel_code=channel_code,
            monitor_config_id=context.monitor_config_id,
            keyword=keyword[:300],
            run_type=context.run_type,
            status="running",
            retry_count=context.retry_count,
            request_payload={"keyword": keyword, "since": context.since.isoformat(), "limit": context.limit},
            adapter_metadata={"definition": asdict(definition)},
            create_by=str(context.user_id) if context.user_id else None,
            update_by=str(context.user_id) if context.user_id else None,
        )
        db.add(run)
        await db.commit()
        await db.refresh(run)
        started = time.perf_counter()
        try:
            if definition.status != "supported":
                raise ValueError(definition.note or f"{channel_code} 适配器暂未稳定接入")
            rows = await self._execute_with_retries(db, run, definition, keyword, timeout_seconds=context.timeout_seconds)
            raw_path = self._write_raw_output(run.id or 0, definition, keyword, rows)
            hits = self._to_hits(definition, rows, keyword, context.since, context.limit, run.id or 0)
            run.status = "success" if hits else "skipped"
            run.hit_count = len(rows) if isinstance(rows, list) else 0
            run.kept_count = len(hits)
            run.page_url = self._first_url(rows)
            run.raw_output_path = raw_path
            run.response_excerpt = json.dumps(rows[:3] if isinstance(rows, list) else rows, ensure_ascii=False, default=str)[:2000]
            return hits
        except Exception as exc:
            run.status = "failed"
            run.error_type = exc.__class__.__name__
            run.error_message = str(exc)[:2000]
            run.response_excerpt = str(exc)[:2000]
            run.raw_output_path = self._write_failure_output(run.id or 0, definition, keyword, exc)
            raise
        finally:
            run.finished_at = datetime.now()
            run.duration_ms = int((time.perf_counter() - started) * 1000)
            run.update_time = datetime.now()
            await db.commit()
            await self._cooldown(definition)

    async def _execute_definition(
        self,
        definition: AdapterDefinition,
        keyword: str,
        *,
        timeout_seconds: int,
    ) -> list[dict[str, Any]]:
        if not definition.script_name or not definition.function_name:
            raise ValueError(definition.note or "适配器缺少可执行函数")
        script_path = self.base_dir / definition.task_dir / definition.script_name
        if not script_path.exists():
            raise FileNotFoundError(f"适配器脚本不存在：{script_path}")
        runtime_dir = self.output_dir / "runtime_cwd" / definition.channel_code
        runtime_dir.mkdir(parents=True, exist_ok=True)
        output_dir = self.output_dir / "subprocess_output" / definition.channel_code
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{datetime.now():%Y%m%d%H%M%S%f}_{random.randint(1000, 9999)}.json"
        wrapper = self._subprocess_wrapper()
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            wrapper,
            str(script_path),
            definition.function_name,
            keyword,
            str(output_path),
            cwd=str(runtime_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=os.environ | {"PYTHONIOENCODING": "utf-8"},
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout_seconds)
        except TimeoutError as exc:
            process.kill()
            await process.communicate()
            raise TimeoutError(f"{definition.channel_code} 适配器执行超过 {timeout_seconds} 秒") from exc
        stdout_text = stdout.decode("utf-8", errors="replace") if stdout else ""
        stderr_text = stderr.decode("utf-8", errors="replace") if stderr else ""
        if process.returncode != 0:
            message = "\n".join(part for part in [stderr_text.strip(), stdout_text.strip()] if part)
            raise RuntimeError(message[:2000] or f"{definition.channel_code} 适配器子进程失败")
        if not output_path.exists():
            raise RuntimeError((stdout_text or stderr_text or "适配器未生成输出文件")[:2000])
        data = json.loads(output_path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise ValueError(f"适配器返回值不是列表：{type(data).__name__}")
        return [item for item in data if isinstance(item, dict)]

    async def _execute_with_retries(
        self,
        db: AsyncSession,
        run: InsightChannelAdapterRun,
        definition: AdapterDefinition,
        keyword: str,
        timeout_seconds: int,
    ) -> list[dict[str, Any]]:
        max_attempts = 2
        last_exc: Exception | None = None
        for attempt in range(max_attempts):
            try:
                return await self._execute_definition(definition, keyword, timeout_seconds=timeout_seconds)
            except Exception as exc:
                last_exc = exc
                run.retry_count = attempt
                run.error_type = exc.__class__.__name__
                run.error_message = str(exc)[:2000]
                run.response_excerpt = str(exc)[:2000]
                if attempt + 1 >= max_attempts:
                    break
                run.status = "retrying"
                run.retry_count = attempt + 1
                run.update_time = datetime.now()
                await db.commit()
                await asyncio.sleep(5 + random.uniform(0, 3))
        if last_exc:
            raise last_exc
        raise RuntimeError("适配器重试异常结束")

    def _subprocess_wrapper(self) -> str:
        return r"""
import importlib.util
import inspect
import json
import pathlib
import sys
import traceback

script_path, function_name, keyword, output_path = sys.argv[1:5]
try:
    spec = importlib.util.spec_from_file_location("insight_channel_adapter_runtime", script_path)
    if not spec or not spec.loader:
        raise ImportError(f"无法加载适配器脚本：{script_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    func = getattr(module, function_name, None)
    if not callable(func):
        raise AttributeError(f"适配器函数不存在：{function_name}")
    signature = inspect.signature(func)
    positional = [
        param
        for param in signature.parameters.values()
        if param.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    ]
    required_count = len([param for param in positional if param.default is inspect.Parameter.empty])
    result = func(keyword, keyword) if required_count >= 2 else func(keyword)
    if not isinstance(result, list):
        raise ValueError(f"适配器返回值不是列表：{type(result).__name__}")
    pathlib.Path(output_path).write_text(json.dumps(result, ensure_ascii=False, default=str), encoding="utf-8")
except Exception:
    traceback.print_exc()
    sys.exit(1)
"""

    def _to_hits(
        self,
        definition: AdapterDefinition,
        rows: list[dict[str, Any]],
        keyword: str,
        since: datetime,
        limit: int,
        run_id: int,
    ) -> list[InsightSearchHit]:
        hits: list[InsightSearchHit] = []
        seen: set[str] = set()
        for row in rows:
            title = str(row.get("title") or "").strip()
            url = str(row.get("url") or "").strip()
            if not title or not url or url in seen:
                continue
            published_at = self._parse_time(row.get("created_at") or row.get("published_at"))
            if published_at and published_at < since:
                continue
            seen.add(url)
            hits.append(
                InsightSearchHit(
                    channel=InsightCrawlerChannel.GENERIC_WEB,
                    title=title,
                    url=url,
                    snippet=str(row.get("content") or row.get("summary") or "")[:800] or None,
                    published_at=published_at,
                    raw={
                        "source": "channel_adapter",
                        "source_channel": definition.channel_code,
                        "source_name": definition.source_name,
                        "keyword": keyword,
                        "adapter_kind": definition.adapter_kind,
                        "adapter_run_id": run_id,
                        "raw": row,
                    },
                )
            )
            if len(hits) >= limit:
                break
        return hits

    def _parse_time(self, value: Any) -> datetime | None:
        if not value:
            return None
        text = str(value).strip().replace("/", "-").replace(".", "-")
        text = re.sub(r"T", " ", text)
        text = re.sub(r"([+-]\d{2}:?\d{2}|Z)$", "", text).strip()
        try:
            return datetime.fromisoformat(text)
        except ValueError:
            pass
        for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                return datetime.strptime(text, pattern)
            except ValueError:
                continue
        return None

    def _write_raw_output(self, run_id: int, definition: AdapterDefinition, keyword: str, rows: list[dict[str, Any]]) -> str:
        day_dir = self.output_dir / datetime.now().strftime("%Y%m%d") / definition.channel_code
        day_dir.mkdir(parents=True, exist_ok=True)
        safe_keyword = re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff_-]+", "_", keyword)[:60] or "keyword"
        path = day_dir / f"run_{run_id}_{safe_keyword}.json"
        path.write_text(json.dumps(rows, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        return str(path)

    def _write_failure_output(self, run_id: int, definition: AdapterDefinition, keyword: str, exc: Exception) -> str:
        day_dir = self.output_dir / datetime.now().strftime("%Y%m%d") / definition.channel_code
        day_dir.mkdir(parents=True, exist_ok=True)
        safe_keyword = re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff_-]+", "_", keyword)[:60] or "keyword"
        path = day_dir / f"run_{run_id}_{safe_keyword}_failed.json"
        payload = {
            "channel_code": definition.channel_code,
            "source_name": definition.source_name,
            "keyword": keyword,
            "error_type": exc.__class__.__name__,
            "error_message": str(exc),
            "failed_at": datetime.now().isoformat(),
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        return str(path)

    def _first_url(self, rows: Any) -> str | None:
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, dict) and row.get("url"):
                    return str(row["url"])[:1200]
        return None

    async def _cooldown(self, definition: AdapterDefinition) -> None:
        seconds = max(0.0, definition.cooldown_seconds + random.uniform(0, 2))
        if seconds:
            await asyncio.sleep(seconds)

    async def recent_run_map(self, db: AsyncSession, channel_codes: list[str]) -> dict[str, InsightChannelAdapterRun]:
        if not channel_codes:
            return {}
        rows = list(
            (
                await db.exec(
                    select(InsightChannelAdapterRun)
                    .where(InsightChannelAdapterRun.channel_code.in_(channel_codes), InsightChannelAdapterRun.is_deleted == 0)
                    .order_by(InsightChannelAdapterRun.started_at.desc())
                    .limit(len(channel_codes) * 5)
                )
            ).all()
        )
        result: dict[str, InsightChannelAdapterRun] = {}
        for row in rows:
            result.setdefault(row.channel_code, row)
        return result


insight_channel_adapter_service = InsightChannelAdapterService()
