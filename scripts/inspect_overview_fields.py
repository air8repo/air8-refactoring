#!/usr/bin/env python3
"""
检查MongoDB中refactoring_financing_overview集合的字段结构
"""

import sys
import os
from pprint import pprint

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.app import create_app

def inspect_overview_fields():
    """检查financing_overview集合的字段结构"""
    print("=" * 60)
    print("检查MongoDB中refactoring_financing_overview集合的字段结构")
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
            
            # 获取前3个文档的完整结构
            print("\n2. 前3个文档的字段结构:")
            print("-" * 40)
            
            # 只获取前3个文档，限制大小
            sample_docs = list(overview_collection.find({}, {}).limit(3))
            
            for i, doc in enumerate(sample_docs, 1):
                print(f"\n文档 {i} 基本信息:")
                print(f"  - _id: {doc.get('_id')}")
                print(f"  - finance_request_number: {doc.get('finance_request_number')}")
                
                # 打印所有顶层字段
                print(f"  - 顶层字段: {list(doc.keys())}")
                
                # 检查order_details结构
                if 'order_details' in doc:
                    print(f"  - order_details 类型: {type(doc['order_details'])}")
                    if isinstance(doc['order_details'], dict):
                        print(f"    order_details 字段: {list(doc['order_details'].keys())}")
                    elif isinstance(doc['order_details'], list):
                        print(f"    order_details 是数组，长度: {len(doc['order_details'])}")
                        if doc['order_details']:
                            print(f"    第一个元素字段: {list(doc['order_details'][0].keys())}")
                
                # 检查bank_statements结构
                if 'bank_statements' in doc:
                    print(f"  - bank_statements 类型: {type(doc['bank_statements'])}")
                    if isinstance(doc['bank_statements'], list):
                        print(f"    bank_statements 数组长度: {len(doc['bank_statements'])}")
                        if doc['bank_statements']:
                            print(f"    第一个银行回单字段: {list(doc['bank_statements'][0].keys())}")
                
                # 检查repayments结构
                if 'repayments' in doc:
                    print(f"  - repayments 类型: {type(doc['repayments'])}")
                    if isinstance(doc['repayments'], list):
                        print(f"    repayments 数组长度: {len(doc['repayments'])}")
                        if doc['repayments']:
                            print(f"    第一个还款记录字段: {list(doc['repayments'][0].keys())}")
                
                print("-" * 40)
            
            # 检查前10个文档中可能存在的所有字段
            print("\n3. 前10个文档中出现的所有字段:")
            print("-" * 40)
            
            all_fields = set()
            nested_fields = {}
            
            sample_10_docs = list(overview_collection.find({}, {}).limit(10))
            
            for doc in sample_10_docs:
                # 收集顶层字段
                all_fields.update(doc.keys())
                
                # 收集嵌套字段
                for field, value in doc.items():
                    if isinstance(value, dict):
                        nested_fields[field] = list(value.keys())
                    elif isinstance(value, list) and value:
                        if isinstance(value[0], dict):
                            nested_fields[field] = list(value[0].keys())
            
            print(f"顶层字段: {sorted(list(all_fields))}")
            print("\n嵌套字段结构:")
            for field, subfields in nested_fields.items():
                print(f"  {field}: {subfields}")
            
            print("\n" + "=" * 60)
            print("字段检查完成")
            print("=" * 60)
            
    except Exception as e:
        print(f"❌ 发生错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    inspect_overview_fields()
