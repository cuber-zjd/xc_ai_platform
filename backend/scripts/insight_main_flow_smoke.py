import asyncio
from datetime import datetime
from uuid import uuid4

from sqlmodel import select

from app.db.session import async_session
from app.models.agent.insight import (
    InsightCandidateReviewStatus,
    InsightCompany,
    InsightCrawlerChannel,
    InsightCrawlResult,
    InsightCrawlStatus,
    InsightDataSource,
    InsightIntelligence,
    InsightIntelligenceCandidate,
    InsightIntelligenceSource,
    InsightReport,
    InsightReportMaterial,
    InsightReportVersion,
    InsightReviewRecord,
    InsightSubjectType,
    InsightTask,
    InsightTaskStatus,
    InsightUserIntelligencePool,
    InsightVisibilityRule,
)
from app.models.system.sys_user import SysUser
from app.schemas.agent.insight.data_source import InsightDataSourceCreate
from app.schemas.agent.insight.intelligence import (
    InsightCandidatePromoteRequest,
    InsightIntelligenceCreate,
    InsightIntelligenceSourceCreate,
    InsightIntelligenceUpdate,
    InsightPoolUpsertRequest,
)
from app.schemas.agent.insight.report import InsightReportGenerateRequest
from app.services.agent.insight.data_source_service import insight_data_source_service
from app.services.agent.insight.intelligence_service import insight_intelligence_service
from app.services.agent.insight.report_service import insight_report_service


MARK = "insight-main-flow-smoke"


