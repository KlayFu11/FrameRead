# S0 Ticket05 validation

## Scope

This record covers the backend admission commit-outcome recovery path and the admin video submission recovery UI. The PostgreSQL fault injector is test-only under `backend/tests/faults/`; production code has no fault-mode switch.

Implementation commit: `24adb23` on `feat/s0-ticket-05`.

## Evidence

- `backend/tests/integration/test_admission_faults.py` uses a real PostgreSQL TCP wire proxy and the real HTTP admin app.
- Dropped `COMMIT` and connection close produced `503 ADMISSION_UNCONFIRMED` with `action=resolve_same_key`; the same key could be submitted again without leaving rows after the first attempt.
- Forwarded `COMMIT` with the response discarded produced `202` with `replayed=true` and the original task ID. A direct operation lookup returned the same task.
- Connection close before the `tasks` insert produced `503 DEPENDENCY_UNAVAILABLE`; `tasks`, `task_outbox`, and `task_events` all remained empty. Logs contained `commit_outcome=rolled_back`.
- The two unknown-result modes logged `commit_outcome=unknown` and the faulted transaction did not re-run its COMMIT. The existing real deadlock test covers `40P01`; the new real `SERIALIZABLE` race covers `40001` and verifies whole-transaction retry with the same identity.
- `frontend/src/admin/VideoTaskForm.tsx` persists `uncertain=true` before sending, locks the submitted fields while pending/uncertain, retains every `503` key, distinguishes `QUEUE_FULL` and `DEPENDENCY_UNAVAILABLE`, and queries `/operations/video:new/{key}` through `api.request` without clearing the key on `404`.

## Checks

- Backend before integration: `pytest -q -p no:cacheprovider --basetemp tmp/pytest-ticket05/full --tb=short` -> `262 passed, 1 warning`.
- Backend after merging integration tip `03c7879` at `024b5e0`: `pytest -q -p no:cacheprovider --basetemp ../tmp/pytest-ticket05-integrated --tb=short` -> `274 passed, 1 warning`. The warning is the existing FastAPI/Starlette TestClient `httpx` deprecation. Tests use real PostgreSQL and Redis through the existing Ticket02 test environment, with per-test isolated databases.
- Ticket05 final backend fault tests: `pytest tests/integration/test_admission_faults.py -q -p no:cacheprovider --basetemp tmp/pytest-ticket05/final-faults --tb=short` -> `4 passed, 1 warning`. Both unknown-result modes assert exactly one `commit_outcome=unknown` log.
- Backend final lint/format: Ruff check passed; `80 files already formatted` after integration.
- Backend final types: strict mypy passed for 48 source files after integration; frozen uv lock check passed before integration, which added no dependency change.
- Frontend: `pnpm test --maxWorkers=1` -> `40 passed` across 5 test files. The regression tests also cover persistence before the first response and exclusion between operation lookup and submission retry.
- Frontend typecheck: `tsc --noEmit` passed.
- Frontend build: Vite production build passed (`90 modules transformed`).

## Browser acceptance

Completed on 2026-11-16 in an isolated Ego Lite 0.6.3.14 task space against `http://127.0.0.1:18085`: built frontend and a test HTTP gateway forwarding to the real Uvicorn admin app, real PostgreSQL through the test wire proxy, and real Redis. The shared Compose stack on port 8080 was not changed.

- A real dropped `COMMIT` produced the uncertain admission notice, locked original fields, retained the key after reload and after an operation lookup `404`, and recovered to queued task `1506efdf-d668-4bf4-82a9-10e9056143a0` through same-key retry.
- The gateway read a real `202` response and discarded it before replying to the browser. Reload retained the original key; same-key retry recovered queued task `468fa436-b5cd-4c32-9d59-8394911927ba`. The 390x844 mobile layout had no horizontal overflow.
- After the final UI change and production build, repeated the response-loss flow and recovered queued task `f7d1db48-6bc9-4284-98f0-df04af2cf505` through the actual operation-query button. Recovery cleared the stored key. The expired session was restored with the isolated test credential before this final pass.
- Inspected all screenshot artifacts: `uncertain-desktop.png`, `not-found-desktop.png`, `recovered-desktop.png`, `response-loss-mobile.png`, `response-loss-recovered-mobile.png`, and `final-recovery-actions-desktop.png`. The notices, locked inputs, and retry/query actions were readable and unobstructed. Snapshots and machine-readable checks are retained alongside this file in `browser-result.json`.

The task-created browser space and test gateway/API were closed. The runtime helper finished successfully and dropped its isolated test databases. Final integrated Docker/nginx acceptance remains part of Ticket10, outside this branch's gateway test.

## Review

Review found and fixed two timing issues: the PostgreSQL response-drop trigger must be armed before forwarding `COMMIT`, and an operation lookup must disable simultaneous submission retry. The lookup regression failed before the UI fix and passed after it. Complete diff review, including new tests and browser artifacts, then completed twice with no remaining finding.

No deployment or push was performed by this ticket branch.
