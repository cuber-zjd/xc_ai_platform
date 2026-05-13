" RFC 函数模块：ZFM_AI_QUERY_ZILOG
" 短文本：AI 查询 ZILOG 函数日志
" 用途：按对象名、关键字和最大行数查询自定义 ZILOG 日志，供 AI 排查函数或事务报错。
" Importing:
"   IV_OBJECT_NAME TYPE CHAR80
"   IV_KEYWORD     TYPE CHAR80
"   IV_MAX_ROWS    TYPE I
" Tables:
"   ET_JSON_LINES  STRUCTURE ZSAI_JSON_LINE
"
" 注意：请把下方 ZILOG_DEMO_TABLE 和字段替换成你们真实日志表。

DATA: lv_max  TYPE i,
      lv_json TYPE string,
      ls_json_line TYPE zsai_json_line.

REFRESH et_json_lines.

lv_max = iv_max_rows.
IF lv_max IS INITIAL.
  lv_max = 60.
ENDIF.
IF lv_max > 120.
  lv_max = 120.
ENDIF.

" 示例返回，现场替换为真实 SELECT。
lv_json = |\{"success":true,"message":"请在 SAP 中替换为真实 ZILOG 查询","object":"{ iv_object_name }","maxRows":{ lv_max },"rows":[|.
lv_json = lv_json && |\{"time":"{ sy-datum } { sy-uzeit }","level":"I","message":"ZILOG 示例记录，关键字：{ iv_keyword }"\}|.
lv_json = lv_json && ']}'.

WHILE lv_json IS NOT INITIAL.
  IF strlen( lv_json ) > 255.
    ls_json_line-line = lv_json(255).
    APPEND ls_json_line TO et_json_lines.
    SHIFT lv_json LEFT BY 255 PLACES.
  ELSE.
    ls_json_line-line = lv_json.
    APPEND ls_json_line TO et_json_lines.
    CLEAR lv_json.
  ENDIF.
ENDWHILE.
