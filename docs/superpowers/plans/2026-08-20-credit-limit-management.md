# 额度管理（买方/买卖方维度）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有额度查询模块基础上，实现按买方汇总 + 供应商钻取的额度管理视图（Celling/预占/实占/总额/Headroom），支持导出和每日超额邮件预警。

**Architecture:** 新增一个纯函数聚合服务 `credit_limit_service.py`（无持久化，实时读 `refactoring_onboard_config` + `refactoring_financing_order` + `refactoring_bank_statement`），供页面路由、导出服务、预警服务三处复用；导出与预警各自拆分为独立服务文件，路由层只做编排。

**Tech Stack:** Flask, PyMongo（MagicMock 模拟测试）, openpyxl, APScheduler, pytest, unittest.mock

**Spec:** `docs/superpowers/specs/2026-08-20-credit-limit-management-design.md`

## Global Constraints

- 所有额度指标本期统一按 USD 展示，不做汇率换算。
- 额度计算全部实时聚合，不新增持久化集合。
- 预警阈值默认 90%（`0.9`），硬编码于 `backend/app/config.py`，本期不做 UI 配置。
- 外部 n8n 邮件接口调用必须设置超时并捕获异常；测试中必须 mock，不发起真实网络请求。
- `/credit/detail`（FR 明细钻取）逻辑与字段本次不修改。
- 每个 task 提交前运行 `pytest backend/tests/` 确保全部通过。

---

## Task 1: 额度聚合服务 — 买卖方配对层（`credit_limit_service.get_buyer_supplier_pairs`）

**Files:**
- Create: `backend/app/services/credit_limit_service.py`
- Test: `backend/tests/test_credit_limit_service.py`

**Interfaces:**
- Produces: `_to_float(val) -> float | None`；`get_buyer_supplier_pairs(mongo, buyer_filter: str | None = None) -> list[dict]`，每个 dict 含键：`uid, buyer_code, buyer_name, supplier_code, supplier_name, currency, celling, reserved, actual, total_occupied, headroom, occupancy_rate`（`headroom`/`occupancy_rate` 在 `celling<=0` 时为 `None`）。

- [ ] **Step 1: 写失败测试 — 预占/实占/总额计算与全外连接**

```python
"""额度管理聚合服务测试"""
from unittest.mock import MagicMock
import pytest


def _make_mongo(onboard_configs=None, financing_orders=None, bank_statements=None):
    mongo = MagicMock()
    mongo.refactoring_onboard_config.find.return_value = onboard_configs or []
    mongo.refactoring_financing_order.find.return_value = financing_orders or []
    mongo.refactoring_bank_statement.find.return_value = bank_statements or []
    return mongo


class TestGetBuyerSupplierPairs:

    def test_reserved_bucket_sums_financing_amount_when_not_db_confirmed(self):
        from backend.app.services.credit_limit_service import get_buyer_supplier_pairs
        mongo = _make_mongo(
            onboard_configs=[{'uid': 'U1', 'refactoring_limit': 100000, 'buyer_code': 'B1',
                               'obligor_name': 'Buyer One', 'supplier_code': 'S1', 'seller_name': 'Seller One'}],
            financing_orders=[
                {'uid': 'U1', 'buyer_code': 'B1', 'supplier_code': 'S1', 'buyer_name': 'Buyer One',
                 'supplier_name': 'Seller One', 'financing_amount': 1000, 'funded_before': True,
                 'bank_finance_status': 'Booking requested accepted', 'invoice_number': 'INV1'},
            ],
        )
        pairs = get_buyer_supplier_pairs(mongo)
        assert len(pairs) == 1
        p = pairs[0]
        assert p['uid'] == 'U1'
        assert p['reserved'] == 1000
        assert p['actual'] == 0
        assert p['total_occupied'] == 1000
        assert p['celling'] == 100000
        assert p['headroom'] == 99000
        assert abs(p['occupancy_rate'] - 0.01) < 1e-9

    def test_actual_bucket_sums_bank_statement_outstanding_amount(self):
        from backend.app.services.credit_limit_service import get_buyer_supplier_pairs
        mongo = _make_mongo(
            onboard_configs=[{'uid': 'U1', 'refactoring_limit': 100000, 'buyer_code': 'B1',
                               'obligor_name': 'Buyer One', 'supplier_code': 'S1', 'seller_name': 'Seller One'}],
            financing_orders=[
                {'uid': 'U1', 'buyer_code': 'B1', 'supplier_code': 'S1', 'buyer_name': 'Buyer One',
                 'supplier_name': 'Seller One', 'financing_amount': 1000, 'funded_before': True,
                 'bank_finance_status': 'Loan booked', 'invoice_number': 'INV1'},
            ],
            bank_statements=[
                {'invoice': {'seller_reference': 'INV1'}, 'finance': {'outstanding_amount': 500}},
            ],
        )
        pairs = get_buyer_supplier_pairs(mongo)
        p = pairs[0]
        assert p['reserved'] == 0
        assert p['actual'] == 500
        assert p['total_occupied'] == 500

    def test_reserved_and_actual_combine_across_multiple_orders(self):
        from backend.app.services.credit_limit_service import get_buyer_supplier_pairs
        mongo = _make_mongo(
            onboard_configs=[{'uid': 'U1', 'refactoring_limit': 100000, 'buyer_code': 'B1',
                               'obligor_name': 'Buyer One', 'supplier_code': 'S1', 'seller_name': 'Seller One'}],
            financing_orders=[
                {'uid': 'U1', 'buyer_code': 'B1', 'supplier_code': 'S1', 'buyer_name': 'Buyer One',
                 'supplier_name': 'Seller One', 'financing_amount': 1000, 'funded_before': True,
                 'bank_finance_status': 'Booking requested accepted', 'invoice_number': 'INV1'},
                {'uid': 'U1', 'buyer_code': 'B1', 'supplier_code': 'S1', 'buyer_name': 'Buyer One',
                 'supplier_name': 'Seller One', 'financing_amount': 2000, 'funded_before': True,
                 'bank_finance_status': 'Loan booked', 'invoice_number': 'INV2'},
            ],
            bank_statements=[
                {'invoice': {'seller_reference': 'INV2'}, 'finance': {'outstanding_amount': 1800}},
            ],
        )
        pairs = get_buyer_supplier_pairs(mongo)
        p = pairs[0]
        assert p['reserved'] == 1000
        assert p['actual'] == 1800
        assert p['total_occupied'] == 2800

    def test_onboard_only_uid_has_zero_occupied_and_full_headroom(self):
        from backend.app.services.credit_limit_service import get_buyer_supplier_pairs
        mongo = _make_mongo(
            onboard_configs=[{'uid': 'U2', 'refactoring_limit': 200000, 'buyer_code': 'B2',
                               'obligor_name': 'Buyer Two', 'supplier_code': 'S2', 'seller_name': 'Seller Two'}],
        )
        pairs = get_buyer_supplier_pairs(mongo)
        assert len(pairs) == 1
        p = pairs[0]
        assert p['celling'] == 200000
        assert p['reserved'] == 0
        assert p['actual'] == 0
        assert p['headroom'] == 200000
        assert p['occupancy_rate'] == 0.0

    def test_financing_only_uid_has_none_headroom_and_occupancy(self):
        from backend.app.services.credit_limit_service import get_buyer_supplier_pairs
        mongo = _make_mongo(
            financing_orders=[
                {'uid': 'U3', 'buyer_code': 'B3', 'supplier_code': 'S3', 'buyer_name': 'Buyer Three',
                 'supplier_name': 'Seller Three', 'financing_amount': 500, 'funded_before': True,
                 'bank_finance_status': 'Booking requested accepted', 'invoice_number': 'INV3'},
            ],
        )
        pairs = get_buyer_supplier_pairs(mongo)
        p = pairs[0]
        assert p['celling'] == 0
        assert p['reserved'] == 500
        assert p['headroom'] is None
        assert p['occupancy_rate'] is None

    def test_buyer_filter_matches_case_insensitively(self):
        from backend.app.services.credit_limit_service import get_buyer_supplier_pairs
        mongo = _make_mongo(
            onboard_configs=[
                {'uid': 'U1', 'refactoring_limit': 1000, 'buyer_code': 'B1', 'obligor_name': 'Amazon Services'},
                {'uid': 'U2', 'refactoring_limit': 2000, 'buyer_code': 'B2', 'obligor_name': 'Homegoods Inc'},
            ],
        )
        pairs = get_buyer_supplier_pairs(mongo, buyer_filter='amazon')
        assert len(pairs) == 1
        assert pairs[0]['buyer_name'] == 'Amazon Services'

    def test_target_list_status_n_pair_is_included(self):
        from backend.app.services.credit_limit_service import get_buyer_supplier_pairs
        mongo = _make_mongo(
            onboard_configs=[{'uid': 'U1', 'refactoring_limit': 0, 'buyer_code': 'B1',
                               'obligor_name': 'Buyer One', 'target_list_status': 'N'}],
        )
        pairs = get_buyer_supplier_pairs(mongo)
        assert len(pairs) == 1
        assert pairs[0]['uid'] == 'U1'

    def test_currency_is_always_usd(self):
        from backend.app.services.credit_limit_service import get_buyer_supplier_pairs
        mongo = _make_mongo(onboard_configs=[{'uid': 'U1', 'refactoring_limit': 1000, 'buyer_code': 'B1'}])
        pairs = get_buyer_supplier_pairs(mongo)
        assert pairs[0]['currency'] == 'USD'
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest backend/tests/test_credit_limit_service.py -v`
Expected: FAIL，报 `ModuleNotFoundError: No module named 'backend.app.services.credit_limit_service'`

