# 设计文档：再保理融资单列表重构

- 日期：2026-08-20
- 分支：feature/financing-list-sdd
- 状态：已完成

## 第一部分：需求

### 简介

再保理融资单列表页面（`/maintenance/financing-overview`，对应旧称 Financing Overview List）当前展示 16 个扁平字段，数据来自 `refactoring_financing_overview` 聚合表。业务方基于实际使用反馈，提出了菜单命名、字段顺序/内容、以及底层聚合逻辑三方面的调整需求。梳理过程中发现现有聚合逻辑存在三处取值错误，以及一处会导致部分业务阶段数据永远无法进入列表的过滤逻辑问题，本次一并修正。

页面视觉样式优化（查询区域过高、菜单样式）明确排除在本次范围外，作为后续独立 spec 处理。

### 需求 1：菜单与页面标题命名

**用户故事**：作为系统用户，我希望菜单和页面标题准确反映"再保理融资单"的业务含义，中英文都清晰一致。

**验收标准**：

1. 当用户查看中文界面导航菜单时，系统应显示"再保理融资单列表"（`nav.financing_overview_list`，`zh-CN.json` 中已是此文案，需确认并保留）。
2. 当用户查看英文界面导航菜单时，系统应显示"Refactoring Financing List"（`en-US.json` 中 `nav.financing_overview_list` 需从"Financing Overview List"改为此文案）。
3. 当用户打开该页面时，页面标题（`overview_list.title`）中英文文案应与菜单文案保持一致。

### 需求 2：列表字段重构（顺序、新增、删除、改名）

**用户故事**：作为业务操作人员，我希望列表按新顺序展示完整的再保理业务信息（资金方、账期、再保理平台/状态/结算三个独立状态、再保理侧金额明细等），以便无需切换页面即可核对完整业务链路。

**新字段顺序与来源**（详细字段级映射见「设计 - 数据模型」）：

| # | 中文列名 | 英文列名 | 变更类型 |
|---|---|---|---|
| 1 | 资金方 | Funder | 新增 |
| 2 | 融资申请号 | Finance Request No. | 不变 |
| 3 | 买方 | Buyer | 不变 |
| 4 | 卖方 | Seller | 不变 |
| 5 | 发票号 | Invoice Number | 不变 |
| 6 | 币种 | Currency | 不变 |
| 7 | 发票金额 | Invoice Amount | 改名（原"融资金额"列改名，取值不变） |
| 8 | 利率% | Interest Rate % | 不变 |
| 9 | 帐期（含收款期） | Actual Tenor (Collection Period Involved) | 新增（复合展示） |
| 10 | 融资金额 | Financing Amount (Trade Currency) | 新增列 + 修复取值 bug |
| 11 | 利息 | Interest Amount | 新增 |
| 12 | 发票到期日 | Invoice Due Date | 移动位置，取值不变 |
| 13 | Air8结算状态 | Air8 Settlement Status | 改名+移动位置，取值不变 |
| 14 | 再保理货币 | Refactor Currency | 新增 |
| 15 | 再报理金额 | Refactor Amount (Discount Amount) | 新增 |
| 16 | 再保理利率 | Refactor Interest Rate | 新增 |
| 17 | 再保理利息 | Refactor Interest Amount | 新增 |
| 18 | 再保理利息（逾期） | — | 新增列，本次不接数据源（见「边界与排除项」） |
| 19 | 净再保理金额 | Net Refactor Amount (Purchase Price) | 新增 |
| 20 | 再保理平台状态 | Refactor Portal Status | 新增 |
| 21 | 再保理状态 | Refactor Status | 修复取值 bug（原误取 invoice.status） |
| 22 | 再保理结算状态 | Refactor Settlement Status | 新增 |
| 23 | 银行再保理编号 | Refactor ID | 改名+修复取值 bug（原"银行来源"误取 db_finance_ref） |
| 24 | 再保理成熟日 | Refactor Due Date | 改名（原"Maturity Date"），取值不变 |
| 25 | DB还款日 | — | 不变 |
| 26 | 系统更新时间 | System Update Time | 改名（原"更新时间"），取值不变 |

删除列：汇总状态（`summary_status`）、批次号（`loan_submission_batch`，数据库字段保留，仅列表不展示）。

**验收标准**：

