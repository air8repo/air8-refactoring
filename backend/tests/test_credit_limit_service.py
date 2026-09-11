"""额度管理聚合服务测试"""
from unittest.mock import MagicMock
import pytest


class TestGetBuyerSupplierPairs:

    def test_pair_sums_earmark_and_utilization_from_deals(self):
        from backend.app.services.credit_limit_service import get_buyer_supplier_pairs
        mongo = _make_mongo_with_repayments(
            onboard_configs=[{'uid': 'U1', 'refactoring_limit': 100000, 'buyer_code': 'B1',
                               'obligor_name': 'Buyer One', 'supplier_code': 'S1', 'seller_name': 'Seller One'}],
            financing_orders=[
                {'uid': 'U1', 'buyer_code': 'B1', 'supplier_code': 'S1', 'buyer_name': 'Buyer One',
                 'supplier_name': 'Seller One', 'finance_request_number': 'FR1', 'invoice_number': 'INV1',
                 'financing_amount': 1000, 'status': 'eligible', 'bank_finance_status': ''},
                {'uid': 'U1', 'buyer_code': 'B1', 'supplier_code': 'S1', 'buyer_name': 'Buyer One',
                 'supplier_name': 'Seller One', 'finance_request_number': 'FR2', 'invoice_number': 'INV2',
                 'financing_amount': 2000, 'status': 'funded before', 'bank_finance_status': 'Loan booked'},
            ],
        )
        pairs = get_buyer_supplier_pairs(mongo)
        assert len(pairs) == 1
        p = pairs[0]
        assert p['uid'] == 'U1'
        assert p['reserved'] == 1000
        assert p['actual'] == 2000
        assert p['total_occupied'] == 3000
        assert p['celling'] == 100000
        assert p['headroom'] == 97000
        assert abs(p['occupancy_rate'] - 0.03) < 1e-9

    def test_total_occupied_subtracts_to_be_settled_on_db(self):
        from backend.app.services.credit_limit_service import get_buyer_supplier_pairs
        mongo = _make_mongo_with_repayments(
            onboard_configs=[{'uid': 'U1', 'refactoring_limit': 100000, 'buyer_code': 'B1',
                               'obligor_name': 'Buyer One'}],
            financing_orders=[
                {'uid': 'U1', 'buyer_code': 'B1', 'buyer_name': 'Buyer One',
                 'finance_request_number': 'FR1', 'invoice_number': 'INV1',
                 'financing_amount': 1000, 'status': 'funded before',
                 'bank_finance_status': 'Loan booked', 'settled_in_air8': 'Settled'},
            ],
            repayment_records=[
                {'finance_request_number': 'FR1', 'settlement_amount': 400, 'created_at': None},
            ],
        )
        pairs = get_buyer_supplier_pairs(mongo)
        p = pairs[0]
        assert p['actual'] == 1000
        assert p['total_occupied'] == 600  # 0(预占) + 1000(实占) - 400(待结清)

    def test_onboard_only_uid_has_zero_occupied_and_full_headroom(self):
        from backend.app.services.credit_limit_service import get_buyer_supplier_pairs
        mongo = _make_mongo_with_repayments(
            onboard_configs=[{'uid': 'U2', 'refactoring_limit': 200000, 'buyer_code': 'B2',
                               'obligor_name': 'Buyer Two', 'supplier_code': 'S2', 'seller_name': 'Seller Two'}],
        )
        pairs = get_buyer_supplier_pairs(mongo)
        assert len(pairs) == 1
        p = pairs[0]
        assert p['celling'] == 200000
        assert p['reserved'] == 0
        assert p['actual'] == 0
        assert p['headroom'] == 200000
        assert p['occupancy_rate'] == 0.0

    def test_deal_only_uid_has_none_headroom_and_occupancy(self):
        from backend.app.services.credit_limit_service import get_buyer_supplier_pairs
        mongo = _make_mongo_with_repayments(
            financing_orders=[
                {'uid': 'U3', 'buyer_code': 'B3', 'buyer_name': 'Buyer Three',
                 'finance_request_number': 'FR1', 'invoice_number': 'INV3',
                 'financing_amount': 500, 'status': 'eligible', 'bank_finance_status': ''},
            ],
        )
        pairs = get_buyer_supplier_pairs(mongo)
        p = pairs[0]
        assert p['celling'] == 0
        assert p['reserved'] == 500
        assert p['headroom'] is None
        assert p['occupancy_rate'] is None

    def test_buyer_filter_matches_case_insensitively(self):
        from backend.app.services.credit_limit_service import get_buyer_supplier_pairs
        mongo = _make_mongo_with_repayments(
            onboard_configs=[
                {'uid': 'U1', 'refactoring_limit': 1000, 'buyer_code': 'B1', 'obligor_name': 'Amazon Services'},
                {'uid': 'U2', 'refactoring_limit': 2000, 'buyer_code': 'B2', 'obligor_name': 'Homegoods Inc'},
            ],
        )
        pairs = get_buyer_supplier_pairs(mongo, buyer_filter='amazon')
        assert len(pairs) == 1
        assert pairs[0]['buyer_name'] == 'Amazon Services'

    def test_target_list_status_n_pair_is_included(self):
        from backend.app.services.credit_limit_service import get_buyer_supplier_pairs
        mongo = _make_mongo_with_repayments(
            onboard_configs=[{'uid': 'U1', 'refactoring_limit': 0, 'buyer_code': 'B1',
                               'obligor_name': 'Buyer One', 'target_list_status': 'N'}],
        )
        pairs = get_buyer_supplier_pairs(mongo)
        assert len(pairs) == 1
        assert pairs[0]['uid'] == 'U1'

    def test_currency_is_always_usd(self):
        from backend.app.services.credit_limit_service import get_buyer_supplier_pairs
        mongo = _make_mongo_with_repayments(onboard_configs=[{'uid': 'U1', 'refactoring_limit': 1000, 'buyer_code': 'B1'}])
        pairs = get_buyer_supplier_pairs(mongo)
        assert pairs[0]['currency'] == 'USD'

    def test_detail_fields_carry_raw_financing_order_identifiers(self):
        from backend.app.services.credit_limit_service import get_buyer_supplier_pairs
        mongo = _make_mongo_with_repayments(
            onboard_configs=[{'uid': 'U1', 'refactoring_limit': 100000, 'buyer_code': 'B1',
                               'obligor_name': 'Amazon.com Services LLC', 'seller_name': 'Photonverse Inc'}],
            financing_orders=[
                {'uid': 'U1', 'buyer_code': 'B1', 'buyer_name': 'AMAZON.COM SERVICES LLC ',
                 'supplier_name': 'PHOTONVERSE, INC.', 'financing_currency': 'usd',
                 'finance_request_number': 'FR1', 'invoice_number': 'INV1',
                 'financing_amount': 1000, 'status': 'eligible', 'bank_finance_status': ''},
            ],
        )
        pairs = get_buyer_supplier_pairs(mongo)
        p = pairs[0]
        assert p['buyer_name'] == 'Amazon.com Services LLC'
        assert p['supplier_name'] == 'Photonverse Inc'
        assert p['currency'] == 'USD'
        assert p['detail_buyer_name'] == 'AMAZON.COM SERVICES LLC '
        assert p['detail_supplier_name'] == 'PHOTONVERSE, INC.'
        assert p['detail_currency'] == 'usd'

    def test_reserved_bucket_excludes_orders_not_eligible(self):
        from backend.app.services.credit_limit_service import get_buyer_supplier_pairs
        mongo = _make_mongo_with_repayments(
            onboard_configs=[{'uid': 'U1', 'refactoring_limit': 100000, 'buyer_code': 'B1',
                               'obligor_name': 'Buyer One'}],
            financing_orders=[
                {'uid': 'U1', 'buyer_code': 'B1', 'buyer_name': 'Buyer One',
                 'finance_request_number': 'FR1', 'invoice_number': 'INV1',
                 'financing_amount': 1000, 'status': 'partial paid', 'bank_finance_status': ''},
            ],
        )
        pairs = get_buyer_supplier_pairs(mongo)
        assert pairs[0]['reserved'] == 0
        assert pairs[0]['total_occupied'] == 0

    def test_deals_param_overrides_internal_get_deal_rows_call(self):
        from backend.app.services.credit_limit_service import get_buyer_supplier_pairs
        mongo = _make_mongo_with_repayments(
            onboard_configs=[{'uid': 'U1', 'refactoring_limit': 100000, 'buyer_code': 'B1',
                               'obligor_name': 'Buyer One'}],
        )
        precomputed_deals = [
            {'uid': 'U1', 'buyer_code': 'B1', 'buyer_name': 'Buyer One', 'supplier_code': '',
             'supplier_name': '', 'earmark_forecast': 500.0, 'credit_utilization': 0.0,
             'to_be_settled_on_db': None, 'total_os': 500.0,
             'detail_buyer_name': '', 'detail_supplier_name': '', 'detail_currency': ''},
        ]
        pairs = get_buyer_supplier_pairs(mongo, deals=precomputed_deals)
        assert pairs[0]['reserved'] == 500.0
        # mongo.refactoring_financing_order.find should NOT have been called, since
        # get_deal_rows (which reads it) was skipped entirely in favor of the precomputed deals
        mongo.refactoring_financing_order.find.assert_not_called()


