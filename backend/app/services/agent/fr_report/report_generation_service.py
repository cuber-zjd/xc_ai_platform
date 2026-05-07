import re
from datetime import datetime
from typing import Any
from uuid import uuid4

from fastapi import UploadFile
from sqlalchemy import text
from sqlmodel import desc, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.logger import logger
from app.models.agent.fr_report.report_task import (
    FrAiReportConversation,
    FrAiReportFeedback,
    FrAiReportTask,
    FrAiReportTaskStatus,
)
from app.schemas.agent.fr_report.ai_report import (
    ExcelAnalysisResult,
    FrAiReportFeedbackCreate,
    FrAiReportFeedbackRead,
    GenerateDslStepResponse,
    GenerateReportResponse,
    GenerateSqlStepResponse,
    PreviewValidationResult,
    ReportTaskListItem,
    ReportTaskRead,
    SqlValidationResult,
)
from app.schemas.page import Page
from app.schemas.agent.fr_report.report_dsl import ReportDSL, ReportType
from app.services.agent.fr_report.agents import (
    data_model_agent,
    report_designer_agent,
    requirement_agent,
)
from app.services.agent.fr_report.cpt_generator import cpt_generator
from app.services.agent.fr_report.dsl_validator import DslValidationError, dsl_validator
from app.services.agent.fr_report.excel_analyzer import excel_analyzer
from app.services.agent.fr_report.minio_staging_service import minio_staging_service
from app.services.agent.fr_report.preview_validator import preview_validator
from app.services.agent.fr_report.sql_react_agent import sql_react_agent
from app.services.agent.fr_report.sqlserver_query_service import sqlserver_query_service


