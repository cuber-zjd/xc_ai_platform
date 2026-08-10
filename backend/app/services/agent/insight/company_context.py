from __future__ import annotations

from typing import Any


def insight_company_business_context(company_name: str) -> str:
    """返回所属产业公司的真实业务边界，供选材、生成和审校复用。"""
    if "健源" in company_name:
        return (
            "健源以玉米精深加工和淀粉糖为核心，重点关注果葡糖浆、麦芽糖浆、功能糖、"
            "糖醇、葡萄糖及其他玉米加工制成的糖类产品，以及这些产品在饮料、茶咖、乳品、"
            "烘焙和食品加工中的具体应用。客户、竞对、政策、技术和市场材料必须能够落到上述"
            "实际产品、配方应用、供需价格、产能或采购变化；只有泛食品、泛消费、门店扩张或"
            "品牌经营信息，但未涉及健源实际产品及其应用的，不予采用。原料端若只有宽泛玉米"
            "行情、信息量过少或口径过于庞杂，无法说明与玉米制糖生产的关系，也不予采用。"
        )
    if "御馨" in company_name:
        return (
            "御馨只聚焦蛋白板块，重点关注蛋白类竞对企业的市场、产品、产能、客户和技术动态，"
            "以及饮料、乳品、肉制品、烘焙、健康食品等下游企业在大豆蛋白、植物蛋白及蛋白"
            "应用领域的新布局、新产品与新进展。植物油、豆油、大豆油、食用油品牌和油脂加工"
            "动态不属于本简报范围，即使与大豆产业链相关也不予采用。原料端仅聚焦非转基因大豆"
            "的供需、价格、进口、种植、采购与政策变化；普通大豆、豆油或宽泛农产品行情不采用。"
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
            "玉米深加工",
            "玉米糖",
            "淀粉糖",
            "果葡糖浆",
            "麦芽糖",
            "葡萄糖",
            "糖浆",
            "功能糖",
            "糖醇",
            "赤藓糖醇",
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
        if not has_own_business:
            return "健源材料未涉及果糖、淀粉糖或玉米加工糖类等实际产品及其应用"
        if headline_is_other_business and not downstream_or_market_value:
            return "跨产业公司材料：大豆或植物蛋白为主，且无健源核心业务直接关系"

    if "御馨" in company_name:
        protein_business = (
            "植物蛋白",
            "大豆蛋白",
            "蛋白粉",
            "蛋白肽",
            "蛋白棒",
            "蛋白饮料",
            "植物基饮料",
            "豆乳",
            "豆奶",
            "豆粕",
            "分离蛋白",
            "浓缩蛋白",
            "组织蛋白",
            "拉丝蛋白",
            "替代蛋白",
        )
        oil_business = ("植物油", "豆油", "大豆油", "食用油", "油脂", "玉米油", "菜籽油")
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
        has_protein_business = any(value in primary_text for value in protein_business)
        has_non_gmo_soybean = any(
            value in primary_text
            for value in ("非转基因大豆", "非转基因豆", "non-gmo soybean", "non gmo soybean")
        )
        headline_is_oil = any(value in headline_text for value in oil_business)
        headline_is_unrelated = any(value in headline_text for value in unrelated_business)
        downstream_or_market_value = any(
            value in primary_text
            for value in (
                "饮料", "乳品", "肉制品", "烘焙", "茶饮", "咖啡", "食品", "新品",
                "扩店", "销量", "采购", "配方", "供应链", "消费", "健康", "监管", "客户",
            )
        )
        if headline_is_oil or (
            any(value in primary_text for value in oil_business)
            and not has_protein_business
            and not has_non_gmo_soybean
        ):
            return "御馨不纳入植物油、豆油及食用油相关动态"
        if not has_protein_business and not has_non_gmo_soybean:
            return "御馨材料未涉及蛋白业务、下游蛋白应用或非转基因大豆原料"
        if headline_is_unrelated and not downstream_or_market_value:
            return "跨产业公司材料：茶饮、糖类或玉米业务为主，且无御馨大豆或植物蛋白直接关系"

    return None


def _stringify_material_value(value: Any) -> str:
    if isinstance(value, (list, tuple, set)):
        return " ".join(str(item) for item in value)
    if isinstance(value, dict):
        return " ".join(f"{key} {item}" for key, item in value.items())
    return str(value or "")
