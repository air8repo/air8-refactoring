# 再保理系统需求基线文档

> 本文档为系统需求的唯一权威基线，描述系统当前实际行为。
> 每个功能 spec（`docs/superpowers/specs/*-design.md`）对应的计划完成后，须将其需求合并进本文档对应章节并登记变更记录。
> 取代 `backend/reqspec.md`（历史参考）。

## 1. 引言

### 1.1 文档目的

本文档描述再保理数据同步系统（Refactoring Data Synchronization System）当前实际运行的功能需求与非功能需求，作为后续规格驱动开发（Spec-Driven Development）的唯一权威基线。当历史文档（如 `backend/reqspec.md`）与当前代码行为不一致时，以代码为准；本文档在编写时已按此原则对已知差异做了修正（见各章节及第 15 章变更记录）。

需求条目编号采用 `REQ-<模块缩写>-NNN` 格式（如 `REQ-AUTH-001`），每条需求包含用户故事和以 EARS（Easy Approach to Requirements Syntax）语法书写的验收标准。

### 1.2 术语定义

| 术语 | 定义 |
|------|------|
| 再保理 (Refactoring) | 银行或金融机构从保理商手中买断卖方企业的应收账款，同时承担与该应收账款相关的信用风险的业务模式 |
| 融资订单 (Financing Order) | 记录企业融资申请的单据，存储于 `refactoring_financing_order` 集合，包含发票信息、融资金额、到期日、批次信息、后处理衍生字段（状态、WIP、逾期利息等）|
| 还款订单 (Repayment Order) | 记录企业还款情况的单据，存储于 `refactoring_repayment_order` 集合，唯一键为 `finance_request_number` |
| 银行对账单 (Bank Statement) | 银行提供的记录发票融资状态、结清状态的单据，存储于 `refactoring_bank_statement` 集合，当前 upsert 唯一键为 `invoice.seller_reference` |
| 融资概览 (Financing Overview) | 聚合融资订单、还款记录和银行对账单三个数据源的综合视图，存储于 `refactoring_financing_overview` 集合，唯一键为 `finance_request_number` |
| 批次管理 (Batch Management) | 对已核准放款的融资单进行分组编号管理的功能，便于批量生成放款文件、批量追踪与作废 |
| 还款批次 (Repayment Batch) | 按还款日期（`batch_date`）分组的还款文件生成记录，存储于 `refactoring_bank_repayment_record` 集合 |
| Onboarding 配置 | 企业加入系统时的基础配置信息（客户代码、审批账期、目标名单状态等），存储于 `refactoring_onboard_config` 集合；支持 Excel 导入和外部 API 每日增量同步两种来源 |
| Loan booked | 银行对账单 `finance.status` 字段的一个取值，表示该笔发票已完成银行放款登记；是判定融资单"已融资"（`funded_before`）及触发数据聚合的核心条件（现行代码使用该值，而非历史文档中的 "Financing confirmed"）|
| WIP / Pending (DB o/s) | Work in Progress / Pending，融资单在 DB 银行侧的未结清金额，用于判断还款文件生成范围和额度查询汇总 |
| FCB | Factoring Client Bank（或系统内对接的商业保理客户方代码体系），指本系统 FCB 模块管理的客户及其交易数据导出功能，用于向 FCB 客户系统推送标准 24 列 Excel 交易文件 |
| Dummy 发票 (Dummy Invoice) | 通过 Tools 模块调用外部 n8n API 创建的测试用发票，用于联调和演示，不代表真实业务交易 |
| n8n | 系统对接的外部工作流自动化平台（域名 `n8n.air8.cn` / `n8n-v2.air8.cn`），承载发票文件下载、Dummy 发票创建、FCB 交易查询、Onboarding 数据导出、邮件通知发送等外部 Webhook 接口 |
| 额度查询 (Credit Query) | 额度管理模块提供的功能，按买方层汇总展示 DB 额度上限（Celling）、预占、实占、Headroom、占用率，支持展开至供应商层配对明细及 FR 单据明细，用于评估授信敞口并支撑每日超阈值预警 |
| Decimal128 | MongoDB 的高精度十进制数值类型，系统所有金额字段导入时统一转换为该类型存储，避免浮点数精度丢失 |

## 2. 用户认证与权限（REQ-AUTH-xxx）

### REQ-AUTH-001 用户注册

**用户故事**：作为系统管理员，我希望能够创建新的登录账号，以便为团队成员分配系统访问权限。

**验收标准**：

1. 当 未登录用户访问 `/auth/register` 页面 时，系统应 显示包含用户名、密码、确认密码字段的注册表单。
2. 当 用户提交注册表单且用户名已存在 时，系统应 拒绝创建并提示用户名已被占用。
3. 当 用户提交的密码与确认密码不一致 时，系统应 拒绝提交并提示两次密码不一致。
4. 当 用户名长度不在 2-20 字符范围内 时，系统应 拒绝提交并提示校验错误。
5. 当 注册信息校验通过 时，系统应 使用 Werkzeug 生成密码哈希并将新用户写入 `users` 集合，不存储明文密码。
6. 在 用户已登录 下，当 用户访问 `/auth/register` 时，系统应 自动跳转到仪表盘页面。

### REQ-AUTH-002 用户登录

**用户故事**：作为系统用户，我希望使用用户名和密码登录系统，以便访问受保护的业务功能。

**验收标准**：

1. 当 用户在 `/auth/login` 提交正确的用户名和密码 时，系统应 通过 `check_password_hash` 验证通过后建立登录会话并跳转到仪表盘（或 `next` 参数指定的页面）。
2. 当 用户提交的用户名不存在或密码不匹配 时，系统应 拒绝登录并显示错误提示，不透露具体是用户名错误还是密码错误。
3. 当 用户勾选"记住我" 时，系统应 延长会话有效期（Flask-Login remember 功能）。
4. 在 用户已登录 下，当 用户访问 `/auth/login` 时，系统应 自动跳转到仪表盘页面。

### REQ-AUTH-003 用户登出

**用户故事**：作为系统用户，我希望能够安全退出登录，以便在共享设备上保护账号安全。

**验收标准**：

1. 当 已登录用户访问 `/auth/logout` 时，系统应 清除当前用户会话并重定向到登录页面。

### REQ-AUTH-004 登录保护与用户加载

**用户故事**：作为系统管理员，我希望除认证入口外的所有业务页面都要求登录，以便防止未授权访问。

**验收标准**：

1. 当 未登录用户访问任何标记 `@login_required` 的路由（除 `/auth/*` 外，几乎所有页面路由） 时，系统应 重定向到登录页面并在登录成功后跳回原请求页面（`next` 参数）。
2. 当 Flask-Login 需要恢复会话中的用户对象 时，系统应 通过 `User.get(user_id)`（基于 MongoDB `_id`/ObjectId）从 `users` 集合加载用户。

## 3. 数据导入（REQ-IMPORT-xxx）

### REQ-IMPORT-001 Excel 文件上传与分发

**用户故事**：作为运营人员，我希望通过上传 Excel 文件将业务数据批量导入系统，以便避免手工逐条录入。

**验收标准**：

1. 当 用户在 `/import/upload` 提交文件 时，系统应 校验文件存在性、扩展名（仅 `.xlsx`、`.xls`）和 `import_type` 参数是否合法。
2. 当 文件超过 16MB 或扩展名不在 `.xlsx`/`.xls` 范围内 时，系统应 拒绝导入并返回错误提示。
3. 当 校验通过 时，系统应 使用 `pandas.read_excel()` 读取文件为 DataFrame，并根据 `import_type`（`onboarding`/`financing`/`repayment`/`bank_statement`/`financing_overview`/`batch_number`/`repayment_date`）分发到对应清洗与导入方法。
4. 当 `import_type` 不在支持的类型集合中 时，系统应 返回"无效的导入类型"错误，不写入数据库。

### REQ-IMPORT-002 数据清洗（CleaningService）

**用户故事**：作为运营人员，我希望上传的原始数据在写库前完成格式标准化和去重，以便避免脏数据污染业务表。

**验收标准**：

