import asyncio
import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from app.core.config import settings
from app.core.logger import logger
from app.schemas.fr_ai_report.ai_report import SqlValidationResult
from app.schemas.fr_ai_report.report_dsl import FieldType, ParameterDSL


READONLY_SQL_PATTERN = re.compile(r"^\s*(select|with)\b", re.IGNORECASE | re.DOTALL)
FORBIDDEN_SQL_PATTERN = re.compile(
    r"\b(insert|update|delete|merge|drop|truncate|alter|create|exec|execute|grant|revoke|backup|restore)\b",
    re.IGNORECASE,
)
PARAMETER_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


class SqlServerQueryService:
    @property
    def is_configured(self) -> bool:
        return all(
            [
                settings.FR_AI_SQLSERVER_HOST,
                settings.FR_AI_SQLSERVER_DATABASE,
                settings.FR_AI_SQLSERVER_USER,
                settings.FR_AI_SQLSERVER_PASSWORD,
            ]
        )

    async def validate_select_sql(
        self,
        sql: str,
        parameters: list[ParameterDSL],
    ) -> SqlValidationResult:
        result = SqlValidationResult(
            enabled=settings.FR_AI_SQLSERVER_ENABLED,
            configured=self.is_configured,
        )
        if not settings.FR_AI_SQLSERVER_ENABLED:
            result.warnings.append("未启用 FR_AI_SQLSERVER_ENABLED，已跳过 SQL Server 数据校验")
            return result
        if not self.is_configured:
            result.warnings.append("SQL Server 连接信息不完整，已跳过数据校验")
            return result

        safety_errors = self._validate_readonly_sql(sql)
        if safety_errors:
            result.errors.extend(safety_errors)
            return result

        executable_sql = self._bind_validation_parameters(sql, parameters, result)
        if result.errors:
            return result

        try:
            rows, columns = await asyncio.to_thread(self._execute_sample_query, executable_sql)
        except Exception as exc:
            logger.warning(f"FineReport AI SQL Server 校验失败：{exc}")
            result.errors.append(f"SQL Server 执行失败：{exc}")
            return result

        result.executed = True
        result.success = True
        result.columns = columns
        result.sampleRows = rows
        result.rowCount = len(rows)
        if len(rows) >= settings.FR_AI_SQLSERVER_MAX_ROWS:
            result.warnings.append(f"仅返回前 {settings.FR_AI_SQLSERVER_MAX_ROWS} 行样例用于校验")
        return result

    async def inspect_table_schema(self, table_name: str) -> tuple[dict[str, Any] | None, list[str], list[str]]:
        warnings: list[str] = []
        errors: list[str] = []
        if not settings.FR_AI_SQLSERVER_ENABLED:
            warnings.append("未启用 FR_AI_SQLSERVER_ENABLED，无法根据表名查询 SQL Server 表结构")
            return None, warnings, errors
        if not self.is_configured:
            warnings.append("SQL Server 连接信息不完整，无法根据表名查询表结构")
            return None, warnings, errors

        try:
            schema_name, pure_table_name = self._parse_table_name(table_name)
        except ValueError as exc:
            errors.append(str(exc))
            return None, warnings, errors

        try:
            columns = await asyncio.to_thread(self._query_table_columns, schema_name, pure_table_name)
        except Exception as exc:
            logger.warning(f"FineReport AI 表结构查询失败：{exc}")
            errors.append(f"SQL Server 表结构查询失败：{exc}")
            return None, warnings, errors

        if not columns:
            errors.append(f"未查询到表结构：{table_name}")
            return None, warnings, errors

        matched_schemas = sorted({str(item["TABLE_SCHEMA"]) for item in columns})
        if len(matched_schemas) > 1:
            warnings.append(f"表名 {pure_table_name} 匹配到多个 schema，已使用 {matched_schemas[0]}")
            columns = [item for item in columns if item["TABLE_SCHEMA"] == matched_schemas[0]]

        resolved_schema = str(columns[0]["TABLE_SCHEMA"])
        fields = [
            {
                "name": str(column["COLUMN_NAME"]),
                "label": str(column["COLUMN_NAME"]),
                "type": self._map_sqlserver_type(str(column["DATA_TYPE"])),
                "role": self._infer_role(str(column["COLUMN_NAME"]), str(column["DATA_TYPE"])),
                "nullable": str(column["IS_NULLABLE"]).upper() == "YES",
                "sourceType": str(column["DATA_TYPE"]),
            }
            for column in columns
        ]
        return {
            "tableName": f"{resolved_schema}.{pure_table_name}",
            "dataSourceStatus": "provided",
            "fields": fields,
        }, warnings, errors

    async def inspect_tables_schema(self, table_names: list[str]) -> tuple[dict[str, Any] | None, list[str], list[str]]:
        warnings: list[str] = []
        errors: list[str] = []
        schemas: list[dict[str, Any]] = []
        for table_name in table_names:
            schema, table_warnings, table_errors = await self.inspect_table_schema(table_name)
            warnings.extend(table_warnings)
            errors.extend(table_errors)
            if schema:
                schemas.append(schema)

        if not schemas:
            return None, warnings, errors
        if len(schemas) == 1:
            return schemas[0], warnings, errors

        aliases = self._build_aliases(schemas)
        relation = {
            "tableName": "__join__",
            "dataSourceStatus": "provided",
            "tables": [
                {
                    "tableName": schema["tableName"],
                    "alias": aliases[schema["tableName"]],
                    "fields": schema["fields"],
                }
                for schema in schemas
            ],
            "fields": [
                {
                    **field,
                    "name": f"{aliases[schema['tableName']]}__{field['name']}",
                    "sourceField": field["name"],
                    "sourceTable": schema["tableName"],
                    "tableAlias": aliases[schema["tableName"]],
                }
                for schema in schemas
                for field in schema["fields"]
            ],
            "joinHints": self._infer_join_hints(schemas, aliases),
        }
        if not relation["joinHints"]:
            warnings.append("未识别到明确 JOIN 字段，请在需求中说明表关联关系，例如：订单.customer_id = 客户.id")
        return relation, warnings, errors

    def _build_aliases(self, schemas: list[dict[str, Any]]) -> dict[str, str]:
        aliases: dict[str, str] = {}
        used: set[str] = set()
        for index, schema in enumerate(schemas, start=1):
            base = schema["tableName"].split(".")[-1]
            alias = "".join(char for char in base.lower() if char.isalnum() or char == "_")[:1] or f"t{index}"
            if alias in used:
                alias = f"t{index}"
            aliases[schema["tableName"]] = alias
            used.add(alias)
        return aliases

    def _infer_join_hints(self, schemas: list[dict[str, Any]], aliases: dict[str, str]) -> list[dict[str, str]]:
        hints: list[dict[str, str]] = []
        for left_index, left_schema in enumerate(schemas):
            for right_schema in schemas[left_index + 1:]:
                left_fields = {field["sourceField"] if "sourceField" in field else field["name"]: field for field in left_schema["fields"]}
                right_fields = {field["sourceField"] if "sourceField" in field else field["name"]: field for field in right_schema["fields"]}
                for left_name in left_fields:
                    candidates = [left_name, left_name.removesuffix("_id"), f"{left_schema['tableName'].split('.')[-1]}_id"]
                    for right_name in right_fields:
                        if right_name in candidates or left_name == f"{right_schema['tableName'].split('.')[-1]}_id":
                            hints.append(
                                {
                                    "leftTable": left_schema["tableName"],
                                    "leftAlias": aliases[left_schema["tableName"]],
                                    "leftField": left_name,
                                    "rightTable": right_schema["tableName"],
                                    "rightAlias": aliases[right_schema["tableName"]],
                                    "rightField": right_name,
                                    "expression": (
                                        f"{aliases[left_schema['tableName']]}.{left_name} = "
                                        f"{aliases[right_schema['tableName']]}.{right_name}"
                                    ),
                                }
                            )
                            break
                    if hints and hints[-1]["leftTable"] == left_schema["tableName"] and hints[-1]["rightTable"] == right_schema["tableName"]:
                        break
        return hints

    def _validate_readonly_sql(self, sql: str) -> list[str]:
        errors: list[str] = []
        normalized = sql.strip()
        if not READONLY_SQL_PATTERN.search(normalized):
            errors.append("SQL 校验只允许 SELECT 或 WITH 查询")
        if FORBIDDEN_SQL_PATTERN.search(normalized):
            errors.append("SQL 包含写入、DDL、执行过程或权限相关关键字，已拒绝执行")
        without_trailing = normalized[:-1] if normalized.endswith(";") else normalized
        if ";" in without_trailing:
            errors.append("SQL 校验不允许多语句执行")
        return errors

    def _parse_table_name(self, table_name: str) -> tuple[str | None, str]:
        cleaned = table_name.strip().replace("[", "").replace("]", "")
        if not cleaned:
            raise ValueError("表名不能为空")
        parts = cleaned.split(".")
        if len(parts) == 1:
            schema_name = None
            pure_table_name = parts[0]
        elif len(parts) == 2:
            schema_name, pure_table_name = parts
        else:
            raise ValueError("表名格式只支持 table 或 schema.table")
        if not all(re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", part) for part in [item for item in [schema_name, pure_table_name] if item]):
            raise ValueError("表名只能包含字母、数字和下划线，并以字母或下划线开头")
        return schema_name, pure_table_name

    def _query_table_columns(self, schema_name: str | None, table_name: str) -> list[dict[str, Any]]:
        connection = self._connect()
        try:
            cursor = connection.cursor()
            if schema_name:
                cursor.execute(
                    """
                    SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, DATA_TYPE, IS_NULLABLE, ORDINAL_POSITION
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
                    ORDER BY ORDINAL_POSITION
                    """,
                    (schema_name, table_name),
                )
            else:
                cursor.execute(
                    """
                    SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, DATA_TYPE, IS_NULLABLE, ORDINAL_POSITION
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_NAME = %s
                    ORDER BY TABLE_SCHEMA, ORDINAL_POSITION
                    """,
                    (table_name,),
                )
            return list(cursor.fetchall())
        finally:
            connection.close()

    def _map_sqlserver_type(self, data_type: str) -> str:
        normalized = data_type.lower()
        if normalized in {"int", "bigint", "smallint", "tinyint"}:
            return "integer"
        if normalized in {"decimal", "numeric", "money", "smallmoney", "float", "real"}:
            return "decimal"
        if normalized in {"date"}:
            return "date"
        if normalized in {"datetime", "datetime2", "smalldatetime", "datetimeoffset", "time"}:
            return "datetime"
        if normalized in {"bit"}:
            return "boolean"
        return "string"

    def _infer_role(self, column_name: str, data_type: str) -> str:
        name = column_name.lower()
        field_type = self._map_sqlserver_type(data_type)
        if field_type in {"date", "datetime"} or any(keyword in name for keyword in ["date", "time", "day", "month", "year"]):
            return "date"
        if field_type in {"integer", "decimal"} and not name.endswith("id") and "code" not in name:
            return "measure"
        if field_type == "string" and any(keyword in name for keyword in ["remark", "desc", "note", "memo"]):
            return "text"
        return "dimension"

    def _bind_validation_parameters(
        self,
        sql: str,
        parameters: list[ParameterDSL],
        result: SqlValidationResult,
    ) -> str:
        parameter_map = {parameter.name: parameter for parameter in parameters}

        def replace(match: re.Match[str]) -> str:
            name = match.group(1)
            parameter = parameter_map.get(name)
            if parameter is None:
                result.errors.append(f"SQL 引用了未定义参数：{name}")
                return "NULL"
            return self._default_literal(parameter)

        executable_sql = PARAMETER_PATTERN.sub(replace, sql)
        unresolved = PARAMETER_PATTERN.findall(executable_sql)
        if unresolved:
            result.errors.append(f"SQL 参数未完全绑定：{', '.join(sorted(set(unresolved)))}")
        return executable_sql

    def _default_literal(self, parameter: ParameterDSL) -> str:
        if parameter.default is not None:
            return self._literal(parameter.default, parameter.type)
        if parameter.type in {FieldType.DATE, FieldType.DATETIME}:
            if parameter.name.lower().startswith(("end", "to")):
                return "'2999-12-31'"
            return "'1900-01-01'"
        if parameter.type in {FieldType.INTEGER, FieldType.DECIMAL}:
            return "0"
        if parameter.type == FieldType.BOOLEAN:
            return "0"
        return "''"

    def _literal(self, value: Any, field_type: FieldType) -> str:
        if value is None:
            return "NULL"
        if field_type in {FieldType.INTEGER, FieldType.DECIMAL}:
            try:
                return str(float(value) if field_type == FieldType.DECIMAL else int(value))
            except (TypeError, ValueError):
                return "0"
        if field_type == FieldType.BOOLEAN:
            return "1" if bool(value) else "0"
        return "'" + str(value).replace("'", "''") + "'"

    def _execute_sample_query(self, sql: str) -> tuple[list[dict[str, Any]], list[str]]:
        connection = self._connect()
        try:
            cursor = connection.cursor()
            cursor.execute(sql)
            rows = cursor.fetchmany(settings.FR_AI_SQLSERVER_MAX_ROWS)
            columns = [item[0] for item in (cursor.description or [])]
            return [self._normalize_row(row) for row in rows], columns
        finally:
            connection.close()

    def _connect(self):
        try:
            import pymssql
        except ImportError as exc:
            raise RuntimeError("未安装 pymssql，无法连接 SQL Server") from exc

        return pymssql.connect(
            server=settings.FR_AI_SQLSERVER_HOST,
            port=settings.FR_AI_SQLSERVER_PORT,
            user=settings.FR_AI_SQLSERVER_USER,
            password=settings.FR_AI_SQLSERVER_PASSWORD,
            database=settings.FR_AI_SQLSERVER_DATABASE,
            login_timeout=settings.FR_AI_SQLSERVER_QUERY_TIMEOUT_SECONDS,
            timeout=settings.FR_AI_SQLSERVER_QUERY_TIMEOUT_SECONDS,
            as_dict=True,
        )

    def _normalize_row(self, row: dict[str, Any]) -> dict[str, Any]:
        normalized: dict[str, Any] = {}
        for key, value in row.items():
            if isinstance(value, (datetime, date)):
                normalized[key] = value.isoformat()
            elif isinstance(value, Decimal):
                normalized[key] = float(value)
            else:
                normalized[key] = value
        return normalized


sqlserver_query_service = SqlServerQueryService()
