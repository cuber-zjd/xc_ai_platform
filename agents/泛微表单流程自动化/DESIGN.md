# 泛微协同办公（E-Weaver/E-Cology）超级智能体 Agent

## 1. 概述

### 1.1 项目目标

构建一个“对话驱动的任务引擎 (Chat-First Task Engine)”，通过 AI Agent 全面提升泛微 OA 系统的运维与实施效率。智能体不仅能通过自动化消除繁琐的表单和流程配置工作，还能提供故障诊断、自动修复以及智能化问答服务。

### 1.2 核心理念：随用随取 (Just-in-time UI)

采用**“聊天触发，流程落地”**的融合交互模式：
- **聊天窗 (Sidebar)** 作为统一的用户入口交互终端，接收指令和自然语言提问。
- **动态工作区 (Main Container)** 根据不同意图展示不同形态的“专业面板”（如表单创建的结构化 5 步向导表格、诊断报告卡片等）。

---

## 2. 系统架构: 多智能体协作模式 (Multi-Agent System)

系统采用“**总控 (Orchestrator) + 多个专业子智能体 (Specialists)**”的架构模型：

```mermaid
graph TD
    User((用户)) -->|自然语言指令| Orchestrator[Agent Orchestrator (总控路由)]
    Orchestrator -->|意图分析: 表单创建| Constructor[建设者 Agent<br>(Constructor)]
    Orchestrator -->|意图分析: 问题排查| Diagnostic[诊断医 Agent<br>(Diagnostic)]
    Orchestrator -->|分发: 执行修复| Repairer[修复员 Agent<br>(Repairer)]
    Orchestrator -->|意图分析: 咨询问答| Knowledge[高级客服 Agent<br>(Knowledge - RAG)]

    Constructor -->|生成解析/执行操作| Weaver[泛微系统<br>(API + Playwright)]
    Diagnostic -->|SQL查询/视图分析| WeaverDB[(泛微数据库)]
    Diagnostic -->|DOM元素分析| Weaver
    Repairer -->|执行原子化修复| Weaver
    Knowledge -->|检索| Milvus[(Milvus 向量库)]
```

### 2.1 子智能体职责与工具 (Tools) 映射

| 子智能体 (Sub-Agent) | 核心职责 | 依赖工具 (Tools) | 输出形态 (前端展示) |
| :--- | :--- | :--- | :--- |
| **建设者 (Constructor)** | 解析文件，自动化创建表单和流转节点 | 文档解析(OCR/PDF/Excel), 结构化LLM, API Client, Playwright | **结构化 5 步向导向导 UI** |
| **诊断医 (Diagnostic)** | 联合数据库和前端页面定位流程配置及异常卡点 | SQL Executor, Admin Web Browser (Inspect) | **诊断报告卡片 (Card)** |
| **修复员 (Repairer)** | 基于诊断医的建议，执行 RPA 级别的快速修复 | Playwright (Action Layer) | **动作确认清单 (打断确认)** |
| **高级客服 (Knowledge)**| 针对二次开发、实施手册的纯知识型专业问答 | Vector Database Retriever | **打字机对话气泡 (Chat)** |

---

## 3. 功能详细设计

### 3.1 建设者 (Constructor)：表单与流程自动化规划 (5步流程)

建设者功能作为结构化的向导形态展示给用户。在 LangGraph 中采用 State 中断机制（`interrupt`），等待用户前端确认。

#### Step 1: 表单字段自动化
1. **输入与解析**: 支持上传 Excel/Word/PDF/图片。
2. **LLM 结构化输出**: 自动识别字段（如: 单行文本、金额控件、人员多选浏览框），并生成标准化 JSON。
3. **前端呈现**: 工作区渲染可编辑的数据表格，用户可手动增删改字段类型。
4. **底层生成**: 用户确认后，调度对应的泛微生成接口或触发 Playwright RPA 执行新建动作。