class TestToFloat:

    def test_converts_decimal128(self):
        from backend.app.services.credit_limit_service import _to_float
        from bson import Decimal128
        assert _to_float(Decimal128('123.45')) == 123.45

    def test_none_returns_none(self):
        from backend.app.services.credit_limit_service import _to_float
        assert _to_float(None) is None

    def test_empty_string_returns_none(self):
        from backend.app.services.credit_limit_service import _to_float
        assert _to_float('') is None

    def test_plain_number_converts(self):
        from backend.app.services.credit_limit_service import _to_float
        assert _to_float(42) == 42.0

    def test_invalid_string_returns_none(self):
        from backend.app.services.credit_limit_service import _to_float
        assert _to_float('not-a-number') is None


class TestAggregateByBuyer:

    def test_sums_multiple_pairs_for_same_buyer(self):
        from backend.app.services.credit_limit_service import aggregate_by_buyer
        pairs = [
            {'uid': 'U1', 'buyer_code': 'B1', 'buyer_name': 'Buyer One', 'supplier_code': 'S1',
             'supplier_name': 'Seller One', 'currency': 'USD', 'celling': 100000, 'reserved': 1000,
             'actual': 2000, 'total_occupied': 3000, 'headroom': 97000, 'occupancy_rate': 0.03},
            {'uid': 'U2', 'buyer_code': 'B1', 'buyer_name': 'Buyer One', 'supplier_code': 'S2',
             'supplier_name': 'Seller Two', 'currency': 'USD', 'celling': 50000, 'reserved': 0,
             'actual': 0, 'total_occupied': 0, 'headroom': 50000, 'occupancy_rate': 0.0},
        ]
        buyers = aggregate_by_buyer(pairs)
        assert len(buyers) == 1
        b = buyers[0]
        assert b['buyer_code'] == 'B1'
        assert b['buyer_name'] == 'Buyer One'
        assert b['celling'] == 150000
        assert b['reserved'] == 1000
        assert b['actual'] == 2000
        assert b['total_occupied'] == 3000
        assert b['headroom'] == 147000
        assert abs(b['occupancy_rate'] - 0.02) < 1e-9
        assert len(b['pairs']) == 2

    def test_zero_celling_buyer_has_none_headroom_and_occupancy(self):
        from backend.app.services.credit_limit_service import aggregate_by_buyer
        pairs = [
            {'uid': 'U1', 'buyer_code': 'B1', 'buyer_name': 'Buyer One', 'supplier_code': 'S1',
             'supplier_name': 'Seller One', 'currency': 'USD', 'celling': 0, 'reserved': 500,
             'actual': 0, 'total_occupied': 500, 'headroom': None, 'occupancy_rate': None},
        ]
        buyers = aggregate_by_buyer(pairs)
        assert buyers[0]['headroom'] is None
        assert buyers[0]['occupancy_rate'] is None

    def test_sorted_by_occupancy_rate_descending_with_none_last(self):
        from backend.app.services.credit_limit_service import aggregate_by_buyer
        pairs = [
            {'uid': 'U1', 'buyer_code': 'LOW', 'buyer_name': 'Low', 'supplier_code': 'S1',
             'supplier_name': 'S', 'currency': 'USD', 'celling': 1000, 'reserved': 100,
             'actual': 0, 'total_occupied': 100, 'headroom': 900, 'occupancy_rate': 0.1},
            {'uid': 'U2', 'buyer_code': 'HIGH', 'buyer_name': 'High', 'supplier_code': 'S2',
             'supplier_name': 'S', 'currency': 'USD', 'celling': 1000, 'reserved': 900,
             'actual': 0, 'total_occupied': 900, 'headroom': 100, 'occupancy_rate': 0.9},
            {'uid': 'U3', 'buyer_code': 'NA', 'buyer_name': 'NoLimit', 'supplier_code': 'S3',
             'supplier_name': 'S', 'currency': 'USD', 'celling': 0, 'reserved': 0,
             'actual': 0, 'total_occupied': 0, 'headroom': None, 'occupancy_rate': None},
        ]
        buyers = aggregate_by_buyer(pairs)
        assert [b['buyer_code'] for b in buyers] == ['HIGH', 'LOW', 'NA']

    def test_empty_pairs_returns_empty_list(self):
        from backend.app.services.credit_limit_service import aggregate_by_buyer
        assert aggregate_by_buyer([]) == []