1. 当 导入 onboarding/financing/repayment/bank_statement/financing_overview 五类数据 时，系统应 分别调用对应清洗方法执行缺失值填充、日期标准化（`pd.to_datetime`）、数值标准化（`pd.to_numeric`）、按业务主键去重（`keep='last'`）、移除全空行。
2. 当 清洗融资订单数据且 `Finance Request Number`/`Invoice Number`/`Supplier Code`/`Buyer Code` 任一为空 时，系统应 过滤掉该行，不参与导入。
3. 当 清洗银行对账单数据且 `Invoice Details - System InvoiceID` 为空 时，系统应 过滤掉该行；`Finance Details - DB Finance Ref.` 不作为必填字段（拒绝/取消的发票本身可能没有该编号）。
4. 当 银行对账单数据中同一 `Invoice Details - Seller Reference` 存在多行 时，系统应 按 `Invoice Details - System InvoiceID` 升序排序后保留最后一条（即保留最大 System InvoiceID 的记录）。
5. 当 银行对账单 Excel 使用旧版列名（如 `Invoice Details - Discount Amount`、`Finance Details - Finance Status` 等） 时，系统应 通过列名别名映射表自动重命名为当前标准列名后再清洗。

### REQ-IMPORT-003 幂等 Upsert 导入

**用户故事**：作为运营人员，我希望重复上传同一份或增量更新的 Excel 文件不会产生重复记录，以便可以安全地多次导入。

**验收标准**：

1. 当 导入 Onboarding 配置 时，系统应 按 `uid` 查询已有记录，存在则 `replace_one` 更新（保留 `_id`/`created_at`），不存在则 `insert_one` 新增。
2. 当 导入融资订单 时，系统应 按 `finance_request_number` upsert，更新时保留已有的有效批次字段（`batch_number>0` 且 `batch_status='active'` 时保留，否则重置为默认值）。
3. 当 导入还款订单 时，系统应 按 `finance_request_number` upsert（唯一主键）。
4. 当 导入银行对账单 时，系统应 按 `invoice.seller_reference` upsert；金额字段统一转换为 `bson.Decimal128` 存储。
5. 当 导入融资概览 时，系统应 按 `finance_request_number` upsert。
6. 当 任一导入方法完成 时，系统应 返回 `{success, inserted, updated, total}` 格式的结果统计。
7. 当 通过 n8n 接口或 Excel 导入融资订单数据（`_import_financing`）时，系统应 将来源数据中的『Collection Period』『Financing Interest』列分别存入 `financing_order.collection_period`（整数）与 `financing_interest`（`Decimal128`）字段；单元格缺失或无法解析时分别按 `0`/`Decimal128('0')` 填充默认值，不中断整批导入。
8. 当 导入银行对账单数据 时，系统应 将 `Finance Details - Advance Ratio` 列的值转换为 `Decimal128` 后存入 `finance.advance_ratio_pct` 字段（原始百分比数值，如 `90` 表示 90%，使用方需自行 `÷100`）；单元格缺失或无法解析时按 `Decimal128('0')` 填充默认值（与其他 `finance.*` 百分比字段的缺省处理一致），不中断整批导入。

### REQ-IMPORT-004 融资订单后处理（衍生字段计算）

**用户故事**：作为运营人员，我希望融资订单导入后自动计算业务状态和金额衍生字段，以便无需手工核算即可判断放款资格和逾期情况。

**验收标准**：

1. 当 融资订单导入完成（新增或更新） 时，系统应 自动对受影响记录执行后处理，计算 `in_the_onboarding_list`、`target_list_status`、`funded_before`、`is_batch`、`settled_in_air8`、`fr_settlement_date`、`air8_settled_fr_amt`、`settled_db_loan`、`wip_pending`、`overdue_interest_settled_wip`、`overdue_interest_od_wip`、`outstanding_loan_excluded_wip`、`fr_overdue_in_coming_period`、`due_date_vs_submission_date`、`status`、`can_push_to_db_today`、`bank_finance_status` 字段。
2. 当 计算 `funded_before` 时，系统应 判定该融资单发票号（`invoice_number`）在 `refactoring_bank_statement` 中是否存在 `finance.status='Loan booked'` 的记录，或该融资单已有有效批次号（`batch_number>0`），任一满足即为 `True`。
3. 当 计算 `status` 时，系统应 按优先级依次判断：`target_list_status='Pending'` → `for next phase`；不在名单（`target_list_status != 'Y'`）→ `not on the list / Code mismatch`；`funded_before` → `funded before`；`fr_overdue_in_coming_period` → `OD related`；账期超出审批账期 → `Finance Tenor Exceed DB approved, pls resubmit later`；`settled_amt_partial` 为零 → `eligible`；否则 → `partial paid`。
4. 当 `status='eligible'` 时，系统应 将 `can_push_to_db_today` 置为 `True`，否则置为 `False`。
5. 当 用户在导出页面点击"刷新融资单" 或 通过 `POST /export/refresh-financing-orders`、`POST /api/financing/refresh` 触发 时，系统应 对全部融资订单重新执行后处理逻辑（`refresh_all_financing_records`）。

### REQ-IMPORT-005 银行对账单结清状态与结清日期原始字段

**用户故事**：作为运营人员，我希望系统输出银行侧未经篡改的结清状态和结清日期原始字段，以便准确判断发票是否已实际结清。

**验收标准**：

1. 当 导入银行对账单且 Excel 单元格 `Invoice Details - Settlement Status` 有值 时，系统应 写入 `invoice.settlement_status`；为空时存储为空字符串 `''`。
2. 当 导入银行对账单且 `Invoice Details - Settlement Date` 单元格为空或解析失败 时，系统应 将 `invoice.settlement_date` 与 `invoice.raw_settlement_date` 均保留为 `None`，不回退填充为导入时的系统当前时间。
3. 当 `POST /api/bank-statement` 输出结清日期 时，系统应 优先输出 `invoice.raw_settlement_date`；若记录不含该字段（历史存量记录），则回退输出 `invoice.settlement_date`，保持向后兼容。

### REQ-IMPORT-006 银行对账单拒绝/取消检测与邮件通知

**用户故事**：作为业务负责人，我希望银行对账单全量导入时系统能自动识别新出现的拒绝/取消/预订异常发票并发送邮件提醒，以便及时跟进处理，无需逐条人工比对。

**验收标准**：

1. 当 本次导入记录的 `Invoice Details - Status` 含子串 `rejected`（大小写不敏感），或 `Finance Details - Financing in statuses` 含子串 `cancelled` 时，系统应 判定为命中提醒条件。
2. 当 本次导入记录的 `invoice.status` 等于 `Financing confirmed` 且 `finance.status` 为 `Booking requested accepted` 或 `Loan booking failed` 时，系统应 同样判定为命中提醒条件（融资已确认但银行端预订异常）。
3. 在 命中提醒条件 下，当 该记录此前未命中（增量对比已存库状态）且未打过 `invoice.rejected_notified_at` 通知日期戳 时，系统应 记录为"新出现"，加入本次通知明细列表，并为该记录写入当次导入时间戳。
4. 当 该记录此前已打过通知日期戳 时，系统应 沿用原有日期戳（不因全量重导而重新触发提醒），确保同一发票只提醒一次。
5. 当 本次导入结束后"新出现"明细列表非空 时，系统应 汇总明细通过 `COMMON_EMAIL_URL`（n8n 通用邮件接口，JSON 入参 `{type:'common', title, body}`，无需 token）发送一封 HTML 表格通知邮件，明细含发票号、买方、卖方、金额币种、发票状态、融资状态、拒绝原因、创建时间、到期日。
6. 当 邮件发送失败 时，系统应 记录错误日志，但不影响本次导入的其余处理结果（导入仍按正常流程完成并返回统计）。

### REQ-IMPORT-007 从外部 API 导入数据

**用户故事**：作为运营人员，我希望无需下载 Excel 文件即可直接从上游系统 API 拉取融资单或还款单数据导入，以便实现自动化数据同步。

**验收标准**：

1. 当 用户在导入页面选择"从 API 导入"并指定类型为 `financing` 或 `repayment` 时，系统应 通过 HTTP GET 请求上游 n8n webhook（`exportFinancingOrders` / `exportRepaymentOrders`）获取 JSON 数据。
2. 当 API 返回数据 时，系统应 将其转换为 DataFrame 并复用与 Excel 导入相同的清洗与 upsert 导入逻辑。
3. 当 `import_type` 不是 `financing` 或 `repayment` 时，系统应 返回"不支持的API导入类型"错误。
4. 当 通过 `POST /api/import/from-api`（Token 鉴权）触发导入 时，系统应 支持 JSON body 或 form 两种传参方式读取 `import_type` 参数。

### REQ-IMPORT-008 批次号与还款日期辅助导入

**用户故事**：作为运营人员，我希望能够通过 Excel 单独回填融资单的批次号或 DB 还款日期，以便修正批次分配或补录还款结果。

**验收标准**：

