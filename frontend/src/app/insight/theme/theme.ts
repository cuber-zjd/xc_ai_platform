export const insightTheme = {
    layout: {
        sidebarWidth: "17rem",
        headerHeight: "4.25rem",
        pageMaxWidth: "1480px",
    },
    radius: {
        xs: "0.5rem",
        sm: "0.75rem",
        md: "0.875rem",
        lg: "1rem",
        xl: "1.25rem",
    },
    shadow: {
        subtle: "0 1px 2px rgba(22, 66, 112, 0.08)",
        card: "0 10px 30px rgba(31, 76, 124, 0.07)",
        floating: "0 18px 46px rgba(22, 66, 112, 0.11)",
    },
    spacing: {
        pageX: "clamp(1rem, 2vw, 1.75rem)",
        pageY: "clamp(1rem, 2vw, 1.5rem)",
        sectionGap: "1rem",
        cardPadding: "1.25rem",
    },
    table: {
        rowHeight: 52,
        headerHeight: 44,
        density: "comfortable",
    },
    badge: {
        radius: "999px",
        height: "1.625rem",
    },
} as const;

export type InsightTheme = typeof insightTheme;
