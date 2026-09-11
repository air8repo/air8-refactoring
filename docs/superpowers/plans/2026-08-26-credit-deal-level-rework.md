# 额度管理 Deal 层重构 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把预占/实占/待结清下沉到单笔融资单（deal）层统一计算，买卖方层/买方层改为对 deal 层求和；重做额度明细页（新列 + 合计行 + 导出）；额度查询列表导出改为固定的买方/买卖方/Deal 三个 sheet（各自带合计行）。

**Architecture:** 新增银行对账单 `Finance Details - Advance Ratio` 字段导入；`credit_limit_service.py` 新增 `get_deal_rows`/`get_pair_deal_rows`/`compute_deal_totals` 作为唯一计算源，`get_buyer_supplier_pairs` 改为在其上做 groupby-sum；两个页面路由与两处导出都消费这套函数。

**Tech Stack:** Flask, PyMongo（MagicMock 测试）, pandas（导入清洗）, openpyxl, pytest

**Spec:** `docs/superpowers/specs/2026-08-26-credit-deal-level-rework-design.md`

## Global Constraints

- 不修改 `_post_process_financing_records`（`backend/app/services/import_service.py`）中 `bank_finance_status`/`status`/`funded_before`/`settled_in_air8` 等既有衍生字段的计算逻辑与查询范围。
- Deal 层新增的对账单查询（不限 `finance.status`）与 `refactoring_bank_repayment_record` 查询均为只读，不写入/修改任何集合。
- 沿用"实时聚合、不落库"原则，额度模块不新增持久化集合。
- `advance_ratio_pct` 原始值为百分比数字（如 `90` 表示 90%），使用时需 `÷ 100`。
- `get_buyer_supplier_pairs(mongo, buyer_filter=None)` 对外签名与既有返回字段（`uid, buyer_code, buyer_name, supplier_code, supplier_name, currency, celling, reserved, actual, total_occupied, headroom, occupancy_rate, detail_buyer_name, detail_supplier_name, detail_currency`）保持不变，供 `credit_export_service.py`/`credit_warning_service.py`/`routes/credit.py` 既有调用方继续使用。
- `aggregate_by_buyer`/`check_warnings` 函数签名与实现均不改动。
- 每个 task 提交前运行 `"/c/Users/Administrator/AppData/Local/Programs/Python/Python314/python.exe" -m pytest backend/tests/` 确保全部通过（该仓库默认 `python` 无 pytest，必须用这个解释器路径）。

---

## Task 1: 银行对账单新增 Advance Ratio 字段导入

**Files:**
- Modify: `backend/app/services/import_service.py:962-974`（`_import_bank_statement` 的 `finance` 子文档映射）
- Modify: `backend/app/services/cleaning_service.py:187-198`（`clean_bank_statement_data` 数值标准化列表）
- Test: `backend/tests/test_import_bank_settlement.py`（追加）、`backend/tests/test_cleaning_bank_statement.py`（追加）

**Interfaces:**
- Produces: `refactoring_bank_statement.finance.advance_ratio_pct`（`Decimal128`，来源 Excel 列 `Finance Details - Advance Ratio`），供 Task 2 的 deal 层计算读取。

- [ ] **Step 1: 写失败测试 — 导入映射**

追加到 `backend/tests/test_import_bank_settlement.py` 末尾：

```python
def test_advance_ratio_pct_uses_excel_value():
    rows = [{
        'Invoice Details - System InvoiceID': 'INV-10',
        'Finance Details - Tenor': 30,
        'Finance Details - Advance Ratio': 90,
    }]
    inserted = _run_import(rows)
    finance = inserted[0]['finance']
    assert finance['advance_ratio_pct'].to_decimal() == 90


def test_advance_ratio_pct_blank_defaults_to_zero():
    rows = [{
        'Invoice Details - System InvoiceID': 'INV-11',
        'Finance Details - Tenor': 30,
    }]
    inserted = _run_import(rows)
    finance = inserted[0]['finance']
    assert finance['advance_ratio_pct'].to_decimal() == 0
```

（`_run_import` 辅助函数已存在于该测试文件顶部，直接复用；`to_decimal` 辅助对缺失值的既有行为是返回 `Decimal128('0')`，与其他百分比字段一致，因此第二个测试断言为 `0` 而不是 `None`。）

追加到 `backend/tests/test_cleaning_bank_statement.py` 末尾：

```python
def test_advance_ratio_is_normalized_to_numeric():
    df = pd.DataFrame([
        {'Invoice Details - System InvoiceID': 'INV-1',
         'Finance Details - Advance Ratio': '90'},
    ])
    out = CleaningService().clean_bank_statement_data(df)
    assert out['Finance Details - Advance Ratio'].iloc[0] == 90.0
```

- [ ] **Step 2: 运行测试确认失败**

Run: `"/c/Users/Administrator/AppData/Local/Programs/Python/Python314/python.exe" -m pytest backend/tests/test_import_bank_settlement.py::test_advance_ratio_pct_uses_excel_value backend/tests/test_import_bank_settlement.py::test_advance_ratio_pct_blank_defaults_to_zero backend/tests/test_cleaning_bank_statement.py::test_advance_ratio_is_normalized_to_numeric -v`
Expected: FAIL（`KeyError: 'advance_ratio_pct'` 或断言值不匹配，因为字段尚未映射；清洗测试因列未被转换为数值类型而失败——若原始输入本就是字符串 `'90'`，`out[...].iloc[0]` 会是字符串 `'90'` 而非 `90.0`）

- [ ] **Step 3: 实现**

在 `backend/app/services/import_service.py` 的 `finance` 子文档字典中（紧跟 `'purchase_price': to_decimal(row.get('Finance Details - Purchase Price'))` 之后）新增一行：

```python
                    'purchase_price': to_decimal(row.get('Finance Details - Purchase Price')),
                    'advance_ratio_pct': to_decimal(row.get('Finance Details - Advance Ratio'))
```

（注意原第 973 行末尾的逗号需要保留，新增字段作为最后一项不加逗号，或按需调整——保持字典语法正确即可。）

在 `backend/app/services/cleaning_service.py` 的 `numeric_fields` 列表中加入新列：

```python
        numeric_fields = [
            'Invoice Details - Original Amount', 'Finance Details - Finance Amount',
            'Finance Details - Outstanding Amount', 'Finance Details - Reference Rate %',
            'Finance Details - Interest Rate %', 'Finance Details - Interest Amount',
            'Finance Details - Purchase Price', 'Finance Details - Advance Ratio',
            'EUR - Original Amount (EUR)',
            'EUR - Finance Amount (EUR)', 'EUR - Outstanding Amount (EUR)',
            'EUR - Interest Amount (EUR)', 'EUR - Purchase Price (EUR)',
            'USD - Original Amount (USD)', 'USD - Finance Amount (USD)',
            'USD - Outstanding Amount (USD)', 'USD - Interest Amount (USD)',
            'USD - Purchase Price (USD)', 'Invoice Details - VAT Rate',
            'Invoice Details - VAT Amount'
        ]
```

- [ ] **Step 4: 运行测试确认通过**

Run: `"/c/Users/Administrator/AppData/Local/Programs/Python/Python314/python.exe" -m pytest backend/tests/test_import_bank_settlement.py backend/tests/test_cleaning_bank_statement.py -v`
Expected: PASS（全部通过，含新增 3 项）

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/import_service.py backend/app/services/cleaning_service.py \
        backend/tests/test_import_bank_settlement.py backend/tests/test_cleaning_bank_statement.py
git commit -m "feat: 银行对账单导入新增 Advance Ratio 字段"
```

---

## Task 2: Deal 层核心计算（`get_deal_rows` / `get_pair_deal_rows` / `compute_deal_totals`）

**Files:**
- Modify: `backend/app/services/credit_limit_service.py`（新增函数，暂不改动 `get_buyer_supplier_pairs`/`aggregate_by_buyer`/`check_warnings`）
- Test: `backend/tests/test_credit_limit_service.py`（新增测试类）

**Interfaces:**
- Consumes: `mongo.refactoring_onboard_config`、`mongo.refactoring_financing_order`、`mongo.refactoring_bank_statement`、`mongo.refactoring_bank_repayment_record`（均为只读 `find`）。
- Produces:
  - `get_deal_rows(mongo, buyer_filter=None) -> list[dict]`：每个 dict 含 `uid, buyer_code, buyer_name, supplier_code, supplier_name, currency, finance_request_number, invoice_number, financing_amount, earmark_forecast, credit_utilization, to_be_settled_on_db, total_os, status, status_display, finance_status_display, settlement_status, due_date, actual_funding_date, batch_number, detail_buyer_name, detail_supplier_name, detail_currency`。
  - `get_pair_deal_rows(mongo, buyer_name, supplier_name, financing_currency) -> list[dict]`：字段同上，按精确匹配查询（供 Task 4 明细页使用）。
  - `compute_deal_totals(deal_rows) -> dict`：`{'financing_amount', 'earmark_forecast', 'credit_utilization', 'to_be_settled_on_db', 'total_os'}` 五个数值之和（供 Task 4/5 的合计行使用）。
  - 内部私有函数 `_build_deal_row(fo, onboard, bs, repay)`、`_fetch_bank_statements_by_invoice(mongo, financing_orders)`、`_fetch_latest_repayment_by_fr(mongo, financing_orders)`（Task 3 会复用 `_fetch_bank_statements_by_invoice`/`_fetch_latest_repayment_by_fr`/`_build_deal_row`，但不直接测试这些私有函数——通过 `get_deal_rows`/`get_pair_deal_rows` 的行为测试覆盖）。

- [ ] **Step 1: 写失败测试**

追加到 `backend/tests/test_credit_limit_service.py` 末尾（`_make_mongo` 辅助函数已存在于文件顶部，需要扩展支持 `repayment_records` 参数——见 Step 1b）：

```python
def _make_mongo_with_repayments(onboard_configs=None, financing_orders=None,
                                 bank_statements=None, repayment_records=None):
    mongo = MagicMock()
    mongo.refactoring_onboard_config.find.return_value = onboard_configs or []
    mongo.refactoring_financing_order.find.return_value = financing_orders or []
    mongo.refactoring_bank_statement.find.return_value = bank_statements or []
    mongo.refactoring_bank_repayment_record.find.return_value = repayment_records or []
    return mongo


