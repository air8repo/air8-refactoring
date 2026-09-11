"""每日额度预警服务 — 复用实时聚合逻辑，超阈值时发送汇总邮件"""
import html
import logging
from datetime import datetime
import requests
from flask import current_app
from backend.app.services.credit_limit_service import (
    get_buyer_supplier_pairs, aggregate_by_buyer, check_warnings,
)

logger = logging.getLogger('credit_warning')


def register_credit_warning_job(scheduler, app):
    """注册定时任务到 APScheduler：每天 07:00 Asia/Shanghai"""
    scheduler.add_job(
        credit_warning_task,
        'cron',
        hour=7,
        minute=0,
        args=[app],
        id='credit_limit_warning',
        replace_existing=True,
    )
    logger.info('Registered credit limit warning job: 07:00 Asia/Shanghai')


def credit_warning_task(app):
    """定时任务入口（在 scheduler 线程中执行）"""
    with app.app_context():
        logger.info('=== Credit limit warning task started ===')
        try:
            _run_warning_check()
        except Exception as e:
            logger.error('Credit limit warning task failed: %s', e, exc_info=True)
        logger.info('=== Credit limit warning task finished ===')


def run_warning_check_manual():
    """手动触发入口（在 Flask request context 中调用）"""
    try:
        result = _run_warning_check()
        return {'success': True, **result}
    except Exception as e:
        logger.error('Manual credit warning check failed: %s', e, exc_info=True)
        return {'success': False, 'message': str(e)}


def _get_mongo():
    try:
        from backend.app.extensions import mongo as ext_mongo
        if ext_mongo is not None:
            return ext_mongo
    except Exception:
        pass
    try:
        if hasattr(current_app, 'extensions'):
            m = current_app.extensions.get('mongo')
            if m is not None:
                return m
    except Exception:
        pass
    return None


def _run_warning_check():
    """核心检查逻辑：聚合 → 阈值筛选 → 超阈值则发邮件"""
    mongo = _get_mongo()
    if mongo is None:
        raise RuntimeError('数据库未连接')

    threshold = current_app.config.get('CREDIT_WARNING_THRESHOLD', 0.9)
    pairs = get_buyer_supplier_pairs(mongo)
    buyers = aggregate_by_buyer(pairs)
    warned = check_warnings(buyers, pairs, threshold)

    warned_buyer_count = len(warned['buyers'])
    warned_pair_count = len(warned['pairs'])
    warned_count = warned_buyer_count + warned_pair_count
    email_sent = False
    if warned_count > 0:
        email_sent = _send_warning_email(warned['buyers'], warned['pairs'])

    logger.info(
        'Credit warning check done: buyers=%d pairs=%d warned_buyers=%d warned_pairs=%d email_sent=%s',
        len(buyers), len(pairs), warned_buyer_count, warned_pair_count, email_sent,
    )
    return {
        'checked_buyers': len(buyers),
        'checked_pairs': len(pairs),
        'warned_count': warned_count,
        'warned_buyer_count': warned_buyer_count,
        'warned_pair_count': warned_pair_count,
        'email_sent': email_sent,
    }


def _send_warning_email(warned_buyers, warned_pairs):
    """通过 n8n-v2 通用邮件 webhook（COMMON_EMAIL_URL）发送超阈值汇总邮件。"""
    email_url = current_app.config.get('COMMON_EMAIL_URL')
    if not email_url:
        logger.warning('邮件接口未配置(COMMON_EMAIL_URL)，跳过额度预警通知')
        return False

    today = datetime.now().strftime('%Y-%m-%d')

    buyer_rows_html = ''.join(
        '<tr>'
        f'<td>{html.escape(str(b.get("buyer_name", "")))}</td>'
        f'<td>{b.get("currency", "")}</td>'
        f'<td>{(b.get("celling") or 0):,.2f}</td>'
        f'<td>{(b.get("total_occupied") or 0):,.2f}</td>'
        f'<td>{(b.get("headroom") or 0):,.2f}</td>'
        f'<td>{(b.get("occupancy_rate") or 0):.1%}</td>'
        '</tr>'
        for b in warned_buyers
    )
    pair_rows_html = ''.join(
        '<tr>'
        f'<td>{html.escape(str(p.get("buyer_name", "")))}</td>'
        f'<td>{html.escape(str(p.get("supplier_name", "")))}</td>'
        f'<td>{p.get("currency", "")}</td>'
        f'<td>{(p.get("celling") or 0):,.2f}</td>'
        f'<td>{(p.get("total_occupied") or 0):,.2f}</td>'
        f'<td>{(p.get("headroom") or 0):,.2f}</td>'
        f'<td>{(p.get("occupancy_rate") or 0):.1%}</td>'
        '</tr>'
        for p in warned_pairs
    )

    body = (
        f'<p>The following buyers/pairs exceeded the credit limit warning threshold on {today}:</p>'
        '<p><b>By Buyer:</b></p>'
        '<table border="1" cellpadding="6" cellspacing="0">'
        '<tr><th>Buyer</th><th>Currency</th><th>Celling</th><th>Total Occupied</th>'
        '<th>Headroom</th><th>Occupancy Rate</th></tr>'
        f'{buyer_rows_html}</table>'
        '<p><b>By Buyer-Supplier Pair:</b></p>'
        '<table border="1" cellpadding="6" cellspacing="0">'
        '<tr><th>Buyer</th><th>Supplier</th><th>Currency</th><th>Celling</th>'
        '<th>Total Occupied</th><th>Headroom</th><th>Occupancy Rate</th></tr>'
        f'{pair_rows_html}</table>'
    )

    payload = {
        'type': 'common',
        'title': f'[Refactoring] Credit Limit Warning - {today} ({len(warned_buyers)} buyer(s))',
        'body': body,
    }

    try:
        response = requests.post(email_url, json=payload, timeout=60, verify=False)
        response.raise_for_status()
        logger.info('Credit limit warning email sent, %d buyer(s); response: %s',
                    len(warned_buyers), response.text[:200])
        return True
    except requests.RequestException as e:
        logger.error('Credit limit warning email failed: %s', e)
        raise
