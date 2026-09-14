# Knowledge and Project Read Records — Buyer Credit Limit Utilization on Dashboard

## Primary preflight — development execution start

- Role: primary
- Phase: development_execution
- Feature: `BUYER-CREDIT-dashboard1`
- Task: TASK-001 initial dispatch context
- Read status: PARTIAL
- Knowledge root: `C:/aiproject/a8_repo`
- Project root: `C:/aiproject/.worktrees/air8-refactoring/A8-67-buyer-credit-limit-utilization-on-dashboard`
- Project HEAD: `c912eeaa3ea5b4b3bc51424cc5fcc5b5d8f442da`
- Working tree: clean tracked files; untracked feature specification artifacts under `specs/`

### Knowledge originals read

- `C:/aiproject/a8_repo/INDEX.md` — router and feature registry; Buyer Credit Limit Utilization is not registered.
- `C:/aiproject/a8_repo/tech/systems/map.md` — placement matrix; it documents the supplier portal and does not authorize Refactoring implementation or remote Hermes changes.
- `C:/aiproject/a8_repo/tech/systems/air8-supplier-portal.md` — portal ownership evidence; it is a different repository/system from this Refactoring worktree.

### Project originals read

- Approved input: Linear Requirement Confirmation A8-69, revision RC-003.
- Approved input: Linear Prototype Confirmation A8-71, `Prototype Analyze Done`.
- Approved input: Linear Task Breakdown A8-75, `Dev Analyze Done`.
- Approved input: Linear Test Cases A8-76, `Dev Analyze Done`.
- `specs/a8-67-buyer-credit-limit-utilization-dashboard/design.md`
- `specs/a8-67-buyer-credit-limit-utilization-dashboard/tasks.md`
- `specs/a8-67-buyer-credit-limit-utilization-dashboard/testcases.md`
- `backend/app/services/onboarding_sync_service.py`
- `backend/app/services/credit_limit_service.py`
- `backend/app/routes/main.py`
- `backend/app/routes/credit.py`
- `backend/app/templates/dashboard.html`
- `backend/app/models/user.py`
- `backend/tests/test_onboarding_sync.py`
- `backend/tests/test_credit_limit_service.py`
- `backend/tests/test_credit_query_route.py`

### Findings and limitations

- `DOC_FACT`: The approved design requires verified currency propagation and an authoritative Admin predicate; it explicitly says to stop with `DESIGN_GAP` if either contract is unavailable.
- `CODE_FACT`: The current Refactoring source uses `login_required`; the inspected `User` model does not expose an obvious role/admin field.
- `CODE_FACT`: Existing Credit Query behavior derives credit utilization from the legacy Financing Amount/advance-ratio path; this is evidence only and is not the new product meaning.
- `INFERENCE`: The A8 knowledge library does not contain an authoritative feature definition for this Refactoring feature, so implementation decisions must remain within the approved RC-003/design contract and current Refactoring evidence.
- `LIMITATION`: The primary preflight did not treat the supplier-portal knowledge documents as Refactoring implementation authority. No remote Hermes or external deployment contract was accessed.
- `BLOCKING_GAP`: DEC-001 and DEC-002 remain explicit design prerequisites for affected implementation tasks until independently resolved by the developer from authorized local evidence or a revised approved design.
