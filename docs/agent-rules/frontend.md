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
- 除 `/insight/*` 等明确独立设计的业务域外，项目视觉已切换为接近 ChatGPT 的极简中性产品壳：浅灰固定侧边栏、冷白主内容区、黑白灰为主、轻描边和克制阴影。
- 默认主题点缀色采用当前 SAP 助手确认过的青绿色体系，用于选中态、轻量标签、聚焦态、状态提示、快捷入口和少量品牌强调；页面整体仍以冷白、浅灰和中性色为主。
- 用户侧与管理后台应共享同一套中性壳语言：紧凑侧边栏、清晰分区、轻量列表项、少量青绿色状态点缀，不再使用大面积紫蓝玻璃渐变、黑底模块或偏黄旧纸感背景。
- 新页面优先复用 `frontend/src/index.css` 中的 `app-shell`、`app-sidebar`、`app-stage`、`app-panel`、`app-panel-soft`、`app-page`、`app-page-header`、`app-kicker`、`app-subtle-text` 等全局类。
- 除非用户明确要求，页面内不要生成高饱和渐变或装饰性玻璃卡片；强调信息优先使用白底、浅灰底、轻描边或紧凑列表表达。
- 状态色可以使用低饱和红、青绿、蓝，但不能让页面变成高饱和色块；青绿色是默认主点缀，不代表整页都要变成单一绿色。
- 助手类智能区域默认遵循“聊天优先、上下文隐藏”：第一屏只展示对话流和输入框，结构读取、工具结果、版本中心、环境信息、待应用修改和调试详情放入弹窗、抽屉、折叠面板或图标入口中按需打开。
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
- 真实报表目录左侧树需要支持用户级显示范围配置：默认显示全部；用户可在“显示范围”弹窗中勾选文件夹或单个报表，保存后主树只展示已选择范围，偏好通过 `GET/PUT /api/v1/fr/ai-reports/files/visibility-preference` 持久化。
- 选择真实报表文件后，前端通过 `GET /api/v1/fr/ai-reports/files/structure` 在线读取后端解析结果，并在右侧副驾驶区域展示报表结构摘要、数据集、参数和 SQL 片段；中间画布基于 `document.sheets[0]` 渲染真实行列、单元格、合并区域和基础样式，属性面板展示当前单元格坐标、合并跨度、字段绑定、样式摘要和原始节点路径；前端不直接读取或解析 CPT/XML 原文。
- 当前新建入口不再承载 AI 需求收集流程，只创建空白 CPT 并保存到指定目录；后续 SQL、ReportDSL、样式、填报和版本发布都在选中该报表后通过右侧小驰侧边栏完成。
- 第一步输入区集中承载报表名称、自然语言需求、人工补充修改意见、相关表名和 Excel 模板上传，允许反复调整后重新生成。
- 第一步结果区优先展示 SQL 文本、SQL 校验摘要、样例数据表格、需求摘要和 Excel 字段识别结果，不再默认展示 FineReport iframe 预览。
- 第二步结果区展示 ReportDSL JSON 和 DSL 表格预览；DSL 预览由前端根据 `reportDsl.layout`、`horizontalExpansion` 与 `sqlValidation.sampleRows` 渲染，不依赖 FineReport 预览地址。
- DSL 预览和模板资源需要优先展示 `reportDsl.reportMeta` / Excel `templateAnalysis` 中的标题、单位、更新时间、均价、备注和筛选条件，避免这些模板级信息散落或丢失。
- 步骤条需要支持点击切换已具备条件的前后步骤；第一步回到 SQL 和数据预览，第二步回到 DSL 设计和 DSL 预览。已有 DSL 时再次点击“重新生成 DSL 并预览”会携带人工修改意见作为 `dsl_feedback`。
- 工作台左右两侧都应按当前步骤收拢内容：第一步只展示 SQL 输入、SQL 结果、数据预览、需求摘要和模板字段；第二步只展示 DSL 修改意见、DSL 预览和 ReportDSL，避免跨步骤内容混在同一区域。
- DSL 预览需要识别 `layout.designHints.specialRows`。当存在 `latest_change_row` 时，预览只取最新日期的涨跌指标，作为单独一行放在横向市场列下方、价格明细行上方。
- 第一步接口优先调用 `POST /api/v1/fr/ai-reports/steps/sql/generate`；第二步接口调用 `POST /api/v1/fr/ai-reports/steps/dsl/generate`；第三步接口调用 `POST /api/v1/fr/ai-reports/steps/cpt/generate` 或 AI 草稿 CPT 入口生成 CPT，支持用户指定 `webroot/APP/reportlets/` 目标路径，并通过版本中心查看、冲突处理和回档；完整报表生成接口和后续步骤接口并存。
- 新建报表弹窗只保留报表名称和保存目录，调用 `POST /api/v1/fr/ai-reports/empty/create` 生成空白 CPT 并写入版本库；弹窗内不得上传资料、运行 SQL/DSL 或调用 `agent/chat`。侧边栏小驰才负责基于当前报表进行聊天式生成和修改。
- 侧边栏小驰主界面保持聊天优先：默认只展示对话流、多行输入框、附件入口和少量动作按钮；上下文、工具、技能、待应用修改项、版本和执行轨迹默认折叠或放入弹窗。
- 小驰工具和技能信息通过 `GET /api/v1/fr/ai-reports/agent/capabilities` 获取，前端只负责展示、启用系统技能和收集个人开发习惯；不得在前端伪造工具成功、扩大工具权限或绕过后端确认门。
- 小驰聊天输入使用 `POST /api/v1/fr/ai-reports/agent/chat`，后端通过大模型语义路由判断普通沟通、当前报表修改、开始生成或保存 CPT；前端按钮只表达用户明确点击的快捷动作，普通输入不得在前端用关键词重做一套意图判断或固定流程编排。
- 小驰待应用修改项确认成功后，前端应清空待应用列表和本轮提示词，只保留已应用快照 ID 用于后续生成 CPT；旧修改项不得继续进入下一轮 `agent/chat` 上下文。只有状态为 `draft` 且操作类型全部为 `xml_patch` 的内容才能展示确认按钮；其他操作类型不得伪装成可确认修改。
- 前端可应用操作白名单需要与后端 CPT 修改主路径同步，`xml_patch` 是唯一可确认类型；前端不得再用“样式、填报、脚本不支持”这类固定能力边界拦截用户需求，是否可写由后端版本控制、XML 校验和预览验证决定。待应用修改项面向用户只展示自然语言修改范围和风险提示，不展示原始 JSON 或 XML；中风险、高风险修改必须让用户在应用前明确确认。
- 帆软报表助手主界面不得摆放保存、撤销、公式、边框、填充等尚未接入真实行为的类设计器按钮；主操作区只保留真实可用入口，例如新建报表和 FineReport 预览。小驰生成待应用修改项后，应在输入框上方直接展示确认卡片，包含修改范围、风险和确认按钮，弹窗详情只作为补充查看。
- 小驰主回答优先展示后端返回的自然语言 `assistantMessage` 或工具产物摘要；前端兜底文案必须简短、贴合状态，避免把所有回答套成固定模板。
- 聊天事件需要以用户可读的执行轨迹展示，展示“计划/工具/结果/风险”，不展示模型原始思考；执行轨迹默认折叠，避免主界面拥挤。
- 路由：用户侧路由 `/fr-ai-reports`，在 `frontend/src/router/index.tsx` 中懒加载。
- 交互形态：左侧聊天输入自然语言需求和上传 Excel，右侧展示 SQL、DSL 预览、ReportDSL、Excel 字段分析和校验提示；分步骤阶段不默认展示 FineReport `previewUrl` iframe。
- 当前阶段只支持表格类报表页面，不展示图表类能力入口；需求引导要贴近周报、分组表、交叉表这类业务样式。
- 可见文案必须使用中文；页面视觉继续沿用全局 ChatGPT 式浅色产品壳和青绿色点缀，保留步骤工作台的信息分区能力，不再使用旧紫蓝玻璃风格。
- 前端不得生成 CPT/XML，只展示后端返回的结构化 ReportDSL，并可用 DSL 与样例数据做轻量预览。

