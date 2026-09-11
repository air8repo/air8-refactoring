# 再保理系统技术规格说明书

> ⚠️ 本文档为历史参考，已被 [docs/system/requirements.md](../docs/system/requirements.md) 取代，不再维护。

## 1. 项目概述

再保理系统是一个用于管理融资订单、还款记录、银行对账单和数据聚合的金融管理系统。该系统支持数据导入导出、批量处理、数据聚合分析等功能，帮助企业实现对再保理业务的全面管理。

### 1.1 系统架构

系统采用前后端一体化的Flask应用架构：

```
app/
 ├─ __init__.py              # Flask应用创建
 ├─ config.py                # 配置管理
 ├─ extensions.py            # 扩展初始化（MongoDB、LoginManager、Babel）
 ├─ routes/                  # API路由和页面路由
 ├─ services/                # 业务逻辑服务
 ├─ models/                  # 数据模型
 ├─ forms/                   # 表单定义
 ├─ templates/               # HTML模板
 ├─ static/                  # 静态资源（CSS、JS、图片）
 └─ i18n/                    # 国际化文件
```

### 1.2 技术栈

| 类别 | 技术 | 版本 |
|------|------|------|
| 后端框架 | Flask | 2.3+ |
| 数据库 | MongoDB | 4.4+ |
| 数据处理 | pandas | 2.0+ |
| 前端框架 | Bootstrap | 5.3 |
| 用户认证 | Flask-Login | 0.6+ |
| 国际化 | Flask-Babel | 3.1+ |
| Excel处理 | openpyxl | 3.1+ |

## 2. 核心功能模块

### 2.1 数据导入模块

**功能说明**：支持从Excel文件和API导入各类业务数据

**实现细节**：
- 基于策略模式设计的导入服务（`ImportService`）
- 支持的数据类型：Onboarding配置、融资订单、还款订单、银行对账单、融资概览、批次号
- 数据清洗和验证（`CleaningService`）
- 支持幂等导入（upsert）

**核心代码**：
```python
class ImportService:
    def import_file(self, file, import_type, bank_channel='DB'):
        # 根据导入类型选择不同的清洗和导入策略
        if import_type == 'financing':
            cleaned_df = self.cleaning_service.clean_financing_data(df)
            return self._import_financing(cleaned_df)
        # ...其他导入类型
```

### 2.2 数据导出模块

**功能说明**：支持将各类业务数据导出为Excel、CSV、PDF格式

**实现细节**：
- 基于策略模式设计的导出服务（`ExportService`）
- 支持的数据类型：融资订单、还款订单、银行对账单、融资概览
- 支持自定义过滤条件
- 支持生成DB放款文件和还款文件

**核心代码**：
```python
class ExportService:
    def export_data(self, export_type, data_type, filters=None):
        # 获取数据
        data = self._get_data(data_type, filters)
        # 根据导出类型选择不同的导出策略
        if export_type == 'excel':
            return self._export_to_excel(data, data_type)
        # ...其他导出类型
```

### 2.3 数据聚合模块

**功能说明**：将融资订单、还款订单和银行对账单数据聚合到融资概览表

**实现细节**：
- 基于MongoDB聚合框架实现
- 支持全量聚合和部分聚合（按融资申请号）
- 支持并行处理以提高性能
- 支持幂等更新

**核心代码**：
```python
class AggregateService:
    def aggregate_financing_overview(self):
        # 筛选符合条件的银行对账单
        confirmed_statements = list(mongo.refactoring_bank_statement.find({...}))
        # 构建数据映射
        invoice_to_financing = {config.get('uid'): config for config in onboard_configs}
        # 并行处理银行对账单
        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            # ...并行处理逻辑
        # 批量更新或插入融资概览记录
        # ...批量操作逻辑
```

### 2.4 批次管理模块

**功能说明**：管理融资单批次和还款批次

**实现细节**：
- 支持批次生成、查询和作废
- 支持批量更新融资单批次信息
- 支持还款批次管理

**核心代码**：
```python
# 生成DB放款文件
def generate_db_loan_file(self, batch_date, bank_channel='db'):
    # 获取下一个批次号
    batch_number = self._get_next_batch_number()
    # 筛选符合条件的融资订单
    financing_orders = list(mongo.refactoring_financing_order.find({...}))
    # 更新融资订单的批次相关字段
    update_result = mongo.refactoring_financing_order.update_many(...)
    # 生成Excel文件并打包
    # ...文件生成逻辑
```