- [ ] **Step 3: 实现 `credit_limit_service.py`**

```python
"""额度管理 — 实时聚合服务（不落库）"""
from bson import Decimal128


def _to_float(val):
    if val is None or val == '':
        return None
    if isinstance(val, Decimal128):
        return float(val.to_decimal())
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def get_buyer_supplier_pairs(mongo, buyer_filter=None):
    """按买卖方配对(uid)实时聚合额度上限、预占、实占。

    Celling: refactoring_onboard_config.refactoring_limit（按 uid）
    预占: funded_before=True 且 bank_finance_status != 'Loan booked' 的融资单 financing_amount 之和
    实占: bank_finance_status == 'Loan booked' 的融资单关联 bank_statement.finance.outstanding_amount 之和
    """
    onboard_configs = list(mongo.refactoring_onboard_config.find())
    onboard_by_uid = {c.get('uid'): c for c in onboard_configs if c.get('uid')}

    financing_orders = list(mongo.refactoring_financing_order.find())

    loan_booked_invoices = [
        fo.get('invoice_number') for fo in financing_orders
        if fo.get('bank_finance_status') == 'Loan booked' and fo.get('invoice_number')
    ]
    bank_statements = []
    if loan_booked_invoices:
        bank_statements = list(mongo.refactoring_bank_statement.find(
            {'invoice.seller_reference': {'$in': loan_booked_invoices}}
        ))
    outstanding_by_invoice = {}
    for bs in bank_statements:
        ref = (bs.get('invoice') or {}).get('seller_reference')
        if ref:
            outstanding_by_invoice[ref] = _to_float((bs.get('finance') or {}).get('outstanding_amount')) or 0.0

    reserved = {}
    actual = {}
    fo_buyer_name = {}
    fo_supplier_name = {}
    fo_buyer_code = {}
    fo_supplier_code = {}

    for fo in financing_orders:
        uid = fo.get('uid')
        if not uid:
            continue
        fo_buyer_name.setdefault(uid, fo.get('buyer_name') or '')
        fo_supplier_name.setdefault(uid, fo.get('supplier_name') or '')
        fo_buyer_code.setdefault(uid, fo.get('buyer_code') or '')
        fo_supplier_code.setdefault(uid, fo.get('supplier_code') or '')

        bank_finance_status = fo.get('bank_finance_status')
        if fo.get('funded_before') and bank_finance_status != 'Loan booked':
            amount = _to_float(fo.get('financing_amount')) or 0.0
            reserved[uid] = reserved.get(uid, 0.0) + amount
        if bank_finance_status == 'Loan booked':
            amount = outstanding_by_invoice.get(fo.get('invoice_number'), 0.0)
            actual[uid] = actual.get(uid, 0.0) + amount

    all_uids = set(onboard_by_uid.keys()) | set(fo_buyer_name.keys())

    pairs = []
    for uid in all_uids:
        onboard = onboard_by_uid.get(uid, {})
        celling = _to_float(onboard.get('refactoring_limit')) or 0.0
        r = round(reserved.get(uid, 0.0), 2)
        a = round(actual.get(uid, 0.0), 2)
        total = round(r + a, 2)

        if celling > 0:
            headroom = round(celling - total, 2)
            occupancy_rate = round(total / celling, 4)
        else:
            headroom = None
            occupancy_rate = None

        pairs.append({
            'uid': uid,
            'buyer_code': onboard.get('buyer_code') or fo_buyer_code.get(uid, ''),
            'buyer_name': onboard.get('obligor_name') or fo_buyer_name.get(uid, ''),
            'supplier_code': onboard.get('supplier_code') or fo_supplier_code.get(uid, ''),
            'supplier_name': onboard.get('seller_name') or fo_supplier_name.get(uid, ''),
            'currency': 'USD',
            'celling': celling,
            'reserved': r,
            'actual': a,
            'total_occupied': total,
            'headroom': headroom,
            'occupancy_rate': occupancy_rate,
        })

    if buyer_filter:
        needle = buyer_filter.strip().lower()
        pairs = [p for p in pairs if needle in (p['buyer_name'] or '').lower()]

    pairs.sort(key=lambda p: (p['occupancy_rate'] is None, -(p['occupancy_rate'] or 0)))
    return pairs
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest backend/tests/test_credit_limit_service.py -v`
Expected: PASS（8 项全部通过）

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/credit_limit_service.py backend/tests/test_credit_limit_service.py
git commit -m "feat: 新增额度管理买卖方配对层聚合服务（预占/实占/Celling/Headroom）"
```

---

## Task 2: 额度聚合服务 — 买方层汇总（`credit_limit_service.aggregate_by_buyer`）

**Files:**
- Modify: `backend/app/services/credit_limit_service.py`
- Test: `backend/tests/test_credit_limit_service.py`

**Interfaces:**
- Consumes: Task 1 的 `get_buyer_supplier_pairs` 输出格式（list[dict]，键同上）。
- Produces: `aggregate_by_buyer(pairs: list[dict]) -> list[dict]`，每个 dict 含 `buyer_code, buyer_name, currency, celling, reserved, actual, total_occupied, headroom, occupancy_rate, pairs`（`pairs` 为该买方下原始配对行列表，供页面/导出钻取）。

- [ ] **Step 1: 写失败测试**

```python
class TestAggregateByBuyer:

    def test_sums_multiple_pairs_for_same_buyer(self):
        from backend.app.services.credit_limit_service import aggregate_by_buyer
        pairs = [
            {'uid': 'U1', 'buyer_code': 'B1', 'buyer_name': 'Buyer One', 'supplier_code': 'S1',
             'supplier_name': 'Seller One', 'currency': 'USD', 'celling': 100000, 'reserved': 1000,
             'actual': 2000, 'total_occupied': 3000, 'headroom': 97000, 'occupancy_rate': 0.03},
            {'uid': 'U2', 'buyer_code': 'B1', 'buyer_name': 'Buyer One', 'supplier_code': 'S2',
             'supplier_name': 'Seller Two', 'currency': 'USD', 'celling': 50000, 'reserved': 0,
             'actual': 0, 'total_occupied': 0, 'headroom': 50000, 'occupancy_rate': 0.0},
        ]
        buyers = aggregate_by_buyer(pairs)
        assert len(buyers) == 1
        b = buyers[0]
        assert b['buyer_code'] == 'B1'
        assert b['buyer_name'] == 'Buyer One'
        assert b['celling'] == 150000
        assert b['reserved'] == 1000
        assert b['actual'] == 2000
        assert b['total_occupied'] == 3000
        assert b['headroom'] == 147000
        assert abs(b['occupancy_rate'] - 0.02) < 1e-9
        assert len(b['pairs']) == 2

    def test_zero_celling_buyer_has_none_headroom_and_occupancy(self):
        from backend.app.services.credit_limit_service import aggregate_by_buyer
        pairs = [
            {'uid': 'U1', 'buyer_code': 'B1', 'buyer_name': 'Buyer One', 'supplier_code': 'S1',
             'supplier_name': 'Seller One', 'currency': 'USD', 'celling': 0, 'reserved': 500,
             'actual': 0, 'total_occupied': 500, 'headroom': None, 'occupancy_rate': None},
        ]
        buyers = aggregate_by_buyer(pairs)
        assert buyers[0]['headroom'] is None
        assert buyers[0]['occupancy_rate'] is None

    def test_sorted_by_occupancy_rate_descending_with_none_last(self):
        from backend.app.services.credit_limit_service import aggregate_by_buyer
        pairs = [
            {'uid': 'U1', 'buyer_code': 'LOW', 'buyer_name': 'Low', 'supplier_code': 'S1',
             'supplier_name': 'S', 'currency': 'USD', 'celling': 1000, 'reserved': 100,
             'actual': 0, 'total_occupied': 100, 'headroom': 900, 'occupancy_rate': 0.1},
            {'uid': 'U2', 'buyer_code': 'HIGH', 'buyer_name': 'High', 'supplier_code': 'S2',
             'supplier_name': 'S', 'currency': 'USD', 'celling': 1000, 'reserved': 900,
             'actual': 0, 'total_occupied': 900, 'headroom': 100, 'occupancy_rate': 0.9},
            {'uid': 'U3', 'buyer_code': 'NA', 'buyer_name': 'NoLimit', 'supplier_code': 'S3',
             'supplier_name': 'S', 'currency': 'USD', 'celling': 0, 'reserved': 0,
             'actual': 0, 'total_occupied': 0, 'headroom': None, 'occupancy_rate': None},
        ]
        buyers = aggregate_by_buyer(pairs)
        assert [b['buyer_code'] for b in buyers] == ['HIGH', 'LOW', 'NA']

    def test_empty_pairs_returns_empty_list(self):
        from backend.app.services.credit_limit_service import aggregate_by_buyer
        assert aggregate_by_buyer([]) == []
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest backend/tests/test_credit_limit_service.py::TestAggregateByBuyer -v`
Expected: FAIL，`ImportError: cannot import name 'aggregate_by_buyer'`

- [ ] **Step 3: 实现 `aggregate_by_buyer`（追加到 `credit_limit_service.py` 末尾）**

```python
def aggregate_by_buyer(pairs):
    """将买卖方配对行按 buyer_code 汇总为买方层记录。"""
    buyers = {}
    for p in pairs:
        key = p['buyer_code'] or p['buyer_name']
        b = buyers.setdefault(key, {
            'buyer_code': p['buyer_code'],
            'buyer_name': p['buyer_name'],
            'currency': 'USD',
            'celling': 0.0,
            'reserved': 0.0,
            'actual': 0.0,
            'total_occupied': 0.0,
            'pairs': [],
        })
        b['celling'] = round(b['celling'] + p['celling'], 2)
        b['reserved'] = round(b['reserved'] + p['reserved'], 2)
        b['actual'] = round(b['actual'] + p['actual'], 2)
        b['total_occupied'] = round(b['total_occupied'] + p['total_occupied'], 2)
        b['pairs'].append(p)

    result = []
    for b in buyers.values():
        if b['celling'] > 0:
            b['headroom'] = round(b['celling'] - b['total_occupied'], 2)
            b['occupancy_rate'] = round(b['total_occupied'] / b['celling'], 4)
        else:
            b['headroom'] = None
            b['occupancy_rate'] = None
        result.append(b)

    result.sort(key=lambda b: (b['occupancy_rate'] is None, -(b['occupancy_rate'] or 0)))
    return result
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest backend/tests/test_credit_limit_service.py -v`
Expected: PASS（全部 12 项）

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/credit_limit_service.py backend/tests/test_credit_limit_service.py
git commit -m "feat: 新增额度管理买方层汇总聚合"
```

