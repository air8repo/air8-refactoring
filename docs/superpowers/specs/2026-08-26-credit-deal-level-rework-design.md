# 设计文档：额度管理 Deal 层重构（预占/实占/结清统一口径 + 明细页重做 + 三层导出）

- 日期：2026-08-26
- 分支：dev
- 状态：草稿

## 第一部分：需求

### 简介

上线后的验收反馈发现额度管理现有口径存在两类问题：一是预占/实占的金额来源与业务预期不符（预占误用了历史累计的 `funded_before` 判定，实占用固定 90% 比例而非真实的银行折算比例）；二是"买方层 → 买卖方层"两级汇总各自独立计算，与最细粒度的单笔融资单（deal）数据没有直接的可追溯关系，导致汇总数字和明细页数字对不上、也无法在明细页看到银行侧真实状态。

本次重构将计算基准下沉到"单笔融资单（deal）"层：先为每笔 deal 计算统一的 Financing Amount 基数，再按状态分流为预占、实占、待结清三个桶，买卖方层和买方层都只是对 deal 层结果的求和，不再各自另算。同时补齐额度明细页（`/credit/detail`）展示银行侧真实字段、汇总行、导出能力，并把额度查询列表的导出从"1 个买方汇总 sheet + N 个买方专属 sheet"改为固定的买方/买卖方/deal 三个 tab。

### 需求 1：银行对账单新增 Advance Ratio 字段

**用户故事**：作为运营人员，我希望系统在导入银行对账单时读取 Advance Ratio（融资成数）列，以便额度计算能使用银行真实的放款比例而不是估算值。

**验收标准**：

1. 当 导入银行对账单 Excel 且存在 `Finance Details - Advance Ratio` 列 时，系统应 将其数值（百分比形式，如 `90` 表示 90%）转换为 `Decimal128` 后写入 `refactoring_bank_statement.finance.advance_ratio_pct`，转换方式与 `finance.interest_rate_pct`/`finance.reference_rate_pct` 一致（复用 `to_decimal` 辅助函数）。
2. 当 该列缺失或单元格为空 时，系统应 将 `finance.advance_ratio_pct` 写为空（与其他百分比字段的空值处理一致），不中断导入。
3. 当 `CleaningService` 清洗银行对账单数据 时，系统应 将 `Finance Details - Advance Ratio` 纳入数值标准化列（`pd.to_numeric`），与 `Finance Details - Interest Rate %` 等字段同等对待。

### 需求 2：Deal 层统一计算（新的核心聚合基础）

**用户故事**：作为风控/财务人员，我希望预占、实占、待结清三个指标都基于同一笔融资单的同一个"Financing Amount"基数计算，以便三者之间的钩稽关系（尤其是结清时的对冲）是自洽的，而不是三套互相独立、口径不一致的公式。

**验收标准**：

