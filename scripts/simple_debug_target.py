import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import mongo
from bson import Decimal128
from datetime import datetime

# 简单调试脚本，检查target_list_status字段
def simple_debug_target():
    print("=== Simple Debug for target_list_status ===")
    
    # 1. 检查onboard配置
    print("\n1. Checking onboard configurations...")
    # 获取一个已知存在的UID
    test_uid = 'C0000505C0000755'
    onboard_config = mongo.refactoring_onboard_config.find_one({'uid': test_uid})
    if onboard_config:
        print(f"   Found onboard config for UID '{test_uid}'")
        print(f"   target_list_status: '{onboard_config.get('target_list_status', '')}'")
    else:
        print(f"   No onboard config found for UID '{test_uid}'")
        
    # 2. 创建一个测试融资单记录
    print("\n2. Creating test financing record...")
    test_finance_number = 'SIMPLE-TEST-001'
    
    # 清理之前的测试记录
    mongo.refactoring_financing_order.delete_one({'finance_request_number': test_finance_number})
    
    # 创建新记录
    record = {
        'uid': test_uid,
        'finance_request_number': test_finance_number,
        'invoice_number': 'SIMPLE-INV-001',
        'cross_ref_inv_no': '',
        'reference_no': '',
        'order_no': '',
        'in_the_onboarding_list': False,
        'target_list_status': 'PENDING',  # 初始值
        'is_batch': False,
        'funded_before': False,
        'status': '',
        'can_push_to_db_today': False,
        'auto_finance': False,
        'supplier_name': 'Test Supplier',
        'supplier_code': 'C0000755',
        'buyer_name': 'Test Buyer',
        'buyer_code': 'C0000505',
        'funder_name': '',
        'funder_code': '',
        'channel_source': '',
        'insurer': '',
        'trade_amount': Decimal128('1000'),
        'financing_amount_trade_currency': Decimal128('800'),
        'financing_amount': Decimal128('800'),
        'actual_financing_amount': Decimal128('800'),
        'settled_amt_partial': Decimal128('0'),
        'trade_currency': 'USD',
        'financing_currency': 'USD',
        'exchange_rate': Decimal128('1.0'),
        'interest_calculation_method': '',
        'interest_rate_fee_charge': Decimal128('0.05'),
        'expected_tenor': 30,
        'actual_tenor': 30,
        'invoice_date': datetime.now(),
        'due_tenor': 30,
        'due_credit_limit': Decimal128('10000'),
        'due_date': datetime.now(),
        'request_date': datetime.now(),
        'expected_funding_date': datetime.now(),
        'actual_funding_date': datetime.now(),
        'actual_shipment_date': datetime.now(),
        'fr_overdue_in_coming_period': False,
        'due_date_vs_submission_date': False,
        'created_at': datetime.now(),
        'updated_at': datetime.now()
    }
    
    result = mongo.refactoring_financing_order.insert_one(record)
    inserted_id = result.inserted_id
    print(f"   Created test record with ID: {inserted_id}")
    
    # 3. 检查初始状态
    print("\n3. Checking initial record status...")
    initial_record = mongo.refactoring_financing_order.find_one({'_id': inserted_id})
    if initial_record:
        print(f"   Initial target_list_status: '{initial_record.get('target_list_status', '')}'")
    
    # 4. 手动执行target_list_status更新逻辑
    print("\n4. Manually updating target_list_status...")
    
    # 获取所有onboard配置
    onboard_configs = list(mongo.refactoring_onboard_config.find())
    onboard_by_uid = {config.get('uid'): config for config in onboard_configs}
    print(f"   Found {len(onboard_by_uid)} onboard configs")
    
    # 检查UID是否在onboard配置中
    if test_uid in onboard_by_uid:
        print(f"   UID '{test_uid}' found in onboard configs")
        # 获取onboard配置中的target_list_status
        new_target_status = onboard_by_uid[test_uid].get('target_list_status', '')
        print(f"   New target_list_status from onboard: '{new_target_status}'")
        
        # 更新记录
        update_result = mongo.refactoring_financing_order.update_one(
            {'_id': inserted_id},
            {
                '$set': {
                    'target_list_status': new_target_status,
                    'updated_at': datetime.now()
                }
            }
        )
        print(f"   Update result: matched {update_result.matched_count}, modified {update_result.modified_count}")
    else:
        print(f"   UID '{test_uid}' not found in onboard configs")
    
    # 5. 检查更新后的状态
    print("\n5. Checking updated record status...")
    updated_record = mongo.refactoring_financing_order.find_one({'_id': inserted_id})
    if updated_record:
        print(f"   Updated target_list_status: '{updated_record.get('target_list_status', '')}'")
    
    # 6. 清理测试数据
    print("\n6. Cleaning up test data...")
    mongo.refactoring_financing_order.delete_one({'_id': inserted_id})
    print("   Test data cleaned up")
    
    print("\n=== Simple Debug Completed ===")

if __name__ == "__main__":
    simple_debug_target()
