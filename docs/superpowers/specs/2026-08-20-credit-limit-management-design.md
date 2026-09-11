# 设计文档：额度管理（买方/买卖方维度，含预占/实占与每日预警）

- 日期：2026-08-20
- 分支：dev
- 状态：草稿

## 第一部分：需求

### 简介

再保理业务需要对 DB 银行核准的买卖方额度进行统一管理，包括"在途"（Air8 已放款但 DB 尚未确认）部分。当前系统已有的额度查询（REQ-CREDIT-001/002）仅按买卖方维度展示未结余额，未与 DB 额度上限对比，也没有买方层面的汇总视图，更没有预占/实占的区分和超额预警能力。本功能在现有额度查询基础上重做为"买方层汇总 + 供应商层钻取 + FR 明细"三级视图，引入 DB 额度上限（Celling）、预占、实占、可用余量（Headroom）等核心指标，并新增每日超额/临近超额的邮件预警。数据量不大，本期采用实时查询聚合，不新增持久化表。

### 需求 1：买方层额度汇总查询

**用户故事**：作为风控/财务人员，我希望按买方（Obligor）维度查看额度上限、预占、实占、可用余量的汇总，以便快速判断该买方整体授信敞口是否接近或超过 DB 核准额度。

**验收标准**：

1. 当 用户访问 `/credit/credit-query` 时，系统应 按买方（`buyer_code`）汇总展示：Obligor 名称、币种（固定展示 `USD`）、Celling（额度上限）、预占、实占、总额（预占+实占）、Headroom（可用余量 = Celling − 总额）、占用率（总额 / Celling）。
2. 当 计算某买方的 Celling 时，系统应 汇总该买方下全部买卖方配对（`uid`）在 `refactoring_onboard_config.refactoring_limit` 中的值，包含 `target_list_status='N'`（尚未提交名单）的配对。
3. 当 计算某买方的预占时，系统应 汇总该买方下全部 `refactoring_financing_order` 记录中满足 `funded_before=True` 且 `bank_finance_status != 'Loan booked'` 的记录的 `financing_amount`。
4. 当 计算某买方的实占时，系统应 汇总该买方下全部满足 `bank_finance_status='Loan booked'` 的融资单关联的 `refactoring_bank_statement.finance.outstanding_amount`（按 `invoice_number = invoice.seller_reference` 关联）。
5. 当 某买方的 Celling 为 0 或不存在对应 onboard 配置 时，系统应 将占用率标记为不可计算（展示为 N/A），并在页面上视为风险状态高亮。
6. 当 用户提交 `buyer_name` 过滤参数 时，系统应 按大小写不敏感的模糊匹配过滤买方名称后再聚合。
7. 当 某买方的占用率超过预警阈值（默认 90%，见需求 6） 时，系统应 在列表中高亮该行。
8. 当 聚合过程中发生异常 时，系统应 捕获异常并在页面展示错误信息，不导致页面崩溃。

### 需求 2：供应商层钻取

**用户故事**：作为风控/财务人员，我希望点击某个买方即可展开其下所有供应商配对的额度明细，以便核实买方层汇总数字的构成。

**验收标准**：

1. 当 用户在买方层列表点击展开某买方 时，系统应 展示该买方下每个买卖方配对（uid）的：Supplier 名称、币种（`USD`）、Celling、预占、实占、总额、Headroom、占用率，计算口径与需求 1 相同但不做买方层汇总（单配对粒度）。
2. 当 供应商层某配对占用率超过预警阈值 时，系统应 高亮该行。

### 需求 3：FR 明细钻取（复用现有 `/credit/detail`）

**用户故事**：作为风控/财务人员，我希望从供应商层继续钻取到具体融资单（FR No）明细，以便核对占用金额是否有异常单据。

**验收标准**：

1. 当 用户在供应商层点击某配对的明细入口 时，系统应 跳转至 `/credit/detail`，沿用现有按 `buyer_name`+`supplier_name`+`financing_currency` 精确匹配、分页（20条/页）、按 `due_date` 降序展示的逻辑，不做改动。

### 需求 4：额度数据导出

**用户故事**：作为运营人员，我希望将当前额度视图导出为 Excel，以便离线分析或汇报。

**验收标准**：

