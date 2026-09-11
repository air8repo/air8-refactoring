import sys
import os

# 确保应用程序在正确的目录中运行
os.chdir(os.path.dirname(os.path.abspath(__file__)))

print(f"Python version: {sys.version}")
print(f"Current directory: {os.getcwd()}")

# 直接运行run.py并捕获输出
import subprocess
result = subprocess.run([sys.executable, 'run.py'], capture_output=True, text=True, timeout=10)

print("=== Run.py Output ===")
print(f"Exit code: {result.returncode}")
print("\n--- STDOUT ---")
print(result.stdout)
print("\n--- STDERR ---")
print(result.stderr)
print("=== End of Output ===")