class TestCheckWarnings:

    def test_filters_rows_at_or_above_threshold(self):
        from backend.app.services.credit_limit_service import check_warnings
        buyer_rows = [
            {'buyer_code': 'B1', 'occupancy_rate': 0.95},
            {'buyer_code': 'B2', 'occupancy_rate': 0.5},
            {'buyer_code': 'B3', 'occupancy_rate': 0.9},
        ]
        pair_rows = [
            {'uid': 'U1', 'occupancy_rate': 0.99},
            {'uid': 'U2', 'occupancy_rate': 0.1},
        ]
        result = check_warnings(buyer_rows, pair_rows, threshold=0.9)
        assert [b['buyer_code'] for b in result['buyers']] == ['B1', 'B3']
        assert [p['uid'] for p in result['pairs']] == ['U1']

    def test_excludes_none_occupancy_rate(self):
        from backend.app.services.credit_limit_service import check_warnings
        buyer_rows = [{'buyer_code': 'B1', 'occupancy_rate': None}]
        result = check_warnings(buyer_rows, [], threshold=0.9)
        assert result['buyers'] == []

    def test_no_rows_over_threshold_returns_empty_lists(self):
        from backend.app.services.credit_limit_service import check_warnings
        buyer_rows = [{'buyer_code': 'B1', 'occupancy_rate': 0.1}]
        result = check_warnings(buyer_rows, [], threshold=0.9)
        assert result == {'buyers': [], 'pairs': []}


