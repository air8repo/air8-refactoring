# FCB 客户导出按 Buyer 匹配 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 `fcb_clients` 支持同一 `supplier_code` 下维护多条客户记录（按 buyer 区分），并让 FCB Excel 导出（手动 + 每日定时）按 supplier_code + buyer 精确匹配客户记录。

**Architecture:** 新增字段 `buyer_air8_code` 到 `fcb_clients`；CRUD 查重规则从单一 `supplier_code` 改为按 `(supplier_code, buyer_air8_code)`（有码时）或 `(supplier_code, customer_name)`（无码时）组合查重；新增共享纯函数 `match_client_for_transaction()` 统一两处导出入口（`fcb_service.export_transactions()`、`daily_export_service._generate_excel()`）的匹配逻辑，替换原先的 `{supplier_code: client}` 一对一 dict 映射。

**Tech Stack:** Python 3 / Flask / MongoDB (pymongo) / pandas + openpyxl / pytest + unittest.mock

## Global Constraints

- 外部 API（n8n）调用一律 mock，不发真实请求（见 `docs/claude/testing.md`）。
- 每个 task 结束时 `pytest backend/tests/` 全部通过。
- 每个 task 完成后立即提交（小步提交），commit message 用中文简述改动。
- 不新增 MongoDB 层唯一索引（现状 `fcb_clients` 本就没有，本次仅补齐应用层查重）。
- 不修改 `EXCEL_COLUMNS` / 导出 Excel 的输出列。
- 参考 spec：`docs/superpowers/specs/2026-08-17-fcb-buyer-matching-design.md`

---

### Task 1: `fcb_clients` 新增 `buyer_air8_code` 字段 + `create_client` 组合查重

_覆盖需求：1.1, 1.2, 2.1, 2.2_

**Files:**
- Modify: `backend/app/services/fcb_service.py:209-241`（`create_client`），新增模块级辅助函数 `_duplicate_query`
- Test: `backend/tests/test_fcb.py`

**Interfaces:**
- Produces: `_duplicate_query(supplier_code, buyer_air8_code, customer_name, exclude_id=None) -> dict`（Mongo 查询条件，供 Task 2 的 `update_client` 复用）
- Produces: `create_client(data)` 返回的 dict 新增 `buyer_air8_code` 键

- [ ] **Step 1: 写失败测试 — 有 buyer_air8_code 时按组合键查重**

在 `backend/tests/test_fcb.py` 的 `TestFCBClientAPI` 类中新增：

```python
    @patch('backend.app.services.fcb_service._get_collection')
    def test_create_client_with_buyer_air8_code(self, mock_col, logged_in_client):
        col = MagicMock()
        mock_col.return_value = col
        col.find_one.return_value = None  # no duplicate
        col.insert_one.return_value = MagicMock(inserted_id=ObjectId('507f1f77bcf86cd799439011'))

        resp = logged_in_client.post('/fcb/api/clients',
            data=json.dumps({
                'supplier_code': 'SUP-003',
                'buyer_air8_code': 'BUYER-A',
                'client_number': '1839',
                'customer_name': 'Client C',
            }),
            content_type='application/json'
        )
        data = json.loads(resp.data)
        assert resp.status_code == 201
        assert data['data']['buyer_air8_code'] == 'BUYER-A'
        # 查重条件应包含 buyer_air8_code，而不是仅 supplier_code
        called_query = col.find_one.call_args[0][0]
        assert called_query == {'supplier_code': 'SUP-003', 'buyer_air8_code': 'BUYER-A'}

    @patch('backend.app.services.fcb_service._get_collection')
    def test_create_client_duplicate_same_supplier_different_buyer_air8_code(self, mock_col, logged_in_client):
        col = MagicMock()
        mock_col.return_value = col
        col.find_one.return_value = None  # 不同 buyer_air8_code，不算重复
        col.insert_one.return_value = MagicMock(inserted_id=ObjectId('507f1f77bcf86cd799439012'))

        resp = logged_in_client.post('/fcb/api/clients',
            data=json.dumps({
                'supplier_code': 'SUP-001',  # 与既有客户相同 supplier_code
                'buyer_air8_code': 'BUYER-B',
                'client_number': '1840',
                'customer_name': 'Client D',
            }),
            content_type='application/json'
        )
        assert resp.status_code == 201

    @patch('backend.app.services.fcb_service._get_collection')
    def test_create_client_duplicate_no_buyer_air8_code_matches_customer_name(self, mock_col, logged_in_client):
        col = MagicMock()
        mock_col.return_value = col
        col.find_one.return_value = {'supplier_code': 'SUP-001', 'customer_name': 'Dup Client'}  # 同名重复

        resp = logged_in_client.post('/fcb/api/clients',
            data=json.dumps({
                'supplier_code': 'SUP-001',
                'customer_name': 'Dup Client',
            }),
            content_type='application/json'
        )
        assert resp.status_code == 409
        called_query = col.find_one.call_args[0][0]
        assert called_query == {'supplier_code': 'SUP-001', 'customer_name': 'Dup Client'}
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest backend/tests/test_fcb.py -k "buyer_air8_code or duplicate" -v`
Expected: FAIL（`buyer_air8_code` 未被读取/查重条件仍是仅 `supplier_code`）

