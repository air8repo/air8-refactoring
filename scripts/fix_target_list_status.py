import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import mongo
from datetime import datetime

# 修复所有融资单的target_list_status字段
def fix_all_target_list_status():
    print("=== Fixing target_list_status for all financing orders ===")
    
    # 获取所有onboard配置数据，按uid分组
    onboard_configs = list(mongo.refactoring_onboard_config.find())
    onboard_by_uid = {config.get('uid'): config for config in onboard_configs}
    print(f"Found {len(onboard_by_uid)} onboard configs")
    
    # 获取所有融资单
    financing_orders = list(mongo.refactoring_financing_order.find())
    total = len(financing_orders)
    print(f"Processing {total} financing orders...")
    
    # 统计修复前后的状态
    before_values = {}
    for order in financing_orders:
        status = order.get('target_list_status', '')
        before_values[status] = before_values.get(status, 0) + 1
    
    print(f"Before fix: {before_values}")
    
    # 执行修复
    fixed_count = 0
    for order in financing_orders:
        record_id = order['_id']
        uid = order.get('uid', '')
        
        # 计算正确的target_list_status值
        if uid in onboard_by_uid:
            target_list_status = onboard_by_uid[uid].get('target_list_status', '')
        else:
            target_list_status = ''
        
        # 只有当值不正确时才更新
        if order.get('target_list_status') != target_list_status:
            result = mongo.refactoring_financing_order.update_one(
                {'_id': record_id},
                {
                    '$set': {
                        'target_list_status': target_list_status,
                        'updated_at': datetime.now()
                    }
                }
            )
            if result.modified_count > 0:
                fixed_count += 1
    
    # 检查修复后的状态
    after_orders = list(mongo.refactoring_financing_order.find())
    after_values = {}
    for order in after_orders:
        status = order.get('target_list_status', '')
        after_values[status] = after_values.get(status, 0) + 1
    
    print(f"After fix: {after_values}")
    print(f"Fixed {fixed_count} records")
    print("=== Fix Completed ===")

if __name__ == "__main__":
    fix_all_target_list_status()