1. 当 导入类型为 `batch_number` 时，系统应 按 `FR#` 匹配融资订单，将 `Loan submission Batch` 写入 `batch_number`，并同步设置 `batch_status='active'`、`is_batch=True`、`funded_before=True`、`bank_source='db'`、`batch_created_at`。
2. 当 导入类型为 `repayment_date` 时，系统应 按 `FR#` 匹配融资订单，解析 `Settle Date`（支持 `YYYYMMDD` 或标准日期字符串）并写入 `db_loan_settle_date`。
3. 当 某行 `FR#` 为空，或批次号/日期无法解析 时，系统应 将该行计入 `failed` 计数，不中断其余行的处理。

### REQ-IMPORT-009 Onboarding 配置定时增量同步

**用户故事**：作为系统管理员，我希望 Onboarding 配置数据能够每日自动从上游系统增量同步，以便无需每天手工导入 Excel。

**验收标准**：

1. 当 系统非测试环境启动且非 Flask reloader 子进程 时，系统应 通过 APScheduler 注册 `onboarding_sync` 定时任务，每日北京时间 02:00 自动执行。
2. 当 定时任务执行 时，系统应 调用 `exportRefactoringPairs` n8n API 拉取全量数据，读取 `refactoring_sync_meta` 中记录的上次同步时间 `last_sync_time`，过滤掉 `update_time <= last_sync_time` 的记录后按 `uid` upsert 写入 `refactoring_onboard_config`。
3. 当 本轮同步完成 时，系统应 更新 `refactoring_sync_meta` 记录本次同步开始时间及新增/更新/跳过统计。
4. 当 运营人员通过 `POST /maintenance/api/sync-onboarding` 手动触发同步 时，系统应 立即执行同一套同步逻辑并返回同步结果摘要。

## 4. 数据导出（REQ-EXPORT-xxx）

### REQ-EXPORT-001 通用数据导出

**用户故事**：作为运营人员，我希望将融资订单、还款订单、银行对账单或融资概览数据导出为 CSV/Excel/PDF 文件，以便进行离线分析或对外提交。

**验收标准**：

1. 当 用户在 `/export/generate` 提交数据类型（financing/repayment/statement/overview）和导出格式（csv/excel/pdf） 时，系统应 查询对应集合数据并生成相应格式文件供下载。
2. 当 用户指定 `finance_request_number`、`invoice_number` 或 `refactoring_status` 过滤条件 时，系统应 仅导出符合条件的记录。
3. 当 导出格式为 CSV 时，系统应 使用 `utf-8-sig` 编码以兼容 Excel 打开中文不乱码。
4. 当 导出格式为 Excel 时，系统应 使用 openpyxl 引擎生成文件并应用表头加粗、填充色、边框、自适应列宽样式。
5. 当 导出数据类型为 `overview`（融资概览） 时，系统应 先将嵌套文档结构按固定表头映射展开为扁平化的多列格式（包含 Seq. 序号及银行对账单/融资单相关重复列），再生成文件。
6. 当 查询结果为空 时，系统应 提示"没有找到符合条件的数据"，不生成空文件。

### REQ-EXPORT-002 DB 放款文件生成

**用户故事**：作为运营人员，我希望一键生成符合 DB 银行放款格式要求的批次文件，以便提交给银行处理放款。

**验收标准**：

1. 当 用户在 `/export/generate_db_loan_file` 提交批次日期 时，系统应 先刷新全部融资单后处理逻辑，再筛选 `can_push_to_db_today=True` 的融资订单。
2. 当 存在符合条件的融资订单 时，系统应 自动获取下一个批次号（现有 `active` 批次中的最大值 +1），并将这些订单的 `batch_number`、`batch_status='active'`、`batch_created_at`、`bank_source` 批量更新。
3. 当 生成放款文件 时，系统应 生成一个包含所有订单的汇总 Excel（含 FT 汇总行）和按供应商分组的独立 Excel（各自含 FT 汇总行），并打包为 ZIP 文件下载。
4. 当 没有符合条件的融资订单 时，系统应 提示"没有找到符合条件的数据"，不生成文件。

### REQ-EXPORT-003 DB 还款文件生成

**用户故事**：作为运营人员，我希望一键生成 DB 银行还款确认文件并同步记录还款批次，以便完成还款流程闭环。

**验收标准**：

1. 当 用户在 `/export/generate_db_repayment_file` 提交还款日期 时，系统应 先刷新全部融资单后处理逻辑，再筛选 `wip_pending>0` 且 `db_loan_settle_date` 为空且 `bank_finance_status='Loan booked'` 的融资订单。
2. 当 存在符合条件的融资订单 时，系统应 将这些订单的 `db_loan_settle_date` 更新为提交的还款日期。
3. 当 生成还款文件数据 时，系统应 关联 `refactoring_bank_statement`（按 `invoice.seller_reference`）补全发票日期、到期日、币种、原始金额，计算结算金额（`settled_in_air8='settled'` 取原始金额，否则为 `Pending for settlement`）。
4. 当 还款文件生成完成 时，系统应 将每条还款记录（含批次日期、银行渠道、供应商、发票号等）写入 `refactoring_bank_repayment_record` 集合，并生成汇总 Excel + 按供应商分组 Excel 打包为 ZIP 下载。

### REQ-EXPORT-004 融资单刷新与融资概览聚合触发

**用户故事**：作为运营人员，我希望能够手动触发融资单后处理刷新和融资概览聚合，以便在数据发生外部变更后及时更新展示结果。

**验收标准**：

1. 当 用户点击"刷新融资单"（`POST /export/refresh-financing-orders`） 时，系统应 对全部融资订单重新计算后处理衍生字段，并以 flash 消息提示结果。
2. 当 用户点击"更新融资概览"（`POST /export/update_overview`） 时，系统应 触发全量数据聚合并以 flash 消息提示更新记录数。

## 5. 数据聚合（REQ-AGG-xxx）

### REQ-AGG-001 全量融资概览聚合

**用户故事**：作为运营人员，我希望系统能够将融资订单、还款记录和银行对账单三个数据源自动关联汇总为融资概览，覆盖从审批中到放款结算的全部业务阶段，以便在仪表盘和导出中查看统一视图。

**验收标准**：

1. 当 触发全量聚合 时，系统应 处理 `refactoring_bank_statement` 中的全部记录（2026-08-20 起不再仅限 `finance.status='Loan booked'`，以便未放款阶段——如"Awaiting file approval"/"Booking requested"/"Booking requested accepted"——的银行对账单也能被聚合，覆盖完整状态流转）。
2. 当 提取唯一 `invoice.seller_reference` 后 时，系统应 批量查询关联的融资订单（按 `invoice_number` 匹配），再批量查询这些融资订单对应的还款记录（按 `finance_request_number` 匹配），以减少数据库往返次数。
3. 当 处理银行对账单 时，系统应 先按 `seller_reference` 分组，再使用线程池（`ThreadPoolExecutor`，最多 32 线程）并行处理每组，避免同一融资单的多条对账单被独立处理导致的写入竞态。
4. 当 同一融资申请号存在多条银行对账单 时，系统应 保留全部对账单于 `bank_statements[]` 数组，同时取按 `invoice.creation_time` 降序排序后的最新一条，用于派生 `refactoring_status`（取最新对账单的 `finance.status`）、`refactor_id`（取 `invoice.system_invoice_id`）、`refactor_portal_status`（取 `invoice.status`）、`refactor_settlement_status`（取 `settlement_status`）、`refactor_currency`、`refactor_amount`、`refactor_interest_rate_pct`、`refactor_interest_amount`、`refactor_purchase_price` 等顶层字段，以及金额汇总（`totals`，仅用最新一条计算，不对历史阶段性快照重复加总）。
5. 当 全部记录生成完成 时，系统应 使用 `bulk_write` + `UpdateOne(upsert=True)`（按 `finance_request_number`，每批最多 1000 个操作）批量写入 `refactoring_financing_overview`。
6. 当 没有银行对账单记录或没有关联到融资订单 时，系统应 直接返回当前 `refactoring_financing_overview` 集合的记录总数，不报错。

### REQ-AGG-002 单笔融资概览聚合

**用户故事**：作为运营人员，我希望能够针对单个融资申请号单独触发聚合，以便在个别数据变更后快速刷新而无需等待全量聚合，且行为与全量聚合逻辑保持一致。

**验收标准**：

1. 当 调用 `manual_aggregate(finance_request_number=...)` 且指定融资申请号 时，系统应 处理该融资申请号关联的全部银行对账单（不再限定 `finance.status='Loan booked'`），保留全部对账单于 `bank_statements[]`，并按 `invoice.creation_time` 取最新一条派生状态与金额字段，规则与 REQ-AGG-001 第 4 条一致。
2. 当 指定的融资申请号不存在对应融资订单 时，系统应 返回失败结果并说明"未找到融资申请号"。

