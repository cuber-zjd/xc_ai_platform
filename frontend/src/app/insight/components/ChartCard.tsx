import { insightChartPalette } from "../theme/chart-theme";
import { SectionCard } from "./SectionCard";

interface ChartCardProps {
    title: string;
    description?: string;
}

const bars = [62, 78, 48, 88, 70, 56, 92];

export function ChartCard({ title, description }: ChartCardProps) {
    return (
        <SectionCard title={title} description={description}>
            <div className="h-64 rounded-[var(--insight-radius-lg)] border border-border bg-linear-to-b from-card to-muted/40 p-4">
                <div className="flex h-full items-end gap-3 border-b border-l border-border/80 px-2 pb-2">
                    {bars.map((value, index) => (
                        <div key={value + index} className="flex flex-1 flex-col items-center gap-2">
                            <div
                                className="w-full max-w-10 rounded-t-xl"
                                style={{
                                    height: `${value}%`,
                                    backgroundColor: insightChartPalette[index % insightChartPalette.length],
                                    opacity: 0.9,
                                }}
                            />
                            <span className="text-[11px] font-medium text-muted-foreground">{`W${index + 1}`}</span>
                        </div>
                    ))}
                </div>
            </div>
        </SectionCard>
    );
}
