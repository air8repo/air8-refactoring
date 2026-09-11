#!/usr/bin/env python3
"""
自动重启Flask服务的agent
监控代码变化，自动重启5000端口的Flask服务
"""

import os
import time
import subprocess
import signal
import re
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class CodeChangeHandler(FileSystemEventHandler):
    """处理代码变化事件"""
    def __init__(self, restart_callback):
        self.restart_callback = restart_callback
        self.last_restart = 0
        self.restart_delay = 1  # 重启延迟，避免频繁重启
    
    def on_modified(self, event):
        """当文件被修改时触发"""
        # 只处理Python文件和HTML模板文件
        if event.is_directory:
            return
        
        if event.src_path.endswith('.py') or event.src_path.endswith('.html'):
            print(f"\n检测到文件变化: {event.src_path}")
            current_time = time.time()
            if current_time - self.last_restart > self.restart_delay:
                self.restart_callback()
                self.last_restart = current_time

class FlaskAutoRestartAgent:
    """Flask自动重启agent"""
    def __init__(self, app_path="backend.app", port=5000):
        self.app_path = app_path
        self.port = port
        self.flask_process = None
        self.observer = None
        self.watched_dirs = [
            "c:\\Users\\v-tuanjiexu\\xutuanjie\\aicode\\backend\\app",
            "c:\\Users\\v-tuanjiexu\\xutuanjie\\aicode\\backend\\app\\templates"
        ]
    
    def find_process_by_port(self, port):
        """根据端口号查找进程PID"""
        try:
            # 使用netstat命令查找端口占用情况
            result = subprocess.run(
                ["netstat", "-ano"],
                capture_output=True,
                text=True,
                encoding="gbk"
            )
            
            # 查找监听指定端口的进程
            pattern = rf"TCP\s+0\.0\.0\.0:{port}\s+0\.0\.0\.0:0\s+LISTENING\s+([0-9]+)"
            match = re.search(pattern, result.stdout)
            if match:
                return int(match.group(1))
            return None
        except Exception as e:
            print(f"查找进程失败: {e}")
            return None
    
    def kill_process(self, pid):
        """终止指定PID的进程"""
        try:
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/F"],
                capture_output=True,
                text=True
            )
            print(f"已终止进程 {pid}")
            return True
        except Exception as e:
            print(f"终止进程 {pid} 失败: {e}")
            return False
    
    def start_flask(self):
        """启动Flask服务"""
        print("\n正在启动Flask服务...")
        # 启动Flask服务，使用新的控制台窗口
        cmd = f"python -m flask --app {self.app_path} run --host=0.0.0.0 --port={self.port}"
        self.flask_process = subprocess.Popen(
            ["cmd.exe", "/c", f"start", "cmd.exe", "/k", cmd],
            shell=False
        )
        print(f"Flask服务已启动，监听端口 {self.port}")
    
    def restart_flask(self):
        """重启Flask服务"""
        print("\n" + "="*60)
        print("开始重启Flask服务...")
        print("="*60)
        
        # 查找并终止现有进程
        pid = self.find_process_by_port(self.port)
        if pid:
            self.kill_process(pid)
            time.sleep(0.5)  # 等待进程完全终止
        
        # 启动新服务
        self.start_flask()
    
    def start_monitoring(self):
        """开始监控代码变化"""
        print("启动代码监控...")
        
        # 初始化事件处理器
        event_handler = CodeChangeHandler(self.restart_flask)
        
        # 初始化观察者
        self.observer = Observer()
        
        # 添加监控目录
        for dir_path in self.watched_dirs:
            if os.path.exists(dir_path):
                self.observer.schedule(event_handler, dir_path, recursive=True)
                print(f"监控目录: {dir_path}")
            else:
                print(f"目录不存在: {dir_path}")
        
        # 启动观察者
        self.observer.start()
        
        # 初始启动Flask服务
        self.restart_flask()
        
        print("\nFlask自动重启agent已启动")
        print("按 Ctrl+C 停止服务")
        
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop()
    
    def stop(self):
        """停止agent"""
        print("\n停止Flask自动重启agent...")
        
        # 停止观察者
        if self.observer:
            self.observer.stop()
            self.observer.join()
        
        # 终止Flask进程
        pid = self.find_process_by_port(self.port)
        if pid:
            self.kill_process(pid)
        
        print("Flask自动重启agent已停止")

if __name__ == "__main__":
    # 创建并启动agent
    agent = FlaskAutoRestartAgent()
    agent.start_monitoring()