#!/usr/bin/env python3
"""
运行数据聚合服务，生成refactoring_financing_overview集合数据
"""

import sys
import os
from pprint import pprint

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.app import create_app

def run_aggregate():
    """运行数据聚合服务"""
    print("=" * 60)
    print("运行数据聚合服务，生成融资概览数据")
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
            
            # 运行聚合服务
            from backend.app.services.aggregate_service import AggregateService
            
            aggregate_service = AggregateService()
            print("\n开始运行数据聚合...")
            
            result = aggregate_service.aggregate_financing_overview()
            
            print(f"\n聚合结果: {result}")
            
            # 检查聚合后的数据
            overview_collection = mongo.db.refactoring_financing_overview
            total_docs = overview_collection.count_documents({})
            print(f"\n聚合后集合中文档数量: {total_docs}")
            
            # 如果有数据，显示第一条记录的关键信息
            if total_docs > 0:
                first_doc = overview_collection.find_one({})
                print(f"\n第一条记录关键信息:")
                print(f"  - finance_request_number: {first_doc.get('finance_request_number')}")
                print(f"  - refactoring_status: {first_doc.get('refactoring_status')}")
                print(f"  - outstanding_loan_exclude_wip: {first_doc.get('outstanding_loan_exclude_wip')}")
            
            print("\n" + "=" * 60)
            print("数据聚合完成")
            print("=" * 60)
            
    except Exception as e:
        print(f"❌ 发生错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    run_aggregate()