- [ ] **Step 3: 实现**

在 `backend/app/services/fcb_service.py` 中，`_serialize_client` 函数之后（约第 84 行）新增：

```python
def _duplicate_query(supplier_code, buyer_air8_code, customer_name, exclude_id=None):
    """构造查重条件：有 buyer_air8_code 用 (supplier_code, buyer_air8_code)，否则用 (supplier_code, customer_name)"""
    if buyer_air8_code:
        query = {'supplier_code': supplier_code, 'buyer_air8_code': buyer_air8_code}
    else:
        query = {'supplier_code': supplier_code, 'customer_name': customer_name}
    if exclude_id:
        query['_id'] = {'$ne': exclude_id}
    return query
```

修改 `create_client`（`fcb_service.py:209-241`）：

```python
    @staticmethod
    def create_client(data):
        col = _get_collection()
        supplier_code = data.get('supplier_code', '').strip()
        if not supplier_code:
            raise ValueError('supplier_code is required')

        buyer_air8_code = data.get('buyer_air8_code', '').strip()
        customer_name = data.get('customer_name', '')

        # 检查唯一性：有 buyer_air8_code 按其查重，否则按 customer_name 查重
        if col.find_one(_duplicate_query(supplier_code, buyer_air8_code, customer_name)):
            raise ValueError('Client with the same supplier_code and buyer already exists')

        now = datetime.utcnow()
        doc = {
            'supplier_code': supplier_code,
            'buyer_air8_code': buyer_air8_code,
            'client_number': data.get('client_number', ''),
            'client_customer_no': data.get('client_customer_no', ''),
            'customer_name': customer_name,
            'customer_address1': data.get('customer_address1', ''),
            'customer_address2': data.get('customer_address2', ''),
            'customer_city': data.get('customer_city', ''),
            'customer_state': data.get('customer_state', ''),
            'customer_zip': data.get('customer_zip', ''),
            'customer_phone': data.get('customer_phone', ''),
            'client_terms_code': data.get('client_terms_code', ''),
            'client_terms_desc': data.get('client_terms_desc', ''),
            'customer_store_no': data.get('customer_store_no', ''),
            'customer_dept_no': data.get('customer_dept_no', ''),
            'created_at': now,
            'updated_at': now,
        }
        result = col.insert_one(doc)
        doc['_id'] = result.inserted_id
        return _serialize_client(doc)
```

同时更新原有的 `test_create_client_duplicate` 测试（`backend/tests/test_fcb.py:120-130`），因为错误提示文案变了：

```python
    @patch('backend.app.services.fcb_service._get_collection')
    def test_create_client_duplicate(self, mock_col, logged_in_client):
        col = MagicMock()
        mock_col.return_value = col
        col.find_one.return_value = {'supplier_code': 'SUP-001'}  # duplicate exists

        resp = logged_in_client.post('/fcb/api/clients',
            data=json.dumps({'supplier_code': 'SUP-001', 'customer_name': 'Dup'}),
            content_type='application/json'
        )
        assert resp.status_code == 409
        data = json.loads(resp.data)
        assert 'already exists' in data['message']
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest backend/tests/test_fcb.py -v`
Expected: PASS（全部 `TestFCBClientAPI` 用例）

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/fcb_service.py backend/tests/test_fcb.py
git commit -m "feat: fcb_clients 新增 buyer_air8_code 字段并按组合键查重"
```

---

### Task 2: `update_client` 组合查重 + 路由捕获重复冲突

_覆盖需求：2.3_

**Files:**
- Modify: `backend/app/services/fcb_service.py:243-260`（`update_client`）
- Modify: `backend/app/routes/fcb.py:58-67`（`api_update_client`）
- Test: `backend/tests/test_fcb.py`

**Interfaces:**
- Consumes: `_duplicate_query(supplier_code, buyer_air8_code, customer_name, exclude_id=None)`（Task 1 产出）
- Produces: `update_client(client_id, data)` 在冲突时抛出 `ValueError`；路由层将其映射为 HTTP 409

- [ ] **Step 1: 写失败测试**

修改 `backend/tests/test_fcb.py` 中已有的 `test_update_client`（第 132-150 行），补上 `col.find_one` 的返回值（因为新逻辑会先查现有记录）：

```python
    @patch('backend.app.services.fcb_service._get_collection')
    def test_update_client(self, mock_col, logged_in_client):
        col = MagicMock()
        mock_col.return_value = col
        oid = ObjectId('507f1f77bcf86cd799439011')
        existing = {
            '_id': oid,
            'supplier_code': 'SUP-001',
            'buyer_air8_code': '',
            'customer_name': 'Old Name',
        }
        col.find_one.side_effect = [existing, None]  # 1) 取现有记录 2) 查重未命中
        col.find_one_and_update.return_value = {
            '_id': oid,
            'supplier_code': 'SUP-001',
            'customer_name': 'Updated',
        }

        resp = logged_in_client.put(f'/fcb/api/clients/{str(oid)}',
            data=json.dumps({'customer_name': 'Updated'}),
            content_type='application/json'
        )
        data = json.loads(resp.data)
        assert resp.status_code == 200
        assert data['success'] is True
        assert data['data']['customer_name'] == 'Updated'
