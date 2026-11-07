from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.agent.insight.feishu_bitable_service import (
    BODY_CELL_BYTES,
    InsightFeishuBitableService,
)


def test_long_chinese_body_roundtrip_and_watermark():
    service = InsightFeishuBitableService()
    body = ("正文与链接 \n𠮷" * 20000) + "结尾"
    parts = service._split_body(body)
    assert len(parts) > 2
    assert all(len(part.encode("utf-8")) <= BODY_CELL_BYTES for part in parts)
    assert "".join(parts) == body
    fields = {service._body_field_name(i): [{"text": part}] for i, part in reversed(list(enumerate(parts)))}
    assert service._read_body_fields(fields) == body
    now = datetime.now()
    row = SimpleNamespace(id=1, content=body, create_time=now-timedelta(days=20), update_time=None)
    fields.update({"情报ID": "1", "同步时间": now.timestamp()*1000})
    assert service._select_incremental_rows([row], [{"fields": fields}]) == []
    row.content = ""
    assert service._select_incremental_rows([row], [{"fields": fields}]) == [row]


@pytest.mark.asyncio
async def test_continuation_fields_created_only_for_selected_body(monkeypatch):
    service = InsightFeishuBitableService()
    create = AsyncMock(side_effect=lambda spec: {"field_name": spec["label"], "type": 1})
    monkeypatch.setattr(service, "_create_field", create)
    monkeypatch.setattr(service, "_list_fields", AsyncMock(return_value=[]))
    records = [{"values": {"content": "中" * 80000}}]
    fields = [{"field_name": "正文", "type": 1}, {"field_name": "标题", "type": 1}]
    await service._ensure_fields(fields, records, ["title"], True)
    create.assert_not_awaited()
    result = await service._ensure_fields(fields, records, ["content"], True)
    assert result["created_fields"] == ["正文（续1）", "正文（续2）", "正文（续3）"]
    with pytest.raises(ValueError, match="长正文续列"):
        await service._ensure_fields(fields, records, ["content"], False)


@pytest.mark.asyncio
async def test_write_clears_old_tail_and_updates_duplicate_rows(monkeypatch):
    service = InsightFeishuBitableService()
    request = AsyncMock(return_value={})
    monkeypatch.setattr(service, "_request", request)
    records = [{"intelligence_id": 1, "title": "标题", "values": {"intelligence_id": "1", "content": "新正文"}}]
    fields = [{"field_name": name, "type": 1} for name in ["情报ID", "正文", "正文（续1）"]]
    old = [{"record_id": i, "fields": {"情报ID": "1"}} for i in ["a", "b"]]
    result = await service._write_records(records, fields, old, update_existing=True)
    assert result["updated_count"] == 2
    written = request.await_args.kwargs["json"]["records"]
    assert all(record["fields"]["正文（续1）"] == "" for record in written)
    assert all(record["fields"]["正文"] == "新正文" for record in written)


@pytest.mark.asyncio
async def test_rejected_cell_does_not_block_other_records(monkeypatch):
    service = InsightFeishuBitableService()
    written = []

    async def request(method, path, *, json):
        if any(record["fields"]["情报ID"] == "bad" for record in json["records"]):
            raise ValueError("TooLargeCell")
        written.extend(json["records"])

    monkeypatch.setattr(service, "_request", request)
    errors = []
    count = await service._write_batch([{"fields": {"情报ID": key}} for key in ["1", "bad", "3"]], "batch_update", errors)
    assert count == len(written) == 2
    assert errors[0]["intelligence_id"] == "bad"
    monkeypatch.setattr(service, "_request", AsyncMock(side_effect=ValueError("ReadTimeout")))
    with pytest.raises(ValueError, match="ReadTimeout"):
        await service._write_batch([{"fields": {"情报ID": "1"}}], "batch_create", [])
    assert service._request.await_count == 1


def test_record_batch_has_byte_budget():
    service = InsightFeishuBitableService()
    records = [{"fields": {"正文": "中" * 25000}} for _ in range(200)]
    batches = list(service._record_batches(records))
    assert len(batches) > 1
    assert sum(map(len, batches)) == 200
    assert all(len(chunk) < 60 for chunk in batches)
