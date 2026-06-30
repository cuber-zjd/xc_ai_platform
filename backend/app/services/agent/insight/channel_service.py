import re
from datetime import datetime
from uuid import uuid4

from sqlalchemy import func, or_
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.agent.insight import InsightChannel
from app.schemas.agent.insight.channel import InsightChannelCreate, InsightChannelRead, InsightChannelUpdate
from app.schemas.page import Page
from app.services.agent.insight.crawler.channel_adapter_service import insight_channel_adapter_service


class InsightChannelService:
    allowed_channel_types = {
        "enterprise_official",
        "industry_media",
        "finance_news",
        "policy_regulation",
        "patent_technology",
        "general_news",
        "ecommerce",
        "wechat_public_account",
        "database",
        "search_engine",
        "custom",
    }
    allowed_collection_methods = {"search", "list_page", "detail_page", "api", "rss", "file_import", "manual_import", "adapter", "pending"}
    allowed_login_requirements = {"none", "account_required", "licensed", "unknown"}
    allowed_access_statuses = {"supported", "partial", "pending", "unsupported"}
    allowed_trust_levels = {"high", "medium", "low"}
    allowed_frequencies = {"manual", "daily", "weekly", "monthly"}
    allowed_processing_policies = {"ai_review", "candidate_only", "do_not_import"}
    allowed_statuses = {"active", "disabled"}

    async def list_channels(
        self,
        db: AsyncSession,
        *,
        page: int,
        size: int,
        keyword: str | None = None,
        channel_type: str | None = None,
        access_status: str | None = None,
        status: str | None = None,
        scenario: str | None = None,
    ) -> Page[InsightChannelRead]:
        page = max(page, 1)
        size = min(max(size, 1), 100)
        filters = [InsightChannel.is_deleted == 0]
        if keyword:
            like_keyword = f"%{keyword.strip()}%"
            filters.append(
                or_(
                    InsightChannel.channel_name.ilike(like_keyword),
                    InsightChannel.channel_code.ilike(like_keyword),
                    InsightChannel.channel_url.ilike(like_keyword),
                )
            )
        if channel_type:
            filters.append(InsightChannel.channel_type == channel_type)
        if access_status:
            filters.append(InsightChannel.access_status == access_status)
        if status:
            filters.append(InsightChannel.status == status)
        if scenario:
            filters.append(InsightChannel.applicable_scenarios.contains([scenario.strip()]))

        total = (await db.exec(select(func.count()).select_from(InsightChannel).where(*filters))).one()
        statement = (
            select(InsightChannel)
            .where(*filters)
            .order_by(InsightChannel.sort_no.asc(), InsightChannel.update_time.desc(), InsightChannel.id.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
        rows = list((await db.exec(statement)).all())
        return Page.create(items=[self._to_read(row) for row in rows], total=total, page=page, size=size)

    async def create_channel(self, db: AsyncSession, payload: InsightChannelCreate, user_id: int | None) -> InsightChannelRead:
        self._validate(payload.model_dump())
        channel_code = self._normalize_code(payload.channel_code, payload.channel_name)
        await self._ensure_code_available(db, channel_code)
        row = InsightChannel(
            channel_code=channel_code,
            channel_name=payload.channel_name.strip(),
            channel_type=payload.channel_type.strip(),
            channel_url=(payload.channel_url or "").strip() or None,
            applicable_scenarios=self._dedupe_strings(payload.applicable_scenarios),
            collection_method=payload.collection_method,
            login_requirement=payload.login_requirement,
            access_status=self._adapter_access_status(channel_code, payload.access_status),
            default_trust_level=payload.default_trust_level,
            default_frequency=payload.default_frequency,
            default_processing_policy=payload.default_processing_policy,
            config_json=payload.config_json,
            sort_no=payload.sort_no,
            comment=payload.comment,
            status=payload.status,
            create_by=str(user_id) if user_id else None,
            update_by=str(user_id) if user_id else None,
        )
        self._sync_adapter_fields(row)
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return self._to_read(row)

    async def update_channel(self, db: AsyncSession, channel_id: int, payload: InsightChannelUpdate, user_id: int | None) -> InsightChannelRead:
        row = await self._get_channel(db, channel_id)
        data = payload.model_dump(exclude_unset=True)
        self._validate(data, partial=True)
        for field, value in data.items():
            if isinstance(value, str):
                value = value.strip()
            if field == "applicable_scenarios" and isinstance(value, list):
                value = self._dedupe_strings(value)
            if field == "channel_url" and value == "":
                value = None
            setattr(row, field, value)
        row.update_by = str(user_id) if user_id else None
        row.update_time = datetime.now()
        await db.commit()
        await db.refresh(row)
        return self._to_read(row)

    async def delete_channel(self, db: AsyncSession, channel_id: int, user_id: int | None) -> None:
        row = await self._get_channel(db, channel_id)
        row.is_deleted = 1
        row.status = "disabled"
        row.update_by = str(user_id) if user_id else None
        row.update_time = datetime.now()
        await db.commit()

    async def seed_default_channels(self, db: AsyncSession, user_id: int | None = None) -> dict[str, int]:
        created_count = 0
        updated_count = 0
        skipped_count = 0
        disabled_count = 0
        for item in DEFAULT_CHANNELS:
            code = self._normalize_code(str(item["channel_code"]), str(item["channel_name"]))
            existing = (await db.exec(select(InsightChannel).where(InsightChannel.channel_code == code, InsightChannel.is_deleted == 0))).first()
            if existing:
                changed = False
                payload = InsightChannelCreate(**item)
                update_values = {
                    "channel_name": payload.channel_name.strip(),
                    "channel_type": payload.channel_type.strip(),
                    "channel_url": (payload.channel_url or "").strip() or None,
                    "applicable_scenarios": self._dedupe_strings(payload.applicable_scenarios),
                    "collection_method": payload.collection_method,
                    "login_requirement": payload.login_requirement,
                    "access_status": payload.access_status,
                    "default_trust_level": payload.default_trust_level,
                    "default_frequency": payload.default_frequency,
                    "default_processing_policy": payload.default_processing_policy,
                    "config_json": payload.config_json,
                    "sort_no": payload.sort_no,
                    "comment": payload.comment,
                    "status": payload.status,
                }
                self._sync_adapter_values(code, update_values)
                for field, value in update_values.items():
                    if getattr(existing, field) != value:
                        setattr(existing, field, value)
                        changed = True
                if changed:
                    existing.update_by = str(user_id) if user_id else None
                    existing.update_time = datetime.now()
                    updated_count += 1
                else:
                    skipped_count += 1
                continue
            payload = InsightChannelCreate(**item)
            await self.create_channel(db, payload, user_id)
            created_count += 1
        deprecated_rows = list(
            (
                await db.exec(
                    select(InsightChannel).where(
                        InsightChannel.channel_code.in_(DEPRECATED_DEFAULT_CHANNEL_CODES),
                        InsightChannel.is_deleted == 0,
                    )
                )
            ).all()
        )
        for row in deprecated_rows:
            row.is_deleted = 1
            row.status = "disabled"
            row.update_by = str(user_id) if user_id else None
            row.update_time = datetime.now()
            disabled_count += 1
        if updated_count or disabled_count:
            await db.commit()
        return {"created_count": created_count, "updated_count": updated_count, "skipped_count": skipped_count, "disabled_count": disabled_count}

    async def _get_channel(self, db: AsyncSession, channel_id: int) -> InsightChannel:
        row = (await db.exec(select(InsightChannel).where(InsightChannel.id == channel_id, InsightChannel.is_deleted == 0))).first()
        if not row:
            raise ValueError("渠道不存在")
        return row

    async def _ensure_code_available(self, db: AsyncSession, channel_code: str) -> None:
        row = (await db.exec(select(InsightChannel).where(InsightChannel.channel_code == channel_code, InsightChannel.is_deleted == 0))).first()
        if row:
            raise ValueError("渠道编码已存在")

    def _validate(self, data: dict, *, partial: bool = False) -> None:
        checks = {
            "channel_type": self.allowed_channel_types,
            "collection_method": self.allowed_collection_methods,
            "login_requirement": self.allowed_login_requirements,
            "access_status": self.allowed_access_statuses,
            "default_trust_level": self.allowed_trust_levels,
            "default_frequency": self.allowed_frequencies,
            "default_processing_policy": self.allowed_processing_policies,
            "status": self.allowed_statuses,
        }
        for field, allowed_values in checks.items():
            if field not in data:
                if partial:
                    continue
                continue
            value = data.get(field)
            if value not in allowed_values:
                raise ValueError(f"{field} 不支持：{value}")

    def _normalize_code(self, code: str | None, name: str) -> str:
        value = (code or "").strip().lower()
        if not value:
            value = re.sub(r"[^a-zA-Z0-9_]+", "_", name.strip().lower()).strip("_")
        if not value or not re.fullmatch(r"[a-zA-Z0-9_]{2,64}", value):
            value = f"channel_{uuid4().hex[:8]}"
        return value[:64]

    def _dedupe_strings(self, values: list[str] | None) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for item in values or []:
            value = str(item).strip()
            if not value or value in seen:
                continue
            seen.add(value)
            result.append(value)
        return result

    def _to_read(self, row: InsightChannel) -> InsightChannelRead:
        data = InsightChannelRead.model_validate(row, from_attributes=True)
        data.applicable_scenarios = data.applicable_scenarios or []
        return data

    def _adapter_access_status(self, channel_code: str, fallback: str) -> str:
        definition = insight_channel_adapter_service.definition_for(channel_code)
        if not definition:
            return fallback
        if definition.status == "supported":
            return "supported"
        if definition.status == "unstable":
            return "partial"
        return fallback

    def _sync_adapter_values(self, channel_code: str, values: dict) -> None:
        definition = insight_channel_adapter_service.definition_for(channel_code)
        if not definition:
            return
        if definition.status == "supported":
            values["access_status"] = "supported"
            values["collection_method"] = "adapter"
            config = dict(values.get("config_json") or {})
            config["adapter"] = {
                "status": definition.status,
                "kind": definition.adapter_kind,
                "task_dir": definition.task_dir,
                "script_name": definition.script_name,
                "function_name": definition.function_name,
                "priority": definition.priority,
            }
            values["config_json"] = config
            return
        if definition.status == "unstable":
            values["access_status"] = "partial"
            values["collection_method"] = "adapter"
            config = dict(values.get("config_json") or {})
            config["adapter"] = {
                "status": definition.status,
                "kind": definition.adapter_kind,
                "task_dir": definition.task_dir,
                "script_name": definition.script_name,
                "function_name": definition.function_name,
                "priority": definition.priority,
                "note": definition.note,
            }
            values["config_json"] = config

    def _sync_adapter_fields(self, row: InsightChannel) -> None:
        values = {
            "access_status": row.access_status,
            "collection_method": row.collection_method,
            "config_json": row.config_json,
        }
        self._sync_adapter_values(row.channel_code, values)
        row.access_status = values["access_status"]
        row.collection_method = values["collection_method"]
        row.config_json = values["config_json"]


MONITOR_SCENARIOS = ("企业新闻", "官网动态", "经营财经", "专利技术", "电商新品", "行业资讯", "政策监管", "技术专利", "综合舆情")


def _normalize_monitor_scenarios(values: list[str]) -> list[str]:
    """把渠道种子的细分类收敛到用户可理解的监测分类。"""

    result: list[str] = []

    def add(value: str) -> None:
        if value in MONITOR_SCENARIOS and value not in result:
            result.append(value)

    for raw_value in values:
        value = raw_value.strip()
        if not value:
            continue
        if value in MONITOR_SCENARIOS:
            add(value)
            continue
        if any(keyword in value for keyword in ("官网", "公告")):
            add("官网动态")
        if any(keyword in value for keyword in ("企业", "投融资")):
            add("企业新闻")
        if any(keyword in value for keyword in ("财经", "资本", "证券", "研报", "产业经济")):
            add("经营财经")
        if "电商" in value or "新品" in value:
            add("电商新品")
        if any(keyword in value for keyword in ("专利", "技术")):
            add("技术专利")
        if any(keyword in value for keyword in ("政策", "监管", "食品安全")):
            add("政策监管")
        if any(keyword in value for keyword in ("行业", "食品", "饮品", "茶饮", "功能", "营养", "植物", "蛋白", "糖酒", "粮油", "农产品", "供需", "价格")):
            add("行业资讯")
        if any(keyword in value for keyword in ("综合", "舆情", "区域", "观点")):
            add("综合舆情")

    return result or ["综合舆情"]


def _default_channel(
    code: str,
    name: str,
    channel_type: str,
    url: str | None,
    scenarios: list[str],
    *,
    method: str = "search",
    trust: str = "medium",
    frequency: str = "daily",
    sort_no: int,
    comment: str | None = None,
    execution_policy: dict | None = None,
) -> dict:
    policy = execution_policy or _default_execution_policy(code, channel_type, method)
    return {
        "channel_code": code,
        "channel_name": name,
        "channel_type": channel_type,
        "channel_url": url,
        "applicable_scenarios": _normalize_monitor_scenarios(scenarios),
        "collection_method": method,
        "access_status": "pending",
        "default_trust_level": trust,
        "default_frequency": frequency,
        "sort_no": sort_no,
        "comment": comment,
        "config_json": {"execution_policy": policy},
    }


def _default_execution_policy(code: str, channel_type: str, method: str) -> dict:
    if code == "baidu_news":
        return {
            "tier": "discovery",
            "cost_level": "low",
            "trigger_mode": "always",
            "role": "先发现线索，按监测对象合并关键词后执行",
        }
    if code == "bocha_search":
        return {
            "tier": "discovery",
            "cost_level": "paid",
            "trigger_mode": "quality_gap",
            "role": "付费补充源，仅在百度资讯结果不足或质量不足时调用",
        }
    if channel_type in {"industry_media", "finance_news", "general_news", "policy_regulation"}:
        return {
            "tier": "vertical",
            "cost_level": "medium",
            "trigger_mode": "channel_schedule",
            "role": "按频道或栏目统一采集，再归属到企业、主题和报告素材",
        }
    if channel_type in {"patent_technology", "database", "enterprise_official"}:
        return {
            "tier": "specialized",
            "cost_level": "medium",
            "trigger_mode": "low_frequency",
            "role": "专项低频渠道，按周、半月或明确触发时补充验证",
        }
    if method == "pending":
        return {
            "tier": "specialized",
            "cost_level": "medium",
            "trigger_mode": "adapter_pending",
            "role": "已纳入渠道库，等待独立适配器接入",
        }
    return {
        "tier": "custom",
        "cost_level": "medium",
        "trigger_mode": "manual_or_schedule",
        "role": "自定义渠道，按配置预算执行",
    }


DEFAULT_CHANNELS: tuple[dict, ...] = (
    _default_channel("baidu_news", "百度资讯", "search_engine", "https://news.baidu.com", list(MONITOR_SCENARIOS), method="api", trust="medium", sort_no=1, comment="默认搜索发现源：每个监测对象默认启用。优先用百度资讯做低成本发现，按监测对象合并关键词后搜索，再进入正文抓取和 AI 入库判断。"),
    _default_channel("bocha_search", "博查搜索", "search_engine", None, list(MONITOR_SCENARIOS), method="api", trust="medium", sort_no=2, comment="默认搜索发现源：每个监测对象默认启用，但按成本控制策略调用。建议先跑百度资讯，百度结果不足、命中质量低或需要补充网页线索时再调用博查；同一监测对象每日合并关键词、缓存去重并限制调用次数。"),
    _default_channel("eastmoney", "东方财富官网", "finance_news", "https://www.eastmoney.com", ["经营财经", "企业新闻", "资本市场"], trust="medium", sort_no=10),
    _default_channel("tonghuashun", "同花顺", "finance_news", "https://www.10jqka.com.cn", ["经营财经", "企业新闻", "资本市场"], trust="medium", sort_no=20),
    _default_channel("xueqiu", "雪球网", "finance_news", "https://xueqiu.com", ["经营财经", "投资者观点"], trust="medium", sort_no=30),
    _default_channel("wipo", "WIPO 专利数据库", "patent_technology", "https://patentscope.wipo.int", ["专利技术", "海外专利"], method="pending", trust="high", frequency="weekly", sort_no=40),
    _default_channel("cnipa", "CNIPA 国家知识产权局", "patent_technology", "https://www.cnipa.gov.cn", ["专利技术", "政策监管"], method="pending", trust="high", frequency="weekly", sort_no=50),
    _default_channel("ebiotrade", "生物通", "industry_media", "https://www.ebiotrade.com", ["生物技术", "科研进展", "行业资讯"], trust="medium", sort_no=60),
    _default_channel("36kr", "36氪", "general_news", "https://36kr.com", ["综合资讯", "投融资", "新消费"], trust="medium", sort_no=70),
    _default_channel("food_daily", "FoodDaily", "industry_media", "https://www.foodaily.com", ["行业资讯", "新品趋势", "食品创新"], trust="high", sort_no=80),
    _default_channel("sohu", "搜狐", "general_news", "https://www.sohu.com", ["综合资讯", "企业新闻"], trust="medium", sort_no=90),
    _default_channel("sina_finance", "新浪财经", "finance_news", "https://finance.sina.com.cn", ["经营财经", "企业新闻", "资本市场"], trust="medium", sort_no=100),
    _default_channel("drinknewspaper", "中国饮品快报", "industry_media", "https://www.drinknewspaper.com", ["饮品行业", "茶饮咖啡", "新品趋势"], trust="medium", sort_no=110),
    _default_channel("food_beverage_research", "食品饮料产业研究", "database", "https://www.fxbaogao.com/archives/industry/%E9%A3%9F%E5%93%81%E9%A5%AE%E6%96%99", ["行业研究", "研报资料", "食品饮料"], trust="medium", frequency="weekly", sort_no=120),
    _default_channel("kamen", "咖门", "industry_media", "https://www.kamencn.com", ["饮品行业", "茶饮咖啡", "行业趋势"], trust="medium", sort_no=130),
    _default_channel("huaon", "华经产业研究院", "database", "https://www.huaon.com", ["行业研究", "产业数据", "研报资料"], trust="medium", frequency="weekly", sort_no=140),
    _default_channel("shipin_huoban", "食品伙伴网", "industry_media", "https://www.foodmate.net", ["行业资讯", "政策监管", "食品安全"], trust="high", sort_no=150),
    _default_channel("toutiao", "今日头条", "general_news", "https://www.toutiao.com", ["综合资讯", "企业新闻", "舆情线索"], trust="medium", sort_no=160),
    _default_channel("tonghuashun_finance", "同花顺财经", "finance_news", "https://news.10jqka.com.cn", ["经营财经", "资本市场", "企业新闻"], trust="medium", sort_no=170),
    _default_channel("qq", "腾讯网", "general_news", "https://www.qq.com", ["综合资讯", "企业新闻"], trust="medium", sort_no=180),
    _default_channel("taiwan", "中国台湾网", "general_news", "https://www.taiwan.cn", ["综合资讯", "区域市场", "政策监管"], trust="high", sort_no=190),
    _default_channel("bjse", "北交所官网", "finance_news", "https://www.bse.cn", ["资本市场", "公告", "企业新闻"], method="pending", trust="high", sort_no=200),
    _default_channel("cnstock", "中国证券网", "finance_news", "https://www.cnstock.com", ["经营财经", "资本市场", "企业新闻"], trust="medium", sort_no=210),
    _default_channel("china_com", "中华网", "general_news", "https://www.china.com", ["综合资讯", "企业新闻"], trust="medium", sort_no=220),
    _default_channel("szse", "深圳证券交易所", "finance_news", "https://www.szse.cn", ["经营财经", "公告", "资本市场"], method="pending", trust="high", sort_no=230),
    _default_channel("stockstar", "证券之星", "finance_news", "https://www.stockstar.com", ["经营财经", "资本市场", "企业新闻"], trust="medium", sort_no=240),
    _default_channel("sse", "上海证券交易所", "finance_news", "https://www.sse.com.cn", ["经营财经", "公告", "资本市场"], method="pending", trust="high", sort_no=250),
    _default_channel("sina", "新浪", "general_news", "https://www.sina.com.cn", ["综合资讯", "企业新闻"], trust="medium", sort_no=260),
    _default_channel("sdxw", "闪电新闻", "general_news", "https://sdxw.iqilu.com", ["综合资讯", "区域市场", "企业新闻"], trust="medium", sort_no=270),
    _default_channel("zqrb", "证券日报", "finance_news", "https://www.zqrb.cn", ["经营财经", "资本市场", "企业新闻"], trust="medium", sort_no=280),
    _default_channel("foodinc", "小食代", "industry_media", "https://www.foodinc.com.cn", ["食品饮料", "企业新闻", "行业趋势"], trust="medium", sort_no=290),
    _default_channel("cet", "中国经济新闻网", "finance_news", "https://www.cet.com.cn", ["经营财经", "政策监管", "产业经济"], trust="medium", sort_no=300),
    _default_channel("xinhua", "新华网", "general_news", "https://www.news.cn", ["综合资讯", "政策监管"], trust="high", sort_no=310),
    _default_channel("shiye_toutiao", "食业头条", "industry_media", None, ["糖酒食品", "行业资讯", "渠道动态"], trust="medium", sort_no=320, comment="偏 APP/公众号渠道，待后续核准可抓取网页入口。"),
    _default_channel("people", "人民网", "general_news", "https://www.people.com.cn", ["综合资讯", "政策监管"], trust="high", sort_no=330),
    _default_channel("netease_news", "网易新闻", "general_news", "https://news.163.com", ["综合资讯", "企业新闻"], trust="medium", sort_no=340),
    _default_channel("xinyingyang", "新营养", "industry_media", "https://xinyingyang.com", ["营养健康", "功能食品", "行业趋势"], trust="medium", sort_no=350),
    _default_channel("sanxin_food", "三新特食汇", "policy_regulation", None, ["新食品原料", "食品添加剂", "政策监管"], trust="medium", frequency="weekly", sort_no=360, comment="名称更像三新食品资讯聚合或公众号，后续接入时需核准稳定网页入口。"),
    _default_channel("plant_based_net", "植物基网", "industry_media", None, ["植物基", "新蛋白", "食品创新"], trust="medium", sort_no=370, comment="待核准稳定网页入口。"),
    _default_channel("functional_food_circle", "功能食品圈", "industry_media", "https://yanfa.foodmate.net/hangye/?action=gnsp", ["功能食品", "营养健康", "行业研究"], trust="medium", sort_no=380),
    _default_channel("yunti", "云梯网", "custom", None, ["行业资讯", "待核准"], trust="low", frequency="weekly", sort_no=390, comment="原始清单仅给出名称，需业务侧确认具体网站。"),
    _default_channel("gmw", "光明网", "general_news", "https://www.gmw.cn", ["综合资讯", "政策监管"], trust="high", sort_no=400),
    _default_channel("daily_food", "每日食品", "industry_media", "https://www.foodaily.com", ["食品饮料", "新品趋势", "食品创新"], trust="high", sort_no=410),
    _default_channel("doupo_wang", "豆粕王", "custom", None, ["农产品", "粮油行情", "专家观点"], trust="low", frequency="weekly", sort_no=420, comment="更像人物或栏目称呼，先作为搜索型渠道占位。"),
    _default_channel("grainnews", "粮油市场报", "industry_media", "https://grainnews.com.cn", ["粮油行业", "农产品", "政策监管"], trust="high", sort_no=430),
    _default_channel("taishan_finance", "泰山财经", "finance_news", "https://f.sdnews.com.cn", ["经营财经", "区域市场", "企业新闻"], trust="medium", sort_no=440),
    _default_channel("chinagrain", "粮信网", "industry_media", "https://www.chinagrain.cn", ["粮油行情", "农产品", "供需价格"], trust="medium", sort_no=450),
    _default_channel("chinastock", "银河证券", "finance_news", "https://www.chinastock.com.cn", ["券商研报", "资本市场", "经营财经"], method="pending", trust="medium", frequency="weekly", sort_no=460),
    _default_channel("food_industry_observe", "食品产业观察市场信息网", "industry_media", "https://business.cctv.com/special/yswcy/home/index.shtml", ["食品产业", "产业观察", "市场信息"], trust="medium", sort_no=470, comment="原始名称未给出明确官网，先关联央视网产业观察入口，后续可核准替换。"),
    _default_channel("cctv_news", "央视新闻网", "general_news", "https://news.cctv.com", ["综合资讯", "政策监管"], trust="high", sort_no=480),
    _default_channel("new_protein", "新蛋白", "industry_media", "https://foodsustainability.cn", ["新蛋白", "合成生物", "食品创新"], trust="medium", sort_no=490),
    _default_channel("yntw", "云糖网", "industry_media", "https://www.yntw.com", ["糖业行情", "农产品", "供需价格"], trust="medium", sort_no=500),
)


DEPRECATED_DEFAULT_CHANNEL_CODES = ("baidu_search", "bocha_news", "bocha_web", "multi_news_search")


insight_channel_service = InsightChannelService()
