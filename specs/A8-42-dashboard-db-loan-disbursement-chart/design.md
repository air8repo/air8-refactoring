# A8-42 Technical Design — DB Disbursement Monthly Chart

**Feature**

`A8-refactoring1` — replace the Refactoring dashboard DB Disbursement table with a monthly amount and interest line chart.

**Planning revision**

`A8-42-DESIGN-v0.2` — Gate 3 proposal; not an approval.

## 1. Approved inputs and planning boundary

This design consumes the exact Gate 2-approved product material. Product-owned IDs are immutable and remain the only source of business meaning.

| Input | Revision / readback | Local evidence |
| --- | --- | --- |
| Requirement Confirmation / Development View | A8-42-RC-v0.1, Linear A8-44, `updatedAt` 2026-09-11T15:19:33.884Z | `specs/A8-42-dashboard-db-loan-disbursement-chart/spec.md`, SHA-256 `9E8E66F3045F7013685573ACCB442994059D989EE52BF56C2049046F33C06CF4` |
| Approved user flow | A8-42-RC-v0.1 | `specs/A8-42-dashboard-db-loan-disbursement-chart/user-flow.md`, SHA-256 `C40A82ADE7CBB14EED4303B4766A56E5AA2FA43778052EE9C7EF779E3E843F35` |
| Gate 2 prototype | A8-42-RC-v0.1, Linear A8-45, `updatedAt` 2026-09-11T16:09:04.743Z, status `Prototype Analyze Done` | `prototype/A8-42-dashboard-db-loan-disbursement-chart/overdue-insights.html`, SHA-256 `3D951A8C1BFED50B8A1125457356CA1C190DCC30B69D26006FA4416AA83ADE9D` |
| Product IDs | `CI-001..CI-002`, `R-001..R-007`, `AC-001..AC-006`, `EX-N-001`, `EX-E-001`, `EX-EMPTY-001`, `PROTOTYPE-VALIDATION-001..005` | Product specification and matching user flow above |

Only these files are written by this phase: this `design.md` and the matching `tasks.md`. Application code, executable tests, `testcases.md`, approvals, workflow state, and Linear are outside the write scope.

## 2. Evidence and current placement

The authorized implementation checkout is `C:/aiproject/.worktrees/air8-refactoring/A8-42-dashboard-db-loan-disbursement-chart`, branch `feature/A8-42-dashboard-db-loan-disbursement-chart`, based on `origin/main` `c912eeaa3ea5b4b3bc51424cc5fcc5b5d8f442da`. The planning snapshot was worktree HEAD `17a909797e484ef8f938f8b2c5b96de36beed5ce`.

| Boundary | Current evidence | Architectural implication |
| --- | --- | --- |
| Page entry | `backend/app/routes/main.py:43-74`, `dashboard()` is `@login_required`, obtains Mongo, calculates dashboard stats, calls `get_db_disbursement()`, and server-renders `dashboard.html`. | Keep the page route, session boundary, server-rendered handoff, database-not-connected response, and unrelated cards unchanged. |
| DB Disbursement projection | `backend/app/routes/main.py:343-418`, `get_db_disbursement()` reads `refactoring_financing_overview` with `{'refactoring_status': 'Loan booked'}`, requires a truthy `loan_submission_batch`, reads `bank_statements[0]`, converts numeric values, and returns batch sums. | Reuse the same collection/filter/inclusion boundary and numeric conversion seam; replace only the projection with month buckets and averages. |
| API | `backend/app/routes/main.py:421-444`, `api_get_db_disbursement()` is `@login_required` and returns `{code, msg, data}` with a broad existing error boundary. | Keep path, authentication, envelope, success message, and error shape. The approved replacement changes `data` to the chart projection; no alternate list payload is required. |
| Persistence convention | `backend/app/services/aggregate_service.py:89-132,146-153,506-517` flattens the latest statement into `bank_statements[0]`; `backend/tests/test_aggregate_financing_overview.py:146-172` verifies newest-first and latest-only totals. | Treat `bank_statements[0]` as the existing snapshot boundary. Do not aggregate historical snapshots or change the aggregate service. |
| Source fields | `aggregate_service.py:94-103` maps `finance.start_date` to `start_date`, `finance.finance_amount` to `finance_amount`, and USD interest to `interest_amount_usd`; `export_service.py` maps `bank_statements.0.start_date` to Finance Details Start Date. | Use the existing flattened fields: `start_date`, `finance_amount`, and `interest_amount_usd`. Do not add purchase price or redefine units/currency. |
| UI | `backend/app/templates/dashboard.html:124-163` renders the old batch table; `:229-333` loads Chart.js, defines `chartTheme`, creates the data-distribution pie chart, and handles `theme-change`. | Replace only the DB Disbursement card body with a Chart.js line chart and extend the existing theme handler without disturbing the pie chart or hidden Settlement Schedule block. |
| Access/test harness | `backend/tests/conftest.py` provides an app, authenticated client, and mocked Mongo; `backend/tests/test_smoke.py` covers protected dashboard access and authenticated dashboard loading; `test_main_dashboard_reports.py` verifies the `Loan booked` filter. | Use mocked Mongo and existing Flask test fixtures. No development, UAT, or production database access is part of verification. |
| Documentation/configuration | `docs/system/modules/dashboard.md` documents the current batch sums and routes; `docs/system/api.md` lists the authenticated endpoint and response envelope. `pytest.ini` selects `backend/tests`; `backend/requirements.txt` provides Flask, PyMongo, pytest, `pytz`, and related runtime/test dependencies. | Update only the affected dashboard/API descriptions with the approved target contract. No migration, dependency, environment, or permission configuration change is planned. |

