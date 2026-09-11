"""一次性补发「拒绝/取消」通知邮件。

对 refactoring_bank_statement 中**当前**处于拒绝/取消、且尚未通知过
（invoice.rejected_notified_at 不存在/为空）的发票，汇总发一封邮件，
并给这些记录盖上 rejected_notified_at 日期戳，确保以后不会重复补发。

判定与日常导入完全一致（复用 import_service 的 _is_rejected_or_cancelled）：
  Invoice Details - Status 含 'rejected'（不分大小写） 或 Finance status 含 'cancelled'。

用法：
  python scripts/backfill_rejected_notification.py            # 预览（dry-run，不发邮件、不改库）
  python scripts/backfill_rejected_notification.py --send     # 真正发邮件并盖戳
"""
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from flask import current_app
from backend.app import create_app
from backend.app.services.import_service import (
    _is_rejected_or_cancelled,
    _send_loan_rejected_notification,
    _fmt_date,
)


def _build_detail(doc):
    inv = doc.get('invoice', {}) or {}
    fin = doc.get('finance', {}) or {}
    par = doc.get('parties', {}) or {}
    return {
        'invoice_no': inv.get('seller_reference', ''),
        'buyer_name': par.get('buyer_name', ''),
        'seller_name': par.get('seller_name', ''),
        'invoice_amount': str(inv.get('original_amount', '')),
        'currency': inv.get('currency', ''),
        'invoice_status': inv.get('status', ''),
        'finance_status': fin.get('status', ''),
        'rejection_reason': inv.get('validation_reason', ''),
        'creation_time': _fmt_date(inv.get('creation_time')),
        'due_date': _fmt_date(inv.get('due_date')),
    }


def main(send: bool):
    app = create_app()
    with app.app_context():
        mongo = current_app.extensions.get('mongo')
        if mongo is None:
            print('无法获取 mongo 对象，请检查数据库连接')
            sys.exit(1)

        # 先用 regex 缩小扫描范围，再用统一判定函数二次确认
        query = {
            '$or': [
                {'invoice.status': {'$regex': 'rejected', '$options': 'i'}},
                {'finance.status': {'$regex': 'cancelled', '$options': 'i'}},
                {'invoice.status': {'$regex': '^financing confirmed$', '$options': 'i'},
                 'finance.status': {'$regex': '^(booking requested accepted|loan booking failed)$',
                                    '$options': 'i'}},
            ]
        }
        candidates = list(mongo.refactoring_bank_statement.find(query))

        to_notify = []
        for doc in candidates:
            inv = doc.get('invoice', {}) or {}
            fin = doc.get('finance', {}) or {}
            if not _is_rejected_or_cancelled(inv.get('status', ''), fin.get('status', '')):
                continue
            if inv.get('rejected_notified_at'):  # 已通知过，跳过
                continue
            to_notify.append(doc)

        print(f'命中拒绝/取消（regex 初筛）：{len(candidates)} 条')
        print(f'其中尚未通知、需补发：{len(to_notify)} 条')

        if not to_notify:
            print('没有需要补发的记录，结束。')
            return

        details = [_build_detail(d) for d in to_notify]
        # 预览前若干条
        for d in details[:10]:
            print(f"  - {d['invoice_no']} | {d['invoice_status']} / {d['finance_status']} "
                  f"| {d['buyer_name']} -> {d['seller_name']} | reason={d['rejection_reason']}")
        if len(details) > 10:
            print(f'  ... 其余 {len(details) - 10} 条略')

        if not send:
            print('\n[dry-run] 未发送邮件、未改库。确认无误后加 --send 执行。')
            return

        # 真正发送（一封汇总邮件）
        _send_loan_rejected_notification(details)
        print(f'已发送补发通知邮件，共 {len(details)} 条。')

        # 盖日期戳，避免以后重复补发
        stamp = datetime.now()
        ids = [d['_id'] for d in to_notify]
        result = mongo.refactoring_bank_statement.update_many(
            {'_id': {'$in': ids}},
            {'$set': {'invoice.rejected_notified_at': stamp}},
        )
        print(f'已盖日期戳：matched={result.matched_count}, modified={result.modified_count}')


if __name__ == '__main__':
    send_flag = '--send' in sys.argv[1:]
    main(send=send_flag)
