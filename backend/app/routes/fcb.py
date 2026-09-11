"""FCB 模块路由 — 客户维护 + 交易数据导出"""
from flask import render_template, request, jsonify, send_file
from flask_login import login_required
from backend.app.routes import fcb_bp
from backend.app.services.fcb_service import FCBService


# ──────────────────────────────────────────────
# 页面路由
# ──────────────────────────────────────────────
@fcb_bp.route('/clients')
@login_required
def clients_page():
    return render_template('fcb/clients.html')


@fcb_bp.route('/export')
@login_required
def export_page():
    return render_template('fcb/export.html')


# ──────────────────────────────────────────────
# 客户 CRUD API
# ──────────────────────────────────────────────
@fcb_bp.route('/api/clients', methods=['GET'])
@login_required
def api_list_clients():
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('pageSize', 20, type=int)
    keyword = request.args.get('keyword', '', type=str).strip()
    result = FCBService.list_clients(page, page_size, keyword or None)
    return jsonify({'success': True, 'data': result})


@fcb_bp.route('/api/clients/<client_id>', methods=['GET'])
@login_required
def api_get_client(client_id):
    client = FCBService.get_client(client_id)
    if not client:
        return jsonify({'success': False, 'message': 'Client not found'}), 404
    return jsonify({'success': True, 'data': client})


@fcb_bp.route('/api/clients', methods=['POST'])
@login_required
def api_create_client():
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'message': 'No data provided'}), 400
    try:
        client = FCBService.create_client(data)
        return jsonify({'success': True, 'data': client}), 201
    except ValueError as e:
        return jsonify({'success': False, 'message': str(e)}), 409


@fcb_bp.route('/api/clients/<client_id>', methods=['PUT'])
@login_required
def api_update_client(client_id):
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'message': 'No data provided'}), 400
    try:
        client = FCBService.update_client(client_id, data)
    except ValueError as e:
        return jsonify({'success': False, 'message': str(e)}), 409
    if not client:
        return jsonify({'success': False, 'message': 'Client not found'}), 404
    return jsonify({'success': True, 'data': client})


@fcb_bp.route('/api/clients/<client_id>', methods=['DELETE'])
@login_required
def api_delete_client(client_id):
    deleted = FCBService.delete_client(client_id)
    if not deleted:
        return jsonify({'success': False, 'message': 'Client not found'}), 404
    return jsonify({'success': True, 'message': 'Client deleted'})


# ──────────────────────────────────────────────
# 导出 API
# ──────────────────────────────────────────────
@fcb_bp.route('/api/export', methods=['POST'])
@login_required
def api_export():
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'message': 'No data provided'}), 400

    financing_nos = data.get('financing_nos')

    if not financing_nos:
        return jsonify({'success': False, 'message': 'Please provide financing numbers'}), 400

    try:
        file_buffer, content_type, filename = FCBService.export_transactions(
            financing_nos=financing_nos
        )
        return send_file(
            file_buffer,
            mimetype=content_type,
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


# ──────────────────────────────────────────────
# 每日推送手动触发
# ──────────────────────────────────────────────
@fcb_bp.route('/api/trigger-daily-export', methods=['POST'])
@login_required
def api_trigger_daily_export():
    from backend.app.services.daily_export_service import run_daily_export_manual
    result = run_daily_export_manual()
    status_code = 200 if result.get('success') else 500
    return jsonify(result), status_code
