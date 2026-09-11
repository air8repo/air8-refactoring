"""
Tests for ImportService._import_financing storing the new
collection_period / financing_interest fields synced from n8n.
"""
import pandas as pd
from unittest.mock import patch, MagicMock
from bson import Decimal128

from backend.app.services.import_service import ImportService


def _run_import(rows):
    df = pd.DataFrame(rows)
    mock_mongo = MagicMock()
    mock_mongo.refactoring_financing_order.find_one.return_value = None
    with patch('backend.app.services.import_service.get_mongo', return_value=mock_mongo):
        with patch.object(ImportService, '_post_process_financing_records'):
            ImportService()._import_financing(df)
    return [c.args[0] for c in mock_mongo.refactoring_financing_order.insert_one.call_args_list]


def _base_row(**overrides):
    row = {
        'Finance Request Number': 'RZ001',
        'Invoice Number': 'INV-001',
        'Supplier Code': 'S001',
        'Buyer Code': 'B001',
    }
    row.update(overrides)
    return row


def test_collection_period_stored_from_source_column():
    inserted = _run_import([_base_row(**{'Collection Period': 5})])
    assert inserted[0]['collection_period'] == 5


def test_collection_period_missing_defaults_to_zero():
    inserted = _run_import([_base_row()])
    assert inserted[0]['collection_period'] == 0


def test_financing_interest_stored_from_source_column():
    inserted = _run_import([_base_row(**{'Financing Interest': 33.70})])
    assert inserted[0]['financing_interest'] == Decimal128('33.7')


def test_financing_interest_missing_defaults_to_zero():
    inserted = _run_import([_base_row()])
    assert inserted[0]['financing_interest'] == Decimal128('0')
