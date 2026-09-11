# 再保理融资单列表重构 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 重构「再保理融资单列表」页面：修正菜单/标题中英文命名，将列表从 16 列扩充/重排为 26 列，并修复底层聚合逻辑中导致数据错误或缺失的 4 处问题（3 处历史取值 bug + 1 处会漏掉未放款阶段数据的硬过滤）。

**Architecture:** 聚合服务改为「按融资申请号分组处理银行对账单、组内取 `invoice.creation_time` 最新一条」，用两个新增的纯函数辅助器（`_pick_latest_statement` / `_build_refactor_snapshot_fields`）消除现有三处代码路径里重复且互相矛盾的取值逻辑；路由层的展示扁平化函数按新字段清单重写；模板按新顺序重排 26 列；i18n 补齐新增列头文案。

**Tech Stack:** Python 3.11 / Flask / PyMongo（MongoDB） / Jinja2 / pytest / pandas（Excel 导入清洗）

**Spec:** `docs/superpowers/specs/2026-08-20-refactoring-financing-list-design.md`

## Global Constraints

- 所有 pytest 用例必须使用 mock（`mock_mongo` fixture / `patch('...get_mongo', ...)`），不得连接真实 MongoDB（CLAUDE.md 测试规范）。
- 每个 task 完成后必须跑一遍 `pytest backend/tests/` 确认全部通过，再提交。
- `financing_order.bank_source`（批次管理用，固定值 "db"）与 `refactoring_financing_overview` 集合的字段互不相干，任何改动只能限定在 `refactoring_financing_overview` 相关代码路径（`aggregate_service.py` / `maintenance.py` 的 overview 相关函数 / `financing_overview_list.html`），不得触碰 `batch_service.py`、`financing_order.bank_source` 写入逻辑。
- 中文文案写入 `zh-CN.json`，英文文案写入 `en-US.json`，两份必须同步更新，key 保持一致。
- 提交信息使用中文，遵循仓库现有 commit message 风格（`feat:`/`fix:`/`test:`/`docs:` 前缀）。

---

## Task 1: 上游同步补充字段（collection_period / financing_interest）

**Files:**
- Modify: `backend/app/services/import_service.py:397-475`（`_import_financing` 方法）
- Modify: `backend/app/services/cleaning_service.py:71-79`（`clean_financing_data` 数值字段清洗）
- Test: `backend/tests/test_import_financing_new_fields.py`（新建）

**Interfaces:**
- Consumes: 无（本 task 不依赖其他 task）
- Produces: `refactoring_financing_order` 集合新增 `collection_period`（int，默认 0）、`financing_interest`（Decimal128，默认 `Decimal128('0')`）两个字段，供 Task 4/5 的聚合逻辑读取。

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_import_financing_new_fields.py`：

```python
"""
Tests for ImportService._import_financing storing the new
collection_period / financing_interest fields synced from n8n.
"""
import pandas as pd
from unittest.mock import patch, MagicMock
from bson import Decimal128

from backend.app.services.import_service import ImportService


def _run_import(rows):
    df = pd.DataFrame(rows)
    mock_mongo = MagicMock()
    mock_mongo.refactoring_financing_order.find_one.return_value = None
    with patch('backend.app.services.import_service.get_mongo', return_value=mock_mongo):
        with patch.object(ImportService, '_post_process_financing_records'):
            ImportService()._import_financing(df)
    return [c.args[0] for c in mock_mongo.refactoring_financing_order.insert_one.call_args_list]


def _base_row(**overrides):
    row = {
        'Finance Request Number': 'RZ001',
        'Invoice Number': 'INV-001',
        'Supplier Code': 'S001',
        'Buyer Code': 'B001',
    }
    row.update(overrides)
    return row


def test_collection_period_stored_from_source_column():
    inserted = _run_import([_base_row(**{'Collection Period': 5})])
    assert inserted[0]['collection_period'] == 5


def test_collection_period_missing_defaults_to_zero():
    inserted = _run_import([_base_row()])
    assert inserted[0]['collection_period'] == 0


def test_financing_interest_stored_from_source_column():
    inserted = _run_import([_base_row(**{'Financing Interest': 33.70})])
    assert inserted[0]['financing_interest'] == Decimal128('33.7')


def test_financing_interest_missing_defaults_to_zero():
    inserted = _run_import([_base_row()])
    assert inserted[0]['financing_interest'] == Decimal128('0')
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest backend/tests/test_import_financing_new_fields.py -v`
Expected: FAIL，`KeyError: 'collection_period'`（字段还不存在）

- [ ] **Step 3: 实现**

在 `backend/app/services/import_service.py` 的 `_import_financing` 方法里，`record = {...}` 字典中，`'actual_tenor': int(row.get('Actual Tenor')) if pd.notna(row.get('Actual Tenor')) else 0,` 这一行后面新增一行：

```python
                'actual_tenor': int(row.get('Actual Tenor')) if pd.notna(row.get('Actual Tenor')) else 0,
                'collection_period': int(row.get('Collection Period')) if pd.notna(row.get('Collection Period')) else 0,
```

`'interest_rate_fee_charge': to_decimal(row.get('Interest Rate/Fee Charge')),` 这一行后面新增一行：

```python
                'interest_rate_fee_charge': to_decimal(row.get('Interest Rate/Fee Charge')),
                'financing_interest': to_decimal(row.get('Financing Interest')),
```

在 `backend/app/services/cleaning_service.py` 的 `clean_financing_data` 方法里，`currency_fields` 列表新增一项：

```python
        currency_fields = [
            'Trade Amount', 'Financing Amount (Trade Currency)', 
            'Financing Amount', 'Actual Financing Amount',
            'Interest Rate/Fee Charge', 'Exchange Rate', 'Financing Interest'
        ]
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest backend/tests/test_import_financing_new_fields.py -v`
Expected: PASS，4 个用例全部通过

- [ ] **Step 5: 跑全量回归**

Run: `python -m pytest backend/tests/ -q`
Expected: 全部通过，无新增失败

- [ ] **Step 6: 提交**

```bash
git add backend/app/services/import_service.py backend/app/services/cleaning_service.py backend/tests/test_import_financing_new_fields.py
git commit -m "feat: 融资订单导入新增 collection_period/financing_interest 字段同步"
```

---

## Task 2: 聚合服务新增共享辅助函数（取最新对账单 + 再保理字段快照）

**Files:**
- Modify: `backend/app/services/aggregate_service.py`（新增两个模块级函数，放在 `get_mongo` 函数之后、`AggregateService` 类定义之前）
- Test: `backend/tests/test_aggregate_service_helpers.py`（新建）

**Interfaces:**
- Consumes: 无
- Produces:
  - `_pick_latest_statement(statements: List[Dict]) -> Optional[Dict]`：入参是 `refactoring_bank_statement` 原始文档列表，按 `invoice.creation_time` 降序返回最新一条；空列表返回 `None`。
  - `_build_refactor_snapshot_fields(latest_statement: Optional[Dict]) -> Dict[str, Any]`：入参是单条银行对账单原始文档（或 `None`），返回包含 `refactoring_status`、`refactor_id`、`refactor_portal_status`、`refactor_settlement_status`、`refactor_currency`、`refactor_amount`、`refactor_interest_rate_pct`、`refactor_interest_amount`、`refactor_purchase_price` 九个 key 的字典，供 Task 4/5 直接 `.update()` 进 overview_record。

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_aggregate_service_helpers.py`：

```python
"""
Tests for the shared aggregation helpers:
  - _pick_latest_statement: pick the newest bank_statement by invoice.creation_time
  - _build_refactor_snapshot_fields: derive top-level overview fields from it
"""
from datetime import datetime
from bson import Decimal128

from backend.app.services.aggregate_service import (
    _pick_latest_statement,
    _build_refactor_snapshot_fields,
)


def _statement(creation_time, **overrides):
    base = {
        'invoice': {
            'creation_time': creation_time,
            'status': 'Financing confirmed',
            'currency': 'USD',
            'system_invoice_id': 'SID-1',
        },
        'finance': {
            'status': 'Loan booked',
            'finance_amount': Decimal128('100'),
            'interest_rate_pct': Decimal128('5.1'),
            'interest_amount': Decimal128('10'),
            'purchase_price': Decimal128('90'),
        },
        'settlement_status': 'Not settled',
    }
    base.update(overrides)
    return base


class TestPickLatestStatement:
    def test_empty_list_returns_none(self):
        assert _pick_latest_statement([]) is None

    def test_single_statement_returned(self):
        s = _statement(datetime(2026, 1, 1))
        assert _pick_latest_statement([s]) is s

    def test_picks_newest_by_creation_time(self):
        older = _statement(datetime(2026, 1, 1), invoice={
            'creation_time': datetime(2026, 1, 1), 'status': 'old', 'currency': 'USD', 'system_invoice_id': 'OLD'
        })
        newer = _statement(datetime(2026, 6, 1), invoice={
            'creation_time': datetime(2026, 6, 1), 'status': 'new', 'currency': 'USD', 'system_invoice_id': 'NEW'
        })
        result = _pick_latest_statement([older, newer])
        assert result['invoice']['system_invoice_id'] == 'NEW'

    def test_missing_creation_time_sorts_before_present_ones(self):
        no_time = _statement(None, invoice={
            'creation_time': None, 'status': 'x', 'currency': 'USD', 'system_invoice_id': 'NO-TIME'
        })
        has_time = _statement(datetime(2026, 1, 1), invoice={
            'creation_time': datetime(2026, 1, 1), 'status': 'y', 'currency': 'USD', 'system_invoice_id': 'HAS-TIME'
        })
        result = _pick_latest_statement([no_time, has_time])
        assert result['invoice']['system_invoice_id'] == 'HAS-TIME'


class TestBuildRefactorSnapshotFields:
    def test_none_statement_returns_empty_defaults(self):
        fields = _build_refactor_snapshot_fields(None)
        assert fields['refactoring_status'] == 'init'
        assert fields['refactor_id'] == ''
        assert fields['refactor_portal_status'] == ''
        assert fields['refactor_settlement_status'] == ''
        assert fields['refactor_currency'] == ''
        assert fields['refactor_amount'] is None
        assert fields['refactor_interest_rate_pct'] is None
        assert fields['refactor_interest_amount'] is None
        assert fields['refactor_purchase_price'] is None

    def test_maps_fields_from_statement(self):
        s = _statement(datetime(2026, 1, 1))
        fields = _build_refactor_snapshot_fields(s)
        assert fields['refactoring_status'] == 'Loan booked'          # finance.status
        assert fields['refactor_id'] == 'SID-1'                       # invoice.system_invoice_id
        assert fields['refactor_portal_status'] == 'Financing confirmed'  # invoice.status
        assert fields['refactor_settlement_status'] == 'Not settled'
        assert fields['refactor_currency'] == 'USD'
        assert fields['refactor_amount'] == Decimal128('100')
        assert fields['refactor_interest_rate_pct'] == Decimal128('5.1')
        assert fields['refactor_interest_amount'] == Decimal128('10')
        assert fields['refactor_purchase_price'] == Decimal128('90')
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest backend/tests/test_aggregate_service_helpers.py -v`
Expected: FAIL，`ImportError: cannot import name '_pick_latest_statement'`