The current table/batch implementation conflicts with the approved target only as an expected current-to-target delta. The live KB has no registered Refactoring DB Disbursement feature, so no KB rule or Portal/Hermes placement is imported into this design.

## 3. Target architecture and reuse

Keep the existing synchronous path:

```text
authenticated GET /dashboard
  -> main.dashboard()
  -> get_db_disbursement()
  -> MongoDB refactoring_financing_overview.find({refactoring_status: "Loan booked"})
  -> deterministic month projection in the existing route module
  -> Jinja dashboard.html
  -> Chart.js line chart
```

The API remains a second consumer of the same helper:

```text
authenticated GET /api/get_db_disbursement
  -> api_get_db_disbursement()
  -> get_db_disbursement()
  -> {code: 0, msg: "success", data: chart_payload}
```

Reuse candidates:

- `get_mongo()` and the existing `refactoring_financing_overview` read seam in `main.py`.
- The current `safe_to_float()` behavior for Decimal128, numeric, string, null, and unparseable values. This preserves existing application defaults; it is not a new currency, precision, or rounding rule.
- `bank_statements[0]` as the latest flattened snapshot, established by the aggregate service and its tests.
- The existing dashboard card, `.chart-container`, Chart.js CDN include, `chartTheme`, and `theme-change` event.
- Existing `common.table.no_data` localization for the empty projection. Additive translated series labels are allowed only if existing keys cannot express the chart labels; keep all enabled locale files aligned and do not alter unrelated copy.
- Existing Flask test fixtures and mocked Mongo calls.

No new service layer, blueprint, collection, database write, frontend framework, client-side fetch, external integration, permission model, chart package, or runtime setting is justified by the approved scope.

## 4. Server projection and data contract

### Source and inclusion boundary

For each record returned by the existing `refactoring_status: 'Loan booked'` query:

1. Preserve the current truthy `loan_submission_batch` and nonempty `bank_statements` inclusion checks.
2. Read the existing latest flattened statement at `bank_statements[0]` once. Historical statements must not become additional chart samples.
3. Read the existing `start_date` (the stored Finance Details Start Date), `finance_amount`, and `interest_amount_usd` fields.
4. Apply the current numeric conversion default before aggregation. `purchase_price_usd` is intentionally not included because the approved target has only amount and interest series.

### Month assignment and aggregation

The implementation must produce the approved Asia/Shanghai calendar-month behavior without creating a new business rule:

- A naive stored `datetime` is treated as the existing local date value and associated with `Asia/Shanghai` before extracting `YYYY-MM`.
- An aware `datetime` is converted to `Asia/Shanghai` before extracting `YYYY-MM`.
- The projection must not parse arbitrary strings, substitute a fallback date, synthesize missing months, or add a new missing-date message. If the existing persisted date cases cannot be handled within these bounded defaults, stop and route `REQUIREMENT_GAP` rather than choosing a product interpretation.
- Each eligible source overview contributes one sample to its assigned month. Accumulate amount and interest independently, using the same sample count, then divide each sum by that month count.
- Sort emitted month keys ascending. Because the key is `YYYY-MM`, lexical order is chronological.
- Emit only populated month keys. Do not create zero-valued points for calendar gaps.

