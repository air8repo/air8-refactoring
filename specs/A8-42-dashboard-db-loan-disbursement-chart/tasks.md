# A8-42 Task Breakdown — DB Disbursement Monthly Chart

**Baseline Revision**

`A8-42-RC-v0.1`

**Technical Design Revision**

`A8-42-DESIGN-v0.2`

**Planning revision**

`A8-42-TASKS-v0.2` — Gate 3 proposal; pending review. No Product-owned IDs are created, renumbered, reinterpreted, or weakened.

The tasks are sequential, behavior-sized developer/tester loop units. Related implementation, copy/configuration, documentation, and focused tests stay together when they deliver one independently verifiable behavior. `TASK-001` must pass before `TASK-002` starts.

## Group DATA-01 — Server projection and API contract

### TASK-001 — Produce the deterministic monthly chart payload

- **Group:** `DATA-01` — Server projection and API contract

- **Risk:** High — financial aggregation, timezone boundary, source inclusion, authenticated API contract, and regression of existing dashboard data semantics.

- **Objective:** Replace the batch-sum result of `get_db_disbursement()` with the approved deterministic chart payload: ascending `YYYY-MM` categories plus parallel average disbursement-amount and interest series. Preserve the `refactoring_status: 'Loan booked'` query, truthy `loan_submission_batch` and nonempty-statement inclusion boundary, latest `bank_statements[0]` snapshot convention, existing numeric conversion defaults, empty helper shape, authenticated API path, `{code, msg, data}` envelope, and existing exception response.

- **Expected file/symbol/API/data scope:**
  - `backend/app/routes/main.py`: `get_db_disbursement()`, `api_get_db_disbursement()`, and only directly supporting private date/bucket helpers in this module.
  - `backend/tests/test_main_dashboard_reports.py` and/or one focused `backend/tests/test_dashboard_db_disbursement_chart.py`: source filter, month assignment, averages, gap omission, latest-snapshot boundary, empty shape, API envelope/error behavior, and protected-route assertions.
  - `docs/system/modules/dashboard.md` and `docs/system/api.md`: update only the DB Disbursement description and `/api/get_db_disbursement` data-contract wording to match the approved chart target.
  - Mongo boundary: read `refactoring_financing_overview` only; no collection/schema/index/write/migration change.

- **Dependencies:** None. `TASK-002` depends on the read-back payload contract and passing focused server tests from this task.

- **Product traceability:** `R-002`, `R-003`, `R-004`, `R-005`, `R-006`, `R-007`; `AC-002`, `AC-003`, `AC-004`, `AC-005`, `AC-006`; `CI-001`; `EX-N-001`, `EX-E-001`, `EX-EMPTY-001`.

- **Verification intent:** Begin with failing focused tests. Assert the exact `Loan booked` filter. Use two same-month records to reproduce `EX-N-001` averages. Verify an aware timestamp near a UTC/local-month boundary maps to the correct Asia/Shanghai month. Verify January/March data omits February, historical snapshots are not double-counted, numeric conversion follows the current helper, and no-record/no-Mongo cases return the documented empty chart shape. Verify `/api/get_db_disbursement` keeps its success/error envelope and both protected routes redirect unauthenticated clients. Run focused tests and then the repository `pytest` suite.

- **Done condition:** The helper returns only the documented chart payload for normal, gap, and empty inputs; its source filter, latest-snapshot boundary, access behavior, and existing API envelope remain intact; dashboard/API documentation matches the contract; focused and full backend tests pass; no unrelated route, persistence, migration, permission, or product behavior changes are included.

## Group UI-01 — Dashboard chart rendering and existing defaults

### TASK-002 — Render the DB Disbursement line chart in the existing dashboard boundary

- **Group:** `UI-01` — Dashboard chart rendering and existing defaults

- **Risk:** Medium — primary dashboard presentation and meaningful empty/theme boundaries; server contract is already verified by `TASK-001`.

- **Objective:** Replace only the DB Disbursement table presentation with a responsive Chart.js line chart that consumes the `TASK-001` payload, shows distinct average amount and interest series, preserves supplied month gaps, and retains existing dashboard access, theme behavior, unrelated cards, and empty/loading/error defaults.

