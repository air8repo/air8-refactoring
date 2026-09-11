import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

class Config:
    """基础配置类"""
    # Flask配置
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key'
    UPLOAD_FOLDER = os.path.join(os.getcwd(), 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB
    
    # 允许上传的文件类型
    ALLOWED_EXTENSIONS = {'xlsx', 'xls'}
    
    # 应用配置
    APP_NAME = '再保理数据同步系统'
    API_TOKEN = os.environ.get('API_TOKEN') or '7a12ef54-12f2-11f1-ba0a-06df603a9138'
    
    # FCB 每日推送邮件配置
    DAILY_EXPORT_EMAIL_URL = os.environ.get('DAILY_EXPORT_EMAIL_URL') or 'https://n8n.air8.cn/webhook/commonSendEmailForRefactoring'
    DAILY_EXPORT_EMAIL_TOKEN = os.environ.get('DAILY_EXPORT_EMAIL_TOKEN') or 'd5173b84678c11f0995006a0ea58daac'

    # 通用邮件接口（n8n-v2）。JSON 入参 {type, title, body}，无需 token。用于 Loan Rejected 等通知。
    COMMON_EMAIL_URL = os.environ.get('COMMON_EMAIL_URL') or 'https://n8n-v2.air8.cn/webhook/commonSendEmailForRefactoring'

    # 额度管理每日预警阈值（占用率 >= 该值即预警），本期硬编码不做 UI 配置
    CREDIT_WARNING_THRESHOLD = 0.9

    # 国际化配置
    LANGUAGES = {
        'zh': '中文',
        'en': 'English'
    }
    BABEL_DEFAULT_LOCALE = 'zh'
    BABEL_TRANSLATION_DIRECTORIES = os.path.join('app', 'translations')
    
    # 创建上传目录（如果不存在）
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)
    
    # 创建翻译目录（如果不存在）
    translations_dir = os.path.join(os.getcwd(), 'translations')
    if not os.path.exists(translations_dir):
        os.makedirs(translations_dir)
        # 创建中文和英文翻译目录
        for lang in ['zh', 'en']:
            lang_dir = os.path.join(translations_dir, lang, 'LC_MESSAGES')
            if not os.path.exists(lang_dir):
                os.makedirs(lang_dir, exist_ok=True)

class DevelopmentConfig(Config):
    """开发环境配置"""
    DEBUG = True
    MONGODB_URI = os.environ.get('MONGODB_URI') or 'mongodb://air8:Air8%40123@localhost:27017/refactoring'

class TestingConfig(Config):
    """测试环境配置"""
    TESTING = True
    WTF_CSRF_ENABLED = False
    MONGODB_URI = os.environ.get('TEST_MONGODB_URI') or 'mongodb://air8:Air8%40123@localhost:27017/refactoring_test'

# 配置映射
config_by_name = {
    'dev': DevelopmentConfig,
    'test': TestingConfig,
    'default': DevelopmentConfig
}
