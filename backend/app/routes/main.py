from flask import render_template, redirect, url_for, current_app
from flask_login import login_required
from backend.app.routes import main_bp
from datetime import datetime, timedelta
from collections import defaultdict

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

@main_bp.route('/')
def index():
    """首页重定向到仪表盘"""
    return redirect(url_for('main.dashboard'))

@main_bp.route('/dashboard')
@login_required
def dashboard():
    """仪表盘页面"""
    mongo = get_mongo()
    if mongo is None:
        return "Database not connected", 500
    
    stats = {
        'financing_count': mongo.refactoring_financing_order.count_documents({}),
        'repayment_count': mongo.refactoring_repayment_order.count_documents({}),
        'statement_count': mongo.refactoring_bank_statement.count_documents({}),
        'overview_count': mongo.refactoring_financing_overview.count_documents({})
    }
    
    # Settlement Schedule 暂时隐藏，跳过查询；恢复展示时取消注释并传给模板
    # settlement_schedule = get_settlement_schedule()
    settlement_schedule = {'due_dates': [], 'totals': {}}
    
    # 获取DB Disbursement数据
    db_disbursement = get_db_disbursement()
    
    # 固定版本信息（写死为最新的git提交日期）
    latest_commit = "2026-01-27 17:30:13"
    
    return render_template(
        'dashboard.html',
        stats=stats,
        settlement_schedule=settlement_schedule,
        db_disbursement=db_disbursement,
        latest_commit=latest_commit
    )

@main_bp.route('/api/get_monthly_financing_with_statement_stats')
@login_required
def api_get_monthly_financing_with_statement_stats():
    """获取按月份统计的有对账单的融资单数据的API端点
    
    Returns:
        JSON: 包含月份列表、有对账单的融资单个数列表
    """
    from flask import request, jsonify
    
    try:
        supplier = request.args.get('supplier')
        stats = get_monthly_financing_with_statement_stats(supplier)
        
        return jsonify({
            "code": 0,
            "msg": "success",
            "data": stats
        })
    except Exception as e:
        return jsonify({
            "code": 1,
            "msg": str(e),
            "data": {}
        })

@main_bp.route('/api/get_settlement_schedule')
@login_required
def api_get_settlement_schedule():
    """获取Settlement Schedule报表数据的API端点
    
    Returns:
        JSON: Settlement Schedule报表数据
    """
    from flask import request, jsonify
    
    try:
        filter_zero = request.args.get('filter_zero', 'false').lower() == 'true'
        schedule = get_settlement_schedule(filter_zero)
        
        return jsonify({
            "code": 0,
            "msg": "success",
            "data": schedule
        })
    except Exception as e:
        return jsonify({
            "code": 1,
            "msg": str(e),
            "data": {}
        })

def get_overdue_stats():
    """获取按月份统计的逾期融资单数据
    
    Returns:
        dict: 包含月份列表、逾期个数列表和平均逾期天数列表
    """
    mongo = get_mongo()
    if mongo is None:
        return {'months': [], 'overdue_counts': [], 'avg_delay_days': []}
    
    monthly_stats = defaultdict(lambda: {
        'count': 0,
        'total_delay_days': 0,
        'delay_orders': 0
    })
    
    financing_orders = list(mongo.refactoring_financing_order.find())
    
    for order in financing_orders:
        due_date = order.get('due_date')
        settlement_date = order.get('settlement_date')
        
        if due_date and settlement_date:
            delay_days = (settlement_date - due_date).days
            
            if delay_days > 0:
                order_month = due_date.strftime('%Y-%m')
                monthly_stats[order_month]['count'] += 1
                monthly_stats[order_month]['total_delay_days'] += delay_days
                monthly_stats[order_month]['delay_orders'] += 1
    
    sorted_months = sorted(monthly_stats.keys())
    months = []
    overdue_counts = []
    avg_delay_days = []
    
    for month in sorted_months:
        months.append(month)
        overdue_counts.append(monthly_stats[month]['count'])
        
        if monthly_stats[month]['delay_orders'] > 0:
            avg = round(monthly_stats[month]['total_delay_days'] / monthly_stats[month]['delay_orders'], 2)
        else:
            avg = 0
        
        avg_delay_days.append(avg)
    
    return {
        'months': months,
        'overdue_counts': overdue_counts,
        'avg_delay_days': avg_delay_days
    }