---

## Task 3: 预警阈值判定与配置常量

**Files:**
- Modify: `backend/app/services/credit_limit_service.py`
- Modify: `backend/app/config.py`
- Test: `backend/tests/test_credit_limit_service.py`

**Interfaces:**
- Consumes: Task 1/2 输出的 `buyer_rows`/`pair_rows`（含 `occupancy_rate` 键）。
- Produces: `check_warnings(buyer_rows: list[dict], pair_rows: list[dict], threshold: float) -> dict`，返回 `{'buyers': [...], 'pairs': [...]}`；`Config.CREDIT_WARNING_THRESHOLD = 0.9`。

- [ ] **Step 1: 写失败测试**

```python
class TestCheckWarnings:

    def test_filters_rows_at_or_above_threshold(self):
        from backend.app.services.credit_limit_service import check_warnings
        buyer_rows = [
            {'buyer_code': 'B1', 'occupancy_rate': 0.95},
            {'buyer_code': 'B2', 'occupancy_rate': 0.5},
            {'buyer_code': 'B3', 'occupancy_rate': 0.9},
        ]
        pair_rows = [
            {'uid': 'U1', 'occupancy_rate': 0.99},
            {'uid': 'U2', 'occupancy_rate': 0.1},
        ]
        result = check_warnings(buyer_rows, pair_rows, threshold=0.9)
        assert [b['buyer_code'] for b in result['buyers']] == ['B1', 'B3']
        assert [p['uid'] for p in result['pairs']] == ['U1']

    def test_excludes_none_occupancy_rate(self):
        from backend.app.services.credit_limit_service import check_warnings
        buyer_rows = [{'buyer_code': 'B1', 'occupancy_rate': None}]
        result = check_warnings(buyer_rows, [], threshold=0.9)
        assert result['buyers'] == []

    def test_no_rows_over_threshold_returns_empty_lists(self):
        from backend.app.services.credit_limit_service import check_warnings
        buyer_rows = [{'buyer_code': 'B1', 'occupancy_rate': 0.1}]
        result = check_warnings(buyer_rows, [], threshold=0.9)
        assert result == {'buyers': [], 'pairs': []}
```

```python
def test_credit_warning_threshold_default_is_point_nine(app):
    assert app.config['CREDIT_WARNING_THRESHOLD'] == 0.9
```
（此函数追加到新文件 `backend/tests/test_credit_limit_service.py` 顶层，使用 `app` fixture，需 `import pytest` 已存在于文件顶部；`app` fixture 来自 `conftest.py`，无需额外 import。）

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest backend/tests/test_credit_limit_service.py -v`
Expected: FAIL，`ImportError: cannot import name 'check_warnings'`；`KeyError: 'CREDIT_WARNING_THRESHOLD'`

- [ ] **Step 3: 实现**

在 `backend/app/config.py` 的 `Config` 类中，紧跟 `COMMON_EMAIL_URL` 定义之后新增：

```python
    # 额度管理每日预警阈值（占用率 >= 该值即预警），本期硬编码不做 UI 配置
    CREDIT_WARNING_THRESHOLD = 0.9
```

在 `credit_limit_service.py` 末尾追加：

```python
def check_warnings(buyer_rows, pair_rows, threshold):
    """筛选占用率达到/超过阈值的买方层与买卖方配对层记录。"""
    warned_buyers = [b for b in buyer_rows if b.get('occupancy_rate') is not None and b['occupancy_rate'] >= threshold]
    warned_pairs = [p for p in pair_rows if p.get('occupancy_rate') is not None and p['occupancy_rate'] >= threshold]
    return {'buyers': warned_buyers, 'pairs': warned_pairs}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest backend/tests/test_credit_limit_service.py -v`
Expected: PASS（全部 16 项）

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/credit_limit_service.py backend/app/config.py backend/tests/test_credit_limit_service.py
git commit -m "feat: 新增额度预警阈值判定与 CREDIT_WARNING_THRESHOLD 配置"
```

---

## Task 4: 重做 `/credit/credit-query` 页面（买方层 + 供应商层展开）

**Files:**
- Modify: `backend/app/routes/credit.py:1-110`（替换 `credit_query` 视图，保留 `credit_query_detail`/`_to_float`/`_fmt_date`/`get_mongo` 不变）
- Modify: `backend/app/templates/credit/credit_query.html`（整体重写）
- Modify: `backend/app/i18n/zh-CN.json:513-530`（`credit.query` 节点新增/调整键）
- Modify: `backend/app/i18n/en-US.json:406-423`（同上，英文）
- Test: `backend/tests/test_credit_query_route.py`

**Interfaces:**
- Consumes: Task 1 `get_buyer_supplier_pairs(mongo, buyer_filter=None)`，Task 2 `aggregate_by_buyer(pairs)`，`current_app.config['CREDIT_WARNING_THRESHOLD']`。
- Produces: 路由 `GET /credit/credit-query`，模板变量 `buyer_rows`（含嵌套 `pairs`）、`buyer_filter`、`threshold`、`total_buyers`、`error`。

- [ ] **Step 1: 写失败测试**