The helper and API `data` member use this internal chart contract:

```json
{
  "months": ["2026-01", "2026-03"],
  "series": {
    "disbursement_amount": [200.0, 310.0],
    "interest": [20.0, 35.0]
  }
}
```

Arrays are parallel by index. With no usable records or no Mongo object, return the same shape with empty arrays:

```json
{"months": [], "series": {"disbursement_amount": [], "interest": []}}
```

The API continues to return `{code: 0, msg: "success", data: ...}` on success and the existing `{code: 1, msg: str(e), data: {}}` on its current exception path. The page route continues to return its existing database-not-connected response before rendering. No new failure or recovery semantics are introduced.

## 5. Frontend boundary

Within the existing DB Disbursement card:

- Remove the old table/list and its batch, start-date, purchase-price, and total columns. Do not retain it as an alternate view (`R-001`, `AC-001`).
- Render a `dbDisbursementChart` canvas only when the server payload contains populated months. Use `months` as the x-axis labels exactly as supplied; JavaScript must not fill gaps.
- Create two line datasets from the parallel arrays: average disbursement amount and average interest. Keep them visually distinct and do not add a purchase-price series (`R-003`, `R-004`). The chart uses the existing default axis semantics; it does not invent currency/unit labels, a second-axis business meaning, or new precision/rounding rules.
- Serialize the server payload with Jinja `tojson` or an equivalent safe JSON handoff. Do not concatenate database values into executable JavaScript or use `innerHTML` for database-derived values.
- For an empty payload, show the existing `common.table.no_data` default in the card body and do not initialize a misleading empty chart. Keep the existing page-level loading/error behavior.
- Extend the existing `theme-change` handler to update the DB Disbursement chart's legend, scales/grid, and tooltip styling when the chart exists; preserve the data-distribution pie chart, hidden Settlement Schedule block, navigation, version footer, and all unrelated dashboard sections.
- Use the existing responsive chart-container behavior. Any new series/axis/empty-state labels must be translated consistently for the repository's enabled locale files and must not change product meaning.

## 6. Affected boundaries and compatibility

| Boundary | Change | Not changed |
| --- | --- | --- |
| Frontend | `dashboard.html` DB Disbursement card, safe payload handoff, Chart.js datasets, empty branch, theme update | Other cards, pie chart, navigation, hidden Settlement Schedule, page route |
| Server | `get_db_disbursement()` projection and its documented API data contract | Query filter, source collection, helper/API path, auth decorators, envelope, broad error boundary |
| Data | Read existing flattened snapshots and calculate an in-memory projection | Mongo schema, persisted documents, indexes, writes, migrations |
| Integration | None discovered inside the checkout | No new external service or client-side request |
| Configuration | None; reuse existing Chart.js CDN and Python dependencies | Environment variables, dependency versions, permission configuration |
| Permission/security | None; preserve `@login_required` on `/dashboard` and `/api/get_db_disbursement` and serialize aggregate values only | No new role, token, or access path |
| Documentation | Update current dashboard/API descriptions to the approved target contract | No product or KB documentation write |

The checkout scan found no in-repository caller of `/api/get_db_disbursement` beyond its definition. External consumers cannot be verified from this worktree; if one is identified before implementation, pause for a compatibility decision rather than silently returning both list and chart semantics.

## 7. Observability, rollback, and security

There is no feature-specific metrics or tracing facility in the Refactoring repository. Reuse the existing Flask request/error handling and API `code`/`msg` response. Focused tests make the source filter, latest-snapshot boundary, month/timezone mapping, averages, gap omission, empty shape, API envelope, and protected routes observable. Do not log source records, credentials, or new raw financial data.

Rollback is a code-only rollback to the pre-feature `main.py` projection/API data shape and the pre-feature DB Disbursement template. No database repair, migration reversal, or external integration rollback is required because the change is read-only. If an external API consumer is discovered, compatibility/rollback sequencing must be resolved before deployment.

## 8. Verification strategy