```

新增冲突场景测试：

```python
    @patch('backend.app.services.fcb_service._get_collection')
    def test_update_client_duplicate_conflict(self, mock_col, logged_in_client):
        col = MagicMock()
        mock_col.return_value = col
        oid = ObjectId('507f1f77bcf86cd799439011')
        other_oid = ObjectId('507f1f77bcf86cd799439099')
        existing = {
            '_id': oid,
            'supplier_code': 'SUP-001',
            'buyer_air8_code': '',
            'customer_name': 'Old Name',
        }
        conflict = {'_id': other_oid, 'supplier_code': 'SUP-001', 'customer_name': 'Taken Name'}
        col.find_one.side_effect = [existing, conflict]

        resp = logged_in_client.put(f'/fcb/api/clients/{str(oid)}',
            data=json.dumps({'customer_name': 'Taken Name'}),
            content_type='application/json'
        )
        assert resp.status_code == 409

    @patch('backend.app.services.fcb_service._get_collection')
    def test_update_client_not_found(self, mock_col, logged_in_client):
        col = MagicMock()
        mock_col.return_value = col
        col.find_one.return_value = None  # 现有记录都找不到

        resp = logged_in_client.put('/fcb/api/clients/507f1f77bcf86cd799439011',
            data=json.dumps({'customer_name': 'X'}),
            content_type='application/json'
        )
        assert resp.status_code == 404
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest backend/tests/test_fcb.py -k update_client -v`
Expected: FAIL（`update_client` 还没有查重/未找到现有记录时返回 404 的逻辑）

- [ ] **Step 3: 实现**

修改 `backend/app/services/fcb_service.py` 的 `update_client`（第 243-260 行）：

```python
    @staticmethod
    def update_client(client_id, data):
        col = _get_collection()
        try:
            oid = ObjectId(client_id)
        except Exception:
            return None

        existing = col.find_one({'_id': oid})
        if not existing:
            return None

        # 不允许更新 _id
        data.pop('_id', None)

        supplier_code = data.get('supplier_code', existing.get('supplier_code', '')).strip()
        buyer_air8_code = data.get('buyer_air8_code', existing.get('buyer_air8_code', '')).strip()
        customer_name = data.get('customer_name', existing.get('customer_name', ''))

        if col.find_one(_duplicate_query(supplier_code, buyer_air8_code, customer_name, exclude_id=oid)):
            raise ValueError('Client with the same supplier_code and buyer already exists')

        data['updated_at'] = datetime.utcnow()

        result = col.find_one_and_update(
            {'_id': oid},
            {'$set': data},
            return_document=True,
        )
        return _serialize_client(result)
