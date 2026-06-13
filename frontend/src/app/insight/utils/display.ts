const intelligenceTypeText: Record<string, string> = {
    strategic_planning: "战略规划",
    strategy: "战略规划",
    marketing_strategy: "营销策略",
    competitor_strategy: "竞品动态",
    competitor: "竞品动态",
    product_launch: "新品情报",
    product_launch_failure: "新品情报",
    new_product: "新品情报",
    financial_report: "财报公告",
    financial: "财报公告",
    industry_news: "行业资讯",
    industry: "行业资讯",
    policy: "政策法规",
    regulation: "政策法规",
    application_solution: "应用方案",
    technology: "应用方案",
    business_operation: "经营动态",
    operation: "经营动态",
    risk_warning: "风险预警",
    risk: "风险预警",
    "csr/esg": "企业社会责任/ESG",
    corporate_social_responsibility: "企业社会责任",
    "corporate_strategy_&_esg": "战略规划",
    market_analysis: "市场分析",
    market_expansion: "市场扩张",
    market_trend: "市场趋势",
};

export function formatInsightType(value?: string | null) {
    if (!value) return "行业资讯";
    const normalized = value.trim().toLowerCase().replace(/[-\s]+/g, "_");
    if (intelligenceTypeText[normalized]) return intelligenceTypeText[normalized];
    if (/^[a-z0-9_]+$/i.test(value)) return "行业资讯";
    return value;
}

export function formatInsightDate(primary?: string | null, fallback?: string | null) {
    if (primary) return formatDateTime(primary);
    if (fallback) return `发布时间未知 · 抓取 ${formatDateTime(fallback)}`;
    return "发布时间未知";
}

export function formatDateTime(value?: string | null) {
    if (!value) return "-";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value.slice(0, 16);
    const pad = (input: number) => String(input).padStart(2, "0");
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}
