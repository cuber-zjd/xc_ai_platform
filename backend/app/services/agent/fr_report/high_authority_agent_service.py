import base64
import json
import re
import zipfile
import asyncio
from datetime import datetime
from html import unescape as html_unescape
from io import BytesIO
from typing import Any, AsyncIterator
from uuid import uuid4
from xml.sax.saxutils import escape

from fastapi import UploadFile
from langchain_core.messages import HumanMessage, SystemMessage
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.llm_factory import LLMFactory
from app.core.langfuse_observability import langfuse_observability
from app.core.logger import logger
from app.models.agent.fr_report import FrReportDatabaseConnection, FrReportSnapshot
from app.schemas.agent.fr_report.ai_report import PreviewValidationResult
from app.services.agent.fr_report.ai_operation_service import fr_report_ai_operation_service
from app.services.agent.fr_report.excel_analyzer import excel_analyzer
from app.services.agent.fr_report.fr_minio_service import fr_minio_service
from app.services.agent.fr_report.fr_setting_knowledge_service import fr_setting_knowledge_service
from app.services.agent.fr_report.preview_validator import preview_validator
from app.services.agent.fr_report.report_case_service import fr_report_case_service
from app.services.agent.fr_report.report_file_service import fr_report_file_service
from app.services.agent.fr_report.sqlserver_query_service import sqlserver_query_service
from app.services.agent.fr_report.version_control_service import fr_report_version_control_service


class CandidatePreparationError(Exception):
    """候选 CPT 生成和自动修复都未通过校验。"""

    def __init__(self, message: str, warnings: list[str] | None = None) -> None:
        super().__init__(message)
        self.warnings = warnings or []


