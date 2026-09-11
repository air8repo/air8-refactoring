# 设计文档：FCB 客户维护与交易数据导出模块

- 日期：2026-03-13
- 分支：历史迁移
- 状态：已完成（历史迁移）

## 第一部分：需求

### 简介

FCB（一家合作银行/客户方）需要独立于现有 refactoring 主业务的客户档案维护与交易数据导出能力。本功能将原独立的 FCB Excel 导出系统集成到 refactoring 系统内，在导航栏 Tools 菜单右侧新增「FCB」菜单，包含两个子功能：FCB 客户维护（CRUD）与 FCB 交易数据导出（按融资编号查询 n8n API 并生成符合 FCB 格式要求的 Excel）。

> 本文档无原始 2-prd 阶段材料，用户故事与验收标准依据 1-requirement 与 3-design 反推补写。

### 需求 1：FCB 客户维护

**用户故事**：作为系统用户，我希望能够增删改查 FCB 客户档案（供应商代码、客户名称、客户编号等），以便为交易数据导出提供准确的客户信息匹配依据。

**验收标准**：

1. 当用户访问 FCB 客户维护页面时，系统应以分页表格展示已有客户列表，支持按 `supplier_code` / `customer_name` / `client_number` 关键词搜索。
2. 当用户通过 Modal 表单新增或编辑客户并提交时，系统应写入/更新 MongoDB `fcb_clients` 集合中对应记录。
3. 在待新增客户的 `supplier_code` 已存在的情况下，当用户提交新增时，系统应拒绝写入并提示唯一性冲突（`supplier_code` 建有唯一索引）。
4. 当用户删除某条客户记录时，系统应从 `fcb_clients` 集合中移除该记录。

### 需求 2：FCB 交易数据导出

**用户故事**：作为系统用户，我希望输入融资编号即可导出符合 FCB 要求的交易数据 Excel，以便按银行/客户约定格式提交交易明细。

**验收标准**：

1. 当用户在导出页面输入一个或多个融资编号并提交时，系统应调用外部 n8n API 查询对应交易数据，并按 24 列固定顺序生成 Excel。
2. 在查询结果仅涉及单个客户的情况下，当导出完成时，系统应直接返回一个 `.xlsx` 文件供下载。
3. 在查询结果涉及多个客户的情况下，当导出完成时，系统应为每个客户生成一个 Excel 并打包为一个 ZIP 供下载。
4. 当外部 API 返回的数据为空或查询不到对应融资编号时，系统应提示用户未找到数据，而非生成空文件。

### 非功能需求

- 功能需登录后才可访问。
- 页面文案需同时支持中文与英文。
- 交易数据导出通过前端 Blob 下载，需正确解析 `Content-Disposition` 提取文件名。

### 边界与排除项

- 原设计中「按日期范围筛选导出」未实现，最终仅保留按融资编号输入的导出方式。
- 客户表单中 `customer_state` 省州下拉列表当前仅覆盖美国州列表，暂不支持其他国家/地区。
- Excel 样式生成逻辑与既有 `export_service.py` 存在部分重复，未做抽取共享。

## 第二部分：设计

### 概述

新增独立的 `fcb_bp` 蓝图与 `FCBService` 服务层，复用系统既有的蓝图注册、i18n、模板继承、MongoDB 访问与 Excel 生成模式。核心难点是解析外部 n8n API 返回的「嵌套 JSON 字符串」响应格式。

### 架构

- `backend/app/routes/fcb.py`（新增）— FCB 蓝图路由：2 个页面路由（客户维护、导出）+ 5 个客户 CRUD API + 1 个导出 API，共 8 个路由。
- `backend/app/services/fcb_service.py`（新增）— `FCBService` 类：MongoDB 客户 CRUD、n8n API 调用、Excel/ZIP 生成（`_build_excel()`、`_merge_row()`、`_get_collection()` 等，后续迭代被复用）。
- `backend/app/templates/fcb/clients.html`（新增）— 客户管理 SPA 页面：Bootstrap 表格 + Modal 表单 + 分页搜索。
- `backend/app/templates/fcb/export.html`（新增）— 导出页面：融资编号输入 + Blob 下载。
- `backend/app/routes/__init__.py` / `backend/app/__init__.py`（修改）— 注册 `fcb_bp`，`url_prefix='/fcb'`。
- `backend/app/templates/base.html`（修改）— Tools 菜单后新增 FCB 下拉菜单。
- `backend/app/i18n/{zh-CN,en-US,zh,en}.json`（修改）— 新增 `fcb.*` 翻译键。
- `backend/tests/test_fcb.py`（新增）— 19 个测试用例，覆盖冒烟、页面加载、CRUD API、导出、Excel 列顺序验证。

### 数据模型

MongoDB 新增集合 `fcb_clients`：

- `supplier_code`（唯一索引）
- `customer_name`、`client_number`、`customer_state` 等客户档案字段

### 接口设计

外部依赖：`GET https://n8n.air8.cn/webhook/exportFcbRefactoringInvoices?token=...&financingNos=FN1,FN2`，响应格式为 `[{"data": "[{...json string...}]"}]`，需先取外层 `data` 字段字符串再二次 `json.loads` 解析。

内部 API：客户 CRUD 支持分页与关键词搜索（`supplier_code` / `customer_name` / `client_number`）；导出 API 接收融资编号列表，返回 `.xlsx` 或 ZIP 文件流。

### 错误处理

- 外部 API 返回数据为空：前端提示未找到数据。
- `supplier_code` 唯一索引冲突：新增/编辑客户时返回错误提示。
- 与原设计的偏差：原计划 n8n API 为 `POST /webhook/invoices` 按发票编号查询，实际改为 `GET /webhook/exportFcbRefactoringInvoices` 按融资编号（`financing_nos`）查询，并移除日期范围筛选。

### 测试策略

`backend/tests/test_fcb.py` 共 19 个用例，覆盖蓝图冒烟测试、页面加载、客户 CRUD API（含分页搜索、唯一索引冲突）、导出功能（单客户/多客户/空结果）、Excel 24 列顺序校验；外部 n8n API 调用按 CLAUDE.md 规则 mock。

### 影响分析

- 新增独立蓝图与服务，未修改既有业务路由；对现有导航栏结构有增量变更，需回归验证菜单展示。
- `FCBService._build_excel()` 等方法在后续 iter-004（FCB 每日导出）中被直接复用，是该模块可扩展性的关键设计。