```python
"""额度查询页面路由测试（买方层 + 供应商层）"""
from unittest.mock import patch


SAMPLE_BUYER_ROWS = [
    {
        'buyer_code': 'B1', 'buyer_name': 'Amazon Services', 'currency': 'USD',
        'celling': 100000.0, 'reserved': 20000.0, 'actual': 75000.0,
        'total_occupied': 95000.0, 'headroom': 5000.0, 'occupancy_rate': 0.95,
        'pairs': [
            {'uid': 'U1', 'buyer_code': 'B1', 'buyer_name': 'Amazon Services',
             'supplier_code': 'S1', 'supplier_name': 'Photonverse Inc', 'currency': 'USD',
             'celling': 100000.0, 'reserved': 20000.0, 'actual': 75000.0,
             'total_occupied': 95000.0, 'headroom': 5000.0, 'occupancy_rate': 0.95},
        ],
    },
]


class TestCreditQueryRoute:

    @patch('backend.app.routes.credit.get_mongo')
    @patch('backend.app.routes.credit.aggregate_by_buyer')
    @patch('backend.app.routes.credit.get_buyer_supplier_pairs')
    def test_renders_buyer_rows(self, mock_pairs, mock_aggregate, mock_get_mongo, logged_in_client):
        mock_get_mongo.return_value = object()
        mock_pairs.return_value = []
        mock_aggregate.return_value = SAMPLE_BUYER_ROWS

        resp = logged_in_client.get('/credit/credit-query')
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        assert 'Amazon Services' in body
        assert 'Photonverse Inc' in body

    @patch('backend.app.routes.credit.get_mongo')
    @patch('backend.app.routes.credit.aggregate_by_buyer')
    @patch('backend.app.routes.credit.get_buyer_supplier_pairs')
    def test_over_threshold_row_is_highlighted(self, mock_pairs, mock_aggregate, mock_get_mongo, logged_in_client):
        mock_get_mongo.return_value = object()
        mock_pairs.return_value = []
        mock_aggregate.return_value = SAMPLE_BUYER_ROWS

        resp = logged_in_client.get('/credit/credit-query')
        body = resp.get_data(as_text=True)
        assert 'table-danger' in body

    @patch('backend.app.routes.credit.get_mongo')
    def test_no_mongo_renders_empty_without_crash(self, mock_get_mongo, logged_in_client):
        mock_get_mongo.return_value = None
        resp = logged_in_client.get('/credit/credit-query')
        assert resp.status_code == 200

    @patch('backend.app.routes.credit.get_mongo')
    @patch('backend.app.routes.credit.aggregate_by_buyer')
    @patch('backend.app.routes.credit.get_buyer_supplier_pairs')
    def test_buyer_filter_passed_to_service(self, mock_pairs, mock_aggregate, mock_get_mongo, logged_in_client):
        mock_get_mongo.return_value = object()
        mock_pairs.return_value = []
        mock_aggregate.return_value = []

        logged_in_client.get('/credit/credit-query?buyer_name=Amazon')
        mock_pairs.assert_called_once()
        assert mock_pairs.call_args[1].get('buyer_filter') == 'Amazon'

    def test_requires_login(self, client):
        resp = client.get('/credit/credit-query')
        assert resp.status_code in (302, 401)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest backend/tests/test_credit_query_route.py -v`
Expected: FAIL（旧路由不认识 `buyer_filter` kwarg 调用方式，模板不含新字段/新样式类）

- [ ] **Step 3: 重写路由**

将 `backend/app/routes/credit.py` 顶部 import 改为：

```python
from flask import render_template, request, current_app
from flask_login import login_required
from backend.app.routes import credit_bp
from backend.app.services.credit_limit_service import get_buyer_supplier_pairs, aggregate_by_buyer
```

将原 `credit_query` 视图函数整体替换为：

```python
@credit_bp.route('/credit-query')
@login_required
def credit_query():
    mongo = get_mongo()
    buyer_rows = []
    error = None
    buyer_filter = request.args.get('buyer_name', '').strip()
    threshold = current_app.config.get('CREDIT_WARNING_THRESHOLD', 0.9)

    if mongo is not None:
        try:
            pairs = get_buyer_supplier_pairs(mongo, buyer_filter=buyer_filter or None)
            buyer_rows = aggregate_by_buyer(pairs)
        except Exception as e:
            error = str(e)

    return render_template(
        'credit/credit_query.html',
        buyer_rows=buyer_rows,
        error=error,
        buyer_filter=buyer_filter,
        threshold=threshold,
        total_buyers=len(buyer_rows),
    )
```

（`_to_float`、`_fmt_date`、`credit_query_detail`、`get_mongo` 保持不变，位于同一文件其余部分。）

- [ ] **Step 4: 重写模板**

`backend/app/templates/credit/credit_query.html` 整体替换为：

```html
{% extends "base.html" %}

{% block title %}{{ _('credit.query.title') }} - {{ config.APP_NAME }}{% endblock %}

{% block content %}
<div class="d-flex justify-content-between align-items-center mb-3">
    <h4><i class="fa fa-credit-card"></i> {{ _('credit.query.title') }}</h4>
</div>

<div class="card mb-3">
    <div class="card-body py-2">
        <form method="get" class="row g-2 align-items-end">
            <div class="col-auto">
                <label class="form-label mb-1 small">{{ _('credit.query.buyer_name') }}</label>
                <input type="text" class="form-control form-control-sm" name="buyer_name"
                       value="{{ buyer_filter }}" placeholder="{{ _('credit.query.buyer_placeholder') }}">
            </div>
            <div class="col-auto">
                <button type="submit" class="btn btn-primary btn-sm">
                    <i class="fa fa-search"></i> {{ _('credit.query.search') }}
                </button>
                <a href="{{ url_for('credit.credit_query') }}" class="btn btn-secondary btn-sm ms-1">
                    <i class="fa fa-refresh"></i> {{ _('credit.query.reset') }}
                </a>
                <button type="submit" formaction="{{ url_for('credit.credit_export') }}" formmethod="post"
                        class="btn btn-outline-success btn-sm ms-1">
                    <i class="fa fa-file-excel-o"></i> {{ _('credit.query.export') }}
                </button>
            </div>
        </form>
    </div>
</div>

{% if error %}
<div class="alert alert-danger">
    <i class="fa fa-exclamation-triangle"></i> {{ error }}
</div>
{% endif %}

<div class="mb-2 text-muted small">
    {{ _('credit.query.total_buyers') }}: <strong>{{ total_buyers }}</strong>
    &middot; {{ _('credit.query.warning_threshold') }}: <strong>{{ "{:.0%}".format(threshold) }}</strong>
</div>

<div class="card">
    <div class="card-body p-0">
        <div class="table-responsive">
            <table class="table table-striped table-hover table-sm mb-0">
                <thead class="table-dark">
                    <tr>
                        <th></th>
                        <th>{{ _('credit.query.buyer_name') }}</th>
                        <th>{{ _('credit.query.currency') }}</th>
                        <th class="text-end">{{ _('credit.query.celling') }}</th>
                        <th class="text-end">{{ _('credit.query.reserved') }}</th>
                        <th class="text-end">{{ _('credit.query.actual') }}</th>
                        <th class="text-end">{{ _('credit.query.total_occupied') }}</th>
                        <th class="text-end">{{ _('credit.query.headroom') }}</th>
                        <th class="text-end">{{ _('credit.query.occupancy_rate') }}</th>
                    </tr>
                </thead>
                <tbody>
                    {% if buyer_rows %}
                        {% for b in buyer_rows %}
                        <tr {% if b.occupancy_rate is not none and b.occupancy_rate >= threshold %}class="table-danger"{% endif %}
                            data-bs-toggle="collapse" data-bs-target="#buyer-{{ loop.index }}" role="button">
                            <td class="text-muted small"><i class="fa fa-caret-right"></i></td>
                            <td>{{ b.buyer_name or '-' }}</td>
                            <td>{{ b.currency }}</td>
                            <td class="text-end font-monospace">{{ "{:,.2f}".format(b.celling) }}</td>
                            <td class="text-end font-monospace">{{ "{:,.2f}".format(b.reserved) }}</td>
                            <td class="text-end font-monospace">{{ "{:,.2f}".format(b.actual) }}</td>
                            <td class="text-end font-monospace fw-bold">{{ "{:,.2f}".format(b.total_occupied) }}</td>
                            <td class="text-end font-monospace">
                                {% if b.headroom is none %}
                                    <span class="text-muted">N/A</span>
                                {% else %}
                                    {{ "{:,.2f}".format(b.headroom) }}
                                {% endif %}
                            </td>
                            <td class="text-end font-monospace">
                                {% if b.occupancy_rate is none %}
                                    <span class="text-muted">N/A</span>
                                {% else %}
                                    {{ "{:.1%}".format(b.occupancy_rate) }}
                                {% endif %}
                            </td>
                        </tr>
                        <tr class="collapse" id="buyer-{{ loop.index }}">
                            <td colspan="9" class="p-0 bg-light">
                                <table class="table table-sm mb-0">
                                    <thead>
                                        <tr class="small text-muted">
                                            <th></th>
                                            <th>{{ _('credit.query.seller_name') }}</th>
                                            <th>{{ _('credit.query.currency') }}</th>
                                            <th class="text-end">{{ _('credit.query.celling') }}</th>
                                            <th class="text-end">{{ _('credit.query.reserved') }}</th>
                                            <th class="text-end">{{ _('credit.query.actual') }}</th>
                                            <th class="text-end">{{ _('credit.query.total_occupied') }}</th>
                                            <th class="text-end">{{ _('credit.query.headroom') }}</th>
                                            <th class="text-end">{{ _('credit.query.occupancy_rate') }}</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {% for p in b.pairs %}
                                        <tr {% if p.occupancy_rate is not none and p.occupancy_rate >= threshold %}class="table-danger"{% endif %}>
                                            <td></td>
                                            <td>{{ p.supplier_name or '-' }}</td>
                                            <td>{{ p.currency }}</td>
                                            <td class="text-end font-monospace">{{ "{:,.2f}".format(p.celling) }}</td>
                                            <td class="text-end font-monospace">{{ "{:,.2f}".format(p.reserved) }}</td>
                                            <td class="text-end font-monospace">{{ "{:,.2f}".format(p.actual) }}</td>
                                            <td class="text-end font-monospace">{{ "{:,.2f}".format(p.total_occupied) }}</td>
                                            <td class="text-end font-monospace">
                                                {% if p.headroom is none %}<span class="text-muted">N/A</span>
                                                {% else %}{{ "{:,.2f}".format(p.headroom) }}{% endif %}
                                            </td>
                                            <td class="text-end font-monospace">
                                                {% if p.occupancy_rate is none %}<span class="text-muted">N/A</span>
                                                {% else %}{{ "{:.1%}".format(p.occupancy_rate) }}{% endif %}
                                            </td>
                                        </tr>
                                        <tr>
                                            <td colspan="9" class="text-end pe-3 pb-2">
                                                <a href="{{ url_for('credit.credit_query_detail',
                                                    buyer_name=p.buyer_name, supplier_name=p.supplier_name,
                                                    currency=p.currency, back_buyer=buyer_filter) }}"
                                                   class="btn btn-outline-primary btn-sm">
                                                    <i class="fa fa-search-plus"></i> {{ _('credit.query.detail') }}
                                                </a>
                                            </td>
                                        </tr>
                                        {% endfor %}
                                    </tbody>
                                </table>
                            </td>
                        </tr>
                        {% endfor %}
                    {% else %}
                        <tr>
                            <td colspan="9" class="text-center text-muted py-4">
                                <i class="fa fa-inbox fa-2x mb-2 d-block"></i>
                                {{ _('common.message.no_data') }}
                            </td>
                        </tr>
                    {% endif %}
                </tbody>
            </table>
        </div>
    </div>
</div>
{% endblock %}
```

