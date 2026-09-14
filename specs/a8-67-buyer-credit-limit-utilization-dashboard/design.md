# Buyer Credit Limit Utilization on Dashboard — Technical Design

## Design status and governed inputs

- Feature point: `BUYER-CREDIT-dashboard1`
- Approved product baseline: Requirement Confirmation `RC-003`, child A8-69.
- Gate 2 prototype: Prototype Confirmation A8-71, confirmed `Prototype Analyze Done`.
- Confirmed implementation decisions: DEC-001 (missing Credit Limit currency defaults to USD; supported currencies remain USD and EUR) and DEC-002 (the existing authenticated access boundary is sufficient for the current Admin-only scope; no additional role differentiation or authorization logic is required).
- Delivery context: Refactoring; base `c912eeaa3ea5b4b3bc51424cc5fcc5b5d8f442da`; branch `feature/A8-67-buyer-credit-limit-utilization-on-dashboard`.
- Scope of this artifact: technical placement, interfaces, implementation boundaries, and behavior-sized tasks. Product IDs and meanings are reproduced only for traceability.

The current Refactoring checkout has no feature-specific implementation. Existing Credit Query behavior is evidence of the current state, not the requested Dashboard behavior.

## Architecture and reuse

The feature belongs in the Refactoring Flask application as a session-protected Dashboard BFF and deterministic Mongo-backed aggregation:

```text
Dashboard page
  -> session-protected JSON route in backend/app/routes/main.py
  -> pure buyer-credit-utilization service
  -> refactoring_financing_order + refactoring_bank_statement
     + refactoring_onboard_config
  -> normalized buyer rows and chart-level effective time
```

Reuse:

- `main.get_mongo()` for the existing application Mongo access pattern.
- `login_required` and the existing Dashboard route/template lifecycle.
- `Chart.js` already loaded by `dashboard.html`; use a mixed bar/line chart or an equivalent existing Chart.js extension, without adding a new chart dependency.
- `_to_float`-style defensive numeric conversion, but keep monetary calculations in `Decimal`/`Decimal128`-compatible values until final display serialization.
- The existing `invoice_number` to `invoice.seller_reference` join used by `_fetch_bank_statements_by_invoice()` and `AggregateService._process_statement_group()`.
- The existing `financing_currency` / bank-statement currency mapping for financing records; the DEC-001 fallback applies only to the approved Credit Limit currency, not to financing-record currency.

Do not reuse `aggregate_by_buyer()` as the Dashboard calculation: it is currently USD-only and derives Actual from the Financing Amount/advance-ratio path. Do not reuse the materialized overview as the source of truth because its history and totals are shaped for other reports.

## Boundaries and affected areas

| Boundary | Planned responsibility | Existing evidence | Change boundary |
| --- | --- | --- | --- |
| Frontend | Dashboard card, USD/EUR selector, chart, accessible data table, empty/loading/error/retry states | `backend/app/templates/dashboard.html:1-334` | `dashboard.html`; only feature-local i18n keys in `backend/app/i18n/*.json` |
| Server/BFF | Validate currency, require the existing session, call deterministic service, serialize JSON, return explicit error response | `backend/app/routes/main.py:43-74,76-126`; `login_required` on current routes | Add one Dashboard JSON route in `main.py` |
| Data | Read financing orders, raw bank statements, and buyer-supplier limit records; select one latest bank snapshot per financing item | `credit_limit_service.py:20-139`; `aggregate_service.py:40-213` | New pure service plus additive currency-aware mapping |
| Credit Query | Share latest-record/status/grouping/outstanding semantics for buyer-level Actual only; preserve reserved, settled, and other metrics | `credit.py:37-60`; `credit_limit_service.py:246-340` | Focused changes to `credit_limit_service.py` and `credit.py` only as required |
| Integration | The onboarding source must preserve the relationship currency needed to filter approved limits | `onboarding_sync_service.py:91-129` currently drops currency | No new remote integration is authorized; confirm the existing payload field before implementation |
| Configuration | No new business threshold; 100% is a feature rule, not `CREDIT_WARNING_THRESHOLD` | `config.py:29` and warning tests | Do not alter the existing 90% warning job/config |
| Permission | Keep the route behind the existing authenticated application boundary; do not broaden access or add role branching | `main.py:43-45`; `User` has id/name/password only | DEC-002 resolves the current scope to the existing `login_required` boundary; no new Admin predicate or authorization field |

## Deterministic data flow

1. The route accepts only the approved selector values `USD` and `EUR`; invalid values are a client error and do not query mixed currencies.
2. Load relationship limits from `refactoring_onboard_config`, retaining buyer code/name, relationship identity, limit value, and a normalized Credit Limit currency. Use the verified source value when present; when the Credit Limit currency cannot be found, use `USD` per DEC-001. The supported selector currencies remain `USD` and `EUR`; do not convert amounts.
3. Load financing orders and join their `invoice_number` to bank statements by `invoice.seller_reference`. The normalized financing-item key must be stable and unique for the order; duplicate or unjoinable records must not be silently counted twice.
4. For each financing item, select one bank statement by descending tuple:
   `invoice.creation_time`, then root `updated_at`, then root `created_at`, all normalized and compared in UTC; on a full timestamp tie use the greatest `invoice.system_invoice_id`.
