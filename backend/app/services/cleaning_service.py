import pandas as pd
import logging
from datetime import datetime
from typing import Dict, List, Any

logger = logging.getLogger(__name__)


class CleaningService:
    """数据清洗服务"""
    
    def clean_onboarding_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """清洗onboarding配置数据"""
        # 复制数据以避免修改原始数据
        cleaned_df = df.copy()
        
        # 1. 处理缺失值
        if 'UID' in cleaned_df.columns:
            cleaned_df['UID'] = cleaned_df['UID'].fillna('')
        else:
            cleaned_df['UID'] = ''  # 如果UID列不存在，添加并设为空字符串
        
        cleaned_df['Air8 Buyer ID'] = cleaned_df['Air8 Buyer ID'].fillna('') if 'Air8 Buyer ID' in cleaned_df.columns else ''
        cleaned_df['Air8 Seller ID'] = cleaned_df['Air8 Seller ID'].fillna('') if 'Air8 Seller ID' in cleaned_df.columns else ''
        cleaned_df['Obligors'] = cleaned_df['Obligors'].fillna('') if 'Obligors' in cleaned_df.columns else ''
        cleaned_df['Seller name'] = cleaned_df['Seller name'].fillna('') if 'Seller name' in cleaned_df.columns else ''
        
        # 2. 标准化日期格式
        if '1st submit date' in cleaned_df.columns:
            cleaned_df['1st submit date'] = pd.to_datetime(cleaned_df['1st submit date'], errors='coerce')
        
        # 3. 标准化目标列表状态
        target_list_col = 'target list satus\nY = started refactoring\nN = not submit'
        if target_list_col in cleaned_df.columns:
            cleaned_df[target_list_col] = cleaned_df[target_list_col].fillna('N')
        
        # 4. 确保数值类型正确
        if 'Approved Tenor' in cleaned_df.columns:
            cleaned_df['Approved Tenor'] = pd.to_numeric(cleaned_df['Approved Tenor'], errors='coerce')
        
        if 'Number of invoice as of 7Oct' in cleaned_df.columns:
            cleaned_df['Number of invoice as of 7Oct'] = pd.to_numeric(cleaned_df['Number of invoice as of 7Oct'], errors='coerce')
        
        # 5. 去重（基于UID）
        if 'UID' in cleaned_df.columns:
            cleaned_df = cleaned_df.drop_duplicates(subset=['UID'], keep='last')
        
        # 6. 移除完全空的行
        cleaned_df = cleaned_df.dropna(how='all')
        
        return cleaned_df
    
    def clean_financing_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """清洗融资订单数据"""
        cleaned_df = df.copy()
        
        # 1. 处理必填字段
        required_fields = ['Finance Request Number', 'Invoice Number', 'Supplier Code', 'Buyer Code']
        for field in required_fields:
            cleaned_df = cleaned_df[cleaned_df[field].notna()]
        
        # 2. 标准化日期格式
        date_fields = [
            'Expected Funding Date', 'Request Date', 'Invoice Date', 
            'Due Date', 'Actual Shipment Date', 'Actual Funding Date'
        ]
        for field in date_fields:
            if field in cleaned_df.columns:
                cleaned_df[field] = pd.to_datetime(cleaned_df[field], errors='coerce')
        
        # 3. 标准化货币和数值字段
        currency_fields = [
            'Trade Amount', 'Financing Amount (Trade Currency)',
            'Financing Amount', 'Actual Financing Amount',
            'Interest Rate/Fee Charge', 'Exchange Rate', 'Financing Interest'
        ]
        for field in currency_fields:
            if field in cleaned_df.columns:
                cleaned_df[field] = pd.to_numeric(cleaned_df[field], errors='coerce')
        
        # 4. 标准化布尔字段
        if 'Auto Finance' in cleaned_df.columns:
            cleaned_df['Auto Finance'] = cleaned_df['Auto Finance'].str.strip().str.upper()
            cleaned_df['Auto Finance'] = cleaned_df['Auto Finance'].replace({'YES': True, 'Y': True, 'NO': False, 'N': False})
        
        # 5. 去重（基于Finance Request Number和Invoice Number）
        cleaned_df = cleaned_df.drop_duplicates(
            subset=['Finance Request Number', 'Invoice Number'], 
            keep='last'
        )
        
        # 6. 移除完全空的行
        cleaned_df = cleaned_df.dropna(how='all')
        
        return cleaned_df
    
    def clean_repayment_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """清洗还款订单数据"""
        cleaned_df = df.copy()
        
        # 1. 处理必填字段
        required_fields = ['Invoice Number', 'Finance Request Number', 'Supplier Code', 'Buyer Code']
        for field in required_fields:
            if field in cleaned_df.columns:
                cleaned_df = cleaned_df[cleaned_df[field].notna()]
        
        # 2. 标准化日期格式
        date_fields = ['Due Date', 'Actual Funding Date', 'Settlement Date']
        for field in date_fields:
            if field in cleaned_df.columns:
                cleaned_df[field] = pd.to_datetime(cleaned_df[field], errors='coerce')
        
        # 3. 标准化数值字段
        numeric_fields = [
            'Cumulative Repayment', 'To Be Recalled Amount', 'O/S Balance',
            'Total AR', 'Total Principle Amount', 'Actual Interest/Fee Charge',
            'Adjusted Interest/Charges', 'Adjusted Amount', 'Cumulative Repaid Principle',
            'O/S Principle', 'Recalled Amount', 'Interest Rate/Fee Charge'
        ]
        for field in numeric_fields:
            if field in cleaned_df.columns:
                cleaned_df[field] = pd.to_numeric(cleaned_df[field], errors='coerce')
        
        # 4. 处理grace_period字段：转换为字符串类型
        if 'Grace Period' in cleaned_df.columns:
            cleaned_df['Grace Period'] = cleaned_df['Grace Period'].astype(str)
        
        # 5. 处理po_number字段：将null值转换为空字符串
        if 'PO Number' in cleaned_df.columns:
            cleaned_df['PO Number'] = cleaned_df['PO Number'].fillna('')
        
        # 6. 去重（基于Invoice Number和Finance Request Number）
        if 'Invoice Number' in cleaned_df.columns and 'Finance Request Number' in cleaned_df.columns:
            cleaned_df = cleaned_df.drop_duplicates(
                subset=['Invoice Number', 'Finance Request Number'], 
                keep='last'
            )
        
        # 7. 移除完全空的行
        cleaned_df = cleaned_df.dropna(how='all')
        
        return cleaned_df
    
    def clean_bank_statement_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """清洗银行对账单数据"""
        cleaned_df = df.copy()
        logger.info("[清洗-银行对账单] 输入 %d 行；列名: %s", len(cleaned_df), list(cleaned_df.columns))

        # 0. 标准化列名，兼容新旧字段名
        column_aliases = {
            'Invoice Details - Discount Amount': 'Finance Details - Finance Amount',
            'Finance Details - Purchase Date':   'Finance Details - Start Date',
            'Finance Details - Finance Due Date':'Finance Details - Due Date',
            'Finance Details - Finance Status':  'Finance Details - Financing in statuses',
            'USD - Discount Amount (USD)':       'USD - Finance Amount (USD)',
        }
        for new_col, old_col in column_aliases.items():
            if new_col in cleaned_df.columns and old_col not in cleaned_df.columns:
                cleaned_df = cleaned_df.rename(columns={new_col: old_col})
                logger.info("[清洗-银行对账单] 列名映射: %s -> %s", new_col, old_col)

        # 1. 处理必填字段
        # 说明：DB Finance Ref 不再必填——拒绝/取消等未融资的发票本就没有 ref，
        # 若强制必填会把这些行全部滤掉（库里看不到拒绝数据）。主键为 System InvoiceID。
        required_fields = [
            'Invoice Details - System InvoiceID',
        ]
        for field in required_fields:
            if field not in cleaned_df.columns:
                logger.error("[清洗-银行对账单] 缺少必填列 '%s'，将抛出 KeyError（所有数据无法导入）", field)
            before = len(cleaned_df)
            cleaned_df = cleaned_df[cleaned_df[field].notna()]
            logger.info("[清洗-银行对账单] 必填字段 '%s' 非空过滤: %d -> %d 行", field, before, len(cleaned_df))

        # 2. 标准化日期格式
        date_fields = [
            'Invoice Details - Issue Date', 'Invoice Details - Due Date',
            'Invoice Details - Adjusted Due Date', 'Invoice Details - Settlement Date',
            'Invoice Details - Creation Time', 'Finance Details - Start Date',
            'Finance Details - Due Date'
        ]
        for field in date_fields:
            if field in cleaned_df.columns:
                cleaned_df[field] = pd.to_datetime(cleaned_df[field], errors='coerce')
        
        # 3. 标准化数值字段
        numeric_fields = [
            'Invoice Details - Original Amount', 'Finance Details - Finance Amount',
            'Finance Details - Outstanding Amount', 'Finance Details - Reference Rate %',
            'Finance Details - Interest Rate %', 'Finance Details - Interest Amount',
            'Finance Details - Purchase Price', 'Finance Details - Advance Ratio',
            'EUR - Original Amount (EUR)',
            'EUR - Finance Amount (EUR)', 'EUR - Outstanding Amount (EUR)',
            'EUR - Interest Amount (EUR)', 'EUR - Purchase Price (EUR)',
            'USD - Original Amount (USD)', 'USD - Finance Amount (USD)',
            'USD - Outstanding Amount (USD)', 'USD - Interest Amount (USD)',
            'USD - Purchase Price (USD)', 'Invoice Details - VAT Rate',
            'Invoice Details - VAT Amount'
        ]
        for field in numeric_fields:
            if field in cleaned_df.columns:
                cleaned_df[field] = pd.to_numeric(cleaned_df[field], errors='coerce')
        
        # 4. 去重：唯一键为 Seller Reference（入库 upsert 键）。
        #    同一 seller_reference 多行时，保留 System InvoiceID 最大的一条
        #    （拒绝旧单 id 小、替代新单 id 大 → 取最新）。
        if 'Invoice Details - Seller Reference' in cleaned_df.columns:
            before = len(cleaned_df)
            cleaned_df = cleaned_df.sort_values('Invoice Details - System InvoiceID')  # 升序，最大排最后
            cleaned_df = cleaned_df.drop_duplicates(
                subset=['Invoice Details - Seller Reference'], keep='last'
            )
            logger.info("[清洗-银行对账单] 按 seller_reference 去重(保留最大 system_invoice_id): %d -> %d 行",
                        before, len(cleaned_df))
        else:
            # 兜底：无 seller_reference 列时仍按 system_invoice_id 去重
            cleaned_df = cleaned_df.drop_duplicates(
                subset=['Invoice Details - System InvoiceID'], keep='last'
            )
        
        # 5. 移除完全空的行
        cleaned_df = cleaned_df.dropna(how='all')

        logger.info("[清洗-银行对账单] 清洗完成，输出 %d 行有效数据", len(cleaned_df))
        return cleaned_df

    def clean_financing_overview_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """清洗融资概览数据"""
        cleaned_df = df.copy()
        
        # 1. 处理必填字段
        required_fields = ['Finance Request Number', 'Invoice Number']
        for field in required_fields:
            cleaned_df = cleaned_df[cleaned_df[field].notna()]
        
        # 2. 标准化日期格式
        date_fields = ['Invoice Date', 'Due Date', 'Actual Shipment Date']
        for field in date_fields:
            if field in cleaned_df.columns:
                cleaned_df[field] = pd.to_datetime(cleaned_df[field], errors='coerce')
        
        # 3. 标准化数值字段
        numeric_fields = ['Trade Amount', 'Financing Amount', 'Expected Tenor', 'Actual Tenor']
        for field in numeric_fields:
            if field in cleaned_df.columns:
                cleaned_df[field] = pd.to_numeric(cleaned_df[field], errors='coerce')
        
        # 4. 去重（基于Finance Request Number）
        cleaned_df = cleaned_df.drop_duplicates(
            subset=['Finance Request Number'], 
            keep='last'
        )
        
        # 5. 移除完全空的行
        cleaned_df = cleaned_df.dropna(how='all')
        
        return cleaned_df
    
    def validate_record(self, record: Dict[str, Any], record_type: str) -> Dict[str, Any]:
        """验证单条记录是否符合业务规则"""
        errors = []
        warnings = []
        
        if record_type == 'onboarding':
            # 验证onboarding记录
            if not record.get('uid'):
                errors.append('UID不能为空')
            if not record.get('air8_buyer_id'):
                errors.append('Air8 Buyer ID不能为空')
            if not record.get('air8_seller_id'):
                errors.append('Air8 Seller ID不能为空')
        
        elif record_type == 'financing':
            # 验证融资订单记录
            if not record.get('finance_request_number'):
                errors.append('融资申请号不能为空')
            if not record.get('invoice_number'):
                errors.append('发票号不能为空')
            if not record.get('supplier_code'):
                errors.append('供应商代码不能为空')
            if not record.get('buyer_code'):
                errors.append('买方代码不能为空')
        
        elif record_type == 'repayment':
            # 验证还款订单记录
            if not record.get('invoice_number'):
                errors.append('发票号不能为空')
            if not record.get('finance_request_number'):
                errors.append('融资申请号不能为空')
        
        elif record_type == 'bank_statement':
            # 验证银行对账单记录
            if not record.get('invoice', {}).get('system_invoice_id'):
                errors.append('系统发票ID不能为空')
            if not record.get('finance', {}).get('db_finance_ref'):
                errors.append('DB融资参考号不能为空')
        
        elif record_type == 'financing_overview':
            # 验证融资概览记录
            if not record.get('finance_request_number'):
                errors.append('融资申请号不能为空')
            if not record.get('order_details', {}).get('invoice_number'):
                errors.append('发票号不能为空')
        
        return {
            'valid': len(errors) == 0,
            'errors': errors,
            'warnings': warnings
        }
    
    def remove_duplicates(self, records: List[Dict[str, Any]], unique_fields: List[str]) -> List[Dict[str, Any]]:
        """根据指定字段去重记录"""
        seen = set()
        unique_records = []
        
        for record in records:
            # 创建唯一标识
            key = tuple(record.get(field, '') for field in unique_fields)
            if key not in seen:
                seen.add(key)
                unique_records.append(record)
        
        return unique_records
