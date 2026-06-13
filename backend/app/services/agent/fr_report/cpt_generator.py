from html import escape

from app.core.config import settings
from app.schemas.agent.fr_report.report_dsl import Aggregation, FieldRole, FieldType, LayoutColumnDSL, ParameterDSL, ReportDSL


class CptGenerator:
    def generate(self, dsl: ReportDSL) -> bytes:
        dataset = dsl.datasets[0]
        cells = self._cells_xml(dsl)
        style_list = self._style_list_xml()
        has_groups = self._header_groups(dsl)
        rows = (4 if has_groups else 3) if dsl.layout.columns else 1
        columns = max(len(dsl.layout.columns), 1)
        row_heights = ",".join(["1152000", "720000", "720000", "723900"][:rows])
        column_widths = ",".join(str(self._column_width(column.width)) for column in dsl.layout.columns) or "2743200"
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
<RowHeight defaultValue="723900"><![CDATA[{row_heights}]]></RowHeight>
<ColumnWidth defaultValue="2743200"><![CDATA[{column_widths}]]></ColumnWidth>
<CellElementList>
{cells}
</CellElementList>
</Table>
</Report>
{style_list}
<DesignerVersion DesignerVersion="KAA"/>
<PreviewType PreviewType="0"/>
</WorkBook>
"""
        return xml.encode("utf-8")

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
        title = dsl.reportMeta.title or dsl.reportName
        if columns:
            parts.append(self._text_cell_xml(0, 0, title, 0, col_span=len(columns)))
        groups = self._header_groups(dsl)
        header_row = 2 if groups else 1
        data_row = header_row + 1
        if groups:
            parts.extend(self._group_header_cells(columns, groups))
        for index, column in enumerate(columns):
            row_span = 2 if groups and self._is_single_group_column(column, groups) else None
            actual_row = 1 if row_span else header_row
            parts.append(self._text_cell_xml(actual_row, index, column.title, 1, expand_direction="none", row_span=row_span))
        for index, column in enumerate(columns):
            if column.role == FieldRole.MEASURE and column.aggregation != Aggregation.NONE:
                expression = self._field_expression(dsl.layout.dataset, column.field, column.role, column.aggregation)
                parts.append(self._text_cell_xml(data_row, index, expression, self._body_style_index(column.role, column.type), column.expandDirection))
            else:
                parts.append(
                    self._dataset_cell_xml(
                        data_row,
                        index,
                        dsl.layout.dataset,
                        column.field,
                        self._body_style_index(column.role, column.type),
                        column.expandDirection,
                    )
                )
        return "\n".join(parts)

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
    ) -> str:
        expand_xml = self._expand_xml(expand_direction)
        return f"""<C c="{column}" r="{row}" s="{style_index}">
<O t="DSColumn">
<Attributes dsName="{escape(dataset_name)}" columnName="{escape(field_name)}"/>
<Complex/>
<RG class="com.fr.report.cell.cellattr.core.group.FunctionGrouper"/>
<Parameters/>
</O>
<PrivilegeControl/>
{expand_xml}
</C>"""

    def _expand_xml(self, expand_direction: str) -> str:
        if expand_direction == "none":
            return "<Expand/>"
        dir_map = {"down": "0", "right": "1"}
        return f'<Expand dir="{dir_map.get(expand_direction, "0")}"/>'

    def _body_style_index(self, role: FieldRole, field_type: object) -> int:
        if role == FieldRole.MEASURE:
            return 3
        if str(field_type) in {"date", "datetime", "FieldType.DATE", "FieldType.DATETIME"}:
            return 4
        return 2

    def _column_width(self, width: int) -> int:
        return max(1524000, min(width * 38100, 7620000))

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

    def _group_header_cells(self, columns: list[LayoutColumnDSL], groups: list[dict[str, object]]) -> list[str]:
        parts: list[str] = []
        field_to_index = {column.field: index for index, column in enumerate(columns)}
        for group in groups:
            label = str(group.get("label") or "")
            fields = [field for field in group.get("fields", []) if isinstance(field, str) and field in field_to_index]
            if not label or not fields:
                continue
            indexes = sorted(field_to_index[field] for field in fields)
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

    def _style_list_xml(self) -> str:
        return """<StyleList>
<Style horizontal_alignment="0" vertical_alignment="1" imageLayout="1">
<FRFont name="SimSun" style="1" size="112"/>
<Background name="NullBackground"/>
<Border/>
</Style>
<Style horizontal_alignment="0" vertical_alignment="1" imageLayout="1">
<FRFont name="SimSun" style="1" size="88"/>
<Background name="ColorBackground" color="-984833"/>
<Border>
<Top style="1"/>
<Bottom style="1"/>
<Left style="1"/>
<Right style="1"/>
</Border>
</Style>
<Style horizontal_alignment="0" vertical_alignment="1" imageLayout="1">
<FRFont name="SimSun" style="0" size="88"/>
<Background name="NullBackground"/>
<Border>
<Top style="1"/>
<Bottom style="1"/>
<Left style="1"/>
<Right style="1"/>
</Border>
</Style>
<Style horizontal_alignment="2" vertical_alignment="1" imageLayout="1">
<FRFont name="SimSun" style="0" size="88"/>
<Background name="NullBackground"/>
<Border>
<Top style="1"/>
<Bottom style="1"/>
<Left style="1"/>
<Right style="1"/>
</Border>
</Style>
<Style horizontal_alignment="0" vertical_alignment="1" imageLayout="1">
<FRFont name="SimSun" style="0" size="88"/>
<Background name="NullBackground"/>
<Border>
<Top style="1"/>
<Bottom style="1"/>
<Left style="1"/>
<Right style="1"/>
</Border>
</Style>
</StyleList>"""


cpt_generator = CptGenerator()
