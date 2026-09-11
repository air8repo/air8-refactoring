# 导入模块 (import)

## 概述
提供 Excel 文件上传和外部 API 数据导入功能，支持多种数据类型（客户配置、融资订单、还款订单、银行对账单、融资概览、批次号、还款日期）的清洗与幂等写入（upsert），导入后自动执行后处理逻辑计算衍生字段。

## 路由
| 方法 | 路径 | 说明 | 认证要求 |
|------|------|------|----------|
| GET | /import/ | 导入页面，显示上传表单 | @login_required |
| POST | /import/upload | 处理 Excel 文件上传 | @login_required |
| POST | /import/import_from_api | 从外部 API 拉取数据导入 | @login_required |

## 核心逻辑

### 1. 文件上传与分发
- 校验文件存在性、扩展名（仅 `.xlsx`、`.xls`）和导入类型参数。
- 通过 `pandas.read_excel()` 读取 Excel 内容为 DataFrame。
- 根据 `import_type` 参数分发到对应的清洗方法和导入方法。

### 2. 数据清洗（CleaningService）
每种数据类型对应一个清洗方法，统一执行：缺失值处理、日期标准化、数值标准化、去重（基于业务主键）、空行移除。

支持的清洗方法：
| 方法 | 去重主键 |
|------|----------|
| `clean_onboarding_data` | UID |
| `clean_financing_data` | Finance Request Number + Invoice Number |
| `clean_repayment_data` | Invoice Number + Finance Request Number |
| `clean_bank_statement_data` | System InvoiceID + DB Finance Ref. |
| `clean_financing_overview_data` | Finance Request Number |

### 3. 幂等导入（Upsert 逻辑）
- 根据业务主键查询已有记录：存在则 `replace_one` 更新（保留 `created_at` 和 `_id`），不存在则 `insert_one` 新增。
- 金额字段统一使用 `bson.Decimal128` 存储以避免浮点精度问题。
- 返回格式：`{success, inserted, updated, total}`。

### 4. 融资订单后处理（_post_process_financing_records）
导入融资订单后自动执行，计算衍生字段：`in_the_onboarding_list`、`funded_before`、`is_batch`、`settled_in_air8`、`wip_pending`、`overdue_interest_settled_wip`、`overdue_interest_od_wip`、`status`、`can_push_to_db_today`。

### 5. API 导入
通过 HTTP GET 请求从外部 n8n webhook 接口拉取 JSON 数据，转换为 DataFrame 后复用现有的清洗和导入流程。支持融资订单和还款订单两种类型。

## 依赖关系
| 依赖 | 用途 |
|------|------|
| pandas | Excel 文件读取、DataFrame 数据处理 |
| pymongo / bson | MongoDB 操作，Decimal128 精确数值存储 |
| requests | API 导入时发起 HTTP 请求 |
| CleaningService | 数据清洗服务 |

## 关键文件
| 文件路径 | 职责 |
|----------|------|
| `backend/app/routes/import_data.py` | 定义导入相关路由 |
| `backend/app/services/import_service.py` | 核心导入服务，包含所有数据类型的导入逻辑和融资订单后处理 |
| `backend/app/services/cleaning_service.py` | 数据清洗服务，按数据类型提供清洗方法和记录验证 |