- [ ] **Step 3: 实现**

在 `backend/app/services/aggregate_service.py` 中，`def get_mongo():` 函数结束、`class AggregateService:` 定义之前，插入：

```python
def _pick_latest_statement(statements):
    """从多条银行对账单原始文档中，按 invoice.creation_time 降序取最新一条；无记录返回 None"""
    if not statements:
        return None

    def sort_key(statement):
        creation_time = statement.get('invoice', {}).get('creation_time')
        return creation_time or datetime.min

    return sorted(statements, key=sort_key, reverse=True)[0]


def _build_refactor_snapshot_fields(latest_statement):
    """由最新一条银行对账单派生 refactoring_financing_overview 的再保理相关顶层字段"""
    if latest_statement is None:
        return {
            'refactoring_status': 'init',
            'refactor_id': '',
            'refactor_portal_status': '',
            'refactor_settlement_status': '',
            'refactor_currency': '',
            'refactor_amount': None,
            'refactor_interest_rate_pct': None,
            'refactor_interest_amount': None,
            'refactor_purchase_price': None,
        }

    invoice = latest_statement.get('invoice', {})
    finance = latest_statement.get('finance', {})
    return {
        'refactoring_status': finance.get('status', 'init'),
        'refactor_id': invoice.get('system_invoice_id', ''),
        'refactor_portal_status': invoice.get('status', ''),
        'refactor_settlement_status': latest_statement.get('settlement_status', ''),
        'refactor_currency': invoice.get('currency', ''),
        'refactor_amount': finance.get('finance_amount'),
        'refactor_interest_rate_pct': finance.get('interest_rate_pct'),
        'refactor_interest_amount': finance.get('interest_amount'),
        'refactor_purchase_price': finance.get('purchase_price'),
    }
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest backend/tests/test_aggregate_service_helpers.py -v`
Expected: PASS，7 个用例全部通过

- [ ] **Step 5: 跑全量回归**

Run: `python -m pytest backend/tests/ -q`
Expected: 全部通过

- [ ] **Step 6: 提交**

```bash
git add backend/app/services/aggregate_service.py backend/tests/test_aggregate_service_helpers.py
git commit -m "feat: 聚合服务新增取最新对账单/再保理字段快照的共享辅助函数"
```

---

## Task 3: 聚合服务新增 `_format_bank_statement` 辅助函数（提取重复格式化逻辑）

**Files:**
- Modify: `backend/app/services/aggregate_service.py`（新增为 `AggregateService` 的方法）
- Test: `backend/tests/test_aggregate_service_helpers.py`（追加用例）

**Interfaces:**
- Consumes: 无
- Produces: `AggregateService._format_bank_statement(statement: Dict) -> Dict`，入参单条银行对账单原始文档，输出写入 `overview.bank_statements[]` 数组的扁平化字典（在现有字段基础上新增 `settlement_status`），供 Task 4/5 复用。

- [ ] **Step 1: 写失败测试**

在 `backend/tests/test_aggregate_service_helpers.py` 末尾追加：

```python
from backend.app.services.aggregate_service import AggregateService


class TestFormatBankStatement:
    def test_includes_settlement_status(self):
        statement = {
            'invoice': {'system_invoice_id': 'SID-1', 'status': 'Financing confirmed', 'currency': 'USD'},
            'finance': {'status': 'Loan booked', 'db_finance_ref': 'REF-1'},
            'usd_details': {},
            'settlement_status': 'Initiated',
        }
        result = AggregateService()._format_bank_statement(statement)
        assert result['settlement_status'] == 'Initiated'
        assert result['system_invoice_id'] == 'SID-1'
        assert result['db_finance_ref'] == 'REF-1'

    def test_missing_settlement_status_is_none(self):
        statement = {'invoice': {}, 'finance': {}, 'usd_details': {}}
        result = AggregateService()._format_bank_statement(statement)
        assert result['settlement_status'] is None
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest backend/tests/test_aggregate_service_helpers.py::TestFormatBankStatement -v`
Expected: FAIL，`AttributeError: 'AggregateService' object has no attribute '_format_bank_statement'`

- [ ] **Step 3: 实现**

在 `backend/app/services/aggregate_service.py` 的 `class AggregateService:` 内，`_process_statement` 方法**之前**新增方法（`_process_statement` 本身在 Task 4 会被替换掉，这里先独立加入新方法）：

```python
    def _format_bank_statement(self, statement):
        """将单条银行对账单原始文档格式化为写入 overview.bank_statements[] 的扁平结构"""
        usd_details = statement.get('usd_details', {})
        invoice = statement.get('invoice', {})
        finance = statement.get('finance', {})
        return {
            'actual_upload_date': datetime.now(),
            'db_finance_ref': finance.get('db_finance_ref'),
            'finance_amount': finance.get('finance_amount'),
            'interest_amount_usd': usd_details.get('interest_amount'),
            'invoice_status': invoice.get('status'),
            'outstanding_amount_usd': usd_details.get('outstanding_amount'),
            'purchase_price_usd': usd_details.get('purchase_price'),
            'start_date': finance.get('start_date'),
            'status': finance.get('status'),
            'system_invoice_id': invoice.get('system_invoice_id'),
            'tenor': finance.get('tenor'),
            'invoice_buyer_reference': invoice.get('buyer_reference'),
            'invoice_seller_reference': invoice.get('seller_reference'),
            'parties_seller_erp_id': statement.get('parties', {}).get('seller_erp_id'),
            'parties_buyer_erp_id': statement.get('parties', {}).get('buyer_erp_id'),
            'parties_buyer_name': statement.get('parties', {}).get('buyer_name'),
            'parties_seller_name': statement.get('parties', {}).get('seller_name'),
            'invoice_issue_date': invoice.get('issue_date'),
            'invoice_due_date': invoice.get('due_date'),
            'invoice_adjusted_due_date': invoice.get('adjusted_due_date'),
            'finance_due_date': finance.get('due_date'),
            'invoice_currency': invoice.get('currency'),
            'invoice_original_amount': invoice.get('original_amount'),
            'invoice_settlement_date': invoice.get('settlement_date'),
            'invoice_creation_time': invoice.get('creation_time'),
            'finance_reference_rate_pct': finance.get('reference_rate'),
            'usd_original_amount': usd_details.get('original_amount'),
            'usd_finance_amount': usd_details.get('finance_amount'),
            'usd_outstanding_amount': usd_details.get('outstanding_amount'),
            'usd_interest_amount': usd_details.get('interest_amount'),
            'usd_purchase_price': usd_details.get('purchase_price'),
            'interest_rate_pct': finance.get('interest_rate_pct'),
            'invoice_vat_rate': invoice.get('vat_rate'),
            'invoice_vat_amount': invoice.get('vat_amount'),
            'outstanding_amount': finance.get('outstanding_amount'),
            'purchase_price': finance.get('purchase_price'),
            'settlement_status': statement.get('settlement_status'),
        }
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest backend/tests/test_aggregate_service_helpers.py -v`
Expected: PASS，全部用例通过

- [ ] **Step 5: 跑全量回归**

Run: `python -m pytest backend/tests/ -q`
Expected: 全部通过

- [ ] **Step 6: 提交**

```bash
git add backend/app/services/aggregate_service.py backend/tests/test_aggregate_service_helpers.py
git commit -m "feat: 聚合服务提取银行对账单格式化公共方法 _format_bank_statement"
```

---

## Task 4: 重构主聚合流程 `aggregate_financing_overview`（去除 Loan booked 过滤 + 按融资单分组）

**Files:**
- Modify: `backend/app/services/aggregate_service.py`（替换 `_process_statement` 为 `_process_statement_group`；修改 `aggregate_financing_overview` 内的查询与分组逻辑）
- Test: `backend/tests/test_aggregate_financing_overview.py`（新建）