- **Expected file/symbol/API/data scope:**
  - `backend/app/templates/dashboard.html`: DB Disbursement card body, `dbDisbursementChart` canvas, safe Jinja JSON handoff, two line datasets, populated/empty branch, existing `chartTheme` reuse, and `theme-change` updates. Remove the old DB Disbursement table only; leave the pie chart and hidden Settlement Schedule block unchanged.
  - `backend/app/i18n/en.json`, `backend/app/i18n/en-US.json`, `backend/app/i18n/zh.json`, and `backend/app/i18n/zh-CN.json`: only aligned additive chart labels if existing keys are insufficient; no unrelated copy or business terminology change.
  - `backend/tests/test_dashboard_db_disbursement_chart.py` (new focused route/template test, or the equivalent existing dashboard test scope): authenticated populated rendering, chart/table replacement, parallel datasets, safe handoff, empty default, theme wiring, and preservation of the unauthenticated dashboard redirect.
  - Browser boundary: existing `/dashboard` HTML only; no new route, client-side data fetch, or API consumer.

- **Dependencies:** `TASK-001` payload contract, focused tests, and documentation must be complete and read back. No parallel implementation is authorized because the template consumes that contract.

- **Product traceability:** `R-001`, `R-003`, `R-004`, `R-005`, `R-006`, `R-007`; `AC-001`, `AC-003`, `AC-004`, `AC-005`, `AC-006`; `CI-001`; `EX-N-001`, `EX-E-001`, `EX-EMPTY-001`; `PROTOTYPE-VALIDATION-001..005`.

- **Verification intent:** Begin with failing render/route assertions. Verify an authenticated populated response contains the DB Disbursement chart canvas and two distinct datasets using the server months/series, contains no old DB Disbursement table or purchase-price series, and uses safe JSON serialization without database-derived HTML interpolation. Verify absent months remain absent, the existing pie chart/unrelated dashboard sections remain present, theme-change updates both charts when populated, and the existing no-data default is rendered without initializing a misleading chart when empty. Re-run focused tests and the repository `pytest` suite, then leave the approved manual user-flow checks to the tester-owned test cases.

- **Done condition:** A permitted user sees the approved monthly DB Disbursement line chart in the existing card; the old table is absent; populated and empty states use the approved/default behavior; the existing theme and unrelated dashboard behavior remain intact; enabled locale files remain valid and aligned if changed; focused and full backend tests pass without changes outside the declared UI/copy/test scope.

## Sequential execution order

1. `TASK-001` — establish, document, and verify the server/API chart contract.
2. `TASK-002` — consume that contract in the existing dashboard presentation and verify the end-user rendering.

No task covers a migration, new permission, alternate table view, new endpoint, external integration, speculative API versioning, knowledge-base write, or unrelated cleanup.

## Requirement → design → task traceability

| Product IDs | Design sections | Tasks |
| --- | --- | --- |
| `R-001`, `AC-001` | Design §5 frontend boundary | `TASK-002` |
| `R-002`, `AC-002` | Design §4 month assignment and aggregation | `TASK-001` |
| `R-003`, `R-004`, `AC-003` | Design §4 data contract; §5 frontend datasets | `TASK-001`, `TASK-002` |
| `R-005`, `AC-004` | Design §4 populated buckets; §5 supplied categories | `TASK-001`, `TASK-002` |
| `R-006`, `AC-005` | Design §2 source/access evidence; §6 server/security boundaries | `TASK-001`, `TASK-002` |
| `R-007`, `AC-006` | Design §4 empty/API defaults; §5 empty branch | `TASK-001`, `TASK-002` |
| `CI-001` | Design §4 and §10 bounded date/default assumptions | `TASK-001`, `TASK-002` |
| `CI-002` | Design §2/§6 read-only KB governance boundary | No implementation task; preserved as non-blocking context |
| `EX-N-001`, `EX-E-001`, `EX-EMPTY-001` | Design §8 verification strategy | `TASK-001`, `TASK-002` |
| `PROTOTYPE-VALIDATION-001..005` | Design §5 frontend boundary and §8 manual verification | `TASK-002` |

Every task has Product-owned acceptance mappings and a unique independently verifiable outcome. No new product meaning is embedded in the plan.
