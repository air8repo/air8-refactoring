import sys
import os

# 添加当前目录到Python搜索路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from flask import current_app
from backend.app import create_app
from werkzeug.security import generate_password_hash

# 创建Flask应用实例
app = create_app()

# 在应用上下文内创建管理员用户
with app.app_context():
    # 获取mongo对象
    mongo = current_app.extensions.get('mongo')
    if mongo is None:
        print('无法获取mongo对象，请检查数据库连接')
        sys.exit(1)
    
    # 定义管理员用户信息
    username = 'admin'
    password = '1234qwerZ'
    
    # 检查是否已存在admin用户
    existing_user = mongo.users.find_one({'username': username})
    
    if existing_user:
        # 更新现有用户的密码
        mongo.users.update_one(
            {'username': username},
            {'$set': {
                'password_hash': generate_password_hash(password)
            }}
        )
        print(f'管理员用户密码已更新: 用户名 {username}, 密码 {password}')
    else:
        # 创建新的管理员用户
        mongo.users.insert_one({
            'username': username,
            'password_hash': generate_password_hash(password)
        })
        print(f'管理员用户创建成功: 用户名 {username}, 密码 {password}')
