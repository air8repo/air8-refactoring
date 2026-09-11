import pandas as pd
import decimal
import logging
from datetime import datetime
from decimal import Decimal, ConversionSyntax
from flask import current_app
from backend.app.services.cleaning_service import CleaningService
from bson import Decimal128

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('import_service.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def get_mongo():
    """获取已初始化的mongo对象"""
    # 首先尝试直接从extensions模块导入（最高优先级，适合运行环境）
    try:
        from backend.app.extensions import mongo as ext_mongo
        if ext_mongo is not None:
            return ext_mongo
    except Exception:
        pass
    
    # 最后尝试从current_app.extensions获取（适合请求上下文环境）
    try:
        from flask import current_app
        if hasattr(current_app, 'extensions'):
            mongo = current_app.extensions.get('mongo')
            if mongo is not None:
                return mongo
    except Exception:
        pass
    
    return None


def _fmt_date(value):
    """将日期值格式化为 YYYY-MM-DD 字符串，空值返回 ''。"""
    if value is None:
        return ''
    try:
        if pd.isna(value):
            return ''
    except (TypeError, ValueError):
        pass
    if hasattr(value, 'strftime'):
        return value.strftime('%Y-%m-%d')
    return str(value)


def _is_rejected_or_cancelled(invoice_status, finance_status):
    """判定是否需要提醒（大小写不敏感）：
    - Invoice status 含 'rejected'，或 Finance status 含 'cancelled'；或
    - Invoice status = 'Financing confirmed' 且 Finance status 为
      'Booking requested accepted' / 'Loan booking failed'（融资已确认但银行端预订异常）。"""
    inv = (invoice_status or '').strip().lower()
    fin = (finance_status or '').strip().lower()
    if 'rejected' in inv or 'cancelled' in fin:
        return True
    if inv == 'financing confirmed' and fin in ('booking requested accepted', 'loan booking failed'):
        return True
    return False


def _send_loan_rejected_notification(records):
    """通过 n8n 通用邮件接口发送 Loan Rejected 汇总通知。

    records: list[dict]，每项为一条新出现的 Loan Rejected 明细。
    走 n8n-v2 通用邮件 webhook（COMMON_EMAIL_URL），JSON 入参 {type, title, body}，
    type 写死为 common，无需 token。
    """
    import requests

    email_url = current_app.config.get('COMMON_EMAIL_URL')
    if not email_url:
        logger.warning('邮件接口未配置(COMMON_EMAIL_URL)，跳过拒绝/取消通知')
        return False

    today = datetime.now().strftime('%Y-%m-%d')

    rows_html = ''.join(
        '<tr>'
        f'<td>{r.get("invoice_no", "")}</td>'
        f'<td>{r.get("buyer_name", "")}</td>'
        f'<td>{r.get("seller_name", "")}</td>'
        f'<td>{r.get("currency", "")} {r.get("invoice_amount", "")}</td>'
        f'<td>{r.get("invoice_status", "")}</td>'
        f'<td>{r.get("finance_status", "")}</td>'
        f'<td>{r.get("rejection_reason", "")}</td>'
        f'<td>{r.get("creation_time", "")}</td>'
        f'<td>{r.get("due_date", "")}</td>'
        '</tr>'
        for r in records
    )
    body = (
        f'<p>The following {len(records)} invoice(s) were newly marked as '
        f'<b>rejected / cancelled</b> by the bank on {today}:</p>'
        '<table border="1" cellpadding="6" cellspacing="0">'
        '<tr><th>Invoice No</th><th>Buyer</th><th>Seller</th>'
        '<th>Invoice Amount</th><th>Invoice Status</th><th>Finance Status</th>'
        '<th>Rejection Reason</th><th>Creation Time</th><th>Due Date</th></tr>'
        f'{rows_html}</table>'
    )

    payload = {
        'type': 'common',
        'title': f'[Refactoring] Rejected/Cancelled Invoice Notification - {today} ({len(records)})',
        'body': body,
    }

    try:
        response = requests.post(
            email_url,
            json=payload,
            timeout=60,
            verify=False,
        )
        response.raise_for_status()
        logger.info('Loan Rejected 通知邮件已发送, 共 %d 条; 响应: %s',
                    len(records), response.text[:200])
        return True
    except requests.RequestException as e:
        logger.error(f'Loan Rejected 通知邮件发送失败: {e}')
        raise


class ImportService:
    """数据导入服务"""
    
    def __init__(self):
        self.cleaning_service = CleaningService()
    
    def import_file(self, file, import_type, bank_channel='DB'):
        """导入Excel文件到MongoDB"""
        try:
            logger.info(f"开始导入文件，类型: {import_type}, 银行渠道: {bank_channel}")

            # 记录文件名与大小，便于定位「读取阶段」卡死/被杀（大文件 OOM 等）
            file_name = getattr(file, 'filename', '<unknown>')
            file_size = -1
            try:
                stream = getattr(file, 'stream', file)
                pos = stream.tell()
                stream.seek(0, 2)
                file_size = stream.tell()
                stream.seek(pos)
            except Exception:
                pass
            logger.info(f"准备读取Excel: 文件名={file_name}, 大小={file_size} bytes")

            try:
                df = pd.read_excel(file)
            except Exception as read_err:
                logger.error(f"读取Excel失败(pd.read_excel): {read_err}", exc_info=True)
                raise
            logger.info(f"成功读取Excel文件，共 {len(df)} 行数据；列名: {list(df.columns)}")

            if import_type == 'onboarding':
                cleaned_df = self.cleaning_service.clean_onboarding_data(df)
                return self._import_onboarding(cleaned_df)
            elif import_type == 'financing':
                cleaned_df = self.cleaning_service.clean_financing_data(df)
                return self._import_financing(cleaned_df)
            elif import_type == 'repayment':
                logger.info("处理还款数据导入")
                cleaned_df = self.cleaning_service.clean_repayment_data(df)
                logger.info(f"还款数据清洗完成，共 {len(cleaned_df)} 行有效数据")
                return self._import_repayment(cleaned_df)
            elif import_type == 'bank_statement':
                cleaned_df = self.cleaning_service.clean_bank_statement_data(df)
                return self._import_bank_statement(cleaned_df, bank_channel=bank_channel)
            elif import_type == 'financing_overview':
                cleaned_df = self.cleaning_service.clean_financing_overview_data(df)
                return self._import_financing_overview(cleaned_df)
            elif import_type == 'batch_number':
                return self._import_batch_number(df)
            elif import_type == 'repayment_date':
                return self._import_repayment_date(df)
            else:
                logger.error(f"无效的导入类型: {import_type}")
                return {'success': False, 'message': '无效的导入类型'}
        except Exception as e:
            logger.error(f"文件导入失败: {str(e)}", exc_info=True)
            return {'success': False, 'message': str(e)}
    
    def import_from_api(self, import_type):
        """从API导入数据到MongoDB"""
        import requests
        try:
            if import_type == 'repayment':
                # API获取还款单数据
                api_url = 'https://n8n.air8.cn/webhook/exportRepaymentOrders?token=d5173b84678c11f0995006a0ea58daac'
                response = requests.get(api_url, verify=False)
                response.raise_for_status()
                api_data = response.json()
                
                # 将JSON数据转换为DataFrame
                df = pd.DataFrame(api_data)
                
                # 调用现有的清洗和导入逻辑
                cleaned_df = self.cleaning_service.clean_repayment_data(df)
                return self._import_repayment(cleaned_df)
            elif import_type == 'financing':
                # API获取融资单数据
                api_url = 'https://n8n.air8.cn/webhook/exportFinancingOrders?token=d5173b84678c11f0995006a0ea58daac'
                response = requests.get(api_url, verify=False)
                response.raise_for_status()
                api_data = response.json()
                
                # 将JSON数据转换为DataFrame
                df = pd.DataFrame(api_data)
                
                # 调用现有的清洗和导入逻辑
                cleaned_df = self.cleaning_service.clean_financing_data(df)
                return self._import_financing(cleaned_df)
            else:
                return {'success': False, 'message': f'不支持的API导入类型: {import_type}'}
        except Exception as e:
            return {'success': False, 'message': f'API导入失败: {str(e)}'}

    
    def _import_onboarding(self, df):
        """导入onboarding配置数据，支持根据uid重复导入"""
        mongo = get_mongo()
        if mongo is None:
            return {'success': False, 'message': '数据库未连接'}
        
        inserted_count = 0
        updated_count = 0
        
        for _, row in df.iterrows():
            uid = ''
            if 'UID' in df.columns:
                uid_val = row.get('UID')
                uid = uid_val if pd.notna(uid_val) else ''
            
            record = {
                'uid': uid,
                'air8_buyer_id': row.get('Air8 Buyer ID') if pd.notna(row.get('Air8 Buyer ID')) else '',
                'obligor_name': row.get('Obligors') if pd.notna(row.get('Obligors')) else '',
                'country': row.get('Country') if pd.notna(row.get('Country')) else '',
                'air8_seller_id': row.get('Air8 Seller ID') if pd.notna(row.get('Air8 Seller ID')) else '',
                'seller_name': row.get('Seller name') if pd.notna(row.get('Seller name')) else '',
                'target_list_status': row.get('target list satus\nY = started refactoring\nN = not submit') if pd.notna(row.get('target list satus\nY = started refactoring\nN = not submit')) else '',
                'approved_tenor_days': int(row.get('Approved Tenor')) if pd.notna(row.get('Approved Tenor')) else 0,
                'max_invoice_count': int(row.get('Number of invoice as of 7Oct')) if pd.notna(row.get('Number of invoice as of 7Oct')) else 0,
                'remarks': row.get('Remarks') if pd.notna(row.get('Remarks')) else '',
                'first_submit_date': row.get('1st submit date').strftime('%Y-%m-%d') if pd.notna(row.get('1st submit date')) else '',
                'updated_at': datetime.now()
            }
            
            existing = mongo.refactoring_onboard_config.find_one({'uid': uid})
            if existing:
                record['_id'] = existing['_id']
                record['created_at'] = existing['created_at']
                mongo.refactoring_onboard_config.replace_one({'_id': existing['_id']}, record)
                updated_count += 1
            else:
                record['created_at'] = datetime.now()
                mongo.refactoring_onboard_config.insert_one(record)
                inserted_count += 1
        
        return {'success': True, 'inserted': inserted_count, 'updated': updated_count, 'total': inserted_count + updated_count}
    
    def _import_batch_number(self, df):
        """导入批次号数据，根据FR#更新融资订单表中的batch_number字段"""
        mongo = get_mongo()
        if mongo is None:
            return {'success': False, 'message': '数据库未连接'}
        
        updated_count = 0
        failed_count = 0
        current_time = datetime.now()
        
        for _, row in df.iterrows():
            try:
                # 获取FR#和批次号
                fr_number = str(row.get('FR#')) if row.get('FR#') is not None and not pd.isna(row.get('FR#')) else ''
                batch_number = row.get('Loan submission Batch')
                
                if not fr_number:
                    failed_count += 1
                    continue
                
                # 将批次号转换为整数类型
                if isinstance(batch_number, (int, float)):
                    batch_number = int(batch_number)
                elif isinstance(batch_number, str) and batch_number.strip().isdigit():
                    batch_number = int(batch_number.strip())
                else:
                    failed_count += 1
                    continue
                
                # 根据FR#更新融资订单表中的批次相关字段
                result = mongo.refactoring_financing_order.update_one(
                    {'finance_request_number': fr_number},  # 根据finance_request_number查找
                    {'$set': {
                        'batch_number': batch_number,
                        'batch_status': 'active',
                        'is_batch': True,  # 设置为true
                        'funded_before': True,  # 设置为true
                        'batch_created_at': current_time,
                        'bank_source': 'db',
                        'updated_at': current_time
                    }}
                )
                
                if result.modified_count > 0:
                    updated_count += 1
                else:
                    # 检查是否找到记录但批次号未改变
                    existing_record = mongo.refactoring_financing_order.find_one({'finance_request_number': fr_number})
                    if existing_record and existing_record.get('batch_number') == batch_number:
                        updated_count += 1  # 记录存在且批次号相同，也算更新成功
                    else:
                        failed_count += 1
            
            except Exception as e:
                failed_count += 1
                print(f"处理FR# {fr_number}时发生错误: {str(e)}")
        
        return {'success': True, 'inserted': 0, 'updated': updated_count, 'failed': failed_count, 'total': updated_count + failed_count}
    
    def _import_repayment_date(self, df):
        """导入还款日期数据，根据FR#更新融资订单表中的db_loan_settle_date字段"""
        mongo = get_mongo()
        if mongo is None:
            return {'success': False, 'message': '数据库未连接'}
        
        updated_count = 0
        failed_count = 0
        current_time = datetime.now()
        
        for _, row in df.iterrows():
            try:
                # 获取FR#和还款日期
                fr_number = str(row.get('FR#')) if row.get('FR#') is not None and not pd.isna(row.get('FR#')) else ''
                settle_date = row.get('Settle Date')
                
                if not fr_number:
                    failed_count += 1
                    continue
                
                # 将还款日期转换为datetime类型
                if isinstance(settle_date, str):
                    # 处理不同格式的日期字符串，如20251212或2025-12-12
                    try:
                        if len(settle_date) == 8 and settle_date.isdigit():
                            # 格式：20251212
                            settle_date = datetime.strptime(settle_date, '%Y%m%d')
                        else:
                            # 格式：2025-12-12或其他
                            settle_date = pd.to_datetime(settle_date)
                    except ValueError:
                        failed_count += 1
                        continue
                elif not isinstance(settle_date, datetime):
                    # 如果不是字符串也不是datetime类型，尝试转换
                    try:
                        settle_date = pd.to_datetime(settle_date)
                    except ValueError:
                        failed_count += 1
                        continue
                
                # 根据FR#更新融资订单表中的db_loan_settle_date字段
                result = mongo.refactoring_financing_order.update_one(
                    {'finance_request_number': fr_number},  # 根据finance_request_number查找
                    {'$set': {
                        'db_loan_settle_date': settle_date,
                        'updated_at': current_time
                    }}
                )
                
                if result.modified_count > 0:
                    updated_count += 1
                else:
                    # 检查是否找到记录但日期未改变
                    existing_record = mongo.refactoring_financing_order.find_one({'finance_request_number': fr_number})
                    if existing_record and existing_record.get('db_loan_settle_date') == settle_date:
                        updated_count += 1  # 记录存在且日期相同，也算更新成功
                    else:
                        failed_count += 1
            
            except Exception as e:
                failed_count += 1
                print(f"处理FR# {fr_number}时发生错误: {str(e)}")
        
        return {'success': True, 'inserted': 0, 'updated': updated_count, 'failed': failed_count, 'total': updated_count + failed_count}
    
    def _import_financing(self, df):
        """导入融资订单数据，支持根据finance_request_number重复导入"""
        mongo = get_mongo()
        if mongo is None:
            return {'success': False, 'message': '数据库未连接'}
        
        inserted_count = 0
        updated_count = 0
        imported_ids = []
        
        def to_decimal(value):
            if pd.isna(value) or value is None:
                return Decimal128('0')
            try:
                if isinstance(value, (int, float)):
                    return Decimal128(str(value))
                # 尝试将字符串转换为数字，处理可能的千分位分隔符和货币符号
                str_value = str(value).strip()
                # 移除可能的货币符号和千分位分隔符
                str_value = str_value.replace(',', '').replace('$', '').replace('¥', '').replace('€', '')
                return Decimal128(str_value)
            except (ValueError, ConversionSyntax) as e:
                # 如果转换失败，记录日志并返回0
                logger.error(f"Decimal conversion failed for value '{value}': {str(e)}")
                return Decimal128('0')
        
        for _, row in df.iterrows():
            buyer_code = row.get('Buyer Code', '')
            supplier_code = row.get('Supplier Code', '')
            uid = buyer_code + supplier_code
            
            finance_request_number = row.get('Finance Request Number')
            
            record = {
                'uid': uid,
                'finance_request_number': finance_request_number,
                'invoice_number': row.get('Invoice Number') if pd.notna(row.get('Invoice Number')) else '',
                'cross_ref_inv_no': row.get('Cross Ref. Inv No.') if pd.notna(row.get('Cross Ref. Inv No.')) else '',
                'reference_no': row.get('Reference No.') if pd.notna(row.get('Reference No.')) else '',
                'order_no': row.get('Order No.') if pd.notna(row.get('Order No.')) else '',
                'in_the_onboarding_list': False,
                'target_list_status': 'PENDING',
                'is_batch': False,
                'funded_before': False,
                'status': row.get('Status') if pd.notna(row.get('Status')) else '',
                'can_push_to_db_today': False,
                'auto_finance': row.get('Auto Finance') == 'Yes',
                'supplier_name': row.get('Supplier Name') if pd.notna(row.get('Supplier Name')) else '',
                'supplier_code': supplier_code,
                'buyer_name': row.get('Buyer Name') if pd.notna(row.get('Buyer Name')) else '',
                'buyer_code': buyer_code,
                'funder_name': row.get('Funder Name') if pd.notna(row.get('Funder Name')) else '',
                'funder_code': row.get('Funder Code') if pd.notna(row.get('Funder Code')) else '',
                'channel_source': row.get('Channel Source') if pd.notna(row.get('Channel Source')) else '',
                'insurer': row.get('Insurer') if pd.notna(row.get('Insurer')) else '',
                'trade_amount': to_decimal(row.get('Trade Amount')),
                'financing_amount_trade_currency': to_decimal(row.get('Financing Amount (Trade Currency)')),
                'financing_amount': to_decimal(row.get('Financing Amount')),
                'actual_financing_amount': to_decimal(row.get('Actual Financing Amount')),
                'settled_amt_partial': to_decimal(row.get('Settled Amt Partial', 0)),
                'trade_currency': row.get('Trade Currency') if pd.notna(row.get('Trade Currency')) else '',
                'financing_currency': row.get('Financing Currency') if pd.notna(row.get('Financing Currency')) else '',
                'exchange_rate': to_decimal(row.get('Exchange Rate')),
                'interest_calculation_method': row.get('Interest Calculation Method') if pd.notna(row.get('Interest Calculation Method')) else '',
                'interest_rate_fee_charge': to_decimal(row.get('Interest Rate/Fee Charge')),
                'financing_interest': to_decimal(row.get('Financing Interest')),
                'expected_tenor': int(row.get('Expected Tenor')) if pd.notna(row.get('Expected Tenor')) else 0,
                'actual_tenor': int(row.get('Actual Tenor')) if pd.notna(row.get('Actual Tenor')) else 0,
                'collection_period': int(row.get('Collection Period')) if pd.notna(row.get('Collection Period')) else 0,
                'invoice_date': row.get('Invoice Date') if pd.notna(row.get('Invoice Date')) else datetime.now(),
                'due_tenor': int(row.get('Approved Tenor')) if pd.notna(row.get('Approved Tenor')) else 0,
                'due_credit_limit': to_decimal(row.get('Approved Credit Limit')) if pd.notna(row.get('Approved Credit Limit')) else Decimal128('0'),
                'due_date': row.get('Due Date') if pd.notna(row.get('Due Date')) else datetime.now(),
                'request_date': row.get('Request Date') if pd.notna(row.get('Request Date')) else datetime.now(),
                'expected_funding_date': row.get('Expected Funding Date') if pd.notna(row.get('Expected Funding Date')) else datetime.now(),
                'actual_funding_date': row.get('Actual Funding Date') if pd.notna(row.get('Actual Funding Date')) else datetime.now(),
                'actual_shipment_date': row.get('Actual Shipment Date') if pd.notna(row.get('Actual Shipment Date')) else row.get('Invoice Date') if pd.notna(row.get('Invoice Date')) else datetime.now(),
                'fr_overdue_in_coming_period': False,
                'due_date_vs_submission_date': False,
                'updated_at': datetime.now()
            }
            
            existing = mongo.refactoring_financing_order.find_one({'finance_request_number': finance_request_number})
            if existing:
                record['_id'] = existing['_id']
                record['created_at'] = existing['created_at']
                
                # 保留现有批次相关字段
                if existing.get('batch_number', 0) > 0 and existing.get('batch_status') == 'active':
                    record['batch_number'] = existing['batch_number']
                    record['batch_status'] = existing['batch_status']
                    record['batch_created_at'] = existing['batch_created_at']
                    record['bank_source'] = existing['bank_source']
                else:
                    # 如果批次号无效或不存在，使用默认值
                    record['batch_number'] = 0
                    record['batch_status'] = ''
                    record['batch_created_at'] = None
                    record['bank_source'] = 'db'
                
                mongo.refactoring_financing_order.replace_one({'_id': existing['_id']}, record)
                imported_ids.append(existing['_id'])
                updated_count += 1
            else:
                record['created_at'] = datetime.now()
                # 新记录使用默认批次相关字段
                record['batch_number'] = 0
                record['batch_status'] = ''
                record['batch_created_at'] = None
                record['bank_source'] = 'db'
                result = mongo.refactoring_financing_order.insert_one(record)
                imported_ids.append(result.inserted_id)
                inserted_count += 1
        
        if imported_ids:
            self._post_process_financing_records(imported_ids, mongo)
        
        return {'success': True, 'inserted': inserted_count, 'updated': updated_count, 'total': inserted_count + updated_count}
    
    def _import_repayment(self, df):
        """导入还款订单数据，支持根据finance_request_number唯一主键重复导入（upsert）"""
        mongo = get_mongo()
        if mongo is None:
            logger.error("数据库连接失败")
            return {'success': False, 'message': '数据库未连接'}
        
        inserted_count = 0
        updated_count = 0
        
        def to_decimal(value):
            if pd.isna(value) or value is None:
                return Decimal128('0')
            try:
                if isinstance(value, (int, float)):
                    return Decimal128(str(value))
                # 尝试将字符串转换为数字，处理可能的千分位分隔符和货币符号
                str_value = str(value).strip()
                # 移除可能的货币符号和千分位分隔符
                str_value = str_value.replace(',', '').replace('$', '').replace('¥', '').replace('€', '')
                return Decimal128(str_value)
            except (ValueError, ConversionSyntax) as e:
                # 如果转换失败，记录日志并返回0
                logger.error(f"Decimal conversion failed for value '{value}': {str(e)}")
                return Decimal128('0')
        
        logger.info(f"开始导入还款数据，共 {len(df)} 行")
        for index, row in df.iterrows():
            try:
                finance_request_number = row.get('Finance Request Number')
                settlement_date = row.get('Settlement Date') if pd.notna(row.get('Settlement Date')) else row.get('Actual Funding Date') if pd.notna(row.get('Actual Funding Date')) else row.get('Due Date') if pd.notna(row.get('Due Date')) else datetime.now()
                
                logger.debug(f"处理还款数据行 {index+1}: FR#={finance_request_number}, 结算日期={settlement_date}")
                
                record = {
                    'invoice_number': row.get('Invoice Number'),
                    'finance_request_number': finance_request_number,
                    'order_type': row.get('Order Type'),
                    'source': row.get('Source'),
                    'supplier_name': row.get('Supplier Name'),
                    'supplier_code': row.get('Supplier Code'),
                    'supplier_country': row.get('Supplier Country'),
                    'buyer_name': row.get('Buyer Name'),
                    'buyer_code': row.get('Buyer Code'),
                    'funder_name': row.get('Funder Name'),
                    'funder_code': row.get('Funder Code'),
                    'invoice_total_tax_include': to_decimal(row.get('Invoice Total Tax Include', 0)),
                    'total_ar': to_decimal(row.get('Total AR')),
                    'total_principle_amount': to_decimal(row.get('Total Principle Amount')),
                    'cumulative_repayment': to_decimal(row.get('Cumulative Repayment')),
                    'os_balance': to_decimal(row.get('O/S Balance')),
                    'os_principle': to_decimal(row.get('O/S Principle')),
                    'cumulative_repaid_principle': to_decimal(row.get('Cumulative Repaid Principle')),
                    'financing_currency': row.get('Financing Currency'),
                    'interest_rate_fee_charge': to_decimal(row.get('Interest Rate/Fee Charge')),
                    'actual_interest_fee_charge': to_decimal(row.get('Actual Interest/Fee Charge')),
                    'adjusted_interest_charges': to_decimal(row.get('Adjusted Interest/Charges')),
                    'adjusted_amount': to_decimal(row.get('Adjusted Amount')),
                    'due_date': row.get('Due Date') if pd.notna(row.get('Due Date')) else datetime.now(),
                    'actual_funding_date': row.get('Actual Funding Date') if pd.notna(row.get('Actual Funding Date')) else datetime.now(),
                    'settlement_date': settlement_date,
                    'grace_period': row.get('Grace Period'),
                    'repayment_status': row.get('Repayment Status'),
                    'recall_type': row.get('Recall Type'),
                    'recalled_amount': to_decimal(row.get('Recalled Amount')),
                    'to_be_recalled_amount': to_decimal(row.get('To Be Recalled Amount')),
                    'po_number': row.get('PO Number'),
                    'updated_at': datetime.now()
                }
                
                existing = mongo.refactoring_repayment_order.find_one({
                    'finance_request_number': finance_request_number
                })
                
                if existing:
                    record['_id'] = existing['_id']
                    record['created_at'] = existing['created_at']
                    mongo.refactoring_repayment_order.replace_one({'_id': existing['_id']}, record)
                    updated_count += 1
                    logger.debug(f"更新还款记录: FR#={finance_request_number}")
                else:
                    record['created_at'] = datetime.now()
                    mongo.refactoring_repayment_order.insert_one(record)
                    inserted_count += 1
                    logger.debug(f"插入新还款记录: FR#={finance_request_number}")
            except Exception as e:
                logger.error(f"处理还款数据行 {index+1} 时失败: {str(e)}", exc_info=True)
        
        logger.info(f"还款数据导入完成，插入 {inserted_count} 条，更新 {updated_count} 条，共 {inserted_count + updated_count} 条")
        return {'success': True, 'inserted': inserted_count, 'updated': updated_count, 'total': inserted_count + updated_count}
    
    def _post_process_financing_records(self, inserted_ids=None, mongo=None):
        """融资订单后处理逻辑，支持处理指定ID或所有记录"""
        if mongo is None:
            mongo = get_mongo()
        if mongo is None:
            return {'success': False, 'message': '数据库未连接'}
        
        try:
            from decimal import Decimal
            from bson import Decimal128
            
            onboard_configs = list(mongo.refactoring_onboard_config.find())
            onboard_by_uid = {config.get('uid'): config for config in onboard_configs}
            
            repayment_orders = list(mongo.refactoring_repayment_order.find())
            repayment_by_finance = {repayment.get('finance_request_number'): repayment for repayment in repayment_orders}
            
            financing_overviews = list(mongo.refactoring_financing_overview.find())
            overview_by_invoice = {overview.get('order_details', {}).get('invoice_number'): overview for overview in financing_overviews}
            
            today = datetime.now().date()
            
            def is_zero(value):
                if value is None:
                    return True
                if isinstance(value, Decimal128):
                    return value.to_decimal() == Decimal('0')
                return value == 0 or value == Decimal('0')
            
            # 如果没有提供inserted_ids，则处理所有融资单
            if inserted_ids is None or len(inserted_ids) == 0:
                # 获取所有融资单的ID
                inserted_ids = [record['_id'] for record in mongo.refactoring_financing_order.find({}, {'_id': 1})]
            
            processed_count = 0
            for record_id in inserted_ids:
                record = mongo.refactoring_financing_order.find_one({'_id': record_id})
                if not record:
                    continue
                processed_count += 1
                
                uid = record.get('uid', '')
                finance_request_number = record.get('finance_request_number', '')
                invoice_number = record.get('invoice_number', '')
                due_date = record.get('due_date')
                target_list_status = record.get('target_list_status', 'PENDING')
                
                in_the_onboarding_list = True if uid in onboard_by_uid else False
                target_list_status = onboard_by_uid[uid].get('target_list_status', '') if uid in onboard_by_uid else ''
                
                # 根据Invoice Number在bank_statement表查找，计算funded_before
                funded_before = False
                # 查询bank_statement表，invoice.seller_reference对应融资单的invoice_number
                # 已融资的判定改为 finance.status='Loan booked'（原为 invoice.status='Financing confirmed'）
                bank_statement = mongo.refactoring_bank_statement.find_one(
                    {'invoice.seller_reference': invoice_number,
                     'finance.status': 'Loan booked'}
                )
                if bank_statement:
                    funded_before = True
                
                # 直接根据record中的batch_number判断is_batch
                batch_number = record.get('batch_number', 0)
                is_batch = batch_number > 0
                
                # 如果is_batch为True，则funded_before也设为True
                if is_batch:
                    funded_before = True
                
                repayment = repayment_by_finance.get(finance_request_number, {})
                settled_amt_partial = repayment.get('cumulative_repayment', Decimal128('0'))
                
                # 计算Settled in Air8：根据Finance Request Number关联repayment_order的Repayment Status
                settled_in_air8 = repayment.get('repayment_status') or ''
                
                # 计算FR Settlement date：如果Settled in Air8="Settled"，则取repayment_order的Settlement Date，否则为空
                fr_settlement_date = repayment.get('settlement_date', '') if settled_in_air8 == 'Settled' else ''
                
                # 计算Air8 Settled FR amt：如果Settled in Air8="settled"，则取Financing Amount (Trade Currency)，否则为空
                financing_amount = record.get('financing_amount', 0)
                air8_settled_fr_amt = financing_amount if settled_in_air8.lower() == 'settled' else ''
                
                # 初始化变量
                finance_amount = 0
                outstanding_amount = 0

                # 计算Settled DB loan：根据发票编号关联bank_statement表
                settled_db_loan = ''
                bank_finance_status = ''
                if bank_statement:
                    invoice_details = bank_statement.get('invoice', {})
                    db_settlement_date = invoice_details.get('settlement_date', '')
                    # 获取Finance Details - Finance Amount 和 Finance Details - Outstanding Amount（原始币种）
                    finance_details_bs = bank_statement.get('finance', {})
                    finance_amount = finance_details_bs.get('finance_amount', Decimal128('0'))
                    outstanding_amount = finance_details_bs.get('outstanding_amount', Decimal128('0'))
                    # 统一在源头将 Decimal128 转换为 Decimal，避免后续与 int 比较/运算时报错
                    # （Decimal128 不支持与 int 比较，例如 outstanding_amount > 0）
                    if isinstance(finance_amount, Decimal128):
                        finance_amount = finance_amount.to_decimal()
                    if isinstance(outstanding_amount, Decimal128):
                        outstanding_amount = outstanding_amount.to_decimal()
                    # 获取银行放款状态
                    bank_finance_status = finance_details_bs.get('status', '')
                    if db_settlement_date:
                        # 计算公式：Finance Details - Finance Amount - Finance Details - Outstanding Amount
                        settled_db_loan = finance_amount - outstanding_amount
                        # 将结果转换回Decimal128
                        settled_db_loan = Decimal128(str(settled_db_loan))

                # 计算WIP / Pending (DB o/s)：复杂的条件判断
                wip_pending = ''
                if settled_in_air8.lower() == 'settled':
                    # 如果Settled in Air8="settled"，且Finance Details - Outstanding Amount > 0，则为该值，否则为空
                    if outstanding_amount > 0:
                        if isinstance(outstanding_amount, Decimal):
                            wip_pending = Decimal128(str(outstanding_amount))
                        else:
                            wip_pending = outstanding_amount
                else:
                    # 否则，为Air8 Settled FR amt - Settled DB loan
                    if air8_settled_fr_amt and settled_db_loan:
                        result = air8_settled_fr_amt - settled_db_loan
                        if isinstance(result, Decimal):
                            wip_pending = Decimal128(str(result))
                        else:
                            wip_pending = result
                
                # 从bank_statement获取Finance Details相关字段
                finance_details_due_date = None
                finance_details_interest_rate = 0
                if bank_statement:
                    invoice_details = bank_statement.get('invoice', {})
                    finance_details = bank_statement.get('finance_details', {})
                    finance_details_due_date = finance_details.get('due_date')
                    finance_details_interest_rate = finance_details.get('interest_rate', 0)
                
                # 获取DB loan settle date (Air8 upload date) - 融资单表上已有的字段
                db_loan_settle_date = record.get('db_loan_settle_date', '')
                
                # 计算Overdue interest (for settled case) - WIP
                overdue_interest_settled = ''
                if settled_in_air8 == 'Settled':
                    if not db_loan_settle_date:
                        overdue_interest_settled = 'pending for settle'
                    else:
                        if finance_details_due_date and isinstance(finance_details_due_date, datetime) and isinstance(db_loan_settle_date, datetime):
                            if finance_details_due_date >= db_loan_settle_date:
                                overdue_interest_settled = ''
                            else:
                                # 计算逾期天数
                                overdue_days = (db_loan_settle_date - finance_details_due_date).days
                                # 计算公式：(settle date - due date)/360 * interest rate/100 * Finance Details - Finance Amount
                                result = (overdue_days / 360) * (finance_details_interest_rate / 100) * finance_amount
                                if isinstance(result, (float, Decimal)):
                                    overdue_interest_settled = Decimal128(str(result))
                                else:
                                    overdue_interest_settled = result

                # 计算Overdue interest (for od case) - WIP
                overdue_interest_od = ''
                if settled_in_air8 != 'Settled':
                    if finance_details_due_date and isinstance(finance_details_due_date, datetime):
                        today = datetime.now()
                        if finance_details_due_date > today:
                            overdue_interest_od = ''
                        else:
                            # 计算逾期天数
                            overdue_days_od = (today - finance_details_due_date).days
                            # 计算公式：-(due date - TODAY())/360 * interest rate/100 * Finance Details - Outstanding Amount
                            result = (overdue_days_od / 360) * (finance_details_interest_rate / 100) * outstanding_amount
                            if isinstance(result, (float, Decimal)):
                                overdue_interest_od = Decimal128(str(result))
                            else:
                                overdue_interest_od = result
                
                # 计算Oustanding loan (DB fund to Air8) excluded WIP settlement
                outstanding_loan_excluded_wip = ''
                if is_batch:
                    if not db_loan_settle_date:
                        if isinstance(outstanding_amount, Decimal):
                            outstanding_loan_excluded_wip = Decimal128(str(outstanding_amount))
                        else:
                            outstanding_loan_excluded_wip = outstanding_amount
                
                fr_overdue_in_coming_period = False
                if due_date:
                    try:
                        if hasattr(due_date, 'date'):
                            due_date_only = due_date.date()
                        else:
                            if isinstance(due_date, str):
                                due_date_obj = datetime.strptime(due_date, '%Y-%m-%d')
                                due_date_only = due_date_obj.date()
                            else:
                                due_date_only = due_date
                        
                        fr_overdue_in_coming_period = True if (due_date_only - today).days < 0 else False
                    except (ValueError, TypeError):
                        fr_overdue_in_coming_period = False
                
                due_date_vs_submission_date = False
                if uid in onboard_by_uid:
                    onboard_config = onboard_by_uid[uid]
                    approved_tenor = onboard_config.get('approved_tenor_days', 0)
                    if due_date:
                        try:
                            if hasattr(due_date, 'date'):
                                due_date_only = due_date.date()
                            else:
                                if isinstance(due_date, str):
                                    due_date_obj = datetime.strptime(due_date, '%Y-%m-%d')
                                    due_date_only = due_date_obj.date()
                                else:
                                    due_date_only = due_date
                            
                            days_diff = (due_date_only - today).days
                            due_date_vs_submission_date = True if days_diff > approved_tenor else False
                        except (ValueError, TypeError):
                            due_date_vs_submission_date = False
                
                status = ''
                if target_list_status == 'Pending':
                    status = 'for next phase'
                elif target_list_status != 'Y':
                    status = 'not on the list / Code mismatch'
                elif funded_before:
                    status = 'funded before'
                elif fr_overdue_in_coming_period:
                    status = 'OD related'
                elif due_date_vs_submission_date:
                    status = 'Finance Tenor Exceed DB approved, pls resubmit later'
                elif is_zero(settled_amt_partial):
                    status = 'eligible'
                else:
                    status = 'partial paid'
                
                can_push_to_db_today = True if status == 'eligible' else False
                
                mongo.refactoring_financing_order.update_one(
                    {'_id': record_id},
                    {
                        '$set': {
                            'in_the_onboarding_list': in_the_onboarding_list,
                            'target_list_status': target_list_status,
                            'is_batch': is_batch,
                            'funded_before': funded_before,
                            'settled_amt_partial': settled_amt_partial,
                            'fr_overdue_in_coming_period': fr_overdue_in_coming_period,
                            'due_date_vs_submission_date': due_date_vs_submission_date,
                            'status': status,
                            'can_push_to_db_today': can_push_to_db_today,
                            'settled_in_air8': settled_in_air8,
                            'fr_settlement_date': fr_settlement_date,
                            'air8_settled_fr_amt': air8_settled_fr_amt,
                            'settled_db_loan': settled_db_loan,
                            'wip_pending': wip_pending,
                            'overdue_interest_settled_wip': overdue_interest_settled,
                            'overdue_interest_od_wip': overdue_interest_od,
                            'outstanding_loan_excluded_wip': outstanding_loan_excluded_wip,
                            'bank_finance_status': bank_finance_status,
                            'updated_at': datetime.now()
                        }
                    }
                )
            
            return {
                'success': True,
                'message': f'成功处理 {processed_count} 条融资单记录',
                'processed_count': processed_count
            }
        except Exception as e:
            print(f"Error in post_process_financing_records: {str(e)}")
            return {
                'success': False,
                'message': f'处理融资单记录时发生错误: {str(e)}'
            }
    
    def refresh_all_financing_records(self):
        """刷新所有融资单的后处理逻辑"""
        return self._post_process_financing_records()
    
    def _import_bank_statement(self, df, bank_channel='DB'):
        """导入银行对账单数据，支持根据invoice.system_invoice_id主键重复导入"""
        mongo = get_mongo()
        if mongo is None:
            logger.error("[导入-银行对账单] 数据库未连接，终止")
            return {'success': False, 'message': '数据库未连接'}

        logger.info("[导入-银行对账单] 开始写入，清洗后共 %d 行", len(df))

        inserted_count = 0
        updated_count = 0
        newly_rejected = []  # 本次新出现的拒绝/取消 明细，用于汇总邮件通知

        def to_decimal(value):
            if pd.isna(value) or value is None:
                return Decimal128('0')
            try:
                if isinstance(value, (int, float)):
                    return Decimal128(str(value))
                # 尝试将字符串转换为数字，处理可能的千分位分隔符和货币符号
                str_value = str(value).strip()
                # 移除可能的货币符号和千分位分隔符
                str_value = str_value.replace(',', '').replace('$', '').replace('¥', '').replace('€', '')
                return Decimal128(str_value)
            except (ValueError, ConversionSyntax) as e:
                # 如果转换失败，记录日志并返回0
                logger.error(f"Decimal conversion failed for value '{value}': {str(e)}")
                return Decimal128('0')
        
        # 银行渠道映射方法，预留扩展接口
        def map_bank_channel_data(record, channel):
            """根据银行渠道映射数据字段"""
            # 基础映射，为不同渠道预留扩展
            if channel == 'DB':
                # DB渠道特殊处理
                pass
            # elif channel == 'OTHER':
            #     # 其他渠道特殊处理
            #     pass
            return record
        
        for _, row in df.iterrows():
            system_invoice_id = str(row.get('Invoice Details - System InvoiceID')) if row.get('Invoice Details - System InvoiceID') is not None and not pd.isna(row.get('Invoice Details - System InvoiceID')) else ''
            
            record = {
                'bank_channel': bank_channel,  # 记录银行渠道
                'parties': {
                    'buyer_name': row.get('Parties Details - Buyer Name') if row.get('Parties Details - Buyer Name') is not None and not pd.isna(row.get('Parties Details - Buyer Name')) else '',
                    'seller_name': row.get('Parties Details - Seller Name') if row.get('Parties Details - Seller Name') is not None and not pd.isna(row.get('Parties Details - Seller Name')) else '',
                    'buyer_erp_id': row.get('Parties Details - Buyer ERP ID') if row.get('Parties Details - Buyer ERP ID') is not None and not pd.isna(row.get('Parties Details - Buyer ERP ID')) else '',
                    'seller_erp_id': row.get('Parties Details - Seller ERP ID') if row.get('Parties Details - Seller ERP ID') is not None and not pd.isna(row.get('Parties Details - Seller ERP ID')) else ''
                },
                'invoice': {
                    'system_invoice_id': system_invoice_id,
                    'status': row.get('Invoice Details - Status') if row.get('Invoice Details - Status') is not None and not pd.isna(row.get('Invoice Details - Status')) else '',
                    'validation_reason': str(row.get('Invoice Details - Validation Status Reason')) if row.get('Invoice Details - Validation Status Reason') is not None and not pd.isna(row.get('Invoice Details - Validation Status Reason')) else '',
                    'issue_date': row.get('Invoice Details - Issue Date') if pd.notna(row.get('Invoice Details - Issue Date')) else datetime.now(),
                    'due_date': row.get('Invoice Details - Due Date') if pd.notna(row.get('Invoice Details - Due Date')) else datetime.now(),
                    'adjusted_due_date': row.get('Invoice Details - Adjusted Due Date') if pd.notna(row.get('Invoice Details - Adjusted Due Date')) else datetime.now(),
                    'seller_reference': row.get('Invoice Details - Seller Reference') if row.get('Invoice Details - Seller Reference') is not None and not pd.isna(row.get('Invoice Details - Seller Reference')) else '',
                    'currency': row.get('Invoice Details - Currency') if row.get('Invoice Details - Currency') is not None and not pd.isna(row.get('Invoice Details - Currency')) else '',
                    'original_amount': to_decimal(row.get('Invoice Details - Original Amount')),
                    # 结清日期用 Excel 原始值；为空/解析失败时留空(None)，不再回退成导入时的系统时间
                    'settlement_date': row.get('Invoice Details - Settlement Date') if pd.notna(row.get('Invoice Details - Settlement Date')) else None,
                    # 结清状态。settlement_status 为银行原始字段。
                    'settlement_status': row.get('Invoice Details - Settlement Status') if row.get('Invoice Details - Settlement Status') is not None and not pd.isna(row.get('Invoice Details - Settlement Status')) else '',
                    # raw_settlement_date 与 settlement_date 现保持一致（历史保留字段）
                    'raw_settlement_date': row.get('Invoice Details - Settlement Date') if pd.notna(row.get('Invoice Details - Settlement Date')) else None,
                    # Creation Time 用 Excel 原始值；为空/解析失败时留空(None)，不再回退成导入时的系统时间
                    'creation_time': row.get('Invoice Details - Creation Time') if pd.notna(row.get('Invoice Details - Creation Time')) else None,
                    'vat_rate': to_decimal(row.get('Invoice Details - VAT Rate')),
                    'vat_amount': to_decimal(row.get('Invoice Details - VAT Amount'))
                },
                'finance': {
                    'status': row.get('Finance Details - Financing in statuses') if row.get('Finance Details - Financing in statuses') is not None and not pd.isna(row.get('Finance Details - Financing in statuses')) else '',
                    'db_finance_ref': row.get('Finance Details - DB Finance Ref.') if row.get('Finance Details - DB Finance Ref.') is not None and not pd.isna(row.get('Finance Details - DB Finance Ref.')) else '',
                    'start_date': row.get('Finance Details - Start Date') if pd.notna(row.get('Finance Details - Start Date')) else datetime.now(),
                    'due_date': row.get('Finance Details - Due Date') if pd.notna(row.get('Finance Details - Due Date')) else datetime.now(),
                    'tenor': int(row.get('Finance Details - Tenor')) if pd.notna(row.get('Finance Details - Tenor')) else 0,
                    'finance_amount': to_decimal(row.get('Finance Details - Finance Amount')),
                    'outstanding_amount': to_decimal(row.get('Finance Details - Outstanding Amount')),
                    'reference_rate_pct': to_decimal(row.get('Finance Details - Reference Rate %')),
                    'interest_rate_pct': to_decimal(row.get('Finance Details - Interest Rate %')),
                    'interest_amount': to_decimal(row.get('Finance Details - Interest Amount')),
                    'purchase_price': to_decimal(row.get('Finance Details - Purchase Price')),
                    'advance_ratio_pct': to_decimal(row.get('Finance Details - Advance Ratio'))
                },
                'usd_details': {
                    'original_amount': to_decimal(row.get('USD - Original Amount (USD)')),
                    'finance_amount': to_decimal(row.get('USD - Finance Amount (USD)')),
                    'outstanding_amount': to_decimal(row.get('USD - Outstanding Amount (USD)')),
                    'interest_amount': to_decimal(row.get('USD - Interest Amount (USD)')),
                    'purchase_price': to_decimal(row.get('USD - Purchase Price (USD)'))
                },
                'updated_at': datetime.now()
            }
            
            # 应用银行渠道映射
            mapped_record = map_bank_channel_data(record, bank_channel)
            
            # upsert 唯一键：invoice.seller_reference（同 seller_reference 覆盖最新）
            seller_reference = mapped_record.get('invoice', {}).get('seller_reference', '')
            existing = mongo.refactoring_bank_statement.find_one({'invoice.seller_reference': seller_reference})

            # 检测「新出现」的拒绝/取消。判定（大小写不敏感、子串匹配）：
            #   Invoice Details - Status 含 'rejected'  或  Finance status 含 'cancelled'。
            # 每次为全量导入，故以已存库状态为基准做增量判断：
            #   仅当本次命中、且之前未命中、也未通知过时才提醒。
            # 同时在 invoice 上打导入日期戳 rejected_notified_at 并跨全量导入沿用，确保只提醒一次。
            new_inv_status = mapped_record.get('invoice', {}).get('status', '')
            new_fin_status = mapped_record.get('finance', {}).get('status', '')
            existing_invoice = existing.get('invoice', {}) if existing else {}
            existing_finance = existing.get('finance', {}) if existing else {}
            prev_notified_at = existing_invoice.get('rejected_notified_at')

            new_hit = _is_rejected_or_cancelled(new_inv_status, new_fin_status)
            old_hit = _is_rejected_or_cancelled(
                existing_invoice.get('status', ''), existing_finance.get('status', ''))

            if new_hit:
                if not old_hit and not prev_notified_at:
                    # 新出现的拒绝/取消：盖上本次导入日期戳并加入通知列表
                    mapped_record['invoice']['rejected_notified_at'] = datetime.now()
                    inv = mapped_record.get('invoice', {})
                    fin = mapped_record.get('finance', {})
                    par = mapped_record.get('parties', {})
                    logger.info(
                        "检测到新出现的拒绝/取消: invoice_no=%s, invoice_status=%s, finance_status=%s, "
                        "reason=%s, buyer=%s, seller=%s, db_finance_ref=%s",
                        system_invoice_id, new_inv_status, new_fin_status,
                        inv.get('validation_reason', ''), par.get('buyer_name', ''),
                        par.get('seller_name', ''), fin.get('db_finance_ref', ''),
                    )
                    newly_rejected.append({
                        'invoice_no': inv.get('seller_reference', ''),   # Invoice No 取 seller_reference
                        'buyer_name': par.get('buyer_name', ''),
                        'seller_name': par.get('seller_name', ''),
                        'invoice_amount': str(inv.get('original_amount', '')),  # 发票金额
                        'currency': inv.get('currency', ''),
                        'invoice_status': new_inv_status,
                        'finance_status': new_fin_status,
                        'rejection_reason': inv.get('validation_reason', ''),
                        'creation_time': _fmt_date(inv.get('creation_time')),
                        'due_date': _fmt_date(inv.get('due_date')),
                    })
                elif prev_notified_at:
                    # 已通知过：保留原导入日期戳，避免全量重导时丢失而被再次提醒
                    mapped_record['invoice']['rejected_notified_at'] = prev_notified_at
                    logger.debug("拒绝/取消已通知过，跳过: invoice_no=%s", system_invoice_id)

            if existing:
                mapped_record['_id'] = existing['_id']
                mapped_record['created_at'] = existing['created_at']
                mongo.refactoring_bank_statement.replace_one({'_id': existing['_id']}, mapped_record)
                updated_count += 1
            else:
                mapped_record['created_at'] = datetime.now()
                mongo.refactoring_bank_statement.insert_one(mapped_record)
                inserted_count += 1
            
            # 处理非Loan booked状态的逻辑
            finance_status = mapped_record.get('finance', {}).get('status', '')
            if finance_status != 'Loan booked':
                # 合并parties.buyer_erp_id和parties.seller_erp_id为uid
                buyer_erp_id = mapped_record.get('parties', {}).get('buyer_erp_id', '')
                seller_erp_id = mapped_record.get('parties', {}).get('seller_erp_id', '')
                uid = f"{buyer_erp_id}-{seller_erp_id}"
                
                # 在refactoring_onboard_config表中查找这个uid
                onboard_config = mongo.refactoring_onboard_config.find_one({'uid': uid})
                if onboard_config:
                    # 将target_list_status改为"Pause"
                    mongo.refactoring_onboard_config.update_one(
                        {'uid': uid},
                        {'$set': {'target_list_status': 'Pause'}}
                    )
        
        # 汇总本次新出现的 Financing rejected，发送邮件通知（失败不影响导入结果）
        if newly_rejected:
            logger.info("本次导入新出现 Financing rejected 共 %d 条，准备发送通知邮件", len(newly_rejected))
            try:
                _send_loan_rejected_notification(newly_rejected)
            except Exception as e:
                logger.error(f"发送拒绝/取消通知邮件失败: {e}", exc_info=True)

        logger.info("[导入-银行对账单] 完成：新增 %d，更新 %d，新拒绝/取消 %d",
                    inserted_count, updated_count, len(newly_rejected))
        return {'success': True, 'inserted': inserted_count, 'updated': updated_count, 'total': inserted_count + updated_count}

    def _import_financing_overview(self, df):
        """导入融资概览数据，支持根据finance_request_number重复导入"""
        mongo = get_mongo()
        if mongo is None:
            return {'success': False, 'message': '数据库未连接'}
        
        inserted_count = 0
        updated_count = 0
        
        def to_decimal(value):
            if pd.isna(value) or value is None:
                return Decimal128('0')
            try:
                if isinstance(value, (int, float)):
                    return Decimal128(str(value))
                return Decimal128(str(value))
            except (ValueError, ConversionSyntax) as e:
                # 如果转换失败，记录日志并返回0
                logger.error(f"Decimal conversion failed for value '{value}': {str(e)}")
                return Decimal128('0')
        
        for _, row in df.iterrows():
            finance_request_number = row.get('Finance Request Number')
            
            record = {
                'finance_request_number': finance_request_number,
                'buyer_erp_id': row.get('Buyer ERP ID') if pd.notna(row.get('Buyer ERP ID')) else '',
                'buyer_name': row.get('Buyer Name') if pd.notna(row.get('Buyer Name')) else '',
                'seller_erp_id': row.get('Seller ERP ID') if pd.notna(row.get('Seller ERP ID')) else '',
                'seller_name': row.get('Seller Name') if pd.notna(row.get('Seller Name')) else '',
                'summary_status': row.get('Status') if pd.notna(row.get('Status')) else '',
                'loan_submission_batch': row.get('Loan Submission Batch') if pd.notna(row.get('Loan Submission Batch')) else '',
                'seq': int(row.get('Seq', 0)),
                'order_details': {
                    'invoice_number': row.get('Invoice Number') if pd.notna(row.get('Invoice Number')) else '',
                    'buyer_reference': row.get('Buyer Reference') if pd.notna(row.get('Buyer Reference')) else '',
                    'seller_reference': row.get('Seller Reference') if pd.notna(row.get('Seller Reference')) else '',
                    'original_amount': to_decimal(row.get('Original Amount')),
                    'currency': row.get('Currency') if pd.notna(row.get('Currency')) else '',
                    'issue_date': row.get('Issue Date') if pd.notna(row.get('Issue Date')) else datetime.now(),
                    'due_date': row.get('Due Date') if pd.notna(row.get('Due Date')) else datetime.now(),
                    'maturity_date': row.get('Maturity Date') if pd.notna(row.get('Maturity Date')) else datetime.now(),
                    'fr_settlement_date': row.get('FR Settlement Date') if pd.notna(row.get('FR Settlement Date')) else datetime.now(),
                    'adjusted_due_date': row.get('Adjusted Due Date') if pd.notna(row.get('Adjusted Due Date')) else datetime.now(),
                    'air8_finance_amt': to_decimal(row.get('Air8 Finance Amt')),
                    'interest_rate_pct': to_decimal(row.get('Interest Rate %'))
                },
                'totals': {
                    'air8_finance_amt': to_decimal(row.get('Air8 Finance Amt', 0)),
                    'air8_settled_fr_amt': to_decimal(row.get('Air8 Settled FR Amt', 0)),
                    'finance_amount_usd': to_decimal(row.get('Finance Amount (USD)', 0)),
                    'interest_amount_usd': to_decimal(row.get('Interest Amount (USD)', 0)),
                    'outstanding_amount_usd': to_decimal(row.get('Outstanding Amount (USD)', 0)),
                    'outstanding_loan_exclude_wip': to_decimal(row.get('Outstanding Loan (exclude WIP)', 0)),
                    'overdue_interest_od_wip': to_decimal(row.get('Overdue Interest (OD WIP)', 0)),
                    'overdue_interest_settled_wip': to_decimal(row.get('Overdue Interest (Settled WIP)', 0)),
                    'purchase_price_usd': to_decimal(row.get('Purchase Price (USD)', 0)),
                    'settled_db_loan': to_decimal(row.get('Settled DB Loan', 0)),
                    'wip_pending_amount': to_decimal(row.get('WIP Pending Amount', 0))
                },
                'bank_statements': [],
                'repayments': [],
                'updated_at': datetime.now()
            }
            
            existing = mongo.refactoring_financing_overview.find_one({'finance_request_number': finance_request_number})
            
            if existing:
                record['_id'] = existing['_id']
                record['created_at'] = existing['created_at']
                mongo.refactoring_financing_overview.replace_one({'_id': existing['_id']}, record)
                updated_count += 1
            else:
                record['created_at'] = datetime.now()
                mongo.refactoring_financing_overview.insert_one(record)
                inserted_count += 1
        
        return {'success': True, 'inserted': inserted_count, 'updated': updated_count, 'total': inserted_count + updated_count}
