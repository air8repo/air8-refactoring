from flask import jsonify, request, current_app
from functools import wraps
from bson import Decimal128
from backend.app.routes import api_bp


def require_token(f):
    """固定 Token 鉴权装饰器"""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('X-API-Token') or request.args.get('token')
        expected = current_app.config.get('API_TOKEN')
        if not token or token != expected:
            return jsonify({'success': False, 'message': 'Unauthorized'}), 401
        return f(*args, **kwargs)
    return decorated


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


def _to_json_safe(value):
    """将 Decimal128 / datetime 等转为 JSON 可序列化类型"""
    if isinstance(value, Decimal128):
        return float(value.to_decimal())
    if hasattr(value, 'isoformat'):  # datetime / date
        return value.isoformat()
    return value


# ──────────────────────────────────────────────
# Endpoint 1: 查询 wip_pending > 0 的融资单
# ──────────────────────────────────────────────
@api_bp.route('/financing/wip-pending', methods=['GET'])
@require_token
def get_wip_pending_orders():
    """
    返回所有 wip_pending > 0 的融资单。
    鉴权: Header X-API-Token 或 Query Param token
    """
    mongo = _get_mongo()
    if mongo is None:
        return jsonify({'success': False, 'message': 'Database not connected'}), 500

    FIELDS = [
        'finance_request_number', 'invoice_number', 'supplier_name', 'supplier_code',
        'buyer_name', 'buyer_code', 'financing_amount', 'financing_currency',
        'wip_pending', 'settled_in_air8', 'status', 'bank_finance_status',
        'actual_funding_date', 'due_date',
    ]

    raw_orders = list(
        mongo.refactoring_financing_order
        .find({'wip_pending': {'$gt': 0}}, {'_id': 0})
        .sort('due_date', 1)
    )

    orders = [{f: _to_json_safe(order.get(f)) for f in FIELDS} for order in raw_orders]

    return jsonify({'success': True, 'total': len(orders), 'data': orders})


# ──────────────────────────────────────────────
# Endpoint 2: 查询 onboard config
# ──────────────────────────────────────────────
@api_bp.route('/onboard-config', methods=['GET'])
@require_token
def get_onboard_config():
    """
    返回 refactoring_onboard_config 表中所有记录。
    鉴权: Header X-API-Token 或 Query Param token
    """
    mongo = _get_mongo()
    if mongo is None:
        return jsonify({'success': False, 'message': 'Database not connected'}), 500

    FIELDS = [
        'uid', 'air8_buyer_id', 'obligor_name', 'country',
        'air8_seller_id', 'seller_name', 'target_list_status',
        'approved_tenor_days', 'max_invoice_count', 'remarks',
        'first_submit_date', 'created_at', 'updated_at',
    ]

    raw_records = list(
        mongo.refactoring_onboard_config.find({}, {'_id': 0})
    )

    records = [{f: _to_json_safe(r.get(f)) for f in FIELDS} for r in raw_records]

    return jsonify({'success': True, 'total': len(records), 'data': records})


# ──────────────────────────────────────────────
# Endpoint 5: 查询 target_list_status='Y' 的 onboard config
# ──────────────────────────────────────────────
@api_bp.route('/onboard-config/active', methods=['GET'])
@require_token
def get_active_onboard_config():
    """
    返回 refactoring_onboard_config 表中 target_list_status='Y' 的记录。
    鉴权: Header X-API-Token 或 Query Param token
    """
    mongo = _get_mongo()
    if mongo is None:
        return jsonify({'success': False, 'message': 'Database not connected'}), 500

    FIELDS = [
        'uid', 'air8_buyer_id', 'obligor_name', 'country',
        'air8_seller_id', 'seller_name', 'target_list_status',
        'approved_tenor_days', 'max_invoice_count', 'remarks',
        'first_submit_date', 'created_at', 'updated_at',
    ]

    raw_records = list(
        mongo.refactoring_onboard_config.find(
            {'target_list_status': 'Y'}, {'_id': 0}
        )
    )

    records = [{f: _to_json_safe(r.get(f)) for f in FIELDS} for r in raw_records]

    return jsonify({'success': True, 'total': len(records), 'data': records})


# ──────────────────────────────────────────────
# Endpoint 3: 刷新融资单
# ──────────────────────────────────────────────
@api_bp.route('/financing/refresh', methods=['POST'])
@require_token
def refresh_financing_orders():
    """
    触发刷新所有融资单（与 export 页面刷新按钮逻辑相同）。
    鉴权: Header X-API-Token 或 Query Param token
    """
    try:
        from backend.app.services.import_service import ImportService
        result = ImportService().refresh_all_financing_records()
        status_code = 200 if result.get('success') else 500
        return jsonify(result), status_code
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


# ──────────────────────────────────────────────
# Endpoint 4: 从 API 导入数据（还款单 / 融资单）
# ──────────────────────────────────────────────
@api_bp.route('/import/from-api', methods=['POST'])
@require_token
def import_from_api():
    """
    触发从 n8n webhook 拉取数据并导入 MongoDB。
    鉴权: Header X-API-Token 或 Query Param token
    Body (JSON 或 form): import_type = 'repayment' | 'financing'
    """
    # 兼容 JSON body 和 form 两种传参方式
    if request.is_json:
        import_type = (request.json or {}).get('import_type')
    else:
        import_type = request.form.get('import_type')

    if not import_type:
        return jsonify({'success': False, 'message': '请提供 import_type 参数 (repayment 或 financing)'}), 400

    try:
        from backend.app.services.import_service import ImportService
        result = ImportService().import_from_api(import_type)
        status_code = 200 if result.get('success') else 500
        return jsonify(result), status_code
    except Exception as e:
        return jsonify({'success': False, 'message': f'API导入过程中发生错误: {str(e)}'}), 500


