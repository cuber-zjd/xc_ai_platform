import json
import re
from datetime import datetime
from html import escape
from hashlib import sha256
from typing import Any
from uuid import uuid4

from fastapi import UploadFile
from langchain_core.messages import HumanMessage, SystemMessage
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.llm_factory import LLMFactory
from app.core.logger import logger
from app.models.agent.fr_report import FrReportOperationDraft, FrReportSnapshot
from app.schemas.agent.fr_report.report_ai_operation import (
    FrReportAiApplyDraftRequest,
    FrReportAiApplyDraftResponse,
    FrReportAiNewReportPlanResponse,
    FrReportAiOperationDraftResponse,
    FrReportAiOperationRead,
    FrReportAiOperationRequest,
    FrReportAiSnapshotCptRequest,
    FrReportAiSnapshotCptResponse,
    FrReportSnapshotRead,
    FrReportAiUploadedFileRead,
)
from app.schemas.agent.fr_report.report_file import (
    FrReportCellRead,
    FrReportFileStructureRead,
)
from app.services.agent.fr_report.preview_validator import preview_validator
from app.services.agent.fr_report.report_file_service import fr_report_file_service
from app.services.agent.fr_report.version_control_service import fr_report_version_control_service


ALLOWED_OPERATION_TYPES = {
    "update_sql",
    "set_cell_style",
    "set_column_width",
    "set_row_height",
    "set_dataset_binding",
    "set_data_column_filter",
    "set_form_property",
    "create_report_plan",
}
DEFAULT_NEW_REPORT_TEMPLATE_OBJECT_PATH = "webroot/APP/reportlets/数据分析/农产品价格平台/大豆/谷物大豆国际海运费报价-周报.cpt"