```

修改 `backend/app/routes/fcb.py` 的 `api_update_client`（第 58-67 行），捕获 `ValueError`：

```python
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
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest backend/tests/test_fcb.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/fcb_service.py backend/app/routes/fcb.py backend/tests/test_fcb.py
git commit -m "fix: update_client 补齐组合查重校验，路由捕获冲突返回 409"
```

---

### Task 3: 新增共享匹配函数 `match_client_for_transaction`

_覆盖需求：3.1, 3.2, 3.3_

**Files:**
- Modify: `backend/app/services/fcb_service.py`（新增模块级函数，放在 `_merge_row` 之后、`_set_excel_styles` 之前，约第 113 行）
- Test: `backend/tests/test_fcb.py`

**Interfaces:**
- Consumes: 无（纯函数，不依赖数据库）
- Produces: `match_client_for_transaction(buyer_code, buyer_name, candidates) -> (client_dict_or_None, is_ambiguous_bool)`，供 Task 4、Task 5 使用

- [ ] **Step 1: 写失败测试**

在 `backend/tests/test_fcb.py` 新增一个测试类：

```python
class TestMatchClientForTransaction:

    def test_matches_by_buyer_air8_code(self):
        from backend.app.services.fcb_service import match_client_for_transaction
        candidates = [
            {'_id': 'c1', 'buyer_air8_code': 'BUYER-A', 'customer_name': 'Name A'},
            {'_id': 'c2', 'buyer_air8_code': 'BUYER-B', 'customer_name': 'Name B'},
        ]
        client, ambiguous = match_client_for_transaction('BUYER-B', 'Name B', candidates)
        assert client['_id'] == 'c2'
        assert ambiguous is False

    def test_buyer_air8_code_mismatch_does_not_fallback_to_name(self):
        from backend.app.services.fcb_service import match_client_for_transaction
        candidates = [
            {'_id': 'c1', 'buyer_air8_code': 'BUYER-A', 'customer_name': 'Name A'},
        ]
        # customer_name 与 buyer_name 相同，但 buyer_air8_code 不等，仍不应命中
        client, ambiguous = match_client_for_transaction('BUYER-X', 'Name A', candidates)
        assert client is None
        assert ambiguous is False

    def test_matches_by_customer_name_when_no_buyer_air8_code(self):
        from backend.app.services.fcb_service import match_client_for_transaction
        candidates = [
            {'_id': 'c1', 'buyer_air8_code': '', 'customer_name': 'Kohl S Inc'},
        ]
        client, ambiguous = match_client_for_transaction('', '  kohl s inc  ', candidates)
        assert client['_id'] == 'c1'
        assert ambiguous is False

    def test_no_match_when_name_differs(self):
        from backend.app.services.fcb_service import match_client_for_transaction
        candidates = [
            {'_id': 'c1', 'buyer_air8_code': '', 'customer_name': 'Kohl S Inc'},
        ]
        client, ambiguous = match_client_for_transaction('', 'Different Buyer', candidates)
        assert client is None
        assert ambiguous is False

    def test_ambiguous_when_multiple_candidates_match(self):
        from backend.app.services.fcb_service import match_client_for_transaction
        candidates = [
            {'_id': 'c1', 'buyer_air8_code': '', 'customer_name': 'Same Name'},
            {'_id': 'c2', 'buyer_air8_code': '', 'customer_name': 'Same Name'},
        ]
        client, ambiguous = match_client_for_transaction('', 'Same Name', candidates)
        assert client is None
        assert ambiguous is True

    def test_no_candidates_returns_unmatched(self):
        from backend.app.services.fcb_service import match_client_for_transaction
        client, ambiguous = match_client_for_transaction('BUYER-A', 'Name A', [])
        assert client is None
        assert ambiguous is False
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest backend/tests/test_fcb.py::TestMatchClientForTransaction -v`
Expected: FAIL（`ImportError: cannot import name 'match_client_for_transaction'`）

- [ ] **Step 3: 实现**

在 `backend/app/services/fcb_service.py` 的 `_merge_row` 函数之后（约第 113 行）新增：

```python
def match_client_for_transaction(buyer_code, buyer_name, candidates):
    """在同一 supplier_code 下的候选客户记录中，找到与交易匹配的唯一客户。

    候选记录若填了 buyer_air8_code，仅按其与 buyer_code 精确比较判定；
    未填 buyer_air8_code 的记录，退化为 customer_name 与 buyer_name 的规整化比较。

    返回 (matched_client_or_None, is_ambiguous)
    """
    buyer_code = (buyer_code or '').strip()
    buyer_name_norm = (buyer_name or '').strip().lower()

    matches = []
    for client in candidates:
        client_buyer_code = (client.get('buyer_air8_code') or '').strip()
        if client_buyer_code:
            if buyer_code and client_buyer_code == buyer_code:
                matches.append(client)
        else:
            client_name_norm = (client.get('customer_name') or '').strip().lower()
            if client_name_norm and client_name_norm == buyer_name_norm:
                matches.append(client)

    if len(matches) == 1:
        return matches[0], False
    if len(matches) == 0:
        return None, False
    return None, True
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest backend/tests/test_fcb.py::TestMatchClientForTransaction -v`
Expected: PASS（6 个用例全部通过）

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/fcb_service.py backend/tests/test_fcb.py
git commit -m "feat: 新增 match_client_for_transaction 共享匹配函数"
```

---

### Task 4: `export_transactions()` 改用新匹配逻辑

_覆盖需求：3.1, 3.2, 3.3, 3.4, 3.5_

**Files:**
- Modify: `backend/app/services/fcb_service.py:274-336`（`export_transactions`）
- Test: `backend/tests/test_fcb.py`

**Interfaces:**
- Consumes: `match_client_for_transaction(buyer_code, buyer_name, candidates)`（Task 3 产出）
- Produces: `export_transactions()` 返回值签名不变，仍为 `(file_buffer, content_type, filename)` 三元组

- [ ] **Step 1: 写失败测试**

在 `backend/tests/test_fcb.py` 的 `TestFCBExportAPI` 类中新增：