### 2.5 仪表盘模块

**功能说明**：提供数据统计和可视化展示

**实现细节**：
- 展示融资订单、还款记录、银行对账单等数据的统计信息
- 提供结算计划和DB放款报表
- 支持数据过滤和排序

**核心代码**：
```python
@main_bp.route('/dashboard')
@login_required
def dashboard():
    # 获取统计数据
    stats = {
        'financing_count': mongo.refactoring_financing_order.count_documents({}),
        'repayment_count': mongo.refactoring_repayment_order.count_documents({}),
        # ...其他统计数据
    }
    # 获取Settlement Schedule数据
    settlement_schedule = get_settlement_schedule()
    # ...其他数据获取逻辑
    # 渲染模板
    return render_template('dashboard.html', **locals())
```

### 2.6 用户认证模块

**功能说明**：管理用户登录和权限控制

**实现细节**：
- 基于Flask-Login实现
- 支持用户密码加密存储
- 支持登录状态管理

**核心代码**：
```python
class User(UserMixin):
    @staticmethod
    def get(user_id):
        # 获取用户信息
        user_data = mongo.users.find_one({'_id': ObjectId(user_id)})
        if user_data:
            return User(user_data['_id'], user_data['username'], user_data['password_hash'])
        return None
    
    def check_password(self, password):
        # 验证密码
        return check_password_hash(self.password_hash, password)
```

### 2.7 国际化模块

**功能说明**：支持多语言切换

**实现细节**：
- 基于Flask-Babel实现
- 支持中文和英文
- 支持URL参数和Cookie存储语言偏好

**核心代码**：
```python
# 语言选择函数
def get_locale():
    # 从查询参数获取语言偏好
    lang = request.args.get('lang')
    # 标准化语言代码
    if lang in ['zh', 'zh-cn', 'zh_cn']:
        lang = 'zh_CN'
    elif lang in ['en', 'en-us', 'en_us']:
        lang = 'en_US'
    # 返回语言代码
    return lang
```

## 3. 数据模型设计

### 3.1 集合列表

| 集合名称 | 描述 |
|----------|------|
| refactoring_onboard_config | Onboarding配置表 |
| refactoring_financing_order | 融资订单表 |
| refactoring_repayment_order | 还款订单表 |
| refactoring_bank_statement | 银行对账单表 |
| refactoring_financing_overview | 融资概览表 |
| users | 用户表 |
| refactoring_bank_repayment_record | 银行还款记录表 |

### 3.2 核心集合结构

#### 3.2.1 refactoring_financing_order（融资订单表）

```json
{
  "_id": ObjectId,
  "uid": String,              // 唯一标识
  "finance_request_number": String,  // 融资申请号
  "invoice_number": String,   // 发票号
  "supplier_name": String,    // 供应商名称
  "buyer_name": String,       // 买家名称
  "trade_amount": Decimal128, // 交易金额
  "financing_amount": Decimal128, // 融资金额
  "due_date": Date,          // 到期日
  "batch_number": Number,    // 批次号
  "batch_status": String,    // 批次状态
  "bank_source": String,     // 银行来源
  "status": String,          // 状态
  "created_at": Date,        // 创建时间
  "updated_at": Date         // 更新时间
}
```

#### 3.2.2 refactoring_bank_statement（银行对账单表）

```json
{
  "_id": ObjectId,
  "bank_channel": String,    // 银行渠道
  "invoice": {
    "system_invoice_id": String, // 系统发票ID
    "status": String,        // 发票状态
    "seller_reference": String,  // 供应商参考号
    "buyer_reference": String,   // 买家参考号
    "issue_date": Date,      // 开票日期
    "due_date": Date,        // 到期日
    "currency": String,      // 货币
    "original_amount": Decimal128 // 原始金额
  },
  "finance": {
    "db_finance_ref": String,    // DB融资参考号
    "finance_amount": Decimal128, // 融资金额
    "status": String,        // 融资状态
    "start_date": Date,      // 开始日期
    "due_date": Date         // 到期日
  },
  "usd_details": {
    "original_amount": Decimal128, // USD原始金额
    "finance_amount": Decimal128,  // USD融资金额
    "interest_amount": Decimal128, // USD利息金额
    "purchase_price": Decimal128,  // USD购买价格
    "outstanding_amount": Decimal128 // USD未结金额
  },
  "created_at": Date,        // 创建时间
  "updated_at": Date         // 更新时间
}
```

