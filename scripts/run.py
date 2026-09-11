import sys
import os

# 添加当前目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app import create_app

# 创建应用实例
app = create_app()

# 明确设置模板文件夹路径
app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
app.template_folder = os.path.join(app_dir, 'backend', 'app', 'templates')

# 打印调试信息
print(f"应用根目录: {app.root_path}")
print(f"模板文件夹路径: {app.template_folder}")
print(f"模板文件夹存在: {os.path.exists(app.template_folder)}")
print(f"login.html存在: {os.path.exists(os.path.join(app.template_folder, 'login.html'))}")

# 打印路由信息
print("\n已注册的路由:")
for rule in app.url_map.iter_rules():
    print(f"  {rule}")

# 添加错误处理
@app.errorhandler(500)
def internal_error(error):
    import traceback
    return traceback.format_exc(), 500

# 确保在开发模式下运行，并且禁用模板缓存
if __name__ == '__main__':
    app.config['TEMPLATES_AUTO_RELOAD'] = True
    app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
    app.run(debug=True, use_reloader=False, host='0.0.0.0')
