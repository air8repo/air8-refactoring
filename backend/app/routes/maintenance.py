import io
import re
from flask import render_template, request, redirect, url_for, flash, jsonify, current_app, send_file
from flask_login import login_required
from datetime import datetime
from bson.objectid import ObjectId
from backend.app.routes import maintenance_bp
from backend.app.services.batch_service import BatchService
from backend.app.services.export_service import ExportService

def get_mongo():
    """获取已初始化的mongo对象"""
    mongo = None
    
    # 首先尝试直接从extensions模块导入（最高优先级，适合测试环境）
    try:
        from backend.app.extensions import mongo as ext_mongo
        if ext_mongo is not None:
            return ext_mongo
    except Exception:
        pass
    
    # 然后尝试从app模块导入
    try:
        from backend.app import mongo as app_mongo
        if app_mongo is not None:
            return app_mongo
    except Exception:
        pass
    
    # 最后尝试从current_app.extensions获取（适合运行环境）
    try:
        if hasattr(current_app, 'extensions'):
            mongo = current_app.extensions.get('mongo')
            if mongo is not None:
                return mongo
    except Exception:
        pass
    
    return None

@maintenance_bp.route('/')
@login_required
def data_overview():
    """数据概览页面"""
    mongo = get_mongo()
    
    # 初始化统计数据
    stats = {
        'onboarding_count': 0,
        'financing_count': 0,
        'repayment_count': 0,
        'statement_count': 0,
        'overview_count': 0,
        'batch_count': 0,
        'repayment_batch_count': 0,
    }

    if mongo is not None:
        try:
            stats['onboarding_count'] = mongo.refactoring_onboard_config.count_documents({})
            stats['financing_count'] = mongo.refactoring_financing_order.count_documents({})
            stats['repayment_count'] = mongo.refactoring_repayment_order.count_documents({})
            stats['statement_count'] = mongo.refactoring_bank_statement.count_documents({})
            stats['overview_count'] = mongo.refactoring_financing_overview.count_documents({})
        except Exception:
            pass

        try:
            batch_numbers = mongo.refactoring_financing_order.distinct(
                'batch_number',
                {'batch_number': {'$exists': True, '$nin': [None, 0, '']}}
            )
            stats['batch_count'] = len(batch_numbers)
        except Exception:
            pass

        try:
            repayment_batch_dates = mongo.refactoring_bank_repayment_record.distinct('batch_date')
            stats['repayment_batch_count'] = len([d for d in repayment_batch_dates if d])
        except Exception:
            pass
    
    return render_template('maintenance/data_overview.html', stats=stats)

@maintenance_bp.route('/table/<table_name>')
@login_required
def view_table(table_name):
    """查看指定表的数据"""
    mongo = get_mongo()
    if mongo is None:
        flash('数据库未连接', 'error')
        return redirect(url_for('maintenance.data_overview'))
    
    valid_tables = {
        'onboarding': 'refactoring_onboard_config',
        'financing': 'refactoring_financing_order',
        'repayment': 'refactoring_repayment_order',
        'statement': 'refactoring_bank_statement',
        'overview': 'refactoring_financing_overview'
    }
    
    if table_name not in valid_tables:
        flash('无效的表名', 'error')
        return redirect(url_for('maintenance.data_overview'))
    
    collection_name = valid_tables[table_name]
    page = int(request.args.get('page', 1))
    per_page = 10
    skip = (page - 1) * per_page
    
    data = list(mongo[collection_name].find().skip(skip).limit(per_page))
    total = mongo[collection_name].count_documents({})
    total_pages = (total + per_page - 1) // per_page
    
    def convert_decimal128_to_float(data_item):
        if isinstance(data_item, dict):
            for key, value in data_item.items():
                if isinstance(value, dict):
                    convert_decimal128_to_float(value)
                elif isinstance(value, list):
                    for item in value:
                        convert_decimal128_to_float(item)
                elif hasattr(value, 'to_decimal'):
                    data_item[key] = float(value.to_decimal())
        return data_item
    
    converted_data = []
    for item in data:
        converted_item = convert_decimal128_to_float(item.copy())
        converted_data.append(converted_item)
    
    end_record = min(page * per_page, total)
    
    return render_template('maintenance/view_table.html', 
                         table_name=table_name,
                         collection_name=collection_name,
                         data=converted_data,
                         page=page,
                         per_page=per_page,
                         total=total,
                         end_record=end_record,
                         total_pages=total_pages)

