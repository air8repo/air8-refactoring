# 设计文档：银行对账单结清状态/日期原始字段输出

- 日期：2026-06-09
- 分支：历史迁移
- 状态：已完成（历史迁移）

## 第一部分：需求

### 简介

`/api/bank-statement` 接口需要输出两个来自银行原始文件的字段——结清状态（`Invoice Details - Settlement Status`）和结清日期（`Invoice Details - Settlement Date`），且必须保证这两个原始字段不被系统逻辑篡改。既有 `invoice.settlement_date` 在 Excel 单元格为空时会被回退为 `datetime.now()`，导致未结清发票被错误地填上当天日期，属于对银行原始数据的隐性篡改；同时系统此前从未读取过结清状态字段。

> 本文档无原始 2-prd 阶段材料，用户故事与验收标准依据 1-requirement 与 3-design 反推补写。

### 需求 1：API 输出原始结清状态与结清日期

**用户故事**：作为 API 调用方，我希望 `/api/bank-statement` 返回银行对账单中真实的结清状态与结清日期（未结清时为空/None），以便据此判断发票是否真正结清，而不是被系统逻辑污染的日期。

**验收标准**：

1. 当调用 `/api/bank-statement` 接口时，系统应在返回结果中包含 `settlement_status` 字段，其值来自银行文件 `Invoice Details - Settlement Status` 列，未填写时为空字符串。
2. 当某条发票记录的银行文件 `Invoice Details - Settlement Date` 列为空时，系统应在 `settlement_date` 字段返回 `None`，而不是当前日期。
3. 在存量记录尚未包含 `raw_settlement_date` 字段的情况下，当调用接口查询该记录时，系统应回退输出旧的 `settlement_date` 字段值，不报错。

### 需求 2：导入时保存原始字段且不篡改

**用户故事**：作为数据导入维护者，我希望导入银行对账单时如实保存结清状态与结清日期原始值，以便下游任何时候都能追溯到银行文件的真实内容。

**验收标准**：

1. 当导入银行对账单 Excel 时，系统应将 `Invoice Details - Settlement Status` 列的值存入 `invoice.settlement_status` 字段，空值存为空字符串。
2. 当导入银行对账单 Excel 时，系统应将 `Invoice Details - Settlement Date` 列的值存入新字段 `invoice.raw_settlement_date`，空值时保持为 `None`，不做任何默认值回退。
3. 在保存 `raw_settlement_date` 的同时，系统应保留既有 `invoice.settlement_date` 字段及其原有回退逻辑不变，避免影响下游已有计算。

### 非功能需求

- 无新增性能或安全约束。

### 边界与排除项

- 不修改既有 `invoice.settlement_date` 字段的写入逻辑与下游计算（[import_service.py:585-592](../../../backend/app/services/import_service.py#L585)），仅新增 raw 字段，规避回归风险。
- 存量 `refactoring_bank_statement` 记录不会自动回填新字段，需重新导入才能获得 `settlement_status` / `raw_settlement_date`；本迭代未提供一次性迁移脚本。

## 第二部分：设计

### 概述

采用「新增 raw 字段、不改动既有字段与下游逻辑」的方案：在导入阶段新增两个原始字段忠实保存银行文件内容，在 API 输出阶段优先使用新字段并对旧记录保持向后兼容回退。

### 架构

- `backend/app/services/import_service.py`（修改）— `_import_bank_statement`：`invoice` 子文档新增 `settlement_status`（← `Invoice Details - Settlement Status`，空值存 `''`）与 `raw_settlement_date`（← `Invoice Details - Settlement Date`，空值保持 `None`，不回退 `datetime.now()`）。
- `backend/app/routes/api.py`（修改）— `_serialize_bank_statement`：新增 `settlement_status` 输出；`settlement_date` 改为优先输出 `raw_settlement_date`，旧记录缺失该字段时回退到既有 `settlement_date`。
- `backend/tests/test_api_bank_statement.py`（新增）— 验证接口输出结清状态/日期、未结清发票日期为 `None`。
- `backend/tests/test_import_bank_settlement.py`（新增）— 验证导入存储 raw 字段、空值保持为空。

### 数据模型

集合 `refactoring_bank_statement`，`invoice` 子文档新增两个字段：

- `invoice.settlement_status`（字符串，来自 `Invoice Details - Settlement Status`，空值为 `''`）
- `invoice.raw_settlement_date`（日期或 `None`，来自 `Invoice Details - Settlement Date`，空值保持 `None`）

既有 `invoice.settlement_date` 字段及索引不变。

### 接口设计

`GET /api/bank-statement` 返回结构新增字段：

```json
{
  "settlement_status": "",
  "settlement_date": null
}
```

`settlement_date` 输出优先级：`raw_settlement_date`（新记录）→ 既有 `settlement_date`（旧记录兼容）。

### 错误处理

无特殊错误处理需求；对旧记录缺字段的情况通过字段回退保证接口不抛错，不需要额外校验分支。

### 测试策略

采用 TDD：先编写两组失败测试（触发 `KeyError: 'settlement_status'`）确认 RED，实现后转 GREEN，全套回归 108 passed。新增用例覆盖接口输出结清状态/日期、未结清发票日期为 `None`、导入存储 raw 字段、空值保持为空。

### 影响分析

- 不改动既有 `settlement_date` 写入逻辑与下游 `if db_settlement_date:` 判断，回归风险低。
- 对外接口输出银行原始字段时应保留空语义（`None`/`''`），不为类型整齐填默认值，这一原则可作为后续同类字段设计的参考。
- 存量数据需重新导入才能获得新字段，如业务需要历史数据也带上新字段，需额外编写一次性迁移脚本（本迭代未做）。
