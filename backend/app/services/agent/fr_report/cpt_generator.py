from html import escape

from app.core.config import settings
from app.schemas.agent.fr_report.report_dsl import Aggregation, CellWidgetDSL, FieldRole, FieldType, LayoutColumnDSL, ParameterDSL, ReportDSL
from app.services.agent.fr_report.style_templates import DEFAULT_STYLE_TEMPLATE, FrReportAreaStyle, FrReportStyleTemplate


class CptGenerator:
    def generate(self, dsl: ReportDSL) -> bytes:
        template = DEFAULT_STYLE_TEMPLATE
        dataset = dsl.datasets[0]
        cells = self._cells_xml(dsl)
        style_list = self._style_list_xml(template)
        has_groups = self._header_groups(dsl)
        rows = (4 if has_groups else 3) if dsl.layout.columns else 1
        action_columns = self._action_column_count(dsl)
        columns = max(len(dsl.layout.columns) + action_columns, 1)
        row_heights = self._row_heights(rows, has_groups, template)
        column_width_values = self._column_width_values(dsl, template)
        column_widths = ",".join(str(width) for width in column_width_values)
        report_attr_set = self._report_attr_set_xml(column_width_values, template)
        report_web_attr = self._report_web_attr_xml(dsl)
        report_write_attr = self._report_write_attr_xml(dsl, self._data_row_index(dsl))
        preview_type = "1" if dsl.writeBack.enabled else "0"
        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<WorkBook xmlVersion="20211223" releaseVersion="11.5.0">
<TableDataMap>
<TableData name="{escape(dataset.name)}" class="com.fr.data.impl.DBTableData">
<Desensitizations desensitizeOpen="false"/>
<Parameters>
{self._parameters_xml(dsl)}
</Parameters>
<Attributes maxMemRowCount="-1"/>
<Connection class="com.fr.data.impl.NameDatabaseConnection">
<DatabaseName><![CDATA[{settings.FR_AI_FINEREPORT_DB_NAME}]]></DatabaseName>
</Connection>
<Query><![CDATA[{dataset.sql}]]></Query>
<PageQuery><![CDATA[]]></PageQuery>
</TableData>
</TableDataMap>
{report_web_attr}
<ReportParameterAttr>
<Attributes showWindow="true"/>
{self._parameter_ui_xml(dsl)}
</ReportParameterAttr>
<Report class="com.fr.report.worksheet.WorkSheet" name="{escape(dsl.reportName)}">
<ReportPageAttr>
<HR/>
<FR/>
</ReportPageAttr>
<Table rows="{rows}" columns="{columns}">
<RowHeight defaultValue="{template.data_row_height}"><![CDATA[{row_heights}]]></RowHeight>
<ColumnWidth defaultValue="{template.default_column_width}"><![CDATA[{column_widths}]]></ColumnWidth>
<CellElementList>
{cells}
</CellElementList>
</Table>
{report_attr_set}
{report_write_attr}
<PrivilegeControl/>
</Report>
{style_list}
<DesignerVersion DesignerVersion="KAA"/>
<PreviewType PreviewType="{preview_type}"/>
</WorkBook>
"""
        return xml.encode("utf-8")

    def _report_attr_set_xml(self, column_widths: list[int], template: FrReportStyleTemplate) -> str:
        content_width = sum(column_widths)
        margin_width = template.paper_margin_left + template.paper_margin_right
        padding_width = 3600000
        paper_width = min(
            max(template.min_paper_width, content_width + margin_width + padding_width),
            template.max_paper_width,
        )
        return f"""<ReportAttrSet>