class TestGetDealRows:

    def test_financing_amount_uses_bank_statement_when_matched(self):
        from backend.app.services.credit_limit_service import get_deal_rows
        mongo = _make_mongo_with_repayments(
            financing_orders=[
                {'uid': 'U1', 'buyer_code': 'B1', 'buyer_name': 'Buyer One',
                 'supplier_code': 'S1', 'supplier_name': 'Seller One',
                 'finance_request_number': 'FR1', 'invoice_number': 'INV1',
                 'financing_amount': 1000, 'status': 'eligible',
                 'bank_finance_status': '', 'financing_currency': 'USD'},
            ],
            bank_statements=[
                {'invoice': {'seller_reference': 'INV1', 'original_amount': 2000, 'settlement_status': ''},
                 'finance': {'advance_ratio_pct': 90, 'status': 'Booking requested accepted'}},
            ],
        )
        deals = get_deal_rows(mongo)
        assert len(deals) == 1
        d = deals[0]
        assert d['financing_amount'] == 1800  # 2000 * 90 / 100
        assert d['earmark_forecast'] == 1800
        assert d['credit_utilization'] == 0
        assert d['finance_status_display'] == 'Booking requested accepted'
        assert d['settlement_status'] == ''

    def test_financing_amount_falls_back_to_financing_order_when_no_bank_statement(self):
        from backend.app.services.credit_limit_service import get_deal_rows
        mongo = _make_mongo_with_repayments(
            financing_orders=[
                {'uid': 'U1', 'buyer_code': 'B1', 'buyer_name': 'Buyer One',
                 'finance_request_number': 'FR1', 'invoice_number': 'INV1',
                 'financing_amount': 1000, 'status': 'eligible', 'bank_finance_status': ''},
            ],
        )
        deals = get_deal_rows(mongo)
        assert deals[0]['financing_amount'] == 1000
        assert deals[0]['earmark_forecast'] == 1000
        assert deals[0]['finance_status_display'] == ''
        assert deals[0]['settlement_status'] == ''

    def test_earmark_forecast_zero_when_not_eligible(self):
        from backend.app.services.credit_limit_service import get_deal_rows
        mongo = _make_mongo_with_repayments(
            financing_orders=[
                {'uid': 'U1', 'buyer_code': 'B1', 'buyer_name': 'Buyer One',
                 'finance_request_number': 'FR1', 'invoice_number': 'INV1',
                 'financing_amount': 1000, 'status': 'funded before', 'bank_finance_status': ''},
            ],
        )
        deals = get_deal_rows(mongo)
        assert deals[0]['earmark_forecast'] == 0
        assert deals[0]['status_display'] == 'Funded Successfully'

    def test_credit_utilization_uses_financing_amount_when_loan_booked(self):
        from backend.app.services.credit_limit_service import get_deal_rows
        mongo = _make_mongo_with_repayments(
            financing_orders=[
                {'uid': 'U1', 'buyer_code': 'B1', 'buyer_name': 'Buyer One',
                 'finance_request_number': 'FR1', 'invoice_number': 'INV1',
                 'financing_amount': 1000, 'status': 'funded before',
                 'bank_finance_status': 'Loan booked'},
            ],
            bank_statements=[
                {'invoice': {'seller_reference': 'INV1', 'original_amount': 2000},
                 'finance': {'advance_ratio_pct': 90, 'status': 'Loan booked'}},
            ],
        )
        deals = get_deal_rows(mongo)
        d = deals[0]
        assert d['earmark_forecast'] == 0
        assert d['credit_utilization'] == 1800
        assert d['total_os'] == 1800

    def test_to_be_settled_on_db_requires_settled_in_air8_and_loan_booked(self):
        from backend.app.services.credit_limit_service import get_deal_rows
        mongo = _make_mongo_with_repayments(
            financing_orders=[
                {'uid': 'U1', 'buyer_code': 'B1', 'buyer_name': 'Buyer One',
                 'finance_request_number': 'FR1', 'invoice_number': 'INV1',
                 'financing_amount': 1000, 'status': 'funded before',
                 'bank_finance_status': 'Loan booked', 'settled_in_air8': 'Settled'},
            ],
            bank_statements=[
                {'invoice': {'seller_reference': 'INV1', 'original_amount': 2000},
                 'finance': {'advance_ratio_pct': 90, 'status': 'Loan booked'}},
            ],
            repayment_records=[
                {'finance_request_number': 'FR1', 'settlement_amount': 1800,
                 'created_at': None},
            ],
        )
        deals = get_deal_rows(mongo)
        d = deals[0]
        assert d['credit_utilization'] == 1800
        assert d['to_be_settled_on_db'] == 1800
        assert d['total_os'] == 0  # 1800(实占) - 1800(待结清) = 0，对冲

    def test_to_be_settled_on_db_none_when_not_loan_booked(self):
        from backend.app.services.credit_limit_service import get_deal_rows
        mongo = _make_mongo_with_repayments(
            financing_orders=[
                {'uid': 'U1', 'buyer_code': 'B1', 'buyer_name': 'Buyer One',
                 'finance_request_number': 'FR1', 'invoice_number': 'INV1',
                 'financing_amount': 1000, 'status': 'funded before',
                 'bank_finance_status': '', 'settled_in_air8': 'Settled'},
            ],
            repayment_records=[
                {'finance_request_number': 'FR1', 'settlement_amount': 1000, 'created_at': None},
            ],
        )
        deals = get_deal_rows(mongo)
        assert deals[0]['to_be_settled_on_db'] is None
        assert deals[0]['total_os'] == 0

    def test_to_be_settled_on_db_none_when_settlement_amount_not_numeric(self):
        from backend.app.services.credit_limit_service import get_deal_rows
        mongo = _make_mongo_with_repayments(
            financing_orders=[
                {'uid': 'U1', 'buyer_code': 'B1', 'buyer_name': 'Buyer One',
                 'finance_request_number': 'FR1', 'invoice_number': 'INV1',
                 'financing_amount': 1000, 'status': 'funded before',
                 'bank_finance_status': 'Loan booked', 'settled_in_air8': 'Settled'},
            ],
            repayment_records=[
                {'finance_request_number': 'FR1', 'settlement_amount': 'Pending for settlement',
                 'created_at': None},
            ],
        )
        deals = get_deal_rows(mongo)
        assert deals[0]['to_be_settled_on_db'] is None

    def test_to_be_settled_on_db_picks_latest_created_at_when_duplicates(self):
        from datetime import datetime
        from backend.app.services.credit_limit_service import get_deal_rows
        mongo = _make_mongo_with_repayments(
            financing_orders=[
                {'uid': 'U1', 'buyer_code': 'B1', 'buyer_name': 'Buyer One',
                 'finance_request_number': 'FR1', 'invoice_number': 'INV1',
                 'financing_amount': 1000, 'status': 'funded before',
                 'bank_finance_status': 'Loan booked', 'settled_in_air8': 'Settled'},
            ],
            repayment_records=[
                {'finance_request_number': 'FR1', 'settlement_amount': 100,
                 'created_at': datetime(2026, 1, 1)},
                {'finance_request_number': 'FR1', 'settlement_amount': 999,
                 'created_at': datetime(2026, 6, 1)},
            ],
        )
        deals = get_deal_rows(mongo)
        assert deals[0]['to_be_settled_on_db'] == 999

    def test_buyer_name_prefers_onboard_config(self):
        from backend.app.services.credit_limit_service import get_deal_rows
        mongo = _make_mongo_with_repayments(
            onboard_configs=[{'uid': 'U1', 'obligor_name': 'Amazon.com Services LLC',
                               'seller_name': 'Photonverse Inc', 'buyer_code': 'B1', 'supplier_code': 'S1'}],
            financing_orders=[
                {'uid': 'U1', 'buyer_name': 'AMAZON.COM SERVICES LLC ', 'supplier_name': 'PHOTONVERSE, INC.',
                 'financing_currency': 'usd', 'finance_request_number': 'FR1', 'invoice_number': 'INV1',
                 'financing_amount': 1000, 'status': 'eligible', 'bank_finance_status': ''},
            ],
        )
        deals = get_deal_rows(mongo)
        d = deals[0]
        assert d['buyer_name'] == 'Amazon.com Services LLC'
        assert d['supplier_name'] == 'Photonverse Inc'
        assert d['currency'] == 'USD'
        assert d['detail_buyer_name'] == 'AMAZON.COM SERVICES LLC '
        assert d['detail_supplier_name'] == 'PHOTONVERSE, INC.'
        assert d['detail_currency'] == 'usd'

    def test_buyer_filter_matches_case_insensitively(self):
        from backend.app.services.credit_limit_service import get_deal_rows
        mongo = _make_mongo_with_repayments(
            financing_orders=[
                {'uid': 'U1', 'buyer_name': 'Amazon Services', 'finance_request_number': 'FR1',
                 'invoice_number': 'INV1', 'financing_amount': 1000, 'status': 'eligible',
                 'bank_finance_status': ''},
                {'uid': 'U2', 'buyer_name': 'Homegoods Inc', 'finance_request_number': 'FR2',
                 'invoice_number': 'INV2', 'financing_amount': 500, 'status': 'eligible',
                 'bank_finance_status': ''},
            ],
        )
        deals = get_deal_rows(mongo, buyer_filter='amazon')
        assert len(deals) == 1
        assert deals[0]['buyer_name'] == 'Amazon Services'

    def test_records_without_uid_are_skipped(self):
        from backend.app.services.credit_limit_service import get_deal_rows
        mongo = _make_mongo_with_repayments(
            financing_orders=[
                {'buyer_name': 'No UID Buyer', 'finance_request_number': 'FR1',
                 'invoice_number': 'INV1', 'financing_amount': 1000, 'status': 'eligible',
                 'bank_finance_status': ''},
            ],
        )
        deals = get_deal_rows(mongo)
        assert deals == []


class TestGetPairDealRows:

    def test_filters_by_exact_buyer_supplier_currency(self):
        from backend.app.services.credit_limit_service import get_pair_deal_rows
        mongo = _make_mongo_with_repayments()
        mongo.refactoring_financing_order.find.return_value = [
            {'uid': 'U1', 'buyer_name': 'Buyer One', 'supplier_name': 'Seller One',
             'financing_currency': 'USD', 'finance_request_number': 'FR1', 'invoice_number': 'INV1',
             'financing_amount': 1000, 'status': 'eligible', 'bank_finance_status': ''},
        ]
        deals = get_pair_deal_rows(mongo, 'Buyer One', 'Seller One', 'USD')
        assert len(deals) == 1
        mongo.refactoring_financing_order.find.assert_called_once_with({
            'buyer_name': 'Buyer One', 'supplier_name': 'Seller One', 'financing_currency': 'USD',
        })


class TestComputeDealTotals:

    def test_sums_the_five_numeric_columns(self):
        from backend.app.services.credit_limit_service import compute_deal_totals
        deals = [
            {'financing_amount': 100, 'earmark_forecast': 100, 'credit_utilization': 0,
             'to_be_settled_on_db': None, 'total_os': 100},
            {'financing_amount': 200, 'earmark_forecast': 0, 'credit_utilization': 200,
             'to_be_settled_on_db': 50, 'total_os': 150},
        ]
        totals = compute_deal_totals(deals)
        assert totals == {
            'financing_amount': 300, 'earmark_forecast': 100, 'credit_utilization': 200,
            'to_be_settled_on_db': 50, 'total_os': 250,
        }

    def test_empty_list_returns_zeros(self):
        from backend.app.services.credit_limit_service import compute_deal_totals
        assert compute_deal_totals([]) == {
            'financing_amount': 0, 'earmark_forecast': 0, 'credit_utilization': 0,
            'to_be_settled_on_db': 0, 'total_os': 0,
        }
