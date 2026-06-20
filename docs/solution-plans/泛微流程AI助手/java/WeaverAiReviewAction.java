package com.ai.weaver.action;

import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.Map;

import weaver.interfaces.workflow.action.Action;
import weaver.soa.workflow.request.Property;
import weaver.soa.workflow.request.RequestInfo;

/**
 * 泛微流程 AI 智审通用 Action。
 *
 * 推荐挂载位置：
 * - 节点后附加操作：上一审批人提交后生成下一节点预审建议。
 * - 节点前附加操作：进入当前节点前预先生成风险提示。
 *
 * Action 参数示例：
 * - platformBaseUrl = http://192.168.14.79:8000
 * - aiSign = 与平台 EXTERNAL_API_KEYS 一致的密钥
 * - env = test
 * - connectTimeoutMillis = 5000
 * - readTimeoutMillis = 30000
 * - blockOnRiskLevel = 空/blocked/high，默认不阻断流程
 *
 * 注意：
 * - 初版建议只生成智审记录，不直接替审。
 * - 如启用 blockOnRiskLevel，请先在测试环境验证返回结构和流程体验。
 */
public class WeaverAiReviewAction implements Action {
    private String platformBaseUrl = "http://localhost:8000";
    private String aiSign = "";
    private String env = "default";
    private int connectTimeoutMillis = 5000;
    private int readTimeoutMillis = 30000;
    private String blockOnRiskLevel = "";

    public void setPlatformBaseUrl(String platformBaseUrl) {
        this.platformBaseUrl = trim(platformBaseUrl);
    }

    public void setAiSign(String aiSign) {
        this.aiSign = trim(aiSign);
    }

    public void setEnv(String env) {
        this.env = trim(env);
    }

    public void setConnectTimeoutMillis(String connectTimeoutMillis) {
        this.connectTimeoutMillis = parseInt(connectTimeoutMillis, 5000);
    }

    public void setReadTimeoutMillis(String readTimeoutMillis) {
        this.readTimeoutMillis = parseInt(readTimeoutMillis, 30000);
    }

    public void setBlockOnRiskLevel(String blockOnRiskLevel) {
        this.blockOnRiskLevel = trim(blockOnRiskLevel);
    }

    @Override
    public String execute(RequestInfo requestInfo) {
        try {
            String payload = buildPayload(requestInfo);
            String response = postJson(apiUrl(), payload);
            if (shouldBlock(response)) {
                requestInfo.getRequestManager().setMessagecontent("AI 智审发现高风险，请先处理风险项后再提交。");
                return Action.FAILURE;
            }
            return Action.SUCCESS;
        } catch (Exception error) {
            // 初版默认不因 AI 智审失败阻断业务流程，避免影响生产审批。
            writeLog("泛微流程 AI 智审 Action 调用失败: " + error.getMessage(), error);
            return Action.SUCCESS;
        }
    }

    private String apiUrl() {
        String base = platformBaseUrl == null ? "" : platformBaseUrl.trim();
        while (base.endsWith("/")) {
            base = base.substring(0, base.length() - 1);
        }
        if (base.endsWith("/api/v1")) {
            return base + "/weaver/ai-assistant/review/precheck";
        }
        return base + "/api/v1/weaver/ai-assistant/review/precheck";
    }

    private String buildPayload(RequestInfo requestInfo) {
        Map<String, Object> baseInfo = new LinkedHashMap<String, Object>();
        baseInfo.put("requestid", requestInfo.getRequestid());
        baseInfo.put("workflowid", requestInfo.getWorkflowid());
        baseInfo.put("nodeid", requestInfo.getRequestManager() == null ? "" : requestInfo.getRequestManager().getNodeid());
        baseInfo.put("requestname", requestInfo.getRequestManager() == null ? "" : requestInfo.getRequestManager().getRequestname());

        Map<String, Object> fields = new LinkedHashMap<String, Object>();
        Property[] properties = requestInfo.getMainTableInfo() == null ? null : requestInfo.getMainTableInfo().getProperty();
        if (properties != null) {
            for (Property property : properties) {
                if (property == null || property.getName() == null) continue;
                String fieldName = property.getName();
                String value = property.getValue();
                Map<String, Object> field = new LinkedHashMap<String, Object>();
                field.put("label", fieldName);
                field.put("fieldId", fieldName);
                field.put("type", "text");
                field.put("writable", false);
                field.put("visible", true);
                field.put("value", value);
                field.put("displayValue", value);
                fields.put(fieldName, field);
            }
        }

        Map<String, Object> context = new LinkedHashMap<String, Object>();
        context.put("env", env);
        context.put("baseInfo", baseInfo);
        context.put("url", "");
        context.put("fields", fields);

        Map<String, Object> submitter = new LinkedHashMap<String, Object>();
        submitter.put("userId", requestInfo.getRequestManager() == null ? "" : requestInfo.getRequestManager().getCreater());
        submitter.put("userName", "");

        Map<String, Object> payload = new LinkedHashMap<String, Object>();
        payload.put("context", context);
        payload.put("triggerType", "action");
        payload.put("operation", "workflow_action_pre_review");
        payload.put("currentNodeId", baseInfo.get("nodeid"));
        payload.put("currentNodeName", "");
        payload.put("submitter", submitter);
        payload.put("reviewer", null);
        payload.put("comment", null);
        payload.put("extra", new LinkedHashMap<String, Object>());
        return toJson(payload);
    }