- [ ] **Step 5: 更新 i18n 文案**

在 `backend/app/i18n/zh-CN.json` 的 `credit.query` 对象中，删除 `total_wip`/`total_outstanding_excl_wip`/`total_os_amount`/`record_count`/`total`/`total_groups`（旧字段不再使用），新增：

```json
      "export": "导出Excel",
      "total_buyers": "买方数",
      "warning_threshold": "预警阈值",
      "celling": "额度上限",
      "reserved": "预占",
      "actual": "实占",
      "total_occupied": "总额",
      "headroom": "可用余量",
      "occupancy_rate": "占用率",
      "export_no_data": "没有找到符合条件的数据"
```

`credit.query.buyer_name`/`seller_name`/`buyer_placeholder`/`search`/`reset`/`currency`/`detail` 保留不变（仍被新模板使用）；`seller_placeholder` 可保留不用或删除均可，不影响功能。

在 `backend/app/i18n/en-US.json` 对应位置做同样增删，英文值：

```json
      "export": "Export Excel",
      "total_buyers": "Total Buyers",
      "warning_threshold": "Warning Threshold",
      "celling": "Celling",
      "reserved": "Reserved",
      "actual": "Actual",
      "total_occupied": "Total Occupied",
      "headroom": "Headroom",
      "occupancy_rate": "Occupancy Rate",
      "export_no_data": "No data found matching the criteria"
```

- [ ] **Step 6: 运行测试确认通过**

Run: `pytest backend/tests/test_credit_query_route.py -v`
Expected: PASS（5 项全部通过）；注意 `test_over_threshold_row_is_highlighted` 依赖模板中 `table-danger` 类字符串，若断言失败请检查模板 Step 4 是否已保存。

- [ ] **Step 7: Commit**

```bash
git add backend/app/routes/credit.py backend/app/templates/credit/credit_query.html \
        backend/app/i18n/zh-CN.json backend/app/i18n/en-US.json backend/tests/test_credit_query_route.py
git commit -m "feat: 重做额度查询页面为买方层汇总+供应商层展开"
```

---

## Task 5: 额度导出 Excel（`POST /credit/export`）

**Files:**
- Create: `backend/app/services/credit_export_service.py`
- Modify: `backend/app/routes/credit.py`（新增 `credit_export` 视图 + 顶部 import）
- Test: `backend/tests/test_credit_export_service.py`

**Interfaces:**
- Consumes: `aggregate_by_buyer` 输出格式（`buyer_rows`，每项含 `pairs` 子列表，字段同 Task 1/2）。
- Produces: `build_credit_limit_workbook(buyer_rows: list[dict]) -> bytes`；路由 `POST /credit/export`。

- [ ] **Step 1: 写失败测试 — 导出服务**

```python
"""额度管理 Excel 导出测试"""
import io
from openpyxl import load_workbook


SAMPLE_BUYER_ROWS = [
    {
        'buyer_code': 'B1', 'buyer_name': 'Amazon Services', 'currency': 'USD',
        'celling': 100000.0, 'reserved': 20000.0, 'actual': 75000.0,
        'total_occupied': 95000.0, 'headroom': 5000.0, 'occupancy_rate': 0.95,
        'pairs': [
            {'uid': 'U1', 'buyer_code': 'B1', 'buyer_name': 'Amazon Services',
             'supplier_code': 'S1', 'supplier_name': 'Photonverse Inc', 'currency': 'USD',
             'celling': 100000.0, 'reserved': 20000.0, 'actual': 75000.0,
             'total_occupied': 95000.0, 'headroom': 5000.0, 'occupancy_rate': 0.95},
        ],
    },
]


class TestBuildCreditLimitWorkbook:

    def test_creates_summary_and_per_buyer_sheets(self):
        from backend.app.services.credit_export_service import build_credit_limit_workbook
        data = build_credit_limit_workbook(SAMPLE_BUYER_ROWS)
        wb = load_workbook(io.BytesIO(data))
        assert wb.sheetnames[0] == 'Buyer Summary'
        assert 'Amazon Services' in wb.sheetnames[1]

    def test_summary_sheet_contains_buyer_row_values(self):
        from backend.app.services.credit_export_service import build_credit_limit_workbook
        data = build_credit_limit_workbook(SAMPLE_BUYER_ROWS)
        wb = load_workbook(io.BytesIO(data))
        ws = wb['Buyer Summary']
        rows = list(ws.iter_rows(values_only=True))
        assert rows[0][0] == 'Buyer'
        assert rows[1][0] == 'Amazon Services'
        assert rows[1][2] == 100000.0  # Celling column

    def test_buyer_detail_sheet_contains_supplier_row(self):
        from backend.app.services.credit_export_service import build_credit_limit_workbook
        data = build_credit_limit_workbook(SAMPLE_BUYER_ROWS)
        wb = load_workbook(io.BytesIO(data))
        ws = wb[wb.sheetnames[1]]
        rows = list(ws.iter_rows(values_only=True))
        assert rows[0][0] == 'Supplier'
        assert rows[1][0] == 'Photonverse Inc'

    def test_sheet_name_truncated_and_sanitized(self):
        from backend.app.services.credit_export_service import build_credit_limit_workbook
        long_name_rows = [
            {**SAMPLE_BUYER_ROWS[0], 'buyer_name': 'A' * 40 + '/Invalid:Name?'},
        ]
        data = build_credit_limit_workbook(long_name_rows)
        wb = load_workbook(io.BytesIO(data))
        assert len(wb.sheetnames[1]) <= 31
        for ch in '\\/*?:[]':
            assert ch not in wb.sheetnames[1]

    def test_duplicate_buyer_names_get_unique_sheet_names(self):
        from backend.app.services.credit_export_service import build_credit_limit_workbook
        rows = [
            {**SAMPLE_BUYER_ROWS[0], 'buyer_code': 'B1'},
            {**SAMPLE_BUYER_ROWS[0], 'buyer_code': 'B2'},
        ]
        data = build_credit_limit_workbook(rows)
        wb = load_workbook(io.BytesIO(data))
        assert len(set(wb.sheetnames[1:])) == 2

    def test_empty_buyer_rows_still_produces_summary_only_workbook(self):
        from backend.app.services.credit_export_service import build_credit_limit_workbook
        data = build_credit_limit_workbook([])
        wb = load_workbook(io.BytesIO(data))
        assert wb.sheetnames == ['Buyer Summary']
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest backend/tests/test_credit_export_service.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'backend.app.services.credit_export_service'`

