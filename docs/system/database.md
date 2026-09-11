# 数据库设计文档

## 1. 概述

系统使用 **MongoDB** 作为数据存储，通过 PyMongo 驱动通信。金融数据使用 `Decimal128` 类型保证精度。

## 2. 连接配置

| 环境 | 配置类 | 数据库名 |
|------|--------|---------|
| 开发 | DevelopmentConfig | refactoring |
| 测试 | TestingConfig | refactoring_test |
| 生产 | ProductionConfig | refactoring_prod |

连接在 `backend/app/extensions.py` 中初始化，通过 `MONGODB_URI` 环境变量配置。

## 3. 集合说明

### 3.1 refactoring_onboard_config — Onboarding 配置表

**主键**：`uid`（买方代码 + 供应商代码）

| 字段名 | 类型 | 说明 |
|--------|------|------|
| uid | String | 唯一标识 |
| air8_buyer_id | String | Air8 买方 ID |
| air8_seller_id | String | Air8 供应商 ID |
| obligor_name | String | 债务人名称 |
| country | String | 国家 |
| seller_name | String | 供应商名称 |
| target_list_status | String | 目标清单状态（Y/N/Pending/Pause） |
| approved_tenor_days | Number | 批准期限(天) |
| max_invoice_count | Number | 最大发票数量 |
| remarks | String | 备注 |
| first_submit_date | String | 首次提交日期 |
| created_at / updated_at | Date | 时间戳 |

### 3.2 refactoring_financing_order — 融资订单表

**主键**：`finance_request_number`

核心字段：

| 字段名 | 类型 | 说明 |
|--------|------|------|
| uid | String | 买方+供应商标识 |
| finance_request_number | String | 融资申请号 |
| invoice_number | String | 发票号 |
| supplier_name/code | String | 供应商信息 |
| buyer_name/code | String | 买方信息 |
| funder_name/code | String | 融资方信息 |
| trade_amount | Decimal128 | 交易金额 |
| financing_amount | Decimal128 | 融资金额 |
| actual_financing_amount | Decimal128 | 实际融资金额 |
| trade_currency | String | 交易货币 |
| financing_currency | String | 融资货币 |
| exchange_rate | Decimal128 | 汇率 |
| interest_rate_fee_charge | Decimal128 | 利率/费用 |
| due_date | Date | 到期日期 |
| status | String | 状态 |
| batch_number | Number | 批次号（0=未批处理） |
| batch_status | String | 批次状态 |
| db_loan_settle_date | Date | DB 贷款结算日期 |
| wip_pending | Decimal128 | WIP/待处理金额 |

状态枚举：`eligible`、`funded before`、`OD related`、`partial paid`、`not on the list / Code mismatch`、`for next phase`

### 3.3 refactoring_repayment_order — 还款订单表

**复合主键**：`finance_request_number` + `settlement_date`

| 字段名 | 类型 | 说明 |
|--------|------|------|
| finance_request_number | String | 融资申请号 |
| invoice_number | String | 发票号 |
| total_principle_amount | Decimal128 | 本金总额 |
| cumulative_repayment | Decimal128 | 累计还款额 |
| os_balance | Decimal128 | 未结余额 |
| cumulative_repaid_principle | Decimal128 | 累计已还本金 |
| due_date | Date | 到期日期 |
| settlement_date | Date | 结算日期 |
| repayment_status | String | 还款状态（Settled/Pending） |

### 3.4 refactoring_bank_statement — 银行对账单表

**主键**：`invoice.system_invoice_id`

嵌套结构：

```
{
  bank_channel: "DB",
  parties: { buyer_name, seller_name, buyer_erp_id, seller_erp_id },
  invoice: {
    system_invoice_id,    // 唯一标识
    status,               // 发票状态
    seller_reference,     // 关联融资订单的 invoice_number
    due_date,
    original_amount: Decimal128,
    currency
  },
  finance: {
    status,               // "Loan booked" 表示已放款
    db_finance_ref,
    finance_amount: Decimal128,
    outstanding_amount: Decimal128,
    interest_amount: Decimal128,
    purchase_price: Decimal128,
    tenor
  },
  usd_details: {
    finance_amount: Decimal128,
    outstanding_amount: Decimal128,
    interest_amount: Decimal128,
    purchase_price: Decimal128
  }
}
```

### 3.5 refactoring_financing_overview — 融资概览表（聚合生成）

**主键**：`finance_request_number`

由 AggregateService 自动聚合生成，关联融资订单 + 还款 + 银行对账单。

核心结构：

```
{
  finance_request_number,
  buyer_name, seller_name,
  loan_submission_batch,
  order_details: { invoice_number, due_date, air8_finance_amt, ... },
  bank_statements: [{ finance_amount, interest_amount_usd, ... }],
  repayments: [{ settlement_date, settlement_amount, ... }],
  totals: {
    air8_finance_amt: Decimal128,
    air8_settled_fr_amt: Decimal128,
    finance_amount_usd: Decimal128,
    interest_amount_usd: Decimal128,
    outstanding_amount_usd: Decimal128,
    purchase_price_usd: Decimal128
  }
}
```

### 3.6 users — 用户表

| 字段名 | 类型 | 说明 |
|--------|------|------|
| _id | ObjectId | MongoDB 主键 |
| username | String | 用户名（唯一） |
| password_hash | String | Werkzeug 密码哈希 |

## 4. 字段类型约定

| 类型 | 用途 | 示例 |
|------|------|------|
| Decimal128 | 所有金额、利率、汇率 | `trade_amount`、`exchange_rate` |
| Date | 日期时间（UTC） | `due_date`、`created_at` |
| Number | 计数、批次号、期限 | `batch_number`、`tenor` |
| String | 分类、状态、标识 | `status`、`finance_request_number` |
| Boolean | 是/否标志 | `is_batch`、`funded_before` |
| 嵌套对象 | 结构化子文档 | `parties`、`invoice`、`finance` |
| 数组 | 多条关联记录 | `bank_statements`、`repayments` |

## 5. 建议索引

```javascript
// financing_order
{ "finance_request_number": 1 }
{ "invoice_number": 1 }
{ "uid": 1 }
{ "batch_number": 1 }

// repayment_order
{ "finance_request_number": 1 }
{ "finance_request_number": 1, "settlement_date": 1 }

// bank_statement
{ "invoice.system_invoice_id": 1 }
{ "invoice.seller_reference": 1 }
{ "finance.status": 1 }

// financing_overview
{ "finance_request_number": 1 }

// onboard_config
{ "uid": 1 }

// users
{ "username": 1 } (unique)
```

## 6. 数据关联关系

```
onboard_config.uid ←→ financing_order.uid
financing_order.invoice_number ←→ bank_statement.invoice.seller_reference
financing_order.finance_request_number ←→ repayment_order.finance_request_number
financing_overview 聚合以上三个集合
```

## 7. 数据导入幂等性

| 导入类型 | 集合 | 去重键 |
|----------|------|--------|
| onboarding | onboard_config | uid |
| financing | financing_order | finance_request_number |
| repayment | repayment_order | finance_request_number + settlement_date |
| bank_statement | bank_statement | invoice.system_invoice_id |
