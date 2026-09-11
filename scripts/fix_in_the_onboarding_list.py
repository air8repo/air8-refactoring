import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import mongo
from datetime import datetime
from bson import Decimal128

# 修复所有融资单的in_the_onboarding_list字段
def fix_all_in_the_onboarding_list():
    print("=== Fixing in_the_onboarding_list for all financing orders ===")
    
    # 获取所有onboard配置数据，按uid分组
    onboard_configs = list(mongo.refactoring_onboard_config.find())
    onboard_by_uid = {config.get('uid'): config for config in onboard_configs}
    print(f"Found {len(onboard_by_uid)} onboard configs")
    
    # 获取所有融资单
    financing_orders = list(mongo.refactoring_financing_order.find())
    total = len(financing_orders)
    print(f"Processing {total} financing orders...")
    
    # 统计修复前后的状态
    before_true = sum(1 for order in financing_orders if order.get('in_the_onboarding_list'))
    before_false = total - before_true
    
    print(f"Before fix: True={before_true}, False={before_false}")
    
    # 执行修复
    fixed_count = 0
    for order in financing_orders:
        record_id = order['_id']
        uid = order.get('uid', '')
        
        # 计算正确的in_the_onboarding_list值
        in_the_onboarding_list = True if uid in onboard_by_uid else False
        
        # 只有当值不正确时才更新
        if order.get('in_the_onboarding_list') != in_the_onboarding_list:
            result = mongo.refactoring_financing_order.update_one(
                {'_id': record_id},
                {
                    '$set': {
                        'in_the_onboarding_list': in_the_onboarding_list,
                        'updated_at': datetime.now()
                    }
                }
            )
            if result.modified_count > 0:
                fixed_count += 1
    
    # 检查修复后的状态
    after_orders = list(mongo.refactoring_financing_order.find())
    after_true = sum(1 for order in after_orders if order.get('in_the_onboarding_list'))
    after_false = total - after_true
    
    print(f"After fix: True={after_true}, False={after_false}")
    print(f"Fixed {fixed_count} records")
    print("=== Fix Completed ===")

if __name__ == "__main__":
    fix_all_in_the_onboarding_list()