async def main() -> None:
    token = uuid4().hex[:10]
    created: dict[str, list[int]] = {
        "users": [],
        "companies": [],
        "data_sources": [],
        "tasks": [],
        "crawl_results": [],
        "candidates": [],
        "intelligences": [],
        "sources": [],
        "pools": [],
        "reports": [],
        "report_materials": [],
        "report_versions": [],
        "review_records": [],
        "rules": [],
    }
    async with async_session() as db:
        try:
            owner = await create_user(db, token, "owner", created)
            viewer = await create_user(db, token, "viewer", created)
            editor = await create_user(db, token, "editor", created)
            outsider = await create_user(db, token, "outsider", created)

            company = InsightCompany(
                company_code=f"main_flow_company_{token}",
                name=f"主链路烟测企业{token}",
                owner_user_id=owner.id,
                create_by=MARK,
                update_by=MARK,
            )
            db.add(company)
            await db.flush()
            created["companies"].append(company.id or 0)

            data_source = InsightDataSource(
                source_code=f"main_flow_source_{token}",
                source_name=f"主链路烟测数据源{token}",
                source_type="web_page",
                base_url="https://example.com/insight-main-flow",
                company_id=company.id,
                owner_user_id=owner.id,
                visibility_scope="private",
                status="enabled",
                create_by=MARK,
                update_by=MARK,
            )
            db.add(data_source)
            await db.flush()
            created["data_sources"].append(data_source.id or 0)

            await grant_rule(db, "data_source", data_source.id or 0, "user", viewer.id, "view", created)
            await grant_rule(db, "data_source", data_source.id or 0, "user", editor.id, "edit", created)

            task = InsightTask(
                task_uid=f"main_flow_task_{token}",
                task_type="manual_url_crawl",
                data_source_id=data_source.id,
                status=InsightTaskStatus.SUCCESS,
                progress=100,
                started_at=datetime.now(),
                finished_at=datetime.now(),
                input_payload={"smoke": True, "token": token},
                create_by=MARK,
                update_by=MARK,
            )
            db.add(task)
            await db.flush()
            created["tasks"].append(task.id or 0)

            crawl_result = InsightCrawlResult(
                task_id=task.id or 0,
                data_source_id=data_source.id,
                channel=InsightCrawlerChannel.FIRECRAWL,
                query_text=f"主链路烟测{token}",
                source_url=f"https://example.com/insight-main-flow/{token}",
                source_title=f"主链路烟测采集标题{token}",
                snippet="用于验证候选审核、正式情报、素材池和报告草稿的临时内容。",
                markdown_content="该临时内容用于验证 Insight 核心业务闭环，不代表真实市场洞察。",
                published_at=datetime.now(),
                dedupe_hash=f"main-flow-{token}",
                crawl_metadata={
                    "smoke": True,
                    "quality_report": {
                        "score": 0.4,
                        "issues": ["正文过短", "疑似重复"],
                        "auto_ignore": True,
                    },
                },
                status=InsightCrawlStatus.PARSED,
                create_by=MARK,
                update_by=MARK,
            )
            db.add(crawl_result)
            await db.flush()
            created["crawl_results"].append(crawl_result.id or 0)

            candidate = InsightIntelligenceCandidate(
                crawl_result_id=crawl_result.id or 0,
                candidate_title=f"主链路烟测候选情报{token}",
                candidate_summary="验证候选情报审核转正后可沉淀为报告素材。",
                subject_type=InsightSubjectType.COMPANY,
                subject_name=company.name,
                company_id=company.id,
                intelligence_type="市场动态",
                suggested_tags=[{"name": "主链路烟测", "source": "acceptance"}],
                confidence=0.92,
                review_status=InsightCandidateReviewStatus.PENDING,
                status="active",
                create_by=MARK,
                update_by=MARK,
            )
            db.add(candidate)
            await db.commit()
            await db.refresh(candidate)
            created["candidates"].append(candidate.id or 0)

            checks: list[tuple[str, bool]] = []
            await check_data_source_validation(db, token, owner.id or 0, created, checks)

            owner_candidates = await list_candidates(db, token, owner.id or 0)
            owner_candidate = next((item for item in owner_candidates.items if item.id == candidate.id), None)
            checks.append(("候选返回质量分", bool(owner_candidate and owner_candidate.quality_score == 0.4)))
            checks.append(("候选返回质量问题原因", bool(owner_candidate and "正文过短" in owner_candidate.quality_issues)))
            checks.append(("候选返回自动忽略建议", bool(owner_candidate and owner_candidate.quality_auto_ignore)))
            checks.append(("owner 能看到候选情报", contains_id(owner_candidates.items, candidate.id)))
            outsider_candidates = await list_candidates(db, token, outsider.id or 0)
            checks.append(("无权用户看不到候选情报", not contains_id(outsider_candidates.items, candidate.id)))
            viewer_candidates = await list_candidates(db, token, viewer.id or 0)
            checks.append(("view 授权用户能看到候选情报", contains_id(viewer_candidates.items, candidate.id)))

            try:
                await insight_intelligence_service.promote_candidate(
                    db,
                    candidate.id,
                    InsightCandidatePromoteRequest(review_comment="view 用户不应能转正"),
                    viewer.id,
                    is_admin=False,
                )
                checks.append(("view 授权用户不能转正候选", False))
            except ValueError:
                checks.append(("view 授权用户不能转正候选", True))

            response = await insight_intelligence_service.promote_candidate(
                db,
                candidate.id,
                InsightCandidatePromoteRequest(
                    review_comment="主链路烟测：edit 用户转正候选",
                    visibility_scope="private",
                    importance_level="medium",
                ),
                editor.id,
                is_admin=False,
            )
            intelligence_id = response.intelligence.id if response.intelligence else None
            checks.append(("edit 授权用户可转正候选", intelligence_id is not None))
            if intelligence_id:
                created["intelligences"].append(intelligence_id)
                await collect_related_ids(db, intelligence_id, created)
                await check_intelligence_maintenance(
                    db,
                    intelligence_id,
                    data_source.id or 0,
                    token,
                    viewer.id or 0,
                    owner.id or 0,
                    editor.id or 0,
                    outsider.id or 0,
                    created,
                    checks,
                )
                material_folder = f"主链路烟测素材{token}"
                noise_intelligence = await create_noise_intelligence(db, token, editor.id or 0, created)
                await check_pool_isolation(
                    db,
                    intelligence_id,
                    noise_intelligence.id or 0,
                    material_folder,
                    token,
                    editor.id or 0,
                    created,
                    checks,
                )

                pool = await insight_intelligence_service.upsert_user_pool(
                    db,
                    intelligence_id,
                    InsightPoolUpsertRequest(
                        pool_type="report_material",
                        folder_name=material_folder,
                        note="主链路烟测自动加入报告素材池",
                    ),
                    user_id=editor.id or 0,
                )
                created["pools"].append(pool.id or 0)
                checks.append(("正式情报可加入报告素材池", pool.intelligence_id == intelligence_id))

                async def generate_with_rules(payload, materials, template):
                    return insight_report_service._fallback_content(payload, materials, template), "rules"

                insight_report_service._generate_content = generate_with_rules
                report_response = await insight_report_service.generate_report(
                    db,
                    InsightReportGenerateRequest(
                        title=f"主链路烟测报告{token}",
                        folder_name=material_folder,
                        max_materials=5,
                    ),
                    user_id=editor.id or 0,
                    is_admin=False,
                )
                report_id = report_response.report.id
                created["reports"].append(report_id)
                await collect_report_related_ids(db, report_id, created)
                report_materials = report_response.report.materials
                checks.append(("素材池情报可生成报告草稿", report_response.used_material_count == 1))
                checks.append((
                    "报告生成只读取目标 report_material 文件夹",
                    bool(report_materials)
                    and all(item.intelligence_id == intelligence_id for item in report_materials)
                    and all(item.selection_source == "report_material_pool" for item in report_materials),
                ))
                try:
                    await insight_report_service.get_report_detail(
                        db,
                        report_id,
                        user_id=outsider.id or 0,
                        is_admin=False,
                    )
                    checks.append(("无权用户不能查看私有报告", False))
                except ValueError:
                    checks.append(("无权用户不能查看私有报告", True))

            failed = [name for name, ok in checks if not ok]
            for name, ok in checks:
                print(f"[{'PASS' if ok else 'FAIL'}] {name}")
            if failed:
                raise SystemExit(f"Insight 主链路烟测未通过: {'; '.join(failed)}")
        finally:
            await cleanup(db, created)


