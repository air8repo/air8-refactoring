# 认证模块 (auth)

## 概述
提供用户注册、登录和退出登录功能，基于 Flask-Login 实现会话管理，使用 MongoDB 存储用户信息，密码通过 Werkzeug 进行哈希加密。

## 路由
| 方法 | 路径 | 说明 | 认证要求 |
|------|------|------|----------|
| GET, POST | /auth/login | 用户登录页面，GET 显示表单，POST 验证凭据并登录 | 无（已登录用户自动跳转到仪表盘） |
| GET, POST | /auth/register | 用户注册页面，GET 显示表单，POST 创建新用户 | 无（已登录用户自动跳转到仪表盘） |
| GET | /auth/logout | 退出登录，清除会话后跳转到登录页 | 无 |

## 核心逻辑
1. **登录流程**：通过 `LoginForm` 表单接收用户名和密码，调用 `User.get_by_username()` 查询用户，再通过 `check_password()` 验证密码哈希。登录成功后支持 `remember me` 记住登录状态，并支持 `next` 参数重定向到原始请求页面。
2. **注册流程**：通过 `RegisterForm` 表单接收用户名、密码和确认密码（需一致），先检查用户名是否已存在，不存在则创建 `User` 对象、设置密码哈希并保存到 MongoDB。
3. **密码安全**：使用 `werkzeug.security.generate_password_hash` 生成密码哈希，`check_password_hash` 验证密码，不存储明文密码。
4. **用户加载**：`User.get(user_id)` 方法供 Flask-Login 的 `user_loader` 回调使用，通过 MongoDB 的 `_id`（ObjectId）加载用户对象。

## 依赖关系
| 依赖 | 用途 |
|------|------|
| Flask-Login | 会话管理（`login_user`、`logout_user`、`current_user`、`UserMixin`） |
| Flask-WTF / WTForms | 表单定义与 CSRF 保护 |
| Werkzeug | 密码哈希生成与验证 |
| pymongo / bson | MongoDB 数据库操作，ObjectId 处理 |

## 关键文件
| 文件路径 | 职责 |
|----------|------|
| `backend/app/routes/auth.py` | 定义登录、注册、退出登录三个路由视图函数 |
| `backend/app/models/user.py` | User 模型类，继承 UserMixin，封装用户的 CRUD 操作和密码管理 |
| `backend/app/forms/auth.py` | 定义 LoginForm 和 RegisterForm 两个 WTForms 表单类 |

## 数据模型
**集合名称**: `users`

| 字段 | 类型 | 说明 |
|------|------|------|
| `_id` | ObjectId | MongoDB 自动生成的主键 |
| `username` | String | 用户名，长度 2-20 字符，唯一 |
| `password_hash` | String | Werkzeug 生成的密码哈希值 |