def test_credit_warning_threshold_default_is_point_nine(app):
    assert app.config['CREDIT_WARNING_THRESHOLD'] == 0.9


def _make_mongo_with_repayments(onboard_configs=None, financing_orders=None,
                                 bank_statements=None, repayment_records=None):
    mongo = MagicMock()
    mongo.refactoring_onboard_config.find.return_value = onboard_configs or []
    mongo.refactoring_financing_order.find.return_value = financing_orders or []
    mongo.refactoring_bank_statement.find.return_value = bank_statements or []
    mongo.refactoring_bank_repayment_record.find.return_value = repayment_records or []
    return mongo


class TestGetDealRows:

    def test_financing_amount_uses_bank_statement_when_matched(self):
        from backend.app.services.credit_limit_service import get_deal_rows
        mongo = _make_mongo_with_repayments(
            financing_orders=[
                {'uid': 'U1', 'buyer_code': 'B1', 'buyer_name': 'Buyer One',
                 'supplier_code': 'S1', 'supplier_name': 'Seller One',
                 'finance_request_number': 'FR1', 'invoice_number': 'INV1',
                 'financing_amount': 1000, 'status': 'eligible',
                 'bank_finance_status': '', 'financing_currency': 'USD'},
            ],
            bank_statements=[
                {'invoice': {'seller_reference': 'INV1', 'original_amount': 2000, 'settlement_status': ''},
                 'finance': {'advance_ratio_pct': 90, 'status': 'Booking requested accepted'}},
            ],
        )
        deals = get_deal_rows(mongo)
        assert len(deals) == 1
        d = deals[0]
        assert d['financing_amount'] == 1800  # 2000 * 90 / 100
        assert d['earmark_forecast'] == 1800
        assert d['credit_utilization'] == 0
        assert d['finance_status_display'] == 'Booking requested accepted'
        assert d['settlement_status'] == ''

    def test_financing_amount_falls_back_to_financing_order_when_no_bank_statement(self):
        from backend.app.services.credit_limit_service import get_deal_rows
        mongo = _make_mongo_with_repayments(
            financing_orders=[
                {'uid': 'U1', 'buyer_code': 'B1', 'buyer_name': 'Buyer One',
                 'finance_request_number': 'FR1', 'invoice_number': 'INV1',
                 'financing_amount': 1000, 'status': 'eligible', 'bank_finance_status': ''},
            ],
        )
        deals = get_deal_rows(mongo)
        assert deals[0]['financing_amount'] == 1000
        assert deals[0]['earmark_forecast'] == 1000
        assert deals[0]['finance_status_display'] == ''
        assert deals[0]['settlement_status'] == ''

    def test_earmark_forecast_zero_when_not_eligible(self):
        from backend.app.services.credit_limit_service import get_deal_rows
        mongo = _make_mongo_with_repayments(
            financing_orders=[
                {'uid': 'U1', 'buyer_code': 'B1', 'buyer_name': 'Buyer One',
                 'finance_request_number': 'FR1', 'invoice_number': 'INV1',
                 'financing_amount': 1000, 'status': 'funded before', 'bank_finance_status': ''},
            ],
        )
        deals = get_deal_rows(mongo)
        assert deals[0]['earmark_forecast'] == 0
        assert deals[0]['status_display'] == 'Funded Successfully'

    def test_credit_utilization_uses_financing_amount_when_loan_booked(self):
        from backend.app.services.credit_limit_service import get_deal_rows
        mongo = _make_mongo_with_repayments(
            financing_orders=[
                {'uid': 'U1', 'buyer_code': 'B1', 'buyer_name': 'Buyer One',
                 'finance_request_number': 'FR1', 'invoice_number': 'INV1',
                 'financing_amount': 1000, 'status': 'funded before',
                 'bank_finance_status': 'Loan booked'},
            ],
            bank_statements=[
                {'invoice': {'seller_reference': 'INV1', 'original_amount': 2000},
                 'finance': {'advance_ratio_pct': 90, 'status': 'Loan booked'}},
            ],
        )
        deals = get_deal_rows(mongo)
        d = deals[0]
        assert d['earmark_forecast'] == 0
        assert d['credit_utilization'] == 1800
        assert d['total_os'] == 1800

    def test_to_be_settled_on_db_requires_settled_in_air8_and_loan_booked(self):
        from backend.app.services.credit_limit_service import get_deal_rows
        mongo = _make_mongo_with_repayments(
            financing_orders=[
                {'uid': 'U1', 'buyer_code': 'B1', 'buyer_name': 'Buyer One',
                 'finance_request_number': 'FR1', 'invoice_number': 'INV1',
                 'financing_amount': 1000, 'status': 'funded before',
                 'bank_finance_status': 'Loan booked', 'settled_in_air8': 'Settled'},
            ],
            bank_statements=[
                {'invoice': {'seller_reference': 'INV1', 'original_amount': 2000},
                 'finance': {'advance_ratio_pct': 90, 'status': 'Loan booked'}},
            ],
            repayment_records=[
                {'finance_request_number': 'FR1', 'settlement_amount': 1800,
                 'created_at': None},
            ],
        )
        deals = get_deal_rows(mongo)
        d = deals[0]
        assert d['credit_utilization'] == 1800
        assert d['to_be_settled_on_db'] == 1800
        assert d['total_os'] == 0  # 1800(实占) - 1800(待结清) = 0，对冲

    def test_to_be_settled_on_db_none_when_db_side_already_settled(self):
        """DB 自己的结清状态字段（invoice.settlement_status）已经是 'Settled' 时，
        说明 DB 侧也已经结清，不再是"Air8 已结清但 DB 未结清"的中间态，待结清应为 None。"""
        from backend.app.services.credit_limit_service import get_deal_rows
        mongo = _make_mongo_with_repayments(
            financing_orders=[
                {'uid': 'U1', 'buyer_code': 'B1', 'buyer_name': 'Buyer One',
                 'finance_request_number': 'FR1', 'invoice_number': 'INV1',
                 'financing_amount': 1000, 'status': 'funded before',
                 'bank_finance_status': 'Loan booked', 'settled_in_air8': 'Settled'},
            ],
            bank_statements=[
                {'invoice': {'seller_reference': 'INV1', 'original_amount': 2000, 'settlement_status': 'Settled'},
                 'finance': {'advance_ratio_pct': 90, 'status': 'Loan booked'}},
            ],
            repayment_records=[
                {'finance_request_number': 'FR1', 'settlement_amount': 1800, 'created_at': None},
            ],
        )
        deals = get_deal_rows(mongo)
        d = deals[0]
        assert d['credit_utilization'] == 1800
        assert d['to_be_settled_on_db'] is None
        assert d['total_os'] == 1800  # 未对冲，因为 DB 侧结清状态已经是 Settled

    def test_to_be_settled_on_db_none_when_not_loan_booked(self):
        from backend.app.services.credit_limit_service import get_deal_rows
        mongo = _make_mongo_with_repayments(
            financing_orders=[
                {'uid': 'U1', 'buyer_code': 'B1', 'buyer_name': 'Buyer One',
                 'finance_request_number': 'FR1', 'invoice_number': 'INV1',
                 'financing_amount': 1000, 'status': 'funded before',
                 'bank_finance_status': '', 'settled_in_air8': 'Settled'},
            ],
            repayment_records=[
                {'finance_request_number': 'FR1', 'settlement_amount': 1000, 'created_at': None},
            ],
        )
        deals = get_deal_rows(mongo)
        assert deals[0]['to_be_settled_on_db'] is None
        assert deals[0]['total_os'] == 0

    def test_to_be_settled_on_db_none_when_settlement_amount_not_numeric(self):
        from backend.app.services.credit_limit_service import get_deal_rows
        mongo = _make_mongo_with_repayments(
            financing_orders=[
                {'uid': 'U1', 'buyer_code': 'B1', 'buyer_name': 'Buyer One',
                 'finance_request_number': 'FR1', 'invoice_number': 'INV1',
                 'financing_amount': 1000, 'status': 'funded before',
                 'bank_finance_status': 'Loan booked', 'settled_in_air8': 'Settled'},
            ],
            repayment_records=[
                {'finance_request_number': 'FR1', 'settlement_amount': 'Pending for settlement',
                 'created_at': None},
            ],
        )
        deals = get_deal_rows(mongo)
        assert deals[0]['to_be_settled_on_db'] is None

    def test_to_be_settled_on_db_picks_latest_created_at_when_duplicates(self):
        from datetime import datetime
        from backend.app.services.credit_limit_service import get_deal_rows
        mongo = _make_mongo_with_repayments(
            financing_orders=[
                {'uid': 'U1', 'buyer_code': 'B1', 'buyer_name': 'Buyer One',
                 'finance_request_number': 'FR1', 'invoice_number': 'INV1',
                 'financing_amount': 1000, 'status': 'funded before',
                 'bank_finance_status': 'Loan booked', 'settled_in_air8': 'Settled'},
            ],
            repayment_records=[
                {'finance_request_number': 'FR1', 'settlement_amount': 100,
                 'created_at': datetime(2026, 1, 1)},
                {'finance_request_number': 'FR1', 'settlement_amount': 999,
                 'created_at': datetime(2026, 6, 1)},
            ],
        )
        deals = get_deal_rows(mongo)
        assert deals[0]['to_be_settled_on_db'] == 999

    def test_buyer_name_prefers_onboard_config(self):
        from backend.app.services.credit_limit_service import get_deal_rows
        mongo = _make_mongo_with_repayments(
            onboard_configs=[{'uid': 'U1', 'obligor_name': 'Amazon.com Services LLC',
                               'seller_name': 'Photonverse Inc', 'buyer_code': 'B1', 'supplier_code': 'S1'}],
            financing_orders=[
                {'uid': 'U1', 'buyer_name': 'AMAZON.COM SERVICES LLC ', 'supplier_name': 'PHOTONVERSE, INC.',
                 'financing_currency': 'usd', 'finance_request_number': 'FR1', 'invoice_number': 'INV1',
                 'financing_amount': 1000, 'status': 'eligible', 'bank_finance_status': ''},
            ],
        )
        deals = get_deal_rows(mongo)
        d = deals[0]
        assert d['buyer_name'] == 'Amazon.com Services LLC'
        assert d['supplier_name'] == 'Photonverse Inc'
        assert d['currency'] == 'USD'
        assert d['detail_buyer_name'] == 'AMAZON.COM SERVICES LLC '
        assert d['detail_supplier_name'] == 'PHOTONVERSE, INC.'
        assert d['detail_currency'] == 'usd'

    def test_buyer_filter_matches_case_insensitively(self):
        from backend.app.services.credit_limit_service import get_deal_rows
        mongo = _make_mongo_with_repayments(
            financing_orders=[
                {'uid': 'U1', 'buyer_name': 'Amazon Services', 'finance_request_number': 'FR1',
                 'invoice_number': 'INV1', 'financing_amount': 1000, 'status': 'eligible',
                 'bank_finance_status': ''},
                {'uid': 'U2', 'buyer_name': 'Homegoods Inc', 'finance_request_number': 'FR2',
                 'invoice_number': 'INV2', 'financing_amount': 500, 'status': 'eligible',
                 'bank_finance_status': ''},
            ],
        )
        deals = get_deal_rows(mongo, buyer_filter='amazon')
        assert len(deals) == 1
        assert deals[0]['buyer_name'] == 'Amazon Services'

    def test_records_without_uid_are_skipped(self):
        from backend.app.services.credit_limit_service import get_deal_rows
        mongo = _make_mongo_with_repayments(
            financing_orders=[
                {'buyer_name': 'No UID Buyer', 'finance_request_number': 'FR1',
                 'invoice_number': 'INV1', 'financing_amount': 1000, 'status': 'eligible',
                 'bank_finance_status': ''},
            ],
        )
        deals = get_deal_rows(mongo)
        assert deals == []

    def test_logs_warning_when_matched_statement_has_no_advance_ratio(self, caplog):
        import logging
        from backend.app.services.credit_limit_service import get_deal_rows
        mongo = _make_mongo_with_repayments(
            financing_orders=[
                {'uid': 'U1', 'buyer_name': 'Buyer One', 'finance_request_number': 'FR1',
                 'invoice_number': 'INV1', 'financing_amount': 1000, 'status': 'eligible',
                 'bank_finance_status': ''},
            ],
            bank_statements=[
                {'invoice': {'seller_reference': 'INV1', 'original_amount': 2000}, 'finance': {}},
            ],
        )
        with caplog.at_level(logging.WARNING, logger='credit_limit_service'):
            deals = get_deal_rows(mongo)
        assert deals[0]['financing_amount'] == 0
        assert any('INV1' in r.message for r in caplog.records)