**Interfaces:**
- Consumes: `_pick_latest_statement`、`_build_refactor_snapshot_fields`（Task 2）、`self._format_bank_statement`（Task 3）
- Produces: `AggregateService._process_statement_group(self, seller_reference, statements, invoice_to_financing, fr_to_repayments) -> Optional[Dict]`，供本 task 内的 `aggregate_financing_overview` 调用；返回值结构供 Task 7 的 `flatten_overview_for_display` 读取（顶层含 `funder`、`refactor_*` 九个字段、`financing_amount_trade_currency`、`interest_amount_trade_currency`，`order_details` 含 `actual_tenor`、`collection_period`）。

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_aggregate_financing_overview.py`：

```python
"""
Tests for AggregateService.aggregate_financing_overview:
  - no longer filters bank statements by finance.status == 'Loan booked'
  - groups multiple statements per finance request and keeps the latest snapshot
  - fixes refactoring_status / refactor_id / financing_amount_trade_currency sourcing
"""
from unittest.mock import patch, MagicMock
from datetime import datetime
from bson import Decimal128

from backend.app.services.aggregate_service import AggregateService


def _financing_order(**overrides):
    base = {
        '_id': 'order-1',
        'finance_request_number': 'RZ001',
        'invoice_number': 'INV-001',
        'buyer_code': 'B001',
        'buyer_name': 'Buyer Co',
        'supplier_code': 'S001',
        'supplier_name': 'Seller Co',
        'insurer': 'DB Insurance',
        'trade_amount': Decimal128('1000'),
        'financing_amount_trade_currency': Decimal128('950'),
        'financing_interest': Decimal128('12.5'),
        'actual_tenor': 39,
        'collection_period': 5,
        'settled_in_air8': 'Pending for Repayment',
        'status': 'Active',
        'batch_number': 0,
    }
    base.update(overrides)
    return base


def _bank_statement(seller_reference, creation_time, finance_status, **overrides):
    base = {
        'invoice': {
            'seller_reference': seller_reference,
            'creation_time': creation_time,
            'status': 'Financing confirmed',
            'currency': 'USD',
            'system_invoice_id': f'SID-{creation_time.isoformat()}',
        },
        'finance': {
            'status': finance_status,
            'db_finance_ref': 'REF-1',
            'finance_amount': Decimal128('100'),
            'interest_rate_pct': Decimal128('5.1'),
            'interest_amount': Decimal128('10'),
            'purchase_price': Decimal128('90'),
        },
        'usd_details': {},
        'settlement_status': 'Not settled',
    }
    base.update(overrides)
    return base


def _run_aggregate(financing_orders, bank_statements, repayments=None):
    mock_mongo = MagicMock()
    mock_mongo.refactoring_bank_statement.count_documents.return_value = len(bank_statements)
    mock_mongo.refactoring_bank_statement.distinct.return_value = list({
        s['invoice']['seller_reference'] for s in bank_statements
    })
    mock_mongo.refactoring_financing_order.find.return_value = financing_orders
    mock_mongo.refactoring_repayment_order.find.return_value = repayments or []

    mock_cursor = MagicMock()
    mock_cursor.__iter__.return_value = iter(bank_statements)
    mock_mongo.refactoring_bank_statement.find.return_value = mock_cursor

    mock_mongo.refactoring_financing_overview.count_documents.return_value = 1
    bulk_result = MagicMock(upserted_count=1, modified_count=0)
    mock_mongo.refactoring_financing_overview.bulk_write.return_value = bulk_result

    with patch('backend.app.services.aggregate_service.get_mongo', return_value=mock_mongo):
        AggregateService().aggregate_financing_overview()

    ops = mock_mongo.refactoring_financing_overview.bulk_write.call_args[0][0]
    return {op._filter['finance_request_number']: op._doc['$set'] for op in ops}


def test_non_loan_booked_statement_is_aggregated():
    """去除 Loan booked 过滤后，早期审批阶段的对账单也应被聚合"""
    order = _financing_order()
    statement = _bank_statement('INV-001', datetime(2026, 1, 1), 'Booking requested')
    records = _run_aggregate([order], [statement])
    assert 'RZ001' in records


def test_query_no_longer_filters_by_loan_booked_status():
    mock_mongo = MagicMock()
    mock_mongo.refactoring_bank_statement.count_documents.return_value = 0
    with patch('backend.app.services.aggregate_service.get_mongo', return_value=mock_mongo):
        AggregateService().aggregate_financing_overview()
    count_call_filter = mock_mongo.refactoring_bank_statement.count_documents.call_args[0][0]
    assert count_call_filter == {}


def test_multiple_statements_pick_latest_by_creation_time():
    order = _financing_order()
    older = _bank_statement('INV-001', datetime(2026, 1, 1), 'Booking requested')
    newer = _bank_statement('INV-001', datetime(2026, 6, 1), 'Loan booked')
    records = _run_aggregate([order], [older, newer])
    record = records['RZ001']
    assert record['refactoring_status'] == 'Loan booked'
    assert len(record['bank_statements']) == 2  # 历史记录全部保留


def test_refactoring_status_sourced_from_finance_status_not_invoice_status():
    order = _financing_order()
    statement = _bank_statement('INV-001', datetime(2026, 1, 1), 'Loan booked')
    statement['invoice']['status'] = 'Financing confirmed'
    records = _run_aggregate([order], [statement])
    assert records['RZ001']['refactoring_status'] == 'Loan booked'
    assert records['RZ001']['refactor_portal_status'] == 'Financing confirmed'


def test_refactor_id_sourced_from_system_invoice_id_not_db_finance_ref():
    order = _financing_order()
    statement = _bank_statement('INV-001', datetime(2026, 1, 1), 'Loan booked')
    records = _run_aggregate([order], [statement])
    assert records['RZ001']['refactor_id'] == statement['invoice']['system_invoice_id']


def test_financing_amount_trade_currency_sourced_from_order_field_not_trade_amount():
    order = _financing_order(financing_amount_trade_currency=Decimal128('950'), trade_amount=Decimal128('1000'))
    statement = _bank_statement('INV-001', datetime(2026, 1, 1), 'Loan booked')
    records = _run_aggregate([order], [statement])
    assert records['RZ001']['financing_amount_trade_currency'] == Decimal128('950')


def test_new_fields_present():
    order = _financing_order()
    statement = _bank_statement('INV-001', datetime(2026, 1, 1), 'Loan booked')
    records = _run_aggregate([order], [statement])
    record = records['RZ001']
    assert record['funder'] == 'DB Insurance'
    assert record['interest_amount_trade_currency'] == Decimal128('12.5')
    assert record['order_details']['actual_tenor'] == 39
    assert record['order_details']['collection_period'] == 5


def test_totals_use_only_latest_statement_not_sum_of_all():
    """同一融资单多条历史阶段性对账单时，totals 不应把各阶段快照的金额加总"""
    order = _financing_order()
    older = _bank_statement(
        'INV-001', datetime(2026, 1, 1), 'Booking requested',
        usd_details={'interest_amount': Decimal128('999')},
    )
    newer = _bank_statement(
        'INV-001', datetime(2026, 6, 1), 'Loan booked',
        usd_details={'interest_amount': Decimal128('10')},
    )
    records = _run_aggregate([order], [older, newer])
    totals = records['RZ001']['totals']
    assert totals['interest_amount_usd'] == Decimal128('10')  # 只取最新一条，不是 999+10
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest backend/tests/test_aggregate_financing_overview.py -v`
Expected: FAIL（当前查询仍带 `finance.status: 'Loan booked'` 过滤，`refactoring_status` 仍取 `invoice.status`，`bank_statements` 只保留一条，`funder`/`interest_amount_trade_currency` 等字段不存在，`totals` 仍会把多条对账单加总）

- [ ] **Step 3: 实现**

在 `backend/app/services/aggregate_service.py` 中，**删除**整个 `_process_statement` 方法（原第 47-175 行），替换为：

```python
    def _process_statement_group(self, seller_reference, statements, invoice_to_financing, fr_to_repayments):
        """处理某个 seller_reference 对应的全部银行对账单，生成一条融资概览记录"""
        financing_order = invoice_to_financing.get(seller_reference)
        if not financing_order:
            return None

        finance_request_number = financing_order.get('finance_request_number')
        if not finance_request_number:
            return None

        repayments = fr_to_repayments.get(finance_request_number, [])

        bank_statements = [self._format_bank_statement(s) for s in statements]
        latest_statement = _pick_latest_statement(statements)
        refactor_fields = _build_refactor_snapshot_fields(latest_statement)

        formatted_repayments = []
        for repayment in repayments:
            formatted_repayments.append({
                'overdue_interest_wip': repayment.get('adjusted_interest_charges'),
                'repayment_from_buyer_to_air8': repayment.get('cumulative_repayment'),
                'repayment_status': repayment.get('repayment_status'),
                'settled_amt_by_air8_to_db': repayment.get('cumulative_repaid_principle'),
                'settlement_amount': repayment.get('os_balance'),
                'settlement_date': repayment.get('settlement_date')
            })

        order_details = {
            'adjusted_due_date': financing_order.get('due_date'),
            'air8_finance_amt': financing_order.get('actual_financing_amount'),
            'buyer_reference': financing_order.get('reference_no'),
            'currency': financing_order.get('trade_currency'),
            'due_date': financing_order.get('due_date'),
            'fr_settlement_date': financing_order.get('actual_funding_date'),
            'interest_rate_pct': financing_order.get('interest_rate_fee_charge'),
            'invoice_number': financing_order.get('invoice_number'),
            'issue_date': financing_order.get('invoice_date'),
            'maturity_date': financing_order.get('due_date'),
            'original_amount': financing_order.get('trade_amount'),
            'seller_reference': financing_order.get('reference_no'),
            'actual_tenor': financing_order.get('actual_tenor'),
            'collection_period': financing_order.get('collection_period'),
        }

        # totals 只应基于最新一条快照计算，避免同一融资单的历史阶段性对账单被重复加总
        totals = self._calculate_totals(financing_order, repayments, [latest_statement] if latest_statement else [])

        record = {
            'finance_request_number': finance_request_number,
            'buyer_erp_id': financing_order.get('buyer_code'),
            'buyer_name': financing_order.get('buyer_name'),
            'seller_erp_id': financing_order.get('supplier_code'),
            'seller_name': financing_order.get('supplier_name', ''),
            'summary_status': financing_order.get('status'),
            'loan_submission_batch': financing_order.get('batch_number', 0),
            'seq': 0,
            'order_details': order_details,
            'bank_statements': bank_statements,
            'repayments': formatted_repayments,
            'totals': totals,
            'updated_at': datetime.now(),
            'settled_in_air8': financing_order.get('settled_in_air8', ''),
            'db_loan_settle_date': financing_order.get('db_loan_settle_date', ''),
            'invoice_settlement_date_db_updated': '',
            'overdue_interest_settled_wip': '',
            'overdue_interest_od_wip': '',
            'air8_settled_fr_amt': totals.get('air8_settled_fr_amt'),
            'settled_db_loan': totals.get('settled_db_loan'),
            'outstanding_loan_exclude_wip': totals.get('outstanding_loan_exclude_wip'),
            'wip_pending_amount': totals.get('wip_pending_amount'),
            'financing_amount_trade_currency': financing_order.get('financing_amount_trade_currency'),
            'interest_amount_trade_currency': financing_order.get('financing_interest'),
            'interest_rate_pct': financing_order.get('interest_rate_fee_charge'),
            'funder': financing_order.get('insurer'),
        }
        record.update(refactor_fields)
        return record
