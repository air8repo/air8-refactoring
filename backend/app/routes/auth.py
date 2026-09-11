from flask import render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, current_user
from backend.app.routes import auth_bp
from backend.app.forms.auth import LoginForm, RegisterForm
from backend.app.models.user import User

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """登录页面"""
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    
    form = LoginForm()
    if form.validate_on_submit():
        user = User.get_by_username(form.username.data)
        if user and user.check_password(form.password.data):
            login_user(user, remember=form.remember.data)
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('main.dashboard'))
        flash('用户名或密码错误', 'error')
    
    return render_template('login.html', form=form)

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """注册页面"""
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    
    form = RegisterForm()
    if form.validate_on_submit():
        # 添加调试日志
        print(f"Form validated successfully for username: {form.username.data}")
        
        # 检查用户名是否已存在
        existing_user = User.get_by_username(form.username.data)
        if existing_user:
            print(f"Username {form.username.data} already exists")
            flash('用户名已存在', 'error')
            return redirect(url_for('auth.register'))
        
        print(f"Username {form.username.data} is available")
        
        # 创建新用户
        new_user = User(None, form.username.data)
        new_user.set_password(form.password.data)
        print(f"Created new user object with username: {new_user.username}")
        
        # 保存到数据库
        if new_user.save():
            print(f"User {new_user.username} saved successfully")
            flash('注册成功，请登录', 'success')
            return redirect(url_for('auth.login'))
        else:
            print(f"Failed to save user {new_user.username}")
            flash('注册失败，请重试', 'error')
    else:
        # 表单验证失败，打印错误信息
        print(f"Form validation failed: {form.errors}")
    
    return render_template('register.html', form=form)

@auth_bp.route('/logout')
def logout():
    """退出登录"""
    logout_user()
    return redirect(url_for('auth.login'))
