import asyncio
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from pathlib import PurePosixPath
from typing import Any
from uuid import uuid4

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import String, cast, func, or_
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.llm_factory import LLMFactory
from app.core.logger import logger
from app.db.session import async_session
from app.models.agent.fr_report import FrReportCase, FrReportCaseChunk, FrReportCaseSampleJob
from app.schemas.agent.fr_report.report_case import (
    FrReportCaseChunkRead,
    FrReportCaseRead,
    FrReportCaseSampleBuildRequest,
    FrReportCaseSampleJobRead,
    FrReportCaseSearchHit,
    FrReportCaseSearchRequest,
    FrReportCaseSearchResponse,
)
from app.services.agent.fr_report.fr_minio_service import fr_minio_service
from app.services.agent.fr_report.preview_validator import preview_validator
from app.services.agent.fr_report.report_file_service import fr_report_file_service
from app.services.agent.fr_report.version_control_service import fr_report_version_control_service
from app.services.agent.insight.embedding_service import insight_embedding_service


class FrReportCaseService:
    """FineReport 样本报表自发现案例库。

    这个服务只负责把真实报表中的可复用经验沉淀成可检索资产，不把案例变成新的规则引擎。
    """

    async def start_sample_build(
        self,
        db: AsyncSession,
        payload: FrReportCaseSampleBuildRequest,
        *,
        user_id: int,
    ) -> FrReportCaseSampleJobRead:
        sample_min = max(1, min(payload.sampleMin, payload.sampleMax))
        sample_max = max(sample_min, min(payload.sampleMax, 500))
        source_prefix = self._normalize_source_prefix(payload.sourcePrefix)
        job = FrReportCaseSampleJob(
            job_id=f"fr-case-job-{uuid4().hex[:12]}",
            source_prefix=source_prefix,
            sample_min=sample_min,
            sample_max=sample_max,
            include_screenshot=payload.includeScreenshot,
            preview_success_only=payload.previewSuccessOnly,
            use_model_analysis=payload.useModelAnalysis,
            status="pending",
            create_by=str(user_id),
            update_by=str(user_id),
        )
        db.add(job)
        await db.commit()
        await db.refresh(job)
        return self._job_read(job)

    async def run_sample_build_job(self, job_id: str, *, user_id: int) -> None:
        async with async_session() as db:
            job = (await db.exec(select(FrReportCaseSampleJob).where(FrReportCaseSampleJob.job_id == job_id))).first()
            if job is None:
                logger.warning(f"FineReport 案例库初始化任务不存在: {job_id}")
                return
            try:
                job.status = "running"
                job.update_by = str(user_id)
                await db.commit()
                if job.selected_reports:
                    selected = list(job.selected_reports)
                else:
                    files = await self._scan_report_files(job.source_prefix)
                    job.total_scanned = len(files)
                    selected = await self._select_sample_reports(files, job.sample_min, job.sample_max)
                    job.selected_reports = selected
                    job.selected_count = len(selected)
                    await db.commit()

                start_index = min(max(job.analyzed_count, 0), len(selected))
                for item in selected[start_index:]:
                    job.current_object_path = str(item.get("objectPath") or "")
                    await db.commit()
                    try:
                        result = await self._analyze_sample_report(
                            db,
                            job=job,
                            item=item,
                            include_screenshot=job.include_screenshot,
                            use_model_analysis=job.use_model_analysis,
                            user_id=user_id,
                        )
                        job.analyzed_count += 1
                        job.candidate_count += result["candidate_count"]
                        job.case_count += result["case_count"]
                        job.warnings = list(job.warnings or []) + result["warnings"]
                    except Exception as exc:
                        logger.warning(f"FineReport 案例分析失败: {item.get('objectPath')} {exc}")
                        job.failed_count += 1
                        job.errors = list(job.errors or []) + [f"{item.get('objectPath')}: {exc}"]
                    await db.commit()

                actual_case_count = (
                    await db.exec(
                        select(func.count())
                        .select_from(FrReportCase)
                        .where(FrReportCase.sample_job_id == job.job_id, FrReportCase.is_deleted == 0)
                    )
                ).one()
                job.case_count = int(actual_case_count or 0)
                job.candidate_count = max(job.candidate_count, job.case_count)
                job.status = "completed" if not job.errors else "completed_with_warnings"
                job.current_object_path = None
                job.summary = {
                    "message": "样本报表分析完成，案例数量由报表中的可复用设置自然产生。",
                    "totalScanned": job.total_scanned,
                    "selectedCount": job.selected_count,
                    "analyzedCount": job.analyzed_count,
                    "candidateCount": job.candidate_count,
                    "caseCount": job.case_count,
                    "failedCount": job.failed_count,
                }
                await db.commit()
            except Exception as exc:
                logger.exception(f"FineReport 案例库初始化任务失败: {job_id}")
                job.status = "failed"
                job.errors = list(job.errors or []) + [str(exc)]
                await db.commit()

    async def get_sample_job(self, db: AsyncSession, job_id: str) -> FrReportCaseSampleJobRead:
        job = (await db.exec(select(FrReportCaseSampleJob).where(FrReportCaseSampleJob.job_id == job_id))).first()
        if job is None:
            raise ValueError("案例库初始化任务不存在")
        return self._job_read(job)

    async def search_cases(self, db: AsyncSession, payload: FrReportCaseSearchRequest) -> FrReportCaseSearchResponse:
        query = payload.query.strip()
        query_vector: list[float] = []
        vector_meta: dict[str, Any] = {"reason": "empty_query"}
        if query:
            query_vector, vector_meta = await insight_embedding_service.embed_text(db, query)

        filters = [FrReportCase.is_deleted == 0]
        if not payload.includeInactive:
            filters.append(FrReportCase.status == "active")
        if payload.sourceObjectPath:
            filters.append(FrReportCase.source_object_path == self._normalize_object_path(payload.sourceObjectPath))
        if payload.tags:
            tag_text = " ".join(payload.tags)
            filters.append(cast(FrReportCase.tags, String).ilike(f"%{tag_text}%"))
        if query and not query_vector:
            like = f"%{query}%"
            filters.append(
                or_(
                    FrReportCase.title.ilike(like),
                    FrReportCase.reason.ilike(like),
                    FrReportCase.search_text.ilike(like),
                    cast(FrReportCase.tags, String).ilike(like),
                    cast(FrReportCase.keywords, String).ilike(like),
                )
            )
        rows = list((await db.exec(select(FrReportCase).where(*filters).order_by(FrReportCase.quality_score.desc()).limit(300))).all())
        chunks = await self._chunks_for_cases(db, [row.case_id for row in rows])

        hits: list[FrReportCaseSearchHit] = []
        for row in rows:
            row_chunks = chunks.get(row.case_id, [])
            keyword_score = self._keyword_score(query, row, row_chunks)
            vector_score = self._vector_score(query_vector, row_chunks)
            score = max(keyword_score, vector_score, row.quality_score / 100 if not query else 0)
            if query and score <= 0:
                continue
            hits.append(
                FrReportCaseSearchHit(
                    case=self._case_read(row, row_chunks[:3], include_raw_xml=False),
                    score=round(score, 6),
                    matchReason="向量召回" if vector_score >= keyword_score and vector_score > 0 else "关键词/结构召回",
                )
            )
        hits.sort(key=lambda item: item.score, reverse=True)
        mode = "case_vector_rag" if query_vector else f"case_keyword_rag:{vector_meta.get('reason')}"
        return FrReportCaseSearchResponse(query=query, hits=hits[: payload.limit], generationMode=mode)

    async def get_case(self, db: AsyncSession, case_id: str) -> FrReportCaseRead:
        row = (await db.exec(select(FrReportCase).where(FrReportCase.case_id == case_id, FrReportCase.is_deleted == 0))).first()
        if row is None:
            raise ValueError("案例不存在")
        chunks = await self._chunks_for_cases(db, [row.case_id])
        return self._case_read(row, chunks.get(row.case_id, []), include_raw_xml=True)

    async def read_reference_report_full(self, *, object_path: str | None = None, case_id: str | None = None, db: AsyncSession | None = None) -> dict[str, Any]:
        target_path = object_path
        if case_id and db is not None:
            row = (await db.exec(select(FrReportCase).where(FrReportCase.case_id == case_id, FrReportCase.is_deleted == 0))).first()
            if row:
                target_path = row.source_object_path
        if not target_path:
            raise ValueError("缺少参考报表路径或案例 ID")
        normalized = self._normalize_object_path(target_path)
        data = await fr_minio_service.download_file(normalized)
        text, encoding = fr_report_file_service._decode_report_text(data)
        if not text:
            raise ValueError("参考报表不是可读取的 XML 文本")
        return {
            "objectPath": normalized,
            "encoding": encoding,
            "xmlChars": len(text),
            "fullCptXml": text,
        }

    async def read_reference_case_context(self, db: AsyncSession, query: str, *, limit: int = 3) -> dict[str, Any]:
        result = await self.search_cases(db, FrReportCaseSearchRequest(query=query, limit=limit))
        return {
            "summary": f"案例库检索完成，命中 {len(result.hits)} 条。",
            "query": query,
            "generationMode": result.generationMode,
            "hits": [hit.model_dump(mode="json") for hit in result.hits],
        }

    async def _scan_report_files(self, source_prefix: str) -> list[dict[str, Any]]:
        result = await fr_report_file_service.list_report_files(
            db=None,
            user_id=None,
            prefix=source_prefix,
            keyword=None,
            limit=5000,
            include_all=True,
        )
        items: list[dict[str, Any]] = []
        for item in result.items:
            path = item.objectPath
            if self._is_noise_path(path):
                continue
            items.append(
                {
                    "objectPath": path,
                    "reportPath": item.reportPath,
                    "fileName": item.fileName,
                    "fileType": item.fileType,
                    "size": item.size or 0,
                    "lastModified": item.lastModified.isoformat() if item.lastModified else None,
                }
            )
        return items

    async def _select_sample_reports(self, files: list[dict[str, Any]], sample_min: int, sample_max: int) -> list[dict[str, Any]]:
        if not files:
            return []
        scored: list[dict[str, Any]] = []
        for item in files:
            score, reasons = self._metadata_score(item)
            scored.append({**item, "sampleScore": score, "sampleReasons": reasons, "directoryKey": self._directory_key(str(item["objectPath"]))})
        scored.sort(key=lambda item: (item["sampleScore"], item.get("size") or 0), reverse=True)

        selected: list[dict[str, Any]] = []
        per_dir: dict[str, int] = {}
        soft_dir_limit = max(2, sample_max // 12)
        for item in scored:
            directory_key = str(item.get("directoryKey") or "")
            if per_dir.get(directory_key, 0) >= soft_dir_limit and len(selected) < sample_min:
                continue
            selected.append(item)
            per_dir[directory_key] = per_dir.get(directory_key, 0) + 1
            if len(selected) >= sample_max:
                break
        if len(selected) < sample_min:
            chosen = {item["objectPath"] for item in selected}
            for item in scored:
                if item["objectPath"] in chosen:
                    continue
                selected.append(item)
                if len(selected) >= min(sample_min, sample_max):
                    break
        return selected[:sample_max]

    async def _analyze_sample_report(
        self,
        db: AsyncSession,
        *,
        job: FrReportCaseSampleJob,
        item: dict[str, Any],
        include_screenshot: bool,
        use_model_analysis: bool,
        user_id: int,
    ) -> dict[str, Any]:
        object_path = self._normalize_object_path(str(item["objectPath"]))
        data = await fr_minio_service.download_file(object_path)
        text, encoding = fr_report_file_service._decode_report_text(data)
        if not text:
            return {"candidate_count": 0, "case_count": 0, "warnings": [f"{object_path}: 非 XML 文本，已跳过"]}
        root = ET.fromstring(text)
        structure = await self._parse_structure_unchecked(object_path, item, text, encoding, root)
        facts = self._extract_report_facts(text, structure)
        snippets = self._extract_snippet_catalog(text)
        reportlet_path = fr_report_version_control_service.reportlet_path(object_path)
        preview_url = preview_validator._preview_url(reportlet_path)
        screenshot_object_path = None
        preview_status = "not_checked"
        warnings: list[str] = []
        should_check_preview = bool(job.preview_success_only or include_screenshot)
        if should_check_preview:
            try:
                validation = await asyncio.wait_for(preview_validator.validate(reportlet_path), timeout=20)
                preview_status = "preview_ok" if not validation.errors else "preview_failed"
                warnings.extend(validation.warnings)
                if job.preview_success_only and validation.errors:
                    return {
                        "candidate_count": 0,
                        "case_count": 0,
                        "warnings": [f"{object_path}: 预览失败，已按 previewSuccessOnly 跳过。"],
                    }
            except Exception as exc:
                preview_status = "preview_check_failed"
                warnings.append(f"{object_path}: 预览校验失败：{exc}")
                if job.preview_success_only:
                    return {
                        "candidate_count": 0,
                        "case_count": 0,
                        "warnings": [f"{object_path}: 预览校验失败，已按 previewSuccessOnly 跳过。"],
                    }
        if include_screenshot and preview_status == "not_checked":
            preview_status = "preview_not_checked"
        if include_screenshot:
            screenshot_result = await self._capture_preview_screenshot(object_path, preview_url, job.job_id)
            screenshot_object_path = screenshot_result.get("screenshotObjectPath")
            warnings.extend([str(item) for item in screenshot_result.get("warnings") or []])

        candidates = []
        if use_model_analysis:
            try:
                candidates = await self._discover_case_candidates_with_model(
                    object_path=object_path,
                    report_name=str(item.get("fileName") or PurePosixPath(object_path).name),
                    structure_summary=structure["summary"],
                    facts=facts,
                    snippets=snippets,
                )
            except Exception as exc:
                warnings.append(f"{object_path}: 模型自发现失败，已使用结构事实兜底：{LLMFactory.describe_invocation_error(exc)}")
        if not candidates:
            candidates = self._discover_case_candidates_by_facts(
                object_path=object_path,
                report_name=str(item.get("fileName") or PurePosixPath(object_path).name),
                facts=facts,
                snippets=snippets,
            )

        case_count = 0
        for candidate in candidates:
            saved = await self._save_case_candidate(
                db,
                job=job,
                item=item,
                structure_summary=structure,
                candidate=candidate,
                snippets=snippets,
                preview_url=preview_url,
                preview_status=preview_status,
                screenshot_object_path=screenshot_object_path,
                user_id=user_id,
            )
            if saved:
                case_count += 1
        return {"candidate_count": len(candidates), "case_count": case_count, "warnings": warnings}

    async def _parse_structure_unchecked(
        self,
        object_path: str,
        item: dict[str, Any],
        text: str,
        encoding: str | None,
        root: ET.Element,
    ) -> dict[str, Any]:
        datasets = fr_report_file_service._parse_table_datasets(root)
        document = fr_report_file_service._parse_report_document(root)
        tag_counts = fr_report_file_service._count_tags(root)
        summary = {
            "datasetCount": len(datasets),
            "parameterCount": tag_counts.get("Parameter", 0),
            "widgetCount": tag_counts.get("Widget", 0),
            "queryCount": sum(1 for dataset in datasets if dataset.querySql),
            "sheetCount": len(document.sheets),
            "cellCount": sum(len(sheet.cells) for sheet in document.sheets),
            "mergeCount": sum(len(sheet.merges) for sheet in document.sheets),
            "xmlChars": len(text),
            "rootTag": root.tag,
        }
        return {
            "objectPath": object_path,
            "reportPath": item.get("reportPath") or fr_report_file_service._to_report_path(object_path),
            "fileName": item.get("fileName") or PurePosixPath(object_path).name,
            "fileType": item.get("fileType") or PurePosixPath(object_path).suffix.lstrip("."),
            "encoding": encoding,
            "summary": summary,
            "datasets": [dataset.model_dump(mode="json") for dataset in datasets[:20]],
            "parameters": [
                widget.model_dump(mode="json")
                for widget in ((document.parameterPanel.widgets if document.parameterPanel else [])[:80])
            ],
            "sheets": [
                {
                    "name": sheet.name,
                    "rowCount": sheet.rowCount,
                    "columnCount": sheet.columnCount,
                    "cellCount": len(sheet.cells),
                    "mergeCount": len(sheet.merges),
                }
                for sheet in document.sheets[:5]
            ],
            "warnings": fr_report_file_service._document_warnings(document),
        }

    def _extract_report_facts(self, source_xml: str, structure: dict[str, Any]) -> dict[str, Any]:
        patterns = {
            "parameterPanel": r"<ReportParameterAttr\b|<ParameterUI\b",
            "widget": r"<Widget\b|WidgetInfo|ComboBox|TextEditor|DateEditor",
            "comboOrDictionary": r"ComboBox|Dictionary|DataDictionary|dataDictionary|widgetValue",
            "dataset": r"<TableData\b|<TableDataMap\b|<Query\b",
            "script": r"<JavaScript|<Script|Event|onclick|onClick|function\s*\(",
            "writeback": r"ReportWriteAttr|Submit|SubmitJob|TableSubmit|ReportWebAttr",
            "style": r"<StyleList\b|<Style\b|Border|Background|Font",
            "hiddenRowColumn": r"<HC\b|<HR\b|visible=\"false\"",
            "horizontalExpansion": r"dir=\"right\"|dir=\"horizontal\"|Expand[^>]+right",
            "verticalExpansion": r"dir=\"down\"|dir=\"vertical\"|Expand[^>]+down",
            "dateFormat": r"DateFormat|yyyy|MM|dd|日期",
            "condition": r"<Condition|ConditionAttr|Highlight|条件",
            "chart": r"<Chart|ChartAttr|WidgetChart",
        }
        counts = {name: len(re.findall(pattern, source_xml, flags=re.I | re.S)) for name, pattern in patterns.items()}
        interesting = [name for name, count in counts.items() if count > 0 and name not in {"dataset", "style"}]
        return {
            "counts": counts,
            "interestingSignals": interesting,
            "structureSummary": structure["summary"],
            "datasetNames": [item.get("name") for item in structure.get("datasets", [])][:20],
            "parameterNames": [item.get("name") for item in structure.get("parameters", [])][:30],
        }

    def _extract_snippet_catalog(self, source_xml: str) -> list[dict[str, Any]]:
        specs = [
            ("parameter", r"<ReportParameterAttr\b[^>]*(?:/>|>.*?</ReportParameterAttr>)"),
            ("parameter_ui", r"<ParameterUI\b[^>]*(?:/>|>.*?</ParameterUI>)"),
            ("report_page", r"<ReportPageAttr\b[^>]*(?:/>|>.*?</ReportPageAttr>)"),
            ("table_data_map", r"<TableDataMap\b[^>]*(?:/>|>.*?</TableDataMap>)"),
            ("table_data", r"<TableData\b[^>]*(?:/>|>.*?</TableData>)"),
            ("style", r"<StyleList\b[^>]*(?:/>|>.*?</StyleList>)"),
            ("writeback", r"<ReportWriteAttr\b[^>]*(?:/>|>.*?</ReportWriteAttr>)"),
            ("web_attr", r"<ReportWebAttr\b[^>]*(?:/>|>.*?</ReportWebAttr>)"),
            ("script", r"<JavaScript\b[^>]*(?:/>|>.*?</JavaScript>)"),
            ("cell_widget", r"<C\b(?=[^>]*(?:Widget|DSColumn|Expand|DateFormat|Visible))[^>]*(?:/>|>.*?</C>)"),
        ]
        snippets: list[dict[str, Any]] = []
        for snippet_type, pattern in specs:
            for index, match in enumerate(re.finditer(pattern, source_xml, flags=re.S | re.I)):
                raw_xml = match.group(0)
                title = self._snippet_title(snippet_type, raw_xml, index)
                snippets.append(
                    {
                        "snippetId": f"{snippet_type}-{index + 1}",
                        "type": snippet_type,
                        "title": title,
                        "selector": self._snippet_selector(snippet_type, raw_xml, index),
                        "summary": self._xml_to_summary(raw_xml),
                        "rawXml": self._compact(raw_xml, 30000),
                        "tags": self._snippet_tags(snippet_type, raw_xml),
                    }
                )
                if len([item for item in snippets if item["type"] == snippet_type]) >= 8:
                    break
        return snippets[:80]

    async def _discover_case_candidates_with_model(
        self,
        *,
        object_path: str,
        report_name: str,
        structure_summary: dict[str, Any],
        facts: dict[str, Any],
        snippets: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        payload = {
            "objectPath": object_path,
            "reportName": report_name,
            "structureSummary": structure_summary,
            "facts": facts,
            "snippetCatalog": [
                {key: value for key, value in item.items() if key != "rawXml"}
                for item in snippets[:40]
            ],
            "instruction": (
                "请像资深 FineReport 工程师整理案例库一样，只从这份报表中主动发现真正值得沉淀的场景写法。"
                "不要预设必须产出哪些类型，也不要为了凑数量生成普通案例。"
                "每个候选必须能说明为什么可复用，并引用 snippetId 作为证据。没有价值就返回空数组。"
            ),
            "expectedJson": {
                "cases": [
                    {
                        "title": "案例标题",
                        "scenario": "适用场景",
                        "reason": "为什么值得沉淀",
                        "tags": ["自动标签"],
                        "keywords": ["检索关键词"],
                        "qualityScore": 0,
                        "snippetIds": ["parameter-1"],
                    }
                ]
            },
        }
        response = await LLMFactory.safe_invoke(
            [
                SystemMessage(content="你是 FineReport 报表案例库自发现分析器。只返回严格 JSON。"),
                HumanMessage(content=json.dumps(payload, ensure_ascii=False)),
            ],
            capability="complex-reasoning",
            temperature=0,
            json_mode=True,
            enable_reasoning=False,
            max_retries=2,
            langfuse_run_name="fr_report_case_discovery",
            langfuse_tags=["fr-report-case-library", "case-discovery"],
            langfuse_metadata={"object_path": object_path},
        )
        content = getattr(response, "content", response)
        if isinstance(content, list):
            content = "".join(str(item) for item in content)
        data = json.loads(self._strip_json_fence(str(content)))
        raw_cases = data.get("cases") if isinstance(data, dict) else []
        if not isinstance(raw_cases, list):
            return []
        return [item for item in raw_cases if isinstance(item, dict)][:12]

    def _discover_case_candidates_by_facts(
        self,
        *,
        object_path: str,
        report_name: str,
        facts: dict[str, Any],
        snippets: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        counts = facts.get("counts") if isinstance(facts.get("counts"), dict) else {}
        signal_score = sum(1 for key, value in counts.items() if key not in {"dataset", "style"} and int(value or 0) > 0)
        if signal_score <= 0:
            return []
        rich_snippets = [
            item for item in snippets
            if item.get("type") not in {"table_data", "style"} or len(str(item.get("summary") or "")) > 80
        ][:8]
        if not rich_snippets:
            return []
        tags = sorted({tag for item in rich_snippets for tag in item.get("tags", [])})
        return [
            {
                "title": f"{report_name} 中的可复用报表写法",
                "scenario": "从真实 CPT 中自发现的复杂设置",
                "reason": "该报表包含区别于普通明细表的参数、控件、扩展、隐藏、填报或脚本等设置，适合作为后续修改时的参考写法。",
                "tags": tags[:12],
                "keywords": [report_name, *tags[:12]],
                "qualityScore": min(80, 45 + signal_score * 5),
                "snippetIds": [str(item.get("snippetId")) for item in rich_snippets],
            }
        ]

    async def _save_case_candidate(
        self,
        db: AsyncSession,
        *,
        job: FrReportCaseSampleJob,
        item: dict[str, Any],
        structure_summary: dict[str, Any],
        candidate: dict[str, Any],
        snippets: list[dict[str, Any]],
        preview_url: str,
        preview_status: str,
        screenshot_object_path: str | None,
        user_id: int,
    ) -> bool:
        snippet_ids = {str(value) for value in candidate.get("snippetIds", []) if value}
        selected_snippets = [item for item in snippets if str(item.get("snippetId")) in snippet_ids]
        if not selected_snippets:
            selected_snippets = snippets[:2]
        title = str(candidate.get("title") or "").strip()
        reason = str(candidate.get("reason") or "").strip()
        if not title or not reason:
            return False
        source_object_path = self._normalize_object_path(str(item["objectPath"]))
        tags = self._clean_words(candidate.get("tags") or [])
        keywords = self._clean_words(candidate.get("keywords") or []) + tags
        search_text = "\n".join(
            [
                title,
                str(candidate.get("scenario") or ""),
                reason,
                " ".join(tags),
                " ".join(keywords),
                "\n".join(str(snippet.get("summary") or "") for snippet in selected_snippets),
            ]
        )
        content_hash = self._hash_text(f"{source_object_path}\n{title}\n{reason}\n{[item.get('selector') for item in selected_snippets]}")
        existing = (
            await db.exec(
                select(FrReportCase).where(
                    FrReportCase.content_hash == content_hash,
                    FrReportCase.is_deleted == 0,
                )
            )
        ).first()
        if existing:
            return False
        row = FrReportCase(
            case_id=f"fr-case-{uuid4().hex[:12]}",
            sample_job_id=job.job_id,
            source_object_path=source_object_path,
            report_path=str(item.get("reportPath") or fr_report_file_service._to_report_path(source_object_path)),
            report_name=str(item.get("fileName") or PurePosixPath(source_object_path).name),
            title=title,
            scenario=str(candidate.get("scenario") or "")[:500] or None,
            reason=reason[:2000],
            evidence={"snippetIds": list(snippet_ids), "source": "model" if candidate.get("snippetIds") else "facts"},
            structure_summary=structure_summary,
            snippet_refs=[
                {key: value for key, value in snippet.items() if key != "rawXml"}
                for snippet in selected_snippets
            ],
            tags=tags,
            keywords=sorted(set(keywords)),
            search_text=search_text[:12000],
            content_hash=content_hash,
            quality_score=float(candidate.get("qualityScore") or 50),
            preview_url=preview_url,
            preview_status=preview_status,
            screenshot_object_path=screenshot_object_path,
            status="active",
            create_by=str(user_id),
            update_by=str(user_id),
        )
        db.add(row)
        await db.flush()
        for snippet in selected_snippets:
            chunk_text = "\n".join([title, reason, str(snippet.get("summary") or ""), str(snippet.get("selector") or "")])
            vector, vector_meta = await insight_embedding_service.embed_text(db, chunk_text)
            db.add(
                FrReportCaseChunk(
                    chunk_id=f"fr-case-chunk-{uuid4().hex[:12]}",
                    case_id=row.case_id,
                    source_object_path=source_object_path,
                    chunk_type=str(snippet.get("type") or "snippet"),
                    title=str(snippet.get("title") or title)[:500],
                    selector=str(snippet.get("selector") or "")[:500] or None,
                    content=str(snippet.get("summary") or "")[:12000],
                    raw_xml=str(snippet.get("rawXml") or "")[:50000],
                    tags=self._clean_words(snippet.get("tags") or []) + tags,
                    search_text=chunk_text[:12000],
                    content_hash=self._hash_text(chunk_text),
                    vector=vector,
                    vector_metadata=vector_meta,
                    status="active",
                    create_by=str(user_id),
                    update_by=str(user_id),
                )
            )
        return True

    async def _capture_preview_screenshot(self, object_path: str, preview_url: str, job_id: str) -> dict[str, Any]:
        try:
            from playwright.async_api import async_playwright
        except Exception:
            return {
                "status": "screenshot_unavailable",
                "warnings": ["当前后端未安装 Playwright，已保留预览 URL，截图稍后可重新刷新。"],
            }
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page(viewport={"width": 1440, "height": 900})
                await page.goto(preview_url, wait_until="networkidle", timeout=30000)
                data = await page.screenshot(full_page=True, type="png")
                await browser.close()
            safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", PurePosixPath(object_path).stem)[:80]
            screenshot_object_path = f"_ai_assets/fr_report_cases/{job_id}/{safe_name}-{uuid4().hex[:8]}.png"
            await fr_minio_service.upload_file(data, screenshot_object_path, "image/png")
            return {"status": "screenshot_captured", "screenshotObjectPath": screenshot_object_path, "warnings": []}
        except Exception as exc:
            return {"status": "screenshot_failed", "warnings": [f"预览截图失败：{exc}"]}

    async def _chunks_for_cases(self, db: AsyncSession, case_ids: list[str]) -> dict[str, list[FrReportCaseChunk]]:
        if not case_ids:
            return {}
        rows = list(
            (
                await db.exec(
                    select(FrReportCaseChunk).where(
                        FrReportCaseChunk.case_id.in_(case_ids),
                        FrReportCaseChunk.is_deleted == 0,
                        FrReportCaseChunk.status == "active",
                    )
                )
            ).all()
        )
        result: dict[str, list[FrReportCaseChunk]] = {}
        for row in rows:
            result.setdefault(row.case_id, []).append(row)
        return result

    def _metadata_score(self, item: dict[str, Any]) -> tuple[float, list[str]]:
        path = str(item.get("objectPath") or "")
        size = int(item.get("size") or 0)
        reasons: list[str] = []
        score = 10.0
        if size > 200_000:
            score += 25
            reasons.append("文件较大，可能包含复杂结构")
        elif size > 80_000:
            score += 15
            reasons.append("文件中等偏大")
        if any(keyword in path for keyword in ["填报", "台账", "明细", "周报", "月报", "报价", "库存", "成本", "利润"]):
            score += 12
            reasons.append("路径包含业务模板特征")
        score += min(path.count("/"), 8)
        return score, reasons

    def _directory_key(self, object_path: str) -> str:
        parts = PurePosixPath(object_path).parts
        try:
            index = parts.index("数据分析")
            return "/".join(parts[index : index + 3])
        except ValueError:
            return "/".join(parts[:4])

    def _keyword_score(self, query: str, row: FrReportCase, chunks: list[FrReportCaseChunk]) -> float:
        if not query:
            return row.quality_score / 100
        terms = [term for term in re.split(r"\s+", query.lower()) if term]
        if not terms:
            return 0
        haystack = "\n".join(
            [
                row.title,
                row.reason or "",
                row.search_text or "",
                " ".join(row.tags or []),
                " ".join(row.keywords or []),
                "\n".join(chunk.search_text or "" for chunk in chunks),
            ]
        ).lower()
        matched = sum(1 for term in terms if term in haystack)
        return matched / max(len(terms), 1)

    def _vector_score(self, query_vector: list[float], chunks: list[FrReportCaseChunk]) -> float:
        if not query_vector:
            return 0
        return max((insight_embedding_service.cosine_similarity(query_vector, chunk.vector) for chunk in chunks if chunk.vector), default=0)

    def _case_read(self, row: FrReportCase, chunks: list[FrReportCaseChunk], *, include_raw_xml: bool) -> FrReportCaseRead:
        return FrReportCaseRead(
            caseId=row.case_id,
            sampleJobId=row.sample_job_id,
            sourceObjectPath=row.source_object_path,
            reportPath=row.report_path,
            reportName=row.report_name,
            title=row.title,
            scenario=row.scenario,
            reason=row.reason,
            evidence=row.evidence or {},
            structureSummary=row.structure_summary or {},
            snippetRefs=row.snippet_refs or [],
            tags=row.tags or [],
            keywords=row.keywords or [],
            searchText=row.search_text,
            qualityScore=row.quality_score,
            previewUrl=row.preview_url,
            previewStatus=row.preview_status,
            screenshotObjectPath=row.screenshot_object_path,
            status=row.status,
            createTime=row.create_time,
            updateTime=row.update_time,
            chunks=[self._chunk_read(chunk, include_raw_xml=include_raw_xml) for chunk in chunks],
        )

    def _chunk_read(self, row: FrReportCaseChunk, *, include_raw_xml: bool) -> FrReportCaseChunkRead:
        return FrReportCaseChunkRead(
            chunkId=row.chunk_id,
            caseId=row.case_id,
            sourceObjectPath=row.source_object_path,
            chunkType=row.chunk_type,
            title=row.title,
            selector=row.selector,
            content=row.content,
            rawXml=row.raw_xml if include_raw_xml else None,
            tags=row.tags or [],
            searchText=row.search_text,
            status=row.status,
        )

    def _job_read(self, job: FrReportCaseSampleJob) -> FrReportCaseSampleJobRead:
        return FrReportCaseSampleJobRead(
            jobId=job.job_id,
            sourcePrefix=job.source_prefix,
            sampleMin=job.sample_min,
            sampleMax=job.sample_max,
            includeScreenshot=job.include_screenshot,
            previewSuccessOnly=job.preview_success_only,
            useModelAnalysis=job.use_model_analysis,
            status=job.status,
            totalScanned=job.total_scanned,
            selectedCount=job.selected_count,
            analyzedCount=job.analyzed_count,
            candidateCount=job.candidate_count,
            caseCount=job.case_count,
            failedCount=job.failed_count,
            currentObjectPath=job.current_object_path,
            summary=job.summary or {},
            selectedReports=job.selected_reports or [],
            warnings=job.warnings or [],
            errors=job.errors or [],
            createTime=job.create_time,
            updateTime=job.update_time,
        )

    def _snippet_title(self, snippet_type: str, raw_xml: str, index: int) -> str:
        name = self._regex_first(raw_xml, r'\bname="([^"]+)"') or self._regex_first(raw_xml, r'\bclass="([^"]+)"')
        return f"{snippet_type} {name or index + 1}"

    def _snippet_selector(self, snippet_type: str, raw_xml: str, index: int) -> str:
        if snippet_type == "table_data":
            name = self._regex_first(raw_xml, r'\bname="([^"]+)"')
            if name:
                return f'TableData[name="{name}"]'
        if snippet_type == "cell_widget":
            column = self._regex_first(raw_xml, r'\bc="(\d+)"')
            row = self._regex_first(raw_xml, r'\br="(\d+)"')
            if column is not None and row is not None:
                return f"cell:{self._column_label(int(column) + 1)}{int(row) + 1}"
        return snippet_type if index == 0 else f"{snippet_type}:{index + 1}"

    def _snippet_tags(self, snippet_type: str, raw_xml: str) -> list[str]:
        tags = {snippet_type}
        marker_map = {
            "下拉": r"ComboBox|Dictionary|dataDictionary",
            "填报": r"ReportWriteAttr|Submit|ReportWebAttr",
            "脚本": r"JavaScript|Script|function",
            "隐藏行列": r"<HC\b|<HR\b|visible=\"false\"",
            "横向扩展": r"dir=\"right\"|horizontal",
            "日期格式": r"DateFormat|yyyy|MM|dd",
            "数据集": r"TableData|Query",
        }
        for label, pattern in marker_map.items():
            if re.search(pattern, raw_xml, flags=re.I | re.S):
                tags.add(label)
        return sorted(tags)

    def _xml_to_summary(self, raw_xml: str) -> str:
        text = re.sub(r"\s+", " ", raw_xml).strip()
        return self._compact(text, 1200)

    def _clean_words(self, value: Any) -> list[str]:
        raw = value if isinstance(value, list) else [value]
        result: list[str] = []
        for item in raw:
            text = str(item or "").strip()
            if text and text not in result:
                result.append(text[:80])
        return result[:30]

    def _normalize_source_prefix(self, value: str) -> str:
        prefix = fr_report_file_service._normalize_prefix(value or "webroot/APP/reportlets/数据分析")
        return prefix.rstrip("/")

    def _normalize_object_path(self, value: str) -> str:
        return fr_report_version_control_service.normalize_target_object_path(
            report_name=None,
            target_folder=None,
            target_object_path=value,
            fallback_object_path=value,
        )

    def _is_noise_path(self, value: str) -> bool:
        return any(part in value for part in ["/版本库/", "/回收站/", "/_ai_assets/", "/AI生成报表/"])

    def _compact(self, value: str, limit: int) -> str:
        if len(value) <= limit:
            return value
        return value[:limit] + "\n...已截断，完整内容仍保留在来源 CPT 中。"

    def _hash_text(self, text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _strip_json_fence(self, text: str) -> str:
        value = text.strip()
        if value.startswith("```"):
            value = re.sub(r"^```(?:json)?", "", value, flags=re.I).strip()
            value = re.sub(r"```$", "", value).strip()
        return value

    def _regex_first(self, text: str, pattern: str) -> str | None:
        match = re.search(pattern, text, flags=re.I | re.S)
        return match.group(1) if match else None

    def _column_label(self, column: int) -> str:
        label = ""
        current = max(1, column)
        while current:
            current, remainder = divmod(current - 1, 26)
            label = chr(65 + remainder) + label
        return label


fr_report_case_service = FrReportCaseService()
