/*
 * 泛微流程 AI 智审 - 审批页 ecode 脚本
 *
 * 使用方式：
 * 1. 复制本文件整段到流程审批/处理页面可加载的 ecode 脚本中。
 * 2. 修改现场配置区的 AI_PLATFORM_BASE_URL、AI_SIGN、WEAVER_ENV。
 * 3. 脚本会在流程页面右下角添加“AI智审”悬浮入口，打开平台 iframe。
 */
(function () {
  "use strict";

  // ========================
  // 现场配置区
  // ========================
  var ENABLE_WEAVER_AI_REVIEW = true;
  var AI_PLATFORM_BASE_URL = "http://192.168.8.79:5173";
  var AI_SIGN = "xc-fw-1af7cc98-66ed-4d55-a4cc-c6240b1f1c3c";
  var WEAVER_ENV = "test";
  var AI_ICON_URL = AI_PLATFORM_BASE_URL.replace(/\/$/, "") + "/ai/weaver-assistant/mascot-selected.png";

  // ========================
  // 内部状态
  // ========================
  var mounted = false;
  var panelOpen = false;
  var buttonId = "weaver-ai-review-button";
  var panelId = "weaver-ai-review-panel";
  var iframeId = "weaver-ai-review-iframe";

  function aiLog() {
    if (!window.console || !console.log) return;
    var args = Array.prototype.slice.call(arguments);
    args.unshift("[泛微流程AI智审]");
    console.log.apply(console, args);
  }

  function safeGetBaseInfo() {
    try {
      if (window.WfForm && typeof WfForm.getBaseInfo === "function") {
        return WfForm.getBaseInfo() || {};
      }
    } catch (error) {
      aiLog("读取 WfForm baseInfo 失败", error);
    }
    return {};
  }

  function getWorkflowId() {
    var baseInfo = safeGetBaseInfo();
    if (baseInfo.workflowid || baseInfo.workflowId) return String(baseInfo.workflowid || baseInfo.workflowId);
    try {
      var params = new URLSearchParams((window.location.hash.split("?")[1] || window.location.search || ""));
      return params.get("workflowid") || params.get("workflowId") || "";
    } catch (error) {
      return "";
    }
  }

  function getNodeId() {
    var baseInfo = safeGetBaseInfo();
    return String(baseInfo.nodeid || baseInfo.nodeId || "");
  }

  function getWorkflowName() {
    var baseInfo = safeGetBaseInfo();
    return String(
      baseInfo.workflowname ||
        baseInfo.workflowName ||
        baseInfo.workflow_name ||
        getPageParam("workflowname") ||
        getPageParam("workflowName") ||
        ""
    );
  }

  function getNodeName() {
    var baseInfo = safeGetBaseInfo();
    return String(
      baseInfo.nodename ||
        baseInfo.nodeName ||
        baseInfo.node_name ||
        getPageParam("nodename") ||
        getPageParam("nodeName") ||
        ""
    );
  }

  function getRequestId() {
    var baseInfo = safeGetBaseInfo();
    return String(
      baseInfo.requestid ||
        baseInfo.requestId ||
        getPageParam("requestid") ||
        getPageParam("requestId") ||
        getPageParam("resourceid") ||
        getPageParam("resourceId") ||
        ""
    );
  }

  function getPageParam(name) {
    var sources = [window.location.search || ""];
    var hash = window.location.hash || "";
    var queryIndex = hash.indexOf("?");
    if (queryIndex >= 0) sources.push(hash.slice(queryIndex));
    for (var i = 0; i < sources.length; i += 1) {
      try {
        var value = new URLSearchParams(sources[i]).get(name);
        if (value !== null && value !== "") return value;
      } catch (error) {}
    }
    return "";
  }

  function getWorkflowPageMode() {
    var isCreate = String(getPageParam("iscreate") || getPageParam("isCreate") || "").toLowerCase();
    if (isCreate === "1" || isCreate === "true") return "create";
    if (isCreate === "0" || isCreate === "false") return "process";

    var baseInfo = safeGetBaseInfo();
    var baseIsCreate = String(baseInfo.iscreate || baseInfo.isCreate || "").toLowerCase();
    if (baseIsCreate === "1" || baseIsCreate === "true") return "create";
    if (baseIsCreate === "0" || baseIsCreate === "false") return "process";

    var requestId = getRequestId();
    if (requestId && requestId !== "0" && requestId !== "-1") return "process";
    return "unknown";
  }

  function isApprovalPage() {
    var hash = window.location.hash || "";
    var pathname = window.location.pathname || "";
    var isRequestRoute = hash.indexOf("#/main/workflow/req") === 0 || pathname.indexOf("/workflow/") >= 0;
    return isRequestRoute && getWorkflowPageMode() === "process";
  }

  function getCurrentUser() {
    try {
      var baseInfo = safeGetBaseInfo();
      return {
        userId: String(baseInfo.f_weaver_belongto_userid || baseInfo.userid || baseInfo.userId || ""),
        userName: String(baseInfo.username || baseInfo.userName || ""),
      };
    } catch (error) {
      return {};
    }
  }

  function readFieldValue(fieldId, element) {
    try {
      if (window.WfForm && typeof WfForm.getFieldValue === "function") {
        var value = WfForm.getFieldValue(fieldId);
        if (value !== undefined && value !== null) return value;
      }
    } catch (error) {
      aiLog("读取字段值失败", fieldId, error);
    }
    if (!element) return "";
    return element.value !== undefined ? element.value : element.textContent || "";
  }

  function readFieldLabel(element) {
    try {
      var cell = element.closest("td");
      var mark = cell && cell.querySelector("[data-fieldname]");
      if (mark && mark.getAttribute("data-fieldname")) return mark.getAttribute("data-fieldname");
      var row = element.closest("tr");
      if (row) {
        var cells = Array.prototype.slice.call(row.querySelectorAll("td"));
        var index = cells.indexOf(cell);
        if (index > 0) {
          return (cells[index - 1].innerText || "").replace(/\*/g, "").trim().slice(0, 80);
        }
      }
    } catch (error) {
      return "";
    }
    return "";
  }

  function isElementVisible(element) {
    if (!element) return false;
    var style = window.getComputedStyle(element);
    if (style.display === "none" || style.visibility === "hidden") return false;
    var rect = element.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  }

  function collectFields() {
    var fields = {};
    var elements = Array.prototype.slice.call(
      document.querySelectorAll("input[name^='field'], textarea[name^='field'], select[name^='field']")
    );
    elements.forEach(function (element) {
      var fieldId = element.name || element.id || "";
      if (!/^field\d+/.test(fieldId)) return;
      if (fields[fieldId]) return;
      var visible = isElementVisible(element) || !!document.querySelector("[data-fieldmark='" + fieldId + "']");
      var writable = visible && !element.disabled && !element.readOnly && element.type !== "hidden";
      var value = readFieldValue(fieldId, element);
      fields[fieldId] = {
        label: readFieldLabel(element) || fieldId,
        fieldId: fieldId,
        type: element.tagName === "SELECT" ? "select" : element.tagName === "TEXTAREA" ? "textarea" : "text",
        writable: writable,
        visible: visible,
        value: value,
        displayValue: value,
      };
    });
    return fields;
  }

  function collectContext() {
    var baseInfo = safeGetBaseInfo();
    return {
      env: WEAVER_ENV,
      pageMode: "approval",
      readOnlyReview: true,
      baseInfo: baseInfo,
      url: window.location.href,
      fields: collectFields(),
    };
  }

  function buildIframeUrl() {
    var workflowId = encodeURIComponent(getWorkflowId());
    var workflowName = encodeURIComponent(getWorkflowName());
    var requestId = encodeURIComponent(getRequestId());
    var nodeId = encodeURIComponent(getNodeId());
    var nodeName = encodeURIComponent(getNodeName());
    var targetOrigin = encodeURIComponent(window.location.origin);
    return (
      AI_PLATFORM_BASE_URL.replace(/\/$/, "") +
      "/ai/weaver/assistant/review?ai_sign=" +
      encodeURIComponent(AI_SIGN) +
      "&env=" +
      encodeURIComponent(WEAVER_ENV) +
      "&workflow_id=" +
      workflowId +
      "&workflow_name=" +
      workflowName +
      "&request_id=" +
      requestId +
      "&node_id=" +
      nodeId +
      "&node_name=" +
      nodeName +
      "&target_origin=" +
      targetOrigin
    );
  }

  function postContext(messageType, requestId) {
    var iframe = document.getElementById(iframeId);
    if (!iframe || !iframe.contentWindow) return;
    iframe.contentWindow.postMessage(
      {
        type: messageType || "WEAVER_AI_REVIEW_CONTEXT",
        requestId: requestId,
        context: collectContext(),
      },
      "*"
    );
  }

  function animatePanel(opening) {
    var panel = document.getElementById(panelId);
    var button = document.getElementById(buttonId);
    if (!panel || !button || typeof panel.animate !== "function") {
      if (panel) panel.style.display = opening ? "block" : "none";
      if (button) {
        button.style.opacity = opening ? "0" : "1";
        button.style.pointerEvents = opening ? "none" : "auto";
      }
      return Promise.resolve();
    }
    if (opening) panel.style.display = "block";
    var animation = panel.animate(
      opening
        ? [
            { opacity: 0, transform: "translate(18px, 24px) scale(.14)", borderRadius: "48px", clipPath: "circle(10% at 92% 94%)" },
            { opacity: 1, transform: "translate(0, 0) scale(1)", borderRadius: "16px", clipPath: "circle(150% at 92% 94%)" },
          ]
        : [
            { opacity: 1, transform: "translate(0, 0) scale(1)", borderRadius: "16px", clipPath: "circle(150% at 92% 94%)" },
            { opacity: 0, transform: "translate(18px, 24px) scale(.14)", borderRadius: "48px", clipPath: "circle(10% at 92% 94%)" },
          ],
      { duration: opening ? 560 : 380, easing: opening ? "cubic-bezier(.16,1,.3,1)" : "cubic-bezier(.7,0,.84,0)", fill: "forwards" }
    );
    button.animate(
      opening
        ? [{ opacity: 1, transform: "scale(1) rotate(0deg)" }, { opacity: 0, transform: "scale(.72) rotate(10deg)" }]
        : [{ opacity: 0, transform: "scale(.72) rotate(10deg)" }, { opacity: 1, transform: "scale(1) rotate(0deg)" }],
      { duration: opening ? 260 : 420, easing: "cubic-bezier(.16,1,.3,1)", fill: "forwards" }
    );
    button.style.pointerEvents = opening ? "none" : "auto";
    return animation.finished.catch(function () {}).then(function () {
      if (!opening) panel.style.display = "none";
    });
  }

  function openPanel() {
    panelOpen = true;
    var panel = document.getElementById(panelId);
    var iframe = document.getElementById(iframeId);
    animatePanel(true);
    if (iframe) {
      iframe.src = buildIframeUrl();
      setTimeout(function () {
        postContext("WEAVER_AI_REVIEW_CONTEXT");
      }, 500);
    }
  }

  function closePanel() {
    panelOpen = false;
    animatePanel(false);
  }

  function appendBlinkEyes(container) {
    ["28.5%", "56.3%"].forEach(function (left) {
      var eye = document.createElement("span");
      eye.style.cssText = [
        "position:absolute",
        "left:" + left,
        "top:54.1%",
        "z-index:2",
        "width:15.2%",
        "height:7.4%",
        "border-radius:999px",
        "overflow:hidden",
        "background:#061945",
        "pointer-events:none",
        "transform:scaleY(0)",
        "transform-origin:center",
      ].join(";");

      var closedLine = document.createElement("span");
      closedLine.style.cssText = [
        "position:absolute",
        "left:14%",
        "right:14%",
        "top:50%",
        "height:2px",
        "border-radius:999px",
        "background:#67e8f9",
        "box-shadow:0 0 5px rgba(34,211,238,.95)",
        "transform:translateY(-50%)",
      ].join(";");
      eye.appendChild(closedLine);
      container.appendChild(eye);

      if (eye.animate) {
        eye.animate(
          [
            { transform: "scaleY(0)", offset: 0 },
            { transform: "scaleY(0)", offset: 0.72 },
            { transform: "scaleY(1)", offset: 0.76 },
            { transform: "scaleY(1)", offset: 0.8 },
            { transform: "scaleY(0)", offset: 0.84 },
            { transform: "scaleY(0)", offset: 1 },
          ],
          { duration: 4600, iterations: Infinity, easing: "ease-in-out" }
        );
      }
    });
  }

  function mount() {
    if (!ENABLE_WEAVER_AI_REVIEW || mounted || !isApprovalPage()) return;
    removeElementById("ai-flow-float-button");
    removeElementById("ai-flow-iframe-panel");
    mounted = true;
    aiLog("开始挂载 AI 智审入口", {
      pageMode: getWorkflowPageMode(),
      requestId: getRequestId(),
      baseInfo: safeGetBaseInfo(),
    });

    var button = document.createElement("button");
    button.id = buttonId;
    button.type = "button";
    var visual = document.createElement("span");
    visual.style.cssText = "position:absolute;inset:0;display:block;transform:scale(1.08);transition:transform .22s ease";
    var icon = document.createElement("img");
    icon.src = AI_ICON_URL;
    icon.alt = "AI智审";
    icon.style.cssText = "display:block;width:100%;height:100%;object-fit:contain;pointer-events:none";
    visual.appendChild(icon);
    appendBlinkEyes(visual);
    button.appendChild(visual);
    button.style.cssText = [
      "position:fixed",
      "right:24px",
      "bottom:96px",
      "z-index:999998",
      "width:82px",
      "height:82px",
      "border:0",
      "padding:0",
      "background:transparent",
      "filter:drop-shadow(0 7px 12px rgba(30,64,175,.28)) drop-shadow(0 0 8px rgba(96,165,250,.38))",
      "transition:filter .25s ease",
      "cursor:pointer",
    ].join(";");
    if (button.animate) {
      button.animate(
        [
          { transform: "translateY(0) rotate(0deg)" },
          { transform: "translateY(-6px) rotate(-1.5deg)" },
          { transform: "translateY(0) rotate(0deg)" },
          { transform: "translateY(-2px) rotate(1.5deg)" },
          { transform: "translateY(0) rotate(0deg)" },
        ],
        { duration: 3200, iterations: Infinity, easing: "ease-in-out" }
      );
    }
    button.onmouseenter = function () {
      button.style.filter = "drop-shadow(0 10px 16px rgba(30,64,175,.36)) drop-shadow(0 0 12px rgba(96,165,250,.5))";
      visual.style.transform = "scale(1.16)";
    };
    button.onmouseleave = function () {
      button.style.filter = "drop-shadow(0 7px 12px rgba(30,64,175,.28)) drop-shadow(0 0 8px rgba(96,165,250,.38))";
      visual.style.transform = "scale(1.08)";
    };
    button.onclick = function () {
      panelOpen ? closePanel() : openPanel();
    };

    var panel = document.createElement("div");
    panel.id = panelId;
    panel.style.cssText = [
      "display:none",
      "position:fixed",
      "right:24px",
      "bottom:24px",
      "z-index:999997",
      "width:500px",
      "height:80vh",
      "max-width:calc(100vw - 32px)",
      "max-height:calc(100vh - 48px)",
      "border:1px solid rgba(96,165,250,.45)",
      "border-radius:22px",
      "overflow:hidden",
      "background:#fff",
      "box-shadow:0 28px 72px rgba(15,42,104,.28),0 0 32px rgba(59,130,246,.14)",
    ].join(";");

    var iframe = document.createElement("iframe");
    iframe.id = iframeId;
    iframe.title = "流程AI智审";
    iframe.style.cssText = "width:100%;height:100%;border:0;background:#fff;";
    panel.appendChild(iframe);

    document.body.appendChild(button);
    document.body.appendChild(panel);

    window.addEventListener("message", function (event) {
      var data = event.data;
      if (!data || typeof data !== "object") return;
      if (data.type === "WEAVER_AI_REVIEW_READY") {
        postContext("WEAVER_AI_REVIEW_CONTEXT");
      }
      if (data.type === "WEAVER_AI_REQUEST_CONTEXT") {
        postContext("WEAVER_AI_CONTEXT_RESPONSE", data.requestId);
      }
      if (data.type === "WEAVER_AI_REVIEW_CLOSE") {
        closePanel();
      }
    });
  }

  function removeElementById(id) {
    var element = document.getElementById(id);
    if (element && element.parentNode) element.parentNode.removeChild(element);
  }

  function unmount() {
    removeElementById(buttonId);
    removeElementById(panelId);
    mounted = false;
    panelOpen = false;
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", mount);
  } else {
    mount();
  }

  window.setInterval(function () {
    if (isApprovalPage()) {
      if (!mounted || !document.getElementById(buttonId)) {
        mounted = false;
        mount();
      }
      return;
    }
    if (mounted) {
      aiLog("检测到已离开审批页面，卸载 AI 智审入口", { pageMode: getWorkflowPageMode() });
      unmount();
    }
  }, 800);
})();
