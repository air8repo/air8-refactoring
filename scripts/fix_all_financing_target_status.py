import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import mongo
from datetime import datetime
from bson import Decimal128

# 修复所有融资单的target_list_status字段
def fix_all_financing_target_status():
    print("=== Fixing target_list_status for all financing orders ===")
    
    # 获取所有onboard配置数据，按uid分组
    print("1. Getting all onboard configurations...")
    onboard_configs = list(mongo.refactoring_onboard_config.find())
    onboard_by_uid = {config.get('uid'): config for config in onboard_configs}
    print(f"   Found {len(onboard_by_uid)} onboard configs")
    
    # 获取所有融资单
    print("\n2. Getting all financing orders...")
    financing_orders = list(mongo.refactoring_financing_order.find())
    total = len(financing_orders)
    print(f"   Found {total} financing orders")
    
    # 统计修复前的状态
    print("\n3. Analyzing current status...")
    before_values = {}
    for order in financing_orders:
        status = order.get('target_list_status', '')
        before_values[status] = before_values.get(status, 0) + 1
    
    print(f"   Current target_list_status distribution:")
    for status, count in before_values.items():
        print(f"     '{status}': {count}")
    
    # 执行修复
    print("\n4. Executing fix...")
    fixed_count = 0
    for i, order in enumerate(financing_orders, 1):
        record_id = order['_id']
        uid = order.get('uid', '')
        
        # 计算正确的target_list_status值
        if uid in onboard_by_uid:
            new_target_status = onboard_by_uid[uid].get('target_list_status', '')
        else:
            new_target_status = ''
        
        # 获取当前值
        current_status = order.get('target_list_status', '')
        
        # 只有当值不正确时才更新
        if current_status != new_target_status:
            # 执行更新
            mongo.refactoring_financing_order.update_one(
                {'_id': record_id},
                {
                    '$set': {
                        'target_list_status': new_target_status,
                        'in_the_onboarding_list': True if uid in onboard_by_uid else False,
                        'updated_at': datetime.now()
                    }
                }
            )
            fixed_count += 1
        
        # 显示进度
        if i % 100 == 0:
            print(f"   Processed {i}/{total} records...")
    
    # 检查修复后的状态
    print("\n5. Verifying fix...")
    after_orders = list(mongo.refactoring_financing_order.find())
    after_values = {}
    for order in after_orders:
        status = order.get('target_list_status', '')
        after_values[status] = after_values.get(status, 0) + 1
    
    print(f"   After fix target_list_status distribution:")
    for status, count in after_values.items():
        print(f"     '{status}': {count}")
    
    print(f"\n=== Fix Completed ===")
    print(f"Total records: {total}")
    print(f"Fixed records: {fixed_count}")
    print(f"Unchanged records: {total - fixed_count}")

if __name__ == "__main__":
    fix_all_financing_target_status()