1. 当 计算某笔融资单（`refactoring_financing_order` 记录）的 Financing Amount 时，系统应 按 `invoice_number == refactoring_bank_statement.invoice.seller_reference` 查找对账单记录，**不限定 `finance.status` 取值**（即未到 `Loan booked` 阶段的记录也可能已有对账单，需要能取到值）；找到时取 `invoice.original_amount × finance.advance_ratio_pct ÷ 100`；未找到匹配对账单时，回退取 `refactoring_financing_order.financing_amount`（原始融资金额字段）。
2. 当 计算预占（Earmark Forecast）时，系统应 在该笔融资单满足 `status == 'eligible'` 且 `bank_finance_status != 'Loan booked'`（`bank_finance_status` 为 `refactoring_financing_order` 上已有的存量衍生字段，本次不改其计算逻辑）时，取该笔的 Financing Amount 作为预占金额，否则预占为 0。
3. 当 计算实占（Credit Utilization）时，系统应 在该笔融资单满足 `bank_finance_status == 'Loan booked'` 时，取该笔的 Financing Amount 作为实占金额，否则实占为 0。
4. 当 计算待结清（To Be Settled on DB）时，系统应 在该笔融资单同时满足 `settled_in_air8 == 'Settled'`（Air8 侧已结清）且 `bank_finance_status == 'Loan booked'`（DB 侧尚未变化，用作"DB 尚未结清"的判定依据）时，按 `finance_request_number` 查询 `refactoring_bank_repayment_record`（若存在多条取 `created_at` 最新一条）取其 `settlement_amount` 字段；当该字段不是数值（如字符串 `'Pending for settlement'`）或找不到匹配记录时，待结清金额为空；不满足前述中间态条件时，待结清金额同样为空（不是 0）。
5. 当 计算该笔的 Total O/S 时，系统应 用 `预占 + 实占 - 待结清`（待结清为空时按 0 参与计算）。
6. 当 展示该笔融资单的银行侧原始状态时，系统应 额外提供（不影响以上金额计算）：`finance_status_display`（步骤 1 匹配到的对账单 `finance.status` 原始值，未匹配到时为空）与 `settlement_status`（同一对账单的 `invoice.settlement_status` 原始值，未匹配到时为空）。
7. 当 展示融资单的业务状态（`status` 字段）为 `'funded before'` 时，系统应 在页面展示为 `'Funded Successfully'`（仅改展示文案，不改存储值、不影响 REQ-IMPORT-004 中 `status` 字段本身的计算与取值）。

### 需求 3：买卖方层 / 买方层聚合改为对 Deal 层求和

**用户故事**：作为风控/财务人员，我希望买卖方层和买方层的预占/实占/Headroom 数字，就是其名下全部融资单 deal 层数字的直接加总，以便三层数据始终可以互相勾稽核对。

**验收标准**：

1. 当 计算某买卖方配对（uid）的预占/实占/待结清/Total O/S 时，系统应 对该 uid 下全部融资单按需求 2 计算出的对应指标求和。
2. 当 计算某买方（buyer_code）的对应指标时，系统应 对该买方下全部买卖方配对的对应指标求和。
3. 当 计算 Headroom 与占用率时，系统应 沿用既有公式（`Headroom = Celling − Total O/S`，`占用率 = Total O/S ÷ Celling`），仅将等号右侧的 `Total O/S` 换为需求 3.1/3.2 的新聚合结果；`Celling` 的取值方式（`refactoring_onboard_config.refactoring_limit`）、全外连接规则、`target_list_status='N'` 配对计入汇总的规则均不变（沿用 REQ-CREDIT-001/002 既有验收标准）。

### 需求 4：额度查询列表页文案调整

**用户故事**：作为风控/财务人员，我希望列表页的列名更准确地反映业务含义，以便区分"预计将要占用"和"已经占用"的额度。

**验收标准**：

1. 当 页面语言为英文 时，系统应 将买方层与买卖方层表格中原 `Reserved` 列标题改为 `Earmark Forecast`，原 `Actual` 列标题改为 `Credit Utilization`；中文列标题（预占/实占）不变。

### 需求 5：额度明细页（`/credit/detail`）重做

**用户故事**：作为风控/财务人员，我希望在额度明细页看到每笔融资单的预占/实占/待结清拆分、银行侧真实状态字段，以及本页汇总的合计行，以便核实某个买卖方配对的额度占用是如何由具体单据构成的。

**验收标准**：

