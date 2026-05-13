" RFC 函数模块：ZFM_AI_READ_TABLE_SAFE
" 短文本：AI 只读分页读取表数据
" 用途：按字段清单、结构化条件和最大行数读取少量样例数据，返回紧凑 JSON。
" Importing:
"   IV_TABLE_NAME TYPE TABNAME
"   IV_MAX_ROWS   TYPE I
" Tables:
"   IT_FIELDS     STRUCTURE ZSAI_FIELD_NAME
"   IT_RANGES     STRUCTURE ZSAI_RANGE
"   ET_JSON_LINES STRUCTURE ZSAI_JSON_LINE
"
" 说明：不做固定表名范围限制；只做只读、字段校验、行数控制和紧凑返回。

DATA: lv_max         TYPE i,
      lv_json        TYPE string,
      lv_value       TYPE string,
      lv_high        TYPE string,
      lv_condition   TYPE string,
      lv_first       TYPE abap_bool,
      lv_inner_first TYPE abap_bool,
      lt_options     TYPE STANDARD TABLE OF rfc_db_opt,
      ls_option      TYPE rfc_db_opt,
      lt_rfc_fields  TYPE STANDARD TABLE OF rfc_db_fld,
      ls_rfc_field   TYPE rfc_db_fld,
      lt_data        TYPE STANDARD TABLE OF tab512,
      ls_data        TYPE tab512,
      lt_values      TYPE STANDARD TABLE OF string,
      ls_json_line   TYPE zsai_json_line,
      ls_field_name  TYPE zsai_field_name,
      ls_range       TYPE zsai_range.

REFRESH et_json_lines.

IF iv_table_name IS INITIAL.
  ls_json_line-line = |\{"success":false,"message":"表名不能为空"\}|.
  APPEND ls_json_line TO et_json_lines.
  RETURN.
ENDIF.

lv_max = iv_max_rows.
IF lv_max IS INITIAL.
  lv_max = 80.
ENDIF.
IF lv_max > 200.
  lv_max = 200.
ENDIF.

LOOP AT it_fields INTO ls_field_name.
  IF ls_field_name-fieldname IS NOT INITIAL.
    CLEAR ls_rfc_field.
    SELECT SINGLE fieldname FROM dd03l INTO ls_rfc_field-fieldname
      WHERE tabname = iv_table_name
        AND fieldname = ls_field_name-fieldname
        AND as4local = 'A'.
    IF sy-subrc = 0.
      APPEND ls_rfc_field TO lt_rfc_fields.
    ENDIF.
  ENDIF.
ENDLOOP.

LOOP AT it_ranges INTO ls_range.
  IF ls_range-fieldname IS INITIAL OR ls_range-low IS INITIAL.
    CONTINUE.
  ENDIF.

  SELECT SINGLE fieldname FROM dd03l INTO ls_range-fieldname
    WHERE tabname = iv_table_name
      AND fieldname = ls_range-fieldname
      AND as4local = 'A'.
  IF sy-subrc <> 0.
    CONTINUE.
  ENDIF.

  lv_value = ls_range-low.
  REPLACE ALL OCCURRENCES OF '''' IN lv_value WITH ''''''.

  IF ls_range-option = 'BT' AND ls_range-high IS NOT INITIAL.
    lv_high = ls_range-high.
    REPLACE ALL OCCURRENCES OF '''' IN lv_high WITH ''''''.
    lv_condition = |{ ls_range-fieldname } BETWEEN '{ lv_value }' AND '{ lv_high }'|.
  ELSEIF ls_range-option = 'CP'.
    lv_condition = |{ ls_range-fieldname } LIKE '{ lv_value }'|.
  ELSEIF ls_range-option = 'NE'.
    lv_condition = |{ ls_range-fieldname } <> '{ lv_value }'|.
  ELSEIF ls_range-option = 'GE'.
    lv_condition = |{ ls_range-fieldname } >= '{ lv_value }'|.
  ELSEIF ls_range-option = 'GT'.
    lv_condition = |{ ls_range-fieldname } > '{ lv_value }'|.
  ELSEIF ls_range-option = 'LE'.
    lv_condition = |{ ls_range-fieldname } <= '{ lv_value }'|.
  ELSEIF ls_range-option = 'LT'.
    lv_condition = |{ ls_range-fieldname } < '{ lv_value }'|.
  ELSE.
    lv_condition = |{ ls_range-fieldname } = '{ lv_value }'|.
  ENDIF.

  IF ls_range-sign = 'E'.
    lv_condition = |NOT ( { lv_condition } )|.
  ENDIF.

  IF lt_options IS INITIAL.
    ls_option-text = lv_condition.
  ELSE.
    ls_option-text = |AND { lv_condition }|.
  ENDIF.
  APPEND ls_option TO lt_options.
ENDLOOP.

CALL FUNCTION 'RFC_READ_TABLE'
  EXPORTING
    query_table = iv_table_name
    delimiter   = '|'
    rowcount    = lv_max
  TABLES
    options     = lt_options
    fields      = lt_rfc_fields
    data        = lt_data
  EXCEPTIONS
    table_not_available  = 1
    table_without_data   = 2
    option_not_valid     = 3
    field_not_valid      = 4
    not_authorized       = 5
    data_buffer_exceeded = 6
    OTHERS               = 7.

IF sy-subrc <> 0.
  lv_json = |\{"success":false,"table":"{ iv_table_name }","message":"RFC_READ_TABLE 读取失败","subrc":{ sy-subrc }\}|.
ELSE.
  lv_json = |\{"success":true,"table":"{ iv_table_name }","maxRows":{ lv_max },"rowCount":{ lines( lt_data ) },"fields":[|.
  lv_first = abap_true.
  LOOP AT lt_rfc_fields INTO ls_rfc_field.
    IF lv_first = abap_true.
      lv_first = abap_false.
    ELSE.
      lv_json = lv_json && ','.
    ENDIF.
    lv_value = ls_rfc_field-fieldname.
    REPLACE ALL OCCURRENCES OF '\' IN lv_value WITH '\\'.
    REPLACE ALL OCCURRENCES OF '"' IN lv_value WITH '\"'.
    lv_json = lv_json && '"' && lv_value && '"'.
  ENDLOOP.

  lv_json = lv_json && '],"rows":['.
  lv_first = abap_true.
  LOOP AT lt_data INTO ls_data.
    IF lv_first = abap_true.
      lv_first = abap_false.
    ELSE.
      lv_json = lv_json && ','.
    ENDIF.

    REFRESH lt_values.
    SPLIT ls_data-wa AT '|' INTO TABLE lt_values.
    lv_json = lv_json && '['.
    lv_inner_first = abap_true.
    LOOP AT lt_values INTO lv_value.
      CONDENSE lv_value.
      REPLACE ALL OCCURRENCES OF '\' IN lv_value WITH '\\'.
      REPLACE ALL OCCURRENCES OF '"' IN lv_value WITH '\"'.
      IF lv_inner_first = abap_true.
        lv_inner_first = abap_false.
      ELSE.
        lv_json = lv_json && ','.
      ENDIF.
      lv_json = lv_json && '"' && lv_value && '"'.
    ENDLOOP.
    lv_json = lv_json && ']'.
  ENDLOOP.
  lv_json = lv_json && ']}'.
ENDIF.

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
