import sys
import os
from werkzeug.security import generate_password_hash

# 添加当前目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app import create_app
from backend.app import extensions

app = create_app()

with app.app_context():
    # 初始化扩展
    extensions.init_extensions(app)
    
    # 获取mongo_db对象
    mongo_db = extensions.mongo
    
    print("=" * 80)
    print("初始化数据库")
    print("=" * 80)
    
    # 创建users集合
    print("\n1. 检查并创建users集合...")
    try:
        # 检查users集合是否存在
        collections = mongo_db.list_collection_names()
        if 'users' not in collections:
            # 创建users集合
            mongo_db.create_collection('users')
            print("✓ 创建users集合成功")
        else:
            print("✓ users集合已存在")
        
        # 添加默认管理员用户
        admin_user = mongo_db.users.find_one({'username': 'admin'})
        if not admin_user:
            # 创建默认管理员用户，密码为 'admin123'
            admin_data = {
                'username': 'admin',
                'password_hash': generate_password_hash('admin123')
            }
            result = mongo_db.users.insert_one(admin_data)
            print("✓ 添加默认管理员用户成功")
        else:
            print("✓ 管理员用户已存在")
        
    except Exception as e:
        print(f"✗ 创建users集合失败: {str(e)}")
        sys.exit(1)
    
    # 创建其他必要的集合
    required_collections = [
        'refactoring_onboard_config',
        'refactoring_financing_order',
        'refactoring_repayment_order',
        'refactoring_bank_statement',
        'refactoring_financing_overview'
    ]
    
    print("\n2. 检查并创建其他必要集合...")
    for collection_name in required_collections:
        try:
            if collection_name not in collections:
                mongo_db.create_collection(collection_name)
                print(f"✓ 创建{collection_name}集合成功")
            else:
                print(f"✓ {collection_name}集合已存在")
        except Exception as e:
            print(f"✗ 创建{collection_name}集合失败: {str(e)}")
    
    # 创建唯一索引
    print("\n3. 创建唯一索引...")
    import pymongo
    try:
        mongo_db.refactoring_repayment_order.create_index(
            [('finance_request_number', pymongo.ASCENDING)],
            unique=True,
            name='unique_finance_request_number'
        )
        print("✓ refactoring_repayment_order.finance_request_number 唯一索引创建成功")
    except Exception as e:
        if 'already exists' in str(e) or 'IndexOptionsConflict' in str(e):
            print("✓ refactoring_repayment_order.finance_request_number 唯一索引已存在")
        else:
            print(f"✗ 创建唯一索引失败: {str(e)}")

    print("\n" + "=" * 80)
    print("数据库初始化完成")
    print("=" * 80)
    print("默认管理员账号:")
    print("  用户名: admin")
    print("  密码: admin123")
