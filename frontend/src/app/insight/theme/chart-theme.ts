export const insightChartPalette = [
    "#2563eb",
    "#0891b2",
    "#0f766e",
    "#7c3aed",
    "#ca8a04",
    "#dc2626",
    "#475569",
];

export const insightChartTheme = {
    colors: insightChartPalette,
    axis: {
        lineColor: "#cbd5e1",
        tickColor: "#94a3b8",
        labelColor: "#64748b",
        labelFontSize: 12,
    },
    grid: {
        lineColor: "#e2e8f0",
        lineDash: [4, 4],
    },
    tooltip: {
        backgroundColor: "rgba(15, 23, 42, 0.92)",
        borderColor: "rgba(148, 163, 184, 0.28)",
        color: "#f8fafc",
        borderRadius: 12,
        padding: 12,
    },
    legend: {
        color: "#475569",
        inactiveColor: "#94a3b8",
        itemGap: 16,
        itemWidth: 10,
        itemHeight: 10,
    },
    line: {
        strokeWidth: 2,
        dotRadius: 3,
        activeDotRadius: 5,
    },
    bar: {
        radius: [8, 8, 0, 0],
        maxBarWidth: 34,
    },
    pie: {
        borderWidth: 2,
        borderColor: "#ffffff",
        labelColor: "#475569",
    },
} as const;

export type InsightChartTheme = typeof insightChartTheme;
