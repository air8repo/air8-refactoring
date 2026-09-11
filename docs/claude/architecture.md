# Architecture & Key Patterns

## Architecture

**Entry point**: `run_flask.py` → `backend.app.create_app()` (app factory pattern)

**Backend structure** (`backend/app/`):
- `routes/` — Flask blueprints: `main_bp` (/), `auth_bp` (/auth), `import_bp` (/import), `export_bp` (/export), `maintenance_bp` (/maintenance), `batch_bp`, `language_bp`
- `services/` — Business logic layer using strategy pattern:
  - `import_service.py` — Handles Excel imports with upsert (idempotent) logic for multiple data types (onboarding, financing, repayment, bank_statement, etc.)
  - `export_service.py` — Exports to CSV/Excel/PDF via pandas DataFrame conversion
  - `aggregate_service.py` — MongoDB aggregation pipelines with multiprocessing
  - `cleaning_service.py` — Data validation and type conversion per data type
  - `batch_service.py` — Batch grouping of financing orders, triggers aggregation after operations
  - `bank_parser/` — Extensible bank statement parser (base_parser + parser_factory pattern)
- `models/user.py` — Flask-Login UserMixin backed by MongoDB
- `forms/auth.py` — WTForms for login/register
- `templates/` — Jinja2 templates with `base.html` as the layout
- `i18n/` — JSON translation files (zh-CN.json, en-US.json, zh.json, en.json)

**Key MongoDB collections**: `refactoring_financing_order`, `refactoring_repayment_order`, `refactoring_bank_statement`, `refactoring_financing_overview`, `users`

## Key Patterns

**Database access**: `extensions.py` holds global `mongo` (pymongo database object). Services access it via `app.extensions['mongo']` or the global `mongo` from extensions. No ORM — direct pymongo operations.

**Internationalization**: Custom JSON-based i18n (not Flask-Babel .po files). Translation function `_()` injected into Jinja2 via `app.context_processor`. Keys use dot notation: `"common.title.dashboard"`. Language resolved from query param `?lang=` → cookie → default `zh-CN`.

**Configuration**: `backend/app/config.py` with `config_by_name` dict (`dev`/`test`/`prod`). MongoDB URI and other settings overridable via environment variables. Default dev config is used when none specified.

**Authentication**: Flask-Login + Werkzeug password hashing. `@login_required` decorator on protected routes.

## Development Notes

- The system is bilingual (Chinese/English). When adding UI text, add translation keys to all four JSON files in `backend/app/i18n/`.
- Excel file uploads are limited to 16MB, extensions `.xlsx` and `.xls` only.
- The `scripts/` directory contains one-off maintenance, migration, and debugging scripts — not part of the core application.
- 系统需求基线见 `docs/system/requirements.md`（唯一权威）。`backend/reqspec.md` 与 `backend/techspec.md` 为历史参考。
