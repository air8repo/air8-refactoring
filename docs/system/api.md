# API 接口文档

## 1. 概述

系统提供两类 API：
- **内部页面路由**：Flask-Login session 认证，服务 Web UI
- **外部 API**：Token 认证（`X-API-Token` 头或 `?token=` 参数），供外部系统调用

## 2. 认证方式

### 页面访问（Flask-Login）
用户通过 `/auth/login` 登录，系统设置 session cookie，后续请求通过 `@login_required` 验证。

### 外部 API（Token）
- 请求头：`X-API-Token: <token>`
- 或查询参数：`?token=<token>`
- Token 配置在 `config.py` 的 `API_TOKEN` 字段

---

## 3. 认证模块 (/auth)

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| GET/POST | /auth/login | 登录 | 否 |
| GET/POST | /auth/register | 注册 | 否 |
| GET | /auth/logout | 登出 | 是 |

## 4. 仪表盘模块 (/)

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| GET | / | 重定向到 /dashboard | 否 |
| GET | /dashboard | 仪表盘页面 | 是 |
| GET | /api/get_monthly_financing_with_statement_stats | 月度融资统计 | 是 |
| GET | /api/get_settlement_schedule | 清算计划报表 | 是 |
| GET | /api/get_db_disbursement | DB 放款报表 | 是 |

**清算计划参数**：`filter_zero` (bool) — 过滤零欠款

## 5. 数据导入模块 (/import)

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| GET | /import/ | 导入页面 | 是 |
| POST | /import/upload | 上传 Excel 导入 | 是 |
| POST | /import/import_from_api | 从 API 导入数据 | 是 |

**upload 参数**：
- `file` (multipart) — Excel 文件（.xlsx/.xls，最大 16MB）
- `import_type` (str) — onboarding/financing/repayment/bank_statement
- `bank_channel` (str, 默认 DB)

## 6. 数据导出模块 (/export)

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| GET | /export/ | 导出页面 | 是 |
| POST | /export/generate | 生成导出文件 | 是 |
| POST | /export/generate_db_loan_file | 生成 DB 放款文件 | 是 |
| POST | /export/generate_db_repayment_file | 生成 DB 还款文件 | 是 |
| POST | /export/refresh-financing-orders | 刷新融资单 | 是 |
| POST | /export/update_overview | 更新融资概览 | 是 |

**generate 参数**：`data_type`、`export_type` (csv/excel/pdf)、过滤条件（可选）

## 7. 数据维护模块 (/maintenance)

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| GET | /maintenance/ | 数据概览 | 是 |
| GET | /maintenance/table/\<table_name\> | 查看集合数据 | 是 |
| GET/POST | /maintenance/edit/\<table_name\>/\<doc_id\> | 编辑文档 | 是 |
| GET/POST | /maintenance/add/\<table_name\> | 新增文档 | 是 |
| GET | /maintenance/delete/\<table_name\>/\<doc_id\> | 删除文档 | 是 |
| GET | /maintenance/repayment_batches | 还款批次页面 | 是 |
| POST | /maintenance/repayment_batches/void/\<batch_date\> | 作废还款批次 | 是 |

**合法 table_name**：onboarding、financing、repayment、statement、overview

## 8. 批次管理 API

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| GET | /api/batches | 所有批次列表 | 是 |
| GET | /api/batches/\<batch_number\> | 批次详情 | 是 |
| PUT | /api/batches/\<batch_number\>/cancel | 作废批次 | 是 |
| GET | /api/batches/by-fr/\<fr_number\> | 按融资号查询批次 | 是 |
| GET | /api/batches/status-count | 状态统计 | 是 |

**响应格式**：`{"code": 0, "msg": "success", "data": {...}}`

## 9. 工具模块 (/tools)

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| GET | /tools/ | 工具首页 | 是 |
| GET | /tools/invoice-download | 发票下载页面 | 是 |
| POST | /tools/invoice-download | 执行发票下载 | 是 |

**发票下载参数**：`financing_nos` (str, 换行分隔) → 返回 ZIP 文件

## 10. 外部 API 模块 (/api)

以下端点使用 Token 认证：

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| GET | /api/financing/wip-pending | 查询 wip_pending>0 的融资单 | Token |
| POST | /api/financing/refresh | 刷新所有融资单 | Token |
| GET | /api/onboard-config | 获取上线配置 | Token |
| POST | /api/import/from-api | 从 API 导入数据 | Token |

**wip-pending 返回**：`{success, total, data: [{finance_request_number, invoice_number, wip_pending, ...}]}`

## 11. 语言设置

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| GET | /set_language/\<language\> | 设置语言 | 是 |
| POST | /api/switch_language | 切换语言 API | 是 |

支持：zh-CN、en-US（Cookie 有效期 30 天）

## 12. 外部 API 依赖

### n8n Webhook
- **发票下载**：`https://n8n.air8.cn/webhook/downloadInvoiceFiles`
  - 参数：`token`、`financingNos`（逗号分隔）
  - 返回：JSON 数组 `[{invoice_no, financing_no, download_url, ...}]`
- **融资/还款数据导入**：通过 ImportService 调用 n8n webhook

## 13. 响应格式

**内部 API**：
```json
{"code": 0, "msg": "success", "data": {...}}
```

**外部 API**：
```json
{"success": true, "message": "...", "total": 10, "data": [...]}
```
