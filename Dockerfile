# 使用Python 3.11 slim基础镜像
FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 复制项目文件
COPY backend/ ./backend/

# 复制根目录下的auto_restart_agent.py文件
COPY auto_restart_agent.py ./

# 安装依赖
RUN pip install --no-cache-dir -r backend/requirements.txt

# 设置环境变量
ENV FLASK_APP=backend.app
ENV PYTHONPATH=/app
ENV DEBUG=True

# 暴露端口
EXPOSE 5000

# 启动命令
CMD ["python", "-m", "flask", "run", "--host", "0.0.0.0", "--debug"]