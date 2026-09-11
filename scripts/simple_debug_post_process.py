import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import mongo
from app.services.import_service import ImportService
import pandas as pd
from datetime import datetime

# 创建一个简单的测试DataFrame
def create_test_df():
    data = {
        'Finance Request Number': ['SIMPLE-DEBUG-001'],
        'Buyer Code': ['C0000505'],  # 这个UID在onboard中存在
        'Supplier Code': ['C0000755'],
        'Invoice Number': ['SIMPLE-INV-001'],
        'Auto Finance': ['Yes'],
        'Trade Amount': [1000],
        'Financing Amount': [800],
        'Actual Financing Amount': [800],
        'Trade Currency': ['USD'],
        'Financing Currency': ['USD'],
        'Exchange Rate': [1.0],
        'Expected Tenor': [30],
        'Actual Tenor': [30],
        'Invoice Date': [datetime.now()],
        'Due Date': [datetime.now()],
        'Request Date': [datetime.now()],
        'Expected Funding Date': [datetime.now()],
        'Actual Funding Date': [datetime.now()],
        'Actual Shipment Date': [datetime.now()]
    }
    return pd.DataFrame(data)

# 简单调试后处理执行过程
def simple_debug_post_process():
    print("=== Simple Debug Post Process Execution ===")
    
    # 获取onboard配置中的target_list_status值作为参考
    print("\n1. Checking onboard configuration...")
    onboard_config = mongo.refactoring_onboard_config.find_one({'uid': 'C0000505C0000755'})
    if onboard_config:
        expected_status = onboard_config.get('target_list_status', '')
        print(f"   Found onboard config for UID 'C0000505C0000755'")
        print(f"   target_list_status in onboard: '{expected_status}'")
    else:
        print(f"   No onboard config found for UID 'C0000505C0000755'")
        return
    
    # 创建测试数据
    print("\n2. Creating test data...")
    df = create_test_df()
    finance_request_number = df.iloc[0]['Finance Request Number']
    print(f"   Finance Request Number: {finance_request_number}")
    
    # 导入前先清理
    mongo.refactoring_financing_order.delete_one({'finance_request_number': finance_request_number})
    
    # 实例化ImportService
    import_service = ImportService()
    
    # 执行导入
    print("\n3. Executing import...")
    result = import_service._import_financing(df)
    print(f"   Import result: {result}")
    
    # 检查导入后的状态
    print("\n4. Checking record after import...")
    record = mongo.refactoring_financing_order.find_one({'finance_request_number': finance_request_number})
    if record:
        print(f"   Record found: {record['finance_request_number']}")
        print(f"   target_list_status: '{record.get('target_list_status')}'")
        print(f"   in_the_onboarding_list: {record.get('in_the_onboarding_list')}")
        
        # 验证结果
        if record.get('target_list_status') == expected_status:
            print("   ✅ PASS: target_list_status correctly updated")
        else:
            print(f"   ❌ FAIL: target_list_status not updated correctly")
            print(f"      Expected: '{expected_status}', Got: '{record.get('target_list_status')}'")
            
            # 手动执行后处理，看看是否能成功
            print("\n5. Manually calling post_process_financing_records...")
            imported_ids = [record['_id']]
            print(f"   Calling with imported_ids: {imported_ids}")
            import_service._post_process_financing_records(imported_ids)
            
            # 再次检查状态
            updated_record = mongo.refactoring_financing_order.find_one({'_id': record['_id']})
            print(f"   Updated target_list_status: '{updated_record.get('target_list_status')}'")
            if updated_record.get('target_list_status') == expected_status:
                print("   ✅ PASS: Manual post process worked!")
            else:
                print("   ❌ FAIL: Manual post process also failed!")
                
                # 检查后处理方法的实现
                print("\n6. Checking post_process_financing_records implementation...")
                # 直接检查onboard_by_uid字典
                print("   Checking onboard_by_uid creation...")
                onboard_configs = list(mongo.refactoring_onboard_config.find())
                onboard_by_uid = {config.get('uid'): config for config in onboard_configs}
                print(f"   Found {len(onboard_by_uid)} onboard configs")
                print(f"   Is 'C0000505C0000755' in onboard_by_uid? {'C0000505C0000755' in onboard_by_uid}")
                if 'C0000505C0000755' in onboard_by_uid:
                    print(f"   onboard_by_uid['C0000505C0000755']: {onboard_by_uid['C0000505C0000755']}")
    else:
        print("   ❌ FAIL: Record not found after import")
    
    # 清理测试数据
    mongo.refactoring_financing_order.delete_one({'finance_request_number': finance_request_number})
    print("\n=== Debugging Completed ===")

if __name__ == "__main__":
    simple_debug_post_process()
