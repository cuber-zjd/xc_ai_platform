" RFC 函数模块：ZFM_AI_PING
" 短文本：AI 平台 SAP RFC 连接测试
" 用途：返回当前系统、客户端、用户和时间，用于验证 AI 平台到 SAP 的 RFC 连通性。
" Tables:
"   ET_JSON_LINES STRUCTURE ZSAI_JSON_LINE

DATA: lv_json TYPE c LENGTH 255,
      ls_line TYPE zsai_json_line.

REFRESH et_json_lines.

lv_json = |\{"pong":true,"sysid":"{ sy-sysid }","client":"{ sy-mandt }","user":"{ sy-uname }","date":"{ sy-datum }","time":"{ sy-uzeit }"\}|.
ls_line-line = lv_json.
APPEND ls_line TO et_json_lines.
