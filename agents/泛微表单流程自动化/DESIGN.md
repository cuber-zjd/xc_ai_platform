# 泛微表单流程自动化 Agent

## 1. 概述

### 1.1 项目目标

通过 AI Agent 实现泛微 OA 系统的表单和流程自动化配置，减少人工操作，提高效率。

### 1.2 技术架构

```
┌─────────────────────────────────────────────────────────────┐
│                      前端 (React 19)                         │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐
│  │Step1表单│ │Step2流程│ │Step3流转│ │Step4人员│ │Step5流程图│
│  │字段配置 │ │  创建   │ │  设置   │ │  设置   │ │  配置    │
│  └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘
└───────┼──────────┼──────────┼──────────┼──────────┼────────┘
        │          │          │          │          │
        ▼          ▼          ▼          ▼          ▼
┌─────────────────────────────────────────────────────────────┐
│                   Backend (FastAPI + LangGraph)              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              Agent Orchestrator (总控)               │   │
│  └──────────────────────────────────────────────────────┘   │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐           │
│  │文件解析 │ │结构化   │ │泛微API  │ │Playwright│           │
│  │Service  │ │LLM节点  │ │Client   │ │自动化   │           │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘           │
└─────────────────────────────────────────────────────────────┘
        │                                    │
        ▼                                    ▼
┌───────────────┐                  ┌─────────────────┐
│ MinIO (文件)   │                  │  泛微系统        │
│ PDF/Word/Excel│                  │  API + 页面     │
│ Img (OCR)     │                  │                  │
└───────────────┘                  └─────────────────┘
```

---

## 2. 五步流程详细设计

### Step 1: 表单字段自动化

#### 2.1.1 文件解析方案

| 文件类型 | 解析方案 | 库 |
|---------|---------|-----|
| Excel (.xlsx/.xls) | openpyxl | 表格结构 + 数据 |
| Word (.docx/.doc) | python-docx + mammoth | 文本提取 |
| PDF | pypdf | 文本提取 |
| 图片 | GPT-4V + OCR | 视觉理解 |

#### 2.1.2 字段类型定义

| 类型 | 说明 | 对应泛微控件 |
|------|------|-------------|
| 文本 | 单行文本 | 单行文本框 |
| 富文本 | 多行/格式 | 多行文本框 |
| 数字 | 整数/小数 | 数字控件 |
| 金额 | 货币格式 | 金额控件 |
| 日期 | 年月日 | 日期控件 |
| 时间 | 时分秒 | 时间控件 |
| 下拉单选 | 单选 | 下拉框 |
| 多选 | 多选 | 复选框 |
| 附件 | 文件上传 | 附件控件 |
| 人员 | 人员浏览框 | 人员控件 |
| 人员(多选) | 多人员 | 人员控件(多选) |
| 部门 | 部门浏览框 | 部门控件 |
| 部门(多选) | 多部门 | 部门控件(多选) |
| 开关 | 是/否 | 是/否控件 |
| 评分 | 1-5星 | 评分控件 |

#### 2.1.3 LLM 结构化输出

```json
{
  "formName": "费用报销单",
  "formNameEn": "expense_reimburse",
  "tableName": "uf_expense_reimburse",
  "fields": [
    {
      "dbName": "apply_user",
      "label": "申请人",
      "type": "人员",
      "length": null,
      "required": true,
      "defaultValue": null,
      "options": null,
      "weaverControl": "人力资源-单选"
    },
    {
      "dbName": "amount",
      "label": "报销金额",
      "type": "金额",
      "length": 12,
      "required": true,
      "defaultValue": null,
      "options": null,
      "weaverControl": "金额控件"
    }
  ]
}
```

#### 2.1.4 前端交互

- 文件上传区（支持拖拽）
- 解析结果展示（可编辑表格）
- 字段增删改功能
- 用户确认后触发 Playwright 自动化

---

### Step 2: 流程创建

#### 2.2.1 配置项

```json
{
  "workflowName": "费用报销流程",
  "workflowCode": "wf_expense",
  "formId": "关联表单ID",
  "category": "财务类",
  "nodeCount": 4,
  "isQuickFlow": false
}
```

#### 2.2.2 泛微 API 示例

```python
# 创建流程
POST /api/workflow/
{
  "workflowName": "费用报销流程",
  "workflowCode": "wf_expense",
  "formId": 123
}
```

---

### Step 3: 流转设置

#### 2.3.1 LLM 结构化输出

```json
{
  "transitions": [
    {
      "id": "uuid-1",
      "fromNode": "开始",
      "toNode": "部门主管审批",
      "condition": "金额 > 1000",
      "conditionField": "amount",
      "conditionOperator": ">",
      "conditionValue": "1000",
      "transitionName": "大于1000元"
    },
    {
      "id": "uuid-2",
      "fromNode": "开始",
      "toNode": "财务审批",
      "condition": "金额 <= 1000",
      "conditionField": "amount",
      "conditionOperator": "<=",
      "conditionValue": "1000",
      "transitionName": "小于等于1000元"
    }
  ]
}
```

#### 2.3.2 前端交互

- 条件编辑器（字段 + 操作符 + 值）
- 支持 AND/OR 组合条件
- 图形化流转预览

---

