# 仪表盘模块 (dashboard)

## 概述
提供系统首页仪表盘，展示四大核心数据集合的记录数统计、数据分布饼图、Settlement Schedule 报表和 DB Disbursement 报表。

## 路由
| 方法 | 路径 | 说明 | 认证要求 |
|------|------|------|----------|
| GET | / | 重定向到 /dashboard | 无 |
| GET | /dashboard | 仪表盘主页面 | @login_required |
| GET | /api/get_monthly_financing_with_statement_stats | 月度有对账单融资单统计 | @login_required |
| GET | /api/get_settlement_schedule | Settlement Schedule 报表数据 | @login_required |
| GET | /api/get_db_disbursement | DB 放款报表数据 | @login_required |

## 核心逻辑

### 统计卡片
四张卡片分别展示融资订单数、还款记录数、银行对账单数、融资概览数。

### Settlement Schedule 报表
从 `refactoring_financing_overview` 按 `due_date` 分组，汇总 DB 贷款金额、买方还款、未结金额、Air8 已结算金额。支持 `filter_zero` 参数过滤零欠款。

### DB Disbursement 报表
从 `refactoring_financing_overview` 查询 `refactoring_status: "Loan booked"` 的记录，使用每条记录 `bank_statements[0]` 的 Finance Details Start Date 按 Asia/Shanghai 日历月份分组，返回每月平均融资金额和平均利息两个序列。没有数据的月份不生成点；空结果保持现有空数据默认行为。

### 辅助统计
- `get_overdue_stats` — 按月统计逾期融资单数量和平均逾期天数
- `get_monthly_financing_with_statement_stats` — 按月统计有对账单的融资单，支持按供应商过滤
- `get_supplier_list` — 获取供应商名称列表

## 前端技术
- Chart.js 渲染数据分布饼图，支持暗色/亮色主题切换
- Bootstrap 5.3 统计卡片和表格
- AJAX 动态刷新 Settlement Schedule 数据

## 关键文件
| 文件路径 | 职责 |
|----------|------|
| `backend/app/routes/main.py` | 路由层及数据查询逻辑 |
| `backend/app/templates/dashboard.html` | Jinja2 模板，渲染图表和报表 |
