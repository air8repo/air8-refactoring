# 批次管理模块 (batch)

## 概述
提供融资订单批次号的查询、详情查看、作废操作和状态统计功能，批次作废后自动触发数据聚合刷新融资概览。

## 路由
| 方法 | 路径 | 说明 | 认证要求 |
|------|------|------|----------|
| GET | /api/batches | 获取所有批次列表 | @login_required |
| GET | /api/batches/<batch_number> | 获取指定批次详情 | @login_required |
| PUT | /api/batches/<batch_number>/cancel | 作废指定批次 | @login_required |
| GET | /api/batches/by-fr/<fr_number> | 根据融资申请号查询批次 | @login_required |
| GET | /api/batches/status-count | 各批次状态数量统计 | @login_required |

## 核心逻辑
- **批次查询**：MongoDB 聚合管道按 `batch_number` 分组（排除 0），统计订单数量和状态
- **批次作废**：重置 `batch_number` 为 0、清空 `batch_status` 和 `batch_created_at`，然后触发全量聚合

## API 响应格式
```json
{"code": 0, "msg": "success", "data": {...}}
```

## 关键文件
| 文件路径 | 职责 |
|----------|------|
| `backend/app/routes/batch.py` | 5 个 API 端点 |
| `backend/app/services/batch_service.py` | BatchService 类，批次查询/作废/统计 |
