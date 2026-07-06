# 经营智能-健源报表全量 CPT 预研

## 1. 预研范围

本次预研面向产业经营智能平台第一阶段“经营数据 AI 分析”，读取帆软中健源相关当前报表，识别可沉淀的经营指标、分析主题和页面形态。

读取目录：

- `webroot/APP/reportlets/数据分析/健源报表`
- `webroot/APP/reportlets/数据分析/健源填报`

范围规则：

- 纳入当前正式 `.cpt` / `.frm`。
- 排除 `历史版本/`、`版本库/`、`回收站/`。
- 销售历史数据子表纳入分析，因为它们承载销售、利润、毛利、边际利润明细口径。

读取结果：

- 当前文件总数：44 个。
- 分类结果：销售与利润达成 9 个，客户经营与风险 11 个，采购库存与头寸 7 个，套保衍生品 7 个，填报维护 8 个，其他 2 个。

## 2. 数据可用性

已通过 SQL Server 只读连接核验部分核心表的数据范围：

| 表 | 记录数 | 日期范围或期间 | 用途 |
| --- | ---: | --- | --- |
| `jy_delivery_data_view2` | 122757 | 2020-12-31 至 2026-07-03 | 销售发货、计划完成、新客户、流失客户、净头寸 |
| `jy_day_data` | 10491 | 2025-06-01 至 2026-07-03 | 日计划、次日计划 |
| `jy_product_sale_plan` | 230 | 最大年份 2026 | 产品月度销量计划、预测销量 |
| `jy_customer_month_plan` | 251 | 最大年份 2026 | 大客户月度计划 |
| `jy_sale_profit` | 5621 | 2025 至 2026 | 销售毛利、利润、边际利润 |
| `jy_accounts_receivable` | 3160 | 实回款 1900-01-01 至 2026-06-24 | 应收、超期、呆坏账 |
| `jy_total_accounts_receivable` | 60 | 2025 至 2026 | 应收总额计划/实际/超期 |
| `jy_sale_contract_view` | 263 | 2023-10-22 至 2026-07-02 | 销售合同、未执行订单 |
| `jy_customer_complaint` | 6 | 2021-04-01 至 2023-05-11 | 客诉分析，数据量较小 |
| `jy_corn_purchase_price` | 2367 | 2020-01-02 至 2026-07-03 | 玉米价格趋势 |
| `CornPurchaseInventoryDaily` | 3 | 2026-04 至 2026-06 | 玉米库存填报，当前样本少 |
| `jy_sap_arrival_settlement_data` | 24989 | 2023-09-11 至 2026-07-02 | 原料到货、入厂、采购 |
| `jy_operating_net_position_fill` | 24 | 2026-06-01 至 2026-06-24 | 经营净头寸人工补充项 |
| `jy_futures_account_risk_fill` | 716 | 2026-01-01 至 2026-06-28 | 期货账户风险度 |
| `jy_otc_option_daily_fill` | 19 | 2026-01-19 至 2026-02-06 | 场外期权日结 |
| `fr_future_trade_ledger` | 3 | 日期字段未识别 | 期货操作台账，当前样本少 |
| `jy_option_trade_ledger` | 1 | 2026-06-15 | 场内期权操作台账，当前样本少 |
| `jy_lost_customer_extend` | 2617 | 最大年份 2026 | 流失客户原因、措施、人工判断 |

结论：

- 最成熟的数据域是销售发货、销量计划、销售利润、客户风险、玉米价格、期货账户风险。
- 采购库存和净头寸已具备真实 SAP 到货、库存与人工填报数据，但部分填报表样本较少，需要按字段稳定性验证。
- 期货、期权台账已具备页面和表结构，但交易台账样本很少，第一版适合做监控和台账查询，不宜过早做复杂绩效归因。

## 3. 报表矩阵

### 3.1 销售与利润达成