### REQ-AGG-003 融资概览金额汇总计算

**用户故事**：作为财务人员，我希望融资概览中的金额字段使用高精度计算，以便避免因浮点误差导致对账偏差。

**验收标准**：

1. 当 计算融资概览的 `air8_finance_amt`、`air8_settled_fr_amt`、`finance_amount_usd`、`interest_amount_usd`、`outstanding_amount_usd`、`purchase_price_usd`、`settled_db_loan` 等汇总字段 时，系统应 使用 Python `Decimal` 进行精确计算，最终统一转换为 MongoDB `Decimal128` 类型存储。

## 6. 批次管理（REQ-BATCH-xxx）

### REQ-BATCH-001 批次列表查询

**用户故事**：作为运营人员，我希望查看所有已生成的放款批次及其状态，以便掌握批次处理进度。

**验收标准**：

1. 当 用户请求 `GET /api/batches` 时，系统应 按 `batch_number`（排除 0）分组统计每个批次的订单数量、状态、生成时间、银行来源，并按批次号降序返回。

### REQ-BATCH-002 批次详情查询

**用户故事**：作为运营人员，我希望查看指定批次下的具体融资订单明细，以便核对批次内容。

**验收标准**：

1. 当 用户请求 `GET /api/batches/<batch_number>` 时，系统应 返回该批次的状态、生成时间、银行来源及全部订单明细列表。
2. 当 指定批次号不存在 时，系统应 返回错误提示"批次号 X 不存在"。

### REQ-BATCH-003 批次作废

**用户故事**：作为运营人员，我希望能够作废已生成的批次，以便撤销错误的批次操作并让相关融资单恢复到可重新处理的状态。

**验收标准**：

1. 当 用户请求 `PUT /api/batches/<batch_number>/cancel` 时，系统应 将该批次下所有融资订单的 `batch_number` 重置为 0，`batch_status` 清空，`batch_created_at` 清空。
2. 当 批次作废字段更新完成 时，系统应 自动触发一次全量数据聚合以刷新融资概览。
3. 当 指定批次号在系统中不存在 时，系统应 返回失败结果，不执行任何更新。

### REQ-BATCH-004 按融资申请号查询批次

**用户故事**：作为运营人员，我希望通过融资申请号快速查到其所属批次，以便定位具体订单的放款批次归属。

**验收标准**：

1. 当 用户请求 `GET /api/batches/by-fr/<fr_number>` 时，系统应 返回该融资申请号对应的批次号、批次状态、生成时间和银行来源。

### REQ-BATCH-005 批次状态统计

**用户故事**：作为运营人员，我希望查看各批次状态的记录数量分布，以便了解批次处理的整体情况。

**验收标准**：

1. 当 用户请求 `GET /api/batches/status-count` 时，系统应 按 `batch_status` 分组统计各状态下的融资订单数量（仅统计有批次号的记录）。

### REQ-BATCH-006 还款批次管理

**用户故事**：作为运营人员，我希望查看和管理已生成的 DB 还款批次，以便在批次数据有误时撤销并重新生成。

**验收标准**：

1. 当 用户访问 `/maintenance/repayment_batches` 时，系统应 按 `batch_date` 分组展示所有还款批次的银行渠道、状态和记录数。
2. 当 用户访问 `/maintenance/repayment_batches/<batch_date>/detail` 时，系统应 展示该批次下的全部还款明细记录（按 `seller_name` 排序）。
3. 当 用户提交 `POST /maintenance/repayment_batches/void/<batch_date>` 作废指定批次 时，系统应 删除 `refactoring_bank_repayment_record` 中该批次的全部记录，并清除相关融资订单的 `db_loan_settle_date` 字段（`$unset`）。
4. 当 指定的还款批次不存在 时，系统应 提示"还款批次不存在"，不执行删除操作。

## 7. 仪表盘（REQ-DASH-xxx）

### REQ-DASH-001 核心数据统计卡片

**用户故事**：作为业务管理人员，我希望登录后第一眼看到系统核心数据量，以便快速掌握业务规模。

**验收标准**：

1. 当 用户访问 `/dashboard` 时，系统应 展示融资订单数、还款记录数、银行对账单数、融资概览记录数四张统计卡片（分别统计对应集合的文档总数）。

### REQ-DASH-002 Settlement Schedule 报表

**用户故事**：作为财务人员，我希望按到期日查看结算计划汇总，以便安排资金和还款计划。

**验收标准**：

1. 当 用户访问仪表盘或调用 `GET /api/get_settlement_schedule` 时，系统应 从 `refactoring_financing_overview` 按 `order_details.due_date` 分组，汇总 DB 放款金额、买方还款、DB 未结金额、Air8 已结算金额，并按日期升序排序。
2. 当 请求携带 `filter_zero=true` 参数 时，系统应 过滤掉未结金额（`os_amt_in_db`）为零的记录。

### REQ-DASH-003 DB Disbursement 报表

**用户故事**：作为财务人员，我希望按批次号查看 DB 放款汇总数据，以便核对每批放款的融资、利息和购买价格总额。

**验收标准**：

1. 当 用户访问仪表盘或调用 `GET /api/get_db_disbursement` 时，系统应 从 `refactoring_financing_overview` 按 `loan_submission_batch` 分组，汇总融资金额、利息金额（USD）、购买价格（USD），并按批次号排序展示。

### REQ-DASH-004 融资单统计图表

**用户故事**：作为业务管理人员，我希望查看按月份统计的有对账单融资单数量和逾期趋势，以便识别业务波动和风险信号。

**验收标准**：

1. 当 用户调用 `GET /api/get_monthly_financing_with_statement_stats` 时，系统应 按月统计已关联银行对账单的融资单数量，支持通过 `supplier` 参数按供应商过滤。
2. 当 仪表盘渲染统计图表 时，系统应 使用 Chart.js 展示数据分布饼图，并支持随主题切换在暗色/亮色模式下正确显示。

## 8. 数据维护（REQ-MAINT-xxx）

### REQ-MAINT-001 数据概览页面

**用户故事**：作为运营人员，我希望在一个页面看到所有核心集合及批次的记录数概况，以便快速定位需要维护的数据。

**验收标准**：

1. 当 用户访问 `/maintenance/` 时，系统应 展示 Onboarding 配置、融资订单、还款订单、银行对账单、融资概览的记录数，以及融资批次数、还款批次数统计。

### REQ-MAINT-002 集合数据分页查看

**用户故事**：作为运营人员，我希望分页浏览指定集合的原始数据，以便核查具体记录内容。

**验收标准**：

1. 当 用户访问 `/maintenance/table/<table_name>`（`table_name` 取值限定为 `onboarding`/`financing`/`repayment`/`statement`/`overview` 白名单） 时，系统应 按 10 条/页分页展示对应集合数据，并将 `Decimal128` 字段递归转换为 `float` 便于展示。
2. 当 `table_name` 不在白名单内 时，系统应 提示"无效的表名"并重定向到数据概览页面。

### REQ-MAINT-003 文档编辑

**用户故事**：作为运营人员，我希望能够直接在维护界面修正错误的字段值，以便快速纠正数据问题而无需重新导入整份 Excel。

**验收标准**：

1. 当 用户提交 `POST /maintenance/edit/<table_name>/<doc_id>` 时，系统应 按表单字段更新对应文档，`onboarding`/`financing` 表的整型字段（如 `approved_tenor_days`、`expected_tenor`）会被强制转换为整数，且不允许覆盖 `created_at`，并刷新 `updated_at`。
2. 当 指定文档不存在 时，系统应 提示"文档不存在"并重定向回列表页面。

### REQ-MAINT-004 文档新增

**用户故事**：作为运营人员，我希望能够手动补录一条缺失的业务记录，以便处理批量导入未覆盖的个别场景。

**验收标准**：

1. 当 用户提交 `POST /maintenance/add/<table_name>` 时，系统应 将表单数据写入对应集合，自动补充 `created_at`/`updated_at` 时间戳。

### REQ-MAINT-005 文档删除

**用户故事**：作为运营人员，我希望能够删除错误录入的记录，以便保持数据集合的准确性。

**验收标准**：

1. 当 用户访问 `/maintenance/delete/<table_name>/<doc_id>` 时，系统应 删除该文档并以 flash 消息提示删除结果（成功/失败）。

### REQ-MAINT-006 融资批次页面查看

**用户故事**：作为运营人员，我希望在维护模块内查看融资批次列表及批次内订单明细，以便与批次管理 API 数据交叉核对。