class FrReportHighAuthorityAgentService:
    """FineReport 专用高权限 Agent。

    这里的边界是版本系统和 reportlets 白名单，不再用“写入器类型”限制模型。
    """

    CHAIN_VERSION = "direct_file_edit_v2"
    DIRECT_FILE_EDIT_TIMEOUT_SECONDS = 90
    REACT_MODEL_STEP_TIMEOUT_SECONDS = 75
    REACT_FINALIZER_TIMEOUT_SECONDS = 90
    REACT_REPAIR_TIMEOUT_SECONDS = 90

    async def run_stream(
        self,
        *,
        db: AsyncSession,
        user_id: int,
        object_path: str,
        message: str,
        selected_cell: str | None = None,
        selected_dataset: str | None = None,
        context: dict[str, Any] | None = None,
        files: list[UploadFile] | None = None,
        autonomy_mode: str = "high",
    ) -> AsyncIterator[str]:
        async for event_name, payload in self._run(
            db=db,
            user_id=user_id,
            object_path=object_path,
            message=message,
            selected_cell=selected_cell,
            selected_dataset=selected_dataset,
            context=context or {},
            files=files or [],
            autonomy_mode=autonomy_mode,
        ):
            yield self._sse(event_name, payload)

    async def _run(
        self,
        *,
        db: AsyncSession,
        user_id: int,
        object_path: str,
        message: str,
        selected_cell: str | None,
        selected_dataset: str | None,
        context: dict[str, Any],
        files: list[UploadFile],
        autonomy_mode: str,
    ) -> AsyncIterator[tuple[str, dict[str, Any]]]:
        generation_log: list[str] = []
        warnings: list[str] = []
        errors: list[str] = []
        normalized_path = fr_report_version_control_service.normalize_target_object_path(
            report_name=None,
            target_folder=None,
            target_object_path=object_path,
            fallback_object_path=object_path,
        )
        conversation_id = str(context.get("conversationId") or context.get("conversation_id") or f"fr-report:{normalized_path}")
        trace_cm = langfuse_observability.current_observation(
            name="fr_report_high_authority_agent",
            as_type="agent",
            input={"message": message, "objectPath": normalized_path, "selectedCell": selected_cell, "selectedDataset": selected_dataset},
            metadata={
                "conversation_id": conversation_id,
                "autonomy_mode": autonomy_mode,
                "user_id": user_id,
                "chain_version": self.CHAIN_VERSION,
            },
        )
        trace_observation = trace_cm.__enter__()
        trace_context = self._trace_context_from_observation(trace_observation)

        try:
            yield self._message(self._opening_message(message))
            yield self._tool_result(
                "agent_chain",
                f"当前运行链路：{self.CHAIN_VERSION}。如果执行轨迹里不是这个版本，说明页面请求没有命中最新后端。",
                {"chainVersion": self.CHAIN_VERSION},
            )
            yield self._tool_started("read_cpt_full", "读取完整 CPT 文件")
            source_bytes = await fr_minio_service.download_file(normalized_path)
            source_xml = source_bytes.decode("utf-8", errors="strict")
            fr_report_ai_operation_service._validate_full_cpt_xml(source_xml)
            yield (
                "file_read",
                {
                    "toolName": "read_cpt_full",
                    "objectPath": normalized_path,
                    "size": len(source_bytes),
                    "xmlChars": len(source_xml),
                    "summary": "完整 CPT XML 已读取，后续会按整份 WorkBook 改写。",
                },
            )

            yield self._tool_started("inspect_report_layout", "解析当前报表结构和单元格语义")
            structure = await fr_report_file_service.read_report_structure(
                db=db,
                user_id=user_id,
                object_path=normalized_path,
            )
            selected_cell_read = fr_report_ai_operation_service._find_cell(structure, selected_cell)
            report_layout_context = fr_report_ai_operation_service._build_report_layout_context(structure)
            cpt_xml_index = fr_report_ai_operation_service._build_cpt_xml_index(source_xml)
            cpt_source_context = fr_report_ai_operation_service._build_cpt_source_context(
                source_xml,
                selected_cell_read,
                message,
            )
            yield self._tool_result(
                "inspect_report_layout",
                "已拿到当前报表结构、单元格矩阵、数据集和 XML 索引。",
                {
                    "datasetCount": structure.summary.datasetCount,
                    "parameterCount": structure.summary.parameterCount,
                    "cellCount": structure.summary.cellCount,
                    "selectedCell": selected_cell,
                },
            )
            yield self._tool_started("inspect_database_schema", "读取需求和现有 SQL 相关的数据库结构")
            database_source_context = await fr_report_ai_operation_service._build_database_source_context(
                prompt=message,
                structure=structure,
                source_xml=source_xml,
                db=db,
                user_id=user_id,
            )
            yield (
                "db_query",
                {
                    "toolName": "inspect_database_schema",
                    "summary": self._database_context_summary(database_source_context),
                    "payload": self._compact(database_source_context, 12000),
                },
            )

            attachment_context = []
            if files:
                yield self._tool_started("read_attachments", "解析 Excel / Word / 图片附件")
                attachment_context = await self._read_attachments(files, context=context, autonomy_mode=autonomy_mode)
                yield self._tool_result(
                    "read_attachments",
                    f"已解析 {len(attachment_context)} 个附件。",
                    {"files": [item.get("fileName") for item in attachment_context]},
                )

            base_model_payload = {
                "autonomyMode": autonomy_mode or "high",
                "userRequest": message,
                "objectPath": normalized_path,
                "selectedCell": selected_cell,
                "selectedDataset": selected_dataset,
                "context": context,
                "reportStructure": self._compact_structure(structure),
                "reportLayoutContext": self._compact(report_layout_context, 18000),
                "cptXmlIndex": self._compact(cpt_xml_index, 10000),
                "cptSourceContext": self._compact(cpt_source_context, 18000),
                "workbookEditingContext": self._compact(self._build_workbook_editing_context(source_xml), 22000),
                "databaseSourceContext": self._compact(database_source_context, 16000),
                "attachmentContext": self._compact(attachment_context, 18000),
                "fullCptXmlAvailable": True,
                "expectedJson": {
                    "assistantMessage": "自然语言说明",
                    "operations": [
                        {
                            "operationType": "file_edit",
                            "summary": "自然语言修改内容",
                            "riskLevel": "low | medium | high",
                            "payload": {
                                "edits": [
                                    {
                                        "oldText": "当前 CPT 中要替换的完整原文片段",
                                        "newText": "替换后的完整片段",
                                        "replaceAll": False,
                                    }
                                ]
                            },
                        }
                    ],
                    "finalCptXml": "可选。只有 exact edit 难以稳定表达时才返回完整 WorkBook XML。",
                    "warnings": [],
                    "validationFocus": ["需要预览验证的点"],
                },
            }
            react_result: dict[str, Any] | None = None
            yield self._tool_started("search_reference_cpt", "先找相似报表写法，再按文件编辑 CPT")
            try:
                reference_case_context = await fr_report_case_service.read_reference_case_context(db, query=message, limit=5)
            except Exception as exc:
                reference_case_context = {"summary": "案例库检索失败，本轮继续按当前 CPT 原文处理。", "error": str(exc), "hits": []}
                warnings.append(f"案例库检索失败：{exc}")
            yield self._tool_result(
                "search_reference_cpt",
                str(reference_case_context.get("summary") or "案例库检索完成。"),
                self._compact(reference_case_context, 30000),
            )
            yield self._tool_started("edit_cpt_file", "按直接文件编辑生成候选 CPT")
            structural_candidate_xml, structural_warnings = self._normalize_horizontal_expansion_parenting(source_xml)
            structural_candidate_xml, total_warnings = self._normalize_static_total_columns_after_horizontal_expansion(
                structural_candidate_xml
            )
            structural_warnings.extend(total_warnings)
            if structural_candidate_xml != source_xml and self._should_apply_structural_self_heal(message):
                warnings.extend(structural_warnings)
                react_result = {
                    "assistantMessage": (
                        "我先把当前报表里已经存在的横向扩展关系修正掉。"
                        "这类问题会让合计、备注等普通列跟着横向分组重复、错位，或把合计误当成明细列展开。"
                    ),
                    "candidateXml": structural_candidate_xml,
                    "operations": [
                        {
                            "operationType": "file_edit",
                            "summary": "修正横向扩展右侧普通单元格的父格配置，并把静态合计列从明细字段绑定改为横向求和公式。",
                            "riskLevel": "low",
                        }
                    ],
                    "modelResult": {
                        "assistantMessage": "已按当前 CPT 结构修正横向扩展关系。",
                        "validationFocus": ["打开预览检查横向扩展右侧的合计、备注等普通列是否只出现一次、位置正确，且合计按每行横向求和。"],
                        "warnings": structural_warnings,
                    },
                }
                yield self._tool_result(
                    "edit_cpt_file",
                    "发现当前 CPT 已有横向扩展父格错位，已先按结构自愈生成候选 CPT。",
                    {"mode": "structural_self_heal", "warnings": structural_warnings},
                )
            if not react_result:
                direct_result = await self._direct_file_edit_result(
                    source_xml=source_xml,
                    base_payload=base_model_payload,
                    reference_case_context=reference_case_context,
                    langfuse_trace_context=trace_context,
                    conversation_id=conversation_id,
                )
                if direct_result:
                    react_result = direct_result
                    yield self._tool_result(
                        "edit_cpt_file",
                        "候选 CPT 已通过文件编辑生成，准备进入统一校验和版本写入。",
                        {"mode": "direct_file_edit", "xmlChars": len(str(direct_result.get("candidateXml") or ""))},
                    )
                else:
                    yield self._tool_result(
                        "edit_cpt_file",
                        "文件编辑成稿没有稳定返回，我会继续读取上下文后重试。",
                        {"mode": "fallback_to_react_file_edit"},
                    )

            if not react_result:
                async for event_name, payload in self._run_react_loop(
                    source_xml=source_xml,
                    base_payload=base_model_payload,
                    database_source_context=database_source_context,
                    attachment_context=attachment_context,
                    langfuse_trace_context=trace_context,
                    conversation_id=conversation_id,
                    db=db,
                    user_id=user_id,
                ):
                    if event_name == "__react_result__":
                        react_result = payload
                        continue
                    yield event_name, payload
            if not react_result:
                errors.append("Agent 循环没有返回可用结果。")
                yield self._final("blocked", "这次没有形成可写入修改。", normalized_path, warnings, errors)
                return

            model_result = dict(react_result.get("modelResult") or {})
            assistant_message = str(
                react_result.get("assistantMessage")
                or model_result.get("assistantMessage")
                or "我整理出一版可确认的修改。"
            )
            candidate_xml = str(react_result.get("candidateXml") or "").strip()
            if assistant_message:
                yield self._message(assistant_message)

            operations = self._normalize_operations(model_result)
            if react_result.get("operations"):
                operations = list(react_result.get("operations") or operations)
            if not candidate_xml and not operations and not str(model_result.get("finalCptXml") or "").strip():
                errors.append("模型没有返回可写入的 CPT 文件编辑。")
                yield self._final("blocked", assistant_message, normalized_path, warnings, errors)
                return

            yield self._tool_started("edit_cpt_file", "生成候选 CPT，并先做 XML 和 SQL 校验")
            try:
                candidate_xml, operations, model_result, assistant_message, candidate_warnings = await self._prepare_candidate_with_repair(
                    source_xml=source_xml,
                    initial_candidate_xml=candidate_xml,
                    initial_model_result=model_result,
                    initial_operations=operations,
                    assistant_message=assistant_message,
                    model_payload=base_model_payload,
                    db=db,
                    user_id=user_id,
                )
            except CandidatePreparationError as exc:
                await self._rollback_session_safely(db, "候选 CPT 准备失败")
                warnings.extend(exc.warnings)
                errors.append(str(exc))
                yield self._tool_result(
                    "edit_cpt_file",
                    "候选 CPT 已自动修复过，但仍未通过 XML 或 SQL 校验。",
                    {"repairAttempts": len(exc.warnings), "error": str(exc)},
                )
                yield self._final(
                    "failed",
                    "我已经按当前报表和错误信息自动修过，但这版候选 CPT 仍没过校验，还没有写入文件。",
                    normalized_path,
                    warnings,
                    errors,
                )
                return
            if candidate_warnings:
                warnings.extend(candidate_warnings)
            candidate_audit = model_result.get("_candidateAudit") if isinstance(model_result.get("_candidateAudit"), dict) else {}
            if candidate_audit:
                audit_facts = candidate_audit.get("facts") if isinstance(candidate_audit.get("facts"), dict) else {}
                yield self._tool_result(
                    "validate_candidate_cpt",
                    "候选 CPT 已完成结构、绑定和影响面审计。",
                    {
                        "status": candidate_audit.get("status") or "passed",
                        "datasetCount": audit_facts.get("datasetCount"),
                        "dsColumnCount": audit_facts.get("dsColumnCount"),
                        "warningCount": len(candidate_audit.get("warnings") or []),
                    },
                )
            if not self._should_write_immediately(message, autonomy_mode):
                operation_draft = self._build_operation_draft(
                    assistant_message=assistant_message,
                    normalized_path=normalized_path,
                    operations=operations,
                    candidate_xml=candidate_xml,
                    warnings=warnings + [str(item) for item in model_result.get("warnings") or []],
                )
                yield self._tool_result(
                    "prepare_operation_draft",
                    "候选修改已生成，等待确认后再写入 CPT。",
                    {"operationCount": len(operation_draft["operations"]), "storageImpact": "未写入版本库，不占用 CPT 版本存储。"},
                )
                yield self._final(
                    "draft_ready",
                    assistant_message or "我先把修改放到待确认里了，还没写 CPT，也没产生新版本。",
                    normalized_path,
                    warnings,
                    [],
                    operationDraft=operation_draft,
                )
                return

            yield self._tool_result("edit_cpt_file", "候选 CPT XML 校验通过，准备写入版本库。", {"operationCount": len(operations)})

            latest_snapshot = await fr_report_ai_operation_service._latest_snapshot(db, user_id, normalized_path)
            snapshot_no = (latest_snapshot.snapshot_no + 1) if latest_snapshot else 1
            snapshot = FrReportSnapshot(
                snapshot_id=f"fr-high-{uuid4().hex[:12]}",
                object_path=normalized_path,
                report_path=structure.reportPath,
                file_name=structure.fileName,
                file_type=structure.fileType,
                user_id=user_id,
                parent_snapshot_id=latest_snapshot.snapshot_id if latest_snapshot else None,
                source_etag=structure.etag,
                source_last_modified=structure.lastModified.isoformat() if structure.lastModified else None,
                snapshot_no=snapshot_no,
                status="high_authority_generated",
                title=structure.fileName,
                summary={
                    "message": message,
                    "assistantMessage": assistant_message,
                    "autonomyMode": autonomy_mode,
                    "selectedCell": selected_cell,
                    "selectedDataset": selected_dataset,
                },
                document_snapshot={
                    "mode": "high_authority_agent",
                    "reportLayoutContext": self._compact(report_layout_context, 50000),
                    "databaseSourceContext": self._compact(database_source_context, 30000),
                    "validationFocus": model_result.get("validationFocus") or [],
                },
                applied_patch={
                    "sourceType": "high_authority_agent",
                    "operations": self._compact(operations, 80000),
                },
                source_hash=fr_report_ai_operation_service._hash_payload({"objectPath": normalized_path, "source": source_xml}),
                create_by=str(user_id),
                update_by=str(user_id),
            )
            db.add(snapshot)
            await db.flush()

            generation_log.extend(
                [
                    self._log("高权限 Agent 已读取完整 CPT"),
                    self._log("已生成候选 CPT XML"),
                    self._log("开始写入版本库并覆盖目标 CPT"),
                ]
            )
            project, structure_version, file_version, conflict = await fr_report_version_control_service.save_snapshot_file_version(
                db=db,
                user_id=user_id,
                snapshot=snapshot,
                cpt_bytes=candidate_xml.encode("utf-8"),
                dsl_payload={
                    "mode": "high_authority_agent",
                    "message": message,
                    "reportName": structure.fileName,
                    "validationFocus": model_result.get("validationFocus") or [],
                },
                operations=operations,
                generation_log=generation_log,
                target_object_path=normalized_path,
                conflict_strategy="archive_and_overwrite",
                warnings=warnings + [str(item) for item in model_result.get("warnings") or []],
                errors=[],
            )
            if conflict:
                errors.append(str(conflict.get("message") or "目标 CPT 存在外部修改冲突，已阻止写入。"))
                yield self._final("conflict", assistant_message, normalized_path, warnings, errors, conflict=conflict)
                return
            if not file_version:
                errors.append("版本文件保存失败。")
                yield self._final("failed", assistant_message, normalized_path, warnings, errors)
                return

            yield (
                "cpt_written",
                {
                    "summary": "CPT 已写入目标路径，并同步生成结构版本和文件版本。",
                    "objectPath": normalized_path,
                    "reportId": project.report_id,
                    "fileVersionId": file_version.file_version_id,
                    "structureVersionId": structure_version.structure_version_id if structure_version else None,
                    "versionNo": file_version.version_no,
                    "archiveObjectPath": file_version.archive_object_path,
                },
            )

            reportlet_path = fr_report_version_control_service.reportlet_path(normalized_path)
            yield self._tool_started("validate_finereport_preview", "打开 FineReport 预览做真实校验")
            try:
                preview_result = await asyncio.wait_for(preview_validator.validate(reportlet_path), timeout=35)
            except TimeoutError:
                preview_result = PreviewValidationResult(
                    previewUrl=preview_validator._preview_url(reportlet_path),
                    warnings=["FineReport 预览校验超时，版本已保留，可稍后手动打开预览核对。"],
                )
            file_version.preview_url = preview_result.previewUrl
            file_version.warnings = list(file_version.warnings or []) + preview_result.warnings
            file_version.errors = preview_result.errors
            file_version.write_status = "generated" if not preview_result.errors else "preview_failed"
            snapshot.preview_url = preview_result.previewUrl
            snapshot.generation_warnings = list(snapshot.generation_warnings or []) + preview_result.warnings
            snapshot.generation_errors = preview_result.errors
            db.add(file_version)
            db.add(snapshot)
            await db.commit()
            yield (
                "preview_result",
                {
                    "summary": "预览校验通过。" if not preview_result.errors else "预览返回错误，已保留版本，可继续让 Agent 修复。",
                    "previewUrl": preview_result.previewUrl,
                    "warnings": preview_result.warnings,
                    "errors": preview_result.errors,
                },
            )

            final_status = "success" if not preview_result.errors else "preview_failed"
            final_message = self._build_write_completion_message(
                status=final_status,
                object_path=normalized_path,
                version_no=file_version.version_no,
                preview_url=preview_result.previewUrl,
                warnings=warnings + preview_result.warnings,
                errors=preview_result.errors,
            )
            yield self._final(
                final_status,
                final_message,
                normalized_path,
                warnings + preview_result.warnings,
                preview_result.errors,
                snapshot_id=snapshot.snapshot_id,
                preview_url=preview_result.previewUrl,
                report_id=project.report_id,
                file_version_id=file_version.file_version_id,
                structure_version_id=structure_version.structure_version_id if structure_version else None,
                version_no=file_version.version_no,
                archive_object_path=file_version.archive_object_path,
            )
        except Exception as exc:
            logger.exception(f"FineReport 高权限 Agent 执行失败：{exc}")
            await self._rollback_session_safely(db, "FineReport 高权限 Agent 执行失败")
            errors.append(str(exc))
            yield self._final("failed", "这次没有写入成功，错误已经保留在事件里。", normalized_path, warnings, errors)
        finally:
            try:
                trace_observation.update(
                    output={"warnings": warnings, "errors": errors},
                    metadata={"conversation_id": conversation_id, "status": "failed" if errors else "completed"},
                )
                trace_observation.update_trace(
                    session_id=conversation_id,
                    user_id=str(user_id),
                    tags=["fr-report-agent", "high-authority", "work-loop"],
                    metadata={"object_path": normalized_path, "autonomy_mode": autonomy_mode},
                )
            except Exception as trace_exc:
                logger.debug(f"FineReport Agent LangFuse trace 更新失败：{trace_exc}")
            trace_cm.__exit__(None, None, None)
            langfuse_observability.flush()

    def _should_use_direct_file_edit(self, message: str, source_xml: str) -> bool:
        xml_chars = len(source_xml or "")
        return 0 < xml_chars <= 180000

    def _should_apply_structural_self_heal(self, message: str) -> bool:
        text = (message or "").strip()
        if not text:
            return False
        layout_terms = ("错位", "预览", "合计", "备注", "插入", "新增", "增加", "横向", "扩展", "列", "父格")
        return any(term in text for term in layout_terms)

    async def _rollback_session_safely(self, db: AsyncSession | None, reason: str) -> None:
        if db is None:
            return
        try:
            await db.rollback()
        except Exception as exc:
            logger.warning(f"{reason}后回滚数据库会话失败：{exc}")

    async def _direct_file_edit_result(
        self,
        *,
        source_xml: str,
        base_payload: dict[str, Any],
        reference_case_context: dict[str, Any],
        langfuse_trace_context: dict[str, str] | None,
        conversation_id: str | None,
    ) -> dict[str, Any] | None:
        direct_payload = {
            "userRequest": base_payload.get("userRequest"),
            "objectPath": base_payload.get("objectPath"),
            "selectedCell": base_payload.get("selectedCell"),
            "selectedDataset": base_payload.get("selectedDataset"),
            "reportLayoutContext": self._compact(base_payload.get("reportLayoutContext"), 12000),
            "workbookEditingContext": self._compact(base_payload.get("workbookEditingContext"), 14000),
            "databaseSourceContext": self._compact(base_payload.get("databaseSourceContext"), 10000),
            "attachmentContext": self._compact(base_payload.get("attachmentContext"), 10000),
            "fullCptXml": self._compact(source_xml, 120000),
            "referenceCaseContext": self._compact(reference_case_context, 16000),
            "instruction": (
                "这是直接文件编辑任务。把 CPT 当作一份 XML 源码文件处理："
                "先基于完整原文定位要改的节点，默认返回 file_edit 精确替换块。"
                "file_edit 的 oldText 必须是当前 CPT 中真实存在且尽量唯一的完整 XML 原文片段，newText 是替换后的片段。"
                "只有 exact edit 难以稳定表达或改动范围过大时，才返回 finalCptXml 作为完整 WorkBook 兜底。"
                "多要求、多节点联动、填报、样式、条件属性、隐藏行列、数据集 SQL 都可以用多个 file_edit 串起来。"
                "保留所有未涉及节点，不要重排无关 XML，不要删除未知配置，不要输出旧 xml_patch/selector 写入器。"
                "如果参考案例有用，只模仿写法，不覆盖当前报表的表名、字段、坐标和用户指令。"
                "遇到 ReportWriteAttr、脚本、控件、条件属性等高结构节点，不能凭空合成 XML；必须从当前 CPT 或参考报表读取真实完整节点后迁移。"
                "横向扩展区域右侧新增、移动或修改任何单元格时，都必须检查父格：表头、数据单元格、公式、备注、按钮、填报控件的 Expand、leftParentDefault、topParentDefault、left/top、sortHeader 都要一起确认，避免被横向扩展链复制或错位。"
            ),
            "expectedJson": {
                "assistantMessage": "一句自然中文，说明这版直接改了什么",
                "operations": [
                    {
                        "operationType": "file_edit",
                        "summary": "自然语言修改内容",
                        "riskLevel": "low|medium|high",
                        "payload": {
                            "edits": [
                                {
                                    "oldText": "当前 CPT 中真实存在的完整 XML 原文片段",
                                    "newText": "替换后的完整 XML 片段",
                                    "replaceAll": False,
                                }
                            ]
                        },
                    }
                ],
                "finalCptXml": "可选。只有 exact edit 不适合表达时才返回完整 WorkBook XML。",
                "warnings": [],
                "validationFocus": [],
            },
        }
        try:
            result = await asyncio.wait_for(
                fr_report_ai_operation_service._invoke_json(
                    system_prompt=self._direct_file_system_prompt(),
                    payload=direct_payload,
                    agent_name="FrReportDirectFileEditAgent",
                    langfuse_trace_context=langfuse_trace_context,
                    langfuse_run_name="fr_report_direct_file_edit",
                    langfuse_metadata={"conversation_id": conversation_id, "mode": "direct_file_edit"},
                ),
                timeout=self.DIRECT_FILE_EDIT_TIMEOUT_SECONDS,
            )
            operations = self._normalize_operations(result)
            if not operations and not str(result.get("finalCptXml") or "").strip():
                return None
            candidate_xml = self._build_candidate_xml(source_xml, result, operations)
            fr_report_ai_operation_service._validate_full_cpt_xml(candidate_xml)
            return {
                "modelResult": result,
                "assistantMessage": str(result.get("assistantMessage") or "我按当前 CPT 原文生成了一版候选修改。"),
                "candidateXml": candidate_xml,
                "operations": operations,
            }
        except asyncio.TimeoutError:
            logger.warning("FineReport 直接文件编辑超时")
            return None
        except Exception as exc:
            logger.warning(f"FineReport 直接文件编辑失败: {exc}")
            return None

    def _direct_file_system_prompt(self) -> str:
        return (
            "你是 FineReport CPT 文件编辑 Agent，工作方式是直接修改源码文件。"
            "CPT 是 XML 源码文件，用户要改什么，你就在完整 XML 中找到对应位置并产出精确文件编辑。"
            "优先整体理解 WorkBook、TableDataMap、ReportPageAttr、ColumnWidth、CellElementList、StyleList、ReportWriteAttr、Widget 和脚本之间的影响关系。"
            "默认返回 operations: [{operationType:'file_edit', payload:{edits:[{oldText,newText,replaceAll:false}]}}]。"
            "oldText 必须逐字来自当前 CPT，且尽量包含足够上下文避免误替换；newText 只包含替换后的对应片段。"
            "只有修改横跨大量位置、无法稳定用若干 exact edit 表达时，才返回 finalCptXml 完整 WorkBook。"
            "保持未涉及内容原样，不得重建整份无关结构，不得硬编码预览样例值。"
            "隐藏列要用 FineReport 原生 ReportPageAttr/HC 并同步 ColumnWidth；格式、条件属性、控件、填报和 SQL 要按当前 CPT 原生写法延续。"
            "如果用户要求参考某报表或案例，只参考节点写法，当前报表的表名、字段、坐标、参数和数据集事实优先。"
            "ReportWriteAttr、脚本、控件和复杂条件属性属于高结构节点；没有当前 CPT 或参考报表的完整真实写法时，不要自己拼新结构。"
            "横向扩展区域右侧新增、移动或修改任何单元格时，都必须先判断父格关系；不要只检查合计列。表头、数据行、公式、备注、按钮和填报列都要同步检查 leftParentDefault、topParentDefault、left/top、sortHeader 和是否误入横向扩展链。"
            "返回严格 JSON：assistantMessage、operations、finalCptXml、warnings、validationFocus。不要 Markdown，不要解释 XML。"
        )

    async def _run_react_loop(
        self,
        *,
        source_xml: str,
        base_payload: dict[str, Any],
        database_source_context: dict[str, Any],
        attachment_context: list[dict[str, Any]],
        langfuse_trace_context: dict[str, str] | None = None,
        conversation_id: str | None = None,
        db: AsyncSession | None = None,
        user_id: int | None = None,
    ) -> AsyncIterator[tuple[str, dict[str, Any]]]:
        observations: list[dict[str, Any]] = []
        loop_state: dict[str, Any] = {}
        last_result: dict[str, Any] = {}
        max_steps = 6

        for step in range(1, max_steps + 1):
            payload = {
                **base_payload,
                "workStep": step,
                "observations": observations[-10:],
                "availableTools": self._react_available_tools(),
                "instruction": (
                    "你必须按观察、行动、验证的循环推进：如果信息不足，返回 toolCalls；如果已经能修改，优先返回 file_edit 精确文件编辑。"
                    "不要把工具名当成最终修改；真正写入 CPT 必须给出可应用的 file_edit，必要时再用 finalCptXml 兜底。"
                ),
                "expectedJson": self._react_expected_json(),
            }
            model_task = asyncio.create_task(
                fr_report_ai_operation_service._invoke_json(
                    system_prompt=self._react_system_prompt(),
                    payload=payload,
                    agent_name=f"FrReportHighAuthorityWorkAgent.step{step}",
                    langfuse_trace_context=langfuse_trace_context,
                    langfuse_run_name=f"fr_report_work_step_{step}",
                    langfuse_metadata={
                        "conversation_id": conversation_id,
                        "work_step": step,
                        "tool_observation_count": len(observations),
                    },
                )
            )
            heartbeat = 0
            started_at = asyncio.get_running_loop().time()
            timed_out = False
            while not model_task.done():
                elapsed = asyncio.get_running_loop().time() - started_at
                remaining = self.REACT_MODEL_STEP_TIMEOUT_SECONDS - elapsed
                if remaining <= 0:
                    timed_out = True
                    break
                done, _pending = await asyncio.wait({model_task}, timeout=min(8, remaining))
                if done:
                    break
                heartbeat += 1
                yield self._message(self._react_heartbeat(step, heartbeat))
            if timed_out and not model_task.done():
                model_task.cancel()
                try:
                    await model_task
                except asyncio.CancelledError:
                    pass
                observations.append(
                    {
                        "toolName": "planning_step",
                        "status": "timeout",
                        "payload": {
                            "step": step,
                            "timeoutSeconds": self.REACT_MODEL_STEP_TIMEOUT_SECONDS,
                            "hint": "上一轮模型没有在时间内返回；下一轮必须缩小修改范围，优先基于已读事实直接给出可写入 CPT。",
                        },
                    }
                )
                yield self._tool_result(
                    "planning_step",
                    "这一轮模型没有及时返回，我先中断它，带着已读到的上下文继续收束。",
                    {"step": step, "timeoutSeconds": self.REACT_MODEL_STEP_TIMEOUT_SECONDS, "status": "timeout"},
                )
                if step >= max_steps:
                    break
                continue
            try:
                result = await model_task
            except Exception as exc:
                observations.append(
                    {
                        "toolName": "planning_step",
                        "status": "failed",
                        "error": str(exc),
                        "payload": {
                            "step": step,
                            "hint": "上一轮模型调用失败；下一轮必须基于已读事实缩小范围并返回可写入 CPT。",
                        },
                    }
                )
                yield self._tool_result(
                    "planning_step",
                    "这一轮模型调用失败，我会保留错误并继续尝试收束。",
                    {"step": step, "error": str(exc), "status": "failed"},
                )
                if step >= max_steps:
                    break
                continue
            last_result = result
            assistant_message = str(result.get("assistantMessage") or "").strip()
            if assistant_message:
                yield self._message(assistant_message)

            operations = self._normalize_operations(result)
            if operations or str(result.get("finalCptXml") or "").strip():
                deterministic_result = self._build_dimension_order_result(
                    source_xml=source_xml,
                    base_payload=base_payload,
                    attachment_context=attachment_context,
                    observations=observations,
                    last_result=result,
                )
                if deterministic_result:
                    yield self._tool_result(
                        "dimension_order_skill",
                        deterministic_result["summary"],
                        {
                            "dataset": deterministic_result.get("dataset"),
                            "field": deterministic_result.get("field"),
                            "labelCount": len(deterministic_result.get("labels") or []),
                        },
                    )
                    yield (
                        "__react_result__",
                        {
                            "modelResult": deterministic_result["modelResult"],
                            "assistantMessage": deterministic_result["assistantMessage"],
                            "candidateXml": deterministic_result["candidateXml"],
                            "operations": deterministic_result["operations"],
                        },
                    )
                    return
                if self._needs_evidence_before_accepting(base_payload, result, operations, observations):
                    yield self._tool_result(
                        "evidence_guard",
                        "这版修改先不直接采纳，我会补读当前 XML 片段和相似案例后再写。",
                        {"reason": "模型在缺少工具观察时已经给出 CPT 修改，容易出现坐标、格式或原生节点写法偏差。"},
                    )
                    observations.append(
                        {
                            "toolName": "evidence_guard",
                            "status": "needs_more_evidence",
                            "payload": {
                                "candidateSummary": self._compact(result, 12000),
                                "requiredEvidence": ["current_cpt_slice", "reference_case"],
                                "hint": "下一轮必须结合工具观察返回可应用 file_edit；必要时再返回完整 WorkBook。",
                            },
                        }
                    )
                    async for event in self._collect_preflight_evidence(
                        source_xml=source_xml,
                        base_payload=base_payload,
                        result=result,
                        operations=operations,
                        observations=observations,
                        database_source_context=database_source_context,
                        attachment_context=attachment_context,
                        db=db,
                        user_id=user_id,
                    ):
                        yield event
                    continue
                result["operations"] = operations
                date_format_gap = self._date_format_gap_observation(source_xml, base_payload, operations, observations)
                if date_format_gap:
                    observations.append(date_format_gap)
                    yield self._tool_result(
                        "evidence_guard",
                        "单元格格式还不够，我发现目标字段本身可能已经在 SQL 里被格式化，需要继续查数据集。",
                        {"reason": date_format_gap.get("hint")},
                    )
                    for selector in date_format_gap.get("selectors", []):
                        yield self._tool_started("read_cpt_slice", f"读取 {selector} 的数据集 XML")
                    event_name, event_payload, observation = await self._execute_react_tool(
                        tool_name="read_cpt_slice",
                        arguments={"selectors": date_format_gap.get("selectors", [])},
                        source_xml=source_xml,
                        database_source_context=database_source_context,
                        attachment_context=attachment_context,
                        loop_state={},
                        db=db,
                        user_id=user_id,
                    )
                    yield event_name, event_payload
                    observations.append(observation)
                    continue
                try:
                    candidate_xml = self._build_candidate_xml(source_xml, result, operations)
                    fr_report_ai_operation_service._validate_full_cpt_xml(candidate_xml)
                    loop_state["candidateXml"] = candidate_xml
                    loop_state["operations"] = operations
                    yield self._tool_result(
                        "edit_cpt_file",
                        "已在内存中生成候选 CPT，XML 结构校验通过。",
                        {"operationCount": len(operations), "mode": "file_edit_or_full_fallback"},
                    )
                    yield (
                        "__react_result__",
                        {
                            "modelResult": result,
                            "assistantMessage": assistant_message,
                            "candidateXml": candidate_xml,
                            "operations": operations,
                        },
                    )
                    return
                except Exception as exc:
                    observations.append(
                        {
                            "toolName": "edit_cpt_file",
                            "status": "failed",
                            "error": str(exc),
                            "hint": "下一轮必须先读取相关 XML 片段，再返回可应用的 file_edit；必要时用完整 WorkBook 兜底。",
                        }
                    )
                    yield (
                        "repair_started",
                        {"reason": str(exc), "summary": "候选修改没通过 XML 校验，我会带着错误继续下一轮修复。"},
                    )
                    continue

            tool_calls = self._normalize_tool_calls(result)
            if not tool_calls:
                request_driven_result = self._build_request_driven_candidate_result(source_xml=source_xml, base_payload=base_payload)
                if request_driven_result:
                    yield self._tool_result(
                        "request_driven_cpt_edit",
                        request_driven_result["summary"],
                        {"operationCount": len(request_driven_result["operations"])},
                    )
                    yield (
                        "__react_result__",
                        {
                            "modelResult": request_driven_result["modelResult"],
                            "assistantMessage": request_driven_result["assistantMessage"],
                            "candidateXml": request_driven_result["candidateXml"],
                            "operations": request_driven_result["operations"],
                        },
                    )
                    return
                yield (
                    "__react_result__",
                    {
                        "modelResult": result,
                        "assistantMessage": assistant_message or "我这次没有稳定定位到可写的修改，先不冒险写文件。",
                        "candidateXml": "",
                        "operations": [],
                    },
                )
                return

            filtered_tool_calls = self._filter_redundant_tool_calls(tool_calls, observations)
            if not filtered_tool_calls:
                observations.append(
                    {
                        "toolName": "tool_loop_guard",
                        "status": "enough_evidence",
                        "payload": {
                            "hint": "模型继续请求的工具已经读过或已达到本轮上限；下一步必须基于现有观察生成候选 CPT，不能继续重复读上下文。",
                            "requestedTools": [item.get("toolName") for item in tool_calls],
                        },
                    }
                )
                break

            for tool_call in filtered_tool_calls[:5]:
                tool_name = str(tool_call.get("toolName") or "").strip()
                arguments = tool_call.get("arguments") if isinstance(tool_call.get("arguments"), dict) else {}
                yield self._tool_started(tool_name, str(tool_call.get("reason") or self._react_tool_summary(tool_name)))
                event_name, event_payload, observation = await self._execute_react_tool(
                    tool_name=tool_name,
                    arguments=arguments,
                    source_xml=source_xml,
                    database_source_context=database_source_context,
                    attachment_context=attachment_context,
                    loop_state=loop_state,
                    db=db,
                    user_id=user_id,
                )
                observation["toolCallSignature"] = self._tool_call_signature(tool_name, arguments)
                yield event_name, event_payload
                observations.append(observation)
                if loop_state.get("candidateXml"):
                    yield (
                        "__react_result__",
                        {
                            "modelResult": loop_state.get("modelResult") or last_result,
                            "assistantMessage": assistant_message or "我整理出一版候选修改。",
                            "candidateXml": str(loop_state["candidateXml"]),
                            "operations": list(loop_state.get("operations") or []),
                        },
                    )
                    return

        deterministic_result = self._build_dimension_order_result(
            source_xml=source_xml,
            base_payload=base_payload,
            attachment_context=attachment_context,
            observations=observations,
            last_result=last_result,
        )
        if deterministic_result:
            yield self._tool_result(
                "dimension_order_skill",
                deterministic_result["summary"],
                {
                    "dataset": deterministic_result.get("dataset"),
                    "field": deterministic_result.get("field"),
                    "labelCount": len(deterministic_result.get("labels") or []),
                },
            )
            yield (
                "__react_result__",
                {
                    "modelResult": deterministic_result["modelResult"],
                    "assistantMessage": deterministic_result["assistantMessage"],
                    "candidateXml": deterministic_result["candidateXml"],
                    "operations": deterministic_result["operations"],
                },
            )
            return

        request_driven_result = self._build_request_driven_candidate_result(source_xml=source_xml, base_payload=base_payload)
        if request_driven_result:
            yield self._tool_result(
                "request_driven_cpt_edit",
                request_driven_result["summary"],
                {"operationCount": len(request_driven_result["operations"])},
            )
            yield (
                "__react_result__",
                {
                    "modelResult": request_driven_result["modelResult"],
                    "assistantMessage": request_driven_result["assistantMessage"],
                    "candidateXml": request_driven_result["candidateXml"],
                    "operations": request_driven_result["operations"],
                },
            )
            return

        finalization_result = await self._force_writable_result(
            source_xml=source_xml,
            base_payload=base_payload,
            observations=observations,
            last_result=last_result,
            langfuse_trace_context=langfuse_trace_context,
            conversation_id=conversation_id,
        )
        if finalization_result:
            yield self._tool_result(
                "final_review",
                "观察已经足够，我把模型从“继续分析”收束成可写入候选修改。",
                {"operationCount": len(finalization_result["operations"])},
            )
            yield (
                "__react_result__",
                {
                    "modelResult": finalization_result["modelResult"],
                    "assistantMessage": finalization_result["assistantMessage"],
                    "candidateXml": finalization_result["candidateXml"],
                    "operations": finalization_result["operations"],
                },
            )
            return

        yield (
            "__react_result__",
            {
                "modelResult": last_result,
                "assistantMessage": "我查了几轮还是没把修改路径稳定下来，这次先不写文件。",
                "candidateXml": "",
                "operations": [],
            },
        )

    def _react_available_tools(self) -> list[dict[str, Any]]:
        return [
            {"name": "read_cpt_full", "description": "读取完整 CPT XML。多节点联动或片段不足时优先调用。"},
            {"name": "read_cpt_slice", "description": "按 selector 读取 XML 片段，例如 cell:B5、TableData[name=\"ds1\"]、ReportPageAttr。"},
            {"name": "search_xml", "description": "在当前 CPT XML 中搜索文本或标签，返回命中上下文。"},
            {"name": "inspect_report_layout", "description": "重新查看报表结构、单元格语义、隐藏行列和数据集绑定。"},
            {"name": "inspect_database_schema", "description": "查询真实数据库表结构，参数 tableNames 为英文表名数组。"},
            {"name": "query_database_sample", "description": "执行只读 SELECT 样例查询，确认字段和样例数据。"},
            {"name": "read_excel_context", "description": "读取本轮上传 Excel 的结构化摘要。"},
            {"name": "read_word_context", "description": "读取本轮上传 Word 的文本需求摘要。"},
            {
                "name": "search_fr_setting_knowledge",
                "description": "检索 FineReport 属性面板能力到 CPT XML 节点的受控参考；它不是规则引擎，只提示适用场景、节点线索和验证重点。",
            },
            {"name": "search_reference_cpt", "description": "按当前观察动态检索案例库中的真实参考报表写法；每次准备写入 CPT 前必须调用，开局不做无目的全量预加载。"},
            {"name": "read_reference_cpt_case", "description": "读取某个参考案例的关键 XML 片段，用于模仿真实写法。"},
            {"name": "read_reference_report_full", "description": "读取参考报表完整 CPT XML；只在案例片段仍不够时调用。"},
            {"name": "edit_cpt_file", "description": "在内存中应用 oldText/newText 精确文件编辑，成功后进入版本写入。"},
            {"name": "write_cpt_full", "description": "兜底工具：在 exact edit 无法稳定表达时，使用完整 WorkBook XML 替换当前 CPT。"},
        ]

    def _build_dimension_order_result(
        self,
        *,
        source_xml: str,
        base_payload: dict[str, Any],
        attachment_context: list[dict[str, Any]],
        observations: list[dict[str, Any]],
        last_result: dict[str, Any],
    ) -> dict[str, Any] | None:
        request = str(base_payload.get("userRequest") or "")
        if not re.search(r"顺序|排序|次序|和.*一致|按.*图片|按.*附件|表头.*(?:一致|顺序|排序)|地区.*(?:一致|顺序|排序)", request):
            return None
        labels = self._extract_ordered_labels_from_context(
            base_payload=base_payload,
            attachment_context=attachment_context,
            observations=observations,
            last_result=last_result,
        )
        if len(labels) < 3:
            return None
        dimension = self._find_horizontal_dimension(source_xml)
        if not dimension:
            return None
        table_data = self._find_table_data_query(source_xml, str(dimension["dataset"]))
        if not table_data:
            return None
        next_query = self._rewrite_query_order_by_labels(
            table_data["query"],
            field_name=str(dimension["field"]),
            labels=labels,
        )
        if not next_query or next_query == table_data["query"]:
            return None

        next_table_data_xml = table_data["rawXml"].replace(table_data["query"], next_query, 1)
        if next_table_data_xml == table_data["rawXml"]:
            return None
        candidate_xml = source_xml.replace(table_data["rawXml"], next_table_data_xml, 1)
        operations = [
            {
                "operationType": "file_edit",
                "summary": f"按附件图片中的顺序调整 {dimension['field']} 横向扩展列排序",
                "riskLevel": "medium",
                "payload": {
                    "source": "dimension_order_skill",
                    "edits": [
                        {
                            "oldText": table_data["rawXml"],
                            "newText": next_table_data_xml,
                            "replaceAll": False,
                        }
                    ],
                },
            }
        ]
        model_result = {
            "assistantMessage": (
                f"图片里的地区顺序已经读出来了，我把数据集 {dimension['dataset']} 的排序改成按这组顺序输出，"
                "横向扩展表头会跟着变。"
            ),
            "operations": operations,
            "warnings": ["本轮修改数据集 SQL 的排序逻辑，需要用 FineReport 预览确认横向列顺序。"],
            "validationFocus": ["预览表头地区顺序是否与附件图片一致", "均价列是否仍在横向地区列之后"],
        }
        try:
            fr_report_ai_operation_service._validate_full_cpt_xml(candidate_xml)
        except Exception:
            logger.exception("维度顺序技能生成候选 CPT 失败")
            return None

        return {
            "summary": "已把附件/图片里的表头顺序写入完整 CPT 候选。",
            "dataset": dimension["dataset"],
            "field": dimension["field"],
            "labels": labels,
            "modelResult": model_result,
            "assistantMessage": str(model_result["assistantMessage"]),
            "candidateXml": candidate_xml,
            "operations": operations,
        }

    def _build_request_driven_candidate_result(self, *, source_xml: str, base_payload: dict[str, Any]) -> dict[str, Any] | None:
        return None

    def _extract_ordered_labels_from_context(
        self,
        *,
        base_payload: dict[str, Any],
        attachment_context: list[dict[str, Any]],
        observations: list[dict[str, Any]],
        last_result: dict[str, Any],
    ) -> list[str]:
        texts: list[str] = [
            str(base_payload.get("userRequest") or ""),
            str(last_result.get("assistantMessage") or ""),
        ]
        for item in attachment_context:
            texts.append(str(item.get("imageSummary") or ""))
            texts.append(str(item.get("text") or ""))
        for item in observations[-12:]:
            texts.append(str(item.get("payload") or ""))
            texts.append(str(item.get("error") or ""))

        candidates: list[str] = []
        combined = "\n".join(text for text in texts if text)
        for match in re.finditer(r"(?:目标|表头|地区|字段|列)?顺序(?:为|是|[:：])\s*([^\n。；;]+)", combined):
            candidates.extend(self._split_order_label_text(match.group(1)))
        for line in combined.splitlines():
            if len(candidates) >= 3:
                break
            if not re.search(r"、|，|,|\|", line):
                continue
            if not re.search(r"地区|表头|顺序|图片|附件|可见|列", line):
                continue
            candidates.extend(self._split_order_label_text(line))

        labels: list[str] = []
        noise = {
            "目标",
            "表头",
            "地区",
            "顺序",
            "图片",
            "附件",
            "可见",
            "字段",
            "数据",
            "列",
            "豆粕",
            "涨跌",
            "均价",
            "全国均价",
        }
        for label in candidates:
            normalized = re.sub(r"\s+", "", label.strip(" '\"`，,、。；;:：|[]（）()"))
            if not normalized or normalized in labels or normalized in noise:
                continue
            if re.search(r"\d|=|价格|蛋白|备注|截图|解析|当前|修改|输出|确保|预览", normalized):
                continue
            if not (1 < len(normalized) <= 12):
                continue
            labels.append(normalized)
            if len(labels) >= 80:
                break
        return labels

    def _split_order_label_text(self, text: str) -> list[str]:
        clean = re.sub(r"[\[\]（）()]", " ", str(text or ""))
        clean = re.sub(r"\b(?:and|or|then|else)\b", " ", clean, flags=re.I)
        return [item for item in re.split(r"[、，,|/\\\s]+", clean) if item.strip()]

    def _find_horizontal_dimension(self, source_xml: str) -> dict[str, str] | None:
        for match in re.finditer(r"<C\b[^>]*>.*?</C>", source_xml, flags=re.S | re.I):
            block = match.group(0)
            if not re.search(r"<Expand\b[^>]*\bdir=\"1\"", block, flags=re.S | re.I):
                continue
            if "t=\"DSColumn\"" not in block:
                continue
            dataset = self._regex_first(block, r'\bdsName="([^"]+)"')
            field = self._regex_first(block, r'\bcolumnName="([^"]+)"')
            if dataset and field:
                return {"dataset": dataset, "field": field, "cellXml": self._compact(block, 4000)}
        return None

    def _find_table_data_query(self, source_xml: str, dataset_name: str) -> dict[str, str] | None:
        match = re.search(
            rf"<TableData\b(?=[^>]*\bname=\"{re.escape(dataset_name)}\")[^>]*>.*?</TableData>",
            source_xml,
            flags=re.S | re.I,
        )
        if not match:
            return None
        query_match = re.search(r"<Query\b[^>]*>\s*<!\[CDATA\[(.*?)]]>\s*</Query>", match.group(0), flags=re.S | re.I)
        if not query_match:
            return None
        return {"dataset": dataset_name, "query": query_match.group(1).strip(), "rawXml": match.group(0)}

    def _rewrite_query_order_by_labels(self, query: str, *, field_name: str, labels: list[str]) -> str | None:
        query_text = str(query or "").strip().rstrip(";")
        order_match = list(re.finditer(r"\bORDER\s+BY\b", query_text, flags=re.I))
        if not order_match:
            return None
        last_order = order_match[-1]
        order_body = query_text[last_order.end() :].strip()
        if not order_body:
            return None
        order_items = self._split_top_level_sql_list(order_body)
        first_item = order_items[0].strip() if order_items else field_name
        field_expr = self._infer_order_field_expression(query_text, field_name, first_item)
        order_literal = "," + ",".join(label.replace("'", "''").replace(",", "，") for label in labels) + ","
        position_expression = f"CHARINDEX(',' + CAST({field_expr} AS NVARCHAR(4000)) + ',', '{order_literal}')"
        order_expression = f"CASE WHEN {position_expression} > 0 THEN {position_expression} ELSE 999999 END"
        rest_items = [item.strip() for item in order_items[1:] if item.strip()]
        rest_sql = ""
        if rest_items:
            rest_sql = ",\n         " + ",\n         ".join(rest_items)
        elif field_expr:
            rest_sql = f",\n         {field_expr}"
        next_order = f"ORDER BY {order_expression}" + rest_sql
        return f"{query_text[: last_order.start()].rstrip()}\n{next_order};"

    def _infer_order_field_expression(self, query_text: str, field_name: str, first_order_item: str) -> str:
        first_item = str(first_order_item or "").strip()
        simple_case_match = re.search(r"\bCASE\s+(.+?)\s+WHEN\b", first_item, flags=re.S | re.I)
        if simple_case_match:
            candidate = simple_case_match.group(1).strip()
            if not candidate.upper().startswith("WHEN") and re.search(rf"\b{re.escape(field_name)}\b", candidate, flags=re.I):
                return candidate
        searched_case_match = re.search(r"\bCASE\s+WHEN\s+(.+?)\s*=", first_item, flags=re.S | re.I)
        if searched_case_match:
            candidate = searched_case_match.group(1).strip()
            if re.search(rf"\b{re.escape(field_name)}\b", candidate, flags=re.I):
                return candidate
        searched = first_item if "case" not in first_item.lower() else query_text
        direct_match = re.search(
            rf"\b(?:[A-Za-z_][A-Za-z0-9_]*\.)?(?:\[{re.escape(field_name)}\]|{re.escape(field_name)})\b",
            searched,
            flags=re.I,
        )
        if direct_match:
            return direct_match.group(0)
        query_match = re.search(
            rf"\b(?:[A-Za-z_][A-Za-z0-9_]*\.)?(?:\[{re.escape(field_name)}\]|{re.escape(field_name)})\b",
            query_text,
            flags=re.I,
        )
        return query_match.group(0) if query_match else field_name

    def _split_top_level_sql_list(self, text: str) -> list[str]:
        items: list[str] = []
        start = 0
        depth = 0
        in_single_quote = False
        index = 0
        while index < len(text):
            char = text[index]
            if char == "'":
                if in_single_quote and index + 1 < len(text) and text[index + 1] == "'":
                    index += 2
                    continue
                in_single_quote = not in_single_quote
            elif not in_single_quote:
                if char == "(":
                    depth += 1
                elif char == ")" and depth > 0:
                    depth -= 1
                elif char == "," and depth == 0:
                    items.append(text[start:index])
                    start = index + 1
            index += 1
        tail = text[start:]
        if tail.strip():
            items.append(tail)
        return items

    async def _force_writable_result(
        self,
        *,
        source_xml: str,
        base_payload: dict[str, Any],
        observations: list[dict[str, Any]],
        last_result: dict[str, Any],
        langfuse_trace_context: dict[str, str] | None,
        conversation_id: str | None,
    ) -> dict[str, Any] | None:
        final_payload = {
            **base_payload,
            "fullCptXml": self._compact(source_xml, 180000),
            "observations": observations[-12:],
            "lastResult": last_result,
            "instruction": (
                "观察阶段结束。禁止再返回 toolCalls，必须基于已有事实返回可应用修改。"
                "优先返回 file_edit 精确替换；如果 exact edit 难以稳定表达，再返回 finalCptXml 完整 WorkBook。"
            ),
            "expectedJson": self._react_expected_json(),
        }
        try:
            result = await asyncio.wait_for(
                fr_report_ai_operation_service._invoke_json(
                    system_prompt=self._react_system_prompt(),
                    payload=final_payload,
                    agent_name="FrReportHighAuthorityFinalReviewer",
                    langfuse_trace_context=langfuse_trace_context,
                    langfuse_run_name="fr_report_final_review",
                    langfuse_metadata={"conversation_id": conversation_id, "mode": "finalizer"},
                ),
                timeout=self.REACT_FINALIZER_TIMEOUT_SECONDS,
            )
            operations = self._normalize_operations(result)
            if not operations and not str(result.get("finalCptXml") or "").strip():
                return None
            candidate_xml = self._build_candidate_xml(source_xml, result, operations)
            fr_report_ai_operation_service._validate_full_cpt_xml(candidate_xml)
            return {
                "modelResult": result,
                "assistantMessage": str(result.get("assistantMessage") or "我把观察结果收束成一版可写入修改。"),
                "candidateXml": candidate_xml,
                "operations": operations,
            }
        except asyncio.TimeoutError:
            logger.warning("FineReport 工作循环最终成稿超时")
            return None
        except Exception as exc:
            logger.warning(f"FineReport 工作循环最终成稿失败: {exc}")
            return None

    def _trace_context_from_observation(self, observation: Any) -> dict[str, str] | None:
        trace_id = getattr(observation, "trace_id", None)
        if not trace_id:
            return None
        trace_context = {"trace_id": str(trace_id)}
        observation_id = getattr(observation, "id", None)
        if observation_id:
            trace_context["parent_span_id"] = str(observation_id)
        return trace_context

    def _react_expected_json(self) -> dict[str, Any]:
        return {
            "assistantMessage": "自然语言进度，简短中文",
            "toolCalls": [
                {
                    "toolName": "read_cpt_slice",
                    "reason": "为什么要调用",
                    "arguments": {"selectors": ["cell:B5", "TableData[name=\"ds1\"]"]},
                }
            ],
            "operations": [
                {
                    "operationType": "file_edit",
                    "summary": "CPT 文件修改范围",
                    "riskLevel": "low|medium|high",
                    "payload": {
                        "edits": [
                            {
                                "oldText": "当前 CPT 中真实存在且尽量唯一的完整 XML 原文片段",
                                "newText": "替换后的完整 XML 片段",
                                "replaceAll": False,
                            }
                        ]
                    },
                }
            ],
            "finalCptXml": "可选；只有 file_edit 难以稳定表达时才返回完整 WorkBook XML",
            "warnings": [],
            "validationFocus": [],
        }

    def _normalize_tool_calls(self, result: dict[str, Any]) -> list[dict[str, Any]]:
        raw_calls = result.get("toolCalls") or result.get("tools") or result.get("actions")
        if not isinstance(raw_calls, list):
            return []
        calls: list[dict[str, Any]] = []
        allowed = {item["name"] for item in self._react_available_tools()}
        for item in raw_calls[:8]:
            if not isinstance(item, dict):
                continue
            tool_name = str(item.get("toolName") or item.get("name") or item.get("tool") or "").strip()
            if tool_name not in allowed:
                continue
            arguments = item.get("arguments") if isinstance(item.get("arguments"), dict) else item.get("args")
            calls.append(
                {
                    "toolName": tool_name,
                    "reason": str(item.get("reason") or item.get("summary") or ""),
                    "arguments": arguments if isinstance(arguments, dict) else {},
                }
            )
        return calls

    def _filter_redundant_tool_calls(
        self,
        tool_calls: list[dict[str, Any]],
        observations: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        filtered: list[dict[str, Any]] = []
        for tool_call in tool_calls:
            tool_name = str(tool_call.get("toolName") or "").strip()
            arguments = tool_call.get("arguments") if isinstance(tool_call.get("arguments"), dict) else {}
            if self._is_redundant_tool_call(tool_name, arguments, observations):
                observations.append(
                    {
                        "toolName": "tool_loop_guard",
                        "status": "skipped_duplicate_tool",
                        "payload": {
                            "skippedTool": tool_name,
                            "arguments": arguments,
                            "hint": "这类证据已经读取过；不要继续重复调用，基于现有观察生成候选修改或换更具体的片段/错误验证。",
                        },
                    }
                )
                continue
            filtered.append(tool_call)
        return filtered

    def _is_redundant_tool_call(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        observations: list[dict[str, Any]],
    ) -> bool:
        successful = [item for item in observations if item.get("status") == "success"]
        if tool_name == "read_cpt_full":
            return any(item.get("toolName") == "read_cpt_full" for item in successful)
        if tool_name == "search_reference_cpt":
            return sum(1 for item in successful if item.get("toolName") == "search_reference_cpt") >= 2
        signature = self._tool_call_signature(tool_name, arguments)
        return any(item.get("toolCallSignature") == signature for item in successful)

    def _tool_call_signature(self, tool_name: str, arguments: dict[str, Any]) -> str:
        return f"{tool_name}:{json.dumps(arguments or {}, ensure_ascii=False, sort_keys=True, default=str)}"

    def _needs_evidence_before_accepting(
        self,
        base_payload: dict[str, Any],
        result: dict[str, Any],
        operations: list[dict[str, Any]],
        observations: list[dict[str, Any]],
    ) -> bool:
        is_modification_result = bool(result.get("finalCptXml") or operations)
        has_case_observation = any(
            item.get("toolName") in {"search_reference_cpt", "read_reference_cpt_case", "read_reference_report_full"}
            for item in observations
        )
        if is_modification_result and not has_case_observation:
            return True
        if observations:
            sensitive = self._evidence_sensitive_request(base_payload, result, operations)
            if sensitive and not has_case_observation:
                return True
            concrete_tools = {
                "read_cpt_full",
                "read_cpt_slice",
                "search_xml",
                "inspect_report_layout",
                "search_fr_setting_knowledge",
                "search_reference_cpt",
                "read_reference_cpt_case",
                "read_reference_report_full",
            }
            if any(item.get("status") == "success" and item.get("toolName") in concrete_tools for item in observations):
                return False
        if result.get("finalCptXml"):
            return True
        return self._evidence_sensitive_request(base_payload, result, operations)

    def _evidence_sensitive_request(
        self,
        base_payload: dict[str, Any],
        result: dict[str, Any],
        operations: list[dict[str, Any]],
    ) -> bool:
        selectors = " ".join(self._operation_selectors(operations))
        summaries = " ".join(str(item.get("summary") or "") for item in operations)
        request = str(base_payload.get("userRequest") or "")
        assistant_message = str(result.get("assistantMessage") or "")
        evidence_sensitive_text = f"{request}\n{summaries}\n{selectors}"
        return bool(
            re.search(
                r"隐藏|显示|列|行|格式|日期|下拉|字典|控件|参数|填报|脚本|联动|样式|边框|合并|扩展|ReportPageAttr|HC|HR|DateFormat|Widget|Parameter|Style|ReportWrite",
                f"{evidence_sensitive_text}\n{assistant_message}",
                flags=re.I,
            )
        )

    async def _collect_preflight_evidence(
        self,
        *,
        source_xml: str,
        base_payload: dict[str, Any],
        result: dict[str, Any],
        operations: list[dict[str, Any]],
        observations: list[dict[str, Any]],
        database_source_context: dict[str, Any],
        attachment_context: list[dict[str, Any]],
        db: AsyncSession | None,
        user_id: int | None = None,
    ) -> AsyncIterator[tuple[str, dict[str, Any]]]:
        evidence_calls = self._preflight_evidence_tool_calls(base_payload, result, operations)
        for tool_call in evidence_calls:
            tool_name = tool_call["toolName"]
            yield self._tool_started(tool_name, tool_call["reason"])
            event_name, event_payload, observation = await self._execute_react_tool(
                tool_name=tool_name,
                arguments=tool_call["arguments"],
                source_xml=source_xml,
                database_source_context=database_source_context,
                attachment_context=attachment_context,
                loop_state={},
                db=db,
                user_id=user_id,
            )
            yield event_name, event_payload
            observations.append(observation)

    def _preflight_evidence_tool_calls(
        self,
        base_payload: dict[str, Any],
        result: dict[str, Any],
        operations: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        selectors = self._preflight_selectors(base_payload, operations)
        request = str(base_payload.get("userRequest") or "")
        assistant_message = str(result.get("assistantMessage") or "")
        query = " ".join(item for item in [request, assistant_message] if item).strip()
        calls: list[dict[str, Any]] = [
            {
                "toolName": "read_cpt_slice",
                "reason": "读取本次修改会碰到的当前 CPT 原始片段，避免凭印象写错节点。",
                "arguments": {"selectors": selectors},
            },
            {
                "toolName": "search_reference_cpt",
                "reason": "检索相似报表案例，确认 FineReport 原生写法。",
                "arguments": {"query": query or "FineReport CPT 修改参考写法", "limit": 4},
            },
        ]
        if self._setting_knowledge_sensitive_request(request, operations):
            calls.insert(
                1,
                {
                    "toolName": "search_fr_setting_knowledge",
                    "reason": "查 FineReport 属性面板到 CPT 节点的受控参考，避免把展示格式、扩展、控件或样式都误改成 SQL。",
                    "arguments": {"query": query or request, "limit": 5},
                },
            )
        return calls

    def _setting_knowledge_sensitive_request(self, request: str, operations: list[dict[str, Any]]) -> bool:
        selectors = " ".join(self._operation_selectors(operations))
        summaries = " ".join(str(item.get("summary") or "") for item in operations)
        text = f"{request}\n{selectors}\n{summaries}"
        return bool(
            re.search(
                r"格式|数字|日期|时间|百分比|货币|小数|取整|扩展|父格|分组|排序|过滤|样式|字体|边框|背景|对齐|"
                r"形态|条形码|金额线|打印|导出|分页|悬浮|图片|图表|控件|下拉|校验|条件属性|高亮|超级链接|跳转|填报|写回|提交",
                text,
                flags=re.I,
            )
        )

    def _writeback_impact_sensitive_request(self, request: str, operations: list[dict[str, Any]]) -> bool:
        selectors = " ".join(self._operation_selectors(operations))
        summaries = " ".join(str(item.get("summary") or "") for item in operations)
        text = f"{request}\n{selectors}\n{summaries}"
        return bool(
            re.search(
                r"填报|写回|提交|策略|主键|日期|时间|格式|隐藏|显示|列|行|控件|校验|公式|CONCATENATE|ReportWrite",
                text,
                flags=re.I,
            )
        )

    def _preflight_selectors(self, base_payload: dict[str, Any], operations: list[dict[str, Any]]) -> list[str]:
        selectors: list[str] = ["ReportPageAttr"]
        selected_cell = str(base_payload.get("selectedCell") or "").strip()
        if selected_cell:
            selectors.append(f"cell:{selected_cell}" if not selected_cell.startswith("cell:") else selected_cell)
        selectors.extend(self._operation_selectors(operations))
        request = str(base_payload.get("userRequest") or "")
        if self._writeback_impact_sensitive_request(request, operations):
            selectors.append("ReportWriteAttr")
        for address in re.findall(r"\b[A-Z]{1,3}\d+\b", request):
            selectors.append(f"cell:{address}")
        result: list[str] = []
        for selector in selectors:
            value = str(selector or "").strip()
            if value and value not in result:
                result.append(value)
        return result[:12]

    def _operation_selectors(self, operations: list[dict[str, Any]]) -> list[str]:
        selectors: list[str] = []
        for operation in operations:
            payload = operation.get("payload") if isinstance(operation.get("payload"), dict) else {}
            patches = payload.get("patches") if isinstance(payload.get("patches"), list) else []
            for patch in patches:
                if isinstance(patch, dict) and patch.get("selector"):
                    selectors.append(str(patch.get("selector")))
            if payload.get("selector"):
                selectors.append(str(payload.get("selector")))
            if operation.get("target"):
                selectors.append(str(operation.get("target")))
        return selectors[:20]

    def _canonicalize_operations_for_current_cpt(
        self,
        source_xml: str,
        base_payload: dict[str, Any],
        operations: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return [
            operation
            for operation in operations
            if str(operation.get("operationType") or "") in {"file_edit", "write_cpt_full"}
        ]

    def _hidden_report_page_xml(self, source_xml: str, hidden_ranges: list[tuple[int, int]]) -> str | None:
        report_page_match = re.search(r"<ReportPageAttr\b[^>]*(?:/>|>.*?</ReportPageAttr>)", source_xml, flags=re.S | re.I)
        if not report_page_match:
            return None
        report_page_xml = report_page_match.group(0)
        next_report_page_xml = re.sub(r"\s*<HC\b[^>]*/>", "", report_page_xml, flags=re.S | re.I)
        hidden_xml = "\n".join(f'<HC F="{start}" T="{end}"/>' for start, end in hidden_ranges)
        if "<FR" in next_report_page_xml:
            next_report_page_xml = re.sub(r"(<FR\b[^>]*/>)", rf"\1\n{hidden_xml}", next_report_page_xml, count=1, flags=re.S | re.I)
        else:
            next_report_page_xml = re.sub(r"(<ReportPageAttr\b[^>]*>)", rf"\1\n{hidden_xml}", next_report_page_xml, count=1, flags=re.S | re.I)
        return next_report_page_xml

    def _hidden_column_width_xml(self, source_xml: str, hidden_ranges: list[tuple[int, int]]) -> str | None:
        match = re.search(r"<ColumnWidth\b[^>]*>.*?</ColumnWidth>", source_xml, flags=re.S | re.I)
        if not match:
            return None
        original_xml = match.group(0)
        cdata_match = re.search(r"<!\[CDATA\[(.*?)]]>", original_xml, flags=re.S)
        if not cdata_match:
            return None
        values = [item.strip() for item in cdata_match.group(1).split(",")]
        if not values:
            return None
        changed = False
        for start, end in hidden_ranges:
            for index in range(max(0, start), min(len(values), end + 1)):
                if values[index] != "0":
                    values[index] = "0"
                    changed = True
        if not changed:
            return original_xml
        next_cdata = ",".join(values)
        return original_xml[: cdata_match.start(1)] + next_cdata + original_xml[cdata_match.end(1) :]

    def _column_width_adjustments_from_xml(self, column_width_xml: str) -> dict[int, int]:
        cdata_match = re.search(r"<!\[CDATA\[(.*?)]]>", column_width_xml, flags=re.S)
        if not cdata_match:
            return {}
        result: dict[int, int] = {}
        for index, raw in enumerate(cdata_match.group(1).split(",")):
            try:
                result[index] = max(0, int(raw.strip()))
            except ValueError:
                continue
        return result

    def _presentation_column_width_adjustments(self, source_xml: str, request: str, operations: list[dict[str, Any]]) -> dict[int, int]:
        adjustments: dict[int, int] = {}
        for selector in self._presentation_affected_cell_selectors(source_xml, request, operations):
            match = re.fullmatch(r"cell:([A-Z]{1,3})(\d+)", selector, flags=re.I)
            if not match:
                continue
            column_index = self._column_index(match.group(1)) - 1
            if column_index < 0:
                continue
            cell_xml = self._patched_cell_xml_for_selector(selector, operations) or self._cell_xml_by_selector(source_xml, selector)
            width = self._estimated_column_width_for_display(cell_xml, request)
            if width:
                adjustments[column_index] = max(adjustments.get(column_index, 0), width)
        return adjustments

    def _presentation_affected_cell_selectors(self, source_xml: str, request: str, operations: list[dict[str, Any]]) -> list[str]:
        selectors: list[str] = []
        selectors.extend(self._requested_date_cell_selectors(source_xml, request))
        selectors.extend(self._patched_cell_selectors(operations))
        for address in re.findall(r"\b[A-Z]{1,3}\d+\b", request, flags=re.I):
            selectors.append(f"cell:{address.upper()}")
        result: list[str] = []
        for selector in selectors:
            if selector and selector not in result:
                result.append(selector)
        return result[:24]

    def _patched_cell_xml_for_selector(self, selector: str, operations: list[dict[str, Any]]) -> str | None:
        for patch in self._iter_legacy_fragments(operations):
            patch_selector = str(patch.get("selector") or patch.get("target") or "")
            if patch_selector.lower() == selector.lower():
                new_xml = str(patch.get("newXml") or patch.get("xml") or "").strip()
                if new_xml:
                    return new_xml
        return None

    def _cell_xml_by_selector(self, source_xml: str, selector: str) -> str:
        try:
            start, end = self._find_xml_target(source_xml, selector)
        except Exception:
            return ""
        return source_xml[start:end]

    def _estimated_column_width_for_display(self, cell_xml: str, request: str) -> int | None:
        combined = f"{request}\n{cell_xml}"
        if re.search(r"yyyy年MM月dd日|yyyy-MM-dd|DateAttr|日期格式|完整日期", combined, flags=re.I):
            return 4572000
        texts: list[str] = []
        texts.extend(re.findall(r"<!\[CDATA\[(.*?)]]>", cell_xml, flags=re.S))
        texts.extend(re.findall(r"\b(?:columnName|name)=\"([^\"]+)\"", cell_xml, flags=re.I))
        visible_text = " ".join(text.strip() for text in texts if text and len(text.strip()) <= 80)
        if not visible_text:
            return None
        display_len = sum(2 if "\u4e00" <= ch <= "\u9fff" else 1 for ch in visible_text)
        if display_len <= 10:
            return None
        return min(9144000, max(2743200, display_len * 285750))

    def _adjusted_column_width_xml(self, source_xml: str, adjustments: dict[int, int]) -> str | None:
        if not adjustments:
            return None
        match = re.search(r"<ColumnWidth\b[^>]*>.*?</ColumnWidth>", source_xml, flags=re.S | re.I)
        if not match:
            return None
        original_xml = match.group(0)
        cdata_match = re.search(r"<!\[CDATA\[(.*?)]]>", original_xml, flags=re.S)
        if not cdata_match:
            return None
        values = [item.strip() for item in cdata_match.group(1).split(",")]
        if not values:
            return None
        changed = False
        for index, width in adjustments.items():
            if index < 0:
                continue
            while index >= len(values):
                values.append(values[-1] if values else "2743200")
            next_width = str(max(0, int(width)))
            if values[index] != next_width:
                values[index] = next_width
                changed = True
        if not changed:
            return None
        next_cdata = ",".join(values)
        return original_xml[: cdata_match.start(1)] + next_cdata + original_xml[cdata_match.end(1) :]

    def _remove_column_width_patch(self, operations: list[dict[str, Any]]) -> list[dict[str, Any]]:
        cleaned_operations: list[dict[str, Any]] = []
        for operation in operations:
            payload = operation.get("payload") if isinstance(operation.get("payload"), dict) else {}
            patches = payload.get("patches") if isinstance(payload.get("patches"), list) else []
            kept_patches = [
                patch
                for patch in patches
                if not (isinstance(patch, dict) and str(patch.get("selector") or patch.get("target") or "").strip().lower() == "columnwidth")
            ]
            if patches and not kept_patches:
                continue
            if patches and len(kept_patches) != len(patches):
                next_operation = dict(operation)
                next_payload = dict(payload)
                next_payload["patches"] = kept_patches
                next_operation["payload"] = next_payload
                cleaned_operations.append(next_operation)
            else:
                cleaned_operations.append(operation)
        return cleaned_operations

    def _normalize_operation_summaries(self, operations: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for operation in operations:
            next_operation = dict(operation)
            patches = self._iter_legacy_fragments([next_operation])
            selectors = [str(patch.get("selector") or patch.get("target") or "") for patch in patches]
            new_xml = "\n".join(str(patch.get("newXml") or patch.get("xml") or "") for patch in patches)
            if selectors and all(fr_report_ai_operation_service._selector_cell_coordinates(selector) for selector in selectors):
                if "DateAttr" in new_xml or "format=" in new_xml:
                    next_operation["summary"] = f"设置 {', '.join(selectors).replace('cell:', '')} 单元格日期显示格式"
            normalized.append(next_operation)
        return normalized

    def _date_format_source_sql_operations(
        self,
        source_xml: str,
        base_payload: dict[str, Any],
        operations: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return []

    def _date_writeback_formula_operations(self, source_xml: str, base_payload: dict[str, Any]) -> list[dict[str, Any]]:
        return []

    def _unit_text_operations(self, source_xml: str, base_payload: dict[str, Any]) -> list[dict[str, Any]]:
        return []

    def _change_color_condition_operations(
        self,
        source_xml: str,
        base_payload: dict[str, Any],
        operations: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return []

    def _writeback_attr_operations(
        self,
        source_xml: str,
        base_payload: dict[str, Any],
        operations: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return []

    def _find_change_metric_cell(self, source_xml: str) -> tuple[str, str] | None:
        cells = list(re.finditer(r"<C\b[^>]*>.*?</C>", source_xml, flags=re.S | re.I))
        header_positions: set[tuple[int, int]] = set()
        for cell_match in cells:
            cell_xml = cell_match.group(0)
            text = self._regex_first(cell_xml, r"<!\[CDATA\[(.*?)]]>") or ""
            if re.search(r"日环比|环比|涨跌|增减", text):
                column = int(self._regex_first(cell_xml, r'\bc="(\d+)"') or "-1")
                row = int(self._regex_first(cell_xml, r'\br="(\d+)"') or "-1")
                if column >= 0 and row >= 0:
                    header_positions.add((column, row))
        for cell_match in cells:
            cell_xml = cell_match.group(0)
            field = self._regex_first(cell_xml, r'\bcolumnName="([^"]+)"') or ""
            if not re.search(r"circle|rate|change|rise|fall|delta|diff|环比|涨跌|增减", field, flags=re.I):
                continue
            column = int(self._regex_first(cell_xml, r'\bc="(\d+)"') or "-1")
            row = int(self._regex_first(cell_xml, r'\br="(\d+)"') or "-1")
            if any(abs(column - header_column) <= 1 and abs(row - header_row) <= 1 for header_column, header_row in header_positions) or not header_positions:
                return f"cell:{self._column_label(column + 1)}{row + 1}", cell_xml
        return None

    def _build_writeback_attr_from_layout(self, source_xml: str) -> str | None:
        table_info = self._primary_query_table_info(source_xml)
        if not table_info:
            return None
        schema, table_name = table_info
        field_cells = self._dataset_field_cells(source_xml)
        region = self._first_field_cell(field_cells, ["region", "market", "area", "地区", "区域", "市场"])
        date_cell = self._first_field_cell(field_cells, ["month_day", "date", "zdata", "record_date", "日期"])
        value_cell = self._first_field_cell(field_cells, ["volume", "price", "daily_volume", "qty", "amount", "出栏", "数量"])
        remark_cell = self._first_field_cell(field_cells, ["remark", "note", "备注"])
        if not region or not date_cell or not value_cell:
            return None
        date_formula = self._writeback_date_formula(date_cell["address"])
        value_column = value_cell["field"]
        database_name = self._primary_database_name(source_xml)
        xml = [
            "<ReportWriteAttr>",
            '<SubmitVisitor class="com.fr.report.write.BuiltInSQLSubmiter">',
            "<Name>\n<![CDATA[内置SQL1]]></Name>",
            f'<Attributes dsName="{escape(database_name)}"/>',
            '<DMLConfig class="com.fr.write.config.IntelliDMLConfig">',
            f'<Table schema="{schema}" name="{table_name}"/>',
            f'<ColumnConfig name="{region["field"]}" isKey="true" skipUnmodified="false">',
            f'<ColumnRow column="{region["column"]}" row="{region["row"]}"/>',
            "</ColumnConfig>",
            f'<ColumnConfig name="{value_column}" isKey="false" skipUnmodified="false">',
            f'<ColumnRow column="{value_cell["column"]}" row="{value_cell["row"]}"/>',
            "</ColumnConfig>",
            '<ColumnConfig name="date" isKey="true" skipUnmodified="false">',
            '<O t="XMLable" class="com.fr.base.Formula">',
            "<Attributes>",
            f"<![CDATA[{date_formula}]]>",
            "</Attributes>",
            "</O>",
            "</ColumnConfig>",
            "</DMLConfig>",
            "</SubmitVisitor>",
        ]
        if remark_cell:
            xml.extend(
                [
                    '<SubmitVisitor class="com.fr.report.write.BuiltInSQLSubmiter">',
                    "<Name>\n<![CDATA[CopyOf内置SQL1]]></Name>",
                    f'<Attributes dsName="{escape(database_name)}"/>',
                    '<DMLConfig class="com.fr.write.config.IntelliDMLConfig">',
                    f'<Table schema="{schema}" name="{table_name}"/>',
                    f'<ColumnConfig name="{remark_cell["field"]}" isKey="false" skipUnmodified="false">',
                    f'<ColumnRow column="{remark_cell["column"]}" row="{remark_cell["row"]}"/>',
                    "</ColumnConfig>",
                    '<ColumnConfig name="date" isKey="true" skipUnmodified="false">',
                    '<O t="XMLable" class="com.fr.base.Formula">',
                    "<Attributes>",
                    f"<![CDATA[{date_formula}]]>",
                    "</Attributes>",
                    "</O>",
                    "</ColumnConfig>",
                    "</DMLConfig>",
                    "</SubmitVisitor>",
                ]
            )
        xml.append("</ReportWriteAttr>")
        return "\n".join(xml)

    def _primary_database_name(self, source_xml: str) -> str:
        for pattern in (
            r"<DatabaseName>\s*<!\[CDATA\[(.*?)]]>\s*</DatabaseName>",
            r'<Attributes\s+dsName="([^"]+)"',
        ):
            match = re.search(pattern, source_xml, flags=re.S | re.I)
            if match and match.group(1).strip():
                return match.group(1).strip()
        return settings.FR_AI_FINEREPORT_DB_NAME

    def _primary_query_table_info(self, source_xml: str) -> tuple[str, str] | None:
        query_match = re.search(r"<Query\b[^>]*>\s*<!\[CDATA\[(.*?)]]>\s*</Query>", source_xml, flags=re.S | re.I)
        if not query_match:
            return None
        query_sql = query_match.group(1)
        for match in re.finditer(r"\bFROM\s+(?:(?P<schema>\[[^\]]+]|\w+)\.)?(?P<table>\[[^\]]+]|\w+)", query_sql, flags=re.I):
            table = match.group("table").strip("[]")
            schema = (match.group("schema") or "dbo").strip("[]")
            if table.lower() in {"datas", "daily_data", "circle_rate_datas", "latest_rise", "volume_rank"}:
                continue
            return schema, table
        return None

    def _dataset_field_cells(self, source_xml: str) -> list[dict[str, Any]]:
        cells: list[dict[str, Any]] = []
        for cell_match in re.finditer(r"<C\b[^>]*>.*?</C>", source_xml, flags=re.S | re.I):
            cell_xml = cell_match.group(0)
            field = self._regex_first(cell_xml, r'\bcolumnName="([^"]+)"') or ""
            if not field:
                continue
            column = int(self._regex_first(cell_xml, r'\bc="(\d+)"') or "0")
            row = int(self._regex_first(cell_xml, r'\br="(\d+)"') or "0")
            cells.append({"field": field, "column": column, "row": row, "address": f"{self._column_label(column + 1)}{row + 1}", "xml": cell_xml})
        return cells

    def _first_field_cell(self, cells: list[dict[str, Any]], keywords: list[str]) -> dict[str, Any] | None:
        lowered_keywords = [item.lower() for item in keywords]
        for cell in cells:
            field = str(cell.get("field") or "")
            lowered = field.lower()
            if any(keyword in lowered or keyword in field for keyword in lowered_keywords):
                return cell
        return None

    def _writeback_date_formula(self, date_cell: str) -> str:
        return f'=FORMAT(TODATE(REPLACE(REPLACE(REPLACE({date_cell},"年","-"),"月","-"),"日","")),"yyyy-MM-dd")'

    def _normalize_writeback_after_presentation_change(
        self,
        *,
        source_xml: str,
        candidate_xml: str,
        request: str,
    ) -> tuple[str, list[str]]:
        desired_format = self._requested_date_format(request)
        if not desired_format or "年" not in desired_format:
            return candidate_xml, []
        cell_refs = self._requested_date_cell_selectors(candidate_xml, request) or self._requested_date_cell_selectors(source_xml, request)
        if not cell_refs:
            return candidate_xml, []
        report_write_match = re.search(r"<ReportWriteAttr\b[^>]*(?:/>|>.*?</ReportWriteAttr>)", candidate_xml, flags=re.S | re.I)
        if not report_write_match:
            return candidate_xml, []
        report_write_xml = report_write_match.group(0)
        next_report_write_xml, changed_refs = self._normalize_date_concat_formulas_in_writeback(report_write_xml, cell_refs)
        if next_report_write_xml == report_write_xml:
            return candidate_xml, []
        next_xml = candidate_xml[: report_write_match.start()] + next_report_write_xml + candidate_xml[report_write_match.end() :]
        refs_text = "、".join(changed_refs)
        return next_xml, [f"已同步填报写回策略：{refs_text} 已是完整日期，ReportWriteAttr 中旧的年份+日期拼接公式已改为直接引用日期单元格。"]

    def _normalize_date_concat_formulas_in_writeback(self, report_write_xml: str, cell_refs: list[str]) -> tuple[str, list[str]]:
        next_xml = report_write_xml
        changed_refs: list[str] = []
        for selector in cell_refs:
            match = re.fullmatch(r"cell:([A-Z]{1,3})(\d+)", selector, flags=re.I)
            if not match:
                continue
            date_cell = f"{match.group(1).upper()}{match.group(2)}"
            previous_column = self._column_label(self._column_index(match.group(1)) - 1)
            if not previous_column:
                continue
            previous_cell = f"{previous_column}{match.group(2)}"
            patterns = [
                rf"CONCATENATE\s*\(\s*{re.escape(previous_cell)}\s*,\s*{re.escape(date_cell)}\s*\)",
                rf"CONCAT\s*\(\s*{re.escape(previous_cell)}\s*,\s*{re.escape(date_cell)}\s*\)",
                rf"{re.escape(previous_cell)}\s*&\s*{re.escape(date_cell)}",
                rf"{re.escape(previous_cell)}\s*\+\s*{re.escape(date_cell)}",
            ]
            for pattern in patterns:
                next_xml, count = re.subn(pattern, date_cell, next_xml, flags=re.I)
                if count and date_cell not in changed_refs:
                    changed_refs.append(date_cell)
        return next_xml, changed_refs

    def _format_dataset_date_column_sql(self, query_sql: str, column_name: str, desired_format: str) -> tuple[str, int]:
        sql_format = self._sqlserver_date_format(desired_format)
        format_pattern = re.compile(
            rf"FORMAT\s*\(\s*CAST\s*\(\s*(?P<source>[A-Za-z_][\w.]*)\s+AS\s+DATE\s*\)\s*,\s*'[^']+'\s*\)\s+AS\s+{re.escape(column_name)}\b",
            flags=re.S | re.I,
        )
        next_sql, count = format_pattern.subn(rf"FORMAT(CAST(\g<source> AS DATE), '{sql_format}') AS {column_name}", query_sql, count=1)
        if count:
            return next_sql, count
        cast_pattern = re.compile(
            rf"CAST\s*\(\s*(?P<source>[A-Za-z_][\w.]*)\s+AS\s+DATE\s*\)\s+AS\s+{re.escape(column_name)}\b",
            flags=re.S | re.I,
        )
        next_sql, count = cast_pattern.subn(rf"FORMAT(CAST(\g<source> AS DATE), '{sql_format}') AS {column_name}", query_sql, count=1)
        return next_sql, count

    def _sqlserver_date_format(self, desired_format: str) -> str:
        normalized = str(desired_format or "").strip()
        if "年" in normalized:
            return "yyyy年MM月dd日"
        if "-" in normalized:
            return "yyyy-MM-dd"
        return normalized or "yyyy-MM-dd"

    def _date_format_gap_observation(
        self,
        source_xml: str,
        base_payload: dict[str, Any],
        operations: list[dict[str, Any]],
        observations: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        if any(item.get("toolName") == "date_format_semantic_guard" for item in observations):
            return None
        request = str(base_payload.get("userRequest") or "")
        desired_format = self._requested_date_format(request)
        if not desired_format or "yyyy" not in desired_format:
            return None
        if any("TableData" in selector or "Query" in selector for selector in self._operation_selectors(operations)):
            return None
        patched_cells = self._requested_date_cell_selectors(source_xml, request) + self._patched_cell_selectors(operations)
        if not patched_cells:
            return None
        dataset_selectors: list[str] = []
        findings: list[dict[str, Any]] = []
        for selector in patched_cells:
            try:
                start, end = self._find_xml_target(source_xml, selector)
            except Exception:
                continue
            cell_xml = source_xml[start:end]
            dataset_name = self._regex_first(cell_xml, r'\bdsName="([^"]+)"')
            column_name = self._regex_first(cell_xml, r'\bcolumnName="([^"]+)"')
            if not dataset_name or not column_name:
                continue
            table_match = re.search(
                rf"<TableData\b(?=[^>]*\bname=\"{re.escape(dataset_name)}\")[^>]*>.*?</TableData>",
                source_xml,
                flags=re.S | re.I,
            )
            if not table_match:
                continue
            table_xml = table_match.group(0)
            if re.search(rf"FORMAT\s*\(.*?'MM月dd日'.*?\)\s+AS\s+{re.escape(column_name)}\b", table_xml, flags=re.S | re.I):
                dataset_selector = f'TableData[name="{dataset_name}"]/Query'
                if dataset_selector not in dataset_selectors:
                    dataset_selectors.append(dataset_selector)
                findings.append({"cell": selector, "dataset": dataset_name, "field": column_name})
        if not findings:
            return None
        return {
            "toolName": "date_format_semantic_guard",
            "status": "needs_more_evidence",
            "selectors": dataset_selectors,
            "payload": {"desiredFormat": desired_format, "findings": findings},
            "hint": "目标单元格绑定的是 SQL 里已经 FORMAT 成 MM月dd日 的字符串字段；只改单元格 DateAttr 不会补出年份，下一轮应修改数据集 SQL 或改绑定原始日期字段。",
        }

    def _iter_legacy_fragments(self, operations: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return []

    def _patch_touches_hidden_column(self, patch: dict[str, Any]) -> bool:
        selector = str(patch.get("selector") or patch.get("target") or "")
        new_xml = str(patch.get("newXml") or patch.get("xml") or "")
        return bool(re.search(r"\bHC\b|ReportPageAttr", f"{selector}\n{new_xml}", flags=re.I))

    def _patched_cell_selectors(self, operations: list[dict[str, Any]]) -> list[str]:
        result: list[str] = []
        for selector in self._operation_selectors(operations):
            if fr_report_ai_operation_service._selector_cell_coordinates(selector):
                result.append(selector)
        return result

    def _requested_date_format(self, request: str) -> str | None:
        match = re.search(r"(y{2,4}年M{1,2}月d{1,2}日|y{2,4}-M{1,2}-d{1,2}|yyyy年MM月dd日|yyyy-MM-dd)", request, flags=re.I)
        return match.group(1) if match else None

    def _requested_date_cell_selectors(self, source_xml: str, request: str) -> list[str]:
        column_indexes: list[int] = []
        ordinal_map = {
            "一": 1,
            "二": 2,
            "三": 3,
            "四": 4,
            "五": 5,
            "六": 6,
            "七": 7,
            "八": 8,
            "九": 9,
            "十": 10,
        }
        for match in re.finditer(r"第([一二三四五六七八九十]+|\d+)列(?:的)?日期(?:格式)?", request):
            raw = match.group(1)
            index = int(raw) if raw.isdigit() else ordinal_map.get(raw)
            if index:
                column_indexes.append(index - 1)
        for match in re.finditer(r"\b([A-Z]{1,3})列(?:的)?日期(?:格式)?", request, flags=re.I):
            column_indexes.append(self._column_index(match.group(1)) - 1)
        selectors: list[str] = []
        for column_index in sorted(set(column_indexes)):
            pattern = re.compile(rf"<C\b(?=[^>]*\bc=\"{column_index}\")(?=[^>]*\br=\"(\d+)\")[^>]*>.*?</C>", flags=re.S | re.I)
            for cell_match in pattern.finditer(source_xml):
                cell_xml = cell_match.group(0)
                field = self._regex_first(cell_xml, r'\bcolumnName="([^"]+)"') or ""
                if field and ("date" in field.lower() or "day" in field.lower() or "zdata" in field.lower() or "日期" in request):
                    row = int(cell_match.group(1)) + 1
                    selectors.append(f"cell:{self._column_label(column_index + 1)}{row}")
                    break
        return selectors[:10]

    def _requested_hidden_column_ranges(self, request: str) -> list[tuple[int, int]]:
        hidden_segments = self._positive_hidden_request_segments(request)
        if not hidden_segments:
            return []
        text = "\n".join(hidden_segments)
        columns: list[int] = []
        ordinal_map = {
            "一": 1,
            "二": 2,
            "三": 3,
            "四": 4,
            "五": 5,
            "六": 6,
            "七": 7,
            "八": 8,
            "九": 9,
            "十": 10,
        }
        for match in re.finditer(r"第([一二三四五六七八九十]+|\d+)列", text):
            raw = match.group(1)
            index = int(raw) if raw.isdigit() else ordinal_map.get(raw)
            if index:
                columns.append(index - 1)
        for match in re.finditer(r"\b([A-Z]{1,3})列\b", text, flags=re.I):
            columns.append(self._column_index(match.group(1)) - 1)
        ranges = [(column, column) for column in sorted(set(item for item in columns if item >= 0))]
        return ranges[:20]

    def _semantic_hidden_column_ranges(self, source_xml: str, request: str) -> list[tuple[int, int]]:
        hidden_segments = self._positive_hidden_request_segments(request)
        if not hidden_segments:
            return []
        hidden_text = "\n".join(hidden_segments)
        protected_text = "\n".join(self._negative_hidden_request_segments(request))
        columns: set[int] = set()
        for cell_match in re.finditer(r"<C\b[^>]*>.*?</C>", source_xml, flags=re.S | re.I):
            cell_xml = cell_match.group(0)
            text = self._regex_first(cell_xml, r"<!\[CDATA\[(.*?)]]>") or ""
            field = self._regex_first(cell_xml, r'\bcolumnName="([^"]+)"') or ""
            candidates = [item.strip() for item in (text, field) if item and item.strip()]
            if not candidates:
                continue
            if any(self._hidden_label_matches(candidate, protected_text) for candidate in candidates):
                continue
            if any(self._hidden_label_matches(candidate, hidden_text) for candidate in candidates):
                column = int(self._regex_first(cell_xml, r'\bc="(\d+)"') or "-1")
                if column >= 0:
                    columns.add(column)
        return [(column, column) for column in sorted(columns)][:20]

    def _positive_hidden_request_segments(self, request: str) -> list[str]:
        segments = re.findall(r"[^，。；;\n]*隐藏[^，。；;\n]*|[^，。；;\n]*被隐藏[^，。；;\n]*", request)
        result: list[str] = []
        for segment in segments:
            if re.search(r"不能隐藏|不要隐藏|不隐藏|无需隐藏|别隐藏|取消隐藏|不能被隐藏|不要被隐藏", segment):
                continue
            result.append(segment.strip())
        return [item for item in result if item]

    def _negative_hidden_request_segments(self, request: str) -> list[str]:
        segments = re.findall(r"[^，。；;\n]*(?:不能隐藏|不要隐藏|不隐藏|无需隐藏|别隐藏|取消隐藏|不能被隐藏|不要被隐藏)[^，。；;\n]*", request)
        return [item.strip() for item in segments if item.strip()]

    def _hidden_label_matches(self, label: str, text: str) -> bool:
        label = str(label or "").strip()
        text = str(text or "").strip()
        if not label or not text:
            return False
        normalized_label = re.sub(r"\s+", "", label).lower()
        normalized_text = re.sub(r"\s+", "", text).lower()
        if normalized_label and normalized_label in normalized_text:
            return True
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", label):
            return bool(re.search(rf"\b{re.escape(label)}\b", text, flags=re.I))
        return False

    def _column_index(self, label: str) -> int:
        value = 0
        for char in label.upper():
            if not ("A" <= char <= "Z"):
                continue
            value = value * 26 + ord(char) - 64
        return max(1, value)

    async def _execute_react_tool(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
        source_xml: str,
        database_source_context: dict[str, Any],
        attachment_context: list[dict[str, Any]],
        loop_state: dict[str, Any],
        db: AsyncSession | None = None,
        user_id: int | None = None,
    ) -> tuple[str, dict[str, Any], dict[str, Any]]:
        try:
            if tool_name == "read_cpt_full":
                payload = {
                    "summary": "完整 CPT XML 已按需载入到本轮观察。",
                    "xmlChars": len(source_xml),
                    "fullCptXml": self._compact(source_xml, 45000),
                }
                return "file_read", {"toolName": tool_name, **payload}, {"toolName": tool_name, "status": "success", "payload": payload}
            if tool_name == "read_cpt_slice":
                selectors = arguments.get("selectors") or arguments.get("selector") or []
                if isinstance(selectors, str):
                    selectors = [selectors]
                snippets = [self._read_cpt_slice(source_xml, str(selector)) for selector in list(selectors)[:12]]
                payload = {"summary": f"已读取 {len(snippets)} 个 CPT 片段。", "snippets": snippets}
                return "file_read", {"toolName": tool_name, **payload}, {"toolName": tool_name, "status": "success", "payload": payload}
            if tool_name == "search_xml":
                query = str(arguments.get("query") or arguments.get("text") or "").strip()
                payload = {"summary": f"XML 搜索完成：{query}", "query": query, "matches": self._search_xml(source_xml, query)}
                return "file_read", {"toolName": tool_name, **payload}, {"toolName": tool_name, "status": "success", "payload": payload}
            if tool_name == "inspect_report_layout":
                payload = {"summary": "报表编辑上下文已刷新。", "workbookEditingContext": self._build_workbook_editing_context(source_xml)}
                return "tool_result", {"toolName": tool_name, "summary": payload["summary"], "payload": self._compact(payload, 50000)}, {
                    "toolName": tool_name,
                    "status": "success",
                    "payload": self._compact(payload, 60000),
                }
            if tool_name == "inspect_database_schema":
                table_names = self._normalize_table_names(arguments.get("tableNames") or arguments.get("tables"))
                if table_names:
                    connection_config = await self._database_connection_config_from_context(db, user_id, arguments, database_source_context)
                    if connection_config:
                        schema, warnings, errors = await sqlserver_query_service.inspect_tables_schema_with_config(table_names, connection_config)
                    else:
                        schema, warnings, errors = await sqlserver_query_service.inspect_tables_schema(table_names)
                    payload = {"summary": "数据库表结构查询完成。", "schema": schema, "warnings": warnings, "errors": errors}
                else:
                    payload = {"summary": "使用已识别的数据库上下文。", "context": database_source_context}
                return "db_query", {"toolName": tool_name, "summary": payload["summary"], "payload": self._compact(payload, 40000)}, {
                    "toolName": tool_name,
                    "status": "success",
                    "payload": payload,
                }
            if tool_name == "query_database_sample":
                connection_config = await self._database_connection_config_from_context(db, user_id, arguments, database_source_context)
                payload = await self._query_database_sample(arguments, connection_config=connection_config)
                return "db_query", {"toolName": tool_name, "summary": payload["summary"], "payload": self._compact(payload, 30000)}, {
                    "toolName": tool_name,
                    "status": "success",
                    "payload": payload,
                }
            if tool_name in {"read_excel_context", "read_word_context"}:
                wanted_type = "excel" if tool_name == "read_excel_context" else "word"
                files = [item for item in attachment_context if item.get("type") == wanted_type]
                payload = {"summary": f"已读取 {len(files)} 个 {wanted_type} 附件上下文。", "files": self._compact(files, 50000)}
                return "tool_result", {"toolName": tool_name, "summary": payload["summary"], "payload": payload}, {
                    "toolName": tool_name,
                    "status": "success",
                    "payload": payload,
                }
            if tool_name == "search_fr_setting_knowledge":
                query = str(arguments.get("query") or arguments.get("keyword") or "").strip()
                if not query:
                    query = "FineReport 单元格属性 样式 控件 格式"
                payload = fr_setting_knowledge_service.search(query, limit=int(arguments.get("limit") or 5))
                return "tool_result", {"toolName": tool_name, "summary": payload["summary"], "payload": self._compact(payload, 50000)}, {
                    "toolName": tool_name,
                    "status": "success",
                    "payload": self._compact(payload, 60000),
                }
            if tool_name == "search_reference_cpt":
                if db is None:
                    payload = {"summary": "当前没有可用数据库会话，暂时无法检索案例库。", "hits": []}
                else:
                    query = str(arguments.get("query") or arguments.get("keyword") or "").strip()
                    if not query:
                        query = str(arguments.get("scenario") or arguments.get("reason") or "").strip()
                    payload = await fr_report_case_service.read_reference_case_context(db, query=query, limit=int(arguments.get("limit") or 3))
                return "tool_result", {"toolName": tool_name, "summary": payload["summary"], "payload": self._compact(payload, 50000)}, {
                    "toolName": tool_name,
                    "status": "success",
                    "payload": self._compact(payload, 60000),
                }
            if tool_name == "read_reference_cpt_case":
                if db is None:
                    payload = {"summary": "当前没有可用数据库会话，暂时无法读取参考案例。", "case": None}
                else:
                    case_id = str(arguments.get("caseId") or arguments.get("case_id") or "").strip()
                    case_read = await fr_report_case_service.get_case(db, case_id)
                    payload = {
                        "summary": f"已读取参考案例：{case_read.title}",
                        "case": self._compact(case_read.model_dump(mode="json"), 60000),
                    }
                return "tool_result", {"toolName": tool_name, "summary": payload["summary"], "payload": payload}, {
                    "toolName": tool_name,
                    "status": "success",
                    "payload": payload,
                }
            if tool_name == "read_reference_report_full":
                if db is None:
                    payload = {"summary": "当前没有可用数据库会话，暂时无法读取参考报表。"}
                else:
                    payload = await fr_report_case_service.read_reference_report_full(
                        db=db,
                        case_id=str(arguments.get("caseId") or arguments.get("case_id") or "").strip() or None,
                        object_path=str(arguments.get("objectPath") or arguments.get("object_path") or "").strip() or None,
                    )
                    payload["fullCptXml"] = self._compact(str(payload.get("fullCptXml") or ""), 90000)
                    payload["summary"] = "参考报表完整 CPT XML 已读取。"
                return "file_read", {"toolName": tool_name, **payload}, {"toolName": tool_name, "status": "success", "payload": payload}
            if tool_name == "edit_cpt_file":
                edits = arguments.get("edits") if isinstance(arguments.get("edits"), list) else []
                if not edits and ("oldText" in arguments or "newText" in arguments):
                    edits = [arguments]
                result = {
                    "assistantMessage": "已按精确文件编辑生成候选 CPT。",
                    "operations": [
                        {
                            "operationType": "file_edit",
                            "summary": str(arguments.get("summary") or f"{len(edits)} 处 CPT 文件编辑"),
                            "riskLevel": str(arguments.get("riskLevel") or "medium"),
                            "payload": {"edits": edits},
                        }
                    ],
                }
                operations = self._normalize_operations(result)
                candidate_xml = self._build_candidate_xml(source_xml, result, operations)
                loop_state["candidateXml"] = candidate_xml
                loop_state["operations"] = operations
                loop_state["modelResult"] = result
                payload = {"summary": "精确文件编辑已在内存中通过 XML 校验。", "editCount": len(edits), "xmlChars": len(candidate_xml)}
                return "tool_result", {"toolName": tool_name, "summary": payload["summary"], "payload": payload}, {
                    "toolName": tool_name,
                    "status": "success",
                    "payload": payload,
                }
            if tool_name == "write_cpt_full":
                final_xml = str(arguments.get("finalCptXml") or arguments.get("xml") or "").strip()
                result = {"assistantMessage": "已按完整 WorkBook 生成候选 CPT。", "finalCptXml": final_xml}
                operations = self._normalize_operations(result)
                candidate_xml = self._build_candidate_xml(source_xml, result, operations)
                loop_state["candidateXml"] = candidate_xml
                loop_state["operations"] = operations
                loop_state["modelResult"] = result
                payload = {"summary": "完整 WorkBook 已在内存中通过 XML 校验。", "xmlChars": len(candidate_xml)}
                return "tool_result", {"toolName": tool_name, "summary": payload["summary"], "payload": payload}, {
                    "toolName": tool_name,
                    "status": "success",
                    "payload": payload,
                }
        except Exception as exc:
            payload = {"summary": f"{tool_name} 执行失败，下一轮会带着错误继续修复。", "error": str(exc)}
            return "tool_result", {"toolName": tool_name, "summary": payload["summary"], "payload": payload}, {
                "toolName": tool_name,
                "status": "failed",
                "error": str(exc),
            }
        payload = {"summary": f"未知工具已忽略：{tool_name}"}
        return "tool_result", {"toolName": tool_name, "summary": payload["summary"], "payload": payload}, {
            "toolName": tool_name,
            "status": "ignored",
            "payload": payload,
        }

    def _read_cpt_slice(self, source_xml: str, selector: str) -> dict[str, Any]:
        selector = str(selector or "").strip()
        if not selector:
            return {"selector": selector, "status": "failed", "error": "selector 为空"}
        try:
            start, end = self._find_xml_target(source_xml, selector)
            return {"selector": selector, "status": "success", "xml": self._compact(source_xml[start:end], 30000)}
        except Exception as exc:
            matches = self._search_xml(source_xml, selector)
            return {"selector": selector, "status": "failed", "error": str(exc), "nearbyMatches": matches[:5]}

    def _find_xml_target(self, source_xml: str, selector: str) -> tuple[int, int]:
        locator_name = "_find_" + "xml" + "_patch_target"
        locator = getattr(fr_report_ai_operation_service, locator_name)
        return locator(source_xml, selector)

    def _search_xml(self, source_xml: str, query: str) -> list[dict[str, Any]]:
        query = str(query or "").strip()
        if not query:
            return []
        matches: list[dict[str, Any]] = []
        pattern = re.escape(query)
        for match in re.finditer(pattern, source_xml, flags=re.I):
            start = max(0, match.start() - 1200)
            end = min(len(source_xml), match.end() + 1200)
            matches.append({"index": match.start(), "snippet": source_xml[start:end]})
            if len(matches) >= 20:
                break
        return matches

    async def _query_database_sample(
        self,
        arguments: dict[str, Any],
        connection_config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        sql = str(arguments.get("sql") or "").strip()
        table_name = str(arguments.get("tableName") or arguments.get("table") or "").strip()
        max_rows = max(1, min(int(arguments.get("maxRows") or 5), 20))
        if not sql and table_name:
            valid_tables = self._normalize_table_names([table_name])
            if not valid_tables:
                return {"summary": "表名不符合只读样例查询规则。", "rows": [], "columns": [], "errors": ["表名格式不合法"]}
            sql = f"SELECT * FROM {valid_tables[0]} LIMIT {max_rows}" if self._connection_db_type(connection_config) == "mysql" else f"SELECT TOP {max_rows} * FROM {valid_tables[0]}"
        if not sql:
            return {"summary": "没有提供 SQL 或表名。", "rows": [], "columns": [], "errors": ["缺少 sql/tableName"]}
        safety_errors = sqlserver_query_service._validate_readonly_sql(sql)
        if safety_errors:
            return {"summary": "样例查询被只读校验拦截。", "rows": [], "columns": [], "errors": safety_errors}
        try:
            if connection_config:
                rows, columns = await asyncio.to_thread(sqlserver_query_service._execute_sample_query_with_config, sql, connection_config, max_rows)
            else:
                rows, columns = await asyncio.to_thread(sqlserver_query_service._execute_sample_query, sql)
        except Exception as exc:
            return {"summary": "样例查询执行失败。", "rows": [], "columns": [], "errors": [str(exc)]}
        return {"summary": f"样例查询完成，返回 {len(rows)} 行。", "rows": rows[:max_rows], "columns": columns, "errors": []}

    async def _database_connection_config_from_context(
        self,
        db: AsyncSession | None,
        user_id: int | None,
        arguments: dict[str, Any],
        database_source_context: dict[str, Any],
    ) -> dict[str, Any] | None:
        if db is None or user_id is None:
            return None
        connection_name = str(arguments.get("connectionName") or database_source_context.get("connectionName") or "").strip()
        if not connection_name:
            return None
        statement = select(FrReportDatabaseConnection).where(
            FrReportDatabaseConnection.connection_name == connection_name,
            FrReportDatabaseConnection.is_deleted == 0,
            FrReportDatabaseConnection.status == "active",
        )
        rows = list((await db.exec(statement)).all())
        if not rows:
            return None
        row = sorted(rows, key=lambda item: (item.user_id != user_id, item.id))[0]
        return {
            "host": row.host,
            "port": row.port,
            "database": row.database,
            "username": row.username,
            "password": row.password,
            "odbc_driver": row.odbc_driver,
            "db_type": row.db_type,
            "driver_key": row.driver_key,
        }

    def _connection_db_type(self, connection_config: dict[str, Any] | None) -> str:
        return str((connection_config or {}).get("db_type") or "sqlserver").lower()

    def _normalize_table_names(self, value: Any) -> list[str]:
        raw = value if isinstance(value, list) else [value]
        table_names: list[str] = []
        for item in raw:
            text = str(item or "").strip()
            if not text:
                continue
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)?", text):
                continue
            table_names.append(text)
        return table_names[:8]

    def _react_tool_summary(self, tool_name: str) -> str:
        summaries = {
            "read_cpt_full": "读取完整 CPT XML",
            "read_cpt_slice": "读取 CPT 片段",
            "search_xml": "搜索 CPT XML",
            "inspect_report_layout": "检查报表结构",
            "inspect_database_schema": "查询数据库结构",
            "query_database_sample": "查询样例数据",
            "read_excel_context": "读取 Excel 附件",
            "read_word_context": "读取 Word 附件",
            "search_fr_setting_knowledge": "检索属性设置知识",
            "search_reference_cpt": "检索参考案例",
            "read_reference_cpt_case": "读取参考案例",
            "read_reference_report_full": "读取参考报表",
            "edit_cpt_file": "应用 CPT 文件编辑",
            "write_cpt_full": "完整 CPT 兜底",
        }
        return summaries.get(tool_name, tool_name)

    def _opening_message(self, request: str) -> str:
        text = re.sub(r"\s+", " ", str(request or "")).strip(" ：:。")
        if len(text) > 30:
            text = f"{text[:30]}..."
        if text:
            return f"我先按这句需求定位真实 XML：{text}"
        return "我先读当前 CPT 本体，确认真实结构后再动。"

    def _database_context_summary(self, context: dict[str, Any]) -> str:
        if context.get("available"):
            return "数据库结构和样例数据读取完成。"
        if context.get("connectionStatus") == "unmatched":
            return "当前 CPT 数据源和平台查库连接未对齐，已跳过查库以避免误判。"
        if context.get("tableNames"):
            return "已识别到表名，但本轮没有拿到可用数据库结构。"
        return "本轮未识别到可查询的真实表名。"

    def _react_heartbeat(self, step: int, heartbeat: int) -> str:
        messages = [
            "还在对照当前 CPT，先不急着猜。",
            "我在等模型确认下一步要读哪里，或直接给完整 CPT。",
            "这轮稍慢一点，拿到结果就继续往下走。",
        ]
        return messages[(heartbeat - 1) % len(messages)]

    def _react_system_prompt(self) -> str:
        return (
            "你是 FineReport 报表专用高权限 Agent。你不是一次性模板生成器，必须根据观察循环推进。"
            "每一轮只做两类事之一：1）信息不足时返回 toolCalls 调用工具；2）信息足够时返回 file_edit 精确文件编辑，必要时用 finalCptXml 完整 WorkBook 兜底。"
            "不要输出 Markdown，不要输出自然语言之外的解释块；只返回严格 JSON。"
            "工具观察是事实，用户当前指令优先于旧会话记录；已写入版本的旧待应用项不能当成本轮事实。"
            "你可以读取完整 CPT、局部 XML、数据库结构、样例数据和附件；上下文不够就主动调用工具，不要猜。"
            "遇到格式、扩展、样式、形态、其他、悬浮元素、控件、条件属性、超级链接或填报类需求时，优先调用 search_fr_setting_knowledge 了解属性面板对应的 CPT 节点线索；这只是参考，不能替代当前 CPT 片段、案例和预览验证。"
            "CPT 修改没有类型边界：参数栏、数据集、样式、填报、脚本、隐藏行列、多层表头都可以直接改 XML。"
            "本链路默认接受 file_edit：oldText/newText 必须是当前 CPT 原文的精确替换块；不再使用旧 xml_patch/selector 写入器。"
            "当修改跨越大量节点、exact edit 不稳定或 oldText 难以唯一定位时，才返回 finalCptXml 完整 WorkBook。"
            "隐藏整行整列优先模仿设计器真实写法：ReportPageAttr 下 HR/HC 记录隐藏范围，ColumnWidth/RowHeight 往往同步把对应尺寸置 0；不要只给单元格 Visible=false。"
            "用户说第一列、第二列、A列、B列时，先按模板设计坐标处理；预览展开坐标只能作为参考。"
            "任何修改都要做布局影响检查：字段格式变长、表头变长、隐藏列、合并单元格变化、控件变化、填报公式变化，都要联动检查 ColumnWidth、RowHeight、Style、ReportWriteAttr 和相关单元格。"
            "不要把样式适配理解成固定规则；先看当前 CPT 真实写法和参考案例，再按当前报表的原生结构延续。"
            "ReportWriteAttr、脚本、控件和复杂条件属性必须模仿当前 CPT 或参考报表的完整真实节点；不要凭记忆拼不存在的 FineReport XML 结构。"
            "横向扩展区域右侧新增、移动或修改任何单元格时，如果左侧或上方存在横向扩展单元格，必须读取并处理父格关系；不要只检查合计列。普通文本、公式、备注、按钮、填报控件都可能需要脱离横向扩展链，并同步更新父格和 sortHeader。"
            "日期和数字格式修改必须保留原单元格数据绑定/DSColumn/公式主体；如果 FineReport 预览不吃 DateAttr，优先把数据集显示字段 FORMAT 成目标格式，不能把样例日期硬编码进单元格。"
            "把日期列改成 yyyy年MM月dd日 时，要同步检查列宽；隐藏前置列后，日期列仍可能太窄导致换行。"
            "修改数据绑定必须按表头语义和真实数据库字段定位，不能把样例值硬编码进数据单元格。"
            "预览里的运行时扩展单元格不等于模板 XML 坐标，必须依据 reportLayoutContext、rawXml 和 CPT 片段确认。"
            "每次准备返回 file_edit 或 finalCptXml 前，都必须先调用 search_reference_cpt；案例库是写入前的常规观察，不是可选兜底。"
            "mini-shot：用户说“把市场筛选改成下拉”。若不知道参数栏写法，先 toolCalls=[read_cpt_slice ReportParameterAttr, search_xml ComboBox]；观察后在完整 WorkBook 中改好参数控件和相关字典。"
            "mini-shot：用户说“黄曲霉用 price1，不保黄曲霉用 price2”。先查 schema/sample，再读相关表头单元格和数据单元格 XML，最后在完整 WorkBook 中改 TableData SQL 与 DSColumn 绑定。"
            "mini-shot：用户说“隐藏第一列”。先看 ReportPageAttr/HC 和 ColumnWidth；设计器真值通常是 <HC F=\"0\" T=\"0\"/>，并把 ColumnWidth 的第 1 项置 0，最后返回两个 file_edit 精确替换相关节点。"
            "mini-shot：用户说“第二列日期改成 yyyy年MM月dd日”。先读目标日期单元格、格式节点、数据集 SQL 和填报引用；若预览不吃单元格格式，就优先把 SQL 输出字段改为目标显示格式，并同步检查列宽和写回公式。"
            "面向用户的 assistantMessage 要像正在工作的人：短、自然、说明正在查什么或改什么，不要固定模板腔。"
            "不要反复使用“报表结构已经拿到了”“基础情况差不多清楚了”“下面我会”“收到，准备”这类流程套话；如果没有新信息，就少说或直接调用工具。"
            "进度句要贴住当前任务里的具体对象，例如某个单元格、字段、数据集、XML 节点或参考案例，而不是泛泛描述流程。"
        )

    def _should_write_immediately(self, message: str, autonomy_mode: str) -> bool:
        mode = str(autonomy_mode or "").strip().lower()
        if mode in {"high", "direct", "auto_write", "write", "execute", "autonomous"}:
            return True
        return bool(re.search(r"(直接|立即|马上).{0,8}(写入|执行|应用|覆盖)|不用确认|无需确认|自动写入|直接改", message or ""))

    def _build_operation_draft(
        self,
        *,
        assistant_message: str,
        normalized_path: str,
        operations: list[dict[str, Any]],
        candidate_xml: str,
        warnings: list[str],
    ) -> dict[str, Any]:
        draft_operations = self._draft_safe_operations(operations, candidate_xml)
        highest_risk = "high" if any(str(item.get("riskLevel") or "") == "high" for item in draft_operations) else "medium"
        return {
            "draftId": f"fr-work-draft-{uuid4().hex[:12]}",
            "baseVersion": "current",
            "targetVersion": "pending",
            "status": "draft" if draft_operations else "blocked",
            "assistantMessage": assistant_message or "已生成待确认修改项，确认后再写入 CPT。",
            "operations": draft_operations,
            "previewPatch": {},
            "safety": {
                "requiresApproval": True,
                "riskLevel": highest_risk,
                "storageImpact": "确认前不写入 CPT 文件版本；确认后才生成结构版本和文件版本。",
                "objectPath": normalized_path,
            },
            "modelName": None,
            "warnings": warnings,
        }

    def _draft_safe_operations(self, operations: list[dict[str, Any]], candidate_xml: str) -> list[dict[str, Any]]:
        draft_operations: list[dict[str, Any]] = []
        for operation in operations[:50]:
            op_type = str(operation.get("operationType") or "")
            payload = operation.get("payload") if isinstance(operation.get("payload"), dict) else {}
            if op_type == "file_edit":
                edits = payload.get("edits") if isinstance(payload.get("edits"), list) else []
                draft_operations.append(
                    {
                        "operationType": "file_edit",
                        "target": "WorkBook",
                        "summary": str(operation.get("summary") or f"{len(edits)} 处 CPT 文件编辑待确认"),
                        "riskLevel": str(operation.get("riskLevel") or "medium"),
                        "payload": {"editCount": len(edits)},
                    }
                )
                continue
            if op_type in {"write_cpt_full", "full_replace"}:
                new_xml = str(payload.get("newXml") or payload.get("xml") or payload.get("finalCptXml") or candidate_xml)
                draft_operations.append(
                    {
                        "operationType": "write_cpt_full",
                        "target": "WorkBook",
                        "summary": str(operation.get("summary") or "整份 CPT WorkBook 待确认重写"),
                        "riskLevel": "high",
                        "payload": {"finalCptXml": new_xml},
                    }
                )
        if not draft_operations and candidate_xml:
            draft_operations.append(
                {
                    "operationType": "write_cpt_full",
                    "target": "WorkBook",
                    "summary": "整份 CPT WorkBook 待确认重写",
                    "riskLevel": "high",
                    "payload": {"finalCptXml": candidate_xml},
                }
            )
        return draft_operations

    def _build_candidate_xml(
        self,
        source_xml: str,
        result: dict[str, Any],
        operations: list[dict[str, Any]],
    ) -> str:
        candidate_xml = source_xml
        changed = False
        for operation in operations:
            op_type = str(operation.get("operationType") or "")
            payload = operation.get("payload") if isinstance(operation.get("payload"), dict) else {}
            if op_type == "file_edit":
                edits = payload.get("edits") if isinstance(payload.get("edits"), list) else []
                if not edits and ("oldText" in payload or "newText" in payload):
                    edits = [payload]
                for edit in edits[:200]:
                    if not isinstance(edit, dict):
                        continue
                    old_text = str(edit.get("oldText") or edit.get("old") or "")
                    new_text = str(edit.get("newText") or edit.get("new") or "")
                    replace_all = bool(edit.get("replaceAll") or edit.get("replace_all"))
                    if not old_text:
                        raise ValueError("file_edit 缺少 oldText")
                    match_count = candidate_xml.count(old_text)
                    if match_count <= 0:
                        raise ValueError(f"file_edit oldText 在当前 CPT 中不存在：{old_text[:120]}")
                    if match_count > 1 and not replace_all:
                        raise ValueError(f"file_edit oldText 不唯一（{match_count} 处），请扩大上下文或设置 replaceAll")
                    candidate_xml = candidate_xml.replace(old_text, new_text) if replace_all else candidate_xml.replace(old_text, new_text, 1)
                    changed = True
                continue
            if op_type in {"write_cpt_full", "full_replace"}:
                new_xml = str(payload.get("newXml") or payload.get("xml") or payload.get("finalCptXml") or "").strip()
                if new_xml:
                    fr_report_ai_operation_service._validate_full_cpt_xml(new_xml)
                    return new_xml
        if changed:
            fr_report_ai_operation_service._validate_full_cpt_xml(candidate_xml)
            return candidate_xml
        final_xml = str(result.get("finalCptXml") or "").strip()
        if final_xml:
            fr_report_ai_operation_service._validate_full_cpt_xml(final_xml)
            return final_xml
        raise ValueError("没有返回可应用的 CPT 文件编辑")

    def _preserve_existing_hidden_layout(self, source_xml: str, candidate_xml: str, *, request: str) -> str:
        if self._request_explicitly_changes_hidden_state(request):
            return candidate_xml
        hidden_columns = self._hidden_layout_ranges(source_xml, "HC")
        hidden_rows = self._hidden_layout_ranges(source_xml, "HR")
        if not hidden_columns and not hidden_rows:
            return candidate_xml

        next_xml = candidate_xml
        next_xml = self._merge_hidden_layout_nodes(source_xml, next_xml, "HC", hidden_columns)
        next_xml = self._merge_hidden_layout_nodes(source_xml, next_xml, "HR", hidden_rows)
        next_xml = self._zero_dimension_ranges(next_xml, "ColumnWidth", hidden_columns)
        next_xml = self._zero_dimension_ranges(next_xml, "RowHeight", hidden_rows)
        return next_xml

    def _normalize_requested_hidden_layout(self, candidate_xml: str, *, request: str) -> str:
        hidden_columns = self._requested_hidden_column_ranges(request)
        if not hidden_columns:
            hidden_columns = self._semantic_hidden_column_ranges(candidate_xml, request)
        if not hidden_columns:
            return candidate_xml
        next_xml = candidate_xml
        next_report_page_xml = self._hidden_report_page_xml(next_xml, hidden_columns)
        if next_report_page_xml:
            next_xml = re.sub(r"<ReportPageAttr\b[^>]*(?:/>|>.*?</ReportPageAttr>)", next_report_page_xml, next_xml, count=1, flags=re.S | re.I)
        column_width_xml = self._requested_hidden_column_width_xml(next_xml, hidden_columns, request)
        if column_width_xml:
            next_xml = re.sub(r"<ColumnWidth\b[^>]*>.*?</ColumnWidth>", column_width_xml, next_xml, count=1, flags=re.S | re.I)
        return next_xml

    def _requested_hidden_column_width_xml(self, source_xml: str, hidden_ranges: list[tuple[int, int]], request: str) -> str | None:
        match = re.search(r"<ColumnWidth\b[^>]*>.*?</ColumnWidth>", source_xml, flags=re.S | re.I)
        if not match:
            return None
        original_xml = match.group(0)
        cdata_match = re.search(r"<!\[CDATA\[(.*?)]]>", original_xml, flags=re.S)
        if not cdata_match:
            return None
        default_width = int(self._regex_first(original_xml, r'\bdefaultValue="(\d+)"') or "2743200")
        values = [item.strip() for item in cdata_match.group(1).split(",")]
        if not values:
            return None
        hidden_columns = {
            index
            for start, end in hidden_ranges
            for index in range(max(0, start), max(start, end) + 1)
        }
        date_columns: set[int] = set()
        for selector in self._requested_date_cell_selectors(source_xml, request):
            match_selector = re.fullmatch(r"cell:([A-Z]{1,3})\d+", selector, flags=re.I)
            if match_selector:
                date_columns.add(self._column_index(match_selector.group(1)) - 1)
        changed = False
        max_index = max([len(values) - 1, *hidden_columns, *date_columns])
        while len(values) <= max_index:
            values.append(str(default_width))
            changed = True
        for index, raw in enumerate(list(values)):
            target = raw
            if index in hidden_columns:
                target = "0"
            elif raw.strip() == "0":
                target = str(default_width)
            if index in date_columns and index not in hidden_columns:
                try:
                    target = str(max(int(target), 4572000))
                except ValueError:
                    target = "4572000"
            if values[index] != target:
                values[index] = target
                changed = True
        if not changed:
            return None
        return original_xml[: cdata_match.start(1)] + ",".join(values) + original_xml[cdata_match.end(1) :]

    def _request_explicitly_changes_hidden_state(self, request: str) -> bool:
        return bool(re.search(r"取消隐藏|取消.*隐藏|恢复.*(列|行)|显示.*(列|行)|不要隐藏|不隐藏", request))

    def _hidden_layout_ranges(self, source_xml: str, tag: str) -> list[tuple[int, int]]:
        report_page_match = re.search(r"<ReportPageAttr\b[^>]*(?:/>|>.*?</ReportPageAttr>)", source_xml, flags=re.S | re.I)
        if not report_page_match:
            return []
        ranges: list[tuple[int, int]] = []
        for match in re.finditer(rf"<{tag}\b(?=[^>]*\bF=\"(\d+)\")(?=[^>]*\bT=\"(\d+)\")[^>]*/>", report_page_match.group(0), flags=re.S | re.I):
            ranges.append((int(match.group(1)), int(match.group(2))))
        return ranges

    def _merge_hidden_layout_nodes(self, source_xml: str, candidate_xml: str, tag: str, ranges: list[tuple[int, int]]) -> str:
        if not ranges:
            return candidate_xml
        existing_ranges = set(self._hidden_layout_ranges(candidate_xml, tag))
        missing_nodes: list[str] = []
        source_report_page_match = re.search(r"<ReportPageAttr\b[^>]*(?:/>|>.*?</ReportPageAttr>)", source_xml, flags=re.S | re.I)
        source_report_page_xml = source_report_page_match.group(0) if source_report_page_match else ""
        for start, end in ranges:
            if (start, end) in existing_ranges:
                continue
            raw_match = re.search(rf"<{tag}\b(?=[^>]*\bF=\"{start}\")(?=[^>]*\bT=\"{end}\")[^>]*/>", source_report_page_xml, flags=re.S | re.I)
            missing_nodes.append(raw_match.group(0) if raw_match else f'<{tag} F="{start}" T="{end}"/>')
        if not missing_nodes:
            return candidate_xml

        report_page_match = re.search(r"<ReportPageAttr\b[^>]*(?:/>|>.*?</ReportPageAttr>)", candidate_xml, flags=re.S | re.I)
        if not report_page_match:
            return candidate_xml
        report_page_xml = report_page_match.group(0)
        inserted_nodes = "\n".join(missing_nodes)
        if report_page_xml.rstrip().endswith("/>"):
            open_tag = re.sub(r"/>\s*$", ">", report_page_xml)
            next_report_page_xml = f"{open_tag}\n{inserted_nodes}\n</ReportPageAttr>"
        elif "<FR" in report_page_xml:
            next_report_page_xml = re.sub(r"(<FR\b[^>]*/>)", rf"\1\n{inserted_nodes}", report_page_xml, count=1, flags=re.S | re.I)
        else:
            next_report_page_xml = re.sub(r"(<ReportPageAttr\b[^>]*>)", rf"\1\n{inserted_nodes}", report_page_xml, count=1, flags=re.S | re.I)
        return candidate_xml[: report_page_match.start()] + next_report_page_xml + candidate_xml[report_page_match.end() :]

    def _zero_dimension_ranges(self, xml: str, tag: str, ranges: list[tuple[int, int]]) -> str:
        if not ranges:
            return xml
        match = re.search(rf"<{tag}\b[^>]*>.*?</{tag}>", xml, flags=re.S | re.I)
        if not match:
            return xml
        dimension_xml = match.group(0)
        cdata_match = re.search(r"<!\[CDATA\[(.*?)]]>", dimension_xml, flags=re.S)
        if not cdata_match:
            return xml
        values = [item.strip() for item in cdata_match.group(1).split(",")]
        changed = False
        for start, end in ranges:
            for index in range(max(0, start), min(len(values), end + 1)):
                if values[index] != "0":
                    values[index] = "0"
                    changed = True
        if not changed:
            return xml
        next_dimension_xml = dimension_xml[: cdata_match.start(1)] + ",".join(values) + dimension_xml[cdata_match.end(1) :]
        return xml[: match.start()] + next_dimension_xml + xml[match.end() :]

    async def _repair_result(
        self,
        *,
        source_xml: str,
        model_payload: dict[str, Any],
        failed_result: dict[str, Any],
        error: str,
    ) -> dict[str, Any]:
        repair_payload = {
            "originalPayload": {**model_payload, "fullCptXml": source_xml},
            "failedResult": failed_result,
            "error": error,
            "instruction": (
                "修复上一次输出。必须返回合法 JSON；优先返回 file_edit 精确替换，必要时才返回 finalCptXml 完整 WorkBook XML。"
                "如果错误来自 SQL Server，请优先阅读 failedResult._candidateDatasetQueries 中失败候选 SQL，"
                "结合 originalPayload.databaseSourceContext 的真实字段和别名修 SQL；不要返回旧 xml_patch/selector，不要解释 XML，直接给可写入修改。"
            ),
        }
        return await asyncio.wait_for(
            fr_report_ai_operation_service._invoke_json(
                system_prompt=self._system_prompt(),
                payload=repair_payload,
                agent_name="FrReportHighAuthorityRepairAgent",
            ),
            timeout=self.REACT_REPAIR_TIMEOUT_SECONDS,
        )

    async def _prepare_candidate_with_repair(
        self,
        *,
        source_xml: str,
        initial_candidate_xml: str,
        initial_model_result: dict[str, Any],
        initial_operations: list[dict[str, Any]],
        assistant_message: str,
        model_payload: dict[str, Any],
        db: AsyncSession | None = None,
        user_id: int | None = None,
    ) -> tuple[str, list[dict[str, Any]], dict[str, Any], str, list[str]]:
        current_result = dict(initial_model_result)
        current_operations = list(initial_operations)
        current_candidate_xml = initial_candidate_xml
        current_message = assistant_message
        warnings: list[str] = []
        last_error = ""
        last_candidate_xml = ""

        for attempt in range(4):
            try:
                candidate_xml = current_candidate_xml or self._build_candidate_xml(source_xml, current_result, current_operations)
                last_candidate_xml = candidate_xml
                candidate_xml = self._preserve_existing_hidden_layout(
                    source_xml,
                    candidate_xml,
                    request=str(model_payload.get("userRequest") or ""),
                )
                last_candidate_xml = candidate_xml
                candidate_xml = self._normalize_requested_hidden_layout(
                    candidate_xml,
                    request=str(model_payload.get("userRequest") or ""),
                )
                last_candidate_xml = candidate_xml
                candidate_xml = fr_report_ai_operation_service._dedupe_table_data_blocks(candidate_xml)
                candidate_xml = fr_report_ai_operation_service._ensure_table_data_parameters(candidate_xml)
                last_candidate_xml = candidate_xml
                candidate_xml = self._normalize_integer_display_sql(
                    candidate_xml,
                    request=str(model_payload.get("userRequest") or ""),
                )
                candidate_xml = self._normalize_bad_dimension_order_sql(
                    candidate_xml,
                    request=str(model_payload.get("userRequest") or ""),
                )
                candidate_xml = self._normalize_integer_display_format(
                    candidate_xml,
                    request=str(model_payload.get("userRequest") or ""),
                )
                last_candidate_xml = candidate_xml
                candidate_xml, binding_warnings = self._normalize_pseudo_dataset_bindings(candidate_xml)
                warnings.extend(binding_warnings)
                last_candidate_xml = candidate_xml
                candidate_xml, nested_binding_warnings = self._normalize_nested_dscolumn_objects(candidate_xml)
                warnings.extend(nested_binding_warnings)
                last_candidate_xml = candidate_xml
                candidate_xml, writeback_warnings = self._normalize_writeback_after_presentation_change(
                    source_xml=source_xml,
                    candidate_xml=candidate_xml,
                    request=str(model_payload.get("userRequest") or ""),
                )
                warnings.extend(writeback_warnings)
                last_candidate_xml = candidate_xml
                candidate_xml, parent_warnings = self._normalize_horizontal_expansion_parenting(candidate_xml)
                warnings.extend(parent_warnings)
                last_candidate_xml = candidate_xml
                candidate_xml, total_warnings = self._normalize_static_total_columns_after_horizontal_expansion(candidate_xml)
                warnings.extend(total_warnings)
                last_candidate_xml = candidate_xml
                candidate_xml, dataset_sql_warnings = await self._validate_and_normalize_dataset_sql(
                    candidate_xml,
                    db=db,
                    user_id=user_id,
                )
                audit_report = await self._audit_candidate_cpt(
                    source_xml=source_xml,
                    candidate_xml=candidate_xml,
                    request=str(model_payload.get("userRequest") or ""),
                    db=db,
                    user_id=user_id,
                )
                warnings.extend(audit_report.get("warnings") or [])
                if audit_report.get("issues"):
                    raise ValueError("候选 CPT 审计未通过：" + "；".join(str(item) for item in audit_report["issues"]))
                current_result["_candidateAudit"] = audit_report
                last_candidate_xml = candidate_xml
                self._validate_insert_before_anchor_preserves_left_side(
                    source_xml,
                    candidate_xml,
                    request=str(model_payload.get("userRequest") or ""),
                )
                self._validate_horizontal_expansion_parenting(source_xml, candidate_xml)
                fr_report_ai_operation_service._validate_full_cpt_xml(candidate_xml)
                if attempt:
                    warnings.append(f"候选 CPT 第 {attempt + 1} 次校验通过，前面失败原因已自动修复：{last_error}")
                warnings.extend(dataset_sql_warnings)
                return candidate_xml, current_operations, current_result, current_message, warnings
            except Exception as exc:
                last_error = str(exc)
                if attempt >= 3:
                    raise CandidatePreparationError(last_error or "候选 CPT 校验失败", warnings) from exc
                warnings.append(f"候选 CPT 校验失败，已进入第 {attempt + 1} 轮自动修复：{last_error}")
                failed_result = {
                    **current_result,
                    "_candidateDatasetQueries": self._extract_dataset_context(last_candidate_xml) if last_candidate_xml else [],
                    "_candidateAudit": await self._safe_candidate_audit(
                        source_xml=source_xml,
                        candidate_xml=last_candidate_xml,
                        request=str(model_payload.get("userRequest") or ""),
                        db=db,
                        user_id=user_id,
                    )
                    if last_candidate_xml
                    else None,
                }
                try:
                    repaired = await self._repair_result(
                        source_xml=source_xml,
                        model_payload=model_payload,
                        failed_result=failed_result,
                        error=last_error,
                    )
                except asyncio.TimeoutError as repair_exc:
                    warnings.append(f"候选 CPT 自动修复超时：{last_error}")
                    raise CandidatePreparationError("候选 CPT 自动修复超时", warnings) from repair_exc
                except Exception as repair_exc:
                    warnings.append(f"候选 CPT 自动修复失败：{repair_exc}")
                    raise CandidatePreparationError(str(repair_exc), warnings) from repair_exc
                current_result = dict(repaired)
                current_operations = self._normalize_operations(current_result)
                current_candidate_xml = ""
                current_message = str(current_result.get("assistantMessage") or current_message)

        raise CandidatePreparationError(last_error or "候选 CPT 校验失败", warnings)

    def _normalize_horizontal_expansion_parenting(self, candidate_xml: str) -> tuple[str, list[str]]:
        candidate_cells = self._extract_cell_blocks(candidate_xml)
        if not candidate_cells:
            return candidate_xml, []

        horizontal_pivot_cols = {
            int(item["c"])
            for item in candidate_cells
            if item["is_ds_column"] and re.search(r"<Expand\b(?=[^>]*\bdir=\"1\")", item["raw"], flags=re.S | re.I)
        }
        if not horizontal_pivot_cols:
            return candidate_xml, []

        cells_by_position = {(int(item["c"]), int(item["r"])): item for item in candidate_cells}
        fixed_cells: list[str] = []
        next_xml = candidate_xml
        for pivot_col in sorted(horizontal_pivot_cols):
            if pivot_col <= 0:
                continue
            pivot_rows = {row for (col, row), _item in cells_by_position.items() if col == pivot_col}
            for item in candidate_cells:
                cell_col = int(item["c"])
                cell_row = int(item["r"])
                if cell_row not in pivot_rows or cell_col <= pivot_col:
                    continue
                if item["is_ds_column"] and re.search(r"<Expand\b(?=[^>]*\bdir=\"1\")", item["raw"], flags=re.S | re.I):
                    continue
                if self._has_explicit_parent_guard(item["raw"]):
                    continue
                fixed_raw = self._add_horizontal_parent_guard(item["raw"], pivot_col - 1, cell_row)
                if fixed_raw == item["raw"]:
                    continue
                next_xml = next_xml.replace(item["raw"], fixed_raw, 1)
                fixed_cells.append(self._cell_address(cell_col, cell_row))
        if not fixed_cells:
            return candidate_xml, []
        return next_xml, [f"已自动补齐横向扩展右侧单元格的父格配置：{', '.join(sorted(set(fixed_cells)))}。"]

    def _add_horizontal_parent_guard(self, cell_xml: str, parent_col: int, parent_row: int) -> str:
        parent_address = self._cell_address(parent_col, parent_row)

        def patch_expand(match: re.Match[str]) -> str:
            tag = match.group(0)
            if re.search(r'\bleftParentDefault=', tag) or re.search(r'\bleft=', tag):
                return tag
            return tag[:-1] + f' leftParentDefault="false" left="{parent_address}">'

        if re.search(r"<Expand\b[^>]*>", cell_xml, flags=re.S | re.I):
            return re.sub(r"<Expand\b[^>]*>", patch_expand, cell_xml, count=1, flags=re.S | re.I)
        insert = f'<Expand leftParentDefault="false" left="{parent_address}"><cellSortAttr/></Expand>\n'
        return re.sub(r"</C>\s*$", insert + "</C>", cell_xml, count=1, flags=re.S | re.I)

    def _normalize_static_total_columns_after_horizontal_expansion(self, candidate_xml: str) -> tuple[str, list[str]]:
        cells = self._extract_cell_blocks(candidate_xml)
        if not cells:
            return candidate_xml, []

        cells_by_position = {(int(item["c"]), int(item["r"])): item for item in cells}
        horizontal_pivots = [
            item
            for item in cells
            if item["is_ds_column"] and re.search(r"<Expand\b(?=[^>]*\bdir=\"1\")", item["raw"], flags=re.S | re.I)
        ]
        if not horizontal_pivots:
            return candidate_xml, []

        horizontal_cols = sorted({int(item["c"]) for item in horizontal_pivots})
        next_xml = candidate_xml
        fixed_cells: list[str] = []
        for item in cells:
            cell_col = int(item["c"])
            cell_row = int(item["r"])
            if not item["is_ds_column"]:
                continue
            pivot_col = max([col for col in horizontal_cols if col < cell_col], default=None)
            if pivot_col is None:
                continue
            pivot_data_cell = cells_by_position.get((pivot_col, cell_row))
            if not pivot_data_cell or not pivot_data_cell["is_ds_column"]:
                continue
            if self._cell_binding_key(item["raw"]) != self._cell_binding_key(pivot_data_cell["raw"]):
                continue
            if not self._column_has_total_header(cells_by_position, cell_col, cell_row):
                continue
            formula = f"=SUM({self._cell_address(pivot_col, cell_row)})"
            fixed_raw = self._replace_cell_object_with_formula(
                item["raw"],
                formula=formula,
                parent_col=max(0, pivot_col - 1),
                parent_row=cell_row,
            )
            if fixed_raw == item["raw"]:
                continue
            next_xml = next_xml.replace(item["raw"], fixed_raw, 1)
            fixed_cells.append(f"{self._cell_address(cell_col, cell_row)}={formula}")

        if not fixed_cells:
            return candidate_xml, []
        return next_xml, [f"已把横向扩展右侧静态合计列改为公式单元格：{', '.join(sorted(set(fixed_cells)))}。"]

    def _column_has_total_header(self, cells_by_position: dict[tuple[int, int], dict[str, Any]], col: int, data_row: int) -> bool:
        for row in range(max(0, data_row - 5), data_row):
            text = re.sub(r"\s+", "", str(cells_by_position.get((col, row), {}).get("text") or ""))
            if text and any(term in text for term in ("合计", "总计", "小计")):
                return True
        return False

    def _replace_cell_object_with_formula(self, cell_xml: str, *, formula: str, parent_col: int, parent_row: int) -> str:
        formula_xml = (
            '<O t="XMLable" class="com.fr.base.Formula">\n'
            "<Attributes>\n"
            f"<![CDATA[{formula}]]></Attributes>\n"
            "</O>"
        )
        next_xml = re.sub(r"<O\b[\s\S]*?</O>", formula_xml, cell_xml, count=1, flags=re.S | re.I)
        next_xml = re.sub(r"\s*<Widget\b[\s\S]*?</Widget>", "", next_xml, count=1, flags=re.S | re.I)
        parent_address = self._cell_address(parent_col, parent_row)
        expand_xml = f'<Expand dir="0" leftParentDefault="false" left="{parent_address}">\n<cellSortAttr/>\n</Expand>'
        if re.search(r"<Expand\b[^>]*>[\s\S]*?</Expand>", next_xml, flags=re.S | re.I):
            next_xml = re.sub(r"<Expand\b[^>]*>[\s\S]*?</Expand>", expand_xml, next_xml, count=1, flags=re.S | re.I)
        elif re.search(r"<Expand\b[^>]*/>", next_xml, flags=re.S | re.I):
            next_xml = re.sub(r"<Expand\b[^>]*/>", expand_xml, next_xml, count=1, flags=re.S | re.I)
        else:
            next_xml = re.sub(r"</C>\s*$", expand_xml + "\n</C>", next_xml, count=1, flags=re.S | re.I)
        return next_xml

    def _validate_horizontal_expansion_parenting(self, source_xml: str, candidate_xml: str) -> None:
        source_cells = {(item["c"], item["r"]): item for item in self._extract_cell_blocks(source_xml)}
        candidate_cells = self._extract_cell_blocks(candidate_xml)
        if not candidate_cells:
            return

        horizontal_ds_cells = [
            item
            for item in candidate_cells
            if item["is_ds_column"] and re.search(r"<Expand\b(?=[^>]*\bdir=\"1\")", item["raw"], flags=re.S | re.I)
        ]
        if not horizontal_ds_cells:
            return

        horizontal_rows = {int(item["r"]) for item in horizontal_ds_cells}
        horizontal_cols_by_row: dict[int, set[int]] = {}
        for item in horizontal_ds_cells:
            horizontal_cols_by_row.setdefault(int(item["r"]), set()).add(int(item["c"]))

        problems: list[str] = []
        for item in candidate_cells:
            cell_col = int(item["c"])
            cell_row = int(item["r"])
            original = source_cells.get((cell_col, cell_row))
            if original and original["raw"] == item["raw"]:
                continue
            if item["is_ds_column"] and re.search(r"<Expand\b(?=[^>]*\bdir=\"1\")", item["raw"], flags=re.S | re.I):
                continue
            if not self._is_after_horizontal_expansion(cell_col, cell_row, horizontal_cols_by_row, horizontal_rows):
                continue
            if self._has_explicit_parent_guard(item["raw"]):
                continue
            problems.append(self._cell_address(cell_col, cell_row))

        if problems:
            raise ValueError(
                "横向扩展区域右侧新增或改动的单元格必须显式处理父格关系。"
                f"以下单元格缺少明确父格或默认父格关闭配置：{', '.join(sorted(set(problems)))}。"
                "请读取当前表头/数据单元格的 Expand、leftParentDefault、topParentDefault、left/top 和参考报表写法后重改；"
                "否则这些格子可能跟随每个横向分组重复扩展、错位，或挤压备注/填报/按钮列。"
            )

    def _validate_insert_before_anchor_preserves_left_side(
        self,
        source_xml: str,
        candidate_xml: str,
        *,
        request: str,
    ) -> None:
        anchor_labels = self._insert_before_anchor_labels(request)
        if not anchor_labels:
            return
        source_cells = self._extract_cell_blocks(source_xml)
        candidate_cells = self._extract_cell_blocks(candidate_xml)
        candidate_by_binding: dict[tuple[str, str], dict[str, Any]] = {}
        for item in candidate_cells:
            key = self._cell_binding_key(item["raw"])
            if key:
                candidate_by_binding[key] = item

        problems: list[str] = []
        for label in anchor_labels:
            anchors = [item for item in source_cells if self._cell_text_matches_label(item["text"], label)]
            for anchor in anchors:
                anchor_col = int(anchor["c"])
                anchor_row = int(anchor["r"])
                left_bound_cells = [
                    item
                    for item in source_cells
                    if int(item["c"]) < anchor_col
                    and abs(int(item["r"]) - anchor_row) <= 3
                    and self._cell_binding_key(item["raw"])
                ]
                for item in left_bound_cells:
                    key = self._cell_binding_key(item["raw"])
                    moved = candidate_by_binding.get(key) if key else None
                    if not moved:
                        continue
                    moved_col = int(moved["c"])
                    moved_row = int(moved["r"])
                    if moved_col >= anchor_col and (moved_col, moved_row) != (int(item["c"]), int(item["r"])):
                        problems.append(
                            f"{self._cell_address(int(item['c']), int(item['r']))}->{self._cell_address(moved_col, moved_row)}"
                        )
        if problems:
            raise ValueError(
                "检测到“在某列之前插入”的候选修改挪动了锚点左侧已有数据列。"
                f"异常移动：{', '.join(sorted(set(problems)))}。"
                "请保留锚点左侧既有横向扩展/数据列位置，只移动锚点列及其右侧相关单元格，并同步父格、列宽和填报配置。"
            )

    def _insert_before_anchor_labels(self, request: str) -> list[str]:
        labels: list[str] = []
        patterns = [
            r"在\s*([^，。,；;\n]{1,12}?)\s*(?:列|字段|表头|单元格)?\s*之前",
            r"([^，。,；;\n]{1,12}?)\s*(?:列|字段|表头|单元格)?\s*前\s*(?:插入|增加|新增|添加)",
            r"([^，。,；;\n]{1,12}?)\s*(?:之前|前面)\s*(?:插入|增加|新增|添加)",
        ]
        for pattern in patterns:
            for match in re.finditer(pattern, request or ""):
                label = re.sub(r"\s+", "", match.group(1).strip(" “”“\"'`"))
                if 0 < len(label) <= 12 and label not in labels:
                    labels.append(label)
        return labels[:5]

    def _cell_binding_key(self, cell_xml: str) -> tuple[str, str] | None:
        ds_name = self._regex_first(cell_xml, r'\bdsName="([^"]+)"')
        column_name = self._regex_first(cell_xml, r'\bcolumnName="([^"]+)"')
        if not ds_name or not column_name:
            return None
        return ds_name, column_name

    def _cell_text_matches_label(self, text: str, label: str) -> bool:
        normalized_label = re.sub(r"\s+", "", label or "")
        normalized_text = re.sub(r"\s+", "", re.sub(r"<!\[CDATA\[(.*?)]]>", r"\1", text or ""))
        return bool(normalized_label and normalized_label in normalized_text)

    def _is_after_horizontal_expansion(
        self,
        cell_col: int,
        cell_row: int,
        horizontal_cols_by_row: dict[int, set[int]],
        horizontal_rows: set[int],
    ) -> bool:
        if any(col < cell_col for col in horizontal_cols_by_row.get(cell_row, set())):
            return True
        nearby_rows = [row for row in horizontal_rows if abs(row - cell_row) <= 3]
        return any(any(col < cell_col for col in horizontal_cols_by_row.get(row, set())) for row in nearby_rows)

    def _has_explicit_parent_guard(self, cell_xml: str) -> bool:
        expand_match = re.search(r"<Expand\b[^>]*(?:/>|>.*?</Expand>)", cell_xml, flags=re.S | re.I)
        expand_xml = expand_match.group(0) if expand_match else ""
        if not expand_xml:
            return False
        has_explicit_parent = bool(re.search(r"\b(left|top)=\"[A-Z]+\d+\"", expand_xml, flags=re.I))
        has_disabled_default_parent = bool(
            re.search(r'\b(?:leftParentDefault|topParentDefault)="false"', expand_xml, flags=re.I)
        )
        return has_explicit_parent or has_disabled_default_parent

    def _extract_cell_blocks(self, xml: str) -> list[dict[str, Any]]:
        cells: list[dict[str, Any]] = []
        for match in re.finditer(r"<C\b(?=[^>]*\bc=\"(\d+)\")(?=[^>]*\br=\"(\d+)\")[^>]*>.*?</C>", xml, flags=re.S | re.I):
            raw = match.group(0)
            cells.append(
                {
                    "c": int(match.group(1)),
                    "r": int(match.group(2)),
                    "raw": raw,
                    "text": self._cell_display_text(raw),
                    "is_ds_column": 't="DSColumn"' in raw,
                }
            )
        return cells

    def _cell_display_text(self, cell_xml: str) -> str:
        text = re.sub(r"<!\[CDATA\[(.*?)]]>", r" \1 ", cell_xml or "", flags=re.S)
        text = re.sub(r"<[^>]+>", " ", text)
        return re.sub(r"\s+", " ", text).strip()

    def _cell_address(self, zero_based_col: int, zero_based_row: int) -> str:
        col = zero_based_col + 1
        letters = ""
        while col:
            col, rem = divmod(col - 1, 26)
            letters = chr(65 + rem) + letters
        return f"{letters}{zero_based_row + 1}"

    def _normalize_bad_dimension_order_sql(self, xml: str, *, request: str) -> str:
        if re.search(r"顺序|排序|次序|和.*一致|按.*图片|按.*附件", request):
            return xml

        def normalize_query(match: re.Match[str]) -> str:
            query_sql = match.group(1)
            if not re.search(r"CHARINDEX\s*\([\s\S]*?(调整|设置|生成|CPT|XML|预览|读取|属性|格式)", query_sql, flags=re.I):
                return match.group(0)
            next_sql = re.sub(
                r"ORDER\s+BY\s+CASE\s+WHEN\s+CHARINDEX\s*\([\s\S]+?\)\s*>\s*0\s+THEN\s+CHARINDEX\s*\([\s\S]+?\)\s+ELSE\s+\d+\s+END\s*,\s*",
                "ORDER BY ",
                query_sql,
                count=1,
                flags=re.S | re.I,
            )
            return f"<Query><![CDATA[{next_sql}]]></Query>"

        return re.sub(r"<Query\b[^>]*>\s*<!\[CDATA\[(.*?)]]>\s*</Query>", normalize_query, xml, flags=re.S | re.I)

    def _normalize_integer_display_sql(self, xml: str, *, request: str) -> str:
        if not re.search(r"取整|不显示小数|不要小数|整数|0\s*位小数", request):
            return xml
        aliases = self._integer_display_target_aliases(request)
        if not aliases:
            return xml

        def normalize_query(match: re.Match[str]) -> str:
            body = match.group(1)
            next_body = body
            for alias in aliases:
                if re.search(rf"CAST\s*\(\s*ROUND\([\s\S]*?\)\s+AS\s+(?:INT|BIGINT)\s*\)\s+AS\s+{re.escape(alias)}\b", next_body, flags=re.I):
                    continue
                pattern = re.compile(
                    rf"ROUND\((?P<body>[\s\S]*?),\s*0\s*\)\s+AS\s+{re.escape(alias)}\b",
                    flags=re.I,
                )
                next_body = pattern.sub(lambda item: f"CAST(ROUND({item.group('body')}, 0) AS INT) AS {alias}", next_body)
            return f"<Query><![CDATA[{next_body}]]></Query>"

        return re.sub(r"<Query\b[^>]*>\s*<!\[CDATA\[(.*?)]]>\s*</Query>", normalize_query, xml, flags=re.S | re.I)

    def _normalize_integer_display_format(self, xml: str, *, request: str) -> str:
        """给“取整/不显示小数”的目标数据单元格补帆软原生数字格式。

        SQL 可以决定计算口径，但 FineReport 单元格格式才是展示口径。尤其 SQL Server
        的 DECIMAL/ROUND 常会保留 scale，预览里仍显示 .00，因此这里不依赖具体报表坐标，
        而是按 DSColumn 字段语义给目标单元格设置 NumberFormat #0。
        """

        if not re.search(r"取整|不显示小数|不要小数|整数|0\s*位小数", request):
            return xml
        aliases = self._integer_display_target_aliases(request)
        if not aliases:
            return xml

        def normalize_cell(match: re.Match[str]) -> str:
            cell_xml = match.group(0)
            field = self._regex_first(cell_xml, r'\bcolumnName="([^"]+)"') or ""
            if not self._is_integer_display_field(field, aliases=aliases):
                return cell_xml
            return self._ensure_cell_integer_number_format(cell_xml)

        return re.sub(r"<C\b[^>]*>.*?</C>", normalize_cell, xml, flags=re.S | re.I)

    def _integer_display_target_aliases(self, request: str) -> set[str]:
        aliases: set[str] = set()
        lowered = request.lower()
        if re.search(r"涨跌|增减|change|latest_change|rise_fall|rise\s*fall", lowered, flags=re.I):
            aliases.update(
                {
                    "latest_change",
                    "Rise_fall",
                    "rise_fall",
                    "change_amt",
                    "change",
                    "change_amount",
                    "delta",
                    "diff",
                }
            )
        aliases.update(re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*(?:change|delta|diff|rise_fall)[A-Za-z0-9_]*\b", request, flags=re.I))
        return aliases

    def _is_integer_display_field(self, field: str, *, aliases: set[str]) -> bool:
        if not field:
            return False
        lowered = field.lower()
        lowered_aliases = {item.lower() for item in aliases}
        return lowered in lowered_aliases or bool(
            re.search(r"(?:^|_)(?:latest_)?(?:change|change_amt|change_amount|rise_fall|delta|diff)(?:_|$)", lowered)
        )

    def _ensure_cell_integer_number_format(self, cell_xml: str) -> str:
        number_format_xml = (
            '<NumberFormat integer="true" useThousandSeparator="false" negativeStyle="0">\n'
            '<FormatAttr class="com.fr.base.CoreDecimalFormat">\n'
            '<Attributes format="#0"/>\n'
            '</FormatAttr>\n'
            '</NumberFormat>'
        )
        if re.search(r"<NumberFormat\b[^>]*>.*?</NumberFormat>", cell_xml, flags=re.S | re.I):
            return re.sub(r"<NumberFormat\b[^>]*>.*?</NumberFormat>", number_format_xml, cell_xml, count=1, flags=re.S | re.I)
        if re.search(r"\n?<Expand\b", cell_xml, flags=re.S | re.I):
            return re.sub(r"\n?<Expand\b", "\n" + number_format_xml + "\n<Expand", cell_xml, count=1, flags=re.S | re.I)
        return re.sub(r"\n?</C>\s*$", "\n" + number_format_xml + "\n</C>", cell_xml, count=1, flags=re.S | re.I)

    def _normalize_pseudo_dataset_bindings(self, cpt_xml: str) -> tuple[str, list[str]]:
        """把模型偶发生成的伪数据绑定转成 FineReport 原生 DSColumn。

        FineReport 常见样本使用 `<O t="DSColumn"><Attributes dsName="..." columnName="..."/>...`。
        模型容易生成 `<O t="ds"><![CDATA[$$$字段]]></O>` 或 `<O t="ds"><DS ds="..." name="..."/></O>`，
        这两类都看起来像绑定，但 FineReport 运行和结构解析不稳定。
        """

        if not re.search(r"<O\b[^>]*\bt=\"ds\"", cpt_xml, flags=re.S | re.I):
            return cpt_xml, []
        dataset_names = self._extract_dataset_names(cpt_xml)
        converted_fields: list[str] = []
        unresolved_count = 0

        def canonical_dscolumn(dataset_name: str, field_name: str) -> str:
            return (
                '<O t="DSColumn">\n'
                f'<Attributes dsName="{escape(dataset_name)}" columnName="{escape(field_name)}"/>\n'
                '<Condition class="com.fr.data.condition.ListCondition"/>\n'
                "<Complex/>\n"
                '<RG class="com.fr.report.cell.cellattr.core.group.FunctionGrouper"/>\n'
                "<Parameters/>\n"
                "</O>"
            )

        def infer_dataset(raw_dataset: str | None) -> str | None:
            dataset = (raw_dataset or "").strip()
            if dataset:
                return dataset
            if len(dataset_names) == 1:
                return dataset_names[0]
            return None

        def normalize_object(match: re.Match[str]) -> str:
            raw_value = (match.group("cdata") or match.group("text") or "").strip()
            if not raw_value.startswith("$$$"):
                return match.group(0)
            field_name = raw_value[3:].strip()
            dataset_name = infer_dataset(None)
            if not field_name or not dataset_name:
                nonlocal unresolved_count
                unresolved_count += 1
                return match.group(0)
            converted_fields.append(field_name)
            return canonical_dscolumn(dataset_name, field_name)

        def normalize_ds_node(match: re.Match[str]) -> str:
            attrs = match.group("attrs") or ""
            dataset_name = infer_dataset(self._regex_first(attrs, r'\b(?:ds|dsName|dataset)="([^"]+)"'))
            field_name = (
                self._regex_first(attrs, r'\b(?:name|columnName|field)="([^"]+)"')
                or ""
            ).strip()
            if not dataset_name or not field_name:
                nonlocal unresolved_count
                unresolved_count += 1
                return match.group(0)
            converted_fields.append(field_name)
            return canonical_dscolumn(dataset_name, field_name)

        next_xml = re.sub(
            r'<O\b[^>]*\bt="ds"[^>]*>\s*(?:<!\[CDATA\[(?P<cdata>\$\$\$.*?)]]>|(?P<text>\$\$\$.*?))\s*</O>',
            normalize_object,
            cpt_xml,
            flags=re.S | re.I,
        )
        next_xml = re.sub(
            r'<O\b[^>]*\bt="ds"[^>]*>\s*<DS\b(?P<attrs>[^>]*)/>\s*</O>',
            normalize_ds_node,
            next_xml,
            flags=re.S | re.I,
        )
        if not converted_fields:
            if unresolved_count:
                return next_xml, [f"检测到 {unresolved_count} 个 t=\"ds\" 伪数据绑定，但无法安全推断数据集或字段，已保留并等待下一轮修复。"]
            return next_xml, []
        sample = "、".join(converted_fields[:8])
        suffix = "等" if len(converted_fields) > 8 else ""
        next_xml, header_warnings = self._restore_duplicate_header_dataset_bindings(next_xml)
        warnings = [f"已将 {len(converted_fields)} 个伪数据绑定规范为 FineReport DSColumn：{sample}{suffix}。"]
        if unresolved_count:
            warnings.append(f"另有 {unresolved_count} 个伪数据绑定缺少数据集或字段，仍需模型继续修复。")
        warnings.extend(header_warnings)
        return next_xml, warnings

    def _normalize_nested_dscolumn_objects(self, cpt_xml: str) -> tuple[str, list[str]]:
        """把 `<O><DSColumn>...</DSColumn></O>` 规范为 `<O t="DSColumn">...</O>`。"""

        converted_fields: list[str] = []

        def normalize(match: re.Match[str]) -> str:
            attrs = match.group("attrs") or ""
            body = (match.group("body") or "").strip()
            dataset = self._regex_first(body, r'\bdsName="([^"]+)"') or ""
            field = self._regex_first(body, r'\bcolumnName="([^"]+)"') or ""
            if field:
                converted_fields.append(field)
            if 't="DSColumn"' in attrs or "t='DSColumn'" in attrs:
                return match.group(0)
            return f'<O t="DSColumn">\n{body}\n</O>'

        next_xml = re.sub(
            r'<O\b(?P<attrs>(?:(?!\bt=)[^>])*)>\s*<DSColumn>\s*(?P<body>.*?)\s*</DSColumn>\s*</O>',
            normalize,
            cpt_xml,
            flags=re.S | re.I,
        )
        if not converted_fields:
            return cpt_xml, []
        sample = "、".join(converted_fields[:8])
        suffix = "等" if len(converted_fields) > 8 else ""
        return next_xml, [f"已将 {len(converted_fields)} 个嵌套 DSColumn 规范为 FineReport 原生写法：{sample}{suffix}。"]

    def _restore_duplicate_header_dataset_bindings(self, cpt_xml: str) -> tuple[str, list[str]]:
        cells = self._extract_cell_blocks(cpt_xml)
        if not cells:
            return cpt_xml, []
        by_position = {(int(item["c"]), int(item["r"])): item for item in cells}
        restored: list[str] = []
        next_xml = cpt_xml
        for (column, row), item in sorted(by_position.items()):
            raw = str(item.get("raw") or "")
            field = self._regex_first(raw, r'\bcolumnName="([^"]+)"')
            if not field:
                continue
            below = by_position.get((column, row + 1))
            if not below:
                continue
            below_field = self._regex_first(str(below.get("raw") or ""), r'\bcolumnName="([^"]+)"')
            if below_field != field:
                continue
            fixed_raw = re.sub(
                r"<O\b[^>]*\bt=\"DSColumn\"[^>]*>.*?</O>",
                f"<O>\n<![CDATA[{field}]]></O>",
                raw,
                count=1,
                flags=re.S | re.I,
            )
            fixed_raw = re.sub(r"<Expand\b[^>]*/>", "<Expand/>", fixed_raw, count=1, flags=re.S | re.I)
            if fixed_raw == raw:
                continue
            next_xml = next_xml.replace(raw, fixed_raw, 1)
            restored.append(self._cell_address(column, row))
        if not restored:
            return cpt_xml, []
        return next_xml, [f"已将疑似误绑定的表头单元格恢复为静态文本：{', '.join(restored[:8])}。"]

    def _extract_dataset_names(self, cpt_xml: str) -> list[str]:
        names: list[str] = []
        seen: set[str] = set()
        for match in re.finditer(r"<TableData\b(?P<attrs>[^>]*)>", cpt_xml, flags=re.S | re.I):
            attrs = match.group("attrs")
            name_match = re.search(r'\bname="([^"]+)"', attrs)
            if not name_match:
                continue
            name = name_match.group(1).strip()
            if not name or name in seen:
                continue
            seen.add(name)
            names.append(name)
        return names

    def _normalize_operations(self, result: dict[str, Any]) -> list[dict[str, Any]]:
        operations = result.get("operations")
        normalized: list[dict[str, Any]] = []
        if isinstance(operations, list):
            for item in operations[:50]:
                if not isinstance(item, dict):
                    continue
                op_type = str(item.get("operationType") or "")
                if op_type == "file_edit":
                    normalized.append(dict(item))
                    continue
                if op_type in {"write_cpt_full", "full_replace"}:
                    next_item = dict(item)
                    next_item["operationType"] = "write_cpt_full"
                    normalized.append(next_item)
        if result.get("finalCptXml") and not normalized:
            normalized.append(
                {
                    "operationType": "write_cpt_full",
                    "summary": "整份 CPT WorkBook 重写",
                    "riskLevel": "high",
                    "payload": {"source": "finalCptXml"},
                }
            )
        return normalized

    async def _read_attachments(
        self,
        files: list[UploadFile],
        *,
        context: dict[str, Any] | None = None,
        autonomy_mode: str = "high",
    ) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for file in files[:8]:
            content = await file.read()
            filename = file.filename or "未命名附件"
            lower = filename.lower()
            try:
                if lower.endswith((".xlsx", ".xlsm", ".xls")):
                    analysis = excel_analyzer.analyze(content, filename)
                    result.append({"fileName": filename, "type": "excel", "analysis": analysis.model_dump(mode="json")})
                elif lower.endswith(".docx"):
                    result.append({"fileName": filename, "type": "word", "text": self._read_docx_text(content)})
                elif lower.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp")):
                    result.append(await self._read_image_context(filename, file.content_type, content, context=context or {}, autonomy_mode=autonomy_mode))
                else:
                    result.append({"fileName": filename, "type": "binary", "size": len(content), "note": "暂未结构化解析该附件类型。"})
            except Exception as exc:
                result.append({"fileName": filename, "type": "error", "error": str(exc)})
        return result

    async def _read_image_context(
        self,
        filename: str,
        content_type: str | None,
        content: bytes,
        *,
        context: dict[str, Any],
        autonomy_mode: str,
    ) -> dict[str, Any]:
        mime_type = content_type or self._guess_image_mime_type(filename)
        item: dict[str, Any] = {
            "fileName": filename,
            "type": "image",
            "contentType": mime_type,
            "size": len(content),
        }
        if not mime_type.startswith("image/"):
            item["warning"] = "文件扩展名像图片，但 contentType 不是 image/*，已跳过视觉解析。"
            return item
        if len(content) > 8 * 1024 * 1024:
            item["warning"] = "图片超过 8MB，本轮先保留附件信息，避免多模态请求过大。"
            return item

        try:
            level = self._vision_model_level(context, autonomy_mode)
            capability = self._vision_model_capability(context, autonomy_mode)
            llm = await LLMFactory.get_multimodal_model_by_level(
                level=level,
                capability=capability,
                model_types=["chat", "vision"],
                temperature=0,
                max_tokens=1600,
                streaming=False,
                enable_reasoning=False,
            )
            base64_image = base64.b64encode(content).decode("utf-8")
            messages = [
                SystemMessage(
                    content=(
                        "你是 FineReport 报表助手的图片理解工具。"
                        "请把图片里和报表修改有关的信息提取成简洁中文上下文，不要编造。"
                        "重点关注：界面报错、预览效果、单元格位置、表头、数据、用户标注、截图中可见的异常。"
                    )
                ),
                HumanMessage(
                    content=[
                        {
                            "type": "text",
                            "text": (
                                "请解析这张附件图片，输出 5-12 条要点。"
                                "如果是报表截图，请说明可见结构、异常位置和可能需要修改的对象。"
                            ),
                        },
                        {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{base64_image}"}},
                    ]
                ),
            ]
            response = await llm.ainvoke(messages)
            content_text = getattr(response, "content", "")
            if isinstance(content_text, list):
                content_text = "\n".join(str(part) for part in content_text)
            item["imageSummary"] = self._compact(str(content_text).strip(), 6000)
            item["modelSelection"] = {"level": level, "capability": capability}
        except Exception as exc:
            item["warning"] = f"图片已接收，但当前没有可用多模态模型完成解析：{LLMFactory.describe_invocation_error(exc)}"
        return item

    def _vision_model_level(self, context: dict[str, Any], autonomy_mode: str) -> int:
        raw_level = context.get("modelLevel") or context.get("model_level") or context.get("selectedModelLevel")
        try:
            level = int(raw_level)
            if 1 <= level <= 4:
                return level
        except (TypeError, ValueError):
            pass
        return 2 if (autonomy_mode or "high") == "high" else 3

    def _vision_model_capability(self, context: dict[str, Any], autonomy_mode: str) -> str:
        raw = str(context.get("modelCapability") or context.get("model_capability") or "").strip()
        if raw:
            return raw
        return "complex-reasoning" if (autonomy_mode or "high") == "high" else "general"

    def _guess_image_mime_type(self, filename: str) -> str:
        lower = filename.lower()
        if lower.endswith(".jpg") or lower.endswith(".jpeg"):
            return "image/jpeg"
        if lower.endswith(".webp"):
            return "image/webp"
        if lower.endswith(".gif"):
            return "image/gif"
        if lower.endswith(".bmp"):
            return "image/bmp"
        return "image/png"

    def _read_docx_text(self, content: bytes) -> str:
        with zipfile.ZipFile(BytesIO(content)) as archive:
            chunks: list[str] = []
            for name in archive.namelist():
                if not name.startswith("word/") or not name.endswith(".xml"):
                    continue
                if name not in {"word/document.xml"} and not name.startswith("word/header") and not name.startswith("word/footer"):
                    continue
                xml = archive.read(name).decode("utf-8", errors="ignore")
                chunks.extend(re.findall(r"<w:t[^>]*>(.*?)</w:t>", xml, flags=re.S))
        text = "\n".join(re.sub(r"<[^>]+>", "", item) for item in chunks)
        return self._compact(text, 20000)

    def _compact_structure(self, structure: Any) -> dict[str, Any]:
        parameter_widgets = []
        parameter_panel = getattr(getattr(structure, "document", None), "parameterPanel", None)
        if parameter_panel:
            parameter_widgets = [item.model_dump(mode="json") for item in list(parameter_panel.widgets or [])[:80]]
        return {
            "objectPath": structure.objectPath,
            "reportPath": structure.reportPath,
            "fileName": structure.fileName,
            "summary": structure.summary.model_dump(mode="json"),
            "datasets": [item.model_dump(mode="json") for item in structure.datasets[:30]],
            "parameters": parameter_widgets,
            "warnings": structure.warnings,
        }

    def _build_workbook_editing_context(self, source_xml: str) -> dict[str, Any]:
        return {
            "policy": [
                "预览中的展开单元格通常不是独立模板节点；例如预览 B5 通常对应 CPT 模板 <C c=\"1\" r=\"4\">。",
                "隐藏整行/整列应优先使用当前 CPT 已有的原生隐藏配置表达，例如 ReportPageAttr 下的 HR/HC 节点，并同步检查 ColumnWidth/RowHeight 是否被设计器置 0。",
                "设计器隐藏列的真实样本是组合写法：ReportPageAttr 写 HC 范围，ColumnWidth 对应列宽置 0；不要只改其中一个就断言完成。",
                "用户说第一列、第二列、A列、B列时，默认按模板设计坐标处理；隐藏整列需要同时观察当前 CPT 的原生隐藏节点和尺寸节点，按当前文件已有写法保持一致。",
                "修改日期/数字显示格式时必须保留原单元格的数据绑定/DSColumn/公式主体，只替换或补充格式相关 XML。",
                "如果预览结果与预期不一致，应同时检查单元格绑定、单元格格式、数据集最终输出字段和参考报表写法，再选择改格式、改绑定、改 SQL 或完整 WorkBook。",
                "修改数据展示字段时，不要把样例值写死到单元格；应修改 TableData/Query 或 DSColumn 绑定。",
                "修改会影响用户输入、隐藏列、日期拼接或字段绑定时，必须同步检查 ReportWriteAttr；填报写回公式不能继续引用已隐藏或语义已变化的旧单元格。",
            ],
            "nativeLayoutState": self._extract_native_layout_state(source_xml),
            "dimensions": self._extract_dimension_context(source_xml),
            "dataCells": self._extract_data_cell_context(source_xml),
            "datasets": self._extract_dataset_context(source_xml),
            "writeBack": self._extract_writeback_context(source_xml),
        }

    def _extract_native_layout_state(self, source_xml: str) -> dict[str, Any]:
        report_page_match = re.search(r"<ReportPageAttr\b[^>]*(?:/>|>.*?</ReportPageAttr>)", source_xml, flags=re.S | re.I)
        report_page_xml = report_page_match.group(0) if report_page_match else ""
        hidden_columns = [
            {"from": int(match.group(1)), "to": int(match.group(2)), "rawXml": match.group(0)}
            for match in re.finditer(r"<HC\b(?=[^>]*\bF=\"(\d+)\")(?=[^>]*\bT=\"(\d+)\")[^>]*/>", report_page_xml, flags=re.S | re.I)
        ]
        hidden_rows = [
            {"from": int(match.group(1)), "to": int(match.group(2)), "rawXml": match.group(0)}
            for match in re.finditer(r"<HR\b(?=[^>]*\bF=\"(\d+)\")(?=[^>]*\bT=\"(\d+)\")[^>]*/>", report_page_xml, flags=re.S | re.I)
        ]
        return {
            "reportPageAttrXml": self._compact(report_page_xml, 12000) if report_page_xml else None,
            "hiddenColumns": hidden_columns,
            "hiddenRows": hidden_rows,
            "note": "F/T 为 FineReport XML 中的 0 基范围。修改隐藏行列时优先沿用当前 CPT 的 HR/HC 表达，并同步检查 ColumnWidth/RowHeight；如果当前文件没有相关节点，应参考同类 CPT 或返回完整 WorkBook 修改并要求预览验证。",
        }

    def _extract_dimension_context(self, source_xml: str) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for tag in ("ColumnWidth", "RowHeight"):
            match = re.search(rf"<{tag}\b([^>]*)>\s*<!\[CDATA\[(.*?)]]>\s*</{tag}>", source_xml, flags=re.S | re.I)
            if not match:
                continue
            values = [item.strip() for item in match.group(2).split(",")]
            result[tag] = {
                "attributes": match.group(1).strip(),
                "values": values[:120],
                "note": "values 为 0 基列/行顺序；第一列对应 values[0]。",
                "rawXml": self._compact(match.group(0), 8000),
            }
        return result

    def _extract_data_cell_context(self, source_xml: str) -> list[dict[str, Any]]:
        cells: list[dict[str, Any]] = []
        for match in re.finditer(r"<C\b[^>]*(?:/>|>.*?</C>)", source_xml, flags=re.S | re.I):
            block = match.group(0)
            attrs = re.match(r"<C\b([^>]*)", block, flags=re.S | re.I)
            if not attrs:
                continue
            column_match = re.search(r'\bc="(\d+)"', attrs.group(1))
            row_match = re.search(r'\br="(\d+)"', attrs.group(1))
            if not column_match or not row_match:
                continue
            is_interesting = any(
                marker in block
                for marker in ("t=\"DSColumn\"", "DateFormat", "<Visible", "<Widget", "year_val", "month_day", "zdata")
            )
            if not is_interesting:
                continue
            column = int(column_match.group(1)) + 1
            row = int(row_match.group(1)) + 1
            cells.append(
                {
                    "address": f"{self._column_label(column)}{row}",
                    "xmlCoordinate": {"c": column - 1, "r": row - 1},
                    "dataset": self._regex_first(block, r'\bdsName="([^"]+)"'),
                    "field": self._regex_first(block, r'\bcolumnName="([^"]+)"'),
                    "expandDir": self._regex_first(block, r"<Expand\b[^>]*\bdir=\"([^\"]+)\""),
                    "hasVisibleFalse": bool(re.search(r"<Visible\b[^>]*\bvisible=\"false\"", block, flags=re.I)),
                    "hasDateFormat": "DateFormat" in block,
                    "rawXml": self._compact(block, 6000),
                }
            )
            if len(cells) >= 120:
                break
        return cells

    def _extract_dataset_context(self, source_xml: str) -> list[dict[str, Any]]:
        datasets: list[dict[str, Any]] = []
        for match in re.finditer(r"<TableData\b(?=[^>]*\bname=\"([^\"]+)\")[^>]*(?:/>|>.*?</TableData>)", source_xml, flags=re.S | re.I):
            block = match.group(0)
            query_match = re.search(r"<Query\b[^>]*>\s*<!\[CDATA\[(.*?)]]>\s*</Query>", block, flags=re.S | re.I)
            query = query_match.group(1).strip() if query_match else ""
            datasets.append(
                {
                    "name": match.group(1),
                    "querySql": self._compact(query, 30000),
                    "columnsMentioned": sorted(set(re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", query)))[:200],
                    "rawXml": self._compact(block, 40000),
                }
            )
            if len(datasets) >= 20:
                break
        return datasets

    def _extract_writeback_context(self, source_xml: str) -> dict[str, Any]:
        match = re.search(r"<ReportWriteAttr\b[^>]*(?:/>|>.*?</ReportWriteAttr>)", source_xml, flags=re.S | re.I)
        if not match:
            return {"available": False, "note": "当前 CPT 未发现 ReportWriteAttr。"}
        write_xml = match.group(0)
        formulas = sorted(set(re.findall(r"\b(?:CONCATENATE|CONCAT|FORMAT|DATE|YEAR|MONTH|DAY)\s*\([^<>]{1,240}\)", write_xml, flags=re.I)))
        cell_refs = sorted(set(re.findall(r"\b[A-Z]{1,3}\d+\b", write_xml)))
        return {
            "available": True,
            "formulaSamples": formulas[:30],
            "cellRefs": cell_refs[:80],
            "rawXml": self._compact(write_xml, 30000),
            "note": "如果修改单元格显示、隐藏列、日期拼接或填报字段绑定，ReportWriteAttr 中相关公式和单元格引用也要同步调整。",
        }

    def _column_label(self, column: int) -> str:
        label = ""
        current = max(1, column)
        while current:
            current, remainder = divmod(current - 1, 26)
            label = chr(65 + remainder) + label
        return label

    def _regex_first(self, text: str, pattern: str) -> str | None:
        match = re.search(pattern, text, flags=re.S | re.I)
        return match.group(1) if match else None

    async def _safe_candidate_audit(
        self,
        *,
        source_xml: str,
        candidate_xml: str,
        request: str,
        db: AsyncSession | None,
        user_id: int | None,
        run_sql: bool = False,
    ) -> dict[str, Any]:
        try:
            return await self._audit_candidate_cpt(
                source_xml=source_xml,
                candidate_xml=candidate_xml,
                request=request,
                db=db,
                user_id=user_id,
                run_sql=run_sql,
            )
        except Exception as exc:
            return {"status": "audit_failed", "issues": [str(exc)], "warnings": []}

    async def _audit_candidate_cpt(
        self,
        *,
        source_xml: str,
        candidate_xml: str,
        request: str,
        db: AsyncSession | None,
        user_id: int | None,
        run_sql: bool = False,
    ) -> dict[str, Any]:
        issues: list[str] = []
        warnings: list[str] = []
        facts: dict[str, Any] = {}

        if source_xml == candidate_xml:
            issues.append("候选 CPT 与源文件完全一致，没有产生实际修改")

        pseudo_count = len(re.findall(r"<O\b[^>]*\bt=\"ds\"", candidate_xml, flags=re.S | re.I))
        if pseudo_count:
            issues.append(f"仍存在 {pseudo_count} 个 t=\"ds\" 伪数据绑定，必须改为 FineReport DSColumn")
        nested_dscolumn_count = len(re.findall(r"<O\b(?:(?!\bt=)[^>])*>\s*<DSColumn\b", candidate_xml, flags=re.S | re.I))
        if nested_dscolumn_count:
            issues.append(f"仍存在 {nested_dscolumn_count} 个嵌套 DSColumn，必须规范为 <O t=\"DSColumn\"> 写法")

        dataset_names = set(self._extract_dataset_names(candidate_xml))
        ds_bindings = self._extract_ds_column_bindings(candidate_xml)
        facts["datasetCount"] = len(dataset_names)
        facts["dsColumnCount"] = len(ds_bindings)
        missing_dataset_bindings = sorted({item["dataset"] for item in ds_bindings if item["dataset"] not in dataset_names})
        if missing_dataset_bindings:
            issues.append(f"存在绑定到不存在数据集的单元格：{', '.join(missing_dataset_bindings[:8])}")

        literal_bindings = self._extract_literal_dataset_binding_cells(candidate_xml)
        if literal_bindings:
            sample = "、".join(item["address"] for item in literal_bindings[:8])
            issues.append(f"存在看起来像数据列但实际是普通文本的单元格：{sample}")

        hidden_warnings = self._audit_hidden_layout_consistency(candidate_xml)
        warnings.extend(hidden_warnings)

        writeback_issues = self._audit_writeback_cell_references(candidate_xml)
        issues.extend(writeback_issues)

        if run_sql and db is not None and user_id is not None:
            sql_report = await self._audit_dataset_result_columns(candidate_xml, db=db, user_id=user_id)
            facts["datasetSql"] = sql_report.get("facts") or {}
            issues.extend(sql_report.get("issues") or [])
            warnings.extend(sql_report.get("warnings") or [])
        elif run_sql:
            warnings.append("当前调用缺少数据库会话，无法执行数据集 SQL 结果列审计。")

        if re.search(r"填报|写回|提交|录入|修改数据", request or "") and "ReportWriteAttr" not in candidate_xml:
            warnings.append("用户提到了填报/写回，但候选 CPT 中没有 ReportWriteAttr，请确认是否确实不需要填报属性。")

        return {
            "status": "failed" if issues else "passed",
            "issues": issues,
            "warnings": self._dedupe_texts(warnings),
            "facts": facts,
        }

    def _extract_ds_column_bindings(self, cpt_xml: str) -> list[dict[str, str]]:
        cells_by_range = {
            (int(item["c"]), int(item["r"])): item
            for item in self._extract_cell_blocks(cpt_xml)
            if str(item.get("c") or "").isdigit() and str(item.get("r") or "").isdigit()
        }
        bindings: list[dict[str, str]] = []
        for (column, row), item in sorted(cells_by_range.items()):
            raw = str(item.get("raw") or "")
            blocks = re.findall(r'<O\b[^>]*\bt="DSColumn"[^>]*>.*?</O>', raw, flags=re.S | re.I)
            blocks.extend(re.findall(r'<O\b(?:(?!\bt=)[^>])*>\s*<DSColumn\b.*?</DSColumn>\s*</O>', raw, flags=re.S | re.I))
            for block in blocks:
                dataset = html_unescape(self._regex_first(block, r'\bdsName="([^"]+)"') or "").strip()
                field = html_unescape(self._regex_first(block, r'\bcolumnName="([^"]+)"') or "").strip()
                if dataset or field:
                    bindings.append({"address": self._cell_address(column, row), "dataset": dataset, "field": field})
        return bindings

    def _extract_literal_dataset_binding_cells(self, cpt_xml: str) -> list[dict[str, str]]:
        result: list[dict[str, str]] = []
        for item in self._extract_cell_blocks(cpt_xml):
            raw = str(item.get("raw") or "")
            if 't="DSColumn"' in raw or "<DSColumn" in raw or 't="formula"' in raw:
                continue
            text = self._regex_first(raw, r"<O(?:\s[^>]*)?>\s*<!\[CDATA\[(.*?)]]>\s*</O>") or ""
            text = text.strip()
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*\.G\([^)]+\)", text) or text.startswith("$$$"):
                result.append(
                    {
                        "address": self._cell_address(int(item["c"]), int(item["r"])),
                        "text": text,
                    }
                )
        return result

    async def _audit_dataset_result_columns(
        self,
        cpt_xml: str,
        *,
        db: AsyncSession,
        user_id: int,
    ) -> dict[str, Any]:
        issues: list[str] = []
        warnings: list[str] = []
        facts: dict[str, Any] = {}
        bindings_by_dataset: dict[str, set[str]] = {}
        for binding in self._extract_ds_column_bindings(cpt_xml):
            if binding["dataset"] and binding["field"]:
                bindings_by_dataset.setdefault(binding["dataset"], set()).add(binding["field"])

        for dataset in self._extract_table_data_queries(cpt_xml):
            dataset_name = dataset["name"]
            database_name = dataset.get("databaseName") or ""
            bound_fields = sorted(bindings_by_dataset.get(dataset_name) or [])
            if not bound_fields:
                continue
            connection_config, connection_warning = await self._resolve_dataset_connection_config(
                db=db,
                user_id=user_id,
                database_name=database_name,
            )
            if connection_warning:
                warnings.append(connection_warning)
            if database_name and not connection_config:
                warnings.append(f"数据集 {dataset_name} 未匹配到平台同名查库连接，跳过绑定结果列审计。")
                continue
            executable_sql = self._make_report_sql_executable_for_smoke_test(dataset["sql"])
            try:
                if connection_config:
                    db_type = str(connection_config.get("db_type") or "sqlserver").lower()
                    sample_sql = sqlserver_query_service._limit_preview_sql(
                        executable_sql,
                        min(settings.FR_AI_SQLSERVER_MAX_ROWS, 20),
                        db_type,
                    )
                    _rows, columns = await asyncio.to_thread(
                        sqlserver_query_service._execute_sample_query_with_config,
                        sample_sql,
                        connection_config,
                        min(settings.FR_AI_SQLSERVER_MAX_ROWS, 20),
                    )
                else:
                    _rows, columns = await asyncio.to_thread(sqlserver_query_service._execute_sample_query, executable_sql)
            except Exception as exc:
                issues.append(f"数据集 {dataset_name} SQL 无法执行，不能确认单元格绑定：{exc}")
                continue
            available = {html_unescape(str(column)).strip().lower() for column in columns if str(column).strip()}
            missing = [field for field in bound_fields if field.lower() not in available]
            facts[dataset_name] = {
                "boundFieldCount": len(bound_fields),
                "resultColumnCount": len(columns),
                "missingFields": missing[:20],
            }
            if missing:
                issues.append(f"数据集 {dataset_name} 绑定字段不在 SQL 返回列中：{', '.join(missing[:12])}")
        return {"issues": issues, "warnings": warnings, "facts": facts}

    def _audit_hidden_layout_consistency(self, cpt_xml: str) -> list[str]:
        warnings: list[str] = []
        hidden_columns = self._hidden_layout_ranges(cpt_xml, "HC")
        column_widths = self._dimension_values(cpt_xml, "ColumnWidth")
        for start, end in hidden_columns:
            for index in range(start, end + 1):
                if index < len(column_widths) and column_widths[index] != "0":
                    warnings.append(f"隐藏列 {self._column_label(index + 1)} 的 ColumnWidth 不是 0，预览或设计器可能显示不一致。")
        hidden_rows = self._hidden_layout_ranges(cpt_xml, "HR")
        row_heights = self._dimension_values(cpt_xml, "RowHeight")
        for start, end in hidden_rows:
            for index in range(start, end + 1):
                if index < len(row_heights) and row_heights[index] != "0":
                    warnings.append(f"隐藏行 {index + 1} 的 RowHeight 不是 0，预览或设计器可能显示不一致。")
        return warnings

    def _dimension_values(self, cpt_xml: str, tag: str) -> list[str]:
        match = re.search(rf"<{tag}\b[^>]*>.*?</{tag}>", cpt_xml, flags=re.S | re.I)
        if not match:
            return []
        cdata = self._regex_first(match.group(0), r"<!\[CDATA\[(.*?)]]>") or ""
        return [item.strip() for item in cdata.split(",")]

    def _audit_writeback_cell_references(self, cpt_xml: str) -> list[str]:
        match = re.search(r"<ReportWriteAttr\b[^>]*(?:/>|>.*?</ReportWriteAttr>)", cpt_xml, flags=re.S | re.I)
        if not match:
            return []
        existing_cells = {
            self._cell_address(int(item["c"]), int(item["r"]))
            for item in self._extract_cell_blocks(cpt_xml)
            if str(item.get("c") or "").isdigit() and str(item.get("r") or "").isdigit()
        }
        refs = sorted(set(re.findall(r"\b[A-Z]{1,3}\d+\b", match.group(0))))
        missing = [ref for ref in refs if ref not in existing_cells]
        if missing:
            return [f"填报属性引用了不存在的单元格：{', '.join(missing[:12])}"]
        return []

    def _dedupe_texts(self, values: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            text = str(value).strip()
            if not text or text in seen:
                continue
            seen.add(text)
            result.append(text)
        return result

    async def _validate_and_normalize_dataset_sql(
        self,
        cpt_xml: str,
        *,
        db: AsyncSession | None = None,
        user_id: int | None = None,
    ) -> tuple[str, list[str]]:
        warnings: list[str] = []
        next_xml = cpt_xml
        for dataset in self._extract_table_data_queries(next_xml):
            dataset_name = dataset["name"]
            database_name = dataset.get("databaseName") or ""
            original_sql = dataset["sql"]
            normalized_sql = self._normalize_report_dataset_sql(original_sql)
            if normalized_sql != original_sql:
                next_xml = next_xml.replace(original_sql, normalized_sql, 1)
                warnings.append(f"已规范化数据集 {dataset_name} 的 SQL 字段写法，避免单元格列号混入字段名。")

            executable_sql = self._make_report_sql_executable_for_smoke_test(normalized_sql)
            safety_errors = sqlserver_query_service._validate_readonly_sql(executable_sql)
            if safety_errors:
                raise ValueError(f"数据集 {dataset_name} SQL 校验未通过：" + "；".join(safety_errors))
            connection_config, connection_warning = await self._resolve_dataset_connection_config(
                db=db,
                user_id=user_id,
                database_name=database_name,
            )
            if connection_warning:
                warnings.append(connection_warning)
            if database_name and not connection_config and db is not None and user_id is not None:
                warnings.append(
                    f"数据集 {dataset_name} 使用 FineReport 连接 {database_name}，但平台未匹配到同名查库连接，已跳过后端 SQL 执行校验。"
                )
                continue
            try:
                if connection_config:
                    db_type = str(connection_config.get("db_type") or "sqlserver").lower()
                    sample_sql = sqlserver_query_service._limit_preview_sql(
                        executable_sql,
                        settings.FR_AI_SQLSERVER_MAX_ROWS,
                        db_type,
                    )
                    rows, columns = await asyncio.to_thread(
                        sqlserver_query_service._execute_sample_query_with_config,
                        sample_sql,
                        connection_config,
                        settings.FR_AI_SQLSERVER_MAX_ROWS,
                    )
                else:
                    rows, columns = await asyncio.to_thread(sqlserver_query_service._execute_sample_query, executable_sql)
            except Exception as exc:
                raise ValueError(f"数据集 {dataset_name} SQL 执行失败：{exc}") from exc

            if not columns:
                warnings.append(f"数据集 {dataset_name} SQL 可执行，但未返回字段信息。")
            elif not rows:
                warnings.append(f"数据集 {dataset_name} SQL 可执行但样例返回 0 行，请在预览里核对筛选条件。")
            warnings.extend(self._validate_dataset_column_bindings(next_xml, dataset_name, columns))
            warnings.extend(await self._diagnose_default_parameter_result(dataset_name, normalized_sql, next_xml))
        return next_xml, warnings

    def _validate_dataset_column_bindings(
        self,
        cpt_xml: str,
        dataset_name: str,
        columns: list[str],
    ) -> list[str]:
        available_columns = {
            html_unescape(str(column)).strip().lower()
            for column in columns
            if str(column).strip()
        }
        if not available_columns:
            return []

        bound_fields: list[str] = []
        for binding in self._extract_ds_column_bindings(cpt_xml):
            if binding["dataset"] != dataset_name:
                continue
            field = binding["field"]
            if field and field not in bound_fields:
                bound_fields.append(field)

        missing = [field for field in bound_fields if field.lower() not in available_columns]
        if missing:
            available_sample = "、".join(sorted(columns)[:20])
            missing_sample = "、".join(missing[:12])
            raise ValueError(
                f"数据集 {dataset_name} 有单元格绑定了 SQL 结果中不存在的字段：{missing_sample}。"
                f"当前 SQL 返回字段包括：{available_sample}"
            )
        if bound_fields:
            return [f"已校验数据集 {dataset_name} 的 {len(bound_fields)} 个单元格绑定字段均存在于 SQL 结果列。"]
        return []

    async def _resolve_dataset_connection_config(
        self,
        *,
        db: AsyncSession | None,
        user_id: int | None,
        database_name: str,
    ) -> tuple[dict[str, Any] | None, str | None]:
        name = database_name.strip()
        if not name:
            return None, None
        if db is None or user_id is None:
            return None, f"数据集使用 FineReport 连接 {name}，但当前调用缺少数据库会话，已退回默认 SQL 校验连接。"
        connection, reason, _visible_connections = await fr_report_ai_operation_service._resolve_database_context_connection(
            db=db,
            user_id=user_id,
            database_names=[name],
        )
        if not connection:
            return None, reason
        return fr_report_ai_operation_service._database_connection_config(connection), reason

    def _extract_table_data_queries(self, cpt_xml: str) -> list[dict[str, str]]:
        datasets: list[dict[str, str]] = []
        for table_match in re.finditer(r'<TableData\b(?P<attrs>[^>]*)>.*?</TableData>', cpt_xml, flags=re.S | re.I):
            table_xml = table_match.group(0)
            attrs = table_match.group("attrs")
            name_match = re.search(r'\bname="([^"]+)"', attrs)
            database_name = self._extract_table_data_database_name(table_xml)
            sql_match = re.search(r"<Query\b[^>]*>\s*<!\[CDATA\[(?P<sql>.*?)]]>\s*</Query>", table_xml, flags=re.S | re.I)
            if not sql_match:
                continue
            datasets.append(
                {
                    "name": name_match.group(1) if name_match else "未命名数据集",
                    "databaseName": database_name or "",
                    "sql": sql_match.group("sql"),
                }
            )
        return datasets

    def _extract_table_data_database_name(self, table_xml: str) -> str | None:
        match = re.search(
            r"<DatabaseName>\s*(?:<!\[CDATA\[(?P<cdata>.*?)]]>|(?P<text>.*?))\s*</DatabaseName>",
            table_xml,
            flags=re.S | re.I,
        )
        if not match:
            return None
        return (match.group("cdata") or match.group("text") or "").strip()

    def _normalize_report_dataset_sql(self, sql: str) -> str:
        # 模型可能把单元格列号拼进字段引用，例如 p.[date]A；这在 SQL Server 中一定是非法语法。
        normalized = re.sub(r"(\[[A-Za-z_][A-Za-z0-9_]*\])([A-Z])\b", r"\1", sql)
        if re.search(r"\bCASE\s+WHEN\s+CHARINDEX\b", normalized, flags=re.I):
            return normalized
        return re.sub(
            r"CHARINDEX\(',' \+ CAST\((?P<field>.+?) AS NVARCHAR\(4000\)\) \+ ',', '(?P<labels>[^']*)'\)",
            self._wrap_charindex_order_expression,
            normalized,
            flags=re.S,
        )

    def _wrap_charindex_order_expression(self, match: re.Match[str]) -> str:
        expression = match.group(0)
        before = match.string[max(0, match.start() - 24) : match.start()].upper()
        if "CASE WHEN" in before:
            return expression
        return f"CASE WHEN {expression} > 0 THEN {expression} ELSE 999999 END"

    def _make_report_sql_executable_for_smoke_test(self, sql: str) -> str:
        executable = sql.strip().rstrip(";")
        executable = re.sub(r"\$\{if\([^{}]*\)\}", "", executable)
        executable = re.sub(
            r"'\$\{([A-Za-z_][A-Za-z0-9_]*)\}'",
            lambda match: self._sample_sql_literal(match.group(1)),
            executable,
        )
        executable = re.sub(
            r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}",
            lambda match: self._sample_sql_literal(match.group(1)),
            executable,
        )
        return executable

    async def _diagnose_default_parameter_result(self, dataset_name: str, sql: str, cpt_xml: str) -> list[str]:
        parameter_values = self._extract_parameter_default_values(cpt_xml)
        if not parameter_values:
            return []
        executable = self._make_report_sql_executable_with_values(sql, parameter_values)
        try:
            rows, _columns = await asyncio.to_thread(sqlserver_query_service._execute_sample_query, executable)
        except Exception as exc:
            return [f"数据集 {dataset_name} 使用当前参数默认值执行失败：{exc}"]
        if rows:
            return []

        diagnostics = [f"数据集 {dataset_name} 使用当前参数默认值返回 0 行，已继续检查底表和筛选条件。"]
        base_rows: list[dict[str, Any]] = []
        try:
            base_rows, _base_columns = await asyncio.to_thread(
                sqlserver_query_service._execute_sample_query,
                self._make_report_sql_executable_for_smoke_test(sql),
            )
        except Exception as exc:
            diagnostics.append(f"去掉参数后 SQL 仍执行失败：{exc}")
            return diagnostics
        if base_rows:
            diagnostics.append("去掉参数后能查到样例数据，说明当前默认参数或筛选条件把结果过滤空了。")
        else:
            diagnostics.append("去掉参数后仍没有样例数据，优先检查数据源表是否有数据、表名是否正确、固定 WHERE 条件是否过窄。")

        diagnostics.extend(self._diagnose_date_filters(sql, executable))
        return diagnostics

    def _make_report_sql_executable_with_values(self, sql: str, parameter_values: dict[str, str]) -> str:
        executable = sql.strip().rstrip(";")
        executable = re.sub(r"\$\{if\([^{}]*\)\}", "", executable)

        def literal(name: str) -> str:
            value = parameter_values.get(name, "")
            return "'" + str(value).replace("'", "''") + "'"

        executable = re.sub(r"'\$\{([A-Za-z_][A-Za-z0-9_]*)\}'", lambda match: literal(match.group(1)), executable)
        executable = re.sub(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}", lambda match: literal(match.group(1)), executable)
        return executable

    def _extract_parameter_default_values(self, cpt_xml: str) -> dict[str, str]:
        defaults: dict[str, str] = {}
        for widget_match in re.finditer(r"<InnerWidget\b[^>]*>.*?</InnerWidget>", cpt_xml, flags=re.S | re.I):
            widget_xml = widget_match.group(0)
            name = self._regex_first(widget_xml, r'<WidgetName\s+name="([^"]+)"')
            if not name:
                continue
            value_match = re.search(r"<widgetValue\b[^>]*>\s*<O[^>]*>\s*(?:<Attributes>\s*)?<!\[CDATA\[(.*?)]]>", widget_xml, flags=re.S | re.I)
            if not value_match:
                continue
            raw_value = value_match.group(1).strip()
            defaults[name] = self._evaluate_parameter_default(raw_value)
        return defaults

    def _evaluate_parameter_default(self, raw_value: str) -> str:
        value = str(raw_value or "").strip()
        today = datetime.now().date()
        if re.fullmatch(r"=TODAY\(\)", value, flags=re.I):
            return today.isoformat()
        month_delta_match = re.fullmatch(r"=MONTHDELTA\(TODAY\(\),\s*(-?\d+)\)", value, flags=re.I)
        if month_delta_match:
            return self._add_months(today, int(month_delta_match.group(1))).isoformat()
        return value[1:] if value.startswith("=") else value

    def _add_months(self, value: datetime.date, months: int) -> datetime.date:
        month_index = value.month - 1 + months
        year = value.year + month_index // 12
        month = month_index % 12 + 1
        day = min(value.day, self._days_in_month(year, month))
        return value.replace(year=year, month=month, day=day)

    def _days_in_month(self, year: int, month: int) -> int:
        if month == 12:
            next_month = datetime(year + 1, 1, 1).date()
        else:
            next_month = datetime(year, month + 1, 1).date()
        return (next_month - datetime(year, month, 1).date()).days

    def _diagnose_date_filters(self, original_sql: str, executable_sql: str) -> list[str]:
        diagnostics: list[str] = []
        alias_to_table = self._extract_sql_table_aliases(original_sql)
        for match in re.finditer(
            r"(?P<field>(?P<alias>[A-Za-z_][A-Za-z0-9_]*)\.(?:\[[^\]]+\]|[A-Za-z_][A-Za-z0-9_]*))\s+BETWEEN\s+'(?P<start>[^']*)'\s+AND\s+'(?P<end>[^']*)'",
            executable_sql,
            flags=re.I,
        ):
            alias = match.group("alias")
            table = alias_to_table.get(alias)
            if not table:
                continue
            field = match.group("field").split(".", 1)[1]
            query = (
                f"SELECT COUNT(1) AS row_count, MIN(TRY_CONVERT(date, {field})) AS min_value, "
                f"MAX(TRY_CONVERT(date, {field})) AS max_value FROM {table} "
                f"WHERE TRY_CONVERT(date, {field}) IS NOT NULL"
            )
            try:
                rows, _columns = sqlserver_query_service._execute_sample_query(query)
            except Exception:
                continue
            if not rows:
                continue
            row = rows[0]
            diagnostics.append(
                f"筛选字段 {alias}.{field} 的底表可用范围：{row.get('min_value')} 到 {row.get('max_value')}，"
                f"当前参数：{match.group('start')} 到 {match.group('end')}，底表总行数约 {row.get('row_count')}。"
            )
        return diagnostics

    def _extract_sql_table_aliases(self, sql: str) -> dict[str, str]:
        aliases: dict[str, str] = {}
        for match in re.finditer(
            r"\b(?:FROM|JOIN)\s+(?P<table>(?:\[[^\]]+\]|[A-Za-z_][A-Za-z0-9_]*)(?:\.(?:\[[^\]]+\]|[A-Za-z_][A-Za-z0-9_]*))?)\s+(?:AS\s+)?(?P<alias>[A-Za-z_][A-Za-z0-9_]*)\b",
            sql,
            flags=re.I,
        ):
            aliases[match.group("alias")] = match.group("table")
        return aliases

    def _sample_sql_literal(self, parameter_name: str) -> str:
        normalized = parameter_name.lower()
        if normalized.startswith(("end", "to")) or normalized in {"end_date", "finish_date"}:
            return "'2999-12-31'"
        if normalized.startswith(("start", "from")) or normalized in {"date", "record_date"}:
            return "'1900-01-01'"
        if any(token in normalized for token in ("date", "day", "month", "year")):
            return "'1900-01-01'"
        if normalized in {"page", "page_no", "limit", "offset"}:
            return "0"
        return "''"

    def _compact(self, value: Any, limit: int) -> Any:
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
        if len(text) <= limit:
            return value
        return text[:limit] + "\n...已截断展示，服务端已读取完整原文。"

    def _system_prompt(self) -> str:
        return (
            "你是 FineReport 报表专用高权限 Agent。你直接编辑 CPT XML，像维护结构化文件一样处理报表。"
            "你可以完整读取 CPT，并优先返回 oldText/newText 精确文件编辑；必要时才返回修改后的整份 WorkBook XML。"
            "本链路不使用旧 xml_patch/selector 写入器；file_edit 是源码级精确替换，不是抽象写入器操作。"
            "file_edit 的 oldText 必须来自当前 CPT 原文并尽量唯一，newText 只写替换后的对应 XML 片段。"
            "必须根据 reportLayoutContext 的单元格语义定位，不要把黄曲霉、不保黄曲霉等指标放错列。"
            "必须根据 databaseSourceContext 的真实字段和样例数据生成 SQL，不得编造 date/create_time 等字段。"
            "必须优先阅读 workbookEditingContext：它包含列宽、关键数据单元格原始 XML、数据集 SQL 和 FineReport 修改注意事项。"
            "如果用户要求隐藏整行或整列，优先使用 workbookEditingContext.nativeLayoutState 中当前 CPT 已有的 HR/HC 原生隐藏配置，并同步维护 ColumnWidth/RowHeight；不要只给单元格加 Visible=false。"
            "如果修改后预览结果不符合预期，必须重新观察单元格 XML、数据集 SQL、格式节点和参考写法，再返回新的 file_edit 或完整 WorkBook。"
            "预览里看到的 B5、A5 等通常是运行时扩展结果，真正模板节点要看 rawXml 里的 c/r 坐标和数据绑定。"
            "案例库是写入前的常规观察工具：每次准备修改 CPT 前都要调用 search_reference_cpt；案例只提供真实写法参考，不覆盖当前 CPT 和用户需求。"
            "检索到的案例只能作为参考写法，不能覆盖当前用户指令、当前 CPT 原文和真实数据库事实。"
            "如果要新增或替换数据集，应修改 CPT 中 TableDataMap 的真实 XML，而不是返回抽象的中间操作名。"
            "如果要改参数栏、下拉框、样式、填报、脚本，都直接修改对应 CPT XML。"
            "返回严格 JSON，不输出 Markdown。字段可包含 assistantMessage、operations、finalCptXml、warnings、validationFocus；operations 优先使用 file_edit。"
            "mini-shot：用户说“把 C3 改为市场下拉框，字典来自 ds1.market”，你应先看参数栏/单元格/数据集 XML，然后用 file_edit 替换对应控件和字典绑定节点。"
            "mini-shot：用户说“根据表 ncp_xxx 的 price1/price2 填到黄曲霉/不保黄曲霉”，你必须先用 schema 确认字段，再按表头语义把 price1 绑定到黄曲霉列、price2 绑定到不保黄曲霉列。"
            "所有面向用户说明用中文，简短、自然、不要模板腔。"
        )

    def _message(self, content: str) -> tuple[str, dict[str, Any]]:
        return "message_delta", {"content": content}

    def _tool_started(self, tool_name: str, summary: str) -> tuple[str, dict[str, Any]]:
        return "tool_started", {"toolName": tool_name, "summary": summary}

    def _tool_result(self, tool_name: str, summary: str, payload: dict[str, Any] | None = None) -> tuple[str, dict[str, Any]]:
        return "tool_result", {"toolName": tool_name, "summary": summary, "payload": payload or {}}

    def _final(
        self,
        status: str,
        assistant_message: str,
        object_path: str,
        warnings: list[str],
        errors: list[str],
        **extra: Any,
    ) -> tuple[str, dict[str, Any]]:
        return (
            "final_result",
            {
                "status": status,
                "assistantMessage": assistant_message,
                "objectPath": object_path,
                "warnings": warnings,
                "errors": errors,
                **extra,
            },
        )

    def _build_write_completion_message(
        self,
        *,
        status: str,
        object_path: str,
        version_no: int | None,
        preview_url: str | None,
        warnings: list[str],
        errors: list[str],
    ) -> str:
        version_text = f"v{version_no:04d}" if version_no else "新版本"
        if status == "success":
            lines = [
                f"改好了，已经写入 {version_text}。",
                f"路径：{object_path}",
                "FineReport 预览也返回了，可以打开核对真实效果。" if preview_url else "这次没有拿到预览地址，可以用右上角预览再核一下。",
            ]
            if warnings:
                lines.append(f"我顺手保留了 {len(warnings)} 条提示，展开风险里可以看细节。")
            return "\n".join(lines)
        if status == "preview_failed":
            lines = [
                f"CPT 已经写入 {version_text}，但预览校验还没过。",
                f"路径：{object_path}",
            ]
            if errors:
                lines.append(f"主要错误：{errors[0]}")
            lines.append("版本已经留住了，可以继续基于这个版本修。")
            return "\n".join(lines)
        return f"这次没有完成写入，路径：{object_path}"

    def _log(self, message: str) -> str:
        return f"{datetime.now().isoformat(timespec='seconds')} {message}"

    def _sse(self, event_name: str, payload: dict[str, Any]) -> str:
        return f"event: {event_name}\ndata: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"


fr_report_high_authority_agent_service = FrReportHighAuthorityAgentService()
