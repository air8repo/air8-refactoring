"""FCB 每日定时推送服务 — 获取数据、生成 Excel、下载附件、发送邮件"""
import io
import json
import logging
import zipfile
import requests
from collections import defaultdict
from datetime import datetime

logger = logging.getLogger('daily_export')

# 每日数据 API
DAILY_API_URL = 'https://n8n.air8.cn/webhook/exportFcbRefactoringInvoicesDaily'
DAILY_API_TOKEN = 'd5173b84678c11f0995006a0ea58daac'


def register_scheduled_jobs(scheduler, app):
    """注册定时任务到 APScheduler"""
    scheduler.add_job(
        daily_export_task,
        'cron',
        hour=6,
        minute=0,
        args=[app],
        id='daily_fcb_export',
        replace_existing=True,
    )
    logger.info('Registered daily FCB export job: 06:00 Asia/Shanghai')


def daily_export_task(app):
    """每日推送主流程（在 scheduler 线程中执行）"""
    with app.app_context():
        logger.info('=== Daily FCB export task started ===')
        try:
            _run_export_pipeline()
        except Exception as e:
            logger.error('Daily FCB export task failed: %s', e, exc_info=True)
        logger.info('=== Daily FCB export task finished ===')


def run_daily_export_manual():
    """手动触发入口（在 Flask request context 中调用）"""
    try:
        result = _run_export_pipeline()
        return {'success': True, 'message': 'Daily export completed', 'details': result}
    except Exception as e:
        logger.error('Manual daily export failed: %s', e, exc_info=True)
        return {'success': False, 'message': str(e)}


def _run_export_pipeline():
    """执行导出流水线的4个步骤"""
    result = {'unmatched_count': 0}

    # Step 1: 获取每日交易数据
    logger.info('Step 1: Fetching daily transactions...')
    transactions, financing_nos = _fetch_daily_transactions()
    result['transactions_count'] = len(transactions)
    result['financing_nos_count'] = len(financing_nos)
    logger.info('Fetched %d transactions, %d financing numbers', len(transactions), len(financing_nos))

    if not transactions:
        logger.warning('No transactions found, skipping export')
        result['message'] = 'No transactions found'
        return result

    # Step 2: 生成 Excel
    excel_buf = None
    excel_filename = None
    try:
        logger.info('Step 2: Generating Excel files...')
        excel_buf, excel_filename, unmatched_count = _generate_excel(transactions)
        result['excel_filename'] = excel_filename
        result['unmatched_count'] = unmatched_count
        logger.info('Generated Excel: %s (unmatched=%d)', excel_filename, unmatched_count)
    except Exception as e:
        logger.error('Step 2 failed (Excel generation): %s', e, exc_info=True)
        result['excel_error'] = str(e)

    # Step 3: 下载发票附件
    invoice_buf = None
    invoice_filename = None
    if financing_nos:
        try:
            logger.info('Step 3: Downloading invoice files for %d financing numbers...', len(financing_nos))
            invoice_buf, invoice_filename = _download_invoices(financing_nos)
            if invoice_buf:
                result['invoice_filename'] = invoice_filename
                logger.info('Downloaded invoices: %s', invoice_filename)
            else:
                logger.warning('No invoice files found')
                result['invoice_warning'] = 'No invoice files found'
        except Exception as e:
            logger.error('Step 3 failed (invoice download): %s', e, exc_info=True)
            result['invoice_error'] = str(e)
    else:
        logger.warning('No financing numbers extracted, skipping invoice download')

    # Step 4: 发送邮件
    if excel_buf or invoice_buf:
        try:
            logger.info('Step 4: Sending email...')
            _send_email(excel_buf, excel_filename, invoice_buf, invoice_filename)
            result['email_sent'] = True
            logger.info('Email sent successfully')
        except Exception as e:
            logger.error('Step 4 failed (email): %s', e, exc_info=True)
            result['email_error'] = str(e)
    else:
        logger.warning('No attachments to send, skipping email')
        result['email_skipped'] = True

    return result


# ── Step 1: 获取每日交易数据 ──────────────────────────

def _fetch_daily_transactions():
    """调用每日 API 获取交易数据，返回 (transactions, financing_nos)"""
    try:
        response = requests.get(
            DAILY_API_URL,
            params={'token': DAILY_API_TOKEN},
            timeout=120,
            verify=False,
        )
        response.raise_for_status()
        raw = response.json()

        # 解析嵌套 JSON: [{"data":"[{...}]"}]
        transactions = []
        if isinstance(raw, list) and raw:
            data_str = raw[0].get('data', '[]')
            if isinstance(data_str, str):
                transactions = json.loads(data_str)
            elif isinstance(data_str, list):
                transactions = data_str

        # 提取去重的融资编号
        financing_nos = list({
            txn['financing_no']
            for txn in transactions
            if txn.get('financing_no')
        })

        return transactions, financing_nos
    except requests.RequestException as e:
        raise ValueError(f'Failed to fetch daily transactions: {e}')


# ── Step 2: 生成 Excel ──────────────────────────

