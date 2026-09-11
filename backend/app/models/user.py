from flask import current_app
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from bson.objectid import ObjectId

class User(UserMixin):
    """用户模型"""
    
    def __init__(self, user_id, username, password_hash=None):
        self.id = str(user_id)  # 转换为字符串，Flask-Login需要字符串ID
        self.username = username
        self.password_hash = password_hash
    
    @staticmethod
    def get(user_id):
        """根据用户ID获取用户"""
        try:
            # 获取已经初始化的mongo对象
            mongo = None
            
            # 尝试从current_app.extensions获取
            try:
                if hasattr(current_app, 'extensions'):
                    mongo = current_app.extensions.get('mongo')
            except Exception:
                pass
            
            # 尝试从app模块直接导入
            if mongo is None:
                try:
                    from backend.app import mongo as app_mongo
                    mongo = app_mongo
                except Exception:
                    pass
            
            # 尝试从extensions模块导入
            if mongo is None:
                try:
                    from backend.app.extensions import mongo as ext_mongo
                    mongo = ext_mongo
                except Exception:
                    pass
            
            if mongo is None:
                return None
            
            # 将字符串ID转换为ObjectId
            object_id = ObjectId(user_id)
            user_data = mongo.users.find_one({'_id': object_id})
            if not user_data:
                return None
            return User(user_data['_id'], user_data['username'], user_data['password_hash'])
        except Exception as e:
            return None
    
    @staticmethod
    def get_by_username(username):
        """根据用户名获取用户"""
        try:
            # 获取已经初始化的mongo对象
            mongo = None
            
            # 尝试从current_app.extensions获取
            try:
                if hasattr(current_app, 'extensions'):
                    mongo = current_app.extensions.get('mongo')
            except Exception:
                pass
            
            # 尝试从app模块直接导入
            if mongo is None:
                try:
                    from backend.app import mongo as app_mongo
                    mongo = app_mongo
                except Exception:
                    pass
            
            # 尝试从extensions模块导入
            if mongo is None:
                try:
                    from backend.app.extensions import mongo as ext_mongo
                    mongo = ext_mongo
                except Exception:
                    pass
            
            if mongo is None:
                return None
            
            user_data = mongo.users.find_one({'username': username})
            if not user_data:
                return None
            return User(user_data['_id'], user_data['username'], user_data['password_hash'])
        except Exception as e:
            return None
    
    def set_password(self, password):
        """设置密码"""
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """验证密码"""
        return check_password_hash(self.password_hash, password)
    
    def save(self):
        """保存用户到数据库"""
        try:
            print("=== User.save() method called ===")
            
            # 获取已经初始化的mongo对象
            mongo = None
            
            # 尝试从current_app.extensions获取
            try:
                if hasattr(current_app, 'extensions'):
                    print("Trying to get mongo from current_app.extensions...")
                    mongo = current_app.extensions.get('mongo')
                    print(f"Got mongo from current_app.extensions: {mongo}")
            except Exception as e:
                print(f"Error getting mongo from current_app.extensions: {e}")
            
            # 尝试从app模块直接导入
            if mongo is None:
                try:
                    print("Trying to import mongo from backend.app...")
                    from backend.app import mongo as app_mongo
                    mongo = app_mongo
                    print(f"Got mongo from backend.app: {mongo}")
                except Exception as e:
                    print(f"Error importing mongo from backend.app: {e}")
            
            # 尝试从extensions模块导入
            if mongo is None:
                try:
                    print("Trying to import mongo from backend.app.extensions...")
                    from backend.app.extensions import mongo as ext_mongo
                    mongo = ext_mongo
                    print(f"Got mongo from backend.app.extensions: {mongo}")
                except Exception as e:
                    print(f"Error importing mongo from backend.app.extensions: {e}")
            
            if mongo is None:
                print("ERROR: Could not get mongo object!")
                return False
            
            print(f"Mongo object: {mongo}")
            
            user_data = {
                'username': self.username,
                'password_hash': self.password_hash
            }
            print(f"User data to save: {user_data}")
            
            # 直接访问数据库和集合
            try:
                # 从app获取配置
                from backend.app import app
                db_name = app.config.get('MONGO_DBNAME', 'refactoring_db')
                print(f"Using database: {db_name}")
                
                # 获取数据库和集合
                db = mongo.db
                if not db:
                    print("Trying to get db from mongo directly...")
                    db = mongo[db_name]
                
                users_collection = db.users
                print(f"Users collection: {users_collection}")
                
                if self.id:
                    # 更新现有用户
                    # 将字符串ID转换为ObjectId
                    from bson.objectid import ObjectId
                    result = users_collection.update_one({'_id': ObjectId(self.id)}, {'$set': user_data})
                    print(f"Update result: {result.raw_result}")
                else:
                    # 创建新用户
                    result = users_collection.insert_one(user_data)
                    print(f"Insert result: {result.inserted_id}")
                    # 将ObjectId转换为字符串，Flask-Login需要字符串ID
                    self.id = str(result.inserted_id)
                    print(f"New user ID: {self.id}")
                
                print("User saved successfully!")
                return True
            except Exception as e:
                print(f"ERROR saving user: {e}")
                import traceback
                traceback.print_exc()
                return False
        except Exception as e:
            print(f"Unexpected error in User.save(): {e}")
            import traceback
            traceback.print_exc()
            return False
