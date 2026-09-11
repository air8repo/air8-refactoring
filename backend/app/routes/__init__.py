# 主路由蓝图
import os
from flask import Blueprint

# 获取当前文件的目录
current_dir = os.path.dirname(os.path.abspath(__file__))
# 获取app目录
app_dir = os.path.dirname(current_dir)
# 构建模板文件夹的绝对路径
template_dir = os.path.join(app_dir, 'templates')

main_bp = Blueprint('main', __name__, template_folder=template_dir)
auth_bp = Blueprint('auth', __name__, template_folder=template_dir)
import_bp = Blueprint('import', __name__, template_folder=template_dir)
export_bp = Blueprint('export', __name__, template_folder=template_dir)
maintenance_bp = Blueprint('maintenance', __name__, template_folder=template_dir)
language_bp = Blueprint('language', __name__, template_folder=template_dir)
batch_bp = Blueprint('batch', __name__, template_folder=template_dir)
api_bp = Blueprint('api', __name__)
tools_bp = Blueprint('tools', __name__, template_folder=template_dir)
fcb_bp = Blueprint('fcb', __name__, template_folder=template_dir)
credit_bp = Blueprint('credit', __name__, template_folder=template_dir)

# 导入路由定义
from backend.app.routes import main, auth, import_data, export, maintenance, language, batch, api, tools, fcb, credit
