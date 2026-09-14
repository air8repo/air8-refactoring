# Manual E2E Test Cases — Buyer Credit Limit Utilization on Dashboard

Product baseline: RC-003 (Requirement Confirmation A8-69). Gate 2 prototype: A8-71. These are manual review scenarios, not automation scripts.

## Journey 1 — Review current utilization

### TC-001 — Render and sort normal USD results

- Risk: High
- Tasks: TASK-001, TASK-002, TASK-003, TASK-005
- Product links: AC-001–AC-005, AC-007–AC-008; EX-N-001, EX-N-002
- Preconditions: Admin user; selected USD fixtures include B001 limits 100,000 and 50,000 with selected latest Loan booked outstanding amounts 60,000 and 20,000, plus another buyer with a higher rate.
- Steps: Open Dashboard; select USD; wait for the request; inspect chart, table, and latest-data labels.
- Expected outcome: Only qualifying buyers appear, grouped by Buyer Code and sorted highest utilization first. B001 shows limit 150,000.00, Used Credit 80,000.00, utilization 53.33%, Remaining Credit 70,000.00, and Asia/Shanghai time; all seven approved fields and chart-level latest time are visible.
- Edge/error coverage: Buyer without a qualifying latest booked item is absent.
- Review focus: Aggregation is independently recalculable and each financing item is counted once.

### TC-002 — Select EUR without cross-currency mixing

- Risk: High
- Tasks: TASK-001, TASK-002, TASK-003, TASK-005
- Product links: AC-006, AC-008; EX-N-003, PROTOTYPE-VALIDATION-002
- Preconditions: A buyer has both USD and EUR limit and financing records.
- Steps: Record the USD result; change the selector to EUR; wait for refresh; compare rows; switch back to USD.
- Expected outcome: Only the selected currency contributes, with no conversion or cross-currency sum. Each selection recalculates and displays two-decimal values.
- Edge/error coverage: Switching back restores the USD-scoped result rather than merging data.
- Review focus: Selector and refresh stay within the approved USD/EUR scope.

### TC-003 — Select deterministic latest snapshot and chart-level time

- Risk: High
- Tasks: TASK-001, TASK-002, TASK-003
- Product links: R-004, R-007, AC-003, AC-005; EX-N-002
- Preconditions: Multiple snapshots exist per financing item, including a full timestamp tie with different system invoice IDs; included buyers have different effective times.
- Steps: Open Dashboard; inspect Used Credit, status eligibility, each buyer timestamp, and chart-level latest time.
- Expected outcome: Selection uses invoice.creation_time, then updated_at, then created_at in UTC, then greatest invoice.system_invoice_id on a full tie. Each item contributes once; chart-level time is the maximum effective time displayed in Asia/Shanghai and each buyer retains its own time.
- Edge/error coverage: An older snapshot with a larger amount does not contribute.
- Review focus: Timestamp and tie-break behavior is deterministic.

## Journey 2 — Interpret boundaries and empty data

### TC-004 — Show unavailable utilization and over-limit treatment

- Risk: High
- Tasks: TASK-001, TASK-002, TASK-005
- Product links: AC-004, AC-005, AC-007, AC-008; EX-E-001, EX-E-002, PROTOTYPE-VALIDATION-001
- Preconditions: Qualifying zero-limit buyer with Used Credit 25,000; 120% buyer; exactly 100% buyer.
- Steps: Open Dashboard; inspect table values, chart, reference line, and highlight treatment.
- Expected outcome: Zero/unavailable limit remains visible with utilization Unavailable and Remaining Credit -25,000.00. The 120% buyer shows 120.00%, -20,000.00, and clear over-limit highlighting. Exactly 100% is on the boundary and is not above 100%.
- Edge/error coverage: Unavailable rates do not outrank calculable rates.
- Review focus: Boundary presentation preserves the approved business meaning.

### TC-005 — Show no-data state for no qualifying buyers

- Risk: Medium
- Tasks: TASK-001, TASK-002, TASK-003, TASK-005
- Product links: AC-002, AC-006; EX-EMPTY-001
- Preconditions: No selected latest financing item has status Loan booked for the selected currency.
- Steps: Open Dashboard and wait for the request.
- Expected outcome: The card remains available and shows an appropriate no-data message with no buyer rows or fabricated values.
- Edge/error coverage: Buyers with limits but no qualifying booked loan remain excluded.
- Review focus: Empty success is distinct from retrieval/aggregation error.

## Journey 3 — Recover from failure and verify compatibility

### TC-006 — Recover from failure without stale data

- Risk: High
- Tasks: TASK-003, TASK-005
- Product links: AC-009; EX-E-003
- Preconditions: Load a successful result, then make the current request or aggregation fail while the prior result exists in the browser.
- Steps: Trigger failure by refresh or currency change; inspect the card; restore the fixture; click Retry; wait for completion.
- Expected outcome: The module remains visible with an error and Retry, and prior successful values are not shown as current. A successful Retry displays the latest successful data.
- Edge/error coverage: Failure is not silently presented as an empty state.
- Review focus: Safe, actionable recovery without stale-data ambiguity.

### TC-007 — Enforce Admin-only access

- Risk: High
- Tasks: TASK-003, TASK-005
- Product links: AC-001, AC-006, CI-001
- Preconditions: Existing Admin and non-Admin authentication fixtures.
- Steps: Open Dashboard and request the data endpoint as each user.
- Expected outcome: Admin can access the feature; non-Admin is rejected through the existing authorization behavior without financial-data leakage or a weaker alternate path.
- Edge/error coverage: Direct endpoint access is protected as well as page access.
- Review focus: Reuse the authoritative permission boundary.

### TC-008 — Reconcile Credit Query Actual without changing other metrics

- Risk: High
- Tasks: TASK-001, TASK-002, TASK-004
- Product links: AC-003, AC-010; EX-N-001, EX-N-002
- Preconditions: Same buyer/currency produces Dashboard and Credit Query rows, including Financing Amount differing from outstanding_amount.
- Steps: Open both views; compare Dashboard Used Credit and buyer Actual; inspect reserved, settled, financing-amount, and other metrics; include a non-latest snapshot and non-booked latest status.
- Expected outcome: Dashboard Used Credit and buyer-level Credit Query Actual use the same latest-record, Loan booked, grouping, and outstanding_amount semantics. Reserved, settled, and other metrics remain unchanged.
- Edge/error coverage: Older and non-qualifying latest records do not affect the shared buyer Actual.
- Review focus: Cross-surface compatibility is explicit and limited to AC-010.

### TC-009 — Verify responsive and readable presentation

- Risk: Medium
- Tasks: TASK-005
- Product links: AC-001, AC-005, AC-008; PROTOTYPE-VALIDATION-001–002
- Preconditions: Populated Admin result set.
- Steps: Inspect desktop and narrow/mobile viewports, selector, chart/table, labels/tooltips, keyboard focus, long buyer names, and mixed unavailable/over-limit rows.
- Expected outcome: Required fields and controls remain readable and usable; reference-line, above-100%, and unavailable states are distinguishable without color alone; unrelated Dashboard content remains intact.
- Edge/error coverage: Long names and mixed boundary rows remain legible.
- Review focus: Assess only the bounded prototype presentation/interaction checks.

## Coverage summary

The cases cover all `AC-001`–`AC-010`, the approved normal/exception/empty examples, deterministic latest selection, currency isolation, permission, error/retry, Credit Query reconciliation, and responsive/accessibility review. No product IDs or business meaning are added.
