import pandas as pd
import io
from datetime import datetime
from typing import List, Dict, Any
from flask import current_app

def get_mongo():
    """获取已初始化的mongo对象"""
    mongo = None
    
    # 首先尝试直接从extensions模块导入（最高优先级，适合测试环境）
    try:
        from backend.app.extensions import mongo as ext_mongo
        if ext_mongo is not None:
            return ext_mongo
    except Exception:
        pass
    
    # 然后尝试从app模块导入
    try:
        from backend.app import mongo as app_mongo
        if app_mongo is not None:
            return app_mongo
    except Exception:
        pass
    
    # 最后尝试从current_app.extensions获取（适合运行环境）
    try:
        if hasattr(current_app, 'extensions'):
            mongo = current_app.extensions.get('mongo')
            if mongo is not None:
                return mongo
    except Exception:
        pass
    
    return None

class ExportService:
    """数据导出服务"""
    
    def export_data(self, export_type: str, data_type: str, filters: Dict[str, Any] = None) -> bytes:
        """导出数据
        
        Args:
            export_type: 导出格式 (csv, excel, pdf)
            data_type: 数据类型 (financing, repayment, overview, statement)
            filters: 过滤条件
        
        Returns:
            bytes: 导出的数据
        """
        data = self._get_data(data_type, filters)
        
        if not data:
            return b''
        
        if export_type == 'csv':
            return self._export_to_csv(data, data_type)
        elif export_type == 'excel':
            return self._export_to_excel(data, data_type)
        elif export_type == 'pdf':
            return self._export_to_pdf(data, data_type)
        else:
            raise ValueError(f'不支持的导出格式: {export_type}')
    
    def _get_data(self, data_type: str, filters: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """根据数据类型获取数据"""
        mongo = get_mongo()
        if mongo is None:
            return []
        
        filters = filters or {}
        
        if data_type == 'financing':
            return list(mongo.refactoring_financing_order.find(filters))
        elif data_type == 'repayment':
            return list(mongo.refactoring_repayment_order.find(filters))
        elif data_type == 'statement':
            return list(mongo.refactoring_bank_statement.find(filters))
        elif data_type == 'overview':
            return list(mongo.refactoring_financing_overview.find(filters))
        else:
            raise ValueError(f'不支持的数据类型: {data_type}')
    
    def _export_to_csv(self, data: List[Dict[str, Any]], data_type: str) -> bytes:
        """导出为CSV格式"""
        df = pd.DataFrame(data)
        
        if '_id' in df.columns:
            df = df.drop('_id', axis=1)
        
        for col in df.columns:
            if pd.api.types.is_datetime64_any_dtype(df[col]):
                df[col] = df[col].apply(lambda x: x.strftime('%Y-%m-%d') if pd.notna(x) else '')
        
        output = io.BytesIO()
        df.to_csv(output, index=False, encoding='utf-8-sig')
        output.seek(0)
        
        return output.getvalue()
    
    def _transform_overview_data(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """转换overview数据，将嵌套结构转换为扁平格式，符合用户要求的表头"""
        # 定义表头与MongoDB字段的映射关系，严格按照用户要求的顺序
        header_mapping = [
            # Loan submission Batch - 第2列
            ('Loan submission Batch', 'loan_submission_batch'),
            # FR# - 第3列
            ('FR#', 'finance_request_number'),
            # Air8 Finance amt - 第4列
            ('Air8 Finance amt', 'order_details.air8_finance_amt'),
            # Invoice Details - Buyer Reference - 第5列
            ('Invoice Details - Buyer Reference', 'bank_statements.0.invoice_seller_reference'),
            # Invoice Details - Seller Reference - 第6列
            ('Invoice Details - Seller Reference', 'bank_statements.0.invoice_seller_reference'),
            # Parties Details - Seller ERP ID - 第7列
            ('Parties Details - Seller ERP ID', 'bank_statements.0.parties_seller_erp_id'),
            # Parties Details - Buyer ERP ID - 第8列
            ('Parties Details - Buyer ERP ID', 'bank_statements.0.parties_buyer_erp_id'),
            # Parties Details - Buyer Name - 第9列
            ('Parties Details - Buyer Name', 'bank_statements.0.parties_buyer_name'),
            # Parties Details - Seller Name - 第10列
            ('Parties Details - Seller Name', 'bank_statements.0.parties_seller_name'),
            # Invoice Details - Issue Date - 第11列
            ('Invoice Details - Issue Date', 'bank_statements.0.invoice_issue_date'),
            # Invoice Details - Due Date - 第12列
            ('Invoice Details - Due Date', 'bank_statements.0.invoice_due_date'),
            # Invoice Details - Adjusted Due Date - 第13列
            ('Invoice Details - Adjusted Due Date', 'bank_statements.0.invoice_adjusted_due_date'),
            # Finance Details - Start Date - 第14列
            ('Finance Details - Start Date', 'bank_statements.0.start_date'),
            # Finance Details - Due Date - 第15列
            ('Finance Details - Due Date', 'bank_statements.0.finance_due_date'),
            # Invoice Details - Currency - 第16列
            ('Invoice Details - Currency', 'bank_statements.0.invoice_currency'),
            # Invoice Details - Original Amount - 第17列
            ('Invoice Details - Original Amount', 'bank_statements.0.invoice_original_amount'),
            # USD - Finance Amount (USD) - 第18列
            ('USD - Finance Amount (USD)', 'bank_statements.0.usd_finance_amount'),
            # USD - Interest Amount (USD) - 第19列
            ('USD - Interest Amount (USD)', 'bank_statements.0.usd_interest_amount'),
            # USD - Purchase Price (USD) - 第20列
            ('USD - Purchase Price (USD)', 'bank_statements.0.usd_purchase_price'),
            # Finance Details - Interest Rate % - 第21列
            ('Finance Details - Interest Rate %', 'bank_statements.0.interest_rate_pct'),
            # USD - Outstanding Amount (USD) - 第22列
            ('USD - Outstanding Amount (USD)', 'bank_statements.0.usd_outstanding_amount'),
            # Finance Details - Financing in statuses - 第23列
            ('Finance Details - Financing in statuses', 'bank_statements.0.finance.status'),
            # Settled in Air8 - 第24列
            ('Settled in Air8', 'settled_in_air8'),
            # FR Settlement date - 第25列
            ('FR Settlement date', 'order_details.fr_settlement_date'),
            # Invoice Details - Settlement Date - 第26列
            ('Invoice Details - Settlement Date', 'bank_statements.0.invoice_settlement_date'),
            # DB loan settle date (Air8 upload date) - 第27列
            ('DB loan settle date (Air8 upload date)', 'db_loan_settle_date'),
            # Invoice Details - Settlement Date (DB updated date) - 第28列
            ('Invoice Details - Settlement Date (DB updated date)', 'bank_statements.0.invoice_settlement_date'),
            # Overdue interest (for settled case)  - WIP - 第29列
            ('Overdue interest (for settled case)  - WIP', 'totals.overdue_interest_settled_wip'),
            # Overdue interest (for od case) - WIP - 第30列
            ('Overdue interest (for od case) - WIP', 'totals.overdue_interest_od_wip'),
            # Air8 Settled FR amt - 第31列
            ('Air8 Settled FR amt', 'air8_settled_fr_amt'),
            # Settled DB loan - 第32列
            ('Settled DB loan', 'settled_db_loan'),
            # Oustanding loan (DB fund to Air8) excluded WIP settlement - 第33列
            ('Oustanding loan (DB fund to Air8) excluded WIP settlement', 'outstanding_loan_exclude_wip'),
            # WIP / Pending (DB o/s) - 第34列
            ('WIP / Pending (DB o/s)', 'wip_pending_amount'),
            # Parties Details - Buyer Name.1 - 第35列
            ('Parties Details - Buyer Name.1', 'bank_statements.0.parties_buyer_name'),
            # Parties Details - Seller Name.1 - 第36列
            ('Parties Details - Seller Name.1', 'bank_statements.0.parties_seller_name'),
            # Parties Details - Buyer ERP ID.1 - 第37列
            ('Parties Details - Buyer ERP ID.1', 'bank_statements.0.parties_buyer_erp_id'),
            # Parties Details - Seller ERP ID.1 - 第38列
            ('Parties Details - Seller ERP ID.1', 'bank_statements.0.parties_seller_erp_id'),
            # Invoice Details - System InvoiceID - 第39列
            ('Invoice Details - System InvoiceID', 'bank_statements.0.system_invoice_id'),
            # Invoice Details - Status - 第40列
            ('Invoice Details - Status', 'bank_statements.0.invoice_status'),
            # Invoice Details - Validation Status Reason - 第41列
            ('Invoice Details - Validation Status Reason', ''),
            # Invoice Details - Issue Date.1 - 第42列（重复）
            ('Invoice Details - Issue Date.1', 'bank_statements.0.invoice_issue_date'),
            # Invoice Details - Due Date.1 - 第43列（重复）
            ('Invoice Details - Due Date.1', 'bank_statements.0.invoice_due_date'),
            # Invoice Details - Adjusted Due Date.1 - 第44列（重复）
            ('Invoice Details - Adjusted Due Date.1', 'bank_statements.0.invoice_adjusted_due_date'),
            # Invoice Details - Buyer Reference.1 - 第45列（重复）
            ('Invoice Details - Buyer Reference.1', 'bank_statements.0.invoice_buyer_reference'),
            # Invoice Details - Seller Reference.1 - 第46列（重复）
            ('Invoice Details - Seller Reference.1', 'bank_statements.0.invoice_seller_reference'),
            # Invoice Details - Currency.1 - 第47列（重复）
            ('Invoice Details - Currency.1', 'bank_statements.0.invoice_currency'),
            # Invoice Details - Original Amount.1 - 第48列（重复）
            ('Invoice Details - Original Amount.1', 'bank_statements.0.invoice_original_amount'),
            # Invoice Details - Settlement Date.1 - 第49列（重复）
            ('Invoice Details - Settlement Date.1', 'bank_statements.0.invoice_settlement_date'),
            # Invoice Details - Creation Time - 第46列
            ('Invoice Details - Creation Time', 'bank_statements.0.invoice_creation_time'),
            # Invoice Details - VAT Rate - 第47列
            ('Invoice Details - VAT Rate', 'bank_statements.0.invoice_vat_rate'),
            # Invoice Details - VAT Amount - 第52列
            ('Invoice Details - VAT Amount', 'bank_statements.0.invoice_vat_amount'),
            # Finance Details - Financing in statuses.1 - 第53列（重复）
            ('Finance Details - Financing in statuses.1', 'bank_statements.0.finance.status'),
            # Finance Details - DB Finance Ref. - 第54列
            ('Finance Details - DB Finance Ref.', 'bank_statements.0.db_finance_ref'),
            # Finance Details - Start Date.1 - 第55列（重复）
            ('Finance Details - Start Date.1', 'bank_statements.0.start_date'),
            # Finance Details - Due Date.1 - 第56列（重复）
            ('Finance Details - Due Date.1', 'bank_statements.0.finance_due_date'),
            # Finance Details - Tenor - 第57列
            ('Finance Details - Tenor', 'bank_statements.0.tenor'),
            # Finance Details - Finance Amount - 第58列
            ('Finance Details - Finance Amount', 'bank_statements.0.finance_amount'),
            # Finance Details - Outstanding Amount - 第59列
            ('Finance Details - Outstanding Amount', 'bank_statements.0.outstanding_amount'),
            # Finance Details - Interest Rate %.1 - 第60列（重复）
            ('Finance Details - Interest Rate %.1', 'bank_statements.0.interest_rate_pct'),
            # Finance Details - Interest Amount - 第61列
            ('Finance Details - Interest Amount', 'bank_statements.0.interest_amount'),
            # Finance Details - Purchase Price - 第62列
            ('Finance Details - Purchase Price', 'bank_statements.0.purchase_price'),
            # USD - Original Amount (USD) - 第63列
            ('USD - Original Amount (USD)', 'bank_statements.0.usd_original_amount'),
            # USD - Finance Amount (USD).1 - 第64列（重复）
            ('USD - Finance Amount (USD).1', 'bank_statements.0.usd_finance_amount'),
            # USD - Outstanding Amount (USD).1 - 第65列（重复）
            ('USD - Outstanding Amount (USD).1', 'bank_statements.0.usd_outstanding_amount'),
            # USD - Interest Amount (USD).1 - 第66列（重复）
            ('USD - Interest Amount (USD).1', 'bank_statements.0.usd_interest_amount'),
            # USD - Purchase Price (USD).1 - 第67列（重复）
            ('USD - Purchase Price (USD).1', 'bank_statements.0.usd_purchase_price')
        ]
        
        # 安全获取嵌套字段的值
        def get_nested_value(data: Dict, path: str):
            """获取嵌套字段的值"""
            if not path:
                return ''
            
            keys = path.split('.')
            value = data
            
            for key in keys:
                # 处理数组索引
                if key.isdigit():
                    index = int(key)
                    if isinstance(value, list) and len(value) > index:
                        value = value[index]
                    else:
                        return ''
                else:
                    if isinstance(value, dict) and key in value:
                        value = value[key]
                    else:
                        return ''
            
            return value
        
        # 转换Decimal128到float
        def safe_convert(value):
            """安全转换数值类型"""
            from bson import Decimal128
            import numpy as np
            
            # 处理NaN值
            if isinstance(value, (float, np.float64)) and np.isnan(value):
                return ''
            
            if isinstance(value, Decimal128):
                return float(value.to_decimal())
            if isinstance(value, (int, float)):
                return value
            if isinstance(value, str):
                try:
                    return float(value)
                except ValueError:
                    return value
            return value
        
        # 格式化日期
        def format_date(date):
            """格式化日期为DD-MMM-YY格式"""
            import numpy as np
            
            # 处理空值
            if date is None or (isinstance(date, (float, np.float64)) and np.isnan(date)):
                return ''
            
            if isinstance(date, datetime):
                return date.strftime('%d-%b-%y').upper()
            elif isinstance(date, str):
                try:
                    # 尝试解析字符串日期
                    parsed_date = datetime.strptime(date, '%Y-%m-%d')
                    return parsed_date.strftime('%d-%b-%y').upper()
                except ValueError:
                    # 尝试解析其他格式
                    try:
                        from dateutil.parser import parse
                        parsed_date = parse(date)
                        return parsed_date.strftime('%d-%b-%y').upper()
                    except (ValueError, ImportError):
                        # 如果解析失败，保持原样
                        return date
            return date
        
        transformed_data = []
        
        for idx, item in enumerate(data):
            row = {}
            
            # 添加Seq. 序列号
            row['Seq.'] = idx + 1
            
            # 映射其他字段
            for header, field_path in header_mapping:
                value = get_nested_value(item, field_path)
                
                # 转换数值（包括Decimal128）
                from bson import Decimal128
                import numpy as np
                
                # 特殊处理：确保Original Amount相关字段被识别为数值，避免被当作日期处理
                if 'Original Amount' in header:
                    # 强制转换为数值
                    value = safe_convert(value)
                # 转换普通数值字段
                elif isinstance(value, (int, float, Decimal128)) or (isinstance(value, str) and value.replace('.', '').isdigit()):
                    value = safe_convert(value)
                # 格式化日期字段 - 确保所有包含Date的字段都使用相同格式
                elif 'Date' in header:
                    # 如果是字符串日期，尝试解析后格式化
                    if isinstance(value, str):
                        try:
                            parsed_date = datetime.strptime(value, '%Y-%m-%d')
                            value = format_date(parsed_date)
                        except ValueError:
                            try:
                                from dateutil.parser import parse
                                parsed_date = parse(value)
                                value = format_date(parsed_date)
                            except (ValueError, ImportError):
                                # 如果解析失败，保持原样
                                pass
                    # 如果是datetime对象，直接格式化
                    elif isinstance(value, datetime):
                        value = format_date(value)
                    # 如果是Timestamp对象（来自pandas），转换后格式化
                    elif hasattr(value, 'to_pydatetime'):
                        value = format_date(value.to_pydatetime())
                # 处理其他空值
                elif value is None or (isinstance(value, (float, np.float64)) and np.isnan(value)):
                    value = ''
                
                row[header] = value
            
            transformed_data.append(row)
        
        return transformed_data
    
    def _export_to_excel(self, data: List[Dict[str, Any]], data_type: str) -> bytes:
        """导出为Excel格式"""
        # 如果是overview数据，进行转换
        if data_type == 'overview' and data:
            data = self._transform_overview_data(data)
        
        df = pd.DataFrame(data)
        
        if '_id' in df.columns:
            df = df.drop('_id', axis=1)
        
        # 处理日期列
        for col in df.columns:
            if pd.api.types.is_datetime64_any_dtype(df[col]):
                df[col] = df[col].fillna(pd.NaT)
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name=data_type.capitalize(), index=False)
            
            # 获取workbook和worksheet对象
            workbook = writer.book
            worksheet = writer.sheets[data_type.capitalize()]
            
            # 应用样式
            self._set_excel_styles(worksheet)
        output.seek(0)
        
        return output.getvalue()
    
    def _export_to_pdf(self, data: List[Dict[str, Any]], data_type: str) -> bytes:
        """导出为PDF格式"""
        df = pd.DataFrame(data)
        
        if '_id' in df.columns:
            df = df.drop('_id', axis=1)
        
        for col in df.columns:
            if pd.api.types.is_datetime64_any_dtype(df[col]):
                df[col] = df[col].apply(lambda x: x.strftime('%Y-%m-%d') if pd.notna(x) else '')
        
        from reportlab.lib.pagesizes import letter
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
        from reportlab.lib import colors
        from reportlab.platypus import Paragraph
        from reportlab.lib.styles import getSampleStyleSheet
        
        output = io.BytesIO()
        doc = SimpleDocTemplate(output, pagesize=letter)
        
        elements = []
        styles = getSampleStyleSheet()
        title = Paragraph(f'{data_type.capitalize()} Report', styles['Title'])
        elements.append(title)
        
        date_text = f'Report generated on: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}'
        elements.append(Paragraph(date_text, styles['Normal']))
        
        table_data = [df.columns.tolist()] + df.values.tolist()
        table = Table(table_data)
        
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        
        elements.append(table)
        doc.build(elements)
        output.seek(0)
        
        return output.getvalue()
    
    def get_export_filename(self, export_type: str, data_type: str) -> str:
        """生成导出文件名"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        extension = {
            'csv': '.csv',
            'excel': '.xlsx',
            'pdf': '.pdf'
        }[export_type]
        
        return f'refactoring_{data_type}_{timestamp}{extension}'
    
    def _set_excel_styles(self, worksheet):
        """设置Excel样式"""
        from openpyxl.styles import Font, PatternFill, Border, Side, Alignment
        
        # 设置header样式
        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="4F81BD", end_color="4F81BD", fill_type="solid")
        header_border = Border(left=Side(style='thin'), right=Side(style='thin'), 
                              top=Side(style='thin'), bottom=Side(style='thin'))
        header_alignment = Alignment(horizontal="center", vertical="center")
        
        # 应用header样式
        for cell in worksheet[1]:
            cell.font = header_font
            cell.fill = header_fill
            cell.border = header_border
            cell.alignment = header_alignment
        
        # 设置数据行样式
        data_border = Border(left=Side(style='thin'), right=Side(style='thin'), 
                            top=Side(style='thin'), bottom=Side(style='thin'))
        data_alignment = Alignment(horizontal="left", vertical="center")
        
        for row in worksheet.iter_rows(min_row=2):
            for cell in row:
                cell.border = data_border
                cell.alignment = data_alignment
        
        # 调整列宽
        for column_cells in worksheet.columns:
            length = max(len(str(cell.value)) for cell in column_cells)
            worksheet.column_dimensions[column_cells[0].column_letter].width = length + 2
    
    def generate_db_loan_file(self, batch_date: str, bank_channel: str = 'db') -> bytes:
        """生成DB放款文件"""
        import zipfile
        
        mongo = get_mongo()
        if mongo is None:
            return b''
        
        # 1. 获取下一个批次号（整数类型）
        batch_number = self._get_next_batch_number()
        
        # 2. 筛选符合条件的融资订单
        financing_orders = list(mongo.refactoring_financing_order.find({'can_push_to_db_today': True}))
        
        if not financing_orders:
            return b''
        
        # 3. 更新这些融资订单的批次相关字段
        current_time = datetime.now()
        finance_request_numbers = [order['finance_request_number'] for order in financing_orders]
        
        update_result = mongo.refactoring_financing_order.update_many(
            {'finance_request_number': {'$in': finance_request_numbers}},
            {'$set': {
                'batch_number': batch_number,
                'batch_status': 'active',
                'batch_created_at': current_time,
                'bank_source': bank_channel,
                'updated_at': current_time
            }}
        )
        
        # 4. 使用更新后的订单数据生成DB文件
        df = pd.DataFrame(financing_orders)
        
        processed_data = []
        for _, row in df.iterrows():
            invoice_date = row.get('invoice_date')
            due_date = row.get('due_date')
            
            invoice_date_str = invoice_date.strftime('%Y%m%d') if pd.notna(invoice_date) else ''
            due_date_str = due_date.strftime('%Y%m%d') if pd.notna(due_date) else ''
            
            trade_currency = row.get('trade_currency', '')
            currency = 'USD' if trade_currency == 'USD' else 'CCY issue'
            
            trade_amount = row.get('trade_amount', 0)
            if hasattr(trade_amount, 'to_decimal'):
                trade_amount = trade_amount.to_decimal()
            
            processed_data.append({
                'Record Type': 'INV',
                'Seller Name': row.get('supplier_code', ''),
                'Seller ERP ID': '',
                'Buyer': row.get('buyer_code', ''),
                'Seller Reference': row.get('invoice_number', ''),
                'Invoice Date': invoice_date_str,
                'Maturity Date': due_date_str,
                'Currency': currency,
                'Amount': trade_amount,
                'Supplier Name': row.get('supplier_name', '')
            })
        
        processed_df = pd.DataFrame(processed_data)
        summary_df = processed_df.copy()
        
        ft_row = {
            'Record Type': 'FT',
            'Seller Name': str(len(summary_df)),
            'Seller ERP ID': summary_df['Amount'].sum(),
            'Buyer': '',
            'Seller Reference': '',
            'Invoice Date': '',
            'Maturity Date': '',
            'Currency': '',
            'Amount': '',
            'Supplier Name': ''
        }
        
        summary_df = pd.concat([summary_df, pd.DataFrame([ft_row])], ignore_index=True)
        
        zip_buffer = io.BytesIO()
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            formatted_date = batch_date.split('-')[2] + '-' + batch_date.split('-')[1] + '-' + batch_date.split('-')[0]
            
            summary_file_name = f'{batch_number} lot {formatted_date}_Summary.xlsx'
            summary_excel_buffer = io.BytesIO()
            with pd.ExcelWriter(summary_excel_buffer, engine='openpyxl') as writer:
                summary_df.drop(columns=['Supplier Name']).to_excel(writer, sheet_name='Summary', index=False)
                
                # 获取workbook和worksheet对象
                workbook = writer.book
                worksheet = writer.sheets['Summary']
                
                # 设置样式
                self._set_excel_styles(worksheet)
            summary_excel_buffer.seek(0)
            zip_file.writestr(summary_file_name, summary_excel_buffer.getvalue())
            
            supplier_groups = processed_df.groupby('Supplier Name')
            
            for supplier_name, group_df in supplier_groups:
                supplier_ft_row = {
                    'Record Type': 'FT',
                    'Seller Name': str(len(group_df)),
                    'Seller ERP ID': group_df['Amount'].sum(),
                    'Buyer': '',
                    'Seller Reference': '',
                    'Invoice Date': '',
                    'Maturity Date': '',
                    'Currency': '',
                    'Amount': '',
                    'Supplier Name': ''
                }
                
                supplier_with_ft = pd.concat([group_df, pd.DataFrame([supplier_ft_row])], ignore_index=True)
                
                supplier_file_name = f'{batch_number} lot {formatted_date}_{supplier_name}.xlsx'
                supplier_excel_buffer = io.BytesIO()
                with pd.ExcelWriter(supplier_excel_buffer, engine='openpyxl') as writer:
                    supplier_with_ft.drop(columns=['Supplier Name']).to_excel(writer, sheet_name=supplier_name, index=False)
                    
                    # 获取workbook和worksheet对象
                    workbook = writer.book
                    worksheet = writer.sheets[supplier_name]
                    
                    # 设置样式
                    self._set_excel_styles(worksheet)
                supplier_excel_buffer.seek(0)
                zip_file.writestr(supplier_file_name, supplier_excel_buffer.getvalue())
        
        zip_buffer.seek(0)
        return zip_buffer.getvalue()
    
    def _get_next_batch_number(self) -> int:
        """获取下一个批次号，返回整数类型"""
        mongo = get_mongo()
        if mongo is None:
            return 1
        
        # 从融资订单表中获取最大批次号，只考虑active状态的批次
        result = mongo.refactoring_financing_order.aggregate([
            {'$match': {'batch_status': 'active'}},  # 只考虑有效批次
            {'$group': {'_id': None, 'max_batch': {'$max': '$batch_number'}}}
        ])
        
        max_batch = 0
        for item in result:
            max_batch = item.get('max_batch', 0)
            break
        
        max_batch = int(max_batch) if max_batch is not None else 0
        
        # 生成下一个批次号
        next_batch = max_batch + 1
        
        return next_batch
    
    def generate_db_repayment_file(self, repayment_date: str, bank_channel: str = 'db') -> bytes:
        """生成DB还款文件"""
        import zipfile
        
        mongo = get_mongo()
        if mongo is None:
            return b''
        
        # 解析还款日期
        repayment_date_obj = datetime.strptime(repayment_date, '%Y-%m-%d')
        repayment_date_str = repayment_date.replace('-', '')
        
        # 1. 从融资单表中过滤WIP / Pending>0且DB loan settle date为空或null的数据
        # 首先查询符合条件的数据
        filter_conditions = {
            'wip_pending': {'$gt': 0},  # WIP / Pending > 0
            'db_loan_settle_date': {'$in': [None, '']},  # DB loan settle date为空或null
            'bank_finance_status': 'Loan booked'  # 银行放款状态为Loan booked
        }
        financing_orders = list(mongo.refactoring_financing_order.find(filter_conditions))
        
        if not financing_orders:
            return b''
        
        # 2. 将DB loan settle date设置为输入的日期
        current_time = datetime.now()
        finance_request_numbers = [order['finance_request_number'] for order in financing_orders]
        
        update_result = mongo.refactoring_financing_order.update_many(
            {'finance_request_number': {'$in': finance_request_numbers}},
            {'$set': {
                'db_loan_settle_date': repayment_date_obj,
                'updated_at': current_time
            }}
        )
        
        # 3. 再次筛选：WIP / Pending>0且DB loan settle date=输入日期的数据
        filter_conditions = {
            'wip_pending': {'$gt': 0},  # WIP / Pending > 0
            'db_loan_settle_date': repayment_date_obj,  # DB loan settle date=输入日期
            'bank_finance_status': 'Loan booked'  # 银行放款状态为Loan booked
        }
        filtered_orders = list(mongo.refactoring_financing_order.find(filter_conditions))
        
        if not filtered_orders:
            return b''
        
        # 4. 生成还款文件数据
        processed_data = []
        repayment_records = []
        
        for order in filtered_orders:
            # 获取关联的bank_statement数据
            invoice_number = order.get('invoice_number', '')
            bank_statement = mongo.refactoring_bank_statement.find_one(
                {'invoice.seller_reference': invoice_number}
            )
            
            # 提取所需字段
            seller_name = order.get('supplier_code', '')  # 供应商code
            seller_erp_id = ''  # 默认空
            
            # 从bank_statement获取发票相关信息
            invoice_issue_date = ''
            invoice_due_date = ''
            invoice_currency = ''
            invoice_original_amount = 0
            
            if bank_statement:
                invoice_details = bank_statement.get('invoice', {})
                invoice_issue_date = invoice_details.get('issue_date', '')
                invoice_due_date = invoice_details.get('due_date', '')
                invoice_currency = invoice_details.get('currency', '')
                invoice_original_amount = invoice_details.get('original_amount', 0)
                
                # 格式化日期
                if isinstance(invoice_issue_date, datetime):
                    invoice_issue_date = invoice_issue_date.strftime('%Y%m%d')
                if isinstance(invoice_due_date, datetime):
                    invoice_due_date = invoice_due_date.strftime('%Y%m%d')
            
            # 计算Settlement Amount
            settled_in_air8 = order.get('settled_in_air8') or ''
            if settled_in_air8.lower() == 'settled':
                settlement_amount = invoice_original_amount
            else:
                settlement_amount = 'Pending for settlement'
            
            # 格式化Settlement Date
            settlement_date = repayment_date_obj.strftime('%Y%m%d')
            
            # 供应商名称
            supplier_name = order.get('supplier_name', '')
            
            # 买家code
            buyer = order.get('buyer_code', '')
            
            # 构建处理后的数据
            processed_row = {
                'Seller Name': seller_name,
                'Seller ERP ID': seller_erp_id,
                'Buyer': buyer,
                'Seller Reference': invoice_number,
                'Invoice Date': invoice_issue_date,
                'Maturity Date': invoice_due_date,
                'Currency': invoice_currency,
                'Amount': invoice_original_amount,
                'Settlement Amount': settlement_amount,
                'Settlement Date': settlement_date,
                'supplier': supplier_name
            }
            
            processed_data.append(processed_row)
            
            # 构建还款批次记录（打平格式，冗余批次号）
            repayment_record = {
                'batch_date': repayment_date,
                'bank_channel': bank_channel,
                'batch_status': 'active',
                'seller_name': seller_name,
                'seller_erp_id': seller_erp_id,
                'buyer_name': buyer,
                'seller_reference': invoice_number,
                'invoice_date': invoice_issue_date,
                'maturity_date': invoice_due_date,
                'currency': invoice_currency,
                'amount': invoice_original_amount,
                'settlement_amount': settlement_amount,
                'settlement_date': settlement_date,
                'supplier': supplier_name,
                'finance_request_number': order.get('finance_request_number', ''),
                'created_at': current_time,
                'updated_at': current_time
            }
            
            repayment_records.append(repayment_record)
        
        # 5. 将还款批次记录保存到数据库
        if repayment_records:
            mongo.refactoring_bank_repayment_record.insert_many(repayment_records)
        
        # 6. 生成Excel文件并打包
        df = pd.DataFrame(processed_data)
        
        zip_buffer = io.BytesIO()
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            # 生成汇总文件
            all_file_name = f'all_{repayment_date_str}.xlsx'
            all_excel_buffer = io.BytesIO()
            with pd.ExcelWriter(all_excel_buffer, engine='openpyxl') as writer:
                df.drop(columns=['supplier']).to_excel(writer, sheet_name='All', index=False)
                
                # 获取workbook和worksheet对象
                workbook = writer.book
                worksheet = writer.sheets['All']
                
                # 设置样式
                self._set_excel_styles(worksheet)
            all_excel_buffer.seek(0)
            zip_file.writestr(all_file_name, all_excel_buffer.getvalue())
            
            # 按供应商分组生成文件
            supplier_groups = df.groupby('supplier')
            
            for supplier_name, group_df in supplier_groups:
                supplier_file_name = f'{supplier_name}_{repayment_date_str}.xlsx'
                supplier_excel_buffer = io.BytesIO()
                with pd.ExcelWriter(supplier_excel_buffer, engine='openpyxl') as writer:
                    group_df.drop(columns=['supplier']).to_excel(writer, sheet_name=supplier_name, index=False)
                    
                    # 获取workbook和worksheet对象
                    workbook = writer.book
                    worksheet = writer.sheets[supplier_name]
                    
                    # 设置样式
                    self._set_excel_styles(worksheet)
                supplier_excel_buffer.seek(0)
                zip_file.writestr(supplier_file_name, supplier_excel_buffer.getvalue())
        
        zip_buffer.seek(0)
        return zip_buffer.getvalue()
