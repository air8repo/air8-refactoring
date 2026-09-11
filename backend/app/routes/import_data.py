from flask import render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required
from backend.app.routes import import_bp
from backend.app.services.import_service import ImportService
from backend.app.config import Config
from datetime import datetime
from bson.objectid import ObjectId

def get_mongo():
    """获取已初始化的mongo对象"""
    mongo = None
    
    # 首先尝试直接从extensions模块导入（最高优先级，适合测试环境）
    try:
        from backend.app.extensions import mongo as ext_mongo
        if ext_mongo is not None:
            return ext_mongo
    except Exception:
        pass
    
    # 然后尝试从app模块导入
    try:
        from backend.app import mongo as app_mongo
        if app_mongo is not None:
            return app_mongo
    except Exception:
        pass
    
    # 最后尝试从current_app.extensions获取（适合运行环境）
    try:
        if hasattr(current_app, 'extensions'):
            mongo = current_app.extensions.get('mongo')
            if mongo is not None:
                return mongo
    except Exception:
        pass
    
    return None

@import_bp.route('/')
@login_required
def import_index():
    """导入页面"""
    return render_template('import.html')

@import_bp.route('/upload', methods=['POST'])
@login_required
def upload_file():
    """处理文件上传"""
    try:
        if 'file' not in request.files:
            return {
                'success': False,
                'message': '没有选择文件'
            }, 400
        
        file = request.files['file']
        if file.filename == '':
            return {
                'success': False,
                'message': '没有选择文件'
            }, 400
        
        if '.' in file.filename and file.filename.rsplit('.', 1)[1].lower() in Config.ALLOWED_EXTENSIONS:
            import_type = request.form.get('import_type')
            bank_channel = request.form.get('bank_channel', 'DB')  # 默认DB
            if not import_type:
                return {
                    'success': False,
                    'message': '请选择导入类型'
                }, 400
            
            import_service = ImportService()
            result = import_service.import_file(file, import_type, bank_channel=bank_channel)
            
            return result
        else:
            return {
                'success': False,
                'message': '只允许上传Excel文件 (.xlsx, .xls)'
            }, 400
    except Exception as e:
        return {
            'success': False,
            'message': f'导入过程中发生错误: {str(e)}'
        }, 500



@import_bp.route('/import_from_api', methods=['POST'])
@login_required
def import_from_api():
    """从API导入数据"""
    try:
        import_type = request.form.get('import_type')
        if not import_type:
            return {
                'success': False,
                'message': '请选择导入类型'
            }, 400
        
        import_service = ImportService()
        result = import_service.import_from_api(import_type)
        
        return result
    except Exception as e:
        return {
            'success': False,
            'message': f'API导入过程中发生错误: {str(e)}'
        }, 500


@import_bp.route('/sync_air8', methods=['POST'])
@login_required
def sync_air8_data():
    """刷新融资单数据（一键同步的第3步）"""
    try:
        import_service = ImportService()
        result = import_service.refresh_all_financing_records()
        return result
    except Exception as e:
        return {
            'success': False,
            'message': f'刷新过程中发生错误: {str(e)}'
        }, 500
