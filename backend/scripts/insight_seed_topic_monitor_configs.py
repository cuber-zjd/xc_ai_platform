import asyncio
import logging
from datetime import datetime

from sqlmodel import select

from app.db.session import async_session
from app.models.agent.insight import InsightMonitorConfig
from app.models.system.sys_user import SysUser


TOPIC_SEEDS = [
    {
        "code": "topic_fructose_maltose_market",
        "name": "果葡糖浆与麦芽糖浆市场动态",
        "monitor_type": "industry",
        "modules": ["行业资讯", "综合舆情"],
        "keywords": ["果葡糖浆", "麦芽糖浆", "淀粉糖", "低糖配料", "饮料配料", "糖浆价格"],
        "prompt": "重点保留价格、供需、应用场景、饮料客户采购变化和竞品替代信号。",
    },
    {
        "code": "topic_plant_protein_opportunity",
        "name": "植物蛋白与蛋白粉机会动态",
        "monitor_type": "industry",
        "modules": ["行业资讯", "技术专利", "综合舆情"],
        "keywords": ["植物蛋白", "大豆蛋白", "蛋白粉", "功能蛋白", "蛋白饮料", "新蛋白"],
        "prompt": "重点保留新品、应用创新、客户采购、产能扩张、技术路线和监管变化。",
    },
    {
        "code": "topic_soybean_meal_grain_oil",
        "name": "豆粕粮油与大豆加工动态",
        "monitor_type": "market",
        "modules": ["经营财经", "行业资讯", "综合舆情"],
        "keywords": ["豆粕", "粮油", "大豆加工", "大豆压榨", "油脂油料", "饲料原料"],
        "prompt": "重点保留原料价格、压榨利润、库存、进出口、饲料需求和竞争格局变化。",
    },
    {
        "code": "topic_corn_deep_processing",
        "name": "玉米深加工与功能糖政策市场",
        "monitor_type": "policy",
        "modules": ["政策监管", "行业资讯", "技术专利"],
        "keywords": ["玉米深加工", "玉米加工", "功能糖", "赤藓糖醇", "低聚糖", "食品添加剂"],
        "prompt": "重点保留产业政策、食品添加剂监管、技术专利、功能糖应用和产能投资变化。",
    },
    {
        "code": "topic_beverage_tea_customers",
        "name": "饮料茶饮客户需求变化",
        "monitor_type": "topic",
        "modules": ["企业新闻", "电商新品", "行业资讯", "综合舆情"],
        "keywords": ["奶茶", "茶饮", "无糖饮料", "低糖饮料", "功能饮料", "食品饮料新品", "配料升级"],
        "prompt": "重点保留客户新品、配方趋势、低糖需求、供应链合作、招商采购和消费者偏好变化。",
    },
    {
        "code": "topic_food_safety_public_opinion",
        "name": "食品安全与质量舆情",
        "monitor_type": "public_opinion",
        "modules": ["政策监管", "综合舆情"],
        "keywords": ["食品安全", "食品质量投诉", "食品添加剂", "市场监管", "消费者投诉", "质量风险"],
        "prompt": "重点保留可能影响食品配料、饮料客户和农产品加工企业经营风险的监管和舆情信息。",
    },
]

logger = logging.getLogger(__name__)


async def main() -> None:
    async with async_session() as db:
        admin = (
            await db.exec(
                select(SysUser).where(
                    SysUser.is_deleted == 0,
                    SysUser.status == 1,
                ).order_by(SysUser.is_superuser.desc(), SysUser.id.asc())
            )
        ).first()
        owner_id = admin.id if admin else None
        now = datetime.now()
        created = 0
        updated = 0
        for seed in TOPIC_SEEDS:
            row = (
                await db.exec(
                    select(InsightMonitorConfig).where(
                        InsightMonitorConfig.config_code == seed["code"],
                        InsightMonitorConfig.is_deleted == 0,
                    )
                )
            ).first()
            payload = {
                "config_name": seed["name"],
                "monitor_type": seed["monitor_type"],
                "object_type": "topic",
                "object_name": seed["name"],
                "relation_type": "行业主题",
                "enabled_modules": seed["modules"],
                "keywords": seed["keywords"],
                "excluded_keywords": ["招聘", "无关论坛灌水", "网盘", "小说"],
                "monitor_strength": "standard",
                "fetch_frequency": "daily",
                "ai_review_prompt": seed["prompt"],
                "ai_review_policy": "ai_auto",
                "owner_user_id": owner_id,
                "visibility_scope": "assigned",
                "generation_mode": "system_seed",
                "schedule_enabled": True,
                "status": "active",
                "config_json": {"collection_budget": {"paid_search_calls_per_run": 1, "max_executed_channels_per_run": 6}},
                "next_run_time": now,
                "update_time": now,
                "update_by": str(owner_id) if owner_id else None,
            }
            if row:
                for key, value in payload.items():
                    setattr(row, key, value)
                updated += 1
            else:
                db.add(
                    InsightMonitorConfig(
                        config_code=seed["code"],
                        create_by=str(owner_id) if owner_id else None,
                        create_time=now,
                        **payload,
                    )
                )
                created += 1
        await db.commit()
        logger.info("Insight topic monitor configs seeded: created=%s updated=%s", created, updated)


if __name__ == "__main__":
    asyncio.run(main())
