"""Pure aggregation for the Dashboard buyer credit utilization card."""

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import logging

try:
    from bson import Decimal128
except ImportError:  # pragma: no cover - bson is a runtime dependency of the app
    Decimal128 = ()


logger = logging.getLogger(__name__)

SUPPORTED_CURRENCIES = frozenset({"USD", "EUR"})
_ZERO = Decimal("0")
_MONEY_QUANTUM = Decimal("0.01")
_RATE_QUANTUM = Decimal("0.0001")
_UTC_MIN = datetime.min.replace(tzinfo=timezone.utc)


def _normalize_currency(value):
    if not isinstance(value, str):
        return None
    currency = value.strip().upper()
    return currency or None


def _normalize_limit_currency(value):
    """Apply the TASK-001 legacy Credit Limit currency contract."""
    currency = _normalize_currency(value)
    return currency if currency in SUPPORTED_CURRENCIES else "USD"


def _to_decimal(value):
    if value is None or value == "":
        return _ZERO
    try:
        if Decimal128 and isinstance(value, Decimal128):
            value = value.to_decimal()
        elif not isinstance(value, Decimal):
            value = Decimal(str(value))
        return value if value.is_finite() else _ZERO
    except (InvalidOperation, TypeError, ValueError):
        return _ZERO


def _system_invoice_id_sort_key(value):
    """Keep numeric invoice IDs numerically ordered while supporting opaque IDs."""
    text = str(value or "")
    try:
        numeric = Decimal(text)
    except (InvalidOperation, TypeError, ValueError):
        return (0, text)
    if not numeric.is_finite():
        return (0, text)
    return (1, numeric, text)


def _to_utc(value):
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
        return _to_utc(parsed)
    return None


def _invoice(statement):
    value = statement.get("invoice")
    return value if isinstance(value, dict) else {}


def _finance(statement):
    value = statement.get("finance")
    return value if isinstance(value, dict) else {}


def _statement_sort_key(statement):
    invoice = _invoice(statement)
    return (
        _to_utc(invoice.get("creation_time")) or _UTC_MIN,
        _to_utc(statement.get("updated_at")) or _UTC_MIN,
        _to_utc(statement.get("created_at")) or _UTC_MIN,
        _system_invoice_id_sort_key(invoice.get("system_invoice_id")),
    )


def _effective_time(statement):
    invoice = _invoice(statement)
    return (
        _to_utc(invoice.get("creation_time"))
        or _to_utc(statement.get("updated_at"))
        or _to_utc(statement.get("created_at"))
    )


def _pick_latest_statement(statements):
    if not statements:
        return None
    return max(statements, key=_statement_sort_key)


def _financing_currency(order, statement):
    """Use the existing financing currency, without the Credit Limit fallback."""
    order_currency = _normalize_currency(order.get("financing_currency"))
    if order_currency:
        return order_currency
    invoice = _invoice(statement)
    return _normalize_currency(invoice.get("currency")) or _normalize_currency(
        _finance(statement).get("currency")
    )


def _financing_item_key(order):
    """Return the stable key that makes one financing order one contribution."""
    return (
        order.get("finance_request_number")
        or order.get("invoice_number")
        or order.get("uid")
    )


def _buyer_code(order):
    return order.get("buyer_code") or ""


def _buyer_name(order):
    return order.get("buyer_name") or ""


def build_buyer_credit_utilization(financing_orders, bank_statements, credit_limits, currency):
    """Build the normalized Dashboard payload from in-memory source documents.

    The function performs no I/O. Timestamps are normalized to UTC, monetary
    values are retained as Decimal values, and only the final money/rate
    values are quantized for the transport boundary.
    """
    selected_currency = _normalize_currency(currency)
    if selected_currency not in SUPPORTED_CURRENCIES:
        raise ValueError("currency must be USD or EUR")

    limits_by_buyer = {}
    limit_names = {}
    for limit in credit_limits:
        if _normalize_limit_currency(limit.get("credit_limit_currency")) != selected_currency:
            continue
        code = limit.get("buyer_code") or ""
        if not code:
            continue
        limits_by_buyer[code] = limits_by_buyer.get(code, _ZERO) + _to_decimal(
            limit.get("refactoring_limit")
        )
        limit_names.setdefault(code, limit.get("obligor_name") or limit.get("buyer_name") or "")

    statements_by_reference = {}
    for statement in bank_statements:
        reference = _invoice(statement).get("seller_reference")
        if reference:
            statements_by_reference.setdefault(reference, []).append(statement)

    qualifying_items = {}
    for order in financing_orders:
        item_key = _financing_item_key(order)
        invoice_number = order.get("invoice_number")
        if not item_key or not invoice_number:
            continue
        if item_key in qualifying_items:
            logger.warning("Duplicate financing item ignored: %s", item_key)
            continue

        latest = _pick_latest_statement(statements_by_reference.get(invoice_number, []))
        if latest is None or _finance(latest).get("status") != "Loan booked":
            continue
        if _financing_currency(order, latest) != selected_currency:
            continue

        qualifying_items[item_key] = (order, latest)

    buyers = {}
    for order, statement in qualifying_items.values():
        code = _buyer_code(order)
        key = code or _buyer_name(order)
        if not key:
            continue
        row = buyers.setdefault(
            key,
            {
                "buyer_code": code,
                "buyer_name": limit_names.get(code) or _buyer_name(order) or "",
                "used_credit": _ZERO,
                "latest_data_time": None,
            },
        )
        row["used_credit"] += _to_decimal(_finance(statement).get("outstanding_amount"))
        effective_time = _effective_time(statement)
        if effective_time and (
            row["latest_data_time"] is None or effective_time > row["latest_data_time"]
        ):
            row["latest_data_time"] = effective_time

    result_rows = []
    for key, buyer in buyers.items():
        total_limit = limits_by_buyer.get(buyer["buyer_code"], _ZERO)
        used_credit = buyer["used_credit"]
        rate = (
            (used_credit / total_limit).quantize(_RATE_QUANTUM, rounding=ROUND_HALF_UP)
            if total_limit > _ZERO
            else None
        )
        result_rows.append(
            {
                "buyer_code": buyer["buyer_code"],
                "buyer_name": buyer["buyer_name"],
                "total_approved_credit_limit": total_limit.quantize(
                    _MONEY_QUANTUM, rounding=ROUND_HALF_UP
                ),
                "used_credit": used_credit.quantize(_MONEY_QUANTUM, rounding=ROUND_HALF_UP),
                "credit_utilization_rate": rate,
                "remaining_credit": (total_limit - used_credit).quantize(
                    _MONEY_QUANTUM, rounding=ROUND_HALF_UP
                ),
                "latest_data_time": buyer["latest_data_time"],
            }
        )

    result_rows.sort(
        key=lambda row: (
            row["credit_utilization_rate"] is None,
            -(row["credit_utilization_rate"] or _ZERO),
            row["buyer_code"],
            row["buyer_name"],
        )
    )
    latest_available_data_time = max(
        (row["latest_data_time"] for row in result_rows if row["latest_data_time"]),
        default=None,
    )
    return {
        "currency": selected_currency,
        "latest_available_data_time": latest_available_data_time,
        "buyers": result_rows,
    }


def aggregate_buyer_credit_utilization(mongo, currency):
    """Read the three approved Mongo boundaries and build the Dashboard payload."""
    return build_buyer_credit_utilization(
        list(mongo.refactoring_financing_order.find()),
        list(mongo.refactoring_bank_statement.find()),
        list(mongo.refactoring_onboard_config.find()),
        currency,
    )
