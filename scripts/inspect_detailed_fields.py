#!/usr/bin/env python3
"""
检查MongoDB中refactoring_financing_overview集合的详细字段结构
"""

import sys
import os
from pprint import pprint

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.app import create_app

def inspect_detailed_fields():
    """检查financing_overview集合的详细字段结构"""
    print("=" * 60)
    print("检查MongoDB中refactoring_financing_overview集合的详细字段结构")
    print("=" * 60)
    
    try:
        # 创建Flask应用实例
        app = create_app()
        
        with app.app_context():
            # 从extensions获取mongo实例
            from backend.app.extensions import mongo
            
            if mongo is None:
                print("❌ MongoDB连接失败")
                return
            
            print("✅ MongoDB连接成功")
            
            # 获取集合
            overview_collection = mongo.db.refactoring_financing_overview
            
            # 获取集合中的文档数量
            total_docs = overview_collection.count_documents({})
            print(f"\n1. 集合中文档数量: {total_docs}")
            
            # 获取第一个文档的完整嵌套结构
            print("\n2. 第一个文档的完整嵌套结构:")
            print("-" * 40)
            
            first_doc = overview_collection.find_one({})
            
            if first_doc:
                print(f"\n文档基本信息:")
                print(f"  - _id: {first_doc.get('_id')}")
                print(f"  - finance_request_number: {first_doc.get('finance_request_number')}")
                print(f"  - refactoring_status: {first_doc.get('refactoring_status')}")
                print(f"  - outstanding_loan_exclude_wip: {first_doc.get('outstanding_loan_exclude_wip')}")
                print(f"  - air8_settled_fr_amt: {first_doc.get('air8_settled_fr_amt')}")
                print(f"  - settled_db_loan: {first_doc.get('settled_db_loan')}")
                
                # 详细检查order_details
                print("\n  - order_details 详细结构:")
                order_details = first_doc.get('order_details', {})
                if isinstance(order_details, dict):
                    for key, value in order_details.items():
                        print(f"    {key}: {value} (类型: {type(value)})")
                else:
                    print(f"    类型: {type(order_details)}, 值: {order_details}")
                
                # 详细检查bank_statements
                print("\n  - bank_statements 详细结构:")
                bank_statements = first_doc.get('bank_statements', [])
                if isinstance(bank_statements, list) and bank_statements:
                    for i, statement in enumerate(bank_statements):
                        print(f"    银行回单 {i+1}:")
                        for key, value in statement.items():
                            print(f"      {key}: {value} (类型: {type(value)})")
                else:
                    print(f"    类型: {type(bank_statements)}, 值: {bank_statements}")
                
                # 详细检查repayments
                print("\n  - repayments 详细结构:")
                repayments = first_doc.get('repayments', [])
                if isinstance(repayments, list) and repayments:
                    for i, repayment in enumerate(repayments):
                        print(f"    还款记录 {i+1}:")
                        for key, value in repayment.items():
                            print(f"      {key}: {value} (类型: {type(value)})")
                else:
                    print(f"    类型: {type(repayments)}, 值: {repayments}")
                
                # 详细检查totals
                print("\n  - totals 详细结构:")
                totals = first_doc.get('totals', {})
                if isinstance(totals, dict):
                    for key, value in totals.items():
                        print(f"    {key}: {value} (类型: {type(value)})")
                else:
                    print(f"    类型: {type(totals)}, 值: {totals}")
                
            else:
                print("\n❌ 集合中没有文档")
            
            print("\n" + "=" * 60)
            print("字段检查完成")
            print("=" * 60)
            
    except Exception as e:
        print(f"❌ 发生错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    inspect_detailed_fields()