@maintenance_bp.route('/edit/<table_name>/<string:doc_id>', methods=['GET', 'POST'])
@login_required
def edit_document(table_name, doc_id):
    """编辑文档"""
    mongo = get_mongo()
    if mongo is None:
        flash('数据库未连接', 'error')
        return redirect(url_for('maintenance.data_overview'))
    
    valid_tables = {
        'onboarding': 'refactoring_onboard_config',
        'financing': 'refactoring_financing_order',
        'repayment': 'refactoring_repayment_order',
        'statement': 'refactoring_bank_statement',
        'overview': 'refactoring_financing_overview'
    }
    
    if table_name not in valid_tables:
        flash('无效的表名', 'error')
        return redirect(url_for('maintenance.data_overview'))
    
    collection_name = valid_tables[table_name]
    
    doc = mongo[collection_name].find_one({'_id': ObjectId(doc_id)})
    
    if not doc:
        flash('文档不存在', 'error')
        return redirect(url_for('maintenance.view_table', table_name=table_name))
    
    def convert_decimal128_to_float(data_item):
        if isinstance(data_item, dict):
            for key, value in data_item.items():
                if isinstance(value, dict):
                    convert_decimal128_to_float(value)
                elif isinstance(value, list):
                    for item in value:
                        convert_decimal128_to_float(item)
                elif hasattr(value, 'to_decimal'):
                    data_item[key] = float(value.to_decimal())
        return data_item
    
    converted_doc = convert_decimal128_to_float(doc.copy())
    
    if request.method == 'POST':
        updated_data = request.form.to_dict()
        
        if table_name == 'onboarding':
            if 'approved_tenor_days' in updated_data:
                updated_data['approved_tenor_days'] = int(updated_data['approved_tenor_days'])
            if 'max_invoice_count' in updated_data:
                updated_data['max_invoice_count'] = int(updated_data['max_invoice_count'])
            updated_data.pop('created_at', None)
            updated_data['updated_at'] = datetime.now()
        elif table_name == 'financing':
            if 'expected_tenor' in updated_data:
                updated_data['expected_tenor'] = int(updated_data['expected_tenor'])
            if 'actual_tenor' in updated_data:
                updated_data['actual_tenor'] = int(updated_data['actual_tenor'])
            updated_data.pop('created_at', None)
            updated_data['updated_at'] = datetime.now()
        elif table_name == 'repayment':
            updated_data.pop('created_at', None)
            updated_data['updated_at'] = datetime.now()
        
        mongo[collection_name].update_one(
            {'_id': ObjectId(doc_id)},
            {'$set': updated_data}
        )
        
        flash('文档更新成功', 'success')
        return redirect(url_for('maintenance.view_table', table_name=table_name))
    
    return render_template('maintenance/edit_document.html', 
                         table_name=table_name,
                         doc_id=doc_id,
                         doc=converted_doc)

@maintenance_bp.route('/delete/<table_name>/<string:doc_id>')
@login_required
def delete_document(table_name, doc_id):
    """删除文档"""
    mongo = get_mongo()
    if mongo is None:
        flash('数据库未连接', 'error')
        return redirect(url_for('maintenance.data_overview'))
    
    valid_tables = {
        'onboarding': 'refactoring_onboard_config',
        'financing': 'refactoring_financing_order',
        'repayment': 'refactoring_repayment_order',
        'statement': 'refactoring_bank_statement',
        'overview': 'refactoring_financing_overview'
    }
    
    if table_name not in valid_tables:
        flash('无效的表名', 'error')
        return redirect(url_for('maintenance.data_overview'))
    
    collection_name = valid_tables[table_name]
    
    result = mongo[collection_name].delete_one({'_id': ObjectId(doc_id)})
    
    if result.deleted_count > 0:
        flash('文档删除成功', 'success')
    else:
        flash('文档删除失败', 'error')
    
    return redirect(url_for('maintenance.view_table', table_name=table_name))

@maintenance_bp.route('/add/<table_name>', methods=['GET', 'POST'])
@login_required
def add_document(table_name):
    """添加新文档"""
    mongo = get_mongo()
    if mongo is None:
        flash('数据库未连接', 'error')
        return redirect(url_for('maintenance.data_overview'))
    
    valid_tables = {
        'onboarding': 'refactoring_onboard_config',
        'financing': 'refactoring_financing_order',
        'repayment': 'refactoring_repayment_order',
        'statement': 'refactoring_bank_statement',
        'overview': 'refactoring_financing_overview'
    }
    
    if table_name not in valid_tables:
        flash('无效的表名', 'error')
        return redirect(url_for('maintenance.data_overview'))
    
    collection_name = valid_tables[table_name]
    
    if request.method == 'POST':
        new_data = request.form.to_dict()
        
        if table_name == 'onboarding':
            # 处理onboarding表字段
            if 'approved_tenor_days' in new_data:
                new_data['approved_tenor_days'] = int(new_data['approved_tenor_days'])
            if 'max_invoice_count' in new_data:
                new_data['max_invoice_count'] = int(new_data['max_invoice_count'])
            new_data['created_at'] = datetime.now()
            new_data['updated_at'] = datetime.now()
        elif table_name == 'financing':
            # 处理financing表字段
            if 'expected_tenor' in new_data:
                new_data['expected_tenor'] = int(new_data['expected_tenor'])
            if 'actual_tenor' in new_data:
                new_data['actual_tenor'] = int(new_data['actual_tenor'])
            new_data['created_at'] = datetime.now()
            new_data['updated_at'] = datetime.now()
        elif table_name == 'repayment':
            # 处理repayment表字段
            new_data['created_at'] = datetime.now()
            new_data['updated_at'] = datetime.now()
        
        # 插入新记录
        result = mongo[collection_name].insert_one(new_data)
        
        if result.inserted_id:
            flash('文档添加成功', 'success')
        else:
            flash('文档添加失败', 'error')
        
        return redirect(url_for('maintenance.view_table', table_name=table_name))
    
    return render_template('maintenance/add_document.html', 
                         table_name=table_name)