- [ ] **Step 3: 实现导出服务**

```python
"""额度管理 Excel 导出 — 买方汇总 sheet + 每个买方一个供应商明细 sheet"""
import io
import re
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Border, Side, Alignment

_INVALID_SHEET_CHARS = re.compile(r'[\\/*?:\[\]]')

_HEADER_FONT = Font(bold=True, color="FFFFFF")
_HEADER_FILL = PatternFill(start_color="4F81BD", end_color="4F81BD", fill_type="solid")
_THIN_BORDER = Border(left=Side(style='thin'), right=Side(style='thin'),
                       top=Side(style='thin'), bottom=Side(style='thin'))
_CENTER = Alignment(horizontal="center", vertical="center")
_LEFT = Alignment(horizontal="left", vertical="center")

_SUMMARY_HEADERS = ['Buyer', 'Currency', 'Celling', 'Reserved', 'Actual', 'Total Occupied', 'Headroom', 'Occupancy Rate']
_DETAIL_HEADERS = ['Supplier', 'Currency', 'Celling', 'Reserved', 'Actual', 'Total Occupied', 'Headroom', 'Occupancy Rate']


def _sanitize_sheet_name(name, used_names):
    cleaned = _INVALID_SHEET_CHARS.sub('_', name or 'Buyer').strip() or 'Buyer'
    base = cleaned[:31]
    candidate = base
    suffix = 1
    while candidate in used_names:
        suffix_str = f'_{suffix}'
        candidate = base[:31 - len(suffix_str)] + suffix_str
        suffix += 1
    used_names.add(candidate)
    return candidate


def _write_header(ws, headers):
    ws.append(headers)
    for cell in ws[1]:
        cell.font = _HEADER_FONT
        cell.fill = _HEADER_FILL
        cell.border = _THIN_BORDER
        cell.alignment = _CENTER


def _write_data_row(ws, values):
    ws.append(values)
    for cell in ws[ws.max_row]:
        cell.border = _THIN_BORDER
        cell.alignment = _LEFT


def _autofit_columns(ws):
    for column_cells in ws.columns:
        length = max(len(str(cell.value)) if cell.value is not None else 0 for cell in column_cells)
        ws.column_dimensions[column_cells[0].column_letter].width = length + 2


def _row_values(name, row):
    occupancy = row.get('occupancy_rate')
    return [
        name,
        row.get('currency', 'USD'),
        row.get('celling', 0.0),
        row.get('reserved', 0.0),
        row.get('actual', 0.0),
        row.get('total_occupied', 0.0),
        row.get('headroom') if row.get('headroom') is not None else 'N/A',
        f"{occupancy:.1%}" if occupancy is not None else 'N/A',
    ]


def build_credit_limit_workbook(buyer_rows):
    """构建额度管理 Excel：sheet1 买方汇总，之后每买方一个供应商明细 sheet。"""
    wb = Workbook()
    summary_ws = wb.active
    summary_ws.title = 'Buyer Summary'
    _write_header(summary_ws, _SUMMARY_HEADERS)
    for b in buyer_rows:
        _write_data_row(summary_ws, _row_values(b.get('buyer_name', ''), b))
    _autofit_columns(summary_ws)

    used_names = {'Buyer Summary'}
    for b in buyer_rows:
        sheet_name = _sanitize_sheet_name(b.get('buyer_name') or b.get('buyer_code') or 'Buyer', used_names)
        ws = wb.create_sheet(sheet_name)
        _write_header(ws, _DETAIL_HEADERS)
        for p in b.get('pairs', []):
            _write_data_row(ws, _row_values(p.get('supplier_name', ''), p))
        _autofit_columns(ws)

    output = io.BytesIO()
    wb.save(output)
    return output.getvalue()
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest backend/tests/test_credit_export_service.py -v`
Expected: PASS（6 项全部通过）

- [ ] **Step 5: 新增导出路由**

在 `backend/app/routes/credit.py` 顶部 import 追加：

```python
import io
from datetime import datetime
from flask import send_file, flash, redirect, url_for
from backend.app.services.credit_export_service import build_credit_limit_workbook
```

在 `credit_query` 视图之后、`credit_query_detail` 之前新增：

```python
@credit_bp.route('/export', methods=['POST'])
@login_required
def credit_export():
    mongo = get_mongo()
    buyer_filter = request.form.get('buyer_name', '').strip()

    if mongo is None:
        flash('没有找到符合条件的数据', 'warning')
        return redirect(url_for('credit.credit_query', buyer_name=buyer_filter))

    pairs = get_buyer_supplier_pairs(mongo, buyer_filter=buyer_filter or None)
    buyer_rows = aggregate_by_buyer(pairs)

    if not buyer_rows:
        flash('没有找到符合条件的数据', 'warning')
        return redirect(url_for('credit.credit_query', buyer_name=buyer_filter))

    workbook_bytes = build_credit_limit_workbook(buyer_rows)
    filename = f"credit_limit_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return send_file(
        io.BytesIO(workbook_bytes),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=filename,
    )
```

- [ ] **Step 6: 写路由测试**

新建 `backend/tests/test_credit_export_route.py`：

```python
"""额度管理导出路由测试"""
from unittest.mock import patch


class TestCreditExportRoute:

    @patch('backend.app.routes.credit.get_mongo')
    @patch('backend.app.routes.credit.aggregate_by_buyer')
    @patch('backend.app.routes.credit.get_buyer_supplier_pairs')
    def test_export_returns_xlsx_file(self, mock_pairs, mock_aggregate, mock_get_mongo, logged_in_client):
        mock_get_mongo.return_value = object()
        mock_pairs.return_value = []
        mock_aggregate.return_value = [
            {'buyer_code': 'B1', 'buyer_name': 'Amazon Services', 'currency': 'USD',
             'celling': 1000.0, 'reserved': 0.0, 'actual': 0.0, 'total_occupied': 0.0,
             'headroom': 1000.0, 'occupancy_rate': 0.0, 'pairs': []},
        ]
        resp = logged_in_client.post('/credit/export')
        assert resp.status_code == 200
        assert resp.mimetype == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'

    @patch('backend.app.routes.credit.get_mongo')
    @patch('backend.app.routes.credit.aggregate_by_buyer')
    @patch('backend.app.routes.credit.get_buyer_supplier_pairs')
    def test_export_empty_result_redirects_with_flash(self, mock_pairs, mock_aggregate, mock_get_mongo, logged_in_client):
        mock_get_mongo.return_value = object()
        mock_pairs.return_value = []
        mock_aggregate.return_value = []
        resp = logged_in_client.post('/credit/export', follow_redirects=True)
        assert resp.status_code == 200
        assert '没有找到符合条件的数据' in resp.get_data(as_text=True)

    def test_export_requires_login(self, client):
        resp = client.post('/credit/export')
        assert resp.status_code in (302, 401)
```

- [ ] **Step 7: 运行全部测试确认通过**

Run: `pytest backend/tests/test_credit_export_service.py backend/tests/test_credit_export_route.py -v`
Expected: PASS（9 项全部通过）

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/credit_export_service.py backend/app/routes/credit.py \
        backend/tests/test_credit_export_service.py backend/tests/test_credit_export_route.py
git commit -m "feat: 新增额度管理 Excel 导出（买方汇总+供应商明细多 sheet）"
```

---

## Task 6: 每日额度预警服务（定时任务 + 邮件 + 手动触发）

**Files:**
- Create: `backend/app/services/credit_warning_service.py`
- Modify: `backend/app/routes/credit.py`（新增 `trigger_warning_check` 视图）
- Test: `backend/tests/test_credit_warning_service.py`

**Interfaces:**
- Consumes: Task 1/2/3 的 `get_buyer_supplier_pairs`、`aggregate_by_buyer`、`check_warnings`；`current_app.config['COMMON_EMAIL_URL']`、`current_app.config['CREDIT_WARNING_THRESHOLD']`。
- Produces: `register_credit_warning_job(scheduler, app)`；`credit_warning_task(app)`；`run_warning_check_manual() -> dict`（含 `success, checked_buyers, checked_pairs, warned_count, email_sent, message`）；路由 `POST /credit/api/trigger-warning-check`。

- [ ] **Step 1: 写失败测试**

```python
"""每日额度预警服务测试"""
from unittest.mock import patch, MagicMock
import pytest
import requests as req_lib


