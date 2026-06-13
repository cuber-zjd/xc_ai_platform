import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

const EMPTY_VALUE = "__insight_empty__";

interface InsightSelectOption {
    value: string;
    label: string;
}

interface InsightSelectProps {
    label?: string;
    value: string;
    options: InsightSelectOption[];
    onChange: (value: string) => void;
    placeholder?: string;
    className?: string;
    triggerClassName?: string;
}

export function InsightSelect({ label, value, options, onChange, placeholder, className, triggerClassName }: InsightSelectProps) {
    const trigger = (
        <Select value={value || EMPTY_VALUE} onValueChange={(nextValue) => onChange(nextValue === EMPTY_VALUE ? "" : nextValue)}>
            <SelectTrigger
                className={`h-11 w-full rounded-xl border-slate-200 bg-white px-3 text-sm font-semibold text-slate-700 shadow-none transition hover:border-blue-200 hover:bg-blue-50/30 focus:ring-4 focus:ring-blue-100 ${triggerClassName ?? ""}`}
            >
                <SelectValue placeholder={placeholder} />
            </SelectTrigger>
            <SelectContent className="z-[80] rounded-xl border-slate-200 bg-white p-1 shadow-[0_18px_48px_rgba(30,74,120,0.14)]">
                {options.map((option) => (
                    <SelectItem
                        key={option.value || option.label}
                        value={option.value || EMPTY_VALUE}
                        className="rounded-lg text-sm font-semibold text-slate-700 focus:bg-blue-50 focus:text-blue-700"
                    >
                        {option.label}
                    </SelectItem>
                ))}
            </SelectContent>
        </Select>
    );

    if (!label) {
        return <div className={className}>{trigger}</div>;
    }

    return (
        <div className={`grid gap-2 ${className ?? ""}`}>
            <span className="text-sm font-bold text-slate-700">{label}</span>
            {trigger}
        </div>
    );
}