1. 当 用户在额度查询页面点击导出并调用 `POST /credit/export` 时，系统应 生成一个 Excel 文件：第一个 sheet 为买方层汇总（需求 1 的全部字段），随后每个买方一个 sheet 展示该买方下的供应商层明细（需求 2 的全部字段）。
2. 当 买方名称包含 Excel sheet 名非法字符或超过 31 字符 时，系统应 清理非法字符并截断、去重后作为 sheet 名。
3. 当 导出时页面存在 `buyer_name` 过滤条件 时，系统应 仅导出过滤后的买方集合。
4. 当 生成的工作簿为空（无任何买方数据） 时，系统应 提示"没有找到符合条件的数据"，不生成空文件。

### 需求 5：每日额度预警

**用户故事**：作为业务负责人，我希望系统每天自动检查各买卖方配对及买方层的额度占用情况，超过阈值时通过邮件提醒相关人员，以便及时跟进降额或补充授信。

**验收标准**：

1. 当 系统非测试环境启动 时，系统应 通过 APScheduler 注册每日北京时间 07:00 的定时任务（避开 02:00 Onboarding 同步与 06:00 FCB 每日推送）。
2. 当 定时任务执行 时，系统应 复用需求 1/2 的实时聚合逻辑，分别计算买方层与买卖方配对层的占用率。
3. 当 存在占用率超过阈值（默认 90%，硬编码于 `backend/app/config.py`，本期不提供 UI 配置） 的买方或配对 时，系统应 汇总明细（买方/配对名称、Celling、预占、实占、总额、Headroom、占用率）通过 `COMMON_EMAIL_URL` 发送一封 HTML 表格通知邮件（JSON 入参 `{type:'common', title, body}`，收件人由 n8n 侧管理，系统不传收件人列表）。
4. 当 不存在超阈值项 时，系统应 跳过发送，不产生空邮件。
5. 当 邮件发送失败 时，系统应 记录错误日志，不影响定时任务其余流程及下次调度。
6. 当 用户提交 `POST /credit/api/trigger-warning-check` 时，系统应 立即执行同一套预警检查逻辑并返回本次检查结果摘要（超阈值买方数、配对数、邮件是否发送）。

### 非功能需求

- 本期所有额度指标均按 USD 币种统一展示，不做汇率换算；多币种支持留待下一版本。
- 额度计算全部为实时查询聚合，不新增持久化集合存储计算结果。
- 外部 n8n API 调用需设置超时并捕获异常（参照 REQ-NFR-003）。

### 边界与排除项

- 不做额度阈值/收件人的 UI 配置界面。
- 不做多币种汇率换算。
- 不改动 `refactoring_onboard_config` 的数据同步逻辑（币种字段留待下一版本）。
- 不新增额度快照/历史趋势记录（如需追溯历史占用率需另开需求）。
- 不改动 `/credit/detail` 现有逻辑与字段。

## 第二部分：设计

### 概述

在现有 `credit` 蓝图基础上重写 `/credit/credit-query` 为买方层汇总 + 供应商层钻取的两级视图（前端 JS 展开/收起，无需跳转新页面），新增 `/credit/export` 导出端点与 `/credit/api/trigger-warning-check` 手动触发端点，新增一个每日 07:00 的 APScheduler 定时任务。核心是一个新的聚合服务函数，按 `uid` 关联 `refactoring_onboard_config`（Celling）与 `refactoring_financing_order`/`refactoring_bank_statement`（预占/实占），供页面查询、导出、预警三处复用。

### 架构

新增/修改文件：

- `backend/app/services/credit_limit_service.py`（新增）：核心聚合逻辑
  - `get_buyer_supplier_limits(buyer_filter=None) -> list[dict]`：返回买卖方配对粒度的额度记录（含 buyer_code 分组键，供路由层再按 buyer_code 汇总或直接展示供应商层）
  - `aggregate_by_buyer(pair_rows) -> list[dict]`：将配对粒度记录按 `buyer_code` 汇总为买方层记录
  - `check_warnings(pair_rows, buyer_rows, threshold) -> dict`：筛选超阈值项，返回预警明细
- `backend/app/services/credit_warning_service.py`（新增）：定时任务注册、邮件发送、手动触发入口，模式参照 `onboarding_sync_service.py` / `daily_export_service.py`
- `backend/app/routes/credit.py`（修改）：重写 `credit_query` 视图，新增 `credit_export`、`trigger_warning_check` 视图
- `backend/app/templates/credit/credit_query.html`（修改）：买方层表格 + 展开供应商层子表格（沿用 Bootstrap 5.3 折叠组件）
- `backend/app/config.py`（修改）：新增 `CREDIT_WARNING_THRESHOLD = 0.9`
- `backend/app/extensions.py`（修改）：注册 `register_credit_warning_job`

### 数据模型

