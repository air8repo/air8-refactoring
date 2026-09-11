# 数据聚合模块 (aggregation)

## 概述
将融资订单、还款记录和银行对账单三个数据源进行关联聚合，生成融资概览（financing_overview）汇总记录，供仪表盘和导出使用。

## 核心逻辑

### 聚合流程（aggregate_financing_overview）
1. 从 `refactoring_bank_statement` 中筛选 `finance.status = "Loan booked"` 的记录
2. 提取唯一 `seller_reference`，批量查询关联的融资订单
3. 提取 `finance_request_number`，批量查询关联的还款记录
4. 使用 `ThreadPoolExecutor` 并行处理每条对账单
5. 逐条生成概览记录（关联融资单 + 还款记录 + 银行对账单）
6. 使用 `bulk_write` + `UpdateOne(upsert=True)` 批量写入 `refactoring_financing_overview`

### 汇总计算（_calculate_totals）
所有金额使用 Python `Decimal` 精确计算，最终存储为 MongoDB `Decimal128`：
- `air8_finance_amt` — 融资金额
- `air8_settled_fr_amt` — 已结算金额（还款记录累计）
- `finance_amount_usd` / `interest_amount_usd` / `outstanding_amount_usd` — USD 明细
- `purchase_price_usd` — 购买价格

### 单笔聚合
支持指定单个 `finance_request_number` 进行聚合，不必全量处理。

## 依赖关系
| 依赖 | 说明 |
|------|------|
| pymongo / bson.Decimal128 | MongoDB 驱动及高精度数值类型 |
| concurrent.futures.ThreadPoolExecutor | 多线程并行处理 |

## 关键文件
| 文件路径 | 职责 |
|----------|------|
| `backend/app/services/aggregate_service.py` | AggregateService 类，聚合逻辑完整实现 |
