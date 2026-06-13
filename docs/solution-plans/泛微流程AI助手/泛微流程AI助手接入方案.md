# 泛微流程 AI 助手接入方案

## 目标

将泛微 ecode 中的代码压缩到最小：只负责显示悬浮图标、打开平台 iframe、把当前流程上下文转发给平台、接收平台返回的写入动作并调用 `WfForm` 执行。AI 助手页面、样式、聊天交互和后端 Agent 均由当前 AI 平台承载。

## 平台侧入口

- 前端嵌入页：`/weaver/assistant/embed?ai_sign=<外部签名>`
- 后端字段配置：`GET /api/v1/weaver/ai-assistant/field-config?workflow_id=<流程ID>`
- 后端聊天接口：`POST /api/v1/weaver/ai-assistant/chat`
- 鉴权方式：请求头 `ai-sign`，值来自后端 `EXTERNAL_API_KEYS` 配置。

## ecode 极简脚本

以下代码放在 ecode 前置加载 `register.js` 中。现场需要替换 `AI_PLATFORM_BASE_URL` 和 `AI_SIGN`。

```javascript
let enableAiFlowAssistant = true;
let aiFlowAssistantMounted = false;

const AI_PLATFORM_BASE_URL = "http://192.168.14.167:5173";
const AI_SIGN = "替换为EXTERNAL_API_KEYS中的一个值";
const AI_ICON_URL = AI_PLATFORM_BASE_URL + "/ai_logo.svg";

const aiLog = function () {
  if (!window.console || !console.log) return;
  const args = Array.prototype.slice.call(arguments);
  args.unshift("[AI流程助手]");
  console.log.apply(console, args);
};

const isWorkflowReqPage = function () {
  const hash = window.location.hash || "";
  return hash.indexOf("#/main/workflow/req") === 0;
};

const collectFormContext = function () {
  const baseInfo = WfForm.getBaseInfo ? WfForm.getBaseInfo() : {};
  const fieldMap = window.WEAVER_AI_FIELD_MAP || {};
  const fields = {};

  Object.keys(fieldMap).forEach(function (bizKey) {
    const item = fieldMap[bizKey];
    const fieldId = typeof item === "string" ? item : item.fieldId;
    if (!fieldId) return;
    fields[bizKey] = {
      label: item.label || bizKey,
      fieldId: fieldId,
      type: item.type || "text",
      writable: item.writable !== false,
      value: WfForm.getFieldValue(fieldId)
    };
  });

  return {
    baseInfo: baseInfo,
    url: window.location.href,
    fields: fields
  };
};

const applyAiActions = function (actions) {
  if (!actions || !actions.length) return;
  actions.forEach(function (action) {
    if (action.type === "set_field" && action.field) {
      WfForm.changeFieldValue(action.field, {
        value: action.value == null ? "" : String(action.value)
      });
    }
    if (action.type === "add_detail_row" && action.detail) {
      WfForm.addDetailRow(action.detail, action.values || {});
    }
  });
};

const openAiAssistant = function () {
  let panel = document.getElementById("ai-flow-iframe-panel");
  if (!panel) {
    panel = document.createElement("div");
    panel.id = "ai-flow-iframe-panel";
    panel.style.position = "fixed";
    panel.style.right = "28px";
    panel.style.bottom = "152px";
    panel.style.zIndex = "2147483647";
    panel.style.width = "420px";
    panel.style.height = "620px";
    panel.style.border = "1px solid #e5e7eb";
    panel.style.borderRadius = "12px";
    panel.style.overflow = "hidden";
    panel.style.boxShadow = "0 18px 48px rgba(15,23,42,.2)";
    panel.style.background = "#fff";

    const iframe = document.createElement("iframe");
    iframe.id = "ai-flow-iframe";
    iframe.src = AI_PLATFORM_BASE_URL + "/weaver/assistant/embed?ai_sign=" + encodeURIComponent(AI_SIGN);
    iframe.style.width = "100%";
    iframe.style.height = "100%";
    iframe.style.border = "0";
    panel.appendChild(iframe);
    document.body.appendChild(panel);
  }

  panel.style.display = panel.style.display === "none" ? "block" : "none";

  const iframeWindow = document.getElementById("ai-flow-iframe").contentWindow;
  if (iframeWindow) {
    iframeWindow.postMessage({
      type: "WEAVER_AI_CONTEXT",
      context: collectFormContext()
    }, AI_PLATFORM_BASE_URL);
  }
};

const mountAiButton = function () {
  if (aiFlowAssistantMounted) return;
  if (!enableAiFlowAssistant || !isWorkflowReqPage() || !window.WfForm) return;

  aiFlowAssistantMounted = true;

  const btn = document.createElement("button");
  btn.id = "ai-flow-float-button";
  btn.type = "button";
  btn.title = "AI填单助手";
  btn.style.position = "fixed";
  btn.style.right = "28px";
  btn.style.bottom = "88px";
  btn.style.zIndex = "2147483647";
  btn.style.width = "64px";
  btn.style.height = "64px";
  btn.style.border = "0";
  btn.style.background = "transparent";
  btn.style.padding = "0";
  btn.style.cursor = "pointer";

  const icon = document.createElement("img");
  icon.src = AI_ICON_URL;
  icon.alt = "AI填单助手";
  icon.style.width = "64px";
  icon.style.height = "64px";
  icon.style.objectFit = "contain";
  icon.style.pointerEvents = "none";
  btn.appendChild(icon);

  btn.onclick = openAiAssistant;
  document.body.appendChild(btn);
  aiLog("AI悬浮入口已挂载");
};

window.addEventListener("message", function (event) {
  if (event.origin !== AI_PLATFORM_BASE_URL) return;
  const data = event.data || {};
  if (data.type === "WEAVER_AI_READY") {
    const iframe = document.getElementById("ai-flow-iframe");
    if (iframe && iframe.contentWindow) {
      iframe.contentWindow.postMessage({
        type: "WEAVER_AI_CONTEXT",
        context: collectFormContext()
      }, AI_PLATFORM_BASE_URL);
    }
  }
  if (data.type === "WEAVER_AI_APPLY_ACTIONS") {
    applyAiActions(data.actions || []);
  }
  if (data.type === "WEAVER_AI_CLOSE") {
    const panel = document.getElementById("ai-flow-iframe-panel");
    if (panel) panel.style.display = "none";
  }
});

ecodeSDK.overwritePropsFnQueueMapSet("WeaReqTop", {
  fn: function () {
    if (!isWorkflowReqPage() || !window.WfForm) return;
    mountAiButton();
  },
  order: 1,
  desc: "流程页面挂载AI填单助手"
});

let aiCheckCount = 0;
const aiTimer = window.setInterval(function () {
  aiCheckCount += 1;
  mountAiButton();
  if (aiFlowAssistantMounted || aiCheckCount > 60) {
    window.clearInterval(aiTimer);
  }
}, 500);
```

## 字段映射示例

第一版建议仍由 ecode 根据流程维护字段白名单，避免把整张表单全部传给 AI。

```javascript
window.WEAVER_AI_FIELD_MAP = {
  title: { label: "标题", fieldId: "field1234", type: "text" },
  reason: { label: "请假原因", fieldId: "field1237", type: "textarea" },
  days: { label: "请假天数", fieldId: "field1238", type: "number" }
};
```

## 安全边界

- ecode 不保存模型 Key，只保存外部接口签名 `ai-sign`。
- AI 后端只返回 `set_field`、`add_detail_row`、`show_message` 等结构化动作。
- ecode 只按白名单动作调用 `WfForm`，不执行 AI 生成的任意 JavaScript。
- 第一版不自动保存、不自动提交、不自动审批。
