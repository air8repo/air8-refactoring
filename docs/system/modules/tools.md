# 工具模块 (tools)

## 概述
辅助工具集合模块，提供各类实用工具功能。当前实现了发票文件批量下载工具，通过调用外部 n8n webhook API 获取发票文件并打包为 ZIP 返回。设计为可扩展架构，支持后续添加更多工具。

## 路由
| 方法 | 路径 | 说明 | 认证要求 |
|------|------|------|----------|
| GET | /tools/ | 工具首页，列出所有可用工具 | @login_required |
| GET | /tools/invoice-download | 发票下载工具页面 | @login_required |
| POST | /tools/invoice-download | 处理发票文件下载请求 | @login_required |

## 核心逻辑

### 发票文件批量下载
1. 用户输入融资编号（每行一个）
2. 按 50 个一批调用外部 API（多批并行 `ThreadPoolExecutor`）
3. 并行下载所有文件（最多 10 个并发线程）
4. 按 `invoice_no + financing_no` 分组打包 ZIP
5. 单组直接打包，多组嵌套子 ZIP

### 配置
| 配置项 | 值 |
|--------|-----|
| API 地址 | `https://n8n.air8.cn/webhook/downloadInvoiceFiles` |
| 批次大小 | 50 |
| 最大下载并发 | 10 |

### 文件名处理
- 优先从 `Content-Disposition` 响应头提取
- 其次从 URL 路径解析
- 清洗非法字符：`\/:*?"<>|`

## 关键文件
| 文件路径 | 职责 |
|----------|------|
| `backend/app/routes/tools.py` | 路由和下载逻辑 |
| `backend/app/templates/tools/index.html` | 工具首页模板 |
| `backend/app/templates/tools/invoice_download.html` | 发票下载页面模板 |
