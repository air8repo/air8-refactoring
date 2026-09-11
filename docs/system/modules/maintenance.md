# 数据维护模块 (maintenance)

## 概述
系统的后台数据管理核心模块，提供对所有核心 MongoDB 集合的 CRUD 操作界面，同时管理融资批次和还款批次。

## 路由
| 方法 | 路径 | 说明 | 认证要求 |
|------|------|------|----------|
| GET | /maintenance/ | 数据概览页面 | @login_required |
| GET | /maintenance/table/<table_name> | 分页查看集合数据 | @login_required |
| GET, POST | /maintenance/edit/<table_name>/<doc_id> | 编辑文档 | @login_required |
| GET | /maintenance/delete/<table_name>/<doc_id> | 删除文档 | @login_required |
| GET, POST | /maintenance/add/<table_name> | 新增文档 | @login_required |
| GET | /maintenance/batches | 融资批次列表页面 | @login_required |
| GET | /maintenance/repayment_batches | 还款批次管理页面 | @login_required |
| POST | /maintenance/repayment_batches/void/<batch_date> | 作废还款批次 | @login_required |

## 核心逻辑

### 合法表名白名单
| 路由参数值 | 对应 MongoDB 集合名 |
|-----------|---------------------|
| `onboarding` | `refactoring_onboard_config` |
| `financing` | `refactoring_financing_order` |
| `repayment` | `refactoring_repayment_order` |
| `statement` | `refactoring_bank_statement` |
| `overview` | `refactoring_financing_overview` |

### 还款批次作废
1. 查询指定 `batch_date` 的所有还款记录
2. 删除记录（`delete_many`）
3. 清除融资单表中对应的 `db_loan_settle_date`（`$unset`）

### Decimal128 类型转换
`convert_decimal128_to_float()` 递归函数在读取文档后将 `Decimal128` 转为 `float`。

## 关键文件
| 文件路径 | 职责 |
|----------|------|
| `backend/app/routes/maintenance.py` | 路由定义，8 个端点 |
| `backend/app/templates/maintenance/*.html` | 6 个页面模板 |
