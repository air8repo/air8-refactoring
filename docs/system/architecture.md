# 系统架构文档

## 1. 系统架构概述

再保理数据同步系统（Refactoring Data Synchronization System）是一个基于 Flask 的前后端一体化 Web 应用，用于管理融资订单、还款记录、银行对账单和数据聚合。

### 架构设计理念

- **分层架构**：路由层、业务逻辑层、数据访问层分离
- **模块化设计**：各功能模块独立，便于维护和扩展
- **策略模式**：导入导出服务采用策略模式支持多种数据类型和格式
- **工厂模式**：银行对账单解析采用工厂模式支持多家银行
- **应用工厂模式**：Flask 应用使用工厂模式创建，支持多环境配置

### 整体架构图

```
┌─────────────────────────────────────────────────────────┐
│                    用户界面层 (Templates)                 │
│              Jinja2 模板 + Bootstrap 5.3 前端             │
└──────────────────┬──────────────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────────────┐
│                    路由层 (Routes)                        │
│  main_bp(/)  auth_bp(/auth)  import_bp(/import)         │
│  export_bp(/export)  batch_bp(/)  maintenance_bp        │
│  api_bp(/api)  tools_bp(/tools)  language_bp(/)         │
└──────────────────┬──────────────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────────────┐
│                   业务逻辑层 (Services)                   │
│  ImportService  ExportService  AggregateService         │
│  BatchService  CleaningService  BankParserFactory       │
└──────────────────┬──────────────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────────────┐
│                   数据访问层 (MongoDB + pymongo)          │
│  refactoring_financing_order  refactoring_repayment_order│
│  refactoring_bank_statement  refactoring_financing_overview│
│  refactoring_onboard_config  users                      │
└─────────────────────────────────────────────────────────┘
```

## 2. 技术栈

| 类别 | 技术 | 用途 |
|------|------|------|
| 后端框架 | Flask 2.3+ | Web 应用框架 |
| 数据库 | MongoDB 4.4+ | NoSQL 文档数据库 |
| 数据库驱动 | pymongo 4.0+ | MongoDB Python 驱动 |
| 数据处理 | pandas 2.0+ | Excel 数据读写和处理 |
| 前端框架 | Bootstrap 5.3 | 响应式 UI 框架 |
| 模板引擎 | Jinja2 | HTML 模板渲染 |
| 用户认证 | Flask-Login | 用户登录和会话管理 |
| 密码加密 | Werkzeug | 密码哈希（PBKDF2+SHA256） |
| HTTP 客户端 | requests | 外部 API 调用 |
| 并发处理 | concurrent.futures | 多线程并行处理 |

## 3. 应用工厂模式

### 入口

```python
# run_flask.py
from backend.app import create_app
app = create_app()  # 默认开发环境
```

### 创建流程

```
create_app(config_class=None)
├─ 加载配置类（默认 DevelopmentConfig）
├─ 创建 Flask 实例，设置模板路径
├─ 初始化扩展 init_extensions(app)
│  ├─ LoginManager
│  ├─ Babel
│  └─ MongoDB 连接
├─ 注册 9 个蓝图
├─ 设置 before_request（语言偏好）
├─ 设置 after_request（Cookie）
├─ 注册 context_processor（翻译函数 _()）
└─ 返回应用实例
```

### 配置管理

`backend/app/config.py` 支持三种环境：

| 环境 | 配置类 | 特点 |
|------|--------|------|
| dev | DevelopmentConfig | DEBUG=True |
| test | TestingConfig | TESTING=True |
| prod | ProductionConfig | DEBUG=False |

关键配置项：`SECRET_KEY`、`MONGODB_URI`、`MAX_CONTENT_LENGTH`(16MB)、`ALLOWED_EXTENSIONS`({xlsx, xls})、`API_TOKEN`

## 4. 蓝图/路由结构