| 报表 | 核心表 | 可沉淀分析 |
| --- | --- | --- |
| `销量计划执行情况表(日报)_v2.cpt` | `jy_product_sale_plan`、`jy_delivery_data_view2`、`jy_day_data` | 产品日/月计划达成、当天完成、次日计划、进度偏差 |
| `销量计划执行情况表(日报).cpt` | 同上 | 旧版日报，可作为 v2 口径对比 |
| `一体化运营销量利润达成情况.cpt` | `jy_customer_month_plan`、`jy_product_sale_plan`、`jy_delivery_data_view2`、`jy_day_data`、`jy_major_customer` | 大客户/即期订单销量达成、预算进度、预测进度、当日计划执行 |
| `一体化运营销量利润达成情况的副本.cpt` | 同上 | 副本，暂不作为主口径 |
| `健源历史数据-销售.cpt` | `jy_delivery_data_view2`、`jy_delivery_data_view`、`jy_customer_base`、`jy_latest_usage`、`jy_sale_profit` | 客户销售画像、销量、净收入、吨毛利、吨利润、吨边际利润 |
| `销售历史数据子表/当年月销量.cpt` | `jy_delivery_data_view` | 当年月销量明细 |
| `销售历史数据子表/当年销量利润明细.cpt` | `jy_delivery_data_view`、`jy_sale_profit` | 客户产品销量、毛利、利润、边际利润 |
| `销售历史数据子表/销售利润明细.cpt` | `jy_sale_profit` | 月度利润明细 |
| `销售历史数据子表/销售毛利明细.cpt`、`销售边际利润明细.cpt` | `jy_sale_profit` | 月度毛利、边际利润明细 |

建议分析：

- 销量达成看板：月计划、应完成进度、累计完成、日计划、当日实际、次日计划。
- 利润质量看板：销量、净收入、吨毛利、吨利润、吨边际利润按客户、产品、市场、业务员拆解。
- 计划偏差信号：产品或客户订单低于应完成进度、连续多日低于计划、次日计划无法覆盖缺口。
- 客户价值信号：高销量低利润、高年用量低边际利润、利润改善/恶化客户。

### 3.2 客户经营与风险

| 报表 | 核心表 | 可沉淀分析 |
| --- | --- | --- |
| `健源公司潜在流失客户情况月报（90天未发货）_v2.cpt` | `jy_delivery_data_view2`、`jy_customer_base`、`jy_latest_usage`、`jy_lost_customer_extend` | 本月跨过 90 天未发货阈值客户、原因、措施 |
| `健源公司流失客户情况月报（180天未发货）_v2.cpt` | 同上 | 本月跨过 180 天未发货阈值客户、确认流失、原因、措施 |
| `新客户开发情况(月报)_v2.cpt` | `jy_delivery_data_view2`、`jy_customer_base`、`jy_latest_usage`、`jy_new_customer_plan`、`jy_sale_profit` | 新客户月度开发、计划达成、累计发货、利润达成 |
| `新客户开发情况(周报)_v3.cpt` | `jy_delivery_data_view2`、`jy_customer_base`、`jy_latest_usage`、`jy_week` | 新客户周度发货和下一步工作思路 |
| `当年开发客户发货情况表.cpt` | `jy_delivery_data_view2`、`jy_customer_base`、`jy_latest_usage`、`jy_new_customer_plan`、`jy_sale_profit` | 当年新开发客户逐月发货、计划、利润 |
| `健源公司未执行及应收账款情况_v2.cpt` | `jy_unexecuted_sales_contract_daily`、`jy_sale_contract_view`、`jy_accounts_receivable`、`jy_total_accounts_receivable`、`jy_product_deal_price` | 未执行订单、超期未执行、应收计划/实际/超期 |
| `健源公司客户应收超期情况表.cpt` | `jy_accounts_receivable` | 客户超期次数、平均超期金额、平均超期天数、坏账风险 |
| `健源公司客户投诉统计表.cpt` | `jy_customer_complaint`、泛微流程表 | 客诉数量、产品、责任部门、处理闭环 |
| `健源填报/客户基础信息表.cpt` | `jy_customer_base` | 客户主数据、客户分类、市场、业务员 |
| `健源填报/客户投诉情况.cpt` | `jy_customer_complaint` | 客诉维护数据 |
| `健源填报/客户超期应收情况维护表.cpt` | `jy_accounts_receivable` | 应收维护数据 |

建议分析：

- 客户生命周期漏斗：新客户开发 -> 发货转化 -> 稳定复购 -> 潜在流失 -> 确认流失。
- 客户风险雷达：流失风险、未执行订单风险、应收超期风险、投诉风险合并成客户风险等级。
- 销售跟进质量：流失原因填写率、跟进措施填写率、应收责任人覆盖、客诉处理闭环率。
- 重点客户清单：高年用量、高去年销量、高应收或高未执行金额客户优先。
- 新客户达成：按产品、市场、客户、月份对比计划数量、预算利润、实际发货、实际利润。