#### Step 2: 流程创建
1. 提取基础配置: `workflowName` (如“费用报销流程”), 关联 `formId`, 类型分类等。

#### Step 3: 流转设置 (复杂路由)
1. **输入**: 自然语言提取规则，如 "金额>1000且申请人为部门副总，流转到总经理"。
2. **结构化提取**: 解析字段 (`conditionField`), 操作符 (`conditionOperator`), 阈值 (`conditionValue`)。
3. **前端呈现**: 面向用户的树状或条带式条件编辑器，供用户核对。

#### Step 4: 节点操作者设置
1. 分析节点流转人员配置，将处理人员归类为：`assignee` (指定人员), `role` (角色岗位), `dept` (部门), `matrix` (组织矩阵), `dynamic` (基于表单动态查找)。

#### Step 5: 流程图配置
综合 Step 2-4，自动化连线并定义图形节点与出口。用户在可视化画布中进行最后的人工干预调整。

### 3.2 诊断医 (Diagnostic)：虚实结合的异常排查

当用户提问：“为什么报销单号 RM-202305 的金额大于 2000，但没流转给财务总监审？” 时触发。

1. **虚拟层 (数据库诊断)**: 智能使用 `SQL_Executor` Tool
   - 寻找历史流转表与配置表 (`workflow_nodebase`, `workflow_billfield`, 业务视图)。
   - 对比数据库记录中该记录的金额值与规则阈值是否匹配。
2. **实体层 (页面诊断)**: 智能使用 `Browser_Inspector` Tool
   - 如果数据库判断无误，启动隐式 Playwright 进入泛微后台，验证特定组件的显示规则（是否因自定义 JS, 或者前端 UI 隐藏条件导致退回操作）。
3. **输出闭环**: 将根因分析整理输出，并将修复建议交由 **Repairer**。

### 3.3 修复员 (Repairer)：极简原子修复

设计特定的不可拆解的原子方法 (Atomic Actions)，确保安全性：
- `update_node_assignee(node_id, new_role_id)`
- `fix_transition_condition(transition_id, correct_operator)`
- **核心逻辑**：Repairer 不会自动偷偷执行，它会在前端面板展现一个类似 Git 的 "Diff 计划列表"，必须经过用户的 Human-in-the-loop 点击「确认修复」后，方可运行 Playwright 修改线上环境。

### 3.4 高级客服 (Knowledge)：智能 RAG 与知识内化

1. 构建专属于泛微平台的语料库并存入 Milvus。
2. 爬取并切片《E-Weaver E-Cology 开发与实施手册》。
3. 为泛微生态提供纯粹的快速问答。如果在解答过程中发现该问题可通过 Agent 直接解决，可以在气泡中嵌入功能直达卡片。

---

## 4. 前端融合交互设计 (React 19 + Shadcn)

整体页面结构是一套精美的“App-in-App”格局：

```
┌────────────────────────────────────────────────────────┐
│  NavBar (当前选中: 泛微超级智能体)                       │
├────────────────────┬───────────────────────────────────┤
│ ▼ Sidebar          │ ▼ Main Workspace                  │
│ [Agent 聊天流]     │ (玻璃拟态的 App-in-App 容器)      │
│                    │                                   │
│ 用户: 帮我新建一个 │ ┌─────────────────────────────────┐ │
│ 请假流程。         │ │                                 │ │
│                    │ │    [ 此区域用于渲染对应的应用 ] │ │
│ Agent: 好的，请在  │ │ 1. 结构化任务: 5 步向导配置页   │ │
│ 右侧上传需求文件。 │ │ 2. 诊断任务:   诊断明细报告视图 │ │
│                    │ │ 3. 空闲/答疑:  数据大盘或说明   │ │
│ [ 附件上传区 ]   ->│ │                                 │ │
│                    │ └─────────────────────────────────┘ │
└────────────────────┴───────────────────────────────────┘
```

