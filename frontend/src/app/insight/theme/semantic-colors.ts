export type InsightStatus = "success" | "warning" | "error" | "info";

export type InsightBusinessTag = "newProduct" | "financialReport" | "regulation" | "industryNews" | "solution" | "keyUpdate";

export const insightStatusColors: Record<InsightStatus, { label: string; text: string; bg: string; border: string }> = {
    success: {
        label: "成功",
        text: "text-emerald-700 dark:text-emerald-300",
        bg: "bg-emerald-50 dark:bg-emerald-950/40",
        border: "border-emerald-200/80 dark:border-emerald-800/70",
    },
    warning: {
        label: "预警",
        text: "text-amber-700 dark:text-amber-300",
        bg: "bg-amber-50 dark:bg-amber-950/40",
        border: "border-amber-200/80 dark:border-amber-800/70",
    },
    error: {
        label: "风险",
        text: "text-rose-700 dark:text-rose-300",
        bg: "bg-rose-50 dark:bg-rose-950/40",
        border: "border-rose-200/80 dark:border-rose-800/70",
    },
    info: {
        label: "信息",
        text: "text-sky-700 dark:text-sky-300",
        bg: "bg-sky-50 dark:bg-sky-950/40",
        border: "border-sky-200/80 dark:border-sky-800/70",
    },
};

export const insightBusinessColors: Record<InsightBusinessTag, { label: string; className: string }> = {
    newProduct: {
        label: "新品",
        className: "border-cyan-200 bg-cyan-50 text-cyan-700 dark:border-cyan-800 dark:bg-cyan-950/40 dark:text-cyan-300",
    },
    financialReport: {
        label: "财报",
        className: "border-blue-200 bg-blue-50 text-blue-700 dark:border-blue-800 dark:bg-blue-950/40 dark:text-blue-300",
    },
    regulation: {
        label: "法规",
        className: "border-violet-200 bg-violet-50 text-violet-700 dark:border-violet-800 dark:bg-violet-950/40 dark:text-violet-300",
    },
    industryNews: {
        label: "行业资讯",
        className: "border-slate-200 bg-slate-50 text-slate-700 dark:border-slate-700 dark:bg-slate-900/60 dark:text-slate-300",
    },
    solution: {
        label: "应用方案",
        className: "border-teal-200 bg-teal-50 text-teal-700 dark:border-teal-800 dark:bg-teal-950/40 dark:text-teal-300",
    },
    keyUpdate: {
        label: "重点动态",
        className: "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-300",
    },
};