### 数据集预览与连接

- 数据集详情应使用弹窗承载 SQL、参数和预览结果，避免在侧栏内展开过深内容。
- 数据库驱动下拉来自 `GET /api/v1/fr/ai-reports/database-drivers`，驱动是平台级选项；连接保存仍走当前用户的 `database-connections`。
- 连接表单不允许手写驱动字符串，当前只从 SQL Server 与 MySQL 8 两类驱动中选择。

## 9. SAP 助手前端

- 用户入口：`/sap-assistant`；管理入口：`/admin/sap-systems`。
- SAP 助手页面采用“左侧聊天 + 右侧动态工作区”，必须展示执行时间线，让用户知道 AI 当前正在识别系统、调用工具、读取源码、查询 DDIC、读取只读样例数据或整理证据。
- 右侧动态工作区至少包含时间线、证据、工具结果和血缘图四类视图。
- SAP 证据不得只塞进聊天文本；源码、日志、DDIC、只读样例数据和知识库片段需要用可展开卡片或结构化面板展示。
- SAP 助手页面需要提供本轮“思考模式”开关，默认关闭；用户使用 LM Studio 等本地模型时可手动关闭模型思考参数。
- 流式协议在现有 `agent-workspace` 基础上扩展 `evidence`、`flowchart`、`system_context` 和 `tool_status` 类型。
- 生产系统或敏感查询应通过明确的人工确认卡片呈现查询范围、系统、对象、字段和最大行数。

## 10. Insight 业务域前端风格隔离

