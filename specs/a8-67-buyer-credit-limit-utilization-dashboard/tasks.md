# Buyer Credit Limit Utilization on Dashboard — Task Breakdown

Product baseline: `RC-003` from A8-69; Gate 2 prototype: A8-71. Product IDs are owned by Product and must not be renumbered or reinterpreted.

## Capability group G1 — Currency-aware source and latest-record normalization

### TASK-001 — Preserve and validate the selected-currency source for relationship limits

- Group: `G1 — Currency-aware source and latest-record normalization`
- Risk: `High`
- Objective: Make approved buyer-supplier relationship limits and qualifying financing records carry deterministic currency into the feature’s normalized read model without conversion: preserve the verified Credit Limit currency when present, default a missing/unlocatable Credit Limit currency to USD per DEC-001, and retain the existing financing-record currency source. Supported currencies remain USD and EUR.
- Expected scope/boundary: `backend/app/services/onboarding_sync_service.py:_map_record/_run_sync`; the normalized feature service introduced for this feature; additive normalized Credit Limit currency field only if required by the existing source mapping; `backend/tests/test_onboarding_sync.py` and focused currency-contract tests. Do not add a role field or authorization logic.
- Dependencies: DEC-001 is resolved and supplies the Credit Limit fallback/allowed currencies. DEC-002 is resolved independently for the route boundary and is not a TASK-001 blocker.
- Product traceability: `R-003`, `R-011`; `AC-003`, `AC-006`; `EX-N-003`, `EX-E-001`, `EX-EMPTY-001`.
- Verification intent: Prove explicit USD/EUR Credit Limit currencies are preserved, a missing/unlocatable Credit Limit currency normalizes to USD, selected-currency filtering is applied to both limit and financing inputs, and existing unrelated callers retain their behavior. Financing records must not inherit the Credit Limit fallback.
- Done condition: The normalized inputs expose deterministic currency for the feature, DEC-001 legacy handling is covered by tests, no amount conversion or cross-currency sum is introduced, and no design-gap route remains for this task.

## Capability group G2 — Deterministic buyer utilization aggregation

### TASK-002 — Select latest financing snapshots and compute buyer rows

- Group: `G2 — Deterministic buyer utilization aggregation`
- Risk: `High`
- Objective: Implement a pure, testable aggregation service that selects one latest bank snapshot per financing item, filters selected latest `Loan booked` records, sums `finance.outstanding_amount` once, aggregates applicable selected-currency limits by Buyer Code, and returns deterministic buyer rows plus chart-level latest effective time.
- Expected scope/boundary: New `backend/app/services/buyer_credit_utilization_service.py` (or the repository-approved equivalent); read-only boundaries for `refactoring_financing_order`, `refactoring_bank_statement`, and `refactoring_onboard_config`; focused `backend/tests/test_buyer_credit_utilization_service.py`.
- Dependencies: `TASK-001`; existing join evidence in `credit_limit_service.py:_fetch_bank_statements_by_invoice` and `aggregate_service.py:_process_statement_group`.
- Product traceability: `R-001`–`R-010`, `R-012`–`R-013`; `AC-001`–`AC-008`; `EX-N-001`, `EX-N-002`, `EX-E-001`, `EX-E-002`, `EX-EMPTY-001`.
- Verification intent: Cover UTC ordering by `invoice.creation_time`, `updated_at`, `created_at`, greatest `invoice.system_invoice_id` full-tie selection, one-item-one-contribution, buyer grouping, zero/unavailable limit, negative remaining credit, descending utilization, final chart timestamp, and two-decimal-safe values.
- Done condition: Pure tests independently recalculate the RC-003 worked examples and boundary cases; no historical snapshot double-counting or cross-currency aggregation remains.

## Capability group G3 — Dashboard API boundary

### TASK-003 — Expose the normalized Dashboard payload

- Group: `G3 — Dashboard API boundary`
- Risk: `High`
- Objective: Add the session-protected Dashboard JSON route with server-side USD/EUR validation, the documented success/empty/error envelope, safe serialization, and controlled aggregation failure behavior.
- Expected scope/boundary: `backend/app/routes/main.py` route adjacent to `dashboard()` and existing JSON routes; `backend/tests/test_main_dashboard_credit_utilization.py`; no change to token-protected external API routes in `backend/app/routes/api.py`.
- Dependencies: `TASK-001`, `TASK-002`; DEC-002 is resolved and requires use of the existing authenticated session boundary only.
- Product traceability: `R-001`–`R-007`, `R-011`, `R-014`; `AC-001`–`AC-006`, `AC-009`; `EX-N-001`–`EX-N-003`, `EX-E-003`, `EX-EMPTY-001`.
- Verification intent: Assert unauthenticated rejection, authenticated access through the existing session boundary, invalid-currency rejection, exact response shape, null chart time for empty data, no raw-document leakage, and error response when retrieval/aggregation raises. Do not add role-differentiation behavior under DEC-002.
- Done condition: The route returns only the normalized contract, remains protected by `login_required` with no new Admin authorization logic, and passes focused route tests without connecting to real MongoDB.