**验收标准**：

1. 当 用户访问 `/maintenance/batches` 时，系统应 展示融资批次列表页面。
2. 当 用户访问 `/maintenance/batches/<batch_number>` 时，系统应 分页（20 条/页）展示该批次下的融资订单明细，按到期日降序排序。

### REQ-MAINT-007 再保理融资单列表查询与导出

**用户故事**：作为运营人员，我希望在维护模块中按多条件筛选再保理融资单数据并导出，以便针对性核查特定批次或状态的数据。

**验收标准**：

1. 当 用户访问 `/maintenance/financing-overview` 并提交融资申请号、发票号、再保理状态、买方名称、卖方名称、Air8结算状态、银行再保理编号（`refactor_id`）等过滤条件 时，系统应 组合成 MongoDB 查询条件（模糊匹配使用 `$regex`），分页（20 条/页）展示结果，并提供各过滤维度的可选值下拉列表。
2. 当 用户查看该列表 时，系统应 按顺序展示 26 列：资金方、融资申请号、买方、卖方、发票号、币种、发票金额、利率%、帐期（含收款期）、融资金额、利息、发票到期日、Air8结算状态、再保理货币、再报理金额、再保理利率、再保理利息、再保理利息（逾期，本次不接数据源固定为空）、净再保理金额、再保理平台状态、再保理状态、再保理结算状态、银行再保理编号、再保理成熟日、DB还款日、系统更新时间；不再展示"汇总状态"与"批次号"列（数据库字段保留，仅列表隐藏）。
3. 当 中文界面查看菜单与页面标题 时，系统应 显示"再保理融资单列表"；英文界面应显示"Refactoring Financing List"。
4. 当 用户提交 `POST /maintenance/financing-overview/export` 时，系统应 按当前过滤条件导出对应的融资概览 Excel 文件。

### REQ-MAINT-008 Onboarding 配置手动同步

**用户故事**：作为运营人员，我希望在需要时立即触发一次 Onboarding 数据同步，而不必等待每日定时任务，以便加快紧急数据更新。

**验收标准**：

1. 当 用户提交 `POST /maintenance/api/sync-onboarding` 时，系统应 立即执行与每日定时任务相同的增量同步逻辑，并返回新增/更新/跳过的统计结果。

## 9. 工具集（REQ-TOOLS-xxx）

### REQ-TOOLS-001 工具首页

**用户故事**：作为系统用户，我希望有一个统一入口浏览所有可用的辅助工具，以便快速找到需要的功能。

**验收标准**：

1. 当 用户访问 `/tools/` 时，系统应 以卡片网格形式展示所有已实现的工具（发票文件下载、创建 Dummy 发票等），每张卡片含图标、标题、描述和进入按钮。

### REQ-TOOLS-002 发票文件批量下载

**用户故事**：作为运营人员，我希望输入一批融资编号后自动下载对应的发票文件并打包为 ZIP，以便无需逐条到上游系统下载附件。

**验收标准**：

1. 当 用户在 `/tools/invoice-download` 提交融资编号列表（每行一个） 时，系统应 按 50 个一批调用外部 API（`https://n8n.air8.cn/webhook/downloadInvoiceFiles`），多批次时使用线程池并行调用（最多 10 并发）。
2. 当 输入为空 时，系统应 提示"请输入至少一个融资编号"，不发起 API 调用。
3. 当 获取到文件下载链接列表 时，系统应 使用线程池（最多 10 并发）并行下载所有文件。
4. 当 按 `invoice_no + financing_no` 分组后仅有一组 时，系统应 将文件直接打包进外层 ZIP；当有多组 时，系统应 为每组生成一个内层子 ZIP 再打包进外层 ZIP。
5. 当 API 未返回任何结果 时，系统应 提示"未找到任何发票文件"。
6. 当 文件名从响应头 `Content-Disposition` 无法提取 时，系统应 退化为从下载 URL 路径解析文件名，仍失败则使用默认名 `file`；文件名中的非法字符（`\/:*?"<>|`）应被替换为下划线。

### REQ-TOOLS-003 创建 Dummy 发票

**用户故事**：作为测试/演示人员，我希望输入买方代码、供应商代码和金额即可快速创建一张测试发票，以便进行系统联调或演示，无需真实业务数据。

**验收标准**：

1. 当 用户在 `/tools/create-dummy-invoice` 提交买方代码、供应商代码、金额 时，系统应 校验三个字段均非空且金额可解析为数字，通过后调用外部 API（`https://n8n.air8.cn/webhook/CreateDummyInvoice`）。
2. 当 任一必填字段为空 时，系统应 返回"请填写所有必填字段"错误，不调用外部 API。
3. 当 金额无法转换为浮点数 时，系统应 返回"金额必须是有效的数字"错误。
4. 当 外部 API 调用成功 时，系统应 以 AJAX 方式将返回的发票信息 JSON 直接展示在页面上，不触发文件下载。
5. 当 外部 API 调用失败或超时 时，系统应 返回"调用API失败，请稍后重试"错误提示。

## 10. FCB 模块（REQ-FCB-xxx）

### REQ-FCB-001 FCB 客户维护（CRUD）

**用户故事**：作为运营人员，我希望维护 FCB 客户档案（客户编号、地址、条款代码等），以便交易数据导出时能正确匹配客户信息生成标准 Excel。

**验收标准**：

1. 当 用户访问 `/fcb/clients` 页面并调用 `GET /fcb/api/clients` 时，系统应 支持关键词搜索（匹配 `supplier_code`/`customer_name`/`client_number`，大小写不敏感）及分页（默认每页 20 条），按创建时间倒序返回。
2. 当 用户提交 `POST /fcb/api/clients` 创建客户且 `supplier_code` 为空 时，系统应 拒绝创建并返回 400 错误。
3. 当 提交的 `(supplier_code, buyer_air8_code)`（`buyer_air8_code` 非空时）或 `(supplier_code, customer_name)`（`buyer_air8_code` 为空时）组合已存在 时，系统应 拒绝创建/更新并返回 409 冲突错误。
4. 当 用户提交 `PUT /fcb/api/clients/<client_id>` 更新客户 时，系统应 按 `_id` 定位并更新字段（不允许覆盖 `_id`），执行与创建相同的组合查重校验，刷新 `updated_at`；客户不存在时返回 404，查重冲突时返回 409。
5. 当 用户提交 `DELETE /fcb/api/clients/<client_id>` 时，系统应 删除对应客户记录；不存在时返回 404。

### REQ-FCB-002 FCB 交易数据导出

**用户故事**：作为运营人员，我希望输入一批融资编号即可生成符合 FCB 系统要求的标准 24 列 Excel 交易文件，以便提交给 FCB 客户系统对账。

**验收标准**：

1. 当 用户在 `/fcb/export` 页面提交融资编号列表并调用 `POST /fcb/api/export` 时，系统应 调用 n8n API（`exportFcbRefactoringInvoices`）获取交易数据，解析响应中嵌套的 JSON 字符串。
2. 当 融资编号列表为空 时，系统应 返回 400 错误"Please provide financing numbers"。
3. 当 交易数据按 `supplier_code` 分组并查出候选客户记录（同一 `supplier_code` 下可能有多条，按 buyer 区分）后，若某候选记录填写了 `buyer_air8_code`，系统应 仅用其与交易的 `buyer_code` 精确比较判定是否命中；若候选记录未填写 `buyer_air8_code`，系统应 用其 `customer_name` 与交易的 `buyer_name`（均去首尾空格、忽略大小写）比较判定是否命中。
4. 当 某笔交易未匹配到任何候选客户，或匹配到多条候选客户（歧义） 时，系统应 将该笔交易计入未匹配列表并跳过，不中断本次导出其余交易的处理；当本次导出涉及的全部交易均未匹配 时，系统应 抛出错误并列出未匹配详情。
5. 当 导出结果中存在多个不同客户记录（含同一 `supplier_code` 下不同 buyer 的情况） 时，系统应 按命中的客户记录（而非仅 `supplier_code`）分组生成 Excel，返回单个 `.xlsx` 或打包为 ZIP。
6. 当 生成 Excel 时，系统应 按固定 24 列顺序（Client Number、Customer Name、Invoice Number 等）合并客户档案字段与交易字段，其中 `Invoice Number` 列需去除连字符。

### REQ-FCB-003 FCB 每日定时推送

**用户故事**：作为业务负责人，我希望系统每天自动生成当日 FCB 交易 Excel 并连同发票附件通过邮件发送给 FCB 客户，以便无需人工每日操作。

**验收标准**：

