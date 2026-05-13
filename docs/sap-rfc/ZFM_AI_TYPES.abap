" 公共类型建议。SE37 函数接口不能引用 TOP include 本地 TYPES。
" 短文本：AI RFC 公共类型定义
" 用途：说明需要先在 SE11 创建的全局结构，并保留函数内部可用的本地辅助类型。
"
" 必须先在 SE11 创建以下全局结构：
" 1. ZSAI_JSON_LINE
"    - LINE TYPE CHAR255
" 2. ZSAI_RANGE
"    - FIELDNAME TYPE FIELDNAME
"    - SIGN      TYPE DDSIGN
"    - OPTION    TYPE DDOPTION
"    - LOW       TYPE CHAR255
"    - HIGH      TYPE CHAR255
" 3. ZSAI_FIELD_NAME
"    - FIELDNAME TYPE FIELDNAME
"
" 然后在 SE37 函数模块接口中使用：
" - ET_JSON_LINES  TYPE ZSAI_JSON_LINE
" - IT_RANGES      TYPE ZSAI_RANGE
" - IT_FIELDS      TYPE ZSAI_FIELD_NAME

TYPES: BEGIN OF zais_field,
         fieldname TYPE fieldname,
         rollname  TYPE rollname,
         datatype  TYPE datatype_d,
         leng      TYPE ddleng,
         decimals  TYPE decimals,
         ddtext    TYPE ddtext,
       END OF zais_field.
TYPES zait_fields TYPE STANDARD TABLE OF zais_field WITH DEFAULT KEY.

TYPES: BEGIN OF zais_range,
         fieldname TYPE fieldname,
         sign      TYPE ddsign,
         option    TYPE ddoption,
         low       TYPE c LENGTH 255,
         high      TYPE c LENGTH 255,
       END OF zais_range.
TYPES zait_ranges TYPE STANDARD TABLE OF zais_range WITH DEFAULT KEY.

TYPES: BEGIN OF zais_return,
         success TYPE abap_bool,
         message TYPE c LENGTH 255,
       END OF zais_return.

TYPES: BEGIN OF zais_audit,
         uname     TYPE syuname,
         datum     TYPE sydatum,
         uzeit     TYPE syuzeit,
         function  TYPE funcname,
         object    TYPE c LENGTH 80,
         row_count TYPE i,
         status    TYPE char1,
         message   TYPE c LENGTH 255,
       END OF zais_audit.