```python
    @patch('backend.app.services.fcb_service.requests.get')
    @patch('backend.app.services.fcb_service._get_collection')
    def test_export_same_supplier_code_different_buyers(self, mock_col, mock_get, logged_in_client):
        """同一 supplier_code 下两个不同 buyer 的交易，应各自匹配到正确客户并生成两个文件"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = [{
            'data': json.dumps([
                {'supplier_code': 'SUP-001', 'buyer_code': 'BUYER-A', 'buyer_name': 'Buyer A',
                 'invoice_number': 'INV-001', 'invoice_amount': '100', 'invoice_date': '2026-01-01'},
                {'supplier_code': 'SUP-001', 'buyer_code': 'BUYER-B', 'buyer_name': 'Buyer B',
                 'invoice_number': 'INV-002', 'invoice_amount': '200', 'invoice_date': '2026-01-02'},
            ])
        }]
        mock_get.return_value = mock_response

        col = MagicMock()
        mock_col.return_value = col
        col.find.return_value = [
            {'_id': ObjectId(), 'supplier_code': 'SUP-001', 'buyer_air8_code': 'BUYER-A',
             'client_number': '1001', 'customer_name': 'Client A', 'client_customer_no': '',
             'customer_address1': '', 'customer_address2': '', 'customer_city': '', 'customer_state': '',
             'customer_zip': '', 'customer_phone': '', 'client_terms_code': '', 'client_terms_desc': '',
             'customer_store_no': '', 'customer_dept_no': ''},
            {'_id': ObjectId(), 'supplier_code': 'SUP-001', 'buyer_air8_code': 'BUYER-B',
             'client_number': '1002', 'customer_name': 'Client B', 'client_customer_no': '',
             'customer_address1': '', 'customer_address2': '', 'customer_city': '', 'customer_state': '',
             'customer_zip': '', 'customer_phone': '', 'client_terms_code': '', 'client_terms_desc': '',
             'customer_store_no': '', 'customer_dept_no': ''},
        ]

        resp = logged_in_client.post('/fcb/api/export',
            data=json.dumps({'financing_nos': ['FN001', 'FN002']}),
            content_type='application/json'
        )
        assert resp.status_code == 200
        assert 'zip' in resp.content_type or 'octet-stream' in resp.content_type

    @patch('backend.app.services.fcb_service.requests.get')
    @patch('backend.app.services.fcb_service._get_collection')
    def test_export_partial_unmatched_still_succeeds(self, mock_col, mock_get, logged_in_client):
        """部分交易未匹配到客户时，其余交易仍应正常导出"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = [{
            'data': json.dumps([
                {'supplier_code': 'SUP-001', 'buyer_code': 'BUYER-A', 'buyer_name': 'Buyer A',
                 'invoice_number': 'INV-001', 'invoice_amount': '100', 'invoice_date': '2026-01-01'},
                {'supplier_code': 'SUP-999', 'buyer_code': 'UNKNOWN', 'buyer_name': 'Unknown Buyer',
                 'invoice_number': 'INV-999', 'invoice_amount': '999', 'invoice_date': '2026-01-01'},
            ])
        }]
        mock_get.return_value = mock_response

        col = MagicMock()
        mock_col.return_value = col
        col.find.return_value = [
            {'_id': ObjectId(), 'supplier_code': 'SUP-001', 'buyer_air8_code': 'BUYER-A',
             'client_number': '1001', 'customer_name': 'Client A', 'client_customer_no': '',
             'customer_address1': '', 'customer_address2': '', 'customer_city': '', 'customer_state': '',
             'customer_zip': '', 'customer_phone': '', 'client_terms_code': '', 'client_terms_desc': '',
             'customer_store_no': '', 'customer_dept_no': ''},
        ]

        resp = logged_in_client.post('/fcb/api/export',
            data=json.dumps({'financing_nos': ['FN001', 'FN002']}),
            content_type='application/json'
        )
        assert resp.status_code == 200
        assert 'spreadsheetml' in resp.content_type or 'octet-stream' in resp.content_type

    @patch('backend.app.services.fcb_service.requests.get')
    @patch('backend.app.services.fcb_service._get_collection')
    def test_export_all_unmatched_raises(self, mock_col, mock_get, logged_in_client):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = [{
            'data': json.dumps([
                {'supplier_code': 'SUP-999', 'buyer_code': 'UNKNOWN', 'buyer_name': 'Unknown Buyer',
                 'invoice_number': 'INV-999', 'invoice_amount': '999', 'invoice_date': '2026-01-01'},
            ])
        }]
        mock_get.return_value = mock_response

        col = MagicMock()
        mock_col.return_value = col
        col.find.return_value = []

        resp = logged_in_client.post('/fcb/api/export',
            data=json.dumps({'financing_nos': ['FN001']}),
            content_type='application/json'
        )
        assert resp.status_code == 500
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest backend/tests/test_fcb.py -k "same_supplier_code_different_buyers or partial_unmatched or all_unmatched" -v`
Expected: FAIL（当前实现按 `supplier_code` 一对一取客户，两个 buyer 会被同一条 `find()` 结果里的最后一条覆盖，无法各自生成正确文件）

- [ ] **Step 3: 实现**

在 `backend/app/services/fcb_service.py` 顶部（`import pandas as pd` 之后）新增：

```python
import logging

logger = logging.getLogger(__name__)
```

重写 `export_transactions`（`fcb_service.py:274-336`）：

