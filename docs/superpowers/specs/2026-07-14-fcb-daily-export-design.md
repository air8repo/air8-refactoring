# 设计文档：FCB 每日定时导出与邮件推送

- 日期：2026-03-16
- 分支：历史迁移
- 状态：已完成（历史迁移）

## 第一部分：需求

### 简介

FCB 交易数据此前需要用户手动在导出页面触发，无法满足每日固定时间自动推送的业务需求。本功能新增 FCB 每日定时推送任务：每日北京时间 6:00 AM 自动获取当日 FCB 发票数据、生成 Excel、下载发票附件并打包，通过 n8n 邮件接口发送给业务方；同时保留手动触发入口。

> 本文档无原始 2-prd 阶段材料，用户故事与验收标准依据 1-requirement 与 3-design 反推补写。

### 需求 1：每日定时自动导出并邮件推送

**用户故事**：作为业务方，我希望每天固定时间自动收到 FCB 交易数据 Excel 和发票附件邮件，以便无需人工登录系统手动导出。

**验收标准**：

1. 当系统时间到达北京时间每日 6:00 AM 时，系统应自动执行数据获取、Excel 生成、发票附件下载与邮件发送的完整流程。
2. 当定时任务获取到当日 FCB 发票数据后，系统应复用 `fcb_service` 的 Excel 生成逻辑生成交易数据文件。
3. 当 Excel 生成完成后，系统应复用 `tools` 模块的批量下载逻辑获取对应发票附件并打包为 ZIP。
4. 当 Excel 与附件均准备完成后，系统应通过 n8n 邮件接口以 `multipart/form-data` 方式发送邮件，附带 Excel 与 ZIP 附件。
5. 当任一步骤（获取数据、生成 Excel、下载附件、发送邮件）失败时，系统应记录日志并继续/终止后续处理，但不应导致整个应用崩溃。

### 需求 2：手动触发定时任务

**用户故事**：作为系统用户，我希望能够在需要时手动触发一次每日导出推送，而不必等到定时时间，以便临时补发或验证。

**验收标准**：

1. 当用户在 FCB 导出页面点击「手动触发推送」按钮时，系统应立即执行一次与定时任务相同的完整流程。
2. 当手动触发执行完成（无论成功或失败）时，系统应向用户返回执行结果提示。

### 非功能需求

- 定时任务基于 `APScheduler`（`BackgroundScheduler`，时区 `Asia/Shanghai`，cron `hour=6, minute=0`）。
- 定时任务仅在非测试环境、且非 Flask debug reloader 子进程中启动，避免 reloader 导致的双重调度。
- 各步骤独立 `try/except`，外部 API 调用统一 120 秒超时。

### 边界与排除项

- 邮件收件人（`to` 字段）当前未在本迭代中配置，由 n8n 侧固定处理。
- 未将任务执行记录写入 MongoDB 做审计追踪。

## 第二部分：设计

### 概述

在应用启动时初始化一个后台 `APScheduler`，定时调用新增的 `daily_export_service`，该服务按顺序编排「获取数据 → 生成 Excel → 下载附件 → 发送邮件」四步，并最大化复用 iter-003（FCB 模块）与 iter-001（发票下载工具）已有的服务函数，避免重复实现。

### 架构

- `backend/app/services/daily_export_service.py`（新增）— 定时任务核心编排逻辑。
- `backend/app/extensions.py`（修改）— 新增 `scheduler` 全局变量，在 `init_extensions` 中启动 `APScheduler`。
- `backend/app/config.py`（修改）— 新增 `DAILY_EXPORT_EMAIL_URL` / Token 配置。
- `backend/app/routes/fcb.py`（修改）— 新增 `/api/trigger-daily-export`（POST）手动触发端点。
- `backend/app/templates/fcb/export.html`（修改）— 新增「手动触发推送」卡片和按钮。
- `backend/app/i18n/{zh-CN,en-US,zh,en}.json`（修改）— 新增 `daily_push_*` 翻译键。
- `backend/tests/test_daily_export.py`（新增）— 16 个测试用例。

复用清单：嵌套 JSON 解析（`fcb_service` 同格式）、MongoDB 客户查询（`fcb_service._get_collection()`）、Excel 生成（`fcb_service._build_excel()`）、批量 API 调用（`tools._call_invoice_api()`）、文件下载（`tools._download_file()`）。

### 数据模型

无新增集合。查询逻辑复用 `fcb_clients` 及既有融资/发票相关集合。

### 接口设计

流程步骤：

1. `GET exportFcbRefactoringInvoicesDaily` 外部 API → 解析嵌套 JSON → 提取 `financing_no` 列表。
2. 复用 `fcb_service` 生成 Excel。
3. 复用 `tools` 模块下载发票附件并打包 ZIP。
4. `POST multipart/form-data` 到 `n8n.air8.cn/webhook/commonSendEmailForRefactoring` 发送邮件（Excel + ZIP 作为附件）。

内部路由：`POST /fcb/api/trigger-daily-export`，手动执行上述四步流程并返回执行结果。

### 错误处理

四个步骤各自独立 `try/except`，单步失败仅记录日志、不阻断已完成的其余处理；所有外部 API 调用设置 120 秒超时，避免定时任务线程长时间挂起。Flask debug reloader 会启动两个进程，需通过 `WERKZEUG_RUN_MAIN` 环境变量判断，仅在主进程启动一次 scheduler，防止任务被重复调度执行两次。

### 测试策略

`backend/tests/test_daily_export.py` 共 16 个测试用例，覆盖数据获取、Excel 生成、附件下载、邮件发送各步骤及整体编排、异常容错场景；外部 n8n API 与邮件接口按 CLAUDE.md 规则 mock。

### 影响分析

- Flask + APScheduler 需注意 app context：scheduler 线程无 request context，需手动 `app.app_context()`，否则涉及 `current_app` 或数据库访问的代码会报错。
- 对 `fcb_service` 与 `tools` 模块无侵入式修改，仅复用其既有函数，风险面较小。
- 后续如需按业务动态指定邮件收件人，或扩展到其他状态（如 Loan Cancelled）通知，可在此基础上参数化。
