/*
 * 泛微流程 AI 助手 ecode 完整脚本
 *
 * 使用方式：
 * 1. 将本文件整段复制到流程发起页面可加载的 ecode 前置脚本中。
 * 2. 只修改“现场配置区”的 AI_PLATFORM_BASE_URL、AI_SIGN、WEAVER_ENV。
 * 3. 本脚本只负责悬浮入口、iframe、WfForm 上下文采集和结构化动作执行。
 */
(function () {
  "use strict";

  // =========================
  // 现场配置区
  // =========================
  var ENABLE_AI_FLOW_ASSISTANT = true;
  var ENABLE_ON_PROCESS_PAGE = false;
  var AI_PLATFORM_BASE_URL = "http://192.168.8.79:5173";
  var AI_ICON_URL = AI_PLATFORM_BASE_URL.replace(/\/$/, "") + "/ai/weaver-assistant/mascot-selected.png";
  var AI_SIGN = "xc-fw-1af7cc98-66ed-4d55-a4cc-c6240b1f1c3c";
  var WEAVER_ENV = "test";

  // =========================
  // 内部状态
  // =========================
  var aiFlowAssistantMounted = false;
  var aiFieldConfigLoaded = false;
  var aiFieldConfigLoading = false;
  var aiFieldConfig = [];
  var aiFieldConfigError = "";
  var platformOrigin = getOrigin(AI_PLATFORM_BASE_URL);
  var WRITE_STEP_DELAY_MS = 700;
  var WRITE_HIGHLIGHT_CLASS = "weaver-ai-field-writing";

  function aiLog() {
    if (!window.console || !console.log) return;
    var args = Array.prototype.slice.call(arguments);
    args.unshift("[泛微流程AI助手]");
    console.log.apply(console, args);
  }

  function aiWarn() {
    if (!window.console || !console.warn) return;
    var args = Array.prototype.slice.call(arguments);
    args.unshift("[泛微流程AI助手]");
    console.warn.apply(console, args);
  }

  function getOrigin(url) {
    try {
      return new URL(url, window.location.href).origin;
    } catch (error) {
      aiWarn("平台地址解析失败", url, error);
      return url;
    }
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

    var baseInfo = getBaseInfo();
    var baseIsCreate = String(baseInfo.iscreate || baseInfo.isCreate || "").toLowerCase();
    if (baseIsCreate === "1" || baseIsCreate === "true") return "create";
    if (baseIsCreate === "0" || baseIsCreate === "false") return "process";

    var requestId = String(
      baseInfo.requestid ||
        baseInfo.requestId ||
        getPageParam("requestid") ||
        getPageParam("requestId") ||
        getPageParam("resourceid") ||
        getPageParam("resourceId") ||
        ""
    );
    if (requestId && requestId !== "0" && requestId !== "-1") return "process";
    return "unknown";
  }

  function isWorkflowReqPage() {
    var hash = window.location.hash || "";
    var pathname = window.location.pathname || "";
    var isRequestRoute = hash.indexOf("#/main/workflow/req") === 0 || pathname.indexOf("/workflow/") >= 0;
    if (!isRequestRoute) return false;
    var pageMode = getWorkflowPageMode();
    return pageMode === "create" || (ENABLE_ON_PROCESS_PAGE && pageMode === "process");
  }

  function getBaseInfo() {
    try {
      if (window.WfForm && typeof WfForm.getBaseInfo === "function") {
        return WfForm.getBaseInfo() || {};
      }
    } catch (error) {
      aiWarn("读取流程基础信息失败", error);
    }
    return {};
  }

  function getWorkflowId() {
    var baseInfo = getBaseInfo();
    return String(baseInfo.workflowid || baseInfo.workflowId || "");
  }

  function normalizeHeaderValue(value) {
    return String(value || "").trim();
  }

  function loadFieldConfig(callback) {
    if (aiFieldConfigLoaded) {
      callback && callback();
      return;
    }
    if (aiFieldConfigLoading) {
      window.setTimeout(function () {
        loadFieldConfig(callback);
      }, 200);
      return;
    }

    var workflowId = getWorkflowId();
    if (!workflowId) {
      aiFieldConfigError = "未识别到 workflowid";
      callback && callback();
      return;
    }

    var safeAiSign = normalizeHeaderValue(AI_SIGN);
    if (!safeAiSign || safeAiSign.indexOf("替换为") >= 0) {
      aiFieldConfigError = "AI_SIGN 未配置";
      aiWarn(aiFieldConfigError);
      callback && callback();
      return;
    }

    aiFieldConfigLoading = true;
    aiFieldConfigError = "";
    var fieldConfigStartedAt = Date.now();

    var params = new URLSearchParams();
    params.set("workflow_id", workflowId);
    params.set("env", WEAVER_ENV);

    fetch(AI_PLATFORM_BASE_URL + "/ai-api/v1/weaver/ai-assistant/field-config?" + params.toString(), {
      method: "GET",
      headers: {
        "ai-sign": safeAiSign
      }
    })
      .then(function (response) {
        if (!response.ok) {
          throw new Error("字段配置接口请求失败：" + response.status);
        }
        return response.json();
      })
      .then(function (result) {
        var data = result && result.data ? result.data : {};
        aiFieldConfig = Array.isArray(data.fields) ? data.fields : [];
        aiFieldConfigLoaded = true;
        aiLog("字段配置加载成功", {
          env: data.env || WEAVER_ENV,
          workflowId: data.workflowId || workflowId,
          workflowName: data.workflowName,
          fields: aiFieldConfig.length,
          elapsedMs: Date.now() - fieldConfigStartedAt
        });
      })
      .catch(function (error) {
        aiFieldConfigError = error && error.message ? error.message : "字段配置加载失败";
        aiWarn(aiFieldConfigError, {
          elapsedMs: Date.now() - fieldConfigStartedAt,
          error: error
        });
      })
      .finally(function () {
        aiFieldConfigLoading = false;
        callback && callback();
      });
  }

  function getFieldValue(fieldId) {
    try {
      if (window.WfForm && typeof WfForm.getFieldValue === "function") {
        return WfForm.getFieldValue(fieldId);
      }
    } catch (error) {
      aiWarn("读取字段值失败", fieldId, error);
    }
    return "";
  }

  function getFieldDisplayValue(fieldId) {
    var candidates = [fieldId + "span", fieldId + "_span", fieldId + "Span"];
    for (var i = 0; i < candidates.length; i += 1) {
      try {
        if (window.WfForm && typeof WfForm.getFieldValue === "function") {
          var wfValue = WfForm.getFieldValue(candidates[i]);
          if (wfValue !== undefined && wfValue !== null && String(wfValue).trim() !== "") {
            return String(wfValue).trim();
          }
        }
      } catch (error) {}
      try {
        var span = document.getElementById(candidates[i]);
        var spanText = readNodeText(span);
        if (spanText) return spanText;
      } catch (error) {}
    }

    try {
      var fieldNode = document.getElementById(fieldId) || document.querySelector('[name="' + fieldId + '"]');
      var nodeText = readNodeText(fieldNode);
      if (nodeText) return nodeText;
      var container = findFieldContainer(fieldNode);
      var containerText = readNodeText(container);
      if (containerText) return containerText;
    } catch (error) {
      aiWarn("读取字段显示值失败", fieldId, error);
    }
    return "";
  }

  function normalizeFieldValue(value, item) {
    var normalized = normalizeDisplayText(value);
    if (!normalized) return "";
    var fieldText = String((item && (item.label || item.fieldName || item.bizKey || item.fieldId)) || "");
    var placeholderTexts = [
      "简要说明请假事由",
      "请输入",
      "请选择",
      "无",
      "undefined"
    ];
    for (var i = 0; i < placeholderTexts.length; i += 1) {
      if (normalized === placeholderTexts[i]) return "";
    }
    if (/原因|事由|说明/.test(fieldText) && /^简要说明/.test(normalized)) {
      return "";
    }
    return normalized;
  }

  function readNodeText(node) {
    if (!node) return "";
    var value = "";
    if (typeof node.value === "string" && node.type !== "hidden") {
      value = node.value;
    }
    if (!value && typeof node.innerText === "string") {
      value = node.innerText;
    }
    if (!value && typeof node.textContent === "string") {
      value = node.textContent;
    }
    return normalizeDisplayText(value);
  }

  function normalizeDisplayText(value) {
    return String(value || "")
      .replace(/\s+/g, " ")
      .replace(/^\s+|\s+$/g, "");
  }

  function findFieldContainer(node) {
    var current = node;
    for (var i = 0; i < 4 && current; i += 1) {
      if (current.getAttribute && current.getAttribute("data-fieldmark")) {
        return current;
      }
      if (current.innerText && normalizeDisplayText(current.innerText)) {
        return current;
      }
      current = current.parentNode;
    }
    return null;
  }

  function getFieldContainer(fieldId) {
    try {
      var direct = document.querySelector('[data-fieldmark="' + fieldId + '"]');
      if (direct) return direct;
    } catch (error) {}
    var nodes = getFieldNodes(fieldId);
    for (var i = 0; i < nodes.length; i += 1) {
      var container = findFieldContainer(nodes[i]);
      if (container) return container;
    }
    return null;
  }

  function getFieldNodes(fieldId) {
    try {
      var selector = [
        '[name="' + fieldId + '"]',
        "#" + fieldId,
        '[data-fieldid="' + fieldId + '"]',
        '[data-fieldmark="' + fieldId + '"]',
        "#" + fieldId + "span",
        "#" + fieldId + "_span",
        "#" + fieldId + "Span"
      ].join(",");
      return Array.prototype.slice.call(document.querySelectorAll(selector));
    } catch (error) {
      aiWarn("查找字段节点失败", fieldId, error);
      return [];
    }
  }

  function isNodeVisible(node) {
    if (!node || !document.documentElement.contains(node)) return false;
    if (node.type === "hidden") return false;
    var current = node;
    while (current && current !== document.documentElement) {
      try {
        var style = window.getComputedStyle(current);
        if (style.display === "none" || style.visibility === "hidden" || style.opacity === "0") {
          return false;
        }
      } catch (error) {}
      current = current.parentElement;
    }
    try {
      if (node.getClientRects && node.getClientRects().length > 0) return true;
    } catch (error) {}
    return !!normalizeDisplayText(node.innerText || node.textContent || node.value || "");
  }

  function findVisibleFieldNode(fieldId) {
    var directContainer = getFieldContainer(fieldId);
    if (isNodeVisible(directContainer)) return directContainer;
    var nodes = getFieldNodes(fieldId);
    for (var i = 0; i < nodes.length; i += 1) {
      if (isNodeVisible(nodes[i])) return nodes[i];
      var container = findFieldContainer(nodes[i]);
      if (isNodeVisible(container)) return container;
    }
    return null;
  }

  function hasReadonlyMarker(node) {
    var current = node;
    for (var i = 0; i < 6 && current; i += 1) {
      try {
        var className = String(current.className || "");
        if (
          /\bwf-field-readonly\b/.test(className) ||
          /\bwea-field-readonly\b/.test(className) ||
          /\breadonly\b/.test(className) ||
          /\bdisabled\b/.test(className) ||
          current.getAttribute("readonly") != null ||
          current.getAttribute("disabled") != null ||
          current.getAttribute("aria-disabled") === "true"
        ) {
          return true;
        }
      } catch (error) {}
      current = current.parentElement;
    }
    return false;
  }

  function isFieldVisible(fieldId) {
    return !!findVisibleFieldNode(fieldId);
  }

  function isFieldWritable(fieldId) {
    if (!isFieldVisible(fieldId)) return false;
    try {
      var container = getFieldContainer(fieldId);
      if (!container || !isNodeVisible(container) || hasReadonlyMarker(container)) return false;
      return hasEditableWidget(container);
    } catch (error) {
      aiWarn("判断字段可写状态失败", fieldId, error);
    }
    return false;
  }

  function hasEditableWidget(container) {
    var nativeInputs = container.querySelectorAll("input:not([type='hidden']), textarea, select");
    for (var i = 0; i < nativeInputs.length; i += 1) {
      var node = nativeInputs[i];
      if (!isNodeVisible(node)) continue;
      if (node.disabled || node.readOnly || node.getAttribute("aria-disabled") === "true") continue;
      if (hasReadonlyMarker(node)) continue;
      return true;
    }

    var selectNode = container.querySelector(".ant-select-enabled, .wea-select");
    if (selectNode && isNodeVisible(selectNode) && !hasReadonlyMarker(selectNode)) {
      var selectClass = String(selectNode.className || "");
      if (!/\bant-select-disabled\b/.test(selectClass)) return true;
    }

    var dateNode = container.querySelector(".wea-date-picker");
    if (dateNode && isNodeVisible(dateNode) && !hasReadonlyMarker(dateNode)) {
      return true;
    }

    var browserNode = container.querySelector(".wea-browser");
    if (browserNode && isNodeVisible(browserNode) && !hasReadonlyMarker(browserNode)) {
      return true;
    }

    var editableNode = container.querySelector("[contenteditable='true']");
    return !!(editableNode && isNodeVisible(editableNode) && !hasReadonlyMarker(editableNode));
  }

  function isSystemAutoField(item) {
    var text = String((item && (item.label || item.fieldName || item.bizKey || item.fieldId)) || "");
    return /申请人|申请日期|申请公司|申请部门|创建人|创建日期|所属公司|所属部门/.test(text);
  }

  function collectFormContext() {
    var baseInfo = getBaseInfo();
    var fields = {};

    aiFieldConfig.forEach(function (item) {
      if (!item || !item.fieldId) return;
      var key = item.bizKey || item.fieldName || item.fieldId;
      var systemAutoField = isSystemAutoField(item);
      var rawValue = normalizeFieldValue(getFieldValue(item.fieldId), item);
      var displayValue = normalizeFieldValue(getFieldDisplayValue(item.fieldId), item);
      var visible = isFieldVisible(item.fieldId);
      var writable = visible && !systemAutoField && item.writable !== false && isFieldWritable(item.fieldId);
      fields[key] = {
        label: item.label || item.fieldName || item.fieldId,
        fieldId: item.fieldId,
        type: item.type || "text",
        options: item.options || [],
        browserType: item.browserType || item.fieldType || "",
        writable: writable,
        visible: visible,
        value: rawValue,
        displayValue: displayValue,
        readonlyReason: writable ? "" : systemAutoField ? "系统自动带出字段" : visible ? "当前页面控件不可编辑" : "当前页面不可见字段"
      };
    });

    return {
      env: WEAVER_ENV,
      baseInfo: baseInfo,
      url: window.location.href,
      fields: fields
    };
  }

  function postContextToIframe(messageType, requestId) {
    var iframe = document.getElementById("ai-flow-iframe");
    if (!iframe || !iframe.contentWindow) return;
    loadFieldConfig(function () {
      iframe.contentWindow.postMessage(
        {
          type: messageType || "WEAVER_AI_CONTEXT",
          requestId: requestId,
          context: collectFormContext()
        },
        platformOrigin
      );
    });
  }

  function applyAiActions(actions) {
    if (!actions || !actions.length) {
      aiLog("没有可执行的写入动作");
      postApplyResult(0, 0, []);
      return;
    }
    var successCount = 0;
    var failures = [];
    var index = 0;

    function runNext() {
      if (index >= actions.length) {
        postApplyResult(successCount, failures.length, failures);
        return;
      }

      var action = actions[index];
      index += 1;
      window.setTimeout(function () {
        executeOneAction(action, function (result) {
          if (result && result.success) {
            successCount += 1;
          } else if (result && result.failure) {
            failures.push(result.failure);
          }
          window.setTimeout(runNext, WRITE_STEP_DELAY_MS);
        });
      }, WRITE_STEP_DELAY_MS);
    }

    runNext();
  }

  function executeOneAction(action, done) {
    var highlightTarget = null;
    try {
      if (action.type === "set_field" && action.field) {
        highlightTarget = startFieldHighlight(action.field);
      }
      window.setTimeout(function () {
        try {
          if (action.type === "set_field" && action.field) {
            if (!isFieldWritable(action.field)) {
              throw new Error("字段当前不可见或不可编辑");
            }
            var fieldValue = action.value == null ? "" : String(action.value);
            var changePayload = {
              value: fieldValue
            };
            var specialObj = action.specialObj || action.specialobj || [];
            if (specialObj && specialObj.length) {
              changePayload.specialobj = specialObj.map(function (item) {
                return {
                  id: String(item.id || item.value || ""),
                  name: String(item.name || item.label || item.id || item.value || "")
                };
              });
            }
            WfForm.changeFieldValue(action.field, changePayload);
            aiLog("已写入字段", action.field, {
              value: fieldValue,
              displayValue: action.displayValue || "",
              specialobj: changePayload.specialobj || []
            });
            stopFieldHighlight(highlightTarget);
            done({ success: true });
            return;
          }
          if (action.type === "add_detail_row" && action.detail) {
            WfForm.addDetailRow(action.detail, action.values || {});
            aiLog("已新增明细行", action.detail);
            stopFieldHighlight(highlightTarget);
            done({ success: true });
            return;
          }
          stopFieldHighlight(highlightTarget);
          done({ success: false });
        } catch (error) {
          stopFieldHighlight(highlightTarget);
          done({
            failure: {
              type: action.type,
              field: action.field,
              label: action.label,
              value: action.value,
              displayValue: action.displayValue,
              detail: action.detail,
              message: error && error.message ? error.message : String(error)
            }
          });
          aiWarn("执行写入动作失败", action, error);
        }
      }, WRITE_STEP_DELAY_MS);
    } catch (error) {
      stopFieldHighlight(highlightTarget);
      done({
        failure: {
          type: action.type,
          field: action.field,
          label: action.label,
          value: action.value,
          displayValue: action.displayValue,
          detail: action.detail,
          message: error && error.message ? error.message : String(error)
        }
      });
      aiWarn("执行写入动作失败", action, error);
    }
  }

  function ensureHighlightStyle() {
    if (document.getElementById("weaver-ai-field-writing-style")) return;
    var style = document.createElement("style");
    style.id = "weaver-ai-field-writing-style";
    style.innerHTML =
      "." + WRITE_HIGHLIGHT_CLASS + "{" +
      "outline:2px solid #14b8a6!important;" +
      "box-shadow:0 0 0 4px rgba(20,184,166,.18)!important;" +
      "border-radius:6px!important;" +
      "transition:box-shadow .2s ease, outline-color .2s ease!important;" +
      "}";
    document.head.appendChild(style);
  }

  function startFieldHighlight(fieldId) {
    ensureHighlightStyle();
    var target = findVisibleFieldNode(fieldId);
    if (!target) return null;
    try {
      target.classList.add(WRITE_HIGHLIGHT_CLASS);
      target.scrollIntoView({ behavior: "smooth", block: "center", inline: "nearest" });
    } catch (error) {
      aiWarn("字段高亮失败", fieldId, error);
    }
    return target;
  }

  function stopFieldHighlight(target) {
    if (!target) return;
    try {
      target.classList.remove(WRITE_HIGHLIGHT_CLASS);
    } catch (error) {}
  }

  function postApplyResult(successCount, failedCount, failures) {
    var iframe = document.getElementById("ai-flow-iframe");
    if (!iframe || !iframe.contentWindow) return;
    iframe.contentWindow.postMessage(
      {
        type: "WEAVER_AI_APPLY_RESULT",
        successCount: successCount,
        failedCount: failedCount,
        failures: failures || []
      },
      platformOrigin
    );
  }

  function buildAssistantUrl() {
    var url = AI_PLATFORM_BASE_URL + "/ai/weaver/assistant/embed";
    var params = new URLSearchParams();
    params.set("ai_sign", AI_SIGN);
    params.set("target_origin", window.location.origin);
    return url + "?" + params.toString();
  }

  function animateAssistantPanel(panel, opening) {
    var button = document.getElementById("ai-flow-float-button");
    if (!panel || !button || typeof panel.animate !== "function") {
      panel.style.display = opening ? "block" : "none";
      button.style.opacity = opening ? "0" : "1";
      button.style.pointerEvents = opening ? "none" : "auto";
      return Promise.resolve();
    }

    if (opening) panel.style.display = "block";
    var panelAnimation = panel.animate(
      opening
        ? [
            { opacity: 0, transform: "translate(20px, 24px) scale(.14)", borderRadius: "48px", clipPath: "circle(10% at 92% 94%)" },
            { opacity: 1, transform: "translate(0, 0) scale(1)", borderRadius: "16px", clipPath: "circle(150% at 92% 94%)" },
          ]
        : [
            { opacity: 1, transform: "translate(0, 0) scale(1)", borderRadius: "16px", clipPath: "circle(150% at 92% 94%)" },
            { opacity: 0, transform: "translate(20px, 24px) scale(.14)", borderRadius: "48px", clipPath: "circle(10% at 92% 94%)" },
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
    return panelAnimation.finished.catch(function () {}).then(function () {
      if (!opening) panel.style.display = "none";
    });
  }

  function closeAiAssistant() {
    var panel = document.getElementById("ai-flow-iframe-panel");
    if (!panel || panel.style.display === "none") return;
    animateAssistantPanel(panel, false);
  }

  function openAiAssistant() {
    var panel = document.getElementById("ai-flow-iframe-panel");
    if (!panel) {
      panel = document.createElement("div");
      panel.id = "ai-flow-iframe-panel";
      panel.style.position = "fixed";
      panel.style.right = "28px";
      panel.style.bottom = "24px";
      panel.style.zIndex = "2147483647";
      panel.style.width = "500px";
      panel.style.maxWidth = "calc(100vw - 32px)";
      panel.style.height = "80vh";
      panel.style.maxHeight = "calc(100vh - 48px)";
      panel.style.border = "1px solid rgba(96,165,250,.45)";
      panel.style.borderRadius = "22px";
      panel.style.overflow = "hidden";
      panel.style.boxShadow = "0 28px 72px rgba(15,42,104,.28), 0 0 32px rgba(59,130,246,.14)";
      panel.style.background = "#fff";
      panel.style.display = "none";

      var iframe = document.createElement("iframe");
      iframe.id = "ai-flow-iframe";
      iframe.src = buildAssistantUrl();
      iframe.style.width = "100%";
      iframe.style.height = "100%";
      iframe.style.border = "0";
      panel.appendChild(iframe);
      document.body.appendChild(panel);
    }

    var willOpen = panel.style.display === "none" || panel.style.display === "";
    if (willOpen) {
      animateAssistantPanel(panel, true);
      postContextToIframe("WEAVER_AI_CONTEXT");
    } else {
      closeAiAssistant();
    }
  }

  function appendBlinkEyes(container) {
    ["28.5%", "56.3%"].forEach(function (left) {
      var eye = document.createElement("span");
      eye.style.position = "absolute";
      eye.style.left = left;
      eye.style.top = "54.1%";
      eye.style.zIndex = "2";
      eye.style.width = "15.2%";
      eye.style.height = "7.4%";
      eye.style.borderRadius = "999px";
      eye.style.overflow = "hidden";
      eye.style.background = "#061945";
      eye.style.pointerEvents = "none";
      eye.style.transform = "scaleY(0)";
      eye.style.transformOrigin = "center";

      var closedLine = document.createElement("span");
      closedLine.style.position = "absolute";
      closedLine.style.left = "14%";
      closedLine.style.right = "14%";
      closedLine.style.top = "50%";
      closedLine.style.height = "2px";
      closedLine.style.borderRadius = "999px";
      closedLine.style.background = "#67e8f9";
      closedLine.style.boxShadow = "0 0 5px rgba(34,211,238,.95)";
      closedLine.style.transform = "translateY(-50%)";
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

  function mountAiButton() {
    if (aiFlowAssistantMounted) return;
    if (!ENABLE_AI_FLOW_ASSISTANT || !isWorkflowReqPage() || !window.WfForm) return;

    removeElementById("weaver-ai-review-button");
    removeElementById("weaver-ai-review-panel");
    aiFlowAssistantMounted = true;

    var btn = document.createElement("button");
    btn.id = "ai-flow-float-button";
    btn.type = "button";
    btn.title = "AI填单助手";
    btn.style.position = "fixed";
    btn.style.right = "28px";
    btn.style.bottom = "88px";
    btn.style.zIndex = "2147483647";
    btn.style.width = "82px";
    btn.style.height = "82px";
    btn.style.border = "0";
    btn.style.background = "transparent";
    btn.style.padding = "0";
    btn.style.cursor = "pointer";
    btn.style.filter = "drop-shadow(0 7px 12px rgba(30,64,175,.28)) drop-shadow(0 0 8px rgba(96,165,250,.38))";
    btn.style.transition = "filter .25s ease";

    var visual = document.createElement("span");
    visual.style.position = "absolute";
    visual.style.inset = "0";
    visual.style.display = "block";
    visual.style.transform = "scale(1.08)";
    visual.style.transition = "transform .22s ease";

    var icon = document.createElement("img");
    icon.src = AI_ICON_URL;
    icon.alt = "AI填单助手";
    icon.style.display = "block";
    icon.style.width = "100%";
    icon.style.height = "100%";
    icon.style.objectFit = "contain";
    icon.style.pointerEvents = "none";
    visual.appendChild(icon);
    appendBlinkEyes(visual);
    btn.appendChild(visual);

    if (btn.animate) {
      btn.animate(
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
    btn.onmouseenter = function () {
      btn.style.filter = "drop-shadow(0 10px 16px rgba(30,64,175,.36)) drop-shadow(0 0 12px rgba(96,165,250,.5))";
      visual.style.transform = "scale(1.16)";
    };
    btn.onmouseleave = function () {
      btn.style.filter = "drop-shadow(0 7px 12px rgba(30,64,175,.28)) drop-shadow(0 0 8px rgba(96,165,250,.38))";
      visual.style.transform = "scale(1.08)";
    };

    btn.onclick = openAiAssistant;
    document.body.appendChild(btn);

    loadFieldConfig();
    aiLog("AI填单入口已挂载", { pageMode: getWorkflowPageMode() });
  }

  function removeElementById(id) {
    var element = document.getElementById(id);
    if (element && element.parentNode) element.parentNode.removeChild(element);
  }

  function unmountAiAssistant() {
    removeElementById("ai-flow-float-button");
    removeElementById("ai-flow-iframe-panel");

    aiFlowAssistantMounted = false;
    aiFieldConfigLoaded = false;
    aiFieldConfigLoading = false;
    aiFieldConfig = [];
    aiFieldConfigError = "";
  }

  window.addEventListener("message", function (event) {
    if (event.origin !== platformOrigin) return;
    var data = event.data || {};

    if (data.type === "WEAVER_AI_READY") {
      postContextToIframe("WEAVER_AI_CONTEXT");
    }
    if (data.type === "WEAVER_AI_REQUEST_CONTEXT") {
      postContextToIframe("WEAVER_AI_CONTEXT_RESPONSE", data.requestId);
    }
    if (data.type === "WEAVER_AI_APPLY_ACTIONS") {
      applyAiActions(data.actions || []);
    }
    if (data.type === "WEAVER_AI_CLOSE") {
      closeAiAssistant();
    }
  });

  if (window.ecodeSDK && typeof ecodeSDK.overwritePropsFnQueueMapSet === "function") {
    ecodeSDK.overwritePropsFnQueueMapSet("WeaReqTop", {
      fn: function () {
        mountAiButton();
      },
      order: 1,
      desc: "流程页面挂载AI填单助手"
    });
  } else {
    aiWarn("未检测到 ecodeSDK，已启用定时挂载兜底");
  }

  var aiCheckCount = 0;
  var aiTimer = window.setInterval(function () {
    aiCheckCount += 1;
    mountAiButton();
    if (aiFlowAssistantMounted || aiCheckCount > 60) {
      window.clearInterval(aiTimer);
    }
  }, 500);

  var lastHash = window.location.hash;
  window.setInterval(function () {
    var currentHash = window.location.hash;
    if (currentHash === lastHash) {
      if (aiFlowAssistantMounted && !isWorkflowReqPage()) {
        aiLog("检测到已离开发起页面，卸载 AI 填单入口", { pageMode: getWorkflowPageMode() });
        unmountAiAssistant();
      }
      return;
    }

    lastHash = currentHash;
    unmountAiAssistant();

    window.setTimeout(function () {
      mountAiButton();
    }, 500);
  }, 800);
})();
