# A8-42 Manual E2E Test Cases — DB Disbursement Monthly Chart

**Feature**

`A8-refactoring1` — Change the Refactoring dashboard DB loan disbursement list to a monthly amount and interest line chart.

**Approved baseline**

`A8-42-RC-v0.1` — `specs/A8-42-dashboard-db-loan-disbursement-chart/spec.md`

**User flow**

`specs/A8-42-dashboard-db-loan-disbursement-chart/user-flow.md`

**Technical design**

`A8-42-DESIGN-v0.2` — `specs/A8-42-dashboard-db-loan-disbursement-chart/design.md`

**Task plan**

`A8-42-TASKS-v0.2` — `specs/A8-42-dashboard-db-loan-disbursement-chart/tasks.md`

**Purpose and review boundary**

These are manual, human-reviewable scenarios for Gate 3. They verify the approved dashboard user journey, deterministic monthly projection, preserved access/source/error boundaries, and the designed presentation/regression surface. They do not define automation scripts, new business outcomes, new Product-owned IDs, currency/unit rules, precision/rounding rules, partial-data semantics, filters, or alternate table behavior.

For every numeric check, use the existing application units and display defaults. Recalculate the expected value from the approved rule before inspecting the chart: arithmetic average per populated calendar month, with Finance Details Start Date interpreted in `Asia/Shanghai`. A missing month is absent, not a zero point.

## Journey 1 — Authorized dashboard entry and populated chart

### TC-001 — Display the populated monthly chart and the EX-N-001 averages

- **Journey/group:** Authorized dashboard entry and populated chart
- **Risk:** High
- **Related tasks:** `TASK-001`, `TASK-002`
- **Product traceability:** `AC-001`, `AC-002`, `AC-003`; `R-001`, `R-002`, `R-003`, `R-004`; `EX-N-001`; `PROTOTYPE-VALIDATION-001`, `PROTOTYPE-VALIDATION-003`
- **Preconditions:** Use a permitted dashboard user. The existing DB loan source contains exactly two eligible records whose Finance Details Start Dates, interpreted in Asia/Shanghai, fall in `2026-01`; amount values are `100` and `300`, and interest values are `10` and `30`, in their existing application units. No record is placed in another populated month for this case.
- **User steps:**
  1. Sign in through the existing login flow.
  2. Open the existing dashboard.
  3. Locate the `DB Disbursement` area.
  4. Inspect the chart type, month category, legend, and the point/tooltip values for both series.
- **Expected outcome:** The DB Disbursement area shows one line-chart category `2026-01`, no old DB Disbursement list/table, and two distinct series whose single point is average amount `200` and average interest `20`; the values are independently recalculable as `(100 + 300) / 2` and `(10 + 30) / 2`.
- **Edge/error coverage:** Confirms replacement rather than coexistence, separate metrics, and the normal populated path.
- **Human review focus:** Confirm that the two series are visually distinguishable and that the chart communicates the same existing units without inventing labels or precision rules.

### TC-002 — Assign records at an Asia/Shanghai month boundary

- **Journey/group:** Authorized dashboard entry and populated chart
- **Risk:** High
- **Related tasks:** `TASK-001`, `TASK-002`
- **Product traceability:** `AC-002`, `AC-003`; `R-002`, `R-003`, `R-004`; `EX-N-001`; `PROTOTYPE-VALIDATION-002`, `PROTOTYPE-VALIDATION-003`
- **Preconditions:** Use a permitted dashboard user and controlled eligible source data with two timezone-aware Finance Details Start Dates: record A at `2026-01-31T15:59:59Z` (which is `2026-01-31` in Asia/Shanghai) with amount `100` and interest `10`; record B at `2026-02-01T00:00:00Z` (which is `2026-02-01` in Asia/Shanghai) with amount `300` and interest `30`. No other eligible records are present.
- **User steps:**
  1. Open the dashboard as the permitted user.
  2. Locate DB Disbursement.
  3. Read the x-axis categories and each series value.
- **Expected outcome:** The chart categories are exactly `2026-01` followed by `2026-02`; the January point is amount `100` and interest `10`, and the February point is amount `300` and interest `30`, proving that each record is assigned by its Asia/Shanghai calendar month rather than by the UTC date.
- **Edge/error coverage:** Covers the month-boundary condition without changing the approved date rule or adding a new worked-example ID.
- **Human review focus:** Verify the displayed category order and that no record is shifted into the neighboring month by the browser or server timezone.

