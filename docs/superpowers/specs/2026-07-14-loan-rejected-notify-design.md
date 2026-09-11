# 设计文档：银行对账单 Loan Rejected 邮件通知

- 日期：2026-06-10
- 分支：历史迁移
- 状态：已完成（历史迁移）

## 第一部分：需求

### 简介

银行对账单为全量导入，业务方无法及时得知某笔融资被拒（Loan Rejected/Financing rejected）。本功能在银行对账单导入时检测 `Finance Details - Finance Status`（`finance.status`）/ `Invoice Details - Status`（`invoice.status`）新出现的拒绝/取消类记录，汇总后通过 n8n 通用邮件接口发送一封明细通知邮件，且保证同一笔记录只提醒一次。

> 本文档无原始 2-prd 阶段材料，用户故事与验收标准依据 1-requirement 与 3-design 反推补写。

### 需求 1：新出现的拒绝/取消记录检测与通知

**用户故事**：作为业务方，我希望在银行对账单导入后，新出现的融资拒绝/取消记录能通过邮件及时通知我，以便尽快跟进处理，而不必逐条比对全量数据。

**验收标准**：

1. 当银行对账单全量导入某条记录时，若其 `invoice.status` 含 `rejected` 或 `finance.status` 含 `cancelled`（大小写不敏感、子串匹配），且该记录导入前的旧状态不满足此条件、且此前未被通知过（无 `invoice.rejected_notified_at` 日期戳），系统应将其视为「新出现」并收集到本次待通知列表。
2. 当某条记录被判定为「新出现」时，系统应为其写入 `invoice.rejected_notified_at` 导入日期戳。
3. 在记录已带有 `rejected_notified_at` 日期戳的情况下，当后续全量重导且状态仍满足触发条件时，系统应沿用原有日期戳，不重复计入本次通知（避免 `replace_one` 丢戳后被再次提醒）。
4. 当本次导入结束后待通知列表非空时，系统应汇总生成一封 HTML 明细邮件并通过 n8n 通用邮件接口发送；列表为空时不发送邮件。
5. 当邮件发送失败时，系统应仅记录日志，不影响本次导入的其余处理结果。

### 需求 2：通知邮件内容

**用户故事**：作为邮件收件人，我希望邮件中包含每条新出现记录的关键信息，以便无需登录系统即可初步判断处理优先级。

**验收标准**：

1. 当生成通知邮件时，系统应以 HTML 表格列出每条新出现记录的发票号、买方、卖方、DB Finance Ref、金额（币种+金额）、状态（Invoice Status、Finance Status）、Rejection Reason、Due Date。
2. 当调用 n8n 通用邮件接口时，系统应以 `Content-Type: application/json` 提交 `{type: "common", title, body}`，其中 `type` 固定为 `common`，无需携带 token。

### 非功能需求

- 邮件发送逻辑需与导入主流程解耦，任何邮件相关异常不得导致导入失败或数据未落库。

### 边界与排除项

- 收件人当前由 n8n 侧固定决定，本迭代未提供动态指定收件人的能力。
- 触发状态目前仅覆盖 `rejected` / `cancelled` 两类子串匹配，未参数化支持任意状态（如未来的 Loan Cancelled 单独判定）。
- 复用 `DAILY_EXPORT_EMAIL_URL` 配置项命名，未新增独立配置；实际请求走新增的 `COMMON_EMAIL_URL`（n8n-v2 通用接口），与 iter-004 中 FCB 每日导出使用的旧邮件接口（n8n 旧域名、带 token、multipart）相互独立、互不影响。

## 第二部分：设计

### 概述

在 `_import_bank_statement` 的行循环中，利用已有的 `existing`（旧记录）查询，零额外查询成本地做「状态转变」检测（旧状态非目标值 → 新状态为目标值），叠加持久化的「导入日期戳」二次去重，确保只在真正新出现时通知一次，且兼容历史已拒绝、无戳的存量数据（避免上线即群发）。

### 架构

- `backend/app/services/import_service.py`（修改）— 新增模块级函数 `_fmt_date`、`_send_loan_rejected_notification`；`_import_bank_statement` 增加 `newly_rejected` 列表收集与循环结束后的汇总发送逻辑。
- `backend/app/config.py`（修改）— 新增环境变量 `COMMON_EMAIL_URL`，默认 `https://n8n-v2.air8.cn/webhook/commonSendEmailForRefactoring`。
- `backend/tests/test_import_loan_rejected.py`（新增）— 覆盖新出现/已拒绝/已通知带戳/状态转变/无 reject 触发等场景，以及邮件 helper 的单元测试。

去重身份：bank statement 主键 `invoice.system_invoice_id`（即 invoice_no）；bank_statement 记录本身不含 FR 号。

### 数据模型

集合 `refactoring_bank_statement`，`invoice` 子文档新增字段：

- `invoice.rejected_notified_at`（日期，首次判定为「新出现」时写入首次导入日期戳；后续沿用不覆盖）

### 接口设计

外部依赖：`POST https://n8n-v2.air8.cn/webhook/commonSendEmailForRefactoring`，`Content-Type: application/json`，请求体 `{type: "common", title: <邮件主题>, body: <HTML明细>}`，无需 token，收件人由 n8n 侧决定。

`_send_loan_rejected_notification(newly_rejected: list) -> None`：接收本次汇总的新出现记录列表，生成 HTML 明细并调用上述接口发送。

### 错误处理

邮件发送逻辑以 `try/except` 包裹，调用失败仅记录日志，不影响 `_import_bank_statement` 主流程的导入结果和返回值。

### 测试策略

采用 TDD：先写失败测试（`_send_loan_rejected_notification` 不存在触发 `AttributeError`）确认 RED，实现后 4 个触发场景（新出现、已拒绝无戳的存量兼容、已通知带戳不重复、状态转变判定）测试转 GREEN，补充邮件 helper 单测（`patch('requests.post')` 全局 patch，因 `requests` 为函数内局部 import），全套回归 113 passed。

### 影响分析

- 仅在 `_import_bank_statement` 内增加检测与发送分支，不改变既有导入返回结构和字段写入逻辑，回归风险集中在银行对账单导入路径，需重点回归验证该导入流程。
- 判定状态的子串匹配硬编码为 `rejected` / `cancelled`，后续如需扩展其他触发状态，建议参数化为配置项而非再次硬编码。
