# 导出模块 (export)

## 概述
提供数据导出功能，支持将融资订单、还款订单、银行对账单和融资概览数据导出为 CSV、Excel、PDF 三种格式；同时支持生成银行放款文件和还款文件（ZIP 包），以及触发融资单刷新和概览数据聚合更新。

## 路由
| 方法 | 路径 | 说明 | 认证要求 |
|------|------|------|----------|
| GET | /export/ | 导出页面 | @login_required |
| POST | /export/generate | 通用数据导出（Excel/CSV/PDF） | @login_required |
| POST | /export/generate_db_loan_file | 生成 DB 放款文件（ZIP） | @login_required |
| POST | /export/generate_db_repayment_file | 生成 DB 还款文件（ZIP） | @login_required |
| POST | /export/refresh-financing-orders | 刷新所有融资单后处理逻辑 | @login_required |
| POST | /export/update_overview | 触发聚合更新融资概览 | @login_required |

## 核心逻辑

### 1. 通用数据导出
- 支持数据类型：financing / repayment / statement / overview
- 支持过滤：finance_request_number、invoice_number、refactoring_status
- CSV 使用 `utf-8-sig` 编码兼容 Excel 打开中文
- Excel 使用 openpyxl 引擎，自动应用表头样式和自适应列宽
- PDF 使用 ReportLab 生成表格报告

### 2. DB 放款文件生成
- 筛选 `can_push_to_db_today == True` 的融资订单
- 自动获取下一个批次号并更新订单的批次字段
- 生成 ZIP 文件（汇总 Excel + 按供应商分组的 Excel）

### 3. DB 还款文件生成
- 筛选 `wip_pending > 0` 且未结算的订单
- 更新 `db_loan_settle_date`，关联银行对账单获取发票详情
- 保存还款批次记录到 `refactoring_bank_repayment_record`

## 依赖关系
| 依赖 | 用途 |
|------|------|
| pandas | DataFrame 数据处理与导出 |
| openpyxl | Excel 文件生成与样式 |
| ReportLab | PDF 报告生成 |
| ImportService | 融资单刷新功能复用 |
| AggregateService | 融资概览聚合更新 |

## 关键文件
| 文件路径 | 职责 |
|----------|------|
| `backend/app/routes/export.py` | 定义导出相关路由 |
| `backend/app/services/export_service.py` | 核心导出服务，包含数据查询、格式转换、文件生成 |
