from app import create_app, mongo
from werkzeug.security import generate_password_hash

# 创建Flask应用实例
app = create_app()

# 在应用上下文内创建测试用户
with app.app_context():
    # 检查是否已存在admin用户
    existing_user = mongo.users.find_one({'username': 'admin'})
    if existing_user:
        print('测试用户已存在: 用户名 admin')
    else:
        # 创建测试用户
        mongo.users.insert_one({
            'username': 'admin',
            'password_hash': generate_password_hash('admin123')
        })
        print('测试用户创建成功: 用户名 admin, 密码 admin123')