1. 当 用户访问 `/credit/detail` 时，系统应 按现有 `buyer_name`+`supplier_name`+`financing_currency` 精确匹配、按 `due_date` 降序展示（分页 20 条/页不变），每行展示：FR#、发票号、Financing Amount（需求 2.1 新公式）、Earmark Forecast（预占）、Credit Utilization（实占）、To Be Settled on DB（待结清，为空时展示 N/A）、Total O/S、Status（`funded before` 展示为 `Funded Successfully`，其余状态值原样展示）、Finance Details - Finance Status（需求 2.6 的 `finance_status_display`）、Invoice Details - Settlement Status（需求 2.6 的 `settlement_status`）、到期日、放款日（`actual_funding_date`）、批次号。
2. 当 页面渲染表格 时，系统应 在表格末尾新增一行合计（Total），对 Financing Amount、Earmark Forecast、Credit Utilization、To Be Settled on DB、Total O/S 五列求和；合计范围为该买卖方配对下**全部**符合过滤条件的记录（不受当前页分页影响）。
3. 当 聚合/查询过程中发生异常 时，系统应 捕获异常并在页面展示错误信息，不导致页面崩溃（沿用既有错误处理约定）。

### 需求 6：额度查询列表页导出改为买方/买卖方/Deal 三个固定 Tab

**用户故事**：作为运营人员，我希望导出的 Excel 有固定的买方、买卖方、Deal 三个 sheet，并且每个 sheet 都有合计行，以便离线核对不同颗粒度的数字。

**验收标准**：

1. 当 用户在额度查询列表页点击导出（`POST /credit/export`） 时，系统应 生成一个包含固定 3 个 sheet 的 Excel：`Buyer`（买方层，一行一个买方）、`Buyer-Supplier`（买卖方层，一行一个配对，平铺展示，不再按买方拆分为多个 sheet）、`Deal`（deal 层，一行一笔融资单，附带其所属买方/买卖方标识列）。
2. 当 生成任一 sheet 时，系统应 在该 sheet 最后追加一行 `Total`，对该 sheet 全部数值列（Celling/Earmark Forecast/Credit Utilization/待结清/Total O/S 等，`Deal` sheet 为 Financing Amount/Earmark Forecast/Credit Utilization/待结清/Total O/S）求和；非数值列（名称、状态等）留空或展示 `Total` 字样。
3. 当 页面存在 `buyer_name` 过滤条件 时，系统应 仅导出过滤后的买方及其下属买卖方配对、deal（与当前页面查询范围一致）。
4. 当 导出结果为空（无买方数据） 时，系统应 提示"没有找到符合条件的数据"，不生成文件（沿用既有约定）。

### 需求 7：额度明细页新增导出

**用户故事**：作为运营人员，我希望在额度明细页也能导出当前买卖方配对下的全部 deal 明细，以便针对单个配对做离线核对。

**验收标准**：

1. 当 用户在 `/credit/detail` 页面点击导出 时，系统应 生成一个 Excel，包含该买卖方配对下**全部**符合过滤条件的 deal 记录（不受分页限制），列与需求 5.1 的页面列一致，末尾追加需求 5.2 口径一致的合计行。
2. 当 导出结果为空 时，系统应 提示"没有找到符合条件的数据"，不生成文件。

### 非功能需求

- 本次重构不改变 `_post_process_financing_records`（`backend/app/services/import_service.py`）中 `bank_finance_status`/`status`/`funded_before` 等既有衍生字段的计算逻辑与查询范围，避免影响导出、聚合、批次管理等其他依赖这些字段的既有模块。
- Deal 层新增的对账单查询（不限 `finance.status`）与 `refactoring_bank_repayment_record` 查询均为额度模块内部的只读查询，不写入/修改任何集合。
- 沿用"实时聚合、不落库"的既有原则（见 2026-08-20 spec 非功能需求）。

### 边界与排除项

- 不修改 `_post_process_financing_records` 本身的 `bank_finance_status` 计算范围（即不把它改成不限 `finance.status` 的宽松查询）——宽松查询只用于额度模块自己新增的 Financing Amount / 展示字段计算，避免影响其他依赖 `bank_finance_status` 的模块（放款文件生成、还款文件生成等）。
- 不追溯修正历史已导入的银行对账单文档的 `advance_ratio_pct`（用户确认会做一次全量重新导入）。
- 不改动每日预警邮件（`credit_warning_service.py`）的触发/内容逻辑——其复用的 `check_warnings`/聚合函数签名不变，只是聚合函数内部计算口径变化后邮件里的数字会相应变化，属自然生效，不需要额外代码改动。
- 不改动 `/credit/detail` 现有的分页大小、排序字段、过滤参数（`buyer_name`/`supplier_name`/`currency`）。
- 不在本次范围内处理 `refactoring_bank_repayment_record` 缺乏唯一索引导致的历史重复记录问题，仅在读取时按 `created_at` 取最新一条兜底。