```

- [ ] **Step 2: 运行测试确认失败**

Run: `"/c/Users/Administrator/AppData/Local/Programs/Python/Python314/python.exe" -m pytest backend/tests/test_credit_limit_service.py -k "TestGetDealRows or TestGetPairDealRows or TestComputeDealTotals" -v`
Expected: FAIL，`ImportError: cannot import name 'get_deal_rows'`

- [ ] **Step 3: 实现**

在 `backend/app/services/credit_limit_service.py` 顶部 import 之后新增：

```python
from datetime import datetime
```

在文件末尾（`check_warnings` 函数之后）追加：

```python
def _fetch_bank_statements_by_invoice(mongo, financing_orders):
    """按 invoice_number 批量取对账单，不限 finance.status。"""
    invoice_numbers = [fo.get('invoice_number') for fo in financing_orders if fo.get('invoice_number')]
    bank_statements = []
    if invoice_numbers:
        bank_statements = list(mongo.refactoring_bank_statement.find(
            {'invoice.seller_reference': {'$in': invoice_numbers}}
        ))
    result = {}
    for bs in bank_statements:
        ref = (bs.get('invoice') or {}).get('seller_reference')
        if ref:
            result[ref] = bs
    return result


def _fetch_latest_repayment_by_fr(mongo, financing_orders):
    """按 finance_request_number 批量取还款记录，多条时取 created_at 最新一条。"""
    fr_numbers = [fo.get('finance_request_number') for fo in financing_orders if fo.get('finance_request_number')]
    repayment_records = []
    if fr_numbers:
        repayment_records = list(mongo.refactoring_bank_repayment_record.find(
            {'finance_request_number': {'$in': fr_numbers}}
        ))
    by_fr = {}
    for rec in repayment_records:
        fr = rec.get('finance_request_number')
        if fr:
            by_fr.setdefault(fr, []).append(rec)
    result = {}
    for fr, records in by_fr.items():
        result[fr] = max(records, key=lambda r: r.get('created_at') or datetime.min)
    return result


def _build_deal_row(fo, onboard, bs, repay):
    """计算单笔融资单(deal)的 Financing Amount / 预占 / 实占 / 待结清 / Total O/S。"""
    invoice_number = fo.get('invoice_number')

    if bs is not None:
        original_amount = _to_float((bs.get('invoice') or {}).get('original_amount')) or 0.0
        advance_ratio_pct = _to_float((bs.get('finance') or {}).get('advance_ratio_pct'))
        financing_amount = original_amount * (advance_ratio_pct / 100) if advance_ratio_pct is not None else 0.0
    else:
        financing_amount = _to_float(fo.get('financing_amount')) or 0.0

    status = fo.get('status') or ''
    bank_finance_status = fo.get('bank_finance_status')
    settled_in_air8 = fo.get('settled_in_air8')

    earmark_forecast = financing_amount if status == 'eligible' and bank_finance_status != 'Loan booked' else 0.0
    credit_utilization = financing_amount if bank_finance_status == 'Loan booked' else 0.0

    to_be_settled_on_db = None
    if settled_in_air8 == 'Settled' and bank_finance_status == 'Loan booked' and repay is not None:
        settlement_amount = _to_float(repay.get('settlement_amount'))
        if settlement_amount is not None:
            to_be_settled_on_db = settlement_amount

    total_os = round(earmark_forecast + credit_utilization - (to_be_settled_on_db or 0.0), 2)

    return {
        'uid': fo.get('uid', ''),
        'buyer_code': onboard.get('buyer_code') or fo.get('buyer_code') or '',
        'buyer_name': onboard.get('obligor_name') or fo.get('buyer_name') or '',
        'supplier_code': onboard.get('supplier_code') or fo.get('supplier_code') or '',
        'supplier_name': onboard.get('seller_name') or fo.get('supplier_name') or '',
        'currency': 'USD',
        'finance_request_number': fo.get('finance_request_number', ''),
        'invoice_number': invoice_number or '',
        'financing_amount': round(financing_amount, 2),
        'earmark_forecast': round(earmark_forecast, 2),
        'credit_utilization': round(credit_utilization, 2),
        'to_be_settled_on_db': round(to_be_settled_on_db, 2) if to_be_settled_on_db is not None else None,
        'total_os': total_os,
        'status': status,
        'status_display': 'Funded Successfully' if status == 'funded before' else status,
        'finance_status_display': (bs.get('finance') or {}).get('status', '') if bs is not None else '',
        'settlement_status': (bs.get('invoice') or {}).get('settlement_status', '') if bs is not None else '',
        'due_date': fo.get('due_date'),
        'actual_funding_date': fo.get('actual_funding_date'),
        'batch_number': fo.get('batch_number', ''),
        'detail_buyer_name': fo.get('buyer_name') or '',
        'detail_supplier_name': fo.get('supplier_name') or '',
        'detail_currency': fo.get('financing_currency') or '',
    }


def get_deal_rows(mongo, buyer_filter=None):
    """按融资单(deal)实时计算 Financing Amount/预占/实占/待结清/Total O/S。"""
    onboard_configs = list(mongo.refactoring_onboard_config.find())
    onboard_by_uid = {c.get('uid'): c for c in onboard_configs if c.get('uid')}

    financing_orders = list(mongo.refactoring_financing_order.find())
    bs_by_invoice = _fetch_bank_statements_by_invoice(mongo, financing_orders)
    repay_by_fr = _fetch_latest_repayment_by_fr(mongo, financing_orders)

    deals = []
    for fo in financing_orders:
        uid = fo.get('uid')
        if not uid:
            continue
        onboard = onboard_by_uid.get(uid, {})
        bs = bs_by_invoice.get(fo.get('invoice_number'))
        repay = repay_by_fr.get(fo.get('finance_request_number'))
        deals.append(_build_deal_row(fo, onboard, bs, repay))

    if buyer_filter:
        needle = buyer_filter.strip().lower()
        deals = [d for d in deals if needle in (d['buyer_name'] or '').lower()]

    return deals


def get_pair_deal_rows(mongo, buyer_name, supplier_name, financing_currency):
    """按买方/卖方/币种精确匹配，返回该买卖方配对下全部融资单的 deal 层数据（供 /credit/detail 使用）。"""
    onboard_configs = list(mongo.refactoring_onboard_config.find())
    onboard_by_uid = {c.get('uid'): c for c in onboard_configs if c.get('uid')}

    financing_orders = list(mongo.refactoring_financing_order.find({
        'buyer_name': buyer_name,
        'supplier_name': supplier_name,
        'financing_currency': financing_currency,
    }))
    bs_by_invoice = _fetch_bank_statements_by_invoice(mongo, financing_orders)
    repay_by_fr = _fetch_latest_repayment_by_fr(mongo, financing_orders)

    deals = []
    for fo in financing_orders:
        uid = fo.get('uid')
        onboard = onboard_by_uid.get(uid, {}) if uid else {}
        bs = bs_by_invoice.get(fo.get('invoice_number'))
        repay = repay_by_fr.get(fo.get('finance_request_number'))
        deals.append(_build_deal_row(fo, onboard, bs, repay))

    return deals


def compute_deal_totals(deal_rows):
    """对 deal 行的 5 个数值列求和，供页面/导出的合计行使用。"""
    return {
        'financing_amount': round(sum(d.get('financing_amount') or 0 for d in deal_rows), 2),
        'earmark_forecast': round(sum(d.get('earmark_forecast') or 0 for d in deal_rows), 2),
        'credit_utilization': round(sum(d.get('credit_utilization') or 0 for d in deal_rows), 2),
        'to_be_settled_on_db': round(sum(d.get('to_be_settled_on_db') or 0 for d in deal_rows), 2),
        'total_os': round(sum(d.get('total_os') or 0 for d in deal_rows), 2),
    }
```

- [ ] **Step 4: 运行测试确认通过**

Run: `"/c/Users/Administrator/AppData/Local/Programs/Python/Python314/python.exe" -m pytest backend/tests/test_credit_limit_service.py -v`
Expected: PASS（新增全部通过；此时 `TestGetBuyerSupplierPairs` 等既有测试类应仍然通过——本 task 未改动 `get_buyer_supplier_pairs`）

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/credit_limit_service.py backend/tests/test_credit_limit_service.py
git commit -m "feat: 新增 Deal 层统一计算(get_deal_rows/get_pair_deal_rows/compute_deal_totals)"
```

---

## Task 3: `get_buyer_supplier_pairs` 改为对 Deal 层求和

**Files:**
- Modify: `backend/app/services/credit_limit_service.py`（替换 `get_buyer_supplier_pairs` 函数体；删除 `_ACTUAL_OUTSTANDING_RATIO` 常量）
- Modify: `backend/tests/test_credit_limit_service.py`（替换 `TestGetBuyerSupplierPairs` 类内容）

**Interfaces:**
- Consumes: Task 2 的 `get_deal_rows(mongo)`。
- Produces: `get_buyer_supplier_pairs(mongo, buyer_filter=None)`，返回字段与签名保持既有约定不变（见 Global Constraints）。

- [ ] **Step 1: 替换失败测试**

在 `backend/tests/test_credit_limit_service.py` 中，删除整个 `class TestGetBuyerSupplierPairs:` 及其全部方法（从 `class TestGetBuyerSupplierPairs:` 开始到 `class TestToFloat:` 之前结束）。同时删除文件顶部（Task 1 之前就存在的）旧的 `_make_mongo(onboard_configs=None, financing_orders=None, bank_statements=None)` 辅助函数——它只被刚删除的旧 `TestGetBuyerSupplierPairs` 测试使用，替换后的新测试类统一使用 Task 2 新增的 `_make_mongo_with_repayments`，留着旧函数会变成未使用的死代码。删除后的位置替换为：