1. 当 系统非测试环境启动 时，系统应 通过 APScheduler 注册每日北京时间 06:00 的定时任务。
2. 当 定时任务执行 时，系统应 依次执行：调用 `exportFcbRefactoringInvoicesDaily` API 获取当日融资编号列表 → 复用 FCB 导出逻辑生成 Excel → 复用 Tools 模块的发票下载逻辑下载附件并打包 ZIP → 通过 `POST multipart/form-data` 调用 `commonSendEmailForRefactoring` 邮件接口发送。
3. 当 某一步骤执行失败 时，系统应 独立捕获异常并记录日志，不影响后续步骤的尝试执行。
4. 当 外部 API 调用超时 时，系统应 使用 120 秒超时限制。

### REQ-FCB-004 FCB 每日推送手动触发

**用户故事**：作为运营人员，我希望能够手动立即触发一次 FCB 每日推送，以便在定时任务失败或需要补发时快速重试。

**验收标准**：

1. 当 用户提交 `POST /fcb/api/trigger-daily-export` 时，系统应 立即执行与定时任务相同的推送流程，成功返回 200，失败返回 500 及错误信息。

## 11. 额度管理（REQ-CREDIT-xxx）

### REQ-CREDIT-001 额度查询（买方层汇总）

**用户故事**：作为风控/财务人员，我希望按买方（Obligor）维度查看额度上限、预占、实占、可用余量的汇总，以便快速判断该买方整体授信敞口是否接近或超过 DB 核准额度。

**验收标准**：

1. 当 用户访问 `/credit/credit-query` 时，系统应 按买方（`buyer_code`）汇总展示：Obligor 名称、Air8 Buyer ID（`buyer_code`）、币种（固定展示 `USD`）、Celling（额度上限）、预占（Earmark Forecast）、实占（Credit Utilization）、总额/Total Occupied（Total O/S = 预占 + 实占 − 待结清，计算细节见 AC3/AC4；待结清为空时按 0 参与计算）、Headroom（可用余量 = Celling − 总额）、占用率（总额 / Celling）。
2. 当 计算某买方的 Celling 时，系统应 汇总该买方下全部买卖方配对（`uid`）在 `refactoring_onboard_config.refactoring_limit` 中的值，包含 `target_list_status='N'`（尚未提交名单）的配对。
3. 当 计算某买方的预占（Earmark Forecast）时，系统应 对该买方下全部买卖方配对（uid）名下的每笔 `refactoring_financing_order` 按统一的 Deal 层口径逐笔计算并求和：先按 `invoice_number == refactoring_bank_statement.invoice.seller_reference` 匹配对账单（**不限定** `finance.status` 取值），匹配到时取 Financing Amount = `invoice.original_amount × finance.advance_ratio_pct ÷ 100`（若匹配到的对账单缺少 `finance.advance_ratio_pct`，该笔 Financing Amount 为 0，不回退；此情况系统应记录一条 `WARNING` 级别日志，说明具体 `invoice_number` 及取到的 `advance_ratio_pct` 值，便于运营人员排查银行对账单数据缺失）；未匹配到任何对账单时，回退取 `refactoring_financing_order.financing_amount`。计算出 Financing Amount 后，该笔同时满足 `status='eligible'` 且 `bank_finance_status != 'Loan booked'` 时，取该 Financing Amount 计入预占，否则该笔预占为 0。不使用 `funded_before` 字段判定（`funded_before` 一旦为 `True` 即不再回退，即使对应银行对账单后续状态已变为非 `Loan booked`，据此判定会将已完成放款流程的融资单按原始金额重复计入预占）。
4. 当 计算某买方的实占（Credit Utilization）、待结清（To Be Settled on DB）与总额（Total O/S）时，系统应：**实占**——对该买方下全部融资单，在其满足 `bank_finance_status='Loan booked'` 时取 AC3 所述同一 Financing Amount 计入实占（否则该笔实占为 0）并逐笔求和；不再统一乘以固定比例 90%（原 `_ACTUAL_OUTSTANDING_RATIO` 硬编码比例已废弃），因为 Financing Amount 本身已经通过对账单的 `finance.advance_ratio_pct`（银行侧真实融资成数）折算，无需再额外打折；**待结清**——对同时满足 `settled_in_air8='Settled'`（Air8 侧已结清）、`bank_finance_status='Loan booked'`（DB 放款状态尚未变化）且该笔关联对账单的 `invoice.settlement_status`（DB 自身的结清状态字段，未匹配到对账单时视为空，同样满足"不等于 Settled"）不等于 `'Settled'`（DB 结清状态字段本身也确认尚未结清，避免仅凭 `bank_finance_status` 停留在 `Loan booked` 误判）的融资单，按其 `finance_request_number` 查询 `refactoring_bank_repayment_record`（若存在多条取 `created_at` 最新一条）取其 `settlement_amount` 字段；该字段不是数值（如字符串 `'Pending for settlement'`）或未查到匹配记录时，该笔待结清为空并按 0 参与求和/Total O/S 计算；不满足前述中间态条件的融资单待结清同样为空（不是 0，但求和时按 0 处理）；**总额/Total O/S**——按 `预占 + 实占 − 待结清` 对该买方下全部融资单求和得到。
5. 当 某买方的 Celling 为 0 或不存在对应 onboard 配置 时，系统应 将占用率标记为不可计算（展示为 N/A），并在页面上视为风险状态高亮。
6. 当 用户提交 `buyer_name` 过滤参数 时，系统应 按大小写不敏感的模糊匹配过滤买方名称后再聚合。
7. 当 某买方的占用率超过预警阈值（默认 90%，见 REQ-CREDIT-004） 时，系统应 在列表中高亮该行。
8. 当 聚合过程中发生异常 时，系统应 捕获异常并在页面展示错误信息，不导致页面崩溃。

买卖方配对全集 = `refactoring_onboard_config` 全部 `uid` 并集 `refactoring_financing_order` 中出现的全部 `uid`（全外连接），任一侧存在即纳入统计，缺失侧对应指标记为 0。本期所有指标均按 USD 统一展示，不做汇率换算；额度计算全部为实时查询聚合，不新增持久化集合存储计算结果。

### REQ-CREDIT-002 额度查询明细钻取（供应商层 + FR 明细）

**用户故事**：作为风控/财务人员，我希望点击某个买方即可展开其下所有供应商配对的额度明细，并能继续钻取到具体融资单（FR No）明细，以便核实买方层汇总数字的构成。

**验收标准**：

1. 当 用户在买方层列表点击展开某买方 时，系统应 展示该买方下每个买卖方配对（uid）的：Supplier 名称、Air8 Seller ID（`supplier_code`）、币种（`USD`）、Celling、预占（Earmark Forecast）、实占（Credit Utilization）、总额/Total O/S、Headroom、占用率，计算口径与 REQ-CREDIT-001 AC2~AC4 相同（对该 uid 下全部 Deal 层结果求和），但不做买方层汇总（单配对粒度）。
2. 当 供应商层某配对占用率超过预警阈值 时，系统应 高亮该行。
3. 当 用户在供应商层点击某配对的明细入口 时，系统应 跳转至 `/credit/detail`，展示该买卖方配对下的 Deal（单笔融资单）层明细列表与合计行，详见 REQ-CREDIT-005。

### REQ-CREDIT-003 额度数据导出（买方/买卖方/Deal 三个固定 Sheet）

**用户故事**：作为运营人员，我希望将当前额度视图导出为 Excel，且导出的 Excel 有固定的买方、买卖方、Deal 三个 sheet 并各自带合计行，以便离线核对不同颗粒度的数字。

**验收标准**：

1. 当 用户在额度查询页面点击导出并调用 `POST /credit/export` 时，系统应 生成一个包含固定 3 个 sheet 的 Excel：`Buyer`（买方层汇总，一行一个买方，字段与 REQ-CREDIT-001 AC1 一致）、`Buyer-Supplier`（买卖方层，一行一个配对，平铺展示，不再按买方拆分为多个 sheet，字段与 REQ-CREDIT-002 AC1 一致）、`Deal`（Deal 层，一行一笔融资单，字段为 FR#、发票号、买方名称、供应商名称、Financing Amount、Earmark Forecast、Credit Utilization、To Be Settled on DB、Total O/S、Status、Finance Details - Finance Status、Invoice Details - Settlement Status、到期日、放款日、批次号）。
2. 当 生成 `Buyer`/`Buyer-Supplier` sheet 时，系统应 在该 sheet 最后追加一行 `Total`，对 Celling/预占/实占/Total Occupied 四列求和，并重新计算 Headroom（= Celling 总和 − Total Occupied 总和）与占用率（= Total Occupied 总和 / Celling 总和，Celling 总和为 0 时两者均展示 `N/A`）；当 生成 `Deal` sheet 时，系统应 在最后追加一行 `Total`，对 Financing Amount/Earmark Forecast/Credit Utilization/To Be Settled on DB/Total O/S 五列求和；三个 sheet 的非数值列（名称、状态等）在 Total 行留空或展示 `Total` 字样。
3. 当 导出时页面存在 `buyer_name` 过滤条件 时，系统应 仅导出过滤后的买方及其下属买卖方配对、Deal（与 `GET /credit/credit-query` 当前查询范围一致）。
4. 当 生成的工作簿为空（无任何买方数据） 时，系统应 提示"没有找到符合条件的数据"，不生成空文件。