<ReportSettings headerHeight="0" footerHeight="0">
<PaperSetting>
<PaperSize width="{paper_width}" height="{template.paper_height}"/>
<Margin top="{template.paper_margin_top}" left="{template.paper_margin_left}" bottom="{template.paper_margin_bottom}" right="{template.paper_margin_right}"/>
</PaperSetting>
<FollowingTheme background="true"/>
<Background name="ColorBackground">
<color><FineColor color="-1" hor="-1" ver="-1"/></color>
</Background>
</ReportSettings>
<Header reportPageType="0">
<Background name="NullBackground"/>
<CenterList/>
<LeftList/>
<RightList/>
</Header>
<Footer reportPageType="0">
<Background name="NullBackground"/>
<CenterList/>
<LeftList/>
<RightList/>
</Footer>
</ReportAttrSet>"""

    def _report_web_attr_xml(self, dsl: ReportDSL) -> str:
        if not dsl.writeBack.enabled or not dsl.writeBack.toolbar:
            return ""
        return """<ReportWebAttr>
<ServerPrinter/>
<WebWriteContent>
<ToolBars>
<ToolBarManager>
<Location>
<Embed position="1"/>
</Location>
<ToolBar>
<Widget class="com.fr.report.web.button.write.Submit">
<WidgetAttr description=""><PrivilegeControl/></WidgetAttr>
<Text><![CDATA[提交]]></Text>
<IconName><![CDATA[submit]]></IconName>
<Verify failVerifySubmit="false" value="true"/>
<Sheet onlySubmitSelect="false"/>
</Widget>
<Widget class="com.fr.report.web.button.write.Verify">
<WidgetAttr description=""><PrivilegeControl/></WidgetAttr>
<Text><![CDATA[数据校验]]></Text>
<IconName><![CDATA[verify]]></IconName>
</Widget>
<Widget class="com.fr.report.web.button.write.AppendColumnRow">
<WidgetAttr description=""><PrivilegeControl/></WidgetAttr>
<Text><![CDATA[添加记录]]></Text>
<IconName><![CDATA[appendrow]]></IconName>
</Widget>
<Widget class="com.fr.report.web.button.write.DeleteColumnRow">
<WidgetAttr description=""><PrivilegeControl/></WidgetAttr>
<Text><![CDATA[删除记录]]></Text>
<IconName><![CDATA[deleterow]]></IconName>
</Widget>
</ToolBar>
</ToolBarManager>
</ToolBars>
</WebWriteContent>
</ReportWebAttr>"""

    def _report_write_attr_xml(self, dsl: ReportDSL, data_row: int) -> str:
        write_back = dsl.writeBack
        if not write_back.enabled or not write_back.tableName:
            return ""
        action_columns = self._action_column_count(dsl)
        action_start = self._action_start_column(dsl.layout.columns, action_columns)
        field_to_column = self._field_to_render_column(dsl.layout.columns, action_start, action_columns)
        parts: list[str] = []
        for column in write_back.columns:
            column_name = escape(column.columnName)
            key = "true" if column.isKey else "false"
            skip = "true" if column.skipUnmodified else "false"
            if column.valueFormula:
                formula = self._resolve_writeback_formula(column.valueFormula, field_to_column, data_row)
                value_xml = f"""<O t="XMLable" class="com.fr.base.Formula">
<Attributes><![CDATA[{formula}]]></Attributes>
</O>"""
            elif column.field and column.field in field_to_column:
                value_xml = f"""<ColumnRow column="{field_to_column[column.field]}" row="{data_row}"/>"""
            else:
                continue
            parts.append(
                f"""<ColumnConfig name="{column_name}" isKey="{key}" skipUnmodified="{skip}">
{value_xml}
</ColumnConfig>"""
            )
        if not parts:
            return ""
        database_name = escape(write_back.databaseName or settings.FR_AI_FINEREPORT_DB_NAME)
        schema_name = escape(write_back.schemaName)
        table_name = escape(write_back.tableName)
        submitter_name = escape(write_back.submitterName)
        return f"""<ReportWriteAttr>