1. 当用户打开融资单列表页面时，系统应按上表顺序展示 26 列表头（中英文随当前语言切换）。
2. 当某条记录关联的银行对账单存在"再保理货币/金额/利率/利息/净再保理金额/平台状态/状态/结算状态"任一字段时，系统应展示该融资单**按 `invoice.creation_time` 降序排序后最新一条**银行对账单的对应取值。
3. 当某条记录没有关联任何银行对账单时，第 14-23 列（再保理相关列）应显示为空，不报错。
4. 当 `financing_order.collection_period` 或 `financing_interest` 字段为空时，第 9/11 列应展示已有部分（如"39 + "或仅"39"），不因缺失而报错或显示异常字符。
5. 当用户查看列表时，"汇总状态"和"批次号"列不应出现在表格中。

### 需求 3：聚合逻辑修正与扩展

**用户故事**：作为数据维护人员，我希望聚合到 `refactoring_financing_overview` 的数据准确反映各阶段的真实状态和金额，包括放款前的早期审批阶段。

**验收标准**：

1. 当银行对账单的 `finance.status` 为"Awaiting file approval"/"Booking requested"/"Booking requested accepted"/"Loan booked"等任意值时，系统应将其纳入聚合范围，不再仅限于 `finance.status = "Loan booked"`。
2. 当聚合某融资申请号的记录时，系统应取值 `refactoring_status` 字段为该融资单最新一条银行对账单的 `finance.status`（而非现有代码错误使用的 `invoice.status`）。
3. 当聚合记录时，系统应新增 `refactor_portal_status` 字段，取值为最新一条银行对账单的 `invoice.status`。
4. 当聚合记录时，系统应新增 `refactor_settlement_status` 字段，取值为最新一条银行对账单的 `settlement_status`。
5. 当聚合记录时，系统应将 `refactor_id` 字段（原 `bank_source`）取值改为最新一条银行对账单的 `invoice.system_invoice_id`（而非现有代码错误使用的 `finance.db_finance_ref`）。
6. 当聚合记录时，系统应将顶层 `financing_amount_trade_currency` 字段取值改为 `financing_order.financing_amount_trade_currency`（而非现有代码错误使用的 `trade_amount`）。
7. 当聚合记录时，系统应新增 `funder` 字段，取值为 `financing_order.insurer`。
8. 当聚合记录时，系统应新增 `refactor_currency`、`refactor_amount`、`refactor_interest_rate_pct`、`refactor_interest_amount`、`refactor_purchase_price` 字段，分别取值最新一条银行对账单的 `invoice.currency`、`finance.finance_amount`、`finance.interest_rate_pct`、`finance.interest_amount`、`finance.purchase_price`。

### 需求 4：上游同步补充字段

**用户故事**：作为数据维护人员，我希望"帐期（含收款期）"和"利息"两列有真实数据来源，而不是长期空白。

**验收标准**：

1. 当通过 n8n 接口或 Excel 导入融资订单数据时，系统应将来源数据中的"Collection Period"列存入 `financing_order.collection_period` 字段。
2. 当通过 n8n 接口或 Excel 导入融资订单数据时，系统应将来源数据中的"Financing Interest"列存入 `financing_order.financing_interest` 字段。
3. 当以上两个来源列缺失时，系统应将对应字段存为空值，不报错、不中断整批导入。

### 非功能需求

- 无新增性能/安全约束；聚合范围扩大（去除 Loan booked 过滤）后处理的银行对账单数量会增加，需在测试中关注批量聚合的执行耗时是否明显劣化。

### 边界与排除项

- 本次不做页面视觉样式优化（查询区域紧凑化、菜单样式），作为下一个独立 spec。
- 第 18 列"再保理利息（逾期）"本次不接入任何数据源，列固定展示为空，计算逻辑留待后续需求明确。
- 不新增筛选条件（沿用现有 6 个筛选字段，仅将 `refactoring_status`/`bank_source`→`refactor_id` 的筛选目标随字段改名同步调整），不新增"再保理平台状态/结算状态"等筛选项。
- 存量 `refactoring_financing_overview` 记录不会自动获得新字段，需重新运行聚合（`manual_aggregate` 或定时任务）才能补齐；本次不提供一次性迁移脚本。
- `financing_order.bank_source`（用于批次管理，固定值 "db"）与本次改动的 `refactoring_financing_overview.refactor_id`（原 `bank_source`）是两个不同集合的同名字段，本次仅改动后者，不影响 `batch_service.py` 等批次管理相关逻辑。
- 死代码 `AggregateService._build_overview_record`（当前无任何调用方）本次一并删除，避免其残留的相同 bug 误导后续维护。