def _generate_excel(transactions):
    """复用 fcb_service 逻辑生成 Excel/ZIP，返回 (BytesIO, filename, unmatched_count)"""
    from backend.app.services.fcb_service import (
        _get_collection, _build_excel, match_client_for_transaction,
    )

    # 按 supplier_code 分组
    groups = {}
    for txn in transactions:
        code = txn.get('supplier_code', '')
        groups.setdefault(code, []).append(txn)

    # 批量查询候选客户（一个 supplier_code 可能对应多个 buyer）
    col = _get_collection()
    supplier_codes = list(groups.keys())
    candidates_map = {}
    for c in col.find({'supplier_code': {'$in': supplier_codes}}):
        candidates_map.setdefault(c['supplier_code'], []).append(c)

    # 逐笔交易匹配客户，按命中的客户 _id 重新分组
    matched_groups = {}
    unmatched_count = 0
    for code, txns in groups.items():
        candidates = candidates_map.get(code, [])
        for txn in txns:
            client, ambiguous = match_client_for_transaction(
                txn.get('buyer_code', ''), txn.get('buyer_name', ''), candidates
            )
            if not client:
                unmatched_count += 1
                logger.warning(
                    'No client match for supplier_code=%s buyer_code=%s buyer_name=%s (ambiguous=%s), skipping',
                    code, txn.get('buyer_code', ''), txn.get('buyer_name', ''), ambiguous,
                )
                continue
            cid = client['_id']
            matched_groups.setdefault(cid, {'client': client, 'txns': []})
            matched_groups[cid]['txns'].append(txn)

    # 生成 Excel 文件
    files = []
    today = datetime.utcnow().strftime('%Y%m%d')
    for group in matched_groups.values():
        client = group['client']
        excel_buf = _build_excel(client, group['txns'])
        client_number = client.get('client_number', 'unknown')
        customer_name = client.get('customer_name', 'unknown')
        safe_name = ''.join(c if c.isalnum() or c in ' _-' else '_' for c in customer_name)
        filename = f'{client_number}_{safe_name}_{today}.xlsx'
        files.append((filename, excel_buf))

    if not files:
        raise ValueError('No matching client data for Excel generation')

    if len(files) == 1:
        return files[0][1], files[0][0], unmatched_count

    # 多客户 → ZIP
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for fname, buf in files:
            zf.writestr(fname, buf.read())
    zip_buf.seek(0)
    return zip_buf, f'fcb_export_{today}.zip', unmatched_count


# ── Step 3: 下载发票附件 ──────────────────────────

def _download_invoices(financing_nos):
    """复用 tools.py 的逻辑下载发票文件并打包 ZIP，返回 (BytesIO, filename) 或 (None, None)"""
    from backend.app.routes.tools import (
        _call_invoice_api, _download_file, _sanitize_filename,
    )
    from concurrent.futures import ThreadPoolExecutor, as_completed

    # 调用 API 获取下载链接
    try:
        api_results = _call_invoice_api(financing_nos)
    except requests.RequestException as e:
        raise ValueError(f'Invoice API call failed: {e}')

    if not api_results:
        return None, None

    # 按 invoice_no + financing_no 分组
    groups = defaultdict(list)
    for item in api_results:
        invoice_no = item.get('invoice_no', '')
        financing_no = item.get('financing_no', '')
        group_key = f'{invoice_no}_{financing_no}'
        groups[group_key].append(item)

    # 并行下载文件
    all_urls = [item['download_url'] for items in groups.values() for item in items if 'download_url' in item]
    downloaded = {}
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_url = {executor.submit(_download_file, url): url for url in all_urls}
        for future in as_completed(future_to_url):
            url = future_to_url[future]
            filename, content = future.result()
            if content is not None:
                downloaded[url] = (filename, content)

    if not downloaded:
        return None, None

    # 打包 ZIP
    outer_buf = io.BytesIO()
    with zipfile.ZipFile(outer_buf, 'w', zipfile.ZIP_DEFLATED) as outer_zip:
        for group_key, items in groups.items():
            safe_group = _sanitize_filename(group_key)
            if len(groups) == 1:
                for item in items:
                    result = downloaded.get(item.get('download_url'))
                    if result:
                        outer_zip.writestr(_sanitize_filename(result[0]), result[1])
            else:
                inner_buf = io.BytesIO()
                with zipfile.ZipFile(inner_buf, 'w', zipfile.ZIP_DEFLATED) as inner_zip:
                    for item in items:
                        result = downloaded.get(item.get('download_url'))
                        if result:
                            inner_zip.writestr(_sanitize_filename(result[0]), result[1])
                inner_buf.seek(0)
                outer_zip.writestr(f'{safe_group}.zip', inner_buf.read())

    outer_buf.seek(0)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    return outer_buf, f'invoice_files_{timestamp}.zip'


# ── Step 4: 发送邮件 ──────────────────────────

def _send_email(excel_buf, excel_filename, invoice_buf, invoice_filename):
    """通过 n8n 邮件接口发送附件"""
    from flask import current_app

    email_url = current_app.config.get('DAILY_EXPORT_EMAIL_URL')
    email_token = current_app.config.get('DAILY_EXPORT_EMAIL_TOKEN')

    if not email_url:
        raise ValueError('DAILY_EXPORT_EMAIL_URL not configured')

    today = datetime.now().strftime('%Y-%m-%d')

    # 构建 multipart/form-data
    files = []
    if excel_buf:
        excel_buf.seek(0)
        files.append(('attachments', (excel_filename, excel_buf.read(), 'application/octet-stream')))
    if invoice_buf:
        invoice_buf.seek(0)
        files.append(('attachments', (invoice_filename, invoice_buf.read(), 'application/zip')))

    data = {
        'subject': f'FCB Daily Export - {today}',
        'body': f'FCB daily export for {today}. Please find the attached files.',
    }

    try:
        response = requests.post(
            email_url,
            params={'token': email_token},
            data=data,
            files=files,
            timeout=120,
            verify=False,
        )
        response.raise_for_status()
        logger.info('Email API response: %s', response.text[:200])
    except requests.RequestException as e:
        raise ValueError(f'Failed to send email: {e}')
