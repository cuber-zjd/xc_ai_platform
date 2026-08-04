from __future__ import annotations

from typing import Any


def insight_company_business_context(company_name: str) -> str:
    """返回所属产业公司的真实业务边界，供选材、生成和审校复用。"""
    if "健源" in company_name:
        return (
            "健源以玉米精深加工和淀粉糖为核心，重点关注果葡糖浆、麦芽糖浆、功能糖、"
            "糖醇及其在饮料、茶咖、乳品、烘焙和食品加工中的应用。选材不仅包括直接出现"
            "上述产品的资讯，也包括茶饮、饮料、烘焙、乳品等客户及潜在客户的新品、扩店、"
            "销量、经营、渠道和供应链变化，以及食品消费、减糖趋势、监管政策、替代配料和"
            "相关技术变化；只要能为销售、市场、研发、采购或经营判断提供清晰启示即可纳入。"
            "大豆蛋白、蛋白粉和豆粕等御馨业务资讯，仅在能影响健源客户、替代配料、竞争格局"
            "或食品行业需求时作为辅助材料，不得写成健源自身业务。"
        )
    if "御馨" in company_name:
        return (
            "御馨以大豆精深加工和植物蛋白为核心，重点关注大豆蛋白、蛋白粉、豆粕及其在"
            "饮料、乳品、肉制品、烘焙和茶咖中的应用。选材不仅包括直接出现大豆或植物蛋白"
            "的资讯，也包括上述客户及潜在客户的新品、扩店、销量、经营、渠道和供应链变化，"
            "以及健康食品、植物基消费、食品监管、配方趋势、替代蛋白和相关技术变化；只要能"
            "为销售、市场、研发、采购或经营判断提供清晰启示即可纳入。果葡糖浆、麦芽糖浆、"
            "功能糖和糖醇等健源业务资讯，仅在能影响御馨客户、复配应用、竞争格局或食品行业"
            "需求时作为辅助材料，不得写成御馨自身业务。"
        )
    return (
        "香驰控股主要从事大豆、玉米精深加工，产品涉及植物蛋白、蛋白粉、豆粕、粮油、"
        "果葡糖浆、麦芽糖浆和功能糖；只保留可影响客户、竞对、研发、销售、采购或"
        "供应链判断的具体事实。"
    )


def insight_company_material_rejection_reason(
    company_name: str,
    item: dict[str, Any],
) -> str | None:
    """只拦截明确错公司且无法形成业务启示的材料，宽口径价值判断交给编辑模型。"""
    headline_text = str(item.get("title") or "").lower()
    primary_text = " ".join(
        (
            _stringify_material_value(item.get("title")),
            _stringify_material_value(item.get("summary")),
            _stringify_material_value(item.get("content"))[:1500],
            _stringify_material_value(item.get("tags")),
            _stringify_material_value(item.get("subject_name")),
            _stringify_material_value(item.get("category")),
        )
    ).lower()

    if "健源" in company_name:
        own_business = (
            "玉米",
            "淀粉糖",
            "果葡糖浆",
            "麦芽糖",
            "糖浆",
            "功能糖",
            "糖醇",
            "赤藓糖醇",
            "代糖",
            "甜味剂",
            "低gi",
            "低糖",
            "无糖",
        )
        other_business = (
            "大豆蛋白",
            "植物蛋白",
            "蛋白粉",
            "豆粕",
            "豆油",
            "大豆油",
            "大豆磷脂",
            "乳清蛋白",
            "禹王",
            "嘉华生物",
            "万得福",
        )
        has_own_business = any(value in primary_text for value in own_business)
        headline_is_other_business = any(value in headline_text for value in other_business)
        downstream_or_market_value = any(
            value in primary_text
            for value in (
                "茶饮", "饮料", "咖啡", "乳品", "烘焙", "食品", "新品", "扩店",
                "销量", "采购", "配方", "供应链", "消费", "减糖", "监管", "客户",
            )
        )
        if headline_is_other_business and not has_own_business and not downstream_or_market_value:
            return "跨产业公司材料：大豆或植物蛋白为主，且无健源核心业务直接关系"

    if "御馨" in company_name:
        own_business = (
            "大豆",
            "植物蛋白",
            "大豆蛋白",
            "蛋白饮料",
            "植物基饮料",
            "豆乳",
            "豆奶",
            "豆粕",
            "豆油",
            "大豆油",
            "大豆磷脂",
            "磷脂",
        )
        unrelated_business = (
            "果葡糖浆",
            "麦芽糖浆",
            "淀粉糖",
            "糖浆",
            "功能糖",
            "糖醇",
            "赤藓糖醇",
            "代糖",
            "甜味剂",
            "玉米深加工",
            "玉米粉",
            "咖啡烘焙",
            "咖啡豆",
            "奶茶",
            "茶饮",
            "无糖茶",
            "低gi",
        )
        has_own_business = any(value in primary_text for value in own_business)
        headline_is_unrelated = any(value in headline_text for value in unrelated_business)
        downstream_or_market_value = any(
            value in primary_text
            for value in (
                "饮料", "乳品", "肉制品", "烘焙", "茶饮", "咖啡", "食品", "新品",
                "扩店", "销量", "采购", "配方", "供应链", "消费", "健康", "监管", "客户",
            )
        )
        if headline_is_unrelated and not has_own_business and not downstream_or_market_value:
            return "跨产业公司材料：茶饮、糖类或玉米业务为主，且无御馨大豆或植物蛋白直接关系"

    return None


def _stringify_material_value(value: Any) -> str:
    if isinstance(value, (list, tuple, set)):
        return " ".join(str(item) for item in value)
    if isinstance(value, dict):
        return " ".join(f"{key} {item}" for key, item in value.items())
    return str(value or "")
