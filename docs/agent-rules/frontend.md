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
- 项目视觉已切换为浅色玻璃卡片、柔和紫蓝渐变点缀、超圆角布局和 App-in-App 容器。
- 用户侧与管理后台应共享同一套品牌语言：悬浮侧边栏、轻雾面板、柔和投影、低饱和状态色。
- 新页面优先复用 `frontend/src/index.css` 中的 `app-shell`、`app-sidebar`、`app-stage`、`app-panel`、`app-panel-soft`、`app-page`、`app-page-header`、`app-kicker`、`app-subtle-text` 等全局类。
- 除非用户明确要求，页面内不要生成黑色或近黑色的大面积卡片；强调信息优先使用浅色渐变、浅底高亮或描边卡片表达。
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

- 历史任务第一版：页面需要通过 `GET /api/v1/fr/ai-reports/tasks` 展示最近任务，允许点击恢复旧任务并沿用 `conversationId` 继续生成下一轮修订。
- 页面必须提供“新建会话”入口，清空当前任务、步骤状态、文件选择和 SQL/DSL mutation 缓存；新会话下一次生成 SQL 时不得沿用旧任务的 `conversationId`。
- 人工反馈第一版：当前任务可提交“可用”或“需调整”反馈，统一调用 `POST /api/v1/fr/ai-reports/tasks/{task_id}/feedback`，为后续经验检索和自驱进化沉淀样本。
- 页面入口：`frontend/src/features/fr-ai-report/pages/FrAiReportChatPage.tsx`。
- API hooks：`frontend/src/features/fr-ai-report/hooks/useFrAiReport.ts`，统一通过 `frontend/src/api/client.ts` 调用 `/api/v1/fr/ai-reports`。
- 当前交互改为步骤工作台，第一步聚焦“生成 SQL 并预览数据”，第二步聚焦“生成 ReportDSL 并基于 DSL 预览”，使用步骤条展示阶段进度。
- 第一步输入区集中承载报表名称、自然语言需求、人工补充修改意见、相关表名和 Excel 模板上传，允许反复调整后重新生成。
- 第一步结果区优先展示 SQL 文本、SQL 校验摘要、样例数据表格、需求摘要和 Excel 字段识别结果，不再默认展示 FineReport iframe 预览。
- 第二步结果区展示 ReportDSL JSON 和 DSL 表格预览；DSL 预览由前端根据 `reportDsl.layout`、`horizontalExpansion` 与 `sqlValidation.sampleRows` 渲染，不依赖 FineReport 预览地址。
- DSL 预览和模板资源需要优先展示 `reportDsl.reportMeta` / Excel `templateAnalysis` 中的标题、单位、更新时间、均价、备注和筛选条件，避免这些模板级信息散落或丢失。
- 步骤条需要支持点击切换已具备条件的前后步骤；第一步回到 SQL 和数据预览，第二步回到 DSL 设计和 DSL 预览。已有 DSL 时再次点击“重新生成 DSL 并预览”会携带人工修改意见作为 `dsl_feedback`。
- 工作台左右两侧都应按当前步骤收拢内容：第一步只展示 SQL 输入、SQL 结果、数据预览、需求摘要和模板字段；第二步只展示 DSL 修改意见、DSL 预览和 ReportDSL，避免跨步骤内容混在同一区域。
- DSL 预览需要识别 `layout.designHints.specialRows`。当存在 `latest_change_row` 时，预览只取最新日期的涨跌指标，作为单独一行放在横向市场列下方、价格明细行上方。
- 第一步接口优先调用 `POST /api/v1/fr/ai-reports/steps/sql/generate`；第二步接口调用 `POST /api/v1/fr/ai-reports/steps/dsl/generate`；第三步接口调用 `POST /api/v1/fr/ai-reports/steps/cpt/generate` 生成 CPT、上传 MinIO staging 并返回 FineReport 预览地址；完整报表生成接口和后续步骤接口并存。
- 路由：用户侧路由 `/fr-ai-reports`，在 `frontend/src/router/index.tsx` 中懒加载。
- 交互形态：左侧聊天输入自然语言需求和上传 Excel，右侧展示 SQL、DSL 预览、ReportDSL、Excel 字段分析和校验提示；分步骤阶段不默认展示 FineReport `previewUrl` iframe。
- 当前阶段只支持表格类报表页面，不展示图表类能力入口；需求引导要贴近周报、分组表、交叉表这类业务样式。
- 可见文案必须使用中文；页面继续沿用浅色玻璃卡片、柔和紫蓝点缀、App-in-App 容器和暗色兼容风格。
- 前端不得生成 CPT/XML，只展示后端返回的结构化 ReportDSL，并可用 DSL 与样例数据做轻量预览。

## 9. SAP 助手前端

- 用户入口：`/sap-assistant`；管理入口：`/admin/sap-systems`。
- SAP 助手页面采用“左侧聊天 + 右侧动态工作区”，必须展示执行时间线，让用户知道 AI 当前正在识别系统、调用工具、读取源码、查询 DDIC、查询 ZILOG 或整理证据。
- 右侧动态工作区至少包含时间线、证据、工具结果和血缘图四类视图。
- SAP 证据不得只塞进聊天文本；源码、日志、DDIC、数据样例和知识库片段需要用可展开卡片或结构化面板展示。
- 流式协议在现有 `agent-workspace` 基础上扩展 `evidence`、`flowchart`、`system_context` 和 `tool_status` 类型。
- 生产系统或敏感查询应通过明确的人工确认卡片呈现查询范围、系统、对象、字段和最大行数。

## 10. Insight 业务域前端风格隔离

- Insight 业务域目录为 `frontend/src/app/insight/`，用于“研发营销市场洞察平台”。
- Insight 页面必须通过 `/insight/*` 路由挂载到独立 `InsightLayout`，不得复用旧系统 `UserLayout`、`AdminLayout` 或页面级 `app-*` 容器样式。
- Insight 主题通过 `InsightThemeScope` 挂载 `data-app="insight"` 与 `.insight-theme`，并在 `frontend/src/app/insight/theme/tokens.css` 内局部重声明 shadcn/ui CSS variables。
- 新增 Insight 页面优先复用 `frontend/src/app/insight/components/` 下的页面级组件，例如 `PageTitle`、`SectionCard`、`FilterBar`、`InsightTag`、`DataTableCard`、`ChartCard`。
- Insight 风格 token、业务语义色和图表规范分别维护在 `theme/tokens.css`、`theme/semantic-colors.ts`、`theme/chart-theme.ts`，不得通过修改 `:root` 或旧系统全局样式实现换肤。
- Insight 可复用 shadcn/ui 基础组件，但对外视觉必须由 insight 局部 token 和封装组件控制，避免旧系统紫蓝玻璃风格污染新业务域。
