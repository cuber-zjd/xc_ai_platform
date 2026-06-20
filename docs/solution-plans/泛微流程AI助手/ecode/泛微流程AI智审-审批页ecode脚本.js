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
  var AI_PLATFORM_BASE_URL = "http://localhost:5173";
  var AI_SIGN = "change-me";
  var WEAVER_ENV = "test";

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

  function getRequestId() {
    var baseInfo = safeGetBaseInfo();
    return String(baseInfo.requestid || baseInfo.requestId || "");
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
      baseInfo: baseInfo,
      url: window.location.href,
      fields: collectFields(),
    };
  }

  function buildIframeUrl() {
    var workflowId = encodeURIComponent(getWorkflowId());
    var requestId = encodeURIComponent(getRequestId());
    var nodeId = encodeURIComponent(getNodeId());
    var targetOrigin = encodeURIComponent(window.location.origin);
    return (
      AI_PLATFORM_BASE_URL.replace(/\/$/, "") +
      "/weaver/assistant/review?ai_sign=" +
      encodeURIComponent(AI_SIGN) +
      "&env=" +
      encodeURIComponent(WEAVER_ENV) +
      "&workflow_id=" +
      workflowId +
      "&request_id=" +
      requestId +
      "&node_id=" +
      nodeId +
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

  function openPanel() {
    panelOpen = true;
    var panel = document.getElementById(panelId);
    var iframe = document.getElementById(iframeId);
    if (panel) panel.style.display = "block";
    if (iframe) {
      iframe.src = buildIframeUrl();
      setTimeout(function () {
        postContext("WEAVER_AI_REVIEW_CONTEXT");
      }, 500);
    }
  }

  function closePanel() {
    panelOpen = false;
    var panel = document.getElementById(panelId);
    if (panel) panel.style.display = "none";
  }

  function mount() {
    if (!ENABLE_WEAVER_AI_REVIEW || mounted) return;
    mounted = true;
    aiLog("开始挂载 AI 智审入口", safeGetBaseInfo());

    var button = document.createElement("button");
    button.id = buttonId;
    button.type = "button";
    button.innerHTML = "AI<br/>智审";
    button.style.cssText = [
      "position:fixed",
      "right:24px",
      "bottom:96px",
      "z-index:999998",
      "width:56px",
      "height:56px",
      "border-radius:50%",
      "border:0",
      "background:#0f766e",
      "color:#fff",
      "font-size:13px",
      "font-weight:700",
      "box-shadow:0 16px 36px rgba(15,118,110,.28)",
      "cursor:pointer",
    ].join(";");
    button.onclick = function () {
      panelOpen ? closePanel() : openPanel();
    };

    var panel = document.createElement("div");
    panel.id = panelId;
    panel.style.cssText = [
      "display:none",
      "position:fixed",
      "right:24px",
      "bottom:164px",
      "z-index:999997",
      "width:460px",
      "height:72vh",
      "max-width:calc(100vw - 56px)",
      "max-height:calc(100vh - 190px)",
      "border:1px solid #dbe3ef",
      "border-radius:12px",
      "overflow:hidden",
      "background:#fff",
      "box-shadow:0 24px 60px rgba(15,23,42,.18)",
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

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", mount);
  } else {
    mount();
  }
})();