@maintenance_bp.route('/api/sync-onboarding', methods=['POST'])
@login_required
def api_sync_onboarding():
    from backend.app.services.onboarding_sync_service import run_onboarding_sync_manual
    result = run_onboarding_sync_manual()
    return jsonify(result), 200 if result.get('success') else 500


@maintenance_bp.route('/batches')
@login_required
def batch_list():
    """批次查询列表页面"""
    return render_template('maintenance/batch_list.html')


@maintenance_bp.route('/batches/<int:batch_number>')
@login_required
def batch_detail(batch_number):
    """批次融资单明细页面"""
    mongo = get_mongo()
    if mongo is None:
        flash('数据库未连接', 'error')
        return redirect(url_for('maintenance.batch_list'))

    per_page = 20
    page = request.args.get('page', 1, type=int)
    skip = (page - 1) * per_page

    query = {'batch_number': batch_number}
    total = mongo.refactoring_financing_order.count_documents(query)
    total_pages = (total + per_page - 1) // per_page

    cursor = (
        mongo.refactoring_financing_order
        .find(query)
        .sort('due_date', -1)
        .skip(skip)
        .limit(per_page)
    )

    def to_float(val):
        if val is None or val == '':
            return None
        if hasattr(val, 'to_decimal'):
            return float(val.to_decimal())
        try:
            return float(val)
        except (TypeError, ValueError):
            return None

    def fmt_date(val):
        if val and hasattr(val, 'strftime'):
            return val.strftime('%Y-%m-%d')
        return val or ''

    records = []
    for rec in cursor:
        financing_amount = to_float(rec.get('financing_amount'))
        actual_amount = to_float(rec.get('actual_financing_amount'))
        records.append({
            'finance_request_number': rec.get('finance_request_number', ''),
            'invoice_number': rec.get('invoice_number', ''),
            'buyer_name': rec.get('buyer_name', ''),
            'supplier_name': rec.get('supplier_name', ''),
            'financing_currency': rec.get('financing_currency', ''),
            'financing_amount': financing_amount,
            'actual_financing_amount': actual_amount,
            'repayment_status': rec.get('repayment_status', ''),
            'status': rec.get('status', ''),
            'due_date': fmt_date(rec.get('due_date')),
            'actual_funding_date': fmt_date(rec.get('actual_funding_date')),
        })

    end_record = min(page * per_page, total)

    return render_template(
        'maintenance/batch_detail.html',
        batch_number=batch_number,
        records=records,
        total=total,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
        end_record=end_record,
    )


@maintenance_bp.route('/repayment_batches')
@login_required
def repayment_batches_page():
    """还款批次管理页面"""
    mongo = get_mongo()
    if mongo is None:
        flash('数据库未连接', 'error')
        return redirect(url_for('maintenance.data_overview'))
    
    # 获取所有还款批次，按批次号（batch_date）分组
    repayment_batches_cursor = mongo.refactoring_bank_repayment_record.aggregate([
        {
            '$group': {
                '_id': '$batch_date',
                'bank_channel': {'$first': '$bank_channel'},
                'batch_status': {'$first': '$batch_status'},
                'record_count': {'$sum': 1},
                'created_at': {'$first': '$created_at'},
                'updated_at': {'$first': '$updated_at'}
            }
        },
        {'$sort': {'_id': -1}}  # 按批次号降序排列
    ])
    
    batches_list = list(repayment_batches_cursor)
    
    return render_template('maintenance/repayment_batches.html', batches=batches_list)