5. Apply the selected currency before aggregation. A relationship limit uses its normalized Credit Limit currency from step 2. A selected latest financing record qualifies only when its latest finance status is `Loan booked` and its existing financing/bank currency is the selected currency. Do not infer a financing-record currency from DEC-001.
6. Group qualifying financing items and applicable relationship limits by `buyer_code`. Each selected financing item contributes `finance.outstanding_amount` once.
7. Compute utilization from Used Credit / Total Approved Credit Limit; use an unavailable utilization value when the limit is unavailable or zero. Compute Remaining Credit as limit minus Used Credit, with unavailable required inputs contributing zero.
8. Sort by utilization descending, placing unavailable utilization after numeric values. Preserve the product-required behavior for equal-rate ordering without introducing a new ordering rule.
9. Serialize each buyer timestamp and the chart-level maximum effective timestamp as UTC instants. The UI formats them for Asia/Shanghai (UTC+8).

## API contract

Proposed route: `GET /api/get_buyer_credit_limit_utilization?currency=USD|EUR`.

Success response:

```json
{
  "code": 0,
  "msg": "success",
  "data": {
    "currency": "USD",
    "latest_available_data_time": "2026-09-12T10:30:00Z",
    "buyers": [
      {
        "buyer_code": "B001",
        "buyer_name": "Northstar Retail",
        "total_approved_credit_limit": 150000.0,
        "used_credit": 80000.0,
        "credit_utilization_rate": 0.5333,
        "remaining_credit": 70000.0,
        "latest_data_time": "2026-09-10T02:00:00Z"
      }
    ]
  }
}
```

`credit_utilization_rate` is a ratio in the transport contract; the UI renders it as a percentage to two decimal places. A zero/ unavailable limit is represented by a numeric limit contribution and a `null` utilization rate so the UI can distinguish “unavailable” from zero utilization. Empty qualifying data is a successful response with `buyers: []` and a null chart-level timestamp.

Failure response:

```json
{"code": 1, "msg": "Unable to load credit data. Please try again.", "data": {}}
```

The route must not expose raw Mongo documents, credentials, or unrelated Credit Query fields.

## UI behavior and presentation boundary

- Render a feature-local card in the existing Dashboard layout.
- Fetch the selected currency on initial load and after selector change; do not retain a successful payload as current when a request fails.
- On failure, keep the card/module shell visible, clear buyer rows/chart data, show the error and Retry, and re-fetch on Retry.
- On success with no buyers, show the no-data message and no buyer rows.
- Use the existing Chart.js loading path. The 100% reference line must use the same utilization scale as the bars; above-100% bars/rows receive the approved over-limit treatment. Exact visual styling remains bounded by `PROTOTYPE-VALIDATION-001`.
- Keep the table as the accessible and exact-value representation of all seven displayed fields. The chart is a visual summary, not a second calculation path.
- The selector presentation and refresh interaction are bounded by `PROTOTYPE-VALIDATION-002`; no new currency or conversion behavior is introduced.

## Credit Query reconciliation

Create one shared latest-record/qualification path used by the Dashboard and buyer-level Credit Query Actual. The shared path must use the approved outstanding field and selected latest status/grouping semantics. Preserve the current reserved, settled, financing-amount, and other non-Actual calculations unless they are mechanically required to expose the shared buyer-level Actual. Existing warning behavior remains governed by `CREDIT_WARNING_THRESHOLD` and is not changed to the Dashboard’s 100% rule.

The reconciliation must be covered by a test that proves the Dashboard Used Credit and Credit Query buyer-level Actual agree for the same fixture while reserved, settled, and other metrics remain unchanged.

## Resolved currency and permission decisions

1. DEC-001 resolves the missing Credit Limit currency behavior. The mapper/normalized read model should preserve a verified source currency when present and normalize an absent/unlocatable Credit Limit currency to `USD`. `USD` and `EUR` remain the only supported selector currencies. This fallback is limited to Credit Limit data; it does not convert amounts or supply a missing financing-record currency.
2. DEC-002 resolves the permission boundary for the current scope. The Dashboard page and JSON route use the existing `login_required` behavior. The current scope has one Admin user and no other role differentiation; no new role field, Admin predicate, or authorization workflow is added.

## Persistence, migration, and compatibility

- MongoDB is schemaless in this repository; no SQL/Drizzle migration applies.
- Prefer an additive normalized Credit Limit currency field in the onboarding projection when the existing source value is available. Readers and the mapper apply the DEC-001 USD fallback for legacy records without that field; no destructive rewrite or mandatory backfill is required for this feature.
- Do not mutate historical bank statements or overview records for this feature.
- Legacy relationship-limit records without a currency use the DEC-001 USD normalization and are covered by focused tests. Financing records continue to use their existing currency source and are not assigned the Credit Limit fallback.
- The existing `/credit/credit-query`, export, warning, settlement, and disbursement flows remain compatible except for the explicitly approved buyer-level Actual reconciliation.
- No external API write, remote Hermes change, or portal-repository change is part of this delivery.