## 第二部分：设计

### 概述

采用「聚合服务改为按融资申请号分组处理银行对账单 + 取最新一条快照 + 修复三处历史取值 bug + 新增字段」的方案。聚合入口从"按单条银行对账单并发处理"改为"按 `seller_reference`/`finance_request_number` 分组，组内按 `invoice.creation_time` 排序取最新"，从根本上解决"多条对账单谁先处理完谁就覆盖"的不确定性问题，同时去掉 `finance.status = 'Loan booked'` 的硬过滤，使早期审批阶段的记录也能进入列表。

### 架构

- `backend/app/services/import_service.py`（修改）——`_import_financing`：新增 `collection_period`（← `Collection Period`）、`financing_interest`（← `Financing Interest`）两个字段读取；`cleaning_service.py` 的 `clean_financing_data` 数值字段清洗列表同步加入 `Financing Interest`。
- `backend/app/services/aggregate_service.py`（重构）：
  - 删除死代码 `_build_overview_record` 及其专属的 `_calculate_totals` 调用路径（`_calculate_totals` 本身仍被其他路径使用，保留）。
  - `aggregate_financing_overview`：查询银行对账单时去掉 `finance.status: 'Loan booked'` 过滤；处理单元从"单条对账单"改为"按 `seller_reference` 分组的对账单列表"，分组后取 `invoice.creation_time` 最新一条用于状态/金额类字段，同时保留全部对账单写入 `bank_statements[]` 数组（不裁剪历史）。
  - `_aggregate_single_finance`：同步去掉 `Loan booked` 过滤，`related_statements` 按 `invoice.creation_time` 降序排序后取首条，替代现有"取查询结果第一个匹配项"的不确定行为。
  - 新增私有辅助函数 `_pick_latest_statement(statements)`，供上述两处复用，避免逻辑再次分叉。
  - 修复三处取值 bug（`refactoring_status`、`refactor_id`/原 `bank_source`、`financing_amount_trade_currency`），新增字段（`funder`、`refactor_portal_status`、`refactor_settlement_status`、`refactor_currency`、`refactor_amount`、`refactor_interest_rate_pct`、`refactor_interest_amount`、`refactor_purchase_price`，`order_details.actual_tenor`/`collection_period`，顶层 `interest_amount_trade_currency`）。
- `backend/app/routes/maintenance.py`（修改）：
  - `flatten_overview_for_display`：按新字段清单取值，新增"帐期"复合字符串拼接（`actual_tenor` + "+" + `collection_period`，任一缺失则只展示已有部分）。
  - `build_overview_filters`：`bank_source` 过滤键改为 `refactor_id`。
  - `financing_overview_list` 路由：`distinct('bank_source')` 改为 `distinct('refactor_id')`。
- `backend/app/templates/maintenance/financing_overview_list.html`（修改）：表头/表体按新顺序重排，筛选表单"银行来源"标签与字段名同步改为"银行再保理编号"。
- `backend/app/i18n/zh-CN.json` / `en-US.json`（修改）：菜单/标题命名（需求1）+ 新增列头文案（需求2）。

### 数据模型

`refactoring_financing_order`（新增字段）：

| 字段 | 类型 | 来源 |
|---|---|---|
| `collection_period` | Number/String | Excel/n8n 列 "Collection Period" |
| `financing_interest` | Decimal128 | Excel/n8n 列 "Financing Interest" |

`refactoring_financing_overview`（新增/变更顶层字段）：

| 字段 | 类型 | 来源 | 说明 |
|---|---|---|---|
| `funder` | String | `financing_order.insurer` | 新增 |
| `refactor_portal_status` | String | 最新对账单 `invoice.status` | 新增 |
| `refactor_settlement_status` | String | 最新对账单 `settlement_status` | 新增 |
| `refactor_currency` | String | 最新对账单 `invoice.currency` | 新增 |
| `refactor_amount` | Decimal128 | 最新对账单 `finance.finance_amount` | 新增 |
| `refactor_interest_rate_pct` | Decimal128 | 最新对账单 `finance.interest_rate_pct` | 新增 |
| `refactor_interest_amount` | Decimal128 | 最新对账单 `finance.interest_amount` | 新增 |
| `refactor_purchase_price` | Decimal128 | 最新对账单 `finance.purchase_price` | 新增 |
| `refactor_id` | String | 最新对账单 `invoice.system_invoice_id` | 改名自 `bank_source`，取值来源同时修正 |
| `refactoring_status` | String | 最新对账单 `finance.status` | 取值来源修正（原 `invoice.status`） |
| `financing_amount_trade_currency` | Decimal128 | `financing_order.financing_amount_trade_currency` | 取值来源修正（原 `trade_amount`） |
| `interest_amount_trade_currency` | Decimal128 | `financing_order.financing_interest` | 新增 |
| `order_details.actual_tenor` | Number | `financing_order.actual_tenor` | 新增 |
| `order_details.collection_period` | Number/String | `financing_order.collection_period` | 新增 |

