import io
import re
import zipfile
import logging
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from urllib.parse import unquote

import requests
from flask import render_template, request, send_file, flash, redirect, url_for, jsonify
from flask_login import login_required

from backend.app.routes import tools_bp

logger = logging.getLogger(__name__)

INVOICE_API_URL = 'https://n8n.air8.cn/webhook/downloadInvoiceFiles'
INVOICE_API_TOKEN = 'd5173b84678c11f0995006a0ea58daac'
BATCH_SIZE = 50
MAX_DOWNLOAD_WORKERS = 10


def _sanitize_filename(name):
    """Remove characters that are invalid in filenames."""
    return re.sub(r'[\\/:*?"<>|]', '_', name).strip()


def _extract_filename_from_url(url):
    """Extract a human-readable filename from a download URL."""
    # Try to get filename from the URL path (before query params)
    path = url.split('?')[0]
    # The last segment of the path is typically the encoded filename
    segment = path.rsplit('/', 1)[-1]
    decoded = unquote(segment)
    # If it looks like a real filename, use it
    if '.' in decoded and len(decoded) < 200:
        return decoded
    return None


def _call_invoice_api_batch(batch, batch_index):
    """Call the external invoice API for a single batch."""
    params = {
        'token': INVOICE_API_TOKEN,
        'financingNos': ','.join(batch),
    }
    try:
        resp = requests.get(INVOICE_API_URL, params=params, timeout=120, verify=False)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list):
            return data
        else:
            logger.warning('Unexpected API response format for batch %d: %s', batch_index, type(data))
            return []
    except requests.RequestException as e:
        logger.error('Invoice API call failed for batch %d: %s', batch_index, e)
        raise


def _call_invoice_api(financing_nos):
    """Call the external invoice API, batching if necessary.

    Uses parallel requests when multiple batches are needed.
    Returns a merged list of all results across batches.
    """
    batches = [financing_nos[i:i + BATCH_SIZE] for i in range(0, len(financing_nos), BATCH_SIZE)]

    if len(batches) == 1:
        return _call_invoice_api_batch(batches[0], 1)

    all_results = []
    with ThreadPoolExecutor(max_workers=min(len(batches), MAX_DOWNLOAD_WORKERS)) as executor:
        futures = {
            executor.submit(_call_invoice_api_batch, batch, idx + 1): idx
            for idx, batch in enumerate(batches)
        }
        for future in as_completed(futures):
            all_results.extend(future.result())

    return all_results


def _download_file(url):
    """Download a file from a URL and return (filename, content_bytes)."""
    try:
        resp = requests.get(url, timeout=120, verify=False)
        resp.raise_for_status()

        # Try Content-Disposition header first
        filename = None
        cd = resp.headers.get('Content-Disposition', '')
        if 'filename=' in cd:
            # Handle both filename="..." and filename*=UTF-8''...
            match = re.search(r"filename\*?=['\"]?(?:UTF-8'')?([^;'\"]+)", cd, re.IGNORECASE)
            if match:
                filename = unquote(match.group(1)).strip()

        # Fallback to URL-based extraction
        if not filename:
            filename = _extract_filename_from_url(url)

        # Final fallback
        if not filename:
            filename = 'file'

        return filename, resp.content
    except requests.RequestException as e:
        logger.warning('Failed to download file from %s: %s', url[:100], e)
        return None, None


DUMMY_INVOICE_API_URL = 'https://n8n.air8.cn/webhook/CreateDummyInvoice'
DUMMY_INVOICE_API_TOKEN = 'd5173b84678c11f0995006a0ea58daac'


@tools_bp.route('/')
@login_required
def tools_index():
    """Tools index page listing all available tools."""
    return render_template('tools/index.html')


@tools_bp.route('/create-dummy-invoice')
@login_required
def create_dummy_invoice():
    """Create dummy invoice tool page."""
    return render_template('tools/create_dummy_invoice.html')