## 第二部分：设计

### 概述

新增一个 deal 层计算函数作为唯一数据源，买卖方层/买方层聚合函数改为在其结果上做 groupby-sum，不再各自独立计算。额度明细页与列表导出都改为消费这个 deal 层结果（明细页展示单个买卖方配对下的 deal，导出的 `Deal` sheet 展示全部 deal）。

### 架构

新增/修改文件：

- `backend/app/services/import_service.py`（修改）：`_import_bank_statement` 新增 `finance.advance_ratio_pct` 字段映射（约在现有 `interest_rate_pct`/`reference_rate_pct` 映射旁）。
- `backend/app/services/cleaning_service.py`（修改）：`Finance Details - Advance Ratio` 加入银行对账单数值标准化列表。
- `backend/app/services/credit_limit_service.py`（重构）：
  - 新增 `get_deal_rows(mongo, buyer_filter=None) -> list[dict]`：核心新函数，按 uid 关联 onboard_config，对每笔 `refactoring_financing_order` 计算 Financing Amount / Earmark Forecast / Credit Utilization / To Be Settled on DB / Total O/S / 展示字段，返回 deal 层平铺列表。
  - `get_buyer_supplier_pairs(mongo, buyer_filter=None)`：改为内部调用 `get_deal_rows` 后按 uid 分组求和（含 onboard-only 全外连接分支，历史签名与返回字段保持兼容，供 `credit_export_service.py`/`credit_warning_service.py`/`routes/credit.py` 既有调用方继续使用）。
  - `aggregate_by_buyer(pairs)`：不变。
- `backend/app/routes/credit.py`（修改）：
  - `credit_query_detail`：改为查询该买卖方配对下全部（不分页）匹配的 `refactoring_financing_order`，调用新的 deal 层单笔计算逻辑得到全部 deal 行，Python 内存中做分页切片用于展示，同时用全量结果计算 Total 行。
  - 新增 `credit_detail_export`（`POST /credit/detail/export`）：复用同一套查询+计算，生成单配对 Excel。
  - `credit_export`：调用新的 `build_credit_limit_workbook`（3 tab 结构）。
- `backend/app/services/credit_export_service.py`（重构）：`build_credit_limit_workbook(buyer_rows, pair_rows, deal_rows)` 改为固定生成 `Buyer`/`Buyer-Supplier`/`Deal` 三个 sheet，各自追加 Total 行；新增 `build_deal_detail_workbook(deal_rows)` 供明细页导出复用（单配对场景，同样列结构+Total 行）。
- `backend/app/templates/credit/credit_query.html`（修改）：仅改英文 i18n 文案对应的列标题内容（模板结构不变）。
- `backend/app/templates/credit/credit_detail.html`（重做）：新列、Total 行、导出按钮。
- `backend/app/i18n/en-US.json` / `zh-CN.json`（修改）：新增/调整相关 key。

### 数据模型

无新增集合。新增字段：`refactoring_bank_statement.finance.advance_ratio_pct`（`Decimal128`，来源 `Finance Details - Advance Ratio`）。

Deal 层计算涉及的既有字段来源：