<SubmitVisitor class="com.fr.report.write.BuiltInSQLSubmiter">
<Name><![CDATA[{submitter_name}]]></Name>
<Attributes dsName="{database_name}"/>
<DMLConfig class="com.fr.write.config.UpdateConfig">
<Table schema="{schema_name}" name="{table_name}"/>
{''.join(parts)}
<Condition class="com.fr.data.condition.ListCondition"/>
</DMLConfig>
</SubmitVisitor>
</ReportWriteAttr>"""

    def _resolve_writeback_formula(self, formula: str, field_to_column: dict[str, int], data_row: int) -> str:
        resolved = formula
        for field, column in field_to_column.items():
            resolved = resolved.replace(f"{{{field}}}", self._cell_address(column, data_row))
        return resolved

    def _cell_address(self, column: int, row: int) -> str:
        return f"{self._column_name(column)}{row + 1}"

    def _column_name(self, column: int) -> str:
        value = column + 1
        parts: list[str] = []
        while value:
            value, remainder = divmod(value - 1, 26)
            parts.append(chr(ord("A") + remainder))
        return "".join(reversed(parts))

    def _row_heights(self, rows: int, has_groups: bool, template: FrReportStyleTemplate) -> str:
        if rows <= 1:
            return str(template.title_row_height)
        heights = [template.title_row_height]
        header_count = 2 if has_groups else 1
        heights.extend([template.header_row_height] * header_count)
        heights.extend([template.data_row_height] * max(0, rows - 1 - header_count))
        return ",".join(str(item) for item in heights[:rows])

    def _parameters_xml(self, dsl: ReportDSL) -> str:
        parts: list[str] = []
        for parameter in dsl.parameters:
            default = "" if parameter.default is None else str(parameter.default)
            parts.append(
                f"""<Parameter>
<Attributes name="{escape(parameter.name)}"/>
<O><![CDATA[{default}]]></O>
</Parameter>"""
            )
        return "\n".join(parts)

    def _cells_xml(self, dsl: ReportDSL) -> str:
        parts: list[str] = []
        columns = dsl.layout.columns or []
        action_columns = self._action_column_count(dsl)
        total_columns = len(columns) + action_columns
        action_start = self._action_start_column(columns, action_columns)
        field_to_column = self._field_to_render_column(columns, action_start, action_columns)
        title = dsl.reportMeta.title or dsl.reportName
        if columns:
            parts.append(self._text_cell_xml(0, 0, title, 0, col_span=total_columns))
        groups = self._header_groups(dsl)
        header_row = 2 if groups else 1
        data_row = header_row + 1
        if groups:
            parts.extend(self._group_header_cells(columns, groups, field_to_column))
            parts.extend(self._action_header_group_cells(action_start, action_columns))
        for index, column in enumerate(columns):
            row_span = 2 if groups and self._is_single_group_column(column, groups) else None
            actual_row = 1 if row_span else header_row
            parts.append(self._text_cell_xml(actual_row, field_to_column[column.field], column.title, 1, expand_direction="none", row_span=row_span))
        parts.extend(self._action_header_cells(action_start, action_columns, header_row))
        widget_map = {widget.field: widget for widget in dsl.writeBack.widgets} if dsl.writeBack.enabled else {}
        for index, column in enumerate(columns):
            render_column = field_to_column[column.field]
            widget = widget_map.get(column.field)
            style_index = self._body_style_index(column.role, column.type, editable=widget is not None)
            if column.role == FieldRole.MEASURE and column.aggregation != Aggregation.NONE:
                expression = self._field_expression(dsl.layout.dataset, column.field, column.role, column.aggregation)
                parts.append(self._text_cell_xml(data_row, render_column, expression, style_index, column.expandDirection))
            else:
                parts.append(
                    self._dataset_cell_xml(
                        data_row,
                        render_column,
                        dsl.layout.dataset,
                        column.field,
                        style_index,
                        column.expandDirection,
                        widget,
                    )
                )
        parts.extend(self._action_button_cells(columns, action_columns, action_start, field_to_column, data_row))
        return "\n".join(parts)

    def _column_width_values(self, dsl: ReportDSL, template: FrReportStyleTemplate) -> list[int]:
        columns = dsl.layout.columns or []
        action_columns = self._action_column_count(dsl)
        values = [self._layout_column_width(column) for column in columns] or [template.default_column_width]
        if action_columns:
            action_start = self._action_start_column(columns, action_columns)
            action_widths = [self._column_width(dsl.writeBack.rowActions.columnWidth)] * action_columns
            values = values[:action_start] + action_widths + values[action_start:]
        return values

    def _data_row_index(self, dsl: ReportDSL) -> int:
        return (2 if self._header_groups(dsl) else 1) + 1

    def _action_column_count(self, dsl: ReportDSL) -> int:
        return 2 if dsl.writeBack.enabled and dsl.writeBack.rowActions.enabled else 0

    def _action_header_group_cells(self, start_column: int, action_columns: int) -> list[str]:
        if action_columns <= 0:
            return []
        return [self._text_cell_xml(1, start_column, "操作", 1, expand_direction="none", col_span=action_columns)]

    def _action_header_cells(self, start_column: int, action_columns: int, header_row: int) -> list[str]:
        if action_columns <= 0:
            return []
        return [
            self._text_cell_xml(header_row, start_column, "插入行", 1, expand_direction="none"),
            self._text_cell_xml(header_row, start_column + 1, "删除行", 1, expand_direction="none"),
        ]

    def _action_button_cells(
        self,
        columns: list[LayoutColumnDSL],
        action_columns: int,
        action_start: int,
        field_to_column: dict[str, int],
        data_row: int,
    ) -> list[str]:
        if action_columns <= 0:
            return []
        fixed_column = next((field_to_column[column.field] for column in columns if not column.hidden), action_start)
        return [
            self._row_action_button_cell_xml(data_row, action_start, "AppendRowButton", "插入行", "add", fixed_column),
            self._row_action_button_cell_xml(data_row, action_start + 1, "DeleteRowButton", "删除行", "delete", fixed_column),
        ]

    def _action_start_column(self, columns: list[LayoutColumnDSL], action_columns: int) -> int:
        if action_columns <= 0:
            return len(columns)
        return next((index for index, column in enumerate(columns) if not column.hidden), len(columns))

    def _field_to_render_column(self, columns: list[LayoutColumnDSL], action_start: int, action_columns: int) -> dict[str, int]:
        return {
            column.field: index + action_columns if action_columns and index >= action_start else index
            for index, column in enumerate(columns)
        }

    def _parameter_ui_xml(self, dsl: ReportDSL) -> str:
        if not dsl.parameters:
            return ""
        widgets = [self._parameter_label_widget(0, "筛选条件", 35, 30, 80)]
        x = 130
        for index, parameter in enumerate(dsl.parameters[:8], start=1):
            label_x = x
            input_x = x + 72
            widgets.append(self._parameter_label_widget(index, parameter.label, label_x, 30, 70))
            widgets.append(self._parameter_input_widget(parameter, input_x, 30, 110))
            x += 205
        widgets.append(self._parameter_submit_widget(x + 10, 30))
        width = max(1000, x + 130)
        return f"""<ParameterUI class="com.fr.form.main.parameter.FormParameterUI">