## Capability group G4 — Credit Query reconciliation

### TASK-004 — Reconcile buyer-level Actual with Dashboard Used Credit

- Group: `G4 — Credit Query reconciliation`
- Risk: `High`
- Objective: Reuse the approved latest-record, `Loan booked`, buyer grouping, and outstanding-amount semantics for buyer-level Credit Query Actual while preserving reserved, settled, and other Credit Query metrics.
- Expected scope/boundary: `backend/app/services/credit_limit_service.py:get_deal_rows/get_buyer_supplier_pairs/aggregate_by_buyer` as needed; `backend/app/routes/credit.py:credit_query`; focused updates to `backend/tests/test_credit_limit_service.py` and `backend/tests/test_credit_query_route.py`.
- Dependencies: `TASK-001`, `TASK-002`; `DEC-001`.
- Product traceability: `R-004`–`R-007`; `AC-003`, `AC-010`; `EX-N-001`, `EX-E-001`.
- Verification intent: Use the same fixture through Dashboard and Credit Query, assert matching buyer-level Actual/Used Credit, and separately assert unchanged reserved, settled, financing-amount, and other metrics. Keep the existing 90% warning-job threshold independent of the Dashboard 100% presentation rule.
- Done condition: Reconciliation tests pass, existing unrelated Credit Query/export/detail tests remain green, and no Dashboard-only currency or error behavior leaks into unrelated Credit Query paths.

## Capability group G5 — Dashboard interaction and presentation

### TASK-005 — Render selector, chart, table, empty state, and retryable error state

- Group: `G5 — Dashboard interaction and presentation`
- Risk: `High`
- Objective: Add the Buyer Credit Limit Utilization card to the existing Dashboard, fetch selected-currency data, render all seven fields and the chart/reference line, and implement empty/error/retry behavior without stale successful data.
- Expected scope/boundary: `backend/app/templates/dashboard.html`; feature-local keys in `backend/app/i18n/en.json`, `en-US.json`, `zh.json`, and `zh-CN.json` if required by existing translation conventions; focused template/route assertions and manual/browser verification fixture.
- Dependencies: `TASK-003`; `PROTOTYPE-VALIDATION-001`; `PROTOTYPE-VALIDATION-002`; existing Chart.js load contract in `dashboard.html`. DEC-003 is a bounded implementation-time compatibility check and does not block task planning.
- Product traceability: `R-008`–`R-014`; `AC-001`, `AC-005`–`AC-009`; `EX-N-001`–`EX-N-003`, `EX-E-002`, `EX-E-003`, `EX-EMPTY-001`, `PROTOTYPE-VALIDATION-001/002`.
- Verification intent: Verify initial load, USD↔EUR refresh, seven displayed fields, two-decimal money/percentage rendering, chart-level Asia/Shanghai time, strict above-100% highlighting, exact-100% reference-line behavior, no-data state, failure clearing, Retry, accessibility table, and theme/responsive readability using deterministic local fixtures.
- Done condition: The card remains visible in all required states, a failed request cannot display stale successful rows, successful Retry replaces the cleared state with the latest payload, and presentation verification introduces no new product meaning.

## Technical review focus

Confirm DEC-001 Credit Limit currency fallback and financing-currency separation, DEC-002 use of the existing authenticated boundary without new role logic, DEC-003 Chart.js/reference-line compatibility, cross-surface data semantics, error/no-stale behavior, dependencies, and High-risk correctness. No product IDs or business meaning are added.

## Sequential execution order and non-overlap

`TASK-001 → TASK-002 → TASK-003 → TASK-004 → TASK-005`.

Each task owns the files/symbols listed above. Related focused tests stay with the behavior they verify. No task creates a separate issue, migration, export, notification, approval record, external integration write, or unrelated cleanup.

## Traceability coverage

- `R-001`–`R-003`: TASK-001, TASK-002, TASK-003.
- `R-004`–`R-007`: TASK-002, TASK-004.
- `R-008`–`R-010`: TASK-002, TASK-005.
- `R-011`: TASK-001, TASK-002, TASK-003, TASK-005.
- `R-012`–`R-014`: TASK-002, TASK-003, TASK-005.
- `AC-001`–`AC-009`: TASK-002, TASK-003, TASK-005.
- `AC-010`: TASK-004.
- `EX-N-001`–`EX-N-003`: TASK-001 through TASK-005 as scoped above.
- `EX-E-001`–`EX-E-003`: TASK-001, TASK-002, TASK-003, TASK-005.
- `EX-EMPTY-001`: TASK-001, TASK-002, TASK-003, TASK-005.
- `PROTOTYPE-VALIDATION-001/002`: TASK-005 only; these remain bounded presentation/interaction checks.