```python
    @staticmethod
    def export_transactions(financing_nos=None):
        """导出交易数据为 Excel（单客户）或 ZIP（多客户）"""

        # 1. 调用 n8n API
        transactions = FCBService._call_n8n_api(financing_nos)
        if not transactions:
            raise ValueError('No transaction data found')

        # 2. 按 supplier_code 分组
        groups = {}
        for txn in transactions:
            code = txn.get('supplier_code', '')
            groups.setdefault(code, []).append(txn)

        # 3. 批量查询候选客户（一个 supplier_code 可能对应多个 buyer）
        col = _get_collection()
        supplier_codes = list(groups.keys())
        candidates_map = {}
        for c in col.find({'supplier_code': {'$in': supplier_codes}}):
            candidates_map.setdefault(c['supplier_code'], []).append(c)

        # 4. 逐笔交易匹配客户，按命中的客户 _id 重新分组
        matched_groups = {}
        unmatched = []
        for code, txns in groups.items():
            candidates = candidates_map.get(code, [])
            for txn in txns:
                client, ambiguous = match_client_for_transaction(
                    txn.get('buyer_code', ''), txn.get('buyer_name', ''), candidates
                )
                if not client:
                    unmatched.append({
                        'supplier_code': code,
                        'buyer_code': txn.get('buyer_code', ''),
                        'buyer_name': txn.get('buyer_name', ''),
                        'ambiguous': ambiguous,
                    })
                    continue
                cid = client['_id']
                matched_groups.setdefault(cid, {'client': client, 'txns': []})
                matched_groups[cid]['txns'].append(txn)

        if not matched_groups:
            detail = ', '.join(
                f"{u['supplier_code']}/{u['buyer_code'] or u['buyer_name']}" for u in unmatched
            )
            raise ValueError(f'No client records matched for: {detail}')

        if unmatched:
            logger.warning('FCB export: %d transaction(s) unmatched: %s', len(unmatched), unmatched)

        # 5. 生成 Excel 文件
        files = []
        today = datetime.utcnow().strftime('%Y%m%d')
        for group in matched_groups.values():
            client = group['client']
            excel_buf = _build_excel(client, group['txns'])
            client_number = client.get('client_number', 'unknown')
            customer_name = client.get('customer_name', 'unknown')
            # 清理文件名中的非法字符
            safe_name = ''.join(c if c.isalnum() or c in ' _-' else '_' for c in customer_name)
            filename = f'{client_number}_{safe_name}_{today}.xlsx'
            files.append((filename, excel_buf))

        # 6. 返回
        if len(files) == 1:
            fname, buf = files[0]
            return (
                buf,
                'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                fname,
            )
        else:
            zip_buf = io.BytesIO()
            with zipfile.ZipFile(zip_buf, 'w', zipfile.ZIP_DEFLATED) as zf:
                for fname, buf in files:
                    zf.writestr(fname, buf.read())
            zip_buf.seek(0)
            return (
                zip_buf,
                'application/zip',
                f'fcb_export_{today}.zip',
            )
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest backend/tests/test_fcb.py -v`
Expected: PASS（全部用例，包括 Task 1-3 新增的用例与原有用例）

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/fcb_service.py backend/tests/test_fcb.py
git commit -m "feat: FCB 导出改为按 supplier_code+buyer 匹配客户记录"
```

---

### Task 5: `daily_export_service._generate_excel()` 复用共享匹配函数

_覆盖需求：3.1, 3.2, 3.3, 3.5_

**Files:**
- Modify: `backend/app/services/daily_export_service.py:153-198`（`_generate_excel`）
- Test: `backend/tests/test_daily_export.py`

**Interfaces:**
- Consumes: `match_client_for_transaction(buyer_code, buyer_name, candidates)`（Task 3 产出）

- [ ] **Step 1: 写失败测试**

在 `backend/tests/test_daily_export.py` 中，先给顶部的 `SAMPLE_TRANSACTIONS_JSON`/`SAMPLE_CLIENT` 补充 buyer 字段，并新增测试类：

```python
class TestGenerateExcelBuyerMatching:

    @patch('backend.app.services.fcb_service._get_collection')
    def test_matches_by_buyer_air8_code(self, mock_col, app):
        from backend.app.services.daily_export_service import _generate_excel

        col = MagicMock()
        mock_col.return_value = col
        col.find.return_value = [
            {**SAMPLE_CLIENT.copy(), '_id': ObjectId(), 'buyer_air8_code': 'BUYER-A'},
        ]

        transactions = [
            {'supplier_code': 'C0001496', 'buyer_code': 'BUYER-A', 'buyer_name': 'Buyer A',
             'invoice_number': 'A0123LF036', 'invoice_amount': '100', 'invoice_date': '2026-01-01'},
        ]

        with app.app_context():
            buf, filename = _generate_excel(transactions)

        assert buf is not None
        assert filename.endswith('.xlsx')

    @patch('backend.app.services.fcb_service._get_collection')
    def test_same_supplier_different_buyers_produce_zip(self, mock_col, app):
        from backend.app.services.daily_export_service import _generate_excel

        col = MagicMock()
        mock_col.return_value = col
        col.find.return_value = [
            {**SAMPLE_CLIENT.copy(), '_id': ObjectId(), 'client_number': '1001',
             'customer_name': 'Client A', 'buyer_air8_code': 'BUYER-A'},
            {**SAMPLE_CLIENT.copy(), '_id': ObjectId(), 'client_number': '1002',
             'customer_name': 'Client B', 'buyer_air8_code': 'BUYER-B'},
        ]

        transactions = [
            {'supplier_code': 'C0001496', 'buyer_code': 'BUYER-A', 'buyer_name': 'Buyer A',
             'invoice_number': 'INV-001', 'invoice_amount': '100', 'invoice_date': '2026-01-01'},
            {'supplier_code': 'C0001496', 'buyer_code': 'BUYER-B', 'buyer_name': 'Buyer B',
             'invoice_number': 'INV-002', 'invoice_amount': '200', 'invoice_date': '2026-01-02'},
        ]

        with app.app_context():
            buf, filename = _generate_excel(transactions)

        assert buf is not None
        assert filename.endswith('.zip')

    @patch('backend.app.services.fcb_service._get_collection')
    def test_unmatched_buyer_skipped_not_fatal(self, mock_col, app):
        from backend.app.services.daily_export_service import _generate_excel

        col = MagicMock()
        mock_col.return_value = col
        col.find.return_value = [
            {**SAMPLE_CLIENT.copy(), '_id': ObjectId(), 'buyer_air8_code': 'BUYER-A'},
        ]

        transactions = [
            {'supplier_code': 'C0001496', 'buyer_code': 'BUYER-A', 'buyer_name': 'Buyer A',
             'invoice_number': 'INV-001', 'invoice_amount': '100', 'invoice_date': '2026-01-01'},
            {'supplier_code': 'C0001496', 'buyer_code': 'BUYER-ZZZ', 'buyer_name': 'Unknown',
             'invoice_number': 'INV-002', 'invoice_amount': '200', 'invoice_date': '2026-01-02'},
        ]

        with app.app_context():
            buf, filename = _generate_excel(transactions)

        assert buf is not None
        assert filename.endswith('.xlsx')
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest backend/tests/test_daily_export.py -k BuyerMatching -v`
Expected: FAIL（当前实现按 `supplier_code` 一对一取客户，无法区分两个 buyer，`test_same_supplier_different_buyers_produce_zip` 只会生成一个文件而非 zip）

- [ ] **Step 3: 实现**

重写 `backend/app/services/daily_export_service.py` 的 `_generate_excel`（第 153-198 行）：

```python
def _generate_excel(transactions):
    """复用 fcb_service 逻辑生成 Excel/ZIP，返回 (BytesIO, filename)"""
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
    for code, txns in groups.items():
        candidates = candidates_map.get(code, [])
        for txn in txns:
            client, ambiguous = match_client_for_transaction(
                txn.get('buyer_code', ''), txn.get('buyer_name', ''), candidates
            )
            if not client:
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
        return files[0][1], files[0][0]

    # 多客户 → ZIP
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for fname, buf in files:
            zf.writestr(fname, buf.read())
    zip_buf.seek(0)
    return zip_buf, f'fcb_export_{today}.zip'