<Parameters/>
<Layout class="com.fr.form.ui.container.WParameterLayout">
<WidgetName name="para"/>
<WidgetAttr aspectRatioLocked="false" aspectRatioBackup="-1.0" description="">
<PrivilegeControl/>
</WidgetAttr>
<FollowingTheme borderStyle="false"/>
<Margin top="0" left="0" bottom="0" right="0"/>
<Border>
<border style="0" borderRadius="0" type="0" borderStyle="0">
<color><FineColor color="-723724" hor="-1" ver="-1"/></color>
</border>
<WidgetTitle><O><![CDATA[新建标题]]></O><FRFont name="SimSun" style="0" size="72"/><Position pos="0"/></WidgetTitle>
<Alpha alpha="1.0"/>
</Border>
<Background name="ColorBackground"><color><FineColor color="-526086" hor="-1" ver="-1"/></color></Background>
<LCAttr vgap="0" hgap="0" compInterval="0"/>
{''.join(widgets)}
</Layout>
<DesignAttr width="{width}" height="80"/>
</ParameterUI>"""

    def _parameter_label_widget(self, index: int, label: str, x: int, y: int, width: int) -> str:
        return f"""<Widget class="com.fr.form.ui.container.WAbsoluteLayout$BoundsWidget">
<InnerWidget class="com.fr.form.ui.Label">
<WidgetName name="label_{index}"/>
<LabelName name="{escape(label)}"/>
<WidgetAttr aspectRatioLocked="false" aspectRatioBackup="-1.0" description=""><PrivilegeControl/></WidgetAttr>
<widgetValue><O><![CDATA[{label}]]></O></widgetValue>
<LabelAttr textalign="0" verticalcenter="true" autoline="false"/>
<FRFont name="SimSun" style="0" size="72"/>
</InnerWidget>
<BoundsAttr x="{x}" y="{y}" width="{width}" height="21"/>
</Widget>"""

    def _parameter_input_widget(self, parameter: ParameterDSL, x: int, y: int, width: int) -> str:
        if parameter.type in {FieldType.DATE, FieldType.DATETIME}:
            default = self._date_default_formula(parameter)
            return f"""<Widget class="com.fr.form.ui.container.WAbsoluteLayout$BoundsWidget">
