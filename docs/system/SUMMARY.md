# 系统模块摘要 (L2)

> 各模块一句话概述。详情见 `modules/` 下对应文档。

## 核心模块

| 模块 | 文档 | 概述 |
|------|------|------|
| 认证 | [auth.md](modules/auth.md) | Flask-Login + bcrypt 认证，登录/注册/登出 |
| 数据导入 | [import.md](modules/import.md) | Excel 上传和 API 导入，CleaningService 清洗，幂等 upsert |
| 数据导出 | [export.md](modules/export.md) | 导出 Excel/CSV/PDF，生成 DB 放款/还款文件 |
| 数据聚合 | [aggregation.md](modules/aggregation.md) | 融资+还款+对账单三源聚合生成 financing_overview |
| 批次管理 | [batch.md](modules/batch.md) | 融资订单批次查询、详情、作废和状态统计 |
| 仪表盘 | [dashboard.md](modules/dashboard.md) | 统计卡片、Chart.js 饼图、Settlement Schedule/DB Disbursement 报表 |
| 数据维护 | [maintenance.md](modules/maintenance.md) | 5 个 MongoDB 集合的 CRUD、还款批次管理 |
| 工具 | [tools.md](modules/tools.md) | 发票文件批量下载（n8n API + 并行下载 + ZIP 打包） |

## 系统级文档

| 文档 | 概述 |
|------|------|
| [architecture.md](architecture.md) | 分层架构、9 蓝图、6 服务类、应用工厂模式 |
| [database.md](database.md) | 6 个 MongoDB 集合设计、Decimal128 精度、索引建议 |
| [api.md](api.md) | 内部页面路由 + 外部 Token API，共 30+ 端点 |