## Journey 2 — Compare populated months and interpret gaps

### TC-003 — Omit a calendar month with no records

- **Journey/group:** Compare populated months and interpret gaps
- **Risk:** High
- **Related tasks:** `TASK-001`, `TASK-002`
- **Product traceability:** `AC-002`, `AC-003`, `AC-004`; `R-002`, `R-003`, `R-005`; `EX-E-001`; `PROTOTYPE-VALIDATION-004`
- **Preconditions:** Use a permitted dashboard user. The eligible source has records in `2026-01` and `2026-03`, with no Finance Details Start Date in `2026-02` under Asia/Shanghai interpretation. Use at least one record in each populated month and retain known amount/interest values for recalculation.
- **User steps:**
  1. Open the dashboard and locate DB Disbursement.
  2. Read all x-axis categories from left to right.
  3. Inspect the line geometry and values for the populated months.
- **Expected outcome:** The chart displays `2026-01` and `2026-03` as the populated categories in ascending order, with no `2026-02` category and no zero-valued February point; each displayed category still has one amount and one interest value.
- **Edge/error coverage:** Covers a missing middle month and guards against synthesizing a zero category or treating a gap as a record.
- **Human review focus:** Confirm that the visual gap is understandable and is not presented as a misleading zero value.

### TC-004 — Preserve the eligible source and newest-statement sample boundary

- **Journey/group:** Compare populated months and interpret gaps
- **Risk:** High
- **Related tasks:** `TASK-001`, `TASK-002`
- **Product traceability:** `AC-003`, `AC-005`; `R-003`, `R-004`, `R-006`; `EX-N-001`
- **Preconditions:** Use a permitted dashboard user and a controlled source fixture containing: one `Loan booked` overview with a newest `bank_statements[0]` sample and an older historical statement, plus one non-`Loan booked` overview in the same calendar month. Give the newest sample amount `100`/interest `10`, the older sample different values, and the non-eligible overview amount `900`/interest `90`.
- **User steps:**
  1. Open the dashboard.
  2. Locate DB Disbursement and inspect the month point.
  3. Compare the displayed value with the newest eligible sample and the excluded values.
- **Expected outcome:** The month point reflects the eligible overview's newest statement exactly once; the older statement is not double-counted and the non-`Loan booked` overview does not affect either series.
- **Edge/error coverage:** Covers source-filter preservation, historical snapshot duplication, and cross-record contamination.
- **Human review focus:** Treat any inclusion of the excluded record or historical statement as a High-risk data-correctness failure, not as a presentation difference.

## Journey 3 — Empty, missing, and failed data defaults

### TC-005 — Show the existing default for an empty source

- **Journey/group:** Empty, missing, and failed data defaults
- **Risk:** Medium
- **Related tasks:** `TASK-001`, `TASK-002`
- **Product traceability:** `AC-006`; `R-007`; `EX-EMPTY-001`; `PROTOTYPE-VALIDATION-005`
- **Preconditions:** Use a permitted dashboard user. The existing DB loan source returns no usable records and the pre-feature dashboard default is available for comparison in the same test environment.
- **User steps:**
  1. Open the dashboard.
  2. Locate DB Disbursement.
  3. Observe the area without adding or selecting any new feature-specific empty-state control.
- **Expected outcome:** The DB Disbursement area shows the existing application empty/loading default, equivalent to the established `common.table.no_data` behavior for an empty projection, and does not initialize or display a misleading chart with zero points; no new business message or fallback is introduced.
- **Edge/error coverage:** Covers no usable records and the empty chart boundary.
- **Human review focus:** Compare with the existing default rather than approving newly authored empty-state copy as product behavior.

### TC-006 — Preserve the existing page and API failure defaults

- **Journey/group:** Empty, missing, and failed data defaults
- **Risk:** High
- **Related tasks:** `TASK-001`, `TASK-002`
- **Product traceability:** `AC-006`, `AC-005`; `R-007`, `R-006`; `EX-EMPTY-001`; `PROTOTYPE-VALIDATION-005`
- **Preconditions:** Use a permitted dashboard user and a controlled test environment that can make the existing Mongo boundary unavailable for the dashboard page, and can make the API helper raise through its existing exception boundary. Do not call a development or production database.
- **User steps:**
  1. Request `/dashboard` while the page data boundary is unavailable.
  2. Request `/api/get_db_disbursement` while the helper failure is active.
  3. Restore the controlled fixture and reopen the dashboard.