### 3.3 采购库存与头寸

| 报表 | 核心表 | 可沉淀分析 |
| --- | --- | --- |
| `玉米采购与库存日报.cpt` | `jy_sap_arrival_settlement_data`、`jy_sap_inventory_stock`、`jy_corn_purchase_price`、`CornPurchaseInventoryDaily` | 门前收购、合同到货、入厂总量、库存、库存均价 |
| `健源玉米每日价格趋势图表.frm`、`健源玉米每日价格趋势图表1.frm` | `jy_corn_purchase_price` | 健源与金玉米每日价格走势 |
| `健源公司原料采购及头寸情况.cpt` | `jy_week`、`jy_po_info`、`jy_ztmm202`、`jy_ekko`、`jy_ekpo`、`jy_mseg`、`jy_dakehusuodingqingkuang` | 原料采购周报、玉米/淀粉采购量价、未执行原料合同、大客户订单锁定 |
| `健源公司经营净头寸.cpt` | `jy_delivery_data_view2`、`jy_sap_arrival_settlement_data`、`jy_sap_inventory_stock`、`jy_operating_net_position_fill`、`jy_corn_purchase_price` | 订单、发货、玉米需求、现货库存、合同待执行、净头寸 |
| `健源填报/每日玉米价格填报表.cpt` | `jy_corn_purchase_price` | 玉米价格维护 |
| `健源填报/玉米采购与库存填报.cpt` | `CornPurchaseInventoryDaily` | 月度库存量、库存成本价维护 |

建议分析：

- 玉米采购库存日监控：入厂量、门前收购、合同到货、库存、库存均价、价格走势。
- 原料采购执行：周/月/季度玉米采购数量和价格对计划的达成偏差。
- 经营净头寸：订单剩余、原料需求、现货结余、合同待执行、净头寸缺口。
- 采购价格信号：健源价格相对金玉米价格的价差、连续上涨/下跌、采购均价异常。
- 库存风险信号：现货结余低于安全库存、净头寸转负、合同到货无法覆盖订单需求。

### 3.4 套保衍生品

| 报表 | 核心表 | 可沉淀分析 |
| --- | --- | --- |
| `健源公司期货操作台账.cpt` | `fr_future_trade_ledger`、`fr_future_contract_base`、`fr_future_settlement_price` | 期货开平仓、持仓、浮盈亏、实现盈亏 |
| `健源公司场外期权操作台账.cpt` | `jy_otc_option_daily_fill`、`jy_futures_contract_close_price` | 场外期权日结、累计倍数、有效数量、单吨收益、每日利润 |
| `场内期权操作台账.cpt` | `jy_option_trade_ledger`、`jy_option_contract_base` | 场内期权开平仓、持仓、权利金、已实现收益 |
| `健源公司期货账户风险度.cpt` | `jy_futures_account_risk_fill`、`jy_futures_company` | 账户权益、保证金、风险度 |
| `健源公司期货公司维护表.cpt` | `jy_futures_company` | 期货公司基础维护 |
| `健源公司期货操作台账基础维护表.cpt`、`健源填报/健源公司场内期权操作台账基础维护表.cpt` | `fr_future_contract_base` | 合约基础维护 |

建议分析：

- 套保账户风险监控：风险度、保证金占用、客户权益趋势。
- 期货持仓损益：开仓、平仓、持仓、浮盈亏、实现盈亏。
- 期权敞口监控：期权类型、标的合约、执行价、持仓量、权利金、每日利润。
- 经营头寸联动：后续可把净头寸与期货/期权持仓合并，形成“现货缺口 + 套保覆盖率”。

当前边界：

- `fr_future_trade_ledger`、`jy_option_trade_ledger` 当前样本少，优先做台账查询和风险度监控，不急于做复杂绩效评价。

### 3.5 填报维护

