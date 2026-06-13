from pathlib import PurePosixPath
import re
import zipfile
import xml.etree.ElementTree as ET
from io import BytesIO

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.models.agent.fr_report import FrReportDatabaseConnection, FrReportDatabaseDriver, FrReportVisibilityPreference
from app.schemas.agent.fr_report.report_file import (
    FrReportCellRead,
    FrReportCellStyleRead,
    FrReportCellWidgetRead,
    FrReportConditionRead,
    FrReportDatabaseConnectionCreate,
    FrReportDatabaseConnectionRead,
    FrReportDatabaseDriverRead,
    FrReportDataColumnRead,
    FrReportDatasetParameterRead,
    FrReportDatasetPreviewRequest,
    FrReportDatasetPreviewResponse,
    FrReportDatasetRead,
    FrReportDimensionRead,
    FrReportDocumentRead,
    FrReportFieldBindingRead,
    FrReportFileListResponse,
    FrReportFileRead,
    FrReportFileStructureRead,
    FrReportMergeRead,
    FrReportSheetRead,
    FrReportSubmitBindingRead,
    FrReportSubmitColumnRead,
    FrReportStructureSummaryRead,
)
from app.services.agent.fr_report.fr_minio_service import fr_minio_service
from app.services.agent.fr_report.sqlserver_query_service import sqlserver_query_service


MAX_SQL_PREVIEW_LENGTH = 8000
MAX_PARSED_CELLS = 1200
MAX_UNSUPPORTED_NODES = 40


