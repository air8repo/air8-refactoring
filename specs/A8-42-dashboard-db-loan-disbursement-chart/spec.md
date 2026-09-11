# A8-42 Product Requirement Baseline

**Baseline Revision**
A8-42-RC-v0.1

**Status**
Materialized for Gate 2

**Source Revision**
Main issue A8-42 and approved Requirement Confirmation child A8-44; Gate 1 Auto-Gated decision read back on 2026-09-11.

# Part 1 — Business View

## 1. Goal and Business Value

Change the Refactoring dashboard DB loan disbursement area from a list/table presentation to a monthly line chart so dashboard users can compare disbursement amount and interest trends over time.

## 2. People and Permissions

- **Primary actor:** A permitted dashboard user.
- **Affected people:** Users who review DB loan disbursement trends.
- **Visibility/permission boundary:** Preserve the existing dashboard access rule; no new permission model is introduced.

## 3. Current and Target Behavior

- **Current behavior:** The DB Disbursement area is presented as a batch-based list/table using the existing DB loan source.
- **Target change:** Present calendar-month average disbursement amount and average interest as two distinct line-chart series.
- **Unchanged behavior:** Existing source, dashboard access, unspecified presentation defaults, and existing empty/loading/error defaults remain unchanged.

## 4. Scope

### In Scope

- Replace the DB loan disbursement list/table with a monthly line chart.
- Use Finance Details Start Date, interpreted in Asia/Shanghai, as the month basis.
- Average amount and interest independently for each populated calendar month.
- Omit months with no records.

### Out of Scope

- Retaining the old table as an alternate view.
- Changes to unrelated dashboard cards, charts, or reports.
- A new data source, permission model, currency/unit rule, precision/rounding rule, filter, partial-data rule, or failure semantic.

## 5. User-Visible Flow

1. A permitted user opens the dashboard.
2. The user locates DB Disbursement.
3. The system shows a monthly line chart with separate amount and interest series.
4. The user compares trends across populated months.
5. Months without data are absent. Empty, missing, or failed loading uses the existing application default.

## 6. Key Decisions and Confirmed Information

- `CI-001` — Finance Details Start Date is interpreted in Asia/Shanghai, grouped by calendar month, with monthly averages and no displayed month without data.
- `CI-002` — The existing DB loan source and dashboard access rule remain unchanged; unspecified display and failure behavior follows existing application defaults.

# Part 2 — Development View

## 7. Current-to-Target Differences

| Area | Current | Target | Related Rules |
|---|---|---|---|
| Presentation | Batch-based table/list | Monthly line chart | `R-001` |
| Time basis | First bank-statement start date per batch | Finance Details Start Date in Asia/Shanghai | `R-002` |
| Aggregation | Batch sums | Per-month averages for amount and interest | `R-003` |
| Empty months | Batch-driven output | Omitted from displayed months | `R-005` |
| Source/access | Existing DB source and dashboard access | Preserved | `R-006`, `R-007` |

## 8. Canonical Business Rules

### R-001 — Chart presentation
- **Applies when:** The permitted user views the dashboard DB Disbursement area.
- **Inputs/data meaning:** Existing DB loan disbursement records.
- **Rule:** The area is a line chart rather than the existing list/table.
- **Output:** The user sees the chart and not the old list/table.
- **Exceptions/boundaries:** The old table is not retained as an alternate view.

### R-002 — Calendar-month assignment
- **Applies when:** A source record has a Finance Details Start Date.
- **Inputs/data meaning:** Interpret the date in Asia/Shanghai and use its calendar year-month.
- **Rule:** Assign each record to the calendar month determined by that date basis.
- **Output:** Each record contributes to exactly one month bucket.
- **Exceptions/boundaries:** Months without records create no displayed bucket.

### R-003 — Monthly average aggregation
- **Applies when:** A month contains one or more usable records.
- **Inputs/data meaning:** Existing amount and interest values in their current application units.
- **Rule:** Calculate the arithmetic average of amount and the arithmetic average of interest independently for each month.
- **Output:** One amount value and one interest value per displayed month.
- **Exceptions/boundaries:** Currency, precision, and rounding remain existing application defaults.

### R-004 — Separate series
- **Applies when:** A populated month is displayed.
- **Rule:** Render disbursement amount and interest as distinct chart series.
- **Output:** The user can compare the two metrics independently.
- **Exceptions/boundaries:** No purchase-price series is added by this request.

### R-005 — Omit empty months
- **Applies when:** No record belongs to a calendar month.
- **Rule:** Do not render that month as a zero-valued chart point.
- **Output:** The month is absent from the displayed chart categories.
- **Exceptions/boundaries:** Existing empty-data defaults apply when no usable records exist at all.