```

`logger` 已在文件顶部定义（沿用现有 `logging.getLogger(__name__)`），无需新增导入。

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest backend/tests/test_daily_export.py -v`
Expected: PASS（全部用例，包括原有 `TestGenerateExcel` 用例）

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/daily_export_service.py backend/tests/test_daily_export.py
git commit -m "refactor: daily_export_service 复用 match_client_for_transaction 消除重复匹配逻辑"
```

---

### Task 6: 前端表单新增 buyer_air8_code 字段

_覆盖需求：1.1, 1.2_

**Files:**
- Modify: `backend/app/templates/fcb/clients.html:109-133`（`#clientModal` 表单）、`:210`（`FIELDS` 数组）
- Modify: `backend/app/i18n/zh.json`、`backend/app/i18n/en.json`
- Test: `backend/tests/test_fcb.py`（页面加载烟雾测试，确认不报错）

**Interfaces:**
- 无新增代码接口；仅前端表单与文案

- [ ] **Step 1: 写失败测试**

在 `backend/tests/test_fcb.py` 的 `TestFCBPages` 类中新增：

```python
    def test_clients_page_contains_buyer_air8_code_field(self, logged_in_client):
        resp = logged_in_client.get('/fcb/clients')
        assert b'f_buyer_air8_code' in resp.data
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest backend/tests/test_fcb.py::TestFCBPages -v`
Expected: FAIL（模板中还没有 `f_buyer_air8_code` 输入框）

- [ ] **Step 3: 实现**

在 `backend/app/templates/fcb/clients.html` 的 `#clientModal` 表单中，`SUPPLIER CODE` 输入框所在行（第 63-72 行）之后插入新的一行：

```html
                    <div class="row">
                        <div class="col-md-6 mb-3">
                            <label class="form-label">{{ _('fcb.clients.buyer_air8_code') }}</label>
                            <input type="text" class="form-control" id="f_buyer_air8_code">
                        </div>
                    </div>
```

修改第 210 行的 `FIELDS` 数组：