@maintenance_bp.route('/repayment_batches/void/<batch_date>', methods=['POST'])
@login_required
def void_repayment_batch(batch_date):
    """作废还款批次"""
    try:
        mongo = get_mongo()
        if mongo is None:
            flash('数据库未连接', 'error')
            return redirect(url_for('maintenance.repayment_batches_page'))
        
        # 1. 获取该批次下的所有还款记录
        repayment_records = list(mongo.refactoring_bank_repayment_record.find({'batch_date': batch_date}))
        
        if not repayment_records:
            flash('还款批次不存在', 'error')
            return redirect(url_for('maintenance.repayment_batches_page'))
        
        # 2. 删除批次记录
        delete_result = mongo.refactoring_bank_repayment_record.delete_many({'batch_date': batch_date})
        
        # 3. 清空融资单表中的还款日期
        finance_request_numbers = [record['finance_request_number'] for record in repayment_records if record.get('finance_request_number')]
        if finance_request_numbers:
            update_result = mongo.refactoring_financing_order.update_many(
                {'finance_request_number': {'$in': finance_request_numbers}},
                {'$unset': {'db_loan_settle_date': 1}}
            )
        
        flash(f'成功作废还款批次 {batch_date}，共删除 {delete_result.deleted_count} 条记录', 'success')
    except Exception as e:
        flash(f'作废还款批次时发生错误: {str(e)}', 'error')

    return redirect(url_for('maintenance.repayment_batches_page'))


@maintenance_bp.route('/repayment_batches/<batch_date>/detail')
@login_required
def repayment_batch_detail(batch_date):
    """还款批次详情页面"""
    mongo = get_mongo()
    if mongo is None:
        flash('数据库未连接', 'error')
        return redirect(url_for('maintenance.repayment_batches_page'))

    records = list(mongo.refactoring_bank_repayment_record.find(
        {'batch_date': batch_date},
        {'_id': 0}
    ).sort('seller_name', 1))

    return render_template(
        'maintenance/repayment_batch_detail.html',
        batch_date=batch_date,
        records=records
    )


def build_overview_filters(params):
    """从请求参数构建 MongoDB 查询过滤条件"""
    filters = {}

    finance_request_number = params.get('finance_request_number', '').strip()
    if finance_request_number:
        filters['finance_request_number'] = {'$regex': re.escape(finance_request_number), '$options': 'i'}

    invoice_number = params.get('invoice_number', '').strip()
    if invoice_number:
        filters['order_details.invoice_number'] = {'$regex': re.escape(invoice_number), '$options': 'i'}

    refactoring_status = params.get('refactoring_status', '').strip()
    if refactoring_status:
        filters['refactoring_status'] = refactoring_status

    buyer_name = params.get('buyer_name', '').strip()
    if buyer_name:
        filters['buyer_name'] = {'$regex': re.escape(buyer_name), '$options': 'i'}

    seller_name = params.get('seller_name', '').strip()
    if seller_name:
        filters['seller_name'] = {'$regex': re.escape(seller_name), '$options': 'i'}

    settled_in_air8 = params.get('settled_in_air8', '').strip()
    if settled_in_air8:
        filters['settled_in_air8'] = settled_in_air8

    refactor_id = params.get('refactor_id', '').strip()
    if refactor_id:
        filters['refactor_id'] = refactor_id

    return filters


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


@maintenance_bp.route('/financing-overview')
@login_required
def financing_overview_list():
    """再保理融资单列表页面"""
    mongo = get_mongo()
    if mongo is None:
        flash('数据库未连接', 'error')
        return redirect(url_for('maintenance.data_overview'))

    filters = build_overview_filters(request.args)

    page = request.args.get('page', 1, type=int)
    per_page = 20
    skip = (page - 1) * per_page

    total = mongo.refactoring_financing_overview.count_documents(filters)
    total_pages = (total + per_page - 1) // per_page
    cursor = mongo.refactoring_financing_overview.find(filters).sort('updated_at', -1).skip(skip).limit(per_page)
    raw_data = list(cursor)

    data = [flatten_overview_for_display(item) for item in raw_data]

    status_options = mongo.refactoring_financing_overview.distinct('refactoring_status')
    bank_source_options = mongo.refactoring_financing_overview.distinct('refactor_id')
    settled_options = mongo.refactoring_financing_overview.distinct('settled_in_air8')

    end_record = min(page * per_page, total)

    return render_template('maintenance/financing_overview_list.html',
        data=data, page=page, per_page=per_page, total=total,
        total_pages=total_pages, end_record=end_record,
        status_options=status_options,
        bank_source_options=bank_source_options,
        settled_options=settled_options,
        filters={k: v for k, v in request.args.items() if k != 'page'})


@maintenance_bp.route('/financing-overview/export', methods=['POST'])
@login_required
def financing_overview_export():
    """导出融资概览数据为Excel"""
    filters = build_overview_filters(request.form)

    export_service = ExportService()
    data = export_service.export_data('excel', 'overview', filters)

    if not data:
        flash('没有可导出的数据', 'warning')
        return redirect(url_for('maintenance.financing_overview_list'))

    filename = export_service.get_export_filename('excel', 'overview')
    return send_file(
        io.BytesIO(data),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=filename
    )
