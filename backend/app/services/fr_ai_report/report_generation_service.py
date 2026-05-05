import re
from datetime import datetime
from typing import Any
from uuid import uuid4

from fastapi import UploadFile
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.logger import logger
from app.models.fr_ai_report.report_task import FrAiReportTask, FrAiReportTaskStatus
from app.schemas.fr_ai_report.ai_report import (
    GenerateReportResponse,
    PreviewValidationResult,
    ReportTaskRead,
    SqlValidationResult,
)
from app.schemas.fr_ai_report.report_dsl import ReportDSL, ReportType
from app.services.fr_ai_report.agents import (
    data_model_agent,
    report_designer_agent,
    requirement_agent,
    sql_agent,
)
from app.services.fr_ai_report.cpt_generator import cpt_generator
from app.services.fr_ai_report.dsl_validator import DslValidationError, dsl_validator
from app.services.fr_ai_report.excel_analyzer import excel_analyzer
from app.services.fr_ai_report.minio_staging_service import minio_staging_service
from app.services.fr_ai_report.preview_validator import preview_validator
from app.services.fr_ai_report.sqlserver_query_service import sqlserver_query_service


class FrAiReportService:
    async def generate(
        self,
        session: AsyncSession,
        requirement: str | None,
        file: UploadFile | None,
        table_schema: dict[str, Any] | None,
        report_name: str | None,
        source_table_name: str | None = None,
    ) -> GenerateReportResponse:
        task_id = str(uuid4())
        logs = [self._log("开始生成 FineReport AI 报表任务")]
        task = FrAiReportTask(
            task_id=task_id,
            report_name=report_name or "AI 自动生成报表",
            requirement_text=requirement,
            table_schema=table_schema,
            generation_log=logs,
        )
        session.add(task)
        await session.commit()
        await session.refresh(task)

        try:
            file_content = await file.read() if file else None
            analysis = excel_analyzer.analyze(file_content, file.filename) if file_content else None
            logs.append(self._log("Excel 分析完成" if analysis else "未提供 Excel，跳过 Excel 分析"))

            requirement_summary = await requirement_agent.summarize(requirement, analysis)
            logs.append(self._log("需求摘要生成完成"))

            final_report_name = report_name or self._default_report_name(requirement_summary, file.filename if file else None)
            table_schema = await self._resolve_table_schema(table_schema, source_table_name, logs)
            data_model = await data_model_agent.design(table_schema, analysis, requirement_summary)
            parameters = report_designer_agent.build_parameters(data_model)
            query_sql = await sql_agent.generate(
                data_model,
                parameters,
                ReportType(requirement_summary["reportType"]),
                requirement_summary,
            )
            sql_validation = await sqlserver_query_service.validate_select_sql(query_sql, parameters)
            if sql_validation.errors and sql_validation.enabled and sql_validation.configured:
                logs.append(self._log("SQL Server 校验失败，尝试让 SqlAgent 修复 SQL"))
                repaired_sql = await sql_agent.repair(
                    query_sql,
                    sql_validation.errors,
                    data_model,
                    parameters,
                    ReportType(requirement_summary["reportType"]),
                    requirement_summary,
                )
                if repaired_sql != query_sql:
                    query_sql = repaired_sql
                    sql_validation = await sqlserver_query_service.validate_select_sql(query_sql, parameters)
            logs.append(
                self._log(
                    "SQL Server 数据校验通过"
                    if sql_validation.success
                    else "SQL Server 数据校验跳过或未通过"
                )
            )
            dsl = await report_designer_agent.design(final_report_name, requirement_summary, data_model, query_sql)
            logs.append(self._log("ReportDSL 生成完成，未生成 CPT/XML"))

            validation_warnings = dsl_validator.validate(dsl)
            logs.append(self._log("ReportDSL 校验通过"))

            cpt_bytes = cpt_generator.generate(dsl)
            logs.append(self._log("确定性 CPT 生成完成"))

            artifacts = await minio_staging_service.save_artifacts(
                task_id=task_id,
                cpt_bytes=cpt_bytes,
                dsl=dsl.model_dump(mode="json"),
                query_sql=query_sql,
                create_table_sql=data_model.createTableSql,
                generation_log=logs,
            )
            reportlet_path = f"reportlets_ai_staging/{task_id}/report.cpt"
            preview_result = await preview_validator.validate(reportlet_path)

            task.report_name = final_report_name
            task.report_type = dsl.reportType.value
            task.status = (
                FrAiReportTaskStatus.GENERATED
                if not sql_validation.errors and not preview_result.errors
                else FrAiReportTaskStatus.VALIDATION_FAILED
            )
            task.data_source_status = data_model.dataSourceStatus
            task.source_file_name = file.filename if file else None
            task.table_schema = table_schema
            task.excel_analysis = analysis.model_dump(mode="json") if analysis else None
            task.requirement_summary = requirement_summary
            task.report_dsl = dsl.model_dump(mode="json")
            task.query_sql = query_sql
            task.sql_validation = sql_validation.model_dump(mode="json")
            task.create_table_sql = data_model.createTableSql
            task.generation_log = logs
            task.cpt_object_path = artifacts["cptObjectPath"]
            task.dsl_object_path = artifacts["dslObjectPath"]
            task.sql_object_path = artifacts["sqlObjectPath"]
            task.create_sql_object_path = artifacts["createSqlObjectPath"]
            task.log_object_path = artifacts["logObjectPath"]
            task.preview_url = preview_result.previewUrl
            task.warnings = validation_warnings + sql_validation.warnings + preview_result.warnings
            task.errors = sql_validation.errors + preview_result.errors
            task.update_time = datetime.now()
            session.add(task)
            await session.commit()

            return GenerateReportResponse(
                taskId=task.task_id,
                status=task.status.value,
                reportName=task.report_name,
                reportType=task.report_type or "",
                previewUrl=task.preview_url,
                warnings=task.warnings,
                errors=task.errors,
            )
        except DslValidationError as exc:
            task.status = FrAiReportTaskStatus.FAILED
            task.errors = exc.errors
            task.warnings = exc.warnings
            task.generation_log = logs + [self._log("ReportDSL 校验失败")]
            task.update_time = datetime.now()
            session.add(task)
            await session.commit()
            return GenerateReportResponse(
                taskId=task.task_id,
                status=task.status.value,
                reportName=task.report_name,
                reportType=task.report_type or "",
                warnings=task.warnings,
                errors=task.errors,
            )
        except Exception as exc:
            logger.exception(f"FineReport AI 报表生成失败：{exc}")
            task.status = FrAiReportTaskStatus.FAILED
            task.errors = [str(exc)]
            task.generation_log = logs + [self._log("任务执行异常")]
            task.update_time = datetime.now()
            session.add(task)
            await session.commit()
            return GenerateReportResponse(
                taskId=task.task_id,
                status=task.status.value,
                reportName=task.report_name,
                reportType=task.report_type or "",
                errors=task.errors,
            )

    async def get_task(self, session: AsyncSession, task_id: str) -> FrAiReportTask | None:
        result = await session.exec(select(FrAiReportTask).where(FrAiReportTask.task_id == task_id))
        return result.first()

    async def validate_preview(self, session: AsyncSession, task_id: str) -> PreviewValidationResult:
        task = await self.get_task(session, task_id)
        if task is None:
            raise ValueError("任务不存在")
        task.status = FrAiReportTaskStatus.VALIDATING
        session.add(task)
        await session.commit()

        reportlet_path = f"reportlets_ai_staging/{task_id}/report.cpt"
        result = await preview_validator.validate(reportlet_path)
        sql_validation = task.sql_validation or {}
        task.preview_url = result.previewUrl
        task.errors = list(sql_validation.get("errors", [])) + result.errors
        task.warnings = list(sql_validation.get("warnings", [])) + result.warnings
        task.status = FrAiReportTaskStatus.VALIDATED if not task.errors else FrAiReportTaskStatus.VALIDATION_FAILED
        task.update_time = datetime.now()
        session.add(task)
        await session.commit()
        return result

    async def publish(self, session: AsyncSession, task_id: str) -> FrAiReportTask:
        task = await self.get_task(session, task_id)
        if task is None:
            raise ValueError("任务不存在")
        warnings = list(task.warnings or [])
        warnings.append("安全策略：publish 仅标记任务已发布，CPT 仍保留在 MinIO staging，不直接写正式 reportlets")
        task.status = FrAiReportTaskStatus.PUBLISHED
        task.warnings = warnings
        task.update_time = datetime.now()
        session.add(task)
        await session.commit()
        await session.refresh(task)
        return task

    def to_read_schema(self, task: FrAiReportTask) -> ReportTaskRead:
        return ReportTaskRead(
            taskId=task.task_id,
            status=task.status.value,
            reportName=task.report_name,
            reportType=task.report_type,
            dataSourceStatus=task.data_source_status,
            cptObjectPath=task.cpt_object_path,
            dslObjectPath=task.dsl_object_path,
            previewUrl=task.preview_url,
            errors=task.errors or [],
            warnings=task.warnings or [],
            excelAnalysis=task.excel_analysis,
            reportDsl=ReportDSL.model_validate(task.report_dsl) if task.report_dsl else None,
            sqlValidation=SqlValidationResult.model_validate(task.sql_validation) if task.sql_validation else None,
            requirementSummary=task.requirement_summary,
            createTime=task.create_time,
            updateTime=task.update_time,
        )

    def _default_report_name(self, summary: dict[str, Any], file_name: str | None) -> str:
        if summary.get("summary") and summary["summary"] != "根据上传 Excel 自动生成基础报表。":
            return summary["summary"][:30]
        if file_name:
            return file_name.rsplit(".", 1)[0]
        return "AI 自动生成报表"

    async def _resolve_table_schema(
        self,
        table_schema: dict[str, Any] | None,
        source_table_name: str | None,
        logs: list[str],
    ) -> dict[str, Any] | None:
        table_names = self._parse_source_table_names(source_table_name)
        if not table_names and (table_schema or {}).get("tableName"):
            table_names = self._parse_source_table_names(str((table_schema or {})["tableName"]))
        if not table_names:
            return table_schema
        if table_schema and table_schema.get("fields"):
            return table_schema

        resolved_schema, warnings, errors = await sqlserver_query_service.inspect_tables_schema(table_names)
        logs.extend(self._log(message) for message in warnings + errors)
        if resolved_schema:
            logs.append(self._log(f"已根据表名查询 SQL Server 表结构：{', '.join(table_names)}"))
            return resolved_schema
        return table_schema or {"tableName": table_names[0], "fields": []}

    def _parse_source_table_names(self, value: str | None) -> list[str]:
        if not value:
            return []
        return [
            item.strip()
            for item in re.split(r"[\n,，;；]+", value)
            if item.strip()
        ][:8]

    def _log(self, message: str) -> str:
        return f"{datetime.now().isoformat(timespec='seconds')} {message}"


fr_ai_report_service = FrAiReportService()