```python
class TestGetBuyerSupplierPairs:

    def test_pair_sums_earmark_and_utilization_from_deals(self):
        from backend.app.services.credit_limit_service import get_buyer_supplier_pairs
        mongo = _make_mongo_with_repayments(
            onboard_configs=[{'uid': 'U1', 'refactoring_limit': 100000, 'buyer_code': 'B1',
                               'obligor_name': 'Buyer One', 'supplier_code': 'S1', 'seller_name': 'Seller One'}],
            financing_orders=[
                {'uid': 'U1', 'buyer_code': 'B1', 'supplier_code': 'S1', 'buyer_name': 'Buyer One',
                 'supplier_name': 'Seller One', 'finance_request_number': 'FR1', 'invoice_number': 'INV1',
                 'financing_amount': 1000, 'status': 'eligible', 'bank_finance_status': ''},
                {'uid': 'U1', 'buyer_code': 'B1', 'supplier_code': 'S1', 'buyer_name': 'Buyer One',
                 'supplier_name': 'Seller One', 'finance_request_number': 'FR2', 'invoice_number': 'INV2',
                 'financing_amount': 2000, 'status': 'funded before', 'bank_finance_status': 'Loan booked'},
            ],
        )
        pairs = get_buyer_supplier_pairs(mongo)
        assert len(pairs) == 1
        p = pairs[0]
        assert p['uid'] == 'U1'
        assert p['reserved'] == 1000
        assert p['actual'] == 2000
        assert p['total_occupied'] == 3000
        assert p['celling'] == 100000
        assert p['headroom'] == 97000
        assert abs(p['occupancy_rate'] - 0.03) < 1e-9

    def test_total_occupied_subtracts_to_be_settled_on_db(self):
        from backend.app.services.credit_limit_service import get_buyer_supplier_pairs
        mongo = _make_mongo_with_repayments(
            onboard_configs=[{'uid': 'U1', 'refactoring_limit': 100000, 'buyer_code': 'B1',
                               'obligor_name': 'Buyer One'}],
            financing_orders=[
                {'uid': 'U1', 'buyer_code': 'B1', 'buyer_name': 'Buyer One',
                 'finance_request_number': 'FR1', 'invoice_number': 'INV1',
                 'financing_amount': 1000, 'status': 'funded before',
                 'bank_finance_status': 'Loan booked', 'settled_in_air8': 'Settled'},
            ],
            repayment_records=[
                {'finance_request_number': 'FR1', 'settlement_amount': 400, 'created_at': None},
            ],
        )
        pairs = get_buyer_supplier_pairs(mongo)
        p = pairs[0]
        assert p['actual'] == 1000
        assert p['total_occupied'] == 600  # 0(预占) + 1000(实占) - 400(待结清)

    def test_onboard_only_uid_has_zero_occupied_and_full_headroom(self):
        from backend.app.services.credit_limit_service import get_buyer_supplier_pairs
        mongo = _make_mongo_with_repayments(
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

    def test_deal_only_uid_has_none_headroom_and_occupancy(self):
        from backend.app.services.credit_limit_service import get_buyer_supplier_pairs
        mongo = _make_mongo_with_repayments(
            financing_orders=[
                {'uid': 'U3', 'buyer_code': 'B3', 'buyer_name': 'Buyer Three',
                 'finance_request_number': 'FR1', 'invoice_number': 'INV3',
                 'financing_amount': 500, 'status': 'eligible', 'bank_finance_status': ''},
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
        mongo = _make_mongo_with_repayments(
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
        mongo = _make_mongo_with_repayments(
            onboard_configs=[{'uid': 'U1', 'refactoring_limit': 0, 'buyer_code': 'B1',
                               'obligor_name': 'Buyer One', 'target_list_status': 'N'}],
        )
        pairs = get_buyer_supplier_pairs(mongo)
        assert len(pairs) == 1
        assert pairs[0]['uid'] == 'U1'

    def test_currency_is_always_usd(self):
        from backend.app.services.credit_limit_service import get_buyer_supplier_pairs
        mongo = _make_mongo_with_repayments(onboard_configs=[{'uid': 'U1', 'refactoring_limit': 1000, 'buyer_code': 'B1'}])
        pairs = get_buyer_supplier_pairs(mongo)
        assert pairs[0]['currency'] == 'USD'

    def test_detail_fields_carry_raw_financing_order_identifiers(self):
        from backend.app.services.credit_limit_service import get_buyer_supplier_pairs
        mongo = _make_mongo_with_repayments(
            onboard_configs=[{'uid': 'U1', 'refactoring_limit': 100000, 'buyer_code': 'B1',
                               'obligor_name': 'Amazon.com Services LLC', 'seller_name': 'Photonverse Inc'}],
            financing_orders=[
                {'uid': 'U1', 'buyer_code': 'B1', 'buyer_name': 'AMAZON.COM SERVICES LLC ',
                 'supplier_name': 'PHOTONVERSE, INC.', 'financing_currency': 'usd',
                 'finance_request_number': 'FR1', 'invoice_number': 'INV1',
                 'financing_amount': 1000, 'status': 'eligible', 'bank_finance_status': ''},
            ],
        )
        pairs = get_buyer_supplier_pairs(mongo)
        p = pairs[0]
        assert p['buyer_name'] == 'Amazon.com Services LLC'
        assert p['supplier_name'] == 'Photonverse Inc'
        assert p['currency'] == 'USD'
        assert p['detail_buyer_name'] == 'AMAZON.COM SERVICES LLC '
        assert p['detail_supplier_name'] == 'PHOTONVERSE, INC.'
        assert p['detail_currency'] == 'usd'

    def test_reserved_bucket_excludes_orders_not_eligible(self):
        from backend.app.services.credit_limit_service import get_buyer_supplier_pairs
        mongo = _make_mongo_with_repayments(
            onboard_configs=[{'uid': 'U1', 'refactoring_limit': 100000, 'buyer_code': 'B1',
                               'obligor_name': 'Buyer One'}],
            financing_orders=[
                {'uid': 'U1', 'buyer_code': 'B1', 'buyer_name': 'Buyer One',
                 'finance_request_number': 'FR1', 'invoice_number': 'INV1',
                 'financing_amount': 1000, 'status': 'partial paid', 'bank_finance_status': ''},
            ],
        )
        pairs = get_buyer_supplier_pairs(mongo)
        assert pairs[0]['reserved'] == 0
        assert pairs[0]['total_occupied'] == 0
```

（这个新测试类保留了原有测试类里仍然有效的场景——onboard-only 全外连接、buyer_filter、target_list_status='N'、currency 恒为 USD、detail_* 字段——但把预占/实占的断言改为对 deal 层求和的新口径；不再需要 `_make_mongo` 辅助函数处理 `bank_statements` 参数缺 `repayment_records` 的旧签名，统一改用 Task 2 新增的 `_make_mongo_with_repayments`。）

- [ ] **Step 2: 运行测试确认失败**

Run: `"/c/Users/Administrator/AppData/Local/Programs/Python/Python314/python.exe" -m pytest backend/tests/test_credit_limit_service.py::TestGetBuyerSupplierPairs -v`
Expected: FAIL（新断言与旧实现的公式不匹配——例如 `test_total_occupied_subtracts_to_be_settled_on_db` 会失败，因为旧实现里 `total_occupied` 就是简单的 `r+a`）

- [ ] **Step 3: 实现**

在 `backend/app/services/credit_limit_service.py` 中：

1. 删除文件顶部的：
```python
# 实占按 DB 实际占用额度上限的比例折算（固定 90%，所有买卖方统一，不区分 advance_ratio）
_ACTUAL_OUTSTANDING_RATIO = 0.9
```

2. 用以下内容整体替换现有的 `get_buyer_supplier_pairs` 函数（从 `def get_buyer_supplier_pairs(mongo, buyer_filter=None):` 到该函数末尾的 `return pairs`）：

```python
def get_buyer_supplier_pairs(mongo, buyer_filter=None):
    """按买卖方配对(uid)对 get_deal_rows 的结果求和：预占、实占、待结清、Total O/S。

    Celling: refactoring_onboard_config.refactoring_limit（按 uid）
    预占/实占/待结清/Total O/S：对该 uid 下全部 deal（见 get_deal_rows）逐项求和
    """
    onboard_configs = list(mongo.refactoring_onboard_config.find())
    onboard_by_uid = {c.get('uid'): c for c in onboard_configs if c.get('uid')}

    deals = get_deal_rows(mongo)

    reserved = {}
    actual = {}
    settled = {}
    deal_buyer_code = {}
    deal_buyer_name = {}
    deal_supplier_code = {}
    deal_supplier_name = {}
    deal_detail_buyer_name = {}
    deal_detail_supplier_name = {}
    deal_detail_currency = {}

    for d in deals:
        uid = d['uid']
        reserved[uid] = reserved.get(uid, 0.0) + d['earmark_forecast']
        actual[uid] = actual.get(uid, 0.0) + d['credit_utilization']
        settled[uid] = settled.get(uid, 0.0) + (d['to_be_settled_on_db'] or 0.0)
        deal_buyer_code.setdefault(uid, d['buyer_code'])
        deal_buyer_name.setdefault(uid, d['buyer_name'])
        deal_supplier_code.setdefault(uid, d['supplier_code'])
        deal_supplier_name.setdefault(uid, d['supplier_name'])
        deal_detail_buyer_name.setdefault(uid, d['detail_buyer_name'])
        deal_detail_supplier_name.setdefault(uid, d['detail_supplier_name'])
        deal_detail_currency.setdefault(uid, d['detail_currency'])

    all_uids = set(onboard_by_uid.keys()) | set(deal_buyer_name.keys())

    pairs = []
    for uid in all_uids:
        onboard = onboard_by_uid.get(uid, {})
        celling = _to_float(onboard.get('refactoring_limit')) or 0.0
        r = round(reserved.get(uid, 0.0), 2)
        a = round(actual.get(uid, 0.0), 2)
        s = round(settled.get(uid, 0.0), 2)
        total = round(r + a - s, 2)

        if celling > 0:
            headroom = round(celling - total, 2)
            occupancy_rate = round(total / celling, 4)
        else:
            headroom = None
            occupancy_rate = None

        pairs.append({
            'uid': uid,
            'buyer_code': onboard.get('buyer_code') or deal_buyer_code.get(uid, ''),
            'buyer_name': onboard.get('obligor_name') or deal_buyer_name.get(uid, ''),
            'supplier_code': onboard.get('supplier_code') or deal_supplier_code.get(uid, ''),
            'supplier_name': onboard.get('seller_name') or deal_supplier_name.get(uid, ''),
            'currency': 'USD',
            'celling': celling,
            'reserved': r,
            'actual': a,
            'total_occupied': total,
            'headroom': headroom,
            'occupancy_rate': occupancy_rate,
            'detail_buyer_name': deal_detail_buyer_name.get(uid, ''),
            'detail_supplier_name': deal_detail_supplier_name.get(uid, ''),
            'detail_currency': deal_detail_currency.get(uid, ''),
        })

    if buyer_filter:
        needle = buyer_filter.strip().lower()
        pairs = [p for p in pairs if needle in (p['buyer_name'] or '').lower()]

    pairs.sort(key=lambda p: (p['occupancy_rate'] is None, -(p['occupancy_rate'] or 0)))
    return pairs
```

- [ ] **Step 4: 运行测试确认通过**

Run: `"/c/Users/Administrator/AppData/Local/Programs/Python/Python314/python.exe" -m pytest backend/tests/test_credit_limit_service.py -v`
Expected: PASS（全部通过，含 `TestAggregateByBuyer`/`TestCheckWarnings`/`TestToFloat` 等既有类——它们不依赖内部实现细节，应保持不变）

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/credit_limit_service.py backend/tests/test_credit_limit_service.py
git commit -m "feat: get_buyer_supplier_pairs 改为对 Deal 层求和，待结清参与 Total O/S 抵消"
```

---

## Task 4: 额度明细页（`/credit/detail`）重做

**Files:**
- Modify: `backend/app/routes/credit.py`（重写 `credit_query_detail` 视图；删除该文件内已不再使用的 `_to_float`/`_fmt_date` 若仍被其他视图使用则保留——两者仍用于本视图的日期格式化，需要保留）
- Modify: `backend/app/templates/credit/credit_detail.html`（重做表格列 + 合计行）
- Modify: `backend/app/i18n/zh-CN.json:547-559`、`backend/app/i18n/en-US.json:440-451`（`credit.detail` 节点）
- Test: `backend/tests/test_credit_detail_route.py`（新建）

**Interfaces:**
- Consumes: Task 2 的 `get_pair_deal_rows(mongo, buyer_name, supplier_name, financing_currency)`、`compute_deal_totals(deal_rows)`。
- Produces: `GET /credit/detail` 渲染 `records`（当前页 deal 行）、`total_row`（`compute_deal_totals` 的结果，跨全部页）。

- [ ] **Step 1: 写失败测试**

新建 `backend/tests/test_credit_detail_route.py`：

```python
"""额度明细页路由测试（Deal 层重做）"""
from unittest.mock import patch


