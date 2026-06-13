from app.services.agent.sap_assistant.rfc_client import SapRfcClient


def test_normalize_result_reports_json_parse_context_for_unescaped_quote() -> None:
    client = SapRfcClient()
    result = client._normalize_result(
        {
            "ET_JSON_LINES": [
                {
                    "LINE": (
                        '{"success":true,"object":"VBRK","fields":['
                        '{"fieldname":"VBELN","ddtext":"销售 "凭证" 编号"}]}'
                    )
                }
            ]
        }
    )

    assert result["JSON_PARSE_ERROR"]
    assert "Expecting ',' delimiter" in result["JSON_PARSE_ERROR_DETAIL"]
    assert "双引号没有转义" in result["JSON_PARSE_ERROR_HINT"]
    assert result["JSON_PARSE_ERROR_CONTEXT"]["markerOffset"] >= 0


def test_normalize_result_repairs_bare_control_char_in_json_string() -> None:
    client = SapRfcClient()
    result = client._normalize_result(
        {
            "ET_JSON_LINES": [
                {
                    "LINE": (
                        '{"success":true,"object":"VBRK","fields":['
                        '{"fieldname":"VBELN","ddtext":"销售\n凭证"}]}'
                    )
                }
            ]
        }
    )

    assert result["JSON_PARSED"]["fields"][0]["ddtext"] == "销售\n凭证"
    assert result["JSON_REPAIR_NOTE"]


def test_normalize_result_repairs_leading_zero_numbers_outside_strings() -> None:
    client = SapRfcClient()
    result = client._normalize_result(
        {
            "ET_JSON_LINES": [
                {
                    "LINE": (
                        '{"success":true,"object":"KONP","fields":['
                        '{"fieldname":"MANDT","rollname":"MANDT","datatype":"CLNT",'
                        '"leng":000003,"decimals":000000,'
                        '"sample":"000003 should stay text"}]}'
                    )
                }
            ]
        }
    )

    field = result["JSON_PARSED"]["fields"][0]
    assert field["leng"] == 3
    assert field["decimals"] == 0
    assert field["sample"] == "000003 should stay text"
    assert result["JSON_REPAIR_NOTE"]
