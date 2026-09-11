import urllib3
from flask import Flask, g, request
from backend.app.config import Config
from backend.app.extensions import init_extensions

# n8n (air8.cn) 接口使用自签名/内网证书，统一关闭 SSL 校验，抑制 urllib3 的 InsecureRequestWarning
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 导出create_app函数，mongo对象将在create_app中初始化后通过extensions访问
__all__ = ['create_app']

def create_app(config_class=None):
    """创建Flask应用实例"""
    import os
    from backend.app.config import config_by_name
    
    # 测试Agent自动重启功能
    
    # 使用开发配置作为默认配置
    if config_class is None:
        config_class = config_by_name['dev']
    
    # 获取当前文件的目录
    current_dir = os.path.dirname(os.path.abspath(__file__))
    # 构建模板文件夹的绝对路径
    template_dir = os.path.join(current_dir, 'templates')
    
    app = Flask(__name__, template_folder=template_dir)
    app.config.from_object(config_class)
    
    # 初始化所有扩展
    init_extensions(app)
    
    # 注册蓝图
    from backend.app.routes import main_bp, auth_bp, import_bp, export_bp, maintenance_bp, batch_bp, language_bp, api_bp, tools_bp, fcb_bp, credit_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(import_bp, url_prefix='/import')
    app.register_blueprint(export_bp, url_prefix='/export')
    app.register_blueprint(maintenance_bp, url_prefix='/maintenance')
    app.register_blueprint(batch_bp)  # 批次管理路由，无需前缀
    app.register_blueprint(language_bp)  # 语言设置路由，无需前缀
    app.register_blueprint(api_bp, url_prefix='/api')
    app.register_blueprint(tools_bp, url_prefix='/tools')
    app.register_blueprint(fcb_bp, url_prefix='/fcb')
    app.register_blueprint(credit_bp, url_prefix='/credit')
    
    # 添加before_request钩子，用于处理语言偏好
    @app.before_request
    def before_request():
        """在请求处理前执行的钩子"""
        # 检查是否有语言查询参数
        lang = request.args.get('lang')
        if lang in ['zh', 'en', 'zh-CN', 'en-US', 'zh_CN', 'en_US']:
            # 将语言偏好存储到g对象中，以便在响应中使用
            g.selected_lang = lang
        else:
            # 从cookie获取语言偏好
            cookie_lang = request.cookies.get('language')
            if cookie_lang:
                g.selected_lang = cookie_lang
            else:
                # 默认使用中文
                g.selected_lang = 'zh-CN'
    
    # 添加after_request钩子，用于设置语言cookie
    @app.after_request
    def after_request(response):
        """在请求处理后执行的钩子"""
        # 如果g对象中有selected_lang，将其存储到cookie中
        if hasattr(g, 'selected_lang'):
            response.set_cookie('language', g.selected_lang, max_age=30*24*60*60)
        return response
    
    # 使用JSON文件加载翻译的函数
    @app.context_processor
    def inject_i18n():
        """将翻译函数注入到模板上下文中"""
        import os
        import json
        
        def translate(text, lang=None):
            """从JSON文件加载翻译，根据当前语言返回不同的翻译结果"""
            # 获取当前语言
            if lang is None:
                lang = g.get('selected_lang', 'zh-CN')
            
            # 标准化语言代码，处理各种输入格式
            if lang:
                lang = lang.lower()
                if lang in ['zh', 'zh-cn', 'zh_cn']:
                    lang = 'zh-CN'
                elif lang in ['en', 'en-us', 'en_us']:
                    lang = 'en-US'
            
            # 构建翻译文件路径
            current_dir = os.path.dirname(os.path.abspath(__file__))
            i18n_dir = os.path.join(current_dir, 'i18n')
            json_path = os.path.join(i18n_dir, f"{lang}.json")
            
            try:
                # 加载翻译文件
                with open(json_path, 'r', encoding='utf-8') as f:
                    translations = json.load(f)
                
                # 支持嵌套键解析，如 "common.title.dashboard"
                keys = text.split('.')
                result = translations
                for key in keys:
                    if key in result:
                        result = result[key]
                    else:
                        # 如果找不到键，尝试直接查找整个文本
                        return translations.get(text, text)
                return result
            except (FileNotFoundError, json.JSONDecodeError):
                # 如果文件不存在或解析错误，返回原文本
                return text
        
        # 将翻译函数添加到Jinja2环境的全局变量中，确保覆盖Flask-Babel的函数
        app.jinja_env.globals['_'] = translate
        
        return dict(_=translate)
    
    return app
