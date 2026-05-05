# 前端开发规则

本文件适用于修改 `frontend/` 下的页面、组件、路由、状态、API 调用和样式。

## 1. 技术栈

- React 19 + TypeScript。
- Vite。
- Tailwind CSS v4。
- Shadcn/ui + Radix UI。
- 图标使用 `lucide-react`。
- 服务端状态使用 TanStack Query。
- 全局状态使用 Zustand。
- 包管理器使用 `pnpm`。

## 2. 目录约定

- 页面入口放在 `frontend/src/pages/`。
- 复杂业务模块放在 `frontend/src/features/<feature>/`。
- 通用布局和业务组件放在 `frontend/src/components/`。
- 基础 UI 组件放在 `frontend/src/components/ui/`。
- API 调用放在 `frontend/src/api/`。
- 全局状态放在 `frontend/src/store/`。
- 工具函数放在 `frontend/src/lib/`。

复杂业务模块建议结构：

```text
features/contract/
├── components/
├── hooks/
├── pages/
└── types.ts
```

## 3. TypeScript 与 React 规范

- 组件文件使用 `PascalCase`。
- hooks 使用 `camelCase`，文件名如 `useContract.ts`。
- 工具类文件可使用 `kebab-case`。
- 组件 props 使用 `interface` 定义。
- 导入顺序：React、第三方、组件、类型和工具。
- 页面和组件内的可见文本必须使用中文。
- 生产代码禁止 `console.log()`。

组件结构建议：

```tsx
import { useState } from "react";

interface Props {
  className?: string;
}

export function ExamplePanel({ className }: Props) {
  const [open, setOpen] = useState(false);

  return <div className={className}>内容</div>;
}
```

## 4. API 与状态

- 所有后端请求优先复用 `frontend/src/api/client.ts`。
- token 注入和 401 处理由 Axios 拦截器统一负责。
- 服务端数据查询使用 TanStack Query。
- 新增业务模块时，优先在模块内提供 `hooks/useXxx.ts`。
- 认证信息和用户信息通过 `useAuthStore` 管理。
- 不要在组件中散落重复的 URL、token 处理和响应解包逻辑。

## 5. UI 与样式

- 使用 Tailwind CSS v4，除全局动画和主题变量外不要新增零散 CSS 文件。
- 条件类名使用 `cn()`。
- 优先使用语义 token，例如 `bg-background`、`text-foreground`。
- 保持暗色模式可用。
- 项目视觉偏向 Zinc 单色、玻璃拟态、圆角布局和 App-in-App 容器。
- 状态色可以使用低饱和红、绿、蓝，但不能让页面变成高饱和色块。
- 按钮、卡片、列表项应有清晰 hover 和 transition。
- 路由切换、弹窗、折叠内容应保持平滑。
- 基础组件优先使用 Shadcn/ui，不做全局样式覆盖。
- 图标只使用 `lucide-react`。

## 6. 路由

- 路由集中维护在 `frontend/src/router/index.tsx`。
- 受保护页面必须经过 `ProtectedRoute`。
- 管理员页面必须经过 `AdminRoute`。
- 新页面需要考虑登录态、角色、懒加载和加载态文案。

## 7. 前端验证命令

```bash
cd frontend
pnpm install
pnpm lint
pnpm build
pnpm dev
```

## 8. FineReport AI 报表前端

- 页面入口：`frontend/src/features/fr-ai-report/pages/FrAiReportChatPage.tsx`。
- API hooks：`frontend/src/features/fr-ai-report/hooks/useFrAiReport.ts`，统一通过 `frontend/src/api/client.ts` 调用 `/api/v1/fr/ai-reports`。
- 路由：用户侧路由 `/fr-ai-reports`，在 `frontend/src/router/index.tsx` 中懒加载。
- 交互形态：左侧聊天输入自然语言需求和上传 Excel，右侧展示 FineReport `previewUrl` iframe、ReportDSL、SQL、Excel 字段分析和校验提示。
- 当前阶段只支持表格类报表页面，不展示图表类能力入口；需求引导要贴近周报、分组表、交叉表这类业务样式。
- 可见文案必须使用中文；页面继续沿用 Zinc 单色、玻璃拟态、App-in-App 容器和暗色兼容风格。
- 前端不得生成 CPT/XML，只展示后端返回的结构化 ReportDSL 和预览地址。