async def create_user(db, token: str, suffix: str, created: dict[str, list[int]]) -> SysUser:
    user = SysUser(
        username=f"insight_flow_{suffix}_{token}",
        full_name=f"Insight主链路烟测{suffix}{token}",
        hashed_password="acceptance-only",
        create_by=MARK,
        update_by=MARK,
    )
    db.add(user)
    await db.flush()
    created["users"].append(user.id or 0)
    return user


async def grant_rule(
    db,
    target_type: str,
    target_id: int,
    principal_type: str,
    principal_id: int | None,
    permission: str,
    created: dict[str, list[int]],
) -> None:
    rule = InsightVisibilityRule(
        target_type=target_type,
        target_id=target_id,
        principal_type=principal_type,
        principal_id=principal_id,
        permission=permission,
        create_by=MARK,
        update_by=MARK,
    )
    db.add(rule)
    await db.flush()
    created["rules"].append(rule.id or 0)


async def list_candidates(db, token: str, user_id: int):
    return await insight_intelligence_service.list_candidates(
        db,
        page=1,
        size=20,
        keyword=token,
        review_status=None,
        subject_type=None,
        intelligence_type=None,
        data_source_id=None,
        user_id=user_id,
        is_admin=False,
    )


def contains_id(items, expected_id: int | None) -> bool:
    return any(item.id == expected_id for item in items)


def contains_intelligence_id(items, expected_id: int | None) -> bool:
    return any(getattr(item, "intelligence_id", None) == expected_id for item in items)


