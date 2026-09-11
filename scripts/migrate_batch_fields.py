import sys
import os
from datetime import datetime

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app import create_app

# 创建应用实例
app = create_app()

with app.app_context():
    from backend.app.services.import_service import get_mongo
    
    # 获取mongo实例
    mongo = get_mongo()
    if mongo is None:
        print("错误: 无法连接到数据库")
        sys.exit(1)
    
    print("=== 批次号管理系统数据迁移脚本 ===")
    print("=" * 50)
    
    # 1. 在refactoring_onboard_config表中添加bank_source字段，默认值为"db"
    print("\n1. 在refactoring_onboard_config表中添加bank_source字段...")
    try:
        result = mongo.refactoring_onboard_config.update_many(
            {'bank_source': {'$exists': False}},  # 只更新没有该字段的文档
            {'$set': {'bank_source': 'db'}}
        )
        print(f"   成功更新 {result.modified_count} 条记录")
    except Exception as e:
        print(f"   错误: {str(e)}")
    
    # 2. 在refactoring_financing_order表中添加批次相关字段
    print("\n2. 在refactoring_financing_order表中添加批次相关字段...")
    try:
        # 添加batch_number字段，默认值为0
        batch_number_result = mongo.refactoring_financing_order.update_many(
            {'batch_number': {'$exists': False}},  # 只更新没有该字段的文档
            {'$set': {'batch_number': 0}}
        )
        print(f"   成功添加batch_number字段: {batch_number_result.modified_count} 条记录")
        
        # 添加batch_status字段，默认值为空字符串
        batch_status_result = mongo.refactoring_financing_order.update_many(
            {'batch_status': {'$exists': False}},  # 只更新没有该字段的文档
            {'$set': {'batch_status': ''}}
        )
        print(f"   成功添加batch_status字段: {batch_status_result.modified_count} 条记录")
        
        # 添加batch_created_at字段，默认值为null
        batch_created_at_result = mongo.refactoring_financing_order.update_many(
            {'batch_created_at': {'$exists': False}},  # 只更新没有该字段的文档
            {'$set': {'batch_created_at': None}}
        )
        print(f"   成功添加batch_created_at字段: {batch_created_at_result.modified_count} 条记录")
        
        # 添加bank_source字段，默认值为"db"
        bank_source_result = mongo.refactoring_financing_order.update_many(
            {'bank_source': {'$exists': False}},  # 只更新没有该字段的文档
            {'$set': {'bank_source': 'db'}}
        )
        print(f"   成功添加bank_source字段: {bank_source_result.modified_count} 条记录")
        
    except Exception as e:
        print(f"   错误: {str(e)}")
    
    # 3. 更新refactoring_financing_overview表中的loan_submission_batch字段为整数类型（如果需要）
    print("\n3. 检查refactoring_financing_overview表中的loan_submission_batch字段类型...")
    try:
        # 这里暂时不进行类型转换，因为我们将不再在overview表中维护批次号
        print("   跳过类型转换，因为批次号将不再在overview表中维护")
    except Exception as e:
        print(f"   错误: {str(e)}")
    
    print("\n=== 数据迁移完成 ===")
    print("所有字段已成功添加到相关表中！")