```

然后修改 `aggregate_financing_overview` 方法：

第一步的过滤条件（原「计算符合条件的记录总数」块）：

```python
            confirmed_statements_count = mongo.refactoring_bank_statement.count_documents({
                'finance.status': 'Loan booked'
            })
```

改为：

```python
            confirmed_statements_count = mongo.refactoring_bank_statement.count_documents({})
```

第二步（`seller_references = mongo.refactoring_bank_statement.distinct(...)`）：

```python
            seller_references = mongo.refactoring_bank_statement.distinct('invoice.seller_reference', {
                'finance.status': 'Loan booked',
                'invoice.seller_reference': {'$ne': None}
            })
```

改为：

```python
            seller_references = mongo.refactoring_bank_statement.distinct('invoice.seller_reference', {
                'invoice.seller_reference': {'$ne': None}
            })
```

第六步（获取银行对账单游标）：

```python
            cursor = mongo.refactoring_bank_statement.find({
                'finance.status': 'Loan booked',
                'invoice.seller_reference': {'$in': seller_references}  # 只处理与融资订单相关的对账单
            }, batch_size=100)  # 每次从数据库获取100条记录
```

改为：

```python
            cursor = mongo.refactoring_bank_statement.find({
                'invoice.seller_reference': {'$in': seller_references}  # 只处理与融资订单相关的对账单
            }, batch_size=100)  # 每次从数据库获取100条记录
```

第七步（原来是「按单条对账单」并发处理，改为「按 seller_reference 分组」后再并发处理）：

```python
            # 第七步：按 seller_reference 分组后处理，生成融资概览记录
            logger.info(f"开始处理 {len(confirmed_statements)} 条银行对账单")

            statements_by_seller_ref = {}
            for statement in confirmed_statements:
                seller_ref = statement.get('invoice', {}).get('seller_reference')
                if seller_ref:
                    statements_by_seller_ref.setdefault(seller_ref, []).append(statement)

            from concurrent.futures import ThreadPoolExecutor
            import concurrent.futures

            all_overview_records = []
            num_threads = min(32, concurrent.futures.ThreadPoolExecutor()._max_workers)

            with ThreadPoolExecutor(max_workers=num_threads) as executor:
                future_to_group = {
                    executor.submit(
                        self._process_statement_group, seller_ref, statements, invoice_to_financing, fr_to_repayments
                    ): seller_ref
                    for seller_ref, statements in statements_by_seller_ref.items()
                }

                for future in concurrent.futures.as_completed(future_to_group):
                    result = future.result()
                    if result:
                        all_overview_records.append(result)

            logger.info(f"并行处理完成，生成了 {len(all_overview_records)} 条融资概览记录")
```

（第八步的批量 upsert 逻辑不变，沿用现有代码。）

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest backend/tests/test_aggregate_financing_overview.py -v`
Expected: PASS，全部用例通过

- [ ] **Step 5: 跑全量回归**

Run: `python -m pytest backend/tests/ -q`
Expected: 全部通过（注意：删除 `_process_statement` 后如有其他测试文件直接调用它，需要一并检查——若存在，先在本 step 记录下来，Task 9 统一处理）

- [ ] **Step 6: 提交**

```bash
git add backend/app/services/aggregate_service.py backend/tests/test_aggregate_financing_overview.py
git commit -m "fix: 主聚合流程去除 Loan booked 过滤并按融资单分组取最新对账单快照"
```

---

## Task 5: 重构 `_aggregate_single_finance`（单条手动聚合，同步修复）

**Files:**
- Modify: `backend/app/services/aggregate_service.py:535-` (`_aggregate_single_finance` 方法)
- Test: `backend/tests/test_aggregate_single_finance.py`（新建）

**Interfaces:**
- Consumes: `_pick_latest_statement`、`_build_refactor_snapshot_fields`（Task 2）、`self._format_bank_statement`（Task 3）
- Produces: `_aggregate_single_finance` 的行为与 Task 4 的批量流程保持一致，供后续「手动触发单个融资单聚合」的 UI 入口使用（无接口签名变化）。

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_aggregate_single_finance.py`：

```python
"""
Tests for AggregateService._aggregate_single_finance:
  - no longer filters by finance.status == 'Loan booked'
  - picks the latest statement by invoice.creation_time when multiple exist
  - settled_in_air8 must come from financing_order, not be hardcoded blank
"""
from unittest.mock import patch, MagicMock
from datetime import datetime
from bson import Decimal128

from backend.app.services.aggregate_service import AggregateService


def _financing_order(**overrides):
    base = {
        'finance_request_number': 'RZ001',
        'invoice_number': 'INV-001',
        'buyer_code': 'B001',
        'buyer_name': 'Buyer Co',
        'supplier_code': 'S001',
        'supplier_name': 'Seller Co',
        'insurer': 'DB Insurance',
        'trade_amount': Decimal128('1000'),
        'financing_amount_trade_currency': Decimal128('950'),
        'financing_interest': Decimal128('12.5'),
        'actual_tenor': 39,
        'collection_period': 5,
        'settled_in_air8': 'Settled',
        'status': 'Active',
        'batch_number': 0,
    }
    base.update(overrides)
    return base


def _bank_statement(db_ref, creation_time, finance_status):
    return {
        'invoice': {
            'seller_reference': 'INV-001',
            'creation_time': creation_time,
            'status': 'Financing confirmed',
            'currency': 'USD',
            'system_invoice_id': f'SID-{creation_time.isoformat()}',
        },
        'finance': {
            'status': finance_status,
            'db_finance_ref': db_ref,
            'finance_amount': Decimal128('100'),
            'interest_rate_pct': Decimal128('5.1'),
            'interest_amount': Decimal128('10'),
            'purchase_price': Decimal128('90'),
        },
        'usd_details': {},
        'settlement_status': 'Not settled',
    }


def _run(financing_order, bank_statements, repayments=None):
    mock_mongo = MagicMock()
    mock_mongo.refactoring_financing_order.find_one.return_value = financing_order
    mock_mongo.refactoring_repayment_order.find.return_value = repayments or []
    mock_mongo.refactoring_bank_statement.find.return_value = bank_statements
    mock_mongo.refactoring_financing_overview.find_one.return_value = None

    with patch('backend.app.services.aggregate_service.get_mongo', return_value=mock_mongo):
        AggregateService()._aggregate_single_finance('RZ001')

    return mock_mongo.refactoring_financing_overview.insert_one.call_args[0][0]


def test_non_loan_booked_statement_is_included():
    order = _financing_order()
    statement = _bank_statement('RZ001', datetime(2026, 1, 1), 'Booking requested')
    record = _run(order, [statement])
    assert record['refactoring_status'] == 'Booking requested'


def test_query_no_longer_filters_by_loan_booked_status():
    order = _financing_order()
    mock_mongo = MagicMock()
    mock_mongo.refactoring_financing_order.find_one.return_value = order
    mock_mongo.refactoring_repayment_order.find.return_value = []
    mock_mongo.refactoring_bank_statement.find.return_value = []
    mock_mongo.refactoring_financing_overview.find_one.return_value = None
    with patch('backend.app.services.aggregate_service.get_mongo', return_value=mock_mongo):
        AggregateService()._aggregate_single_finance('RZ001')
    find_filter = mock_mongo.refactoring_bank_statement.find.call_args[0][0]
    assert find_filter == {}


