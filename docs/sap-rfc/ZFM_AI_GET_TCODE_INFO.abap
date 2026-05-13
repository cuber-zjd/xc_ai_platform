" RFC 函数模块：ZFM_AI_GET_TCODE_INFO
" 短文本：AI 查询事务码对应程序信息
" 用途：根据事务码精确/模糊匹配，或按事务描述模糊查询 TSTC/TSTCT，供 AI 定位入口代码。
" Importing:
"   IV_TCODE    TYPE TCODE
"   IV_QUERY    TYPE CHAR80
"   IV_MAX_ROWS TYPE I
" Tables:
"   ET_JSON_LINES STRUCTURE ZSAI_JSON_LINE

TYPES: BEGIN OF zais_tcode_hit,
         tcode  TYPE tcode,
         pgmna  TYPE progname,
         dypno  TYPE sy-dynnr,
         ttext  TYPE tstct-ttext,
         source TYPE c LENGTH 10,
       END OF zais_tcode_hit.

DATA: lt_hits      TYPE STANDARD TABLE OF zais_tcode_hit,
      ls_hit       TYPE zais_tcode_hit,
      ls_tstc      TYPE tstc,
      ls_tstct     TYPE tstct,
      lv_query     TYPE c LENGTH 80,
      lv_tcode_query TYPE c LENGTH 80,
      lv_tcode_like TYPE c LENGTH 90,
      lv_text_like TYPE c LENGTH 90,
      lv_max       TYPE i,
      lv_json      TYPE string,
      lv_value     TYPE string,
      lv_first     TYPE abap_bool,
      ls_line      TYPE zsai_json_line.

REFRESH et_json_lines.

lv_query = iv_query.
IF lv_query IS INITIAL.
  lv_query = iv_tcode.
ENDIF.
CONDENSE lv_query.
lv_tcode_query = lv_query.
TRANSLATE lv_tcode_query TO UPPER CASE.

lv_max = iv_max_rows.
IF lv_max IS INITIAL.
  lv_max = 20.
ENDIF.
IF lv_max > 50.
  lv_max = 50.
ENDIF.

IF iv_tcode IS INITIAL AND lv_query IS INITIAL.
  ls_line-line = |\{"success":false,"message":"事务码或查询关键字不能为空"\}|.
  APPEND ls_line TO et_json_lines.
  RETURN.
ENDIF.

IF iv_tcode IS NOT INITIAL.
  SELECT SINGLE * FROM tstc INTO ls_tstc WHERE tcode = iv_tcode.
  IF sy-subrc = 0.
    CLEAR ls_hit.
    ls_hit-tcode = ls_tstc-tcode.
    ls_hit-pgmna = ls_tstc-pgmna.
    ls_hit-dypno = ls_tstc-dypno.
    ls_hit-source = 'exact'.
    SELECT SINGLE ttext FROM tstct INTO ls_hit-ttext
      WHERE sprsl = sy-langu
        AND tcode = ls_tstc-tcode.
    APPEND ls_hit TO lt_hits.
  ENDIF.
ENDIF.

IF lines( lt_hits ) < lv_max AND lv_query IS NOT INITIAL.
  CONCATENATE '%' lv_tcode_query '%' INTO lv_tcode_like.
  SELECT * FROM tstc INTO ls_tstc
    UP TO lv_max ROWS
    WHERE tcode LIKE lv_tcode_like.
    READ TABLE lt_hits WITH KEY tcode = ls_tstc-tcode TRANSPORTING NO FIELDS.
    IF sy-subrc = 0.
      CONTINUE.
    ENDIF.
    CLEAR ls_hit.
    ls_hit-tcode = ls_tstc-tcode.
    ls_hit-pgmna = ls_tstc-pgmna.
    ls_hit-dypno = ls_tstc-dypno.
    ls_hit-source = 'tcode'.
    SELECT SINGLE ttext FROM tstct INTO ls_hit-ttext
      WHERE sprsl = sy-langu
        AND tcode = ls_tstc-tcode.
    APPEND ls_hit TO lt_hits.
    IF lines( lt_hits ) >= lv_max.
      EXIT.
    ENDIF.
  ENDSELECT.
ENDIF.

IF lines( lt_hits ) < lv_max AND lv_query IS NOT INITIAL.
  CONCATENATE '%' lv_query '%' INTO lv_text_like.
  SELECT * FROM tstct INTO ls_tstct
    UP TO lv_max ROWS
    WHERE sprsl = sy-langu
      AND ttext LIKE lv_text_like.
    READ TABLE lt_hits WITH KEY tcode = ls_tstct-tcode TRANSPORTING NO FIELDS.
    IF sy-subrc = 0.
      CONTINUE.
    ENDIF.
    SELECT SINGLE * FROM tstc INTO ls_tstc WHERE tcode = ls_tstct-tcode.
    IF sy-subrc <> 0.
      CONTINUE.
    ENDIF.
    CLEAR ls_hit.
    ls_hit-tcode = ls_tstc-tcode.
    ls_hit-pgmna = ls_tstc-pgmna.
    ls_hit-dypno = ls_tstc-dypno.
    ls_hit-ttext = ls_tstct-ttext.
    ls_hit-source = 'text'.
    APPEND ls_hit TO lt_hits.
    IF lines( lt_hits ) >= lv_max.
      EXIT.
    ENDIF.
  ENDSELECT.
ENDIF.

IF lt_hits IS INITIAL.
  lv_json = |\{"success":false,"message":"未找到事务码","query":"{ lv_query }","items":[]\}|.
ELSE.
  lv_json = |\{"success":true,"query":"{ lv_query }","count":{ lines( lt_hits ) },"items":[|.
  lv_first = abap_true.
  LOOP AT lt_hits INTO ls_hit.
    IF lv_first = abap_true.
      lv_first = abap_false.
    ELSE.
      lv_json = lv_json && ','.
    ENDIF.

    lv_value = ls_hit-ttext.
    REPLACE ALL OCCURRENCES OF '\' IN lv_value WITH '\\'.
    REPLACE ALL OCCURRENCES OF '"' IN lv_value WITH '\"'.

    lv_json = lv_json &&
      |\{"tcode":"{ ls_hit-tcode }","program":"{ ls_hit-pgmna }","screen":"{ ls_hit-dypno }","text":"{ lv_value }","match":"{ ls_hit-source }"\}|.
  ENDLOOP.
  lv_json = lv_json && ']}'.
ENDIF.

WHILE lv_json IS NOT INITIAL.
  IF strlen( lv_json ) > 255.
    ls_line-line = lv_json(255).
    APPEND ls_line TO et_json_lines.
    SHIFT lv_json LEFT BY 255 PLACES.
  ELSE.
    ls_line-line = lv_json.
    APPEND ls_line TO et_json_lines.
    CLEAR lv_json.
  ENDIF.
ENDWHILE.
