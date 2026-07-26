from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import datetime
from typing import Any
from uuid import uuid4

import httpx
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.models.agent.insight import (
    InsightIntelligence,
    InsightIntelligenceAsset,
    InsightIntelligenceSource,
    InsightIntelligenceTag,
    InsightCompany,
    InsightMonitorConfig,
    InsightTag,
    InsightTask,
    InsightTaskStatus,
)
from app.models.system.sys_company import SysCompany
from app.schemas.agent.insight.feishu import (
    InsightFeishuFieldOption,
    InsightFeishuSyncOptionsRead,
    InsightFeishuSyncRequest,
    InsightFeishuSyncResponse,
)


FIELD_SPECS = [
    {"code": "intelligence_id", "label": "情报ID", "field_type": 1, "required": True, "default_selected": True},
    {"code": "title", "label": "标题", "field_type": 1, "required": False, "default_selected": True},
    {"code": "summary", "label": "摘要", "field_type": 1, "required": False, "default_selected": True},
    {"code": "content", "label": "正文", "field_type": 1, "required": False, "default_selected": False},
    {"code": "publish_time", "label": "发布时间", "field_type": 5, "required": False, "default_selected": True},
    {"code": "capture_time", "label": "入库时间", "field_type": 5, "required": False, "default_selected": True},
    {"code": "subject_name", "label": "企业/监测对象", "field_type": 1, "required": False, "default_selected": True},
    {"code": "sys_company_name", "label": "所属公司", "field_type": 4, "required": False, "default_selected": True},
    {"code": "category", "label": "分类", "field_type": 3, "required": False, "default_selected": True},
    {"code": "tags", "label": "标签", "field_type": 4, "required": False, "default_selected": True},
    {"code": "importance", "label": "重要性", "field_type": 3, "required": False, "default_selected": True},
    {"code": "selection_reason", "label": "选中理由", "field_type": 1, "required": False, "default_selected": True},
    {"code": "business_insight", "label": "业务启示", "field_type": 1, "required": False, "default_selected": True},
    {"code": "risk_opportunity", "label": "风险/机会", "field_type": 1, "required": False, "default_selected": True},
    {"code": "source_channel", "label": "来源渠道", "field_type": 3, "required": False, "default_selected": True},
    {"code": "source_url", "label": "原文链接", "field_type": 15, "required": False, "default_selected": True},
    {"code": "platform_url", "label": "平台详情链接", "field_type": 15, "required": False, "default_selected": True},
    {"code": "sync_time", "label": "同步时间", "field_type": 5, "required": False, "default_selected": True},
]


