import os
from flask import Flask
from backend.app import create_app

# 设置环境变量
os.environ['FLASK_APP'] = 'backend.app'
os.environ['FLASK_ENV'] = 'development'

# 创建并运行应用
app = create_app()

if __name__ == '__main__':
    app.run(debug=True, port=5000)