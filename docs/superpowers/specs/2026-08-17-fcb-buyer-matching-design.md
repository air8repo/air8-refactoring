# 设计文档：FCB 客户导出按 Buyer 匹配

- 日期：2026-08-17
- 分支：dev
- 状态：草稿

## 第一部分：需求

### 简介

FCB Client Management（`fcb_clients` 集合）目前以 `supplier_code` 作为客户记录的应用层唯一键，一个 supplier_code 只能对应一条客户记录。n8n 的交易接口（`exportFcbRefactoringInvoices`）现已新增 `buyer_code`、`buyer_name` 字段，同一 `supplier_code` 实际上可能对应多个不同的 buyer（对手方）。本功能让 `fcb_clients` 支持同一 supplier_code 下维护多条记录（每条对应一个 buyer），并在导出 FCB Excel 时按 supplier_code + buyer 维度精确匹配客户记录，而不是像现在这样按 supplier_code 直接认领唯一客户。

`fcb_clients` 中已有的 `customer_name` 字段在业务含义上等同于 buyer name。

### 需求 1：客户记录新增 buyer_air8_code 字段

**用户故事**：作为 FCB 客户管理员，我希望能在客户记录上登记该客户对应的 Air8 buyer 编码，以便导出时能精确匹配到具体的 buyer。

**验收标准**：

1. 当管理员在"Edit Client"表单中新增/编辑客户记录时，系统应提供 `buyer_air8_code` 输入框（可选，非必填）。
2. 当 `buyer_air8_code` 未填写时，系统应允许保存该记录（历史数据由管理员后续手动从页面补录，本功能不做批量迁移）。

### 需求 2：同一 supplier_code 允许对应多条客户记录

**用户故事**：作为 FCB 客户管理员，我希望同一个 supplier_code 下能维护多个 buyer 各自的客户资料，以便导出时能为每个 buyer 生成独立、正确的 Excel。

**验收标准**：

1. 当新建客户记录时，若提交的 `buyer_air8_code` 非空，系统应按 `(supplier_code, buyer_air8_code)` 组合查重，若已存在相同组合的记录则拒绝并提示重复。
2. 当新建客户记录时，若提交的 `buyer_air8_code` 为空，系统应按 `(supplier_code, customer_name)` 组合查重，若已存在相同组合的记录则拒绝并提示重复。
3. 当编辑（更新）已有客户记录时，系统应执行与新建相同的查重规则（当前 `update_client` 完全没有查重校验，属于本功能需一并修复的缺口）。

### 需求 3：导出 Excel 时按 supplier_code + buyer 匹配客户记录

**用户故事**：作为财务人员，我希望导出 FCB Excel 时，每一笔交易都能匹配到正确 buyer 对应的客户资料，而不是被同 supplier_code 下的任意一条记录顶替。

**验收标准**：

1. 在同一 supplier_code 下存在多条候选客户记录的前提下，当某条候选记录填写了 `buyer_air8_code` 时，系统应仅用该字段与交易的 `buyer_code` 做精确比较来判定是否命中，不再回退到姓名比较。
2. 在同一 supplier_code 下存在多条候选客户记录的前提下，当某条候选记录未填写 `buyer_air8_code` 时，系统应用该记录的 `customer_name`（去首尾空格、忽略大小写）与交易的 `buyer_name`（同样处理）比较来判定是否命中。
3. 当某笔交易的 supplier_code 在候选客户中找不到任何命中记录，或命中多条记录（歧义）时，系统应将该笔交易计入"未匹配"列表并跳过，不中断本次导出的其余交易处理。
4. 当本次导出请求涉及的全部交易都未匹配到任何客户记录时，系统应整体报错并提示未匹配的 supplier_code/buyer 信息。
5. 当导出结果中存在多个不同客户记录（含同 supplier_code 不同 buyer 的情况）时，系统应按命中的客户记录（而非 supplier_code）分组生成 Excel，即同一 supplier_code 下不同 buyer 的交易各自生成独立文件。

### 非功能需求

- 无新增性能/安全约束；沿用现有 n8n 调用超时（120s）与 `verify=False` 的既有配置（不在本功能范围内调整）。

### 边界与排除项

- 不做历史数据的 `buyer_air8_code` 批量回填，由管理员在页面手动补录。
- 不修改导出 Excel 的输出列（`EXCEL_COLUMNS`），buyer 信息仅用于匹配，不作为导出列展示。
- 不新增 `fcb_clients` 集合上的 MongoDB 层唯一索引（现状本就没有，本功能仅补齐应用层查重逻辑，与现状保持一致的实现方式）。
- 不改动 `_call_n8n_api` 的接口调用方式，只消费其新增的 `buyer_code`/`buyer_name` 字段。

## 第二部分：设计

### 概述

新增一个共享的匹配纯函数 `match_client_for_transaction()`，替换掉 `fcb_service.export_transactions()` 与 `daily_export_service._generate_excel()` 中各自独立实现的 `{supplier_code: client}` 一对一映射逻辑。CRUD 侧新增 `buyer_air8_code` 字段与对应的组合查重规则。

### 架构

| 文件 | 改动 |
|------|------|
| `backend/app/services/fcb_service.py` | 客户 dict 新增 `buyer_air8_code` 字段读写；`create_client`/`update_client` 改为组合查重；新增 `match_client_for_transaction()`；重写 `export_transactions()` 的分组匹配逻辑 |
| `backend/app/services/daily_export_service.py` | `_generate_excel()` 改为调用 `fcb_service.match_client_for_transaction()`，删除本地重复的匹配逻辑 |
| `backend/app/templates/fcb/clients.html` | `FIELDS` 数组与 `#clientModal` 表单新增 `buyer_air8_code` 输入框 |
| `backend/app/routes/fcb.py` | 无需改动（已透传 dict） |

