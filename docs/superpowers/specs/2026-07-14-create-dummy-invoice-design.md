# 设计文档：创建 Dummy 发票工具

- 日期：2026-03-01
- 分支：历史迁移
- 状态：已完成（历史迁移）

## 第一部分：需求

### 简介

测试与业务验证场景中，需要快速生成测试用的发票数据。本功能在 Tools 菜单下新增「创建 Dummy 发票」工具：用户输入买方代码、供应商代码和金额 3 个参数，系统调用外部 n8n API 创建测试发票，并将返回的发票信息直接显示在页面上，无需下载文件。

> 本文档无原始 2-prd 阶段材料，用户故事与验收标准依据 1-requirement 与 3-design 反推补写。

### 需求 1：创建 Dummy 发票

**用户故事**：作为系统用户，我希望在 Tools 菜单下通过简单表单创建测试发票，以便快速获得可用于验证的发票数据，而无需在外部系统手工操作。

**验收标准**：

1. 当用户访问「创建 Dummy 发票」页面时，系统应展示买方代码、供应商代码、金额三个输入框和提交按钮。
2. 当用户填写三个参数并提交时，系统应通过 AJAX（不刷新页面）向后端发起请求，后端调用外部 n8n API 创建测试发票。
3. 当外部 API 调用成功时，系统应将返回的发票信息以 JSON 形式在页面结果区域展示。
4. 当外部 API 调用失败或返回错误时，系统应在页面错误区域展示失败提示，而不是无响应。

### 非功能需求

- 功能需登录后才可访问，与其余 Tools 子功能保持一致的访问控制。
- 页面文案需同时支持中文与英文。

### 边界与排除项

- 不涉及数据库读写，发票创建结果完全由外部 n8n API 返回并直接展示，不落库。
- 不提供文件下载，交互模式为 AJAX + JSON 展示，区别于 invoice_download 的文件流下载模式。

## 第二部分：设计

### 概述

复用 iter-001 建立的 `tools_bp` 蓝图与页面模式，新增一组路由与模板。由于本功能返回结构化数据而非文件，前端采用 `fetch` API 提交表单并异步渲染结果，而非 iframe 下载模式。

### 架构

- `backend/app/routes/tools.py`（修改）— 新增 `create_dummy_invoice`（GET，页面）与 `create_dummy_invoice_post`（POST，调用外部 API）两个路由，新增 API URL/Token 常量。
- `backend/app/templates/tools/create_dummy_invoice.html`（新增）— 3 个输入框、AJAX 提交、结果/错误展示区、使用说明侧栏。
- `backend/app/templates/tools/index.html`（修改）— 新增该工具的卡片入口。
- `backend/app/templates/base.html`（修改）— 导航栏 Tools 下拉菜单新增链接。
- `backend/app/i18n/{zh-CN,en-US,zh,en}.json`（修改）— 各新增 16 个 `tools.create_dummy_invoice.*` 翻译键。

### 数据模型

无。本功能不涉及数据库读写。

### 接口设计

外部依赖：`GET https://n8n.air8.cn/webhook/CreateDummyInvoice`，参数 `token`、`buyerCode`、`supplierCode`、`amount`；Token 硬编码在后端路由中（与 invoice_download 一致的安全模式），返回创建的发票信息 JSON，由后端透传给前端展示。

### 错误处理

后端接收 POST 请求后先校验参数，参数缺失或外部 API 返回失败时，向前端返回错误 JSON，前端在错误展示区提示用户，不影响页面其余部分。

### 测试策略

未编写自动化测试用例，采用手动验证功能可用性。

### 影响分析

- 仅在既有 `tools_bp` 蓝图内新增路由与模板，未修改其他业务模块，风险面小。
- 该迭代结束后曾遗漏文档更新（未及时创建迭代目录、更新索引），据此在 CLAUDE.md 中补充了「开发完成检查清单」流程约束（后续迭代文档体系已随本次改造替换）。