### R-006 — Preserve source and access
- **Applies when:** The chart loads for an authorized dashboard user.
- **Rule:** Continue using the existing DB loan source and dashboard access boundary.
- **Output:** No new permission or source behavior is visible.
- **Exceptions/boundaries:** Unrelated dashboard areas remain unchanged.

### R-007 — Existing defaults
- **Applies when:** Units, precision, rounding, partial-data, filters, responsive behavior, or loading errors are encountered.
- **Rule:** Follow existing application defaults; this request adds no new business meaning.
- **Output:** The existing default behavior remains visible.
- **Exceptions/boundaries:** Any change to these meanings requires a new product decision and baseline revision.

## 9. Acceptance Criteria

### AC-001 — Monthly chart replaces list
- **Linked rules:** `R-001`
- **Given:** A permitted user is viewing the dashboard.
- **When:** The DB Disbursement area loads.
- **Then:** A line chart is shown and the old list/table is not shown.
- **Examples:** `EX-N-001`

### AC-002 — Asia/Shanghai month basis
- **Linked rules:** `R-002`
- **Given:** Records have Finance Details Start Dates.
- **When:** The chart assigns records to months.
- **Then:** Each record is assigned using its Asia/Shanghai calendar year-month.
- **Examples:** `EX-N-001`, `EX-E-001`

### AC-003 — Separate monthly averages
- **Linked rules:** `R-003`, `R-004`
- **Given:** A month has usable records.
- **When:** Its chart point is calculated.
- **Then:** The point exposes one average amount and one average interest in separate series.
- **Examples:** `EX-N-001`

### AC-004 — No empty-month point
- **Linked rules:** `R-005`
- **Given:** No record belongs to a calendar month.
- **When:** The chart renders its month categories.
- **Then:** That month is absent rather than shown as zero.
- **Examples:** `EX-E-001`

### AC-005 — Existing source and access preserved
- **Linked rules:** `R-006`
- **Given:** The dashboard is used under its existing access boundary.
- **When:** DB Disbursement data loads.
- **Then:** The existing source and access behavior remain in force.
- **Examples:** `EX-N-001`

### AC-006 — Existing defaults for empty/error states
- **Linked rules:** `R-007`
- **Given:** The source is empty, missing, or fails to load.
- **When:** The DB Disbursement area responds.
- **Then:** Existing application default behavior is shown without a new business message or fallback.
- **Examples:** `EX-EMPTY-001`

## 10. Worked Examples

### EX-N-001 — Normal monthly aggregation
- **Linked rules/criteria:** `R-002`, `R-003`, `R-004`, `AC-001`, `AC-002`, `AC-003`
- **Input:** Two records with Finance Details Start Dates interpreted in Asia/Shanghai falling in 2026-01; amount values 100 and 300; interest values 10 and 30, in existing application units.
- **Rule:** `(100 + 300) / 2 = 200` amount and `(10 + 30) / 2 = 20` interest.
- **Expected output:** One `2026-01` chart point with average amount 200 and average interest 20 as separate series.

### EX-E-001 — Month without data
- **Linked rules/criteria:** `R-002`, `R-005`, `AC-002`, `AC-004`
- **Input:** Records exist in 2026-01 and 2026-03, but none has a Finance Details Start Date in 2026-02 under Asia/Shanghai interpretation.
- **Rule:** Only months containing records produce chart categories.
- **Expected output:** `2026-02` is absent from the chart.

### EX-EMPTY-001 — No usable records
- **Linked rules/criteria:** `R-007`, `AC-006`
- **Input:** The existing DB loan source returns no usable records.
- **Rule:** Use the existing application empty/loading default.
- **Expected output:** The existing default empty/loading behavior is shown; no new fallback message is introduced.

## 11. Deferred Interaction Validation

None. The prototype demonstrates the bounded presentation and state controls without deferring business meaning.

## 12. Unresolved Conflicts and Items

None in the approved baseline. The A8 knowledge-placement follow-up is governance-only and does not change this product contract.

## 13. Traceability

| Rule | Acceptance Criterion | Confirmed Facts | Worked Examples | Prototype Validation |
|---|---|---|---|---|
| `R-001` | `AC-001` | `CI-001` | `EX-N-001` | `PROTOTYPE-VALIDATION-001` |
| `R-002` | `AC-002` | `CI-001` | `EX-N-001`, `EX-E-001` | `PROTOTYPE-VALIDATION-002` |
| `R-003`, `R-004` | `AC-003` | `CI-001` | `EX-N-001` | `PROTOTYPE-VALIDATION-003` |
| `R-005` | `AC-004` | `CI-001` | `EX-E-001` | `PROTOTYPE-VALIDATION-004` |
| `R-006`, `R-007` | `AC-005`, `AC-006` | `CI-002` | `EX-N-001`, `EX-EMPTY-001` | `PROTOTYPE-VALIDATION-005` |