# ──────────────────────────────────────────────
# Endpoint 6: 查询 bank statement
# ──────────────────────────────────────────────
def _serialize_bank_statement(doc):
    """将 bank statement 文档的嵌套结构扁平化为 JSON 可序列化字典"""
    parties = doc.get('parties') or {}
    invoice = doc.get('invoice') or {}
    finance = doc.get('finance') or {}
    usd = doc.get('usd_details') or {}
    return {
        'bank_channel': doc.get('bank_channel'),
        # parties
        'buyer_name': _to_json_safe(parties.get('buyer_name')),
        'seller_name': _to_json_safe(parties.get('seller_name')),
        'buyer_erp_id': _to_json_safe(parties.get('buyer_erp_id')),
        'seller_erp_id': _to_json_safe(parties.get('seller_erp_id')),
        # invoice
        'system_invoice_id': invoice.get('system_invoice_id'),
        'invoice_status': invoice.get('status'),
        'validation_reason': invoice.get('validation_reason'),
        'issue_date': _to_json_safe(invoice.get('issue_date')),
        'due_date': _to_json_safe(invoice.get('due_date')),
        'adjusted_due_date': _to_json_safe(invoice.get('adjusted_due_date')),
        'seller_reference': invoice.get('seller_reference'),
        'currency': invoice.get('currency'),
        'original_amount': _to_json_safe(invoice.get('original_amount')),
        # 结清状态 / 结清日期：输出未经篡改的银行原始字段。
        # raw_settlement_date 为新增 raw 字段，旧记录无此字段时回退到 settlement_date。
        'settlement_status': invoice.get('settlement_status', ''),
        'settlement_date': _to_json_safe(
            invoice.get('raw_settlement_date')
            if 'raw_settlement_date' in invoice
            else invoice.get('settlement_date')
        ),
        'creation_time': _to_json_safe(invoice.get('creation_time')),
        'vat_rate': _to_json_safe(invoice.get('vat_rate')),
        'vat_amount': _to_json_safe(invoice.get('vat_amount')),
        # finance
        'finance_status': finance.get('status'),
        'db_finance_ref': finance.get('db_finance_ref'),
        'finance_start_date': _to_json_safe(finance.get('start_date')),
        'finance_due_date': _to_json_safe(finance.get('due_date')),
        'tenor': finance.get('tenor'),
        'finance_amount': _to_json_safe(finance.get('finance_amount')),
        'outstanding_amount': _to_json_safe(finance.get('outstanding_amount')),
        'reference_rate_pct': _to_json_safe(finance.get('reference_rate_pct')),
        'interest_rate_pct': _to_json_safe(finance.get('interest_rate_pct')),
        'interest_amount': _to_json_safe(finance.get('interest_amount')),
        'purchase_price': _to_json_safe(finance.get('purchase_price')),
        # usd_details
        'usd_original_amount': _to_json_safe(usd.get('original_amount')),
        'usd_finance_amount': _to_json_safe(usd.get('finance_amount')),
        'usd_outstanding_amount': _to_json_safe(usd.get('outstanding_amount')),
        'usd_interest_amount': _to_json_safe(usd.get('interest_amount')),
        'usd_purchase_price': _to_json_safe(usd.get('purchase_price')),
        # timestamps
        'created_at': _to_json_safe(doc.get('created_at')),
        'updated_at': _to_json_safe(doc.get('updated_at')),
    }


@api_bp.route('/bank-statement', methods=['POST'])
@require_token
def get_bank_statements():
    """
    返回 refactoring_bank_statement 表中的记录，支持分页。
    鉴权: Header X-API-Token 或 Query Param token
    Body (JSON，均可选):
      invoice_ids — 发票编号列表 (list)，匹配 invoice.system_invoice_id
      buyer       — parties.buyer_name 精确匹配
      supplier    — parties.seller_name 精确匹配
      pageNum     — 页码，从 1 开始，默认 1
      pageSize    — 每页条数，默认 20，最大 200
    """
    mongo = _get_mongo()
    if mongo is None:
        return jsonify({'success': False, 'message': 'Database not connected'}), 500

    body = request.get_json(silent=True) or {}

    # 过滤条件
    query = {}
    invoice_ids = body.get('invoice_ids')
    if invoice_ids and isinstance(invoice_ids, list):
        ids = [x for x in invoice_ids if x]
        if ids:
            query['invoice.system_invoice_id'] = {'$in': ids}
    buyer = (body.get('buyer') or '').strip()
    if buyer:
        query['parties.buyer_name'] = buyer
    supplier = (body.get('supplier') or '').strip()
    if supplier:
        query['parties.seller_name'] = supplier

    # 分页参数
    try:
        page_num = max(1, int(body.get('pageNum', 1)))
        page_size = min(5000, max(1, int(body.get('pageSize', 200))))
    except (ValueError, TypeError):
        return jsonify({'success': False, 'message': 'pageNum 和 pageSize 必须为整数'}), 400

    total = mongo.refactoring_bank_statement.count_documents(query)
    import math
    pages = math.ceil(total / page_size) if total > 0 else 0
    skip = (page_num - 1) * page_size

    raw_docs = list(
        mongo.refactoring_bank_statement.find(query, {'_id': 0})
        .skip(skip)
        .limit(page_size)
    )
    records = [_serialize_bank_statement(doc) for doc in raw_docs]

    return jsonify({
        'success': True,
        'total': total,
        'pages': pages,
        'pageNum': page_num,
        'pageSize': page_size,
        'data': records,
    })
