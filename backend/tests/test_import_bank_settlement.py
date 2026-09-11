"""
Tests for ImportService._import_bank_statement storing the raw bank settlement
fields without tampering:
  - invoice.settlement_status   from 'Invoice Details - Settlement Status'
  - invoice.raw_settlement_date from 'Invoice Details - Settlement Date'
                                 (blank stays None, never datetime.now())
"""
import pandas as pd
from unittest.mock import patch, MagicMock
from datetime import datetime

from backend.app.services.import_service import ImportService


def _run_import(rows):
    df = pd.DataFrame(rows)
    mock_mongo = MagicMock()
    mock_mongo.refactoring_bank_statement.find_one.return_value = None
    with patch('backend.app.services.import_service.get_mongo', return_value=mock_mongo):
        ImportService()._import_bank_statement(df)
    # 返回所有 insert_one 调用的记录
    return [c.args[0] for c in mock_mongo.refactoring_bank_statement.insert_one.call_args_list]


def test_creation_time_uses_excel_value():
    rows = [{
        'Invoice Details - System InvoiceID': 'INV-1',
        'Invoice Details - Creation Time': datetime(2026, 4, 1, 9, 30),
        'Finance Details - Tenor': 30,
    }]
    inserted = _run_import(rows)
    assert inserted[0]['invoice']['creation_time'] == datetime(2026, 4, 1, 9, 30)


def test_creation_time_blank_stays_none_not_import_time():
    rows = [{
        'Invoice Details - System InvoiceID': 'INV-2',
        'Invoice Details - Creation Time': pd.NaT,
        'Finance Details - Tenor': 30,
    }]
    inserted = _run_import(rows)
    # 空值应保持 None，而不是被填成导入时的系统时间
    assert inserted[0]['invoice']['creation_time'] is None


def test_settlement_date_blank_stays_none_not_import_time():
    rows = [{
        'Invoice Details - System InvoiceID': 'INV-3',
        'Invoice Details - Settlement Date': pd.NaT,
        'Finance Details - Tenor': 30,
    }]
    inserted = _run_import(rows)
    # settlement_date 空值也应留空，而不是导入时的系统时间
    assert inserted[0]['invoice']['settlement_date'] is None


def test_settlement_date_uses_excel_value():
    rows = [{
        'Invoice Details - System InvoiceID': 'INV-4',
        'Invoice Details - Settlement Date': datetime(2026, 5, 28, 3, 9, 58),
        'Finance Details - Tenor': 30,
    }]
    inserted = _run_import(rows)
    assert inserted[0]['invoice']['settlement_date'] == datetime(2026, 5, 28, 3, 9, 58)


def test_settled_invoice_stores_raw_fields():
    rows = [{
        'Invoice Details - System InvoiceID': 'INV-1',
        'Invoice Details - Settlement Status': 'Settled',
        'Invoice Details - Settlement Date': datetime(2026, 5, 1),
        'Finance Details - Tenor': 30,
    }]
    inserted = _run_import(rows)
    invoice = inserted[0]['invoice']
    assert invoice['settlement_status'] == 'Settled'
    assert invoice['raw_settlement_date'] == datetime(2026, 5, 1)


def test_unsettled_invoice_keeps_blank_raw_date():
    rows = [{
        'Invoice Details - System InvoiceID': 'INV-2',
        'Invoice Details - Settlement Status': None,
        'Invoice Details - Settlement Date': pd.NaT,
        'Finance Details - Tenor': 30,
    }]
    inserted = _run_import(rows)
    invoice = inserted[0]['invoice']
    assert invoice['settlement_status'] == ''
    assert invoice['raw_settlement_date'] is None


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