```javascript
var FIELDS = ['supplier_code','buyer_air8_code','client_number','client_customer_no','customer_name','customer_address1','customer_address2','customer_city','customer_state','customer_zip','customer_phone','client_terms_code','client_terms_desc','customer_store_no','customer_dept_no'];
```

同时把列表表格加一列展示（第 30-38 行表头 + 第 179-190 行行渲染），在 `Client Number` 列之后插入 `Buyer Air8 Code` 列：

表头（约第 30-38 行，找到 `<th>{{ _('fcb.clients.client_number') }}</th>` 之后插入）：

```html
<th>{{ _('fcb.clients.buyer_air8_code') }}</th>
```

行渲染（`loadClients` 函数内，约第 182 行 `client_number` 之后插入）：

```javascript
            html += '<td>' + (c.buyer_air8_code||'') + '</td>';
```

在 `backend/app/i18n/en.json` 的 `fcb.clients.customer_store_no` 那一行之前新增：

```json
  "fcb.clients.buyer_air8_code": "Buyer Air8 Code",
```

在 `backend/app/i18n/zh.json` 对应位置新增：

```json
  "fcb.clients.buyer_air8_code": "买方 Air8 编码",
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest backend/tests/test_fcb.py -v`
Expected: PASS（全部用例）

- [ ] **Step 5: 提交**

```bash
git add backend/app/templates/fcb/clients.html backend/app/i18n/zh.json backend/app/i18n/en.json backend/tests/test_fcb.py
git commit -m "feat: FCB 客户管理页面新增 Buyer Air8 Code 字段"
```

---

### Task 7: 全量回归 + 需求基线同步

_覆盖需求：全部（1-3）_

**Files:**
- Modify: `docs/system/requirements.md`（REQ-FCB-001、REQ-FCB-002 章节 + 第 15 章变更记录）

**Interfaces:**
- 无代码接口；仅文档同步

- [ ] **Step 1: 跑全量测试确认无回归**

Run: `pytest backend/tests/ -v`
Expected: 全部 PASS，无失败无 error

- [ ] **Step 2: 更新 `docs/system/requirements.md` 的 REQ-FCB-001**

在 `docs/system/requirements.md` 第 459-469 行的 `REQ-FCB-001` 验收标准列表中，第 3 条之后插入新条目（原第 3、4 条依次调整措辞）：

```markdown
3. 当 提交的 `(supplier_code, buyer_air8_code)`（`buyer_air8_code` 非空时）或 `(supplier_code, customer_name)`（`buyer_air8_code` 为空时）组合已存在 时，系统应 拒绝创建/更新并返回 409 冲突错误。
4. 当 用户提交 `PUT /fcb/api/clients/<client_id>` 更新客户 时，系统应 按 `_id` 定位并更新字段（不允许覆盖 `_id`），执行与创建相同的组合查重校验，刷新 `updated_at`；客户不存在时返回 404，查重冲突时返回 409。
```

（删除原第 3 条"仅按 supplier_code 查重"的表述，删除原第 4 条中"客户不存在时返回 404"的旧措辞，替换为上述两条）

- [ ] **Step 3: 更新 `docs/system/requirements.md` 的 REQ-FCB-002**

在第 471-481 行的 `REQ-FCB-002` 验收标准列表中，第 3 条之后插入：

```markdown
3. 当 交易数据按 `supplier_code` 分组并查出候选客户记录（同一 `supplier_code` 下可能有多条，按 buyer 区分）后，若某候选记录填写了 `buyer_air8_code`，系统应 仅用其与交易的 `buyer_code` 精确比较判定是否命中；若候选记录未填写 `buyer_air8_code`，系统应 用其 `customer_name` 与交易的 `buyer_name`（均去首尾空格、忽略大小写）比较判定是否命中。
4. 当 某笔交易未匹配到任何候选客户，或匹配到多条候选客户（歧义） 时，系统应 将该笔交易计入未匹配列表并跳过，不中断本次导出其余交易的处理；当本次导出涉及的全部交易均未匹配 时，系统应 抛出错误并列出未匹配详情。
5. 当 导出结果中存在多个不同客户记录（含同一 `supplier_code` 下不同 buyer 的情况） 时，系统应 按命中的客户记录（而非仅 `supplier_code`）分组生成 Excel，返回单个 `.xlsx` 或打包为 ZIP。
```

（原第 3 条"某些分组找不到对应客户"表述并入新第 4 条；原第 5 条"匹配到的客户分组"表述由新第 5 条取代）

- [ ] **Step 4: 登记变更记录**

在第 647-651 行的变更记录表末尾新增一行：

```markdown
| 2026-08-17 | `2026-08-17-fcb-buyer-matching-design.md` | FCB 客户支持同一 supplier_code 对应多个 buyer（新增 `buyer_air8_code` 字段），CRUD 查重与导出匹配逻辑从单一 supplier_code 改为 supplier_code + buyer 组合匹配 |
```

- [ ] **Step 5: 提交**

```bash
git add docs/system/requirements.md
git commit -m "docs: 同步 FCB buyer 匹配需求变更进基线文档"
```