    private String postJson(String url, String payload) throws Exception {
        HttpURLConnection connection = null;
        try {
            connection = (HttpURLConnection) new URL(url).openConnection();
            connection.setRequestMethod("POST");
            connection.setConnectTimeout(connectTimeoutMillis);
            connection.setReadTimeout(readTimeoutMillis);
            connection.setDoOutput(true);
            connection.setRequestProperty("Content-Type", "application/json;charset=UTF-8");
            connection.setRequestProperty("ai-sign", aiSign);
            byte[] bytes = payload.getBytes(StandardCharsets.UTF_8);
            connection.setRequestProperty("Content-Length", String.valueOf(bytes.length));
            OutputStream outputStream = connection.getOutputStream();
            outputStream.write(bytes);
            outputStream.flush();
            outputStream.close();

            int status = connection.getResponseCode();
            InputStream inputStream = status >= 200 && status < 300 ? connection.getInputStream() : connection.getErrorStream();
            String response = readAll(inputStream);
            if (status < 200 || status >= 300) {
                throw new RuntimeException("HTTP " + status + ": " + response);
            }
            return response;
        } finally {
            if (connection != null) {
                connection.disconnect();
            }
        }
    }

    private boolean shouldBlock(String response) {
        if (blockOnRiskLevel == null || blockOnRiskLevel.trim().length() == 0) return false;
        String normalized = blockOnRiskLevel.trim().toLowerCase();
        if (normalized.indexOf("blocked") >= 0 && response.indexOf("\"riskLevel\":\"blocked\"") >= 0) return true;
        return normalized.indexOf("high") >= 0 && response.indexOf("\"riskLevel\":\"high\"") >= 0;
    }

    private String readAll(InputStream inputStream) throws Exception {
        if (inputStream == null) return "";
        BufferedReader reader = new BufferedReader(new InputStreamReader(inputStream, StandardCharsets.UTF_8));
        StringBuilder builder = new StringBuilder();
        String line;
        while ((line = reader.readLine()) != null) {
            builder.append(line);
        }
        reader.close();
        return builder.toString();
    }

    private String toJson(Object value) {
        if (value == null) return "null";
        if (value instanceof Map) {
            StringBuilder builder = new StringBuilder();
            builder.append("{");
            boolean first = true;
            for (Object entryObject : ((Map<?, ?>) value).entrySet()) {
                Map.Entry<?, ?> entry = (Map.Entry<?, ?>) entryObject;
                if (!first) builder.append(",");
                first = false;
                builder.append(quote(String.valueOf(entry.getKey()))).append(":").append(toJson(entry.getValue()));
            }
            builder.append("}");
            return builder.toString();
        }
        if (value instanceof Iterable) {
            StringBuilder builder = new StringBuilder();
            builder.append("[");
            boolean first = true;
            for (Object item : (Iterable<?>) value) {
                if (!first) builder.append(",");
                first = false;
                builder.append(toJson(item));
            }
            builder.append("]");
            return builder.toString();
        }
        if (value instanceof Number || value instanceof Boolean) {
            return String.valueOf(value);
        }
        return quote(String.valueOf(value));
    }

    private String quote(String value) {
        StringBuilder builder = new StringBuilder();
        builder.append("\"");
        for (int i = 0; i < value.length(); i += 1) {
            char ch = value.charAt(i);
            if (ch == '\\' || ch == '"') {
                builder.append('\\').append(ch);
            } else if (ch == '\n') {
                builder.append("\\n");
            } else if (ch == '\r') {
                builder.append("\\r");
            } else if (ch == '\t') {
                builder.append("\\t");
            } else {
                builder.append(ch);
            }
        }
        builder.append("\"");
        return builder.toString();
    }

    private String trim(String value) {
        return value == null ? "" : value.trim();
    }

    private int parseInt(String value, int defaultValue) {
        try {
            return Integer.parseInt(trim(value));
        } catch (Exception error) {
            return defaultValue;
        }
    }

    private void writeLog(String message, Exception error) {
        try {
            new weaver.general.BaseBean().writeLog(message);
        } catch (Exception ignored) {
            // ignore
        }
    }
}