def test_picks_latest_statement_by_creation_time():
    order = _financing_order()
    older = _bank_statement('RZ001', datetime(2026, 1, 1), 'Booking requested')
    newer = _bank_statement('RZ001', datetime(2026, 6, 1), 'Loan booked')
    record = _run(order, [older, newer])
    assert record['refactoring_status'] == 'Loan booked'
    assert len(record['bank_statements']) == 2


def test_settled_in_air8_sourced_from_financing_order_not_hardcoded_blank():
    order = _financing_order(settled_in_air8='Settled')
    statement = _bank_statement('RZ001', datetime(2026, 1, 1), 'Loan booked')
    record = _run(order, [statement])
    assert record['settled_in_air8'] == 'Settled'


def test_totals_use_only_latest_statement_not_sum_of_all():
    """同一融资单多条历史阶段性对账单时，totals 不应把各阶段快照的金额加总"""
    order = _financing_order()
    older = _bank_statement('RZ001', datetime(2026, 1, 1), 'Booking requested')
    older['usd_details'] = {'interest_amount': Decimal128('999')}
    newer = _bank_statement('RZ001', datetime(2026, 6, 1), 'Loan booked')
    newer['usd_details'] = {'interest_amount': Decimal128('10')}
    record = _run(order, [older, newer])
    assert record['totals']['interest_amount_usd'] == Decimal128('10')  # 只取最新一条，不是 999+10


def test_new_fields_present():
    order = _financing_order()
    statement = _bank_statement('RZ001', datetime(2026, 1, 1), 'Loan booked')
    record = _run(order, [statement])
    assert record['funder'] == 'DB Insurance'
    assert record['financing_amount_trade_currency'] == Decimal128('950')
    assert record['interest_amount_trade_currency'] == Decimal128('12.5')
    assert record['order_details']['actual_tenor'] == 39
    assert record['order_details']['collection_period'] == 5
    assert record['refactor_id'] == statement['invoice']['system_invoice_id']
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest backend/tests/test_aggregate_single_finance.py -v`
Expected: FAIL（现有代码仍按 `finance.status: 'Loan booked'` 查询、`settled_in_air8` 硬编码为 `''`、缺少新字段）

- [ ] **Step 3: 实现**

在 `backend/app/services/aggregate_service.py` 的 `_aggregate_single_finance` 方法中：

第三步查询银行对账单：

```python
            # 第三步：筛选与该融资申请号相关的银行对账单，只处理状态为"Loan booked"的数据
            related_statements = []
            confirmed_statements = list(mongo.refactoring_bank_statement.find({
                'finance.status': 'Loan booked'
            }))
```

改为：

```python
            # 第三步：筛选与该融资申请号相关的银行对账单（不再限定 finance.status）
            related_statements = []
            confirmed_statements = list(mongo.refactoring_bank_statement.find({}))
```

第四步「构建银行对账单数组」整段（从 `bank_statements = []` 到该 if 块结束，含内部完整的 `formatted_bank_statement` 字典）替换为：

```python
            # 第四步：格式化全部匹配的银行对账单，取最新一条用于再保理状态/金额快照
            bank_statements = [self._format_bank_statement(s) for s in related_statements]
            latest_statement = _pick_latest_statement(related_statements)
            refactor_fields = _build_refactor_snapshot_fields(latest_statement)
            # totals 只用最新一条快照计算，避免同一融资单的历史阶段性对账单被重复加总
            totals_source_statements = [latest_statement] if latest_statement else []
```

第六步 `order_details` 字典末尾新增两个 key：

```python
            order_details = {
                'adjusted_due_date': financing.get('due_date'),
                'air8_finance_amt': financing.get('actual_financing_amount'),
                'buyer_reference': financing.get('reference_no'),
                'currency': financing.get('trade_currency'),
                'due_date': financing.get('due_date'),
                'fr_settlement_date': financing.get('actual_funding_date'),
                'interest_rate_pct': financing.get('interest_rate_fee_charge'),
                'invoice_number': financing.get('invoice_number'),
                'issue_date': financing.get('invoice_date'),
                'maturity_date': financing.get('due_date'),
                'original_amount': financing.get('trade_amount'),
                'seller_reference': financing.get('reference_no'),
                'actual_tenor': financing.get('actual_tenor'),
                'collection_period': financing.get('collection_period'),
            }
```

第七步「计算汇总数据」这一行：

```python
            totals = self._calculate_totals(financing, repayments, related_statements)
```

改为（使用 Step 3 前面已定义的 `totals_source_statements`，避免同一融资单的多条历史阶段性对账单被重复加总）：

```python
            totals = self._calculate_totals(financing, repayments, totals_source_statements)
```

第八步 `overview_record` 字典，删除这两行（不再需要，改由 `refactor_fields` 提供且来源已修正）：

```python
                'bank_source': bank_statements[0]['db_finance_ref'] if bank_statements else '',
                'refactoring_status': bank_statements[0]['invoice_status'] if bank_statements else 'init',
```

并把：

```python
                # 补全用户要求的其他字段
                'settled_in_air8': '',
                'db_loan_settle_date': '',
```

改为：

```python
                # 补全用户要求的其他字段
                'settled_in_air8': financing.get('settled_in_air8', ''),
                'db_loan_settle_date': financing.get('db_loan_settle_date', ''),
```

在 `overview_record` 字典的 `'wip_pending_amount': totals.get('wip_pending_amount')` 这一行后面新增（注意补上逗号）：

```python
                'wip_pending_amount': totals.get('wip_pending_amount'),
                'financing_amount_trade_currency': financing.get('financing_amount_trade_currency'),
                'interest_amount_trade_currency': financing.get('financing_interest'),
                'funder': financing.get('insurer'),
            }
            overview_record.update(refactor_fields)
```

（把原来紧跟其后的 `}` 结尾去掉，改用 `overview_record.update(refactor_fields)` 收尾，因为 `refactor_fields` 里也包含 `refactoring_status`。）

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest backend/tests/test_aggregate_single_finance.py -v`
Expected: PASS，全部用例通过

- [ ] **Step 5: 跑全量回归**

Run: `python -m pytest backend/tests/ -q`
Expected: 全部通过

- [ ] **Step 6: 提交**

```bash
git add backend/app/services/aggregate_service.py backend/tests/test_aggregate_single_finance.py
git commit -m "fix: 单笔手动聚合去除 Loan booked 过滤，修复 settled_in_air8 恒为空及取值来源 bug"
```

---

## Task 6: 删除死代码 `_build_overview_record`

**Files:**
- Modify: `backend/app/services/aggregate_service.py`（删除 `_build_overview_record` 方法及其专属的 `_group_repayments_by_finance`/`_group_statements_by_db_ref` 辅助方法，如确认无其他调用方）
- Test: 无新增测试（本 task 是纯删除，用全量回归验证不影响任何行为）

**Interfaces:**
- Consumes: 无
- Produces: 无（纯删除，不改变任何对外行为）

- [ ] **Step 1: 确认无调用方**

Run（在 `backend` 整个目录搜索，确认三个方法只有定义、没有调用）：

```bash
grep -rn "_build_overview_record\|_group_repayments_by_finance\|_group_statements_by_db_ref" backend/ --include=*.py
```

Expected: 每个方法只出现一次（各自的 `def` 定义行），没有调用点。若 `_group_repayments_by_finance`/`_group_statements_by_db_ref` 被其他方法调用，则只删除 `_build_overview_record`，保留被调用的辅助方法。

- [ ] **Step 2: 删除**

在 `backend/app/services/aggregate_service.py` 中删除 `_build_overview_record` 方法整体（Step 1 确认的行号范围），以及经 Step 1 确认无其他调用方的 `_group_repayments_by_finance`/`_group_statements_by_db_ref`。

- [ ] **Step 3: 跑全量回归**

Run: `python -m pytest backend/tests/ -q`
Expected: 全部通过，无任何失败（证明这些代码确实未被使用）

- [ ] **Step 4: 提交**

```bash
git add backend/app/services/aggregate_service.py
git commit -m "refactor: 删除未被调用的死代码 _build_overview_record"
```

---

## Task 7: 路由层 `flatten_overview_for_display` / `build_overview_filters` 按新字段清单重写

**Files:**
- Modify: `backend/app/routes/maintenance.py:486-579`
- Test: `backend/tests/test_financing_overview_list.py`（在现有文件基础上修改 `MOCK_OVERVIEW_RECORD` 并新增用例）

**Interfaces:**
- Consumes: Task 4/5 产出的 `refactoring_financing_overview` 新字段结构
- Produces: `flatten_overview_for_display(item) -> dict`，输出 26 列对应的展平字典（含新增 `tenor_display` 复合字符串字段），供 Task 8 的模板直接渲染；`build_overview_filters(params) -> dict`，过滤参数 key 由 `bank_source` 改为 `refactor_id`。

- [ ] **Step 1: 写失败测试**

修改 `backend/tests/test_financing_overview_list.py` 顶部的 `MOCK_OVERVIEW_RECORD`，新增字段：

