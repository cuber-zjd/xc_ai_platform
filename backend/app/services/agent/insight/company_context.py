from __future__ import annotations

from typing import Any


def insight_company_business_context(company_name: str) -> str:
    """返回所属产业公司的真实业务边界，供选材、生成和审校复用。"""
    if "健源" in company_name:
        return (
            "健源以玉米精深加工和淀粉糖为核心，重点关注果葡糖浆、麦芽糖浆、功能糖、"
            "糖醇及其在饮料、茶咖、乳品、烘焙和食品加工中的应用；材料必须能落到"
            "配方、采购、产能、价格、客户经营或监管准入。大豆蛋白、蛋白粉和豆粕不是"
            "健源月报的核心业务，除非事件能直接影响玉米深加工或淀粉糖业务。"
        )
    if "御馨" in company_name:
        return (
            "御馨以大豆精深加工和植物蛋白为核心，重点关注大豆蛋白、蛋白粉、豆粕及其在"
            "饮料、乳品、肉制品、烘焙和茶咖中的应用；客户、竞对和原料变化必须能落到"
            "配方应用、采购需求、供应链、产能、价格或食品合规。果葡糖浆、麦芽糖浆、"
            "功能糖和糖醇不是御馨月报的核心业务，除非事件能直接影响大豆或植物蛋白业务。"
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
    """按产业公司边界拦截跨业务材料，避免仅靠模型相关性判断。"""
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

    generic_policy_terms = (
        "食品安全法",
        "食品标识",
        "食品监管",
        "市场监管",
        "进出口",
        "海关",
        "关税",
        "外贸",
    )
    has_generic_policy = any(value in primary_text for value in generic_policy_terms)

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
        if headline_is_other_business and not has_own_business:
            return "跨产业公司材料：大豆或植物蛋白为主，且无健源核心业务直接关系"
        if not has_own_business and not has_generic_policy:
            return "标题、摘要或监测主题缺少健源玉米深加工或糖类业务直接事实"

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
        if headline_is_unrelated and not has_own_business:
            return "跨产业公司材料：茶饮、糖类或玉米业务为主，且无御馨大豆或植物蛋白直接关系"
        if not has_own_business:
            if has_generic_policy:
                return "通用政策未明确涉及御馨大豆、植物蛋白或其产品准入"
            return "标题、摘要或监测主题缺少御馨大豆及植物蛋白业务的直接事实"

    return None


def _stringify_material_value(value: Any) -> str:
    if isinstance(value, (list, tuple, set)):
        return " ".join(str(item) for item in value)
    if isinstance(value, dict):
        return " ".join(f"{key} {item}" for key, item in value.items())
    return str(value or "")