<InnerWidget class="com.fr.form.ui.DateEditor">
<WidgetName name="{escape(parameter.name)}"/>
<WidgetAttr aspectRatioLocked="false" aspectRatioBackup="-1.0" description=""><PrivilegeControl/></WidgetAttr>
<widgetValue><O t="XMLable" class="com.fr.base.Formula"><Attributes><![CDATA[{default}]]></Attributes></O></widgetValue>
<DateAttr/>
</InnerWidget>
<BoundsAttr x="{x}" y="{y}" width="{width}" height="21"/>
</Widget>"""
        return f"""<Widget class="com.fr.form.ui.container.WAbsoluteLayout$BoundsWidget">
<InnerWidget class="com.fr.form.ui.ComboBox">
<WidgetName name="{escape(parameter.name)}"/>
<WidgetAttr aspectRatioLocked="false" aspectRatioBackup="-1.0" description=""><PrivilegeControl/></WidgetAttr>
<Dictionary class="com.fr.data.impl.TableDataDictionary">
<FormulaDictAttr kiName="{escape(parameter.name)}" viName="{escape(parameter.name)}"/>
<TableDataDictAttr>
<TableData class="com.fr.data.impl.NameTableData"><Name><![CDATA[ds_main]]></Name></TableData>
</TableDataDictAttr>
</Dictionary>
<widgetValue><O><![CDATA[]]></O></widgetValue>
</InnerWidget>
<BoundsAttr x="{x}" y="{y}" width="{width}" height="21"/>
</Widget>"""

    def _parameter_submit_widget(self, x: int, y: int) -> str:
        return f"""<Widget class="com.fr.form.ui.container.WAbsoluteLayout$BoundsWidget">
<InnerWidget class="com.fr.form.parameter.FormSubmitButton">
<WidgetName name="Search"/>
<WidgetAttr aspectRatioLocked="false" aspectRatioBackup="-1.0" description=""><PrivilegeControl/></WidgetAttr>
<Text><![CDATA[查询]]></Text>
</InnerWidget>
<BoundsAttr x="{x}" y="{y}" width="80" height="21"/>
</Widget>"""

    def _date_default_formula(self, parameter: ParameterDSL) -> str:
        if parameter.default:
            return str(parameter.default)
        if parameter.name.lower().startswith("start"):
            return "=DATEINMONTH(TODAY(),1)"
        return "=TODAY()"

    def _field_expression(self, dataset_name: str, field_name: str, role: FieldRole, aggregation: Aggregation) -> str:
        if role == FieldRole.MEASURE and aggregation != Aggregation.NONE:
            return f"={aggregation.value.upper()}({dataset_name}.{field_name})"
        return f"=${dataset_name}.{field_name}"

    def _text_cell_xml(
        self,
        row: int,
        column: int,
        value: str,
        style_index: int,
        expand_direction: str = "down",
        col_span: int | None = None,
        row_span: int | None = None,
    ) -> str:
        expand_xml = self._expand_xml(expand_direction)
        span_attr = f' cs="{col_span}"' if col_span and col_span > 1 else ""
        row_span_attr = f' rs="{row_span}"' if row_span and row_span > 1 else ""
        return f"""<C c="{column}" r="{row}"{span_attr}{row_span_attr} s="{style_index}">
