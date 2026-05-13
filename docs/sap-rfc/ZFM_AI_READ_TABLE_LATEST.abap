" RFC 函数模块：ZFM_AI_READ_TABLE_LATEST
" 短文本：AI 只读排序读取最新表数据
" 用途：按字段清单、结构化条件和排序字段读取 Top N 记录，适用于“最新/最后一笔/最大凭证号”等问题。
" Importing:
"   IV_TABLE_NAME TYPE TABNAME
"   IV_MAX_ROWS   TYPE I
" Tables:
"   IT_FIELDS      STRUCTURE ZSAI_FIELD_NAME
"   IT_RANGES      STRUCTURE ZSAI_RANGE
"   IT_SORT_FIELDS STRUCTURE ZSAI_SORT_FIELD  " FIELDNAME CHAR30, DIRECTION CHAR4(ASC/DESC)
"   ET_JSON_LINES  STRUCTURE ZSAI_JSON_LINE
"
" 说明：
" 1. 本函数只能 SELECT，不做 DDL/DML。
" 2. 所有字段名必须先在 DD03L 校验存在。
" 3. IV_MAX_ROWS 默认 1，最大 20。
" 4. 物料凭证最新记录建议 MKPF 按 CPUDT DESC、CPUTM DESC 排序；必要时追加 MJAHR DESC、MBLNR DESC。

DATA: lv_max         TYPE i,
      lv_json        TYPE string,
      lv_value       TYPE string,
      lv_high        TYPE string,
      lv_condition   TYPE string,
      lv_where       TYPE string,
      lv_order       TYPE string,
      lv_first       TYPE abap_bool,
      lv_inner_first TYPE abap_bool,
      lt_components  TYPE cl_abap_structdescr=>component_table,
      ls_component   LIKE LINE OF lt_components,
      lr_struct      TYPE REF TO cl_abap_structdescr,
      lr_table       TYPE REF TO cl_abap_tabledescr,
      lr_data        TYPE REF TO data,
      lr_line        TYPE REF TO data,
      lt_values      TYPE STANDARD TABLE OF string,
      ls_json_line   TYPE zsai_json_line,
      ls_field_name  TYPE zsai_field_name,
      ls_range       TYPE zsai_range,
      ls_sort        TYPE zsai_sort_field.

FIELD-SYMBOLS: <lt_data> TYPE STANDARD TABLE,
               <ls_data> TYPE any,
               <lv_field> TYPE any.

REFRESH et_json_lines.

IF iv_table_name IS INITIAL.
  ls_json_line-line = |\{"success":false,"message":"表名不能为空"\}|.
  APPEND ls_json_line TO et_json_lines.
  RETURN.
ENDIF.

lv_max = iv_max_rows.
IF lv_max IS INITIAL.
  lv_max = 1.
ENDIF.
IF lv_max > 20.
  lv_max = 20.
ENDIF.

LOOP AT it_fields INTO ls_field_name.
  IF ls_field_name-fieldname IS INITIAL.
    CONTINUE.
  ENDIF.
  SELECT SINGLE fieldname, rollname FROM dd03l INTO @DATA(ls_dd03l)
    WHERE tabname = @iv_table_name
      AND fieldname = @ls_field_name-fieldname
      AND as4local = 'A'.
  IF sy-subrc <> 0.
    CONTINUE.
  ENDIF.
  CLEAR ls_component.
  ls_component-name = ls_dd03l-fieldname.
  ls_component-type ?= cl_abap_elemdescr=>describe_by_name( ls_dd03l-rollname ).
  APPEND ls_component TO lt_components.
ENDLOOP.

IF lt_components IS INITIAL.
  ls_json_line-line = |\{"success":false,"table":"{ iv_table_name }","message":"字段清单不能为空或字段不存在"\}|.
  APPEND ls_json_line TO et_json_lines.
  RETURN.
ENDIF.

