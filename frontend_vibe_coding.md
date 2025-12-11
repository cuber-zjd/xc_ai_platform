# Frontend "Vibe Coding" Guide ✨

> **核心哲学 (Core Philosophy)**:  
> **Premium Minimalist**. 代码要简洁，界面要高级。我们要的不仅仅是功能可用，而是用户在使用时的愉悦感 (Delight)。
> **包管理**: **一定要使用pnpm**

---

## 1. 视觉美学标准 (Aesthetic Standards)

### 🎨 色彩与风格 (Palette & Style)
*   **Monochrome Supreme**: 主色调使用 `Zinc` (50-950)。避免使用高饱和度的纯色（红/蓝/绿），除非用于状态指示。
*   **Dark Mode First**: 所有组件必须完美适配暗黑模式。使用 `bg-background` 和 `text-foreground` 等语义化 Token，而不是硬编码颜色。
*   **Glassmorphism**: 在侧边栏、Header、Modal 遮罩使用 `backdrop-blur`，营造通透的高级感。
    *   Example: `bg-background/80 backdrop-blur-md border-b`

### 🌫️ 动效与交互 (Motion & Interaction)
*   **Micro-Interactions**: 按钮、卡片、列表项在 Hover 时必须有反馈。
    *   *推荐*: `hover:bg-accent hover:text-accent-foreground transition-colors duration-200`
*   **Smooth Transitions**: 路由切换、Dialog 弹出、折叠面板必须有过渡动画。
    *   *严禁*: 瞬间生硬的闪现。

---

## 2. 技术栈与工具链 (Tech Stack & Tooling)

### 🧩 UI 组件 (Shadcn/ui)
我们不重复造轮子。所有基础组件 **必须** 优先使用 Shadcn/ui。
*   **Add Component**: 
    ```bash
    pnpm dlx shadcn@latest add avatar
    ```
*   **Customization**: 在 `components/ui` 目录下修改源码，而不是覆盖样式。

### 🛠️ 核心库 (Core Libraries)
*   **Styling**: `Tailwind CSS v4`. 禁止写 `.css` 文件（除非是全局动画 Keyframes）。
*   **Icons**: `lucide-react`. 统一风格，禁止混用 material icons 或 font awesome。
*   **State**: 
    *   全局状态 (User/Threme): `Zustand`
    *   服务端状态 (API Data): `TanStack Query`
*   **API**: `src/api/client.ts` (基于 Axios 封装)。

---

## 3. 编码规范 (Coding Etiquette)

### 📁 目录结构 (Directory Structure)
遵循 **Feature-based** 结构。同一个功能的组件、Hooks、Utils 尽量靠近。
```plaintext
src/
├── features/chat/          # [推荐] 复杂业务模块聚合
│   ├── components/
│   ├── hooks/
│   └── types.ts
├── components/ui/          # 纯 UI 组件 (Shadcn)
├── components/common/      # 全局业务组件 (UserAvatar, Logo)
└── pages/                  # 路由页面入口
```

### 📝 命名与写法 (Naming & Syntax)
*   **Components**: PascalCase (`UserProfile.tsx`).
*   **Hooks**: camelCase (`useAuth.ts`).
*   **Import Order**:
    1.  React / Standard Libs
    2.  Third-party (Zustand, Lucide, Axios)
    3.  Components (`@/components/...`)
    4.  Utils / Types / Local
*   **Component Structure**:
    ```tsx
    // 1. Imports
    import { useState } from "react";
    import { cn } from "@/lib/utils";
    
    // 2. Types
    interface Props { ... }
    
    // 3. Component
    export function MyComponent({ className }: Props) {
        // 4. Hooks
        // 5. Derived State
        // 6. Effects
        // 7. Render
        return <div className={cn("base-style", className)}>...</div>;
    }
    ```

---

## 4. "Vibe" 检查清单 (Self-Check)

提交代码前，请灵魂拷问自己：
- [ ] **Is it Responsive?** 在移动端 (Drawer) 和桌面端 (Sidebar) 都能完美展示吗？
- [ ] **Is it Dark Mode Ready?** 切换到深色模式，有没有刺眼的白色块或看不清的字？
- [ ] **Is it Alive?** 点击按钮有没有反馈？加载数据有没有 Skeleton？
- [ ] **Is it Clean?** 代码里有没有残留的 `console.log` 或硬编码的 `hex` 颜色？

---

> **记住**: 我们在构建的是 **AI Platform**，它本身就代表着未来。代码和界面必须体现出这种**未来感 (Futuristic)**。