| 蓝图 | URL 前缀 | 路由文件 | 职责 |
|-----|----------|---------|------|
| main_bp | / | `routes/main.py` | 仪表盘、统计 API |
| auth_bp | /auth | `routes/auth.py` | 登录、注册、登出 |
| import_bp | /import | `routes/import_data.py` | 文件/API 导入 |
| export_bp | /export | `routes/export.py` | 数据导出、文件生成 |
| maintenance_bp | /maintenance | `routes/maintenance.py` | 数据维护、聚合 |
| batch_bp | / | `routes/batch.py` | 批次管理 |
| language_bp | / | `routes/language.py` | 语言切换 |
| api_bp | /api | `routes/api.py` | 外部 API 接口 |
| tools_bp | /tools | `routes/tools.py` | 工具函数 |

## 5. 服务层架构

### ImportService（数据导入）
- 从 Excel 文件或外部 API 读取数据
- 调用 CleaningService 进行数据验证
- 幂等导入到 MongoDB（upsert）
- 支持：onboarding、financing、repayment、bank_statement 等类型

### ExportService（数据导出）
- 从 MongoDB 查询数据
- 通过 pandas DataFrame 转换
- 导出为 Excel/CSV/PDF
- 生成 DB 放款文件和还款文件

### AggregateService（数据聚合）
- MongoDB 聚合管道
- 融资订单 + 还款 + 对账单 → 融资概览
- 支持全量和单笔聚合
- ThreadPoolExecutor 并行处理

### BatchService（批次管理）
- 融资订单批次分组
- 批次号生成、更新、作废
- 作废后触发聚合刷新

### CleaningService（数据清洗）
- 数据类型验证和转换
- 日期→datetime，金额→Decimal128
- 格式标准化和缺失值处理

### BankParserFactory（银行解析工厂）
- BaseParser 基类 + 具体实现
- ParserFactory 工厂创建解析器
- 支持 DB 等银行渠道

## 6. 数据库访问模式

全局 MongoDB 实例在 `extensions.py` 中初始化：

```python
client = MongoClient(app.config['MONGODB_URI'])
mongo = client.get_database()
app.extensions['mongo'] = mongo
```

访问方式：
1. `from backend.app.extensions import mongo` — 直接导入
2. `current_app.extensions['mongo']` — Flask 请求上下文
3. 无 ORM，直接使用 pymongo 操作（find、insert、update、aggregate）

## 7. 国际化机制

- 自定义 JSON 方案（非 Flask-Babel .po 文件）
- 翻译文件：`backend/app/i18n/` 下 4 个 JSON 文件（zh-CN、en-US、zh、en）
- 翻译函数 `_()` 通过 `context_processor` 注入 Jinja2
- 点号键名：`"common.title.dashboard"`
- 语言选择优先级：URL 参数 > Cookie > 默认 zh-CN

## 8. 认证机制

- Flask-Login + Werkzeug 密码哈希
- User 模型继承 UserMixin，存储在 MongoDB `users` 集合
- `@login_required` 装饰器保护路由
- 外部 API 使用固定 Token 鉴权（`X-API-Token` 头或 `?token=` 参数）

## 9. 目录结构

```
air8-refactoring/
├── run_flask.py                    # 应用入口
├── backend/
│   ├── app/
│   │   ├── __init__.py            # 应用工厂
│   │   ├── config.py              # 配置管理
│   │   ├── extensions.py          # 扩展初始化
│   │   ├── routes/                # 路由蓝图（9个）
│   │   ├── services/              # 业务逻辑层
│   │   │   ├── import_service.py
│   │   │   ├── export_service.py
│   │   │   ├── aggregate_service.py
│   │   │   ├── batch_service.py
│   │   │   ├── cleaning_service.py
│   │   │   └── bank_parser/       # 银行解析器（工厂模式）
│   │   ├── models/user.py         # 用户模型
│   │   ├── forms/auth.py          # 认证表单
│   │   ├── templates/             # Jinja2 模板
│   │   ├── static/                # 静态资源
│   │   └── i18n/                  # 翻译文件
│   ├── tests/                     # 单元测试
│   └── scripts/                   # 维护脚本
└── docs/                          # 项目文档
```