WARNED_BUYERS = [
    {'buyer_code': 'B1', 'buyer_name': 'Amazon Services', 'currency': 'USD',
     'celling': 100000.0, 'reserved': 20000.0, 'actual': 75000.0,
     'total_occupied': 95000.0, 'headroom': 5000.0, 'occupancy_rate': 0.95},
]
WARNED_PAIRS = [
    {'uid': 'U1', 'buyer_name': 'Amazon Services', 'supplier_name': 'Photonverse Inc',
     'currency': 'USD', 'celling': 100000.0, 'reserved': 20000.0, 'actual': 75000.0,
     'total_occupied': 95000.0, 'headroom': 5000.0, 'occupancy_rate': 0.95},
]


class TestRunWarningCheck:

    @patch('backend.app.services.credit_warning_service._get_mongo')
    @patch('backend.app.services.credit_warning_service.get_buyer_supplier_pairs')
    @patch('backend.app.services.credit_warning_service.aggregate_by_buyer')
    @patch('backend.app.services.credit_warning_service.check_warnings')
    @patch('backend.app.services.credit_warning_service._send_warning_email')
    def test_sends_email_when_warnings_found(self, mock_send, mock_check, mock_agg, mock_pairs, mock_get_mongo, app):
        from backend.app.services.credit_warning_service import _run_warning_check
        mock_get_mongo.return_value = MagicMock()
        mock_pairs.return_value = WARNED_PAIRS
        mock_agg.return_value = WARNED_BUYERS
        mock_check.return_value = {'buyers': WARNED_BUYERS, 'pairs': WARNED_PAIRS}
        mock_send.return_value = True

        with app.app_context():
            result = _run_warning_check()

        assert result['warned_count'] == 1
        assert result['email_sent'] is True
        mock_send.assert_called_once()

    @patch('backend.app.services.credit_warning_service._get_mongo')
    @patch('backend.app.services.credit_warning_service.get_buyer_supplier_pairs')
    @patch('backend.app.services.credit_warning_service.aggregate_by_buyer')
    @patch('backend.app.services.credit_warning_service.check_warnings')
    @patch('backend.app.services.credit_warning_service._send_warning_email')
    def test_skips_email_when_no_warnings(self, mock_send, mock_check, mock_agg, mock_pairs, mock_get_mongo, app):
        from backend.app.services.credit_warning_service import _run_warning_check
        mock_get_mongo.return_value = MagicMock()
        mock_pairs.return_value = []
        mock_agg.return_value = []
        mock_check.return_value = {'buyers': [], 'pairs': []}

        with app.app_context():
            result = _run_warning_check()

        assert result['warned_count'] == 0
        assert result['email_sent'] is False
        mock_send.assert_not_called()

    @patch('backend.app.services.credit_warning_service._get_mongo')
    def test_raises_when_no_mongo(self, mock_get_mongo, app):
        from backend.app.services.credit_warning_service import _run_warning_check
        mock_get_mongo.return_value = None
        with app.app_context():
            with pytest.raises(RuntimeError):
                _run_warning_check()


class TestSendWarningEmail:

    def test_posts_json_payload_to_common_email_url(self, app):
        from backend.app.services.credit_warning_service import _send_warning_email
        with app.app_context():
            app.config['COMMON_EMAIL_URL'] = 'https://n8n-v2.air8.cn/webhook/commonSendEmailForRefactoring'
            with patch('backend.app.services.credit_warning_service.requests.post') as mock_post:
                mock_post.return_value = MagicMock(status_code=200, text='ok')
                result = _send_warning_email(WARNED_BUYERS, WARNED_PAIRS)
        assert result is True
        call_kwargs = mock_post.call_args
        payload = call_kwargs[1]['json']
        assert payload['type'] == 'common'
        assert 'Amazon Services' in payload['body']

    def test_returns_false_when_email_url_not_configured(self, app):
        from backend.app.services.credit_warning_service import _send_warning_email
        with app.app_context():
            app.config['COMMON_EMAIL_URL'] = None
            result = _send_warning_email(WARNED_BUYERS, WARNED_PAIRS)
        assert result is False

    def test_raises_on_request_exception(self, app):
        from backend.app.services.credit_warning_service import _send_warning_email
        with app.app_context():
            app.config['COMMON_EMAIL_URL'] = 'https://n8n-v2.air8.cn/webhook/commonSendEmailForRefactoring'
            with patch('backend.app.services.credit_warning_service.requests.post') as mock_post:
                mock_post.side_effect = req_lib.exceptions.RequestException('timeout')
                with pytest.raises(req_lib.exceptions.RequestException):
                    _send_warning_email(WARNED_BUYERS, WARNED_PAIRS)


class TestManualTrigger:

    @patch('backend.app.services.credit_warning_service._run_warning_check')
    def test_returns_success(self, mock_run):
        from backend.app.services.credit_warning_service import run_warning_check_manual
        mock_run.return_value = {'checked_buyers': 3, 'checked_pairs': 5, 'warned_count': 1, 'email_sent': True}
        result = run_warning_check_manual()
        assert result['success'] is True

    @patch('backend.app.services.credit_warning_service._run_warning_check')
    def test_returns_failure_on_exception(self, mock_run):
        from backend.app.services.credit_warning_service import run_warning_check_manual
        mock_run.side_effect = RuntimeError('DB error')
        result = run_warning_check_manual()
        assert result['success'] is False
        assert 'DB error' in result['message']


class TestSchedulerRegistration:

    def test_registers_cron_job_at_seven_am(self):
        from backend.app.services.credit_warning_service import register_credit_warning_job
        scheduler = MagicMock()
        app = MagicMock()
        register_credit_warning_job(scheduler, app)
        scheduler.add_job.assert_called_once()
        call_kwargs = scheduler.add_job.call_args
        assert call_kwargs[1]['id'] == 'credit_limit_warning'
        assert call_kwargs[0][1] == 'cron'
        assert call_kwargs[1]['hour'] == 7
        assert call_kwargs[1]['minute'] == 0


class TestTriggerWarningCheckEndpoint:

    @patch('backend.app.services.credit_warning_service.run_warning_check_manual')
    def test_endpoint_returns_200_on_success(self, mock_manual, logged_in_client):
        mock_manual.return_value = {'success': True, 'checked_buyers': 2, 'checked_pairs': 3,
                                     'warned_count': 0, 'email_sent': False}
        resp = logged_in_client.post('/credit/api/trigger-warning-check')
        assert resp.status_code == 200
        assert resp.get_json()['success'] is True

    @patch('backend.app.services.credit_warning_service.run_warning_check_manual')
    def test_endpoint_returns_500_on_failure(self, mock_manual, logged_in_client):
        mock_manual.return_value = {'success': False, 'message': 'DB error'}
        resp = logged_in_client.post('/credit/api/trigger-warning-check')
        assert resp.status_code == 500

    def test_endpoint_requires_login(self, client):
        resp = client.post('/credit/api/trigger-warning-check')
        assert resp.status_code in (302, 401)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest backend/tests/test_credit_warning_service.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'backend.app.services.credit_warning_service'`

- [ ] **Step 3: 实现 `credit_warning_service.py`**

```python
"""每日额度预警服务 — 复用实时聚合逻辑，超阈值时发送汇总邮件"""
import html
import logging
from datetime import datetime
import requests
from flask import current_app
from backend.app.services.credit_limit_service import (
    get_buyer_supplier_pairs, aggregate_by_buyer, check_warnings,
)

logger = logging.getLogger('credit_warning')


def register_credit_warning_job(scheduler, app):
    """注册定时任务到 APScheduler：每天 07:00 Asia/Shanghai"""
    scheduler.add_job(
        credit_warning_task,
        'cron',
        hour=7,
        minute=0,
        args=[app],
        id='credit_limit_warning',
        replace_existing=True,
    )
    logger.info('Registered credit limit warning job: 07:00 Asia/Shanghai')


def credit_warning_task(app):
    """定时任务入口（在 scheduler 线程中执行）"""
    with app.app_context():
        logger.info('=== Credit limit warning task started ===')
        try:
            _run_warning_check()
        except Exception as e:
            logger.error('Credit limit warning task failed: %s', e, exc_info=True)
        logger.info('=== Credit limit warning task finished ===')


def run_warning_check_manual():
    """手动触发入口（在 Flask request context 中调用）"""
    try:
        result = _run_warning_check()
        return {'success': True, **result}
    except Exception as e:
        logger.error('Manual credit warning check failed: %s', e, exc_info=True)
        return {'success': False, 'message': str(e)}


def _get_mongo():
    try:
        from backend.app.extensions import mongo as ext_mongo
        if ext_mongo is not None:
            return ext_mongo
    except Exception:
        pass
    try:
        if hasattr(current_app, 'extensions'):
            m = current_app.extensions.get('mongo')
            if m is not None:
                return m
    except Exception:
        pass
    return None