```python
MOCK_OVERVIEW_RECORD = {
    '_id': 'fake_id',
    'finance_request_number': 'RZ202512110000000094',
    'buyer_name': 'Test Buyer',
    'buyer_erp_id': 'B001',
    'seller_name': 'Test Seller',
    'seller_erp_id': 'S001',
    'funder': 'DB Insurance',
    'summary_status': 'Active',
    'refactoring_status': 'Loan booked',
    'refactor_portal_status': 'Financing confirmed',
    'refactor_settlement_status': 'Not settled',
    'refactor_currency': 'USD',
    'refactor_amount': Decimal128('2548.10'),
    'refactor_interest_rate_pct': Decimal128('5.1694'),
    'refactor_interest_amount': Decimal128('7.32'),
    'refactor_purchase_price': Decimal128('2540.78'),
    'refactor_id': 'GFM2638847',
    'settled_in_air8': 'Pending for Repayment',
    'loan_submission_batch': 1,
    'bank_source': 'DB',
    'financing_amount_trade_currency': Decimal128('100000.50'),
    'interest_amount_trade_currency': Decimal128('33.70'),
    'interest_rate_pct': 3.5,
    'db_loan_settle_date': datetime(2025, 6, 30),
    'updated_at': datetime(2025, 6, 1),
    'order_details': {
        'invoice_number': 'INV-2025-001',
        'currency': 'USD',
        'due_date': datetime(2025, 7, 15),
        'maturity_date': datetime(2025, 8, 15),
        'original_amount': Decimal128('2831.22'),
        'actual_tenor': 39,
        'collection_period': 5,
    },
    'totals': {
        'wip_pending_amount': Decimal128('5000.00'),
    },
    'bank_statements': [],
    'repayments': [],
}
```

在文件末尾新增测试类：

```python
class TestFlattenNewFields:
    """新字段清单展平测试"""

    def test_funder_displayed(self, logged_in_client, mock_mongo):
        mock_mongo.refactoring_financing_overview.find.return_value = _mock_chain(
            [MOCK_OVERVIEW_RECORD.copy()]
        )
        mock_mongo.refactoring_financing_overview.count_documents.return_value = 1
        mock_mongo.refactoring_financing_overview.distinct.return_value = []

        resp = logged_in_client.get(ENDPOINT)
        assert b'DB Insurance' in resp.data

    def test_invoice_amount_displayed(self, logged_in_client, mock_mongo):
        mock_mongo.refactoring_financing_overview.find.return_value = _mock_chain(
            [MOCK_OVERVIEW_RECORD.copy()]
        )
        mock_mongo.refactoring_financing_overview.count_documents.return_value = 1
        mock_mongo.refactoring_financing_overview.distinct.return_value = []

        resp = logged_in_client.get(ENDPOINT)
        assert b'2,831.22' in resp.data  # order_details.original_amount

    def test_tenor_display_combines_actual_tenor_and_collection_period(self, logged_in_client, mock_mongo):
        mock_mongo.refactoring_financing_overview.find.return_value = _mock_chain(
            [MOCK_OVERVIEW_RECORD.copy()]
        )
        mock_mongo.refactoring_financing_overview.count_documents.return_value = 1
        mock_mongo.refactoring_financing_overview.distinct.return_value = []

        resp = logged_in_client.get(ENDPOINT)
        assert b'39 + 5' in resp.data

    def test_refactor_id_displayed(self, logged_in_client, mock_mongo):
        mock_mongo.refactoring_financing_overview.find.return_value = _mock_chain(
            [MOCK_OVERVIEW_RECORD.copy()]
        )
        mock_mongo.refactoring_financing_overview.count_documents.return_value = 1
        mock_mongo.refactoring_financing_overview.distinct.return_value = []

        resp = logged_in_client.get(ENDPOINT)
        assert b'GFM2638847' in resp.data

    def test_summary_status_and_batch_not_displayed(self, logged_in_client, mock_mongo):
        mock_mongo.refactoring_financing_overview.find.return_value = _mock_chain(
            [MOCK_OVERVIEW_RECORD.copy()]
        )
        mock_mongo.refactoring_financing_overview.count_documents.return_value = 1
        mock_mongo.refactoring_financing_overview.distinct.return_value = []

        resp = logged_in_client.get(ENDPOINT)
        assert b'Active' not in resp.data  # summary_status 的值不应出现

    def test_filter_by_refactor_id(self, logged_in_client, mock_mongo):
        mock_mongo.refactoring_financing_overview.find.return_value = _mock_chain([])
        mock_mongo.refactoring_financing_overview.count_documents.return_value = 0
        mock_mongo.refactoring_financing_overview.distinct.return_value = []

        logged_in_client.get(f'{ENDPOINT}?refactor_id=GFM2638847')

        call_args = mock_mongo.refactoring_financing_overview.find.call_args
        filters = call_args[0][0]
        assert filters['refactor_id'] == 'GFM2638847'
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest backend/tests/test_financing_overview_list.py -v`
Expected: 新增用例 FAIL（`flatten_overview_for_display` 还不认识 `funder`/`refactor_id`/`tenor_display` 等字段，模板还没有对应的列；`build_overview_filters` 还不接受 `refactor_id` 参数）

- [ ] **Step 3: 实现**

在 `backend/app/routes/maintenance.py` 中，把 `flatten_overview_for_display` 函数整体替换为：

```python
def _to_display_number(val):
    return float(val.to_decimal()) if hasattr(val, 'to_decimal') else val


def _format_tenor(actual_tenor, collection_period):
    parts = []
    if actual_tenor not in (None, ''):
        parts.append(str(actual_tenor))
    if collection_period not in (None, ''):
        parts.append(str(collection_period))
    return ' + '.join(parts)


def flatten_overview_for_display(item):
    """将 overview 记录扁平化用于表格展示（26 列新字段清单）"""
    row = {}

    text_fields = (
        'finance_request_number', 'buyer_name', 'seller_name', 'funder',
        'refactoring_status', 'refactor_id', 'refactor_portal_status',
        'refactor_settlement_status', 'refactor_currency', 'settled_in_air8',
        'db_loan_settle_date', 'updated_at',
    )
    for key in text_fields:
        row[key] = item.get(key)

    numeric_fields = (
        'financing_amount_trade_currency', 'interest_amount_trade_currency',
        'refactor_amount', 'refactor_interest_rate_pct',
        'refactor_interest_amount', 'refactor_purchase_price',
        'interest_rate_pct',
    )
    for key in numeric_fields:
        row[key] = _to_display_number(item.get(key))

    od = item.get('order_details') or {}
    row['invoice_number'] = od.get('invoice_number')
    row['currency'] = od.get('currency')
    row['due_date'] = od.get('due_date')
    row['maturity_date'] = od.get('maturity_date')
    row['original_amount'] = _to_display_number(od.get('original_amount'))
    row['tenor_display'] = _format_tenor(od.get('actual_tenor'), od.get('collection_period'))

    return row
```

（删除原来的 `famt = item.get('financing_amount_trade_currency')` 那两行，功能已被 `numeric_fields` 循环覆盖。）

`build_overview_filters` 函数中，把：

```python
    bank_source = params.get('bank_source', '').strip()
    if bank_source:
        filters['bank_source'] = bank_source
```

改为：

```python
    refactor_id = params.get('refactor_id', '').strip()
    if refactor_id:
        filters['refactor_id'] = refactor_id
```

`financing_overview_list` 路由函数中，把：

```python
    bank_source_options = mongo.refactoring_financing_overview.distinct('bank_source')
```

改为：

```python
    bank_source_options = mongo.refactoring_financing_overview.distinct('refactor_id')
```

（变量名 `bank_source_options` 暂保持不变，避免连带修改模板变量名；模板改动统一放在 Task 8。）

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest backend/tests/test_financing_overview_list.py -v`
Expected: 大部分 PASS；`test_tenor_display_...`/`test_refactor_id_displayed` 等依赖模板渲染的用例此时仍可能 FAIL（模板还未按新列渲染），这属于预期——留给 Task 8 完成后一起转绿。若本 task 想独立转绿，可临时只跑不依赖模板具体 HTML 内容的用例：

Run: `python -m pytest backend/tests/test_financing_overview_list.py::TestFinancingOverviewList::test_filter_by_refactor_id -v`（此用例在 `test_filter_by_refactor_id` 命名下需要先重命名，见下方 Step 4b）

- [ ] **Step 4b: 更新过滤字段改名相关的既有用例**

`backend/tests/test_financing_overview_list.py` 中原有的 `test_filter_by_finance_request_number` 等用例不受影响；但没有名为 `bank_source` 过滤的既有用例（原文件未覆盖），无需额外改动。

- [ ] **Step 5: 跑全量回归**

Run: `python -m pytest backend/tests/ -q`
Expected: 除「依赖模板新列渲染」的用例外全部通过（该部分在 Task 8 完成后统一转绿，Task 8 的 Step 4 会重新跑一次本文件确认）

- [ ] **Step 6: 提交**

```bash
git add backend/app/routes/maintenance.py backend/tests/test_financing_overview_list.py
git commit -m "feat: flatten_overview_for_display/build_overview_filters 适配新字段清单与 refactor_id 改名"
```

---

## Task 8: 模板 26 列重排 + 筛选表单改名 + i18n 命名/列头文案

**Files:**
- Modify: `backend/app/templates/maintenance/financing_overview_list.html`
- Modify: `backend/app/i18n/zh-CN.json`
- Modify: `backend/app/i18n/en-US.json`

**Interfaces:**
- Consumes: Task 7 产出的 `flatten_overview_for_display` 字段清单（`row.funder`、`row.tenor_display`、`row.refactor_id` 等）
- Produces: 页面最终视觉输出；供 Task 9 做端到端回归验证。

- [ ] **Step 1: 修改 i18n — 菜单与标题命名（需求1）**

`backend/app/i18n/en-US.json`，把：

```json
      "financing_overview_list": "Financing Overview List",
```

改为：

```json
      "financing_overview_list": "Refactoring Financing List",