class FrReportAiOperationService:
    async def generate_operation_draft(
        self,
        db: AsyncSession,
        user_id: int,
        payload: FrReportAiOperationRequest,
    ) -> FrReportAiOperationDraftResponse:
        structure = await fr_report_file_service.read_report_structure(
            db=db,
            user_id=user_id,
            object_path=payload.objectPath,
        )
        selected_cell = self._find_cell(structure, payload.selectedCell)
        model_payload = {
            "userPrompt": payload.prompt,
            "mode": payload.mode,
            "report": self._compact_structure(structure, selected_cell),
            "selectedCell": selected_cell.model_dump(mode="json") if selected_cell else None,
            "selectedDataset": payload.selectedDataset,
            "previewColumns": payload.previewColumns[:80],
            "previewRows": payload.previewRows[:8],
            "safetyRules": [
                "AI 只允许生成受控 JSON 操作，不允许生成 CPT/XML 原文。",
                "字段引用必须来自 previewColumns 或当前报表已解析字段。",
                "写回 reportlets 必须经过人工确认、版本归档和外部修改冲突检测。",
                "SQL 修改只能给出草案和风险说明，不得夹带危险 DDL/DML。",
            ],
            "expectedJson": {
                "assistantMessage": "中文说明",
                "operations": [
                    {
                        "operationType": "set_cell_style",
                        "target": "C3",
                        "summary": "把 C3 加粗并设置浅色背景",
                        "riskLevel": "low",
                        "payload": {"style": {"bold": True, "backgroundColor": "#fff8d9"}},
                    }
                ],
                "previewPatch": {"cells": {"C3": {"style": {"bold": True}}}},
                "safety": {"requiresApproval": True, "blockedReasons": []},
                "warnings": [],
            },
        }
        result = await self._invoke_json(
            system_prompt=self._operation_system_prompt(),
            payload=model_payload,
            agent_name="FrReportAiOperationAgent",
        )
        operations, warnings = self._normalize_operations(
            result.get("operations"),
            preview_columns=payload.previewColumns,
        )
        warnings.extend(str(item) for item in result.get("warnings") or [])
        preview_patch = self._normalize_preview_patch(
            result.get("previewPatch"),
            operations,
            payload.selectedCell,
        )
        return FrReportAiOperationDraftResponse(
            draftId=f"fr-ai-draft-{uuid4().hex[:12]}",
            baseVersion="source-current",
            targetVersion="AI 草稿",
            status="draft" if operations else "blocked",
            assistantMessage=str(result.get("assistantMessage") or "已生成 AI 操作草稿，请检查后再应用为新版本。"),
            operations=operations,
            previewPatch=preview_patch,
            safety=dict(result.get("safety") or {"requiresApproval": True}),
            modelName=str(result.get("modelName") or "") or None,
            warnings=warnings,
        )

    async def apply_operation_draft(
        self,
        db: AsyncSession,
        user_id: int,
        payload: FrReportAiApplyDraftRequest,
    ) -> FrReportAiApplyDraftResponse:
        if not payload.operations:
            raise ValueError("AI 草稿没有可应用的操作")

        structure = await fr_report_file_service.read_report_structure(
            db=db,
            user_id=user_id,
            object_path=payload.objectPath,
        )
        operations, warnings = self._normalize_operations(
            [item.model_dump(mode="json") for item in payload.operations],
            preview_columns=[],
            strict_field_check=False,
        )
        if not operations:
            raise ValueError("AI 草稿操作未通过白名单校验")

        latest_snapshot = await self._latest_snapshot(db, user_id, structure.objectPath)
        if latest_snapshot is None:
            base_snapshot = self._build_source_snapshot(structure, user_id)
            db.add(base_snapshot)
            await db.flush()
        else:
            base_snapshot = latest_snapshot

        target_document = self._apply_operations_to_document(
            base_snapshot.document_snapshot,
            operations,
            payload.previewPatch,
        )
        target_snapshot = FrReportSnapshot(
            snapshot_id=f"fr-snap-{uuid4().hex[:12]}",
            object_path=structure.objectPath,
            report_path=structure.reportPath,
            file_name=structure.fileName,
            file_type=structure.fileType,
            user_id=user_id,
            parent_snapshot_id=base_snapshot.snapshot_id,
            source_etag=structure.etag,
            source_last_modified=structure.lastModified.isoformat() if structure.lastModified else None,
            snapshot_no=base_snapshot.snapshot_no + 1,
            status="snapshot_created",
            title=structure.document.title if structure.document else structure.fileName,
            summary=structure.summary.model_dump(mode="json"),
            document_snapshot=target_document,
            applied_patch=payload.previewPatch,
            source_hash=self._hash_payload(target_document),
            create_by=str(user_id),
            update_by=str(user_id),
        )
        operation_draft = FrReportOperationDraft(
            draft_id=payload.draftId,
            object_path=structure.objectPath,
            user_id=user_id,
            base_snapshot_id=base_snapshot.snapshot_id,
            target_snapshot_id=target_snapshot.snapshot_id,
            prompt=payload.prompt,
            selected_cell=payload.selectedCell,
            selected_dataset=payload.selectedDataset,
            status="applied",
            assistant_message=payload.assistantMessage,
            operations=[item.model_dump(mode="json") for item in operations],
            preview_patch=payload.previewPatch,
            safety=payload.safety,
            warnings=[*payload.warnings, *warnings],
            create_by=str(user_id),
            update_by=str(user_id),
        )
        db.add(target_snapshot)
        await db.flush()

        existing_draft = await self._get_operation_draft(db, payload.draftId)
        if existing_draft:
            existing_draft.target_snapshot_id = target_snapshot.snapshot_id
            existing_draft.base_snapshot_id = base_snapshot.snapshot_id
            existing_draft.status = "applied"
            existing_draft.operations = operation_draft.operations
            existing_draft.preview_patch = operation_draft.preview_patch
            existing_draft.safety = operation_draft.safety
            existing_draft.warnings = operation_draft.warnings
            existing_draft.update_time = datetime.now()
            existing_draft.update_by = str(user_id)
        else:
            db.add(operation_draft)

        await db.commit()
        await db.refresh(base_snapshot)
        await db.refresh(target_snapshot)
        return FrReportAiApplyDraftResponse(
            draftId=payload.draftId,
            status="applied",
            baseSnapshot=self._to_snapshot_read(base_snapshot),
            targetSnapshot=self._to_snapshot_read(target_snapshot),
            targetVersion=f"V{target_snapshot.snapshot_no} AI 草稿",
            assistantMessage="AI 草稿已保存为新的后端快照版本，后续可基于该快照生成 reportlets 专用目录 CPT。",
            operations=operations,
            previewPatch=payload.previewPatch,
            warnings=[*payload.warnings, *warnings],
        )

    async def generate_snapshot_cpt(
        self,
        db: AsyncSession,
        user_id: int,
        payload: FrReportAiSnapshotCptRequest,
    ) -> FrReportAiSnapshotCptResponse:
        snapshot = await self._get_snapshot(db, user_id, payload.snapshotId)
        if snapshot is None:
            raise ValueError("AI 快照不存在或无权访问")

        draft = await self._get_snapshot_operation_draft(db, snapshot.snapshot_id)
        operations = draft.operations if draft else []
        cpt_bytes = self._snapshot_to_cpt_bytes(snapshot)
        generation_log = [
            f"{datetime.now().isoformat(timespec='seconds')} 从 AI 快照确定性生成 CPT",
            f"snapshot_id={snapshot.snapshot_id}",
            "target_dir=用户指定 reportlets 路径，写入前执行版本归档和外部修改检测",
        ]
        target_object_path = fr_report_version_control_service.normalize_target_object_path(
            report_name=payload.reportName,
            target_folder=payload.targetFolder,
            target_object_path=payload.targetObjectPath,
            fallback_object_path=snapshot.object_path,
        )
        reportlet_path = fr_report_version_control_service.reportlet_path(target_object_path)
        project, structure_version, file_version, conflict = await fr_report_version_control_service.save_snapshot_file_version(
            db=db,
            user_id=user_id,
            snapshot=snapshot,
            cpt_bytes=cpt_bytes,
            dsl_payload=snapshot.document_snapshot,
            operations=operations,
            generation_log=generation_log,
            target_object_path=target_object_path,
            conflict_strategy=payload.conflictStrategy,
        )
        if conflict:
            return FrReportAiSnapshotCptResponse(
                snapshotId=snapshot.snapshot_id,
                status="conflict",
                cptObjectPath=target_object_path,
                previewUrl="",
                reportId=project.report_id,
                conflict=conflict,
                warnings=["检测到目标 CPT 存在未纳入平台版本库的外部修改，已阻止覆盖。"],
                errors=[],
            )
        validation = await preview_validator.validate(reportlet_path)
        status = "preview_failed" if validation.errors else "generated"
        if file_version:
            file_version.preview_url = validation.previewUrl
            file_version.warnings = validation.warnings
            file_version.errors = validation.errors
            file_version.write_status = status
            file_version.update_time = datetime.now()
            file_version.update_by = str(user_id)

        snapshot.cpt_object_path = target_object_path
        snapshot.meta_object_path = file_version.manifest_object_path if file_version else None
        snapshot.preview_url = validation.previewUrl
        snapshot.generation_errors = validation.errors
        snapshot.generation_warnings = validation.warnings
        snapshot.status = status
        snapshot.update_time = datetime.now()
        snapshot.update_by = str(user_id)
        await db.commit()
        await db.refresh(snapshot)

        return FrReportAiSnapshotCptResponse(
            snapshotId=snapshot.snapshot_id,
            status=status,
            cptObjectPath=target_object_path,
            metaObjectPath=file_version.manifest_object_path if file_version else None,
            operationsObjectPath=file_version.diff_object_path if file_version else None,
            logObjectPath=None,
            previewUrl=validation.previewUrl,
            reportId=project.report_id,
            fileVersionId=file_version.file_version_id if file_version else None,
            structureVersionId=structure_version.structure_version_id if structure_version else None,
            warnings=validation.warnings,
            errors=validation.errors,
        )

    async def create_new_report_plan(
        self,
        db: AsyncSession,
        user_id: int,
        requirement: str,
        template_object_path: str | None,
        report_name: str | None,
        target_folder: str | None,
        files: list[UploadFile],
    ) -> FrReportAiNewReportPlanResponse:
        effective_template_object_path = template_object_path or DEFAULT_NEW_REPORT_TEMPLATE_OBJECT_PATH
        template_summary: dict[str, Any] = {}
        if effective_template_object_path:
            structure = await fr_report_file_service.read_report_structure(
                db=db,
                user_id=user_id,
                object_path=effective_template_object_path,
            )
            template_summary = self._compact_structure(structure, None)
            template_summary["objectPath"] = effective_template_object_path

        uploaded_files = [await self._read_upload_summary(file) for file in files[:8]]
        result = await self._invoke_json(
            system_prompt=self._new_report_system_prompt(),
            payload={
                "requirement": requirement,
                "reportName": report_name,
                "targetFolder": target_folder,
                "templateSummary": template_summary,
                "uploadedFiles": [item.model_dump(mode="json") for item in uploaded_files],
                "businessConstraints": self._new_report_business_constraints(requirement),
                "expectedJson": {
                    "assistantMessage": "中文说明",
                    "questions": ["是否已有业务数据库表？", "是否需要填报？"],
                    "proposal": {
                        "reportName": "日报",
                        "reportType": "填报/查询",
                        "datasets": [],
                        "layout": {},
                        "styleTemplate": {},
                        "formMode": False,
                        "risks": [],
                    },
                    "operations": [],
                    "safety": {"requiresApproval": True},
                    "warnings": [],
                },
            },
            agent_name="FrReportAiNewReportAgent",
        )
        proposal = self._normalize_new_report_proposal(requirement, dict(result.get("proposal") or {}))
        operations, warnings = self._normalize_operations(
            result.get("operations"),
            preview_columns=[],
            strict_field_check=False,
        )
        warnings.extend(str(item) for item in result.get("warnings") or [])
        if self._is_futures_report_requirement(requirement):
            warnings.append("期货台账方案已归一到平台约定表名，最终 CPT 仍由确定性 ReportDSL/CPT 生成链路输出。")
        target_object_path = None
        if report_name or target_folder:
            target_object_path = fr_report_version_control_service.normalize_target_object_path(
                report_name=report_name or str(proposal.get("reportName") or "AI生成报表"),
                target_folder=target_folder,
                fallback_object_path=effective_template_object_path,
            )
        return FrReportAiNewReportPlanResponse(
            draftId=f"fr-ai-new-{uuid4().hex[:12]}",
            status="proposal",
            assistantMessage=str(result.get("assistantMessage") or "已生成新建报表方案，请先确认关键问题。"),
            reportName=report_name or str(proposal.get("reportName") or ""),
            targetFolder=target_folder,
            targetObjectPath=target_object_path,
            questions=[str(item) for item in result.get("questions") or []][:8],
            proposal=proposal,
            operations=operations,
            templateSummary=template_summary,
            uploadedFiles=uploaded_files,
            safety=dict(result.get("safety") or {"requiresApproval": True}),
            warnings=warnings,
        )

    async def _invoke_json(
        self,
        system_prompt: str,
        payload: dict[str, Any],
        agent_name: str,
    ) -> dict[str, Any]:
        try:
            response = await LLMFactory.safe_invoke(
                [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=json.dumps(payload, ensure_ascii=False)),
                ],
                capability="complex-reasoning",
                temperature=0,
                json_mode=True,
                enable_reasoning=False,
                max_retries=3,
            )
        except Exception as exc:
            message = LLMFactory.describe_invocation_error(exc)
            logger.warning(f"{agent_name} 模型调用失败: {message}")
            raise RuntimeError(message) from exc

        content = getattr(response, "content", response)
        if isinstance(content, list):
            content = "".join(str(item) for item in content)
        if not isinstance(content, str):
            raise RuntimeError(f"{agent_name} 模型返回了非文本内容")
        try:
            return json.loads(self._strip_json_fence(content))
        except json.JSONDecodeError as exc:
            logger.warning(f"{agent_name} JSON 解析失败，原始内容前 500 字: {content[:500]}")
            raise RuntimeError("模型返回内容不是合法 JSON，请稍后重试或收窄指令范围。") from exc

    def _operation_system_prompt(self) -> str:
        return (
            "你是 FineReport 报表设计器 AI 操作代理。"
            "你只能返回严格 JSON，不输出 Markdown。"
            "你不能生成 CPT、XML 或正式文件路径。"
            "你需要把用户意图拆成可审计操作，operationType 只能使用白名单："
            f"{', '.join(sorted(ALLOWED_OPERATION_TYPES))}。"
            "页面样式修改必须同时给出 previewPatch.cells，用单元格地址作为 key。"
            "涉及 SQL、填报、字段绑定时必须说明风险，并设置 requiresApproval=true。"
            "所有说明使用中文。"
        )

    def _new_report_system_prompt(self) -> str:
        return (
            "你是 FineReport 新建报表方案代理。"
            "你只能返回严格 JSON，不输出 Markdown。"
            "你需要结合自然语言、上传文件摘要和模板结构，先提出必要追问，再形成可执行方案。"
            "方案必须覆盖数据源/SQL、报表布局、样式模板、填报属性、版本流程和安全风险。"
            "如果 payload.businessConstraints 提供了推荐表名、主键、字段或写回规则，proposal 中必须优先使用这些约束，不得自行改名或替换为示例表。"
            "禁止生成 CPT/XML，禁止声称已经绕过版本控制写入 reportlets。"
            "所有说明使用中文。"
        )

    def _new_report_business_constraints(self, requirement: str) -> dict[str, Any]:
        if not self._is_futures_report_requirement(requirement):
            return {}
        return {
            "scenario": "futures_operation_ledger",
            "tables": {
                "main": "fr_future_trade_ledger",
                "contractBase": "fr_future_contract_base",
                "settlementPrice": "fr_future_settlement_price",
            },
            "writeBack": {
                "enabled": True,
                "targetTable": "fr_future_trade_ledger",
                "primaryKeys": ["ledger_id"],
                "businessKeys": ["account_name", "contract_variety", "contract_code"],
                "allowInsert": True,
                "allowDelete": True,
            },
            "safetyRules": [
                "单元格控件优先使用轻量 TextEditor/NumberEditor/DateEditor，不绑定大数据集下拉。",
                "查询筛选参数使用 start_date/end_date/account_name/contract_variety/contract_code。",
                "平仓数量必须小于等于开仓数量。",
            ],
        }

    def _normalize_new_report_proposal(self, requirement: str, proposal: dict[str, Any]) -> dict[str, Any]:
        if not self._is_futures_report_requirement(requirement):
            return proposal
        replacements = {
            "futures_ledger": "fr_future_trade_ledger",
            "future_ledger": "fr_future_trade_ledger",
            "futures_basic": "fr_future_contract_base",
            "future_basic": "fr_future_contract_base",
            "futures_settlement_price": "fr_future_settlement_price",
            "future_settlement_price": "fr_future_settlement_price",
        }

        def replace_value(value: Any) -> Any:
            if isinstance(value, str):
                normalized = value
                for old, new in replacements.items():
                    normalized = re.sub(rf"\b{re.escape(old)}\b", new, normalized, flags=re.IGNORECASE)
                return normalized
            if isinstance(value, list):
                return [replace_value(item) for item in value]
            if isinstance(value, dict):
                return {key: replace_value(item) for key, item in value.items()}
            return value

        normalized = replace_value(proposal)
        if isinstance(normalized, dict):
            normalized.setdefault("formMode", True)
            normalized["businessConstraints"] = self._new_report_business_constraints(requirement)
        return normalized if isinstance(normalized, dict) else proposal

    def _is_futures_report_requirement(self, requirement: str) -> bool:
        keywords = ("期货", "合约品种", "合约代码", "开仓", "平仓", "持仓", "台账")
        return sum(1 for keyword in keywords if keyword in requirement) >= 3

    def _compact_structure(
        self,
        structure: FrReportFileStructureRead,
        selected_cell: FrReportCellRead | None,
    ) -> dict[str, Any]:
        sheet = structure.document.sheets[0] if structure.document and structure.document.sheets else None
        cells = sheet.cells if sheet else []
        return {
            "objectPath": structure.objectPath,
            "fileName": structure.fileName,
            "fileType": structure.fileType,
            "datasets": [
                {
                    "name": item.name,
                    "databaseName": item.databaseName,
                    "querySql": self._limit_text(item.querySql, 1200),
                }
                for item in structure.datasets[:20]
            ],
            "sheet": {
                "name": sheet.name if sheet else None,
                "rowCount": sheet.rowCount if sheet else 0,
                "columnCount": sheet.columnCount if sheet else 0,
                "sampleCells": [
                    {
                        "address": cell.address,
                        "text": cell.text,
                        "formula": cell.formula,
                        "style": cell.style.model_dump(mode="json"),
                        "dataColumn": cell.dataColumn.model_dump(mode="json") if cell.dataColumn else None,
                        "widget": cell.widget.model_dump(mode="json") if cell.widget else None,
                    }
                    for cell in cells[:80]
                ],
                "selectedCellAddress": selected_cell.address if selected_cell else None,
            },
            "summary": structure.summary.model_dump(mode="json"),
            "warnings": structure.warnings[:12],
        }

    def _find_cell(
        self,
        structure: FrReportFileStructureRead,
        address: str | None,
    ) -> FrReportCellRead | None:
        if not address or not structure.document:
            return None
        target = address.upper()
        for sheet in structure.document.sheets:
            for cell in sheet.cells:
                if cell.address.upper() == target:
                    return cell
        return None

    def _normalize_operations(
        self,
        raw_operations: Any,
        preview_columns: list[str],
        strict_field_check: bool = True,
    ) -> tuple[list[FrReportAiOperationRead], list[str]]:
        operations: list[FrReportAiOperationRead] = []
        warnings: list[str] = []
        allowed_fields = set(preview_columns)
        for raw in list(raw_operations or [])[:12]:
            if not isinstance(raw, dict):
                warnings.append("已忽略一个非对象操作。")
                continue
            operation_type = str(raw.get("operationType") or "")
            if operation_type not in ALLOWED_OPERATION_TYPES:
                warnings.append(f"已忽略不在白名单内的操作：{operation_type or '空类型'}。")
                continue
            payload = dict(raw.get("payload") or {})
            field = payload.get("field") or payload.get("column")
            if strict_field_check and allowed_fields and field and str(field) not in allowed_fields:
                warnings.append(f"操作字段 {field} 不在当前数据集预览字段内，已忽略。")
                continue
            risk_level = str(raw.get("riskLevel") or "low")
            if risk_level not in {"low", "medium", "high"}:
                risk_level = "medium"
            operations.append(
                FrReportAiOperationRead(
                    operationType=operation_type,
                    target=str(raw.get("target") or "") or None,
                    summary=str(raw.get("summary") or operation_type),
                    riskLevel=risk_level,  # type: ignore[arg-type]
                    payload=payload,
                )
            )
        return operations, warnings

    def _normalize_preview_patch(
        self,
        raw_patch: Any,
        operations: list[FrReportAiOperationRead],
        selected_cell: str | None,
    ) -> dict[str, Any]:
        patch = raw_patch if isinstance(raw_patch, dict) else {}
        cells = patch.get("cells") if isinstance(patch.get("cells"), dict) else {}
        for operation in operations:
            if operation.operationType != "set_cell_style":
                continue
            target = operation.target or selected_cell
            style = operation.payload.get("style")
            if target and isinstance(style, dict):
                cells[target] = {
                    **dict(cells.get(target) or {}),
                    "style": {**style},
                    "badge": "AI",
                }
        if cells:
            patch["cells"] = cells
        return patch

    async def _latest_snapshot(
        self,
        db: AsyncSession,
        user_id: int,
        object_path: str,
    ) -> FrReportSnapshot | None:
        statement = (
            select(FrReportSnapshot)
            .where(
                FrReportSnapshot.user_id == user_id,
                FrReportSnapshot.object_path == object_path,
                FrReportSnapshot.is_deleted == 0,
            )
            .order_by(FrReportSnapshot.snapshot_no.desc(), FrReportSnapshot.id.desc())
            .limit(1)
        )
        return (await db.exec(statement)).first()

    async def _get_snapshot(
        self,
        db: AsyncSession,
        user_id: int,
        snapshot_id: str,
    ) -> FrReportSnapshot | None:
        statement = select(FrReportSnapshot).where(
            FrReportSnapshot.snapshot_id == snapshot_id,
            FrReportSnapshot.user_id == user_id,
            FrReportSnapshot.is_deleted == 0,
        )
        return (await db.exec(statement)).first()

    async def _get_operation_draft(
        self,
        db: AsyncSession,
        draft_id: str,
    ) -> FrReportOperationDraft | None:
        statement = select(FrReportOperationDraft).where(
            FrReportOperationDraft.draft_id == draft_id,
            FrReportOperationDraft.is_deleted == 0,
        )
        return (await db.exec(statement)).first()

    async def _get_snapshot_operation_draft(
        self,
        db: AsyncSession,
        snapshot_id: str,
    ) -> FrReportOperationDraft | None:
        statement = (
            select(FrReportOperationDraft)
            .where(
                FrReportOperationDraft.target_snapshot_id == snapshot_id,
                FrReportOperationDraft.is_deleted == 0,
            )
            .order_by(FrReportOperationDraft.id.desc())
            .limit(1)
        )
        return (await db.exec(statement)).first()

    def _build_source_snapshot(
        self,
        structure: FrReportFileStructureRead,
        user_id: int,
    ) -> FrReportSnapshot:
        document_payload = structure.model_dump(mode="json")
        return FrReportSnapshot(
            snapshot_id=f"fr-snap-{uuid4().hex[:12]}",
            object_path=structure.objectPath,
            report_path=structure.reportPath,
            file_name=structure.fileName,
            file_type=structure.fileType,
            user_id=user_id,
            source_etag=structure.etag,
            source_last_modified=structure.lastModified.isoformat() if structure.lastModified else None,
            snapshot_no=1,
            status="source_imported",
            title=structure.document.title if structure.document else structure.fileName,
            summary=structure.summary.model_dump(mode="json"),
            document_snapshot=document_payload,
            source_hash=self._hash_payload(document_payload),
            create_by=str(user_id),
            update_by=str(user_id),
        )

    def _apply_operations_to_document(
        self,
        document_snapshot: dict[str, Any],
        operations: list[FrReportAiOperationRead],
        preview_patch: dict[str, Any],
    ) -> dict[str, Any]:
        result = json.loads(json.dumps(document_snapshot, ensure_ascii=False))
        for operation in operations:
            if operation.operationType == "set_cell_style":
                self._apply_cell_style(result, operation)
        if preview_patch:
            result.setdefault("aiPreviewPatch", preview_patch)
        return result

    def _apply_cell_style(
        self,
        snapshot: dict[str, Any],
        operation: FrReportAiOperationRead,
    ) -> None:
        target = operation.target
        style_patch = operation.payload.get("style")
        if not target or not isinstance(style_patch, dict):
            return
        sheets = ((snapshot.get("document") or {}).get("sheets") or [])
        for sheet in sheets:
            for cell in sheet.get("cells") or []:
                if str(cell.get("address") or "").upper() != target.upper():
                    continue
                style = dict(cell.get("style") or {})
                style.update(style_patch)
                cell["style"] = style
                cell["aiModified"] = True
                return

    def _hash_payload(self, payload: dict[str, Any]) -> str:
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
        return sha256(raw.encode("utf-8")).hexdigest()

    def _snapshot_to_cpt_bytes(self, snapshot: FrReportSnapshot) -> bytes:
        document = snapshot.document_snapshot or {}
        sheet = self._first_sheet(document)
        title = snapshot.title or snapshot.file_name or "AI生成报表"
        row_count = max(int(sheet.get("rowCount") or 1), 1)
        column_count = max(int(sheet.get("columnCount") or 1), 1)
        cells_xml = self._snapshot_cells_xml(sheet.get("cells") or [])
        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<WorkBook xmlVersion="20211223" releaseVersion="11.5.0">
