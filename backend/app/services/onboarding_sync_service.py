"""Onboarding 配置数据增量同步服务"""
import logging
import requests
from datetime import datetime

logger = logging.getLogger('onboarding_sync')

ONBOARDING_API_URL = (
    'https://n8n.air8.cn/webhook/exportRefactoringPairs'
    '?token=d5173b84678c11f0995006a0ea58daac'
)

_DATETIME_FORMATS = ('%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d')


def register_onboarding_sync_job(scheduler, app):
    """注册定时任务到 APScheduler：每天 02:00 Asia/Shanghai"""
    scheduler.add_job(
        onboarding_sync_task,
        'cron',
        hour=2,
        minute=0,
        args=[app],
        id='onboarding_sync',
        replace_existing=True,
    )
    logger.info('Registered onboarding sync job: 02:00 Asia/Shanghai')


def onboarding_sync_task(app):
    """定时任务入口（在 scheduler 线程中执行）"""
    with app.app_context():
        logger.info('=== Onboarding sync task started ===')
        try:
            _run_sync()
        except Exception as e:
            logger.error('Onboarding sync task failed: %s', e, exc_info=True)
        logger.info('=== Onboarding sync task finished ===')


def run_onboarding_sync_manual():
    """手动触发入口（在 Flask request context 中调用）"""
    try:
        details = _run_sync()
        msg = (
            f"同步完成：新增 {details['inserted']} 条，"
            f"更新 {details['updated']} 条，"
            f"跳过 {details['skipped']} 条（共拉取 {details['total_fetched']} 条）"
        )
        return {'success': True, 'message': msg, 'details': details}
    except Exception as e:
        logger.error('Manual onboarding sync failed: %s', e, exc_info=True)
        return {'success': False, 'message': str(e)}


# ── internal ──────────────────────────────────────────────────────────────────

def _get_mongo():
    try:
        from backend.app.extensions import mongo as ext_mongo
        if ext_mongo is not None:
            return ext_mongo
    except Exception:
        pass
    try:
        from flask import current_app
        if hasattr(current_app, 'extensions'):
            m = current_app.extensions.get('mongo')
            if m is not None:
                return m
    except Exception:
        pass
    return None


def _parse_datetime(value):
    """将字符串解析为 datetime，解析失败返回 None"""
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    for fmt in _DATETIME_FORMATS:
        try:
            return datetime.strptime(value, fmt)
        except (ValueError, TypeError):
            continue
    return None


def _map_record(api_row):
    """将 API 数据映射为 MongoDB 文档（不含 created_at）"""
    approved_tenor = api_row.get('approved_tenor') or 0
    try:
        approved_tenor = int(approved_tenor)
    except (ValueError, TypeError):
        approved_tenor = 0

    advance_ratio = api_row.get('advance_ratio')
    try:
        advance_ratio = float(advance_ratio) if advance_ratio not in (None, '') else None
    except (ValueError, TypeError):
        advance_ratio = None

    refactoring_limit = api_row.get('refactoring_limit')
    try:
        refactoring_limit = float(refactoring_limit) if refactoring_limit not in (None, '') else None
    except (ValueError, TypeError):
        refactoring_limit = None

    return {
        'uid': api_row.get('uid', ''),
        'refactoring_funder': api_row.get('refactoring_funder', ''),
        'supplier_code': api_row.get('supplier_code', ''),
        'seller_name': api_row.get('supplier_name', ''),
        'buyer_code': api_row.get('buyer_code', ''),
        'obligor_name': api_row.get('buyer_name', ''),
        'approved_tenor_days': approved_tenor,
        'advance_ratio': advance_ratio,
        'refactoring_limit': refactoring_limit,
        'target_list_status': api_row.get('target_list_status', 'Y'),
        'api_update_time': _parse_datetime(api_row.get('update_time')),
        'updated_at': datetime.now(),
    }


def _run_sync():
    """核心同步逻辑：拉取 → 增量过滤 → upsert → 更新 meta"""
    mongo = _get_mongo()
    if mongo is None:
        raise RuntimeError('数据库未连接')

    sync_start = datetime.now()

    # 1. 读取上次同步时间
    meta = mongo.refactoring_sync_meta.find_one({'type': 'onboarding'})
    last_sync_time = meta.get('last_sync_time') if meta else None
    logger.info('Last onboarding sync time: %s', last_sync_time)

    # 2. 拉取全量 API 数据
    response = requests.get(ONBOARDING_API_URL, timeout=30, verify=False)
    response.raise_for_status()
    api_data = response.json()
    total_fetched = len(api_data)
    logger.info('Fetched %d records from API', total_fetched)

    inserted = updated = skipped = 0

    for api_row in api_data:
        uid = api_row.get('uid', '').strip()
        if not uid:
            skipped += 1
            continue

        # 3. 增量过滤：update_time <= last_sync_time 则跳过
        if last_sync_time is not None:
            row_update_time = _parse_datetime(api_row.get('update_time'))
            if row_update_time is not None and row_update_time <= last_sync_time:
                skipped += 1
                continue

        record = _map_record(api_row)

        # 4. upsert by uid
        existing = mongo.refactoring_onboard_config.find_one({'uid': uid})
        if existing:
            mongo.refactoring_onboard_config.update_one(
                {'uid': uid},
                {'$set': record}
            )
            updated += 1
        else:
            record['created_at'] = _parse_datetime(api_row.get('create_time')) or datetime.now()
            mongo.refactoring_onboard_config.insert_one(record)
            inserted += 1

    # 5. 更新 sync meta
    mongo.refactoring_sync_meta.update_one(
        {'type': 'onboarding'},
        {'$set': {
            'type': 'onboarding',
            'last_sync_time': sync_start,
            'last_sync_inserted': inserted,
            'last_sync_updated': updated,
            'last_sync_skipped': skipped,
        }},
        upsert=True,
    )

    logger.info(
        'Onboarding sync done: inserted=%d updated=%d skipped=%d total=%d',
        inserted, updated, skipped, total_fetched,
    )
    return {
        'inserted': inserted,
        'updated': updated,
        'skipped': skipped,
        'total_fetched': total_fetched,
    }
