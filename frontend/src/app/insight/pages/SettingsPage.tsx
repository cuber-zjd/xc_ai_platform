import { Settings } from "lucide-react";

import { EmptyState, PageTitle } from "../components";
import { PageContainer } from "../layout/PageContainer";

export function SettingsPage() {
    return (
        <PageContainer>
            <PageTitle title="系统设置" description="静态 demo 阶段暂不接入接口，后续可在此配置用户权限、标签字典、推送策略和模型参数。" />
            <EmptyState icon={<Settings className="size-5" />} title="设置能力待接入" description="当前页面保持 insight 统一视觉风格，后续按业务接口继续扩展。" />
        </PageContainer>
    );
}