def get_monthly_financing_with_statement_stats(supplier=None):
    """获取按月份统计的有对账单的融资单数据
    
    Args:
        supplier (str, optional): 供应商名称，用于过滤数据
    
    Returns:
        dict: 包含月份列表、有对账单的融资单个数列表
    """
    mongo = get_mongo()
    if mongo is None:
        return {'months': [], 'financing_with_statement_counts': []}
    
    monthly_stats = defaultdict(int)
    
    bank_statements = list(mongo.refactoring_bank_statement.find())
    statement_finance_request_numbers = set()
    
    for statement in bank_statements:
        finance_request_number = statement.get('finance_request_number')
        if finance_request_number:
            statement_finance_request_numbers.add(finance_request_number)
    
    query = {}
    if supplier:
        query['supplier_name'] = supplier
    
    financing_orders = list(mongo.refactoring_financing_order.find(query))
    
    for order in financing_orders:
        finance_request_number = order.get('finance_request_number')
        due_date = order.get('due_date')
        
        if finance_request_number and due_date:
            if finance_request_number in statement_finance_request_numbers:
                order_month = due_date.strftime('%Y-%m')
                monthly_stats[order_month] += 1
    
    sorted_months = sorted(monthly_stats.keys())
    months = []
    financing_with_statement_counts = []
    
    for month in sorted_months:
        months.append(month)
        financing_with_statement_counts.append(monthly_stats[month])
    
    return {
        'months': months,
        'financing_with_statement_counts': financing_with_statement_counts
    }

def get_supplier_list():
    """获取所有供应商列表
    
    Returns:
        list: 供应商列表
    """
    mongo = get_mongo()
    if mongo is None:
        return []
    
    suppliers = mongo.refactoring_financing_order.distinct('supplier_name')
    suppliers = [supplier for supplier in suppliers if supplier]
    
    return suppliers

def get_settlement_schedule(filter_zero=False):
    """获取Settlement Schedule报表数据
    
    Args:
        filter_zero (bool, optional): 是否过滤零欠款记录. Defaults to False.
    
    Returns:
        dict: Settlement Schedule报表数据
    """
    mongo = get_mongo()
    if mongo is None:
        return {'due_dates': [], 'totals': {}}
    
    # 仅统计已放款（及之后结算阶段）的记录，与重构前的 finance.status == 'Loan booked' 过滤口径保持一致
    overview_data = list(mongo.refactoring_financing_overview.find({'refactoring_status': 'Loan booked'}))
    
    # 按due_date分组汇总
    schedule = defaultdict(lambda: {
        'db_loan_amt': 0,
        'repayment_from_buyer': 0,
        'os_amt_in_db': 0,
        'settled_amt_by_air8': 0
    })
    
    for item in overview_data:
        # 从order_details中获取due_date
        order_details = item.get('order_details', {})
        due_date = order_details.get('due_date')
        
        if due_date:
            # 格式化日期为YYYY-MM-DD
            due_date_str = due_date.strftime('%Y-%m-%d')
            
            # 从文档直接获取关键数据（根据MongoDB实际结构）
            
            # 安全转换函数，处理Decimal128和其他类型
            def safe_to_float(value):
                if value is None:
                    return 0.0
                
                # 处理Decimal128类型
                from bson import Decimal128
                if isinstance(value, Decimal128):
                    return float(value.to_decimal())
                
                # 处理数值类型
                if isinstance(value, (int, float)):
                    return float(value)
                
                # 处理字符串类型
                if isinstance(value, str):
                    try:
                        return float(value)
                    except ValueError:
                        return 0.0
                
                # 其他类型尝试转换
                try:
                    return float(value)
                except (ValueError, TypeError):
                    return 0.0
            
            # 获取db_loan_amt：从totals.finance_amount_usd获取
            totals = item.get('totals', {})
            db_loan_amt = safe_to_float(totals.get('finance_amount_usd', 0))
            
            # 获取repayment_from_buyer：从repayments中汇总
            repayment_from_buyer = 0
            repayments = item.get('repayments', [])
            for repayment in repayments:
                repayment_val = repayment.get('repayment_from_buyer_to_air8')
                repayment_from_buyer += safe_to_float(repayment_val)
            
            # 获取os_amt_in_db：从totals.outstanding_amount_usd获取
            os_amt_in_db = safe_to_float(totals.get('outstanding_amount_usd', 0))
            
            # 获取settled_amt_by_air8：从totals.settled_db_loan或直接从文档获取
            settled_amt_by_air8 = safe_to_float(item.get('settled_db_loan', 0))
            
            # 如果需要过滤零欠款记录
            if not filter_zero or os_amt_in_db != 0:
                # 汇总数据
                schedule[due_date_str]['db_loan_amt'] += db_loan_amt
                schedule[due_date_str]['repayment_from_buyer'] += repayment_from_buyer
                schedule[due_date_str]['os_amt_in_db'] += os_amt_in_db
                schedule[due_date_str]['settled_amt_by_air8'] += settled_amt_by_air8
    
    # 按日期排序
    sorted_dates = sorted(schedule.keys())
    
    return {
        'due_dates': sorted_dates,
        'totals': schedule
    }