| 用途 | 来源 |
|------|------|
| Financing Amount 基数 | `refactoring_bank_statement`（按 `invoice.seller_reference == financing_order.invoice_number` 任意匹配，不限状态）：`invoice.original_amount × finance.advance_ratio_pct ÷ 100`；未匹配时回退 `financing_order.financing_amount` |
| 预占门槛 | `financing_order.status == 'eligible'` 且 `financing_order.bank_finance_status != 'Loan booked'` |
| 实占门槛 | `financing_order.bank_finance_status == 'Loan booked'` |
| 待结清门槛 | `financing_order.settled_in_air8 == 'Settled'` 且 `financing_order.bank_finance_status == 'Loan booked'` |
| 待结清金额 | `refactoring_bank_repayment_record.settlement_amount`（按 `finance_request_number` 匹配，取 `created_at` 最新一条；非数值或未匹配则为空） |
| 展示用银行状态 | 同一次不限状态的 `refactoring_bank_statement` 匹配结果：`finance.status`、`invoice.settlement_status` |

### 接口设计

- `credit_limit_service.get_deal_rows(mongo, buyer_filter=None) -> list[dict]`：每个 dict 含 `uid, buyer_code, buyer_name, supplier_code, supplier_name, currency, finance_request_number, invoice_number, financing_amount, earmark_forecast, credit_utilization, to_be_settled_on_db, total_os, status, status_display, finance_status_display, settlement_status, due_date, actual_funding_date, batch_number, detail_buyer_name, detail_supplier_name, detail_currency`（`detail_*` 字段延续既有钻取用途）。
- `credit_limit_service.get_buyer_supplier_pairs(mongo, buyer_filter=None)`：签名与既有返回字段不变（内部实现改为基于 `get_deal_rows` 求和）。
- `GET /credit/detail`：查询逻辑改为全量取该配对全部 deal（用于 Total 行与内存分页），响应新增 `total_row` 上下文变量。
- `POST /credit/detail/export`：新增端点，参数与 `GET /credit/detail` 相同的过滤条件（`buyer_name`/`supplier_name`/`currency`，从表单读取）。
- `POST /credit/export`：不变的端点，内部改为拼装三个 tab。

### 错误处理

- 沿用既有约定：聚合异常时捕获并展示错误信息（页面）或 flash+redirect（导出），不抛 500。
- `refactoring_bank_repayment_record.settlement_amount` 取值时做类型防御（非数值时视为空，不参与求和/不抛异常）。

### 测试策略

- `get_deal_rows`：覆盖 Financing Amount 的对账单命中/未命中回退、预占/实占/待结清各自的门槛判断（含"实占+待结清同时命中，Total O/S 抵消为 0"的场景）、`refactoring_bank_repayment_record` 多条取最新、`settlement_amount` 非数值时的空值处理。
- `get_buyer_supplier_pairs`/`aggregate_by_buyer`：验证新的求和结果与 `get_deal_rows` 逐笔相加一致。
- `credit_query_detail`：Total 行为全量而非当页局部和的回归测试。
- `credit_export_service`：3 个 sheet 固定存在、各自 Total 行数值正确、`Deal` sheet 携带买方/买卖方标识列。
- 新增 `/credit/detail/export`：内容与页面 Total 行口径一致。
- 外部依赖（无新增外部 API 调用）无需 mock；沿用 mongomock/MagicMock 风格。

### 影响分析

- `credit_query_detail` 从"数据库分页"改为"取全量后内存分页"，需评估单个买卖方配对下 deal 数量的量级（当前样例 42 条，量级可控；若未来单配对可能达到数千条需重新评估性能，本次不做该优化）。
- `credit_export_service.build_credit_limit_workbook` 签名变化（新增 `pair_rows`/`deal_rows` 参数），`routes/credit.py` 的 `credit_export` 调用处需同步修改。
- `get_buyer_supplier_pairs` 内部实现改变但对外签名/字段不变，`credit_warning_service.py`、既有测试的 mock 调用方式不受影响。
- `docs/system/requirements.md` REQ-CREDIT-001~002 的预占/实占/Headroom 计算口径描述、REQ-CREDIT-003 导出结构描述需同步更新为本次新口径；新增关于明细页与其导出的验收标准。