| 报表 | 核心表 | 作用 |
| --- | --- | --- |
| `产品成交价格.cpt` | `jy_product_deal_price`、`jy_week` | 产品、市场、周度成交价维护 |
| `产品月度计划情况.cpt` | `jy_product_sale_plan` | 产品月计划、预测销量维护 |
| `大客户月度计划表.cpt` | `jy_customer_month_plan` | 大客户产品月计划、预测销量维护 |
| `健源销售利润.cpt` | `jy_sale_profit` | 销售利润维护 |
| `健源公司客户产品年用量维护表.cpt` | `jy_latest_usage` | 客户产品年用量维护 |
| `客户基础信息表.cpt` | `jy_customer_base` | 客户主数据维护 |
| `周定义.cpt` | `jy_week` | 周期维表维护 |
| `新客户开发情况月报预算数据.cpt`、`新客户开发月度利润达成.cpt` | `jy_new_customer_plan`、`jy_new_customer_profit` | 新客户预算和利润维护 |

建议处理：

- 这些不是第一屏分析主报表，但它们是指标口径和计划值来源。
- 经营智能需要把这些维护表识别为“主数据/计划数据/人工补充数据”，并在口径说明中显示数据来源和更新时间。

## 4. 建议做成的经营智能分析主题

### 4.1 销量与利润驾驶台

目标：每天回答“销量完成怎么样，利润质量怎么样，哪里偏离计划”。

核心指标：

- 月计划销量、预测销量、累计完成销量。
- 应完成进度、实际完成进度、偏差量、偏差率。
- 当日计划、当日实际、次日计划。
- 净收入、毛利、利润、边际利润。
- 吨毛利、吨利润、吨边际利润。

维度：

- 产品、品类、市场、部门、客户、大客户/即期订单、业务员、日期。

信号示例：

- “麦芽糖浆本月累计完成低于应完成进度，缺口集中在即期订单。”
- “某客户销量正常但吨边际利润低于同类客户，建议复核报价和成本口径。”

### 4.2 客户增长与流失雷达

目标：把新客户、流失客户、应收、投诉放在同一张客户风险图里。

核心指标：

- 新客户数、新客户发货量、新客户利润、新客户计划达成率。
- 潜在流失客户数、确认流失客户数、风险年用量、风险去年销量。
- 未执行订单量、超期未执行量、应收超期金额、坏账标记。
- 投诉次数、未闭环投诉数。

维度：

- 客户、产品、市场、国家/地区、应用领域、业务员、原因类型。

信号示例：

- “某客户同时出现 180 天未发货和应收超期，应提升为高风险客户。”
- “差异化糖浆流失客户原因填写率为 0，应优先补齐销售跟进信息。”

### 4.3 采购库存与净头寸监控

目标：回答“原料够不够，采购价格是否异常，订单和库存是否匹配”。

核心指标：

- 门前收购量、合同到货量、入厂总量。
- 玉米库存量、库存成本价、库存均价。
- 玉米价格、金玉米价格、价差。
- 期初剩余订单、核心客户签单、中小客户签单、发货量、当日剩余订单。
- 玉米需求量、现货结余、合同签订、合同待执行、净头寸。

维度：

- 日期、周、月、采购类型、合同、供应商、产品。

信号示例：

- “净头寸连续转负，同时玉米价格上涨，采购和销售需要共同关注锁价窗口。”
- “合同到货低于计划，库存结余逼近安全线，应提示原料采购风险。”

### 4.4 套保与衍生品风险监控

目标：先做风险可见，不急于替代专业套保分析。

核心指标：

- 期货账户风险度、保证金占用、客户权益。
- 期货持仓量、浮盈亏、实现盈亏。
- 场内/场外期权持仓、权利金、有效数量、每日利润。
- 后续扩展：套保覆盖率、现货净头寸与期货/期权敞口匹配。

信号示例：

- “某期货账户风险度接近阈值，保证金占用上升。”
- “现货净头寸为负但套保覆盖不足，应作为风险观察信号。”

### 4.5 经营信号流

目标：把上述主题沉淀为统一信号。

建议第一版信号类型：

- 计划偏差信号。
- 利润异常信号。
- 客户风险信号。
- 应收超期信号。
- 库存/头寸风险信号。
- 采购价格异动信号。
- 套保账户风险信号。
- 数据质量/资料缺口信号。

信号必须展示：

- 时间范围。
- 指标口径。
- 关联报表。
- SQL 来源表。
- 证据数据。
- AI 解释。
- 建议关注动作。