### 数据模型

`fcb_clients` 集合新增字段：

```
buyer_air8_code: str | None   # 可选，Air8 内部 buyer 编码
```

无 MongoDB schema 校验/索引变更（集合本身是 schemaless，现状也没有针对 `fcb_clients` 的 DB 层唯一索引）。

### 接口设计

新增纯函数（`fcb_service.py`）：

```python
def match_client_for_transaction(buyer_code, buyer_name, candidates):
    """在同一 supplier_code 下的候选客户记录中，找到与交易匹配的唯一客户。

    candidates: 同一 supplier_code 下的客户记录列表
    返回: (matched_client_or_None, is_ambiguous: bool)
    """
```

匹配规则（按候选记录逐条判断，不做全局优先级切换）：
- 记录已填 `buyer_air8_code` → 仅当 `buyer_air8_code == buyer_code`（精确）才算命中
- 记录未填 `buyer_air8_code` → 仅当 `normalize(customer_name) == normalize(buyer_name)` 才算命中
  （`normalize` = `str.strip().lower()`）
- 命中 0 条 → `(None, False)`；命中 1 条 → `(client, False)`；命中 ≥2 条 → `(None, True)`（歧义按未匹配处理）

`create_client(data)` / `update_client(client_id, data)` 查重逻辑：

```python
def _duplicate_query(supplier_code, buyer_air8_code, customer_name, exclude_id=None):
    if buyer_air8_code:
        query = {'supplier_code': supplier_code, 'buyer_air8_code': buyer_air8_code}
    else:
        query = {'supplier_code': supplier_code, 'customer_name': customer_name}
    if exclude_id:
        query['_id'] = {'$ne': exclude_id}
    return query
```

`export_transactions()` / `_generate_excel()` 流程调整为：

1. 按 `supplier_code` 分组交易（不变）
2. 批量查询：`{supplier_code: [client, ...]}`（从一对一 dict 改为一对多列表）
3. 对每笔交易调用 `match_client_for_transaction(txn.buyer_code, txn.buyer_name, candidates)`
4. 按匹配到的客户 `_id` 重新分组交易，未匹配/歧义的交易计入 `unmatched` 列表
5. 若 `unmatched` 非空但仍有匹配成功的交易 → 继续生成，日志记录 `unmatched`
6. 若全部未匹配 → 抛 `ValueError`，列出未匹配的 supplier_code + buyer_code/buyer_name

### 错误处理

| 场景 | 处理方式 |
|------|----------|
| 新建/编辑客户，组合键重复 | 409（沿用现有 `ValueError` → HTTP 409 的路由映射） |
| 交易未匹配到任何客户 / 匹配到多条（歧义） | 计入 `unmatched`，跳过该笔交易，不中断整体导出 |
| 本次导出全部交易未匹配 | 抛 `ValueError`，列出未匹配详情，路由层返回错误提示 |
| n8n 交易缺失 `buyer_code`/`buyer_name` 字段 | 视为空值参与比较（大概率导致未匹配，进入 unmatched 列表，不额外抛异常） |

### 测试策略

外部 n8n API 调用一律 mock（沿用 `testing.md` 规则）。新增/更新以下单元测试：

- `match_client_for_transaction()`：
  - 候选记录有 `buyer_air8_code` 且与交易 `buyer_code` 相等 → 命中
  - 候选记录有 `buyer_air8_code` 但与交易 `buyer_code` 不等 → 不命中（即使 customer_name 与 buyer_name 相等也不回退）
  - 候选记录无 `buyer_air8_code`，`customer_name`/`buyer_name` 大小写、首尾空格不同但内容相同 → 命中
  - 候选记录无 `buyer_air8_code` 且姓名不匹配 → 不命中
  - 同 supplier_code 下命中 0 条 / 命中 ≥2 条 → 均返回未匹配（含歧义场景）
- `create_client`/`update_client`：
  - 有 `buyer_air8_code` 时的组合查重（新建冲突、编辑冲突、编辑自身不算冲突）
  - 无 `buyer_air8_code` 时按 `customer_name` 的组合查重
- `export_transactions()` / `_generate_excel()`：
  - 同 supplier_code、不同 buyer 的多条候选记录场景下，交易被正确分流到各自客户，生成对应数量的 Excel 文件
  - 部分未匹配、部分匹配成功时，导出仍正常完成且日志记录未匹配详情
  - 全部未匹配时抛出 `ValueError`

### 影响分析

- **现有单 buyer 场景不受影响**：若某 supplier_code 下始终只有一条客户记录，无论其是否填了 `buyer_air8_code`，只要匹配规则命中该唯一记录即可（`buyer_air8_code` 为空时走 `customer_name` 比较，需要 n8n 侧的 `buyer_name` 与页面 `customer_name` 保持一致，否则会从"总是命中"变为"需要姓名匹配才命中"——这是本次改动对存量数据的行为变化点，需要在上线前用现网数据抽查确认）。
- **两处导出入口行为统一**：`daily_export_service._generate_excel()` 不再维护独立的匹配逻辑，改为依赖 `fcb_service` 的共享函数，消除历史上两处实现可能不同步的风险。
- **`clients.html` 表单**新增字段后，需确认现有 `FIELDS` 驱动的保存/回显逻辑能正确处理新字段（该数组同时驱动读取与保存 payload 构造）。
- **回归验证范围**：FCB 客户 CRUD（新建/编辑重复校验）、手动导出（`POST /fcb/api/export`）、每日定时导出任务（`daily_export_service`）。
