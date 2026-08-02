/*
 * 泛微流程 AI 智审 - 规则配置页 ecode 脚本
 *
 * 使用方式：
 * 1. 复制本文件整段到流程路径设置/基础信息页可加载的 ecode 脚本中。
 * 2. 修改现场配置区的 AI_PLATFORM_BASE_URL、AI_SIGN、WEAVER_ENV。
 * 3. 脚本会在“基础设置 / 表单管理 / 流转设置 / 高级设置”同级区域追加“AI智审规则”页签。
 */
(function () {
  "use strict";

  // ========================
  // 现场配置区
  // ========================
  var ENABLE_AI_REVIEW_CONFIG = true;
  var AI_PLATFORM_BASE_URL = "http://192.168.14.44:5173";
  var AI_SIGN = "xc-fw-1af7cc98-66ed-4d55-a4cc-c6240b1f1c3c";
  var WEAVER_ENV = "prod";

  var mounted = false;
  var tabId = "weaver-ai-review-config-tab";
  var panelId = "weaver-ai-review-config-panel";
  var iframeId = "weaver-ai-review-config-iframe";
  var observer = null;

  function aiLog() {
    if (!window.console || !console.log) return;
    var args = Array.prototype.slice.call(arguments);
    args.unshift("[泛微流程AI智审配置]");
    console.log.apply(console, args);
  }

  function isWorkflowSettingPage() {
    var href = window.location.href || "";
    var hash = window.location.hash || "";
    return href.indexOf("/wui/engine.html") >= 0 && hash.indexOf("workflowengine/path") >= 0 && !!getWorkflowId();
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
      aiLog("读取 workflowId 失败", error);
      return "";
    }
  }

  function getWorkflowName() {
    try {
      var input = document.querySelector("input[value*='请假'], input[type='text']");
      return input && input.value ? input.value : "";
    } catch (error) {
      return "";
    }
  }

  function buildIframeUrl() {
    return (
      AI_PLATFORM_BASE_URL.replace(/\/$/, "") +
      "/ai/weaver/assistant/review-config?ai_sign=" +
      encodeURIComponent(AI_SIGN) +
      "&env=" +
      encodeURIComponent(WEAVER_ENV) +
      "&workflow_id=" +
      encodeURIComponent(getWorkflowId()) +
      "&workflow_name=" +
      encodeURIComponent(getWorkflowName())
    );
  }

  function findPrimaryTabBar() {
    var candidates = Array.prototype.slice.call(document.querySelectorAll("div, ul"));
    return candidates.find(function (node) {
      var text = (node.innerText || "").replace(/\s+/g, "");
      return text.indexOf("基础设置") >= 0 && text.indexOf("高级设置") >= 0 && node.querySelectorAll("span,div,li,a").length >= 4;
    });
  }

  function findAdvancedTab(tabBar) {
    if (!tabBar) return null;
    var nodes = Array.prototype.slice.call(tabBar.querySelectorAll("div,span,li,a,button"));
    for (var i = 0; i < nodes.length; i += 1) {
      var text = (nodes[i].textContent || "").replace(/\s+/g, "");
      if (text !== "高级设置") continue;
      var current = nodes[i];
      while (current.parentElement && current.parentElement !== tabBar) {
        current = current.parentElement;
      }
      return current;
    }
    return null;
  }

  function findContentHost(tabBar) {
    var current = tabBar;
    for (var i = 0; i < 5 && current; i += 1) {
      if (current.parentElement && current.parentElement.clientHeight > 220) return current.parentElement;
      current = current.parentElement;
    }
    return document.body;
  }

  function deactivateSiblings(tab) {
    var parent = tab.parentElement;
    if (!parent) return;
    Array.prototype.slice.call(parent.children).forEach(function (child) {
      child.style.color = "";
      child.style.borderBottom = "";
      child.style.background = "";
    });
  }

  function showPanel() {
    var panel = document.getElementById(panelId);
    var iframe = document.getElementById(iframeId);
    var tab = document.getElementById(tabId);
    if (!panel || !iframe || !tab) return;
    deactivateSiblings(tab);
    tab.style.color = "#0f766e";
    tab.style.borderBottom = "2px solid #0f766e";
    panel.style.display = "block";
    iframe.src = buildIframeUrl();
  }

  function hidePanel() {
    var panel = document.getElementById(panelId);
    var tab = document.getElementById(tabId);
    if (panel) panel.style.display = "none";
    if (tab) {
      tab.style.color = "#334155";
      tab.style.borderBottom = "2px solid transparent";
    }
  }

  function bindNativeTabClose(tabBar) {
    if (!tabBar || tabBar.getAttribute("data-ai-review-close-bound") === "1") return;
    tabBar.setAttribute("data-ai-review-close-bound", "1");
    tabBar.addEventListener("click", function (event) {
      var target = event.target;
      if (target && target.closest && target.closest("#" + tabId)) return;
      hidePanel();
    }, true);
  }

  function mount() {
    if (!ENABLE_AI_REVIEW_CONFIG || mounted || !isWorkflowSettingPage()) return;
    var tabBar = findPrimaryTabBar();
    if (!tabBar) {
      aiLog("未找到流程设置一级页签，稍后重试");
      window.setTimeout(mount, 800);
      return;
    }
    var advancedTab = findAdvancedTab(tabBar);
    mounted = true;
    aiLog("开始挂载 AI 智审规则页签", { workflowId: getWorkflowId() });

    var tab = document.createElement("div");
    tab.id = tabId;
    tab.innerText = "AI智审规则";
    tab.style.cssText = [
      "display:inline-flex",
      "align-items:center",
      "height:40px",
      "padding:0 18px",
      "cursor:pointer",
      "font-size:14px",
      "color:#334155",
      "border-bottom:2px solid transparent",
    ].join(";");
    tab.onclick = showPanel;
    if (advancedTab && advancedTab.parentElement) {
      var insertAnchor = document.getElementById("weaver-ai-workflow-rule-tab") || advancedTab;
      insertAnchor.parentElement.insertBefore(tab, insertAnchor.nextSibling);
    } else {
      tabBar.appendChild(tab);
    }

    var host = findContentHost(tabBar);
    var panel = document.createElement("div");
    panel.id = panelId;
    panel.style.cssText = [
      "display:none",
      "position:absolute",
      "left:0",
      "right:0",
      "top:44px",
      "bottom:0",
      "z-index:20",
      "background:#fff",
    ].join(";");
    if (window.getComputedStyle(host).position === "static") {
      host.style.position = "relative";
    }

    var iframe = document.createElement("iframe");
    iframe.id = iframeId;
    iframe.title = "流程AI智审规则";
    iframe.style.cssText = "width:100%;height:100%;border:0;background:#fff;";
    panel.appendChild(iframe);
    host.appendChild(panel);
    bindNativeTabClose(tabBar);
  }

  function unmountIfNeeded() {
    if (isWorkflowSettingPage()) return;
    var tab = document.getElementById(tabId);
    var panel = document.getElementById(panelId);
    if (tab && tab.parentNode) tab.parentNode.removeChild(tab);
    if (panel && panel.parentNode) panel.parentNode.removeChild(panel);
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

  function startObserver() {
    if (observer || !document.body) return;
    observer = new MutationObserver(function () {
      if (mounted && (!document.getElementById(tabId) || !document.getElementById(panelId))) {
        mounted = false;
      }
      if (!mounted && isWorkflowSettingPage()) {
        window.setTimeout(mount, 100);
      }
    });
    observer.observe(document.body, { childList: true, subtree: true });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      startObserver();
      mount();
    });
  } else {
    startObserver();
    mount();
  }

  window.setTimeout(mount, 500);
  window.setTimeout(mount, 1500);
  window.setTimeout(mount, 3000);
  window.setTimeout(mount, 6000);
})();