class FrAiReportService:
    async def generate_sql_step(
        self,
        session: AsyncSession,
        requirement: str | None,
        file: UploadFile | None,
        table_schema: dict[str, Any] | None,
        report_name: str | None,
        source_table_name: str | None = None,
        conversation_id: str | None = None,
        user_id: str | None = None,
    ) -> GenerateSqlStepResponse:
        await self._ensure_task_columns(session)
        task_id = str(uuid4())
        conversation, revision_no, parent_task_id = await self._prepare_conversation(
            session,
            conversation_id,
            report_name,
            source_table_name,
            user_id,
        )
        logs = [self._log("开始执行 FineReport AI 报表第一步：生成 SQL 并预览数据")]
        task = FrAiReportTask(
            task_id=task_id,
            conversation_id=conversation.conversation_id,
            parent_task_id=parent_task_id,
            revision_no=revision_no,
            report_name=report_name or "AI 自动生成报表",
            requirement_text=requirement,
            source_table_name=source_table_name,
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

            final_report_name = report_name or self._default_report_name(
                requirement_summary,
                file.filename if file else None,
            )
            resolved_table_schema = await self._resolve_table_schema(table_schema, source_table_name, logs)
            data_model = await data_model_agent.design(resolved_table_schema, analysis, requirement_summary)
            parameters = report_designer_agent.build_parameters(data_model)
            sql_react_result = await sql_react_agent.generate_and_validate(
                data_model,
                parameters,
                ReportType(requirement_summary["reportType"]),
                requirement_summary,
                analysis,
            )
            logs.extend(self._log(message) for message in sql_react_result.logs)
            logs.append(
                self._log(
                    "SQL 生成和数据预览完成"
                    if sql_react_result.validation.success
                    else "SQL 已生成，但数据预览未完全通过"
                )
            )

            task.report_name = final_report_name
            task.report_type = requirement_summary["reportType"]
            task.status = (
                FrAiReportTaskStatus.GENERATED
                if not sql_react_result.validation.errors
                else FrAiReportTaskStatus.VALIDATION_FAILED
            )
            task.data_source_status = data_model.dataSourceStatus
            task.source_file_name = file.filename if file else None
            task.source_table_name = source_table_name
            task.table_schema = resolved_table_schema
            task.excel_analysis = analysis.model_dump(mode="json") if analysis else None
            task.requirement_summary = requirement_summary
            task.query_sql = sql_react_result.sql
            task.sql_validation = sql_react_result.validation.model_dump(mode="json")
            task.create_table_sql = data_model.createTableSql
            task.generation_log = logs
            task.warnings = sql_react_result.validation.warnings
            task.errors = sql_react_result.validation.errors
            task.update_time = datetime.now()
            session.add(task)
            await self._touch_conversation(session, conversation, task)
            await session.commit()
            await session.refresh(task)

            return self.to_sql_step_schema(task)
        except Exception as exc:
            logger.exception(f"FineReport AI SQL 步骤生成失败：{exc}")
            task.status = FrAiReportTaskStatus.FAILED
            task.errors = [str(exc)]
            task.generation_log = logs + [self._log("第一步执行异常")]
            task.update_time = datetime.now()
            session.add(task)
            await session.commit()
            await session.refresh(task)
            return self.to_sql_step_schema(task)

    async def generate_dsl_step(
        self,
        session: AsyncSession,
        task_id: str,
        dsl_feedback: str | None = None,
    ) -> GenerateDslStepResponse:
        await self._ensure_task_columns(session)
        task = await self.get_task(session, task_id)
        if task is None:
            raise ValueError("任务不存在")
        if not task.query_sql:
            raise ValueError("请先完成第一步 SQL 生成")
        if not task.requirement_summary:
            raise ValueError("任务缺少需求摘要，无法生成 ReportDSL")
        logs = list(task.generation_log or [])
        logs.append(self._log("开始执行 FineReport AI 报表第二步：生成 ReportDSL 并使用 DSL 预览"))
        if dsl_feedback and dsl_feedback.strip():
            logs.append(self._log("收到 DSL 修改意见，重新生成 ReportDSL"))
        task.status = FrAiReportTaskStatus.GENERATING
        task.generation_log = logs
        task.update_time = datetime.now()
        session.add(task)
        await session.commit()
        await session.refresh(task)

        try:
            analysis = ExcelAnalysisResult.model_validate(task.excel_analysis) if task.excel_analysis else None
            requirement_summary = self._merge_dsl_feedback(task.requirement_summary, dsl_feedback)
            data_model = await data_model_agent.design(task.table_schema, analysis, requirement_summary)
            dsl = await report_designer_agent.design(
                task.report_name,
                requirement_summary,
                data_model,
                task.query_sql,
            )
            logs.append(self._log("ReportDSL 生成完成，未生成 CPT/XML"))
            validation_warnings = dsl_validator.validate(dsl)
            logs.append(self._log("ReportDSL 校验通过，前端将基于 DSL 和 SQL 样例数据渲染预览"))

            sql_validation = task.sql_validation or {}
            sql_errors = list(sql_validation.get("errors", []))
            sql_warnings = list(sql_validation.get("warnings", []))
            task.report_type = dsl.reportType.value
            task.data_source_status = data_model.dataSourceStatus
            task.table_schema = task.table_schema
            task.requirement_summary = requirement_summary
            task.report_dsl = dsl.model_dump(mode="json")
            task.create_table_sql = data_model.createTableSql
            task.generation_log = logs
            task.warnings = validation_warnings + sql_warnings
            task.errors = sql_errors
            task.status = FrAiReportTaskStatus.GENERATED if not task.errors else FrAiReportTaskStatus.VALIDATION_FAILED
            task.update_time = datetime.now()
            session.add(task)
            if task.conversation_id:
                result = await session.exec(
                    select(FrAiReportConversation).where(
                        FrAiReportConversation.conversation_id == task.conversation_id,
                        FrAiReportConversation.is_deleted == 0,
                    )
                )
                conversation = result.first()
                if conversation:
                    await self._touch_conversation(session, conversation, task)
            await session.commit()
            await session.refresh(task)
            return self.to_dsl_step_schema(task)
        except DslValidationError as exc:
            task.status = FrAiReportTaskStatus.FAILED
            task.errors = exc.errors
            task.warnings = exc.warnings
            task.generation_log = logs + [self._log("ReportDSL 校验失败")]
            task.update_time = datetime.now()
            session.add(task)
            await session.commit()
            await session.refresh(task)
            return self.to_dsl_step_schema(task)
        except Exception as exc:
            logger.exception(f"FineReport AI DSL 步骤生成失败：{exc}")
            task.status = FrAiReportTaskStatus.FAILED
            task.errors = [str(exc)]
            task.generation_log = logs + [self._log("第二步执行异常")]
            task.update_time = datetime.now()
            session.add(task)
            await session.commit()
            await session.refresh(task)
            return self.to_dsl_step_schema(task)

    async def generate(
        self,
        session: AsyncSession,
        requirement: str | None,
        file: UploadFile | None,
        table_schema: dict[str, Any] | None,
        report_name: str | None,
        source_table_name: str | None = None,
        conversation_id: str | None = None,
        user_id: str | None = None,
    ) -> GenerateReportResponse:
        await self._ensure_task_columns(session)
        task_id = str(uuid4())
        conversation, revision_no, parent_task_id = await self._prepare_conversation(
            session,
            conversation_id,
            report_name,
            source_table_name,
            user_id,
        )
        logs = [self._log("开始生成 FineReport AI 报表任务")]
        task = FrAiReportTask(
            task_id=task_id,
            conversation_id=conversation.conversation_id,
            parent_task_id=parent_task_id,
            revision_no=revision_no,
            report_name=report_name or "AI 自动生成报表",
            requirement_text=requirement,
            source_table_name=source_table_name,
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
            sql_react_result = await sql_react_agent.generate_and_validate(
                data_model,
                parameters,
                ReportType(requirement_summary["reportType"]),
                requirement_summary,
                analysis,
            )
            query_sql = sql_react_result.sql
            sql_validation = sql_react_result.validation
            logs.extend(self._log(message) for message in sql_react_result.logs)
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
            await self._touch_conversation(session, conversation, task)
            await session.commit()

            return GenerateReportResponse(
                taskId=task.task_id,
                conversationId=task.conversation_id,
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

    async def list_tasks(
        self,
        session: AsyncSession,
        page: int = 1,
        size: int = 20,
        keyword: str | None = None,
        status: str | None = None,
        user_id: str | None = None,
    ) -> Page[ReportTaskListItem]:
        page = max(page, 1)
        size = min(max(size, 1), 100)
        query = select(FrAiReportTask).where(FrAiReportTask.is_deleted == 0)
        if status:
            query = query.where(FrAiReportTask.status == status)
        if keyword:
            like_value = f"%{keyword.strip()}%"
            query = query.where(
                (FrAiReportTask.report_name.ilike(like_value))
                | (FrAiReportTask.requirement_text.ilike(like_value))
                | (FrAiReportTask.source_table_name.ilike(like_value))
            )
        if user_id:
            conversation_query = select(FrAiReportConversation.conversation_id).where(
                FrAiReportConversation.user_id == user_id,
                FrAiReportConversation.is_deleted == 0,
            )
            query = query.where(
                (FrAiReportTask.conversation_id == None)  # noqa: E711
                | FrAiReportTask.conversation_id.in_(conversation_query)
            )

        total = (await session.exec(select(func.count()).select_from(query.subquery()))).one()
        result = await session.exec(
            query.order_by(desc(FrAiReportTask.update_time))
            .offset((page - 1) * size)
            .limit(size)
        )
        items = [self.to_list_item(task) for task in result.all()]
        return Page(total=total, items=items, page=page, size=size)

    async def add_feedback(
        self,
        session: AsyncSession,
        task_id: str,
        feedback: FrAiReportFeedbackCreate,
    ) -> FrAiReportFeedbackRead:
        task = await self.get_task(session, task_id)
        if task is None:
            raise ValueError("任务不存在")
        feedback_obj = FrAiReportFeedback(
            feedback_id=str(uuid4()),
            conversation_id=task.conversation_id,
            task_id=task.task_id,
            feedback_type=feedback.feedbackType,
            content=feedback.content,
            payload=feedback.payload,
            is_positive=feedback.isPositive,
        )
        session.add(feedback_obj)
        await session.commit()
        await session.refresh(feedback_obj)
        return self.to_feedback_schema(feedback_obj)

    async def _ensure_task_columns(self, session: AsyncSession) -> None:
        columns = [
            ("report_type", "VARCHAR"),
            ("source_table_name", "VARCHAR"),
            ("sql_validation", "JSONB"),
            ("warnings", "JSONB"),
            ("errors", "JSONB"),
            ("cpt_object_path", "VARCHAR"),
            ("dsl_object_path", "VARCHAR"),
            ("sql_object_path", "VARCHAR"),
            ("create_sql_object_path", "VARCHAR"),
            ("log_object_path", "VARCHAR"),
            ("preview_url", "VARCHAR"),
            ("conversation_id", "VARCHAR"),
            ("parent_task_id", "VARCHAR"),
            ("revision_no", "INTEGER DEFAULT 1"),
        ]
        for col_name, col_type in columns:
            await session.exec(
                text(
                    f"ALTER TABLE fr_ai_report_task ADD COLUMN IF NOT EXISTS {col_name} {col_type}"
                )
            )
        await session.commit()

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
            conversationId=task.conversation_id,
            parentTaskId=task.parent_task_id,
            revisionNo=task.revision_no or 1,
            status=task.status.value,
            reportName=task.report_name,
            reportType=task.report_type,
            dataSourceStatus=task.data_source_status,
            sourceTableName=task.source_table_name,
            sourceFileName=task.source_file_name,
            requirementText=task.requirement_text,
            cptObjectPath=task.cpt_object_path,
            dslObjectPath=task.dsl_object_path,
            previewUrl=task.preview_url,
            errors=task.errors or [],
            warnings=task.warnings or [],
            excelAnalysis=task.excel_analysis,
            querySql=task.query_sql,
            reportDsl=ReportDSL.model_validate(task.report_dsl) if task.report_dsl else None,
            sqlValidation=SqlValidationResult.model_validate(task.sql_validation) if task.sql_validation else None,
            requirementSummary=task.requirement_summary,
            createTime=task.create_time,
            updateTime=task.update_time,
        )

    def to_sql_step_schema(self, task: FrAiReportTask) -> GenerateSqlStepResponse:
        return GenerateSqlStepResponse(
            taskId=task.task_id,
            conversationId=task.conversation_id,
            parentTaskId=task.parent_task_id,
            revisionNo=task.revision_no or 1,
            status=task.status.value,
            reportName=task.report_name,
            reportType=task.report_type or "",
            dataSourceStatus=task.data_source_status,
            sourceTableName=task.source_table_name,
            sourceFileName=task.source_file_name,
            requirementText=task.requirement_text,
            requirementSummary=task.requirement_summary,
            excelAnalysis=task.excel_analysis,
            querySql=task.query_sql,
            sqlValidation=SqlValidationResult.model_validate(task.sql_validation) if task.sql_validation else None,
            warnings=task.warnings or [],
            errors=task.errors or [],
            createTime=task.create_time,
            updateTime=task.update_time,
        )

    def to_dsl_step_schema(self, task: FrAiReportTask) -> GenerateDslStepResponse:
        return GenerateDslStepResponse(
            taskId=task.task_id,
            conversationId=task.conversation_id,
            parentTaskId=task.parent_task_id,
            revisionNo=task.revision_no or 1,
            status=task.status.value,
            reportName=task.report_name,
            reportType=task.report_type or "",
            reportDsl=ReportDSL.model_validate(task.report_dsl) if task.report_dsl else None,
            sqlValidation=SqlValidationResult.model_validate(task.sql_validation) if task.sql_validation else None,
            warnings=task.warnings or [],
            errors=task.errors or [],
            createTime=task.create_time,
            updateTime=task.update_time,
        )

    def to_list_item(self, task: FrAiReportTask) -> ReportTaskListItem:
        return ReportTaskListItem(
            taskId=task.task_id,
            conversationId=task.conversation_id,
            parentTaskId=task.parent_task_id,
            revisionNo=task.revision_no or 1,
            status=task.status.value,
            reportName=task.report_name,
            reportType=task.report_type,
            dataSourceStatus=task.data_source_status,
            sourceTableName=task.source_table_name,
            sourceFileName=task.source_file_name,
            requirementText=task.requirement_text,
            previewUrl=task.preview_url,
            errorCount=len(task.errors or []),
            warningCount=len(task.warnings or []),
            createTime=task.create_time,
            updateTime=task.update_time,
        )

    def to_feedback_schema(self, feedback: FrAiReportFeedback) -> FrAiReportFeedbackRead:
        return FrAiReportFeedbackRead(
            feedbackId=feedback.feedback_id,
            conversationId=feedback.conversation_id,
            taskId=feedback.task_id,
            feedbackType=feedback.feedback_type,
            content=feedback.content,
            payload=feedback.payload,
            isPositive=feedback.is_positive,
            createTime=feedback.create_time,
            updateTime=feedback.update_time,
        )

    async def _prepare_conversation(
        self,
        session: AsyncSession,
        conversation_id: str | None,
        report_name: str | None,
        source_table_name: str | None,
        user_id: str | None,
    ) -> tuple[FrAiReportConversation, int, str | None]:
        conversation = None
        if conversation_id:
            result = await session.exec(
                select(FrAiReportConversation).where(
                    FrAiReportConversation.conversation_id == conversation_id,
                    FrAiReportConversation.is_deleted == 0,
                )
            )
            conversation = result.first()
        if conversation is None:
            conversation = FrAiReportConversation(
                conversation_id=str(uuid4()),
                title=report_name or "AI 自动生成报表",
                user_id=user_id,
                source_table_name=source_table_name,
            )
            session.add(conversation)
            await session.commit()
            await session.refresh(conversation)
            return conversation, 1, None

        latest_task_id = conversation.latest_task_id
        latest_revision = 0
        if latest_task_id:
            latest_task = await self.get_task(session, latest_task_id)
            latest_revision = latest_task.revision_no if latest_task else 0
        return conversation, latest_revision + 1, latest_task_id

    async def _touch_conversation(
        self,
        session: AsyncSession,
        conversation: FrAiReportConversation,
        task: FrAiReportTask,
    ) -> None:
        conversation.latest_task_id = task.task_id
        conversation.title = task.report_name or conversation.title
        conversation.status = task.status.value
        conversation.source_table_name = task.source_table_name or conversation.source_table_name
        conversation.summary = {
            "reportType": task.report_type,
            "dataSourceStatus": task.data_source_status,
            "hasExcel": bool(task.source_file_name),
            "hasSql": bool(task.query_sql),
            "hasDsl": bool(task.report_dsl),
        }
        conversation.update_time = datetime.now()
        session.add(conversation)

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
        detail = "；".join(errors + warnings) or "未查询到字段结构"
        raise ValueError(f"无法根据表名查询 SQL Server 表结构：{', '.join(table_names)}。{detail}")

    def _merge_dsl_feedback(
        self,
        requirement_summary: dict[str, Any],
        dsl_feedback: str | None,
    ) -> dict[str, Any]:
        if not dsl_feedback or not dsl_feedback.strip():
            return dict(requirement_summary)

        summary = dict(requirement_summary)
        feedback_text = dsl_feedback.strip()
        summary["dslRevisionNote"] = feedback_text
        template_design = dict(summary.get("templateDesign") or {})
        design_notes = list(template_design.get("designNotes") or [])
        design_notes.append(feedback_text)
        template_design["designNotes"] = design_notes[-10:]

        if self._requires_latest_change_row(feedback_text):
            special_rows = list(template_design.get("specialRows") or [])
            special_rows.append(
                {
                    "id": "latest_change_row",
                    "label": "涨跌",
                    "kind": "latest_change_only",
                    "keepRows": 1,
                    "position": "below_column_group_above_price_rows",
                    "dimensionHint": "市场",
                    "measureHint": "涨跌",
                    "dateRule": "latest_date",
                }
            )
            template_design["specialRows"] = special_rows

        summary["templateDesign"] = template_design
        return summary

    def _requires_latest_change_row(self, feedback_text: str) -> bool:
        normalized = feedback_text.replace(" ", "")
        return (
            "涨跌" in normalized
            and any(keyword in normalized for keyword in ["最新一天", "最新1天", "最后一天"])
            and any(keyword in normalized for keyword in ["单独一行", "只保留一行", "保留一行"])
        )

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