class TestGetPairDealRows:

    def test_filters_by_exact_buyer_supplier_currency(self):
        from backend.app.services.credit_limit_service import get_pair_deal_rows
        mongo = _make_mongo_with_repayments()
        mongo.refactoring_financing_order.find.return_value = [
            {'uid': 'U1', 'buyer_name': 'Buyer One', 'supplier_name': 'Seller One',
             'financing_currency': 'USD', 'finance_request_number': 'FR1', 'invoice_number': 'INV1',
             'financing_amount': 1000, 'status': 'eligible', 'bank_finance_status': ''},
        ]
        deals = get_pair_deal_rows(mongo, 'Buyer One', 'Seller One', 'USD')
        assert len(deals) == 1
        mongo.refactoring_financing_order.find.assert_called_once_with({
            'buyer_name': 'Buyer One', 'supplier_name': 'Seller One', 'financing_currency': 'USD',
        })


class TestComputeDealTotals:

    def test_sums_the_five_numeric_columns(self):
        from backend.app.services.credit_limit_service import compute_deal_totals
        deals = [
            {'financing_amount': 100, 'earmark_forecast': 100, 'credit_utilization': 0,
             'to_be_settled_on_db': None, 'total_os': 100},
            {'financing_amount': 200, 'earmark_forecast': 0, 'credit_utilization': 200,
             'to_be_settled_on_db': 50, 'total_os': 150},
        ]
        totals = compute_deal_totals(deals)
        assert totals == {
            'financing_amount': 300, 'earmark_forecast': 100, 'credit_utilization': 200,
            'to_be_settled_on_db': 50, 'total_os': 250,
        }

    def test_empty_list_returns_zeros(self):
        from backend.app.services.credit_limit_service import compute_deal_totals
        assert compute_deal_totals([]) == {
            'financing_amount': 0, 'earmark_forecast': 0, 'credit_utilization': 0,
            'to_be_settled_on_db': 0, 'total_os': 0,
        }
