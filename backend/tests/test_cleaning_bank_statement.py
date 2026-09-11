"""
Tests for clean_bank_statement_data: DB Finance Ref is no longer required,
so rejected/cancelled (and other) invoices without a finance ref are kept.
System InvoiceID remains the only required field and the dedup key.
"""
import pandas as pd

from backend.app.services.cleaning_service import CleaningService


def test_row_without_db_ref_is_kept():
    df = pd.DataFrame([
        {'Invoice Details - System InvoiceID': 'INV-1',
         'Invoice Details - Status': 'Financing rejected',
         'Finance Details - DB Finance Ref.': None},
        {'Invoice Details - System InvoiceID': 'INV-2',
         'Invoice Details - Status': 'Financing confirmed',
         'Finance Details - DB Finance Ref.': 'REF-2'},
    ])
    out = CleaningService().clean_bank_statement_data(df)
    assert set(out['Invoice Details - System InvoiceID']) == {'INV-1', 'INV-2'}


def test_system_invoice_id_still_required():
    df = pd.DataFrame([
        {'Invoice Details - System InvoiceID': None,
         'Finance Details - DB Finance Ref.': 'REF-1'},
        {'Invoice Details - System InvoiceID': 'INV-2',
         'Finance Details - DB Finance Ref.': 'REF-2'},
    ])
    out = CleaningService().clean_bank_statement_data(df)
    assert list(out['Invoice Details - System InvoiceID']) == ['INV-2']


def test_dedup_by_seller_reference_keeps_max_system_invoice_id():
    """同一 seller_reference 多行时，保留 system_invoice_id 最大的一条。"""
    df = pd.DataFrame([
        {'Invoice Details - System InvoiceID': 100,
         'Invoice Details - Seller Reference': 'R1',
         'Invoice Details - Status': 'rejected'},
        {'Invoice Details - System InvoiceID': 200,
         'Invoice Details - Seller Reference': 'R1',
         'Invoice Details - Status': 'confirmed'},
        {'Invoice Details - System InvoiceID': 50,
         'Invoice Details - Seller Reference': 'R2',
         'Invoice Details - Status': 'rejected'},
    ])
    out = CleaningService().clean_bank_statement_data(df)
    assert len(out) == 2  # R1 去重后只剩一条
    kept = {r['Invoice Details - Seller Reference']: r['Invoice Details - System InvoiceID']
            for _, r in out.iterrows()}
    assert kept == {'R1': 200, 'R2': 50}


def test_dedup_by_system_invoice_id_keeps_last():
    df = pd.DataFrame([
        {'Invoice Details - System InvoiceID': 'INV-1',
         'Invoice Details - Status': 'old',
         'Finance Details - DB Finance Ref.': None},
        {'Invoice Details - System InvoiceID': 'INV-1',
         'Invoice Details - Status': 'new',
         'Finance Details - DB Finance Ref.': None},
    ])
    out = CleaningService().clean_bank_statement_data(df)
    assert len(out) == 1
    assert out.iloc[0]['Invoice Details - Status'] == 'new'


def test_advance_ratio_is_normalized_to_numeric():
    df = pd.DataFrame([
        {'Invoice Details - System InvoiceID': 'INV-1',
         'Finance Details - Advance Ratio': '90'},
    ])
    out = CleaningService().clean_bank_statement_data(df)
    assert out['Finance Details - Advance Ratio'].iloc[0] == 90.0
