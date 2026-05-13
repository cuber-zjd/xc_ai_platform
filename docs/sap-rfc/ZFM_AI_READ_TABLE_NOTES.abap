" 短文本：AI 只读取数审计与返回量建议
" 用途：说明只读 RFC 取数建议维护的审计表和返回量控制字段，供 SE11 建表或维护视图参考。
"
" 建议透明表：ZAI_RFC_AUDIT
"
" 字段建议：
" MANDT       CLNT
" LOG_ID      CHAR32
" UNAME       SYUNAME
" DATUM       SYDATUM
" UZEIT       SYUZEIT
" FUNCTION    FUNCNAME
" OBJECT_NAME CHAR80
" ROW_COUNT   INT4
" STATUS      CHAR1
" MESSAGE     CHAR255
"
" 可选配置表：ZAI_READ_LIMIT
"
" 字段建议：
" MANDT       CLNT   客户端
" TABLE_NAME  TABNAME 表名，填 * 表示默认规则
" MAX_ROWS    INT4   单次建议最大行数
" ENV         CHAR10 环境，例如 DEV/QAS/PRD
" COMMENT     CHAR80 说明
"
" 建议：
" 1. 不按 Z/Y 或固定名单限制读取对象，但所有函数保持只读。
" 2. 单次查询限制行数和超时，默认小批量返回；需要更多数据时让 AI 带条件或分页再次调用。
" 3. 返回给 AI 的 JSON 尽量使用字段数组 + 行数组，避免每行重复字段名。
" 4. 敏感字段如需脱敏，可在 RFC 内部按企业现有权限体系处理。
" 5. 审计表定期归档，不允许 AI 删除审计记录。