SAMPLE_DEALS = [
    {'uid': 'U1', 'buyer_code': 'B1', 'buyer_name': 'Buyer One', 'supplier_code': 'S1',
     'supplier_name': 'Seller One', 'currency': 'USD', 'finance_request_number': 'FR1',
     'invoice_number': 'INV1', 'financing_amount': 1000.0, 'earmark_forecast': 1000.0,
     'credit_utilization': 0.0, 'to_be_settled_on_db': None, 'total_os': 1000.0,
     'status': 'eligible', 'status_display': 'eligible', 'finance_status_display': '',
     'settlement_status': '', 'due_date': None, 'actual_funding_date': None, 'batch_number': ''},
    {'uid': 'U1', 'buyer_code': 'B1', 'buyer_name': 'Buyer One', 'supplier_code': 'S1',
     'supplier_name': 'Seller One', 'currency': 'USD', 'finance_request_number': 'FR2',
     'invoice_number': 'INV2', 'financing_amount': 2000.0, 'earmark_forecast': 0.0,
     'credit_utilization': 2000.0, 'to_be_settled_on_db': None, 'total_os': 2000.0,
     'status': 'funded before', 'status_display': 'Funded Successfully',
     'finance_status_display': 'Loan booked', 'settlement_status': 'Pending',
     'due_date': None, 'actual_funding_date': None, 'batch_number': '53'},
]


class TestCreditQueryDetailRoute:

    @patch('backend.app.routes.credit.get_mongo')
    @patch('backend.app.routes.credit.get_pair_deal_rows')
    def test_renders_deal_rows_and_total(self, mock_deals, mock_get_mongo, logged_in_client):
        mock_get_mongo.return_value = object()
        mock_deals.return_value = SAMPLE_DEALS

        resp = logged_in_client.get('/credit/detail?buyer_name=Buyer+One&supplier_name=Seller+One&currency=USD')
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        assert 'FR1' in body
        assert 'FR2' in body
        assert 'Funded Successfully' in body
        assert '3,000.00' in body  # Total O/S 合计: 1000 + 2000

    @patch('backend.app.routes.credit.get_mongo')
    @patch('backend.app.routes.credit.get_pair_deal_rows')
    def test_total_row_covers_all_pages_not_just_current_page(self, mock_deals, mock_get_mongo, logged_in_client):
        # 生成 25 条 deal（超过每页 20 条），验证合计行用的是全部 25 条而不是当页 20 条
        many_deals = [
            {**SAMPLE_DEALS[0], 'finance_request_number': f'FR{i}', 'earmark_forecast': 100.0,
             'total_os': 100.0, 'credit_utilization': 0.0}
            for i in range(25)
        ]
        mock_get_mongo.return_value = object()
        mock_deals.return_value = many_deals

        resp = logged_in_client.get('/credit/detail?buyer_name=Buyer+One&supplier_name=Seller+One&currency=USD')
        body = resp.get_data(as_text=True)
        assert '2,500.00' in body  # 25 * 100，而不是当页 20 条的 2,000.00

    @patch('backend.app.routes.credit.get_mongo')
    def test_no_mongo_renders_empty_without_crash(self, mock_get_mongo, logged_in_client):
        mock_get_mongo.return_value = None
        resp = logged_in_client.get('/credit/detail')
        assert resp.status_code == 200

    def test_requires_login(self, client):
        resp = client.get('/credit/detail')
        assert resp.status_code in (302, 401)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `"/c/Users/Administrator/AppData/Local/Programs/Python/Python314/python.exe" -m pytest backend/tests/test_credit_detail_route.py -v`
Expected: FAIL（路由仍是旧实现，模板不含新字段/合计行）

- [ ] **Step 3: 重写路由**

在 `backend/app/routes/credit.py` 顶部 import 中，把：

```python
from backend.app.services.credit_limit_service import get_buyer_supplier_pairs, aggregate_by_buyer
```

改为：

```python
from backend.app.services.credit_limit_service import (
    get_buyer_supplier_pairs, aggregate_by_buyer, get_pair_deal_rows, compute_deal_totals,
)
```

将 `credit_query_detail` 视图函数（从 `@credit_bp.route('/detail')` 到该函数末尾的 `return render_template(...)`）整体替换为：

```python
@credit_bp.route('/detail')
@login_required
def credit_query_detail():
    buyer_name = request.args.get('buyer_name', '').strip()
    supplier_name = request.args.get('supplier_name', '').strip()
    financing_currency = request.args.get('currency', '').strip()
    page = request.args.get('page', 1, type=int)
    back_buyer = request.args.get('back_buyer', '')
    back_seller = request.args.get('back_seller', '')

    mongo = get_mongo()
    all_deals = []
    error = None

    if mongo is not None:
        try:
            all_deals = get_pair_deal_rows(mongo, buyer_name, supplier_name, financing_currency)
            all_deals.sort(key=lambda d: d.get('due_date') or datetime.min, reverse=True)
        except Exception as e:
            error = str(e)

    total = len(all_deals)
    total_pages = (total + _PER_PAGE - 1) // _PER_PAGE if total else 0
    start = (page - 1) * _PER_PAGE
    records = all_deals[start:start + _PER_PAGE]
    for rec in records:
        rec['due_date'] = _fmt_date(rec.get('due_date'))
        rec['actual_funding_date'] = _fmt_date(rec.get('actual_funding_date'))

    total_row = compute_deal_totals(all_deals)
    end_record = min(page * _PER_PAGE, total)

    return render_template(
        'credit/credit_detail.html',
        buyer_name=buyer_name,
        supplier_name=supplier_name,
        financing_currency=financing_currency,
        records=records,
        total=total,
        total_row=total_row,
        page=page,
        per_page=_PER_PAGE,
        total_pages=total_pages,
        end_record=end_record,
        error=error,
        back_buyer=back_buyer,
        back_seller=back_seller,
    )
```

（`datetime` 需要在文件顶部已导入——`credit.py` 已有 `from datetime import datetime`，无需重复添加。原有 `query`/`count_documents`/`skip`/`limit` 的数据库分页逻辑整体移除，改为取全量后在内存中排序、切片；`_to_float`/`_fmt_date` 辅助函数保留不动，仍在此处使用。）

- [ ] **Step 4: 重写模板**

将 `backend/app/templates/credit/credit_detail.html` 的表头（第 49-62 行）替换为：

```html
                <thead class="table-dark">
                    <tr>
                        <th>#</th>
                        <th>{{ _('credit.detail.finance_request_number') }}</th>
                        <th>{{ _('credit.detail.invoice_number') }}</th>
                        <th class="text-end">{{ _('credit.detail.financing_amount') }}</th>
                        <th class="text-end">{{ _('credit.detail.earmark_forecast') }}</th>
                        <th class="text-end">{{ _('credit.detail.credit_utilization') }}</th>
                        <th class="text-end">{{ _('credit.detail.to_be_settled_on_db') }}</th>
                        <th class="text-end">{{ _('credit.detail.total_os') }}</th>
                        <th>{{ _('credit.detail.status') }}</th>
                        <th>{{ _('credit.detail.finance_status') }}</th>
                        <th>{{ _('credit.detail.settlement_status') }}</th>
                        <th>{{ _('credit.detail.due_date') }}</th>
                        <th>{{ _('credit.detail.funding_date') }}</th>
                        <th>{{ _('credit.detail.batch') }}</th>
                    </tr>
                </thead>
```

表体（第 64-104 行）替换为：

```html
                <tbody>
                    {% if records %}
                        {% for rec in records %}
                        <tr {% if rec.total_os > 0 %}class="table-warning"{% endif %}>
                            <td class="text-muted small">{{ (page - 1) * per_page + loop.index }}</td>
                            <td class="font-monospace small">{{ rec.finance_request_number or '-' }}</td>
                            <td class="small">{{ rec.invoice_number or '-' }}</td>
                            <td class="text-end font-monospace">{{ "{:,.2f}".format(rec.financing_amount) }}</td>
                            <td class="text-end font-monospace">
                                {% if rec.earmark_forecast %}{{ "{:,.2f}".format(rec.earmark_forecast) }}
                                {% else %}<span class="text-muted">-</span>{% endif %}
                            </td>
                            <td class="text-end font-monospace">
                                {% if rec.credit_utilization %}{{ "{:,.2f}".format(rec.credit_utilization) }}
                                {% else %}<span class="text-muted">-</span>{% endif %}
                            </td>
                            <td class="text-end font-monospace">
                                {% if rec.to_be_settled_on_db is not none %}{{ "{:,.2f}".format(rec.to_be_settled_on_db) }}
                                {% else %}<span class="text-muted">N/A</span>{% endif %}
                            </td>
                            <td class="text-end font-monospace fw-bold">{{ "{:,.2f}".format(rec.total_os) }}</td>
                            <td class="small">{{ rec.status_display or '-' }}</td>
                            <td class="small">{{ rec.finance_status_display or '-' }}</td>
                            <td class="small">{{ rec.settlement_status or '-' }}</td>
                            <td class="small">{{ rec.due_date or '-' }}</td>
                            <td class="small">{{ rec.actual_funding_date or '-' }}</td>
                            <td class="small text-center">{{ rec.batch_number or '-' }}</td>
                        </tr>
                        {% endfor %}
                    {% else %}
                        <tr>
                            <td colspan="14" class="text-center text-muted py-4">
                                <i class="fa fa-inbox fa-2x mb-2 d-block"></i>
                                {{ _('common.message.no_data') }}
                            </td>
                        </tr>
                    {% endif %}
                </tbody>
                {% if records %}
                <tfoot class="table-secondary fw-bold">
                    <tr>
                        <td colspan="3">{{ _('credit.detail.total_row') }}</td>
                        <td class="text-end font-monospace">{{ "{:,.2f}".format(total_row.financing_amount) }}</td>
                        <td class="text-end font-monospace">{{ "{:,.2f}".format(total_row.earmark_forecast) }}</td>
                        <td class="text-end font-monospace">{{ "{:,.2f}".format(total_row.credit_utilization) }}</td>
                        <td class="text-end font-monospace">{{ "{:,.2f}".format(total_row.to_be_settled_on_db) }}</td>
                        <td class="text-end font-monospace">{{ "{:,.2f}".format(total_row.total_os) }}</td>
                        <td colspan="6"></td>
                    </tr>
                </tfoot>
                {% endif %}
```