@tools_bp.route('/create-dummy-invoice', methods=['POST'])
@login_required
def create_dummy_invoice_post():
    """Process dummy invoice creation request."""
    buyer_code = request.form.get('buyer_code', '').strip()
    supplier_code = request.form.get('supplier_code', '').strip()
    amount = request.form.get('amount', '').strip()

    if not buyer_code or not supplier_code or not amount:
        return jsonify({'success': False, 'message': '请填写所有必填字段'})

    try:
        float(amount)
    except ValueError:
        return jsonify({'success': False, 'message': '金额必须是有效的数字'})

    params = {
        'token': DUMMY_INVOICE_API_TOKEN,
        'buyerCode': buyer_code,
        'supplierCode': supplier_code,
        'amount': amount,
    }

    try:
        resp = requests.get(DUMMY_INVOICE_API_URL, params=params, timeout=60, verify=False)
        resp.raise_for_status()
        data = resp.json()
        return jsonify({'success': True, 'data': data})
    except requests.RequestException as e:
        logger.error('Dummy invoice API call failed: %s', e)
        return jsonify({'success': False, 'message': '调用API失败，请稍后重试'})


@tools_bp.route('/invoice-download')
@login_required
def invoice_download():
    """Invoice download tool page."""
    return render_template('tools/invoice_download.html')


@tools_bp.route('/invoice-download', methods=['POST'])
@login_required
def invoice_download_post():
    """Process invoice file download request."""
    raw_input = request.form.get('financing_nos', '').strip()

    if not raw_input:
        flash('请输入至少一个融资编号', 'danger')
        return redirect(url_for('tools.invoice_download'))

    # Parse financing numbers: split by newlines, strip whitespace, remove empty
    financing_nos = [line.strip() for line in raw_input.splitlines() if line.strip()]

    if not financing_nos:
        flash('请输入至少一个融资编号', 'danger')
        return redirect(url_for('tools.invoice_download'))

    # Call external API
    try:
        api_results = _call_invoice_api(financing_nos)
    except requests.RequestException:
        flash('调用API失败，请稍后重试', 'danger')
        return redirect(url_for('tools.invoice_download'))

    if not api_results:
        flash('未找到任何发票文件', 'warning')
        return redirect(url_for('tools.invoice_download'))

    # Group by invoice_no + financing_no
    groups = defaultdict(list)
    for item in api_results:
        invoice_no = item.get('invoice_no', '')
        financing_no = item.get('financing_no', '')
        group_key = f"{invoice_no}_{financing_no}"
        groups[group_key].append(item)

    # Download all files in parallel
    all_urls = [item['download_url'] for items in groups.values() for item in items if item.get('download_url')]
    downloaded = {}
    with ThreadPoolExecutor(max_workers=MAX_DOWNLOAD_WORKERS) as executor:
        future_to_url = {executor.submit(_download_file, url): url for url in all_urls}
        for future in as_completed(future_to_url):
            url = future_to_url[future]
            filename, content = future.result()
            if content is not None:
                downloaded[url] = (filename, content)

    # Build the final zip in memory
    outer_buf = io.BytesIO()
    with zipfile.ZipFile(outer_buf, 'w', zipfile.ZIP_DEFLATED) as outer_zip:
        for group_key, items in groups.items():
            safe_group_name = _sanitize_filename(group_key)

            if len(groups) == 1:
                # Only one group: put files directly in the outer zip
                for item in items:
                    result = downloaded.get(item.get('download_url'))
                    if result is None:
                        continue
                    safe_filename = _sanitize_filename(result[0])
                    outer_zip.writestr(safe_filename, result[1])
            else:
                # Multiple groups: create a sub-zip per group
                inner_buf = io.BytesIO()
                with zipfile.ZipFile(inner_buf, 'w', zipfile.ZIP_DEFLATED) as inner_zip:
                    for item in items:
                        result = downloaded.get(item.get('download_url'))
                        if result is None:
                            continue
                        safe_filename = _sanitize_filename(result[0])
                        inner_zip.writestr(safe_filename, result[1])
                inner_buf.seek(0)
                outer_zip.writestr(f"{safe_group_name}.zip", inner_buf.read())

    outer_buf.seek(0)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    download_name = f"invoice_files_{timestamp}.zip"

    return send_file(
        outer_buf,
        mimetype='application/zip',
        as_attachment=True,
        download_name=download_name,
    )
