#!/usr/bin/env python3
"""
检查MongoDB中的所有集合和文档数量
"""

import sys
import os
from pprint import pprint

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.app import create_app

def check_mongo_collections():
    """检查MongoDB中的所有集合和文档数量"""
    print("=" * 60)
    print("检查MongoDB中的所有集合和文档数量")
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
            print(f"  - 数据库名称: {mongo.db.name}")
            
            # 获取所有集合
            collections = mongo.db.list_collection_names()
            
            print(f"\n1. 数据库中共有 {len(collections)} 个集合:")
            print("-" * 40)
            
            for collection_name in sorted(collections):
                count = mongo.db[collection_name].count_documents({})
                print(f"  {collection_name}: {count} 条文档")
                
                # 如果是refactoring相关的集合，显示更详细信息
                if 'refactoring' in collection_name:
                    # 显示第一条文档的前几个字段
                    first_doc = mongo.db[collection_name].find_one({})
                    if first_doc:
                        print(f"    示例文档字段: {list(first_doc.keys())[:5]}...")
                
            print("\n" + "=" * 60)
            print("集合检查完成")
            print("=" * 60)
            
    except Exception as e:
        print(f"❌ 发生错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    check_mongo_collections()