（`colspan` 从旧的 `11` 改为 `14`，对应新的 14 列表头；`tfoot` 的合计行放在 `tbody` 之后、`table` 结束之前，与原 `credit_query.html` 早期版本的 `tfoot` 用法一致。）

- [ ] **Step 5: 更新 i18n 文案**

在 `backend/app/i18n/zh-CN.json` 的 `credit.detail` 对象中，删除 `wip_pending`/`outstanding_excl_wip`，新增（放在 `financing_amount` 之后、`status` 之前）：

```json
      "earmark_forecast": "预占",
      "credit_utilization": "实占",
      "to_be_settled_on_db": "待结清(DB)",
```

在 `status` 之后新增：

```json
      "finance_status": "DB放款状态",
      "settlement_status": "结清状态",
```

在该对象末尾（`batch` 之后）新增：

```json
      "total_row": "合计",
      "export": "导出Excel"
```

在 `backend/app/i18n/en-US.json` 的 `credit.detail` 对象做相同的增删，英文值：

```json
      "earmark_forecast": "Earmark Forecast",
      "credit_utilization": "Credit Utilization",
      "to_be_settled_on_db": "To Be Settled on DB",
```

```json
      "finance_status": "Finance Details - Finance Status",
      "settlement_status": "Invoice Details - Settlement Status",
```

```json
      "total_row": "Total",
      "export": "Export Excel"
```

- [ ] **Step 6: 运行测试确认通过**

Run: `"/c/Users/Administrator/AppData/Local/Programs/Python/Python314/python.exe" -m pytest backend/tests/test_credit_detail_route.py -v`
Expected: PASS（4 项全部通过）

- [ ] **Step 7: Commit**

```bash
git add backend/app/routes/credit.py backend/app/templates/credit/credit_detail.html \
        backend/app/i18n/zh-CN.json backend/app/i18n/en-US.json backend/tests/test_credit_detail_route.py
git commit -m "feat: 额度明细页重做为 Deal 层字段 + 跨页合计行"
```

---

## Task 5: 额度明细页新增导出

**Files:**
- Modify: `backend/app/services/credit_export_service.py`（新增 `build_deal_detail_workbook`）
- Modify: `backend/app/routes/credit.py`（新增 `POST /credit/detail/export` 路由）
- Modify: `backend/app/templates/credit/credit_detail.html`（新增导出按钮）
- Test: `backend/tests/test_credit_export_service.py`（追加）、`backend/tests/test_credit_detail_route.py`（追加）

**Interfaces:**
- Consumes: Task 2 的 `get_pair_deal_rows`/`compute_deal_totals`。
- Produces: `build_deal_detail_workbook(deal_rows, total_row) -> bytes`；路由 `POST /credit/detail/export`。

- [ ] **Step 1: 写失败测试 — 导出服务**

追加到 `backend/tests/test_credit_export_service.py` 末尾：

```python
SAMPLE_DEAL_ROWS = [
    {'finance_request_number': 'FR1', 'invoice_number': 'INV1', 'buyer_name': 'Buyer One',
     'supplier_name': 'Seller One', 'financing_amount': 1000.0, 'earmark_forecast': 1000.0,
     'credit_utilization': 0.0, 'to_be_settled_on_db': None, 'total_os': 1000.0,
     'status_display': 'eligible', 'finance_status_display': '', 'settlement_status': '',
     'due_date': '2026-10-01', 'actual_funding_date': '', 'batch_number': ''},
]


class TestBuildDealDetailWorkbook:

    def test_creates_deal_sheet_with_header_and_rows(self):
        from backend.app.services.credit_export_service import build_deal_detail_workbook
        from backend.app.services.credit_limit_service import compute_deal_totals
        total_row = compute_deal_totals(SAMPLE_DEAL_ROWS)
        data = build_deal_detail_workbook(SAMPLE_DEAL_ROWS, total_row)
        wb = load_workbook(io.BytesIO(data))
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
        assert rows[0][0] == 'FR#'
        assert rows[1][0] == 'FR1'

    def test_appends_total_row_at_the_end(self):
        from backend.app.services.credit_export_service import build_deal_detail_workbook
        from backend.app.services.credit_limit_service import compute_deal_totals
        total_row = compute_deal_totals(SAMPLE_DEAL_ROWS)
        data = build_deal_detail_workbook(SAMPLE_DEAL_ROWS, total_row)
        wb = load_workbook(io.BytesIO(data))
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
        last_row = rows[-1]
        assert last_row[0] == 'Total'
        header = rows[0]
        idx = header.index('Financing Amount')
        assert last_row[idx] == 1000.0
```

- [ ] **Step 2: 运行测试确认失败**

Run: `"/c/Users/Administrator/AppData/Local/Programs/Python/Python314/python.exe" -m pytest backend/tests/test_credit_export_service.py::TestBuildDealDetailWorkbook -v`
Expected: FAIL，`ImportError: cannot import name 'build_deal_detail_workbook'`

- [ ] **Step 3: 实现导出函数**

在 `backend/app/services/credit_export_service.py` 末尾追加：

```python
_DEAL_HEADERS = ['FR#', 'Invoice#', 'Buyer', 'Supplier', 'Financing Amount', 'Earmark Forecast',
                  'Credit Utilization', 'To Be Settled on DB', 'Total O/S', 'Status',
                  'Finance Details - Finance Status', 'Invoice Details - Settlement Status',
                  'Due Date', 'Funding Date', 'Batch']


def _deal_row_values(d):
    return [
        d.get('finance_request_number', ''),
        d.get('invoice_number', ''),
        d.get('buyer_name', ''),
        d.get('supplier_name', ''),
        d.get('financing_amount', 0.0),
        d.get('earmark_forecast', 0.0),
        d.get('credit_utilization', 0.0),
        d.get('to_be_settled_on_db') if d.get('to_be_settled_on_db') is not None else 'N/A',
        d.get('total_os', 0.0),
        d.get('status_display', ''),
        d.get('finance_status_display', ''),
        d.get('settlement_status', ''),
        d.get('due_date', ''),
        d.get('actual_funding_date', ''),
        d.get('batch_number', ''),
    ]


def _deal_total_row_values(total_row):
    return [
        'Total', '', '', '',
        total_row.get('financing_amount', 0.0),
        total_row.get('earmark_forecast', 0.0),
        total_row.get('credit_utilization', 0.0),
        total_row.get('to_be_settled_on_db', 0.0),
        total_row.get('total_os', 0.0),
        '', '', '', '', '', '',
    ]


def build_deal_detail_workbook(deal_rows, total_row):
    """构建单个买卖方配对的 Deal 明细 Excel，末尾追加合计行。"""
    wb = Workbook()
    ws = wb.active
    ws.title = 'Deal Detail'
    _write_header(ws, _DEAL_HEADERS)
    for d in deal_rows:
        _write_data_row(ws, _deal_row_values(d))
    _write_data_row(ws, _deal_total_row_values(total_row))
    _autofit_columns(ws)

    output = io.BytesIO()
    wb.save(output)
    return output.getvalue()
```

- [ ] **Step 4: 运行测试确认通过**

Run: `"/c/Users/Administrator/AppData/Local/Programs/Python/Python314/python.exe" -m pytest backend/tests/test_credit_export_service.py::TestBuildDealDetailWorkbook -v`
Expected: PASS

- [ ] **Step 5: 新增导出路由**

在 `backend/app/routes/credit.py` 顶部 import 追加：

```python
from backend.app.services.credit_export_service import build_credit_limit_workbook, build_deal_detail_workbook
```

（替换原有的 `from backend.app.services.credit_export_service import build_credit_limit_workbook` 单行 import。）

在 `credit_query_detail` 视图之后新增：

```python
@credit_bp.route('/detail/export', methods=['POST'])
@login_required
def credit_detail_export():
    buyer_name = request.form.get('buyer_name', '').strip()
    supplier_name = request.form.get('supplier_name', '').strip()
    financing_currency = request.form.get('currency', '').strip()

    mongo = get_mongo()
    if mongo is None:
        flash('没有找到符合条件的数据', 'warning')
        return redirect(url_for('credit.credit_query_detail', buyer_name=buyer_name,
                                 supplier_name=supplier_name, currency=financing_currency))

    try:
        deals = get_pair_deal_rows(mongo, buyer_name, supplier_name, financing_currency)
    except Exception as e:
        flash(str(e), 'danger')
        return redirect(url_for('credit.credit_query_detail', buyer_name=buyer_name,
                                 supplier_name=supplier_name, currency=financing_currency))

    if not deals:
        flash('没有找到符合条件的数据', 'warning')
        return redirect(url_for('credit.credit_query_detail', buyer_name=buyer_name,
                                 supplier_name=supplier_name, currency=financing_currency))

    for d in deals:
        d['due_date'] = _fmt_date(d.get('due_date'))
        d['actual_funding_date'] = _fmt_date(d.get('actual_funding_date'))

    total_row = compute_deal_totals(deals)
    workbook_bytes = build_deal_detail_workbook(deals, total_row)
    filename = f"credit_detail_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return send_file(
        io.BytesIO(workbook_bytes),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=filename,
    )
```

- [ ] **Step 6: 模板加导出按钮**

在 `backend/app/templates/credit/credit_detail.html` 顶部的返回按钮区域（第 6-12 行）中，紧跟"返回列表"按钮之后新增一个隐藏表单和导出按钮：

```html
<div class="d-flex justify-content-between align-items-center mb-3">
    <h4><i class="fa fa-list-alt"></i> {{ _('credit.detail.title') }}</h4>
    <div>
        <form method="post" action="{{ url_for('credit.credit_detail_export') }}" class="d-inline">
            <input type="hidden" name="buyer_name" value="{{ buyer_name }}">
            <input type="hidden" name="supplier_name" value="{{ supplier_name }}">
            <input type="hidden" name="currency" value="{{ financing_currency }}">
            <button type="submit" class="btn btn-outline-success btn-sm">
                <i class="fa fa-file-excel-o"></i> {{ _('credit.detail.export') }}
            </button>
        </form>
        <a href="{{ url_for('credit.credit_query', buyer_name=back_buyer, seller_name=back_seller) }}"
           class="btn btn-secondary btn-sm">
            <i class="fa fa-arrow-left"></i> {{ _('credit.detail.back') }}
        </a>
    </div>
</div>
```

- [ ] **Step 7: 写路由测试**

追加到 `backend/tests/test_credit_detail_route.py` 末尾：