## Observability, security, and rollback

- Log route start/end, selected currency, buyer/item counts, selected/latest record counts, and elapsed time at info/debug level; never log monetary payloads, buyer-sensitive rows, tokens, or full documents.
- Log malformed timestamps, missing join keys, duplicate financing-item keys, and missing currency as structured warnings with safe identifiers only; aggregation failure returns the controlled error response.
- Keep the session authentication decorator on both the page and JSON route. Under DEC-002, the existing authenticated access boundary is the complete authorization boundary for this scope; do not add a role field, Admin predicate, or client-side authorization check. Validate selector input server-side; do not trust client-side filtering for currency.
- Escape buyer names/codes in the template and avoid constructing HTML from raw API strings.
- Roll back by reverting the feature commit(s). Since the design adds no destructive migration, rollback removes the card/route and leaves source collections intact. If the onboarding projection is extended, the additive field may remain unused after application rollback.

## Testability and verification strategy

- Pure service tests use deterministic in-memory documents and `Decimal128`/numeric/string variants; no real MongoDB or external endpoint. Include explicit USD fallback coverage for missing Credit Limit currency and explicit EUR preservation.
- Cover latest selection, full timestamp ties, UTC comparison, selected currency filtering, one contribution per financing item, buyer aggregation, zero/unavailable limits, negative remaining credit, sorting, chart-level max time, and empty results.
- Route tests mock `get_mongo()` and assert request validation, success/error envelopes, the existing authenticated-session boundary, and no stale-data contract at the UI boundary. Do not add role-differentiation tests or a new Admin authorization contract under DEC-002.
- Credit Query tests verify AC-010 and preserve reserved/settled/other metrics.
- Template/browser verification covers selector refresh, 100% line and strict-above-100% highlight, two-decimal display, table fields, empty state, error/retry clearing, and Asia/Shanghai rendering. Use only deterministic local fixtures/mock server; never real MongoDB or UAT writes.

## Alternatives considered

| Alternative | Decision | Reason |
| --- | --- | --- |
| Reuse `aggregate_by_buyer()` | Reject | It is USD-only and uses legacy Financing Amount semantics. |
| Read `refactoring_financing_overview` | Reject as source of truth | It is a materialized report with historical snapshots and unrelated totals. |
| Add a new external service or remote Hermes flow | Reject | The approved placement is deterministic Refactoring Dashboard behavior; no remote change is authorized. |
| Client-side aggregation from raw endpoints | Reject | It would expose sensitive raw data and permit currency/permission bypasses. |
| New charting dependency | Reject unless existing Chart.js cannot satisfy the prototype | Existing `dashboard.html` already loads Chart.js; minimize deployment and rollback risk. |
| Add a new Admin role field or predicate | Reject for this delivery | DEC-002 explicitly keeps the existing authenticated access boundary and does not introduce role differentiation. |

## Requirement-to-design traceability

| Product IDs | Design coverage |
| --- | --- |
| `BUYER-CREDIT-dashboard1`; `R-001`–`R-007` | Deterministic source flow, latest selector, UTC timestamps, buyer grouping, outstanding field, and chart-level time. |
| `R-008`–`R-013` | Sorting, 100% reference line, strict over-limit styling, unavailable limit, currency scope, remaining-credit and final display rounding. |
| `R-014` | Controlled route/UI error, Retry, module visibility, and stale-success clearing. |
| `AC-001`–`AC-009` | API contract, UI/table/chart states, calculations, currency, rounding, empty/error behavior. |
| `AC-010` | Shared selector/qualification path and Credit Query preservation test. |
| `EX-N-001`–`EX-N-003` | Normal aggregation, chart-level time, and selected-currency fixtures. |
| `EX-E-001`–`EX-E-003` | Unavailable limit, over-limit, and retrieval/aggregation failure fixtures. |
| `EX-EMPTY-001` | Successful empty response and no-data UI fixture. |
| `PROTOTYPE-VALIDATION-001/002` | Presentation-only verification in the UI task; no business meaning is changed. |

## Open technical decisions

- `DEC-001`: resolved by the confirmed decision: preserve a verified Credit Limit currency when present; default an unavailable Credit Limit currency to USD; support USD and EUR without conversion.
- `DEC-002`: resolved by the confirmed decision: use the existing authenticated access boundary for the current Admin-only scope; no additional role differentiation or Admin authorization logic.
- `DEC-003`: whether the existing Chart.js version supports the required mixed chart/reference-line configuration without a plugin; decide during TASK-005 implementation using the checked-in/current CDN contract, without changing the acceptance meaning. This is non-blocking because the approved design already permits either the existing Chart.js configuration or an equivalent existing extension.