```

同文件里 `"overview_list": { "title": "Financing Overview List", ...` 的 `title` 值改为 `"Refactoring Financing List"`。

`backend/app/i18n/zh-CN.json` 中 `nav.financing_overview_list` 与 `overview_list.title` 已经是"再保理融资单列表"，无需改动，仅确认无误。

- [ ] **Step 2: 修改 i18n — 列头与筛选文案（需求2）**

`backend/app/i18n/zh-CN.json` 的 `overview_list` 块，把 `filter.bank_source` 和 `column` 整体替换为：

```json
    "filter": {
      "finance_request_number": "融资申请号",
      "invoice_number": "发票号",
      "refactoring_status": "再保理状态",
      "buyer_name": "买方名称",
      "seller_name": "卖方名称",
      "settled_in_air8": "Air8结算状态",
      "refactor_id": "银行再保理编号",
      "all": "全部"
    },
    "button": {
      "search": "搜索",
      "reset": "重置",
      "export_excel": "导出Excel"
    },
    "column": {
      "funder": "资金方",
      "fr_number": "融资申请号",
      "buyer_name": "买方",
      "seller_name": "卖方",
      "invoice_number": "发票号",
      "currency": "币种",
      "invoice_amount": "发票金额",
      "interest_rate": "利率%",
      "tenor": "帐期（含收款期）",
      "financing_amount": "融资金额",
      "interest_amount": "利息",
      "due_date": "发票到期日",
      "air8_settlement_status": "Air8结算状态",
      "refactor_currency": "再保理货币",
      "refactor_amount": "再报理金额",
      "refactor_interest_rate": "再保理利率",
      "refactor_interest_amount": "再保理利息",
      "refactor_overdue_interest": "再保理利息（逾期）",
      "refactor_net_amount": "净再保理金额",
      "refactor_portal_status": "再保理平台状态",
      "refactoring_status": "再保理状态",
      "refactor_settlement_status": "再保理结算状态",
      "refactor_id": "银行再保理编号",
      "maturity_date": "再保理成熟日",
      "db_settle_date": "DB还款日",
      "updated_at": "系统更新时间"
    },
```

`backend/app/i18n/en-US.json` 对应块替换为：

```json
    "filter": {
      "finance_request_number": "Finance Request Number",
      "invoice_number": "Invoice Number",
      "refactoring_status": "Refactoring Status",
      "buyer_name": "Buyer Name",
      "seller_name": "Seller Name",
      "settled_in_air8": "Air8 Settlement Status",
      "refactor_id": "Refactor ID",
      "all": "All"
    },
    "button": {
      "search": "Search",
      "reset": "Reset",
      "export_excel": "Export Excel"
    },
    "column": {
      "funder": "Funder",
      "fr_number": "FR#",
      "buyer_name": "Buyer",
      "seller_name": "Seller",
      "invoice_number": "Invoice#",
      "currency": "Currency",
      "invoice_amount": "Invoice Amount",
      "interest_rate": "Interest Rate%",
      "tenor": "Actual Tenor (Collection Period Involved)",
      "financing_amount": "Financing Amount (Trade Currency)",
      "interest_amount": "Interest Amount",
      "due_date": "Invoice Due Date",
      "air8_settlement_status": "Air8 Settlement Status",
      "refactor_currency": "Refactor Currency",
      "refactor_amount": "Refactor Amount (Discount Amount)",
      "refactor_interest_rate": "Refactor Interest Rate",
      "refactor_interest_amount": "Refactor Interest Amount",
      "refactor_overdue_interest": "Refactor Interest Amount (Overdue)",
      "refactor_net_amount": "Net Refactor Amount (Purchase Price)",
      "refactor_portal_status": "Refactor Portal Status",
      "refactoring_status": "Refactor Status",
      "refactor_settlement_status": "Refactor Settlement Status",
      "refactor_id": "Refactor ID",
      "maturity_date": "Refactor Due Date",
      "db_settle_date": "DB Settle Date",
      "updated_at": "System Update Time"
    },
```

- [ ] **Step 3: 重写模板**

将 `backend/app/templates/maintenance/financing_overview_list.html` 整个文件替换为：

```html
{% extends "base.html" %}

{% block title %}{{ _('overview_list.title') }} - {{ config.APP_NAME }}{% endblock %}

{% block content %}
<div class="page-header">
    <h1 class="page-title">{{ _('overview_list.title') }}</h1>
</div>

<!-- 筛选条件卡片 -->
<div class="card mb-4">
    <div class="card-header">
        <h5 class="card-title"><i class="fa fa-filter"></i> {{ _('overview_list.button.search') }}</h5>
    </div>
    <div class="card-body">
        <form id="filter-form" method="GET" action="{{ url_for('maintenance.financing_overview_list') }}">
            <div class="form-row">
                <div class="form-col">
                    <label for="finance_request_number" class="form-label">{{ _('overview_list.filter.finance_request_number') }}</label>
                    <input type="text" class="form-control" id="finance_request_number" name="finance_request_number"
                           value="{{ filters.get('finance_request_number', '') }}" placeholder="{{ _('overview_list.filter.finance_request_number') }}">
                </div>
                <div class="form-col">
                    <label for="invoice_number" class="form-label">{{ _('overview_list.filter.invoice_number') }}</label>
                    <input type="text" class="form-control" id="invoice_number" name="invoice_number"
                           value="{{ filters.get('invoice_number', '') }}" placeholder="{{ _('overview_list.filter.invoice_number') }}">
                </div>
                <div class="form-col">
                    <label for="refactoring_status" class="form-label">{{ _('overview_list.filter.refactoring_status') }}</label>
                    <select class="form-select" id="refactoring_status" name="refactoring_status">
                        <option value="">{{ _('overview_list.filter.all') }}</option>
                        {% for opt in status_options %}
                            <option value="{{ opt }}" {% if filters.get('refactoring_status') == opt %}selected{% endif %}>{{ opt }}</option>
                        {% endfor %}
                    </select>
                </div>
            </div>
            <div class="form-row">
                <div class="form-col">
                    <label for="buyer_name" class="form-label">{{ _('overview_list.filter.buyer_name') }}</label>
                    <input type="text" class="form-control" id="buyer_name" name="buyer_name"
                           value="{{ filters.get('buyer_name', '') }}" placeholder="{{ _('overview_list.filter.buyer_name') }}">
                </div>
                <div class="form-col">
                    <label for="seller_name" class="form-label">{{ _('overview_list.filter.seller_name') }}</label>
                    <input type="text" class="form-control" id="seller_name" name="seller_name"
                           value="{{ filters.get('seller_name', '') }}" placeholder="{{ _('overview_list.filter.seller_name') }}">
                </div>
                <div class="form-col">
                    <label for="settled_in_air8" class="form-label">{{ _('overview_list.filter.settled_in_air8') }}</label>
                    <select class="form-select" id="settled_in_air8" name="settled_in_air8">
                        <option value="">{{ _('overview_list.filter.all') }}</option>
                        {% for opt in settled_options %}
                            <option value="{{ opt }}" {% if filters.get('settled_in_air8') == opt %}selected{% endif %}>{{ opt }}</option>
                        {% endfor %}
                    </select>
                </div>
                <div class="form-col">
                    <label for="refactor_id" class="form-label">{{ _('overview_list.filter.refactor_id') }}</label>
                    <select class="form-select" id="refactor_id" name="refactor_id">
                        <option value="">{{ _('overview_list.filter.all') }}</option>
                        {% for opt in bank_source_options %}
                            <option value="{{ opt }}" {% if filters.get('refactor_id') == opt %}selected{% endif %}>{{ opt }}</option>
                        {% endfor %}
                    </select>
                </div>
            </div>
            <div class="card-footer">
                <button type="submit" class="btn btn-primary">
                    <i class="fa fa-search"></i> {{ _('overview_list.button.search') }}
                </button>
                <a href="{{ url_for('maintenance.financing_overview_list') }}" class="btn btn-secondary">
                    <i class="fa fa-undo"></i> {{ _('overview_list.button.reset') }}
                </a>
                <button type="button" id="export-btn" class="btn btn-success">
                    <i class="fa fa-download"></i> {{ _('overview_list.button.export_excel') }}
                </button>
            </div>
        </form>
        <!-- 隐藏的导出表单 -->
        <form id="export-form" method="POST" action="{{ url_for('maintenance.financing_overview_export') }}" style="display:none;">
            <input type="hidden" name="finance_request_number" value="{{ filters.get('finance_request_number', '') }}">
            <input type="hidden" name="invoice_number" value="{{ filters.get('invoice_number', '') }}">
            <input type="hidden" name="refactoring_status" value="{{ filters.get('refactoring_status', '') }}">
            <input type="hidden" name="buyer_name" value="{{ filters.get('buyer_name', '') }}">
            <input type="hidden" name="seller_name" value="{{ filters.get('seller_name', '') }}">
            <input type="hidden" name="settled_in_air8" value="{{ filters.get('settled_in_air8', '') }}">
            <input type="hidden" name="refactor_id" value="{{ filters.get('refactor_id', '') }}">
        </form>
    </div>
</div>

<!-- 数据表格 -->
<div class="card">
    <div class="card-body">
        {% if data %}
        <div class="table-responsive">
            <table class="table table-striped table-hover">
                <thead>
                    <tr>
                        <th>{{ _('overview_list.column.funder') }}</th>
                        <th>{{ _('overview_list.column.fr_number') }}</th>
                        <th>{{ _('overview_list.column.buyer_name') }}</th>
                        <th>{{ _('overview_list.column.seller_name') }}</th>
                        <th>{{ _('overview_list.column.invoice_number') }}</th>
                        <th>{{ _('overview_list.column.currency') }}</th>
                        <th>{{ _('overview_list.column.invoice_amount') }}</th>
                        <th>{{ _('overview_list.column.interest_rate') }}</th>
                        <th>{{ _('overview_list.column.tenor') }}</th>
                        <th>{{ _('overview_list.column.financing_amount') }}</th>
                        <th>{{ _('overview_list.column.interest_amount') }}</th>
                        <th>{{ _('overview_list.column.due_date') }}</th>
                        <th>{{ _('overview_list.column.air8_settlement_status') }}</th>
                        <th>{{ _('overview_list.column.refactor_currency') }}</th>
                        <th>{{ _('overview_list.column.refactor_amount') }}</th>
                        <th>{{ _('overview_list.column.refactor_interest_rate') }}</th>
                        <th>{{ _('overview_list.column.refactor_interest_amount') }}</th>
                        <th>{{ _('overview_list.column.refactor_overdue_interest') }}</th>
                        <th>{{ _('overview_list.column.refactor_net_amount') }}</th>
                        <th>{{ _('overview_list.column.refactor_portal_status') }}</th>
                        <th>{{ _('overview_list.column.refactoring_status') }}</th>
                        <th>{{ _('overview_list.column.refactor_settlement_status') }}</th>
                        <th>{{ _('overview_list.column.refactor_id') }}</th>
                        <th>{{ _('overview_list.column.maturity_date') }}</th>
                        <th>{{ _('overview_list.column.db_settle_date') }}</th>
                        <th>{{ _('overview_list.column.updated_at') }}</th>
                    </tr>
                </thead>
                <tbody>
                    {% for row in data %}
                    <tr>
                        <td>{{ row.funder or '' }}</td>
                        <td>{{ row.finance_request_number or '' }}</td>
                        <td>{{ row.buyer_name or '' }}</td>
                        <td>{{ row.seller_name or '' }}</td>
                        <td>{{ row.invoice_number or '' }}</td>
                        <td>{{ row.currency or '' }}</td>
                        <td>{{ '{:,.2f}'.format(row.original_amount) if row.original_amount is not none else '' }}</td>
                        <td>{{ row.interest_rate_pct if row.interest_rate_pct is not none else '' }}</td>
                        <td>{{ row.tenor_display or '' }}</td>
                        <td>{{ '{:,.2f}'.format(row.financing_amount_trade_currency) if row.financing_amount_trade_currency is not none else '' }}</td>
                        <td>{{ '{:,.2f}'.format(row.interest_amount_trade_currency) if row.interest_amount_trade_currency is not none else '' }}</td>
                        <td>{{ row.due_date.strftime('%Y-%m-%d') if row.due_date else '' }}</td>
                        <td>{{ row.settled_in_air8 or '' }}</td>
                        <td>{{ row.refactor_currency or '' }}</td>
                        <td>{{ '{:,.2f}'.format(row.refactor_amount) if row.refactor_amount is not none else '' }}</td>
                        <td>{{ row.refactor_interest_rate_pct if row.refactor_interest_rate_pct is not none else '' }}</td>
                        <td>{{ '{:,.2f}'.format(row.refactor_interest_amount) if row.refactor_interest_amount is not none else '' }}</td>
                        <td></td>
                        <td>{{ '{:,.2f}'.format(row.refactor_purchase_price) if row.refactor_purchase_price is not none else '' }}</td>
                        <td>{{ row.refactor_portal_status or '' }}</td>
                        <td>{{ row.refactoring_status or '' }}</td>
                        <td>{{ row.refactor_settlement_status or '' }}</td>
                        <td>{{ row.refactor_id or '' }}</td>
                        <td>{{ row.maturity_date.strftime('%Y-%m-%d') if row.maturity_date else '' }}</td>
                        <td>{{ row.db_loan_settle_date.strftime('%Y-%m-%d') if row.db_loan_settle_date else '' }}</td>
                        <td>{{ row.updated_at.strftime('%Y-%m-%d %H:%M') if row.updated_at else '' }}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>

        <!-- 分页控件 -->
        {% if total_pages > 1 %}
        <nav aria-label="Page navigation">
            <ul class="pagination justify-content-center">
                <li class="page-item {% if page == 1 %}disabled{% endif %}">
                    <a class="page-link" href="{{ url_for('maintenance.financing_overview_list', page=page-1, **filters) }}">
                        {{ _('common.table.previous_page') }}
                    </a>
                </li>
                {% for p in range(1, total_pages + 1) %}
                <li class="page-item {% if p == page %}active{% endif %}">
                    <a class="page-link" href="{{ url_for('maintenance.financing_overview_list', page=p, **filters) }}">{{ p }}</a>
                </li>
                {% endfor %}
                <li class="page-item {% if page == total_pages %}disabled{% endif %}">
                    <a class="page-link" href="{{ url_for('maintenance.financing_overview_list', page=page+1, **filters) }}">
                        {{ _('common.table.next_page') }}
                    </a>
                </li>
            </ul>
        </nav>
        {% endif %}

        <!-- 数据统计 -->
        <div class="text-center mt-3">
            <p class="text-muted">
                {{ _('overview_list.showing') }} {{ (page-1)*per_page + 1 }} {{ _('overview_list.to') }} {{ end_record }} {{ _('overview_list.of') }} {{ total }} {{ _('overview_list.records') }}
            </p>
        </div>

        {% else %}
        <div class="empty-state">
            <i class="fa fa-inbox"></i>
            <p>{{ _('overview_list.no_data') }}</p>
        </div>
        {% endif %}
    </div>
</div>

{% block extra_js %}
<script>
    document.getElementById('export-btn').addEventListener('click', function() {
        // 将当前筛选条件同步到导出表单
        var filterForm = document.getElementById('filter-form');
        var exportForm = document.getElementById('export-form');
        var fields = ['finance_request_number', 'invoice_number', 'refactoring_status',
                      'buyer_name', 'seller_name', 'settled_in_air8', 'refactor_id'];
        fields.forEach(function(name) {
            var src = filterForm.querySelector('[name="' + name + '"]');
            var dst = exportForm.querySelector('[name="' + name + '"]');
            if (src && dst) dst.value = src.value;
        });
        exportForm.submit();
    });
</script>
{% endblock %}
{% endblock %}
```

（第 18 列"再保理利息（逾期）"按 spec 边界约定固定留空 `<td></td>`，不绑定任何字段。）

- [ ] **Step 4: 跑测试确认全部通过**

Run: `python -m pytest backend/tests/test_financing_overview_list.py -v`
Expected: 全部 PASS，包括 Task 7 中标记为「留给本 task 转绿」的用例

- [ ] **Step 5: 跑全量回归**

Run: `python -m pytest backend/tests/ -q`
Expected: 全部通过

- [ ] **Step 6: 用真实开发服务器过一遍页面（手工冒烟）**

Run: `python run_flask.py`，浏览器打开 `http://localhost:5000/maintenance/financing-overview`，检查：
- 中英文切换下菜单文案分别为"再保理融资单列表" / "Refactoring Financing List"
- 表格表头按 26 列新顺序展示，"汇总状态"/"批次号"列不再出现
- 筛选区"银行再保理编号"下拉可正常搜索

Expected: 页面正常加载，无 Jinja2 报错，无 JS 控制台报错

- [ ] **Step 7: 提交**

```bash
git add backend/app/templates/maintenance/financing_overview_list.html backend/app/i18n/zh-CN.json backend/app/i18n/en-US.json
git commit -m "feat: 融资单列表页面 26 列重排、筛选字段改名、菜单/标题中英文命名调整"
```

---

## Task 9: 端到端回归 + 需求基线同步

**Files:**
- Modify: `docs/system/requirements.md`（按 spec-workflow.md 规则，将本 spec 的需求章节内容合并进基线）

**Interfaces:**
- Consumes: 全部前序 task 的产出
- Produces: 无代码产出，收尾验证与文档同步

- [ ] **Step 1: 跑全量测试套件**

Run: `python -m pytest backend/tests/ -q`
Expected: 全部通过，通过数量不少于重构前的 202（加上本计划新增的测试用例）

- [ ] **Step 2: 手动触发一次全量聚合，检查记录数变化**

若本地/测试环境有可用的 MongoDB 数据，可通过 `python scripts/run_aggregate.py` 手动跑一次聚合，对比聚合前后 `refactoring_financing_overview` 的记录数——去除 `Loan booked` 过滤后记录数应等于或多于之前（覆盖了更多在途阶段的融资单）。若本地无可用数据库，跳过本 step，仅在测试环境验证。

- [ ] **Step 3: 更新需求基线文档**

打开 `docs/system/requirements.md`，找到"融资概览 (Financing Overview)"相关章节（术语表第 23 行附近），将本次 spec 第一部分的 4 条需求（菜单命名、字段重构、聚合逻辑修正、上游同步字段）合并进对应模块的 `REQ-<模块缩写>-NNN` 条目；在文档末尾"变更记录"表新增一行，注明日期 2026-08-20、变更内容摘要、关联 spec 路径。

- [ ] **Step 4: 提交**

```bash
git add docs/system/requirements.md
git commit -m "docs: 再保理融资单列表重构需求合并进基线文档"
```

- [ ] **Step 5: 更新 spec 文档状态**

将 `docs/superpowers/specs/2026-08-20-refactoring-financing-list-design.md` 头部的"状态：草稿"改为"状态：已完成"，提交：

```bash
git add docs/superpowers/specs/2026-08-20-refactoring-financing-list-design.md
git commit -m "docs: 标记再保理融资单列表重构 spec 为已完成"
```