class FrReportFileService:
    def __init__(self) -> None:
        self.storage = fr_minio_service

    async def list_report_files(
        self,
        db: AsyncSession | None = None,
        user_id: int | None = None,
        prefix: str | None = None,
        keyword: str | None = None,
        limit: int = 200,
        include_all: bool = False,
    ) -> FrReportFileListResponse:
        allowed_prefixes = self._allowed_prefixes()
        target_prefix = self._normalize_prefix(prefix or allowed_prefixes[0])
        if not self._is_allowed_prefix(target_prefix, allowed_prefixes):
            raise ValueError("报表目录不在允许扫描范围内")

        extensions = self._extensions()
        objects = await self.storage.list_objects(target_prefix)
        keyword_text = keyword.strip().lower() if keyword else None
        visible_paths = await self.get_visible_paths(db, user_id) if db is not None and user_id is not None else []
        items: list[FrReportFileRead] = []
        for obj in objects:
            object_path = getattr(obj, "object_name", "")
            if not object_path or object_path.endswith("/"):
                continue
            file_type = PurePosixPath(object_path).suffix.lower()
            if file_type not in extensions:
                continue
            if keyword_text and keyword_text not in object_path.lower():
                continue
            report_path = self._to_report_path(object_path)
            if not include_all and visible_paths and not self._matches_visible_paths(report_path, visible_paths):
                continue
            items.append(
                FrReportFileRead(
                    objectPath=object_path,
                    reportPath=report_path,
                    fileName=PurePosixPath(object_path).name,
                    fileType=file_type.lstrip("."),
                    size=getattr(obj, "size", None),
                    etag=getattr(obj, "etag", None),
                    lastModified=getattr(obj, "last_modified", None),
                )
            )

        items.sort(key=lambda item: item.lastModified.timestamp() if item.lastModified else 0, reverse=True)
        sliced_items = items[: max(1, min(limit, 5000))]
        return FrReportFileListResponse(
            bucket=self.storage.bucket,
            prefix=target_prefix,
            allowedPrefixes=allowed_prefixes,
            extensions=extensions,
            total=len(items),
            items=sliced_items,
            visibleOnly=not include_all and bool(visible_paths),
            selectedVisiblePaths=visible_paths,
        )

    async def get_visible_paths(self, db: AsyncSession | None, user_id: int | None) -> list[str]:
        if db is None or user_id is None:
            return []
        statement = select(FrReportVisibilityPreference).where(
            FrReportVisibilityPreference.user_id == user_id,
            FrReportVisibilityPreference.is_deleted == 0,
            FrReportVisibilityPreference.status == "active",
        )
        row = (await db.exec(statement)).first()
        return row.visible_paths if row else []

    async def update_visible_paths(
        self,
        db: AsyncSession,
        user_id: int,
        visible_paths: list[str],
    ) -> list[str]:
        normalized_paths = self._normalize_visible_paths(visible_paths)
        statement = select(FrReportVisibilityPreference).where(
            FrReportVisibilityPreference.user_id == user_id,
            FrReportVisibilityPreference.is_deleted == 0,
        )
        row = (await db.exec(statement)).first()
        if row is None:
            row = FrReportVisibilityPreference(user_id=user_id, visible_paths=normalized_paths)
            db.add(row)
        else:
            row.visible_paths = normalized_paths
            row.status = "active"
        await db.commit()
        await db.refresh(row)
        return row.visible_paths

    async def read_report_structure(
        self,
        db: AsyncSession,
        user_id: int,
        object_path: str,
    ) -> FrReportFileStructureRead:
        normalized_path = self._normalize_prefix(object_path)
        allowed_prefixes = self._allowed_prefixes()
        if not self._is_allowed_prefix(normalized_path, allowed_prefixes):
            raise ValueError("报表目录不在允许读取范围内")

        file_type = PurePosixPath(normalized_path).suffix.lower()
        if file_type not in self._extensions():
            raise ValueError("当前文件类型不支持结构解析")

        report_path = self._to_report_path(normalized_path)
        visible_paths = await self.get_visible_paths(db, user_id)
        if visible_paths and not self._matches_visible_paths(report_path, visible_paths):
            raise PermissionError("当前报表不在你的显示范围内")

        stat = await self.storage.stat_object(normalized_path)
        data = await self.storage.download_file(normalized_path)
        base = {
            "objectPath": normalized_path,
            "reportPath": report_path,
            "fileName": PurePosixPath(normalized_path).name,
            "fileType": file_type.lstrip("."),
            "size": getattr(stat, "size", None),
            "etag": getattr(stat, "etag", None),
            "lastModified": getattr(stat, "last_modified", None),
        }

        if zipfile.is_zipfile(BytesIO(data)):
            return FrReportFileStructureRead(
                **base,
                format="zip",
                warnings=["当前报表是压缩包结构，第一版暂未展开解析内部 XML"],
            )

        text, encoding = self._decode_report_text(data)
        if text is None:
            return FrReportFileStructureRead(
                **base,
                format="binary",
                warnings=["当前报表不是可直接解析的 XML 文本，后续需要补充二进制结构解析"],
            )

        try:
            root = ET.fromstring(text)
        except ET.ParseError as exc:
            return FrReportFileStructureRead(
                **base,
                format="text",
                encoding=encoding,
                warnings=[f"报表文本不是合法 XML：{exc}"],
            )

        datasets = self._parse_table_datasets(root)
        document = self._parse_report_document(root)
        tag_counts = self._count_tags(root)
        return FrReportFileStructureRead(
            **base,
            format="xml",
            encoding=encoding,
            xmlVersion=root.attrib.get("xmlVersion"),
            releaseVersion=root.attrib.get("releaseVersion"),
            rootTag=root.tag,
            datasets=datasets,
            document=document,
            summary=FrReportStructureSummaryRead(
                datasetCount=len(datasets),
                parameterCount=tag_counts.get("Parameter", 0),
                widgetCount=tag_counts.get("Widget", 0),
                queryCount=sum(1 for dataset in datasets if dataset.querySql),
                sheetCount=len(document.sheets),
                cellCount=sum(len(sheet.cells) for sheet in document.sheets),
                mergeCount=sum(len(sheet.merges) for sheet in document.sheets),
            ),
            warnings=self._document_warnings(document),
        )

    async def list_database_connections(self, db: AsyncSession, user_id: int) -> list[FrReportDatabaseConnectionRead]:
        statement = select(FrReportDatabaseConnection).where(
            FrReportDatabaseConnection.user_id == user_id,
            FrReportDatabaseConnection.is_deleted == 0,
            FrReportDatabaseConnection.status == "active",
        )
        rows = (await db.exec(statement)).all()
        driver_map = await self._database_driver_map(db)
        return [self._to_connection_read(row, driver_map.get(row.driver_key)) for row in rows]

    async def list_database_drivers(self, db: AsyncSession) -> list[FrReportDatabaseDriverRead]:
        statement = (
            select(FrReportDatabaseDriver)
            .where(
                FrReportDatabaseDriver.is_deleted == 0,
                FrReportDatabaseDriver.status == "active",
            )
            .order_by(FrReportDatabaseDriver.id)
        )
        rows = (await db.exec(statement)).all()
        return [self._to_driver_read(row) for row in rows]

    async def upsert_database_connection(
        self,
        db: AsyncSession,
        user_id: int,
        payload: FrReportDatabaseConnectionCreate,
    ) -> FrReportDatabaseConnectionRead:
        connection_name = payload.connectionName.strip()
        if not connection_name:
            raise ValueError("连接名称不能为空")
        driver = await self._get_database_driver(db, payload.driverKey)
        if driver is None:
            raise ValueError("未找到对应的数据库驱动，请先选择已支持的驱动")

        statement = select(FrReportDatabaseConnection).where(
            FrReportDatabaseConnection.user_id == user_id,
            FrReportDatabaseConnection.connection_name == connection_name,
            FrReportDatabaseConnection.is_deleted == 0,
        )
        row = (await db.exec(statement)).first()
        if row is None:
            row = FrReportDatabaseConnection(
                user_id=user_id,
                connection_name=connection_name,
                driver_key=driver.driver_key,
                db_type=driver.db_type,
                host=payload.host.strip(),
                port=payload.port or driver.default_port,
                database=payload.database.strip(),
                username=payload.username.strip(),
                password=payload.password,
                odbc_driver=driver.odbc_driver,
            )
            db.add(row)
        else:
            row.driver_key = driver.driver_key
            row.db_type = driver.db_type
            row.host = payload.host.strip()
            row.port = payload.port or driver.default_port
            row.database = payload.database.strip()
            row.username = payload.username.strip()
            row.password = payload.password
            row.odbc_driver = driver.odbc_driver
            row.status = "active"
        await db.commit()
        await db.refresh(row)
        return self._to_connection_read(row, driver)

    async def preview_dataset(
        self,
        db: AsyncSession,
        user_id: int,
        payload: FrReportDatasetPreviewRequest,
    ) -> FrReportDatasetPreviewResponse:
        connection = await self._get_database_connection(db, user_id, payload.connectionName)
        if connection is None:
            return FrReportDatasetPreviewResponse(
                connectionName=payload.connectionName,
                needsConnection=True,
                errors=["未找到对应数据库连接，请先补充连接信息"],
            )

        parameter_values = {item.name: item.value for item in payload.parameters}
        rows, columns, warnings, errors = await sqlserver_query_service.preview_select_sql(
            payload.querySql,
            parameter_values,
            {
                "host": connection.host,
                "port": connection.port,
                "database": connection.database,
                "username": connection.username,
                "password": connection.password,
                "odbc_driver": connection.odbc_driver,
                "db_type": connection.db_type,
                "driver_key": connection.driver_key,
            },
            max_rows=payload.maxRows,
        )
        return FrReportDatasetPreviewResponse(
            connectionName=payload.connectionName,
            needsConnection=False,
            executed=not errors,
            success=not errors,
            columns=columns,
            sampleRows=rows,
            rowCount=len(rows),
            warnings=warnings,
            errors=errors,
        )

    def _allowed_prefixes(self) -> list[str]:
        prefixes = [
            self._normalize_prefix(item)
            for item in settings.FR_AI_REPORT_FILE_PREFIXES.split(",")
            if item.strip()
        ]
        return prefixes or ["webroot/APP/reportlets"]

    def _extensions(self) -> list[str]:
        extensions = []
        for item in settings.FR_AI_REPORT_FILE_EXTENSIONS.split(","):
            value = item.strip().lower()
            if not value:
                continue
            extensions.append(value if value.startswith(".") else f".{value}")
        return extensions or [".cpt", ".frm"]

    def _normalize_prefix(self, value: str) -> str:
        return value.strip().strip("/")

    def _is_allowed_prefix(self, prefix: str, allowed_prefixes: list[str]) -> bool:
        return any(prefix == allowed or prefix.startswith(f"{allowed}/") for allowed in allowed_prefixes)

    def _to_report_path(self, object_path: str) -> str:
        marker = "webroot/APP/"
        if object_path.startswith(marker):
            return object_path[len(marker) :]
        return object_path

    def _normalize_visible_paths(self, paths: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for path in paths:
            value = path.strip().strip("/")
            if not value or value in seen:
                continue
            seen.add(value)
            result.append(value)
        return result

    def _matches_visible_paths(self, report_path: str, visible_paths: list[str]) -> bool:
        normalized_report_path = report_path.strip().strip("/")
        display_report_path = normalized_report_path.removeprefix("reportlets/")
        return any(
            normalized_report_path == visible_path
            or normalized_report_path.startswith(f"{visible_path}/")
            or display_report_path == visible_path
            or display_report_path.startswith(f"{visible_path}/")
            for visible_path in visible_paths
        )

    async def _get_database_connection(
        self,
        db: AsyncSession,
        user_id: int,
        connection_name: str,
    ) -> FrReportDatabaseConnection | None:
        statement = select(FrReportDatabaseConnection).where(
            FrReportDatabaseConnection.user_id == user_id,
            FrReportDatabaseConnection.connection_name == connection_name.strip(),
            FrReportDatabaseConnection.is_deleted == 0,
            FrReportDatabaseConnection.status == "active",
        )
        return (await db.exec(statement)).first()

    async def _get_database_driver(self, db: AsyncSession, driver_key: str) -> FrReportDatabaseDriver | None:
        statement = select(FrReportDatabaseDriver).where(
            FrReportDatabaseDriver.driver_key == driver_key.strip(),
            FrReportDatabaseDriver.is_deleted == 0,
            FrReportDatabaseDriver.status == "active",
        )
        return (await db.exec(statement)).first()

    async def _database_driver_map(self, db: AsyncSession) -> dict[str, FrReportDatabaseDriver]:
        statement = select(FrReportDatabaseDriver).where(
            FrReportDatabaseDriver.is_deleted == 0,
            FrReportDatabaseDriver.status == "active",
        )
        rows = (await db.exec(statement)).all()
        return {row.driver_key: row for row in rows}

    def _to_connection_read(
        self,
        row: FrReportDatabaseConnection,
        driver: FrReportDatabaseDriver | None = None,
    ) -> FrReportDatabaseConnectionRead:
        return FrReportDatabaseConnectionRead(
            connectionName=row.connection_name,
            driverKey=row.driver_key,
            driverName=driver.display_name if driver else None,
            dbType=row.db_type,
            host=row.host,
            port=row.port,
            database=row.database,
            username=row.username,
            odbcDriver=row.odbc_driver,
            configured=bool(row.password),
        )

    def _to_driver_read(self, row: FrReportDatabaseDriver) -> FrReportDatabaseDriverRead:
        return FrReportDatabaseDriverRead(
            driverKey=row.driver_key,
            displayName=row.display_name,
            dbType=row.db_type,
            pythonDriver=row.python_driver,
            odbcDriver=row.odbc_driver,
            defaultPort=row.default_port,
            description=row.description,
        )

    def _decode_report_text(self, data: bytes) -> tuple[str | None, str | None]:
        for encoding in ("utf-8", "gbk", "utf-16le"):
            try:
                text = data.decode(encoding)
            except UnicodeDecodeError:
                continue
            if self._printable_ratio(text[:2000]) >= 0.85:
                return text, encoding
        return None, None

    def _printable_ratio(self, text: str) -> float:
        if not text:
            return 0
        printable_count = sum(1 for char in text if char.isprintable() or char in "\r\n\t")
        return printable_count / len(text)

    def _parse_report_document(self, root: ET.Element) -> FrReportDocumentRead:
        element_paths = self._element_paths(root)
        style_map = self._style_map(root)
        report_nodes = [node for node in root.iter() if self._local_name(node.tag).lower() == "report"]
        table_nodes = [node for node in root.iter() if self._local_name(node.tag).lower() == "table"]
        sheet_sources = report_nodes or table_nodes or [root]
        sheets: list[FrReportSheetRead] = []

        for index, source in enumerate(sheet_sources, start=1):
            table = self._first_descendant(source, {"table"})
            sheet_node = table or source
            sheet = self._parse_sheet(source, sheet_node, index, element_paths, style_map)
            if sheet.cells or sheet_node is not root:
                sheets.append(sheet)

        if not sheets:
            sheets.append(
                FrReportSheetRead(
                    name="Sheet1",
                    rowCount=18,
                    columnCount=12,
                    warnings=["未识别到可渲染单元格，已返回空白设计器网格"],
                )
            )

        title = self._infer_document_title(root, sheets)
        return FrReportDocumentRead(
            title=title,
            sheets=sheets,
            unsupportedNodes=self._unsupported_nodes(root),
            parseCoverage={
                "reportNodes": len(report_nodes),
                "tableNodes": len(table_nodes),
                "sheetCount": len(sheets),
                "cellCount": sum(len(sheet.cells) for sheet in sheets),
                "mergeCount": sum(len(sheet.merges) for sheet in sheets),
            },
        )

    def _parse_sheet(
        self,
        source: ET.Element,
        sheet_node: ET.Element,
        index: int,
        element_paths: dict[int, str],
        style_map: dict[str, FrReportCellStyleRead],
    ) -> FrReportSheetRead:
        name = source.attrib.get("name") or source.attrib.get("reportName") or f"Sheet{index}"
        submit_bindings = self._parse_submit_bindings(source)
        submit_bindings_by_cell = self._submit_bindings_by_cell(submit_bindings)
        cells = self._parse_cells(sheet_node, element_paths, style_map, submit_bindings_by_cell)
        merges = [
            FrReportMergeRead(
                startRow=cell.row,
                startColumn=cell.column,
                endRow=cell.row + cell.rowSpan - 1,
                endColumn=cell.column + cell.colSpan - 1,
            )
            for cell in cells
            if cell.rowSpan > 1 or cell.colSpan > 1
        ]
        row_dimensions = self._parse_dimensions(sheet_node, "row")
        column_dimensions = self._parse_dimensions(sheet_node, "column")
        row_count = self._positive_int(
            sheet_node.attrib.get("rows")
            or sheet_node.attrib.get("rowCount")
            or sheet_node.attrib.get("row_count")
            or source.attrib.get("rows")
        )
        column_count = self._positive_int(
            sheet_node.attrib.get("columns")
            or sheet_node.attrib.get("columnCount")
            or sheet_node.attrib.get("colCount")
            or sheet_node.attrib.get("column_count")
            or source.attrib.get("columns")
        )
        max_row = max([cell.row + cell.rowSpan - 1 for cell in cells] + [dimension.index for dimension in row_dimensions] + [0])
        max_column = max(
            [cell.column + cell.colSpan - 1 for cell in cells] + [dimension.index for dimension in column_dimensions] + [0]
        )
        warnings = []
        if len(cells) >= MAX_PARSED_CELLS:
            warnings.append(f"单元格超过 {MAX_PARSED_CELLS} 个，当前仅返回前 {MAX_PARSED_CELLS} 个")
        if not cells:
            warnings.append("未识别到单元格节点，当前仅能展示空白网格")

        return FrReportSheetRead(
            name=name,
            rowCount=max(row_count or 0, max_row, 18),
            columnCount=max(column_count or 0, max_column, 12),
            rows=row_dimensions,
            columns=column_dimensions,
            cells=cells,
            merges=merges,
            submitBindings=submit_bindings,
            warnings=warnings,
        )

    def _parse_cells(
        self,
        sheet_node: ET.Element,
        element_paths: dict[int, str],
        style_map: dict[str, FrReportCellStyleRead],
        submit_bindings_by_cell: dict[str, list[FrReportSubmitBindingRead]] | None = None,
    ) -> list[FrReportCellRead]:
        cells: list[FrReportCellRead] = []
        for node in sheet_node.iter():
            if self._local_name(node.tag).lower() not in {"cell", "cellelement", "c"}:
                continue
            row = self._cell_coordinate_value(node, ("row", "r", "rowIndex", "row_index"))
            column = self._cell_coordinate_value(node, ("column", "col", "c", "columnIndex", "column_index"))
            if row is None or column is None:
                continue
            text = self._cell_text(node)
            formula = text if text and text.startswith("=") else self._child_text(node, {"formula"})
            field_binding = self._field_binding_from_cell(node) or self._field_binding(formula or text or "")
            data_column = self._data_column_from_cell(node, field_binding)
            widget = self._cell_widget(node)
            row_span = self._span_value(node, ("rowSpan", "rowspan", "row_span", "mergeRows", "mergeRowCount", "rs"))
            col_span = self._span_value(node, ("colSpan", "colspan", "col_span", "mergeColumns", "mergeColumnCount", "cs"))
            cells.append(
                FrReportCellRead(
                    row=row,
                    column=column,
                    address=f"{self._column_label(column)}{row}",
                    text=text,
                    formula=formula,
                    fieldBinding=field_binding,
                    dataColumn=data_column,
                    widget=widget,
                    submitBindings=(submit_bindings_by_cell or {}).get(f"{row}:{column}", []),
                    rowSpan=row_span,
                    colSpan=col_span,
                    expandDirection=self._expand_direction(node),
                    style=self._cell_style(node, style_map),
                    rawTag=self._local_name(node.tag),
                    rawPath=element_paths.get(id(node)),
                )
            )
            if len(cells) >= MAX_PARSED_CELLS:
                break
        cells.sort(key=lambda item: (item.row, item.column))
        return cells

    def _parse_dimensions(self, sheet_node: ET.Element, dimension_type: str) -> list[FrReportDimensionRead]:
        tag_names = {"row", "rowheight"} if dimension_type == "row" else {"column", "col", "columnwidth"}
        index_keys = ("index", "idx", "row", "r") if dimension_type == "row" else ("index", "idx", "column", "col", "c")
        size_keys = ("height", "h") if dimension_type == "row" else ("width", "w")
        dimensions: list[FrReportDimensionRead] = []
        seen: set[int] = set()
        for node in sheet_node.iter():
            tag = self._local_name(node.tag).lower()
            if tag not in tag_names:
                continue
            if tag in {"rowheight", "columnwidth"}:
                for item in self._parse_dimension_list(node):
                    if item.index in seen:
                        continue
                    dimensions.append(item)
                    seen.add(item.index)
                continue
            index = self._coordinate_value(node, index_keys)
            if index is None or index in seen:
                continue
            size = self._positive_int(self._first_attribute(node, size_keys))
            dimensions.append(FrReportDimensionRead(index=index, size=size))
            seen.add(index)
        dimensions.sort(key=lambda item: item.index)
        return dimensions

    def _parse_dimension_list(self, node: ET.Element) -> list[FrReportDimensionRead]:
        values = [value.strip() for value in "".join(node.itertext()).split(",")]
        result: list[FrReportDimensionRead] = []
        for index, value in enumerate(values, start=1):
            raw_size = self._integer_value(value)
            if raw_size is None:
                continue
            result.append(FrReportDimensionRead(index=index, size=self._finereport_size_to_px(raw_size)))
        return result

    def _cell_text(self, node: ET.Element) -> str | None:
        object_node = self._first_child(node, {"o"})
        if object_node is not None:
            text = self._cell_object_text(object_node)
        else:
            text = self._child_text(node, {"text", "value", "content"})
        if text is None and node.text and node.text.strip():
            text = node.text.strip()
        if text is None:
            return None
        return text[:500]

    def _cell_object_text(self, object_node: ET.Element) -> str | None:
        object_type = (object_node.attrib.get("t") or "").lower()
        object_class = (object_node.attrib.get("class") or "").lower()
        if object_type == "dscolumn":
            binding = self._dataset_binding_from_object(object_node)
            if binding:
                return binding.expression
        if "formula" in object_class:
            attributes = self._first_child(object_node, {"attributes"})
            if attributes is not None:
                text = "".join(attributes.itertext()).strip()
                return text or None
        text = "".join(object_node.itertext()).strip()
        if "$$$" in text:
            binding = self._dataset_binding_from_object(object_node)
            return binding.expression if binding else None
        return text or None

    def _child_text(self, node: ET.Element, names: set[str]) -> str | None:
        for child in node:
            if self._local_name(child.tag).lower() in names:
                text = "".join(child.itertext()).strip()
                return text or None
        return None

    def _child_attribute(self, node: ET.Element | None, names: set[str], attribute_name: str) -> str | None:
        if node is None:
            return None
        for child in node:
            if self._local_name(child.tag).lower() in names:
                return child.attrib.get(attribute_name)
        return None

    def _field_binding(self, expression: str) -> FrReportFieldBindingRead | None:
        if not expression:
            return None
        patterns = [
            r"\$\{?(?P<dataset>[\w\u4e00-\u9fff]+)\.(?P<field>[\w\u4e00-\u9fff]+)\}?",
            r"(?P<aggregation>SUM|AVG|COUNT|MAX|MIN|G|S)\((?P<dataset>[\w\u4e00-\u9fff]+)\.(?P<field>[\w\u4e00-\u9fff]+)\)",
        ]
        for pattern in patterns:
            match = re.search(pattern, expression, re.IGNORECASE)
            if not match:
                continue
            aggregation = match.groupdict().get("aggregation")
            return FrReportFieldBindingRead(
                dataset=match.group("dataset"),
                field=match.group("field"),
                expression=expression[:500],
                aggregation=aggregation.upper() if aggregation else None,
            )
        return None

    def _field_binding_from_cell(self, node: ET.Element) -> FrReportFieldBindingRead | None:
        object_node = self._first_child(node, {"o"})
        if object_node is None:
            return None
        return self._dataset_binding_from_object(object_node)

    def _dataset_binding_from_object(self, object_node: ET.Element) -> FrReportFieldBindingRead | None:
        if (object_node.attrib.get("t") or "").lower() != "dscolumn":
            return None
        attributes = self._first_child(object_node, {"attributes"})
        attrs = attributes.attrib if attributes is not None else object_node.attrib
        dataset = attrs.get("dsName") or attrs.get("dsname") or attrs.get("dataset")
        field = attrs.get("columnName") or attrs.get("columnname") or attrs.get("field")
        if not dataset or not field:
            return None
        aggregation = self._dataset_aggregation(object_node)
        expression = f"{dataset}.{aggregation}({field})" if aggregation else f"{dataset}.{field}"
        return FrReportFieldBindingRead(dataset=dataset, field=field, expression=expression, aggregation=aggregation)

    def _dataset_aggregation(self, object_node: ET.Element) -> str | None:
        for node in object_node.iter():
            class_name = node.attrib.get("class", "")
            if "FunctionGrouper" in class_name:
                return "G"
            if "SumFunction" in class_name:
                return "SUM"
            if "AverageFunction" in class_name:
                return "AVG"
            if "CountFunction" in class_name:
                return "COUNT"
            if "MaxFunction" in class_name:
                return "MAX"
            if "MinFunction" in class_name:
                return "MIN"
        return None

    def _data_column_from_cell(
        self,
        node: ET.Element,
        binding: FrReportFieldBindingRead | None,
    ) -> FrReportDataColumnRead | None:
        object_node = self._first_child(node, {"o"})
        if object_node is None or (object_node.attrib.get("t") or "").lower() != "dscolumn":
            return None
        conditions = self._data_column_conditions(object_node)
        parent_cell = self._parent_cell_from_conditions(conditions)
        present_node = self._first_child(node, {"present"})
        present_content = self._child_text(present_node, {"content"}) if present_node is not None else None
        expand_direction = self._expand_direction(node)
        complex_extendable = self._first_child(object_node, {"complex"}) is not None
        return FrReportDataColumnRead(
            dataset=binding.dataset if binding else None,
            field=binding.field if binding else None,
            parentCell=parent_cell,
            aggregation=binding.aggregation if binding else self._dataset_aggregation(object_node),
            expandDirection=expand_direction,
            customDisplay=present_content,
            horizontalExtendable=complex_extendable or expand_direction == "horizontal",
            verticalExtendable=complex_extendable or expand_direction == "vertical",
            conditions=conditions,
        )

    def _data_column_conditions(self, object_node: ET.Element) -> list[FrReportConditionRead]:
        conditions: list[FrReportConditionRead] = []
        for condition_node in object_node.iter():
            if self._local_name(condition_node.tag).lower() != "condition":
                continue
            if "CommonCondition" not in condition_node.attrib.get("class", ""):
                continue
            column = self._child_text(condition_node, {"cname"})
            compare_node = self._first_child(condition_node, {"compare"})
            operator = self._condition_operator(compare_node.attrib.get("op") if compare_node is not None else None)
            value = self._child_text(compare_node, {"o"}) if compare_node is not None else None
            join_node = self._nearest_parent_join(object_node, condition_node)
            conditions.append(
                FrReportConditionRead(
                    column=column,
                    operator=operator,
                    value=value,
                    join=join_node,
                )
            )
        return conditions

    def _nearest_parent_join(self, root: ET.Element, target: ET.Element) -> str | None:
        for join_node in root.iter():
            if self._local_name(join_node.tag).lower() != "joincondition":
                continue
            if any(child is target for child in join_node.iter()):
                return "AND" if join_node.attrib.get("join") == "0" else "OR"
        return None

    def _condition_operator(self, value: object | None) -> str | None:
        text = str(value).strip() if value is not None else ""
        return {
            "0": "等于",
            "1": "不等于",
            "2": "大于",
            "3": "大于等于",
            "4": "小于",
            "5": "小于等于",
            "6": "包含",
            "7": "不包含",
        }.get(text, text or None)

    def _parent_cell_from_conditions(self, conditions: list[FrReportConditionRead]) -> str | None:
        # FineReport stores parent-cell relationships separately in some versions.
        # For legacy CPTs this is often implied by sibling conditions, so keep it explicit only when found later.
        return None

    def _cell_widget(self, node: ET.Element) -> FrReportCellWidgetRead | None:
        widget_node = self._first_descendant(node, {"widget"})
        if widget_node is None:
            return None
        widget_class = widget_node.attrib.get("class")
        widget_attr = self._first_descendant(widget_node, {"widgetattr"})
        widget_name = self._child_attribute(widget_node, {"widgetname"}, "name")
        return FrReportCellWidgetRead(
            widgetClass=widget_class,
            widgetType=self._widget_type(widget_class),
            widgetName=widget_name,
            description=widget_attr.attrib.get("description") if widget_attr is not None else None,
        )

    def _widget_type(self, widget_class: str | None) -> str | None:
        if not widget_class:
            return None
        name = widget_class.rsplit(".", 1)[-1]
        return {
            "NumberEditor": "数字控件",
            "TextEditor": "文本控件",
            "DateEditor": "日期控件",
            "ComboBox": "下拉框",
            "CheckBox": "复选框",
            "Radio": "单选框",
        }.get(name, name)

    def _parse_submit_bindings(self, source: ET.Element) -> list[FrReportSubmitBindingRead]:
        bindings: list[FrReportSubmitBindingRead] = []
        write_attr = self._first_descendant(source, {"reportwriteattr"})
        if write_attr is None:
            return bindings
        for submit_node in write_attr:
            if self._local_name(submit_node.tag).lower() != "submitvisitor":
                continue
            dml_node = self._first_child(submit_node, {"dmlconfig"})
            table_node = self._first_child(dml_node, {"table"}) if dml_node is not None else None
            binding = FrReportSubmitBindingRead(
                name=self._child_text(submit_node, {"name"}),
                database=self._child_attribute(submit_node, {"attributes"}, "dsName"),
                schemaName=table_node.attrib.get("schema") if table_node is not None else None,
                tableName=table_node.attrib.get("name") if table_node is not None else None,
                submitterClass=submit_node.attrib.get("class"),
                columns=self._submit_columns(dml_node),
            )
            bindings.append(binding)
        return bindings

    def _submit_columns(self, dml_node: ET.Element | None) -> list[FrReportSubmitColumnRead]:
        if dml_node is None:
            return []
        columns: list[FrReportSubmitColumnRead] = []
        for column_node in dml_node:
            if self._local_name(column_node.tag).lower() != "columnconfig":
                continue
            column_row = self._first_child(column_node, {"columnrow"})
            row = self._integer_value(column_row.attrib.get("row")) if column_row is not None else None
            column = self._integer_value(column_row.attrib.get("column")) if column_row is not None else None
            cell = f"{self._column_label(column + 1)}{row + 1}" if row is not None and column is not None else None
            columns.append(
                FrReportSubmitColumnRead(
                    column=column_node.attrib.get("name", ""),
                    value=self._cell_object_text(self._first_child(column_node, {"o"})) if self._first_child(column_node, {"o"}) is not None else None,
                    isKey=self._bool_value(column_node.attrib.get("isKey")) or False,
                    skipUnmodified=self._bool_value(column_node.attrib.get("skipUnmodified")) or False,
                    cell=cell,
                )
            )
        return columns

    def _submit_bindings_by_cell(self, bindings: list[FrReportSubmitBindingRead]) -> dict[str, list[FrReportSubmitBindingRead]]:
        result: dict[str, list[FrReportSubmitBindingRead]] = {}
        for binding in bindings:
            for column in binding.columns:
                if not column.cell:
                    continue
                match = re.match(r"([A-Z]+)(\d+)", column.cell)
                if not match:
                    continue
                key = f"{int(match.group(2))}:{self._column_index(match.group(1))}"
                result.setdefault(key, []).append(binding)
        return result

    def _style_map(self, root: ET.Element) -> dict[str, FrReportCellStyleRead]:
        styles: dict[str, FrReportCellStyleRead] = {}
        for index, node in enumerate(item for item in root.iter() if self._local_name(item.tag).lower() == "style"):
            styles[str(index)] = self._style_from_node(node, str(index))
        return styles

    def _cell_style(self, node: ET.Element, style_map: dict[str, FrReportCellStyleRead]) -> FrReportCellStyleRead:
        style_node = self._first_descendant(node, {"style"})
        attrs = dict(node.attrib)
        style_name = attrs.get("name") or attrs.get("styleName") or attrs.get("style") or attrs.get("s")
        base_style = style_map.get(style_name or "")
        if style_node is not None:
            attrs.update(style_node.attrib)
            inline_style = self._style_from_node(style_node, style_name)
            return self._merge_style(base_style, inline_style)
        direct_style = FrReportCellStyleRead(
            styleName=style_name,
            fontSize=self._fr_font_size_to_px(self._positive_int(attrs.get("fontSize") or attrs.get("fontsize") or attrs.get("size"))),
            bold=self._bool_value(attrs.get("bold") or attrs.get("isBold")),
            italic=self._bool_value(attrs.get("italic") or attrs.get("isItalic")),
            color=self._fr_color(attrs.get("color") or attrs.get("foreground") or attrs.get("fontColor")),
            backgroundColor=self._fr_color(attrs.get("background") or attrs.get("backgroundColor") or attrs.get("bgColor")),
            horizontalAlign=self._alignment(attrs.get("horizontalAlign") or attrs.get("hAlign") or attrs.get("align") or attrs.get("horizontal_alignment")),
            verticalAlign=self._alignment(attrs.get("verticalAlign") or attrs.get("vAlign") or attrs.get("vertical_alignment")),
        )
        return self._merge_style(base_style, direct_style)

    def _style_from_node(self, style_node: ET.Element, style_name: str | None = None) -> FrReportCellStyleRead:
        attrs = dict(style_node.attrib)
        font_node = self._first_child(style_node, {"frfont"})
        background_node = self._first_child(style_node, {"background"})
        border_node = self._first_child(style_node, {"border"})
        font_attrs = font_node.attrib if font_node is not None else {}
        background_attrs = background_node.attrib if background_node is not None else {}
        border = self._border_style(border_node)
        font_style = self._integer_value(font_attrs.get("style"))
        return FrReportCellStyleRead(
            styleName=style_name or attrs.get("name") or attrs.get("styleName"),
            fontFamily=font_attrs.get("name"),
            fontSize=self._fr_font_size_to_px(self._positive_int(font_attrs.get("size"))),
            bold=self._bool_value(font_attrs.get("bold")) if font_attrs.get("bold") is not None else (bool(font_style & 1) if font_style is not None else None),
            italic=self._bool_value(font_attrs.get("italic")) if font_attrs.get("italic") is not None else (bool(font_style & 2) if font_style is not None else None),
            underline=self._bool_value(font_attrs.get("underline")),
            color=self._node_color(font_node, ("foreground", "color")),
            backgroundColor=self._node_color(background_node, ("color",)) if background_attrs.get("name") != "NullBackground" else None,
            borderColor=border["borderColor"],
            borderTop=border["borderTop"],
            borderRight=border["borderRight"],
            borderBottom=border["borderBottom"],
            borderLeft=border["borderLeft"],
            horizontalAlign=self._alignment(attrs.get("horizontal_alignment") or attrs.get("horizontalAlign") or attrs.get("align")),
            verticalAlign=self._alignment(attrs.get("vertical_alignment") or attrs.get("verticalAlign")),
        )

    def _border_style(self, border_node: ET.Element | None) -> dict[str, str | bool | None]:
        result: dict[str, str | bool | None] = {
            "borderColor": None,
            "borderTop": None,
            "borderRight": None,
            "borderBottom": None,
            "borderLeft": None,
        }
        if border_node is None:
            return result
        side_map = {"top": "borderTop", "right": "borderRight", "bottom": "borderBottom", "left": "borderLeft"}
        for child in border_node:
            side_key = side_map.get(self._local_name(child.tag).lower())
            if not side_key:
                continue
            has_border = (self._integer_value(child.attrib.get("style")) or 0) > 0
            result[side_key] = has_border
            if has_border and result["borderColor"] is None:
                result["borderColor"] = self._node_color(child, ("color",))
        return result

    def _merge_style(
        self,
        base: FrReportCellStyleRead | None,
        override: FrReportCellStyleRead | None,
    ) -> FrReportCellStyleRead:
        if base is None:
            return override or FrReportCellStyleRead()
        if override is None:
            return base
        data = base.model_dump()
        for key, value in override.model_dump().items():
            if value is not None:
                data[key] = value
        return FrReportCellStyleRead(**data)

    def _expand_direction(self, node: ET.Element) -> str | None:
        expand_node = self._first_descendant(node, {"expand"})
        if expand_node is None:
            return self._expand_direction_label(node.attrib.get("expandDirection") or node.attrib.get("expand"))
        return self._expand_direction_label(expand_node.attrib.get("dir") or expand_node.attrib.get("direction"))

    def _expand_direction_label(self, value: object | None) -> str | None:
        if value is None:
            return None
        text = str(value).strip().lower()
        return {
            "0": "vertical",
            "1": "horizontal",
            "2": "none",
            "vertical": "vertical",
            "horizontal": "horizontal",
            "none": "none",
        }.get(text, text or None)

    def _span_value(self, node: ET.Element, keys: tuple[str, ...]) -> int:
        value = self._integer_value(self._first_attribute(node, keys))
        if value is not None:
            return max(value, 1)
        merge_node = self._first_descendant(node, {"merge"})
        if merge_node is not None:
            value = self._integer_value(self._first_attribute(merge_node, keys))
            if value is not None:
                return max(value, 1)
        return 1

    def _coordinate_value(self, node: ET.Element, keys: tuple[str, ...]) -> int | None:
        value = self._integer_value(self._first_attribute(node, keys))
        if value is None:
            return None
        return value + 1 if value == 0 else value

    def _cell_coordinate_value(self, node: ET.Element, keys: tuple[str, ...]) -> int | None:
        value = self._integer_value(self._first_attribute(node, keys))
        if value is None:
            return None
        if self._local_name(node.tag).lower() == "c":
            return value + 1
        return value + 1 if value == 0 else value

    def _first_attribute(self, node: ET.Element, keys: tuple[str, ...]) -> str | None:
        lower_attrs = {key.lower(): value for key, value in node.attrib.items()}
        for key in keys:
            value = lower_attrs.get(key.lower())
            if value not in (None, ""):
                return value
        return None

    def _positive_int(self, value: object | None) -> int | None:
        number = self._integer_value(value)
        return number if number is not None and number > 0 else None

    def _integer_value(self, value: object | None) -> int | None:
        if value is None:
            return None
        match = re.search(r"-?\d+", str(value))
        if not match:
            return None
        return int(match.group())

    def _finereport_size_to_px(self, value: int) -> int:
        if value > 10000:
            return max(16, min(round(value / 30480), 240))
        return max(16, min(value, 240))

    def _fr_font_size_to_px(self, value: int | None) -> int | None:
        if value is None:
            return None
        return max(10, min(round(value / 6), 32))

    def _fr_color(self, value: object | None) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        if text.startswith("#"):
            return text
        number = self._integer_value(text)
        if number is None:
            return text
        rgb = number & 0xFFFFFF
        return f"#{rgb:06x}"

    def _node_color(self, node: ET.Element | None, attribute_names: tuple[str, ...]) -> str | None:
        if node is None:
            return None
        for name in attribute_names:
            color = self._fr_color(node.attrib.get(name))
            if color:
                return color
        for child in node.iter():
            for name in attribute_names:
                color = self._fr_color(child.attrib.get(name))
                if color:
                    return color
            if self._local_name(child.tag).lower() == "finecolor":
                color = self._fr_color(child.attrib.get("color"))
                if color:
                    return color
        return None

    def _alignment(self, value: object | None) -> str | None:
        if value is None:
            return None
        text = str(value).strip().lower()
        return {
            "0": "center",
            "1": "left",
            "2": "right",
            "3": "justify",
            "left": "left",
            "center": "center",
            "right": "right",
            "middle": "center",
            "top": "top",
            "bottom": "bottom",
        }.get(text, text or None)

    def _bool_value(self, value: object | None) -> bool | None:
        if value is None:
            return None
        text = str(value).strip().lower()
        if text in {"true", "1", "yes"}:
            return True
        if text in {"false", "0", "no"}:
            return False
        return None

    def _first_descendant(self, node: ET.Element, names: set[str]) -> ET.Element | None:
        for child in node.iter():
            if child is node:
                continue
            if self._local_name(child.tag).lower() in names:
                return child
        return None

    def _first_child(self, node: ET.Element, names: set[str]) -> ET.Element | None:
        for child in node:
            if self._local_name(child.tag).lower() in names:
                return child
        return None

    def _infer_document_title(self, root: ET.Element, sheets: list[FrReportSheetRead]) -> str | None:
        for sheet in sheets:
            first_cell = next((cell for cell in sheet.cells if cell.text and cell.row <= 3), None)
            if first_cell:
                return first_cell.text
        return root.attrib.get("name") or root.attrib.get("title")

    def _unsupported_nodes(self, root: ET.Element) -> list[str]:
        parsed_tags = {
            "workbook",
            "report",
            "table",
            "cell",
            "cellelement",
            "c",
            "row",
            "column",
            "col",
            "rowheight",
            "columnwidth",
            "o",
            "text",
            "value",
            "formula",
            "style",
            "expand",
            "merge",
            "tabledatamap",
            "tabledata",
            "parameters",
            "parameter",
            "attributes",
            "connection",
            "databasename",
            "query",
            "pagequery",
        }
        result: list[str] = []
        seen: set[str] = set()
        for node in root.iter():
            tag = self._local_name(node.tag)
            if tag.lower() in parsed_tags or tag in seen:
                continue
            seen.add(tag)
            result.append(tag)
            if len(result) >= MAX_UNSUPPORTED_NODES:
                break
        return result

    def _document_warnings(self, document: FrReportDocumentRead) -> list[str]:
        warnings: list[str] = []
        if not document.sheets:
            warnings.append("未识别到工作表结构")
        elif sum(len(sheet.cells) for sheet in document.sheets) == 0:
            warnings.append("未识别到可渲染单元格，画布将展示空白网格")
        if document.unsupportedNodes:
            warnings.append(f"存在暂未解析节点：{', '.join(document.unsupportedNodes[:8])}")
        for sheet in document.sheets:
            warnings.extend(sheet.warnings)
        return list(dict.fromkeys(warnings))

    def _element_paths(self, root: ET.Element) -> dict[int, str]:
        paths: dict[int, str] = {}

        def walk(node: ET.Element, path: str) -> None:
            paths[id(node)] = path
            counters: dict[str, int] = {}
            for child in node:
                tag = self._local_name(child.tag)
                counters[tag] = counters.get(tag, 0) + 1
                walk(child, f"{path}/{tag}[{counters[tag]}]")

        walk(root, f"/{self._local_name(root.tag)}")
        return paths

    def _local_name(self, tag: str) -> str:
        return tag.rsplit("}", 1)[-1] if "}" in tag else tag

    def _column_label(self, index: int) -> str:
        label = ""
        current = index
        while current > 0:
            current, remainder = divmod(current - 1, 26)
            label = chr(65 + remainder) + label
        return label or "A"

    def _column_index(self, label: str) -> int:
        result = 0
        for char in label.upper():
            if not ("A" <= char <= "Z"):
                continue
            result = result * 26 + ord(char) - 64
        return result

    def _parse_table_datasets(self, root: ET.Element) -> list[FrReportDatasetRead]:
        datasets: list[FrReportDatasetRead] = []
        for table_data in root.findall(".//TableData"):
            raw_query = (table_data.findtext("./Query") or "").strip()
            formatted_query = self._format_sql_preview(raw_query)
            query_sql = formatted_query[:MAX_SQL_PREVIEW_LENGTH] if formatted_query else None
            parameters: list[FrReportDatasetParameterRead] = []
            for parameter in table_data.findall("./Parameters/Parameter"):
                attributes = parameter.find("./Attributes")
                name = attributes.attrib.get("name") if attributes is not None else None
                if not name:
                    continue
                parameters.append(
                    FrReportDatasetParameterRead(
                        name=name,
                        defaultValue=(parameter.findtext("./O") or "").strip() or None,
                    )
                )
            datasets.append(
                FrReportDatasetRead(
                    name=table_data.attrib.get("name", ""),
                    className=table_data.attrib.get("class"),
                    databaseName=(table_data.findtext(".//DatabaseName") or "").strip() or None,
                    parameters=parameters,
                    querySql=query_sql,
                    querySqlTruncated=bool(formatted_query and len(formatted_query) > MAX_SQL_PREVIEW_LENGTH),
                )
            )
        return datasets

    def _format_sql_preview(self, sql: str) -> str:
        normalized = sql.strip()
        if not normalized:
            return ""
        if "\n" in normalized:
            return "\n".join(line.rstrip() for line in normalized.splitlines()).strip()
        keywords = [
            " SELECT ",
            " FROM ",
            " WHERE ",
            " AND ",
            " OR ",
            " GROUP BY ",
            " ORDER BY ",
            " HAVING ",
            " UNION ",
        ]
        compact_sql = re.sub(r"\s+", " ", normalized)
        formatted = f" {compact_sql} "
        for keyword in keywords:
            formatted = re.sub(keyword, f"\n{keyword.strip()} ", formatted, flags=re.IGNORECASE)
        return formatted.strip()

    def _count_tags(self, root: ET.Element) -> dict[str, int]:
        counts: dict[str, int] = {}
        for node in root.iter():
            counts[node.tag] = counts.get(node.tag, 0) + 1
        return counts


fr_report_file_service = FrReportFileService()