- **状态同步**: 左侧对话与右侧应用状态使用 Zustand `useAgentStore` 同步。
- **对话框增强**: AI 除了能回复 Markdown 文本外，还可以下发 `ActionCard` (如：执行修复确认框、步骤导航器)。

---

## 5. LangGraph 工作流详细编排

```python
# 核心节点的伪代码架构演示
workflow = StateGraph(AgentState)

workflow.add_node("intent_classifier", classify_intent)

workflow.add_node("builder_step1", process_form_step1)
workflow.add_node("builder_step2", process_flow_step2)
# ...
workflow.add_node("diagnostic", diagnose_issue)
workflow.add_node("repair", execute_repair)
workflow.add_node("rag_chat", general_qa)

# 根据第一步意图进行分发
workflow.add_conditional_edges(
    "intent_classifier",
    route_to_specialist, # 返回 "builder_step1" / "diagnostic" / "rag_chat"
)

# 建设者的关键: interrupt
workflow.add_edge("builder_step1", "builder_step2")
# LangGraph 中的 Human-in-the-loop 机制
# 编译时添加 checkpointer，使其在到达需要人类确认的节点前暂停
app = workflow.compile(
    checkpointer=memory,
    interrupt_before=["builder_step2", "builder_step3", "builder_step4", "builder_step5", "repair"]
)
```

---

## 6. 数据模型 (扩展)

```sql
-- 原建设配置表
CREATE TABLE sys_weaver_workflow_config (
    id VARCHAR(36) PRIMARY KEY,
    config_name VARCHAR(200),
    form_config JSONB,
    workflow_config JSONB,
    status VARCHAR(20) DEFAULT 'draft',
    -- ...
);

-- 新增：运维交互审计日志
CREATE TABLE sys_weaver_agent_audit (
    id VARCHAR(36) PRIMARY KEY,
    agent_type VARCHAR(20) COMMENT 'Constructor/Diagnostic/Repairer',
    intent_desc TEXT COMMENT '用户原始意图',
    execution_result JSONB COMMENT '智能体执行内容与报告结果',
    has_human_approved BOOLEAN DEFAULT FALSE COMMENT '用户是否确认过修复',
    create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## 7. 开发路线图 (Roadmap)

| Phase | 组件/模块 | 内容 & 里程碑 | 优先级 |
|-------|-----------|--------------|--------|
| Phase 1 | **架构与大脑** | 搭建前后台 Agent Chat 架构；完成 `Intent Classifier` 的总控路由编排。 | P0 |
| Phase 2 | **建设者(Constructor)** | 开发前端向导容器；集成 OCR/PDF 解析；打通第一个表单配置项生成的 LangGraph 交互。 | P0 |
| Phase 3 | **诊断医(Diagnostic)** | 实现 `SQL_Executor_Tool` 和泛微表结构常识 Prompt，完成纯后端的异常定位闭环验证。 | P1 |
| Phase 4 | **高级客服(RAG)** | 数据整理与清洗入库；对接 Milvus 完成检索增强对话。 | P1 |
| Phase 5 | **修复员(Repairer)** | 对接 Playwright Tool；打通诊断向修复分发的确认流程 (Human-in-the-loop)。 | P2 |
| Phase 6 | **端到端调优** | 多场景混合对话的稳定性测试，确保各分支流畅运转。 | P2 |

---

## 8. 待确认与待准备事项

1. **环境权限**: 需要获取泛微管理员账户（API 和 UI 登录）以及数据库直连只读/读写账号用于 Agent Tool 封装。
2. **字典梳理**: 需要预先准备一份泛微底表映射的核心常用词典（例如 `workflow_base` 等表与字段的作用定义）给大模型。
3. **Playwright 适配**: 泛微不同版本的 DOM 结构可能有异，需确认目标站点的版本，在 Repairer 动作开发时需要增加元素可用性校验机制。