### Step 4: 节点操作者设置

#### 2.4.1 规则类型

| 类型 | 说明 | 示例 |
|------|------|------|
| `assignee` | 指定人 | 工号、姓名 |
| `role` | 岗位 | 财务经理 |
| `dept` | 部门 | 销售部 |
| `matrix` | 矩阵 | 部门+岗位 |
| `field` | 表单字段 | 申请人字段 |
| `dynamic` | 动态 | 上一节点审批人 |

#### 2.4.2 LLM 结构化输出

```json
{
  "nodes": [
    {
      "nodeId": "node-1",
      "nodeName": "部门主管审批",
      "assigneeType": "dept",
      "assigneeValue": "当前用户部门",
      "assigneeConfig": {
        "multi": false,
        "sameDept": true,
        "level": 1
      }
    },
    {
      "nodeId": "node-2",
      "nodeName": "财务审批",
      "assigneeType": "role",
      "assigneeValue": "财务经理",
      "assigneeConfig": {
        "multi": false
      }
    }
  ]
}
```

#### 2.4.3 前端交互

- 表格展示各节点配置
- 下拉选择操作者类型
- 批量编辑支持
- 不确定的字段留空，用户手动选择

---

### Step 5: 流程图配置

#### 2.5.1 配置式生成

基于 Step 2-4 的配置自动生成流程图：
- 节点定义
- 出口设置（流转条件）
- 自动串联

#### 2.5.2 人工干预

- 流程图预览
- 节点/连线调整
- 异常路径处理

---

## 3. 数据模型

### 3.1 泛微表单流程配置表

```sql
CREATE TABLE e泛微_form_workflow_config (
    id SERIAL PRIMARY KEY,
    config_name VARCHAR(200) NOT NULL COMMENT '配置名称',
    form_config JSONB COMMENT 'Step1 表单字段配置',
    workflow_config JSONB COMMENT 'Step2 流程创建配置',
    transition_config JSONB COMMENT 'Step3 流转设置',
    node_assignee_config JSONB COMMENT 'Step4 节点操作者配置',
    status VARCHAR(20) DEFAULT 'draft' COMMENT '状态: draft/published',
    create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    create_by VARCHAR(50),
    update_by VARCHAR(50)
);
```

### 3.2 各步骤配置 JSON 结构

#### form_config (Step1)

```json
{
  "formName": "费用报销单",
  "formNameEn": "expense_reimburse",
  "tableName": "uf_expense_reimburse",
  "fields": [...]
}
```

#### workflow_config (Step2)

```json
{
  "workflowName": "费用报销流程",
  "workflowCode": "wf_expense",
  "formId": 123,
  "category": "财务类",
  "nodeCount": 4
}
```

#### transition_config (Step3)

```json
{
  "transitions": [...]
}
```

#### node_assignee_config (Step4)

```json
{
  "nodes": [...]
}
```

---

## 4. 技术实现要点

### 4.1 文件解析

| 文件类型 | 库 | 说明 |
|---------|-----|-----|
| Excel | openpyxl | 读取表格结构、表头、数据 |
| Word | python-docx | 读取段落、表格 |
| PDF | pypdf | 文本提取 |
| 图片 | GPT-4V | 视觉理解 + OCR |

### 4.2 LLM 结构化输出

使用 LangChain 的 `with_structured_output` 或 Pydantic JSON Mode 确保输出格式稳定。

### 4.3 泛微集成

- **API 方式**：调用泛微 REST API 创建表单、流程
- **Playwright**：页面元素定位，自动化操作

### 4.4 LangGraph 工作流

```
                                ┌─────────────┐
                                │   Start     │
                                └──────┬──────┘
                                       │
                    ┌──────────────────┼──────────────────┐
                    │                  │                  │
                    ▼                  ▼                  ▼
             ┌───────────┐      ┌───────────┐      ┌───────────┐
             │ Step1     │      │ Step2     │      │ Step3     │
             │ 文件解析   │ ───► │ 流程创建   │ ───► │ 流转设置   │
             └───────────┘      └───────────┘      └─────┬─────┘
                                                          │
                                                    ┌─────┴─────┐
                                                    │           │
                                                    ▼           ▼
                                             ┌───────────┐ ┌───────────┐
                                             │ Step4     │ │ Step5     │
                                             │ 节点设置   │ │ 流程图配置 │
                                             └─────┬─────┘ └─────┬─────┘
                                                   │             │
                                                   └──────┬──────┘
                                                          │
                                                          ▼
                                                    ┌───────────┐
                                                    │   End     │
                                                    └───────────┘
```

---

## 5. 开发计划

| Phase | 内容 | 优先级 |
|-------|------|--------|
| Phase 1 | 文件解析 + LLM 结构化输出 | P0 |
| Phase 2 | 前端表单字段配置界面 | P0 |
| Phase 3 | 泛微 API Client + Playwright | P1 |
| Phase 4 | 后续步骤配置界面 | P1 |
| Phase 5 | 端到端联调 | P1 |

---

## 6. 待确认事项

1. 泛微系统具体版本和 API 文档
2. 泛微表单字段创建的具体方式（API/页面）
3. 流程节点操作者设置的详细规则
4. 是否需要支持流程撤回、退回等高级功能