def _run_warning_check():
    """核心检查逻辑：聚合 → 阈值筛选 → 超阈值则发邮件"""
    mongo = _get_mongo()
    if mongo is None:
        raise RuntimeError('数据库未连接')

    threshold = current_app.config.get('CREDIT_WARNING_THRESHOLD', 0.9)
    pairs = get_buyer_supplier_pairs(mongo)
    buyers = aggregate_by_buyer(pairs)
    warned = check_warnings(buyers, pairs, threshold)

    warned_count = len(warned['buyers'])
    email_sent = False
    if warned_count > 0:
        email_sent = _send_warning_email(warned['buyers'], warned['pairs'])

    logger.info(
        'Credit warning check done: buyers=%d pairs=%d warned=%d email_sent=%s',
        len(buyers), len(pairs), warned_count, email_sent,
    )
    return {
        'checked_buyers': len(buyers),
        'checked_pairs': len(pairs),
        'warned_count': warned_count,
        'email_sent': email_sent,
    }


def _send_warning_email(warned_buyers, warned_pairs):
    """通过 n8n-v2 通用邮件 webhook（COMMON_EMAIL_URL）发送超阈值汇总邮件。"""
    email_url = current_app.config.get('COMMON_EMAIL_URL')
    if not email_url:
        logger.warning('邮件接口未配置(COMMON_EMAIL_URL)，跳过额度预警通知')
        return False

    today = datetime.now().strftime('%Y-%m-%d')

    buyer_rows_html = ''.join(
        '<tr>'
        f'<td>{html.escape(str(b.get("buyer_name", "")))}</td>'
        f'<td>{b.get("currency", "")}</td>'
        f'<td>{b.get("celling", 0):,.2f}</td>'
        f'<td>{b.get("total_occupied", 0):,.2f}</td>'
        f'<td>{b.get("headroom", 0):,.2f}</td>'
        f'<td>{b.get("occupancy_rate", 0):.1%}</td>'
        '</tr>'
        for b in warned_buyers
    )
    pair_rows_html = ''.join(
        '<tr>'
        f'<td>{html.escape(str(p.get("buyer_name", "")))}</td>'
        f'<td>{html.escape(str(p.get("supplier_name", "")))}</td>'
        f'<td>{p.get("currency", "")}</td>'
        f'<td>{p.get("celling", 0):,.2f}</td>'
        f'<td>{p.get("total_occupied", 0):,.2f}</td>'
        f'<td>{p.get("headroom", 0):,.2f}</td>'
        f'<td>{p.get("occupancy_rate", 0):.1%}</td>'
        '</tr>'
        for p in warned_pairs
    )

    body = (
        f'<p>The following buyers/pairs exceeded the credit limit warning threshold on {today}:</p>'
        '<p><b>By Buyer:</b></p>'
        '<table border="1" cellpadding="6" cellspacing="0">'
        '<tr><th>Buyer</th><th>Currency</th><th>Celling</th><th>Total Occupied</th>'
        '<th>Headroom</th><th>Occupancy Rate</th></tr>'
        f'{buyer_rows_html}</table>'
        '<p><b>By Buyer-Supplier Pair:</b></p>'
        '<table border="1" cellpadding="6" cellspacing="0">'
        '<tr><th>Buyer</th><th>Supplier</th><th>Currency</th><th>Celling</th>'
        '<th>Total Occupied</th><th>Headroom</th><th>Occupancy Rate</th></tr>'
        f'{pair_rows_html}</table>'
    )

    payload = {
        'type': 'common',
        'title': f'[Refactoring] Credit Limit Warning - {today} ({len(warned_buyers)} buyer(s))',
        'body': body,
    }

    try:
        response = requests.post(email_url, json=payload, timeout=60, verify=False)
        response.raise_for_status()
        logger.info('Credit limit warning email sent, %d buyer(s); response: %s',
                    len(warned_buyers), response.text[:200])
        return True
    except requests.RequestException as e:
        logger.error('Credit limit warning email failed: %s', e)
        raise
```

- [ ] **Step 4: 新增手动触发路由**

在 `backend/app/routes/credit.py` 末尾新增：

```python
@credit_bp.route('/api/trigger-warning-check', methods=['POST'])
@login_required
def trigger_warning_check():
    from backend.app.services.credit_warning_service import run_warning_check_manual
    from flask import jsonify
    result = run_warning_check_manual()
    status_code = 200 if result.get('success') else 500
    return jsonify(result), status_code
```

- [ ] **Step 5: 运行测试确认通过**

Run: `pytest backend/tests/test_credit_warning_service.py -v`
Expected: PASS（全部 11 项通过）

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/credit_warning_service.py backend/app/routes/credit.py \
        backend/tests/test_credit_warning_service.py
git commit -m "feat: 新增每日额度预警定时任务、邮件通知与手动触发端点"
```

---

## Task 7: 注册定时任务 + 全量回归 + 基线文档同步

**Files:**
- Modify: `backend/app/extensions.py:98-110`
- Modify: `docs/system/requirements.md`（第 11 章 额度管理，REQ-CREDIT-001/002 改写 + 新增 REQ-CREDIT-003~006 + 变更记录）
- Modify: `docs/INDEX.md`（如有必要，通常无需改动）

**Interfaces:**
- Consumes: Task 6 的 `register_credit_warning_job(scheduler, app)`。

- [ ] **Step 1: 注册定时任务**

在 `backend/app/extensions.py` 中，紧跟以下已有代码块之后：

```python
            from backend.app.services.onboarding_sync_service import register_onboarding_sync_job
            register_onboarding_sync_job(scheduler, app)
```

新增：

```python
            from backend.app.services.credit_warning_service import register_credit_warning_job
            register_credit_warning_job(scheduler, app)
```

- [ ] **Step 2: 写调度器集成测试**

新建/追加到 `backend/tests/test_credit_warning_service.py` 末尾：

```python
class TestExtensionsRegistersCreditWarningJob:

    def test_extensions_wires_credit_warning_job(self):
        import inspect
        from backend.app.extensions import init_extensions
        source = inspect.getsource(init_extensions)
        assert 'register_credit_warning_job' in source
```

- [ ] **Step 3: 运行测试确认通过**

Run: `pytest backend/tests/test_credit_warning_service.py -v`
Expected: PASS

- [ ] **Step 4: 运行全量回归测试**

Run: `pytest backend/tests/ -v`
Expected: 全部通过，包括 `test_smoke.py`

- [ ] **Step 5: 同步需求基线文档**

在 `docs/system/requirements.md` 第 11 章「额度管理（REQ-CREDIT-xxx）」中：

1. 用本 spec 第一部分「需求 1」「需求 2」「需求 3」的验收标准替换/补充 REQ-CREDIT-001（买方层汇总）、REQ-CREDIT-002（供应商层钻取，标注复用 `/credit/detail`）。
2. 新增 REQ-CREDIT-003（额度数据导出）、REQ-CREDIT-004（每日额度预警），验收标准取自 spec 第一部分「需求 4」「需求 5」。
3. 之前记录的「附：DB Limit 额度报表结构参考」小节标注为已实现，指向本 REQ 条目，或直接删除（其内容已被正式 REQ 取代）。
4. 在文档末尾「15. 变更记录」表格追加一行：

```markdown
| 2026-08-20 | `2026-08-20-credit-limit-management-design.md` | 额度管理重做为买方层汇总+供应商层钻取，新增预占/实占/Celling/Headroom 指标、Excel 导出、每日超阈值邮件预警（REQ-CREDIT-001~004） |
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/extensions.py backend/tests/test_credit_warning_service.py docs/system/requirements.md
git commit -m "feat: 接入每日额度预警定时任务并同步需求基线文档"
```

---

## 任务依赖与并行说明

- Task 1 → Task 2 → Task 3：严格串行（同一文件，函数间存在数据依赖）。
- Task 3 完成后，Task 4（页面路由+模板）、Task 5（导出）、Task 6（预警服务）三者仅依赖 Task 1/2/3 暴露的函数签名（`get_buyer_supplier_pairs`/`aggregate_by_buyer`/`check_warnings`），彼此不修改同一文件的同一区域（Task 4/5/6 都会追加内容到 `backend/app/routes/credit.py`，但各自新增独立函数，冲突面很小），**可并行执行**；若并行执行，建议按 Task 4 → Task 5 → Task 6 顺序合并 `credit.py` 的改动以避免合并冲突，或由执行者协调三次独立的追加式编辑。
- Task 7 依赖 Task 6 的 `register_credit_warning_job`，需在 Task 6 合并后执行。
