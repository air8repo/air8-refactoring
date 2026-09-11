# Flask自动重启Agent

## 功能介绍

这是一个用于自动重启Flask服务的Agent，它可以：

1. 监控代码文件变化（Python文件和HTML模板）
2. 自动检测5000端口的Flask服务
3. 当检测到代码变化时，自动重启Flask服务
4. 支持手动停止服务

## 安装依赖

```bash
pip install watchdog
```

## 使用方法

### 方式1：直接运行Python脚本

```bash
python auto_restart_agent.py
```

### 方式2：使用Windows批处理脚本

双击运行 `start_auto_restart.bat` 文件，或在命令行中执行：

```bash
start_auto_restart.bat
```

## 工作原理

1. **代码监控**：使用 `watchdog` 库监控以下目录的文件变化：
   - `backend/app`（Python代码）
   - `backend/app/templates`（HTML模板）

2. **端口检测**：使用 `netstat` 命令查找监听5000端口的进程

3. **进程管理**：使用 `taskkill` 命令终止现有Flask进程

4. **服务重启**：在新的控制台窗口中启动Flask服务

## 配置说明

在 `auto_restart_agent.py` 文件中可以修改以下配置：

| 配置项 | 默认值 | 说明 |
|-------|-------|------|
| `app_path` | `backend.app` | Flask应用路径 |
| `port` | `5000` | Flask服务端口 |
| `watched_dirs` | 如上文所述 | 监控目录列表 |
| `restart_delay` | `1` | 重启延迟（秒），避免频繁重启 |

## 停止服务

1. 按 `Ctrl+C` 停止Agent
2. Agent会自动终止Flask服务

## 注意事项

1. 确保已安装 `watchdog` 库
2. 确保Flask服务使用5000端口
3. 建议在开发环境中使用，生产环境请使用正式的WSGI服务器
4. 服务会在新的控制台窗口中启动，方便查看日志

## 开发说明

### 主要文件

- `auto_restart_agent.py`：主程序文件，包含Agent实现
- `start_auto_restart.bat`：Windows启动脚本

### 核心类

- `CodeChangeHandler`：处理文件变化事件
- `FlaskAutoRestartAgent`：Flask自动重启Agent主类

## 测试

1. 启动Agent
2. 修改任意Python文件或HTML模板
3. 观察是否自动重启Flask服务

## 版本历史

- v1.0.0：初始版本，支持基本的自动重启功能

## 许可证

MIT