The tester-owned manual cases will use the exact Gate 2 inputs and later verify the approved user flow. Developer/tester loops should provide focused automated evidence as follows:

- Server tests: preserve the exact `Loan booked` filter; verify `EX-N-001` averages; verify an aware timestamp crossing a UTC/local-month boundary; verify `EX-E-001` omits February; verify one sample per latest statement; verify empty/no-Mongo shape; verify the API success/error envelope and unauthenticated redirects.
- UI/route tests: with the existing authenticated client and mocked Mongo, verify the populated page contains the DB chart canvas and two datasets, contains no old DB Disbursement table, uses safe serialized data, and preserves unrelated chart markup; verify the empty projection uses the existing no-data default and does not initialize a chart.
- Regression: retain `backend/tests/test_smoke.py` protected-route/dashboard loading coverage and run the repository-selected `pytest` suite after focused tests. Do not run UAT-write scripts or connect to a real Mongo instance.
- Manual E2E: the later `testcases.md` must cover `AC-001..AC-006` and `PROTOTYPE-VALIDATION-001..005` without introducing a new business outcome.

## 9. Alternatives considered

1. **Mongo aggregation pipeline with timezone operators.** Rejected for this bounded change: the current helper already owns the read projection and its Python conversion/access boundary is covered by tests. A pipeline would add Mongo server/operator compatibility without evidence that it is needed.
2. **Send raw records and aggregate in JavaScript.** Rejected: it exposes more financial source data, duplicates calculation/timezone logic in the browser, and weakens the protected server boundary.
3. **Add a new chart endpoint while retaining the old endpoint.** Rejected by the approved replacement scope and the absence of an in-repository caller. Reconsider only if an external consumer is explicitly identified.
4. **Keep the old table beside the chart.** Rejected by the approved out-of-scope behavior and `AC-001`.
5. **Add a new persistence snapshot or migration.** Rejected: the existing flattened latest statement already supplies the required fields and the feature is read-only.

## 10. Assumptions and unresolved technical decisions

- **Bounded assumption — stored date representation:** current import and aggregate evidence supplies `datetime` values in `bank_statements[0].start_date`. Naive values are treated as Asia/Shanghai local values and aware values are converted. No arbitrary string parser or fallback date is authorized.
- **Bounded assumption — numeric defaults:** preserve the current helper's `safe_to_float()` behavior and existing application display defaults. Product meaning for currency, units, precision, rounding, and partial data is not expanded.
- **Unresolved — external API consumers:** none are locatable in this checkout. A discovered consumer may require a compatibility design revision (`DESIGN_GAP`) before implementation.
- **Unresolved — unsupported/missing persisted dates:** if real eligible records contain a date form outside the bounded existing representation and omission would change product meaning, route `REQUIREMENT_GAP`; do not invent behavior in code or tasks.
- **Unresolved — tooltip presentation:** use existing two-decimal display conventions only as presentation, with unrounded aggregate payloads. Any different precision or rounding policy requires Product to revise the baseline.

## 11. Requirement → design traceability

| Product IDs | Design coverage |
| --- | --- |
| `R-001`, `AC-001` | §5 table replacement and chart-only populated state; §8 UI verification |
| `R-002`, `AC-002` | §4 Asia/Shanghai date conversion and `YYYY-MM` assignment; §8 boundary test |
| `R-003`, `R-004`, `AC-003` | §4 independent averages and parallel series; §5 two datasets; `EX-N-001` verification |
| `R-005`, `AC-004` | §4 populated buckets only; §5 exact categories; `EX-E-001` verification |
| `R-006`, `AC-005` | §2 source/filter/access evidence; §6 source and permission boundaries; protected-route tests |
| `R-007`, `AC-006` | §4 empty/API/page defaults; §5 empty branch; `EX-EMPTY-001` verification |
| `CI-001` | §4 date/aggregation boundary and §10 bounded defaults |
| `CI-002` | §2/§6 read-only KB boundary; governance-only and not an implementation task |
| `EX-N-001`, `EX-E-001`, `EX-EMPTY-001` | §8 focused verification and the corresponding task entries |
| `PROTOTYPE-VALIDATION-001..005` | §5 frontend behavior and §8 later manual E2E coverage |

No new requirement, acceptance criterion, example, permission, or business rule is introduced.
