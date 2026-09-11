"""
Tests for rejected/cancelled-invoice email notification on bank statement import.

Trigger (case-insensitive): invoice.status contains 'rejected'
                            OR finance.status contains 'cancelled'.
Only a *newly* rejected/cancelled invoice (not previously in that state, and not
yet notified) triggers one aggregated email. Dedup identity is the bank statement
key invoice.system_invoice_id (invoice_no). Notify once only.
Email lists: invoice_no, buyer/seller, db_finance_ref, amount, due date,
both status fields (invoice + finance) and the rejection reason
(Invoice Details - Validation Status Reason).
"""
import pandas as pd
from unittest.mock import patch, MagicMock

from backend.app.services.import_service import (
    ImportService,
    _send_loan_rejected_notification,
)


def _row(invoice_id, inv_status='Financing in progress', fin_status='Loan booked',
         buyer='B', seller='S', reason='Buyer credit insufficient', seller_ref=None):
    return {
        'Invoice Details - System InvoiceID': invoice_id,
        'Invoice Details - Seller Reference': seller_ref or ('SR-' + invoice_id),
        'Invoice Details - Status': inv_status,
        'Invoice Details - Validation Status Reason': reason,
        'Invoice Details - Original Amount': 12345,
        'Invoice Details - Creation Time': '2026-05-01',
        'Parties Details - Buyer Name': buyer,
        'Parties Details - Seller Name': seller,
        'Invoice Details - Currency': 'USD',
        'Finance Details - Financing in statuses': fin_status,
        'Finance Details - DB Finance Ref.': 'REF-' + invoice_id,
        'Finance Details - Finance Amount': 1000,
        'Finance Details - Tenor': 30,
    }


def _import(rows, existing_by_ref=None, capture_saved=False):
    """运行导入，返回 (传给通知函数的 records, 是否调用了通知)。
    existing_by_ref 按 invoice.seller_reference 索引旧记录。
    capture_saved=True 时额外返回入库的 mapped_record 列表。"""
    existing_by_ref = existing_by_ref or {}
    df = pd.DataFrame(rows)
    mock_mongo = MagicMock()
    mock_mongo.refactoring_bank_statement.find_one.side_effect = \
        lambda q: existing_by_ref.get(q.get('invoice.seller_reference'))
    mock_mongo.refactoring_onboard_config.find_one.return_value = None

    with patch('backend.app.services.import_service.get_mongo', return_value=mock_mongo), \
         patch('backend.app.services.import_service._send_loan_rejected_notification') as mock_notify:
        ImportService()._import_bank_statement(df)

    records = mock_notify.call_args.args[0] if mock_notify.called else []
    if capture_saved:
        saved = [c.args[0] for c in mock_mongo.refactoring_bank_statement.insert_one.call_args_list]
        saved += [c.args[1] for c in mock_mongo.refactoring_bank_statement.replace_one.call_args_list]
        return records, mock_notify.called, saved
    return records, mock_notify.called


def test_invoice_status_rejected_triggers():
    records, called, saved = _import(
        [_row('INV-1', inv_status='Financing rejected')], capture_saved=True)
    assert called is True
    r = records[0]
    assert r['invoice_no'] == 'SR-INV-1'           # Invoice No 取 seller_reference
    assert r['invoice_amount'] == '12345'          # 发票金额 = Original Amount
    assert r['creation_time'] == '2026-05-01'      # 新增 Creation Time
    assert r['invoice_status'] == 'Financing rejected'
    assert r['rejection_reason'] == 'Buyer credit insufficient'
    assert 'db_finance_ref' not in r               # DB Finance Ref 已去掉
    assert saved[0]['invoice']['rejected_notified_at'] is not None


def test_invoice_status_rejected_case_insensitive():
    """大小写不敏感 + 子串匹配：'REJECTED'、'partially Rejected' 都触发。"""
    records, called = _import([_row('INV-1', inv_status='Partially REJECTED')])
    assert called is True


def test_finance_status_cancelled_triggers():
    records, called = _import(
        [_row('INV-2', inv_status='Financing in progress', fin_status='Cancelled')])
    assert called is True
    assert records[0]['invoice_no'] == 'SR-INV-2'


def test_confirmed_booking_requested_accepted_triggers():
    records, called = _import(
        [_row('INV-1', inv_status='Financing confirmed', fin_status='Booking requested accepted')])
    assert called is True


def test_confirmed_loan_booking_failed_triggers():
    records, called = _import(
        [_row('INV-1', inv_status='Financing confirmed', fin_status='Loan booking failed')])
    assert called is True


def test_confirmed_loan_booked_no_email():
    records, called = _import(
        [_row('INV-1', inv_status='Financing confirmed', fin_status='Loan booked')])
    assert called is False


def test_neither_rejected_nor_cancelled_no_email():
    records, called = _import(
        [_row('INV-1', inv_status='Financing in progress', fin_status='Loan booked')])
    assert called is False


def test_already_rejected_not_renotified():
    """全量重导：已是 rejected 不再提醒（按 seller_reference 匹配旧记录）。"""
    existing = {'SR-INV-1': {'_id': 1, 'created_at': 'x',
                             'invoice': {'status': 'Financing rejected'},
                             'finance': {'status': 'Loan booked'}}}
    records, called = _import([_row('INV-1', inv_status='Financing rejected')], existing)
    assert called is False


def test_previously_notified_stamp_preserved():
    from datetime import datetime
    stamp = datetime(2026, 6, 1)
    existing = {'SR-INV-1': {'_id': 1, 'created_at': 'x',
                             'invoice': {'status': 'Financing rejected',
                                         'rejected_notified_at': stamp},
                             'finance': {'status': 'Loan booked'}}}
    records, called, saved = _import([_row('INV-1', inv_status='Financing rejected')],
                                     existing, capture_saved=True)
    assert called is False
    assert saved[0]['invoice']['rejected_notified_at'] == stamp


def test_transition_to_rejected_triggers():
    existing = {'SR-INV-1': {'_id': 1, 'created_at': 'x',
                             'invoice': {'status': 'Financing in progress'},
                             'finance': {'status': 'Loan booked'}}}
    records, called = _import([_row('INV-1', inv_status='Financing rejected')], existing)
    assert called is True


def test_notification_posts_to_n8n(app):
    """helper 应向 n8n-v2 通用邮件接口 POST，body 含明细、双状态与拒绝原因。"""
    records = [{
        'invoice_no': 'SR-9', 'buyer_name': 'Buyer', 'seller_name': 'Seller',
        'invoice_amount': '12345', 'currency': 'USD',
        'invoice_status': 'Financing rejected', 'finance_status': 'Cancelled',
        'rejection_reason': 'Credit limit exceeded',
        'creation_time': '2026-04-01', 'due_date': '2026-05-01',
    }]
    with app.app_context():
        with patch('requests.post') as mock_post:
            mock_post.return_value = MagicMock(status_code=200, text='ok')
            ok = _send_loan_rejected_notification(records)

    assert ok is True
    assert mock_post.called
    args, kwargs = mock_post.call_args
    assert (args[0] if args else kwargs.get('url')) == \
        'https://n8n-v2.air8.cn/webhook/commonSendEmailForRefactoring'
    payload = kwargs['json']
    assert payload['type'] == 'common'
    assert 'SR-9' in payload['body']             # Invoice No = seller_reference
    assert '12345' in payload['body']            # 发票金额
    assert '2026-04-01' in payload['body']       # Creation Time
    assert 'Credit limit exceeded' in payload['body']
    assert 'Cancelled' in payload['body']
    assert not kwargs.get('params')