不变字段（沿用现状）：`finance_request_number`、`buyer_name`、`seller_name`、`order_details.invoice_number/currency/due_date/maturity_date/original_amount`、`interest_rate_pct`、`settled_in_air8`（作为"Air8结算状态"列的取值来源，列名/位置变化，字段本身不变）、`db_loan_settle_date`、`updated_at`。

删除的展示用途（字段本身不删，仅列表不再取用）：`summary_status`、`loan_submission_batch`。

### 接口设计

无新增/修改的对外 API 路由。`GET /maintenance/financing-overview` 返回的模板变量 `data` 中每行新增上述字段；`POST /maintenance/financing-overview/export`（Excel 导出）的字段集合是否同步扩展，本次不在范围内（导出功能维持现有字段，如需扩展另开需求）。

### 错误处理

- 新增字段（`funder`/`collection_period`/`financing_interest`/`refactor_*`）在源数据缺失时一律以空值（`''`/`None`）展示，不抛异常、不阻断整行渲染，与现有 `row.xxx or ''` 的模板容错模式保持一致。
- 分组取最新对账单时，若某融资申请号完全没有关联银行对账单，`refactor_*` 系列字段全部为空，`refactoring_status` 保留现有默认值 `'init'` 语义（沿用现状，不改变默认值行为）。
- 聚合过程中单个分组处理异常不应中断整批聚合，沿用现有 try/except 汇总错误信息的模式。

### 测试策略

采用 TDD，外部 API（n8n）按 CLAUDE.md 规则 mock：

- `test_import_service.py`（或对应现有文件）新增用例：验证 `collection_period`/`financing_interest` 正确导入，缺失时为空值。
- `test_aggregate_service.py`（或新建）新增用例：
  - 验证去掉 `Loan booked` 过滤后，非放款阶段的银行对账单也能被聚合。
  - 验证同一融资申请号存在多条银行对账单时，聚合结果取 `invoice.creation_time` 最新一条的状态/金额字段。
  - 验证 `refactoring_status` 取自 `finance.status`、`refactor_id` 取自 `invoice.system_invoice_id`、`financing_amount_trade_currency` 取自 `financing_order.financing_amount_trade_currency`（三处 bug 修复的回归测试）。
  - 验证新增字段（`funder`、`refactor_portal_status` 等）在有/无关联对账单两种情况下的取值。
- `test_financing_overview_list.py` 更新：`flatten_overview_for_display` 按新字段清单展开，"帐期"复合字符串拼接逻辑（含缺失分量场景）。
- 路由层测试：筛选参数 `bank_source`→`refactor_id` 改名后，过滤查询条件与下拉选项来源同步更新的回归验证。

### 影响分析

- **聚合范围扩大**：去除 `Loan booked` 过滤后，`refactoring_financing_overview` 记录数会显著增加（覆盖所有在途融资单，而非仅放款成功的），需要评估对聚合执行耗时、列表分页总数的影响；相关下游若有基于"overview 记录数=放款成功数"的假设（如仪表盘统计），需要逐一排查是否受影响。
- **字段改名影响面**：`bank_source`→`refactor_id` 仅涉及 `refactoring_financing_overview` 集合，与 `financing_order.bank_source`（批次管理用）互不相干，已在「边界与排除项」中明确区分，避免误改批次管理逻辑。
- **存量数据**：改动上线后，存量记录字段不会自动更新，需人工触发一次全量 `manual_aggregate()` 才能让列表页展示新字段与修正后的取值；触发前旧记录仍会按旧结构渲染（模板需对新字段做 `or ''` 兜底，不会报错，但会显示空白）。
- **死代码清理**：删除未被调用的 `_build_overview_record` 属于安全的范围内清理，无外部调用方，不影响现有行为。
