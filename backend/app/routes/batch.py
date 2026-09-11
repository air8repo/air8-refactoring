from flask import jsonify, request
from flask_login import login_required
from backend.app.routes import batch_bp
from backend.app.services.batch_service import BatchService

@batch_bp.route('/api/batches', methods=['GET'])
@login_required
def get_all_batches():
    """获取所有批次号信息"""
    try:
        batch_service = BatchService()
        batches = batch_service.get_all_batches()
        return jsonify({
            'code': 0,
            'msg': 'success',
            'data': batches
        })
    except Exception as e:
        return jsonify({
            'code': 1,
            'msg': f'获取批次列表失败: {str(e)}',
            'data': []
        })

@batch_bp.route('/api/batches/<int:batch_number>', methods=['GET'])
@login_required
def get_batch(batch_number):
    """获取特定批次的详细信息"""
    try:
        batch_service = BatchService()
        batch = batch_service.get_batch_by_number(batch_number)
        if batch:
            return jsonify({
                'code': 0,
                'msg': 'success',
                'data': batch
            })
        else:
            return jsonify({
                'code': 1,
                'msg': f'批次号 {batch_number} 不存在',
                'data': {}
            })
    except Exception as e:
        return jsonify({
            'code': 1,
            'msg': f'获取批次详情失败: {str(e)}',
            'data': {}
        })

@batch_bp.route('/api/batches/<int:batch_number>/cancel', methods=['PUT'])
@login_required
def cancel_batch(batch_number):
    """作废指定批次号"""
    try:
        batch_service = BatchService()
        result = batch_service.cancel_batch(batch_number)
        if result['success']:
            return jsonify({
                'code': 0,
                'msg': result['message'],
                'data': {
                    'updated_count': result['updated_count'],
                    'aggregate_result': result['aggregate_result']
                }
            })
        else:
            return jsonify({
                'code': 1,
                'msg': result['message'],
                'data': {}
            })
    except Exception as e:
        return jsonify({
            'code': 1,
            'msg': f'作废批次失败: {str(e)}',
            'data': {}
        })

@batch_bp.route('/api/batches/by-fr/<finance_request_number>', methods=['GET'])
@login_required
def get_batch_by_fr(finance_request_number):
    """根据融资申请号获取批次信息"""
    try:
        batch_service = BatchService()
        batch = batch_service.get_batch_by_finance_request_number(finance_request_number)
        return jsonify({
            'code': 0,
            'msg': 'success',
            'data': batch
        })
    except Exception as e:
        return jsonify({
            'code': 1,
            'msg': f'获取批次信息失败: {str(e)}',
            'data': {}
        })

@batch_bp.route('/api/batches/status-count', methods=['GET'])
@login_required
def get_batch_status_count():
    """获取各批次状态的数量统计"""
    try:
        batch_service = BatchService()
        status_count = batch_service.get_batch_status_count()
        return jsonify({
            'code': 0,
            'msg': 'success',
            'data': status_count
        })
    except Exception as e:
        return jsonify({
            'code': 1,
            'msg': f'获取批次状态统计失败: {str(e)}',
            'data': {}
        })
