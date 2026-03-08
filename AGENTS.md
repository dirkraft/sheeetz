# Sheeetz — Agent Instructions

## Quick Reference

- **Stack (preferred):** `cd backend && source .venv/bin/activate && sheeetz up`
- **Stack status:** `cd backend && source .venv/bin/activate && sheeetz status`
- **Stack down:** `cd backend && source .venv/bin/activate && sheeetz down`
- **API tests:** `cd backend && pytest tests/ -v --ignore=tests/test_drive.py`
- **E2E tests:** `cd e2e && npx playwright test`
- **Type check frontend:** `cd frontend && npx vue-tsc --noEmit`
- **Build frontend:** `cd frontend && npx vite build`

The stack manager implementation lives in `backend/sheeetz/cli.py` and is the source of truth for local dev process control.

## Architecture Rules

### Metadata is EAV

All sheet metadata lives in the `sheet_meta` table as `(sheet_id, key, value)` rows — NOT as columns on the `sheets` table. When querying or sorting by metadata:
- **Filtering:** use aliased JOINs on `SheetMeta` (see `meta_filters` handling in `sheets.py`)
- **Sorting:** direct columns (`filename`, `folder_path`) sort on `Sheet` attributes; any other `sort_by` value does a LEFT OUTER JOIN on `sheet_meta` filtered to that key

### PDF Metadata is Non-Destructive

User edits write to the `http://sheeetz.app/meta/1.0/` XMP namespace only. Original PDF metadata (`dc:title`, DocInfo `/Author`, etc.) is never modified. The `RAW_TO_CORE_MAP` in `storage/metadata.py` controls priority — sheeetz namespace wins over standard keys. The `pages` field is always auto-derived from `len(pdf.pages)` and must never be written.

Custom (non-core) metadata fields are any sheeetz-namespace keys not in `RAW_TO_CORE_MAP`. They are extracted by `map_raw_to_core` and stored as regular `sheet_meta` rows.

### Columns: Static vs Dynamic

`Sheets.vue` has two column types:
- **Static:** hardcoded in `STATIC_COLUMNS` (filename, title, composer, tags, pages, folder, source)
- **Custom:** built dynamically from metadata keys via `mergeCustomKeys()`

`columnMap`, `allColumns`, and `allKeys` are all `computed` — they react to changes in `customColumns`. New custom keys are discovered two ways:
1. `getMetadataKeys()` call on mount (before settings restore)
2. Scanning sheet metadata after each `load()` response

### Auth

Google OAuth 2.0 with `itsdangerous` session cookies. `get_current_user` FastAPI dependency gates all data routes. Drive tokens are stored in `User.drive_token_json` and refreshed inline per-request.

### Backend-Agnostic Sheets

`Sheet.backend_type` (`"local"` | `"gdrive"`) + `Sheet.backend_file_id` (filesystem path or Drive file ID). Router code switches on `backend_type` for all file operations. Unique constraint: `(user_id, backend_type, backend_file_id)`.

## Conventions

### Frontend

- Vue 3 Composition API with `<script setup>` — no Options API
- No global state library (Pinia/Vuex) — per-view `ref`/`computed` state
- All API calls go through typed functions in `api.ts` using the `apiFetch<T>` wrapper
- Vite proxies `/api` → backend (configured via `VITE_API_TARGET` env var)

### Backend

- Fully async: `async def` routes, `AsyncSession`, `aiosqlite`
- Schema changes require Alembic migrations (`alembic revision --autogenerate`)
- `pydantic-settings` for config — env vars or `.env` file in `backend/`
- Google Drive API calls use raw `httpx`, not a client library

### Testing

- **API tests** use in-memory SQLite and `pytest-asyncio` (auto mode). Fixtures in `conftest.py` provide `db`, `seeded_db`, `client`, etc.
- **E2E tests** use Playwright with real pikepdf-generated PDF fixtures. `global-setup.ts` seeds the DB and injects auth cookies. The Playwright config spins up both backend (port 8001) and frontend (port 5174).
- **Fixture PDFs** are generated at test time by `backend/tests/generate_fixtures.py` (gitignored). They include both standard XMP metadata and sheeetz-namespace custom fields.
- Drive tests (`test_drive.py`) use `respx` to mock all Google API calls — no credentials needed.

### CI

GitHub Actions on PRs to `main` runs two jobs: `api-tests` and `e2e-tests`. Both must pass before merge.

## File Map

| What | Where |
|------|-------|
| FastAPI app entry | `backend/sheeetz/main.py` |
| Config / env vars | `backend/sheeetz/config.py` |
| ORM models | `backend/sheeetz/models.py` |
| Sheet list/sort/filter | `backend/sheeetz/routers/sheets.py` |
| PDF metadata logic | `backend/sheeetz/storage/metadata.py` |
| Folder scanning | `backend/sheeetz/storage/scanner.py` |
| Drive API wrappers | `backend/sheeetz/storage/drive_api.py` |
| All frontend API calls | `frontend/src/api.ts` |
| Sheet list + columns | `frontend/src/views/Sheets.vue` |
| PDF viewer + edit panel | `frontend/src/views/SheetViewer.vue` |
| Typeahead component | `frontend/src/components/AutocompleteInput.vue` |
| E2E test setup | `e2e/tests/global-setup.ts` |
| Fixture PDF generator | `backend/tests/generate_fixtures.py` |
| CI workflow | `.github/workflows/test.yml` |
