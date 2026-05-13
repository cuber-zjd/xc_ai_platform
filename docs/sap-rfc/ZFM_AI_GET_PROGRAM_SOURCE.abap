" RFC 函数模块：ZFM_AI_GET_PROGRAM_SOURCE
" 短文本：AI 读取程序或函数完整源码
" 用途：一次读取 Report、Include 或函数模块完整源码，平台侧再分段投喂给 AI。
" Importing:
"   IV_OBJECT_NAME TYPE PROGNAME
"   IV_OBJECT_TYPE TYPE CHAR10
"   IV_START_LINE  TYPE I
"   IV_MAX_LINES   TYPE I
" Tables:
"   ET_JSON_LINES  STRUCTURE ZSAI_JSON_LINE

DATA: lt_source TYPE STANDARD TABLE OF string,
      lv_line   TYPE string,
      lv_json   TYPE string,
      lv_name   TYPE progname,
      lv_include TYPE progname,
      lv_funcname TYPE rs38l-name,
      lv_func_include TYPE rs38l-include,
      lv_group   TYPE rs38l-area,
      lv_start  TYPE i,
      lv_max    TYPE i,
      lv_end    TYPE i,
      lv_line_no TYPE i,
      lv_returned TYPE i,
      lv_first   TYPE abap_bool,
      ls_json_line TYPE zsai_json_line.

REFRESH et_json_lines.

IF iv_object_name IS INITIAL.
  ls_json_line-line = |\{"success":false,"message":"对象名不能为空"\}|.
  APPEND ls_json_line TO et_json_lines.
  RETURN.
ENDIF.

lv_name = iv_object_name.

lv_start = iv_start_line.
IF lv_start IS INITIAL OR lv_start < 1.
  lv_start = 1.
ENDIF.

lv_max = iv_max_lines.
IF lv_max IS INITIAL.
  lv_max = 0.
ENDIF.

IF iv_object_type = 'FUNC'.
  CLEAR lv_include.
  CLEAR lv_func_include.
  CLEAR lv_group.
  lv_funcname = iv_object_name.

  CALL FUNCTION 'FUNCTION_INCLUDE_INFO'
    CHANGING
      funcname = lv_funcname
      group    = lv_group
      include  = lv_func_include
    EXCEPTIONS
      function_not_exists = 1
      include_not_exists  = 2
      group_not_exists    = 3
      no_selections       = 4
      no_function_include = 5
      OTHERS              = 6.

  IF sy-subrc = 0 AND lv_func_include IS NOT INITIAL.
    lv_name = lv_func_include.
  ELSE.
    SELECT SINGLE pname FROM tfdir INTO lv_include WHERE funcname = iv_object_name.
    IF sy-subrc = 0 AND lv_include IS NOT INITIAL.
      lv_name = lv_include.
    ENDIF.
  ENDIF.
ENDIF.

READ REPORT lv_name INTO lt_source.
IF sy-subrc <> 0.
  ls_json_line-line = |\{"success":false,"message":"读取源码失败","object":"{ iv_object_name }"\}|.
  APPEND ls_json_line TO et_json_lines.
  RETURN.
ENDIF.

IF lv_max > 0.
  lv_end = lv_start + lv_max - 1.
ELSE.
  lv_end = lines( lt_source ).
ENDIF.
lv_returned = lv_end - lv_start + 1.
IF lv_returned < 0.
  lv_returned = 0.
ENDIF.

lv_json = |\{"success":true,"object":"{ iv_object_name }","resolvedProgram":"{ lv_name }","startLine":{ lv_start },"maxLines":{ lv_max },"totalLines":{ lines( lt_source ) },"returnedLines":{ lv_returned },"lines":[|.
lv_first = abap_true.
LOOP AT lt_source INTO lv_line.
  lv_line_no = sy-tabix.
  IF lv_line_no < lv_start OR lv_line_no > lv_end.
    CONTINUE.
  ENDIF.
  REPLACE ALL OCCURRENCES OF '\' IN lv_line WITH '\\'.
  REPLACE ALL OCCURRENCES OF '"' IN lv_line WITH '\"'.
  IF lv_first = abap_true.
    lv_first = abap_false.
  ELSE.
    lv_json = lv_json && ','.
  ENDIF.
  lv_json = lv_json && '"' && lv_line && '"'.
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