## 5. 第一版落地优先级

建议不要一口气做全量问数，先按数据成熟度分三批：

### P0：最适合先做

- 销量计划执行情况表(日报)_v2。
- 一体化运营销量利润达成情况。
- 健源历史数据-销售。
- 新客户开发情况(月报)_v2 / 周报_v3。
- 90 天潜在流失、180 天流失。
- 未执行及应收账款情况_v2。

原因：数据范围较完整，经营价值直接，适合形成第一批“经营信号卡”。

### P1：第二批接入

- 玉米采购与库存日报。
- 健源公司经营净头寸。
- 健源玉米每日价格趋势图表。
- 健源公司原料采购及头寸情况。
- 客户应收超期情况表。

原因：可形成采购、库存、净头寸风险，但部分填报数据需要继续验证。

### P2：第三批增强

- 期货操作台账。
- 场内/场外期权操作台账。
- 期货账户风险度。
- 客户投诉统计。

原因：期货/期权交易台账样本较少，客诉历史样本较少，适合先做查询与风险展示，后续再做趋势归因。

## 6. 页面建议

入口沿用产业经营智能平台规划：

- 路径：`/insight/operation-intelligence`
- 菜单：`经营智能`
- 初期仅管理员可见。

第一版页面建议：

1. 经营信号流
   - 展示 AI 自动生成的计划偏差、客户风险、应收风险、库存头寸风险。

2. 主题分析 Tabs
   - 销量利润。
   - 客户增长与风险。
   - 采购库存与头寸。
   - 套保风险。

3. 经营问数
   - 只允许在已登记指标和维度内问数。
   - 回答展示 SQL 口径、筛选条件、结果表和解释。

4. 报表证据中心
   - 列出报表名称、CPT 路径、数据集、来源表、可用指标、最近数据期间。
   - 让管理员能追溯“AI 这个结论来自哪张报表、哪张表、哪个口径”。

## 7. 后端建议

建议新增 Insight operation 子域：

- `backend/app/services/agent/insight/operation/report_catalog_service.py`
- `backend/app/services/agent/insight/operation/metric_catalog_service.py`
- `backend/app/services/agent/insight/operation/sales_analysis_service.py`
- `backend/app/services/agent/insight/operation/customer_risk_service.py`
- `backend/app/services/agent/insight/operation/procurement_position_service.py`
- `backend/app/services/agent/insight/operation/hedging_risk_service.py`
- `backend/app/services/agent/insight/operation/signal_service.py`

建议接口：

- `GET /ai-api/v1/insight/operation/reports`
- `GET /ai-api/v1/insight/operation/metrics`
- `GET /ai-api/v1/insight/operation/sales/summary`
- `GET /ai-api/v1/insight/operation/customers/risk-summary`
- `GET /ai-api/v1/insight/operation/procurement-position/summary`
- `GET /ai-api/v1/insight/operation/hedging/summary`
- `GET /ai-api/v1/insight/operation/signals`
- `POST /ai-api/v1/insight/operation/signals/generate`

建议模型：

- 经营报表目录：报表名、CPT 路径、主题、来源表、参数、主指标、口径说明。
- 经营指标目录：指标编码、名称、单位、聚合方式、来源 SQL、维度。
- 经营信号：类型、等级、指标、维度、事实摘要、证据、AI 解释、状态。
- 经营信号反馈：准确性、有用性、人工备注、处理结果。

## 8. 风险与注意点

- CPT 中存在副本、旧版和子表，第一版必须明确主报表，不要把副本和子表重复计入 KPI。
- 部分参数在 FineReport 单元格层过滤，后端重做指标时应把筛选显式写入 SQL 或语义层。
- 流失客户 90/180 天报表实际是“跨阈值当月名单”，不是全量沉默客户池；后端指标名称必须区分。
- `jy_latest_usage` 存在疑似异常年份最大值 `205`，作为年用量来源时需要清洗或只取最新有效年份。
- `jy_accounts_receivable` 中 `actual_payment_date=1900-01-01` 可能代表未回款或默认值，应在应收分析中单独解释。
- 填报维护表是计划值和人工补充事实来源，不能简单当作结果报表。
- 所有经营数据初期仍按既有方案仅管理员可见，接口必须后端鉴权过滤。