<TableDataMap/>
<ReportParameterAttr>
<Attributes showWindow="true"/>
</ReportParameterAttr>
<Report class="com.fr.report.worksheet.WorkSheet" name="{escape(title)}">
<ReportPageAttr>
<HR/>
<FR/>
</ReportPageAttr>
<Table rows="{row_count}" columns="{column_count}">
{cells_xml}
</Table>
</Report>
</WorkBook>
"""
        return xml.encode("utf-8")

    def _first_sheet(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        document = snapshot.get("document") or {}
        sheets = document.get("sheets") or []
        if sheets and isinstance(sheets[0], dict):
            return sheets[0]
        return {"rowCount": 1, "columnCount": 1, "cells": []}

    def _snapshot_cells_xml(self, cells: list[dict[str, Any]]) -> str:
        parts: list[str] = []
        for cell in cells[:5000]:
            row = int(cell.get("row") or 1)
            column = int(cell.get("column") or 1)
            value = self._cell_display_value(cell)
            style = cell.get("style") or {}
            style_name = self._style_name(style, bool(cell.get("aiModified")))
            row_span = int(cell.get("rowSpan") or 1)
            col_span = int(cell.get("colSpan") or 1)
            span_xml = ""
            if row_span > 1:
                span_xml += f'\n<Attributes rowSpan="{row_span}"/>'
            if col_span > 1:
                span_xml += f'\n<Attributes colSpan="{col_span}"/>'
            parts.append(
                f"""<Cell row="{row}" column="{column}">