async def check_data_source_validation(db, token: str, user_id: int, created: dict[str, list[int]], checks: list[tuple[str, bool]]) -> None:
    try:
        await insight_data_source_service.create_data_source(
            db,
            InsightDataSourceCreate(
                source_name=f"缺少 URL 网页源{token}",
                source_type="web_page",
                status="enabled",
            ),
            user_id=user_id,
        )
        checks.append(("启用网页类数据源时必须校验 URL", False))
    except ValueError:
        checks.append(("启用网页类数据源时必须校验 URL", True))

    try:
        await insight_data_source_service.create_data_source(
            db,
            InsightDataSourceCreate(
                source_name=f"缺少关键词周期源{token}",
                source_type="bocha_news",
                fetch_frequency="hourly",
                schedule_enabled=True,
                fetch_config={"max_results": 6, "crawl_top_n": 4},
            ),
            user_id=user_id,
        )
        checks.append(("周期搜索类数据源必须校验独立关键词", False))
    except ValueError:
        checks.append(("周期搜索类数据源必须校验独立关键词", True))

    saved = await insight_data_source_service.create_data_source(
        db,
        InsightDataSourceCreate(
            source_name=f"字段保存烟测源{token}",
            source_type="bocha_news",
            base_url="https://example.com/field-save",
            fetch_frequency="daily",
            schedule_enabled=False,
            visibility_scope="private",
            fetch_config={
                "keywords": ["新品"],
                "include_keywords": ["供应链"],
                "exclude_keywords": ["招聘"],
                "max_results": 7,
                "crawl_top_n": 5,
                "enable_llm_filter": True,
                "filter_prompt": "只保留与客户经营洞察相关的信息",
            },
        ),
        user_id=user_id,
    )
    created["data_sources"].append(saved.id or 0)
    saved_config = saved.fetch_config or {}
    checks.append(("数据源保存必须包含词配置", saved_config.get("include_keywords") == ["供应链"]))
    checks.append(("数据源保存 LLM 筛选开关和提示词", bool(saved_config.get("enable_llm_filter") and saved_config.get("filter_prompt"))))


async def create_noise_intelligence(db, token: str, user_id: int, created: dict[str, list[int]]) -> InsightIntelligence:
    noise = await insight_intelligence_service.create_intelligence(
        db,
        InsightIntelligenceCreate(
            title=f"主链路烟测干扰情报{token}",
            subject_type="company",
            subject_name="干扰企业",
            intelligence_type="行业资讯",
            visibility_scope="private",
            summary="不应被目标素材文件夹报告引用。",
            content="用于验证收藏、稍后看、隐藏和其他素材文件夹不会污染目标报告。",
            source=InsightIntelligenceSourceCreate(
                source_type="manual",
                source_url=f"https://example.com/insight-main-flow/noise/{token}",
                source_title=f"主链路烟测干扰来源{token}",
            ),
        ),
        user_id=user_id,
    )
    created["intelligences"].append(noise.id or 0)
    await collect_related_ids(db, noise.id or 0, created)
    return noise


