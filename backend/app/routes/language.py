from flask import request, redirect, url_for, make_response, jsonify
from flask_login import login_required
from backend.app.routes import language_bp

@language_bp.route('/set_language/<language>')
@login_required
def set_language(language):
    """设置语言偏好"""
    # 标准化语言代码，处理各种格式
    if language:
        language = language.lower()
        if language in ['zh', 'zh-cn', 'zh_cn']:
            language = 'zh_CN'
        elif language in ['en', 'en-us', 'en_us']:
            language = 'en_US'
    
    # 创建响应对象
    response = make_response(redirect(request.referrer or url_for('main.dashboard')))
    
    # 设置语言cookie，有效期30天
    response.set_cookie('language', language, max_age=30*24*60*60)
    
    return response

@language_bp.route('/api/switch_language', methods=['POST'])
@login_required
def switch_language_api():
    """API端点：切换语言（用于无刷新语言切换）"""
    # 获取语言参数
    lang = request.args.get('lang', 'zh-CN')
    
    # 标准化语言代码，处理各种格式
    if lang:
        lang = lang.lower()
        if lang in ['zh', 'zh-cn', 'zh_cn']:
            lang = 'zh_CN'
        elif lang in ['en', 'en-us', 'en_us']:
            lang = 'en_US'
    
    # 创建响应对象
    response = jsonify({'success': True, 'message': 'Language switched successfully'})
    
    # 设置语言cookie，有效期30天
    response.set_cookie('language', lang, max_age=30*24*60*60, path='/')
    
    return response