- **Expected outcome:** `/dashboard` retains the established page failure response (`500` with the existing `Database not connected` behavior when Mongo is unavailable), while the authenticated API retains its existing error envelope with `code: 1`, the existing exception message field, and `data: {}`; after restoration, the normal chart flow works without a new recovery/business message.
- **Edge/error coverage:** Covers unavailable source, API exception handling, and recovery to the existing normal path.
- **Human review focus:** Verify that the feature does not swallow errors, expose raw financing records, or introduce a new failure semantic.

## Journey 4 — Access boundary and API compatibility

### TC-007 — Preserve authentication on the page and chart API

- **Journey/group:** Access boundary and API compatibility
- **Risk:** High
- **Related tasks:** `TASK-001`, `TASK-002`
- **Product traceability:** `AC-005`, `AC-001`; `R-006`, `R-001`; `EX-N-001`
- **Preconditions:** Prepare one eligible populated fixture as in `EX-N-001`, plus one logged-out browser/session and one permitted logged-in session.
- **User steps:**
  1. In the logged-out session, request `/dashboard`.
  2. In the same logged-out session, request `/api/get_db_disbursement`.
  3. Sign in through the existing login flow.
  4. Repeat both requests in the permitted session.
- **Expected outcome:** Both logged-out requests preserve the existing redirect to `/auth/login`; both authenticated requests remain accessible, and the dashboard shows the populated chart for the permitted user without requiring a new role, token, or permission path.
- **Edge/error coverage:** Covers page/API permission parity and prevents an unauthenticated chart-data bypass.
- **Human review focus:** Confirm the access boundary is unchanged and no raw data is returned before authentication.

### TC-008 — Preserve the authenticated API envelope and chart payload alignment

- **Journey/group:** Access boundary and API compatibility
- **Risk:** High
- **Related tasks:** `TASK-001`, `TASK-002`
- **Product traceability:** `AC-002`, `AC-003`, `AC-005`, `AC-006`; `R-002`, `R-003`, `R-004`, `R-006`, `R-007`; `EX-N-001`, `EX-EMPTY-001`
- **Preconditions:** Use an authenticated client and a populated fixture with known `EX-N-001` values, then an empty fixture. The API is the existing `GET /api/get_db_disbursement` route.
- **User steps:**
  1. Request the API with the populated fixture.
  2. Verify the JSON keys and parallel array indexes.
  3. Repeat with the empty fixture.
- **Expected outcome:** The populated response remains `{code: 0, msg: "success", data: ...}`, where `data.months` is ascending and `data.series.disbursement_amount` and `data.series.interest` have equal length and the `EX-N-001` values; the empty response keeps the same chart-shaped data contract with empty month and series arrays.
- **Edge/error coverage:** Covers route-envelope compatibility and the server-to-chart alignment contract without retaining the old list-shaped payload.
- **Human review focus:** Check that values are not recomputed from raw records in the browser and that array indexes identify the same month across both series.

## Journey 5 — Theme, responsive presentation, and feature regression

### TC-009 — Keep both series readable across the existing theme switch

- **Journey/group:** Theme, responsive presentation, and feature regression
- **Risk:** Medium
- **Related tasks:** `TASK-002`
- **Product traceability:** `AC-001`, `AC-003`, `AC-006`; `R-001`, `R-003`, `R-004`, `R-007`; `EX-N-001`; `PROTOTYPE-VALIDATION-001`, `PROTOTYPE-VALIDATION-003`, `PROTOTYPE-VALIDATION-005`
- **Preconditions:** Use a permitted user with the populated `EX-N-001` fixture. The existing light/dark theme control and the existing Chart.js CDN path are available.
- **User steps:**
  1. Open DB Disbursement in the default theme.
  2. Record the visible categories and both values.
  3. Switch to the other existing theme.
  4. Inspect the chart, legend, axes/grid, and a tooltip in the new theme.
- **Expected outcome:** The same month and numeric values remain visible after the theme change; both series, legend, axes/grid, and tooltip retain readable contrast using the existing theme update path, with no chart reset, missing series, or new theme-specific business meaning.
- **Edge/error coverage:** Covers theme-change state transition and visual readability for both data series.
- **Human review focus:** Check contrast, series distinction, and data preservation rather than approving a new color or formatting rule.

### TC-010 — Keep the chart usable at responsive widths and with existing controls

