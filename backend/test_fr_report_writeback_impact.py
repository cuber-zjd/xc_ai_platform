from app.services.agent.fr_report.high_authority_agent_service import FrReportHighAuthorityAgentService


def test_date_display_change_updates_writeback_concat_formula() -> None:
    service = FrReportHighAuthorityAgentService()
    xml = (
        '<WorkBook><Report>'
        '<C c="1" r="4"><O t="DSColumn"><Attributes dsName="data" columnName="month_day"/></O></C>'
        "<ReportWriteAttr><SubmitVisitor><DMLConfig>"
        '<ColumnConfig name="record_date"><O t="Formula"><![CDATA[CONCATENATE(A5,B5)]]></O></ColumnConfig>'
        "</DMLConfig></SubmitVisitor></ReportWriteAttr>"
        "</Report></WorkBook>"
    )

    next_xml, warnings = service._normalize_writeback_after_presentation_change(
        source_xml=xml,
        candidate_xml=xml,
        request="第二列日期显示为yyyy年MM月dd日",
    )

    assert "CONCATENATE(A5,B5)" not in next_xml
    assert "<![CDATA[B5]]>" in next_xml
    assert warnings
