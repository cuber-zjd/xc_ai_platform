export default function DashboardPage() {
    return (
        <div className="space-y-6">
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
                {/* Stats Cards Mockup */}
                {[1, 2, 3, 4].map((i) => (
                    <div key={i} className="rounded-xl border bg-card text-card-foreground shadow p-6">
                        <div className="flex flex-row items-center justify-between space-y-0 pb-2">
                            <h3 className="tracking-tight text-sm font-medium">Total Revenue</h3>
                        </div>
                        <div className="text-2xl font-bold">$45,231.89</div>
                        <p className="text-xs text-muted-foreground">+20.1% from last month</p>
                    </div>
                ))}
            </div>
            <div className="min-h-[400px] flex items-center justify-center rounded-xl border border-dashed bg-muted/50">
                <span className="text-muted-foreground">Chart Area Placeholder</span>
            </div>
        </div>
    )
}
