import asyncio
import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from app.core.config import settings
from app.core.logger import logger
from app.schemas.agent.fr_report.ai_report import SqlValidationResult
from app.schemas.agent.fr_report.report_dsl import FieldType, ParameterDSL


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
        if not rows:
            result.success = False
            result.errors.append(
                "SQL 执行成功但返回 0 行，请检查日期、市场、产品、等级、包装等筛选条件是否过窄或与样例数据不一致"
            )
            fallback_rows, fallback_columns, fallback_warning = await self._fallback_preview_rows(sql)
            if fallback_rows:
                result.columns = fallback_columns
                result.sampleRows = fallback_rows
                result.rowCount = len(fallback_rows)
                result.warnings.append(fallback_warning)
            else:
                result.warnings.append("未能构造可用的兜底样例预览 SQL")
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

    async def sample_data_model(self, data_model: Any, row_count: int = 5) -> dict[str, list[dict[str, Any]]]:
        if not settings.FR_AI_SQLSERVER_ENABLED or not self.is_configured:
            return {}
        tables = data_model.tables or [{"tableName": data_model.tableName}]
        samples: dict[str, list[dict[str, Any]]] = {}
        for table in tables[:8]:
            table_name = str(table.get("tableName"))
            if table_name == "__join__":
                continue
            try:
                self._parse_table_name(table_name)
                rows, _columns = await asyncio.to_thread(
                    self._execute_sample_query,
                    f"SELECT TOP {max(1, min(row_count, 20))} * FROM {table_name}",
                )
                samples[table_name] = rows
            except Exception as exc:
                logger.warning(f"SQL Server 样例数据查询失败 {table_name}：{exc}")
        return samples

    async def preview_select_sql(
        self,
        sql: str,
        parameter_values: dict[str, Any],
        connection_config: dict[str, Any],
        max_rows: int = 20,
    ) -> tuple[list[dict[str, Any]], list[str], list[str], list[str]]:
        errors = self._validate_readonly_sql(sql)
        warnings: list[str] = []
        if errors:
            return [], [], warnings, errors

        executable_sql = self._bind_preview_parameters(sql, parameter_values)
        unresolved = PARAMETER_PATTERN.findall(executable_sql)
        if unresolved:
            errors.append(f"SQL 参数未全部赋值：{', '.join(sorted(set(unresolved)))}")
            return [], [], warnings, errors

        db_type = str(connection_config.get("db_type") or "sqlserver").lower()
        preview_sql = self._limit_preview_sql(executable_sql, max_rows, db_type)
        try:
            rows, columns = await asyncio.to_thread(self._execute_sample_query_with_config, preview_sql, connection_config, max_rows)
        except Exception as exc:
            logger.warning(f"FineReport 数据集预览失败：{exc}")
            errors.append(f"数据集预览失败：{exc}")
            return [], [], warnings, errors

        if len(rows) >= max_rows:
            warnings.append(f"仅返回前 {max_rows} 行预览数据")
        return rows, columns, warnings, errors

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

    async def _fallback_preview_rows(self, sql: str) -> tuple[list[dict[str, Any]], list[str], str]:
        preview_sql = self._build_unfiltered_preview_sql(sql)
        if not preview_sql:
            return [], [], ""
        safety_errors = self._validate_readonly_sql(preview_sql)
        if safety_errors:
            return [], [], ""
        try:
            rows, columns = await asyncio.to_thread(self._execute_sample_query, preview_sql)
        except Exception as exc:
            logger.warning(f"FineReport AI SQL 空结果兜底预览失败：{exc}")
            return [], [], ""
        if not rows:
            return [], [], ""
        return (
            rows,
            columns,
            "原 SQL 执行成功但返回 0 行，已临时使用去除筛选条件后的安全样例 SQL 展示数据预览；请检查日期、市场、产品等筛选条件是否过窄。",
        )

    def _build_unfiltered_preview_sql(self, sql: str) -> str | None:
        normalized = sql.strip().rstrip(";")
        if re.search(r"\b(group\s+by|having|union|intersect|except|distinct)\b", normalized, re.IGNORECASE):
            return None
        match = re.match(
            r"^\s*select\s+(?P<select>.*?)\s+from\s+(?P<from>.+?)(?:\s+where\s+.+?)?(?:\s+order\s+by\s+.+?)?$",
            normalized,
            re.IGNORECASE | re.DOTALL,
        )
        if not match:
            return None
        select_clause = match.group("select").strip()
        from_clause = match.group("from").strip()
        from_clause = re.split(r"\s+where\s+|\s+order\s+by\s+", from_clause, flags=re.IGNORECASE)[0].strip()
        if not select_clause or not from_clause:
            return None
        select_clause = re.sub(r"^\s*top\s+\d+\s+", "", select_clause, flags=re.IGNORECASE)
        return f"SELECT TOP {settings.FR_AI_SQLSERVER_MAX_ROWS}\n    {select_clause}\nFROM {from_clause}"

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
                    f"""
                    SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, DATA_TYPE, IS_NULLABLE, ORDINAL_POSITION
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_SCHEMA = '{schema_name}' AND TABLE_NAME = '{table_name}'
                    ORDER BY ORDINAL_POSITION
                    """
                )
            else:
                cursor.execute(
                    f"""
                    SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, DATA_TYPE, IS_NULLABLE, ORDINAL_POSITION
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_NAME = '{table_name}'
                    ORDER BY TABLE_SCHEMA, ORDINAL_POSITION
                    """
                )
            return self._rows_to_dicts(cursor)
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

        def replace_quoted(match: re.Match[str]) -> str:
            name = match.group(1)
            parameter = parameter_map.get(name)
            if parameter is None:
                result.errors.append(f"SQL 引用了未定义参数：{name}")
                return "NULL"
            return self._default_literal(parameter)

        def replace(match: re.Match[str]) -> str:
            name = match.group(1)
            parameter = parameter_map.get(name)
            if parameter is None:
                result.errors.append(f"SQL 引用了未定义参数：{name}")
                return "NULL"
            return self._default_literal(parameter)

        executable_sql = re.sub(r"'\$\{([A-Za-z_][A-Za-z0-9_]*)\}'", replace_quoted, sql)
        executable_sql = PARAMETER_PATTERN.sub(replace, executable_sql)
        unresolved = PARAMETER_PATTERN.findall(executable_sql)
        if unresolved:
            result.errors.append(f"SQL 参数未完全绑定：{', '.join(sorted(set(unresolved)))}")
        return executable_sql

    def _bind_preview_parameters(self, sql: str, parameter_values: dict[str, Any]) -> str:
        def literal(name: str) -> str:
            value = parameter_values.get(name)
            if value is None:
                return "NULL"
            if isinstance(value, bool):
                return "1" if value else "0"
            if isinstance(value, (int, float)):
                return str(value)
            return "'" + str(value).replace("'", "''") + "'"

        executable_sql = re.sub(r"'\$\{([A-Za-z_][A-Za-z0-9_]*)\}'", lambda match: literal(match.group(1)), sql)
        return PARAMETER_PATTERN.sub(lambda match: literal(match.group(1)), executable_sql)

    def _limit_preview_sql(self, sql: str, max_rows: int, db_type: str = "sqlserver") -> str:
        normalized = sql.strip().rstrip(";")
        row_limit = max(1, min(max_rows, settings.FR_AI_SQLSERVER_MAX_ROWS, 100))
        if db_type == "mysql":
            if re.search(r"\blimit\s+\d+\s*$", normalized, re.IGNORECASE):
                return normalized
            return f"{normalized}\nLIMIT {row_limit}"
        if re.match(r"^\s*select\s+top\s+\d+\b", normalized, re.IGNORECASE):
            return normalized
        if re.match(r"^\s*select\b", normalized, re.IGNORECASE):
            return re.sub(r"^\s*select\b", f"SELECT TOP {row_limit}", normalized, count=1, flags=re.IGNORECASE)
        return normalized

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
            columns = [item[0] for item in (cursor.description or [])]
            rows = cursor.fetchmany(settings.FR_AI_SQLSERVER_MAX_ROWS)
            return [self._normalize_row(row) for row in self._rows_to_dicts(cursor, rows)], columns
        finally:
            connection.close()

    def _execute_sample_query_with_config(
        self,
        sql: str,
        connection_config: dict[str, Any],
        max_rows: int,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        connection = self._connect_with_config(connection_config)
        try:
            cursor = connection.cursor()
            cursor.execute(sql)
            columns = [item[0] for item in (cursor.description or [])]
            rows = cursor.fetchmany(max(1, min(max_rows, 100)))
            return [self._normalize_row(row) for row in self._rows_to_dicts(cursor, rows)], columns
        finally:
            connection.close()

    def _connect(self):
        try:
            return self._connect_pyodbc()
        except Exception as pyodbc_exc:
            logger.warning(f"pyodbc 连接 SQL Server 失败，尝试 pymssql：{pyodbc_exc}")
            return self._connect_pymssql()

    def _connect_with_config(self, connection_config: dict[str, Any]):
        db_type = str(connection_config.get("db_type") or "sqlserver").lower()
        if db_type == "mysql":
            return self._connect_mysql_with_config(connection_config)
        try:
            return self._connect_pyodbc_with_config(connection_config)
        except Exception as pyodbc_exc:
            logger.warning(f"pyodbc 连接 SQL Server 失败，尝试 pymssql：{pyodbc_exc}")
            return self._connect_pymssql_with_config(connection_config)

    def _connect_mysql_with_config(self, connection_config: dict[str, Any]):
        try:
            import pymysql
        except ImportError as exc:
            raise RuntimeError("未安装 pymysql，无法连接 MySQL 8") from exc

        return pymysql.connect(
            host=connection_config["host"],
            port=connection_config.get("port") or 3306,
            user=connection_config["username"],
            password=connection_config["password"],
            database=connection_config["database"],
            connect_timeout=settings.FR_AI_SQLSERVER_QUERY_TIMEOUT_SECONDS,
            read_timeout=settings.FR_AI_SQLSERVER_QUERY_TIMEOUT_SECONDS,
            write_timeout=settings.FR_AI_SQLSERVER_QUERY_TIMEOUT_SECONDS,
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
        )

    def _connect_pyodbc_with_config(self, connection_config: dict[str, Any]):
        try:
            import pyodbc
        except ImportError as exc:
            raise RuntimeError("未安装 pyodbc，无法使用 ODBC 连接 SQL Server") from exc

        driver = self._resolve_sqlserver_odbc_driver(pyodbc, connection_config.get("odbc_driver"))
        conn_str = (
            f"DRIVER={{{driver}}};"
            f"SERVER={connection_config['host']},{connection_config.get('port') or 1433};"
            f"DATABASE={connection_config['database']};"
            f"UID={connection_config['username']};"
            f"PWD={connection_config['password']};"
            "TrustServerCertificate=yes;"
            "Encrypt=no;"
        )
        return pyodbc.connect(conn_str, timeout=settings.FR_AI_SQLSERVER_QUERY_TIMEOUT_SECONDS)

    def _resolve_sqlserver_odbc_driver(self, pyodbc_module: Any, preferred_driver: str | None) -> str:
        installed_drivers = set(pyodbc_module.drivers())
        candidates = [
            preferred_driver,
            settings.FR_AI_SQLSERVER_ODBC_DRIVER,
            "ODBC Driver 18 for SQL Server",
            "ODBC Driver 17 for SQL Server",
            "SQL Server Native Client 11.0",
            "SQL Server",
        ]
        for driver in candidates:
            if driver and driver in installed_drivers:
                return driver
        if preferred_driver:
            return preferred_driver
        if installed_drivers:
            return sorted(installed_drivers)[0]
        return settings.FR_AI_SQLSERVER_ODBC_DRIVER

    def _connect_pymssql_with_config(self, connection_config: dict[str, Any]):
        try:
            import pymssql
        except ImportError as exc:
            raise RuntimeError("未安装 pymssql，无法连接 SQL Server") from exc

        return pymssql.connect(
            server=connection_config["host"],
            port=connection_config.get("port") or 1433,
            user=connection_config["username"],
            password=connection_config["password"],
            database=connection_config["database"],
            login_timeout=settings.FR_AI_SQLSERVER_QUERY_TIMEOUT_SECONDS,
            timeout=settings.FR_AI_SQLSERVER_QUERY_TIMEOUT_SECONDS,
            as_dict=True,
        )

    def _connect_pyodbc(self):
        try:
            import pyodbc
        except ImportError as exc:
            raise RuntimeError("未安装 pyodbc，无法使用 ODBC 连接 SQL Server") from exc

        conn_str = (
            f"DRIVER={{{settings.FR_AI_SQLSERVER_ODBC_DRIVER}}};"
            f"SERVER={settings.FR_AI_SQLSERVER_HOST},{settings.FR_AI_SQLSERVER_PORT};"
            f"DATABASE={settings.FR_AI_SQLSERVER_DATABASE};"
            f"UID={settings.FR_AI_SQLSERVER_USER};"
            f"PWD={settings.FR_AI_SQLSERVER_PASSWORD};"
            "TrustServerCertificate=yes;"
            "Encrypt=no;"
        )
        return pyodbc.connect(conn_str, timeout=settings.FR_AI_SQLSERVER_QUERY_TIMEOUT_SECONDS)

    def _connect_pymssql(self):
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

    def _rows_to_dicts(self, cursor, rows=None) -> list[dict[str, Any]]:
        rows = cursor.fetchall() if rows is None else rows
        columns = [item[0] for item in (cursor.description or [])]
        normalized_rows: list[dict[str, Any]] = []
        for row in rows:
            if isinstance(row, dict):
                normalized_rows.append(row)
            else:
                normalized_rows.append(dict(zip(columns, row, strict=False)))
        return normalized_rows

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