- Insight 业务域目录为 `frontend/src/app/insight/`，用于“研发营销市场洞察平台”。
- Insight 页面必须通过 `/insight/*` 路由挂载到独立 `InsightLayout`，不得复用旧系统 `UserLayout`、`AdminLayout` 或页面级 `app-*` 容器样式。
- Insight AI 助手入口为 `/insight/assistant`，页面直接调用 `/api/v1/insight/assistant/chat` 和 `/api/v1/insight/research/deep`，回答和研究结论必须展示库内引用、情报详情入口和来源 URL，不得用前端静态内容伪造证据。
- Insight 质量运营入口为 `/insight/quality`，页面读取 `GET /api/v1/insight/quality/overview` 展示真实质量指标；缺数据图表必须展示空状态，不得使用样例点或假指标兜底。
- Insight 主题通过 `InsightThemeScope` 挂载 `data-app="insight"` 与 `.insight-theme`，并在 `frontend/src/app/insight/theme/tokens.css` 内局部重声明 shadcn/ui CSS variables。
- 新增 Insight 页面优先复用 `frontend/src/app/insight/components/` 下的页面级组件，例如 `PageTitle`、`SectionCard`、`FilterBar`、`InsightTag`、`ChartCard`。
- Insight 风格 token、业务语义色和图表规范分别维护在 `theme/tokens.css`、`theme/semantic-colors.ts`、`theme/chart-theme.ts`，不得通过修改 `:root` 或旧系统全局样式实现换肤。
- Insight 可复用 shadcn/ui 基础组件，但对外视觉必须由 insight 局部 token 和封装组件控制，避免旧系统紫蓝玻璃风格污染新业务域。
- Insight 登录后业务页不使用常驻顶层 Header，用户信息与退出入口放到侧边栏底部；主内容区从业务内容开始，避免顶部壳层占用可视高度。
- Insight 页面默认不展示占位型大标题和解释型小标题；如需页面级操作，保留紧凑操作区即可，页面语义通过侧栏选中态、Tab、筛选栏和内容本身表达。
- Insight 页面默认采用固定工作台结构：页面根容器不进行纵向整页滚动，顶部工具条、Tab、筛选和分页等控制区保持稳定，滚动只出现在列表、表格、详情、预览、日志和可展开内容等组件内部。
- Insight 响应式断点要按真实办公设备设计：1024px 及以上保持桌面侧栏和主内容双栏，不得把常见笔记本宽度误切成移动单列；1023px 及以下再使用底部移动导航。
- Insight 配置类和列表类页面必须坚持“主信息优先”：默认展示筛选、列表、关键状态和主要操作；新增、编辑、详情、说明、调试信息等次要内容优先放入弹窗、抽屉、折叠区或独立详情页，不要把大表单常驻在列表上方挤压数据区。
- Insight 页面应控制卡片层级、margin 和 padding，避免标题卡片、Tab 卡片、内容卡片多层嵌套导致小屏幕可视区域被容器占满；Tab 应优先采用紧凑工具条形态，长说明只在需要时展示。
- Insight 系统设置只承载渠道库、执行源等管理员基础配置；监测配置放在普通菜单 `/insight/monitoring`，分类及标签维护放在普通菜单 `/insight/tags`，业务用户可维护 AI 评审可选的受控分类和标签。配置列表必须分页展示，新增和编辑使用弹窗，列表区域内部滚动，旧 `/insight/data-sources` 仅作为兼容跳转。
 
## 泛微流程AI助手补充

- 泛微嵌入页入口为 `/weaver/assistant/embed`，源码位于 `frontend/src/features/weaver-ai-assistant/`。
- 泛微流程规则配置嵌入页入口为 `/weaver/assistant/workflow-config`，同样位于 `frontend/src/features/weaver-ai-assistant/`，用于在泛微流程路径设置页维护当前流程的特殊填报要求、提示词和工具/技能说明。
- 泛微流程 AI 智审嵌入页入口为 `/weaver/assistant/review`，规则配置入口为 `/weaver/assistant/review-config`，用于在审批页展示 AI 预审建议、在流程设置页维护节点/审批人智审口径。
- 该页面用于 iframe 嵌入泛微流程页，不经过 `ProtectedRoute`，通过 URL 中的 `ai_sign` 调用后端外部接口。
- 页面与 ecode 父页面通过 `postMessage` 通讯：接收 `WEAVER_AI_CONTEXT`，发送 `WEAVER_AI_APPLY_ACTIONS` 和 `WEAVER_AI_CLOSE`。
- 发送聊天前应通过 `WEAVER_AI_REQUEST_CONTEXT` 请求 ecode 回传最新表单状态；聊天回答使用 `/api/v1/weaver/ai-assistant/chat/stream` SSE 流式展示，动作到达后才启用“写入表单”确认。
- 悬浮图标资源优先使用 `frontend/public/ai_logo.svg`，正式环境通过平台前端域名访问 `/ai_logo.svg`。
- 智审页面只展示风险、建议和检查项，不提供直接审批、退回、提交按钮；如后续做 AI 替审，也必须通过后端审计和泛微 Action 白名单能力实现。
