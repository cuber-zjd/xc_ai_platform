import { Outlet } from "react-router-dom";

import { InsightThemeScope } from "../theme/InsightThemeScope";
import { InsightMobileNav, InsightSidebar } from "./InsightSidebar";

export function InsightLayout() {
    return (
        <InsightThemeScope>
            <div className="insight-shell">
                <InsightSidebar />
                <div className="insight-main">
                    <div className="insight-content">
                        <Outlet />
                    </div>
                    <InsightMobileNav />
                </div>
            </div>
        </InsightThemeScope>
    );
}