### REQ-CREDIT-004 每日额度预警

**用户故事**：作为业务负责人，我希望系统每天自动检查各买卖方配对及买方层的额度占用情况，超过阈值时通过邮件提醒相关人员，以便及时跟进降额或补充授信。

**验收标准**：

1. 当 系统非测试环境启动 时，系统应 通过 APScheduler 注册每日北京时间 07:00 的定时任务（避开 02:00 Onboarding 同步与 06:00 FCB 每日推送）。
2. 当 定时任务执行 时，系统应 复用 REQ-CREDIT-001/002 的实时聚合逻辑，分别计算买方层与买卖方配对层的占用率。
3. 当 存在占用率超过阈值（默认 90%，硬编码于 `backend/app/config.py` 的 `CREDIT_WARNING_THRESHOLD`，本期不提供 UI 配置） 的买方或配对 时，系统应 汇总明细（买方/配对名称、Celling、预占、实占、总额、Headroom、占用率）通过 `COMMON_EMAIL_URL` 发送一封 HTML 表格通知邮件（JSON 入参 `{type:'common', title, body}`），收件人由 n8n 侧管理，系统不传收件人列表。
4. 当 不存在超阈值项 时，系统应 跳过发送，不产生空邮件。
5. 当 邮件发送失败 时，系统应 记录错误日志，不影响定时任务其余流程及下次调度。
6. 当 用户提交 `POST /credit/api/trigger-warning-check` 时，系统应 立即执行同一套预警检查逻辑并返回本次检查结果摘要（`checked_buyers`、`checked_pairs`、`warned_count`、`email_sent`）。

### REQ-CREDIT-005 额度明细页（`/credit/detail`）重做

**用户故事**：作为风控/财务人员，我希望在额度明细页看到每笔融资单的预占/实占/待结清拆分、银行侧真实状态字段，以及本页汇总的合计行，以便核实某个买卖方配对的额度占用是如何由具体单据构成的。

**验收标准**：

1. 当 用户访问 `/credit/detail` 时，系统应 按 `buyer_name`+`supplier_name`+`financing_currency` 精确匹配取出该配对下**全部**符合条件的 `refactoring_financing_order`，逐笔计算 Deal 层数据（REQ-CREDIT-001 AC3/AC4 口径）后按 `due_date` 降序排列，再在内存中按 20 条/页分页展示（分页大小、排序字段、过滤参数不变）；每行展示：FR#、发票号、Financing Amount、Earmark Forecast（预占）、Credit Utilization（实占）、To Be Settled on DB（待结清，为空时展示 `N/A`）、Total O/S、Status（业务状态原始值为 `funded before` 时展示为 `Funded Successfully`，其余状态原样展示，不改变存储值）、Finance Details - Finance Status（匹配到的对账单 `finance.status` 原始值，未匹配到对账单时为空）、Invoice Details - Settlement Status（匹配到的对账单 `invoice.settlement_status` 原始值，未匹配到对账单时为空）、到期日、放款日（`actual_funding_date`）、批次号。
2. 当 页面渲染表格 时，系统应 在表格末尾新增一行合计（Total），对 Financing Amount、Earmark Forecast、Credit Utilization、To Be Settled on DB、Total O/S 五列求和；合计范围为该买卖方配对下**全部**符合过滤条件的记录，不受当前页分页影响。
3. 当 聚合/查询过程中发生异常 时，系统应 捕获异常并在页面展示错误信息，不导致页面崩溃。

### REQ-CREDIT-006 额度明细页导出

**用户故事**：作为运营人员，我希望在额度明细页也能导出当前买卖方配对下的全部 Deal 明细，以便针对单个配对做离线核对。

**验收标准**：

1. 当 用户在 `/credit/detail` 页面点击导出并调用 `POST /credit/detail/export` 时，系统应 以与 `GET /credit/detail` 相同的 `buyer_name`/`supplier_name`/`currency` 过滤条件（从表单读取）生成一个 Excel，包含该买卖方配对下**全部**符合条件的 Deal 记录（不受分页限制），列与 REQ-CREDIT-005 AC1 的页面列一致，末尾追加与 REQ-CREDIT-005 AC2 口径一致的合计行。
2. 当 导出结果为空 时，系统应 提示"没有找到符合条件的数据"，不生成文件。

## 12. 对外 API（REQ-API-xxx）

### REQ-API-001 Token 鉴权机制

**用户故事**：作为对外系统集成方，我希望通过固定 Token 完成 API 鉴权，以便安全地拉取本系统数据。

**验收标准**：

1. 当 请求 `/api/*` 下任一受保护端点 时，系统应 从请求头 `X-API-Token` 或查询参数 `token` 中读取令牌，与配置的 `API_TOKEN` 比对。
2. 当 令牌缺失或不匹配 时，系统应 返回 401 状态码及 `{'success': False, 'message': 'Unauthorized'}`。

### REQ-API-002 查询 WIP Pending 融资单

**用户故事**：作为对外系统集成方，我希望拉取所有存在未结金额的融资单，以便在下游系统同步展示。

**验收标准**：

1. 当 请求 `GET /api/financing/wip-pending` 且鉴权通过 时，系统应 返回全部 `wip_pending > 0` 的融资单指定字段集合，按到期日升序排序，并将 `Decimal128`/日期类型转换为 JSON 可序列化格式。

### REQ-API-003 查询 Onboarding 配置

**用户故事**：作为对外系统集成方，我希望拉取全部或仅活跃状态的 Onboarding 配置数据，以便与本系统的客户名单保持一致。

**验收标准**：

1. 当 请求 `GET /api/onboard-config` 且鉴权通过 时，系统应 返回 `refactoring_onboard_config` 集合全部记录的指定字段。
2. 当 请求 `GET /api/onboard-config/active` 且鉴权通过 时，系统应 仅返回 `target_list_status='Y'` 的记录。

### REQ-API-004 触发融资单刷新（对外）

**用户故事**：作为对外系统集成方，我希望能够通过 API 触发本系统重新计算融资单衍生字段，以便在上游数据变更后同步刷新。

**验收标准**：

1. 当 请求 `POST /api/financing/refresh` 且鉴权通过 时，系统应 触发与导出页面"刷新融资单"按钮相同的全量后处理逻辑，成功返回 200，失败返回 500。

### REQ-API-005 从外部 API 触发数据导入（对外）

**用户故事**：作为对外系统集成方，我希望能够通过 API 触发本系统从上游拉取融资单或还款单数据，以便实现系统间自动化联动。

**验收标准**：

1. 当 请求 `POST /api/import/from-api` 且鉴权通过、并提供 `import_type`（`repayment` 或 `financing`） 时，系统应 触发对应的 API 导入流程并返回导入统计结果。
2. 当 未提供 `import_type` 参数 时，系统应 返回 400 错误，提示需提供该参数。

### REQ-API-006 查询银行对账单（对外）

**用户故事**：作为对外系统集成方，我希望分页查询银行对账单数据（含结清状态/日期），以便在下游系统展示发票结清进度。

**验收标准**：

1. 当 请求 `POST /api/bank-statement` 且鉴权通过 时，系统应 支持按 `invoice_ids` 列表（匹配 `invoice.system_invoice_id`）、`buyer`（精确匹配 `parties.buyer_name`）、`supplier`（精确匹配 `parties.seller_name`）过滤，支持 `pageNum`/`pageSize`（默认 1/200，最大 5000）分页。
2. 当 返回的每条记录序列化 时，系统应 将嵌套的 `parties`/`invoice`/`finance`/`usd_details` 结构扁平化为单层字段，其中 `settlement_status` 输出银行原始结清状态，`settlement_date` 按 REQ-IMPORT-005 规则优先输出 `raw_settlement_date`。
3. 当 `pageNum`/`pageSize` 参数无法解析为整数 时，系统应 返回 400 错误。

