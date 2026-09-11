# A8-42 User Flow — DB Disbursement Monthly Chart

**Baseline**
A8-42-RC-v0.1

**Purpose**
Show how a permitted dashboard user moves from the existing dashboard entry to a trustworthy comparison of monthly DB loan disbursement amount and interest.

## Primary flow

1. **Open dashboard** — The permitted user opens the existing dashboard.
2. **Locate DB Disbursement** — The user finds the DB Disbursement area in the dashboard.
3. **View monthly chart** — The system shows a line chart instead of the old list/table.
4. **Read the time axis** — Records are grouped by calendar month using Finance Details Start Date interpreted in Asia/Shanghai.
5. **Compare series** — The user compares the separate monthly average disbursement-amount and interest series.
6. **Interpret gaps** — Months with no records are omitted rather than shown as zero-valued points.

## Alternate review states

- **Empty source (`EX-EMPTY-001`, `AC-006`):** Existing application empty/loading default behavior is shown. No new empty-state business message is proposed.
- **Loading/error default (`AC-006`):** Existing application failure behavior remains in force. The prototype labels this state for review only and does not define new recovery semantics.

## Prototype validation anchors

- `PROTOTYPE-VALIDATION-001` — Confirm that the DB Disbursement area reads as a chart and no old list/table is present.
- `PROTOTYPE-VALIDATION-002` — Confirm that the visible source note communicates Finance Details Start Date and Asia/Shanghai month grouping.
- `PROTOTYPE-VALIDATION-003` — Confirm that amount and interest are visibly distinct series and that the worked-example values are independently readable.
- `PROTOTYPE-VALIDATION-004` — Confirm that the populated sample omits March, which has no records.
- `PROTOTYPE-VALIDATION-005` — Confirm that empty and existing-error-default states are reviewable without introducing new business meaning.

## Out-of-scope interaction

The prototype does not add filters, date-range controls, alternate table view, new permissions, currency/unit labels, rounding rules, or a new error/recovery flow.
