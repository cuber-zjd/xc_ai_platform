from html import escape

from app.core.config import settings
from app.schemas.agent.fr_report.report_dsl import Aggregation, FieldRole, ReportDSL


class CptGenerator:
    def generate(self, dsl: ReportDSL) -> bytes:
        dataset = dsl.datasets[0]
        cells = self._cells_xml(dsl)
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
</ReportParameterAttr>
<Report class="com.fr.report.worksheet.WorkSheet" name="{escape(dsl.reportName)}">
<ReportPageAttr>
<HR/>
<FR/>
</ReportPageAttr>
<Table rows="{len(dsl.layout.columns) + 2}" columns="{max(len(dsl.layout.columns), 1)}">
{cells}
</Table>
</Report>
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
        for index, column in enumerate(columns, start=1):
            parts.append(self._cell_xml(1, index, column.title, "title"))
        for index, column in enumerate(columns, start=1):
            expression = self._field_expression(dsl.layout.dataset, column.field, column.role, column.aggregation)
            parts.append(self._cell_xml(2, index, expression, "field", column.expandDirection))
        return "\n".join(parts)

    def _field_expression(self, dataset_name: str, field_name: str, role: FieldRole, aggregation: Aggregation) -> str:
        if role == FieldRole.MEASURE and aggregation != Aggregation.NONE:
            return f"={aggregation.value.upper()}({dataset_name}.{field_name})"
        return f"=${dataset_name}.{field_name}"

    def _cell_xml(
        self,
        row: int,
        column: int,
        value: str,
        cell_type: str,
        expand_direction: str = "down",
    ) -> str:
        style = "header" if cell_type == "title" else "body"
        expand_xml = "" if expand_direction == "none" else f'<Expand dir="{escape(expand_direction)}"/>'
        return f"""<Cell row="{row}" column="{column}">
<O><![CDATA[{value}]]></O>
<PrivilegeControl/>
{expand_xml}
<Style name="{style}"/>
</Cell>"""


cpt_generator = CptGenerator()
