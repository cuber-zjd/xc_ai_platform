import { ChevronDown } from "lucide-react";

import { HeaderMeta, SearchField } from "../components/DemoPrimitives";

export function InsightHeader() {
    return (
        <header className="sticky top-0 z-20 flex h-[88px] items-center justify-between border-b border-slate-200 bg-white/95 px-8 backdrop-blur-xl">
            <div className="mx-auto w-full max-w-[1480px]">
                <div className="flex items-center justify-between gap-6">
                    <div className="w-full max-w-[390px]">
                        <SearchField />
                    </div>
                    <div className="flex items-center gap-7">
                        <HeaderMeta />
                        <div className="flex items-center gap-3">
                            <div className="size-10 rounded-full border-2 border-blue-100 bg-linear-to-br from-blue-100 to-orange-100" />
                            <span className="text-sm font-bold text-slate-800">张伟</span>
                            <ChevronDown className="size-4 text-slate-500" />
                        </div>
                    </div>
                </div>
            </div>
        </header>
    );
}
