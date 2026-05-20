" RFC 函数模块：ZFM_AI_GET_DDIC_META
" 短文本：AI 查询 DDIC 表和结构元数据
" 用途：读取表、结构字段、数据元素、类型、长度和字段文本，供 AI 理解数据结构。
" Importing:
"   IV_OBJECT_NAME TYPE TABNAME
"   IV_OBJECT_TYPE TYPE CHAR10
" Tables:
"   ET_JSON_LINES  STRUCTURE ZSAI_JSON_LINE

DATA: lt_dfies TYPE STANDARD TABLE OF dfies,
      ls_dfies TYPE dfies,
      lv_json  TYPE string,
      lv_fieldtext TYPE string,
      lv_rollname TYPE string,
      ls_json_line TYPE zsai_json_line.

FORM escape_json CHANGING cv_text TYPE string.
  REPLACE ALL OCCURRENCES OF '\' IN cv_text WITH '\\'.
  REPLACE ALL OCCURRENCES OF '"' IN cv_text WITH '\"'.
  REPLACE ALL OCCURRENCES OF cl_abap_char_utilities=>cr_lf IN cv_text WITH '\n'.
  REPLACE ALL OCCURRENCES OF cl_abap_char_utilities=>newline IN cv_text WITH '\n'.
  REPLACE ALL OCCURRENCES OF cl_abap_char_utilities=>horizontal_tab IN cv_text WITH '\t'.
ENDFORM.

REFRESH et_json_lines.

IF iv_object_name IS INITIAL.
  ls_json_line-line = |\{"success":false,"message":"DDIC 对象名不能为空"\}|.
  APPEND ls_json_line TO et_json_lines.
  RETURN.
ENDIF.

CALL FUNCTION 'DDIF_FIELDINFO_GET'
  EXPORTING
    tabname        = iv_object_name
    langu          = sy-langu
  TABLES
    dfies_tab      = lt_dfies
  EXCEPTIONS
    not_found      = 1
    internal_error = 2
    OTHERS         = 3.

IF sy-subrc <> 0.
  ls_json_line-line = |\{"success":false,"message":"未找到 DDIC 对象","object":"{ iv_object_name }"\}|.
  APPEND ls_json_line TO et_json_lines.
  RETURN.
ENDIF.

lv_json = |\{"success":true,"object":"{ iv_object_name }","fields":[|.
LOOP AT lt_dfies INTO ls_dfies.
  IF sy-tabix > 1.
    lv_json = lv_json && ','.
  ENDIF.
  lv_rollname = ls_dfies-rollname.
  lv_fieldtext = ls_dfies-fieldtext.
  PERFORM escape_json CHANGING lv_rollname.
  PERFORM escape_json CHANGING lv_fieldtext.
  lv_json = lv_json &&
    |\{"fieldname":"{ ls_dfies-fieldname }","rollname":"{ lv_rollname }","datatype":"{ ls_dfies-datatype }","leng":{ ls_dfies-leng },"decimals":{ ls_dfies-decimals },"ddtext":"{ lv_fieldtext }"\}|.
ENDLOOP.
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
