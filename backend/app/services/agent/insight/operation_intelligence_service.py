import asyncio
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from app.core.config import settings
from app.schemas.agent.insight.operation import (
    InsightOperationCustomerLifecycle,
    InsightOperationDomain,
    InsightOperationEvidence,
    InsightOperationLifecycleSection,
    InsightOperationMetric,
    InsightOperationOverview,
    InsightOperationSeriesPoint,
    InsightOperationSignal,
    InsightOperationTableRow,
)
from app.services.agent.fr_report.sqlserver_query_service import sqlserver_query_service


class InsightOperationIntelligenceService:
    async def get_overview(self) -> InsightOperationOverview:
        warnings: list[str] = []
        if not settings.FR_AI_SQLSERVER_ENABLED or not sqlserver_query_service.is_configured:
            warnings.append("SQL Server 经营数据连接未启用或配置不完整，当前仅能展示功能边界。")
            return self._empty_overview(warnings)

        analysis_date = await self._latest_date("jy_delivery_data_view2", "posting_date", warnings)
        analysis_period = await self._latest_period_from_extend(warnings)
        if analysis_date is None:
            analysis_date = date.today()
            warnings.append("未能读取发货最新日期，已使用服务器日期作为兜底。")
        if not analysis_period:
            analysis_period = analysis_date.strftime("%Y-%m")

        sales_domain = await self._sales_domain(analysis_date, warnings)
        customer_domain = await self._customer_domain(analysis_period, warnings)
        position_domain = await self._position_domain(analysis_date, warnings)
        hedge_domain = await self._hedge_domain(warnings)
        domains = [sales_domain, customer_domain, position_domain, hedge_domain]
        signals = self._build_signals(domains)
        kpis = self._build_kpis(domains)
        headline = self._headline(kpis, signals, analysis_date, analysis_period)
        return InsightOperationOverview(
            generatedAt=datetime.now().isoformat(timespec="seconds"),
            analysisDate=analysis_date.isoformat(),
            analysisPeriod=analysis_period,
            dataFreshness=await self._data_freshness(warnings),
            headline=headline,
            executiveSummary=self._executive_summary(domains, signals),
            kpis=kpis,
            signals=signals,
            domains=domains,
            evidence=self._evidence(),
            warnings=warnings,
        )

    async def get_customer_lifecycle(self) -> InsightOperationCustomerLifecycle:
        warnings: list[str] = []
        if not settings.FR_AI_SQLSERVER_ENABLED or not sqlserver_query_service.is_configured:
            warnings.append("SQL Server 经营数据连接未启用或配置不完整，暂不能生成客户生命周期分析。")
            return InsightOperationCustomerLifecycle(
                generatedAt=datetime.now().isoformat(timespec="seconds"),
                headline="客户生命周期分析已就绪，但缺少可读取的数据连接。",
                summary=["请先确认 FineReport SQL Server 只读连接配置。"],
                warnings=warnings,
                evidence=self._customer_lifecycle_evidence(),
            )

        analysis_date = await self._latest_date("jy_delivery_data_view2", "posting_date", warnings) or date.today()
        analysis_period = await self._latest_period_from_extend(warnings) or analysis_date.strftime("%Y-%m")
        new_quality = await self._new_customer_quality(warnings)
        plan_actual = await self._new_customer_plan_actual(warnings)
        churn_trend = await self._customer_churn_trend(warnings)
        reactivation = await self._customer_reactivation(warnings)
        silent_pool = await self._customer_silent_pool(analysis_date, warnings)
        action_rows = await self._customer_action_rows(analysis_date, warnings)
        reason_rows = await self._customer_reason_quality(warnings)
        overdue_rows = await self._customer_overdue_overlap(analysis_date, warnings)

        new_count = sum(self._num(row.get("new_customer_products")) for row in new_quality)
        new_qty_90d = sum(self._num(row.get("qty_90d")) for row in new_quality)
        matured = sum(self._num(row.get("matured_90d")) for row in new_quality)
        repeated = sum(self._num(row.get("repeated_90d_matured")) for row in new_quality)
        repeat_rate = repeated * 100 / matured if matured else None
        potential_row = next((row for row in churn_trend if row.get("month_id") == analysis_period and row.get("type_name") == "90天潜在"), {})
        lost_row = next((row for row in churn_trend if row.get("month_id") == analysis_period and row.get("type_name") == "180天流失"), {})
        potential_usage = self._num(potential_row.get("annual_usage"))
        lost_count = self._num(lost_row.get("customers"))
        lost_usage = self._num(lost_row.get("annual_usage"))
        urgent_silent_usage = sum(
            self._num(row.get("annual_usage"))
            for row in silent_pool
            if row.get("risk_bucket") == "90-179天沉默池"
        )
        overdue_amount = sum(self._num(row.get("overdue_amount")) for row in overdue_rows)
        reason_total = sum(self._num(row.get("rows")) for row in reason_rows)
        reason_filled = sum(self._num(row.get("lost_reason_filled")) for row in reason_rows)
        reason_fill_rate = reason_filled * 100 / reason_total if reason_total else None

        summary = [
            f"2026 年新客户产品记录 {int(new_count)} 个，90 天累计发货约 {new_qty_90d:.0f} 吨，成熟客户 90 天复购率约 {repeat_rate:.1f}%。" if repeat_rate is not None else f"2026 年新客户产品记录 {int(new_count)} 个，90 天累计发货约 {new_qty_90d:.0f} 吨。",
            f"{analysis_period} 的 90 天潜在流失年用量约 {potential_usage:.0f} 吨，高于 180 天流失年用量 {lost_usage:.0f} 吨，挽回窗口应前移。",
            f"90-179 天沉默池年用量约 {urgent_silent_usage:.0f} 吨，适合转成当月销售行动清单。",
            f"沉默客户叠加超期应收约 {overdue_amount:.0f} 元，需销售、财务和信用管理联动。",
        ]
        signals = self._build_customer_lifecycle_signals(
            repeat_rate=repeat_rate,
            potential_usage=potential_usage,
            lost_usage=lost_usage,
            urgent_silent_usage=urgent_silent_usage,
            overdue_amount=overdue_amount,
            reason_fill_rate=reason_fill_rate,
        )
        return InsightOperationCustomerLifecycle(
            generatedAt=datetime.now().isoformat(timespec="seconds"),
            analysisDate=analysis_date.isoformat(),
            analysisPeriod=analysis_period,
            headline="客户生命周期进入可运营状态：新客看二单，流失看 90 天挽回，沉默池按价值分层。",
            summary=summary,
            metrics=[
                InsightOperationMetric(key="new_customer_products", label="新客户产品数", value=int(new_count), unit="个", description="2026 年首次发货客户-产品记录"),
                InsightOperationMetric(key="new_90d_qty", label="新客90天发货", value=round(new_qty_90d, 1), unit="吨"),
                InsightOperationMetric(key="repeat_rate_90d", label="成熟新客复购率", value=round(repeat_rate, 1) if repeat_rate is not None else None, unit="%", severity="warning" if repeat_rate is not None and repeat_rate < 55 else "normal"),
                InsightOperationMetric(key="potential_usage", label="90天风险年用量", value=round(potential_usage, 1), unit="吨", severity="warning"),
                InsightOperationMetric(key="lost_usage", label="180天流失年用量", value=round(lost_usage, 1), unit="吨", severity="danger" if lost_count else "normal"),
                InsightOperationMetric(key="urgent_silent_usage", label="行动池年用量", value=round(urgent_silent_usage, 1), unit="吨", severity="warning"),
                InsightOperationMetric(key="overdue_amount", label="沉默叠加应收", value=round(overdue_amount, 1), unit="元", severity="danger" if overdue_amount > 1000000 else "warning"),
                InsightOperationMetric(key="reason_fill_rate", label="标准原因填写率", value=round(reason_fill_rate, 1) if reason_fill_rate is not None else None, unit="%", severity="warning" if reason_fill_rate is not None and reason_fill_rate < 70 else "normal"),
            ],
            sections=[
                InsightOperationLifecycleSection(
                    key="new-quality",
                    title="新客户质量",
                    subtitle="首单不是终点，重点看 90 天复购、90 天累计吨数和沉默回落。",
                    metrics=[
                        InsightOperationMetric(key="new_count", label="新客户产品", value=int(new_count), unit="个"),
                        InsightOperationMetric(key="repeat_rate", label="成熟复购率", value=round(repeat_rate, 1) if repeat_rate is not None else None, unit="%"),
                    ],
                    rows=[
                        InsightOperationTableRow(
                            name=str(row.get("mara_group_desc")),
                            values={
                                "新客户产品": int(self._num(row.get("new_customer_products"))),
                                "90天发货": round(self._num(row.get("qty_90d")), 1),
                                "成熟客户": int(self._num(row.get("matured_90d"))),
                                "90天复购率": round(self._num(row.get("mature_repeat_rate_90d")), 1),
                                "已60天沉默": int(self._num(row.get("already_silent_60d"))),
                            },
                        )
                        for row in new_quality
                    ],
                    findings=[
                        "果葡糖浆新客 90 天规模最大，但已出现较多 60 天沉默，需要做二单转化。",
                        "麦芽糖浆新客复购率偏低，应从首单完成转向复购跟进。",
                        "差异化糖浆体量小但复购率高，适合按应用场景复制高质量样本。",
                    ],
                ),
                InsightOperationLifecycleSection(
                    key="new-plan",
                    title="新客户计划达成",
                    subtitle="把新客户计划量和实际首月发货量对齐，识别市场缺口。",
                    rows=[
                        InsightOperationTableRow(
                            name=f"{row.get('product')}｜{row.get('market')}",
                            values={
                                "计划量": round(self._num(row.get("plan_amount")), 1),
                                "实际新客": int(self._num(row.get("actual_new_customer_products"))),
                                "首月发货": round(self._num(row.get("first_month_qty")), 1),
                                "达成率": round(self._num(row.get("first_month_qty_vs_plan_pct")), 1),
                            },
                        )
                        for row in plan_actual
                    ],
                    findings=[
                        "国际果葡糖浆新客户计划缺口最明显，需要单独跟踪。",
                        "国内果葡糖浆接近计划量，但仍需叠加利润质量判断。",
                    ],
                ),
                InsightOperationLifecycleSection(
                    key="churn-window",
                    title="90天挽回窗口",
                    subtitle="90 天跨阈值不是结论，而是恢复发货的关键干预点。",
                    rows=[
                        InsightOperationTableRow(
                            name=str(row.get("cross_month")),
                            values={
                                "跨阈值客户": int(self._num(row.get("crossed_90_customers"))),
                                "90天恢复": int(self._num(row.get("reactivated_90d"))),
                                "180天恢复": int(self._num(row.get("reactivated_180d"))),
                                "90天恢复率": round(self._num(row.get("reactivated_90d_rate")), 1),
                                "180天恢复率": round(self._num(row.get("reactivated_180d_rate")), 1),
                            },
                        )
                        for row in reactivation
                    ],
                    findings=[
                        "跨过 90 天后的自然恢复率不稳定，低谷月份不足三成。",
                        "90 天节点应自动形成销售任务，而不是等 180 天报表确认流失。",
                    ],
                ),
                InsightOperationLifecycleSection(
                    key="silent-pool",
                    title="沉默客户分层",
                    subtitle="月报只看当月跨阈值，沉默池用于找到被历史口径漏掉的高价值客户。",
                    rows=[
                        InsightOperationTableRow(
                            name=f"{row.get('risk_bucket')}｜{row.get('mara_group_desc')}｜{row.get('sale_market')}",
                            values={
                                "客户产品数": int(self._num(row.get("customer_products"))),
                                "年用量": round(self._num(row.get("annual_usage")), 1),
                                "近365天销量": round(self._num(row.get("sales_365d")), 1),
                                "前365天销量": round(self._num(row.get("sales_prev365d")), 1),
                                "平均沉默天数": round(self._num(row.get("avg_silent_days")), 1),
                            },
                        )
                        for row in silent_pool
                    ],
                    findings=[
                        "90-179 天沉默池最适合转成当月行动清单。",
                        "180 天以上沉默池需要按近 365 天销量和年用量二次筛选，避免历史客户挤占销售精力。",
                    ],
                ),
                InsightOperationLifecycleSection(
                    key="risk-overlap",
                    title="应收与原因质量",
                    subtitle="将流失风险从销售动作升级为经营协同动作。",
                    rows=[
                        InsightOperationTableRow(
                            name=f"{row.get('bucket')}｜{row.get('mara_group_desc')}",
                            values={
                                "沉默客户产品": int(self._num(row.get("silent_customer_products"))),
                                "超期客户产品": int(self._num(row.get("overdue_customer_products"))),
                                "超期金额": round(self._num(row.get("overdue_amount")), 1),
                                "最长超期天数": int(self._num(row.get("max_overdue_days"))),
                            },
                        )
                        for row in overdue_rows
                    ],
                    findings=[
                        "少数沉默客户叠加大额应收，应进入财务和信用协同处理。",
                        "流失补充表中标准原因填写不足，具体原因需要 AI 归类为价格、产能、主体切换等结构化标签。",
                    ],
                ),
                InsightOperationLifecycleSection(
                    key="action-list",
                    title="高价值行动清单",
                    subtitle="按年用量、近年销量、沉默天数、应收和原因缺口排序。",
                    rows=[
                        InsightOperationTableRow(
                            name=str(row.get("relation_customer_name") or row.get("relation_customer_no")),
                            values={
                                "产品": row.get("mara_group_desc"),
                                "最后发货": row.get("last_date"),
                                "沉默天数": int(self._num(row.get("silent_days"))),
                                "年用量": round(self._num(row.get("annual_usage")), 1),
                                "2025销量": round(self._num(row.get("sales_2025")), 1),
                                "2026销量": round(self._num(row.get("sales_2026")), 1),
                                "超期金额": round(self._num(row.get("overdue_amount")), 1),
                                "原因": row.get("specific_lost_reason") or row.get("lost_reason") or "待补充",
                            },
                        )
                        for row in action_rows
                    ],
                    findings=[
                        "高年用量沉默客户不一定出现在当月流失月报中，必须单独维护行动池。",
                        "多账户合作客户应先做主体合并，再判断是否真实流失。",
                    ],
                ),
            ],
            signals=signals,
            evidence=self._customer_lifecycle_evidence(),
            warnings=warnings,
        )

    def _empty_overview(self, warnings: list[str]) -> InsightOperationOverview:
        return InsightOperationOverview(
            generatedAt=datetime.now().isoformat(timespec="seconds"),
            headline="经营智能已就绪，但还没有可读取的经营数据连接。",
            executiveSummary=["请先确认 FineReport SQL Server 只读连接配置，再生成经营分析。"],
            warnings=warnings,
            evidence=self._evidence(),
        )

    async def _sales_domain(self, analysis_date: date, warnings: list[str]) -> InsightOperationDomain:
        sql = f"""
        DECLARE @date_val date = '{analysis_date.isoformat()}';
        DECLARE @month_start date = DATEFROMPARTS(YEAR(@date_val), MONTH(@date_val), 1);
        WITH plan_data AS (
            SELECT
                NULLIF(LTRIM(RTRIM(mara_group_name)), '') AS product,
                SUM(TRY_CAST(sales_volume AS decimal(18, 4))) AS monthly_plan,
                SUM(TRY_CAST(sale_predict_volume AS decimal(18, 4))) AS forecast_sales
            FROM jy_product_sale_plan
            WHERE TRY_CAST(year_val AS int) = YEAR(@date_val)
              AND TRY_CAST(month_val AS int) = MONTH(@date_val)
            GROUP BY NULLIF(LTRIM(RTRIM(mara_group_name)), '')
        ),
        actual_data AS (
            SELECT
                mara_group_desc AS product,
                SUM(shipment_quantity) AS actual_sales,
                SUM(net_income) / 10000.0 AS net_income_wan,
                COUNT(DISTINCT relation_customer_no) AS active_customers
            FROM jy_delivery_data_view2
            WHERE posting_date >= @month_start
              AND posting_date <= @date_val
              AND mara_group_desc IS NOT NULL
            GROUP BY mara_group_desc
        ),
        profit_data AS (
            SELECT
                mara_group_desc AS product,
                SUM(quantity) AS profit_quantity,
                SUM(gross_profit) AS gross_profit_wan,
                SUM(profit) AS profit_wan,
                SUM(marginal_profit) AS marginal_profit_wan
            FROM jy_sale_profit
            WHERE TRY_CAST(year_val AS int) = YEAR(@date_val)
              AND TRY_CAST(month_val AS int) = MONTH(@date_val)
            GROUP BY mara_group_desc
        )
        SELECT
            COALESCE(a.product, p.product, pr.product) AS product,
            COALESCE(p.monthly_plan, 0) AS monthly_plan,
            COALESCE(p.forecast_sales, 0) AS forecast_sales,
            COALESCE(a.actual_sales, 0) AS actual_sales,
            COALESCE(a.net_income_wan, 0) AS net_income_wan,
            COALESCE(a.active_customers, 0) AS active_customers,
            COALESCE(pr.gross_profit_wan, 0) AS gross_profit_wan,
            COALESCE(pr.profit_wan, 0) AS profit_wan,
            COALESCE(pr.marginal_profit_wan, 0) AS marginal_profit_wan,
            CASE WHEN COALESCE(p.monthly_plan, 0) = 0 THEN NULL
                 ELSE COALESCE(a.actual_sales, 0) * 100.0 / NULLIF(p.monthly_plan, 0)
            END AS completion_rate
        FROM actual_data a
        FULL JOIN plan_data p ON a.product = p.product
        FULL JOIN profit_data pr ON COALESCE(a.product, p.product) = pr.product
        WHERE COALESCE(a.product, p.product, pr.product) IS NOT NULL
        ORDER BY actual_sales DESC;
        """
        rows = await self._query(sql, "读取销量利润达成失败", warnings)
        total_plan = sum(self._num(row.get("monthly_plan")) for row in rows)
        total_actual = sum(self._num(row.get("actual_sales")) for row in rows)
        total_profit = sum(self._num(row.get("profit_wan")) for row in rows)
        total_margin = sum(self._num(row.get("marginal_profit_wan")) for row in rows)
        completion = total_actual * 100 / total_plan if total_plan else None
        rows_sorted = sorted(rows, key=lambda item: self._num(item.get("actual_sales")), reverse=True)
        low_rows = [row for row in rows if self._num(row.get("monthly_plan")) > 0 and self._num(row.get("completion_rate")) < 70]
        findings: list[str] = []
        if completion is not None:
            findings.append(f"截至 {analysis_date.strftime('%m月%d日')}，产品累计销量完成率约 {completion:.1f}%。")
        if rows_sorted:
            top = rows_sorted[0]
            findings.append(f"{top.get('product')} 是当前销量贡献最高的产品，累计发货 {self._num(top.get('actual_sales')):.0f} 吨。")
        if low_rows:
            findings.append("存在产品完成率低于 70%，需要结合日计划和次日计划检查缺口。")
        return InsightOperationDomain(
            key="sales",
            title="销量与利润达成",
            subtitle="产品月计划、实际发货、净收入和利润质量",
            score=self._score_completion(completion),
            scoreLabel=self._score_label(completion),
            metrics=[
                InsightOperationMetric(key="actual_sales", label="累计销量", value=round(total_actual, 1), unit="吨", description="本月截至分析日实际发货量"),
                InsightOperationMetric(key="completion_rate", label="计划完成率", value=round(completion, 1) if completion is not None else None, unit="%", severity="warning" if completion is not None and completion < 85 else "normal"),
                InsightOperationMetric(key="profit", label="利润", value=round(total_profit, 1), unit="万元"),
                InsightOperationMetric(key="marginal_profit", label="边际利润", value=round(total_margin, 1), unit="万元"),
            ],
            series=[
                InsightOperationSeriesPoint(
                    label=str(row.get("product") or "未命名"),
                    value=round(self._num(row.get("actual_sales")), 1),
                    extra={
                        "计划": round(self._num(row.get("monthly_plan")), 1),
                        "完成率": round(self._num(row.get("completion_rate")), 1) if row.get("completion_rate") is not None else None,
                        "利润": round(self._num(row.get("profit_wan")), 1),
                    },
                )
                for row in rows_sorted[:8]
            ],
            rows=[
                InsightOperationTableRow(
                    name=str(row.get("product") or "未命名"),
                    values={
                        "月计划": round(self._num(row.get("monthly_plan")), 1),
                        "实际": round(self._num(row.get("actual_sales")), 1),
                        "完成率": round(self._num(row.get("completion_rate")), 1) if row.get("completion_rate") is not None else None,
                        "活跃客户": int(self._num(row.get("active_customers"))),
                        "利润": round(self._num(row.get("profit_wan")), 1),
                    },
                )
                for row in rows_sorted[:10]
            ],
            findings=findings,
            evidenceReports=["销量计划执行情况表(日报)_v2.cpt", "一体化运营销量利润达成情况.cpt", "健源历史数据-销售.cpt"],
        )

    async def _customer_domain(self, period: str, warnings: list[str]) -> InsightOperationDomain:
        churn90 = await self._churn_summary(period, 90, "潜在流失客户", warnings)
        churn180 = await self._churn_summary(period, 180, "流失客户", warnings)
        receivable = await self._query(
            """
            SELECT
                COUNT(*) AS overdue_count,
                SUM(TRY_CAST(amount AS decimal(18, 4))) AS overdue_amount,
                AVG(TRY_CAST(overdue_days AS decimal(18, 4))) AS avg_overdue_days,
                SUM(CASE WHEN CAST(ISNULL(is_bad_debt, '') AS nvarchar(20)) IN ('是','1','true','True') THEN 1 ELSE 0 END) AS bad_debt_count
            FROM jy_accounts_receivable
            WHERE ISNULL(is_history, 0) = 0
              AND TRY_CAST(overdue_days AS decimal(18, 4)) > 0;
            """,
            "读取应收超期失败",
            warnings,
        )
        new_customers = await self._query(
            f"""
            DECLARE @period char(7) = '{period}';
            SELECT
                mara_group_desc AS product,
                COUNT(DISTINCT relation_customer_no) AS customer_count,
                SUM(shipment_quantity) AS shipment_quantity
            FROM jy_delivery_data_view2
            WHERE FORMAT(posting_date, 'yyyy-MM') = @period
              AND relation_customer_no IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1
                  FROM jy_delivery_data_view2 old_data
                  WHERE old_data.relation_customer_no = jy_delivery_data_view2.relation_customer_no
                    AND old_data.mara_group_desc = jy_delivery_data_view2.mara_group_desc
                    AND old_data.posting_date < DATEFROMPARTS(TRY_CAST(LEFT(@period, 4) AS int), TRY_CAST(RIGHT(@period, 2) AS int), 1)
              )
            GROUP BY mara_group_desc
            ORDER BY customer_count DESC;
            """,
            "读取新客户开发失败",
            warnings,
        )
        receivable_row = receivable[0] if receivable else {}
        churn90_count = sum(self._num(row.get("customer_count")) for row in churn90)
        churn180_count = sum(self._num(row.get("customer_count")) for row in churn180)
        risk_usage = sum(self._num(row.get("annual_usage_sum")) for row in churn90 + churn180)
        overdue_amount = self._num(receivable_row.get("overdue_amount"))
        reason_missing = sum(max(0, self._num(row.get("customer_count")) - self._num(row.get("reason_filled_count"))) for row in churn90)
        reason_missing += sum(max(0, self._num(row.get("customer_count")) - self._num(row.get("lost_reason_filled_count"))) for row in churn180)
        findings = [
            f"{period} 潜在流失客户 {int(churn90_count)} 户，180 天流失客户 {int(churn180_count)} 户。",
            f"流失相关客户年用量风险合计约 {risk_usage:.0f} 吨。",
        ]
        if reason_missing:
            findings.append(f"仍有 {int(reason_missing)} 户缺少原因或流失判断，适合生成资料缺口信号。")
        if overdue_amount:
            findings.append(f"当前超期应收金额约 {overdue_amount:.0f} 元，应和客户流失风险联动查看。")
        series = [
            InsightOperationSeriesPoint(label=f"90天-{row.get('mara_group_desc')}", value=int(self._num(row.get("customer_count"))), extra={"年用量": round(self._num(row.get("annual_usage_sum")), 1)})
            for row in churn90
        ] + [
            InsightOperationSeriesPoint(label=f"180天-{row.get('mara_group_desc')}", value=int(self._num(row.get("customer_count"))), extra={"年用量": round(self._num(row.get("annual_usage_sum")), 1)})
            for row in churn180
        ]
        return InsightOperationDomain(
            key="customer",
            title="客户增长与风险",
            subtitle="新客户、流失客户、应收超期和跟进质量",
            score=max(45, 92 - int(churn90_count + churn180_count + reason_missing)),
            scoreLabel="风险可控" if churn90_count + churn180_count < 50 else "需重点跟进",
            metrics=[
                InsightOperationMetric(key="potential_lost", label="潜在流失", value=int(churn90_count), unit="户", severity="warning" if churn90_count else "normal"),
                InsightOperationMetric(key="lost", label="180天流失", value=int(churn180_count), unit="户", severity="danger" if churn180_count else "normal"),
                InsightOperationMetric(key="risk_usage", label="风险年用量", value=round(risk_usage, 1), unit="吨"),
                InsightOperationMetric(key="overdue_amount", label="超期应收", value=round(overdue_amount, 1), unit="元", severity="warning" if overdue_amount else "normal"),
            ],
            series=series[:10],
            rows=[
                InsightOperationTableRow(name=str(row.get("product") or "未命名"), values={"新客户数": int(self._num(row.get("customer_count"))), "发货量": round(self._num(row.get("shipment_quantity")), 1)})
                for row in new_customers[:8]
            ],
            findings=findings,
            evidenceReports=["新客户开发情况(月报)_v2.cpt", "健源公司潜在流失客户情况月报（90天未发货）_v2.cpt", "健源公司流失客户情况月报（180天未发货）_v2.cpt", "健源公司未执行及应收账款情况_v2.cpt"],
        )

    async def _position_domain(self, analysis_date: date, warnings: list[str]) -> InsightOperationDomain:
        price_rows = await self._query(
            """
            WITH latest AS (
                SELECT TOP 1 date_val, jianyuan_price, jinyumi_price
                FROM jy_corn_purchase_price
                WHERE jianyuan_price IS NOT NULL OR jinyumi_price IS NOT NULL
                ORDER BY date_val DESC
            ),
            recent AS (
                SELECT AVG(TRY_CAST(jianyuan_price AS decimal(18, 4))) AS avg_30d
                FROM jy_corn_purchase_price
                WHERE date_val >= DATEADD(day, -30, (SELECT date_val FROM latest))
                  AND date_val <= (SELECT date_val FROM latest)
            )
            SELECT latest.date_val, latest.jianyuan_price, latest.jinyumi_price, recent.avg_30d
            FROM latest CROSS JOIN recent;
            """,
            "读取玉米价格失败",
            warnings,
        )
        inventory_rows = await self._query(
            """
            SELECT TOP 1 Year_Month, CornInventoryQty, CornInventoryCost
            FROM CornPurchaseInventoryDaily
            ORDER BY Year_Month DESC;
            """,
            "读取玉米库存填报失败",
            warnings,
        )
        arrival_rows = await self._query(
            f"""
            DECLARE @date_val date = '{analysis_date.isoformat()}';
            SELECT
                SUM(CASE WHEN arrival_date = @date_val THEN settlement_qty ELSE 0 END) AS today_arrival_qty,
                SUM(CASE WHEN arrival_date >= DATEADD(day, -6, @date_val) AND arrival_date <= @date_val THEN settlement_qty ELSE 0 END) AS week_arrival_qty
            FROM jy_sap_arrival_settlement_data;
            """,
            "读取原料到货失败",
            warnings,
        )
        net_rows = await self._query(
            """
            SELECT TOP 1 record_date, net_position_qty, spot_balance_qty, contract_pending_qty
            FROM jy_operating_net_position_fill
            ORDER BY record_date DESC;
            """,
            "读取经营净头寸填报失败",
            warnings,
            optional=True,
        )
        price = price_rows[0] if price_rows else {}
        inventory = inventory_rows[0] if inventory_rows else {}
        arrival = arrival_rows[0] if arrival_rows else {}
        net = net_rows[0] if net_rows else {}
        latest_price = self._num(price.get("jianyuan_price"))
        avg_30d = self._num(price.get("avg_30d"))
        price_delta = latest_price - avg_30d if latest_price and avg_30d else 0
        findings = []
        if price:
            findings.append(f"玉米最新价格 {latest_price:.0f} 元/吨，较近 30 日均价 {'高' if price_delta >= 0 else '低'} {abs(price_delta):.0f} 元/吨。")
        if inventory:
            findings.append(f"库存填报最新期间 {inventory.get('Year_Month')}，库存量 {self._num(inventory.get('CornInventoryQty')):.0f} 吨。")
        if arrival:
            findings.append(f"近 7 日原料到货约 {self._num(arrival.get('week_arrival_qty')):.0f} 吨。")
        if net:
            findings.append(f"经营净头寸最新记录 {net.get('record_date')}，净头寸 {self._num(net.get('net_position_qty')):.0f} 吨。")
        return InsightOperationDomain(
            key="position",
            title="采购库存与净头寸",
            subtitle="玉米价格、采购到货、库存和经营净头寸",
            score=72 if price_delta <= 50 else 58,
            scoreLabel="价格压力上行" if price_delta > 50 else "跟踪中",
            metrics=[
                InsightOperationMetric(key="corn_price", label="健源玉米价", value=round(latest_price, 1) if latest_price else None, unit="元/吨", severity="warning" if price_delta > 50 else "normal"),
                InsightOperationMetric(key="corn_price_delta", label="较30日均价", value=round(price_delta, 1), unit="元/吨", severity="warning" if price_delta > 50 else "normal"),
                InsightOperationMetric(key="inventory", label="玉米库存", value=round(self._num(inventory.get("CornInventoryQty")), 1), unit="吨"),
                InsightOperationMetric(key="week_arrival", label="近7日到货", value=round(self._num(arrival.get("week_arrival_qty")), 1), unit="吨"),
            ],
            series=[
                InsightOperationSeriesPoint(label="最新价格", value=round(latest_price, 1) if latest_price else 0),
                InsightOperationSeriesPoint(label="30日均价", value=round(avg_30d, 1) if avg_30d else 0),
                InsightOperationSeriesPoint(label="库存量", value=round(self._num(inventory.get("CornInventoryQty")), 1)),
                InsightOperationSeriesPoint(label="近7日到货", value=round(self._num(arrival.get("week_arrival_qty")), 1)),
            ],
            rows=[
                InsightOperationTableRow(name="玉米价格", values={"日期": price.get("date_val"), "健源": latest_price, "金玉米": self._num(price.get("jinyumi_price"))}),
                InsightOperationTableRow(name="库存填报", values={"期间": inventory.get("Year_Month"), "库存量": self._num(inventory.get("CornInventoryQty")), "成本价": self._num(inventory.get("CornInventoryCost"))}),
                InsightOperationTableRow(name="经营净头寸", values={"日期": net.get("record_date"), "净头寸": self._num(net.get("net_position_qty")), "现货结余": self._num(net.get("spot_balance_qty"))}),
            ],
            findings=findings,
            evidenceReports=["玉米采购与库存日报.cpt", "健源公司经营净头寸.cpt", "健源玉米每日价格趋势图表.frm"],
        )

    async def _hedge_domain(self, warnings: list[str]) -> InsightOperationDomain:
        risk_rows = await self._query(
            """
            WITH latest AS (
                SELECT MAX(record_date) AS record_date FROM jy_futures_account_risk_fill
            )
            SELECT
                f.record_date,
                SUM(TRY_CAST(f.margin_amount AS decimal(18,4))) AS margin_amount,
                SUM(TRY_CAST(f.customer_equity AS decimal(18,4))) AS customer_equity,
                MAX(
                    CASE
                        WHEN TRY_CAST(f.customer_equity AS decimal(18,4)) = 0 THEN NULL
                        ELSE TRY_CAST(f.margin_amount AS decimal(18,4)) * 100.0 / NULLIF(TRY_CAST(f.customer_equity AS decimal(18,4)), 0)
                    END
                ) AS max_risk_rate,
                AVG(
                    CASE
                        WHEN TRY_CAST(f.customer_equity AS decimal(18,4)) = 0 THEN NULL
                        ELSE TRY_CAST(f.margin_amount AS decimal(18,4)) * 100.0 / NULLIF(TRY_CAST(f.customer_equity AS decimal(18,4)), 0)
                    END
                ) AS avg_risk_rate,
                COUNT(DISTINCT f.futures_company_name) AS company_count
            FROM jy_futures_account_risk_fill f
            INNER JOIN latest l ON f.record_date = l.record_date
            GROUP BY f.record_date;
            """,
            "读取期货账户风险失败",
            warnings,
        )
        futures_rows = await self._query("SELECT COUNT(*) AS ledger_count FROM fr_future_trade_ledger;", "读取期货台账失败", warnings, optional=True)
        otc_rows = await self._query(
            "SELECT COUNT(*) AS fill_count, SUM(TRY_CAST(daily_profit AS decimal(18,4))) AS daily_profit FROM jy_otc_option_daily_fill;",
            "读取场外期权日结失败",
            warnings,
            optional=True,
        )
        row = risk_rows[0] if risk_rows else {}
        max_risk = self._num(row.get("max_risk_rate"))
        findings = []
        if row:
            findings.append(f"期货账户风险度最新日期 {row.get('record_date')}，最高风险度 {max_risk:.2f}%。")
        if futures_rows:
            findings.append(f"期货操作台账当前 {int(self._num(futures_rows[0].get('ledger_count')))} 条，样本较少，适合先做风险监控。")
        if otc_rows:
            findings.append(f"场外期权日结 {int(self._num(otc_rows[0].get('fill_count')))} 条，可展示每日损益和有效数量。")
        return InsightOperationDomain(
            key="hedging",
            title="套保与衍生品风险",
            subtitle="期货账户风险度、操作台账和期权日结",
            score=62 if max_risk >= 80 else 78,
            scoreLabel="风险度偏高" if max_risk >= 80 else "低样本监控",
            metrics=[
                InsightOperationMetric(key="risk_rate", label="最高风险度", value=round(max_risk, 2) if row else None, unit="%", severity="danger" if max_risk >= 80 else "normal"),
                InsightOperationMetric(key="margin", label="保证金占用", value=round(self._num(row.get("margin_amount")), 1), unit="元"),
                InsightOperationMetric(key="equity", label="客户权益", value=round(self._num(row.get("customer_equity")), 1), unit="元"),
                InsightOperationMetric(key="account_count", label="期货公司", value=int(self._num(row.get("company_count"))), unit="个"),
            ],
            series=[
                InsightOperationSeriesPoint(label="最高风险度", value=round(max_risk, 2)),
                InsightOperationSeriesPoint(label="平均风险度", value=round(self._num(row.get("avg_risk_rate")), 2)),
                InsightOperationSeriesPoint(label="期货台账", value=int(self._num(futures_rows[0].get("ledger_count"))) if futures_rows else 0),
                InsightOperationSeriesPoint(label="场外期权日结", value=int(self._num(otc_rows[0].get("fill_count"))) if otc_rows else 0),
            ],
            rows=[
                InsightOperationTableRow(name="期货账户", values={"日期": row.get("record_date"), "最高风险度": round(max_risk, 2), "保证金": round(self._num(row.get("margin_amount")), 1)}),
                InsightOperationTableRow(name="期货台账", values={"记录数": int(self._num(futures_rows[0].get("ledger_count"))) if futures_rows else 0}),
                InsightOperationTableRow(name="场外期权", values={"日结记录": int(self._num(otc_rows[0].get("fill_count"))) if otc_rows else 0, "累计日利润": round(self._num(otc_rows[0].get("daily_profit")), 1) if otc_rows else 0}),
            ],
            findings=findings,
            evidenceReports=["健源公司期货账户风险度.cpt", "健源公司期货操作台账.cpt", "健源公司场外期权操作台账.cpt", "场内期权操作台账.cpt"],
        )

    async def _churn_summary(self, period: str, days: int, label: str, warnings: list[str]) -> list[dict[str, Any]]:
        sql = f"""
        DECLARE @month_end_day date = EOMONTH(CONCAT('{period}', '-01'));
        WITH DeliveryData AS (
            SELECT relation_customer_no, posting_date, shipment_quantity, mara_group_desc, YEAR(posting_date) AS sales_year
            FROM jy_delivery_data_view2
            WHERE relation_customer_no IS NOT NULL
        ),
        RecentDelivery AS (
            SELECT DISTINCT relation_customer_no
            FROM DeliveryData
            WHERE posting_date >= DATEADD(day, -{days}, @month_end_day)
        ),
        ThresholdMonthDelivery AS (
            SELECT DISTINCT relation_customer_no
            FROM DeliveryData
            WHERE posting_date < DATEADD(day, -{days}, @month_end_day)
              AND posting_date >= DATEADD(day, -{days} - DAY(@month_end_day), @month_end_day)
        ),
        TargetCustomers AS (
            SELECT t.relation_customer_no
            FROM ThresholdMonthDelivery t
            WHERE NOT EXISTS (SELECT 1 FROM RecentDelivery r WHERE t.relation_customer_no = r.relation_customer_no)
        ),
        AnnualSales AS (
            SELECT relation_customer_no,
                   SUM(CASE WHEN sales_year = YEAR(@month_end_day) - 1 THEN shipment_quantity ELSE 0 END) AS last_year_sales
            FROM DeliveryData
            WHERE sales_year = YEAR(@month_end_day) - 1
            GROUP BY relation_customer_no
        ),
        LastShipmentInfo AS (
            SELECT relation_customer_no, shipment_quantity, mara_group_desc,
                   ROW_NUMBER() OVER (PARTITION BY relation_customer_no ORDER BY posting_date DESC) AS rn
            FROM DeliveryData
            WHERE EXISTS (SELECT 1 FROM TargetCustomers tc WHERE DeliveryData.relation_customer_no = tc.relation_customer_no)
        ),
        Detail AS (
            SELECT cb.customer_no, lsi.mara_group_desc, annual_usage.usage, ys.last_year_sales,
                   lsi.shipment_quantity AS last_month_ship_qty,
                   ext.is_lost, ext.lost_reason, ext.specific_lost_reason, ext.follow_measures
            FROM TargetCustomers tc
            LEFT JOIN jy_customer_base cb ON tc.relation_customer_no = cb.customer_no
            LEFT JOIN AnnualSales ys ON cb.customer_no = ys.relation_customer_no
            LEFT JOIN LastShipmentInfo lsi ON cb.customer_no = lsi.relation_customer_no AND lsi.rn = 1
            LEFT JOIN jy_latest_usage annual_usage ON cb.customer_no = annual_usage.customer_no AND annual_usage.mara_group_name = lsi.mara_group_desc
            LEFT JOIN jy_lost_customer_extend ext ON cb.customer_no = ext.customer_no AND ext.year_val = YEAR(@month_end_day) AND ext.month_val = MONTH(@month_end_day)
            WHERE cb.customer_name IS NOT NULL
              AND lsi.mara_group_desc IN ('果葡糖浆', '麦芽糖浆', '差异化糖浆')
        )
        SELECT '{label}' AS type,
               mara_group_desc,
               COUNT(*) AS customer_count,
               SUM(COALESCE(TRY_CAST(usage AS decimal(18,4)), 0)) AS annual_usage_sum,
               SUM(COALESCE(TRY_CAST(last_year_sales AS decimal(18,4)), 0)) AS last_year_sales_sum,
               SUM(COALESCE(TRY_CAST(last_month_ship_qty AS decimal(18,4)), 0)) AS last_ship_qty_sum,
               SUM(CASE WHEN COALESCE(specific_lost_reason, '') <> '' THEN 1 ELSE 0 END) AS reason_filled_count,
               SUM(CASE WHEN COALESCE(lost_reason, '') <> '' THEN 1 ELSE 0 END) AS lost_reason_filled_count,
               SUM(CASE WHEN COALESCE(follow_measures, '') <> '' THEN 1 ELSE 0 END) AS follow_filled_count
        FROM Detail
        GROUP BY mara_group_desc
        ORDER BY customer_count DESC;
        """
        return await self._query(sql, f"读取{label}失败", warnings)

    async def _new_customer_quality(self, warnings: list[str]) -> list[dict[str, Any]]:
        return await self._query(
            """
            WITH ScopeDelivery AS (
                SELECT relation_customer_no, relation_customer_name, posting_date, shipment_quantity, mara_group_desc, sale_market, salesman
                FROM jy_delivery_data_view2
                WHERE relation_customer_no IS NOT NULL
                  AND mara_group_desc IN ('果葡糖浆','麦芽糖浆','差异化糖浆')
            ),
            FirstProduct AS (
                SELECT relation_customer_no, mara_group_desc, MIN(posting_date) AS first_date
                FROM ScopeDelivery
                GROUP BY relation_customer_no, mara_group_desc
            ),
            Cohort AS (
                SELECT f.relation_customer_no, f.mara_group_desc, f.first_date,
                       MAX(d.relation_customer_name) AS relation_customer_name,
                       MAX(d.sale_market) AS sale_market,
                       MAX(d.salesman) AS salesman
                FROM FirstProduct f
                JOIN ScopeDelivery d
                  ON f.relation_customer_no=d.relation_customer_no
                 AND f.mara_group_desc=d.mara_group_desc
                 AND f.first_date=d.posting_date
                WHERE f.first_date >= '2026-01-01' AND f.first_date <= '2026-07-03'
                GROUP BY f.relation_customer_no, f.mara_group_desc, f.first_date
            ),
            Agg AS (
                SELECT c.relation_customer_no, c.mara_group_desc, c.first_date, c.sale_market,
                       SUM(CASE WHEN d.posting_date <= DATEADD(day,30,c.first_date) THEN d.shipment_quantity ELSE 0 END) AS qty_30d,
                       SUM(CASE WHEN d.posting_date <= DATEADD(day,90,c.first_date) THEN d.shipment_quantity ELSE 0 END) AS qty_90d,
                       MAX(CASE WHEN d.posting_date > c.first_date AND d.posting_date <= DATEADD(day,90,c.first_date) THEN 1 ELSE 0 END) AS repeated_90d,
                       MAX(d.posting_date) AS latest_ship_date
                FROM Cohort c
                LEFT JOIN ScopeDelivery d
                  ON c.relation_customer_no=d.relation_customer_no
                 AND c.mara_group_desc=d.mara_group_desc
                 AND d.posting_date >= c.first_date
                GROUP BY c.relation_customer_no, c.mara_group_desc, c.first_date, c.sale_market
            )
            SELECT mara_group_desc,
                   COUNT(*) AS new_customer_products,
                   SUM(qty_30d) AS qty_30d,
                   SUM(qty_90d) AS qty_90d,
                   SUM(CASE WHEN DATEDIFF(day, first_date, '2026-07-03') >= 90 THEN 1 ELSE 0 END) AS matured_90d,
                   SUM(CASE WHEN DATEDIFF(day, first_date, '2026-07-03') >= 90 THEN repeated_90d ELSE 0 END) AS repeated_90d_matured,
                   CASE WHEN SUM(CASE WHEN DATEDIFF(day, first_date, '2026-07-03') >= 90 THEN 1 ELSE 0 END)=0 THEN NULL
                        ELSE SUM(CASE WHEN DATEDIFF(day, first_date, '2026-07-03') >= 90 THEN repeated_90d ELSE 0 END)*100.0
                             / SUM(CASE WHEN DATEDIFF(day, first_date, '2026-07-03') >= 90 THEN 1 ELSE 0 END)
                   END AS mature_repeat_rate_90d,
                   SUM(CASE WHEN DATEDIFF(day, latest_ship_date, '2026-07-03') >= 60 THEN 1 ELSE 0 END) AS already_silent_60d
            FROM Agg
            GROUP BY mara_group_desc
            ORDER BY qty_90d DESC;
            """,
            "读取新客户质量失败",
            warnings,
        )

    async def _new_customer_plan_actual(self, warnings: list[str]) -> list[dict[str, Any]]:
        return await self._query(
            """
            WITH ScopeDelivery AS (
                SELECT relation_customer_no, posting_date, shipment_quantity, mara_group_desc,
                       CASE WHEN sale_market='10' THEN '国内市场'
                            WHEN sale_market='20' THEN '国际市场'
                            ELSE ISNULL(sale_market,'未识别') END AS market_name
                FROM jy_delivery_data_view2
                WHERE relation_customer_no IS NOT NULL
                  AND mara_group_desc IN ('果葡糖浆','麦芽糖浆','差异化糖浆')
            ),
            FirstProduct AS (
                SELECT relation_customer_no, mara_group_desc, MIN(posting_date) AS first_date
                FROM ScopeDelivery
                GROUP BY relation_customer_no, mara_group_desc
            ),
            Actual AS (
                SELECT d.mara_group_desc AS product, d.market_name AS market,
                       COUNT(DISTINCT CONCAT(d.relation_customer_no,'|',d.mara_group_desc)) AS actual_new_customer_products,
                       SUM(d.shipment_quantity) AS first_month_qty
                FROM ScopeDelivery d
                JOIN FirstProduct f
                  ON d.relation_customer_no=f.relation_customer_no
                 AND d.mara_group_desc=f.mara_group_desc
                 AND FORMAT(f.first_date,'yyyy-MM')=FORMAT(d.posting_date,'yyyy-MM')
                WHERE f.first_date>='2026-01-01' AND f.first_date<='2026-07-03'
                GROUP BY d.mara_group_desc, d.market_name
            ),
            PlanData AS (
                SELECT product, market, SUM(plan_amount) AS plan_amount, SUM(plan_profit) AS plan_profit
                FROM jy_new_customer_plan
                WHERE TRY_CAST(year_val AS int)=2026
                GROUP BY product, market
            )
            SELECT COALESCE(p.product,a.product) AS product,
                   COALESCE(p.market,a.market) AS market,
                   p.plan_amount,
                   p.plan_profit,
                   a.actual_new_customer_products,
                   a.first_month_qty,
                   CASE WHEN p.plan_amount=0 THEN NULL ELSE a.first_month_qty*100.0/p.plan_amount END AS first_month_qty_vs_plan_pct
            FROM PlanData p
            FULL JOIN Actual a ON p.product=a.product AND p.market=a.market
            ORDER BY product, market;
            """,
            "读取新客户计划达成失败",
            warnings,
        )

    async def _customer_churn_trend(self, warnings: list[str]) -> list[dict[str, Any]]:
        return await self._query(
            """
            WITH MonthBase AS (
                SELECT CAST('2026-01-01' AS date) AS month_start
                UNION ALL SELECT DATEADD(month, 1, month_start) FROM MonthBase WHERE month_start < '2026-06-01'
            ),
            DeliveryData AS (
                SELECT relation_customer_no, posting_date, shipment_quantity, mara_group_desc
                FROM jy_delivery_data_view2
                WHERE relation_customer_no IS NOT NULL
                  AND mara_group_desc IN ('果葡糖浆','麦芽糖浆','差异化糖浆')
            ),
            Thresholds AS (
                SELECT m.month_start, EOMONTH(m.month_start) AS month_end, v.days, v.type_name
                FROM MonthBase m CROSS JOIN (VALUES (90,'90天潜在'),(180,'180天流失')) v(days,type_name)
            ),
            TargetCustomers AS (
                SELECT t.month_start, t.month_end, t.days, t.type_name, d.relation_customer_no
                FROM Thresholds t
                INNER JOIN DeliveryData d
                   ON d.posting_date < DATEADD(day, -t.days, t.month_end)
                  AND d.posting_date >= DATEADD(day, -t.days - DAY(t.month_end), t.month_end)
                WHERE NOT EXISTS (
                    SELECT 1 FROM DeliveryData r
                    WHERE r.relation_customer_no=d.relation_customer_no
                      AND r.posting_date >= DATEADD(day, -t.days, t.month_end)
                      AND r.posting_date <= t.month_end
                )
                GROUP BY t.month_start, t.month_end, t.days, t.type_name, d.relation_customer_no
            ),
            LastInfo AS (
                SELECT tc.month_start, tc.type_name, dd.relation_customer_no, dd.mara_group_desc, dd.shipment_quantity,
                       ROW_NUMBER() OVER(PARTITION BY tc.month_start, tc.type_name, dd.relation_customer_no ORDER BY dd.posting_date DESC) AS rn
                FROM TargetCustomers tc
                JOIN DeliveryData dd ON tc.relation_customer_no=dd.relation_customer_no AND dd.posting_date <= tc.month_end
            ),
            Detail AS (
                SELECT li.month_start, li.type_name, li.mara_group_desc, li.relation_customer_no, li.shipment_quantity, u.usage
                FROM LastInfo li
                LEFT JOIN jy_latest_usage u
                  ON CAST(li.relation_customer_no AS varchar(50))=u.customer_no
                 AND li.mara_group_desc=u.mara_group_name
                WHERE li.rn=1
            )
            SELECT FORMAT(month_start,'yyyy-MM') AS month_id,
                   type_name,
                   COUNT(DISTINCT relation_customer_no) AS customers,
                   SUM(COALESCE(usage,0)) AS annual_usage,
                   SUM(COALESCE(shipment_quantity,0)) AS last_ship_qty
            FROM Detail
            GROUP BY FORMAT(month_start,'yyyy-MM'), type_name
            ORDER BY month_id, type_name
            OPTION (MAXRECURSION 20);
            """,
            "读取客户流失趋势失败",
            warnings,
        )

    async def _customer_reactivation(self, warnings: list[str]) -> list[dict[str, Any]]:
        return await self._query(
            """
            WITH MonthBase AS (
                SELECT CAST('2025-07-01' AS date) AS month_start
                UNION ALL SELECT DATEADD(month, 1, month_start) FROM MonthBase WHERE month_start < '2026-03-01'
            ),
            DeliveryData AS (
                SELECT relation_customer_no, posting_date, shipment_quantity, mara_group_desc
                FROM jy_delivery_data_view2
                WHERE relation_customer_no IS NOT NULL
                  AND mara_group_desc IN ('果葡糖浆','麦芽糖浆','差异化糖浆')
            ),
            Target90 AS (
                SELECT m.month_start, EOMONTH(m.month_start) AS month_end, d.relation_customer_no
                FROM MonthBase m
                INNER JOIN DeliveryData d
                   ON d.posting_date < DATEADD(day, -90, EOMONTH(m.month_start))
                  AND d.posting_date >= DATEADD(day, -90 - DAY(EOMONTH(m.month_start)), EOMONTH(m.month_start))
                WHERE NOT EXISTS (
                    SELECT 1 FROM DeliveryData r
                    WHERE r.relation_customer_no=d.relation_customer_no
                      AND r.posting_date >= DATEADD(day, -90, EOMONTH(m.month_start))
                      AND r.posting_date <= EOMONTH(m.month_start)
                )
                GROUP BY m.month_start, EOMONTH(m.month_start), d.relation_customer_no
            ),
            Flags AS (
                SELECT t.month_start, t.relation_customer_no,
                       MAX(CASE WHEN d.posting_date > t.month_end AND d.posting_date <= DATEADD(day,90,t.month_end) THEN 1 ELSE 0 END) AS reactivated_90d,
                       MAX(CASE WHEN d.posting_date > t.month_end AND d.posting_date <= DATEADD(day,180,t.month_end) THEN 1 ELSE 0 END) AS reactivated_180d
                FROM Target90 t
                LEFT JOIN DeliveryData d
                  ON d.relation_customer_no=t.relation_customer_no
                 AND d.posting_date > t.month_end
                 AND d.posting_date <= DATEADD(day,180,t.month_end)
                GROUP BY t.month_start, t.relation_customer_no
            )
            SELECT FORMAT(month_start,'yyyy-MM') AS cross_month,
                   COUNT(*) AS crossed_90_customers,
                   SUM(reactivated_90d) AS reactivated_90d,
                   SUM(reactivated_180d) AS reactivated_180d,
                   SUM(reactivated_90d)*100.0/COUNT(*) AS reactivated_90d_rate,
                   SUM(reactivated_180d)*100.0/COUNT(*) AS reactivated_180d_rate
            FROM Flags
            GROUP BY FORMAT(month_start,'yyyy-MM')
            ORDER BY cross_month
            OPTION (MAXRECURSION 20);
            """,
            "读取90天恢复率失败",
            warnings,
        )

    async def _customer_silent_pool(self, analysis_date: date, warnings: list[str]) -> list[dict[str, Any]]:
        return await self._query(
            f"""
            DECLARE @asof date = '{analysis_date.isoformat()}';
            WITH ScopeDelivery AS (
                SELECT relation_customer_no, relation_customer_name, posting_date, shipment_quantity, mara_group_desc, sale_market, salesman
                FROM jy_delivery_data_view2
                WHERE relation_customer_no IS NOT NULL
                  AND mara_group_desc IN ('果葡糖浆','麦芽糖浆','差异化糖浆')
            ),
            LastProduct AS (
                SELECT relation_customer_no, mara_group_desc, MAX(posting_date) AS last_date
                FROM ScopeDelivery
                WHERE posting_date <= @asof
                GROUP BY relation_customer_no, mara_group_desc
            ),
            LastRows AS (
                SELECT l.relation_customer_no, d.relation_customer_name, l.mara_group_desc, l.last_date, d.sale_market, d.salesman,
                       ROW_NUMBER() OVER(PARTITION BY l.relation_customer_no,l.mara_group_desc ORDER BY d.posting_date DESC) AS rn
                FROM LastProduct l
                JOIN ScopeDelivery d
                  ON l.relation_customer_no=d.relation_customer_no
                 AND l.mara_group_desc=d.mara_group_desc
                 AND l.last_date=d.posting_date
            ),
            SalesAgg AS (
                SELECT relation_customer_no, mara_group_desc,
                       SUM(CASE WHEN posting_date >= DATEADD(day,-365,@asof) THEN shipment_quantity ELSE 0 END) AS sales_365d,
                       SUM(CASE WHEN posting_date >= DATEADD(day,-730,@asof) AND posting_date < DATEADD(day,-365,@asof) THEN shipment_quantity ELSE 0 END) AS sales_prev365d
                FROM ScopeDelivery
                GROUP BY relation_customer_no, mara_group_desc
            ),
            Risk AS (
                SELECT lr.relation_customer_no, lr.mara_group_desc, lr.last_date, DATEDIFF(day,lr.last_date,@asof) AS silent_days,
                       CASE WHEN lr.sale_market='10' THEN '国内市场'
                            WHEN lr.sale_market='20' THEN '国际市场'
                            ELSE ISNULL(lr.sale_market,'未识别') END AS sale_market,
                       ISNULL(lr.salesman,'未识别') AS salesman,
                       u.usage, s.sales_365d, s.sales_prev365d
                FROM LastRows lr
                LEFT JOIN jy_latest_usage u
                  ON CAST(lr.relation_customer_no AS varchar(50))=u.customer_no
                 AND lr.mara_group_desc=u.mara_group_name
                LEFT JOIN SalesAgg s
                  ON lr.relation_customer_no=s.relation_customer_no
                 AND lr.mara_group_desc=s.mara_group_desc
                WHERE lr.rn=1 AND DATEDIFF(day,lr.last_date,@asof) >= 90
            )
            SELECT CASE WHEN silent_days >= 180 THEN '180天以上沉默池' ELSE '90-179天沉默池' END AS risk_bucket,
                   mara_group_desc,
                   sale_market,
                   COUNT(*) AS customer_products,
                   SUM(COALESCE(usage,0)) AS annual_usage,
                   SUM(COALESCE(sales_365d,0)) AS sales_365d,
                   SUM(COALESCE(sales_prev365d,0)) AS sales_prev365d,
                   AVG(CAST(silent_days AS decimal(18,2))) AS avg_silent_days
            FROM Risk
            GROUP BY CASE WHEN silent_days >= 180 THEN '180天以上沉默池' ELSE '90-179天沉默池' END, mara_group_desc, sale_market
            ORDER BY risk_bucket, annual_usage DESC;
            """,
            "读取沉默客户池失败",
            warnings,
        )

    async def _customer_overdue_overlap(self, analysis_date: date, warnings: list[str]) -> list[dict[str, Any]]:
        return await self._query(
            f"""
            DECLARE @asof date = '{analysis_date.isoformat()}';
            WITH LastProduct AS (
                SELECT relation_customer_no, mara_group_desc, MAX(posting_date) AS last_date
                FROM jy_delivery_data_view2
                WHERE relation_customer_no IS NOT NULL
                  AND mara_group_desc IN ('果葡糖浆','麦芽糖浆','差异化糖浆')
                  AND posting_date <= @asof
                GROUP BY relation_customer_no, mara_group_desc
            ),
            Silent AS (
                SELECT relation_customer_no, mara_group_desc, DATEDIFF(day,last_date,@asof) AS silent_days
                FROM LastProduct
                WHERE DATEDIFF(day,last_date,@asof)>=90
            ),
            Receivable AS (
                SELECT customer_no,
                       SUM(CASE WHEN ISNULL(is_history,0)=0 AND overdue_days>0 THEN amount ELSE 0 END) AS overdue_amount,
                       MAX(CASE WHEN ISNULL(is_history,0)=0 AND overdue_days>0 THEN overdue_days ELSE 0 END) AS max_overdue_days,
                       SUM(CASE WHEN ISNULL(is_history,0)=0 AND is_bad_debt=1 THEN 1 ELSE 0 END) AS bad_debt_count
                FROM jy_accounts_receivable
                GROUP BY customer_no
            )
            SELECT CASE WHEN s.silent_days>=180 THEN '180天以上' ELSE '90-179天' END AS bucket,
                   s.mara_group_desc,
                   COUNT(*) AS silent_customer_products,
                   SUM(CASE WHEN r.overdue_amount>0 THEN 1 ELSE 0 END) AS overdue_customer_products,
                   SUM(COALESCE(r.overdue_amount,0)) AS overdue_amount,
                   MAX(COALESCE(r.max_overdue_days,0)) AS max_overdue_days,
                   SUM(COALESCE(r.bad_debt_count,0)) AS bad_debt_count
            FROM Silent s
            LEFT JOIN Receivable r ON CAST(s.relation_customer_no AS varchar(50))=r.customer_no
            GROUP BY CASE WHEN s.silent_days>=180 THEN '180天以上' ELSE '90-179天' END, s.mara_group_desc
            ORDER BY bucket, overdue_amount DESC;
            """,
            "读取沉默客户应收叠加失败",
            warnings,
        )

    async def _customer_reason_quality(self, warnings: list[str]) -> list[dict[str, Any]]:
        return await self._query(
            """
            SELECT year_val, month_val,
                   COUNT(*) AS rows,
                   SUM(CASE WHEN NULLIF(LTRIM(RTRIM(is_lost)),'') IS NOT NULL THEN 1 ELSE 0 END) AS is_lost_filled,
                   SUM(CASE WHEN NULLIF(LTRIM(RTRIM(lost_reason)),'') IS NOT NULL THEN 1 ELSE 0 END) AS lost_reason_filled,
                   SUM(CASE WHEN NULLIF(LTRIM(RTRIM(specific_lost_reason)),'') IS NOT NULL THEN 1 ELSE 0 END) AS specific_reason_filled,
                   SUM(CASE WHEN NULLIF(LTRIM(RTRIM(follow_measures)),'') IS NOT NULL THEN 1 ELSE 0 END) AS follow_filled
            FROM jy_lost_customer_extend
            WHERE year_val='2026' AND month_val='6'
            GROUP BY year_val, month_val;
            """,
            "读取流失原因质量失败",
            warnings,
        )

    async def _customer_action_rows(self, analysis_date: date, warnings: list[str]) -> list[dict[str, Any]]:
        return await self._query(
            f"""
            DECLARE @asof date = '{analysis_date.isoformat()}';
            WITH ScopeDelivery AS (
                SELECT relation_customer_no, relation_customer_name, posting_date, shipment_quantity, mara_group_desc, sale_market, salesman
                FROM jy_delivery_data_view2
                WHERE relation_customer_no IS NOT NULL
                  AND mara_group_desc IN ('果葡糖浆','麦芽糖浆','差异化糖浆')
            ),
            LastProduct AS (
                SELECT relation_customer_no, mara_group_desc, MAX(posting_date) AS last_date
                FROM ScopeDelivery
                WHERE posting_date <= @asof
                GROUP BY relation_customer_no, mara_group_desc
            ),
            LastRows AS (
                SELECT l.relation_customer_no, d.relation_customer_name, l.mara_group_desc, l.last_date, d.sale_market, d.salesman,
                       ROW_NUMBER() OVER(PARTITION BY l.relation_customer_no,l.mara_group_desc ORDER BY d.posting_date DESC) AS rn
                FROM LastProduct l
                JOIN ScopeDelivery d
                  ON l.relation_customer_no=d.relation_customer_no
                 AND l.mara_group_desc=d.mara_group_desc
                 AND l.last_date=d.posting_date
            ),
            SalesAgg AS (
                SELECT relation_customer_no, mara_group_desc,
                       SUM(CASE WHEN YEAR(posting_date)=2025 THEN shipment_quantity ELSE 0 END) AS sales_2025,
                       SUM(CASE WHEN YEAR(posting_date)=2026 THEN shipment_quantity ELSE 0 END) AS sales_2026
                FROM ScopeDelivery
                GROUP BY relation_customer_no, mara_group_desc
            ),
            Receivable AS (
                SELECT customer_no,
                       SUM(CASE WHEN ISNULL(is_history,0)=0 AND overdue_days > 0 THEN amount ELSE 0 END) AS overdue_amount,
                       MAX(CASE WHEN ISNULL(is_history,0)=0 AND overdue_days > 0 THEN overdue_days ELSE 0 END) AS max_overdue_days
                FROM jy_accounts_receivable
                GROUP BY customer_no
            )
            SELECT TOP 20 lr.relation_customer_no,
                   lr.relation_customer_name,
                   lr.mara_group_desc,
                   lr.last_date,
                   DATEDIFF(day,lr.last_date,@asof) AS silent_days,
                   CASE WHEN lr.sale_market='10' THEN '国内市场'
                        WHEN lr.sale_market='20' THEN '国际市场'
                        ELSE ISNULL(lr.sale_market,'未识别') END AS sale_market,
                   lr.salesman,
                   u.usage AS annual_usage,
                   s.sales_2025,
                   s.sales_2026,
                   r.overdue_amount,
                   r.max_overdue_days,
                   ext.is_lost,
                   ext.lost_reason,
                   ext.specific_lost_reason,
                   ext.follow_measures
            FROM LastRows lr
            LEFT JOIN jy_latest_usage u
              ON CAST(lr.relation_customer_no AS varchar(50))=u.customer_no
             AND lr.mara_group_desc=u.mara_group_name
            LEFT JOIN SalesAgg s
              ON lr.relation_customer_no=s.relation_customer_no
             AND lr.mara_group_desc=s.mara_group_desc
            LEFT JOIN Receivable r ON CAST(lr.relation_customer_no AS varchar(50))=r.customer_no
            LEFT JOIN jy_lost_customer_extend ext
              ON CAST(lr.relation_customer_no AS varchar(50))=ext.customer_no
             AND ext.year_val='2026'
             AND ext.month_val='6'
            WHERE lr.rn=1 AND DATEDIFF(day,lr.last_date,@asof) >= 90
            ORDER BY COALESCE(u.usage,0) DESC, COALESCE(s.sales_2025,0) DESC;
            """,
            "读取客户行动清单失败",
            warnings,
        )

    async def _latest_date(self, table: str, field: str, warnings: list[str]) -> date | None:
        rows = await self._query(f"SELECT MAX({field}) AS latest_date FROM {table};", f"读取 {table} 最新日期失败", warnings)
        value = rows[0].get("latest_date") if rows else None
        return self._to_date(value)

    async def _latest_period_from_extend(self, warnings: list[str]) -> str | None:
        rows = await self._query(
            """
            SELECT TOP 1 CONCAT(year_val, '-', RIGHT(CONCAT('00', month_val), 2)) AS period
            FROM jy_lost_customer_extend
            WHERE TRY_CAST(year_val AS int) BETWEEN 2020 AND 2099
              AND TRY_CAST(month_val AS int) BETWEEN 1 AND 12
            ORDER BY TRY_CAST(year_val AS int) DESC, TRY_CAST(month_val AS int) DESC;
            """,
            "读取客户流失最新期间失败",
            warnings,
            optional=True,
        )
        return str(rows[0].get("period")) if rows and rows[0].get("period") else None

    async def _data_freshness(self, warnings: list[str]) -> list[str]:
        checks = [
            ("销售发货", "jy_delivery_data_view2", "posting_date"),
            ("日计划", "jy_day_data", "date_val"),
            ("玉米价格", "jy_corn_purchase_price", "date_val"),
            ("期货风险", "jy_futures_account_risk_fill", "record_date"),
        ]
        result: list[str] = []
        for label, table, field in checks:
            latest = await self._latest_date(table, field, warnings)
            if latest:
                result.append(f"{label}：{latest.isoformat()}")
        return result

    async def _query(self, sql: str, warning: str, warnings: list[str], optional: bool = False) -> list[dict[str, Any]]:
        try:
            rows, _columns = await asyncio.to_thread(sqlserver_query_service._execute_sample_query, sql)
            return [self._normalize_row(row) for row in rows]
        except Exception as exc:
            if not optional:
                warnings.append(f"{warning}：{exc}")
            return []

    def _build_kpis(self, domains: list[InsightOperationDomain]) -> list[InsightOperationMetric]:
        metrics: list[InsightOperationMetric] = []
        for domain in domains:
            metrics.extend(domain.metrics[:2])
        return metrics[:8]

    def _build_signals(self, domains: list[InsightOperationDomain]) -> list[InsightOperationSignal]:
        domain_map = {domain.key: domain for domain in domains}
        signals: list[InsightOperationSignal] = []
        sales = domain_map.get("sales")
        if sales:
            completion_metric = next((item for item in sales.metrics if item.key == "completion_rate"), None)
            completion = self._num(completion_metric.value if completion_metric else None)
            if completion and completion < 85:
                signals.append(
                    InsightOperationSignal(
                        title="销量进度低于经营节奏",
                        level="warning",
                        domain=sales.title,
                        summary=f"本月累计销量完成率约 {completion:.1f}%，低于理想进度。",
                        evidence=[f.label for f in sales.metrics[:3]],
                        suggestion="优先检查低完成率产品的当日计划、次日计划和大客户发货缺口。",
                    )
                )
        customer = domain_map.get("customer")
        if customer:
            lost = self._metric_value(customer, "lost")
            potential = self._metric_value(customer, "potential_lost")
            if lost + potential > 0:
                signals.append(
                    InsightOperationSignal(
                        title="客户流失风险需要销售跟进",
                        level="danger" if lost >= 30 else "warning",
                        domain=customer.title,
                        summary=f"最新期间潜在流失 {int(potential)} 户，180 天流失 {int(lost)} 户。",
                        evidence=["90天潜在流失", "180天流失", "流失客户额外数据"],
                        suggestion="把高年用量客户、原因缺失客户和应收超期客户合并为销售跟进清单。",
                    )
                )
        position = domain_map.get("position")
        if position:
            price_delta = self._metric_value(position, "corn_price_delta")
            if price_delta > 50:
                signals.append(
                    InsightOperationSignal(
                        title="玉米采购价格压力上行",
                        level="warning",
                        domain=position.title,
                        summary=f"健源玉米最新价格较 30 日均价高 {price_delta:.0f} 元/吨。",
                        evidence=["玉米价格", "采购库存日报"],
                        suggestion="联动查看净头寸、合同到货和库存结余，评估锁价窗口。",
                    )
                )
        hedge = domain_map.get("hedging")
        if hedge:
            risk = self._metric_value(hedge, "risk_rate")
            if risk >= 80:
                signals.append(
                    InsightOperationSignal(
                        title="期货账户风险度接近高位",
                        level="danger",
                        domain=hedge.title,
                        summary=f"最新最高风险度 {risk:.2f}%。",
                        evidence=["期货账户风险度"],
                        suggestion="检查保证金占用、客户权益和现货净头寸是否匹配。",
                    )
                )
        if not signals:
            signals.append(
                InsightOperationSignal(
                    title="经营数据已形成可追踪证据链",
                    level="normal",
                    domain="经营总览",
                    summary="销售、客户、采购库存和套保四类数据均已接入首屏分析。",
                    evidence=["健源报表全量 CPT 预研"],
                    suggestion="下一步可启用定时生成经营信号，并沉淀人工反馈。",
                )
            )
        return signals[:6]

    def _headline(self, kpis: list[InsightOperationMetric], signals: list[InsightOperationSignal], analysis_date: date, period: str) -> str:
        danger_count = sum(1 for item in signals if item.level == "danger")
        warning_count = sum(1 for item in signals if item.level == "warning")
        if danger_count:
            prefix = f"发现 {danger_count} 个高优先级经营风险"
        elif warning_count:
            prefix = f"发现 {warning_count} 个需要跟进的经营信号"
        else:
            prefix = "经营数据链路已跑通，暂无高优先级异常"
        return f"{prefix}，分析日 {analysis_date.isoformat()}，客户风险期间 {period}。"

    def _executive_summary(self, domains: list[InsightOperationDomain], signals: list[InsightOperationSignal]) -> list[str]:
        result = [signal.summary for signal in signals[:3]]
        for domain in domains:
            result.extend(domain.findings[:1])
        return result[:6]

    def _evidence(self) -> list[InsightOperationEvidence]:
        return [
            InsightOperationEvidence(
                title="销量利润与计划",
                reportPath="webroot/APP/reportlets/数据分析/健源报表/销量计划执行情况表(日报)_v2.cpt",
                tables=["jy_product_sale_plan", "jy_delivery_data_view2", "jy_day_data", "jy_sale_profit"],
                metrics=["累计销量", "计划完成率", "利润", "边际利润"],
            ),
            InsightOperationEvidence(
                title="客户增长与流失",
                reportPath="webroot/APP/reportlets/数据分析/健源报表/健源公司流失客户情况月报（180天未发货）_v2.cpt",
                tables=["jy_delivery_data_view2", "jy_customer_base", "jy_latest_usage", "jy_lost_customer_extend"],
                metrics=["潜在流失客户数", "180天流失客户数", "风险年用量", "跟进覆盖率"],
                note="90/180 天报表当前口径为跨阈值当月名单，不是全量沉默客户池。",
            ),
            InsightOperationEvidence(
                title="采购库存与净头寸",
                reportPath="webroot/APP/reportlets/数据分析/健源报表/健源公司经营净头寸.cpt",
                tables=["jy_corn_purchase_price", "jy_sap_arrival_settlement_data", "jy_sap_inventory_stock", "jy_operating_net_position_fill"],
                metrics=["玉米价格", "库存量", "近7日到货", "净头寸"],
            ),
            InsightOperationEvidence(
                title="套保与账户风险",
                reportPath="webroot/APP/reportlets/数据分析/健源报表/健源公司期货账户风险度.cpt",
                tables=["jy_futures_account_risk_fill", "fr_future_trade_ledger", "jy_otc_option_daily_fill", "jy_option_trade_ledger"],
                metrics=["风险度", "保证金占用", "客户权益", "期权日结利润"],
            ),
        ]

    def _customer_lifecycle_evidence(self) -> list[InsightOperationEvidence]:
        return [
            InsightOperationEvidence(
                title="新客户开发与计划",
                reportPath="webroot/APP/reportlets/数据分析/健源报表/新客户开发情况(月报)_v2.cpt",
                tables=["jy_delivery_data_view2", "jy_new_customer_plan", "jy_new_customer_profit", "jy_sale_profit"],
                metrics=["新客户产品数", "首月发货", "90天复购", "新客户计划达成"],
                note="新客户按客户-产品首次发货识别，一个客户多产品会产生多条新客户产品记录。",
            ),
            InsightOperationEvidence(
                title="90/180天客户流失",
                reportPath="webroot/APP/reportlets/数据分析/健源报表/健源公司潜在流失客户情况月报（90天未发货）_v2.cpt",
                tables=["jy_delivery_data_view2", "jy_customer_base", "jy_latest_usage", "jy_lost_customer_extend"],
                metrics=["90天跨阈值", "180天跨阈值", "恢复发货率", "沉默池年用量"],
                note="CPT 月报展示当月跨阈值客户；页面额外补充截至分析日的存量沉默池。",
            ),
            InsightOperationEvidence(
                title="应收与客户风险叠加",
                reportPath="webroot/APP/reportlets/数据分析/健源报表/健源公司未执行及应收账款情况_v2.cpt",
                tables=["jy_accounts_receivable", "jy_sale_contract_view", "jy_delivery_data_view2"],
                metrics=["超期金额", "最长超期天数", "沉默客户叠加应收"],
            ),
        ]

    def _build_customer_lifecycle_signals(
        self,
        *,
        repeat_rate: float | None,
        potential_usage: float,
        lost_usage: float,
        urgent_silent_usage: float,
        overdue_amount: float,
        reason_fill_rate: float | None,
    ) -> list[InsightOperationSignal]:
        signals: list[InsightOperationSignal] = []
        if repeat_rate is not None and repeat_rate < 55:
            signals.append(
                InsightOperationSignal(
                    title="新客户二单转化偏弱",
                    level="warning",
                    domain="新客户质量",
                    summary=f"成熟新客户 90 天复购率约 {repeat_rate:.1f}%，需要从首单开发转向二单转化。",
                    evidence=["jy_delivery_data_view2", "新客户首次发货 cohort"],
                    suggestion="把首单后 30/60/90 天未复购客户自动推给对应业务员。",
                )
            )
        if potential_usage > lost_usage * 3 and potential_usage > 10000:
            signals.append(
                InsightOperationSignal(
                    title="挽回窗口应前移到90天",
                    level="danger",
                    domain="客户流失",
                    summary=f"90 天潜在流失年用量约 {potential_usage:.0f} 吨，显著高于 180 天流失 {lost_usage:.0f} 吨。",
                    evidence=["90天潜在流失", "180天流失", "jy_latest_usage"],
                    suggestion="将 90 天跨阈值客户作为本月销售行动主清单，180 天客户作为复盘和确认清单。",
                )
            )
        if urgent_silent_usage > 50000:
            signals.append(
                InsightOperationSignal(
                    title="存量沉默池存在高价值客户",
                    level="warning",
                    domain="沉默客户",
                    summary=f"90-179 天沉默池年用量约 {urgent_silent_usage:.0f} 吨，月报跨阈值口径无法完整覆盖。",
                    evidence=["最后发货日", "近365天销量", "客户年用量"],
                    suggestion="按年用量、近365天销量、沉默天数筛出高价值客户行动池。",
                )
            )
        if overdue_amount > 1000000:
            signals.append(
                InsightOperationSignal(
                    title="沉默客户叠加大额应收",
                    level="danger",
                    domain="应收风险",
                    summary=f"沉默客户叠加超期应收约 {overdue_amount:.0f} 元，已超出普通销售跟进范畴。",
                    evidence=["jy_accounts_receivable", "沉默客户池"],
                    suggestion="对超期金额高的客户建立销售、财务、信用管理协同处理卡。",
                )
            )
        if reason_fill_rate is not None and reason_fill_rate < 70:
            signals.append(
                InsightOperationSignal(
                    title="流失原因结构化不足",
                    level="warning",
                    domain="跟进质量",
                    summary=f"标准流失原因填写率约 {reason_fill_rate:.1f}%，大量原因停留在自由文本。",
                    evidence=["jy_lost_customer_extend"],
                    suggestion="用 AI 将具体原因归类为价格、产能、主体切换、账期、认证、周期等标准标签。",
                )
            )
        return signals[:6]

    def _metric_value(self, domain: InsightOperationDomain, key: str) -> float:
        item = next((metric for metric in domain.metrics if metric.key == key), None)
        return self._num(item.value if item else None)

    def _score_completion(self, completion: float | None) -> int:
        if completion is None:
            return 60
        return max(35, min(96, int(completion)))

    def _score_label(self, completion: float | None) -> str:
        if completion is None:
            return "待校验"
        if completion >= 95:
            return "节奏良好"
        if completion >= 80:
            return "基本跟进"
        return "进度偏慢"

    def _num(self, value: object | None) -> float:
        if value is None:
            return 0.0
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, (int, float)):
            return float(value)
        try:
            return float(str(value).strip())
        except (TypeError, ValueError):
            return 0.0

    def _to_date(self, value: object | None) -> date | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        try:
            return datetime.fromisoformat(str(value)).date()
        except ValueError:
            return None

    def _normalize_row(self, row: dict[str, Any]) -> dict[str, Any]:
        normalized: dict[str, Any] = {}
        for key, value in row.items():
            if isinstance(value, datetime):
                normalized[key] = value.isoformat(sep=" ", timespec="seconds")
            elif isinstance(value, date):
                normalized[key] = value.isoformat()
            elif isinstance(value, Decimal):
                normalized[key] = float(value)
            else:
                normalized[key] = value
        return normalized


insight_operation_intelligence_service = InsightOperationIntelligenceService()