- **Journey/group:** Theme, responsive presentation, and feature regression
- **Risk:** Medium
- **Related tasks:** `TASK-002`
- **Product traceability:** `AC-001`, `AC-003`, `AC-005`; `R-001`, `R-003`, `R-004`, `R-006`, `R-007`; `EX-N-001`; `PROTOTYPE-VALIDATION-001`, `PROTOTYPE-VALIDATION-003`
- **Preconditions:** Use a permitted user with the populated fixture. Prepare desktop, tablet, and narrow mobile viewport sizes supported by the existing dashboard; do not add a feature-specific responsive control.
- **User steps:**
  1. Open the dashboard at desktop width and inspect the DB Disbursement card.
  2. Resize or reopen at tablet and narrow mobile widths.
  3. Inspect the chart canvas, month labels, legend, tooltip/point inspection, navigation, and existing theme/language controls.
- **Expected outcome:** The DB Disbursement card and chart remain within the viewport without horizontal clipping or overlap, the two series and their month/value context remain human-readable, and existing dashboard controls remain usable at each supported width; no alternate table or new responsive business behavior appears.
- **Edge/error coverage:** Covers responsive layout, label/legend readability, and interaction affordance where the existing Chart.js/dashboard implementation supports it.
- **Human review focus:** Review keyboard focus, non-color cues, text scaling, and screen-reader-visible chart context as applicable to the existing application defaults; do not infer a new accessibility requirement from this case.

### TC-011 — Leave unrelated dashboard surfaces unchanged

- **Journey/group:** Theme, responsive presentation, and feature regression
- **Risk:** High
- **Related tasks:** `TASK-001`, `TASK-002`
- **Product traceability:** `AC-001`, `AC-003`, `AC-005`; `R-001`, `R-003`, `R-004`, `R-006`; `EX-N-001`; `PROTOTYPE-VALIDATION-001`, `PROTOTYPE-VALIDATION-003`
- **Preconditions:** Use a permitted user with the populated fixture and known counts for the existing dashboard summary cards. The existing data-distribution pie chart is populated.
- **User steps:**
  1. Open the dashboard and record the four summary-card counts and data-distribution pie-chart labels/values.
  2. Inspect DB Disbursement.
  3. Verify the hidden Settlement Schedule block, version footer, navigation, and other dashboard areas.
  4. Inspect the DB Disbursement legend and confirm no purchase-price series is shown.
- **Expected outcome:** Only the DB Disbursement presentation/data projection changes: the four counts, pie chart, hidden Settlement Schedule block, footer, navigation, and unrelated areas retain their established behavior; DB Disbursement has only amount and interest series and no purchase-price series or retained table.
- **Edge/error coverage:** Covers hidden scope expansion, unrelated-card regression, and accidental retention of an out-of-scope metric.
- **Human review focus:** Compare against the baseline dashboard and treat changes outside DB Disbursement as a regression unless separately approved.

## Coverage summary

| Area | Cases | Primary Product IDs | Primary tasks |
| --- | --- | --- | --- |
| Normal chart replacement and averages | `TC-001` | `AC-001..AC-003`, `EX-N-001` | `TASK-001`, `TASK-002` |
| Asia/Shanghai month assignment | `TC-002` | `AC-002..AC-003`, `EX-N-001` | `TASK-001`, `TASK-002` |
| Missing-month omission | `TC-003` | `AC-002..AC-004`, `EX-E-001` | `TASK-001`, `TASK-002` |
| Source/access and snapshot boundaries | `TC-004`, `TC-007` | `AC-005`, `EX-N-001` | `TASK-001`, `TASK-002` |
| Empty and failure defaults | `TC-005`, `TC-006`, `TC-008` | `AC-006`, `EX-EMPTY-001` | `TASK-001`, `TASK-002` |
| API contract | `TC-006`, `TC-008` | `AC-005..AC-006`, `EX-N-001`, `EX-EMPTY-001` | `TASK-001`, `TASK-002` |
| Theme and responsive/accessibility review | `TC-009`, `TC-010` | `AC-001`, `AC-003`, `AC-005`, `EX-N-001` | `TASK-002` |
| Unrelated dashboard regression and scope | `TC-011` | `AC-001`, `AC-003`, `AC-005`, `EX-N-001` | `TASK-001`, `TASK-002` |

No acceptance criterion, worked-example ID, or business outcome is added or renumbered by this proposal.