```python
class TestCreditDetailExportRoute:

    @patch('backend.app.routes.credit.get_mongo')
    @patch('backend.app.routes.credit.get_pair_deal_rows')
    def test_export_returns_xlsx_file(self, mock_deals, mock_get_mongo, logged_in_client):
        mock_get_mongo.return_value = object()
        mock_deals.return_value = SAMPLE_DEALS
        resp = logged_in_client.post('/credit/detail/export', data={
            'buyer_name': 'Buyer One', 'supplier_name': 'Seller One', 'currency': 'USD',
        })
        assert resp.status_code == 200
        assert resp.mimetype == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'

    @patch('backend.app.routes.credit.get_mongo')
    @patch('backend.app.routes.credit.get_pair_deal_rows')
    def test_export_empty_result_redirects_with_flash(self, mock_deals, mock_get_mongo, logged_in_client):
        mock_get_mongo.return_value = object()
        mock_deals.return_value = []
        resp = logged_in_client.post('/credit/detail/export', data={
            'buyer_name': 'X', 'supplier_name': 'Y', 'currency': 'USD',
        }, follow_redirects=True)
        assert resp.status_code == 200
        assert '没有找到符合条件的数据' in resp.get_data(as_text=True)

    def test_export_requires_login(self, client):
        resp = client.post('/credit/detail/export')
        assert resp.status_code in (302, 401)
```

- [ ] **Step 8: 运行测试确认通过**

Run: `"/c/Users/Administrator/AppData/Local/Programs/Python/Python314/python.exe" -m pytest backend/tests/test_credit_export_service.py backend/tests/test_credit_detail_route.py -v`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add backend/app/services/credit_export_service.py backend/app/routes/credit.py \
        backend/app/templates/credit/credit_detail.html \
        backend/tests/test_credit_export_service.py backend/tests/test_credit_detail_route.py
git commit -m "feat: 额度明细页新增 Excel 导出（含合计行）"
```

---

## Task 6: 额度查询列表导出改为买方/买卖方/Deal 三个固定 Tab

**Files:**
- Modify: `backend/app/services/credit_export_service.py`（重写 `build_credit_limit_workbook`）
- Modify: `backend/app/routes/credit.py`（`credit_export` 视图改为三参数调用）
- Test: `backend/tests/test_credit_export_service.py`（替换 `TestBuildCreditLimitWorkbook` 类）、`backend/tests/test_credit_export_route.py`（更新 mock）

**Interfaces:**
- Consumes: Task 2 的 `get_deal_rows`、`compute_deal_totals`；既有的 `get_buyer_supplier_pairs`/`aggregate_by_buyer`。
- Produces: `build_credit_limit_workbook(buyer_rows, pair_rows, deal_rows) -> bytes`（3 个固定 sheet：`Buyer`/`Buyer-Supplier`/`Deal`，各自末尾追加 `Total` 行）。

- [ ] **Step 1: 替换失败测试**

在 `backend/tests/test_credit_export_service.py` 中，删除整个 `class TestBuildCreditLimitWorkbook:` 及其方法，替换为：

```python
SAMPLE_PAIR_ROWS = [
    {'uid': 'U1', 'buyer_code': 'B1', 'buyer_name': 'Amazon Services', 'supplier_code': 'S1',
     'supplier_name': 'Photonverse Inc', 'currency': 'USD', 'celling': 100000.0, 'reserved': 20000.0,
     'actual': 75000.0, 'total_occupied': 95000.0, 'headroom': 5000.0, 'occupancy_rate': 0.95},
]


class TestBuildCreditLimitWorkbook:

    def test_creates_exactly_three_fixed_sheets(self):
        from backend.app.services.credit_export_service import build_credit_limit_workbook
        data = build_credit_limit_workbook(SAMPLE_BUYER_ROWS, SAMPLE_PAIR_ROWS, SAMPLE_DEAL_ROWS)
        wb = load_workbook(io.BytesIO(data))
        assert wb.sheetnames == ['Buyer', 'Buyer-Supplier', 'Deal']

    def test_buyer_sheet_contains_row_and_total(self):
        from backend.app.services.credit_export_service import build_credit_limit_workbook
        data = build_credit_limit_workbook(SAMPLE_BUYER_ROWS, SAMPLE_PAIR_ROWS, SAMPLE_DEAL_ROWS)
        wb = load_workbook(io.BytesIO(data))
        rows = list(wb['Buyer'].iter_rows(values_only=True))
        assert rows[0][0] == 'Buyer'
        assert rows[1][0] == 'Amazon Services'
        assert rows[-1][0] == 'Total'
        header = rows[0]
        celling_idx = header.index('Celling')
        assert rows[-1][celling_idx] == 100000.0

    def test_buyer_supplier_sheet_is_flat_not_split_by_buyer(self):
        from backend.app.services.credit_export_service import build_credit_limit_workbook
        data = build_credit_limit_workbook(SAMPLE_BUYER_ROWS, SAMPLE_PAIR_ROWS, SAMPLE_DEAL_ROWS)
        wb = load_workbook(io.BytesIO(data))
        rows = list(wb['Buyer-Supplier'].iter_rows(values_only=True))
        assert rows[0][0] == 'Buyer'
        header = rows[0]
        assert 'Supplier' in header
        assert rows[1][header.index('Supplier')] == 'Photonverse Inc'
        assert rows[-1][0] == 'Total'

    def test_deal_sheet_carries_buyer_supplier_identifiers_and_total(self):
        from backend.app.services.credit_export_service import build_credit_limit_workbook
        data = build_credit_limit_workbook(SAMPLE_BUYER_ROWS, SAMPLE_PAIR_ROWS, SAMPLE_DEAL_ROWS)
        wb = load_workbook(io.BytesIO(data))
        rows = list(wb['Deal'].iter_rows(values_only=True))
        header = rows[0]
        assert 'Buyer' in header
        assert 'Supplier' in header
        assert rows[1][header.index('FR#')] == 'FR1'
        assert rows[-1][0] == 'Total'

    def test_empty_input_still_produces_three_sheets_with_header_only(self):
        from backend.app.services.credit_export_service import build_credit_limit_workbook
        data = build_credit_limit_workbook([], [], [])
        wb = load_workbook(io.BytesIO(data))
        assert wb.sheetnames == ['Buyer', 'Buyer-Supplier', 'Deal']
        assert list(wb['Buyer'].iter_rows(values_only=True))[0][0] == 'Buyer'
```

（`SAMPLE_BUYER_ROWS`/`SAMPLE_DEAL_ROWS` 沿用文件里已有的模块级样例数据——`SAMPLE_BUYER_ROWS` 在 Task 之前已存在，`SAMPLE_DEAL_ROWS` 是 Task 5 Step 1 新增的模块级样例；`SAMPLE_PAIR_ROWS` 是本 task 新增的模块级样例，放在这个新测试类之前。同时删除 `SAMPLE_BUYER_ROWS` 里原来嵌套的 `'pairs': [...]` 字段依赖——新签名下 `build_credit_limit_workbook` 不再从 `buyer_rows` 里取 `pairs`，`SAMPLE_BUYER_ROWS` 保留原样即可，多余的 `pairs` 键不影响测试。）

- [ ] **Step 2: 运行测试确认失败**

Run: `"/c/Users/Administrator/AppData/Local/Programs/Python/Python314/python.exe" -m pytest backend/tests/test_credit_export_service.py::TestBuildCreditLimitWorkbook -v`
Expected: FAIL（旧实现签名只接受一个参数 `buyer_rows`，且生成的是"1 汇总 + N 买方"结构而非固定 3 sheet）

- [ ] **Step 3: 重写导出函数**

在 `backend/app/services/credit_export_service.py` 中，删除 `_sanitize_sheet_name` 函数（不再需要按买方拆分 sheet，因此不需要清理/去重 sheet 名），并把 `_SUMMARY_HEADERS`/`_DETAIL_HEADERS`/`_row_values`/`build_credit_limit_workbook` 整体替换为：

```python
_BUYER_HEADERS = ['Buyer', 'Air8 Buyer ID', 'Currency', 'Celling', 'Reserved', 'Actual', 'Total Occupied', 'Headroom', 'Occupancy Rate']
_PAIR_HEADERS = ['Buyer', 'Air8 Buyer ID', 'Supplier', 'Air8 Seller ID', 'Currency', 'Celling', 'Reserved', 'Actual', 'Total Occupied', 'Headroom', 'Occupancy Rate']


def _amount_row_values(name, id_value, row):
    occupancy = row.get('occupancy_rate')
    return [
        name, id_value, row.get('currency', 'USD'),
        row.get('celling', 0.0), row.get('reserved', 0.0), row.get('actual', 0.0),
        row.get('total_occupied', 0.0),
        row.get('headroom') if row.get('headroom') is not None else 'N/A',
        f"{occupancy:.1%}" if occupancy is not None else 'N/A',
    ]


def _amount_total_row_values(rows, blank_count):
    """blank_count = 该 sheet 中 Celling 列之前除 'Total' 占用的那一格外，还有几个非数值列
    （名称/ID/币种等）需要留空对齐。Buyer sheet 是 Buyer/Air8 Buyer ID/Currency 共 3 列，
    'Total' 占 1 格，blank_count=2；Buyer-Supplier sheet 是 Buyer/Air8 Buyer
    ID/Supplier/Air8 Seller ID/Currency 共 5 列，blank_count=4。"""
    celling_sum = sum(r.get('celling', 0.0) for r in rows)
    reserved_sum = sum(r.get('reserved', 0.0) for r in rows)
    actual_sum = sum(r.get('actual', 0.0) for r in rows)
    total_sum = sum(r.get('total_occupied', 0.0) for r in rows)
    headroom_sum = round(celling_sum - total_sum, 2) if celling_sum else 'N/A'
    occupancy_avg = round(total_sum / celling_sum, 4) if celling_sum else None
    prefix = ['Total'] + [''] * blank_count
    return prefix + [
        round(celling_sum, 2), round(reserved_sum, 2), round(actual_sum, 2), round(total_sum, 2),
        headroom_sum, f"{occupancy_avg:.1%}" if occupancy_avg is not None else 'N/A',
    ]


def build_credit_limit_workbook(buyer_rows, pair_rows, deal_rows):
    """构建额度管理 Excel：固定 3 个 sheet（Buyer/Buyer-Supplier/Deal），各自末尾追加 Total 行。"""
    wb = Workbook()

    buyer_ws = wb.active
    buyer_ws.title = 'Buyer'
    _write_header(buyer_ws, _BUYER_HEADERS)
    for b in buyer_rows:
        _write_data_row(buyer_ws, _amount_row_values(b.get('buyer_name', ''), b.get('buyer_code', ''), b))
    if buyer_rows:
        _write_data_row(buyer_ws, _amount_total_row_values(buyer_rows, blank_count=2))
    _autofit_columns(buyer_ws)

    pair_ws = wb.create_sheet('Buyer-Supplier')
    _write_header(pair_ws, _PAIR_HEADERS)
    for p in pair_rows:
        occupancy = p.get('occupancy_rate')
        pair_ws.append([
            p.get('buyer_name', ''), p.get('buyer_code', ''), p.get('supplier_name', ''), p.get('supplier_code', ''),
            p.get('currency', 'USD'), p.get('celling', 0.0), p.get('reserved', 0.0), p.get('actual', 0.0),
            p.get('total_occupied', 0.0),
            p.get('headroom') if p.get('headroom') is not None else 'N/A',
            f"{occupancy:.1%}" if occupancy is not None else 'N/A',
        ])
        for cell in pair_ws[pair_ws.max_row]:
            cell.border = _THIN_BORDER
            cell.alignment = _LEFT
    if pair_rows:
        _write_data_row(pair_ws, _amount_total_row_values(pair_rows, blank_count=4))
    _autofit_columns(pair_ws)

    deal_ws = wb.create_sheet('Deal')
    _write_header(deal_ws, _DEAL_HEADERS)
    for d in deal_rows:
        _write_data_row(deal_ws, _deal_row_values(d))
    if deal_rows:
        deal_totals = {
            'financing_amount': sum(d.get('financing_amount', 0.0) for d in deal_rows),
            'earmark_forecast': sum(d.get('earmark_forecast', 0.0) for d in deal_rows),
            'credit_utilization': sum(d.get('credit_utilization', 0.0) for d in deal_rows),
            'to_be_settled_on_db': sum(d.get('to_be_settled_on_db') or 0.0 for d in deal_rows),
            'total_os': sum(d.get('total_os', 0.0) for d in deal_rows),
        }
        _write_data_row(deal_ws, _deal_total_row_values(deal_totals))
    _autofit_columns(deal_ws)

    output = io.BytesIO()
    wb.save(output)
    return output.getvalue()
