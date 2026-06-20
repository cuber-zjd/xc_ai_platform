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
    FrAiReportAgentChatResponse,
    FrAiReportAgentContext,
    FrAiReportAgentEvent,
    FrAiReportFeedbackCreate,
    FrAiReportFeedbackRead,
    FrAiReportRequirementReviewResponse,
    GenerateDslStepResponse,
    GenerateCptStepResponse,
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
from app.services.agent.fr_report.preview_validator import preview_validator
from app.services.agent.fr_report.requirement_planner import fr_report_requirement_planner
from app.services.agent.fr_report.sql_react_agent import sql_react_agent
from app.services.agent.fr_report.sqlserver_query_service import sqlserver_query_service
from app.services.agent.fr_report.version_control_service import fr_report_version_control_service


class FrAiReportService:
    async def agent_chat(
        self,
        session: AsyncSession,
        *,
        user_id: int,
        message: str,
        action: str,
        context: FrAiReportAgentContext,
        file: UploadFile | None = None,
    ) -> FrAiReportAgentChatResponse:
        next_context = self._merge_agent_context(context, message)
        events: list[FrAiReportAgentEvent] = [
            FrAiReportAgentEvent(type="message", content="小驰已收到，我先判断信息是否足够，再决定是否调用工具。")
        ]
        warnings: list[str] = []
        errors: list[str] = []
        action = action if action in {"chat", "start_generate", "save_cpt"} else "chat"

        if action == "save_cpt":
            if not next_context.taskId:
                return FrAiReportAgentChatResponse(
                    status="need_input",
                    context=next_context,
                    events=events
                    + [
                        FrAiReportAgentEvent(
                            type="need_user_input",
                            content="还没有可保存的报表任务。请先描述需求并让我生成报表方案。",
                        )
                    ],
                    questions=["请先让我生成 SQL 和报表方案，再保存成 CPT。"],
                )
            try:
                task = await self.get_task(session, next_context.taskId)
                if task is None:
                    raise ValueError("任务不存在")
                dsl_step: GenerateDslStepResponse | None = None
                if not task.report_dsl:
                    events.append(
                        FrAiReportAgentEvent(
                            type="tool_call_start",
                            toolName="generate_report_dsl",
                            content="当前任务还没有 ReportDSL，小驰先生成可确定性落 CPT 的报表结构。",
                        )
                    )
                    dsl_step = await self.generate_dsl_step(session, next_context.taskId)
                    events.append(
                        FrAiReportAgentEvent(
                            type="tool_call_result",
                            toolName="generate_report_dsl",
                            content="ReportDSL 已生成。",
                            payload={"taskId": dsl_step.taskId, "status": dsl_step.status},
                        )
                    )
                events.append(
                    FrAiReportAgentEvent(
                        type="tool_call_start",
                        toolName="generate_cpt",
                        content="开始生成 CPT，并通过版本控制检查目标文件是否有外部修改。",
                    )
                )
                cpt_step = await self.generate_cpt_step(
                    session,
                    next_context.taskId,
                    user_id=user_id,
                    report_name=next_context.reportName,
                    target_folder=next_context.targetFolder,
                    target_object_path=next_context.targetObjectPath,
                    conflict_strategy="abort",
                )
                next_context.taskId = cpt_step.taskId
                next_context.conversationId = cpt_step.conversationId
                events.append(
                    FrAiReportAgentEvent(
                        type="cpt_ready",
                        toolName="generate_cpt",
                        content="CPT 已生成并写入版本库。若检测到设计器外部修改，会在结果里提示冲突。",
                        payload={
                            "taskId": cpt_step.taskId,
                            "cptObjectPath": cpt_step.cptObjectPath,
                            "previewUrl": cpt_step.previewUrl,
                            "status": cpt_step.status,
                        },
                    )
                )
                return FrAiReportAgentChatResponse(
                    status="cpt_ready" if not cpt_step.errors else "failed",
                    conversationId=cpt_step.conversationId,
                    taskId=cpt_step.taskId,
                    context=next_context,
                    events=events,
                    dslStep=dsl_step,
                    cptStep=cpt_step,
                    warnings=cpt_step.warnings,
                    errors=cpt_step.errors,
                )
            except ValueError as exc:
                errors.append(str(exc))
                events.append(FrAiReportAgentEvent(type="error", content=str(exc)))
                return FrAiReportAgentChatResponse(status="failed", context=next_context, events=events, errors=errors)

        merged_requirement = self._build_agent_requirement(next_context, message)
        missing_items = self._agent_missing_items(next_context, bool(file))
        if missing_items:
            events.append(
                FrAiReportAgentEvent(
                    type="need_user_input",
                    content="我还缺少一些关键信息，补齐后就能继续。",
                    payload={"missingItems": missing_items},
                )
            )
            return FrAiReportAgentChatResponse(
                status="need_input",
                context=next_context,
                events=events,
                questions=missing_items,
            )

        events.append(
            FrAiReportAgentEvent(
                type="tool_call_start",
                toolName="review_requirement",
                content="开始做需求预检，识别报表类型、填报属性、数据来源和需要追问的点。",
            )
        )
        review = await self.review_requirement(
            requirement=merged_requirement,
            file=file,
            table_schema=None,
            source_table_name=next_context.sourceTableName,
        )
        ai_review = await requirement_agent.review_chat(
            requirement=merged_requirement,
            analysis=review.excelAnalysis,
            rule_review=review.model_dump(mode="json", exclude={"excelAnalysis"}),
        )
        display_summary = review.summary
        display_questions = list(review.questions)
        if ai_review:
            display_summary = str(ai_review.get("summary") or review.summary)
            display_questions = [
                str(question)
                for question in (ai_review.get("questions") or [])
                if str(question).strip()
            ][:6]
            ai_source_tables = ai_review.get("sourceTables") or []
            if isinstance(ai_source_tables, list) and ai_source_tables:
                next_context.sourceTableName = ", ".join(str(item) for item in ai_source_tables if str(item).strip()) or next_context.sourceTableName
            events.append(
                FrAiReportAgentEvent(
                    type="tool_call_result",
                    toolName="ai_requirement_review",
                    content=display_summary,
                    payload={
                        "scenario": ai_review.get("scenario"),
                        "reportType": ai_review.get("reportType"),
                        "nextAction": ai_review.get("nextAction"),
                        "sourceTables": ai_source_tables,
                    },
                )
            )
        else:
            display_summary = self._latest_message_summary(message)
            display_questions = []
            events.append(
                FrAiReportAgentEvent(
                    type="message",
                    content="模型需求理解暂时没有返回有效 JSON，小驰先按你最新这条消息做轻量理解；后续生成 SQL/DSL 仍会继续走受控工具。",
                )
            )
        events.append(
            FrAiReportAgentEvent(
                type="tool_call_result",
                toolName="review_requirement",
                content="规则预检已完成，将作为安全边界和兜底参考。",
                payload={"status": review.status, "scenario": review.scenario, "questions": review.questions},
            )
        )
        if action == "chat" and display_questions:
            return FrAiReportAgentChatResponse(
                status="need_input",
                context=next_context,
                events=events
                + [
                    FrAiReportAgentEvent(
                        type="message",
                        content="现在还不急着生成，我先把关键问题问清楚，避免生成出来又偏。",
                    )
                ],
                questions=display_questions,
                review=review,
                warnings=review.warnings,
            )
        if action == "chat":
            return FrAiReportAgentChatResponse(
                status="ready",
                context=next_context,
                events=events
                + [
                    FrAiReportAgentEvent(
                        type="message",
                        content="信息基本够了。你可以直接说“开始生成报表”，我会读取真实表结构、预览样例数据并生成 SQL 和 ReportDSL。",
                    )
                ],
                review=review,
                warnings=review.warnings,
            )
        if display_questions:
            warnings.extend([f"未完全确认，按用户已提供信息继续生成：{question}" for question in display_questions])
            events.append(
                FrAiReportAgentEvent(
                    type="message",
                    content="你已经明确要求开始生成，我会把未完全确认的问题作为假设和风险提示继续执行，生成后可以继续调整。",
                    payload={"assumptionQuestions": display_questions},
                )
            )

        events.append(
            FrAiReportAgentEvent(
                type="tool_call_start",
                toolName="generate_sql_with_preview",
                content="条件已满足，开始读取真实表结构、预览数据并让 SQL ReAct Agent 生成可执行 SQL。",
            )
        )
        sql_step = await self.generate_sql_step(
            session=session,
            requirement=merged_requirement,
            file=file,
            table_schema=None,
            report_name=next_context.reportName,
            source_table_name=next_context.sourceTableName,
            conversation_id=next_context.conversationId,
            user_id=str(user_id),
            ddl_dialect=next_context.ddlDialect,
            id_auto_increment=next_context.idAutoIncrement,
        )
        next_context.taskId = sql_step.taskId
        next_context.conversationId = sql_step.conversationId
        events.append(
            FrAiReportAgentEvent(
                type="sql_ready",
                toolName="generate_sql_with_preview",
                content="SQL 步骤已完成，已包含只读校验结果和样例数据。",
                payload={
                    "taskId": sql_step.taskId,
                    "status": sql_step.status,
                    "success": bool(sql_step.sqlValidation and sql_step.sqlValidation.success),
                    "columns": sql_step.sqlValidation.columns if sql_step.sqlValidation else [],
                },
            )
        )
        warnings.extend(sql_step.warnings)
        errors.extend(sql_step.errors)
        if sql_step.errors:
            return FrAiReportAgentChatResponse(
                status="sql_failed",
                conversationId=sql_step.conversationId,
                taskId=sql_step.taskId,
                context=next_context,
                events=events,
                review=review,
                sqlStep=sql_step,
                warnings=warnings,
                errors=errors,
            )

        events.append(
            FrAiReportAgentEvent(
                type="tool_call_start",
                toolName="generate_report_dsl",
                content="SQL 可用，继续生成 ReportDSL。这里仍然不会让 AI 直接写 CPT/XML。",
            )
        )
        dsl_step = await self.generate_dsl_step(session, sql_step.taskId)
        events.append(
            FrAiReportAgentEvent(
                type="dsl_ready",
                toolName="generate_report_dsl",
                content="ReportDSL 已生成，前端可以实时渲染轻量预览。",
                payload={"taskId": dsl_step.taskId, "status": dsl_step.status},
            )
        )
        warnings.extend(dsl_step.warnings)
        errors.extend(dsl_step.errors)
        return FrAiReportAgentChatResponse(
            status="dsl_ready" if not errors else "dsl_failed",
            conversationId=dsl_step.conversationId,
            taskId=dsl_step.taskId,
            context=next_context,
            events=events,
            review=review,
            sqlStep=sql_step,
            dslStep=dsl_step,
            warnings=warnings,
            errors=errors,
        )

    async def review_requirement(
        self,
        requirement: str | None,
        file: UploadFile | None,
        table_schema: dict[str, Any] | None,
        source_table_name: str | None = None,
    ) -> FrAiReportRequirementReviewResponse:
        file_content = await file.read() if file else None
        if file:
            await file.seek(0)
        analysis = excel_analyzer.analyze(file_content, file.filename) if file_content else None
        return fr_report_requirement_planner.review(
            requirement=requirement,
            analysis=analysis,
            source_table_name=source_table_name,
            table_schema=table_schema,
        )

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
        ddl_dialect: str | None = None,
        id_auto_increment: bool = True,
        table_name_overrides: dict[str, Any] | None = None,
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
            business_review = fr_report_requirement_planner.review(
                requirement=requirement,
                analysis=analysis,
                source_table_name=source_table_name,
                table_schema=table_schema,
            )
            requirement_summary["businessPlan"] = business_review.model_dump(
                mode="json",
                exclude={"excelAnalysis"},
            )
            requirement_summary["ddlOptions"] = self._build_ddl_options(
                ddl_dialect=ddl_dialect,
                id_auto_increment=id_auto_increment,
                table_name_overrides=table_name_overrides,
                source_table_name=source_table_name,
                business_plan=requirement_summary["businessPlan"],
            )
            logs.append(self._log("需求预检完成，已识别维护表、追问和质量门禁"))
            logs.append(self._log("需求摘要生成完成"))

            final_report_name = report_name or self._default_report_name(
                requirement_summary,
                file.filename if file else None,
            )
            resolved_table_schema = await self._resolve_table_schema(
                table_schema,
                source_table_name,
                logs,
                allow_designed_fallback=(
                    (requirement_summary.get("businessPlan") or {}).get("scenario")
                    in {"futures_operation_ledger", "option_operation_ledger"}
                ),
            )
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
            supervisor_warnings, supervisor_errors = self._supervise_generation(
                requirement_summary,
                data_model.model_dump(mode="json"),
                sql_react_result.sql,
            )
            logs.extend(self._log(message) for message in supervisor_warnings + supervisor_errors)

            task.report_name = final_report_name
            task.report_type = requirement_summary["reportType"]
            task.status = (
                FrAiReportTaskStatus.GENERATED
                if not sql_react_result.validation.errors and not supervisor_errors
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
            task.warnings = business_review.warnings + sql_react_result.validation.warnings + supervisor_warnings
            task.errors = sql_react_result.validation.errors + supervisor_errors
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
        target_folder: str | None = None,
        target_object_path: str | None = None,
        conflict_strategy: str = "abort",
        source_table_name: str | None = None,
        conversation_id: str | None = None,
        user_id: str | None = None,
        owner_user_id: int | None = None,
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
            business_review = fr_report_requirement_planner.review(
                requirement=requirement,
                analysis=analysis,
                source_table_name=source_table_name,
                table_schema=table_schema,
            )
            requirement_summary["businessPlan"] = business_review.model_dump(
                mode="json",
                exclude={"excelAnalysis"},
            )
            logs.append(self._log("需求预检完成，已识别维护表、追问和质量门禁"))
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
            supervisor_warnings, supervisor_errors = self._supervise_generation(
                requirement_summary,
                data_model.model_dump(mode="json"),
                query_sql,
            )
            logs.extend(self._log(message) for message in supervisor_warnings + supervisor_errors)
            dsl = await report_designer_agent.design(final_report_name, requirement_summary, data_model, query_sql)
            logs.append(self._log("ReportDSL 生成完成，未生成 CPT/XML"))

            validation_warnings = dsl_validator.validate(dsl)
            logs.append(self._log("ReportDSL 校验通过"))

            cpt_bytes = cpt_generator.generate(dsl)
            logs.append(self._log("确定性 CPT 生成完成"))

            task.report_name = final_report_name
            task.report_type = dsl.reportType.value
            task.data_source_status = data_model.dataSourceStatus
            task.source_file_name = file.filename if file else None
            task.table_schema = table_schema
            task.excel_analysis = analysis.model_dump(mode="json") if analysis else None
            task.requirement_summary = requirement_summary
            task.report_dsl = dsl.model_dump(mode="json")
            task.query_sql = query_sql
            task.sql_validation = sql_validation.model_dump(mode="json")
            task.create_table_sql = data_model.createTableSql

            normalized_target = fr_report_version_control_service.normalize_target_object_path(
                report_name=final_report_name,
                target_folder=target_folder,
                target_object_path=target_object_path,
                fallback_object_path=task.cpt_object_path,
            )
            project, structure_version, file_version, conflict = await fr_report_version_control_service.save_task_file_version(
                db=session,
                user_id=owner_user_id or int(user_id or 0),
                task=task,
                cpt_bytes=cpt_bytes,
                dsl_payload=dsl.model_dump(mode="json"),
                generation_log=logs,
                target_object_path=normalized_target,
                conflict_strategy=conflict_strategy,
                validation_warnings=validation_warnings,
            )
            if conflict:
                task.status = FrAiReportTaskStatus.VALIDATION_FAILED
                task.cpt_object_path = normalized_target
                task.generation_log = logs + [self._log(f"检测到目标 CPT 外部修改，已阻止覆盖：{conflict.get('message', '')}")]
                task.warnings = business_review.warnings + validation_warnings + [conflict.get("message", "检测到目标 CPT 外部修改，已阻止覆盖")]
                task.errors = []
                task.update_time = datetime.now()
                session.add(task)
                await self._touch_conversation(session, conversation, task)
                await session.commit()
                return GenerateReportResponse(
                    taskId=task.task_id,
                    conversationId=task.conversation_id,
                    status="conflict",
                    reportName=task.report_name,
                    reportType=task.report_type or "",
                    warnings=task.warnings,
                    errors=task.errors,
                )
            if not file_version:
                raise ValueError("文件版本保存失败")

            reportlet_path = fr_report_version_control_service.reportlet_path(normalized_target)
            preview_result = await preview_validator.validate(reportlet_path, write_mode=dsl.writeBack.enabled)

            file_version.preview_url = preview_result.previewUrl
            file_version.warnings = validation_warnings + preview_result.warnings
            file_version.errors = preview_result.errors
            file_version.write_status = "generated" if not preview_result.errors else "preview_failed"
            session.add(file_version)

            task.status = (
                FrAiReportTaskStatus.GENERATED
                if not sql_validation.errors and not preview_result.errors and not supervisor_errors
                else FrAiReportTaskStatus.VALIDATION_FAILED
            )
            task.generation_log = logs
            task.cpt_object_path = normalized_target
            task.dsl_object_path = file_version.dsl_object_path
            task.sql_object_path = None
            task.create_sql_object_path = None
            task.log_object_path = file_version.manifest_object_path
            task.preview_url = preview_result.previewUrl
            task.warnings = business_review.warnings + validation_warnings + sql_validation.warnings + supervisor_warnings + preview_result.warnings
            task.errors = sql_validation.errors + supervisor_errors + preview_result.errors
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

    async def generate_cpt_step(
        self,
        session: AsyncSession,
        task_id: str,
        user_id: int,
        report_name: str | None = None,
        target_folder: str | None = None,
        target_object_path: str | None = None,
        conflict_strategy: str = "abort",
    ) -> GenerateCptStepResponse:
        await self._ensure_task_columns(session)
        task = await self.get_task(session, task_id)
        if task is None:
            raise ValueError("任务不存在")
        if not task.report_dsl:
            raise ValueError("请先完成第二步 ReportDSL 生成")
        if not task.query_sql:
            raise ValueError("任务缺少 SQL，无法生成 CPT")

        logs = list(task.generation_log or [])
        logs.append(self._log("开始执行 FineReport AI 报表第三步：生成 CPT 并写入目标 reportlets 路径"))
        task.status = FrAiReportTaskStatus.GENERATING
        task.generation_log = logs
        task.update_time = datetime.now()
        session.add(task)
        await session.commit()
        await session.refresh(task)

        try:
            dsl = ReportDSL.model_validate(task.report_dsl)
            validation_warnings = dsl_validator.validate(dsl)
            logs.append(self._log("ReportDSL 校验通过，开始确定性生成 CPT"))

            cpt_bytes = cpt_generator.generate(dsl)
            logs.append(self._log("确定性 CPT 生成完成"))

            normalized_target = fr_report_version_control_service.normalize_target_object_path(
                report_name=report_name or task.report_name,
                target_folder=target_folder,
                target_object_path=target_object_path,
                fallback_object_path=task.cpt_object_path,
            )
            project, structure_version, file_version, conflict = await fr_report_version_control_service.save_task_file_version(
                db=session,
                user_id=user_id,
                task=task,
                cpt_bytes=cpt_bytes,
                dsl_payload=dsl.model_dump(mode="json"),
                generation_log=logs,
                target_object_path=normalized_target,
                conflict_strategy=conflict_strategy,
                validation_warnings=validation_warnings,
            )
            if conflict:
                logs.append(self._log(f"检测到目标 CPT 外部修改，已阻止覆盖：{conflict.get('message', '')}"))
                task.status = FrAiReportTaskStatus.VALIDATION_FAILED
                task.cpt_object_path = normalized_target
                task.warnings = validation_warnings + [conflict.get("message", "检测到目标 CPT 外部修改，已阻止覆盖")]
                task.errors = []
                task.generation_log = logs
                task.update_time = datetime.now()
                session.add(task)
                await session.commit()
                await session.refresh(task)
                response = self.to_cpt_step_schema(task)
                response.status = "conflict"
                response.reportId = project.report_id
                response.conflict = conflict
                return response

            if not file_version:
                raise ValueError("文件版本保存失败")

            logs.append(self._log("CPT、DSL、manifest 和 diff 已写入目标路径并归档到版本库"))

            reportlet_path = fr_report_version_control_service.reportlet_path(normalized_target)
            preview_result = await preview_validator.validate(reportlet_path, write_mode=dsl.writeBack.enabled)
            if preview_result.errors:
                logs.append(self._log("FineReport 预览校验未通过"))
            else:
                logs.append(self._log("FineReport 预览地址生成完成"))

            file_version.preview_url = preview_result.previewUrl
            file_version.warnings = validation_warnings + preview_result.warnings
            file_version.errors = preview_result.errors
            file_version.write_status = "generated" if not preview_result.errors else "preview_failed"
            session.add(file_version)

            sql_validation = task.sql_validation or {}
            sql_errors = list(sql_validation.get("errors", []))
            sql_warnings = list(sql_validation.get("warnings", []))
            task.report_type = dsl.reportType.value
            task.cpt_object_path = normalized_target
            task.dsl_object_path = file_version.dsl_object_path
            task.sql_object_path = None
            task.create_sql_object_path = None
            task.log_object_path = file_version.manifest_object_path
            task.preview_url = preview_result.previewUrl
            task.warnings = validation_warnings + sql_warnings + preview_result.warnings
            task.errors = sql_errors + preview_result.errors
            task.status = FrAiReportTaskStatus.VALIDATED if not task.errors else FrAiReportTaskStatus.VALIDATION_FAILED
            task.generation_log = logs
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
            response = self.to_cpt_step_schema(task)
            response.reportId = project.report_id
            response.fileVersionId = file_version.file_version_id
            response.structureVersionId = structure_version.structure_version_id if structure_version else None
            return response
        except DslValidationError as exc:
            task.status = FrAiReportTaskStatus.FAILED
            task.errors = exc.errors
            task.warnings = exc.warnings
            task.generation_log = logs + [self._log("第三步 ReportDSL 校验失败，未生成 CPT")]
            task.update_time = datetime.now()
            session.add(task)
            await session.commit()
            await session.refresh(task)
            return self.to_cpt_step_schema(task)
        except Exception as exc:
            logger.exception(f"FineReport AI CPT 步骤生成失败：{exc}")
            task.status = FrAiReportTaskStatus.FAILED
            task.errors = [str(exc)]
            task.generation_log = logs + [self._log("第三步执行异常")]
            task.update_time = datetime.now()
            session.add(task)
            await session.commit()
            await session.refresh(task)
            return self.to_cpt_step_schema(task)

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

        if not task.cpt_object_path:
            raise ValueError("任务尚未生成 CPT 文件")
        reportlet_path = fr_report_version_control_service.reportlet_path(task.cpt_object_path)
        write_mode = False
        if task.report_dsl:
            write_mode = ReportDSL.model_validate(task.report_dsl).writeBack.enabled
        result = await preview_validator.validate(reportlet_path, write_mode=write_mode)
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
        warnings.append("安全策略：publish 仅标记任务已发布；真实 CPT 写入、覆盖和回档必须继续通过版本控制与外部修改检测。")
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
            createTableSql=task.create_table_sql,
            warnings=task.warnings or [],
            errors=task.errors or [],
            createTime=task.create_time,
            updateTime=task.update_time,
        )

    def _merge_agent_context(self, context: FrAiReportAgentContext, message: str) -> FrAiReportAgentContext:
        next_context = context.model_copy(deep=True)
        text_value = message.strip()
        if text_value:
            if self._is_fresh_report_request(text_value):
                next_context.requirement = text_value
                next_context.taskId = None
                next_context.conversationId = None
                next_context.sourceTableName = None
            elif next_context.requirement:
                if text_value not in next_context.requirement:
                    next_context.requirement = f"{next_context.requirement}\n{text_value}".strip()
            else:
                next_context.requirement = text_value
        extracted_report_name = self._match_agent_text(
            message,
            [
                r"(?:报表名|报表名称|名称)\s*[：:]\s*([^\n，,。；;]+)",
                r"(?:生成|新建|做)(?:一个|一张)?\s*([^\n，,。；;]{2,40}?报表)",
            ],
        )
        if extracted_report_name:
            next_context.reportName = extracted_report_name.strip().removesuffix(".cpt")
        extracted_folder = self._match_agent_text(
            message,
            [
                r"(?:目录|路径|保存到|放到|生成到|存放位置)\s*[：:]\s*([^\n，。；;]+)",
                r"(webroot/APP/reportlets/[^\s，。；;]+)",
            ],
        )
        if extracted_folder:
            next_context.targetFolder = self._normalize_agent_folder(extracted_folder)
        extracted_tables = self._match_agent_text(
            message,
            [
                r"(?:已有表|数据表|来源表|相关表|用表|表名)\s*[：:]\s*([A-Za-z0-9_\.\[\]，,、；;\s]+)",
                r"(?:使用|读取|基于)\s*([A-Za-z0-9_\.\[\]，,、；;\s]{3,})\s*(?:这些表|这几个表|做报表)",
            ],
        )
        if extracted_tables:
            next_context.sourceTableName = extracted_tables.strip(" ，,、；;")
        if not next_context.ddlDialect:
            next_context.ddlDialect = "sqlserver"
        return next_context

    def _build_agent_requirement(self, context: FrAiReportAgentContext, message: str) -> str:
        parts = []
        if context.requirement:
            parts.append(context.requirement.strip())
        if message.strip() and message.strip() not in parts:
            parts.append(message.strip())
        if context.templateObjectPath:
            parts.append(f"参考模板：{context.templateObjectPath}")
        if context.targetFolder:
            parts.append(f"生成目录：{context.targetFolder}")
        if context.sourceTableName:
            parts.append(f"用户指定已有数据表：{context.sourceTableName}")
        return "\n".join(part for part in parts if part).strip()

    def _agent_missing_items(self, context: FrAiReportAgentContext, has_file: bool) -> list[str]:
        missing_items: list[str] = []
        if not context.reportName:
            missing_items.append("请告诉我报表名称，或者直接说“报表名：xxx”。")
        if not context.targetFolder:
            missing_items.append("请指定生成目录，例如 webroot/APP/reportlets/数据分析/AI生成报表。")
        if not context.requirement and not has_file:
            missing_items.append("请描述要生成的报表内容，或上传 Excel、Word、图片等参考资料。")
        return missing_items

    def _match_agent_text(self, text_value: str, patterns: list[str]) -> str | None:
        for pattern in patterns:
            match = re.search(pattern, text_value, flags=re.IGNORECASE)
            if match and match.group(1).strip():
                return match.group(1).strip()
        return None

    def _is_fresh_report_request(self, text_value: str) -> bool:
        normalized = re.sub(r"\s+", "", text_value)
        return bool(
            re.search(r"^(帮我|我要|请|直接)?(做|新建|生成|创建|设计)(一个|一张)?", normalized)
            or re.search(r"报表名[：:]", text_value)
        )

    def _latest_message_summary(self, text_value: str) -> str:
        text = re.sub(r"\s+", " ", text_value).strip()
        return f"我理解你的最新需求是：{text[:220]}{'...' if len(text) > 220 else ''}"

    def _normalize_agent_folder(self, value: str) -> str:
        folder = value.strip().replace("\\", "/").strip("/")
        if folder.endswith(".cpt"):
            folder = folder.rsplit("/", 1)[0]
        if folder.startswith("APP/reportlets/"):
            folder = f"webroot/{folder}"
        if folder.startswith("reportlets/"):
            folder = f"webroot/APP/{folder}"
        if not folder.startswith("webroot/APP/reportlets"):
            folder = f"webroot/APP/reportlets/{folder}"
        return re.sub(r"/+", "/", folder)

    def _build_ddl_options(
        self,
        ddl_dialect: str | None,
        id_auto_increment: bool,
        table_name_overrides: dict[str, Any] | None,
        source_table_name: str | None,
        business_plan: dict[str, Any],
    ) -> dict[str, Any]:
        dialect = (ddl_dialect or "sqlserver").strip().lower()
        if dialect in {"mssql", "sql_server"}:
            dialect = "sqlserver"
        if dialect not in {"sqlserver", "mysql", "postgresql"}:
            dialect = "sqlserver"
        overrides = {
            str(key): str(value).strip()
            for key, value in (table_name_overrides or {}).items()
            if str(key).strip() and str(value).strip()
        }
        scenario = business_plan.get("scenario")
        if source_table_name and scenario == "option_operation_ledger":
            overrides.setdefault("fr_option_trade_ledger", source_table_name.strip())
        elif source_table_name and scenario == "futures_operation_ledger":
            overrides.setdefault("fr_future_trade_ledger", source_table_name.strip())
        elif source_table_name and source_table_name.strip():
            overrides.setdefault("primary", source_table_name.strip())
        return {
            "dialect": dialect,
            "idAutoIncrement": bool(id_auto_increment),
            "tableNames": overrides,
        }

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

    def to_cpt_step_schema(self, task: FrAiReportTask) -> GenerateCptStepResponse:
        return GenerateCptStepResponse(
            taskId=task.task_id,
            conversationId=task.conversation_id,
            parentTaskId=task.parent_task_id,
            revisionNo=task.revision_no or 1,
            status=task.status.value,
            reportName=task.report_name,
            reportType=task.report_type or "",
            cptObjectPath=task.cpt_object_path,
            dslObjectPath=task.dsl_object_path,
            sqlObjectPath=task.sql_object_path,
            createSqlObjectPath=task.create_sql_object_path,
            logObjectPath=task.log_object_path,
            previewUrl=task.preview_url,
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
        allow_designed_fallback: bool = False,
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
        if allow_designed_fallback:
            logs.append(
                self._log(
                    f"未查询到真实表结构，已按沉淀场景候选模型继续生成：{', '.join(table_names)}。{detail}"
                )
            )
            return None
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

    def _supervise_generation(
        self,
        requirement_summary: dict[str, Any],
        data_model: dict[str, Any],
        query_sql: str | None,
    ) -> tuple[list[str], list[str]]:
        business_plan = requirement_summary.get("businessPlan") or {}
        if business_plan.get("scenario") != "futures_operation_ledger":
            return [], []

        warnings: list[str] = []
        errors: list[str] = []
        sql_text = query_sql or ""
        model_text = f"{data_model} {sql_text}".lower()
        required_tables = [
            "fr_future_contract_base",
            "fr_future_trade_ledger",
            "fr_future_settlement_price",
        ]
        missing_tables = [table for table in required_tables if table.lower() not in model_text]
        if missing_tables:
            errors.append(f"监工校验失败：期货台账缺少关键候选表 {', '.join(missing_tables)}。")

        required_terms = {
            "contract_variety": "合约品种组合主键",
            "tons_per_lot": "吨数/手换算率",
            "close_quantity_lot": "平仓数量",
            "remaining_quantity_lot": "剩余持仓",
            "settlement_price": "查询截止日收盘价",
            "floating_profit": "持仓浮动盈亏",
            "realized_profit": "平仓盈亏",
        }
        for term, label in required_terms.items():
            if term not in model_text:
                errors.append(f"监工校验失败：期货台账缺少 {label} 规则或字段。")

        if "${end_date}" not in sql_text:
            warnings.append("监工提示：SQL 未显式使用查询截止日期 ${end_date}，浮动盈亏可能无法按截止日计算。")
        if "${start_date}" not in sql_text:
            warnings.append("监工提示：SQL 未显式使用查询开始日期 ${start_date}，台账区间查询可能不完整。")
        if "close_quantity_lot" in sql_text and "<= t.open_quantity_lot" not in sql_text and "<= open_quantity_lot" not in sql_text:
            errors.append("监工校验失败：同一行开平仓模式下，SQL 或表约束必须校验平仓数量不超过开仓数量。")
        if data_model.get("dataSourceStatus") == "designed_not_verified":
            warnings.append("监工提示：当前使用的是 AI 设计的候选表结构，正式生成前需要用户确认真实数据库表和字段。")
        return warnings, errors

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