<O><![CDATA[{self._safe_cdata(value)}]]></O>
<PrivilegeControl/>{span_xml}
<Style name="{style_name}"/>
</Cell>"""
            )
        return "\n".join(parts)

    def _cell_display_value(self, cell: dict[str, Any]) -> str:
        formula = cell.get("formula")
        text = cell.get("text")
        if formula not in (None, ""):
            return str(formula)
        if text not in (None, ""):
            return str(text)
        data_column = cell.get("dataColumn") or {}
        dataset = data_column.get("dataset")
        field = data_column.get("field")
        if dataset and field:
            return f"=${dataset}.{field}"
        return ""

    def _style_name(self, style: dict[str, Any], ai_modified: bool) -> str:
        if ai_modified:
            return "ai_modified"
        if style.get("bold") or style.get("backgroundColor"):
            return "header"
        return str(style.get("styleName") or "body")

    def _safe_cdata(self, value: str) -> str:
        return value.replace("]]>", "]]]]><![CDATA[>")

    def _to_snapshot_read(self, snapshot: FrReportSnapshot) -> FrReportSnapshotRead:
        return FrReportSnapshotRead(
            snapshotId=snapshot.snapshot_id,
            objectPath=snapshot.object_path,
            reportPath=snapshot.report_path,
            fileName=snapshot.file_name,
            parentSnapshotId=snapshot.parent_snapshot_id,
            snapshotNo=snapshot.snapshot_no,
            status=snapshot.status,
            title=snapshot.title,
            summary=snapshot.summary or {},
            appliedPatch=snapshot.applied_patch or {},
        )

    async def _read_upload_summary(self, file: UploadFile) -> FrReportAiUploadedFileRead:
        content = await file.read()
        await file.seek(0)
        text_preview = None
        if file.content_type and (
            file.content_type.startswith("text/")
            or file.filename.lower().endswith((".csv", ".txt", ".md"))
        ):
            text_preview = content[:4000].decode("utf-8", errors="ignore")
        return FrReportAiUploadedFileRead(
            fileName=file.filename,
            contentType=file.content_type,
            size=len(content),
            textPreview=text_preview,
        )

    def _strip_json_fence(self, text: str) -> str:
        value = text.strip()
        if value.startswith("```"):
            value = re.sub(r"^```(?:json)?", "", value, flags=re.IGNORECASE).strip()
            value = re.sub(r"```$", "", value).strip()
        return value

    def _limit_text(self, text: str | None, max_length: int) -> str | None:
        if not text:
            return text
        if len(text) <= max_length:
            return text
        return f"{text[:max_length]}..."


fr_report_ai_operation_service = FrReportAiOperationService()