<O><![CDATA[{value}]]></O>
<PrivilegeControl/>
{expand_xml}
</C>"""

    def _dataset_cell_xml(
        self,
        row: int,
        column: int,
        dataset_name: str,
        field_name: str,
        style_index: int,
        expand_direction: str = "down",
        widget: CellWidgetDSL | None = None,
    ) -> str:
        expand_xml = self._expand_xml(expand_direction)
        widget_xml = self._cell_widget_xml(widget) if widget else ""
        return f"""<C c="{column}" r="{row}" s="{style_index}">
<O t="DSColumn">
<Attributes dsName="{escape(dataset_name)}" columnName="{escape(field_name)}"/>
<Complex/>
<RG class="com.fr.report.cell.cellattr.core.group.FunctionGrouper"/>
<Parameters/>
</O>
<PrivilegeControl/>
{widget_xml}
{expand_xml}
</C>"""

    def _row_action_button_cell_xml(self, row: int, column: int, button_class: str, text: str, icon_name: str, fixed_column: int) -> str:
        return f"""<C c="{column}" r="{row}" s="2">
<PrivilegeControl/>
<Widget class="com.fr.report.web.button.write.{button_class}">
<WidgetAttr description="">
<PrivilegeControl/>
</WidgetAttr>
<Text><![CDATA[{text}]]></Text>
<IconName><![CDATA[{icon_name}]]></IconName>
<FixCell row="{row}" col="{fixed_column}"/>
</Widget>
<Expand/>
</C>"""

    def _cell_widget_xml(self, widget: CellWidgetDSL) -> str:
        widget_type = widget.widgetType
        widget_name = escape(widget.widgetName or widget.field)
        if widget_type == "number":
            return """<Widget class="com.fr.form.ui.NumberEditor">
<WidgetAttr description="">
<PrivilegeControl/>
</WidgetAttr>
<NumberAttr>
<widgetValue/>
</NumberAttr>
</Widget>"""
        if widget_type == "date":
            return """<Widget class="com.fr.form.ui.DateEditor">
<WidgetAttr description="">
<PrivilegeControl/>
</WidgetAttr>
<DateAttr/>
<widgetValue/>
</Widget>"""
        if widget_type == "combo":
            dataset = escape(widget.dictionaryDataset or "ds_main")
            key_field = escape(widget.dictionaryKeyField or widget.field)
            value_field = escape(widget.dictionaryValueField or widget.field)
            return f"""<Widget class="com.fr.form.ui.ComboBox">
<WidgetName name="{widget_name}"/>
<WidgetAttr description="">
<PrivilegeControl/>
</WidgetAttr>
<Dictionary class="com.fr.data.impl.TableDataDictionary">
<FormulaDictAttr kiName="{key_field}" viName="{value_field}"/>
<TableDataDictAttr>
<TableData class="com.fr.data.impl.NameTableData"><Name><![CDATA[{dataset}]]></Name></TableData>
</TableDataDictAttr>
</Dictionary>
<widgetValue><O><![CDATA[]]></O></widgetValue>
</Widget>"""
        return f"""<Widget class="com.fr.form.ui.TextEditor">