```

（`_DEAL_HEADERS`/`_deal_row_values`/`_deal_total_row_values` 已在 Task 5 中定义，本函数直接复用——`_DEAL_HEADERS` 本身已包含 `Buyer`/`Supplier` 两列（见 Task 5 定义），`Deal` sheet 不需要再额外前置，否则会导致买方/卖方列重复出现、合计行的 `'Total'` 标签错位。）

- [ ] **Step 4: 更新导出路由**

在 `backend/app/routes/credit.py` 中，把 `credit_export` 视图里：

```python
    try:
        pairs = get_buyer_supplier_pairs(mongo, buyer_filter=buyer_filter or None)
        buyer_rows = aggregate_by_buyer(pairs)
    except Exception as e:
        flash(str(e), 'danger')
        return redirect(url_for('credit.credit_query', buyer_name=buyer_filter))

    if not buyer_rows:
        flash('没有找到符合条件的数据', 'warning')
        return redirect(url_for('credit.credit_query', buyer_name=buyer_filter))

    workbook_bytes = build_credit_limit_workbook(buyer_rows)
```

改为：

```python
    try:
        pairs = get_buyer_supplier_pairs(mongo, buyer_filter=buyer_filter or None)
        buyer_rows = aggregate_by_buyer(pairs)
        deal_rows = get_deal_rows(mongo, buyer_filter=buyer_filter or None)
    except Exception as e:
        flash(str(e), 'danger')
        return redirect(url_for('credit.credit_query', buyer_name=buyer_filter))

    if not buyer_rows:
        flash('没有找到符合条件的数据', 'warning')
        return redirect(url_for('credit.credit_query', buyer_name=buyer_filter))

    workbook_bytes = build_credit_limit_workbook(buyer_rows, pairs, deal_rows)
```

同时在文件顶部 import 中把：

```python
from backend.app.services.credit_limit_service import (
    get_buyer_supplier_pairs, aggregate_by_buyer, get_pair_deal_rows, compute_deal_totals,
)
```

改为（新增 `get_deal_rows`）：

```python
from backend.app.services.credit_limit_service import (
    get_buyer_supplier_pairs, aggregate_by_buyer, get_pair_deal_rows, compute_deal_totals, get_deal_rows,
)
```

- [ ] **Step 5: 更新路由测试的 mock**

在 `backend/tests/test_credit_export_route.py` 中，`TestCreditExportRoute` 的两个测试都新增对 `get_deal_rows` 的 patch 与 mock 返回值。把：

```python
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
```

改为：

```python
    @patch('backend.app.routes.credit.get_mongo')
    @patch('backend.app.routes.credit.get_deal_rows')
    @patch('backend.app.routes.credit.aggregate_by_buyer')
    @patch('backend.app.routes.credit.get_buyer_supplier_pairs')
    def test_export_returns_xlsx_file(self, mock_pairs, mock_aggregate, mock_deals, mock_get_mongo, logged_in_client):
        mock_get_mongo.return_value = object()
        mock_pairs.return_value = []
        mock_deals.return_value = []
        mock_aggregate.return_value = [
            {'buyer_code': 'B1', 'buyer_name': 'Amazon Services', 'currency': 'USD',
             'celling': 1000.0, 'reserved': 0.0, 'actual': 0.0, 'total_occupied': 0.0,
             'headroom': 1000.0, 'occupancy_rate': 0.0, 'pairs': []},
        ]
        resp = logged_in_client.post('/credit/export')
        assert resp.status_code == 200
        assert resp.mimetype == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
```

对 `test_export_empty_result_redirects_with_flash` 做同样的 `@patch('backend.app.routes.credit.get_deal_rows')` 追加和 `mock_deals.return_value = []` 追加（参数顺序：新增的 patch 装饰器放在离函数最近的位置，对应函数签名里最靠前的新增参数——按 Python `@patch` 装饰器"就近对应"的规则，装饰器书写顺序从下到上对应函数参数从左到右，因此新增的 `@patch('backend.app.routes.credit.get_deal_rows')` 应放在 `@patch('backend.app.routes.credit.get_mongo')` 和 `@patch('backend.app.routes.credit.aggregate_by_buyer')` 之间，紧跟在 `get_buyer_supplier_pairs` 之后、`aggregate_by_buyer` 之前，和上面 `test_export_returns_xlsx_file` 的写法保持一致）。

- [ ] **Step 6: 运行测试确认通过**

Run: `"/c/Users/Administrator/AppData/Local/Programs/Python/Python314/python.exe" -m pytest backend/tests/test_credit_export_service.py backend/tests/test_credit_export_route.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/credit_export_service.py backend/app/routes/credit.py \
        backend/tests/test_credit_export_service.py backend/tests/test_credit_export_route.py
git commit -m "feat: 额度查询导出改为买方/买卖方/Deal 三个固定 sheet，各自带合计行"
```

---

## Task 7: 额度查询列表页文案调整（Reserved→Earmark Forecast，Actual→Credit Utilization）

**Files:**
- Modify: `backend/app/i18n/en-US.json:432-433`
- Test: `backend/tests/test_credit_query_route.py`（追加断言）

**Interfaces:**
- 无代码接口变化，仅英文显示文案。

- [ ] **Step 1: 写失败测试**

在 `backend/tests/test_credit_query_route.py` 的 `test_renders_buyer_rows` 测试末尾追加断言（在已有的 `assert 'S1' in body` 之后）：

```python
        assert 'Earmark Forecast' in body
        assert 'Credit Utilization' in body
```

（这个断言依赖页面渲染时读取 `en-US.json`，需确认测试客户端使用的默认语言/cookie 会命中英文翻译——若默认语言为中文导致断言失败，改为直接请求 `?lang=en` 查询参数：`logged_in_client.get('/credit/credit-query?lang=en')`，并同步修改这条测试用例的请求 URL。)

- [ ] **Step 2: 运行测试确认失败**

Run: `"/c/Users/Administrator/AppData/Local/Programs/Python/Python314/python.exe" -m pytest backend/tests/test_credit_query_route.py::TestCreditQueryRoute::test_renders_buyer_rows -v`
Expected: FAIL（当前英文文案仍是 `Reserved`/`Actual`）

- [ ] **Step 3: 实现**

在 `backend/app/i18n/en-US.json` 中，把：

```json
      "reserved": "Reserved",
      "actual": "Actual",
```

改为：

```json
      "reserved": "Earmark Forecast",
      "actual": "Credit Utilization",
```

（中文 `zh-CN.json` 的 `"reserved": "预占"`、`"actual": "实占"` 不变。）

- [ ] **Step 4: 运行测试确认通过**

Run: `"/c/Users/Administrator/AppData/Local/Programs/Python/Python314/python.exe" -m pytest backend/tests/test_credit_query_route.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/i18n/en-US.json backend/tests/test_credit_query_route.py
git commit -m "feat: 额度查询列表英文列名改为 Earmark Forecast / Credit Utilization"
```

---

## Task 8: 全量回归 + 需求基线文档同步

**Files:**
- Modify: `docs/system/requirements.md`（第 11 章 额度管理）

**Interfaces:**
- Consumes: 全部前序 task。

- [ ] **Step 1: 运行全量回归测试**

Run: `"/c/Users/Administrator/AppData/Local/Programs/Python/Python314/python.exe" -m pytest backend/tests/ -v`
Expected: 全部通过，包括 `test_smoke.py`、`test_credit_warning_service.py`（预警服务复用 `get_buyer_supplier_pairs`/`aggregate_by_buyer`，签名未变，理应无需改动即可通过）

- [ ] **Step 2: 同步需求基线文档**

在 `docs/system/requirements.md` 第 11 章「额度管理（REQ-CREDIT-xxx）」中：

1. 更新 REQ-CREDIT-001/002 的预占（AC3）、实占（AC4）验收标准描述，改为引用本次 spec（`2026-08-26-credit-deal-level-rework-design.md`）需求 2/3 的 Deal 层统一计算口径（Financing Amount 基数、预占/实占/待结清门槛、Total O/S 抵消公式），删除已过时的"实占乘以固定 90%"表述。
2. 新增/更新 REQ-CREDIT-005（额度明细页重做）：引用本次 spec 需求 5 的验收标准（新列、跨页合计行）。
3. 新增 REQ-CREDIT-006（额度明细页导出）：引用本次 spec 需求 7。
4. 更新 REQ-CREDIT-003（原"额度数据导出"）的验收标准，改为固定 3 sheet（Buyer/Buyer-Supplier/Deal）+ 各自合计行的描述（本次 spec 需求 6）。
5. 在文档末尾「15. 变更记录」表格追加一行：

```markdown
| 2026-08-26 | `2026-08-26-credit-deal-level-rework-design.md` | 额度管理预占/实占/待结清下沉到 Deal 层统一计算（新增银行对账单 Advance Ratio 字段，Financing Amount = original_amount×advance_ratio，实占不再固定 90%，待结清取自 refactoring_bank_repayment_record），买卖方/买方层改为对 Deal 层求和；额度明细页重做（新列、跨页合计行、导出）；额度查询导出改为固定买方/买卖方/Deal 三个 sheet 均带合计行（REQ-CREDIT-001~003、005~006） |
```

- [ ] **Step 3: Commit**

```bash
git add docs/system/requirements.md
git commit -m "docs: 同步额度管理 Deal 层重构需求基线"
```

---

## 任务依赖说明

Task 1 → Task 2 → Task 3 严格串行（Task 2 依赖 Task 1 新增的 `advance_ratio_pct` 字段语义；Task 3 依赖 Task 2 的 `get_deal_rows`）。Task 4/5/6/7 都依赖 Task 3 完成后的 `get_buyer_supplier_pairs`/`get_deal_rows`/`compute_deal_totals`，且 Task 4→5→6 都会修改 `backend/app/routes/credit.py` 同一文件，按 subagent-driven-development 的规则不并行派发实现子代理，按 Task 1→2→3→4→5→6→7→8 顺序执行。Task 8 依赖全部前序 task 完成。