async def check_pool_isolation(
    db,
    intelligence_id: int,
    noise_intelligence_id: int,
    material_folder: str,
    token: str,
    user_id: int,
    created: dict[str, list[int]],
    checks: list[tuple[str, bool]],
) -> None:
    try:
        await insight_intelligence_service.upsert_user_pool(
            db,
            intelligence_id,
            InsightPoolUpsertRequest(pool_type="typo_pool", folder_name=material_folder),
            user_id=user_id,
        )
        checks.append(("用户情报池拒绝非法池类型", False))
    except ValueError:
        checks.append(("用户情报池拒绝非法池类型", True))

    target_pool = await insight_intelligence_service.upsert_user_pool(
        db,
        intelligence_id,
        InsightPoolUpsertRequest(pool_type="report_material", folder_name=material_folder, note="主素材"),
        user_id=user_id,
    )
    favorite_pool = await insight_intelligence_service.upsert_user_pool(
        db,
        noise_intelligence_id,
        InsightPoolUpsertRequest(pool_type="favorite", folder_name=material_folder, note="干扰收藏"),
        user_id=user_id,
    )
    later_pool = await insight_intelligence_service.upsert_user_pool(
        db,
        noise_intelligence_id,
        InsightPoolUpsertRequest(pool_type="later", folder_name=material_folder, note="干扰稍后看"),
        user_id=user_id,
    )
    other_material_pool = await insight_intelligence_service.upsert_user_pool(
        db,
        noise_intelligence_id,
        InsightPoolUpsertRequest(pool_type="report_material", folder_name=f"其他素材文件夹{token}", note="其他素材文件夹"),
        user_id=user_id,
    )
    hidden_pool = await insight_intelligence_service.upsert_user_pool(
        db,
        noise_intelligence_id,
        InsightPoolUpsertRequest(pool_type="hidden", folder_name=material_folder, note="干扰隐藏"),
        user_id=user_id,
    )
    created["pools"].extend(
        [
            target_pool.id or 0,
            favorite_pool.id or 0,
            later_pool.id or 0,
            hidden_pool.id or 0,
            other_material_pool.id or 0,
        ]
    )

    material_page = await insight_intelligence_service.list_user_pool(
        db,
        user_id=user_id,
        pool_type="report_material",
    )
    favorite_page = await insight_intelligence_service.list_user_pool(
        db,
        user_id=user_id,
        pool_type="favorite",
    )
    checks.append((
        "report_material 池只返回目标素材类型",
        contains_intelligence_id(material_page, intelligence_id)
        and all(item.pool_type == "report_material" for item in material_page),
    ))
    checks.append((
        "favorite 池不混入 report_material 素材",
        contains_intelligence_id(favorite_page, noise_intelligence_id)
        and all(item.pool_type == "favorite" for item in favorite_page),
    ))

    try:
        await insight_intelligence_service.list_user_pool(
            db,
            user_id=user_id,
            pool_type="unknown_pool",
        )
        checks.append(("用户情报池列表拒绝非法池类型", False))
    except ValueError:
        checks.append(("用户情报池列表拒绝非法池类型", True))


async def check_intelligence_maintenance(
    db,
    intelligence_id: int,
    data_source_id: int,
    token: str,
    viewer_id: int,
    owner_id: int,
    editor_id: int,
    outsider_id: int,
    created: dict[str, list[int]],
    checks: list[tuple[str, bool]],
) -> None:
    try:
        await insight_intelligence_service.update_intelligence(
            db,
            intelligence_id,
            InsightIntelligenceUpdate(summary="view 用户不应能编辑正式情报"),
            user_id=viewer_id,
            is_admin=False,
        )
        checks.append(("view 授权用户不能编辑正式情报", False))
    except ValueError:
        checks.append(("view 授权用户不能编辑正式情报", True))

    await grant_rule(db, "intelligence", intelligence_id, "user", owner_id, "edit", created)
    updated = await insight_intelligence_service.update_intelligence(
        db,
        intelligence_id,
        InsightIntelligenceUpdate(
            title=f"主链路烟测正式情报已编辑{token}",
            summary=f"主链路烟测正式情报编辑摘要{token}",
            suggested_tags=[{"name": "已编辑", "source": "smoke"}],
        ),
        user_id=owner_id,
        is_admin=False,
    )
    checks.append(("显式 edit 授权用户可编辑正式情报", updated.title.endswith(token) and bool((updated.raw_payload or {}).get("suggested_tags"))))

    try:
        await insight_intelligence_service.add_source(
            db,
            intelligence_id,
            InsightIntelligenceSourceCreate(),
            user_id=editor_id,
            is_admin=False,
        )
        checks.append(("来源证据不能保存为空", False))
    except ValueError:
        checks.append(("来源证据不能保存为空", True))

    try:
        await insight_intelligence_service.add_source(
            db,
            intelligence_id,
            InsightIntelligenceSourceCreate(source_title="无权用户不应能补来源"),
            user_id=outsider_id,
            is_admin=False,
        )
        checks.append(("无权用户不能补充来源证据", False))
    except ValueError:
        checks.append(("无权用户不能补充来源证据", True))

    source = await insight_intelligence_service.add_source(
        db,
        intelligence_id,
        InsightIntelligenceSourceCreate(
            data_source_id=data_source_id,
            source_type="manual",
            source_url=f"https://example.com/insight-main-flow/manual-source/{token}",
            source_title=f"主链路烟测补充来源{token}",
            content_excerpt="用于验证正式情报人工补充来源证据可追踪。",
            source_metadata={"smoke": True, "token": token},
        ),
        user_id=editor_id,
        is_admin=False,
    )
    created["sources"].append(source.id or 0)
    detail = await insight_intelligence_service.get_intelligence_detail(
        db,
        intelligence_id,
        user_id=editor_id,
        is_admin=False,
    )
    checks.append(("编辑后详情展示最新正式情报内容", detail.title == updated.title and detail.summary == updated.summary))
    checks.append(("新增来源证据可在详情追踪", any(item.id == source.id and item.source_url == source.source_url for item in detail.sources)))
    await collect_related_ids(db, intelligence_id, created)


