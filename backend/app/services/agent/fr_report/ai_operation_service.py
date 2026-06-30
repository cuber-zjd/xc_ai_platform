import asyncio
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

from app.core.config import settings
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
from app.services.agent.fr_report.fr_minio_service import fr_minio_service
from app.services.agent.fr_report.report_file_service import fr_report_file_service
from app.services.agent.fr_report.sqlserver_query_service import sqlserver_query_service
from app.services.agent.fr_report.version_control_service import fr_report_version_control_service


ALLOWED_OPERATION_TYPES = {"xml_patch"}
SNAPSHOT_APPLY_OPERATION_TYPES = {"xml_patch"}
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
        source_xml = await self._read_source_cpt_xml(payload.objectPath)
        cpt_source_context = self._build_cpt_source_context(source_xml, selected_cell, payload.prompt)
        cpt_xml_index = self._build_cpt_xml_index(source_xml)
        report_layout_context = self._build_report_layout_context(structure)
        database_source_context = await self._build_database_source_context(
            prompt=payload.prompt,
            structure=structure,
            source_xml=source_xml,
        )
        experience_context = await self._build_operation_experience_context(
            db=db,
            user_id=user_id,
            object_path=payload.objectPath,
            prompt=payload.prompt,
        )
        model_payload = {
            "userPrompt": payload.prompt,
            "mode": payload.mode,
            "report": self._compact_structure(structure, selected_cell),
            "reportLayoutContext": report_layout_context,
            "cptSourceContext": cpt_source_context,
            "cptXmlIndex": cpt_xml_index,
            "databaseSourceContext": database_source_context,
            "experienceContext": experience_context,
            "selectedCell": selected_cell.model_dump(mode="json") if selected_cell else None,
            "selectedDataset": payload.selectedDataset,
            "previewColumns": payload.previewColumns[:80],
            "previewRows": payload.previewRows[:8],
            "allowedOperationTypes": sorted(ALLOWED_OPERATION_TYPES),
            "safetyRules": [
                "AI 只允许通过 operationType=xml_patch 返回 CPT XML 修改。",
                "禁止返回 update_sql、set_form_property、set_data_column_filter、set_cell_style 等旧语义操作；这些只能作为理解意图的中间想法，最终必须落实为 xml_patch。",
                "优先基于 cptSourceContext 中的原始 XML 片段做最小修改，不要凭空编造未读取过的大段 XML。",
                "涉及数据库字段、日期字段或样例值时，必须优先使用 databaseSourceContext 中真实表结构和样例数据；如果没有查到，不得编造字段名。",
                "涉及把数据填入报表时，必须优先使用 reportLayoutContext 的单元格矩阵和表头语义定位，不能只按用户口语顺序猜单元格。",
                "cptXmlIndex 只用于快速定位，不能限制你需要读取和修改的范围；若需求跨多处节点，应返回多个 patch 或 full_replace。",
                "experienceContext 是按需检索到的历史经验，只能作为参考，当前用户需求和当前 CPT 原文优先。",
                "写回 reportlets 必须经过人工确认、版本归档和外部修改冲突检测。",
                "SQL 修改只能给出草案和风险说明，不得夹带危险 DDL/DML。",
            ],
            "expectedJson": {
                "assistantMessage": "中文说明",
                "operations": [
                    {
                        "operationType": "xml_patch",
                        "target": "cell:C3",
                        "summary": "直接修改 CPT XML 中 C3 对应片段",
                        "riskLevel": "medium",
                        "payload": {
                            "patches": [
                                {
                                    "action": "replace",
                                    "selector": "cell:C3",
                                    "newXml": "<C c=\"2\" r=\"2\" s=\"1\"><O><![CDATA[示例]]></O><PrivilegeControl/><Expand/></C>",
                                }
                            ]
                        },
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
        result = await self._repair_xml_patch_result_if_needed(
            result=result,
            model_payload=model_payload,
        )
        operations, warnings = self._normalize_operations(
            result.get("operations"),
            preview_columns=payload.previewColumns,
        )
        warnings.extend(self._unsupported_snapshot_operation_warnings(operations))
        warnings.extend(self._operation_risk_warnings(operations))
        warnings.extend(str(item) for item in result.get("warnings") or [])
        preview_patch = self._normalize_preview_patch(
            result.get("previewPatch"),
            operations,
            payload.selectedCell,
        )
        safety = dict(result.get("safety") or {"requiresApproval": True})
        max_risk = self._max_operation_risk(operations)
        if max_risk in {"medium", "high"}:
            safety["requiresApproval"] = True
            safety["riskLevel"] = max_risk
        return FrReportAiOperationDraftResponse(
            draftId=f"fr-ai-draft-{uuid4().hex[:12]}",
            baseVersion="source-current",
            targetVersion="待应用修改项",
            status="draft" if operations else "blocked",
            assistantMessage=str(result.get("assistantMessage") or "已生成待应用修改项，请检查后再确认应用。"),
            operations=operations,
            previewPatch=preview_patch,
            safety=safety,
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
            raise ValueError("当前没有可应用的修改项")

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
            raise ValueError("当前没有有效的文件修改项")
        applyable_operations = [item for item in operations if item.operationType in SNAPSHOT_APPLY_OPERATION_TYPES]
        unsupported_operations = [item for item in operations if item.operationType not in SNAPSHOT_APPLY_OPERATION_TYPES]
        if unsupported_operations:
            labels = "、".join(f"{item.operationType}({item.summary})" for item in unsupported_operations[:6])
            raise ValueError(f"返回内容包含不可应用的修改项，已取消应用且没有写入 CPT：{labels}。")
        if not applyable_operations:
            raise ValueError("当前没有可应用的文件修改项。")

        latest_snapshot = await self._latest_snapshot(db, user_id, structure.objectPath)
        if latest_snapshot is None:
            base_snapshot = self._build_source_snapshot(structure, user_id)
            db.add(base_snapshot)
            await db.flush()
        else:
            base_snapshot = latest_snapshot

        target_document, apply_warnings = self._apply_operations_to_document(
            base_snapshot.document_snapshot,
            applyable_operations,
            payload.previewPatch,
        )
        warnings.extend(apply_warnings)
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
            targetVersion=f"V{target_snapshot.snapshot_no} 待应用修改项",
            assistantMessage="待应用修改项已进入新的后端快照版本，后续可基于该快照生成 reportlets 专用目录 CPT。",
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
        operations = draft.operations if draft else self._snapshot_xml_patch_operations(snapshot)
        target_object_path = fr_report_version_control_service.normalize_target_object_path(
            report_name=payload.reportName,
            target_folder=payload.targetFolder,
            target_object_path=payload.targetObjectPath,
            fallback_object_path=snapshot.object_path,
        )
        cpt_bytes, patch_warnings = await self._build_snapshot_cpt_bytes(
            snapshot=snapshot,
            target_object_path=target_object_path,
            operations=operations,
        )
        generation_log = [
            f"{datetime.now().isoformat(timespec='seconds')} 从 AI 快照确定性生成 CPT",
            f"snapshot_id={snapshot.snapshot_id}",
            "target_dir=用户指定 reportlets 路径，写入前执行版本归档和外部修改检测",
            "existing_cpt_patch=优先基于当前 CPT XML 增量写入，避免重建导致原内容丢失",
            *patch_warnings,
        ]
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
                warnings=["检测到目标 CPT 存在未纳入平台版本库的外部修改，已阻止覆盖。", *patch_warnings],
                errors=[],
            )
        validation = await preview_validator.validate(reportlet_path)
        status = "preview_failed" if validation.errors else "generated"
        if file_version:
            file_version.preview_url = validation.previewUrl
            file_version.warnings = [*patch_warnings, *validation.warnings]
            file_version.errors = validation.errors
            file_version.write_status = status
            file_version.update_time = datetime.now()
            file_version.update_by = str(user_id)

        snapshot.cpt_object_path = target_object_path
        snapshot.meta_object_path = file_version.manifest_object_path if file_version else None
        snapshot.preview_url = validation.previewUrl
        snapshot.generation_errors = validation.errors
        snapshot.generation_warnings = [*patch_warnings, *validation.warnings]
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
            warnings=[*patch_warnings, *validation.warnings],
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
            "你的主工作方式是像代码助手一样直接修改 CPT XML：读取 cptSourceContext 中的相关片段，返回 xml_patch。"
            "你需要把用户意图拆成可审计操作；operationType 只能使用 xml_patch。"
            "payload.patches 可声明 replace/insert_before/insert_after/delete/full_replace。"
            "样式 StyleList、填报 ReportWriteAttr/ReportWebAttr、脚本事件、参数栏、数据集、单元格都可以改；"
            "参数栏控件、下拉框、SQL 和样式都要直接返回对应 CPT XML 片段。"
            "如果用户明确要求大改或局部片段不足，可以 full_replace 返回完整 CPT XML。"
            "你必须先使用 reportLayoutContext 判断当前表头、数据区域和单元格语义；例如数据列应按上方表头链定位，不能把相邻列当成目标列。"
            "你必须先使用 databaseSourceContext 判断真实字段、日期字段和样例值；没有查到字段时，不能假设 create_time/date 等字段存在。"
            "如果用户要求把数据库数据写入报表，优先修改数据集 SQL 和对应单元格数据绑定，而不是把样例值硬编码到单元格。"
            "页面可视改动尽量同时给出 previewPatch.cells，用单元格地址作为 key。"
            "涉及 SQL、填报、字段绑定时必须说明风险，并设置 requiresApproval=true。"
            f"{self._operation_minishots()}"
            "所有说明使用中文。"
        )

    def _operation_repair_system_prompt(self) -> str:
        return (
            "你是 FineReport CPT 文件补丁修复代理。"
            "你只能返回严格 JSON，不输出 Markdown。"
            "上一轮模型返回了不可直接应用的中间结构，你要把它改写为真正可应用的 CPT XML patch。"
            "operationType 只能是 xml_patch；禁止返回 update_sql、set_form_property、set_data_column_filter、set_cell_style 等旧语义操作。"
            "如果上一轮意图是改参数栏、下拉框、SQL、样式、填报或脚本，你必须直接替换或插入对应的 CPT XML 片段。"
            "优先使用 cptSourceContext.snippets 里的 selector 和原始 XML；可以使用 selector=ReportParameterAttr、ParameterUI、TableData[name=\"ds1\"]、TableData[name=\"ds1\"]/Query、cell:A1 等。"
            "如果局部片段不足以表达正确修改，但当前需求明确，可以使用 action=full_replace 返回完整 WorkBook。"
            "返回内容必须包含 operations，且至少一个 operationType=xml_patch；所有说明使用中文。"
        )

    async def _repair_xml_patch_result_if_needed(
        self,
        *,
        result: dict[str, Any],
        model_payload: dict[str, Any],
    ) -> dict[str, Any]:
        raw_operations = result.get("operations")
        if self._has_xml_patch_operation(raw_operations):
            return result
        if not isinstance(raw_operations, list) or not raw_operations:
            return result

        repair_payload = dict(model_payload)
        repair_payload["repairMode"] = "convert_invalid_operations_to_direct_cpt_xml_patch"
        repair_payload["invalidModelOutput"] = self._compact_json_for_prompt(result, limit=8000)
        repair_payload["repairRules"] = [
            "不要解释为什么失败，直接返回修复后的 JSON。",
            "operations 数组内只允许 operationType=xml_patch。",
            "把 invalidModelOutput 中的旧语义操作当作需求理解，不要原样返回。",
            "参数栏新增或修改筛选控件时，直接 patch ReportParameterAttr 或 ParameterUI。",
            "数据集 SQL 变化时，直接 patch TableData[name=\"数据集名\"]/Query 或完整 TableData 节点。",
            "用户明确说不要做的视觉效果不得加入 patch。",
        ]
        repair_payload["expectedJson"] = {
            "assistantMessage": "中文说明，说明将修改哪些 CPT 文件区域",
            "operations": [
                {
                    "operationType": "xml_patch",
                    "target": "ReportParameterAttr 或 TableData[name=\"ds1\"]",
                    "summary": "自然语言说明修改范围",
                    "riskLevel": "medium",
                    "payload": {
                        "patches": [
                            {
                                "action": "replace",
                                "selector": "ReportParameterAttr",
                                "newXml": "<ReportParameterAttr>...</ReportParameterAttr>",
                            }
                        ]
                    },
                }
            ],
            "previewPatch": {"cells": {}},
            "safety": {"requiresApproval": True, "riskLevel": "medium"},
            "warnings": [],
        }
        try:
            repaired = await self._invoke_json(
                system_prompt=self._operation_repair_system_prompt(),
                payload=repair_payload,
                agent_name="FrReportAiOperationRepairAgent",
            )
        except RuntimeError as exc:
            logger.warning(f"FineReport 待应用修改项自动修复失败：{exc}")
            return result
        if not self._has_xml_patch_operation(repaired.get("operations")):
            return result
        warnings = [str(item) for item in repaired.get("warnings") or []]
        warnings.append("已将不可直接应用的中间结构自动改写为可确认的文件修改项。")
        repaired["warnings"] = warnings
        return repaired

    def _has_xml_patch_operation(self, raw_operations: Any) -> bool:
        return any(
            isinstance(item, dict) and str(item.get("operationType") or "") == "xml_patch"
            for item in list(raw_operations or [])
        )

    def _compact_json_for_prompt(self, value: Any, *, limit: int) -> str:
        try:
            text = json.dumps(value, ensure_ascii=False, default=str)
        except TypeError:
            text = str(value)
        return self._limit_text(text, limit) or ""

    def _operation_minishots(self) -> str:
        return (
            "下面是极短 mini-shot，用来示范输出形态，不是固定流程："
            "例1 用户：把 C2 标题改成交易确认书编号并加粗。"
            "输出：{\"assistantMessage\":\"我会直接替换 C2 的 CPT 单元格片段。\","
            "\"operations\":[{\"operationType\":\"xml_patch\",\"target\":\"cell:C2\",\"summary\":\"替换 C2 标题单元格 XML\","
            "\"riskLevel\":\"low\",\"payload\":{\"patches\":[{\"action\":\"replace\",\"selector\":\"cell:C2\","
            "\"newXml\":\"<C c=\\\"2\\\" r=\\\"1\\\" s=\\\"1\\\"><O><![CDATA[交易确认书编号]]></O><PrivilegeControl/><Expand/></C>\"}]} }],"
            "\"previewPatch\":{\"cells\":{\"C2\":{\"text\":\"交易确认书编号\",\"badge\":\"AI\"}}},\"safety\":{\"requiresApproval\":true}}。"
            "例2 用户：把参数栏里的操作平台改成下拉，字典用 ds1.operate_platform。"
            "输出：operationType 必须是 xml_patch，selector 选 ReportParameterAttr 或 ParameterUI，newXml 中直接包含 com.fr.form.ui.ComboBox 和 TableDataDictionary。"
            "例3 用户：填报提交前加校验脚本。"
            "输出 xml_patch 修改 ReportWriteAttr/ReportWebAttr 或脚本事件节点，summary 说明影响和风险。"
            "例4 用户：这张报表整体结构都重做。"
            "输出 xml_patch action=full_replace，newXml 是完整 <WorkBook>...</WorkBook>，并把 riskLevel 设为 high。"
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

    async def _read_source_cpt_xml(self, object_path: str) -> str | None:
        try:
            if not await fr_minio_service.object_exists(object_path):
                return None
            content = await fr_minio_service.download_file(object_path)
            return content.decode("utf-8", errors="strict")
        except Exception as exc:
            logger.warning(f"读取 CPT 原始 XML 片段失败：{object_path}，{exc}")
            return None

    def _build_cpt_source_context(
        self,
        source_xml: str | None,
        selected_cell: FrReportCellRead | None,
        prompt: str | None,
    ) -> dict[str, Any]:
        if not source_xml:
            return {"available": False, "snippets": []}
        snippets: list[dict[str, str]] = []
        prompt_text = str(prompt or "")
        if selected_cell:
            cell_xml = self._extract_cell_xml(source_xml, selected_cell.row, selected_cell.column)
            if cell_xml:
                snippets.append({"selector": f"cell:{selected_cell.address}", "reason": "当前选中单元格", "xml": self._limit_text(cell_xml, 6000) or ""})

        keyword_groups = [
            (("参数", "筛选", "下拉", "日期"), ("ReportParameterAttr", "ParameterUI")),
            (("数据集", "sql", "SQL", "查询"), ("TableDataMap",)),
            (("样式", "颜色", "字体", "边框", "背景", "居中", "加粗"), ("StyleList",)),
            (("填报", "提交", "写回", "新增行", "删除行", "校验"), ("ReportWriteAttr", "ReportWebAttr")),
            (("脚本", "事件", "js", "JS", "JavaScript", "点击"), ("JavaScript", "Event", "Widget")),
        ]
        for keywords, tags in keyword_groups:
            if not any(keyword in prompt_text for keyword in keywords):
                continue
            for tag in tags:
                for index, xml in enumerate(self._extract_tag_xml_blocks(source_xml, tag, limit=3), start=1):
                    snippets.append({"selector": tag if index == 1 else f"{tag}[{index}]", "reason": f"命中需求关键词：{','.join(keywords[:3])}", "xml": self._limit_text(xml, 12000) or ""})

        if not snippets:
            for tag in ("ReportParameterAttr", "TableDataMap"):
                for index, xml in enumerate(self._extract_tag_xml_blocks(source_xml, tag, limit=1), start=1):
                    snippets.append({"selector": tag if index == 1 else f"{tag}[{index}]", "reason": "默认上下文", "xml": self._limit_text(xml, 9000) or ""})

        return {
            "available": True,
            "editingMode": "direct_cpt_xml_patch",
            "tokenPolicy": "按需提供当前单元格和需求相关片段；索引只帮助定位，不限制读取范围；需要跨区域修改时返回多个 patch，局部信息不足且确有必要时可 full_replace。",
            "supportsFullReplace": True,
            "snippets": snippets[:12],
        }

    def _build_cpt_xml_index(self, source_xml: str | None) -> dict[str, Any]:
        if not source_xml:
            return {"available": False}

        cells: list[dict[str, Any]] = []
        for match in re.finditer(r"<C\b([^>]*)>(.*?)</C>", source_xml, flags=re.S | re.I):
            attrs = match.group(1)
            column_match = re.search(r'\bc="(\d+)"', attrs)
            row_match = re.search(r'\br="(\d+)"', attrs)
            if not column_match or not row_match:
                continue
            column = int(column_match.group(1)) + 1
            row = int(row_match.group(1)) + 1
            cell_xml = match.group(0)
            cells.append(
                {
                    "selector": f"cell:{self._column_label(column)}{row}",
                    "row": row,
                    "column": column,
                    "styleIndex": self._regex_first(attrs, r'\bs="([^"]+)"'),
                    "hasWidget": "<Widget" in cell_xml,
                    "hasFormula": "<Formula" in cell_xml or "=&" in cell_xml or "formula" in cell_xml.lower(),
                    "hasDataColumn": "<DSColumn" in cell_xml or "<DataColumn" in cell_xml or "ds1." in cell_xml,
                    "textPreview": self._limit_text(self._strip_xml(cell_xml), 80),
                }
            )
            if len(cells) >= 160:
                break

        datasets = []
        for match in re.finditer(r"<TableData\b([^>]*\bname=\"([^\"]+)\"[^>]*)>(.*?)</TableData>", source_xml, flags=re.S | re.I):
            body = match.group(3)
            query_match = re.search(r"<Query\b[^>]*>(.*?)</Query>", body, flags=re.S | re.I)
            datasets.append(
                {
                    "selector": f"TableData[name=\"{match.group(2)}\"]",
                    "name": match.group(2),
                    "hasQuery": query_match is not None,
                    "queryPreview": self._limit_text(self._strip_xml(query_match.group(1)) if query_match else "", 500),
                }
            )
            if len(datasets) >= 40:
                break

        parameters = []
        parameter_xml = "\n".join(self._extract_tag_xml_blocks(source_xml, "ReportParameterAttr", limit=2))
        for name in re.findall(r'\bname="([^"]+)"', parameter_xml):
            if name not in parameters:
                parameters.append(name)
            if len(parameters) >= 80:
                break

        widgets = []
        for match in re.finditer(r"<Widget\b([^>]*)(?:/>|>.*?</Widget>)", source_xml, flags=re.S | re.I):
            attrs = match.group(1)
            widgets.append(
                {
                    "selector": f"Widget[{len(widgets) + 1}]",
                    "class": self._regex_first(attrs, r'\bclass="([^"]+)"') or self._regex_first(attrs, r'\bwidgetName="([^"]+)"'),
                    "name": self._regex_first(attrs, r'\bname="([^"]+)"') or self._regex_first(attrs, r'\bwidgetName="([^"]+)"'),
                }
            )
            if len(widgets) >= 80:
                break

        return {
            "available": True,
            "indexPolicy": "索引是省 token 的导航图，不是读取或修改边界；需求涉及多处时可以继续使用片段、selector 或 full_replace 覆盖相关区域。",
            "workbook": {
                "sizeChars": len(source_xml),
                "cellCountIndexed": len(cells),
                "styleCountApprox": len(re.findall(r"<Style\b", source_xml, flags=re.I)),
                "hasReportWriteAttr": bool(re.search(r"<ReportWriteAttr\b", source_xml, flags=re.I)),
                "hasReportWebAttr": bool(re.search(r"<ReportWebAttr\b", source_xml, flags=re.I)),
                "scriptTagCount": len(re.findall(r"<(?:JavaScript|Event)\b", source_xml, flags=re.I)),
            },
            "cells": cells,
            "datasets": datasets,
            "parameters": parameters,
            "widgets": widgets,
        }

    def _build_report_layout_context(self, structure: FrReportFileStructureRead) -> dict[str, Any]:
        sheet = structure.document.sheets[0] if structure.document and structure.document.sheets else None
        if not sheet:
            return {"available": False, "cells": [], "semanticCells": []}
        cells = list(sheet.cells or [])
        cell_map = {(cell.row, cell.column): cell for cell in cells}
        non_empty = [
            cell
            for cell in cells
            if cell.text not in (None, "")
            or cell.formula not in (None, "")
            or cell.dataColumn is not None
            or cell.fieldBinding is not None
            or cell.widget is not None
        ]
        non_empty.sort(key=lambda item: (item.row, item.column))

        def compact_cell(cell: FrReportCellRead) -> dict[str, Any]:
            return {
                "address": cell.address,
                "row": cell.row,
                "column": cell.column,
                "text": cell.text,
                "formula": cell.formula,
                "rowSpan": cell.rowSpan,
                "colSpan": cell.colSpan,
                "dataColumn": cell.dataColumn.model_dump(mode="json") if cell.dataColumn else None,
                "fieldBinding": cell.fieldBinding.model_dump(mode="json") if cell.fieldBinding else None,
                "widget": cell.widget.model_dump(mode="json") if cell.widget else None,
            }

        semantic_cells: list[dict[str, Any]] = []
        for cell in non_empty[:180]:
            upper_headers = [
                value
                for row in range(1, cell.row)
                if (value := self._cell_context_text(cell_map.get((row, cell.column))))
            ][-6:]
            left_headers = [
                value
                for column in range(1, cell.column)
                if (value := self._cell_context_text(cell_map.get((cell.row, column))))
            ][-6:]
            semantic_cells.append(
                {
                    **compact_cell(cell),
                    "upperHeaders": upper_headers,
                    "leftHeaders": left_headers,
                    "semanticHint": " / ".join([*upper_headers, *left_headers, self._cell_context_text(cell) or ""]),
                }
            )

        rows: list[dict[str, Any]] = []
        for row_index in sorted({cell.row for cell in non_empty})[:40]:
            row_cells = [
                compact_cell(cell)
                for cell in sorted((item for item in non_empty if item.row == row_index), key=lambda item: item.column)[:24]
            ]
            rows.append({"row": row_index, "cells": row_cells})

        return {
            "available": True,
            "sheetName": sheet.name,
            "rowCount": sheet.rowCount,
            "columnCount": sheet.columnCount,
            "policy": "这是当前报表的实际单元格布局。修改数据绑定或填写数据时，必须按表头链和现有数据区域定位，不得按自然语言顺序猜列。",
            "rows": rows,
            "semanticCells": semantic_cells[:180],
        }

    def _cell_context_text(self, cell: FrReportCellRead | None) -> str | None:
        if not cell:
            return None
        for value in (cell.text, cell.formula):
            if value not in (None, ""):
                return str(value)
        if cell.dataColumn:
            return f"{cell.dataColumn.dataset}.{cell.dataColumn.field}"
        if cell.fieldBinding:
            return cell.fieldBinding.expression
        return None

    async def _build_database_source_context(
        self,
        *,
        prompt: str,
        structure: FrReportFileStructureRead,
        source_xml: str | None,
    ) -> dict[str, Any]:
        table_names = self._extract_database_table_names_for_context(prompt, structure, source_xml)
        if not table_names:
            return {"available": False, "tableNames": [], "reason": "未从用户需求或当前数据集 SQL 中识别到数据库表名"}

        schema, warnings, errors = await sqlserver_query_service.inspect_tables_schema(table_names)
        samples: dict[str, list[dict[str, Any]]] = {}
        sample_errors: list[str] = []
        for table_name in self._table_names_from_resolved_schema(schema):
            try:
                rows, _columns = await asyncio.to_thread(
                    sqlserver_query_service._execute_sample_query,
                    f"SELECT TOP 5 * FROM {table_name}",
                )
                samples[table_name] = rows[:5]
            except Exception as exc:
                logger.warning(f"FineReport AI 表样例查询失败 {table_name}：{exc}")
                sample_errors.append(f"{table_name}: {exc}")

        return {
            "available": bool(schema),
            "tableNames": table_names,
            "schema": schema,
            "sampleRows": samples,
            "warnings": warnings,
            "errors": [*errors, *sample_errors],
            "policy": "数据库字段、日期字段和样例值必须以这里的真实结构为准；没有出现在 schema.fields 中的字段不得编造。",
        }

    def _extract_database_table_names_for_context(
        self,
        prompt: str,
        structure: FrReportFileStructureRead,
        source_xml: str | None,
    ) -> list[str]:
        texts = [prompt or ""]
        for dataset in structure.datasets[:20]:
            if dataset.querySql:
                texts.append(dataset.querySql)
        if source_xml:
            for match in re.finditer(r"<(?:Query|SQL)\b[^>]*>(.*?)</(?:Query|SQL)>", source_xml, flags=re.S | re.I):
                texts.append(self._strip_xml(match.group(1)))
        candidates: list[str] = []
        for text in texts:
            candidates.extend(self._extract_sql_from_join_tables(text))
            candidates.extend(re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*\b", text))
            candidates.extend(
                item
                for item in re.findall(r"\b[A-Za-z_][A-Za-z0-9_]{2,}\b", text)
                if "_" in item and item.lower() not in self._sql_reserved_words()
            )
        result: list[str] = []
        for candidate in candidates:
            normalized = candidate.strip().strip("[]`\"")
            if not normalized or normalized.lower() in self._sql_reserved_words():
                continue
            if not self._looks_like_database_table_name(normalized):
                continue
            if normalized not in result:
                result.append(normalized)
            if len(result) >= 6:
                break
        return result

    def _extract_sql_from_join_tables(self, text: str) -> list[str]:
        return [
            match.group(1).strip("[]`\"")
            for match in re.finditer(
                r"\b(?:from|join)\s+([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)?)",
                text,
                flags=re.I,
            )
        ]

    def _table_names_from_resolved_schema(self, schema: dict[str, Any] | None) -> list[str]:
        if not schema:
            return []
        if schema.get("tableName") and schema.get("tableName") != "__join__":
            return [str(schema["tableName"])]
        return [str(item.get("tableName")) for item in list(schema.get("tables") or []) if item.get("tableName")]

    def _looks_like_database_table_name(self, value: str) -> bool:
        parts = value.split(".")
        return 1 <= len(parts) <= 2 and all(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", part) for part in parts)

    def _sql_reserved_words(self) -> set[str]:
        return {
            "select",
            "from",
            "where",
            "join",
            "left",
            "right",
            "inner",
            "outer",
            "on",
            "and",
            "or",
            "as",
            "case",
            "when",
            "then",
            "else",
            "end",
            "top",
            "order",
            "group",
            "by",
            "price1",
            "price2",
        }

    async def _build_operation_experience_context(
        self,
        db: AsyncSession,
        user_id: int,
        object_path: str,
        prompt: str | None,
    ) -> dict[str, Any]:
        statement = (
            select(FrReportOperationDraft)
            .where(
                FrReportOperationDraft.user_id == user_id,
                FrReportOperationDraft.object_path == object_path,
                FrReportOperationDraft.status == "applied",
                FrReportOperationDraft.is_deleted == 0,
            )
            .order_by(FrReportOperationDraft.id.desc())
            .limit(8)
        )
        rows = list((await db.exec(statement)).all())
        if not rows:
            return {"available": False, "items": []}

        prompt_terms = {term for term in re.split(r"\W+", str(prompt or "").lower()) if len(term) >= 2}
        items: list[dict[str, Any]] = []
        for row in rows:
            operations = row.operations if isinstance(row.operations, list) else []
            xml_patch_operations = [item for item in operations if isinstance(item, dict) and item.get("operationType") == "xml_patch"]
            if not xml_patch_operations:
                continue
            searchable = " ".join(
                [
                    str(row.prompt or ""),
                    str(row.assistant_message or ""),
                    " ".join(str(item.get("summary") or "") for item in xml_patch_operations),
                ]
            ).lower()
            score = sum(1 for term in prompt_terms if term in searchable)
            items.append(
                {
                    "prompt": self._limit_text(row.prompt or "", 220),
                    "assistantSummary": self._limit_text(row.assistant_message or "", 260),
                    "operationCount": len(xml_patch_operations),
                    "selectors": self._xml_patch_selectors(xml_patch_operations),
                    "riskLevels": sorted({str(item.get("riskLevel") or "low") for item in xml_patch_operations}),
                    "score": score,
                }
            )

        items.sort(key=lambda item: (item["score"], item["operationCount"]), reverse=True)
        return {
            "available": bool(items),
            "loadPolicy": "这是按需检索到的同报表历史成功修改摘要，不进入系统提示词；只在与当前需求相关时参考，当前 CPT 原文和当前用户要求优先。",
            "items": items[:3],
        }

    def _regex_first(self, text: str, pattern: str) -> str | None:
        match = re.search(pattern, text, flags=re.S | re.I)
        return match.group(1) if match else None

    def _strip_xml(self, xml: str) -> str:
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", xml)).strip()

    def _xml_patch_selectors(self, operations: list[dict[str, Any]]) -> list[str]:
        selectors: list[str] = []
        for operation in operations[:6]:
            payload = operation.get("payload") if isinstance(operation.get("payload"), dict) else {}
            patches = payload.get("patches") if isinstance(payload.get("patches"), list) else [payload]
            for patch in patches[:8]:
                if not isinstance(patch, dict):
                    continue
                selector = str(patch.get("selector") or patch.get("target") or patch.get("action") or "").strip()
                if selector and selector not in selectors:
                    selectors.append(selector)
        return selectors[:12]

    def _extract_cell_xml(self, xml: str, row: int, column: int) -> str | None:
        pattern = re.compile(rf"<C\b(?=[^>]*\bc=\"{column - 1}\")(?=[^>]*\br=\"{row - 1}\")[^>]*>.*?</C>", flags=re.S | re.I)
        match = pattern.search(xml)
        return match.group(0) if match else None

    def _extract_tag_xml_blocks(self, xml: str, tag: str, limit: int = 1) -> list[str]:
        pattern = re.compile(rf"<{re.escape(tag)}\b[^>]*(?:/>|>.*?</{re.escape(tag)}>)", flags=re.S | re.I)
        return [match.group(0) for match in list(pattern.finditer(xml))[:limit]]

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
                        "rawTag": cell.rawTag,
                        "rawPath": cell.rawPath,
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
        for raw in list(raw_operations or [])[:12]:
            if not isinstance(raw, dict):
                warnings.append("已忽略一个非对象操作。")
                continue
            operation_type = str(raw.get("operationType") or "")
            if operation_type not in ALLOWED_OPERATION_TYPES:
                warnings.append(f"已忽略不可应用的修改项：{operation_type or '空类型'}。")
                continue
            payload = dict(raw.get("payload") or {})
            risk_level = str(raw.get("riskLevel") or "low")
            if risk_level not in {"low", "medium", "high"}:
                risk_level = "medium"
            risk_level = self._max_risk_level([risk_level, self._infer_operation_risk(operation_type, payload)])
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
        if cells:
            patch["cells"] = cells
        xml_diffs = self._xml_diff_previews(operations)
        if xml_diffs:
            patch["xmlDiffs"] = xml_diffs
        return patch

    def _xml_diff_previews(self, operations: list[FrReportAiOperationRead]) -> list[dict[str, Any]]:
        diffs: list[dict[str, Any]] = []
        for operation in operations:
            if operation.operationType != "xml_patch":
                continue
            patches = operation.payload.get("patches") if isinstance(operation.payload.get("patches"), list) else [operation.payload]
            for patch in patches[:12]:
                if not isinstance(patch, dict):
                    continue
                diffs.append(
                    {
                        "action": str(patch.get("action") or patch.get("op") or "replace"),
                        "selector": str(patch.get("selector") or patch.get("target") or operation.target or ""),
                        "oldPreview": self._limit_text(str(patch.get("oldXml") or ""), 800),
                        "newPreview": self._limit_text(str(patch.get("newXml") or patch.get("xml") or ""), 1200),
                    }
                )
        return diffs[:20]

    def _infer_operation_risk(self, operation_type: str, payload: dict[str, Any]) -> str:
        patches = payload.get("patches") if isinstance(payload.get("patches"), list) else [payload]
        levels: list[str] = []
        for patch in patches[:12]:
            if not isinstance(patch, dict):
                continue
            action = str(patch.get("action") or patch.get("op") or "replace").lower()
            selector = str(patch.get("selector") or patch.get("target") or "").lower()
            new_xml = str(patch.get("newXml") or patch.get("xml") or "").lower()
            combined = f"{selector}\n{new_xml}"
            if action == "full_replace" or "<workbook" in new_xml:
                levels.append("high")
            elif any(token in combined for token in ("stylelist", "reportwriteattr", "reportwebattr", "javascript", "<event", "script")):
                levels.append("high")
            elif action == "delete" or any(token in combined for token in ("tabledata", "query", "reportparameterattr", "parameterui", "widget")):
                levels.append("medium")
            else:
                levels.append("low")
        return self._max_risk_level(levels or ["low"])

    def _operation_risk_warnings(self, operations: list[FrReportAiOperationRead]) -> list[str]:
        max_risk = self._max_operation_risk(operations)
        if max_risk == "high":
            return ["本轮包含高风险 CPT XML 修改，可能影响样式、填报、脚本、数据集或整份 WorkBook；应用前需要用户确认，并保留版本回档。"]
        if max_risk == "medium":
            return ["本轮包含中风险 CPT XML 修改，应用前需要用户确认；生成 CPT 前仍会进行版本归档、冲突检测和预览校验。"]
        return []

    def _max_operation_risk(self, operations: list[FrReportAiOperationRead]) -> str:
        return self._max_risk_level([item.riskLevel for item in operations] or ["low"])

    def _max_risk_level(self, levels: list[str]) -> str:
        order = {"low": 0, "medium": 1, "high": 2}
        normalized = [level if level in order else "medium" for level in levels]
        return max(normalized, key=lambda level: order[level])

    def _unsupported_snapshot_operation_warnings(
        self,
        operations: list[FrReportAiOperationRead],
    ) -> list[str]:
        warnings: list[str] = []
        unsupported = [item for item in operations if item.operationType not in SNAPSHOT_APPLY_OPERATION_TYPES]
        if not unsupported:
            return warnings
        labels = "、".join(f"{item.operationType}({item.summary})" for item in unsupported[:6])
        warnings.append(
            "返回内容包含不可直接应用的修改项，已忽略且不会写入 CPT："
            f"{labels}。请重新生成待应用修改项。"
        )
        return warnings

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
    ) -> tuple[dict[str, Any], list[str]]:
        result = json.loads(json.dumps(document_snapshot, ensure_ascii=False))
        if preview_patch:
            result.setdefault("aiPreviewPatch", preview_patch)
        result["aiXmlPatchOperations"] = [item.model_dump(mode="json") for item in operations if item.operationType == "xml_patch"]
        return result, []

    def _apply_cell_style(
        self,
        snapshot: dict[str, Any],
        operation: FrReportAiOperationRead,
    ) -> None:
        style_patch = operation.payload.get("style")
        if not isinstance(style_patch, dict):
            return
        cell = self._ensure_snapshot_cell(snapshot, operation)
        if cell is None:
            return
        style = dict(cell.get("style") or {})
        style.update(style_patch)
        cell["style"] = style
        cell["aiModified"] = True

    def _apply_cell_value(
        self,
        snapshot: dict[str, Any],
        operation: FrReportAiOperationRead,
        as_formula: bool,
    ) -> list[str]:
        cell = self._ensure_snapshot_cell(snapshot, operation)
        if cell is None:
            return [f"{operation.operationType} 未识别到目标单元格，已跳过。"]
        raw_value = (
            operation.payload.get("formula")
            if as_formula
            else operation.payload.get("text")
            or operation.payload.get("value")
            or operation.payload.get("content")
        )
        if raw_value is None:
            raw_value = operation.payload.get("value") if as_formula else None
        if raw_value is None:
            return [f"{operation.operationType} 未提供单元格内容，已跳过。"]
        value = str(raw_value)
        if as_formula and not value.startswith("="):
            value = f"={value}"
        if as_formula:
            cell["formula"] = value
            cell["text"] = None
        else:
            cell["text"] = value
            cell["formula"] = None
        cell.pop("dataColumn", None)
        cell["aiModified"] = True
        return []

    def _apply_dataset_binding(
        self,
        snapshot: dict[str, Any],
        operation: FrReportAiOperationRead,
    ) -> list[str]:
        cell = self._ensure_snapshot_cell(snapshot, operation)
        if cell is None:
            return [f"{operation.operationType} 未识别到目标单元格，已跳过。"]
        payload = operation.payload
        dataset = str(payload.get("dataset") or payload.get("datasetName") or payload.get("dsName") or payload.get("sourceDataset") or "ds1")
        field = payload.get("field") or payload.get("column") or payload.get("fieldName") or payload.get("sourceField")
        if isinstance(field, str) and "." in field:
            field = field.rsplit(".", 1)[-1]
        field_name = self._normalize_parameter_name(field)
        if not field_name:
            return [f"{operation.operationType} 未提供可识别的数据字段，已跳过。"]
        expand_direction = self._normalize_expand_direction(payload.get("expandDirection") or payload.get("expand") or "down")
        cell["dataColumn"] = {
            "dataset": dataset,
            "field": field_name,
            "aggregation": payload.get("aggregation"),
            "expandDirection": expand_direction,
        }
        cell["text"] = None
        cell["formula"] = None
        cell["expandDirection"] = expand_direction
        cell["aiModified"] = True
        return []

    def _apply_cell_widget(
        self,
        snapshot: dict[str, Any],
        operation: FrReportAiOperationRead,
    ) -> list[str]:
        cell = self._ensure_snapshot_cell(snapshot, operation)
        if cell is None:
            return [f"{operation.operationType} 未识别到目标单元格，已跳过。"]
        cell["aiModified"] = True
        return []

    def _apply_cell_expand(
        self,
        snapshot: dict[str, Any],
        operation: FrReportAiOperationRead,
    ) -> list[str]:
        cell = self._ensure_snapshot_cell(snapshot, operation)
        if cell is None:
            return [f"{operation.operationType} 未识别到目标单元格，已跳过。"]
        cell["expandDirection"] = self._normalize_expand_direction(
            operation.payload.get("expandDirection") or operation.payload.get("expand") or operation.payload.get("direction")
        )
        cell["aiModified"] = True
        return []

    def _apply_cell_merge(
        self,
        snapshot: dict[str, Any],
        operation: FrReportAiOperationRead,
        merge: bool,
    ) -> list[str]:
        sheet = self._first_sheet(snapshot)
        cell_range = self._cell_range_from_operation(operation)
        if cell_range is None:
            return [f"{operation.operationType} 未识别到合并区域，已跳过。"]
        start_row, start_column, end_row, end_column = cell_range
        cell = self._ensure_snapshot_cell(snapshot, operation, start_row=start_row, start_column=start_column)
        if cell is None:
            return [f"{operation.operationType} 未识别到起始单元格，已跳过。"]
        merges = [item for item in list(sheet.get("merges") or []) if isinstance(item, dict)]
        if merge:
            cell["rowSpan"] = max(1, end_row - start_row + 1)
            cell["colSpan"] = max(1, end_column - start_column + 1)
            merges = [
                item
                for item in merges
                if not (
                    int(item.get("startRow") or 0) == start_row
                    and int(item.get("startColumn") or 0) == start_column
                )
            ]
            merges.append(
                {
                    "startRow": start_row,
                    "startColumn": start_column,
                    "endRow": end_row,
                    "endColumn": end_column,
                }
            )
        else:
            cell["rowSpan"] = 1
            cell["colSpan"] = 1
            merges = [
                item
                for item in merges
                if not (
                    int(item.get("startRow") or 0) <= start_row <= int(item.get("endRow") or 0)
                    and int(item.get("startColumn") or 0) <= start_column <= int(item.get("endColumn") or 0)
                )
            ]
        sheet["merges"] = merges
        cell["aiModified"] = True
        sheet["rowCount"] = max(int(sheet.get("rowCount") or 0), end_row)
        sheet["columnCount"] = max(int(sheet.get("columnCount") or 0), end_column)
        return []

    def _widget_class_for_type(self, widget_type: str) -> str:
        return {
            "number": "com.fr.form.ui.NumberEditor",
            "date": "com.fr.form.ui.DateEditor",
            "combo": "com.fr.form.ui.ComboBox",
            "text": "com.fr.form.ui.TextEditor",
        }.get(widget_type, "com.fr.form.ui.TextEditor")

    def _apply_sheet_dimension(
        self,
        snapshot: dict[str, Any],
        operation: FrReportAiOperationRead,
        dimension_type: str,
    ) -> list[str]:
        sheet = self._first_sheet(snapshot)
        key = "columns" if dimension_type == "column" else "rows"
        default_size = 88 if dimension_type == "column" else 36
        min_size = 24 if dimension_type == "column" else 16
        max_size = 600 if dimension_type == "column" else 240
        indices = self._dimension_indices_from_operation(operation, dimension_type)
        if not indices:
            label = "列" if dimension_type == "column" else "行"
            return [f"{operation.operationType} 没有识别到要调整的{label}，已跳过尺寸写入。"]

        current = {
            int(item.get("index")): dict(item)
            for item in list(sheet.get(key) or [])
            if isinstance(item, dict) and self._positive_int(item.get("index"))
        }
        for index in indices[:20]:
            old_size = self._positive_int(current.get(index, {}).get("size")) or default_size
            new_size = self._dimension_size_from_operation(operation, old_size, dimension_type)
            if new_size is None:
                label = "宽度" if dimension_type == "column" else "高度"
                return [f"{operation.operationType} 没有识别到新的{label}或倍数，已跳过尺寸写入。"]
            current[index] = {
                "index": index,
                "size": max(min_size, min(max_size, int(round(new_size)))),
                "aiModified": True,
            }
        sheet[key] = sorted(current.values(), key=lambda item: int(item.get("index") or 0))
        count_key = "columnCount" if dimension_type == "column" else "rowCount"
        sheet[count_key] = max(int(sheet.get(count_key) or 0), max(indices))
        return []

    def _dimension_indices_from_operation(self, operation: FrReportAiOperationRead, dimension_type: str) -> list[int]:
        payload = operation.payload if isinstance(operation.payload, dict) else {}
        raw_values: list[Any] = []
        if dimension_type == "column":
            for key in ("columns", "columnIndexes", "columnIndices"):
                value = payload.get(key)
                if isinstance(value, list):
                    raw_values.extend(value)
            raw_values.extend(
                [
                    payload.get("column"),
                    payload.get("columnIndex"),
                    payload.get("columnNumber"),
                    payload.get("index"),
                    payload.get("cell"),
                    operation.target,
                ]
            )
        else:
            for key in ("rows", "rowIndexes", "rowIndices"):
                value = payload.get(key)
                if isinstance(value, list):
                    raw_values.extend(value)
            raw_values.extend(
                [
                    payload.get("row"),
                    payload.get("rowIndex"),
                    payload.get("rowNumber"),
                    payload.get("index"),
                    payload.get("cell"),
                    operation.target,
                ]
            )

        indices: list[int] = []
        for raw in raw_values:
            index = self._dimension_index(raw, dimension_type)
            if index and index not in indices:
                indices.append(index)
        return indices

    def _dimension_index(self, raw: Any, dimension_type: str) -> int | None:
        if raw is None:
            return None
        if isinstance(raw, int):
            return raw if raw > 0 else None
        text = str(raw).strip()
        if not text:
            return None
        cell_match = re.fullmatch(r"\$?([A-Za-z]{1,3})\$?([0-9]{1,7})", text)
        if cell_match:
            return self._column_index(cell_match.group(1)) if dimension_type == "column" else int(cell_match.group(2))
        if dimension_type == "column":
            column_match = re.fullmatch(r"[A-Za-z]{1,3}", text)
            if column_match:
                return self._column_index(text)
            column_text_match = re.search(r"第?\s*([A-Za-z]{1,3})\s*列", text, flags=re.IGNORECASE)
            if column_text_match:
                return self._column_index(column_text_match.group(1))
        row_text_match = re.search(r"第?\s*([0-9]{1,7})\s*[行列]?", text)
        if row_text_match:
            return int(row_text_match.group(1))
        return self._positive_int(text)

    def _dimension_size_from_operation(
        self,
        operation: FrReportAiOperationRead,
        old_size: int,
        dimension_type: str,
    ) -> int | None:
        payload = operation.payload if isinstance(operation.payload, dict) else {}
        size_keys = (
            ("width", "size", "px", "value", "newWidth", "targetWidth")
            if dimension_type == "column"
            else ("height", "size", "px", "value", "newHeight", "targetHeight")
        )
        for key in size_keys:
            size = self._positive_int(payload.get(key))
            if size:
                return size
        factor = self._dimension_factor_from_operation(operation)
        if factor:
            return int(round(old_size * factor))
        return None

    def _dimension_factor_from_operation(self, operation: FrReportAiOperationRead) -> float | None:
        payload = operation.payload if isinstance(operation.payload, dict) else {}
        for key in ("factor", "scale", "multiplier", "multiple"):
            value = payload.get(key)
            try:
                factor = float(str(value).replace("倍", "").strip())
            except (TypeError, ValueError):
                continue
            if factor > 0:
                return min(factor, 8.0)
        text = f"{operation.summary or ''} {operation.target or ''} {payload.get('description') or ''} {payload.get('size') or ''}"
        if re.search(r"两倍|2\s*倍|翻倍|扩大一倍", text):
            return 2.0
        if re.search(r"一半|减半|0\.5\s*倍", text):
            return 0.5
        match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*倍", text)
        if match:
            return min(float(match.group(1)), 8.0)
        return None

    def _is_combo_widget_operation(self, operation: FrReportAiOperationRead) -> bool:
        payload = operation.payload if isinstance(operation.payload, dict) else {}
        widget = payload.get("widget") if isinstance(payload.get("widget"), dict) else {}
        text = " ".join(
            str(item or "")
            for item in (
                widget.get("widgetClass"),
                widget.get("widgetType"),
                payload.get("widgetType"),
                operation.summary,
            )
        )
        return bool(widget) and self._normalize_widget_type(text) == "combo"

    def _apply_parameter_panel(
        self,
        snapshot: dict[str, Any],
        operation: FrReportAiOperationRead,
    ) -> list[str]:
        warnings: list[str] = []
        remove_parameters = self._removed_parameter_names_from_payload(operation.payload, operation.summary)
        for name in remove_parameters:
            self._remove_snapshot_parameter(snapshot, name)

        panel = operation.payload.get("parameterPanel")
        raw_parameters = (
            operation.payload.get("parameters")
            or operation.payload.get("widgets")
            or operation.payload.get("modifyWidgets")
            or operation.payload.get("modifyParameters")
        )
        if isinstance(panel, dict):
            raw_parameters = (
                panel.get("widgets")
                or panel.get("parameters")
                or panel.get("modifyWidgets")
                or panel.get("modifyParameters")
                or raw_parameters
            )
        if not isinstance(raw_parameters, list):
            single_parameter = self._single_parameter_from_operation(operation)
            if single_parameter:
                raw_parameters = [single_parameter]
        if not isinstance(raw_parameters, list):
            if not remove_parameters:
                warnings.append(f"{operation.operationType} 未提供可识别的参数控件列表，已跳过参数栏写入。")
            return warnings

        current_parameters = {
            str(item.get("name") or item.get("widgetName")): dict(item)
            for item in list(snapshot.get("aiParameters") or [])
            if isinstance(item, dict)
            and (item.get("name") or item.get("widgetName"))
            and not self._is_cell_address_parameter(self._normalize_parameter_name(item.get("name") or item.get("widgetName")))
        }
        for raw in raw_parameters[:16]:
            if not isinstance(raw, dict):
                continue
            dictionary = raw.get("dataDictionary") if isinstance(raw.get("dataDictionary"), dict) else {}
            name = self._normalize_parameter_name(
                raw.get("name")
                or raw.get("widgetName")
                or dictionary.get("column")
                or dictionary.get("field")
                or dictionary.get("valueField")
                or dictionary.get("textField")
                or dictionary.get("labelField")
            )
            if not name:
                warnings.append(f"已忽略无法识别名称的参数控件：{raw}")
                continue
            if self._is_cell_address_parameter(name):
                warnings.append(f"已忽略疑似单元格坐标的参数名：{name}")
                continue
            widget_type = self._normalize_widget_type(raw.get("widgetType") or raw.get("widgettype") or raw.get("type"))
            dictionary_column = (
                dictionary.get("column")
                or dictionary.get("field")
                or dictionary.get("valueField")
                or dictionary.get("textField")
                or dictionary.get("labelField")
                or name
            )
            data_dictionary = (
                {
                    "dataset": str(dictionary.get("dataset") or dictionary.get("datasetName") or "ds1"),
                    "column": str(dictionary_column),
                    "valueField": str(dictionary.get("valueField") or dictionary_column),
                    "textField": str(dictionary.get("textField") or dictionary.get("labelField") or dictionary_column),
                }
                if dictionary
                else None
            )
            parameter = {
                "name": name,
                "label": str(raw.get("label") or self._humanize_parameter_label(name)),
                "widgetType": widget_type,
                "defaultValue": raw.get("defaultValue") if raw.get("defaultValue") is not None else raw.get("default"),
                "dataDictionary": data_dictionary,
            }
            current_parameters[name] = {key: value for key, value in parameter.items() if value is not None}

        if not current_parameters:
            warnings.append("参数栏操作没有形成有效参数，已跳过。")
            return warnings

        snapshot["aiParameters"] = list(current_parameters.values())
        self._merge_dataset_parameters(snapshot, snapshot["aiParameters"])
        snapshot["aiParameterPanel"] = {
            "enabled": True,
            "layout": "horizontal",
            "sourceOperation": operation.operationType,
            "updateTime": datetime.now().isoformat(timespec="seconds"),
        }
        return warnings

    def _single_parameter_from_operation(self, operation: FrReportAiOperationRead) -> dict[str, Any] | None:
        payload = operation.payload if isinstance(operation.payload, dict) else {}
        dictionary = payload.get("dataDictionary") if isinstance(payload.get("dataDictionary"), dict) else {}
        name = self._normalize_parameter_name(
            operation.target
            or payload.get("name")
            or payload.get("widgetName")
            or payload.get("parameterName")
            or payload.get("controlName")
            or payload.get("field")
            or payload.get("column")
            or dictionary.get("column")
            or dictionary.get("field")
            or dictionary.get("valueField")
            or dictionary.get("textField")
            or dictionary.get("labelField")
        )
        widget_type = self._normalize_widget_type(payload.get("widgetType") or payload.get("widgettype") or payload.get("type") or payload.get("widgetClass"))
        if not name and widget_type == "text" and not dictionary:
            return None
        return {
            "name": name,
            "label": payload.get("label") or payload.get("caption") or (self._humanize_parameter_label(name) if name else None),
            "widgetType": widget_type,
            "defaultValue": payload.get("defaultValue") if payload.get("defaultValue") is not None else payload.get("default"),
            "dataDictionary": dictionary if dictionary else None,
        }

    def _apply_dataset_sql(
        self,
        snapshot: dict[str, Any],
        operation: FrReportAiOperationRead,
    ) -> list[str]:
        warnings: list[str] = []
        raw_sql = operation.payload.get("newSql") or operation.payload.get("proposedSql") or operation.payload.get("sql")
        if not isinstance(raw_sql, str) or not raw_sql.strip():
            warnings.append("SQL 操作没有提供新 SQL，已跳过 SQL 写入。")
            return warnings
        normalized_sql = raw_sql.strip()
        if "..." in normalized_sql or "…" in normalized_sql:
            warnings.append("模型返回的 SQL 含省略号或截断内容，已拒绝写入数据集 SQL。")
            return warnings
        if not self._is_safe_select_sql(normalized_sql):
            warnings.append("模型返回的 SQL 未通过只读查询校验，已拒绝写入数据集 SQL。")
            return warnings
        target_dataset = str(operation.target or "").strip()
        datasets = snapshot.get("datasets")
        if not isinstance(datasets, list) or not datasets:
            warnings.append("当前快照没有可更新的数据集，已跳过 SQL 写入。")
            return warnings
        target = None
        if target_dataset:
            for dataset in datasets:
                if isinstance(dataset, dict) and str(dataset.get("name") or "") == target_dataset:
                    target = dataset
                    break
        if target is None:
            target = datasets[0] if isinstance(datasets[0], dict) else None
        if target is None:
            warnings.append("未找到可更新的数据集，已跳过 SQL 写入。")
            return warnings
        target["querySql"] = normalized_sql
        target["aiModified"] = True
        self._sync_dataset_parameters_with_sql(snapshot, target, normalized_sql)
        self._merge_dataset_parameters(snapshot, snapshot.get("aiParameters") or [])
        return warnings

    def _sync_dataset_parameters_with_sql(self, snapshot: dict[str, Any], dataset: dict[str, Any], sql: str) -> None:
        referenced_names = self._extract_sql_parameters(sql)
        if not referenced_names:
            dataset["parameters"] = []
            snapshot["aiParameters"] = []
            return
        referenced = set(referenced_names)
        current_defaults = {
            self._normalize_parameter_name(item.get("name")): item.get("defaultValue")
            for item in list(dataset.get("parameters") or [])
            if isinstance(item, dict) and item.get("name")
        }
        dataset["parameters"] = [
            {"name": name, "defaultValue": current_defaults.get(name)}
            for name in referenced_names
        ]
        snapshot["aiParameters"] = [
            item
            for item in list(snapshot.get("aiParameters") or [])
            if isinstance(item, dict)
            and (name := self._normalize_parameter_name(item.get("name")))
            and name in referenced
            and not self._is_cell_address_parameter(name)
        ]
        removed = {
            name
            for name in current_defaults
            if name and name not in referenced
        }
        if removed:
            existing_removed = {
                self._normalize_parameter_name(item)
                for item in list(snapshot.get("aiRemovedParameters") or [])
                if self._normalize_parameter_name(item)
            }
            snapshot["aiRemovedParameters"] = sorted(existing_removed | removed)

    def _apply_data_column_filter(
        self,
        snapshot: dict[str, Any],
        operation: FrReportAiOperationRead,
    ) -> list[str]:
        payload = operation.payload
        widget = payload.get("widget") if isinstance(payload.get("widget"), dict) else {}
        widget_dictionary = widget.get("dataDictionary") if isinstance(widget.get("dataDictionary"), dict) else {}
        dictionary = payload.get("dataDictionary") if isinstance(payload.get("dataDictionary"), dict) else widget_dictionary
        raw_field = (
            payload.get("field")
            or payload.get("column")
            or payload.get("fieldName")
            or payload.get("sourceField")
            or dictionary.get("column")
            or dictionary.get("field")
            or dictionary.get("valueField")
            or dictionary.get("textField")
            or dictionary.get("labelField")
            or dictionary.get("keyField")
            or self._field_from_operation_summary(operation.summary)
            or operation.target
        )
        if isinstance(raw_field, str) and "." in raw_field:
            raw_field = raw_field.rsplit(".", 1)[-1]
        field_name = self._normalize_parameter_name(raw_field)
        if field_name and self._is_cell_address_parameter(field_name):
            field_name = None
        if not field_name:
            return [f"{operation.operationType} 未提供可识别的字段名，已跳过筛选控件写入。"]

        action_text = f"{operation.summary} {payload.get('action') or ''}"
        should_remove = bool(payload.get("remove") or payload.get("disabled") is True or payload.get("enabled") is False)
        if re.search(r"去掉|删除|移除|取消|不再|remove|delete|disable", action_text, flags=re.IGNORECASE):
            should_remove = True
        if should_remove:
            self._remove_snapshot_parameter(snapshot, field_name)
            return []

        dataset_name = str(
            dictionary.get("dataset")
            or dictionary.get("datasetName")
            or payload.get("dataset")
            or payload.get("sourceDataset")
            or payload.get("dataSet")
            or "ds1"
        )
        dictionary_column = str(
            dictionary.get("column")
            or dictionary.get("field")
            or dictionary.get("valueField")
            or dictionary.get("textField")
            or dictionary.get("labelField")
            or dictionary.get("keyField")
            or raw_field
            or field_name
        )
        current_parameters = {
            str(item.get("name")): dict(item)
            for item in list(snapshot.get("aiParameters") or [])
            if isinstance(item, dict)
            and item.get("name")
            and not self._is_cell_address_parameter(self._normalize_parameter_name(item.get("name")))
        }
        current_parameters[field_name] = {
            "name": field_name,
            "label": str(payload.get("label") or self._humanize_parameter_label(field_name)),
            "widgetType": "combo",
            "defaultValue": payload.get("defaultValue") if payload.get("defaultValue") is not None else "",
            "dataDictionary": {
                "dataset": dataset_name,
                "column": dictionary_column,
                "valueField": dictionary_column,
                "textField": dictionary_column,
            },
        }
        snapshot["aiParameters"] = list(current_parameters.values())
        snapshot["aiRemovedParameters"] = [
            item
            for item in list(snapshot.get("aiRemovedParameters") or [])
            if self._normalize_parameter_name(item) != field_name
        ]
        self._merge_dataset_parameters(snapshot, snapshot["aiParameters"])
        snapshot["aiParameterPanel"] = {
            "enabled": True,
            "layout": "horizontal",
            "sourceOperation": operation.operationType,
            "updateTime": datetime.now().isoformat(timespec="seconds"),
        }
        return []

    def _remove_snapshot_parameter(self, snapshot: dict[str, Any], name: str) -> None:
        normalized_name = self._normalize_parameter_name(name)
        if not normalized_name:
            return
        removed = {
            self._normalize_parameter_name(item)
            for item in list(snapshot.get("aiRemovedParameters") or [])
            if self._normalize_parameter_name(item)
        }
        removed.add(normalized_name)
        snapshot["aiRemovedParameters"] = sorted(removed)
        snapshot["aiParameters"] = [
            item
            for item in list(snapshot.get("aiParameters") or [])
            if not (isinstance(item, dict) and self._normalize_parameter_name(item.get("name")) == normalized_name)
        ]
        datasets = snapshot.get("datasets")
        if not isinstance(datasets, list):
            return
        for dataset in datasets:
            if not isinstance(dataset, dict):
                continue
            dataset["parameters"] = [
                item
                for item in list(dataset.get("parameters") or [])
                if not (isinstance(item, dict) and self._normalize_parameter_name(item.get("name")) == normalized_name)
            ]

    def _sanitize_snapshot_parameters(self, snapshot: dict[str, Any]) -> None:
        removed = self._snapshot_removed_parameters(snapshot)
        clean_parameters: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in list(snapshot.get("aiParameters") or []):
            if not isinstance(item, dict):
                continue
            name = self._normalize_parameter_name(item.get("name"))
            if not name or name in removed or self._is_cell_address_parameter(name) or name in seen:
                continue
            clean_item = dict(item)
            clean_item["name"] = name
            clean_parameters.append(clean_item)
            seen.add(name)
        snapshot["aiParameters"] = clean_parameters

        datasets = snapshot.get("datasets")
        if not isinstance(datasets, list):
            return
        for dataset in datasets:
            if not isinstance(dataset, dict):
                continue
            clean_dataset_parameters: list[dict[str, Any]] = []
            seen_dataset: set[str] = set()
            for item in list(dataset.get("parameters") or []):
                if not isinstance(item, dict):
                    continue
                name = self._normalize_parameter_name(item.get("name"))
                if not name or name in removed or self._is_cell_address_parameter(name) or name in seen_dataset:
                    continue
                clean_item = dict(item)
                clean_item["name"] = name
                clean_dataset_parameters.append(clean_item)
                seen_dataset.add(name)
            dataset["parameters"] = clean_dataset_parameters

    def _merge_dataset_parameters(self, snapshot: dict[str, Any], parameters: list[dict[str, Any]]) -> None:
        datasets = snapshot.get("datasets")
        if not isinstance(datasets, list):
            return
        for dataset in datasets:
            if not isinstance(dataset, dict):
                continue
            current = {
                str(item.get("name")): dict(item)
                for item in list(dataset.get("parameters") or [])
                if isinstance(item, dict)
                and item.get("name")
                and not self._is_cell_address_parameter(self._normalize_parameter_name(item.get("name")))
            }
            for parameter in parameters:
                name = self._normalize_parameter_name(parameter.get("name"))
                if not name or self._is_cell_address_parameter(name):
                    continue
                current.setdefault(name, {"name": name, "defaultValue": parameter.get("defaultValue")})
            dataset["parameters"] = list(current.values())

    def _normalize_parameter_name(self, value: Any) -> str | None:
        raw = str(value or "").strip()
        if not raw:
            return None
        normalized = re.sub(r"[^0-9A-Za-z_]", "_", raw)
        normalized = re.sub(r"_+", "_", normalized).strip("_")
        normalized = re.sub(r"_(filter|widget|control|input)$", "", normalized, flags=re.I)
        if not normalized:
            return None
        if normalized[0].isdigit():
            normalized = f"p_{normalized}"
        return normalized[:64]

    def _positive_int(self, value: Any) -> int | None:
        if value is None:
            return None
        match = re.search(r"-?\d+", str(value))
        if not match:
            return None
        number = int(match.group())
        return number if number > 0 else None

    def _column_index(self, label: str) -> int | None:
        result = 0
        for char in str(label or "").upper():
            if not ("A" <= char <= "Z"):
                continue
            result = result * 26 + ord(char) - 64
        return result or None

    def _column_label(self, index: int) -> str:
        label = ""
        current = max(1, int(index or 1))
        while current > 0:
            current, remainder = divmod(current - 1, 26)
            label = chr(65 + remainder) + label
        return label or "A"

    def _cell_position_from_operation(self, operation: FrReportAiOperationRead) -> tuple[int, int] | None:
        payload = operation.payload if isinstance(operation.payload, dict) else {}
        for raw in (
            operation.target,
            payload.get("cell"),
            payload.get("address"),
            payload.get("targetCell"),
            payload.get("startCell"),
        ):
            position = self._parse_cell_address(raw)
            if position:
                return position
        row = self._positive_int(payload.get("row") or payload.get("rowIndex"))
        column = self._dimension_index(payload.get("column") or payload.get("columnIndex"), "column")
        if row and column:
            return row, column
        return None

    def _parse_cell_address(self, raw: Any) -> tuple[int, int] | None:
        if raw is None:
            return None
        text = str(raw).strip()
        if not text:
            return None
        if ":" in text:
            text = text.split(":", 1)[0]
        match = re.fullmatch(r"\$?([A-Za-z]{1,3})\$?([0-9]{1,7})", text)
        if not match:
            return None
        column = self._column_index(match.group(1))
        row = int(match.group(2))
        return (row, column) if column and row > 0 else None

    def _cell_range_from_operation(self, operation: FrReportAiOperationRead) -> tuple[int, int, int, int] | None:
        payload = operation.payload if isinstance(operation.payload, dict) else {}
        raw_range = payload.get("range") or payload.get("cellRange") or operation.target
        if isinstance(raw_range, str) and ":" in raw_range:
            start_raw, end_raw = raw_range.split(":", 1)
            start = self._parse_cell_address(start_raw)
            end = self._parse_cell_address(end_raw)
            if start and end:
                start_row, start_column = start
                end_row, end_column = end
                return min(start_row, end_row), min(start_column, end_column), max(start_row, end_row), max(start_column, end_column)
        start = self._parse_cell_address(payload.get("startCell") or operation.target)
        end = self._parse_cell_address(payload.get("endCell"))
        if start and end:
            start_row, start_column = start
            end_row, end_column = end
            return min(start_row, end_row), min(start_column, end_column), max(start_row, end_row), max(start_column, end_column)
        if start:
            start_row, start_column = start
            row_span = self._positive_int(payload.get("rowSpan") or payload.get("rows")) or 1
            col_span = self._positive_int(payload.get("colSpan") or payload.get("columns")) or 1
            return start_row, start_column, start_row + row_span - 1, start_column + col_span - 1
        return None

    def _ensure_snapshot_cell(
        self,
        snapshot: dict[str, Any],
        operation: FrReportAiOperationRead,
        start_row: int | None = None,
        start_column: int | None = None,
    ) -> dict[str, Any] | None:
        sheet = self._first_sheet(snapshot)
        if start_row is None or start_column is None:
            position = self._cell_position_from_operation(operation)
            if position is None:
                return None
            start_row, start_column = position
        cells = sheet.setdefault("cells", [])
        address = f"{self._column_label(start_column)}{start_row}"
        for cell in cells:
            if isinstance(cell, dict) and str(cell.get("address") or "").upper() == address.upper():
                return cell
        cell = {
            "row": start_row,
            "column": start_column,
            "address": address,
            "text": "",
            "rowSpan": 1,
            "colSpan": 1,
            "style": {},
        }
        cells.append(cell)
        sheet["rowCount"] = max(int(sheet.get("rowCount") or 0), start_row)
        sheet["columnCount"] = max(int(sheet.get("columnCount") or 0), start_column)
        return cell

    def _normalize_expand_direction(self, value: Any) -> str:
        text = str(value or "").strip().lower()
        if text in {"right", "horizontal", "横向", "向右", "列扩展"}:
            return "right"
        if text in {"none", "fixed", "不扩展", "固定"}:
            return "none"
        return "down"

    def _is_cell_address_parameter(self, name: str | None) -> bool:
        if not name:
            return False
        return bool(re.fullmatch(r"[A-Za-z]{1,3}[0-9]{1,7}", str(name).strip()))

    def _field_from_operation_summary(self, summary: str | None) -> str | None:
        text = str(summary or "")
        for pattern in (
            r"ds1\.([A-Za-z_][A-Za-z0-9_]*)",
            r"ds1中的([A-Za-z_][A-Za-z0-9_]*)字段",
            r"字段为([A-Za-z_][A-Za-z0-9_]*)",
            r"使用([A-Za-z_][A-Za-z0-9_]*)字段",
        ):
            match = re.search(pattern, text)
            if match:
                return match.group(1)
        return None

    def _normalize_widget_type(self, value: Any) -> str:
        text = str(value or "").strip().lower()
        if "date" in text or "日期" in text:
            return "date"
        if "combo" in text or "select" in text or "dropdown" in text or "下拉" in text or "选择" in text:
            return "combo"
        if "number" in text or "数字" in text or "数值" in text:
            return "number"
        return "text"

    def _is_safe_select_sql(self, sql: str) -> bool:
        compact = re.sub(r"/\*.*?\*/", " ", sql, flags=re.S)
        compact = re.sub(r"--.*?$", " ", compact, flags=re.M)
        lowered = compact.lower()
        forbidden = (
            " insert ",
            " update ",
            " delete ",
            " drop ",
            " alter ",
            " truncate ",
            " merge ",
            " exec ",
            " execute ",
            " create ",
            " grant ",
            " revoke ",
        )
        padded = f" {lowered} "
        if any(keyword in padded for keyword in forbidden):
            return False
        statements = [item.strip() for item in compact.split(";") if item.strip()]
        if not statements:
            return lowered.strip().startswith(("select", "with"))
        if len(statements) == 1:
            return statements[0].lower().startswith(("select", "with"))
        declarations = statements[:-1]
        final_statement = statements[-1].lower()
        if not final_statement.startswith(("select", "with")):
            return False
        return all(
            re.fullmatch(
                r"declare\s+@[a-z_][a-z0-9_]*\s+[a-z0-9_()]+(?:\s*=\s*(?:'[^']*'|n'[^']*'|null))?",
                declaration,
                flags=re.IGNORECASE,
            )
            for declaration in declarations
        )

    def _hash_payload(self, payload: dict[str, Any]) -> str:
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
        return sha256(raw.encode("utf-8")).hexdigest()

    async def _build_snapshot_cpt_bytes(
        self,
        snapshot: FrReportSnapshot,
        target_object_path: str,
        operations: list[dict[str, Any]],
    ) -> tuple[bytes, list[str]]:
        warnings: list[str] = []
        if self._has_xml_patch_operation(operations):
            source_object_path = snapshot.object_path
            if await fr_minio_service.object_exists(source_object_path):
                source_bytes = await fr_minio_service.download_file(source_object_path)
                source_label = source_object_path
            elif await fr_minio_service.object_exists(target_object_path):
                source_bytes = await fr_minio_service.download_file(target_object_path)
                source_label = target_object_path
            else:
                raise ValueError("当前修改需要基于原 CPT XML 写入，但源 CPT 文件不存在。")
            try:
                patched = self._patch_existing_cpt_bytes(source_bytes, snapshot.document_snapshot or {}, operations)
                warnings.append(f"已基于源 CPT XML 增量写入 {len(operations)} 个待应用修改项，源文件：{source_label}。")
                return patched, warnings
            except Exception as exc:
                logger.exception(f"增量写入 FineReport CPT 失败，已阻止重建覆盖: {exc}")
                raise ValueError(f"现有 CPT 增量写入失败：{exc}。已阻止用结构快照重建覆盖，避免原报表内容丢失。") from exc
        if target_object_path == snapshot.object_path and await fr_minio_service.object_exists(target_object_path):
            source_bytes = await fr_minio_service.download_file(target_object_path)
            try:
                patched = self._patch_existing_cpt_bytes(source_bytes, snapshot.document_snapshot or {}, operations)
                warnings.append("已基于当前 CPT XML 生成文件，未重建原报表内容。")
                return patched, warnings
            except Exception as exc:
                logger.exception(f"读取 FineReport CPT 失败，已阻止重建覆盖: {exc}")
                raise ValueError(f"现有 CPT 读取失败：{exc}。已阻止用结构快照重建覆盖，避免原报表内容丢失。") from exc
        warnings.append("目标路径不是当前源 CPT 或源文件不存在，使用结构快照生成新 CPT。")
        return self._snapshot_to_cpt_bytes(snapshot), warnings

    def _snapshot_xml_patch_operations(self, snapshot: FrReportSnapshot) -> list[dict[str, Any]]:
        document_snapshot = snapshot.document_snapshot if isinstance(snapshot.document_snapshot, dict) else {}
        raw_operations = document_snapshot.get("aiXmlPatchOperations")
        if not isinstance(raw_operations, list):
            return []
        return [item for item in raw_operations if isinstance(item, dict) and item.get("operationType") == "xml_patch"]

    def _patch_existing_cpt_bytes(
        self,
        source_bytes: bytes,
        document: dict[str, Any],
        operations: list[dict[str, Any]],
    ) -> bytes:
        text = source_bytes.decode("utf-8", errors="strict")
        text = self._apply_xml_patch_operations(text, operations)
        text = self._dedupe_table_data_blocks(text)
        text = self._ensure_table_data_parameters(text)
        return text.encode("utf-8")

    def _apply_xml_patch_operations(self, xml: str, operations: list[dict[str, Any]]) -> str:
        result = xml
        for operation in operations:
            if not isinstance(operation, dict) or operation.get("operationType") != "xml_patch":
                continue
            payload = operation.get("payload") if isinstance(operation.get("payload"), dict) else {}
            patches = payload.get("patches") if isinstance(payload.get("patches"), list) else [payload]
            for patch in self._coalesce_xml_insert_patches(patches[:12]):
                if not isinstance(patch, dict):
                    continue
                result = self._apply_single_xml_patch(result, patch)
        return result

    def _coalesce_xml_insert_patches(self, patches: list[Any]) -> list[Any]:
        merged: list[Any] = []
        for patch in patches:
            if not isinstance(patch, dict):
                merged.append(patch)
                continue
            action = str(patch.get("action") or patch.get("op") or "replace").strip()
            selector = str(patch.get("selector") or patch.get("target") or "").strip()
            new_xml = str(patch.get("newXml") or patch.get("xml") or "")
            if (
                action in {"insert_before", "insert_after"}
                and selector
                and new_xml
                and merged
                and isinstance(merged[-1], dict)
                and str(merged[-1].get("action") or merged[-1].get("op") or "").strip() == action
                and str(merged[-1].get("selector") or merged[-1].get("target") or "").strip() == selector
            ):
                key = "newXml" if "newXml" in merged[-1] else "xml"
                merged[-1][key] = f"{str(merged[-1].get(key) or '')}\n{new_xml}"
                continue
            merged.append(dict(patch))
        return merged

    def _apply_single_xml_patch(self, xml: str, patch: dict[str, Any]) -> str:
        action = str(patch.get("action") or patch.get("op") or "replace").strip()
        selector = str(patch.get("selector") or patch.get("target") or "").strip()
        if action not in {"replace", "insert_before", "insert_after", "delete", "full_replace"}:
            raise ValueError(f"不支持的 CPT XML patch 动作：{action}")
        new_xml = str(patch.get("newXml") or patch.get("xml") or "")
        if action == "full_replace":
            self._validate_full_cpt_xml(new_xml)
            return new_xml
        if not selector:
            raise ValueError("XML patch 缺少 selector")
        target_missing_table_data_map = False
        try:
            start, end = self._find_xml_patch_target(xml, selector)
        except ValueError:
            old_xml = str(patch.get("oldXml") or patch.get("old_xml") or "")
            if old_xml and old_xml in xml:
                start = xml.index(old_xml)
                end = start + len(old_xml)
            elif action in {"replace", "insert_before", "insert_after"} and self._selector_targets_table_data_map(selector):
                start = end = -1
                target_missing_table_data_map = True
            else:
                raise
        if action != "delete":
            new_xml = self._normalize_xml_patch_fragment(selector, new_xml)
            self._validate_xml_patch_fragment(new_xml)
        if action in {"insert_before", "insert_after"} and self._selector_targets_table_data_map(selector):
            names = self._table_data_names(new_xml)
            if names:
                xml = self._remove_table_data_blocks(xml, names)
            try:
                start, end = self._find_xml_patch_target(xml, selector)
                target_missing_table_data_map = False
            except ValueError:
                start = end = -1
                target_missing_table_data_map = True
        if target_missing_table_data_map:
            return self._insert_missing_table_data_map(xml, new_xml)
        if (
            action in {"insert_before", "insert_after"}
            and self._selector_targets_table_data_map(selector)
            and self._is_self_closing_tag(xml[start:end], "TableDataMap")
        ):
            return xml[:start] + self._expand_self_closing_tag(xml[start:end], "TableDataMap", new_xml) + xml[end:]
        if (
            action in {"insert_before", "insert_after"}
            and self._selector_targets_table_data_map(selector)
            and re.match(r"\s*<TableDataMap\b", xml[start:end], flags=re.I)
        ):
            return xml[:start] + self._merge_table_data_map_children(xml[start:end], new_xml) + xml[end:]
        if action == "replace":
            return xml[:start] + new_xml + xml[end:]
        if action == "insert_before":
            return xml[:start] + new_xml + xml[start:]
        if action == "insert_after":
            return xml[:end] + new_xml + xml[end:]
        return xml[:start] + xml[end:]

    def _find_xml_patch_target(self, xml: str, selector: str) -> tuple[int, int]:
        text = self._normalize_xml_patch_selector(selector)
        if len(text) > 500:
            raise ValueError("XML patch selector 过长")
        if ">" in text:
            return self._find_xml_patch_path_target(xml, text)
        cell_match = re.fullmatch(r"cell:?\s*([A-Za-z]{1,3}[0-9]{1,7})", text, flags=re.I)
        if cell_match:
            row, column = self._parse_cell_address(cell_match.group(1)) or (0, 0)
            pattern = re.compile(rf"<C\b(?=[^>]*\bc=\"{column - 1}\")(?=[^>]*\br=\"{row - 1}\")[^>]*>.*?</C>", flags=re.S | re.I)
            match = pattern.search(xml)
            if match:
                return match.start(), match.end()
            raise ValueError(f"没有找到目标单元格 XML：{cell_match.group(1)}")
        c_match = re.fullmatch(r"C\[\s*c\s*=\s*['\"]?(\d+)['\"]?\s*,\s*r\s*=\s*['\"]?(\d+)['\"]?\s*\]", text, flags=re.I)
        if c_match:
            column = int(c_match.group(1))
            row = int(c_match.group(2))
            pattern = re.compile(rf"<C\b(?=[^>]*\bc=\"{column}\")(?=[^>]*\br=\"{row}\")[^>]*>.*?</C>", flags=re.S | re.I)
            match = pattern.search(xml)
            if match:
                return match.start(), match.end()
            raise ValueError(f"没有找到目标单元格 XML：c={column}, r={row}")
        table_data_match = re.fullmatch(r"TableData\[\s*name\s*=\s*['\"]([^'\"]+)['\"]\s*\](?:/Query)?", text, flags=re.I)
        if table_data_match:
            if text.lower().endswith("/query"):
                return self._find_table_data_query_target(xml, table_data_match.group(1))
            match = self._find_table_data_block(xml, table_data_match.group(1))
            if match:
                return match.start(), match.end()
            raise ValueError(f"没有找到目标数据集 XML：{table_data_match.group(1)}")
        attr_match = re.fullmatch(r"([A-Za-z][A-Za-z0-9_$]*)\[\s*([A-Za-z_:][A-Za-z0-9_:.-]*)\s*=\s*['\"]([^'\"]+)['\"]\s*\]", text)
        if attr_match:
            tag, attr, value = attr_match.groups()
            return self._find_tag_block_by_attr(xml, tag, attr, value)
        indexed_match = re.fullmatch(r"([A-Za-z][A-Za-z0-9_$]*)\[\s*(\d+)\s*\]", text)
        if indexed_match:
            tag, index_text = indexed_match.groups()
            return self._find_tag_block_by_index(xml, tag, max(0, int(index_text) - 1))
        tag_match = re.fullmatch(r"<?\s*([A-Za-z][A-Za-z0-9_$]*)\s*>?", text)
        if tag_match:
            return self._find_tag_block_by_index(xml, tag_match.group(1), 0)
        raise ValueError(f"不支持的 XML patch selector：{selector}")

    def _normalize_xml_patch_selector(self, selector: str) -> str:
        text = str(selector or "").strip()
        if not text:
            return ""
        text = text.replace("\\", "/")
        text = re.sub(r"^\./", "", text)
        text = re.sub(r"^/+", "", text)
        text = re.sub(r"\[(\d+)\]", lambda match: f"[{max(1, int(match.group(1)))}]", text)
        text = re.sub(r"\bTableDataList\b", "TableDataMap", text, flags=re.I)
        text = re.sub(r"\bDataSetList\b", "TableDataMap", text, flags=re.I)
        text = re.sub(r"\bDatasetList\b", "TableDataMap", text, flags=re.I)
        text = re.sub(r"\bDataSetMap\b", "TableDataMap", text, flags=re.I)
        text = re.sub(r"\bDatasetMap\b", "TableDataMap", text, flags=re.I)
        text = re.sub(r"\bWorkBook\b\s*/\s*", "", text, count=1, flags=re.I)
        text = re.sub(r"\bReport\[\s*1\s*\]\s*/\s*", "", text, count=1, flags=re.I)
        if "/" in text and ">" not in text:
            text = " > ".join(part for part in (part.strip() for part in text.split("/")) if part)
        if re.fullmatch(r"TableDataMap\[\s*1\s*\]", text, flags=re.I):
            return "TableDataMap"
        return text

    def _find_xml_patch_path_target(self, xml: str, selector: str) -> tuple[int, int]:
        parts = [part.strip() for part in selector.split(">") if part.strip()]
        if not parts:
            raise ValueError("XML patch selector 路径为空")
        table_data_part = next((part for part in parts if re.fullmatch(r"TableData\[\s*name\s*=\s*['\"][^'\"]+['\"]\s*\]", part, flags=re.I)), None)
        if table_data_part and self._selector_targets_query(parts[-1]):
            name = re.search(r"name\s*=\s*['\"]([^'\"]+)['\"]", table_data_part, flags=re.I)
            if name:
                return self._find_table_data_query_target(xml, name.group(1))

        start = 0
        end = len(xml)
        normalized_parts = [self._normalize_xml_selector_segment(part) for part in parts]
        for index, segment in enumerate(normalized_parts):
            if segment.lower() == "attributes" and self._selector_targets_query(parts[-1]):
                continue
            if self._segment_targets_report(segment) and any(self._segment_targets_table_data_map(item) for item in normalized_parts[index + 1 :]):
                continue
            rel_start, rel_end = self._find_xml_selector_segment(xml[start:end], segment)
            start, end = start + rel_start, start + rel_end
        return start, end

    def _normalize_xml_selector_segment(self, segment: str) -> str:
        text = segment.strip()
        text = re.sub(r"\bTableDataList\b", "TableDataMap", text, flags=re.I)
        text = re.sub(r"\bDataSetList\b", "TableDataMap", text, flags=re.I)
        text = re.sub(r"\bDatasetList\b", "TableDataMap", text, flags=re.I)
        text = re.sub(r"\bDataSetMap\b", "TableDataMap", text, flags=re.I)
        text = re.sub(r"\bDatasetMap\b", "TableDataMap", text, flags=re.I)
        if re.fullmatch(r"(WorkBook|Report|TableDataMap)\[\s*1\s*\]", text, flags=re.I):
            return text.split("[", 1)[0]
        if text.lower() == "querysql":
            return "Query"
        return text

    def _selector_targets_query(self, selector: str) -> bool:
        return selector.strip().lower() in {"query", "querysql"} or selector.strip().lower().endswith("/query")

    def _selector_targets_table_data_map(self, selector: str) -> bool:
        normalized = self._normalize_xml_patch_selector(selector)
        parts = [part.strip() for part in re.split(r">|/", normalized) if part.strip()]
        return any(self._segment_targets_table_data_map(part) for part in parts)

    def _segment_targets_table_data_map(self, segment: str) -> bool:
        return re.fullmatch(r"TableDataMap(?:\[\s*1\s*\])?", segment.strip(), flags=re.I) is not None

    def _segment_targets_report(self, segment: str) -> bool:
        return re.fullmatch(r"Report(?:\[\s*\d+\s*\])?", segment.strip(), flags=re.I) is not None

    def _is_self_closing_tag(self, xml: str, tag: str) -> bool:
        return re.fullmatch(rf"\s*<{re.escape(tag)}\b[^>]*/>\s*", xml, flags=re.S | re.I) is not None

    def _expand_self_closing_tag(self, xml: str, tag: str, child_xml: str) -> str:
        stripped = xml.strip()
        open_tag = re.sub(r"/>\s*$", ">", stripped, flags=re.S)
        return f"{open_tag}\n{child_xml}\n</{tag}>"

    def _merge_table_data_map_children(self, table_data_map_xml: str, child_xml: str) -> str:
        normalized_child = self._normalize_table_data_fragment(child_xml)
        names = self._table_data_names(normalized_child)
        merged = self._remove_table_data_blocks(table_data_map_xml, names) if names else table_data_map_xml
        close_match = re.search(r"</TableDataMap\s*>", merged, flags=re.I)
        if not close_match:
            return self._expand_self_closing_tag(merged, "TableDataMap", normalized_child)
        insert_at = close_match.start()
        return f"{merged[:insert_at].rstrip()}\n{normalized_child}\n{merged[insert_at:]}"

    def _table_data_names(self, xml: str) -> set[str]:
        return {
            match.group(1)
            for match in re.finditer(r"<TableData\b(?=[^>]*\bname=\"([^\"]+)\")", xml, flags=re.I)
            if match.group(1)
        }

    def _remove_table_data_blocks(self, xml: str, names: set[str]) -> str:
        result = xml
        for name in names:
            pattern = re.compile(
                rf"\s*<TableData\b(?=[^>]*\bname=\"{re.escape(name)}\")[^>]*(?:/>|>.*?</TableData>)",
                flags=re.S | re.I,
            )
            result = pattern.sub("", result)
        return result

    def _dedupe_table_data_blocks(self, xml: str) -> str:
        table_data_matches = list(re.finditer(r"<TableData\b(?=[^>]*\bname=\"([^\"]+)\")[^>]*(?:/>|>.*?</TableData>)", xml, flags=re.S | re.I))
        if not table_data_matches:
            return xml
        by_name: dict[str, str] = {}
        for match in table_data_matches:
            by_name[match.group(1)] = self._normalize_table_data_fragment(match.group(0))
        table_data_map_match = re.search(r"<TableDataMap\b[^>]*(?:/>|>.*?</TableDataMap>)", xml, flags=re.S | re.I)
        if not table_data_map_match:
            cleaned = self._remove_table_data_blocks(xml, set(by_name))
            return self._insert_missing_table_data_map(cleaned, "\n".join(by_name.values()))
        cleaned = self._remove_table_data_blocks(xml, set(by_name))
        start, end = self._find_tag_block_by_index(cleaned, "TableDataMap", 0)
        merged = self._merge_table_data_map_children(cleaned[start:end], "\n".join(by_name.values()))
        return cleaned[:start] + merged + cleaned[end:]

    def _insert_missing_table_data_map(self, xml: str, child_xml: str) -> str:
        table_data_map_xml = child_xml.strip()
        if not re.match(r"<TableDataMap\b", table_data_map_xml, flags=re.I):
            table_data_map_xml = f"<TableDataMap>\n{child_xml}\n</TableDataMap>"
        insert_at = self._table_data_map_insert_position(xml)
        return f"{xml[:insert_at]}\n{table_data_map_xml}\n{xml[insert_at:]}"

    def _table_data_map_insert_position(self, xml: str) -> int:
        workbook_match = re.search(r"<WorkBook\b[^>]*>", xml, flags=re.I)
        if workbook_match:
            return workbook_match.end()
        for tag in ("ReportParameterAttr", "Report"):
            match = re.search(rf"<{tag}\b", xml, flags=re.I)
            if match:
                return match.start()
        close_match = re.search(r"</WorkBook>", xml, flags=re.I)
        if close_match:
            return close_match.start()
        raise ValueError("当前 CPT 缺少 WorkBook 根节点，无法新增数据集容器")

    def _find_xml_selector_segment(self, xml: str, segment: str) -> tuple[int, int]:
        table_data_match = re.fullmatch(r"TableData\[\s*name\s*=\s*['\"]([^'\"]+)['\"]\s*\]", segment, flags=re.I)
        if table_data_match:
            match = self._find_table_data_block(xml, table_data_match.group(1))
            if match:
                return match.start(), match.end()
            raise ValueError(f"没有找到目标数据集 XML：{table_data_match.group(1)}")
        attr_match = re.fullmatch(r"([A-Za-z][A-Za-z0-9_$]*)\[\s*([A-Za-z_:][A-Za-z0-9_:.-]*)\s*=\s*['\"]([^'\"]+)['\"]\s*\]", segment)
        if attr_match:
            tag, attr, value = attr_match.groups()
            return self._find_tag_block_by_attr(xml, tag, attr, value)
        indexed_match = re.fullmatch(r"([A-Za-z][A-Za-z0-9_$]*)\[\s*(\d+)\s*\]", segment)
        if indexed_match:
            tag, index_text = indexed_match.groups()
            return self._find_tag_block_by_index(xml, tag, max(0, int(index_text) - 1))
        tag_match = re.fullmatch(r"<?\s*([A-Za-z][A-Za-z0-9_$]*)\s*>?", segment)
        if tag_match:
            return self._find_tag_block_by_index(xml, tag_match.group(1), 0)
        raise ValueError(f"不支持的 XML patch selector 片段：{segment}")

    def _find_table_data_block(self, xml: str, name: str) -> re.Match[str] | None:
        pattern = re.compile(rf"<TableData\b(?=[^>]*\bname=\"{re.escape(name)}\")[^>]*>.*?</TableData>", flags=re.S | re.I)
        return pattern.search(xml)

    def _find_table_data_query_target(self, xml: str, name: str) -> tuple[int, int]:
        match = self._find_table_data_block(xml, name)
        if not match:
            raise ValueError(f"没有找到目标数据集 XML：{name}")
        query_match = re.search(r"<Query\b[^>]*>.*?</Query>", match.group(0), flags=re.S | re.I)
        if not query_match:
            raise ValueError(f"数据集 {name} 没有找到 Query 节点")
        return match.start() + query_match.start(), match.start() + query_match.end()

    def _normalize_xml_patch_fragment(self, selector: str, fragment: str) -> str:
        if not self._selector_targets_query(selector.split(">")[-1] if ">" in selector else selector):
            if re.search(r"<TableData\b", fragment, flags=re.I):
                return self._normalize_table_data_fragment(fragment)
            return self._normalize_widget_fragment(fragment)
        stripped = fragment.strip()
        query_match = re.fullmatch(r"<querySql\b([^>]*)>(.*)</querySql>", stripped, flags=re.S | re.I)
        if query_match:
            return f"<Query{query_match.group(1)}>{self._normalize_query_fragment_body(query_match.group(2))}</Query>"
        query_match = re.fullmatch(r"<Query\b([^>]*)>(.*)</Query>", stripped, flags=re.S | re.I)
        if query_match:
            return f"<Query{query_match.group(1)}>{self._normalize_query_fragment_body(query_match.group(2))}</Query>"
        if not re.match(r"<Query\b", stripped, flags=re.I):
            return f"<Query><![CDATA[{self._normalize_query_sql(stripped)}]]></Query>"
        return fragment

    def _normalize_table_data_fragment(self, fragment: str) -> str:
        def normalize_block(match: re.Match[str]) -> str:
            block = match.group(0)
            block = re.sub(r"<SQL\b([^>]*)>(.*?)</SQL>", r"<Query\1>\2</Query>", block, flags=re.S | re.I)
            open_match = re.match(r"<TableData\b[^>]*>", block, flags=re.I)
            if not open_match:
                return block
            open_tag = open_match.group(0)
            if "class=" not in open_tag:
                open_tag = open_tag[:-1] + ' class="com.fr.data.impl.DBTableData">'
                block = open_tag + block[open_match.end() :]
            additions: list[str] = []
            if not re.search(r"<Desensitizations\b", block, flags=re.I):
                additions.append('<Desensitizations desensitizeOpen="false"/>')
            if not re.search(r"<Parameters\b", block, flags=re.I):
                additions.append("<Parameters/>")
            if not re.search(r"<Attributes\b", block, flags=re.I):
                additions.append('<Attributes maxMemRowCount="-1"/>')
            if not re.search(r"<Connection\b", block, flags=re.I):
                additions.append(
                    '<Connection class="com.fr.data.impl.NameDatabaseConnection">\n'
                    f"<DatabaseName><![CDATA[{self._safe_cdata(settings.FR_AI_FINEREPORT_DB_NAME)}]]></DatabaseName>\n"
                    "</Connection>"
                )
            if additions:
                block = block[: len(open_tag)] + "\n" + "\n".join(additions) + block[len(open_tag) :]
            if not re.search(r"<PageQuery\b", block, flags=re.I):
                block = re.sub(r"</TableData>\s*$", "<PageQuery><![CDATA[]]></PageQuery>\n</TableData>", block, flags=re.S | re.I)
            return block

        return re.sub(
            r"<TableData\b[^>]*(?:/>|>.*?</TableData>)",
            normalize_block,
            fragment.strip(),
            flags=re.S | re.I,
        )

    def _normalize_widget_fragment(self, fragment: str) -> str:
        if "<Widget " in fragment:
            return re.sub(
                r"<Widget\b[^>]*>.*?</Widget>",
                lambda match: self._normalize_single_widget_fragment(match.group(0)),
                fragment,
                flags=re.S | re.I,
            )
        return self._normalize_single_widget_fragment(fragment)

    def _normalize_single_widget_fragment(self, fragment: str) -> str:
        widget_name_match = re.search(r"<WidgetName\s+name=\"([A-Za-z_][A-Za-z0-9_]*)\"\s*/>", fragment)
        if not widget_name_match:
            return fragment
        widget_name = widget_name_match.group(1)
        fragment = self._normalize_table_data_dictionary_fragment(fragment, widget_name)
        widget_value_pattern = re.compile(r"<widgetValue>.*?</widgetValue>", flags=re.S | re.I)
        widget_value_match = widget_value_pattern.search(fragment)
        if not widget_value_match or f"${widget_name}" not in widget_value_match.group(0):
            return fragment
        return widget_value_pattern.sub("<widgetValue><O><![CDATA[]]></O></widgetValue>", fragment, count=1)

    def _normalize_table_data_dictionary_fragment(self, fragment: str, widget_name: str) -> str:
        dictionary_pattern = re.compile(
            r"<Dictionary\s+class=\"com\.fr\.data\.impl\.TableDataDictionary\">(?P<body>.*?)</Dictionary>",
            flags=re.S | re.I,
        )

        def repl(match: re.Match[str]) -> str:
            body = match.group("body")
            if "com.fr.data.impl.NameTableData" in body and "FormulaDictAttr" in body:
                return match.group(0)
            dataset_match = re.search(r"<TableDataName>\s*<!\[CDATA\[(?P<name>.*?)]]>\s*</TableDataName>", body, flags=re.S | re.I)
            column_match = re.search(r"<ColumnName>\s*<!\[CDATA\[(?P<name>.*?)]]>\s*</ColumnName>", body, flags=re.S | re.I)
            dataset_name = dataset_match.group("name").strip() if dataset_match else "ds1"
            column_name = column_match.group("name").strip() if column_match else widget_name
            if not column_name:
                column_name = widget_name
            if not dataset_name:
                dataset_name = "ds1"
            return (
                '<Dictionary class="com.fr.data.impl.TableDataDictionary">\n'
                f'<FormulaDictAttr kiName="{escape(column_name)}" viName="{escape(column_name)}"/>\n'
                "<TableDataDictAttr>\n"
                f'<TableData class="com.fr.data.impl.NameTableData"><Name><![CDATA[{self._safe_cdata(dataset_name)}]]></Name></TableData>\n'
                "</TableDataDictAttr>\n"
                "</Dictionary>"
            )

        return dictionary_pattern.sub(repl, fragment, count=1)

    def _normalize_query_fragment_body(self, body: str) -> str:
        cdata_match = re.fullmatch(r"\s*<!\[CDATA\[(.*)]]>\s*", body, flags=re.S)
        if cdata_match:
            return f"<![CDATA[{self._normalize_query_sql(cdata_match.group(1))}]]>"
        return body

    def _normalize_query_sql(self, sql: str) -> str:
        pattern = re.compile(
            r"""\$\{if\(\s*len\(\$?(?P<param>[A-Za-z_][A-Za-z0-9_]*)\)\s*==\s*0\s*\|\|\s*\$?(?P=param)\s*==\s*"全部"\s*,\s*""\s*,\s*"(?P<prefix>\s+and\s+(?P<column>[A-Za-z_][A-Za-z0-9_.]*)\s*=\s*')"\s*\+\s*\$?(?P=param)\s*\+\s*"'\s*"\s*\)}""",
            flags=re.I,
        )

        def repl(match: re.Match[str]) -> str:
            param = match.group("param")
            column = match.group("column")
            return f" and ('${{{param}}}' = '' or '${{{param}}}' = '全部' or {column} = '${{{param}}}')"

        return pattern.sub(repl, sql)

    def _ensure_table_data_parameters(self, xml: str) -> str:
        def repl(match: re.Match[str]) -> str:
            block = match.group(0)
            query_match = re.search(r"<Query\b[^>]*>\s*<!\[CDATA\[(.*?)]]>\s*</Query>", block, flags=re.S | re.I)
            if not query_match:
                return block
            query_sql = query_match.group(1)
            query_params = {
                item
                for item in re.findall(r"\$\{([A-Za-z_][A-Za-z0-9_]*)}", query_sql)
                if item.lower() not in {"if"}
            }
            if not query_params:
                return block
            existing_params = set(re.findall(r"<Parameter>\s*<Attributes\s+name=\"([^\"]+)\"", block, flags=re.S | re.I))
            missing = sorted(query_params - existing_params)
            if not missing:
                return block
            additions = "".join(
                f"<Parameter>\n<Attributes name=\"{name}\"/>\n<O>\n<![CDATA[]]></O>\n</Parameter>\n"
                for name in missing
            )
            if re.search(r"<Parameters>\s*</Parameters>", block, flags=re.S | re.I):
                return re.sub(r"<Parameters>\s*</Parameters>", f"<Parameters>\n{additions}</Parameters>", block, count=1, flags=re.S | re.I)
            if "</Parameters>" in block:
                return block.replace("</Parameters>", f"{additions}</Parameters>", 1)
            insert_at = block.find("<Attributes")
            if insert_at >= 0:
                return f"{block[:insert_at]}<Parameters>\n{additions}</Parameters>\n{block[insert_at:]}"
            return block

        return re.sub(r"<TableData\b[^>]*>.*?</TableData>", repl, xml, flags=re.S | re.I)

    def _find_tag_block_by_attr(self, xml: str, tag: str, attr: str, value: str) -> tuple[int, int]:
        pattern = re.compile(
            rf"<{re.escape(tag)}\b(?=[^>]*\b{re.escape(attr)}=\"{re.escape(value)}\")[^>]*(?:/>|>.*?</{re.escape(tag)}>)",
            flags=re.S | re.I,
        )
        match = pattern.search(xml)
        if not match:
            raise ValueError(f"没有找到目标 XML 节点：{tag}[{attr}={value}]")
        return match.start(), match.end()

    def _find_tag_block_by_index(self, xml: str, tag: str, index: int) -> tuple[int, int]:
        pattern = re.compile(
            rf"<{re.escape(tag)}\b[^>]*(?:/>|>.*?</{re.escape(tag)}>)",
            flags=re.S | re.I,
        )
        matches = list(pattern.finditer(xml))
        if index >= len(matches):
            raise ValueError(f"没有找到目标 XML 节点：{tag}[{index + 1}]")
        match = matches[index]
        return match.start(), match.end()

    def _validate_xml_patch_fragment(self, fragment: str) -> None:
        if not fragment.strip():
            raise ValueError("XML patch 片段不能为空")
        lowered = fragment.lower()
        forbidden_tags = ("<!entity", "<!doctype")
        if any(tag in lowered for tag in forbidden_tags):
            raise ValueError("XML patch 片段包含禁止修改的高风险节点")
        import xml.etree.ElementTree as ET

        try:
            ET.fromstring(f"<Root>{fragment}</Root>")
        except ET.ParseError as exc:
            raise ValueError(f"XML patch 片段不是合法 XML：{exc}") from exc

    def _validate_full_cpt_xml(self, content: str) -> None:
        if not content.strip():
            raise ValueError("完整 CPT XML 不能为空")
        lowered = content.lower()
        if "<!entity" in lowered or "<!doctype" in lowered:
            raise ValueError("完整 CPT XML 包含禁止的实体或 DTD")
        import xml.etree.ElementTree as ET

        try:
            root = ET.fromstring(content.encode("utf-8"))
        except ET.ParseError as exc:
            raise ValueError(f"完整 CPT XML 不是合法 XML：{exc}") from exc
        if root.tag.rsplit("}", 1)[-1].lower() != "workbook":
            raise ValueError("完整 CPT XML 根节点必须是 WorkBook")

    def _patch_existing_cells(self, xml: str, document: dict[str, Any]) -> str:
        sheet = self._first_sheet(document)
        cells = [
            cell
            for cell in list(sheet.get("cells") or [])
            if isinstance(cell, dict) and cell.get("aiModified")
        ]
        for cell in cells:
            xml = self._patch_existing_cell(xml, cell)
        return xml

    def _patch_existing_cell(self, xml: str, cell: dict[str, Any]) -> str:
        row = self._positive_int(cell.get("row"))
        column = self._positive_int(cell.get("column"))
        if not row or not column:
            return xml
        xml_row = row - 1
        xml_column = column - 1
        pattern = re.compile(
            rf"<C\b(?=[^>]*\bc=\"{xml_column}\")(?=[^>]*\br=\"{xml_row}\")[^>]*>.*?</C>",
            flags=re.S | re.I,
        )
        match = pattern.search(xml)
        existing_style = None
        if match:
            style_match = re.search(r'\bs="(\d+)"', match.group(0))
            if style_match:
                existing_style = int(style_match.group(1))
        cell_xml = self._snapshot_cell_c_xml(cell, existing_style_index=existing_style)
        if match:
            return xml[: match.start()] + cell_xml + xml[match.end() :]
        list_match = re.search(r"</CellElementList>", xml, flags=re.I)
        if list_match:
            return xml[: list_match.start()] + f"{cell_xml}\n" + xml[list_match.start() :]
        table_match = re.search(r"(<Table\b[^>]*>)", xml, flags=re.S | re.I)
        if not table_match:
            return xml
        cell_list = f"\n<CellElementList>\n{cell_xml}\n</CellElementList>"
        return xml[: table_match.end()] + cell_list + xml[table_match.end() :]

    def _patch_existing_dimensions(self, xml: str, document: dict[str, Any]) -> str:
        sheet = self._first_sheet(document)
        xml = self._patch_existing_dimension_list(xml, "ColumnWidth", sheet.get("columns") or [], 88)
        xml = self._patch_existing_dimension_list(xml, "RowHeight", sheet.get("rows") or [], 36)
        return xml

    def _patch_existing_dimension_list(
        self,
        xml: str,
        tag_name: str,
        dimensions: list[Any],
        default_px: int,
    ) -> str:
        dimension_map = {
            int(item.get("index")): self._positive_int(item.get("size"))
            for item in dimensions
            if isinstance(item, dict) and self._positive_int(item.get("index")) and self._positive_int(item.get("size"))
        }
        if not dimension_map:
            return xml

        tag_pattern = re.compile(rf"<{tag_name}\b([^>]*)>(.*?)</{tag_name}>", flags=re.S | re.I)
        tag_match = tag_pattern.search(xml)
        if tag_match:
            attrs = tag_match.group(1)
            existing_values = self._dimension_raw_values(tag_match.group(2))
            default_raw = self._dimension_default_raw(attrs, default_px)
            use_large_unit = default_raw > 10000 or any(abs(value) > 10000 for value in existing_values)
            max_index = max(max(dimension_map), len(existing_values), 1)
            raw_values = list(existing_values) + [default_raw] * (max_index - len(existing_values))
            for index, size in dimension_map.items():
                raw_values[index - 1] = self._px_to_dimension_raw(size or default_px, use_large_unit)
            replacement = f"<{tag_name}{attrs}><![CDATA[{','.join(str(value) for value in raw_values)}]]></{tag_name}>"
            return xml[: tag_match.start()] + replacement + xml[tag_match.end() :]

        table_match = re.search(r"<Table\b(?=[^>]*(?:rows|columns)=)[^>]*>", xml, flags=re.S | re.I)
        if not table_match:
            return xml
        max_index = max(max(dimension_map), 1)
        default_raw = self._px_to_dimension_raw(default_px, True)
        raw_values = [default_raw] * max_index
        for index, size in dimension_map.items():
            raw_values[index - 1] = self._px_to_dimension_raw(size or default_px, True)
        dimension_xml = f"\n<{tag_name} defaultValue=\"{default_raw}\"><![CDATA[{','.join(str(value) for value in raw_values)}]]></{tag_name}>"
        return xml[: table_match.end()] + dimension_xml + xml[table_match.end() :]

    def _dimension_raw_values(self, raw_text: str) -> list[int]:
        values: list[int] = []
        for value in re.findall(r"-?\d+", raw_text or ""):
            try:
                values.append(int(value))
            except ValueError:
                continue
        return values

    def _dimension_default_raw(self, attrs: str, default_px: int) -> int:
        match = re.search(r'defaultValue="(-?\d+)"', attrs or "", flags=re.I)
        if match:
            return int(match.group(1))
        return self._px_to_dimension_raw(default_px, True)

    def _px_to_dimension_raw(self, size_px: int, use_large_unit: bool) -> int:
        size = max(1, int(round(size_px)))
        return size * 30480 if use_large_unit else size

    def _patch_existing_table_data_parameters(
        self,
        xml: str,
        parameters: list[dict[str, Any]],
        removed_parameters: set[str] | None = None,
    ) -> str:
        params_xml = self._parameters_xml_for_existing_cpt(parameters)
        table_match = re.search(r"(<TableData\b[^>]*>)(.*?)(</TableData>)", xml, flags=re.S)
        if not table_match:
            return xml
        table_body = table_match.group(2)
        removed = removed_parameters or set()
        if not params_xml and not removed:
            return xml
        params_match = re.search(r"<Parameters>(.*?)</Parameters>", table_body, flags=re.S)
        if params_match:
            if params_xml:
                merged_block = f"\n{params_xml}\n"
            else:
                merged_block = self._remove_parameter_xml_by_name(params_match.group(1), removed)
            table_body = table_body[: params_match.start(1)] + merged_block + table_body[params_match.end(1) :]
        else:
            table_body = f"\n<Parameters>\n{params_xml}\n</Parameters>{table_body}"
        return xml[: table_match.start(2)] + table_body + xml[table_match.end(2) :]

    def _remove_parameter_xml_by_name(self, parameters_xml: str, removed_names: set[str]) -> str:
        if not removed_names:
            return parameters_xml

        def keep_or_remove(match: re.Match[str]) -> str:
            block = match.group(0)
            name_match = re.search(r'<Attributes\b[^>]*\bname="([^"]+)"', block)
            if not name_match:
                return block
            name = self._normalize_parameter_name(name_match.group(1))
            return "" if name in removed_names else block

        return re.sub(r"<Parameter\b.*?</Parameter>", keep_or_remove, parameters_xml, flags=re.S)

    def _patch_existing_report_parameter_attr(self, xml: str, document: dict[str, Any]) -> str:
        parameter_ui_xml = self._snapshot_parameter_ui_xml(self._snapshot_parameters(document))
        if "<ReportParameterAttr>" in xml and "</ReportParameterAttr>" in xml:
            attr_match = re.search(r"<ReportParameterAttr>(.*?)</ReportParameterAttr>", xml, flags=re.S)
            if not attr_match:
                return xml
            body = attr_match.group(1)
            body = self._ensure_delay_playing_not_defaulted(body)
            if re.search(r"<ParameterUI\b.*?</ParameterUI>", body, flags=re.S):
                body = re.sub(r"<ParameterUI\b.*?</ParameterUI>", parameter_ui_xml, body, count=1, flags=re.S)
            else:
                body = f"{body.rstrip()}\n{parameter_ui_xml}\n"
            return xml[: attr_match.start(1)] + body + xml[attr_match.end(1) :]
        report_index = xml.find("<Report ")
        if report_index < 0:
            return xml
        return f"{xml[:report_index]}{self._snapshot_report_parameter_attr_xml(document)}\n{xml[report_index:]}"

    def _ensure_delay_playing_not_defaulted(self, report_parameter_attr_body: str) -> str:
        attributes_match = re.search(r"<Attributes\b([^>]*)/>", report_parameter_attr_body, flags=re.S)
        if not attributes_match:
            return f'\n<Attributes delayPlaying="false"/>{report_parameter_attr_body}'
        attrs = attributes_match.group(1)
        if "delayPlaying=" in attrs:
            return report_parameter_attr_body
        replacement = f"<Attributes{attrs} delayPlaying=\"false\"/>"
        return report_parameter_attr_body[: attributes_match.start()] + replacement + report_parameter_attr_body[attributes_match.end() :]

    def _removed_parameter_names_from_payload(self, payload: dict[str, Any], summary: str | None = None) -> set[str]:
        removed: set[str] = set()
        for key in ("removeParameter", "removeWidget", "deletedParameter", "deletedWidget"):
            name = self._normalize_parameter_name(payload.get(key))
            if name:
                removed.add(name)
        for key in ("removeParameters", "removeWidgets", "deletedParameters", "deletedWidgets"):
            values = payload.get(key)
            if not isinstance(values, list):
                continue
            for item in values:
                name = self._normalize_parameter_name(item)
                if name:
                    removed.add(name)

        labels = payload.get("removeLabels")
        if isinstance(labels, list):
            label_to_name = {
                "结算日期": "settlement_date",
                "操作平台": "operate_platform",
                "交易确认书编号": "trade_confirm_no",
                "标的合约": "futures_contract",
                "期权类型": "option_type",
                "交易方向": "trade_direction",
            }
            for label in labels:
                mapped = label_to_name.get(str(label or "").strip())
                if mapped:
                    removed.add(mapped)

        text = f"{summary or ''} {payload.get('action') or ''}"
        if re.search(r"去掉|删除|移除|取消|不再|remove|delete|disable", text, flags=re.IGNORECASE):
            for label, name in {
                "结算日期": "settlement_date",
                "settlement_date": "settlement_date",
            }.items():
                if label in text:
                    removed.add(name)
        return removed

    def _strip_removed_parameter_filters(self, sql: str, removed: set[str]) -> str:
        if not removed:
            return sql
        patterns = [
            re.compile(rf"@\s*{re.escape(name)}\b|\$\{{\s*{re.escape(name)}\s*\}}", flags=re.IGNORECASE)
            for name in removed
            if name
        ]
        if not patterns:
            return sql
        lines: list[str] = []
        for line in sql.splitlines():
            stripped = line.lstrip()
            if stripped.upper().startswith(("DECLARE ", "AND ")) and any(pattern.search(line) for pattern in patterns):
                continue
            lines.append(line)
        return "\n".join(lines)

    def _augment_option_ledger_sql(self, sql: str, parameters: list[dict[str, Any]]) -> str:
        wanted = {self._normalize_parameter_name(item.get("name")) for item in parameters if isinstance(item, dict)}
        wanted.discard(None)
        field_map = {
            "settlement_date": ("f.settlement_date", "date"),
            "operate_platform": ("f.operate_platform", "text"),
            "trade_confirm_no": ("f.trade_confirm_no", "text"),
            "futures_contract": ("f.futures_contract", "text"),
            "option_type": ("f.option_type", "text"),
            "trade_direction": ("f.trade_direction", "text"),
        }
        active = [name for name in field_map if name in wanted and f"${{{name}}}" not in sql]
        if not active:
            return sql
        declarations: list[str] = []
        conditions: list[str] = []
        for name in active:
            field, field_type = field_map[name]
            if field_type == "date":
                declarations.append(f"DECLARE @{name} nvarchar(20) = '${{{name}}}';")
                conditions.append(f"      AND (@{name} = N'' OR CONVERT(varchar(10), {field}, 23) = @{name})")
            else:
                declarations.append(f"DECLARE @{name} nvarchar(200) = '${{{name}}}';")
                conditions.append(f"      AND (@{name} = N'' OR {field} = @{name})")
        if declarations and ";WITH base_data AS" in sql:
            sql = sql.replace(";WITH base_data AS", "\n".join(declarations) + "\n\n;WITH base_data AS", 1)
        condition_block = "\n".join(conditions)
        anchor = "WHERE f.settlement_date BETWEEN @start_date AND @end_date"
        if condition_block and anchor in sql:
            sql = sql.replace(anchor, f"{anchor}\n{condition_block}", 1)
        return sql

    def _parameters_xml_for_existing_cpt(self, parameters: list[dict[str, Any]]) -> str:
        parts: list[str] = []
        seen: set[str] = set()
        for parameter in parameters:
            name = self._normalize_parameter_name(parameter.get("name")) if isinstance(parameter, dict) else None
            if not name or name in seen:
                continue
            seen.add(name)
            default = parameter.get("defaultValue") if isinstance(parameter, dict) else None
            if default is None and name == "start_date":
                default = "2026-06-01"
            elif default is None and name == "end_date":
                default = "2026-06-24"
            value = "" if default is None else str(default)
            parts.append(
                f"""<Parameter>
<Attributes name="{escape(name)}"/>
<O>
<![CDATA[{self._safe_cdata(value)}]]></O>
</Parameter>"""
            )
        return "\n".join(parts)

    def _snapshot_to_cpt_bytes(self, snapshot: FrReportSnapshot) -> bytes:
        document = snapshot.document_snapshot or {}
        sheet = self._first_sheet(document)
        title = snapshot.title or snapshot.file_name or "AI生成报表"
        row_count = max(int(sheet.get("rowCount") or 1), 1)
        column_count = max(int(sheet.get("columnCount") or 1), 1)
        column_width_xml = self._snapshot_dimension_xml("ColumnWidth", sheet.get("columns") or [], column_count, 88)
        row_height_xml = self._snapshot_dimension_xml("RowHeight", sheet.get("rows") or [], row_count, 36)
        cells_xml = self._snapshot_cells_xml(sheet.get("cells") or [])
        table_data_map_xml = self._snapshot_table_data_map_xml(document)
        report_parameter_attr_xml = self._snapshot_report_parameter_attr_xml(document)
        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<WorkBook xmlVersion="20211223" releaseVersion="11.5.0">
{table_data_map_xml}
{report_parameter_attr_xml}
<Report class="com.fr.report.worksheet.WorkSheet" name="{escape(title)}">
<ReportPageAttr>
<HR/>
<FR/>
</ReportPageAttr>
<Table rows="{row_count}" columns="{column_count}">
{column_width_xml}
{row_height_xml}
<CellElementList>
{cells_xml}
</CellElementList>
</Table>
</Report>
</WorkBook>
"""
        return xml.encode("utf-8")

    def _snapshot_dimension_xml(
        self,
        tag_name: str,
        dimensions: list[Any],
        count: int,
        default_px: int,
    ) -> str:
        dimension_map = {
            int(item.get("index")): self._positive_int(item.get("size"))
            for item in dimensions
            if isinstance(item, dict) and self._positive_int(item.get("index")) and self._positive_int(item.get("size"))
        }
        if not dimension_map:
            return ""
        max_index = max(max(dimension_map), count, 1)
        default_raw = self._px_to_dimension_raw(default_px, True)
        raw_values = [default_raw] * max_index
        for index, size in dimension_map.items():
            raw_values[index - 1] = self._px_to_dimension_raw(size or default_px, True)
        return f'<{tag_name} defaultValue="{default_raw}"><![CDATA[{",".join(str(value) for value in raw_values)}]]></{tag_name}>'

    def _snapshot_table_data_map_xml(self, snapshot: dict[str, Any]) -> str:
        datasets = [item for item in list(snapshot.get("datasets") or []) if isinstance(item, dict)]
        if not datasets:
            return "<TableDataMap/>"
        parts: list[str] = []
        for dataset in datasets[:20]:
            name = str(dataset.get("name") or "ds1")
            query_sql = str(dataset.get("querySql") or "")
            database_name = str(dataset.get("databaseName") or settings.FR_AI_FINEREPORT_DB_NAME)
            parameters = self._dataset_parameters_for_xml(dataset, query_sql)
            parts.append(
                f"""<TableData name="{escape(name)}" class="com.fr.data.impl.DBTableData">
<Desensitizations desensitizeOpen="false"/>
<Parameters>
{parameters}
</Parameters>
<Attributes maxMemRowCount="-1"/>
<Connection class="com.fr.data.impl.NameDatabaseConnection">
<DatabaseName><![CDATA[{self._safe_cdata(database_name)}]]></DatabaseName>
</Connection>
<Query><![CDATA[{self._safe_cdata(query_sql)}]]></Query>
<PageQuery><![CDATA[]]></PageQuery>
</TableData>"""
            )
        return f"""<TableDataMap>
{''.join(parts)}
</TableDataMap>"""

    def _dataset_parameters_for_xml(self, dataset: dict[str, Any], query_sql: str) -> str:
        current = {
            self._normalize_parameter_name(item.get("name")): item.get("defaultValue")
            for item in list(dataset.get("parameters") or [])
            if isinstance(item, dict) and item.get("name")
        }
        for name in self._extract_sql_parameters(query_sql):
            current.setdefault(name, "")
        parts: list[str] = []
        for name, default_value in current.items():
            if not name:
                continue
            default = "" if default_value is None else str(default_value)
            parts.append(
                f"""<Parameter>
<Attributes name="{escape(name)}"/>
<O><![CDATA[{self._safe_cdata(default)}]]></O>
</Parameter>"""
            )
        return "\n".join(parts)

    def _snapshot_report_parameter_attr_xml(self, snapshot: dict[str, Any]) -> str:
        parameters = self._snapshot_parameters(snapshot)
        parameter_ui_xml = self._snapshot_parameter_ui_xml(parameters)
        return f"""<ReportParameterAttr>
<Attributes showWindow="true"/>
{parameter_ui_xml}
</ReportParameterAttr>"""

    def _snapshot_parameters(self, snapshot: dict[str, Any]) -> list[dict[str, Any]]:
        current: dict[str, dict[str, Any]] = {}
        removed = self._snapshot_removed_parameters(snapshot)
        for dataset in list(snapshot.get("datasets") or []):
            if not isinstance(dataset, dict):
                continue
            for parameter in list(dataset.get("parameters") or []):
                if not isinstance(parameter, dict):
                    continue
                name = self._normalize_parameter_name(parameter.get("name"))
                if not name:
                    continue
                if self._is_cell_address_parameter(name):
                    continue
                if name in removed:
                    continue
                current.setdefault(
                    name,
                    {
                        "name": name,
                        "label": self._humanize_parameter_label(name),
                        "widgetType": self._guess_parameter_widget_type(name),
                        "defaultValue": parameter.get("defaultValue"),
                    },
                )
        for parameter in list(snapshot.get("aiParameters") or []):
            if not isinstance(parameter, dict):
                continue
            name = self._normalize_parameter_name(parameter.get("name"))
            if not name:
                continue
            if self._is_cell_address_parameter(name):
                continue
            if name in removed:
                continue
            current[name] = {
                **current.get(name, {}),
                **{key: value for key, value in parameter.items() if value is not None},
                "name": name,
                "label": str(parameter.get("label") or current.get(name, {}).get("label") or self._humanize_parameter_label(name)),
                "widgetType": self._normalize_widget_type(parameter.get("widgetType") or current.get(name, {}).get("widgetType")),
            }
        priority = {
            "start_date": 0,
            "end_date": 1,
            "settlement_date": 2,
            "operate_platform": 3,
            "trade_confirm_no": 4,
            "futures_contract": 5,
            "option_type": 6,
            "trade_direction": 7,
        }
        return sorted(current.values(), key=lambda item: (priority.get(str(item.get("name") or ""), 100), str(item.get("name") or "")))

    def _snapshot_removed_parameters(self, snapshot: dict[str, Any]) -> set[str]:
        return {
            name
            for item in list(snapshot.get("aiRemovedParameters") or [])
            if (name := self._normalize_parameter_name(item))
        }

    def _snapshot_parameter_ui_xml(self, parameters: list[dict[str, Any]]) -> str:
        if not parameters:
            return ""
        widgets = [self._snapshot_parameter_label_widget(0, "筛选条件", 24, 18, 72)]
        start_x = 110
        x = start_x
        y = 18
        for index, parameter in enumerate(parameters[:10], start=1):
            if index == 5:
                x = start_x
                y = 50
            label = str(parameter.get("label") or parameter.get("name") or "")
            label_width = max(88, min(132, len(label) * 15))
            input_width = 136
            widgets.append(self._snapshot_parameter_label_widget(index, label, x, y, label_width))
            widgets.append(self._snapshot_parameter_input_widget(parameter, x + label_width + 8, y, input_width))
            x += label_width + input_width + 32
        widgets.append(self._snapshot_parameter_submit_widget(x + 8, y))
        width = max(1080, min(1800, x + 110))
        height = 92 if len(parameters) > 5 else 64
        return f"""<ParameterUI class="com.fr.form.main.parameter.FormParameterUI">
<Parameters/>
<Layout class="com.fr.form.ui.container.WParameterLayout">
<WidgetName name="para"/>
<WidgetAttr aspectRatioLocked="false" aspectRatioBackup="-1.0" description="">
<PrivilegeControl/>
</WidgetAttr>
<FollowingTheme borderStyle="false"/>
<Margin top="0" left="0" bottom="0" right="0"/>
<Background name="ColorBackground"><color><FineColor color="-1" hor="-1" ver="-1"/></color></Background>
<LCAttr vgap="0" hgap="0" compInterval="0"/>
{''.join(widgets)}
</Layout>
<DesignAttr width="{width}" height="{height}"/>
</ParameterUI>"""

    def _snapshot_parameter_label_widget(self, index: int, label: str, x: int, y: int, width: int) -> str:
        safe_label = self._safe_cdata(label)
        return f"""<Widget class="com.fr.form.ui.container.WAbsoluteLayout$BoundsWidget">
<InnerWidget class="com.fr.form.ui.Label">
<WidgetName name="label_{index}"/>
<LabelName name="{escape(label)}"/>
<WidgetAttr aspectRatioLocked="false" aspectRatioBackup="-1.0" description=""><PrivilegeControl/></WidgetAttr>
<widgetValue><O><![CDATA[{safe_label}]]></O></widgetValue>
<LabelAttr textalign="0" verticalcenter="true" autoline="false"/>
<FRFont name="SimSun" style="0" size="72"/>
</InnerWidget>
<BoundsAttr x="{x}" y="{y}" width="{width}" height="21"/>
</Widget>"""

    def _snapshot_parameter_input_widget(self, parameter: dict[str, Any], x: int, y: int, width: int) -> str:
        name = self._normalize_parameter_name(parameter.get("name")) or "param"
        widget_type = self._normalize_widget_type(parameter.get("widgetType"))
        default_value = parameter.get("defaultValue")
        if widget_type == "date":
            default = self._date_default_formula_for_name(name) if name in {"start_date", "end_date"} else str(default_value or "")
            is_formula = default.startswith("=")
            widget_value_xml = (
                f"""<widgetValue><O t="XMLable" class="com.fr.base.Formula"><Attributes><![CDATA[{self._safe_cdata(default)}]]></Attributes></O></widgetValue>"""
                if is_formula
                else f"""<widgetValue><O><![CDATA[{self._safe_cdata(default)}]]></O></widgetValue>"""
            )
            return f"""<Widget class="com.fr.form.ui.container.WAbsoluteLayout$BoundsWidget">
<InnerWidget class="com.fr.form.ui.DateEditor">
<WidgetName name="{escape(name)}"/>
<WidgetAttr aspectRatioLocked="false" aspectRatioBackup="-1.0" description=""><PrivilegeControl/></WidgetAttr>
{widget_value_xml}
<DateAttr/>
</InnerWidget>
<BoundsAttr x="{x}" y="{y}" width="{width}" height="21"/>
</Widget>"""
        if widget_type == "combo":
            dictionary = parameter.get("dataDictionary") if isinstance(parameter.get("dataDictionary"), dict) else {}
            dataset_name = str(dictionary.get("dataset") or "ds1")
            column_name = str(dictionary.get("column") or name)
            return f"""<Widget class="com.fr.form.ui.container.WAbsoluteLayout$BoundsWidget">
<InnerWidget class="com.fr.form.ui.ComboBox">
<WidgetName name="{escape(name)}"/>
<WidgetAttr aspectRatioLocked="false" aspectRatioBackup="-1.0" description=""><PrivilegeControl/></WidgetAttr>
<Dictionary class="com.fr.data.impl.TableDataDictionary">
<FormulaDictAttr kiName="{escape(column_name)}" viName="{escape(column_name)}"/>
<TableDataDictAttr>
<TableData class="com.fr.data.impl.NameTableData"><Name><![CDATA[{self._safe_cdata(dataset_name)}]]></Name></TableData>
</TableDataDictAttr>
</Dictionary>
<widgetValue><O><![CDATA[]]></O></widgetValue>
</InnerWidget>
<BoundsAttr x="{x}" y="{y}" width="{width}" height="21"/>
</Widget>"""
        value = "" if default_value is None else str(default_value)
        return f"""<Widget class="com.fr.form.ui.container.WAbsoluteLayout$BoundsWidget">
<InnerWidget class="com.fr.form.ui.TextEditor">
<WidgetName name="{escape(name)}"/>
<WidgetAttr aspectRatioLocked="false" aspectRatioBackup="-1.0" description=""><PrivilegeControl/></WidgetAttr>
<widgetValue><O><![CDATA[{self._safe_cdata(value)}]]></O></widgetValue>
</InnerWidget>
<BoundsAttr x="{x}" y="{y}" width="{width}" height="21"/>
</Widget>"""

    def _snapshot_parameter_submit_widget(self, x: int, y: int) -> str:
        return f"""<Widget class="com.fr.form.ui.container.WAbsoluteLayout$BoundsWidget">
<InnerWidget class="com.fr.form.parameter.FormSubmitButton">
<WidgetName name="Search"/>
<WidgetAttr aspectRatioLocked="false" aspectRatioBackup="-1.0" description=""><PrivilegeControl/></WidgetAttr>
<Text><![CDATA[查询]]></Text>
</InnerWidget>
<BoundsAttr x="{x}" y="{y}" width="72" height="21"/>
</Widget>"""

    def _extract_sql_parameters(self, sql: str | None) -> list[str]:
        if not sql:
            return []
        names: list[str] = []
        for raw in re.findall(r"\$\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}", sql):
            name = self._normalize_parameter_name(raw)
            if name and name not in names:
                names.append(name)
        return names

    def _humanize_parameter_label(self, name: str) -> str:
        mapping = {
            "start_date": "开始日期",
            "end_date": "结束日期",
            "settlement_date": "结算日期",
            "settlement_date_start": "结算日期(起)",
            "settlement_date_end": "结算日期(止)",
            "operate_platform": "操作平台",
            "platform": "操作平台",
            "trade_confirm_no": "交易确认书编号",
            "trade_confirm_id": "交易确认书编号",
            "futures_contract": "标的合约",
            "underlying_contract": "标的合约",
            "option_type": "期权类型",
            "trade_direction": "交易方向",
        }
        return mapping.get(name, name)

    def _guess_parameter_widget_type(self, name: str) -> str:
        return "date" if "date" in name.lower() else "text"

    def _date_default_formula_for_name(self, name: str) -> str:
        lowered = name.lower()
        if lowered.startswith("start") or lowered.endswith("_start"):
            return "=DATEINMONTH(TODAY(),1)"
        return "=TODAY()"

    def _first_sheet(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        document = snapshot.get("document") or {}
        sheets = document.get("sheets") or []
        if sheets and isinstance(sheets[0], dict):
            return sheets[0]
        return {"rowCount": 1, "columnCount": 1, "cells": []}

    def _snapshot_cells_xml(self, cells: list[dict[str, Any]]) -> str:
        parts: list[str] = []
        for cell in cells[:5000]:
            parts.append(self._snapshot_cell_c_xml(cell))
        return "\n".join(parts)

    def _snapshot_cell_c_xml(self, cell: dict[str, Any], existing_style_index: int | None = None) -> str:
        row = max(1, int(cell.get("row") or 1))
        column = max(1, int(cell.get("column") or 1))
        row_span = max(1, int(cell.get("rowSpan") or 1))
        col_span = max(1, int(cell.get("colSpan") or 1))
        style_index = self._cell_style_index(cell, existing_style_index)
        attrs = [f'c="{column - 1}"', f'r="{row - 1}"']
        if col_span > 1:
            attrs.append(f'cs="{col_span}"')
        if row_span > 1:
            attrs.append(f'rs="{row_span}"')
        attrs.append(f's="{style_index}"')
        object_xml = self._cell_object_xml(cell)
        widget_xml = self._cell_widget_xml(cell.get("widget") if isinstance(cell.get("widget"), dict) else None)
        expand_xml = self._cell_expand_xml(str(cell.get("expandDirection") or "down"))
        return f"""<C {' '.join(attrs)}>
{object_xml}
<PrivilegeControl/>
{widget_xml}
{expand_xml}
</C>"""

    def _cell_object_xml(self, cell: dict[str, Any]) -> str:
        data_column = cell.get("dataColumn") if isinstance(cell.get("dataColumn"), dict) else {}
        dataset = data_column.get("dataset")
        field = data_column.get("field")
        if dataset and field:
            return f"""<O t="DSColumn">
<Attributes dsName="{escape(str(dataset))}" columnName="{escape(str(field))}"/>
<Complex/>
<RG class="com.fr.report.cell.cellattr.core.group.FunctionGrouper"/>
<Parameters/>
</O>"""
        formula = cell.get("formula")
        if formula not in (None, ""):
            return f"""<O t="XMLable" class="com.fr.base.Formula">
<Attributes><![CDATA[{self._safe_cdata(str(formula))}]]></Attributes>
</O>"""
        value = self._cell_display_value(cell)
        return f"""<O>
<![CDATA[{self._safe_cdata(value)}]]></O>"""

    def _cell_widget_xml(self, widget: dict[str, Any] | None) -> str:
        if not widget:
            return ""
        widget_type = self._normalize_widget_type(widget.get("widgetType") or widget.get("widgetClass"))
        widget_name = escape(str(widget.get("widgetName") or widget.get("name") or "cell_widget"))
        if widget_type == "number":
            return """<Widget class="com.fr.form.ui.NumberEditor">
<WidgetAttr description=""><PrivilegeControl/></WidgetAttr>
<NumberAttr><widgetValue/></NumberAttr>
</Widget>"""
        if widget_type == "date":
            return """<Widget class="com.fr.form.ui.DateEditor">
<WidgetAttr description=""><PrivilegeControl/></WidgetAttr>
<DateAttr/>
<widgetValue/>
</Widget>"""
        if widget_type == "combo":
            dictionary = widget.get("dataDictionary") if isinstance(widget.get("dataDictionary"), dict) else {}
            dataset = escape(str(dictionary.get("dataset") or "ds1"))
            key_field = escape(str(dictionary.get("valueField") or dictionary.get("column") or widget_name))
            value_field = escape(str(dictionary.get("textField") or dictionary.get("column") or key_field))
            return f"""<Widget class="com.fr.form.ui.ComboBox">
<WidgetName name="{widget_name}"/>
<WidgetAttr description=""><PrivilegeControl/></WidgetAttr>
<Dictionary class="com.fr.data.impl.TableDataDictionary">
<FormulaDictAttr kiName="{key_field}" viName="{value_field}"/>
<TableDataDictAttr>
<TableData class="com.fr.data.impl.NameTableData"><Name><![CDATA[{self._safe_cdata(dataset)}]]></Name></TableData>
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
</Widget>"""

    def _cell_expand_xml(self, expand_direction: str) -> str:
        normalized = self._normalize_expand_direction(expand_direction)
        if normalized == "none":
            return "<Expand/>"
        return f'<Expand dir="{"1" if normalized == "right" else "0"}"/>'

    def _cell_style_index(self, cell: dict[str, Any], existing_style_index: int | None = None) -> int:
        style = cell.get("style") if isinstance(cell.get("style"), dict) else {}
        if style and cell.get("aiModified"):
            if style.get("bold") or style.get("backgroundColor") or style.get("fillColor"):
                return 1
            if style.get("align") == "right" or style.get("horizontalAlignment") == "right":
                return 3
        if existing_style_index is not None:
            return existing_style_index
        return self._positive_int(style.get("styleIndex") or style.get("s")) or 2

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