无新增集合。字段来源：

| 指标 | 来源集合 | 字段/口径 |
|------|---------|-----------|
| Celling | `refactoring_onboard_config` | 按 `uid` 取 `refactoring_limit`；`uid` 缺失时视为 0 |
| 预占 | `refactoring_financing_order` | `funded_before=True` 且 `bank_finance_status != 'Loan booked'` 的记录，`SUM(financing_amount)` |
| 实占 | `refactoring_financing_order` 关联 `refactoring_bank_statement` | `bank_finance_status='Loan booked'` 的记录，按 `invoice_number = bank_statement.invoice.seller_reference` 关联，`SUM(bank_statement.finance.outstanding_amount)` |
| 买方分组键 | `refactoring_onboard_config.buyer_code` 优先，缺失时取 `refactoring_financing_order.buyer_code` | 用于买方层汇总与展示名（`obligor_name`/`buyer_name`） |
| 供应商分组键 | 同上，取 `supplier_code`/`seller_name`（`obligor_name`+`seller_name` 缺失时回退 `buyer_name`/`supplier_name`） | 展示名 |

买卖方配对全集 = `refactoring_onboard_config` 全部 `uid` 并集 `refactoring_financing_order` 中出现的全部 `uid`（全外连接），任一侧存在即纳入统计，缺失侧对应指标记为 0。

### 接口设计

- `GET /credit/credit-query?buyer_name=<str>`
  - 返回买方层列表（`buyer_rows`）及嵌套的供应商层数据（`pair_rows`，按 `buyer_code` 分组传给模板供前端展开），复用 `credit_limit_service.get_buyer_supplier_limits` + `aggregate_by_buyer`。
- `POST /credit/export`（表单参数同 `buyer_name` 过滤）
  - 生成 Excel（openpyxl），返回文件下载响应，风格与 `export_service` 现有导出（表头加粗/填充/边框/自适应列宽）保持一致。
- `POST /credit/api/trigger-warning-check`
  - 立即执行 `credit_warning_service.run_warning_check_manual()`，返回 `{success, checked_buyers, checked_pairs, warned_count, email_sent}`。

### 错误处理

- Mongo 未连接：页面/接口返回明确错误提示，不抛出未捕获异常（参照现有 `credit.py` try/except 模式）。
- 聚合异常：捕获后记录日志，页面展示错误信息（沿用 REQ-CREDIT-001 现有做法）。
- 邮件发送失败：记录日志，不影响定时任务其余步骤和下次调度（参照 REQ-NFR-003 / REQ-IMPORT-006）。
- 导出时结果集为空：提示"没有找到符合条件的数据"，不生成文件（参照 REQ-EXPORT-001）。

### 测试策略

使用 mongomock 构造 `refactoring_onboard_config`/`refactoring_financing_order`/`refactoring_bank_statement` 测试数据，覆盖：

- 预占/实占/总额计算：不同 `funded_before`/`bank_finance_status` 组合下的分类正确性
- 买方层汇总：多供应商配对聚合、`target_list_status='N'` 配对计入、uid 仅存在于一侧（onboard 无 financing 或反之）的边界情况
- Celling 缺失（占用率 N/A）与超阈值高亮判定
- 导出：sheet 数量、sheet 名清理截断、空结果不生成文件
- 预警：阈值判定、无超阈值项时不发邮件、mock `requests.post` 验证邮件请求体结构、邮件发送异常不中断定时任务
- 手动触发端点：`POST /credit/api/trigger-warning-check` 返回结构

外部 n8n 邮件接口调用一律 mock，不发起真实网络请求（参照 `docs/claude/testing.md`）。

### 影响分析

- 现有 `/credit/credit-query` 页面结构与返回字段变化较大（原按 buyer_supplier+currency 三维分组的平铺列表，改为买方层+供应商层两级），需要同步检查是否有其他页面/脚本直接依赖该页面的旧字段结构（初步排查未发现其他模块引用该页面输出，仅为用户直接访问）。
- `/credit/detail` 不改动，兼容原有链接方式，但跳转参数改由新供应商层数据提供（`buyer_name`/`supplier_name`/`financing_currency` 语义不变）。
- 新增定时任务与现有 02:00/06:00 任务共用同一个 `BackgroundScheduler` 实例，需确认 07:00 时间点不与未来任务冲突。
- REQ-CREDIT-001/002 验收标准将在本 spec 实施计划全部完成后合并进 `docs/system/requirements.md`（按 `docs/claude/spec-workflow.md` 流程），届时替换现有条目内容。
