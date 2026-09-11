from flask_login import LoginManager
from flask_babel import Babel
from pymongo import MongoClient

# 定时任务调度器
scheduler = None

# 初始化登录管理器
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.login_message_category = 'info'

# 初始化MongoDB客户端和数据库
client = None
mongo = None

# 初始化Babel
babel = Babel()

# 语言选择函数
def get_locale():
    """获取当前语言设置"""
    from flask import request, g
    # 从查询参数获取语言偏好
    lang = request.args.get('lang')
    # 标准化语言代码，处理各种格式：zh, zh-CN, zh_CN, zh-cn, en, en-US, en_US, en-us
    if lang:
        lang = lang.lower()
        if lang in ['zh', 'zh-cn', 'zh_cn']:
            lang = 'zh_CN'
        elif lang in ['en', 'en-us', 'en_us']:
            lang = 'en_US'
        # 将语言偏好存储到cookie中
        g.selected_lang = lang
        return lang
    # 从cookie获取语言偏好
    lang = request.cookies.get('language')
    if lang:
        lang = lang.lower()
        if lang in ['zh', 'zh-cn', 'zh_cn']:
            lang = 'zh_CN'
        elif lang in ['en', 'en-us', 'en_us']:
            lang = 'en_US'
        return lang
    # 默认返回中文
    return 'zh_CN'

# 自定义翻译选择器，加载 JSON 翻译文件
def get_translations():
    """自定义翻译选择器，加载 JSON 翻译文件"""
    from flask import current_app, request
    import os
    
    # 获取当前语言
    locale = get_locale()
    
    # 将下划线格式转换为连字符格式，用于加载JSON文件
    file_locale = locale.replace('_', '-')
    
    # 构建 JSON 翻译文件路径
    i18n_dir = os.path.join(current_app.root_path, 'i18n')
    json_path = os.path.join(i18n_dir, f"{file_locale}.json")
    
    # 如果文件存在，加载 JSON 翻译
    if os.path.exists(json_path):
        from backend.app.utils.translations import JSONTranslations
        return JSONTranslations().load_json(json_path)
    
    # 否则返回默认翻译
    return None

# 用户加载函数
@login_manager.user_loader
def load_user(user_id):
    """加载用户"""
    from backend.app.models.user import User
    return User.get(user_id)

# 初始化函数
def init_extensions(app):
    """初始化所有扩展"""
    # 初始化登录管理器
    login_manager.init_app(app)
    
    # 初始化Babel
    babel.init_app(app, locale_selector=get_locale)
    
    # 初始化MongoDB
    global client, mongo
    client = MongoClient(app.config['MONGODB_URI'])
    mongo = client.get_database()
    
    # 将mongo对象添加到app.extensions中，方便其他模块使用
    if not hasattr(app, 'extensions'):
        app.extensions = {}
    app.extensions['mongo'] = mongo
    
    # 初始化定时任务调度器（仅非测试环境）
    global scheduler
    if not app.config.get('TESTING'):
        import os
        # 防止 Flask reloader 启动两个 scheduler
        if os.environ.get('WERKZEUG_RUN_MAIN') == 'true' or not app.debug:
            from apscheduler.schedulers.background import BackgroundScheduler
            scheduler = BackgroundScheduler(timezone='Asia/Shanghai')
            from backend.app.services.daily_export_service import register_scheduled_jobs
            register_scheduled_jobs(scheduler, app)
            from backend.app.services.onboarding_sync_service import register_onboarding_sync_job
            register_onboarding_sync_job(scheduler, app)
            from backend.app.services.credit_warning_service import register_credit_warning_job
            register_credit_warning_job(scheduler, app)
            scheduler.start()

    # 覆盖Flask-Babel的翻译获取机制，使用我们的JSON翻译加载器
    from flask_babel import get_translations as babel_get_translations
    
    def custom_get_translations():        
        """自定义翻译获取函数，优先使用JSON翻译文件"""
        return get_translations()
    
    # 将自定义翻译获取函数添加到babel对象中
    babel.get_translations = custom_get_translations