<WidgetName name="{widget_name}"/>
<WidgetAttr aspectRatioLocked="false" aspectRatioBackup="-1.0" description="">
<MobileBookMark useBookMark="false" bookMarkName="" frozen="false" index="-1" oldWidgetName=""/>
<PrivilegeControl/>
</WidgetAttr>
<TextAttr/>
<Reg class="com.fr.form.ui.reg.NoneReg"/>
<widgetValue/>
<MobileScanCodeAttr scanCode="true" textInputMode="0" isSupportManual="true" isSupportScan="true" isSupportNFC="false" nfcContentType="0"/>
<MobileTextEditAttr allowOneClickClear="true"/>
</Widget>"""

    def _expand_xml(self, expand_direction: str) -> str:
        if expand_direction == "none":
            return "<Expand/>"
        dir_map = {"down": "0", "right": "1"}
        return f'<Expand dir="{dir_map.get(expand_direction, "0")}"/>'

    def _body_style_index(self, role: FieldRole, field_type: object, editable: bool = False) -> int:
        offset = 3 if editable else 0
        if role == FieldRole.MEASURE:
            return 3 + offset
        if str(field_type) in {"date", "datetime", "FieldType.DATE", "FieldType.DATETIME"}:
            return 4 + offset
        return 2 + offset

    def _column_width(self, width: int) -> int:
        return max(1524000, min(width * 38100, 7620000))

    def _layout_column_width(self, column: LayoutColumnDSL) -> int:
        if column.hidden:
            return 0
        return self._column_width(column.width)

    def _header_groups(self, dsl: ReportDSL) -> list[dict[str, object]]:
        groups = dsl.layout.designHints.get("headerGroups") if dsl.layout.designHints else None
        if not isinstance(groups, list):
            return []
        normalized: list[dict[str, object]] = []
        for group in groups:
            if not isinstance(group, dict):
                continue
            fields = group.get("fields")
            if not isinstance(fields, list) or not fields:
                continue
            normalized.append(
                {
                    "label": str(group.get("label") or ""),
                    "fields": [str(field) for field in fields],
                }
            )
        return normalized

    def _group_header_cells(
        self,
        columns: list[LayoutColumnDSL],
        groups: list[dict[str, object]],
        field_to_column: dict[str, int],
    ) -> list[str]:
        parts: list[str] = []
        field_names = {column.field for column in columns}
        for group in groups:
            label = str(group.get("label") or "")
            fields = [field for field in group.get("fields", []) if isinstance(field, str) and field in field_names]
            if not label or not fields:
                continue
            indexes = sorted(field_to_column[field] for field in fields)
            start = indexes[0]
            span = indexes[-1] - indexes[0] + 1
            parts.append(self._text_cell_xml(1, start, label, 1, expand_direction="none", col_span=span))
        return parts

    def _is_single_group_column(self, column: LayoutColumnDSL, groups: list[dict[str, object]]) -> bool:
        for group in groups:
            fields = group.get("fields")
            if not isinstance(fields, list) or column.field not in fields:
                continue
            return not str(group.get("label") or "")
        return True

    def _style_list_xml(self, template: FrReportStyleTemplate) -> str:
        return f"""<StyleList>
{self._style_xml(template.title, with_border=False)}
{self._style_xml(template.header, with_border=True)}
{self._style_xml(template.body_text, with_border=True)}
{self._style_xml(template.body_number, with_border=True)}
{self._style_xml(template.body_date, with_border=True)}
{self._editable_style_xml(template.body_text)}
{self._editable_style_xml(template.body_number)}
{self._editable_style_xml(template.body_date)}
</StyleList>"""

    def _editable_style_xml(self, style: FrReportAreaStyle) -> str:
        return self._style_xml(style, with_border=True)

    def _style_xml(self, style: FrReportAreaStyle, with_border: bool) -> str:
        background = (
            '<Background name="NullBackground"/>'
            if style.background_color.upper() == "#FFFFFF"
            else f"""<Background name="ColorBackground">
<color>
<FineColor color="{style.fr_background_color}" hor="-1" ver="-1"/>
</color>
</Background>"""
        )
        border = self._border_xml(style.fr_border_color) if with_border else "<Border/>"
        return f"""<Style horizontal_alignment="{style.horizontal_alignment}" vertical_alignment="{style.vertical_alignment}" imageLayout="1">
<FRFont name="{escape(style.text.font_family)}" style="{style.text.fr_font_style}" size="{style.text.font_size}"/>
{background}
{border}
</Style>"""

    def _border_xml(self, color: int) -> str:
        color_xml = f"""<color>
<FineColor color="{color}" hor="-1" ver="-1"/>
</color>"""
        return f"""<Border>
<Top style="1">
{color_xml}
</Top>
<Bottom style="1">
{color_xml}
</Bottom>
<Left style="1">
{color_xml}
</Left>
<Right style="1">
{color_xml}
</Right>
</Border>"""


cpt_generator = CptGenerator()
