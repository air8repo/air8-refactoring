import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app import create_app
from backend.app import extensions, mongo
from bson import Decimal128
from decimal import Decimal
from datetime import datetime

app = create_app()

with app.app_context():
    # 初始化扩展
    extensions.init_extensions(app)
    
    # 获取mongo_db对象
    mongo_db = extensions.mongo
    
    print("=" * 80)
    print("修复融资订单Status逻辑")
    print("=" * 80)
    
    # 获取所有onboard配置数据，按uid分组
    onboard_configs = list(mongo_db.refactoring_onboard_config.find())
    onboard_by_uid = {config.get('uid'): config for config in onboard_configs}
    print(f"找到 {len(onboard_by_uid)} 条onboard配置记录")
    
    # 获取所有repayment_order数据，按finance_request_number分组
    repayment_orders = list(mongo_db.refactoring_repayment_order.find())
    repayment_by_finance = {repayment.get('finance_request_number'): repayment for repayment in repayment_orders}
    print(f"找到 {len(repayment_by_finance)} 条还款记录")
    
    # 获取所有financing_overview数据，按invoice_number分组
    financing_overviews = list(mongo_db.refactoring_financing_overview.find())
    overview_by_invoice = {overview.get('order_details', {}).get('invoice_number'): overview for overview in financing_overviews}
    print(f"找到 {len(overview_by_invoice)} 条概览记录")
    
    # 获取所有融资订单
    financing_orders = list(mongo_db.refactoring_financing_order.find())
    print(f"找到 {len(financing_orders)} 条融资订单记录")
    
    # 辅助函数：检查Decimal128值是否接近0
    def is_zero(value):
        if value is None:
            return True
        if isinstance(value, Decimal128):
            return value.to_decimal() == Decimal('0')
        return value == 0 or value == Decimal('0')
    
    # 获取当前日期
    today = datetime.now().date()
    
    updated_count = 0
    skipped_count = 0
    
    print("\n开始处理...")
    
    for order in financing_orders:
        record_id = order['_id']
        uid = order.get('uid', '')
        finance_request_number = order.get('finance_request_number', '')
        invoice_number = order.get('invoice_number', '')
        due_date = order.get('due_date')
        
        # 计算字段值
        # in_the_onboarding_list
        in_the_onboarding_list = True if uid in onboard_by_uid else False
        
        # target_list_status
        target_list_status = onboard_by_uid[uid].get('target_list_status', '') if uid in onboard_by_uid else ''
        
        # is_batch
        overview = overview_by_invoice.get(invoice_number, {})
        loan_submission_batch = overview.get('loan_submission_batch', '')
        is_batch = bool(loan_submission_batch)
        
        # funded_before
        funded_before = True if overview.get('financing_amount', 0) > 0 else False
        
        # settled_amt_partial
        repayment = repayment_by_finance.get(finance_request_number, {})
        settled_amt_partial = repayment.get('cumulative_repayment', Decimal128('0'))
        
        # fr_overdue_in_coming_period
        fr_overdue_in_coming_period = False
        if due_date:
            due_date_only = due_date.date() if hasattr(due_date, 'date') else due_date
            fr_overdue_in_coming_period = True if (due_date_only - today).days < 0 else False
        
        # due_date_vs_submission_date
        due_date_vs_submission_date = False
        if uid in onboard_by_uid:
            onboard_config = onboard_by_uid[uid]
            approved_tenor = onboard_config.get('approved_tenor_days', 0)
            if due_date:
                due_date_only = due_date.date() if hasattr(due_date, 'date') else due_date
                days_diff = (due_date_only - today).days
                due_date_vs_submission_date = True if days_diff > approved_tenor else False
        
        # Status计算
        status = ''
        if target_list_status == 'Pending':
            status = 'for next phase'
        elif target_list_status != 'Y':
            status = 'not on the list / Code mismatch'
        elif funded_before:
            status = 'funded before'
        elif fr_overdue_in_coming_period:
            status = 'OD related'
        elif due_date_vs_submission_date:
            status = 'Finance Tenor Exceed DB approved, pls resubmit later'
        elif is_zero(settled_amt_partial):
            status = 'eligible'
        else:
            status = 'partial paid'
        
        # can_push_to_db_today
        can_push_to_db_today = True if status == 'eligible' else False
        
        # 检查是否需要更新
        current_status = order.get('status', '')
        if current_status != status or order.get('can_push_to_db_today', False) != can_push_to_db_today:
            # 更新记录
            mongo_db.refactoring_financing_order.update_one(
                {'_id': record_id},
                {
                    '$set': {
                        'in_the_onboarding_list': in_the_onboarding_list,
                        'target_list_status': target_list_status,
                        'is_batch': is_batch,
                        'funded_before': funded_before,
                        'settled_amt_partial': settled_amt_partial,
                        'fr_overdue_in_coming_period': fr_overdue_in_coming_period,
                        'due_date_vs_submission_date': due_date_vs_submission_date,
                        'status': status,
                        'can_push_to_db_today': can_push_to_db_today,
                        'updated_at': datetime.now()
                    }
                }
            )
            updated_count += 1
        else:
            skipped_count += 1
    
    print(f"\n处理完成!")
    print(f"  更新: {updated_count} 条记录")
    print(f"  跳过: {skipped_count} 条记录")
    
    # 验证修复结果
    test_order = mongo_db.refactoring_financing_order.find_one({'finance_request_number': 'RZ202512110000000094'})
    if test_order:
        print(f"\n修复验证:")
        print(f"  订单: RZ202512110000000094")
        print(f"  target_list_status: '{test_order.get('target_list_status', '')}'")
        print(f"  funded_before: {test_order.get('funded_before', False)}")
        print(f"  settled_amt_partial: {test_order.get('settled_amt_partial', '')}")
        print(f"  status: '{test_order.get('status', '')}'")
        print(f"  can_push_to_db_today: {test_order.get('can_push_to_db_today', False)}")
        
        if test_order.get('status') == 'eligible':
            print("\n✓ 修复成功！status现在是eligible")
        else:
            print(f"\n✗ 修复未完全成功，status仍然是 '{test_order.get('status', '')}'")
    else:
        print("未找到指定的测试订单")
