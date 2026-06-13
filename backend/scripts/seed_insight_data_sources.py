"""根据御馨及健源市场洞察需求初始化第一批真实数据源。"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime
from typing import Any

from sqlmodel import select

from app.db.init_db import init_db
from app.db.session import async_session, engine
from app.models.agent.insight import InsightDataSource
from app.schemas.agent.insight.data_source import InsightDataSourceExecuteRequest
from app.services.agent.insight.data_source_service import insight_data_source_service

FILTER_PROMPT = (
    "只保留与企业经营动态、新品上市、产品型号、技术进展、市场布局、采购需求、"
    "财报公告、食品法规、供应链合作相关的信息；过滤招聘、纯广告、无关股吧、"
    "低质量转载和明显重复内容。"
)

SOURCES: list[dict[str, Any]] = [
    {
        "source_code": "yxjy_baidu_new_tea_drinks",
        "source_name": "健源-新茶饮客户新品与市场动态",
        "source_type": "baidu_news",
        "fetch_frequency": "daily",
        "fetch_config": {
            "keywords": ["蜜雪冰城 新品", "瑞幸 新品", "霸王茶姬 新品", "奈雪的茶 新品", "茶百道 新品", "喜茶 新品"],
            "include_keywords": ["蜜雪冰城", "瑞幸", "霸王茶姬", "奈雪", "茶百道", "喜茶", "新品", "上新", "推出", "上市", "开店", "供应链", "采购", "合作"],
            "exclude_keywords": ["招聘", "加盟骗局", "二手", "股吧"],
            "max_results": 8,
            "crawl_top_n": 2,
            "freshness": "noLimit",
            "schedule_type": "daily",
            "enable_llm_filter": True,
            "filter_prompt": FILTER_PROMPT,
            "llm_min_score": 0.65,
            "llm_failure_policy": "keep",
            "extra": {"business_line": "健源", "subject": "新茶饮客户"},
        },
    },
    {
        "source_code": "yxjy_baidu_f55_customers",
        "source_name": "健源-F55果糖客户经营与新品动态",
        "source_type": "baidu_news",
        "fetch_frequency": "daily",
        "fetch_config": {
            "keywords": ["可口可乐 新品", "百事 新品", "元气森林 新品", "农夫山泉 新品", "娃哈哈 新品", "蒙牛 伊利 新品"],
            "include_keywords": ["可口可乐", "百事", "元气森林", "农夫山泉", "娃哈哈", "蒙牛", "伊利", "新品", "上新", "推出", "上市", "饮料", "采购", "供应链", "合作"],
            "exclude_keywords": ["招聘", "促销", "优惠券"],
            "max_results": 8,
            "crawl_top_n": 2,
            "freshness": "noLimit",
            "schedule_type": "daily",
            "enable_llm_filter": True,
            "filter_prompt": FILTER_PROMPT,
            "extra": {"business_line": "健源", "subject": "F55果糖客户"},
        },
    },
    {
        "source_code": "yxjy_baidu_functional_sugar_competitors",
        "source_name": "健源-功能糖竞对价格新品与经营动态",
        "source_type": "baidu_news",
        "fetch_frequency": "daily",
        "fetch_config": {
            "keywords": ["中粮科技 功能糖", "保龄宝 赤藓糖醇", "三元生物 赤藓糖醇", "西王食品 新品", "益海嘉里 糖浆"],
            "include_keywords": ["新品", "价格", "经营", "财报", "公告", "赤藓糖醇", "功能糖"],
            "exclude_keywords": ["招聘", "股吧", "问答"],
            "max_results": 8,
            "crawl_top_n": 2,
            "freshness": "noLimit",
            "schedule_type": "daily",
            "enable_llm_filter": True,
            "filter_prompt": FILTER_PROMPT,
            "extra": {"business_line": "健源", "subject": "功能糖竞对"},
        },
    },
    {
        "source_code": "yxjy_bocha_soy_protein_competitors",
        "source_name": "御馨-大豆蛋白竞对技术与应用动态",
        "source_type": "bocha_news",
        "fetch_frequency": "daily",
        "fetch_config": {
            "keywords": ["禹王生态 大豆蛋白", "嘉华股份 大豆蛋白", "山松 大豆蛋白", "不二制油 大豆蛋白", "Roquette 植物蛋白"],
            "include_keywords": ["大豆蛋白", "植物蛋白", "产品", "型号", "技术", "应用", "产能"],
            "exclude_keywords": ["招聘", "招标", "股吧"],
            "max_results": 8,
            "crawl_top_n": 2,
            "freshness": "noLimit",
            "schedule_type": "daily",
            "enable_llm_filter": True,
            "filter_prompt": FILTER_PROMPT,
            "extra": {"business_line": "御馨", "subject": "大豆蛋白竞对"},
        },
    },
    {
        "source_code": "yxjy_bocha_health_customers",
        "source_name": "御馨-健康与特医客户产品需求动态",
        "source_type": "bocha_news",
        "fetch_frequency": "daily",
        "fetch_config": {
            "keywords": ["汤臣倍健 蛋白粉 新品", "养生堂 蛋白 产品", "康恩贝 特医食品", "雅培 特医 新品", "Kellogg 蛋白棒 新品"],
            "include_keywords": ["蛋白", "特医", "新品", "配料", "营养", "植物基"],
            "exclude_keywords": ["招聘", "优惠券", "直播带货"],
            "max_results": 8,
            "crawl_top_n": 2,
            "freshness": "noLimit",
            "schedule_type": "daily",
            "enable_llm_filter": True,
            "filter_prompt": FILTER_PROMPT,
            "extra": {"business_line": "御馨", "subject": "健康特医客户"},
        },
    },
    {
        "source_code": "yxjy_multi_industry_policy_trends",
        "source_name": "行业-食品法规政策与风味趋势",
        "source_type": "multi_news",
        "fetch_frequency": "daily",
        "fetch_config": {
            "keywords": ["食品添加剂 标准", "食品安全 法规", "植物蛋白 行业趋势", "茶饮 风味 趋势", "无糖饮料 甜味剂 趋势"],
            "include_keywords": ["标准", "法规", "趋势", "政策", "风味", "行业"],
            "exclude_keywords": ["培训广告", "论文代写", "招聘"],
            "max_results": 10,
            "crawl_top_n": 2,
            "freshness": "noLimit",
            "schedule_type": "daily",
            "enable_llm_filter": True,
            "filter_prompt": FILTER_PROMPT,
            "extra": {"business_line": "共用", "subject": "行业政策趋势"},
        },
    },
    {
        "source_code": "yxjy_multi_ecommerce_soy_protein_new_products",
        "source_name": "电商-大豆蛋白与植物肉新品监控",
        "source_type": "multi_news",
        "fetch_frequency": "daily",
        "fetch_config": {
            "keywords": ["大豆蛋白 蛋白棒 新品", "植物肉 新品 配料表", "蛋白粉 大豆蛋白 新品", "低脂植物蛋白 产品"],
            "include_keywords": ["新品", "配料", "蛋白", "植物肉", "销量", "排名"],
            "exclude_keywords": ["优惠券", "代购", "招聘"],
            "max_results": 8,
            "crawl_top_n": 1,
            "freshness": "noLimit",
            "schedule_type": "daily",
            "enable_llm_filter": True,
            "filter_prompt": FILTER_PROMPT,
            "extra": {"business_line": "御馨", "subject": "电商新品"},
        },
    },
    {
        "source_code": "yxjy_official_yuwang_protein",
        "source_name": "官网-禹王生态大豆蛋白",
        "source_type": "official_site",
        "base_url": "https://www.yuwangprotein.com/",
        "fetch_frequency": "daily",
        "fetch_config": {"keywords": ["禹王生态 大豆蛋白"], "crawl_top_n": 1, "schedule_type": "daily", "extra": {"business_line": "御馨", "subject": "竞对官网"}},
    },
    {
        "source_code": "yxjy_official_sinoglory_jiahua",
        "source_name": "官网-嘉华股份大豆蛋白",
        "source_type": "official_site",
        "base_url": "https://www.sinoglorygroup.com/",
        "fetch_frequency": "daily",
        "fetch_config": {"keywords": ["嘉华股份 大豆蛋白"], "crawl_top_n": 1, "schedule_type": "daily", "extra": {"business_line": "御馨", "subject": "竞对官网"}},
    },
    {
        "source_code": "yxjy_official_cofco_biochemical",
        "source_name": "官网-中粮科技投资者与公告",
        "source_type": "official_site",
        "base_url": "https://www.cofco.com/cn/Investors/COFCOBiochemical/",
        "fetch_frequency": "daily",
        "fetch_config": {"keywords": ["中粮科技 财报 公告"], "crawl_top_n": 1, "schedule_type": "daily", "extra": {"business_line": "健源", "subject": "上市竞对官网"}},
    },
    {
        "source_code": "yxjy_official_baolingbao",
        "source_name": "官网-保龄宝功能糖",
        "source_type": "official_site",
        "base_url": "https://www.blb-cn.com/",
        "fetch_frequency": "daily",
        "fetch_config": {"keywords": ["保龄宝 功能糖"], "crawl_top_n": 1, "schedule_type": "daily", "extra": {"business_line": "健源", "subject": "功能糖竞对官网"}},
    },
    {
        "source_code": "yxjy_official_foodaily",
        "source_name": "媒体-Foodaily每日食品",
        "source_type": "web_page",
        "base_url": "https://www.foodaily.com/",
        "fetch_frequency": "daily",
        "fetch_config": {"keywords": ["食品饮料 新品 趋势"], "crawl_top_n": 1, "schedule_type": "daily", "extra": {"business_line": "共用", "subject": "行业媒体"}},
    },
    {
        "source_code": "yxjy_official_fbif_foodtalks",
        "source_name": "媒体-FBIF食品饮料创新",
        "source_type": "web_page",
        "base_url": "https://www.foodtalks.cn/",
        "fetch_frequency": "daily",
        "fetch_config": {"keywords": ["食品饮料创新 新品 趋势"], "crawl_top_n": 1, "schedule_type": "daily", "extra": {"business_line": "共用", "subject": "行业媒体"}},
    },
    {
        "source_code": "yxjy_official_iff",
        "source_name": "官网-IFF风味与配料趋势",
        "source_type": "official_site",
        "base_url": "https://www.iff.com/",
        "fetch_frequency": "weekly",
        "fetch_config": {"keywords": ["IFF flavor trends ingredients"], "crawl_top_n": 1, "schedule_type": "weekly", "extra": {"business_line": "共用", "subject": "国际香精风味"}},
    },
]

DEFAULT_TEST_CODES = [
    "yxjy_official_sinoglory_jiahua",
    "yxjy_bocha_soy_protein_competitors",
    "yxjy_baidu_new_tea_drinks",
]


async def upsert_sources() -> dict[str, int]:
    created = 0
    updated = 0
    ids: dict[str, int] = {}
    async with async_session() as session:
        for item in SOURCES:
            row = (
                await session.exec(
                    select(InsightDataSource).where(InsightDataSource.source_code == item["source_code"])
                )
            ).first()
            if row is None:
                row = InsightDataSource(
                    source_code=item["source_code"],
                    source_name=item["source_name"],
                    source_type=item["source_type"],
                    base_url=item.get("base_url"),
                    fetch_frequency=item.get("fetch_frequency", "manual"),
                    fetch_config=item.get("fetch_config"),
                    status="enabled",
                    create_by="codex",
                    update_by="codex",
                )
                session.add(row)
                created += 1
            else:
                row.source_name = item["source_name"]
                row.source_type = item["source_type"]
                row.base_url = item.get("base_url")
                row.fetch_frequency = item.get("fetch_frequency", "manual")
                row.fetch_config = item.get("fetch_config")
                row.status = "enabled"
                row.update_by = "codex"
                row.update_time = datetime.now()
                updated += 1
            await session.flush()
            if row.id is not None:
                ids[item["source_code"]] = row.id
        await session.commit()
    print(f"数据源写入完成：新增 {created}，更新 {updated}，合计 {len(SOURCES)}")
    for item in SOURCES:
        print(f"- {item['source_code']} | {item['source_name']} | {item['source_type']} | {item.get('base_url') or '关键词搜索'}")
    return ids


async def execute_tests(ids: dict[str, int], test_codes: list[str]) -> None:
    print("\n开始代表性测试：")
    for code in test_codes:
        async with async_session() as session:
            source_id = ids[code]
            try:
                result = await insight_data_source_service.execute_data_source(
                    session,
                    source_id,
                    InsightDataSourceExecuteRequest(crawl_top_n=1),
                    user_id=None,
                )
            except Exception as exc:  # noqa: BLE001
                await session.rollback()
                print(f"[FAIL] {code}: {type(exc).__name__}: {str(exc)[:200]}")
                continue

            if result.manual_result:
                title = result.manual_result.candidate.candidate_title
                print(f"[OK] {code}: 官网抓取成功，候选标题={title[:80]}")
            elif result.search_result:
                hits = len(result.search_result.hits)
                crawled = len(result.search_result.crawled_results)
                candidates = len(result.search_result.candidates)
                first = result.search_result.hits[0].title if hits else "无"
                print(f"[OK] {code}: 发现 {hits}，抓取 {crawled}，候选 {candidates}，首条={first[:80]}")
            else:
                print(f"[WARN] {code}: 执行完成但无结果")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true", help="写入后执行少量代表性数据源")
    parser.add_argument("--skip-init-db", action="store_true", help="跳过 create_all 初始化")
    args = parser.parse_args()

    engine.echo = False
    if not args.skip_init_db:
        await init_db()
    ids = await upsert_sources()
    if args.test:
        await execute_tests(ids, DEFAULT_TEST_CODES)


if __name__ == "__main__":
    asyncio.run(main())
