import hashlib
import json
import re
from datetime import datetime
from pathlib import PurePosixPath
from typing import Any
from uuid import uuid4

from sqlalchemy import text
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.models.agent.fr_report import (
    FrAiReportTask,
    FrReportExternalChangeLog,
    FrReportFileVersion,
    FrReportProject,
    FrReportSnapshot,
    FrReportStructureVersion,
)
from app.schemas.agent.fr_report.report_ai_operation import (
    FrReportExternalSyncResponse,
    FrReportFileVersionRead,
    FrReportProjectRead,
    FrReportRecycleResponse,
    FrReportStructureVersionRead,
    FrReportStructureRollbackResponse,
    FrReportVersionListResponse,
    FrReportVersionRollbackResponse,
)
from app.services.agent.fr_report.fr_minio_service import FrMinIOObjectStat, fr_minio_service
from app.services.agent.fr_report.preview_validator import preview_validator


REPORTLETS_ROOT = "webroot/APP/reportlets"


class FrReportVersionControlService:
    def normalize_target_object_path(
        self,
        *,
        report_name: str | None = None,
        target_folder: str | None = None,
        target_object_path: str | None = None,
        fallback_object_path: str | None = None,
    ) -> str:
        if target_object_path:
            return self._normalize_object_path(target_object_path)
        safe_name = self._normalize_report_name(report_name or self._name_from_object_path(fallback_object_path) or "AI生成报表")
        folder = self._normalize_folder(target_folder or self._folder_from_object_path(fallback_object_path) or f"{REPORTLETS_ROOT}/AI生成报表")
        return self._normalize_object_path(f"{folder}/{safe_name}")

    def reportlet_path(self, object_path: str) -> str:
        normalized = self._normalize_object_path(object_path)
        return normalized.removeprefix(f"{REPORTLETS_ROOT}/")

    async def list_versions(
        self,
        db: AsyncSession,
        user_id: int,
        object_path: str,
    ) -> FrReportVersionListResponse:
        normalized = self._normalize_object_path(object_path)
        self._assert_object_path_allowed(normalized)
        project = await self._get_project_by_object_path(db, user_id, normalized)
        if project is None:
            return FrReportVersionListResponse(project=None)
        structure_versions = (
            await db.exec(
                select(FrReportStructureVersion)
                .where(
                    FrReportStructureVersion.report_id == project.report_id,
                    FrReportStructureVersion.is_deleted == 0,
                )
                .order_by(FrReportStructureVersion.version_no.desc(), FrReportStructureVersion.id.desc())
            )
        ).all()
        file_versions = (
            await db.exec(
                select(FrReportFileVersion)
                .where(
                    FrReportFileVersion.report_id == project.report_id,
                    FrReportFileVersion.is_deleted == 0,
                )
                .order_by(FrReportFileVersion.version_no.desc(), FrReportFileVersion.id.desc())
            )
        ).all()
        conflict = await self.detect_external_conflict(db, project)
        return FrReportVersionListResponse(
            project=self._project_read(project),
            structureVersions=[self._structure_read(item) for item in structure_versions],
            fileVersions=[self._file_read(item) for item in file_versions],
            externalConflict=conflict,
        )

    async def save_snapshot_file_version(
        self,
        *,
        db: AsyncSession,
        user_id: int,
        snapshot: FrReportSnapshot,
        cpt_bytes: bytes,
        dsl_payload: dict[str, Any],
        operations: list[dict[str, Any]],
        generation_log: list[str],
        target_object_path: str,
        conflict_strategy: str = "abort",
        preview_url: str | None = None,
        warnings: list[str] | None = None,
        errors: list[str] | None = None,
    ) -> tuple[FrReportProject, FrReportStructureVersion | None, FrReportFileVersion | None, dict[str, Any] | None]:
        normalized = self._normalize_object_path(target_object_path)
        self._assert_object_path_allowed(normalized)
        await self._lock_object_path(db, normalized)
        if conflict_strategy not in {"abort", "import_external", "archive_and_overwrite"}:
            raise ValueError("未知的冲突处理策略")
        project = await self._ensure_project(db, user_id, normalized, snapshot)
        latest_file = await self._latest_file_version(db, project.report_id)
        current_stat = await fr_minio_service.stat_object_safe(normalized, include_hash=True)
        conflict = self._build_conflict(project, latest_file, current_stat)
        if conflict and conflict_strategy == "abort":
            await self._record_conflict(db, project, latest_file, current_stat, conflict)
            return project, None, None, conflict

        if conflict and conflict_strategy == "import_external":
            imported = await self._archive_existing_object(
                db=db,
                user_id=user_id,
                project=project,
                current_stat=current_stat,
                source_type="external_imported",
                structure_version_id=None,
                manifest_extra={"reason": "检测到 FineReport 设计器外部修改，先同步为文件版本。"},
            )
            latest_file = imported

        if conflict and conflict_strategy == "archive_and_overwrite":
            archived = await self._archive_existing_object(
                db=db,
                user_id=user_id,
                project=project,
                current_stat=current_stat,
                source_type="external_archived_before_overwrite",
                structure_version_id=None,
                manifest_extra={"reason": "覆盖前自动归档当前目标 CPT，避免 FineReport 设计器修改丢失。"},
            )
            latest_file = archived

        structure_version = await self._ensure_structure_version(db, user_id, project, snapshot, operations)
        version_no = await self._next_file_version_no(db, project.report_id)
        archive_base = self._archive_base_path(normalized)
        archive_dir = f"{archive_base}/v{version_no:04d}"
        target_hash = hashlib.sha256(cpt_bytes).hexdigest()
        source_hash = current_stat.content_hash if current_stat.exists else None
        manifest = {
            "reportId": project.report_id,
            "structureVersionId": structure_version.structure_version_id,
            "fileVersionNo": version_no,
            "currentObjectPath": normalized,
            "archiveDir": archive_dir,
            "sourceHash": source_hash,
            "targetHash": target_hash,
            "sourceEtag": current_stat.etag,
            "sourceLastModified": current_stat.last_modified,
            "generatedAt": datetime.now().isoformat(timespec="seconds"),
            "conflictStrategy": conflict_strategy,
        }
        paths = {
            "archiveObjectPath": f"{archive_dir}/report.cpt",
            "dslObjectPath": f"{archive_dir}/report.dsl.json",
            "manifestObjectPath": f"{archive_dir}/manifest.json",
            "diffObjectPath": f"{archive_dir}/diff.json",
            "logObjectPath": f"{archive_dir}/generation.log",
        }
        await fr_minio_service.upload_file(cpt_bytes, paths["archiveObjectPath"], "application/octet-stream")
        await fr_minio_service.upload_file(json.dumps(dsl_payload, ensure_ascii=False, indent=2, default=str).encode("utf-8"), paths["dslObjectPath"], "application/json")
        await fr_minio_service.upload_file(json.dumps(manifest, ensure_ascii=False, indent=2, default=str).encode("utf-8"), paths["manifestObjectPath"], "application/json")
        await fr_minio_service.upload_file(json.dumps({"operations": operations}, ensure_ascii=False, indent=2, default=str).encode("utf-8"), paths["diffObjectPath"], "application/json")
        await fr_minio_service.upload_file("\n".join(generation_log).encode("utf-8"), paths["logObjectPath"], "text/plain")
        await fr_minio_service.upload_file(cpt_bytes, normalized, "application/octet-stream")
        target_stat = await fr_minio_service.stat_object_safe(normalized, include_hash=True)
        file_version = FrReportFileVersion(
            file_version_id=f"fr-file-{uuid4().hex[:12]}",
            report_id=project.report_id,
            structure_version_id=structure_version.structure_version_id,
            version_no=version_no,
            version_name=f"文件版本 v{version_no:04d}",
            current_object_path=normalized,
            archive_object_path=paths["archiveObjectPath"],
            dsl_object_path=paths["dslObjectPath"],
            manifest_object_path=paths["manifestObjectPath"],
            diff_object_path=paths["diffObjectPath"],
            source_file_hash=source_hash,
            target_file_hash=target_stat.content_hash or target_hash,
            source_etag=current_stat.etag,
            target_etag=target_stat.etag,
            source_last_modified=current_stat.last_modified,
            target_last_modified=target_stat.last_modified,
            write_status="generated" if not errors else "preview_failed",
            preview_url=preview_url,
            manifest=manifest,
            warnings=warnings or [],
            errors=errors or [],
            create_by=str(user_id),
            update_by=str(user_id),
        )
        db.add(file_version)
        project.current_structure_version_id = structure_version.structure_version_id
        project.current_file_version_id = file_version.file_version_id
        project.current_object_path = normalized
        project.update_by = str(user_id)
        project.update_time = datetime.now()
        await db.commit()
        await db.refresh(project)
        await db.refresh(structure_version)
        await db.refresh(file_version)
        return project, structure_version, file_version, None

    async def save_task_file_version(
        self,
        *,
        db: AsyncSession,
        user_id: int,
        task: FrAiReportTask,
        cpt_bytes: bytes,
        dsl_payload: dict[str, Any],
        generation_log: list[str],
        target_object_path: str,
        conflict_strategy: str = "abort",
        validation_warnings: list[str] | None = None,
    ) -> tuple[FrReportProject, FrReportStructureVersion | None, FrReportFileVersion | None, dict[str, Any] | None]:
        dsl_hash = hashlib.sha1(json.dumps(dsl_payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:12]
        snapshot = FrReportSnapshot(
            snapshot_id=f"task-{task.task_id}-{dsl_hash}",
            object_path=task.cpt_object_path or target_object_path,
            report_path=self.reportlet_path(target_object_path),
            file_name=task.report_name,
            file_type="cpt",
            user_id=user_id,
            snapshot_no=task.revision_no or 1,
            status="task_generated",
            title=task.report_name,
            summary={
                "taskId": task.task_id,
                "conversationId": task.conversation_id,
                "sourceTableName": task.source_table_name,
                "requirementText": task.requirement_text,
            },
            document_snapshot={
                "taskId": task.task_id,
                "reportDsl": dsl_payload,
                "querySql": task.query_sql,
                "sqlValidation": task.sql_validation or {},
                "createTableSql": task.create_table_sql,
            },
            applied_patch={
                "sourceType": "steps_cpt_generate",
                "taskId": task.task_id,
            },
        )
        return await self.save_snapshot_file_version(
            db=db,
            user_id=user_id,
            snapshot=snapshot,
            cpt_bytes=cpt_bytes,
            dsl_payload=dsl_payload,
            operations=[
                {
                    "operationType": "generate_cpt_from_task",
                    "taskId": task.task_id,
                    "summary": "基于分步骤任务 ReportDSL 确定性生成 CPT",
                }
            ],
            generation_log=generation_log,
            target_object_path=target_object_path,
            conflict_strategy=conflict_strategy,
            warnings=validation_warnings or [],
        )

    async def rollback_file_version(
        self,
        db: AsyncSession,
        user_id: int,
        file_version_id: str,
    ) -> FrReportVersionRollbackResponse:
        source = (
            await db.exec(
                select(FrReportFileVersion).where(
                    FrReportFileVersion.file_version_id == file_version_id,
                    FrReportFileVersion.is_deleted == 0,
                )
            )
        ).first()
        if source is None:
            raise ValueError("文件版本不存在")
        project = await self._get_project_by_report_id(db, user_id, source.report_id)
        if project is None:
            raise PermissionError("无权操作该报表版本")
        await self._lock_object_path(db, project.current_object_path)
        conflict = await self.detect_external_conflict(db, project)
        if conflict:
            raise ValueError("当前 CPT 已被 FineReport 设计器修改，请先同步外部修改后再回档")
        data = await fr_minio_service.download_file(source.archive_object_path)
        target_stat = await fr_minio_service.stat_object_safe(project.current_object_path, include_hash=True)
        next_no = await self._next_file_version_no(db, project.report_id)
        archive_dir = f"{self._archive_base_path(project.current_object_path)}/v{next_no:04d}"
        archive_object_path = f"{archive_dir}/report.cpt"
        manifest = {
            "rollbackFromFileVersionId": source.file_version_id,
            "rollbackFromVersionNo": source.version_no,
            "currentObjectPath": project.current_object_path,
            "sourceHash": target_stat.content_hash if target_stat.exists else None,
            "generatedAt": datetime.now().isoformat(timespec="seconds"),
        }
        await fr_minio_service.upload_file(data, archive_object_path, "application/octet-stream")
        await fr_minio_service.upload_file(json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"), f"{archive_dir}/manifest.json", "application/json")
        await fr_minio_service.upload_file(json.dumps({"rollbackFrom": source.file_version_id}, ensure_ascii=False, indent=2).encode("utf-8"), f"{archive_dir}/diff.json", "application/json")
        await fr_minio_service.upload_file(data, project.current_object_path, "application/octet-stream")
        restored_stat = await fr_minio_service.stat_object_safe(project.current_object_path, include_hash=True)
        reportlet_path = self.reportlet_path(project.current_object_path)
        validation = await preview_validator.validate(reportlet_path, write_mode=False)
        rollback_version = FrReportFileVersion(
            file_version_id=f"fr-file-{uuid4().hex[:12]}",
            report_id=project.report_id,
            structure_version_id=source.structure_version_id,
            version_no=next_no,
            version_name=f"回档自 v{source.version_no:04d}",
            current_object_path=project.current_object_path,
            archive_object_path=archive_object_path,
            manifest_object_path=f"{archive_dir}/manifest.json",
            diff_object_path=f"{archive_dir}/diff.json",
            source_file_hash=target_stat.content_hash if target_stat.exists else None,
            target_file_hash=restored_stat.content_hash,
            source_etag=target_stat.etag,
            target_etag=restored_stat.etag,
            source_last_modified=target_stat.last_modified,
            target_last_modified=restored_stat.last_modified,
            write_status="rolled_back" if not validation.errors else "preview_failed",
            preview_url=validation.previewUrl,
            manifest=manifest,
            warnings=validation.warnings,
            errors=validation.errors,
            create_by=str(user_id),
            update_by=str(user_id),
        )
        db.add(rollback_version)
        project.current_file_version_id = rollback_version.file_version_id
        project.current_structure_version_id = rollback_version.structure_version_id
        project.update_time = datetime.now()
        project.update_by = str(user_id)
        await db.commit()
        await db.refresh(rollback_version)
        return FrReportVersionRollbackResponse(
            reportId=project.report_id,
            restoredFileVersionId=source.file_version_id,
            newFileVersionId=rollback_version.file_version_id,
            currentObjectPath=project.current_object_path,
            previewUrl=validation.previewUrl,
            warnings=validation.warnings,
        )

    async def rollback_structure_version(
        self,
        db: AsyncSession,
        user_id: int,
        structure_version_id: str,
    ) -> FrReportStructureRollbackResponse:
        source = (
            await db.exec(
                select(FrReportStructureVersion).where(
                    FrReportStructureVersion.structure_version_id == structure_version_id,
                    FrReportStructureVersion.is_deleted == 0,
                )
            )
        ).first()
        if source is None:
            raise ValueError("平台结构版本不存在")
        project = await self._get_project_by_report_id(db, user_id, source.report_id)
        if project is None:
            raise PermissionError("无权操作该报表结构版本")
        await self._lock_object_path(db, project.current_object_path)
        latest = await self._latest_structure_version(db, project.report_id)
        next_no = (latest.version_no + 1) if latest else 1
        rollback_version = FrReportStructureVersion(
            structure_version_id=f"fr-struct-{uuid4().hex[:12]}",
            report_id=project.report_id,
            snapshot_id=source.snapshot_id,
            version_no=next_no,
            version_name=f"结构回档自 V{source.version_no}",
            parent_version_id=latest.structure_version_id if latest else None,
            source_type="structure_rollback",
            report_dsl=source.report_dsl or {},
            document_snapshot=source.document_snapshot or {},
            sql_snapshot=source.sql_snapshot or {},
            style_snapshot=source.style_snapshot or {},
            writeback_snapshot=source.writeback_snapshot or {},
            operation_patch={
                "rollbackFromStructureVersionId": source.structure_version_id,
                "rollbackFromVersionNo": source.version_no,
            },
            diff_summary={
                "rollbackFromStructureVersionId": source.structure_version_id,
                "rollbackFromVersionNo": source.version_no,
            },
            create_by=str(user_id),
            update_by=str(user_id),
        )
        db.add(rollback_version)
        await db.flush()
        project.current_structure_version_id = rollback_version.structure_version_id
        project.update_time = datetime.now()
        project.update_by = str(user_id)
        await db.commit()
        await db.refresh(rollback_version)
        return FrReportStructureRollbackResponse(
            reportId=project.report_id,
            restoredStructureVersionId=source.structure_version_id,
            newStructureVersionId=rollback_version.structure_version_id,
            currentObjectPath=project.current_object_path,
            warnings=["已恢复为新的平台结构版本，尚未覆盖 CPT 文件；确认后可重新生成 CPT 文件版本。"],
        )

    async def sync_external_file_version(
        self,
        db: AsyncSession,
        user_id: int,
        object_path: str,
    ) -> FrReportExternalSyncResponse:
        normalized = self._normalize_object_path(object_path)
        self._assert_object_path_allowed(normalized)
        await self._lock_object_path(db, normalized)
        current_stat = await fr_minio_service.stat_object_safe(normalized, include_hash=True)
        if not current_stat.exists:
            raise ValueError("目标 CPT 不存在，无法同步外部修改")
        snapshot = FrReportSnapshot(
            snapshot_id=f"external-{uuid4().hex[:12]}",
            object_path=normalized,
            report_path=self.reportlet_path(normalized),
            file_name=self._name_from_object_path(normalized),
            file_type="cpt",
            user_id=user_id,
            snapshot_no=1,
            status="external_synced",
            title=self._name_from_object_path(normalized),
            summary={"sourceType": "manual_external_sync"},
            document_snapshot={},
            applied_patch={"sourceType": "manual_external_sync"},
        )
        project = await self._ensure_project(db, user_id, normalized, snapshot)
        latest_file = await self._latest_file_version(db, project.report_id)
        conflict = self._build_conflict(project, latest_file, current_stat)
        if latest_file and not conflict:
            return FrReportExternalSyncResponse(
                reportId=project.report_id,
                fileVersion=self._file_read(latest_file),
                currentObjectPath=project.current_object_path,
                warnings=["当前文件与平台最新文件版本一致，无需重复同步。"],
            )
        file_version = await self._archive_existing_object(
            db=db,
            user_id=user_id,
            project=project,
            current_stat=current_stat,
            source_type="external_synced",
            structure_version_id=project.current_structure_version_id,
            manifest_extra={"reason": "用户手动同步 FineReport 设计器中的当前 CPT 文件。"},
        )
        project.update_by = str(user_id)
        project.update_time = datetime.now()
        await db.commit()
        await db.refresh(project)
        await db.refresh(file_version)
        return FrReportExternalSyncResponse(
            reportId=project.report_id,
            fileVersion=self._file_read(file_version),
            currentObjectPath=project.current_object_path,
            warnings=["已将当前 MinIO CPT 同步为新的文件版本，未覆盖文件。"],
        )

    async def recycle_report_file(
        self,
        db: AsyncSession,
        user_id: int,
        object_path: str,
    ) -> FrReportRecycleResponse:
        normalized = self._normalize_object_path(object_path)
        self._assert_object_path_allowed(normalized)
        await self._lock_object_path(db, normalized)
        project = await self._get_project_by_object_path(db, user_id, normalized)
        if project is None:
            raise PermissionError("无权回收该报表，或该报表尚未纳入版本管理")
        conflict = await self.detect_external_conflict(db, project)
        if conflict:
            raise ValueError("当前 CPT 已被 FineReport 设计器修改，请先同步外部修改后再移入回收站")
        current_stat = await fr_minio_service.stat_object_safe(normalized, include_hash=True)
        if not current_stat.exists:
            raise ValueError("目标 CPT 不存在，无法移入回收站")
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        trash_path = f"{self._trash_base_path(normalized)}/{timestamp}/report.cpt"
        await fr_minio_service.copy_object_by_download(normalized, trash_path)
        await fr_minio_service.delete_object(normalized)
        manifest = {
            "reportId": project.report_id,
            "recycledObjectPath": normalized,
            "trashObjectPath": trash_path,
            "sourceHash": current_stat.content_hash,
            "sourceEtag": current_stat.etag,
            "sourceLastModified": current_stat.last_modified,
            "recycledAt": datetime.now().isoformat(timespec="seconds"),
        }
        await fr_minio_service.upload_file(
            json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"),
            f"{self._trash_base_path(normalized)}/{timestamp}/manifest.json",
            "application/json",
        )
        project.status = "recycled"
        project.update_by = str(user_id)
        project.update_time = datetime.now()
        db.add(project)
        await db.commit()
        return FrReportRecycleResponse(
            reportId=project.report_id,
            recycledObjectPath=normalized,
            trashObjectPath=trash_path,
            warnings=["已移入回收站；历史文件版本仍可在版本库中回档。"],
        )

    async def detect_external_conflict(self, db: AsyncSession, project: FrReportProject) -> dict[str, Any] | None:
        latest_file = await self._latest_file_version(db, project.report_id)
        current_stat = await fr_minio_service.stat_object_safe(project.current_object_path, include_hash=True)
        return self._build_conflict(project, latest_file, current_stat)

    async def _lock_object_path(self, db: AsyncSession, object_path: str) -> None:
        await db.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
            {"lock_key": f"fr-report-version:{object_path}"},
        )

    async def _ensure_project(
        self,
        db: AsyncSession,
        user_id: int,
        object_path: str,
        snapshot: FrReportSnapshot,
    ) -> FrReportProject:
        project = await self._get_project_by_object_path(db, user_id, object_path)
        if project:
            return project
        report_name = self._name_from_object_path(object_path) or snapshot.title or snapshot.file_name or "报表.cpt"
        report_name = self._normalize_report_name(report_name)
        project = FrReportProject(
            report_id=f"fr-rpt-{uuid4().hex[:12]}",
            report_name=report_name.removesuffix(".cpt"),
            report_code=self._slug_code(report_name),
            target_folder=self._folder_from_object_path(object_path) or REPORTLETS_ROOT,
            current_object_path=object_path,
            owner_user_id=user_id,
            source_object_path=snapshot.object_path,
            summary=snapshot.summary or {},
            create_by=str(user_id),
            update_by=str(user_id),
        )
        db.add(project)
        await db.flush()
        return project

    async def _ensure_structure_version(
        self,
        db: AsyncSession,
        user_id: int,
        project: FrReportProject,
        snapshot: FrReportSnapshot,
        operations: list[dict[str, Any]],
    ) -> FrReportStructureVersion:
        existing = None
        if snapshot.snapshot_id:
            existing = (
                await db.exec(
                    select(FrReportStructureVersion).where(
                        FrReportStructureVersion.report_id == project.report_id,
                        FrReportStructureVersion.snapshot_id == snapshot.snapshot_id,
                        FrReportStructureVersion.is_deleted == 0,
                    )
                )
            ).first()
        if existing:
            return existing
        latest = await self._latest_structure_version(db, project.report_id)
        version_no = (latest.version_no + 1) if latest else 1
        document = snapshot.document_snapshot or {}
        structure = FrReportStructureVersion(
            structure_version_id=f"fr-struct-{uuid4().hex[:12]}",
            report_id=project.report_id,
            snapshot_id=snapshot.snapshot_id,
            version_no=version_no,
            version_name=f"平台结构版本 V{version_no}",
            parent_version_id=latest.structure_version_id if latest else None,
            source_type=snapshot.status or "ai_generated",
            report_dsl=document.get("reportDsl") or {},
            document_snapshot=document,
            operation_patch={"operations": operations, "appliedPatch": snapshot.applied_patch or {}},
            diff_summary={"snapshotNo": snapshot.snapshot_no, "snapshotStatus": snapshot.status},
            create_by=str(user_id),
            update_by=str(user_id),
        )
        db.add(structure)
        await db.flush()
        return structure

    async def _archive_existing_object(
        self,
        *,
        db: AsyncSession,
        user_id: int,
        project: FrReportProject,
        current_stat: FrMinIOObjectStat,
        source_type: str,
        structure_version_id: str | None,
        manifest_extra: dict[str, Any],
    ) -> FrReportFileVersion:
        if not current_stat.exists:
            raise ValueError("当前文件不存在，无法同步外部修改")
        version_no = await self._next_file_version_no(db, project.report_id)
        archive_dir = f"{self._archive_base_path(project.current_object_path)}/v{version_no:04d}"
        archive_object_path = f"{archive_dir}/report.cpt"
        await fr_minio_service.copy_object_by_download(project.current_object_path, archive_object_path)
        manifest = {
            "reportId": project.report_id,
            "sourceType": source_type,
            "currentObjectPath": project.current_object_path,
            "archiveObjectPath": archive_object_path,
            "detectedHash": current_stat.content_hash,
            "detectedEtag": current_stat.etag,
            "detectedLastModified": current_stat.last_modified,
            "generatedAt": datetime.now().isoformat(timespec="seconds"),
            **manifest_extra,
        }
        await fr_minio_service.upload_file(json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"), f"{archive_dir}/manifest.json", "application/json")
        diff = {
            "sourceType": source_type,
            "summary": manifest_extra.get("reason") or "归档当前目标 CPT",
            "detectedHash": current_stat.content_hash,
            "detectedLastModified": current_stat.last_modified,
        }
        await fr_minio_service.upload_file(json.dumps(diff, ensure_ascii=False, indent=2).encode("utf-8"), f"{archive_dir}/diff.json", "application/json")
        file_version = FrReportFileVersion(
            file_version_id=f"fr-file-{uuid4().hex[:12]}",
            report_id=project.report_id,
            structure_version_id=structure_version_id,
            version_no=version_no,
            version_name="覆盖前自动归档" if source_type == "external_archived_before_overwrite" else "设计器外部修改同步",
            current_object_path=project.current_object_path,
            archive_object_path=archive_object_path,
            manifest_object_path=f"{archive_dir}/manifest.json",
            diff_object_path=f"{archive_dir}/diff.json",
            target_file_hash=current_stat.content_hash,
            target_etag=current_stat.etag,
            target_last_modified=current_stat.last_modified,
            write_status=source_type,
            manifest=manifest,
            warnings=[manifest_extra.get("reason", "")],
            create_by=str(user_id),
            update_by=str(user_id),
        )
        db.add(file_version)
        await db.flush()
        project.current_file_version_id = file_version.file_version_id
        return file_version

    def _build_conflict(
        self,
        project: FrReportProject,
        latest_file: FrReportFileVersion | None,
        current_stat: FrMinIOObjectStat,
    ) -> dict[str, Any] | None:
        if not current_stat.exists:
            return None
        if latest_file is None:
            return {
                "type": "untracked_existing_file",
                "message": "目标路径已存在 CPT，但平台尚无文件版本记录。写入前需要先归档现有文件。",
                "currentObjectPath": project.current_object_path,
                "detectedHash": current_stat.content_hash,
                "detectedEtag": current_stat.etag,
                "detectedLastModified": current_stat.last_modified,
                "resolutionOptions": ["sync_external_only", "archive_and_overwrite", "cancel"],
            }
        if latest_file.target_file_hash and current_stat.content_hash and latest_file.target_file_hash != current_stat.content_hash:
            return {
                "type": "external_modified",
                "message": "当前 CPT 文件与平台最新文件版本 hash 不一致，可能已在 FineReport 设计器中修改。",
                "currentObjectPath": project.current_object_path,
                "baseFileVersionId": latest_file.file_version_id,
                "baseHash": latest_file.target_file_hash,
                "detectedHash": current_stat.content_hash,
                "baseLastModified": latest_file.target_last_modified,
                "detectedLastModified": current_stat.last_modified,
                "resolutionOptions": ["sync_external_only", "archive_and_overwrite", "cancel"],
            }
        return None

    async def _record_conflict(
        self,
        db: AsyncSession,
        project: FrReportProject,
        latest_file: FrReportFileVersion | None,
        current_stat: FrMinIOObjectStat,
        conflict: dict[str, Any],
    ) -> None:
        change = FrReportExternalChangeLog(
            change_id=f"fr-ext-{uuid4().hex[:12]}",
            report_id=project.report_id,
            object_path=project.current_object_path,
            last_known_hash=latest_file.target_file_hash if latest_file else None,
            detected_hash=current_stat.content_hash,
            last_known_etag=latest_file.target_etag if latest_file else None,
            detected_etag=current_stat.etag,
            last_known_modified=latest_file.target_last_modified if latest_file else None,
            detected_modified=current_stat.last_modified,
            base_file_version_id=latest_file.file_version_id if latest_file else None,
            detail=conflict,
        )
        db.add(change)
        await db.commit()

    async def _get_project_by_object_path(self, db: AsyncSession, user_id: int, object_path: str) -> FrReportProject | None:
        return (
            await db.exec(
                select(FrReportProject).where(
                    FrReportProject.current_object_path == object_path,
                    FrReportProject.owner_user_id == user_id,
                    FrReportProject.is_deleted == 0,
                )
            )
        ).first()

    async def _get_project_by_report_id(self, db: AsyncSession, user_id: int, report_id: str) -> FrReportProject | None:
        return (
            await db.exec(
                select(FrReportProject).where(
                    FrReportProject.report_id == report_id,
                    FrReportProject.owner_user_id == user_id,
                    FrReportProject.is_deleted == 0,
                )
            )
        ).first()

    async def _latest_structure_version(self, db: AsyncSession, report_id: str) -> FrReportStructureVersion | None:
        return (
            await db.exec(
                select(FrReportStructureVersion)
                .where(FrReportStructureVersion.report_id == report_id, FrReportStructureVersion.is_deleted == 0)
                .order_by(FrReportStructureVersion.version_no.desc(), FrReportStructureVersion.id.desc())
            )
        ).first()

    async def _latest_file_version(self, db: AsyncSession, report_id: str) -> FrReportFileVersion | None:
        return (
            await db.exec(
                select(FrReportFileVersion)
                .where(FrReportFileVersion.report_id == report_id, FrReportFileVersion.is_deleted == 0)
                .order_by(FrReportFileVersion.version_no.desc(), FrReportFileVersion.id.desc())
            )
        ).first()

    async def _next_file_version_no(self, db: AsyncSession, report_id: str) -> int:
        latest = await self._latest_file_version(db, report_id)
        return (latest.version_no + 1) if latest else 1

    def _normalize_report_name(self, report_name: str) -> str:
        name = report_name.strip().replace("\\", "/").split("/")[-1]
        name = re.sub(r'[<>:"|?*\x00-\x1f]', "_", name)
        if not name.lower().endswith(".cpt"):
            name = f"{name}.cpt"
        if name in {".cpt", ""}:
            raise ValueError("报表名称不能为空")
        return name

    def _normalize_folder(self, target_folder: str) -> str:
        folder = target_folder.strip().replace("\\", "/").rstrip("/")
        if not folder:
            raise ValueError("目标目录不能为空")
        if folder.startswith("reportlets/"):
            folder = f"webroot/APP/{folder}"
        elif not folder.startswith(REPORTLETS_ROOT):
            folder = f"{REPORTLETS_ROOT}/{folder.lstrip('/')}"
        return self._normalize_object_path(folder)

    def _normalize_object_path(self, object_path: str) -> str:
        normalized = str(PurePosixPath(object_path.strip().replace("\\", "/")))
        if normalized in {".", ""}:
            raise ValueError("对象路径不能为空")
        if normalized.startswith("reportlets/"):
            normalized = f"webroot/APP/{normalized}"
        if not normalized.startswith(f"{REPORTLETS_ROOT}/") and normalized != REPORTLETS_ROOT:
            raise ValueError("只能写入 webroot/APP/reportlets 下的帆软报表目录")
        if "/../" in f"/{normalized}/" or normalized.endswith("/.."):
            raise ValueError("对象路径不能包含上级目录")
        return normalized

    def _assert_object_path_allowed(self, object_path: str) -> None:
        allowed_prefixes = [
            self._normalize_object_path(item.strip())
            for item in settings.FR_AI_REPORT_FILE_PREFIXES.split(",")
            if item.strip()
        ] or [REPORTLETS_ROOT]
        if not any(object_path == prefix or object_path.startswith(f"{prefix.rstrip('/')}/") for prefix in allowed_prefixes):
            raise ValueError("当前路径不在 FineReport AI 允许读写范围内")

    def _folder_from_object_path(self, object_path: str | None) -> str | None:
        if not object_path:
            return None
        path = self._normalize_object_path(object_path)
        return str(PurePosixPath(path).parent)

    def _name_from_object_path(self, object_path: str | None) -> str | None:
        if not object_path:
            return None
        return PurePosixPath(object_path).name

    def _archive_base_path(self, object_path: str) -> str:
        normalized = self._normalize_object_path(object_path)
        folder = str(PurePosixPath(normalized).parent)
        stem = PurePosixPath(normalized).name.removesuffix(".cpt")
        return f"{folder}/版本库/{stem}"

    def _trash_base_path(self, object_path: str) -> str:
        normalized = self._normalize_object_path(object_path)
        folder = str(PurePosixPath(normalized).parent)
        stem = PurePosixPath(normalized).name.removesuffix(".cpt")
        return f"{folder}/回收站/{stem}"

    def _slug_code(self, report_name: str) -> str:
        digest = hashlib.sha1(report_name.encode("utf-8")).hexdigest()[:8]
        return f"fr_report_{digest}"

    def _project_read(self, project: FrReportProject) -> FrReportProjectRead:
        return FrReportProjectRead(
            reportId=project.report_id,
            reportName=project.report_name,
            reportCode=project.report_code,
            targetFolder=project.target_folder,
            currentObjectPath=project.current_object_path,
            currentStructureVersionId=project.current_structure_version_id,
            currentFileVersionId=project.current_file_version_id,
            status=project.status,
        )

    def _structure_read(self, item: FrReportStructureVersion) -> FrReportStructureVersionRead:
        return FrReportStructureVersionRead(
            structureVersionId=item.structure_version_id,
            reportId=item.report_id,
            snapshotId=item.snapshot_id,
            versionNo=item.version_no,
            versionName=item.version_name,
            parentVersionId=item.parent_version_id,
            sourceType=item.source_type,
            status=item.status,
            createTime=item.create_time.isoformat(timespec="seconds"),
            diffSummary=item.diff_summary or {},
        )

    def _file_read(self, item: FrReportFileVersion) -> FrReportFileVersionRead:
        return FrReportFileVersionRead(
            fileVersionId=item.file_version_id,
            reportId=item.report_id,
            structureVersionId=item.structure_version_id,
            versionNo=item.version_no,
            versionName=item.version_name,
            currentObjectPath=item.current_object_path,
            archiveObjectPath=item.archive_object_path,
            manifestObjectPath=item.manifest_object_path,
            sourceFileHash=item.source_file_hash,
            targetFileHash=item.target_file_hash,
            sourceLastModified=item.source_last_modified,
            targetLastModified=item.target_last_modified,
            writeStatus=item.write_status,
            previewUrl=item.preview_url,
            createTime=item.create_time.isoformat(timespec="seconds"),
            diffSummary={
                "sourceHash": item.source_file_hash,
                "targetHash": item.target_file_hash,
                "writeStatus": item.write_status,
                "manifest": item.manifest or {},
            },
            warnings=item.warnings or [],
            errors=item.errors or [],
        )


fr_report_version_control_service = FrReportVersionControlService()