LOOP AT it_ranges INTO ls_range.
  IF ls_range-fieldname IS INITIAL OR ls_range-low IS INITIAL.
    CONTINUE.
  ENDIF.
  SELECT SINGLE fieldname FROM dd03l INTO @DATA(lv_range_field)
    WHERE tabname = @iv_table_name
      AND fieldname = @ls_range-fieldname
      AND as4local = 'A'.
  IF sy-subrc <> 0.
    CONTINUE.
  ENDIF.

  lv_value = ls_range-low.
  REPLACE ALL OCCURRENCES OF '''' IN lv_value WITH ''''''.
  IF ls_range-option = 'BT' AND ls_range-high IS NOT INITIAL.
    lv_high = ls_range-high.
    REPLACE ALL OCCURRENCES OF '''' IN lv_high WITH ''''''.
    lv_condition = |{ lv_range_field } BETWEEN '{ lv_value }' AND '{ lv_high }'|.
  ELSEIF ls_range-option = 'CP'.
    lv_condition = |{ lv_range_field } LIKE '{ lv_value }'|.
  ELSEIF ls_range-option = 'NE'.
    lv_condition = |{ lv_range_field } <> '{ lv_value }'|.
  ELSEIF ls_range-option = 'GE'.
    lv_condition = |{ lv_range_field } >= '{ lv_value }'|.
  ELSEIF ls_range-option = 'GT'.
    lv_condition = |{ lv_range_field } > '{ lv_value }'|.
  ELSEIF ls_range-option = 'LE'.
    lv_condition = |{ lv_range_field } <= '{ lv_value }'|.
  ELSEIF ls_range-option = 'LT'.
    lv_condition = |{ lv_range_field } < '{ lv_value }'|.
  ELSE.
    lv_condition = |{ lv_range_field } = '{ lv_value }'|.
  ENDIF.

  IF ls_range-sign = 'E'.
    lv_condition = |NOT ( { lv_condition } )|.
  ENDIF.
  IF lv_where IS INITIAL.
    lv_where = lv_condition.
  ELSE.
    lv_where = |{ lv_where } AND { lv_condition }|.
  ENDIF.
ENDLOOP.

LOOP AT it_sort_fields INTO ls_sort.
  IF ls_sort-fieldname IS INITIAL.
    CONTINUE.
  ENDIF.
  SELECT SINGLE fieldname FROM dd03l INTO @DATA(lv_sort_field)
    WHERE tabname = @iv_table_name
      AND fieldname = @ls_sort-fieldname
      AND as4local = 'A'.
  IF sy-subrc <> 0.
    CONTINUE.
  ENDIF.
  IF lv_order IS INITIAL.
    lv_order = lv_sort_field.
  ELSE.
    lv_order = |{ lv_order }, { lv_sort_field }|.
  ENDIF.
  IF ls_sort-direction = 'ASC'.
    lv_order = |{ lv_order } ASCENDING|.
  ELSE.
    lv_order = |{ lv_order } DESCENDING|.
  ENDIF.
ENDLOOP.

IF lv_order IS INITIAL.
  ls_json_line-line = |\{"success":false,"table":"{ iv_table_name }","message":"排序字段不能为空，无法确定最新记录"\}|.
  APPEND ls_json_line TO et_json_lines.
  RETURN.
ENDIF.

TRY.
    lr_struct = cl_abap_structdescr=>create( lt_components ).
    lr_table = cl_abap_tabledescr=>create( lr_struct ).
    CREATE DATA lr_data TYPE HANDLE lr_table.
    ASSIGN lr_data->* TO <lt_data>.

    IF lv_where IS INITIAL.
      SELECT (it_fields) FROM (iv_table_name)
        INTO CORRESPONDING FIELDS OF TABLE @<lt_data>
        ORDER BY (lv_order)
        UP TO @lv_max ROWS.
    ELSE.
      SELECT (it_fields) FROM (iv_table_name)
        INTO CORRESPONDING FIELDS OF TABLE @<lt_data>
        WHERE (lv_where)
        ORDER BY (lv_order)
        UP TO @lv_max ROWS.
    ENDIF.
  CATCH cx_root INTO DATA(lx_error).
    lv_value = lx_error->get_text( ).
    REPLACE ALL OCCURRENCES OF '\' IN lv_value WITH '\\'.
    REPLACE ALL OCCURRENCES OF '"' IN lv_value WITH '\"'.
    ls_json_line-line = |\{"success":false,"table":"{ iv_table_name }","message":"排序读取失败：{ lv_value }"\}|.
    APPEND ls_json_line TO et_json_lines.
    RETURN.
ENDTRY.

lv_json = |\{"success":true,"table":"{ iv_table_name }","maxRows":{ lv_max },"orderBy":"{ lv_order }","rowCount":{ lines( <lt_data> ) },"fields":[|.
lv_first = abap_true.
LOOP AT it_fields INTO ls_field_name.
  IF lv_first = abap_true.
    lv_first = abap_false.
  ELSE.
    lv_json = lv_json && ','.
  ENDIF.
  lv_value = ls_field_name-fieldname.
  REPLACE ALL OCCURRENCES OF '\' IN lv_value WITH '\\'.
  REPLACE ALL OCCURRENCES OF '"' IN lv_value WITH '\"'.
  lv_json = lv_json && '"' && lv_value && '"'.
ENDLOOP.

lv_json = lv_json && '],"rows":['.
lv_first = abap_true.
LOOP AT <lt_data> ASSIGNING <ls_data>.
  IF lv_first = abap_true.
    lv_first = abap_false.
  ELSE.
    lv_json = lv_json && ','.
  ENDIF.
  lv_json = lv_json && '['.
  lv_inner_first = abap_true.
  LOOP AT it_fields INTO ls_field_name.
    ASSIGN COMPONENT ls_field_name-fieldname OF STRUCTURE <ls_data> TO <lv_field>.
    IF sy-subrc = 0.
      lv_value = <lv_field>.
    ELSE.
      CLEAR lv_value.
    ENDIF.
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