#### 3.2.3 refactoring_financing_overview（融资概览表）

```json
{
  "_id": ObjectId,
  "finance_request_number": String,  // 融资申请号
  "buyer_name": String,       // 买家名称
  "seller_name": String,      // 供应商名称
  "loan_submission_batch": Number,   // 贷款提交批次
  "order_details": {
    "invoice_number": String,   // 发票号
    "due_date": Date,          // 到期日
    "air8_finance_amt": Decimal128 // Air8融资金额
  },
  "bank_statements": [{
    "system_invoice_id": String, // 系统发票ID
    "finance_amount": Decimal128,  // 融资金额
    "interest_amount_usd": Decimal128, // 利息金额（USD）
    "outstanding_amount_usd": Decimal128, // 未结金额（USD）
    "purchase_price_usd": Decimal128, // 购买价格（USD）
    "status": String,        // 状态
    "start_date": Date       // 开始日期
  }],
  "repayments": [{
    "repayment_from_buyer_to_air8": Decimal128, // 买家还款给Air8
    "repayment_status": String,   // 还款状态
    "settlement_date": Date       // 结算日期
  }],
  "totals": {
    "finance_amount_usd": Decimal128, // 融资金额（USD）
    "outstanding_amount_usd": Decimal128, // 未结金额（USD）
    "air8_settled_fr_amt": Decimal128, // Air8结算金额
    "settled_db_loan": Decimal128, // 已结DB贷款
    "wip_pending_amount": Decimal128 // WIP待处理金额
  },
  "bank_source": String,     // 银行来源
  "refactoring_status": String, // 重构状态
  "updated_at": Date         // 更新时间
}
```

## 4. API接口设计

### 4.1 认证接口

| 接口 | 方法 | 路径 | 功能 |
|------|------|------|------|
| 用户登录 | POST | /auth/login | 用户登录 |
| 用户登出 | GET | /auth/logout | 用户登出 |

### 4.2 数据管理接口

| 接口 | 方法 | 路径 | 功能 |
|------|------|------|------|
| 文件上传 | POST | /import/upload | 上传Excel文件 |
| API导入 | POST | /import/import_from_api | 从API导入数据 |
| 数据导出 | POST | /export/generate | 导出数据 |
| 生成DB放款文件 | POST | /export/generate_db_loan_file | 生成DB放款文件 |
| 生成DB还款文件 | POST | /export/generate_db_repayment_file | 生成DB还款文件 |
| 刷新融资单 | POST | /export/refresh-financing-orders | 刷新融资单 |
| 更新融资概览 | POST | /export/update_overview | 更新融资概览 |

### 4.3 数据聚合接口

| 接口 | 方法 | 路径 | 功能 |
|------|------|------|------|
| 执行数据聚合 | POST | /maintenance/aggregate | 执行数据聚合 |
| 部分数据聚合 | POST | /maintenance/aggregate_partial | 按融资申请号聚合 |

### 4.4 批次管理接口

| 接口 | 方法 | 路径 | 功能 |
|------|------|------|------|
| 批次列表 | GET | /maintenance/batch_list | 获取批次列表 |
| 作废批次 | POST | /maintenance/cancel_batch | 作废批次 |
| 还款批次列表 | GET | /maintenance/repayment_batch_list | 获取还款批次列表 |
| 作废还款批次 | POST | /maintenance/cancel_repayment_batch | 作废还款批次 |

### 4.5 仪表盘接口

| 接口 | 方法 | 路径 | 功能 |
|------|------|------|------|
| 月度融资统计 | GET | /api/get_monthly_financing_with_statement_stats | 获取月度融资统计 |
| 结算计划数据 | GET | /api/get_settlement_schedule | 获取结算计划数据 |
| DB放款数据 | GET | /api/get_db_disbursement | 获取DB放款数据 |

