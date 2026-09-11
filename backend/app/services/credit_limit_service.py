"""额度管理 — 实时聚合服务（不落库）"""
from bson import Decimal128
from datetime import datetime
import logging

logger = logging.getLogger('credit_limit_service')


def _to_float(val):
    if val is None or val == '':
        return None
    if isinstance(val, Decimal128):
        return float(val.to_decimal())
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def get_buyer_supplier_pairs(mongo, buyer_filter=None, deals=None):
    """按买卖方配对(uid)对 get_deal_rows 的结果求和：预占、实占、待结清、Total O/S。

    Celling: refactoring_onboard_config.refactoring_limit（按 uid）
    预占/实占/待结清/Total O/S：对该 uid 下全部 deal（见 get_deal_rows）逐项求和

    deals: 可选，调用方若已算好 get_deal_rows 的结果可直接传入，避免重复查询/计算
        （不传时内部按未过滤的 get_deal_rows(mongo) 现算，行为与旧版本完全一致）。
    """
    onboard_configs = list(mongo.refactoring_onboard_config.find())
    onboard_by_uid = {c.get('uid'): c for c in onboard_configs if c.get('uid')}

    if deals is None:
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


def check_warnings(buyer_rows, pair_rows, threshold):
    """筛选占用率达到/超过阈值的买方层与买卖方配对层记录。"""
    warned_buyers = [b for b in buyer_rows if b.get('occupancy_rate') is not None and b['occupancy_rate'] >= threshold]
    warned_pairs = [p for p in pair_rows if p.get('occupancy_rate') is not None and p['occupancy_rate'] >= threshold]
    return {'buyers': warned_buyers, 'pairs': warned_pairs}


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
        if advance_ratio_pct:
            financing_amount = original_amount * (advance_ratio_pct / 100)
        else:
            financing_amount = 0.0
            logger.warning(
                'Financing Amount is 0 for invoice_number=%s: matched bank statement has no usable '
                'advance_ratio_pct (got %r) — this deal will report 0 for whichever bucket it belongs to',
                invoice_number, advance_ratio_pct,
            )
    else:
        financing_amount = _to_float(fo.get('financing_amount')) or 0.0

    status = fo.get('status') or ''
    bank_finance_status = fo.get('bank_finance_status')
    settled_in_air8 = fo.get('settled_in_air8')

    earmark_forecast = financing_amount if status == 'eligible' and bank_finance_status != 'Loan booked' else 0.0
    credit_utilization = financing_amount if bank_finance_status == 'Loan booked' else 0.0

    settlement_status = (bs.get('invoice') or {}).get('settlement_status', '') if bs is not None else ''

    to_be_settled_on_db = None
    if (settled_in_air8 == 'Settled' and bank_finance_status == 'Loan booked'
            and settlement_status != 'Settled' and repay is not None):
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
        'settlement_status': settlement_status,
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