## 13. 国际化与通用（REQ-COMMON-xxx）

### REQ-COMMON-001 多语言支持

**用户故事**：作为国际化团队成员，我希望系统界面支持中英文切换，以便不同语言背景的用户都能正常使用。

**验收标准**：

1. 当 用户访问 `/set_language/<language>` 或调用 `POST /api/switch_language` 时，系统应 将语言代码标准化（`zh`/`zh-cn`/`zh_cn` → `zh_CN`；`en`/`en-us`/`en_us` → `en_US`）后写入 `language` Cookie（有效期 30 天）。
2. 当 请求携带 `?lang=` 查询参数 时，系统应 优先使用该参数确定当前语言；否则读取 `language` Cookie；两者都缺失时默认使用 `zh_CN`。
3. 当 页面渲染文本 时，系统应 通过自定义 JSON 翻译加载器（覆盖 Flask-Babel 默认机制）从 `backend/app/i18n/<locale>.json` 加载翻译，键使用点号分隔（如 `common.title.dashboard`）。

### REQ-COMMON-002 主题切换

**用户故事**：作为系统用户，我希望能够在浅色和深色主题间切换，以便在不同使用环境下获得舒适的视觉体验。

**验收标准**：

1. 当 用户在导航栏选择"浅色"或"深色"主题 时，系统应 通过前端脚本（`theme.js`）应用对应样式（`theme.css`）并持久化偏好（Cookie）。
2. 当 页面重新加载 时，系统应 读取已保存的主题偏好并应用，默认使用浅色主题。

### REQ-COMMON-003 登录保护横切要求

**用户故事**：作为系统安全负责人，我希望除认证入口和对外 Token API 外的所有页面和内部接口都强制要求登录，以便防止未授权访问业务数据。

**验收标准**：

1. 当 任一未标注 `@login_required` 豁免（`/auth/login`、`/auth/register`、`/auth/logout`、`/api/*` 对外端点除外）的路由被未登录用户访问 时，系统应 拒绝直接访问并重定向到登录页。
2. 当 `/api/*` 前缀下的对外端点被访问 时，系统应 使用固定 Token 鉴权（`require_token` 装饰器）而非登录会话鉴权。

## 14. 非功能需求（REQ-NFR-xxx）

### REQ-NFR-001 文件上传限制

**用户故事**：作为系统管理员，我希望限制上传文件的大小和类型，以便防止超大文件或非法格式文件影响系统稳定性。

**验收标准**：

1. 当 上传文件大小超过 16MB（`MAX_CONTENT_LENGTH`） 时，系统应 拒绝该请求。
2. 当 上传文件扩展名不属于 `{'xlsx', 'xls'}`（`ALLOWED_EXTENSIONS`） 时，系统应 拒绝导入并提示格式错误。

### REQ-NFR-002 幂等导入保证

**用户故事**：作为运营人员，我希望重复导入同一份数据不会产生重复记录或丢失既有关联字段，以便安全地进行重复上传或修正性重传。

**验收标准**：

1. 当 任一数据类型（Onboarding/融资单/还款单/银行对账单/融资概览）按其业务主键重复导入 时，系统应 更新已有记录而非插入新记录，且保留原有 `_id` 与 `created_at`。
2. 当 融资订单更新导入且已有有效批次（`batch_number>0` 且 `batch_status='active'`） 时，系统应 保留原批次相关字段不被覆盖为默认值。

### REQ-NFR-003 外部 API 调用容错

**用户故事**：作为系统运维人员，我希望所有外部 n8n API 调用具备超时保护和错误处理，以便单次外部依赖故障不会导致整个请求或后台任务失控挂起。

**验收标准**：

1. 当 系统调用任一 n8n webhook（发票下载、Dummy 发票创建、FCB 交易查询、Onboarding 同步、邮件通知等） 时，系统应 设置明确的超时时间（30~120 秒不等，视接口而定）。
2. 当 外部 API 调用抛出 `requests.RequestException` 时，系统应 捕获异常并记录日志，向用户返回友好错误提示，不使未捕获异常导致 500 页面崩溃（用户可见路由均包裹 try/except）。
3. 当 定时任务（FCB 每日推送、Onboarding 每日同步）中的某个步骤失败 时，系统应 记录日志并继续/结束当次任务，不影响下一次调度周期的正常触发。

### REQ-NFR-004 日志记录

**用户故事**：作为系统运维人员，我希望关键业务操作（导入、聚合、定时任务）留有详细日志，以便排查数据异常和故障定位。

**验收标准**：

1. 当 执行 Excel 导入、银行对账单清洗与写入、数据聚合、定时任务 时，系统应 记录包含文件名/行数/耗时关键节点、成功计数、失败计数的日志（`import_service.log` 及标准输出）。
2. 当 数据聚合或后处理过程中发生异常 时，系统应 记录完整异常堆栈（`traceback`）便于排查。

## 15. 变更记录

| 日期 | 来源 spec | 变更内容 |
|------|-----------|----------|
| 2026-07-14 | （初始基线） | 依据现有代码与历史迭代建立基线；涵盖认证、导入（含 iter-005/006 结清字段与拒绝通知增强）、导出、聚合（聚合触发条件由 `invoice.status='Financing confirmed'` 修正为 `finance.status='Loan booked'`）、批次管理、仪表盘、数据维护（含 Onboarding 每日同步、融资概览列表与导出）、工具集（iter-001/002）、FCB 模块（iter-003/004）、额度管理、对外 API、国际化通用及非功能需求 |
| 2026-08-17 | `2026-08-17-fcb-buyer-matching-design.md` | FCB 客户支持同一 supplier_code 对应多个 buyer（新增 `buyer_air8_code` 字段），CRUD 查重与导出匹配逻辑从单一 supplier_code 改为 supplier_code + buyer 组合匹配 |
| 2026-08-20 | `2026-08-20-credit-limit-management-design.md` | 额度管理重做为买方层汇总+供应商层钻取，新增预占/实占/Celling/Headroom 指标、Excel 导出、每日超阈值邮件预警（REQ-CREDIT-001~004） |
| 2026-08-20 | `2026-08-20-refactoring-financing-list-design.md` | 再保理融资单列表重构：菜单/标题中英文命名调整；列表由 16 列扩充为 26 列（新增资金方/帐期/利息/再保理货币-金额-利率-利息-净额/再保理平台状态-状态-结算状态等字段，移除汇总状态/批次号列）；聚合逻辑去除 `finance.status='Loan booked'` 过滤（覆盖未放款阶段记录），按融资申请号分组取最新对账单快照，修复 `refactoring_status`/`bank_source`（改名 `refactor_id`）/`financing_amount_trade_currency` 三处历史取值 bug，totals 避免同一融资单历史快照重复加总（REQ-AGG-001~002、REQ-MAINT-007）；存量 `refactoring_financing_overview` 记录需人工触发一次重新聚合（`manual_aggregate()` 或定时批处理任务）才能获得新增/修复字段 |
| 2026-08-20 | （用户验收反馈，非独立 spec） | 额度查询页面买方层/供应商层分别新增 Air8 Buyer ID / Air8 Seller ID 列，导出 Excel 同步新增；修复预占计算错误使用 `funded_before` 判定导致已完成放款的历史融资单被按原始金额重复计入的问题，改为要求 `status='eligible'`；实占金额修正为按 `bank_statement.finance.outstanding_amount` 乘以固定 90% 计算（REQ-CREDIT-001 AC1/3/4、REQ-CREDIT-002 AC1） |
| 2026-08-26 | `2026-08-26-credit-deal-level-rework-design.md` | 额度管理预占/实占/待结清下沉到 Deal 层统一计算（新增银行对账单 Advance Ratio 字段，Financing Amount = original_amount×advance_ratio，实占不再固定 90%，待结清取自 refactoring_bank_repayment_record），买卖方/买方层改为对 Deal 层求和；额度明细页重做（新列、跨页合计行、导出）；额度查询导出改为固定买方/买卖方/Deal 三个 sheet 均带合计行（REQ-CREDIT-001~003、005~006） |
| 2026-08-28 | （用户验收反馈，非独立 spec） | 修复待结清（To Be Settled on DB）误判：原判定仅依赖 `settled_in_air8='Settled'` 且 `bank_finance_status='Loan booked'`，未核对 DB 自身的结清状态字段 `invoice.settlement_status`，导致 DB 侧其实已经结清（`settlement_status='Settled'`）时仍被计入待结清、错误对冲 Total O/S；新增 `settlement_status != 'Settled'` 条件（REQ-CREDIT-001 AC4） |
