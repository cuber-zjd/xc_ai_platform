/*
 * 泛微流程 AI 助手 - 流程规则配置页 ecode 脚本
 *
 * 使用方式：
 * 1. 将本文件整段复制到流程路径设置/基础信息页可加载的 ecode 脚本中。
 * 2. 只修改“现场配置区”的 AI_PLATFORM_BASE_URL、AI_SIGN、WEAVER_ENV。
 * 3. 本脚本只负责在流程设置页追加“AI填报规则”页签并打开平台 iframe，规则维护和保存都由平台完成。
 */
(function () {
  "use strict";

  // =========================
  // 现场配置区
  // =========================
  var ENABLE_AI_WORKFLOW_RULE_CONFIG = true;
  var AI_PLATFORM_BASE_URL = "http://192.168.8.79:5173";
  var AI_SIGN = "xc-fw-1af7cc98-66ed-4d55-a4cc-c6240b1f1c3c";
  var WEAVER_ENV = "test";

  // =========================
  // 内部状态
  // =========================
  var mounted = false;
  var active = false;
  var panelId = "weaver-ai-workflow-rule-panel";
  var tabId = "weaver-ai-workflow-rule-tab";
  var nativeContentDisplayCache = [];
  var observer = null;

  function aiLog() {
    if (!window.console || !console.log) return;
    var args = Array.prototype.slice.call(arguments);
    args.unshift("[泛微流程AI规则配置]");
    console.log.apply(console, args);
  }

  function aiWarn() {
    if (!window.console || !console.warn) return;
    var args = Array.prototype.slice.call(arguments);
    args.unshift("[泛微流程AI规则配置]");
    console.warn.apply(console, args);
  }

  function isWorkflowBaseInfoPage() {
    var href = window.location.href || "";
    var hash = window.location.hash || "";
    var hasWorkflowEnginePath = href.indexOf("/wui/engine.html") >= 0 && hash.indexOf("workflowengine/path") >= 0;
    var hasWorkflowId = !!getWorkflowId();
    return hasWorkflowEnginePath && hasWorkflowId;
  }

  function getWorkflowId() {
    try {
      var hash = window.location.hash || "";
      var queryIndex = hash.indexOf("?");
      if (queryIndex >= 0) {
        var params = new URLSearchParams(hash.slice(queryIndex + 1));
        var id = params.get("workflowId") || params.get("workflowid");
        if (id) return id;
      }
      var urlParams = new URLSearchParams(window.location.search || "");
      return urlParams.get("workflowId") || urlParams.get("workflowid") || "";
    } catch (error) {
      aiWarn("读取 workflowId 失败", error);
      return "";
    }
  }

  function getWorkflowName() {
    try {
      var titleInput = document.querySelector("input[name='workflowname'], input[id*='workflowname'], input[placeholder*='流程']");
      if (titleInput && titleInput.value) return String(titleInput.value).trim();
      var titleText = document.querySelector(".ant-form-item-control-input-content span, .wea-form-item-content span");
      if (titleText && titleText.textContent) return titleText.textContent.trim();
    } catch (error) {
      aiWarn("读取流程名称失败", error);
    }
    return "";
  }

  function buildIframeUrl(workflowId) {
    var url = new URL(AI_PLATFORM_BASE_URL + "/weaver/assistant/workflow-config");
    url.searchParams.set("ai_sign", AI_SIGN);
    url.searchParams.set("env", WEAVER_ENV);
    url.searchParams.set("workflowId", workflowId);
    url.searchParams.set("target_origin", window.location.origin);
    var workflowName = getWorkflowName();
    if (workflowName) url.searchParams.set("workflowName", workflowName);
    return url.toString();
  }

  function ensureStyle() {
    if (document.getElementById("weaver-ai-workflow-rule-style")) return;
    var style = document.createElement("style");
    style.id = "weaver-ai-workflow-rule-style";
    style.textContent = [
      "#" + tabId + " {",
      "  display: inline-flex;",
      "  align-items: center;",
      "  justify-content: center;",
      "  height: 44px;",
      "  min-width: 92px;",
      "  padding: 0 18px;",
      "  border: 0;",
      "  border-bottom: 2px solid transparent;",
      "  border-radius: 0;",
      "  background: transparent;",
      "  color: #333;",
      "  font-size: 13px;",
      "  line-height: 44px;",
      "  cursor: pointer;",
      "  white-space: nowrap;",
      "}",
      "#" + tabId + ":hover { color: #1890ff; }",
      "#" + tabId + ".is-active {",
      "  color: #1890ff;",
      "  border-bottom-color: #1890ff;",
      "  background: #fff;",
      "}",
      "#" + panelId + " {",
      "  display: none;",
      "  width: 100%;",
      "  min-height: 560px;",
      "  height: calc(100vh - 178px);",
      "  border: 0;",
      "  background: #fff;",
      "  overflow: hidden;",
      "}",
      "#" + panelId + ".is-active { display: block; }",
      "#" + panelId + " iframe { width: 100%; height: 100%; border: 0; }",
    ].join("\n");
    document.head.appendChild(style);
  }

  function isVisibleElement(el) {
    if (!el || el.nodeType !== 1) return false;
    var rect = el.getBoundingClientRect();
    var style = window.getComputedStyle(el);
    return rect.width > 0 && rect.height > 0 && style.display !== "none" && style.visibility !== "hidden";
  }

  function textOf(el) {
    return (el && el.textContent ? el.textContent : "").replace(/\s+/g, "");
  }

  function findLabelElement(label) {
    var nodes = document.querySelectorAll("div, span, a, button, li");
    for (var i = 0; i < nodes.length; i += 1) {
      var node = nodes[i];
      if (!isVisibleElement(node)) continue;
      if (textOf(node) === label) return node;
    }
    return null;
  }

  function findTabItem(label) {
    var labelNode = findLabelElement(label);
    var current = labelNode;
    while (current && current !== document.body) {
      var currentText = textOf(current);
      var parentText = textOf(current.parentElement);
      if (currentText === label && parentText.indexOf("基础设置") >= 0 && parentText.indexOf("表单管理") >= 0) {
        return current;
      }
      if (currentText === label && current.parentElement && current.parentElement.children.length >= 3) {
        return current;
      }
      current = current.parentElement;
    }
    return labelNode;
  }

  function findPrimaryTabBar() {
    var advancedTab = findTabItem("高级设置");
    var current = advancedTab;
    while (current && current !== document.body) {
      var text = textOf(current);
      var rect = current.getBoundingClientRect();
      if (
        text.indexOf("基础设置") >= 0 &&
        text.indexOf("表单管理") >= 0 &&
        text.indexOf("流转设置") >= 0 &&
        text.indexOf("高级设置") >= 0 &&
        rect.height <= 80
      ) {
        return current;
      }
      current = current.parentElement;
    }
    return advancedTab && advancedTab.parentElement ? advancedTab.parentElement : null;
  }

  function getPrimaryContentRoot(tabBar) {
    var current = tabBar;
    while (current && current !== document.body) {
      var parent = current.parentElement;
      if (parent) {
        var rect = parent.getBoundingClientRect();
        var tabRect = tabBar.getBoundingClientRect();
        if (rect.width >= tabRect.width && rect.height > tabRect.height + 120) {
          return parent;
        }
      }
      current = parent;
    }
    return document.body;
  }

  function hideNativeContent(tabBar) {
    var root = getPrimaryContentRoot(tabBar);
    var tabRect = tabBar.getBoundingClientRect();
    nativeContentDisplayCache = [];
    var children = Array.prototype.slice.call(root.children || []);
    children.forEach(function (child) {
      if (child.id === panelId) return;
      if (child.contains(tabBar) || tabBar.contains(child)) return;
      var rect = child.getBoundingClientRect();
      if (rect.top >= tabRect.bottom - 2 && isVisibleElement(child)) {
        nativeContentDisplayCache.push({ el: child, display: child.style.display });
        child.style.display = "none";
      }
    });
    return root;
  }

  function showNativeContent() {
    nativeContentDisplayCache.forEach(function (item) {
      if (item.el) item.el.style.display = item.display || "";
    });
    nativeContentDisplayCache = [];
  }

  function setActiveTab(isActive) {
    active = isActive;
    var aiTab = document.getElementById(tabId);
    var panel = document.getElementById(panelId);
    if (aiTab) {
      if (isActive) aiTab.classList.add("is-active");
      else aiTab.classList.remove("is-active");
    }
    if (panel) {
      if (isActive) panel.classList.add("is-active");
      else panel.classList.remove("is-active");
    }
  }

  function openAiRulePanel(tabBar) {
    var root = hideNativeContent(tabBar);
    var panel = document.getElementById(panelId);
    if (panel && panel.parentElement !== root) root.appendChild(panel);
    setActiveTab(true);
  }

  function closeAiRulePanel() {
    showNativeContent();
    setActiveTab(false);
  }

  function bindNativeTabClose(tabBar) {
    if (tabBar.getAttribute("data-ai-rule-close-bound") === "1") return;
    tabBar.setAttribute("data-ai-rule-close-bound", "1");
    tabBar.addEventListener("click", function (event) {
      var target = event.target;
      if (target && target.closest && target.closest("#" + tabId)) return;
      if (active) closeAiRulePanel();
    }, true);
  }

  function mount() {
    if (!ENABLE_AI_WORKFLOW_RULE_CONFIG) return;
    if (mounted) return;
    if (!isWorkflowBaseInfoPage()) {
      aiLog("当前页面不是流程路径设置页，暂不挂载", {
        href: window.location.href,
        hash: window.location.hash,
        workflowId: getWorkflowId()
      });
      return;
    }

    var workflowId = getWorkflowId();
    if (!workflowId) {
      aiWarn("未识别到 workflowId，暂不挂载");
      return;
    }

    ensureStyle();

    var advancedTab = findTabItem("高级设置");
    var tabBar = findPrimaryTabBar();
    if (!advancedTab || !tabBar) {
      aiWarn("未找到流程设置一级页签，稍后重试");
      return;
    }

    if (!document.getElementById(tabId)) {
      var tab = document.createElement("button");
      tab.id = tabId;
      tab.type = "button";
      tab.textContent = "AI填报规则";
      tab.onclick = function (event) {
        event.preventDefault();
        event.stopPropagation();
        if (active) {
          closeAiRulePanel();
          return;
        }
        openAiRulePanel(tabBar);
      };
      advancedTab.parentElement.insertBefore(tab, advancedTab.nextSibling);
    }

    if (!document.getElementById(panelId)) {
      var panel = document.createElement("div");
      panel.id = panelId;
      var iframe = document.createElement("iframe");
      iframe.src = buildIframeUrl(workflowId);
      iframe.title = "流程 AI 填报规则配置";
      panel.appendChild(iframe);
      getPrimaryContentRoot(tabBar).appendChild(panel);
    }

    bindNativeTabClose(tabBar);
    mounted = true;
    aiLog("流程规则配置入口已挂载", {
      env: WEAVER_ENV,
      workflowId: workflowId,
      mode: "primary-tab",
      iframe: document.querySelector("#" + panelId + " iframe") ? document.querySelector("#" + panelId + " iframe").src : ""
    });
  }

  function unmountIfNeeded() {
    if (isWorkflowBaseInfoPage()) return;
    var panel = document.getElementById(panelId);
    var tab = document.getElementById(tabId);
    if (panel) panel.remove();
    if (tab) tab.remove();
    showNativeContent();
    mounted = false;
  }

  function checkRoute() {
    unmountIfNeeded();
    window.setTimeout(mount, 300);
  }

  aiLog("脚本已加载", {
    href: window.location.href,
    hash: window.location.hash,
    workflowId: getWorkflowId()
  });
  window.addEventListener("hashchange", checkRoute);
  observer = new MutationObserver(function () {
    if (mounted && (!document.getElementById(tabId) || !document.getElementById(panelId))) {
      mounted = false;
      active = false;
      showNativeContent();
    }
    if (!mounted) window.setTimeout(mount, 100);
  });
  observer.observe(document.body, { childList: true, subtree: true });
  window.setTimeout(mount, 500);
  window.setTimeout(mount, 1500);
  window.setTimeout(mount, 3000);
  window.setTimeout(mount, 6000);
})();