def get_db_disbursement():
    """获取DB放款报表数据
    
    Returns:
        dict: DB放款报表数据
    """
    mongo = get_mongo()
    if mongo is None:
        return {'batches': [], 'totals': {}}
    
    # 仅统计已放款（及之后结算阶段）的记录，与重构前的 finance.status == 'Loan booked' 过滤口径保持一致
    overview_data = list(mongo.refactoring_financing_overview.find({'refactoring_status': 'Loan booked'}))
    
    # 按批次号分组汇总
    disbursement = defaultdict(lambda: {
        'start_date': None,
        'finance_amount_sum': 0,
        'interest_amount_sum': 0,
        'purchase_price_sum': 0
    })
    
    for item in overview_data:
        # 获取批次号
        batch_number = item.get('loan_submission_batch')
        if not batch_number:
            continue
        
        # 从bank_statements[0]获取数据
        bank_statements = item.get('bank_statements', [])
        if bank_statements:
            bank_statement = bank_statements[0]
            
            # 安全转换函数，处理Decimal128和其他类型
            def safe_to_float(value):
                if value is None:
                    return 0.0
                
                # 处理Decimal128类型
                from bson import Decimal128
                if isinstance(value, Decimal128):
                    return float(value.to_decimal())
                
                # 处理数值类型
                if isinstance(value, (int, float)):
                    return float(value)
                
                # 处理字符串类型
                if isinstance(value, str):
                    try:
                        return float(value)
                    except ValueError:
                        return 0.0
                
                # 其他类型尝试转换
                try:
                    return float(value)
                except (ValueError, TypeError):
                    return 0.0
            
            # 获取开始日期
            start_date = bank_statement.get('start_date')
            if start_date:
                disbursement[batch_number]['start_date'] = start_date
            
            # 汇总金额
            disbursement[batch_number]['finance_amount_sum'] += safe_to_float(bank_statement.get('finance_amount', 0))
            disbursement[batch_number]['interest_amount_sum'] += safe_to_float(bank_statement.get('interest_amount_usd', 0))
            disbursement[batch_number]['purchase_price_sum'] += safe_to_float(bank_statement.get('purchase_price_usd', 0))
    
    # 按批次号排序
    sorted_batches = sorted(disbursement.keys())
    
    return {
        'batches': sorted_batches,
        'disbursement': disbursement
    }


@main_bp.route('/api/get_db_disbursement')
@login_required
def api_get_db_disbursement():
    """获取DB放款报表数据的API端点
    
    Returns:
        JSON: DB放款报表数据
    """
    from flask import jsonify
    
    try:
        disbursement_data = get_db_disbursement()
        
        return jsonify({
            "code": 0,
            "msg": "success",
            "data": disbursement_data
        })
    except Exception as e:
        return jsonify({
            "code": 1,
            "msg": str(e),
            "data": {}
        })

