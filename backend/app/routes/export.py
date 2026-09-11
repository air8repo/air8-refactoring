import io
import zipfile
from flask import render_template, request, send_file, flash, redirect, url_for
from flask_login import login_required
from backend.app.routes import export_bp
from backend.app.services.export_service import ExportService
from backend.app.services.import_service import ImportService

@export_bp.route('/')
@login_required
def export_index():
    """导出页面"""
    return render_template('export.html')

@export_bp.route('/generate', methods=['POST'])
@login_required
def generate_export():
    """生成导出文件"""
    try:
        # 获取表单数据
        data_type = request.form.get('data_type')
        export_type = request.form.get('export_type')
        
        if not data_type or not export_type:
            flash('请选择数据类型和导出格式', 'error')
            return redirect(url_for('export.export_index'))
        
        # 创建导出服务实例
        export_service = ExportService()
        
        # 处理过滤条件
        filters = {}
        
        # 获取融资申请号过滤
        finance_request_number = request.form.get('finance_request_number')
        if finance_request_number:
            filters['finance_request_number'] = finance_request_number
        
        # 获取发票号过滤
        invoice_number = request.form.get('invoice_number')
        if invoice_number:
            filters['invoice_number'] = invoice_number
        
        # 获取refactoring_status过滤
        refactoring_status = request.form.get('refactoring_status')
        if refactoring_status:
            filters['refactoring_status'] = refactoring_status
        
        # 导出数据
        data = export_service.export_data(export_type, data_type, filters)
        
        if not data:
            flash('没有找到符合条件的数据', 'warning')
            return redirect(url_for('export.export_index'))
        
        # 生成文件名
        filename = export_service.get_export_filename(export_type, data_type)
        
        # 设置MIME类型
        mimetypes = {
            'csv': 'text/csv',
            'excel': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'pdf': 'application/pdf'
        }
        
        return send_file(
            io.BytesIO(data),
            mimetype=mimetypes[export_type],
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        flash(f'导出过程中发生错误: {str(e)}', 'error')
        return redirect(url_for('export.export_index'))

@export_bp.route('/generate_db_loan_file', methods=['POST'])
@login_required
def generate_db_loan_file():
    """生成DB放款文件"""
    try:
        # 先刷新融资单数据，确保最新
        ImportService().refresh_all_financing_records()

        # 获取表单数据
        batch_date = request.form.get('batch_date')
        
        if not batch_date:
            flash('请选择批次日期', 'error')
            return redirect(url_for('export.export_index'))
        
        # 创建导出服务实例
        export_service = ExportService()
        
        # 获取银行渠道参数
        bank_channel = request.form.get('bank_channel', 'db')
        
        # 生成DB放款文件
        zip_data = export_service.generate_db_loan_file(batch_date, bank_channel)
        
        if not zip_data:
            flash('没有找到符合条件的数据', 'warning')
            return redirect(url_for('export.export_index'))
        
        # 生成文件名
        filename = f'db_loan_files_{batch_date.replace("-", "")}.zip'
        
        return send_file(
            io.BytesIO(zip_data),
            mimetype='application/zip',
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        flash(f'生成DB放款文件时发生错误: {str(e)}', 'error')
        return redirect(url_for('export.export_index'))

@export_bp.route('/generate_db_repayment_file', methods=['POST'])
@login_required
def generate_db_repayment_file():
    """生成DB还款文件"""
    try:
        # 先刷新融资单数据，确保最新
        ImportService().refresh_all_financing_records()

        # 获取表单数据
        repayment_date = request.form.get('repayment_date')
        
        if not repayment_date:
            flash('请选择还款日期', 'error')
            return redirect(url_for('export.export_index'))
        
        # 创建导出服务实例
        export_service = ExportService()
        
        # 获取银行渠道参数
        bank_channel = request.form.get('bank_channel', 'db')
        
        # 生成DB还款文件
        zip_data = export_service.generate_db_repayment_file(repayment_date, bank_channel)
        
        if not zip_data:
            flash('没有找到符合条件的数据', 'warning')
            return redirect(url_for('export.export_index'))
        
        # 生成文件名
        filename = f'db_repayment_files_{repayment_date.replace("-", "")}.zip'
        
        return send_file(
            io.BytesIO(zip_data),
            mimetype='application/zip',
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        flash(f'生成DB还款文件时发生错误: {str(e)}', 'error')
        return redirect(url_for('export.export_index'))

@export_bp.route('/refresh-financing-orders', methods=['POST'])
@login_required
def refresh_financing_orders():
    """刷新融资单"""
    try:
        # 创建ImportService实例
        import_service = ImportService()
        
        # 调用刷新方法
        result = import_service.refresh_all_financing_records()
        
        if result['success']:
            # 如果有message字段，使用该字段，否则使用默认消息
            message = result.get('message', '刷新融资单成功')
            flash(message, 'success')
        else:
            # 如果有message字段，使用该字段，否则使用默认消息
            message = result.get('message', '刷新融资单失败，请稍后重试')
            flash(message, 'error')
            
    except Exception as e:
        flash(f'刷新融资单时发生错误: {str(e)}', 'error')
        
    # 重定向回导出页面
    return redirect(url_for('export.export_index'))

@export_bp.route('/update_overview', methods=['POST'])
@login_required
def update_overview():
    """更新融资概览数据"""
    try:
        from backend.app.services.aggregate_service import AggregateService
        
        aggregate_service = AggregateService()
        result = aggregate_service.aggregate_financing_overview()
        
        if result['success']:
            flash(f'成功更新 {result.get("count", 0)} 条融资概览记录', 'success')
        else:
            # 如果有message字段，使用该字段，否则使用默认消息
            message = result.get('message', '更新融资概览数据失败，请稍后重试')
            flash(f'更新融资概览数据时发生错误: {message}', 'error')
    except Exception as e:
        flash(f'更新融资概览数据时发生错误: {str(e)}', 'error')
    
    return redirect(url_for('export.export_index'))