class InsightFeishuBitableService:
    def __init__(self) -> None:
        self._tenant_token: str | None = None
        self._tenant_token_expires_at = 0.0

    def get_options(self) -> InsightFeishuSyncOptionsRead:
        configured = all(
            [
                settings.FEISHU_APP_ID,
                settings.FEISHU_APP_SECRET,
                settings.INSIGHT_FEISHU_BITABLE_APP_TOKEN,
                settings.INSIGHT_FEISHU_BITABLE_TABLE_ID,
            ]
        )
        warnings: list[str] = []
        if not configured:
            warnings.append("飞书应用或多维表格配置不完整")
        if not settings.INSIGHT_FEISHU_SYNC_ENABLED:
            warnings.append("后台自动同步未开启，当前仍可手动同步")
        return InsightFeishuSyncOptionsRead(
            configured=configured,
            enabled=bool(configured),
            fields=[InsightFeishuFieldOption(**item) for item in FIELD_SPECS],
            warnings=warnings,
        )

    async def sync_intelligences(
        self,
        db: AsyncSession,
        payload: InsightFeishuSyncRequest,
        *,
        user_id: int,
        is_admin: bool,
    ) -> InsightFeishuSyncResponse:
        options = self.get_options()
        if not options.enabled:
            raise ValueError("飞书多维表格同步尚未启用或配置不完整")

        task = InsightTask(
            task_uid=f"insight_feishu_sync_{uuid4().hex}",
            task_type="feishu_bitable_sync",
            status=InsightTaskStatus.RUNNING,
            progress=10,
            started_at=datetime.now(),
            input_payload=payload.model_dump(mode="json") | {"user_id": user_id},
            create_by=str(user_id),
            update_by=str(user_id),
        )
        db.add(task)
        await db.commit()
        await db.refresh(task)
        task_id = task.id

        try:
            selected_codes = self._selected_field_codes(payload.field_codes)
            rows = await self._load_intelligences(db, payload, user_id=user_id, is_admin=is_admin)
            record_payloads = await self._build_record_payloads(db, rows, selected_codes)
            fields = await self._list_fields()
            metadata_result = await self._ensure_fields(fields, record_payloads, selected_codes, payload.ensure_metadata)
            fields = metadata_result["fields"]
            existing_records = await self._list_records()
            result = await self._write_records(
                record_payloads,
                fields,
                existing_records,
                update_existing=payload.update_existing,
            )
            response = InsightFeishuSyncResponse(
                task_id=task.id or 0,
                requested_count=len(payload.intelligence_ids) if payload.scope == "selected" else len(rows),
                eligible_count=len(rows),
                created_count=result["created_count"],
                updated_count=result["updated_count"],
                skipped_count=result["skipped_count"],
                failed_count=len(result["errors"]),
                metadata_created_fields=metadata_result["created_fields"],
                metadata_updated_fields=metadata_result["updated_fields"],
                warnings=metadata_result["warnings"],
                errors=result["errors"][:50],
            )
            task.status = InsightTaskStatus.SUCCESS if response.failed_count == 0 else InsightTaskStatus.FAILED
            task.progress = 100
            task.finished_at = datetime.now()
            task.output_payload = response.model_dump(mode="json")
            task.error_message = None if response.failed_count == 0 else f"{response.failed_count} 条记录同步失败"
            task.update_time = datetime.now()
            db.add(task)
            await db.commit()
            return response
        except Exception as exc:
            await db.rollback()
            failed_task = await db.get(InsightTask, task_id) if task_id else None
            if failed_task:
                error_message = self._exception_message(exc)
                failed_task.status = InsightTaskStatus.FAILED
                failed_task.progress = 100
                failed_task.finished_at = datetime.now()
                failed_task.error_message = error_message[:1000]
                failed_task.output_payload = {"error": error_message}
                failed_task.update_time = datetime.now()
                db.add(failed_task)
                await db.commit()
            raise

    def _selected_field_codes(self, values: list[str]) -> list[str]:
        supported = {item["code"] for item in FIELD_SPECS}
        selected = [item for item in values if item in supported]
        if not selected:
            selected = [item["code"] for item in FIELD_SPECS if item["default_selected"]]
        if "intelligence_id" not in selected:
            selected.insert(0, "intelligence_id")
        return list(dict.fromkeys(selected))

    async def _load_intelligences(
        self,
        db: AsyncSession,
        payload: InsightFeishuSyncRequest,
        *,
        user_id: int,
        is_admin: bool,
    ) -> list[InsightIntelligence]:
        filters = [
            InsightIntelligence.is_deleted == 0,
            InsightIntelligence.status == "active",
        ]
        if payload.scope == "selected":
            filters.append(InsightIntelligence.id.in_(payload.intelligence_ids))
        else:
            filters.extend(
                [
                    InsightIntelligence.publish_time >= payload.date_from,
                    InsightIntelligence.publish_time <= payload.date_to,
                ]
            )
        if not is_admin:
            from app.services.agent.insight.intelligence_service import insight_intelligence_service

            visible_ids = await insight_intelligence_service._get_visible_intelligence_ids(db, user_id)  # noqa: SLF001
            if not visible_ids:
                return []
            filters.append(InsightIntelligence.id.in_(visible_ids))
        return list(
            (
                await db.exec(
                    select(InsightIntelligence)
                    .where(*filters)
                    .order_by(InsightIntelligence.publish_time.desc().nullslast(), InsightIntelligence.id.desc())
                    .limit(2000)
                )
            ).all()
        )

    async def _build_record_payloads(
        self,
        db: AsyncSession,
        rows: list[InsightIntelligence],
        selected_codes: list[str],
    ) -> list[dict[str, Any]]:
        if not rows:
            return []
        ids = [row.id for row in rows if row.id]
        sources = list(
            (
                await db.exec(
                    select(InsightIntelligenceSource)
                    .where(
                        InsightIntelligenceSource.intelligence_id.in_(ids),
                        InsightIntelligenceSource.is_deleted == 0,
                    )
                    .order_by(InsightIntelligenceSource.id.asc())
                )
            ).all()
        )
        assets = list(
            (
                await db.exec(
                    select(InsightIntelligenceAsset).where(
                        InsightIntelligenceAsset.intelligence_id.in_(ids),
                        InsightIntelligenceAsset.is_deleted == 0,
                    )
                )
            ).all()
        )
        company_ids = {row.company_id for row in rows if row.company_id}
        monitor_config_ids = {row.monitor_config_id for row in rows if row.monitor_config_id}
        companies = (
            list(
                (
                    await db.exec(
                        select(InsightCompany).where(
                            InsightCompany.id.in_(company_ids),
                            InsightCompany.is_deleted == 0,
                        )
                    )
                ).all()
            )
            if company_ids
            else []
        )
        sys_company_ids = {row.sys_company_id for row in companies if row.sys_company_id}
        monitor_configs = (
            list(
                (
                    await db.exec(
                        select(InsightMonitorConfig).where(
                            InsightMonitorConfig.id.in_(monitor_config_ids),
                            InsightMonitorConfig.is_deleted == 0,
                        )
                    )
                ).all()
            )
            if monitor_config_ids
            else []
        )
        for monitor_config in monitor_configs:
            configured_ids = (monitor_config.config_json or {}).get("business_sys_company_ids") or []
            sys_company_ids.update(int(item) for item in configured_ids if str(item).isdigit())
        sys_companies = (
            list(
                (
                    await db.exec(
                        select(SysCompany).where(
                            SysCompany.id.in_(sys_company_ids),
                            SysCompany.is_deleted == 0,
                        )
                    )
                ).all()
            )
            if sys_company_ids
            else []
        )
        tag_rows = list(
            (
                await db.exec(
                    select(InsightIntelligenceTag, InsightTag)
                    .join(InsightTag, InsightTag.id == InsightIntelligenceTag.tag_id)
                    .where(
                        InsightIntelligenceTag.intelligence_id.in_(ids),
                        InsightIntelligenceTag.is_deleted == 0,
                        InsightTag.is_deleted == 0,
                        InsightTag.status == "active",
                    )
                )
            ).all()
        )
        source_by_intelligence: dict[int, InsightIntelligenceSource] = {}
        for source in sources:
            source_by_intelligence.setdefault(source.intelligence_id, source)
        asset_by_intelligence = {item.intelligence_id: item for item in assets if item.intelligence_id}
        company_by_id = {item.id: item for item in companies if item.id}
        monitor_config_by_id = {item.id: item for item in monitor_configs if item.id}
        sys_company_by_id = {item.id: item for item in sys_companies if item.id}
        tags_by_intelligence: dict[int, list[str]] = defaultdict(list)
        categories_by_intelligence: dict[int, list[str]] = defaultdict(list)
        for relation, tag in tag_rows:
            tags_by_intelligence[relation.intelligence_id].append(tag.tag_name)
            if tag.tag_type:
                categories_by_intelligence[relation.intelligence_id].append(tag.tag_type)

        now = datetime.now()
        result: list[dict[str, Any]] = []
        for row in rows:
            if not row.id:
                continue
            source = source_by_intelligence.get(row.id)
            asset = asset_by_intelligence.get(row.id)
            review_payload = (asset.review_payload if asset else None) or {}
            raw_payload = row.raw_payload or {}
            company = company_by_id.get(row.company_id)
            sys_company = sys_company_by_id.get(company.sys_company_id) if company else None
            monitor_config = monitor_config_by_id.get(row.monitor_config_id)
            raw_configured_company_ids = (
                (monitor_config.config_json or {}).get("business_sys_company_ids") if monitor_config else []
            )
            configured_company_ids = [
                int(item) for item in raw_configured_company_ids or [] if str(item).isdigit()
            ]
            configured_company_names = [
                sys_company_by_id[company_id].name
                for company_id in configured_company_ids or []
                if company_id in sys_company_by_id
            ]
            business_company_names = [sys_company.name] if sys_company else configured_company_names
            opportunities = (asset.opportunities if asset else []) or self._string_list(review_payload.get("opportunities"))
            risks = (asset.risks if asset else []) or self._string_list(review_payload.get("risks"))
            values = {
                "intelligence_id": str(row.id),
                "title": row.title,
                "summary": row.summary or "",
                "content": row.content or "",
                "publish_time": row.publish_time,
                "capture_time": row.capture_time or row.create_time,
                "subject_name": row.subject_name or "",
                "sys_company_name": list(dict.fromkeys(business_company_names)) or ["未归属"],
                "category": self._first_text(raw_payload.get("category_name"), row.intelligence_type),
                "tags": list(dict.fromkeys(tags_by_intelligence.get(row.id, []))),
                "importance": self._importance_label(row.importance_level),
                "selection_reason": self._first_text(
                    review_payload.get("reason"),
                    raw_payload.get("selection_reason"),
                    raw_payload.get("review_reason"),
                ),
                "business_insight": self._first_text(
                    review_payload.get("business_insight"),
                    review_payload.get("business_value"),
                    raw_payload.get("business_insight"),
                ),
                "risk_opportunity": self._join_sections(opportunities, risks),
                "source_channel": self._first_text(
                    asset.source_channel if asset else None,
                    source.source_type if source else None,
                ),
                "source_url": source.source_url if source else (asset.source_url if asset else None),
                "platform_url": f"{settings.INSIGHT_PUBLIC_BASE_URL.rstrip('/')}/insight/intelligence/{row.id}",
                "sync_time": now,
            }
            result.append({"intelligence_id": row.id, "title": row.title, "values": {key: values.get(key) for key in selected_codes}})
        return result

    async def build_export_rows(
        self,
        db: AsyncSession,
        rows: list[InsightIntelligence],
        field_codes: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """复用情报字段归属和来源整理逻辑，不调用飞书接口。"""
        selected_codes = self._selected_field_codes(field_codes or [item["code"] for item in FIELD_SPECS])
        return await self._build_record_payloads(db, rows, selected_codes)

    async def _ensure_fields(
        self,
        fields: list[dict[str, Any]],
        records: list[dict[str, Any]],
        selected_codes: list[str],
        enabled: bool,
    ) -> dict[str, Any]:
        by_name = {str(item.get("field_name") or ""): item for item in fields}
        created_fields: list[str] = []
        updated_fields: list[str] = []
        warnings: list[str] = []
        specs = {item["code"]: item for item in FIELD_SPECS}

        for code in selected_codes:
            spec = specs[code]
            field = by_name.get(spec["label"])
            if field is None:
                if not enabled:
                    raise ValueError(f"飞书多维表格缺少字段：{spec['label']}")
                field = await self._create_field(spec)
                by_name[spec["label"]] = field
                created_fields.append(spec["label"])
            actual_type = int(field.get("type") or 1)
            if actual_type != spec["field_type"]:
                if enabled and spec["field_type"] == 1 and actual_type in {3, 4}:
                    field = await self._convert_field_to_text(field)
                    by_name[spec["label"]] = field
                    actual_type = 1
                    updated_fields.append(spec["label"])
                elif enabled and spec["field_type"] in {3, 4} and actual_type in {3, 4}:
                    field = await self._convert_selection_field_type(field, spec["field_type"])
                    by_name[spec["label"]] = field
                    actual_type = spec["field_type"]
                    updated_fields.append(spec["label"])
                else:
                    warnings.append(f"字段“{spec['label']}”当前类型与推荐类型不同，已按现有类型写入，未自动转换历史字段")

            if enabled and actual_type == spec["field_type"] and spec["field_type"] in {3, 4}:
                values = self._field_option_values(records, code)
                if values and await self._extend_field_options(field, values):
                    updated_fields.append(spec["label"])

        refreshed = await self._list_fields() if created_fields or updated_fields else fields
        return {
            "fields": refreshed,
            "created_fields": created_fields,
            "updated_fields": updated_fields,
            "warnings": warnings,
        }

    async def _create_field(self, spec: dict[str, Any]) -> dict[str, Any]:
        body: dict[str, Any] = {"field_name": spec["label"], "type": spec["field_type"]}
        if spec["field_type"] in {3, 4}:
            body["property"] = {"options": []}
        data = await self._request("POST", self._fields_path(), json=body)
        return data.get("field") or data

    async def _extend_field_options(self, field: dict[str, Any], values: list[str]) -> bool:
        property_payload = field.get("property") if isinstance(field.get("property"), dict) else {}
        current_options = list(property_payload.get("options") or [])
        current_names = {str(item.get("name") or "") for item in current_options if isinstance(item, dict)}
        additions = [value for value in values if value and value not in current_names]
        if not additions:
            return False
        body = {
            "field_name": field.get("field_name"),
            "type": int(field.get("type") or 1),
            "property": {"options": [*current_options, *({"name": value} for value in additions)]},
        }
        await self._request("PUT", f"{self._fields_path()}/{field['field_id']}", json=body)
        return True

    async def _convert_field_to_text(self, field: dict[str, Any]) -> dict[str, Any]:
        body = {"field_name": field.get("field_name"), "type": 1}
        data = await self._request("PUT", f"{self._fields_path()}/{field['field_id']}", json=body)
        return data.get("field") or data

    async def _convert_selection_field_type(self, field: dict[str, Any], field_type: int) -> dict[str, Any]:
        property_payload = field.get("property") if isinstance(field.get("property"), dict) else {}
        body = {
            "field_name": field.get("field_name"),
            "type": field_type,
            "property": {"options": list(property_payload.get("options") or [])},
        }
        data = await self._request("PUT", f"{self._fields_path()}/{field['field_id']}", json=body)
        return data.get("field") or data

    async def _write_records(
        self,
        records: list[dict[str, Any]],
        fields: list[dict[str, Any]],
        existing_records: list[dict[str, Any]],
        *,
        update_existing: bool,
    ) -> dict[str, Any]:
        fields_by_name = {str(item.get("field_name") or ""): item for item in fields}
        existing_by_id: dict[str, str] = {}
        for item in existing_records:
            value = (item.get("fields") or {}).get("情报ID")
            normalized = self._normalize_text_value(value)
            if normalized:
                existing_by_id[normalized] = str(item.get("record_id") or "")

        creates: list[dict[str, Any]] = []
        updates: list[dict[str, Any]] = []
        skipped_count = 0
        errors: list[dict[str, Any]] = []
        specs = {item["code"]: item for item in FIELD_SPECS}
        for item in records:
            try:
                feishu_fields = {
                    specs[code]["label"]: self._adapt_field_value(
                        value,
                        fields_by_name.get(specs[code]["label"], {}),
                        title=item["title"],
                    )
                    for code, value in item["values"].items()
                    if code in specs
                }
                record_id = existing_by_id.get(str(item["intelligence_id"]))
                if record_id and update_existing:
                    updates.append({"record_id": record_id, "fields": feishu_fields})
                elif record_id:
                    skipped_count += 1
                else:
                    creates.append({"fields": feishu_fields})
            except Exception as exc:
                errors.append({"intelligence_id": item["intelligence_id"], "title": item["title"], "error": str(exc)[:500]})

        for chunk in self._chunks(creates, 500):
            await self._request("POST", f"{self._records_path()}/batch_create", json={"records": chunk})
        for chunk in self._chunks(updates, 500):
            await self._request("POST", f"{self._records_path()}/batch_update", json={"records": chunk})
        return {
            "created_count": len(creates),
            "updated_count": len(updates),
            "skipped_count": skipped_count,
            "errors": errors,
        }

    async def _list_fields(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        page_token: str | None = None
        while True:
            params: dict[str, Any] = {"page_size": 100}
            if page_token:
                params["page_token"] = page_token
            data = await self._request("GET", self._fields_path(), params=params)
            items.extend(item for item in (data.get("items") or []) if isinstance(item, dict))
            if not data.get("has_more"):
                return items
            page_token = data.get("page_token")

    async def _list_records(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        page_token: str | None = None
        while True:
            params: dict[str, Any] = {"page_size": 500}
            if page_token:
                params["page_token"] = page_token
            data = await self._request("GET", self._records_path(), params=params)
            items.extend(item for item in (data.get("items") or []) if isinstance(item, dict))
            if not data.get("has_more"):
                return items
            page_token = data.get("page_token")

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        token = await self._get_tenant_token()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        attempts = max(settings.FEISHU_RETRY_MAX_ATTEMPTS, 1)
        last_error: Exception | None = None
        for attempt in range(attempts):
            try:
                async with httpx.AsyncClient(timeout=max(settings.FEISHU_TIMEOUT_SECONDS, 5)) as client:
                    response = await client.request(
                        method,
                        f"{settings.FEISHU_BASE_URL.rstrip('/')}{path}",
                        params=params,
                        json=json,
                        headers=headers,
                    )
                response.raise_for_status()
                payload = response.json()
                if int(payload.get("code") or 0) != 0:
                    raise ValueError(f"飞书接口返回失败：{payload.get('msg') or payload.get('message') or payload.get('code')}")
                data = payload.get("data")
                return data if isinstance(data, dict) else {}
            except (httpx.HTTPError, ValueError) as exc:
                last_error = exc
                if attempt + 1 < attempts:
                    await asyncio.sleep(min(2**attempt, 4))
        if last_error:
            raise ValueError(f"飞书接口调用失败（{method} {path}）：{self._exception_message(last_error)}")
        raise ValueError(f"飞书接口调用失败（{method} {path}）")

    async def _get_tenant_token(self) -> str:
        now = asyncio.get_running_loop().time()
        if self._tenant_token and now < self._tenant_token_expires_at:
            return self._tenant_token
        try:
            async with httpx.AsyncClient(timeout=max(settings.FEISHU_TIMEOUT_SECONDS, 5)) as client:
                response = await client.post(
                    f"{settings.FEISHU_BASE_URL.rstrip('/')}/open-apis/auth/v3/tenant_access_token/internal",
                    json={"app_id": settings.FEISHU_APP_ID, "app_secret": settings.FEISHU_APP_SECRET},
                )
        except httpx.HTTPError as exc:
            raise ValueError(f"获取飞书访问凭证失败：{self._exception_message(exc)}") from exc
        response.raise_for_status()
        payload = response.json()
        if int(payload.get("code") or 0) != 0 or not payload.get("tenant_access_token"):
            raise ValueError(f"获取飞书访问凭证失败：{payload.get('msg') or payload.get('code')}")
        self._tenant_token = str(payload["tenant_access_token"])
        self._tenant_token_expires_at = now + max(int(payload.get("expire") or 7200) - 120, 60)
        return self._tenant_token

    def _fields_path(self) -> str:
        return (
            "/open-apis/bitable/v1/apps/"
            f"{settings.INSIGHT_FEISHU_BITABLE_APP_TOKEN}/tables/"
            f"{settings.INSIGHT_FEISHU_BITABLE_TABLE_ID}/fields"
        )

    def _records_path(self) -> str:
        return (
            "/open-apis/bitable/v1/apps/"
            f"{settings.INSIGHT_FEISHU_BITABLE_APP_TOKEN}/tables/"
            f"{settings.INSIGHT_FEISHU_BITABLE_TABLE_ID}/records"
        )

    def _adapt_field_value(self, value: Any, field: dict[str, Any], *, title: str) -> Any:
        field_type = int(field.get("type") or 1)
        if value is None:
            return None
        if field_type == 5:
            if isinstance(value, datetime):
                return int(value.timestamp() * 1000)
            return value
        if field_type == 15:
            text = str(value).strip()
            return {"link": text, "text": title[:100]} if text else None
        if field_type == 4:
            return value if isinstance(value, list) else [str(value)]
        if field_type == 3:
            if isinstance(value, list):
                return str(value[0]) if value else None
            return str(value) if value != "" else None
        if isinstance(value, list):
            return "、".join(str(item) for item in value if str(item).strip())
        if isinstance(value, datetime):
            return value.strftime("%Y-%m-%d %H:%M:%S")
        return str(value)

    def _field_option_values(self, records: list[dict[str, Any]], code: str) -> list[str]:
        values: list[str] = []
        for item in records:
            value = item["values"].get(code)
            candidates = value if isinstance(value, list) else [value]
            for candidate in candidates:
                text = str(candidate or "").strip()
                if text and text not in values:
                    values.append(text)
        return values[:500]

    def _importance_label(self, value: str | None) -> str:
        return {"high": "高", "medium": "中", "low": "低"}.get(str(value or "").lower(), str(value or "中"))

    def _join_sections(self, opportunities: list[str], risks: list[str]) -> str:
        sections: list[str] = []
        if opportunities:
            sections.append("机会：" + "；".join(opportunities))
        if risks:
            sections.append("风险：" + "；".join(risks))
        return "\n".join(sections)

    def _first_text(self, *values: Any) -> str:
        for value in values:
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    def _string_list(self, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()]

    def _normalize_text_value(self, value: Any) -> str:
        if isinstance(value, list) and value:
            return self._normalize_text_value(value[0])
        if isinstance(value, dict):
            return str(value.get("text") or value.get("value") or "").strip()
        return str(value or "").strip()

    def _chunks(self, values: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
        return [values[index : index + size] for index in range(0, len(values), size)]

    def _exception_message(self, exc: Exception) -> str:
        detail = str(exc).strip()
        return f"{exc.__class__.__name__}: {detail}" if detail else exc.__class__.__name__


insight_feishu_bitable_service = InsightFeishuBitableService()