async def collect_related_ids(db, intelligence_id: int, created: dict[str, list[int]]) -> None:
    sources = list(
        (
            await db.exec(
                select(InsightIntelligenceSource).where(
                    InsightIntelligenceSource.intelligence_id == intelligence_id,
                    InsightIntelligenceSource.is_deleted == 0,
                )
            )
        ).all()
    )
    created["sources"].extend([row.id or 0 for row in sources])
    records = list(
        (
            await db.exec(
                select(InsightReviewRecord).where(
                    InsightReviewRecord.intelligence_id == intelligence_id,
                    InsightReviewRecord.is_deleted == 0,
                )
            )
        ).all()
    )
    created["review_records"].extend([row.id or 0 for row in records])


async def collect_report_related_ids(db, report_id: int, created: dict[str, list[int]]) -> None:
    materials = list(
        (
            await db.exec(
                select(InsightReportMaterial).where(
                    InsightReportMaterial.report_id == report_id,
                    InsightReportMaterial.is_deleted == 0,
                )
            )
        ).all()
    )
    created["report_materials"].extend([row.id or 0 for row in materials])
    versions = list(
        (
            await db.exec(
                select(InsightReportVersion).where(
                    InsightReportVersion.report_id == report_id,
                    InsightReportVersion.is_deleted == 0,
                )
            )
        ).all()
    )
    created["report_versions"].extend([row.id or 0 for row in versions])


async def cleanup(db, created: dict[str, list[int]]) -> None:
    model_map = {
        "report_materials": InsightReportMaterial,
        "report_versions": InsightReportVersion,
        "reports": InsightReport,
        "pools": InsightUserIntelligencePool,
        "review_records": InsightReviewRecord,
        "sources": InsightIntelligenceSource,
        "intelligences": InsightIntelligence,
        "candidates": InsightIntelligenceCandidate,
        "crawl_results": InsightCrawlResult,
        "tasks": InsightTask,
        "rules": InsightVisibilityRule,
        "data_sources": InsightDataSource,
        "companies": InsightCompany,
        "users": SysUser,
    }
    for key, model in model_map.items():
        ids = [item_id for item_id in created[key] if item_id]
        if not ids:
            continue
        rows = list((await db.exec(select(model).where(model.id.in_(ids)))).all())
        for row in rows:
            row.is_deleted = 1
            row.update_by = f"{MARK}-cleanup"
        await db.commit()


if __name__ == "__main__":
    asyncio.run(main())
