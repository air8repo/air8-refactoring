import io
from datetime import datetime
from flask import render_template, request, current_app, send_file, flash, redirect, url_for
from flask_login import login_required
from backend.app.routes import credit_bp
from backend.app.services.credit_limit_service import (
    get_buyer_supplier_pairs, aggregate_by_buyer, get_pair_deal_rows, compute_deal_totals, get_deal_rows,
)
from backend.app.services.credit_export_service import build_credit_limit_workbook, build_deal_detail_workbook

_PER_PAGE = 20


def get_mongo():
    try:
        from backend.app.extensions import mongo as ext_mongo
        if ext_mongo is not None:
            return ext_mongo
    except Exception:
        pass
    try:
        from backend.app import mongo as app_mongo
        if app_mongo is not None:
            return app_mongo
    except Exception:
        pass
    try:
        if hasattr(current_app, 'extensions'):
            mongo = current_app.extensions.get('mongo')
            if mongo is not None:
                return mongo
    except Exception:
        pass
    return None


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


@credit_bp.route('/export', methods=['POST'])
@login_required
def credit_export():
    mongo = get_mongo()
    buyer_filter = request.form.get('buyer_name', '').strip()

    if mongo is None:
        flash('没有找到符合条件的数据', 'warning')
        return redirect(url_for('credit.credit_query', buyer_name=buyer_filter))

    try:
        deal_rows = get_deal_rows(mongo, buyer_filter=buyer_filter or None)
        pairs = get_buyer_supplier_pairs(mongo, buyer_filter=buyer_filter or None, deals=deal_rows)
        buyer_rows = aggregate_by_buyer(pairs)
    except Exception as e:
        flash(str(e), 'danger')
        return redirect(url_for('credit.credit_query', buyer_name=buyer_filter))

    if not buyer_rows:
        flash('没有找到符合条件的数据', 'warning')
        return redirect(url_for('credit.credit_query', buyer_name=buyer_filter))

    workbook_bytes = build_credit_limit_workbook(buyer_rows, pairs, deal_rows)
    filename = f"credit_limit_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return send_file(
        io.BytesIO(workbook_bytes),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=filename,
    )


def _fmt_date(val):
    if val and hasattr(val, 'strftime'):
        return val.strftime('%Y-%m-%d')
    return val or ''


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


@credit_bp.route('/api/trigger-warning-check', methods=['POST'])
@login_required
def trigger_warning_check():
    from backend.app.services.credit_warning_service import run_warning_check_manual
    from flask import jsonify
    result = run_warning_check_manual()
    status_code = 200 if result.get('success') else 500
    return jsonify(result), status_code