## 5. 性能与安全

### 5.1 性能优化

1. **数据处理优化**
   - 使用pandas批量处理Excel数据
   - 采用MongoDB聚合框架进行数据聚合
   - 实现并行处理提高数据聚合效率

2. **查询优化**
   - 为频繁查询的字段创建索引
   - 使用批量操作减少数据库交互
   - 实现数据缓存机制

3. **文件处理优化**
   - 采用流式处理大文件
   - 实现文件压缩和分块传输

### 5.2 安全措施

1. **用户认证与授权**
   - 基于Flask-Login实现用户认证
   - 密码使用Werkzeug安全哈希存储
   - 支持会话管理和CSRF保护

2. **数据安全**
   - 敏感数据加密存储
   - 实现数据访问控制
   - 定期备份数据库

3. **API安全**
   - 实现API访问控制
   - 支持请求频率限制
   - 实现输入验证和过滤

## 6. 部署与维护

### 6.1 部署方式

1. **本地部署**
   ```bash
   python run_flask.py
   ```

2. **Docker部署**
   ```bash
   docker build -t refactoring-system .
   docker run -p 5000:5000 refactoring-system
   ```

### 6.2 环境配置

| 环境变量 | 描述 | 默认值 |
|----------|------|--------|
| SECRET_KEY | Flask密钥 | dev-secret-key |
| MONGODB_URI | MongoDB连接字符串 | mongodb://localhost:27017/refactoring |
| DEBUG | 调试模式 | True |
| TESTING | 测试模式 | False |

### 6.3 维护计划

1. **定期维护**
   - 数据库备份（每日）
   - 日志清理（每周）
   - 性能监控（实时）

2. **异常处理**
   - 实现全局异常处理
   - 记录详细错误日志
   - 提供错误恢复机制

## 7. 扩展性设计

### 7.1 模块化设计

系统采用模块化设计，各功能模块独立，便于扩展和维护：

- 新增银行渠道支持：在`bank_parser`目录下添加新的解析器
- 新增数据导入导出格式：在`ImportService`和`ExportService`中添加新的策略
- 新增报表类型：在`dashboard`和`export`模块中添加新的报表生成逻辑

### 7.2 插件机制

系统支持通过扩展点实现插件功能：

- 数据清洗扩展：在`cleaning_service.py`中添加新的清洗规则
- 数据聚合扩展：在`aggregate_service.py`中添加新的聚合规则
- 导出格式扩展：在`export_service.py`中添加新的导出格式

## 8. 测试策略

### 8.1 测试类型

- 单元测试：测试单个函数和方法
- 集成测试：测试模块间的交互
- 功能测试：测试完整的业务流程
- 性能测试：测试系统的响应性能

### 8.2 测试工具

| 测试类型 | 工具 |
|----------|------|
| 单元测试 | pytest |
| 集成测试 | pytest + Flask-Testing |
| API测试 | pytest + requests |
| 性能测试 | locust |

### 8.3 测试覆盖率

| 模块 | 目标覆盖率 |
|------|------------|
| services | 90%+ |
| models | 80%+ |
| routes | 70%+ |
| forms | 60%+ |

## 9. 版本控制

### 9.1 版本策略

采用语义化版本控制：

```
X.Y.Z
├── X：主版本号（不兼容的API变更）
├── Y：次版本号（功能性新增和修改）
└── Z：修订号（错误修复）
```

### 9.2 发布流程

1. 功能开发完成
2. 编写并通过所有测试
3. 更新版本号和CHANGELOG
4. 构建并部署
5. 验证发布结果

## 10. 文档管理

### 10.1 文档类型

- 技术规格说明书
- 需求规格说明书
- API文档
- 用户手册
- 部署手册

### 10.2 文档维护

- 文档与代码同步更新
- 使用Markdown格式编写
- 支持在线浏览和下载

## 11. 总结

再保理系统是一个功能完善、架构清晰的金融管理系统，采用现代Web技术栈实现。系统支持数据导入导出、批量处理、数据聚合分析等核心功能，具备良好的性能、安全性和扩展性。

系统的模块化设计和灵活的插件机制使得它能够适应业务需求的变化，为企业提供可靠的再保理业务管理解决方案。